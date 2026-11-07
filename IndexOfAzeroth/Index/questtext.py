# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import glob
import os
import re
import threading

import blurbs
from characters import realm_key
import datafiles
import prompts
import savedvars
import store

DATA = datafiles.data_path("questtext.json")
SAVED_NAME = "IndexOfAzeroth.lua"
ASKED_MOST = 50
SUMMARY_MOST = 120
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

_lock = threading.Lock()
_saved = {}


def char_folder(c):
    c = c or {}
    return "-".join(p for p in (c.get("name"), c.get("surname")) if p)


def saved_file(wtf, char):
    if not wtf or not char:
        return None
    folder, realm = char_folder(char), char.get("realm") or ""
    if not folder:
        return None
    found = glob.glob(os.path.join(glob.escape(wtf), "Account", "*", "*", glob.escape(folder), "SavedVariables", SAVED_NAME))
    mine = [p for p in found if realm_key(os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p)))))
            == realm_key(realm)]
    if len(mine) == 1:
        return mine[0]
    return found[0] if len(found) == 1 and not mine else None


def game_texts(path, look=prompts.look_texts):
    now = store.stamp(path) if path else None
    if now is None:
        return {}
    with _lock:
        hit = _saved.get(path)
        if hit and hit[0] == now:
            return hit[1]
    try:
        db = savedvars.read(path).get("IndexOfAzerothCharDB")
    except (OSError, savedvars.SavedVariablesError):
        db = None
    kept = db.get("questText") if isinstance(db, dict) else None
    if isinstance(kept, list):
        kept = dict(enumerate(kept, 1))
    out = {}
    for qid, rec in (kept.items() if isinstance(kept, dict) else ()):
        if not isinstance(rec, dict) or not isinstance(qid, (int, float)) or isinstance(qid, bool):
            continue
        got = {k: rec[s].strip() for k, s in (("text", "d"), ("todo", "o")) if isinstance(rec.get(s), str) and rec[s].strip()}
        if got:
            out[int(qid)] = got
    look(path, [(f"quest {qid}'s {field}", words) for qid, rec in sorted(out.items()) for field, words in rec.items()])
    with _lock:
        _saved[path] = (now, out)
    return out


def summary(todo, most=SUMMARY_MOST):
    out = ""
    for part in SENTENCE_END.split(" ".join((todo or "").split())):
        if out and len(out) + 1 + len(part) > most:
            break
        out = f"{out} {part}" if out else part
    return out


def texts(ids, char=None, wtf=None, look=prompts.look_texts):
    data = datafiles.load(DATA).get("quests") or {}
    game = game_texts(saved_file(wtf, char), look) if char else {}
    out = {}
    for qid in list(dict.fromkeys(ids))[:ASKED_MOST]:
        mine, ours = game.get(qid) or {}, data.get(str(qid)) or {}
        rec = {k: mine.get(k) or ours.get(k) for k in ("text", "todo") if mine.get(k) or ours.get(k)}
        line = blurbs.line(qid)
        if rec or line:
            short = summary(rec.get("todo"))
            out[qid] = {**rec, **({"summary": short} if short else {}), "game": bool(mine),
                        **({"blurb": line} if line else {})}
    return out
