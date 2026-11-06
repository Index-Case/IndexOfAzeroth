# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import io
import os
import struct
import threading

import numpy as np
from PIL import Image

import datafiles
import mainstores
import pictures
import store
from facts import MAP_CORNER, TILE_YARDS

HEIGHTS = mainstores.path("heights")
PER_TILE = 16
CELL = TILE_YARDS / PER_TILE
SAMPLES = 4
HEADER = struct.Struct("<HHffI")
COARSE_BOX = struct.Struct("<hh")
COARSE_FLAG = 1
CLEAR, FOGGED = 255, 0
WHOLE = 128


def coarse_box(instance, folder=None):
    try:
        with open(f"{folder or HEIGHTS}/{int(instance)}/coarse.bin", "rb") as f:
            raw = f.read()
    except (OSError, ValueError):
        return None
    if len(raw) < HEADER.size + COARSE_BOX.size:
        return None
    n, _, _, _, flags = HEADER.unpack_from(raw)
    if not n or not flags & COARSE_FLAG:
        return None
    col, row = COARSE_BOX.unpack_from(raw, HEADER.size)
    return col, row, n, (len(raw) - HEADER.size - COARSE_BOX.size) // (3 * n)


def part_rect(zone, part):
    art, world = zone["art"], zone["world"]
    u0, u1 = part["x"] / art["width"], (part["x"] + part["width"]) / art["width"]
    v0, v1 = part["y"] / art["height"], (part["y"] + part["height"]) / art["height"]
    across, down = world["left"] - world["right"], world["top"] - world["bottom"]
    return (world["top"] - v0 * down, world["top"] - v1 * down,
            world["left"] - u0 * across, world["left"] - u1 * across)


def on_grid(rect, box, samples=SAMPLES):
    north, south, west, east = rect
    col0, row0, _, _ = box
    at = lambda yards, first: round((MAP_CORNER - yards) / CELL * samples) - first * PER_TILE * samples
    return at(north, row0), at(south, row0), at(west, col0), at(east, col0)


def shape_on_grid(shape, rect, box, samples=SAMPLES):
    r0, r1, c0, c1 = on_grid(rect, box, samples)
    _, _, width, rows = box
    if r1 <= r0 or c1 <= c0:
        return None
    inside = np.asarray(Image.fromarray(shape).resize((c1 - c0, r1 - r0), Image.BOX)) >= WHOLE
    top, left = max(0, r0), max(0, c0)
    bottom, right = min(rows * samples, r1), min(width * samples, c1)
    if bottom <= top or right <= left:
        return None
    return top, left, inside[top - r0:bottom - r0, left - c0:right - c0]


_parts = {}
_parts_lock = threading.Lock()


def parts_of(maps):
    with _parts_lock:
        kept = _parts.get(id(maps))
        if kept and kept[0] is maps:
            return kept[1]
    by_file, on = {}, {}
    for mid, zone in maps.items():
        parts = (zone.get("art") or {}).get("overlays") or ()
        if not parts or not zone.get("world") or zone.get("instance") is None:
            continue
        for k, part in enumerate(parts):
            for row in part["files"]:
                for f in row:
                    if f:
                        by_file[int(f)] = (str(mid), k)
            on.setdefault(int(zone["instance"]), []).append((str(mid), k, part_rect(zone, part)))
    with _parts_lock:
        _parts.clear()
        _parts[id(maps)] = (maps, (by_file, on))
    return by_file, on


def explored_parts(files, maps):
    by_file, _ = parts_of(maps)
    return {by_file[int(f)] for f in files if int(f) in by_file}


class Shapes:

    def __init__(self, folder=None):
        self.folder = folder
        self.lock = threading.Lock()
        self.kept = {}

    def path(self, mid):
        return pictures.fogmask_path(mid, self.folder)

    def stamp(self, mid):
        path = self.path(mid)
        return store.stamp(path) if os.path.isfile(path) else None

    def __call__(self, mid, art):
        path, stamp = self.path(mid), self.stamp(mid)
        if stamp is None:
            return None
        with self.lock:
            kept = self.kept.get(path)
            if kept and kept[0] == stamp:
                return kept[1]
        try:
            with Image.open(path) as img:
                sheet = np.asarray(img.convert("L"))
        except (OSError, ValueError):
            return None
        places = pictures.fogmask_places(art)
        if sheet.shape[0] < sum(h for _, _, _, h in places):
            return None
        cut = [sheet[top:top + h, left:left + w] for left, top, w, h in places]
        with self.lock:
            self.kept[path] = (stamp, cut)
        return cut


def picture(files, instance, maps, box, shapes, samples=SAMPLES):
    _, on = parts_of(maps)
    seen = explored_parts(files, maps)
    _, _, width, rows = box
    hidden = np.zeros((rows * samples, width * samples), bool)
    shown = np.zeros_like(hidden)
    zone_shapes = {}
    for mid, k, rect in on.get(int(instance), ()):
        if mid not in zone_shapes:
            zone_shapes[mid] = shapes(mid, maps[mid]["art"])
        placed = zone_shapes[mid] and shape_on_grid(zone_shapes[mid][k], rect, box, samples)
        if placed:
            top, left, inside = placed
            into = shown if (mid, k) in seen else hidden
            into[top:top + inside.shape[0], left:left + inside.shape[1]] |= inside
    fogged = (hidden & ~shown).reshape(rows, samples, width, samples).mean((1, 3))
    return np.rint(CLEAR - fogged * (CLEAR - FOGGED)).astype(np.uint8)


def png(grey):
    out = io.BytesIO()
    Image.fromarray(grey, "L").save(out, "PNG")
    return out.getvalue()


class FogPictures:

    def __init__(self, folder=None, maps=None, shapes=None):
        self.folder = folder
        self.maps = maps or (lambda: datafiles.load(datafiles.data_path("maps.json")).get("maps", {}))
        self.shapes = shapes or Shapes()
        self.version = 0
        self.lock = threading.Lock()
        self.kept = {}

    def moved(self):
        with self.lock:
            self.version += 1

    def get(self, explored, key, instance):
        box = coarse_box(instance, self.folder)
        if not explored or box is None:
            return None
        maps, files = self.maps(), tuple(explored["files"])
        zones = sorted({mid for mid, _, _ in parts_of(maps)[1].get(int(instance), ())})
        made_from = (files, id(maps), box, tuple(self.shapes.stamp(mid) for mid in zones))
        with self.lock:
            kept = self.kept.get((key, int(instance)))
            if kept and kept[0] == made_from and kept[1] is maps:
                return kept[2]
        made = png(picture(files, instance, maps, box, self.shapes))
        with self.lock:
            self.kept[(key, int(instance))] = (made_from, maps, made)
        return made
