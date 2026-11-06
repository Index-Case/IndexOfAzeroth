# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os
import re
import time

import numpy as np

import arrays
import casc
import client
import nav
import navfill
from serverlog import append_log
import navstore
import store
from nav import wm

NAV_KINDS = ("adt", "obj", "tex0", "wdt", "wmo", "wmog", "m2", "skin")
MODEL_KINDS = ("wmo", "wmog", "m2", "skin")
COPY = re.compile(r"([a-z0-9]+)-(\d+)\.[a-z0-9]+")
KEYS = re.compile(r"keys-(.+)\.npz")
BUILDING_KEY = nav.PLACED_NAME
PROPS_KEY = re.compile(r"(\d+)-props-(-?\d+)-(-?\d+)")
TILE_KEY = re.compile(r"(\d+)_(\d+)_(\d+)")
CHECK_SECONDS, PACKED_CHECK_SECONDS = 0.32, 0.54
TIMED_LEAST = 20
LONG = 1800


def copy_id(name):
    m = COPY.fullmatch(name)
    return (m[1], int(m[2])) if m else None


def keys_path(build, folder=None):
    return os.path.join(folder or nav.CACHE, f"keys-{build}.npz")


def file_piece(name):
    m = nav.KEPT_NAME.fullmatch(name)
    if not m or m[3] == "b":
        return None, False
    kind, key = m[3], m[5]
    if kind in ("t", "r", "v"):
        t = TILE_KEY.fullmatch(key)
        return (({"t": "tiles", "r": "roads", "v": "graph"}[kind], int(t[1]), key) if t else None), False
    if kind == "g":
        return ("shapes", None, key), False
    p = PROPS_KEY.fullmatch(key)
    if p:
        return ("doodads", int(p[1]), key), m[2] is not None
    b = BUILDING_KEY.fullmatch(key)
    return (("buildings", int(b[1]), key) if b else None), m[2] is not None


class Keys:

    def __init__(self, build, since, keys, maps):
        self.build, self.since, self.keys, self.maps = build, float(since), keys, maps

    def save(self, folder=None):
        path = keys_path(self.build, folder)
        fids = np.array(sorted(self.keys), np.int64)
        ids = np.array(sorted(self.maps), np.int64)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        arrays.save_npz(path, build=np.array(self.build), since=np.array(self.since), fids=fids,
                        ckeys=np.array([np.frombuffer(self.keys[f], np.uint8) for f in fids.tolist()], np.uint8).reshape(-1, 16),
                        map_ids=ids, map_digests=np.array([np.frombuffer(self.maps[i][0], np.uint8) for i in ids.tolist()],
                                                          np.uint8).reshape(-1, 20),
                        map_wdts=np.array([self.maps[i][1] for i in ids.tolist()], np.int64))
        return path

    @classmethod
    def load(cls, path):
        z = navstore.load_npz(path)
        try:
            return cls(str(z["build"]), float(z["since"]),
                       {int(f): k.tobytes() for f, k in zip(z["fids"], z["ckeys"])},
                       {int(i): (d.tobytes(), int(w)) for i, d, w in zip(z["map_ids"], z["map_digests"], z["map_wdts"])})
        except (TypeError, KeyError, ValueError):
            return None


def kept_builds(folder=None):
    names = navstore.names(folder or nav.CACHE)
    return sorted(m[1] for m in (KEYS.fullmatch(n) for n in names) if m)


def last_keys(before, folder=None):
    got = [k for k in (Keys.load(keys_path(b, folder)) for b in kept_builds(folder) if b != before) if k is not None]
    return max(got, key=lambda k: k.since) if got else None


def map_rows_digest(rows):
    out = {}
    for r in rows:
        text = "\x1f".join(f"{k}={r[k]}" for k in sorted(r))
        out[int(r["ID"])] = (hashlib.sha1(text.encode("utf-8")).digest(), int(r.get("WdtFileDataID") or 0))
    return out


def copies(folder=None, kinds=NAV_KINDS):
    out = {}
    try:
        with os.scandir(folder or wm.CACHE) as it:
            for e in it:
                got = copy_id(e.name)
                if got and (kinds is None or got[0] in kinds):
                    out[e.name] = (*got, e.stat().st_mtime)
    except FileNotFoundError:
        pass
    return out


def note_keys(build=None, extra=(), folder=None, copies_of=copies, rows=None, keys_of=casc.content_keys):
    try:
        build = build or wm.installed_version()
    except OSError:
        return None
    since = wm.switched_since()
    if wm.switched_build() != build or not since:
        return None
    fids = {c[1] for c in copies_of().values()} | {int(f) for f in extra}
    kept = Keys.load(keys_path(build, folder))
    if kept is not None and kept.build == build:
        fids |= set(kept.keys)
    keys = keys_of(sorted(fids), build)
    if keys is None:
        return None
    try:
        rows = client.rows("Map", build) if rows is None else rows
    except OSError:
        return None
    return Keys(build, since, keys, map_rows_digest(rows)).save(folder)


DIFFERENT_SAID = 5


def compare_copies(before=None, folder=None, keys_of=casc.content_keys, clock=time.time):
    try:
        build = wm.installed_version()
    except OSError:
        return None
    since = wm.switched_since()
    if wm.switched_build() != build or not since:
        return None
    at = clock()
    kept = {n: c for n, c in copies(folder, kinds=None).items() if c[2] >= since}
    keys = keys_of(sorted({c[1] for c in kept.values()}), build)
    if keys is None:
        return None
    before = before or {}
    carried = before.get("build") == build and before.get("since") == since
    after = float(before.get("at") or 0) if carried else 0.0
    different = {n for n in before.get("different") or () if n in kept and kept[n][2] < after} if carried else set()
    read = 0
    for name, (_, fid, mt) in sorted(kept.items()):
        if fid not in keys or mt < after:
            continue
        try:
            with open(os.path.join(folder or wm.CACHE, name), "rb") as f:
                digest = hashlib.md5(f.read()).digest()
        except OSError:
            continue
        read += 1
        if digest != keys[fid]:
            different.add(name)
    absent = sum(1 for c in kept.values() if c[1] not in keys)
    return {"build": build, "since": since, "at": at, "read": read, "same": len(kept) - absent - len(different),
            "absent": absent, "different": sorted(different)}


def copies_line(got):
    diff = got["different"]
    said = f"{len(diff):,} different" + (f": {', '.join(diff[:DIFFERENT_SAID])}" if diff else "") + (
        f" and {len(diff) - DIFFERENT_SAID:,} more" if len(diff) > DIFFERENT_SAID else "")
    return (f"the game's archives against our kept client files for build {got['build']}: {got['read']:,} copies read, "
            f"{got['same']:,} the same, {got['absent']:,} not in the install, {said}")


def note_copies(got, log, clock=time.time):
    if got and got["read"]:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(clock()))
        append_log(log, f"{stamp} navigation: {copies_line(got)}\n")


class KeyPass:

    def __init__(self, old, new, since, new_maps, folder=None, names=None, copies_now=None, marks=nav.kept_marks,
                 tile_parts=navfill.tile_parts, touch=wm.touch, clock=time.time, rules=None):
        self.old, self.new, self.since, self.new_maps = old, new, since, new_maps
        self.rules = rules or nav.code_rules()
        self.folder = folder or nav.CACHE
        self.names = navstore.names(self.folder) if names is None else names
        self.copies = copies() if copies_now is None else copies_now
        self.marks, self.tile_parts, self.touch, self.clock = marks, tile_parts, touch, clock
        self.changed = {f for f, k in old.keys.items() if new.get(f) != k}
        kinds = {c[1]: c[0] for c in self.copies.values()}
        self.models_changed = any(kinds.get(f, MODEL_KINDS[0]) in MODEL_KINDS for f in self.changed)
        self.seen = set()
        self.dirty_maps = {i for i, (digest, wdt) in new_maps.items()
                           if old.maps.get(i, (None,))[0] != digest or wdt not in old.keys or wdt in self.changed}

    def judge(self, sources):
        if not sources:
            return "check"
        said = "same"
        for s in sources:
            got = copy_id(s)
            if not got:
                return "check"
            self.seen.add(got[1])
            if got[1] not in self.old.keys:
                said = "check"
            elif got[1] in self.changed:
                return "changed"
        return said

    def path(self, name):
        return os.path.join(self.folder, name)

    def run(self, dry=False):
        t0 = self.clock()
        old_since = self.old.since
        kept, left = {}, {}
        dirty_tiles, moved = set(), set()
        current = {n: v for n, v in self.names.items() if nav.name_under(n, self.rules) == n}
        for name, (_, mt) in current.items():
            piece, _ = file_piece(name)
            if not piece or piece[0] not in ("tiles", "roads", "graph"):
                continue
            said = "check" if mt < old_since else self.judge((self.marks(self.path(name)) or {}).get("sources"))
            if said != "same":
                if piece[0] == "tiles":
                    dirty_tiles.add(piece[2])
                if mt < self.since:
                    left[name] = said
            elif mt < self.since:
                kept[name] = piece[0]
        for key in dirty_tiles:
            inst, col, row = map(int, key.split("_"))
            got = self.tile_parts(self.path(navfill.tile_name(inst, col, row, self.rules)))
            moved.update((inst, int(p[1])) for p in (got[0] if got else ()))
        joins = {}
        for name, (_, mt) in current.items():
            piece, is_joins = file_piece(name)
            if not piece or piece[0] in ("tiles", "roads", "graph") or mt >= self.since:
                continue
            if mt < old_since:
                left[name] = "check"
                continue
            if piece[0] != "shapes" and self.moved(piece, dirty_tiles, moved):
                left[name] = "check"
                continue
            marks = self.marks(self.path(name))
            if marks is None:
                said = "check"
            elif marks.get("empty"):
                said = "check" if self.models_changed else "same"
            else:
                said = self.judge(marks["sources"])
            if said != "same":
                left[name] = said
            elif is_joins:
                joins[name] = piece[0]
            else:
                kept[name] = piece[0]
        for name, kind in sorted(joins.items(), key=lambda nk: len(nav.made_from(nk[0]))):
            sources = nav.made_from(name)
            times = [current[s][1] if s in current else None for s in sources]
            if all(s in kept or (t is not None and t >= self.since) for s, t in zip(sources, times)) \
                    and nav.as_new(current[name][1], times):
                kept[name] = kind
            else:
                left[name] = "check"
        copies_kept = [n for n, (_, fid, mt) in self.copies.items()
                       if fid in self.old.keys and fid not in self.changed and old_since <= mt < self.since]
        if not dry:
            for name in sorted(kept, key=lambda n: (kept[n] == "graph", len(nav.made_from(n)))):
                self.touch(self.path(name))
            now = self.clock()
            for name in copies_kept:
                os.utime(os.path.join(wm.CACHE, name), (now, now))
        return {"kept": kept, "left": left, "copies": len(copies_kept), "changed": sorted(self.changed),
                "dirty": sorted(self.dirty_maps), "seconds": round(self.clock() - t0, 1)}

    def moved(self, piece, dirty_tiles, moved):
        kind, inst, key = piece
        if inst in self.dirty_maps:
            return True
        if kind == "buildings":
            return (inst, int(BUILDING_KEY.fullmatch(key)[3])) in moved
        p = PROPS_KEY.fullmatch(key)
        return any(f"{inst}_{c}_{r}" in dirty_tiles for c, r in reach_tiles(int(p[2]), int(p[3])))


def reach_tiles(gn, gw):
    top, left, bottom, right = nav.props_bounds(gn, gw)
    ra, ca = nav.cell_of(top + 10, left + 10)
    rb, cb = nav.cell_of(bottom - 10, right - 10)
    return nav.Terrain.needed(ra, ca, rb + 1, cb + 1)


def key_pass(build=None, folder=None, dry=False, say=print, keys_of=casc.content_keys, rows=None, **seams):
    build = build or wm.installed_version()
    since = wm.switched_since()
    old = last_keys(build, folder)
    if old is None or wm.switched_build() != build or old.since >= since:
        return None
    new = keys_of(sorted(old.keys), build)
    if new is None:
        return None
    rows = client.rows("Map", build) if rows is None else rows
    kp = KeyPass(old, new, since, map_rows_digest(rows), folder=folder, **seams)
    got = kp.run(dry=dry)
    if not dry:
        note_keys(build, extra=kp.seen, folder=folder, keys_of=keys_of, rows=rows)
        say(f"key pass from {old.build} to {build}: {len(got['kept']):,} kept with no read, {len(got['left']):,} left "
            f"to the byte check, {len(got['changed']):,} client files changed, {got['seconds']} s")
    return got



def piece_counts(names):
    out = {k: set() for k in navfill.KINDS}
    for name in names:
        piece, _ = file_piece(name)
        if piece and piece[0] in out:
            out[piece[0]].add(piece[1:])
    return out


def rule_changes(was, now):
    was = dict(was or {})
    if "props" not in was and "layers" in was:
        was["props"] = was["layers"]
    return [k for k in now if was.get(k) != now[k]]


def rebuilt_by_rules(changed):
    kinds = set()
    if "terrain" in changed:
        kinds |= {"tiles", "buildings", "doodads"}
    if {"shapes", "joins"} & set(changed):
        kinds |= {"buildings", "doodads"}
    if "layers" in changed:
        kinds |= {"buildings"}
    if "props" in changed:
        kinds |= {"doodads"}
    if "roads" in changed:
        kinds |= {"roads"}
    if {"terrain", "roads", "joins", "layers", "graph"} & set(changed):
        kinds |= {"graph"}
    return kinds


def piece_seconds(state):
    took = (state or {}).get("took") or {}
    defaults = {**navfill.DEFAULT_SECONDS, "stale": CHECK_SECONDS}
    out = {}
    for k in navfill.KINDS + ("stale",):
        n, secs = (took.get(k) or (0, 0.0))[:2]
        out["check" if k == "stale" else k] = secs / n if n >= TIMED_LEAST else defaults[k]
    return out


def packed_only(folder=None):
    folder = folder or nav.CACHE
    try:
        loose = set(os.listdir(folder))
    except FileNotFoundError:
        loose = set()
    return navstore.packed_names(folder) - loose


def stale_files(maps, names, since=None, rules=None):
    since = wm.switched_since() if since is None else since
    rules = rules or nav.code_rules()
    return {f: "check" for p in navfill.stale(maps, names, since, rules=rules) for f in navfill.piece_files(p, rules)
            if f in names and names[f][1] < since}


def pass_due(state, build):
    return not (state.get("state") == "done" and state.get("build") == build
                and float(state.get("since") or 0) >= wm.switched_since())


def keys_left(state, build, run_pass):
    if not pass_due(state, build):
        return None, False
    got = run_pass()
    return (None, True) if got is None else (got["left"], False)


def verdict(build, state, names, missing=None, left=None, stale=None, rules=None, by_bytes=False, map_names=None,
            packed=(), workers=navfill.FILL_WORKERS, clock=time.time):
    rules = nav.code_rules() if rules is None else rules
    changed = rule_changes(state.get("rules"), rules)
    have = piece_counts(names)
    build_set = {k: set() for k in navfill.KINDS}
    check_set = {k: set() for k in navfill.KINDS}
    slow = set()
    for k in rebuilt_by_rules(changed):
        build_set[k] |= have[k]
    for k, pieces in (missing or {}).items():
        build_set[k] |= set(pieces)
    for name, said in (left if left is not None else stale or {}).items():
        piece, _ = file_piece(name)
        if piece and piece[0] in build_set:
            (build_set if said == "changed" else check_set)[piece[0]].add(piece[1:])
            if name in packed:
                slow.add(piece)
    for k in navfill.KINDS:
        check_set[k] -= build_set[k]
    secs = piece_seconds(state)
    slow = sum(1 for p in slow if p[1:] in check_set[p[0]])
    maps = {}
    for k in navfill.KINDS:
        for which, pieces in (("build", build_set[k]), ("check", check_set[k])):
            for inst, _ in pieces:
                m = maps.setdefault(inst, {"name": (map_names or {}).get(inst) or f"map {inst}",
                                           **{kk: 0 for kk in navfill.KINDS}, "checks": 0})
                m[k if which == "build" else "checks"] += 1
    totals = {k: len(build_set[k]) for k in navfill.KINDS}
    totals["checks"] = sum(len(v) for v in check_set.values())
    seconds = (sum(totals[k] * secs[k] for k in navfill.KINDS) + (totals["checks"] - slow) * secs["check"]
               + slow * PACKED_CHECK_SECONDS) / max(1, workers)
    every = sum(len(v) for v in have.values())
    built = sum(totals[k] for k in navfill.KINDS)
    said = ("nothing" if not built and not totals["checks"] else "check" if not built
            else "whole" if built >= every else "part")
    return {"build": build, "from": state.get("build"), "rules": changed, "verdict": said, "maps": dict(sorted(maps.items())),
            "totals": totals, "seconds": round(seconds), "at": round(clock()), "by_bytes": by_bytes}


def duration(seconds):
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def verdict_lines(v, workers=navfill.FILL_WORKERS):
    t = v["totals"]
    why = []
    if v["from"] != v["build"]:
        why.append(f"build {v['build']} after {v['from'] or 'none'}" + (", no keys kept to compare: every piece is "
                                                                         "checked by its bytes" if v["by_bytes"] else ""))
    if v["rules"]:
        why.append("rules changed: " + ", ".join(v["rules"]))
    head = f"Navigation check for build {v['build']}: "
    if v["verdict"] == "nothing":
        return [head + "nothing to rebuild" + (f" ({'. '.join(why)})" if why else "")]
    parts = [f"{t[k]:,} {navfill.PHASE_WORDS[k]}" for k in navfill.KINDS if t[k]]
    if t["checks"]:
        parts.append(f"{t['checks']:,} pieces checked by their bytes")
    said = "nothing to rebuild, " if v["verdict"] == "check" else f"rebuild in {v['verdict']}: "
    lines = [head + said + f"{', '.join(parts)}, about {duration(v['seconds'])} on {workers} workers"]
    if why:
        lines.append("why: " + ". ".join(why))
    for inst, m in v["maps"].items():
        parts = [f"{m[k]:,} {navfill.PHASE_WORDS[k]}" for k in navfill.KINDS if m[k]]
        if m["checks"]:
            parts.append(f"{m['checks']:,} checked")
        lines.append(f"  {inst!s:>5} {m['name'][:32]:32s} {', '.join(parts)}")
    return lines


def missing_pieces(maps):
    out = {k: set() for k in navfill.KINDS}
    for m in maps.values():
        for k in navfill.KINDS:
            for p in m["missing"].get(k, ()):
                piece, _ = file_piece(navfill.piece_files(p)[0])
                if piece:
                    out[k].add(piece[1:])
    return out


def check_now(rules=None, state_path=navfill.STATE, names=None, maps=None, dry_pass=None):
    state = store.load_json(state_path, {})
    build = wm.installed_version()
    names = navstore.names() if names is None else names
    code = nav.code_rules()
    maps = navfill.survey(names=names, rules=code) if maps is None else maps
    left, by_bytes = keys_left(state, build, dry_pass or (lambda: key_pass(build, dry=True)))
    return verdict(build, state, names, missing=missing_pieces(maps), left=left, stale=stale_files(maps, names, rules=code),
                   rules=rules, by_bytes=by_bytes, map_names={i: m["name"] for i, m in maps.items()},
                   packed=packed_only())


def note_verdict(v, path, log):
    v = {**v, "long": v["verdict"] != "nothing" and v["seconds"] >= LONG}
    store.save_json(path, v)
    if v["verdict"] != "nothing":
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v["at"]))
        append_log(log, "".join(f"{stamp} navigation: {line}\n" for line in verdict_lines(v)))
    return v
