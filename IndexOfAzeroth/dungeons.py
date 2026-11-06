# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import copy
import datetime
import os
import re
import threading
import time

from epic import for_side
from facts import MAX_LEVEL
from layers import kill_xp
from serverlog import log_error
import mainstores
import moblevels
import opendungeons
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "dungeons.json")
OPEN = os.path.join(ROOT, "data", "open_dungeons.json")
PORTRAITS = os.path.join(ROOT, "data", "portraits.json")
RUNS = os.path.join(ROOT, "data", "runs.json")
WISH = os.path.join(ROOT, "data", "wishlist.json")
CAP_WINDOW = 3600
MAX_RUNS = 50
MAX_STARS = 40


load_json = store.load_json


EPIC_ABOVE = 2
DETAIL_LISTS = ("quests", "bosses", "trash", "floors", "chain", "entrances")
SUMMED = ("key", "name", "kind", "instance", "levels", "zone", "location", "card", "floors", "gameLevel", "opens", "later",
          "wayIn", "coming", "where", "players", "levelsElsewhere", "brackets",
          "entrances")
KINDS = {"dungeon": "Dungeon", "raid": "Raid", "battleground": "Battleground"}


def place_key(name):
    name = re.sub(r"^(lower|upper) ", "", (name or "").lower().split(":")[0])
    return re.sub(r"[^a-z0-9]", "", name.replace("the ", ""))


def opened(run):
    return run.get("open", run["inside"])


def opening(day, today=None):
    if not day or day <= (today or datetime.date.today().isoformat()):
        return ""
    d = datetime.date.fromisoformat(day)
    return f"opens {d.day} {d.strftime('%b')}"


class Dungeons:
    def __init__(self):
        data = load_json(DATA, {"dungeons": [], "floors": {}, "items": {}})
        self.list = data["dungeons"]
        self.coming, self.battlegrounds = data.get("coming", []), data.get("battlegrounds", [])
        self.more_by_key = {d["key"]: d for d in self.coming + self.battlegrounds}
        self.floors = data["floors"]
        self.items = data["items"]
        self.chain = {int(k): v for k, v in data.get("chainQuests", {}).items()}
        maps = load_json(mainstores.standing(os.path.join(ROOT, "data", "dungeonmaps.json")), {"maps": {}})
        high = maps.get("maps") or {}
        for f in self.floors.values():
            h = high.get(str(f["instance"]))
            if h:
                f["high"] = {"world": h["world"], "v": maps.get("built", "")}
        baked = load_json(mainstores.standing(os.path.join(ROOT, "data", "dungeonbake.json")), {"floors": {}})
        for f in self.floors.values():
            b = (baked.get("floors") or {}).get(str(f["instance"]))
            if f.get("tilesOnly") and b and b.get("outdoors"):
                f["baked"] = {"world": b["world"], "v": b["print"]}
        self.by_key = {d["key"]: d for d in self.list}
        faces = load_json(PORTRAITS, {})
        self.npc_faces = {int(k): v for k, v in (faces.get("npc") or {}).items()}
        self.giver_faces = faces.get("giver") or {}
        self.lock = threading.Lock()
        self.runs = load_json(RUNS, {"runs": [], "entries": []})
        kept = load_json(WISH, {})
        self.stars = {k: {"items": list(v.get("items") or []), "merged": bool(v.get("merged"))}
                      for k, v in (kept.get("chars") or {}).items()}
        self.unclaimed = list(kept.get("items") or [])
        self.last_run = None
        self.open_seen, self.open_state = None, {}


    def open_now(self):
        try:
            seen = os.stat(OPEN).st_mtime_ns
        except OSError:
            seen = None
        if seen != self.open_seen:
            self.open_state = opendungeons.resolve(load_json(OPEN, {"posts": {}}), self.list) if seen else {}
            self.open_seen = seen
        return self.open_state

    def open_words(self, key):
        s = self.open_now().get(key)
        if not s:
            return {}
        if not s["open"]:
            return {"notOpen": True}
        return {k: v for k, v in {"openFrom": s.get("from"),
                                  "openLevels": [s["from"], s["to"]] if s.get("from") and s.get("to") else None}.items() if v}

    def face(self, giver=None, npc=None):
        if npc is not None:
            return self.npc_faces.get(int(npc))
        if giver and not giver.get("item"):
            return self.giver_faces.get(f"{giver['name']}|{giver.get('map') or ''}")
        return None

    def xp_run(self, d, level, share, cap=MAX_LEVEL):
        return round(sum(kill_xp(level, int(lv), cap) * share(level, int(lv)) * sum(counts)
                         for lv, counts in (d.get("mobs") or {}).items()))

    def summary(self, level=0, share=None, cap=MAX_LEVEL):
        def summed(d):
            return {k: d.get(k) for k in SUMMED[:9]} | {k: d[k] for k in SUMMED[9:] if k in d}
        out = []
        for i, d in enumerate(self.list, 1):
            out.append(summed(d) | self.open_words(d["key"]) | {"index": i, "bosses": len(d.get("bosses", [])),
                                    "quests": [{"side": q["side"], "classes": q.get("classes")} for q in d.get("quests", [])],
                                    "loot": sorted({i for b in d.get("bosses", []) for i in b["loot"]}),
                                    "xpRun": self.xp_run(d, level, share, cap) if level and share and d.get("mobs") else None})
        for d in self.coming:
            out.append(summed(d) | {"index": None, "bosses": 0, "quests": [], "loot": []})
        for d in self.battlegrounds:
            out.append(summed(d) | {"index": None, "bosses": 0, "quests": [], "loot": [],
                                    "entranceCount": len(d.get("entrances") or []),
                                    "battlemasterCount": len(d.get("battlemasters") or [])})
        return sorted(out, key=lambda d: (list(KINDS).index(d["kind"]) if d["kind"] in KINDS else 9,
                                          (d.get("levels") or [99, 99])[1], d["name"]))

    def entrance_words(self, name, kind, today=None):
        places = [d for d in self.list + self.battlegrounds if d["kind"] == kind and place_key(d["name"]) == place_key(name)]
        word = KINDS.get(kind, kind.title())
        if not places:
            return f"{word}, not in Forever's first raid release" if kind == "raid" else word
        low, high = min(d["levels"][1] for d in places), max(d["levels"][2] for d in places)
        words = f"{word}, " + (f"levels {low}-{high}" if low != high else f"level {low}")
        game = sorted({d["gameLevel"] for d in places if d.get("gameLevel")})
        if game:
            words += f" (Forever's own data gives level {' or '.join(str(g) for g in game)})"
        opens = next((w for w in (opening(d.get("opens"), today) for d in places) if w), "")
        if all(self.open_words(d["key"]).get("notOpen") for d in places):
            words += ", not open yet"
        elif opens:
            words += f", {opens}"
        elif any(d.get("later") for d in places):
            words += ", not in Forever's first raid release"
        way = next((d["wayIn"] for d in places if d.get("wayIn")), None)
        return f"{words}. Way in: {way}" if way else words

    def ways_in_beside(self, names):
        known = {place_key(n) for n in names}
        return [{"name": d["name"], "kind": d["kind"], "map": e["map"], "x": e["x"], "y": e["y"],
                 "sub": self.entrance_words(d["name"], d["kind"]), "described": bool(e.get("described"))}
                for d in self.list if place_key(d["name"]) not in known for e in d.get("entrances") or ()]

    def detail(self, key, book=None):
        d = self.by_key.get(key)
        if not d:
            more = self.more_by_key.get(key)
            return more and {**more, **{k: more.get(k) or [] for k in DETAIL_LISTS}, "index": None, "items": {},
                             "floorInfo": {}, "epicFrom": {}}
        ids = {i for b in d.get("bosses") or [] for i in b.get("loot") or []} | set(d.get("trash") or [])
        for q in d.get("quests") or []:
            ids |= set(q.get("rewards", {}).get("choice", [])) | set(q.get("rewards", {}).get("items", []))
        lists = {k: d.get(k) or [] for k in DETAIL_LISTS}
        paid = {q["id"]: (book or {}).get(q["id"], {}).get("xp") for q in lists["quests"]}
        lists["quests"] = [{**q, "rewards": {**(q.get("rewards") or {}), "xp": paid[q["id"]]}} if paid[q["id"]] else q
                           for q in lists["quests"]]
        lists["bosses"] = [{**b, "levels": moblevels.game(b.get("npc"), moblevels.span(b.get("minLevel") or b.get("level"), b.get("level"))
                                                         or moblevels.of_data(b.get("npc")))} for b in lists["bosses"]]
        return {**d, **lists, **self.open_words(key), "index": self.list.index(d) + 1, "items": {str(i): self.items[str(i)] for i in ids if str(i) in self.items},
                "floorInfo": {f: self.floors[f] for f in d.get("floors", []) if f in self.floors},
                "epicFrom": {side: self.epic_from(d, side) for side in ("Alliance", "Horde")}}

    def epic_from(self, d, side):
        by_id = {k: for_side(q, side) for k, q in {**self.chain, **{q["id"]: q for q in d.get("quests", [])}}.items()}
        seen, low = set(), None
        todo = [by_id[q["id"]] for q in d.get("quests", []) if by_id[q["id"]].get("side") in (None, "Both", side)]
        while todo:
            q = todo.pop()
            if q["id"] in seen or q.get("side") not in (None, "Both", side):
                continue
            seen.add(q["id"])
            if not q.get("classes"):
                opens = max(q.get("req") or 1, (q.get("level") or 0) - EPIC_ABOVE)
                low = opens if low is None else min(low, opens)
            todo += [by_id[p] for p in q.get("preAll", []) + q.get("preAny", []) if p in by_id]
        return low


    def note_run(self, run):
        now = time.time()
        with self.lock:
            entries = [t for t in self.runs["entries"] if now - t < CAP_WINDOW]
            for minutes in run["entries"]:
                t = now - minutes * 60
                if not any(abs(t - e) < 150 for e in entries):
                    entries.append(t)
            entries.sort()
            changed = entries != self.runs["entries"]
            self.runs["entries"] = entries
            prev = self.last_run
            if prev and opened(prev) and prev["key"] and (not opened(run) or run["key"] != prev["key"]):
                d = self.by_key.get(prev["key"], {})
                also = {k: v for k, v in (prev.get("also") or {}).items() if v}
                bosses = len(d.get("bosses", [])) + sum(len(self.by_key.get(k, {}).get("bosses", [])) for k in also)
                self.runs["runs"].insert(0, {"key": prev["key"], "name": d.get("name", prev["key"]), "ended": round(now),
                                             "seconds": prev["seconds"], "deaths": prev["deaths"], "xp": prev["xp"],
                                             "money": prev["money"], "kills": len(prev["kills"]) + sum(map(len, also.values())),
                                             "bosses": bosses, "loot": prev["loot"]})
                del self.runs["runs"][MAX_RUNS:]
                changed = True
            self.last_run = run
            if changed:
                storewriter.save_json_later(RUNS, self.runs)

    def cap(self):
        now = time.time()
        with self.lock:
            return [round((now - t) / 60) for t in self.runs["entries"] if now - t < CAP_WINDOW]

    def run_log(self):
        with self.lock:
            return {"runs": copy.deepcopy(self.runs["runs"]), "cap": self.cap_unlocked()}

    def cap_unlocked(self):
        now = time.time()
        return [round((now - t) / 60) for t in self.runs["entries"] if now - t < CAP_WINDOW]


    def stars_of(self, char):
        if not char:
            return None
        with self.lock:
            return list((self.stars.get(char) or {}).get("items") or [])

    def move(self, old, new):
        if not old or not new or old == new:
            return False
        with self.lock:
            had = self.stars.pop(old, None)
            if had is None:
                return False
            entry = self.stars.setdefault(new, {"items": [], "merged": False})
            entry["items"] = sorted(set(entry["items"]) | set(had.get("items") or []))[:MAX_STARS]
            entry["merged"] = entry["merged"] or bool(had.get("merged"))
            self.save_stars()
            return True

    def toggle_wish(self, char, item):
        if not char:
            return None
        with self.lock:
            entry = self.stars.setdefault(char, {"items": [], "merged": False})
            items = set(entry["items"]) ^ {item}
            if len(items) > MAX_STARS:
                return None
            entry["items"] = sorted(items)
            self.save_stars()
            return list(entry["items"])

    def merge_wish(self, char, items):
        with self.lock:
            entry = self.stars.setdefault(char, {"items": [], "merged": False})
            if entry["merged"]:
                return False
            entry["items"] = sorted(set(entry["items"]) | set(items) | set(self.unclaimed))[:MAX_STARS]
            entry["merged"], self.unclaimed = True, []
            self.save_stars()
            return True

    def shared_stars(self):
        with self.lock:
            return {k: list(v["items"]) for k, v in sorted(self.stars.items()) if v["merged"]}

    def save_stars(self):
        storewriter.save_json_later(WISH, {"chars": self.stars, **({"items": self.unclaimed} if self.unclaimed else {})})


_sharing = threading.Lock()


def share_stars(hub):
    if not getattr(hub, "shared", None):
        return
    with _sharing:
        try:
            hub.shared.set_stars(hub.dungeons.shared_stars())
        except OSError:
            log_error("writing the starred loot into Shared.lua")
