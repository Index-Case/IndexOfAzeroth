# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import collections
import gzip
import heapq
import json
import math
import os
import threading
import time

import jsontext
import mainstores
import playerstores
import store
import workers
from auction import (BAND_LEAST, LOOP_LISTED_LEAST, POOLED, asks as count_asks, band_of, kept_key, pair_cut, pooled_in,
                     read_whole, row_key)
from protocol import AUCTION_BAND, AUCTION_BID, AUCTION_MIN_BID, AUCTION_NOKEY, AUCTION_SOLD
from dayrecord import day_of
from serverlog import log_error

CHEAP_ALWAYS = 0.15
CHEAP_MOST = 0.30
JUMP = 1.20
TRIM_SD = 1.5
ASKS_LEAST = LOOP_LISTED_LEAST
MAD_SIGMA = 1.4826
R_FLOOR = 0.03 ** 2
BAIT_Z = 3.0
BAIT_SIGMA_FLOOR = 0.1
BAIT_REST = 10
BAIT_MOST = 3
FAR_HIGH = 10.0
FRONT = 5
Z90 = 1.645
HELD = 0.90
CAL_LEAST = 100
DECISIONS_LEAST = 3
AGE_TAU = 7 * 86400
CAL_EDGES = [math.asinh(w / 2) / Z90 for w in (0.25, 0.5, 1.0, 1.5, 3.0)]
Q_GRID = [10 ** (e / 10) for e in range(-70, -1, 2)]
FLOOR_GRID = [(s / 100) ** 2 for s in (1, 2, 3, 5, 8, 12, 18, 25, 35, 50, 70)]
Q_OWN = 20
Q_DEFAULT = 0.01 / 24
FIT_DAYS = 60
BREAK_P = 0.25
CP_RATE = 1 / (30 * 24)
CP_JUMP = 0.5 ** 2
CP_KEEP = 20
CP_SURE = 0.5
RESET_Z = 3.0
SURVIVE_LEAST = 20
VOL_DAYS = 7
VOL_LEAST = 5
SUPPORT_DAYS = 60
LEVEL_DAYS = 30
LEVEL_DAYS_LEAST = 3
STATES = [(0.60, "spiking"), (0.15, "rising"), (-0.15, "stable"), (-0.60, "falling"), (-math.inf, "crashing")]
HOUR = 3600
DAY = 86400

W_SALE = 0.9
W_CANCEL = 0.2
W_ALONE = 0.5
W_RELIST = 0.05
WALL_NEAR = 1.05

R_SCAN, R_PRICE, R_NOISE, R_KEPT, R_LOW, R_P10, R_P50, R_P90, R_UNITS, R_AUCTIONS, R_BAIT, R_FRONT, R_SURVIVE, R_SALES, \
    R_WALL = range(15)
S_HOURS, S_GONE, S_UNITS, S_EXPIRED, S_SOLD, S_CANCELLED, S_FRONT, S_NEW, S_UNDER, S_PRICES, S_LISTED = range(11)
SALES_MARK = 6
PLACE_DIGITS = 2

DAILY = "daily-"
MODEL = "model.json"
MODEL_MARK = 3
OPEN = "open.json.gz"



def quantile(pairs, share):
    total = sum(c for _, c in pairs)
    run = 0
    for p, c in pairs:
        run += c
        if run >= share * total:
            return p
    return pairs[-1][0]


def median(values):
    s = sorted(values)
    n = len(s)
    return (s[(n - 1) // 2] + s[n // 2]) / 2 if n else None


def bait_count(asks):
    out = 0
    for k in range(min(BAIT_MOST, len(asks))):
        rest = [math.log(u) for u, _ in asks[k + 1:k + 1 + BAIT_REST]]
        if len(rest) < 2:
            break
        mid = median(rest)
        sigma = max(MAD_SIGMA * median([abs(v - mid) for v in rest]), BAIT_SIGMA_FLOOR)
        if (mid - math.log(asks[k][0])) / sigma <= BAIT_Z:
            break
        out = k + 1
    return out


def far_from_rest(asks):
    low = bait_count(asks)
    return low, asks[low][0] * FAR_HIGH if asks else math.inf


def floor_of(asks):
    return asks[far_from_rest(asks)[0]][0] if asks else None


def scan_price(asks):
    total = sum(c for _, c in asks)
    take, run, last = [], 0, None
    for u, c in asks:
        if take and (run >= CHEAP_MOST * total or (run >= CHEAP_ALWAYS * total and u >= last * JUMP)):
            break
        take.append((u, c))
        run += c
        last = u
    mean = sum(u * c for u, c in take) / run
    sd = math.sqrt(sum(c * (u - mean) ** 2 for u, c in take) / run)
    kept = [(u, c) for u, c in take if not sd or abs(u - mean) <= TRIM_SD * sd] or take
    price = sum(u * c for u, c in kept) / sum(c for _, c in kept)
    logs = [math.log(u) for u, _ in kept]
    mid = median(logs)
    noise = max(R_FLOOR, (MAD_SIGMA * median([abs(v - mid) for v in logs])) ** 2 / len(kept))
    return price, noise, len(kept)


def reading(rows, front_before=None, hours=None):
    asks = sorted((a[3] / a[2], a[2]) for a in rows if a[3] > 0 and a[2] > 0)
    bait, top = far_from_rest(asks)
    counted = [a for a in rows if not (a[3] > 0 and a[2] > 0 and a[3] / a[2] > top)]
    asks = [s for s in asks if s[0] <= top]
    out = [0, None, None, 0, None, None, None, None, sum(a[2] for a in counted), len(counted), 0, [], None, None, 0]
    if asks:
        out[R_LOW] = round(asks[0][0], 2)
        out[R_WALL] = sum(c for u, c in asks if u <= asks[0][0] * WALL_NEAR)
        out[R_P10], out[R_P50], out[R_P90] = (round(quantile(asks, s), 2) for s in (0.1, 0.5, 0.9))
        out[R_BAIT] = bait
        if count_asks(counted) >= ASKS_LEAST and len(asks) > bait:
            price, noise, kept = scan_price(asks[bait:])
            out[R_PRICE], out[R_NOISE], out[R_KEPT] = round(price, 2), round(noise, 8), kept
        out[R_FRONT] = [[a[2], a[3]] for a in sorted((a for a in rows if a[3] > 0 and a[2] > 0),
                                                      key=lambda a: a[3] / a[2])[:FRONT]]
    if front_before:
        have = collections.Counter((a[2], a[3]) for a in rows)
        was = collections.Counter((c, b) for c, b in front_before)
        out[R_SURVIVE] = [len(front_before), sum(min(n, have[k]) for k, n in was.items()), round(hours, 3)]
    return out


def readings(rows, fronts_before=None, hours=None, sales=None, pooled=frozenset()):
    by = collections.defaultdict(list)
    for a in rows:
        if not a[5] & AUCTION_NOKEY:
            by[row_key(a[0], a[1], pooled)].append(a)
    fronts_before = fronts_before or {}
    out = {k: reading(v, fronts_before.get(k), hours) for k, v in by.items()}
    for k, front in fronts_before.items():
        if k not in out and front:
            out[k] = reading([], front, hours)
    for k, part in (sales or {}).items():
        if k not in out:
            out[k] = reading([], fronts_before.get(k), hours)
        out[k][R_SALES] = part
    return out



L_COUNT, L_BUY, L_SELLER, L_EARLIEST, L_LATEST, L_SINCE, L_BID = range(7)


def band_window(band, t, bands):
    if band is None:
        return t, math.inf
    return t + bands[band], (t + bands[band + 1]) if band + 1 < len(bands) else math.inf


def listed(rows, t, bands, one_based, pooled=frozenset()):
    out = collections.defaultdict(list)
    for item, bonus, count, buy, _, flags, seller in rows:
        if buy > 0 and count > 0 and not flags & (AUCTION_SOLD | AUCTION_NOKEY):
            lo, hi = band_window(band_of(flags, one_based), t, bands)
            out[row_key(item, bonus, pooled)].append([count, buy, seller or "", lo, hi, t, bool(flags & AUCTION_BID)])
    return dict(out)


def expiry_share(o, tb, longest):
    lo, hi = o[L_EARLIEST], min(o[L_LATEST], max(o[L_EARLIEST], o[L_SINCE] + longest))
    return 0.0 if tb <= lo else 1.0 if tb >= hi else (tb - lo) / (hi - lo)


def same_seller(a, b):
    return a == b or not a or not b


def pair_item(was, now, ta, tb, longest):
    gap = tb - ta
    by_key = collections.defaultdict(list)
    for o in was:
        by_key[(o[L_COUNT], o[L_BUY])].append(o)
    news = collections.defaultdict(list)
    for n in now:
        news[(n[L_COUNT], n[L_BUY])].append(n)
    fresh, kept, gone, seen = [], [], [], 0
    for key in by_key.keys() | news.keys():
        olds = sorted(by_key.get(key, ()), key=lambda o: o[L_EARLIEST])
        ready, i = [], 0
        alone = len(olds) == 1 and len(news.get(key, ())) == 1
        for n in sorted(news.get(key, ()), key=lambda n: n[L_LATEST]):
            while i < len(olds) and olds[i][L_EARLIEST] <= n[L_LATEST]:
                heapq.heappush(ready, (-olds[i][L_LATEST], i))
                i += 1
            aside, got = [], None
            while ready and -ready[0][0] >= n[L_EARLIEST]:
                top = heapq.heappop(ready)
                if same_seller(olds[top[1]][L_SELLER], n[L_SELLER]):
                    got = olds[top[1]]
                    break
                aside.append(top)
            for top in aside:
                heapq.heappush(ready, top)
            if got is None:
                fresh.append(n)
                continue
            kept.append(got)
            n[L_EARLIEST], n[L_LATEST] = max(n[L_EARLIEST], got[L_EARLIEST]), min(n[L_LATEST], got[L_LATEST])
            if alone and got[L_EARLIEST] > tb:
                n[L_SINCE] = got[L_SINCE]
                seen = max(seen, n[L_EARLIEST] - n[L_SINCE])
            n[L_SELLER] = n[L_SELLER] or got[L_SELLER]
        gone.extend(olds[j] for _, j in ready)
        gone.extend(olds[i:])
    front = {id(o) for o in sorted(was, key=lambda o: o[L_BUY] / o[L_COUNT])[:FRONT]}
    sold = expired = cancelled = front_sold = 0.0
    units = n_gone = 0
    ref = floor_of(sorted((o[L_BUY] / o[L_COUNT], o[L_COUNT]) for o in was))
    placed = collections.defaultdict(float)

    def add(o, count, w, p_exp):
        nonlocal sold, expired, cancelled, front_sold, units, n_gone
        s = count * ((1 - p_exp) * w + (p_exp if o[L_BID] else 0))
        sold += s
        if s > 0:
            placed[round(o[L_BUY] / o[L_COUNT] / ref, PLACE_DIGITS)] += s
        expired += 0 if o[L_BID] else count * p_exp
        cancelled += count * (1 - p_exp) * (1 - w)
        units += count
        n_gone += 1
        if id(o) in front:
            front_sold += s

    by_unit = collections.defaultdict(list)
    for f in sorted(fresh, key=lambda f: f[L_COUNT]):
        by_unit[round(f[L_BUY] / f[L_COUNT], 6)].append(f)
    whole = []
    for g in sorted(gone, key=lambda g: -g[L_COUNT]):
        rest, at = by_unit.get(round(g[L_BUY] / g[L_COUNT], 6), []), None
        for i, f in enumerate(rest):
            if f[L_COUNT] >= g[L_COUNT]:
                break
            if f[L_BUY] * g[L_COUNT] == g[L_BUY] * f[L_COUNT] and f[L_EARLIEST] <= g[L_LATEST] \
                    and g[L_EARLIEST] <= f[L_LATEST] and same_seller(f[L_SELLER], g[L_SELLER]):
                at = i
                break
        if at is None:
            whole.append(g)
            continue
        f = rest.pop(at)
        f[L_EARLIEST], f[L_LATEST] = max(f[L_EARLIEST], g[L_EARLIEST]), min(f[L_LATEST], g[L_LATEST])
        add(g, g[L_COUNT] - f[L_COUNT], W_SALE, 0.0)
        kept.append(g)
    fresh = [f for rest in by_unit.values() for f in rest]
    there = sorted(o[L_BUY] / o[L_COUNT] for o in [*kept, *fresh])
    again_of = collections.defaultdict(list)
    for f in sorted(fresh, key=lambda f: f[L_BUY]):
        again_of[f[L_COUNT]].append(f)
    for g in sorted(whole, key=lambda g: -g[L_BUY] / g[L_COUNT]):
        unit, same, at = g[L_BUY] / g[L_COUNT], again_of.get(g[L_COUNT], []), None
        for i, f in enumerate(same):
            if f[L_BUY] >= g[L_BUY]:
                break
            if same_seller(f[L_SELLER], g[L_SELLER]):
                at = i
                break
        if at is not None:
            same.pop(at)
            w = W_RELIST
        elif not there:
            w = W_ALONE
        else:
            w = W_CANCEL + (W_SALE - W_CANCEL) * (len(there) - bisect.bisect_left(there, unit)) / len(there)
        add(g, g[L_COUNT], w, expiry_share(g, tb, longest))
    listed_at = collections.defaultdict(int)
    for f in fresh:
        listed_at[round(f[L_BUY] / f[L_COUNT] / ref, PLACE_DIGITS) if ref else 1.0] += f[L_COUNT]
    out = [round(gap / HOUR, 3), n_gone, units] + [round(v, 2) for v in (expired, sold, cancelled, front_sold)] + \
        [sum(f[L_COUNT] for f in fresh), sum(u for r, u in listed_at.items() if r <= 1),
         [[r, round(u, 2)] for r, u in sorted(placed.items()) if round(u, 2) > 0],
         [[r, u] for r, u in sorted(listed_at.items())]]
    return out, seen


def reckon_pair(carried, rows, ta, tb, bands, longest, one_based, pooled=frozenset(), cut=frozenset()):
    now = listed(rows, tb, bands, one_based, pooled)
    sales, longest = {}, max(longest, bands[-1])
    seen = longest
    for key, was in carried.items():
        if int(key.split(":")[0]) in cut:
            continue
        part, most = pair_item(was, now.get(key, []), ta, tb, longest)
        sales[key] = part
        seen = max(seen, most)
    return sales, now, seen



def breaks_between(breaks, a, b):
    return bisect.bisect_right(breaks, b) - bisect.bisect_right(breaks, a)


def log_normal(y, mu, var):
    return -0.5 * (math.log(2 * math.pi * var) + (y - mu) ** 2 / var)


def run_filter(points, q, breaks=(), start=None):
    state, out = start, []
    for t, y, noise in points:
        row = {"t": t, "used": y is not None, "z": None}
        if state is None:
            if y is None:
                row.update(level=None, P=None, before=None)
                out.append(row)
                continue
            state = (t, y, noise)
            row.update(level=y, P=noise, before=None)
            out.append(row)
            continue
        t0, mu, p = state
        pred = p + q * max(0.0, t - t0) / HOUR + BREAK_P * breaks_between(breaks, t0, t)
        row["before"] = pred
        if y is None:
            row.update(level=mu, P=pred)
            out.append(row)
            state = (t, mu, pred)
            continue
        s = pred + noise
        gain = pred / s
        row["z"] = (y - mu) / math.sqrt(s)
        mu = mu + gain * (y - mu)
        p = (1 - gain) * pred
        state = (t, mu, p)
        row.update(level=mu, P=p)
        out.append(row)
    return out, state


def at_time(state, t, q, breaks=()):
    t0, mu, p = state
    return mu, p + q * max(0.0, t - t0) / HOUR + BREAK_P * breaks_between(breaks, t0, t)


def interval(mu, p, c=Z90):
    sd = math.sqrt(max(p, 0.0))
    return math.exp(mu), math.exp(mu - c * sd), math.exp(mu + c * sd)


def gap_edges(bands, longest):
    return sorted({b / HOUR for b in bands[1:] if b > 0} | ({longest / HOUR} if longest else set()))


def gap_bin(hours, edges):
    return bisect.bisect_left(edges, hours)


def kind_of(key, classes=None):
    if classes is None:
        import gamedata
        classes = gamedata.item_classes()
    return "pooled" if (classes[3].get(str(key).split(":")[0]) or 0) > 1 else "single"


def multiple(model, sd, hours=0.0, kind=None):
    cal = (model or {}).get("calib") or {}
    k = bisect.bisect_right(CAL_EDGES, sd)
    cell = f"{k}.{gap_bin(hours, cal.get('gaps') or [])}.{kind}"
    by = cal.get("c") or []
    if (cal.get("cells") or {}).get(cell):
        return cal["cells"][cell], True
    if k < len(by) and by[k]:
        return by[k], False
    return cal.get("pooled") or Z90, False


def price_range(model, mu, p, noise, hours=0.0, kind=None):
    var = max(p, 0.0) + max(noise or 0.0, 0.0)
    c, measured = multiple(model, math.sqrt(var), hours, kind)
    return (*interval(mu, var, c), measured)


def noise_now(readings, floor):
    for r in reversed(readings):
        if r[R_PRICE]:
            return max(r[R_NOISE] or 0.0, floor)
    return max(floor, R_FLOOR)


def quantile_of(values, share, weights=None):
    if not values:
        return None
    pairs = sorted(zip(values, weights or [1.0] * len(values)))
    want, run = share * (sum(w for _, w in pairs) + 1.0), 0.0
    for v, w in pairs:
        run += w
        if run >= want - 1e-12:
            return v
    return pairs[-1][0]


def lower_of(values, share, weights=None):
    got = quantile_of([-v for v in values], 1 - share, weights)
    return None if got is None else -got


def aged(times, now):
    return None if now is None else [math.exp(-max(0.0, now - t) / AGE_TAU) for t in times]


def calibrate(series, house, own, scored=None, gaps=(), now=None):
    fitted = [[] for _ in range(len(CAL_EDGES) + 1)]
    for k, pts in series.items():
        q, floor = own.get(k) or house or (Q_DEFAULT, R_FLOOR)
        state, before = None, None
        for t, y, noise, jumps in pts:
            noise = max(noise or 0.0, floor)
            if state is None:
                state, before = (t, y, noise), noise
                continue
            t0, mu, p = state
            pred = p + q * max(0.0, t - t0) / HOUR + BREAK_P * jumps
            var = pred + before
            fitted[bisect.bisect_right(CAL_EDGES, math.sqrt(var))].append(abs(y - mu) / math.sqrt(var))
            gain = pred / (pred + noise)
            state, before = (t, mu + gain * (y - mu), (1 - gain) * pred), noise
    past, cells = [[] for _ in fitted], collections.defaultdict(list)
    for t, sd, hours, kind, z in scored or ():
        k = bisect.bisect_right(CAL_EDGES, sd)
        past[k].append((t, z))
        cells[f"{k}.{gap_bin(hours, gaps)}.{kind}"].append((t, z))

    def held(rows):
        return round(quantile_of([z for _, z in rows], HELD, aged([t for t, _ in rows], now)), 4)

    def enough(rows):
        return len(rows) >= CAL_LEAST and len({t for t, _ in rows}) >= DECISIONS_LEAST

    def measured(old, seen):
        if enough(old):
            return held(old), True
        return (round(max(Z90, quantile_of(seen, HELD)), 4), False) if len(seen) >= CAL_LEAST else (None, False)
    got = [measured(o, s) for o, s in zip(past, fitted)]
    pooled = measured([x for xs in past for x in xs], [z for zs in fitted for z in zs])
    return {"edges": [round(e, 6) for e in CAL_EDGES], "gaps": [round(g, 4) for g in gaps],
            "cells": {c: held(rows) for c, rows in sorted(cells.items()) if enough(rows)},
            "n": [len(o) if p else len(s) for o, s, (_, p) in zip(past, fitted, got)],
            "c": [c for c, _ in got], "past": [p for _, p in got], "pooled": pooled[0], "pooledPast": pooled[1]}


def changes(points, q, breaks=()):
    runs, marks, last_t = [], [], None
    for j, (t, y, noise) in enumerate(points):
        if not runs:
            runs, last_t = [[0.0, y, noise, j]], t
            continue
        g = max(0.0, t - last_t) / HOUR
        hazard = min(1 - 1e-12, max(1e-12, 1 - math.exp(-CP_RATE * g)))
        jump = BREAK_P * breaks_between(breaks, last_t, t)
        best = max(runs, key=lambda r: r[0])
        grown, mass = [], max(r[0] for r in runs)
        total = mass + math.log(sum(math.exp(r[0] - mass) for r in runs))
        for w, mu, p, at in runs:
            pred = p + q * g + jump
            s = pred + noise
            gain = pred / s
            grown.append([w + math.log(1 - hazard) + log_normal(y, mu, s), mu + gain * (y - mu), (1 - gain) * pred, at])
        fresh = best[2] + q * g + jump + CP_JUMP
        gain = fresh / (fresh + noise)
        grown.append([total + math.log(hazard) + log_normal(y, best[1], fresh + noise), best[1] + gain * (y - best[1]),
                      (1 - gain) * fresh, j])
        top = max(r[0] for r in grown)
        norm = top + math.log(sum(math.exp(r[0] - top) for r in grown))
        runs = sorted(([r[0] - norm] + r[1:] for r in grown), key=lambda r: -r[0])[:CP_KEEP]
        lead = runs[0]
        if lead[3] > 0 and lead[3] < j and math.exp(lead[0]) >= CP_SURE and lead[3] not in marks:
            marks.append(lead[3])
        last_t = t
    return marks


def fit_noise(series, worth=Q_OWN):
    import numpy as np
    keys, lls, steps = None, [], 0
    for floor in FLOOR_GRID:
        keys, ll, steps = fit_q(series, floor)
        if not keys:
            return None, {}
        lls.append(ll)
    ll = np.stack(lls)
    total = ll.sum(axis=2)
    f, g = np.unravel_index(int(np.argmax(total)), total.shape)
    import gamedata
    classes = gamedata.item_classes()[0]
    sub = [tuple(classes.get(k.split(":")[0]) or ()) for k in keys]
    pooled = {}
    for s in set(sub):
        members = [i for i, x in enumerate(sub) if x == s]
        if s and len(members) >= 2:
            a, b = np.unravel_index(int(np.argmax(ll[:, :, members].sum(axis=2))), total.shape)
            pooled[s] = (float(Q_GRID[b]), float(FLOOR_GRID[a]))
    pairs = {}
    for i, k in enumerate(keys):
        if len(series[k]) >= worth:
            a, b = np.unravel_index(int(np.argmax(ll[:, :, i])), total.shape)
            pairs[k] = (float(Q_GRID[b]), float(FLOOR_GRID[a]))
        else:
            pairs[k] = pooled.get(sub[i]) or (float(Q_GRID[g]), float(FLOOR_GRID[f]))
    return (float(Q_GRID[g]), float(FLOOR_GRID[f])), pairs


def fit_q(series, floor=R_FLOOR):
    import numpy as np
    keys = [k for k, pts in series.items() if len(pts) >= 2]
    if not keys:
        return [], None, 0
    times = sorted({p[0] for k in keys for p in series[k]})
    col = {t: i for i, t in enumerate(times)}
    n, m = len(keys), len(times)
    y = np.full((n, m), np.nan)
    noise = np.ones((n, m))
    jumps = np.zeros((n, m))
    for i, k in enumerate(keys):
        for t, v, r, b in series[k]:
            y[i, col[t]], noise[i, col[t]], jumps[i, col[t]] = v, max(r, floor), b
    grid = np.array(Q_GRID)[:, None]
    mu = np.zeros((len(Q_GRID), n))
    p = np.full((len(Q_GRID), n), np.inf)
    started = np.zeros(n, dtype=bool)
    last = np.zeros(n)
    ll = np.zeros((len(Q_GRID), n))
    for j, t in enumerate(times):
        seen = ~np.isnan(y[:, j])
        if not seen.any():
            continue
        g = (t - last) / HOUR
        both = seen & started
        if both.any():
            pred = p[:, both] + grid * g[both] + BREAK_P * jumps[both, j]
            s = pred + noise[both, j]
            d = y[both, j] - mu[:, both]
            ll[:, both] += -0.5 * (np.log(2 * np.pi * s) + d * d / s)
            gain = pred / s
            mu[:, both] += gain * d
            p[:, both] = (1 - gain) * pred
        first = seen & ~started
        if first.any():
            mu[:, first] = y[first, j]
            p[:, first] = noise[first, j]
            started |= first
        last[seen] = t
    return keys, ll, sum(len(series[k]) - 1 for k in keys)


def fit_survival(rows):
    rows = [r for r in rows if r and r[0] and r[2] > 0]
    if not rows:
        return None
    import numpy as np
    distinct = list(dict.fromkeys(tuple(r) for r in rows))
    at = {r: i for i, r in enumerate(distinct)}
    index = np.array([at[tuple(r)] for r in rows], dtype=np.intp)
    best, rate = None, None
    for e in range(-60, 11):
        lam = 10 ** (e / 10)
        terms = []
        for n, kept, h in distinct:
            stay = math.exp(-lam * h)
            terms.append(kept * math.log(max(stay, 1e-300)) + (n - kept) * math.log(max(1 - stay, 1e-300)))
        ll = float(np.cumsum(np.array(terms)[index])[-1])
        if best is None or ll > best:
            best, rate = ll, lam
    return rate


def volatility(points):
    moves = [(b[0], (b[1] - a[1]) / math.sqrt((b[0] - a[0]) / HOUR)) for a, b in zip(points, points[1:]) if b[0] > a[0]]
    out = []
    for t, _ in moves:
        near = [z for at, z in moves if t - VOL_DAYS * DAY < at <= t]
        if len(near) >= VOL_LEAST:
            mid = median(near)
            out.append((t, MAD_SIGMA * median([abs(z - mid) for z in near]) * math.sqrt(24)))
    return out


def is_reset(r, z):
    s = r[R_SURVIVE]
    return bool(s and s[0] >= 2 and not s[1] and (z or 0) > RESET_Z)


def sales_of(r):
    return r[R_SALES] if len(r) > R_SALES else None


def state_of(change):
    return next(name for least, name in STATES if change > least)



def ladder(rows):
    asks = sorted((a[3] / a[2], a[2]) for a in rows if a[3] > 0 and a[2] > 0)
    top = far_from_rest(asks)[1]
    steps = collections.OrderedDict()
    for unit, count in asks:
        u = round(unit, 4)
        s = steps.setdefault(u, [u, 0, 0, unit > top])
        s[1] += count
        s[2] += 1
    return list(steps.values())


def walk(rows, share=1.0):
    out, units, cost = [], 0.0, 0.0
    for u, c in sorted((a[3] / a[2], a[2]) for a in rows if a[3] > 0 and a[2] > 0):
        units += c * share
        cost += u * c * share
        out.append((u, c, units, cost))
    return out


def depth(rows, want, share=1.0):
    taken = None
    for step in walk(rows, share):
        taken = step
        if step[2] >= want:
            break
    if taken is None or want <= 0:
        return None
    return {"units": taken[2], "cost": taken[3], "average": taken[3] / taken[2], "marginal": taken[0]}



def day_path(folder, day):
    return os.path.join(folder, f"{DAILY}{day}.json.gz")


def day_files(folder):
    return {name[len(DAILY):-len(".json.gz")]: path for name, path in playerstores.listing(folder).items()
            if name.startswith(DAILY) and name.endswith(".json.gz")}


def write_day(folder, day, head, lines):
    text = [jsontext.dumps(head)] + [f"{k}\t{jsontext.dumps(v)}" for k, v in sorted(lines.items())]
    os.makedirs(folder, exist_ok=True)
    store.write_bytes(day_path(folder, day), gzip.compress(("\n".join(text) + "\n").encode("utf-8"), 6))


def read_head(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.loads(f.readline())
    except (OSError, ValueError, EOFError):
        return None


def read_day(path, pool=None):
    try:
        text = gzip.decompress(open(path, "rb").read()).decode("utf-8").split("\n")
        head, lines = json.loads(text[0]), {}
        for line in text[1:]:
            if line:
                k, v = line.split("\t", 1)
                lines[k] = json.loads(v)
        return head, repooled(head, lines, pool)
    except (OSError, ValueError, EOFError):
        return None, {}


def repooled(head, lines, pool):
    if not pool or pool[1] is None or not head:
        return lines
    times = [s["t"] for s in head.get("scans", [])]
    out = {}
    for k, v in lines.items():
        for r in v.get("o") or ():
            got = out.setdefault(kept_key(k, times[r[R_SCAN]] if r[R_SCAN] < len(times) else None, pool), {})
            got.setdefault("o", []).append(r)
        if v.get("k"):
            got = out.setdefault(kept_key(k, v["k"][0], pool), {})
            if not got.get("k") or got["k"][0] < v["k"][0]:
                got["k"] = v["k"]
    for v in out.values():
        if "o" in v:
            v["o"].sort(key=lambda r: r[R_SCAN])
    return out


def item_lines(raw, end, keys):
    out = {}
    for key in keys:
        at = raw.find(b"\n" + key.encode() + b"\t", end - 1)
        if at >= 0:
            stop = raw.find(b"\n", at + 1)
            out[key] = json.loads(raw[at + len(key) + 2:stop if stop >= 0 else None])
    return out


def kept_keys(key, pool):
    item, _, tail = key.partition(":")
    if not pool or pool[1] is None or not item.isdigit() or int(item) not in pool[0] or (tail and tail != POOLED):
        return [key]
    return [item, f"{item}:{POOLED}"]


def read_item(path, key, pool=None):
    try:
        raw = gzip.decompress(open(path, "rb").read())
    except (OSError, EOFError):
        return None, None
    end = raw.find(b"\n")
    try:
        head = json.loads(raw[:end])
    except ValueError:
        return None, None
    return head, repooled(head, item_lines(raw, end, kept_keys(key, pool)), pool).get(key)


def load_model(folder):
    return store.load_json(playerstores.standing(os.path.join(folder, MODEL)), {})


def states_of(folder, keys, pool=None):
    states = {key: [] for key in keys}
    marks = {k.encode() + b"\t": k for key in keys for k in kept_keys(key, pool)}
    for _, path in sorted(day_files(folder).items()):
        try:
            with open(path, "rb") as f:
                raw = gzip.decompress(f.read())
        except (OSError, EOFError):
            continue
        for line in raw.split(b"\n")[1:]:
            tab = line.find(b"\t")
            key = marks.get(line[:tab + 1]) if tab > 0 else None
            if key is None:
                continue
            try:
                k = json.loads(line[tab + 1:]).get("k")
            except ValueError:
                continue
            if k and kept_key(key, k[0], pool) in states:
                states[kept_key(key, k[0], pool)].append(tuple(k))
    return {key: sorted(run) for key, run in states.items()}


def prices_at(folder, wanted, states=None, pool=None):
    model = load_model(folder)
    if states is None:
        states = states_of(folder, wanted, pool)
    out = {}
    for key, times in wanted.items():
        run, got = states.get(key) or [], {}
        starts = [s[0] for s in run]
        q, _ = noise_of(model, key)
        breaks = sorted((model.get("breaks") or {}).get(key.split(":")[0], []))
        for t in times:
            i = bisect.bisect_right(starts, t)
            got[t] = interval(*at_time(run[i - 1], t, q, breaks)) if i else None
        out[key] = got
    return out



def read_metas(house):
    with house.lock:
        return [dict(m) for m in house.scans if read_whole(m)]


def is_short(meta):
    return bool(meta.get("missing"))


def plan(house, files=None):
    files = day_files(house.folder) if files is None else files
    by_day = collections.defaultdict(list)
    for m in read_metas(house):
        by_day[day_of(m["started"])].append(m)
    first = None
    for day in sorted(by_day):
        head = read_head(files[day]) if day in files else None
        have = {s["id"]: bool(s.get("short")) for s in (head or {}).get("scans", [])}
        if not head or not head.get("states") or head.get("sales") != SALES_MARK or \
                any(have.get(m["id"]) != is_short(m) for m in by_day[day]) or any("bands" not in s for s in head.get("scans", [])):
            first = day
            break
    return [] if first is None else [(d, by_day[d]) for d in sorted(by_day) if d >= first]


def pending(house):
    import auctionmarket
    import backtest
    return bool(house.keep and (plan(house) or auctionmarket.due(house) or backtest.due(house)))


def scan_rows(house, sid):
    try:
        with gzip.open(house.scan_file(sid), "rt", encoding="utf-8") as f:
            d = json.load(f)
        sellers = d.get("sellers", [])
        return ([(r[0], r[1], r[2], r[3], r[4], r[5], sellers[r[6]] if r[6] < len(sellers) else None)
                 for rows in d.get("chunks", {}).values() for r in rows], d.get("bands") or list(BAND_LEAST))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def one_based(rows):
    return any(a[5] & AUCTION_BAND == 4 for a in rows)


def write_open(folder, scan, carried, longest):
    t = scan[1]
    items = {k: [[o[L_COUNT], o[L_BUY], o[L_SELLER], round(o[L_EARLIEST] - t), None if o[L_LATEST] == math.inf
                  else round(o[L_LATEST] - t), round(o[L_SINCE] - t), int(o[L_BID])] for o in v] for k, v in carried.items()}
    os.makedirs(folder, exist_ok=True)
    store.write_bytes(os.path.join(folder, OPEN), gzip.compress(
        jsontext.dumps({"scan": scan[0], "t": t, "longest": longest, "items": items}).encode("utf-8"), 6))


def carried_before(house, scan):
    try:
        with gzip.open(mainstores.standing(os.path.join(house.folder, OPEN)), "rt", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("scan") == scan[0]:
            t, pool, out = d["t"], house.pool, {}
            for k, v in d["items"].items():
                out.setdefault(kept_key(k, t, pool), []).extend(
                    [c, b, s, t + lo, math.inf if hi is None else t + hi, t + since, bool(bid)] for c, b, s, lo, hi, since, bid in v)
            return out, d.get("longest")
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        pass
    got = scan_rows(house, scan[0])
    if got is None:
        return None, None
    return listed(got[0], scan[1], got[1], one_based(got[0]), pooled_in(marked(house, scan[0]), house.pool[0])), None


def marked(house, sid):
    meta = house.meta(sid)
    return bool(meta and meta.get("keys"))


def item_breaks(builds):
    out = collections.defaultdict(list)
    for b in builds or ():
        items = (b.get("changes") or {}).get("items") or {}
        for kind in ("new", "changed"):
            for entry in items.get(kind) or ():
                if isinstance(entry, list) and entry:
                    out[str(entry[0])].append(b.get("date") or 0)
    return {k: sorted(set(v)) for k, v in out.items()}


_builds = {"at": None, "builds": []}


def known_builds():
    path = mainstores.standing(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "patches.json"))
    try:
        at = os.path.getmtime(path)
    except OSError:
        return []
    if _builds["at"] != at:
        _builds.update(at=at, builds=store.load_json(path, {}).get("builds") or [])
    return _builds["builds"]


def keep_line(scans, kept, obs, i, line, got):
    if i is None:
        i = len(scans)
        scans.append(line)
        kept[line["id"]] = i
    else:
        scans[i] = line
        for k in list(obs):
            obs[k] = [r for r in obs[k] if r[R_SCAN] != i]
            if not obs[k]:
                del obs[k]
    for k, r in got.items():
        r[R_SCAN] = i
        obs.setdefault(k, []).append(r)
    return i


def summarise(house, builds=None, stop=None, now=time.time):
    import auctionmarket
    import backtest
    began, folder = time.time(), house.folder
    files = day_files(folder)
    days = plan(house, files)
    breaks = item_breaks(known_builds() if builds is None else builds)
    if not days:
        scored = backtest.due(house)
        if scored:
            backtest.run(house, files, now)
        model = load_model(folder)
        if scored or model.get("mark") != MODEL_MARK:
            model = fit_model(house, files, breaks, now())
        if auctionmarket.due(house, files):
            auctionmarket.market(house, model, files, breaks)
        return {"days": 0, "scans": 0, "seconds": time.time() - began}
    read = 0
    first = days[0][0]
    before = sorted(d for d in files if d < first)
    fronts, front_t = {}, None
    prev, longest = None, None
    prev_keys = False
    for day in reversed(before):
        head, lines = read_day(files[day], house.pool)
        whole_at = [i for i, s in enumerate((head or {}).get("scans") or ()) if not s.get("short")]
        if whole_at:
            last_i = whole_at[-1]
            last = head["scans"][last_i]
            front_t = last["t"]
            fronts = {k: r[R_FRONT] for k, v in lines.items() for r in v.get("o", ()) if r[R_SCAN] == last_i and r[R_FRONT]}
            prev, longest = (last["id"], front_t), head.get("longest")
            prev_keys = bool(last.get("keys"))
            break
    carried = None
    import gamedata
    stacks = gamedata.item_classes()[3]
    for day, metas in days:
        had = day in files
        head, lines = read_day(files[day], house.pool) if had else (None, {})
        if had and not head:
            bad = files[day] + ".bad"
            try:
                os.replace(files[day], bad)
            except OSError:
                log_error(f"the auction house day {day} of {house.key} can't be read and can't be set aside: the pass "
                          f"stopped before it wrote anything")
                return {"days": 0, "scans": read, "seconds": time.time() - began, "failed": True}
            log_error(f"the auction house day {day} of {house.key} can't be read: set aside as {os.path.basename(bad)} "
                      f"and read again from its scans")
            had, head, lines = False, None, {}
        redo = bool(head) and (head.get("sales") != SALES_MARK or any("bands" not in s for s in head["scans"]))
        kept = {s["id"]: i for i, s in enumerate((head or {}).get("scans", []))}
        scans = [dict(s) for s in (head or {}).get("scans", [])]
        obs = {k: list(v.get("o", ())) for k, v in lines.items() if v.get("o")}
        fresh = False
        for m in sorted(metas, key=lambda m: m["started"]):
            if stop and stop():
                return {"days": 0, "scans": read, "seconds": time.time() - began, "stopped": True}
            i = kept.get(m["id"])
            short = is_short(m)
            if i is not None and not redo and scans[i].get("before") == (prev[0] if prev else None) and \
                    bool(scans[i].get("short")) == short:
                if not short:
                    fronts = {k: r[R_FRONT] for k, v in obs.items() for r in v if r[R_SCAN] == i and r[R_FRONT]}
                    front_t, prev, carried = m["started"], (m["id"], m["started"]), None
                    prev_keys = bool(scans[i].get("keys"))
                    longest = scans[i].get("longest") or longest
                continue
            got_file = scan_rows(house, m["id"])
            if got_file is None:
                log_error(f"the auction house scan {m['id']} of {house.key} can't be read: its line says so, and its "
                          f"auctions are in none of the prices or the sales")
                keep_line(scans, kept, obs, i, {"id": m["id"], "t": m["started"], "by": m.get("by"),
                                                "byFrom": m.get("byFrom"), "auctions": m.get("auctions"),
                                                "before": prev[0] if prev else None, "bids": 0, "over": 0,
                                                "bands": list(BAND_LEAST), "lost": True}, {})
                fresh = True
                continue
            rows, bands = got_file
            sales = None
            keys_now, suffixed = bool(m.get("keys")), house.pool[0]
            pooled = pooled_in(keys_now, suffixed)
            if short:
                got = readings(rows, None, None, None, pooled)
            else:
                cut = pair_cut(prev_keys if prev else keys_now, keys_now, suffixed, {a[0] for a in rows if a[5] & AUCTION_NOKEY})
                if prev and carried is None:
                    carried, kept_longest = carried_before(house, prev)
                    longest = max(longest or 0, kept_longest or 0) or None
                if prev and carried is not None:
                    sales, carried, longest = reckon_pair(carried, rows, prev[1], m["started"], bands, longest or 0,
                                                          one_based(rows), pooled, cut)
                else:
                    carried = listed(rows, m["started"], bands, one_based(rows), pooled)
                fronts = {k: f for k, f in fronts.items() if int(k.split(":")[0]) not in cut}
                got = readings(rows, fronts, (m["started"] - front_t) / HOUR if front_t else None, sales, pooled)
            bids = sum(1 for a in rows if a[5] & (AUCTION_MIN_BID | AUCTION_BID))
            over = sum(1 for a in rows if a[2] > (stacks.get(str(a[0])) or a[2]))
            del rows
            line = {"id": m["id"], "t": m["started"], "by": m.get("by"), "byFrom": m.get("byFrom"),
                    "auctions": m.get("auctions"), "before": prev[0] if prev else None, "bids": bids, "over": over,
                    "bands": bands, "longest": longest, **({"keys": True} if keys_now else {}),
                    **({"short": True} if short else {})}
            keep_line(scans, kept, obs, i, line, got)
            if not short:
                prev_keys = keys_now
                fronts = {k: r[R_FRONT] for k, r in got.items() if r[R_FRONT]}
                front_t, prev = m["started"], (m["id"], m["started"])
            read += 1
            fresh = True
        if fresh or not head or redo:
            order = sorted(range(len(scans)), key=lambda i: scans[i]["t"])
            renum = {old: new for new, old in enumerate(order)}
            scans = [scans[i] for i in order]
            for rows in obs.values():
                for r in rows:
                    r[R_SCAN] = renum[r[R_SCAN]]
                rows.sort(key=lambda r: r[R_SCAN])
            write_day(folder, day, {"day": day, "house": house.key, "scans": scans, "states": False,
                                    "sales": SALES_MARK, "longest": longest},
                      {k: {"o": v} for k, v in obs.items()})
            files[day] = day_path(folder, day)
            if carried is not None and house.keep:
                write_open(folder, prev, carried, longest)
    backtest.run(house, files, now)
    model = fit_model(house, files, breaks, now())
    states = {}
    if before:
        _, lines = read_day(files[before[-1]], house.pool)
        states = {k: v["k"] for k, v in lines.items() if v.get("k")}
    for day, _ in days:
        if stop and stop():
            return {"days": len(days), "scans": read, "seconds": time.time() - began, "stopped": True}
        head, lines = read_day(files[day], house.pool)
        if not head:
            continue
        times = [s["t"] for s in head["scans"]]
        out = {}
        for k, v in lines.items():
            rows = v.get("o") or []
            if not rows:
                continue
            q, floor = noise_of(model, k)
            pts = points([(times[r[R_SCAN]], r) for r in rows], floor)
            _, state = run_filter(pts, q, breaks.get(k.split(":")[0], ()), tuple(states[k]) if k in states else None)
            if state:
                states[k] = [state[0], round(state[1], 6), round(state[2], 8)]
            out[k] = {"o": rows}
        for k, s in states.items():
            out.setdefault(k, {})["k"] = s
        write_day(folder, day, {**head, "states": True, "noise": model["q"]["house"]}, out)
    auctionmarket.market(house, model, files, breaks)
    return {"days": len(days), "scans": read, "seconds": time.time() - began}


def noise_of(model, key):
    q = (model or {}).get("q") or {}
    got = q.get("items", {}).get(key) or q.get("house") or (Q_DEFAULT, R_FLOOR)
    return got[0], got[1]


def points(rows, floor):
    return [(t, math.log(r[R_PRICE]) if r[R_PRICE] else None, max(r[R_NOISE] or 0, floor)) for t, r in rows]


def fit_series(series, scored=None, gaps=(), now=None):
    pooled, own = fit_noise(series) if series else (None, {})
    return {"q": {"house": list(pooled or (Q_DEFAULT, R_FLOOR)), "fitted": pooled is not None,
                  "items": {k: list(v) for k, v in own.items()}},
            "calib": calibrate(series, pooled, own, scored, gaps, now)}


def fit_model(house, files, breaks, now):
    since = day_of(now - FIT_DAYS * DAY)
    series, survive, bands, longest = collections.defaultdict(list), [], BAND_LEAST, None
    for day in sorted(d for d in files if d >= since):
        head, lines = read_day(files[day], house.pool)
        if not head:
            continue
        times = [s["t"] for s in head["scans"]]
        bands = next((s["bands"] for s in reversed(head["scans"]) if s.get("bands")), bands)
        longest = head.get("longest") or longest
        for k, v in lines.items():
            for r in v.get("o", ()):
                if r[R_SURVIVE]:
                    survive.append(r[R_SURVIVE])
                if r[R_PRICE]:
                    series[k].append((times[r[R_SCAN]], math.log(r[R_PRICE]), r[R_NOISE]))
    for k, pts in series.items():
        pts.sort()
        b = breaks.get(k.split(":")[0], ())
        series[k] = [(t, y, r, breaks_between(b, pts[i - 1][0], t) if i else 0) for i, (t, y, r) in enumerate(pts)]
    import backtest
    scored = ((backtest.load(house.folder) or {}).get("scored") or {}).get("price")
    model = {**fit_series(series, scored, gap_edges(bands, longest), now), "survive": {"house": fit_survival(survive)},
             "breaks": breaks, "made": now,
             "mark": MODEL_MARK}
    if house.keep:
        os.makedirs(house.folder, exist_ok=True)
        store.save_json(os.path.join(house.folder, MODEL), model, indent=None)
    return model



def series(folder, key, since, pool=None):
    files = day_files(folder)
    days = sorted(files)
    first = day_of(since) if since else (days[0] if days else "")
    use = [d for d in days if d >= first]
    earlier = [d for d in days if d < first]
    start = None
    if earlier:
        _, line = read_item(files[earlier[-1]], key, pool)
        start = tuple(line["k"]) if line and line.get("k") else None
    out = []
    for day in use:
        head, line = read_item(files[day], key, pool)
        if not head or not line:
            continue
        for r in line.get("o", ()):
            s = head["scans"][r[R_SCAN]]
            out.append({"t": s["t"], "id": s["id"], "by": s.get("by"), "byFrom": s.get("byFrom"), "reading": r})
    out.sort(key=lambda s: s["t"])
    return out, start, len(use)


class Summaries:

    def __init__(self, spawn, apart=workers.apart):
        self.spawn, self.apart, self.lock, self.going, self.last, self.asked = \
            spawn, apart, threading.Lock(), set(), {}, set()

    def start(self, house, redo=False):
        if not house or not house.keep:
            return False
        with self.lock:
            if house.key in self.going:
                if redo:
                    self.asked.add(house.key)
                return True
            if not pending(house):
                return False
            self.going.add(house.key)

        def work():
            again = False
            try:
                self.last[house.key] = self.apart(summarise, house, what="auction house pass")
            except Exception:
                log_error(f"summarising the auction house {house.key}")
            finally:
                with self.lock:
                    self.going.discard(house.key)
                    again = house.key in self.asked
                    self.asked.discard(house.key)
            if again:
                self.start(house, redo=True)
        self.spawn(work)
        return True

    def running(self, key):
        with self.lock:
            return key in self.going
