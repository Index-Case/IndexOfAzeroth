# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import operator
import os
import re
import threading
import time

import conditions
import gamelogs
import meter
import moblevels
from pending import addon_folder, lua_string, write_in_place

FILE = "MeterDetail.lua"
HEADER = "-- Written by the Index: your fights by spell, from the game's combat log, read at login or /reload.\n"
FIGHTS_MOST = 500
BYTES_MOST = 256 * 1024
EVERY = 10.0
LINE_MOST = 600
FLOOR = 2 * 3600
LEAD = meter.CARRY_MOST
FREEZE = 900.0
LINES_STEP = 4000
FIGHTS_STEP = 100
FIGHT_BIT = 1
HITS = gamelogs.DAMAGE | gamelogs.MISSED
SPELL_KEYS = {"id", "n", "by", "h", "c", "tk", "d", "lo", "hi", "ok", "m"}
ENEMY_KEYS = {"n", "d", "c"}
ENEMIES_MOST = 12
CLASSIFICATION = {0: "normal", 1: "elite", 2: "rareelite", 3: "worldboss", 4: "rare"}
BY_TIME = operator.itemgetter("t")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LUA_WORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in", "local", "nil",
             "not", "or", "repeat", "return", "then", "true", "until", "while"}


def number(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{round(v, 2):g}"


def field(k):
    if isinstance(k, int) and not isinstance(k, bool):
        return f"[{k}]"
    k = str(k)
    return k if NAME.match(k) and k not in LUA_WORDS else f"[{lua_string(k)}]"


def lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, dict):
        return "{" + ",".join(f"{field(k)}={lua(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua(x) for x in v) + "}"
    return number(v)


def enemy(e):
    got = {"n": e[1], "d": e[2], "c": CLASSIFICATION.get(moblevels.rank_of(e[0]))}
    return {k: v for k, v in got.items() if v is not None}


def held(f):
    if "_cd" not in f:
        f["_cd"] = conditions.held(f["up"], f["end"] - f["t"])
    return f["_cd"]


def entry(f, auras=True):
    spells = [{k: v for k, v in r.items() if k in SPELL_KEYS} for r in f["sp"] if meter.struck(r)]
    out = {"t": int(f["t"]), "len": round(f["end"] - f["t"], 1), "dmg": f["dmg"], "ok": f["ok"], "burst": f["burst"],
           "heal": f["heal"], "oh": f["oh"], "on": f["on"], "sp": spells, "ne": len(f["en"]), "en": [enemy(e) for e in f["en"][:ENEMIES_MOST]],
           "cd": [[r[0], r[1], r[2], int(round(r[3])), r[5]] for r in held(f)]}
    if auras:
        out["up"], out["down"] = f["up"], f["down"]
        out["ln"] = ",".join(str(int(round(v))) for v in f.get("ps", ())[:LINE_MOST])
    return out


def row(f, auras=True):
    kept = "_row" if auras else "_bare"
    if kept not in f:
        f[kept] = lua(entry(f, auras))
    return f[kept]


def render(key, fights, class_id=None):
    fights = fights[-FIGHTS_MOST:]
    rows = [row(f) for f in fights]
    own = conditions.reads(class_id)
    words = {**own["words"], **conditions.words([r for f in fights for r in held(f)])}
    reads = f"ench={lua(dict(sorted(own['ench'].items())))}," if own["ench"] else ""
    head = HEADER + (f"IndexOfAzerothMeterDetail = {{char={lua_string(key)},words={lua(dict(sorted(words.items())))},"
                     f"{reads}fights={{\n")
    size = len(head.encode("utf-8")) + 4 + sum(len(r.encode("utf-8")) + 2 for r in rows)
    for i, f in enumerate(fights):
        if size <= BYTES_MOST:
            break
        bare = row(f, auras=False)
        size -= len(rows[i].encode("utf-8")) - len(bare.encode("utf-8"))
        rows[i] = bare
    while rows and size > BYTES_MOST:
        size -= len(rows.pop(0).encode("utf-8")) + 2
    return head + "".join(r + ",\n" for r in rows) + "}}\n"


class MeterFile:
    def __init__(self, record, addons_dir, who, loaded=None, log_error=None, now=time.time, class_id=None):
        self.record, self.addons_dir, self.who, self.now = record, addons_dir, who, now
        self.loaded = loaded or (lambda: None)
        self.class_id = class_id or (lambda: None)
        self.log_error = log_error
        self.lock = threading.Lock()
        self.events = {}
        self.fights = {}
        self.settled = {}
        self.seeds = {}
        self.walks = {}
        self.dirty = set()
        self.wrote_at = 0.0
        self.text = None
        self.failed = False

    def path(self):
        folder = addon_folder(self.addons_dir)
        return folder and os.path.join(folder, FILE)

    def ensure(self):
        path = self.path()
        if path and not os.path.exists(path):
            write_in_place(path, HEADER + "IndexOfAzerothMeterDetail = nil\n")

    def _guarded(self, work, *args):
        try:
            return work(*args)
        except Exception:
            if not self.failed and self.log_error:
                self.log_error("the meter's file")
            self.failed = True
            return False

    def take(self, written):
        return self._guarded(self._take, written)

    def update(self):
        return self._guarded(self._update)

    def _take(self, written):
        with self.lock:
            for key, evs in written:
                if key not in self.events or not evs:
                    continue
                self.events[key] += evs
                if any(e.get("k") == "c" and e["e"] in HITS for e in evs):
                    self.dirty.add(key)
        return True

    def since(self, now):
        loaded = self.loaded()
        return min(loaded, now - FLOOR) if loaded else now - FLOOR

    def _update(self):
        key, now = self.who(), self.now()
        if not key:
            return False
        with self.lock:
            since = self.since(now)
            if key not in self.events:
                self.events[key], self.fights[key] = [], []
                self.seeds[key] = {"lines": self.record.lines_between(key, since - LEAD, now), "at": 0,
                                   "from": since - LEAD, "got": []}
                return False
            seed = self.seeds.get(key)
            if seed:
                return self._read_on(key, seed)
            walk = self.walks.get(key)
            if not walk:
                last = self.record.last.get(key) or {}
                if key not in self.dirty or now - self.wrote_at < EVERY or (last.get("fl") or 0) & FIGHT_BIT:
                    return False
                if not self.path():
                    return False
                settled = self.settled.get(key) or {"n": 0, "t": float("-inf"), "on": None}
                evs = sorted((e for e in self.events[key] if e["t"] > settled["t"]), key=BY_TIME)
                self.events[key] = list(evs)
                self.dirty.discard(key)
                on = settled["on"] and {side: dict(auras) for side, auras in settled["on"].items()}
                self.walks[key] = {"walk": meter.Walk(evs, now, on), "fights": self.fights[key][:settled["n"]],
                                   "newest": evs[-1].get("t", now) if evs else now}
                return False
            if not walk["walk"].done:
                more = walk["walk"].more(FIGHTS_STEP)
                for f in more:
                    row(f)
                walk["fights"] += more
                return False
            del self.walks[key]
            fights = [f for f in walk["fights"] if f["end"] >= since][-FIGHTS_MOST:]
            n = sum(1 for f in fights if f["end"] < walk["newest"] - FREEZE)
            if n:
                self.settled[key] = {"n": n, "t": fights[n - 1]["end"], "on": fights[n - 1]["after"]}
                self.events[key] = [e for e in self.events[key] if e.get("t", 0) > fights[n - 1]["end"]]
            else:
                self.settled.pop(key, None)
            self.fights[key] = fights
            text, path = render(key, fights, self.class_id()), self.path()
            self.wrote_at = now
            if path and text != self.text:
                write_in_place(path, text)
                self.text = text
                self.failed = False
                return True
            return False

    def _read_on(self, key, seed):
        lines, at = seed["lines"], seed["at"]
        for line in lines[at:at + LINES_STEP]:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("t", 0) >= seed["from"]:
                seed["got"].append(e)
        seed["at"] = at + LINES_STEP
        if seed["at"] >= len(lines):
            del self.seeds[key]
            self.events[key] = seed["got"] + self.events[key]
            self.dirty.add(key)
        return False
