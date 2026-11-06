# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading
import time

import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "offers.json")
OFFERED = "offered"


def standing(who, done):
    who = who or {}
    if who.get("level") is None or who.get("classId") is None:
        return None
    me = {"level": int(who["level"]), "classId": int(who["classId"]), "race": who.get("race"), "side": who.get("side"),
          "done": sorted({int(i) for i in done or ()})}
    if who.get("skills") is not None:
        me["skills"] = {str(int(line)): int(rank or 0) for line, rank in who["skills"].items()}
    return me


def holds(answer, me):
    if answer.get("answer") != OFFERED or any(answer.get(k) != me[k] for k in ("classId", "race", "side")):
        return False
    return me["level"] >= answer["level"] and set(me["done"]) >= set(answer["done"])


class GiverAnswers:
    def __init__(self, path=PATH):
        self.path, self.lock = path, threading.Lock()
        self.data = store.load_json(path, {})
        self.data.setdefault("quests", {})
        self.version = 0

    def note(self, qid, npc, who, done, name=None, now=None):
        me = standing(who, done)
        if me is None or qid is None:
            return False
        with self.lock:
            q = self.data["quests"].setdefault(str(int(qid)), {"name": name, "answers": []})
            if name and not q.get("name"):
                q["name"] = name
            if any(holds(a, me) and set(a) >= set(me) for a in q["answers"]):
                return False
            q["answers"].append({"answer": OFFERED, "npc": npc, **me, "at": round(time.time() if now is None else now)})
            self.version += 1
            storewriter.save_json_later(self.path, self.data)
            return True

    def known(self, who, done):
        me = standing(who, done)
        if me is None:
            return set()
        with self.lock:
            return {int(qid) for qid, q in self.data["quests"].items() if any(holds(a, me) for a in q.get("answers") or ())}

    def offered_ever(self):
        with self.lock:
            return {int(qid) for qid, q in self.data["quests"].items()
                    if any(a.get("answer") == OFFERED for a in q.get("answers") or ())}
