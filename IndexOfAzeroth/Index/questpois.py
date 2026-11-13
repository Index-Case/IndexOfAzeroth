# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import threading
import time

from epic import counted
from plansteps import norm_words
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "data", "quest_pois.json")
CHECKS = os.path.join(ROOT, "data", "quest_checks.json")
OBJECTIVE_FAR = 300.0
TURNIN_FAR = 100.0
MARKS_KEPT = 12


def nearest(spot, points):
    return min((math.hypot(p[1] - spot[1], p[2] - spot[2]) for p in points if p and p[0] == spot[0]), default=math.inf)


class QuestPois:
    def __init__(self, path=PATH, checks=CHECKS):
        self.path, self.checks_path = path, checks
        self.lock = threading.Lock()
        kept = store.load_json(path, {})
        self.pois = {int(k): v for k, v in (kept.get("quests") or {}).items()}
        self.said = {int(k): v for k, v in (kept.get("counts") or {}).items()}
        self.checks = {int(k): v for k, v in (store.load_json(checks, {}).get("quests") or {}).items()}

    def note(self, entries, book, to_world, now=None):
        now = round(now or time.time())
        changed = False
        with self.lock:
            for e in entries:
                if "id" in e:
                    changed |= self.note_counts(e, book, now)
                p = e.get("poi")
                if not p or "id" not in e:
                    continue
                kind = "end" if e.get("complete") else "obj"
                spot = [int(p["map"]), round(p["x"] * 100, 2), round(p["y"] * 100, 2)]
                have = self.pois.setdefault(e["id"], {})
                areas = [[int(a["obj"]), spot[0], round(a["x"] * 100, 2), round(a["y"] * 100, 2), int(a["r"])]
                         for a in e.get("areas") or ()] if kind == "obj" else []
                if areas and have.get("areas") != areas:
                    have["areas"], have["areasAt"] = areas, now
                    changed = True
                if (have.get(kind) or [None])[:3] == spot:
                    continue
                if kind == "obj":
                    before = have.get("marks") or ([have["obj"][:3]] if have.get("obj") else [])
                    have["marks"] = ([m for m in before if m != spot] + [spot])[-MARKS_KEPT:]
                have[kind] = spot + [now]
                changed = True
                found = self.check(e["id"], kind, spot, book, to_world, now)
                was = self.checks.get(e["id"], {})
                if found:
                    self.checks[e["id"]] = {**was, kind: found}
                elif kind in was:
                    was.pop(kind)
                    if not was:
                        self.checks.pop(e["id"], None)
            if changed:
                storewriter.save_json_later(self.path, {"quests": {str(k): v for k, v in sorted(self.pois.items())},
                                                  "counts": {str(k): v for k, v in sorted(self.said.items())}}, indent=None)
                storewriter.save_json_later(self.checks_path, {"quests": {str(k): v for k, v in sorted(self.checks.items())}})
        return changed

    def note_counts(self, e, book, now):
        said = [[words, o["need"]] for o in e.get("objectives") or () for words in [norm_words(o.get("text"))] if words and o.get("need")]
        if not said or self.said.get(e["id"]) == said:
            return False
        self.said[e["id"]] = said
        q = book.quests.get(e["id"])
        was = self.checks.get(e["id"], {})
        if q and counted(q, said) is not q:
            self.checks[e["id"]] = {**was, "count": {"name": q.get("name"), "game": said, "at": now,
                                                     "data": [[t.get("name"), t.get("count", 1)] for t in q.get("targets") or []]}}
        elif "count" in was:
            was.pop("count")
            if not was:
                self.checks.pop(e["id"], None)
        return True

    def counts(self):
        with self.lock:
            return {k: [tuple(s) for s in v] for k, v in self.said.items()}

    def kept(self, qid, complete):
        with self.lock:
            spot = self.pois.get(qid, {}).get("end" if complete else "obj")
        return {"map": spot[0], "x": round(spot[1] / 100, 4), "y": round(spot[2] / 100, 4)} if spot else None

    @staticmethod
    def check(qid, kind, spot, book, to_world, now):
        q = book.quests.get(qid)
        at = to_world(*spot)
        if not q or not at:
            return None
        if kind == "obj":
            points = [to_world(*s) for t in q.get("targets", []) for s in t.get("spots", [])]
            if not points:
                return None
            yards = nearest(at, points)
            far = OBJECTIVE_FAR
        else:
            yards = nearest(at, [to_world(g["map"], g["x"], g["y"]) for g in q.get("end", []) if g.get("map") is not None])
            far = TURNIN_FAR
        if yards <= far:
            return None
        return {"name": q.get("name"), "game": spot, "yards": None if math.isinf(yards) else round(yards), "at": now}

    def world(self, to_world):
        with self.lock:
            out = {}
            for qid, have in self.pois.items():
                spots = {k: to_world(*have[k][:3]) for k in ("obj", "end") if have.get(k)}
                spots = {k: v for k, v in spots.items() if v}
                areas = [{"obj": a[0], "at": to_world(*a[1:4]), "r": a[4]} for a in have.get("areas") or ()]
                areas = [a for a in areas if a["at"]]
                if areas and spots.get("obj"):
                    mark = spots["obj"]
                    yards = lambda a: math.hypot(a["at"][1] - mark[1], a["at"][2] - mark[2]) - a["r"] \
                        if a["at"][0] == mark[0] else math.inf
                    nearest = min(yards(a) for a in areas)
                    for a in areas:
                        a["main"] = yards(a) <= max(0.0, nearest)
                marks = [w for w in (to_world(*m[:3]) for m in have.get("marks") or ([have["obj"]] if have.get("obj") else ())) if w]
                if spots:
                    out[qid] = {**spots, "maps": {k: have[k][0] for k in spots}, **({"areas": areas} if areas else {}),
                                **({"marks": marks} if marks else {})}
            return out
