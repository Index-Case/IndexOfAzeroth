# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import re

import numpy as np

import director_rules
import planreport
import planunits
import store
from epic import Epic, GROUP_TYPES, asks_offer, can_take, fight_level, if_offered, for_side, leads_up, level_guessed, taken_instead, \
    unavailable, first as first_needs, objective_places, own_run as own_run_why, placed, spell_unmet
from epicwatch import names
import plansteps
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
LOG_MOST = 20
ON_THE_WAY = 60.0
RAID_TYPE = 62
SKIP_TYPES = {41: "the quest is a PvP quest", RAID_TYPE: "the quest is for a raid"}
NOT_YOURS = re.compile(r"^the quest is for (the other faction|another class|another race)$")
KINDS = {"pickup": 0, "objective": 1, "dungeon": 1, "turnin": 2}
WALK_MARGIN = 1.3
FLY = 28.0
FLIGHT_COST = 15.0


def flight_travel(nodes, hops, known, speed=RUN, flying=FLY):
    mine = [n for n in nodes if n["id"] in known]
    if len(mine) < 2:
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

    def travel(a, b):
        walk, flown = math.hypot(a[1] - b[1], a[2] - b[2]) * WALK_MARGIN, fly(a, b)
        return walk if flown is None else min(walk, flown)
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


class QuestPlan(Epic):
    def __init__(self, key, name, wanted, book_, to_world, level, xp, side, race, class_id, skills, done, log, anchor,
                 parked=(), faces=None, follow=False, kill_xp=None, mob_level=None, bags=(), dungeon_of=None,
                 band=None, travel=None, close=False, objectives=None, pois=None, spawns_of=None, danger_of=None,
                 counts=None, rested=0, inside=(), cap=MAX_LEVEL, offered=(), with_gets=None, extra=(), stops=(),
                 raids=False, found_in=None, runs=(), spells=None, log_most=None, closed=None, kept=(),
                 heights_of=None, ways=None, levels=None, seconds=None):
        book_ = book_.for_side(side, class_id)
        super().__init__({"key": key, "name": name, "quests": list(extra)}, book_.quests, to_world, level, side, class_id,
                         done, log, anchor, None, parked, faces, close, spawns_of=spawns_of, danger_of=danger_of,
                         mob_level=mob_level, counts=counts, offered=offered, with_gets=with_gets, objectives=objectives,
                         book=book_.quests if extra else None, heights_of=heights_of, levels=levels)
        self.book, self.follow, self.stops = book_, follow, list(stops)
        self.band_of = "zone" if key.startswith("zone:") else "dungeon"
        self.zone = int(key[5:]) if key.startswith("zone:") and key[5:].isdigit() else None
        self.wanted = list(wanted) + self.lead_ins(wanted)
        self.xp_now, self.race, self.skills = xp or 0, race or 0, skills or {}
        self.spells = None if spells is None else set(spells)
        self.xp_to_next = xp_table()
        self.kill_xp, self.mob_level, self.bags = kill_xp, mob_level, set(bags)
        self.rested, self.inside, self.cap = rested or 0, set(inside), cap
        self.dungeon_of, self.band, self.travel, self.ways, self.seconds = dungeon_of, band, travel, ways, seconds
        self.raids, self.found_in = raids, found_in
        self.log_most = log_most or LOG_MOST
        self.closed = dict(closed or {})
        self.shut_epic = next((k for k in runs if k in self.closed), None)
        self.runs = set(runs) - set(self.closed)
        self.runs_made = set(self.runs)
        self.runs_lone = set()
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

    def gap(self, a, b):
        if self.travel and a and b and a[0] == b[0]:
            return self.travel(a, b)
        return Epic.gap(a, b)


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
        starts = q.get("start") or []
        if any(g.get("map") is not None for g in starts):
            return None
        if self.start_item(q) or self.joins(q):
            return None
        items = [g for g in starts if g.get("item")]
        run = self.met_inside(q)
        if run and len(items) < len(starts):
            return f"the quest starts inside {run[1]}, where this plan doesn't take you"
        if run:
            item = next(g for g in items if self.found_in(g["item"], run))
            return f"the quest starts from {item['name']}, which you find inside {run[1]}, where this plan doesn't take you"
        if items:
            return f"the quest starts from {items[0]['name']}, which you don't have"
        return "the giver of the quest isn't on any map"

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
        run = self.met_inside(q)
        return bool(run) and run[0] in self.runs_made

    def start_item(self, q):
        items = [g for g in q.get("start") or () if g.get("item")]
        mine = next((g for g in items if g["item"] in self.bags), None)
        if mine or not items or not self.found_in or not self.joins(q):
            return mine
        run = self.dungeon_of(q)
        return next((g for g in items if self.found_in(g["item"], run)), None)

    def closure(self):
        self.runs_made = set(self.runs)
        if self.dungeon_of:
            plan, _ = self.taken()
            makers = (q for i, q in plan.items() if not self.log.get(i))
            self.runs_made |= {run[0] for run in map(self.dungeon_of, makers) if run} - self.runs_lone
        plan, later = self.taken()
        planreport.report(picked=plan, crumbs=self.passed)
        return plan, later

    def taken(self):
        plan, later, seen = {}, [], set()
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
            if not why and qid not in self.log and not in_band(q, self.band):
                why = f"the quest opens at level {opens_at(q)}, well above the {self.band_of}'s levels of {self.band[0]}-{self.band[1]}"
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
                    self.startable(q) or not in_band(q, self.band):
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
        past = planunits.walked_past(spots + [g[0] for _, g, _ in crumbs], [-1] * (n + len(crumbs)),
                                     [None] * n + [g for _, g, _ in crumbs], runs + [runs[-1]] * len(crumbs),
                                     self.anchor, self.gap, every=True, ways=self.ways)
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
        for p in q.get("preAll", []) + ([q["startsWith"]] if q.get("startsWith") else []):
            if p not in self.done and p in self.by_id:
                out += self.lead_up(self.by_id[p], seen, known) + [self.by_id[p]]
        anys = [p for p in q.get("preAny", []) if p in self.by_id]
        if anys and not any(p in self.done for p in q.get("preAny", [])):
            out += min((self.lead_up(self.by_id[p], seen, known) + [self.by_id[p]] for p in anys),
                       key=lambda c: (bool(self.allowed(c[-1], True)), len(c)))
        known[q["id"]] = list({x["id"]: x for x in out}.values())
        return known[q["id"]]


    @staticmethod
    def pre_of(q):
        return q.get("preAll", []) + q.get("preAny", []) + ([q["startsWith"]] if q.get("startsWith") else [])

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
        late = {i for i, q in plan.items() if q.get("type") in GROUP_TYPES}
        after = {i: set(self.pre_of(q)) for i, q in plan.items()}
        for a, b in self.links:
            after[b[0]].add(a[0])
        more = True
        while more:
            more = {i for i, before in after.items() if i not in late and before & late}
            late |= more
        return late

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
            if item:
                text = f"Use {item['name']} to start {q['name']}"
            else:
                text = f"Pick up {q['name']}" + (f" from {who}" if who else "")
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
                s = self.step("objective", q, "; ".join(words), mark, target=words[0], count=1, game=True, map=on)
                if opens_at(q) > 1:
                    s["min"] = opens_at(q)
                nodes.append({"kind": "objective", "step": s, "kills": None})
        if inside and not self.log.get(q["id"]):
            for t in q.get("targets", []) if need_items else ():
                s = t.get("get") and self.objective_at(q, t, near, loop=False)
                if s:
                    nodes.append({"kind": "objective", "step": s, "kills": self.kills_of(t, s)})
            nodes.append(run_level({"kind": "dungeon", "dungeon": inside, "works": {q["id"]: opens_at(q)}}))
        nodes.append({"kind": "turnin", "step": self.mapped(self.step("turnin", q, f"Turn in {q['name']}" + (f" to {who_end}" if who_end else ""),
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
            step = self.mapped(self.step("pickup", q, f"Pick up {q['name']}" + (f" from {who}" if who else ""), at, npc=who,
                                         min=offered_at(q), face=self.face(g), **self.giver_ids([g])), [g])
            out.append((spot_of(step), step))
        return out

    def marked(self, q):
        mark = (self.pois.get(q["id"]) or {}).get("obj")
        if not mark:
            return None, False
        targets = [t for t in q.get("targets", []) if not t.get("get") and not placed(t, q) and not self.left_out(q["id"], t)]

        def closest(t):
            return min((math.hypot(p[1] - mark[1], p[2] - mark[2]) for p in (self.to_world(*s) for s in t["spots"])
                        if p and p[0] == mark[0]), default=math.inf)
        return mark, bool(targets) and all(closest(t) > OBJECTIVE_FAR for t in targets)

    def objective_at(self, q, t, near, level=None, loop=True):
        mark, wrong = (None, False) if t.get("get") or placed(t, q) or t.get("owned") else self.marked(q)
        areas = self.game_areas(q, t) if mark else []
        s = None if wrong else self.objective(q, t, mark or near, level, loop, areas)
        if s is None and (wrong or areas):
            at = next((a["at"] for a in areas if a.get("main")), mark)
            s = self.step("objective", q, t.get("text") or t["name"], at, target=t["name"], count=t.get("count", 1),
                          objective=t["kind"], game=True, map=((self.pois.get(q["id"]) or {}).get("maps") or {}).get("obj"),
                          places=objective_places([], at[0], [], areas))
        fight, work = s and fight_level(t, self.mob_level), opens_at(q)
        if s and (fight or work > 1):
            s["min"] = max(fight or 0, work)
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


    def cost(self, route, i, spot):
        if spot is None:
            return 0.0
        return plansteps.added(route, i, spot, self.anchor, node_spot, self.gap)

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

    def best_place(self, route, spot, lo, hi, ok=None, node=None):
        inside = self.timed_inside(route, node)
        allowed = lambda i, _=0: not ((ok and not ok(i)) or i in inside)
        if spot is None:
            return next((i for i in range(lo, hi + 1) if allowed(i)), None)
        best = plansteps.cheapest(route, [spot], lo, hi, self.anchor, node_spot, self.gap, allowed)
        return best[1] if best else None

    def best_giver(self, route, pick, lo, hi, ok):
        if not pick.get("givers"):
            return self.best_place(route, pick["spot"], lo, hi, ok, pick)
        inside = self.timed_inside(route, pick)
        allowed = lambda i, _=0: ok(i) and i not in inside
        best = plansteps.cheapest(route, [s for s, _ in pick["givers"]], lo, hi, self.anchor, node_spot, self.gap, allowed)
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
        stop = lambda frm: next((k for k in range(frm, len(route)) if route[k]["kind"] == "grind"), len(route))
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
            if n["kind"] == "objective":
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
        i = self.best_place(route, node["spot"], lo, hi, lambda i: self.feasible(route[:i] + [grind, node] + route[i:]))
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
        runs = planunits.runs_at([n.get("spot") for n in route])
        reach = [planunits.reach("giver", runs[min(p, len(runs) - 1)] if runs else None) for p in range(len(route) + 1)]
        firsts = [self.passes(route, n, prev, nxt, reach, inside) for n in run]
        windows, off_way = [], False
        for i in range(lo, len(route) + 1):
            if not need <= levels[i] <= top or i in inside or load[i] >= room:
                continue
            at, last = pick["spot"] or prev[i], i
            added, places = plansteps.detour(prev[i], pick["spot"], nxt[i], self.gap) if pick["spot"] else 0.0, [i]
            for n, first in zip(run, firsts):
                here = plansteps.detour(at, n["spot"], nxt[last], self.gap) if n["spot"] else 0.0
                p = last if here <= reach[last] else first[last + 1] if last + 1 < len(first) else None
                if p is None:
                    break
                added += here if p == last else plansteps.detour(prev[p], n["spot"], nxt[p], self.gap)
                places.append(p)
                at, last = n["spot"] or at, p
            else:
                held = route[i:last]
                if max(load[i:last + 1]) >= room or any(m["kind"] in ("grind", "dungeon") or (
                        m.get("quest") not in (None, q["id"]) and self.timed(m["quest"])) for m in held):
                    continue
                windows.append((added, i, places))
                continue
            off_way = True
        over, steps = [], [pick] + run
        for added, i, places in sorted(windows, key=lambda w: (w[0], w[1])):
            trial = list(route)
            for j in sorted(range(len(steps)), key=lambda j: (places[j], j), reverse=True):
                trial.insert(places[j], steps[j])
            start = next(k for k, m in enumerate(trial) if m is pick)
            end = next(k for k, m in enumerate(trial) if m is run[-1])
            took = self.clock_s(trial[start:end + 1], levels[i])
            if took <= q["limit"]:
                route[:] = trial
                return True
            over.append(took)
        why = ("clock", q["limit"], min(over)) if over else ("way",) if off_way \
            else self.level_stop(levels, lo, len(route), need, top)
        return self.misfit(q, why)

    def sides(self, route):
        prev, nxt = [self.anchor], [None] * (len(route) + 1)
        for m in route:
            prev.append(m.get("spot") or prev[-1])
        for k in range(len(route) - 1, -1, -1):
            nxt[k] = route[k].get("spot") or nxt[k + 1]
        return prev, nxt

    def passes(self, route, n, prev, nxt, reach, inside):
        out, found = [None] * (len(route) + 2), None
        for p in range(len(route), -1, -1):
            if p not in inside and (not n["spot"] or plansteps.detour(prev[p], n["spot"], nxt[p], self.gap) <= reach[p]):
                found = p
            out[p] = found
        return out

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

    def window_of(self, rest, n, hold_late=False):
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
            hi = min(hi, next((i for i in range(lo, len(rest)) if rest[i]["kind"] == "grind"), len(rest)))
        rlo, rhi = self.bounds(rest, (n["quest"], {"pickup": "P", "turnin": "T"}.get(n["kind"], "T")))
        lo, hi = max(lo, rlo if n["kind"] != "objective" else lo), min(hi, rhi)
        if n.get("late"):
            lo = max(lo, max([i + 1 for i, m in enumerate(rest) if not m.get("late")], default=0))
        elif hold_late:
            late = [i for i, m in enumerate(rest) if m.get("late")]
            if late and not any(not m.get("late") for m in rest[late[0]:]):
                hi = min(hi, late[0])
        return (lo, hi) if lo <= hi else None

    def feasible(self, route):
        levels = self.levels(route)
        if not all(waits(n) <= levels[i] and (n["kind"] != "pickup" or levels[i] <= (self.by_id[n["quest"]].get("maxLevel")
                                                                                     or self.cap))
                   for i, n in enumerate(route)):
            return False
        if max(self.log_load(route)) > self.log_room():
            return False
        at = {(n["quest"], {"pickup": "P", "turnin": "T"}[n["kind"]]): k for k, n in enumerate(route)
              if n["kind"] in ("pickup", "turnin")}
        return all(at[a] < at[b] for a, b in self.links if a in at and b in at)

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
        here = self.cost(rest, k, n["spot"])
        i = self.best_place(rest, n["spot"], w[0], w[1])
        if i is None or i == k:
            return None
        least = POLISH_LEAST
        if i > k:
            near = planunits.reach("visit", runs[min(k, len(runs) - 1)] if runs else None)
            prev = plansteps.around(rest, k, self.anchor, node_spot)[0]
            if planunits.apart(prev, n["spot"]) <= near:
                least = max(least, near)
        if self.cost(rest, i, n["spot"]) > here - least:
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
        here = self.cost(rest, k, n["spot"])
        best = plansteps.cheapest(rest, [n["spot"]], lo, w[0] - 1, self.anchor, node_spot, self.gap)
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
        walk = lambda r: planunits.walk_of([m.get("spot") for m in r], self.gap, self.anchor)
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
        walk = lambda r: planunits.walk_of([m.get("spot") for m in r], self.gap, self.anchor)
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
                i = self.best_place(rest, n["spot"], lo, hi) if lo <= hi else None
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
        w = self.window_of(rest, n, hold_late=True)
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
            if waits(n):
                r = max(r, next((i for i in range(len(levels)) if levels[i] >= waits(n)), k) - 1)
            if kind != "objective":
                r = max([r] + [at.get(a, -1) for a in before.get((q, kind[0].upper()), ())])
            out.append(min(r, k - 1))
        return out

    def feel(self, route):
        spots = [n.get("spot") for n in route]
        return planunits.feel(spots, self.ready_of(route), [n["kind"] for n in route], self.gap, self.anchor,
                              planunits.runs_at(spots), self.givers(route), ways=self.ways)

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
        for q in everything:
            if q["id"] in self.late:
                for n in nodes[q["id"]]:
                    n["late"] = True
        after = self.after_timed(plan)
        quests = [q for q in everything if q["id"] not in after]
        waiting = self.place_all(route, [q for q in quests if q["id"] not in self.late], placed, plan, nodes)
        self.place_all(route, [q for q in quests if q.get("type") in GROUP_TYPES], placed, plan, nodes)
        waiting += self.place_all(route, [q for q in quests if q["id"] in self.late and q["id"] not in placed], placed, plan, nodes)
        self.pruned = self.prune(route, {k: q for k, q in plan.items() if k not in after}, waiting)
        for s in self.stops:
            n = {"kind": "stop", "step": {"quest": None, **s}, "quest": None, "spot": spot_of(s)}
            i = self.best_place(route, n["spot"], 0, len(route))
            route.insert(len(route) if i is None else i, n)
        planreport.report(ordered=route)
        self.polish(route)
        self.gather(route)
        planreport.report(ordered=route)
        self.at_runs(route)
        self.camps_again(route)
        self.unit_rules(route)
        if after:
            late = self.place_all(route, [q for q in everything if q["id"] in after], placed, plan, nodes)
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
        same = [t for t in q.get("targets", []) if step.get("target") in (t["name"], t.get("title"))
                and step.get("get") == t.get("get")]
        return next((t for t in same if t.get("text") == step.get("text")), same[0] if same else None)

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
                    lo = max(lo, max([i + 1 for i, m in enumerate(route) if not m.get("late")], default=0))
                if self.fit_quest(route, q, nodes[q["id"]], lo):
                    placed.add(q["id"])
                    pending.remove(q)
                    progress = True
                    mine = nodes[q["id"]]
                    planreport.report(placed=mine, at=mine and (mine[-1], sum(len(nodes[i]) for i in placed),
                                                                sum(map(len, nodes.values()))) or None)
            if not progress:
                ready = [q for q in pending if not [p for p in self.pre_of(q) if p in plan and p not in placed]
                         and q["id"] not in self.held_back and not self.skill_short(q)]
                level = self.levels(route)[-1]
                need = min((n for n in (waits_for(nodes[q["id"]]) for q in ready) if n > level), default=None)
                if need is None or need > self.cap:
                    return pending
                route.append({"kind": "grind", "to": need, "spot": None, "quest": None})
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
            if why[0] == "way":
                return "the quest is timed, and the plan picks up a timed quest only when it's going that way anyway"
            if tied.get(q["id"]) or any(q["id"] in before for before in tied.values()):
                return "the quest has no place in the order that the quests tied to it need"
            return "the quests that must come before and after it leave it no place in the order"
        out = []
        for q in waiting:
            r = None if self.held_back.get(q["id"]) else root(q, {q["id"]})
            out.append((q, first_needs(r["name"], own(r)) if r else own(q) or stopped(q)))
        return out

    def asks_for(self, q):
        return if_offered(q) and (not level_guessed(q) or in_band(q, self.band))

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
            text = f"Pick up {q['name']}" + (f" from {who}" if who else "") + (", if offered" if maybe else "")
            step = self.mapped(self.step("pickup", q, text, at, npc=who, min=offered_at(q), **({"maybe": True} if maybe else {}),
                                         face=self.face(self.giver(q.get("start"))), **self.giver_ids(q.get("start"))),
                               q.get("start"))
            marked = next((m["step"] for m in route if (m.get("step") or {}).get("giverAt")
                           and plansteps.own_with(m["step"], step)), None)
            if marked:
                step.update(giverAt=[step["inst"], *step["at"][:2]], inst=marked["inst"], at=list(marked["at"]))
            n = {"kind": "pickup", "step": step, "quest": q["id"], "spot": spot_of(step), **({"maybe": True} if maybe else {})}
            levels, roomy = self.levels(route), self.room_from(route)
            fits = lambda i: offered_at(q) <= levels[i] <= (q.get("maxLevel") or self.cap) and roomy[i]
            lo = max([k + 1 for k, m in enumerate(route) if plansteps.own_with(m.get("step") or {}, step)]
                     + [turned[c["id"]] + 1 for c in chain], default=0)
            i = self.best_place(route, n["spot"], lo, len(route), fits)
            if i is None or self.cost(route, i, n["spot"]) > ON_THE_WAY:
                continue
            route.insert(i, n)
            placed.add(q["id"])
        return placed

    def lone_runs(self, route):
        return {n["dungeon"][0] for n in route if n["kind"] == "dungeon" and n.get("quests")
                and n["dungeon"][0] not in self.runs and all(self.met_inside(self.by_id[i]) for i in n["quests"])}

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
        lone = self.lone_runs(route)
        while lone:
            self.runs_lone |= lone
            plan, later = self.closure()
            route, waiting = self.order(plan)
            lone = self.lone_runs(route) - self.runs_lone
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
                n["step"] = {"kind": "dungeon", "quest": None, "questName": name, "text": f"Do {name}: " + ", ".join(names),
                             "inst": door[0] if door else None, "at": [round(v, 1) for v in door[1:]] if door else None,
                             "quests": ids, "dungeon": key}
            n["step"]["lv"] = reckoned[k]
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


def in_band(q, band):
    return not band or opens_at(q) <= band[1] + BAND_ABOVE


norm_words = plansteps.norm_words
spot_of = plansteps.spot


def said_fit(said, t):
    want = [norm_words(w) for w in (t.get("text"), t.get("name")) if w]
    return max([len(w) for w in want if w and w in said] + [len(said) for w in want if w and said in w] + [0])


def node_spot(n):
    return n["spot"]


def node_reach(n, p):
    return plansteps.reach_of(n["step"], p) if (n.get("step") or {}).get("at") else planunits.apart(n.get("spot"), p)
