# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import json
import math
import os
import struct

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
APPROVED = os.path.join(ROOT, "data", "dungeon_levels.json")

WALKABLE = 0.6
SPACING = 0.5
GAP = 6.0
WIDTH = 5
PAIR_MIN = 50
STEP = 2.0
GROUND = "ground"
SQUARE = 16
HEAD = 5.0


def level_boxes(floor_of, level, k):
    squares = {}
    for r, f in floor_of.items():
        if level.get(r) != k:
            continue
        for ix, iy, z in f:
            s = (int(ix // SQUARE), int(iy // SQUARE))
            lo, hi = squares.get(s, (z, z))
            squares[s] = (min(lo, z), max(hi, z))
    return [[sx * SQUARE, sy * SQUARE, round(float(lo) - 1, 1), (sx + 1) * SQUARE, (sy + 1) * SQUARE,
             round(float(hi) + HEAD, 1)] for (sx, sy), (lo, hi) in sorted(squares.items())]


def approved():
    try:
        with open(APPROVED, encoding="utf-8") as f:
            return {int(k): v for k, v in (json.load(f).get("approved") or {}).items()}
    except (OSError, ValueError):
        return {}


def room_floor(raw, place):
    import wmonav
    v, t, _ = wmonav.group_geometry(raw)
    if not len(t):
        return np.zeros((0, 3))
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    n = np.cross(b - a, c - a)
    up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-9) >= WALKABLE
    if not up.any():
        return np.zeros((0, 3))
    p, _ = wmonav.sample_triangles(a[up], b[up], c[up], SPACING)
    _, ox, oy, oz, yaw, *_ = place
    ang = math.radians(180 + yaw)
    ca, sa = math.cos(ang), math.sin(ang)
    x, y = ox + p[:, 0] * ca - p[:, 1] * sa, oy + p[:, 0] * sa + p[:, 1] * ca
    return np.unique(np.stack([np.floor(x), np.floor(y), np.round(oz + p[:, 2])], axis=1), axis=0)


def floors(rooms, places, version):
    import clientfiles as wm
    out, groups = {}, {}
    for n, g in sorted(set(rooms)):
        fid = places[n][0]
        if fid not in groups:
            root = wm.chunks(wm.fetch_dropped(wm.file_address(fid, version), f"wmo-{fid}.wmo"))
            gfid = root.get("GFID", b"")
            groups[fid] = list(struct.unpack_from(f"<{len(gfid) // 4}I", gfid)) if gfid else []
        gf = groups[fid]
        if g >= len(gf) or not gf[g]:
            out[(n, g)] = np.zeros((0, 3))
            continue
        out[(n, g)] = room_floor(wm.fetch(wm.file_address(gf[g], version), f"wmog-{gf[g]}.wmo"), places[n])
    return out


def bands(zs):
    zs = sorted(zs)
    out, cur = [], [zs[0]]
    for z, k in zs[1:]:
        if z - cur[-1][0] >= GAP:
            out.append(cur)
            cur = [(z, k)]
        else:
            cur.append((z, k))
    out.append(cur)
    return out


def widened(cells):
    import cv2
    if not cells:
        return set()
    xs, ys = zip(*cells)
    x0, y0 = min(xs), min(ys)
    m = np.zeros((max(xs) - x0 + 1, max(ys) - y0 + 1), np.uint8)
    m[np.array(xs) - x0, np.array(ys) - y0] = 1
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WIDTH, WIDTH)))
    ix, iy = np.nonzero(m)
    return set(zip((ix + x0).tolist(), (iy + y0).tolist()))


def over_each_other(by_cell):
    pairs = collections.Counter()
    for cell in widened({c for c, zs in by_cell.items() if len(bands(zs)) > 1}):
        bs = bands(by_cell[cell])
        here = {(a, b) for lo, hi in zip(bs, bs[1:]) for _, a in lo for _, b in hi if a != b}
        pairs.update(here)
    return {p: n for p, n in pairs.items() if n >= PAIR_MIN}


def under_ground(by_cell, ground):
    cells, judged = collections.defaultdict(set), collections.Counter()
    for (cx, cy), zs in by_cell.items():
        g = ground(cx + 0.5, cy + 0.5)
        if g is None:
            continue
        for z, k in zs:
            judged[k] += 1
            if z <= g - GAP:
                cells[k].add((cx, cy))
    out = {}
    for k, cs in cells.items():
        n = len(widened(cs))
        if n >= PAIR_MIN and len(cs) * 2 > judged[k]:
            out[k] = n
    return out


def cycle(over):
    state, stack = {}, []

    def visit(k):
        state[k] = 1
        stack.append(k)
        for u in list(over.get(k, ())):
            if state.get(u) == 1:
                return stack[stack.index(u):]
            if u not in state:
                got = visit(u)
                if got:
                    return got
        state[k] = 2
        stack.pop()
        return None
    for k in list(over):
        if k not in state:
            got = visit(k)
            if got:
                return got
    return None


def levels(floor_of, ground=None):
    by_cell = collections.defaultdict(list)
    for k, f in floor_of.items():
        for ix, iy, z in f:
            by_cell[(int(ix), int(iy))].append((float(z), k))
    over = collections.defaultdict(dict)
    for (a, b), n in over_each_other(by_cell).items():
        over[a][b] = n
    for k, n in (under_ground(by_cell, ground) if ground else {}).items():
        over[k][GROUND] = n
    while True:
        cyc = cycle(over)
        if not cyc:
            break
        a, b = min(zip(cyc, cyc[1:] + cyc[:1]), key=lambda e: over[e[0]][e[1]])
        del over[a][b]
    depth = {}

    def down(k):
        if k not in depth:
            depth[k] = 0
            depth[k] = max((down(u) + 1 for u in over.get(k, ())), default=0)
        return depth[k]
    level = {k: down(k) for k in set(over) | {u for d in over.values() for u in d} if k != GROUND}
    touch = collections.defaultdict(set)
    for (cx, cy), zs in by_cell.items():
        for dx, dy in ((0, 0), (0, 1), (1, -1), (1, 0), (1, 1)):
            for z2, k2 in by_cell.get((cx + dx, cy + dy), ()):
                for z1, k1 in zs:
                    if k1 != k2 and abs(z1 - z2) <= STEP:
                        touch[k1].add(k2)
                        touch[k2].add(k1)
    middle = {k: float(np.median(f[:, 2])) if len(f) else 0.0 for k, f in floor_of.items()}
    frontier = set(level)
    while frontier:
        nxt = set()
        for k in sorted(floor_of):
            near = [n for n in touch[k] if n in frontier] if k not in level else ()
            if near:
                level[k] = level[min(near, key=lambda n: (abs(middle[n] - middle[k]), n))]
                nxt.add(k)
        frontier = nxt
    return {k: level.get(k, 0) for k in floor_of}
