# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import copy
import json
import math
import os
import re
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import numpy as np

from layers import CAMP_CELL, CAMP_CLEAR, KILL_REACH, RESPAWN_FALLBACK, XpAuras, cover_route, item_table, kill_xp, stop_heights
from facts import RUN_SPEED
from geo import height_of, line_reach
from objectives import ObjectiveIndex
from errands import ANY_NPC, HERE, LAND_REACH, TODO_LINES, Errands, addon_chores, camp_buy, landed_pick, planned_kinds
import carried
import game
import nav
from routes import name_hash
from epic import closed_by, discrete_spots, heat_patches, if_offered, walks_alone
import plansteps
import planunits
import planlead
import planrepair
from kept import UNKEPT, keep
from versioned import Versioned
import questplan
import planreport
import questitems
import camping
import coretrip
import classtrip
import hearth
import profepics
import crafting
import races
import ticks
import storewriter
import mapzones
import moblevels
from mapzones import world_pos, zone_holding
from serverlog import log_error, start_thread
import storedonly
from gamedata import ITEM_TIPS, TRAINER_PRICES, client_table, item_name, load_class_spells, silenced_todos, stat_weights
from shared import plan_notes
from shared import placed_step
from shared import WAY_MOST
from shared import ride_of
import upgrades
from characters import char_entry, same_char

ROOT = os.path.dirname(os.path.abspath(__file__))


def quest_state(hub):
    q = (hub.extra or {}).get("quests") or {}
    done = set(hub.characters.completed_ids()) if getattr(hub, "characters", None) else set()
    for index, bits in (q.get("done") or {}).items():
        dungeons = hub.dungeons.list
        if not 1 <= int(index) <= len(dungeons):
            continue
        d = dungeons[int(index) - 1]
        ids = [x["id"] for x in d.get("quests", [])] + list(d.get("chain", []))
        done.update(ids[i] for i in bits if i < len(ids))
    return done, {x["id"]: x["complete"] for x in q.get("log") or []}


def wanted(ids):
    return tuple(sorted({int(i) for i in ids or () if str(i).strip().isdigit()}))


_ways_cache = {}

WAYS_KEPT = 1024


def shared_way_finder(hub, mode):
    level = (hub.state or {}).get("level") or 1
    faction = ((hub.status or {}).get("strs") or {}).get("faction", "")

    def find_way(inst, a, b, want=(), easy=False):
        want = wanted(want)
        key = (getattr(hub, "data_version", 0), inst, *(round(v) for v in a[:3]), len(a), *(round(v) for v in b[:3]), len(b),
               mode, level, faction, want, bool(easy))
        way = _ways_cache.get(key, UNKEPT)
        if way is not UNKEPT:
            return way
        with nav.easy_way() if easy else contextlib.nullcontext():
            way = work_way(inst, a, b, want)
        if way and (way.get("unbuilt") or way.get("degraded")):
            return way
        return keep(_ways_cache, key, way, WAYS_KEPT)

    way = mode if mode in ("safe", "fight") else "round"

    def work_way(inst, a, b, want):
        avoid = way_avoid(hub, inst, way, level, faction, want)
        height = lambda p: p[2] if len(p) > 2 else None
        with nav.wm.background():
            return round_or_through(hub, inst, tuple(a[:2]), tuple(b[:2]), height(a), height(b), None, False, avoid, level, way,
                                    side=faction or None)
    return find_way


def way_avoid(hub, inst, way, level, faction, want=()):
    if hub.paths.terrain.is_dungeon(inst):
        return None
    mobs = hub.world.threats(inst, level, faction, fight=way == "fight", want=want)
    return ((way, level, faction, want) + ((hub.world.level_cap(),) if way == "fight" else ()), mobs) \
        + (("roads",) if way == "safe" else ("seek",) if way == "fight" else ())


def walking_seconds(hub, mode):
    level = (hub.state or {}).get("level") or 1
    faction = ((hub.status or {}).get("strs") or {}).get("faction", "")
    way = mode if mode in ("safe", "fight") else "round"

    def seconds(inst, a, goals, want=()):
        avoid = way_avoid(hub, inst, way, level, faction, wanted(want))
        with nav.wm.background():
            return hub.paths.walk_seconds(inst, tuple(a[:2]), [tuple(g[:3]) for g in goals], avoid, level,
                                          start_z=a[2] if len(a) > 2 else None, side=faction or None)
    return seconds


_legs_cache = {}
LEGS_KEPT = 65536


def plan_ways(hub, find_route=None):
    finder = [find_route] if find_route else []
    faction = ((hub.status or {}).get("strs") or {}).get("faction", "")
    stamp = nav.store_stamp() if getattr(hub, "paths", None) is not None else None
    corners, known, searchers, failed = {}, {}, {}, set()

    def end(p):
        return round(p[1]), round(p[2])

    def searcher(inst, area):
        got = searchers.get(inst)
        if got is None or got[0] != area:
            with nav.wm.background():
                got = searchers[inst] = (area, hub.paths.leg_ways(inst, corners[inst], side=faction or None))
        return got[1]

    def route(a, b, want=()):
        if not finder:
            finder.append(shared_route_finder(hub, "any"))
        return finder[0](a, b, *((want,) if want else ()))

    def ridden(a, b):
        try:
            return ride_of(a, b, route) is not None
        except Exception as e:
            if not isinstance(e, nav.NotBuilt):
                log_error("the plan's rides", e)
            return False

    def ways(legs, spots=()):
        out, asked, play = [None] * len(legs), {}, {}
        for p in list(spots) + [p for leg in legs for p in leg]:
            if p:
                play.setdefault(p[0], []).append(p)
        for inst, ps in play.items():
            lo, hi = corners.get(inst, ((-math.inf, -math.inf), (math.inf, math.inf)))
            corners[inst] = ((max([lo[0]] + [p[1] for p in ps]), max([lo[1]] + [p[2] for p in ps])),
                             (min([hi[0]] + [p[1] for p in ps]), min([hi[1]] + [p[2] for p in ps])))
            known.setdefault(inst, {}).update({end(p): (float(p[1]), float(p[2])) for p in ps})
        for k, (a, b) in enumerate(legs):
            if a and b and a[0] == b[0]:
                if ridden(a, b):
                    out[k] = planunits.RIDE
                else:
                    asked.setdefault(a[0], []).append(k)
        for inst, ks in asked.items():
            if inst in failed or getattr(hub, "paths", None) is None:
                continue
            try:
                area = hub.paths.leg_region(inst, corners[inst])
                base = (getattr(hub, "data_version", 0), stamp, inst, area, faction)
                todo = [k for k in ks if _legs_cache.get(base + end(legs[k][0]) + end(legs[k][1]), UNKEPT) is UNKEPT]
                if todo:
                    got, extra = searcher(inst, area)([(legs[k][0][1:3], legs[k][1][1:3]) for k in todo],
                                                      list(known[inst].values()))
                    for (a, p), line in extra.items():
                        keep(_legs_cache, base + (round(a[0]), round(a[1]), round(p[0]), round(p[1])), line, LEGS_KEPT)
                    for k, line in zip(todo, got):
                        keep(_legs_cache, base + end(legs[k][0]) + end(legs[k][1]), line, LEGS_KEPT)
            except Exception as e:
                if not isinstance(e, nav.NotBuilt):
                    log_error("the plan's ways", e)
                failed.add(inst)
                continue
            for k in ks:
                out[k] = _legs_cache.get(base + end(legs[k][0]) + end(legs[k][1]))
        return out
    return ways


ROUTE_CODES = {"boat": "B", "zeppelin": "Z", "airship": "A", "tram": "T", "flight": "F"}

_routes_cache = {}

ROUTES_KEPT = 256


def shared_route_finder(hub, mode):
    taxi = hub.characters.known_taxi()
    st = hub.status or {}
    side = (st.get("strs") or {}).get("faction") or None
    hearth = None
    walk = shared_way_finder(hub, mode)
    known = len((taxi or {}).get("ids") or ()) + len((taxi or {}).get("hashes") or ())
    level = (getattr(hub, "state", None) or {}).get("level")
    race, spells, _ = travel_means(hub, side)
    means = (race, len(spells or ()))
    store = nav.store_stamp() if getattr(hub, "paths", None) is not None else None

    def find_route(a, b, want=()):
        want = wanted(want)
        key = (getattr(hub, "data_version", 0), a[0], round(a[1]), round(a[2]), b[0], round(b[1]), round(b[2]), mode, known,
               hearth, level, want, means, side)
        kept = _routes_cache.get(key, UNKEPT)
        if kept is not UNKEPT and kept[0] in (None, store):
            return kept[1]
        with nav.wm.background():
            plan = weigh_route(hub, tuple(a[:3]), tuple(b[:3]), "", side, taxi, hearth, patience=WEIGH_BACKGROUND)
        legs = plan.get("legs") or []
        pieces, at, ride, unbuilt = [], a, None, False
        for leg in legs:
            if leg["kind"] != "walk":
                said = leg["kind"] in ("door", "teleport")
                code = "D" if said else "H" if leg["kind"] == "hearth" else ROUTE_CODES.get(leg.get("vehicle"), "B")
                text = leg["name"] if said else re.sub(r"^Hearthstone to ", "", leg["name"]) \
                    if leg["kind"] == "hearth" else re.sub(r"^.*? to ", "", leg["name"])
                node = {"d": leg["node"]} if leg.get("node") else {}
                if not ride or (ride["r"] == "D" and code != "D"):
                    ride = {"r": code, "t": text, **({"n": leg["npc"]} if leg.get("npc") else {}),
                            **({"ni": leg["npcId"]} if leg.get("npcId") else {}), **node}
                elif code != "D":
                    ride["t"] = text
                    ride.pop("d", None)
                    ride.update(node)
                if leg.get("at"):
                    at = (leg["map"], *leg["at"])
                continue
            to = (leg["map"], *leg["to"])
            try:
                way = walk(leg["map"], tuple(at[1:]), tuple(to[1:]), want) if at and at[0] == leg["map"] else None
            except nav.NotBuilt as e:
                nav.wm.note_unbuilt(e.what)
                way, unbuilt = None, True
            short = bool(way and way.get("partial")) and way.get("gap", math.inf) > nav.NEAR_GAP
            if ride and short:
                break
            pts = [p[:3] for p in way["points"]] if way and not short and way.get("points") else [to[1:3]]
            pieces.append({**(ride or {}), "i": leg["map"], "w": [[round(float(v), 1) for v in p[:3]] for p in pts]})
            ride, at = None, to
        if ride:
            pieces.append({**ride, "i": None, "w": []})
        if pieces and plan.get("minutes"):
            pieces[0]["m"] = round(float(plan["minutes"]), 1)
        if plan.get("complete") and not unbuilt:
            keep(_routes_cache, key, (None, pieces or None), ROUTES_KEPT)
        elif store is not None:
            keep(_routes_cache, key, (store, pieces or None), ROUTES_KEPT)
        return pieces or None
    return find_route


GROUND_RADIUS = 150

GROUND_STEP = 10

WADE = 1.5


def shared_ground_finder(hub):
    def find_ground(inst, north, west):
        terrain = hub.paths.terrain
        if terrain.is_dungeon(inst):
            return None
        r0, c0 = nav.cell_of(north + GROUND_RADIUS, west + GROUND_RADIUS)
        r1, c1 = nav.cell_of(north - GROUND_RADIUS, west - GROUND_RADIUS)
        with nav.wm.background():
            ground = terrain.region(inst, r0, c0, r1 + 1, c1 + 1)["ground"]
        n = int(2 * GROUND_RADIUS // GROUND_STEP) + 1
        heights = []
        for i in range(n):
            for j in range(n):
                r, c = nav.cell_of(north + GROUND_RADIUS - i * GROUND_STEP, west + GROUND_RADIUS - j * GROUND_STEP)
                v = float(ground[r - r0, c - c0]) if 0 <= r - r0 < ground.shape[0] and 0 <= c - c0 < ground.shape[1] else math.nan
                heights.append(int(round(v)) if math.isfinite(v) else False)
        if not any(h is not False for h in heights):
            return None
        return {"n": round(north + GROUND_RADIUS, 1), "w": round(west + GROUND_RADIUS, 1), "s": GROUND_STEP, "c": n, "h": heights}
    return find_ground


_errands = {"version": None, "errands": None}


def errands_of(hub):
    if _errands["errands"] is None or _errands["version"] != hub.data_version:
        flights = (hub.routes.data.get("flights") or {}).get("nodes", ())
        _errands.update(version=hub.data_version, errands=Errands(hub.world.services, hub.world.geo, hub.routes.data.get("inns", ()),
                                                                  flights, hub.world.trainer_levels, hub.world.trainer_costs,
                                                                  teaches=trainer_teaches(hub), game_prices=game_prices(hub),
                                                                  walkers=hub.world.walking(),
                                                                  sellers=lambda item: camping.load().sellers(item),
                                                                  camp=lambda: camping.restock(camping.load(), hub.world.services),
                                                                  item_name=item_name, walled=hub.world.walled))
    return _errands["errands"]


SKIP_KINDS = {1: "train", 2: "bind", 3: "flightpath", 4: "sell", 5: "repair", 6: "restock",
              7: "camp"}

SKIP_THINGS = {1: "water", 2: "ammo", 3: "ankh", 4: "camp"}


def skipped_errands(hub):
    inns = {name_hash(i["names"][0]): i["names"][0] for i in hub.routes.data.get("inns", ())}
    out = {}
    for s in ((hub.extra or {}).get("epic") or {}).get("skipped") or ():
        kind, v = SKIP_KINDS.get(s["kind"]), s["value"]
        key = {"train": f"train:{v}", "flightpath": f"flightpath:{v}", "sell": "sell", "repair": "repair",
               "restock": f"restock:{SKIP_THINGS.get(v)}", "bind": f"bind:{inns.get(v)}" if v in inns else None}.get(kind)
        if key:
            out[key] = s["level"]
    return out


def camp_skipped(hub):
    return next((s["value"] for s in ((hub.extra or {}).get("epic") or {}).get("skipped") or ()
                 if SKIP_KINDS.get(s["kind"]) == "camp"), None)


def camp_state(hub, facts=None, money=None):
    s, st = hub.state or {}, hub.status or {}
    facts = ticks.game_facts(hub) if facts is None else facts
    me = me_record(hub)
    profs = [p for p in me.get("professions") or () if p.get("name") in SKILL_LINES]
    colours = {int(spell): c for book in (me.get("recipes") or {}).values() for spell, c in (book.get("known") or {}).items()}

    def npc(i):
        m = hub.world.mobs.get(str(i))
        return (m[0], round((m[1] + m[2]) / 2)) if m else None
    return {"level": s.get("level") or 1, "side": (st.get("strs") or {}).get("faction", ""),
            "skills": {SKILL_LINES[p["name"]]: p.get("rank") or 0 for p in profs},
            "caps": {SKILL_LINES[p["name"]]: p["max"] for p in profs if p.get("max")},
            "known": facts.get("recipes") or {}, "items": facts.get("items"), "auras": facts.get("auras") or {},
            "cooldowns": facts.get("cooldowns") or {}, "colours": colours, "skipped": camp_skipped(hub), "now": time.time(),
            "npc": npc, "camped": me.get("camped"), "money": money}


def grade_state(hub):
    s, st = hub.state or {}, hub.status or {}
    nums = st.get("nums") or {}
    cs = getattr(hub, "class_spells", None) or {}
    return {"level": s.get("level") or 1, "faction": (st.get("strs") or {}).get("faction", ""),
            "ammo_kind": nums.get("ammoKind") or None,
            "grades": {"ammo": nums.get("ammoGrade") or 0, "water": nums.get("waterGrade") or 0},
            "schedule": ((cs.get("classes") or {}).get(str(st.get("classId"))) or {}).get("levels"),
            "known_spells": hub.characters.known_spells()}


def errand_state(hub):
    st = hub.status or {}
    nums, strs = st.get("nums") or {}, st.get("strs") or {}
    side = strs.get("faction", "")
    me = hub.characters.playing() or {}
    junk = nums.get("bagJunk")
    if junk is None:
        bag_items = (me.get("bags") or {}).get("items")
        items = client_table("items.json", "items")[1] if bag_items is not None else {}
        junk = None if bag_items is None else sum(1 for i in bag_items if (items.get(str(i)) or [None, None])[1] == 0)
    return {**grade_state(hub), "class_id": st.get("classId"), "money": nums.get("money"),
            "bag_free": nums.get("bagFree"), "durability": nums.get("durability"), "junk": junk,
            "warnings": [w["key"] for w in st.get("warnings") or ()],
            "bind": strs.get("bind") or "", "trained": nums.get("trainedLevel") or None,
            "race": races.bit_of(me.get("race"), side),
            "known": hub.routes.known_flights(hub.characters.known_taxi(), side), "skipped": skipped_errands(hub),
            "silenced": sorted(silenced_todos() & set(TODO_LINES.values())),
            "junk_value": nums.get("bagJunkValue"),
            "addon_chores": addon_chores(nums.get("addonChores")),
            "camps": nums.get("camps"), "camp_wood": nums.get("campWood"), "camp_tool": nums.get("campTool")}


def camp_purchase(hub):
    services = getattr(getattr(hub, "world", None), "services", None) or ()
    return camp_buy({**errand_state(hub), "game": ticks.game_facts(hub)}, camping.restock(camping.load(), services))


def standable(hub, inst, pts, margin=KILL_REACH):
    import numpy as np
    t = getattr(getattr(hub, "paths", None), "terrain", None)
    if not pts or inst is None or t is None:
        return None
    try:
        if t.is_dungeon(inst):
            return None
        ns, ws = [p[0] for p in pts], [p[1] for p in pts]
        r0, c0 = nav.cell_of(max(ns) + margin, max(ws) + margin)
        r1, c1 = nav.cell_of(min(ns) - margin, min(ws) - margin)
        with nav.wm.background():
            g = t.region(inst, r0, c0, r1 + 1, c1 + 1)
    except (OSError, ValueError, KeyError, game.GameNotFound):
        return None
    ground, water = g["ground"], g["water"]
    with np.errstate(invalid="ignore"):
        ok = (~np.isnan(ground) & ~g["holes"] & ~g["hazard"] & (g["tilt"] <= nav.MAX_UP)
              & ~(np.isfinite(water) & (water - ground > WADE)))
    reached = None
    if getattr(t, "client_files", False):
        try:
            with nav.wm.background():
                reached = hub.paths.reached_ground(inst, pts)
        except (OSError, ValueError, KeyError, struct.error):
            reached = None

    def stand(p):
        r, c = nav.cell_of(p[0], p[1])
        if not (0 <= r - r0 < ok.shape[0] and 0 <= c - c0 < ok.shape[1] and ok[r - r0, c - c0]):
            return False
        if reached is None:
            return True
        rr0, rc0, walked = reached
        return 0 <= r - rr0 < walked.shape[0] and 0 <= c - rc0 < walked.shape[1] and bool(walked[r - rr0, c - rc0])
    return Footing(stand, ground, water, r0, c0)


class Footing:

    def __init__(self, stand, ground, water, r0, c0):
        self.stand, self.ground, self.water, self.r0, self.c0 = stand, ground, water, r0, c0

    def __call__(self, p):
        return self.stand(p)

    def cell(self, p):
        r, c = nav.cell_of(p[0], p[1])
        r, c = r - self.r0, c - self.c0
        if 0 <= r < self.ground.shape[0] and 0 <= c < self.ground.shape[1]:
            return float(self.ground[r, c]), float(self.water[r, c])
        return math.nan, math.nan

    def height(self, p):
        ground, water = self.cell(p)
        return water if math.isfinite(water) and not ground >= water else ground

    def under(self, p):
        z, ground = height_of(p), self.cell(p)[0]
        return z is not None and math.isfinite(ground) and z <= ground - nav.MOB_UNDER

    def stands_at(self, p):
        z = height_of(p)
        if z is None:
            return math.nan
        ground, water = self.cell(p)
        swims = math.isfinite(water) and water - z > WADE and not (math.isfinite(ground) and z <= ground - nav.MOB_UNDER)
        return water if swims else z


def stand_heights(hub, inst, stops, spawns):
    t = getattr(getattr(hub, "paths", None), "terrain", None)
    pts = [p[:2] for p in stops] + [p[:2] for p in spawns]
    if not pts or inst is None or t is None:
        return None
    cells = [nav.cell_of(p[0], p[1]) for p in pts]
    r0, c0 = min(r for r, _ in cells), min(c for _, c in cells)
    try:
        if t.is_dungeon(inst):
            return None
        with nav.wm.background():
            g = t.region(inst, r0, c0, max(r for r, _ in cells) + 1, max(c for _, c in cells) + 1)
    except (OSError, ValueError, KeyError, game.GameNotFound):
        return None
    ground = np.array([g["ground"][r - r0, c - c0] for r, c in cells], np.float64)
    water = np.array([g["water"][r - r0, c - c0] for r, c in cells], np.float64)
    with np.errstate(invalid="ignore"):
        at = np.where(np.isfinite(water) & ~(ground >= water), water, ground)[:len(stops)]
        z = np.array([p[2] if len(p) > 2 and p[2] is not None else np.nan for p in spawns], np.float64)
        wet, dry = water[len(stops):], ground[len(stops):]
        swims = np.isfinite(wet) & (wet - z > WADE) & ~(z <= dry - nav.MOB_UNDER)
    return [float(h) for h in at], [not s for s in swims.tolist()]


def game_prices(hub):
    return {c: {int(s): v for s, v in p.items()} for c, p in ((hub.trainer_prices or {}).get("classes") or {}).items()}


def trainer_teaches(hub):
    out = {int(n): set(ids) for n, ids in ((getattr(hub, "class_spells", None) or {}).get("trainers") or {}).items()}
    for n, ids in ((hub.trainer_prices or {}).get("trainers") or {}).items():
        if int(n) in out:
            out[int(n)] |= set(ids)
    return out


def note_trainer(hub, npc, spells):
    cid = (hub.status or {}).get("classId")
    if not cid or not spells:
        return
    tp, cid, build = hub.trainer_prices, str(cid), game.installed_version()
    tp.setdefault("classes", {}).setdefault(cid, {}).update({str(s): c for s, c, _ in spells})
    tp.setdefault("levels", {}).setdefault(cid, {}).update({str(s): lv for s, _, lv in spells})
    tp.setdefault("builds", {}).setdefault(cid, {}).update({str(s): build for s, _, _ in spells})
    if npc:
        had = tp.setdefault("trainers", {}).get(str(npc)) or []
        tp["trainers"][str(npc)] = sorted(set(had) | {s for s, _, _ in spells})
        tp.setdefault("seen", {})[str(npc)] = {"at": round(time.time()), "class": int(cid)}
    storewriter.save_json_later(TRAINER_PRICES, tp, indent=None)
    errands = _errands["errands"] if _errands["version"] == hub.data_version else None
    if errands:
        errands.game_prices.setdefault(cid, {}).update({s: c for s, c, _ in spells})
        if npc and npc in errands.teaches:
            errands.teaches[npc] |= {s for s, _, _ in spells}
    learn_trainer_spells(hub, cid, [s for s, _, _ in spells])
    if getattr(hub, "watch", None):
        hub.watch.poke()


def note_profession_trainer(hub, npc, profession, services, now=None):
    if not npc or not services:
        return
    now = round(now or time.time())
    hub.trainer_prices.setdefault("professions", {})[str(npc)] = {"profession": profession, "at": now,
                                                                   "char": hub.characters.current, "services": services}
    storewriter.save_json_later(TRAINER_PRICES, hub.trainer_prices, indent=None)
    hub.characters.profession_trainer(profession, npc, [s for s in services if "rank" in s], now)


def profession_summary(hub):
    me = hub.characters.playing() or {}
    books, trainers = me.get("recipes") or {}, me.get("profTrainers") or {}
    known = hub.characters.known_spells() or set()
    pd = prof_data()
    skills = [(p["name"], p.get("rank"), p.get("max")) for p in me.get("professions") or ()]
    named = {name for name, _, _ in skills}
    skills += [(name, b.get("skill"), b.get("max")) for name, b in sorted(books.items()) if name not in named]
    out = []
    for name, rank, top in skills:
        book, seen = books.get(name), trainers.get(name)
        ranks = [s for s in (seen or {}).get("ranks") or () if not s.get("known") and s["spell"] not in known]
        nxt = min(ranks, key=lambda s: (s["skill"], s["level"], s["spell"])) if ranks else None
        line = pd.by_name.get(name)
        out.append({"name": name, "rank": rank, "max": top, "recipes": len(book["known"]) if book else None,
                    "at": book["at"] if book else None, "trainerAt": seen["at"] if seen else None,
                    "next": {k: nxt[k] for k in ("rank", "skill", "level", "cost")} if nxt else None,
                    "line": line, "cat": camping.category(name), "gear": line is not None and pd.gear(line)})
    return out


_spells_building = threading.Lock()


def learn_trainer_spells(hub, cid, spells):
    levels = (((getattr(hub, "class_spells", None) or {}).get("classes") or {}).get(str(cid)) or {}).get("levels") or {}
    have = {s["id"] for v in levels.values() for s in v["spells"]}
    if all(s in have for s in spells) or not _spells_building.acquire(blocking=False):
        return

    def build():
        try:
            storewriter.flush_later()
            with open(os.path.join(ROOT, "data", "rebuild.log"), "a", encoding="utf-8") as log:
                log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} the class spells again, for a trainer's new spells\n")
                log.flush()
                subprocess.run([sys.executable or "python", os.path.join(ROOT, "tools", "build_class_spells.py")], cwd=ROOT,
                               check=True, stdout=log, stderr=subprocess.STDOUT,
                               env={**os.environ, storedonly.STORED_ONLY: "1"},
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            hub.class_spells = load_class_spells()
            if getattr(hub, "watch", None):
                hub.watch.poke()
        except (OSError, subprocess.CalledProcessError):
            log_error("building the class spells again for the trainer's new spells (its words in data/rebuild.log)")
        finally:
            _spells_building.release()
    start_thread("class-spells", build)


GLOW_NEAR = 600.0

CAMP_NEAR = 120.0

PATROL_NEAR = 150.0

OBJECTIVES = Versioned(lambda: ObjectiveIndex(), lambda where: log_error(where), "objective index")


def glow_index(hub):
    return OBJECTIVES.get(getattr(hub, "data_version", None) or 0)


def spawn_finder(hub, side=None):
    index = glow_index(hub)
    return lambda kind, oid: index.world_spawns(kind, oid, side)


SPAWN_POINTS_REACH = 2500.0


def table_spawns(hub, side=None):
    index = glow_index(hub)

    def find_spawns(e):
        ids = [("npc", str(m)) for m in e.get("mi") or ()]
        if not ids and e.get("it"):
            ids = [(kind, str(i)) for kind, i in index.item_sources(e["it"])]
        at, out = e.get("at") or (), {}
        if len(at) < 2:
            return []
        for kind, i in ids:
            for p in index.world_spawns(kind, i, side() if side else None):
                if p[0] == e.get("inst") and math.hypot(p[1] - at[0], p[2] - at[1]) <= SPAWN_POINTS_REACH:
                    out.setdefault((round(p[1]), round(p[2])), None)
        return [list(p) for p in out]
    return find_spawns


def found_inside(hub):
    index = glow_index(hub)
    area_of = {d["key"]: d.get("area") for d in hub.dungeons.list}
    ours = {str(a) for a in area_of.values() if a}

    def found_in(item, run):
        area = str(area_of.get(run[0]))
        spawns = [(a, p) for kind, oid in index.item_sources(item)
                  for a, pts in (((index.npcs if kind == "npc" else index.objects).get(str(oid)) or {}).get("s") or {}).items()
                  for p in pts]
        if any(a == area for a, _ in spawns):
            return True
        return bool(spawns) and all(p[0] < 0 or p[1] < 0 for _, p in spawns) and not any(a in ours for a, _ in spawns)
    return found_in


CAMP_DANGER_OWN = 1.0


def camp_danger(hub, faction):
    def danger_of(inst, level, own):
        rows = hub.world.threats(inst, level, faction, fight=True)
        if not len(rows) or not own:
            return rows[:0]
        pad = CAMP_CLEAR + 3 * CAMP_CELL
        ns, ws = [p[0] for p in own], [p[1] for p in own]
        rows = rows[(rows[:, 3] > 0) & (rows[:, 0] >= min(ns) - pad) & (rows[:, 0] <= max(ns) + pad)
                    & (rows[:, 1] >= min(ws) - pad) & (rows[:, 1] <= max(ws) + pad)]
        if len(rows):
            mine = np.array(own, float)
            theirs = np.zeros(len(rows), bool)
            for k in range(0, len(mine), 256):
                part = mine[k:k + 256]
                theirs |= ((np.abs(rows[:, None, 0] - part[None, :, 0]) < CAMP_DANGER_OWN)
                           & (np.abs(rows[:, None, 1] - part[None, :, 1]) < CAMP_DANGER_OWN)).any(axis=1)
            rows = rows[~theirs]
        return rows
    return danger_of


ESCORT_NEAR = 60.0


def escort_of(hub, steps, st):
    if st.get("objective") in ("kill", "loot") or st.get("quest") is None or st.get("get"):
        return None
    pick = next((s for s in steps if s.get("kind") == "pickup" and s.get("quest") == st["quest"] and s.get("at")), None)
    if pick:
        who, at = pick.get("npc"), (pick["inst"], *pick["at"][:2])
    else:
        g = next(iter((questplan.book().quests.get(st["quest"]) or {}).get("start") or ()), None)
        who, at = g and g.get("name"), g and g.get("map") is not None and world_pos(g["map"], g["x"] / 100, g["y"] / 100)
    if not who or not at:
        return None
    walks = [e for e in hub.world.escorts.get(who, ()) if e["map"] == at[0]
             and math.hypot(e["pts"][0][0] - at[1], e["pts"][0][1] - at[2]) <= ESCORT_NEAR]
    return min(walks, key=lambda e: math.hypot(e["pts"][0][0] - at[1], e["pts"][0][1] - at[2])) if walks else None


TALK_KINDS = ("pickup", "turnin", "errand")

WALK_ALONG = 1.25

WANDER_STAND = 15.0

WALK_SAME = 20.0

WALK_ALONG_LEAST = 30.0


def talk_npc(st):
    if st.get("kind") in TALK_KINDS:
        return st.get("npc") or None
    if st.get("kind") == "objective" and st.get("talk"):
        return (st.get("npc") if st.get("get") else st.get("target")) or None
    return None


def npc_ids(hub, name):
    ids = list(glow_index(hub).npc_names.get(name.lower(), ()))
    ids +=[str(sv["id"]) for sv in getattr(hub.world, "services", None) or () if sv.get("n") == name and sv.get("id")]
    return list(dict.fromkeys(str(i) for i in ids))


WALK_ACROSS = 40.0


def walk_across(pts):
    return max((math.dist(a, b) for k, a in enumerate(pts) for b in pts[k + 1:]), default=0.0)


def npc_walk(hub, name, inst, at):
    ids = npc_ids(hub, name)
    for walks in (getattr(hub.world, "patrols", None) or {}, getattr(hub.world, "giver_walks", None) or {}):
        best = None
        for i in ids:
            for r_inst, pts in walks.get(i, ()):
                if r_inst != inst or len(pts) < 2:
                    continue
                pts = [(float(n), float(w)) for n, w in pts]
                near = min(math.hypot(n - at[0], w - at[1]) for n, w in pts)
                if near <= PATROL_NEAR and (best is None or near < best[0]) and walk_across(pts) >= WALK_ACROSS:
                    best = (near, pts)
        if best:
            return [[round(n, 1), round(w, 1)] for n, w in best[1]]
    return None


def walk_stretch(walk, a, b):
    closed = math.dist(walk[0], walk[-1]) <= WALK_SAME
    if a <= b:
        return walk[a:b + 1]
    return walk[a:] + walk[1:b + 1] if closed else walk[b:a + 1][::-1]


def walk_on_way(seconds, inst, prev, walk, nxt):
    entry = min(range(len(walk)), key=lambda k: math.dist(walk[k], prev))
    if nxt is None:
        return False, [walk[entry]]
    out = min(range(len(walk)), key=lambda k: math.dist(walk[k], nxt))
    near, nearest = math.dist(walk[entry], prev) + WALK_SAME, entry
    yards, entry = min((sum(math.dist(p, q) for p, q in zip(s, s[1:])), k) for k in range(len(walk))
                       if math.dist(walk[k], prev) <= near for s in [walk_stretch(walk, k, out)])
    if yards < WALK_ALONG_LEAST:
        return False, [walk[nearest]]

    def cost(a, b):
        if seconds is not None:
            got = seconds(inst, tuple(a), [tuple(b)])
            if isinstance(got, (list, tuple)) and got and isinstance(got[0], dict) and got[0].get("seconds") is not None:
                return got[0]["seconds"]
        return math.dist(a, b) / RUN_SPEED
    there = cost(prev, walk[entry])
    on = there + yards / RUN_SPEED + cost(walk[out], nxt) <= WALK_ALONG * (there + cost(walk[entry], nxt))
    return (True, walk_stretch(walk, entry, out)) if on else (False, [walk[nearest]])


def talk_walks(hub, steps, start=None):
    patrols = getattr(hub.world, "patrols", None)
    if not patrols:
        return steps
    find = walking_seconds(hub, "any") if getattr(hub, "paths", None) is not None else None

    def seconds(inst, a, goals):
        try:
            return find(inst, a, goals)
        except storedonly.NotBuilt:
            return None
        except Exception:
            log_error("talk walks: walking seconds")
            return None
    seconds = seconds if find else None
    wander = getattr(hub.world, "wander", None) or {}
    prev = start[1:3] if start and len(start) > 2 else None
    prev_inst = start[0] if start else None
    for k, st in enumerate(steps):
        name = talk_npc(st)
        spot = st["giverAt"][1:3] if st.get("giverAt") and st["giverAt"][0] == st.get("inst") else (st.get("at") or [])[:2]
        walk = name and st.get("at") and npc_walk(hub, name, st["inst"], spot)
        if walk:
            nxt = next((s["at"][:2] for s in steps[k + 1:] if s.get("at") and s.get("inst") == st["inst"]), None)
            came = prev if prev is not None and prev_inst == st["inst"] else st["at"][:2]
            on, way = walk_on_way(seconds, st["inst"], came, walk, nxt)
            st["patrols"], st["walker"] = [walk], "on" if on else "off"
            st.pop("walkWay", None)
            if math.dist(way[0], st["at"][:2]) > WALK_SAME:
                st.setdefault("giverAt", [st["inst"], *st["at"][:2]])
                st["at"] = list(way[0])
            st["moves"] = move_words([name], on)
        elif walks_alone(st) and st.get("who") and st.get("at"):
            st["alone"] = True
            nxt = next((s["at"][:2] for s in steps[k + 1:] if s.get("at") and s.get("inst") == st["inst"]), None)
            came = prev if prev is not None and prev_inst == st["inst"] else st["at"][:2]
            if st.get("patrols"):
                walk = [[float(n), float(w)] for n, w in max(st["patrols"], key=len)]
                st["moves"] = move_words(st["who"], walk_on_way(seconds, st["inst"], came, walk, nxt)[0])
            elif any(wander.get(str(m), 0.0) > WANDER_STAND for m in st.get("mobs") or ()):
                st["moves"] = move_words(st["who"], None)
        if st.get("at"):
            prev, prev_inst = st["at"][:2], st.get("inst")
    return steps


def move_words(names, on):
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    s = "s" if len(names) == 1 else ""
    if on is None:
        return f"{who} roam{s} the marked area."
    if on:
        return f"{who} walk{s} along your route. You'll meet {who} on the way."
    return f"{who} walk{s} the marked route, shown in blue on the map."


def step_levels(hub, mobs, who):
    spans = {}
    for i in mobs:
        m = hub.world.mobs.get(str(i))
        if m:
            data = moblevels.span(m[1], m[2]) if len(m) > 2 else None
            spans.setdefault(m[0], []).append(moblevels.game(i, data or moblevels.of_data(i)))
    return [moblevels.merge(spans.get(name, ())) for name in who]


QUESTIE_TYPES = {"kill": "monster", "loot": "item", "use": "object"}


def objective_sources(index, st, whole=True):
    out = []
    if whole and st.get("quest") is not None:
        words = st.get("target") or st.get("text")
        out.append(index.quest_sources({"quest": st.get("quest"), "type": QUESTIE_TYPES.get(st.get("objective")), "text": words}))
        t = step_target(st) or {}
        out.append([("npc", str(i)) for i in t.get("mobs") or ()] + [("object", str(i)) for i in t.get("objects") or ()])
    out.append([("npc", i) for i in index.named_in(st.get("text") or st.get("target"), words=True)])
    return [s for s in out if s]


def step_target(st):
    words = st.get("target") or st.get("text")
    return next((t for t in (questplan.book().quests.get(st.get("quest")) or {}).get("targets") or () if t.get("name") == words), None)


def walk_escorts(hub, steps):
    for st in steps:
        walk = st.get("kind") == "objective" and escort_of(hub, steps, st)
        if walk:
            st["escort"], st["escortNpc"] = walk["pts"], walk["entry"]
            st["at"] = list(walk["pts"][-1])
    return steps


def step_places(hub, steps, start=None):
    return talk_walks(hub, walk_escorts(hub, steps), start)


def epic_targets(hub, steps, start=None):
    walk_escorts(hub, steps)

    def reach(p, route):
        return min((seg_yards(p, a, b) for a, b in zip(route, route[1:] or route)), default=math.inf)
    for k, st in enumerate(steps):
        if st.get("kind") == "objective" and not st.get("inPlace") and not st.get("owner") and (not st.get("spawns") or not st.get("mobs") and not st.get("objects")) and st.get("at"):
            m = st.get("map") or zone_holding(st["inst"], st["at"][0], st["at"][1])
            spawns, sources = [], []
            for sources in objective_sources(glow_index(hub), st, whole=not st.get("spawns")) if m else ():
                pts, _ = glow_index(hub).points(sources, m)
                spawns = [p for p in (world_pos(m, x, y) for x, y in pts) if p and p[0] == st["inst"]]
                if spawns:
                    break
            if not spawns and not st.get("spawns"):
                t = step_target(st) or {}
                spawns = [p for p in (world_pos(sm, x / 100, y / 100) for sm, x, y in t.get("spots") or ()) if p and p[0] == st["inst"]]
                sources = [("npc", str(i)) for i in t.get("mobs") or ()] + [("object", str(i)) for i in t.get("objects") or ()]
            near = [p for p in spawns if math.hypot(p[1] - st["at"][0], p[2] - st["at"][1]) <= GLOW_NEAR]
            if near or spawns:
                st["spawns"] = [[round(p[1], 1), round(p[2], 1)] for p in (near or spawns)]
                for key, kind in (("mobs", "npc"), ("objects", "object")):
                    if any(s[0] == kind for s in sources):
                        st[key] = [int(i) for s, i in sources if s == kind]
        if st.get("kind") == "errand" and st.get("what") == "farm" and st.get("spawns"):
            farm_camp(hub, steps, k, st)
            continue
        mobs = st.get("mobs") if st.get("kind") == "objective" else None
        if not mobs:
            continue
        st["who"] = list(dict.fromkeys(n for n in (npc_name(hub, i) for i in mobs) if n))
        st["levels"] = step_levels(hub, mobs, st["who"])
        at, route = st["at"][:2], st.get("loop") or []
        placed = []

        def spawned():
            if not placed:
                placed.append(camp_heights(hub, st["inst"], st.get("spawns") or (), mobs))
            return placed[0]
        camp = [p for p in (spawned() if route else [tuple(p) for p in st.get("spawns") or ()])
                if (reach(p, route) <= KILL_REACH if route else math.hypot(p[0] - at[0], p[1] - at[1]) <= CAMP_NEAR)]
        st["patrols"] = [[[round(float(n), 1), round(float(w), 1)] for n, w in pts]
                         for i in mobs for inst, pts in hub.world.patrols.get(str(i), ()) if inst == st["inst"]
                         and any(math.hypot(float(n) - c[0], float(w) - c[1]) <= PATROL_NEAR for n, w in pts for c in camp + [tuple(at)])]
        if len(camp) >= 2 and st.get("objective") in ("kill", "loot", "use") and not st.get("each") \
                and (st.get("area") or not route and not discrete_spots(camp)):
            st["area"] = True
            st.pop("loop", None)
        elif len(camp) >= 2 and st.get("objective") in ("kill", "loot", "use") and not st.get("each"):
            mid = (sum(p[0] for p in camp) / len(camp), sum(p[1] for p in camp) / len(camp))
            walked = [tuple(min(pts, key=lambda p: math.hypot(p[0] - mid[0], p[1] - mid[1]))) for pts in st["patrols"]]
            prev = next((s["at"][:2] for s in reversed(steps[:k]) if s.get("at") and s.get("inst") == st["inst"]), None)
            first = prev or (route[0] if route else None)
            at_height = {tuple(p[:2]): p for p in spawned()}
            st["loop"] = [list(p) for p in camp_way(hub, st["inst"], [at_height.get(tuple(p[:2]), p) for p in camp] + walked, first)]
        if st.get("loop"):
            stops = st["loop"]
            st["loop"] = stop_heights(stops, spawned(), stand=stand_heights(hub, st["inst"], stops, spawned()))
    return talk_walks(hub, steps, start)


def farm_camp(hub, steps, k, st):
    mobs = st.get("mobs") or ()
    if mobs:
        st["who"] = list(dict.fromkeys(n for n in (npc_name(hub, i) for i in mobs) if n))
        st["levels"] = step_levels(hub, mobs, st["who"])
    spawns = camp_heights(hub, st["inst"], st["spawns"], mobs)
    if len(spawns) < 2:
        return
    prev = next((s["at"][:2] for s in reversed(steps[:k]) if s.get("at") and s.get("inst") == st["inst"]), None)
    stops = [list(p) for p in camp_way(hub, st["inst"], spawns, prev)]
    st["loop"] = stop_heights(stops, spawns, stand=stand_heights(hub, st["inst"], stops, spawns))


def camp_way(hub, inst, spawns, start=None):
    pts, heights = [tuple(p[:2]) for p in spawns], [height_of(p) for p in spawns]
    return cover_route(pts, start=start, stand=standable(hub, inst, pts), heights=heights) \
        or cover_route(pts, start=start, heights=heights)


def npc_name(hub, npc):
    m = hub.world.mobs.get(str(npc))
    if m:
        return m[0]
    index = glow_index(hub)
    return ((getattr(index, "npcs", None) or {}).get(str(npc)) or {}).get("n")


def camp_heights(hub, inst, spawns, mobs):
    spots = [tuple(p[:2]) for p in spawns]
    best = [height_of(p) if height_of(p) is not None else math.nan for p in spawns]
    for mob in mobs if not all(math.isfinite(z) for z in best) else ():
        for k, z in enumerate(hub.world.spot_heights(str(mob), inst, spots)):
            if not math.isfinite(best[k]) and math.isfinite(z):
                best[k] = z
    return [(n, w, z) for (n, w), z in zip(spots, best)]


def epic_close(hub, key):
    epic = ((hub.shared.data or {}).get("epic") or {}) if getattr(hub, "shared", None) else {}
    return bool(epic.get("close")) if epic.get("key") == key else False


def game_unknown(hub):
    s, st = hub.state or {}, hub.status or {}
    if not ((st.get("strs") or {}).get("faction") and s.get("level")) or not hub.characters.playing():
        return "the game hasn't said who's playing yet, and it needs the WoW window on screen with the strip on to say so"
    if (hub.extra or {}).get("quests") is None:
        return "the game hasn't sent your quest log yet"
    return None


def planned_blind(hub):
    return game_unknown(hub) or mapzones.zones_unknown(hub)


def objectives_unknown(hub):
    ql = (hub.extra or {}).get("questlog") or {}
    if ql.get("char") != hub.characters.current:
        return ("the game hasn't sent your quest log's objectives yet, and it sends them within 15 seconds of the WoW window "
                "being on screen")
    return None


def build_epic(hub, key, anchor, parked=(), close=None):
    try:
        sig = built_sig(hub, key, anchor, parked, close)
    except Exception:
        log_error("an epic's signature")
        sig = None
    hit = _built.get(sig) if sig else None
    if hit and time.time() - hit[0] <= BUILT_SECONDS:
        return copy.deepcopy(hit[1])
    shared = getattr(hub, "shared", None)
    if not hasattr(shared, "plan_report") or getattr(shared, "working", None) == key or planreport.reporting_now():
        return worked_epic(hub, key, anchor, parked, close, sig)
    with planreport.reporting(lambda *said: shared.plan_report(key, *said)):
        try:
            return worked_epic(hub, key, anchor, parked, close, sig)
        finally:
            shared.plan_done(key)


def worked_epic(hub, key, anchor, parked, close, sig):
    epic = plan_epic(hub, key, anchor, parked, close)
    if epic is not None and not epic.get("waiting"):
        epic = dress_epic(hub, key, epic, anchor or here_now(hub))
    if sig and epic is not None and not epic.get("waiting"):
        keep(_built, sig, (time.time(), copy.deepcopy(epic)), BUILT_KEPT)
    return epic


BUILT_SECONDS = 60.0

BUILT_KEPT = 8

_built = {}


def built_sig(hub, key, anchor, parked, close):
    s = hub.state or {}
    done, log = quest_state(hub)
    facts = [key, list(anchor) if anchor else None, sorted(parked or ()), close, craft_kept(hub, key).get("craft"),
             epic_inputs(hub, done, log), who_now(hub), s.get("level"), s.get("xp"), s.get("rested"),
             (hub.extra or {}).get("auras"), None if anchor else here_now(hub), hub.characters.current,
             hub.characters.max_level(), ticks.game_facts(hub), getattr(hub, "data_version", 0)]
    return json.dumps(facts, sort_keys=True, default=lambda o: sorted(map(repr, o)) if isinstance(o, (set, frozenset)) else repr(o))


ALONG_LEAST = 4
ALONG_AREA_LEAST = 2

ALONG_WORSE = 200.0


def along_the_way(steps, start=None):
    out, k = list(steps), 1
    spot = plansteps.spot
    runs = planunits.runs_at([spot(s) for s in out])
    while k < len(out):
        st = out[k]
        spawns = st.get("spawns") or []
        turn = next((j for j in range(k + 1, len(out)) if out[j].get("quest") == st.get("quest") and (
            out[j].get("kind") == "turnin" or st.get("get") and out[j].get("kind") == "objective" and not out[j].get("get"))), None)
        near = planunits.reach("visit", runs[min(k, len(runs) - 1)])
        if (st.get("kind") != "objective" or st.get("objective") not in ("kill", "loot") or st.get("along") or turn is None
                or turn - k < 2 or len(spawns) < ALONG_LEAST or not spot(st)
                or plansteps.reach_of(st, spot(out[k - 1])) <= near or plansteps.reach_of(st, start) <= near):
            k += 1
            continue
        stops = [(i, spot(out[i])) for i in [k - 1] + list(range(k + 1, turn + 1)) if spot(out[i]) and spot(out[i])[0] == st["inst"]]
        met, last = set(), None
        for (_, a), (j, b) in zip(stops, stops[1:]):
            hit = {m for m, p in enumerate(spawns) if line_reach(tuple(p[:3]), a[1:], b[1:]) <= KILL_REACH}
            if hit:
                met, last = met | hit, j
        kills = (st.get("count") or 1) * (1 if st.get("objective") == "kill" else questplan.LOOT_KILLS)
        if len(met) < max(ALONG_LEAST, kills):
            k += 1
            continue
        rest, at = out[:k] + out[k + 1:], spot(st)
        detour = lambda i: plansteps.added(rest, i, at, None)
        pos = min(range(min(last, turn - 1), turn), key=detour)
        if detour(pos) > detour(k) + ALONG_WORSE:
            k += 1
            continue
        st["along"] = True
        out = rest[:pos] + [st] + rest[pos:]
        runs = planunits.runs_at([spot(s) for s in out])
    return promote_along(out)


def crosses_area(steps, j, st):
    spot, here = plansteps.spot, plansteps.spot(steps[j])
    if not here or here[0] != st["inst"]:
        return False
    ways = [[tuple(p[:3])] for p in steps[j].get("spawns") or () if steps[j].get("kind") == "objective"]
    before = spot(steps[j - 1]) if j else None
    ways.append([before[1:], here[1:]] if before and before[0] == here[0] else [here[1:]])
    spawns = [tuple(p[:3]) for p in st["spawns"]]
    return len(plansteps.near_way(spawns, ways, KILL_REACH)) >= min(ALONG_AREA_LEAST, len(spawns))


def beside(steps, j, st, near):
    here = plansteps.spot(steps[j])
    if not here or here[0] != st["inst"]:
        return False
    camp = [(here[0], *p[:2]) for p in steps[j].get("spawns") or () if steps[j].get("kind") == "objective"]
    return min(plansteps.reach_of(st, p) for p in [here] + camp) <= near


def promote_along(steps):
    out, spot = list(steps), plansteps.spot
    runs = planunits.runs_at([spot(s) for s in out])
    for st in list(out):
        k = out.index(st)
        if st.get("kind") != "objective" or st.get("objective") not in ("kill", "loot") or st.get("along") \
                or not st.get("spawns") or not spot(st):
            continue
        rest, at = out[:k] + out[k + 1:], spot(st)
        lo = planrepair.leveled(rest, st, max([j + 1 for j in range(k) if out[j].get("quest") == st.get("quest")] + [1]), k)
        best = (plansteps.added(rest, k, at, None), k)
        for j in range(lo, k):
            if crosses_area(out, j, st) or beside(out, j, st, planunits.reach("visit", runs[j])):
                for pos in (j, j + 1):
                    cost = plansteps.added(rest, pos, at, None)
                    if cost < best[0] - plansteps.TIE:
                        best = (cost, pos)
        if best[1] != k:
            out = rest[:best[1]] + [st] + rest[best[1]:]
            runs = planunits.runs_at([spot(s) for s in out])
    return out


seg_yards = line_reach


def plan_epic(hub, key, anchor, parked=(), close=None, kept=None):
    epic = plan_quests(hub, key, anchor, parked, close, kept)
    if epic and not epic.get("waiting"):
        if key.startswith("zone:"):
            epic["steps"] = class_trips(hub, epic["steps"], anchor or here_now(hub), parked, close)
        epic["steps"] = along_the_way(epic["steps"], tuple((anchor or here_now(hub) or ())[:3]) or None)
    return epic


def class_me(hub):
    s, st = hub.state or {}, hub.status or {}
    side = (st.get("strs") or {}).get("faction", "")
    done, log = quest_state(hub)
    return {"level": s.get("level") or 1, "xp": s.get("xp") or 0, "classId": st.get("classId"), "side": side,
            "race": races.bit_of(me_record(hub).get("race"), side), "done": done, "log": set(log)}


_quest_reader = None


def quest_reader(hub):
    s, st = hub.state or {}, hub.status or {}
    me = me_record(hub)
    side, cls = (st.get("strs") or {}).get("faction", ""), st.get("classId")
    done, log = quest_state(hub)
    skills, spells, cap = skills_of(me), spells_of(me), hub.characters.max_level()
    closed = {k: (hub.dungeons.by_key.get(k) or {}).get("name") or k for k, o in hub.dungeons.open_now().items() if not o.get("open")}
    b = questplan.book()
    key = (id(b), s.get("level") or 1, side, me.get("race"), cls, frozenset(done), frozenset(log), tuple(sorted(skills.items())),
           None if spells is None else frozenset(spells), cap, tuple(sorted(closed)))
    global _quest_reader
    got = _quest_reader
    if got is None or got[0] != key:
        got = _quest_reader = (key, questplan.QuestPlan(
            "item:0", "", [], b, lambda m, x, y: world_pos(m, x / 100, y / 100), s.get("level") or 1, 0, side,
            races.bit_of(me.get("race"), side), cls, skills, done, log, None, cap=cap, spells=spells, closed=closed))
    return got[1]


def class_chains(hub):
    me = class_me(hub)
    if not me["classId"]:
        return []
    cap = hub.characters.max_level()
    return classtrip.offers(classtrip.chains(), me["classId"], me["side"], me["race"], me["done"], me["log"], cap, 0, cap,
                            class_near(hub, here_now(hub)), quest_opens(hub))


def mob_levels(hub):
    def mob_level(npc):
        m = hub.world.mobs.get(str(npc))
        return (m[1] + m[2]) / 2 if m else None
    return mob_level


def quest_opens(hub):
    book, mob_level = questplan.book(), mob_levels(hub)

    def opens(qid):
        q = book.quests.get(qid)
        return questplan.quest_waits(q, mob_level) if q else None
    return opens


def class_near(hub, at):
    speed = hub.characters.travel_speed() or questplan.RUN
    return classtrip.nearness(plan_walk(hub, speed), giver_spot, at)


def giver_spot(m, x, y):
    return world_pos(m, x / 100, y / 100)


def class_trips(hub, steps, at, parked=(), close=None):
    all_chains = classtrip.chains()
    if not all_chains or not steps:
        return steps
    me = class_me(hub)
    if not classtrip.open_chains(all_chains, me["classId"], me["side"], me["race"], me["done"], hub.characters.max_level(),
                                 log=me["log"]):
        return steps
    at = tuple(at[:3]) if at else None
    step_costs(hub, steps, at)

    def chain_plan(chain, quests, spot, level):
        with planreport.quiet():
            sub = quest_epic(hub, f"{classtrip.KEY}{chain['id']}", spot, parked, bool(close), at_level=level,
                             quests=quests)
        sub_steps = (sub or {}).get("steps") or []
        if sub_steps:
            step_costs(hub, sub_steps, spot)
        return sub_steps
    speed = hub.characters.travel_speed() or questplan.RUN
    return classtrip.plan(steps, at, me, all_chains, questplan.xp_table(), chain_plan, plan_walk(hub, speed), giver_spot,
                          hub.characters.max_level(), quest_opens(hub))


def who_now(hub):
    s, st, me = hub.state or {}, hub.status or {}, me_record(hub)
    return {"level": s.get("level"), "classId": st.get("classId"), "race": me.get("race"),
            "side": (st.get("strs") or {}).get("faction"), "skills": skills_of(me)}


def skills_of(me):
    return {SKILL_LINES[p["name"]]: p.get("rank") or 0 for p in me.get("professions") or () if p.get("name") in SKILL_LINES}


def spells_of(me):
    book, recipes = me.get("spells"), me.get("recipes") or {}
    if book is None and not recipes:
        return None
    return {int(s) for s in book or ()} | {int(s) for b in recipes.values() for s in b.get("known") or ()}


def given_offers(hub, done):
    answers = getattr(hub, "offers", None)
    if not answers:
        return set()
    book_ = questplan.book().quests
    seen = {q for q in answers.offered_ever() if (book_.get(q) or {}).get("unconfirmed") and not book_[q].get("unknown")}
    return {q for q in answers.known(who_now(hub), done) if unknown_giver(q) is not None} | seen


def unknown_giver(qid):
    q = questplan.book().quests.get(int(qid)) if qid is not None else None
    if not q or not if_offered(q):
        return None
    return next((g.get("name") for g in q.get("start") or () if g.get("name") and not g.get("item")), "")


def log_objectives(hub):
    return {e["id"]: [(o.get("text") or "", o.get("finished"), o.get("type")) for o in e.get("objectives") or ()]
            for e in log_entries(hub) if "id" in e}


def log_levels(hub):
    return {e["id"]: e["level"] for e in log_entries(hub) if "id" in e and e.get("level")}


def log_entries(hub):
    ql = (hub.extra or {}).get("questlog") or {}
    if ql.get("char") not in (None, hub.characters.current):
        return []
    return ql.get("entries") or []


def plan_quests(hub, key, anchor, parked=(), close=None, kept=None):
    close = epic_close(hub, key) if close is None else close
    waiting = planned_blind(hub) or objectives_unknown(hub)
    if waiting:
        return {"waiting": waiting}
    return quest_epic(hub, key, anchor, parked, close, given_offers(hub, quest_state(hub)[0]), kept=kept)


def bag_items(me):
    items = (me.get("bags") or {}).get("items") or {}
    return {int(i[0]) for i in items} if isinstance(items, list) else {int(i) for i in items}


STEP_TALK = 10.0

STEP_OTHER = 30.0

STEP_RUN = 1800.0

STEP_DETOUR = 1.25

STEP_FAR = 600.0


def reckoned_walk(speed):
    def walk(a, b):
        if not a or not b:
            return 0.0
        if a[0] != b[0]:
            return STEP_FAR
        return min(math.hypot(a[1] - b[1], a[2] - b[2]) * STEP_DETOUR / speed, STEP_FAR)
    return walk


def objective_fights(hub, step):
    mobs = [m for m in (hub.world.mobs.get(str(m)) for m in step.get("mobs") or () if str(m).isdigit()) if m]
    fights = mobs and step.get("objective") not in ("talk", "interact", "event")
    kills = (step.get("count") or 1) * (1 if step.get("objective") == "kill" else questplan.LOOT_KILLS) if fights else 0
    return mobs, kills


def step_coin(hub, steps):
    for step in steps:
        if step.get("kind") == "objective":
            mobs, kills = objective_fights(hub, step)
            coin = sum(float(m[7] or 0) for m in mobs) / len(mobs) if mobs else 0.0
            if kills and coin > 0:
                step["gain"] = int(round(kills * coin))
    return steps


def step_costs(hub, steps, at, camps=False, level=None):
    s = hub.state or {}
    level, into, rested = level or s.get("level") or 1, 0 if level else s.get("xp") or 0, s.get("rested") or 0
    cap = hub.characters.max_level()
    book, speed = questplan.book(), hub.characters.travel_speed() or questplan.RUN
    xp = questplan.xp_table()
    inside = {d.get("instance") for d in hub.dungeons.list}
    auras, clock = XpAuras(hub.extra.get("auras")), 0.0
    prev = at
    walk_of = reckoned_walk(speed)
    for step in steps:
        gain, busy = 0.0, STEP_TALK
        if step["kind"] == "turnin" and step.get("quest") in book.quests:
            gain = questplan.quest_xp(book.quests[step["quest"]], level, cap) * auras.factor("quest", clock)
        elif step["kind"] == "objective":
            mobs, kills = objective_fights(hub, step)
            levels = [(m[1] + m[2]) / 2 for m in mobs]
            health = [(m[4] + m[5]) / 2 for m in mobs if m[4] > 0]
            if levels:
                mob = sum(levels) / len(levels)
                gain = kills * kill_xp(level, mob, cap) * hub.world.xp.share(level, mob, step.get("inst") in inside) \
                    * auras.factor("kill", clock)
                more = min(gain, rested)
                gain, rested = gain + more, rested - more
            busy = kills * hub.world.kill_seconds(level, sum(health) / len(health) if health else hub.world.typical_health(level)) \
                if kills else STEP_OTHER
            if camps and kills and gain > 0:
                step["kh"], step["kn"] = camp_reckoning(hub, step, busy / kills)
        elif step["kind"] == "dungeon":
            busy = STEP_RUN
        spot = (step["inst"], *step["at"][:2]) if step.get("at") and step.get("inst") is not None else None
        walk = 0.0
        if spot and prev:
            walk = math.hypot(spot[1] - prev[1], spot[2] - prev[2]) * STEP_DETOUR / speed if spot[0] == prev[0] else STEP_FAR
            hearthed = step.get("hearth") or {}
            if hearthed.get("p") and hearthed.get("spot"):
                walk = min(walk, hearth.CAST + walk_of(tuple(hearthed["spot"]), spot))
        step["xp"], step["sec"] = int(round(gain)), int(round(min(walk, STEP_FAR) + busy))
        clock += step["sec"]
        into += gain
        while level < cap and xp.get(level) is not None and into >= xp[level]:
            into -= xp[level]
            level += 1
        prev = spot or prev
    return steps


def run_seconds(hub):
    return lambda steps, at, level=None: [s["sec"] for s in step_costs(hub, [dict(s) for s in steps], at, level=level)]


def camp_reckoning(hub, step, kill_s):
    rate = 3600.0 / kill_s if kill_s > 0 else 0.0
    spawns = [(float(p[0]), float(p[1])) for p in step.get("spawns") or ()]
    patches = heat_patches(spawns) if spawns else []
    mobs = [str(m) for m in step.get("mobs") or () if str(m).isdigit()]
    n = len(patches[0][1]) if patches else None
    if n and mobs:
        world = hub.world
        backs = [world.measured_respawn(m) or world.respawn_npcs.get(m) or RESPAWN_FALLBACK for m in mobs]
        rate = min(rate, 3600.0 * n / (sum(backs) / len(backs)))
    return max(1, int(round(rate))), n


def reckon_levels(hub, steps, at=None, costed=False):
    s = hub.state or {}
    level, into = s.get("level") or 1, s.get("xp") or 0
    cap, xp = hub.characters.max_level(), questplan.xp_table()
    copies = steps if costed else step_costs(hub, [dict(st) for st in steps], at)
    out = []
    for st in copies:
        if st.get("grind") and st["grind"] > level:
            level, into = min(st["grind"], cap), 0
        out.append(level)
        into += st.get("xp") or 0
        while level < cap and xp.get(level) is not None and into >= xp[level]:
            into -= xp[level]
            level += 1
    return out


def grind_first(steps):
    for k, st in enumerate(steps):
        j = k
        while st.get("grind") and j > 0 and steps[j - 1].get("kind") == "errand":
            j -= 1
        train = next((i for i in range(j, k) if steps[i].get("what") == "train"
                      and ((steps[i].get("need") or {}).get("level") or 0) >= st["grind"]), None)
        if train is not None:
            steps[train]["grind"] = st.pop("grind")
    return steps


def dress_epic(hub, key, epic, at, chores=True, landed=False, leave=None):
    d = None if ":" in key else hub.dungeons.by_key.get(key)
    only = planned_kinds({"train"} if key.startswith(("log:", classtrip.KEY, f"{CRAFT_EPIC}:")) else None,
                         addon_chores(((hub.status or {}).get("nums") or {}).get("addonChores")))
    step_coin(hub, epic["steps"])
    ways = plan_ways(hub) if chores else None
    shown = set()

    def chores_shown():
        if not chores or not planreport.reporting_now():
            return
        new = []
        for s in epic["steps"]:
            seen = repr(placed_step(s)) if s["kind"] == "errand" else None
            if seen and seen not in shown:
                shown.add(seen)
                new.append(s)
        planreport.report(placed=new, ordered=epic["steps"])
    if chores:
        planreport.report("chores")
        step_places(hub, epic["steps"], at)
        me = {**errand_state(hub), "game": ticks.game_facts(hub)}
        notes = camp_chores(hub, key, epic, at, me) + prof_chores(hub, key, epic, at, me) + fish_chores(hub, key, epic, at, me) \
            + craft_chores(hub, key, epic, at, me)
        epic["steps"], more = errands_of(hub).plan(epic["steps"], None, me, at, only=only)
        epic["errandNotes"] = notes + more
        chores_shown()
        step_costs(hub, epic["steps"], at)
        epic["steps"], trips = core_trips(hub, epic["steps"], at, me)
        epic["errandNotes"] += trips
        chores_shown()
        step_costs(hub, epic["steps"], at)
        epic["steps"] = plan_hearths(hub, epic["steps"], at, bind_steps=only is None or "bind" in only)
        chores_shown()
        epic["steps"] = planrepair.while_there(epic["steps"], tuple(at[:3]) if at else None,
                                               lambda steps: reckon_levels(hub, steps, at, costed=True), ways=ways)
        chores_shown()
    if chores:
        step_places(hub, epic["steps"], at)
        done, log = quest_state(hub)
        epic["steps"], _ = planlead.settle(epic["steps"], tuple(at[:3]) if at else None, log, done,
                                           reckon_levels(hub, epic["steps"], at, costed=True),
                                           money=errand_state(hub).get("money"), ways=ways)
        chores_shown()
    step_costs(hub, epic["steps"], at)
    epic["steps"] = plan_hearths(hub, epic["steps"], at, bind_steps=False)
    errand_also(hub, epic["steps"])
    if landed:
        repick_errands(hub, epic["steps"], at, leave)
    grind_first(epic["steps"])
    step_costs(hub, epic["steps"], at, camps=True)
    for step in epic["steps"]:
        z = step.get("map") or (step.get("at") and zone_holding(step["inst"], step["at"][0], step["at"][1]))
        if z:
            step["map"] = z
            if not step.get("zone"):
                step["zone"] = mapzones.MAPS[str(z)].get("name")
        run = d or hub.dungeons.by_key.get(step.get("dungeon") or "")
        if step["kind"] == "dungeon" and run:
            step["bosses"] = boss_track(run, step.get("quests") or [], hub.dungeons)
            step["qmobs"] = quest_mobs(hub, run, step.get("quests") or [])
    epic_targets(hub, epic["steps"], at)
    each_respawns(hub, epic["steps"])
    chores_shown()
    if planreport.reporting_now():
        planreport.report(finds=planreport.step_finds(epic["steps"], quest_state(hub)[1], (hub.state or {}).get("zone"), epic),
                          ordered=epic["steps"])
    return epic


def each_respawns(hub, steps):
    world = getattr(hub, "world", None)
    seen = getattr(world, "measured_respawn", None) or (lambda npc: None)
    npcs, objects = getattr(world, "respawn_npcs", None) or {}, getattr(world, "respawn_objects", None) or {}
    for st in steps:
        if not st.get("each"):
            continue
        times = [seen(i) or npcs.get(str(i)) for i in st.get("mobs") or ()] + [objects.get(str(i)) for i in st.get("objects") or ()]
        st["respawn"] = int(max([t for t in times if t] or [RESPAWN_FALLBACK]))


HEARTHSTONE_SPELL = 8690
_hearth_cooldown = {"seconds": None}


def hearth_cooldown():
    if _hearth_cooldown["seconds"] is None:
        seconds = hearth.COOLDOWN
        try:
            import client
            row = next((r for r in client.rows("SpellCooldowns", stored=True) if r.get("SpellID") == str(HEARTHSTONE_SPELL)), None)
            ms = max(int(row.get("CategoryRecoveryTime") or 0), int(row.get("RecoveryTime") or 0)) if row else 0
            seconds = ms / 1000 if ms > 0 else seconds
        except Exception:
            pass
        _hearth_cooldown["seconds"] = seconds
    return _hearth_cooldown["seconds"]


def bind_inns(hub):
    faction = ((hub.status or {}).get("strs") or {}).get("faction", "")
    keepers = {}
    for name, place, _ in errands_of(hub).places({"inn"}, faction):
        keepers.setdefault(name, place)
    inns = [i for i in hub.routes.data.get("inns", ()) if i.get("binds") and i.get("npc") in keepers]
    return inns, {i["names"][0]: (i["npc"], keepers[i["npc"]]) for i in inns}


def leg_travel(hub, speed):
    walk, memo = reckoned_walk(speed), {}
    st = hub.status or {}
    side = (st.get("strs") or {}).get("faction") or None

    def travel(a, b):
        if not a or not b:
            return 0.0
        yards = math.hypot(a[1] - b[1], a[2] - b[2]) if a[0] == b[0] else math.inf
        if yards < WAY_MOST:
            return walk(a, b)
        key = (a[0], round(a[1]), round(a[2]), b[0], round(b[1]), round(b[2]))
        if key not in memo:
            seconds = None
            try:
                race, spells, bags = travel_means(hub, side)
                plans = hub.routes.plans(tuple(a[:3]), tuple(b[:3]), "", side, hub.characters.known_taxi(), None, speed,
                                         race=race, spells=spells, bags=bags, wait=True)
                seconds = plans[0]["yards"] / speed if plans else None
            except Exception:
                seconds = None
            memo[key] = seconds if seconds else (yards * STEP_DETOUR / speed if a[0] == b[0] else STEP_FAR)
        return memo[key]
    return travel


def plan_walk(hub, speed):
    walk = reckoned_walk(speed)
    walk.travel = leg_travel(hub, speed)
    return walk


def plan_hearths(hub, steps, at, bind_steps=True):
    st = hub.status or {}
    nums, strs = st.get("nums") or {}, st.get("strs") or {}
    inns, keepers = bind_inns(hub)
    gone = {k[len("bind:"):] for k in skipped_errands(hub) if k.startswith("bind:")}
    walk = plan_walk(hub, hub.characters.travel_speed() or questplan.RUN)
    return hearth.plan(steps, tuple(at[:3]) if at else None, walk, inns, strs.get("bind") or "",
                       nums.get("hearth"), hearth_cooldown(), keepers if bind_steps else None, gone)


def spec_name(hub, cid):
    tree = upgrades.spec_tree((hub.status or {}).get("nums") or {})
    specs = ((stat_weights().get("classes") or {}).get(str(cid)) or {}).get("specs") or ()
    name = next((s.get("name") for s in specs if s.get("tree") == tree), None) if tree else None
    return re.sub(r"\s*\(.*\)$", "", name) if name else None


def core_trips(hub, steps, at, me):
    if "train" not in (me.get("addon_chores") or ()) or me.get("known_spells") is None or not me.get("schedule"):
        return steps, []
    s, st = hub.state or {}, hub.status or {}
    strs = st.get("strs") or {}
    level, cid, faction = s.get("level") or 1, st.get("classId"), strs.get("faction", "")
    cap = hub.characters.max_level()
    speed = hub.characters.travel_speed() or questplan.RUN
    errands = errands_of(hub)
    spec = spec_name(hub, cid)
    named = {k for v in me["schedule"].values() for x in v.get("spells") or () for k in (x.get("specs") or {})}
    spec = spec if not spec or spec in named else next((k for k in sorted(named) if k.startswith(spec) or spec.startswith(k)), spec)
    mine = {"level": level, "xp": s.get("xp") or 0, "known": set(me["known_spells"]), "race": me.get("race"),
            "spec": spec, "skipped": me.get("skipped") or {}, "money": me.get("money")}
    return coretrip.plan(steps, tuple(at[:3]) if at else None, plan_walk(hub, speed), mine, me["schedule"],
                         questplan.xp_table(), errands.places({"class"}, faction, detail=cid, ids=True), errands.teaches, cap)


def camp_chores(hub, key, epic, at, errand):
    cd = camping.load()
    me = camp_state(hub, errand.get("game"), errand.get("money"))
    if key == camping.KEY:
        chores = camping.Chores(cd, me, errands_of(hub), at)
        steps, later = chores.plan(epic["steps"], epic.get("camp"), epic.get("later") or ())
        wall = chores.wall_step(steps)
        epic["steps"], epic["campLater"] = steps + ([wall] if wall else []), later
        return chores.notes
    if key.startswith(("zone:", "log:", classtrip.KEY)):
        epic["steps"] = camping.make_camp(epic["steps"], cd, me, errands_of(hub))
    return []


_prof_data = {"camp": None, "data": None}


def prof_data():
    cd = camping.load()
    if _prof_data["camp"] is not cd:
        _prof_data.update(camp=cd, data=profepics.ProfData(cd))
    return _prof_data["data"]


def zone_mapper(hub):
    area_map = getattr(getattr(getattr(hub, "world", None), "geo", None), "area_map", None) or {}
    return lambda area: area_map.get(str(area))


def prof_state(hub, facts=None, record=None, money=None):
    if record is not None:
        return profepics.state_of(record, record.get("level"), record.get("faction"),
                                  profepics.game_ranks(record, getattr(hub, "trainer_prices", None)), None, zone_mapper(hub))
    s, st = hub.state or {}, hub.status or {}
    facts = ticks.game_facts(hub) if facts is None else facts
    me = me_record(hub)
    return profepics.state_of(me, s.get("level") or 1, (st.get("strs") or {}).get("faction", ""),
                              profepics.game_ranks(me, getattr(hub, "trainer_prices", None)), facts.get("items"),
                              zone_mapper(hub), here_now(hub), money)


def prof_line(key):
    got = profepics.epic_of(key)
    return got[0] if got and (got[2] is None or got[2] in crafting.MODES) else None


def level_of(hub, key):
    line = prof_line(key)
    pd = prof_data()
    if line is None or pd.cd.names.get(line, "") in profepics.OFFERS:
        return None
    _, to, way = profepics.epic_of(key)
    if to is None:
        to = profepics.status(pd, line, prof_state(hub))["target"]
    return line, to, way or crafting.BOTH


def prof_epics_in(hub, key):
    line = prof_line(key)
    if line is not None:
        return line, []
    epics = profepics.on(me_record(hub))
    return None, (sorted(epics) if epics and (key.startswith(("zone:", "log:", classtrip.KEY)) or key == camping.KEY) else [])


def prof_chores(hub, key, epic, at, errand):
    line, riding = prof_epics_in(hub, key)
    if line is None and not riding or line is not None and level_of(hub, key):
        return []
    pd, me, notes = prof_data(), prof_state(hub, errand.get("game"), money=errand.get("money")), []
    if line is not None:
        epic["steps"], epic["profChores"] = profepics.own_plan(epic["steps"], pd, me, errands_of(hub), at,
                                                               profepics.status(pd, line, me), notes)
        return notes
    statuses = [profepics.status(pd, pd.by_name[n], me) for n in riding if n in pd.by_name]
    epic["steps"], epic["profChores"] = profepics.ride_along(epic["steps"], pd, me, errands_of(hub), at, statuses, notes)
    return notes


def fish_chores(hub, key, epic, at, errand):
    line, riding = prof_epics_in(hub, key)
    pd, me, notes = prof_data(), prof_state(hub, errand.get("game"), money=errand.get("money")), []
    fish = pd.by_name.get(profepics.FISHING)
    fishing = profepics.status(pd, fish, me) if fish is not None and (line == fish or profepics.FISHING in riding) else None
    epic["steps"] = profepics.fish_gear(epic["steps"], pd, me, errands_of(hub), at, fishing, own=line == fish, notes=notes)
    return notes


def prof_inputs(hub):
    me = me_record(hub)
    if not profepics.on(me):
        return None
    return [sorted(profepics.on(me)), [(p.get("name"), p.get("max")) for p in me.get("professions") or ()],
            sorted((n, len(b.get("known") or {})) for n, b in (me.get("recipes") or {}).items())]


def prof_panel(hub):
    pd = prof_data()
    snap = hub.characters.snapshot()
    current = snap["current"] if hub.characters.playing() else None
    out = {"list": [], "epics": [], "alts": {}, "playing": current}
    if current:
        out.update(profepics.panel(pd, prof_state(hub), me_record(hub)))
        epic = (((getattr(hub, "shared", None) and hub.shared.data) or {}).get("epic")) or {}
        steps = epic.get("steps") or () if epic.get("char") is None or same_char(epic["char"], playing_char(hub)) else ()
        keys = [s.get("key") or "" for s in steps if s.get("k") == "S"]
        for e in out["epics"]:
            e["planned"] = any(k.startswith(f"{profepics.PREFIX}{e['line']}:") for k in keys)
    for key, record in (snap.get("chars") or {}).items():
        epics = profepics.on(record)
        if key == current or not epics:
            continue
        me = prof_state(hub, record=record)
        out["alts"][key] = [{**profepics.status(pd, pd.by_name[n], me), "hidden": bool(e.get("hidden"))}
                            for n, e in sorted(epics.items()) if n in pd.by_name]
    return out


def repick_errands(hub, steps, at, leave=None):
    errands, me = errands_of(hub), errand_state(hub)
    here = tuple(at[:3]) if at else None
    for k, st in enumerate(steps):
        if st.get("kind") != "errand" or not here:
            break
        mine = plansteps.spot(st)
        if not (leave and leave(st)) and not (mine and plansteps.gap(here, mine) <= HERE):
            e = landed_pick(st.get("also"), here)
            if e and e["npc"] != st.get("npc"):
                moved = errands.moved_to(st, (e["npc"], (e["inst"], *e["at"][:2], e["at"][2] if len(e["at"]) > 2 else None,
                                                         e.get("map")), {}), me)
                steps[k] = {**moved, **({"cost": e["cost"]} if e.get("cost") else {}),
                            **({"text": e["text"], "questName": e["text"]} if e.get("text") else {})}
    return steps


_walk_cache = {}

WALK_KEPT = 1024


def nearest_by_walk(hub, frm, places, seconds=None):
    on = [p for p in places if p[1][0] == frm[0]]
    if not on:
        return None
    key = (getattr(hub, "data_version", 0), frm[0], round(frm[1]), round(frm[2]),
           tuple((p[0], round(p[1][1]), round(p[1][2])) for p in on))
    kept = _walk_cache.get(key, UNKEPT)
    if kept is not UNKEPT:
        return kept
    crow = lambda p: math.hypot(p[1][1] - frm[1], p[1][2] - frm[2])
    try:
        got = (seconds or walking_seconds(hub, "any"))(frm[0], frm[1:3], [p[1][1:4] if p[1][3] is not None else p[1][1:3]
                                                                         for p in on])
    except Exception:
        got = None
    if not isinstance(got, (list, tuple)) or len(got) != len(on):
        return min(on, key=crow)
    secs = [g.get("seconds") if isinstance(g, dict) else None for g in got]
    walk = lambda i: (secs[i] is None, secs[i] or 0.0, crow(on[i]))
    return keep(_walk_cache, key, on[min(range(len(on)), key=walk)], WALK_KEPT)


def errand_also(hub, steps):
    todo = [st for st in steps if st.get("kind") == "errand" and st.get("what") in ANY_NPC]
    for st in todo:
        st.pop("also", None)
    if not todo or not getattr(hub, "routes", None):
        return steps
    errands, me = errands_of(hub), errand_state(hub)
    strs = (hub.status or {}).get("strs") or {}
    side = strs.get("faction") or None
    race, spells, _ = travel_means(hub, side)
    binds = [strs.get("bind")] + [(st.get("need") or {}).get("bind") for st in steps if st.get("what") == "bind"]
    nodes = [(st.get("need") or {}).get("node") for st in steps if st.get("what") == "flightpath"]
    lands = hub.routes.landings(side, hub.characters.known_taxi(), [b for b in binds if b],
                                [n for n in nodes if n is not None], race, spells)
    seconds = walking_seconds(hub, "any")
    for st in todo:
        places, also = errands.serving_step(st, me) or (), []
        for land in lands:
            near = [p for p in places if p[1][0] == land[0] and math.hypot(p[1][1] - land[1], p[1][2] - land[2]) <= LAND_REACH]
            best = near and nearest_by_walk(hub, land, near, seconds)
            if not best:
                continue
            m = errands.moved_to(st, best, me)
            zone = (mapzones.MAPS.get(str(m["map"])) or {}).get("name") if m.get("map") else None
            also.append({"l": [land[0], round(land[1], 1), round(land[2], 1)], "npc": m["npc"], "inst": m["inst"],
                         "at": m["at"], **{k: v for k, v in (("map", m.get("map")), ("zone", zone), ("cost", m.get("cost")),
                                                             ("text", m.get("text"))) if v}})
        if also:
            st["also"] = also
    return steps


SKILL_LINES = {"Alchemy": 171, "Blacksmithing": 164, "Enchanting": 333, "Engineering": 202, "Herbalism": 182,
               "Leatherworking": 165, "Mining": 186, "Skinning": 393, "Tailoring": 197, "Cooking": 185, "First Aid": 129,
               "Fishing": 356}


def me_record(hub):
    return hub.characters.playing() or {}


def class_pick(hub, chain, anchor=None):
    me = class_me(hub)
    return classtrip.pick(chain, classtrip.openings(chain, me["classId"], me["side"], me["race"], me["done"],
                                                    hub.characters.max_level(), me["log"]), me["log"],
                          class_near(hub, tuple(anchor[:3]) if anchor else here_now(hub)), me["done"])


def epic_label(hub, key):
    kind, _, rest = key.partition(":")
    if not rest:
        d = hub.dungeons.by_key.get(key)
        return d and d["name"]
    if kind == "zone":
        z = questplan.book().zones.get(int(rest)) if rest.isdigit() else None
        return z and z["name"]
    if key == camping.KEY:
        return camping.NAME
    if kind == "class":
        chain = classtrip.by_id(int(rest)) if rest.isdigit() else None
        got = chain and class_pick(hub, chain)
        return chain and classtrip.title(chain, got[0] if got else classtrip.opening_of(chain, class_me(hub)["done"]))
    if prof_line(key) is not None:
        name = prof_data().cd.names.get(prof_line(key))
        return name and f"{name} epic"
    if kind in (ITEM_EPIC, CRAFT_EPIC):
        return item_name(int(rest)) if rest.isdigit() else None
    return "Your quests" if kind == "log" else None


ITEM_EPIC = "item"

CRAFT_EPIC = "craft"


def craft_item(key):
    kind, _, rest = key.partition(":")
    return int(rest) if kind == CRAFT_EPIC and rest.isdigit() else None


def craft_kept(hub, key):
    epic = ((hub.shared.data or {}).get("epic") or {}) if getattr(hub, "shared", None) else {}
    return epic if epic.get("key") == key else {}


def craft_tree(hub, key, anchor, picks=None, running=False):
    import itemsources
    item, level = craft_item(key), level_of(hub, key)
    if item is None and level is None:
        return None
    table = craft_kept(hub, key)
    kept = table.get("craft") or {}
    picks = kept.get("picks") if picks is None else picks
    carry = hub.characters.bags_now() or {}
    start = table.get("anchor") or anchor
    here = tuple(start[:3]) if start else here_now(hub)
    pd = prof_data()
    src = crafting.Sources(itemsources.lookup(hub), pd, known=spells_of(me_record(hub)) or (), here=here,
                           quest_seconds=lambda i, q: quest_seconds(hub, i, here), talk=STEP_TALK)
    if level:
        line, to, way = level
        up = crafting.levelling(pd, src, prof_state(hub), line, to, way, picks)
        made = crafting.materials(up["goals"], carry, src, picks, way)
        return {**made, "walls": up["walls"], "route": up["route"], "line": line, "to": to, "way": way}
    have = carry.get(item, 0)
    total = kept["total"] if kept.get("total") and (running or kept["total"] > have) else have + 1
    up = crafting.craft_goals(pd, src, prof_state(hub), item, total, carry, picks)
    made = crafting.materials(up["goals"], carry, src, picks)
    return {**made, "walls": up["walls"], "route": up["route"], "item": item, "total": total}


def quested_for(made):
    return sorted({r["ways"]["quest"]["id"] for r in made["rows"] if r["short"] and r["pick"] == "quest"})


def quest_seconds(hub, item, at):
    with planreport.quiet():
        sub = quest_epic(hub, f"{ITEM_EPIC}:{item}", at)
    steps = (sub or {}).get("steps") or []
    return float(sum(s["sec"] for s in step_costs(hub, steps, at))) if steps else None


def craft_picks(made):
    return {str(r["item"]): r["pick"] for r in made["rows"] if r["short"] and r["pick"] and r["kind"] != "goal"}


def material_rows(made):
    import market
    table = item_table()
    out, rows, merged = [], made["rows"], {}
    for r in rows:
        if r["kind"] == "goal" or not r["short"]:
            continue
        crafts, p = [], r["parent"]
        while p is not None and rows[p]["kind"] != "goal":
            crafts.append(rows[p]["item"])
            p = rows[p]["parent"]
        same = (r["item"], r["kind"], tuple(crafts))
        if same in merged:
            got = out[merged[same]]
            for k in ("need", "have", "short", "cost"):
                got[k] += r[k]
            continue
        merged[same] = len(out)
        ways, row = r.get("ways") or {}, table.get(str(r["item"])) or ()
        icon = row[2] if len(row) > 2 and row[2] else None
        spot = ways.get(r["pick"]) if r["pick"] in ("grind", "gather") else None
        vendor, quest = (ways.get("vendor") or {}).get("name"), (ways.get("quest") or {}).get("name")
        out.append({"item": r["item"], "name": r["name"], "q": row[1] if len(row) > 1 else 1,
                    "icon": icon or "inv_misc_questionmark", "iconStored": bool(icon) and market.icon_stored(icon),
                    "kind": r["kind"], "depth": r["depth"], "need": r["need"], "have": r["have"], "short": r["short"],
                    "pick": r["pick"], "cost": r["cost"], "vendor": vendor, "quest": quest,
                    "zone": (mapzones.MAPS.get(str(spot.get("map"))) or {}).get("name") if spot else None,
                    "keys": {"grind": "grind" if ways.get("grind") else "gather" if ways.get("gather") else None, "quest": quest,
                             "craft": True if ways.get("craft") else None, "buy": vendor,
                             "auction": True if ways.get("auction") else None}})
    return out


def craft_chores(hub, key, epic, at, errand):
    made, item = epic.get("craft"), craft_item(key)
    if not made or item is None and prof_line(key) is None:
        return []
    pd, me = prof_data(), prof_state(hub, errand.get("game"), money=errand.get("money"))
    chores = profepics.Chores(pd, me, errands_of(hub), at, own=True)
    own, label = ((key, made["rows"][made["goals"][-1]]["name"]) if item is not None
                  else (profepics.epic_key(made["line"]), pd.cd.names.get(made["line"], "")))
    epic["steps"] = crafting.chores(epic["steps"], made, chores, pd, me, own, label)
    return chores.notes


def item_quest(hub, rest):
    import itemsources
    got = itemsources.lookup(hub).quests(int(rest)) if rest.isdigit() else []
    return got[0]["id"] if got else None


def flight_model(hub):
    side = ((hub.status or {}).get("strs") or {}).get("faction", "")
    flights = hub.routes.data.get("flights") or {}
    known = hub.routes.known_flights(hub.characters.known_taxi(), side)
    return questplan.flight_travel([n for n in flights.get("nodes", ()) if n.get("side") in (None, side)],
                                   flights.get("hops", ()), known, hub.characters.travel_speed() or questplan.RUN,
                                   hub.routes.fly)


def quest_epic(hub, key, anchor, parked=(), close=False, offered=(), at_level=None, quests=None, kept=None):
    b = questplan.book()
    kind, _, rest = key.partition(":")
    d = None if ":" in key else hub.dungeons.by_key.get(key)
    chain, made = None, None
    if d:
        wanted, name, follow, band = [], None, False, None
    elif kind == "zone":
        z = b.zones.get(int(rest)) if rest.isdigit() else None
        if not z:
            return None
        wanted, name, follow, band = z["quests"], f"{z['name']} quest epic", False, hub.zone_levels.get(rest)
    elif kind == "log":
        wanted = [int(x) for x in rest.split(".") if x.isdigit()]
        if not wanted:
            return None
        name, follow, band = "Quest log epic", False, None
    elif kind == "class":
        chain = classtrip.by_id(int(rest)) if rest.isdigit() else None
        if not chain:
            return None
        if quests is None:
            got = class_pick(hub, chain, anchor)
            opening, quests = got if got else (None, [])
        else:
            opening = classtrip.opening_of(chain, quests)
        wanted, name, follow, band = list(quests), f"{classtrip.title(chain, opening)} class quest epic", False, None
        if not wanted:
            return None
    elif key == camping.KEY:
        wanted, name, follow, band = [], camping.NAME, False, None
    elif kind == ITEM_EPIC:
        qid, label = item_quest(hub, rest), epic_label(hub, key)
        if qid is None or not label:
            return None
        wanted, name, follow, band = [qid], f"{label} quest epic", False, None
    elif kind == CRAFT_EPIC:
        made, label = craft_tree(hub, key, anchor, running=kept is not None), epic_label(hub, key)
        if not made or not label or made["rows"][made["goals"][-1]]["pick"] != "craft":
            return None
        wanted = quested_for(made)
        name, follow, band = crafting.epic_name(label), False, None
    elif prof_line(key) is not None:
        name = epic_label(hub, key)
        if not name:
            return None
        made = craft_tree(hub, key, anchor, running=kept is not None)
        wanted, follow, band = quested_for(made) if made else [], False, None
    else:
        return None
    planreport.report("log", planreport.log_finds(log_entries(hub)))
    s, st = hub.state or {}, hub.status or {}
    done, log = quest_state(hub)
    me = me_record(hub)
    skills, spells = skills_of(me), spells_of(me)
    objectives = log_objectives(hub)
    bags = bag_items(me)
    by_area = {d.get("area"): d for d in hub.dungeons.list if d.get("area")}
    portals = {}
    for p in hub.routes.portals():
        portals.setdefault(p["dungeon"], p)

    def dungeon_of(q):
        d = by_area.get(q.get("zone"))
        if not d:
            return None
        portal = portals.get(d["name"])
        return d["key"], d["name"], ((portal["inst"], *portal["walk"]) if portal else None)

    mob_level = mob_levels(hub)
    cap = hub.characters.max_level()

    def measured(level, mob):
        return kill_xp(level, mob, cap) * hub.world.xp.share(level, mob)

    def to_world(map_id, x, y):
        return world_pos(map_id, x / 100, y / 100)
    side = (st.get("strs") or {}).get("faction", "")
    travel = flight_model(hub)
    race = races.bit_of(me.get("race"), side)
    area = None
    if kind == "camp":
        area = camping.area(b.for_side(side, st.get("classId")), side, race, st.get("classId"), done, log,
                            anchor or here_now(hub), to_world)
        wanted = area["quests"] if area else []
    parts = {}
    if d:
        portal = portals.get(d["name"])
        parts = questplan.dungeon_parts(d, b, (portal["inst"], *portal["walk"]) if portal else None, to_world, dungeon_of)
        wanted, name, band, dungeon_of = (parts.pop(k) for k in ("wanted", "name", "band", "dungeon_of"))
    level_now, xp_now = s.get("level") or 1, s.get("xp") or 0
    if at_level and at_level > level_now:
        level_now, xp_now = at_level, 0
    plan = questplan.QuestPlan(key, name, wanted, b, to_world, level_now, xp_now,
                               side, race, st.get("classId"), skills, done, log, anchor, parked, faces=hub.dungeons,
                               follow=follow, kill_xp=measured, mob_level=mob_level, bags=bags, dungeon_of=dungeon_of,
                               band=band, travel=travel, ways=plan_ways(hub), seconds=run_seconds(hub),
                               close=close, objectives=objectives, levels=log_levels(hub),
                               pois=hub.questpois.world(lambda m, x, y: world_pos(m, x / 100, y / 100)),
                               spawns_of=spawn_finder(hub, side), danger_of=camp_danger(hub, side), counts=hub.questpois.counts(),
                               rested=s.get("rested") or 0, inside={d.get("instance") for d in hub.dungeons.list},
                               cap=cap, offered=offered, with_gets=questitems.adder(glow_index(hub), bags, side, hub.world.mobs),
                               found_in=found_inside(hub), spells=spells, kept=kept or (),
                               heights_of=lambda inst, spots, mobs: camp_heights(hub, inst, spots, mobs),
                               log_most=(st.get("nums") or {}).get("questsMax"),
                               closed={k: (hub.dungeons.by_key.get(k) or {}).get("name") or k
                                       for k, s in hub.dungeons.open_now().items() if not s.get("open")},
                               **parts).build()
    if plan and kind == ITEM_EPIC:
        for step in plan["steps"]:
            if step.get("kind") == "turnin" and step.get("quest") == wanted[0]:
                step["want"] = int(rest)
    if plan and made:
        wants = {r["ways"]["quest"]["id"]: r["item"] for r in made["rows"] if r["short"] and r["pick"] == "quest"}
        for step in plan["steps"]:
            if step.get("kind") == "turnin" and step.get("quest") in wants:
                step["want"] = wants[step["quest"]]
        plan["craft"], plan["materials"] = made, material_rows(made)
        if "route" in made:
            plan["route"] = made["route"]
    if plan and kind == "class":
        for step in plan["steps"]:
            if step.get("quest") is not None:
                step["cq"] = chain["id"]
    if plan and kind == "log":
        plan["next"] = questplan.next_in_chains(b, wanted, done, log, {st_["quest"] for st_ in plan["steps"] if st_.get("quest")},
                                                side, race, st.get("classId"), skills, cap, spells) or None
    if plan and kind == "camp":
        plan["camp"] = area and {"zone": area["zone"], "camper": area["camper"], "at": list(area["at"]),
                              "enders": area["enders"]}
    return plan


def camp_opens():
    return camping.opens(questplan.book())


def quest_zones(hub):
    b = questplan.book()
    st = hub.status or {}
    me = me_record(hub)
    side, cls = (st.get("strs") or {}).get("faction", ""), st.get("classId")
    race = races.bit_of(me.get("race"), side)
    done, log = quest_state(hub)
    cap, spells = hub.characters.max_level(), spells_of(me)
    out = []
    for mid, z in sorted(b.zones.items()):
        band = hub.zone_levels.get(str(mid))
        mine = [i for i in z["quests"] if not questplan.open_to(b.quests[i], side, race, cls, in_log=i in log, cap=cap,
                                                                spells=None if i in done else spells)
                and (i in log or questplan.in_band(b.quests[i], band))]
        if mine:
            out.append({"id": mid, "name": z["name"], "quests": len(mine), "done": sum(1 for i in mine if i in done),
                        "missing": sum(1 for i in mine if if_offered(b.quests[i]) and i not in done)})
    return out


QMOBS_MOST = 12


def quest_mobs(hub, d, quest_ids):
    out = []
    for q in d.get("quests", []):
        if q["id"] not in quest_ids:
            continue
        names = []
        for t in q.get("targets", []):
            for m in t.get("mobs") or []:
                rec = hub.world.mobs.get(str(m))
                if rec and rec[0] not in names:
                    names.append(rec[0])
        if names:
            out.append({"q": q["id"], "m": names[:QMOBS_MOST]})
    return out


BOSS_TARGET_MOBS = 3


BOSS_TITLES = {"Lord", "Lady", "Archmage", "Captain", "Baron", "Baroness", "Commander", "Mr.", "Twilight", "Wolf", "Master",
               "High", "Grand", "Inquisitor", "Houndmaster", "Arcanist", "Bloodmage", "Overlord", "General", "Prince",
               "Princess", "King", "Queen", "Magister", "Chief", "Warlord", "Emperor", "Doctor", "Priestess", "Hydromancer",
               "Ambassador", "Instructor", "Lorekeeper", "Scarlet", "Chieftain", "Elder"}


def named_in(text, name):
    words = name.split()
    k = 0
    while k < len(words) - 1 and words[k] in BOSS_TITLES:
        k += 1
    return any(len(n) >= 4 and re.search(rf"\b{re.escape(n)}\b", text or "") for n in {name, " ".join(words[k:])})


def boss_track(d, quest_ids, faces=None):
    inside = [q for q in d.get("quests", []) if q["id"] in quest_ids]
    out = []
    for b in d.get("bosses", []):
        serves = list(dict.fromkeys(
            q["name"] for q in inside
            if b.get("npc") in {m for t in q.get("targets", []) if len(t.get("mobs") or []) <= BOSS_TARGET_MOBS for m in (t.get("mobs") or [])}
            or named_in(q.get("objective"), b["name"])))
        if serves or not b.get("rare"):
            face = b.get("display") or (faces.face(npc=b["npc"]) if faces and b.get("npc") else None)
            out.append({"n": b["name"], **({"q": serves} if serves else {}), **({"f": face} if face else {})})
    return out


def here_now(hub):
    s = hub.state or {}
    pos = s.get("pos")
    return world_pos(s["map"], pos["x"], pos["y"]) if pos and s.get("map") else None


def start_fresh(hub, key, anchor, mode, close=False, parked=(), asked=None):
    epic = build_epic(hub, key, anchor, parked=parked, close=close)
    if epic is None or epic.get("waiting"):
        return epic and False
    meta = {"name": epic_label(hub, key), "char": playing_char(hub),
            "close": bool(close) or None,
            "anchor": list(anchor) if anchor else None, "mode": mode,
            "fresh": True, "start": True,
            "parked": sorted(parked) or None,
            "maybe": epic.get("maybe"),
            "next": epic.get("next"),
            "asked": asked,
            "craft": {**({"total": epic["craft"]["total"]} if epic["craft"].get("total") else {}),
                      "picks": craft_picks(epic["craft"])} if epic.get("craft") else None,
            "aside": aside_of(hub, key),
            **plan_notes(epic)}
    return hub.shared.start_epic(key, epic["steps"], shared_way_finder(hub, mode), meta, shared_route_finder(hub, mode))


def aside_of(hub, key):
    if craft_item(key) is None:
        return None
    held = (((getattr(hub, "shared", None) and hub.shared.data) or {}).get("epic") or {}).get("key")
    if not held or craft_item(held) is not None:
        return "keep"
    return {"parked": sorted(int(q) for q in ((hub.extra or {}).get("epic") or {}).get("parked") or ())}


def replan_asked(hub, asked):
    sh = hub.shared
    if not sh:
        return None
    epic = (sh.data or {}).get("epic") or {}
    mode, close, here = epic.get("mode") or "any", bool(epic.get("close")), here_now(hub)
    if asked.get("mode") == "class" and asked.get("quests"):
        chain = classtrip.by_id(int(asked["quests"][0]))
        return start_fresh(hub, f"{classtrip.KEY}{chain['id']}", here, mode, close, asked="game") if chain else None
    if asked.get("mode") == "zone" and asked.get("quests"):
        key = "log:" + ".".join(str(q) for q in sorted(set(asked["quests"])))
        return start_fresh(hub, key, here, mode, close, asked="game")
    if asked.get("mode") == "here" and epic.get("key"):
        parked = {int(q) for q in ((hub.extra or {}).get("epic") or {}).get("parked") or ()}
        return start_fresh(hub, epic["key"], here, mode, close, parked, asked="game")
    return None


def epic_stop_or_start(hub, report):
    sh = hub.shared
    if not sh:
        return
    data, v = sh.data or {}, report.get("version")
    epic = ((data if v == data.get("version") else sh.history.get(v)) or {}).get("epic")
    if data.get("epic") and epic and (report.get("stopped") or report.get("running")):
        sh.game_guide(epic["key"], bool(report.get("running")))


def wearer(hub, tips=None):
    tips = tips or ITEM_TIPS
    st, weights = hub.status or {}, stat_weights()
    nums, cls = st.get("nums") or {}, st.get("classId")
    worn_now = (hub.extra or {}).get("equipped") or {}
    equipped = worn_now.get("items")
    keyed = worn_now.get("keys") or equipped
    facts = {i: tips.stats(i) for i in keyed or () if i}
    role = next((m.get("role") for m in ((hub.extra or {}).get("group") or {}).get("members") or () if m.get("me")), None)
    w = upgrades.spec_info(weights, cls, nums, role)["w"]
    worn_ids = {k: (equipped[k - 1] if k <= len(equipped) else 0) or 0 for k in range(1, 19)} if equipped is not None else {}
    worn_keys = {k: (keyed[k - 1] if k <= len(keyed) else 0) or 0 for k in range(1, 19)} if equipped is not None else {}
    worn = {k: (facts.get(i) or upgrades.UNKNOWN) if i else None for k, i in worn_keys.items()} if equipped is not None else None
    gear = list(((hub.extra or {}).get("run") or {}).get("gear") or ())
    return {"cls": cls, "level": (hub.state or {}).get("level") or 1, "nums": nums, "w": w, "weights": weights,
            "worn": worn, "gear": gear}, worn_ids


def reward_finder(hub, tips=None):
    tips = tips or ITEM_TIPS

    def choices_of(qid):
        q = questplan.book().quests.get(qid) or next((x for d in hub.dungeons.list for x in d.get("quests", ()) if x.get("id") == qid), {})
        return list((q.get("rewards") or {}).get("choice") or ())

    def rewards(steps, apart=False):
        wanted = {q: choices_of(q) for q in {s.get("quest") for s in steps if s.get("kind") == "turnin"} - {None}}
        base, worn_ids = wearer(hub, tips)
        worn, gear = base["worn"], base["gear"]
        facts = {i: tips.stats(i) for i in {i for got in wanted.values() if len(got) > 1 for i in got}}
        out = []
        for s in steps:
            choice = wanted.get(s.get("quest")) if s.get("kind") == "turnin" else None
            if not choice or len(choice) < 2:
                out.append(None)
                continue
            me = {**base, "level": s.get("lv") or base["level"]}
            picked, wear = upgrades.reward_picks([(i, facts.get(i)) for i in choice], me, worn_ids, want=s.get("want"))
            out.append(picked)
            if wear and wear[2] and worn is not None and not apart:
                iid, it, slot = wear
                worn[slot], worn_ids[slot] = it, iid
                if it.get("inv") == 17:
                    worn[17], worn_ids[17] = None, 0
                if len(gear) >= slot:
                    gear[slot - 1] = it.get("il") or 0
        return out
    return rewards


ENDERS_MOST = 4


def ends_finder(hub, book=None):
    def quest_of(qid):
        b = book if book is not None else questplan.book().quests
        return b.get(qid) or next((x for d in hub.dungeons.list for x in d.get("quests", ()) if x.get("id") == qid), {})

    def ends(steps):
        _, log = quest_state(hub)
        held = {q for s in steps if s.get("kind") == "turnin" for q in plansteps.step_ids(s)}
        out = []
        for qid in sorted(set(log) - held):
            n = 0
            for g in quest_of(qid).get("end") or ():
                at = g.get("map") is not None and world_pos(g["map"], g["x"] / 100, g["y"] / 100)
                if not at or n >= ENDERS_MOST:
                    continue
                spot = [round(float(at[1]), 1), round(float(at[2]), 1)] + ([round(float(g["z"]), 1)] if g.get("z") is not None else [])
                out.append({"q": qid, "i": at[0], "at": spot, **({"npc": g["name"]} if g.get("name") else {})})
                n += 1
        return out
    return ends


def reward_quests(hub):
    b = questplan.book()
    done, log = quest_state(hub)
    st, s = hub.status or {}, hub.state or {}
    out = set(log)
    here, level = s.get("map"), s.get("level") or 1
    if not here:
        return sorted(out)
    side, cls = (st.get("strs") or {}).get("faction", ""), st.get("classId")
    me = me_record(hub)
    race, spells = races.bit_of(me.get("race"), side), spells_of(me)
    cap = hub.characters.max_level()
    for qid, q in b.quests.items():
        if (len((q.get("rewards") or {}).get("choice") or ()) < 2 or qid in done or qid in log
                or (q.get("req") or 1) > level or not any(g.get("map") == here for g in q.get("start") or ())):
            continue
        if any(p not in done for p in q.get("preAll") or ()) or (q.get("preAny") and not any(p in done for p in q["preAny"])) \
                or closed_by(q, done, log) is not None:
            continue
        if not questplan.open_to(q, side, race, cls, in_log=False, cap=cap, spells=spells):
            out.add(qid)
    return sorted(out)


def quest_picks(hub, ids, tips=None):
    ids = list(ids)
    got = reward_finder(hub, tips)([{"kind": "turnin", "quest": i} for i in ids], apart=True)
    return {i: rw for i, rw in zip(ids, got) if rw and rw.get("known")}


class QuestPicks:
    def __init__(self, hub, tips=None):
        self.hub, self.tips = hub, tips

    def wanted(self):
        me = playing_char(self.hub)
        if not me:
            return None
        st = self.hub.status or {}
        profs = tuple(sorted((p.get("name"), p.get("rank")) for p in (me_record(self.hub).get("professions") or ())))
        return (json.dumps(me, sort_keys=True), (self.hub.state or {}).get("level"), st.get("classId"),
                tuple(reward_quests(self.hub)), worn_text(self.hub) is not None, profs)

    def table(self, wanted):
        return {"char": json.loads(wanted[0]), "quests": quest_picks(self.hub, wanted[3], self.tips),
                "recipes": recipe_marks(self.hub, self.tips)}


def recipe_marks(hub, tips=None):
    import recipeups
    me, _ = wearer(hub, tips)
    if me["worn"] is None:
        return {}
    profs = profepics.state_of(me_record(hub), None, None)["profs"]
    return recipeups.marks(prof_data(), me, profs, tips or ITEM_TIPS)


def worn_text(hub):
    worn = (hub.extra or {}).get("equipped") or {}
    if worn.get("items") is None:
        return None
    return json.dumps([worn.get("items"), worn.get("keys")])


def epic_context(hub):
    s, st = hub.state or {}, hub.status or {}
    done, log = quest_state(hub)
    flags, nums = s.get("flags") or {}, st.get("nums") or {}
    fill = getattr(hub, "navfill", None)
    facts = ticks.game_facts(hub)
    return {"me": playing_char(hub), "here": here_now(hub), "inside": bool(flags.get("instance")),
            "flying": bool(flags.get("taxi")), "dead": bool(flags.get("dead") or flags.get("ghost")),
            "live": hub.extra.get("epic"), "loaded": nums.get("sharedVersion"), "done": done, "log": log,
            "clocks": [e["id"] for e in log_entries(hub) if e.get("id") is not None and e.get("ends")],
            "inputs": epic_inputs(hub, done, log), "facts": facts,
            "errand": {**errand_state(hub), "game": facts},
            "who": who_now(hub),
            "worn": worn_text(hub),
            "built": fill.state().get("counts") if fill else None}


def epic_inputs(hub, done, log):
    chores = {k: v for k, v in errand_state(hub).items() if k != "schedule"}
    me = hub.characters.playing() or {}
    items = (me.get("bags") or {}).get("items") or {}
    ql = (hub.extra or {}).get("questlog") or {}
    facts = [getattr(hub, "data_version", 0), chores, sorted(done), sorted(log.items()), ql.get("char"), ql.get("entries"),
             sorted(str(i[0] if isinstance(i, (list, tuple)) else i) for i in items),
             [(p.get("name"), p.get("rank")) for p in me.get("professions") or ()], me.get("race"),
             hub.characters.travel_speed(), len(getattr(hub, "zone_levels", None) or {}), game_unknown(hub), objectives_unknown(hub),
             getattr(getattr(hub, "offers", None), "version", 0),
             prof_inputs(hub),
             ticks.inputs(hub, named=ticks.named_items(((getattr(getattr(hub, "shared", None), "data", None) or {}).get("epic")
                                                        or {}).get("steps"))),
             camp_skipped(hub) is not None]
    return json.dumps(facts, sort_keys=True, default=lambda o: sorted(map(repr, o)) if isinstance(o, (set, frozenset)) else repr(o))


def playing_char(hub):
    me = me_record(hub)
    return char_entry(me) if me else None


def playing_now(hub):
    me = None if hub.strip_lost(hub.link) else hub.characters.confirmed()
    return char_entry(me) if me else None


WEIGH_CLOSE = 1.4


WEIGH_MOST = 4

WEIGH_SECONDS = 8.0

WEIGH_BACKGROUND = math.inf

LATE = "late"

OVER_WORTH = 20.0

SHORT_WAY = 300.0

DETOUR_MOST = 0.3

DANGER_STEP = 3.0


DANGER_EDGE = 80.0

DANGER_LEVELS = 12.0


def through_is_better(straight, round_len, through_len):
    return straight < SHORT_WAY and round_len > through_len * (1 + DETOUR_MOST)


def round_or_through(hub, inst, start, goal, start_z, goal_z, indoors, ghost, avoid, level, mode, side=None):
    body = hub.paths.find(inst, start, goal, start_z, goal_z, indoors, ghost, avoid, level=level, side=side)
    if mode == "safe":
        return safest_or_plain(hub, inst, start, goal, start_z, goal_z, indoors, ghost, avoid, level, body, side)
    straight = math.hypot(goal[0] - start[0], goal[1] - start[1])
    if (mode not in ("round", "gather") or not body or body.get("partial") or avoid is None
            or not through_is_better(straight, body.get("length") or 0, straight)):
        return body
    through = hub.paths.find(inst, start, goal, start_z, goal_z, indoors, ghost, None, level=level, side=side)
    if through and not through.get("partial") and through_is_better(straight, body["length"], through["length"]):
        return {**through, "through": True}
    return body


def safest_or_plain(hub, inst, start, goal, start_z, goal_z, indoors, ghost, avoid, level, body, side=None):
    if not body or not body.get("points") or avoid is None or not len(avoid[1]):
        return body
    red = red_yards(body["points"], avoid[1])
    if red <= 0:
        return body
    plain = hub.paths.find(inst, start, goal, start_z, goal_z, indoors, ghost, (("round",) + tuple(avoid[0][1:]), avoid[1]),
                           level=level, side=side)
    if plain and plain.get("points") and (not plain.get("partial") or body.get("partial")) \
            and red_yards(plain["points"], avoid[1]) < red:
        return plain
    return body


def red_yards(points, threats):
    return sum(math.dist(a[:2], b[:2]) for run in danger_stretches(points, threats) for a, b in zip(run, run[1:]))


UNDER_GROUND = 3.0


def covered_points(hub, inst, points):
    return covered_split(hub, inst, points)[0]


def indoor_points(hub, inst, points):
    return covered_split(hub, inst, points, rooms=True)[1]


def covered_split(hub, inst, points, rooms=False):
    t = getattr(getattr(hub, "paths", None), "terrain", None)
    pts = [p for p in points or () if len(p) > 2 and p[2] is not None]
    if not pts or t is None:
        return [], []
    try:
        if t.is_dungeon(inst):
            return [], []
        r0, c0 = nav.cell_of(max(p[0] for p in pts) + 2, max(p[1] for p in pts) + 2)
        r1, c1 = nav.cell_of(min(p[0] for p in pts) - 2, min(p[1] for p in pts) - 2)
        with nav.wm.background():
            region = t.region(inst, r0, c0, r1 + 1, c1 + 1)
        ground = region["ground"]
    except (OSError, ValueError, KeyError, game.GameNotFound):
        return [], []
    areas, city = region.get("area"), getattr(hub, "city_areas", None)
    out, indoor = [], []
    for k, p in enumerate(points):
        if len(p) < 3 or p[2] is None:
            continue
        r, c = nav.cell_of(p[0], p[1])
        inside_region = 0 <= r - r0 < ground.shape[0] and 0 <= c - c0 < ground.shape[1]
        area = int(areas[r - r0, c - c0]) if inside_region and areas is not None else 0
        if city is not None and area < len(city) and city[area]:
            continue
        g = ground[r - r0, c - c0] if inside_region else np.nan
        under = not np.isnan(g) and p[2] < float(g) - UNDER_GROUND
        try:
            inside = (rooms or not under) and hub.indoors.indoor_at(inst, p[0], p[1], p[2])
        except (OSError, ValueError, KeyError, AttributeError, game.GameNotFound):
            inside = False
        if under or inside:
            out.append(k)
        if inside and rooms:
            indoor.append(k)
    return out, indoor


def danger_stretches(points, threats, step=DANGER_STEP):
    if not points or threats is None or not len(threats):
        return []
    t = np.asarray(threats, dtype=float)
    t = t[t[:, 3] > 0]
    pts = np.asarray([(p[0], p[1], p[2] if len(p) > 2 and p[2] is not None else np.nan) for p in points], dtype=float)
    looks = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(np.hypot(*(b[:2] - a[:2])) // step))
        looks += [a + (b - a) * k / n for k in range(1, n + 1)]
    s = np.asarray(looks)
    lo, hi = s[:, :2].min(0) - DANGER_EDGE, s[:, :2].max(0) + DANGER_EDGE
    t = t[(t[:, 0] >= lo[0]) & (t[:, 0] <= hi[0]) & (t[:, 1] >= lo[1]) & (t[:, 1] <= hi[1])]
    if not len(t):
        return []
    hit = nav.reach_hits(s, t, DANGER_LEVELS)[0]
    out, run = [], []
    for p, h in zip(s, hit):
        if h:
            run.append([round(float(p[0]), 1), round(float(p[1]), 1)])
        elif run:
            if len(run) > 1:
                out.append(run)
            run = []
    if len(run) > 1:
        out.append(run)
    return out


def walk_yards(hub, inst, a, b, level=None, faction="", ghost=False):
    avoid = way_avoid(hub, inst, "round", level, faction) if level else None
    r = hub.paths.find(inst, tuple(a[:2]), tuple(b[:2]), start_z=a[2] if len(a) > 2 else None,
                       goal_z=b[2] if len(b) > 2 else None, ghost=ghost, avoid=avoid, level=level, side=faction or None)
    if not r:
        return None
    planreport.report(walked=((inst, a, b), r.get("points") or ()))
    yards = r["length"] + ((r.get("gap") or 0.0) if r["partial"] else 0.0)
    return yards, yards + ((r.get("over") or 0) + (r.get("enemy") or 0)) * (OVER_WORTH - 1), bool(r["partial"])


def route_words(plan):
    rides = [leg["name"] for leg in plan["legs"] if leg["kind"] != "walk"]
    return ", then ".join(rides) if rides else "Walking all the way"


FLIGHT_MASTER_NEAR = 60.0


def flight_masters(hub, side):
    world = getattr(hub, "world", None)
    if world is None or not hasattr(world, "services"):
        return []
    return errands_of(hub).places({"flight"}, side or "", ids=True)


def name_flight_masters(hub, legs, start, side):
    out, masters = [], None
    for k, leg in enumerate(legs):
        leg = dict(leg)
        if leg.get("vehicle") == "flight":
            if masters is None:
                masters = flight_masters(hub, side)
            prev = legs[k - 1] if k else None
            inst, spot = (prev.get("map"), prev.get("to") or prev.get("at")) if prev else (start[0], start[1:3])
            near = [(math.hypot(p[1] - spot[0], p[2] - spot[1]), n, rest[1] if len(rest) > 1 else None)
                    for n, p, *rest in masters if spot and p[0] == inst]
            yards, who, npc_id = min(near, key=lambda m: m[0], default=(None, None, None))
            if who and yards <= FLIGHT_MASTER_NEAR:
                leg.update({"npc": who, **({"npcId": npc_id} if npc_id else {})})
        out.append(leg)
    return out


WEIGH_WORKERS = 6

WEIGH_WORKERS_BEHIND = 2

_weigh_lock = threading.RLock()

_weigh_pools = {}

_weighing = {}


def weigh_pool(behind):
    with _weigh_lock:
        if behind not in _weigh_pools:
            _weigh_pools[behind] = ThreadPoolExecutor(WEIGH_WORKERS_BEHIND if behind else WEIGH_WORKERS,
                                                      thread_name_prefix="weighing behind" if behind else "weighing")
        return _weigh_pools[behind]


def _weighed(key, done):
    with _weigh_lock:
        if (_weighing.get(key) or [None])[0] is done:
            del _weighing[key]


def weigh_walks(hub, walks, level, side, patience, ghost=False):
    behind = nav.wm.in_background()
    pool, deadline, mine = weigh_pool(behind), time.time() + patience, []
    switches = tuple(sorted(carried.values().items()))
    with _weigh_lock:
        for w in walks:
            key = (id(hub), w, level, side, ghost, switches)
            entry = _weighing.get(key)
            if entry is None:
                work = pool.submit(walk_yards, hub, *w, level=level, faction=side, ghost=ghost)
                entry = _weighing[key] = [work, 0]
                work.add_done_callback(lambda done, key=key: _weighed(key, done))
            entry[1] += 1
            mine.append((w, key, entry))
    out = {}
    for w, key, (work, _) in mine:
        try:
            out[w] = work.result(timeout=None if math.isinf(patience) else max(0.0, deadline - time.time()))
        except (FutureTimeout, CancelledError):
            out[w] = LATE
        except nav.NotBuilt as e:
            nav.wm.note_unbuilt(e.what)
            out[w] = LATE
        except (OSError, game.GameNotFound):
            out[w] = None
        except Exception:
            log_error("weighing a route's walk")
            out[w] = None
    with _weigh_lock:
        for w, key, entry in mine:
            entry[1] -= 1
            if entry[1] <= 0 and entry[0].cancel():
                _weighing.pop(key, None)
    return out


def travel_means(hub, side):
    chars = hub.characters
    me = (chars.playing() if hasattr(chars, "playing") else None) or {}
    race = races.bit_of(me.get("race"), side) if me.get("race") else 0
    spells = chars.known_spells() if hasattr(chars, "known_spells") else None
    bags = chars.bags_now() if hasattr(chars, "bags_now") else None
    return race, spells, bags


def weigh_route(hub, start, goal, name, side, taxi, hearth, patience=None, ghost=False):
    speed, level = hub.characters.travel_speed(), None if ghost else (hub.state or {}).get("level")
    race, spells, bags = travel_means(hub, side)
    cuts = []
    patience = WEIGH_SECONDS if patience is None else patience
    settled = math.isinf(patience)
    plans = hub.routes.plans(start, goal, name, side, taxi, hearth, speed, ghost=ghost, race=race, spells=spells, bags=bags,
                             cuts=cuts, wait=settled)
    real = {}
    if cuts:
        real.update(weigh_walks(hub, list(dict.fromkeys(cuts))[:WEIGH_MOST * 2], level, side or "", patience, ghost))
        found = frozenset(w for w, got in real.items() if got not in (None, LATE) and not got[2])
        if found:
            plans = hub.routes.plans(start, goal, name, side, taxi, hearth, speed, ghost=ghost, race=race, spells=spells,
                                     bags=bags, allow=found, wait=settled)
    if not plans:
        return {"legs": [], "speed": speed, "weighed": False, "complete": True}
    planreport.report(tried=plans)
    close = [p for p in plans if p["cost"] <= plans[0]["cost"] * WEIGH_CLOSE][:WEIGH_MOST]

    def weigh(some):
        walks = list({w[:3] for p in some for w in p["walks"]} - set(real))
        if walks:
            real.update(weigh_walks(hub, walks, level, side or "", patience, ghost))
        for p in some:
            for w in p["walks"]:
                got = real.get(w[:3])
                if got == LATE:
                    p["late"] = True
                elif got is not None:
                    yards, counted, cut = got
                    p["cost"] += counted - w[3]
                    p["yards"] += yards - w[3]
                    p["over"] = p.get("over", False) or counted > yards
                    p["cut"] = p.get("cut", False) or cut

    def rank(p):
        return bool(p.get("cut")), bool(p.get("late")), p["cost"]
    weighed = len(close) > 1 or bool(level)
    if weighed:
        weigh(close)
        best = min(close, key=rank)
        if (best.get("over") or best.get("cut") or best.get("late")) and len(plans) > len(close):
            rest = plans[len(close):WEIGH_MOST * 2]
            weigh(rest)
            close += rest
        plans = sorted(close, key=rank)
    minutes = lambda p: round(p["yards"] / speed / 60, 1)
    best = plans[0]
    planreport.report(won=best)
    body = {"legs": name_flight_masters(hub, best["legs"], start, side), "yards": round(best["yards"]), "minutes": minutes(best),
            "speed": speed, "weighed": weighed,
            "complete": not any(p.get("late") for p in plans)}
    other = next((p for p in plans[1:] if not p.get("late") and not p.get("cut")), None) if weighed else None
    if other:
        body["against"] = {"what": route_words(other), "minutes": minutes(other),
                           "hearth": bool(other["legs"]) and other["legs"][0]["kind"] == "hearth"}
    return body


def measured_respawn(hub):
    def respawn(npc):
        shortest, longest, watched = hub.respawns.time_seen(npc)
        return (longest if watched else shortest) or None
    return respawn


def warm_paths(hub):
    done = set()
    while True:
        time.sleep(5)
        s = hub.state or {}
        try:
            pos = s.get("pos")
            here = pos and world_pos(s.get("map"), pos["x"], pos["y"])
            if not here or (s.get("flags") or {}).get("taxi"):
                continue
            r, c = nav.cell_of(here[1], here[2])
            key = (here[0], r // 128, c // 128)
            near = (here[0], "near", round(here[1] / nav.PROP_GRID), round(here[2] / nav.PROP_GRID))
            if key not in done:
                hub.paths.warm(*here)
                done.update((key, near))
            elif near not in done:
                hub.paths.warm_near(*here)
                done.add(near)
        except Exception:
            log_error("path warm-up")
