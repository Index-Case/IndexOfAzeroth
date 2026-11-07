# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import re

import director_rules
from geo import line_reach

FAR = 1e6
EPIC_CODE = {"pickup": "P", "objective": "O", "turnin": "T", "dungeon": "D", "errand": "S"}
OBJECTIVE_ICONS = ("kill", "loot", "grab", "use", "talk", "heal", "event", "explore", "escort", "buy", "pickpocket")
OBJECTIVE_KINDS = {"kill": "kill", "loot": "loot", "use": "use", "interact": "use", "talk": "talk", "event": "event",
                   "pickpocket": "pickpocket",
                   "explore": "explore"}
HEAL_WORDS = re.compile(r"\b(heal(ed|s)?|cured?|bandaged|revived?|mended)\b", re.I)
BUY_WORD = "Buy"


def objective_icon(step):
    kind = step.get("objective")
    if step.get("escort"):
        return "escort"
    if kind == "loot" and step.get("objects") and not step.get("mobs"):
        return "grab"
    if kind == "talk" and step.get("get") and (step.get("text") or "").startswith(f"{BUY_WORD} "):
        return "buy"
    if kind == "event" and HEAL_WORDS.search(step.get("text") or ""):
        return "heal"
    return OBJECTIVE_KINDS.get(kind)
TIE = 1e-6


def spot(step):
    if not step or not step.get("at") or step.get("inst") is None:
        return None
    at = step["at"]
    return (step["inst"], at[0], at[1]) + ((at[2],) if len(at) > 2 and at[2] is not None else ())


def reach_of(step, p):
    at = spot(step)
    if not at or not p or at[0] != p[0]:
        return math.inf
    pts = [at[1:]] + [q[:2] for q in (step.get("spawns") or ())] + [q[:2] for q in (step.get("loop") or ())]
    return min(math.hypot(q[0] - p[1], q[1] - p[2]) for q in pts)


def here(step, p, run=None):
    at = spot(step)
    if not at or not p or at[0] != p[0]:
        return False
    t = {"ar": step.get("places") or [], "loop": step.get("loop"), "x": at[1], "y": at[2]}
    return director_rules.here(t, p[1], p[2], run) is not None


def gap(a, b):
    if not a or not b:
        return FAR / 2
    return math.hypot(a[1] - b[1], a[2] - b[2]) if a[0] == b[0] else FAR


def norm_words(words):
    w = re.sub(r"^\s*\d+\s*/\s*\d+\s*|:\s*\d+\s*/\s*\d+\s*$|\(optional\)", "", (words or "").casefold())
    return re.sub(r"\s+", " ", w).strip()


SAID_KILL = re.compile(r"\b(slain|killed|destroyed|defeated)\b")
SAID_HELP = re.compile(r"\b(heal(ed)?|freed|rescued|helped|saved|cured|revived|bandaged|comforted|calmed|released|aided|"
                       r"tended|blessed|inspired|fed)\b")
SAID_TALK = re.compile(r"^(speak|talk|listen) (with|to)\b|\b(spoken|talked|listened) (with|to)\b")
SAID_USE = re.compile(r"\b(used|placed|planted|activated|lit|burned|searched|examined|investigated)\b")
SAID_FITS = {"kill": ("mobs",), "event": ("mobs",), "talk": ("mobs",), "use": ("objects",), "loot": ("mobs", "objects")}
SAID_TYPES = {"item": "loot", "object": "use"}
SAID_BY_WORDS = (None, "monster", "event")


def said_kind(words, name=None, kind=None):
    if kind in SAID_TYPES:
        return SAID_TYPES[kind]
    if kind not in SAID_BY_WORDS:
        return None
    w = norm_words(words)
    if name:
        w = w.replace(norm_words(name), " ")
    if SAID_KILL.search(w):
        return "kill"
    if SAID_HELP.search(w):
        return "event"
    if SAID_TALK.search(w):
        return "talk"
    if SAID_USE.search(w):
        return "use"
    return None


def said_for(t, said):
    want = [norm_words(w) for w in (t.get("text"), t.get("name")) if w]
    for line in said or ():
        got = norm_words(line[0])
        if got and any(w and (w in got or got in w) for w in want):
            return line
    return None


def step_ids(step):
    ids = step.get("quests") if step.get("kind") == "dungeon" else [step["quest"]] if step.get("quest") else []
    return list(ids or [])


def around(steps, i, start, spot_of=spot):
    prev = next((p for p in map(spot_of, reversed(steps[:i])) if p), start)
    return prev, next((p for p in map(spot_of, steps[i:]) if p), None)


def detour(prev, at, nxt, gap=gap):
    return gap(prev, at) + (gap(at, nxt) - gap(prev, nxt) if nxt else 0.0)


def added(steps, i, at, start, spot_of=spot, gap=gap):
    prev, nxt = around(steps, i, start, spot_of)
    return detour(prev, at, nxt, gap)


def cheapest(steps, spots, lo, hi, start, spot_of=spot, gap=gap, ok=None):
    best = None
    for i in range(lo, hi + 1):
        prev, nxt = around(steps, i, start, spot_of)
        for k, at in enumerate(spots):
            if ok and not ok(i, k):
                continue
            c = detour(prev, at, nxt, gap)
            if best is None or c < best[0] - TIE:
                best = (c, i, k)
    return best


def near_way(points, ways, reach):
    pts = [tuple(float(v) for v in p[:3] if v is not None) for p in points]
    if not pts:
        return set()
    lo_n, hi_n = min(p[0] for p in pts) - reach, max(p[0] for p in pts) + reach
    lo_w, hi_w = min(p[1] for p in pts) - reach, max(p[1] for p in pts) + reach
    hit = set()
    for way in ways:
        bends = [tuple(float(v) for v in b[:3] if v is not None) for b in way]
        for a, b in zip(bends, bends[1:] or bends):
            if max(a[0], b[0]) < lo_n or min(a[0], b[0]) > hi_n or max(a[1], b[1]) < lo_w or min(a[1], b[1]) > hi_w:
                continue
            n0, n1, w0, w1 = min(a[0], b[0]) - reach, max(a[0], b[0]) + reach, min(a[1], b[1]) - reach, max(a[1], b[1]) + reach
            hit.update(k for k, p in enumerate(pts) if k not in hit and n0 <= p[0] <= n1 and w0 <= p[1] <= w1
                       and line_reach(p, a, b) <= reach)
    return hit


def giver_spots(step):
    return [p for p in (spot(step), tuple(step["giverAt"]) if step.get("giverAt") else None) if p]


def giver_of(step):
    return ("npc", step["npcId"]) if step.get("npcId") else ("object", step["objectId"]) if step.get("objectId") else None


def same_giver(a, b):
    if giver_of(a) is None or giver_of(a) != giver_of(b):
        return False
    near = director_rules.GUIDE["with_giver"].value
    return any(pa[0] == pb[0] and math.hypot(pa[1] - pb[1], pa[2] - pb[2]) <= near for pa in giver_spots(a) for pb in giver_spots(b))


def own_with(step, giver):
    return step.get("kind") in ("pickup", "turnin") and not step.get("maybe") and same_giver(step, giver)


def offered_last(steps):
    out = list(steps)
    for m in reversed([s for s in steps if s.get("kind") == "pickup" and s.get("maybe")]):
        at = next(k for k, s in enumerate(out) if s is m)
        last = max((k for k, s in enumerate(out) if own_with(s, m)), default=-1)
        if last > at:
            out.insert(last, out.pop(at))
    return out
