# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import hashlib
import json
import os
import sys
import threading
import time
import jsontext
import mainstores
import storewriter
try:
    import msvcrt
except ImportError:
    msvcrt = None

ROOT = os.path.dirname(os.path.abspath(__file__))
REFRESH = os.path.join(ROOT, "data", "buildcache", "refresh.json")
if os.environ.get("WCC_TRAFFIC_LOG"):
    import traffic
    traffic.log_to_file(os.environ["WCC_TRAFFIC_LOG"])

MISSING = os.path.join(ROOT, "data", "buildcache", "missing.json")
RECHECK = 86400
_lock = threading.RLock()
SWAP_TRIES, SWAP_WAIT = 50, 0.04


@contextlib.contextmanager
def locked(path):
    mainstores.refuse_write(path)
    with _lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".lock", "a+b") as f:
            if msvcrt:
                while True:
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.02)
            try:
                yield
            finally:
                if msvcrt:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def write_bytes(path, data):
    mainstores.refuse_write(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part =f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    with open(part, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(SWAP_TRIES):
        try:
            os.replace(part, path)
            return
        except PermissionError:
            if attempt == SWAP_TRIES - 1:
                with contextlib.suppress(OSError):
                    os.remove(part)
                raise
            time.sleep(SWAP_WAIT)


def save_json(path, obj, indent=1, sort_keys=False):
    write_bytes(path, jsontext.dumps(obj, indent, sort_keys).encode("utf-8"))


def write_fetched(path, data):
    write_bytes(path, data)
    import prompts
    prompts.look(path, data)


def stamp(path):
    try:
        st = path.stat() if isinstance(path, os.DirEntry) else os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


_digests = {}


def digest(path):
    now = stamp(path)
    if now is None:
        return None
    with _lock:
        got = _digests.get(path)
    if got is not None and got[0] == now:
        return got[1]
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    with _lock:
        _digests[path] = (now, h.hexdigest())
    return h.hexdigest()


def load_json(path, default, hook=None):
    waiting = storewriter.waiting(path)
    if waiting is not None:
        return json.loads(waiting, object_hook=hook)
    for attempt in range(SWAP_TRIES):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f, object_hook=hook)
        except FileNotFoundError:
            return default
        except PermissionError:
            if attempt == SWAP_TRIES - 1:
                raise
            time.sleep(SWAP_WAIT)
        except ValueError:
            if mainstores.in_main(path):
                return default
            try:
                os.replace(path, f"{path}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
            except OSError:
                pass
            return default


def _marks():
    return set(load_json(REFRESH, []))


def mark_refresh(names):
    names = set(names)
    if not names:
        return
    with locked(REFRESH):
        save_json(REFRESH, sorted(_marks() | names))


def refresh_due(name):
    return name in _marks()


def refreshed(name):
    if not refresh_due(name):
        return
    with locked(REFRESH):
        marks = _marks()
        if name in marks:
            save_json(REFRESH, sorted(marks - {name}))



def running_builder():
    base = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return base[6:-3] if base.startswith("build_") and base.endswith(".py") else None


BUILDER_RUN = "WCC_BUILDER_RUN"


def start_builder_run():
    os.environ[BUILDER_RUN] = f"{os.getpid()}.{time.time_ns()}"


def builder_run():
    return os.environ.get(BUILDER_RUN) or str(os.getpid())


def mark_missing(source, names, builder=None):
    names = set(names)
    if not names:
        return
    builder, now = builder or running_builder(), round(time.time())
    with locked(MISSING):
        m = load_json(MISSING, {})
        for n in names:
            e = m.setdefault(f"{source}|{n}", {"source": source, "name": n, "since": now})
            e["asked"] = now
            if builder:
                e["builder"] = builder
        save_json(MISSING, m, indent=None)


def found(source, names):
    names = set(names)
    if not names or not any(e["source"] == source and e["name"] in names for e in missing()):
        return
    with locked(MISSING):
        m = load_json(MISSING, {})
        for n in names:
            m.pop(f"{source}|{n}", None)
        save_json(MISSING, m, indent=None)


def missing(source=None):
    return [e for e in load_json(MISSING, {}).values() if source is None or e["source"] == source]


def missing_due(source, name):
    e = load_json(MISSING, {}).get(f"{source}|{name}")
    return bool(e) and time.time() - e.get("asked", 0) >= RECHECK


def missing_builders():
    return {e["builder"] for e in missing() if e.get("builder")}
