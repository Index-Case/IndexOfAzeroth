# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "enemies_seen.json")
FIELDS = ("cls", "race", "sex", "guild", "title")
LEVELS_KEPT = 40


class EnemiesSeen:
    def __init__(self, path=STATE):
        self.path, self.lock = path, threading.Lock()
        kept = store.load_json(path, {})
        self.data = {g: p for g, p in kept.items() if isinstance(p, dict)} if isinstance(kept, dict) else {}
        self.version = 0

    def note(self, sightings, now):
        news = False
        with self.lock:
            for s in sightings or ():
                guid = s.get("guid")
                if not guid:
                    continue
                news = True
                t = round(now - (s.get("age") or 0), 1)
                p = self.data.setdefault(guid, {"levels": [], "first": t, "last": t})
                for k in FIELDS:
                    if s.get(k) not in (None, ""):
                        p[k] = s[k]
                p["first"], p["last"] = min(p["first"], t), max(p["last"], t)
                level, least = s.get("level"), s.get("least")
                if level is not None or least is not None:
                    levels = p["levels"]
                    if not levels or levels[-1][1:] != [level, least]:
                        levels.append([t, level, least])
                        levels.sort(key=lambda x: x[0])
                        del levels[:-LEVELS_KEPT]
            if news:
                self.version += 1
                storewriter.save_json_later(self.path, self.data, indent=None)
        return news

    def of(self, guid):
        with self.lock:
            p = self.data.get(guid)
            return {**p, "levels": [list(x) for x in p["levels"]]} if p else None

    def level_at(self, guid, t):
        with self.lock:
            levels = (self.data.get(guid) or {}).get("levels") or ()
            if not levels:
                return None, None
            nearest = min(levels, key=lambda x: abs(x[0] - t))
            return nearest[1], nearest[2]
