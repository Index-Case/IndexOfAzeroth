# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import threading
import time

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "entrances_seen.json")
WITHIN = 90.0
MOVED = 40.0


class SeenEntrances:
    def __init__(self, path=PATH, names=None):
        self.path, self.lock = path, threading.Lock()
        self.data = store.load_json(path, {})
        self.names = names or (lambda map_id: None)
        self.last = None

    def watch(self, state, here):
        inst = state.get("instance") or {}
        now = time.time()
        if here and not (state.get("flags") or {}).get("instance"):
            self.last = (*here, now)
            return
        map_id = inst.get("id")
        name = map_id and self.names(map_id)
        if not name:
            return
        key = str(map_id)
        with self.lock:
            if not self.last or now - self.last[3] > WITHIN:
                return
            seen = self.data.get(key) or {}
            outside = [self.last[0], round(self.last[1], 1), round(self.last[2], 1)]
            was = seen.get("outside")
            self.last = None
            if not was or was[0] != outside[0] or math.dist(was[1:], outside[1:]) > MOVED:
                self.data[key] = {"name": name, "outside": outside, "at": round(now)}
                storewriter.save_json_later(self.path, self.data)

    def doors(self, known=()):
        with self.lock:
            return [{"dungeon": e["name"], "outside": e["outside"], "inside": e["inside"], "learnt": True}
                    for e in self.data.values() if e.get("inside") and e["inside"][0] not in known]

    def on(self, instance):
        with self.lock:
            return [(e["name"], e["outside"][1], e["outside"][2]) for e in self.data.values() if e["outside"][0] == instance]

    def outside_of(self, map_id):
        with self.lock:
            e = self.data.get(str(map_id))
            return list(e["outside"]) if e else None
