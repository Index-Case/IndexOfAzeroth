# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import numpy as np

import director_rules

STRETCH = director_rules.RUN["steps"].value
TALKS = ("pickup", "turnin", "errand", "stop")
WAY_ROUND = 2.0
AREA = ("objective", "dungeon")


def plan_value(name):
    return director_rules.PLAN[name].value


def yards(p, q):
    if not p or not q or p[0] != q[0]:
        return None
    return math.hypot(p[1] - q[1], p[2] - q[2])


def apart(p, q):
    d = yards(p, q)
    return math.inf if d is None else d


def runs_at(spots, steps=STRETCH):
    pts = [(k, p) for k, p in enumerate(spots) if p]
    out, j = [director_rules.RUN["typical"].value] * len(spots), 0
    for k in range(len(spots)):
        while j < len(pts) and pts[j][0] < k:
            j += 1
        legs = [yards(a, b) for (_, a), (_, b) in zip(pts[j:j + steps + 1], pts[j + 1:j + steps + 1])]
        out[k] = director_rules.run([x for x in legs if x is not None])
    return out


def reach(name, run):
    return director_rules.reach(name, run)


def visits(spots, runs=None):
    out, first = [], None
    for k, p in enumerate(spots):
        if p is None:
            if out:
                out[-1].append(k)
            else:
                out.append([k])
            continue
        if first is not None:
            run = runs[first] if runs else None
            d = yards(spots[first], p)
            if d is not None and d <= reach("visit", run):
                out[-1].append(k)
                continue
        out.append([k])
        first = k
    return out


def kind_of(kinds):
    return "area" if any(k in AREA for k in kinds) else "town"


def trips(spots, vs, ready, kinds, gap, runs=None):
    out = []
    first = [v[0] for v in vs]
    spot_of = lambda v: spots[first[v]]
    k = 1
    while k < len(vs):
        b, gone, came = spot_of(k), 0.0, None
        run = runs[first[k]] if runs else None
        far = reach("far", run)
        for a in range(k - 1, -1, -1):
            d = yards(spot_of(a), b)
            if d is None:
                break
            near = min(gone * plan_value("back_share"), reach("back_most", run))
            if a < k - 1 and gone >= far and d <= near:
                came = a
                break
            gone = max(gone, d)
        if came is None:
            k += 1
            continue
        left = vs[came][-1]
        near = min(gone * plan_value("back_share"), reach("back_most", run))
        stay = k
        while stay + 1 < len(vs) and apart(spot_of(came), spot_of(stay + 1)) <= near:
            stay += 1
        there = [j for v in vs[k:stay + 1] for j in v if spots[j]]
        away = [j for v in vs[came + 1:k] for j in v if spots[j]]
        left_over = [ready[j] <= left and kinds[j] != "errand" for j in there] \
            if not finishing(spots, vs, ready, came, k) else []
        if there and left_over and all(left_over):
            prev = next((spots[j] for j in reversed(range(first[k])) if spots[j]), None)
            out.append(("far", came, k, gap(prev, b) if prev else 0.0))
        if any(left_over) and len(away) <= plan_value("lone") and all(kinds[j] in TALKS for j in away):
            walk = 0.0
            p = spots[left]
            for j in range(left + 1, first[k] + 1):
                if spots[j]:
                    walk += gap(p, spots[j])
                    p = spots[j]
            out.append(("jaunt", came, k, walk))
        k = stay + 1
    for k in range(1, len(vs) - 1):
        a, b, c = vs[k - 1], vs[k], vs[k + 1]
        run = runs[b[0]] if runs else None
        ac, ab = yards(spots[a[0]], spots[c[0]]), yards(spots[a[0]], spots[b[0]])
        if ac is None or ab is None or ac > reach("visit", run) or ab < reach("visit", run):
            continue
        if not any(b[0] <= ready[j] <= b[-1] for j in c) and not finishing(spots, vs, ready, k - 1, k + 1):
            out.append(("return", k - 1, k + 1, reach("visit", run)))
    return out


RIDE = "ride"


def _passing(a, b, p, giver, way, ride, lines=None):
    (ai, ax, ay), (bi, bx, by), (pi, px, py) = a, b, p
    lines = lines or [None] * len(ai)
    ride = ride | np.array([x is RIDE for x in lines], bool)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        same_ab, same_bp = (bi == ai) & (bi >= 0), bi == pi
        dap, dab, dpb = np.hypot(ax - px, ay - py), np.hypot(ax - bx, ay - by), np.hypot(px - bx, py - by)
        dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
        hop = director_rules.RUN["hop"].value
        at_a = (dap <= giver) & (dab > giver) & (dap + dpb - dab <= giver) & ((dap <= way) | (dot >= 0))
        t = np.clip(dot / (dab * dab), 0.0, 1.0)
        dqp, dqb = np.hypot(ax + t * (bx - ax) - px, ay + t * (by - ay) - py), (1.0 - t) * dab
        by_way = ~ride & (dab < director_rules.COST["ridden"].value) & (t > 0) & (dqp <= giver) & (dqb > giver) \
            & (dqp + dpb - dqb <= giver)
        for i, line in enumerate(lines):
            if line is None or line is RIDE:
                continue
            g, w = giver[i, 0], way[i, 0]
            off, along, length, ahead = _along(line, px[0], py[0], g)
            dpb_i = dpb[i]
            at_a[i] = (dap[i] <= g) & (length > g) & (dap[i] + dpb_i - length <= g) & ((dap[i] <= w) | (ahead >= 0))
            by_way[i] = ~ride[i] & (along > 0) & (off <= g) & (length - along > g) & (off + dpb_i - (length - along) <= g)
        return (ai == pi) & (ai >= 0) & same_ab & same_bp & (dpb > hop) & (at_a | by_way)


def _along(line, px, py, first):
    seg = line[1:] - line[:-1]
    size = np.hypot(seg[:, 0], seg[:, 1])
    start = np.concatenate([[0.0], np.cumsum(size)])
    len2 = np.where(size > 0, size * size, 1.0)
    t = np.clip(((px[None, :] - line[:-1, :1]) * seg[:, :1] + (py[None, :] - line[:-1, 1:]) * seg[:, 1:]) / len2[:, None],
                0.0, 1.0)
    off = np.hypot(line[:-1, :1] + t * seg[:, :1] - px[None, :], line[:-1, 1:] + t * seg[:, 1:] - py[None, :])
    off = np.where(np.isnan(off), np.inf, off)
    near = np.argmin(off, axis=0)
    cols = np.arange(len(px))
    along = start[near] + t[near, cols] * size[near]
    to = min(first, start[-1])
    k = min(int(np.searchsorted(start, to, side="right")) - 1, len(seg) - 1)
    u = (to - start[k]) / size[k] if size[k] > 0 else 0.0
    hx, hy = seg[k, 0] * u + line[k, 0] - line[0, 0], seg[k, 1] * u + line[k, 1] - line[0, 1]
    ahead = (px - line[0, 0]) * hx + (py - line[0, 1]) * hy
    return off[near, cols], along, start[-1], ahead


def _arrays(ps):
    return (np.array([p[0] if p else -1 for p in ps], dtype=np.int64),
            np.array([p[1] if p else np.nan for p in ps], dtype=float),
            np.array([p[2] if p else np.nan for p in ps], dtype=float))


def walked_past(spots, ready, givers, runs=None, start=None, gap=None, ridden=None, every=False, ways=None):
    gap = gap or apart
    cols = [(m, p) for m, g in enumerate(givers or ()) if g and spots[m]
            for p in ([spots[m]] if g is True else g) if p]
    if not cols:
        return []
    n, lead = len(spots), 1 if start else 0
    places = ([start] if start else []) + list(spots)
    vs = visits(places, runs_at(places))
    first_of, visit_of = {}, {}
    for v in vs:
        for k in v:
            first_of[k], visit_of[k] = v[0], v[0]
    before, last = [], start
    for q in spots:
        before.append(last)
        last = q or last
    a, b, p = (tuple(x[:, None] for x in _arrays(before)), tuple(x[:, None] for x in _arrays(spots)),
               tuple(x[None, :] for x in _arrays([q for _, q in cols])))
    giver = np.array([reach("giver", runs[k] if runs else None) for k in range(n)])[:, None]
    way = np.array([reach("way", runs[k] if runs else None) for k in range(n)])[:, None]
    ride = np.array([bool(ridden and ridden[k]) for k in range(n)])[:, None]
    open_at, at_m = np.array([ready[m] for m, _ in cols]), np.array([m for m, _ in cols])
    lines = None
    if ways:
        with np.errstate(invalid="ignore"):
            dab, room = np.hypot(a[1] - b[1], a[2] - b[2]), np.hypot(a[1] - p[1], a[2] - p[2]) + np.hypot(b[1] - p[1],
                                                                                                         b[2] - p[2])
            near = (room <= WAY_ROUND * dab + 2 * giver) & (open_at[None, :] < np.arange(n)[:, None]) \
                & (at_m[None, :] > np.arange(n)[:, None])
        asked = [k for k in range(n) if before[k] and spots[k] and before[k][0] == spots[k][0] and near[k].any()]
        got = ways([(before[k], spots[k]) for k in asked], [q for q in places if q] + [q for _, q in cols])
        lines = [None] * n
        for k, line in zip(asked, got):
            lines[k] = line
    hit = _passing(a, b, p, giver, way, ride, lines)
    (pi_, px, py), near, beside = _arrays([q for _, q in cols]), np.full(len(cols), np.inf), []
    for k, q in enumerate(places):
        if first_of.get(k) == k:
            near = np.full(len(cols), np.inf)
        if q:
            with np.errstate(invalid="ignore"):
                d = np.where(pi_ == q[0], np.hypot(px - q[1], py - q[2]), np.inf)
            near = np.minimum(near, d)
        beside.append(near)
    left = np.array([k + lead > 0 and spots[k] is not None and first_of.get(k + lead) == k + lead for k in range(n)])
    near_place = np.array([beside[k + lead - 1] if k + lead > 0 else np.full(len(cols), np.inf) for k in range(n)])
    with np.errstate(invalid="ignore"):
        dpb = np.where(b[0] == p[0], np.hypot(b[1] - p[1], b[2] - p[2]), np.inf)
    other = (b[0] >= 0) & (b[0] != a[0]) & (a[0] == p[0])
    hit |= left[:, None] & (near_place <= giver) & ((dpb > giver) | other)
    rows = np.arange(n)[:, None]
    hit &= (rows > open_at[None, :]) & (rows < at_m[None, :])
    out = {}
    for c in np.nonzero(hit.any(axis=0))[0]:
        m, q = cols[c]
        for i in (np.nonzero(hit[:, c])[0] if every else [int(hit[:, c].argmax())]):
            if every or m not in out or i < out[m][0][0]:
                s = max(0, visit_of.get(i + lead - 1, i + lead) - lead) if i + lead > 0 else 0
                out.setdefault(m, [])
                if not every:
                    out[m] = []
                out[m].append((int(i), q, s))
    return sorted((i, m, 2 * gap(spots[i], q), q, s) for m, hits in out.items() for i, q, s in hits)


def behind(places, off):
    hop = director_rules.RUN["hop"].value
    return any(off(q) <= hop for q in places if q)


def finishing(spots, vs, ready, came, k):
    away = [j for v in vs[came + 1:k] for j in v if spots[j]]
    if came < 1 or not away:
        return False
    f, hop = away[0], director_rules.RUN["hop"].value
    return vs[came][0] <= ready[f] <= vs[came][-1] and behind([spots[j] for j in vs[came - 1]], lambda q: apart(q, spots[f])) \
        and all(apart(spots[f], spots[j]) <= hop for j in away)


def skips(spots, vs, ready, kinds, runs=None):
    out = []
    for k in range(len(vs) - 1):
        i = vs[k][-1]
        run = runs[i] if runs else None
        near = reach("visit", run)
        on = (yards(spots[i], spots[vs[k + 1][0]]) if spots[i] and spots[vs[k + 1][0]] else None)
        if on is None or on < near:
            continue
        back = [spots[j] for j in vs[k - 1]] if k else []
        for v in vs[k + 2:]:
            m = next((m for m in v if spots[m] and ready[m] <= i and kinds[m] not in ("errand", "dungeon")
                      and (apart(spots[i], spots[m]) <= near
                           or ready[m] >= vs[k][0] and behind(back, lambda q: apart(q, spots[m])))), None)
            if m is not None:
                out.append((k, m))
                break
    return out


def walk_of(spots, gap, start=None):
    total, prev = 0.0, start
    for p in spots:
        if p is None:
            continue
        if prev is not None:
            total += gap(prev, p)
        prev = p
    return total


def feel(spots, ready, kinds, gap, start=None, runs=None, givers=None, ridden=None, ways=None):
    vs = visits(spots, runs)
    found = trips(spots, vs, ready, kinds, gap, runs)
    left = skips(spots, vs, ready, kinds, runs)
    cost = sum(reach("visit", runs[vs[k][-1]] if runs else None) for k, _ in left)
    past = walked_past(spots, ready, givers, runs, start, gap, ridden, ways=ways) if givers else []
    return walk_of(spots, gap, start) + sum(t[3] for t in found) + cost + sum(x[2] for x in past), found, left, vs, past
