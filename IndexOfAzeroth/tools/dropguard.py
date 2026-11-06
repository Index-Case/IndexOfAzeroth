# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import store

HELD = 4
DROP_SHARE = 0.05
DROP_LEAST = 50
LOSS_SHARE = 0.25
LOSS_FLOOR = 20
ACCEPT = "WCC_ACCEPT_DROP"
HELD_NOTES = os.path.join(ROOT, "data", "buildcache", "held.json")
SOME = 10


def made(path):
    got = store.load_json(path, None)
    if got is None:
        raise SystemExit(f"{os.path.basename(sys.argv[0] or 'builder')}: {os.path.basename(path)} isn't there or "
                         f"can't be read. Another step makes it: nothing written, the step runs again once that one has")
    return got


def keys_of(records):
    if isinstance(records, dict):
        return {str(k) for k in records}
    if isinstance(records, list):
        return {str(r["id"]) if isinstance(r, dict) and "id" in r else json.dumps(r, sort_keys=True) for r in records}
    return set()


def drops(old, new, collections, least=DROP_LEAST, share=DROP_SHARE):
    out = {}
    for name in collections:
        was, now = (keys_of(old or {}), keys_of(new or {})) if name is None else \
            (keys_of((old or {}).get(name)), keys_of((new or {}).get(name)))
        gone = was - now
        if was and gone and len(gone) >= least and len(gone) > share * len(was):
            out[name or "records"] = {"was": len(was), "now": len(now), "dropped": len(gone),
                                      "some": sorted(gone, key=lambda k: (len(k), k))[:SOME]}
    return out


def fallen(old, new, counts):
    after = counts(new)
    try:
        before = counts(old) if old is not None else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        before = {}
    out = {}
    for key, (what, was) in before.items():
        now = after.get(key, (what, 0))[1]
        if was >= LOSS_FLOOR and now < was * (1 - LOSS_SHARE):
            out[what] = {"was": was, "now": now, "dropped": was - now, "some": []}
    return out


def accepted(name):
    said = {w.strip().lower() for w in os.environ.get(ACCEPT, "").split(",") if w.strip()}
    return "all" in said or name.lower() in said


def held(writes):
    out = {}
    for path, obj, collections, *guard in writes:
        guard = guard[0] if guard else {}
        if not (collections or guard.get("counts")):
            continue
        name, old = os.path.basename(path), store.load_json(path, None)
        found = drops(old, obj, collections, **{k: guard[k] for k in ("least", "share") if k in guard}) \
            if collections and isinstance(old, dict) else {}
        if guard.get("counts"):
            found.update(fallen(old, obj, guard["counts"]))
        if found and accepted(name):
            print(f"{name} written with what it drops, {ACCEPT} naming it: {words({name: {'collections': found}})}")
        elif found:
            out[name] = {"build": (old.get("build") or old.get("version")) if isinstance(old, dict) else None,
                         "collections": found}
    return out


def words(files):
    return ", ".join(f"{name} {coll} {c['dropped']:,} of {c['was']:,}" for name, f in files.items()
                     for coll, c in f["collections"].items())


def note(step, files, notes=None):
    notes = notes or HELD_NOTES
    with store.locked(notes):
        kept = store.load_json(notes, {}) or {}
        kept[step] = {"at": round(time.time()), "files": files}
        store.save_json(notes, kept)


def step_name():
    return store.running_builder() or os.path.splitext(os.path.basename(sys.argv[0] or "builder"))[0]


def save_all(writes, indent=1):
    found = held(writes)
    if found:
        note(step_name(), found)
        print(f"{os.path.basename(sys.argv[0] or 'builder')}: held, nothing written. It would drop {words(found)} "
              f"against the last good build. To write it anyway: {ACCEPT}={','.join(found)}")
        sys.exit(HELD)
    for path, obj, _, *guard in writes:
        store.save_json(path, obj, indent=(guard[0] if guard else {}).get("indent", indent))
