# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os
import re
import threading

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "settings.json")
KEY = re.compile(r"cc\.[A-Za-z][A-Za-z0-9_.]{0,60}")
VALUE_MOST = 4000
MOST = 200

lock = threading.Lock()


def fits(key, value):
    if not isinstance(key, str) or not KEY.fullmatch(key):
        return False
    try:
        return len(json.dumps(value)) <= VALUE_MOST
    except (TypeError, ValueError):
        return False


def load(path=None):
    kept = store.load_json(path or PATH, {})
    return {k: v for k, v in kept.items() if fits(k, v)} if isinstance(kept, dict) else {}


def change(changes, path=None):
    if not isinstance(changes, dict) or not all(fits(k, v) for k, v in changes.items()):
        return None
    with lock:
        kept = load(path)
        for k, v in changes.items():
            if v is None:
                kept.pop(k, None)
            else:
                kept[k] = v
        if len(kept) > MOST:
            return None
        storewriter.save_json_later(path or PATH, kept)
        return kept
