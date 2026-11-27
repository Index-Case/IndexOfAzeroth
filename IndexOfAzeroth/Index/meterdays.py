# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import os
import subprocess
import threading
import time

import conditions
import dayrecord
from dayrecord import DayRecord
import game
import meter
from pvp import your_level
import store
import workers

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "data", "meter")
TOOL = os.path.abspath(__file__)
WHAT = "damage meter history"
CHECK_EVERY = 60.0
TODAY_EVERY = 600.0
START_GAP = 30.0
LATE = 10.0
FIGHTS_MOST = 3000
FORM = 5
DETAIL = ("sp", "up", "en")
FRESH_MOST = 2000
FOLLOWED = {"c", "p", "g"} | meter.PLACE_KINDS
SPARSE = ("multi", "ttk", "dg", "boss")
ELITE_RANKS = (1, 2, 3)
WEAPON_SLOTS = (16, 17, 18)
SETUP_KINDS = ("gear", "spells", "talents", "ranks")


def day_path(folder, key, day):
    return os.path.join(folder, dayrecord.safe(key), day + ".json")


def summary(f):
    span = max(0.0, f["end"] - f["t"])
    return {"t": round(f["t"], 2), "len": round(span, 1), "dmg": f["dmg"], "dps": round(f["dmg"] / max(span, 1.0), 1),
            "taken": f["on"]["d"], "heal": f["heal"], "name": f["foe"], "kills": f["kills"], "act": f["act"],
            "group": f["group"], "died": f["died"], "ne": len(f["en"]), "multi": f["multi"], "main": f["main"],
            "ttk": f["ttk"], "zn": f["zone"] if f["inst"] else None}


def spelled(f):
    whole = set(f.get("whole") or ())
    held = conditions.held(f["up"], f["end"] - f["t"])
    return {**summary(f), **({"cd": held} if held else {}),
            "sp": [[r.get("id"), r.get("n"), r.get("by"), r["d"], r["cs"], r["h"], r["c"], sum(r["m"].values()), r["tk"],
                    [[a, *v] for a, v in sorted((r.get("u") or {}).items())], r["nt"], r["vl"], r["vh"]] for r in f["sp"]],
            "up": [[a["id"], a["n"], a["s"], a["x"], 1 if a["id"] in whole else 0, a["y"]] for a in f["up"]],
            "en": f["en"]}


def compact(f):
    out = {k: v for k, v in f.items() if k not in DETAIL and k != "zn" and not (k in SPARSE and v in (None, False))}
    if not f.get("multi"):
        out.pop("main", None)
    return out


def _bounds(since, until):
    return float("-inf") if since is None else since, float("inf") if until is None else until


def current(kept, stamp):
    return bool(kept) and kept.get("stamp") == stamp and kept.get("form") == FORM and kept.get("cond") == conditions.made()


def build_day(record, key, day, now=None):
    now = now or time.time()
    stamp = record.stamp(key, day)
    cond = conditions.made()
    events = record.day(key, day)
    until = min(now, dayrecord.day_start(day) + 86400)
    fights = meter.Walk(events, until).more()
    fights = [f for f in fights if f["end"] < now - LATE]
    setups = [{k: v for k, v in e.items() if k != "k"} for e in events if e.get("k") == "s"]
    return {"stamp": stamp, "form": FORM, "cond": cond, "built": round(now), "fights": [spelled(f) for f in fights], "setups": setups}


def build(record, folder=STORE, now=time.time, say=print):
    jobs = []
    for key in record.characters():
        for d in record.days(key):
            if not current(store.load_json(day_path(folder, key, d["day"]), None), record.stamp(key, d["day"])):
                jobs.append((d["day"], key))
    for day, key in sorted(jobs, reverse=True):
        store.save_json(day_path(folder, key, day), build_day(record, key, day, now()), indent=None)
    if jobs:
        say(f"{WHAT}: {len(jobs)} day{'s' if len(jobs) != 1 else ''} built")
    return len(jobs)


def main(say=print):
    with workers.turn(WHAT, ROOT, say=say):
        build(DayRecord(), say=say)
    return 0


def setup_at(kinds, t):
    def last(kind):
        times, evs = kinds.get(kind, ((), ()))
        i = bisect.bisect_left(times, t)
        return evs[i - 1] if i else None
    gear, talents = last("gear"), last("talents")
    items = gear and gear.get("items")
    return {"gear": items, "weapons": [items[s - 1] if s <= len(items) else None for s in WEAPON_SLOTS] if items else None,
            "talents": talents and talents.get("points")}


def marks(reports, setups):
    out = [{"t": r["at"], "kind": "level", "level": r.get("level"), "from": r.get("from")}
           for r in reports or () if isinstance(r.get("at"), (int, float))]
    was = {}
    for e in setups:
        kind, before = e.get("w"), was.get(e.get("w"))
        if kind not in SETUP_KINDS:
            continue
        was[kind] = e
        if before is None:
            continue
        if kind == "gear":
            a, b = before.get("items") or [], e.get("items") or []
            n = max(len(a), len(b))
            a, b = a + [0] * (n - len(a)), b + [0] * (n - len(b))
            slots = [{"slot": i + 1, "was": a[i], "now": b[i]} for i in range(n) if a[i] != b[i]]
            if slots:
                out.append({"t": e["t"], "kind": "gear", "slots": slots,
                            "weapon": any(s["slot"] in WEAPON_SLOTS for s in slots)})
        elif kind == "spells":
            a, b = set(before.get("ids") or ()), set(e.get("ids") or ())
            if a != b:
                out.append({"t": e["t"], "kind": "spell", "learned": sorted(b - a), "lost": sorted(a - b)})
        elif kind == "talents" and before.get("points") != e.get("points"):
            out.append({"t": e["t"], "kind": "talent", "points": e.get("points"), "was": before.get("points")})
        elif kind == "ranks":
            a, b = before.get("ranks") or {}, e.get("ranks") or {}
            changed = {n: [a.get(n, 0), b.get(n, 0)] for n in sorted(set(a) | set(b)) if a.get(n, 0) != b.get(n, 0)}
            if changed:
                out.append({"t": e["t"], "kind": "talent", "ranks": changed})
    return sorted(out, key=lambda m: m["t"])


def opened(f):
    return {**summary(f), "cd": conditions.held(f["up"], f["end"] - f["t"]),
            "end": round(f["end"], 2), "burst": f["burst"], "unknown": f["unknown"], "line": f["ps"],
            "spells": [{"id": r.get("id"), "name": r.get("n"), "by": r.get("by"), "dmg": r["d"], "casts": r["cs"],
                        "hits": r["h"], "crits": r["c"], "ticks": r["tk"], "misses": sum(r["m"].values()),
                        "miss": r["m"], "lo": r["lo"], "hi": r["hi"], "ok": r["ok"], "foes": r["nt"],
                        "volleys": r["vl"], "blows": r["vh"]} for r in f["sp"]],
            "enemies": [{"npc": e[0], "name": e[1], "dmg": e[2], "died": e[3]} for e in f["en"]],
            "up": [{"id": a["id"], "name": a["n"], "secs": a["s"], "times": a["x"]} for a in f["up"]],
            "down": [{"id": a["id"], "name": a["n"], "secs": a["s"], "times": a["x"]} for a in f["down"]]}


class MeterDays:
    def __init__(self, record, reports=None, folder=STORE, popen=subprocess.Popen, queue=workers.queue,
                 clock=time.time, log_error=None, place=None, rank=None):
        self.record, self.reports, self.folder = record, reports, folder
        self.place, self.rank = place or (lambda zone: None), rank or (lambda npc: None)
        self.popen, self.queue, self.clock, self.log_error = popen, queue, clock, log_error
        self.lock = threading.Lock()
        self.kept = {}
        self.follow = {}
        self.events = (None, [])
        self.proc = None
        self.started = float("-inf")
        self.looked = float("-inf")
        self.failed = False


    def stored(self, key, day):
        path = day_path(self.folder, key, day)
        st = store.stamp(path)
        with self.lock:
            kept = self.kept.get((key, day))
        if kept and kept[0] == st:
            return kept[1]
        got = store.load_json(path, None) if st else None
        with self.lock:
            self.kept[(key, day)] = (st, got)
        return got

    def _todo(self, key, now):
        today, todo, due = dayrecord.day_of(now), 0, False
        for d in self.record.days(key):
            got = self.stored(key, d["day"])
            if current(got, self.record.stamp(key, d["day"])):
                continue
            if d["day"] != today or not got or got.get("form") != FORM:
                todo, due = todo + 1, True
            elif now - got.get("built", 0) >= TODAY_EVERY and not self.fighting(key):
                due = True
        return todo, due

    def running(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        here = os.path.normcase(ROOT)
        return any(r.get("what") == WHAT and os.path.normcase(r.get("root") or "") == here for r in self.queue())

    def start(self):
        with self.lock:
            now = self.clock()
            if now - self.started < START_GAP:
                return False
            self.started = now
        if self.running():
            return False
        self.proc = self.popen([game.console_python(), TOOL], cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


    def marked(self, f):
        place = self.place(f.get("zn")) if f.get("zn") else None
        bosses = place["bosses"] if place else ()
        return {"dg": place["name"] if place else None, "boss": any(e[0] in bosses for e in f.get("en") or ())}

    def foe_kind(self, npc, place):
        if place and npc in place["bosses"]:
            return "boss"
        return "elite" if self.rank(npc) in ELITE_RANKS else None


    def _guarded(self, work, *args):
        try:
            return work(*args)
        except Exception:
            if not self.failed and self.log_error:
                self.log_error("the meter's history")
            self.failed = True
            return False

    def take(self, written):
        return self._guarded(self._take, written)

    def update(self):
        return self._guarded(self._update)

    def _take(self, written):
        with self.lock:
            for key, evs in written:
                f = self.follow.setdefault(key, {"events": [], "ready": False, "fresh": [], "closed": float("-inf"),
                                                 "where": self.record_where(key)})
                f["events"] += [e for e in evs if e.get("k") in FOLLOWED and e.get("t", 0) > f["closed"]]
        return True

    def record_where(self, key):
        zone = (getattr(self.record, "zone", {}).get(key) or ("",))[0]
        return {"zone": zone or None, "inst": getattr(self.record, "inside", {}).get(key)}

    def _update(self):
        now = self.clock()
        with self.lock:
            for f in self.follow.values():
                self._close(f, now)
        if now - self.looked >= CHECK_EVERY:
            self.looked = now
            if any(self._todo(key, now)[1] for key in self.record.characters()):
                self.start()
        self.failed = False
        return True

    @staticmethod
    def _spans(f, now):
        f["events"].sort(key=lambda e: e.get("t", 0))
        spans = DayRecord.fight_spans(f["events"], now)
        return spans, bool(spans) and spans[-1][1] >= now - LATE

    def _close(self, f, now):
        if not f["events"]:
            return
        spans, still = self._spans(f, now)
        closed = spans[:-1] if still else spans
        if not f["ready"]:
            if not still:
                f["where"] = meter.placed(f["where"], f["events"])
                f["ready"], f["events"], f["closed"] = True, [], now - LATE
            return
        for start, end in closed:
            where = meter.placed(f["where"], [e for e in f["events"] if e.get("t", 0) <= start])
            got = meter.breakdown(f["events"], start, end, where=where)
            if any(map(meter.struck, got["sp"])):
                f["fresh"].append(spelled(got))
        del f["fresh"][:-FRESH_MOST]
        if closed:
            f["closed"] = closed[-1][1]
        keep = f["closed"] if still else max(f["closed"], now - LATE)
        f["where"] = meter.placed(f["where"], [e for e in f["events"] if e.get("t", 0) <= keep])
        f["events"] = [e for e in f["events"] if e.get("t", 0) > keep]

    def fighting(self, key, live=None):
        if ((self.record.last.get(key) or {}).get("fl") or 0) & 1:
            return True
        return (live or self.now(key)) is not None

    def now(self, key):
        now = self.clock()
        with self.lock:
            f = self.follow.get(key)
            if not f or not f["ready"] or not f["events"]:
                return None
            spans, still = self._spans(f, now)
            if not still:
                return None
            start = spans[-1][0]
            dmg = meter.breakdown(f["events"], start, now)["dmg"]
        return {"t": round(start, 2), "dps": round(dmg / max(now - start, 1.0), 1)}


    def answer(self, key, since=None, until=None):
        since, until = _bounds(since, until)
        todo, fights, setups, picked = self._history(key, since, until)
        kinds = {}
        for e in setups:
            got = kinds.setdefault(e.get("w"), ([], []))
            got[0].append(e["t"])
            got[1].append(e)
        reports = self.reports.of(key) if self.reports else []
        rows = [{**compact({**f, **self.marked(f)}), "lvl": your_level(reports, f["t"]), **setup_at(kinds, f["t"])}
                for f in picked[-FIGHTS_MOST:]]
        live = self.now(key)
        return {"char": key, "building": todo, "fighting": self.fighting(key, live),
                "last": {"t": fights[-1]["t"], "dps": fights[-1]["dps"]} if fights else None, "now": live,
                "fights": rows, "cut": max(0, len(picked) - FIGHTS_MOST),
                "events": [m for m in marks(reports, setups) if since <= m["t"] <= until]}

    def _history(self, key, since, until):
        todo, due = self._todo(key, self.clock())
        if due:
            self.start()
        fights, setups = [], []
        for d in self.record.days(key):
            got = self.stored(key, d["day"]) or {}
            fights += got.get("fights") or []
            setups += got.get("setups") or []
        fights.sort(key=lambda f: f["t"])
        end = fights[-1]["t"] + fights[-1]["len"] if fights else float("-inf")
        with self.lock:
            fights += [f for f in (self.follow.get(key) or {}).get("fresh", ()) if f["t"] > end]
        setups.sort(key=lambda e: e["t"])
        return todo, fights, setups, [f for f in fights if since <= f["t"] <= until]

    def spells(self, key, since=None, until=None):
        todo, _, _, picked = self._history(key, *_bounds(since, until))
        spells, auras = {}, {}

        def place(table, k):
            return table.setdefault(k, len(table))

        rows = []
        for f in picked[-FIGHTS_MOST:]:
            sp, up = f.get("sp"), f.get("up")
            if sp is None or up is None:
                rows.append([f["t"], f["len"], f["dmg"], f["dps"], None, None])
                continue
            named = {a[0]: a[1] for a in up}
            rows.append([f["t"], f["len"], f["dmg"], f["dps"],
                         [[place(spells, (r[0], r[1], r[2])), *r[3:9], [[place(auras, (s[0], named.get(s[0]))), *s[1:]]
                                                                       for s in r[9]], *r[10:13]] for r in sp],
                         [[place(auras, (a[0], a[1])), *a[2:]] for a in up]])
        return {"char": key, "building": todo, "cut": max(0, len(picked) - FIGHTS_MOST),
                "spells": [list(k) for k in spells], "auras": [list(k) for k in auras], "fights": rows}

    def fight(self, key, t):
        day = dayrecord.day_of(t)
        stamp = (key, day, self.record.stamp(key, day))
        with self.lock:
            kept = self.events
        events = kept[1] if kept[0] == stamp else self.record.day(key, day)
        with self.lock:
            self.events = (stamp, events)
        walk = meter.Walk(events, min(self.clock(), dayrecord.day_start(day) + 86400))
        while not walk.done:
            got = walk.more(1, since=t)
            if got:
                return self._opened(got[0]) if abs(got[0]["t"] - t) <= 1 else None
        return None

    def _opened(self, f):
        out = opened(f)
        zn = out.pop("zn")
        place = self.place(zn) if zn else None
        for e in out["enemies"]:
            e["kind"] = self.foe_kind(e["npc"], place)
        return {**out, **self.marked({"zn": zn, "en": f["en"]})}


if __name__ == "__main__":
    raise SystemExit(main())
