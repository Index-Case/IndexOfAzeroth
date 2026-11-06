# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import os
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import clientfiles as wm
import navstore


def kept_from_before(path):
    try:
        return navstore.getmtime(path) < wm.switched_since()
    except OSError:
        return False


class Realign:

    def __init__(self):
        self.lock = threading.Lock()
        self.telling = threading.Lock()
        self.counts = {}
        self.said = {}
        self.told = None
        self.place_of = None

    @contextlib.contextmanager
    def working(self, kind, where=None, when=True):
        if not when:
            yield
            return
        key = (kind, self.place(where))
        with self.lock:
            self.counts[key] = self.counts.get(key, 0) + 1
        self.tell()
        try:
            yield
        finally:
            with self.lock:
                self.counts[key] -= 1
                if not self.counts[key]:
                    del self.counts[key]
            self.tell()

    def place(self, where):
        if not where or not self.place_of:
            return None
        try:
            return self.place_of(*where)
        except Exception:
            return None

    def running(self):
        with self.lock:
            keys = sorted(self.counts, key=lambda k: (k[0], k[1] or ""))
        out = {}
        for kind, place in keys:
            places = out.setdefault(kind, [])
            if place:
                places.append(place)
        return out

    def tell(self):
        with self.telling:
            now = self.running()
            if now != self.said:
                self.said = now
                if self.told:
                    self.told()


REALIGN = Realign()
working = REALIGN.working


def state(rebuild):
    what = REALIGN.running()
    rebuilding = (rebuild or {}).get("state") == "rebuilding"
    if not rebuilding and not what:
        return None
    read_in = rebuilding and rebuild.get("readIn")
    return {"build": rebuilding and rebuild.get("build") or wm.switched_build(), "rebuilding": rebuilding,
            "step": rebuild.get("step") if rebuilding else None, "what": what, **({"readIn": read_in} if read_in else {})}
