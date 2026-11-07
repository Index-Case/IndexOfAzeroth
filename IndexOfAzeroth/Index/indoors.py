# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import clientfiles as wm
import client
import mainstores
import realign
import store

CACHE = mainstores.own("indoorcache")
MAIN = mainstores.path("indoorcache") if mainstores.main_data() else None
ADT_YARDS = 1600 / 3
Z_MARGIN = 6
BOX_MARGIN = 2


class Indoors:
    def __init__(self):
        self.lock = threading.Lock()
        self.maps = None
        self.index = None
        self.wdts = {}
        self.results = {}
        self.rooms = {}
        self.making = {}
        self.placed = {}

    def setup(self, index=True):
        with self.lock:
            if self.maps is None:
                self.maps = {int(r["ID"]): r for r in client.rows("Map", stored=wm.serving())}
            if index and self.index is None:
                self.index = wm.minimap_index()

    def around(self, instance, wx, wy, reach=0):
        row = self.maps.get(instance)
        if not row or not int(row["WdtFileDataID"] or 0):
            return []
        version = wm.installed_version()
        if instance not in self.wdts:
            self.wdts[instance] = wm.map_file(row, version)
        col, r = int(32 - wy / ADT_YARDS), int(32 - wx / ADT_YARDS)
        key = (instance, col, r, reach, version)
        if key not in self.placed:
            cells = [(col + dc, r + dr) for dr in range(-reach, reach + 1) for dc in range(-reach, reach + 1)]
            self.placed[key] = wm.tile_placements(self.wdts[instance], cells, version)
        return self.placed[key]

    def indoor_at(self, instance, wx, wy, wz):
        if wz is None:
            return False
        with wm.kept_only(wm.serving()):
            return self._indoor_at(instance, wx, wy, wz)

    def _indoor_at(self, instance, wx, wy, wz):
        self.setup(index=False)
        version = wm.installed_version()
        for place in self.around(instance, wx, wy, 0):
            fid, ox, oy, oz, yaw, _, box = place
            if not (box[0] - BOX_MARGIN <= wx <= box[1] + BOX_MARGIN and box[2] - BOX_MARGIN <= wy <= box[3] + BOX_MARGIN):
                continue
            a = math.radians(180 + yaw)
            dx, dy = wx - ox, wy - oy
            lx, ly, lz = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a), wz - oz
            key = (fid, version)
            if key not in self.rooms:
                try:
                    self.rooms[key] = wm.building_rooms(fid, version)
                except OSError:
                    continue
            if any(flags & wm.INDOOR_ROOM and g[0] <= lx <= g[3] and g[1] <= ly <= g[4] and g[2] - 1 <= lz <= g[5] + 1
                   for flags, g in self.rooms[key]):
                return True
        return False

    def find(self, instance, wx, wy, wz=None):
        self.setup()
        version = wm.installed_version()
        best = None
        for reach in (0, 1):
            for place in self.around(instance, wx, wy, reach):
                fid, ox, oy, oz, yaw, _, box = place
                if not (box[0] - BOX_MARGIN <= wx <= box[1] + BOX_MARGIN and box[2] - BOX_MARGIN <= wy <= box[3] + BOX_MARGIN):
                    continue
                a = math.radians(180 + yaw)
                dx, dy = wx - ox, wy - oy
                lx = dx * math.cos(a) + dy * math.sin(a)
                ly = -dx * math.sin(a) + dy * math.cos(a)
                lz = None if wz is None else wz - oz
                try:
                    groups = wm.building(fid, version)
                except OSError:
                    continue
                for g in groups:
                    inside = g[0] <= lx <= g[3] and g[1] <= ly <= g[4] and (lz is None or g[2] - Z_MARGIN <= lz <= g[5] + Z_MARGIN)
                    if inside:
                        size = (g[3] - g[0]) * (g[4] - g[1])
                        if best is None or size < best[0]:
                            best = (size, place)
            if best:
                break
        if not best:
            return None
        place = best[1]
        key = (instance, place[5])
        with self.lock:
            making = self.making.setdefault(key, threading.Lock())
        with making:
            if key not in self.results:
                self.results[key] = self.kept(instance, place[5], version)
            if self.results[key] is False:
                wmos, by_prefix = self.index
                pieces = wm.pieces_of([place], version, wmos, by_prefix)
                with realign.working("building pictures", (instance, wx, wy), when=any(
                        realign.kept_from_before(mainstores.standing(os.path.join(wm.CACHE, f"mm-{p[0]}.blp")))
                        for p in pieces)):
                    made = pieces and wm.compose(pieces, version, max_side=2048)
                if not made:
                    self.results[key] = None
                else:
                    image, world = made
                    os.makedirs(CACHE, exist_ok=True)
                    name = f"{instance}_{place[5]}.png"
                    part = os.path.join(CACHE, f"{name}.{threading.get_ident()}.part")
                    image.save(part, format="PNG", optimize=True)
                    os.replace(part, os.path.join(CACHE, name))
                    path = wmos.get(place[0], "")
                    self.results[key] = {"image": name, "world": world, "name": os.path.basename(path)[:-4] if path else ""}
                    store.save_json(os.path.join(CACHE, f"{instance}_{place[5]}.json"), {**self.results[key], "version": version})
            return self.results[key]

    @staticmethod
    def kept(instance, uid, version):
        name = f"{instance}_{uid}"
        folder = MAIN if MAIN and not os.path.isfile(os.path.join(CACHE, name + ".json")) else CACHE
        found = store.load_json(os.path.join(folder, name + ".json"), None)
        if not isinstance(found, dict) or found.get("version") != version or found.get("image") != name + ".png" \
                or not isinstance(found.get("world"), dict) or not os.path.isfile(os.path.join(folder, name + ".png")):
            return False
        return {"image": found["image"], "world": found["world"], "name": found.get("name", "")}
