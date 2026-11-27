# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import collections
import gzip
import hashlib
import json
import math
import os
import time

import auctiondays as ad
import auctionmarket as am
import jsontext
import store
import workers
from dayrecord import day_of

HELD = 0.90
N_LEAST = 50
BIN_LEAST = 10
BINS_MOST = 10
FAIL_SHARE = 0.10
FIT_DAYS = ad.FIT_DAYS
BACKTEST = "backtest.json"
WALKED = "backtest_walk.json.gz"
CHAIN_MARK = 8
SCORE_MARK = 8
PRICE_FIELDS = ("t", "item", "hours", "gap", "kind", "word", "shown", "next", "error", "sd")
SALES_FIELDS = ("t", "item", "hours", "word", "from", "rate", "shown", "next", "day", "seen", "pred", "gone", "sold", "pairs",
                "bin", "kind", "pit")
STATE_FIELDS = ("state", "sure", "next", "side")
PICK_FIELDS = ("t", "item", "kind", "units", "auctions", "upTo", "hours", "cycles", "sells", "one", "edge", "price", "level",
               "gold")
SELL_FIELDS = ("t", "item", "way", "units", "held", "hours", "cycles", "sells", "one", "edge", "price", "level", "gold",
               "evidence")
LEVELS = (1.05, 1.5)
RECORDS = (("price", PRICE_FIELDS), ("sales", SALES_FIELDS), ("states", STATE_FIELDS), ("picks", PICK_FIELDS),
           ("sell", SELL_FIELDS))
SPAN_EDGES = (12, 48)
RATE_EDGES = am.RATE_EDGES



class History:

    def __init__(self, files, pool=None):
        scans, items, self.heads = {}, collections.defaultdict(list), []
        self.pool, self.views = pool, None
        for day in sorted(files):
            head, lines = ad.read_day(files[day])
            if not head:
                continue
            times = [s["t"] for s in head["scans"]]
            for s in head["scans"]:
                scans[s["t"]] = s["id"]
                self.heads.append((s["t"], s.get("bands"), head.get("longest")))
            for k, v in lines.items():
                for r in v.get("o") or ():
                    items[k].append((times[r[ad.R_SCAN]], r))
            del lines
        self.scans = sorted(scans.items())
        self.items = {k: sorted(v, key=lambda x: x[0]) for k, v in items.items()}
        self.times = {k: [t for t, _ in v] for k, v in self.items.items()}

    def edges(self, t):
        known = [h for h in self.heads if h[0] <= t]
        bands = next((b for _, b, _ in reversed(known) if b), ad.BAND_LEAST)
        return ad.gap_edges(bands, self.longest(t))

    def longest(self, t):
        return max((lg or 0 for s, _, lg in self.heads if day_of(s) < day_of(t)), default=0) or None

    def view(self, at):
        known = self.known(at)
        if self.views and self.views[0] == known:
            return self.views[1]
        items, times = dict(self.items), dict(self.times)
        for i in known:
            for key, rows in self.pooled(i, True).items():
                if rows:
                    items[key], times[key] = rows, [t for t, _ in rows]
                else:
                    items.pop(key, None)
                    times.pop(key, None)
        self.views = (known, (items, times))
        return self.views[1]

    def known(self, at):
        suffixed, since = self.pool or ({}, None)
        return tuple(sorted(i for i, f in suffixed.items() if f is not None and f <= at)) if since is not None else ()

    def pooled(self, item, known):
        k, key = str(item), f"{item}:{ad.POOLED}"
        mine, pooled = self.items.get(k, []), self.items.get(key, [])
        if not known:
            return {k: mine, key: pooled}
        since = self.pool[1]
        return {k: [x for x in mine if x[0] >= since],
                key: sorted(pooled + [x for x in mine if x[0] < since], key=lambda x: x[0])}

    def readings(self, key, at):
        item = key.split(":")[0]
        if not item.isdigit() or key not in (item, f"{item}:{ad.POOLED}"):
            return self.items.get(key, [])
        suffixed, since = self.pool or ({}, None)
        f = suffixed.get(int(item))
        known = since is not None and f is not None and f <= at
        return self.pooled(int(item), known)[key]

    def upto(self, t):
        items, times = self.view(t)
        out = {}
        for k, v in items.items():
            n = bisect.bisect_right(times[k], t)
            if n:
                out[k] = v[:n]
        return out

    def between(self, a, b):
        items, times = self.view(a)
        out = {}
        for k, v in items.items():
            ts = times[k]
            i, j = bisect.bisect_right(ts, a), bisect.bisect_right(ts, b)
            if j > i:
                out[k] = v[i:j]
        return out

    def density(self):
        ts = [t for t, _ in self.scans]
        gaps = [(b - a) / ad.HOUR for a, b in zip(ts, ts[1:])]
        return {"scans": len(ts), "days": len({day_of(t) for t in ts}), "first": ts[0] if ts else None,
                "last": ts[-1] if ts else None, "gap": round(ad.median(gaps), 2) if gaps else None,
                "longest": round(max(gaps), 2) if gaps else None,
                "short": sum(1 for g in gaps if g * ad.HOUR <= am.GAP_FULL)}


def walk(history, predict, horizon, start=1):
    out = []
    for t, _ in history.scans[start:]:
        known = history.upto(t)
        after = history.between(t, t + horizon)
        for pred in predict(known, t) or ():
            got = pred["settle"](after)
            if got is None:
                continue
            out.append({"t": t, "item": pred.get("item"), "p": float(pred["p"]), "group": pred.get("group"), **got})
    return out



def wilson(hits, n, share):
    if not n:
        return 0.0, 1.0
    z = normal_quantile(1 - share / 2)
    p = hits / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, mid - half), min(1.0, mid + half)


def normal_quantile(p):
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -normal_quantile(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def bin_count(n):
    return max(1, min(BINS_MOST, n // (BIN_LEAST * 3)))


def score(records):
    n = len(records)
    out = {"n": n, "needs": N_LEAST, "came": None, "predicted": None, "brier": None, "reliability": None,
           "resolution": None, "uncertainty": None, "bins": [], "holds": None}
    if not n:
        return out
    k = bin_count(n)
    groups = [[] for _ in range(k)]
    for r in records:
        groups[min(k - 1, int(r["p"] * k))].append(r)
    came = sum(r["o"] for r in records) / n
    counted = sum(1 for g in groups if len(g) >= BIN_LEAST)
    share = FAIL_SHARE / max(1, counted)
    rel = res = 0.0
    for i, g in enumerate(groups):
        if not g:
            continue
        m = len(g)
        p = sum(r["p"] for r in g) / m
        hits = sum(r["o"] for r in g)
        o = hits / m
        lo, hi = wilson(hits, m, share)
        rel += m * (p - o) ** 2
        res += m * (o - came) ** 2
        out["bins"].append({"low": i / k, "high": (i + 1) / k, "n": m, "p": round(p, 4), "o": round(o, 4),
                            "lo": round(lo, 4), "hi": round(hi, 4), "counts": m >= BIN_LEAST, "fits": lo <= p <= hi})
    out.update(came=round(came, 4), predicted=round(sum(r["p"] for r in records) / n, 4),
               brier=round(sum((r["p"] - r["o"]) ** 2 for r in records) / n, 5), reliability=round(rel / n, 5),
               resolution=round(res / n, 5), uncertainty=round(came * (1 - came), 5))
    if n >= N_LEAST and counted:
        out["holds"] = all(b["fits"] for b in out["bins"] if b["counts"])
    return out


def gate(files, predict, horizon, groups=False):
    history = History(files)
    records = walk(history, predict, horizon)
    got = score(records)
    out = {"holds": got["holds"], "score": got, "density": history.density()}
    if groups:
        by = collections.defaultdict(list)
        for r in records:
            by[r.get("group")].append(r)
        out["groups"] = {g: score(v) for g, v in by.items()}
    return out


QUALITY = ("low", "medium", "high")
QUALITY_STEPS = {"low": 1, "medium": 3, "high": 5}
CLOSE = 0.10
SCANS_LEAST = 3
FRESH = ad.DAY
STALE = 7 * ad.DAY


def test_of(s):
    if s["n"] < N_LEAST or s["holds"] is None:
        return "few"
    if s["holds"]:
        return "holds"
    return "near" if abs(s["came"] - s["predicted"]) <= CLOSE else "off"


def quality(tested, group, scans, newest, now):
    s = ((tested or {}).get("groups") or {}).get(group) or (tested or {}).get("score") or score([])
    verdict = test_of(s)
    test = {"few": "low", "holds": "high", "near": "medium", "off": "low"}[verdict]
    why = [] if verdict == "holds" else ["checks.few" if verdict == "few" else f"backtest.{verdict}"]
    age = max(0.0, now - newest) if newest else None
    if scans < SCANS_LEAST:
        data = "low"
        why.append("scans.few")
    elif age is None or age > STALE:
        data = "low"
        why.append("scans.old")
    elif age > FRESH:
        data = "medium"
        why.append("scans.aging")
    else:
        data = "high"
    word = min(test, data, key=QUALITY.index)
    return {"word": word, "steps": QUALITY_STEPS[word], "scans": scans, "age": age, "checks": s["n"], "came": s["came"],
            "predicted": s["predicted"], "brier": s["brier"], "why": why}



def word_of(steps):
    return "high" if steps >= 4 else "medium" if steps >= 2 else "low"


def span_of(hours):
    return "near" if hours <= SPAN_EDGES[0] else "day" if hours <= SPAN_EDGES[1] else "far"


def rate_of(day):
    return "slow" if day < RATE_EDGES[0] else "steady" if day < RATE_EDGES[1] else "fast"


def fit_at(known, t, breaks, scored=None, gaps=()):
    since = t - FIT_DAYS * ad.DAY
    series = {}
    for k, rows in known.items():
        pts = [(s, math.log(r[ad.R_PRICE]), r[ad.R_NOISE]) for s, r in rows if r[ad.R_PRICE] and s >= since]
        if len(pts) >= 2:
            b = breaks.get(k.split(":")[0], ())
            series[k] = [(s, y, n, ad.breaks_between(b, pts[i - 1][0], s) if i else 0) for i, (s, y, n) in enumerate(pts)]
    return ad.fit_series(series, scored, gaps, t)


def chain(history, breaks, classes, records=False):
    walked = walk_chain(history, breaks, classes)
    out = answer_of(history, walked)
    if records:
        out["records"] = {k: walked[k] for k in ("price", "sales", "states", "picks")}
    return out


def answer_of(history, walked):
    last = history.scans[-1][0] if history.scans else 0
    keep = lambda rows: [x for x in rows if x[0] >= last - FIT_DAYS * ad.DAY]
    return {"density": history.density(), "price": price_scores(walked["price"]), "sales": sales_scores(walked["sales"]),
            "states": state_scores(walked["states"]),
            "picks": picks_scores(settle_picks(history, walked["picks"]), history.scans[-1][0] if history.scans else None,
                                  walked.get("skipped") or 0),
            "sell": sell_scores(settle_picks(history, [p for p in walked["sell"] if p["way"] == "house"]), last,
                                walked.get("skipped") or 0, [p for p in walked["sell"] if p["way"] == "vendor"]),
            "scored": {"price": [[round(t), round(sd, 5), round(h, 3), kind, round(z, 4)]
                                 for t, sd, h, kind, z in keep(walked["scored"])],
                       "sales": [[round(t), b, rate, kind, round(pit, 5)] for t, b, rate, kind, pit in keep(walked["pits"])]}}


def walk_chain(history, breaks, classes, kept=None, hold=None, book=None, goods=()):
    from counting import state_answer, steps_of
    import auctionpicks as ap
    book = book if book is not None else book_of()
    hold = hold or ap.hold_of(book["fees"])
    price, sales, states, picks, sell = [], [], [], [], []
    skipped = 0
    scored = []
    pits = []
    scans = [t for t, _ in history.scans]
    first = 0
    if kept:
        price, sales, states, picks = (rows_of(kept["records"][name], fields) for name, fields in RECORDS[:4])
        sell = rows_of(kept["records"]["sell"], SELL_FIELDS) if kept["records"].get("sell") else []
        scored, pits = list(kept["scored"]), list(kept["pits"])
        skipped = kept.get("skipped") or 0
        first = len(kept["scans"]) - 1
    for j in range(first, len(scans) - 1):
        t, nxt = scans[j], scans[j + 1]
        known = history.upto(t)
        edges = history.edges(t)
        model = fit_at(known, t, breaks, [x for x in scored if x[0] >= t - FIT_DAYS * ad.DAY], edges)
        coming = history.between(t, nxt)
        parts = {k: [(s, ad.sales_of(r), False) for s, r in rows if ad.sales_of(r)] for k, rows in known.items()}
        fit = am.fit_sales({k: [(s, p) for s, p, _ in v] for k, v in parts.items()}, edges,
                           [x for x in pits if x[0] >= t - FIT_DAYS * ad.DAY], t, classes=classes)
        evs = {k: am.evidence(v, t, fit) for k, v in parts.items()}
        priors = am.priors_of(evs, classes)
        house_pairs = max((ev["pairs"] for ev in evs.values()), default=0)
        raw = replay_flips(book, history, j, model, hold, parts, edges, fit, evs, priors, house_pairs, classes, breaks)
        got, missed = replay_picks(known, t, history.scans[j][1], hold, parts, edges, fit, evs, priors, house_pairs,
                                   classes, book, model, breaks, {(p["item"], p["t"]) for p in raw})
        picks += raw + got
        skipped += missed
        sold, missed = replay_sell_picks(known, t, history.scans[j][1], hold, parts, edges, fit, evs, priors, house_pairs,
                                         classes, book, model, breaks, goods)
        sell += sold
        skipped += missed
        for k, later in coming.items():
            _, r = later[0]
            rows = known.get(k, [])
            q, floor = ad.noise_of(model, k)
            b = breaks.get(k.split(":")[0], ())
            used = sum(1 for _, x in rows if x[ad.R_PRICE])
            if used and r[ad.R_PRICE]:
                pts = ad.points(rows + [(nxt, r)], floor)
                got, _ = ad.run_filter(pts, q, b)
                before = got[-2] if len(got) > 1 else None
                if before and before["level"] is not None:
                    mu, p = before["level"], got[-1]["before"]
                    noise = ad.noise_now([x for _, x in rows], floor)
                    gap = (nxt - rows[-1][0]) / ad.HOUR
                    kind = ad.kind_of(k, classes)
                    shown, lo, hi, measured = ad.price_range(model, mu, p, noise, gap, kind)
                    y = math.log(r[ad.R_PRICE])
                    steps = steps_of(shown, lo, hi, used, measured)
                    held = int(lo <= r[ad.R_PRICE] <= hi)
                    sd = math.sqrt(p + noise)
                    price.append({"t": t, "item": k, "hours": (nxt - t) / ad.HOUR, "gap": gap, "kind": kind,
                                  "word": word_of(steps), "shown": held, "next": held, "error": y - mu, "sd": sd})
                    levels = [{"t": s, "level": math.exp(g["level"]), "reset": ad.is_reset(x, g["z"])}
                              for (s, x), g in zip(rows, got) if g["level"] is not None]
                    _, now_lo, now_hi, _ = ad.price_range(model, mu, before["P"], noise, 0.0, kind)
                    now_state = state_answer(levels, math.exp(before["level"]), t, now_lo, now_hi)
                    then = state_answer(levels + [{"t": nxt, "level": math.exp(got[-1]["level"])}],
                                        math.exp(got[-1]["level"]), nxt)
                    if now_state["state"] and then["state"]:
                        states.append({"state": now_state["state"], "sure": now_state["sure"], "next": then["state"],
                                       "side": (then["change"] > 0) == (now_state["change"] > 0)})
            part = ad.sales_of(r)
            if part and part[ad.S_HOURS] > 0:
                ev = evs.get(k) or am.evidence([], t, fit)
                prior = priors.get(am.subclass_of(classes, k), am.PRIOR_LEAST)
                fig = am.sales_figure(ev, prior, house_pairs, fit, ad.kind_of(k, classes))
                if fig is None:
                    continue
                hours, sold = part[ad.S_HOURS], part[ad.S_SOLD]
                seen = 24 * sold / hours
                low, high = am.pair_range(fig, hours, fit)
                pred = fig["units"] * am.seen_share(fit, hours) * fig["a"] / fig["b"]
                held = int(low <= round(sold / fig["units"]) * fig["units"] <= high)
                sales.append({"t": t, "item": k, "hours": hours, "word": word_of(fig["steps"]), "from": fig["from"],
                              "rate": rate_of(fig["day"]), "shown": held, "next": held, "day": fig["day"], "seen": seen,
                              "pred": pred, "gone": part[ad.S_GONE], "sold": sold, "pairs": ev["pairs"],
                              "bin": ad.gap_bin(hours, edges), "kind": fig["kind"], "pit": am.pit_of(fig, hours, fit, sold)})
        scored += [(t, r["sd"], r["gap"], r["kind"], abs(r["error"]) / r["sd"]) for r in price if r["t"] == t]
        pits += [(t, r["bin"], am.rate_class(r["day"]), r["kind"], r["pit"]) for r in sales if r["t"] == t]
    return {"price": price, "sales": sales, "states": states, "picks": picks, "sell": sell, "skipped": skipped,
            "scored": scored, "pits": pits}



def hold_of_house(side=None, fees=None):
    import auctionpicks as ap
    return ap.hold_of(fees or am.fees_of(side))


def kept_answers(house):
    import auctionpicks as ap
    folder = getattr(house, "folder", None)
    kept = ap.read_kept(folder, ap.ANSWERS) if folder else {}
    return [v[1] for v in kept.values() if isinstance(v, list) and len(v) == 2 and isinstance(v[1], dict)]


def answer_fees(house, answers=None):
    answers = kept_answers(house) if answers is None else answers
    shown = [a for a in answers if a.get("fees")]
    if shown:
        return max(shown, key=lambda a: a.get("made") or 0)["fees"]
    return am.fees_of(getattr(house, "faction", None), money_rules(house))


def held_of(house, answers=None):
    answers = kept_answers(house) if answers is None else answers
    if not answers:
        return []
    newest = max(answers, key=lambda a: a.get("made") or 0)
    return [(p.get("item"), p.get("units")) for p in newest.get("sell") or () if isinstance(p, dict)]


def money_rules(house):
    key = getattr(house, "key", None)
    if not key or "|" not in key:
        return {}
    try:
        import gamedata
        import ledger
        import mainstores
        import trades
        root = os.path.dirname(os.path.abspath(__file__))
        board = store.load_json(mainstores.standing(os.path.join(root, "data", "characters.json")), {})
        chars = {k: {"name": c.get("name"), "realm": c.get("realm"), "faction": c.get("faction")}
                 for k, c in (board.get("chars") or {}).items()}
        return trades.Trades(ledger.Ledger(), lambda: chars, vendor=gamedata.item_sell_price).view(key).get("rules") or {}
    except Exception:
        return {}


def replay_picks(known, t, sid, hold, parts, edges, fit, evs, priors, house_pairs, classes, book, model, breaks,
                 replayed=()):
    made = made_picks(known, t, sid, parts, edges, fit, evs, priors, house_pairs, classes, book, model, breaks, replayed)
    return pick_records(made, t, hold, am.pace_of(fit)[1])


def replay_sell_picks(known, t, sid, hold, parts, edges, fit, evs, priors, house_pairs, classes, book, model, breaks,
                      held):
    made, missing = made_sell_picks(known, t, sid, hold, parts, edges, fit, evs, priors, house_pairs, classes, book,
                                    model, breaks, held)
    records, skipped = sell_records(made, t, hold, am.pace_of(fit)[1])
    return records, missing + skipped


def pick_records(made, t, hold, edge):
    hours, cycles = hold
    records, skipped = [], 0
    for p in made:
        if p.get("plan") != "house" or not p.get("units") or p.get("listAt") is None:
            skipped += 1
            continue
        records.append({"t": t, "item": p["item"], "kind": p["kind"], "units": p["units"], "auctions": p["auctions"],
                        "upTo": p["upTo"], "hours": hours, "cycles": cycles, "sells": p["sells"], "one": p["one"],
                        "edge": edge, "price": p["listAt"], "level": p["level"], "gold": None})
    return records, skipped


def sell_records(made, t, hold, edge):
    hours, cycles = hold
    records, skipped = [], 0
    for p in made:
        way, units = p.get("way"), p.get("units") or 0
        if way == "vendor":
            if not units:
                skipped += 1
                continue
            vendor = p.get("vendor")
            records.append({"t": t, "item": p["item"], "way": "vendor", "units": units, "held": units, "hours": None,
                            "cycles": None, "sells": None, "one": None, "edge": None, "price": None, "level": None,
                            "gold": units * vendor if vendor is not None else p.get("gold"),
                            "evidence": p.get("evidence")})
            continue
        post = p.get("post") or 0
        if way != "house" or not post or p.get("listAt") is None or p.get("sells") is None or p.get("one") is None:
            skipped += 1
            continue
        records.append({"t": t, "item": p["item"], "way": "house", "units": post, "held": units, "hours": hours,
                        "cycles": cycles, "sells": p["sells"], "one": p["one"], "edge": edge, "price": p["listAt"],
                        "level": p.get("level") or 0, "gold": p.get("gold"), "evidence": p.get("evidence")})
    return records, skipped


def made_picks(known, t, sid, parts, edges, fit, evs, priors, house_pairs, classes, book, model, breaks, replayed=()):
    import auctionpicks as ap
    fit_under, under_of = am.undercuts_of(parts, edges, t, classes)
    todo = []
    for k, rows in known.items():
        s, r = rows[-1]
        if s != t or not r[ad.R_PRICE] or k not in evs or (k, t) in replayed:
            continue
        auctions = front_asks(r)
        if len({round(a[3] / a[2], 4) for a in auctions}) < 2:
            continue
        kind = ad.kind_of(k, classes)
        fig = am.sales_figure(evs[k], priors.get(am.subclass_of(classes, k), am.PRIOR_LEAST), house_pairs, fit, kind)
        if not fig or fig.get("a") is None:
            continue
        todo.append((k, rows, auctions, fig, under_of(k), breaks.get(k.split(":")[0], ()), book["vendor"](k),
                     am.subclass_of(classes, k), kind))
    with workers.mapped(buy_of, todo, (model, fit, fit_under, book["rules"], book["fees"], t, sid),
                        "auction recommendations", ODDS_LEAST, FLIPS_BATCH) as got:
        picked = [f for f in got if f]
    picked.sort(key=lambda p: -p["mean"])
    return picked[:ap.SHOWN]


def front_asks(r):
    return [[0, 0, count, buyout] for count, buyout in (r[ad.R_FRONT] or ()) if count > 0 and buyout > 0]


def level_of(price, floor):
    return bisect.bisect_right(LEVELS, round(price / floor, ad.PLACE_DIGITS)) if floor else 0


def made_sell_picks(known, t, sid, hold, parts, edges, fit, evs, priors, house_pairs, classes, book, model, breaks,
                    held):
    import auctionpicks as ap
    fit_under, under_of = am.undercuts_of(parts, edges, t, classes)
    ctx = {"model": model, "fit": fit, "under": fit_under, "rules": book["rules"], "fees": book["fees"], "now": t,
           "newest": t, "newestId": sid, "cal": {}, "age": 0.0, "gap": 0.0, "tested": None,
           "unchecked": [e["effect"] for e in ap.EFFECTS if e["use"] == "unmeasured"]}
    made, skipped = [], 0
    for item, units in held:
        if not item or not units:
            skipped += 1
            continue
        rows = known.get(item) or []
        r = rows[-1][1] if rows and rows[-1][0] == t else None
        vendor = book["vendor"](item)
        row = {"item": item, "vendorPays": vendor, "scans": len(rows)}
        pick = None
        if r is not None and r[ad.R_PRICE]:
            kind = ad.kind_of(item, classes)
            fig = am.sales_figure(evs.get(item) or am.evidence([], t, fit),
                                  priors.get(am.subclass_of(classes, item), am.PRIOR_LEAST), house_pairs, fit, kind)
            if fig and fig.get("a") is not None:
                row.update(sales=fig, under=under_of(item))
                q, floor = ad.noise_of(model, item)
                b = breaks.get(item.split(":")[0], ())
                _, state = ad.run_filter(ad.points(rows, floor), q, b)
                if state:
                    mu, p = ad.at_time(state, t, q, b)
                    price, low, high, measured = ad.price_range(model, mu, p, ad.noise_now([x for _, x in rows], floor),
                                                                0.0, kind)
                    row["price"] = {"price": price, "low": low, "high": high, "measured": measured}
                asks = front_asks(r)
                pick = ap.sell_item(item, row, asks, units, ctx)
                if pick is not None and pick["way"] == "house":
                    asks = sorted((a[3] / a[2], a[2]) for a in asks if a[3] > 0 and a[2] > 0)
                    pick["level"] = level_of(pick["listAt"], ad.floor_of(asks))
        if pick is None and vendor:
            pick = ap.vendor_only(item, row, units)
        if pick is None:
            skipped += 1
            continue
        model_chances = pick.get("model") or {}
        made.append({"item": item, "way": pick["way"], "units": units, "post": pick.get("post") or 0,
                     "listAt": pick.get("listAt"), "level": pick.get("level"), "sells": model_chances.get("sells"),
                     "one": model_chances.get("one"), "gold": pick.get("gold"), "vendor": pick.get("vendor"),
                     "evidence": pick.get("evidence")})
    return made, skipped


def replay_flips(book, history, j, model, hold, parts, edges, fit, evs, priors, house_pairs, classes, breaks):
    t, sid = history.scans[j]
    ladder = book["ladder"](sid, set(history.known(t))) if book.get("ladder") else None
    if not ladder:
        return []
    known = history.upto(t)
    fit_under, under_of = am.undercuts_of(parts, edges, t, classes)
    todo = []
    for k, rows in known.items():
        if rows[-1][0] != t or not rows[-1][1][ad.R_PRICE] or k not in evs or len({a[3] / a[2] for a in ladder.get(k, ())
                                                                                     if a[2] > 0 and a[3] > 0}) < 2:
            continue
        kind = ad.kind_of(k, classes)
        fig = am.sales_figure(evs[k], priors.get(am.subclass_of(classes, k), am.PRIOR_LEAST), house_pairs, fit, kind)
        if not fig or fig.get("a") is None:
            continue
        todo.append((k, rows, ladder[k], fig, under_of(k), breaks.get(k.split(":")[0], ()), book["vendor"](k),
                     am.subclass_of(classes, k), kind))
    hours, cycles = hold
    edge = am.pace_of(fit)[1]
    with workers.mapped(buy_of, todo, (model, fit, fit_under, book["rules"], book["fees"], t, sid),
                        "auction recommendations", ODDS_LEAST, FLIPS_BATCH) as got:
        return [{"t": t, "item": item[0], "kind": f["kind"], "units": f["units"], "auctions": f["auctions"],
                 "upTo": f["upTo"], "hours": hours, "cycles": cycles, "sells": f["sells"], "one": f["one"], "edge": edge,
                 "price": f["listAt"], "level": f["level"], "gold": f["gold"]}
                for item, f in zip(todo, got) if f and f["plan"] == "house" and f["mean"] > 0]


FLIPS_BATCH = 25


def buy_of(shared, item):
    import auctionpicks as ap
    model, fit, fit_under, rules, fees, t, sid = shared
    k, rows, auctions, fig, under, b, vendor, sub, kind = item
    q, floor = ad.noise_of(model, k)
    _, state = ad.run_filter(ad.points(rows, floor), q, b)
    if not state:
        return None
    mu, p = ad.at_time(state, t, q, b)
    price, low, high, measured = ad.price_range(model, mu, p, ad.noise_now([x for _, x in rows], floor), 0.0, kind)
    row = {"item": k, "sales": fig, "under": under, "price": {"price": price, "low": low, "high": high, "measured": measured},
           "vendorPays": vendor, "bait": bool(rows[-1][1][ad.R_BAIT]), "sub": sub, "scans": len(rows)}
    ctx = {"model": model, "fit": fit, "under": fit_under, "rules": rules, "fees": fees, "now": t, "newest": t,
           "newestId": sid, "survive": 1.0, "cal": {}}
    cand = ap.buy_item(k, row, auctions, ctx)
    if not cand:
        return None
    cand = ap.offered(cand, False)
    if not cand:
        return None
    full = ap.buy_item(k, row, auctions, ctx, cand["best"]["k"], vendor_flips=False)
    if not full:
        return None
    step, top = full["best"], full["draws"]
    house = step["plan"] == "house"
    dep = fees["deposit"]
    return {"item": k, "kind": step["kind"], "plan": step["plan"], "units": step["units"], "auctions": step["k"],
            "upTo": round(step["upTo"], 2), "listAt": round(step["price"], 2),
            "level": level_of(step["price"], full["floor"]), "mean": float(step["mean"]),
            "sells": float(top["p"]) if house else None, "one": float(full["oneRaw"]) if house else None,
            "gold": [step["price"] * (1 - fees["cut"]) - vendor, step["units"] * vendor - step["cost"],
                     max(dep["least"], dep["share"] * vendor * step["units"])] if house else None}


ODDS_LEAST = 200


SETTLE_SLACK = 1e-9


def settle_picks(history, picks):
    import auctionpicks as ap
    scans = [s for s, _ in history.scans]
    out = {w: {"checks": [], "apart": None, "edge": None, "span": None, "t": None} for w in ("sells", "one")}
    flips = []
    for p in picks:
        listing = p["hours"] * ad.HOUR
        first = bisect.bisect_right(scans, p["t"])
        for which, cycles in (("one", 1), ("sells", p["cycles"])):
            k = bisect.bisect_left(scans, p["t"] + listing * cycles)
            if k >= len(scans):
                continue
            seen = scans[max(0, first - 1):k + 1]
            longest = max((b - a for a, b in zip(seen, seen[1:])), default=0.0) / ad.HOUR
            got = out[which]
            got["apart"] = longest if got["apart"] is None else min(got["apart"], longest)
            if got["t"] is None or p["t"] >= got["t"]:
                got.update(t=p["t"], edge=p["edge"], span=p["hours"] * cycles)
            if p["edge"] is not None and longest > p["edge"]:
                continue
            came = ap.came_measured(pairs_seen(history, p["item"], p["t"], scans[k], p.get("price")), p["t"], p["hours"],
                                    cycles)
            got["checks"].append({"p": p[which], "o": int(came[-1] >= p["units"] - SETTLE_SLACK), "t": p["t"], "at": scans[k],
                                  "level": p.get("level") or 0})
            if which == "sells" and isinstance(p.get("gold"), (list, tuple)):
                a, b, d = p["gold"]
                out_at = next((c for c, n in enumerate(came) if n >= p["units"] - SETTLE_SLACK), cycles)
                flips.append({"t": p["t"], "at": scans[k], "gold": min(p["units"], came[-1]) * a + b - out_at * d})
    got = {w: {k: v for k, v in got.items() if k != "t"} for w, got in out.items()}
    return {**got, "flips": flips}


RECORD_ENDS = {"sold": 1, "partly": 0, "expired": 0, "removed": 0}


def record_checks(history, auctions, ladder_at, durations, rules, classes):
    import auctionpicks as ap
    scans = [t for t, _ in history.scans]
    fits, out = {}, []
    for a in sorted(auctions, key=lambda a: a.get("posted") or 0):
        o = RECORD_ENDS.get(a.get("outcome"))
        key, posted, unit = a.get("itemKey"), a.get("posted"), a.get("unit")
        hours = (durations or {}).get(a.get("duration"))
        if o is None or a.get("sure") == "guess" or not key or posted is None or not unit or not hours:
            continue
        j = bisect.bisect_right(scans, posted) - 1
        if j < 0:
            continue
        t, sid = history.scans[j]
        if t not in fits:
            known = history.upto(t)
            edges = history.edges(t)
            parts = {k: [(s, ad.sales_of(r), False) for s, r in rows if ad.sales_of(r)] for k, rows in known.items()}
            fit = am.fit_sales({k: [(s, p) for s, p, _ in v] for k, v in parts.items()}, edges, None, t)
            evs = {k: am.evidence(v, t, fit) for k, v in parts.items()}
            fits[t] = (fit, evs, am.priors_of(evs, classes), max((ev["pairs"] for ev in evs.values()), default=0),
                       am.undercuts_of(parts, edges, t, classes))
        fit, evs, priors, pairs, (fit_under, under_of) = fits[t]
        fig = am.sales_figure(evs.get(key) or am.evidence([], t, fit), priors.get(am.subclass_of(classes, key), am.PRIOR_LEAST),
                              pairs, fit, ad.kind_of(key))
        steps = ladder_at(sid, key)
        if not fig or fig.get("a") is None or steps is None:
            continue
        front = ap.ahead(steps, unit, ap.newest_first(rules, key))
        demand, under, _ = ap.queue(fig, under_of(key), fit, fit_under, hours / ad.HOUR, 1, key)
        p = float((ap.sold_by(demand, under, front)[:, 0] >= a["units"]).mean())
        out.append({"t": posted, "item": key, "units": a["units"], "p": p, "o": o})
    return out


def unchecked_of(target):
    seen = (target or {}).get("seen") or {}
    checked = ((target or {}).get("before") or {}).get("n")
    far = seen.get("apart") is not None and seen.get("edge") is not None and seen["apart"] > seen["edge"]
    return seen if far and not checked else None


def pairs_seen(history, item, t, end, price=None):
    rows = history.readings(item, t)
    ts = [s for s, _ in rows]
    i = bisect.bisect_right(ts, t)
    out, before, older = [], t, rows[i - 1][1] if i else None
    for s, r in rows[i:bisect.bisect_right(ts, end)]:
        part = ad.sales_of(r)
        if part:
            out.append((max(before, s - part[ad.S_HOURS] * ad.HOUR), s, part[ad.S_UNDER], sold_at(part, price, older)))
        before, older = s, r
    return out


def floor_seen(r):
    front, bait = (r[ad.R_FRONT] or [], r[ad.R_BAIT] or 0) if r else ([], 0)
    return front[bait][1] / front[bait][0] if bait < len(front) else None


def sold_at(part, price, older):
    if price is None or len(part) <= ad.S_PRICES:
        return part[ad.S_SOLD]
    floor = floor_seen(older)
    place = round(price / floor, ad.PLACE_DIGITS) if floor else math.inf
    if place <= 1:
        return part[ad.S_SOLD]
    return sum(u for x, u in part[ad.S_PRICES] if x >= place)



CAL_BANDS = 10


def calibration(checks, now=None):
    if len(checks) < N_LEAST:
        return []
    weights = [1.0] * len(checks) if now is None else ad.aged([c["t"] for c in checks], now)
    bands = [[i / CAL_BANDS, (i + 1) / CAL_BANDS, 0.0, 0.0, 0] for i in range(CAL_BANDS)]
    for c, w in zip(checks, weights):
        b = bands[min(CAL_BANDS - 1, int(c["p"] * CAL_BANDS))]
        b[2] += c["o"] * w
        b[3] += w
        b[4] += 1
    join = lambda a, b: [a[0], b[1], a[2] + b[2], a[3] + b[3], a[4] + b[4]]
    pooled = []
    for b in bands:
        if pooled and pooled[-1][4] < N_LEAST:
            pooled[-1] = join(pooled[-1], b)
        else:
            pooled.append(b)
    if len(pooled) > 1 and pooled[-1][4] < N_LEAST:
        pooled[-2:] = [join(pooled[-2], pooled[-1])]
    share = lambda b: b[2] / b[3] if b[3] else 0.0
    steps = []
    for b in pooled:
        steps.append(b)
        while len(steps) > 1 and share(steps[-1]) < share(steps[-2]):
            steps[-2:] = [join(steps[-2], steps[-1])]
    return [[round(b[0], 4), round(b[1], 4), round(share(b), 4), b[4]] for b in steps]


def calibrated(steps, p):
    if not steps:
        return None
    s = next((s for s in steps if p < s[1]), steps[-1])
    return s[2] if s[2] is not None else min(p, s[4])


def in_band(p, low, high):
    return low <= p < high or (high >= 1 and p >= 1)


def shown_map(steps, settled, rows, now):
    weights = [1.0] * len(rows) if now is None else ad.aged([r["t"] for r in rows], now)
    mixed, most = [], 1.0
    for low, high, share, n in reversed(steps):
        model = [{"p": min(c["p"], most), "o": c["o"]} for c in settled if in_band(c["p"], low, high)]
        inside = [(r, w) for r, w in zip(rows, weights) if in_band(r["raw"], low, high)]
        err = lambda key: sum(w * (min(r[key], most) - r["o"]) ** 2 for r, w in inside)
        use = test_of(score(model)) == "off" or (len(inside) >= N_LEAST and err("p") < err("raw"))
        mixed.append([low, high, min(share, most) if use else None, n, most])
        most = min(share, most) if use else min(low, most)
    if all(s[2] is None for s in mixed):
        return []
    return [[s[0], s[1], None if s[2] is None else round(s[2], 4), s[3], round(s[4], 4)] for s in reversed(mixed)]


def recalibrated_checks(checks):
    out = []
    for t in sorted({c["t"] for c in checks}):
        settled = [c for c in checks if c["at"] <= t]
        steps = calibration(settled, t)
        if not steps:
            continue
        shown = shown_map(steps, settled, [r for r in out if r["at"] <= t], t)
        out += [{"p": calibrated(steps, c["p"]), "shown": calibrated(shown, c["p"]) if shown else c["p"], "raw": c["p"],
                 "o": c["o"], "t": c["t"], "at": c["at"]} for c in checks if c["t"] == t]
    return out


def target_of(checks, now):
    steps = calibration(checks, now)
    after = recalibrated_checks(checks)
    shown = shown_map(steps, checks, after, now)
    brier = lambda key: round(sum((r[key] - r["o"]) ** 2 for r in after) / len(after), 5)
    bands = []
    for low, high, share, _, most in shown or [[lo, hi, None, n, 1.0] for lo, hi, _, n in steps]:
        rows = ([{"p": min(r["p"], most), "o": r["o"]} for r in after if in_band(r["raw"], low, high)] if share is not None
                else [{"p": min(c["p"], most), "o": c["o"]} for c in checks if in_band(c["p"], low, high)])
        use = "corrected" if share is not None else "capped" if most < high else "model"
        bands.append({"low": low, "high": high, "use": use, **score(rows)})
    use = {"corrected": sum(b["use"] == "corrected" for b in bands), "capped": sum(b["use"] == "capped" for b in bands), "of": len(bands)}
    return {"before": score(checks), "after": score(after), "shown": score([{"p": r["shown"], "o": r["o"]} for r in after]),
            "steps": steps, "map": shown, "use": use, "bands": bands,
            "brier": {"model": brier("raw"), "corrected": brier("p"), "shown": brier("shown")} if after else None}


def picks_scores(settled, now, skipped=0):
    out = {}
    for which in ("sells", "one"):
        s = settled[which]
        at = lambda level: [c for c in s["checks"] if c.get("level", 0) == level]
        got = {**target_of(at(0), now), "seen": {k: s[k] for k in ("apart", "edge", "span")}}
        out[which] = {**got, "apart": unchecked_of(got),
                      "above": [{"low": low, "high": high, **target_of(at(level), now)}
                                for level, (low, high) in enumerate(zip(LEVELS, LEVELS[1:] + (None,)), 1)]}
    flips = settled.get("flips") or []
    out["flips"] = {"n": len(flips), "gained": sum(f["gold"] > 0 for f in flips), "lost": sum(f["gold"] < 0 for f in flips),
                    "net": round(sum(f["gold"] for f in flips))}
    out["skipped"] = skipped
    return out


def sell_scores(settled, now, skipped=0, vendor=()):
    out = picks_scores(settled, now, skipped)
    out.pop("flips", None)
    out["vendor"] = {"n": len(vendor), "gold": round(sum(p.get("gold") or 0 for p in vendor))}
    return out


def target_at(tested, which, level):
    got = (tested or {}).get(which) or {}
    above = got.get("above") or []
    return got if level == 0 else above[level - 1] if level <= len(above) else {}


def map_of(cal, which, level):
    maps = (cal or {}).get(which) or []
    return maps[level] if level < len(maps) else None


def maps_of(tested):
    return {which: [target_at(tested, which, level).get("map") for level in range(len(LEVELS) + 1)] for which in ("sells", "one")}


def band_of(tested, which, p, level=0):
    bands = target_at(tested, which, level).get("bands") or []
    return next((b for b in bands if p < b["high"]), bands[-1] if bands else None)



def columns(rows, fields):
    return {f: [r[f] for r in rows] for f in fields}


def rows_of(cols, fields):
    return [dict(zip(fields, values)) for values in zip(*(cols[f] for f in fields))]


def walk_read(history, breaks, classes, upto, hold=None):
    hold = hold or hold_of_house(None)
    scans = history.scans[:upto]
    if not scans:
        return None
    end, last = scans[-1][0], scans[-2][0] if len(scans) > 1 else scans[-1][0]
    prints = {t: hashlib.sha1() for t, _ in scans}
    for k in sorted(history.items):
        for t, r in history.items[k]:
            if t in prints:
                prints[t].update(json.dumps([k, r]).encode())
    bands = {t: b for t, b, _ in history.heads}
    days = {}
    for t, _, longest in history.heads:
        if day_of(t) < day_of(last):
            days[day_of(t)] = longest
    upto_end = {k: [b for b in v if b <= end] for k, v in breaks.items()}
    suffixed, since = history.pool or ({}, None)
    known = [[i, suffixed[i]] for i in history.known(last)]
    return {"marks": walk_marks(),
            "scans": [[t, sid, prints[t].hexdigest(), bands.get(t)] for t, sid in scans],
            "days": [[d, longest] for d, longest in sorted(days.items())],
            "breaks": hashlib.sha1(json.dumps({k: v for k, v in sorted(upto_end.items()) if v}).encode()).hexdigest(),
            "classes": hashlib.sha1(json.dumps(sorted(classes[0].items())).encode()).hexdigest(), "hold": list(hold),
            "pool": hashlib.sha1(json.dumps([since if known else None, known]).encode()).hexdigest()}


def kept_walk(folder, history, breaks, classes, hold=None):
    path = os.path.join(folder, WALKED)
    try:
        with open(path, "rb") as f:
            kept = json.loads(gzip.decompress(f.read()).decode("utf-8"))
    except (OSError, ValueError, EOFError):
        return None
    if not kept or not kept.get("read") or len(kept["read"]["scans"]) > len(history.scans):
        return None
    return kept if walk_read(history, breaks, classes, len(kept["read"]["scans"]), hold) == kept["read"] else None


def walk_kept(history, walked, breaks, classes, hold=None):
    last = history.scans[-1][0] if history.scans else 0
    keep = lambda rows: [list(x) for x in rows if x[0] >= last - FIT_DAYS * ad.DAY]
    return {"scans": [t for t, _ in history.scans], "read": walk_read(history, breaks, classes, len(history.scans), hold),
            "skipped": walked.get("skipped") or 0,
            "records": {name: columns(walked[name], fields) for name, fields in RECORDS},
            "scored": keep(walked["scored"]), "pits": keep(walked["pits"])}


def coverage(records, key):
    return score([{"p": HELD, "o": r[key]} for r in records])


def split(records, by):
    groups = collections.defaultdict(list)
    for r in records:
        groups[by(r)].append(r)
    return groups


def price_scores(records):
    def errors(rs):
        e = [r["error"] for r in rs]
        if not e:
            return {"n": 0}
        mid = ad.median([abs(x) for x in e])
        return {"n": len(e), "median": round(math.exp(mid) - 1, 4), "bias": round(math.exp(sum(e) / len(e)) - 1, 4),
                "p90": round(math.exp(sorted(abs(x) for x in e)[int(0.9 * (len(e) - 1))]) - 1, 4)}

    def part(rs):
        return {"shown": coverage(rs, "shown"), "next": coverage(rs, "next"), "error": errors(rs)}
    return {**part(records), "words": {w: part(v) for w, v in split(records, lambda r: r["word"]).items()},
            "spans": {s: part(v) for s, v in split(records, lambda r: span_of(r["hours"])).items()},
            "kinds": {s: part(v) for s, v in split(records, lambda r: r.get("kind")).items()}}


def sales_scores(records):
    def errors(rs):
        if not rs:
            return {"n": 0}
        d = [r["day"] - r["seen"] for r in rs]
        return {"n": len(d), "median": round(ad.median([abs(x) for x in d]), 3), "bias": round(sum(d) / len(d), 3),
                "pair": round(ad.median([abs(r["pred"] - r["sold"]) for r in rs]), 3)}

    def part(rs):
        return {"shown": coverage(rs, "shown"), "next": coverage(rs, "next"), "error": errors(rs)}
    return {**part(records), "words": {w: part(v) for w, v in split(records, lambda r: r["word"]).items()},
            "rates": {s: part(v) for s, v in split(records, lambda r: r["rate"]).items()},
            "spans": {s: part(v) for s, v in split(records, lambda r: span_of(r["hours"])).items()},
            "kinds": {s: part(v) for s, v in split(records, lambda r: r.get("kind")).items()},
            "from": {s: part(v) for s, v in split(records, lambda r: r["from"]).items()}}


def state_scores(records):
    out = {}
    by = lambda r: r["state"] if r.get("sure") is None else f'{r["state"]} {"sure" if r["sure"] else "uncertain"}'
    for name, rs in [*split(records, lambda r: r["state"]).items(), *split(records, by).items()]:
        if name in out:
            continue
        state = name.split(" ")[0]
        out[name] = {"n": len(rs), "same": round(sum(r["next"] == state for r in rs) / len(rs), 4),
                     "side": round(sum(r["side"] for r in rs) / len(rs), 4)}
    return out



def run(house, files=None, now=time.time):
    import gamedata
    files = ad.day_files(house.folder) if files is None else files
    history = History(files, house.pool)
    breaks, classes = ad.item_breaks(ad.known_builds()), gamedata.item_classes()
    answers = kept_answers(house)
    fees = answer_fees(house, answers)
    book = book_of(house, fees)
    hold = hold_of_house(getattr(house, "faction", None), fees)
    held = held_of(house, answers)
    kept = kept_walk(house.folder, history, breaks, classes, hold) if house.keep else None
    walked = walk_chain(history, breaks, classes, kept, hold, book, held)
    out = {"made": now(), "newest": history.scans[-1][1] if history.scans else None, "marks": marks(),
           "kept": len(kept["scans"]) if kept else 0, **answer_of(history, walked)}
    if house.keep:
        os.makedirs(house.folder, exist_ok=True)
        store.write_bytes(os.path.join(house.folder, WALKED),
                          gzip.compress(jsontext.dumps(walk_kept(history, walked, breaks, classes, hold)).encode("utf-8"), 6))
        store.write_bytes(os.path.join(house.folder, BACKTEST), jsontext.dumps(out).encode("utf-8"))
    return out


def book_of(house=None, fees=None):
    import auction
    import gamedata
    paid = {}

    def ladder(sid, known):
        try:
            with gzip.open(house.scan_file(sid), "rt", encoding="utf-8") as f:
                scan = auction.Scan.from_json(json.load(f))
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return None
        pooled, out = auction.pooled_in(scan.keys, known), collections.defaultdict(list)
        for a in scan.auctions():
            if not a[5] & auction.AUCTION_NOKEY:
                out[auction.row_key(a[0], a[1], pooled)].append(a)
        return out

    def vendor(key):
        item = key.split(":")[0]
        if item not in paid:
            paid[item] = (gamedata.item_sell_price(int(item)) if item.isdigit() else None) or 0
        return paid[item]
    market = (am.load(house.folder) if house is not None and getattr(house, "folder", None) else None) or {}
    return {"fees": fees or answer_fees(house), "rules": market.get("rules") or {},
            "ladder": ladder if hasattr(house, "scan_file") else None, "vendor": vendor}


def marks():
    return walk_marks() + [SCORE_MARK]


def walk_marks():
    return [CHAIN_MARK, ad.MODEL_MARK, ad.SALES_MARK, am.MARK]


def due(house):
    whole = ad.read_metas(house)
    got = load(house.folder) if whole else None
    return bool(whole) and (not got or got.get("newest") != whole[-1]["id"] or got.get("marks") != marks())


def load(folder):
    import playerstores
    return store.load_json(playerstores.standing(os.path.join(folder, BACKTEST)), None)
