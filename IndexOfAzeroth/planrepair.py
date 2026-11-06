# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import planreport
import planunits
import plansteps
from plansteps import EPIC_CODE, own_with, offered_last, spot, step_ids

ORDER = {"P": 0, "O": 1, "D": 1, "T": 2, "S": None}


def code(s):
    return EPIC_CODE.get(s.get("kind"))


def plain(s):
    return {"k": code(s), "ids": step_ids(s), "inst": s.get("inst"), "at": s.get("at"), "name": s.get("questName"),
            "npc": s.get("npc"), "count": s.get("count"), **{k: s[k] for k in ("what", "key", "target", "need") if s.get(k)}}


def level_at(s, levels, k):
    if levels is not None:
        return levels[k] if k < len(levels) else levels[-1] if levels else None
    lv = s.get("lv")
    return lv if isinstance(lv, (int, float)) else None


def bounds(out, s, levels=None):
    ours, rank = set(step_ids(s)), ORDER.get(code(s))
    lo, hi = 0, len(out)
    if rank is None:
        return lo, hi
    for k, o in enumerate(out):
        if not ours & set(step_ids(o)) or o is s:
            continue
        r = ORDER.get(code(o))
        if r is not None and r < rank:
            lo = max(lo, k + 1)
        elif r is not None and r > rank and hi == len(out):
            hi = k
    if s.get("kind") == "objective":
        for k, o in enumerate(out):
            if not ours & set(step_ids(o)) or o is s:
                continue
            if s.get("get") and (o.get("kind") == "dungeon" or o.get("kind") == "objective" and not o.get("get")):
                hi = min(hi, k)
            elif not s.get("get") and o.get("kind") == "objective" and o.get("get"):
                lo = max(lo, k + 1)
    if s.get("kind") == "pickup":
        first = set(s.get("pre") or ())
        lo = max([lo] + [k + 1 for k, o in enumerate(out) if o.get("kind") == "turnin" and o.get("quest") in first])
        anys = [k + 1 for k, o in enumerate(out) if o.get("kind") == "turnin" and o.get("quest") in set(s.get("any") or ())]
        if anys:
            lo = max(lo, min(anys))
        if s.get("par"):
            lo = max([lo] + [k + 1 for k, o in enumerate(out) if o.get("kind") == "pickup" and o.get("quest") == s["par"]])
        if s.get("dis"):
            hi = min([hi] + [k for k, o in enumerate(out) if o.get("kind") == "turnin" and o.get("quest") == s["dis"]])
        if s.get("until"):
            hi = min([hi] + [k for k, o in enumerate(out) if o.get("kind") == "turnin" and o.get("quest") == s["until"]])
        lo = max([lo] + [k + 1 for k, o in enumerate(out) if o.get("kind") == "turnin" and o.get("crumb") is not None
                         and o.get("crumb") == s.get("quest")])
        if s.get("maybe"):
            lo = max([lo] + [k + 1 for k, o in enumerate(out) if own_with(o, s)])
    lo = leveled(out, s, lo, hi, levels)
    if s.get("kind") == "turnin":
        q = s.get("quest")
        hi = min([hi] + [k for k, o in enumerate(out) if o.get("kind") == "pickup" and o is not s
                         and (q in (o.get("pre") or ()) or q in (o.get("any") or ()))])
        lo = max([lo] + [k + 1 for k, o in enumerate(out) if o.get("kind") == "pickup" and o.get("dis") == q])
        lo = max([lo] + [k + 1 for k, o in enumerate(out) if o.get("kind") == "pickup" and q is not None and o.get("until") == q])
        if s.get("crumb"):
            hi = min([hi] + [k for k, o in enumerate(out) if o.get("kind") == "pickup" and o.get("quest") == s["crumb"]])
    if s.get("kind") == "pickup" and s.get("quest") is not None:
        hi = min([hi] + [k for k, o in enumerate(out) if o.get("kind") == "pickup" and o.get("par") == s["quest"]])
    return (lo, hi) if lo <= hi else None


def waits(s):
    return (s.get("min") or 0) if code(s) in ("P", "O") else 0


def leveled(out, s, lo, hi, levels=None):
    if not waits(s):
        return lo
    lv = [level_at(o, levels, k) for k, o in enumerate(out)]
    if not any(v is not None for v in lv):
        return lo
    return next((k for k in range(lo, hi) if (lv[k] or 0) >= waits(s)), max(lo, hi))


def spots_of(steps):
    return [spot(s) for s in steps]


def join_at(out, s, lo, hi, start):
    at = spot(s)
    if at is None:
        return lo
    spots = spots_of(out)
    runs = planunits.runs_at(spots)
    best = None
    for v in planunits.visits(spots, runs):
        first, last = v[0], v[-1]
        places = range(max(lo, first), min(hi, last + 1) + 1)
        if not places:
            continue
        near = planunits.reach("visit", runs[first] if runs else None)
        d = min(planunits.apart(at, spots[k]) for k in v)
        if d > near or (best and d >= best[0]):
            continue
        got = plansteps.cheapest(out, [at], places.start, places.stop - 1, start)
        if got:
            best = (d, got[1])
    if best:
        return best[1]
    got = plansteps.cheapest(out, [at], lo, hi, start)
    return got[1] if got else hi


def pairing(mine, held):
    from epicwatch import pair_up
    return pair_up(mine, [plain(s) for s in held])


def repair(left, planned, start, log=None, levels=None, level=None, was=None, ways=None, clocks=()):
    log = log or {}
    held = [s for s in planned if s.get("at") and s.get("inst") is not None and code(s) not in (None, "S")]
    mine = [w for w in left if w["k"] != "S"]
    pairs = pairing(mine, held)
    out = [held[pairs[i]] for i in range(len(mine)) if i in pairs]
    walked = {(id(held[pairs[i]]), id(held[pairs[i + 1]])) for i in range(len(mine) - 1) if i in pairs and i + 1 in pairs}
    taken = set(pairs.values())
    new = [s for j, s in enumerate(held) if j not in taken]
    gone = [w for i, w in enumerate(mine) if i not in pairs and not (w["k"] == "O" and any(q in log for q in w["ids"]))]
    timed = [s for s in new if s.get("quest") in set(clocks)]
    out = timed + out
    for s in new:
        if any(s is t for t in timed):
            continue
        b = bounds(out, s, levels(out) if levels else None)
        if b is None:
            return None
        lo = max(b[0], len(timed))
        if lo > b[1]:
            return None
        out.insert(join_at(out, s, lo, b[1], start), s)
    floor = max(1, len(timed))
    out = opened(out, start, levels, level, was, floor)
    fresh = {id(s) for s in new} | {id(s) for s in dinged(out, level, was)}
    out = open_givers(out, start, levels, floor, legs={(id(a), id(b)) for a, b in zip(out, out[1:])} - walked,
                      fresh=fresh, ways=ways)
    return offered_last(out), [plain(s) for s in new], gone


def dinged(steps, level=None, was=None):
    if level is None or was is None or level <= was:
        return []
    return [s for s in steps if s.get("kind") == "pickup" and takes(s) and spot(s) and was < (s.get("min") or 0) <= level]


def opened(out, start, levels=None, level=None, was=None, floor=1):
    if level is None or was is None or level <= was:
        return out
    out, lv = list(out), levels(out) if levels else None
    for s in dinged(out, level, was):
        j = next(k for k, o in enumerate(out) if o is s)
        rest, lv_rest = out[:j] + out[j + 1:], lv and lv[:j] + lv[j + 1:]
        b = bounds(rest, s, lv_rest)
        if not b or max(b[0], floor) > min(b[1], j):
            continue
        here = plansteps.added(rest, j, spot(s), start)
        i = join_at(rest, s, max(b[0], floor), min(b[1], j), start)
        if i < j and plansteps.added(rest, i, spot(s), start) < here - plansteps.TIE:
            out, lv = rest[:i] + [s] + rest[i:], lv_rest and moved_levels(lv_rest, i)
    return out


def moved_levels(lv, i):
    return lv[:i] + [lv[i] if i < len(lv) else lv[-1] if lv else None] + lv[i:]


def open_givers(steps, start, levels=None, floor=1, legs=None, fresh=(), ways=None):
    out = list(steps)
    for _ in range(MOVES):
        moved = None
        past = walked_past(out, start, needs(out, levels), every=legs is not None, ways=ways)
        old = {m for i, m, _, _, _ in past if i < 1 or (id(out[i - 1]), id(out[i])) not in (legs or ())}
        for i, m, _, at, lo in past:
            s = out[m]
            if m < floor or i > min(k for k, x, _, _, _ in past if x == m) or (
                    legs is not None and id(s) not in fresh and m in old):
                continue
            rest = out[:m] + out[m + 1:]
            b = bounds(rest, s, levels(rest) if levels else None)
            lo, hi = max(lo, floor, b[0] if b else len(rest) + 1), min(i, b[1] if b else -1)
            if lo <= hi:
                got = plansteps.cheapest(rest, [at], lo, hi, start)
                moved = rest[:got[1]] + [s] + rest[got[1]:]
                break
        if moved is None:
            return out
        out = moved
    return out


def walked_past(steps, start, need, every=False, ways=None):
    pos = {id(s): k for k, s in enumerate(steps)}
    ready = [max((pos[x] for x in need.get(id(s), ()) if x in pos), default=-1) for s in steps]
    return planunits.walked_past(spots_of(steps), ready, [takes(s) and spot(s) is not None for s in steps],
                                 planunits.runs_at(spots_of(steps)), start, plansteps.gap,
                                 [bool((s.get("hearth") or {}).get("p")) for s in steps], every, ways)


def walk(steps, start):
    return planunits.walk_of([spot(s) for s in steps], plansteps.gap, start)


def from_here(steps, start, levels=None):
    head = 0
    while head < len(steps) and head < planunits.STRETCH and code(steps[head]) not in (None, "S") and spot(steps[head]):
        head += 1
    stretch, after = steps[:head], steps[head:]
    if len(stretch) < 2 or not start:
        return list(steps)
    end = next((spot(s) for s in after if spot(s)), None)
    lv = levels(steps) if levels else None
    before = must_before(stretch, lv[0] if lv else None)
    best = shortest(stretch, before, start, end)
    if best is None:
        return list(steps)
    runs = planunits.runs_at([start] + spots_of(steps))
    own = walk(stretch, start) + (plansteps.gap(spot(stretch[-1]), end) if end else 0.0)
    if best[0] > own - planunits.reach("reorder", runs[0] if runs else None):
        return list(steps)
    return best[1] + after


def must_before(stretch, level=None):
    out = {k: set() for k in range(len(stretch))}
    for k, s in enumerate(stretch):
        ids, rank = set(step_ids(s)), ORDER.get(code(s))
        for j, o in enumerate(stretch):
            if j == k:
                continue
            r = ORDER.get(code(o))
            same = bool(ids & set(step_ids(o)))
            if same and r is not None and rank is not None and r < rank:
                out[k].add(j)
            if s.get("kind") == "pickup" and o.get("kind") == "turnin" and o.get("quest") in set(s.get("pre") or ()):
                out[k].add(j)
            if s.get("kind") == "pickup" and s.get("par") and o.get("kind") == "pickup" and o.get("quest") == s["par"]:
                out[k].add(j)
            if same and s.get("kind") == "objective" and not s.get("get") and o.get("kind") == "objective" and o.get("get"):
                out[k].add(j)
            if same and s.get("kind") == "dungeon" and o.get("get"):
                out[k].add(j)
            if s.get("maybe") and own_with(o, s):
                out[k].add(j)
            if s.get("kind") == "turnin" and o.get("kind") == "pickup" and s.get("quest") is not None \
                    and s.get("quest") in (o.get("dis"), o.get("until")):
                out[k].add(j)
            if s.get("kind") == "pickup" and o.get("kind") == "turnin" and o.get("crumb") is not None \
                    and o.get("crumb") == s.get("quest"):
                out[k].add(j)
        if s.get("kind") == "pickup" and s.get("any"):
            anys = [j for j, o in enumerate(stretch) if j != k and o.get("kind") == "turnin" and o.get("quest") in set(s["any"])]
            if anys:
                out[k].add(min(anys))
        if waits(s) and (level is None or waits(s) > level):
            out[k] |= set(range(k))
    return out


def shortest(stretch, before, start, end):
    spots = [spot(s) for s in stretch]
    n, best = len(stretch), [None]

    def go(done, at, yards, order):
        if best[0] is not None and yards >= best[0][0]:
            return
        if len(order) == n:
            total = yards + (plansteps.gap(at, end) if end else 0.0)
            if best[0] is None or total < best[0][0] - plansteps.TIE:
                best[0] = (total, [stretch[k] for k in order])
            return
        for k in range(n):
            if k not in done and before[k] <= done:
                go(done | {k}, spots[k], yards + plansteps.gap(at, spots[k]), order + [k])
    go(frozenset(), start, 0.0, [])
    return best[0]


MOVES = 24


def needs(steps, levels=None):
    before = must_before(steps, float("inf"))
    lv = levels(steps) if levels else [level_at(s, None, k) for k, s in enumerate(steps)]
    out = {}
    for k, s in enumerate(steps):
        got = {id(steps[j]) for j in before[k]}
        if code(s) in (None, "S") and k:
            got.add(id(steps[k - 1]))
        if waits(s):
            t = next((j for j, v in enumerate(lv) if v is not None and v >= waits(s)), None)
            if t is None:
                got |= {id(o) for o in steps[:k]}
            elif t:
                got.add(id(steps[t - 1]))
        out[id(s)] = got
    return out


def feel_of(steps, start, need, ways=None):
    spots, ready, kinds, runs = laid_out(steps, start, need)
    lead = [None] if start else []
    return planunits.feel(spots, ready, kinds, plansteps.gap, None, runs,
                          lead + [takes(s) and spot(s) is not None for s in steps],
                          lead + [bool((s.get("hearth") or {}).get("p")) for s in steps], ways)


def laid_out(steps, start, need):
    lead = [start] if start else []
    spots = lead + [spot(s) for s in steps]
    pos = {id(s): k + len(lead) for k, s in enumerate(steps)}
    ready = [-1] * len(lead) + [max((pos[i] for i in need.get(id(s), ()) if i in pos), default=-1) for s in steps]
    kinds = ["here"] * len(lead) + [s.get("kind") for s in steps]
    return spots, ready, kinds, planunits.runs_at(spots)


def beside_later(steps, start, need, vs, passed=()):
    spots, ready, _, runs = laid_out(steps, start, need)
    lead, out = 1 if start else 0, []
    for k in range(len(vs) - 1):
        i = vs[k][-1]
        near = planunits.reach("visit", runs[i] if runs else None)
        on = planunits.yards(spots[i], spots[vs[k + 1][0]]) if spots[i] and spots[vs[k + 1][0]] else None
        if on is None or on < near:
            continue
        found = [(planunits.apart(spots[i], spots[m]), m) for v in vs[k + 2:] for m in v
                 if m >= lead and spots[m] and ready[m] <= i and takes(steps[m - lead])
                 and planunits.apart(spots[i], spots[m]) <= near]
        out += [(k, m) for _, m in sorted(found)]
    visit_of = {m: v for v, visit in enumerate(vs) for m in visit}
    for leg, m, *_ in passed:
        k = visit_of.get(leg - 1) if leg >= 1 else None
        if k is not None and visit_of.get(m, -1) > k and (k, m) not in out:
            out.append((k, m))
    return out


def log_load(steps, held=None):
    if held is None:
        picked = {s.get("quest") for s in steps if s.get("kind") == "pickup"}
        held = len({s.get("quest") for s in steps if s.get("kind") == "turnin" and s.get("quest") not in picked})
    out, n = [], held
    for s in steps:
        out.append(n)
        n += {"pickup": 1, "turnin": -1}.get(s.get("kind"), 0)
    return out + [n]


def takes(s):
    return s.get("kind") in ("pickup", "turnin") and not s.get("maybe") and not s.get("group") and not s.get("limit") \
        and not s.get("aside")


def taken_in(out, start, need, vs, k, m, log_most):
    lead = 1 if start else 0
    j = m - lead
    there = next(v for v in vs if m in v)
    chunk, done_by = [j], {id(o) for o in out[:vs[k][-1] - lead + 1]}
    while chunk[-1] + 1 < len(out) and chunk[-1] + 1 + lead in there:
        c = out[chunk[-1] + 1]
        asked = c.get("kind") == "pickup" and c.get("maybe") and not c.get("group") and not c.get("limit") \
            and not c.get("aside")
        if not (takes(c) or asked) or not need.get(id(c), set()) <= done_by | {id(out[x]) for x in chunk}:
            break
        chunk.append(chunk[-1] + 1)
    moving = [out[c] for c in chunk]
    ids = {id(o) for o in moving}
    rest = [o for o in out if id(o) not in ids]
    lo, hi = max(vs[k][0] - lead + 1, 0), vs[k][-1] - lead + 1
    if k == 0 and start:
        near = planunits.reach("visit", planunits.runs_at([start] + [spot(o) for o in rest])[0])
        while lo < len(rest) and rest[lo].get("kind") == "objective" and spot(rest[lo]) \
                and planunits.apart(spot(rest[lo]), start) <= near:
            lo += 1
    pos = {id(o): p for p, o in enumerate(rest)}
    lo = max([lo] + [pos[i] + 1 for o in moving for i in need.get(id(o), ()) if i not in ids and i in pos])
    if lo > hi:
        return None
    got = plansteps.cheapest(rest, [spot(moving[0])], lo, hi, start)
    if not got:
        return None
    p = got[1]
    trial = rest[:p] + moving + rest[p:]
    if max(log_load(trial, log_load(out)[0])[min(p, j):max(p, j) + len(moving) + 1]) > log_most:
        return None
    return trial


def while_there(steps, start, levels=None, log_most=None, ways=None):
    if log_most is None:
        import questplan
        log_most = questplan.LOG_MOST
    out = list(steps)
    for _ in range(MOVES):
        need = needs(out, levels)
        current = feel_of(out, start, need, ways)
        moved = None
        vs = current[3]
        for k, m in beside_later(out, start, need, vs, current[4]):
            planreport.weighing(out, m - (1 if start else 0))
            trial = taken_in(out, start, need, vs, k, m, log_most)
            if trial is not None and feel_of(trial, start, need, ways)[0] < current[0] - plansteps.TIE:
                moved = trial
                break
        if moved is None:
            break
        out = moved
    return out
