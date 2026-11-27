# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import hashlib
import math
import os
import time

import numpy as np

import auctiondays as ad
import mainstores
import store
from dayrecord import day_of

GAP_FULL = 12 * ad.HOUR
DAY_HOURS = 24
FIT_ROUNDS = 50
VOLUME_DAYS = 30
VOLUME_TAU = ad.AGE_TAU
PRIOR_SALES = 2
SPREAD_LEAST = 100
LEVEL_EDGE = 1e-4
RATE_EDGES = (1.0, 10.0)
MARK = 9
PRIOR_LEAST = 0.1
LOW_Q, HIGH_Q = 0.05, 0.95
HEAT_LEAST = 3
WEEK_SPAN = 3.5 * ad.DAY
STACK_SCANS = 3
MARKET = "market.json"



def gamma_p(a, x):
    if x <= 0:
        return 0.0
    scale = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1:
        ap, d = a, 1.0 / a
        total = d
        for _ in range(1000):
            ap += 1
            d *= x / ap
            total += d
            if abs(d) < abs(total) * 1e-12:
                break
        return min(1.0, total * scale)
    b, c, d = x + 1 - a, 1e300, 1 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = b + an / c
        c = c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return max(0.0, 1 - scale * h)


def gamma_quantile(a, rate, p):
    lo, hi = 0.0, max(1.0, 2 * a / rate)
    while gamma_p(a, rate * hi) < p:
        hi *= 2
    for _ in range(64):
        mid = (lo + hi) / 2
        if gamma_p(a, rate * mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2



def fit_sales(parts, edges, scored=None, now=None, place=ad.S_SOLD, classes=None):
    aged = lambda t: 1.0 if now is None else math.exp(-max(0.0, now - t) / VOLUME_TAU)
    obs = [(k, ad.gap_bin(p[ad.S_HOURS], edges), max(0.0, p[place]), aged(t)) for k, rows in parts.items()
           for t, p in rows if p and p[ad.S_HOURS] > 0 and len(p) > place]
    bins = len(edges) + 1
    day = ad.gap_bin(DAY_HOURS, edges)
    seen = [1.0] * bins
    used = {b for _, b, _, _ in obs}
    keys = list(dict.fromkeys(k for k, _, _, _ in obs))
    at = {k: i for i, k in enumerate(keys)}
    ki = np.array([at[k] for k, _, _, _ in obs], dtype=np.intp)
    bi = np.array([b for _, b, _, _ in obs], dtype=np.intp)
    sv = np.array([s for _, _, s, _ in obs], dtype=float)
    sold = np.bincount(ki, weights=sv, minlength=len(keys))
    top = np.bincount(bi, weights=sv, minlength=bins).tolist()
    lam = np.zeros(len(keys))
    for _ in range(FIT_ROUNDS):
        lam = sold / np.bincount(ki, weights=np.array(seen)[bi], minlength=len(keys))
        under = np.bincount(bi, weights=lam[ki], minlength=bins).tolist()
        seen = [top[b] / under[b] if under[b] > 0 and top[b] > 0 else seen[b] for b in range(bins)]
        base = seen[day] if day in used else seen[min(used, key=lambda b: abs(b - day))] if used else 1.0
        seen = [v / base for v in seen]
    lam = dict(zip(keys, lam.tolist()))
    size = {k: units_of([p for _, p in rows]) for k, rows in parts.items()}
    n = collections.Counter(k for k, _, _, _ in obs)
    kinds = {k: ad.kind_of(k, classes) for k in n}
    moments = collections.defaultdict(lambda: [0.0, 0.0, 0])
    hours = collections.defaultdict(lambda: [0.0, 0, set()])
    for k, rows in parts.items():
        for t, p in rows:
            if p and p[ad.S_HOURS] > 0 and len(p) > place:
                h = hours[ad.gap_bin(p[ad.S_HOURS], edges)]
                h[0] += p[ad.S_HOURS]
                h[1] += 1
                h[2].add(t)
    for k, b, s, w in obs:
        if n[k] < 2:
            continue
        e, m = s / size[k], lam.get(k, 0.0) * seen[b] / size[k]
        for cell in (str(b), f"{b}.{kinds[k]}", "all"):
            got = moments[cell]
            got[0] += w * ((e - m) ** 2 * n[k] / (n[k] - 1) - e)
            got[1] += w * m * m
            got[2] += 1
    shape = lambda c: round(c[1] / c[0], 4) if c[0] > 0 and c[1] > 0 and c[2] >= SPREAD_LEAST else None
    pits = collections.defaultdict(list)
    for t, b, rate, kind, pit in scored or ():
        pits[f"{int(b)}.{int(rate)}.{kind}"].append((t, pit))
    cells = {c: levels_of([p for _, p in v], ad.aged([t for t, _ in v], now), len({t for t, _ in v}))
             for c, v in sorted(pits.items())}
    return {"edges": [round(e, 4) for e in edges], "seen": [round(seen[b], 5) if b in used else None for b in range(bins)],
            "hours": [round(hours[b][0] / hours[b][1], 3) if hours[b][1] else None for b in range(bins)],
            "scans": [len(hours[b][2]) for b in range(bins)],
            "day": day, "k": {c: shape(v) for c, v in moments.items() if c != "all" and shape(v)},
            "kAll": shape(moments["all"]) if "all" in moments else None, "levels": {c: v for c, v in cells.items() if v},
            "pairs": len(obs), "items": len(n)}


def rate_class(day):
    return sum(day >= e for e in RATE_EDGES)


def levels_of(pits, weights=None, decisions=None):
    if len(pits) < ad.CAL_LEAST or (decisions is not None and decisions < ad.DECISIONS_LEAST):
        return None
    edge = lambda v: round(min(max(v, LEVEL_EDGE), 1 - LEVEL_EDGE), 5)
    return [edge(ad.lower_of(pits, LOW_Q, weights)), edge(ad.quantile_of(pits, HIGH_Q, weights))]


def at_gap(values, b):
    known = [i for i, v in enumerate(values or []) if v is not None]
    return values[min(known, key=lambda i: abs(i - b))] if known else None


def seen_share(fit, hours):
    got = at_gap((fit or {}).get("seen"), ad.gap_bin(hours, (fit or {}).get("edges") or []))
    return 1.0 if got is None else got


def pace_of(fit):
    seen, hours, scans = (fit or {}).get("seen") or [], (fit or {}).get("hours") or [], (fit or {}).get("scans") or []
    edges = (fit or {}).get("edges") or []
    upper = lambda b: edges[b] if b < len(edges) else None
    day = ad.gap_bin(DAY_HOURS, edges)
    anchor = day if 0 <= day < len(seen) and seen[day] else \
        min((b for b, s in enumerate(seen) if s), key=lambda b: abs(b - day), default=None)
    pace = 1.0 / (hours[anchor] if anchor is not None and anchor < len(hours) and hours[anchor] else DAY_HOURS)
    for b, (s, h, n) in enumerate(zip(seen, hours, scans)):
        if s and h and n >= ad.DECISIONS_LEAST:
            return pace, upper(b)
    edge = upper(day)
    return pace, DAY_HOURS if edge is None else edge


def spread_shape(fit, hours, kind=None):
    got = (fit or {}).get("k") or {}
    b = ad.gap_bin(hours, (fit or {}).get("edges") or [])
    return got.get(f"{b}.{kind}") or got.get(str(b)) or (fit or {}).get("kAll")


def units_of(sales):
    gone = sum(p[ad.S_GONE] for p in sales if p)
    units = sum(p[ad.S_UNITS] for p in sales if p)
    return max(1.0, units / gone) if gone else 1.0



def evidence(parts, now, fit, place=ad.S_SOLD):
    parts = [x for x in parts if len(x[1]) > place]
    u = units_of([p for _, p, _ in parts])
    out = {"events": 0.0, "seen": 0.0, "units": u, "pairs": 0, "short": 0, "reset": 0.0, "at": collections.defaultdict(float)}
    places = ad.S_PRICES if place == ad.S_SOLD else ad.S_LISTED if place == ad.S_UNDER else None
    for t, p, reset in parts:
        w = math.exp(-max(0.0, now - t) / VOLUME_TAU)
        apart = p[ad.S_FRONT] if reset and place == ad.S_SOLD else 0.0
        out["events"] += w * max(0.0, p[place] - apart) / u
        out["seen"] += w * seen_share(fit, p[ad.S_HOURS])
        out["reset"] += apart
        out["pairs"] += 1
        out["short"] += p[ad.S_HOURS] * ad.HOUR <= GAP_FULL
        if places is not None and len(p) > places:
            for r, units in p[places]:
                out["at"][r] += w * units / u
    return out


def above_of(at):
    run, out = 0.0, []
    for r in sorted(at, reverse=True):
        run += at[r]
        if r > 1:
            out.append([r, round(run, 4)])
    return out[::-1], round(sum(at.values()), 4)


def below_of(at):
    run, out = 0.0, []
    for r in sorted(at):
        if r > 1:
            run += at[r]
            out.append([r, round(run, 4)])
    return out


def posterior(ev, prior):
    rate = max(prior, PRIOR_LEAST) / ev["units"]
    b0 = min(1.0, PRIOR_SALES / rate)
    return rate * b0 + ev["events"], b0 + ev["seen"]


def nb_quantiles(mean, var, shares):
    if mean <= 0:
        return [0 for _ in shares]
    if var <= mean * (1 + 1e-9):
        logp, step = -mean, lambda n: math.log(mean) - math.log(n + 1)
    else:
        r = mean * mean / (var - mean)
        keep = r / (r + mean)
        logp, step = r * math.log(keep), lambda n: math.log(n + r) - math.log(n + 1) + math.log(1 - keep)
    got, total, n, want = {}, 0.0, 0, sorted(shares)
    while want and n <= 10 ** 7:
        total += math.exp(logp)
        while want and total >= want[0] - 1e-12:
            got[want.pop(0)] = n
        logp += step(n)
        n += 1
    return [got.get(s, n) for s in shares]


def pair_moments(fig, hours, fit):
    s, a, b, k = seen_share(fit, hours), fig["a"], fig["b"], spread_shape(fit, hours, fig.get("kind"))
    mean = s * a / b
    return mean, mean + s * s * (a / (b * b) + (a * (a + 1) / (b * b * k) if k else 0.0))


def range_levels(fit, hours, day, kind=None):
    b = ad.gap_bin(hours, (fit or {}).get("edges") or [])
    got = ((fit or {}).get("levels") or {}).get(f"{b}.{rate_class(day)}.{kind}")
    return (got, True) if got else ([LOW_Q, HIGH_Q], False)


def pair_range(fig, hours, fit, shares=None):
    mean, var = pair_moments(fig, hours, fit)
    return [n * fig["units"] for n in nb_quantiles(mean, var, shares or range_levels(fit, hours, fig["day"], fig.get("kind"))[0])]


def pit_of(fig, hours, fit, sold):
    mean, var = pair_moments(fig, hours, fit)
    below, upto = nb_cdf(mean, var, round(sold / fig["units"]))
    return (below + upto) / 2


def nb_cdf(mean, var, x):
    if mean <= 0:
        return (0.0, 1.0) if x <= 0 else (1.0, 1.0)
    if var <= mean * (1 + 1e-9):
        logp, step = -mean, lambda n: math.log(mean) - math.log(n + 1)
    else:
        r = mean * mean / (var - mean)
        keep = r / (r + mean)
        logp, step = r * math.log(keep), lambda n: math.log(n + r) - math.log(n + 1) + math.log(1 - keep)
    total = 0.0
    for n in range(max(0, x)):
        total += math.exp(logp)
        logp += step(n)
    return min(1.0, total), min(1.0, total + math.exp(logp))


def sales_figure(ev, prior, house_pairs, fit=None, kind=None, place=ad.S_SOLD):
    from counting import steps_of
    if not ev["pairs"] and not house_pairs:
        return None
    a, b = posterior(ev, prior)
    got = {"day": round(ev["units"] * a / b, 3), "a": round(a, 5), "b": round(b, 5), "units": round(ev["units"], 3), "kind": kind}
    low, high = pair_range(got, DAY_HOURS, fit)
    has = bool(ev["pairs"])
    measured = has and range_levels(fit, DAY_HOURS, got["day"], kind)[1]
    steps = steps_of(max(got["day"], 1e-9), low, high, ev["pairs"], measured) if has else 0
    if place == ad.S_UNDER:
        where = {"below": below_of(ev.get("at") or {})}
    else:
        above, priced = above_of(ev.get("at") or {})
        where = {"above": above, "priced": priced}
    return {**got, "low": round(low, 3), "high": round(high, 3), "steps": steps, "measured": bool(measured),
            "from": "own" if has else "prior", "pairs": ev["pairs"], "short": ev["short"], "reset": round(ev["reset"], 2),
            **where}


def priors_of(evs, classes):
    by_sub = collections.defaultdict(list)
    for k, ev in evs.items():
        if ev["seen"]:
            by_sub[subclass_of(classes, k)].append(ev["units"] * ev["events"] / ev["seen"])
    return {sub: round(max(PRIOR_LEAST, ad.median(v)), 4) for sub, v in by_sub.items()}



def subclass_of(classes, key):
    got = classes[0].get(key.split(":")[0])
    return f"{got[0]}.{got[1]}" if got else ""


def house_rules(heads, longest):
    lines = [s for h in heads for s in h["scans"]]
    over = [s["over"] for s in lines if "over" in s]
    bids = [s["bids"] for s in lines if "bids" in s]
    return {"style": "commodity" if any(over) else "stack" if len(over) >= STACK_SCANS else None,
            "bids": True if any(bids) else False if len(bids) >= STACK_SCANS else None,
            "longest": longest}


GUIDE_CUT = {"faction": 0.05, "neutral": 0.15}
GUIDE_DEPOSIT = {"faction": 0.60, "neutral": 3.00}
GUIDE_LEAST = 1
GUIDE_HOURS = 24
GAME_LONGEST = 3


def fees_of(side, read=None):
    kind = "neutral" if side == "Neutral" else "faction"
    read = read or {}
    cut = (read.get("cut") or {}).get("share")
    rate = ((read.get("deposit") or {}).get(GAME_LONGEST) or {}).get("rate")
    least = read.get("least") if rate is not None else None
    length = (read.get("durations") or {}).get(GAME_LONGEST) if rate is not None else None
    came = {"cut": "guide" if cut is None else "game", "deposit": "guide" if rate is None else "game"}
    return {"cut": GUIDE_CUT[kind] if cut is None else cut,
            "deposit": {"share": GUIDE_DEPOSIT[kind] if rate is None else rate,
                        "least": GUIDE_LEAST if least is None else least},
            "hours": length / ad.HOUR if length else GUIDE_HOURS,
            "kind": kind, "from": came, "read": came["cut"] == came["deposit"] == "game"}


def undercuts_of(parts, edges, now, classes):
    fit = fit_sales({k: [(t, p) for t, p, _ in v] for k, v in parts.items()}, edges, None, now, ad.S_UNDER, classes)
    evs = {k: evidence(v, now, fit, ad.S_UNDER) for k, v in parts.items()}
    priors = priors_of(evs, classes)
    pairs = max((ev["pairs"] for ev in evs.values()), default=0)

    def figure(key):
        ev = evs.get(key) or evidence([], now, fit, ad.S_UNDER)
        return sales_figure(ev, priors.get(subclass_of(classes, key), PRIOR_LEAST), pairs, fit, ad.kind_of(key, classes),
                            ad.S_UNDER)
    return fit, figure



KAPPA_GRID = [0.0] + [math.log(2) / 10 ** (e / 10) for e in range(0, 31)]


def state_samples(levels, parts, edges):
    import bisect
    from counting import state_answer
    times = [t for t, _, _ in levels]
    states = []
    for j, (t, price, _) in enumerate(levels):
        first = bisect.bisect_left(times, t - ad.LEVEL_DAYS * ad.DAY)
        got = state_answer([{"t": s, "level": lv, "reset": rs} for s, lv, rs in levels[first:j + 1]], price, t)
        if got["state"]:
            states.append((t, got["state"], math.log1p(got["change"])))
    moves = []
    at = {t: j for j, t in enumerate(times)}
    for t, state, dev in states:
        j = at[t]
        if j + 1 < len(levels):
            later, price = levels[j + 1][0], levels[j + 1][1]
            moves.append((later, state, dev, (later - t) / ad.HOUR, math.log(price / levels[j][1])))
    unders = []
    if states:
        rates = collections.defaultdict(lambda: [0.0, 0.0])
        for _, p, _ in parts:
            if p[ad.S_HOURS] > 0:
                r = rates[ad.gap_bin(p[ad.S_HOURS], edges)]
                r[0] += p[ad.S_UNDER]
                r[1] += p[ad.S_HOURS]
        starts = [s for s, _, _ in states]
        for t, p, _ in parts:
            if p[ad.S_HOURS] <= 0:
                continue
            i = bisect.bisect_right(starts, t - p[ad.S_HOURS] * ad.HOUR) - 1
            if i >= 0:
                units, hours = rates[ad.gap_bin(p[ad.S_HOURS], edges)]
                unders.append((t, states[i][1], p[ad.S_UNDER], units / hours * p[ad.S_HOURS]))
    return moves, unders


def state_moves(moves, unders, least):
    import numpy as np
    out = {}
    names = [name for _, name in ad.STATES]
    total = sum(u for _, _, u, _ in unders), sum(e for _, _, _, e in unders)
    usual = total[0] / total[1] if total[1] else None
    grid = np.array(KAPPA_GRID)[:, None]
    for name in names:
        ms = np.array([(dev, hours, move) for _, st, dev, hours, move in moves if st == name]).reshape(-1, 3)
        kappa = 0.0
        if len(ms) >= least:
            gone = ms[:, 0] * (1 - np.exp(-grid * ms[:, 1]))
            kappa = float(KAPPA_GRID[int(np.argmin(np.abs(ms[:, 2] + gone).sum(axis=1)))])
        us = [(u, e) for _, st, u, e in unders if st == name]
        seen = sum(e for _, e in us)
        under = 1.0
        if len(us) >= least and seen > 0 and usual:
            under = sum(u for u, _ in us) / seen / usual
        out[name] = {"kappa": round(kappa, 6), "under": round(under, 4), "n": len(ms), "pairs": len(us)}
    return out


def clock_of(files):
    if not files:
        return None
    head = ad.read_head(files[max(files)])
    return head["scans"][-1]["t"] if head and head.get("scans") else None


def inputs_of(house, files):
    import backtest
    clock = clock_of(files)
    if clock is None:
        return None
    first = day_of(clock - VOLUME_DAYS * ad.DAY)
    days = sorted(d for d in files if d >= first)
    days = sorted(d for d in files if d < first)[-1:] + days
    folder, pool = house.folder, house.pool
    parts = [MARK, ad.MODEL_MARK, [(d, store.digest(files[d])) for d in days],
             store.digest(mainstores.standing(os.path.join(folder, ad.MODEL))),
             store.digest(mainstores.standing(os.path.join(folder, backtest.BACKTEST))),
             sorted(ad.item_breaks(ad.known_builds()).items()), sorted(pool[0]), pool[1]]
    return hashlib.blake2b(repr(parts).encode("utf-8"), digest_size=16).hexdigest()


def market(house, model, files, breaks):
    from counting import state_answer, steps_of
    import gamedata
    now = clock_of(files) or time.time()
    since = now - VOLUME_DAYS * ad.DAY
    first = day_of(since)
    use = sorted(d for d in files if d >= first)
    earlier = sorted(d for d in files if d < first)
    states = {}
    if earlier:
        _, lines = ad.read_day(files[earlier[-1]], house.pool)
        states = {k: tuple(v["k"]) for k, v in lines.items() if v.get("k")}
    acc = collections.defaultdict(lambda: {"levels": [], "units": 0, "priced": 0, "last": None, "parts": [], "noise": None})
    heads, scans, longest, bands = [], [], None, ad.BAND_LEAST
    for day in use:
        head, lines = ad.read_day(files[day], house.pool)
        if not head:
            continue
        times = [s["t"] for s in head["scans"]]
        heads.append(head)
        scans.extend((s["t"], s["id"]) for s in head["scans"] if s["t"] >= since)
        longest = head.get("longest") or longest
        bands = next((s["bands"] for s in reversed(head["scans"]) if s.get("bands")), bands)
        for k, v in lines.items():
            rows = v.get("o") or []
            if not rows:
                continue
            q, floor = ad.noise_of(model, k)
            pts = ad.points([(times[r[ad.R_SCAN]], r) for r in rows], floor)
            got, last = ad.run_filter(pts, q, breaks.get(k.split(":")[0], ()), states.get(k))
            if last:
                states[k] = last
            a = acc[k]
            for r, s, (t, _, _) in zip(rows, got, pts):
                if t < since:
                    continue
                if s["level"] is not None:
                    a["levels"].append((t, math.exp(s["level"]), ad.is_reset(r, s["z"])))
                a["priced"] += r[ad.R_PRICE] is not None
                a["units"] += r[ad.R_UNITS]
                a["last"] = (t, r)
                if r[ad.R_PRICE]:
                    a["noise"] = max(r[ad.R_NOISE] or 0.0, floor)
                p = ad.sales_of(r)
                if p:
                    a["parts"].append((t, p, ad.is_reset(r, s["z"])))
        del lines
    scans.sort()
    newest = scans[-1][0] if scans else None
    classes = gamedata.item_classes()
    import backtest
    scored = ((backtest.load(house.folder) or {}).get("scored") or {}).get("sales")
    fit = fit_sales({k: [(t, p) for t, p, _ in a["parts"]] for k, a in acc.items()}, ad.gap_edges(bands, longest), scored,
                    now, classes=classes)
    evs = {k: evidence(a["parts"], now, fit) for k, a in acc.items()}
    priors = priors_of(evs, classes)
    under, under_of = undercuts_of({k: a["parts"] for k, a in acc.items()}, ad.gap_edges(bands, longest), now, classes)
    moves, unders = [], []
    for a in acc.values():
        m, u = state_samples(a["levels"], a["parts"], ad.gap_edges(bands, longest))
        moves += m
        unders += u
    moved = state_moves(moves, unders, backtest.N_LEAST)
    del moves, unders
    pairs = max((ev["pairs"] for ev in evs.values()), default=0)
    house_short = max((ev["short"] for ev in evs.values()), default=0)
    items = []
    for k, a in acc.items():
        ident = k.split(":")[0]
        sub = subclass_of(classes, k)
        row = {"item": k, "sub": sub, "scans": a["priced"], "listed": 0, "auctions": 0, "cheapest": None, "wall": 0,
               "average": round(a["units"] / len(scans), 2) if scans else 0, "price": None, "state": None,
               "seen": a["last"][0] if a["last"] else None, "bait": False, "reset": False, "vendor": False}
        if a["last"] and a["last"][0] == newest:
            r = a["last"][1]
            row.update(listed=r[ad.R_UNITS], auctions=r[ad.R_AUCTIONS], cheapest=r[ad.R_LOW], wall=r[ad.R_WALL] if len(r) > ad.R_WALL else 0,
                       bait=bool(r[ad.R_BAIT]), reset=bool(a["parts"] and a["parts"][-1][0] == newest and a["parts"][-1][2]))
        if a["priced"] and k in states:
            q, floor = ad.noise_of(model, k)
            mu, p = ad.at_time(states[k], newest or now, q, breaks.get(ident, ()))
            price, lo, hi, measured = ad.price_range(model, mu, p, a["noise"] or floor,
                                                     max(0.0, (newest or now) - states[k][0]) / ad.HOUR, ad.kind_of(k, classes))
            row["price"] = {"price": round(price, 2), "low": round(lo, 2), "high": round(hi, 2),
                            "steps": steps_of(price, lo, hi, a["priced"], measured), "measured": measured}
            row["state"] = state_answer([{"t": t, "level": lv, "reset": rs} for t, lv, rs in a["levels"]], price,
                                        newest or now, lo, hi)
        row["sales"] = sales_figure(evs[k], priors.get(sub, PRIOR_LEAST), pairs, fit, ad.kind_of(k, classes))
        row["under"] = under_of(k)
        vendor = gamedata.item_sell_price(int(ident)) if ident.isdigit() else None
        row["vendor"] = bool(vendor and row["cheapest"] is not None and row["cheapest"] < vendor)
        row["vendorPays"] = vendor
        items.append(row)
    out = {"made": now, "rests": inputs_of(house, files), "mark": MARK, "newest": newest, "newestId": scans[-1][1] if scans else None, "scans": len(scans),
           "pairs": pairs, "short": house_short, "days": VOLUME_DAYS,
           "rules": house_rules(heads, longest), "priors": priors, "sales": fit, "under": under, "moved": moved,
           "items": items}
    if house.keep:
        os.makedirs(house.folder, exist_ok=True)
        store.save_json(os.path.join(house.folder, MARKET), out, indent=None)
        _loaded.pop(house.folder, None)
    return out


_loaded = {}


def load(folder):
    path = mainstores.standing(os.path.join(folder, MARKET))
    try:
        at = os.path.getmtime(path)
    except OSError:
        return None
    got = _loaded.get(folder)
    if not got or got[0] != at:
        got = _loaded[folder] = (at, store.load_json(path, None))
    return got[1]


def due(house, files=None):
    whole = ad.read_metas(house)
    if not whole:
        return False
    got = load(house.folder)
    if not got or got.get("newestId") != whole[-1]["id"] or got.get("mark") != MARK or \
            ad.load_model(house.folder).get("mark") != ad.MODEL_MARK:
        return True
    return got.get("rests") != inputs_of(house, ad.day_files(house.folder) if files is None else files)



def hour_of_week(t):
    lt = time.localtime(t)
    return lt.tm_wday * 24 + lt.tm_hour


def spread(a, b):
    out, t = collections.Counter(), a
    while t < b:
        nxt = min(b, (math.floor(t / ad.HOUR) + 1) * ad.HOUR)
        out[hour_of_week(t)] += nxt - t
        t = nxt
    return out


def heat(scans, pairs):
    sold = [[0.0, 0.0, 0] for _ in range(168)]
    for t, p in pairs:
        if p[ad.S_HOURS] * ad.HOUR > GAP_FULL or p[ad.S_HOURS] <= 0:
            continue
        cover = spread(t - p[ad.S_HOURS] * ad.HOUR, t)
        total = sum(cover.values())
        for h, secs in cover.items():
            share = secs / total
            sold[h][0] += p[ad.S_SOLD] * share
            sold[h][1] += secs / ad.HOUR
            sold[h][2] += 1
    priced = [(s["t"], s["price"]) for s in scans if s["price"]]
    price = [[0.0, 0] for _ in range(168)]
    for t, v in priced:
        week = [x for u, x in priced if abs(u - t) <= WEEK_SPAN]
        mid = ad.median(week)
        if mid:
            c = price[hour_of_week(t)]
            c[0] += v / mid
            c[1] += 1
    cells = lambda rows: [[rows[d * 24 + h] for h in range(24)] for d in range(7)]
    return {"sold": cells([[round(c[0] / c[1], 3) if c[2] >= HEAT_LEAST and c[1] else None, c[2]] for c in sold]),
            "price": cells([[round(c[0] / c[1], 4) if c[1] >= HEAT_LEAST else None, c[1]] for c in price])}


def by_day(parts, prior, fit, kind=None):
    days = collections.defaultdict(list)
    for part in parts:
        days[day_of(part[0])].append(part)
    out = []
    for day in sorted(days):
        noon = time.mktime(time.strptime(day, "%Y-%m-%d")) + 12 * ad.HOUR
        got = sales_figure(evidence(days[day], noon, fit), prior, 1, fit, kind)
        out.append({"day": day, "t": noon, "sold": got["day"], "low": got["low"], "high": got["high"],
                    "pairs": len(days[day])})
    return out


def item_sales(rows, states, prior, house_pairs, now, scans, fit=None, kind=None):
    parts = []
    for r, s in zip(rows, states):
        p = ad.sales_of(r["reading"])
        if p:
            parts.append((r["t"], p, ad.is_reset(r["reading"], s["z"])))
    ev = evidence(parts, now, fit)
    pairs = [(t, p) for t, p, _ in parts]
    table = [{"t": t, "hours": p[ad.S_HOURS], "gone": p[ad.S_GONE], "units": p[ad.S_UNITS], "sold": p[ad.S_SOLD],
              "expired": p[ad.S_EXPIRED], "cancelled": p[ad.S_CANCELLED], "reset": reset,
              "share": round(p[ad.S_SOLD] / p[ad.S_UNITS], 3) if p[ad.S_UNITS] else None} for t, p, reset in parts]
    return {"figure": sales_figure(ev, prior, house_pairs, fit, kind), "pairs": table, "days": by_day(parts, prior, fit, kind),
            "heat": heat(scans, pairs), "newest": parts[-1][0] if parts else None, "prior": prior}
