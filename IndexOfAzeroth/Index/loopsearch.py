# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from layers import (BACK_SHARE, COVER_YARDS, GATHER_NEAR, GATHER_STOPS, Coverage, RangeOr, gather_rate, gather_score,
                    turn_back, way_cost)

WALK_WORKERS = 4
SEEDS = 12
SHAKES = 16
GRANULAR = 8
TIE = 1e-9
SHORTER = 0.5


def gains(rate, yards, than):
    return rate > than[0] * (1 + TIE) or (rate >= than[0] * (1 - TIE * TIE) and yards < than[1] - SHORTER)


def best_loop(propose, until, tried=None, stopped=None):
    best, seen = None, set()

    def note(loop):
        if tried is not None and loop.key not in seen:
            seen.add(loop.key)
            tried(loop)
    while True:
        loop = propose()
        if loop is None or loop.score == -math.inf or (best is not None and loop.score <= best.score * (1 + TIE)):
            return best, True
        if not loop.missing:
            note(loop)
            return loop, True
        if (stopped and stopped()) or (best is not None and time.time() >= until):
            return best, False
        loop.walk()
        loop = loop.walked()
        if loop.missing:
            return best, False
        if loop.score > -math.inf:
            note(loop)
            if best is None or loop.score > best.score:
                best = loop


class Walked:

    def __init__(self, walk, workers=WALK_WORKERS):
        self.walk, self.workers = walk, workers
        self.hops, self.lock = {}, threading.Lock()

    def get(self, a, b):
        return self.hops.get((a[0], a[1], b[0], b[1]))

    def walk_all(self, pairs, stopped=None):
        todo = list(dict.fromkeys((tuple(a), tuple(b)) for a, b in pairs if self.get(a, b) is None))

        def one(ab):
            if stopped and stopped():
                return
            a, b = ab
            got = self.walk(a, b)
            gap = got[1] or 0.0
            entry = {"yards": got[0] if gap <= GATHER_NEAR else math.inf, "gap": gap, "points": got[2] if len(got) > 2 else None}
            with self.lock:
                self.hops[(a[0], a[1], b[0], b[1])] = entry
        if len(todo) == 1:
            one(todo[0])
        elif todo:
            with ThreadPoolExecutor(min(self.workers, len(todo))) as pool:
                list(pool.map(one, todo))


class Camp:

    def __init__(self, inst, block, north, west, estimate, stops_for, walked, speed):
        self.inst, self.block, self.north, self.west, self.estimate = inst, block, north, west, estimate
        self.stops_for, self.walked_for, self.speed = stops_for, walked, max(float(speed), 1.0)
        self.key, self.score, self.detour, self._stops, self._walked = (inst, round(north, 1), round(west, 1)), estimate, 0.0, None, None

    @property
    def stops(self):
        if self._stops is None:
            self._stops = self.stops_for(self.block) or []
        return self._stops

    @property
    def walked_store(self):
        if self._walked is None:
            self._walked = self.walked_for()
        return self._walked

    def hops(self):
        s = [tuple(p[:2]) for p in self.stops]
        return list(zip(s, s[1:] + s[:1])) if len(s) > 1 else []

    @property
    def missing(self):
        return [(a, b) for a, b in self.hops() if self.walked_store.get(a, b) is None]

    def walk(self):
        self.walked_store.walk_all(self.missing)

    def walked(self):
        from layers import camp_walked
        if self.missing:
            return self
        got = [self.walked_store.get(a, b)["yards"] for a, b in self.hops()]
        if math.inf in got:
            self.score = -math.inf
            return self
        straight = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in self.hops())
        self.detour = max(0.0, sum(got) - straight) / self.speed
        self.score = camp_walked(self.estimate, self.block, self.detour)
        return self

    def ways(self):
        out = {}
        for a, b in self.hops():
            hop = self.walked_store.get(a, b)
            if hop and hop["points"]:
                out[(a[0], a[1], b[0], b[1])] = {"points": hop["points"], "partial": hop["gap"] > 0,
                                                 **({"gap": hop["gap"]} if hop["gap"] > 0 else {})}
        return out


def hop_pairs(xy, reach=COVER_YARDS):
    n = len(xy)
    if n < 2:
        return [], {}
    xy = np.asarray(xy, float)
    pairs, rows = [], []
    for i in range(n - 1):
        ab = xy[i + 1:] - xy[i]
        ak = xy - xy[i]
        long2 = np.maximum((ab * ab).sum(1), 1e-9)
        t = (ab @ ak.T) / long2[:, None]
        off2 = (ak * ak).sum(1)[None, :] - t * t * long2[:, None]
        inside = (t > 0) & (t < 1) & (off2 <= reach * reach)
        inside[:, i] = False
        inside[np.arange(n - 1 - i), np.arange(i + 1, n)] = False
        pairs += [(i, i + 1 + int(j)) for j in np.flatnonzero(~inside.any(1))]
        j, k = np.nonzero(inside)
        rows.append(np.stack([k, np.full(len(j), i), i + 1 + j], 1).astype(np.int32))
    rows = np.concatenate(rows)
    rows = rows[np.argsort(rows[:, 0], kind="stable")]
    groups, starts = np.unique(rows[:, 0], return_index=True)
    return pairs, {int(g): part[:, 1:] for g, part in zip(groups, np.split(rows, starts[1:]))}


def simplified(points, most):
    keep = list(range(len(points)))
    if len(keep) <= most:
        return keep

    def area(k):
        a, b, c = points[keep[k - 1]], points[keep[k]], points[keep[(k + 1) % len(keep)]]
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
    while len(keep) > max(most, 3):
        del keep[min(range(len(keep)), key=area)]
    return keep


class Tour:

    def __init__(self, field, tour, chains, yards, mask, penalty):
        self.field, self.tour, self.chains, self.yards, self.mask, self.penalty = field, tour, chains, yards, mask, penalty
        self.key = (field.zone, tuple(tour), tuple(tuple(c) for c in chains))
        self.nodes = field.value(mask)
        self.score = field.rate(self.nodes, yards, penalty) if yards < math.inf else -math.inf
        self.missing = [(field.at[a], field.at[b]) for a, b in self.hops() if field.walked.get(field.at[a], field.at[b]) is None]

    def hops(self):
        return [(c[k], c[k + 1]) for c in self.chains for k in range(len(c) - 1)]

    def walk(self):
        self.field.walked.walk_all(self.missing, self.field.stopped)

    def walked(self):
        return self.field.as_walked(self.tour, self.chains)

    def line(self):
        return [g for c in self.chains for g in c[:-1]] or list(self.tour)

    def figures(self):
        return gather_score(self.field.cover, self.mask, self.yards, self.field.speed, self.field.respawn)

    def route(self):
        f, line = self.field, self.line()
        if len(line) < 2:
            return [f.groups[g] for g in line], {}, [None] * len(line)
        keep = simplified([f.at[g] for g in line], GATHER_STOPS)
        stops = [line[k] for k in keep]
        ways, bends = {}, []
        for s, k in enumerate(keep):
            end = keep[(s + 1) % len(keep)] if s + 1 < len(keep) else keep[0] + len(line)
            pts, gap = [], 0.0
            for q in range(k, end):
                a, b = f.at[line[q % len(line)]], f.at[line[(q + 1) % len(line)]]
                hop = f.walked.get(a, b)
                got = hop["points"] if hop and hop["points"] else [[b[0], b[1]]]
                pts += [list(p) for p in got]
                gap = hop["gap"] if hop else 0.0
            a, b = f.at[stops[s]], f.at[stops[(s + 1) % len(stops)]]
            ways[(a[0], a[1], b[0], b[1])] = {"points": pts, "partial": gap > 0, **({"gap": gap} if gap > 0 else {})}
            bends.append(pts)
        return [f.groups[g] for g in stops], ways, bends


class Field:

    def __init__(self, zone, setup, speed, walked, stopped=None, seed=0):
        self.zone, self.setup, self.walked, self.stopped = zone, setup, walked, stopped
        self.speed, self.respawn = max(float(speed), 1.0), float(setup["respawn"])
        self.groups = list(setup["groups"])
        self.at = [(g[0], g[1]) for g in self.groups]
        self.n = len(self.groups)
        self.xy = np.array(self.at, float).reshape(-1, 2)
        self.cover = Coverage(setup["pts"], setup.get("weights"))
        self.value = self.cover.value
        self.pairs, self.past = hop_pairs(self.xy)
        self.index = {a: i for i, a in enumerate(self.at)}
        self.rng = random.Random(seed)
        self.solved_with, self.kept, self.best = None, {}, None
        self.live = len(self.pairs)
        self.edge_masks, self.shapes = {}, {}

    def rate(self, nodes, yards, weighed=0.0):
        return gather_rate(nodes, yards, self.speed, self.respawn, weighed)


    def hop(self, i, j):
        a, b = self.at[i], self.at[j]
        got = self.walked.get(a, b)
        key = (i, j, got is not None)
        if key not in self.edge_masks:
            pts = got and got["points"]
            self.edge_masks[key] = self.cover.near([a] + [tuple(p[:2]) for p in pts]) if pts else self.cover.straight(a, b)
        return (got["yards"] if got else math.hypot(a[0] - b[0], a[1] - b[1])), self.edge_masks[key]

    def walked_hops(self):
        index = self.index
        return [(index[(a0, a1)], index[(b0, b1)], hop["yards"]) for (a0, a1, b0, b1), hop in list(self.walked.hops.items())
                if (a0, a1) in index and (b0, b1) in index]

    def walked_count(self):
        return len(self.walked_hops())

    def network(self):
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        cut = {g for i, j, yards in self.walked_hops() if yards == math.inf for g in (i, j)}
        live = set(self.pairs).union(*(map(tuple, self.past[g].tolist()) for g in cut if g in self.past))
        if len(live) != self.live:
            self.live, self.kept = len(live), {s: (t, None) for s, (t, _) in self.kept.items()}
        rows, cols, cost = [], [], []
        for i, j in sorted(live):
            for a, b in ((i, j), (j, i)):
                y = self.hop(a, b)[0]
                if y < math.inf:
                    rows.append(a)
                    cols.append(b)
                    cost.append(max(y, 0.01))
        graph = csr_matrix((cost, (rows, cols)), shape=(self.n, self.n))
        self.D, self.P = dijkstra(graph, directed=True, return_predecessors=True)
        self.chain_masks, self.step_memo, self.turn_memo = {}, {}, {}

    def chain(self, i, j):
        if i == j:
            return [i]
        out = [j]
        while out[-1] != i:
            out.append(int(self.P[i, out[-1]]))
        return out[::-1]

    def cm(self, i, j):
        key = (i, j)
        got = self.chain_masks.get(key)
        if got is None:
            if i == j:
                got = self.cover.straight(self.at[i], self.at[i])
            elif self.D[i, j] == math.inf:
                got = 0
            else:
                c, got = self.chain(i, j), 0
                for a, b in zip(c, c[1:]):
                    got |= self.hop(a, b)[1]
            self.chain_masks[key] = got
        return got

    def steps(self, i, j):
        key = (i, j)
        got = self.step_memo.get(key)
        if got is None:
            c, at = self.chain(i, j), self.at
            inner = sum(turn_back(at[c[k - 1]], at[c[k]], at[c[k + 1]]) for k in range(1, len(c) - 1))
            got = self.step_memo[key] = (c[1] if len(c) > 1 else j, c[-2] if len(c) > 1 else i, inner)
        return got

    def turn(self, x, y, z):
        key = (x, y, z)
        got = self.turn_memo.get(key)
        if got is None:
            got = self.turn_memo[key] = turn_back(self.at[self.steps(x, y)[1]], self.at[y], self.at[self.steps(y, z)[0]])
        return got

    def turns(self, t):
        m = len(t)
        if m < 2:
            return 0.0
        return sum(self.steps(t[k], t[(k + 1) % m])[2] + self.turn(t[k - 1], t[k], t[(k + 1) % m]) for k in range(m))

    def penalty(self, line):
        pts = [self.at[g] for g in line]
        if len(pts) == 2:
            return BACK_SHARE * (turn_back(pts[0], pts[1], pts[0]) + turn_back(pts[1], pts[0], pts[1]))
        if len(pts) < 3:
            return 0.0
        plain = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(pts, pts[1:] + pts[:1]))
        return max(0.0, way_cost(pts, None, True) - plain)

    def tour_of(self, tour):
        m = len(tour)
        hops = [(tour[k], tour[(k + 1) % m]) for k in range(m)] if m > 1 else []
        if any(self.D[a, b] == math.inf for a, b in hops) or (m == 1 and self.n > 1):
            return Tour(self, list(tour), [[a, b] for a, b in hops], math.inf, 0, 0.0)
        chains = [self.chain(a, b) for a, b in hops] or [[tour[0]]]
        mask = 0
        for k in range(m):
            mask |= self.cm(tour[k], tour[(k + 1) % m])
        line = [g for c in chains for g in c[:-1]] or list(tour)
        return Tour(self, list(tour), chains, float(sum(self.D[a, b] for a, b in hops)), mask, self.penalty(line))

    def as_walked(self, tour, chains):
        yards, mask = 0.0, 0
        for c in chains:
            if len(c) == 1:
                mask |= self.cover.straight(self.at[c[0]], self.at[c[0]])
            for a, b in zip(c, c[1:]):
                y, got = self.hop(a, b)
                yards += y
                mask |= got
        line = [g for c in chains for g in c[:-1]] or list(tour)
        return Tour(self, list(tour), chains, yards, mask, self.penalty(line))


    def propose(self):
        if not self.n:
            return None
        now = self.walked_count()
        if now != self.solved_with:
            self.solved_with = now
            self.network()
            self.best = self.solve()
        return self.best if self.best.score > -math.inf else None

    def solve(self):
        if self.n <= 2:
            tour = list(range(self.n))
            return self.tour_of(tour) if self.n == 1 or (self.D[0, 1] < math.inf and self.D[1, 0] < math.inf) else self.tour_of([0])
        found = {}
        for seed in self.seeds():
            kept = self.kept.get(seed)
            if kept is None or self.shape(kept[0]) != kept[1]:
                best = self.searched(kept[0] if kept else self.grown(seed))
                kept = self.kept[seed] = (best, self.shape(best))
            found[tuple(kept[0])] = kept[1]
        return self.tour_of(list(max(found, key=found.get)))

    def searched(self, start):
        cur = best = self.improve(start)
        for _ in range(SHAKES):
            if self.stopped and self.stopped():
                break
            cand = self.improve(self.shaken(cur))
            if self.shape(cand) >= self.shape(cur):
                cur = cand
            if self.shape(cand) > self.shape(best):
                best = cand
        return best

    def shape(self, tour):
        key = (self.solved_with, tuple(tour))
        if key not in self.shapes:
            if self.shapes and next(iter(self.shapes))[0] != self.solved_with:
                self.shapes.clear()
            loop = self.tour_of(tour)
            self.shapes[key] = (loop.score, -(loop.yards + loop.penalty))
        return self.shapes[key]

    def seeds(self):
        held = [g[2] for g in self.groups]
        picked = [max(range(self.n), key=lambda i: held[i])]
        far = np.hypot(*(self.xy - self.xy[picked[0]]).T)
        while len(picked) < min(SEEDS, self.n):
            nxt = int(np.argmax(far))
            if far[nxt] <= 0:
                break
            picked.append(nxt)
            far = np.minimum(far, np.hypot(*(self.xy - self.xy[nxt]).T))
        return picked

    def grown(self, seed):
        tour = [seed]
        for j in np.argsort(self.D[seed] + self.D[:, seed]):
            j = int(j)
            if j != seed and self.D[seed, j] < math.inf and self.D[j, seed] < math.inf:
                tour.append(j)
                if len(tour) == 3:
                    break
        return tour

    def shaken(self, tour):
        t, m, rng = list(tour), len(tour), self.rng
        if m > 3:
            cut = rng.randint(1, max(1, m // 4))
            at = rng.randrange(m)
            drop = {(at + q) % m for q in range(cut)}
            t = [g for k, g in enumerate(t) if k not in drop] or t[:1]
        else:
            cut = 1
        out = [v for v in range(self.n) if v not in set(t)]
        if out:
            d = np.min(np.hypot(*(self.xy[out][:, None, :] - self.xy[t][None, :, :]).transpose(2, 0, 1)), axis=1)
            near = [out[k] for k in np.argsort(d)[:max(4, 3 * cut)]]
            for v in rng.sample(near, min(cut, len(near))):
                t = self.inserted(t, v)
        return t

    def inserted(self, t, v):
        m = len(t)
        best, at = math.inf, None
        for k in range(m):
            a, b = t[k], t[(k + 1) % m]
            if self.D[a, b] == math.inf and m > 1:
                continue
            y = self.D[a, v] + self.D[v, b] - (self.D[a, b] if m > 1 else 0.0)
            if y < best:
                best, at = y, k + 1
        return t[:at] + [v] + t[at:] if at is not None else t

    def improve(self, tour):
        t = list(tour)
        while True:
            if self.stopped and self.stopped():
                return t
            st = self.state(t)
            if st is None:
                return t
            best, move = st["now"], None
            for kind in ("near", "turn"):
                for mv in self.moves(st, kind):
                    got = self.valued(st, *mv)
                    if got is not None and gains(*got, best):
                        best, move = got, mv
                if move is not None:
                    break
            if move is None:
                return t
            t = self.moved(t, *move)

    def state(self, t):
        D, steps, turn, value, m = self.D, self.steps, self.turn, self.value, len(t)
        nxt = [t[(k + 1) % m] for k in range(m)]
        hop_len = [D[t[k], nxt[k]] if m > 1 else 0.0 for k in range(m)]
        Y = sum(hop_len)
        if Y == math.inf:
            return None
        ro = RangeOr([self.cm(t[k], nxt[k]) for k in range(m)])
        inner = [steps(t[k], nxt[k])[2] if m > 1 else 0.0 for k in range(m)]
        J = [turn(t[k - 1], t[k], nxt[k]) if m > 1 else 0.0 for k in range(m)]
        TB = sum(inner) + sum(J)
        ex1 = [ro.of(k + 1, m - 1) for k in range(m)]
        ex2 = [ro.of(k + 1, m - 2) for k in range(m)] if m > 2 else []
        inside = set(t)
        out = [v for v in range(self.n) if v not in inside]
        nearest = {}
        if out:
            d = np.hypot(*(self.xy[out][:, None, :] - self.xy[t][None, :, :]).transpose(2, 0, 1))
            k_of = np.argmin(d, axis=1)
            near = d[np.arange(len(out)), k_of]
            for q in np.argsort(near, kind="stable"):
                got = nearest.setdefault(int(k_of[q]), [])
                if len(got) < GRANULAR:
                    got.append(out[q])
        return {"t": t, "m": m, "nxt": nxt, "hop_len": hop_len, "Y": Y, "ro": ro, "inner": inner, "J": J, "TB": TB,
                "ex1": ex1, "v1": [value(x) for x in ex1], "ex2": ex2, "v2": [value(x) for x in ex2], "nearest": nearest,
                "now": (self.rate(value(ro.of(0, m)), Y, BACK_SHARE * TB), Y)}

    def moves(self, st, kind):
        m, nearest = st["m"], st["nearest"]
        if kind == "turn":
            return [("2opt", i, j) for i in range(m - 2) for j in range(i + 2, m) if not (i == 0 and j == m - 1)] if m > 3 else []
        out = [("in", h, v) for k, vs in nearest.items() for v in vs for h in sorted({(k - 1) % m, k})]
        if m == 2:
            out += [("swap", k, v) for k in range(2) for v in nearest.get(k, ())]
        if m > 2:
            out += [mv for k in range(m) for mv in [("out", k, None)] + [("swap", k, v) for v in nearest.get(k, ())]]
        return out

    def valued(self, st, kind, k, v):
        D, steps, turn, value, rate = self.D, self.steps, self.turn, self.value, self.rate
        t, m, nxt, hop_len, Y = st["t"], st["m"], st["nxt"], st["hop_len"], st["Y"]
        inner, J, TB = st["inner"], st["J"], st["TB"]
        if kind == "in":
            a, b = t[k], nxt[k]
            y = Y - hop_len[k] + D[a, v] + D[v, b]
            if y == math.inf:
                return None
            if m == 1:
                back = self.turns([a, v])
            else:
                p, q = t[k - 1], t[(k + 2) % m]
                back = (TB - inner[k] + steps(a, v)[2] + steps(v, b)[2] - J[k] - J[(k + 1) % m]
                        + turn(p, a, v) + turn(a, v, b) + turn(v, b, q))
            return rate(st["v1"][k] + value((self.cm(a, v) | self.cm(v, b)) & ~st["ex1"][k]), y, BACK_SHARE * back), y
        if kind == "swap" and m == 2:
            o = t[1 - k]
            y = D[o, v] + D[v, o]
            if y == math.inf:
                return None
            return rate(value(self.cm(o, v) | self.cm(v, o)), y, BACK_SHARE * self.turns([o, v])), y
        if kind in ("out", "swap"):
            a, b, p, q = t[k - 1], nxt[k], t[k - 2], t[(k + 2) % m]
            cut = TB - inner[k - 1] - inner[k] - J[k - 1] - J[k] - J[(k + 1) % m]
            if kind == "out":
                y = Y - hop_len[k - 1] - hop_len[k] + D[a, b]
                if y == math.inf:
                    return None
                back, mask = cut + steps(a, b)[2] + turn(p, a, b) + turn(a, b, q), self.cm(a, b)
            else:
                y = Y - hop_len[k - 1] - hop_len[k] + D[a, v] + D[v, b]
                if y == math.inf:
                    return None
                back = cut + steps(a, v)[2] + steps(v, b)[2] + turn(p, a, v) + turn(a, v, b) + turn(v, b, q)
                mask = self.cm(a, v) | self.cm(v, b)
            return rate(st["v2"][k] + value(mask & ~st["ex2"][k]), y, BACK_SHARE * back), y
        return self.turned(st, k, v)

    def turned(self, st, i, j):
        D, steps, turn, value, rate = self.D, self.steps, self.turn, self.value, self.rate
        t, m = st["t"], st["m"]
        if "span" not in st:
            back_ok = [D[t[(k + 1) % m], t[k]] < math.inf for k in range(m)]
            rows = {"fwd": st["hop_len"], "back": [D[t[(k + 1) % m], t[k]] for k in range(m)], "inner": st["inner"],
                    "rin": [steps(t[(k + 1) % m], t[k])[2] if back_ok[k] else math.inf for k in range(m)], "J": st["J"],
                    "rJ": [turn(t[(k + 1) % m], t[k], t[k - 1]) if back_ok[k] and back_ok[k - 1] else math.inf for k in range(m)]}
            sums = {}
            for name, row in rows.items():
                acc, gaps = [0.0], [0]
                for x in row:
                    acc.append(acc[-1] + (x if x < math.inf else 0.0))
                    gaps.append(gaps[-1] + (x == math.inf))
                sums[name] = (acc, gaps)

            def span(name, lo, hi):
                if hi < lo:
                    return 0.0
                acc, gaps = sums[name]
                return math.inf if gaps[hi + 1] > gaps[lo] else acc[hi + 1] - acc[lo]
            st["span"] = span
            st["back"] = RangeOr([self.cm(t[(k + 1) % m], t[k]) for k in range(m)])
        span, J = st["span"], st["J"]
        a, b, c, e = t[i], t[i + 1], t[j], t[(j + 1) % m]
        y = st["Y"] - span("fwd", i, j) + D[a, c] + span("back", i + 1, j - 1) + D[b, e]
        if y == math.inf:
            return None
        gone = span("inner", i, j) + span("J", i, min(j + 1, m - 1)) + (J[0] if j + 1 == m else 0.0)
        new = (steps(a, c)[2] + span("rin", i + 1, j - 1) + steps(b, e)[2] + turn(t[i - 1], a, c) + turn(a, c, t[j - 1])
               + span("rJ", i + 2, j - 1) + turn(t[i + 2], b, e) + turn(b, e, t[(j + 2) % m]))
        mask = st["ro"].of(j + 1, m - (j - i + 1)) | st["back"].of(i + 1, j - i - 1) | self.cm(a, c) | self.cm(b, e)
        return rate(value(mask), y, BACK_SHARE * (st["TB"] - gone + new)), y

    @staticmethod
    def moved(t, kind, k, v):
        if kind == "in":
            return t[:k + 1] + [v] + t[k + 1:]
        if kind == "out":
            return t[:k] + t[k + 1:]
        if kind == "swap":
            return t[:k] + [v] + t[k + 1:]
        return t[:k + 1] + t[k + 1:v + 1][::-1] + t[v + 1:]
