# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading
import time

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "gathered.json")
SAME_YARDS = 3.0
SAME_SECONDS = 30.0
KEEP = 20000


class Gathered:
    def __init__(self, path=PATH):
        self.path, self.lock = path, threading.Lock()
        self.seen = store.load_json(path, {}).get("seen", [])

    def note(self, gathers, now=None):
        now = time.time() if now is None else now
        fresh = []
        with self.lock:
            recent = self.seen[-200:]
            for g in gathers:
                at, (n, w) = now - g["age"], g["pos"]
                if any(o["name"] == g["name"] and o["inst"] == g["map"] and abs(o["at"] - at) < SAME_SECONDS
                       and abs(o["n"] - n) <= SAME_YARDS and abs(o["w"] - w) <= SAME_YARDS for o in recent):
                    continue
                obs = {"name": g["name"], "inst": g["map"], "n": n, "w": w, "at": round(at)}
                fresh.append(obs)
                recent.append(obs)
            if fresh:
                self.seen = (self.seen + fresh)[-KEEP:]
                seen = self.seen
                storewriter.save_json_later(self.path, lambda: {"seen": seen}, indent=None)
        return bool(fresh)

    def all(self):
        with self.lock:
            return list(self.seen)
