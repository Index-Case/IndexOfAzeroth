# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os
import struct

import store

MAGIC = b"XFTH"
HEAD = struct.Struct("<4sII32s")
ENTRY = struct.Struct("<4siiIIIIB3x")
VALID = 1
VERSIONS = (9,)
KEEP_CACHED = {3744420815, 35137211}


class Unreadable(ValueError):
    pass


class Entry:
    __slots__ = ("region", "push", "unique", "table_hash", "record_id", "status", "data")

    def __init__(self, region, push, unique, table_hash, record_id, status, data):
        self.region, self.push, self.unique, self.table_hash = region, push, unique, table_hash
        self.record_id, self.status, self.data = record_id, status, data

    @property
    def adds(self):
        return self.status == VALID and len(self.data) > 0


class Cache:
    def __init__(self, version, build, entries):
        self.version, self.build, self.entries = version, build, entries
        self._by_table = None

    def of(self, table_hash):
        if self._by_table is None:
            by = {}
            for e in self.entries:
                by.setdefault(e.table_hash, []).append(e)
            self._by_table = {h: sorted(es, key=lambda e: e.push) for h, es in by.items()}
        return self._by_table.get(table_hash, [])

    def tables(self):
        self.of(0)
        return dict(self._by_table)


def read(data):
    if len(data) < HEAD.size:
        raise Unreadable("a DBCache.bin cut short")
    magic, version, build, _ = HEAD.unpack_from(data)
    if magic != MAGIC:
        raise Unreadable("not a DBCache.bin")
    if version not in VERSIONS:
        raise Unreadable(f"DBCache.bin version {version}")
    at, entries = HEAD.size, []
    while at < len(data):
        if at + ENTRY.size > len(data):
            raise Unreadable("an entry cut short")
        magic, region, push, unique, table_hash, record_id, size, status = ENTRY.unpack_from(data, at)
        if magic != MAGIC:
            raise Unreadable(f"an entry without its magic at {at}")
        at += ENTRY.size
        if at + size > len(data):
            raise Unreadable("an entry's data cut short")
        entries.append(Entry(region, push, unique, table_hash, record_id, status, data[at:at + size]))
        at += size
    return Cache(version, build, entries)


def signature(entries):
    h = hashlib.sha1()
    for e in entries:
        h.update(struct.pack("<iIBI", e.push, e.record_id, e.status, len(e.data)))
        h.update(e.data)
    return h.hexdigest()[:16] if entries else "none"


def apply(rows, ids, entries, decode):
    rows, ids = list(rows), list(ids)
    at = {i: n for n, i in enumerate(ids)}
    gone = set()
    counts = dict.fromkeys(("added", "changed", "deleted", "same"), 0)
    keep = bool(entries) and entries[0].table_hash in KEEP_CACHED and any(
        e.adds and e.push == -1 for e in entries)
    for e in entries:
        n = at.get(e.record_id)
        if n is not None and n in gone:
            n = None
        if e.adds:
            row = decode(e)
            if n is None:
                at[e.record_id] = len(rows)
                rows.append(row)
                ids.append(e.record_id)
                counts["added"] += 1
            elif rows[n] == row:
                counts["same"] += 1
            else:
                rows[n] = row
                counts["changed"] += 1
        elif not keep and n is not None:
            gone.add(n)
            counts["deleted"] += 1
    if gone:
        rows = [r for n, r in enumerate(rows) if n not in gone]
        ids = [i for n, i in enumerate(ids) if n not in gone]
    return rows, ids, counts


def locale_of(tags):
    for part in (tags or "").split(":"):
        if part.strip().endswith("text?"):
            for word in part.split():
                if len(word) == 4 and word[:2].islower() and word[2:].isupper():
                    return word
    return "enUS"


def path_of(folder, tags=""):
    return os.path.join(folder, "Cache", "ADB", locale_of(tags), "DBCache.bin")


def copies(path):
    folder, name = os.path.split(path)
    try:
        found = [os.path.join(folder, n) for n in os.listdir(folder)
                 if n.startswith(name) and n.endswith(".tmp") and n[len(name):-4].isdigit()]
    except OSError:
        return []
    stamped = [(st, p) for p in found for st in [store.stamp(p)] if st is not None]
    return [p for st, p in sorted(stamped, reverse=True)]
