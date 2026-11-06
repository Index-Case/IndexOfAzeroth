# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import threading
import time
from collections import OrderedDict
from types import SimpleNamespace

import numpy as np
from scipy.sparse import csr_matrix, coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

import nav
import navstore
import wmonav
from serverlog import log_error, start_thread

STRIDE = 4
BLOCKS = 128 // STRIDE
RING = STRIDE
KEEP_GRAPHS = 1200
FLOOR_REACH = STRIDE * 1.5
FLOOR_Z = 2.5
WALK_SPEED = 7.0
SWIM_SPEED = 4.72


def tile_path(inst, col, row, rules=None):
    return os.path.join(nav.CACHE, nav.graph_name(f"{inst}_{col}_{row}", rules))


def bends(pts, keep):
    n = len(pts)
    if n <= 2:
        return pts
    kept = np.zeros(n, bool)
    kept[0] = kept[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, d, mid = pts[i], pts[j] - pts[i], pts[i + 1:j]
        len2 = float(d @ d)
        t = np.clip(((mid - a) @ d) / len2, 0.0, 1.0) if len2 > 0 else np.zeros(len(mid))
        off = np.hypot(*(a + t[:, None] * d - mid).T)
        k = int(np.argmax(off))
        if off[k] > keep:
            kept[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[kept]


def height_off(h, z):
    if isinstance(z, (tuple, list)):
        return np.maximum(np.maximum(np.subtract(z[0], h), np.subtract(h, z[1])), 0.0)
    return np.abs(np.subtract(h, z))


def floors_path(key, rules=None):
    return os.path.join(nav.CACHE, nav.floors_name(key, rules))


def tile_inputs(inst, col, row, got, rules=None):
    rules = rules or nav.rules_in_force()
    out = [nav.NPC_TRAILS]
    for tr in (row - 1, row, row + 1):
        for tc in (col - 1, col, col + 1):
            out += [nav.tile_path(inst, tc, tr, rules), nav.road_path(inst, tc, tr, rules)]
    for p in (got or {}).get("bigs", ()):
        out.append(os.path.join(nav.CACHE, nav.joins_name(nav.place_key(inst, p), rules)))
    for gn, gw in nav.lattice_areas(*ring_box(col, row)):
        out.append(os.path.join(nav.CACHE, nav.joins_name(nav.props_key(inst, gn, gw), rules)))
    return out


def ring_box(col, row):
    return row * 128 - RING, col * 128 - RING, row * 128 + 128 + RING, col * 128 + 128 + RING



def labels(g):
    h, w = g["ground"].shape
    masks = nav.move_masks(g, nav.CELL)
    _, _, blocked = nav.blocked_cells(g)
    big = h * w
    lab = np.where(blocked, big, np.arange(big, dtype=np.int64).reshape(h, w))
    by = nav.walks(masks)
    rows, cols = np.arange(h), np.arange(w)
    both = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        rs, cs, ok = by[(dr, dc)]
        back = by[(-dr, -dc)][2]
        _, _, rt, ct = nav.shifted(h, w, dr, dc)
        same = ((rows[rs] // STRIDE) == ((rows[rs] + dr) // STRIDE))[:, None] & \
            ((cols[cs] // STRIDE) == ((cols[cs] + dc) // STRIDE))[None, :]
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
    bw = w // STRIDE
    block = (rows[:, None] // STRIDE) * bw + cols[None, :] // STRIDE
    walk = lab < big
    pairs = np.unique(np.stack([block[walk], lab[walk]], 1), axis=0)
    piece = np.full((h, w), -1, np.int64)
    if len(pairs):
        key = block[walk] * big + lab[walk]
        piece[walk] = np.searchsorted(pairs[:, 0] * big + pairs[:, 1], key)
    start = np.searchsorted(pairs[:, 0], pairs[:, 0], "left") if len(pairs) else np.zeros(0, np.int64)
    rank = np.arange(len(pairs)) - start
    return piece, len(pairs), (pairs[:, 0] if len(pairs) else np.zeros(0, np.int64)), rank, masks


def area_blocks(area):
    blocks = area.reshape(BLOCKS, STRIDE, BLOCKS, STRIDE).transpose(0, 2, 1, 3).reshape(BLOCKS * BLOCKS, -1)
    out = np.zeros(BLOCKS * BLOCKS, np.uint32)
    for k, cells in enumerate(blocks):
        vals, counts = np.unique(cells, return_counts=True)
        out[k] = vals[np.argmax(counts)]
    return out.reshape(BLOCKS, BLOCKS)


COARSE_KEYS = ("ground", "spread", "tilt", "water", "hazard", "holes", "ocean", "building", "trail", "walls", "floored", "road")


def build_tile(paths, inst, col, row):
    terrain = paths.terrain
    r0, c0, r1, c1 = ring_box(col, row)
    tiles = terrain.tiles_for(inst, r0, c0, r1, c1)
    if tiles.get((col, row)) is None:
        return {"none": np.array(True)}
    roads = terrain.roads_for(inst, r0, c0, r1, c1)
    g = terrain.region(inst, r0, c0, r1, c1, tiles, roads)
    g["road"] = g["road"] >= nav.ROAD_SHARE * 255
    h, w = g["ground"].shape
    cells, heights = terrain.npc_trails(inst)
    rr, cc = np.divmod(cells, 8192)
    sel = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
    rr, cc, zz = rr[sel] - r0, cc[sel] - c0, heights[sel]
    trail = np.zeros((h, w), bool)
    on = np.abs(g["ground"][rr, cc] - zz) <= nav.NPC_TRAIL_Z
    trail[rr[on], cc[on]] = True
    g["trail"] = trail
    g["walls"], g["floored"] = np.zeros((h, w), bool), np.zeros((h, w), bool)
    sources = set(terrain.sources_under(inst, r0, c0, r1, c1))
    placed, bigs = [], []
    for place in terrain.places_in(inst, r0, c0, r1, c1, small=False, tiles=tiles):
        b = navstore.load_npz(os.path.join(nav.CACHE, nav.joins_name(nav.place_key(inst, place))))
        if b is None or "blocks" not in b or "floored" not in b:
            try:
                b = paths.buildings.get(inst, place)
            except nav.NothingToWalk:
                continue
        bigs.append(nav.full_place(place))
        for key, got in (("walls", b["blocks"]), ("floored", b["floored"])):
            br, bc = np.divmod(got, 8192)
            inside = (br >= r0) & (br < r1) & (bc >= c0) & (bc < c1)
            g[key][br[inside] - r0, bc[inside] - c0] = True
        placed.append(np.asarray(place, np.float64)[:6])
    walls = paths.buildings.walls(inst, r0, c0, r1, c1) if terrain.client_files else nav.NO_WALLS
    g["barred"] = nav.barred_grid(walls.barred, r0, c0, (h, w))
    g["jumped"] = nav.barred_grid(walls.jumped, r0, c0, (h, w))
    dungeon = terrain.client_files and terrain.is_dungeon(inst)
    g["max_up"] = nav.DUNGEON_MAX_UP if dungeon else nav.MAX_UP
    g["cliff_jump"] = nav.DUNGEON_CLIFF_JUMP if dungeon else nav.CLIFF_JUMP
    piece, count, block, rank, masks = labels(g)
    if not count:
        return {"none": np.array(True)}
    bw = w // STRIDE
    ring_b = RING // STRIDE
    br_, bc_ = np.divmod(block, bw)
    inner = (br_ >= ring_b) & (br_ < ring_b + BLOCKS) & (bc_ >= ring_b) & (bc_ < ring_b + BLOCKS)
    local = np.full(count, -1, np.int64)
    local[inner] = np.arange(int(inner.sum()))
    walk = piece >= 0
    ri, ci = np.nonzero(walk)
    pid = piece[walk]
    many = np.maximum(np.bincount(pid, minlength=count), 1)
    centre = np.stack([np.bincount(pid, weights=ri, minlength=count) / many + r0,
                       np.bincount(pid, weights=ci, minlength=count) / many + c0], 1)
    d2 = (ri + r0 - centre[pid, 0]) ** 2 + (ci + c0 - centre[pid, 1]) ** 2
    order = np.lexsort((d2, pid))
    first = order[np.r_[True, pid[order][1:] != pid[order][:-1]]] if len(order) else order
    spot = np.zeros((count, 2), np.int64)
    spot[pid[first]] = np.stack([ri[first] + r0, ci[first] + c0], 1)
    walks, drops = [], []
    for dr, dc, rs, cs, ok, _, drop in masks:
        _, _, rt, ct = nav.shifted(h, w, dr, dc)
        a, b = piece[rs, cs], piece[rt, ct]
        m = ok & (a >= 0) & (b >= 0) & (a != b)
        m &= inner[np.maximum(a, 0)]
        if m.any():
            k = a[m] * count + b[m]
            walks.append(np.unique(k[~drop[m]]))
            drops.append(np.unique(k[drop[m]]))
    walk_keys = np.unique(np.concatenate(walks)) if walks else np.zeros(0, np.int64)
    drop_keys = np.unique(np.concatenate(drops)) if drops else np.zeros(0, np.int64)
    keys = np.union1d(walk_keys, drop_keys)
    fall = np.isin(keys, drop_keys) & ~np.isin(keys, walk_keys)
    pa, pb = keys // count, keys % count
    yards = (np.maximum(np.hypot(*(centre[pa] - centre[pb]).T), 0.5) * nav.CELL).astype(np.float32)
    own = inner[pb]
    nbr, nbc = br_[pb[~own]] - ring_b, bc_[pb[~own]] - ring_b
    side_r, side_c = np.where(nbr < 0, -1, np.where(nbr >= BLOCKS, 1, 0)), np.where(nbc < 0, -1, np.where(nbc >= BLOCKS, 1, 0))
    fine = {k: g[k][RING:-RING, RING:-RING] for k in COARSE_KEYS}
    coarse = nav.downsample(fine, STRIDE)
    out = {"piece_of": np.where(walk[RING:-RING, RING:-RING], local[np.maximum(piece[RING:-RING, RING:-RING], 0)], -1).astype(np.int32),
           "centre": centre[inner].astype(np.float32), "spot": spot[inner].astype(np.int32),
           "block": (((br_ - ring_b) * BLOCKS + bc_ - ring_b)[inner]).astype(np.int16),
           "edges": np.stack([local[pa[own]], local[pb[own]]], 1).astype(np.int32), "edge_yards": yards[own],
           "edge_fall": fall[own],
           "across": np.stack([local[pa[~own]], (side_r + 1) * 3 + side_c + 1, (nbr % BLOCKS) * BLOCKS + nbc % BLOCKS,
                               rank[pb[~own]]], 1).astype(np.int32),
           "across_yards": yards[~own], "across_fall": fall[~own],
           "area": area_blocks(g["area"][RING:-RING, RING:-RING]), "bigs": np.array(bigs, np.float64).reshape(-1, nav.PLACE_COLUMNS),
           "sources": np.array(sorted(sources)), "placed": nav.placed_digest(*placed) if placed else nav.NOWHERE}
    for k in COARSE_KEYS:
        if k in coarse:
            out["c_" + k] = coarse[k].astype(np.float32 if coarse[k].dtype.kind == "f" else bool)
    return out


def build_floors(paths, inst, place):
    b = paths.buildings.get(inst, place)
    L, G = b["layers"], b["graph"]
    nodes = L.nodes
    if not len(nodes):
        return {"none": np.array(True)}
    z = L.heights[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
    bw = -(-L.w // STRIDE)
    bid = (nodes[:, 0] // STRIDE) * bw + nodes[:, 1] // STRIDE
    coo = G.tocoo()
    same = bid[coo.row] == bid[coo.col]
    n = len(nodes)
    inside = coo_matrix((np.ones(int(same.sum()), bool), (coo.row[same], coo.col[same])), shape=(n, n)).tocsr()
    both = inside.multiply(inside.T)
    count, lab = connected_components(both, directed=False)
    north, west = L.world(nodes[:, 0], nodes[:, 1])
    many = np.maximum(np.bincount(lab, minlength=count), 1)
    centre = np.stack([np.bincount(lab, weights=north, minlength=count) / many, np.bincount(lab, weights=west, minlength=count) / many,
                       np.bincount(lab, weights=z, minlength=count) / many], 1)
    d2 = (north - centre[lab, 0]) ** 2 + (west - centre[lab, 1]) ** 2 + (z - centre[lab, 2]) ** 2
    order = np.lexsort((d2, lab))
    first = order[np.r_[True, lab[order][1:] != lab[order][:-1]]]
    spot = np.zeros((count, 3), np.float64)
    spot[lab[first]] = np.stack([north[first], west[first], z[first]], 1)
    other = lab[coo.row] != lab[coo.col]
    pa, pb, data = lab[coo.row[other]], lab[coo.col[other]], coo.data[other]
    step = np.hypot(np.hypot(north[coo.row[other]] - north[coo.col[other]], west[coo.row[other]] - west[coo.col[other]]),
                    z[coo.row[other]] - z[coo.col[other]])
    drop = data >= wmonav.DROP_COST
    unit = np.where(drop, np.inf, data / np.maximum(step, 0.5))
    key = pa.astype(np.int64) * count + pb
    keys, inv = np.unique(key, return_inverse=True)
    best = np.full(len(keys), np.inf)
    np.minimum.at(best, inv, unit)
    fall = ~np.isfinite(best)
    ea, eb = keys // count, keys % count
    yards = np.maximum(np.hypot(np.hypot(*(centre[ea, :2] - centre[eb, :2]).T), centre[ea, 2] - centre[eb, 2]), 0.5)
    jn, jc = b["joins"][:, 0], b["joins"][:, 1]
    jr, jcc = np.divmod(jc, 8192)
    rim = np.flatnonzero(np.diff(G.tocsr().indptr) < 8)
    out = {"centre": centre.astype(np.float32), "spot": spot.astype(np.float32), "piece_of_node": lab.astype(np.int32),
           "edges": np.stack([ea, eb], 1).astype(np.int32),
           "edge_yards": yards.astype(np.float32), "edge_unit": np.where(fall, 1.0, best).astype(np.float32), "edge_fall": fall,
           "rim_at": np.stack([lab[rim], np.round(north[rim]), np.round(west[rim])], 1).astype(np.int32),
           "rim_z": z[rim].astype(np.float32)}
    if len(jn):
        g = paths.terrain.region(inst, int(jr.min()), int(jcc.min()), int(jr.max()) + 1, int(jcc.max()) + 1)
        ground = g["ground"][jr - jr.min(), jcc - jcc.min()]
        rise = z[jn] - ground
        tn, tw = nav.world_of(jr, jcc)
        jyards = np.maximum(np.hypot(north[jn] - tn, west[jn] - tw), nav.CELL / 2) + (np.abs(rise) > nav.JOIN_UP) * wmonav.DROP_COST
        up, down = nav.join_steps(rise, b["onto"])
        ok = np.isfinite(rise) & (up | down)
        out.update(joins=np.stack([lab[jn[ok]], jc[ok]], 1).astype(np.int64), join_yards=jyards[ok].astype(np.float32),
                   join_up=up[ok], join_down=down[ok])
    else:
        out.update(joins=np.zeros((0, 2), np.int64), join_yards=np.zeros(0, np.float32), join_up=np.zeros(0, bool),
                   join_down=np.zeros(0, bool))
    return out


def meets(floors):
    rims = [(off, f["rim_at"], f["rim_z"]) for off, f in floors if "rim_at" in f and len(f["rim_at"])]
    boxes = [(r[:, 1].min(), r[:, 1].max(), r[:, 2].min(), r[:, 2].max()) for _, r, _ in rims]
    out_a, out_b = [], []
    for i in range(len(rims)):
        for j in range(i + 1, len(rims)):
            (n0, n1, w0, w1), (m0, m1, v0, v1) = boxes[i], boxes[j]
            if n0 > m1 + 1 or m0 > n1 + 1 or w0 > v1 + 1 or v0 > w1 + 1:
                continue
            (oa, ra, za), (ob, rb, zb) = rims[i], rims[j]
            keys_a = ra[:, 1].astype(np.int64) * 100003 + ra[:, 2]
            order = np.argsort(keys_a, kind="stable")
            sorted_a, keys_b = keys_a[order], rb[:, 1].astype(np.int64) * 100003 + rb[:, 2]
            for dn in (-1, 0, 1):
                for dw in (-1, 0, 1):
                    want = keys_b + dn * 100003 + dw
                    lo = np.searchsorted(sorted_a, want, "left")
                    many = np.searchsorted(sorted_a, want, "right") - lo
                    kb = np.repeat(np.arange(len(want)), many)
                    ka = order[np.repeat(lo, many) + np.arange(len(kb)) - np.repeat(np.cumsum(many) - many, many)]
                    near = np.abs(za[ka] - zb[kb]) <= nav.STEP_JOIN
                    if near.any():
                        pairs = np.unique(np.stack([ra[ka[near], 0] + oa, rb[kb[near], 0] + ob], 1), axis=0)
                        out_a.append(pairs[:, 0])
                        out_b.append(pairs[:, 1])
    if not out_a:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    pairs = np.unique(np.stack([np.concatenate(out_a), np.concatenate(out_b)], 1), axis=0)
    return pairs[:, 0].astype(np.int64), pairs[:, 1].astype(np.int64)



class Store:

    def __init__(self, paths):
        self.paths = paths
        self.lock = threading.Lock()
        self.kept = OrderedDict()
        self.checked = {}

    def get(self, key, path, build, inputs):
        now = nav.store_stamp()
        with self.lock:
            if key in self.kept and (not self.paths.terrain.client_files
                                     or nav.kept_fresh(self.checked, key, now, lambda: navstore.stamp(path))):
                self.kept.move_to_end(key)
                return self.kept[key]
        stand_in = not self.paths.terrain.client_files
        stamp = None if stand_in else navstore.stamp(path)
        got = None if stand_in else navstore.load_npz(path)
        if got is None and nav.wm.serving() and not stand_in:
            raise nav.NotBuilt(("graph", os.path.basename(path)))
        if got is not None and not nav.wm.serving() and self.older(path, inputs(got)):
            got = None
        if got is None:
            got = build()
            if not stand_in:
                os.makedirs(nav.CACHE, exist_ok=True)
                nav.arrays.save_npz(path, **got)
                stamp = navstore.stamp(path)
        got = None if "none" in got else got
        with self.lock:
            self.kept[key] = got
            self.checked[key] = (stamp, now)
            while len(self.kept) > KEEP_GRAPHS:
                self.checked.pop(self.kept.popitem(last=False)[0], None)
        return got

    @staticmethod
    def older(path, inputs):
        return not nav.as_new(nav.made_at(path), [nav.made_at(i) for i in inputs])

    def tile(self, inst, col, row):
        return self.get(("tile", inst, col, row), tile_path(inst, col, row), lambda: build_tile(self.paths, inst, col, row),
                        lambda got: tile_inputs(inst, col, row, got))

    def floors(self, inst, place):
        key = nav.place_key(inst, place)
        files = [os.path.join(nav.CACHE, nav.layers_name(key)), os.path.join(nav.CACHE, nav.joins_name(key))]
        return self.get(("floors", key), floors_path(key),
                        lambda: build_floors(self.paths, inst, place), lambda got: files)



class Region:

    def __init__(self, store, inst, tc0, tr0, tc1, tr1):
        self.inst, self.tc0, self.tr0, self.tc1, self.tr1 = inst, tc0, tr0, tc1, tr1
        paths = store.paths
        self.terrain = paths.terrain
        nr, nc = tr1 - tr0 + 1, tc1 - tc0 + 1
        self.r0, self.c0 = tr0 * 128, tc0 * 128
        self._dungeon = bool(paths.terrain.client_files and paths.terrain.is_dungeon(inst))
        self.tiles, self.offset, n = {}, {}, 0
        for tr in range(tr0, tr1 + 1):
            for tc in range(tc0, tc1 + 1):
                if not paths.terrain.on_map(inst, tc, tr):
                    continue
                t = store.tile(inst, tc, tr)
                if t is None:
                    continue
                self.tiles[(tc, tr)] = t
                self.offset[(tc, tr)] = n
                n += len(t["centre"])
        self.terrain_nodes = n
        self.g = g = {"ground": np.full((nr * BLOCKS, nc * BLOCKS), np.nan, np.float32)}
        for k in COARSE_KEYS[1:]:
            g[k] = np.full((nr * BLOCKS, nc * BLOCKS), np.nan, np.float32) if k == "water" else \
                np.zeros((nr * BLOCKS, nc * BLOCKS), np.float32 if k in ("spread", "tilt") else bool)
        g["area"] = np.zeros((nr * BLOCKS, nc * BLOCKS), np.uint32)
        blk, cen, spot, ea, eb, ey, ef = [], [], [], [], [], [], []
        for (tc, tr), t in self.tiles.items():
            br, bc = (tr - tr0) * BLOCKS, (tc - tc0) * BLOCKS
            for k in COARSE_KEYS:
                if "c_" + k in t:
                    g[k][br:br + BLOCKS, bc:bc + BLOCKS] = t["c_" + k]
            g["area"][br:br + BLOCKS, bc:bc + BLOCKS] = t["area"]
            b = t["block"].astype(np.int64)
            blk.append((br + b // BLOCKS) * (nc * BLOCKS) + bc + b % BLOCKS)
            cen.append(t["centre"])
            spot.append(t["spot"])
            off = self.offset[(tc, tr)]
            ea.append(t["edges"][:, 0] + off); eb.append(t["edges"][:, 1] + off)
            ey.append(t["edge_yards"]); ef.append(t["edge_fall"])
            across = t["across"]
            for d in np.unique(across[:, 1]) if len(across) else ():
                sr, sc = int(d) // 3 - 1, int(d) % 3 - 1
                other = self.tiles.get((tc + sc, tr + sr))
                if other is None:
                    continue
                m = across[:, 1] == d
                nb, nk = across[m, 2], across[m, 3]
                at = np.searchsorted(other["block"], nb) + nk
                ok = (at < len(other["block"]))
                ok[ok] &= other["block"][at[ok]] == nb[ok]
                ea.append(across[m, 0][ok] + off); eb.append(at[ok] + self.offset[(tc + sc, tr + sr)])
                ey.append(t["across_yards"][m][ok]); ef.append(t["across_fall"][m][ok])
        cat = lambda a, dtype: np.concatenate(a).astype(dtype) if a else np.zeros(0, dtype)
        self.block = cat(blk, np.int64)
        self.centre = cat(cen, np.float64).reshape(-1, 2)
        self.spot = cat(spot, np.int64).reshape(-1, 2)
        self.t_edges = (cat(ea, np.int64), cat(eb, np.int64), cat(ey, np.float64), cat(ef, bool))
        self.floors, fa, fb, fy, fu, ff, ja, jb, jy = [], [], [], [], [], [], [], [], []
        self.floor_at = {}
        fcen = []
        bigs = {}
        for t in self.tiles.values():
            for p in t.get("bigs", np.zeros((0, nav.PLACE_COLUMNS))):
                if len(p) > len(bigs.get(int(p[1]), ())):
                    bigs[int(p[1])] = p
        for place in bigs.values():
            try:
                f = store.floors(inst, place)
            except nav.NothingToWalk:
                continue
            if f is None:
                continue
            off = n
            n += len(f["centre"])
            self.floors.append((off, f))
            self.floor_at[int(place[1])] = (off, f)
            fcen.append(f["centre"])
            fa.append(f["edges"][:, 0] + off); fb.append(f["edges"][:, 1] + off)
            fy.append(f["edge_yards"]); fu.append(f["edge_unit"]); ff.append(f["edge_fall"])
            if len(f["joins"]):
                node = self.node_of_cells(f["joins"][:, 1])
                ok = node >= 0
                up, down = f["join_up"] & ok, f["join_down"] & ok
                ja += [node[up], f["joins"][down, 0] + off]
                jb += [f["joins"][up, 0] + off, node[down]]
                jy += [f["join_yards"][up], f["join_yards"][down]]
        self.f_edges = (cat(fa, np.int64), cat(fb, np.int64), cat(fy, np.float64), cat(fu, np.float64), cat(ff, bool))
        ma, mb = meets(self.floors)
        ja += [ma, mb]
        jb += [mb, ma]
        jy += [np.full(len(ma), 1.5), np.full(len(mb), 1.5)]
        self.joins = (cat(ja, np.int64), cat(jb, np.int64), cat(jy, np.float64))
        self.floor_centre = cat(fcen, np.float64).reshape(-1, 3)
        self.n = n
        self.movers = self.rides(paths)

    def node_of_cells(self, cells):
        cells = np.asarray(cells, np.int64).reshape(-1)
        r, c = np.divmod(cells, 8192)
        out = np.full(len(cells), -1, np.int64)
        tile = (r // 128) * 64 + c // 128
        for k in np.unique(tile).tolist():
            tr, tc = divmod(k, 64)
            t = self.tiles.get((tc, tr))
            if t is None:
                continue
            m = tile == k
            p = t["piece_of"][r[m] - tr * 128, c[m] - tc * 128].astype(np.int64)
            out[m] = np.where(p >= 0, p + self.offset[(tc, tr)], -1)
        return out

    def ground_node(self, point, reach=3):
        r, c = nav.cell_of(*point)
        got = int(self.node_of_cells([r * 8192 + c])[0]) if nav.on_grid(r, c) else -1
        if got >= 0:
            return got
        span = np.arange(-reach * STRIDE, reach * STRIDE + 1)
        dr, dc = (d.ravel() for d in np.meshgrid(span, span, indexing="ij"))
        on = nav.on_grid(r + dr, c + dc)
        dr, dc = dr[on], dc[on]
        nodes = self.node_of_cells((r + dr) * 8192 + c + dc)
        ok = nodes >= 0
        if not ok.any():
            return -1
        d = np.hypot(dr, dc)
        return int(nodes[ok][np.argmin(d[ok])])

    def ground_height(self, point):
        r, c = nav.cell_of(*point)
        t = self.terrain.tile(self.inst, c // 128, r // 128) if nav.on_grid(r, c) else None
        return float(t["ground"][r % 128, c % 128]) if t is not None else math.nan

    def floor_tree(self):
        if getattr(self, "_floor_tree", None) is None:
            from scipy.spatial import cKDTree
            self._floor_tree = cKDTree(self.floor_centre[:, :2])
        return self._floor_tree

    def nodes_at(self, point, z=None, reach=3):
        ground = self.ground_node(point, reach)
        out = [ground] if ground >= 0 else []
        beside = self.beside(point, z) if ground >= 0 and self.pocket(ground) else []
        floors = []
        if len(self.floor_centre):
            near = np.asarray(self.floor_tree().query_ball_point(point[:2], FLOOR_REACH), np.int64)
            fc = self.floor_centre[near]
            d = np.hypot(fc[:, 0] - point[0], fc[:, 1] - point[1])
            if z is None:
                return out + [int(k) + self.terrain_nodes for k in near[np.lexsort((near, d))]] + beside
            off = height_off(fc[:, 2], z)
            floors = [(float(o), float(e), int(k) + self.terrain_nodes) for o, e, k in zip(off, d, near) if o <= FLOOR_Z]
        if z is None:
            return out + beside
        gh = self.ground_height(point)
        on = [(float(height_off(gh, z)), 0.0, ground)] if ground >= 0 and nav.ground_stands(gh, z, not floors) else []
        return [k for *_, k in sorted(floors + on)] + beside

    def weak(self):
        got = getattr(self, "_weak", None)
        if got is None:
            a = np.concatenate([self.t_edges[0], self.f_edges[0], self.joins[0]])
            b = np.concatenate([self.t_edges[1], self.f_edges[1], self.joins[1]])
            graph = coo_matrix((np.ones(len(a), np.int8), (a, b)), shape=(self.n, self.n)).tocsr()
            lab = connected_components(graph, directed=True, connection="weak")[1]
            got = self._weak = (lab, np.bincount(lab, minlength=1))
        return got

    def pocket(self, node):
        lab, size = self.weak()
        return bool(size[lab[node]] < PLACE_PIECES)

    def beside(self, point, z=None):
        r, c = nav.cell_of(*point[:2])
        k = int(math.ceil(nav.TALK_REACH / nav.CELL))
        dr, dc = (d.ravel() for d in np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1), indexing="ij"))
        rr, cc = r + dr, c + dc
        on = nav.on_grid(rr, cc)
        rr, cc = rr[on], cc[on]
        north, west = nav.world_of(rr, cc)
        z = self.ground_height(point) if z is None else z
        up = np.zeros(len(rr))
        if isinstance(z, (tuple, list)) or np.isfinite(z):
            heights = np.array([self.ground_height((n, w)) for n, w in zip(north.tolist(), west.tolist())])
            up = np.nan_to_num(height_off(heights, z), nan=np.inf)
        near = np.hypot(np.hypot(north - point[0], west - point[1]), up)
        nodes = self.node_of_cells(rr * 8192 + cc)
        out = []
        for i in np.argsort(near, kind="stable").tolist():
            node = int(nodes[i])
            if near[i] <= nav.TALK_REACH and node >= 0 and node not in out and not self.pocket(node):
                out.append(node)
        return out

    def node_at(self, point, z=None, reach=3):
        got = self.nodes_at(point, z, reach)
        return got[0] if got else -1

    def rides(self, paths):
        out = []
        for m in paths.movers():
            if m["map"] != self.inst:
                continue
            ends = [self.node_at(p[:2], p[2]) for p in nav.mover_ends(m)]
            if -1 not in ends and ends[0] != ends[1]:
                cost = m["seconds"] * 7.0 + 10.0
                out.append((ends[0], ends[1], cost, m.get("side")))
                if not m.get("oneWay"):
                    out.append((ends[1], ends[0], cost, m.get("side")))
        return out

    def floor_cities(self, capitals):
        kept = getattr(self, "_cities", None)
        if kept is not None and kept[0] is capitals:
            return kept[1]
        fc = self.floor_centre
        r, c = ((nav.CORNER - fc[:, 0]) // nav.CELL).astype(np.int64), ((nav.CORNER - fc[:, 1]) // nav.CELL).astype(np.int64)
        br, bc = (r - self.r0) // STRIDE, (c - self.c0) // STRIDE
        h, w = self.g["ground"].shape
        on = (br >= 0) & (br < h) & (bc >= 0) & (bc < w)
        area, ground = np.zeros(len(fc), np.int64), np.full(len(fc), np.nan)
        area[on], ground[on] = self.g["area"][br[on], bc[on]], self.g["ground"][br[on], bc[on]]
        got = capitals.at(self.inst, fc[:, 0], fc[:, 1], fc[:, 2], ground, area)
        self._cities = (capitals, got)
        return got

    def world(self, nodes):
        nodes = np.asarray(nodes, np.int64)
        out = np.full((len(nodes), 3), np.nan)
        land = nodes < self.terrain_nodes
        r, c = self.spot[nodes[land], 0], self.spot[nodes[land], 1]
        n, w = nav.world_of(r, c)
        out[land, 0], out[land, 1] = n, w
        if self.floors and not land.all():
            starts = np.array([off for off, _ in self.floors], np.int64)
            which = np.searchsorted(starts, nodes, side="right") - 1
            for k in np.unique(which[~land]).tolist():
                off, f = self.floors[k]
                m = ~land & (which == k)
                out[m] = f["spot"][nodes[m] - off]
        return out

    def priced(self, paths, profile):
        g = {k: v for k, v in self.g.items()}
        g["trail"] = g["trail"] | profile.walked_blocks(paths, self)
        g["ghost"], g["trail_cost"], g["path_cost"] = profile.ghost, profile.trail_cost, profile.path_cost
        g["danger_cost"], g["max_up"] = profile.danger_cost, self.max_up
        h, w = g["ground"].shape
        shim = type("Shim", (), {})()
        shim.avoid, shim.g, shim.h, shim.w, shim.stride = profile.rows, g, h, w, STRIDE
        shim.r0, shim.c0, shim.roads, shim.seek, shim.gather = self.r0, self.c0, profile.roads, profile.seek, profile.gather
        nav.Search.mobs(shim)
        if profile.level and not profile.ghost and not self.dungeon:
            paths.mark_over(g, profile.level, profile.block_of(self, profile.start), profile.block_of(self, profile.goal),
                            exempt=profile.exempt)
        costly = frozenset() if self.dungeon else paths.costly(profile.walker)
        if costly:
            paths.mark_capitals(g, costly)
        pop = paths.populated_of(self.inst) if paths.populated_of and not self.dungeon else None
        if pop is not None and not profile.gather:
            top, left, cell, grid = pop
            north = nav.CORNER - (self.r0 + (np.arange(h) + 0.5) * STRIDE) * nav.CELL
            west = nav.CORNER - (self.c0 + (np.arange(w) + 0.5) * STRIDE) * nav.CELL
            gi, gj = ((top - north) // cell).astype(int), ((left - west) // cell).astype(int)
            oki, okj = (gi >= 0) & (gi < grid.shape[0]), (gj >= 0) & (gj < grid.shape[1])
            near = grid[np.clip(gi, 0, grid.shape[0] - 1)][:, np.clip(gj, 0, grid.shape[1] - 1)]
            g["wild"] = ~(near & oki[:, None] & okj[None, :])
        weight = nav.cell_weights(g, nav.CELL * STRIDE).ravel()
        a, b, yards, fall = self.t_edges
        cost = [yards * (weight[self.block[a]] + weight[self.block[b]]) / 2 + fall * wmonav.DROP_COST]
        rows, cols = [a], [b]
        fa, fb, fy, fu, ff = self.f_edges
        if len(fa):
            hot = self.floor_danger(profile.rows)
            k = fa - self.terrain_nodes, fb - self.terrain_nodes
            danger = 1 + profile.danger_cost * np.minimum((hot[k[0]] + hot[k[1]]) / 2, nav.DANGER_CAP) if hot is not None else 1.0
            if costly:
                far = np.isin(self.floor_cities(paths.capitals), list(costly)).astype(np.float64)
                danger = danger * (1 + (nav.CAPITAL_COST - 1) * (far[k[0]] + far[k[1]]) / 2)
            cost.append(fy * fu * danger + ff * wmonav.DROP_COST)
            rows.append(fa); cols.append(fb)
        ja, jb, jy = self.joins
        rows.append(ja); cols.append(jb); cost.append(jy)
        movers = [m[:3] for m in self.movers if nav.rideable(m[3], profile.walker)]
        if movers:
            mv = np.array(movers, np.float64)
            rows.append(mv[:, 0].astype(np.int64)); cols.append(mv[:, 1].astype(np.int64)); cost.append(mv[:, 2])
        graph = csr_matrix((np.concatenate(cost), (np.concatenate(rows), np.concatenate(cols))), shape=(self.n, self.n))
        swim = nav.on_water(g).ravel()
        over = g["over"].ravel() if "over" in g else np.zeros(h * w, bool)
        zone = g["zone"].ravel() if "zone" in g else np.zeros(h * w, np.int64)
        return graph, weight, swim, over, zone

    @property
    def dungeon(self):
        return getattr(self, "_dungeon", False)

    @property
    def max_up(self):
        return nav.DUNGEON_MAX_UP if self.dungeon else nav.MAX_UP

    def floor_danger(self, rows):
        if rows is None or not len(rows) or rows.shape[1] < 5 or not len(self.floor_centre):
            return None
        rows = rows[(rows[:, 3] > 0) & np.isfinite(rows[:, 4])]
        if not len(rows):
            return None
        fc = self.floor_centre
        rows = rows[(rows[:, 0] + rows[:, 2] >= fc[:, 0].min()) & (rows[:, 0] - rows[:, 2] <= fc[:, 0].max())
                    & (rows[:, 1] + rows[:, 2] >= fc[:, 1].min()) & (rows[:, 1] - rows[:, 2] <= fc[:, 1].max())]
        if not len(rows):
            return None
        hot = np.zeros(len(fc), np.float32)
        for (n, w, r, weight, mz), near in zip(rows[:, :5], self.floor_tree().query_ball_point(rows[:, :2], rows[:, 2])):
            if near:
                near = np.asarray(near)
                hot[near[np.abs(fc[near, 2] - mz) <= nav.FLOOR_MOB_Z]] += weight
        return hot if hot.any() else None


class Profile:

    def __init__(self, rows=None, mode="", level=None, ghost=False, start=None, goal=None, walker=None):
        self.rows = rows
        self.roads, self.seek, self.gather = mode == "roads", mode == "seek", mode == "gather"
        self.ghost, self.level, self.start, self.goal, self.walker = ghost, level, start, goal, walker
        self.exempt = None
        self.trail_cost = 1.0 if self.gather else nav.SAFE_TRAIL_COST if self.roads else nav.TRAIL_COST
        self.path_cost = 1.0 if self.gather else nav.PATH_COST
        self.danger_cost = nav.SAFEST_COST if self.roads else nav.SAFE_COST

    @staticmethod
    def block_of(region, point):
        if point is None:
            return (-1, -1)
        r, c = nav.cell_of(*point[:2])
        return ((r - region.r0) // STRIDE, (c - region.c0) // STRIDE)

    def walked_blocks(self, paths, region):
        h, w = region.g["ground"].shape
        out = np.zeros((h, w), bool)
        walked = tuple(paths.terrain.trails.get(region.inst, ()))
        if walked:
            rr, cc = np.divmod(np.fromiter(walked, np.int64, len(walked)), 8192)
            br, bc = (rr - region.r0) // STRIDE, (cc - region.c0) // STRIDE
            ok = (br >= 0) & (br < h) & (bc >= 0) & (bc < w)
            out[br[ok], bc[ok]] = True
        return out

    def key(self, paths, inst):
        return (self.roads, self.seek, self.gather, self.ghost, self.level, paths.mobs_digest(self.rows),
                tuple(self.exempt or ()), self.walker) + paths.walk_stamp(inst)


REGION_MARGIN = 5
REGION_SHARE = 0.35
REGION_GROW = 3
END_MARGIN = 30
STRETCH = 1200.0
STRETCH_MARGIN = 24
BEND = STRETCH_MARGIN * nav.CELL * 0.7
JOIN_NEAR = 2 * STRIDE * nav.CELL
JOIN_SAVES = 40.0
KEEP_REGIONS = 3
KEEP_PRICES = 6
KEEP_COSTS = 16
KEEP_ANSWERS = 4096
PIECES_STALE = 3600.0
PLACE_PIECES = 100
LEG_REACH = 2.5
LEG_PAD = 200.0
LEG_BEND = 8.0


class Pieces:

    def __init__(self, store, inst):
        region = Region(store, inst, 0, 0, 63, 63)
        a, b, _, _ = region.t_edges
        fa, fb, *_ = region.f_edges
        ja, jb, _ = region.joins
        mv = np.array([m[:3] for m in region.movers], np.float64).reshape(-1, 3)
        rows = np.concatenate([a, fa, ja, mv[:, 0]]).astype(np.int64)
        cols = np.concatenate([b, fb, jb, mv[:, 1]]).astype(np.int64)
        graph = csr_matrix((np.ones(len(rows), np.int8), (rows, cols)), shape=(region.n, region.n))
        self.weak = connected_components(graph, directed=True, connection="weak")[1].astype(np.int32)
        self.strong = connected_components(graph, directed=True, connection="strong")[1].astype(np.int32)
        self.grounded = np.bincount(self.weak[:region.terrain_nodes], minlength=int(self.weak.max(initial=-1)) + 1) > 0
        self.grounded &= np.bincount(self.weak) >= PLACE_PIECES
        self.where = Region.__new__(Region)
        self.where.tiles = {k: {"piece_of": t["piece_of"].astype(np.int16 if len(t["centre"]) < 32767 else np.int32)}
                            for k, t in region.tiles.items()}
        self.where._weak = (self.weak, np.bincount(self.weak, minlength=1))
        self.where.offset, self.where.floor_centre = region.offset, region.floor_centre
        self.where.terrain_nodes, self.where.inst, self.where.terrain = region.terrain_nodes, inst, region.terrain
        if len(region.floor_centre):
            self.where.floor_tree()
        self.known = {}

    def labels(self, spot):
        key = tuple(spot)
        if key not in self.known:
            nodes = self.where.nodes_at(spot[:2], spot[2] if len(spot) > 2 else None)
            free = [k for k in nodes if self.grounded[self.weak[k]]]
            nodes = [k for k in nodes if k < self.where.terrain_nodes or k in free] if free else nodes
            ok = bool(nodes) and self.grounded[self.weak[nodes[0]]] and all(self.weak[k] == self.weak[nodes[0]] for k in nodes)
            node = nodes[0] if ok else None
            self.known[key] = (int(self.weak[node]), int(self.strong[node])) if ok else None
        return self.known[key]


class TravelGraph:

    def __init__(self, paths):
        self.paths = paths
        self.store = Store(paths)
        self.lock = threading.Lock()
        self.regions = OrderedDict()
        self.prices = OrderedDict()
        self.costs = OrderedDict()
        self.answers = OrderedDict()
        self.map_pieces = {}
        self.piecing = {}

    @staticmethod
    def region_key(inst, a, b, margin):
        ra, ca = nav.cell_of(*a[:2])
        rb, cb = nav.cell_of(*b[:2])
        tr0, tr1 = sorted((nav.grid_tile(ra), nav.grid_tile(rb)))
        tc0, tc1 = sorted((nav.grid_tile(ca), nav.grid_tile(cb)))
        m = max(margin, int(math.ceil(REGION_SHARE * max(tr1 - tr0, tc1 - tc0))))
        return (inst, max(0, tc0 - m), max(0, tr0 - m), min(63, tc1 + m), min(63, tr1 + m))

    def region(self, inst, a, b, margin):
        key = self.region_key(inst, a, b, margin)
        stamp = nav.store_stamp()
        with self.lock:
            got = self.regions.get(key)
            if got is not None and got[0] == stamp:
                self.regions.move_to_end(key)
                return (key, stamp), got[1]
        region = Region(self.store, *key)
        with self.lock:
            self.forget(key)
            self.regions[key] = (stamp, region)
            while len(self.regions) > KEEP_REGIONS:
                self.forget(self.regions.popitem(last=False)[0])
        return (key, stamp), region

    def forget(self, key):
        for k in [k for k in self.prices if k[0][0] == key]:
            self.prices.pop(k, None)
        for k in [k for k in self.costs if k[0][0][0] == key]:
            self.costs.pop(k, None)

    def priced(self, key, region, profile):
        pk = (key, profile.key(self.paths, region.inst))
        with self.lock:
            got = self.prices.get(pk)
            if got is not None:
                self.prices.move_to_end(pk)
                return pk, got
        got = region.priced(self.paths, profile)
        if profile.key(self.paths, region.inst) != pk[1]:
            return pk, got
        with self.lock:
            self.prices[pk] = got
            while len(self.prices) > KEEP_PRICES:
                self.prices.popitem(last=False)
        return pk, got

    def exempt(self, inst, *spots):
        lut = self.paths.zone_levels
        if lut is None:
            return ()
        out = []
        for p in spots:
            r, c = nav.cell_of(*p[:2])
            g = self.paths.terrain.region(inst, r, c, r + 1, c + 1)
            area = int(g["area"][0, 0])
            out.append(int(lut[0][min(area, len(lut[0]) - 1)]))
        return tuple(z for z in out if z)


    def walk_costs(self, inst, start, goals, rows=None, mode="", level=None, ghost=False, start_z=None, margin=1, walker=None):
        if not goals:
            return []
        lo = (max(p[0] for p in [start] + list(goals)), max(p[1] for p in [start] + list(goals)))
        hi = (min(p[0] for p in [start] + list(goals)), min(p[1] for p in [start] + list(goals)))
        profile = Profile(rows, mode, level, ghost, start, None, walker)
        profile.exempt = self.exempt(inst, start)
        stamp = nav.store_stamp()
        ask = ((self.region_key(inst, lo, hi, margin), stamp), profile.key(self.paths, inst), tuple(start), start_z,
               tuple(tuple(g) for g in goals), margin)
        with self.lock:
            got = self.answers.get(ask)
            if got is not None:
                self.answers.move_to_end(ask)
        if got is None:
            got = self.work_costs(inst, start, goals, rows, mode, level, ghost, start_z, margin, walker, lo, hi, profile)
            same = nav.store_stamp() == stamp and profile.key(self.paths, inst) == ask[1]
            with self.lock:
                if same:
                    self.answers[ask] = got
                    while len(self.answers) > KEEP_ANSWERS:
                        self.answers.popitem(last=False)
        return [dict(v) if v is not None else None for v in got]

    def work_costs(self, inst, start, goals, rows, mode, level, ghost, start_z, margin, walker, lo, hi, profile):
        key, region = self.region(inst, lo, hi, margin)
        pk, (graph, weight, swim, _, _) = self.priced(key, region, profile)
        out, srcs = [None] * len(goals), region.nodes_at(start[:2], start_z)
        if not srcs:
            return out
        first, pred = self.costs_from(pk, graph, tuple(srcs[:1]))
        self.costs_to(region, swim, start, goals, first, pred, out)
        if None in out and len(srcs) > 1:
            self.costs_to(region, swim, start, goals, *self.costs_from(pk, graph, tuple(srcs[1:])), out)
        missing = [k for k, v in enumerate(out) if v is None]
        if missing and margin < 3 and self.boxed(region, np.flatnonzero(np.isfinite(first))):
            wider = self.walk_costs(inst, start, [goals[k] for k in missing], rows, mode, level, ghost, start_z, margin * 3,
                                    walker)
            for k, v in zip(missing, wider):
                out[k] = v
        return out

    def costs_from(self, pk, graph, srcs):
        ck = (pk, srcs[0]) if len(srcs) == 1 else (pk, srcs)
        with self.lock:
            got = self.costs.get(ck)
            if got is not None:
                self.costs.move_to_end(ck)
        if got is None:
            got = dijkstra(graph, indices=srcs[0], return_predecessors=True) if len(srcs) == 1 else \
                dijkstra(graph, indices=list(srcs), return_predecessors=True, min_only=True)[:2]
            with self.lock:
                self.costs[ck] = got
                while len(self.costs) > KEEP_COSTS:
                    self.costs.popitem(last=False)
        return got

    @staticmethod
    def costs_to(region, swim, start, goals, dist, pred, out):
        for i, goal in enumerate(goals):
            if out[i] is not None:
                continue
            reached = [k for k in region.nodes_at(goal[:2], goal[2] if len(goal) > 2 else None) if np.isfinite(dist[k])]
            if not reached:
                continue
            node = min(reached, key=lambda k: dist[k])
            chain = [node]
            while pred[chain[-1]] >= 0:
                chain.append(int(pred[chain[-1]]))
            pts = region.world(chain[::-1])
            here = pts[0]
            steps = np.hypot(pts[1:, 0] - pts[:-1, 0], pts[1:, 1] - pts[:-1, 1])
            after = np.asarray(chain[::-1][1:], np.int64)
            land = after < region.terrain_nodes
            wet = np.zeros(len(steps), bool)
            wet[land] = swim[region.block[after[land]]]
            ends = math.hypot(here[0] - start[0], here[1] - start[1]) + math.hypot(pts[-1][0] - goal[0], pts[-1][1] - goal[1])
            if len(chain) == 1:
                ends = math.hypot(goal[0] - start[0], goal[1] - start[1])
            yards = float(steps.sum()) + ends
            swum = float(steps[wet].sum())
            out[i] = {"seconds": round((yards - swum) / WALK_SPEED + swum / SWIM_SPEED, 1), "yards": round(yards),
                      "cost": round(float(dist[node]) + ends, 1)}


    def leg_ways(self, inst, box, rows=None, mode="", level=None, walker=None, exempt=(), margin=1):
        key, region = self.region(inst, box[0], box[1], margin)
        profile = Profile(rows, mode, level, False, None, None, walker)
        profile.exempt = tuple(sorted(set(exempt)))
        _, (graph, _, _, _, _) = self.priced(key, region, profile)
        _, piece = connected_components(graph, directed=True, connection="weak")
        nodes = {}

        def at(p):
            p = (float(p[0]), float(p[1]))
            if p not in nodes:
                nodes[p] = region.nodes_at(p)
            return nodes[p]

        def ways(legs, also=()):
            out, extra, froms = [None] * len(legs), {}, {}
            for k, (a, _) in enumerate(legs):
                froms.setdefault((float(a[0]), float(a[1])), []).append(k)
            for a, ks in froms.items():
                srcs = at(a)
                if not srcs:
                    continue
                joined = lambda p: [g for g in at(p) if piece[g] == piece[srcs[0]]]
                goals = {k: joined(legs[k][1]) for k in ks}
                ks = [k for k in ks if goals[k]]
                if not ks:
                    continue
                far = max(math.hypot(legs[k][1][0] - a[0], legs[k][1][1] - a[1]) for k in ks)
                for limit in (far * LEG_REACH + LEG_PAD, np.inf):
                    dist, pred = dijkstra(graph, indices=srcs[0], return_predecessors=True, limit=limit)
                    for k in ks:
                        reached = [g for g in goals[k] if np.isfinite(dist[g])]
                        if reached:
                            out[k] = self.leg_points(region, pred, min(reached, key=lambda g: dist[g]), a, legs[k][1])
                    for p in also:
                        reached = [g for g in joined(p) if np.isfinite(dist[g])]
                        if reached and (a, tuple(p[:2])) not in extra:
                            extra[(a, tuple(p[:2]))] = self.leg_points(region, pred, min(reached, key=lambda g: dist[g]),
                                                                       a, p)
                    ks, also = [k for k in ks if out[k] is None], ()
                    if not ks:
                        break
            return out, extra
        return ways

    @staticmethod
    def leg_points(region, pred, node, a, b):
        chain = [node]
        while pred[chain[-1]] >= 0:
            chain.append(int(pred[chain[-1]]))
        pts = np.vstack([np.asarray(a[:2], float)[None], region.world(chain[::-1])[:, :2], np.asarray(b[:2], float)[None]])
        return bends(pts, LEG_BEND)


    def pieces(self, inst, wait=False):
        stamp = nav.store_stamp()
        with self.lock:
            got = self.map_pieces.get(inst)
            fresh = got is not None and (got[0] == stamp or time.time() - got[1] < PIECES_STALE)
            working = self.piecing.get(inst)
            start = not fresh and working is None
            if start:
                working = self.piecing[inst] = threading.Event()
        if start:
            def work():
                try:
                    made = Pieces(self.store, inst)
                except Exception:
                    log_error(f"working out map {inst}'s pieces")
                    made = None
                with self.lock:
                    self.map_pieces[inst] = (stamp, time.time(), made)
                    self.piecing.pop(inst, None)
                working.set()
            if wait and got is None:
                work()
            else:
                start_thread(f"map {inst}'s pieces", work)
        elif wait and got is None:
            working.wait()
        if wait and got is None:
            got = self.map_pieces.get(inst)
        return got[2] if got else None

    def reach(self, inst, spot, spots, ghost=False, reverse=False, wait=False):
        out = [None] * len(spots)
        pieces = self.pieces(inst, wait) if spots else None
        here = pieces.labels(spot) if pieces else None
        if here:
            for k, p in enumerate(spots):
                there = pieces.labels(p)
                if there and there[0] != here[0]:
                    out[k] = False
                elif there and there[1] == here[1]:
                    out[k] = True
        rest = [k for k, v in enumerate(out) if v is None]
        if rest:
            for k, v in zip(rest, self.near_reach(inst, spot, [spots[k] for k in rest], ghost, reverse)):
                out[k] = v
        return out

    def near_reach(self, inst, spot, spots, ghost=False, reverse=False, margin=1):
        if not spots:
            return []
        key, region = self.region(inst, spot, spot, margin)
        profile = Profile(None, "", None, ghost, spot, None)
        pk, (graph, *_) = self.priced(key, region, profile)
        src = tuple(region.nodes_at(spot[:2], spot[2] if len(spot) > 2 else None))
        if not src:
            return [None] * len(spots)
        ck = (pk, src, "reach", reverse)
        with self.lock:
            got = self.costs.get(ck)
            if got is not None:
                self.costs.move_to_end(ck)
        if got is None:
            got = np.isfinite(dijkstra(graph.T.tocsr() if reverse else graph, indices=list(src), min_only=True))
            with self.lock:
                self.costs[ck] = got
                while len(self.costs) > KEEP_COSTS:
                    self.costs.popitem(last=False)
        reached = np.flatnonzero(got)
        unsure = None if self.boxed(region, reached) or len(reached) < PLACE_PIECES else False
        out = []
        for p in spots:
            r, c = nav.cell_of(*p[:2])
            inside = region.tr0 <= nav.grid_tile(r) <= region.tr1 and region.tc0 <= nav.grid_tile(c) <= region.tc1
            nodes = region.nodes_at(p[:2], p[2] if len(p) > 2 else None) if inside else []
            out.append(None if inside and not nodes else True if any(got[k] for k in nodes) else unsure)
        return out


    def end(self, inst, point, z, indoors, profile, reverse=False):
        s = nav.Search(self.paths, inst, point, point, END_MARGIN, z if not reverse else None, z if reverse else None,
                       indoors if not reverse else None, True, profile.ghost, profile.rows, profile.seek, profile.roads,
                       profile.gather, None, False, profile.level, profile.exempt, profile.walker)
        if not s.read_ground():
            return None
        for stage in (s.read_buildings, s.floors_over, s.rules, s.coarse, s.mobs, s.terrain_graph, s.building_graph,
                      s.close_graph, s.ends):
            stage()
        if reverse:
            starts = list(dict.fromkeys(s.targets or s.fallback))
            if not starts:
                return None
            dist = dijkstra(s.graph.T.tocsr(), indices=starts, min_only=True)
        else:
            if not s.walk():
                return None
            dist = s.dist
        return s, dist

    def seeds(self, region, s, dist):
        out = {}
        reached = np.flatnonzero(np.isfinite(dist))
        land = reached[reached < s.n]
        if len(land):
            rr, cc = s.cells_of(land)
            nodes = region.node_of_cells((s.r0 + rr) * 8192 + s.c0 + cc)
            for v, k in zip(nodes.tolist(), land.tolist()):
                if v >= 0 and (v not in out or dist[k] < out[v][0]):
                    out[v] = (float(dist[k]), k)
        for bi, place in s.big.items():
            got = region.floor_at.get(int(place[1]))
            if got is None:
                continue
            off_r, f = got
            off, size = s.offsets[bi], len(s.blds[bi]["layers"].nodes)
            mine = reached[(reached >= off) & (reached < off + size)]
            if not len(mine) or len(f["piece_of_node"]) != size:
                continue
            for v, k in zip((f["piece_of_node"][mine - off] + off_r).tolist(), mine.tolist()):
                if v not in out or dist[k] < out[v][0]:
                    out[v] = (float(dist[k]), k)
        return out

    def long_way(self, inst, start, goal, start_z=None, goal_z=None, indoors=None, ghost=False, rows=None, mode="",
                 level=None, margin=REGION_MARGIN, walker=None):
        profile = Profile(rows, mode, level, ghost, start, goal, walker)
        profile.exempt = self.exempt(inst, start, goal)
        a = self.end(inst, start, start_z, indoors, profile)
        b = self.end(inst, goal, goal_z, None, profile, reverse=True)
        if a is None or b is None:
            return None
        best = self.route(inst, start, goal, margin, profile, a, b)
        if best is not None and best.partial and margin < REGION_MARGIN * REGION_GROW and self.boxed(best.region, best.reached):
            best = self.route(inst, start, goal, margin * REGION_GROW, profile, a, b) or best
        if best is None:
            return None
        graph, weight, swim, over, zone = best.priced
        return self.assemble(best.region, profile, inst, start, goal, a[0], b[0], best.seeds, best.sinks, best.chain,
                             best.partial, weight, swim, over, zone)

    def route(self, inst, start, goal, margin, profile, a, b):
        key, region = self.region(inst, start, goal, margin)
        _, priced = self.priced(key, region, profile)
        graph = priced[0]
        seeds, sinks = self.seeds(region, *a), self.seeds(region, *b)
        if not seeds:
            return None
        n = region.n
        src, dst = n, n + 1
        coo = graph.tocoo()
        rows_, cols_, data = [coo.row, np.full(len(seeds), src)], [coo.col, np.array(list(seeds), np.int64)], \
            [coo.data, np.array([c for c, _ in seeds.values()])]
        if sinks:
            rows_.append(np.array(list(sinks), np.int64)); cols_.append(np.full(len(sinks), dst))
            data.append(np.array([c for c, _ in sinks.values()]))
        aug = csr_matrix((np.concatenate(data), (np.concatenate(rows_), np.concatenate(cols_))), shape=(n + 2, n + 2))
        dist, pred = dijkstra(aug, indices=src, return_predecessors=True)
        partial = not np.isfinite(dist[dst])
        reached = None
        if partial:
            reached = np.flatnonzero(np.isfinite(dist[:n]))
            spots = region.world(reached)
            last = int(reached[np.argmin(np.hypot(spots[:, 0] - goal[0], spots[:, 1] - goal[1]))])
        else:
            last = int(pred[dst])
        chain = [last]
        while pred[chain[-1]] >= 0 and pred[chain[-1]] != src:
            chain.append(int(pred[chain[-1]]))
        return SimpleNamespace(price=float(dist[dst]), region=region, priced=priced, seeds=seeds, sinks=sinks,
                               chain=chain[::-1], partial=partial, reached=reached, margin=margin)

    @staticmethod
    def boxed(region, reached):
        land = reached[reached < region.terrain_nodes]
        if not len(land):
            return False
        r, c = region.spot[land, 0] - region.r0, region.spot[land, 1] - region.c0
        h, w = (region.tr1 - region.tr0 + 1) * 128, (region.tc1 - region.tc0 + 1) * 128
        edge = STRIDE * 2
        return bool(((r < edge) | (r >= h - edge) | (c < edge) | (c >= w - edge)).any())

    def assemble(self, region, profile, inst, start, goal, sa, sb, seeds, sinks, chain, partial, weight, swim, over, zone):
        first = seeds[chain[0]][1]
        sa.end, sa.partial, sa.near_end, sa.snapped, sa.boxed = first, False, None, False, False
        head = sa.way(to_goal=False)
        pts = [list(p) for p in head["points"]]
        cost, swum = float(sa.dist[first]), float(head["swum"])
        overs, zones = float(head.get("over", 0)), list(head.get("overZones", []))
        enemy, cities = float(head.get("enemy", 0)), list(head.get("enemyCities", []))
        spots = region.world(chain)
        at = [pts[-1] if pts else list(start)]
        if not partial:
            last = sinks[chain[-1]][1]
            end_at = sb.cells_of([last]) if last < sb.n else None
            if end_at is not None:
                r, c = int(end_at[0][0]), int(end_at[1][0])
                spots[-1, :2] = nav.world_of(sb.r0 + r, sb.c0 + c)
                spots[-1, 2] = np.nan
            else:
                k = sb.building_of(last)
                L = sb.blds[k]["layers"]
                n_, w_ = L.world(*L.nodes[last - sb.offsets[k], :2])
                spots[-1] = (float(n_), float(w_), sb.node_height(last))
        was, since = 0, 0
        for k in self.anchors(spots, np.asarray(chain) < region.terrain_nodes):
            to = spots[k] if chain[k] >= region.terrain_nodes or np.isfinite(spots[k][2]) else self.on_ground(region, inst, spots[k])
            seg = self.stretch(inst, at[-1], to, profile)
            if seg is None:
                piece = [[round(float(v), 1) for v in (s[:2] if not np.isfinite(s[2]) else s)] for s in spots[min(was + 1, k):k + 1]]
                pts, since = self.unspurred(inst, pts, since, piece, profile)
            else:
                pts, since = self.unspurred(inst, pts, since, seg["points"], profile)
                cost += seg["cost"]
                swum += seg["swum"]
                overs += seg.get("over", 0)
                zones += seg.get("overZones", [])
                enemy += seg.get("enemy", 0)
                cities += seg.get("enemyCities", [])
            at.append(pts[-1] if pts else at[-1])
            was = k
        tail_partial, gap, near = partial, 0, None
        last = sinks[chain[-1]][1] if not partial else None
        if partial and pts:
            r, c = nav.cell_of(*pts[-1][:2])
            if 0 <= r - sb.r0 < sb.fh and 0 <= c - sb.c0 < sb.fw:
                last = int(sb.node_of(r - sb.r0, c - sb.c0))
        if last is not None and last >= 0:
            sb.sources, sb.others, sb.pocket, sb.indoor_start = [last], [], False, None
            if sb.walk():
                tail = sb.way()
                pts, since = self.unspurred(inst, pts, since, tail["points"], profile)
                cost += tail["cost"]
                swum += tail["swum"]
                overs += tail.get("over", 0)
                zones += tail.get("overZones", [])
                enemy += tail.get("enemy", 0)
                cities += tail.get("enemyCities", [])
                tail_partial, gap, near = tail["partial"], tail.get("gap", 0), tail.get("near")
                partial = False
        if partial:
            gap = round(math.hypot(pts[-1][0] - goal[0], pts[-1][1] - goal[1]) if pts else math.hypot(start[0] - goal[0], start[1] - goal[1]))
            pts.append(list(goal))
        length = nav.way_length([start] + pts)
        out = {"points": [[round(v, 1) for v in p] for p in pts], "length": round(length), "partial": bool(tail_partial),
               "stride": 1, "boxed": False, "cost": round(cost, 1), "swum": round(swum), "travel": True}
        if overs:
            out["over"] = round(overs)
            out["overZones"] = list(dict.fromkeys(zones))
        if enemy:
            out["enemy"] = round(enemy)
            out["enemyCities"] = list(dict.fromkeys(cities))
        if tail_partial:
            out["gap"] = gap
        if near:
            out["near"] = near
        if profile.rows is not None and len(profile.rows):
            rows = profile.rows
            out["mobs"] = nav.mobs_passed(start, pts, rows[rows[:, 3] >= 0])
            if profile.seek:
                out["fight"] = nav.mobs_passed(start, pts, rows[rows[:, 3] < 0])
        return out

    def on_ground(self, region, inst, spot):
        r, c = nav.cell_of(*spot[:2])
        br, bc = (r - region.r0) // STRIDE, (c - region.c0) // STRIDE
        floored = region.g.get("floored")
        if floored is not None and 0 <= br < floored.shape[0] and 0 <= bc < floored.shape[1] and floored[br, bc]:
            return spot
        g = self.paths.terrain.region(inst, r, c, r + 1, c + 1)
        z, wz = float(g["ground"][0, 0]), float(g["water"][0, 0])
        out = np.array(spot, np.float64)
        out[2] = wz if np.isfinite(wz) and not (np.isfinite(z) and z >= wz) else z
        return out

    @staticmethod
    def anchors(spots, ground):
        n = len(spots)
        if n < 2:
            return []
        cuts = sorted({0, n - 1} | {k for k in range(1, n) if ground[k] != ground[k - 1]})
        steps = np.r_[0.0, np.cumsum(np.hypot(np.diff(spots[:, 0]), np.diff(spots[:, 1])))]
        out = set(cuts[1:])
        todo = list(zip(cuts[:-1], cuts[1:]))
        while todo:
            i, j = todo.pop()
            if j - i < 2:
                continue
            a, b = spots[i, :2], spots[j, :2]
            mid = spots[i + 1:j, :2]
            ab = b - a
            t = np.clip(((mid - a) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
            off = np.hypot(*(mid - (a + t[:, None] * ab)).T)
            k = i + 1 + int(np.argmax(off))
            if off.max() <= BEND:
                if steps[j] - steps[i] <= STRETCH:
                    continue
                k = int(np.clip(np.searchsorted(steps, (steps[i] + steps[j]) / 2), i + 1, j - 1))
            out.add(k)
            todo += [(i, k), (k, j)]
        return sorted(out)

    def unspurred(self, inst, pts, since, piece, profile):
        if since >= len(pts) or not piece:
            return pts + piece, len(pts)
        last = np.array([p[:2] for p in pts[since:]], np.float64)
        on = np.array([p[:2] for p in piece], np.float64)
        to_end = np.r_[np.cumsum(np.hypot(*np.diff(last, axis=0).T)[::-1])[::-1], 0.0]
        from_join = np.cumsum(np.hypot(*np.diff(np.vstack([last[-1:], on]), axis=0).T))
        across = np.hypot(last[:, None, 0] - on[None, :, 0], last[:, None, 1] - on[None, :, 1])
        along = to_end[:, None] + from_join[None, :]
        saves = np.where(across <= JOIN_NEAR, along - across, -np.inf)
        i, j = np.unravel_index(int(np.argmax(saves)), saves.shape)
        if saves[i, j] <= JOIN_SAVES:
            return pts + piece, len(pts)
        a, b = pts[since + i], piece[j]
        hop = self.stretch(inst, a, b, profile)
        if hop is None or nav.way_length([a] + hop["points"]) >= along[i, j]:
            return pts + piece, len(pts)
        kept = pts[:since + i + 1]
        return kept + hop["points"] + piece[j + 1:], len(kept)

    def stretch(self, inst, a, b, profile):
        az = a[2] if len(a) > 2 and a[2] is not None and np.isfinite(a[2]) else None
        bz = b[2] if len(b) > 2 and np.isfinite(b[2]) else None
        for margin in (STRETCH_MARGIN, STRETCH_MARGIN * 3):
            got = self.paths.search(inst, tuple(a[:2]), tuple(b[:2]), margin, az, bz, None, houses=False, ghost=profile.ghost,
                                    avoid=profile.rows, seek=profile.seek, roads=profile.roads, gather=profile.gather,
                                    level=profile.level, exempt=profile.exempt, walker=profile.walker)
            if got is not None and not got["partial"]:
                return got
        return None
