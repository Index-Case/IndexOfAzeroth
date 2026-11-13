# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import io
import json
import lzma
import os
import tarfile
import threading
from collections import OrderedDict

import numpy as np

import arrays
import mainstores
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("DGG_NAVCACHE") or os.path.join(ROOT, "data", "navcache")
PACK = os.environ.get("DGG_NAVPACK") or mainstores.path("navpack")
BASE = os.environ.get("DGG_NAVBASE") or None
KEEP_BYTES = 256 << 20
MARKS = "checked"
COMPACT = 2

_lock = threading.Lock()
_index = [None, None]
_groups = OrderedDict()
_held = [0]
_loading = {}


def _key(folder):
    return os.path.normcase(os.path.abspath(folder))


def in_store(path):
    return _key(os.path.dirname(path)) == _key(CACHE)


def group_file(run, gid):
    return f"{run}-{gid:05d}.xz" if run else f"{gid:05d}.xz"


class Index:

    def __init__(self, files, run=None, runs=None):
        self.run = run
        self.runs = runs
        self.names = sorted(files)
        rows = np.array([files[n] for n in self.names], np.int64).reshape(-1, 3)
        self.group, self.size, self.ns = rows[:, 0], rows[:, 1], rows[:, 2]
        self.checked = {}
        self.marks_seen = None
        self.marks_read = None
        self.mark_lines = 0
        self.marks_lock = threading.Lock()

    def file(self, gid):
        return group_file(self.runs[gid] if self.runs else self.run, gid)

    def get(self, name):
        i = bisect.bisect_left(self.names, name)
        if i == len(self.names) or self.names[i] != name:
            return None
        return int(self.group[i]), int(self.size[i]), max(int(self.ns[i]), self.checked.get(name, 0))

    def __iter__(self):
        return iter(self.names)

    def __len__(self):
        return len(self.names)

    def items(self):
        checked = self.checked
        for i, n in enumerate(self.names):
            yield n, (int(self.group[i]), int(self.size[i]), max(int(self.ns[i]), checked.get(n, 0)))


def index(pack=None):
    pack = PACK if pack is None else pack
    path = os.path.join(pack, "index.json")
    key = (_key(pack), store.stamp(path))
    got = _index[:]
    if got[0] == key:
        read_marks(pack, got[1])
        return got[1]
    raw = {}
    if key[1] is not None:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    files = raw.get("files", {})
    if files and not isinstance(next(iter(files.values())), list):
        raise ValueError(f"{path}: an index without each file's size and time, pack it again")
    made = Index(files, raw.get("run"), raw.get("runs"))
    read_marks(pack, made)
    with _lock:
        _index[:] = [key, made]
    return made


def marks_path(pack, run):
    return os.path.join(pack, MARKS, f"{run or 'pack'}.tsv")


def read_marks(pack, made):
    path = marks_path(pack, made.run)
    try:
        st = os.stat(path)
        seen = (st.st_ino, st.st_size)
    except OSError:
        seen = None
    if seen == made.marks_seen:
        return
    with made.marks_lock:
        if seen == made.marks_seen:
            return
        if seen is None:
            made.checked, made.marks_read, made.mark_lines, made.marks_seen = {}, None, 0, None
            return
        try:
            with open(path, "rb") as f:
                st = os.fstat(f.fileno())
                at = made.marks_read
                again = at is None or at[0] != st.st_ino or st.st_size < at[1]
                start = 0 if again else at[1]
                f.seek(start)
                data = f.read()
        except OSError:
            return
        whole = data[:data.rfind(b"\n") + 1]
        checked, lines = ({}, 0) if again else (made.checked, made.mark_lines)
        for line in whole.splitlines():
            name, _, ns = line.partition(b"\t")
            if name and ns.isdigit():
                n, v = name.decode("utf-8", "replace"), int(ns)
                if v > checked.get(n, 0):
                    checked[n] = v
                lines += 1
        made.checked, made.mark_lines = checked, lines
        made.marks_read, made.marks_seen = (st.st_ino, start + len(whole)), (st.st_ino, st.st_size)


def packed(path):
    if not in_store(path):
        return None
    return index().get(os.path.basename(path))


def base():
    return BASE or mainstores.under(CACHE)


def based(path):
    top = base()
    if not top or not in_store(path) or os.path.exists(path):
        return None
    there = os.path.join(top, os.path.basename(path))
    return there if os.path.exists(there) else None


def seconds(ns):
    sec, rest = divmod(ns, 1_000_000_000)
    return float(sec) + rest * 1e-9


def stamp(path, under=True):
    got = store.stamp(path)
    if got is not None:
        return got
    there = based(path) if under else None
    if there:
        return store.stamp(there)
    entry = packed(path)
    return None if entry is None else (entry[2], entry[1])


def exists(path):
    return stamp(path) is not None


def getmtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        there = based(path)
        if there:
            return os.path.getmtime(there)
        entry = packed(path)
        if entry is None:
            raise
        return seconds(entry[2])


def _group(pack, file):
    key = (_key(pack), file)
    with _lock:
        got = _groups.get(key)
        if got is not None:
            _groups.move_to_end(key)
            return got[0]
        loading = _loading.setdefault(key, threading.Lock())
    with loading:
        with _lock:
            got = _groups.get(key)
            if got is not None:
                _groups.move_to_end(key)
                return got[0]
        with open(os.path.join(pack, file), "rb") as f:
            raw = lzma.decompress(f.read())
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        size = sum(len(b) for b in files.values())
        with _lock:
            _groups[key] = (files, size)
            _held[0] += size
            while _held[0] > KEEP_BYTES and len(_groups) > 1:
                _, (_, gone) = _groups.popitem(last=False)
                _held[0] -= gone
            _loading.pop(key, None)
        return files


def packed_bytes(path):
    if not in_store(path):
        return None
    name = os.path.basename(path)
    got = index()
    while True:
        entry = got.get(name)
        if entry is None:
            return None
        file = got.file(entry[0])
        try:
            found = _group(PACK, file)
        except FileNotFoundError:
            found = None
        data = None if found is None else found.get(name)
        if data is not None:
            return data
        newer = index()
        if newer is got:
            raise ValueError(f"{PACK}: index.json names {name} in {file}, which "
                             f"{'is gone' if found is None else 'lacks it'}: pack it again")
        got = newer


def opened(path):
    try:
        return open(path, "rb")
    except FileNotFoundError:
        there = based(path)
        if there:
            return open(there, "rb")
        data = packed_bytes(path)
        if data is None:
            raise
        return io.BytesIO(data)


def base_bytes(path):
    there = based(path)
    if not there:
        return None
    with open(there, "rb") as f:
        return f.read()


def load_npz(path):
    got = arrays.load_npz(path)
    if got is not None or os.path.exists(path):
        return got
    data = base_bytes(path)
    data = packed_bytes(path) if data is None else data
    if data is None:
        return None
    try:
        with np.load(io.BytesIO(data)) as z:
            return {k: z[k] for k in z.files}
    except arrays.UNREADABLE:
        return None


def load_json(path, default, under=True):
    if os.path.exists(path) or not in_store(path):
        return store.load_json(path, default)
    data = base_bytes(path) if under else None
    data = packed_bytes(path) if data is None else data
    return default if data is None else json.loads(data.decode("utf-8"))


def touch(path, at):
    if not os.path.exists(path) and not based(path) and packed(path) is not None and not mainstores.in_main(PACK):
        mark(os.path.basename(path), round(at * 1e9))
        return
    make_loose(path)
    os.utime(path, (at, at))


def mark(name, ns):
    made = index()
    path = marks_path(PACK, made.run)
    line = f"{name}\t{ns}\n".encode("utf-8")
    with store.locked(path):
        first = not os.path.exists(path)
        with open(path, "a+b") as f:
            f.seek(0, os.SEEK_END)
            if f.tell():
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    line = b"\n" + line
            f.write(line)
        if first and index().run == made.run:
            own = os.path.basename(path)
            for other in os.listdir(os.path.dirname(path)):
                if other not in (own, own + ".lock"):
                    try:
                        os.remove(os.path.join(os.path.dirname(path), other))
                    except OSError:
                        pass
        read_marks(PACK, made)
        if made.mark_lines > COMPACT * max(len(made), 1):
            with made.marks_lock:
                data = b"".join(f"{n}\t{v}\n".encode("utf-8") for n, v in sorted(made.checked.items()))
            try:
                store.write_bytes(path, data)
            except PermissionError:
                return
            read_marks(PACK, made)


def make_loose(path):
    if os.path.exists(path):
        return
    data = base_bytes(path)
    data = packed_bytes(path) if data is None else data
    if data is None:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.endswith(".npz"):
        with np.load(io.BytesIO(data)) as z:
            arrays.save_npz(path, **{k: z[k] for k in z.files})
    else:
        store.write_bytes(path, data)


def packed_names(folder=None):
    folder = CACHE if folder is None else folder
    return set(index()) if _key(folder) == _key(CACHE) else set()


def loose(folder=None):
    folder = CACHE if folder is None else folder
    under = base() if _key(folder) == _key(CACHE) else None
    out = {}
    for top in ([under] if under else []) + [folder]:
        try:
            with os.scandir(top) as it:
                for e in it:
                    if e.is_file() and not e.name.endswith(".part") and ".unreadable-" not in e.name:
                        out[e.name] = e.stat()
        except FileNotFoundError:
            pass
    return out


def names(folder=None):
    folder = CACHE if folder is None else folder
    out = {}
    if _key(folder) == _key(CACHE):
        out = {n: (e[1], seconds(e[2])) for n, e in index().items() if n.endswith(".npz")}
    out.update({n: (st.st_size, st.st_mtime) for n, st in loose(folder).items() if n.endswith(".npz")})
    return out


def store_stamp(folder=None):
    folder = CACHE if folder is None else folder
    mine = _key(folder) == _key(CACHE)
    pack = store.stamp(os.path.join(PACK, "index.json")) if mine else None
    under = base() if mine else None
    if under:
        return store.stamp(folder), pack, store.stamp(under)
    return store.stamp(folder), pack
