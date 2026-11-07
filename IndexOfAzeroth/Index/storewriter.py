# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import atexit
import contextlib
import os
import threading
import time
import jsontext
import mainstores
import store
from serverlog import start_thread

LOADED_ONLY = ("data",)

_later = {}
_later_cv = threading.Condition()
_in_hand = {}
_refused = {}
_writer = None
_on_error = None
RETRY_WAIT = 5.0


def save_json_later(path, obj, indent=1):
    def text(o):
        return jsontext.dumps(o, indent).encode("utf-8")
    write_later(path, (lambda: text(obj())) if callable(obj) else text(obj))


def write_later(path, data):
    _hand(path, data)


class _Journal:
    __slots__ = ("fold", "adds")

    def __init__(self, fold=None, adds=b""):
        self.fold, self.adds = fold, adds


def journal_of(path):
    return path + ".journal"


def add_later(path, data):
    _hand(path, _Journal(None, data))


def fold_later(path, make):
    _hand(path, _Journal(make))


def journal(path):
    for attempt in range(store.SWAP_TRIES):
        try:
            with open(journal_of(path), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return b""
        except PermissionError:
            if attempt == store.SWAP_TRIES - 1:
                raise
            time.sleep(store.SWAP_WAIT)


def _after(earlier, later):
    if earlier is None or not isinstance(later, _Journal) or later.fold:
        return later
    return _Journal(earlier.fold, earlier.adds + later.adds)


def _append(path, data):
    mainstores.refuse_write(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "ab", buffering=0) as f:
        end = f.seek(0, os.SEEK_END)
        try:
            view = memoryview(data)
            while view:
                view = view[f.write(view):]
            os.fsync(f.fileno())
        except BaseException:
            with contextlib.suppress(OSError):
                f.truncate(end)
            raise


def _hand(path, data):
    global _writer
    with _later_cv:
        _later[path] = _after(_later.get(path), data)
        if _writer is None:
            atexit.register(flush_later)
        if _writer is None or not _writer.is_alive():
            _writer = start_thread("store-writer", _write_loop)
        _later_cv.notify()


def _due():
    now, soonest = time.monotonic(), None
    for path in _later:
        left = _refused.get(path, now - RETRY_WAIT) + RETRY_WAIT - now
        if left <= 0:
            return path, None
        soonest = left if soonest is None else min(soonest, left)
    return None, soonest


def _write_loop():
    while True:
        with _later_cv:
            path, wait = _due()
            while path is None:
                _later_cv.wait(wait)
                path, wait = _due()
            data = _in_hand[path] = _later.pop(path)
        refused, left = False, data
        try:
            if isinstance(data, _Journal):
                if data.fold:
                    store.write_bytes(path, data.fold())
                    if os.path.exists(journal_of(path)):
                        store.write_bytes(journal_of(path), b"")
                    left = _Journal(None, data.adds)
                if data.adds:
                    _append(journal_of(path), data.adds)
            else:
                store.write_bytes(path, data() if callable(data) else data)
            left = None
        except OSError:
            refused = True
            if _on_error and path not in _refused:
                with contextlib.suppress(Exception):
                    _on_error(path)
        except Exception:
            left = _Journal(None, left.adds) if isinstance(left, _Journal) and left.fold and left.adds else None
            if _on_error:
                with contextlib.suppress(Exception):
                    _on_error(path)
        finally:
            with _later_cv:
                del _in_hand[path]
                if left is not None:
                    _later[path] = _after(left, _later[path]) if path in _later else left
                if refused:
                    _refused[path] = time.monotonic()
                else:
                    _refused.pop(path, None)
                _later_cv.notify_all()


def waiting(path):
    with _later_cv:
        data = _later.get(path, _in_hand.get(path))
    if isinstance(data, _Journal):
        return None
    return data() if callable(data) else data


def on_write_error(fn):
    global _on_error
    _on_error = fn


def flush_later(timeout=10.0):
    end = time.time() + timeout
    with _later_cv:
        while _later or _in_hand:
            left = end - time.time()
            if left <= 0:
                return False
            _later_cv.wait(left)
    return True
