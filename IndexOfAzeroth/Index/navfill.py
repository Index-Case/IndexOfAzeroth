# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import os
import struct
import subprocess
import threading
import time

import numpy as np

import arrays
import casc
import client
import game
import nav
import navstore
import store
import travel
import workers
from nav import wm
from serverlog import append_log

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "navfill.json")
WANTED = os.path.join(ROOT, "data", "navfill-wanted.json")
LOCK = os.path.join(ROOT, "data", "navfill.lock")
TOOL = os.path.join(ROOT, "tools", "fill_nav.py")
VERDICT, REBUILD_LOG = "navverdict.json", "rebuild.log"
DOWNLOAD_GAP = 0.35
FILL_WORKERS = workers.PROCESSES
BATCH = 48
WANT_REACH = 250.0
WANTED_MOST = 24
EMPTY_MOST = 512
STATE_EVERY = 3.0
CHECK_EVERY = 600
PRUNE_AFTER = 60
STARTUP_DELAY = 30
RECHECK = 86400
START_GAP = 60
RUN_LOOK = 2.0
KINDS = ("tiles", "roads", "buildings", "doodads", "graph")
PHASES = ("tiles", "roads", "buildings", "doodads", "stale", "graph")
DEFAULT_SECONDS = {"tiles": 1.0, "roads": 0.1, "buildings": 6.0, "graph": 0.5, "doodads": 0.2}
PIECE_KIND = {"tile": "tiles", "roads": "roads", "building": "buildings", "graph": "graph", "doodads": "doodads"}
PHASE_WORDS = {"tiles": "terrain tiles", "roads": "roads", "buildings": "buildings", "graph": "travel graph",
               "doodads": "doodad areas",
               "stale": "pieces kept from before the build"}
CONTINENTS = (0, 1)
AREA_SPAN = 1024


def fill_build():
    build = wm.installed_version()
    return build if wm.switched_build() == build else None



def map_rows():
    return {int(r["ID"]): r for r in client.rows("Map") if int(r.get("WdtFileDataID") or 0)}


def map_tiles(wdt):
    maid = wdt.get("MAID", b"")
    return [(i % 64, i // 64) for i in range(min(len(maid) // 32, 4096)) if struct.unpack_from("<I", maid, i * 32)[0]]


def global_place(wdt):
    m = struct.unpack_from("<II3f3f3f3fHHHH", wdt.get("MODF", b""), 0)
    px, py, pz = m[2:5]
    return (float(m[0]), float(m[1]), -pz, -px, py, m[6], 0.0, 0.0, 0.0, 0.0, 1.0)


def area_key(gn, gw):
    return (gn + AREA_SPAN // 2) * AREA_SPAN + gw + AREA_SPAN // 2


def area_spot(key):
    return int(key // AREA_SPAN - AREA_SPAN // 2), int(key % AREA_SPAN - AREA_SPAN // 2)


def doodad_areas(doodads):
    gn, gw = nav.doodad_spots(doodads)
    return np.unique(area_key(gn, gw))


def tile_parts(path):
    try:
        with navstore.opened(path) as f, np.load(f) as z:
            if "none" in z.files:
                return np.zeros((0, 11)), np.zeros((0, nav.DOODAD_COLUMNS))
            return (z["places"] if "places" in z.files else np.zeros((0, 11)),
                    z["doodads"] if "doodads" in z.files else np.zeros((0, nav.DOODAD_COLUMNS)))
    except arrays.UNREADABLE:
        return None


def graph_bigs(path):
    try:
        with navstore.opened(path) as f, np.load(f) as z:
            return z["bigs"] if "bigs" in z.files else np.zeros((0, nav.PLACE_COLUMNS))
    except arrays.UNREADABLE:
        return None


def built_names(folder=None):
    return navstore.names(folder or nav.CACHE)


def tile_name(inst, col, row, rules=None):
    return os.path.basename(nav.tile_path(inst, col, row, rules))


def road_name(inst, col, row, rules=None):
    return os.path.basename(nav.road_path(inst, col, row, rules))


def made_new(names, name):
    when = lambda n: names[n][1] if n in names else None
    return nav.as_new(when(name), [when(n) for n in nav.made_from(name)])


def place_built(names, key, rules=None):
    layers = names.get(nav.layers_name(key, rules))
    return layers is not None and (layers[0] <= EMPTY_MOST or made_new(names, nav.joins_name(key, rules)))


def survey_map(inst, wdt, names, parts=tile_parts, rules=None):
    rules = rules or nav.rules_in_force()
    tiles = map_tiles(wdt)
    kind = "terrain" if tiles else "building" if wdt.get("MODF") else None
    pieces = {k: [] for k in KINDS}
    if kind == "building":
        pieces["buildings"].append(("building", inst, global_place(wdt)))
    places, areas, behind = {}, [], set()
    for col, row in tiles:
        pieces["tiles"].append(("tile", inst, col, row))
        pieces["roads"].append(("roads", inst, col, row))
        pieces["graph"].append(("graph", inst, col, row))
        name = tile_name(inst, col, row, rules)
        got = parts(os.path.join(nav.CACHE, name)) if name in names else None
        if got is None:
            continue
        if nav.places_behind(got[0]):
            behind.add((col, row))
        for p in got[0]:
            row_ = tuple(float(v) for v in p)
            if len(row_) > len(places.get(int(p[1]), ())):
                places[int(p[1])] = row_
        areas.append(doodad_areas(got[1]))
    pieces["buildings"] += [("building", inst, p) for p in places.values()]
    keys = np.unique(np.concatenate(areas)) if areas else np.zeros(0, np.int64)
    pieces["doodads"] = [("doodads", inst, *area_spot(a)) for a in keys.tolist()]
    missing = {k: [p for p in pieces[k] if not piece_built(names, p, rules)] for k in KINDS}
    missing["tiles"] += [p for p in pieces["tiles"] if (p[2], p[3]) in behind and p not in missing["tiles"]]
    return {"kind": kind, "pieces": pieces, "missing": missing,
            **{k: [len(pieces[k]) - len(missing[k]), len(pieces[k])] for k in KINDS}}


def graph_name(inst, col, row, rules=None):
    return nav.graph_name(f"{inst}_{col}_{row}", rules)


def graph_built(names, inst, col, row, rules=None):
    name = graph_name(inst, col, row, rules)
    if name not in names:
        return False
    bigs = graph_bigs(os.path.join(nav.CACHE, name))
    if bigs is None:
        return False
    return nav.as_new(names[name][1], [written(names, p) for p in travel.tile_inputs(inst, col, row, {"bigs": bigs}, rules)])


def written(names, path):
    if os.path.dirname(path) != nav.CACHE:
        return nav.made_at(path)
    got = names.get(os.path.basename(path))
    return None if got is None else got[1]


def has_floors_graph(place):
    return bool(place[10]) and any(float(v) for v in place[6:10])


def piece_files(piece, rules=None):
    if piece[0] == "tile":
        return [tile_name(*piece[1:4], rules)]
    if piece[0] == "roads":
        return [road_name(*piece[1:4], rules)]
    if piece[0] == "graph":
        return [graph_name(*piece[1:4], rules)]
    key = nav.place_key(piece[1], piece[2]) if piece[0] == "building" else nav.props_key(piece[1], piece[2], piece[3])
    floors = [nav.floors_name(key, rules)] if piece[0] == "building" and has_floors_graph(piece[2]) else []
    return [nav.layers_name(key, rules), nav.joins_name(key, rules)] + floors


def stale(maps, names, since, done=(), rules=None):
    if not since:
        return []
    return [p for m in maps.values() for k in KINDS for p in m["pieces"][k] if p not in done
            and piece_built(names, p, rules) and any(names[f][1] < since for f in piece_files(p, rules) if f in names)]


def piece_built(names, piece, rules=None):
    if piece[0] == "tile":
        return tile_name(*piece[1:4], rules) in names
    if piece[0] == "roads":
        return road_name(*piece[1:4], rules) in names
    if piece[0] == "graph":
        return graph_built(names, *piece[1:4], rules)
    key = nav.place_key(piece[1], piece[2]) if piece[0] == "building" else nav.props_key(piece[1], piece[2], piece[3])
    floors = piece[0] != "building" or not has_floors_graph(piece[2]) or made_new(names, nav.floors_name(key, rules))
    return place_built(names, key, rules) and floors


def kept_wdt(row):
    try:
        return wm.chunks(wm.kept_file(f"wdt-{row['WdtFileDataID']}.wdt"))
    except wm.NotBuilt:
        return None


def survey(only=None, names=None, rows=None, wdt=kept_wdt, parts=tile_parts, rules=None):
    rows = map_rows() if rows is None else rows
    names = built_names() if names is None else names
    rules = rules or nav.rules_in_force()
    out = {}
    for inst, row in sorted(rows.items()):
        if only and inst not in only:
            continue
        w = wdt(row)
        name = row.get("MapName_lang") or row.get("Directory") or str(inst)
        if w is None:
            out[inst] = {"name": name, "wdt": False, "kind": None, "pieces": {k: [] for k in KINDS},
                         "missing": {k: [] for k in KINDS}, **{k: [0, 0] for k in KINDS}}
            continue
        out[inst] = {"name": name, "wdt": True, **survey_map(inst, w, names, parts, rules)}
    return out


def totals(maps):
    out = {k: [sum(m[k][0] for m in maps.values()), sum(m[k][1] for m in maps.values())] for k in KINDS}
    out["maps"] = [sum(1 for m in maps.values() if m.get("wdt")), len(maps)]
    return out


def whole(maps):
    return all(m.get("wdt") and all(m[k][0] == m[k][1] for k in KINDS) for m in maps.values())


def piece_words(piece):
    if piece[0] == "tile":
        return f"tile {piece[2]}_{piece[3]}"
    if piece[0] == "roads":
        return f"roads {piece[2]}_{piece[3]}"
    if piece[0] == "graph":
        return f"graph {piece[2]}_{piece[3]}"
    if piece[0] == "building":
        return f"building {int(piece[2][0])}/{int(piece[2][1])}"
    return f"doodads {piece[2]},{piece[3]}"


def report_lines(maps, most=5):
    lines = []
    for inst, m in maps.items():
        if not m.get("wdt"):
            lines.append(f"{inst:5d} {m['name'][:32]:32s} its WDT isn't fetched yet: its pieces are unknown")
            continue
        said = "  ".join(f"{k} {m[k][0]:,} of {m[k][1]:,}" for k in KINDS)
        lines.append(f"{inst:5d} {m['name'][:32]:32s} {m['kind'] or 'nothing to walk':9s} {said}")
        for k in KINDS:
            gone = m["missing"][k]
            if gone:
                more = f" and {len(gone) - most:,} more" if len(gone) > most else ""
                lines.append(f"      missing: {', '.join(piece_words(p) for p in gone[:most])}{more}")
    t = totals(maps)
    lines.append(f"maps {t['maps'][0]} of {t['maps'][1]} with their WDT, " + ", ".join(f"{k} {t[k][0]:,} of {t[k][1]:,}" for k in KINDS))
    lines.append("none missing" if whole(maps) else "some missing: the fill builds them (python tools/fill_nav.py fill)")
    return lines



_pace = None
_paths = None


def paced(download):
    inner = getattr(download, "unpaced", download)

    def run(url):
        if _pace is not None:
            lock, last = _pace
            with lock:
                wait = last.value + DOWNLOAD_GAP - time.time()
                if wait > 0:
                    time.sleep(wait)
                last.value = time.time()
        return inner(url)
    run.unpaced = inner
    return run


def worker_setup(pace=None):
    global _pace, _paths
    _pace, _paths = pace, None
    wm._remote = paced(wm._remote)
    nav.KEEP_TILES, nav.KEEP_BUILDINGS_BYTES = 64, 64 << 20
    travel.KEEP_GRAPHS = 16


def build_piece(piece):
    global _paths
    t0, before = time.time(), casc.counts()
    error = None
    try:
        with wm.filling():
            if _paths is None:
                _paths = nav.Paths()
            kind, inst = piece[0], piece[1]
            if kind == "tile":
                _paths.terrain.tile(inst, piece[2], piece[3])
            elif kind == "roads":
                _paths.terrain.fetch_roads(inst, piece[2], piece[3])
            elif kind == "graph":
                _paths.travel.store.tile(inst, piece[2], piece[3])
            elif kind == "building":
                place = np.asarray(piece[2], np.float64)
                try:
                    _paths.buildings.get(inst, place)
                    if has_floors_graph(place):
                        _paths.travel.store.floors(inst, place)
                except nav.NothingToWalk:
                    pass
            else:
                _paths.buildings.props(inst, (piece[2] * nav.PROP_GRID, piece[3] * nav.PROP_GRID))
    except Exception as e:
        error = f"{type(e).__name__}: {e}"[:300]
    return piece, error, time.time() - t0, reads_since(before)


def reads_since(before):
    now = casc.counts()
    return {k: now[k] - before.get(k, 0) for k in casc.KINDS if now[k] != before.get(k, 0)}


def add_reads(total, reads):
    for k, n in reads.items():
        total[k] = total.get(k, 0) + n
    return total


def piece_spot(piece):
    if piece[0] in ("tile", "roads", "graph"):
        return (piece[1], *nav.world_of(piece[3] * 128 + 64, piece[2] * 128 + 64))
    if piece[0] == "building":
        return piece[1], piece[2][2], piece[2][3]
    return piece[1], piece[2] * nav.PROP_GRID, piece[3] * nav.PROP_GRID


def near(piece, spots):
    inst, n, w = piece_spot(piece)
    reach = WANT_REACH + (nav.TILE / 2 if piece[0] in ("tile", "roads", "graph") else 0)
    return any(s[0] == inst and abs(s[1] - n) <= reach and abs(s[2] - w) <= reach for s in spots)


def first_key(piece):
    kind = ("tile", "roads", "building", "doodads", "graph").index(piece[0])
    return kind, piece[0] == "building" and not piece[2][10]


def whose(name):
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def read_wanted(path=WANTED):
    got = store.load_json(path, [])
    return [tuple(s[:3]) for s in got if isinstance(s, list) and len(s) >= 3][:WANTED_MOST]


class FillRun:

    def __init__(self, pool, only=None, fetch_wdt=None, state_path=STATE, wanted_path=WANTED, say=print, clock=time.time,
                 workers=FILL_WORKERS):
        self.pool, self.only, self.say, self.clock, self.workers = pool, only, say, clock, workers
        self.fetch_wdt = fetch_wdt or (lambda row: wm.map_file(row, wm.installed_version()))
        self.state_path, self.wanted_path = state_path, wanted_path
        self.rules = nav.code_rules()
        self.state = {"state": "filling", "build": None, "rules": self.rules, "served": None, "since": 0.0,
                      "started": round(clock()), "phase": "maps", "doing": None, "counts": {}, "next": None, "held": 0,
                      "failed": 0,
                      "lastError": None, "eta": None, "reads": dict.fromkeys(casc.KINDS, 0)}
        self.noted = 0.0
        self.worker_reads = {}
        self.own_before = casc.counts()
        self.handed = set()
        self.tried = set()
        self.failed = set()
        self.took = {k: [0, 0.0] for k in KINDS + ("stale",)}
        self.before = store.load_json(state_path, {})
        self.state["copies"] = self.before.get("copies")
        self.maps = {}
        self.wanted, self.first = None, []
        self.first_again = False

    def note(self, force=False, **changes):
        self.state.update(changes)
        self.state["reads"] = add_reads(add_reads(dict.fromkeys(casc.KINDS, 0), self.worker_reads), reads_since(self.own_before))
        was = self.before.get("took") or {}
        self.state["took"] = {k: [n, round(s, 1)] if n else list(was.get(k) or (0, 0.0)) for k, (n, s) in self.took.items()}
        if force or self.clock() - self.noted >= STATE_EVERY:
            self.noted = self.clock()
            self.state["updated"] = round(self.noted)
            store.save_json(self.state_path, self.state)

    def read_maps(self):
        rows = map_rows()
        for inst in sorted(rows, key=lambda i: (i not in CONTINENTS, i)):
            if self.only and inst not in self.only:
                continue
            try:
                self.maps[inst] = (rows[inst], self.fetch_wdt(rows[inst]))
            except OSError as e:
                self.say(f"map {inst}: its WDT can't be had ({e})")
                self.maps[inst] = (rows[inst], None)
        self.save_index()

    def save_index(self):
        path = nav.map_index_path(self.rules)
        index = navstore.load_json(path, {})
        for inst, (_, wdt) in self.maps.items():
            if wdt is not None:
                tiles = map_tiles(wdt)
                kind = "terrain" if tiles else "building" if wdt.get("MODF") else None
                index[str(inst)] = {"kind": kind, "global": list(global_place(wdt)) if kind == "building" else None,
                                    "tiles": [list(t) for t in tiles]}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.save_json(path, index)

    def surveyed(self, only=None, rules=None, names=None):
        names = built_names() if names is None else names
        wdts = {inst: w for inst, (_, w) in self.maps.items()}
        rows = {inst: row for inst, (row, _) in self.maps.items() if not only or inst in only}
        return survey(names=names, rows=rows, wdt=lambda row: wdts.get(int(row["ID"])), rules=rules or self.rules), names

    def sets(self, maps, names):
        import navcheck
        served = nav.served_rules()
        if served == self.rules:
            return {"served": served, "counts": totals(maps), "whole": whole(maps), "next": None}
        mine, _ = self.surveyed(rules=served, names=names)
        return {"served": served, "counts": totals(mine), "whole": whole(mine),
                "next": {"rules": navcheck.rule_changes(served, self.rules), "counts": totals(maps)}}

    def building(self):
        return (self.state.get("next") or self.state)["counts"]

    def run(self):
        self.state.update(build=wm.installed_version(), since=wm.switched_since())
        self.note(force=True)
        self.read_maps()
        self.check_keys()
        for phase in PHASES:
            self.fill(phase)
        maps, names = self.surveyed()
        self.switch(maps, names)
        self.note(force=True, state="done", phase=None, doing=None, eta=0, **self.sets(maps, names), done=round(self.clock()))
        self.keep_keys()
        self.compare_copies()
        return self.state["counts"]

    def switch(self, maps, names):
        got = nav.switched()
        if self.only or (got is not None and got[0] == self.rules):
            return False
        served = nav.served_rules()
        lost = [p for m in maps.values() for k in KINDS for p in m["missing"][k]
                if piece_built(names, p, served) and piece_files(p, served) != piece_files(p, self.rules)]
        if lost:
            held = all(p in self.tried for p in lost)
            self.state["held"] = len(lost) if held else 0
            self.say(f"the switch to the code's rules waits on {len(lost):,} served piece{'s' if len(lost) != 1 else ''} "
                     f"they haven't built yet, {piece_words(lost[0])} on map {lost[0][1]} first"
                     + (": this run tried each one, and the next day's fill tries them again" if held else ""))
            return False
        import navcheck
        nav.switch_served(self.rules, clock=self.clock)
        changed = navcheck.rule_changes(served, self.rules)
        self.say("the store is served by the code's rules now" + (f": {', '.join(changed)} changed" if changed else ""))
        return True

    def check_keys(self):
        import navcheck
        try:
            left, by_bytes = navcheck.keys_left(self.before, self.state["build"], lambda: navcheck.key_pass(say=self.say))
            maps, names = self.surveyed()
            v = navcheck.verdict(self.state["build"], self.before, names, missing=navcheck.missing_pieces(maps),
                                 left=left, stale=navcheck.stale_files(maps, names), by_bytes=by_bytes,
                                 map_names={i: m["name"] for i, m in maps.items()}, packed=navcheck.packed_only(),
                                 workers=self.workers)
            folder = os.path.dirname(self.state_path)
            navcheck.note_verdict(v, os.path.join(folder, VERDICT), os.path.join(folder, REBUILD_LOG))
        except Exception as e:
            self.say(f"key pass or verdict failed: {type(e).__name__}: {e}")

    def keep_keys(self):
        import navcheck
        try:
            navcheck.note_keys()
        except Exception as e:
            self.say(f"keeping the build's keys failed: {type(e).__name__}: {e}")

    def compare_copies(self):
        import navcheck
        try:
            got = navcheck.compare_copies(self.state.get("copies"))
        except Exception as e:
            self.say(f"comparing the kept client files with the game's failed: {type(e).__name__}: {e}")
            return
        if got is not None:
            if got["read"]:
                self.say(navcheck.copies_line(got))
            self.note(force=True, copies=got)

    def todo(self, phase):
        maps, names = self.surveyed()
        self.note(**self.sets(maps, names))
        if phase == "stale":
            return stale(maps, names, wm.switched_since(), self.tried, self.rules)
        return sorted((p for m in maps.values() for p in m["missing"][phase] if p not in self.failed), key=first_key)

    def wanted_first(self):
        wanted = read_wanted(self.wanted_path)
        if wanted == self.wanted and not self.first_again:
            return
        self.wanted, self.first_again = wanted, False
        if not wanted:
            self.first = []
            return
        maps, _ = self.surveyed(only={s[0] for s in wanted})
        self.first = sorted((p for m in maps.values() for k in KINDS for p in m["missing"][k]
                             if p not in self.handed and p not in self.failed and near(p, wanted)), key=first_key)

    def next_batch(self, todo, at):
        batch = []
        while self.first and len(batch) < BATCH:
            p = self.first.pop(0)
            if p not in self.handed:
                batch.append(p)
                self.handed.add(p)
        while at < len(todo) and len(batch) < BATCH:
            p, at = todo[at], at + 1
            if p not in self.handed:
                batch.append(p)
                self.handed.add(p)
        self.tried.update(batch)
        return batch, at

    def fill(self, phase):
        self.handed = set()
        todo, at = self.todo(phase), 0
        while True:
            self.wanted_first()
            batch, at = self.next_batch(todo, at)
            if not batch:
                break
            if any(p[0] == "tile" and self.wanted and near(p, self.wanted) for p in batch):
                self.first_again = True
            name = self.maps.get(batch[-1][1], ({}, None))[0].get("MapName_lang") or f"map {batch[-1][1]}"
            doing = f"{whose(name)} {PHASE_WORDS[phase]}"
            self.note(force=doing != self.state.get("doing"), phase=phase, doing=doing, eta=self.eta())
            for piece, error, seconds, reads in self.pool.map(build_piece, batch):
                add_reads(self.worker_reads, reads)
                kind = PIECE_KIND[piece[0]]
                took = self.took["stale" if phase == "stale" else kind]
                took[0] += 1
                took[1] += seconds
                if error:
                    self.failed.add(piece)
                    self.say(f"failed: {piece_words(piece)} on map {piece[1]}: {error}")
                    self.note(failed=self.state["failed"] + 1, lastError=f"{piece_words(piece)} on map {piece[1]}: {error}")
                elif phase != "stale" and self.building().get(kind):
                    c = self.building()[kind]
                    c[0] += 1
                    c[1] = max(c[1], c[0])
                    self.note(eta=self.eta())
        self.note(force=True)

    def eta(self):
        counts, left = self.building() or {}, 0.0
        for k in KINDS:
            built, every = counts.get(k) or (0, 0)
            n, secs = self.took.get(k) or (0, 0.0)
            left += max(0, every - built) * (secs / n if n else DEFAULT_SECONDS[k])
        return round(left / max(1, self.workers))



def fill_running(path=LOCK):
    if not os.path.exists(path):
        return False
    try:
        with open(path, "a+b") as f:
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return False
    except OSError:
        return False


class Fill:

    def __init__(self, log=None, popen=subprocess.Popen, state_path=STATE, wanted_path=WANTED, running=fill_running,
                 clock=time.time, prune=None):
        self.log, self.popen, self.state_path, self.wanted_path = log, popen, state_path, wanted_path
        self.held, self.clock = running, clock
        self.prune = prune or nav.prune_cache
        self.pruned = (nav.switched() or (None,))[0]
        self.lock = threading.Lock()
        self.wants = collections.OrderedDict()
        self.proc = None
        self.started = 0.0
        self.read = (None, {})
        self.looked = (-RUN_LOOK, False)

    def state(self):
        stamp = store.stamp(self.state_path)
        if stamp != self.read[0]:
            self.read = (stamp, store.load_json(self.state_path, {}))
        return self.read[1]

    def running(self):
        now = self.clock()
        if now - self.looked[0] >= RUN_LOOK:
            self.looked = (now, bool(self.held()))
        return self.looked[1]

    def due(self, state=None):
        s = self.state() if state is None else state
        try:
            build = fill_build()
        except (OSError, game.GameNotFound):
            return False
        if build is None:
            return False
        return (s.get("state") != "done" or s.get("build") != build or s.get("rules") != nav.code_rules()
                or float(s.get("since") or 0) < wm.switched_since() or self.clock() - float(s.get("done") or 0) > RECHECK
                or nav.switched() is None or (nav.served_rules() != nav.code_rules() and not s.get("held")))

    def tidy(self):
        got = nav.switched()
        if got is None or got[0] == self.pruned or self.clock() - got[1] < PRUNE_AFTER:
            return False
        self.pruned = got[0]
        self.prune()
        return True

    def start(self):
        with self.lock:
            if self.clock() - self.started < START_GAP or self.held():
                return False
            self.started = self.clock()
            self.looked = (self.clock(), True)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            import rebuild
            self.proc = self.popen([game.console_python(), TOOL, "fill"], cwd=ROOT, creationflags=flags,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env={**os.environ, "WCC_TRAFFIC_LOG": rebuild.TRAFFIC_LOG})
            return True

    def look(self):
        self.tidy()
        return self.due() and self.start()

    def watch(self, sleep=time.sleep):
        sleep(STARTUP_DELAY)
        while True:
            try:
                self.look()
            except Exception:
                if self.log:
                    self.log("navigation fill")
            sleep(CHECK_EVERY)

    def want(self, inst, north, west):
        key = (int(inst), round(north / 100), round(west / 100))
        with self.lock:
            fresh = key not in self.wants
            self.wants.pop(key, None)
            self.wants[key] = [int(inst), round(float(north), 1), round(float(west), 1)]
            while len(self.wants) > WANTED_MOST:
                self.wants.popitem(last=False)
            spots = list(reversed(self.wants.values()))
        if fresh:
            try:
                store.save_json(self.wanted_path, spots)
            except OSError:
                if self.log:
                    self.log("navigation wanted spots")
        if fresh and not self.running() and self.due():
            self.start()

    def snapshot(self):
        s = self.state()
        return {**s, "running": bool(self.running()), "pct": share(s.get("counts"))}

    def brief(self):
        s = self.snapshot()
        if not s.get("state"):
            return None
        return {"state": s["state"], "running": s["running"], "pct": s["pct"], "doing": s.get("doing"), "eta": s.get("eta"),
                "whole": bool(s.get("whole")), "counts": s.get("counts"), "reads": s.get("reads")}


def share(counts):
    if not counts:
        return None
    weight = {"tiles": 1.0, "roads": 0.1, "buildings": 1.0, "graph": 0.5, "doodads": 0.1}
    have = sum(weight[k] * (counts.get(k) or [0, 0])[0] for k in KINDS)
    want = sum(weight[k] * (counts.get(k) or [0, 0])[1] for k in KINDS)
    return round(100.0 * have / want, 1) if want else None


def logged(say, log, clock=time.time):
    def line(text):
        say(text)
        append_log(log, f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(clock()))} navigation: {text}\n")
    return line


def fill_main(only=None, processes=FILL_WORKERS, say=print):
    say = logged(say, os.path.join(os.path.dirname(STATE), REBUILD_LOG))
    import multiprocessing
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    with open(LOCK, "a+b") as held:
        import msvcrt
        try:
            msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            say("another fill runs: this one leaves it to that")
            return None
        if fill_build() is None:
            say(f"build {wm.installed_version()} is installed and its arrival isn't noted yet: the fill waits for the "
                f"rebuild to note it")
            return None
        with workers.turn("navigation fill", ROOT, say=say):
            for path in wm.clean_leftovers():
                say(f"cleared {os.path.basename(path)}")
            pace = (multiprocessing.Lock(), multiprocessing.Value("d", 0.0))
            worker_setup(pace)
            with wm.filling(), worker_pool(processes, pace) as pool:
                return FillRun(pool, only=only, say=say, workers=processes).run()


def worker_pool(processes, pace):
    return workers.pool(processes, worker_setup, (pace,), what="navigation fill")


def survey_json(maps):
    return {str(inst): {"name": m["name"], "wdt": m.get("wdt"), "kind": m.get("kind"), **{k: m[k] for k in KINDS}}
            for inst, m in maps.items()}
