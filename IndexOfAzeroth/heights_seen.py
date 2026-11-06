# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import threading
import time

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "heights_seen.json")
MATCH_YARDS = 15.0
MOVED = 0.5


class SeenHeights:
    def __init__(self, path=PATH):
        self.path, self.lock = path, threading.Lock()
        self.data = store.load_json(path, {})
        self.version = 0

    def note(self, heights, now=None):
        now = time.time() if now is None else now
        news = False
        with self.lock:
            for h in heights:
                if not h.get("name"):
                    continue
                key = f"{h['inst']}|{round(h['at'][0])}|{round(h['at'][1])}|{h['name']}"
                was = self.data.get(key)
                if was and abs(was["z"] - h["z"]) < MOVED:
                    continue
                self.data[key] = {"name": h["name"], "npc": h.get("npc") or (was or {}).get("npc"), "inst": h["inst"],
                                  "at": [h["at"][0], h["at"][1]], "z": round(h["z"], 1), "seen": h.get("seen", 0),
                                  "when": round(now)}
                news = True
            if news:
                self.version += 1
                storewriter.save_json_later(self.path, self.data)
        return news

    def height(self, inst, north, west, name):
        best, near = None, MATCH_YARDS
        with self.lock:
            for h in self.data.values():
                if h["inst"] != inst or h["name"] != name:
                    continue
                d = math.dist(h["at"], (north, west))
                if d <= near:
                    best, near = h["z"], d
        return best

    def listed(self):
        with self.lock:
            return [{"name": h["name"], "inst": h["inst"], "at": h["at"], "z": h["z"]} for h in self.data.values()]
