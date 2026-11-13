# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import re
from collections import Counter

import blurbs
import datafiles
from geo import reach_yards
from layers import CAMP_WALK, COVER_STOPS, KILL_REACH, camp_loop, camp_stops, fights_from, loop_tour, polished
import plansteps
import stepwords
from plurals import plural

CLOSE_WALK = 100.0
CLOSE_RADIUS = 700.0
SPAWNS_NEAR = 800.0
SPAWNS_MOST = 400
SAFE_SHARE = 0.5
GAME_SHARE = 0.5
TALKS = ("talk", "interact")
EACH_KINDS = ("talk", "interact", "event", "use")
SPAWN_SPARE = 2
SENTENCE = re.compile(r"(?<=[.!?])\s+")
SPOT_LINK = 60.0
SPOT_WIDE = 40.0
AREA_MOST = 12
PLACES_MOST = 12


_placed = {"key": None, "means": {}}


def placed_means():
    import camping
    cd = camping.load()
    if _placed["key"] is not cd:
        means = {}
        for s, item in cd.made.items():
            n = cd.recipe(s).get("n")
            if n:
                spells, items = means.setdefault(n, (set(), set()))
                spells.add(int(s))
                items.add(int(item))
        _placed.update(key=cd, means=means)
    return _placed["means"]


def placed(t, q):
    if not t.get("objects") or t.get("mobs"):
        return False
    spells, items = placed_means().get(t.get("name"), (set(), set()))
    given = {int(i) for i in q.get("provided") or () if str(i).lstrip("-").isdigit()}
    return bool(given & items) or (q.get("spell") is not None and abs(int(q["spell"])) in spells)


PLACES = datafiles.data_path("quest_places.json")
PLACE_REACH = 60.0
MARKED_NEAR = 300.0
MARKED_PLACE = 2500.0
NEAR_WORDS = re.compile(r"\b(?:near|next to|beside)\b", re.I)


def place_records(qid):
    return (datafiles.load(PLACES, {}).get("quests") or {}).get(str(qid)) or []


def worded(q):
    recs, targets = place_records(q.get("id")), q.get("targets")
    if not recs or not targets:
        return q
    out = []
    for t in targets:
        r = next((r for r in recs if r.get("at") and r.get("target") == t.get("name")
                  and (r["how"] == "whose" and (r.get("thing") or "").casefold() == t["name"].casefold()
                       or r["how"] == "near" and r.get("npc") and t.get("objects") and not t.get("mobs"))), None)
        if not r:
            out.append(t)
        elif r["how"] == "whose":
            words = (r.get("words") or "").strip().rstrip(".")
            out.append({**t, "title": r["phrase"], "place": r["at"], "owned": True,
                        **({"text": words} if words and NEAR_WORDS.search(words) and not t.get("text") else {})})
        else:
            out.append({**t, "place": r["at"]})
    return q if all(a is b for a, b in zip(out, targets)) else {**q, "targets": out}


def each_spawn(t):
    return t["kind"] in EACH_KINDS or (t["kind"] == "loot" and bool(t.get("objects")) and not t.get("mobs"))


def fight_level(t, mob_level):
    if not t.get("mobs") or t.get("friendly") or not mob_level or \
            not (t["kind"] == "kill" or t["kind"] == "loot" and not t.get("objects")):
        return None
    levels = [lv for lv in (mob_level(m) for m in t["mobs"]) if lv]
    return fights_from(min(levels)) if levels else None


def spread_spawns(here, seed, want):
    seen, left = set(), []
    for p in here:
        if (round(p[1]), round(p[2])) not in seen:
            seen.add((round(p[1]), round(p[2])))
            left.append(p)
    taken = [min(left, key=lambda p: math.hypot(p[1] - seed[0], p[2] - seed[1]))]
    left.remove(taken[0])
    while left and len(taken) < want:
        nxt = min(left, key=lambda p: min(math.hypot(p[1] - q[1], p[2] - q[2]) for q in taken))
        left.remove(nxt)
        taken.append(nxt)
    mid = (sum(p[1] for p in taken) / len(taken), sum(p[2] for p in taken) / len(taken))
    if len(taken) < 2 or max(reach_yards(p[1:3], mid) for p in taken) <= KILL_REACH:
        return None
    return taken, mid


def quest_progress(qid, done, log):
    return "done" if qid in done else "ready" if log.get(qid) else "log" if qid in log else "todo"


def walks_alone(st):
    return st.get("kind") == "objective" and not st.get("loop") and len(st.get("spawns") or ()) == 1


def heat_patches(pts):
    n = len(pts)
    root = list(range(n))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) <= SPOT_LINK:
                root[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = [((sum(pts[i][0] for i in g) / len(g), sum(pts[i][1] for i in g) / len(g)), g) for g in groups.values()]
    return sorted(out, key=lambda mg: (-len(mg[1]), mg[0]))


def step_area(spawns):
    pts = [(float(p[0]), float(p[1])) for p in spawns]
    out = []
    for mid, group in heat_patches(pts)[:AREA_MOST]:
        reach = max(math.hypot(pts[i][0] - mid[0], pts[i][1] - mid[1]) for i in group) + SPOT_WIDE
        out.append([round(mid[0], 1), round(mid[1], 1), round(reach)])
    return out


def objective_places(own, inst, spots, areas):
    out = [list(p) for p in own]
    more = [[round(a["at"][1], 1), round(a["at"][2], 1), round(a["r"])] for a in areas or () if a["at"][0] == inst]
    more += step_area([p[1:3] for p in spots if p[0] == inst])
    for p in more:
        if len(out) >= len(own) + PLACES_MOST:
            break
        if not any(math.hypot(p[0] - q[0], p[1] - q[1]) + p[2] <= q[2] for q in out):
            out.append(p)
    return out


def other_places(step, own):
    own = own or []
    return [p for p in step.get("places") or () if p not in own]


def discrete_spots(pts):
    patches = heat_patches(pts)
    return len(patches) >= 2 and all(math.hypot(pts[i][0] - mid[0], pts[i][1] - mid[1]) <= SPOT_WIDE
                                     for mid, g in patches for i in g)


def quest_sentence(q, name):
    said = [s.strip() for s in SENTENCE.split((q.get("objective") or "").strip()) if s.strip()]
    return next((s for s in said if name in s), said[0] if said else name)
GROUP_TYPES = {1}
ELITE_RANKS = {1, 2, 3}
ALONE_KINDS = {"loot", "kill", "talk", "interact", "use"}


def group_work(q, mob_rank=None, guards_near=None):
    if q.get("type") not in GROUP_TYPES:
        return False
    targets = q.get("targets") or []
    if not (mob_rank and guards_near) or not targets or q.get("unplaced"):
        return True
    for t in targets:
        if t.get("kind") not in ALONE_KINDS or not t.get("spots"):
            return True
        ranks = [mob_rank(m) for m in t.get("mobs") or ()]
        if any(r is None or r in ELITE_RANKS for r in ranks):
            return True
        if t["kind"] in ("kill", "loot") and not ranks and not t.get("objects"):
            return True
    return 0 in guards_near([s for t in targets for s in t["spots"]])


MISSING = "is new in Forever and no source says yet what opens it"
UNSEEN = "is new in Forever and no giver has offered it yet"
UNSURE = "has sources that disagree on who starts it"
IF_OFFERED = (MISSING, UNSEEN, UNSURE)
CONFLICT = "conflict"
SINGLE = "single"
CONFIRMED = "confirmed"


def start_in_conflict(q):
    return ((q or {}).get("confidence") or {}).get("start") == CONFLICT


def if_offered(q):
    return bool(q.get("unknown") or q.get("unconfirmed") or start_in_conflict(q))


def level_guessed(q):
    return ((q or {}).get("confidence") or {}).get("level") == SINGLE


def rated(q, book):
    if not book or "confidence" in (q or {}):
        return q
    mine = book.get(q.get("id")) if q else None
    if not mine or "confidence" not in mine:
        return q
    out = {**q, "confidence": mine["confidence"]}
    if mine.get("unconfirmed"):
        out["unconfirmed"] = True
    return out


def asks_offer(why):
    return any(w in (why or "") for w in IF_OFFERED)


QUEST =re.compile(r"\bthe quest\b(?!s)")


def about(why, name):
    return QUEST.sub(lambda _: name, why, count=1)


def first(name, why):
    return f"you need {name} first, and {about(why, name)}"


def own_run(names):
    return f"you hand in {names} first, so the quest needs a dungeon run of its own"


def leads_up(name, why):
    return f"the quest only leads up to {name}, and {about(why, name)}"


def for_side(q, side, class_id=None):
    mine = ((q or {}).get("sides") or {}).get(side)
    if not mine:
        return q
    out = {k: v for k, v in q.items() if k != "sides"}
    by_class = (mine.get("byClass") or {}).get(str(class_id)) or {} if class_id is not None else {}
    for k, v in [*mine.items(), *by_class.items()]:
        if k == "byClass":
            continue
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def spell_name(spell):
    import camping
    return camping.load().recipe(abs(spell)).get("n")


def spell_unmet(q, spells):
    spell = q.get("spell") or 0
    if not spell:
        return None
    name = spell_name(spell)
    if spell < 0:
        if spells is not None and -spell in spells:
            return (f"you already know {name}, and the quest is only offered before you learn it" if name else
                    "you already know the spell or recipe that closes the quest")
        return None
    if spells is None:
        return (f"the quest needs {name}, and the game hasn't shown your spells yet" if name else
                "the quest needs a spell, and the game hasn't shown your spells yet")
    if spell not in spells:
        return f"the quest needs {name}, which you don't know yet" if name else "the quest needs a spell you don't know yet"
    return None


def taken_instead(q, done, log, planned=()):
    return next((x for x in q.get("exclusive") or () if x in done or x in log or x in planned), None)


def closed_by(q, done, log, planned=(), by_id=None):
    name = lambda i: ((by_id or {}).get(i) or {}).get("name") or f"quest {i}"
    other = taken_instead(q, done, log, planned)
    if other is not None:
        whom = next((g["name"] for g in ((by_id or {}).get(other) or {}).get("start") or ()
                     if g.get("name") and not g.get("item")), None)
        took = name(other) + (f" from {whom}" if whom else "")
        return "version", (f"the quest closed when you took {took}" if other in done or other in log
                           else f"the plan takes {took} instead")
    if q.get("until") and q["until"] in done:
        return "until", f"the quest closed when you handed in {name(q['until'])}"
    if q.get("next") and (q["next"] in done or q["next"] in log):
        return "next", f"you already have or have done the follow-up, {name(q['next'])}"
    if q.get("breadcrumbFor") and (q["breadcrumbFor"] in done or q["breadcrumbFor"] in log):
        return "crumb", f"the quest only leads to {name(q['breadcrumbFor'])}, which you already have or have done"
    if q.get("parent") and q["parent"] in done:
        return "parent", f"the quest is part of {name(q['parent'])}, which you have handed in"
    return None


def unavailable(q, done, log, level, by_id=None, planned=()):
    if q["id"] in log:
        return None
    closed = closed_by(q, done, log, planned, by_id)
    if closed and closed[0] == "version":
        return closed[1]
    if q.get("unknown"):
        return f"the quest {MISSING}"
    if start_in_conflict(q):
        return f"the quest {UNSURE}"
    if q.get("unconfirmed"):
        return f"the quest {UNSEEN}"
    if q.get("maxLevel") and level > q["maxLevel"]:
        return f"the quest is only open up to level {q['maxLevel']}"
    if closed:
        return closed[1]
    if q.get("spec") or q.get("ranks") or q.get("maxRep"):
        return "the quest needs a specialisation, profession rank or reputation that the plan can't check"
    return None


def can_take(q, side, class_id):
    if q.get("side") not in (None, "Both", side):
        return "the quest is for the other faction"
    cls = q.get("classes")
    if cls and class_id and not cls & (1 << (class_id - 1)):
        return "the quest is for another class"
    return None


def merged(q, said=None):
    targets = q.get("targets")
    if not targets or len(targets) < 2:
        return q
    out, at = [], {}
    for t in targets:
        key = repr(sorted((k, repr(v)) for k, v in t.items() if k != "count"))
        if key in at:
            out[at[key]].append(t)
        else:
            at[key] = len(out)
            out.append([t])
    if len(out) == len(targets):
        return q

    def logged_apart(ts):
        want = [plansteps.norm_words(w) for w in (ts[0].get("text"), ts[0].get("name")) if w]
        lines = [plansteps.norm_words(line[0]) for line in said or () if line]
        return sum(1 for g in lines if g and any(w and (w in g or g in w) for w in want)) >= len(ts)
    joined = []
    for ts in out:
        if len(ts) == 1 or logged_apart(ts):
            joined.extend(ts)
        else:
            joined.append({**ts[0], "count": sum(t.get("count", 1) for t in ts)})
    return q if len(joined) == len(targets) else {**q, "targets": joined}


def leveled(q, level):
    if not level:
        return q
    rated_ =(q.get("confidence") or {}).get("level")
    if q.get("level") == level and rated_ in (None, CONFIRMED) and (q.get("req") or 0) <= level:
        return q
    out = {**q, "level": level}
    if (q.get("req") or 0) > level:
        out["req"] = level
    if rated_ is not None:
        out["confidence"] = {**q["confidence"], "level": CONFIRMED}
    return out


def counted(q, said):
    targets = q.get("targets") if said else None
    if not targets:
        return q
    out = list(targets)
    for words, count in said:
        longest, at = 0, None
        for i, t in enumerate(out):
            for name in (plansteps.norm_words(w) for w in (t.get("text"), t.get("name")) if w):
                if name and name in words and len(name) > longest:
                    longest, at = len(name), i
        if at is not None and count and out[at].get("count", 1) != count:
            out[at] = {**out[at], "count": count}
    return q if out == targets else {**q, "targets": out}


def logged(q, said):
    targets = q.get("targets") if said else None
    if not targets:
        return q
    out = list(targets)
    for i, t in enumerate(out):
        if t.get("get") or t.get("kind") not in ("kill", "loot", "use", "talk", "interact", "event"):
            continue
        line = plansteps.said_for(t, said)
        kind = line and plansteps.said_kind(line[0], t.get("name"), line[2] if len(line) > 2 else None)
        if kind and kind != t["kind"] and any(t.get(k) for k in plansteps.SAID_FITS[kind]):
            out[i] = {**t, "kind": kind}
    return q if out == targets else {**q, "targets": out}


def opened(q, offered):
    if if_offered(q) and q["id"] in offered:
        out = {k: v for k, v in q.items() if k not in ("unknown", "unconfirmed")}
        if start_in_conflict(out):
            out["confidence"] = {**out["confidence"], "start": "confirmed"}
        return out
    return q


class Epic:
    def __init__(self, dungeon, chain, to_world, level, side, class_id, done, log, anchor, door=None, parked=(),
                 faces=None, close=False, spawns_of=None, danger_of=None, mob_level=None, counts=None, offered=(),
                 with_gets=None, objectives=None, book=None, heights_of=None, levels=None, zone_side=None):
        counts, offered, said, levels = counts or {}, set(offered), objectives or {}, levels or {}
        gets = with_gets or (lambda q: q)
        mine = [gets(worded(opened(logged(counted(merged(leveled(for_side(rated(q, book), side, class_id), levels.get(q["id"])),
                                                         said.get(q["id"])), counts.get(q["id"])), said.get(q["id"])), offered)))
                for q in dungeon.get("quests", [])]
        if any(a is not b for a, b in zip(mine, dungeon.get("quests", []))):
            dungeon = {**dungeon, "quests": mine}
        self.d, self.to_world, self.faces, self.close = dungeon, to_world, faces, close
        self.chain = {k: gets(worded(opened(logged(counted(merged(leveled(for_side(rated(q, book), side, class_id), levels.get(k)),
                                                                  said.get(k)), counts.get(k)), said.get(k)), offered)))
                      for k, q in chain.items()}
        self.spawns_of, self.danger_of, self.mob_level, self.heights_of = spawns_of, danger_of, mob_level, heights_of
        self.zone_side = zone_side
        self.level, self.side, self.class_id = level, side, class_id
        self.done, self.log, self.anchor, self.door = set(done), dict(log), anchor, door
        self.parked = set(parked)
        self.by_id = {**self.chain, **{q["id"]: q for q in dungeon.get("quests", [])}}


    def allowed(self, q, needed=False, have=()):
        raise NotImplementedError("questplan.QuestPlan.allowed is the one rule of who can take a quest")

    def before(self, q, seen=frozenset(), have=frozenset()):
        if q["id"] in seen or q["id"] in self.log:
            return [], None
        seen = seen | {q["id"]}
        order = []
        for p in q.get("preAll", []) + ([q["startsWith"]] if q.get("startsWith") and q["startsWith"] not in self.log else []):
            pq = self.by_id.get(p)
            if p in self.done or not pq:
                continue
            why = self.allowed(pq, True, have)
            if why:
                return None, first(pq["name"], why)
            sub, why = self.before(pq, seen, have)
            if sub is None:
                return None, why
            order += sub + [pq]
        anys = [p for p in q.get("preAny", []) if p in self.by_id]
        if anys and not any(p in self.done for p in q.get("preAny", [])):
            options, why_not = [], None
            for p in anys:
                pq = self.by_id[p]
                why = self.allowed(pq, True, have)
                if why:
                    why_not = why_not or first(pq["name"], why)
                    continue
                sub, why = self.before(pq, seen, have)
                if sub is None:
                    why_not = why_not or why
                    continue
                options.append(sub + [pq])
            if not options:
                return None, why_not or "you can't take any of the quests that lead up to the quest"
            mine = set(have) | set(self.log)
            order += min(options, key=lambda o: (sum(x["id"] not in mine for x in o), len(o)))
        out, have = [], set()
        for x in order:
            if x["id"] not in have:
                have.add(x["id"])
                out.append(x)
        return out, None


    def place(self, givers):
        for g in givers or []:
            if g.get("map") is not None:
                at = self.to_world(g["map"], g["x"], g["y"])
                if at:
                    return ((*at, g["z"]) if g.get("z") is not None else at), g["name"]
        return None, (givers[0]["name"] if givers else None)

    def giver(self, givers):
        on_map = (g for g in givers or [] if g.get("map") is not None and self.to_world(g["map"], g["x"], g["y"]))
        return next(on_map, (givers or [None])[0])

    def thing(self, givers):
        g = self.giver(givers) or {}
        return bool(g.get("object")) and not g.get("npc")

    def giver_ids(self, givers):
        g = self.giver(givers) or {}
        return {"npcId": g["npc"]} if g.get("npc") else {"objectId": g["object"]} if g.get("object") else {}

    def face(self, giver=None, mobs=()):
        if not self.faces:
            return None
        if giver is not None:
            return self.faces.face(giver=giver)
        return next((f for f in (self.faces.face(npc=m) for m in mobs) if f), None)

    def step(self, kind, q, text, at=None, **more):
        zone = more.pop("zone", None)
        if kind == "turnin":
            more = {"cash": (q.get("rewards") or {}).get("money") or None, "crumb": q.get("breadcrumbFor"), **more}
        if kind == "pickup":
            anys = q.get("preAny") or []
            more = {"pre": (q.get("preAll") or []) + ([q["startsWith"]] if q.get("startsWith") else []) or None,
                    "any": None if any(p in self.done for p in anys) else anys or None, "par": q.get("parent"),
                    "dis": q.get("disabledBy"), "until": q.get("until"), "limit": q.get("limit"),
                    "req": q.get("req"), **more}
        line = blurbs.line(q["id"])
        return stepwords.said({
            "kind": kind, "quest": q["id"], "questName": q["name"], "text": text,
            **({"blurb": line} if line else {}),
            "inst": at[0] if at else None, "at": [round(v, 1) for v in at[1:]] if at else None,
            **({"zone": zone} if zone else {}),
            **({"group": True} if q.get("type") in GROUP_TYPES else {}),
            **{k: v for k, v in more.items() if v is not None}}, text)

    def mapped(self, step, givers=None, spots=None):
        if not step or not step.get("at"):
            return step
        g = self.giver(givers) if givers is not None else None
        if g and g.get("map") is not None and self.to_world(g["map"], g["x"], g["y"]):
            step["map"] = g["map"]
            if g.get("zone"):
                step.setdefault("zone", g["zone"])
        elif spots:
            n, w = step["at"][0], step["at"][1]
            best = min(((s, self.to_world(*s)) for s in spots), key=lambda sw: math.hypot(sw[1][1] - n, sw[1][2] - w)
                       if sw[1] and sw[1][0] == step["inst"] else math.inf)
            if best[1] and best[1][0] == step["inst"]:
                step["map"] = best[0][0]
        return step

    def spawned(self, q, t, level):
        if not self.spawns_of:
            return []
        every = [(*p[:3], ("npc", m), p[3]) for m in t.get("mobs") or () for p in self.spawns_of("npc", m)] + \
                [(*p[:3], ("object", o), p[3]) for o in t.get("objects") or () for p in self.spawns_of("object", o)]
        pool = [p for p in every if q.get("zone") and p[4] == q["zone"]] or every
        if self.zone_side and self.side:
            pool = [p for p in pool if self.zone_side(p[4]) in (None, self.side)] or pool
        if t["kind"] == "loot" and self.mob_level:
            pool = [p for p in pool if p[3][0] != "npc" or fights_from(self.mob_level(p[3][1]) or 0) <= level] or pool
        return [p[:4] for p in pool]

    @staticmethod
    def marked_place(spots, marks):
        for m in reversed(marks or ()):
            by = lambda p, reach: p[0] == m[0] and math.hypot(p[1] - m[1], p[2] - m[2]) <= reach
            if any(by(p, MARKED_NEAR) for p in spots):
                return [p for p in spots if by(p, MARKED_PLACE)]
        return []

    def objective(self, q, t, near, level=None, loop=True, areas=None, marks=None):
        level = level or self.level
        if placed(t, q):
            return self.in_place(q, t, near)
        found = self.spawned(q, t, level)
        spots = found or [(*p, None) for p in (self.to_world(m, x, y) for m, x, y in t["spots"]) if p]
        named, there = t.get("place") and self.to_world(*t["place"]), []
        if named:
            there = [p for p in spots if p[0] == named[0] and math.hypot(p[1] - named[1], p[2] - named[2]) <= PLACE_REACH]
            if there:
                spots = there
            elif t.get("owned"):
                return self.at_owner(q, t, named)
        if not spots:
            return None
        at_mark = self.marked_place(spots, marks)
        if at_mark:
            spots, near = at_mark, near if near and near[0] == at_mark[0][0] else at_mark[0][:3]
        sources = there or [p for p in (self.to_world(m, x, y) for m, x, y in t["spots"]) if p]
        if self.close:
            near = self.place(q.get("start"))[0] or self.place(q.get("end"))[0] or near
        inst = (near or spots[0])[0]
        here = [p for p in spots if p[0] == inst] or [p for p in spots if p[0] == spots[0][0]]
        inst = here[0][0]
        least = 4
        if self.close and near and near[0] == inst:
            close_by = [p for p in here if math.hypot(p[1] - near[1], p[2] - near[2]) <= CLOSE_RADIUS]
            if len(close_by) >= 2:
                here, least = close_by, 2
        title = t.get("title") or t["name"]
        text = stepwords.objective(q, t, quest_sentence)
        camp, at, stops, each, taken, area = None, None, None, False, [], False
        start = near[1:3] if near and near[0] == inst else None
        here, game = self.in_game_areas(here, areas, start, least, CLOSE_WALK if self.close else CAMP_WALK)
        if not here:
            return None
        if t["kind"] in ("kill", "loot", "use"):
            pts = [(p[1], p[2], 1.0, p[3]) for p in here]
            walk = CLOSE_WALK if self.close else CAMP_WALK
            camp = camp_loop(pts, start, least=least, walk_halves=walk, line=True, route=False)
            danger = self.danger_of(inst, level, [p[1:3] for p in here]) if camp and self.danger_of and found and t["kind"] != "use" else None
            safe = danger is not None and len(danger) and camp_loop(pts, start, danger, least=least, walk_halves=walk, line=True,
                                                                     route=False)
            if safe and safe[4] >= SAFE_SHARE * camp[4]:
                camp = safe
            if camp:
                at, area = (inst, camp[1], camp[2]), not discrete_spots([p[1:3] for p in camp[0]])
                stops = camp_stops(camp[0], start, line=True) if loop and not area else None
        if t.get("count", 1) > 1 and each_spawn(t):
            want = min(len(here), max(t["count"], min(SPAWN_SPARE * t["count"], COVER_STOPS)))
            spread = spread_spawns(here, camp[1:3] if camp else start or here[0][1:3], want)
            if spread and discrete_spots([p[1:3] for p in spread[0]]):
                taken, each, area = spread[0], True, False
                tour = polished(loop_tour([p[1:3] for p in taken], start or spread[1]), loop=True)
                at, stops = at or (inst, *tour[0]), tour if loop else None
                camp = (taken,)
            elif spread:
                taken, area, stops = spread[0], True, None
                at = at or (inst, *spread[1])
                camp = (taken,)
        if not at:
            at = min(here, key=lambda p: math.hypot(p[1] - near[1], p[2] - near[2]) if near and near[0] == p[0] else 0)[:3]
        kept = sorted((p for p in here if math.hypot(p[1] - at[1], p[2] - at[2]) <= SPAWNS_NEAR),
                      key=lambda p: math.hypot(p[1] - at[1], p[2] - at[2]))[:SPAWNS_MOST] or here[:1]
        kept = taken + [p for p in kept if p not in taken]
        whose = {k: t[k] for k in ("mobs", "objects") if t.get(k)}
        if found:
            in_camp, round_it = Counter(p[3] for p in (camp[0] if camp else ())), Counter(p[3] for p in kept)
            order = sorted(round_it, key=lambda k: (-in_camp[k], -round_it[k]))
            whose = {k: [i for kind, i in order if kind == ("npc" if k == "mobs" else "object")] for k in ("mobs", "objects")}
            whose = {k: v for k, v in whose.items() if v}
        more = {"target": title, "count": t.get("count", 1), "objective": t["kind"],
                **({"things": plural(t["name"], blurbs.line(q["id"]) or "", t.get("count"))}
                   if len(q.get("targets") or ()) > 1 else {}),
                **({"talk": True} if t["kind"] in TALKS else {}), **({"get": t["get"]} if t.get("get") else {}),
                **({"getItems": list(t["items"])} if t.get("get") and t.get("items") else {}),
                **({"getAny": True} if t.get("get") and t.get("items") and t.get("any") else {}),
                **({"friendly": True} if t.get("friendly") else {}),
                **({"npc": t["names"][str(whose["mobs"][0])]} if t.get("names") and whose.get("mobs")
                   and str(whose["mobs"][0]) in t["names"] else {}),
                "spawns": self.spawn_spots(inst, kept, whose.get("mobs") or ()),
                "face": self.face(mobs=whose.get("mobs") or ()), **whose}
        if area:
            more["area"] = True
        more.update(game or {})
        more["places"] = objective_places(step_area(more["spawns"]), inst, sources, areas)
        if stops:
            more["loop"] = [[round(s[0], 1), round(s[1], 1)] for s in stops]
            if each:
                more["each"] = True
        return self.mapped(self.step("objective", q, text, at, **more), spots=t["spots"])

    @staticmethod
    def in_game_areas(here, areas, start, least, walk):
        areas = [a for a in areas or () if here and a["at"][0] == here[0][0]]
        if not areas:
            return here, None
        main = [a for a in areas if a.get("main")] or areas[:1]

        def inside(p, of):
            return any(math.hypot(p[1] - a["at"][1], p[2] - a["at"][2]) <= a["r"] for a in of)
        in_main = [p for p in here if inside(p, main)]
        pick = in_main or [p for p in here if inside(p, areas)]
        mid = [round(main[0]["at"][1], 1), round(main[0]["at"][2], 1)]
        if not pick:
            return [], None
        if len(pick) < len(here):
            pts = lambda ps: [(p[1], p[2], 1.0, p[3] if len(p) > 3 else None) for p in ps]
            ours = camp_loop(pts(here), start, least=least, walk_halves=walk, line=True, route=False)
            theirs = camp_loop(pts(pick), start, least=min(least, len(pick)), walk_halves=walk, line=True, route=False)
            if ours and (not theirs or theirs[4] < GAME_SHARE * ours[4]) \
                    and not inside((None, ours[1], ours[2]), areas):
                return here, {"gameArea": "ours", "gameAt": mid}
        return pick, {"gameArea": "main" if in_main else "other"}

    def spawn_spots(self, inst, kept, mobs):
        flat = [(round(p[1], 1), round(p[2], 1)) for p in kept]
        placed = self.heights_of(inst, flat, mobs) if self.heights_of and mobs and flat else [(n, w, math.nan) for n, w in flat]
        return [[n, w] + ([round(z, 1)] if math.isfinite(z) else []) for n, w, z in placed]

    def in_place(self, q, t, near):
        at = near or self.place(q.get("start"))[0] or self.place(q.get("end"))[0]
        if not at:
            return None
        text = stepwords.objective(q, t, quest_sentence)
        return self.step("objective", q, text, at[:3], target=t["name"], count=t.get("count", 1), objective=t["kind"],
                         inPlace=True)

    def at_owner(self, q, t, at):
        title = t.get("title") or t["name"]
        step = self.step("objective", q, stepwords.objective(q, t, quest_sentence), at[:3], target=title,
                         count=t.get("count", 1), objective=t["kind"], owner=True)
        step["map"] = t["place"][0]
        return step

    def left_out(self, qid, t):
        return False

    def wants_gets(self, q):
        if self.log.get(q["id"]):
            return False
        own = [t for t in q.get("targets", []) if not t.get("get")]
        return not own or not all(self.left_out(q["id"], t) for t in own)

    def state(self, qid):
        return quest_progress(qid, self.done, self.log)

    gap = staticmethod(plansteps.gap)
