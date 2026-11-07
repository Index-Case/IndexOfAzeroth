# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

import numpy as np

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(ROOT, "data", "dangerous.json")
REACH = 50.0
CAREFUL_MOST = 2


def along(pts, step):
    pts = [np.asarray(p[:2], float) for p in pts]
    out = pts[:1]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(np.hypot(*(b - a)) // step))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return [list(p) for p in out]


def words(m):
    level = "" if m.get("min") is None else str(m["min"]) if m.get("min") == m.get("max") or not m.get("max") else f"{m['min']}-{m['max']}"
    rank = (m.get("rank") or "Normal").lower()
    moves = (m.get("move") or "").lower()
    head = " ".join(w for w in (f"level {level}" if level else "", rank if rank != "normal" else "") if w)
    about = [head] + (["patrols"] if "patrol" in moves else [])
    return f"{m['name']} ({', '.join(a for a in about if a)})" + (f": {m['notes']}" if m.get("notes") else "")


class Dangerous:
    def __init__(self, path=FILE):
        self.path = path
        self.load()

    def load(self):
        data = store.load_json(self.path, {})
        self.mobs = data.get("mobs") or []
        self.points = [np.asarray(m.get("pins", []) + [p for line in m.get("lines", []) for p in along(line, REACH / 2)], float).reshape(-1, 2)
                       for m in self.mobs]
        self.boxes = [(p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()) if len(p) else None for p in self.points]

    def near(self, inst, pts, side, reach=REACH):
        if not pts or not self.mobs:
            return []
        looks = np.asarray(along(pts, reach / 2), float)
        lo, hi = looks.min(0) - reach, looks.max(0) + reach
        found = []
        for m, p, box in zip(self.mobs, self.points, self.boxes):
            if m.get("inst") != inst or (side and m.get("side") != side) or box is None:
                continue
            if box[1] < lo[0] or box[0] > hi[0] or box[3] < lo[1] or box[2] > hi[1]:
                continue
            d2 = ((looks[:, None, :] - p[None, :, :]) ** 2).sum(-1)
            if d2.min() <= reach * reach:
                found.append((not m.get("elite"), int(d2.min(1).argmin()), m))
        return [m for _, _, m in sorted(found, key=lambda f: (f[0], f[1]))]

    def span_notes(self, inst, spans, side):
        return [[words(m) for m in self.near(inst, span, side)] for span in spans or []]

    def careful(self, inst, pts, side):
        mobs = self.near(inst, pts, side)
        return "; ".join(words(m).replace(";", ",") for m in mobs[:CAREFUL_MOST]) or None
