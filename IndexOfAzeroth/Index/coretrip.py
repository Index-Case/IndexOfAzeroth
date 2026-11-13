# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import director_rules as rules
from errands import in_hand, learnable, money_note, paid_by, teaches_all
import hearth
import plansteps

NEAR = 150.0
HANDIN_OFF = 30.0


def core_kind(s, spec=None):
    if s.get("value") == "core":
        return s.get("kind") or "class"
    mine = (s.get("specs") or {}).get(spec) if spec else None
    if isinstance(mine, dict) and mine.get("value") == "core":
        return mine.get("kind") or "spec"
    return None


def core_levels(schedule, known, race, spec, upto):
    known, core, every = set(known), {}, {}
    while True:
        more = [(lv, s) for lv, s in learnable(schedule, known, race, upto) if s["id"] not in known]
        if not more:
            break
        for lv, s in more:
            known.add(s["id"])
            every.setdefault(lv, []).append(s)
            kind = core_kind(s, spec)
            if kind:
                core.setdefault(lv, []).append((s, kind))
    return core, every


def core_words(core):
    names = list(dict.fromkeys(s["name"] for kind in ("class", "spec") for s, k in core if k == kind))
    said = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    return rules.say("core_now_one" if len(names) == 1 else "core_now", {"spells": said})


def xp_through(steps, table, level, into, cap):
    before, t = [0.0], 0.0
    for s in steps:
        t += float(s.get("xp") or 0)
        before.append(t)

    def need(L):
        return sum(table.get(lv) or 0 for lv in range(level, min(L, cap))) - into
    return before, need


def unit_end(steps, i, at, near=NEAR):
    q = steps[i].get("quest") if 0 <= i < len(steps) else None
    j = i
    while j + 1 < len(steps):
        s = steps[j + 1]
        here = hearth.spot(s)
        if s.get("kind") != "objective" or not here or not at or here[0] != at[0] \
                or math.hypot(here[1] - at[1], here[2] - at[2]) > near or (q is not None and s.get("quest") != q):
            break
        j += 1
    return j


def at_hand(steps, start):
    j = -1
    while j + 1 < len(steps):
        s = steps[j + 1]
        if s.get("kind") != "objective" or not plansteps.here(s, start):
            break
        j += 1
    return j


def last_spot(steps, i, start):
    return next((hearth.spot(s) for s in reversed(steps[:i + 1]) if hearth.spot(s)), start)


def ready_by(steps, j):
    later = {s.get("quest") for s in steps[j + 1:] if s.get("kind") in ("pickup", "objective", "dungeon")}
    return [k for k in range(j + 1, len(steps)) if steps[k].get("kind") == "turnin" and steps[k].get("quest") is not None
            and steps[k]["quest"] not in later]


def on_way(steps, j, here, there, walk):
    pos, took = here, []
    if not here or not there:
        return took
    for k in sorted(ready_by(steps, j), key=lambda k: walk(here, hearth.spot(steps[k]) or here)):
        g = hearth.spot(steps[k])
        if not g or g[0] != pos[0] or g[0] != there[0]:
            continue
        if walk(pos, g) + walk(g, there) - walk(pos, there) <= HANDIN_OFF:
            pos = g
            took.append(k)
    return took


def spot_of(trainer):
    return tuple(trainer[1][:3])


def path(frm, spots, walk):
    t, pos = 0.0, frm
    for p in spots:
        t, pos = t + walk(pos, p), p
    return t


def goes_on(steps, j, took, frm, walk):
    took, pos, replaced = set(took), frm, 0.0
    for k in range(j + 1, len(steps)):
        p = hearth.spot(steps[k])
        if not p:
            continue
        if k not in took:
            return p, replaced + walk(pos, p)
        replaced, pos = replaced + walk(pos, p), p
    return None, replaced


def trainer_for(trips, walk):
    return min(trips, key=lambda x: trip_added(x, walk))


def trip_added(x, walk):
    on, replaced = x[2]
    return x[1] + (walk(spot_of(x[0]), on) if on else 0.0) - replaced


def hand_end(steps, start):
    hand = {s.get("quest") for s in steps[:at_hand(steps, start) + 1]} - {None}
    return max([k for k, s in enumerate(steps) if s.get("kind") == "objective" and s.get("quest") in hand] + [-1])


def train_step(L, core, spells, trainer, cost=None, pay=0):
    name, p = trainer[0], trainer[1]
    text = f"Train at {name}"
    return {"kind": "errand", "what": "train", "key": f"train:{L}", "quest": None, "questName": text, "text": text,
            "npc": name, "inst": p[0], "at": [round(p[1], 1), round(p[2], 1)] + ([round(p[3], 1)] if len(p) > 3 and p[3] is not None else []),
            "need": {"spells": [s["id"] for s in spells], "level": L, **({"pay": int(round(pay))} if pay else {})}, "min": L, "trip": L, "why": core_words(core),
            **({"map": int(p[4])} if len(p) > 4 and p[4] else {}), **({"cost": int(round(cost))} if cost else {})}


def visit(steps, e, last, cores, L, every, taught, trainers, teaches, me, by=None):
    if last:
        k = next(i for i, s in enumerate(steps) if s is last[0])
        steps = [s if s.get("trip") != last[0]["trip"] else {f: v for f, v in s.items() if f != "trip"}
                 for i, s in enumerate(steps) if i != k]
        taught = taught - {s["id"] for s in last[2]}
    spells = [s for lv in sorted(every) if lv <= L for s in every[lv] if s["id"] not in taught]
    ids = {s["id"] for s, _ in cores}
    mine = [t for t in trainers if teaches_all(teaches, t[3], ids)]
    price = sum(s.get("cost") or 0 for s, _ in cores)
    m = paid_by(steps, me.get("money"), price, e + 1)
    if not mine or m is None:
        return None
    e = max(e, m - 1)
    if by is not None and e >= by:
        return None
    most = in_hand(steps, e + 1) - 1
    if by is not None:
        most = min(most, by - 1)
    return steps, e, most, cores, spells, mine, price, taught


def plan(steps, start, walk, me, schedule, table, trainers, teaches=None, cap=60):
    steps = [dict(s) for s in steps]
    travel = getattr(walk, "travel", walk)
    known = me.get("known")
    notes = []
    if not schedule or known is None or not trainers:
        return steps, notes
    level, into = me.get("level") or 1, float(me.get("xp") or 0)
    skipped = me.get("skipped") or {}
    passed = max([int(k[6:]) for k in skipped if k.startswith("train:") and k[6:].isdigit()] + [0])
    core, every = core_levels(schedule, known, me.get("race"), me.get("spec"), cap)
    taught, last = set(), None
    for L in sorted(core):
        if L <= passed or f"train:{L}" in skipped:
            continue
        before, need = xp_through(steps, table, level, into, cap)
        want = need(L)
        if want <= 0:
            d = -1
        else:
            d = next((k for k in range(len(steps)) if before[k + 1] >= want), None)
            if d is None:
                continue
        e = max(hand_end(steps, start), unit_end(steps, d, hearth.spot(steps[d])) if d >= 0 else -1)
        prev = next((k for k, s in enumerate(steps) if last and s is last[0]), None)
        got = None
        if prev is not None and e < prev:
            got = visit(steps, e, last, list(last[1]) + list(core[L]), L, every, taught, trainers, teaches, me, prev)
            if got is None:
                e = prev
        if got is None:
            got = visit(steps, e, None, list(core[L]), L, every, taught, trainers, teaches, me)
        price = sum(s.get("cost") or 0 for s, _ in core[L])
        if got is None and me.get("money") is None and price:
            notes.append(money_note("train", "unknown", f"Training your level {L} spells", price, None, f"level {L} spells"))
            break
        if got is None:
            continue
        steps, first, most, cores, spells, mine, price, taught = got

        def trip_after(j):
            here = last_spot(steps, j, start)
            trips = []
            for t in mine:
                took = on_way(steps, j, here, spot_of(t), walk)
                trips.append((t, path(here, [hearth.spot(steps[k]) for k in took] + [spot_of(t)], travel),
                              goes_on(steps, j, took, here, travel), took))
            return trainer_for(trips, travel)
        e, (t, _, _, took) = min(((j, trip_after(j)) for j in range(first, most + 1)),
                                 key=lambda x: trip_added(x[1], travel))
        moved = [steps[k] for k in took]
        for s in moved:
            s["trip"] = L
        rest = [s for k, s in enumerate(steps) if k not in set(took)]
        go = train_step(L, cores, spells, t, sum(s.get("cost") or 0 for s in spells), price)
        steps = rest[:e + 1] + moved + [go] + rest[e + 1:]
        taught |= {s["id"] for s in spells}
        last = (go, cores, spells)
    return steps, notes
