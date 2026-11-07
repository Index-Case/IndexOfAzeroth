# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import json
import os
import re
import sys
import threading

import mainstores
import protocol
import store
import suffixes

ROOT = os.path.dirname(os.path.abspath(__file__))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

TIPS = mainstores.path("tooltips")
INDEX = mainstores.path("tooltips.json")
FALLBACK = mainstores.path("tooltips_fallback.json")
SHARD = 1000
TIPS_KEPT = 2000
FILES_KEPT = 40
MISSING = "missing"
NOT_READ = object()


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


SLOT_INV = {"Head": 1, "Neck": 2, "Shoulder": 3, "Shirt": 4, "Chest": 5, "Robe": 20, "Waist": 6, "Legs": 7, "Feet": 8,
            "Wrist": 9, "Hands": 10, "Finger": 11, "Trinket": 12, "One-Hand": 13, "Back": 16, "Two-Hand": 17, "Tabard": 19,
            "Main Hand": 21, "Off Hand": 22, "Held In Off-hand": 23, "Ammo": 24, "Thrown": 25, "Ranged": 15, "Relic": 28}
SLOT_WORD = "|".join(sorted(SLOT_INV, key=len, reverse=True))


def stats_of(tip):
    import build_gear
    text = tip.get("tooltip", "")
    ilvl, need = re.search(r"<!--ilvl-->(\d+)", text), re.search(r"<!--rlvl-->(\d+)", text)
    slot = re.search(rf"<td>({SLOT_WORD})</td>", text) or re.search(rf"<br>({SLOT_WORD})<", text)
    kind = re.search(r"<!--scstart(\d+):(-?\d+)-->", text)
    cls, sub = (int(kind[1]), max(0, int(kind[2]))) if kind else (None, None)
    inv = SLOT_INV.get(slot[1]) if slot else None
    if inv == 22 and (cls, sub) == (4, 6):
        inv = 14
    if inv == 15 and cls == 2 and sub in (3, 18, 19):
        inv = 26
    made_for = re.search(r"Classes: (.*?)</div>", text)
    classes = sum(1 << (int(c) - 1) for c in re.findall(r"class=(\d+)", made_for[1])) if made_for else 0
    skill = NEEDS_SKILL.search(text)
    return {"n": tip.get("name"), "q": tip.get("quality", 1), "il": int(ilvl[1]) if ilvl else 0,
            "slot": slot[1] if slot else None, "st": build_gear.stats(text, None),
            "cls": cls, "sub": sub, "inv": inv, "rl": int(need[1]) if need else 0, "classes": classes or None,
            "sell": sell_price(text), "needs": [skill[1], int(skill[2])] if skill else None}


NEEDS_SKILL = re.compile(r"Requires (?:<a [^>]*>)?([A-Z][A-Za-z' ]*?)(?:</a>)? \((\d+)\)")


COIN_VALUE = {"gold": 10000, "silver": 100, "copper": 1}


def sell_price(text):
    line = re.search(r'class="whtt-sellprice">(.*?)</div>', text)
    if not line:
        return None
    return sum(int(n) * COIN_VALUE[coin] for coin, n in re.findall(r'class="money(gold|silver|copper)">(\d+)<', line[1]))


class ItemTips:
    def __init__(self, kind="item", folder=None, index=None, fallback=None):
        self.kind = kind
        self.folder, self.index, self.fallback = folder or TIPS, index or INDEX, fallback or FALLBACK
        self.lock = threading.Lock()
        self.kept = collections.OrderedDict()
        self.files = collections.OrderedDict()
        self.read = (NOT_READ, frozenset(), {})

    def none(self):
        stamp = (store.stamp(self.index), store.stamp(self.fallback))
        with self.lock:
            if self.read[0] == stamp:
                return self.read[1], self.read[2]
        side = (read_json(self.index) or {}).get(self.kind) or {}
        ids = frozenset(i for i in side.get("none") or () if isinstance(i, int))
        stand = {int(k): v for k, v in ((read_json(self.fallback) or {}).get(self.kind) or {}).items()
                 if str(k).isdigit() and isinstance(v, dict) and v.get("file")}
        with self.lock:
            self.read = (stamp, ids, stand)
            self.kept.clear()
            self.files.clear()
        return ids, stand

    def key_of(self, item_id):
        if self.kind != "item":
            return item_id
        item, bonuses = protocol.split_key(item_id)
        return item_id if item is None else protocol.item_key(item, bonuses)

    def file(self, path):
        with self.lock:
            if path in self.files:
                self.files.move_to_end(path)
                return self.files[path]
        held = read_json(path) or {}
        with self.lock:
            self.files[path] = held
            while len(self.files) > FILES_KEPT:
                self.files.popitem(last=False)
        return held

    def stored(self, oid, stand):
        if oid in stand:
            copy = read_json(os.path.join(self.folder, "kept", stand[oid]["file"]))
            if copy is not None:
                return {"domain": stand[oid].get("domain", "forever"), **copy}
        if not isinstance(oid, int):
            return None
        tip = self.file(os.path.join(self.folder, f"{self.kind}-{oid // SHARD}.json")).get(str(oid))
        return {"domain": "client", **tip} if isinstance(tip, dict) else None

    def tooltip(self, item_id):
        key = self.key_of(item_id)
        if isinstance(key, str) and self.kind == "item" and protocol.split_key(key)[0]:
            return self.suffixed(*protocol.split_key(key))
        none, stand = self.none()
        with self.lock:
            got = self.kept.get(key)
            if got:
                self.kept.move_to_end(key)
                return got["tip"]
        tip = self.stored(key, stand)
        if tip is None:
            return None if key in none else MISSING
        self.keep(key, tip)
        return tip

    def suffixed(self, item_id, bonuses):
        key = protocol.item_key(item_id, bonuses)
        with self.lock:
            got = self.kept.get(key)
            if got:
                self.kept.move_to_end(key)
                return got["tip"]
        base = self.tooltip(item_id)
        if not isinstance(base, dict):
            return base
        tip, whole = suffixes.apply(base, bonuses, stats_of(base)["inv"])
        if not whole:
            return tip or base
        self.keep(key, tip)
        return tip

    def stats(self, item_id):
        key = self.key_of(item_id)
        tip = self.tooltip(key)
        if not tip or tip == MISSING:
            return None
        with self.lock:
            got = self.kept.get(key)
            if got and got["stats"] is not None:
                return got["stats"]
        st = stats_of(tip)
        with self.lock:
            if key in self.kept:
                self.kept[key]["stats"] = st
        return st

    def keep(self, item_id, tip):
        with self.lock:
            self.kept[item_id] = {"tip": tip, "stats": None}
            self.kept.move_to_end(item_id)
            while len(self.kept) > TIPS_KEPT:
                self.kept.popitem(last=False)

    def forget(self):
        with self.lock:
            self.kept.clear()
            self.files.clear()
            self.read = (NOT_READ, frozenset(), {})


def item_tip(item_id, tips=None):
    tip = (tips or _builder_tips()).tooltip(item_id)
    return tip if isinstance(tip, dict) else None


_shared = {}


def _builder_tips():
    if "items" not in _shared:
        _shared["items"] = ItemTips()
    return _shared["items"]
