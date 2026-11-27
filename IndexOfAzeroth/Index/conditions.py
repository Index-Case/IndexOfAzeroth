# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "conditions.json")
AURA_KINDS = ("form", "pick", "self")
READ_KINDS = ("enchant", "pet")
_kept = {}


def index(table):
    out = {}
    for c in (table or {}).get("classes", {}).values():
        for g in c.get("groups") or ():
            if g.get("kind") not in AURA_KINDS:
                continue
            for m in g["members"]:
                for sid in m["ranks"]:
                    out.setdefault(sid, (g["key"], m["spell"], m["name"], g.get("name")))
    return out


def _table(path=PATH):
    st = store.stamp(path)
    kept = _kept.get(path)
    if kept and kept[0] == st:
        return kept[1:]
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        raw = None
    table = store.load_json(path, None) if raw else None
    got = (index(table), hashlib.sha1(raw).hexdigest()[:12] if raw else None, table or {})
    _kept[path] = (st, *got)
    return got


def made(path=PATH):
    return _table(path)[1]


def held(up, span, path=PATH, table=None):
    by = table if table is not None else _table(path)[0]
    groups = {}
    for a in up:
        aura, secs = a["id"], a["y"]
        hit = by.get(aura)
        if not hit or not secs or secs <= 0:
            continue
        key, spell, name = hit[:3]
        conds = groups.setdefault(key, {})
        conds[(spell, name)] = max(conds.get((spell, name), 0.0), secs)
    out, span = [], max(span or 0.0, 0.0)
    for key in sorted(groups):
        (spell, name), secs = max(groups[key].items(), key=lambda kv: (kv[1], -kv[0][0]))
        share = min(100, round(100 * secs / span)) if span > 0 else 100
        out.append([key, spell, name, round(secs, 1), share, 1 if len(groups[key]) > 1 else 0])
    return out


def words(rows, path=PATH, table=None):
    by = table if table is not None else _table(path)[0]
    said = {(hit[0], hit[1]): hit[3] for hit in by.values() if hit[3]}
    out = {}
    for r in rows:
        word = said.get((r[0], r[1]))
        if word:
            out[r[0]] = word
    return out


def reads(class_id, path=PATH, table=None):
    table = table if table is not None else _table(path)[2]
    out = {"ench": {}, "words": {}}
    c = (table.get("classes") or {}).get(str(class_id)) if class_id is not None else None
    if not c:
        return out
    for g in list(c.get("groups") or ()) + list(table.get("every") or ()):
        if g.get("kind") not in READ_KINDS:
            continue
        if g.get("name"):
            out["words"].setdefault(g["key"], g["name"])
        for m in g["members"]:
            for i in m.get("enchants") or ():
                out["ench"].setdefault(i, [m["spell"], m["name"]])
    return out
