# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import csv
import hashlib
import io
import json
import os
import re
import struct
import sys
import threading

import casc
import db2
import game
import gamefiles
import hotfix
import mainstores
import store
import storedonly
from game import installed_version

ROOT = os.path.dirname(os.path.abspath(__file__))
KEPT = os.path.join(ROOT, "data", "buildcache")
MISSING_SOURCE = "client files"
DEFS = os.path.join(ROOT, "data", "tabledefs")
TABLE_FILES = "db2files.csv"
DB2_FILES = "listfile-db2.csv"
MADE = "tables-made-{build}.json"
_older = {}
_make_lock = threading.RLock()
_told = set()
_read = {}
_said = {}


def path_of(table, build, folder=None):
    return os.path.join(folder or KEPT, f"{table.lower()}-{build}.csv")


def made_path(build, folder=None):
    return os.path.join(folder or KEPT, MADE.format(build=build))


def notes_of(build, folder=None):
    notes = store.load_json(made_path(build, folder), {})
    return notes if isinstance(notes, dict) else {}


def stood(table, build):
    path = mainstores.standing(path_of(table, build))
    return path, os.path.dirname(path)


def made_builds():
    head, tail = MADE.split("{build}")
    try:
        names = os.listdir(KEPT)
    except OSError:
        names = []
    found = [n[len(head):-len(tail)] for n in names if n.startswith(head) and n.endswith(tail)]
    return sorted((b for b in found if game.VERSION.fullmatch(b)), key=game.version_key, reverse=True)


def stored_build(table, build=None):
    return (stored_copy(table, build) or (None,))[0]


def stored_copy(table, build=None, exact=False):
    build = build or installed_version()
    main = mainstores.under(KEPT)
    for folder in [None] + ([main] if main else []):
        found = (build if os.path.exists(path_of(table, build, folder)) else None) if exact else \
            _stored_in(table, build, folder)
        if found:
            return found, folder
    return None


def _stored_in(table, build, folder=None):
    if os.path.exists(path_of(table, build, folder)):
        return build
    key = (table.lower(), build, folder)
    if key not in _older:
        _older[key] = max(_kept_builds(table, folder), key=game.version_key, default=None)
    return _older[key]


def _kept_builds(table, folder=None):
    prefix = f"{table.lower()}-"
    try:
        names = os.listdir(folder or KEPT)
    except OSError:
        names = []
    return [n[len(prefix):-4] for n in names if n.startswith(prefix) and n.endswith(".csv")
            and game.VERSION.fullmatch(n[len(prefix):-4])]


def _earlier(table, build):
    main = mainstores.under(KEPT)
    found = {b for folder in [None] + ([main] if main else []) for b in _kept_builds(table, folder)}
    return sorted((b for b in found if game.version_key(b) < game.version_key(build)), key=game.version_key,
                  reverse=True)



def _kept_read(path, parse):
    st = store.stamp(path)
    if st is None:
        return None
    held = _read.get(path)
    if held is None or held[0] != st:
        try:
            if os.path.isdir(path):
                held = _read[path] = (st, parse(None))
            else:
                held = _read[path] = (st, parse(gamefiles.read_part(path)))
        except FileNotFoundError:
            return None
    return held[1]


def _db2_files(data):
    out = {}
    for line in data.decode("utf-8", "replace").splitlines():
        fid, _, name = line.strip().partition(";")
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        if fid.isdigit() and base.lower().endswith(".db2"):
            out[base[:-4].lower()] = int(fid)
    return out


def db2_file(table):
    return (_kept_read(mainstores.standing(os.path.join(DEFS, TABLE_FILES)), _db2_files) or {}).get(table.lower())


def definition(table):
    defs = mainstores.standing(DEFS)
    try:
        names = _kept_read(defs, lambda _: {n[:-4].lower(): n for n in os.listdir(defs) if n.endswith(".dbd")})
    except OSError:
        return None
    name = (names or {}).get(table.lower())
    if not name:
        return None
    return _kept_read(os.path.join(defs, name), lambda data: (
        db2.parse_dbd(data.decode("utf-8")), hashlib.sha1(data).hexdigest()[:12]))


def _read_cache(data):
    try:
        return hotfix.read(data)
    except hotfix.Unreadable as e:
        return e


def _cache_path():
    folder = game.data_folder()
    tags =_kept_read(game.build_info_path(folder), lambda data: casc.build_info(
        data.decode("utf-8", "replace"), game.lead_product()).get("Tags", ""))
    return hotfix.path_of(folder, tags)


def _cache_now():
    try:
        path = _cache_path()
        return path, _kept_read(path, _read_cache)
    except (OSError, casc.LocalError, game.GameNotFound):
        return None


def hotfixes(build):
    now = _cache_now()
    if now is None:
        return None, None
    path, got = now
    if got is None:
        return None, "none"
    if isinstance(got, hotfix.Unreadable):
        return None, f"unreadable {store.stamp(path)}"
    if str(got.build) != build.rsplit(".", 1)[-1]:
        return None, f"build {got.build}"
    return got, None


def kept_hotfixes(build):
    try:
        path = _cache_path()
    except (OSError, casc.LocalError, game.GameNotFound):
        return None
    for p in [path] + hotfix.copies(path):
        try:
            got = _kept_read(p, _read_cache)
        except OSError:
            continue
        if isinstance(got, hotfix.Cache) and str(got.build) == build.rsplit(".", 1)[-1]:
            return got
    return None


def _hotfix_print(build, table_hash, installed=True):
    cache, why = hotfixes(build) if installed else (kept_hotfixes(build), None)
    return hotfix.signature(cache.of(table_hash)) if cache is not None else why



KEY_TABLES = {"TactKey": "Key", "TactKeyLookup": "TACTID"}
_held = {}


def key_name(name):
    return f"{name:016X}"


def keys(build):
    now = _cache_now()
    if now is None:
        return None
    cache = now[1] if isinstance(now[1], hotfix.Cache) else None
    made_of = [build, store.stamp(now[0])]
    for table in KEY_TABLES:
        try:
            defined = definition(table)
        except (OSError, ValueError):
            defined = None
        made_of.append((db2_file(table), defined[1] if defined else None))
    memo = tuple(made_of)
    if memo not in _held:
        held = {} if any(None in part for part in made_of[2:]) else _read_keys(build, cache)
        if held is None:
            return None
        _held.clear()
        _held[memo] = held
    return _held[memo]


def _read_keys(build, cache):
    columns = {}
    for table, column in KEY_TABLES.items():
        got = _read_install(table, build)
        if got is None:
            return None
        read, layout, _ = got
        try:
            rows = db2.rows(read, layout)
            ids = read.ids + [new for new, _ in read.copies]
            entries = cache.of(read.table_hash) if cache is not None else []
            rows, ids, _ = hotfix.apply(rows, ids, entries, lambda e: db2.hotfix_row(e.data, e.record_id, layout))
        except (ValueError, struct.error, IndexError, KeyError) as e:
            _said[table.lower()] = f"{type(e).__name__}: {e}"
            return {}
        at = next(i for i, c in enumerate(layout.columns) if c.name == column)
        columns[table] = {i: bytes(row[at]) for i, row in zip(ids, rows)}
    names = columns["TactKeyLookup"]
    return {int.from_bytes(names[i], "little"): key for i, key in columns["TactKey"].items()
            if i in names and len(names[i]) == 8 and len(key) == 16}


def keys_moved(note, build):
    locked = note.get("locked")
    if locked is None:
        return bool(note.get("encrypted rows"))
    opened = note.get("opened") or {}
    held = keys(build) if locked or opened else None
    if held is None:
        return False
    names = {key_name(n) for n in held}
    return any(n in names for n in locked) or any(n not in names for n in opened)


def keys_said(build=None):
    build = build or installed_version()
    held = keys(build)
    if held is None:
        return None
    names = {key_name(n) for n in held}
    counts = {}
    for csv_name, note in notes_of(build).items():
        if not isinstance(note, dict):
            continue
        sections = {**(note.get("locked") or {}), **(note.get("opened") or {})}
        rows = sum(n for name, n in sections.items() if name in names)
        if rows:
            counts[note.get("table") or csv_name.rsplit("-", 1)[0]] = rows
    return ", ".join(f"{t} {n:,}" for t, n in sorted(counts.items())) or "none"



EXISTS_IN = {"itemsparse": "Item"}
SIGNED = re.compile(r"[0-9a-f]{16}")
PLACEHOLDER = re.compile(r"<[^>]*>|[\(\[](?:UNUSED|NYI|TXT|DNT|PH)[\)\]]|\bzzOLD\b|\bDEPRECATED\b|^REMOVE\b"
                         r"|\(\d+\)[a-z]*$", re.I)
GAP = ("build ", "unreadable ")


def _gapped(note):
    word = note.get("hotfixes")
    return isinstance(word, str) and word.startswith(GAP) and "filled" not in note


def _unfilled(table, note):
    return _gapped(note) or (table.lower() in EXISTS_IN and SIGNED.fullmatch(str(note.get("hotfixes"))) is not None
                             and "filled" not in note)


def last_hotfixed(table, build):
    for b in made_builds():
        if game.version_key(b) >= game.version_key(build):
            continue
        note = notes_of(b).get(os.path.basename(path_of(table, b)))
        if isinstance(note, dict) and SIGNED.fullmatch(str(note.get("hotfixes"))) and os.path.exists(path_of(table, b)):
            return b
    return None


def _hotfixed(table_hash, last):
    cache = kept_hotfixes(last)
    if cache is None:
        return None, f"the game keeps no hotfix cache of {last}"
    final = {e.record_id: e.adds for e in cache.of(table_hash)}
    return ({rid for rid, adds in final.items() if adds}, {rid for rid, adds in final.items() if not adds}), None


def _still(table, build, hotfixed, why):
    parent = EXISTS_IN.get(table.lower())
    if parent:
        try:
            got = rows(parent, build, stored=True)
        except (storedonly.NotStored, OSError, ValueError) as e:
            return None, f"no {parent} table: {e}"
        return {int(r["ID"]) for r in got if (r.get("ID") or "").isdigit()}, parent
    return (hotfixed, "hotfixes") if hotfixed is not None else (None, why)


def _stored_lines(table, last, layout, want):
    out = {}
    old = csv.reader(io.StringIO(raw(table, last, stored=True).decode("utf-8"), newline=""))
    at = {name: n for n, name in enumerate(next(old, []))}
    if "ID" not in at:
        return out
    plan = [at.get(name) for name in db2.column_names(layout.columns)]
    for r in old:
        rid = r[at["ID"]] if len(r) > at["ID"] else ""
        if rid.isdigit() and int(rid) in want:
            out[int(rid)] = [db2.cell(r[n]) if n is not None and n < len(r) else None for n in plan]
    return out


def fill_gap(table, build, table_hash, csv_bytes, layout, have, last=None):
    last = last or last_hotfixed(table, build)
    if last is None:
        return csv_bytes, {"rows": 0}
    hotfixed, why = _hotfixed(table_hash, last)
    gave, deleted = hotfixed if hotfixed is not None else (None, set())
    still, test = _still(table, build, gave, why)
    have = set(have)
    want = still - have if still is not None else set()
    keep = gave & have if gave is not None else set()
    drop = deleted & have
    filled = {"rows": 0, "kept": 0, "dropped": 0, "from": last, "test": test}
    if hotfixed is None:
        filled["not kept"] = why
    try:
        stored = _stored_lines(table, last, layout, want | keep | drop) if want or keep or drop else {}
    except (OSError, csv.Error, UnicodeDecodeError) as e:
        return csv_bytes, dict(filled, test=f"{test}, the stored table unread: {e}")
    older, builds = _taken(table, last, layout, want - set(stored))
    if builds:
        filled["builds"] = builds
    kept = {rid: cells for rid, cells in stored.items() if rid in keep}
    drop -= set(stored)
    if kept or drop:
        own = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
        lines, at = [",".join(own[0])], own[0].index("ID")
        for r in own[1:]:
            rid = int(r[at]) if len(r) > at and r[at].isdigit() else None
            if rid in drop:
                filled["dropped"] += 1
                continue
            cells = [db2.cell(v) for v in r]
            old = kept.get(rid)
            if old is not None:
                taken = [o if o is not None else c for o, c in zip(old, cells)]
                filled["kept"] += taken != cells
                cells = taken
            lines.append(",".join(cells))
        csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    added = [cells for rid, cells in stored.items() if rid in want] + list(older.values())
    filled["rows"] = len(added)
    return csv_bytes + _lines_of(added, layout), filled


def fill_standing(table, build, csv_bytes, layout, have, gone=()):
    parent = EXISTS_IN.get(table.lower())
    if not parent:
        return csv_bytes, None
    still, test = _still(table, build, None, None)
    filled = {"rows": 0, "test": test, "standing": True}
    if still is None:
        return csv_bytes, filled
    taken, builds = _taken(table, build, layout, still - set(have) - set(gone))
    filled["rows"] = len(taken)
    if builds:
        filled["builds"] = builds
    return csv_bytes + _lines_of(list(taken.values()), layout), filled


def _taken(table, build, layout, want):
    got, builds, left = {}, {}, set(want)
    for b in _earlier(table, build) if left else ():
        try:
            lines = _stored_lines(table, b, layout, left)
        except (OSError, csv.Error, UnicodeDecodeError, storedonly.NotStored):
            continue
        if lines:
            got.update(lines)
            builds[b] = len(lines)
            left -= set(lines)
        if not left:
            break
    return got, builds


def _lines_of(rows, layout):
    blanks = ["" if col.kind in ("string", "locstring") else "0"
              for col in layout.columns for _ in db2.column_names([col])]
    lines = [",".join(c if c is not None else b for c, b in zip(cells, blanks)) for cells in rows]
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def from_install(table, build):
    if os.environ.get(casc.OFF):
        return None
    cache, why = hotfixes(build)
    if cache is None and why is None:
        _said[table.lower()] = "the game's hotfix cache can't be read this moment"
        return None
    held = keys(build)
    if held is None:
        _said[table.lower()] = "the keys the client holds can't be read this moment"
        return None
    got = _read_install(table, build, held)
    if got is None:
        return None
    read, layout, definition_print = got
    try:
        rows = db2.rows(read, layout)
        ids = read.ids + [new for new, _ in read.copies]
        entries = cache.of(read.table_hash) if cache is not None else []
        rows, ids, counts = hotfix.apply(rows, ids, entries, lambda e: db2.hotfix_row(e.data, e.record_id, layout))
        csv_bytes = db2.csv_of(rows, layout)
        if cache is None:
            csv_bytes, filled = fill_gap(table, build, read.table_hash, csv_bytes, layout, ids)
        else:
            final = {e.record_id: e.adds for e in entries}
            csv_bytes, filled = fill_standing(table, build, csv_bytes, layout, ids,
                                              {rid for rid, adds in final.items() if not adds})
    except (ValueError, struct.error, IndexError, KeyError) as e:
        _said[table.lower()] = f"{type(e).__name__}: {e}"
        return None
    note = {"hash": read.table_hash, "hotfixes": hotfix.signature(entries) if cache is not None else why,
            "definition": definition_print, "encrypted rows": sum(n for _, n in read.encrypted), "table": table,
            "locked": _by_key(read.encrypted), "opened": _by_key(read.opened)}
    if filled is not None:
        note["filled"] = filled
    _said.pop(table.lower(), None)
    return csv_bytes, note, counts


def _own(note):
    word = str(note.get("hotfixes"))
    return word == "none" or SIGNED.fullmatch(word) is not None


def from_kept(table, build, path, note):
    cache = kept_hotfixes(build)
    if cache is None or note.get("hash") is None:
        return None
    try:
        defined = definition(table)
        layout = defined[0].layout(None, build) if defined else None
        if layout is None:
            return None
        with open(path, encoding="utf-8", newline="") as f:
            lines = list(csv.reader(f))
        names = db2.column_names(layout.columns)
        at = names.index("ID") if "ID" in names else None
        if not lines or lines[0] != names or at is None or any(len(r) <= at or not r[at].isdigit() for r in lines[1:]):
            return None
        entries = cache.of(note["hash"])
        rows, _, counts = hotfix.apply(
            [[db2.cell(v) for v in r] for r in lines[1:]], [int(r[at]) for r in lines[1:]], entries,
            lambda e: [db2.cell(v) for values in db2.hotfix_row(e.data, e.record_id, layout) for v in values])
    except (OSError, ValueError, csv.Error):
        return None
    data = ("\n".join(",".join(r) for r in [names] + rows) + "\n").encode("utf-8")
    return data, dict(note, hotfixes=hotfix.signature(entries)), counts


def _by_key(sections):
    out = {}
    for name, rows in sections:
        out[key_name(name)] = out.get(key_name(name), 0) + rows
    return out


def _read_install(table, build, held=None):
    if os.environ.get(casc.OFF):
        return None
    fid, defined = db2_file(table), None
    try:
        defined = definition(table)
    except (OSError, ValueError) as e:
        _said[table.lower()] = f"definition: {e}"
    if fid is None or defined is None:
        _said.setdefault(table.lower(), "no file ID" if fid is None else "no definition")
        return None
    before = casc.counts()
    got = casc.read_clear(fid, build, held)
    if got is None:
        kind = next((k for k, n in casc.counts().items() if n > before.get(k, 0)), "error")
        _said[table.lower()] = {"missing": "the install hasn't got its file", "build": "another build installed",
                                "encrypted": "its file is encrypted"}.get(kind) or f"install: {casc.last_error()}"
        return None
    data, zeros = got
    dbd, definition_print = defined
    try:
        layout = dbd.layout(db2.HEAD.unpack_from(data)[8], build) if len(data) >= db2.HEAD.size else None
        if layout is None:
            raise db2.Unreadable("not a DB2 file")
        return db2.read_wdc5(data, zeros, layout.columns), layout, definition_print
    except (ValueError, struct.error, IndexError, KeyError) as e:
        _said[table.lower()] = f"{type(e).__name__}: {e}"
        return None


def local(table, build):
    try:
        if os.environ.get(casc.OFF):
            return False
        installed = build == installed_version()
    except (OSError, game.GameNotFound):
        return False
    path, folder = stood(table, build)
    note = notes_of(build, folder).get(os.path.basename(path))
    stored = isinstance(note, dict) and bool(note) and os.path.exists(path)
    if not installed and not (stored and _own(note)):
        return False
    if stored and _hotfix_print(build, note.get("hash"), installed) in (None, note.get("hotfixes")):
        if not installed:
            return True
        defined = None
        try:
            defined = definition(table)
        except (OSError, ValueError):
            pass
        if (note.get("hotfixes") is not None and defined is not None and defined[1] == note.get("definition")
                and not _unfilled(table, note) and not keys_moved(note, build)):
            return True
    with _make_lock:
        made = from_install(table, build) if installed else from_kept(table, build, path, note)
        if made is None:
            return not installed
        data, note, _ = made
        _keep_made(table, build, data, note)
    return True


def _keep_made(table, build, data, note):
    os.makedirs(KEPT, exist_ok=True)
    path = path_of(table, build)
    store.write_fetched(path, data)
    with store.locked(made_path(build)):
        notes = notes_of(build)
        notes[os.path.basename(path)] = note
        store.save_json(made_path(build), notes)


def settle_gap(build, last):
    if game.version_key(last) >= game.version_key(build):
        return {"": f"{last} isn't before {build}: the gap rule takes the rows of a hotfixed build before it"}
    try:
        if build == installed_version():
            return {"": f"{build} is the installed build: its tables are made from the install"}
    except (OSError, game.GameNotFound):
        pass
    hashes = {}
    for b in made_builds():
        for name, note in notes_of(b).items():
            if isinstance(note, dict) and note.get("hash") is not None:
                hashes.setdefault(name.rpartition("-")[0], note["hash"])
    out = {}
    suffix = f"-{build}.csv"
    for name in sorted(n for n in os.listdir(KEPT) if n.endswith(suffix)):
        table = name[:-len(suffix)]
        try:
            defined = definition(table)
            layout = defined[0].layout(None, build) if defined else None
        except (OSError, ValueError) as e:
            out[table] = f"no definition: {e}"
            continue
        if layout is None:
            out[table] = "no definition"
            continue
        if table not in hashes:
            out[table] = "no table hash: no note of the table"
            continue
        if not os.path.exists(path_of(table, last)):
            out[table] = f"no stored table of {last}"
            continue
        with open(path_of(table, build), "rb") as f:
            data = f.read()
        text = data.decode("utf-8")
        own = csv.reader(io.StringIO(text))
        head = next(own, [])
        if head != db2.column_names(layout.columns) or "ID" not in head:
            out[table] = f"its columns aren't WoWDBDefs' layout for {build}"
            continue
        at = head.index("ID")
        have = [int(r[at]) for r in own if len(r) > at and r[at].isdigit()]
        with _make_lock:
            got, filled = fill_gap(table, build, hashes[table], data, layout, have, last)
            if got != data:
                _keep_made(table, build, got, {"hash": hashes[table], "hotfixes": f"build {last.rsplit('.', 1)[-1]}",
                                               "definition": defined[1], "filled": filled})
        out[table] = filled
    return out


def local_said():
    return dict(_said)


def raw(table, build=None, check=None, stored=False):
    asked, build = build, build or installed_version()
    made = local(table, build)
    path, _ = stood(table, build)
    if not made and not os.path.exists(path):
        outside = None if stored else storedonly.sources()
        if outside is None:
            found = stored_copy(table, build, exact=bool(asked))
            if found is None:
                raise storedonly.NotStored(f"Not stored yet: the client's {table} of {build}")
            path = path_of(table, *found)
        else:
            data = outside.table(table, build)
            if check and not check(data):
                raise ValueError(f"the answer for {table} of {build} isn't the table")
            path = path_of(table, build)
            os.makedirs(KEPT, exist_ok=True)
            store.write_fetched(path, data)
    with open(path, "rb") as f:
        return f.read()


def filled(table, build):
    path, folder = stood(table, build)
    notes = _kept_read(made_path(build, folder), lambda data: json.loads(data.decode("utf-8"))) or {}
    note = notes.get(os.path.basename(path)) if isinstance(notes, dict) else None
    return (note.get("filled") or {}) if isinstance(note, dict) else {}


def rows(table, build=None, stored=False):
    got = list(csv.DictReader(io.StringIO(raw(table, build, stored=stored).decode("utf-8"))))
    try:
        build = build or installed_version()
        gave = filled(table, build) if (table, build) not in _told else {}
    except (OSError, ValueError, game.GameNotFound):
        gave = {}
    older = ", ".join(f"{b} {n:,}" for b, n in (gave.get("builds") or {}).items())
    if gave.get("standing") and gave.get("rows"):
        _told.add((table, build))
        print(f"{table} of {build}: {gave['rows']:,} rows are filled from earlier builds' tables ({older}). Each filled "
              f"row is one whose record is still in this build's {gave.get('test')} table, where the game's hotfixes "
              f"for {build} haven't given the row yet.")
    elif gave.get("rows") or gave.get("kept") or gave.get("dropped"):
        _told.add((table, build))
        test, last = gave.get("test"), gave.get("from")
        why = (f"its record is still in this build's {test} table" if test != "hotfixes" else
               "the row came from that build's hotfixes, which the game still keeps")
        said = [f"{table} of {build}: the game hasn't logged in on {build} yet, so this build's table is its archive "
                f"file alone. {last} is the last build whose hotfixes were applied."]
        if gave.get("rows"):
            said.append(f"{gave['rows']:,} rows are filled from {last}. Each filled row is one the table lacks where "
                        f"{why}.")
        if older:
            said.append(f"Of those, the rows {last}'s stored table lacks come from older builds' tables ({older}).")
        if gave.get("kept"):
            said.append(f"{gave['kept']:,} rows keep {last}'s values. Each kept row is one {last}'s hotfixes gave "
                        f"that this build's file holds at its own values.")
        if gave.get("dropped"):
            said.append(f"{gave['dropped']:,} rows are left out. Each one is a row {last}'s hotfixes deleted that "
                        f"this build's file still holds.")
        print(" ".join(said))
    return got


def main(argv):
    if len(argv) != 4 or argv[1] != "settle":
        raise SystemExit("python client.py settle BUILD LAST")
    import jsontext
    print(jsontext.dumps(settle_gap(argv[2], argv[3]), 1))


if __name__ == "__main__":
    main(sys.argv)
