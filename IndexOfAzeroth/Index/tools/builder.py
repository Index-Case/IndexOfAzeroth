# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import game
import store

NO_GAME = 2
MORE = 3
WAITING = 5


REDO = "WCC_REDO"
RESUME = "WCC_RESUME"
RUN_ENV = "WCC_REBUILD_RUN"
FILL_NOTES = os.path.join(ROOT, "data", "buildcache", "fills.json")

waits = []


def redo():
    return os.environ.get(REDO) == "1"


def resuming():
    return os.environ.get(RESUME) == "1"


def rebuild_run():
    return os.environ.get(RUN_ENV) or None


def wait_until(when):
    waits.append(when)


class MoreToFetch(Exception):
    pass


class NothingFetched(Exception):
    pass


def note_fill(script, notes=None):
    notes = notes or FILL_NOTES
    os.makedirs(os.path.dirname(notes), exist_ok=True)
    with store.locked(notes):
        kept = store.load_json(notes, {}) or {}
        kept[script] = {"at": round(time.time(), 3), "after": max(waits) if waits else None}
        store.save_json(notes, kept)


def run(main, *args):
    script = os.path.basename(sys.argv[0] or "builder")
    store.start_builder_run()
    try:
        return main(*args)
    except game.GameNotFound as e:
        print(f"{script}: {e}", file=sys.stderr)
        sys.exit(NO_GAME)
    except NothingFetched as e:
        print(f"{script}: {e}")
        if rebuild_run():
            note_fill(script)
        sys.exit(WAITING)
    except MoreToFetch as e:
        print(f"{script}: {e}")
        if rebuild_run():
            note_fill(script)
        sys.exit(MORE)
