# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import math
import os
import re

import numpy as np

import director_rules
import holdings
import planreport
import planunits
import store
from epic import Epic, asks_offer, can_take, closed_by, fight_level, if_offered, for_side, leads_up, level_guessed, taken_instead, \
    unavailable, first as first_needs, group_work, objective_places, own_run as own_run_why, placed, spell_unmet, \
    quest_sentence, needs
from epicwatch import names
from layers import gray_level
import mapzones
import plansteps
import stepwords
from facts import MAX_LEVEL, RUN_SPEED as RUN, xp_table
from spelltext import duration
from words import say as word_said

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "quests.json")
EPIC_ABOVE = 2
LOOT_KILLS = 1.5
POLISH_PASSES = 20
POLISH_LEAST = 10.0
PASS_MOVES = 40
BAND_ABOVE = 5
OBJECTIVE_FAR = 300.0
TURNIN_FAR = 100.0
ELSEWHERE = 250.0
EARLY_STEPS = 5
LOG_MOST = 20
ON_THE_WAY = 60.0
FAR_KINDS = ("pickup", "objective", "turnin")
LINE_SHARE = 0.9
RAID_TYPE = 62
SKIP_TYPES = {41: "the quest is a PvP quest", RAID_TYPE: "the quest is for a raid"}
NO_HAND_IN = "no source says where the quest is handed in"
NOT_YOURS = re.compile(r"^the quest is for (the other faction|another class|another race)$")
KINDS = {"pickup": 0, "objective": 1, "dungeon": 1, "turnin": 2}
WALK_MARGIN = 1.3
FLY = 28.0
FLIGHT_COST = 15.0


def flight_travel(nodes, hops, known, speed=RUN, flying=FLY, doors=()):
    mine = [n for n in nodes if n["id"] in known]
    if len(mine) < 2 and not doors:
        return None
    index = {n["id"]: k for k, n in enumerate(mine)}
    far = np.full((len(mine), len(mine)), np.inf)
    np.fill_diagonal(far, 0.0)
    for a, b, yards, *_ in hops:
        if a in index and b in index:
            far[index[a], index[b]] = min(far[index[a], index[b]], yards)
    for k in range(len(mine)):
        far = np.minimum(far, far[:, k:k + 1] + far[k:k + 1, :])
    nearest = {}

    def near(p):
        key = (p[0], round(p[1] / 10), round(p[2] / 10))
        if key not in nearest:
            on = [(math.hypot(n["at"][0] - p[1], n["at"][1] - p[2]), k) for k, n in enumerate(mine) if n["map"] == p[0]]
            nearest[key] = min(on) if on else None
        return nearest[key]

    def fly(a, b):
        fa, fb = near(a), near(b)
        if not fa or not fb or fa[1] == fb[1] or not np.isfinite(far[fa[1], fb[1]]):
            return None
        return (fa[0] + fb[0]) * WALK_MARGIN + (far[fa[1], fb[1]] / flying + FLIGHT_COST) * speed

    def by_air(a, b):
        walk, flown = math.hypot(a[1] - b[1], a[2] - b[2]) * WALK_MARGIN, fly(a, b)
        return walk if flown is None else min(walk, flown)

    def travel(a, b):
        return min([by_air(a, b)] + [by_air(a, d) + yards + by_air(e, b) for d, e, yards in doors if d[0] == a[0]])
    return travel

_books = {}


class QuestBook:
    def __init__(self, data, everyone=None):
        self.quests = {int(k): v for k, v in (data.get("quests") or {}).items()}
        self.zones = {int(k): v for k, v in (data.get("zones") or {}).items()}
        self.skills = {int(k): v for k, v in (data.get("skills") or {}).items()}
        self.everyone = everyone or self
        self.sides = {}
        self.after = {}
        for q in self.quests.values():
            for p in set(q.get("preAll", []) + q.get("preAny", [])):
                self.after.setdefault(p, []).append(q["id"])
        for q in self.quests.values():
            n = q.get("next")
            if n and n in self.quests and n not in self.after.get(q["id"], ()):
                self.after.setdefault(q["id"], []).append(n)

    def followups(self, qid):
        return self.after.get(qid, [])

    def line(self, qids):
        out, todo = set(), [q for q in qids if q is not None]
        while todo:
            q = todo.pop()
            if q in out:
                continue
            out.add(q)
            todo += self.followups(q)
            crumb = (self.quests.get(q) or {}).get("breadcrumbFor")
            if crumb:
                todo.append(crumb)
        return out

    def leads_to(self, q, zone):
        if any(e.get("map") == zone for e in q.get("end") or ()):
            return True
        nxt = self.quests.get(q.get("next")) if q.get("next") else None
        return bool(nxt) and starts_in(nxt, zone)

    def for_side(self, side, class_id=None):
        top = self.everyone
        key = (side, class_id)
        if key not in top.sides:
            quests = {i: for_side(q, side, class_id) for i, q in top.quests.items()}
            same = all(quests[i] is q for i, q in top.quests.items())
            top.sides[key] = top if same else QuestBook({"quests": quests, "zones": top.zones, "skills": top.skills}, top)
        return top.sides[key]


def book(path=DATA):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return QuestBook({})
    have = _books.get(path)
    if not have or have[0] != mtime:
        _books[path] = (mtime, QuestBook(store.load_json(path, {})))
    return _books[path][1]


def breadcrumb_to(q):
    if q.get("targets"):
        return None
    return q.get("breadcrumbFor") or q.get("next")


def starts_in(q, zone):
    return any(g.get("map") == zone for g in q.get("start") or ())


def offered_at(q):
    return q.get("req") or 1


def opens_at(q):
    return max(q.get("req") or 1, (q.get("level") or 1) - EPIC_ABOVE)


def waits(n):
    return n.get("min") or (n.get("step") or {}).get("min") or 0


def run_level(run, qid=None, level=None):
    works = run.setdefault("works", {})
    if qid is not None and level is None:
        works.pop(qid, None)
    elif qid is not None:
        works[qid] = max(level, works.get(qid, 0))
    top = max(works.values(), default=0)
    if top > 1:
        run["min"] = top
    else:
        run.pop("min", None)
    return run


def waits_for(nodes):
    return max([waits(n) for n in nodes] + [1])


def quest_waits(q, mob_level=None):
    return max([opens_at(q)] + [fight_level(t, mob_level) or 1 for t in q.get("targets") or ()])


def quest_xp(q, level, cap=MAX_LEVEL):
    full = q.get("xp") or 0
    if level >= cap or not full:
        return 0
    d = level - (q.get("level") or level)
    return full if d <= 5 else math.ceil(full * {6: 0.8, 7: 0.6, 8: 0.4, 9: 0.2}.get(d, 0.1))


def grey(q, level):
    return (q.get("level") or level) <= gray_level(level)


def epic_zone(key):
    return int(key[5:]) if key.startswith("zone:") and key[5:].isdigit() else None


def zone_holds(zone, m):
    return int(m) == zone or mapzones.city_zone(m) == zone


def outside(zone, step):
    return zone is not None and step.get("map") is not None and not zone_holds(zone, step["map"])


def leg_line(items, inside, spot):
    placed = [(inside(x), spot(x)) for x in items if spot(x)]
    legs = sorted(d for (ia, a), (ib, b) in zip(placed, placed[1:]) if ia and ib
                  for d in [planunits.apart(a, b)] if d < math.inf)
    return legs[min(len(legs) - 1, int(LINE_SHARE * len(legs)))] if legs else None


def carries_on(book_, took, later):
    follows = book_.line({q for q in took if q is not None})
    return bool(follows) and any(follows & set(q) for q in later)


def trips_out(items, inside, spot, quests, book_, line=None):
    line = line if line is not None else leg_line(items, inside, spot)
    out, k, n = [], 0, len(items)
    while k < n:
        if inside(items[k]):
            k += 1
            continue
        j = k
        while j + 1 < n and not inside(items[j + 1]):
            j += 1
        chain = carries_on(book_, [q for x in items[k:j + 1] for q in quests(x)],
                           [quests(x) for x in items[j + 1:] if inside(x)])
        left = next((spot(items[i]) for i in range(k - 1, -1, -1) if inside(items[i]) and spot(items[i])), None)
        far = [planunits.apart(left, spot(x)) for x in items[k:j + 1] if spot(x)]
        yards = max(far) if far else math.inf
        out.append({"first": k, "last": j, "chain": chain, "yards": yards,
                    "nip": not chain and line is not None and yards <= line})
        k = j + 1
    return out


def early_at(steps, k):
    s, n = steps[k], 0
    for o in steps[k + 1:]:
        if o.get("kind") == "errand":
            continue
        n += 1
        if o.get("quest") == s.get("quest") and o.get("kind") != "pickup":
            a, b = spot_of(s), spot_of(o)
            return n >= EARLY_STEPS and (not (a and b) or a[0] != b[0] or math.hypot(a[1] - b[1], a[2] - b[2]) > ELSEWHERE)
    return False


def early_reasons(steps):
    for k, s in enumerate(steps):
        if s.get("kind") == "pickup" and early_at(steps, k):
            stepwords.give(s, "early", npc=s.get("npc"))
        elif s.get("kind") == "pickup":
            stepwords.drop(s, ("early",))
    return steps


def visit_reasons(steps, zone, towns=None, early=None, book_=None):
    if zone is None:
        return steps
    early = early if early is not None else {
        id(s): ("pass" if s["reason"][0] == "farpass" else "trip" if s["reason"][0] == "trip" else s["reason"][1].get("quest"))
        for s in steps if (s.get("reason") or [None])[0] in ("far", "farpass", "trip")}
    quest = [s for s in steps if s.get("kind") in FAR_KINDS]
    for s in quest:
        stepwords.drop(s, ("far", "farpass", "trip"))
    away = lambda s: outside(zone, s)
    quiet = {id(s) for t in trips_out(quest, lambda s: not away(s), spot_of, lambda s: (s.get("quest"),), book_ or book())
             if t["chain"] or t["nip"] for s in quest[t["first"]:t["last"] + 1]}
    k = 0
    while k < len(quest):
        if not away(quest[k]):
            k += 1
            continue
        place, j = None, k
        while j < len(quest) and away(quest[j]) and quest[j]["map"] == quest[k]["map"]:
            place, j = place or stepwords.place(quest[j], towns), j + 1
        visit, j = quest[k:j], j - 1
        whys = [early[id(s)] for s in visit if early.get(id(s))]
        why = next((w for w in whys if w in {s.get("questName") for s in visit}), whys[0] if whys else None)
        if why == "pass":
            stepwords.give(quest[k], "farpass", place=place)
        elif why == "trip" or not why and id(quest[k]) not in quiet:
            stepwords.give(quest[k], "trip", place=place, n=len(visit))
        elif why:
            stepwords.give(quest[k], "far", quest=why, place=place)
        k = j + 1
    return steps


class QuestPlan(Epic):
    far_held = False
    holdings = None

    def __init__(self, key, name, wanted, book_, to_world, level, xp, side, race, class_id, skills, done, log, anchor,
                 parked=(), faces=None, follow=False, kill_xp=None, mob_level=None, bags=(), dungeon_of=None,
                 band=None, travel=None, objectives=None, pois=None, spawns_of=None, danger_of=None,
                 counts=None, rested=0, inside=(), cap=MAX_LEVEL, offered=(), with_gets=None, extra=(), stops=(),
                 raids=False, found_in=None, runs=(), spells=None, log_most=None, closed=None, kept=(),
                 heights_of=None, ways=None, levels=None, seconds=None, mob_rank=None, guards_near=None, zone_side=None,
                 towns=None, holdings=None):
        book_ = book_.for_side(side, class_id)
        super().__init__({"key": key, "name": name, "quests": list(extra)}, book_.quests, to_world, level, side, class_id,
                         done, log, anchor, None, parked, faces, spawns_of=spawns_of, danger_of=danger_of,
                         mob_level=mob_level, counts=counts, offered=offered, with_gets=with_gets, objectives=objectives,
                         book=book_.quests if extra else None, heights_of=heights_of, levels=levels, zone_side=zone_side)
        self.book, self.follow, self.stops = book_, follow, list(stops)
        self.band_of = "zone" if key.startswith("zone:") else "dungeon"
        self.zone = epic_zone(key)
        self.wanted = list(wanted) + self.lead_ins(wanted)
        self.xp_now, self.race, self.skills = xp or 0, race or 0, skills or {}
        self.spells = None if spells is None else set(spells)
        self.xp_to_next = xp_table()
        self.kill_xp, self.mob_level, self.bags = kill_xp, mob_level, set(bags)
        self.mob_rank, self.guards_near = mob_rank, guards_near
        self.towns = towns
        self.rested, self.inside, self.cap = rested or 0, set(inside), cap
        self.dungeon_of, self.band, self.travel, self.ways, self.seconds = dungeon_of, band, travel, ways, seconds
        self.band_level = level if self.zone is not None else None
        self.raids, self.found_in = raids, found_in
        self.log_most = log_most or LOG_MOST
        self.closed = dict(closed or {})
        self.shut_epic = next((k for k in runs if k in self.closed), None)
        self.runs = set(runs) - set(self.closed)
        self.game_objectives = objectives or {}
        self.pois = pois or {}
        self.links = []
        self.held_back = {}
        self.late = set()
        self.chained = set()
        self.spares = []
        self.passed = set()
        self.kept = set(kept)
        self.pruned = {}
        self.misfits = {}
        self.nodes = {}
        self.passes = planunits.Passes()
        self.walks = {}
        self.holdings = holdings
        self.looked, self.gives = {}, set()
        self.deferred = []
        self.zones_of = {}

    def gap(self, a, b, held=None):
        if self.travel and a and b and a[0] == b[0]:
            key = (a, b, held)
            got = self.walks.get(key)
            if got is None:
                got = self.travel(a, b) if held is None else self.travel(a, b, held)
                got = self.walks[key] = got if got is not None else Epic.gap(a, b)
            return got
        return Epic.gap(a, b)

    def held_of(self, route):
        if not self.holdings:
            return None
        only = [k for k, n in enumerate(route) if id(n) in self.gives or id(n) not in self.looked]
        if not only:
            return None
        got = self.holdings.along([n.get("step") or n for n in route], [n.get("spot") for n in route], only)
        if got[-1] is holdings.LIVE:
            return None
        return [None if h is holdings.LIVE else h for h in got]

    def then_of(self, node, spot=None):
        if not self.holdings or node is None or id(node) in self.looked and id(node) not in self.gives:
            return None
        many = node.get("givers") and spot is None
        spots = [s for s, _ in node["givers"]] if many else [spot if spot is not None else node.get("spot")]
        steps = [st for _, st in node["givers"]] if many else [node.get("step") or node]

        def then(held, k):
            got = self.holdings.after(held or holdings.LIVE, steps[k], spots[k])
            return None if got is holdings.LIVE else got
        return then

    def look(self, nodes):
        if not self.holdings:
            return
        nodes = list(nodes)
        places = [n.get("givers") and [(st, sp) for sp, st in n["givers"]] or [(n.get("step") or n, n.get("spot"))]
                  for n in nodes]
        gives = self.holdings.giving(places)
        for k, n in enumerate(nodes):
            self.looked[id(n)] = n
            (self.gives.add if k in gives else self.gives.discard)(id(n))

    def after_node(self, held, node):
        then = self.then_of(node, node.get("spot"))
        return then(held, 0) if then else held


    def allowed(self, q, needed=False, have=()):
        return open_to(q, self.side, self.race, self.class_id, self.skills, in_log=q["id"] in self.log, cap=self.cap,
                       raids=self.raids, needed=needed, spells=self.spells) or \
            unavailable(q, self.done, self.log, self.level, self.by_id, have) or self.shut(q)

    def spare(self, q):
        f = self.by_id.get(breadcrumb_to(q))
        if not f or q["id"] in self.log:
            return False
        if q["id"] in (f.get("preAll") or ()) or q["id"] == f.get("startsWith"):
            return False
        anys = f.get("preAny") or ()
        return q["id"] not in anys or any(p != q["id"] and (p in self.done or p in self.log) for p in anys)

    def startable(self, q):
        if q["id"] in self.log:
            return None
        if not self.handed_in_at(q):
            return NO_HAND_IN
        starts = q.get("start") or []
        if any(g.get("map") is not None for g in starts):
            return None
        if self.start_item(q) or self.joins(q):
            return None
        items = [g for g in starts if g.get("item")]
        if items:
            return f"the quest starts from {items[0]['name']}, which you don't have"
        return "the giver of the quest isn't on any map"

    def handed_in_at(self, q):
        if any(e.get("map") is not None for e in q.get("end") or ()) or (self.pois.get(q["id"]) or {}).get("end"):
            return True
        return bool(self.dungeon_of and self.dungeon_of(q))

    def shut(self, q):
        run = self.dungeon_of(q) if self.dungeon_of else None
        if run and run[0] in self.closed:
            return f"the quest is done inside {run[1]}, which isn't open yet"
        if self.shut_epic:
            return f"the quest is for {self.closed[self.shut_epic]}, which isn't open yet"
        return None

    def met_inside(self, q):
        starts = q.get("start") or []
        if q["id"] in self.log or not starts or not self.dungeon_of or any(g.get("map") is not None for g in starts):
            return None
        items = [g for g in starts if g.get("item")]
        if any(g["item"] in self.bags for g in items):
            return None
        run = self.dungeon_of(q)
        if run and (len(items) < len(starts) or self.found_in and any(self.found_in(g["item"], run) for g in items)):
            return run
        return None

    def joins(self, q):
        return bool(self.met_inside(q))

    def nested_of(self, q):
        run = self.dungeon_of(q) if self.dungeon_of else None
        return run if run and run[0] not in self.runs and q["id"] in self.leads else None

    def nested_runs(self):
        plan, _ = self.closure()
        out = {}
        for q in plan.values():
            run = self.nested_of(q)
            if run and run[0] not in out:
                out[run[0]] = {"key": run[0], "name": run[1], "quest": self.leads[q["id"]], "opener": q["name"]}
        return list(out.values())

    def start_item(self, q):
        items = [g for g in q.get("start") or () if g.get("item")]
        mine = next((g for g in items if g["item"] in self.bags), None)
        if mine or not items or not self.found_in or not self.joins(q):
            return mine
        run = self.dungeon_of(q)
        return next((g for g in items if self.found_in(g["item"], run)), None)

    def closure(self):
        plan, later = self.taken()
        planreport.report(picked=plan, crumbs=self.passed)
        return plan, later

    def taken(self):
        plan, later, seen, wanted = {}, [], set(), set(self.wanted)
        self.leads = {}
        self.spares = spares = []
        todo = list(self.wanted)
        while todo:
            qid = todo.pop(0)
            if qid in seen:
                continue
            seen.add(qid)
            q = self.by_id.get(qid)
            if not q:
                continue
            if self.follow:
                todo += self.book.followups(qid)
            if qid in self.done:
                continue
            if qid not in self.log and taken_instead(q, self.done, self.log, plan) is not None:
                continue
            why = self.allowed(q) or self.startable(q)
            if not why and qid not in self.log and not in_band(q, self.band, self.band_level):
                why = f"the quest opens at level {opens_at(q)}, " + (
                    f"well above the {self.band_of}'s levels of {self.band[0]}-{self.band[1]}" if self.band
                    else f"well above your level of {self.band_level}")
            if not why and self.spare(q) and qid not in self.passed:
                spares.append(qid)
                continue
            chain, why2 = (None, None) if why else self.before(q, have=frozenset(plan))
            if chain:
                stuck = next((cq for cq in chain if self.startable(cq)), None)
                if stuck:
                    chain, why2 = None, first_needs(stuck["name"], self.startable(stuck))
            if why or chain is None:
                if not self.follow or qid in self.wanted:
                    later.append((q, why or why2))
                continue
            ahead = None
            for cq in reversed(chain + [q]):
                if cq["id"] in wanted:
                    ahead = cq
                elif ahead:
                    self.leads.setdefault(cq["id"], ahead["name"])
            for cq in chain + [q]:
                plan.setdefault(cq["id"], cq)
        later = [(q, why) for q, why in later if q["id"] not in plan]
        listed, self.chained, known = {q["id"] for q, _ in later}, set(), {}
        for q, why in list(later):
            if NOT_YOURS.match(why):
                continue
            for cq in self.lead_up(q, known=known):
                if cq["id"] in plan or cq["id"] in listed or cq["id"] in self.done or cq["id"] in self.log or \
                        taken_instead(cq, self.done, self.log, plan) is not None:
                    continue
                listed.add(cq["id"])
                self.chained.add(cq["id"])
                later.append((cq, self.allowed(cq, True) or self.startable(cq) or leads_up(q["name"], why)))
        return plan, later

    def lead_ins(self, own):
        if self.zone is None:
            return []
        quests, own = self.book.quests, set(own)
        return self.thread_in([i for i in self.log if i in quests and i not in own
                               and self.book.leads_to(quests[i], self.zone)], own)

    def thread_in(self, ids, own=frozenset()):
        out, todo, quests = [], list(ids), self.book.quests
        while todo:
            qid = todo.pop(0)
            if qid in out:
                continue
            out.append(qid)
            todo += [f for f in self.book.followups(qid) if f in quests and f not in own and starts_in(quests[f], self.zone)]
        return out

    def crumbs_passed(self, route, plan):
        if not self.anchor or not route:
            return []
        have, own = frozenset(plan), set(self.wanted) | set(plan)
        spots = [n.get("spot") for n in route]
        runs = planunits.runs_at(spots)
        cands = set(self.spares)
        if self.zone is not None:
            cands |= {q["id"] for q in self.by_id.values() if q["id"] not in own and not q.get("targets")
                      and not starts_in(q, self.zone) and self.book.leads_to(q, self.zone)}
        crumbs, held = [], set()
        for i in sorted(cands):
            q = self.by_id.get(i)
            if not q or i in plan or i in self.done or i in self.log or \
                    taken_instead(q, self.done, self.log, plan) is not None or self.allowed(q, have=have) or \
                    self.startable(q) or not in_band(q, self.band, self.band_level):
                continue
            chain, _ = self.before(q, have=have)
            if chain is None or any(c["id"] not in plan for c in chain):
                continue
            if i in self.kept:
                held.add(i)
                continue
            givers = [p for p in (self.to_world(g["map"], g["x"], g["y"]) for g in q.get("start") or ()
                                  if g.get("map") is not None) if p]
            ends = [(g["map"], self.to_world(g["map"], g["x"], g["y"])) for g in q.get("end") or () if g.get("map") is not None]
            at = next((k for k, p in enumerate(spots) for _, e in ends
                       if planunits.apart(p, e) <= planunits.reach("giver", runs[k])), None)
            if at is None:
                at = next((k for k, n in enumerate(route) for m, _ in ends
                           if (n.get("step") or {}).get("map") == m and n.get("spot")), None)
            if givers and at is not None:
                crumbs.append((i, givers, at))
        if not crumbs:
            return self.thread_in(sorted(held), own)
        n, levels = len(route), self.levels(route)
        h = self.held_of(route)
        past = planunits.walked_past(spots + [g[0] for _, g, _ in crumbs], [-1] * (n + len(crumbs)),
                                     [None] * n + [g for _, g, _ in crumbs], runs + [runs[-1]] * len(crumbs),
                                     self.anchor, self.gap, every=True, ways=self.ways,
                                     held=h and h[:n] + [h[n]] * (len(crumbs) + 1))
        taken = {crumbs[m - n][0] for k, m, _, _, s in past
                 if s <= crumbs[m - n][2] and levels[k] >= offered_at(self.by_id[crumbs[m - n][0]])}
        taken |= {i for i, givers, at in crumbs if levels[at] >= offered_at(self.by_id[i]) and spots[at]
                  and any(planunits.apart(g, spots[at]) <= planunits.reach("giver", runs[at]) for g in givers)}
        return self.thread_in(sorted(taken | held), own)

    def lead_up(self, q, seen=frozenset(), known=None):
        known = {} if known is None else known
        if q["id"] in seen or q["id"] in self.log:
            return []
        if q["id"] in known:
            return known[q["id"]]
        seen, out = seen | {q["id"]}, []
        handed, choice, held = needs(q)
        for p in handed + ([held] if held and held not in self.log else []):
            if p not in self.done and p in self.by_id:
                out += self.lead_up(self.by_id[p], seen, known) + [self.by_id[p]]
        anys = [p for p in choice if p in self.by_id]
        if anys and not any(p in self.done for p in choice):
            out += min((self.lead_up(self.by_id[p], seen, known) + [self.by_id[p]] for p in anys),
                       key=lambda c: (bool(self.allowed(c[-1], True)), len(c)))
        known[q["id"]] = list({x["id"]: x for x in out}.values())
        return known[q["id"]]


    @staticmethod
    def pre_of(q):
        handed, choice, _ = needs(q)
        return handed + choice

    def pairs(self, plan):
        out = []
        for q in plan.values():
            i = q["id"]
            p = q.get("parent")
            if p and (p in plan or p in self.log):
                if p not in self.log:
                    out.append(((p, "P"), (i, "P")))
                if p in plan:
                    out.append(((i, "T"), (p, "T")))
            if q.get("until") in plan:
                out.append(((i, "P"), (q["until"], "T")))
            if q.get("disabledBy") in plan:
                out.append(((q["disabledBy"], "T"), (i, "P")))
            if q.get("breadcrumbFor") in plan:
                out.append(((i, "T"), (q["breadcrumbFor"], "P")))
        return out

    def late_quests(self, plan):
        late = {i for i, q in plan.items() if group_work(q, self.mob_rank, self.guards_near)}
        after = {i: set(self.pre_of(q)) for i, q in plan.items()}
        for a, b in self.links:
            after[b[0]].add(a[0])
        more = True
        while more:
            more = {i for i, before in after.items() if i not in late and before & late}
            late |= more
        return late


    def in_zone(self, step):
        m = (step or {}).get("map")
        if self.zone is None or m is None:
            return True
        if m not in self.zones_of:
            self.zones_of[m] = zone_holds(self.zone, m)
        return self.zones_of[m]

    def zone_of(self, n):
        return None if self.in_zone(n.get("step")) else n["step"]["map"]

    def waiting(self, plan, nodes):
        every = [n for q in plan for n in nodes.get(q, ())]
        out, own = {id(n): [] for n in every}, {}
        for q in plan:
            ns = nodes.get(q, ())
            for a in ns:
                out[id(a)] += [b for b in ns if KINDS.get(a["kind"], 3) < KINDS.get(b["kind"], 3)]
                for g in a.get("gets", ()):
                    if id(g) in out:
                        out[id(g)].append(a)
            own[(q, "P")] = next((n for n in ns if n["kind"] == "pickup"), None)
            own[(q, "T")] = next((n for n in ns if n["kind"] == "turnin"), None)
        opens = [(p, q) for q, quest in plan.items() for p in self.pre_of(quest)] \
            + [(p, f) for p in plan for f in self.book.followups(p)]
        for a, b in [((p, "T"), (q, "P")) for p, q in opens] + list(self.links):
            if own.get(a) and own.get(b):
                out[id(own[a])].append(own[b])
        return out

    def mark_far(self, plan, nodes):
        if self.zone is None:
            return
        after = self.waiting(plan, nodes)
        runs = {q for q in plan if any(n["kind"] == "dungeon" for n in nodes.get(q, ()))}
        goes = lambda n: n["kind"] in FAR_KINDS and not n.get("inside") and n.get("quest") not in runs
        home = [m for q in plan for m in nodes.get(q, ()) if self.in_zone(m.get("step"))]
        known = {}

        def stuck(n):
            k = id(n)
            if k not in known:
                known[k] = False
                known[k] = not goes(n) or any(stuck(m) for m in after[k])
            return known[k]

        def waited_on(n):
            seen, todo = set(), list(after[id(n)])
            while todo:
                m = todo.pop()
                if id(m) not in seen:
                    seen.add(id(m))
                    if self.in_zone(m.get("step")):
                        return True
                    todo += after.get(id(m), ())
            return False
        later = lambda n: [(m["quest"],) for m in home
                           if m["quest"] != n["quest"] or KINDS.get(m["kind"], 3) > KINDS.get(n["kind"], 3)]
        for q in plan:
            for n in nodes.get(q, ()):
                if not self.in_zone(n.get("step")) and not stuck(n) and not waited_on(n) \
                        and not carries_on(self.book, (n["quest"],), later(n)):
                    n["far"] = True

    def far_fallback(self, pending, plan, nodes):
        if self.zone is None:
            return False
        ids = {q["id"] for q in pending if not any(n["kind"] == "dungeon" for n in nodes.get(q["id"], ()))}
        todo = [n for q in pending if q["id"] in ids and (self.misfits.get(q["id"]) or ("",))[0] == "order"
                for n in nodes.get(q["id"], ()) if not self.in_zone(n.get("step"))]
        if not todo:
            return False
        after, marked = self.waiting(plan, nodes), False
        while todo:
            n = todo.pop()
            if n.get("quest") in ids and n["kind"] in FAR_KINDS and not n.get("inside") and not n.get("far"):
                n["far"], n["early"], marked = True, "trip", True
                todo += after.get(id(n), ())
        return marked

    @staticmethod
    def rank(n):
        return 2 if n.get("away") else 1 if n.get("late") else 0

    def held(self, rest, n, lo, hi, hold_late=False, passing=False):
        r = 0 if passing else self.rank(n)
        if r:
            lo = max([lo] + [i + 1 for i, m in enumerate(rest) if self.rank(m) < r])
        if r < 2 and self.far_held:
            hi = min(hi, self.far_tail(rest))
        if r < 1 and hold_late:
            late = next((i for i, m in enumerate(rest) if self.rank(m) >= 1), None)
            if late is not None and all(self.rank(m) >= 1 for m in rest[late:]):
                hi = min(hi, late)
        return lo, hi

    def far_tail(self, rest):
        k = len(rest)
        while k and rest[k - 1].get("away"):
            k -= 1
        return k if not any(m.get("away") for m in rest[:k]) else len(rest)

    def still_xp(self, rest, n):
        q, levels = self.by_id[n["quest"]], self.levels(rest)
        return next((p - 1 for p in range(len(levels)) if self.greyed(q, levels[p])), len(rest))

    def greyed(self, q, level):
        return quest_xp(q, level, self.cap) < quest_xp(q, self.level, self.cap)

    def put_off(self, route, q, n):
        need = waits(n)
        if self.reach(route, need, len(route)) <= len(route):
            self.deferred.append(n)
            return True
        self.unfit(route, q["id"])
        self.deferred = [m for m in self.deferred if m.get("quest") != q["id"]]
        return self.misfit(q, ("late", need))

    def place_far(self, route):
        todo, self.deferred, out = self.deferred, [], []
        placed = [n for n in route if n.get("far") and not self.put(n)]
        if placed and not self.feasible(route):
            route[:] = [n for n in route if not (n.get("far") and not self.put(n))]
            for n in placed:
                n.pop("away", None)
                n.pop("early", None)
            todo = placed + todo
        line = leg_line([n for n in route if n["kind"] in FAR_KINDS], lambda n: self.in_zone(n.get("step")),
                        lambda n: n.get("spot"))
        for trip in self.trips(todo):
            if self.far_nip(route, trip, line):
                continue
            zones = {self.zone_of(n) for n in trip} - {None}
            there = [n for n in route if not n.get("away") and self.zone_of(n) in zones]
            if len(zones) == 1 and there and self.far_before(route, trip, join=True):
                said = next((n["early"] for n in there if n.get("early")), None)
                for n in trip:
                    if said:
                        n["early"] = said
                continue
            if self.far_close(route, trip, line):
                for n in trip:
                    n["early"] = "pass"
                continue
            if self.far_at_end(route, trip):
                continue
            end = self.levels(route)[self.far_tail(route) if self.far_held else len(route)]
            gone = [n["quest"] for n in trip if n["kind"] == "turnin" and self.greyed(self.by_id[n["quest"]], end)]
            came = []
            if not self.far_before(route, trip):
                out += self.far_anywhere(route, trip)
            elif gone:
                came = self.far_mates(route, trip)
            for n in trip + came if gone else ():
                n["early"] = self.by_id[n["quest"] if n["quest"] in gone else gone[0]]["name"]
        return out

    def trips(self, steps):
        hop = director_rules.RUN["hop"].value
        root = list(range(len(steps)))

        def top(i):
            while root[i] != i:
                root[i] = root[root[i]]
                i = root[i]
            return i
        for i, a in enumerate(steps):
            for j in range(i):
                b = steps[j]
                if a.get("quest") is not None and a.get("quest") == b.get("quest") \
                        or planunits.apart(a.get("spot"), b.get("spot")) <= hop:
                    root[top(i)] = top(j)
        out, at = [], {}
        for i, s in enumerate(steps):
            r = top(i)
            if r not in at:
                at[r] = len(out)
                out.append([])
            out[at[r]].append(s)
        return out

    def place_one(self, route, n):
        w = self.window_of(route, n)
        if not w:
            return None
        return self.best_giver(route, n, w[0], w[1], lambda i: True) if n["kind"] == "pickup" \
            else self.best_place(route, n["spot"], w[0], w[1], node=n)

    def far_at_end(self, route, trip):
        trial, givers = list(route), [(n, n["spot"], n["step"]) for n in trip if n["kind"] == "pickup"]
        for n in trip:
            n["away"] = True
        self.far_held, kept = True, set(self.faults(route))
        for n in trip:
            i = self.place_one(trial, n)
            if i is None:
                break
            trial.insert(i, n)
        else:
            if set(self.faults(trial)) <= kept and self.in_order(trial):
                route[:] = trial
                return True
        for n in trip:
            n.pop("away", None)
        for n, spot, step in givers:
            n["spot"], n["step"] = spot, step
        return False

    def far_before(self, route, trip, join=False):
        end = len(route)
        while end and (route[end - 1].get("late") or route[end - 1].get("away")):
            end -= 1
        inside, kept = self.timed_inside(route), set(self.faults(route))
        zones = {self.zone_of(n) for n in trip} - {None}
        joins = lambda p: any(0 <= q < len(route) and self.zone_of(route[q]) in zones for q in (p - 1, p))
        for p in [p for p in range(end, -1, -1) if joins(p)] + ([] if join else [
                p for p in range(end, -1, -1) if not joins(p) and not self.amid_far(route, p)]):
            trial = route[:p] + trip + route[p:]
            if p not in inside and set(self.faults(trial)) <= kept and self.in_order(trial):
                route[:] = trial
                return True
        return False

    def far_nip(self, route, trip, line):
        if line is None:
            return False
        trial, kept = list(route), set(self.faults(route))
        givers = [(n, n["spot"], n["step"]) for n in trip if n["kind"] == "pickup"]

        def left(n):
            k = next(i for i, m in enumerate(trial) if m is n)
            return next((m["spot"] for m in reversed(trial[:k]) if m.get("spot") and self.in_zone(m.get("step"))), None)
        for n in trip:
            i = self.place_one(trial, n)
            if i is None:
                break
            trial.insert(i, n)
        else:
            if all(planunits.apart(left(n), n.get("spot")) <= line for n in trip) and set(self.faults(trial)) <= kept \
                    and self.in_order(trial):
                route[:] = trial
                for n in trip:
                    n.pop("early", None)
                return True
        for n, spot, step in givers:
            n["spot"], n["step"] = spot, step
        return False

    def far_close(self, route, trip, line):
        spots = [n["spot"] for n in trip if n.get("spot")]
        if line is None or not spots:
            return False
        end = len(route)
        while end and (route[end - 1].get("late") or route[end - 1].get("away")):
            end -= 1
        inside, kept = self.timed_inside(route), set(self.faults(route))
        home = lambda p: 0 <= p < end and route[p].get("spot") and self.in_zone(route[p].get("step"))
        for p in range(end, 0, -1):
            if not home(p - 1) or p in inside or self.amid_far(route, p):
                continue
            b = route[p]["spot"] if home(p) else None
            if max(planunits.off_leg(s, route[p - 1]["spot"], b) for s in spots) > line:
                continue
            trial = route[:p] + trip + route[p:]
            if set(self.faults(trial)) <= kept and self.in_order(trial):
                route[:] = trial
                return True
        return False

    def far_mates(self, route, trip):
        zones = {self.zone_of(n) for n in trip} - {None}
        held = [n for n in route if n.get("away") and not self.put(n)]
        mine = lambda q: [n for n in route if n.get("quest") == q and self.zone_of(n) is not None]
        quests = {n["quest"] for n in held if self.zone_of(n) in zones}
        quests = {q for q in quests if all(self.zone_of(n) in zones for n in mine(q))}
        moving = [n for n in held if n["quest"] in quests]
        if not moving:
            return []
        kept, givers = set(self.faults(route)), [(n, n["spot"], n["step"]) for n in moving if n["kind"] == "pickup"]
        trial = [n for n in route if not any(n is m for m in moving)]
        for n in moving:
            n.pop("away")
        for n in moving:
            i = self.place_one(trial, n)
            if i is None:
                break
            trial.insert(i, n)
        else:
            if set(self.faults(trial)) <= kept and self.in_order(trial):
                route[:] = trial
                return moving
        for n in moving:
            n["away"] = True
        for n, spot, step in givers:
            n["spot"], n["step"] = spot, step
        return []

    def amid_far(self, route, p):
        return 0 < p < len(route) and not self.in_zone(route[p - 1].get("step")) and not self.in_zone(route[p].get("step"))

    def far_anywhere(self, route, trip):
        out = []
        for n in trip:
            if any(q["id"] == n.get("quest") for q in out):
                continue
            i = self.place_one(route, n)
            if i is None:
                self.unfit(route, n["quest"])
                self.misfit(self.by_id[n["quest"]], ("order",))
                out.append(self.by_id[n["quest"]])
                continue
            route.insert(i, n)
        return out

    @staticmethod
    def unfit(route, qid):
        route[:] = [m for m in route if m.get("quest") != qid or m["kind"] == "dungeon"]
        for m in route:
            if m["kind"] == "dungeon" and qid in (m.get("quests") or ()):
                m["quests"].remove(qid)
            if m["kind"] == "dungeon" and qid in (m.get("works") or {}):
                run_level(m, qid, None)

    def bounds(self, route, key):
        at = {}
        for k, n in enumerate(route):
            kind = {"pickup": "P", "turnin": "T"}.get(n["kind"])
            if kind and n.get("quest") is not None:
                at[(n["quest"], kind)] = k
        lo, hi = 0, len(route)
        for a, b in self.links:
            if b == key and a in at:
                lo = max(lo, at[a] + 1)
            if a == key and b in at:
                hi = min(hi, at[b])
        return lo, hi


    def quest_nodes(self, q):
        nodes, near = [], None
        if q["id"] not in self.log:
            at, who = self.place(q.get("start"))
            item = self.start_item(q) if at is None else None
            text = stepwords.pickup(q["name"], who, self.thing(q.get("start")), item=item and item["name"])
            nodes.append({"kind": "pickup", "step": self.mapped(self.step("pickup", q, text, at, npc=who, min=offered_at(q),
                                                                          face=self.face(self.giver(q.get("start"))),
                                                                          **self.giver_ids(q.get("start"))), q.get("start"))})
            givers = self.pickup_givers(q)
            if len(givers) > 1:
                nodes[-1]["givers"] = givers
            near = at
        at_end, who_end = self.place(q.get("end"))
        marks = self.pois.get(q["id"]) or {}
        giver_at = None
        if marks.get("end") and (not at_end or math.hypot(at_end[1] - marks["end"][1], at_end[2] - marks["end"][2]) > TURNIN_FAR
                                 or at_end[0] != marks["end"][0]):
            giver_at, at_end = at_end and [round(v, 1) for v in at_end[:3]], marks["end"]
        near = near or at_end
        inside = self.dungeon_of(q) if self.dungeon_of else None
        need_items = self.wants_gets(q)
        if not self.log.get(q["id"]) and not inside:
            for t in q.get("targets", []):
                if (not need_items) if t.get("get") else self.left_out(q["id"], t):
                    continue
                s = self.objective_at(q, t, near, loop=False)
                if s:
                    nodes.append({"kind": "objective", "step": s, "kills": self.kills_of(t, s)})
        if q["id"] in self.log and not self.log[q["id"]] and not inside and \
                not any(n["kind"] == "objective" and not n["step"].get("get") for n in nodes):
            mark = (self.pois.get(q["id"]) or {}).get("obj")
            words = [re.sub(r"^\s*\d+\s*/\s*\d+\s*|:\s*\d+\s*/\s*\d+\s*$", "", w or "").strip()
                     for w, finished, *_ in self.game_objectives.get(q["id"], ()) if not finished and "(optional)" not in (w or "").casefold()]
            if mark and words:
                on = ((self.pois.get(q["id"]) or {}).get("maps") or {}).get("obj")
                s = self.step("objective", q, stepwords.game_objective(q, words, quest_sentence), mark, target=words[0],
                              count=1, game=True, map=on)
                if opens_at(q) > 1:
                    s["min"] = opens_at(q)
                nodes.append({"kind": "objective", "step": s, "kills": None})
        if inside and not self.log.get(q["id"]):
            for t in q.get("targets", []) if need_items else ():
                s = t.get("get") and self.objective_at(q, t, near, loop=False)
                if s:
                    nodes.append({"kind": "objective", "step": s, "kills": self.kills_of(t, s)})
            nodes.append(run_level({"kind": "dungeon", "dungeon": inside, "works": {q["id"]: opens_at(q)}}))
        nodes.append({"kind": "turnin", "step": self.mapped(self.step("turnin", q, stepwords.turnin(q["name"], who_end, self.thing(q.get("end"))),
                                                                      at_end, npc=who_end, face=self.face(self.giver(q.get("end"))),
                                                                      giverAt=giver_at, **self.giver_ids(q.get("end"))), q.get("end"))})
        if opens_at(q) > 1 and not self.log.get(q["id"]) and not any(n["kind"] in ("objective", "dungeon") for n in nodes):
            nodes[-1]["min"] = opens_at(q)
        gets = [n for n in nodes if n["kind"] == "objective" and n["step"].get("get")]
        for n in nodes:
            n["quest"] = q["id"]
            n["spot"] = spot_of(n.get("step")) if n["kind"] != "dungeon" else inside[2]
            if inside and n["spot"] is None and n["kind"] in ("pickup", "turnin"):
                n["inside"], n["spot"] = True, tuple(inside[2][:3]) if inside[2] else None
            if gets and (n["kind"] == "dungeon" or n["kind"] == "objective" and not n["step"].get("get")):
                n["gets"] = gets
        return nodes

    def pickup_givers(self, q):
        out, seen = [], set()
        for g in q.get("start") or ():
            if g.get("map") is None or g.get("item"):
                continue
            at, who = self.place([g])
            if at is None or (at[:3], who) in seen:
                continue
            seen.add((at[:3], who))
            step = self.mapped(self.step("pickup", q, stepwords.pickup(q["name"], who, self.thing([g])), at, npc=who,
                                         min=offered_at(q), face=self.face(g), **self.giver_ids([g])), [g])
            out.append((spot_of(step), step))
        return out

    def marked(self, q):
        mark = (self.pois.get(q["id"]) or {}).get("obj")
        if not mark:
            return None, False
        targets = [t for t in q.get("targets", []) if not placed(t, q) and not self.left_out(q["id"], t)]

        def closest(t):
            return min((math.hypot(p[1] - mark[1], p[2] - mark[2]) for p in (self.to_world(*s) for s in t.get("spots") or ())
                        if p and p[0] == mark[0]), default=math.inf)
        return mark, any(not t.get("get") for t in targets) and all(closest(t) > OBJECTIVE_FAR for t in targets)

    def objective_at(self, q, t, near, level=None, loop=True):
        mark, wrong = (None, False) if t.get("get") or placed(t, q) or t.get("owned") else self.marked(q)
        areas = self.game_areas(q, t) if mark else []
        s = None if wrong else self.objective(q, t, mark or near, level, loop, areas, (self.pois.get(q["id"]) or {}).get("marks"))
        if s is None and (wrong or areas):
            at = next((a["at"] for a in areas if a.get("main")), mark)
            s = self.step("objective", q, stepwords.objective(q, t, quest_sentence), at, target=t["name"], count=t.get("count", 1),
                          objective=t["kind"], part=t.get("part"), game=True,
                          map=((self.pois.get(q["id"]) or {}).get("maps") or {}).get("obj"),
                          places=objective_places([], at[0], [], areas))
        fight, work = s and fight_level(t, self.mob_level), opens_at(q)
        if s and (fight or work > 1):
            s["min"] = max(fight or 0, work)
            s["fight"] = fight or 0
        return s

    def game_areas(self, q, t):
        areas = (self.pois.get(q["id"]) or {}).get("areas") or []
        if not areas:
            return []
        targets = [u for u in q.get("targets", ()) if not u.get("get")]
        if len(targets) <= 1:
            return list(areas)
        others = [u for u in targets if u is not t]
        mine = set()
        for k, (words, *_) in enumerate(self.game_objectives.get(q["id"]) or (), 1):
            said = norm_words(words)
            fit = said_fit(said, t)
            if fit and not any(said_fit(said, u) > fit for u in others):
                mine.add(k)
        return [a for a in areas if a["obj"] == 0 or a["obj"] in mine]

    def left_out(self, qid, t):
        game = self.game_objectives.get(qid)
        if not game:
            return False
        q = self.book.quests.get(qid) or {}
        others = [u for u in q.get("targets", ()) if u != t and not u.get("get")]
        for words, finished, *_ in game:
            said = norm_words(words)
            fit = said_fit(said, t)
            if fit and not any(said_fit(said, u) > fit for u in others):
                return bool(finished) or "(optional)" in (words or "").casefold()
        return False

    def begun(self, n):
        step, qid = n.get("step") or {}, n.get("quest")
        game = self.game_objectives.get(qid)
        if not game or not step.get("target"):
            return False
        me = {"text": step.get("text"), "name": step["target"]}
        q = self.book.quests.get(qid) or {}
        others = [u for u in q.get("targets", ()) if not u.get("get") and u.get("name") != step["target"]]
        for words, finished, *_ in game:
            said = norm_words(words)
            fit = said_fit(said, me)
            if fit and not any(said_fit(said, u) > fit for u in others):
                have = re.search(r"(\d+)\s*/\s*\d+", words or "")
                return not finished and have is not None and int(have.group(1)) > 0
        return False

    def kills_of(self, t, s=None):
        mobs = (s or {}).get("mobs") or t.get("mobs")
        if t["kind"] not in ("kill", "loot") or not mobs or not self.mob_level or (s or {}).get("inst") in self.inside:
            return None
        levels = [lv for lv in (self.mob_level(m) for m in mobs) if lv]
        if not levels:
            return None
        n = (t.get("count") or 1) * (1 if t["kind"] == "kill" else LOOT_KILLS)
        return n, sum(levels) / len(levels)


    def levels(self, route):
        level, xp, rested, out = self.level, self.xp_now, self.rested, []
        for n in route:
            out.append(level)
            if n["kind"] == "grind":
                to = min(n["to"], self.cap)
                if to > level:
                    ground = sum(self.xp_to_next.get(lv) or 0 for lv in range(level, to)) - xp
                    level, xp, rested = to, 0, rested - min(rested, max(0, ground) / 2)
                continue
            gain = 0
            if n["kind"] == "turnin":
                gain = quest_xp(self.by_id[n["quest"]], level, self.cap)
            elif n.get("kills") and self.kill_xp:
                count, mob = n["kills"]
                gain = count * self.kill_xp(level, mob)
                more = min(gain, rested)
                gain, rested = gain + more, rested - more
            xp += gain
            while level < self.cap and self.xp_to_next.get(level) is not None and xp >= self.xp_to_next[level]:
                xp -= self.xp_to_next[level]
                level += 1
        out.append(level)
        return out

    def reach(self, route, need, lo):
        if not need or need <= self.level:
            return lo
        levels = self.levels(route)
        return next((i for i in range(lo, len(route) + 1) if levels[i] >= need), len(route) + 1)


    def skill_short(self, q):
        need = q.get("skillTo")
        return (need[0], need[1]) if need and self.skills.get(need[0], 0) < need[1] else None

    def skill_said(self, q):
        short = self.skill_short(q)
        return short and word_said("both.step-why.skill", {"skill": self.book.skills.get(short[0]), "rank": short[1]})


    def cost(self, route, i, spot, node=None):
        if spot is None:
            return 0.0
        return plansteps.added(route, i, spot, self.anchor, node_spot, self.gap, self.held_of(route),
                               self.then_of(node, spot))

    def timed(self, qid):
        return bool((self.by_id.get(qid) or {}).get("limit"))

    def timed_inside(self, route, node=None):
        out, first = set(), {}
        met = not (node is not None and (node.get("inside") or node.get("kind") == "dungeon"))
        for k, m in enumerate(route):
            q = m.get("quest")
            if q is not None and m["kind"] in ("pickup", "objective", "turnin") and self.timed(q):
                first.setdefault(q, k)
                if m["kind"] == "turnin":
                    out.update(range(first[q] + 1, k + 1))
            if met and k + 1 < len(route) and m.get("inside") and m["kind"] in ("pickup", "turnin"):
                out.add(k + 1)
        return out

    def best_place(self, route, spot, lo, hi, ok=None, node=None, placing=None):
        inside = self.timed_inside(route, node)
        allowed = lambda i, _=0: not ((ok and not ok(i)) or i in inside)
        if spot is None:
            return next((i for i in range(lo, hi + 1) if allowed(i)), None)
        best = plansteps.cheapest(route, [spot], lo, hi, self.anchor, node_spot, self.gap, allowed, self.held_of(route),
                                  self.then_of(placing if placing is not None else node, spot))
        return best[1] if best else None

    def best_giver(self, route, pick, lo, hi, ok):
        if not pick.get("givers"):
            return self.best_place(route, pick["spot"], lo, hi, ok, pick)
        inside = self.timed_inside(route, pick)
        allowed = lambda i, _=0: ok(i) and i not in inside
        best = plansteps.cheapest(route, [s for s, _ in pick["givers"]], lo, hi, self.anchor, node_spot, self.gap, allowed,
                                  self.held_of(route), self.then_of(pick))
        if not best:
            return None
        pick["spot"], pick["step"] = pick["givers"][best[2]]
        return best[1]

    def fit_quest(self, route, q, nodes, lo):
        short = self.skill_short(q)
        if short:
            return self.misfit(q, ("skill", *short))
        if self.timed(q["id"]) and not any(n["kind"] == "dungeon" for n in nodes):
            return self.fit_timed(route, q, nodes, lo)
        run = self.shared_run(route, nodes)
        levels = self.levels(route)
        at = lo
        pick = next((n for n in nodes if n["kind"] == "pickup"), None)
        if pick is not None and pick.get("far"):
            if not self.put_off(route, q, pick):
                return False
            pick = None
        end = lambda: self.far_tail(route) if self.far_held else len(route)
        stop = lambda frm: next((k for k in range(frm, end()) if route[k]["kind"] == "grind"), end())
        top = q.get("maxLevel") or self.cap
        if pick:
            need = waits(pick)
            plo, phi = self.bounds(route, (q["id"], "P"))
            phi = min(phi, self.bounds(route, (q["id"], "T"))[1])
            if run:
                held = self.handed_in(route, run)
                if max(lo, plo) > held:
                    first = max(lo, plo)
                    own = self.needs_run_first(q, route, run)
                    moved = None if own else self.hold_later(route, run, first)
                    if moved is not None:
                        lo = plo = first - moved
                    elif not own and self.pull_earlier(route, q, run):
                        lo = max([i + 1 for i, m in enumerate(route) if m["kind"] == "turnin" and m["quest"] in self.pre_of(q)],
                                 default=0)
                        plo = self.bounds(route, (q["id"], "P"))[0]
                    else:
                        return self.own_run(route, q, run, first)
                    phi = min(self.bounds(route, (q["id"], "P"))[1], self.bounds(route, (q["id"], "T"))[1])
                    held, levels = self.handed_in(route, run), self.levels(route)
                phi = min(phi, held)
            phi = min(phi, end())
            roomy, leveled = self.room_from(route), lambda i: need <= levels[i] <= top
            i = self.best_giver(route, pick, max(lo, plo), phi, lambda i: leveled(i) and roomy[i])
            if i is None and run:
                i = self.grind_to(route, q, pick, max(lo, plo), phi)
            if i is None:
                full = self.best_giver(route, pick, max(lo, plo), phi, leveled) is not None
                return self.misfit(q, ("log",) if full else self.level_stop(levels, max(lo, plo), phi, need, top))
            route.insert(i, pick)
            at = i + 1
        last = at
        tlo, thi = self.bounds(route, (q["id"], "T"))
        after_gets = lambda n, frm: max([frm] + [k + 1 for k, m in enumerate(route) if any(m is g for g in n.get("gets", ()))])
        for_run = [g for n in nodes if n["kind"] == "dungeon" for g in n.get("gets", ())] if run else []
        for n in nodes:
            if n["kind"] == "objective" and n.get("far"):
                if not self.put_off(route, q, n):
                    return False
            elif n["kind"] == "objective":
                ready = self.reach(route, waits(n), at)
                low = max(after_gets(n, at), ready)
                held = self.handed_in(route, run) if any(n is g for g in for_run) else len(route)
                i = self.best_place(route, n["spot"], low, min(stop(ready), thi, held), node=n)
                if i is None:
                    self.unfit(route, q["id"])
                    late = after_gets(n, at) <= min(stop(at), thi, held) and ready > min(stop(ready), thi)
                    return self.misfit(q, ("order",) if not late else ("late", waits(n))
                                       if 1 < waits(n) <= opens_at(q)
                                       else ("fight", n["step"].get("target") or n["step"].get("text"), waits(n)))
                route.insert(i, n)
                last = last + 1 if i < last else i + 1
                thi += 1 if i <= thi else 0
            elif n["kind"] == "dungeon":
                need = waits(n)
                if run:
                    i = next(k for k, m in enumerate(route) if m is run)
                    if pick and i < at and not pick.get("inside") or i < after_gets(n, 0) or self.levels(route)[i] < need:
                        was = i
                        del route[i]
                        at, last = at - (i < at), last - (i < last)
                        low, held = after_gets(n, at), self.handed_in(route, run)
                        run_level(run, q["id"], need)
                        i = self.best_place(route, run["spot"], max(low, self.reach(route, need, 0)),
                                            min(stop(low), held), node=run)
                        if i is None and need:
                            i = self.grind_to(route, q, run, low, min(stop(low), held), need)
                        if i is None:
                            route.insert(was, run)
                            self.unfit(route, q["id"])
                            return self.misfit(q, ("late", need) if self.reach(route, need, low) > held else ("order",))
                        route.insert(i, run)
                    run_level(run, q["id"], need)
                    run["quests"].append(q["id"])
                    run["gets"] = run.get("gets", []) + n.get("gets", [])
                    last = max(last, i + 1)
                else:
                    n.setdefault("quests", []).append(q["id"])
                    low = max(after_gets(n, at), self.reach(route, need, at))
                    i = self.best_place(route, n["spot"], low, stop(low), node=n)
                    if i is None:
                        self.unfit(route, q["id"])
                        return self.misfit(q, ("late", need) if low > len(route) else ("order",))
                    route.insert(i, n)
                    last = max(last, i + 1)
        turn = next(n for n in nodes if n["kind"] == "turnin")
        if turn.get("far"):
            return self.put_off(route, q, turn)
        tlo, thi = self.bounds(route, (q["id"], "T"))
        ready = self.reach(route, waits(turn), last)
        i = self.best_place(route, turn["spot"], max(ready, tlo), min(stop(ready), thi), node=turn)
        if i is None:
            self.unfit(route, q["id"])
            return self.misfit(q, ("late", waits(turn)) if waits(turn) and ready > min(stop(ready), thi) else ("order",))
        route.insert(i, turn)
        return True

    def misfit(self, q, why):
        self.misfits[q["id"]] = why
        return False

    @staticmethod
    def level_stop(levels, lo, hi, need, top):
        there = levels[lo:hi + 1]
        return ("past", top) if there and min(there) > top else ("late", need)

    @staticmethod
    def shared_run(route, nodes):
        n = next((n for n in nodes if n["kind"] == "dungeon"), None)
        return n and next((m for m in route if m["kind"] == "dungeon" and m["dungeon"][0] == n["dungeon"][0]), None)

    @staticmethod
    def handed_in(route, run):
        return next((k for k, m in enumerate(route) if m["kind"] == "turnin" and m["quest"] in run["quests"]
                     and not m.get("inside")), len(route))

    def own_run(self, route, q, run, first):
        chain = self.chain_of(q)
        turned = [m for m in route[:first] if m["kind"] == "turnin" and m["quest"] in run["quests"] and not m.get("inside")]
        late = [m for m in route[self.handed_in(route, run):first] if m["kind"] == "turnin" and m["quest"] in chain
                and m["quest"] in self.late]
        said = lambda ms: names([self.by_id[m["quest"]]["name"] for m in ms])
        mine = [m for m in turned if m["quest"] in chain]
        if mine or not late:
            self.held_back[q["id"]] = own_run_why(said(mine or turned))
        else:
            self.held_back[q["id"]] = (f"you need {said(late)} first, which this plan leaves till last with the group "
                                       "quests, so the quest needs a dungeon run of its own")
        return False

    def chain_of(self, q):
        todo, seen = list(self.pre_of(q)) + [a[0] for a, b in self.links if b == (q["id"], "P")], set()
        while todo:
            p = todo.pop()
            if p in seen:
                continue
            seen.add(p)
            todo += (self.pre_of(self.by_id[p]) if p in self.by_id else []) + [a[0] for a, b in self.links if b == (p, "P")]
        return seen

    def needs_run_first(self, q, route, run):
        outside = {m["quest"] for m in route if m["kind"] == "turnin" and m["quest"] in run["quests"] and not m.get("inside")}
        return bool(outside & self.chain_of(q))

    def hold_later(self, route, run, first):
        moving = [m for m in route[:first] if m["kind"] == "turnin" and m["quest"] in run["quests"] and not m.get("inside")]
        after = route[first - 1]
        trial = [m for m in route if not any(m is x for x in moving)]
        for m in moving:
            lo = next(k for k, x in enumerate(trial) if x is after) + 1
            follow = set(self.book.followups(m["quest"]))
            hi = min([k for k, x in enumerate(trial) if x["kind"] == "pickup" and x["quest"] in follow]
                     + [k for k in range(lo, len(trial)) if trial[k]["kind"] == "grind"], default=len(trial))
            rlo, rhi = self.bounds(trial, (m["quest"], "T"))
            i = self.best_place(trial, m["spot"], max(lo, rlo), min(hi, rhi), node=m)
            if i is None:
                return None
            trial.insert(i, m)
        if not self.feasible(trial):
            return None
        route[:] = trial
        return len(moving)

    def pull_earlier(self, route, q, run):
        held = self.handed_in(route, run)
        before_pickup = lambda x: self.pre_of(self.by_id[x]) + [a[0] for a, b in self.links if b == (x, "P")]
        turned = lambda r, x: next((k for k, m in enumerate(r) if m["kind"] == "turnin" and m["quest"] == x), None)
        moving, todo = set(), before_pickup(q["id"]) if q["id"] in self.by_id else []
        while todo:
            p = todo.pop()
            t = turned(route, p)
            if p in moving or t is None or t < held:
                continue
            if p in run["quests"] or p in self.late or self.timed(p) or \
                    any(m["kind"] == "dungeon" and p in (m.get("quests") or ()) for m in route):
                return False
            moving.add(p)
            if any(m["kind"] == "pickup" and m["quest"] == p for m in route[held:]):
                todo += before_pickup(p)
        if not moving:
            return False
        pulled = [m for m in route[held:] if m.get("quest") in moving]
        trial = route[:held] + [m for m in route[held:] if m.get("quest") not in moving]
        for m in pulled:
            own = [k for k, x in enumerate(trial) if x.get("quest") == m["quest"]]
            if m["kind"] == "pickup":
                lo = max([k + 1 for k, x in enumerate(trial) if x["kind"] == "turnin"
                          and x["quest"] in self.pre_of(self.by_id[m["quest"]])], default=0)
            else:
                lo = max([k + 1 for k in own] + [k + 1 for k, x in enumerate(trial) if any(x is g for g in m.get("gets", ()))],
                         default=0)
            rlo, rhi = self.bounds(trial, (m["quest"], {"pickup": "P", "turnin": "T"}.get(m["kind"], "T")))
            lo = max(lo, rlo if m["kind"] != "objective" else lo)
            hi = min(rhi, self.handed_in(trial, run),
                     next((k for k in range(lo, len(trial)) if trial[k]["kind"] == "grind"), len(trial)))
            i = self.best_place(trial, m["spot"], lo, hi, node=m)
            if i is None:
                return False
            trial.insert(i, m)
        first = max([k + 1 for k, x in enumerate(trial) if x["kind"] == "turnin" and x["quest"] in self.pre_of(q)]
                    + [self.bounds(trial, (q["id"], "P"))[0]])
        if first > self.handed_in(trial, run) or not self.feasible(trial):
            return False
        route[:] = trial
        return True

    def grind_to(self, route, q, node, lo, hi, to=None):
        to = to or (waits(node) if node else offered_at(q))
        if to > self.cap:
            return None
        grind = {"kind": "grind", "to": to, "spot": None, "quest": None}
        i = self.best_place(route, node["spot"], lo, hi, lambda i: self.feasible(route[:i] + [grind, node] + route[i:]),
                            placing=node)
        if i is None:
            return None
        route.insert(i, grind)
        return i + 1

    def fit_timed(self, route, q, nodes, lo):
        pick = next((n for n in nodes if n["kind"] == "pickup"), None)
        rest = [n for n in nodes if n["kind"] == "objective"]
        run, near = [], pick["spot"] if pick else self.anchor
        while rest:
            free = [m for m in rest if not any(g is r for g in m.get("gets", ()) for r in rest)]
            n = min(free, key=lambda m: self.gap(near, m["spot"]) if m["spot"] else 0.0)
            rest.remove(n)
            run.append(n)
            near = n["spot"] or near
        run.append(next(n for n in nodes if n["kind"] == "turnin"))
        need = waits_for(nodes)
        if not pick:
            i = self.reach(route, need, 0)
            if i > len(route):
                return self.misfit(q, ("late", need))
            route[i:i] = run
            return True
        levels, top = self.levels(route), q.get("maxLevel") or self.cap
        load, room = self.log_load(route), self.log_room()
        inside = self.timed_inside(route, pick)
        prev, nxt = self.sides(route)
        steps, places = [pick] + run, []
        held = self.held_of(route)
        for i in range(lo, len(route) + 1):
            if not need <= levels[i] <= top or i in inside or load[i] >= room:
                continue
            walk, at = 0.0, prev[i]
            h0 = h = plansteps.held_at(held, i)
            for n in steps:
                if n["spot"]:
                    walk, at = walk + plansteps.leg(self.gap, at, n["spot"], h), n["spot"]
                h = self.after_node(h, n)
            places.append((walk + (plansteps.leg(self.gap, at, nxt[i], h) - plansteps.leg(self.gap, prev[i], nxt[i], h0)
                                   if nxt[i] else 0.0), i))
        tail = (self.far_tail(route) if self.far_held else len(route)) if any(n.get("far") for n in steps) else None
        if tail is not None:
            gives = [p for p in places if not self.greyed(q, levels[p[1]]) and not self.amid_far(route, p[1])]
            places = sorted(p for p in gives if p[1] >= tail) or sorted((p for p in gives if p[1] < tail), key=lambda p: -p[1])
        over = []
        for _, i in places if tail is not None else sorted(places):
            took = self.clock_s(steps, levels[i])
            if took <= q["limit"]:
                route[i:i] = steps
                for n in steps if tail is not None else ():
                    if i >= tail:
                        n["away"] = self.far_held = True
                    elif self.greyed(q, levels[tail]):
                        n["early"] = q["name"]
                return True
            over.append(took)
        return self.misfit(q, ("clock", q["limit"], min(over)) if over else self.level_stop(levels, lo, len(route), need, top))

    def sides(self, route):
        prev, nxt = [self.anchor], [None] * (len(route) + 1)
        for m in route:
            prev.append(m.get("spot") or prev[-1])
        for k in range(len(route) - 1, -1, -1):
            nxt[k] = route[k].get("spot") or nxt[k + 1]
        return prev, nxt

    def clock_s(self, window, level=None):
        if self.seconds:
            return sum(self.seconds([m["step"] for m in window if m.get("step")], window[0]["spot"], level)[1:])
        at, walked = window[0]["spot"], 0.0
        for m in window[1:]:
            if m.get("spot"):
                walked, at = walked + self.gap(at, m["spot"]), m["spot"]
        return walked / RUN

    def window(self, route, k, hold_late=False):
        return self.window_of(route[:k] + route[k + 1:], route[k], hold_late)

    def put(self, n):
        if n["kind"] == "stop":
            return False
        return n["kind"] not in ("pickup", "objective", "turnin") or self.timed(n["quest"]) or bool(n.get("inside"))

    def window_of(self, rest, n, hold_late=False, passing=False):
        if n["kind"] == "stop":
            return 0, len(rest)
        if self.put(n):
            return None
        q = self.by_id[n["quest"]]
        own = [i for i, m in enumerate(rest) if m.get("quest") == n["quest"] or n["quest"] in (m.get("quests") or ())]
        pre = set(self.pre_of(q))
        lo, hi = 0, len(rest)
        if n["kind"] == "pickup":
            lo = max([i + 1 for i, m in enumerate(rest) if m["kind"] == "turnin" and m["quest"] in pre], default=0)
            hi = min([i for i in own], default=len(rest))
        elif n["kind"] == "objective":
            lo = max([i + 1 for i in own if rest[i]["kind"] == "pickup" or any(rest[i] is g for g in n.get("gets", ()))],
                     default=0)
            hi = min([i for i in own if rest[i]["kind"] == "turnin" or any(n is g for g in rest[i].get("gets", ()))],
                     default=len(rest))
        else:
            lo = max([i + 1 for i in own], default=0)
            after = set(self.book.followups(n["quest"]))
            hi = min([i for i, m in enumerate(rest) if m["kind"] == "pickup" and m["quest"] in after], default=len(rest))
        if n["kind"] != "pickup":
            lo = self.reach(rest, waits(n), lo)
            if not n.get("far"):
                hi = min(hi, next((i for i in range(lo, len(rest)) if rest[i]["kind"] == "grind"), len(rest)))
        rlo, rhi = self.bounds(rest, (n["quest"], {"pickup": "P", "turnin": "T"}.get(n["kind"], "T")))
        lo, hi = max(lo, rlo if n["kind"] != "objective" else lo), min(hi, rhi)
        lo, hi = self.held(rest, n, lo, hi, hold_late, passing)
        if n.get("far") and n["kind"] == "turnin":
            last = self.still_xp(rest, n)
            hi = min(hi, last) if last >= lo else hi
        return (lo, hi) if lo <= hi else None

    def feasible(self, route):
        return next(self.faults(route), None) is None

    def faults(self, route):
        levels = self.levels(route)
        for i, n in enumerate(route):
            if not (waits(n) <= levels[i] and (n["kind"] != "pickup" or levels[i] <= (self.by_id[n["quest"]].get("maxLevel")
                                                                                      or self.cap))
                    and not (n.get("far") and n["kind"] == "turnin" and self.greyed(self.by_id[n["quest"]], levels[i]))):
                yield id(n)
        if max(self.log_load(route)) > self.log_room():
            yield "log"
        at = {(n["quest"], {"pickup": "P", "turnin": "T"}[n["kind"]]): k for k, n in enumerate(route)
              if n["kind"] in ("pickup", "turnin")}
        for a, b in self.links:
            if a in at and b in at and not at[a] < at[b]:
                yield (a, b)

    def polish(self, route, feel=False):
        runs = planunits.runs_at([n.get("spot") for n in route])
        current = self.feel(route)[0] if feel else None
        tried = set()
        for _ in range(POLISH_PASSES):
            better = False
            for k in range(len(route)):
                if route[k]["spot"] is None:
                    continue
                planreport.weighing(route, k)
                trial = self.moved(route, k, runs, feel) or self.led(route, k, tried, feel)
                if trial is None:
                    continue
                if feel:
                    f = self.feel(trial)[0]
                    if f > current + plansteps.TIE:
                        continue
                    current = f
                route[:] = trial
                better = True
            if not better:
                break

    def moved(self, route, k, runs, feel=False):
        n = route[k]
        w = self.window(route, k, hold_late=feel)
        if not w:
            return None
        rest = route[:k] + route[k + 1:]
        here = self.cost(rest, k, n["spot"], n)
        i = self.best_place(rest, n["spot"], w[0], w[1], placing=n)
        if i is None or i == k:
            return None
        least = POLISH_LEAST
        if i > k:
            near = planunits.reach("visit", runs[min(k, len(runs) - 1)] if runs else None)
            prev = plansteps.around(rest, k, self.anchor, node_spot)[0]
            if planunits.apart(prev, n["spot"]) <= near:
                least = max(least, near)
        if self.cost(rest, i, n["spot"], n) > here - least:
            return None
        trial = rest[:i] + [n] + rest[i:]
        return trial if self.feasible(trial) else None

    def led(self, route, k, tried, feel=False):
        n = route[k]
        if n.get("kind") != "objective" or n.get("late") or n.get("inside") or self.timed(n["quest"]):
            return None
        rest = route[:k] + route[k + 1:]
        w = self.window_of(rest, n, hold_late=feel)
        lo = self.reach(rest, waits(n), 0)
        if not w or lo >= w[0]:
            return None
        here = self.cost(rest, k, n["spot"], n)
        best = plansteps.cheapest(rest, [n["spot"]], lo, w[0] - 1, self.anchor, node_spot, self.gap,
                                  held=self.held_of(rest), then=self.then_of(n, n["spot"]))
        if not best or best[0] > here - POLISH_LEAST:
            return None
        p = best[1]
        if (id(n), p and id(rest[p - 1])) in tried:
            return None
        tried.add((id(n), p and id(rest[p - 1])))
        moving, todo = set(), self.needed(rest, n, p)
        while todo:
            m = todo.pop()
            if id(m) in moving:
                continue
            if m["kind"] not in ("pickup", "objective", "turnin") or m.get("late") or m.get("inside") or m.get("maybe") \
                    or self.timed(m["quest"]):
                return None
            moving.add(id(m))
            todo += self.needed(rest, m, p)
        left = next((m for m in reversed(rest[:p]) if id(m) not in moving), None)
        trial = [m for m in rest if id(m) not in moving]
        for m in [m for m in rest if id(m) in moving] + [n]:
            span = self.window_of(trial, m, hold_late=feel)
            if not span:
                return None
            hi = span[1] if m is n else min(span[1], next((j for j, y in enumerate(trial) if y is left), 0))
            i = self.best_place(trial, m["spot"], self.reach(trial, waits(m), span[0]), hi, node=m)
            if i is None:
                return None
            trial.insert(i, m)
        if not self.feasible(trial) or not self.in_order(trial):
            return None
        walk = lambda r: planunits.walk_of([m.get("spot") for m in r], self.gap, self.anchor, self.held_of(r))
        return trial if walk(trial) < walk(route) - POLISH_LEAST else None

    def needed(self, rest, n, p):
        q, kind = n["quest"], n["kind"]
        out = []
        if kind == "pickup":
            by = self.by_id.get(q) or {}
            turned = {m["quest"]: j for j, m in enumerate(rest) if m["kind"] == "turnin" and m.get("quest") is not None}
            for p_ in by.get("preAll", []) + ([by["startsWith"]] if by.get("startsWith") else []):
                if turned.get(p_, -1) >= p:
                    out.append(rest[turned[p_]])
            anys = sorted(turned[a] for a in by.get("preAny", []) if a in turned)
            if anys and anys[0] >= p:
                out.append(rest[anys[0]])
        elif kind == "objective":
            out += [m for m in rest[p:] if m.get("quest") == q and m["kind"] == "pickup" or any(m is g for g in n.get("gets", ()))]
        else:
            out += [m for m in rest[p:] if m.get("quest") == q or q in (m.get("quests") or ())]
        if kind in ("pickup", "turnin"):
            at = {(m["quest"], {"pickup": "P", "turnin": "T"}[m["kind"]]): j for j, m in enumerate(rest)
                  if m["kind"] in ("pickup", "turnin") and m.get("quest") is not None}
            out += [rest[at[a]] for a, b in self.links if b == (q, kind[0].upper()) and at.get(a, -1) >= p]
        return out

    def gather(self, route, feel=False):
        runs = planunits.runs_at([n.get("spot") for n in route])
        got = self.feel(route) if feel else None
        current, past = (got[0], {id(route[m]) for _, m, *_ in got[4]}) if feel else (None, set())
        walk = lambda r: planunits.walk_of([m.get("spot") for m in r], self.gap, self.anchor, self.held_of(r))
        walked, ready = walk(route), self.ready_of(route)
        k = -1 if self.anchor else 0
        while k < len(route):
            if (self.anchor if k < 0 else route[k].get("spot")) is None:
                k += 1
                continue
            planreport.weighing(route, k)
            slack = planunits.reach("slack", runs[min(max(k, 0), len(runs) - 1)] if runs else None)
            end, close = self.visit_of(route, k, runs)
            back, j = self.left_place(route, k, runs), end + 2
            while j < len(route):
                n = route[j]
                if not close(n) and not (ready[j] == k and planunits.behind(back, lambda q: node_reach(n, q))):
                    j += 1
                    continue
                chunk = self.with_place(route, [j], n["spot"], k + 1, ready)
                moving = [route[x] for x in chunk]
                rest = route[:j] + route[chunk[-1] + 1:]
                w = self.window_of(rest, n, hold_late=feel)
                lo, hi = (max(w[0], k + 1), min(w[1], end + 1)) if w else (1, 0)
                i = self.best_place(rest, n["spot"], lo, hi, placing=n) if lo <= hi else None
                trial = rest[:i] + moving + rest[i:] if i is not None else None
                cheap = trial is not None and walk(trial) <= walked + slack
                if trial is None or not (cheap or feel) or not self.feasible(trial) \
                        or (len(moving) > 1 and not self.in_order(trial)):
                    j += 1
                    continue
                undo = None
                if feel:
                    got, bar = self.feel(trial), current + (slack if cheap else -plansteps.TIE)
                    new = sum(c for _, m, c, *_ in got[4] if id(trial[m]) not in past)
                    if got[0] > bar >= got[0] - new:
                        trial, got, undo = self.with_passes(trial)
                    if got[0] > bar:
                        if undo:
                            undo()
                        j += 1
                        continue
                    current, past = got[0], {id(trial[m]) for _, m, *_ in got[4]}
                was, by = (route[k] if k >= 0 else None), {id(m): r for m, r in zip(route, runs)}
                route[:] = trial
                runs[:] = [by[id(m)] for m in route]
                walked, ready = walk(route), self.ready_of(route)
                if undo is None:
                    end += len(moving)
                    j += len(moving)
                    continue
                k = next(x for x, m in enumerate(route) if m is was) if was is not None else -1
                last = max(x for x, m in enumerate(route) if any(m is y for y in moving))
                end = max(self.visit_of(route, k, runs)[0], last)
                back, j = self.left_place(route, k, runs), end + 2
            k += 1

    def left_place(self, route, k, runs):
        if k < 0:
            return []
        vs = planunits.visits([n.get("spot") for n in route], runs)
        v = next((v for v, xs in enumerate(vs) if k in xs), 0)
        return [route[x].get("spot") for x in vs[v - 1]] if v else []

    def with_passes(self, trial):
        chosen = [(m, m["spot"], m["step"]) for m in trial if m.get("givers")]
        trial = list(trial)
        self.pass_givers(trial)

        def undo():
            for m, spot, step in chosen:
                m["spot"], m["step"] = spot, step
        return trial, self.feel(trial), undo

    def visit_of(self, route, k, runs):
        here = self.anchor if k < 0 else route[k].get("spot")
        near = planunits.reach("visit", runs[min(max(k, 0), len(runs) - 1)] if runs else None)
        close = lambda m: here is not None and m.get("spot") is not None and node_reach(m, here) <= near
        end = k
        while end + 1 < len(route) and (route[end + 1].get("spot") is None or close(route[end + 1])):
            end += 1
        return end, close


    def unit_rules(self, route):
        rounds = (lambda: self.pass_givers(route), lambda: self.gather(route, feel=True),
                  lambda: self.polish(route, feel=True), lambda: self.gather(route, feel=True),
                  lambda: self.pass_givers(route))
        for n, run in enumerate(rounds, 1):
            planreport.report("polish", rounds=(n, len(rounds)))
            run()
            planreport.report(ordered=route)

    def log_room(self):
        return max(self.log_most, len(self.log))

    def room_from(self, route):
        load, room = self.log_load(route), self.log_room()
        out, top = [False] * len(load), 0
        for k in range(len(load) - 1, -1, -1):
            top = max(top, load[k])
            out[k] = top < room
        return out

    def log_load(self, route):
        n, out = len(self.log), []
        for m in route:
            out.append(n)
            if m["kind"] == "pickup":
                n += 1
            elif m["kind"] == "turnin" and m.get("quest") is not None:
                n -= 1
        out.append(n)
        return out

    def pass_givers(self, route, floor=0):
        for _ in range(PASS_MOVES):
            feel = self.feel(route)
            for i, m, _, at, s in feel[4]:
                if m < floor:
                    continue
                planreport.weighing(route, m)
                if not self.into_pass(route, i, m, at, s, floor, feel[0]):
                    continue
                break
            else:
                return

    def into_pass(self, route, i, m, at, s, floor, was):
        n, chunk = route[m], self.opened(route, i, m, at, s)
        moving = [route[j] for j in chunk]
        rest = [x for j, x in enumerate(route) if j not in chunk]
        w = self.window_of(rest, n, hold_late=True, passing=True)
        if not w:
            return False
        lo, hi = max(w[0], floor, s), min(w[1], i)
        if lo > hi:
            return False
        was_at = (n["spot"], n["step"])
        n["spot"], n["step"] = next(((sp, st) for sp, st in n.get("givers") or () if sp == at), was_at)

        def ok(k):
            trial = rest[:k] + moving + rest[k:]
            return self.feasible(trial) and (len(moving) == 1 or self.in_order(trial))
        k = self.best_place(rest, at, lo, hi, ok, n)
        trial = rest[:k] + moving + rest[k:] if k is not None else None
        if trial is not None and self.feel(trial)[0] < was - plansteps.TIE:
            route[:] = trial
            for x in moving:
                if x.pop("away", None) and x.get("far"):
                    x.setdefault("early", "pass")
            return True
        n["spot"], n["step"] = was_at
        return False

    def opened(self, route, i, m, at, s):
        ready, givers = self.ready_of(route), self.givers(route)
        hop = director_rules.RUN["hop"].value
        chunk = [j for j in range(i, m) if givers[j] and ready[j] < s and planunits.apart(route[j].get("spot"), at) <= hop]
        chunk.append(m)
        return self.with_place(route, chunk, at, s, ready)

    def with_place(self, route, chunk, at, s, ready):
        hop = director_rules.RUN["hop"].value
        for j in range(chunk[-1] + 1, len(route)):
            m = route[j]
            if planunits.apart(m.get("spot"), at) > hop or not (ready[j] < s or ready[j] in chunk) or self.put(m) \
                    or m.get("late"):
                break
            chunk.append(j)
        return chunk

    def givers(self, route):
        out = []
        for n in route:
            if n["kind"] not in ("pickup", "turnin") or n.get("maybe") or not n.get("spot") \
                    or (n.get("step") or {}).get("group") or self.timed(n["quest"]):
                out.append(None)
            else:
                out.append([n["spot"]] + [sp for sp, _ in n.get("givers") or () if sp != n["spot"]])
        return out

    def ready_of(self, route):
        levels = self.levels(route)
        picked, turned, work, pos = {}, {}, {}, {}
        for k, n in enumerate(route):
            pos[id(n)] = k
            for q in ([n["quest"]] if n.get("quest") is not None else []) + list(n.get("quests") or ()):
                if n["kind"] == "pickup":
                    picked[q] = k
                elif n["kind"] == "turnin":
                    turned[q] = k
                elif n["kind"] in ("objective", "dungeon"):
                    work.setdefault(q, []).append(k)
        at = {**{(q, "P"): k for q, k in picked.items()}, **{(q, "T"): k for q, k in turned.items()}}
        before = {}
        for a, b in self.links:
            before.setdefault(b, []).append(a)
        out = []
        for k, n in enumerate(route):
            kind, q = n["kind"], n.get("quest")
            if kind == "stop":
                out.append(-1)
                continue
            if kind not in ("pickup", "objective", "turnin") or self.timed(q):
                out.append(k - 1)
                continue
            if kind == "pickup":
                r = max([turned.get(p, -1) for p in self.pre_of(self.by_id[q])] + [-1])
            elif kind == "objective":
                r = max([picked.get(q, -1)] + [pos.get(id(g), -1) for g in n.get("gets", ())])
            else:
                r = max([picked.get(q, -1)] + [i for i in work.get(q, ()) if i < k])
            wait = waits(n)
            if wait:
                r = max(r, bisect.bisect_left(levels, wait) - 1)
            if kind != "objective":
                r = max([r] + [at.get(a, -1) for a in before.get((q, kind[0].upper()), ())])
            out.append(min(r, k - 1))
        return out

    def feel(self, route):
        spots = [n.get("spot") for n in route]
        return planunits.feel(spots, self.ready_of(route), [n["kind"] for n in route], self.gap, self.anchor,
                              planunits.runs_at(spots), self.givers(route), ways=self.ways, kept=self.passes,
                              held=self.held_of(route))

    def prune(self, route, plan, waiting):
        if self.follow or not waiting:
            return {}
        placed = {n["quest"] for n in route if n.get("quest") is not None}
        leads = {}
        for w, q in plan.items():
            for p in self.chain_of(q) & placed:
                leads.setdefault(p, set()).add(w)
        wanted, gone = set(self.wanted), {}
        more = True
        while more:
            more = False
            for p, ws in leads.items():
                left = [w for w in ws if w not in placed]
                if p not in gone and p not in wanted and p not in self.log and left and \
                        all(w not in placed or w in gone for w in ws):
                    gone[p] = min(left)
                    more = True
        if not gone:
            return {}
        trial = list(route)
        for p in gone:
            self.unfit(trial, p)
        trial = [n for n in trial if n["kind"] != "dungeon" or n.get("quests")]
        while trial and trial[-1]["kind"] == "grind":
            trial.pop()
        if not self.feasible(trial):
            return {}
        route[:] = trial
        return gone

    def at_runs(self, route):
        for run in [n for n in route if n["kind"] == "dungeon"]:
            key = run["dungeon"][0]
            met = [n for n in route if n.get("inside") and (self.dungeon_of(self.by_id[n["quest"]]) or (None,))[0] == key]
            if not met:
                continue
            rest = [n for n in route if not any(n is m for m in met)]
            k = next(i for i, n in enumerate(rest) if n is run)
            trial = rest[:k] + met + rest[k:]
            if self.feasible(trial) and self.in_order(trial):
                route[:] = trial

    def in_order(self, route):
        at = {}
        for k, n in enumerate(route):
            if n.get("quest") is not None and n["kind"] in ("pickup", "objective", "turnin"):
                at.setdefault((n["quest"], n["kind"]), []).append(k)
        for k, n in enumerate(route):
            if n.get("quest") is None or n["kind"] not in ("pickup", "objective", "turnin"):
                continue
            q = self.by_id.get(n["quest"]) or {}
            if n["kind"] == "pickup":
                before = [(p, "turnin") for p in q.get("preAll", []) + ([q["startsWith"]] if q.get("startsWith") else [])]
                anys = [i for p in q.get("preAny", []) for i in at.get((p, "turnin"), ())]
                if anys and min(anys) >= k:
                    return False
            else:
                before = [(n["quest"], "pickup")] + ([(n["quest"], "objective")] if n["kind"] == "turnin" else [])
            if any(i >= k for b in before for i in at.get(b, ())):
                return False
        return True

    def order(self, plan):
        planreport.report("order")
        route, placed, waiting = [], set(), []
        self.links, self.held_back = self.pairs(plan), {}
        self.late = self.late_quests(plan)
        everything = sorted(plan.values(), key=lambda q: (q["id"] in self.late, opens_at(q), q.get("level") or 0, q["id"]))
        nodes = self.nodes = {q["id"]: self.quest_nodes(q) for q in everything}
        self.look(n for ns in nodes.values() for n in ns)
        for q in everything:
            if q["id"] in self.late:
                for n in nodes[q["id"]]:
                    n["late"] = True
        self.deferred, self.far_held = [], False
        self.mark_far(plan, nodes)
        after = self.after_timed(plan)
        quests = [q for q in everything if q["id"] not in after]
        waiting = self.place_all(route, [q for q in quests if q["id"] not in self.late], placed, plan, nodes)
        self.place_all(route, [q for q in quests if group_work(q, self.mob_rank, self.guards_near)], placed, plan, nodes)
        waiting += self.place_all(route, [q for q in quests if q["id"] in self.late and q["id"] not in placed], placed, plan, nodes)
        dropped = self.place_far(route)
        placed -= {q["id"] for q in dropped}
        waiting += dropped
        self.pruned = self.prune(route, {k: q for k, q in plan.items() if k not in after}, waiting)
        for s in self.stops:
            n = {"kind": "stop", "step": {"quest": None, **s}, "quest": None, "spot": spot_of(s)}
            i = self.best_place(route, n["spot"], 0, len(route), placing=n)
            route.insert(len(route) if i is None else i, n)
        planreport.report(ordered=route)
        self.polish(route)
        self.gather(route)
        planreport.report(ordered=route)
        self.at_runs(route)
        self.camps_again(route)
        self.look(route)
        self.unit_rules(route)
        if after:
            late = self.place_all(route, [q for q in everything if q["id"] in after], placed, plan, nodes)
            dropped = self.place_far(route)
            placed -= {q["id"] for q in dropped}
            late += dropped
            self.pruned.update(self.prune(route, plan, late))
            waiting += late
            self.unit_rules(route)
        running = [n for n in route if n.get("quest") in self.log and self.timed(n["quest"])
                   and waits_for(nodes.get(n["quest"], ())) <= self.level]
        a = self.anchor
        runs = planunits.runs_at([n.get("spot") for n in route])
        run = planunits.runs_at([a] + [n.get("spot") for n in route])[0]
        here = self.visit_of(route, -1, runs)[0] if a else -1
        doing = [n for k, n in enumerate(route) if k <= here and n["kind"] == "objective" and n.get("quest") in self.log
                 and not self.log[n["quest"]] and n.get("spot") and plansteps.here(n["step"], a, run)
                 and self.begun(n) and waits(n) <= self.level and not any(n is r for r in running)]
        doing = [n for n in doing if all(any(g is d for d in doing) for g in n.get("gets", ()))]
        hand = {n["quest"] for n in doing}
        rest = [n for n in route if n["kind"] == "objective" and n.get("quest") in hand and not any(n is d for d in doing)
                and waits(n) <= self.level]
        rest = [n for n in rest if all(any(g is d for d in doing + rest) for g in n.get("gets", ()))]
        doing += rest
        first = {id(n) for n in running + doing}
        route[:] = running + doing + [n for n in route if id(n) not in first]
        if first:
            self.pass_givers(route, floor=len(first))
        planreport.report(ordered=route)
        return route, waiting

    def after_timed(self, plan):
        out = {i for i in plan if self.timed(i) and i not in self.log}
        tied = {}
        for a, b in self.links:
            if a[0] != b[0]:
                tied.setdefault(b[0], set()).add(a[0])
        more = bool(out)
        while more:
            more = False
            for i, q in plan.items():
                if i not in out and (set(self.pre_of(q)) | tied.get(i, set())) & out:
                    out.add(i)
                    more = True
        return out

    def camps_again(self, route):
        near, reckoned = self.anchor, self.levels(route)
        for k, n in enumerate(route):
            if n["kind"] == "objective" and not n["step"].get("game"):
                q = self.by_id[n["quest"]]
                t = self.target_of(q, n["step"])
                s = t and self.objective_at(q, t, near, reckoned[k])
                if s:
                    n["step"], n["spot"] = s, spot_of(s)
            near = n.get("spot") or near

    @staticmethod
    def target_of(q, step):
        if step.get("part") is not None:
            return next((t for t in q.get("targets", []) if t.get("part") == step["part"]), None)
        same = [t for t in q.get("targets", []) if step.get("target") in (t["name"], t.get("title"))
                and step.get("get") == t.get("get")]
        return next((t for t in same if stepwords.objective(q, t, quest_sentence) == step.get("text")), same[0] if same else None)

    def place_all(self, route, pending, placed, plan, nodes):
        tied = {}
        for a, b in self.links:
            if a[0] != b[0]:
                tied.setdefault(b[0], set()).add(a[0])
        for x, before in list(tied.items()):
            for y in list(before):
                if x in tied.get(y, ()):
                    before.discard(y)
                    tied[y].discard(x)
        while pending:
            progress = False
            for q in list(pending):
                pre = [p for p in self.pre_of(q) + list(tied.get(q["id"], ())) if p in plan and p not in placed]
                if pre or q["id"] in self.held_back:
                    continue
                lo = max([i + 1 for i, m in enumerate(route) if m["kind"] == "turnin" and m["quest"] in set(self.pre_of(q))],
                         default=0)
                if q["id"] in self.late and not self.shared_run(route, nodes[q["id"]]):
                    lo = max(lo, max([i + 1 for i, m in enumerate(route) if self.rank(m) < 1], default=0))
                if self.fit_quest(route, q, nodes[q["id"]], lo):
                    placed.add(q["id"])
                    pending.remove(q)
                    progress = True
                    mine = nodes[q["id"]]
                    planreport.report(placed=mine, at=mine and (mine[-1], sum(len(nodes[i]) for i in placed),
                                                                sum(map(len, nodes.values()))) or None)
            if not progress and self.far_fallback(pending, plan, nodes):
                continue
            if not progress:
                ready = [q for q in pending if not [p for p in self.pre_of(q) if p in plan and p not in placed]
                         and q["id"] not in self.held_back and not self.skill_short(q)]
                at = self.far_tail(route) if self.far_held else len(route)
                level = self.levels(route)[at]
                need = min((n for n in (waits_for(nodes[q["id"]]) for q in ready) if n > level), default=None)
                if need is None or need > self.cap:
                    return pending
                route.insert(at, {"kind": "grind", "to": need, "spot": None, "quest": None})
        return []

    def waiting_why(self, waiting, plan, top, ahead=None):
        ids, tied = {q["id"] for q in waiting}, {}
        for a, b in self.links:
            if a[0] != b[0]:
                tied.setdefault(b[0], set()).add(a[0])
        sure = director_rules.said("reckoned", ahead)

        def own(q):
            lv = waits_for(self.nodes[q["id"]]) if q["id"] in self.nodes else opens_at(q)
            return self.held_back.get(q["id"]) or self.skill_said(q) or (
                f"the quest opens at level {lv}, above the game's level cap of {self.cap}" if lv > self.cap
                else f"the quest opens at level {lv}" + (f", and this plan takes you to level {top}" if sure else "")
                if lv > top else None)

        def root(q, seen):
            for p in self.pre_of(q) + sorted(tied.get(q["id"], ())):
                if p in ids and p in plan and p not in seen:
                    r = root(self.by_id[p], seen | {p})
                    if r or own(self.by_id[p]):
                        return r or self.by_id[p]
            return None
        def stopped(q):
            why = self.misfits.get(q["id"]) or ("order",)
            if why[0] == "past":
                return f"the quest closes at level {why[1]}, and the plan passes that level before you can pick it up"
            if why[0] == "late":
                return f"the quest opens at level {why[1]}, and the plan reaches that level only after quests that must come later"
            if why[0] == "fight":
                return f"the {why[1]} suit level {why[2]}, and the plan reaches that level only after the quest is due back"
            if why[0] == "log":
                return f"your quest log is full wherever the plan could pick the quest up ({self.log_room()} quests)"
            if why[0] == "clock":
                return f"the quest gives you {duration(why[1] * 1000)} to finish it, and the plan reckons it takes " \
                       f"{duration(why[2] * 1000)}"
            if tied.get(q["id"]) or any(q["id"] in before for before in tied.values()):
                return "the quest has no place in the order that the quests tied to it need"
            return "the quests that must come before and after it leave it no place in the order"
        out = []
        for q in waiting:
            r = None if self.held_back.get(q["id"]) else root(q, {q["id"]})
            out.append((q, first_needs(r["name"], own(r)) if r else own(q) or stopped(q)))
        return out

    def reasons(self, steps, early=None):
        pickups = {s["quest"]: s for s in steps if s.get("kind") == "pickup"}
        far = lambda a, b: not (a and b) or a[0] != b[0] or math.hypot(a[1] - b[1], a[2] - b[2]) > ELSEWHERE
        towns = self.towns
        visit_reasons(steps, self.zone, towns, early or {}, self.book)
        for k, s in enumerate(steps):
            q = self.by_id.get(s.get("quest"))
            if not q or s.get("kind") not in ("pickup", "turnin", "objective"):
                continue
            here = spot_of(s)
            run = self.dungeon_of(q) if self.dungeon_of else None
            if s["kind"] in ("pickup", "turnin"):
                for bid, pick in pickups.items():
                    b = self.by_id.get(bid)
                    if b and bid != q["id"] and q["id"] in self.pre_of(b) and pick.get("npc") != s.get("npc") \
                            and far(here, spot_of(pick)):
                        stepwords.give(s, "opens", quest=b["name"], npc=pick.get("npc"), place=stepwords.place(pick, towns))
                        break
                g = self.giver(q.get("start" if s["kind"] == "pickup" else "end")) or {}
                if run and g.get("inside"):
                    stepwords.give(s, "within", dungeon=run[1], **({"npc": g.get("name")} if g.get("npc") else {}))
            if s["kind"] == "pickup":
                end = self.giver(q.get("end")) or {}
                turn = next((t for t in steps if t.get("kind") == "turnin" and t.get("quest") == q["id"]), None)
                if not run and not q.get("targets") and end.get("name") and end["name"] in (q.get("objective") or "") and turn:
                    stepwords.give(s, "message", npc=end["name"], place=stepwords.place(turn, towns))
                ts = q.get("targets") or ()
                carried = run and any(q["id"] in (t.get("quests") or ()) for t in steps if t.get("kind") == "dungeon") \
                    and not any(t.get("kind") == "objective" and t.get("quest") == q["id"] for t in steps) \
                    and not (ts and all(t.get("spots") for t in ts))
                if carried:
                    stepwords.give(s, "inside", dungeon=run[1])
                if early_at(steps, k):
                    stepwords.give(s, "early", npc=s.get("npc"))
            if q["id"] in self.late and group_work(q, self.mob_rank, self.guards_near):
                stepwords.give(s, "group")

    def asks_for(self, q):
        return if_offered(q) and (not level_guessed(q) or in_band(q, self.band, self.band_level))

    def maybe_on_the_way(self, route, missing):
        placed = set()
        for q in sorted(missing, key=lambda q: q["id"]):
            maybe = if_offered(q)
            if maybe and not self.asks_for(q):
                continue
            if not (maybe or self.skill_short(q)) or q["id"] in self.log or q["id"] in self.done or \
                    open_to(q, self.side, self.race, self.class_id, self.skills, in_log=False, cap=self.cap, spells=self.spells):
                continue
            turned = {m["quest"]: k for k, m in enumerate(route) if m["kind"] == "turnin"}
            chain = [] if maybe else self.before(q, have=frozenset(turned))[0]
            if chain is None or any(c["id"] not in turned for c in chain):
                continue
            at, who = self.place(q.get("start"))
            if at is None:
                continue
            text = stepwords.pickup(q["name"], who, self.thing(q.get("start")), maybe=maybe)
            step = self.mapped(self.step("pickup", q, text, at, npc=who, min=offered_at(q), **({"maybe": True} if maybe else {}),
                                         face=self.face(self.giver(q.get("start"))), **self.giver_ids(q.get("start"))),
                               q.get("start"))
            if maybe:
                stepwords.give(step, "offer", npc=who, quest=q["name"])
            marked = next((m["step"] for m in route if (m.get("step") or {}).get("giverAt")
                           and plansteps.own_with(m["step"], step)), None)
            if marked:
                step.update(giverAt=[step["inst"], *step["at"][:2]], inst=marked["inst"], at=list(marked["at"]))
            n = {"kind": "pickup", "step": step, "quest": q["id"], "spot": spot_of(step), **({"maybe": True} if maybe else {})}
            levels, roomy = self.levels(route), self.room_from(route)
            fits = lambda i: offered_at(q) <= levels[i] <= (q.get("maxLevel") or self.cap) and roomy[i]
            lo = max([k + 1 for k, m in enumerate(route) if plansteps.own_with(m.get("step") or {}, step)]
                     + [turned[c["id"]] + 1 for c in chain], default=0)
            i = self.best_place(route, n["spot"], lo, len(route), fits, placing=n)
            if i is None or self.cost(route, i, n["spot"], n) > ON_THE_WAY:
                continue
            route.insert(i, n)
            placed.add(q["id"])
        return placed

    def build(self):
        planreport.report("offers")
        plan, later = self.closure()
        planreport.report(finds=planreport.offer_finds(plan.values(), self.log))
        route, waiting = self.order(plan)
        crumbs = self.crumbs_passed(route, plan)
        if crumbs:
            self.passed |= set(crumbs)
            self.wanted += crumbs
            plan, later = self.closure()
            route, waiting = self.order(plan)
        top = self.levels(route)[-1] if route else self.level
        waited = self.waiting_why(waiting, plan, top, ahead=sum(n["kind"] != "grind" for n in route))
        later += waited
        why_of = {q["id"]: why for q, why in waited}
        for p, w in sorted(self.pruned.items()):
            later.append((self.by_id[p], leads_up(self.by_id[w]["name"], why_of.get(w, ""))))
            self.chained.add(p)
        missing = [q for q, why in later if asks_offer(why) and q["id"] not in self.chained]
        short = {q["id"]: self.skill_short(q) for q, _ in waited if self.skill_short(q)}
        on_way = self.maybe_on_the_way(route, list({q["id"]: q for q in missing + [self.by_id[i] for i in short]}.values()))
        steps, near, grinds = [], self.anchor, []
        reckoned = self.levels(route)
        for k, n in enumerate(route):
            if n["kind"] == "grind":
                grinds.append({"before": len(steps), "to": n["to"]})
                continue
            if n["kind"] == "objective" and n["step"].get("inPlace") and not n["step"].get("game"):
                q = self.by_id[n["quest"]]
                t = self.target_of(q, n["step"])
                s = t and self.objective_at(q, t, near, reckoned[k])
                if s and s.get("inPlace") and steps and steps[-1].get("map") and steps[-1].get("inst") == s["inst"]:
                    s["map"] = steps[-1]["map"]
                if s:
                    n["step"] = s
            if n["kind"] == "dungeon":
                key, name, door = n["dungeon"]
                ids = n.get("quests", [])
                names = [self.by_id[i].get("name") or f"quest {i}" for i in ids]
                n["step"] = {"kind": "dungeon", "quest": None, "questName": name, "text": stepwords.run(name),
                             **({"forQuest": stepwords.names(names)} if names else {}),
                             "inst": door[0] if door else None, "at": [round(v, 1) for v in door[1:]] if door else None,
                             "quests": ids, "dungeon": key}
                if ids and all(self.nested_of(self.by_id[i]) for i in ids):
                    own = next((m["dungeon"][1] for m in route if m["kind"] == "dungeon" and m["dungeon"][0] in self.runs), None)
                    n["step"]["nested"] = {"quest": stepwords.names(list(dict.fromkeys(self.leads[i] for i in ids))),
                                           "opener": stepwords.names(names), **({"before": own} if own else {})}
            n["step"]["lv"] = reckoned[k]
            n["step"].pop("leadsTo", None)
            if n["step"].get("quest") in self.leads:
                n["step"]["leadsTo"] = self.leads[n["step"]["quest"]]
            steps.append(n["step"])
            if n["step"].get("at"):
                near = (n["step"]["inst"], *n["step"]["at"][:2])
        parked = [s for s in steps if s["quest"] in self.parked and s["kind"] != "dungeon"]
        aside = {id(s) for s in parked} | {id(s) for s in steps if s.get("maybe") and any(plansteps.own_with(p, s) for p in parked)}
        for g in grinds:
            s = next((s for s in steps[g["before"]:] if id(s) not in aside), None)
            if s:
                s["grind"] = max(s.get("grind") or 0, g["to"])
        steps = [s for s in steps if id(s) not in aside] + [s for s in steps if id(s) in aside]
        for s in steps[len(steps) - len(aside):]:
            s["aside"] = True
        self.reasons(steps, {id(n["step"]): n["early"] for n in route if n.get("early")})
        self.felt = self.feel(route)[0] if route else 0.0
        planreport.report(finds=planreport.step_finds(steps, self.log))
        wanted = [self.by_id[i] for i in dict.fromkeys(self.wanted) if i in self.by_id]
        return {"key": self.d["key"], "name": self.d["name"], "steps": steps, "levelTo": top, "grinds": grinds,
                "quests": [{"id": q["id"], "name": q["name"], "state": self.state(q["id"])}
                           for q in sorted(plan.values(), key=lambda q: (opens_at(q), q["id"]))],
                "later": [{"id": q["id"], "name": q["name"], "why": why,
                           **({"missing": True} if asks_offer(why) and q["id"] not in self.chained else {}),
                           **({"onWay": True} if q["id"] in on_way else {}),
                           **({"skill": list(short[q["id"]]), "skillName": self.book.skills.get(short[q["id"]][0]),
                               **({"inLog": True} if q["id"] in self.log else {})} if q["id"] in short else {})}
                          for q, why in later],
                "maybe": [q["id"] for q in missing if self.asks_for(q) and q["id"] not in self.log and q["id"] not in self.done
                          and not open_to(q, self.side, self.race, self.class_id, self.skills, in_log=False, cap=self.cap,
                                          spells=self.spells)],
                "asked": len(wanted)}


def nothing_inside(q, spots=()):
    starts, ends = q.get("start") or [], q.get("end") or []
    if spots or not starts or not ends or not (q.get("next") or q.get("breadcrumbFor")):
        return False
    if any(not t.get("get") for t in q.get("targets") or ()):
        return False
    if any(g.get("item") or g.get("inside") or g.get("map") is None for g in starts + ends):
        return False
    return not {g.get("name") for g in starts} & {g.get("name") for g in ends}


def dungeon_parts(dungeon, book_, door, to_world, dungeon_of=None):
    door = door or next((p for p in (to_world(e["map"], e["x"], e["y"]) for e in dungeon.get("entrances") or ()) if p), None)
    own = [q["id"] for q in dungeon.get("quests", ())]
    run = (dungeon["key"], dungeon["name"], door)
    spots = {q["id"]: q.get("spots") or () for q in dungeon.get("quests", ())}

    def inside(q):
        if q["id"] in spots:
            return None if nothing_inside(q, spots[q["id"]]) else run
        return dungeon_of(q) if dungeon_of else None
    levels = dungeon.get("levels") or ()
    extra = [q for q in dungeon.get("quests", ()) if q["id"] not in book_.quests]
    return {"wanted": own, "name": f"{dungeon['name']} quest epic", "band": [levels[0], levels[-1]] if levels else None,
            "dungeon_of": inside, "extra": extra, "raids": True, "runs": [dungeon["key"]]}


def dungeon_epic(dungeon, chain, to_world, level, side, class_id, done, log, anchor, door=None, xp=0, race=0, skills=None,
                 dungeon_of=None, **more):
    if not isinstance(chain, QuestBook):
        chain = QuestBook({"quests": {**chain, **{q["id"]: q for q in dungeon.get("quests", ())}}})
    parts = dungeon_parts(dungeon, chain, door, to_world, dungeon_of)
    wanted, name = parts.pop("wanted"), parts.pop("name")
    return QuestPlan(dungeon["key"], name, wanted, chain, to_world, level, xp, side, race, class_id, skills, done, log, anchor,
                     **parts, **more)


def next_in_chains(book_, wanted, done, log, planned, side, race, class_id, skills=None, cap=MAX_LEVEL, spells=None):
    book_ = book_.for_side(side, class_id)
    out, seen = [], set(wanted) | set(planned)
    for qid in wanted:
        for f in book_.followups(qid):
            q = book_.quests.get(f)
            if q and f not in seen and f not in done and f not in log and not open_to(q, side, race, class_id, skills, in_log=False, cap=cap,
                                                                                   spells=spells):
                seen.add(f)
                out.append({"id": f, "name": q["name"]})
    return out


def open_to(q, side, race, class_id, skills=None, *, in_log, cap=MAX_LEVEL, raids=False, needed=False, spells=None):
    if in_log:
        return None
    q = for_side(q, side, class_id)
    why = can_take(q, side, class_id)
    if why:
        return why
    if (q.get("req") or 0) > cap:
        return f"the quest opens at level {q['req']}, above the game's level cap of {cap}"
    if q.get("races") and race and not q["races"] & race:
        return "the quest is for another race"
    skill = q.get("skill")
    if skill and skills is not None and skills.get(skill[0], 0) < (skill[1] if len(skill) > 1 else 1):
        return "the quest needs a profession you don't have"
    why = spell_unmet(q, spells)
    if why:
        return why
    if q.get("repeat") and not needed:
        return "the quest is repeatable"
    if q.get("type") in SKIP_TYPES and not (raids and q["type"] == RAID_TYPE):
        return SKIP_TYPES[q["type"]]
    if q.get("rep"):
        return "the quest needs a reputation with a faction"
    return None


def open_now(q, side, race, class_id, done, log, cap=MAX_LEVEL, spells=None):
    if q["id"] in done or q["id"] in log:
        return False
    if open_to(q, side, race, class_id, None, in_log=False, cap=cap, spells=spells) or closed_by(q, done, log) is not None:
        return False
    return not (q.get("preAll") and not set(q["preAll"]) <= done or q.get("preAny") and not set(q["preAny"]) & done)


def in_band(q, band, level=None):
    top = band[1] if band else level
    return top is None or opens_at(q) <= top + BAND_ABOVE


norm_words = plansteps.norm_words
spot_of = plansteps.spot


def said_fit(said, t):
    want = [norm_words(w) for w in (t.get("text"), t.get("name")) if w]
    return max([len(w) for w in want if w and w in said] + [len(said) for w in want if w and said in w] + [0])


def node_spot(n):
    return n["spot"]


def node_reach(n, p):
    return plansteps.reach_of(n["step"], p) if (n.get("step") or {}).get("at") else planunits.apart(n.get("spot"), p)
