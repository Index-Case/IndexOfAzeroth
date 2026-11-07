# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

import coretrip
import epic
import hearth
import store

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "classquests.json")
KEY = "class:"
_kept = {}


def chains(path=DATA):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    have = _kept.get(path)
    if not have or have[0] != mtime:
        _kept[path] = (mtime, list((store.load_json(path, {}) or {}).get("chains") or ()))
    return _kept[path][1]


def by_id(chain_id, path=DATA):
    every = chains(path)
    return next((c for c in every if c.get("id") == chain_id), None) or \
        next((c for c in every if any(s.get("id") == chain_id for s in c.get("steps") or ())), None)


def for_you(opening, side, race):
    if opening.get("side") not in (None, "Both", side):
        return False
    mask = opening.get("races") or 0
    return not mask or not race or bool(mask & race)


def taught_by(chain, opening):
    mine = set(opening.get("quests") or ())
    return {u["quest"] for u in chain.get("unlocks") or () if u.get("quest") in mine}


def openings(chain, class_id, side, race, done, cap=60, log=(), planned=()):
    if chain.get("class") != class_id or (chain.get("level") or 1) > cap:
        return []
    every = chain.get("openings") or ()
    if any(taught_by(chain, o) and taught_by(chain, o) <= done for o in every):
        return []
    steps = {s["id"]: s for s in chain.get("steps") or ()}

    def shut(o):
        path = set(o.get("quests") or ())
        held, have, plan_ = set(done) - path, set(log) - path, set(planned) - path
        return any(epic.taken_instead(steps.get(q) or {}, held, have, plan_) is not None
                   for q in path - set(done) - set(log))
    return [o for o in every if for_you(o, side, race) and not shut(o) and not set(o.get("quests") or ()) <= done]


def breadcrumbs(chain):
    ids = {s["id"] for s in chain.get("steps") or ()}
    return {s["id"] for s in chain.get("steps") or () if s.get("breadcrumbFor") in ids}


def quests_of(chain, opening, log):
    crumbs = breadcrumbs(chain)
    return [q for q in opening.get("quests") or () if q not in crumbs or q in log]


def mechanic_part(chain, opening, quests):
    teach = taught_by(chain, opening)
    last = max((k for k, q in enumerate(quests) if q in teach), default=None)
    return list(quests) if last is None else list(quests[:last + 1])


def first_givers(chain, quests):
    first = next((s for s in chain.get("steps") or () if quests and s["id"] == quests[0]), None)
    return [(g["map"], g["x"], g["y"]) for g in (first or {}).get("start") or () if g.get("map") is not None]


def nearness(walk, spot_of, at):
    if not (walk and spot_of and at):
        return None
    travel = getattr(walk, "travel", walk)

    def near(c, quests):
        spots = [spot_of(*g) for g in first_givers(c, quests)]
        return min((travel(at, s) for s in spots if s), default=None)
    return near


def pick(chain, mine, log, near=None, done=()):
    if not mine:
        return None
    shared = set.intersection(*(set(o.get("quests") or ()) for o in mine))
    options = [(o, quests_of(chain, o, log)) for o in mine]
    for held in (set(log), set(done)):
        on = [(o, q) for o, q in options if (set(o.get("quests") or ()) - shared) & held]
        if on:
            options = on
            break
    if near and len(options) > 1:
        timed = [(near(chain, q), k) for k, (_, q) in enumerate(options)]
        known = [t for t in timed if t[0] is not None]
        if known:
            return options[min(known)[1]]
    return options[0]


def open_chains(all_chains, class_id, side, race, done, cap=60, kind="mechanic", log=(), planned=()):
    out = []
    for c in all_chains:
        if c.get("kind") != kind:
            continue
        mine = openings(c, class_id, side, race, done, cap, log, planned)
        if mine:
            out.append((c, mine))
    return sorted(out, key=lambda x: (x[0].get("level") or 1, x[0]["id"]))


def unlock_words(chain, opening=None):
    mine = taught_by(chain, opening) if opening else None
    ups = [u for u in chain.get("unlocks") or () if mine is None or u.get("quest") in mine]
    named = [u for u in ups if u.get("shown")] or ups
    names = list(dict.fromkeys(u["name"] for u in named if u.get("name")))
    if not names:
        return ""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def title(chain, opening=None):
    names = {s["id"]: s.get("name") for s in chain.get("steps") or ()}
    mine = set(opening.get("quests") or ()) | {opening.get("quest")} if opening else None
    taught = [u["quest"] for u in chain.get("unlocks") or () if mine is None or u.get("quest") in mine]
    first = opening.get("quest") if opening else next(iter(names), None)
    return next((names[q] for q in [*reversed(taught), first] if names.get(q)), None) or chain.get("name") or ""


def opening_of(chain, quests):
    want = set(quests or ())
    held = sorted(((len(want & set(o.get("quests") or ())), k) for k, o in enumerate(chain.get("openings") or ())),
                  reverse=True)
    if not held or not held[0][0] or (len(held) > 1 and held[1][0] == held[0][0]):
        return None
    return chain["openings"][held[0][1]]


def taken_up_at(chain, quests, opens=None):
    L = int(chain.get("level") or 1)
    return max(L, opens(quests[0]) or L) if opens and quests else L


def offers(all_chains, class_id, side, race, done, log, level, ahead, cap=60, near=None, opens=None):
    out = []
    for c, mine in open_chains(all_chains, class_id, side, race, done, cap, log=log):
        o, quests = pick(c, mine, log, near, done)
        quests = [q for q in quests if q not in done]
        lv = taken_up_at(c, quests, opens)
        if lv > level + ahead:
            continue
        out.append({"c": c["id"], "n": title(c, o), "lv": lv, "u": unlock_words(c, o), "q": quests})
    return out


def plan(steps, start, me, all_chains, table, chain_plan, walk=None, spot_of=None, cap=60, opens=None):
    steps = [dict(s) for s in steps]
    done, log = set(me.get("done") or ()), set(me.get("log") or ())
    level, into = me.get("level") or 1, float(me.get("xp") or 0)
    planned = {s["quest"] for s in steps if s.get("quest") is not None}
    for chain, mine in open_chains(all_chains, me.get("classId"), me.get("side"), me.get("race") or 0, done, cap, log=log,
                                   planned=planned):
        before, need = coretrip.xp_through(steps, table, level, into, cap)

        def place(L):
            want = need(L)
            d = -1 if want <= 0 else next((k for k in range(len(steps)) if before[k + 1] >= want), None)
            if d is None:
                return None
            e = max(coretrip.at_hand(steps, start), coretrip.unit_end(steps, d, hearth.spot(steps[d])) if d >= 0 else -1)
            return e, coretrip.last_spot(steps, e, start)
        earliest = place(min(taken_up_at(chain, [q for q in mechanic_part(chain, o, quests_of(chain, o, log)) if q not in done],
                                         opens) for o in mine))
        if earliest is None:
            continue
        o, quests = pick(chain, mine, log, nearness(walk, spot_of, earliest[1]), done)
        quests = [q for q in mechanic_part(chain, o, quests) if q not in done]
        L = taken_up_at(chain, quests, opens)
        got = place(L)
        if not quests or got is None:
            continue
        e, at = got
        sub = chain_plan(chain, quests, at, max(level, L)) or []
        if not sub:
            continue
        ids = set(quests) | {s["quest"] for s in sub if s.get("quest") is not None}
        ids |= {q for other in chain.get("openings") or () if other is not o for q in other.get("quests") or ()} \
            - set(o.get("quests") or ())
        ids |= {s["quest"] for s in steps if s.get("crumb") in ids and s.get("quest") is not None}
        keep = [k for k, s in enumerate(steps) if s.get("quest") not in ids or s.get("kind") == "errand"]
        kept = set(keep)
        e -= sum(1 for k in range(e + 1) if k not in kept)
        rest = [steps[k] for k in keep]
        block = [{**dict(s), "cq": chain["id"]} for s in sub]
        first = next((hearth.spot(s) for s in block if hearth.spot(s)), None)
        trips, later = town_trips(rest, e, block[0].get("map"), table, level, into, cap, L)
        if later != e:
            e, at = later, coretrip.last_spot(rest, later, start)
        took = [k for k in (coretrip.on_way(rest, e, at, first, walk) if walk else []) if k not in trips]
        gone = set(trips) | set(took)
        steps = [s for k, s in enumerate(rest[:e + 1]) if k not in gone] + [rest[k] for k in took] + \
            [rest[k] for k in trips] + block + [s for k, s in enumerate(rest) if k > e and k not in gone]
    return steps


def town_trips(steps, e, town, table, level, into, cap, L):
    if town is None:
        return [], e
    runs, k = [], 0
    while k <= e and k < len(steps):
        if steps[k].get("map") != town:
            k += 1
            continue
        j = k
        while j + 1 <= e and j + 1 < len(steps) and steps[j + 1].get("map") == town:
            j += 1
        if k > 0 and j < e:
            runs.append((k, j))
        k = j + 1
    out, want = [], coretrip.xp_through((), table, level, into, cap)[1](L)
    for a, b in runs:
        gone = set(out) | set(range(a, b + 1))
        got, at = 0.0, e
        if want > 0:
            at = None
            for i, st in enumerate(steps):
                if i in gone:
                    continue
                got += float(st.get("xp") or 0)
                if got >= want:
                    at = i
                    break
            if at is None:
                continue
            at = max(e, coretrip.unit_end(steps, at, hearth.spot(steps[at])))
        mine = {steps[i].get("quest") for i in range(a, b + 1)} - {None}
        if any(steps[i].get("quest") in mine or mine & set((steps[i].get("pre") or []) + (steps[i].get("any") or [])
                                                            + [steps[i].get("par"), steps[i].get("crumb")])
               for i in range(b + 1, at + 1) if i not in gone):
            continue
        out += list(range(a, b + 1))
        e = at
    return out, e
