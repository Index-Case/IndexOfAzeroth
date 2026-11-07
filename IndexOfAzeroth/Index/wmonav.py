# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import io
import math
import os
import struct
import sys
import threading
import time

from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image
from scipy.ndimage import grey_closing
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import clientfiles as wm
import arrays
import m2
import realign
import storedonly
import store
import navstore

CACHE = navstore.CACHE
VERSION = 15
PROPS_VERSION = 14
GEO_VERSION = 4
RES = 1.0
SAMPLE = 0.45
LAYERS = 6
MAX_UP = 50
DUNGEON_MAX_UP = 62
STEP = 1.2
STEP_UP = 1.4
MAX_DROP = 4.0
JUMP_REACH = 4
JUMP_DROP = 10.0
JUMP_UP = 1.64
DROP_COST = 30.0
WATER_JUMP_REACH = 8
WATER_JUMP_DROP = 60.0
BODY = (0.6, 2.2)
OWN_FLOOR = 1.2
BODY_WIDTH = 0.4
GAP = 0.3
TREAD = 0.75
FINE = 0.05
SUB = 4
STAND = [(r, c) for r in (1, 2) for c in (1, 2)]
SWIM_COST = 4.0
UNIT = 1600 / 3 / 128


chunk_dict = wm.chunks


def group_geometry(raw, drawn=None):
    top = chunk_dict(raw)
    mogp = top.get("MOGP", b"")
    sub, at = {}, 68
    while at + 8 <= len(mogp):
        tag = mogp[at:at + 4][::-1].decode("latin1")
        size = struct.unpack_from("<I", mogp, at + 4)[0]
        sub.setdefault(tag, mogp[at + 8:at + 8 + size])
        at += 8 + size
    verts = np.frombuffer(sub.get("MOVT", b""), "<f4").reshape(-1, 3).astype(np.float32)
    if sub.get("MOVX"):
        idx = np.frombuffer(sub["MOVX"], "<u4").reshape(-1, 3).astype(np.int64)
    else:
        idx = np.frombuffer(sub.get("MOVI", b""), "<u2").reshape(-1, 3).astype(np.int64)
    if sub.get("MPY2"):
        mpy2 = np.frombuffer(sub["MPY2"], "<u2").reshape(-1, 2)
        flags, material = (mpy2[:, 0] & 0xFF).astype(np.uint8), mpy2[:, 1]
        material = np.where(material == 0xFFFF, 0xFF, material)
    elif sub.get("MOPY"):
        mopy = np.frombuffer(sub["MOPY"], np.uint8).reshape(-1, 2)
        flags, material = mopy[:, 0], mopy[:, 1]
    else:
        flags, material = np.zeros(len(idx), np.uint8), np.zeros(len(idx), np.uint8)
    n = min(len(idx), len(flags))
    if drawn is None:
        solid = ((flags[:n] & 0x08) != 0) | (((flags[:n] & 0x20) != 0) & ((flags[:n] & 0x04) == 0)) | (material[:n] == 0xFF)
    else:
        solid = (material[:n] != 0xFF) & (material[:n] < drawn)
    liquids = []
    mliq = sub.get("MLIQ")
    if mliq and len(mliq) >= 30:
        xv, yv, xt, yt = struct.unpack_from("<4I", mliq, 0)
        corner = struct.unpack_from("<3f", mliq, 16)
        nverts, ntiles = xv * yv, xt * yt
        if 30 + nverts * 8 + ntiles <= len(mliq):
            heights = np.array([struct.unpack_from("<f", mliq, 30 + i * 8 + 4)[0] for i in range(nverts)], np.float32).reshape(yv, xv)
            tiles = np.frombuffer(mliq, np.uint8, ntiles, 30 + nverts * 8).reshape(yt, xt)
            liquids.append((np.array(corner, np.float32), heights, (tiles & 0x0F) != 0x0F))
    return verts, idx[:n][solid], liquids


def building_geometry(fid, version):
    return _kept_or_worked_out(os.path.join(CACHE, f"g{GEO_VERSION}-wmo-{fid}.npz"), lambda: _building_geometry(fid, version))


def building_surfaces(fid, version):
    return _kept_or_worked_out(os.path.join(CACHE, f"g{GEO_VERSION}-wmodrawn-{fid}.npz"),
                               lambda: _building_geometry(fid, version, drawn=True))


def _kept_or_worked_out(path, work):
    if wm.serving():
        out = navstore.load_npz(path)
        if out is None or not {"verts", "tris", "water"} <= set(out):
            raise wm.NotBuilt(("shape", os.path.basename(path)))
        out.pop("sources", None)
        return out
    with realign.working("paths", when=realign.kept_from_before(path)):
        kept = _kept_geometry(path)
        if kept is not None:
            return kept
        with wm.recording() as used:
            out = work()
        return _keep_geometry(path, out, used)


GEOMETRY = {"verts", "tris", "water"}
RASTER = {"at", "heights"}


def _kept_geometry(path, fields=GEOMETRY):
    out = navstore.load_npz(path)
    if out is None or not fields <= set(out):
        return None
    sources = [str(s) for s in out.pop("sources", ())]
    if not wm.still_good(path, sources):
        return None
    wm.note_sources(sources or [wm.UNKNOWN_SOURCE])
    return out


def _keep_geometry(path, out, used):
    os.makedirs(CACHE, exist_ok=True)
    arrays.save_npz(path, **out, sources=np.array(sorted(used)))
    return out


def _building_geometry(fid, version, drawn=False):
    root = chunk_dict(wm.fetch(wm.file_address(fid, version), f"wmo-{fid}.wmo"))
    materials = len(root.get("MOMT", b"")) // 64 if drawn else None
    gfid = root.get("GFID", b"")
    groups = [g for g in struct.unpack_from(f"<{len(gfid) // 4}I", gfid) if g] if gfid else []
    all_v, all_t, water = [], [], []
    base = 0

    def download(g):
        try:
            return wm.fetch(wm.file_address(g, version), f"wmog-{g}.wmo")
        except OSError as e:
            if storedonly.not_there(e):
                return None
            raise
    with ThreadPoolExecutor(8) as pool:
        raws = list(pool.map(download, groups))
    for raw in raws:
        if raw is None:
            continue
        try:
            v, t, liq = group_geometry(raw, materials)
        except (ValueError, struct.error):
            continue
        all_v.append(v)
        all_t.append(t + base)
        base += len(v)
        for corner, heights, mask in liq:
            yt, xt = mask.shape
            for j in range(yt):
                for i in range(xt):
                    if mask[j, i]:
                        h = float(heights[j:j + 2, i:i + 2].max())
                        water.append((corner[0] + (i + 0.5) * UNIT, corner[1] + (j + 0.5) * UNIT, h))
    return {"verts": np.concatenate(all_v) if all_v else np.zeros((0, 3), np.float32),
            "tris": np.concatenate(all_t) if all_t else np.zeros((0, 3), np.int32),
            "water": np.array(water, np.float32).reshape(-1, 3)}


WMO_DOODAD_SET = 32
WMO_DOODAD = 40


def wmo_doodads(root, chosen=0):
    ids, modd, mods = root.get("MODI", b""), root.get("MODD", b""), root.get("MODS", b"")
    models = struct.unpack_from(f"<{len(ids) // 4}I", ids) if ids else ()
    sets = [struct.unpack_from("<II", mods, k + 20) for k in range(0, len(mods) - WMO_DOODAD_SET + 1, WMO_DOODAD_SET)]
    shown = {i for s in {0, chosen} if s < len(sets) for i in range(sets[s][0], sets[s][0] + sets[s][1])}
    out = []
    for i in sorted(shown):
        if (i + 1) * WMO_DOODAD > len(modd):
            continue
        name, x, y, z, qx, qy, qz, qw, scale = struct.unpack_from("<I3f4ff", modd, i * WMO_DOODAD)
        k = name & 0xFFFFFF
        if k < len(models) and models[k]:
            out.append((models[k], x, y, z, qx, qy, qz, qw, scale))
    return out


def quat_turn(q, points):
    x, y, z, w = q
    m = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    return np.asarray(points, np.float64) @ m.T


def m2_geometry(fid, version):
    return _kept_or_worked_out(os.path.join(CACHE, f"g{GEO_VERSION}-m2-{fid}.npz"), lambda: _m2_geometry(fid, version))


def _m2_geometry(fid, version):
    raw = wm.fetch(wm.file_address(fid, version), f"m2-{fid}.m2")
    md = raw[8:8 + struct.unpack_from("<I", raw, 4)[0]] if raw[:4] == b"MD21" else raw
    verts, tris = np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int64)
    if md[:4] == b"MD20" and len(md) >= 0xE8:
        ni, oi = struct.unpack_from("<II", md, 0xD8)
        nv, ov = struct.unpack_from("<II", md, 0xE0)
        if nv and ni and ov + nv * 12 <= len(md) and oi + ni * 2 <= len(md):
            verts = np.frombuffer(md, "<f4", nv * 3, ov).reshape(-1, 3).astype(np.float32)
            tris = np.frombuffer(md, "<u2", ni - ni % 3, oi).reshape(-1, 3).astype(np.int64)
            tris = tris[(tris < nv).all(axis=1)]
    return {"verts": verts, "tris": tris, "water": np.zeros((0, 3), np.float32)}


BOUNDS = os.path.join(CACHE, "m2-bounds-1.json")
_bounds = {"read": False, "boxes": {}, "dirty": False}
_bounds_lock = threading.Lock()


def _m2_body(fid, version):
    raw = wm.fetch(wm.file_address(fid, version), f"m2-{fid}.m2")
    return raw[8:8 + struct.unpack_from("<I", raw, 4)[0]] if raw[:4] == b"MD21" else raw


def _per_model(kept, path, fid, work):
    with _bounds_lock:
        if not kept["read"]:
            kept["boxes"] = navstore.load_json(path, {})
            kept["read"] = True
        got = kept["boxes"].get(str(fid))
    if got and got["at"] >= wm.switched_since():
        return tuple(got["box"]) if got["box"] else None
    value = work()
    with _bounds_lock:
        kept["boxes"][str(fid)] = {"at": time.time(), "box": value}
        kept["dirty"] = True
    return tuple(value) if value else None


def _keep_per_model(kept, path):
    with _bounds_lock:
        if kept["dirty"]:
            os.makedirs(CACHE, exist_ok=True)
            store.save_json(path, kept["boxes"], indent=None)
            kept["dirty"] = False


def m2_bounds(fid, version):
    def work():
        md = _m2_body(fid, version)
        return list(struct.unpack_from("<6f", md, 0xA0)) if md[:4] == b"MD20" and len(md) >= 0xB8 else None
    return _per_model(_bounds, BOUNDS, fid, work)


def keep_m2_bounds():
    _keep_per_model(_bounds, BOUNDS)


RASTER_CELL = 1.0
RASTER_CLOSE = 1
RASTER_VERSION = 1
ALPHA_CUT = 0.5
ALPHA_SIDE = 128
M2_STRIDE = 48


def m2_vertices(md, uv=False):
    none = np.zeros((0, 5 if uv else 3))
    if md[:4] != b"MD20" or len(md) < 0x44:
        return none
    nv, ov = struct.unpack_from("<II", md, 0x3C)
    if not nv or ov + nv * M2_STRIDE > len(md):
        return none
    floats = np.frombuffer(md, "<f4", nv * M2_STRIDE // 4, ov).reshape(nv, -1).astype(np.float64)
    verts = floats[:, [0, 1, 2, 8, 9]] if uv else floats[:, :3]
    return np.where(np.isfinite(verts).all(1)[:, None], verts, np.nan)


def _m2_array(md, at, fmt):
    count, start = struct.unpack_from("<II", md, at)
    size = struct.calcsize("<" + fmt)
    if not count or start + count * size > len(md):
        return []
    return [struct.unpack_from("<" + fmt, md, start + k * size) for k in range(count)]


def m2_sections(raw, md, count, version, every=False):
    parts = m2.chunks(raw) if raw[:4] == b"MD21" else {}
    sfid = parts.get("SFID", b"")
    if len(sfid) < 4:
        return []
    skin_id = struct.unpack_from("<I", sfid)[0]
    try:
        skin = m2.read_skin(wm.fetch(wm.file_address(skin_id, version), f"skin-{skin_id}.skin"))
    except (OSError, ValueError, struct.error) as e:
        if isinstance(e, OSError) and not storedonly.not_there(e):
            raise
        return []
    txid = parts.get("TXID", b"")
    files = struct.unpack_from(f"<{len(txid) // 4}I", txid) if txid else ()
    textures = _m2_array(md, 0x50, "II")
    blends = [b for _, b in _m2_array(md, 0x70, "HH")]
    combos = [c for (c,) in _m2_array(md, 0x80, "H")]
    lookup, indices = np.array(skin["lookup"], np.int64), np.array(skin["indices"], np.int64)
    out = []
    for k, s in enumerate(skin["sections"]):
        idx = indices[s["indexStart"]:s["indexStart"] + s["indexCount"] - s["indexCount"] % 3]
        if not len(idx) or idx.max() >= len(lookup):
            continue
        tris = lookup[idx].reshape(-1, 3)
        tris = tris[(tris < count).all(1)]
        texture, blend = None, -1
        batch = next((b for b in skin["batches"] if b["section"] == k), None)
        if batch and batch["material"] < len(blends):
            blend = blends[batch["material"]]
        if batch and (blend >= 1 or (every and blend == 0)) and batch["textureCombo"] < len(combos):
            t = combos[batch["textureCombo"]]
            if t < len(textures) and textures[t][0] == 0 and t < len(files) and files[t]:
                texture = files[t]
        out.append((tris, texture, blend) if every else (tris, texture))
    return out


def texture_alpha(fid, version):
    try:
        blp = wm.fetch(wm.file_address(fid, version), f"tex-{fid}.blp")
    except OSError as e:
        if not storedonly.not_there(e):
            raise
        return None
    try:
        im = Image.open(io.BytesIO(blp)).convert("RGBA")
    except (OSError, ValueError, struct.error, NotImplementedError):
        return None
    im.thumbnail((ALPHA_SIDE, ALPHA_SIDE))
    return np.asarray(im)[:, :, 3].astype(np.float64) / 255


def model_points(verts, sections, alpha_of, cell=RASTER_CELL):
    good = np.isfinite(verts).all(1)
    if not sections:
        return verts[good, :3]
    out = [np.zeros((0, 3))]
    for tris, texture in sections:
        tris = tris[good[tris].all(1)]
        if not len(tris):
            continue
        a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
        p = sample_triangles(a[:, :3], b[:, :3], c[:, :3], cell / 2)
        pts, owner = p[0].astype(np.float64), p[1]
        alpha = alpha_of(texture) if texture else None
        if alpha is not None:
            ta, tb, tc = a[owner, :3], b[owner, :3], c[owner, :3]
            e0, e1, e2 = tb - ta, tc - ta, pts - ta
            d00, d01, d11 = (e0 * e0).sum(1), (e0 * e1).sum(1), (e1 * e1).sum(1)
            d20, d21 = (e2 * e0).sum(1), (e2 * e1).sum(1)
            den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-12, d00 * d11 - d01 * d01, 1.0)
            v, w = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
            uv = a[owner, 3:] + v[:, None] * (b[owner, 3:] - a[owner, 3:]) + w[:, None] * (c[owner, 3:] - a[owner, 3:])
            t = np.mod(uv, 1.0)
            t = np.where((t == 0) & (uv > 0), 1.0, t)
            h, wd = alpha.shape
            col = np.minimum(np.floor(t[:, 0] * wd).astype(np.int64), wd - 1)
            row = np.minimum(np.floor(t[:, 1] * h).astype(np.int64), h - 1)
            pts = pts[alpha[row, col] >= ALPHA_CUT]
        out.append(pts)
    return np.concatenate(out)


def raster_of_points(pts, size, cell=RASTER_CELL, close=RASTER_CLOSE):
    if not len(pts):
        return None
    x0 = (math.floor(pts[:, 0].min() / cell) - close) * cell
    y0 = (math.floor(pts[:, 1].min() / cell) - close) * cell
    i = np.floor((pts[:, 0] - x0) / cell).astype(np.int64)
    j = np.floor((pts[:, 1] - y0) / cell).astype(np.int64)
    top = np.full((i.max() + close + 1, j.max() + close + 1), -np.inf)
    np.maximum.at(top, (i, j), pts[:, 2])
    r = np.arange(-close, close + 1)
    disc = r[:, None] ** 2 + r[None, :] ** 2 <= close * close
    closed = grey_closing(top, footprint=disc, mode="constant", cval=-np.inf)
    heights = np.where(np.isfinite(top), top, closed)
    return float(x0), float(y0), float(cell), np.where(np.isfinite(heights), heights, np.nan), size


def model_size(verts):
    good = verts[np.isfinite(verts).all(1), :3]
    if not len(good):
        return 0.0, 0.0
    lo, hi = good.min(0), good.max(0)
    return float(max(hi[0] - lo[0], hi[1] - lo[1])), float(hi[2] - lo[2])


class FetchFailed(Exception):

    def __init__(self, fid, error):
        super().__init__(f"file {fid}: {error!r}")
        self.fid, self.error = fid, error


def transient(error):
    return isinstance(error, OSError) and not storedonly.not_there(error) and not isinstance(error, storedonly.NotStored)


def m2_raster(fid, version):
    path = os.path.join(CACHE, f"m2-raster-{RASTER_VERSION}-{fid}.npz")
    kept = _kept_geometry(path, RASTER)
    if kept is None:
        alphas = {}

        def alpha_of(texture):
            if texture not in alphas:
                alphas[texture] = texture_alpha(texture, version)
            return alphas[texture]
        with wm.recording() as used:
            try:
                raw = wm.fetch(wm.file_address(fid, version), f"m2-{fid}.m2")
                md = raw[8:8 + struct.unpack_from("<I", raw, 4)[0]] if raw[:4] == b"MD21" else raw
                verts = m2_vertices(md, uv=True)
                pts = model_points(verts, m2_sections(raw, md, len(verts), version), alpha_of)
            except OSError as e:
                if not transient(e):
                    raise
                raise FetchFailed(fid, e) from e
        got = raster_of_points(pts, model_size(verts))
        at = (*got[:3], *got[4]) if got else (0.0,) * 5
        heights = (got[3] if got else np.zeros((0, 0))).astype(np.float32)
        kept = _keep_geometry(path, {"at": np.array(at, np.float64), "heights": heights}, used)
    if not kept["heights"].size:
        return None
    x0, y0, cell, across, tall = (float(v) for v in kept["at"])
    return x0, y0, cell, kept["heights"].astype(np.float64), (across, tall)


def place(points, origin, yaw, scale=1.0, tilt=(0.0, 0.0)):
    points = points * scale
    if not (tilt[0] or tilt[1]):
        a = math.radians(180 + yaw)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        return np.stack([origin[0] + x * math.cos(a) - y * math.sin(a), origin[1] + x * math.sin(a) + y * math.cos(a), origin[2] + z], 1)
    p = np.asarray(points, np.float64) @ turned(yaw, tilt).T
    return np.stack([origin[0] + p[:, 0], origin[1] + p[:, 1], origin[2] + p[:, 2]], 1)


def turned(yaw, tilt):
    (cz, sz), (cy, sy), (cx, sx) = ((math.cos(math.radians(v)), math.sin(math.radians(v))) for v in (yaw, tilt[0], tilt[1]))
    z = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    x = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    return np.diag([-1.0, -1.0, 1.0]) @ z @ y @ x


def sample_triangles(a, b, c, spacing=None):
    longest = np.maximum(np.maximum(np.linalg.norm(b - a, axis=1), np.linalg.norm(c - a, axis=1)), np.linalg.norm(c - b, axis=1))
    steps = np.clip(np.ceil(longest / (spacing or SAMPLE)).astype(int), 1, 400)
    pts, owner = [], []
    for n in np.unique(steps):
        sel = np.flatnonzero(steps == n)
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        keep = i + j <= n
        wi, wj = (i[keep] / n).astype(np.float32), (j[keep] / n).astype(np.float32)
        p = a[sel, None, :] + wi[None, :, None] * (b - a)[sel, None, :] + wj[None, :, None] * (c - a)[sel, None, :]
        pts.append(p.reshape(-1, 3))
        owner.append(np.repeat(sel, len(wi)))
    if not pts:
        return np.zeros((0, 3), np.float32), np.zeros(0, int)
    return np.concatenate(pts), np.concatenate(owner)


def within(height, z, slack=3):
    if z is None:
        return True
    if isinstance(z, (tuple, list)):
        return z[0] - slack <= height <= z[1] + slack
    return abs(height - z) <= slack


class Layers:

    def __init__(self, parts, res=RES, bounds=None, max_up=MAX_UP, kept=None, cap_first=False):
        self.max_up = max_up
        tris_w, water_w = [], []
        for geo, origin, yaw, *rest in parts:
            scale = rest[0] if rest else 1.0
            tilt = rest[1] if len(rest) > 1 else (0.0, 0.0)
            if len(geo["tris"]):
                v = place(geo["verts"], origin, yaw, scale, tilt)
                t = geo["tris"]
                tris_w.append(np.stack([v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]], 1))
            if len(geo["water"]):
                water_w.append(place(geo["water"], origin, yaw, scale, tilt))
        tris = np.concatenate(tris_w) if tris_w else np.zeros((0, 3, 3), np.float32)
        water = np.concatenate(water_w) if water_w else np.zeros((0, 3), np.float32)
        allp = np.concatenate([tris.reshape(-1, 3), water]) if len(water) else tris.reshape(-1, 3)
        if bounds is None:
            if not len(allp):
                raise ValueError("no geometry")
            bounds = (allp[:, 0].max() + 2, allp[:, 1].max() + 2, allp[:, 0].min() - 2, allp[:, 1].min() - 2)
        self.top, self.left = float(bounds[0]), float(bounds[1])
        self.res = res
        self.h = max(1, int(math.ceil((bounds[0] - bounds[2]) / res)))
        self.w = max(1, int(math.ceil((bounds[1] - bounds[3]) / res)))
        self.zmin = float(allp[:, 2].min()) - 3 if len(allp) else 0.0
        bottom, right = self.top - self.h * res - res, self.left - self.w * res - res
        tris = tris[(tris[:, :, 0].max(axis=1) >= bottom) & (tris[:, :, 0].min(axis=1) <= self.top + res)
                    & (tris[:, :, 1].max(axis=1) >= right) & (tris[:, :, 1].min(axis=1) <= self.left + res)]

        a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal, axis=1) + 1e-9
        walk = normal[:, 2] / length >= math.cos(math.radians(self.max_up))
        pts, owner = sample_triangles(a, b, c)
        r, cc = self.cell(pts[:, 0], pts[:, 1])
        inside = (r >= 0) & (r < self.h) & (cc >= 0) & (cc < self.w)
        pts, owner, r, cc = pts[inside], owner[inside], r[inside], cc[inside]
        key = (r.astype(np.int64) * self.w + cc) * 100000
        zval = np.round((pts[:, 2] - self.zmin) * 10).astype(np.int64)
        fw_all = walk[owner]
        self.walls = np.sort(key[~fw_all] + zval[~fw_all])
        self.floors = np.sort(key[fw_all] + zval[fw_all])
        fr = np.clip(((self.top - pts[:, 0]) / self.res - r) * SUB, 0, SUB - 1).astype(np.int64)
        fc = np.clip(((self.left - pts[:, 1]) / self.res - cc) * SUB, 0, SUB - 1).astype(np.int64)
        fine = ((r.astype(np.int64) * self.w + cc) * SUB * SUB + fr * SUB + fc) * 100000
        self.walls_fine = np.sort(fine[~fw_all] + zval[~fw_all])
        self.floors_fine = np.sort(fine[fw_all] + zval[fw_all])
        if kept is not None:
            if kept[0].shape[:2] != (self.h, self.w):
                raise ValueError(f"kept layers of a {kept[0].shape[:2]} grid, these parts make {(self.h, self.w)}")
            self.heights, self.swim = kept
            self.index_nodes()
            return
        fw = walk[owner]
        floors = np.stack([r[fw], cc[fw], np.round(pts[fw, 2] / 0.75) * 0.75], 1)
        wr, wc = self.cell(water[:, 0], water[:, 1]) if len(water) else (np.zeros(0, int), np.zeros(0, int))
        win = (wr >= 0) & (wr < self.h) & (wc >= 0) & (wc < self.w)
        heights = np.full((self.h, self.w, LAYERS), np.nan, np.float32)
        swim = np.zeros((self.h, self.w, LAYERS), bool)
        spans = {}
        for rr, c2, hh in np.unique(floors, axis=0) if len(floors) else []:
            spans.setdefault((int(rr), int(c2)), []).append((float(hh), False))
        for (rr, c2), hh in zip(zip(wr[win], wc[win]), water[win, 2]):
            spans.setdefault((int(rr), int(c2)), []).append((float(hh), True))
        cand = []
        for (rr, c2), lst in spans.items():
            lst.sort(key=lambda s: -s[0])
            kept = []
            for hh, sw in lst:
                if all(abs(hh - k[0]) >= 1.0 for k in kept):
                    kept.append((hh, sw))
            cand += [(rr, c2, hh, sw) for hh, sw in kept]
        cr, cc2, ch, cs = (np.array([k[i] for k in cand], dtype) for i, dtype in ((0, np.int64), (1, np.int64),
                                                                                 (2, np.float32), (3, bool)))
        base = (cr * self.w + cc2) * 100000
        hz = (ch - self.zmin) * 10
        hit = self.solid(cr, cc2, STAND, ch)
        a = np.searchsorted(self.floors, base + np.round(hz + OWN_FLOOR * 10).astype(np.int64), "left")
        b = np.searchsorted(self.floors, base + np.round(hz + BODY[1] * 10).astype(np.int64), "right")
        room = ~(hit | (b > a)) | cs
        test = np.flatnonzero(room & ~cs)
        room[test] = self.broad(cr[test], cc2[test], ch[test], tris, walk, owner, pts, r, cc)

        def ranks(cr, cc2):
            cell = cr * self.w + cc2
            at = np.arange(len(cell))
            return at - np.maximum.accumulate(np.where(np.r_[True, cell[1:] != cell[:-1]], at, 0)) if len(cell) else at
        if cap_first:
            rank = ranks(cr, cc2)
            top = (rank < LAYERS) & room
        else:
            cr, cc2, ch, cs = cr[room], cc2[room], ch[room], cs[room]
            rank = ranks(cr, cc2)
            top = rank < LAYERS
        heights[cr[top], cc2[top], rank[top]] = ch[top]
        swim[cr[top], cc2[top], rank[top]] = cs[top]
        self.heights, self.swim = heights, swim

    def solid(self, rows, cols, quarters, height, top=None, over=BODY[0], samples=None):
        hit = np.zeros(len(rows), bool)
        if not len(rows):
            return hit
        fine = self.walls_fine if samples is None else samples
        cell = (rows.astype(np.int64) * self.w + cols) * SUB * SUB
        lo = np.round((height - self.zmin + over) * 10).astype(np.int64)
        hi = np.round(((height if top is None else top) - self.zmin + BODY[1]) * 10).astype(np.int64)
        for qr, qc in quarters:
            base = (cell + qr * SUB + qc) * 100000
            a = np.searchsorted(fine, base + lo, "left")
            b = np.searchsorted(fine, base + hi, "right")
            hit |= b > a
        return hit

    def open_between(self, rows, cols, low, high):
        top = high - BODY[1]
        return ~(self.solid(rows, cols, STAND, low, top)
                 | self.solid(rows, cols, STAND, low, top, OWN_FLOOR, self.floors_fine))

    def crossing(self, ra, ca, dr, dc, height, top=None):
        last = SUB - 1
        if dr and dc:
            ar, ac = (last if dr > 0 else 0), (last if dc > 0 else 0)
            br, bc = last - ar, last - ac
            return (self.solid(ra, ca, [(ar, ac)], height, top) | self.solid(ra + dr, ca + dc, [(br, bc)], height, top)
                    | self.solid(ra, ca + dc, [(ar, bc)], height, top) | self.solid(ra + dr, ca, [(br, ac)], height, top))
        mid = range(1, SUB - 1)
        if dr:
            qa, qb = [((last if dr > 0 else 0), q) for q in mid], [((0 if dr > 0 else last), q) for q in mid]
        else:
            qa, qb = [(q, (last if dc > 0 else 0)) for q in mid], [(q, (0 if dc > 0 else last)) for q in mid]
        return self.solid(ra, ca, qa, height, top) | self.solid(ra + dr, ca + dc, qb, height, top)

    def sweep(self, r0, c0, dr, dc, top, bottom):
        steps = max(abs(dr), abs(dc))
        line = [(round(dr * k / steps), round(dc * k / steps)) for k in range(steps + 1)]
        hit = np.zeros(len(r0), bool)
        for k, ((pr, pc), (qr, qc)) in enumerate(zip(line, line[1:])):
            for test in ("floors", "edge", "walls"):
                i = np.flatnonzero(~hit)
                if not len(i):
                    return hit
                a, b, z0, z1 = r0[i], c0[i], top[i], bottom[i]
                if test == "floors":
                    hit[i] = self.solid(a + qr, b + qc, STAND, z1, z0, OWN_FLOOR, self.floors_fine)
                elif test == "edge":
                    hit[i] = self.crossing(a + pr, b + pc, qr - pr, qc - pc, z0 if k == 0 else z1, z0)
                else:
                    hit[i] = self.solid(a + qr, b + qc, STAND, z1, z0)
        return hit

    def broad(self, cr, cc2, ch, tris, walk, owner, points, rows, cols):
        out = np.zeros(len(cr), bool)
        if not len(cr) or not len(points):
            return out

        def turn(a, b, p):
            return (b[..., 0] - a[..., 0]) * (p[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (p[..., 0] - a[..., 0])
        flat = tris[:, :, :2].astype(np.float64)
        rim = np.linalg.norm(flat[:, [1, 2, 0]] - flat, axis=2).sum(axis=1)
        twice = np.abs(turn(flat[:, 0], flat[:, 1], flat[:, 2]))
        roomy = walk & (twice / np.maximum(rim, 1e-9) >= BODY_WIDTH / 2)
        cell = rows.astype(np.int64) * self.w + cols
        z10 = np.round((points[:, 2] - self.zmin) * 10).astype(np.int64)
        base = (cr.astype(np.int64) * self.w + cc2) * 100000
        hz = np.round((ch - self.zmin) * 10).astype(np.int64)
        mine = roomy[owner]
        keys = np.sort(cell[mine] * 100000 + z10[mine])
        tread = round(TREAD * 10)
        out[:] = np.searchsorted(keys, base + hz + tread, "right") > np.searchsorted(keys, base + hz - tread, "left")
        rest = np.flatnonzero(~out)
        if not len(rest):
            return out
        from scipy.ndimage import binary_closing, distance_transform_edt
        low, high = -(1.0 + TREAD / 2) * 10, BODY[0] * 10
        fw = np.flatnonzero(walk[owner])
        order = fw[np.argsort(cell[fw], kind="stable")]
        sorted_cell = cell[order]
        pairs = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                near = (cr[rest].astype(np.int64) + dr) * self.w + cc2[rest] + dc
                ok = (cr[rest] + dr >= 0) & (cr[rest] + dr < self.h) & (cc2[rest] + dc >= 0) & (cc2[rest] + dc < self.w)
                a, b = np.searchsorted(sorted_cell, near, "left"), np.searchsorted(sorted_cell, near, "right")
                n = np.where(ok, b - a, 0)
                which = np.repeat(np.arange(len(rest)), n)
                at = order[np.repeat(a, n) + np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)]
                dz = z10[at] - hz[rest][which]
                band = (dz >= low) & (dz <= high)
                pairs.append(which[band] * len(tris) + owner[at[band]])
        pairs = np.unique(np.concatenate(pairs))
        which, tri = pairs // len(tris), pairs % len(tris)
        pad = BODY_WIDTH / 2 + FINE
        k = int(round((self.res + 2 * pad) / FINE))
        g = (np.arange(k) + 0.5) * FINE - pad
        on = np.zeros((len(rest), k, k), bool)
        t3 = tris.astype(np.float64)
        for s in range(0, len(pairs), 2000):
            i, t = which[s:s + 2000], tri[s:s + 2000]
            p = np.stack(np.broadcast_arrays((self.top - cr[rest][i] * self.res)[:, None, None] - g[None, :, None],
                                             (self.left - cc2[rest][i] * self.res)[:, None, None] - g[None, None, :]), -1)
            A, B, C = (t3[t, j][:, None, None, :] for j in range(3))
            area = turn(A, B, C)
            area = np.where(np.abs(area) < 1e-12, np.nan, area)
            with np.errstate(invalid="ignore"):
                wa, wb, wc = turn(B, C, p) / area, turn(C, A, p) / area, turn(A, B, p) / area
                z = (wa * A[..., 2] + wb * B[..., 2] + wc * C[..., 2] - self.zmin) * 10 - hz[rest][i][:, None, None]
                hit = (wa >= -1e-9) & (wb >= -1e-9) & (wc >= -1e-9) & (z >= low) & (z <= high)
            first, start = np.unique(i, return_index=True)
            on[first] |= np.logical_or.reduceat(hit, start, axis=0)
        gap = int(math.ceil(GAP / 2 / FINE))
        disk = np.hypot(*np.mgrid[-gap:gap + 1, -gap:gap + 1]) <= gap
        on = binary_closing(np.pad(on, ((0, 0), (gap, gap), (gap, gap))), disk[None])[:, gap:-gap, gap:-gap]
        edge = distance_transform_edt(np.pad(on, ((0, 0), (1, 1), (1, 1))), sampling=(1e6, 1.0, 1.0))[:, 1:-1, 1:-1]
        inside = (g >= 0) & (g < self.res)
        room = edge[:, inside][:, :, inside] * FINE - FINE / 2
        out[rest] = (room >= BODY_WIDTH / 2).reshape(len(rest), -1).any(axis=1)
        return out

    def climbs(self, ra, ca, rb, cb, low, high):
        k = len(ra)
        cells = np.concatenate([ra * self.w + ca, rb * self.w + cb]).astype(np.int64) * 100000
        pair = np.tile(np.arange(k), 2)
        lo = np.round((np.tile(low, 2) - 0.4 - self.zmin) * 10).astype(np.int64)
        hi = np.round((np.tile(high, 2) + 0.4 - self.zmin) * 10).astype(np.int64)
        first = np.searchsorted(self.floors, cells + lo, "left")
        count = np.searchsorted(self.floors, cells + hi, "right") - first
        at = np.repeat(first, count) + np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
        z, of = self.floors[at] - np.repeat(cells, count), np.repeat(pair, count)
        order = np.lexsort((z, of))
        z, of = z[order], of[order]
        tallest = np.zeros(k, np.int64)
        same = of[1:] == of[:-1]
        np.maximum.at(tallest, of[1:][same], np.diff(z)[same])
        return (np.bincount(of, minlength=k) > 0) & (tallest <= round(STEP_UP * 10))

    def standing(self):
        return Layers.from_arrays(self.heights, self.swim, self.top, self.left, self.res)

    @classmethod
    def from_arrays(cls, heights, swim, top, left, res):
        self = cls.__new__(cls)
        self.heights, self.swim = heights, swim
        self.top, self.left, self.res = float(top), float(left), float(res)
        self.h, self.w = heights.shape[:2]
        self.index_nodes()
        return self

    def index_nodes(self):
        valid = ~np.isnan(self.heights)
        self.index = np.full(self.heights.shape, -1, np.int64)
        self.index[valid] = np.arange(valid.sum())
        self.nodes = np.argwhere(valid)

    def cell(self, north, west):
        return (np.floor((self.top - north) / self.res).astype(int), np.floor((self.left - west) / self.res).astype(int))

    def world(self, r, c):
        return self.top - (r + 0.5) * self.res, self.left - (c + 0.5) * self.res

    def graph(self):
        self.index_nodes()
        index = self.index
        h, w = self.h, self.w
        rows, cols, data = [], [], []
        up = math.tan(math.radians(getattr(self, "max_up", MAX_UP)))
        slack = 0.75 if getattr(self, "max_up", MAX_UP) > MAX_UP else 0.25
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            dist = self.res * (math.sqrt(2) if dr and dc else 1)
            rs, cs = slice(max(0, -dr), h - max(0, dr)), slice(max(0, -dc), w - max(0, dc))
            rt, ct = slice(max(0, dr), h - max(0, -dr)), slice(max(0, dc), w - max(0, -dc))
            for la in range(LAYERS):
                ha, sa, ia = self.heights[rs, cs, la], self.swim[rs, cs, la], index[rs, cs, la]
                if not (ia >= 0).any():
                    continue
                for lb in range(LAYERS):
                    hb, sb, ib = self.heights[rt, ct, lb], self.swim[rt, ct, lb], index[rt, ct, lb]
                    rise = hb - ha
                    ok = (ia >= 0) & (ib >= 0) & (
                        (sa & sb & (np.abs(rise) <= dist * 2)) |
                        (~sb & (rise <= dist * max(up, STEP) + slack) & (-rise <= MAX_DROP)) |
                        (sb & ~sa & (rise <= 0.5) & (-rise <= MAX_DROP)))
                    if not ok.any():
                        continue
                    if hasattr(self, "walls_fine"):
                        oi, oj = np.nonzero(ok)
                        ra, ca = oi + rs.start, oj + cs.start
                        across = self.crossing(ra, ca, dr, dc, np.maximum(ha[oi, oj], hb[oi, oj]))
                        ok[oi[across], oj[across]] = False
                        if not ok.any():
                            continue
                    if hasattr(self, "floors"):
                        oi, oj = np.nonzero(ok & ~sa & ~sb & (rise > STEP_UP - 0.75))
                        if len(oi):
                            ra, ca = oi + rs.start, oj + cs.start
                            bare = ~self.climbs(ra, ca, ra + dr, ca + dc, ha[oi, oj], hb[oi, oj])
                            ok[oi[bare], oj[bare]] = False
                    rows.append(ia[ok]); cols.append(ib[ok])
                    data.append(np.where(sa[ok] | sb[ok], SWIM_COST, 1.0) * dist)
        self.falls(rows, cols, data)
        self.jumps(rows, cols, data)
        for lw in range(LAYERS):
            for lf in range(LAYERS):
                if lf == lw:
                    continue
                iw, jf = index[:, :, lw], index[:, :, lf]
                ok = (iw >= 0) & (jf >= 0) & self.swim[:, :, lw] & (self.heights[:, :, lf] < self.heights[:, :, lw])
                if ok.any() and hasattr(self, "floors_fine"):
                    oi, oj = np.nonzero(ok)
                    shut = ~self.open_between(oi, oj, self.heights[oi, oj, lf], self.heights[oi, oj, lw])
                    ok[oi[shut], oj[shut]] = False
                if ok.any():
                    depth = (self.heights[:, :, lw] - self.heights[:, :, lf])[ok] * SWIM_COST
                    rows += [iw[ok], jf[ok]]; cols += [jf[ok], iw[ok]]; data += [depth, depth]
        n = len(self.nodes)
        if not rows:
            return csr_matrix((n, n))
        return priced(self, csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)))

    def jumps(self, rows, cols, data):
        if not rows:
            return
        n = len(self.nodes)
        out_degree = np.bincount(np.concatenate(rows), minlength=n)
        ledges = np.flatnonzero(out_degree < 8)
        if not len(ledges):
            return
        hh = self.heights
        lr, lc, ll = self.nodes[ledges].T
        la = hh[lr, lc, ll]
        for dr in range(-WATER_JUMP_REACH, WATER_JUMP_REACH + 1):
            for dc in range(-WATER_JUMP_REACH, WATER_JUMP_REACH + 1):
                dist = math.hypot(dr, dc)
                if dist < 1.5 or dist > WATER_JUMP_REACH + 0.5:
                    continue
                onto_ground = dist <= JUMP_REACH + 0.5
                tr, tc = lr + dr, lc + dc
                inside = (tr >= 0) & (tr < self.h) & (tc >= 0) & (tc < self.w)
                src, tr, tc, ha = ledges[inside], tr[inside], tc[inside], la[inside]
                for lb in range(LAYERS):
                    hb = hh[tr, tc, lb]
                    drop = ha - hb
                    into_water = self.swim[tr, tc, lb] & (drop <= WATER_JUMP_DROP)
                    ok = ~np.isnan(hb) & (drop > MAX_DROP) & (((drop <= JUMP_DROP) & onto_ground) | into_water)
                    if not ok.any():
                        continue
                    s2, r2, c2, a2, b2 = src[ok], tr[ok], tc[ok], ha[ok], hb[ok]
                    clear = ~self.sweep(r2 - dr, c2 - dc, dr, dc, a2, b2)
                    if not clear.any():
                        continue
                    target = self.index[r2[clear], c2[clear], lb]
                    rows.append(s2[clear]); cols.append(target)
                    data.append(np.full(int(clear.sum()), dist * self.res))

    def falls(self, rows, cols, data):
        if not rows:
            return
        r, c, d = np.concatenate(rows), np.concatenate(cols), np.concatenate(data)
        n, nodes = len(self.nodes), self.nodes
        z = self.heights[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
        down = np.flatnonzero(z[c] < z[r])
        made = np.sort(r.astype(np.int64) * n + c)
        back = c[down].astype(np.int64) * n + r[down]
        fall = down[made[np.searchsorted(made, back).clip(0, len(made) - 1)] != back]
        keep = np.ones(len(r), bool)
        dr, dc = nodes[c[fall], 0] - nodes[r[fall], 0], nodes[c[fall], 1] - nodes[r[fall], 1]
        for sr, sc in {(int(a), int(b)) for a, b in zip(dr, dc)}:
            k = fall[(dr == sr) & (dc == sc)]
            keep[k[self.sweep(nodes[r[k], 0], nodes[r[k], 1], sr, sc, z[r[k]], z[c[k]])]] = False
        rows[:], cols[:], data[:] = [r[keep]], [c[keep]], [d[keep]]

    def near(self, north, west, z=None, radius=3, every=False):
        r0, c0 = self.cell(np.array([north]), np.array([west]))
        r0, c0 = int(r0[0]), int(c0[0])
        found = []
        for rad in range(radius + 1):
            for r in range(r0 - rad, r0 + rad + 1):
                for c in range(c0 - rad, c0 + rad + 1):
                    if max(abs(r - r0), abs(c - c0)) != rad or not (0 <= r < self.h and 0 <= c < self.w):
                        continue
                    for l in range(LAYERS):
                        i = self.index[r, c, l]
                        if i >= 0 and within(self.heights[r, c, l], z):
                            found.append(int(i))
            if found and not every:
                return found
        return found


def hop_down(across):
    return across * STEP + 0.75


def priced(layers, graph):
    nodes = layers.nodes
    r, c = nodes[:, 0].astype(np.int32), nodes[:, 1].astype(np.int32)
    rows, cols = np.repeat(np.arange(len(nodes), dtype=np.int32), np.diff(graph.indptr)), graph.indices
    dr, dc = r[cols] - r[rows], c[cols] - c[rows]
    height = layers.heights[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
    jump = (np.abs(dr) > 1) | (np.abs(dc) > 1)
    d = np.flatnonzero(jump | (height[rows] - height[cols] > hop_down(layers.res)))
    rows, cols, jump = rows[d], cols[d], jump[d]
    across = np.hypot(dr[d], dc[d]) * layers.res
    hop = ~jump & (across > 0) & (height[rows] - height[cols] > hop_down(across))
    k = np.flatnonzero(hop)
    if len(k):
        hop[k[np.asarray(graph[cols[k], rows[k]]).ravel() > 0]] = False
    drop = jump | hop
    if not drop.any():
        return graph
    swim = layers.swim[nodes[:, 0], nodes[:, 1], nodes[:, 2]]
    wet = hop & (swim[rows] | swim[cols])
    data = graph.data.copy()
    data[d[drop]] = (np.where(wet, SWIM_COST, 1.0) * across + DROP_COST)[drop]
    return csr_matrix((data, graph.indices, graph.indptr), shape=graph.shape)


def find_path(layers, graph, start, goal, start_z=None, goal_z=None):
    sources = layers.near(*start, start_z) or layers.near(*start, None, radius=6)
    targets = layers.near(*goal, goal_z) or layers.near(*goal, None, radius=6)
    if not sources:
        return None
    dist, pred, _ = dijkstra(graph, indices=sources, return_predecessors=True, min_only=True)
    reach = [t for t in targets if np.isfinite(dist[t])]
    partial = not reach
    if reach:
        end = min(reach, key=lambda t: dist[t])
    else:
        ok = np.flatnonzero(np.isfinite(dist))
        rr, cc = layers.nodes[ok, 0], layers.nodes[ok, 1]
        gr, gc = layers.cell(np.array([goal[0]]), np.array([goal[1]]))
        end = int(ok[np.argmin((rr - gr[0]) ** 2 + (cc - gc[0]) ** 2)])
    chain = [end]
    while pred[chain[-1]] >= 0:
        chain.append(int(pred[chain[-1]]))
    chain.reverse()
    keep = straighten(layers, graph, chain)
    pts = []
    for i in keep[1:]:
        r, c, l = layers.nodes[i]
        n, w = layers.world(r, c)
        pts.append([round(n, 1), round(w, 1), round(float(layers.heights[r, c, l]), 1)])
    if pts and not partial:
        pts[-1][:2] = [round(goal[0], 1), round(goal[1], 1)]
    gap = None
    if partial:
        end = pts[-1] if pts else start
        gap = round(math.hypot(goal[0] - end[0], goal[1] - end[1]))
        pts.append([round(goal[0], 1), round(goal[1], 1)])
    length, prev = 0.0, start
    for p in pts:
        length += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    out = {"points": pts, "length": round(length), "partial": partial}
    if partial:
        out["gap"] = gap
    return out


def straighten(layers, graph, chain, hot=None):
    indptr, indices = graph.indptr, graph.indices
    nodes, heights = layers.nodes, layers.heights

    swim = layers.swim

    def drop(a, b):
        ra, ca, la = nodes[a]
        rb, cb, lb = nodes[b]
        across = math.hypot(int(rb) - int(ra), int(cb) - int(ca)) * layers.res
        return bool(heights[ra, ca, la] - heights[rb, cb, lb] > hop_down(across)) and \
            not (indices[indptr[b]:indptr[b + 1]] == a).any()

    def walk_ok(a, b):
        ra, ca, la = nodes[a]
        rb, cb, lb = nodes[b]
        ha, hb = heights[ra, ca, la], heights[rb, cb, lb]
        wet = swim[ra, ca, la] or swim[rb, cb, lb]
        mobs = max(hot[a], hot[b]) if hot is not None else None
        n = max(abs(rb - ra), abs(cb - ca))
        cur = a
        for k in range(1, n + 1):
            r, c = round(ra + (rb - ra) * k / n), round(ca + (cb - ca) * k / n)
            want = ha + (hb - ha) * k / n
            best, best_d = -1, 1e9
            for j in indices[indptr[cur]:indptr[cur + 1]]:
                if nodes[j, 0] == r and nodes[j, 1] == c and (wet or not swim[r, c, nodes[j, 2]]) and not drop(cur, j):
                    d = abs(heights[r, c, nodes[j, 2]] - want)
                    if d < best_d:
                        best, best_d = j, d
            if best < 0 or (mobs is not None and hot[best] > mobs + 1e-6):
                return False
            cur = best
        return cur == b
    if len(chain) < 3:
        return chain
    out, i = [chain[0]], 0
    while i < len(chain) - 1:
        j = min(len(chain) - 1, i + 80)
        while j > i + 1 and not walk_ok(chain[i], chain[j]):
            j -= 1 if j - i < 12 else max(1, (j - i) // 4)
        out.append(chain[j])
        i = j
    return out
