# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import stepwords

CAST = 20.0
COOLDOWN = 3600.0
LEAST = 30.0
BIND_NEAR = 250.0
HORIZON = 2 * COOLDOWN
BIND_LEAST = 60.0
TALK = 10.0
FLY = 28.0


def spot(step):
    return (step["inst"], step["at"][0], step["at"][1]) if step and step.get("at") and step.get("inst") is not None else None


def inn_spot(inn):
    return inn["map"], inn["at"][0], inn["at"][1]


def bound_inn(inns, bind):
    return next((i for i in inns if bind and bind in (i.get("binds") or ())), None)


def walk_in(s, prev, walk):
    here = spot(s)
    if not (here and prev):
        return 0.0
    h = s.get("hearth") or {}
    return CAST + walk(tuple(h["spot"]), here) if h.get("p") and h.get("spot") else walk(prev, here)


def busy_of(steps, start, walk):
    out, prev = [], start
    for s in steps:
        out.append(max(0.0, float(s.get("sec") or 0) - walk_in(s, prev, walk)))
        prev = spot(s) or prev
    return out


def clock_of(steps, start, walk):
    travel = getattr(walk, "travel", walk)
    clock, prev, t = [], start, 0.0
    for s in steps:
        here = spot(s)
        clock.append(t)
        t += (travel(prev, here) if (here and prev) else 0.0) + s.get("_busy", 0.0)
        prev = here or prev
    clock.append(t)
    return clock


def candidates(steps, start, walk, binds, lo=0, hi=None):
    travel = getattr(walk, "travel", walk)
    hi = len(steps) if hi is None else hi
    out, prev = [], start
    for k, s in enumerate(steps[:hi]):
        here = spot(s)
        if here and prev and k >= lo and binds[k] is not None and s.get("what") != "bind":
            inn = inn_spot(binds[k])
            way_in = travel(prev, here)
            soonest = math.hypot(inn[1] - here[1], inn[2] - here[2]) / FLY if inn[0] == here[0] else 0.0
            if way_in - CAST - soonest >= LEAST:
                saving = way_in - (CAST + travel(inn, here))
                if saving >= LEAST:
                    out.append((k, saving, binds[k]))
        prev = here or prev
    return out


def pick(cands, clock, left, cooldown=COOLDOWN, fixed=()):
    n, must = len(cands), set(fixed)
    best, back = [None] * n, [None] * n
    for i in range(n):
        k, s, _ = cands[i]
        options = []
        if clock[k] >= left - 1e-6 and not any(m < i for m in must):
            options.append((s, None))
        for j in range(i):
            if best[j] is not None and clock[k] - clock[cands[j][0]] - cands[j][1] >= cooldown - 1e-6 \
                    and not any(j < m < i for m in must):
                options.append((best[j] + s, j))
        if options:
            best[i], back[i] = max(options, key=lambda o: (o[0], -1 if o[1] is None else -o[1]))
    ends = [i for i in range(n) if best[i] is not None and not any(m > i for m in must)]
    if not ends:
        return pick(cands, clock, left, cooldown) if must else ([], 0.0)
    i = max(ends, key=lambda e: (best[e], -e))
    total, chosen = best[i], []
    while i is not None:
        chosen.append(i)
        i = back[i]
    chosen.reverse()
    return chosen, total


def bind_timeline(steps, inns, first):
    out, now = [], first
    for s in steps:
        out.append(now)
        if s.get("kind") == "errand" and s.get("what") == "bind":
            names = (s.get("need") or {}).get("bind") or ()
            names = set(names if isinstance(names, list) else [names])
            now = next((i for i in inns if set(i.get("binds") or ()) & names), now)
    out.append(now)
    return out


def saved(steps, start, walk, binds, ready, cooldown, lo=0, hi=None, fixed=()):
    clock = clock_of(steps, start, walk)
    cands = candidates(steps, start, walk, binds, lo, hi)
    chosen, total = pick(cands, clock, ready, cooldown, [c for c, (k, _, _) in enumerate(cands) if k in fixed])
    return total, cands, chosen


def ready_at(steps, start, walk, binds, left, cooldown, k):
    clock = clock_of(steps, start, walk)
    _, cands, chosen = saved(steps, start, walk, binds, left, cooldown, 0, k)
    if not chosen:
        return max(left, clock[k])
    last = cands[chosen[-1]]
    return max(clock[k], clock[last[0]] + last[1] + cooldown)


def bind_step(inn, keeper):
    name, p = keeper
    where = inn["names"][0]
    return {"kind": "errand", "what": "bind", "key": f"bind:{where}", "quest": None, "questName": f"Set your hearth at {name} in {where}",
            "text": f"Set your hearth at {name} in {where}", "npc": name, "inst": p[0],
            "at": [round(p[1], 1), round(p[2], 1)] + ([round(p[3], 1)] if len(p) > 3 and p[3] is not None else []),
            "need": {"bind": list(inn["binds"])}, **({"map": int(p[4])} if len(p) > 4 and p[4] else {}), "_busy": TALK}


def towns(inns):
    return {"near": BIND_NEAR, "list": [[i["names"][0], i["map"], round(i["at"][0], 1), round(i["at"][1], 1)]
                                        for i in inns or () if i.get("names") and i.get("at")]}


def visits(steps, inns):
    out, was = [], None
    for k, s in enumerate(steps):
        here = spot(s)
        if not here or s.get("kind") == "errand":
            continue
        near = [(math.hypot(here[1] - i["at"][0], here[2] - i["at"][1]), n) for n, i in enumerate(inns) if i["map"] == here[0]]
        near = [x for x in near if x[0] <= BIND_NEAR]
        at = inns[min(near)[1]] if near else None
        if at is not None and at is not was:
            out.append((k, at))
        was = at
    return out


def area_end(hubs, gone):
    if not hubs or hubs[0][1]["names"][0] not in gone:
        return 0
    there = hubs[0][1]
    return next((k for k, inn in hubs if inn is not there and inn["names"][0] not in gone), math.inf)


def plan(steps, start, walk, inns, bind, left, cooldown=COOLDOWN, keepers=None, gone=()):
    steps = [dict(s) for s in steps]
    for s, b in zip(steps, busy_of(steps, start, walk)):
        s["_busy"] = b
    fixed = {id(s) for s in steps if (s.get("hearth") or {}).get("core")}
    for s in steps:
        s.pop("hearth", None)
        stepwords.drop(s, ("bind", "hearth"))
    if bind and left is not None:
        first, gone = bound_inn(inns, bind), set(gone)
        k_from = 0
        while keepers:
            binds = bind_timeline(steps, inns, first)
            hubs = visits(steps, inns)
            out_at = area_end(hubs, gone)
            core_at = max([k for k, s in enumerate(steps) if id(s) in fixed] + [-1])
            nxt = next(((k, inn) for k, inn in hubs if k >= max(k_from, out_at) and k > core_at and inn is not binds[k]
                        and inn["names"][0] not in gone and inn["names"][0] in keepers), None)
            if nxt is None:
                break
            k, inn = nxt
            clock = clock_of(steps, start, walk)
            hi = next((j for j in range(k, len(steps)) if clock[j] > clock[k] + HORIZON), len(steps))
            ready = ready_at(steps, start, walk, binds, left, cooldown, k)
            keep = saved(steps, start, walk, binds, ready, cooldown, k, hi)[0]
            moved = binds[:k] + [inn] * (len(binds) - k)
            gain = saved(steps, start, walk, moved, ready, cooldown, k, hi)[0] - keep
            name, place = keepers[inn["names"][0]]
            prev = next((spot(s) for s in reversed(steps[:k]) if spot(s)), start)
            at, here = (place[0], place[1], place[2]), spot(steps[k])
            cost = TALK + ((walk(prev, at) + walk(at, here) - walk(prev, here)) if prev else 0.0)
            if gain - cost >= BIND_LEAST:
                steps.insert(k, bind_step(inn, (name, place)))
                k_from = k + 2
            else:
                k_from = k + 1
        binds = bind_timeline(steps, inns, first)
        fixed_at = {k for k, s in enumerate(steps) if id(s) in fixed}
        _, cands, chosen = saved(steps, start, walk, binds, left, cooldown, fixed=fixed_at)
        picked = {cands[c][0] for c in chosen}
        for k, saving, inn in cands:
            steps[k]["hearth"] = {"to": inn["names"][0], "bind": list(inn["binds"]), "spot": list(inn_spot(inn)),
                                  "saves": int(round(saving)), "p": k in picked, "cd": int(round(cooldown)),
                                  **({"core": True} if k in fixed_at else {})}
        reasons(steps, inns, first, [cands[c] for c in chosen])
    for s in steps:
        s.pop("_busy", None)
    return steps


def reasons(steps, inns, first, picked):
    binds, near = bind_timeline(steps, inns, first), towns(inns)
    place_of = lambda p: stepwords.place(p, near)
    for k, saving, inn in picked:
        if round(saving / 60) >= 1:
            was = next((place_of(p) for p in reversed(steps[:k]) if place_of(p)), None)
            stepwords.give(steps[k], "hearth", min=int(round(saving / 60)),
                           **({"stops": [was, inn["names"][0]], "at": 2} if was else {}))
    for b, s in enumerate(steps):
        if s.get("kind") != "errand" or s.get("what") != "bind":
            continue
        inn = binds[b + 1]
        use = next((k for k, _, at in picked if k > b and at is inn), None)
        before = next((place_of(p) for p in reversed(steps[b + 1:use]) if place_of(p)), None) if use else None
        if before and inn:
            town = inn["names"][0]
            stepwords.give(s, "bind", town=town, place=before, stops=[town, before, town], at=1)
