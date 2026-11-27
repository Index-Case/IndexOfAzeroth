# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import copy
import datetime
import os
import re
import threading
import time

import dungeon_levels
from epic import for_side, needs
from facts import MAX_LEVEL
from layers import kill_xp
from serverlog import log_error
import mainstores
import moblevels
import opendungeons
from questplan import nothing_inside, offered_at
import store
import storewriter
import words

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "dungeons.json")
OPEN = os.path.join(ROOT, "data", "open_dungeons.json")
AREAS = os.path.join(ROOT, "data", "area_sources.json")
PORTRAITS = os.path.join(ROOT, "data", "portraits.json")
RUNS = os.path.join(ROOT, "data", "runs.json")
WISH = os.path.join(ROOT, "data", "wishlist.json")
CAP_WINDOW = 3600
MAX_RUNS = 50
MAX_STARS = 40


load_json = store.load_json


DETAIL_LISTS = ("quests", "bosses", "trash", "floors", "chain", "entrances")
SUMMED = ("key", "name", "kind", "instance", "levels", "zone", "location", "card", "floors", "opens", "later",
          "wayIn", "coming", "where", "players", "levelsElsewhere", "brackets",
          "entrances", "levelsLine")
KINDS = {"dungeon": "Dungeon", "raid": "Raid", "battleground": "Battleground"}


def place_key(name):
    name = re.sub(r"^(lower|upper) ", "", (name or "").lower().split(":")[0])
    return re.sub(r"[^a-z0-9]", "", name.replace("the ", ""))


def level_line(levels):
    if not levels:
        return None
    start, low, high = levels
    if low == high:
        return words.say("page.journal.dungeon.levels.from", {"level": start or "?"})
    if start and start < low:
        return words.say("page.journal.dungeon.levels.open", {"lo": low, "hi": high, "level": start})
    return words.say("page.journal.dungeon.levels.range", {"lo": low, "hi": high})


def home_wing(wings, pos):
    if len(wings) == 1:
        return wings[0]

    def gap(d):
        bosses = [b["pos"] for b in d.get("bosses") or () if b.get("pos")]
        return min((abs(pos[0] - b[0]) + abs(pos[1] - b[1]) + 3 * abs(pos[2] - b[2]) for b in bosses), default=1e9)
    return min(wings, key=gap)


def opened(run):
    return run.get("open", run["inside"])


def today():
    return datetime.date.today().isoformat()


def opening(day, now=None):
    if not day or day <= (now or today()):
        return ""
    d = datetime.date.fromisoformat(day)
    return f"opens {d.day} {d.strftime('%b')}"


def content_spots(d):
    return [b["pos"] for b in d.get("bosses") or () if b.get("pos")] \
        + [p for q in d.get("quests") or () for p in q.get("spots") or ()]


BOSS_LEVELS = os.path.join(ROOT, "data", "dungeon_boss_levels.json")


def boss_levels():
    return {(b["dungeon"], b["boss"]): b["level"] for b in load_json(BOSS_LEVELS, {}).get("bosses") or ()}


INSIDE_GIVERS = os.path.join(ROOT, "data", "dungeon_inside_givers.json")


def inside_givers():
    out = {}
    for g in load_json(INSIDE_GIVERS, {}).get("givers") or ():
        for kind in ("npc", "object"):
            if kind in g:
                out[(kind, g[kind])] = g
    return out


def played_below(d, boxes, recorded=None):
    if any((recorded or {}).get((d["name"], b["name"])) == "below" for b in d.get("bosses") or () if not b.get("pos")):
        return True
    return any(len(p) > 2 and p[2] is not None and all(b[i] <= p[i] <= b[i + 3] for i in range(3))
               for p in content_spots(d) for b in boxes)


class Dungeons:
    def __init__(self):
        data = load_json(DATA, {"dungeons": [], "floors": {}, "items": {}})
        self.list = data["dungeons"]
        self.coming, self.battlegrounds = data.get("coming", []), data.get("battlegrounds", [])
        self.more_by_key = {d["key"]: d for d in self.coming + self.battlegrounds}
        for d in self.list + self.coming + self.battlegrounds:
            d["levelsLine"] = level_line(d.get("levels"))
        self.floors = data["floors"]
        self.items = data["items"]
        self.chain = {int(k): v for k, v in data.get("chainQuests", {}).items()}
        maps = load_json(mainstores.standing(os.path.join(ROOT, "data", "dungeonmaps.json")), {"maps": {}})
        high = maps.get("maps") or {}
        for f in self.floors.values():
            h = high.get(str(f["instance"]))
            if h:
                f["high"] = {"world": h["world"], "v": maps.get("built", ""), "picture": str(f["instance"])}
        self.levels(high, maps.get("built", ""))
        baked = load_json(mainstores.standing(os.path.join(ROOT, "data", "dungeonbake.json")), {"floors": {}})
        for f in self.floors.values():
            b = (baked.get("floors") or {}).get(str(f["instance"]))
            if f.get("tilesOnly") and f.get("level") != "below" and b and b.get("outdoors"):
                f["baked"] = {"world": b["world"], "v": b["print"]}
        self.by_key = {d["key"]: d for d in self.list}
        self.listing = {}
        for d in self.list:
            for q in d.get("quests") or ():
                self.listing.setdefault(q["id"], []).append((d, q))
        self.met = inside_givers()
        self.wings = {}
        for d in self.list:
            self.wings.setdefault(d.get("instance"), []).append(d)
        self.places = {}
        for d in self.list:
            zone = d.get("zone") or d["name"]
            got = self.places.setdefault(place_key(zone), {"name": zone, "bosses": set()})
            got["bosses"] |= {b["npc"] for b in d.get("bosses") or () if b.get("npc")}
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
        self.launch = data.get("launch")
        self.open_seen, self.open_state = {}, {}

    def levels(self, high, built):
        approved, recorded = dungeon_levels.approved(), boss_levels()
        for fid, f in list(self.floors.items()):
            levels = [] if f.get("tilesOnly") or f["instance"] not in approved else sorted(
                (k for k in high if k.startswith(f"{f['instance']}-level")), key=lambda k: int(k.rsplit("level", 1)[1]))
            if len(levels) > 1:
                f.update(name=words.say("page.dungeon.level.whole"))
                parts = [f"{fid}-{k.split('-', 1)[1]}" for k in levels]
                for n, (part, k) in enumerate(zip(parts, levels), 1):
                    self.floors[part] = {**f, "name": words.say("page.dungeon.level.number", {"n": n}), "level": "rooms",
                                         "of": fid, "boxes": high[k]["boxes"],
                                         "high": {"world": high[k]["world"], "v": built, "picture": k}}
                for d in self.list:
                    if fid in d.get("floors", []):
                        d["floors"] = [x for g in d["floors"] for x in ((g, *parts) if g == fid else (g,))]
                continue
            below = f.get("tilesOnly") and high.get(f"{f['instance']}-below")
            if not below:
                continue
            surface = high.get(f"{f['instance']}-surface")
            f.pop("high", None)
            if surface:
                f["high"] = {"world": surface["world"], "v": built, "picture": f"{f['instance']}-surface"}
            if not any(played_below(d, below["boxes"], recorded) for d in self.list if fid in d.get("floors", [])):
                continue
            f.update(name=words.say("page.dungeon.level.surface"), level="surface")
            under = f"{fid}-below"
            self.floors[under] = {**f, "name": words.say("page.dungeon.level.below"), "level": "below",
                                  "boxes": below["boxes"],
                                  "high": {"world": below["world"], "v": built, "picture": f"{f['instance']}-below"}}
            for d in self.list:
                if fid in d.get("floors", []):
                    d["floors"] = [x for g in d["floors"] for x in ((g, under) if g == fid else (g,))]


    def place_of(self, zone):
        return self.places.get(place_key(zone)) if zone else None

    def run_of(self, q):
        if q["id"] not in self.listing:
            for g in [*(q.get("start") or ()), *(q.get("end") or ())]:
                wings = self.wings.get(g.get("inst")) if g.get("inside") else None
                if not wings:
                    continue
                pos = g.get("pos")
                if pos and len(pos) >= 3:
                    return home_wing(wings, pos)
                boss = next((self.met[k].get("boss") for k in (("npc", g.get("npc")), ("object", g.get("object")))
                             if k in self.met), None)
                return next((d for d in wings if any(b.get("name") == boss for b in d.get("bosses") or ())), wings[0])
            return None
        doing = [(d, rec) for d, rec in self.listing.get(q["id"], ()) if not nothing_inside(q, rec.get("spots") or ())]
        if len(doing) < 2:
            return doing[0][0] if doing else None
        held = {}
        for d, rec in doing:
            wings = [w for w, _ in doing if w.get("instance") == d.get("instance")]
            held[d["key"]] = sum(home_wing(wings, p) is d for p in rec.get("spots") or ()
                                 if isinstance(p, (list, tuple)) and len(p) >= 3)
        return max((d for d, _ in doing), key=lambda d: held[d["key"]])

    def open_now(self, side=None):
        stamp = []
        for path in (OPEN, AREAS):
            try:
                stamp.append(os.stat(path).st_mtime_ns)
            except OSError:
                stamp.append(None)
        with self.lock:
            runs = [{"key": r.get("key"), "ended": r.get("ended")} for r in self.runs.get("runs") or ()]
        stamp += [id(self.list), len(runs), max((r["ended"] or 0 for r in runs), default=0), today()]
        if self.open_seen.get(side) != stamp:
            self.open_state[side] = opendungeons.place_states(
                self.list, load_json(OPEN, {"posts": {}}), load_json(AREAS, {}), runs, self.launch, stamp[-1], side)
            self.open_seen[side] = stamp
        return self.open_state[side]

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
        words = f"{word}, " + level_line([min(d["levels"][0] for d in places), min(d["levels"][1] for d in places),
                                          max(d["levels"][2] for d in places)])
        opens = next((w for w in (opening(d.get("opens"), today) for d in places) if w), "")
        if all(self.open_words(d["key"]).get("notOpen") for d in places):
            words += f", {opens}" if opens else ", not in Forever's first raid release" if any(d.get("later") for d in places) \
                else ", not open yet"
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
                low = offered_at(q) if low is None else min(low, offered_at(q))
            handed, choice, held = needs(q)
            todo += [by_id[p] for p in handed + choice + [held] if p in by_id]
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
