# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import glob
import gzip
import json
import math
import os
import random
import re
import threading
import time

import jsontext
import playerstores
import savedvars
import store
from characters import realm_label, realm_readable, realm_region, realm_type
from protocol import (AUCTION_BAND, AUCTION_KEYS, AUCTION_MIN_BID, AUCTION_NOKEY, AUCTION_SILENT, AUCTION_SOLD,
                      AUCTION_STATES, AUCTION_WHOLE, MAX_WIDE_PAYLOAD, item_key, parse_key, split_key)
from serverlog import log_error, start_thread

ROOT = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(ROOT, "data", "auction")
FEED_KEPT = 3000
SCANS_KEPT = 40
SALES_KEPT = 500
INTERRUPTED = 5
STRIP_LOST = 2
RECENT = 14 * 86400
DAY = 86400
SAVED_EVERY = 5
BAND_LEAST = [0, 1800, 7200, 28800]
LOOP_LISTED_LEAST = 3
DEMO_REALM = "Demo"
HEAD_NAME_MOST = 36
GAME_ENDS = ("done", "stopped", "failed")
ENDED = GAME_ENDS + ("interrupted",)
STATE_CODES = {v: k for k, v in AUCTION_STATES.items()}
SAVED_NAME = "IndexOfAzeroth.lua"



POOLED = "pooled"


def row_bonuses(field):
    if not field:
        return ()
    if isinstance(field, int):
        return (field,) if field > 0 else ()
    if isinstance(field, tuple):
        return field
    return tuple(int(b) for b in str(field).split(":") if b.isdigit() and int(b) > 0)


def row_key(item, bonus, pooled=frozenset()):
    bonuses = row_bonuses(bonus)
    if not bonuses and item in pooled:
        return f"{item}:{POOLED}"
    return str(item_key(item, bonuses))


def pooled_in(marked, suffixed):
    return frozenset() if marked else frozenset(suffixed)


def kept_key(key, t, pool, at=None):
    suffixed, since = pool or ({}, None)
    if since is None or t is None or t >= since or not str(key).isdigit() or int(key) not in suffixed:
        return key
    if at is not None and (suffixed[int(key)] is None or suffixed[int(key)] > at):
        return key
    return f"{key}:{POOLED}"


def pair_cut(before_marked, after_marked, suffixed, unknown=()):
    return (frozenset(suffixed) if bool(before_marked) != bool(after_marked) else frozenset()) | frozenset(unknown)


def key_item(key):
    head, _, tail = str(key).partition(":")
    if tail == POOLED:
        return int(head) if head.isdigit() and int(head) else None
    return split_key(key)[0]


def price_key(text):
    head, _, tail = str(text or "").strip().partition(":")
    if tail == POOLED:
        item = key_item(f"{head}:{POOLED}")
        return None if item is None else f"{item}:{POOLED}"
    key = parse_key(text)
    return None if key is None else str(key)


def slug(realm, faction):
    return re.sub(r"[^a-z0-9]+", "-", f"{realm}-{faction}".lower()).strip("-") or "unknown"


def house_key(realm, faction):
    return f"{realm_label(realm)}|{faction or ''}"


def house_of_key(key):
    realm, _, faction = (key or "").partition("|")
    return house_key(realm, faction)


def in_house(realm, faction, key):
    return house_key(realm, faction) == house_of_key(key)


def house_name(key):
    market, _, faction = house_of_key(key).partition("|")
    return ", ".join(x for x in (market, faction) if x)


def read_whole(meta):
    return meta.get("state") == "done" and bool(meta.get("auctions"))


def house_listed(realm):
    return bool(realm_region(realm) and realm_type(realm))


class Scan:

    def __init__(self, sid, realm="", faction="", started=None, source="strip"):
        self.id, self.realm, self.faction = sid, realm, faction
        self.started = sid if started is None else started
        self.ended = None
        self.state, self.whole = "asking", False
        self.total = self.read = self.sent = self.parts = self.seconds = 0
        self.bands = list(BAND_LEAST)
        self.chunks = {}
        self.heard = None
        self.source = source
        self.finished = False
        self.keys = False
        self.by = self.by_key = self.by_from = None

    def stamp_by(self, name, playing):
        key, now_name = playing or (None, None)
        if name:
            match = key if now_name == name else None
            self.by_key = (self.by_key or match) if self.by == name else match
            self.by, self.by_from = name, "scan"
        elif now_name and not self.by:
            self.by, self.by_key, self.by_from = now_name, key, "play"

    @property
    def house(self):
        return house_key(self.realm, self.faction)

    def missing(self):
        return [n for n in range(1, self.parts + 1) if n not in self.chunks]

    def complete(self):
        return self.state == "done" and self.whole_in()

    def whole_in(self):
        return self.whole and not self.missing()

    def end_as(self, got):
        self.state, self.whole = got.state, got.whole
        self.total, self.read, self.sent = got.total or self.total, got.read or self.read, got.sent or self.sent

    def auctions(self):
        return [a for n in sorted(self.chunks) for a in self.chunks[n]]

    def received(self):
        return sum(len(c) for c in self.chunks.values())

    def one_based(self):
        return any(a[5] & AUCTION_BAND == 4 for c in self.chunks.values() for a in c)

    def copy(self):
        c = Scan.__new__(Scan)
        c.__dict__.update(self.__dict__)
        c.chunks, c.bands = dict(self.chunks), list(self.bands)
        return c

    def meta(self):
        out = {"id": self.id, "started": self.started, "ended": self.ended, "state": self.state, "whole": self.whole_in(),
               "complete": self.complete(), "auctions": self.received(), "total": self.total,
               "missing": self.missing(), "source": self.source, "items": self.items(), "seconds": self.seconds}
        if self.by:
            out.update(by=self.by, byKey=self.by_key, byFrom=self.by_from)
        if self.keys:
            out["keys"] = True
        return out

    def items(self):
        return len({(a[0], a[1]) for c in self.chunks.values() for a in c})

    def to_live(self):
        return {"id": self.id, "realm": self.realm, "faction": self.faction, "started": self.started,
                "state": self.state, "total": self.total, "read": self.read, "sent": self.sent, "parts": self.parts,
                "bands": self.bands}

    def to_json(self):
        sellers, index = [], {}
        chunks = {}
        for n, rows in self.chunks.items():
            out = []
            for item, sfx, count, buy, bid, flags, seller in rows:
                if seller not in index:
                    index[seller] = len(sellers)
                    sellers.append(seller)
                out.append([item, sfx, count, buy, bid, flags, index[seller]])
            chunks[str(n)] = out
        return {"id": self.id, "realm": self.realm, "faction": self.faction, "started": self.started,
                "ended": self.ended, "state": self.state, "whole": self.whole, "total": self.total, "read": self.read,
                "sent": self.sent, "parts": self.parts, "seconds": self.seconds, "bands": self.bands,
                "source": self.source, "sellers": sellers, "chunks": chunks, "by": self.by, "byKey": self.by_key,
                "byFrom": self.by_from, **({"keys": True} if self.keys else {})}

    @classmethod
    def from_json(cls, d):
        s = cls(d["id"], d.get("realm", ""), d.get("faction", ""), d.get("started"), d.get("source", "strip"))
        s.ended, s.state, s.whole = d.get("ended"), d.get("state", "done"), bool(d.get("whole"))
        s.total, s.read, s.sent = d.get("total", 0), d.get("read", 0), d.get("sent", 0)
        s.parts, s.seconds, s.bands = d.get("parts", 0), d.get("seconds", 0), d.get("bands") or list(BAND_LEAST)
        s.by, s.by_key, s.by_from = d.get("by"), d.get("byKey"), d.get("byFrom")
        s.keys = bool(d.get("keys"))
        sellers = d.get("sellers", [])
        s.chunks = {int(n): [(r[0], r[1], r[2], r[3], r[4], r[5], sellers[r[6]]) for r in rows]
                    for n, rows in d.get("chunks", {}).items()}
        s.finished = True
        return s



def band_of(flags, one_based):
    band = flags & AUCTION_BAND
    if band == 7:
        return None
    return max(0, min(3, band - 1 if one_based else band))


def least_of(scan, band):
    return scan.bands[band] if band < len(scan.bands) else BAND_LEAST[band]


def band_least(scan, flags, one_based):
    band = band_of(flags, one_based)
    return 0 if band is None else least_of(scan, band)


def match(before, after, could_be):
    pool = collections.defaultdict(collections.Counter)
    for seller, band in before:
        pool[band][seller] += 1
    order = (3, 2, 1, 0, None)
    new = []
    for seller, band in sorted(after, key=lambda a: -1 if a[1] is None else a[1], reverse=True):
        bands = [b for b in order if pool[b] and could_be(b, band)]
        took = next(((b, seller) for b in bands if seller and pool[b].get(seller)), None)
        if took is None:
            took = next(((b, "" if pool[b].get("") else next(iter(pool[b])))
                         for b in bands if pool[b].get("") or not seller), None)
        if took is None:
            new.append((seller, band))
            continue
        b, who = took
        pool[b][who] -= 1
        if not pool[b][who]:
            del pool[b][who]
    left = [(seller, band) for band, sellers in pool.items() for seller, n in sellers.items() for _ in range(n)]
    return left, new


def relisted(seller, count, by, of):
    return seller == by if seller and by else count == of


def reckon(before, after, suffixed=frozenset()):
    gap = (after.ended or after.started) - before.started
    unknown = set()

    def could_be(was, now):
        if was is None or now is None:
            return True
        return now <= was and (now == 3 or least_of(after, now + 1) > least_of(before, was) - gap)

    switch = pair_cut(before.keys, after.keys, suffixed)

    def listed(scan):
        one_based = scan.one_based()
        out, sold = collections.defaultdict(list), collections.Counter()
        for item, bonus, count, buy, bid, flags, seller in scan.auctions():
            if flags & AUCTION_NOKEY:
                if scan is after:
                    unknown.add(item)
                continue
            key = (item, 0 if item in switch else row_bonuses(bonus) or 0, count, buy)
            if flags & AUCTION_SOLD:
                sold[key] += 1
            elif buy > 0:
                out[key].append((seller, band_of(flags, one_based)))
        return out, sold

    (listed_before, sold_before), (listed_after, sold_after) = listed(before), listed(after)
    cut = switch | unknown
    pooled = pooled_in(after.keys, suffixed)
    left_of = collections.defaultdict(list)
    new_of = collections.defaultdict(list)
    for key in listed_before.keys() | listed_after.keys():
        if key[0] in cut:
            continue
        left, new = match(listed_before.get(key, ()), listed_after.get(key, ()), could_be)
        left.sort(key=lambda a: -1 if a[1] is None else least_of(before, a[1]), reverse=True)
        marked = max(0, sold_after.get(key, 0) - sold_before.get(key, 0))
        left_of[key[:2]].extend((key[3], key[2], seller, band) for seller, band in left[marked:])
        new_of[key[:2]].extend((key[3], key[2], seller, band) for seller, band in new)
    sales = collections.defaultdict(list)
    for (item, bonus), left in left_of.items():
        new, sold = new_of.get((item, bonus), []), []
        for g in sorted(left, key=lambda g: -g[1]):
            f = next((f for f in new if f[1] < g[1] and f[0] * g[1] == g[0] * f[1] and could_be(g[3], f[3])
                      and (f[2] == g[2] or not (f[2] and g[2]))), None)
            if f is not None:
                new.remove(f)
                left.remove(g)
                sold.append((g[0] / g[1], g[1] - f[1]))
        gone = sorted(((buy / count, count, seller) for buy, count, seller, band in left
                       if band is not None and least_of(before, band) > gap), reverse=True)
        for _, count, seller, _ in new:
            k = next((k for k, (_, of, by) in enumerate(gone) if relisted(seller, count, by, of)), None)
            if k is not None:
                del gone[k]
        sold.extend((unit, count) for unit, count, _ in gone)
        for unit, count in sorted(sold):
            sales[row_key(item, bonus, pooled)].append([after.started, round(unit), count, before.started])
    for key, n in sold_after.items():
        for _ in range(0 if key[0] in cut else max(0, n - sold_before.get(key, 0))):
            sales[row_key(key[0], key[1], pooled)].append([after.started, round(key[3] / key[2]), key[2], before.started])
    return dict(sales)



def weighted_median(pairs):
    pairs = sorted(pairs)
    half, run, middle = sum(c for _, c in pairs) / 2, 0, pairs[-1][0]
    for price, count in pairs:
        run += count
        if run >= half:
            middle = price
            break
    return middle


def listed_stats(auctions):
    units = [(a[3] / a[2], a[2]) for a in auctions if a[3] > 0]
    out = {"auctions": len(auctions), "quantity": sum(a[2] for a in auctions),
           "bidOnly": sum(1 for a in auctions if a[3] <= 0)}
    if not units:
        bids = [a[4] / a[2] for a in auctions if a[4] > 0]
        out["lowestBid"] = round(min(bids)) if bids else None
        return out
    distinct = sorted({round(u) for u, _ in units})
    qty = sum(c for _, c in units)
    out.update(top=distinct[::-1][:3], bottom=distinct[:3], average=round(sum(u * c for u, c in units) / qty),
               median=round(weighted_median(units)))
    return out


def asks(auctions):
    return len({a[6] if len(a) > 6 and a[6] else round(a[3] / max(1, a[2])) for a in auctions if a[3] > 0})


def sales_stats(rows, now):
    rows = sorted(rows, key=lambda r: r[0])
    units = sum(r[2] for r in rows)
    recent = [r for r in rows if now - r[0] <= RECENT]
    return {"sold": len(rows), "units": units, "average": round(sum(r[1] * r[2] for r in rows) / units),
            "median": round(weighted_median([(r[1], r[2]) for r in rows])), "last": rows[-1][0],
            "recentSold": len(recent),
            "recentAverage": round(sum(r[1] * r[2] for r in recent) / sum(r[2] for r in recent)) if recent else None,
            "recentMedian": round(weighted_median([(r[1], r[2]) for r in recent])) if recent else None,
            "newest": [{"at": r[0], "unit": r[1], "count": r[2], "since": r[3]} for r in rows[::-1][:10]]}


def value_of(listed, sales):
    if sales and sales.get("recentMedian") is not None:
        return sales["recentMedian"], "sales"
    if listed and listed.get("median") is not None:
        return listed["median"], "listed"
    return None, None



class House:

    def __init__(self, key, folder, keep=True, others=()):
        self.realm, _, self.faction = house_of_key(key).partition("|")
        self.keep, self.folder, self.folders = keep, folder, [folder, *others]
        self.lock = threading.RLock()
        self.keeping = threading.RLock()
        self.loaded = {}
        self.index = None
        d = store.load_json(playerstores.standing(os.path.join(self.folder, "house.json")), {}) if keep else {}
        self.stored_realm = d.get("realm") or self.realm
        self.scans = d.get("scans", [])
        for m in self.scans:
            m["complete"] = bool(m.get("whole") and read_whole(m))
        self.sales = d.get("sales", {})
        self.reckoned = [tuple(p) for p in d.get("reckoned", [])]
        self.next_scan_at = d.get("nextScanAt")
        self.no_answer = bool(d.get("noAnswer"))
        self.suffixed = {}
        self.keyed_since = d.get("keyedSince")
        self.take_suffixed(d)
        self.merged = list(d.get("merged", []))
        for other in others if keep else ():
            if os.path.basename(other) not in self.merged:
                self.take_in(store.load_json(playerstores.standing(os.path.join(other, "house.json")), {}))
                self.merged.append(os.path.basename(other))
        unknown = [i for i, t in self.suffixed.items() if t is None]
        if unknown:
            self.suffixed.update(self.first_suffixed(unknown))

    def take_suffixed(self, d):
        at = d.get("suffixedAt") or {}
        for item in d.get("suffixed", []):
            t = at.get(str(item))
            was = self.suffixed.get(item)
            self.suffixed[item] = t if was is None else was if t is None else min(was, t)

    def first_suffixed(self, items):
        left, out = set(items), {}
        for m in sorted(self.scans, key=lambda m: m["started"]):
            if not left:
                break
            if not m.get("keys"):
                continue
            try:
                with gzip.open(self.scan_file(m["id"]), "rt", encoding="utf-8") as f:
                    scan = Scan.from_json(json.load(f))
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                continue
            for item in {a[0] for a in scan.auctions() if row_bonuses(a[1])} & left:
                out[item] = scan.started
            left -= set(out)
        return {**out, **{item: self.keyed_since for item in left}}

    LEFT = ("lock", "keeping", "loaded", "index", "sales", "reckoned")
    handed = False

    def __getstate__(self):
        with self.lock:
            return {k: v for k, v in self.__dict__.items() if k not in self.LEFT}

    def __setstate__(self, state):
        self.__dict__.update(state, lock=threading.RLock(), keeping=threading.RLock(), loaded={}, index=None, sales={},
                             reckoned=[], handed=True)

    def take_in(self, d):
        have = {m["id"] for m in self.scans}
        self.scans = sorted(self.scans + [m for m in d.get("scans", []) if m.get("id") not in have],
                            key=lambda m: m["started"])
        for key, rows in d.get("sales", {}).items():
            kept = self.sales.get(key, [])
            seen = {tuple(r) for r in kept}
            self.sales[key] = sorted(kept + [r for r in rows if tuple(r) not in seen], key=lambda r: r[0])[-SALES_KEPT:]
        self.reckoned += [tuple(p) for p in d.get("reckoned", []) if tuple(p) not in set(self.reckoned)]
        self.take_suffixed(d)
        if d.get("keyedSince") and (self.keyed_since is None or d["keyedSince"] < self.keyed_since):
            self.keyed_since = d["keyedSince"]
        if (d.get("nextScanAt") or 0) > (self.next_scan_at or 0):
            self.next_scan_at, self.no_answer = d["nextScanAt"], bool(d.get("noAnswer"))

    def note_next(self, at, silent):
        with self.lock:
            if at is None or (self.next_scan_at or 0) > at or (at, bool(silent)) == (self.next_scan_at, self.no_answer):
                return False
            self.next_scan_at, self.no_answer = at, bool(silent)
            return True

    def store_next(self):
        with self.lock:
            if self.keep:
                os.makedirs(self.folder, exist_ok=True)
            self.save()

    @property
    def key(self):
        return f"{self.realm}|{self.faction}"

    def save(self):
        if not self.keep or self.handed:
            return
        d = {"realm": self.stored_realm, "faction": self.faction, "scans": self.scans, "sales": self.sales,
             "reckoned": [list(p) for p in self.reckoned], "nextScanAt": self.next_scan_at, "noAnswer": self.no_answer}
        if self.merged:
            d["merged"] = self.merged
        if self.keyed_since is not None:
            d.update(suffixed=sorted(self.suffixed), suffixedAt={str(i): t for i, t in sorted(self.suffixed.items())},
                     keyedSince=self.keyed_since)
        try:
            store.save_json(os.path.join(self.folder, "house.json"), d)
        except OSError:
            log_error(f"writing the auction house {self.key}")

    def scan_path(self, sid):
        return os.path.join(self.folder, f"scan-{sid}.json.gz")

    def scan_file(self, sid):
        name = os.path.basename(self.scan_path(sid))
        for folder in self.folders:
            path = playerstores.standing(os.path.join(folder, name))
            if os.path.exists(path):
                return path
        return playerstores.standing(self.scan_path(sid))

    def scan(self, sid):
        with self.lock:
            if sid not in self.loaded and self.keep:
                try:
                    with gzip.open(self.scan_file(sid), "rt", encoding="utf-8") as f:
                        self.loaded[sid] = Scan.from_json(json.load(f))
                except (OSError, ValueError, KeyError, IndexError, TypeError):
                    return None
            return self.loaded.get(sid)

    def meta(self, sid):
        return next((m for m in self.scans if m["id"] == sid), None)

    def put(self, scan):
        with self.lock:
            metas = sorted([m for m in self.scans if m["id"] != scan.id] + [scan.meta()], key=lambda m: m["started"])
            cut = max(0, len(metas) - SCANS_KEPT)
            dropped, metas = metas[:cut], metas[cut:]
            kept = any(m["id"] == scan.id for m in metas)
            if self.keep and kept:
                os.makedirs(self.folder, exist_ok=True)
                store.write_bytes(self.scan_path(scan.id), gzip.compress(jsontext.dumps(scan.to_json()).encode("utf-8")))
            self.scans = metas
            for old in dropped:
                self.loaded.pop(old["id"], None)
                if self.keep:
                    try:
                        os.remove(self.scan_path(old["id"]))
                    except OSError:
                        pass
            if kept:
                self.loaded[scan.id] = scan
            if scan.keys:
                for item in {a[0] for a in scan.auctions() if row_bonuses(a[1])}:
                    if self.suffixed.get(item) is None or scan.started < self.suffixed[item]:
                        self.suffixed[item] = scan.started
                self.keyed_since = min(self.keyed_since or scan.started, scan.started)
            added = self.reckon(scan)
            self.index = None
            self.save()
            return added

    def reckon(self, scan):
        if not scan.complete():
            return {}
        whole = [m for m in self.scans if m["complete"] and not m["missing"]]
        if not whole or whole[-1]["id"] != scan.id or len(whole) < 2:
            return {}
        pair = (whole[-2]["id"], scan.id)
        before = self.scan(pair[0])
        if pair in self.reckoned or before is None:
            return {}
        added = reckon(before, scan, self.suffixed)
        for key, rows in added.items():
            self.sales[key] = (self.sales.get(key, []) + rows)[-SALES_KEPT:]
        self.reckoned.append(pair)
        return added

    def by_item(self, sid):
        scan = self.scan(sid)
        out = collections.defaultdict(list)
        pooled = pooled_in(scan.keys, self.suffixed) if scan else frozenset()
        for a in scan.auctions() if scan else ():
            if not a[5] & AUCTION_NOKEY:
                out[row_key(a[0], a[1], pooled)].append(a)
        return out

    @property
    def pool(self):
        with self.lock:
            return dict(self.suffixed), self.keyed_since

    def keyed_sales(self):
        pool = self.pool
        with self.lock:
            if pool[1] is None:
                return dict(self.sales)
            out = collections.defaultdict(list)
            for key, rows in self.sales.items():
                for r in rows:
                    out[kept_key(key, r[0], pool)].append(r)
            return {k: sorted(v, key=lambda r: r[0]) for k, v in out.items()}

    def listing(self):
        with self.lock:
            made_of = (tuple((m["id"], m["auctions"]) for m in self.scans), len(self.suffixed))
            if self.index and self.index[0] == made_of:
                return self.index[1]
            whole = [m for m in self.scans if read_whole(m)]
            base = whole[-1] if whole else None
            out = {}
            for m in self.scans:
                if m is not base and m["auctions"] and (not base or m["started"] > base["started"]):
                    for key, rows in self.by_item(m["id"]).items():
                        out[key] = (m["started"], rows)
            if base:
                for key, rows in self.by_item(base["id"]).items():
                    if key not in out or out[key][0] <= base["started"] + DAY:
                        out[key] = (base["started"], rows)
            self.index = (made_of, out)
            return out

    def uncounted(self):
        with self.lock:
            return any("items" not in m for m in self.scans)

    def fill_counts(self):
        with self.lock:
            todo = [m["id"] for m in self.scans if "items" not in m]
        for sid in todo:
            try:
                with gzip.open(self.scan_file(sid), "rt", encoding="utf-8") as f:
                    d = json.load(f)
                items = len({(r[0], r[1]) for rows in d.get("chunks", {}).values() for r in rows})
                seconds = d.get("seconds") or 0
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                items, seconds = None, None
            with self.lock:
                m = self.meta(sid)
                if m is not None and "items" not in m:
                    m["items"], m["seconds"] = items, m.get("seconds", seconds)
        with self.lock:
            self.save()

    def last(self, complete=False):
        done = [m for m in self.scans if m["auctions"] and (m["complete"] or not complete)]
        return done[-1] if done else None

    def last_scan(self, complete=False):
        m = self.last(complete)
        return (m["ended"] or m["started"]) if m else None



class Auctions:

    def __init__(self, folder=FOLDER, infos=None, realm_now=None, now=time.time, faction_now=None, who_now=None,
                 vendor_seen=None):
        self.folder, self.now = folder, now
        self.vendor_seen = vendor_seen
        self.who_now = who_now or (lambda: None)
        self.infos = infos or _item_infos
        self.realm_now = realm_now or (lambda: None)
        self.faction_now = faction_now or (lambda: None)
        self.worked = {}
        self.lock = threading.RLock()
        self.houses = {}
        self.live = None
        self.feed = collections.deque(maxlen=FEED_KEPT)
        self.feed_seq = 0
        self.version = 0
        self.told = None
        self.strip_at = self.strip_back = None
        self.saved_seen = {}
        self.demo_thread = None
        self.counting = set()
        self.passes = None
        self._known_houses()
        self._waiting_on()

    def _known_houses(self):
        self.stored = collections.defaultdict(list)
        for folder in playerstores.listing(self.folder).values():
            d = store.load_json(playerstores.standing(os.path.join(folder, "house.json")), {})
            if d.get("realm") is not None and d.get("faction") is not None:
                newest = max((m.get("started") or 0 for m in d.get("scans") or ()), default=0)
                self.stored[house_key(d["realm"], d["faction"])].append((newest, folder))
        for key in list(self.stored):
            self.house(*key.split("|", 1))

    def _folders(self, key):
        named = slug(*key.split("|", 1))
        stored = [f for _, f in sorted(self.stored.get(key, ()), key=lambda p: (os.path.basename(p[1]) != named, -p[0]))]
        home = os.path.basename(stored[0]) if stored else named
        return os.path.join(self.folder, home), stored[1:]

    def _waiting_on(self):
        d = store.load_json(os.path.join(self.folder, "live.json"), None)
        if isinstance(d, dict) and isinstance(d.get("id"), int):
            s = Scan(d["id"], d.get("realm", ""), d.get("faction", ""), d.get("started"))
            s.state, s.total, s.read, s.sent = d.get("state", "reading"), d.get("total", 0), d.get("read", 0), d.get("sent", 0)
            s.parts, s.bands, s.heard = d.get("parts", 0), d.get("bands") or list(BAND_LEAST), self.now()
            self.live = s

    def _note_live(self, s):
        path = os.path.join(self.folder, "live.json")
        if s and not s.finished and s.source != "demo":
            os.makedirs(self.folder, exist_ok=True)
            store.save_json(path, s.to_live())
        else:
            try:
                os.remove(path)
            except OSError:
                pass

    def _realm(self, realm):
        return realm if realm_readable(realm) else self.realm_now() or ""

    def house(self, realm, faction):
        key = house_key(realm, faction)
        with self.lock:
            if key not in self.houses:
                folder, others = self._folders(key)
                self.houses[key] = House(key, folder, keep=realm != DEMO_REALM, others=others)
            return self.houses[key]

    def key_of(self, key=None):
        return house_of_key(key) if key else self.default_house()


    def strip_read(self, now=None):
        now = self.now() if now is None else now
        if self.strip_at is None or now - self.strip_at > STRIP_LOST:
            self.strip_back = now
        self.strip_at = now

    def _live_for(self, sid, now):
        s = self.live
        if s and s.id == sid:
            return s
        if s and not s.finished:
            self._finish(s, now)
        self.live = Scan(sid)
        return self.live

    def take_head(self, h, now=None):
        now = self.now() if now is None else now
        with self.lock:
            s = self._live_for(h["scan"], now)
            s.heard = now
            if not s.finished:
                fresh = not s.realm and not s.faction
                s.realm = h["realm"] if realm_readable(h["realm"]) else s.realm or self._realm(h["realm"])
                s.faction = h["faction"] or s.faction
                s.source = "demo" if s.realm == DEMO_REALM else s.source
                s.state, s.whole, s.seconds, s.bands = h["state"], h["whole"], h["seconds"], h["bands"]
                s.keys = s.keys or bool(h.get("keys"))
                s.stamp_by(h.get("by"), self.who_now())
                s.total, s.read, s.sent, s.parts = h["total"], h["read"], h["sent"], max(s.parts, h["chunks"])
                if s.realm or s.faction:
                    house = self.house(s.realm, s.faction)
                    if house.note_next(h.get("next"), h.get("silent")):
                        self.spawn(house.store_next)
                if s.state in GAME_ENDS:
                    self._finish(s, now)
                elif fresh:
                    self._note_live(s)
            return self.brief()

    def take_chunk(self, c, now=None):
        now = self.now() if now is None else now
        with self.lock:
            s = self._live_for(c["scan"], now)
            s.heard = now
            if c["chunk"] in s.chunks:
                return self.brief()
            s.chunks[c["chunk"]] = c["auctions"]
            s.parts = max(s.parts, c["chunk"])
            self._to_feed(c["auctions"])
            if s.finished:
                self._keep(s)
            return self.brief()

    def _to_feed(self, auctions):
        infos = self.infos(sorted({row_key(a[0], a[1]) for a in auctions}))
        for item, bonus, count, buy, bid, flags, seller in auctions:
            key = row_key(item, bonus)
            info = infos.get(key) or {}
            self.feed_seq += 1
            self.feed.append({"seq": self.feed_seq, "item": item, "bonus": bonus, "key": key,
                              "name": info.get("n"), "q": info.get("q"), "icon": info.get("icon"), "count": count,
                              "buyout": buy, "unit": round(buy / count) if buy else 0, "bid": bid,
                              "seller": seller})

    def _finish(self, s, now):
        s.finished = True
        if s.state not in ENDED:
            s.state = "interrupted"
        s.ended = s.ended or now
        self._note_live(None)
        self._keep(s)

    def _keep(self, s):
        if not s.realm and not s.faction:
            return
        self.spawn(self._put, self.house(s.realm, s.faction), s)

    @staticmethod
    def spawn(fn, *args):
        start_thread("auction scan kept", fn, args)

    def _put(self, house, s):
        try:
            with house.keeping:
                with self.lock:
                    scan = s.copy()
                added = house.put(scan)
        except Exception:
            log_error(f"keeping the auction house scan {s.id} of {house.key}")
            return None
        with self.lock:
            self.version += 1
            brief = self.brief()
        if self.told:
            self.told(brief)
        self.summarise(house.key)
        return added

    def summarise(self, key, redo=False):
        import auctiondays
        with self.lock:
            if self.passes is None:
                self.passes = auctiondays.Summaries(self.spawn)
            house = self.houses.get(key) if key else None
        return self.passes.start(house, redo)

    def running(self, now=None):
        now = self.now() if now is None else now
        with self.lock:
            s = self.live
            if not s or s.finished:
                return False
            since = max(s.heard or now, self.strip_back or 0)
            if self.strip_at is not None and now - self.strip_at < STRIP_LOST and now - since > INTERRUPTED:
                self._finish(s, now)
                told = self.brief()
            else:
                return True
        if self.told:
            self.told(told)
        return False

    def brief(self):
        with self.lock:
            s = self.live
            key = s.house if s and (s.realm or s.faction) else self.default_house()
            house = self.houses.get(key) if key else None
            last = house.last_scan() if house else None
            newest = house.scans[-1] if house and house.scans else None
            running = bool(s and not s.finished)
            out = {"running": running, "waiting": running and (self.strip_at is None or self.now() - self.strip_at > STRIP_LOST),
                   "house": key, "houseName": house_name(key), "lastScan": last, "lastComplete": house.last_scan(complete=True) if house else None,
                   "lastScanId": newest["id"] if newest else None,
                   "lastScanComplete": newest["complete"] if newest else None,
                   "stale": last is None or self.now() - last > DAY, "feed": self.feed_seq, "version": self.version,
                   "nextScanAt": house.next_scan_at if house else None,
                   "noAnswer": house.no_answer if house else False}
            if s:
                out.update(scan=s.id, realm=s.realm, faction=s.faction, state=s.state, complete=s.complete(),
                           whole=s.whole_in(), total=s.total, read=s.read, sent=s.sent, received=s.received(),
                           missing=len(s.missing()), started=s.started, seconds=s.seconds, demo=s.source == "demo")
            return out

    def default_house(self):
        realm, faction = self.realm_now(), self.faction_now()
        if realm and faction:
            return house_key(realm, faction)
        with self.lock:
            houses = [h for h in self.houses.values() if h.last_scan() is not None]
        mine = [h for h in houses if in_house(realm, h.faction, h.key)] if realm else houses
        return max(mine, key=lambda h: h.last_scan()).key if mine else None


    def status(self):
        out = self.brief()
        with self.lock:
            houses = list(self.houses.values())
        out["houses"] = []
        for h in houses:
            with h.lock:
                newest = h.scans[-1] if h.scans else None
                out["houses"].append({"house": h.key, "realm": h.realm, "faction": h.faction, "scans": len(h.scans),
                                      "lastScan": h.last_scan(), "lastComplete": h.last_scan(complete=True),
                                      "lastScanId": newest["id"] if newest else None,
                                      "lastScanComplete": newest["complete"] if newest else None,
                                      "sold": sum(len(v) for v in h.sales.values()),
                                      "nextScanAt": h.next_scan_at, "noAnswer": h.no_answer})
        return out

    def scans_of(self, key=None):
        key = self.key_of(key)
        with self.lock:
            kept = dict(self.houses)
        h = kept.get(key)
        realm, faction = (h.realm, h.faction) if h else ((key or "|").split("|", 1) + [""])[:2]
        scans = []
        if h:
            with h.lock:
                scans = [dict(m) for m in h.scans]
        return {"house": key, "name": house_name(key), "realm": realm, "faction": faction, "scans": scans,
                "houses": sorted(({"house": x.key, "name": house_name(x.key), "realm": x.realm, "faction": x.faction}
                                  for x in kept.values() if x.scans and house_listed(x.realm)), key=lambda x: x["name"])}

    def item_of(self, item, key=None):
        got = self.house_of(key)
        with self.lock:
            h = self.houses.get(got["house"]) if got["folder"] else None
        return {**got, "listed": h.listing().get(str(item)) if h else None}

    def whole_listings(self, key, since, items):
        with self.lock:
            h = self.houses.get(house_of_key(key))
        if not h:
            return []
        with h.lock:
            metas = [(m["started"], m["id"]) for m in h.scans if m["complete"] and not m["missing"] and m["started"] >= since]
        out = []
        for t, sid in metas:
            got = h.by_item(sid)
            out.append((t, {k: got[k] for k in items if k in got}))
        return out

    def listing_of(self, key=None):
        got = self.house_of(key)
        with self.lock:
            h = self.houses.get(got["house"]) if got["folder"] else None
        if not h:
            return {**got, "listing": {}, "scans": []}
        with h.lock:
            scans = [dict(m) for m in h.scans]
        return {**got, "listing": h.listing(), "scans": scans}

    def house_of(self, key=None):
        key = self.key_of(key)
        with self.lock:
            h = self.houses.get(key) if key else None
        if not h or not h.keep:
            return {"house": key, "realm": h.realm if h else None, "folder": None, "summarising": False, "pool": None}
        return {"house": key, "realm": h.realm, "folder": h.folder, "summarising": self.summarise(key), "pool": h.pool}

    def count_house(self, key):
        key = house_of_key(key)
        with self.lock:
            house = self.houses.get(key)
            if not house or not house.uncounted():
                return False
            if key not in self.counting:
                self.counting.add(key)

                def count():
                    try:
                        house.fill_counts()
                    finally:
                        with self.lock:
                            self.counting.discard(key)
                self.spawn(count)
            return True

    def feed_since(self, since=0, most=500):
        with self.lock:
            items = [e for e in self.feed if e["seq"] > since]
            return {"seq": self.feed_seq, "items": items[-most:], "running": bool(self.live and not self.live.finished)}

    def _house_for(self, key):
        key = self.key_of(key)
        with self.lock:
            return self.houses.get(key) if key else None

    def prices(self, keys, house=None):
        h = self._house_for(house)
        if not h:
            return {"house": None, "items": {}}
        listing = h.listing()
        now = self.now()
        infos = self.infos(sorted({str(k) for k in keys}))
        out = {}
        with h.lock:
            kept = h.keyed_sales()
            seen = set(listing) | set(kept)
            for key in keys:
                key = str(key)
                rows = listing[key][1] if key in listing else []
                sold = kept.get(key, [])
                listed = listed_stats(rows) if rows else None
                sales = sales_stats(sold, now) if sold else None
                value, source = value_of(listed, sales)
                info = infos.get(key) or {}
                out[key] = {"name": info.get("n"), "q": info.get("q"), "icon": info.get("icon"), "listed": listed,
                            "sales": sales, "value": value, "from": source,
                            "scanned": listing[key][0] if key in listing else None,
                            "suffixes": None if ":" in key else sorted(k for k in seen if k.startswith(key + ":"))}
        return {"house": h.key, "items": out}

    def items(self, house=None, words=None, most=None):
        h = self._house_for(house)
        if not h:
            return {"house": None, "items": []}
        listing = h.listing()
        infos = self.infos(sorted(listing))
        words = (words or "").strip().lower()
        out = []
        now = self.now()
        with h.lock:
            kept = h.keyed_sales()
            for key, (_, rows) in listing.items():
                info = infos.get(key) or {}
                if words and words not in (info.get("n") or "").lower():
                    continue
                listed = listed_stats(rows)
                sold = kept.get(key, [])
                sales = sales_stats(sold, now) if sold else None
                value, source = value_of(listed, sales)
                out.append({"item": key, "name": info.get("n"), "q": info.get("q"), "icon": info.get("icon"),
                            "auctions": listed["auctions"], "quantity": listed["quantity"],
                            "low": (listed.get("bottom") or [None])[0], "average": listed.get("average"),
                            "high": (listed.get("top") or [None])[0], "sold": sales["sold"] if sales else 0,
                            "value": value, "from": source})
        out.sort(key=lambda e: ((e["name"] or "~").lower(), e["item"]))
        return {"house": h.key, "items": out[:most] if most else out}

    def stamp(self, h):
        with h.lock:
            last = h.scans[-1] if h.scans else {}
            return self.version, id(h), len(h.scans), last.get("id"), last.get("auctions"), len(h.reckoned)

    def _worked(self, what, h, make):
        key = (what, h.key, self.stamp(h))
        got = self.worked.get(key)
        if got is None:
            got = make()
            with self.lock:
                for old in [k for k in self.worked if k[0] == what and k != key][1:]:
                    del self.worked[old]
                self.worked[key] = got
        return got

    def by_item(self, h):
        def make():
            out = collections.defaultdict(dict)
            for key, (_, rows) in h.listing().items():
                out[int(key.split(":")[0])].setdefault(key, ([], []))[0].extend(rows)
            for key, rows in h.keyed_sales().items():
                out[int(key.split(":")[0])].setdefault(key, ([], []))[1].extend(rows)
            return dict(out)
        return self._worked("items", h, make)

    def loop_prices(self, house=None):
        h = self._house_for(house)
        if not h:
            return None, {}

        def make():
            now, out = self.now(), {}
            for item, keys in self.by_item(h).items():
                figures = []
                for rows, sold in keys.values():
                    enough = asks(rows) >= LOOP_LISTED_LEAST
                    value, _ = value_of(listed_stats(rows) if enough else None, sales_stats(sold, now) if sold else None)
                    if value:
                        figures.append((len(rows), value))
                listed = sum(n for n, _ in figures)
                if figures:
                    out[item] = round(sum(n * v for n, v in figures) / listed if listed
                                      else sum(v for _, v in figures) / len(figures))
            return out
        return (h.key, self.stamp(h)), self._worked("loop", h, make)

    def listed_counts(self, house=None):
        h = self._house_for(house)
        if not h:
            return {}
        counts = {i: sum(len(rows) for rows, _ in keys.values()) for i, keys in self.by_item(h).items()}
        return {i: n for i, n in counts.items() if n}

    def summaries(self, keys, house=None):
        h = self._house_for(house)
        if not h:
            return {"house": None, "items": {}}
        have, now, out = self.by_item(h), self.now(), {}
        for key in map(str, keys):
            rows, sold = (have.get(int(key.partition(":")[0])) or {}).get(key, ([], []))
            if not rows and not sold:
                continue
            listed = listed_stats(rows) if rows else None
            sales = sales_stats(sold, now) if sold else None
            value, source = value_of(listed, sales)
            out[key] = {"auctions": listed["auctions"] if listed else 0, "quantity": listed["quantity"] if listed else 0,
                        "low": ((listed or {}).get("bottom") or [None])[0], "average": (listed or {}).get("average"),
                        "high": ((listed or {}).get("top") or [None])[0], "sold": sales["sold"] if sales else 0,
                        "value": value, "from": source}
        return {"house": h.key, "items": out}


    def import_saved(self, table, now=None):
        now = self.now() if now is None else now
        changed = []
        for rec in (table or {}).get("scans") or []:
            try:
                got, nxt, silent = parse_saved_scan(rec)
            except SAVED_BAD:
                continue
            sid = got.id
            got.realm = self._realm(got.realm)
            if got.realm or got.faction:
                house = self.house(got.realm, got.faction)
                if nxt is not None and house.note_next(nxt, silent):
                    house.store_next()
            with self.lock:
                s = self.live if self.live and self.live.id == sid else None
                if s and not s.finished:
                    for n, rows in got.chunks.items():
                        if n not in s.chunks:
                            s.chunks[n] = rows
                            self._to_feed(rows)
                    s.parts = max(s.parts, got.parts)
                    s.end_as(got)
                    s.realm, s.faction = got.realm or s.realm, got.faction or s.faction
                    s.keys = s.keys or got.keys
                    s.stamp_by(got.by, None)
                    self._finish(s, now)
                    changed.append(sid)
                    continue
            if not (got.realm or got.faction):
                continue
            house = self.house(got.realm, got.faction)
            with house.lock:
                meta = house.meta(sid)
                told = meta and meta["state"] == "interrupted" and got.state != "interrupted"
                if meta and not meta["missing"] and not told:
                    continue
                kept = house.scan(sid) if meta else None
                if kept:
                    scan = kept.copy()
                    added = {n: rows for n, rows in got.chunks.items() if n not in scan.chunks}
                else:
                    scan, added = got, dict(got.chunks)
                named = got.by and not scan.by
                if meta and not added and not told and not named:
                    continue
                scan.chunks.update(added)
                scan.stamp_by(got.by, None)
                scan.keys = scan.keys or got.keys
                scan.parts = max(scan.parts, got.parts)
                scan.end_as(got)
                scan.ended = scan.ended or got.ended or now
            if self._put(house, scan) is not None:
                changed.append(sid)
        return changed

    def saved_files(self, wtf):
        return sorted(glob.glob(os.path.join(wtf, "Account", "*", "SavedVariables", SAVED_NAME)))

    def check_saved(self, wtf):
        changed = []
        for path in self.saved_files(wtf) if wtf else ():
            stamp = store.stamp(path)
            if stamp is None or self.saved_seen.get(path) == stamp:
                continue
            self.saved_seen[path] = stamp
            db = savedvars.read(path).get("IndexOfAzerothDB")
            if isinstance(db, dict) and isinstance(db.get("auction"), dict):
                changed += self.import_saved(db["auction"])
            if self.vendor_seen and isinstance(db, dict) and isinstance(db.get("sell"), dict):
                self.vendor_seen(list(db["sell"].items()))
        return changed

    def watch_saved(self, wtf_dir, log_error, stop=None, every=SAVED_EVERY):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.check_saved(wtf_dir())
            except Exception:
                log_error("reading the auction house scans from the SavedVariables")
            stop.wait(every)


    def play_demo(self, auctions=4000, speed=3.0, seed=7, wait=False, sleep=time.sleep):
        from protocol import parse_frame
        with self.lock:
            if self.running() or (self.demo_thread and self.demo_thread.is_alive()):
                return False
            self.houses.pop(house_key(DEMO_REALM, "Horde"), None)
        rng = random.Random(seed)
        before_rows, after_rows = demo_house(rng, auctions, item_pool())
        now = int(self.now())
        house = self.house(DEMO_REALM, "Horde")
        before = Scan(now - 6 * 3600, DEMO_REALM, "Horde", source="demo")
        before.chunks = {n + 1: c for n, c in enumerate(split_parts(before_rows))}
        before.parts, before.state, before.whole, before.finished = len(before.chunks), "done", True, True
        before.ended = before.started + 20
        house.put(before)

        def play():
            sid = now
            parts = encode_chunks(after_rows, sid)
            head = {"scan": sid, "state": "reading", "whole": False, "total": len(after_rows), "read": len(after_rows),
                    "sent": 0, "chunks": 0, "seconds": 0, "bands": [0, 1800, 7200, 28800], "realm": DEMO_REALM,
                    "faction": "Horde"}
            t0, sent = self.now(), 0
            self._demo_frame(parse_frame(encode_head(head)))
            for n, part in enumerate(parts, 1):
                kind, data = parse_frame(part)
                sent += len(data["auctions"])
                self._demo_frame((kind, data))
                if n % max(1, round(speed)) == 0:
                    head.update(sent=sent, chunks=n, seconds=int(self.now() - t0))
                    self._demo_frame(parse_frame(encode_head(head)))
                sleep(1 / speed)
            head.update(state="done", whole=True, sent=sent, chunks=len(parts), seconds=int(self.now() - t0))
            self._demo_frame(parse_frame(encode_head(head)))

        if wait:
            play()
            return True
        self.demo_thread = start_thread("auction demo", play)
        return True

    def _demo_frame(self, frame):
        self.strip_read()
        kind, data = frame
        brief = self.take_head(data) if kind == "auction" else self.take_chunk(data)
        if self.told:
            self.told(brief)


def _item_infos(keys):
    import gamedata
    pooled = {str(k) for k in keys if str(k).endswith(":" + POOLED)}
    out = gamedata.item_infos([k for k in keys if str(k) not in pooled] + sorted({key_item(k) for k in pooled} - {None}))
    for k in pooled:
        base = out.get(str(key_item(k)))
        if base:
            out[k] = {**base, "pooled": 1}
    return out


SAVED_BAD = (KeyError, TypeError, ValueError, AttributeError, OverflowError)


def parse_saved_scan(rec):
    sid = int(rec["id"])
    texts = rec.get("chunks") or []
    texts = dict(enumerate(texts, 1)) if isinstance(texts, list) else {int(k): v for k, v in texts.items()}
    s = Scan(sid, rec.get("realm") or "", rec.get("faction") or "", rec.get("started") or sid, source="saved")
    s.chunks = {n: parse_saved_chunk(t) for n, t in texts.items()}
    s.parts = int(rec.get("parts") or 0) or (max(texts) if texts else 0)
    s.state = "done" if rec.get("complete") else rec.get("state") if rec.get("state") in GAME_ENDS else "stopped"
    s.whole = bool(rec.get("whole") or rec.get("complete"))
    s.ended = rec.get("ended")
    s.total, s.read, s.sent = rec.get("total") or 0, rec.get("read") or 0, rec.get("sent") or 0
    s.bands = [int(b) for b in rec.get("bands") or BAND_LEAST]
    s.stamp_by(str(rec["who"]) if rec.get("who") else None, None)
    s.keys = bool(rec.get("keys"))
    s.finished = True
    nxt = rec.get("nextAt")
    return s, int(nxt) if isinstance(nxt, (int, float)) else None, rec.get("silent")


def parse_saved_chunk(text):
    out = []
    for group in filter(None, text.split("~")):
        seller, _, rows = group.partition("^")
        for row in filter(None, rows.split("/")):
            item, bonus, count, buy, bid, flags = row.split(",")
            bonus = ":".join(map(str, sorted(set(row_bonuses(bonus.strip())))))
            item, count, buy, bid, flags = (int(float(v)) for v in (item, count, buy, bid, flags))
            out.append((item, bonus, count, buy, bid, flags, seller))
    return out



def _var(v):
    out = bytearray()
    v = max(0, int(v))
    while v >= 128:
        out.append(v % 128 + 128)
        v //= 128
    out.append(v)
    return bytes(out)


def _str(s, most):
    b = s.encode("utf-8")
    if len(b) > most:
        b = re.sub(rb"[\xc0-\xff][\x80-\xbf]*$", b"", b[:most])
    return bytes([len(b)]) + b


def encode_head(h):
    flags = (AUCTION_WHOLE if h["whole"] else 0) | (AUCTION_SILENT if h.get("silent") else 0) | \
        (AUCTION_KEYS if h.get("keys") else 0)
    return (bytes([32]) + int(h["scan"]).to_bytes(4, "little") + bytes([STATE_CODES[h["state"]], flags])
            + b"".join(_var(h[k]) for k in ("total", "read", "sent", "chunks", "seconds"))
            + b"".join(_var(b) for b in h["bands"]) + _str(h["realm"], 48) + _str(h["faction"], 16)
            + (int(h["next"]).to_bytes(4, "little") if h.get("next") is not None else b"")
            + (_str(h["by"], HEAD_NAME_MOST) if h.get("by") and h.get("next") is not None else b""))


def _auction_bytes(a):
    out = bytes([a[5]]) + _var(a[2]) + _var(a[3])
    return out + _var(a[4]) if a[5] & AUCTION_MIN_BID else out


def encode_chunks(auctions, sid, room=MAX_WIDE_PAYLOAD):
    by_seller = {}
    for a in auctions:
        by_seller.setdefault(a[6], []).append(a)
    queue = [(seller, sorted(rows, key=lambda a: (a[0], str(a[1])))) for seller, rows in by_seller.items()]
    frames, at, k = [], 0, 0
    while at < len(queue):
        frame = bytearray(bytes([33]) + int(sid).to_bytes(4, "little") + _var(len(frames) + 1))
        groups_at = len(frame)
        frame.append(0)
        groups = 0
        while at < len(queue) and groups < 255:
            seller, rows = queue[at]
            head = _str(seller, 48)
            free = room - len(frame) - len(head) - 3
            body, runs, prev = bytearray(), 0, None
            while k < len(rows):
                a = rows[k]
                bonuses = row_bonuses(a[1])
                step = (a[0] - prev if prev is not None else a[0]) * 2 + (1 if bonuses else 0)
                sfx = (bytes([len(bonuses)]) + b"".join(_var(b) for b in bonuses)) if bonuses else b""
                size = len(_var(step)) + len(sfx) + 3
                j, part = k, bytearray()
                while j < len(rows) and rows[j][:2] == a[:2] and len(body) + size + len(part) + len(_auction_bytes(rows[j])) <= free:
                    part += _auction_bytes(rows[j])
                    j += 1
                if j == k:
                    break
                body += _var(step) + sfx + _var(j - k) + part
                runs, prev = runs + 1, a[0]
                if j < len(rows) and rows[j][:2] == a[:2]:
                    k = j
                    break
                k = j
            if runs:
                frame += head + _var(runs) + body
                groups += 1
            if k < len(rows):
                break
            at, k = at + 1, 0
        frame[groups_at] = groups
        frames.append(bytes(frame))
    return frames


def split_parts(rows, size=400):
    return [rows[i:i + size] for i in range(0, len(rows), size)] or [[]]



DEMO_SELLERS = ["Grimtusk", "Zulmai", "Thraka", "Mokvar", "Kelris", "Ushara", "Bramwick", "Nazgrel", "Tikki", "Oskarr",
                "Velane", "Durgan", "Shaena", "Krognar", "Melis", "Jorvik", "Azzara", "Trokk", "Pellin", "Garosh"]


def item_pool():
    import gamedata
    _, items, _ = gamedata.client_table("items.json", "items")
    pool = [int(k) for k, v in items.items() if 1 <= v[1] <= 3 and not (len(v) > 3 and v[3])]
    return sorted(pool)[:3000] or list(range(2000, 2600))


def demo_house(rng, n, pool):
    items = rng.sample(pool, min(len(pool), max(1, n // 6)))
    price = {i: int(math.exp(rng.uniform(math.log(20), math.log(400000)))) for i in items}
    def one(seller=None, item=None):
        item = item or rng.choice(items)
        count = rng.choice([1, 1, 1, 5, 10, 20])
        unit = max(1, int(price[item] * rng.uniform(0.8, 1.3)))
        band = rng.choice([0, 1, 2, 3, 3, 3])
        buy = 0 if rng.random() < 0.05 else unit * count
        bid = int(unit * count * 0.8)
        flags = band | (AUCTION_MIN_BID if buy == 0 else 0)
        return (item, 0, count, buy, bid, flags, seller or rng.choice(DEMO_SELLERS))
    before = [one() for _ in range(n)]
    after = []
    for a in before:
        r = rng.random()
        if r < 0.06 and a[5] & AUCTION_BAND == 3:
            continue
        if r < 0.08:
            continue
        if r < 0.10 and a[3] > 0:
            after.append((a[0], 0, a[2], int(a[3] * 0.9), a[4], a[5], a[6]))
            continue
        after.append(a)
    while len(after) < n:
        after.append(one())
    rng.shuffle(after)
    return before, after
