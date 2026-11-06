# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import hashlib
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import client
import clienttips
import dropguard
import mainstores
import store
from game import installed_version

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "tooltips")
INDEX = os.path.join(DATA, "tooltips.json")
FALLBACK = os.path.join(DATA, "tooltips_fallback.json")
KEPT = os.path.join(OUT, "kept")
SHARD = 1000


def shard_path(kind, oid, folder=None):
    folder = folder or OUT
    return os.path.join(folder, f"{kind}-{oid // SHARD}.json")


def class_spells(path=None):
    classes = dropguard.made(path or os.path.join(DATA, "classspells.json")).get("classes") or {}
    taught = {s["id"]: int(c) for c, v in classes.items() for lv in (v.get("levels") or {}).values()
              for s in lv.get("spells") or ()}
    talents = {t["id"]: int(c) for c, v in classes.items() for tree in v.get("trees") or () for t in tree.get("talents") or ()}
    return {**talents, **taught}


def fingerprints(tables, raw=client.raw):
    return {t: hashlib.sha1(raw(t)).hexdigest()[:12] for t in tables}


def build(tables, spells_of):
    b = clienttips.Builder(tables)
    items = {iid: tip for iid in tables.sparse for tip in [b.item(iid)] if tip}
    spells = {sid: tip for sid, cid in spells_of.items() for tip in [b.spell(sid, cid)] if tip}
    return items, spells, set(tables.item) | set(tables.sparse)


def wanted(items, spells, every_item):
    out = [("item", iid, "no ItemSparse row") for iid in sorted(every_item - set(items))]
    out += [("item", iid, "; ".join(tip["gaps"])) for iid, tip in sorted(items.items()) if tip.get("gaps")]
    out += [("spell", sid, "; ".join(tip["gaps"])) for sid, tip in sorted(spells.items()) if tip.get("gaps")]
    return out


def stood_in(kind, oid, kept=None):
    path = mainstores.standing(os.path.join(kept or KEPT, kept_name(kind, oid)))
    if os.path.isfile(path):
        return path, (store.load_json(path, {}) or {}).get("domain", "forever")
    return None


def kept_name(kind, oid):
    return f"{kind}-{oid}.json"


def choose_fallbacks(items, spells, every_item, kept=None):
    out, none = {"item": {}, "spell": {}}, {"item": [], "spell": []}
    for kind, oid, reason in wanted(items, spells, every_item):
        found = stood_in(kind, oid, kept)
        if found:
            out[kind][oid] = {"reason": reason, "domain": found[1], "file": kept_name(kind, oid)}
        elif kind == "item" and oid not in items:
            none["item"].append(oid)
    return out, none


def shard_writes(kind, tips, folder=None):
    folder = folder or OUT
    os.makedirs(folder, exist_ok=True)
    shards = collections.defaultdict(dict)
    for oid, tip in tips.items():
        shards[oid // SHARD][str(oid)] = {k: v for k, v in tip.items() if k != "gaps"}
    writes = []
    old = {n for n in os.listdir(folder) if n.startswith(f"{kind}-") and n.endswith(".json")}
    for k, held in shards.items():
        path = os.path.join(folder, f"{kind}-{k}.json")
        old.discard(os.path.basename(path))
        if store.load_json(path, None) != held:
            writes.append((path, held, (None,)))
    return writes + [(path, {}, (None,)) for path in (os.path.join(folder, name) for name in sorted(old))
                     if store.load_json(path, None) != {}]


def main(rows=client.rows, raw=client.raw):
    began = time.time()
    build = installed_version()
    tables = clienttips.Tables(rows)
    items, spells, every_item = build_all(tables)
    chosen, none = choose_fallbacks(items, spells, every_item)
    shards = shard_writes("item", items) + shard_writes("spell", spells)
    gaps = collections.Counter(g for tips in (items, spells) for tip in tips.values() for g in tip.get("gaps") or ())
    fallback = {kind: {str(k): v for k, v in sorted(e.items())} for kind, e in chosen.items()}
    index = {"build": build, "tables": fingerprints(clienttips.TABLES, raw),
             "item": {"of": len(every_item), "built": len(items), "fallback": len(chosen["item"]), "none": none["item"]},
             "spell": {"of": len(class_spells()), "built": len(spells), "fallback": len(chosen["spell"]), "none": []},
             "gaps": dict(gaps.most_common())}
    dropguard.save_all(shards + [(FALLBACK, fallback, (), {"indent": 1}), (INDEX, index, ())], indent=None)
    print(f"{len(items)} item tooltips built of {len(every_item)} items, {len(chosen['item'])} stand in from kept copies, "
          f"{len(none['item'])} with none; {len(spells)} class spell tooltips, {len(chosen['spell'])} from kept copies; "
          f"{len(shards)} files written, in {time.time() - began:.0f} s")


def build_all(tables):
    return build(tables, class_spells())


if __name__ == "__main__":
    import builder
    builder.run(main)
