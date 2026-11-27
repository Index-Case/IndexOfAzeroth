# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import gc
import gzip
import hashlib
import json
import math
import os
import threading
import time

import numpy as np

import auctiondays as ad
import auctionmarket as am
import jsontext
import picksreport
import store
import workers
from serverlog import log_error, log_note, start_thread

DRAWS = 1000
STEP_HOURS = 1.0
GROUPS = 50
RELISTS = 3
RESERVE = 0.20
SHARE_CAP = 0.40
KELLY_PART = 0.25
SHOWN = 25
FILL_TRIES = 3
AUCTIONS_MOST = 30
SALES_AT_LEAST = 2
LOW_Q, HIGH_Q = 0.10, 0.90
WIDE_LOW, WIDE_HIGH = 0.05, 0.95
STEPS_HIGH = 4
STEPS_LOW = 1



def hold_of(fees):
    return fees["hours"], RELISTS


def newest_first(rules, key):
    return (rules or {}).get("style") == "commodity" and ad.kind_of(key) == "pooled"


def ahead(steps, price, strict):
    return sum(s[1] for s in steps if (s[0] < price if strict else s[0] <= price))


BAND = 0.10


def list_price(steps, strict, market=None):
    anchor = next((matched(s[0], strict) for s in steps if s[2] > 1), None)
    if market is None:
        return anchor if anchor is not None else matched(steps[0][0], strict)
    top = min(market["high"], market["price"] * (1 + BAND))
    return anchor if anchor is not None and anchor <= top else market["price"]


def matched(p, strict):
    return p if strict or p <= 1 else p - 1


def sell_price(steps, strict, market, sales, floor):
    bound = list_price(steps, strict, market)
    for price in [bound] + [matched(s[0], strict) for s in reversed(steps) if floor < matched(s[0], strict) < bound]:
        fig = demand_at(sales, price, floor)
        if fig is not None:
            return price, fig
    return matched(floor, strict), sales


def evidence_of(sales, price, floor):
    priced = (sales or {}).get("priced") or 0.0
    ratio = round(price / floor, ad.PLACE_DIGITS) if sales and floor else 1.0
    at = priced if ratio <= 1 else next((e for r, e in sales.get("above") or () if r >= ratio), 0.0)
    return round(priced, 1), round(at, 1)


def ladder_of(rows):
    return [s[:3] for s in ad.ladder(rows) if not s[3]]


def ladder_left(auctions, top):
    out = []
    for p, u in auctions:
        if p > top:
            break
        p = round(p, 4)
        if out and out[-1][0] == p:
            out[-1][1] += u
            out[-1][2] += 1
        else:
            out.append([p, u, 1])
    return out



def seed_of(key):
    return int(hashlib.sha256(str(key).encode()).hexdigest()[:8], 16)


def demand_at(sales, price, floor):
    priced = (sales or {}).get("priced") or 0.0
    if not sales:
        return None
    ratio = round(price / floor, ad.PLACE_DIGITS) if floor else 1.0
    if not priced:
        return sales if ratio <= 1 and sales.get("from") == "prior" else None
    if ratio <= 1:
        return sales if priced >= SALES_AT_LEAST else None
    at = next((e for r, e in sales.get("above") or () if r >= ratio), 0.0)
    if at < SALES_AT_LEAST:
        return None
    return {**sales, "a": sales["a"] * min(1.0, at / priced)}


def undercuts_at(under, price, floor):
    ratio = round(price / floor, ad.PLACE_DIGITS) if under and floor else 1.0
    if ratio <= 1:
        return under
    more = 0.0
    for r, e in under.get("below") or ():
        if r > ratio:
            break
        more = e
    return {**under, "a": under["a"] + more} if more else under


def queue(sales, under, fit, fit_under, hours, cycles, key, crowd=1.0):
    rng = np.random.default_rng(seed_of(key))
    paths = DRAWS // GROUPS
    steps = max(1, math.ceil(hours / STEP_HOURS))

    def flow(fig, f, times=1.0):
        if not fig:
            return np.zeros((DRAWS, cycles, steps))
        lam = np.repeat(rng.gamma(fig["a"], 1.0 / fig["b"], GROUPS), paths)
        k = am.spread_shape(f, am.DAY_HOURS, fig.get("kind"))
        g = rng.gamma(k, 1.0 / k, (DRAWS, cycles)) if k else np.ones((DRAWS, cycles))
        pace = am.pace_of(f)[0] * hours / steps * times
        return rng.poisson((lam[:, None] * g * pace)[:, :, None], (DRAWS, cycles, steps)) * fig["units"]
    return flow(sales, fit), flow(under, fit_under, crowd), np.repeat(np.arange(GROUPS), paths)


def sold_by(demand, under, units_ahead):
    draws, cycles, steps = demand.shape
    came = np.zeros((draws, cycles))
    total = np.zeros(draws)
    for c in range(cycles):
        front = np.full(draws, float(units_ahead) if c == 0 else 0.0)
        for s in range(steps):
            front = front + under[:, c, s]
            served = np.minimum(demand[:, c, s], front)
            front = front - served
            total = total + demand[:, c, s] - served
        came[:, c] = total
    return came


def listing_odds(sales, under, fit, fit_under, hours, cycles, key, units):
    demand, flow, _ = queue(sales, under, fit, fit_under, hours, cycles, key)
    came = sold_by(demand, flow, 0)
    return float((came[:, -1] >= units).mean()), float((came[:, 0] >= units).mean())


def came_measured(pairs, t, hours, cycles):
    span = hours * ad.HOUR
    came, fronts = [0.0] * cycles, [0.0] * cycles
    for a, s, new, sold in pairs:
        long = max(1e-9, s - a)
        for c in range(cycles):
            part = (min(s, t + (c + 1) * span) - max(a, t + c * span)) / long
            if part <= 0:
                continue
            fronts[c] += new * part
            served = min(sold * part, fronts[c])
            fronts[c] -= served
            for d in range(c, cycles):
                came[d] += sold * part - served
    return came


def walk_prices(q, age_hours, hours, cycles, breaks_since, key, state=None):
    rng = np.random.default_rng(seed_of(key) + 1)
    start = q * age_hours + ad.BREAK_P * breaks_since
    first = rng.normal(0.0, math.sqrt(start), DRAWS)
    steps = rng.normal(0.0, math.sqrt(q * hours), (DRAWS, cycles - 1)) if cycles > 1 else np.zeros((DRAWS, 0))
    walk = np.cumsum(np.column_stack([first, steps]), axis=1) - (start + q * hours * np.arange(cycles)) / 2
    if state and state["kappa"] > 0:
        since = age_hours + hours * np.arange(cycles)
        walk = walk - state["dev"] * (1 - np.exp(-state["kappa"] * since))
    return np.exp(walk)


def outcome(sold, units, price, moves, fees, vendor):
    held = np.broadcast_to(np.asarray(units, dtype=float), (len(sold),))[:, None]
    got = np.minimum(sold, held)
    step = np.diff(np.column_stack([np.zeros(len(got)), got]), axis=1)
    gold = (step * (1 - fees["cut"]) * price * moves).sum(axis=1)
    left = held - got
    dep = fees["deposit"]
    lost = np.where(left > 0, np.maximum(dep["least"], dep["share"] * (vendor or 0) * left), 0.0)
    gold = gold - lost.sum(axis=1)
    up = (np.column_stack([np.zeros(len(got)), got[:, :-1]]) < held).sum(axis=1)
    return gold + left[:, -1] * (vendor or 0), got[:, -1], up



def quantiles(values, qs, w=None):
    if w is None:
        return np.quantile(values, qs)
    order = np.argsort(values, kind="stable")
    v, ws = values[order], w[order]
    cum = np.cumsum(ws)
    return np.interp(np.asarray(qs) * cum[-1], cum - ws / 2, v)


def mean_of(values, w=None):
    return float(values.mean() if w is None else np.average(values, weights=w))


def share_of(mask, w=None):
    if w is None:
        return float(mask.mean())
    total = w.sum()
    return float(w[mask].sum() / total) if total else 0.0


def spread(values, w=None):
    q = quantiles(values, [LOW_Q, HIGH_Q, WIDE_LOW, WIDE_HIGH], w)
    return {"mean": mean_of(values, w), "p10": float(q[0]), "p90": float(q[1]), "p5": float(q[2]), "p95": float(q[3])}


def kelly(profit, groups, w=None):
    won, lost = profit > 0, profit < 0
    alike = np.ones(len(profit)) if w is None else w
    if not (alike[won] > 0).any():
        return 0.0
    if not (alike[lost] > 0).any():
        return 1.0
    chance = float(np.average(won, weights=alike))
    gain = float(quantiles(profit[won], [0.5], None if w is None else w[won])[0])
    loss = float(quantiles(-profit[lost], [0.5], None if w is None else w[lost])[0])
    return max(0.0, KELLY_PART * (chance - (1 - chance) / (gain / loss)))


def chance_low(profit, groups, w=None):
    won = profit > 0
    alike = np.ones(len(profit)) if w is None else w
    totals = np.bincount(groups, weights=alike, minlength=GROUPS)[:GROUPS]
    wins = np.bincount(groups, weights=alike * won, minlength=GROUPS)[:GROUPS]
    return float(np.quantile((wins + 0.5) / (totals + 1.0), WIDE_LOW))


def recalibrate(draws, held, some, steps, groups, missing):
    import backtest
    p = float(held[some].mean()) if some.any() else 0.0
    c = backtest.calibrated(steps, p) if some.any() else None
    if c is None:
        return draws, None, groups, p, p
    real = len(held)
    for outcome, value in (("unsold", False), ("sold", True)):
        if (c < 1 if outcome == "unsold" else c > 0) and not (held[some] == value).any():
            draws = {k: np.concatenate([v, np.full(GROUPS, missing[outcome][k], dtype=float)]) for k, v in draws.items()}
            held = np.concatenate([held, np.full(GROUPS, value)])
            some = np.concatenate([some, np.ones(GROUPS, dtype=bool)])
            groups = np.concatenate([groups, np.arange(GROUPS)])
    bought = some[:real].sum() / real
    w = np.where(some, 0.0, 1.0 / real)
    for value, share in ((True, c), (False, 1 - c)):
        these = some & (held == value)
        if these.any():
            w[these] = bought * share / these.sum()
    return draws, w, groups, p, c


def quality(mean, p5, p95, scans, measured, fees, ctx, market=True, rated=None, vendor=0, prior=False):
    from counting import steps_of
    sure = p95 - p5 <= 1e-9 * max(1.0, abs(mean))
    steps = 5 if sure and scans else steps_of(max(abs(mean), 1.0), p5, p95, scans, measured)
    apart = rated is None and market and ((ctx.get("tested") or {}).get("sells") or {}).get("apart")
    why = [] if rated is not None else ["backtest.apart" if apart else "backtest"]
    tested = [] if rated is None else [TESTED[w] for w in rated["why"] if w in TESTED]
    if prior:
        why.append("prior")
    if rated is not None:
        steps = min(steps, rated["steps"])
    if market and not fees["read"]:
        why.append("fees")
    if ctx["age"] > ad.DAY:
        why.append("old")
    if ctx["gap"] > 2 * ad.DAY:
        why.append("apart")
    if market:
        why += [f"effect.{e}" for e in ctx["unchecked"]]
    if vendor is None:
        why.append("vendor")
    steps = max(0, steps - len(why))
    if expects_loss(mean):
        steps = min(steps, STEPS_LOW)
        why.append("loses")
    return steps, tested + why


def expects_loss(expected):
    return round(expected) <= 0


TESTED = {"checks.few": "tested.few", "backtest.off": "tested.off", "backtest.near": "tested.near"}


def worst_of(units, cost, vendor, fees, cycles):
    dep = fees["deposit"]
    return units * vendor - cost - cycles * max(dep["least"], dep["share"] * vendor * units)


def post_floor(units, vendor, fees):
    if not vendor:
        return None
    dep = fees["deposit"]
    deposit = max(dep["least"], dep["share"] * vendor * units)
    return round((units * vendor + deposit) / (units * (1 - fees["cut"])), 2)


def chance_of(ctx, which, p, hold=None, level=0):
    import backtest
    got = backtest.calibrated(backtest.map_of(ctx["cal"], which, level), p)
    got = p if got is None else got
    return got if hold is None else min(got, hold)


def tested_of(rated):
    return {"n": rated["checks"], "came": rated["came"], "predicted": rated["predicted"]} if rated and rated["checks"] else None


def rated_of(ctx, p, scans, level=0):
    import backtest
    band = backtest.band_of(ctx.get("tested"), "sells", p, level)
    return backtest.quality({"score": band}, None, scans, ctx["newest"], ctx["now"]) if band else None


def word_of(steps):
    return "high" if steps >= STEPS_HIGH else "medium" if steps > STEPS_LOW else "low"



def state_reading(row, moved):
    st = row.get("state") or {}
    got = (moved or {}).get(st.get("state"))
    if not got or st.get("change") is None:
        return None
    return {"state": st["state"], "dev": math.log1p(st["change"]), "kappa": got["kappa"], "under": got["under"]}


def item_inputs(row, model, key, now, newest, moved=None):
    sales = row.get("sales")
    if not sales or sales.get("a") is None:
        return None
    q, _ = ad.noise_of(model, key)
    breaks = sorted((model.get("breaks") or {}).get(key.split(":")[0], []))
    price = row.get("price") or {}
    return {"q": q, "age": max(0.0, now - (newest or now)) / ad.HOUR, "breaks": ad.breaks_between(breaks, newest or now, now),
            "scans": row.get("scans") or 0, "measured": bool(price.get("measured") and sales.get("measured")),
            "sales": sales, "under": row.get("under"), "state": state_reading(row, moved)}


def crowd_of(inp):
    return inp["state"]["under"] if inp["state"] else 1.0


def flip_limit(market, fees, units, vendor, cycles):
    dep = fees["deposit"]
    deposits = cycles * max(dep["least"], dep["share"] * vendor * units)
    return min(market["low"], market["price"] * (1 - fees["cut"]) - deposits / units)


RESET_UNITS = 5
RESET_COST = 500000
RESET_OVER = 2.0
RESET_UNMEASURED = ("sellers",)


def day_rate(fig):
    return fig["a"] / fig["b"] * fig["units"] if fig else None


def reset_unmet(market, units, cost, price, sales=None, under=None, floor=None):
    demand = demand_at(sales, price, floor) if sales and floor else None
    restock = undercuts_at(under, price, floor) if under and floor else None
    return [c for c, bad in (("band", price > min(market["high"], market["price"] * (1 + BAND))),
                             ("size", units > RESET_UNITS), ("margin", price < RESET_OVER * cost / units),
                             ("cost", cost > RESET_COST), ("demand", demand is None),
                             ("restock", demand is None or restock is None or day_rate(restock) >= day_rate(demand)))
            if bad]


def kind_of(plan, row, fees, units, cost, up_to, price, cycles, vendor, floor=None):
    if plan == "vendor":
        return "vendor"
    market = row.get("price")
    if market is None:
        return None
    if price > market["price"]:
        return None if reset_unmet(market, units, cost, price, row.get("sales"), row.get("under"), floor) else "reset"
    if up_to > flip_limit(market, fees, units, vendor, cycles):
        return None
    return "snipe" if row.get("bait") else "flip"


def buy_item(key, row, rows, ctx, detail=None, vendor_flips=True):
    steps = ladder_of(rows)
    import backtest
    inp = item_inputs(row, ctx["model"], key, ctx["now"], ctx["newest"], ctx.get("moved"))
    if not inp:
        return None
    hours, cycles = hold_of(ctx["fees"])
    strict = newest_first(ctx["rules"], key)
    demand, under, groups = queue(inp["sales"], inp["under"], ctx["fit"], ctx["under"], hours, cycles, key, crowd_of(inp))
    moves = walk_prices(inp["q"], inp["age"], hours, cycles, inp["breaks"], key, inp["state"])
    vendor = row.get("vendorPays") or 0
    share = ctx["survive"]
    market = row.get("price")
    reach = float(np.quantile(demand.sum(axis=(1, 2)), WIDE_HIGH))
    auctions = sorted(((a[3] / a[2], a[2]) for a in rows if a[3] > 0 and a[2] > 0))
    if not auctions or (len(steps) < 2 and not (vendor and auctions[0][0] < vendor)):
        return None
    floor = ad.floor_of(auctions)
    came, flows, ahead_flows = {}, {}, {}

    def demand_of(price):
        if price not in flows:
            fig = demand_at(inp["sales"], price, floor)
            flows[price] = None if fig is None else demand if fig is inp["sales"] else \
                queue(fig, None, ctx["fit"], ctx["under"], hours, cycles, key)[0]
        return flows[price]

    def under_of(price):
        if price not in ahead_flows:
            fig = undercuts_at(inp["under"], price, floor)
            ahead_flows[price] = under if fig is inp["under"] else \
                queue(None, fig, ctx["fit"], ctx["under"], hours, cycles, key, crowd_of(inp))[1]
        return ahead_flows[price]

    def came_to(price, front):
        if (price, front) not in came:
            came[(price, front)] = sold_by(demand_of(price), under_of(price), front)
        return came[(price, front)]
    curve, best, units = [], None, 0
    far = ad.far_from_rest(auctions)[1]
    there = np.random.default_rng(seed_of(key) + 2).random((DRAWS, min(AUCTIONS_MOST, len(auctions)))) < share
    have, paid = np.zeros(DRAWS), np.zeros(DRAWS)
    for k in range(1, min(AUCTIONS_MOST, len(auctions)) + 1):
        units += auctions[k - 1][1]
        if k > 1 and units > max(reach, auctions[0][1]):
            break
        have = have + there[:, k - 1] * auctions[k - 1][1]
        paid = paid + there[:, k - 1] * auctions[k - 1][1] * auctions[k - 1][0]
        cost = sum(c * p for p, c in auctions[:k])
        left = ladder_left(auctions[k:], far)
        if not left:
            break
        price = list_price(left, strict, market)
        kind = kind_of("house", row, ctx["fees"], units, cost, auctions[k - 1][0], price, cycles, vendor, floor)
        listable = kind is not None and demand_of(price) is not None
        flip = vendor > auctions[k - 1][0]
        if not listable and not flip:
            break
        front = ahead(left, price, strict)
        house = None
        if listable:
            gold, sold, up = outcome(came_to(price, front), have, price, moves, ctx["fees"], vendor)
            fee = ctx["fees"]
            worst = worst_of(units, cost, vendor, fee, cycles)
            draws, w, gs, p, c = recalibrate(
                {"profit": gold - paid, "sold": sold, "up": up, "gold": gold, "have": have.copy()}, sold >= have, have > 0,
                backtest.map_of(ctx["cal"], "sells", backtest.level_of(price, floor)), groups,
                {"unsold": {"profit": worst, "sold": 0, "up": cycles, "gold": worst + cost, "have": units},
                 "sold": {"profit": units * price * (1 - fee["cut"]) - cost, "sold": units, "up": 1,
                          "gold": units * price * (1 - fee["cut"]), "have": units}})
            house = {"plan": "house", "kind": kind, "price": price, "ahead": front, "w": w, "groups": gs, "p": p, "c": c,
                     **draws}
        top = house
        sure = have * vendor - paid
        if flip and (top is None or quantiles(top["profit"], [LOW_Q], top["w"])[0] <= np.quantile(sure, LOW_Q)):
            top = {"plan": "vendor", "kind": kind_of("vendor", row, ctx["fees"], units, cost, auctions[k - 1][0], vendor,
                                                     cycles, vendor), "price": vendor, "profit": sure, "sold": np.zeros(DRAWS), "up": np.zeros(DRAWS),
                   "gold": have * vendor, "ahead": front, "have": have.copy(), "w": None, "groups": groups, "p": None, "c": None}
        step = step_of(k, units, cost, auctions[k - 1][0], top)
        if top is not house:
            step["listing"] = house and step_of(k, units, cost, auctions[k - 1][0], house)
        curve.append(step)
        if detail == k and not vendor_flips and top is not house:
            best = (step["listing"], house) if house else None
        elif detail == k or (detail is None and (best is None or step["mean"] > best[0]["mean"])):
            best = (step, top)
    if not curve or best is None:
        return None
    step, top = best
    real = top["have"][:DRAWS]
    some = real > 0
    one = float((came_to(step["price"], top["ahead"])[:, 0] >= real)[some].mean()) if some.any() and top["plan"] == "house" \
        else 0.0
    return {"key": key, "sub": row.get("sub"), "inputs": inp, "curve": curve, "best": step,
            "draws": top if detail is not None else None, "groups": top["groups"] if detail is not None else None,
            "kelly": step["kelly"], "vendor": vendor, "oneRaw": one, "hold": [hours, cycles], "floor": floor}


def step_of(k, units, cost, up_to, top):
    q = quantiles(top["profit"], [LOW_Q, 0.5], top["w"])
    mean = mean_of(top["profit"], top["w"])
    return {"k": k, "units": units, "cost": cost, "upTo": up_to, "price": top["price"], "plan": top["plan"], "kind": top["kind"],
            "mean": mean, "var": mean_of((top["profit"] - mean) ** 2, top["w"]), "p10": float(q[0]),
            "median": float(q[1]), "kelly": kelly(top["profit"], top["groups"], top["w"]),
            "kellyLow": round(chance_low(top["profit"], top["groups"], top["w"]), 4)}


def offered(cand, vendor_flips):
    if vendor_flips or all(s["plan"] != "vendor" for s in cand["curve"]):
        return cand
    curve = []
    for s in cand["curve"]:
        s = s["listing"] if s["plan"] == "vendor" else s
        if s is None:
            break
        curve.append(s)
    if not curve:
        return None
    got = {**cand, "curve": curve}
    got["best"] = best_step(got, 0)
    got["kelly"] = got["best"]["kelly"]
    return got


def best_step(cand, budget):
    lam = 1.0 / (2 * budget) if budget else 0.0
    return max(cand["curve"], key=lambda s: s["mean"] - lam * s["var"])


def buy_pick(cand, row, rows, info, ctx, k=None, vendor_flips=True):
    full = buy_item(cand["key"], row, rows, ctx, k or cand["best"]["k"], vendor_flips)
    step, top, fees, inp = full["best"], full["draws"], ctx["fees"], full["inputs"]
    profit, w = top["profit"], top["w"]
    s = spread(profit, w)
    vendor, house = full["vendor"], step["plan"] == "house"
    import backtest
    level = backtest.level_of(step["price"], full["floor"])
    rated = rated_of(ctx, top["p"], inp["scans"], level) if house else None
    kind = step["kind"]
    seen = {**ctx, "unchecked": [*ctx["unchecked"], *RESET_UNMEASURED]} if kind == "reset" else ctx
    steps, why = quality(s["mean"], s["p5"], s["p95"], inp["scans"], inp["measured"] or not house, fees, seen, house, rated,
                         row.get("vendorPays"), prior=inp["sales"].get("from") == "prior")
    have = top["have"][:DRAWS]
    some = have > 0
    pick = {"item": cand["key"], "name": info.get("n"), "q": info.get("q"), "icon": info.get("icon"), "sub": row.get("sub"),
            "kind": kind, "units": step["units"], "auctions": step["k"], "cost": round(step["cost"]), "upTo": round(step["upTo"], 2),
            "there": round(float(some.mean()), 3), "got": round(float(have.mean()), 1),
            "sellAt": round(step["price"], 2), "sells": round(top["c"], 3) if house else None,
            "floor": post_floor(step["units"], vendor, fees) if house else None,
            "sellsOne": round(chance_of(ctx, "one", full["oneRaw"], top["c"], level), 3) if house else None,
            "gain": round(share_of(profit > 0, w), 3), "lose": round(share_of(profit < 0, w), 3),
            "expected": round(s["mean"]), "median": round(float(quantiles(profit, [0.5], w)[0])), "p10": round(s["p10"]),
            "p90": round(s["p90"]),
            "model": {"sells": round(top["p"], 3), "one": round(full["oneRaw"], 3)} if house else None,
            "worst": round(worst_of(step["units"], step["cost"], vendor, fees, full["hold"][1]) if house else float(profit.min())),
            "steps": steps, "word": word_of(steps), "vendor": row.get("vendorPays"),
            "lowered": why, "plan": step["plan"],
            "kelly": round(step["kelly"], 4), "kellyLow": round(step["kellyLow"], 4),
            "curve": [[c["units"], round(c["mean"]), round(c["cost"])] for c in cand["curve"]],
            "rests": rests_of(row, inp, ctx), "hold": full["hold"], "made": ctx["now"], "scan": ctx["newestId"],
            "inputs": {"sales": [inp["sales"]["a"], inp["sales"]["b"], inp["sales"]["units"]],
                       "under": [inp["under"]["a"], inp["under"]["b"], inp["under"]["units"]] if inp["under"] else None,
                       "q": inp["q"], "ahead": top["ahead"], "state": inp["state"]},
            "evidence": dict(zip(("seen", "at"), evidence_of(inp["sales"], step["price"], full["floor"]))),
            "tested": tested_of(rated)}
    pick["weak"] = weak_of(pick["expected"], pick["gain"])
    return pick


def weak_of(expected, chance):
    return [w for w, bad in (("loses", expects_loss(expected)), ("odds", chance is not None and chance < 0.5)) if bad]


def rests_of(row, inp, ctx):
    sales = inp["sales"]
    return {"scans": inp["scans"], "pairs": sales.get("pairs"), "newest": ctx["newest"], "priceSteps": (row.get("price") or {}).get("steps"),
            "salesSteps": sales.get("steps"), "salesFrom": sales.get("from")}



def fill(cands, budget, picks_of, vendor_flips=True, risk=1.0):
    offered_all = [offered(c, vendor_flips) for c in cands]
    hidden = sum(1 for c in offered_all if not c) if not vendor_flips else 0
    cands = [c for c in offered_all if c]
    spend = budget * (1 - RESERVE) if budget else 0.0
    lam = 1.0 / (2 * budget) if budget else 0.0
    taken, by_sub, spent, cost = {}, {}, 0.0, {}
    blocked, dead = {}, set()
    picksreport.note("fill", cands=len(cands), budget=round(budget or 0), spend=round(spend))
    funded = []
    for _ in range(FILL_TRIES):
        taken, by_sub, spent, cost, blocked = {}, {}, 0.0, {}, {}
        moving = True
        while moving:
            moving = False
            best = None
            for c in cands:
                if c["key"] in dead:
                    continue
                k = taken.get(c["key"], 0)
                if k >= len(c["curve"]):
                    continue
                nxt, was = c["curve"][k], c["curve"][k - 1] if k else None
                gain = nxt["mean"] - (was["mean"] if was else 0.0)
                var = nxt["var"] - (was["var"] if was else 0.0)
                more = nxt["cost"] - (was["cost"] if was else 0.0)
                if more <= 0 or gain - lam * var <= 0:
                    blocked[c["key"]] = "share"
                    continue
                sub = c["sub"]
                if spent + more > spend:
                    blocked[c["key"]] = "room"
                    continue
                if nxt["cost"] > nxt["kelly"] * budget * risk:
                    blocked[c["key"]] = "purse" if nxt["kelly"] > 0 else "kelly"
                    continue
                if by_sub.get(sub, 0.0) + more > SHARE_CAP * budget:
                    blocked[c["key"]] = "share"
                    continue
                value = (gain - lam * var) / more
                if best is None or value > best[0]:
                    best = (value, c, more)
            if best:
                _, c, more = best
                taken[c["key"]] = taken.get(c["key"], 0) + 1
                by_sub[c["sub"]] = by_sub.get(c["sub"], 0.0) + more
                cost[c["key"]] = cost.get(c["key"], 0.0) + more
                spent += more
                moving = True
                picksreport.funded(c, taken[c["key"]], more, spent)
        funded = []
        failed = False
        for c in cands:
            if c["key"] in dead:
                continue
            if taken.get(c["key"]):
                p = picks_of(c, c["curve"][taken[c["key"]] - 1]["k"])
                picksreport.note("drop" if p is None else "pick", i=c["key"], gold=p and p["expected"])
                if p is None:
                    spent -= cost.get(c["key"], 0.0)
                    by_sub[c["sub"]] = by_sub.get(c["sub"], 0.0) - cost.get(c["key"], 0.0)
                    taken.pop(c["key"], None)
                    dead.add(c["key"])
                    failed = True
                else:
                    funded.append(p)
        if not failed:
            break
    for p in funded:
        p["funded"] = True
    ranked = [(best_step(c, budget), c) for c in cands if not taken.get(c["key"])]
    ranked.sort(key=lambda sc: -(sc[0]["mean"] - lam * sc[0]["var"]))
    others = []
    for s, c in ranked:
        if len(funded) + len(others) >= SHOWN:
            break
        p = picks_of(c, s["k"])
        if p is None:
            continue
        p["funded"] = False
        p["unfunded"] = why_unfunded(p, budget, spend - spent, blocked.get(c["key"]))
        others.append(p)
        picksreport.note("out", i=c["key"], why=p["unfunded"], cost=p["cost"], gold=p["expected"])
    total = sum(p["expected"] for p in funded)
    picks = sorted(funded, key=lambda p: -p["expected"]) + others
    picksreport.note("settle", order=[p["item"] for p in picks], spent=round(spent), spend=round(spend), expected=total)
    return {"picks": picks, "spent": round(spent), "spend": round(spend), "expected": total,
            "left": round((budget or 0) - spent), "hidden": hidden}


def why_unfunded(pick, budget, room, why=None):
    if not budget:
        return "budget"
    if expects_loss(pick["expected"]):
        return "loses"
    if why:
        return why
    if pick["kelly"] <= 0:
        return "kelly"
    if pick["cost"] > room:
        return "room"
    return "share"



def sell_item(key, row, rows, units, ctx, yours=()):
    inp = item_inputs(row, ctx["model"], key, ctx["now"], ctx["newest"], ctx.get("moved"))
    steps = ladder_of(rows or [])
    known = row.get("vendorPays") is not None
    vendor = row.get("vendorPays") or 0
    if not inp or not steps:
        return None
    hours, cycles = hold_of(ctx["fees"])
    strict = newest_first(ctx["rules"], key)
    floor = ad.floor_of(sorted((r[3] / r[2], r[2]) for r in rows if r[3] > 0 and r[2] > 0))
    price, sales = sell_price(steps, strict, row.get("price"), inp["sales"], floor)
    import backtest
    level = backtest.level_of(price, floor)
    demand, under, groups = queue(sales, undercuts_at(inp["under"], price, floor), ctx["fit"], ctx["under"], hours,
                                  cycles, key, crowd_of(inp))
    moves = walk_prices(inp["q"], inp["age"], hours, cycles, inp["breaks"], key, inp["state"])
    sold = sold_by(demand, under, ahead(ladder_of(list(rows) + list(yours)) if yours else steps, price, strict))
    top = None
    fee = ctx["fees"]
    for n in sorted({max(1, int(round(units * f))) for f in (0.1, 0.25, 0.5, 0.75, 1.0)} | {1, units}):
        gold, got, up = outcome(sold, n, price, moves, fee, vendor)
        worst = worst_of(n, n * vendor, vendor, fee, cycles)
        draws, w, _, p, c = recalibrate(
            {"gain": gold - n * vendor, "gold": gold, "sold": got, "up": up}, got >= n, np.ones(len(got), dtype=bool),
            backtest.map_of(ctx["cal"], "sells", level), np.zeros(len(got), dtype=int),
            {"unsold": {"gain": worst, "gold": worst + n * vendor, "sold": 0, "up": cycles},
             "sold": {"gain": n * price * (1 - fee["cut"]) - n * vendor, "gold": n * price * (1 - fee["cut"]), "sold": n, "up": 1}})
        if top is None or mean_of(draws["gain"], w) > mean_of(top["gain"], top["w"]):
            top = {"price": price, "units": n, "w": w, "p": p, "c": c, "one": float((sold[:, 0] >= n).mean()), **draws}
    top["days"] = mean_of(top["up"], top["w"]) * hours / 24
    way = "vendor" if vendor and expects_loss(mean_of(top["gain"], top["w"])) else "house"
    if way == "vendor":
        return vendor_only(key, row, units)
    w = top["w"]
    s = spread(top["gain"], w)
    rated = rated_of(ctx, top["p"], inp["scans"], level)
    steps_q, why = quality(s["mean"], s["p5"], s["p95"], inp["scans"], inp["measured"], fee, ctx, rated=rated,
                           vendor=row.get("vendorPays"), prior=inp["sales"].get("from") == "prior")
    pick = {"item": key, "way": way, "units": units, "post": top["units"], "listAt": round(top["price"], 2),
            "floor": post_floor(top["units"], row.get("vendorPays"), fee),
            "sellsOne": round(chance_of(ctx, "one", top["one"], top["c"], level), 3), "sells": round(top["c"], 3),
            "beats": round(share_of(top["gain"] > 0, w), 3) if known else None,
            "gold": round(mean_of(top["gold"], w) + (units - top["units"]) * vendor),
            "gain": round(s["mean"]), "p10": round(s["p10"]), "p90": round(s["p90"]),
            "vendorGold": round(units * vendor) if known else None, "vendor": row.get("vendorPays"),
            "days": round(top["days"], 2), "steps": steps_q, "word": word_of(steps_q), "lowered": why,
            "rests": rests_of(row, inp, ctx), "hold": [hours, cycles], "made": ctx["now"], "scan": ctx["newestId"],
            "worst": round(worst_of(top["units"], top["units"] * vendor, vendor, fee, cycles)), "kelly": None,
            "evidence": dict(zip(("seen", "at"), evidence_of(inp["sales"], top["price"], floor))),
            "model": {"sells": round(top["p"], 3), "one": round(top["one"], 3)}, "tested": tested_of(rated)}
    pick["weak"] = weak_of(pick["gain"], pick["beats"])
    return pick


def vendor_only(key, row, units, why="beats"):
    v = row.get("vendorPays") or 0
    return {"item": key, "way": "vendor", "wayWhy": why, "units": units, "post": 0, "listAt": None, "sellsOne": None,
            "sells": None, "beats": None,
            "gold": units * v, "gain": 0, "p10": units * v, "p90": units * v, "vendorGold": units * v, "vendor": v, "days": 0, "worst": 0,
            "steps": 5, "word": "high", "lowered": [], "rests": None, "hold": None, "made": None, "scan": None, "kelly": None,
            "weak": []}



_left_out = set()


def evaluated(key, make):
    got, fault = tried(make)
    if fault:
        left_out(key, fault)
    return got


def tried(make):
    try:
        return make(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def left_out(key, fault):
    said = (str(key), fault)
    if said not in _left_out:
        _left_out.add(said)
        log_note(f"auction recommendations: {said[0]} left out of the answer, {said[1]}")


CANDIDATES = "picks-candidates.json.gz"
SHAPE = 4
PICKS_MARK = 3
ANSWERS = "picks.json.gz"


def read_kept(folder, name):
    try:
        with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else {}
    except (OSError, EOFError, ValueError):
        return {}


def write_kept(folder, name, doc):
    if not folder or not os.path.isdir(folder):
        return
    try:
        store.write_bytes(os.path.join(folder, name), gzip.compress(jsontext.dumps(doc).encode("utf-8"), 6))
    except OSError:
        log_error(f"keeping the auction house recommendations in {folder}")


def listed_mark(rows):
    asks = sorted((r[3], r[2]) for r in rows if r[3] > 0 and r[2] > 0)
    return hashlib.blake2b(repr(asks).encode("utf-8"), digest_size=12).hexdigest()



POOL_LEAST = 200
BATCH = 40
WEIGH_CTX = ("model", "fit", "under", "rules", "fees", "now", "newest", "survive", "cal", "moved")


def weigh(ctx, item):
    key, row, rows = item
    return tried(lambda: buy_item(key, row, rows, ctx))


def weighing(todo, ctx):
    return workers.mapped(weigh, todo, {k: ctx[k] for k in WEIGH_CTX if k in ctx}, "auction recommendations",
                          POOL_LEAST, BATCH)


_made = {}
_lock = threading.Lock()
_making = {}


def candidates(folder, market, model, listing, ctx, vendor_of):
    with _lock:
        making = _making.setdefault(folder, threading.Lock())
    with making:
        fees = ctx["fees"]
        stamp = repr((SHAPE, market.get("rests"), market.get("newestId"), fees["cut"], fees["deposit"]["share"],
                      fees["deposit"]["least"], fees["hours"], repr(ctx["cal"])))
        got = _made.get(folder)
        if got is None:
            kept_doc = read_kept(folder, CANDIDATES)
            got = (kept_doc.get("stamp"), {k: tuple(v) for k, v in (kept_doc.get("items") or {}).items()})
        kept_ones = got[1] if got[0] == stamp else {}
        made, out, moved = {}, [], got[0] != stamp
        def may_pay(r):
            if (r.get("sales") or {}).get("from") != "prior":
                return True
            price = r.get("price") or {}
            return bool(r.get("vendor")) or (price.get("low") is not None and r.get("cheapest") is not None
                                             and r["cheapest"] <= price["low"])

        rows = [r for r in market["items"] if listing.get(r["item"]) and r.get("sales") and may_pay(r)]
        rests_of = {r["item"]: [listed_mark(listing[r["item"]][1]), vendor_of(r["item"])] for r in rows}
        fresh = {k for k, rests in rests_of.items() if not (kept_ones.get(k) and kept_ones[k][0] == rests)}
        picksreport.note("list", rows=market["items"], listing=listing, fresh=len(fresh))
        todo = [(r["item"], {**r, "vendorPays": r.get("vendorPays") if r.get("vendorPays") is not None else rests_of[r["item"]][1]},
                 listing[r["item"]][1]) for r in rows
                if r["item"] in fresh]
        with weighing(todo, ctx) as weighed:
            for row in rows:
                key, listed = row["item"], listing[row["item"]]
                rests, was, again = rests_of[key], kept_ones.get(key), key in fresh
                if again:
                    cand, fault = next(weighed)
                    if fault:
                        left_out(key, fault)
                    moved = True
                else:
                    cand = was[1]
                picksreport.weighed(key, cand, not again, listed[1])
                made[key] = (rests, cand)
                if cand:
                    out.append(cand)
        _made[folder] = (stamp, made)
        if moved or len(made) != len(kept_ones):
            write_kept(folder, CANDIDATES, {"stamp": stamp, "items": {k: [r, c] for k, (r, c) in made.items()}})
        return out


_answers, _working, _read, _moved = {}, set(), set(), {}
_failed = {}
SETTLE = 2.0


def prune_answers(folder):
    by_prefix = {}
    for (f, w), (_, answer) in _answers.items():
        if f == folder:
            made = answer.get("made") if isinstance(answer, dict) else None
            by_prefix.setdefault(w.rpartition("|")[0], []).append((made if isinstance(made, (int, float)) else 0.0, w))
    for group in by_prefix.values():
        if len(group) > 2:
            group.sort(key=lambda pair: pair[0], reverse=True)
            for _, w in group[2:]:
                _answers.pop((folder, w), None)


def kept(folder, which, rests, make, start=None):
    k, rests = (folder, which), repr(rests)
    with _lock:
        if folder not in _read:
            _read.add(folder)
            for w, v in read_kept(folder, ANSWERS).items():
                if isinstance(v, list) and len(v) == 2:
                    _answers.setdefault((folder, w), (v[0], v[1]))
        got = _answers.get(k)
        if got and got[0] == rests:
            _moved.pop(k, None)
            return got[1], k in _working
        if _failed.get(k) == rests and k not in _working:
            return (got[1] if got else None), False
        was = _moved.get(k)
        if not was or was[0] != rests:
            _moved[k] = was = (rests, time.monotonic())
        if got and got[1] is not None and time.monotonic() - was[1] < SETTLE:
            return got[1], True
        begin = k not in _working
        _working.add(k)

    def work():
        answer = None
        gc.collect(1)
        gc.freeze()
        run = picksreport.begin(folder, which)
        try:
            with picksreport.noting(run):
                answer = make()
        finally:
            with _lock:
                if answer is not None:
                    _answers[k] = (rests, answer)
                    _failed.pop(k, None)
                elif got:
                    _answers[k] = got
                else:
                    _answers.pop(k, None)
                if answer is None:
                    _failed[k] = rests
                _working.discard(k)
                if answer is not None:
                    prune_answers(folder)
                doc = {w: list(v) for (f, w), v in _answers.items() if f == folder}
            run.end()
            if answer is not None:
                write_kept(folder, ANSWERS, doc)
    if begin:
        (start or start_thread)(f"auction recommendations {which}", work)
    return (got[1] if got else None), True


def answer(folder, market, model, listing, scans, held, budget, which, infos, vendor_of, fees, now, tested=None,
           yours=None, paid=None, emptied=None, bound=None, vendor_flips=True, risk=1.0):
    import backtest
    rules = market.get("rules") or {}
    survive = (model.get("survive") or {}).get("house")
    newest = market.get("newest")
    share = math.exp(-survive * max(0.0, now - (newest or now)) / ad.HOUR) if survive is not None else 1.0
    week = sorted(m["started"] for m in scans if m.get("complete") and not m.get("missing") and m["started"] >= now - 7 * ad.DAY)
    ctx = {"model": model, "fit": market.get("sales"), "under": market.get("under"), "moved": market.get("moved"),
           "rules": rules, "fees": fees,
           "now": now, "newest": newest, "newestId": market.get("newestId"), "survive": share,
           "age": max(0.0, now - (newest or now)), "gap": max((b - a for a, b in zip(week, week[1:])), default=0.0),
           "unchecked": [e["effect"] for e in EFFECTS if e["use"] == "unmeasured"], "tested": tested,
           "cal": backtest.maps_of(tested)}
    rows = {r["item"]: r for r in market["items"]}
    cands = candidates(folder, market, model, listing, ctx, vendor_of)
    used = budget.get("here") if which == "here" else budget.get("reach")
    info = lambda key: infos.get(key) or {}

    def pick(cand, k):
        base = rows[cand["key"]]
        row = {**base, "vendorPays": base.get("vendorPays") if base.get("vendorPays") is not None else vendor_of(cand["key"])}
        return evaluated(cand["key"], lambda: buy_pick(cand, row, listing[cand["key"]][1], info(cand["key"]), ctx, k,
                                                       vendor_flips))

    def sold(key, where):
        units = sum(where.values())
        base = rows.get(key) or {"item": key}
        row = {**base, "vendorPays": base.get("vendorPays") if base.get("vendorPays") is not None else vendor_of(key)}
        asks, ahead_too = (listing.get(key) or (None, []))[1], (yours or {}).get(key, ())
        last = not asks and key in (emptied or {})
        if last:
            asks, ahead_too = emptied[key], ()
        got = sell_item(key, row, asks, units, ctx, ahead_too) if rows.get(key) else None
        if got and last and got["way"] == "house":
            got["lastScan"] = True
        if got is None and row["vendorPays"]:
            got = vendor_only(key, row, units, "noprice")
        if got:
            cost, covered = (paid or {}).get(key) or (None, 0)
            got.update(name=info(key).get("n"), q=info(key).get("q"), icon=info(key).get("icon"), sub=row.get("sub"), on=where,
                       paid=cost, paidUnits=covered)
        return got

    def soulbound(key, where):
        row = {"item": key, "vendorPays": vendor_of(key)}
        if not row["vendorPays"]:
            return None
        got = vendor_only(key, row, sum(where.values()))
        got.update(name=info(key).get("n"), q=info(key).get("q"), icon=info(key).get("icon"),
                   sub=(rows.get(key) or {}).get("sub"), on=where, bound=True, paid=None, paidUnits=0)
        return got

    def weighed(key, where, way):
        got = evaluated(key, lambda: way(key, where))
        picksreport.note("sell", i=key, units=sum(where.values()), way=got and got["way"], gold=got and got["gold"], post=got and got["post"])
        return got
    buy = fill(cands, used or 0, pick, vendor_flips, risk)
    picksreport.note("held", held=[*held, *(bound or {})])
    sell = [got for got in (weighed(key, where, sold) for key, where in held.items()) if got]
    sell += [got for got in (weighed(key, where, soulbound) for key, where in (bound or {}).items()) if got]
    sell.sort(key=lambda p: -(p["gold"] or 0))
    picksreport.note("sold", order=[p["item"] for p in sell])
    return {"made": now, "newest": newest, "newestId": market.get("newestId"), "rules": rules, "fees": fees,
            "hold": list(hold_of(fees)), "budget": {**budget, "used": used, "which": which, "reserve": RESERVE},
            "population": population(scans), "openings": openings(now)[:1], "effects": EFFECTS,
            "scansApart": ((tested or {}).get("sells") or {}).get("apart"),
            "buy": buy, "sell": sell, "candidates": len(cands)}


EFFECTS = [{"effect": "patch", "use": "price"}, {"effect": "state", "use": "price"}, {"effect": "week", "use": "unmeasured"},
           {"effect": "launch", "use": "out"}, {"effect": "population", "use": "out"},
           {"effect": "events", "use": "unmeasured"}]



def population(scans):
    pts = [(m["started"] / ad.DAY, math.log(m["auctions"])) for m in scans
           if m.get("complete") and not m.get("missing") and m.get("auctions")]
    n = len(pts)
    if n < 3:
        return None
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    res = sum((y - my - b * (x - mx)) ** 2 for x, y in pts) / (n - 2) if n > 2 else 0.0
    half = t90(n - 2) * math.sqrt(res / sxx)
    state = "growing" if b - half > 0 else "falling" if b + half < 0 else "stable"
    return {"trend": round(math.exp(b) - 1, 4), "low": round(math.exp(b - half) - 1, 4), "high": round(math.exp(b + half) - 1, 4),
            "state": state, "scans": n}


def t90(df):
    table = [6.314, 2.920, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833, 1.812, 1.796, 1.782, 1.771, 1.761, 1.753,
             1.746, 1.740, 1.734, 1.729, 1.725, 1.721, 1.717, 1.714, 1.711, 1.708, 1.706, 1.703, 1.701, 1.699, 1.697]
    return table[df - 1] if 1 <= df <= len(table) else ad.Z90


def openings(now, path=None):
    import store
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dungeons.json")
    d = store.load_json(path, {}) or {}
    rows = list(d.get("dungeons") or []) + list(d.get("coming") or [])
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    out = {(r.get("opens"), r.get("kind")): r for r in rows if r.get("opens") and r["opens"] > today}
    return [{"opens": o, "kind": k, "names": sorted(r.get("name") for r in rows if r.get("opens") == o and r.get("kind") == k)}
            for o, k in sorted(out)]
