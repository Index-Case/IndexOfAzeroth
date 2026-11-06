# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import email.utils
import html
import ipaddress
import json
import math
import os
import re
import socket
import time
from urllib.parse import parse_qs, unquote

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from errands import spell_states
from indoors import Indoors
import storedonly
import mainstores
import nav
import planreport
import game
import gaps
import protocol
from itemtips import MISSING
import races
import books
import legacy
from characters import realm_label, seen_record
import camping
import datafiles
import dayrecord
import crafting
import farmspots
import itemsources
import nextupgrades
import hidden
import mapzones
from mapzones import (city_names, dock_pois, learnt_entrances, learnt_way_in, nearest_dock, portal_pois, portals_in,
                      zone_names)
import npcs
import market
import pictures
import questplan
import questtext
import pagesettings
import jsontext
import streams
import updates
import updatenews
import upgrades
import talentplan
import youtube
from serverlog import log_error, log_note
from gamedata import ITEM_TIPS, SPELL_TIPS, item_ids, item_infos, load_todo, save_todo, spell_icons, stat_weights, stored_icon, todo_lock
from planning import (build_epic, covered_split, danger_stretches, game_prices, playing_char, playing_now, prof_panel,
                      profession_summary, quest_zones, round_or_through, start_fresh, wanted, weigh_route, camp_opens,
                      camp_state, class_chains, planned_blind)
from gathering import (GATHER_SEARCH_KEEP, GRIND_MAPS_MOST, GRIND_SEARCH_SECONDS, SEARCHES_MOST, GatherSearch,
                       _searches_lock, camp_walk, safest_way)
from shared import quiet_table
from dungeons import share_stars
from epicwatch import plan_mode
from levelreport import valid_key
import levelshots

ROOT = os.path.dirname(os.path.abspath(__file__))


STARTED = round(time.time())

WEB = os.path.join(ROOT, "web")


TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json", ".jpg": "image/jpeg",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".ttf": "font/ttf",
         ".woff2": "font/woff2", ".gif": "image/gif", ".webp": "image/webp",
         ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


MAX_BODY = 1 << 20

MY_NAMES = {"localhost", socket.gethostname().lower()}


def whole(v, default=0):
    return int(v) if isinstance(v, str) and v.isdecimal() and len(v) <= 12 else default


LEATHERS_MOST = 64


def leather_ids(v):
    return tuple(sorted({i for i in (whole(p) for p in (v or "").split(",")[:LEATHERS_MOST]) if i}))


def finite(v):
    x = float(v)
    if not math.isfinite(x):
        raise ValueError(f"not a finite number: {v}")
    return x


def tenth(x):
    return math.floor(x * 10 + 0.5) / 10


ROUTES = {}

SHAPED = []


def serves(method, path, end=None, fetches=None, only_here=None):
    def register(route):
        route.fetches = fetches
        route.only_here = only_here
        if end is None:
            ROUTES[method, path] = route
        else:
            SHAPED.append((method, path, end, route))
        return route
    return register


def reading_stores(route):
    return contextlib.nullcontext() if getattr(route, "fetches", None) else storedonly.stored_only()


def route_for(method, path):
    route = ROUTES.get((method, path))
    if route:
        return route, ()
    for m, start, end, route in SHAPED:
        if m == method and path.startswith(start) and path.endswith(end) and len(path) >= len(start) + len(end):
            return route, (path[len(start):len(path) - len(end)],)
    return None, ()


def page_file(path):
    return not path.startswith("/api/") and route_for("GET", path)[0] is None


@serves("GET", "/events")
def get_events(h, hub):
    return h.stream()


@serves("GET", "/api/state")
def get_state(h, hub):
    return h.send_json(hub.snapshot()[1])


@serves("GET", "/api/maps")
def get_maps(h, hub):
    waiting = mapzones.zones_unknown(hub)
    if waiting:
        return h.send_json({"waiting": waiting}, status=409)
    read = datafiles.load(datafiles.data_path("maps.json"))
    maps = {**read, "maps": {k: dict(v) for k, v in (read.get("maps") or {}).items()}}
    maps["maps"].update({k: dict(v) for k, v in hub.dungeons.floors.items()})
    for mid, levels in hub.zone_levels.items():
        if mid in maps["maps"]:
            maps["maps"][mid]["levels"] = levels
    for mid, areas in mapzones.AREAS.items():
        if mid in maps["maps"]:
            maps["maps"][mid]["areas"] = areas
    version = hub.tiles.get("version")
    for mid, m in maps["maps"].items():
        if m.get("art"):
            m["picture"] = pictures.stamp(pictures.worldmap_spec(mid, m["art"], version))
        if m.get("highlight"):
            m["highlightPicture"] = pictures.stamp(pictures.glow_spec(m["highlight"], version))
    for mid, m in maps["maps"].items():
        sig = pictures.paperup_sig(mid, None if m.get("art") else m.get("area"))
        if sig:
            m["paperup"] = sig
    return h.send_json(maps)


@serves("GET", "/api/hidden")
def get_hidden(h, hub):
    return h.send_json({"places": {str(k): v for k, v in hidden.places_now().items()}})


@serves("GET", "/api/dungeons")
def get_dungeons(h, hub):
    xp = hub.world.xp
    share = (lambda level, mob: xp.share(level, mob, inside=True)) if xp.measured(inside=True) else None
    return h.send_json([with_card(hub, d) for d in hub.dungeons.summary(whole(h.query().get("level")), share,
                                                                         hub.characters.max_level())])


def with_card(hub, d):
    if not d.get("card"):
        return d
    return {**d, "cardPicture": pictures.stamp(pictures.card_spec(d, hub.tiles.get("version")))}


@serves("GET", "/api/dungeon/", "")
def get_dungeon(h, hub, key):
    body = hub.dungeons.detail(key, questplan.book().quests)
    if body is None:
        return h.send_error(404)
    walked = body.get("instance") and not body.get("coming") and all(e.get("described") for e in body["entrances"]) \
        and learnt_way_in(hub, body["instance"])
    if walked:
        body = {**body, "entrances": [walked]}
    return h.send_json({**with_card(hub, body), "portals": [p for p in hub.routes.portals() if p["dungeon"] == body["name"]]})


def send_tooltip(h, tips, oid, named=None, keyed=False):
    oid = protocol.parse_key(oid) if keyed else whole(oid)
    if not oid:
        return h.send_error(404)
    body = tips.tooltip(oid)
    if isinstance(body, dict):
        return h.send_json(body, cache=True)
    base = protocol.split_key(oid)[0]
    known = named(base) if named else {}
    gaps.note(f"{tips.kind}-tip", base, "tooltip", known.get("name"))
    return h.send_json({"missing" if body == MISSING else "none": True, **known}, status=404)


@serves("POST", "/api/gap")
def post_gap(h, hub, body):
    try:
        heard = gaps.note(body.get("kind"), body.get("id"), body.get("where"), body.get("name"))
    except ValueError:
        return h.send_error(400)
    return h.send_json({"heard": heard})


def item_named(item_id):
    it = item_infos([item_id]).get(str(item_id))
    return {"name": it["n"], "quality": it["q"]} if it else {}


@serves("GET", "/api/tooltip/", "")
def get_tooltip(h, hub, item):
    return send_tooltip(h, ITEM_TIPS, item, item_named, keyed=True)


@serves("GET", "/api/spelltip/", "")
def get_spelltip(h, hub, spell):
    return send_tooltip(h, SPELL_TIPS, spell)


def send_asked(h, ask, none=None):
    try:
        found = ask()
    except ValueError as e:
        return h.send_error(400, str(e))
    except storedonly.Unreadable as e:
        return h.send_error(502, str(e))
    except OSError as e:
        return h.send_error(504, str(e))
    return h.send_error(404, none) if found is None else h.send_json(found)


@serves("GET", "/api/youtube/channel", fetches="the video window: the channel of the video you paste, from YouTube")
def get_youtube_channel(h, hub):
    q = h.query()
    return send_asked(h, lambda: youtube.channel(video=q.get("video"), handle=q.get("handle")),
                      none="YouTube has no such video or channel")


@serves("GET", "/api/video/live", fetches="the video window: whether a saved stream is live, from its site")
def get_video_live(h, hub):
    q = h.query()
    return send_asked(h, lambda: {"live": streams.live(q.get("site"), q.get("channel"))})


@serves("GET", "/api/path")
def get_path(h, hub):
    q, world = h.query(), hub.world
    ghost = q.get("ghost") == "1"

    def height(v):
        if not v:
            return None
        parts = [finite(x) for x in v.split(",")]
        return tuple(parts) if len(parts) == 2 else parts[0]
    try:
        inst = int(q["inst"])
        start, goal = (finite(q["fn"]), finite(q["fw"])), (finite(q["tn"]), finite(q["tw"]))
        start_z, goal_z = height(q.get("fz")), height(q.get("tz"))
    except (KeyError, ValueError):
        return h.send_error(400)
    indoor_flag = {"1": True, "0": False}.get(q.get("indoors"))
    want = wanted((q.get("want") or "").split(","))
    try:
        avoid, asked = None, contextlib.nullcontext()
        mode = "" if ghost else q.get("mode") or ""
        if not mode and q.get("level") and not ghost and not hub.paths.terrain.is_dungeon(inst):
            mode = "round"
        if mode == "gather":
            level, faction = whole(q.get("level"), 1) or 1, q.get("faction", "")
            layer, types = q.get("layer", ""), tuple(t for t in q.get("types", "").split("|") if t)
            dd = q.get("daredevil") == "1"
            avoid = (("gather", level, faction, layer, types, dd),
                     world.gather_rows(inst, level, faction, layer, types, daredevil=dd), "gather")
            asked = safest_way(dd)
        elif mode in ("round", "safe", "fight"):
            level, faction = whole(q.get("level"), 1) or 1, q.get("faction", "")
            mobs = world.threats(inst, level, faction, fight=mode == "fight", want=want)
            avoid = ((mode, level, faction, want) + ((world.level_cap(),) if mode == "fight" else ()), mobs) \
                + (("seek",) if mode == "fight" else ("roads",) if mode == "safe" else ())
        level = None if ghost else whole(q.get("level"))
        with (nav.wm.background() if q.get("bg") == "1" else contextlib.nullcontext()), asked:
            body = round_or_through(hub, inst, start, goal, start_z, goal_z, indoor_flag, ghost, avoid, level or None, mode,
                                    side=q.get("faction") or None)
        body = dict(body) if body else body
        if body and q.get("easy") == "1" and not ghost and mode != "gather" and not body.get("partial") \
                and (body.get("climbs") or body.get("drops")):
            with nav.easy_way():
                easy = round_or_through(hub, inst, start, goal, start_z, goal_z, indoor_flag, ghost, avoid, level or None,
                                        mode, side=q.get("faction") or None)
            if easy and easy.get("points") and not easy.get("partial"):
                covered, indoor = covered_split(hub, inst, easy["points"], rooms=True)
                body["easy"] = {"points": easy["points"], "length": easy["length"], "covered": covered, "indoor": indoor}
        if body and body.get("overZones"):
            body["overZones"] = zone_names(hub, body["overZones"])
        if body and body.get("enemyCities"):
            body["enemyCities"] = city_names(hub, body["enemyCities"])
        if body and body.get("enemyGoal"):
            body["enemyGoal"] = (city_names(hub, [body["enemyGoal"]]) or [None])[0]
        if body and body.get("points"):
            body["covered"], body["indoor"] = covered_split(hub, inst, body["points"], rooms=True)
        if body and q.get("level") and not ghost and not hub.paths.terrain.is_dungeon(inst):
            body["danger"] = danger_stretches(body.get("points"), world.threats(
                inst, whole(q.get("level"), 1) or 1, q.get("faction", ""), want=want))
            body["dangerNotes"] = hub.dangerous.span_notes(inst, body["danger"], q.get("faction") or None)
    except storedonly.NotStored:
        return h.send_error(404, "Not stored yet")
    except OSError as e:
        return h.send_error(502, str(e))
    return h.send_json(body)


@serves("GET", "/api/patches")
def get_patches(h, hub):
    body = hub.patches.snapshot() if hub.patches else {"patches": []}
    return h.send_json({**body, "started": STARTED})


@serves("GET", "/api/pack")
def get_pack(h, hub):
    return h.send_json(hub.pack.snapshot())


@serves("GET", "/api/shared")
def get_shared(h, hub):
    asked = whole(h.query().get("version"))
    body = hub.shared.snapshot(asked) if hub.shared else {"version": None, "working": None, "epic": None}
    body["playing"] = playing_char(hub)
    return h.send_json(body)


@serves("GET", "/api/shared/progress")
def get_shared_progress(h, hub):
    q = h.query()
    at = lambda name: whole(q[name]) if name in q else None
    return h.send_json(hub.shared.progress_now(ways_from=at("from"), steps_from=at("steps"), quests="quests" in q,
                                               order="order" in q) if hub.shared else None)


@serves("GET", "/api/activity")
def get_activity(h, hub):
    return h.send_json(nav.ACTIVITY.now())


@serves("GET", "/api/navfill")
def get_navfill(h, hub):
    return h.send_json(hub.navfill.snapshot())


@serves("GET", "/api/route")
def get_route(h, hub):
    q = h.query()
    try:
        start = (int(q["si"]), finite(q["sn"]), finite(q["sw"]))
        goal = (int(q["gi"]), finite(q["gn"]), finite(q["gw"]))
    except (KeyError, ValueError):
        return h.send_error(400)
    ghost = q.get("ghost") == "1"
    taxi = None if ghost else hub.characters.known_taxi()
    ask, shared = whole(q.get("ask")), hub.shared
    told = planreport.reporting(lambda *said: shared.route_report(ask, *said)) if ask and shared else contextlib.nullcontext()
    try:
        with told:
            plan = weigh_route(hub, start, goal, q.get("name", ""), q.get("side") or None, taxi,
                               None if ghost else q.get("hearth") or None, ghost=ghost)
    finally:
        if ask and shared:
            shared.route_done(ask)
    plan["noFlights"] = not taxi and not ghost
    return h.send_json(plan)


@serves("GET", "/api/route/progress")
def get_route_progress(h, hub):
    q = h.query()
    ask = whole(q.get("ask"))
    return h.send_json(hub.shared.route_progress(ask, whole(q.get("walks")), tried="tried" in q)
                       if ask and hub.shared else None)


@serves("GET", "/api/respawns")
def get_respawns(h, hub):
    return h.send_json({"timers": hub.respawns.current(), "now": time.time()})


@serves("GET", "/api/heights")
def get_heights(h, hub):
    return h.send_json({"heights": hub.heights_seen.listed()})


@serves("GET", "/api/auction/status")
def get_auction_status(h, hub):
    return h.send_json(hub.auction.status())


@serves("GET", "/api/auction/feed")
def get_auction_feed(h, hub):
    q = h.query()
    return h.send_json(hub.auction.feed_since(whole(q.get("since")), min(500, whole(q.get("most"), 500) or 500)))


@serves("GET", "/api/auction/prices")
def get_auction_prices(h, hub):
    q = h.query()
    keys = [k for k in q.get("ids", "").split(",") if re.fullmatch(r"\d{1,7}(:-?\d{1,7})?", k)][:400]
    return h.send_json(hub.auction.prices(keys, q.get("house") or None))


@serves("GET", "/api/auction/items")
def get_auction_items(h, hub):
    q = h.query()
    return h.send_json(hub.auction.items(q.get("house") or None, q.get("q", "")[:60], whole(q.get("most")) or None))


@serves("GET", "/api/market/search")
def get_market_search(h, hub):
    q = h.query()
    text = q.get("q", "").strip()
    if not text:
        return h.send_error(400)
    return h.send_json(market.answer(hub.auction, text, q.get("full") == "1", itemsources.lookup(hub).keys))


@serves("GET", "/api/market/item/", "",
        fetches="the Market menu: an item looked up, its icon when our store lacks it, from the client's files")
def get_market_item(h, hub, item):
    item_id = whole(item)
    body = market.fetch_item(item_id) if item_id else None
    return h.send_json(body) if body else h.send_error(404)


@serves("POST", "/api/auction/demo")
def post_auction_demo(h, hub, body):
    n = body.get("auctions", 4000)
    speed = body.get("speed", 3)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 50000 \
            or not isinstance(speed, (int, float)) or isinstance(speed, bool) or not 0.2 <= speed <= 100:
        return h.send_error(400)
    if not hub.auction.play_demo(auctions=n, speed=float(speed)):
        return h.send_error(409)
    return h.send_json(hub.auction.brief())


@serves("GET", "/api/characters")
def get_characters(h, hub):
    snap = hub.characters.snapshot()
    every = (snap.get("chars") or {}).values()
    named = lambda c: {**c, "realmName": realm_label(c["realm"])} if c.get("realm") else c
    chars = {}
    for key, c in (snap.get("chars") or {}).items():
        shown = races.shown_name(c.get("race"), c.get("faction", "")) if c.get("race") else None
        seen = seen_record(key, c, every, mapzones.zone_map_named)
        chars[key] = named({**c, **({"raceName": shown} if shown else {}), **({"seen": seen} if seen else {})})
    snap = {**snap, "chars": chars, "removed": {k: named(r) for k, r in (snap.get("removed") or {}).items()}}
    return h.send_json({**snap, "legacyBoard": legacy.board(snap.get("legacy"), snap.get("chars") or {}), "now": time.time()})


@serves("GET", "/api/runs")
def get_runs(h, hub):
    return h.send_json(hub.dungeons.run_log())


@serves("GET", "/api/layerzones")
def get_layerzones(h, hub):
    q = h.query()
    try:
        body = hub.world.zone_scores(int(q["instance"]), int(q.get("level") or 1), q.get("faction", ""), q.get("all") == "1",
                                     int(q.get("skin") or 0), ah=q.get("ah") == "1", skinning=whole(q.get("skinning")),
                                     leathers=leather_ids(q.get("leathers")))
    except (KeyError, ValueError):
        return h.send_error(400)
    return h.send_json(body)


@serves("GET", "/api/nodezones")
def get_nodezones(h, hub):
    try:
        body = hub.world.zone_nodes(int(h.query()["instance"]))
    except (KeyError, ValueError):
        return h.send_error(400)
    return h.send_json(body)


@serves("GET", "/api/nodekinds")
def get_nodekinds(h, hub):
    return h.send_json(hub.world.node_kinds())


@serves("GET", "/api/leatherkinds")
def get_leatherkinds(h, hub):
    return h.send_json(hub.world.skin_kinds())


@serves("GET", "/api/leatherzones")
def get_leatherzones(h, hub):
    q = h.query()
    try:
        body = hub.world.zone_leathers(int(q["instance"]), q.get("faction", ""))
    except (KeyError, ValueError):
        return h.send_error(400)
    return h.send_json(body)


@serves("GET", "/api/epic")
def get_epic(h, hub):
    q = h.query()
    try:
        anchor = (int(q["inst"]), finite(q["n"]), finite(q["w"])) if q.get("inst") else None
        parked = {int(p) for p in (q.get("parked") or "").split(".") if p}
        body = build_epic(hub, q["key"], anchor, parked=parked, close=q.get("close") == "1")
    except (KeyError, ValueError):
        return h.send_error(400)
    if body is None:
        return h.send_error(404)
    if body.get("waiting"):
        return h.send_json(body, status=409)
    return h.send_json(body)


@serves("GET", "/api/quests")
def get_quests(h, hub):
    waiting = planned_blind(hub)
    if waiting:
        return h.send_json({"waiting": waiting}, status=409)
    return h.send_json({"zones": quest_zones(hub), "campOpens": camp_opens(), "classChains": class_chains(hub)})


@serves("GET", "/api/questtext")
def get_questtext(h, hub):
    try:
        wtf = game.wtf_dir()
    except game.GameNotFound:
        wtf = None
    ids = [i for i in map(whole, h.query().get("ids", "").split(",")) if i]
    return h.send_json(questtext.texts(ids, hub.characters.playing(), wtf))


@serves("GET", "/api/grindloop")
def get_grindloop(h, hub):
    q = h.query()
    try:
        item = whole(q.get("item")) or None
        maps = sorted(farmspots.farm_for(hub.world).zones()) if item else \
            [int(m) for m in (q.get("maps") or q["map"]).split(",") if m][:GRIND_MAPS_MOST]
        near = (finite(q["n"]), finite(q["w"])) if q.get("n") else None
        level, faction = int(q.get("level") or 1), q.get("faction", "")
        body = hub.world.grind_loop(maps, level, faction, near,
                                    walk=lambda inst, ids: camp_walk(hub, inst, level, faction, ids),
                                    until=time.time() + GRIND_SEARCH_SECONDS,
                                    gold=q.get("gold") == "1",
                                    near_inst=int(q["i"]) if q.get("i") else None,
                                    all_levels=q.get("all") == "1",
                                    aoe=whole(q.get("aoe")),
                                    skin=whole(q.get("skin")),
                                    ah=q.get("ah") == "1",
                                    skinning=itemsources.skinning(itemsources.me_of(hub)) if item else whole(q.get("skinning")),
                                    leathers=leather_ids(q.get("leathers")),
                                    item=item)
    except (KeyError, ValueError):
        return h.send_error(400)
    return h.send_json(body)


@serves("GET", "/api/gatherspot")
def get_gatherspot(h, hub):
    q = h.query()
    item = whole(q.get("item"))
    try:
        here = (int(q["i"]), finite(q["n"]), finite(q["w"])) if q.get("i") else None
    except (KeyError, ValueError):
        return h.send_error(400)
    if not item:
        return h.send_error(400)
    skills = {k: whole(q.get(k)) for k in ("mining", "herbalism")}
    spots = farmspots.farm_for(hub.world).spots(item, max(1, whole(q.get("level"), 1)), q.get("faction", ""), here, skills,
                                                kill=False)["spots"]
    return h.send_json(spots[0] if spots else None)


@serves("GET", "/api/itemsources")
def get_itemsources(h, hub):
    item = whole(h.query().get("item"))
    if not item:
        return h.send_error(400)
    return h.send_json(itemsources.lookup(hub).sources(item))


@serves("GET", "/api/nextupgrades")
def get_nextupgrades(h, hub):
    return h.send_json(nextupgrades.answer(hub))


@serves("GET", "/api/gathersearch")
def get_gathersearch(h, hub):
    q = h.query()
    searches = hub.gather_searches
    with _searches_lock:
        for sid in [k for k, s in searches.items() if s.finished and time.time() - s.finished > GATHER_SEARCH_KEEP]:
            del searches[sid]
        search = searches.get(q["id"]) if q.get("id") else None
    if q.get("id"):
        if not search:
            return h.send_error(404)
        if q.get("stop") == "1":
            search.stopped = True
        return h.send_json(search.snapshot(whole(q.get("since"), 0)))
    try:
        types = [t for t in q.get("types", "").split("|") if t]
        maps = [int(m) for m in (q.get("maps") or q["map"]).split(",") if m.strip()][:GRIND_MAPS_MOST]
        params = {"maps": maps, "layer": q["layer"], "types": types, "skill": whole(q.get("skill"), None),
                  "near": (finite(q["n"]), finite(q["w"])) if q.get("n") else None,
                  "level": whole(q.get("level"), 0) or (hub.state or {}).get("level") or 1,
                  "faction": q.get("faction", ""), "speed": hub.characters.travel_speed(),
                  "client": q.get("client", ""), "daredevil": q.get("daredevil") == "1"}
    except (KeyError, ValueError):
        return h.send_error(400)
    with _searches_lock:
        for s in searches.values():
            if s.params.get("client") == params["client"]:
                s.stopped = True
        busy = sum(1 for s in searches.values() if s.state == "running" and not s.stopped)
        search = GatherSearch(hub, params) if busy < SEARCHES_MOST else None
        if search:
            searches[search.id] = search
    if not search:
        return h.send_error(429, f"{busy} gathering searches are running. Ask again when one of them is done")
    return h.send_json({"id": search.id})


@serves("GET", "/api/spellicons")
def get_spellicons(h, hub):
    return h.send_json(spell_icons([n for n in h.query().get("names", "").split("|") if n]))


@serves("GET", "/api/iteminfo")
def get_iteminfo(h, hub):
    return h.send_json(item_infos([i for i in map(whole, h.query().get("ids", "").split(",")) if i][:400]))


@serves("GET", "/api/itemids")
def get_itemids(h, hub):
    return h.send_json(item_ids([n for n in h.query().get("names", "").split("|") if n][:50]))


@serves("GET", "/api/itemstats")
def get_itemstats(h, hub):
    ids = [i for i in map(protocol.parse_key, h.query().get("ids", "").split(",")) if i][:20]
    return h.send_json({str(i): ITEM_TIPS.stats(i) for i in ids})


@serves("GET", "/api/gear")
def get_gear(h, hub):
    try:
        with open(os.path.join(ROOT, "data", "gear.json"), "rb") as f:
            return h.send_bytes(f.read(), TYPES[".json"])
    except OSError:
        return h.send_error(404)


@serves("GET", "/api/classspells")
def get_classspells(h, hub):
    cs, st = hub.class_spells or {}, hub.status or {}
    cid = whole(h.query().get("class"), 0) or st.get("classId")
    c = (cs.get("classes") or {}).get(str(cid))
    if not c:
        return h.send_error(404)
    mine = st.get("classId") == cid
    me = (hub.characters.playing() or {}) if mine else {}
    race = races.bit_of(me.get("race"), (st.get("strs") or {}).get("faction", ""))
    level = (hub.state or {}).get("level") or 1
    known = hub.characters.known_spells() if mine else None
    if known is not None:
        pets = hub.characters.known_pet_spells()
        known |= {s["id"] for v in c["levels"].values() for s in v["spells"] if s.get("petSpell") in pets}
    states = spell_states(c["levels"], known, race, level if mine else 0)
    game = game_prices(hub).get(str(cid)) or {}
    levels = {}
    for lv, v in c["levels"].items():
        spells = [{**s, "state": states.get(s["id"]), **({"cost": game[s["id"]], "game": True} if s["id"] in game else {})}
                  for s in v["spells"] if s.get("pet") != "beast"]
        own = [s for s in spells if s.get("trainer") is not False and not s.get("races") and not s.get("needs")]
        levels[lv] = {**v, "spells": spells, "cost": sum(s["cost"] for s in own)
                      if own and all(s.get("cost") is not None for s in own) else v.get("cost")}
    gated, unknown = gated_levels(cs.get("gated") or {}, cid, me, known, level if mine else 0)
    near = {cat: nearest_service(hub, cat) for cat in sorted({e["at"] for v in gated.values() for e in v if e.get("at")})} if mine else {}
    return h.send_json({"class": cid, "name": c["name"], "levels": levels, "mine": mine, "level": level if mine else None,
                        "maxLevel": hub.characters.max_level(), "known": known is not None, "trained": (st.get("nums") or {}).get("trainedLevel") if mine else None,
                        "gated": gated, "gatedUnknown": unknown, "nearest": near,
                        "trees": talent_trees(c, cid), "spec": upgrades.spec_tree(st.get("nums") or {}) if mine else 0,
                        "talentPlan": talentplan.talent_plan(c, cid, (talentplan.builds().get("classes") or {}).get(str(cid)),
                                                             st.get("nums") or {}, hub.talentranks.ranks(hub.characters.current),
                                                             level, hub.characters.talent_build()) if mine else None,
                        **({"petTrainer": nearest_service(hub, "pettrainer")} if mine and any(s.get("pet") == "trainer" for v in levels.values()
                                                                                            for s in v["spells"]) else {})})


def talent_trees(c, cid):
    roles = upgrades.tree_roles(stat_weights()).get(str(cid)) or []
    return [{**t, "roles": roles[i] if i < len(roles) else []} for i, t in enumerate(c.get("trees") or ())]


GATED_AT = {"riding": "riding", "weapon": "weapons"}


def gated_levels(gated, cid, me, known, level):
    out, have = {}, set(known or ())
    mine = list((gated.get("classes") or {}).get(str(cid), {}).items())
    trainers = me.get("profTrainers") or {}
    for name in dict.fromkeys([p["name"] for p in me.get("professions") or ()] + sorted(me.get("recipes") or {})):
        seen = {r["spell"]: r for r in (trainers.get(name) or {}).get("ranks") or ()}
        for lv, entries in ((gated.get("professions") or {}).get(name) or {}).items():
            for e in entries:
                said = seen.get(e["id"])
                if said:
                    have |= {e["id"]} if said.get("known") else set()
                    e = {k: v for k, v in e.items() if k not in ("classic", "forever")} | {"cost": said.get("cost", e.get("cost")), "game": True}
                    lv = str(said.get("level") or lv)
                mine.append((lv, [{**e, "at": name.lower().replace(" ", "")}]))
    for lv, entries in mine:
        for e in entries:
            reached = int(lv) <= level
            state = (("known" if reached else "later") if e["kind"] in ("talent", "milestone")
                     else "known" if e.get("id") in have else "unknown" if known is None and reached else "learn" if reached else "later")
            out.setdefault(lv, []).append({**e, "state": state, **({"at": GATED_AT[e["kind"]]} if e["kind"] in GATED_AT else {})})
    return dict(sorted(out.items(), key=lambda kv: int(kv[0]))), (gated.get("unknown") or {}).get(str(cid)) or []


def nearest_service(hub, cat):
    s, st = hub.state or {}, hub.status or {}
    pos, world = s.get("pos"), getattr(hub, "world", None)
    if not pos or s.get("map") is None or world is None:
        return None
    return world.nearest(s["map"], pos["x"], pos["y"], (st.get("strs") or {}).get("faction", ""), {cat})


def _asked_char(h, hub):
    key = h.query().get("char")
    if key is not None and not valid_key(key):
        h.send_error(400)
        return None
    return hub.characters.resolve(key or hub.characters.current or (hub.characters.last_seen() or {}).get("character") or "")


@serves("GET", "/api/levelreports")
def get_levelreports(h, hub):
    key = _asked_char(h, hub)
    if key is None:
        return None
    if not key:
        return h.send_json({"char": None, "reports": []})
    hub.levelreports.ensure(key)
    record = getattr(hub, "dayrecord", None)
    counting = record.counting(key) if record else set()
    reports = [dict(r, counting=True) if r.get("level") in counting else r for r in hub.levelreports.of(key)]
    return h.send_json({"char": key, "reports": reports})



@serves("GET", "/api/replay/days")
def get_replay_days(h, hub):
    key = _asked_char(h, hub)
    if key is None:
        return None
    return h.send_json({"char": key or None, "days": hub.dayrecord.days(key) if key else []})


@serves("GET", "/api/replay/day")
def get_replay_day(h, hub):
    key, day = _asked_char(h, hub), h.query().get("day") or ""
    if key is None:
        return None
    if not dayrecord.is_day(day):
        return h.send_error(400)
    got = hub.dayrecord.view(key, day) if key else {"events": [], "me": None, "placed": False}
    names = {e["spn"] for e in got["events"] if e.get("spn")}
    rec = (hub.characters.snapshot().get("chars") or {}).get(key) or {}
    return h.send_json({"char": key or None, "day": day, **got, "icons": spell_icons(sorted(names)),
                        "className": rec.get("className")})


@serves("GET", "/api/replay/kills")
def get_replay_kills(h, hub):
    key, q = _asked_char(h, hub), h.query()
    if key is None:
        return None
    try:
        until = float(q.get("until") or time.time())
        since = float(q.get("since") or until - 3600)
    except ValueError:
        return h.send_error(400)
    if until - since > 31 * 86400:
        return h.send_error(400)
    return h.send_json({"char": key or None, "kills": hub.dayrecord.kills(key, since, until) if key else []})


@serves("GET", "/levelshot/", ".jpg")
def get_levelshot(h, hub, name):
    path = levelshots.path_of(name, hub.levelreports.shots)
    return h.send_file(path, cache=True) if path else h.send_error(404)


@serves("POST", "/api/levelreports")
def post_levelreports(h, hub, body):
    char, level = body.get("char"), body.get("level")
    if body.get("do") != "seen" or not valid_key(char) or not isinstance(level, int) or isinstance(level, bool):
        return h.send_error(400)
    return h.send_json({"changed": hub.levelreports.seen(hub.characters.resolve(char), level)})


@serves("GET", "/api/professions")
def get_professions(h, hub):
    return h.send_json({"professions": profession_summary(hub)})


@serves("GET", "/api/profepics")
def get_profepics(h, hub):
    return h.send_json(prof_panel(hub))


@serves("POST", "/api/talentbuild")
def post_talentbuild(h, hub, body):
    build = body.get("build") if isinstance(body, dict) else None
    if build is not None and not isinstance(build, str):
        return h.send_error(400)
    cid = (hub.status or {}).get("classId")
    if not hub.characters.playing() or not cid:
        return h.send_error(409, "The game hasn't said who's playing yet")
    if build and not any(b.get("key") == build for b in (talentplan.builds().get("classes") or {}).get(str(cid)) or ()):
        return h.send_error(404)
    return h.send_json({"changed": hub.characters.talent_build(build, pick=True)})


@serves("POST", "/api/profepics",
        only_here="starts or stops a profession epic, its chores written into the running plan in Shared.lua")
def post_profepics(h, hub, body):
    do, name, char = body.get("do"), body.get("name"), body.get("char")
    if do not in ("start", "stop", "hide", "unhide") or not isinstance(name, str) or (char is not None and not isinstance(char, str)):
        return h.send_error(400)
    current = hub.characters.snapshot()["current"] if hub.characters.playing() else None
    char = hub.characters.resolve(char) if char else char
    if do == "start":
        if not current or (char and char != current):
            return h.send_error(409, "You can only start a profession epic for the character you are playing")
        row = next((r for r in prof_panel(hub)["list"] if r["name"] == name), None)
        if not row:
            return h.send_error(404)
        if not row["can"]:
            return h.send_error(409, row["why"] or "This profession epic isn't open to you")
    changed = hub.characters.prof_epic(name, do, key=None if not char or char == current else char)
    if changed and getattr(hub, "watch", None):
        hub.watch.poke()
    return h.send_json({"changed": changed})


@serves("GET", "/api/books")
def get_books(h, hub):
    got = books.answer(hub.characters)
    return h.send_json(got) if got else h.send_error(404)


CAMP_USE = re.compile(r"Use:\s*(.+)")


def camp_use(item):
    tip = ITEM_TIPS.tooltip(item)
    if not isinstance(tip, dict):
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", tip.get("tooltip") or ""))
    found = CAMP_USE.search(re.sub(r"\s+", " ", text))
    if not found:
        return None
    use = re.split(r"\s*\((?:\d+ \w+ )?Cooldown\)|\s*Max Stack:|\s*Sell Price:", found.group(1))[0]
    return use.strip() or None


@serves("GET", "/api/camp")
def get_camp(h, hub):
    got = camping.panel(camping.load(), camp_state(hub), camp_use)
    return h.send_json(got) if got else h.send_error(404)


@serves("GET", "/api/prospectpictures")
def get_prospectpictures(h, hub):
    folder = os.path.join(ROOT, "web", "img")
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().startswith("prospecting")
                       and n.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"))
    except OSError:
        names = []
    return h.send_json([f"img/{n}" for n in names])


@serves("GET", "/api/statweights")
def get_statweights(h, hub):
    weights = stat_weights()
    return h.send_json(weights) if weights else h.send_error(404)


def send_picture(h, spec):
    if not spec:
        return h.send_error(404)
    path, current = pictures.on_hand(spec)
    if not path:
        return h.send_error(404, "Not stored yet")
    asked = h.query().get("v")
    return h.send_file(path, cache=current if asked is None else asked == pictures.stamp(spec))


@serves("GET", "/card/", ".jpg")
def get_card(h, hub, key):
    d = hub.dungeons.by_key.get(key)
    if not d or not d.get("card"):
        return h.send_error(404)
    return send_picture(h, pictures.card_spec(d, hub.tiles.get("version")))


@serves("GET", "/api/rares")
def get_rares(h, hub):
    map_id = whole(h.query().get("map"))
    rares = hub.rares["by_map"].get(map_id, [])
    out = [{**r, "at": [r["at"][0] / 100, r["at"][1] / 100], "spots": [[x / 100, y / 100] for x, y in r["spots"]],
            "walks": mapzones.patrols_on(hub, map_id, r["id"])} for r in rares]
    ids = {str(i) for r in rares for i in r["loot"]}
    return h.send_json({"map": map_id, "rares": out, "items": {i: hub.rares["items"][i] for i in ids if i in hub.rares["items"]}})


@serves("GET", "/api/npcs")
def get_npcs(h, hub):
    q = h.query()
    text = q.get("q", "").strip()
    try:
        here = (int(q["inst"]), finite(q["n"]), finite(q["w"])) if q.get("inst") else None
    except (KeyError, ValueError):
        return h.send_error(400)
    if not text:
        return h.send_error(400)
    book = npcs.npc_book(hub)
    faction = q.get("faction", "") if q.get("faction") in ("Alliance", "Horde") else ""
    return h.send_lines(npcs.answer(book, text, q.get("full") == "1", here, faction, getattr(hub.world, "spot_heights", None)))


@serves("GET", "/api/npcspots")
def get_npc_spots(h, hub):
    name = h.query().get("name", "").strip()
    if not name:
        return h.send_error(400)
    spots = npcs.heat_spots(npcs.npc_book(hub), name)
    if spots is None:
        return h.send_error(404)
    return h.send_json({"name": name, "spots": spots})


@serves("GET", "/api/indoor")
def get_indoor(h, hub):
    q = h.query()
    try:
        inst = int(q["inst"])
        found = hub.indoors.find(inst, finite(q["x"]), finite(q["y"]), finite(q["z"]) if q.get("z") else None)
    except (KeyError, ValueError):
        return h.send_error(400)
    if found:
        found = {**found, "portals": portals_in(hub, inst, found["world"])}
    return h.send_json(found)


@serves("GET", "/indoor/", ".png")
def get_indoor_picture(h, hub, name):
    if not name.replace("_", "").isdigit():
        return h.send_error(404)
    local = mainstores.find("indoorcache", name + ".png", root=ROOT)
    if not os.path.exists(local):
        return h.send_error(404)
    return h.send_file(local, cache=True)


@serves("GET", "/dungeonmap/", ".png")
def get_dungeonmap(h, hub, inst):
    local = mainstores.find("dungeonmaps", f"{inst}.png", root=ROOT)
    if not inst.isdigit() or not os.path.exists(local):
        return h.send_error(404)
    return h.send_file(local, cache=True)


@serves("GET", "/dungeonbake/", ".jpg")
def get_dungeonbake(h, hub, inst):
    local = mainstores.find("dungeonbake", f"{inst}.jpg", root=ROOT)
    if not inst.isdigit() or not os.path.exists(local):
        return h.send_error(404)
    return h.send_file(local, cache=True)


@serves("GET", "/fileicon/", ".jpg")
def get_fileicon(h, hub, fid):
    fid = whole(fid)
    if not fid:
        return h.send_error(404)
    found, icon = stored_icon(64, fid=fid)
    return h.send_file(icon, cache=found) if icon else h.send_error(404)


@serves("GET", "/api/layers")
def get_layers(h, hub):
    q = h.query()
    num = lambda k: whole(q.get(k))
    skills = {k: num(k) for k in ("mining", "herbalism", "skinning", "fishing")}
    skills["skinned"] = whole(q.get("skinned"), skills["skinning"])
    return h.send_json(hub.world.build(num("map"), max(1, num("level")), q.get("faction", ""), skills, q.get("all") == "1",
                                       ah=q.get("ah") == "1",
                                       leathers=leather_ids(q.get("leathers"))))


@serves("GET", "/api/todo")
def get_todo(h, hub):
    with todo_lock:
        todo = load_todo()
    return h.send_json(todo)


@serves("GET", "/api/settings")
def get_settings(h, hub):
    return h.send_json(pagesettings.load())


@serves("POST", "/api/settings")
def post_settings(h, hub, body):
    kept = pagesettings.change(body.get("set") if isinstance(body, dict) else None)
    return h.send_error(400) if kept is None else h.send_json(kept)


@serves("POST", "/api/update", only_here="answers a release's update offer, which the launcher downloads and puts in")
def post_update(h, hub, body):
    watch = getattr(hub, "updates", None)
    if not getattr(watch, "version", ""):
        return h.send_error(404)
    if not updatenews.choose(watch.root, body.get("choice") if isinstance(body, dict) else None):
        return h.send_error(400)
    return h.send_json({"ok": True})


@serves("GET", "/api/poi")
def get_poi(h, hub):
    q = h.query()
    map_id = whole(q.get("map"))
    body = hub.world.pois(map_id, q.get("faction", ""), hub.entrances.get(map_id), journal=hub.dungeons)
    learnt = learnt_entrances(hub, map_id, [p for p in body["pois"] if not p.get("described")])
    walked = {p["name"].lower().removeprefix("the ") for p in learnt}
    body["pois"] = [p for p in body["pois"] if not (p.get("described") and p["name"].lower().removeprefix("the ") in walked)]
    body["pois"] += portal_pois(hub, map_id) + learnt + dock_pois(hub, map_id)
    return h.send_json(body)


@serves("GET", "/api/travel")
def get_travel(h, hub):
    return h.send_json(hub.routes.networks(h.query().get("faction") or None))


@serves("GET", "/api/nearest")
def get_nearest(h, hub):
    q, world = h.query(), hub.world
    try:
        map_id, fx, fy = int(q["map"]), finite(q["x"]), finite(q["y"])
        detail = int(q["detail"]) if q.get("detail") else None
        goods = [int(i) for i in q.get("goods", "").split(",") if i]
    except (KeyError, ValueError):
        return h.send_error(400)
    cats, items = set(q.get("cats", "").split(",")), [i for i in q.get("items", "").split("|") if i]
    if "boat" in cats:
        return h.send_json(nearest_dock(hub, map_id, fx, fy, q.get("faction", "")))
    if cats & ENTRANCE_KINDS:
        return h.send_json(world.nearest_entrance(map_id, fx, fy, q.get("faction", ""), cats, journal=hub.dungeons))
    ammo = q.get("ammo") if q.get("ammo") in ("arrow", "bullet") else None
    best = (goods and world.nearest(map_id, fx, fy, q.get("faction", ""), cats, goods=goods)) or \
        (items and world.nearest(map_id, fx, fy, q.get("faction", ""), cats, items, ammo)) or \
        world.nearest(map_id, fx, fy, q.get("faction", ""), cats, ammo=ammo, detail=detail)
    return h.send_json(best)


ENTRANCE_KINDS = {"dungeon", "raid", "battleground"}


@serves("GET", "/highlight/", ".png")
def get_highlight(h, hub, fid):
    fid = whole(fid)
    if fid not in mapzones.HIGHLIGHTS:
        return h.send_error(404)
    return send_picture(h, pictures.glow_spec(fid, hub.tiles.get("version")))


@serves("GET", "/icon/", ".jpg")
def get_icon(h, hub, rest):
    size, _, name = rest.rpartition("/")
    if size not in ("", "large") or not name or len(name) > 80 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in name):
        return h.send_error(404)
    found, icon = stored_icon(56 if size else 36, name=name)
    return h.send_file(icon, cache=found) if icon else h.send_error(404)


@serves("GET", "/api/tiles")
def get_tiles(h, hub):
    tiles = pictures.floor_tiles(hub.tiles, hub.dungeons.floors)
    stamps = {inst: {key: pictures.stamp(pictures.tile_spec(tiles, inst, key)) for key in keys}
              for inst, keys in tiles["instances"].items()}
    return h.send_json({**tiles, "instances": {inst: {k: s for k, s in keys.items() if s} for inst, keys in stamps.items()}})


@serves("GET", "/tile/", ".jpg")
def get_tile(h, hub, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].replace("_", "").isdigit():
        return h.send_error(404)
    return send_picture(h, pictures.tile_spec(pictures.floor_tiles(hub.tiles, hub.dungeons.floors), parts[0], parts[1]))


def built_file(path, shape):
    d = datafiles.load(path)
    if not (isinstance(d, dict) and shape(d)):
        raise datafiles.Unread(f"{os.path.basename(path)} isn't the shape the page reads")
    return d


def stamped(version, path):
    return f"{version}.{int(os.path.getmtime(path))}"


RENDER = mainstores.path("rendertiles")
TILE_KEY = re.compile(r"[0-9]+_[0-9]+")


def render_masks():
    out, root = {}, os.path.join(RENDER, "mask")
    for inst in (os.listdir(root) if os.path.isdir(root) else []):
        folder = os.path.join(root, inst)
        if inst.isdigit() and os.path.isdir(folder):
            out[inst] = sorted(n[:-4] for n in os.listdir(folder) if n.endswith(".png") and TILE_KEY.fullmatch(n[:-4]))
    return out


@serves("GET", "/api/rendertiles")
def get_render_tiles(h, hub):
    path = os.path.join(RENDER, "index.json")
    index = built_file(path, lambda d: isinstance(d.get("instances"), dict))
    return h.send_json({**index, "version": stamped(index.get("version"), path), "masks": render_masks()})


@serves("GET", "/rendermask/", ".png")
def get_render_mask(h, hub, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not TILE_KEY.fullmatch(parts[1]):
        return h.send_error(404)
    path = os.path.join(RENDER, "mask", parts[0], parts[1] + ".png")
    return h.send_file(path) if os.path.isfile(path) else h.send_error(404)


@serves("GET", "/rendershape/", ".png")
def get_render_shape(h, hub, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not TILE_KEY.fullmatch(parts[1]):
        return h.send_error(404)
    path = os.path.join(RENDER, "shape", parts[0], parts[1] + ".png")
    return h.send_file(path) if os.path.isfile(path) else h.send_error(404)


@serves("GET", "/rendertile/", ".jpg")
def get_render_tile(h, hub, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or parts[1].count("_") != 1 or not parts[1].replace("_", "").isdigit():
        return h.send_error(404)
    path = os.path.join(RENDER, parts[0], parts[1] + ".jpg")
    return h.send_file(path, cache=True) if os.path.isfile(path) else h.send_error(404)


LIGHT_TINT = os.path.join(ROOT, "data", "lighttint.json")


@serves("GET", "/api/lighttint")
def get_light_tint(h, hub):
    return h.send_json(built_file(LIGHT_TINT, lambda d: isinstance(d.get("instances"), dict)))


TORCHES = os.path.join(ROOT, "data", "torches.json")


@serves("GET", "/api/torches")
def get_torches(h, hub):
    return h.send_json(built_file(TORCHES, lambda d: isinstance(d.get("instances"), dict) and isinstance(d.get("colours"), list)))


ROADWAYS = os.path.join(ROOT, "data", "roadways.json")


@serves("GET", "/api/roadways")
def get_roadways(h, hub):
    return h.send_json(built_file(ROADWAYS, lambda d: isinstance(d.get("instances"), dict)))


CLOUDS = os.path.join(ROOT, "data", "clouds")
CLOUD_PIECE = re.compile(r"[a-z_]+_[0-9]+")


@serves("GET", "/api/clouds")
def get_clouds(h, hub):
    index = built_file(os.path.join(CLOUDS, "index.json"),
                       lambda d: isinstance(d.get("instances"), dict) and isinstance(d.get("pieces"), list))
    return h.send_json({k: index[k] for k in ("version", "pieceTiles", "pieces", "instances", "areas", "circles") if k in index})


@serves("GET", "/clouds/", ".png")
def get_cloud_piece(h, hub, rest):
    if not CLOUD_PIECE.fullmatch(rest):
        return h.send_error(404)
    path = os.path.join(CLOUDS, "pieces", rest + ".png")
    return h.send_file(path, cache=True) if os.path.isfile(path) else h.send_error(404)


DETAILVIEW = mainstores.path("detailview")
DETAILVIEW_FILE = re.compile(r"(minimap|render)/[0-9]+/(mid/)?[0-9]+_[0-9]+\.webp|crests/(alliance|horde)\.png")


@serves("GET", "/api/detailview")
def get_detailview(h, hub):
    path = os.path.join(DETAILVIEW, "index.json")
    index = built_file(path, lambda d: isinstance(d.get("overviews"), dict))
    version = stamped(index["version"], path) if index.get("version") is not None else None
    return h.send_json({"version": version, "chunk": index.get("chunk"), "tilePx": index.get("tilePx"),
                        "overviews": index.get("overviews", {}), "midPx": index.get("midPx"), "mid": index.get("mid", {}),
                        "names": index.get("names", {}), "places": index.get("places", {}),
                        "capitals": index.get("capitals", {}), "crests": index.get("crests", [])})


@serves("GET", "/detailview/", "")
def get_detailview_file(h, hub, rest):
    if not DETAILVIEW_FILE.fullmatch(rest):
        return h.send_error(404)
    path = os.path.join(DETAILVIEW, *rest.split("/"))
    return h.send_file(path, cache=True) if os.path.isfile(path) else h.send_error(404)


HEIGHTS = mainstores.path("heights")


@serves("GET", "/api/heights/", ".bin")
def get_height_map(h, hub, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not (parts[1] == "coarse" or (
            parts[1].count("_") == 1 and parts[1].replace("_", "").isdigit())):
        return h.send_error(404)
    path = os.path.join(HEIGHTS, parts[0], parts[1] + ".bin")
    return h.send_file(path, checked=True) if os.path.isfile(path) else h.send_error(404)


@serves("GET", "/api/fog/", ".png")
def get_fog(h, hub, rest):
    key, _, instance = rest.rpartition("/")
    key = unquote(key)
    if not valid_key(key) or not instance.isdigit():
        return h.send_error(404)
    key = hub.characters.resolve(key)
    made = hub.fog.get(hub.characters.explored_of(key), key, int(instance))
    return h.send_bytes(made, TYPES[".png"]) if made else h.send_error(404)


def sea_store(name, *parts):
    return mainstores.find(name, *parts)


def sea_index(name):
    try:
        with open(sea_store(name, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {}
    return {"version": index.get("version", 0), "instances": index.get("instances", {})}


@serves("GET", "/api/seafield")
def get_sea_index(h, hub):
    return h.send_json(sea_index("seafield"))


@serves("GET", "/api/seafield/", ".bin")
def get_sea_field(h, hub, rest):
    return send_field_tile(h, "seafield", rest)


@serves("GET", "/api/inlandfield")
def get_inland_index(h, hub):
    return h.send_json(sea_index("inlandfield"))


@serves("GET", "/api/inlandfield/", ".bin")
def get_inland_field(h, hub, rest):
    return send_field_tile(h, "inlandfield", rest)


def send_field_tile(h, name, rest):
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not TILE_KEY.fullmatch(parts[1]):
        return h.send_error(404)
    path = sea_store(name, parts[0], parts[1] + ".bin")
    return h.send_file(path) if os.path.isfile(path) else h.send_error(404)


@serves("GET", "/api/seamask")
def get_sea_mask_index(h, hub):
    try:
        with open(sea_store("seamask", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {}
    return h.send_json({"version": index.get("version", 0), **({"world": index["world"]} if index.get("world") else {})})


@serves("GET", "/api/seamask/", ".png")
def get_sea_mask(h, hub, rest):
    if rest != "world":
        return h.send_error(404)
    path = sea_store("seamask", "world.png")
    return h.send_file(path) if os.path.isfile(path) else h.send_error(404)


def tree_file(*parts):
    return mainstores.find("trees", *parts)


@serves("GET", "/api/trees/", ".json")
def get_trees(h, hub, rest):
    parts = rest.split("/")
    good = parts == ["index"] or (len(parts) == 2 and parts[0].isdigit() and parts[1].count("_") == 1
                                  and parts[1].replace("_", "").isdigit())
    path = good and tree_file(*parts[:-1], parts[-1] + ".json")
    return h.send_file(path) if path and os.path.isfile(path) else h.send_error(404)


@serves("GET", "/api/trees/shape/", ".png")
def get_tree_shape(h, hub, rest):
    parts = rest.split("/")
    good = len(parts) == 2 and parts[0].isdigit() and TILE_KEY.fullmatch(parts[1])
    path = good and tree_file("shape", parts[0], parts[1] + ".png")
    return h.send_file(path, cache=True) if path and os.path.isfile(path) else h.send_error(404)


@serves("GET", "/api/trees/roof/", ".png")
def get_tree_roof(h, hub, rest):
    parts = rest.split("/")
    good = len(parts) == 2 and parts[0].isdigit() and TILE_KEY.fullmatch(parts[1])
    path = good and tree_file("roof", parts[0], parts[1] + ".png")
    return h.send_file(path, cache=True) if path and os.path.isfile(path) else h.send_error(404)


def send_tree_sided(h, kind, rest):
    parts = rest.split("/")
    good = len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and TILE_KEY.fullmatch(parts[2])
    path = good and tree_file(kind, parts[0], parts[1], parts[2] + ".png")
    return h.send_file(path, cache=True) if path and os.path.isfile(path) else h.send_error(404)


@serves("GET", "/api/trees/far/", ".png")
def get_tree_far(h, hub, rest):
    return send_tree_sided(h, "far", rest)


@serves("GET", "/api/trees/close/", ".png")
def get_tree_close(h, hub, rest):
    return send_tree_sided(h, "close", rest)


def road_picture(instance, col, row):
    import io
    import numpy as np
    import navstore
    from PIL import Image
    kept = navstore.load_npz(nav.road_path(instance, col, row))
    road = kept.get("road") if kept else None
    if road is None:
        return None
    rgba = np.zeros(road.shape + (4,), np.uint8)
    rgba[..., 3] = road
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return buf.getvalue()


@serves("GET", "/api/trees/roads/", ".png")
def get_tree_roads(h, hub, rest):
    parts = rest.split("/")
    good = len(parts) == 2 and parts[0].isdigit() and TILE_KEY.fullmatch(parts[1])
    made = good and road_picture(int(parts[0]), *map(int, parts[1].split("_")))
    return h.send_bytes(made, TYPES[".png"], cache=True) if made else h.send_error(404)


@serves("GET", "/api/trees/models/", ".png")
def get_tree_model(h, hub, fid):
    path = fid.isdigit() and tree_file("models", f"{fid}.png")
    return h.send_file(path) if path and os.path.isfile(path) else h.send_error(404)


@serves("GET", "/worldmap/", ".jpg")
def get_worldmap(h, hub, map_id):
    art = mapzones.MAPS.get(map_id, {}).get("art") or hub.dungeons.floors.get(map_id, {}).get("art")
    return send_picture(h, art and pictures.worldmap_spec(map_id, art, hub.tiles.get("version")))


@serves("GET", "/paperup/", ".jpg")
def get_paperup(h, hub, map_id):
    m = mapzones.MAPS.get(map_id, {})
    return send_picture(h, pictures.paperup_spec(map_id, None if m.get("art") else m.get("area")))


@serves("GET", "/ui/", ".png")
def get_ui_picture(h, hub, name):
    return send_picture(h, pictures.ui_spec(name))


@serves("GET", "/map/", ".jpg")
def get_zone_art(h, hub, area):
    area = whole(area)
    if not area or not any(m.get("area") == area for m in mapzones.MAPS.values()):
        return h.send_error(404)
    return send_picture(h, pictures.zone_art_spec(area))


@serves("POST", "/api/respawns")
def post_respawns(h, hub, body):
    if not isinstance(body.get("forget"), str):
        return h.send_error(400)
    hub.respawns.forget(body["forget"])
    return h.send_json({})


@serves("POST", "/api/characters")
def post_characters(h, hub, body):
    forget, restore = body.get("forget"), body.get("restore")
    if isinstance(restore, str):
        return h.send_json({"restored": hub.characters.restore(restore)})
    if not isinstance(forget, str):
        return h.send_error(400)
    if body.get("confirm") != "FORGET":
        return h.send_error(400, "Type FORGET to take a character off the board")
    hub.characters.forget(forget)
    return h.send_json({})


@serves("POST", "/api/pending", only_here="writes Pending.lua in the game's addon folder")
def post_pending(h, hub, body):
    line = body.get("line")
    if isinstance(line, str) and line.startswith(("/ioa ", "/ioa ")) and len(line) <= 20000:
        title = body.get("guide") if isinstance(body.get("guide"), str) else ""
        page = body.get("page") if isinstance(body.get("page"), str) else ""
        what = body.get("what") if isinstance(body.get("what"), str) else ""
        written = bool(hub.pending) and hub.pending.set(line, playing_now(hub), title[:80], page[:40], what[:12])
    elif body.get("clear") is True:
        written = bool(hub.pending) and hub.pending.clear(body.get("kind") if body.get("kind") in ("go", "loop") else "go")
    else:
        return h.send_error(400)
    return h.send_json({"written": written})


@serves("POST", "/api/shared/epic", only_here="writes an epic into Shared.lua in the game's addon folder")
def post_shared_epic(h, hub, body):
    try:
        key, anchor = str(body["key"]), body.get("anchor")
        anchor = (int(anchor[0]), tenth(finite(anchor[1])), tenth(finite(anchor[2]))) if anchor else None
        parked = body.get("parked") or []
        if not isinstance(parked, list):
            raise TypeError("parked: a list of quest IDs")
        parked = {int(q) for q in parked}
    except (ValueError, KeyError, TypeError, IndexError):
        return h.send_error(400)
    if not hub.shared:
        return h.send_json({"started": False})
    version, last = (hub.shared.data or {}).get("version"), hub.shared.run_start
    started = start_fresh(hub, key, anchor, plan_mode(body.get("mode")), body.get("close") is True, parked)
    log_note(f"page start {key}: click {body.get('click')}, {'sent again' if body.get('again') is True else 'first send'}, "
             f"table at version {version}, last start written {last}, started {started}")
    if started is None:
        return h.send_error(404)
    return h.send_json({"started": started})


@serves("POST", "/api/shared/mode", only_here="has the epic's plan in Shared.lua written again its new way")
def post_shared_mode(h, hub, body):
    key, mode = body.get("key"), body.get("mode")
    if not isinstance(key, str) or not key or mode not in ("safe", "fight", "any"):
        return h.send_error(400)
    return h.send_json({"asked": bool(hub.watch) and hub.watch.ask_mode(key, mode, playing_char(hub))})


@serves("POST", "/api/shared/stop", only_here="marks the epic closed in Shared.lua in the game's addon folder")
def post_shared_stop(h, hub, body):
    key = body.get("key")
    done = bool(hub.shared) and hub.shared.close_epic(str(key) if key else None, by="page")
    return h.send_json({"stopped": done})


@serves("POST", "/api/shared/open", only_here="marks the epic open again in Shared.lua in the game's addon folder")
def post_shared_open(h, hub, body):
    key = body.get("key")
    if not isinstance(key, str) or not key:
        return h.send_error(400)
    return h.send_json({"opened": bool(hub.shared) and hub.shared.open_epic(key, by="page")})


@serves("POST", "/api/shared/pick", only_here="keeps a crafting epic's pick in Shared.lua in the game's addon folder")
def post_shared_pick(h, hub, body):
    key, item, way = body.get("key"), body.get("item"), body.get("way")
    if not isinstance(key, str) or not key or not isinstance(item, int) or way not in crafting.WAYS:
        return h.send_error(400)
    return h.send_json({"set": bool(hub.shared) and hub.shared.set_pick(key, item, way)})


@serves("POST", "/api/shared/back", only_here="writes the epic set aside back into Shared.lua in the game's addon folder")
def post_shared_back(h, hub, body):
    return h.send_json({"back": bool(hub.shared) and hub.shared.back()})


@serves("POST", "/api/addons", fetches="the addons' install and updates: Check addons now",
        only_here="installs and updates the addons in the game's addon folder")
def post_addons(h, hub, body):
    if hub.addons:
        hub.addons.check_now()
    return h.send_json({"started": bool(hub.addons)})


@serves("POST", "/api/pack", only_here="writes a pack into your Downloads or reads one in, long work")
def post_pack(h, hub, body):
    if body.get("do") == "import":
        path = str(body.get("path") or "").strip().strip('"')
        if not os.path.isfile(path):
            return h.send_json({"started": False, "message": "There is no file at that path"})
        started = hub.pack.import_(path)
    else:
        started = hub.pack.export()
    return h.send_json({"started": started})


@serves("POST", "/api/rebuild", fetches="the pipeline itself: Check sources now and Rebuild everything, in the Sources drawer",
        only_here="starts the pipeline, long work")
def post_rebuild(h, hub, body):
    what = body.get("what")
    started = hub.rebuilder.start("rebuild asked for on the page", "sources" if what == "sources" else None) if hub.rebuilder else False
    return h.send_json({"started": started})


@serves("POST", "/api/wish", only_here="writes the starred loot into Shared.lua in the game's addon folder")
def post_wish(h, hub, body):
    if not isinstance(body.get("toggle"), int) or isinstance(body["toggle"], bool):
        return h.send_error(400)
    stars = hub.dungeons.toggle_wish(hub.characters.current, body["toggle"])
    if stars is None:
        return h.send_error(409)
    share_stars(hub)
    hub.publish()
    return h.send_json(stars)


def moved_warnings(moved):
    if not isinstance(moved, dict) or not all(
            isinstance(d, dict) and isinstance(d.get("sig"), str) and d["sig"].startswith("low|") and isinstance(d.get("todo"), str)
            for d in moved.values()):
        return None
    return {k[:200]: {"sig": d["sig"][:40], "todo": d["todo"][:200]} for k, d in moved.items()}


@serves("POST", "/api/todo", only_here="writes the quiet warnings into Shared.lua in the game's addon folder")
def post_todo(h, hub, body):
    moved = moved_warnings(body["dismiss"]) if "dismiss" in body else {}
    if moved is None:
        return h.send_error(400)
    with todo_lock:
        todo = load_todo()
        if isinstance(body.get("silence"), str):
            todo["silenced"][body["silence"]] = str(body.get("label", body["silence"]))[:200]
        if isinstance(body.get("unsilence"), str):
            todo["silenced"].pop(body["unsilence"], None)
        todo["dismissed"].update(moved)
        if isinstance(body.get("unmove"), str):
            todo["dismissed"].pop(body["unmove"], None)
        save_todo(todo)
        if getattr(hub, "moves", None):
            hub.moves.took(todo)
        if hub.shared:
            try:
                hub.shared.set_quiet(quiet_table(todo))
            except OSError:
                log_error("writing the quiet warnings into Shared.lua")
    if ("silence" in body or "unsilence" in body) and getattr(hub, "watch", None):
        hub.watch.poke()
    return h.send_json(todo)


ART = os.path.join(WEB, "art")
ART_NAME = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def art_names(folder=ART):
    try:
        files = os.listdir(folder)
    except OSError:
        return []
    names = (f[:-4].lower() for f in files if f.lower().endswith(".png"))
    return sorted(n for n in names if n and set(n) <= ART_NAME)


class PageServer(ThreadingHTTPServer):
    request_queue_size = socket.SOMAXCONN
    allow_reuse_address = False
    daemon_threads = True


def make_handler(hub):
    if getattr(hub, "indoors", None) is None:
        hub.indoors = Indoors()

    class Handler(BaseHTTPRequestHandler):
        timeout = 30

        def log_message(self, fmt, *args):
            pass

        def refused(self):
            host = self.headers.get("Host") or ""
            name = host[1:host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0]
            if name and name.lower() not in MY_NAMES:
                try:
                    ipaddress.ip_address(name)
                except ValueError:
                    return "Ask by this PC's address"
            if self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site") and not (
                    self.command == "GET" and self.headers.get("Sec-Fetch-Dest") == "document"
                    and page_file(self.path.split("?")[0])):
                return "Not from another site"
            if self.command == "POST":
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    return "Send JSON"
            route = route_for(self.command, self.path.split("?")[0])[0]
            if getattr(route, "only_here", None) and not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return "Only from this PC"
            return None

        def query(self):
            return {k: v[0] for k, v in parse_qs(self.path.partition("?")[2]).items()}

        def read_json(self, most=MAX_BODY):
            n = whole(self.headers.get("Content-Length") or "0", -1)
            if not 0 <= n <= most:
                self.send_error(413 if n > most else 400)
                return None
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self.send_error(400, "A JSON object")
                return None
            return body

        def failed(self, where):
            log_error(where)
            with contextlib.suppress(OSError):
                self.send_error(500)

        def send_bytes(self, body, ctype, cache=False, status=200, tag=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            stamped = "v" in self.query()
            if tag:
                self.send_header("ETag", tag[0])
                self.send_header("Last-Modified", tag[1])
            self.send_header("Cache-Control", "no-cache" if tag else ("max-age=31536000, immutable" if stamped else "max-age=86400") if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, body, status=200, cache=False):
            self.send_bytes(jsontext.dumps(body).encode(), TYPES[".json"], cache, status)

        def send_lines(self, parts):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            for part in parts:
                self.wfile.write(jsontext.dumps(part).encode() + b"\n")
                self.wfile.flush()

        def send_file(self, path, cache=False, checked=False):
            ext = os.path.splitext(path)[1]
            tag = None
            if checked:
                st = os.stat(path)
                tag = (f'"{st.st_size:x}-{st.st_mtime_ns:x}"', email.utils.formatdate(st.st_mtime, usegmt=True))
                if tag[0] in (self.headers.get("If-None-Match") or "") or self.headers.get("If-Modified-Since") == tag[1]:
                    self.send_response(304)
                    self.send_header("ETag", tag[0])
                    self.send_header("Last-Modified", tag[1])
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    return
            with open(path, "rb") as f:
                self.send_bytes(f.read(), TYPES.get(ext, "application/octet-stream"), cache, tag=tag)

        def send_web_file(self, path):
            local = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
            if local.startswith(os.path.join(WEB, "")) and os.path.isfile(local):
                return self.send_file(local)
            self.send_error(404)

        def do_GET(self):
            path = self.path.split("?")[0]
            why = self.refused()
            if why:
                return self.send_error(403, why)
            try:
                route, rest = route_for("GET", path)
                with reading_stores(route):
                    if path == "/":
                        return self.send_page()
                    dv = getattr(hub, "dev", None)
                    if dv and dv.get(self, path):
                        return
                    if route:
                        return route(self, hub, *rest)
                    self.send_web_file(path)
            except storedonly.NotStored:
                with contextlib.suppress(OSError):
                    self.send_error(404, "Not stored yet")
            except (ConnectionError, TimeoutError):
                pass
            except OSError as e:
                with contextlib.suppress(OSError):
                    self.send_error(502, str(e))
            except Exception:
                self.failed(f"GET {path}")

        def do_POST(self):
            where = self.path.split("?")[0]
            why = self.refused()
            if why:
                return self.send_error(403, why)
            try:
                dv = getattr(hub, "dev", None)
                body = self.read_json((dv.body_limit(where) if dv else None) or MAX_BODY)
                if body is None:
                    return
                route, rest = route_for("POST", where)
                with reading_stores(route):
                    if route:
                        return route(self, hub, body, *rest)
                    if dv and dv.post(self, where, body):
                        return
                    self.send_error(404)
            except storedonly.NotStored:
                with contextlib.suppress(OSError):
                    self.send_error(404, "Not stored yet")
            except (ConnectionError, TimeoutError):
                pass
            except Exception:
                self.failed(f"POST {where}")

        def send_page(self):
            with open(os.path.join(WEB, "index.html"), "rb") as f:
                page = f.read()
            page = page.replace(b'<meta name="page-version" content="">',
                                f'<meta name="page-version" content="{updates.page_version()}">'.encode())
            page = page.replace(b'<html lang="en" data-art="">', f'<html lang="en" data-art="{" ".join(art_names())}">'.encode())
            dv = getattr(hub, "dev", None)
            return self.send_bytes(dv.page(self, page) if dv else page, TYPES[".html"])

        def stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            pages = getattr(hub, "pages", None)
            if pages:
                pages.opened()
            try:
                while True:
                    with hub.cond:
                        hub.cond.wait_for(lambda: hub.version != seen, timeout=5)
                    version, message = hub.encoded()
                    if version == seen:
                        self.wfile.write(b": keepalive\n\n")
                    else:
                        self.wfile.write(message)
                        seen = version
                    self.wfile.flush()
            except (ConnectionError, BrokenPipeError, OSError):
                return
            finally:
                if pages:
                    pages.closed()

    return Handler
