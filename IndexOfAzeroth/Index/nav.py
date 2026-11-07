# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
from collections import OrderedDict, namedtuple
import contextlib
import contextvars
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import warnings

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.sparse import csr_matrix, spmatrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import clientfiles as wm
import mainstores
import store
import storewriter
import storedonly
import arrays
import carried
import navstore
import facts
import client
import realign
import routes


class Activity:

    def __init__(self):
        self.lock = threading.Lock()
        self.counts = {"downloading": 0, "working": 0, "ahead": 0}
        self.waits = {}

    @contextlib.contextmanager
    def waiting_on(self, host):
        if wm.in_background():
            yield
            return
        me = object()
        with self.lock:
            self.waits.setdefault(host, {})[id(me)] = time.time()
        try:
            yield
        finally:
            with self.lock:
                self.waits.get(host, {}).pop(id(me), None)
                if not self.waits.get(host):
                    self.waits.pop(host, None)

    @contextlib.contextmanager
    def doing(self, kind):
        kind = "ahead" if wm.in_background() else kind
        with self.lock:
            self.counts[kind] += 1
        try:
            yield
        finally:
            with self.lock:
                self.counts[kind] -= 1

    def now(self):
        with self.lock:
            t = time.time()
            waiting = {host: round(t - min(starts.values()), 1) for host, starts in self.waits.items() if starts}
            return {**self.counts, "waiting": waiting}


ACTIVITY = Activity()
_download = wm.fetch


def _counted_fetch(url, cache=None, max_age=None):
    path = cache and mainstores.standing(os.path.join(wm.CACHE, cache))
    if path and max_age is None and os.path.exists(path):
        return _download(url, cache, max_age)
    with ACTIVITY.doing("downloading"):
        return _download(url, cache, max_age)


wm.fetch = _counted_fetch
import wmonav
NotBuilt = wm.NotBuilt


class NothingToWalk(ValueError):
    pass

CACHE = navstore.CACHE
TERRAIN_VERSION = 8
JOINS_VERSION = 12
ROADS_VERSION = 2
GRAPH_VERSION = 6
SERVED = "served.json"
SWITCH_LOOK = 1.0
_served = [None, None, -math.inf]
ROAD_TEXTURE = re.compile(r"road|cobble|street|paving|brick|flagstone|path|^ironforgerock09browncracks_|^tanariscrackedground_|^winterspringdirt_")
ROAD_SHARE = 0.3
TRAILS = os.path.join(ROOT, "data", "trails.npz")
WAYS = os.path.join(ROOT, "data", "ways.json")
WAY_HEIGHT = 6.0
NPC_TRAILS = os.path.join(ROOT, "data", "npc_trails.npz")
KEPT_WAYS = os.path.join(ROOT, "data", "navways")
WAYS_VERSION = 6
KEPT_WAY_NAME = re.compile(r"w(\d+)-([0-9a-f]{32})\.json")
WAYS_DATA = (WAYS, NPC_TRAILS) + tuple(os.path.join(ROOT, "data", f) for f in ("world.json", "maps.json", "cities.json"))
NPC_TRAIL_Z = 4.0
PORTAL_NEAR = 100.0
CORNER = facts.MAP_CORNER
TILE = facts.TILE_YARDS
CELL = TILE / 128
MAX_UP = 45
CLIMB_UP = 48
SCRAMBLE_COST = 10.0
DUNGEON_MAX_UP = 55
EASY_UP = 30
STEEP_COST = 1.5
MAX_DROP = 11.0
SWIM_DEPTH = 1.3
SWIM_COST = wmonav.SWIM_COST
OFFSHORE_FROM = 12.0
OFFSHORE_SPAN = 48.0
OFFSHORE_COST = 5.0
OCEAN_COST = 3.0
STROKE = 5.0
SWIM_WIDER = 150.0
SWIM_GROW = 5
BUILDING_COST = 4.0
WILD_COST = 3.0
TRAIL_COST = 0.85
SAFE_TRAIL_COST = 0.6
PATH_COST = 0.95
SAFE_COST = 3.0
SAFEST_MARGIN = 10.0
SAFEST_RING_COST = 0.5
SAFEST_COST = 12.0
DANGER_CAP = 6
RED_SLACK = 1.0
MOB_UNDER = 5.0
FLOOR_MOB_Z = 6.0
SEEK_GAIN = 0.35
SEEK_FLOOR = 0.3
GATHER_COST = 0.6
STEP_JOIN = 1.2
OVER_GROUND = 3.0
INDOOR_REACH = 12
SAME_FLOOR_REACH = 15.0
SAME_FLOOR_DETOUR = 20.0
SNAP_CELLS = 4
TALK_REACH = 5.0
POCKET = 9
PROP_REACH = 60.0
PROP_GRID = 40.0
PROP_LATTICE = round(2 * PROP_REACH / PROP_GRID)
YARD_ORIGIN = 17067
YARD_SPAN = 2 * YARD_ORIGIN
YARD_STEP = 0.25
MAX_CELLS = 700 * 700
WIDER_CELLS = 1000 * 1000
MARGIN = 60
PATHS_KEPT = 4096
REACHED_KEPT = 512
DIGESTS_KEPT = 32
HOT_KEPT = 4
NEAR_GAP = 40.0
MAX_SIDE = 1800
HEIGHT_GAP = 8.0
MAX_APART = 4000
FREE_BUILDINGS = ("bridge", "dock", "pier", "walkway", "ramp", "stair", "road", "fence")
MAX_BUILDING = 90
JOIN_YARDS = 4.0
JOIN_UP = 1.5
JOIN_OUT = 8
CLIFF_JUMP = 11.0
DUNGEON_CLIFF_JUMP = 16.0
FALL_FROM = 14.57
FALL_SHARE, FALL_OFF = 0.018, 0.2426
FALL_MARGIN = 3.0
FALL_MOST = (0.5 + FALL_OFF) / FALL_SHARE - FALL_MARGIN
FALL_MARKED = FALL_FROM - FALL_MARGIN
FALL_ALL = 0.5
FALL_COST = 4.0


def fall_share(yards):
    return 0.0 if yards < FALL_FROM else min(1.0, max(0.0, FALL_SHARE * yards - FALL_OFF))


def ground_stands(ground, z, bare=False):
    if ground is None or not np.isfinite(ground):
        return False
    if wmonav.within(ground, z):
        return True
    low = min(z) if isinstance(z, (tuple, list)) else z
    return bare and low - ground <= FALL_MARKED


EASY = carried.switch(__name__, "easy", False)


@contextlib.contextmanager
def easy_way(falls_only=False):
    token = EASY.set("falls" if falls_only else True)
    try:
        yield
    finally:
        EASY.reset(token)
WALL_HITS = 3
KEEP_BUILDINGS_BYTES = 384 << 20
KEEP_TILES = 600
ROOT_ADDED = ("ocean", "area")
OVER_ABOVE = 3
OVER_COST = 40.0
OVER_ROAD_COST = 2.0
CAPITAL_COST = 40.0
CITY_UNDER = 5.0
LONG_BY_GRAPH = True


def way_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def cell_of(north, west):
    return int((CORNER - north) // CELL), int((CORNER - west) // CELL)


GRID_CELLS = 64 * 128
MAP_BOX = (0, 0, GRID_CELLS, GRID_CELLS)


def on_grid(row, col):
    return (row >= 0) & (row < GRID_CELLS) & (col >= 0) & (col < GRID_CELLS)


def grid_tile(cell):
    return min(max(cell // 128, 0), 63)


def world_of(row, col, stride=1):
    return CORNER - (row + stride / 2) * CELL, CORNER - (col + stride / 2) * CELL


def chunk_list(raw):
    at, out = 0, []
    while at + 8 <= len(raw):
        tag = raw[at:at + 4][::-1].decode("latin1")
        size = struct.unpack_from("<I", raw, at + 4)[0]
        out.append((tag, raw[at + 8:at + 8 + size]))
        at += 8 + size
    return out


def triangle_slopes(outer, inner):
    h = CELL / 2
    nw, ne, sw, se = outer[:-1, :-1], outer[:-1, 1:], outer[1:, :-1], outer[1:, 1:]
    out = []
    for (a, pa), (b, pb) in (((nw, (h, h)), (ne, (h, -h))), ((ne, (h, -h)), (se, (-h, -h))),
                             ((se, (-h, -h)), (sw, (-h, h))), ((sw, (-h, h)), (nw, (h, h)))):
        u = np.stack([np.full_like(a, pa[0]), np.full_like(a, pa[1]), a - inner])
        v = np.stack([np.full_like(b, pb[0]), np.full_like(b, pb[1]), b - inner])
        n = np.cross(u, v, axis=0)
        out.append(np.degrees(np.arccos(np.abs(n[2]) / (np.linalg.norm(n, axis=0) + 1e-9))))
    return np.stack(out)


def parse_root(raw, hazards, oceans=()):
    ground = np.full((128, 128), np.nan, np.float32)
    spread = np.zeros((128, 128), np.float32)
    tilt = np.zeros((128, 128), np.float32)
    water = np.full((128, 128), np.nan, np.float32)
    hazard = np.zeros((128, 128), bool)
    ocean = np.zeros((128, 128), bool)
    holes = np.zeros((128, 128), bool)
    area = np.zeros((128, 128), np.uint32)
    chunks = chunk_list(raw)
    mcnks = [body for tag, body in chunks if tag == "MCNK"]
    for body in mcnks:
        if len(body) < 128:
            continue
        flags, ix, iy = struct.unpack_from("<III", body, 0)
        if ix < 16 and iy < 16:
            area[iy * 8:iy * 8 + 8, ix * 8:ix * 8 + 8] = struct.unpack_from("<I", body, 0x34)[0]
        base = struct.unpack_from("<3f", body, 0x68)[2]
        at = 128
        heights = None
        while at + 8 <= len(body):
            tag = body[at:at + 4][::-1].decode("latin1")
            size = struct.unpack_from("<I", body, at + 4)[0]
            if tag == "MCVT" and size >= 580:
                heights = np.frombuffer(body, "<f4", 145, at + 8).astype(np.float32) + base
                break
            at += 8 + size
        if heights is None:
            continue
        rows = [heights[k * 17: k * 17 + 9] for k in range(9)]
        inner = np.array([heights[k * 17 + 9: k * 17 + 17] for k in range(8)])
        outer = np.array(rows)
        r0, c0 = iy * 8, ix * 8
        ground[r0:r0 + 8, c0:c0 + 8] = inner
        corners = np.stack([outer[:-1, :-1], outer[:-1, 1:], outer[1:, :-1], outer[1:, 1:]])
        spread[r0:r0 + 8, c0:c0 + 8] = corners.max(0) - corners.min(0)
        slopes = np.sort(triangle_slopes(outer, inner), axis=0)
        tilt[r0:r0 + 8, c0:c0 + 8] = (slopes[1] + slopes[2]) / 2
        if flags & 0x10000:
            bits = struct.unpack_from("<Q", body, 0x14)[0]
            for k in range(64):
                if bits >> k & 1:
                    holes[r0 + k // 8, c0 + k % 8] = True
        else:
            bits = struct.unpack_from("<H", body, 0x3C)[0]
            for k in range(16):
                if bits >> k & 1:
                    rr, cc = r0 + (k // 4) * 2, c0 + (k % 4) * 2
                    holes[rr:rr + 2, cc:cc + 2] = True
    for tag, body in chunks:
        if tag != "MH2O" or len(body) < 256 * 12:
            continue
        for k in range(256):
            off, layers, _ = struct.unpack_from("<III", body, k * 12)
            cr, cc = (k // 16) * 8, (k % 16) * 8
            for layer in range(layers if off else 0):
                p = off + layer * 24
                if p + 24 > len(body):
                    break
                ltype, _, lo, hi, xo, yo, w, h, bitmap, _ = struct.unpack_from("<HHffBBBBII", body, p)
                exists = None
                if bitmap and bitmap + (w * h + 7) // 8 <= len(body):
                    raw_bits = int.from_bytes(body[bitmap:bitmap + (w * h + 7) // 8], "little")
                    exists = [raw_bits >> i & 1 for i in range(w * h)]
                for y in range(h):
                    for x in range(w):
                        if exists is not None and not exists[y * w + x]:
                            continue
                        r, c = cr + yo + y, cc + xo + x
                        if 0 <= r < 128 and 0 <= c < 128:
                            water[r, c] = hi if np.isnan(water[r, c]) else max(water[r, c], hi)
                            if ltype in hazards:
                                hazard[r, c] = True
                            if ltype in oceans:
                                ocean[r, c] = True
    return {"ground": ground, "spread": spread, "tilt": tilt, "water": water, "hazard": hazard, "ocean": ocean, "holes": holes,
            "area": area}


def parse_buildings(raw, names):
    out = []
    for tag, body in chunk_list(raw):
        if tag != "MODF":
            continue
        for i in range(0, len(body) - 63, 64):
            m = struct.unpack_from("<II3f3f3f3fHHHH", body, i)
            name = names.get(m[0], "").lower()
            if any(k in name for k in FREE_BUILDINGS):
                continue
            (x1, y1, z1), (x2, y2, z2) = m[8:11], m[11:14]
            n1, n2 = CORNER - z1, CORNER - z2
            w1, w2 = CORNER - x1, CORNER - x2
            if abs(n1 - n2) > MAX_BUILDING or abs(w1 - w2) > MAX_BUILDING:
                continue
            out.append((max(n1, n2), min(n1, n2), max(w1, w2), min(w1, w2), min(y1, y2), max(y1, y2)))
    return out


WALKED_ON = ("bridge", "dock", "pier", "walkway")


MIN_LAYERED = 6
MAX_HOUSES = 24
HOUSE_REACH = 120
HOUSE_INSIDE = 6.0


PLACE_COLUMNS = 14
TILT_AT, SCALE_AT = 11, 13


def parse_places(raw, names=None):
    out = []
    for p in modf_rows(raw):
        n1, n2, w1, w2 = p["box"]
        if abs(n1 - n2) < MIN_LAYERED and abs(w1 - w2) < MIN_LAYERED:
            continue
        small = abs(n1 - n2) <= MAX_BUILDING and abs(w1 - w2) <= MAX_BUILDING
        always = not small or any(k in (names or {}).get(p["fid"], "").lower() for k in WALKED_ON)
        out.append((p["fid"], p["uid"], *p["at"], p["yaw"], max(n1, n2), min(n1, n2), max(w1, w2), min(w1, w2),
                    1.0 if always else 0.0, *p["tilt"], p["scale"]))
    return np.array(out, np.float64).reshape(-1, PLACE_COLUMNS)


def modf_rows(raw):
    out = []
    for tag, body in chunk_list(raw):
        if tag != "MODF":
            continue
        for i in range(0, len(body) - 63, 64):
            m = struct.unpack_from("<II3f3f3f3fHHHH", body, i)
            (x1, _, z1), (x2, _, z2) = m[8:11], m[11:14]
            px, py, pz = m[2:5]
            out.append({"fid": m[0], "uid": m[1], "at": (CORNER - pz, CORNER - px, py), "yaw": m[6], "tilt": (m[5], m[7]),
                        "box": (CORNER - z1, CORNER - z2, CORNER - x1, CORNER - x2), "doodad_set": m[15],
                        "scale": (m[17] or 1024) / 1024})
    return out


DOODAD_COLUMNS = 10


def parse_doodads(raw):
    out = []
    for tag, body in chunk_list(raw):
        if tag != "MDDF":
            continue
        for i in range(0, len(body) - 35, 36):
            fid, uid, px, py, pz, rx, ry, rz, scale, flags = struct.unpack_from("<II3f3fHH", body, i)
            if flags & 0x40:
                out.append((fid, uid, CORNER - pz, CORNER - px, py, ry, scale / 1024, rx, rz))
    return np.array(out, np.float64).reshape(-1, DOODAD_COLUMNS - 1)


def doodad_reach(geo, yaw, scale, tilt):
    if geo is None or not len(geo["tris"]):
        return 0.0
    p = wmonav.place(np.asarray(geo["verts"], np.float64)[np.unique(geo["tris"])], (0.0, 0.0, 0.0), yaw, scale, tilt)
    return float(np.max(np.hypot(p[:, 0], p[:, 1])))


def with_reach(rows, version):
    rows = np.asarray(rows, np.float64).reshape(-1, DOODAD_COLUMNS - 1)
    fids = sorted({int(f) for f in rows[:, 0]})
    with ThreadPoolExecutor(8) as pool:
        shapes = dict(zip(fids, pool.map(lambda fid: _shape(wmonav.m2_geometry, fid, version), fids)))
    failed = [fid for fid, geo in shapes.items() if geo is FAILED]
    if failed:
        raise OSError(f"{len(failed)} doodad shapes not to be had now")
    reach = [doodad_reach(shapes[int(d[0])], d[5], d[6], (d[7], d[8])) for d in rows]
    return np.column_stack([rows, np.asarray(reach, np.float64).reshape(-1, 1)]).reshape(-1, DOODAD_COLUMNS)


def reaches(rows, gn, gw):
    rows = np.asarray(rows, np.float64).reshape(-1, DOODAD_COLUMNS)
    dn = np.maximum(np.abs(rows[:, 2] - gn * PROP_GRID) - PROP_REACH, 0.0)
    dw = np.maximum(np.abs(rows[:, 3] - gw * PROP_GRID) - PROP_REACH, 0.0)
    return (rows[:, 9] > 0) & (np.hypot(dn, dw) <= rows[:, 9])


def doodad_spots(rows):
    rows = np.asarray(rows, np.float64).reshape(-1, DOODAD_COLUMNS)
    rows = rows[rows[:, 9] > 0]
    if not len(rows):
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    span = int(math.ceil((PROP_REACH + rows[:, 9].max()) / PROP_GRID)) + 1
    gn0, gw0 = np.round(rows[:, 2] / PROP_GRID).astype(np.int64), np.round(rows[:, 3] / PROP_GRID).astype(np.int64)
    out_n, out_w = [], []
    for dn in range(-span, span + 1):
        for dw in range(-span, span + 1):
            gn, gw = gn0 + dn, gw0 + dw
            ok = reaches(rows, gn, gw)
            out_n.append(gn[ok])
            out_w.append(gw[ok])
    return np.concatenate(out_n), np.concatenate(out_w)


def alpha_map(mcal, at, flags, big):
    if flags & 0x200:
        out, k = bytearray(), at
        while len(out) < 4096 and k < len(mcal):
            head, k = mcal[k], k + 1
            n = head & 0x7F
            if head & 0x80:
                out += mcal[k:k + 1] * n
                k += 1
            else:
                out += mcal[k:k + n]
                k += n
        return np.frombuffer(bytes(out[:4096]).ljust(4096, b"\0"), np.uint8).reshape(64, 64) / np.float32(255)
    if big:
        raw = np.frombuffer(mcal[at:at + 4096].ljust(4096, b"\0"), np.uint8)
        return raw.reshape(64, 64) / np.float32(255)
    raw = np.frombuffer(mcal[at:at + 2048].ljust(2048, b"\0"), np.uint8)
    return np.stack([raw & 0x0F, raw >> 4], 1).reshape(64, 64) / np.float32(15)


def parse_tex0(raw, big, names):
    top = chunk_list(raw)
    tex = []
    for tag, body in top:
        if tag == "MDID":
            tex = [names.get(f, "") for f in struct.unpack_from(f"<{len(body) // 4}I", body)]
        elif tag == "MTEX" and not tex:
            tex = [t.decode("latin1") for t in body.split(b"\0") if t]
    road = [bool(ROAD_TEXTURE.search(t.replace("\\", "/").rsplit("/", 1)[-1].lower())) for t in tex]
    share = np.zeros((128, 128), np.float32)
    if not any(road):
        return share.astype(np.uint8)
    for k, chunk in enumerate(body for tag, body in top if tag == "MCNK"):
        if k >= 256:
            break
        sub = dict(chunk_list(chunk))
        mcly, mcal = sub.get("MCLY", b""), sub.get("MCAL", b"")
        layers = [struct.unpack_from("<IIIi", mcly, i * 16) for i in range(len(mcly) // 16)]
        if not any(tid < len(road) and road[tid] for tid, *_ in layers):
            continue
        cover, painted = np.zeros((64, 64), np.float32), np.zeros((64, 64), np.float32)
        for i in range(len(layers) - 1, -1, -1):
            tid, flags, at, _ = layers[i]
            alpha = np.ones((64, 64), np.float32) if i == 0 else \
                alpha_map(mcal, at, flags, big) if flags & 0x100 else np.zeros((64, 64), np.float32)
            seen = alpha * (1 - cover)
            cover += seen
            if tid < len(road) and road[tid]:
                painted += seen
        cy, cx = divmod(k, 16)
        share[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = painted.reshape(8, 8, 8, 8).mean(axis=(1, 3))
    return np.clip(np.rint(share * 255), 0, 255).astype(np.uint8)


def mover_ends(m):
    if m.get("stops"):
        return [(m["a"][0], m["a"][1], m["stops"][0][2]), (m["b"][0], m["b"][1], m["stops"][1][2])]
    return [m["a"], m["b"]]


BOARD_YARDS = 10.0


def ride_yards(m):
    return routes.ride_seconds(m) * facts.RUN_SPEED + BOARD_YARDS


def same_map_portals(doors):
    out = []
    for d in doors:
        a, b = d.get("outside") or (), d.get("inside") or ()
        if not d.get("oneWay") or len(a) < 4 or len(b) < 4 or a[0] != b[0] or math.dist(a[1:3], b[1:3]) > PORTAL_NEAR:
            continue
        out.append({"name": d.get("to") or d.get("dungeon"), "map": a[0], "a": list(a[1:4]), "b": list(b[1:4]),
                    "seconds": 0, "oneWay": True, **({"side": d["side"]} if d.get("side") else {})})
    return out


class SingleFlight:

    def __init__(self):
        self.lock = threading.Lock()
        self.calls = {}

    def do(self, key, fn):
        with self.lock:
            call = self.calls.get(key)
            owner = call is None
            if owner:
                call = self.calls[key] = {"done": threading.Event(), "result": None, "error": None}
        if not owner:
            call["done"].wait()
            if call["error"] is not None:
                raise call["error"]
            return call["result"]
        try:
            call["result"] = fn()
            return call["result"]
        except BaseException as e:
            call["error"] = e
            raise
        finally:
            with self.lock:
                self.calls.pop(key, None)
            call["done"].set()



def code_rules():
    return {"terrain": TERRAIN_VERSION, "joins": JOINS_VERSION, "layers": wmonav.VERSION, "shapes": wmonav.GEO_VERSION,
            "roads": ROADS_VERSION, "props": wmonav.PROPS_VERSION, "graph": GRAPH_VERSION}


def served_path():
    return os.path.join(CACHE, SERVED)


def switch_look():
    path, now = served_path(), time.monotonic()
    got = _served[:]
    if got[0] is not None and got[0][0] == path and now - got[2] < SWITCH_LOOK:
        return got[0], got[1]
    key = (path, navstore.stamp(path, under=False))
    read = got[1] if got[0] == key else None
    if got[0] != key and key[1] is not None:
        try:
            data = navstore.load_json(path, None, under=False)
            rules = data.get("rules") if isinstance(data, dict) else None
            if isinstance(rules, dict):
                read = ({k: int(rules.get(k, v)) for k, v in code_rules().items()}, float(data.get("since") or 0.0))
        except (OSError, ValueError, TypeError):
            read = None
    _served[:] = [key, read, now]
    return key, read


def switched():
    return switch_look()[1]


def served_rules():
    got = switched()
    return dict(got[0]) if got else code_rules()


def rules_in_force():
    return served_rules() if wm.serving() else code_rules()


def switch_served(rules, clock=time.time):
    os.makedirs(CACHE, exist_ok=True)
    store.save_json(served_path(), {"rules": dict(rules), "since": clock()}, indent=None)
    _served[2] = -math.inf


def tile_path(instance, col, row, rules=None):
    return os.path.join(CACHE, f"t{(rules or rules_in_force())['terrain']}-{instance}_{col}_{row}.npz")


def road_path(instance, col, row, rules=None):
    return os.path.join(CACHE, f"r{(rules or rules_in_force())['roads']}-{instance}_{col}_{row}.npz")


def terrain_textures(kept=False):
    out = {}
    for line in wm.listed(**wm.TERRAIN, kept=kept):
        fid, _, name = line.strip().partition(";")
        if fid.isdigit():
            out[int(fid)] = name.lower()
    return out


def store_stamp():
    return navstore.store_stamp(CACHE) + (switch_look()[0],)


def array_digest(a):
    a = np.ascontiguousarray(a)
    return a.shape, str(a.dtype), hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest()


def trails_sorted(cells):
    a = np.sort(np.asarray(cells, np.int64))
    return a, np.concatenate((np.zeros(1, np.int64), np.cumsum(a)))


def trails_mark(saved, box):
    if saved is None or not len(saved[0]):
        return 0, 0
    cells, sums = saved
    r0, c0, r1, c1 = box
    rows = np.arange(max(r0, int(cells[0]) // GRID_CELLS), min(r1, int(cells[-1]) // GRID_CELLS + 1), dtype=np.int64)
    c0, c1 = min(max(c0, 0), GRID_CELLS), min(max(c1, 0), GRID_CELLS)
    if not len(rows) or c0 >= c1:
        return 0, 0
    lo, hi = np.searchsorted(cells, rows * GRID_CELLS + c0), np.searchsorted(cells, rows * GRID_CELLS + c1)
    return int((hi - lo).sum()), int((sums[hi] - sums[lo]).sum())


_trails_read = contextvars.ContextVar(f"{__name__}.trails_read", default=())


@contextlib.contextmanager
def noting_trails():
    found = []
    token = _trails_read.set(_trails_read.get() + (found,))
    try:
        yield found
    finally:
        _trails_read.reset(token)


def note_trails(instance, box):
    for found in _trails_read.get():
        found.append((instance, box))


def trails_box(read, instance):
    boxes = [b for i, b in read if i == instance and b is not None]
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def ways_folder():
    named = os.environ.get("DGG_NAVWAYS")
    return KEPT_WAYS if named is None else named or None


def kept_fresh(checked, key, now, stamp_of):
    was = checked.get(key)
    if was is None:
        return False
    if was[1] == now:
        return True
    if stamp_of() != was[0]:
        return False
    checked[key] = (was[0], now)
    return True


def map_index_path(rules=None):
    return os.path.join(CACHE, f"maps{(rules or rules_in_force())['terrain']}.json")


def building_key(instance, fid, uid):
    return f"{instance}-{fid}-{uid}"


TILTED = "-tilted"
SCALED = "-scaled"
PLACED_SUFFIXES = ("", TILTED, SCALED, TILTED + SCALED)
PLACED_NAME = re.compile(rf"(\d+)-(\d+)-(\d+)((?:{TILTED})?(?:{SCALED})?)")


def place_tilt(place):
    return (float(place[TILT_AT]), float(place[TILT_AT + 1])) if len(place) > TILT_AT + 1 else (0.0, 0.0)


def place_scale(place):
    return float(place[SCALE_AT]) if len(place) > SCALE_AT else 1.0


def place_suffix(place):
    return (TILTED if any(place_tilt(place)) else "") + (SCALED if place_scale(place) != 1.0 else "")


def place_key(instance, place):
    return building_key(instance, int(place[0]), int(place[1])) + place_suffix(place)


def places_behind(places):
    return places is not None and len(places) > 0 and np.asarray(places).shape[1] < PLACE_COLUMNS


def full_place(place):
    row = np.zeros(PLACE_COLUMNS, np.float64)
    row[SCALE_AT] = 1.0
    row[:min(len(place), PLACE_COLUMNS)] = np.asarray(place, np.float64)[:PLACE_COLUMNS]
    return row


def props_key(instance, gn, gw):
    return f"{instance}-props-{gn}-{gw}"


def lattice_areas(r0, c0, r1, c1):
    north, south = CORNER - r0 * CELL, CORNER - r1 * CELL
    west, east = CORNER - c0 * CELL, CORNER - c1 * CELL
    span = PROP_LATTICE * PROP_GRID
    return [(kn * PROP_LATTICE, kw * PROP_LATTICE)
            for kn in range(math.floor((south + PROP_REACH) / span), math.floor((north + PROP_REACH) / span) + 1)
            for kw in range(math.floor((east + PROP_REACH) / span), math.floor((west + PROP_REACH) / span) + 1)]


def props_bounds(gn, gw):
    cn, cw = gn * PROP_GRID, gw * PROP_GRID
    return cn + PROP_REACH, cw + PROP_REACH, cn - PROP_REACH, cw - PROP_REACH


def layers_name(key, rules=None):
    r = rules or rules_in_force()
    props = "-props-" in key
    made = f"{r['props'] if props else r['layers']}.{r['shapes']}" + (f".{r['terrain']}" if props else "")
    return f"l{made}-{key}.npz"


def joins_name(key, rules=None):
    r = rules or rules_in_force()
    return f"j{r['joins']}.{r['terrain']}-{layers_name(key, r)}"


def graph_made_by(rules=None):
    r = rules or rules_in_force()
    return f"{r['graph']}.{r['terrain']}.{r['roads']}.{r['joins']}.{r['layers']}"


def graph_name(key, rules=None):
    return f"v{graph_made_by(rules)}-{key}.npz"


def floors_name(key, rules=None):
    r = rules or rules_in_force()
    return f"c{r['graph']}-{joins_name(key, r)}"


def old_combined(key):
    layers = f"l11.4{'.7' if '-props-' in key else ''}-{key}.npz"
    return os.path.join(CACHE, f"b7.11-{key}.npz"), layers, f"j7.7-{layers}"


def layers_kept(key):
    old, layers, _ = old_combined(key)
    return navstore.exists(os.path.join(CACHE, layers_name(key))) or (layers == layers_name(key) and navstore.exists(old))


def layers_kept_since_switch(key):
    path = os.path.join(CACHE, layers_name(key))
    old, layers, _ = old_combined(key)
    if not navstore.exists(path) and layers == layers_name(key):
        path = old
    try:
        return navstore.getmtime(path) >= wm.switched_since()
    except OSError:
        return False


def layers_kept_from_before(key):
    return layers_kept(key) and not layers_kept_since_switch(key)



def placed_digest(*parts):
    h = hashlib.sha1()
    for part in parts:
        a = np.ascontiguousarray(part, np.float64)
        h.update(repr(a.shape).encode())
        h.update(a.tobytes())
    return np.frombuffer(h.digest(), np.uint8)


NOWHERE = placed_digest()


def empty_area(names):
    return set(names) - {"placed"} == {"heights"}


def kept_marks(path):
    for _ in range(store.SWAP_TRIES):
        try:
            with navstore.opened(path) as f, np.load(f) as z:
                names = set(z.files)
                return {"sources": [str(s) for s in z["sources"]] if "sources" in names else [],
                        "placed": z["placed"] if "placed" in names else None, "empty": empty_area(names)}
        except FileNotFoundError:
            return None
        except PermissionError:
            time.sleep(store.SWAP_WAIT)
        except arrays.UNREADABLE:
            arrays.set_aside(path)
            return None
    return None


def made_good(path, marks, placed):
    try:
        if navstore.getmtime(path) >= wm.switched_since():
            return True
        if marks["placed"] is None or not np.array_equal(marks["placed"], placed()):
            return False
        sources = marks["sources"]
        if marks["empty"]:
            if marks.get("stands_for") is None:
                return False
            sources = list(marks["stands_for"]())
            if not sources:
                wm.mark_checked(path)
                return True
        return wm.still_good(path, sources)
    except OSError:
        return False


def walking_good(key, placed_of, sources_of=None):
    lpath, jpath = os.path.join(CACHE, layers_name(key)), os.path.join(CACHE, joins_name(key))
    made = {path: made_at(path) for path in (lpath, jpath)}
    marks = kept_marks(lpath)
    digest = []

    def placed():
        if not digest:
            digest.append(placed_of())
        return digest[0]
    if marks is not None:
        marks["stands_for"] = sources_of
    if marks is None or not made_good(lpath, marks, placed):
        return False, False
    if marks["empty"]:
        return True, True
    if not as_new(made[jpath], [made[lpath]]):
        return True, False
    joins = kept_marks(jpath)
    if joins is None or not made_good(jpath, joins, placed):
        return True, False
    with contextlib.suppress(OSError):
        if not as_new(made_at(jpath), [made_at(lpath)]):
            wm.mark_checked(jpath)
    return True, True


def keep_added(path, tile, sources):
    try:
        arrays.save_npz(path, **tile, sources=np.array(sources))
    except OSError:
        pass


def tile_kept(instance, col, row):
    path = tile_path(instance, col, row)
    marks = kept_marks(path)
    try:
        if marks is None or not wm.still_good(path, marks["sources"]):
            return False
        with navstore.opened(path) as f, np.load(f) as z:
            names = set(z.files)
            return "none" in names or (all(k in names for k in ROOT_ADDED)
                                       and not places_behind(z["places"] if "places" in names else None))
    except (OSError, *arrays.UNREADABLE):
        return False


LAYER_KEYS = ("heights", "swim", "meta", "data", "indices", "indptr")
JOIN_KEYS = ("joins", "blocks", "floored", "walls", "barred", "onto", "jumped")
JOINS_ADDED = {"jumped": np.zeros(0, np.int64)}
DoodadWalls = namedtuple("DoodadWalls", ("barred", "jumped", "yards"))
NO_WALLS = DoodadWalls(np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64))


def split_old(key):
    old, layers, joins = old_combined(key)
    if layers != layers_name(key) or navstore.exists(os.path.join(CACHE, layers)) or not navstore.exists(old):
        return
    b = kept_arrays(old, ("heights",))
    if b is None:
        return
    if set(b) == {"heights"}:
        arrays.save_npz(os.path.join(CACHE, layers), heights=b["heights"])
    elif set(LAYER_KEYS) <= set(b):
        arrays.save_npz(os.path.join(CACHE, layers), **{k: b[k] for k in LAYER_KEYS})
        if joins == joins_name(key) and set(JOIN_KEYS) <= set(b):
            arrays.save_npz(os.path.join(CACHE, joins), **{k: b[k] for k in JOIN_KEYS}, nodes=np.array(len(b["indptr"]) - 1))
    else:
        arrays.set_aside(old)
        return
    with contextlib.suppress(OSError):
        os.remove(old)


def made_at(path):
    try:
        return navstore.getmtime(path)
    except OSError:
        return None


def as_new(made, sources):
    return made is not None and all(s is None or s <= made for s in sources)


def kept_arrays(path, keys, any_build=False):
    try:
        if navstore.getmtime(path) < (0.0 if any_build else wm.switched_since()):
            return None
    except OSError:
        return None
    b = navstore.load_npz(path)
    if b is None:
        return None
    if not set(keys) <= set(b):
        name = os.path.basename(path)
        if name_under(name, code_rules()) in (None, name):
            arrays.set_aside(path)
        return None
    return b


def layer_arrays(layers, graph):
    return {"heights": layers.heights, "swim": layers.swim, "meta": np.array([layers.top, layers.left, layers.res]),
            "data": graph.data, "indices": graph.indices, "indptr": graph.indptr}


def layers_of(b):
    try:
        layers = wmonav.Layers.from_arrays(b["heights"], b["swim"], *b["meta"])
        moves = csr_matrix((b["data"], b["indices"], b["indptr"]), shape=(len(layers.nodes), len(layers.nodes)))
        return layers, wmonav.priced(layers, moves)
    except (KeyError, TypeError, IndexError) as e:
        raise ValueError(f"saved layers that don't fit together: {e}") from e


def floor_tops(layers):
    nodes = layers.nodes
    north = layers.top - (nodes[:, 0] + 0.5) * layers.res
    west = layers.left - (nodes[:, 1] + 0.5) * layers.res
    cells = ((CORNER - north) // CELL).astype(np.int64) * 8192 + ((CORNER - west) // CELL).astype(np.int64)
    z = layers.heights[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
    order = np.lexsort((z, cells))
    cells, z = cells[order], z[order]
    last = np.r_[cells[1:] != cells[:-1], True] if len(cells) else np.zeros(0, bool)
    return cells[last], z[last]


def join_arrays(b, keys=JOIN_KEYS):
    if b is None or any(k not in b and k not in JOINS_ADDED for k in keys):
        return None
    return tuple(b[k] if k in b else JOINS_ADDED[k] for k in keys)


def kept_joins(jpath, lpath, nodes, any_build=False):
    layers_made = made_at(lpath)
    if layers_made is None or not as_new(made_at(jpath), [layers_made]):
        return None
    j = kept_arrays(jpath, tuple(k for k in JOIN_KEYS if k not in JOINS_ADDED) + ("nodes",), any_build)
    try:
        return join_arrays(j) if j is not None and int(j["nodes"]) == nodes else None
    except (TypeError, ValueError):
        return None


KEPT_NAME = re.compile(r"(?:c(\d+)-)?(?:j(\d+(?:\.\d+)*)-)?([tglbrv])(\d+(?:\.\d+)*)-([\w-]+)\.npz")


def made_from(name):
    m = KEPT_NAME.fullmatch(name)
    if not m or m[2] is None:
        return []
    layers = f"{m[3]}{m[4]}-{m[5]}.npz"
    return [name.split("-", 1)[1], layers] if m[1] is not None else [layers]


def name_under(name, rules=None):
    m = KEPT_NAME.fullmatch(name)
    if not m:
        return None
    r = rules or rules_in_force()
    floors, joins, kind, key = m[1], m[2], m[3], m[5]
    if floors is not None:
        return floors_name(key, r) if kind == "l" and joins is not None else None
    if joins is not None:
        return joins_name(key, r) if kind == "l" else None
    if kind == "t":
        return f"t{r['terrain']}-{key}.npz"
    if kind == "r":
        return f"r{r['roads']}-{key}.npz"
    if kind == "v":
        return graph_name(key, r)
    if kind == "g":
        return f"g{r['shapes']}-{key}.npz"
    return layers_name(key, r)


def placed_twins(name):
    m = KEPT_NAME.fullmatch(name)
    b = PLACED_NAME.fullmatch(m[5]) if m and m[3] == "l" else None
    if not b:
        return []
    stem = name[:-len(f"{b[4]}.npz")]
    return [f"{stem}{s}.npz" for s in PLACED_SUFFIXES if s != b[4] and b[4] in s]


def prune_cache():
    def listed(folder):
        try:
            return set(os.listdir(folder))
        except OSError:
            return set()
    names, gone = listed(CACHE), 0
    have = names | navstore.packed_names(CACHE) if names else names
    served, code = served_rules(), code_rules()
    for name in names:
        new = name_under(name, served)
        if new is None:
            continue
        if name == new or (code != served and name == name_under(name, code)):
            old = any(t in have for t in placed_twins(name))
        else:
            old = new in have or any(t in have for t in placed_twins(new))
        if old:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(CACHE, name))
                gone += 1
    folder = ways_folder()
    ways = listed(folder) if folder else set()
    for name in ways:
        m = KEPT_WAY_NAME.fullmatch(name)
        if m and int(m[1]) != WAYS_VERSION and f"w{WAYS_VERSION}-{m[2]}.json" in ways:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(folder, name))
                gone += 1
    return gone


class Terrain:

    def __init__(self, fetch_tile=None, client_files=None, fetch_roads=None):
        self.lock = threading.Lock()
        self.tiles = OrderedDict()
        self.checked = {}
        self.tables = None
        self.wdts = {}
        self.index_read = (None, {})
        self.fetch_tile = fetch_tile or self._fetch_tile
        self.client_files = fetch_tile is None if client_files is None else client_files
        self.roads = OrderedDict()
        self.roads_checked = {}
        self.fetch_roads = fetch_roads or (self._fetch_roads if fetch_tile is None else lambda inst, col, row: None)
        self.flight = SingleFlight()
        self.trails_lock = threading.Lock()
        self.trails, self.trails_saved = self._load_trails()
        self.trails_dirty = 0
        self.wanted = None

    def want(self, instance, north, west):
        if self.wanted:
            try:
                self.wanted(instance, north, west)
            except Exception:
                pass

    def forget(self):
        with self.lock:
            self.tiles.clear()
            self.checked.clear()
            self.roads.clear()
            self.roads_checked.clear()
            self.wdts.clear()
            self.tables = None
            self.index_read = (None, {})
            self.__dict__.pop("_npc", None)


    def client_tables(self):
        tables = self.tables
        if tables is not None:
            return tables
        with self.lock:
            if self.tables is None:
                stored = wm.serving()
                maps = {int(r["ID"]): r for r in client.rows("Map", stored=stored)}
                liquids = client.rows("LiquidType", stored=stored)
                hazards = {int(r["ID"]) for r in liquids if any(k in (r.get("Name") or "").lower() for k in ("lava", "magma", "slime", "fire"))}
                oceans = {int(r["ID"]) for r in liquids if "ocean" in (r.get("Name") or "").lower()}
                names = wm.listfile(kept=True)[0] if wm.serving() else wm.listfile()[0]
                self.tables = (maps, hazards, names, oceans)
            return self.tables

    def wdt(self, instance):
        map_row = self.client_tables()[0].get(instance)
        if not map_row or not int(map_row["WdtFileDataID"] or 0):
            return None
        if instance not in self.wdts:
            self.wdts[instance] = wm.chunks(wm.kept_file(f"wdt-{map_row['WdtFileDataID']}.wdt")) if wm.serving() \
                else wm.map_file(map_row, wm.installed_version())
        return self.wdts[instance]

    def on_map(self, instance, col, row):
        if not (0 <= col < 64 and 0 <= row < 64):
            return False
        if self.fetch_tile != self._fetch_tile:
            return True
        entry = self.indexed(instance) if wm.serving() else None
        if entry is not None and "tiles" in entry:
            return (col, row) in entry["tiles"]
        wdt = self.wdt(instance)
        maid = wdt.get("MAID", b"") if wdt else b""
        return len(maid) >= (row * 64 + col) * 32 + 4 and bool(struct.unpack_from("<I", maid, (row * 64 + col) * 32)[0])

    def is_dungeon(self, instance):
        row = self.client_tables()[0].get(instance)
        return bool(row) and row.get("InstanceType", "0") not in ("0", "")

    def indexed(self, instance):
        path = map_index_path()
        stamp = navstore.stamp(path)
        if stamp != self.index_read[0]:
            read = navstore.load_json(path, {})
            for entry in read.values():
                if isinstance(entry, dict) and "tiles" in entry:
                    entry["tiles"] = {(int(c), int(r)) for c, r in entry["tiles"]}
            self.index_read = (stamp, read)
        return self.index_read[1].get(str(instance))

    def map_kind(self, instance):
        entry = self.indexed(instance) if wm.serving() else None
        if entry is not None:
            return entry.get("kind")
        wdt = self.wdt(instance)
        if not wdt:
            return None
        maid = wdt.get("MAID", b"")
        if any(struct.unpack_from("<I", maid, i)[0] for i in range(0, len(maid) - 31, 32)):
            return "terrain"
        return "building" if "MODF" in wdt else None

    def global_building(self, instance):
        entry = self.indexed(instance) if wm.serving() else None
        if entry and entry.get("global"):
            return np.array(entry["global"][:10], np.float64)
        body = self.wdt(instance).get("MODF", b"")
        m = struct.unpack_from("<II3f3f3f3fHHHH", body, 0)
        px, py, pz = m[2:5]
        return np.array([m[0], m[1], -pz, -px, py, m[6], 0, 0, 0, 0], np.float64)

    def _fetch_tile(self, instance, col, row):
        path = tile_path(instance, col, row)

        def load():
            tile = navstore.load_npz(path)
            if wm.serving():
                if tile is None:
                    try:
                        off = not self.on_map(instance, col, row)
                    except NotBuilt:
                        off = False
                    if off:
                        return {"none": np.array(True)}
                    self.want(instance, *world_of(row * 128 + 64, col * 128 + 64))
                    raise NotBuilt(("tile", instance, col, row))
                tile.pop("sources", None)
                if "none" not in tile:
                    tile.setdefault("ocean", np.zeros((128, 128), bool))
                    tile.setdefault("area", np.zeros((128, 128), np.uint32))
                return tile
            middle = (instance, *world_of(row * 128, col * 128, 128))
            with realign.working("paths", middle, when=realign.kept_from_before(path)):
                if tile is not None:
                    sources = [str(s) for s in tile.pop("sources", ())]
                    if wm.still_good(path, sources):
                        missing = [k for k in ROOT_ADDED if k not in tile] if "none" not in tile else []
                        if missing:
                            self._add_root(instance, col, row, path, tile, sources, missing)
                        if "none" not in tile and places_behind(tile.get("places")):
                            self._read_places_again(instance, col, row, path, tile, sources)
                        return tile
                with ACTIVITY.doing("working"):
                    return self._read_tile(instance, col, row, path)
        return self.flight.do(("tile", instance, col, row), load)

    def _add_root(self, instance, col, row, path, tile, sources, missing):
        blank = {"ocean": np.zeros((128, 128), bool), "area": np.zeros((128, 128), np.uint32)}
        wdt = self.wdt(instance)
        maid = wdt.get("MAID", b"") if wdt else b""
        at = (row * 64 + col) * 32
        if len(maid) < at + 32 or not struct.unpack_from("<I", maid, at)[0]:
            tile.update({k: blank[k] for k in missing})
            return
        fid = struct.unpack_from("<I", maid, at)[0]
        _, hazards, _, oceans = self.client_tables()
        try:
            raw = wm.fetch(wm.file_address(fid, wm.installed_version()), f"adt-{fid}.adt")
            parsed = parse_root(raw, hazards, oceans)
            tile.update({k: parsed[k] for k in missing})
        except OSError:
            tile.update({k: blank[k] for k in missing})
            return
        keep_added(path, tile, sources)

    def _read_places_again(self, instance, col, row, path, tile, sources):
        wdt = self.wdt(instance)
        maid = wdt.get("MAID", b"") if wdt else b""
        at = (row * 64 + col) * 32
        obj = struct.unpack_from("<8I", maid, at)[1] if len(maid) >= at + 32 else 0
        if not obj:
            return
        try:
            raw = wm.fetch(wm.file_address(obj, wm.installed_version()), f"obj-{obj}.adt")
        except OSError:
            return
        tile["places"] = parse_places(raw, self.client_tables()[2])
        keep_added(path, tile, sources)

    def _read_tile(self, instance, col, row, path):
        wdt = self.wdt(instance)
        if not wdt:
            return None
        version = wm.installed_version()
        maid = wdt.get("MAID", b"")
        at = (row * 64 + col) * 32
        if not (0 <= col < 64 and 0 <= row < 64) or len(maid) < at + 32:
            return None
        files = struct.unpack_from("<8I", maid, at)
        maps, hazards, names, oceans = self.client_tables()
        used = {f"wdt-{maps[instance]['WdtFileDataID']}.wdt"}
        if not files[0]:
            tile = {"none": np.array(True)}
        else:
            with wm.recording() as fetched, ThreadPoolExecutor(2) as pool:
                want_obj = pool.submit(wm.fetch, wm.file_address(files[1], version),
                                       f"obj-{files[1]}.adt") if files[1] else None
                root = pool.submit(wm.fetch, wm.file_address(files[0], version), f"adt-{files[0]}.adt")
                obj = want_obj.result() if want_obj else b""
                tile = parse_root(root.result(), hazards, oceans)
            tile["buildings"] = np.array(parse_buildings(obj, names) if obj else [], np.float32).reshape(-1, 6)
            tile["places"] = parse_places(obj, names) if obj else np.zeros((0, PLACE_COLUMNS))
            rows = parse_doodads(obj) if obj else np.zeros((0, DOODAD_COLUMNS - 1))
            tile["doodads"] = with_reach(rows, version)
            used |= fetched | {f"m2-{int(fid)}.m2" for fid in np.unique(rows[:, 0])}
        os.makedirs(CACHE, exist_ok=True)
        arrays.save_npz(path, **tile, sources=np.array(sorted(used)))
        return tile

    def _fetch_roads(self, instance, col, row):
        path = road_path(instance, col, row)

        def load():
            kept = navstore.load_npz(path)
            if wm.serving():
                if kept is None:
                    self.want(instance, *world_of(row * 128 + 64, col * 128 + 64))
                    wm.note_unbuilt(("roads", instance, col, row))
                    return None
                return kept.get("road")
            middle = (instance, *world_of(row * 128, col * 128, 128))
            with realign.working("paths", middle, when=realign.kept_from_before(path)):
                if kept is not None and wm.still_good(path, [str(s) for s in kept.get("sources", ())]):
                    return kept.get("road")
                with ACTIVITY.doing("working"):
                    return self._read_roads(instance, col, row, path)
        return self.flight.do(("roads", instance, col, row), load)

    def _read_roads(self, instance, col, row, path):
        wdt = self.wdt(instance)
        maid = wdt.get("MAID", b"") if wdt else b""
        at = (row * 64 + col) * 32
        files = struct.unpack_from("<8I", maid, at) if 0 <= col < 64 and 0 <= row < 64 and len(maid) >= at + 32 else (0,) * 8
        used = {f"wdt-{self.client_tables()[0][instance]['WdtFileDataID']}.wdt"} if wdt else set()
        road = None
        if files[0] and files[3]:
            with wm.recording() as fetched:
                raw = wm.fetch(wm.file_address(files[3], wm.installed_version()), f"tex0-{files[3]}.adt")
            used |= fetched
            mphd = struct.unpack_from("<I", wdt.get("MPHD", b"\0\0\0\0"), 0)[0]
            road = parse_tex0(raw, bool(mphd & 0x84), terrain_textures(kept=wm.serving()))
            road = road if road.any() else None
        os.makedirs(CACHE, exist_ok=True)
        if road is None:
            arrays.save_npz(path, none=np.array(True), sources=np.array(sorted(used)))
        else:
            arrays.save_npz(path, road=road, sources=np.array(sorted(used)))
        return road

    def roads_for(self, instance, r0, c0, r1, c1):
        needed, have = self.needed(r0, c0, r1, c1), {}
        now = store_stamp()
        with self.lock:
            for k in needed:
                key = (instance, *k)
                if key in self.roads and kept_fresh(self.roads_checked, key, now, lambda: navstore.stamp(road_path(*key))):
                    self.roads.move_to_end(key)
                    have[k] = self.roads[key]
        missing = [k for k in needed if k not in have]
        stamps = {k: (navstore.stamp(road_path(instance, *k)), now) for k in missing}
        for k in missing:
            have[k] = self.fetch_roads(instance, *k)
        with self.lock:
            for k in missing:
                if have[k] is None and wm.serving() and stamps[k][0] is None:
                    continue
                self.roads[(instance, *k)] = have[k]
                self.roads_checked[(instance, *k)] = stamps[k]
            while len(self.roads) > KEEP_TILES:
                self.roads_checked.pop(self.roads.popitem(last=False)[0], None)
        return have

    @staticmethod
    def needed(r0, c0, r1, c1):
        return [(tc, tr) for tr in range(r0 // 128, (r1 - 1) // 128 + 1) for tc in range(c0 // 128, (c1 - 1) // 128 + 1)]

    def tiles_for(self, instance, r0, c0, r1, c1):
        needed, have = self.needed(r0, c0, r1, c1), {}
        now = store_stamp()
        with self.lock:
            for k in needed:
                key = (instance, *k)
                if key in self.tiles and kept_fresh(self.checked, key, now, lambda: navstore.stamp(tile_path(*key))):
                    self.tiles.move_to_end(key)
                    have[k] = self.tiles[key]
        missing = [k for k in needed if k not in have]
        stamps = {k: (navstore.stamp(tile_path(instance, *k)), now) for k in missing}
        if len(missing) == 1:
            have[missing[0]] = self.fetch_tile(instance, *missing[0])
        elif missing:
            with ThreadPoolExecutor(8) as pool:
                have.update(zip(missing, pool.map(lambda k: self.fetch_tile(instance, *k), missing)))
        for k in missing:
            have[k] = None if have[k] is None or "none" in have[k] else have[k]
        with self.lock:
            for k in missing:
                self.tiles[(instance, *k)] = have[k]
                self.checked[(instance, *k)] = stamps[k]
            while len(self.tiles) > KEEP_TILES:
                self.checked.pop(self.tiles.popitem(last=False)[0], None)
        return {k: have[k] for k in needed}

    def tile(self, instance, col, row):
        return self.tiles_for(instance, row * 128, col * 128, row * 128 + 1, col * 128 + 1)[(col, row)]


    def region(self, instance, r0, c0, r1, c1, tiles=None, roads=None):
        h, w = r1 - r0, c1 - c0
        out = {"ground": np.full((h, w), np.nan, np.float32), "spread": np.zeros((h, w), np.float32), "tilt": np.zeros((h, w), np.float32),
               "water": np.full((h, w), np.nan, np.float32), "hazard": np.zeros((h, w), bool), "ocean": np.zeros((h, w), bool),
               "holes": np.zeros((h, w), bool), "building": np.zeros((h, w), bool), "area": np.zeros((h, w), np.uint32)}
        if roads is not None:
            out["road"] = np.zeros((h, w), np.uint8)
        tiles = self.tiles_for(instance, r0, c0, r1, c1) if tiles is None else tiles
        for tc, tr in self.needed(r0, c0, r1, c1):
            t = tiles.get((tc, tr))
            if t is None:
                continue
            gr0, gc0 = tr * 128, tc * 128
            a0, b0 = max(r0, gr0), max(c0, gc0)
            a1, b1 = min(r1, gr0 + 128), min(c1, gc0 + 128)
            src = (slice(a0 - gr0, a1 - gr0), slice(b0 - gc0, b1 - gc0))
            dst = (slice(a0 - r0, a1 - r0), slice(b0 - c0, b1 - c0))
            for k in ("ground", "spread", "tilt", "water", "hazard", "ocean", "holes", "area"):
                if k in t:
                    out[k][dst] = t[k][src]
            if roads is not None and roads.get((tc, tr)) is not None:
                out["road"][dst] = roads[(tc, tr)][src]
            for nmax, nmin, wmax, wmin, zmin, zmax in t.get("buildings", []):
                ra, ca = cell_of(nmax, wmax)
                rb, cb = cell_of(nmin, wmin)
                ra, rb, ca, cb = max(ra, r0), min(rb, r1 - 1), max(ca, c0), min(cb, c1 - 1)
                if ra > rb or ca > cb:
                    continue
                block = out["ground"][ra - r0:rb - r0 + 1, ca - c0:cb - c0 + 1]
                at_ground = (zmin < block + 3) & (zmax > block + 2)
                out["building"][ra - r0:rb - r0 + 1, ca - c0:cb - c0 + 1] |= at_ground
        return out

    def places_in(self, instance, r0, c0, r1, c1, small=False, tiles=None):
        top, bottom = CORNER - r0 * CELL, CORNER - r1 * CELL
        left, right = CORNER - c0 * CELL, CORNER - c1 * CELL
        tiles = self.tiles_for(instance, r0, c0, r1, c1) if tiles is None else tiles
        seen, out = set(), []
        for tc, tr in self.needed(r0, c0, r1, c1):
            t = tiles.get((tc, tr))
            for p in (t.get("places", ()) if t else ()):
                if int(p[1]) in seen or p[7] > top or p[6] < bottom or p[9] > left or p[8] < right or not (small or p[10]):
                    continue
                seen.add(int(p[1]))
                out.append(p)
        return out

    def sources_under(self, instance, r0, c0, r1, c1):
        names = set()
        if not self.client_files:
            return names
        for tc, tr in self.needed(r0, c0, r1, c1):
            if not self.on_map(instance, tc, tr):
                continue
            marks = kept_marks(tile_path(instance, tc, tr))
            names.update((marks or {}).get("sources") or [wm.UNKNOWN_SOURCE])
        return names


    def npc_maps(self):
        npc = getattr(self, "_npc", None)
        if npc is None:
            npc = {}
            for k, a in (arrays.load_npz(NPC_TRAILS) or {}).items():
                name = k.split("_")
                if len(name) == 3 and name[1].isdigit():
                    npc.setdefault(int(name[1]), {})[name[2]] = a
            self._npc = npc
        return npc

    def npc_trails(self, instance):
        t = self.npc_maps().get(instance)
        return (t["c"], t["z"]) if t else (np.zeros(0, np.int64), np.zeros(0, np.float32))

    def npc_stretches(self, instance):
        return self.npc_maps().get(instance, {}).get("s", np.zeros((0, 6), np.float32))

    def _load_trails(self):
        added = storewriter.journal(TRAILS)
        out = {}
        for k, a in (arrays.load_npz(TRAILS) or {}).items():
            name = k.split("_")
            if len(name) == 2 and name[1].lstrip("-").isdigit():
                out[int(name[1])] = set(a.tolist())
        for instance, key in np.frombuffer(added[:len(added) // 16 * 16], np.int64).reshape(-1, 2).tolist():
            out.setdefault(instance, set()).add(key)
        return out, {k: trails_sorted(np.fromiter(v, np.int64, len(v))) for k, v in out.items()}

    def trails_version(self, instance, box):
        if box is None:
            return None
        with self.trails_lock:
            saved = self.trails_saved.get(instance)
        return trails_mark(saved, box)

    def save_trails(self):
        saved = {k: trails_sorted(np.fromiter(v, np.int64, len(v))) for k, v in tuple(self.trails.items())}
        self.trails_dirty = 0
        with self.trails_lock:
            self.trails_saved = saved

        def packed():
            buf = io.BytesIO()
            np.savez_compressed(buf, **{f"i_{k}": cells for k, (cells, _) in saved.items()})
            return buf.getvalue()
        os.makedirs(os.path.dirname(TRAILS), exist_ok=True)
        storewriter.fold_later(TRAILS, packed)

    def walked(self, instance, a, b):
        cells = self.trails.setdefault(instance, set())
        steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (CELL / 2)))
        new = []
        for i in range(steps + 1):
            t = i / steps
            r, c = cell_of(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            key = r * 8192 + c
            if key not in cells:
                cells.add(key)
                new.append((instance, key))
        if new:
            self.trails_dirty += len(new)
            storewriter.add_later(TRAILS, np.array(new, np.int64).tobytes())


def downsample(g, k):
    if k == 1:
        return g
    h, w = g["ground"].shape
    h2, w2 = h // k, w // k

    def blocks(a):
        return a[:h2 * k, :w2 * k].reshape(h2, k, w2, k)
    ground = blocks(g["ground"])
    warnings.filterwarnings("ignore", "All-NaN slice", RuntimeWarning)
    out = {"ground": np.nanmax(ground, axis=(1, 3)) if not np.isnan(ground).all() else ground[:, 0, :, 0],
           "spread": blocks(g["spread"]).max(axis=(1, 3)),
           "tilt": blocks(g["tilt"]).mean(axis=(1, 3)),
           "water": np.nanmax(blocks(g["water"]), axis=(1, 3)),
           "hazard": blocks(g["hazard"]).any(axis=(1, 3)), "holes": blocks(g["holes"]).all(axis=(1, 3)),
           "ocean": blocks(g["ocean"]).any(axis=(1, 3)) if "ocean" in g else np.zeros((h2, w2), bool),
           "building": blocks(g["building"]).mean(axis=(1, 3)) > 0.5, "trail": blocks(g["trail"]).any(axis=(1, 3)),
           "walls": blocks(g["walls"]).any(axis=(1, 3))}
    if "road" in g:
        out["road"] = blocks(g["road"]).any(axis=(1, 3))
    if "floored" in g:
        out["floored"] = blocks(g["floored"]).any(axis=(1, 3))
    if "over" in g:
        out["over"] = blocks(g["over"]).mean(axis=(1, 3)) > 0.5
    if "capital" in g:
        out["capital"] = blocks(g["capital"]).any(axis=(1, 3))
    return out


def on_water(g):
    ground, water = g["ground"], g["water"]
    return ~np.isnan(water) & (water - ground > (0.0 if g.get("ghost") else SWIM_DEPTH))


def offshore(g, step=CELL):
    swim = on_water(g)
    if g.get("ghost") or not swim.any():
        return np.zeros(swim.shape)
    from scipy.ndimage import distance_transform_edt
    return distance_transform_edt(swim) * step


def cell_weights(g, step=CELL):
    swim = on_water(g)
    weight = np.where(swim, 1.0 if g.get("ghost") else SWIM_COST, 1.0)
    if not g.get("ghost") and "ocean" in g:
        weight = weight * np.where(swim & g["ocean"], OCEAN_COST, 1.0)
    if not g.get("ghost") and swim.any():
        out = offshore(g, step)
        weight = weight * np.where(swim, 1 + (OFFSHORE_COST - 1) * np.clip((out - OFFSHORE_FROM) / OFFSHORE_SPAN, 0, 1), 1.0)
    if "tilt" in g:
        near = maximum_filter(g["tilt"], size=3, mode="nearest")
        limit = g.get("max_up", MAX_UP)
        weight = weight * np.where(swim, 1.0, 1 + STEEP_COST * np.clip((near - EASY_UP) / (limit - EASY_UP), 0, 1))
        weight = weight * np.where(~swim & ~g["trail"] & (g["tilt"] > limit), SCRAMBLE_COST, 1.0)
    if "danger" in g:
        weight = weight * (1 + g.get("danger_cost", SAFE_COST) * np.minimum(g["danger"], DANGER_CAP))
    if "ring" in g:
        weight = weight * np.where(g["danger"] > 0, 1.0, 1 + SAFEST_RING_COST * np.minimum(g["ring"], DANGER_CAP))
    if "worth" in g:
        weight = weight * np.maximum(SEEK_FLOOR, 1 - SEEK_GAIN * np.minimum(g["worth"], DANGER_CAP))
    painted = g["road"] if "road" in g else np.zeros(g["trail"].shape, bool)
    walked = g["trail"] & ~painted
    if "wild" in g:
        weight = weight * np.where(g["wild"] & ~walked & ~painted & ~(swim & bool(g.get("ghost"))), WILD_COST, 1.0)
    clear = ~(g["danger"] > 0) if "ring" in g else True
    weight = weight * np.where(g["building"], BUILDING_COST, 1.0) * np.where(
        painted & clear, g.get("trail_cost", TRAIL_COST), np.where(walked & clear, g.get("path_cost", PATH_COST), 1.0))
    if "pull" in g:
        weight = np.where(g["pull"], GATHER_COST, weight)
    if "over" in g:
        weight = weight * np.where(g["over"], np.where(painted, OVER_ROAD_COST, OVER_COST), 1.0)
    if "capital" in g:
        weight = weight * np.where(g["capital"], CAPITAL_COST, 1.0)
    return weight


def floor_danger(L, rows, keep=None):
    if rows is None or not len(rows) or rows.shape[1] < 5:
        return None
    rows = rows[(rows[:, 3] > 0) & np.isfinite(rows[:, 4])]
    if not len(rows):
        return None
    north, west = L.world(L.nodes[:, 0], L.nodes[:, 1])
    if not len(north):
        return None
    z = L.heights[L.nodes[:, 0], L.nodes[:, 1], L.nodes[:, 2]]
    rows = rows[(rows[:, 0] + rows[:, 2] >= north.min()) & (rows[:, 0] - rows[:, 2] <= north.max())
                & (rows[:, 1] + rows[:, 2] >= west.min()) & (rows[:, 1] - rows[:, 2] <= west.max())]
    if not len(rows):
        return None

    def work():
        hot = np.zeros(len(z), np.float32)
        for n, w, r, weight, mz in rows[:, :5]:
            hot[((north - n) ** 2 + (west - w) ** 2 <= r * r) & (np.abs(z - mz) <= FLOOR_MOB_Z)] += weight
        if not hot.any():
            return None
        hot.flags.writeable = False
        return hot
    return keep(np.ascontiguousarray(rows[:, :5]).tobytes(), work) if keep is not None else work()


STEPS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
JUMPS = ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (-2, 2), (2, -2), (2, 2))
OPPOSITE = tuple(STEPS.index((-dr, -dc)) for dr, dc in STEPS)


def shifted(h, w, dr, dc):
    return (slice(max(0, -dr), h - max(0, dr)), slice(max(0, -dc), w - max(0, dc)),
            slice(max(0, dr), h - max(0, -dr)), slice(max(0, dc), w - max(0, -dc)))


def climb_limit(g):
    return g.get("max_up", MAX_UP) if g.get("easy") else max(g.get("max_up", MAX_UP), CLIMB_UP)


def blocked_cells(g):
    ground, water = g["ground"], g["water"]
    swim = on_water(g)
    height = np.where(swim, water, ground)
    limit = climb_limit(g)
    steep = (~swim & (g["tilt"] > limit)) if not g.get("ghost") else np.zeros(ground.shape, bool)
    blocked = (np.isnan(ground) | g["holes"]) & ~g["trail"] | g["hazard"] | steep
    if "walls" in g:
        opened = g["trail"] & ~g["floored"] if "floored" in g else g["trail"]
        blocked |= g["walls"] & ~opened
    return swim, height, blocked


def ghost_faces(g, swim):
    if "tilt" not in g:
        return np.zeros(g["ground"].shape, bool)
    return ~swim & (g["tilt"] > climb_limit(g))


def move_masks(g, step):
    swim, height, blocked = blocked_cells(g)
    up = math.tan(math.radians(climb_limit(g)))
    h, w = height.shape
    ghost = bool(g.get("ghost"))
    wall = blocked & g["walls"] if "walls" in g else np.zeros((h, w), bool)
    barred, jumped = g.get("barred"), g.get("jumped")

    def cells(dr, dc, kr, kc):
        return (slice(max(0, -dr) + kr, h - max(0, dr) + kr), slice(max(0, -dc) + kc, w - max(0, dc) + kc))

    def marked(grid, dr, dc, sr, sc, d):
        sd, od = STEPS[d], OPPOSITE[d]
        a, b = grid[cells(dr, dc, sr, sc)], grid[cells(dr, dc, sr + sd[0], sc + sd[1])]
        return ((a >> d) & 1 == 1) | ((b >> od) & 1 == 1)

    def unbarred(dr, dc, sr, sc, d):
        return True if barred is None else ~marked(barred, dr, dc, sr, sc, d)
    face = ghost_faces(g, swim) if ghost else None
    fall = (g.get("fall_most") or 0.0) if step <= CELL * 1.01 else 0.0
    down = max(MAX_DROP * step / CELL, fall)
    out = []
    for d, (dr, dc) in enumerate(STEPS):
        dist = step * (math.sqrt(2) if dr and dc else 1)
        rs, cs, rt, ct = shifted(h, w, dr, dc)
        rise = height[rt, ct] - height[rs, cs]
        wet = swim[rs, cs] & swim[rt, ct]
        free = ~blocked[rs, cs] & ~blocked[rt, ct] & unbarred(dr, dc, 0, 0, d)
        leap = marked(jumped, dr, dc, 0, 0, d) if jumped is not None else False
        if ghost:
            level = ~face[rs, cs] & ~face[rt, ct] & (wet | (rise <= dist * up))
            ok = free & ((rise <= 0) | level)
            out.append((dr, dc, rs, cs, ok, dist, ok & leap))
            continue
        ok = free & (wet | ((rise <= dist * up) & (-rise <= down)))
        out.append((dr, dc, rs, cs, ok, dist, ok & ((~wet & (-rise > dist * up)) | leap)))
    if step <= CELL * 1.01:
        drop_max = math.inf if ghost else max(g.get("cliff_jump", CLIFF_JUMP), fall)
        for dr, dc in JUMPS:
            dist = step * math.hypot(dr, dc)
            rs, cs, rt, ct = shifted(h, w, dr, dc)
            sr, sc = dr // 2, dc // 2
            rm, cm = cells(dr, dc, sr, sc)
            drop = height[rs, cs] - height[rt, ct]
            half = STEPS.index((sr, sc))
            ok = ~blocked[rs, cs] & ~blocked[rt, ct] & blocked[rm, cm] & ~wall[rm, cm] & ~swim[rs, cs] \
                & (drop > MAX_DROP * step / CELL / 2) & (drop <= drop_max) & ~(height[rm, cm] > height[rs, cs] + 1) \
                & unbarred(dr, dc, 0, 0, half) & unbarred(dr, dc, sr, sc, half)
            out.append((dr, dc, rs, cs, ok, dist, ok & (not ghost)))
    return out


def walks(masks):
    return {(dr, dc): (rs, cs, ok & ~drop) for dr, dc, rs, cs, ok, _, drop in masks}


def moves(g, step):
    weight = cell_weights(g, step)
    swim, height, _ = blocked_cells(g)
    up = math.tan(math.radians(g.get("max_up", MAX_UP)))
    h, w = g["ground"].shape
    flat = cell_weights({k: v for k, v in g.items() if k != "tilt"}, step) if g.get("ghost") and "tilt" in g else None
    out = []
    for dr, dc, rs, cs, ok, dist, drop in move_masks(g, step):
        _, _, rt, ct = shifted(h, w, dr, dc)
        steep = (height[rt, ct] - height[rs, cs] > dist * up) & ~(swim[rs, cs] & swim[rt, ct]) \
            & ~(g["trail"][rs, cs] & g["trail"][rt, ct])
        cost = dist * np.maximum((weight[rs, cs] + weight[rt, ct]) / 2, np.where(steep, np.float32(SCRAMBLE_COST), np.float32(0.0)))
        if flat is not None:
            down = height[rt, ct] < height[rs, cs]
            cost = np.where(down, dist * (flat[rs, cs] + flat[rt, ct]) / 2, cost)
        risky = np.where(drop, np.maximum(height[rs, cs] - height[rt, ct] - FALL_MARKED, 0), 0) if g.get("fall_most") else 0
        out.append((dr, dc, rs, cs, ok, cost + drop * np.float32(wmonav.DROP_COST) + np.float32(FALL_COST) * risky, drop))
    return out


def block_pieces(g, s):
    h, w = g["ground"].shape
    masks = move_masks(g, CELL)
    _, _, blocked = blocked_cells(g)
    n, big = h * w, h * w
    lab = np.where(blocked, big, np.arange(n, dtype=np.int64).reshape(h, w))
    by = walks(masks)
    rows, cols = np.arange(h), np.arange(w)
    both = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        rs, cs, ok = by[(dr, dc)]
        back = by[(-dr, -dc)][2]
        _, _, rt, ct = shifted(h, w, dr, dc)
        same = ((rows[rs] // s) == ((rows[rs] + dr) // s))[:, None] & ((cols[cs] // s) == ((cols[cs] + dc) // s))[None, :]
        both.append((rs, cs, rt, ct, ok & back & same))
    while True:
        before = lab.copy()
        for rs, cs, rt, ct, m in both:
            low = np.minimum(lab[rs, cs], lab[rt, ct])
            lab[rs, cs] = np.where(m, low, lab[rs, cs])
            lab[rt, ct] = np.where(m, np.minimum(lab[rt, ct], low), lab[rt, ct])
        flat = lab.ravel()
        live = flat < big
        flat[live] = flat[flat[live]]
        if np.array_equal(lab, before):
            break
    walk = ~blocked
    roots, inv = np.unique(lab[walk], return_inverse=True)
    piece = np.full((h, w), -1, np.int64)
    piece[walk] = inv
    count = len(roots)
    rr, cc = np.nonzero(walk)
    many = np.maximum(np.bincount(inv, minlength=count), 1)
    at = np.stack([np.bincount(inv, weights=rr, minlength=count) / many, np.bincount(inv, weights=cc, minlength=count) / many], 1)
    keys = ([], [])
    for dr, dc, rs, cs, ok, _, drop in masks:
        _, _, rt, ct = shifted(h, w, dr, dc)
        a, b = piece[rs, cs], piece[rt, ct]
        m = ok & (a != b)
        if m.any():
            if dr == 0:
                a, b, m, drop = a.T, b.T, m.T, drop.T
            for kept, sel in zip(keys, (m & ~drop, m & drop)):
                k = a[sel] * count + b[sel]
                if len(k):
                    kept.append(np.unique(k[np.concatenate(([True], k[1:] != k[:-1]))]))
    walk_keys, drop_keys = (np.unique(np.concatenate(k)) if k else np.zeros(0, np.int64) for k in keys)
    keys = np.union1d(walk_keys, drop_keys)
    fall = np.isin(keys, drop_keys, assume_unique=True) & ~np.isin(keys, walk_keys, assume_unique=True)
    return piece, count, at, (keys // count, keys % count, fall), masks


def held_bytes(item):
    if item is None:
        return 0
    seen, total, todo = set(), 0, [item]
    while todo:
        v = todo.pop()
        if v is None or id(v) in seen:
            continue
        seen.add(id(v))
        if isinstance(v, np.ndarray):
            base = v
            while isinstance(base.base, np.ndarray):
                base = base.base
            total += sys.getsizeof(v) - (v.nbytes if v.flags.owndata else 0)
            if base is v or id(base) not in seen:
                seen.add(id(base))
                total += base.nbytes
        elif isinstance(v, dict):
            total += sys.getsizeof(v)
            todo += [*v.keys(), *v.values()]
        elif isinstance(v, (tuple, list)):
            total += sys.getsizeof(v)
            todo += v
        elif isinstance(v, (wmonav.Layers, spmatrix)):
            total += sys.getsizeof(v) + sys.getsizeof(vars(v))
            todo += vars(v).values()
        elif isinstance(v, (bytes, str, int, float, np.generic)):
            total += sys.getsizeof(v)
    return total


class Buildings:

    def __init__(self, terrain):
        self.terrain = terrain
        self.kept = OrderedDict()
        self.keys = {}
        self.checked = {}
        self.kept_bytes = 0
        self.lock = threading.Lock()
        self.flight = SingleFlight()

    def clear(self):
        with self.lock:
            self.kept.clear()
            self.keys.clear()
            self.checked.clear()
            self.kept_bytes = 0

    @staticmethod
    def files_stamp(key):
        if len(key) == 4 and key[1] in ("props", "walls"):
            name = props_key(key[0], key[2], key[3])
        elif len(key) == 3 or (len(key) == 4 and key[3] in PLACED_SUFFIXES[1:]):
            name = building_key(*key[:3]) + "".join(key[3:])
        else:
            return None
        return navstore.stamp(os.path.join(CACHE, layers_name(name))), navstore.stamp(os.path.join(CACHE, joins_name(name)))

    def remembered(self, key):
        now = store_stamp()
        with self.lock:
            if key in self.kept and kept_fresh(self.checked, key, now, lambda: self.files_stamp(key)):
                self.kept.move_to_end(key)
                return True, self.kept[key][0]
        return False, None

    def keep(self, key, item, stamp=None, now=None):
        size = held_bytes(item)
        stamp = self.files_stamp(key) if stamp is None else stamp
        now = store_stamp() if now is None else now
        with self.lock:
            if key in self.kept:
                self._let_go(key)
            self.kept[key] = (item, size)
            self.keys[id(item)] = key
            self.checked[key] = (stamp, now)
            self.kept_bytes += size
            self._trim()

    def worked_on(self, b, name, key, work, most=0):
        with self.lock:
            got = b.get(name)
            if got is not None and key in got:
                return got[key]
        value = work()
        with self.lock:
            got = b.setdefault(name, {})
            if most and key not in got and len(got) >= most:
                got.pop(next(iter(got)))
            got[key] = value
            at = self.keys.get(id(b))
            if at in self.kept and self.kept[at][0] is b:
                size = held_bytes(b)
                self.kept_bytes += size - self.kept[at][1]
                self.kept[at] = (b, size)
                self._trim()
        return value

    def _let_go(self, key):
        item, size = self.kept.pop(key)
        self.keys.pop(id(item), None)
        self.checked.pop(key, None)
        self.kept_bytes -= size

    def _trim(self):
        while self.kept_bytes > KEEP_BUILDINGS_BYTES and len(self.kept) > 1:
            self._let_go(next(iter(self.kept)))

    def kept_now(self, key, work, keep_none=True):
        found, item = self.remembered(key)
        if found:
            return item
        now, before = store_stamp(), self.files_stamp(key)
        item = self.flight.do(key, work)
        if item is not None or keep_none:
            self.keep(key, item, before if wm.serving() else self.files_stamp(key), now)
        return item

    def get(self, instance, place):
        suffix = place_suffix(place)
        key = (instance, int(place[0]), int(place[1])) + ((suffix,) if suffix else ())
        return self.kept_now(key, lambda: self._get(instance, place))

    def _get(self, instance, place):
        fid = int(place[0])

        def parts():
            return [(wmonav.building_geometry(fid, wm.installed_version()), (place[2], place[3], place[4]), place[5],
                     place_scale(place), place_tilt(place))]
        got = self._worked_out(instance, place_key(instance, place), parts,
                               where=(instance, float(place[2]), float(place[3])), placed_of=lambda: self.placed(instance, place))
        if got is None:
            raise NothingToWalk(f"building {fid}: nothing to walk")
        return got

    def placed(self, instance, place):
        tilt, scale = place_tilt(place), place_scale(place)
        return placed_digest(np.asarray(place, np.float64)[2:6], [self.max_up(instance)], *([tilt] if any(tilt) else []),
                             *([[scale]] if scale != 1.0 else []))

    def kept_good(self, instance, place):
        return all(walking_good(place_key(instance, place), lambda: self.placed(instance, place)))

    def _worked_out(self, instance, key, parts_of, bounds=None, where=None, placed_of=lambda: NOWHERE, sources_of=None):
        if wm.serving():
            try:
                return self.built(key)
            except NotBuilt:
                if where:
                    self.terrain.want(*where)
                raise
        with realign.working("paths", where, when=layers_kept_from_before(key)):
            return self._work_out(instance, key, parts_of, bounds, placed_of, sources_of)

    @staticmethod
    def built(key, rules=None):
        lpath, jpath = os.path.join(CACHE, layers_name(key, rules)), os.path.join(CACHE, joins_name(key, rules))
        b = kept_arrays(lpath, ("heights",), any_build=True)
        if b is not None and empty_area(b):
            return None
        try:
            layers, graph = layers_of(b) if b is not None else (None, None)
        except ValueError:
            layers = graph = None
        joins = kept_joins(jpath, lpath, len(layers.nodes), any_build=True) if layers is not None else None
        if joins is None:
            raise NotBuilt(("doodads" if "-props-" in key else "building", key))
        return dict(zip(("layers", "graph") + JOIN_KEYS, (layers, graph) + joins))

    def _work_out(self, instance, key, parts_of, bounds, placed_of, sources_of):
        split_old(key)
        lpath, jpath = os.path.join(CACHE, layers_name(key)), os.path.join(CACHE, joins_name(key))
        digest = []

        def placed():
            if not digest:
                digest.append(placed_of())
            return digest[0]
        good, joins_good = walking_good(key, placed, sources_of)
        b = kept_arrays(lpath, ("heights",), any_build=True) if good else None
        if b is not None and empty_area(b):
            return None
        layers = graph = built = None
        if b is not None:
            try:
                layers, graph = layers_of(b)
            except ValueError:
                arrays.set_aside(lpath)
        if layers is not None and joins_good:
            joins = kept_joins(jpath, lpath, len(layers.nodes), any_build=True)
            if joins is not None:
                return dict(zip(("layers", "graph") + JOIN_KEYS, (layers, graph) + joins))
        with wm.recording() as used:
            parts = parts_of()
        if parts and not any(len(geo["tris"]) or len(geo["water"]) for geo, *_ in parts):
            parts = []
        if layers is not None:
            try:
                with ACTIVITY.doing("working"):
                    built = wmonav.Layers(parts, bounds=bounds, max_up=self.max_up(instance), kept=(layers.heights, layers.swim))
                if (built.top, built.left, built.res) != (layers.top, layers.left, layers.res):
                    raise ValueError("kept layers at another spot than their parts make")
            except ValueError:
                layers = None
        os.makedirs(CACHE, exist_ok=True)
        if layers is None:
            if not parts:
                arrays.save_npz(lpath, heights=np.zeros((0, 0, 1), np.float32), placed=placed())
                return None
            with ACTIVITY.doing("working"):
                built = wmonav.Layers(parts, bounds=bounds, max_up=self.max_up(instance),
                                      cap_first="-props-" in key and wmonav.PROPS_VERSION <= 12)
                graph = built.graph()
            sources = set(used)
            arrays.save_npz(lpath, **layer_arrays(built, graph), sources=np.array(sorted(sources), str), placed=placed())
            layers = built.standing()
        else:
            sources = {str(s) for s in b.get("sources", ())} or {wm.UNKNOWN_SOURCE}
        with ACTIVITY.doing("working"):
            joins = self.links(instance, built, graph, doodads="-props-" in key)
        if self.terrain.map_kind(instance) == "terrain":
            rows, cols = join_cells(built)
            sources |= self.terrain.sources_under(instance, int(rows.min()), int(cols.min()), int(rows.max()) + 1,
                                                  int(cols.max()) + 1)
        arrays.save_npz(jpath, **dict(zip(JOIN_KEYS, joins)), nodes=np.array(len(layers.nodes)),
                        sources=np.array(sorted(sources), str), placed=placed())
        return dict(zip(("layers", "graph") + JOIN_KEYS, (layers, graph) + tuple(joins)))

    def max_up(self, instance):
        return wmonav.DUNGEON_MAX_UP if self.terrain.is_dungeon(instance) else wmonav.MAX_UP

    def prefetch(self, instance, places):
        if wm.serving():
            return
        todo = {int(p[0]) for p in places if (instance, int(p[0]), int(p[1])) not in self.kept
                and not layers_kept_since_switch(place_key(instance, p))}
        if len(todo) > 1:
            version = wm.installed_version()
            with ThreadPoolExecutor(8) as pool:
                list(pool.map(lambda fid: _quiet(wmonav.building_geometry, fid, version), todo))

    def props(self, instance, point):
        gn, gw = round(point[0] / PROP_GRID), round(point[1] / PROP_GRID)
        return self.kept_now((instance, "props", gn, gw), lambda: self._props(instance, gn, gw), keep_none=False)

    def doodads_near(self, instance, gn, gw):
        bounds = props_bounds(gn, gw)
        ra, ca = cell_of(bounds[0] + TILE, bounds[1] + TILE)
        rb, cb = cell_of(bounds[2] - TILE, bounds[3] - TILE)
        near = []
        for tc, tr in self.terrain.needed(ra, ca, rb + 1, cb + 1):
            t = self.terrain.tile(instance, tc, tr) if self.terrain.on_map(instance, tc, tr) else None
            rows = np.asarray((t or {}).get("doodads", ()), np.float64).reshape(-1, DOODAD_COLUMNS)
            near += list(rows[reaches(rows, gn, gw)])
        return near

    def _props(self, instance, gn, gw):
        cn, cw = gn * PROP_GRID, gw * PROP_GRID
        bounds = props_bounds(gn, gw)
        if wm.serving():
            try:
                return self.built(props_key(instance, gn, gw))
            except NotBuilt:
                if not self.doodads_near(instance, gn, gw):
                    return None
                self.terrain.want(instance, cn, cw)
                raise

        seen = []

        def doodads():
            if not seen:
                seen.append(self.doodads_near(instance, gn, gw))
            return seen[0]
        if not doodads():
            return None

        def parts():
            version = wm.installed_version()
            near = doodads()
            with ThreadPoolExecutor(8) as pool:
                fids = list({int(d[0]) for d in near})
                geos = dict(zip(fids, pool.map(lambda fid: _shape(wmonav.m2_geometry, fid, version), fids)))
            failed = [fid for fid, geo in geos.items() if geo is FAILED]
            if failed:
                raise OSError(f"{len(failed)} doodad shapes round ({cn:.0f}, {cw:.0f}) not to be had now")
            return [(geos[int(d[0])], (d[2], d[3], d[4]), d[5], d[6], (d[7], d[8])) for d in near
                    if geos.get(int(d[0])) is not None and len(geos[int(d[0])]["tris"])]
        return self._worked_out(instance, props_key(instance, gn, gw), parts, bounds, where=(instance, cn, cw),
                                placed_of=lambda: self.doodads_placed(instance, doodads()),
                                sources_of=lambda: doodads_files(doodads()))

    def doodads_placed(self, instance, near):
        rows = np.asarray(near, np.float64).reshape(-1, DOODAD_COLUMNS)
        return placed_digest(rows[np.lexsort(rows.T[::-1])], [self.max_up(instance)])

    def walls(self, instance, r0, c0, r1, c1):
        barred, jumped, yards = ([np.zeros(0, np.int64)] for _ in range(3))
        for gn, gw in lattice_areas(r0, c0, r1, c1):
            try:
                got = self.area_walls(instance, gn, gw)
            except NotBuilt as e:
                wm.note_unbuilt(e.what)
                continue
            for out, codes in ((barred, got.barred), (jumped, got.jumped)):
                rr, cc = np.divmod(codes // 8, 8192)
                out.append(codes[(rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)])
            yr, yc = np.divmod(got.yards, YARD_SPAN)
            rr = ((CORNER - (YARD_ORIGIN - yr - 0.5)) // CELL).astype(np.int64)
            cc = ((CORNER - (YARD_ORIGIN - yc - 0.5)) // CELL).astype(np.int64)
            yards.append(got.yards[(rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)])
        return DoodadWalls(np.concatenate(barred), np.concatenate(jumped), np.unique(np.concatenate(yards)))

    def area_walls(self, instance, gn, gw):
        def work():
            keys = ("barred", "jumped", "walls")
            got = join_arrays(navstore.load_npz(os.path.join(CACHE, joins_name(props_key(instance, gn, gw)))), keys)
            if got is None:
                b = self.props(instance, (gn * PROP_GRID, gw * PROP_GRID)) if self.doodads_near(instance, gn, gw) else None
                if not b:
                    return NO_WALLS
                got = tuple(b[k] for k in keys)
            return DoodadWalls(*(np.asarray(v, np.int64) for v in got))
        return self.kept_now((instance, "walls", gn, gw), work)

    def props_kept_good(self, instance, point):
        gn, gw = round(point[0] / PROP_GRID), round(point[1] / PROP_GRID)
        seen = []

        def doodads():
            if not seen:
                seen.append(self.doodads_near(instance, gn, gw))
            return seen[0]
        return all(walking_good(props_key(instance, gn, gw), lambda: self.doodads_placed(instance, doodads()),
                                lambda: doodads_files(doodads())))

    def links(self, instance, layers, graph, doodads=False):
        if self.terrain.map_kind(instance) != "terrain":
            return (np.zeros((0, 2), np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64),
                    np.zeros(0, np.int64), np.zeros(0, bool), np.zeros(0, np.int64))
        pad = JOIN_OUT + 1
        rows, cols = join_cells(layers)
        g = self.terrain.region(instance, int(rows.min()), int(cols.min()), int(rows.max()) + 1, int(cols.max()) + 1)
        at = ((rows - rows.min())[:, None], (cols - cols.min())[None, :])
        ground, cells = g["ground"][at], rows[:, None] * 8192 + cols[None, :]
        standable = ~np.isnan(ground) & ~g["holes"][at]

        def in_grid(r, c):
            return (r >= 0) & (r < layers.h) & (c >= 0) & (c < layers.w)

        def in_way(solid, r, c, over=None):
            base = (r.astype(np.int64) * layers.w + c) * 100000
            z = ((ground[r + pad, c + pad] if over is None else over) - layers.zmin) * 10
            return (np.searchsorted(solid, base + np.round(z + wmonav.BODY[1] * 10).astype(np.int64), "right")
                    > np.searchsorted(solid, base + np.round(z + wmonav.BODY[0] * 10).astype(np.int64), "left"))

        def room(r, c):
            ok = standable[r + pad, c + pad]
            i = np.flatnonzero(ok & in_grid(r, c))
            ok[i] = ~layers.solid(r[i], c[i], wmonav.STAND, ground[r[i] + pad, c[i] + pad]) & ~in_way(layers.floors, r[i], c[i])
            return ok
        rr, cc = np.nonzero(~np.isnan(ground[pad:-pad, pad:-pad]))
        hit = in_way(layers.walls, rr, cc) | in_way(layers.floors, rr, cc)
        uniq, counts = np.unique(cells[rr[hit] + pad, cc[hit] + pad], return_counts=True)
        blocks = uniq[counts >= WALL_HITS].astype(np.int64)
        open_ = standable & ~np.isin(cells, blocks)
        outside = open_ & outside_cells(g, int(rows.min()), int(cols.min()), blocks)[at]
        nodes = layers.nodes
        floored = np.intersect1d(blocks, cells[nodes[:, 0] + pad, nodes[:, 1] + pad])
        heights = layers.heights[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
        moves = graph.tocoo()
        d = nodes[moves.col, :2] - nodes[moves.row, :2]
        one = (np.abs(d) <= 1).all(axis=1)
        onward = np.zeros((len(nodes), 3, 3), bool)
        onward[moves.row[one], d[one, 0] + 1, d[one, 1] + 1] = True
        joins = [np.zeros((0, 2), np.int64)]
        for dr, dc in STEPS:
            r, c = nodes[:, 0] + dr, nodes[:, 1] + dc
            k = np.flatnonzero(~onward[:, dr + 1, dc + 1] & in_grid(r, c) & (np.abs(heights - ground[r + pad, c + pad]) <= JOIN_YARDS))
            low = ground[r[k] + pad, c[k] + pad]
            fall = heights[k] - low > JOIN_UP
            wall = layers.crossing(nodes[k, 0], nodes[k, 1], dr, dc, heights[k])
            wall[fall] = layers.sweep(nodes[k[fall], 0], nodes[k[fall], 1], dr, dc, heights[k[fall]], low[fall])
            k = k[~wall & room(r[k], c[k])]
            r, c = r[k], c[k]
            first = np.full(len(k), -1, np.int64)
            for step in range(JOIN_OUT + 1):
                here = outside[r + pad, c + pad]
                met = cells[r + pad, c + pad]
                first = np.where((first < 0) & open_[r + pad, c + pad], met, first)
                joins.append(np.stack([k[here], met[here]], 1))
                k, r, c, first = k[~here], r[~here], c[~here], first[~here]
                if step == JOIN_OUT or not len(k):
                    break
                r2, c2 = r + dr, c + dc
                both = in_grid(r, c) & in_grid(r2, c2)
                wall = np.zeros(len(k), bool)
                wall[both] = layers.crossing(r[both], c[both], dr, dc,
                                             np.fmax(ground[r + pad, c + pad], ground[r2 + pad, c2 + pad])[both])
                on = ~wall & room(r2, c2)
                stop = ~on & (first >= 0)
                joins.append(np.stack([k[stop], first[stop]], 1))
                k, r, c, first = k[on], r2[on], c2[on], first[on]
            left = first >= 0
            joins.append(np.stack([k[left], first[left]], 1))
        joins = np.unique(np.concatenate(joins), axis=0).astype(np.int64)
        jn = joins[:, 0]
        wn, ww = layers.world(nodes[jn, 0], nodes[jn, 1])
        with np.errstate(invalid="ignore"):
            onto = heights[jn] - ground_under(g, int(rows.min()), int(cols.min()), wn, ww) <= JOIN_UP
        if not doodads:
            return joins, blocks, floored, np.zeros(0, np.int64), np.zeros(0, np.int64), onto, np.zeros(0, np.int64)
        walked = np.zeros((layers.h, layers.w), bool)
        if onto.any():
            k = np.flatnonzero(np.isfinite(dijkstra(graph, indices=np.unique(joins[onto, 0]), min_only=True)))
            r, c, z = nodes[k, 0], nodes[k, 1], heights[k]
            low = z - ground_under(g, int(rows.min()), int(cols.min()), *layers.world(r, c)) <= JOIN_UP
            k = k[low & ~in_way(layers.walls, r, c, z) & ~in_way(layers.floors, r, c, z)]
            walked[nodes[k, 0], nodes[k, 1]] = True
        yards, low = wall_yards(layers, g, int(rows.min()), int(cols.min()), walked)
        barred, jumped = barred_moves(layers, yards, low)
        return joins, blocks, floored, yards, barred, onto, jumped


def ground_under(g, r0, c0, north, west):
    h = g["ground"]
    gr = np.clip((CORNER - np.asarray(north, np.float64)) / CELL - 0.5 - r0, 0, h.shape[0] - 1)
    gc = np.clip((CORNER - np.asarray(west, np.float64)) / CELL - 0.5 - c0, 0, h.shape[1] - 1)
    ra, ca = np.minimum(gr.astype(np.int64), h.shape[0] - 2).clip(0), np.minimum(gc.astype(np.int64), h.shape[1] - 2).clip(0)
    rb, cb = np.minimum(ra + 1, h.shape[0] - 1), np.minimum(ca + 1, h.shape[1] - 1)
    tr, tc = np.clip(gr - ra, 0, 1), np.clip(gc - ca, 0, 1)
    own = h[np.rint(gr).astype(np.int64).clip(0, h.shape[0] - 1), np.rint(gc).astype(np.int64).clip(0, h.shape[1] - 1)]
    rise = CELL * math.tan(math.radians(g.get("max_up", MAX_UP)))
    total = weight = 0.0
    with np.errstate(invalid="ignore"):
        for z, share in ((h[ra, ca], (1 - tr) * (1 - tc)), (h[rb, ca], tr * (1 - tc)), (h[ra, cb], (1 - tr) * tc),
                         (h[rb, cb], tr * tc)):
            ok = np.abs(z - own) <= rise
            total = total + np.where(ok, z * share, 0.0)
            weight = weight + np.where(ok, share, 0.0)
        return np.where(weight > 0, total / np.where(weight > 0, weight, 1.0), own)


def yard_of(north, west):
    return (np.floor(YARD_ORIGIN - np.asarray(north, np.float64)).astype(np.int64) * YARD_SPAN
            + np.floor(YARD_ORIGIN - np.asarray(west, np.float64)).astype(np.int64))


def wall_yards(layers, g, r0, c0, walked):
    from scipy.ndimage import label
    r, c =(a.ravel() for a in np.indices((layers.h, layers.w)))
    north, west = layers.world(r, c)
    z = ground_under(g, r0, c0, north, west)
    ok = np.isfinite(z) & ~walked.ravel()
    base = (r[ok].astype(np.int64) * layers.w + c[ok]) * 100000

    def solid(over, up):
        lo = base + np.round((z[ok] - layers.zmin + over) * 10).astype(np.int64)
        hi = base + np.round((z[ok] - layers.zmin + up) * 10).astype(np.int64)
        out = np.zeros(len(r), bool)
        out[ok] = ((np.searchsorted(layers.walls, hi, "right") > np.searchsorted(layers.walls, lo, "left"))
                   | (np.searchsorted(layers.floors, hi, "right") > np.searchsorted(layers.floors, lo, "left")))
        return out.reshape(layers.h, layers.w)
    fill, free = solid(*wmonav.BODY), ~walked
    high = solid(wmonav.JUMP_UP, wmonav.JUMP_UP + wmonav.BODY[1])
    slant = fill[:-1, :-1] & fill[1:, 1:] & ~fill[:-1, 1:] & ~fill[1:, :-1]
    back = fill[:-1, 1:] & fill[1:, :-1] & ~fill[:-1, :-1] & ~fill[1:, 1:]
    fill[:-1, 1:] |= slant & free[:-1, 1:]
    high[:-1, 1:] |= slant & free[:-1, 1:] & (high[:-1, :-1] | high[1:, 1:])
    fill[:-1, :-1] |= back & free[:-1, :-1]
    high[:-1, :-1] |= back & free[:-1, :-1] & (high[:-1, 1:] | high[1:, :-1])
    lab, n = label(~(fill & high))
    keep = np.zeros(n + 1, bool)
    keep[np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])] = True
    keep[lab[walked | ~np.isfinite(z).reshape(layers.h, layers.w)]] = True
    shut = ~keep[lab]
    fill |= shut
    high |= shut
    r, c = np.nonzero(fill)
    lr, lc = np.nonzero(fill & ~high)
    return np.unique(yard_of(*layers.world(r, c))), np.unique(yard_of(*layers.world(lr, lc)))


def walls_crossed(yards, north0, west0, north1, west1):
    n0, w0, n1, w1 = (np.atleast_1d(np.asarray(a, np.float64)) for a in (north0, west0, north1, west1))
    if not len(yards) or not len(n0):
        return np.zeros(len(n0), bool)
    t = np.linspace(0.0, 1.0, int(math.ceil(float(np.max(np.hypot(n1 - n0, w1 - w0))) / YARD_STEP)) + 1)
    ids = yard_of(n0[:, None] + (n1 - n0)[:, None] * t, w0[:, None] + (w1 - w0)[:, None] * t)
    return (yards[np.searchsorted(yards, ids).clip(0, len(yards) - 1)] == ids).any(axis=1)


def barred_moves(layers, yards, low):
    top, left, res = layers.top, layers.left, layers.res
    ra = math.floor((CORNER - top) / CELL - 0.5) + 1
    rb = math.floor((CORNER - (top - layers.h * res)) / CELL - 0.5)
    ca = math.floor((CORNER - left) / CELL - 0.5) + 1
    cb = math.floor((CORNER - (left - layers.w * res)) / CELL - 0.5)
    if ra > rb or ca > cb or not len(yards):
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    rr, cc = (a.ravel() for a in np.meshgrid(np.arange(ra, rb + 1), np.arange(ca, cb + 1), indexing="ij"))
    high = np.setdiff1d(yards, low, assume_unique=True)
    barred, jumped = [], []
    for d, (dr, dc) in enumerate(STEPS):
        ends = (*world_of(rr, cc), *world_of(rr + dr, cc + dc))
        bar = walls_crossed(high, *ends)
        over = ~bar & walls_crossed(low, *ends)
        barred.append((rr[bar] * 8192 + cc[bar]) * 8 + d)
        jumped.append((rr[over] * 8192 + cc[over]) * 8 + d)
    return np.concatenate(barred).astype(np.int64), np.concatenate(jumped).astype(np.int64)


def barred_grid(codes, r0, c0, shape):
    out = np.zeros(shape, np.uint8)
    cells, d = np.divmod(np.asarray(codes, np.int64), 8)
    rr, cc = np.divmod(cells, 8192)
    rr, cc = rr - r0, cc - c0
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    np.bitwise_or.at(out, (rr[ok], cc[ok]), np.left_shift(1, d[ok]).astype(np.uint8))
    return out


def join_steps(rise, onto):
    with np.errstate(invalid="ignore"):
        up = onto & (rise <= JOIN_UP) & (rise >= -JOIN_YARDS)
        down = (rise <= JOIN_YARDS) & (rise >= -JOIN_UP)
    return up, down


def outside_cells(g, r0, c0, blocks):
    from scipy.ndimage import label
    h, w = g["ground"].shape
    ids = (r0 + np.arange(h))[:, None] * 8192 + (c0 + np.arange(w))[None, :]
    free = ~np.isnan(g["ground"]) & ~g["holes"] & ~np.isin(ids, blocks)
    lab, _ = label(free, structure=np.ones((3, 3), bool))
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return np.isin(lab, edge[edge > 0])


def doodads_files(near):
    return sorted({f"m2-{int(d[0])}.m2" for d in near})


def join_cells(layers):
    pad = JOIN_OUT + 1
    north = layers.top - (np.arange(-pad, layers.h + pad) + 0.5) * layers.res
    west = layers.left - (np.arange(-pad, layers.w + pad) + 0.5) * layers.res
    return ((CORNER - north) // CELL).astype(np.int64), ((CORNER - west) // CELL).astype(np.int64)


def in_house(place, layers, end, z=None, outdoors=False):
    if outdoors or not (place[7] <= end[0] <= place[6] and place[9] <= end[1] <= place[8]):
        return False
    return len(layers.near(end[0], end[1], z, radius=1)) > 0


def houses_near(places, ends):
    def apart(p):
        return min(math.hypot((p[6] + p[7]) / 2 - e[0], (p[8] + p[9]) / 2 - e[1]) for e in ends)
    small = sorted((p for p in places if not p[10]), key=apart)
    return [p for p in small if apart(p) <= HOUSE_REACH][:MAX_HOUSES]


def search_box(start, goal, margin_cells, max_cells=None):
    max_cells = MAX_CELLS if max_cells is None else max_cells
    sr, sc = cell_of(*start)
    gr, gc = cell_of(*goal)
    margin_r = max(MARGIN, min(margin_cells, (MAX_SIDE - abs(gr - sr)) // 2))
    margin_c = max(MARGIN, min(margin_cells, (MAX_SIDE - abs(gc - sc)) // 2))
    span = max(abs(gr - sr) + 2 * margin_r, abs(gc - sc) + 2 * margin_c)
    stride = 1
    while (span / stride) ** 2 > max_cells and stride < 16:
        stride *= 2
    r0, r1 = min(sr, gr) - margin_r, max(sr, gr) + margin_r
    c0, c1 = min(sc, gc) - margin_c, max(sc, gc) + margin_c
    r0, c0 = r0 - r0 % stride, c0 - c0 % stride
    r1, c1 = r1 + stride - (r1 - r0) % stride, c1 + stride - (c1 - c0) % stride
    return (r0, c0, r1, c1), stride


def _quiet(f, *args):
    try:
        return f(*args)
    except (OSError, ValueError, KeyError, struct.error):
        return None


FAILED = object()


def _shape(f, *args):
    try:
        return f(*args)
    except OSError as e:
        return None if storedonly.not_there(e) else FAILED
    except (ValueError, KeyError, struct.error):
        return None


REACH_PAIRS = 1 << 16
REACH_SLACK = 1e-4


def reach_hits(looks, rows, levels=None):
    looks, rows = np.asarray(looks), np.asarray(rows)
    look_hit, row_hit = np.zeros(len(looks), bool), np.zeros(len(rows), bool)
    li = np.flatnonzero(np.isfinite(looks[:, :2]).all(1)) if len(looks) else np.zeros(0, np.intp)
    if not len(li) or not len(rows):
        return look_hit, row_hit
    spots = looks[li, :2].astype(np.float64)
    lo, hi = spots.min(0), spots.max(0)
    at = rows[:, :2].astype(np.float64)
    far = np.abs(rows[:, 2].astype(np.float64)) * (1 + REACH_SLACK)
    with np.errstate(invalid="ignore"):
        ri = np.flatnonzero(np.isfinite(rows[:, :3]).all(1) & (at[:, 0] + far >= lo[0]) & (at[:, 0] - far <= hi[0])
                            & (at[:, 1] + far >= lo[1]) & (at[:, 1] - far <= hi[1]))
    if not len(ri):
        return look_hit, row_hit
    tree = cKDTree(spots)
    at, far = at[ri], far[ri]
    total = np.cumsum(tree.query_ball_point(at, far, return_length=True))
    heights = levels is not None and looks.shape[1] > 2 and rows.shape[1] > 4
    k = 0
    while k < len(ri):
        end = max(k + 1, int(np.searchsorted(total, (total[k - 1] if k else 0) + REACH_PAIRS, side="right")))
        near = tree.query_ball_point(at[k:end], far[k:end])
        sizes = np.fromiter((len(x) for x in near), np.intp, end - k)
        if sizes.sum():
            i = li[np.fromiter((p for x in near for p in x), np.intp, int(sizes.sum()))]
            j = ri[np.repeat(np.arange(k, end), sizes)]
            inside = (looks[i, 0] - rows[j, 0]) ** 2 + (looks[i, 1] - rows[j, 1]) ** 2 <= rows[j, 2] ** 2
            if heights:
                with np.errstate(invalid="ignore"):
                    inside &= ~(np.abs(looks[i, 2] - rows[j, 4]) > levels)
            look_hit[i[inside]] = True
            row_hit[j[inside]] = True
        k = end
    return look_hit, row_hit


def mobs_passed(start, pts, mobs):
    if not len(mobs) or not pts:
        return 0
    way = [np.array(start[:2], np.float32)]
    prev = way[0]
    for p in pts:
        p = np.array(p[:2], np.float32)
        n = max(1, int(np.hypot(*(p - prev)) / 2))
        way += [prev + (p - prev) * (k / n) for k in range(1, n + 1)]
        prev = p
    return int(reach_hits(np.stack(way), mobs)[1].sum())


class Capitals:

    def __init__(self, area_city, sides, rooms=()):
        self.area_city = np.asarray(area_city, np.int64)
        self.side = dict(sides)
        self.rooms = list(rooms)
        held = (array_digest(self.area_city), sorted((int(c), str(s)) for c, s in self.side.items()),
                [(int(i), int(c), float(t), float(left), float(cell), array_digest(np.asarray(m, bool)))
                 for i, c, t, left, cell, m in self.rooms])
        self.stamp = hashlib.blake2b(repr(held).encode("utf-8"), digest_size=16).hexdigest()

    def enemy(self, side):
        if side not in facts.FACTION_BITS:
            return frozenset()
        return frozenset(c for c, s in self.side.items() if s != side)

    def of_areas(self, area):
        a, top = np.asarray(area, np.int64), len(self.area_city) - 1
        if top < 0:
            return np.zeros(a.shape, np.int64)
        return np.where((a >= 0) & (a <= top), self.area_city[np.clip(a, 0, top)], 0)

    def of_rooms(self, inst, north, west):
        north, west = np.asarray(north, np.float64), np.asarray(west, np.float64)
        out = np.zeros(north.shape, np.int64)
        for at, city, top, left, cell, mask in self.rooms:
            if at != inst:
                continue
            r, c = np.floor((top - north) / cell).astype(np.int64), np.floor((left - west) / cell).astype(np.int64)
            on = (r >= 0) & (r < mask.shape[0]) & (c >= 0) & (c < mask.shape[1]) & (out == 0)
            hit = np.zeros(north.shape, bool)
            hit[on] = mask[r[on], c[on]]
            out[hit] = city
        return out

    def at(self, inst, north, west, z, ground, area):
        out = self.of_areas(area)
        z, ground = np.asarray(z, np.float64), np.asarray(ground, np.float64)
        with np.errstate(invalid="ignore"):
            under = z < ground - CITY_UNDER
        if under.any():
            out = out.copy()
            out[under] = self.of_rooms(inst, np.asarray(north)[under], np.asarray(west)[under])
        return out


Walker = namedtuple("Walker", "side open goal rides")


def rideable(side, walker):
    return walker is None or walker.rides is None or side in (None, walker.rides)


WALK_TABLES = ("populated_of", "zone_levels", "capitals")


def rules_stamp(tables):
    levels, caps = tables["zone_levels"], tables["capitals"]
    held = (tables["populated_of"] is not None, None if levels is None else tuple(array_digest(a) for a in levels),
            None if caps is None else caps.stamp)
    return hashlib.blake2b(repr(held).encode("utf-8"), digest_size=16).hexdigest()


def walk_table(name, doc):
    return property(lambda self: self.walk_tables[name], lambda self, value: self.set_tables(**{name: value}), doc=doc)


class Paths:
    populated_of = walk_table("populated_of", "instance -> where creatures are, (top, left, cell, grid): the world "
                                              "layers' wilds")
    zone_levels = walk_table("zone_levels", "(zone of each area ID, that zone's lowest level): arrays from mapzones "
                                            "(mark_over)")
    capitals = walk_table("capitals", "the capital cities and their sides (Capitals), from mapzones: the walks' sides")

    def __init__(self, terrain=None):
        self.terrain = terrain or Terrain()
        self.buildings = Buildings(self.terrain)
        self.lock = threading.Lock()
        self.flight = SingleFlight()
        self.cache = OrderedDict()
        self.cache_stamp = None
        self.reached, self.reached_stamp = OrderedDict(), None
        self.digests = OrderedDict()
        self.walk_tables = dict.fromkeys(WALK_TABLES)
        self.rules = rules_stamp(self.walk_tables)
        self.room_indoors = None
        self.ways = self.read_ways()

    @staticmethod
    def read_ways():
        try:
            with open(WAYS, encoding="utf-8") as f:
                return json.load(f).get("ways", [])
        except (OSError, ValueError):
            return []

    def set_tables(self, **tables):
        unknown = set(tables) - set(WALK_TABLES)
        if unknown:
            raise TypeError(f"no walk table named {', '.join(sorted(unknown))}")
        with self.lock:
            self.walk_tables = {**self.walk_tables, **tables}
            self.rules = rules_stamp(self.walk_tables)

    def walk_stamp(self, instance, box):
        return self.rules, self.terrain.trails_version(instance, box)

    def noted(self, instance, work, by=None):
        by = by or self.walk_stamp
        before = by(instance, MAP_BOX)
        with noting_trails() as read:
            got = work()
        box = trails_box(read, instance)
        return got, box, (by(instance, box) if by(instance, MAP_BOX) == before else None)

    def reset(self):
        with self.lock:
            self.cache.clear()
            self.reached.clear()
            self.buildings.clear()
            self.terrain.forget()
            self.__dict__.pop("_movers", None)
            self.__dict__.pop("_travel", None)
            self.ways = self.read_ways()

    @property
    def travel(self):
        got = self.__dict__.get("_travel")
        if got is None:
            import travel
            got = self.__dict__.setdefault("_travel", travel.TravelGraph(self))
        return got

    def by_graph(self, instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, walker=None):
        mode = avoid[2] if avoid and len(avoid) > 2 else ""
        try:
            return self.travel.long_way(instance, start, goal, start_z, goal_z, indoors, ghost, avoid[1] if avoid else None,
                                        mode, level, walker=walker)
        except NotBuilt as e:
            wm.note_unbuilt(e.what)
            for end in (start, goal):
                self.terrain.want(instance, *end[:2])
            return None

    def walk_seconds(self, instance, start, goals, avoid=None, level=None, ghost=False, start_z=None, side=None):
        mode = avoid[2] if avoid and len(avoid) > 2 else ""
        return self.travel.walk_costs(instance, start, goals, avoid[1] if avoid else None, mode, level, ghost, start_z,
                                      walker=self.walker(instance, start, None, start_z, None, side, ghost))

    def leg_ways(self, instance, box, avoid=None, level=None, side=None, exempt=()):
        mode = avoid[2] if avoid and len(avoid) > 2 else ""
        walker = Walker(side, (), 0, side) if side in facts.FACTION_BITS else None
        return self.travel.leg_ways(instance, box, avoid[1] if avoid else None, mode, level, walker, exempt)

    def leg_region(self, instance, box):
        return self.travel.region_key(instance, *box, 1)


    def ground_at(self, instance, north, west):
        north, west = np.asarray(north, np.float64), np.asarray(west, np.float64)
        r, c = ((CORNER - north) // CELL).astype(np.int64), ((CORNER - west) // CELL).astype(np.int64)
        area, ground = np.zeros(len(r), np.int64), np.full(len(r), np.nan)
        ok = on_grid(r, c)
        tile = (r // 128) * 64 + c // 128
        for k in np.unique(tile[ok]).tolist():
            t = self.terrain.tile(instance, k % 64, k // 64)
            if t is None:
                continue
            m = ok & (tile == k)
            if "area" in t:
                area[m] = t["area"][r[m] % 128, c[m] % 128]
            ground[m] = t["ground"][r[m] % 128, c[m] % 128]
        return area, ground

    def cities_at(self, instance, north, west, z):
        if self.capitals is None:
            return None
        area, ground = self.ground_at(instance, north, west)
        return self.capitals.at(instance, north, west, z, ground, area)

    def city_at(self, instance, point, z=None, indoors=None):
        north, west = np.array([point[0]], np.float64), np.array([point[1]], np.float64)
        area, ground = self.ground_at(instance, north, west)
        got = int(self.capitals.of_areas(area)[0])
        top = max(z) if isinstance(z, tuple) else z
        if got or indoors is False and top is None or (top is not None and np.isfinite(ground[0]) and top >= ground[0] - CITY_UNDER):
            return got
        return int(self.capitals.of_rooms(instance, north, west)[0])

    def walker(self, instance, start, goal, start_z, goal_z, side, ghost=False, ground=True, indoors=None):
        if ghost or side not in facts.FACTION_BITS:
            return None
        if self.capitals is None or not ground:
            return Walker(side, (), 0, side)
        enemy = self.capitals.enemy(side)
        here = self.city_at(instance, start, start_z, indoors)
        there = self.city_at(instance, goal, goal_z) if goal is not None else 0
        there = there if there in enemy and there != here else 0
        return Walker(side, (here,) if here else (), there, None if there or here in enemy else side)

    def costly(self, walker):
        if walker is None or self.capitals is None:
            return frozenset()
        return self.capitals.enemy(walker.side) - set(walker.open)

    def floor_cities(self, instance, b):
        caps, L = self.capitals, b["layers"]
        if caps is None or not len(L.nodes):
            return None

        def work():
            n = L.nodes
            north, west = L.world(n[:, 0], n[:, 1])
            got = self.cities_at(instance, np.asarray(north, np.float64), np.asarray(west, np.float64),
                                 L.heights[n[:, 0], n[:, 1], n[:, 2]])
            return got.astype(np.int32) if got.any() else None
        try:
            return self.buildings.worked_on(b, "cities", caps, work, most=1)
        except (NotBuilt, OSError, ValueError, KeyError, struct.error):
            return None

    def stop_outside(self, instance, start, goal, result, walker, rows=None):
        pts = result.get("points") or []
        if not pts:
            return result
        at = np.array([[p[0], p[1], p[2] if len(p) > 2 and p[2] is not None else np.nan] for p in pts], np.float64)
        ids = self.cities_at(instance, at[:, 0], at[:, 1], at[:, 2])
        walked = len(pts) - (1 if result.get("partial") else 0)
        inside = np.flatnonzero(ids[:walked] == walker.goal)
        if not len(inside):
            return result
        k = int(inside[0])
        kept = [list(p) for p in pts[:k]]
        edge = self.edge_before(instance, kept[-1] if kept else [start[0], start[1]], pts[k], walker.goal)
        if edge:
            kept.append(edge)
        last = kept[-1] if kept else start
        out = {key: v for key, v in result.items() if key not in ("near", "gap")}
        out.update(partial=True, gap=round(math.hypot(last[0] - goal[0], last[1] - goal[1])), enemyGoal=walker.goal)
        kept.append([round(float(goal[0]), 1), round(float(goal[1]), 1)])
        out.update(points=kept, length=round(way_length([start] + kept)))
        if rows is not None and len(rows) and "mobs" in result:
            out["mobs"] = mobs_passed(start, kept, rows[rows[:, 3] >= 0])
            if "fight" in result:
                out["fight"] = mobs_passed(start, kept, rows[rows[:, 3] < 0])
        return out

    def edge_before(self, instance, a, b, city):
        flat = math.hypot(b[0] - a[0], b[1] - a[1])
        za = a[2] if len(a) > 2 and a[2] is not None else np.nan
        zb = b[2] if len(b) > 2 and b[2] is not None else np.nan
        if flat <= 2 * CELL or abs(zb - za) > flat:
            return None
        t = np.linspace(0.0, 1.0, int(flat // 2) + 2)[1:-1]
        north, west, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, za + (zb - za) * t
        ids = self.cities_at(instance, north, west, z)
        inside = np.flatnonzero(ids == city)
        k = int(inside[0]) if len(inside) else len(t)
        if k == 0:
            return None
        spot = [round(float(north[k - 1]), 1), round(float(west[k - 1]), 1)]
        return spot + ([round(float(z[k - 1]), 1)] if np.isfinite(z[k - 1]) else [])

    def reach(self, instance, spot, spots, ghost=False, reverse=False, wait=False):
        try:
            return self.travel.reach(instance, spot, spots, ghost, reverse, wait)
        except NotBuilt as e:
            wm.note_unbuilt(e.what)
            self.terrain.want(instance, *spot[:2])
            return [None] * len(spots)

    def forget_ways(self):
        with self.lock:
            self.cache.clear()

    def way_at(self, instance, point, z, indoors):
        for way in self.ways:
            inside = way["points"][0]
            if way["inst"] != instance or math.hypot(point[0] - inside[0], point[1] - inside[1]) > way["reach"]:
                continue
            if z is not None and not isinstance(z, tuple) and abs(z - inside[2]) > WAY_HEIGHT:
                continue
            if z is None and indoors is False:
                continue
            return way
        return None

    def reached_ground(self, instance, pts):
        key = (instance, tuple((round(float(p[0]), 1), round(float(p[1]), 1)) for p in pts))
        stamp = store_stamp()
        with self.lock:
            if stamp != self.reached_stamp:
                self.reached.clear()
                self.reached_stamp = stamp
            kept = self.reached.get(key)
        if kept is not None and kept[1] == self.walk_stamp(instance, kept[0]):
            with self.lock:
                if key in self.reached:
                    self.reached.move_to_end(key)
            note_trails(instance, kept[0])
            return kept[2]
        with wm.noting_unbuilt() as unbuilt:
            got, box, walked = self.noted(instance, lambda: self._reached_ground(instance, pts))
        if got is not None:
            got[2].flags.writeable = False
        with self.lock:
            if not unbuilt and walked is not None and stamp == self.reached_stamp:
                self.reached[key] = (box, walked, got)
                while len(self.reached) > REACHED_KEPT:
                    self.reached.popitem(last=False)
        return got

    def _reached_ground(self, instance, pts):
        ns, ws = [p[0] for p in pts], [p[1] for p in pts]
        s = Search(self, instance, (max(ns), max(ws)), (min(ns), min(ws)), MARGIN, None, None, False, False, False,
                   None, False, False, False, None, False, None)
        if s.stride != 1 or not s.read_ground():
            return None
        s.read_buildings()
        for gn in range(math.floor(min(ns) / PROP_GRID), math.ceil(max(ns) / PROP_GRID) + 1):
            for gw in range(math.floor(min(ws) / PROP_GRID), math.ceil(max(ws) / PROP_GRID) + 1):
                try:
                    props = self.buildings.props(instance, (gn * PROP_GRID, gw * PROP_GRID))
                except NotBuilt as e:
                    wm.note_unbuilt(e.what)
                    continue
                if props:
                    s.doodads.add(len(s.blds))
                    s.blds.append(props)
                    s.dear.append(1.0)
        for stage in (s.floors_over, s.rules, s.coarse, s.terrain_graph, s.building_graph, s.close_graph):
            stage()
        graph = s.graph
        deep = (offshore(s.fine) > STROKE).ravel()
        if deep.any():
            keep = np.ones(graph.shape[0], bool)
            keep[:s.n] = ~deep
            coo = graph.tocoo()
            ok = keep[coo.row] & keep[coo.col]
            graph = csr_matrix((coo.data[ok], (coo.row[ok], coo.col[ok])), shape=graph.shape)
        _, label = connected_components(graph, connection="strong")
        land = s.passable.ravel() & np.isin(np.arange(s.n), graph.indices)
        if not land.any():
            return s.r0, s.c0, np.zeros((s.fh, s.fw), bool)
        size = np.bincount(label[:s.n][land], minlength=label.max() + 1)
        held = np.zeros(len(size), np.int64)
        for p in pts:
            r, c = cell_of(p[0], p[1])
            r, c = r - s.r0, c - s.c0
            if 0 <= r < s.fh and 0 <= c < s.fw and land[r * s.fw + c]:
                held[label[r * s.fw + c]] += 1
        stretch = int(np.lexsort((size, held))[-1])
        mask = (land & (label[:s.n] == stretch)).reshape(s.fh, s.fw)
        for b, off in zip(s.blds, s.offsets):
            L = b["layers"]
            mine = np.flatnonzero(label[off:off + len(L.nodes)] == stretch)
            wn, ww = L.world(L.nodes[mine, 0], L.nodes[mine, 1])
            rr = ((CORNER - np.asarray(wn)) // CELL).astype(np.int64) - s.r0
            cc = ((CORNER - np.asarray(ww)) // CELL).astype(np.int64) - s.c0
            inside = (rr >= 0) & (rr < s.fh) & (cc >= 0) & (cc < s.fw)
            mask[rr[inside], cc[inside]] = True
        return s.r0, s.c0, mask

    def blocked_nodes(self, instance, blds, offsets):
        out = []
        for way in self.ways:
            block = way.get("block")
            if not block or way["inst"] != instance:
                continue
            inside, (lo, hi) = way["points"][0], block["heights"]
            for b, off in zip(blds, offsets):
                L = b["layers"]
                if not len(L.nodes):
                    continue
                wn, ww = L.world(L.nodes[:, 0], L.nodes[:, 1])
                hh = L.heights[L.nodes[:, 0], L.nodes[:, 1], L.nodes[:, 2]]
                near = (np.hypot(np.asarray(wn) - inside[0], np.asarray(ww) - inside[1]) <= block["reach"]) & (hh >= lo) & (hh <= hi)
                out.append(np.flatnonzero(near) + off)
        return np.concatenate(out) if out else np.zeros(0, np.int64)

    def find(self, instance, start, goal, start_z=None, goal_z=None, indoors=None, ghost=False, avoid=None, level=None,
             side=None):
        got = self.walked(instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, side)
        if got and got.get("fall", 0) > FALL_ALL and not EASY.get():
            with easy_way(falls_only=True):
                easy = self.walked(instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, side)
            if easy and not easy.get("partial"):
                return easy
        return got

    def walked(self, instance, start, goal, start_z=None, goal_z=None, indoors=None, ghost=False, avoid=None, level=None,
               side=None):
        out, into = self.way_at(instance, start, start_z, indoors), self.way_at(instance, goal, goal_z, None)
        if out and out is into:
            out = into = None
        if out:
            far = out["points"][-1]
            rest = self.find(instance, tuple(far[:2]), goal, far[2], goal_z, None, ghost, avoid, level, side)
            if rest:
                pts = [list(p) for p in out["points"]] + rest["points"]
                return {**rest, "points": pts, "length": round(way_length([start] + pts[:len(out["points"])]) + rest["length"])}
        if into:
            far = into["points"][-1]
            rest = self._find(instance, start, tuple(far[:2]), start_z, far[2], indoors, ghost, avoid, level, side)
            if rest and not rest["partial"]:
                back = [list(p) for p in reversed(into["points"][:-1])]
                if math.hypot(goal[0] - back[-1][0], goal[1] - back[-1][1]) > 1:
                    end = [goal[0], goal[1]] + ([goal_z] if goal_z is not None and not isinstance(goal_z, tuple) else [])
                    back.append([round(float(v), 1) for v in end])
                return {**rest, "points": rest["points"] + back, "length": round(rest["length"] + way_length([list(far)] + back))}
        return self._find(instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, side)

    def _find(self, instance, start, goal, start_z=None, goal_z=None, indoors=None, ghost=False, avoid=None, level=None,
              side=None):
        t0 = time.time()
        sr, sc = cell_of(*start)
        gr, gc = cell_of(*goal)
        if not (on_grid(sr, sc) and on_grid(gr, gc)) or max(abs(gr - sr), abs(gc - sc)) > MAX_APART:
            return None
        asked = (gr, gc, repr(start_z), repr(goal_z), indoors, ghost, avoid[0] if avoid else None,
                 self.mobs_digest(avoid[1]) if avoid else None, level,
                 EASY.get(), side or None)
        key, own = (instance, sr // 3, sc // 3) + asked, (instance, "from", sr, sc) + asked
        stamp = store_stamp()
        with self.lock:
            if stamp != self.cache_stamp:
                self.cache.clear()
                self.cache_stamp = stamp
            found = [(k, self.cache.get(k)) for k in (key, own)]
        for k, got in found:
            if got is not None and got[1] == self.ways_data(instance, got[0]):
                with self.lock:
                    if k in self.cache:
                        self.cache.move_to_end(k)
                note_trails(instance, got[0])
                return got[2]

        def work():
            with wm.noting_unbuilt() as unbuilt:
                kind = self.terrain.map_kind(instance) if self.terrain.client_files else "terrain"
                walker = self.walker(instance, start, goal, start_z, goal_z, side, ghost, kind == "terrain", indoors)
                result = worked(kind, walker)
                if result is not None and walker and walker.goal:
                    result = self.stop_outside(instance, start, goal, result, walker, avoid[1] if avoid else None)
            if result is not None and unbuilt:
                result["unbuilt"] = sorted({str(w[0]) for w in unbuilt})
            return result

        def worked(kind, walker):
            if kind == "building":
                return self.in_building(instance, start, goal, start_z, goal_z, walker)
            if kind is None:
                return None
            result = None
            gathering = bool(avoid) and avoid[2:] == ("gather",)
            by_graph = not gathering and LONG_BY_GRAPH and EASY.get() is not True
            if by_graph and search_box(start, goal, MARGIN)[1] > 1:
                got = self.by_graph(instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, walker)
                if got is not None:
                    return got
            for grow in (1, 3, 9):
                if grow > 1 and by_graph and search_box(start, goal, MARGIN * grow)[1] > 1:
                    by_graph = False
                    got = self.by_graph(instance, start, goal, start_z, goal_z, indoors, ghost, avoid, level, walker)
                    if got is not None and not got["partial"]:
                        if result is None or result["partial"] or got["cost"] < result["cost"]:
                            result = got
                        break
                found = self.search(instance, start, goal, MARGIN * grow, start_z, goal_z, indoors, houses=not gathering, ghost=ghost,
                                    avoid=avoid[1] if avoid else None, seek=bool(avoid) and avoid[2:] == ("seek",),
                                    roads=bool(avoid) and avoid[2:] == ("roads",), gather=bool(avoid) and avoid[2:] == ("gather",),
                                    level=level, walker=walker)
                if result is not None and not result["partial"] and (found is None or found["partial"] or found["cost"] >= result["cost"]):
                    break
                if found is None:
                    break
                result = found
                if not result["partial"]:
                    if (result.get("over") or result.get("enemy") or result.get("drops")) and grow == 1:
                        continue
                    break
                if not result.pop("boxed", False):
                    break
                if grow == 3 and result.get("gap", math.inf) <= NEAR_GAP:
                    break
            if result is not None and not result["partial"] and result["swum"] > SWIM_WIDER and not gathering \
                    and not result.get("travel"):
                wider = self.search(instance, start, goal, MARGIN * SWIM_GROW, start_z, goal_z, indoors, houses=False, ghost=ghost,
                                    avoid=avoid[1] if avoid else None, seek=bool(avoid) and avoid[2:] == ("seek",),
                                    roads=bool(avoid) and avoid[2:] == ("roads",), gather=bool(avoid) and avoid[2:] == ("gather",),
                                    max_cells=WIDER_CELLS, end_props=True, level=level, walker=walker)
                if wider is not None and not wider["partial"] and wider["cost"] < result["cost"]:
                    result = wider
            flat = math.hypot(goal[0] - start[0], goal[1] - start[1])
            if result is not None and start_z is None and goal_z is None and not gathering and flat <= SAME_FLOOR_REACH \
                    and (result["partial"] or result["length"] > 2 * flat + SAME_FLOOR_DETOUR):
                shared = self.search(instance, start, goal, MARGIN, None, None, indoors, ghost=ghost,
                                     avoid=avoid[1] if avoid else None, seek=bool(avoid) and avoid[2:] == ("seek",),
                                     roads=bool(avoid) and avoid[2:] == ("roads",), level=level, share_floor=True, walker=walker)
                if shared is not None and not shared["partial"] and (result["partial"] or shared["length"] < result["length"]):
                    result = shared
            if result:
                result.pop("boxed", None)
            return result

        def kept_or_worked():
            way = self.kept_way((key, own), instance)
            return (way, True) if way is not None else (self.noted(instance, work, self.ways_data), False)
        (result, box, data), on_disk = self.flight.do((own, self.ways_data(instance, MAP_BOX)), kept_or_worked)
        if result is None:
            return None
        note_trails(instance, box)
        result = {**result, "ms": round((time.time() - t0) * 1000)}
        if result.get("degraded") or result.get("unbuilt"):
            return result
        with self.lock:
            if stamp != self.cache_stamp or data is None:
                return result
            kept = own if result.get("partial") else key
            self.cache[kept] = (box, data, result)
            while len(self.cache) > PATHS_KEPT:
                self.cache.popitem(last=False)
        if not on_disk:
            self.keep_way(kept, box, data, result)
        return result

    def ways_data(self, instance, box):
        return (tuple(store.digest(p) for p in WAYS_DATA + (wm.SWITCH,)),) + self.walk_stamp(instance, box)

    @staticmethod
    def kept_rules():
        return tuple(sorted(rules_in_force().items()))

    @staticmethod
    def kept_way_path(folder, key):
        digest = hashlib.blake2b(repr(key).encode("utf-8"), digest_size=16).hexdigest()
        return os.path.join(folder, f"w{WAYS_VERSION}-{digest}.json")

    def kept_way(self, keys, instance):
        folder = ways_folder()
        rules = repr(self.kept_rules()) if folder else None
        for key in keys if folder else ():
            got = store.load_json(self.kept_way_path(folder, key), None)
            if not got or got.get("key") != repr(key) or got.get("rules") != rules:
                continue
            box = tuple(got["box"]) if got.get("box") is not None else None
            data = self.ways_data(instance, box)
            if got.get("data") == repr(data):
                return got["way"], box, data
        return None

    def keep_way(self, key, box, data, way):
        folder = ways_folder()
        if not folder:
            return
        os.makedirs(folder, exist_ok=True)
        storewriter.save_json_later(self.kept_way_path(folder, key), {"key": repr(key), "rules": repr(self.kept_rules()),
                                                                 "box": box, "data": repr(data), "way": way}, indent=None)

    def mobs_digest(self, rows):
        if rows is None:
            return None
        with self.lock:
            hit = self.digests.get(id(rows))
            if hit is not None and hit[0] is rows:
                return hit[1]
        digest = array_digest(rows)
        if not isinstance(rows, np.ndarray):
            return digest
        with self.lock:
            self.digests[id(rows)] = (rows, digest)
            while len(self.digests) > DIGESTS_KEPT:
                self.digests.popitem(last=False)
        return digest

    def warm(self, instance, north, west):
        r, c = cell_of(north, west)
        if not (0 <= r < 64 * 128 and 0 <= c < 64 * 128):
            return
        if wm.serving():
            self.terrain.want(instance, north, west)
            return
        with wm.background():
            kind = self.terrain.map_kind(instance)
            if kind == "building":
                self.buildings.get(instance, self.terrain.global_building(instance))
                return
            if kind != "terrain":
                return
            tr, tc = r // 128, c // 128
            box = ((tr - 1) * 128, (tc - 1) * 128, (tr + 2) * 128, (tc + 2) * 128)
            tiles = self.terrain.tiles_for(instance, *box)
            places = self.terrain.places_in(instance, *box, tiles=tiles)
            self.buildings.prefetch(instance, places)
            for place in places:
                try:
                    self.buildings.get(instance, place)
                except (OSError, ValueError, KeyError, struct.error):
                    pass
        self.warm_near(instance, north, west)

    def warm_near(self, instance, north, west):
        if wm.serving():
            self.terrain.want(instance, north, west)
            return
        r, c = cell_of(north, west)
        reach = int(HOUSE_REACH / CELL) + 1
        with wm.background():
            if self.terrain.map_kind(instance) != "terrain":
                return
            houses = houses_near(self.terrain.places_in(instance, r - reach, c - reach, r + reach + 1, c + reach + 1, small=True),
                                 [(north, west)])
            self.buildings.prefetch(instance, houses)
            for place in houses:
                _quiet(self.buildings.get, instance, place)
            _quiet(self.buildings.props, instance, (north, west))

    def warm_leg(self, instance, a, b):
        if wm.serving():
            for end in (a, b):
                self.terrain.want(instance, *end[:2])
            return
        with wm.background():
            self.find(instance, a, b)

    def movers(self):
        movers = getattr(self, "_movers", None)
        if movers is None:
            try:
                with open(os.path.join(ROOT, "data", "routes.json"), encoding="utf-8") as f:
                    data = json.load(f)
                movers = data.get("movers", []) + same_map_portals(data.get("doors", []))
            except (OSError, ValueError):
                movers = []
            self._movers = movers
        return movers

    def ridden(self, instance, b, walker=None):
        movers = [m for m in self.movers() if m["map"] == instance]
        who = walker.rides if walker and any(m.get("side") for m in movers) else None

        def work():
            L, rows, cols, data = b["layers"], [], [], []
            for m in movers:
                if not rideable(m.get("side"), walker):
                    continue
                ends = []
                for p in mover_ends(m):
                    best, best_d = None, 5.0
                    for i in L.near(p[0], p[1], (p[2] - 4, p[2] + 4), radius=8, every=True):
                        d = abs(L.heights[tuple(L.nodes[i])] - p[2])
                        if d < best_d:
                            best, best_d = i, d
                    ends.append(best)
                if None not in ends and ends[0] != ends[1]:
                    cost = ride_yards(m)
                    ways = ends[:1] if m.get("oneWay") else ends
                    rows += ways; cols += [ends[1] if e == ends[0] else ends[0] for e in ways]; data += [cost] * len(ways)
            for x0, y0, z0, x1, y1, z1 in self.terrain.npc_stretches(instance):
                ends = []
                for n_, w_, z_ in ((x0, y0, z0), (x1, y1, z1)):
                    found = L.near(n_, w_, (z_ - NPC_TRAIL_Z, z_ + NPC_TRAIL_Z), radius=3)
                    ends.append(min(found, key=lambda i: abs(L.heights[tuple(L.nodes[i])] - z_)) if found else None)
                if None not in ends and ends[0] != ends[1]:
                    cost = math.dist((x0, y0, z0), (x1, y1, z1)) * 1.1
                    rows += ends; cols += ends[::-1]; data += [cost, cost]
            graph = b["graph"]
            return (graph + csr_matrix((data, (rows, cols)), shape=graph.shape)).tocsr() if rows else graph
        return self.buildings.worked_on(b, "ridden", who, work)

    def in_building(self, instance, start, goal, start_z, goal_z, walker=None):
        b = self.buildings.get(instance, self.terrain.global_building(instance))
        result = wmonav.find_path(b["layers"], self.ridden(instance, b, walker), start, goal, start_z, goal_z)
        if result:
            result["stride"] = 1
        return result

    def search(self, instance, start, goal, margin_cells, start_z=None, goal_z=None, indoors=None, houses=True, ghost=False,
               avoid=None, seek=False, roads=False, gather=False, max_cells=None, end_props=False, level=None,
               share_floor=False, exempt=None, walker=None):
        s = Search(self, instance, start, goal, margin_cells, start_z, goal_z, indoors, houses, ghost, avoid, seek, roads,
                   gather, max_cells, end_props, level, exempt, walker)
        if not s.read_ground():
            return None
        s.read_buildings()
        s.floors_over()
        s.rules()
        s.coarse()
        s.mobs()
        s.terrain_graph()
        s.building_graph()
        s.close_graph()
        s.ends()
        if share_floor and not s.share_floor():
            return None
        if not s.walk():
            return None
        return s.way()

    def mark_over(self, g, level, start_cell, goal_cell, exempt=None):
        lut = self.zone_levels
        if lut is None or "area" not in g:
            return
        zone_of, lowest = lut
        area = np.minimum(g["area"], len(zone_of) - 1).astype(np.int64)
        zone = zone_of[area]
        low = lowest[area]
        over = (low > 0) & (low >= level + OVER_ABOVE)
        ends = set(exempt) if exempt is not None else \
            {int(zone[r, c]) for r, c in (start_cell, goal_cell) if 0 <= r < zone.shape[0] and 0 <= c < zone.shape[1]}
        ends.discard(0)
        if ends:
            over &= ~np.isin(zone, list(ends))
        g["over"], g["zone"] = over, zone

    def mark_capitals(self, g, costly):
        if self.capitals is None or "area" not in g:
            return
        city = self.capitals.of_areas(g["area"])
        city = np.where(np.isin(city, list(costly)), city, 0)
        if city.any():
            g["city"], g["capital"] = city, city > 0

    @staticmethod
    def straighten(cells, ok_moves, h, w, weights=None, danger=None, walls=None):
        def allowed(a, b):
            dr, dc = b[0] - a[0], b[1] - a[1]
            rs, cs, ok = ok_moves[(dr, dc)]
            i, j = a[0] - rs.start, a[1] - cs.start
            return 0 <= i < ok.shape[0] and 0 <= j < ok.shape[1] and bool(ok[i, j])

        red = None
        if danger is not None and len(cells) >= 3:
            red = [0.0]
            for c0, c1 in zip(cells, cells[1:]):
                red.append(red[-1] + (math.hypot(c1[0] - c0[0], c1[1] - c0[1]) if danger[c1] > 0 else 0.0))

        def line_ok(i, j):
            a, b, skipped = cells[i], cells[j], cells[i + 1:j]
            n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
            limit = max(weights[a], weights[b]) if weights is not None else None
            mobs = max(danger[a], danger[b]) if danger is not None else None
            prev, cheapest, reached = a, min(weights[a], weights[b]) if weights is not None else None, 0
            for k in range(1, n + 1):
                p = (round(a[0] + (b[0] - a[0]) * k / n), round(a[1] + (b[1] - a[1]) * k / n))
                if not allowed(prev, p) or (limit is not None and weights[p] > limit + 1e-6):
                    return False
                if mobs is not None and danger[p] > mobs + 1e-6:
                    return False
                if cheapest is not None:
                    cheapest = min(cheapest, weights[p])
                reached += mobs is not None and danger[p] > 0
                prev = p
            if red is not None and reached and reached * math.hypot(b[0] - a[0], b[1] - a[1]) / n > red[j] - red[i] + RED_SLACK:
                return False
            if walls is not None and walls(i, j):
                return False
            return cheapest is None or not skipped or min(weights[c] for c in skipped) >= cheapest - 1e-6
        if len(cells) < 3:
            return cells
        out, i = [cells[0]], 0
        while i < len(cells) - 1:
            j = len(cells) - 1
            while j > i + 1 and not line_ok(i, j):
                j = max(i + 1, i + (j - i) // 2) if j - i > 40 else j - 1
            out.append(cells[j])
            i = j
        return out


class Search:

    def __init__(self, paths, instance, start, goal, margin_cells, start_z, goal_z, indoors, houses, ghost, avoid, seek,
                 roads, gather, max_cells, end_props, level, exempt=None, walker=None):
        self.paths, self.terrain = paths, paths.terrain
        self.instance, self.start, self.goal, self.start_z, self.goal_z = instance, start, goal, start_z, goal_z
        self.indoors, self.houses, self.ghost, self.avoid, self.seek = indoors, houses, ghost, avoid, seek
        self.roads, self.gather, self.end_props, self.level = roads, gather, end_props, level
        self.exempt = exempt
        self.walker, self.costly = walker, frozenset()
        self.floor_city = {}
        self.sr, self.sc = cell_of(*start)
        self.gr, self.gc = cell_of(*goal)
        (self.r0, self.c0, self.r1, self.c1), self.stride = search_box(start, goal, margin_cells, max_cells)
        self.degraded = False
        self.blds, self.dear = [], []
        self.big = {}
        self.placed = {}
        self.streets, self.doodads = set(), set()
        self.prop_walls = NO_WALLS
        self.near = None

    def read_ground(self):
        instance, r0, c0, r1, c1 = self.instance, self.r0, self.c0, self.r1, self.c1
        self.tiles = self.terrain.tiles_for(instance, r0, c0, r1, c1)
        roads = self.terrain.roads_for(instance, r0, c0, r1, c1)
        g = self.g = self.terrain.region(instance, r0, c0, r1, c1, self.tiles, roads)
        if np.isnan(g["ground"]).all():
            return False
        g["road"] = g["road"] >= ROAD_SHARE * 255
        trail = np.zeros(g["ground"].shape, bool)
        walked = tuple(self.terrain.trails.get(instance, ()))
        rr, cc = np.divmod(np.fromiter(walked, np.int64, len(walked)), 8192)
        inside = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
        trail[rr[inside] - r0, cc[inside] - c0] = True
        note_trails(instance, (r0, c0, r1, c1))
        cells, heights = self.terrain.npc_trails(instance)
        rr, cc = np.divmod(cells, 8192)
        sel = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
        rr, cc, zz = rr[sel] - r0, cc[sel] - c0, heights[sel]
        on_ground = np.abs(g["ground"][rr, cc] - zz) <= NPC_TRAIL_Z
        npc = self.npc = np.zeros(g["ground"].shape, bool)
        npc[rr[on_ground], cc[on_ground]] = True
        trail |= npc
        g["trail"] = trail
        return True

    def read_buildings(self):
        if not self.terrain.client_files:
            return
        paths, g, instance, start, goal = self.paths, self.g, self.instance, self.start, self.goal
        r0, c0, r1, c1, stride = self.r0, self.c0, self.r1, self.c1, self.stride
        blds, dear = self.blds, self.dear
        places = self.terrain.places_in(instance, r0, c0, r1, c1, small=stride == 1 and self.houses, tiles=self.tiles)
        big = [p for p in places if p[10]]
        small = houses_near(places, (start, goal))
        for p in small:
            ra, ca = cell_of(p[6], p[8])
            rb, cb = cell_of(p[7], p[9])
            g["building"][max(0, ra - r0):max(0, rb - r0 + 1), max(0, ca - c0):max(0, cb - c0 + 1)] = False
        paths.buildings.prefetch(instance, big + small)
        houses_at = {int(p[1]) for p in small}
        for place in big + small:
            try:
                blds.append(paths.buildings.get(instance, place))
            except NotBuilt as e:
                if place[10]:
                    raise
                wm.note_unbuilt(e.what)
                continue
            except OSError as e:
                self.degraded = self.degraded or not storedonly.not_there(e)
                continue
            except (ValueError, KeyError, struct.error):
                continue
            L = blds[-1]["layers"]
            own = int(place[1]) in houses_at and (in_house(place, L, start, self.start_z, self.indoors is False)
                                                  or in_house(place, L, goal, self.goal_z))
            dear.append(HOUSE_INSIDE if int(place[1]) in houses_at and not own else 1.0)
            self.placed[len(blds) - 1] = int(place[1])
            if place[10]:
                self.streets.add(len(blds) - 1)
                self.big[len(blds) - 1] = place
        if (stride == 1 and self.houses) or self.end_props:
            done = set()
            for end in (start, goal):
                area = (round(end[0] / PROP_GRID), round(end[1] / PROP_GRID))
                if area in done:
                    continue
                done.add(area)
                try:
                    props = paths.buildings.props(instance, end)
                except NotBuilt as e:
                    props = None
                    wm.note_unbuilt(e.what)
                except OSError as e:
                    props, self.degraded = None, self.degraded or not storedonly.not_there(e)
                except (ValueError, KeyError, struct.error):
                    props = None
                if props:
                    self.doodads.add(len(blds))
                    blds.append(props)
                    dear.append(1.0)
        try:
            self.prop_walls = paths.buildings.walls(instance, r0, c0, r1, c1)
        except OSError as e:
            self.degraded = self.degraded or not storedonly.not_there(e)
        except (ValueError, KeyError, struct.error):
            pass

    def floors_over(self):
        g, r0, c0, r1, c1 = self.g, self.r0, self.c0, self.r1, self.c1
        g["walls"], g["floored"] = np.zeros(g["ground"].shape, bool), np.zeros(g["ground"].shape, bool)
        g["barred"] = barred_grid(self.prop_walls.barred, r0, c0, g["ground"].shape)
        g["jumped"] = barred_grid(self.prop_walls.jumped, r0, c0, g["ground"].shape)
        under = np.zeros(g["ground"].shape, bool)
        self.floor_cells = np.zeros(g["ground"].shape, bool)
        for i, b in enumerate(self.blds):
            for key, cells in (("walls", b["blocks"]), ("floored", b["floored"])) if i not in self.doodads else ():
                rr, cc = np.divmod(cells, 8192)
                inside = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
                g[key][rr[inside] - r0, cc[inside] - c0] = True
            cells, tops = self.paths.buildings.worked_on(b, "tops", None, lambda: floor_tops(b["layers"]))
            rr, cc = np.divmod(cells, 8192)
            inside = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
            rr, cc, tops = rr[inside] - r0, cc[inside] - c0, tops[inside]
            self.floor_cells[rr, cc] = True
            over = tops > g["ground"][rr, cc] + JOIN_YARDS
            under[rr[over], cc[over]] = True
        g["trail"] &= ~under | self.npc

    def rules(self):
        g, level, ghost = self.g, self.level, self.ghost
        dungeon = self.dungeon = self.terrain.client_files and self.terrain.is_dungeon(self.instance)
        g["ghost"] = ghost
        g["trail_cost"] = 1.0 if self.gather else SAFE_TRAIL_COST if self.roads else TRAIL_COST
        g["path_cost"] = 1.0 if self.gather else PATH_COST
        g["danger_cost"] = SAFEST_COST if self.roads else SAFE_COST
        g["max_up"] = DUNGEON_MAX_UP if dungeon else MAX_UP
        g["cliff_jump"] = DUNGEON_CLIFF_JUMP if dungeon else CLIFF_JUMP
        easy = EASY.get()
        g["easy"] = easy is True
        g["fall_most"] = FALL_MOST if not (dungeon or ghost or easy) and self.stride == 1 else None
        if level and not ghost and not dungeon:
            self.paths.mark_over(g, level, (self.sr - self.r0, self.sc - self.c0), (self.gr - self.r0, self.gc - self.c0),
                                 exempt=self.exempt)
        self.costly = frozenset() if dungeon else self.paths.costly(self.walker)
        if self.costly:
            self.paths.mark_capitals(g, self.costly)

    def coarse(self):
        r0, c0, stride = self.r0, self.c0, self.stride
        fine = self.fine = self.g
        g = self.g = downsample(fine, stride)
        for k in ("ghost", "trail_cost", "path_cost", "danger_cost", "max_up", "cliff_jump", "easy", "fall_most"):
            g[k] = fine[k]
        h, w = self.h, self.w = g["ground"].shape
        self.fh, self.fw = fine["ground"].shape
        paths = self.paths
        pop = paths.populated_of(self.instance) if paths.populated_of and not self.dungeon else None
        if pop is not None and not self.gather:
            top, left, cell, grid = pop
            north = CORNER - (r0 + (np.arange(h) + 0.5) * stride) * CELL
            west = CORNER - (c0 + (np.arange(w) + 0.5) * stride) * CELL
            gi, gj = ((top - north) // cell).astype(int), ((left - west) // cell).astype(int)
            oki, okj = (gi >= 0) & (gi < grid.shape[0]), (gj >= 0) & (gj < grid.shape[1])
            near = grid[np.clip(gi, 0, grid.shape[0] - 1)][:, np.clip(gj, 0, grid.shape[1] - 1)]
            g["wild"] = ~(near & oki[:, None] & okj[None, :])

    def mobs(self):
        avoid, g, h, w = self.avoid, self.g, self.h, self.w
        if avoid is None or not len(avoid):
            return
        span = CELL * self.stride
        north0, west0 = world_of(self.r0, self.c0)[0] + CELL / 2, world_of(self.r0, self.c0)[1] + CELL / 2
        rr = (north0 - avoid[:, 0]) / span
        cc = (west0 - avoid[:, 1]) / span
        reach = avoid[:, 2] / span
        extra = SAFEST_MARGIN / span if self.roads else 0.0
        inside = (rr + reach + extra >= 0) & (rr - reach - extra < h) & (cc + reach + extra >= 0) & (cc - reach - extra < w)
        near = self.near = avoid[inside]
        mob_z = near[:, 4] if near.shape[1] > 4 else np.full(len(near), np.nan, np.float32)
        danger, worth = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
        ring = np.zeros((h, w), np.float32) if self.roads else None
        for (mr, mc, rad), weight, mz in zip(np.stack([rr[inside], cc[inside], reach[inside]], 1), near[:, 3], mob_z):
            out = rad + (extra if weight > 0 else 0.0)
            i0, i1 = max(0, int(mr - out)), min(h, int(mr + out) + 2)
            j0, j1 = max(0, int(mc - out)), min(w, int(mc + out) + 2)
            if weight > 0 and np.isfinite(mz):
                gz = g["ground"][min(max(int(mr), 0), h - 1), min(max(int(mc), 0), w - 1)]
                if np.isfinite(gz) and mz < gz - MOB_UNDER:
                    continue
            ii, jj = np.ogrid[i0:i1, j0:j1]
            d2 = (ii + 0.5 - mr) ** 2 + (jj + 0.5 - mc) ** 2
            reached = d2 <= rad ** 2
            if weight >= 0:
                danger[i0:i1, j0:j1] += weight * reached
                if ring is not None:
                    ring[i0:i1, j0:j1] += weight * (d2 <= out ** 2)
            else:
                worth[i0:i1, j0:j1] -= weight * reached
        g["danger"] = danger
        if ring is not None:
            g["ring"] = ring
        if self.seek:
            g["worth"] = worth
        if self.gather:
            g["pull"] = worth > 0

    def terrain_graph(self):
        g, fine, stride, h, w, fh, fw = self.g, self.fine, self.stride, self.h, self.w, self.fh, self.fw
        rows, cols, data = self.rows, self.cols, self.data = [], [], []
        if stride == 1:
            n = h * w
            idx = np.arange(n).reshape(h, w)
            step_moves = moves(g, CELL)
            for dr, dc, rs, cs, ok, cost, _ in step_moves:
                _, _, rt, ct = shifted(h, w, dr, dc)
                rows.append(idx[rs, cs][ok]); cols.append(idx[rt, ct][ok]); data.append(cost[ok])
            node_of = lambda r, c: r * w + c
            cells_of = lambda nodes: np.divmod(np.asarray(nodes), w)
            weights = cell_weights(g, CELL)
        else:
            piece, n, at, (pa, pb, fall), step_moves = block_pieces(fine, stride)
            weights = cell_weights(g, CELL * stride)
            blk = np.minimum(at[:, 0] // stride, h - 1).astype(np.int64) * w + np.minimum(at[:, 1] // stride, w - 1).astype(np.int64)
            wp = weights.ravel()[blk]
            yards = np.maximum(np.hypot(at[pa, 0] - at[pb, 0], at[pa, 1] - at[pb, 1]), 0.5) * CELL
            rows.append(pa); cols.append(pb); data.append(yards * (wp[pa] + wp[pb]) / 2 + fall * wmonav.DROP_COST)
            node_of = lambda r, c: piece[r, c]
            spot_of = np.clip(np.rint(at), 0, [fh - 1, fw - 1]).astype(np.int64)
            cells_of = lambda nodes: (spot_of[np.asarray(nodes), 0], spot_of[np.asarray(nodes), 1])
            weights = np.repeat(np.repeat(weights, stride, 0), stride, 1)
        mobs_at = g.get("danger")
        if mobs_at is not None and stride > 1:
            mobs_at = np.repeat(np.repeat(mobs_at, stride, 0), stride, 1)
        self.n, self.step_moves, self.node_of, self.cells_of, self.weights, self.mobs_at = n, step_moves, node_of, cells_of, weights, mobs_at

    def building_graph(self):
        blds, dear, near, node_of = self.blds, self.dear, self.near, self.node_of
        r0, c0, r1, c1, fh, fw = self.r0, self.c0, self.r1, self.c1, self.fh, self.fw
        rows, cols, data = self.rows, self.cols, self.data
        passable = self.passable = np.zeros((fh, fw), bool)
        for dr, dc, rs, cs, ok, _, _ in self.step_moves:
            passable[rs, cs] |= ok
        ground = self.ground = self.fine["ground"]
        offsets, total, hots = self.offsets, self.total, self.hots = [], self.n, []
        for i, (b, k) in enumerate(zip(blds, dear)):
            offsets.append(total)
            gb = b["graph"].tocoo()
            cost = gb.data * k
            hot = floor_danger(b["layers"], near, lambda key, work, b=b: self.paths.buildings.worked_on(b, "hot", key, work, HOT_KEPT))
            hots.append(hot)
            if hot is not None:
                cost = cost * (1 + self.g.get("danger_cost", SAFE_COST) * np.minimum((hot[gb.row] + hot[gb.col]) / 2, DANGER_CAP))
            cities = self.paths.floor_cities(self.instance, b) if self.costly else None
            if cities is not None:
                city = np.where(np.isin(cities, list(self.costly)), cities, 0)
                if city.any():
                    self.floor_city[i] = city
                    far = (city > 0).astype(np.float64)
                    cost = cost * (1 + (CAPITAL_COST - 1) * (far[gb.row] + far[gb.col]) / 2)
            rows.append(gb.row.astype(np.int64) + total); cols.append(gb.col.astype(np.int64) + total); data.append(cost)
            jr, jc = np.divmod(b["joins"][:, 1], 8192)
            inside = (jr >= r0) & (jr < r1) & (jc >= c0) & (jc < c1)
            L = b["layers"]
            jn = b["joins"][inside, 0]
            floor = L.heights[L.nodes[jn, 0], L.nodes[jn, 1], L.nodes[jn, 2]]
            rr, cc = jr[inside] - r0, jc[inside] - c0
            rise = floor - ground[rr, cc]
            up, down = join_steps(rise, b["onto"][inside])
            up, down = passable[rr, cc] & up, passable[rr, cc] & down
            wn, ww = L.world(L.nodes[jn, 0], L.nodes[jn, 1])
            tn, tw = world_of(jr[inside], jc[inside])
            yards = np.maximum(np.hypot(wn - tn, ww - tw), CELL / 2)
            yards = yards + (np.abs(rise) > JOIN_UP) * wmonav.DROP_COST
            rows += [np.asarray(node_of(rr[up], cc[up]), np.int64), jn[down] + total]
            cols += [jn[up] + total, np.asarray(node_of(rr[down], cc[down]), np.int64)]
            data += [yards[up], yards[down]]
            total += len(L.nodes)
        self.total = total
        placed = []
        for b, off in zip(blds, offsets):
            L = b["layers"]
            wn, ww = L.world(L.nodes[:, 0], L.nodes[:, 1])
            placed.append((np.round(np.asarray(wn)).astype(np.int64), np.round(np.asarray(ww)).astype(np.int64),
                           L.heights[L.nodes[:, 0], L.nodes[:, 1], L.nodes[:, 2]], off))
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                (na, wa, ha, oa), (nb, wb, hb, ob) = placed[i], placed[j]
                if not len(na) or not len(nb) or na.min() > nb.max() + 1 or nb.min() > na.max() + 1                         or wa.min() > wb.max() + 1 or wb.min() > wa.max() + 1:
                    continue
                keys_a = na * 100003 + wa
                order = np.argsort(keys_a, kind="stable")
                sorted_a, keys_b = keys_a[order], nb * 100003 + wb
                for dn in (-1, 0, 1):
                    for dw in (-1, 0, 1):
                        want = keys_b + dn * 100003 + dw
                        lo = np.searchsorted(sorted_a, want, "left")
                        many = np.searchsorted(sorted_a, want, "right") - lo
                        kb = np.repeat(np.arange(len(want)), many)
                        ka = order[np.repeat(lo, many) + np.arange(len(kb)) - np.repeat(np.cumsum(many) - many, many)]
                        near = np.abs(ha[ka] - hb[kb]) <= STEP_JOIN
                        ka, kb = ka[near] + oa, kb[near] + ob
                        rows += [ka, kb]; cols += [kb, ka]; data += [np.full(len(ka), 1.5), np.full(len(kb), 1.5)]
        def spot(point):
            best, best_d = None, 5.0
            rr, cc = cell_of(point[0], point[1])
            if r0 <= rr < r1 and c0 <= cc < c1:
                tn, gz = int(node_of(rr - r0, cc - c0)), ground[rr - r0, cc - c0]
                if tn >= 0 and not np.isnan(gz) and abs(gz - point[2]) < best_d:
                    best, best_d = tn, abs(gz - point[2])
            for b, off in zip(blds, offsets):
                L = b["layers"]
                for i in L.near(point[0], point[1], (point[2] - 4, point[2] + 4), radius=8, every=True):
                    d = abs(L.heights[tuple(L.nodes[i])] - point[2])
                    if d < best_d:
                        best, best_d = i + off, d
            return best
        inside_box = lambda p: r0 <= cell_of(p[0], p[1])[0] < r1 and c0 <= cell_of(p[0], p[1])[1] < c1
        for m in self.paths.movers():
            ends = mover_ends(m)
            if m["map"] != self.instance or not all(inside_box(p) for p in ends):
                continue
            if not rideable(m.get("side"), self.walker):
                continue
            a, b = (spot(p) for p in ends)
            if a is not None and b is not None and a != b:
                cost = ride_yards(m)
                rows.append(np.array([a])); cols.append(np.array([b])); data.append(np.array([cost]))
                if not m.get("oneWay"):
                    rows.append(np.array([b])); cols.append(np.array([a])); data.append(np.array([cost]))

    def close_graph(self):
        rows, cols, data = np.concatenate(self.rows), np.concatenate(self.cols), np.concatenate(self.data)
        blocked = self.paths.blocked_nodes(self.instance, self.blds, self.offsets)
        if len(blocked):
            keep = ~(np.isin(rows, blocked) | np.isin(cols, blocked))
            rows, cols, data = rows[keep], cols[keep], data[keep]
        self.graph = csr_matrix((data, (rows, cols)), shape=(self.total, self.total))
        self.sfr, self.sfc, self.gfr, self.gfc = self.sr - self.r0, self.sc - self.c0, self.gr - self.r0, self.gc - self.c0
        self.tstart, self.tgoal = int(self.node_of(self.sfr, self.sfc)), int(self.node_of(self.gfr, self.gfc))

    def building_of(self, node):
        return max(i for i, off in enumerate(self.offsets) if node >= off)

    def node_height(self, node):
        k = self.building_of(node)
        L = self.blds[k]["layers"]
        return float(L.heights[tuple(L.nodes[node - self.offsets[k]])])

    def building_nodes(self, point, z, near_ground_only, radius=2):
        found = []
        pr, pc = cell_of(*point)
        for b, off in zip(self.blds, self.offsets):
            L = b["layers"]
            for i in L.near(point[0], point[1], z, radius=radius, every=radius > 2):
                hh = L.heights[tuple(L.nodes[i])]
                if near_ground_only and not (abs(hh - self.ground[pr - self.r0, pc - self.c0]) <= 3):
                    continue
                found.append(i + off)
        return found

    def floors_under(self, point, gz, every=False, within=None):
        found = []
        for f in self.building_nodes(point, None, False, radius=INDOOR_REACH):
            k = self.building_of(f)
            if k in self.doodads or (within is not None and k not in within) \
                    or not (np.isnan(gz) or self.node_height(f) < gz - MOB_UNDER):
                continue
            L = self.blds[k]["layers"]
            r, c, _ = L.nodes[f - self.offsets[k]]
            n, w = L.world(r, c)
            found.append((math.hypot(float(n) - point[0], float(w) - point[1]), f))
        if every:
            return [f for _, f in found]
        nearest = min((d for d, _ in found), default=0.0)
        return [f for d, f in found if d <= nearest + 1.5]

    def share_floor(self):
        goal_floors = self.floors_under(self.goal, self.ground[self.gfr, self.gfc], every=True)
        kept = {self.building_of(f) for f in goal_floors}
        if not kept:
            return False
        on = [f for f in self.sources if f >= self.n and self.building_of(f) in kept]
        if not on:
            on = self.floors_under(self.start, self.ground[self.sfr, self.sfc], within=kept)
            if on and self.indoors is False and self.room_indoors(on[0]):
                on = []
        if not on:
            return False
        self.sources, self.others, self.pocket = on, [], False
        self.targets, self.fallback = goal_floors, []
        self.goal_height, self.snapped = None, False
        return True

    def room_indoors(self, node):
        ask = self.paths.room_indoors
        if ask is None:
            return False
        k = self.building_of(node)
        L = self.blds[k]["layers"]
        r, c, l = L.nodes[node - self.offsets[k]]
        n, w = L.world(r, c)
        return bool(ask(self.instance, float(n), float(w), float(L.heights[r, c, l])))

    def near_ones(self, r, c, reach):
        got = []
        for dr in range(-reach, reach + 1):
            for dc in range(-reach, reach + 1):
                if 0 <= r + dr < self.fh and 0 <= c + dc < self.fw and self.passable[r + dr, c + dc]:
                    got.append(int(self.node_of(r + dr, c + dc)))
        return list(dict.fromkeys(got))

    def standing(self, nodes, z, bare=False):
        if z is None or not nodes:
            return nodes
        rr, cc = self.cells_of(nodes)
        return [k for k, gz in zip(nodes, self.ground[rr, cc].tolist()) if ground_stands(gz, z, bare)]

    def reached_from(self, spot, nodes):
        yards = self.prop_walls.yards
        cells = [k for k in nodes if 0 <= k < self.n]
        if not len(yards) or not cells or walls_crossed(yards, spot[0], spot[1], spot[0], spot[1])[0]:
            return nodes
        rr, cc = self.cells_of(cells)
        north, west = world_of(self.r0 + np.asarray(rr), self.c0 + np.asarray(cc))
        far = walls_crossed(yards, np.full(len(cells), float(spot[0])), np.full(len(cells), float(spot[1])), north, west)
        past = {k for k, f in zip(cells, far.tolist()) if f}
        return [k for k in nodes if k not in past]

    def ring_by(self, spot, r, c, z, bare, radii):
        first = []
        for rad in radii:
            got = self.standing(self.near_ones(r, c, rad * self.stride), z, bare)
            side = self.reached_from(spot, got)
            if side:
                return side, True
            first = first or got
        return first, False

    def fall_pocket(self, sources):
        if self.stride != 1 or not self.fine.get("fall_most"):
            return False
        height = blocked_cells(self.fine)[1]
        moves_by = [(dr, dc, ok) for dr, dc, rs, cs, ok, _, _ in self.step_moves]
        seen = set()
        for s in sources:
            if s < self.n:
                rr, cc = self.cells_of([s])
                seen.add((int(rr[0]), int(cc[0])))
        todo = list(seen)
        while todo and len(seen) <= POCKET:
            r, c = todo.pop()
            for dr, dc, ok in moves_by:
                rt, ct = r + dr, c + dc
                rs, cs = r - max(0, -dr), c - max(0, -dc)
                if not (0 <= rt < self.fh and 0 <= ct < self.fw) or (rt, ct) in seen:
                    continue
                if not (0 <= rs < ok.shape[0] and 0 <= cs < ok.shape[1]) or not ok[rs, cs]:
                    continue
                if height[r, c] - height[rt, ct] > FALL_MARKED:
                    continue
                seen.add((rt, ct))
                todo.append((rt, ct))
        return len(seen) <= POCKET

    def ends(self):
        start, goal, start_z, goal_z, indoors = self.start, self.goal, self.start_z, self.goal_z, self.indoors
        ground, passable, stride = self.ground, self.passable, self.stride
        sfr, sfc, gfr, gfc, tstart, tgoal = self.sfr, self.sfc, self.gfr, self.gfc, self.tstart, self.tgoal
        building_nodes, near_ones, node_height = self.building_nodes, self.near_ones, self.node_height
        on_ground, others, pocket = True, [], False
        self.indoor_start = None
        bare = False
        if start_z is not None:
            sources = building_nodes(start, start_z, False)
            bare = not sources
            on_ground = ground_stands(ground[sfr, sfc], start_z, bare)
        elif indoors:
            sources = [f for f in building_nodes(start, None, False) if self.building_of(f) not in self.doodads]
            self.indoor_start = (start, ground[sfr, sfc])
            if not sources:
                sources = self.floors_under(*self.indoor_start)
            on_ground = not sources
            others, pocket = [f for f in near_ones(sfr, sfc, 3 * stride) if f not in sources], True
        elif indoors is False:
            floors = building_nodes(start, None, False, radius=1)
            gz = ground[sfr, sfc]
            over = floors if np.isnan(gz) else [f for f in floors if self.building_of(f) in self.streets]
            top = max((node_height(f) for f in over), default=None)
            if top is not None and (np.isnan(gz) or top > gz + OVER_GROUND):
                sources, on_ground = [f for f in over if node_height(f) >= top - 3], False
                others = [f for f in floors if f not in sources] + ([tstart] if tstart >= 0 and passable[sfr, sfc] else [])
            else:
                sources = building_nodes(start, None, True)
        else:
            sources = building_nodes(start, None, True)
        if on_ground:
            own = self.reached_from(start, [tstart]) if tstart >= 0 else []
            ring = []
            if not passable[sfr, sfc] or (tstart >= 0 and not own):
                ring, kept = self.ring_by(start, sfr, sfc, start_z, bare, (1, 2, 3))
                if not kept:
                    own = [tstart] if tstart >= 0 else []
                    ring = [] if passable[sfr, sfc] else ring
            sources = own + sources + ring
            if start_z is None:
                others = [f for f in near_ones(sfr, sfc, 3 * stride) + building_nodes(start, None, False, radius=1)
                          if f not in sources]
                pocket = True
        ground_goal, goal_bare = ([tgoal] if tgoal >= 0 else []), False
        if ground_goal and not self.reached_from(goal, ground_goal):
            around, kept = self.ring_by(goal, gfr, gfc, goal_z, False, (1, 2))
            ground_goal = around if kept else ground_goal
        if goal_z is not None:
            targets = building_nodes(goal, goal_z, False)
            goal_bare = not targets
            goal_on_ground = ground_stands(ground[gfr, gfc], goal_z, goal_bare)
            if goal_on_ground:
                targets += ground_goal
            fallback = []
        elif self.floor_cells[max(0, gfr - 1):gfr + 2, max(0, gfc - 1):gfc + 2].any():
            targets = building_nodes(goal, None, False, radius=12)
            fallback = ground_goal
            goal_on_ground = not targets
            gz = ground[gfr, gfc]
            tops = {t for t in targets if np.isfinite(gz) and self.building_of(t) in self.doodads
                    and node_height(t) > gz + OVER_GROUND}
            if tops:
                targets = [t for t in targets if t not in tops]
                if all(self.building_of(t) in self.doodads for t in targets):
                    targets, goal_on_ground = targets + ground_goal, True
                fallback = [t for t in ground_goal if t not in targets] + sorted(tops)
        else:
            targets, fallback, goal_on_ground = ground_goal, [], True
        on_ground_z = self.surfaces(gfr, gfc) if goal_z is None and goal_on_ground else np.nan
        self.goal_height = goal_z if goal_z is not None else float(on_ground_z) if np.isfinite(on_ground_z) else None
        snapped = False
        on_face = self.ghost and bool(ghost_faces(self.fine, on_water(self.fine))[gfr, gfc])
        if goal_on_ground and (not passable[gfr, gfc] or on_face):
            around = self.standing(near_ones(gfr, gfc, SNAP_CELLS * stride), goal_z, goal_bare)
            around = self.reached_from(goal, around) or around
            if around:
                targets = [t for t in targets if t != tgoal] + around
                snapped = True
        self.sources, self.targets, self.fallback, self.snapped = sources, targets, fallback, snapped
        self.others, self.pocket = others, pocket
        self.over = [f for f in building_nodes(start, None, False, radius=1) if f not in sources
                     and self.building_of(f) not in self.doodads] if start_z is None and indoors is False else []

    def surfaces(self, rr, cc):
        z, wz = self.ground[rr, cc], self.fine["water"][rr, cc]
        return np.where(np.isfinite(wz) & ~(np.isfinite(z) & (z >= wz)), wz, z)

    def from_goal(self, nodes):
        nodes = np.asarray(nodes, np.int64)
        north, west, z = np.empty(len(nodes)), np.empty(len(nodes)), np.empty(len(nodes))
        land = nodes < self.n
        rr, cc = self.cells_of(nodes[land])
        north[land], west[land] = world_of(self.r0 + rr, self.c0 + cc)
        z[land] = self.surfaces(rr, cc)
        for b, off in zip(self.blds, self.offsets):
            L = b["layers"]
            mine = (nodes >= off) & (nodes < off + len(L.nodes))
            r, c, l = L.nodes[nodes[mine] - off].T
            north[mine], west[mine] = L.world(r, c)
            z[mine] = L.heights[r, c, l]
        flat, want = np.hypot(north - self.goal[0], west - self.goal[1]), self.goal_height
        if want is None:
            return flat, np.full(len(nodes), np.nan)
        if isinstance(want, tuple):
            return flat, np.maximum(np.maximum(want[0] - z, z - want[1]), 0.0)
        return flat, np.abs(z - want)

    def offset(self, node):
        goal = self.goal
        if node < self.n:
            if not self.snapped:
                return 0.0
            cr, cc_ = (int(v) for v in self.cells_of([node]))
            wn, ww = world_of(self.r0 + cr, self.c0 + cc_)
            return math.hypot(wn - goal[0], ww - goal[1])
        k = max(i for i, off in enumerate(self.offsets) if node >= off)
        L = self.blds[k]["layers"]
        r, c, _l = L.nodes[node - self.offsets[k]]
        wn, ww = L.world(r, c)
        return math.hypot(wn - goal[0], ww - goal[1])

    def nearest_reached(self, dist):
        ok = np.flatnonzero(np.isfinite(dist))
        flat, up = self.from_goal(ok)
        near = np.hypot(flat, np.nan_to_num(up))
        k = int(np.lexsort((dist[ok], np.round(near, 1)))[0])
        return int(ok[k]), float(near[k]) if self.goal_height is not None else None

    def walk(self):
        sources, targets, fallback, n, stride = self.sources, self.targets, self.fallback, self.n, self.stride

        def from_(starts):
            dist, pred, _ = dijkstra(self.graph, indices=starts, return_predecessors=True, min_only=True) if starts \
                else (np.full(self.total, np.inf), np.full(self.total, -9999), None)
            return dist, pred, [t for t in targets if np.isfinite(dist[t])] or [t for t in fallback if np.isfinite(dist[t])]
        dist, pred, reach = from_(sources)
        if not reach and self.indoor_start is not None:
            more = [f for f in self.floors_under(*self.indoor_start, every=True) if f not in sources]
            if more:
                sources = sources + more
                dist, pred, reach = from_(sources)
        if not reach and self.others and (not self.pocket or np.isfinite(dist[:n]).sum() <= POCKET):
            dist, pred, reach = from_(sources + self.others)
        elif reach and self.others and self.pocket and self.fall_pocket(sources):
            dist, pred, reach = from_(sources + self.others)
        if not reach and self.over:
            heights = {f: self.node_height(f) for f in self.over}
            for top in sorted(set(heights.values()), reverse=True):
                tried = from_([f for f, z in heights.items() if top - 3 <= z <= top])
                if tried[2]:
                    dist, pred, reach = tried
                    break
        partial, self.near_end = not reach, None
        if not np.isfinite(dist).any():
            return False
        if reach:
            end = min(reach, key=lambda t: (round(self.offset(t)), dist[t]))
        else:
            end, near = self.nearest_reached(dist)
            if near is not None and near <= TALK_REACH:
                partial, self.near_end = False, near
        boxed = False
        if partial:
            fh, fw, r0, c0, r1, c1 = self.fh, self.fw, self.r0, self.c0, self.r1, self.c1
            seen = np.flatnonzero(np.isfinite(dist[:n]))
            if len(seen):
                rr, cc = self.cells_of(seen)
                boxed = bool(((rr < stride) | (rr >= fh - stride) | (cc < stride) | (cc >= fw - stride)).any())
            for b, off in zip(self.blds, self.offsets):
                if boxed:
                    break
                L = b["layers"]
                fin = np.flatnonzero(np.isfinite(dist[off:off + len(L.nodes)]))
                if len(fin):
                    wn, ww = L.world(L.nodes[fin, 0], L.nodes[fin, 1])
                    rr, cc = (CORNER - np.asarray(wn)) // CELL, (CORNER - np.asarray(ww)) // CELL
                    boxed = bool(((rr <= r0 + stride) | (rr >= r1 - 1 - stride) | (cc <= c0 + stride) | (cc >= c1 - 1 - stride)).any())
        self.dist, self.pred, self.end, self.partial, self.boxed = dist, pred, end, partial, boxed
        return True

    def tricky(self, pts, cells):
        fine = self.fine
        self.fallen = 0.0
        tilt = fine.get("tilt")
        limit = fine.get("max_up", MAX_UP)
        steep = None if tilt is None or fine.get("ghost") else (tilt > limit) & ~fine["trail"] & ~on_water(fine)
        climbs, drops = [], []
        for j in range(1, len(pts)):
            a, b = cells[j - 1], cells[j]
            if a is None or b is None or len(pts[j - 1]) < 3 or len(pts[j]) < 3:
                continue
            fall = pts[j - 1][2] - pts[j][2]
            if fall >= FALL_MARKED and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 2:
                drops.append(j - 1)
                self.fallen += fall_share(fall + FALL_MARGIN)
            elif fall < 0 and steep is not None:
                n = max(abs(a[0] - b[0]), abs(a[1] - b[1])) * 2 + 1
                rr = np.rint(np.linspace(a[0], b[0], n)).astype(np.int64)
                cc = np.rint(np.linspace(a[1], b[1], n)).astype(np.int64)
                if steep[rr, cc].any():
                    climbs.append(j - 1)
        return climbs, drops

    def way(self, to_goal=True):
        start, goal, goal_z, n, stride, end, partial = self.start, self.goal, self.goal_z, self.n, self.stride, self.end, self.partial
        blds, offsets, cells_of, fine, ground, r0, c0 = self.blds, self.offsets, self.cells_of, self.fine, self.ground, self.r0, self.c0
        pred, near = self.pred, self.near
        chain = [end]
        while pred[chain[-1]] >= 0:
            chain.append(int(pred[chain[-1]]))
        chain.reverse()
        ok_moves = walks(self.step_moves)
        yards = self.prop_walls.yards
        crosses = (lambda p, q: bool(walls_crossed(yards, p[0], p[1], q[0], q[1])[0])) if len(yards) else None
        clear = lambda p: crosses is not None and not crosses(p, p)
        near_goal = round(self.near_end) if self.near_end is not None else round(self.offset(end)) if self.snapped and not partial else 0
        at_goal = bool(not partial and not near_goal and to_goal)
        owner = lambda node: -1 if node < n else max(k for k, off in enumerate(offsets) if node >= off)
        def surface(r, c):
            z, wz = ground[r, c], fine["water"][r, c]
            if np.isfinite(wz) and not (np.isfinite(z) and z >= wz):
                z = wz
            return (float(z),) if np.isfinite(z) else ()
        pts, i, ground_cells = [], 0, []
        while i < len(chain):
            j = i
            while j + 1 < len(chain) and owner(chain[j + 1]) == owner(chain[i]):
                j += 1
            run, k = chain[i:j + 1], owner(chain[i])
            if k < 0:
                rr, cc = cells_of(run)
                cells = list(zip(rr.tolist(), cc.tolist()))
                spots = [world_of(r0 + r, c0 + c) for r, c in cells]
                if i == 0 and clear(start):
                    spots[0] = tuple(start[:2])
                if j == len(chain) - 1 and at_goal and clear(goal):
                    spots[-1] = tuple(goal[:2])
                walls = (lambda a, b, spots=spots: crosses(spots[a], spots[b])) if crosses else None
                cells = self.paths.straighten(cells, ok_moves, self.fh, self.fw, self.weights, self.mobs_at, walls)
                pts += [[*world_of(r0 + r, c0 + c), *surface(r, c)] for r, c in cells]
                ground_cells += cells
            else:
                L, off = blds[k]["layers"], offsets[k]
                for v in wmonav.straighten(L, blds[k]["graph"], [v - off for v in run], self.hots[k]):
                    r, c, l = L.nodes[v]
                    pts.append([*L.world(r, c), float(L.heights[r, c, l])])
                    ground_cells.append(None)
            i = j + 1
        climbs, drops = self.tricky(pts, ground_cells)
        on_ground = lambda a, b: len(pts) > 1 and ground_cells[a] is not None and ground_cells[b] is not None
        if clear(start) and on_ground(0, 1) and crosses(start, pts[1]):
            climbs, drops = [c + 1 for c in climbs], [d + 1 for d in drops]
        else:
            pts = pts[1:]
            ground_cells = ground_cells[1:]
        if pts and at_goal:
            if clear(goal) and on_ground(-2, -1) and crosses(pts[-2], goal):
                pts.append([*goal, *pts[-1][2:]])
            else:
                pts[-1][:2] = list(goal)
        gap = 0
        if partial:
            last = pts[-1] if pts else start
            gap = math.hypot(last[0] - goal[0], last[1] - goal[1])
            up = float(self.from_goal([end])[1][0]) if goal_z is not None else np.nan
            if up > HEIGHT_GAP:
                gap = math.hypot(gap, up)
            gap = round(gap)
            pts.append(list(goal))
        length, prev = 0.0, start
        for p in pts:
            length += math.hypot(p[0] - prev[0], p[1] - prev[1])
            prev = p
        terrain = np.asarray([v for v in chain if v < n], np.int64)
        tr, tc = cells_of(terrain) if len(terrain) else (np.zeros(0, np.int64), np.zeros(0, np.int64))
        wet = np.zeros(len(tr), bool) if self.ghost else on_water(fine)[tr, tc]
        swum = float(wet.sum()) * CELL * stride
        out = {"points": [[round(v, 1) for v in p] for p in pts], "length": round(length),
               "partial": partial, "stride": stride, "boxed": self.boxed, "cost": round(float(self.dist[end]), 1), "swum": round(swum)}
        if swum:
            lo, hi = 0, len(wet)
            while chain[0] < n and lo < hi and wet[lo]:
                lo += 1
            while not partial and chain[-1] < n and hi > lo and wet[hi - 1]:
                hi -= 1
            out["offshore"] = round(float(offshore(fine)[tr[lo:hi], tc[lo:hi]].max()), 1) if hi > lo else 0.0
        if "over" in fine:
            crossed = fine["over"][tr, tc]
            if crossed.any():
                out["over"] = round(float(crossed.sum()) * CELL * stride)
                out["overZones"] = [int(z) for z in dict.fromkeys(fine["zone"][tr, tc][crossed].tolist())]
        towns, yards = [], 0.0
        if "city" in fine:
            ids = fine["city"][tr, tc]
            ids = ids[(ids > 0) & (ids != (self.walker.goal if self.walker else 0))]
            towns, yards = ids.tolist(), float(len(ids)) * CELL * stride
        for k, city in self.floor_city.items():
            off, L = offsets[k], blds[k]["layers"]
            mine = np.asarray([v - off for v in chain if off <= v < off + len(L.nodes)], np.int64)
            ids = city[mine] if len(mine) else mine
            ids = ids[(ids > 0) & (ids != (self.walker.goal if self.walker else 0))]
            towns, yards = towns + ids.tolist(), yards + float(len(ids)) * L.res
        if towns:
            out["enemy"] = round(yards)
            out["enemyCities"] = [int(c) for c in dict.fromkeys(towns)]
        if partial:
            out["gap"] = gap
        if climbs:
            out["climbs"] = climbs
        if drops:
            out["drops"] = drops
            out["fall"] = round(self.fallen, 2)
        if self.degraded:
            out["degraded"] = True
        if near_goal:
            out["near"] = near_goal
        if near is not None:
            out["mobs"] = mobs_passed(start, pts, near[near[:, 3] >= 0])
            if self.seek:
                out["fight"] = mobs_passed(start, pts, near[near[:, 3] < 0])
        return out
