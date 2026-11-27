# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datetime
import glob
import json
import os
import queue
import threading

import jsontext
import savedvars
import store
import storewriter
from dayrecord import safe
from protocol import (LEDGER_CANCEL, LEDGER_LISTED, LEDGER_MAILED, LEDGER_NOTICE, LEDGER_OWNED, LEDGER_POST,
                      LEDGER_TAKE)
from serverlog import log_error, start_thread

ROOT = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(ROOT, "data", "ledger")
SAVED_NAME = "IndexOfAzeroth.lua"
SAVED_EVERY = 5
FOLD_EVERY = 500

STOOD, LOOT, QUEST, VENDOR, REPAIR, TRAINING, FLIGHT, UNEXPLAINED, AUCTION, MAIL, TRADE = range(11)
CAUSES = {STOOD: "stood", LOOT: "loot", QUEST: "quest", VENDOR: "vendor", REPAIR: "repair", TRAINING: "training",
          FLIGHT: "flight", UNEXPLAINED: "unexplained", AUCTION: "auction", MAIL: "mail", TRADE: "trade"}
LOOT_FROM = {1: "corpse", 2: "alive", 3: "object", 4: "item", 5: "share", 6: "unknown"}
VENDOR_PART = {1: "sell", 2: "buy", 3: "buyback"}
REPAIR_ALL = 1
WHY = {1: "none", 2: "two", 3: "unseen"}
WINDOWS = {1: "merchant", 2: "trainer", 4: "taxi", 8: "loot", 16: "mail", 32: "auction", 64: "trade"}
AUCTION_PART = {0: "window", 1: "deposit", 2: "buyout", 3: "bid", 4: "commodity", 5: "cancel"}
MAIL_PART = {0: "window", 1: "sale", 2: "refund", 3: "player", 4: "cod", 5: "sent", 6: "postage", 7: "game"}
TRADE_PART = {0: "window", 1: "received", 2: "given", 3: "both"}
LOOT_BOOK = {"corpse": "grinding", "alive": "loot", "object": "loot", "item": "loot", "share": "share", "unknown": "loot"}
AUCTION_BOOK = {"deposit": "auctionfee", "cancel": "auctionfee", "buyout": "auctionbuy", "bid": "auctionbuy",
                "commodity": "auctionbuy"}

POST, OWNED, LISTED, CANCEL, NOTICE, MAILED, TAKE = (LEDGER_POST, LEDGER_OWNED, LEDGER_LISTED, LEDGER_CANCEL, LEDGER_NOTICE,
                                                     LEDGER_MAILED, LEDGER_TAKE)
KINDS = {POST: "post", OWNED: "owned", LISTED: "listed", CANCEL: "cancel", NOTICE: "notice", MAILED: "mail", TAKE: "take"}
MONEY_TEXT = ("cause", "sub", "d", "b", "id", "windows", "id2", "count", "part", "name", "bonus")
TEXT = {"P": (POST, ("auction", "item", "bonus", "units", "buyout", "bid", "duration", "deposit", "commodity", "name")),
        "O": (OWNED, ("auction", "item", "bonus", "units", "buyout", "bid", "left", "sold", "name")),
        "L": (LISTED, ("ids",)),
        "C": (CANCEL, ("auction",)),
        "N": (NOTICE, ("what", "auction", "from", "name")),
        "A": (MAILED, ("what", "money", "bid", "buyout", "deposit", "cut", "units", "item", "bonus", "expires", "name",
                       "other")),
        "T": (TAKE, ("what", "item", "bonus", "units", "mail", "cod", "sender"))}
TEXT_FIELDS = {"name", "other", "sender"}
FLAG_FIELDS = {"commodity", "sold", "cod"}
LIST_FIELDS = {"ids", "bonus"}


def key_hash(key):
    h = 0
    for b in (key or "").encode("utf-8"):
        h = (h * 31 + b) % 65536
    return h




def unescape(s):
    return s.replace("%2C", ",").replace("%0A", "\n").replace("%25", "%")


def parse_kept(text):
    if not isinstance(text, str) or not text:
        return None
    tag = None
    if text[0].isdigit():
        parts = text.split(",", 10)
        if len(parts) != 11:
            return None
        names, parts = ("seq", "t") + MONEY_TEXT[:8] + ("name",), parts
        raw_name = True
    else:
        tag, _, rest = text.partition(",")
        fields = ("seq", "t") + (MONEY_TEXT if tag == "M" else TEXT[tag][1] if tag in TEXT else ())
        parts = rest.split(",")
        if tag == "M" and len(parts) == len(fields) - 1:
            fields = fields[:-1]
        if len(fields) == 2 or len(parts) != len(fields):
            return None
        names, raw_name = fields, False
    e = {} if text[0].isdigit() or tag == "M" else {"kind": TEXT[tag][0]}
    try:
        for name, v in zip(names, parts):
            if v == "":
                continue
            if name in TEXT_FIELDS:
                e[name] = v if raw_name else unescape(v)
            elif name in LIST_FIELDS:
                e[name] = [int(x) for x in v.split(";") if x and (name != "bonus" or int(x) > 0)]
            elif name in FLAG_FIELDS:
                e[name] = v == "1"
            else:
                e[name] = int(float(v))
    except ValueError:
        return None
    if "seq" not in e or "t" not in e or ("kind" not in e and not all(k in e for k in ("cause", "sub", "d", "b"))):
        return None
    return e


def listed(v):
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v[k] for k in sorted(k for k in v if isinstance(k, int))]
    return []


def month_of(t):
    return datetime.date.fromtimestamp(t).strftime("%Y-%m")


def sale_parts(d, invoice):
    deposit, cut = (invoice or {}).get("deposit") or 0, (invoice or {}).get("cut") or 0
    parts = {"auction": d - deposit + cut}
    if deposit:
        parts["refund"] = deposit
    if cut:
        parts["auctionfee"] = -cut
    return parts


def auction_mail_change(x, e, cause, sub, mails):
    d = e["d"]
    if cause == "auction":
        x["sub"] = AUCTION_PART.get(sub, "window")
        x["parts"] = {AUCTION_BOOK.get(x["sub"], "auctionbuy" if d < 0 else "auction"): d} if d else {}
        if e.get("id2") is not None:
            x["auction"] = e["id2"]
    elif cause == "mail":
        x["sub"] = MAIL_PART.get(sub, "window")
        invoice = mails.get((e.get("series"), e["id2"])) if e.get("id2") is not None else None
        if invoice:
            x["invoice"] = {k: invoice[k] for k in ("seq", "name", "item", "bonus", "units", "buyout", "bid", "deposit", "cut")
                            if invoice.get(k) is not None}
        if x["sub"] == "sale":
            x["parts"] = sale_parts(d, invoice)
            if invoice and invoice.get("item"):
                x["id"] = invoice["item"]
        elif x["sub"] == "refund":
            x["parts"] = {"refund": d}
        elif x["sub"] in ("sent", "postage"):
            attached = min(abs(d), e.get("part") or 0) if x["sub"] == "sent" else 0
            x["parts"] = {k: v for k, v in (("mail", -attached), ("postage", -(abs(d) - attached))) if v}
        else:
            x["parts"] = {"mail": d} if d else {}
    else:
        x["sub"] = TRADE_PART.get(sub, "window")
        x["parts"] = {"trade": d} if d else {}
    for k in ("id", "count", "name", "part"):
        if e.get(k) is not None and k not in x:
            x[k] = e[k]
    return x


def change_of(e, mails=None):
    cause = CAUSES.get(e["cause"], "unexplained")
    x = {"t": e["t"], "c": e["b"], "d": e["d"], "parts": {}, "unseen": False, "seq": e["seq"], "series": e.get("series")}
    sub = e.get("sub") or 0
    if cause == "stood":
        return x
    if cause in ("auction", "mail", "trade"):
        return auction_mail_change(x, e, cause, sub, mails or {})
    if cause == "loot":
        part = LOOT_FROM.get(sub, "unknown")
        x["sub"], book = part, LOOT_BOOK[part]
    elif cause == "vendor":
        x["sub"], book = VENDOR_PART.get(sub), "vendor"
    elif cause == "unexplained":
        x["why"], book = WHY.get(sub, "none"), "unexplained"
        x["unseen"] = x["why"] == "unseen"
        if e.get("windows"):
            x["windows"] = [name for bit, name in sorted(WINDOWS.items()) if e["windows"] & bit]
    else:
        book = cause
        if cause == "repair" and sub == REPAIR_ALL:
            x["all"] = True
    if e["d"]:
        x["parts"][book] = e["d"]
    for k, out in (("id", "id"), ("id2", "from"), ("count", "count"), ("name", "name")):
        if e.get(k) is not None:
            x[out] = e[k]
    return x


class Ledger:

    def __init__(self, folder=FOLDER, resolve=None):
        self.folder = folder
        self.resolve = resolve or (lambda key: key)
        self.lock = threading.Lock()
        self.kept = {}
        self.added = {}
        self.version = 0
        self.saved_seen = {}
        self.inbox = queue.Queue()
        self.worker = None


    def _path(self, key, month):
        return os.path.join(self.folder, safe(key), month + ".jsonl")

    def _load(self, key):
        got = self.kept.get(key)
        if got is not None:
            return got
        got = {}
        for path in glob.glob(os.path.join(self.folder, safe(key), "*.jsonl")):
            raw = storewriter.journal(path)
            try:
                with open(path, "rb") as f:
                    raw = f.read() + b"\n" + raw
            except FileNotFoundError:
                pass
            for line in raw.decode("utf-8", "replace").splitlines():
                try:
                    e = json.loads(line)
                    got[(e["series"], e["seq"])] = e
                except (ValueError, KeyError, TypeError):
                    continue
        for path in glob.glob(os.path.join(self.folder, safe(key), "*.jsonl.journal")):
            whole = path[:-len(".journal")]
            if not os.path.exists(whole):
                for line in storewriter.journal(whole).decode("utf-8", "replace").splitlines():
                    try:
                        e = json.loads(line)
                        got[(e["series"], e["seq"])] = e
                    except (ValueError, KeyError, TypeError):
                        continue
        self.kept[key] = got
        return got

    def add(self, key, series, entries):
        key = self.resolve(key)
        if not key or not isinstance(series, int):
            return 0
        new = 0
        with self.lock:
            got = self._load(key)
            for e in entries:
                if not e or (series, e["seq"]) in got:
                    continue
                e = dict(e, series=series)
                got[(series, e["seq"])] = e
                month = month_of(e["t"])
                path = self._path(key, month)
                storewriter.add_later(path, (jsontext.dumps(e) + "\n").encode("utf-8"))
                adds = self.added.setdefault((key, month), 0) + 1
                self.added[(key, month)] = adds
                if adds >= FOLD_EVERY:
                    self.added[(key, month)] = 0
                    lines = [x for x in got.values() if month_of(x["t"]) == month]
                    storewriter.fold_later(path, lambda lines=lines: "".join(
                        jsontext.dumps(x) + "\n" for x in sorted(lines, key=lambda x: (x["series"], x["seq"]))).encode("utf-8"))
                new += 1
            if new:
                self.version += 1
        return new

    def move(self, old, new):
        if not os.path.isdir(os.path.join(self.folder, safe(old))):
            return False
        self._hand(lambda: self._move(old, new))
        return True

    def _move(self, old, new):
        with self.lock:
            entries = list(self._load(old).values())
        for series in {e["series"] for e in entries}:
            self.add(new, series, [e for e in entries if e["series"] == series])


    def take(self, key, frame):
        if not key or frame.get("hash") != key_hash(key) or not frame.get("entries"):
            return
        self._hand(lambda: self.add(key, frame["series"], frame["entries"]))

    def _hand(self, job):
        self.inbox.put(job)
        if self.worker is None or not self.worker.is_alive():
            self.worker = start_thread("money record", self.work)

    def work(self, stop=None):
        while not (stop and stop.is_set()):
            try:
                job = self.inbox.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                job()
            except Exception:
                log_error("keeping the money record")

    def drain(self):
        while True:
            try:
                job = self.inbox.get_nowait()
            except queue.Empty:
                return
            job()


    def import_saved(self, table):
        new = 0
        for key, rec in (table or {}).items() if isinstance(table, dict) else ():
            if not isinstance(rec, dict) or not isinstance(key, str):
                continue
            series = rec.get("series")
            series = int(series) if isinstance(series, (int, float)) else None
            entries = [e for e in (parse_kept(x) for x in listed(rec.get("entries"))) if e]
            if series is not None and entries:
                new += self.add(key, series, entries)
        return new

    def saved_files(self, wtf):
        return sorted(glob.glob(os.path.join(wtf, "Account", "*", "SavedVariables", SAVED_NAME)))

    def check_saved(self, wtf):
        new = 0
        for path in self.saved_files(wtf) if wtf else ():
            stamp = store.stamp(path)
            if stamp is None or self.saved_seen.get(path) == stamp:
                continue
            self.saved_seen[path] = stamp
            db = savedvars.read(path).get("IndexOfAzerothDB")
            if isinstance(db, dict) and isinstance(db.get("ledger"), dict):
                new += self.import_saved(db["ledger"])
        return new

    def watch_saved(self, wtf_dir, log_error, stop=None, every=SAVED_EVERY):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.check_saved(wtf_dir())
            except Exception:
                log_error("reading the money record from the SavedVariables")
            stop.wait(every)


    def entries(self, key):
        with self.lock:
            got = list(self._load(self.resolve(key)).values())
        return sorted(got, key=lambda e: (e["t"], e["series"], e["seq"]))

    def purse(self, key):
        entries = self.entries(key)
        mails = {(e["series"], e["seq"]): e for e in entries if e.get("kind") == MAILED}
        changes = [change_of(e, mails) for e in entries if "kind" not in e]
        return {"changes": changes, "times": [x["t"] for x in changes],
                "seen": sorted({datetime.date.fromtimestamp(x["t"]).isoformat() for x in changes})}


class LedgerFirst:

    def __init__(self, ledger, earlier):
        self.ledger = ledger
        self.earlier = earlier

    def book(self, key):
        later = self.ledger.purse(key)
        before = self.earlier.book(key) if self.earlier else {"changes": [], "times": [], "seen": []}
        if not later["changes"]:
            return before
        seam = later["changes"][0]["t"]
        kept = [x for x in before["changes"] if x["t"] < seam]
        changes = list(later["changes"])
        first = changes[0]
        if kept and first["d"] == 0 and first["c"] != kept[-1]["c"]:
            d = first["c"] - kept[-1]["c"]
            changes[0] = dict(first, d=d, parts={"unexplained": d}, unseen=True, why="unseen")
        changes = kept + changes
        return {**{k: before[k] for k in ("spans", "deaths", "places") if k in before},
                "changes": changes, "times": [x["t"] for x in changes], "seam": seam,
                "seen": sorted(set(before["seen"]) | set(later["seen"]))}
