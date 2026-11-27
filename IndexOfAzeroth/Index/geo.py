# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import datafiles


def to_world(w, fx, fy):
    return w["top"] - fy * (w["top"] - w["bottom"]), w["left"] - fx * (w["left"] - w["right"])


def to_map(w, north, west):
    return (w["left"] - west) / (w["left"] - w["right"]), (w["top"] - north) / (w["top"] - w["bottom"])


def seg_yards(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / max(ab[0] ** 2 + ab[1] ** 2, 1e-9)))
    return math.hypot(p[0] - a[0] - t * ab[0], p[1] - a[1] - t * ab[1])


def height_of(p):
    if len(p) > 2 and p[2] is not None:
        z = float(p[2])
        return z if math.isfinite(z) else None
    return None


def reach_yards(p, q):
    a, b = height_of(p), height_of(q)
    flat = math.hypot(p[0] - q[0], p[1] - q[1])
    return flat if a is None or b is None else math.hypot(flat, a - b)


def line_reach(p, a, b):
    hs = [height_of(x) for x in (p, a, b)]
    if None in hs:
        return seg_yards(p, a, b)
    ab = (b[0] - a[0], b[1] - a[1], hs[2] - hs[1])
    ap = (p[0] - a[0], p[1] - a[1], hs[0] - hs[1])
    t = max(0.0, min(1.0, sum(u * v for u, v in zip(ap, ab)) / max(sum(u * u for u in ab), 1e-9)))
    return math.sqrt(sum((u - t * v) ** 2 for u, v in zip(ap, ab)))


class MapGeometry:
    def __init__(self):
        maps = datafiles.load(datafiles.data_path("maps.json"), {}).get("maps", {})
        self.maps = {int(k): v for k, v in maps.items()}
        self.area_map = {}
        for map_id, m in sorted(self.maps.items(), key=lambda kv: -kv[1]["type"]):
            if m["area"] and m["type"] >= 3:
                self.area_map.setdefault(str(m["area"]), map_id)

    def to_world(self, map_id, fx, fy):
        m = self.maps.get(map_id)
        if not m or "world" not in m:
            return None
        return (*to_world(m["world"], fx, fy), m["instance"])

    def area_to_world(self, area, x, y):
        map_id = self.area_map.get(str(area))
        return self.to_world(map_id, x / 100, y / 100) if map_id else None

    def project(self, area, points, player_map, margin):
        return self.project_from(self.area_map.get(str(area)), points, player_map, margin)

    def project_from(self, map_id, points, player_map, margin):
        src, dst = self.maps.get(map_id), self.maps.get(player_map)
        if not src or not dst or src["instance"] != dst["instance"]:
            return []
        out = []
        for x, y in points:
            fx, fy = to_map(dst["world"], *to_world(src["world"], x / 100, y / 100))
            if -margin <= fx <= 1 + margin and -margin <= fy <= 1 + margin:
                out.append((round(fx, 4), round(fy, 4)))
        return out
