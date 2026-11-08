# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
from epic import unavailable
import questplan

KINDS = ("ready", "take", "open", "done")
SHAPE = {"ready": "?", "take": "!", "open": "?"}
QUESTS_NAMED = 8


def quest_kinds(book, me, done, log, level, cap, spells=None):
    out = {}
    for qid, q in book.quests.items():
        starts, ends = [("!", g) for g in q.get("start") or ()], [("?", g) for g in q.get("end") or ()]
        if qid in log:
            out[qid] = ("ready" if log[qid] else "open", ends)
        elif qid in done:
            out[qid] = ("done", starts + ends)
        elif (q.get("req") or 1) <= level and questplan.open_now(q, me["side"], me["race"], me["classId"], done, log, cap, spells) \
                and unavailable(q, done, log, level, book.quests) is None:
            out[qid] = ("take", starts)
    return out


def marks(book, kinds, project):
    by_spot = {}
    for qid, (kind, spots) in kinds.items():
        for role, g in spots:
            if g.get("map") is None or g.get("inside"):
                continue
            at = project(g["map"], g["x"], g["y"])
            if at is None:
                continue
            key = (g.get("npc") or g.get("object") or g.get("name"), g["map"], round(g["x"], 1), round(g["y"], 1))
            mark = by_spot.setdefault(key, {"n": g.get("name") or "", "x": at[0], "y": at[1], "z": g.get("z"),
                                            "o": 1 if g.get("object") else 0, "roles": set(), "q": []})
            mark["roles"].add(role)
            mark["q"].append({"n": book.quests[qid]["name"], "k": kind})
    out = []
    for mark in by_spot.values():
        mark["q"].sort(key=lambda x: (KINDS.index(x["k"]), x["n"]))
        kind = mark["q"][0]["k"]
        roles = mark.pop("roles")
        shape = SHAPE.get(kind) or ("!" if "!" in roles else "?")
        out.append({**mark, "k": kind, "m": shape, "q": mark["q"][:QUESTS_NAMED], "more": max(0, len(mark["q"]) - QUESTS_NAMED)})
    return out

