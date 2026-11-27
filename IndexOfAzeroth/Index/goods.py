# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import time

import auctiondays as ad
import auctionmarket as am
from auction import in_house

SOLD, COMMODITY, ITEM, BIDDER = 1, 2, 4, 8
BAND_UNKNOWN = 255
PLACES = ("bags", "bank", "mail", "auctions")


def owned_record(pages, old):
    at = pages[0]["at"]
    listed = [a for p in pages for a in p["auctions"]]
    was = (old or {}).get("seen") or {}
    seen = {str(a["id"]): was.get(str(a["id"]), at) for a in listed}
    return {"at": at, "side": pages[0]["side"], "list": listed, "seen": seen}



def unit_price(a, rows=()):
    if not a["buy"]:
        return None
    if a["flags"] & COMMODITY:
        return a["buy"]
    if a["flags"] & ITEM or a["q"] == 1:
        return a["buy"] / a["q"]
    for r in rows:
        if r[2] == a["q"] and r[3] == a["buy"]:
            return a["buy"] / a["q"]
        if r[2] == a["q"] and r[3] == a["buy"] * a["q"]:
            return a["buy"]
    return None


def ends_of(a, at):
    return at + a["left"] if a["left"] else None


def matches_of(rows, mine, t):
    out, taken = {}, set()
    for a, unit, at in mine:
        ends = ends_of(a, at)
        if unit is None or (ends is not None and ends < t):
            continue
        whole = round(unit * a["q"])
        for i, r in enumerate(rows):
            if i not in taken and r[2] == a["q"] and r[3] > 0 and abs(r[3] - whole) <= 1:
                out[a["id"]] = i
                taken.add(i)
                break
    return out


def ahead(rows, unit, skip, newest_first):
    n = 0
    for i, r in enumerate(rows):
        if i in skip or r[3] <= 0 or r[2] <= 0:
            continue
        u = r[3] / r[2]
        if u < unit - 1e-9 or (not newest_first and u <= unit + 1e-9):
            n += r[2]
    return n


def cheapest_other(rows, skip):
    prices = [r[3] / r[2] for i, r in enumerate(rows) if i not in skip and r[3] > 0 and r[2] > 0]
    return min(prices) if prices else None


def shown(hub, which):
    current = hub.characters.current
    return {current} if which == "here" and current else None


def house_chars(chars, key, only=None):
    return {k: c for k, c in chars.items()
            if in_house(c.get("realm"), c.get("faction"), key) and (only is None or k in only)}


def house_parts(hub, house):
    got = hub.auction.house_of(house)
    key = got["house"] or ""
    return key, key.partition("|")[2], am.load(got["folder"]) if got["folder"] else None


def auctions(hub, house=None, now=None, which="all"):
    import trades
    now = now or time.time()
    key, faction, market = house_parts(hub, house)
    style = ((market or {}).get("rules") or {}).get("style")
    newest_first = style == "commodity"
    mine, characters = [], []
    for c in house_chars(hub.characters.snapshot()["chars"], key, shown(hub, which)).values():
        rec = c.get("auctions")
        if not rec or rec.get("side") != faction:
            continue
        characters.append({"name": c.get("name"), "at": rec["at"]})
        for a in rec["list"]:
            mine.append((c.get("name"), a, rec["at"], rec["seen"].get(str(a["id"]), rec["at"])))
    out = {"house": key, "now": now, "style": style, "listed": None, "characters": characters, "auctions": [],
           "ladders": {}}
    if not mine:
        return out
    keys = sorted({a["key"] for _, a, _, _ in mine})
    view = hub.trades.view(key)
    costs = trades.reposted(view)
    deposits = {r["auction"]: r.get("paid") if r.get("paid") is not None else r.get("deposit")
                for r in view["auctions"] if r.get("auction")}
    listed = {k: hub.auction.item_of(k, key)["listed"] for k in keys}
    infos = hub.auction.infos(keys)
    out["listed"] = max((v[0] for v in listed.values() if v), default=None)
    units = {a["id"]: unit_price(a, (listed[a["key"]] or (0, []))[1]) for _, a, _, _ in mine}
    by_key = {}
    for who, a, at, seen in mine:
        by_key.setdefault(a["key"], []).append((who, a, at, seen))
    since = min(seen for _, _, _, seen in mine)
    history = hub.auction.whole_listings(key, since, keys) if since < now else []
    for item, group in by_key.items():
        t, rows = listed[item] or (None, [])
        matched = matches_of(rows, [(a, units[a["id"]], at) for _, a, at, _ in group], t or now)
        other = cheapest_other(rows, set(matched.values()))
        out["ladders"][item] = ladder_of(rows, [(a, units[a["id"]]) for _, a, _, _ in group])
        for who, a, at, seen in group:
            u, info = units[a["id"]], infos.get(a["key"]) or {}
            row = {"id": a["id"], "who": who, "item": a["item"], "key": a["key"], "name": info.get("n"), "q": info.get("q"),
                   "icon": info.get("icon"), "units": a["q"], "unit": u, "bid": a["bid"] or None, "sold": bool(a["flags"] & SOLD),
                   "band": None if a["band"] == BAND_UNKNOWN else a["band"], "ends": ends_of(a, at), "at": at, "seen": seen,
                   "scan": t, "other": other, "under": None, "ahead": None, "match": None, "history": [],
                   "reposts": (costs.get(str(a["key"])) or {}).get("reposts", 0),
                   "lost": (costs.get(str(a["key"])) or {}).get("lost", 0), "deposit": deposits.get(a["id"])}
            if u is not None and t is not None and not row["sold"]:
                found = matched.get(a["id"])
                row["ahead"] = ahead(rows, u, set() if found is None else {found}, newest_first)
                row["under"] = round(u - other, 2) if other is not None and other < u else 0
                row["match"] = other
                for st, items in history:
                    if st >= seen:
                        hrows = items.get(item) or []
                        row["history"].append([st, ahead(hrows, u, set(matches_of(hrows, [(a, u, at)], st).values()), newest_first)])
            out["auctions"].append(row)
    return out


def ladder_of(rows, yours):
    marks = {}
    for a, u in yours:
        if u is not None and not a["flags"] & SOLD:
            marks[round(u, 4)] = marks.get(round(u, 4), 0) + a["q"]
    steps = [[s[0], s[1], s[2], marks.pop(s[0], 0)] for s in ad.ladder(rows)]
    return sorted(steps + [[u, 0, 0, n] for u, n in marks.items()], key=lambda s: s[0])



def counts_of(snap):
    if not snap:
        return {}
    out = {str(k): n for k, n in (snap.get("items") or {}).items()}
    for k, n in (snap.get("sfx") or {}).items():
        base = str(k).split(":")[0]
        out[base] = out.get(base, 0) - n
        out[str(k)] = out.get(str(k), 0) + n
    return {k: n for k, n in out.items() if n > 0}


def on_auction(rec, faction):
    out = {}
    if rec and rec.get("side") == faction:
        for a in rec["list"]:
            if not a["flags"] & SOLD:
                out[a["key"]] = out.get(a["key"], 0) + a["q"]
    return out


def value_of(key, prices, vendor, bound=False):
    r = None if bound else prices.get(key)
    p = (r or {}).get("price")
    if p:
        return {"unit": p["price"], "low": p["low"], "high": p["high"], "from": "market", "steps": p["steps"],
                "scans": r.get("scans"), "seen": r.get("seen")}
    v = vendor(key)
    if v:
        return {"unit": v, "low": v, "high": v, "from": "vendor", "steps": None, "scans": None, "seen": None}
    return {"unit": None, "low": None, "high": None, "from": None if v == 0 else "unknown", "steps": None, "scans": None,
            "seen": None}


def acted(hub, got, snap):
    import trades
    if not got.get("house"):
        return {"listing": got.get("listing") or {}, "yours": {}, "emptied": {}, "bought": [], "cancelled": [],
                "mark": (0, None)}
    faction = got["house"].partition("|")[2]
    owned = [(a, rec["at"], rec["seen"].get(str(a["id"]), rec["at"]))
             for c in house_chars(snap["chars"], got["house"]).values()
             for rec in [c.get("auctions")] if rec and rec.get("side") == faction for a in rec["list"]]
    suffixed = (got.get("pool") or (frozenset(), None))[0]
    return trades.listing_now(hub.trades.view(got["house"]), got.get("listing") or {}, suffixed, owned)


def split_bound(rec, items):
    told = (rec or {}).get("bound") or {}
    out = []
    for k, n in items.items():
        b = min(n, told.get(k, 0))
        out.extend((k, m, flag) for m, flag in ((n - b, False), (b, True)) if m > 0)
    return out


def bound_unread(snap, house, only=None):
    out = [(c.get("name"), w) for c in house_chars(snap["chars"], house, only).values() for w in ("bags", "bank")
           if c.get(w) and "bound" not in c[w]]
    if only is None and snap.get("warband") and "bound" not in snap["warband"]:
        out.append((None, "warband"))
    return out


def house_holdings(snap, house, coming=(), only=None):
    faction, out = house.partition("|")[2], []
    chars = house_chars(snap["chars"], house, only)
    waiting = {}
    for who, k, n, t in coming:
        mail = (chars.get(who) or {}).get("mail")
        if mail and t > (mail.get("at") or 0):
            spot = waiting.setdefault(who, {})
            spot[k] = spot.get(k, 0) + n
    for who, c in chars.items():
        for where in PLACES:
            rec = c.get(where)
            if rec:
                items = on_auction(rec, faction) if where == "auctions" else counts_of(rec)
                if where == "mail":
                    for k, n in waiting.get(who, {}).items():
                        items[k] = items.get(k, 0) + n
                out.extend((c.get("name"), where, k, n, b) for k, n, b in split_bound(rec, items))
    if only is None and snap.get("warband"):
        out.extend((None, "warband", k, n, b) for k, n, b in split_bound(snap["warband"], counts_of(snap["warband"])))
    return out


SELL_FROM = ("bags", "bank", "mail", "warband")


def sell_places(snap, house, coming=(), only=None):
    out, bound = {}, {}
    for who, where, k, n, b in house_holdings(snap, house, coming, only):
        if where in SELL_FROM:
            name = "Warband bank" if where == "warband" else who or "?"
            spot = (bound if b else out).setdefault(k, {}).setdefault(name, {})
            spot[where] = spot.get(where, 0) + n
    return out, bound


def units_of(places):
    return {k: {name: sum(at.values()) for name, at in by.items()} for k, by in places.items()}


def to_sell(snap, house, coming=(), only=None):
    return tuple(units_of(side) for side in sell_places(snap, house, coming, only))


def place_times(snap, house, only=None):
    return {c.get("name"): {w: c[w].get("at") for w in PLACES if c.get(w)} for c in house_chars(snap["chars"], house, only).values()}


def held(hub, house=None, now=None, which="all"):
    import gamedata
    import trades
    now = now or time.time()
    snap = hub.characters.snapshot()
    key, _, market = house_parts(hub, house)
    prices = {r["item"]: r for r in (market or {}).get("items") or ()}
    only = shown(hub, which)
    out = {"house": key, "now": now, "priced": (market or {}).get("newest"),
           "elsewhere": len(snap["chars"]) - len(house_chars(snap["chars"], key)),
           "characters": [{"who": who, "places": at} for who, at in place_times(snap, key, only).items()],
           "classes": {}, "rows": []}
    if only is None and snap.get("warband"):
        out["characters"].append({"who": None, "places": {"warband": snap["warband"].get("at")}})
    goods = house_holdings(snap, key, trades.to_mail(acted(hub, hub.auction.listing_of(key), snap)), only)
    infos = hub.auction.infos(sorted({k for _, _, k, _, _ in goods}))
    classes = gamedata.item_classes()
    used = set()
    for who, where, k, n, b in goods:
        info = infos.get(k) or {}
        v = value_of(k, prices, gamedata.item_sell_price, b)
        cls = am.subclass_of(classes, k).split(".")[0]
        cls = cls if cls in classes[1] else ""
        used.add(cls)
        out["rows"].append({"who": who, "where": where, "key": k, "name": info.get("n"), "q": info.get("q"),
                            "icon": info.get("icon"), "cls": cls, "units": n, "bound": b, **v,
                            "total": None if v["unit"] is None else round(v["unit"] * n)})
    out["classes"] = {c: classes[1][c] for c in used if c in classes[1]}
    out["unbound"] = [list(p) for p in bound_unread(snap, key, only)]
    return out
