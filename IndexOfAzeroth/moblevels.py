# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
import threading

import datafiles
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "data", "world.json")
RESPAWNS = os.path.join(ROOT, "data", "respawns.json")
HIGHEST = 99
SKULL = "??"
TEXT = re.compile(r"\bLevel\s+(\d+|\?\?)(?:\s*-\s*(\d+|\?\?))?\s*", re.I)


def level(v):
    if v == SKULL:
        return SKULL
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        return None
    return SKULL if v > HIGHEST else v


def span(lo, hi=None):
    lo = level(lo)
    if lo is None:
        return None
    return [lo, level(hi) or lo]


def from_text(text):
    m = TEXT.search(text) if isinstance(text, str) else None
    if not m:
        return None, (text or "").strip() if isinstance(text, str) else ""
    lo, hi = (g if g == SKULL or g is None else int(g) for g in m.groups())
    rest = (text[:m.start()] + text[m.end():]).strip()
    return span(lo, hi), rest


def of(npc):
    if npc is None:
        return None
    return game(npc, of_data(npc))


def game(npc, data):
    return choose(data, learnt.levels(npc) if learnt and npc is not None else None)


def of_data(npc):
    if npc is None:
        return None
    m = (datafiles.load(WORLD, {}).get("mobs") or {}).get(str(npc))
    got = span(m[1], m[2]) if m and len(m) > 2 else None
    if got:
        return got
    r = (datafiles.load(RESPAWNS, {}).get("npcs") or {}).get(str(npc))
    return span(r[4], r[5]) if r and len(r) > 5 else None


def merge(spans):
    spans = [s for s in spans if s]
    if not spans:
        return None
    lows = [v for s in spans for v in s if v != SKULL]
    if not lows:
        return [SKULL, SKULL]
    return [min(lows), SKULL if any(SKULL in s for s in spans) else max(lows)]


def _inside(seen, data):
    for v in seen:
        if v == SKULL or v in data:
            continue
        if SKULL in data or not data[0] <= v <= data[1]:
            return False
    return True


def choose(data, seen):
    if not seen:
        return data
    if not data:
        return seen
    return data if _inside(seen, data) else seen


LEARNT = os.path.join(ROOT, "data", "levels_seen.json")
learnt = None


class SeenLevels:

    def __init__(self, path=LEARNT):
        self.path, self.lock = path, threading.Lock()
        kept = store.load_json(path, {})
        self.data = {str(k): v for k, v in kept.items() if isinstance(v, list) and len(v) == 2} if isinstance(kept, dict) else {}
        self.version = 0

    def note(self, kills):
        news = False
        with self.lock:
            for k in kills:
                v, npc = level(k.get("level")), k.get("npc")
                if v is None or not npc:
                    continue
                key, was = str(npc), self.data.get(str(npc))
                if v == SKULL:
                    got = was or [SKULL, SKULL]
                elif not was or SKULL in was:
                    got = [v, v]
                else:
                    got = [min(was[0], v), max(was[1], v)]
                if got != was:
                    self.data[key], news = got, True
            if news:
                self.version += 1
                storewriter.save_json_later(self.path, self.data, indent=None)
        return news

    def levels(self, npc):
        with self.lock:
            got = self.data.get(str(npc))
            return list(got) if got else None
