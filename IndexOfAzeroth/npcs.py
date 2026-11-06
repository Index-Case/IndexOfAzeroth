# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import math
import re
import time
import unicodedata

import numpy as np

import datafiles
import facts
import moblevels
import store
from geo import MapGeometry
from serverlog import log_error
from versioned import Versioned

LIVE_MOST, FULL_MOST = 25, 250
TYPOS_LIVE = ((4, 1),)
TYPOS_FULL = ((3, 1), (6, 2))
INSIDE_FROM = 4
CLOSE_FROM = 3
CLOSE_SPREAD = 2.5
WORD_MOST = 20
WORDS_MOST = 6
TEXT_MOST = 60
FAR = 99
RANK_WORDS = {1: "elite", 2: "rare elite", 3: "boss", 4: "rare"}
RARE_RANKS = (2, 4)
HEAT_SPAWNS = 3

DROPPED = str.maketrans("", "", "'\"`‘’“”")


def fold(text):
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).translate(DROPPED)
    return " ".join(re.sub(r"[^0-9a-z]+", " ", t).split())


def placeholder(name):
    return bool(re.search(r"[<>\[\]]|\b(trigger|invisible|doodad|generator|spawner|marker|debug|dnd|dnr|dnt)\b", name or "", re.I))


def area_names():
    try:
        import client
        return {str(r["ID"]): r.get("AreaName_lang") or "" for r in client.rows("AreaTable", stored=True)}
    except Exception:
        return {}


class Entry:
    __slots__ = ("name", "key", "words", "compact", "ids", "sub", "levels", "rank", "rare", "masks", "hostile_service",
                 "spots", "dungeon", "zones")

    def __init__(self, name, key):
        self.name, self.key, self.words, self.compact = name, key, tuple(key.split()), key.replace(" ", "")
        self.ids, self.sub, self.levels, self.rank, self.rare = [], "", None, 0, False
        self.masks = None
        self.hostile_service = None
        self.spots = []
        self.dungeon = None
        self.zones = []


class NpcBook:

    def __init__(self, npcs, world, rares, dungeons, geo, areas=None):
        self.geo = geo
        self.areas = {str(k): v for k, v in (areas or {}).items()}
        by_area = {}
        for d in dungeons:
            by_area.setdefault(str(d.get("area")), (d["key"], d["name"].split(":")[0]))
        entries, placed, facts_of = {}, {}, {}
        names = {}

        def zone_of_area(area):
            m = geo.maps.get(geo.area_map.get(str(area)))
            return m and m.get("name")

        def area_spots(npc_id, areas, height=None):
            out = []
            for area, pts in (areas or {}).items():
                zone = zone_of_area(area)
                for x, y in pts:
                    at = x >= 0 and y >= 0 and geo.area_to_world(area, x, y)
                    if at:
                        out.append((at[2], at[0], at[1], zone or "", npc_id, height))
            return out

        for sv in world.get("services", []):
            npc_id = str(sv["id"])
            names.setdefault(npc_id, sv["n"])
            placed.setdefault(npc_id, area_spots(npc_id, sv.get("s"), sv.get("z")))
            f = facts_of.setdefault(npc_id, {})
            f.setdefault("sub", sv.get("sub") or "")
            f["service"] = (sv.get("fr", 0), sv.get("en", 0))
        spawns = world.get("mobSpawns", {})
        for npc_id, m in world.get("mobs", {}).items():
            names.setdefault(npc_id, m[0])
            if not placed.get(npc_id):
                placed[npc_id] = area_spots(npc_id, spawns.get(npc_id))
            f = facts_of.setdefault(npc_id, {})
            f["levels"], f["rank"] = (m[1], m[2]), m[3]
            f["masks"] = (m[6], m[11] if len(m) > 11 else 1)
        for r in rares:
            npc_id = str(r["id"])
            names.setdefault(npc_id, r["name"])
            facts_of.setdefault(npc_id, {})["rare"] = True
            if not placed.get(npc_id):
                m = geo.maps.get(r.get("map"))
                spots = []
                for x, y in r.get("spots") or [r["at"]]:
                    at = geo.to_world(r.get("map"), x / 100, y / 100)
                    if at:
                        spots.append((at[2], at[0], at[1], (m or {}).get("name", ""), npc_id, None))
                placed[npc_id] = spots
        dungeon_of = {}
        for npc_id, n in npcs.items():
            names.setdefault(npc_id, n["n"])
            if not placed.get(npc_id):
                placed[npc_id] = area_spots(npc_id, n.get("s"))
            for area, pts in (n.get("s") or {}).items():
                if str(area) in by_area and any(x < 0 for x, _ in pts):
                    dungeon_of.setdefault(npc_id, by_area[str(area)])
                elif any(x < 0 for x, _ in pts) and self.areas.get(str(area)):
                    dungeon_of.setdefault(npc_id, (None, self.areas[str(area)]))
        for npc_id, name in names.items():
            key = fold(name)
            if not key or placeholder(name):
                continue
            e = entries.get(key)
            if e is None:
                e = entries[key] = Entry(name, key)
            e.ids.append(npc_id)
            f = facts_of.get(npc_id, {})
            e.sub = e.sub or f.get("sub", "")
            if f.get("levels"):
                lo, hi = f["levels"]
                e.levels = (min(lo, e.levels[0]), max(hi, e.levels[1])) if e.levels else (lo, hi)
            e.rank = max(e.rank, f.get("rank", 0))
            e.rare = e.rare or f.get("rare", False) or f.get("rank", 0) in RARE_RANKS
            e.masks = e.masks or f.get("masks")
            e.hostile_service = e.hostile_service or f.get("service")
            seen = {(s[0], round(s[1]), round(s[2])) for s in e.spots}
            for s in placed.get(npc_id) or ():
                if (s[0], round(s[1]), round(s[2])) not in seen:
                    seen.add((s[0], round(s[1]), round(s[2])))
                    e.spots.append(s)
            if not e.spots and npc_id in dungeon_of:
                e.dungeon = e.dungeon or dungeon_of[npc_id]
        self.entries = sorted(entries.values(), key=lambda e: e.key)
        for e in self.entries:
            counts = {}
            for s in e.spots:
                if s[3]:
                    counts[s[3]] = counts.get(s[3], 0) + 1
            e.zones = sorted(counts, key=lambda z: (-counts[z], z))
            if e.spots:
                e.dungeon = None
        self.by_key = {e.key: e for e in self.entries}
        self.index_words()
        self.index_spots()


    def index_words(self):
        self.by_word = {"n": {}, "s": {}, "z": {}}
        for i, e in enumerate(self.entries):
            for kind, words in (("n", e.words), ("s", fold(e.sub).split()),
                                ("z", [w for z in e.zones or ([e.dungeon[1]] if e.dungeon else []) for w in fold(z).split()])):
                for w in words:
                    self.by_word[kind].setdefault(w, set()).add(i)
        self.vocab = sorted(set(self.by_word["n"]) | set(self.by_word["s"]) | set(self.by_word["z"]))
        longest = max((len(w) for w in self.vocab), default=1)
        width = min(WORD_MOST, longest)
        self.codes = np.zeros((len(self.vocab), width), np.uint8)
        for r, w in enumerate(self.vocab):
            b = w[:width].encode("ascii", "ignore")
            self.codes[r, :len(b)] = np.frombuffer(b, np.uint8)
        self.lens = np.array([min(len(w), width) for w in self.vocab], np.int16)
        self.compacts = [e.compact for e in self.entries]
        self.word_starts = []
        for e in self.entries:
            at, starts = 0, []
            for w in e.words:
                starts.append(at)
                at += len(w)
            self.word_starts.append(starts)

    def index_spots(self):
        inst, north, west, owner = [], [], [], []
        self.first = []
        for i, e in enumerate(self.entries):
            self.first.append(len(inst))
            for s in e.spots:
                inst.append(s[0]); north.append(s[1]); west.append(s[2]); owner.append(i)
        self.spot_inst = np.array(inst, np.int32)
        self.spot_n, self.spot_w = np.array(north, np.float64), np.array(west, np.float64)
        self.counts = np.array([len(e.spots) for e in self.entries], np.int64)


    def yards(self, here):
        out = np.full(len(self.entries), np.inf)
        if here is None or not len(self.spot_inst):
            return out
        d = np.where(self.spot_inst == here[0], np.hypot(self.spot_n - here[1], self.spot_w - here[2]), np.inf)
        has = self.counts > 0
        starts = np.array(self.first, np.int64)[has]
        out[has] = np.minimum.reduceat(d, starts)
        return out

    def nearest(self, e, here):
        if not e.spots:
            return None, None
        if here is not None:
            same = [(math.hypot(s[1] - here[1], s[2] - here[2]), s) for s in e.spots if s[0] == here[0]]
            if same:
                d, s = min(same, key=lambda x: x[0])
                return s, d
        main = e.zones[0] if e.zones else ""
        return next((s for s in e.spots if s[3] == main), e.spots[0]), None


    def starting(self, word, kinds="n"):
        lo = bisect.bisect_left(self.vocab, word)
        hi = bisect.bisect_left(self.vocab, word + "\x7f")
        out = set()
        for w in self.vocab[lo:hi]:
            for kind in kinds:
                out |= self.by_word[kind].get(w, set())
        return out

    def distances(self, word):
        q = np.frombuffer(word[:WORD_MOST].encode("ascii", "ignore"), np.uint8)
        codes, lens = self.codes, self.lens
        rows, width = codes.shape
        if not len(q) or not rows:
            return np.full(rows, FAR, np.int16)
        prev2, eq_prev = None, None
        prev = np.tile(np.arange(width + 1, dtype=np.int16), (rows, 1))
        for i in range(1, len(q) + 1):
            eq = codes == q[i - 1]
            cur = np.empty((rows, width + 1), np.int16)
            cur[:, 0] = i
            for j in range(1, width + 1):
                best = np.minimum(np.minimum(prev[:, j], cur[:, j - 1]) + 1, prev[:, j - 1] + ~eq[:, j - 1])
                if eq_prev is not None and j > 1:
                    best = np.where(eq[:, j - 2] & eq_prev[:, j - 1], np.minimum(best, prev2[:, j - 2] + 1), best)
                cur[:, j] = best
            prev2, prev, eq_prev = prev, cur, eq
        whole = prev[np.arange(rows), lens]
        lo, hi = max(1, len(q) - 1), min(width, len(q) + 1)
        if lo > hi:
            return whole
        start = prev[:, lo:hi + 1].copy()
        start[np.arange(lo, hi + 1)[None, :] > lens[:, None]] = FAR
        return np.minimum(whole, start.min(axis=1))

    def reach(self, word, table, kinds, kept=None):
        most = max((k for least, k in table if len(word) >= least), default=0)
        if not most:
            return {i: 0 for i in self.starting(word, kinds)}
        if kept is None:
            kept = {}
        if word not in kept:
            kept[word] = self.distances(word)
        d, best = kept[word], {}
        for r in np.nonzero(d <= most)[0]:
            v, off = self.vocab[r], int(d[r])
            for kind in kinds:
                for i in self.by_word[kind].get(v, ()):
                    if off < best.get(i, FAR):
                        best[i] = off
        return best

    def off_by(self, words, table, kinds, kept=None):
        out = [self.reach(w, table, kinds, kept) for w in words]
        return out if all(out) else None

    def search(self, text, full=False, here=None):
        q = fold(str(text or "")[:TEXT_MOST])
        words = q.split()[:WORDS_MOST]
        if not words:
            return
        compact = "".join(words)
        far = self.yards(here)
        found, kept = set(), {}

        def ranked(scores):
            new = [i for i in scores if i not in found]
            new.sort(key=lambda i: (-scores[i], far[i], self.entries[i].key))
            found.update(new)
            return new

        scores = {}
        hits = set.intersection(*[self.starting(w) for w in words])
        if len(compact) >= INSIDE_FROM:
            hits |= {i for i, c in enumerate(self.compacts) if compact in c}
        for i in hits:
            e = self.entries[i]
            scores[i] = (100 if e.key == q else 90 if e.key.startswith(q) else 80 if self.in_order(words, e.words)
                         else 70 if all(any(v.startswith(w) for v in e.words) for w in words) else 60)
        yield "names", ranked(scores)
        if not full and 100 in scores.values():
            return
        if len(compact) >= CLOSE_FROM:
            pattern, scores, most = re.compile(".*?".join(map(re.escape, compact))), {}, CLOSE_SPREAD * len(compact)
            for i, c in enumerate(self.compacts):
                if i in found:
                    continue
                spans = [m.end() - at for at in self.word_starts[i] if c[at] == compact[0]
                         for m in [pattern.match(c, at)] if m]
                if spans and min(spans) <= most:
                    scores[i] = 50 - (min(spans) - len(compact))
            yield "letters", ranked(scores)
        near = self.off_by(words, TYPOS_FULL if full else TYPOS_LIVE, "n", kept)
        if near:
            both = set.intersection(*[set(b) for b in near])
            yield "typos", ranked({i: 40 - 10 * sum(b[i] for b in near) for i in both})
        if full:
            near = self.off_by(words, TYPOS_FULL, "nsz", kept)
            if near:
                named = set().union(*[set(self.reach(w, TYPOS_FULL, "ns", kept)) for w in words])
                both = set.intersection(*[set(b) for b in near]) & named
                yield "more", ranked({i: 30 - 10 * sum(b[i] for b in near) for i in both})

    @staticmethod
    def in_order(words, names):
        k = 0
        for v in names:
            if k < len(words) and v.startswith(words[k]):
                k += 1
        return k == len(words)


def kind_for(e, faction):
    side = 1 | facts.faction_bit(faction)
    if e.masks is not None:
        return "npc" if e.masks[0] & side else "mob"
    if e.hostile_service is not None:
        friend, enemy = e.hostile_service
        return "mob" if enemy & side and not friend & side else "npc"
    return "mob" if e.rare else "npc"


def found(book, e, here, faction, heights=None):
    spot, yards = book.nearest(e, here)
    z = spot and spot[5]
    if spot and z is None and heights:
        got = heights(spot[4], spot[0], [(spot[1], spot[2])])
        z = float(got[0]) if got and got[0] is not None and not math.isnan(got[0]) else None
    zone = spot[3] if spot else e.dungeon[1] if e.dungeon else ""
    levels = moblevels.span(*e.levels) if e.levels else next(filter(None, map(moblevels.of_data, e.ids)), None)
    levels = moblevels.game(e.ids[0], levels)
    return {"id": int(e.ids[0]) if e.ids[0].isdigit() else e.ids[0], "name": e.name, "sub": e.sub,
            "levels": levels, "rank": RANK_WORDS.get(e.rank, ""), "rare": e.rare,
            "kind": kind_for(e, faction), "zone": zone, "zones": [z2 for z2 in e.zones if z2 != zone][:8],
            "at": {"inst": int(spot[0]), "n": round(spot[1], 1), "w": round(spot[2], 1),
                   "z": round(z, 1) if z is not None else None} if spot else None,
            "yards": round(yards) if yards is not None else None,
            "dungeon": e.dungeon[0] if e.dungeon and not spot else None, "heat": shows_heat(e)}


def shows_heat(e):
    return len(e.spots) >= HEAT_SPAWNS


def heat_spots(book, name):
    e = book.by_key.get(fold(name))
    if e is None:
        return None
    return [[int(s[0]), round(s[1], 1), round(s[2], 1)] for s in e.spots] if shows_heat(e) else []


def answer(book, text, full, here, faction, heights=None):
    started, sent = time.perf_counter(), 0
    most = FULL_MOST if full else LIVE_MOST
    for name, hits in book.search(text, full, here):
        take = hits[:most - sent]
        if take:
            sent += len(take)
            yield {"pass": name, "found": [found(book, book.entries[i], here, faction, heights) for i in take]}
        if sent >= most:
            break
    yield {"done": True, "count": sent, "more": not full, "ms": round((time.perf_counter() - started) * 1000)}


def build_book():
    from layers import with_trainers
    geo = MapGeometry()
    world = datafiles.load(datafiles.data_path("world.json"), {})
    profs = datafiles.load(datafiles.data_path("professions.json"), {})
    world = {**world, "services": with_trainers(world.get("services") or [], profs, geo)}
    npcs = datafiles.load(datafiles.data_path("objectives.json"), {}).get("npcs", {})
    rares = store.load_json(datafiles.data_path("rares.json"), {}).get("rares", [])
    dungeons = datafiles.load(datafiles.data_path("dungeons.json"), {}).get("dungeons", [])
    return NpcBook(npcs, world, rares, dungeons, geo, area_names())


BOOK = Versioned(build_book, lambda where: log_error(where), "NPC book")


def npc_book(hub):
    return BOOK.get(getattr(hub, "data_version", None) or 0)


def warm_npcs(hub):
    try:
        npc_book(hub)
    except Exception:
        log_error("building the NPC book")
