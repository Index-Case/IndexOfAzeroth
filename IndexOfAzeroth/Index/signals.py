# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import threading
import time

from serverlog import log_error

LOADED_ONLY = ("data", "plans")

_listeners = []
_lock = threading.Lock()


def listen(fn):
    with _lock:
        _listeners.append(fn)
    return fn


def unlisten(fn):
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def send(kind, **what):
    signal = {"kind": kind, "sent": round(time.time(), 3), **what}
    with _lock:
        heard = list(_listeners)
    for fn in heard:
        try:
            fn(signal)
        except Exception:
            log_error(f"a listener on the {kind} signal")
    return bool(heard)
