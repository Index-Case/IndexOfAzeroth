# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading
import time

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "firespots.json")
FRESH = 10
SAME = 3
DUNGEON_KINDS = ("party", "raid")


class Firespots:
    def __init__(self, path=PATH):
        self.path, self.lock = path, threading.Lock()
        self.data = store.load_json(path, {})
        self.version = 0

    def note(self, char, state, casts, kits, where, now=None):
        now = time.time() if now is None else now
        pos, inst = (state or {}).get("pos"), (state or {}).get("instance") or {}
        if not char or not pos or inst.get("kind") in DUNGEON_KINDS:
            return False
        news = False
        with self.lock:
            fires = self.data.setdefault(char, [])
            for c in casts:
                kit = kits.get(c["id"])
                if not kit or not kit[0] or c["ago"] > FRESH:
                    continue
                at = round(now - c["ago"])
                spot = where(state["map"], pos["x"], pos["y"])
                if not spot or any(f["spell"] == c["id"] and abs(f["at"] - at) <= SAME for f in fires):
                    continue
                fires.append({"spell": c["id"], "name": kit[1], "at": at, "ends": at + kit[0], "map": state["map"],
                              "x": pos["x"], "y": pos["y"], "inst": spot[0], "north": spot[1], "west": spot[2]})
                news = True
            news = self.drop_out(now) or news
            if news:
                self.version += 1
                storewriter.save_json_later(self.path, self.data)
        return news

    def move(self, old, new):
        if not old or not new or old == new:
            return False
        with self.lock:
            had = self.data.pop(old, None)
            if had is None:
                return False
            self.data.setdefault(new, []).extend(had)
            self.data[new].sort(key=lambda f: f["at"])
            self.version += 1
            storewriter.save_json_later(self.path, self.data)
            return True

    def drop_out(self, now):
        gone = False
        for char in list(self.data):
            live = [f for f in self.data[char] if f["ends"] > now]
            gone = gone or len(live) != len(self.data[char])
            if live:
                self.data[char] = live
            else:
                del self.data[char]
        return gone

    def live(self, char, now=None):
        now = time.time() if now is None else now
        with self.lock:
            return [dict(f) for f in self.data.get(char) or () if f["ends"] > now]
