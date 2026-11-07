# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import threading
import time

from gamedata import load_todo, save_todo, todo_lock
from serverlog import log_error
from shared import quiet_table

GONE_S = 10.0


def applies(key, move, status, bars):
    if key.startswith("rank:"):
        if not isinstance(bars, dict):
            return None
        best = str((move or {}).get("sig", "")).partition("|")[2]
        return any(r.get("name") == key[len("rank:"):] and str(r.get("best")) == best for r in bars.get("ranks") or ())
    if not isinstance(status, dict):
        return None
    return any(w.get("key") == key for w in status.get("warnings") or ())


class WarnMoves:

    def __init__(self, shared=None):
        self.shared = shared
        self.moved = {}
        self.gone = {}
        self.version = 0
        self.lock = threading.Lock()

    def took(self, todo):
        with self.lock:
            self.moved = {k: dict(d) for k, d in (todo.get("dismissed") or {}).items() if isinstance(d, dict)}
            self.gone = {k: t for k, t in self.gone.items() if k in self.moved}

    def seen(self, status, bars, now=None):
        now = time.time() if now is None else now
        over = []
        with self.lock:
            for key, move in self.moved.items():
                holds = applies(key, move, status, bars)
                if holds is None or holds:
                    self.gone.pop(key, None)
                elif now - self.gone.setdefault(key, now) >= GONE_S:
                    over.append(key)
        return self.forget(over) if over else []

    def forget(self, keys):
        with todo_lock:
            todo = load_todo()
            with self.lock:
                gone = [k for k in keys if k in todo["dismissed"] and todo["dismissed"][k] == self.moved.get(k)]
            for k in gone:
                todo["dismissed"].pop(k)
            if gone:
                save_todo(todo)
                if self.shared:
                    try:
                        self.shared.set_quiet(quiet_table(todo))
                    except OSError:
                        log_error("writing the quiet warnings into Shared.lua")
            self.took(todo)
            if gone:
                self.version += 1
        return gone
