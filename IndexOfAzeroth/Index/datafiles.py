# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading

import store
import storedonly

ROOT = os.path.dirname(os.path.abspath(__file__))
_kept = {}
_locks = {}
_locks_lock = threading.Lock()
REFUSED = "a data file's contents are shared by every reader: change a copy of your own"
NEEDED = object()


class Unread(storedonly.NotStored):
    pass


def _refuse(self, *args, **kwargs):
    raise TypeError(REFUSED)


class ReadOnlyDict(dict):
    __slots__ = ()
    __setitem__ = __delitem__ = __ior__ = clear = pop = popitem = setdefault = update = _refuse

    def __reduce__(self):
        return dict, (dict(self),)


class ReadOnlyList(list):
    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = append = extend = insert = pop = remove = clear = sort = reverse = _refuse

    def __reduce__(self):
        return list, (list(self),)


def _lists(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                dict.__setitem__(o, k, _lists(v))
        return o
    if isinstance(o, list):
        return ReadOnlyList([_lists(v) if isinstance(v, (dict, list)) else v for v in o])
    return o


def data_path(name):
    return os.path.join(ROOT, "data", name)


def load(path, default=NEEDED):
    path = os.path.abspath(path)
    with _locks_lock:
        lock = _locks.setdefault(path, threading.Lock())
    with lock:
        now = store.stamp(path)
        hit = _kept.get(path)
        if now is not None and hit and hit[0] == now:
            return hit[1]
        parsed = store.load_json(path, default, hook=ReadOnlyDict)
        if parsed is NEEDED:
            _kept.pop(path, None)
            raise Unread(f"{os.path.basename(path)} isn't there or can't be read")
        if now is None or parsed is default:
            _kept.pop(path, None)
            return parsed
        parsed = _lists(parsed)
        _kept[path] = (now, parsed)
        return parsed


def forget():
    _kept.clear()
