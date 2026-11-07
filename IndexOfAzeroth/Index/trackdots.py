# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import math
import os
import sys
import threading
import time

import cv2
import numpy as np

import jsontext
import signals
import store
import storewriter
from mapzones import world_pos

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "trackdots.json")

USAGE = ("  python trackdots.py capture OUT.png   the live game's minimap saved as a picture for the tests, refused in an "
         "instance")
ON = True

GATHER_SPELLS = {"Find Minerals": "mining", "Find Herbs": "herbalism"}
GATHER_IDS = {2580: "mining", 8388: "mining", 2383: "herbalism", 8387: "herbalism"}

RATE = 0.25
MIN_SIDE = 40
TRACKING_FRESH = 8.0
DOT_RED, DOT_GREEN, DOT_BLUE, DOT_SPREAD = 200, 140, 100, 130
DOT_MIN_PX = 3
DOT_MIN, DOT_MAX = 0.02, 0.10
CENTER_SHARE = 0.07
EDGE = 2
TRACK_FORGET = 3.0
STILL_READINGS = 8
STILL_SECONDS = 2.5
MOVE_YARDS = 5.0
NEW_SAME = 8.0
VIEW_SHARE = 0.85
PASS_READINGS = 4
PASS_GAP = 120.0
EMPTY_PASSES = 5
NEW_MOST = 2000


def spot_yards(ypp):
    return 5.0 + ypp


def track_yards(ypp):
    return 3.0 + 2.0 * ypp


def still_yards(ypp):
    return 2.0 + 1.5 * ypp


_kinds = None


def gather_kinds():
    global _kinds
    if _kinds is None:
        found = dict(GATHER_IDS)
        try:
            import client
            for row in client.rows("SpellName", stored=True):
                layer = GATHER_SPELLS.get(row.get("Name_lang") or row.get("Name"))
                if layer and row.get("ID"):
                    found[int(row["ID"])] = layer
        except Exception:
            pass
        _kinds = found
    return _kinds


def gate(state, tracking, kinds, now):
    if not state:
        return None, "no position from the game"
    flags = state.get("flags") or {}
    if flags.get("instance"):
        return None, "inside an instance"
    inst = state.get("instance")
    if not inst or inst.get("kind") is not None or inst.get("id") is None:
        return None, "the addon didn't say you're outside an instance"
    if flags.get("taxi") or flags.get("ghost") or flags.get("dead"):
        return None, "on a flight or dead"
    mm = state.get("minimap")
    if not mm or not mm.get("shown") or min(mm.get("w") or 0, mm.get("h") or 0) < MIN_SIDE:
        return None, "no minimap on screen"
    tr, came = tracking or (None, None)
    if not tr or now - came > TRACKING_FRESH or tr.get("on") is None or tr.get("more") or not tr.get("radius"):
        return None, "the addon didn't say what's tracked"
    if tr.get("zoom") != mm.get("zoom") or tr.get("indoors") != mm.get("indoors"):
        return None, "the minimap's zoom changed since the addon said its reach"
    layers = set()
    for t in tr["on"]:
        if t.get("spell"):
            layer = kinds.get(t.get("id"))
            if not layer:
                return None, "another tracking spell is on"
            layers.add(layer)
    if not layers:
        return None, "neither Find Minerals nor Find Herbs is on"
    pos = state.get("pos")
    if not pos or not state.get("map") or not world_pos(state["map"], pos["x"], pos["y"]):
        return None, "no position from the game"
    if mm.get("rotate") and state.get("facing") is None:
        return None, "the minimap turns and the game didn't say which way you face"
    return layers, None


_masks = {}


def read_mask(w, h, square):
    key = (w, h, square)
    if key not in _masks:
        yy, xx = np.ogrid[0:h, 0:w]
        side, cx, cy = min(w, h), (w - 1) / 2, (h - 1) / 2
        r = np.hypot(xx - cx, yy - cy)
        keep = r > side * CENTER_SHARE
        if square:
            keep = keep & (xx >= EDGE) & (xx < w - EDGE) & (yy >= EDGE) & (yy < h - EDGE)
        else:
            keep = keep & (r < side / 2 - EDGE)
        _masks.clear()
        _masks[key] = keep
    return _masks[key]


def yellow_of(bgra, w, h, square=False):
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)
    b, g, r = img[..., 0].astype(np.int16), img[..., 1].astype(np.int16), img[..., 2].astype(np.int16)
    yellow = (r >= DOT_RED) & (g >= DOT_GREEN) & (g <= r) & (b <= DOT_BLUE) & (r - b >= DOT_SPREAD)
    return (yellow & read_mask(w, h, square)).astype(np.uint8)


def find_dots(bgra, w, h, square=False, mask=None):
    mask = yellow_of(bgra, w, h, square) if mask is None else mask
    if not mask.any():
        return []
    count, _, stats, centres = cv2.connectedComponentsWithStats(mask, connectivity=8)
    side = min(w, h)
    lo, hi = max(DOT_MIN_PX, side * DOT_MIN), side * DOT_MAX
    out = []
    for i in range(1, count):
        _, _, bw, bh, area = (int(v) for v in stats[i])
        if not (lo <= bw <= hi and lo <= bh <= hi) or max(bw, bh) > 1.5 * min(bw, bh) or area < 0.5 * bw * bh:
            continue
        out.append((float(centres[i][0] - (w - 1) / 2), float(centres[i][1] - (h - 1) / 2), max(bw, bh)))
    return out


def to_world(north, west, right, down, ypp, facing):
    up, right = -down * ypp, right * ypp
    c, s = math.cos(facing), math.sin(facing)
    return north + up * c + right * s, west + up * s - right * c


def to_pixel(north, west, at, ypp, facing):
    dn, dw = at[0] - north, at[1] - west
    c, s = math.cos(facing), math.sin(facing)
    return (s * dn - c * dw) / ypp, -(c * dn + s * dw) / ypp


def yellow_near(mask, right, down, pixels):
    h, w = mask.shape
    x, y = (w - 1) / 2 + right, (h - 1) / 2 + down
    x0, x1 = max(0, int(x - pixels)), min(w, int(x + pixels) + 1)
    y0, y1 = max(0, int(y - pixels)), min(h, int(y + pixels) + 1)
    return x0 < x1 and y0 < y1 and int(mask[y0:y1, x0:x1].sum()) >= 2


def spot_name(key):
    layer, inst, n, w = key
    return f"{layer}:{inst}:{n:.1f}:{w:.1f}"


class DotReader:

    def __init__(self, hub=None, grabber=None, path=PATH, world=None, build=None, changed=None, kinds=None):
        self.hub, self.grabber, self.path = hub, grabber, path
        self.world = world or (lambda: hub.world)
        self.build = build or installed_build
        self.changed = changed or (lambda: None)
        self.kinds = kinds or gather_kinds
        self.lock = threading.Lock()
        self.data = self.load()
        self.tracks, self.passes, self.track_inst = [], {}, None
        self.indexes = {}
        self.problem = None
        self.timing = []


    def load(self):
        data = store.load_json(self.path, {})
        spots = data.get("spots") or {}
        for s in spots.values():
            if s.get("marked") and s.get("empty", 0) < EMPTY_PASSES:
                s["marked"] = False
        return {"build": data.get("build"), "spots": spots, "new": data.get("new") or []}

    def save(self):
        data = json.loads(json.dumps(self.data))
        storewriter.save_json_later(self.path, lambda: data, indent=None)

    def emptied(self):
        with self.lock:
            return {(s["layer"], s["inst"], s["n"], s["w"]) for s in self.data["spots"].values() if s.get("marked")}

    def same_build(self):
        build = self.build()
        if not build:
            return False
        if build != self.data["build"]:
            had = any(s.get("marked") for s in self.data["spots"].values())
            self.data["build"], self.data["spots"] = build, {}
            self.passes.clear()
            self.save()
            if had:
                self.changed()
        return True


    def index(self, layer):
        world = self.world()
        table = getattr(world, "nodes_full", None) or world.nodes
        key = (id(table), layer)
        if key not in self.indexes:
            from scipy.spatial import cKDTree
            found = {}
            for node in table.get(layer, ()):
                for area, pts in node["s"].items():
                    for x, y in pts:
                        k = world.spot_key(layer, area, x, y)
                        if k:
                            found.setdefault(k[1], set()).add(k)
            self.indexes = {k: v for k, v in self.indexes.items() if k[0] == id(table)}
            self.indexes[key] = {inst: (cKDTree(np.array([k[2:] for k in keys])), keys)
                                 for inst, keys in ((i, sorted(ks)) for i, ks in found.items())}
        return self.indexes[key]

    def near_spots(self, layers, inst, at, yards):
        out = []
        for layer in layers:
            tree, keys = self.index(layer).get(inst, (None, ()))
            if tree is None:
                continue
            for i in tree.query_ball_point(at, yards):
                out.append((math.hypot(keys[i][2] - at[0], keys[i][3] - at[1]), keys[i]))
        return sorted(out)


    def step(self, state, tr, bgra, now, layers):
        mm = state["minimap"]
        w, h = mm["w"], mm["h"]
        side = min(w, h)
        ypp = tr["radius"] / (side / 2)
        inst, pn, pw = world_pos(state["map"], state["pos"]["x"], state["pos"]["y"])
        facing = (state.get("facing") or 0.0) if mm.get("rotate") else 0.0
        mask = yellow_of(bgra, w, h, tr.get("shape") == "square")
        dots = [to_world(pn, pw, dx, dy, ypp, facing) for dx, dy, _ in find_dots(bgra, w, h, mask=mask)]
        yellow = lambda at: yellow_near(mask, *to_pixel(pn, pw, at, ypp, facing), spot_yards(ypp) / ypp)
        with self.lock:
            what = (inst, tuple(sorted(layers)))
            if what != self.track_inst:
                self.tracks, self.passes, self.track_inst = [], {}, what
            standing = self.follow(dots, (pn, pw), now, ypp)
            changed = False
            for t in standing:
                changed |= self.place(t, inst, layers, now, ypp)
            if mm.get("indoors"):
                self.passes.clear()
            else:
                changed |= self.look(yellow, inst, (pn, pw), layers, now, tr["radius"], ypp)
        if changed:
            self.save()
            self.changed()
        return {"dots": dots, "standing": [(t["n"], t["w"]) for t in standing]}

    def follow(self, dots, here, now, ypp):
        self.tracks = [t for t in self.tracks if now - t["last"] <= TRACK_FORGET]
        out, taken = [], set()
        for n, w in dots:
            best = min(((math.hypot(t["n"] - n, t["w"] - w), i) for i, t in enumerate(self.tracks) if i not in taken),
                       default=(None, None))
            if best[0] is None or best[0] > track_yards(ypp):
                self.tracks.append({"n": n, "w": w, "fn": n, "fw": w, "sn": n, "sw": w, "k": 1, "first": now, "last": now,
                                    "here": here, "moved": 0.0, "wandered": False, "standing": False})
                taken.add(len(self.tracks) - 1)
                continue
            t = self.tracks[best[1]]
            taken.add(best[1])
            if math.hypot(t["fn"] - n, t["fw"] - w) > still_yards(ypp):
                t["wandered"] = True
            t["sn"], t["sw"], t["k"], t["last"] = t["sn"] + n, t["sw"] + w, t["k"] + 1, now
            t["n"], t["w"] = t["sn"] / t["k"], t["sw"] / t["k"]
            t["moved"] = max(t["moved"], math.hypot(here[0] - t["here"][0], here[1] - t["here"][1]))
            if (not t["standing"] and not t["wandered"] and t["k"] >= STILL_READINGS and now - t["first"] >= STILL_SECONDS
                    and t["moved"] >= MOVE_YARDS):
                t["standing"] = True
                out.append(t)
        return out

    def place(self, t, inst, layers, now, ypp):
        near = self.near_spots(layers, inst, (t["n"], t["w"]), spot_yards(ypp))
        if near:
            key = near[0][1]
            s = self.spot(key)
            s["seen"], s["empty"] = round(now), 0
            self.passes.pop(key, None)
            if s.get("marked"):
                s["marked"] = False
                return True
            return False
        self.new_spot(sorted(layers), inst, t["n"], t["w"], now)
        return False

    def spot(self, key):
        return self.data["spots"].setdefault(spot_name(key), {"layer": key[0], "inst": key[1], "n": key[2], "w": key[3],
                                                              "empty": 0, "emptyAt": None, "seen": None, "marked": False})

    def new_spot(self, layers, inst, n, w, now):
        for s in self.data["new"]:
            if s["inst"] == inst and math.hypot(s["n"] - n, s["w"] - w) <= NEW_SAME:
                s["last"], s["count"] = round(now), s["count"] + 1
                return
        s = {"layers": layers, "inst": inst, "n": round(n, 1), "w": round(w, 1), "first": round(now), "last": round(now), "count": 1}
        self.data["new"] = (self.data["new"] + [s])[-NEW_MOST:]
        self.save()
        signals.send("trackdot", layers=layers, inst=inst, n=s["n"], w=s["w"], at=s["first"])

    def look(self, yellow, inst, here, layers, now, radius, ypp):
        reach, close = radius * VIEW_SHARE, radius * 2 * CENTER_SHARE + spot_yards(ypp)
        seen = set()
        for d, key in self.near_spots(layers, inst, here, reach):
            if d < close:
                continue
            seen.add(key)
            p = self.passes.setdefault(key, {"k": 0, "dot": False})
            p["k"] += 1
            if not p["dot"] and yellow(key[2:]):
                p["dot"] = True
        changed = False
        for key in [k for k in self.passes if k not in seen]:
            p = self.passes.pop(key)
            if p["k"] < PASS_READINGS or p["dot"]:
                continue
            s = self.spot(key)
            if s["emptyAt"] is not None and now - s["emptyAt"] < PASS_GAP:
                continue
            s["empty"], s["emptyAt"] = s["empty"] + 1, round(now)
            self.save()
            if s["empty"] >= EMPTY_PASSES and not s["marked"]:
                s["marked"] = changed = True
        return changed

    def stop_passes(self):
        with self.lock:
            self.passes.clear()


    def tick(self, now):
        hub = self.hub
        state = hub.state if hub else None
        tracking = getattr(hub, "tracking", None)
        layers, why = gate(state, tracking, self.kinds(), now)
        if layers is None or not self.same_build():
            self.problem = why or "the client's build isn't known"
            self.stop_passes()
            return None
        mm = state["minimap"]
        bgra = self.grabber.grab(mm["x"], mm["y"], mm["w"], mm["h"]) if self.grabber else None
        if bgra is None:
            self.problem = "the game's window isn't there"
            self.stop_passes()
            return None
        self.problem = None
        return self.step(state, tracking[0], bgra, now, layers)

    def run(self):
        while True:
            started = time.perf_counter()
            try:
                self.tick(time.time())
            except Exception as e:
                self.problem = f"minimap reading failed: {e}"
            took = time.perf_counter() - started
            self.timing = (self.timing + [took])[-300:]
            time.sleep(max(0.02, RATE - took))


def installed_build():
    try:
        import game
        return game.played_version()
    except Exception:
        return None


def capture(out, wait=10.0):
    from capture import StripReader
    from protocol import StripError, parse_frame
    reader, state, tr, end = StripReader(), None, None, time.time() + wait
    while (state is None or tr is None) and time.time() < end:
        try:
            kind, data = parse_frame(reader.read()[1])
        except (StripError, ValueError, IndexError, KeyError):
            kind, data = None, None
        if kind == "position":
            state = data
        elif kind == "tracking":
            tr = data
        time.sleep(1 / 15)
    flags, inst = (state or {}).get("flags") or {}, (state or {}).get("instance")
    if not state or flags.get("instance") or not inst or inst.get("kind") is not None:
        print("no capture: inside an instance, or the game didn't say you're outside one")
        return 1
    mm = state.get("minimap")
    if not mm or not mm.get("shown"):
        print("no capture: no minimap on screen")
        return 1
    from capture import WindowRegion
    bgra = WindowRegion().grab(mm["x"], mm["y"], mm["w"], mm["h"])
    if bgra is None:
        print("no capture: the game's window isn't there")
        return 1
    img = np.frombuffer(bgra, np.uint8).reshape(mm["h"], mm["w"], 4)
    cv2.imwrite(out, img[..., :3])
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
        f.write(jsontext.dumps({**{k: state.get(k) for k in ("map", "pos", "facing", "minimap", "instance", "flags", "zone")}, "tracking": tr}, 1))
    print("saved", out)
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "capture":
        sys.exit(capture(sys.argv[2]))
    print(USAGE)
