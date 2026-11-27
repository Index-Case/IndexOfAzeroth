# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import datetime
import json
import os
import re
import threading
import time

import gamelogs
import store
import storewriter
from characters import counted
from auction import house_key
from trades import resold

ROOT = os.path.dirname(os.path.abspath(__file__))
MARKS = os.path.join(ROOT, "data", "ledger", "waste.json")

COIN_SAME = 1.0
LOOT_NEAR = 2.5
WEEKS_AFTER = 120
HOURS_MOST = 2 * 86400
RANGES = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": None}
TREND_DAYS = 30
CAUSES = ("grinding", "loot", "share", "quest", "vendor", "repair", "training", "flight", "auction", "auctionbuy",
          "auctionfee", "refund", "mail", "postage", "trade", "between", "atvendor", "unexplained")
PEOPLE = ("mail", "trade", "between")
PEOPLE_MOST = 200
SOURCES_MOST = 200
UNEXPLAINED_MOST = 500
PLAYED_GAP = 60.0
DEATH_SAME = 2.0
T_OF = re.compile(r'"t":\s*(-?[0-9.]+)')
COIN_LINE = re.compile(r"^(?:You loot |Your share of the loot is )((?:\d+ (?:Gold|Silver|Copper)(?:, )?)+)\.?$")
COIN_PART = re.compile(r"(\d+) (Gold|Silver|Copper)")
COPPER = {"Gold": 10000, "Silver": 100, "Copper": 1}


def coin_of(text):
    m = COIN_LINE.match(text or "")
    return sum(int(n) * COPPER[u] for n, u in COIN_PART.findall(m.group(1))) if m else None


def coins_of(lines):
    out = []
    last = {}
    for t, c in sorted(lines):
        if c in last and t - last[c] <= COIN_SAME:
            last[c] = t
            continue
        last[c] = t
        out.append((t, c))
    return out


def causes_of(money, coins):
    out, prev = [], None
    times = [t for t, _ in coins]
    used = [False] * len(coins)
    for e in money:
        c = e.get("c")
        if not isinstance(c, int):
            continue
        if prev is None:
            prev = c
            out.append({"t": e["t"], "c": c, "d": 0, "parts": {}, "unseen": False})
            continue
        d, prev = c - prev, c
        if not d:
            continue
        unseen = "d" not in e
        parts, left = {}, d
        if d > 0 and not unseen:
            lo, hi = bisect.bisect_left(times, e["t"] - LOOT_NEAR), bisect.bisect_right(times, e["t"] + LOOT_NEAR)
            near = sorted((i for i in range(lo, hi) if not used[i]), key=lambda i: abs(times[i] - e["t"]))
            whole = next((i for i in near if coins[i][1] == d), None)
            for i in ([whole] if whole is not None else near):
                if coins[i][1] <= left:
                    used[i] = True
                    left -= coins[i][1]
                    parts["loot"] = parts.get("loot", 0) + coins[i][1]
        if left and e.get("v") and not unseen:
            parts["atvendor"], left = left, 0
        if left:
            parts["unexplained"] = left
        out.append({"t": e["t"], "c": c, "d": d, "parts": parts, "unseen": unseen})
    return out


class RecordedMoney:

    def __init__(self, record):
        self.record = record
        self.lock = threading.Lock()
        self.days = {}
        self.books = {}

    def _day(self, key, day):
        stamp = self.record.stamp(key, day)
        kept = self.days.get((key, day))
        if kept and kept[0] == stamp:
            return kept[1]
        money, lines, seen, times, deaths, zones = [], [], False, [], [], []
        for line in self.record.day_lines(key, day):
            t = T_OF.search(line)
            if t:
                times.append(float(t.group(1)))
            if '"k":"$"' in line:
                seen = True
                try:
                    money.append(json.loads(line))
                except ValueError:
                    continue
            elif '"k":"m"' in line and ("Copper" in line or "Silver" in line or "Gold" in line):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                c = coin_of(e.get("text")) if e.get("ch") == "system" else None
                if c:
                    lines.append((e["t"], c))
            elif '"k":"z"' in line or '"k":"i"' in line:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                zones.append((e["t"], e["k"], e.get("zone") if e["k"] == "z" else e.get("kind"), e.get("sub")))
            elif '"UNIT_DIED"' in line:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if gamelogs.is_me(e.get("df", 0)):
                    deaths.append(e["t"])
            if not seen and ('"k":"p"' in line or '"k":"g"' in line):
                seen = True
        got = {"money": money, "coins": lines, "seen": seen, "spans": spans_of(times), "deaths": deaths, "zones": zones}
        self.days[(key, day)] = (stamp, got)
        return got

    def book(self, key):
        with self.lock:
            days = [d["day"] for d in self.record.days(key)]
            got = {day: self._day(key, day) for day in days}
            stamps = tuple((day, str(self.days[(key, day)][0])) for day in days)
            kept = self.books.get(key)
            if kept and kept[0] == stamps:
                return kept[1]
            money = sorted((e for day in days for e in got[day]["money"]), key=lambda e: e["t"])
            coins = coins_of([x for day in days for x in got[day]["coins"]])
            changes = causes_of(money, coins)
            book = {"changes": changes, "times": [x["t"] for x in changes],
                    "seen": [day for day in days if got[day]["seen"]],
                    "spans": merged([s for day in days for s in got[day]["spans"]]),
                    "deaths": deaths_of([t for day in days for t in got[day]["deaths"]]),
                    "places": places_of([z for day in days for z in got[day]["zones"]])}
            self.books[key] = (stamps, book)
            return book


def spans_of(times):
    out = []
    for t in sorted(times):
        if out and t - out[-1][1] <= PLAYED_GAP:
            out[-1][1] = t
        else:
            out.append([t, t])
    return [s for s in out if s[1] > s[0]]


def merged(spans):
    out = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] <= PLAYED_GAP:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def played_in(spans, since, until):
    return sum(max(0.0, min(b, until) - max(a, since)) for a, b in spans)


def deaths_of(times):
    out = []
    for t in sorted(times):
        if not out or t - out[-1] > DEATH_SAME:
            out.append(t)
    return out


def places_of(events):
    out, zone, sub, inside = [], None, None, False
    for t, k, what, part in sorted(events, key=lambda e: e[0]):
        if k == "z":
            zone, sub = what, part
        else:
            inside = bool(what)
        out.append((t, zone, None if inside else (sub or None)))
    return out


def place_at(places, t):
    i = bisect.bisect_right([p[0] for p in places], t)
    if not i or not places[i - 1][1]:
        return None
    _, zone, sub = places[i - 1]
    return {"zone": zone, "sub": sub} if sub else {"zone": zone}


def day_of(t):
    return datetime.date.fromtimestamp(t).isoformat()


def day_start(day):
    return time.mktime(datetime.date.fromisoformat(day).timetuple())


def bucket_of(since, until):
    return "hour" if until - since <= HOURS_MOST else "week" if until - since > WEEKS_AFTER * 86400 else "day"


def span_of(rng, first, now, picked=None):
    if picked:
        since, until = picked
    elif rng == "24h":
        since, until = now - 86400, now
    else:
        today = datetime.date.fromtimestamp(now)
        back = RANGES.get(rng, 7)
        start = (datetime.date.fromtimestamp(first) if first else today) if back is None \
            else today - datetime.timedelta(days=back - 1)
        since, until = time.mktime(start.timetuple()), now
    bucket = bucket_of(since, until)
    at = datetime.datetime.fromtimestamp(since)
    at = at.replace(minute=0, second=0, microsecond=0) if bucket == "hour" else datetime.datetime.combine(at.date(), datetime.time())
    return at.timestamp(), until, bucket


def buckets_of(since, until, bucket):
    out, d = [], datetime.datetime.fromtimestamp(since)
    step = {"hour": datetime.timedelta(hours=1), "day": datetime.timedelta(days=1),
            "week": datetime.timedelta(days=7)}[bucket]
    while d.timestamp() <= until:
        out.append(d.timestamp())
        d = d + step if bucket == "hour" else datetime.datetime.combine(d.date() + step, datetime.time())
    return out


def source_of(x, cause, sold=None):
    if sold is not None and cause in ("auction", "auctionfee", "refund") and x.get("sub") == "sale":
        return ("item", sold, None)
    if cause in ("grinding", "loot"):
        kind = {"corpse": "npc", "alive": "npc", "object": "object", "item": "item"}.get(x.get("sub"))
        return (kind, x.get("id"), None) if kind and x.get("id") is not None else (None, None, None)
    if cause == "quest":
        return ("quest", x.get("id"), None) if x.get("id") is not None else (None, None, None)
    if cause == "vendor":
        return ("item", x.get("id"), None) if x.get("id") is not None else (None, None, x.get("name"))
    if cause == "training" and x.get("id") is not None:
        return ("spell", x["id"], None)
    if cause in ("repair", "training"):
        return (None, None, x.get("name"))
    if cause == "flight" and x.get("id") is not None:
        return ("route", (x.get("from"), x["id"]), None)
    if cause in ("auction", "auctionbuy", "auctionfee", "refund"):
        if x.get("id") is not None:
            return ("item", x["id"], None)
        return (None, None, (x.get("invoice") or {}).get("name"))
    if cause in PEOPLE:
        return (None, None, x.get("name"))
    return (None, None, None)


def wasted_by_rule(x, cause, key, house):
    if cause == "auctionfee" and x.get("sub") == "deposit" and (key, x.get("series"), x.get("seq")) in house.get("lost", ()):
        return ("deposit", abs(x["parts"][cause]))
    if cause == "auction":
        loss = (house.get("resold") or {}).get(f"{key}|{x.get('series')}|{x.get('seq')}")
        return ("resold", loss) if loss else None
    if cause == "vendor" and x.get("sub") == "sell" and house.get("cut") is not None and x.get("id") and x.get("count"):
        at = ((house.get("prices") or {}).get(str(x["id"])) or {}).get(x["t"])
        if at:
            forgone = round((1 - house["cut"]) * at[1] * x["count"] - x["parts"][cause])
            return ("vendor", forgone) if forgone > 0 else None
    return None


def own_names(chars):
    return {((c.get("name") or "").lower(), (c.get("realm") or "").lower()) for c in chars.values() if c.get("name")}


def is_own(name, realm, own):
    if not name:
        return False
    who, _, theirs = name.partition("-")
    return (who.lower(), (theirs or realm or "").lower()) in own


def booked(x, rec, own, scope):
    parts = x["parts"]
    if not any(c in parts for c in ("mail", "trade")) or not is_own(x.get("name"), rec.get("realm"), own):
        return parts
    if scope == "account":
        return {c: v for c, v in parts.items() if c not in ("mail", "trade")}
    return {("between" if c in ("mail", "trade") else c): v for c, v in parts.items()}


def kind_of(x):
    if x.get("why"):
        return x["why"]
    if x.get("unseen"):
        return "unseen"
    return "none" if "seq" in x else "before"


def source_key(side, cause, kind, id, name):
    return json.dumps([side, cause, kind, list(id) if isinstance(id, tuple) else id, name], separators=(",", ":"))


class Marks:

    def __init__(self, path=MARKS):
        self.path = path
        self.lock = threading.Lock()
        self.marks = None

    def get(self):
        with self.lock:
            if self.marks is None and not self.path:
                self.marks = {}
            if self.marks is None:
                got = store.load_json(self.path, {})
                self.marks = {k: v for k, v in got.items() if isinstance(v, bool)} if isinstance(got, dict) else {}
            return dict(self.marks)

    def set(self, key, waste):
        self.get()
        with self.lock:
            if self.marks.get(key) == waste:
                return False
            if waste is None:
                self.marks.pop(key, None)
            else:
                self.marks[key] = waste
            if self.path:
                storewriter.save_json_later(self.path, dict(self.marks))
            return True


def held_at(book, t):
    i = bisect.bisect_right(book["times"], t)
    return book["changes"][i - 1]["c"] if i else None


class Financials:

    def __init__(self, source, chars, now=time.time, names=None, marks=None, trades=None, market=None):
        self.source = source
        self.chars = chars
        self.now = now
        self.marks = marks or Marks(path=None)
        self.names = names or (lambda kind, id: None)
        self.trades = trades
        self.market = market or (lambda house, wanted: {})

    def auction_waste(self, houses, books, since, until):
        out = {}
        for house, keys in houses.items():
            view = self.trades(house) if self.trades else None
            if not view:
                continue
            failed = {r["key"] for r in view["auctions"] if r["outcome"] in ("expired", "cancelled") and r.get("sure") == "certain"}
            cut = (view["rules"].get("cut") or {}).get("share")
            wanted = {}
            if cut is not None:
                for k in keys:
                    for x in books[k]["changes"]:
                        if since <= x["t"] <= until and x.get("sub") == "sell" and "vendor" in x["parts"] and x.get("id"):
                            wanted.setdefault(str(x["id"]), []).append(x["t"])
            rows = {r["key"]: r for r in view["auctions"]}
            out[house] = {"lost": {tuple(v) for a, v in view["deposits"].items() if a in failed},
                          "resold": resold(view), "cut": cut, "prices": self.market(house, wanted) if wanted else {},
                          "items": {m: rows[a].get("item") for m, a in view["saleMoney"].items() if a in rows and rows[a].get("item")}}
        return out

    def name_of(self, kind, id):
        try:
            return self.names(kind, id) if id is not None else None
        except Exception:
            return None

    def answer(self, scope, key, rng, picked=None, every=False):
        now = self.now()
        chars = self.chars() or {}
        if scope == "account":
            near = counted(chars, key, every)
            chars = {k: c for k, c in chars.items() if k in near}
        keys = sorted(chars) if scope == "account" else [key] if key else []
        books = {k: self.source.book(k) for k in keys}
        first = min((b["changes"][0]["t"] for b in books.values() if b["changes"]), default=None)
        since, until, bucket = span_of(rng, first, now, picked)
        starts = buckets_of(since, until, bucket)
        rows = [{"at": s, "income": 0, "spending": 0, "in": {}, "out": {}} for s in starts]
        causes = {"in": {}, "out": {}}
        before = {"in": {}, "out": {}}
        subs = {"in": {}, "out": {}}
        sources = {}
        lost = []
        unseen = {"in": 0, "out": 0}
        people, opened = [], 0
        others = {}
        own = own_names(chars)
        house_of = {k: house_key((chars.get(k) or {}).get("realm"), (chars.get(k) or {}).get("faction")) for k in keys}
        by_house = {}
        for k in keys:
            by_house.setdefault(house_of[k], []).append(k)
        waste_of = self.auction_waste(by_house, books, since, until)
        for k in keys:
            book, rec = books[k], chars.get(k) or {}
            house = waste_of.get(house_of[k]) or {}
            changes = book["changes"]
            if changes and since <= changes[0]["t"] <= until:
                opened += changes[0]["c"]
            inc = spent = 0
            deaths, repaired = book.get("deaths") or [], None
            for x in changes:
                death = None
                if "repair" in x["parts"]:
                    lo = bisect.bisect_right(deaths, repaired) if repaired is not None else 0
                    death = "death" if lo < bisect.bisect_right(deaths, x["t"]) else None
                    repaired = x["t"]
                parts = booked(x, rec, own, scope)
                if x["d"] and 2 * since - until <= x["t"] < since:
                    for cause, amount in parts.items():
                        side = "in" if amount > 0 else "out"
                        before[side][cause] = before[side].get(cause, 0) + abs(amount)
                if not since <= x["t"] <= until or not x["d"]:
                    continue
                self.count_person(others, x, k, rec, own)
                at = max(0, bisect.bisect_right(starts, x["t"]) - 1)
                row = rows[at]
                for cause, amount in parts.items():
                    side = "in" if amount > 0 else "out"
                    causes[side][cause] = causes[side].get(cause, 0) + abs(amount)
                    row[side][cause] = row[side].get(cause, 0) + abs(amount)
                    sub = kind_of(x) if cause == "unexplained" else ("all" if x.get("all") else "seen") \
                        if cause == "repair" else x.get("sub") if cause not in ("grinding", "share", "quest", "training",
                                                                                 "flight", "atvendor") else ""
                    part = subs[side].setdefault(cause, {}).setdefault(sub or "", [0, 0])
                    part[0] += abs(amount)
                    part[1] += 1
                    kind, id, name = source_of(x, cause, house.get("items", {}).get(f"{k}|{x.get('series')}|{x.get('seq')}"))
                    s = sources.setdefault((side, cause, kind, id if not isinstance(id, tuple) else tuple(id), name),
                                           {"total": 0, "n": 0, "by": {}, "at": set(), "waste": {}})
                    s["total"] += abs(amount)
                    s["n"] += 1
                    s["by"][at] = s["by"].get(at, 0) + abs(amount)
                    if cause in ("vendor", "training") and x.get("name"):
                        s["at"].add(x["name"])
                    wasted = (death, abs(amount)) if cause == "repair" and death else wasted_by_rule(x, cause, k, house)
                    if wasted and wasted[1] > 0:
                        w = s["waste"].setdefault(wasted[0], [0, 0])
                        w[0] += wasted[1]
                        w[1] += 1
                    if cause == "unexplained":
                        lost.append((x["t"], amount, kind_of(x), x.get("windows") or [], k,
                                     place_at(book.get("places") or [], x["t"])))
                    if amount > 0:
                        row["income"] += amount
                        inc += amount
                    else:
                        row["spending"] -= amount
                        spent -= amount
                if x["unseen"]:
                    unseen["in" if x["d"] > 0 else "out"] += abs(x["d"])
            people.append({"key": k, "name": rec.get("name"), "realm": rec.get("realm"),
                           "faction": rec.get("faction"), "money": rec.get("money"),
                           "start": held_at(book, since), "end": held_at(book, until), "income": inc, "spending": spent,
                           "played": round(played_in(book.get("spans") or [], since, until)),
                           "points": [[round(x["t"], 1), x["c"]] for x in changes if since <= x["t"] <= until],
                           "seen": [d for d in book["seen"] if since < day_start(d) + 86400 and day_start(d) <= until]})
        seen_days = {d for p in people for d in p["seen"]}
        for i, row in enumerate(rows):
            end = starts[i + 1] if i + 1 < len(starts) else until
            row["net"] = row["income"] - row["spending"]
            row["seen"] = any(row["at"] <= day_start(d) + 86399 and day_start(d) < end for d in seen_days)
            known = {p["key"]: held_at(books[p["key"]], min(end, until)) for p in people} if row["seen"] else {}
            row["parts"] = {k: v for k, v in known.items() if v is not None}
            row["held"] = sum(row["parts"].values()) if row["seen"] else None
        income = sum(r["income"] for r in rows)
        spending = sum(r["spending"] for r in rows)
        moved = income + spending
        unexplained = causes["in"].get("unexplained", 0) + causes["out"].get("unexplained", 0)
        named = [(a, side, c) for side in ("in", "out") for c, a in causes[side].items() if c != "unexplained"]
        top = max(((a, c) for a, side, c in named if side == "in"), default=None)
        drain = max(((a, c) for a, side, c in named if side == "out"), default=None)
        houses = {}
        for k, rec in chars.items() if scope == "account" else ():
            h = houses.setdefault((rec.get("realm") or "", rec.get("faction") or ""), {"count": 0, "money": 0})
            h["count"] += 1
            h["money"] += rec.get("money") or 0
        active = [books[p["key"]] for p in people if p["points"] or p["start"] is not None]
        seams = [b.get("seam") for b in active]
        if not active or all(s is None for s in seams):
            record = {"state": "none"}
        elif any(s is None for s in seams):
            record = {"state": "mixed"}
        else:
            latest = max(seams)
            record = {"state": "before", "from": latest} if latest > since else {"state": "recorded"}
        listed = self.listed(sources)
        return {
            "scope": scope, "char": key if scope != "account" else None, "range": rng, "now": now,
            "since": since, "until": until, "bucket": bucket, "first": first,
            "gold": sum((chars.get(k) or {}).get("money") or 0 for k in keys),
            "income": income, "spending": spending, "net": income - spending,
            "unexplained": unexplained, "unexplainedShare": unexplained / moved if moved else 0,
            "unseen": unseen, "causes": causes, "opened": opened,
            "start": sum(p["start"] or 0 for p in people), "end": sum(p["end"] or 0 for p in people),
            "top": {"cause": top[1], "amount": top[0]} if top else None,
            "drain": {"cause": drain[1], "amount": drain[0]} if drain else None,
            "rows": rows, "days": self.days(rows, bucket, people, books, since, until,
                                            lambda k, x: booked(x, chars.get(k) or {}, own, scope)),
            "trend": self.trend(people, books, now),
            "characters": people,
            "houses": [{"realm": r, "faction": f, **h} for (r, f), h in sorted(houses.items())],
            "record": record, "before": before,
            "parts": {side: {c: {s: {"total": v[0], "n": v[1]} for s, v in got.items()} for c, got in subs[side].items()}
                      for side in subs},
            "sources": listed, "waste": self.waste(listed),
            "played": sum(p["played"] for p in people),
            "lost": [{"t": round(t, 1), "d": d, "kind": kind, "windows": w, "key": k, "place": place}
                     for t, d, kind, w, k, place in sorted(lost, key=lambda x: -x[0])[:UNEXPLAINED_MOST]],
            "lostCount": len(lost),
            "others": sorted(({**p, "how": sorted(p["how"])} for p in others.values()),
                             key=lambda p: -(p["sent"] + p["received"]))[:PEOPLE_MOST],
            "cut": {h: w["cut"] for h, w in waste_of.items() if w.get("cut") is not None},
        }

    @staticmethod
    def count_person(others, x, key, rec, own):
        name, amount = x.get("name"), sum(v for c, v in x["parts"].items() if c in ("mail", "trade"))
        if not name or not amount:
            return
        who, _, realm = name.partition("-")
        if realm and realm.lower() == (rec.get("realm") or "").lower():
            name = who
        p = others.setdefault(name, {"name": name, "sent": 0, "received": 0, "n": 0, "last": 0, "by": {}, "how": set(),
                                     "own": is_own(name, rec.get("realm"), own)})
        side = "received" if amount > 0 else "sent"
        p[side] += abs(amount)
        p["n"] += 1
        p["last"] = max(p["last"], x["t"])
        p["how"].add("trade" if "trade" in x["parts"] else "mail")
        by = p["by"].setdefault(key, {"sent": 0, "received": 0})
        by[side] += abs(amount)

    WHYS = ("death", "deposit", "resold", "vendor")

    @staticmethod
    def waste(listed):
        out = {why: {"total": 0, "n": 0} for why in Financials.WHYS + ("marked",)}
        for side in ("in", "out"):
            for s in listed[side]:
                if s["marked"] is True:
                    out["marked"]["total"] += s["total"]
                    out["marked"]["n"] += 1
                elif s["marked"] is None:
                    for why, (total, n) in s["waste"].items():
                        out[why]["total"] += total
                        out[why]["n"] += n
        return out

    def listed(self, sources):
        out = {"in": [], "out": []}
        marks = self.marks.get()
        for (side, cause, kind, id, name), s in sources.items():
            out[side].append((s["total"], cause, kind, id, name, s, source_key(side, cause, kind, id, name)))
        for side in out:
            got = []
            for total, cause, kind, id, name, s, key in sorted(out[side], key=lambda x: -x[0])[:SOURCES_MOST]:
                x = {"cause": cause, "kind": kind, "total": total, "n": s["n"], "by": sorted(s["by"].items()),
                     "at": sorted(s["at"]), "key": key, "waste": s["waste"], "marked": marks.get(key)}
                if kind == "route":
                    x["from"], x["to"] = self.name_of("node", id[0]), self.name_of("node", id[1])
                else:
                    x["name"] = name or self.name_of(kind, id)
                if kind == "item":
                    x["id"] = id
                got.append(x)
            out[side] = got
        return out

    @staticmethod
    def days(rows, bucket, people, books, since, until, parts_of=lambda key, x: x["parts"]):
        if bucket == "day":
            return [{"day": day_of(r["at"]), "income": r["income"], "spending": r["spending"], "net": r["net"],
                     "seen": r["seen"]} for r in rows]
        out = {}
        d = datetime.date.fromtimestamp(since)
        while time.mktime(d.timetuple()) <= until:
            out[d.isoformat()] = {"day": d.isoformat(), "income": 0, "spending": 0, "net": 0, "seen": False}
            d += datetime.timedelta(days=1)
        for p in people:
            for day in p["seen"]:
                if day in out:
                    out[day]["seen"] = True
            for x in books[p["key"]]["changes"]:
                cell = out.get(day_of(x["t"])) if since <= x["t"] <= until else None
                if cell and x["d"]:
                    for amount in parts_of(p["key"], x).values():
                        cell["income" if amount > 0 else "spending"] += abs(amount)
                        cell["net"] += amount
        return list(out.values())

    @staticmethod
    def trend(people, books, now):
        today = datetime.date.fromtimestamp(now)
        out = []
        for back in range(TREND_DAYS - 1, -1, -1):
            d = today - datetime.timedelta(days=back)
            day, end = d.isoformat(), min(now, time.mktime(d.timetuple()) + 86399)
            seen = any(day in books[p["key"]]["seen"] for p in people)
            known = [held_at(books[p["key"]], end) for p in people]
            out.append({"day": day, "held": sum(v for v in known if v is not None) if seen else None})
        return out
