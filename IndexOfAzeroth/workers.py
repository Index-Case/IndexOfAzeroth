# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import concurrent.futures
import contextlib
import json
import multiprocessing
import os
import sys
import tempfile
import time
import jsontext
import store

LOADED_ONLY = ("data", "plans", "suites")
ENV = "WCC_WORKERS"
LEAVE = 2
BELOW_NORMAL = 0x4000
PROCESSES = 2
GB = 1 << 30
RUN_COMMIT = 6 * GB
KEEP_SHARE = 0.10
QUEUE = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "wcc-heavy")
HELD = "WCC_HEAVY_TURN"
POLL = 5.0
YOUNG_NS = 5 * 10**9
LOCK_AT = 1 << 20


def playing():
    import game
    return game.running()


def count(leave=LEAVE, most=None, builder=False):
    env = os.environ.get(ENV, "").strip()
    cores = (os.cpu_count() or 1) - leave
    n = int(env) if env.isdigit() else cores if builder and not playing() else min(PROCESSES, cores)
    if most is not None:
        n = min(n, most)
    return max(1, n)


def places(cores=None):
    return max(1, ((cores or os.cpu_count() or 1) - LEAVE) // PROCESSES)


ROOT = os.path.dirname(os.path.abspath(__file__))
ROOM = "room.json"


def _room_kept(path):
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f).get("room")
    except (OSError, ValueError, AttributeError):
        return None
    return got if isinstance(got, int) and not isinstance(got, bool) and got >= 1 else None


def machine_room(folder=None, root=None):
    path = os.path.join(folder or QUEUE, ROOM)
    if not os.path.isdir(os.path.join(root or ROOT, ".git")):
        return _room_kept(path) or places()
    mine = places()
    if _room_kept(path) != mine:
        with contextlib.suppress(OSError):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            store.save_json(path, {"room": mine}, indent=None)
    return mine


def commit():
    if sys.platform != "win32":
        return None
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32), ("total_phys", ctypes.c_uint64),
                    ("avail_phys", ctypes.c_uint64), ("total_commit", ctypes.c_uint64),
                    ("avail_commit", ctypes.c_uint64), ("total_virtual", ctypes.c_uint64),
                    ("avail_virtual", ctypes.c_uint64), ("avail_extended", ctypes.c_uint64)]
    st = Status()
    st.length = ctypes.sizeof(Status)
    if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return st.avail_commit, st.total_commit


def memory_short(memory=commit):
    got = memory()
    if not got:
        return None
    free, limit = got
    wanted = RUN_COMMIT + KEEP_SHARE * limit
    if free >= wanted:
        return None
    return f"memory: {free / GB:.0f} GB free to commit, {wanted / GB:.0f} GB wanted"


def _priority(cls=None):
    if sys.platform != "win32":
        return None
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    had = k32.GetPriorityClass(k32.GetCurrentProcess())
    if cls is not None:
        k32.SetPriorityClass(k32.GetCurrentProcess(), cls)
    return had


def _lock(fh, at=LOCK_AT):
    import msvcrt
    fh.seek(at)
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock(fh, at=LOCK_AT):
    import msvcrt
    fh.seek(at)
    with contextlib.suppress(OSError):
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def _remove(*paths):
    for path in paths:
        with contextlib.suppress(OSError):
            os.remove(path)


def queue(folder=None, now_ns=None):
    folder = folder or QUEUE
    now_ns = now_ns or time.time_ns()
    try:
        names = sorted(n[:-len(".ticket")] for n in os.listdir(folder) if n.endswith(".ticket"))
    except OSError:
        return []
    out = []
    for name in names:
        ticket, going = os.path.join(folder, name + ".ticket"), os.path.join(folder, name + ".going")
        try:
            with open(ticket, "rb") as fh:
                words = fh.read(LOCK_AT)
                ended = now_ns - int(name.split("-")[0]) > YOUNG_NS and _lock(fh)
                if ended:
                    _unlock(fh)
        except (OSError, ValueError):
            continue
        if ended:
            _remove(going, ticket)
            continue
        try:
            entry = json.loads(words.decode("utf-8"))
        except ValueError:
            entry = {}
        out.append({**entry, "name": name, "going": os.path.isfile(going)})
    return out


def waits(pid, folder=None):
    if os.environ.get(HELD):
        return False
    return any(r.get("pid") == pid and not r["going"] for r in queue(folder))


def _said(runs):
    return ", ".join(f"{r.get('what') or '?'} in {r.get('root') or '?'}" for r in runs)


@contextlib.contextmanager
def turn(what, root=None, folder=None, room=None, short=None, say=print, poll=POLL, sleep=time.sleep):
    had = _priority(BELOW_NORMAL)
    if os.environ.get(HELD):
        try:
            yield
        finally:
            _priority(had)
        return
    folder, short, given = folder or QUEUE, short or memory_short, room
    os.makedirs(folder, exist_ok=True)
    name = f"{time.time_ns():020d}-{os.getpid()}"
    ticket, going = os.path.join(folder, name + ".ticket"), os.path.join(folder, name + ".going")
    fh = open(ticket, "w+b")
    try:
        fh.write(jsontext.dumps({"pid": os.getpid(), "what": what, "root": root or os.getcwd()}).encode("utf-8"))
        fh.flush()
        _lock(fh)
        told = None
        while True:
            runs = queue(folder)
            ahead = [r for r in runs if not r["going"] and r["name"] < name]
            on = [r for r in runs if r["going"]]
            room = given or machine_room(folder)
            memory = None if ahead or len(on) >= room else short()
            if ahead:
                key, why = ("ahead", [r["name"] for r in ahead]), (
                    f"{len(ahead)} heavy run{'s' if len(ahead) != 1 else ''} ahead in the queue ({_said(ahead)})")
            elif len(on) >= room:
                key, why = ("full", [r["name"] for r in on]), (
                    f"{len(on)} heavy run{'s' if len(on) != 1 else ''} going, as many as the machine takes at once "
                    f"({_said(on)})")
            elif memory:
                key, why = ("memory",), memory
            else:
                break
            if key != told:
                say(f"{what}: waiting for the machine, {why}")
                told = key
            sleep(poll)
        open(going, "wb").close()
        if told:
            say(f"{what}: its turn came, running")
        os.environ[HELD] = name
        try:
            yield
        finally:
            os.environ.pop(HELD, None)
    finally:
        _remove(going)
        _unlock(fh)
        fh.close()
        _remove(ticket)
        _priority(had)


class Inline(concurrent.futures.Executor):

    def __init__(self, setup=None, args=()):
        if setup:
            setup(*args)

    def submit(self, fn, *args, **kwargs):
        future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:
            future.set_exception(e)
        return future

    def map(self, fn, *iterables, timeout=None, chunksize=1):
        return (fn(*args) for args in zip(*iterables))


class Pool(concurrent.futures.ProcessPoolExecutor):

    def __init__(self, n, setup=None, args=(), what=None):
        self._turn = turn(what or os.path.basename(sys.argv[0] or "python"))
        self._turn.__enter__()
        try:
            super().__init__(n, initializer=setup, initargs=args)
        except BaseException:
            self._give_back()
            raise

    def _give_back(self):
        held, self._turn = self._turn, None
        if held:
            held.__exit__(None, None, None)

    def shutdown(self, wait=True, **kwargs):
        try:
            super().shutdown(wait, **kwargs)
        finally:
            self._give_back()


def pool(n, setup=None, args=(), what=None):
    if n <= 1:
        return Inline(setup, args)
    return Pool(n, setup, args, what)


def gate(n):
    return multiprocessing.BoundedSemaphore(n)


def gated(fn, at):
    if at is None:
        return fn
    inner = getattr(fn, "ungated", fn)

    def run(*args, **kwargs):
        with at:
            return inner(*args, **kwargs)
    run.ungated = inner
    return run
