# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import contextvars
import re

import carried
import plurals
import quip_lines

_REPORT = contextvars.ContextVar("plan_report", default=None)
_CARRIED_BY = carried


def report(stage=None, finds=(), picked=None, placed=(), ordered=None, crumbs=None, at=None, rounds=None, tried=None,
           walked=None, won=None):
    to = _REPORT.get()
    if to is None:
        return
    try:
        to(stage, list(finds), picked, placed, ordered, crumbs, at, rounds, tried, walked, won)
    except Exception:
        pass


def weighing(steps, k):
    if _REPORT.get() is not None and 0 <= k < len(steps):
        report(at=(steps[k], k + 1, len(steps)))


def reporting_now():
    return _REPORT.get() is not None


@contextlib.contextmanager
def reporting(to):
    token = _REPORT.set(to)
    try:
        yield
    finally:
        _REPORT.reset(token)


@contextlib.contextmanager
def quiet():
    token = _REPORT.set(None)
    try:
        yield
    finally:
        _REPORT.reset(token)


def first(finds, each=quip_lines.EACH):
    out, seen, count = [], set(), {}
    for f in finds:
        key = tuple(sorted((k, str(v)) for k, v in f.items()))
        if key in seen or count.get(f["k"], 0) >= each:
            continue
        seen.add(key)
        count[f["k"]] = count.get(f["k"], 0) + 1
        out.append(f)
    return out


def part(o):
    done, need, text = o.get("done"), o.get("need"), o.get("text") or ""
    if o.get("finished") or not isinstance(done, int) or not isinstance(need, int) or done >= need:
        return None
    m = re.match(r"^\d+/\d+ (.+)$", text) or re.match(r"^(.+?): \d+/\d+$", text)
    return {"done": done, "need": need, "thing": m.group(1)} if m else None


def log_finds(entries):
    quests = [e for e in entries if e.get("id") is not None and e.get("title")]
    out = []
    for e in quests:
        out.append({"k": "done" if e.get("complete") else "quest", "quest": e["title"]})
        if not e.get("complete"):
            out += [{"k": "part", **p} for p in map(part, e.get("objectives") or ()) if p]
    if len(quests) >= 2:
        out.append({"k": "count", "count": len(quests)})
    return first(out)


def mobs(step):
    if step.get("objective") != "kill":
        return None
    return step.get("things") or (plurals.plural(step["target"]) if step.get("target") else None)


def way_now(step, n):
    if step.get("npc"):
        return {"k": "npc", "npc": step["npc"], "n": n}
    if mobs(step) and step.get("questName"):
        return {"k": "camp", "who": mobs(step), "quest": step["questName"], "n": n}
    if step.get("questName"):
        return {"k": "quest", "quest": step["questName"], "n": n}
    return None


def offer_finds(quests, log):
    return first({"k": "offer", "quest": q["name"]} for q in quests if q.get("name") and q.get("id") not in log)


def lower(text):
    return text[:1].lower() + text[1:]


def step_finds(steps, log=None, here=None, plan=None):
    log = log or {}
    out, zones, hearths, camps, back = [], set(), set(), set(), set()
    for s in steps:
        kind = s.get("kind")
        if kind == "turnin" and s.get("npc") and s.get("questName"):
            if s.get("quest") in log and s["quest"] not in back:
                back.add(s["quest"])
                out.append({"k": "handin" if log[s["quest"]] else "helping", "npc": s["npc"], "quest": s["questName"]})
            if (s.get("cash") or 0) > 0:
                out.append({"k": "cash", "npc": s["npc"], "quest": s["questName"]})
        if kind == "pickup" and s.get("npc") and s.get("questName") and s.get("quest") not in log:
            out.append({"k": "pickup", "npc": s["npc"], "quest": s["questName"]})
        if kind == "objective" and mobs(s) and s.get("questName") and s["questName"] not in camps:
            camps.add(s["questName"])
            out.append({"k": "camp", "who": mobs(s), "quest": s["questName"]})
        h = s.get("hearth") or {}
        if h.get("p") and h.get("to") and h["to"] not in hearths:
            hearths.add(h["to"])
            out.append({"k": "hearth", "to": h["to"]})
            minutes = round((h.get("saves") or 0) / 60)
            if minutes >= quip_lines.SAVES_LEAST:
                out.append({"k": "saves", "to": h["to"], "min": minutes})
        if kind == "errand" and s.get("what") == "train" and s.get("npc") and s.get("min"):
            out.append({"k": "train", "npc": s["npc"], "level": s["min"]})
        if s.get("group") and s.get("questName"):
            out.append({"k": "group", "quest": s["questName"]})
        if here and s.get("zone") and s["zone"] != here and s["zone"] not in zones:
            zones.add(s["zone"])
            out.append({"k": "zone", "zone": s["zone"]})
    if plan is None:
        return first(out)
    if plan.get("levelTo"):
        out.append({"k": "levelTo", "level": plan["levelTo"]})
    out += [{"k": "grind", "level": g["to"]} for g in plan.get("grinds") or () if g.get("to")]
    if len(steps) >= 2:
        out.append({"k": "steps", "count": len(steps)})
    if steps and steps[0].get("text"):
        out.append({"k": "first", "step": lower(steps[0]["text"])})
    out += [{"k": "later", "quest": x["name"]} for x in plan.get("later") or () if x.get("name") and not x.get("missing")]
    return first(out)
