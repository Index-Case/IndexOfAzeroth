# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import contextlib
import datetime
import glob
import gzip
import json
import os
import re
import threading
import time
import zlib

import arrays
from characters import key_named, names_char
import gamelogs
import jsontext
import mainstores
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(ROOT, "data", "replay")
THIN_YARDS = 3.0
THIN_TURN = 0.35
THIN_EVERY = 15.0
READ_MOST = 4 << 20
KILL_AFTER = 120
FIGHT_TAIL = 4.0
SETTLE = 60
OWNERS_KEPT = 200
PACK_QUIET = 3600
EVERY = 2
AXES_PAIR = 2.0
AXES_MOST = 15
AXES_LEAST = 3
FIGURES = 2
READ_RULES = 2
AMOUNTS = ("a", "ok", "oh", "cr")
COMBAT_LOGS, CHAT_LOGS = "WoWCombatLog*.txt", "WoWChatLog*.txt"
LOG_NAMED = re.compile(r"WoWCombatLog-(\d\d)(\d\d)(\d\d)_(\d\d)(\d\d)(\d\d)\.txt$", re.I)
LOG_SLACK = 10
GROUP_CHANNELS = {"to", "whisper", "party", "raid", "guild", "officer"}
STILL_SPEED = 0.8
MOUNT_SPEED = 9.5
PACE_JOIN = 30
VENDOR_BIT = 32
INDOORS_BIT = 64
SYSTEM_KEPT = re.compile(r"^(Quest accepted: |.+ completed\.$|Congratulations, you have reached |.+ has challenged you to a duel)")
DAMAGE = gamelogs.DAMAGE
JOINING = ".joining"


def safe(key):
    return re.sub(r"[^\w .-]", "_", key or "").strip() or "_"


def day_of(t):
    return datetime.date.fromtimestamp(t).isoformat()


def is_day(name):
    try:
        return datetime.date.fromisoformat(name).isoformat() == name
    except (TypeError, ValueError):
        return False


def day_file(name):
    day, _, kind = name.partition(".")
    return day if kind in ("jsonl", "jsonl.gz") and is_day(day) else None


def unpacked(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return b""
    try:
        return gzip.decompress(data)
    except (OSError, EOFError, zlib.error):
        arrays.set_aside(path)
        return b""


def day_start(day):
    return time.mktime(datetime.date.fromisoformat(day).timetuple())


def merge_spans(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


class DayRecord:
    BY_KEY = ("last", "zone", "inside", "vendor", "coins", "leads")

    def __init__(self, folder=FOLDER, logs_dir=None, open_map=None, world=None, chars=None, now=time.time):
        self.folder = folder
        self.logs_dir = logs_dir or (lambda: None)
        self.open_map = open_map or (lambda m: False)
        self.world = world or (lambda m, x, y: None)
        self.chars = chars or (lambda: {})
        self.now = now
        self.lock = threading.Lock()
        self.buffer = []
        self.last = {}
        self.zone = {}
        self.inside = {}
        self.vendor = {}
        self.coins = {}
        self.leads = {}
        self.hit = {}
        self.where = {}
        self.carry = {}
        self.read_to = 0.0
        self.caught_up = False
        self.sizes = {}
        self.moves = []
        self.moved_tail = False
        self.state = store.load_json(self._tail_path(), {})
        self.state.setdefault("files", {})
        self.state.setdefault("owners", [])
        self.state.setdefault("logs", {})
        self.state.pop("began", None)
        if not self.state["files"]:
            self.state.setdefault("read", READ_RULES)
        self.uncovered = set()
        self.reports = None
        self.spell_levels = None

    def _tail_path(self):
        return os.path.join(self.folder, "tail.json")


    def _owner_at(self, t):
        key = None
        for at, k in self.state["owners"]:
            if at <= t:
                key = k
            else:
                break
        return key

    def _owner(self, key, t):
        owners = self.state["owners"]
        if owners and owners[-1][1] == key:
            return
        owners.append([t, key])
        owners.sort(key=lambda o: o[0])
        del owners[:-OWNERS_KEPT]

    def _key_for(self, name, guid=None):
        return key_named(self.chars(), name, guid)

    def move(self, old, new):
        rename = lambda k: new if k == old else k
        with self.lock:
            self.buffer = [(rename(k), ev) for k, ev in self.buffer]
            owners = self.state["owners"]
            if any(k == old for _, k in owners):
                self.state["owners"] = [[t, rename(k)] for t, k in owners]
                self.moved_tail = True
            for name in self.BY_KEY:
                held = getattr(self, name)
                if old in held:
                    held[new] = held.pop(old)
            self.hit = {g: (t, rename(k)) for g, (t, k) in self.hit.items()}
            self.sizes = {(rename(k), day): n for (k, day), n in self.sizes.items()}
            self.uncovered = {(rename(k), *rest) for k, *rest in self.uncovered}
            self.moves.append((old, new))

    def _move_days(self, old, new):
        src, dest = os.path.join(self.folder, safe(old)), os.path.join(self.folder, safe(new))
        if src == dest or not os.path.isdir(src):
            return
        mainstores.refuse_write(dest)
        if not os.path.exists(dest):
            os.replace(src, dest)
            return
        while names := sorted(os.listdir(src), key=lambda n: not n.endswith(JOINING)):
            name = names[0]
            here = os.path.join(src, name)
            there = os.path.join(dest, name[:-len(JOINING)] if name.endswith(JOINING) else name)
            if not os.path.exists(there):
                os.replace(here, there)
                continue
            if not name.endswith(JOINING):
                os.replace(here, here + JOINING)
                here += JOINING
            if there.endswith(".gz"):
                store.write_bytes(there, gzip.compress(unpacked(there) + unpacked(here), 9))
            else:
                with open(here, "rb") as b, open(there, "ab") as a:
                    a.write(b.read())
            with contextlib.suppress(FileNotFoundError):
                os.remove(here)
        os.rmdir(src)


    def position(self, key, state, now=None):
        if not key or not isinstance(state, dict):
            return
        now = now or self.now()
        fl = state.get("flags") or {}
        vendor = bool((state.get("act") or {}).get("vendor"))
        indoors = bool((state.get("minimap") or {}).get("indoors"))
        bits = (1 if fl.get("combat") else 0) | (2 if fl.get("ghost") else 0) | (4 if fl.get("taxi") else 0) \
            | (8 if fl.get("dead") else 0) | (16 if fl.get("resting") else 0) | (VENDOR_BIT if vendor else 0) \
            | (INDOORS_BIT if indoors else 0)
        pos, m = state.get("pos"), state.get("map")
        speed = state.get("speed")
        speed = speed if isinstance(speed, (int, float)) and not isinstance(speed, bool) else None
        pace = None if speed is None else 0 if speed < STILL_SPEED else 1 if speed < MOUNT_SPEED else 2
        with self.lock:
            self._owner(key, now)
            self.vendor[key] = vendor
            last = self.last.get(key)
            zone = (state.get("zone") or "", state.get("subzone") or "")
            if zone != self.zone.get(key) and zone[0]:
                self.zone[key] = zone
                self.buffer.append((key, {"t": round(now, 2), "k": "z", "zone": zone[0], "sub": zone[1]}))
            kind = (state.get("instance") or {}).get("kind")
            if kind != self.inside.get(key, None):
                if kind or key in self.inside:
                    self.buffer.append((key, {"t": round(now, 2), "k": "i", **({"kind": kind} if kind else {})}))
                self.inside[key] = kind
            if not pos or not m:
                if last and not last.get("gone"):
                    self.last[key] = {"t": now, "gone": True}
                    self.buffer.append((key, {"t": round(now, 2), "k": "g"}))
                return
            f = state.get("facing")
            wp = self.world(m, pos["x"], pos["y"])
            if last and not last.get("gone") and last["m"] == m and last["fl"] == bits and last.get("pace") == pace \
                    and now - last["t"] < THIN_EVERY:
                moved = ((wp[1] - last["wp"][1]) ** 2 + (wp[2] - last["wp"][2]) ** 2) ** 0.5 \
                    if wp and last.get("wp") else abs(pos["x"] - last["x"]) * 1000 + abs(pos["y"] - last["y"]) * 1000
                turned = abs(((f or 0) - (last.get("f") or 0) + 3.14159) % 6.28318 - 3.14159) if f is not None else 0
                if moved < THIN_YARDS and turned < THIN_TURN:
                    return
            self.last[key] = {"t": now, "m": m, "x": pos["x"], "y": pos["y"], "f": f, "fl": bits, "wp": wp, "pace": pace}
            ev = {"t": round(now, 2), "k": "p", "m": m, "x": round(pos["x"], 5), "y": round(pos["y"], 5)}
            if f is not None:
                ev["f"] = round(f, 2)
            if bits:
                ev["fl"] = bits
            if speed is not None:
                ev["s"] = round(speed, 1)
            self.buffer.append((key, ev))

    def money(self, key, copper, now=None):
        if not key or not isinstance(copper, int) or isinstance(copper, bool) or copper < 0:
            return
        now = now or self.now()
        with self.lock:
            was = self.coins.get(key)
            if was == copper:
                return
            self.coins[key] = copper
            ev = {"t": round(now, 2), "k": "$", "c": copper}
            if was is not None:
                ev["d"] = copper - was
            if self.vendor.get(key):
                ev["v"] = 1
            self.buffer.append((key, ev))

    @staticmethod
    def lead_of(report):
        if not isinstance(report, dict) or not report.get("running"):
            return {}
        out = {"plan": report.get("plan"), "v": report.get("version"), "step": report.get("cur")}
        if report.get("handIn"):
            out["hand"] = report["handIn"]
        chore = next((c for c in report.get("chores") or () if c.get("lead")), None)
        if chore:
            out["chore"] = {"what": chore.get("what"), "npc": chore.get("npc")}
        reason = report.get("reason")
        if reason:
            out["why"] = reason.get("key")
            if reason.get("other"):
                out["other"] = reason["other"]
        return out

    def lead(self, key, report, now=None):
        if not key:
            return
        now = now or self.now()
        led, day = self.lead_of(report), day_of(now)
        with self.lock:
            if self.leads.get(key) == (led, day):
                return
            self.leads[key] = (led, day)
            self.buffer.append((key, {"t": round(now, 2), "k": "l", **led}))


    def _read(self, path, size):
        name = os.path.basename(path)
        off = self.state["files"].get(name, 0)
        if size < off:
            off, self.carry[name] = 0, ""
        if size <= off:
            return [], True
        with open(path, "rb") as f:
            f.seek(off)
            data = f.read(min(size - off, READ_MOST))
        cut = data.rfind(b"\n")
        if cut < 0:
            return [], size - off <= READ_MOST
        self.state["files"][name] = off + cut + 1
        text = data[:cut + 1].decode("utf-8", "replace")
        return text.splitlines(), off + cut + 1 >= size

    def reread(self, folder):
        self.flush()
        with self.lock:
            files = dict(self.state["files"])
        found, spans, hits, where = {}, [], {}, {}
        for _, path, _ in self._files(folder, COMBAT_LOGS):
            upto = files.get(os.path.basename(path))
            if not upto:
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read(upto)
            except OSError:
                continue
            first = last = None
            for line in data.decode("utf-8", "replace").splitlines():
                got = gamelogs.stamp(line, self.now())
                if not got:
                    continue
                t, rest = got
                first, last = t if first is None else first, t
                ev = gamelogs.combat(rest)
                if not ev:
                    continue
                with self.lock:
                    kept = self._combat_event(t, ev, hits, where, learn=False)
                if kept:
                    found.setdefault((safe(kept[0]), day_of(t)), []).append(kept[1])
            if first is not None:
                spans.append((first, last))
        days = set(found)
        for path in glob.glob(os.path.join(self.folder, "*", "*.jsonl*")):
            day = day_file(os.path.basename(path))
            if day:
                days.add((os.path.basename(os.path.dirname(path)), day))
        for folder_name, day in sorted(days):
            evs = []
            for e in self.day(folder_name, day):
                if e.get("k") == "c":
                    if any(a <= e["t"] <= b for a, b in spans):
                        continue
                    for k in AMOUNTS:
                        e.pop(k, None)
                evs.append(e)
            evs += found.get((folder_name, day), [])
            self._write_day(folder_name, day, sorted(evs, key=lambda e: e.get("t", 0)))
        with self.lock:
            self.state["read"] = READ_RULES
            tail = jsontext.dumps(self.state).encode("utf-8")
        store.write_bytes(self._tail_path(), tail)

    def _write_day(self, key, day, events):
        packed = day < day_of(self.now())
        path, other = self._path(key, day, packed), self._path(key, day, not packed)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = "".join(jsontext.dumps(e) + "\n" for e in events).encode("utf-8")
        store.write_bytes(path, gzip.compress(data, 9) if packed else data)
        if os.path.exists(other):
            mainstores.refuse_write(other)
            os.remove(other)

    def _log_read(self, name, lines):
        if LOG_NAMED.search(name) or name in self.state["logs"]:
            return
        for line in lines:
            got = gamelogs.stamp(line, self.now())
            if got:
                with self.lock:
                    self.state["logs"][name] = got[0]
                return

    def _log_begins(self):
        out = []
        for name in self.state["files"]:
            m = LOG_NAMED.search(name)
            if m:
                mon, day, yy, hh, mm, ss = (int(x) for x in m.groups())
                out.append(time.mktime((2000 + yy, mon, day, hh, mm, ss, 0, 0, -1)))
            elif name in self.state["logs"]:
                out.append(self.state["logs"][name])
        return sorted(out)

    def _files(self, folder, pattern):
        paths = glob.glob(os.path.join(folder, pattern))
        try:
            return sorted(((os.path.getmtime(p), p, os.path.getsize(p)) for p in paths), key=lambda x: x[0])
        except OSError:
            return []

    def poll(self):
        folder = self.logs_dir()
        came, ends = False, True
        if folder and os.path.isdir(folder):
            if self.state.get("read") != READ_RULES:
                self.reread(folder)
            for pattern, take in ((COMBAT_LOGS, self.combat_line), (CHAT_LOGS, self.chat_line)):
                for _, path, size in self._files(folder, pattern):
                    try:
                        lines, end = self._read(path, size)
                    except OSError:
                        continue
                    ends = ends and end
                    if pattern == COMBAT_LOGS:
                        self._log_read(os.path.basename(path), lines)
                    for line in lines:
                        came = take(line) or came
        self.caught_up = ends
        self.flush()
        self.fill_reports()
        return came

    def combat_line(self, line):
        got = gamelogs.stamp(line, self.now())
        if not got:
            return False
        t, rest = got
        ev = gamelogs.combat(rest)
        if not ev:
            return False
        with self.lock:
            self.read_to = max(self.read_to, t)
            got = self._combat_event(t, ev, self.hit, self.where, learn=True)
            if got:
                self.buffer.append(got)
        return bool(got)

    def _combat_event(self, t, ev, hits, where, learn):
        if learn:
            for name, guid, flags in ((ev["sn"], ev["sg"], ev["sf"]), (ev["dn"], ev["dg"], ev["df"])):
                if gamelogs.is_me(flags):
                    key = self._key_for(name, guid)
                    if key:
                        self._owner(key, t)
                    break
        key = self._owner_at(t)
        mine_s, mine_d = gamelogs.mine(ev["sf"]), gamelogs.mine(ev["df"])
        if ev["e"] in DAMAGE or ev["e"] in gamelogs.MISSED:
            if mine_s and not mine_d and ev["dg"]:
                hits[ev["dg"]] = (t, key)
            elif mine_d and not mine_s and ev["sg"]:
                hits[ev["sg"]] = (t, key)
        if ev["e"] == "UNIT_DIED" and not mine_d:
            hit = hits.pop(ev["dg"], None)
            if not hit or t - hit[0] > KILL_AFTER:
                return None
            key = hit[1] or key
            ev["kill"] = 1
        elif not (mine_s or mine_d):
            return None
        if not key:
            return None
        info = ev.pop("info", None)
        if info:
            pos = info["pos"]
            if self.open_map(pos[0]):
                ev["ig"], ev["w"] = info["guid"], pos
                where[info["guid"]] = pos
        if ev["e"] in ("UNIT_DIED", "PARTY_KILL") and ev["dg"] in where:
            ev["w"] = where.pop(ev["dg"])
        for k in ("sg", "sn", "dg", "dn", "sp", "spn"):
            if ev.get(k) in ("", None, "0000000000000000", "nil"):
                ev.pop(k, None)
        if not ev.get("sf"):
            ev.pop("sf", None)
        if not ev.get("df"):
            ev.pop("df", None)
        if len(hits) > 2000:
            for g in [g for g, h in hits.items() if t - h[0] > KILL_AFTER]:
                del hits[g]
        if len(where) > 5000:
            where.clear()
        return key, {"t": t, "k": "c", **ev}

    def chat_line(self, line):
        got = gamelogs.stamp(line, self.now())
        if not got:
            return False
        t, rest = got
        c = gamelogs.chat(rest)
        with self.lock:
            key = self._owner_at(t)
            if not key:
                return False
            me = self.chars().get(key) or {}
            mine = names_char(me, c.get("who"))
            named = not mine and gamelogs.mentions(c["text"], me.get("name"))
            if c["ch"] == "system":
                text = c["text"]
                if not (named or text.startswith("You ") or text.startswith("Your ") or SYSTEM_KEPT.match(text)):
                    return False
            elif c["ch"] not in GROUP_CHANNELS and not (mine or named):
                return False
            ev = {"t": t, "k": "m", **{k: v for k, v in c.items() if v is not None}}
            if named:
                ev["at"] = 1
            self.buffer.append((key, ev))
        return True


    def _path(self, key, day, packed=False):
        return os.path.join(self.folder, safe(key), day + (".jsonl.gz" if packed else ".jsonl"))

    def flush(self):
        with self.lock:
            todo, self.buffer = self.buffer, []
            moves, self.moves = self.moves, []
            moved, self.moved_tail = self.moved_tail, False
            tail = jsontext.dumps(self.state).encode("utf-8")
        moving, kept, refused = [], [], None
        for old, new in moves:
            try:
                self._move_days(old, new)
            except OSError as e:
                moving.append((old, new))
                refused = refused or e
        by = {}
        for key, ev in todo:
            by.setdefault((key, day_of(ev["t"])), []).append(ev)
        for (key, day), evs in by.items():
            path = self._path(key, day)
            mainstores.refuse_write(path)
            data = "".join(jsontext.dumps(e) + "\n" for e in evs).encode("utf-8")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "ab") as f:
                    f.write(data)
            except OSError as e:
                kept += [(key, ev) for ev in evs]
                refused = refused or e
                continue
            self.sizes[(key, day)] = self.sizes.get((key, day), 0) + len(data)
        if kept or moving:
            with self.lock:
                renamed = dict(self.moves)
                self.buffer[:0] = [(renamed.get(k, k), ev) for k, ev in kept]
                self.moves[:0] = moving
                self.moved_tail = self.moved_tail or (moved and bool(kept))
        if not kept and (todo or moved or not os.path.exists(self._tail_path())):
            os.makedirs(self.folder, exist_ok=True)
            store.write_bytes(self._tail_path(), tail)
        if refused:
            raise refused

    def pack(self, now=None):
        now = now or self.now()
        today, packed = day_of(now), 0
        for path in glob.glob(os.path.join(self.folder, "*", "*.jsonl")):
            day = os.path.basename(path)[:-6]
            try:
                if day >= today or now - os.path.getmtime(path) < PACK_QUIET:
                    continue
                with open(path, "rb") as f:
                    loose = f.read()
                gz = path + ".gz"
                store.write_bytes(gz, gzip.compress(unpacked(gz) + loose, 9))
                os.remove(path)
                packed += 1
            except OSError:
                continue
        return packed

    def day(self, key, day):
        raw = b""
        packed, loose = self._path(key, day, True), self._path(key, day)
        try:
            raw += unpacked(packed)
            if os.path.exists(loose):
                with open(loose, "rb") as f:
                    raw += f.read()
        except OSError:
            pass
        out = []
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        out.sort(key=lambda e: e.get("t", 0))
        return out


    @staticmethod
    def me_of(events):
        for e in events:
            if e.get("k") != "c":
                continue
            if gamelogs.is_me(e.get("sf", 0)) and e.get("sg"):
                return e["sg"]
            if gamelogs.is_me(e.get("df", 0)) and e.get("dg"):
                return e["dg"]
        return None

    def axes(self, events, me=None):
        me = me or self.me_of(events)
        strip = [e for e in events if e.get("k") == "p"]
        pairs, j = [], 0
        for e in events:
            if e.get("k") != "c" or e.get("ig") != me or not e.get("w") or not strip:
                continue
            while j + 1 < len(strip) and abs(strip[j + 1]["t"] - e["t"]) <= abs(strip[j]["t"] - e["t"]):
                j += 1
            p = strip[j]
            if abs(p["t"] - e["t"]) > AXES_PAIR or p.get("m") != e["w"][0]:
                continue
            got = self.world(p["m"], p["x"], p["y"])
            if got:
                pairs.append(((got[1], got[2]), (e["w"][1], e["w"][2])))
        if len(pairs) >= AXES_LEAST:
            best = None
            for swap in (False, True):
                for a in (1, -1):
                    for b in (1, -1):
                        errs = sorted(((n - a * (y if swap else x)) ** 2 + (w - b * (x if swap else y)) ** 2) ** 0.5
                                      for (n, w), (x, y) in pairs)
                        mid = errs[len(errs) // 2]
                        if best is None or mid < best[0]:
                            best = (mid, [swap, a, b])
            if best[0] <= AXES_MOST:
                with self.lock:
                    self.state["axes"] = best[1]
                return tuple(best[1])
        got = self.state.get("axes")
        return tuple(got) if got else None

    def view(self, key, day):
        events = self.day(key, day)
        me = self.me_of(events)
        ax = self.axes(events, me)
        if ax:
            swap, a, b = ax
            for e in events:
                w = e.get("w")
                if e.get("k") != "c" or not w:
                    continue
                inst = (self.world(w[0], 0.5, 0.5) or (None,))[0]
                if inst is None:
                    continue
                x, y = w[1], w[2]
                e["at"] = [inst, round(a * (y if swap else x), 1), round(b * (x if swap else y), 1), w[3]]
        self.paces(events)
        return {"events": events, "me": me, "placed": bool(ax)}

    def paces(self, events):
        prev, prev_w = None, None
        for e in events:
            k = e.get("k")
            if k == "g":
                prev = None
                continue
            if k != "p":
                continue
            w = self.world(e.get("m"), e.get("x"), e.get("y"))
            if prev is not None and "s" not in prev and prev_w and w and prev_w[0] == w[0] and prev.get("m") == e.get("m"):
                dt = e["t"] - prev["t"]
                if 0 < dt <= PACE_JOIN:
                    prev["v"] = round(((w[1] - prev_w[1]) ** 2 + (w[2] - prev_w[2]) ** 2) ** 0.5 / dt, 1)
            prev, prev_w = e, w
        return events

    def days(self, key):
        out = {}
        for path in glob.glob(os.path.join(self.folder, safe(key), "*.jsonl*")):
            day = day_file(os.path.basename(path))
            if not day:
                continue
            out[day] = out.get(day, 0) + os.path.getsize(path)
        return [{"day": d, "bytes": out[d]} for d in sorted(out)]

    def between(self, key, since, until):
        out, d = [], datetime.date.fromtimestamp(since)
        end = datetime.date.fromtimestamp(until)
        while d <= end:
            out.extend(e for e in self.day(key, d.isoformat()) if since <= e.get("t", 0) <= until)
            d += datetime.timedelta(days=1)
        return out


    @staticmethod
    def kills_in(events):
        seen, out = set(), []
        for e in events:
            if e.get("k") != "c" or not (e.get("kill") or (e["e"] == "PARTY_KILL" and gamelogs.mine(e.get("sf", 0)))):
                continue
            guid = e.get("dg")
            if not guid or guid in seen or gamelogs.mine(e.get("df", 0)):
                continue
            seen.add(guid)
            out.append({"t": e["t"], "guid": guid, "npc": gamelogs.npc_of(guid), "name": e.get("dn"), "w": e.get("w")})
        return out

    def kills(self, key, since, until):
        return self.kills_in(self.between(key, since, until))

    @staticmethod
    def strip_fights(events, until):
        spans, start = [], None
        for e in events:
            if e.get("k") == "p":
                fighting = bool((e.get("fl") or 0) & 1)
                if fighting and start is None:
                    start = e["t"]
                elif not fighting and start is not None:
                    spans.append((start, e["t"]))
                    start = None
            elif e.get("k") == "g" and start is not None:
                spans.append((start, e["t"]))
                start = None
        if start is not None:
            spans.append((start, until))
        return spans

    def covered(self, key, since, until):
        with self.lock:
            begins = self._log_begins()
        if not begins or begins[0] > since + LOG_SLACK:
            return False
        evs = self.between(key, since, until)
        lines = [e["t"] for e in evs if e.get("k") == "c"]
        for a, b in self.strip_fights(evs, until):
            i = bisect.bisect_left(lines, a - LOG_SLACK)
            if i == len(lines) or lines[i] > b + LOG_SLACK:
                return False
        return True

    def figures(self, key, since, until, spell_levels=None):
        evs = self.between(key, since, until)
        deaths, dealt, taken, last_death, casts = 0, 0, 0, -1e9, {}
        spans = self.strip_fights(evs, until)
        for e in evs:
            if e.get("k") != "c":
                continue
            sf, df, a = e.get("sf", 0), e.get("df", 0), e.get("a")
            if e["e"] in DAMAGE:
                if gamelogs.mine(sf) and not gamelogs.mine(df):
                    dealt = None if dealt is None or a is None else dealt + a
                    spans.append((e["t"], e["t"] + FIGHT_TAIL))
                elif gamelogs.is_me(df) and not gamelogs.mine(sf):
                    taken = None if taken is None or a is None else taken + a
                    spans.append((e["t"], e["t"] + FIGHT_TAIL))
            elif e["e"] == "UNIT_DIED" and gamelogs.is_me(df) and e["t"] - last_death > 2:
                deaths, last_death = deaths + 1, e["t"]
            elif e["e"] == "SPELL_CAST_SUCCESS" and gamelogs.is_me(sf) and e.get("spn"):
                c = casts.setdefault(e["spn"], {"name": e["spn"], "id": e.get("sp"), "casts": 0, "first": e["t"]})
                c["casts"] += 1
        fighting = sum(min(b, until) - max(a, since) for a, b in merge_spans(spans) if min(b, until) > max(a, since))
        spell = None
        pick = [c for c in casts.values() if spell_levels is None or c["name"] in spell_levels]
        if pick:
            best = max(pick, key=lambda c: (c["casts"], -c["first"]))
            spell = {"name": best["name"], "id": best["id"], "casts": best["casts"],
                     "level": (spell_levels or {}).get(best["name"])}
        return {"kills": len(self.kills_in(evs)), "deaths": deaths, "dealt": dealt, "taken": taken,
                "fighting": round(fighting), "spell": spell}

    def counting(self, key):
        if not self.reports or not self.logs_dir():
            return set()
        return {level for level, since, until in self.reports.wanting(key, FIGURES)
                if (key, level, since, until) not in self.uncovered}

    def fill_reports(self, now=None):
        if not self.reports or self.state.get("read") != READ_RULES:
            return 0
        now, done = now or self.now(), 0
        with self.lock:
            read_to, caught_up = self.read_to, self.caught_up
        for key in self.reports.characters():
            for level, since, until in self.reports.wanting(key, FIGURES):
                if not (read_to >= until + 2 or (caught_up and now - until >= SETTLE)) \
                        or (key, level, since, until) in self.uncovered:
                    continue
                if not self.covered(key, since, until):
                    self.uncovered.add((key, level, since, until))
                    continue
                levels = self.spell_levels(key) if self.spell_levels else None
                self.reports.set_figures(key, level, self.figures(key, since, until, levels), FIGURES)
                done += 1
        return done

    def watch(self, stop=None, every=EVERY, log_error=None):
        packed_at = 0
        while not (stop and stop.is_set()):
            try:
                self.poll()
                if self.now() - packed_at > 3600:
                    self.pack()
                    packed_at = self.now()
            except Exception:
                if log_error:
                    log_error("the day's recording")
            if stop:
                stop.wait(every)
            else:
                time.sleep(every)
