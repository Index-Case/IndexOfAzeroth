# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import queue
import time

import numpy as np

import nav
import wmonav
from serverlog import log_error, start_thread

STEP_ON = wmonav.STEP_UP
RISE = math.tan(math.radians(wmonav.MAX_UP))
GAP = 2.0
STILL = 1.5
RUN_MOST = 40.0
ENTRY_MOST = 8.0
KEEP_TILES = 64
RETRY = 60.0


class Index:

    def __init__(self, yards=None, ways_on=None, failed=False):
        self.yards, self.ways_on, self.failed = yards or {}, ways_on or {}, failed
        self.made = time.time()


def tile_index(paths, inst, col, row):
    store, yards, ways = paths.travel.store, {}, {}
    if not paths.terrain.on_map(inst, col, row):
        return Index()
    g = store.tile(inst, col, row)
    for gn, gw in (g or {}).get("walked", ()):
        try:
            f = store.walked(inst, int(gn), int(gw))
            b = paths.buildings.props(inst, (int(gn) * nav.PROP_GRID, int(gw) * nav.PROP_GRID)) if f else None
        except nav.NotBuilt as e:
            nav.wm.note_unbuilt(e.what)
            continue
        if not f or not b or len(f["piece_of_node"]) != len(b["layers"].nodes):
            continue
        L, piece = b["layers"], f["piece_of_node"]
        k = np.flatnonzero(piece >= 0)
        r, c, layer = L.nodes[k].T
        north, west = L.world(r, c)
        z = L.heights[r, c, layer]
        for yard, height in zip(nav.yard_of(north, west).tolist(), z.tolist()):
            yards.setdefault(yard, set()).add(round(height, 2))
        up = f["join_up"]
        for p, cell in zip(f["joins"][up, 0].tolist(), f["joins"][up, 1].tolist()):
            ways.setdefault(int(cell), set()).add(round(float(f["centre"][p, 2]), 2))
    return Index({y: tuple(sorted(h)) for y, h in yards.items()}, {c: tuple(sorted(h)) for c, h in ways.items()})


def yard(north, west):
    return (int(math.floor(nav.YARD_ORIGIN - north)) * nav.YARD_SPAN + int(math.floor(nav.YARD_ORIGIN - west)))


def cell(north, west):
    return int((nav.CORNER - north) // nav.CELL) * 8192 + int((nav.CORNER - west) // nav.CELL)


def nearest(heights, z, most):
    best = None
    for h in heights:
        if abs(h - z) <= most and (best is None or abs(h - z) < abs(best - z)):
            best = h
    return best


class Decks:

    def __init__(self, paths=None, index_of=None, clock=time.time):
        self.paths, self.clock = paths, clock
        self.index_of = index_of or (lambda inst, col, row: tile_index(self.paths, inst, col, row))
        self.indexes = {}
        self.asked = set()
        self.todo = queue.SimpleQueue()
        self.loader = None
        self.inst, self.north, self.west, self.when = None, 0.0, 0.0, 0.0
        self.known, self.inside, self.on = False, False, None
        self.out_north = self.out_west = None


    def step(self, state, here):
        now = self.clock()
        if not here or ((state or {}).get("flags") or {}).get("taxi"):
            self.inst, self.known = None, False
            return None
        inst, north, west = here
        key = (inst, int((nav.CORNER - west) // nav.TILE), int((nav.CORNER - north) // nav.TILE))
        index = self.indexes.get(key)
        if index is None:
            self.ask(key)
            self.known = False
            self.remember(inst, north, west, now, False)
            return None
        moved = math.hypot(north - self.north, west - self.west) if self.inst == inst else math.inf
        still = moved <= STILL
        seen = self.inst == inst and (still or (now - self.when <= GAP and moved <= RUN_MOST * max(now - self.when, 0.05)))
        if not seen:
            self.known = False
        reach = STEP_ON + RISE * min(moved, ENTRY_MOST)
        surfaces = index.yards.get(yard(north, west))
        if surfaces is None and self.on is not None and self.known:
            surfaces = self.beside(index, north, west, reach)
        if surfaces is None:
            self.known, self.on = True, None
            self.out_north, self.out_west = north, west
        elif not self.known:
            self.on = None
        elif self.on is not None:
            self.on = nearest(surfaces, self.on, reach)
        elif not self.inside:
            self.on = self.entry(index, surfaces, north, west)
        self.remember(inst, north, west, now, surfaces is not None)
        return self.on

    def remember(self, inst, north, west, now, inside):
        self.inst, self.north, self.west, self.when, self.inside = inst, north, west, now, inside

    def beside(self, index, north, west, reach):
        for dn in (-1.0, 0.0, 1.0):
            for dw in (-1.0, 0.0, 1.0):
                got = index.yards.get(yard(north + dn, west + dw))
                if got is not None and nearest(got, self.on, reach) is not None:
                    return got
        return None

    def entry(self, index, surfaces, north, west):
        if self.out_north is None:
            return None
        span = math.hypot(north - self.out_north, west - self.out_west)
        if span > ENTRY_MOST:
            return None
        steps = int(span) + 1
        for k in range(steps + 1):
            t = k / steps
            joined = index.ways_on.get(cell(self.out_north + (north - self.out_north) * t,
                                            self.out_west + (west - self.out_west) * t))
            if joined is None:
                continue
            for h in joined:
                got = nearest(surfaces, h, nav.JOIN_YARDS)
                if got is not None:
                    return got
        return None

    def ask(self, key):
        if key in self.asked:
            return
        self.asked.add(key)
        self.todo.put_nowait(key)
        if self.loader is None:
            self.loader = start_thread("the decks' indexes", self.load)


    def load(self):
        while True:
            try:
                key = self.todo.get(timeout=RETRY)
            except queue.Empty:
                key = None
            if key is not None:
                try:
                    index = self.index_of(*key)
                except Exception:
                    log_error(f"the decks of tile {key}")
                    index = Index(failed=True)
                kept = dict(self.indexes)
                kept[key] = index
                while len(kept) > KEEP_TILES:
                    kept.pop(min(kept, key=lambda k: kept[k].made))
                self.indexes = kept
                self.asked.discard(key)
            now = self.clock()
            stale = [k for k, v in self.indexes.items() if v.failed and now - v.made > RETRY]
            if stale:
                self.indexes = {k: v for k, v in self.indexes.items() if k not in stale}
