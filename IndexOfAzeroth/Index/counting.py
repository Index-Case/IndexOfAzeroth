# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import math
import time

import auctiondays as ad
import auctionmarket as am
from auction import in_house, read_whole
from dayrecord import day_of


def by_record(meta, record, chars, house, days):
    t = meta.get("ended") or meta.get("started")
    key = record.who_played(t) if t else None
    c = chars.get(key) if key else None
    if not c or not c.get("name") or (c.get("realm") and house and not in_house(c["realm"], house.partition("|")[2], house)):
        return None
    if key not in days:
        days[key] = {d["day"] for d in record.days(key)}
    return {"name": c["name"], "key": key} if day_of(t) in days[key] else None


def arrived(meta):
    total = meta.get("total") or 0
    if not (read_whole(meta) and meta.get("missing") and total):
        return None
    return max(1, min(99, math.floor(100 * meta.get("auctions", 0) / total)))


def scan_row(meta, record, chars, house, days):
    by, how = meta.get("by"), meta.get("byFrom")
    if not by:
        told = by_record(meta, record, chars, house, days)
        by, how = (told["name"], "record") if told else (None, None)
    return {"t": meta["started"], "ended": meta.get("ended"), "state": meta.get("state"),
            "whole": bool(meta.get("complete") and not meta.get("missing")), "auctions": meta.get("auctions", 0),
            "arrived": arrived(meta),
            "items": meta.get("items"), "counted": "items" in meta, "seconds": meta.get("seconds"), "by": by,
            "from": "scan" if how == "scan" else ("record" if by else None)}


def budget(purses, current, house):
    known = {k: p for k, p in purses.items() if p.get("money") is not None}
    reach = sum(p["money"] for p in known.values() if in_house(p.get("realm"), p.get("faction"), house))
    me = purses.get(current) or max(purses.values(), key=lambda p: p.get("seen") or 0, default={})
    return {"here": me.get("money"), "all": sum(p["money"] for p in known.values()),
            "reach": reach, "unknown": len(purses) - len(known)}


def answer(hub, house=None, redo=False):
    got = hub.auction.scans_of(house)
    chars, days = (hub.characters.records() if got["scans"] else {}), {}
    return {"house": got["house"], "name": got["name"], "houses": got["houses"], "now": time.time(), "playing": hub.characters.current,
            "budget": budget(hub.characters.purses(), hub.characters.current, got["house"]),
            "scans": [scan_row(m, hub.dayrecord, chars, got["house"], days) for m in got["scans"]],
            "counting": bool(got["scans"]) and hub.auction.count_house(got["house"]),
            "summarising": bool(got["scans"]) and hub.auction.summarise(got["house"], redo),
            "stamp": stamp_of(hub, got["house"], got["scans"])}


def stamp_of(hub, house, scans):
    import gamedata
    from goods import PLACES, house_chars
    got = hub.auction.house_of(house)
    market = am.load(got["folder"]) if got["folder"] else None
    snap = hub.characters.snapshot()
    held = max([(c.get(where) or {}).get("at") or 0 for c in house_chars(snap["chars"], house or "").values()
                for where in PLACES] + [(snap.get("warband") or {}).get("at") or 0])
    last = scans[-1] if scans else {}
    seen = gamedata.seen_prices.version if gamedata.seen_prices else 0
    return ".".join(str(v) for v in (hub.auction.version, len(scans), last.get("id"), last.get("auctions"),
                                     (market or {}).get("rests"), hub.ledger.version, seen, held))



CURVE_MOST = 400
BAND_STEP = 2 * 3600
BAND_MOST = 24
STEADY = 3


def steps_of(price, low, high, used, measured=True):
    width = (high - low) / price
    steps = 5 if width < 0.25 else 4 if width < 0.5 else 3 if width < 1.0 else 2 if width < 1.5 else 1 if width < 3 else 0
    if used < STEADY or high <= low or not low <= price <= high:
        return min(steps, 1)
    return steps if measured else min(steps, 3)


def band_points(states, noises, q, breaks, now, model, kind=None):
    out, prev, prev_noise = [], None, None
    for s, noise in zip(states, noises):
        if s["level"] is None:
            continue
        if prev is not None:
            out.extend(gap_points(prev, s["t"], q, breaks, s["before"], model, prev_noise, kind))
        price, lo, hi, _ = ad.price_range(model, s["level"], s["P"], noise, 0.0, kind)
        out.append([s["t"], round(price, 2), round(lo, 2), round(hi, 2)])
        prev, prev_noise = (s["t"], s["level"], s["P"]), noise
    if prev is not None and now > prev[0]:
        out.extend(gap_points(prev, now, q, breaks, ad.at_time(prev, now, q, breaks)[1], model, prev_noise, kind))
    return out


def gap_points(state, to, q, breaks, end_p, model, noise, kind=None):
    t0, mu, _ = state
    n = max(1, min(BAND_MOST, math.ceil((to - t0) / BAND_STEP)))
    out = []
    for i in range(1, n + 1):
        t = t0 + (to - t0) * i / n
        p = end_p if i == n else ad.at_time(state, t, q, breaks)[1]
        price, lo, hi, _ = ad.price_range(model, mu, p, noise, (t - t0) / ad.HOUR, kind)
        out.append([round(t), round(price, 2), round(lo, 2), round(hi, 2)])
    return out


def noises_of(points, floor):
    out, last = [], floor
    for _, y, noise in points:
        if y is not None:
            last = noise
        out.append(last)
    return out


def thinned(rows, most=CURVE_MOST):
    if len(rows) <= most:
        return rows
    every = len(rows) / most
    return [rows[int(i * every)] for i in range(most - 1)] + [rows[-1]]


def depth_answer(listed, rows, model, now):
    if not listed or not listed[1]:
        return None
    t, auctions = listed
    seen = [r["reading"][ad.R_SURVIVE] for r in rows if r["reading"][ad.R_SURVIVE]]
    own = ad.fit_survival(seen) if sum(s[0] for s in seen) >= ad.SURVIVE_LEAST else None
    rate = own if own is not None else (model.get("survive") or {}).get("house")
    share = math.exp(-rate * max(0.0, now - t) / ad.HOUR) if rate is not None else None
    walked = ad.walk(auctions)
    later = ad.walk(auctions, share) if share is not None else None
    curve = [[round(w[2], 2), round(w[3] / w[2], 2), round(w[0], 2)] + ([round(e[2], 2), round(e[3] / e[2], 2)] if later else [])
             for w, e in zip(walked, later or walked)]
    cum, steps = 0, []
    for unit, units, n, far in ad.ladder(auctions):
        cum += unit * units
        steps.append([round(unit, 2), units, n, round(cum), far])
    return {"t": t, "steps": steps, "curve": thinned(curve), "units": sum(s[1] for s in steps), "farHigh": ad.FAR_HIGH,
            "survive": None if rate is None else {"rate": rate, "own": own is not None, "share": share}}


def item(hub, house=None, key=None, since=0):
    import gamedata
    from auction import price_key
    ah, now = hub.auction, time.time()
    key = price_key(key) or ""
    ident = key.split(":")[0]
    got = ah.item_of(key, house)
    info = (ah.infos([key]) if key else {}).get(key) or {}
    out = {"house": got["house"], "item": key, "name": info.get("n"), "q": info.get("q"), "icon": info.get("icon"),
           "pooled": bool(info.get("pooled")),
           "vendor": gamedata.item_sell_price(key) if ident.isdigit() else None, "now": now, "summarising": got["summarising"], "seen": False, "scans": [],
           "band": [], "price": None, "support": None, "state": None, "volatility": [], "changes": [], "resets": [],
           "breaks": [], "depth": None, "cheapest": None, "sales": None}
    if not got["folder"] or not ident.isdigit():
        return out
    model = ad.load_model(got["folder"])
    q, floor = ad.noise_of(model, key)
    breaks = sorted((model.get("breaks") or {}).get(ident, []))
    reach = min(since, now - ad.SUPPORT_DAYS * ad.DAY) if since else 0
    rows, start, _ = ad.series(got["folder"], key, reach, got.get("pool"))
    pts = ad.points([(r["t"], r["reading"]) for r in rows], floor)
    states, last = ad.run_filter(pts, q, breaks, start)
    noises, kind = noises_of(pts, floor), ad.kind_of(key)
    priced = [(p[0], p[1], p[2]) for p in pts if p[1] is not None]
    marks = {priced[i][0] for i in ad.changes(priced, q, breaks)}
    chars, days = hub.characters.records(), {}
    for r, s, noise in zip(rows, states, noises):
        how = ("scan" if r["byFrom"] == "scan" else "record") if r["by"] else None
        if not r["by"]:
            told = by_record({"started": r["t"]}, hub.dayrecord, chars, got["house"], days)
            r["by"], how = (told["name"], "record") if told else (None, None)
        g = r["reading"]
        lo = hi = level = None
        if s["level"] is not None:
            level, lo, hi, _ = ad.price_range(model, s["level"], s["P"], noise, 0.0, kind)
        reset = ad.is_reset(g, s["z"])
        out["scans"].append({"t": r["t"], "by": r["by"], "from": how, "price": g[ad.R_PRICE], "low": g[ad.R_LOW], "p10": g[ad.R_P10],
                             "p50": g[ad.R_P50], "p90": g[ad.R_P90], "units": g[ad.R_UNITS], "auctions": g[ad.R_AUCTIONS],
                             "bait": g[ad.R_BAIT], "level": rounded(level), "lo": rounded(lo), "hi": rounded(hi),
                             "change": r["t"] in marks, "reset": reset})
    out["band"] = band_points(states, noises, q, breaks, now, model, kind)
    out["changes"] = sorted(marks)
    out["resets"] = [s["t"] for s in out["scans"] if s["reset"]]
    out["breaks"] = [b for b in breaks if b >= (rows[0]["t"] if rows else now)]
    out["depth"] = depth_answer(got["listed"], rows, model, now)
    out["seen"] = bool(rows or out["depth"] or start)
    if out["depth"]:
        newest = rows[-1]["reading"] if rows and rows[-1]["t"] == out["depth"]["t"] else None
        out["cheapest"] = {"t": out["depth"]["t"], "unit": out["depth"]["steps"][0][0], "bait": bool(newest and newest[ad.R_BAIT])}
    if last:
        mu, p = ad.at_time(last, now, q, breaks)
        price, lo, hi, measured = ad.price_range(model, mu, p, noises[-1] if noises else floor, (now - last[0]) / ad.HOUR, kind)
        used = [s for s in out["scans"] if s["price"] and s["t"] >= (since or 0)]
        gaps = [b["t"] - a["t"] for a, b in zip(used, used[1:])]
        out["price"] = {"price": round(price, 2), "low": round(lo, 2), "high": round(hi, 2), "newest": last[0],
                        "scans": len(used), "gap": max(gaps) if gaps else None, "measured": measured,
                        "steps": steps_of(price, lo, hi, len(used), measured),
                        "own": key in (model.get("q") or {}).get("items", {})}
        out["state"] = state_answer(out["scans"], price, now, lo, hi)
        if out["state"]["state"]:
            out["state"].update(uncertain_state(out["state"], state_holds(got["folder"])))
    recent = [s["price"] for s in out["scans"] if s["price"] and s["t"] >= now - ad.SUPPORT_DAYS * ad.DAY]
    if len(recent) >= 5:
        out["support"] = {"p10": round(ad.quantile([(v, 1) for v in sorted(recent)], 0.1), 2),
                          "p90": round(ad.quantile([(v, 1) for v in sorted(recent)], 0.9), 2), "scans": len(recent)}
    out["volatility"] = [[t, round(v, 4)] for t, v in ad.volatility([(p[0], p[1]) for p in priced])]
    house_m = am.load(got["folder"]) or {}
    import gamedata
    prior = (house_m.get("priors") or {}).get(am.subclass_of(gamedata.item_classes(), key), am.PRIOR_LEAST)
    shown = [(r, s, o) for r, s, o in zip(rows, states, out["scans"]) if r["t"] >= (since or 0)]
    out["sales"] = am.item_sales([r for r, _, _ in shown], [s for _, s, _ in shown], prior, house_m.get("pairs") or 0,
                                 now, [o for _, _, o in shown], house_m.get("sales"), kind)
    return out


MARKET_COLUMNS = ["item", "name", "q", "icon", "sub", "price", "profit", "margin", "low", "high", "steps", "scans",
                  "state", "change", "listed", "average", "auctions", "cheapest", "wall", "seen", "bait", "reset",
                  "vendor", "day", "dayLow", "dayHigh", "daySteps", "dayCraft", "from", "pairs", "short", "resetUnits",
                  "uncertain"]
HOLD_LEAST = 0.5


def state_holds(folder):
    import backtest
    return (backtest.load(folder) or {}).get("states") or {} if folder else {}


def uncertain_state(state, holds):
    import backtest
    ranged = "sure" in state
    got = holds.get(f'{state["state"]} sure' if ranged else state["state"]) or {}
    n, held = got.get("n") or 0, got.get("same")
    return {"uncertain": (ranged and state["sure"] is not True) or n < backtest.N_LEAST or held is None or held < HOLD_LEAST,
            "held": held if n >= backtest.N_LEAST else None, "n": n}


def craft_profits(rows, cut, recipes):
    prices, days, known = {}, {}, {r["item"] for r in rows}
    for r in rows:
        prices[r["item"]] = (r.get("price") or {}).get("price")
        days[r["item"]] = (r.get("sales") or {}).get("day")
    base_known = {k.split(":")[0] for k in known if ":" not in k or k.endswith(":pooled")}

    def price_of(item):
        for key in (str(item), f"{item}:pooled"):
            if prices.get(key) is not None:
                return prices[key]
        return None
    best, left = {}, 0
    for rec in recipes.values():
        makes = rec.get("makes") or ()
        if not makes:
            continue
        made, count = int(makes[0]), int(makes[1]) if len(makes) > 1 else 1
        if str(made) not in base_known:
            continue
        unit = price_of(made)
        if unit is None:
            left += 1
            continue
        cost, priced = 0.0, True
        for item, n in rec.get("reagents") or ():
            reagent = price_of(item)
            if reagent is None:
                priced = False
                break
            cost += reagent * int(n)
        if not priced:
            left += 1
            continue
        profit = round(unit * count * (1 - cut) - cost)
        margin = round(profit / cost, 4) if cost else None
        if made not in best or profit > best[made][0]:
            best[made] = (profit, margin, count)
    out, no_rate = {}, 0
    for item, (profit, margin, count) in best.items():
        for key in (str(item), f"{item}:pooled"):
            if key in known:
                day = days[key]
                out[key] = [profit, margin, None if day is None else round(day / count, 3)]
                if day is None:
                    no_rate += 1
    return out, left, no_rate


def market_row(r, info, holds, crafts=None):
    p, st, s = r.get("price") or {}, r.get("state") or {}, r.get("sales") or {}
    profit, margin, day_craft = (crafts or {}).get(r["item"]) or (None, None, None)
    return [r["item"], info.get("n"), info.get("q"), info.get("icon"), r["sub"], p.get("price"), profit, margin,
            p.get("low"), p.get("high"), p.get("steps"), r["scans"], st.get("state"), st.get("change"), r["listed"],
            r["average"], r["auctions"], r["cheapest"], r["wall"], r["seen"], r["bait"], r["reset"], r["vendor"],
            s.get("day"), s.get("low"), s.get("high"), s.get("steps"), day_craft, s.get("from"), s.get("pairs"),
            s.get("short"), s.get("reset"),
            uncertain_state(st, holds)["uncertain"] if st.get("state") else None]


def market(hub, house=None):
    import backtest
    import camping
    import gamedata
    got = hub.auction.house_of(house)
    out = {"house": got["house"], "now": time.time(), "summarising": got["summarising"], "made": None,
           "columns": MARKET_COLUMNS, "items": [], "crafts": {"left": 0, "leftSales": 0}}
    m = am.load(got["folder"]) if got["folder"] else None
    if not m:
        return out
    infos = hub.auction.infos(sorted({r["item"] for r in m["items"]}))
    _, classes, subs, _ = gamedata.item_classes()
    used = {r["sub"] for r in m["items"]}
    out.update({k: m.get(k) for k in ("made", "newest", "scans", "pairs", "short", "days", "rules")})
    out["fees"] = house_fees(hub, got["house"])
    crafts, left, left_sales = craft_profits(m["items"], out["fees"]["cut"], camping.load().recipes)
    out["crafts"] = {"left": left, "leftSales": left_sales}
    holds = state_holds(got["folder"])
    out.update(classes={c: classes[c] for c in {s.split(".")[0] for s in used if s} if c in classes},
               subs={s: subs[s] for s in used if s in subs}, groups=market_groups(m["items"]),
               holds={k: v for k, v in holds.items() if (v.get("n") or 0) >= backtest.N_LEAST},
               items=[market_row(r, infos.get(r["item"]) or {}, holds, crafts) for r in m["items"]])
    for g in out["groups"].values():
        g["uncertain"] = uncertain_state(g, holds)["uncertain"] if g.get("state") else None
    read = hub.trades.view(got["house"])["rules"] if got["house"] else {}
    dep = read.get("deposit") or {}
    names = hub.auction.infos(sorted({d["item"] for d in dep.values() if d.get("item")})) if dep else {}
    out["rules"] = {**(out.get("rules") or {}), "cut": read.get("cut"), "least": read.get("least"),
                    "deposit": {k: {**d, "name": (names.get(str(d.get("item"))) or {}).get("n")} for k, d in dep.items()} or None}
    return out



def record(hub, house=None, which="all"):
    import gamedata
    import goods
    import trades
    got = hub.auction.house_of(house)
    v = hub.trades.view(got["house"]) if got["house"] else None
    out = {"house": got["house"], "now": time.time(), "made": False, "auctions": [], "notices": [], "sales": [], "bids": [],
           "items": [], "rules": {}, "theta": {}, "characters": [], "infos": {}}
    if not v:
        return out
    only = goods.shown(hub, which)
    if only is not None:
        v = {**v, **{k: [r for r in v[k] if r.get("char") in only] for k in ("auctions", "notices", "sales", "bids")},
             "characters": [c for c in v["characters"] if c["key"] in only]}
        v["items"] = trades.summaries(v["auctions"])
    out.update({k: v[k] for k in ("auctions", "notices", "sales", "bids", "items", "rules", "theta", "characters")})
    out["made"] = bool(v["auctions"] or v["notices"] or v["sales"])
    named = gamedata.item_ids({r.get("name") for r in v["sales"] + v["notices"] + v["items"] if r.get("name")})
    out["sales"] = [{**r, "item": named.get(r.get("name"))} for r in v["sales"]]
    out["notices"] = [{**n, "item": named.get(n.get("name"))} for n in v["notices"]]
    out["items"] = [{**s, "item": s.get("item") or named.get(s.get("name"))} for s in v["items"]]
    ids = {r.get("item") for r in v["auctions"] + v["bids"] + out["sales"] + out["notices"] + out["items"]} - {None}
    out["infos"] = hub.auction.infos(sorted(ids))
    return out


def market_groups(rows):
    sums = {}
    for r in rows:
        sales, price, st = r.get("sales") or {}, (r.get("price") or {}).get("price"), r.get("state") or {}
        gold = sales["day"] * price if sales.get("day") is not None and price else 0.0
        for key in {r["sub"].split(".")[0], r["sub"]}:
            s = sums.setdefault(key, [0.0, 0.0, 0.0])
            s[0] += gold
            if st.get("change") is not None:
                s[1] += gold * st["change"]
                s[2] += gold
    out = {}
    for key, (gold, moved, weight) in sums.items():
        change = moved / weight if weight else None
        out[key] = {"gold": round(gold), "change": None if change is None else round(change, 4),
                    "state": None if change is None else ad.state_of(change)}
    return out


def odds(hub, house=None):
    import backtest
    got = hub.auction.house_of(house)
    out = {"house": got["house"], "now": time.time(), "summarising": got["summarising"], "made": None,
           "record": backtest.score([])}
    kept = backtest.load(got["folder"]) if got["folder"] else None
    if kept:
        out.update({k: kept.get(k) for k in ("made", "newest", "density", "price", "sales", "states", "picks")})
    h = hub.auction.houses.get(got["house"]) if got["folder"] else None
    m = am.load(got["folder"]) if got["folder"] else None
    if h and m:
        record, working = record_odds(h, hub.trades.view(got["house"]), m)
        if record:
            out["record"] = record["score"]
        out["summarising"] = out["summarising"] or working
    return out


_record = {}
_record_working = set()


def record_odds(house, view, market, start=None):
    import backtest
    from serverlog import start_thread
    ends = tuple(sorted((a["key"], a.get("outcome"), a.get("sure")) for a in view["auctions"]
                        if a.get("outcome") in backtest.RECORD_ENDS))
    stamp = (market.get("rests"), ends)
    got = _record.get(house.folder)
    if got and got[0] == stamp:
        return got[1], False
    if house.folder not in _record_working:
        _record_working.add(house.folder)

        def work():
            try:
                _record[house.folder] = (stamp, record_answer(house, view, market, ends))
            finally:
                _record_working.discard(house.folder)
        (start or start_thread)("auction record odds", work)
    got = _record.get(house.folder)
    return (got[1] if got else None), house.folder in _record_working


def record_answer(house, view, market, ends):
    import auction
    import auctionpicks
    import backtest
    import gamedata
    ladders = {}

    def ladder_at(sid, key):
        if sid not in ladders:
            read = ad.scan_rows(house, sid)
            by = collections.defaultdict(list)
            for r in (read or ([], None))[0]:
                by[auction.row_key(r[0], r[1])].append(r)
            ladders.clear()
            ladders[sid] = None if read is None else {k: auctionpicks.ladder_of(v) for k, v in by.items()}
        got = ladders[sid]
        return None if got is None else got.get(key, [])
    checks = []
    if ends:
        history = backtest.History(ad.day_files(house.folder), house.pool)
        checks = backtest.record_checks(history, view["auctions"], ladder_at, (view.get("rules") or {}).get("durations"),
                                        market.get("rules"), gamedata.item_classes())
    return {"checks": checks, "score": backtest.score(checks)}


def rounded(v):
    return None if v is None else round(v, 2)


def state_answer(scans, price, now, low=None, high=None):
    near = [s for s in scans if s["level"] is not None and s["t"] >= now - ad.LEVEL_DAYS * ad.DAY and not s.get("reset")]
    by_day = collections.defaultdict(list)
    for s in near:
        by_day[day_of(s["t"])].append(s["level"])
    days = len(by_day)
    if days < ad.LEVEL_DAYS_LEAST:
        return {"state": None, "days": days}
    level = sum(sum(v) / len(v) for v in by_day.values()) / days
    change = price / level - 1
    state = ad.state_of(change)
    sure = None if low is None or high is None else ad.state_of(low / level - 1) == state == ad.state_of(high / level - 1)
    return {"state": state, "change": round(change, 4), "level": round(level, 2), "days": days, "sure": sure}


def house_fees(hub, house):
    return am.fees_of(house.partition("|")[2], hub.trades.view(house)["rules"])



def picks(hub, house=None, which="here", vendor_flips=False, risk=1.0):
    import auctionpicks
    import backtest
    import gamedata
    import goods
    import trades
    got = hub.auction.listing_of(house)
    now = time.time()
    out = {"house": got["house"], "now": now, "summarising": got["summarising"], "made": None}
    m = am.load(got["folder"]) if got["folder"] else None
    if not m or m.get("mark") != am.MARK:
        return out
    snap = hub.characters.snapshot()
    acts = goods.acted(hub, got, snap)
    places = goods.sell_places(snap, got["house"], trades.to_mail(acts), goods.shown(hub, which))
    held, bound = (goods.units_of(side) for side in places)
    paid = trades.paid_for(hub.trades.view(got["house"]), acts, {k: sum(v.values()) for k, v in held.items()})
    purses = hub.characters.purses()
    money, fees = budget(purses, hub.characters.current, got["house"]), house_fees(hub, got["house"])
    tested = backtest.load(got["folder"]) or {}
    rests = (auctionpicks.PICKS_MARK, m.get("rests"), which, vendor_flips, repr(risk), repr(money), repr(fees),
             tuple(sorted((k, tuple(sorted(v.items()))) for k, v in held.items())),
             tuple(sorted((k, tuple(sorted(v.items()))) for k, v in bound.items())), tested.get("newest"),
             repr(tested.get("marks")), gamedata.seen_prices.version if gamedata.seen_prices else 0, acts["mark"],
             repr(sorted(paid.items())))

    def make():
        keys = set(held) | set(bound) | {r["item"] for r in m["items"]}
        return auctionpicks.answer(got["folder"], m, ad.load_model(got["folder"]), acts["listing"], got["scans"], held, money,
                                   which, hub.auction.infos(sorted(keys)), gamedata.item_sell_price, fees, time.time(),
                                   tested.get("picks"), acts["yours"], paid, acts["emptied"], bound, vendor_flips, risk)
    answer, working = auctionpicks.kept(got["folder"], f"{which}|{int(vendor_flips)}|{risk:g}", rests, make)
    if answer:
        out.update(answer)
    out["reposted"] = trades.reposted(hub.trades.view(got["house"]))
    out["places"] = {"held": places[0], "bound": places[1], "seen": goods.place_times(snap, got["house"], goods.shown(hub, which))}
    out.update(summarising=got["summarising"] or working, playing=(purses.get(hub.characters.current) or {}).get("name"))
    return out
