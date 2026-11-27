# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.error

import client
import datafiles
import jsontext
import store
import storedonly

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
KINDS = {
    "items": [("ItemSparse", "ID", "stats"), ("Item", "ID", "kind")],
    "spells": [("SpellName", "ID", "name"), ("Spell", "ID", "tooltip"), ("SpellEffect", "SpellID", "effects"),
               ("SpellPower", "SpellID", "cost"), ("SpellCooldowns", "SpellID", "cooldown"),
               ("SpellMisc", "SpellID", "details"), ("SpellLevels", "SpellID", "levels")],
    "quests": [("QuestV2", "ID", "flags")],
    "creatures": [("Creature", "ID", "details")],
    "areas": [("AreaTable", "ID", "details")],
    "rooms": [("WMOAreaTable", "ID", "details")],
    "minimaps": [("WMOMinimapTexture", "WMOID", "tiles")],
}
NAME_COLUMN = {"items": "Display_lang", "spells": "Name_lang", "creatures": "Name_lang", "areas": "AreaName_lang",
               "rooms": "AreaName_lang"}
AREA_COLUMN = {"areas": "ID", "rooms": "AreaTableID", "minimaps": "WMOID"}
STATES = ("new", "changed", "gone")
LIST_MOST = 10000
DIFF_LIMIT = 3600


def header(data):
    end = data.find(b"\n")
    return next(csv.reader([data[:end if end >= 0 else len(data)].decode("utf-8", "replace").rstrip("\r")]), [])


def table(name, build, owner):
    try:
        data = client.raw(name, build, check=lambda d: {"ID", owner} <= set(header(d)))
    except urllib.error.HTTPError as e:
        if not storedonly.not_there(e):
            raise
        return None
    except ValueError:
        return None
    cols = header(data)
    if not {"ID", owner} <= set(cols):
        return None
    return cols, data.decode("utf-8", "replace")


def lines(cols, text):
    rows = csv.reader(io.StringIO(text))
    next(rows, None)
    return (r for r in rows if len(r) >= len(cols))


def rows_of(cols, text, owner, shared):
    at_id, at_owner, at = cols.index("ID"), cols.index(owner), [cols.index(c) for c in shared]
    return {r[at_id]: (r[at_owner], hash(tuple(r[i] for i in at))) for r in lines(cols, text)}


def names_of(cols, text, column):
    if column not in cols:
        return {}
    at_id, at = cols.index("ID"), cols.index(column)
    return {r[at_id]: r[at] for r in lines(cols, text) if r[at]}


def our_names(kind):
    if kind == "quests":
        quests = datafiles.load(os.path.join(DATA, "quests.json"), {}).get("quests") or {}
        return {str(k): q["name"] for k, q in quests.items() if q.get("name")}
    if kind == "creatures":
        world = datafiles.load(os.path.join(DATA, "world.json"), {})
        fields = list(world.get("mobFields") or [])
        at = fields.index("name") if "name" in fields else None
        return {str(k): m[at] for k, m in (world.get("mobs") or {}).items() if at is not None and len(m) > at and m[at]}
    return {}


def roots(cols, rows):
    wmo, names, group, at = (cols.index(c) for c in ("WMOID", "NameSetID", "WMOGroupID", "AreaTableID"))
    return {(r[wmo], r[names]): int(r[at] or 0) for r in rows if r[group] == "-1"}


def areas_in(kind, cols, text, build):
    column = AREA_COLUMN[kind]
    rows = list(lines(cols, text))
    if column == "WMOID":
        got = table("WMOAreaTable", build, "ID")
        building = {}
        for (wmo, names), area in sorted((roots(got[0], lines(*got)) if got else {}).items(),
                                         key=lambda e: (e[0][0], int(e[0][1] or 0))):
            if area:
                building.setdefault(wmo, area)
        at = cols.index(column)
        return {r[at]: building.get(r[at], 0) for r in rows}
    at_id, at = cols.index("ID"), cols.index(column)
    out = {r[at_id]: int(r[at] or 0) for r in rows}
    if kind == "rooms":
        root = roots(cols, rows)
        wmo, names = cols.index("WMOID"), cols.index("NameSetID")
        for r in rows:
            if not out[r[at_id]]:
                out[r[at_id]] = root.get((r[wmo], r[names]), 0)
    return out


def map_areas():
    import mapzones
    maps = {}
    for mid, m in mapzones.MAPS.items():
        if m.get("area"):
            maps.setdefault(int(m["area"]), []).append([int(mid), m.get("name") or ""])
    return maps


def places(kind, build, first):
    import mapzones
    import opendungeons
    got = table("AreaTable", build, "ID")
    if got is None:
        return {}
    rows = list(csv.DictReader(io.StringIO(got[1])))
    parent = {int(r["ID"]): int(r["ParentAreaID"] or 0) for r in rows}
    name = {int(r["ID"]): r["AreaName_lang"] for r in rows}
    city = mapzones.capital_of(rows, opendungeons.barred())
    maps = map_areas()
    out = {}
    for row, area in areas_in(kind, *first, build).items():
        on = next((maps[a] for a in mapzones.area_chain(parent, area) if a in maps), []) if area else []
        out[row] = (name.get(area, ""), name.get(city[area], "") if area in city else "", sorted(on))
    return out


def ident(value):
    try:
        return int(value)
    except ValueError:
        return value


def kind_changes(kind, old, new):
    words, missing, first = {}, [], None
    for n, (name, owner, word) in enumerate(KINDS[kind]):
        a, b = table(name, old, owner), table(name, new, owner)
        if a is None or b is None:
            if n == 0:
                return {"missing": [name]}
            missing.append(name)
            continue
        shared = [c for c in b[0] if c in a[0]]
        before, after = rows_of(*a, owner, shared), rows_of(*b, owner, shared)
        if n == 0:
            first = (a, b, {o for o, _ in before.values()}, {o for o, _ in after.values()})
        for row in before.keys() | after.keys():
            if before.get(row) != after.get(row):
                for got in (before.get(row), after.get(row)):
                    if got:
                        words.setdefault(got[0], set()).add(word)
    a, b, had, has = first
    names = {"new": names_of(*b, NAME_COLUMN.get(kind)), "gone": names_of(*a, NAME_COLUMN.get(kind))}
    names["changed"] = names["new"]
    where = {}
    if kind in AREA_COLUMN:
        where = {"new": places(kind, new, b), "gone": places(kind, old, a)}
        where["changed"] = where["new"]
    ours = []

    def named(state, i):
        if names[state].get(i):
            return names[state][i]
        if where.get(state, {}).get(i, ("",))[0]:
            return where[state][i][0]
        if not ours:
            ours.append(our_names(kind))
        return ours[0].get(i, "")
    order = [w for _, _, w in KINDS[kind]]
    ids = {"new": has - had, "gone": had - has, "changed": {i for i in words if i in had and i in has}}
    out = {"counts": {s: len(ids[s]) for s in STATES}, "missing": missing}
    for state in STATES:
        found = [[ident(i), named(state, i)] + ([[w for w in order if w in words[i]]] if state == "changed" else [])
                 for i in ids[state]]
        found.sort(key=lambda e: (not e[1], e[1].lower(), str(e[0]).zfill(12)))
        out[state] = found[:LIST_MOST]
    if kind in AREA_COLUMN:
        out["cities"] = cities_of(where, ids, named)
    return out


def cities_of(where, ids, named):
    out = {}
    for state in STATES:
        for i in ids[state]:
            _, city, maps = where[state].get(i, ("", "", []))
            if city:
                got = out.setdefault(city, {"maps": []})
                got["maps"] += [m for m in maps if m not in got["maps"]]
                got.setdefault(state, set()).add(named(state, i))
    for got in out.values():
        got["maps"].sort()
        for state in STATES:
            if state in got:
                got[state] = sorted(got[state], key=str.lower)[:LIST_MOST]
    return out


def tables_print(old, new):
    try:
        installed = client.installed_version()
    except Exception:
        installed = None
    stamps = []
    for build in (old, new):
        for name, _, _ in (t for tables in KINDS.values() for t in tables):
            if build == installed:
                try:
                    client.local(name, build)
                except Exception:
                    pass
            stamp = store.stamp(client.stood(name, build)[0])
            if stamp is None:
                return None
            stamps.append(f"{build} {name} {stamp[0]} {stamp[1]}")
    import opendungeons
    stamps.append(json.dumps([sorted(map_areas().items()), opendungeons.barred()]))
    return hashlib.sha1("\n".join(stamps).encode()).hexdigest()[:12]


def changes(old, new):
    return {kind: kind_changes(kind, old, new) for kind in KINDS}


def run(old, new):
    import game
    import rebuild
    try:
        done = subprocess.run([game.console_python(), *rebuild.LAUNCH, os.path.abspath(__file__), old, new], cwd=ROOT,
                              capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=DIFF_LIMIT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              env={**os.environ, "WCC_TRAFFIC_LOG": rebuild.TRAFFIC_LOG})
    except subprocess.TimeoutExpired as e:
        raise OSError(f"the build's changes took more than {DIFF_LIMIT} s") from e
    if done.returncode:
        said = (done.stderr or "").strip().splitlines()
        raise OSError(said[-1] if said else f"the build's changes failed (exit {done.returncode})")
    return json.loads(done.stdout)


def main(argv):
    print(jsontext.dumps(changes(argv[1], argv[2])))


if __name__ == "__main__":
    main(sys.argv)
