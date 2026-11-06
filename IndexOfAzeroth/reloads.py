# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

from store import load_json
from storewriter import save_json_later

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "reloads.json")

FIRST = 60.0
LEARNT = 3
KEEP = 10
BUFFER = 0.25
BUFFER_MIN = 3.0
FLOOR = 8.0
CEILING = 120.0
LONGEST = 300.0


def wait_for(times):
    if len(times) < LEARNT:
        return FIRST
    mean = sum(times) / len(times)
    return min(CEILING, max(FLOOR, mean + max(BUFFER_MIN, mean * BUFFER)))


class Reloads:

    def __init__(self, path=PATH, load=load_json, save=save_json_later):
        self.path, self.save = path, save
        kept = load(path, {})
        times = kept.get("seconds") if isinstance(kept, dict) else None
        self.times = [float(t) for t in times or () if isinstance(t, (int, float)) and 0 < t <= LONGEST][-KEEP:]
        self.since = None
        self.until = None
        self.gone = False

    def wait(self):
        return wait_for(self.times)

    def signal(self, now):
        if self.since is None:
            self.since, self.until, self.gone = now, now + self.wait(), False

    def lost(self):
        if self.since is not None:
            self.gone = True

    def back(self, now):
        if self.since is None:
            return
        took = now - self.since
        if self.gone and 0 < took <= LONGEST:
            self.times = (self.times + [round(took, 2)])[-KEEP:]
            self.save(self.path, {"seconds": list(self.times)})
        self.since = self.until = None
        self.gone = False

    def link(self, now):
        if self.since is not None and now - self.since > LONGEST:
            self.since = self.until = None
            self.gone = False
        if self.since is None or now >= self.until:
            return None
        return {"since": round(self.since, 2), "until": round(self.until, 2)}
