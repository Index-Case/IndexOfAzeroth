# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import copy
import math
import os
import threading
import time
from collections import Counter

from geo import MapGeometry
import datafiles
import moblevels
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "respawns.json")
WORLD = os.path.join(ROOT, "data", "world.json")
STATE = os.path.join(ROOT, "data", "kills.json")
SEEN = os.path.join(ROOT, "data", "respawns_seen.json")
OBJECTIVES = os.path.join(ROOT, "data", "objectives.json")
QUEST_WINDOW = (30, 90)
QUEST_MEASURED = 3
MATCH_YARDS = 150
FALLBACK = 300
SHOW_UP = 180
MAX_TIMERS = 300
COMMON_NEARBY = 3
COMMON_YARDS = 400
COMMON_SEEN = 2
COMMON_KILLS = 2
COMMON_WINDOW = 15 * 60
RARE_RANKS = (2, 4)
WATCH_YARDS = 40
TIGHT_SECONDS = 5
MIN_RESPAWN = 10
KEEP_SEEN = 10
TIGHT_LAST = 5
LIVES_SECONDS = 600
LIVES_YARDS = 150


def load_data():
    try:
        d = datafiles.load(DATA, {})
        npcs, spawns = {int(k): v for k, v in d["npcs"].items()}, {int(k): v for k, v in d["spawns"].items()}
        groups = {int(k): v for k, v in d.get("groups", {}).items()}
    except (ValueError, KeyError, AttributeError, TypeError):
        npcs, spawns, groups = {}, {}, {}
    world = datafiles.load(WORLD, {})
    if not world:
        return npcs, spawns, groups
    geo = MapGeometry()
    mobs = world.get("mobs", {})
    for key, areas in world.get("mobSpawns", {}).items():
        npc = int(key)
        if npc in spawns:
            continue
        pts = [[w[2], round(w[0], 1), round(w[1], 1), None, None]
               for area, points in areas.items() for w in (geo.area_to_world(area, x, y) for x, y in points) if w]
        if pts:
            spawns[npc] = pts
            if key in mobs:
                npcs.setdefault(npc, [mobs[key][0], mobs[key][3], None])
    return npcs, spawns, groups


def load_critters():
    try:
        return {int(i) for i in (datafiles.load(DATA, {}) or {}).get("critters") or ()}
    except (ValueError, TypeError, AttributeError):
        return set()


def load_names():
    d = store.load_json(OBJECTIVES, {}) or {}
    out = {}
    for k, v in (d.get("npcs") or {}).items():
        if isinstance(v, dict) and v.get("n") and str(k).isdigit():
            out[int(k)] = v["n"]
    return out


def load_quest_targets():
    d = store.load_json(OBJECTIVES, {}) or {}
    quests, items = d.get("quests") or {}, d.get("items") or {}
    out = set()
    for q in quests.values():
        out.update(int(c) for c in q.get("c") or [])
        for item in q.get("i") or []:
            out.update(int(n) for n in (items.get(str(item)) or {}).get("d") or [])
    return out


class Respawns:

    def __init__(self, realm_now=None):
        self.lock = threading.Lock()
        self.npcs, self.spawns, self.groups = load_data()
        self.quest_targets = load_quest_targets()
        self.critters, self.names = load_critters(), load_names()
        self.realm_now = realm_now or (lambda: "")
        self.kept = self.load()
        self.realm = ""
        self.timers = self.kept.pop("", [])
        self.version = 0
        self.seen = {}
        self.recent = {}
        self.measured = store.load_json(SEEN, {})
        self.watching = {}
        self.backs_seen = {}
        self.away = {}

    def reload(self):
        self.npcs, self.spawns, self.groups = load_data()
        self.quest_targets = load_quest_targets()
        self.critters, self.names = load_critters(), load_names()

    def name_of(self, k):
        info = self.npcs.get(k["npc"])
        return k.get("name") or (info[0] if info else None) or self.names.get(k["npc"])

    def load(self):
        kept = store.load_json(STATE, {})
        if isinstance(kept, list):
            kept = {"realms": {"": kept}}
        realms = kept.get("realms") if isinstance(kept, dict) else None
        out = {}
        for r, ts in realms.items() if isinstance(realms, dict) else ():
            if isinstance(ts, list):
                out[str(r)] = [t for t in ts if isinstance(t, dict)]
        for timers in out.values():
            for t in timers:
                t.setdefault("levels", moblevels.of(t.get("npc")))
        return out

    def sync(self):
        realm = self.realm_now() or ""
        with self.lock:
            return self._use(realm)

    def _use(self, realm):
        if not realm or realm == self.realm:
            return False
        if self.realm:
            self.kept[self.realm] = self.timers
            self.away[self.realm] = (self.seen, self.recent, self.watching, self.backs_seen)
            self.timers = []
            self.seen, self.recent, self.watching, self.backs_seen = self.away.pop(realm, ({}, {}, {}, {}))
        ids = {t.get("id") for t in self.timers}
        self.timers = [t for t in self.kept.pop(realm, []) if t.get("id") not in ids] + self.timers
        self.realm = realm
        self.version += 1
        self.save()
        return True

    def save(self):
        storewriter.save_json_later(STATE, {"realms": {**self.kept, self.realm: self.timers}}, indent=None)

    def note(self, kills, now=None, zone=None):
        now = now or time.time()
        self.sync()
        added = False
        with self.lock:
            known = {t["id"] for t in self.timers}
            self.seen = {key: s for key, s in self.seen.items() if now - s[0] < 3600}
            for k in kills:
                key = f"{k['npc']}-{k['spawn']}"
                if key in known or key in self.seen:
                    continue
                pos = k.get("pos")
                if not pos:
                    continue
                died = now - k.get("age", 0)
                self.seen[key] = [died, k["map"], pos[0], pos[1]]
                if k["npc"] in self.critters or not self.name_of(k) or self.common(k, pos, died):
                    before = len(self.timers)
                    self.timers = [t for t in self.timers if t["npc"] != k["npc"]]
                    added |= len(self.timers) != before
                    continue
                timer = self.place(k, pos, died, now)
                if zone:
                    timer["zone"] = zone
                self.timers.append(timer)
                known.add(key)
                added = True
            if added:
                self.prune(now)
                self.save()
                self.version += 1
        return added

    def common(self, k, pos, died):
        info = self.npcs.get(k["npc"])
        if info and info[1] in RARE_RANKS:
            return False
        near = [s for s in self.spawns.get(k["npc"], []) if s[0] == k["map"] and math.hypot(s[1] - pos[0], s[2] - pos[1]) < COMMON_YARDS]
        mobs = sum(1 for s in near if len(s) < 6)
        grouped = Counter(s[5] for s in near if len(s) > 5)
        mobs += sum(min(n, self.groups.get(g, n)) for g, n in grouped.items())
        if mobs >= COMMON_NEARBY:
            return True
        alone = mobs == 1 and near[0][3] is not None
        if not alone and (k.get("others") or 0) - self.lives(k, pos, died) >= COMMON_SEEN:
            return True
        if near:
            return False
        times = [t for t in self.recent.get(k["npc"], []) if died - t < COMMON_WINDOW] + [died]
        self.recent[k["npc"]] = times
        return len(times) >= COMMON_KILLS

    def lives(self, k, pos, died):
        prefix = f"{k['npc']}-"
        return sum(1 for key, (t, m, north, west, ended) in self.backs_seen.items()
                   if ended and key.startswith(prefix) and 0 <= died - t <= LIVES_SECONDS and m == k["map"]
                   and north is not None and math.hypot(north - pos[0], west - pos[1]) < LIVES_YARDS)

    def place(self, k, pos, died, now):
        info = self.npcs.get(k["npc"])
        name = self.name_of(k)
        busy = {(t["map"], t["x"], t["y"]) for t in self.timers if t["npc"] == k["npc"] and t["died"] + t["max"] > now}
        best, best_d = None, MATCH_YARDS
        for s in self.spawns.get(k["npc"], []):
            if s[0] != k["map"] or (s[0], s[1], s[2]) in busy:
                continue
            d = math.hypot(s[1] - pos[0], s[2] - pos[1])
            if d < best_d:
                best, best_d = s, d
        base = {"id": f"{k['npc']}-{k['spawn']}", "npc": k["npc"], "name": name, "map": k["map"], "died": round(died, 1),
                "rare": bool(info and info[1] in (2, 4)),
                "levels": moblevels.choose(moblevels.of(k["npc"]), moblevels.span(k.get("level")))}
        typical = (info[2] if info else None) or FALLBACK
        if best:
            timer = {**base, "x": best[1], "y": best[2], "min": best[3] or typical, "max": best[4] or typical, "guess": False,
                     "est": best[3] is None}
        else:
            timer = {**base, "x": round(pos[0], 1), "y": round(pos[1], 1), "min": typical, "max": typical, "guess": True}
        if k["npc"] in self.quest_targets and not base["rare"]:
            soon, late = self.quest_window()
            if timer["guess"] or timer.get("est"):
                timer.update(min=soon, max=late, est=True)
            else:
                timer.update(min=min(timer["min"], soon), est=True)
        lo, hi, tight = self.time_seen(k["npc"])
        if tight:
            timer.update(min=lo, max=hi, est=False, measured=True)
        elif lo is not None and lo < timer["max"]:
            timer.update(min=min(timer["min"], lo), max=lo)
        return timer

    def quest_window(self):
        times = sorted(s for npc, obs in self.measured.items() if npc.isdigit() and int(npc) in self.quest_targets
                       for s, tight in obs[-TIGHT_LAST:] if tight)
        if len(times) < QUEST_MEASURED:
            return QUEST_WINDOW
        if len(times) >= 8:
            return times[len(times) // 4], times[(3 * len(times)) // 4]
        return times[0], times[-1]

    def time_seen(self, npc):
        obs = self.measured.get(str(npc)) or []
        tight = [s for s, ok in obs if ok][-TIGHT_LAST:]
        if tight:
            return min(tight), max(tight), True
        if obs:
            first = min(s for s, _ in obs)
            return first, first, False
        return None, None, False

    def watch(self, here, now=None):
        now = now or time.time()
        self.sync()
        with self.lock:
            for t in self.timers:
                if t["map"] == here[0] and math.hypot(t["x"] - here[1], t["y"] - here[2]) < WATCH_YARDS:
                    self.watching.setdefault(t["id"], now)
                else:
                    self.watching.pop(t["id"], None)

    def note_backs(self, backs, now=None):
        now = now or time.time()
        self.sync()
        changed = False
        with self.lock:
            self.backs_seen = {key: s for key, s in self.backs_seen.items() if now - s[0] < 3600}
            for b in backs:
                key = f"{b['npc']}-{b['spawn']}"
                if key in self.backs_seen:
                    continue
                at, pos = now - b.get("age", 0), b.get("pos")
                self.backs_seen[key] = [at, b.get("map"), *(pos or (None, None)), False]
                runs = [t for t in self.timers if t["npc"] == b["npc"] and not t.get("back") and t["died"] + MIN_RESPAWN < at
                        and (not pos or t["map"] == b["map"] and math.hypot(t["x"] - pos[0], t["y"] - pos[1]) < MATCH_YARDS)]
                if not runs:
                    self.backs_seen[key][4] = bool(pos) and any(
                        other.startswith(f"{b['npc']}-") and m == b["map"] and MIN_RESPAWN <= at - died <= LIVES_SECONDS
                        and math.hypot(north - pos[0], west - pos[1]) < LIVES_YARDS
                        for other, (died, m, north, west) in self.seen.items())
                    continue
                t = max(runs, key=lambda t: t["died"])
                took = round(at - t["died"])
                since = self.watching.get(t["id"])
                tight = since is not None and at - since >= TIGHT_SECONDS
                obs = self.measured.setdefault(str(b["npc"]), [])
                obs.append([took, tight])
                del obs[:-KEEP_SEEN]
                t.update(back=round(at, 1), min=took, max=took)
                self.backs_seen[key][4] = True
                changed = True
            if changed:
                self.save()
                storewriter.save_json_later(SEEN, self.measured, indent=None)
                self.version += 1
        return changed

    def prune(self, now):
        self.timers = [t for t in self.timers if t["died"] + t["max"] + SHOW_UP > now][-MAX_TIMERS:]

    def forget(self, timer_id):
        self.sync()
        with self.lock:
            before = len(self.timers)
            self.timers = [t for t in self.timers if t["id"] != timer_id]
            if len(self.timers) != before:
                self.save()
                self.version += 1

    def current(self, now=None):
        now = now or time.time()
        self.sync()
        with self.lock:
            before = len(self.timers)
            self.prune(now)
            if len(self.timers) != before:
                self.save()
                self.version += 1
            return copy.deepcopy(self.timers)
