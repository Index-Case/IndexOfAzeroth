# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import math
import os
import threading
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
MAPS = os.path.join(ROOT, "data", "dungeonmaps")

ON = False

DIAMETER = {True: [300, 240, 180, 120, 80, 50], False: [466.67, 400, 333.33, 266.67, 200, 133.33]}
RATE = 0.25
MATCH_NEAR = 0.45
MATCH_FAR = 0.55
FIX_YARDS = 3.0
GROWTH = 5.0
LOST = 60.0
TOP_SPEED = 20.0
STALE = 15.0


class Reference:

    def __init__(self, image_path, world):
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        alpha = img[..., 3:4].astype(np.float32) / 255
        self.gray = (cv2.cvtColor(img[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255) * alpha[..., 0]
        self.world = world
        self.ppy = self.gray.shape[1] / (world["left"] - world["right"])
        self.scaled = {}

    def at(self, ppy):
        key = round(ppy, 3)
        if key not in self.scaled:
            f = ppy / self.ppy
            size = (max(1, int(self.gray.shape[1] * f)), max(1, int(self.gray.shape[0] * f)))
            self.scaled = dict(list(self.scaled.items())[-1:])
            self.scaled[key] = cv2.resize(self.gray, size, interpolation=cv2.INTER_AREA)
        return self.scaled[key]

    def to_px(self, wx, wy, ppy):
        return (self.world["left"] - wy) * ppy, (self.world["top"] - wx) * ppy

    def to_world(self, col, row, ppy):
        return self.world["top"] - row / ppy, self.world["left"] - col / ppy


def window(img, a0, a1, b0, b1):
    out = np.zeros((a1 - a0, b1 - b0), img.dtype)
    ra0, ra1, rb0, rb1 = max(a0, 0), min(a1, img.shape[0]), max(b0, 0), min(b1, img.shape[1])
    if ra0 < ra1 and rb0 < rb1:
        out[ra0 - a0:ra1 - a0, rb0 - b0:rb1 - b0] = img[ra0:ra1, rb0:rb1]
    return out


def prepare(bgra, w, h):
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)
    bgr = img[..., :3]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - (w - 1) / 2, yy - (h - 1) / 2)
    side = min(w, h)
    mask = (r < side * 0.46) & (r > side * 0.08)
    b, g, rr = bgr[..., 0].astype(int), bgr[..., 1].astype(int), bgr[..., 2].astype(int)
    icons = ((b > 200) & (g > 200) & (rr > 200)) | ((rr > 190) & (g > 160) & (b < 90))
    mask &= ~icons
    return gray, mask.astype(np.uint8)


class MinimapTracker:
    def __init__(self, hub=None, grabber=None):
        self.hub, self.grabber = hub, grabber
        self.refs, self.index_mtime = {}, 0
        self.estimates = {}
        self.scale_fix = {}
        self.last_kills = None
        self.lock = threading.Lock()
        self.problem = None


    def reference(self, instance):
        path = os.path.join(ROOT, "data", "dungeonmaps.json")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        if mtime != self.index_mtime:
            self.refs, self.index_mtime = {}, mtime
            with open(path, encoding="utf-8") as f:
                self.index = json.load(f)["maps"]
        if instance not in self.refs:
            self.refs.clear()
            entry = self.index.get(str(instance))
            image = os.path.join(MAPS, f"{instance}.png")
            self.refs[instance] = Reference(image, entry["world"]) if entry and os.path.exists(image) else None
        return self.refs[instance]


    def locate(self, ref, gray, mask, ppy, center=None, radius=None, area=None):
        big = ref.at(ppy)
        h, w = gray.shape
        if center is not None:
            cx, cy = ref.to_px(center[0], center[1], ppy)
            r = radius * ppy
            c0, c1 = int(cx - r - w / 2), int(cx + r + w / 2)
            r0, r1 = int(cy - r - h / 2), int(cy + r + h / 2)
        elif area is not None:
            (c0, r0), (c1, r1) = ref.to_px(area[1], area[3], ppy), ref.to_px(area[0], area[2], ppy)
            c0, r0, c1, r1 = int(c0 - w / 2), int(r0 - h / 2), int(c1 + w / 2), int(r1 + h / 2)
        else:
            c0, r0, c1, r1 = -w // 2, -h // 2, big.shape[1] + w // 2, big.shape[0] + h // 2
        pad = max(w, h)
        c0, r0 = max(0, c0 + pad), max(0, r0 + pad)
        c1, r1 = min(big.shape[1] + 2 * pad, c1 + pad), min(big.shape[0] + 2 * pad, r1 + pad)
        if r1 - r0 < h or c1 - c0 < w:
            return -1, None, None
        region = window(big, r0 - pad, r1 - pad, c0 - pad, c1 - pad)
        scores = cv2.matchTemplate(region, gray, cv2.TM_CCOEFF_NORMED, mask=mask)
        scores = np.nan_to_num(scores, nan=-1, posinf=-1, neginf=-1)
        _, best, _, (bx, by) = cv2.minMaxLoc(scores)
        col = c0 + bx + w / 2 - pad
        row = r0 + by + h / 2 - pad
        wx, wy = ref.to_world(col, row, ppy)
        return best, wx, wy

    def step(self, instance, mm, bgra, now, floor_area=None, boss_at=None):
        ref = self.reference(instance)
        if ref is None:
            return None
        if mm["rotate"]:
            self.problem = "Rotate Minimap is on: turn it off in the game's options for positions inside dungeons"
            return None
        self.problem = None
        est = self.estimates.get(instance)
        if est and now - est["t"] > 60:
            est = None
        if est:
            dt = now - est["t"]
            est["x"] += est["vx"] * dt
            est["y"] += est["vy"] * dt
            decay = math.exp(-dt / 2)
            est["vx"] *= decay
            est["vy"] *= decay
            est["sigma"] = min(500.0, est["sigma"] + GROWTH * dt)
            est["t"] = now
        if boss_at:
            est = {"x": boss_at[0], "y": boss_at[1], "vx": 0.0, "vy": 0.0, "sigma": 20.0, "t": now, "heading": est and est.get("heading"),
                   "score": None, "source": "boss"}
        key = (mm["indoors"], min(5, mm["zoom"]))
        ppy0 = mm["w"] / DIAMETER[mm["indoors"]][min(5, mm["zoom"])]
        gray, mask = prepare(bgra, mm["w"], mm["h"])
        if mask.sum() < 200 or float(gray[mask > 0].std()) < 0.02:
            fix = None
        elif est and est["sigma"] < LOST:
            ppy = ppy0 * self.scale_fix.get(key, 1.0)
            score, wx, wy = self.locate(ref, gray, mask, ppy, center=(est["x"], est["y"]), radius=3 * est["sigma"] + 15)
            fix = (score, wx, wy, ppy) if score >= MATCH_NEAR else None
        else:
            fix = None
            for m in (0.9, 0.95, 1.0, 1.05, 1.1):
                score, wx, wy = self.locate(ref, gray, mask, ppy0 * m, area=floor_area)
                if score >= MATCH_FAR and (fix is None or score > fix[0]):
                    fix = (score, wx, wy, ppy0 * m)
            if fix:
                self.scale_fix[key] = round(fix[3] / ppy0, 2)
        if fix:
            score, wx, wy, _ = fix
            if est and est["sigma"] < LOST:
                jump = math.hypot(wx - est["x"], wy - est["y"])
                if jump > TOP_SPEED * RATE * 2 + 3 * est["sigma"]:
                    fix = None
        if fix:
            score, wx, wy, _ = fix
            if est:
                k = est["sigma"] ** 2 / (est["sigma"] ** 2 + FIX_YARDS ** 2)
                nx, ny = est["x"] + k * (wx - est["x"]), est["y"] + k * (wy - est["y"])
                dt = max(RATE, now - est.get("fixed", now - RATE))
                vx, vy = (nx - est.get("fx", nx)) / dt, (ny - est.get("fy", ny)) / dt
                if math.hypot(vx, vy) > TOP_SPEED:
                    vx = vy = 0.0
                est.update(x=nx, y=ny, vx=0.5 * est["vx"] + 0.5 * vx, vy=0.5 * est["vy"] + 0.5 * vy,
                           sigma=math.sqrt(1 / (1 / est["sigma"] ** 2 + 1 / FIX_YARDS ** 2)), score=round(score, 2), source="minimap")
            else:
                est = {"x": wx, "y": wy, "vx": 0.0, "vy": 0.0, "sigma": FIX_YARDS * 2, "t": now, "heading": None,
                       "score": round(score, 2), "source": "minimap"}
            est["fixed"], est["fx"], est["fy"] = now, est["x"], est["y"]
        if est:
            if math.hypot(est["vx"], est["vy"]) > 1.5:
                est["heading"] = math.atan2(est["vy"], est["vx"]) % (2 * math.pi)
            if not fix and est.get("source") == "minimap":
                est["source"] = "estimate"
            self.estimates[instance] = est
        return est

    def current(self, instance, now=None):
        est = self.estimates.get(instance)
        now = now or time.time()
        if not est or now - est.get("fixed", est["t"]) > STALE:
            return None
        return {"x": round(est["x"], 1), "y": round(est["y"], 1), "sigma": round(est["sigma"], 1),
                "heading": est.get("heading"), "score": est.get("score"), "source": est.get("source")}


    def run(self):
        while True:
            started = time.time()
            try:
                self.tick(started)
            except Exception as e:
                self.problem = f"minimap reading failed: {e}"
            time.sleep(max(0.02, RATE - (time.time() - started)))

    def tick(self, now):
        hub = self.hub
        s = hub.state if hub else None
        inst = s and s.get("instance")
        mm = s and s.get("minimap")
        if not inst or not inst.get("id") or not mm or not mm.get("shown") or (inst.get("world") and not inst.get("estimated")):
            return
        if self.reference(inst["id"]) is None:
            return
        boss_at = None
        run = hub.extra.get("run")
        kills = tuple(run["kills"]) if run and run.get("inside") else ()
        if self.last_kills is not None and len(kills) > len(self.last_kills):
            d = hub.dungeons.by_key.get(run["key"])
            new = [k for k in kills if k not in self.last_kills]
            if d and new and 0 < new[-1] <= len(d["bosses"]) and d["bosses"][new[-1] - 1].get("pos"):
                boss_at = d["bosses"][new[-1] - 1]["pos"][:2]
        self.last_kills = kills
        area = None
        sub = (s.get("subzone") or "").lower()
        for f in hub.dungeons.floors.values():
            if f["instance"] == inst["id"] and f["name"].lower() == sub:
                w = f["world"]
                area = (w["bottom"], w["top"], w["right"], w["left"])
        bgra = self.grabber.grab(mm["x"], mm["y"], mm["w"], mm["h"]) if self.grabber and mm["w"] > 20 and mm["h"] > 20 else None
        if bgra is None:
            return
        with self.lock:
            self.step(inst["id"], mm, bgra, now, floor_area=area, boss_at=boss_at)
