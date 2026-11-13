# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import director_rules
import errands
import planreport
import shared
from plansteps import EPIC_CODE, step_ids

TODO, DONE, WAIT, PARKED = 0, 1, 2, 4
FIELDS = (("npc", "npc"), ("min", "min"), ("req", "req"), ("limit", "limit"), ("pre", "pre"), ("any", "any"),
          ("par", "par"), ("dis", "dis"), ("maybe", "maybe"), ("grp", "group"), ("trip", "trip"), ("cq", "cq"),
          ("what", "what"), ("need", "need"), ("en", "escortNpc"), ("get", "get"),
          ("ni", "npcId"), ("oi", "objectId"),
          ("takes", "takes"))


def dist(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def entries(steps):
    out = []
    for n, st in enumerate(steps):
        code, ids = EPIC_CODE.get(st.get("kind")), step_ids(st)
        if not code or (not ids and code != "S") or not st.get("at"):
            continue
        e = {"k": code, "ids": ids, "inst": st["inst"], "at": [float(v) for v in st["at"][:2]], "text": st.get("text", "")}
        for key, src in FIELDS:
            if st.get(src) not in (None, ""):
                e[key] = st[src]
        if code != "S" and isinstance(st.get("lv"), (int, float)) and not isinstance(st.get("lv"), bool):
            e["wl"] = int(st["lv"])
        if code == "O" and st.get("spawns"):
            e["ar"] = shared.step_area(st["spawns"])
        more = shared.other_places(st, e.get("ar")) if code == "O" else None
        if more:
            e["hr"] = more
        if code == "O" and st.get("talk") and not e.get("npc") and st.get("target"):
            e["npc"] = st["target"]
        out.append((n, e))
    return out


def legs_of(es, start):
    out = [[] for _ in es]
    prev = base = {"inst": start[0], "at": list(start[1:3])} if start else None
    for k, e in enumerate(es[:shared.WAYS_AHEAD]):
        here = (e["inst"], *e["at"][:2])
        if prev is not None and prev["inst"] == e["inst"]:
            out[k].append(("way", (prev["inst"], *prev["at"][:2]), here))
            if prev.get("k") == "S" and base is not None and base is not prev and base["inst"] == e["inst"]:
                out[k].append(("alt", (base["inst"], *base["at"][:2]), here))
        prev, base = e, (e if e["k"] != "S" else base)
    return out


def lay_ways(es, start, ways, before=None):
    kept = {id(e): (m == 0, was) for m, (e, was) in enumerate(zip(before, legs_of(before, start)))} if before else {}
    out, legs = [], []
    for k, (e, now) in enumerate(zip(es, legs_of(es, start))):
        if kept.get(id(e)) == (k == 0, now):
            out.append(e)
            continue
        out.append({f: v for f, v in e.items() if f not in ("way", "alt")})
        legs.extend((k, key, a, b) for key, a, b in now)
    got = ways([(a, b) for _, _, a, b in legs]) if legs else []
    for (k, key, _, _), line in zip(legs, got):
        if line is None or isinstance(line, str) or (key == "alt" and "way" not in out[k]):
            continue
        pts = [[float(v) for v in q[:2]] for q in line]
        out[k][key] = pts[1:-1] if key == "way" and k else pts[:-1]
    return out


def entry_ways(E, i):
    e, out = E[i], []
    if e.get("way"):
        prev = E[i - 1] if i else None
        if prev is not None and prev["inst"] == e["inst"]:
            out.append([[float(v) for v in prev["at"][:2]]] + [[float(v) for v in b[:2]] for b in e["way"]])
        elif not i:
            out.append([[float(v) for v in b[:2]] for b in e["way"]])
    if e.get("alt"):
        out.append([[float(v) for v in b[:2]] for b in e["alt"]])
    h = e.get("hearth")
    if isinstance(h, dict) and h.get("w") and h.get("i") == e["inst"]:
        out.append([[float(v) for v in h["at"][:2]]] + [[float(v) for v in b[:2]] for b in h["w"]])
    return out


def key(e):
    if e.get("extra"):
        return "x:" + ",".join(str(i) for i in e.get("ids") or ())
    return f"{e.get('k') or '?'}:{','.join(str(i) for i in e.get('ids') or ())}:{e.get('text') or ''}"


def is_plan(e):
    return bool(e.get("cq")) or e.get("k") != "S" or e.get("trip") is not None


class State:

    def __init__(self, entries, log=None, done=(), parked=(), begun=(), ends=(), money=None):
        self.entries = entries
        self.money0 = money
        self.log0 = dict(log or {})
        self.done0 = set(done)
        self.parked = set(parked)
        self.begun0 = set(begun)
        self.ends = list(ends)
        self.hand_ins = {e["ids"][0] for e in entries if e["k"] == "T" and e.get("ids")}
        self.plan = [is_plan(e) for e in entries]
        self.works = {}
        for e in entries:
            for q in (e.get("ids") or ())[:1] if e["k"] == "O" else e.get("ids") or () if e["k"] == "D" else ():
                self.works.setdefault(q, set()).add(key(e))
        self._reach = None

    def at(self, k):
        return Look(self, k)

    def reached(self, e, level=False, money=False):
        if self._reach is None:
            quests, keys, takers, mins, pays = {}, {}, {}, set(), set()
            for i, x in enumerate(self.entries):
                for q in (*(x.get("ids") or ()), *(x.get("pre") or ()), *(x.get("any") or ())):
                    quests.setdefault(q, set()).add(i)
                keys.setdefault(key(x), set()).add(i)
                for t in self.entries if isinstance(x.get("takes"), dict) else ():
                    if t is not x and takes_from(x, t):
                        takers.setdefault(key(t), set()).add(i)
                if x.get("min"):
                    mins.add(i)
                if x["k"] == "S" and isinstance(x.get("need"), dict) and x["need"].get("pay"):
                    pays.add(i)
            self._reach = quests, keys, takers, mins, pays
        quests, keys, takers, mins, pays = self._reach
        out = set(keys.get(key(e), ())) | takers.get(key(e), set())
        for q in e.get("ids") or ():
            out |= quests.get(q, set())
        return out | (mins if level else set()) | (pays if money else set())


class Look:

    def __init__(self, st, k, level=None):
        self.st, self.k = st, 0
        self.log, self.turned, self.keys = dict(st.log0), set(st.done0), set()
        self.spent = 0
        self.money = st.money0
        self.begun = set(st.begun0)
        self._states = None
        for e in st.entries[:k]:
            self._done(e)
        self.level = level if level is not None else self.level_at(k)

    def _done(self, e):
        q = e["ids"][0] if e.get("ids") else None
        self.keys.add(key(e))
        if e["k"] == "P" and q is not None:
            self.log.setdefault(q, False)
        elif e["k"] == "T" and q is not None:
            self.log.pop(q, None)
            self.turned.add(q)
        self.spent += e.get("dm") or 0
        self.money = None if self.st.money0 is None else self.st.money0 + self.spent
        self.begun = set()
        self.k += 1

    def next(self, level=None):
        e, was = self.st.entries[self.k], (self.level, self.money)
        self._done(e)
        self.level = level if level is not None else self.level_at(self.k)
        if self._states is not None:
            for i in self.st.reached(e, self.level != was[0], self.money != was[1]):
                self._states[i] = self.state(self.st.entries[i])
        return self

    def on(self, st):
        other = Look.__new__(Look)
        other.__dict__.update(self.__dict__)
        other.st, other._states = st, None
        other.log, other.turned, other.keys, other.begun = dict(self.log), set(self.turned), set(self.keys), set(self.begun)
        return other

    def states(self):
        if self._states is None:
            self._states = [self.state(e) for e in self.st.entries]
        return self._states

    def level_at(self, k):
        for e in reversed(self.st.entries[:k + 1]):
            if isinstance(e.get("wl"), int):
                return e["wl"]
        return 1

    def in_log(self, q):
        return q is not None and q in self.log

    def complete(self, q):
        if not self.in_log(q):
            return False
        if self.log.get(q):
            return True
        works = self.st.works.get(q)
        if not works:
            return q not in self.st.log0
        return works <= self.keys

    def needs_first(self, e):
        out, opened = [], any(p in self.turned for p in e.get("any") or ())
        for group in (e.get("pre") or (), () if opened else e.get("any") or ()):
            for p in group:
                if p in self.st.hand_ins and p not in self.turned:
                    out.append(p)
        return out

    def waits_on(self, e):
        needs = self.needs_first(e)
        return next((p for p in needs if p in self.st.parked), needs[0] if needs else None)

    def expected(self, e):
        def turned(p):
            return p in self.turned or p not in self.st.hand_ins
        if not all(turned(p) for p in e.get("pre") or ()):
            return False
        if e.get("any") and not any(turned(p) for p in e["any"]):
            return False
        if e.get("par") is not None and not self.in_log(e["par"]):
            return False
        if e.get("dis") is not None and self.in_log(e["dis"]):
            return False
        return True

    def done(self, e):
        if e["k"] == "S":
            return key(e) in self.keys
        if e["k"] == "O" and len(e.get("ids") or ()) == 1 and self.in_log(e["ids"][0]) and key(e) in self.keys:
            return True
        for q in e.get("ids") or ():
            ok = q in self.turned or (e["k"] == "P" and self.in_log(q)) or (e["k"] in ("O", "D") and self.complete(q))
            if not ok:
                return False
        return True

    def below(self, e):
        return bool(e.get("min")) and self.level < e["min"]

    def untaught(self, e):
        need = e.get("need") if isinstance(e.get("need"), dict) else {}
        want = need.get("taught")
        if not want:
            return False
        for t in self.st.entries:
            rows = (t.get("need") or {}).get("skills") if isinstance(t.get("need"), dict) else None
            if t is not e and not takes_from(t, e) and any(r[0] == want[0] and r[1] >= want[1] for r in rows or ()):
                return self.base(t) != DONE
        return False

    def base(self, e):
        if e["k"] == "S":
            if self.done(e):
                return DONE
            if e.get("what") == "wall":
                return WAIT
            if isinstance(e.get("takes"), dict) and any(
                    t is not e and takes_from(e, t) and self.base(t) in (TODO, WAIT) for t in self.st.entries):
                return WAIT
            if self.below(e) or self.untaught(e):
                return WAIT
            pay = (e.get("need") or {}).get("pay") if isinstance(e.get("need"), dict) else None
            if pay and self.money is not None and self.money < pay:
                return WAIT
            return TODO
        ids = e.get("ids") or ()
        if e["k"] == "D":
            have = any(self.in_log(q) or q in self.turned for q in ids)
            open_ = any(self.in_log(q) and not self.complete(q) for q in ids)
            return DONE if have and not open_ else (TODO if have else WAIT)
        if self.done(e):
            return DONE
        q = ids[0] if ids else None
        if e["k"] == "P":
            if self.waits_on(e) is not None:
                return WAIT
            if self.below(e):
                return WAIT
            return TODO
        if not self.in_log(q):
            return WAIT
        if self.below(e):
            return WAIT
        if e["k"] == "T" and not self.complete(q):
            return WAIT
        return TODO

    def state(self, e):
        b = self.base(e)
        if b != DONE and e["k"] != "D" and e.get("ids") and e["ids"][0] in self.st.parked:
            return PARKED, b
        return b, b

    def takes(self, e, s, b):
        if e["k"] == "T":
            return s == TODO or (s == PARKED and b == TODO)
        if e["k"] != "P" or e.get("limit") or not self.expected(e):
            return False
        if s == TODO:
            return True
        return s == WAIT and e.get("req") is not None and self.waits_on(e) is None and self.level >= e["req"]

    def open(self, e, s, b):
        return s != PARKED and self.takes(e, s, b) and not e.get("maybe") and not e.get("grp") and not e.get("limit")

    def after(self, s, t):
        a = (s.get("ids") or [None])[0]
        b = (t.get("ids") or [None])[0]
        if a is not None and a == b:
            return True
        if s["k"] == "P" and t["k"] == "T" and b in self.needs_first(s):
            return True
        if takes_from(s, t):
            return True
        return bool(s.get("maybe")) and with_giver(s, t)


def takes_from(s, t):
    if s["k"] != "S" or t["k"] != "S" or not isinstance(s.get("takes"), dict) or not isinstance(t.get("need"), dict):
        return False
    takes, need = s["takes"], t["need"]
    got = {"items": {str(row[0]) for row in need.get("items") or () if row},
           "recipes": {str(v) for v in need.get("recipes") or ()},
           "skills": {str(row[0]) for row in need.get("skills") or () if row and list(row[1:2]) == [1]}}
    return any(got[kind] & {str(v) for v in takes.get(kind) or ()} for kind in got)


def with_giver(s, t):
    def giver(e):
        return ("ni", e["ni"]) if e.get("ni") else ("oi", e["oi"]) if e.get("oi") else None
    return giver(t) is not None and giver(t) == giver(s) and t.get("inst") == s.get("inst") \
        and dist(t["at"][0], t["at"][1], s["at"][0], s["at"][1]) <= director_rules.GUIDE["with_giver"].value


def lead(look, at):
    E, n = look.st.entries, len(look.st.entries)
    states = look.states()
    plan = look.st.plan
    N = next((i for i in range(n) if plan[i] and (states[i][0] == TODO
                                                  or (states[i][0] == WAIT and look.takes(E[i], *states[i])))), None)
    if N is None:
        return None, None
    offs, plan_c = weigh(look, states, plan, N, *at)
    if plan_c["kind"] == "progress":
        return plan_c, N
    return next((c for c in offs if c["sure"]), plan_c), N


def stretch_run(E, N):
    lengths, prev, counted = [], None, 0
    for e in E[N:]:
        counted += 1
        if counted > director_rules.RUN["steps"].value + 1:
            break
        if prev is not None and prev["inst"] == e["inst"]:
            lengths.append(dist(prev["at"][0], prev["at"][1], e["at"][0], e["at"][1]))
        prev = e
    return director_rules.run(lengths)


def off_way(E, P, inst):
    return E[P]["inst"] != inst


def order(look, states, plan, P, t, inst):
    E, stops, anchor, counted = look.st.entries, [], None, 0
    placed = not (t.get("i") is not None and t["i"] > P)
    if placed:
        stops.append(t)
    for i in range(P + 1, len(E)):
        e = E[i]
        if plan[i] and states[i][0] in (TODO, WAIT) and e["inst"] == inst:
            stop = t if t.get("i") == i else {"e": e, "key": key(e), "x": e["at"][0], "y": e["at"][1], "ar": e.get("ar"),
                                               "order": i, "open": look.open(e, *states[i]), "ways": entry_ways(E, i)}
            counted += 1
            if counted > director_rules.RUN["steps"].value and placed:
                anchor = stop
                break
            stops.append(stop)
            placed = placed or stop is t
    return stops, anchor


def weigh(look, states, plan, N, inst, px, py):
    E, n = look.st.entries, len(look.st.entries)
    run = stretch_run(E, N)
    reach = {name: director_rules.reach(name, run) for name in ("giver", "area")}
    away = off_way(E, N, inst)
    offs, keys = [], set()
    getting = {e["ids"][0] for e, (s, _) in zip(E, states) if e.get("get") and e.get("ids") and s == TODO}

    def waits_for_item(e):
        return not e.get("get") and bool(e.get("ids")) and e["ids"][0] in getting

    def add(c):
        if c["key"] not in keys:
            keys.add(c["key"])
            offs.append(c)

    def tried_later(i, e):
        return e["k"] == "P" and bool(e.get("maybe")) and any(
            E[j]["k"] in ("P", "T") and states[j][0] in (TODO, WAIT) and not E[j].get("maybe") and with_giver(e, E[j])
            for j in range(i))

    def found(i, e):
        return {"i": i, "e": e, "key": key(e), "ar": e.get("ar")}

    for i in range(n):
        e, (s, b) = E[i], states[i]
        if e["inst"] != inst or i == N:
            continue
        d = dist(e["at"][0], e["at"][1], px, py)
        q = e["ids"][0] if e.get("ids") else None
        if not plan[i]:
            if s == TODO and d <= reach["giver"]:
                add({**found(i, e), "kind": "errand", "walk": d, "x": e["at"][0], "y": e["at"][1], "sure": away})
        elif e["k"] == "O":
            if s != TODO or not look.in_log(q) or waits_for_item(e):
                continue
            got = away and director_rules.here({"ar": e.get("ar"), "hr": e.get("hr"), "x": e["at"][0], "y": e["at"][1]},
                                               px, py, run)
            if got:
                fa, bx, by, _, mx, my = got
                add({**found(i, e), "kind": "area", "walk": max(0, fa), "x": bx, "y": by, "ox": mx, "oy": my, "sure": True})
        elif e["k"] in ("T", "P") and look.takes(e, s, b) and d <= reach["giver"] and not tried_later(i, e):
            add({**found(i, e), "kind": "handin" if e["k"] == "T" else "pickup", "walk": d, "x": e["at"][0], "y": e["at"][1],
                 "sure": away, "open": look.open(e, s, b), "ways": entry_ways(E, i)})
    for x in look.st.ends:
        q = x.get("q")
        if q in look.st.hand_ins or not look.complete(q) or x.get("i") != inst or not isinstance(x.get("at"), list):
            continue
        e = {"k": "T", "ids": [q], "inst": x["i"], "at": x["at"][:2], "npc": x.get("npc"), "extra": True}
        d = dist(e["at"][0], e["at"][1], px, py)
        if d <= reach["giver"]:
            add({"e": e, "key": key(e), "extra": True, "kind": "handin", "walk": d, "x": e["at"][0], "y": e["at"][1],
                 "sure": True})
    sN = E[N]
    plan_c = {"i": N, "e": sN, "key": key(sN), "kind": "next", "plan": True, "ar": sN.get("ar"), "ways": entry_ways(E, N)}
    if sN["inst"] != inst:
        far = director_rules.COST["far"].value
        plan_c.update(walk=far, x=px + far, y=py)
    elif sN["k"] == "O":
        fa, bx, by, _, mx, my = director_rules.among({"ar": sN.get("ar"), "loop": sN.get("loop"), "x": sN["at"][0],
                                                      "y": sN["at"][1]}, px, py)
        inside = fa <= (0 if sN.get("ar") else reach["area"])
        plan_c.update(walk=max(0, fa), x=bx, y=by, ox=mx, oy=my)
        if plan_c["key"] in look.begun and inside and not waits_for_item(sN):
            plan_c["kind"] = "progress"
    else:
        plan_c.update(walk=dist(sN["at"][0], sN["at"][1], px, py), x=sN["at"][0], y=sN["at"][1])
    for c in offs:
        if not c["sure"] and c["kind"] == "errand":
            c["sure"] = c["i"] < N or director_rules.apart(c, plan_c)
        elif not c["sure"]:
            stops, anchor = order(look, states, plan, N, c, inst)
            c["saves"] = director_rules.sooner(c, plan_c, stops, anchor, {"x": px, "y": py}, run)
            c["sure"] = c["saves"]["yes"]
    return offs, plan_c


def leaves(e, at):
    if at is None or e["inst"] != at[0]:
        return (e["inst"], e["at"][0], e["at"][1])
    _, x, y = director_rules.reached({"x": e["at"][0], "y": e["at"][1], "ar": e.get("ar")}, at[1], at[2])
    return (e["inst"], x, y)


SETTLE_MOVES = 80
SETTLE_PASSES = 8
SETTLE_EACH = 3


def units_of(steps, levels=None):
    units, glued, lv = [], [], 1
    for n, st in enumerate(steps):
        own = levels[n] if levels and n < len(levels) else st.get("lv")
        lv = own if isinstance(own, int) and not isinstance(own, bool) else lv
        es = entries([st])
        if es:
            dm = sum(errands.step_money(s) for s in glued + [st])
            units.append((glued + [st], {**es[0][1], **({"dm": dm} if dm else {})}, lv))
            glued = []
        else:
            glued.append(st)
    return units, glued


def laid(units, start, ways, before=None):
    if not ways:
        return units
    return [(u[0], e, u[2]) for u, e in zip(units, lay_ways([u[1] for u in units], start, ways,
                                                             before and [u[1] for u in before]))]


def lead_at(units, k, at, log=None, done=(), parked=(), money=None):
    return lead(Look(State([u[1] for u in units], log, done, parked, money=money), k, level=units[k][2]), at)


def look_of(units, log=None, done=(), parked=(), money=None):
    return Look(State([u[1] for u in units], log, done, parked, money=money), 0, level=units[0][2])


def parked_of(steps):
    return {q for st in steps if st.get("aside") for q in step_ids(st)}


def breaks(steps, start, log=None, done=(), levels=None, money=None, ways=None):
    if not start or not steps:
        return []
    units = laid(units_of(steps, levels)[0], start, ways)
    parked, out, at = parked_of(steps), [], tuple(start[:3])
    look = look_of(units, log, done, parked, money) if units else None
    for k in range(len(units)):
        if k:
            look.next(units[k][2])
        best, N = lead(look, at)
        if N is None:
            break
        j = best.get("i", -1) if best is not None else -1
        if best is not None and (j is None or j > N) and best["key"] != key(units[N][1]):
            row = (N, units[N][1].get("text"), best["e"].get("text") or best["key"])
            if row not in out:
                out.append(row)
        at = leaves(units[k][1], at)
    return out


def settle(steps, start, log=None, done=(), levels=None, log_most=None, money=None, ways=None):
    import questplan
    if not start or not steps:
        return list(steps), []
    log_most = log_most or questplan.LOG_MOST
    units, glued = units_of(steps, levels)
    units = laid(units, start, ways)
    parked, held = parked_of(steps), len(log or {})

    def log_fits(trial, k, j):
        n = held
        for m, u in enumerate(trial[:j + 1]):
            n += 1 if u[1]["k"] == "P" else (-1 if u[1]["k"] == "T" else 0)
            if m >= k and n > log_most:
                return False
        return True

    moved, brought = [], {}
    for _ in range(SETTLE_PASSES):
        k, at, before = 0, tuple(start[:3]), len(moved)
        look = look_of(units, log, done, parked, money)
        while k < len(units):
            planreport.report(at=(units[k][0][-1], k + 1, len(units)))
            best, N = lead(look, at)
            if N is None:
                break
            j = best.get("i") if best is not None else None
            if j is not None and j > N and best["key"] != key(units[N][1]) \
                    and brought.get(best["key"], 0) < SETTLE_EACH and len(moved) < SETTLE_MOVES \
                    and not any(look.after(units[j][1], units[m][1]) for m in range(k, j)):
                trial = units[:k] + [units[j][:2] + (units[k][2],)] + \
                    [u[:2] + (units[m + 1][2],) for m, u in enumerate(units[k:j], k)] + units[j + 1:]
                if units[j][1]["k"] != "P" or log_fits(trial, k, j):
                    trial = laid(trial, start, ways, units)
                    tried = look.on(State([u[1] for u in trial], log, done, parked, money=money))
                    again, _ = lead(tried, at)
                    if again is not None and again["key"] == key(trial[k][1]):
                        saves = best.get("saves")
                        moved.append((trial[k][1].get("text"), units[k][1].get("text"),
                                      saves and saves["later"] - saves["now"]))
                        brought[best["key"]] = brought.get(best["key"], 0) + 1
                        units, look = trial, tried
            at = leaves(units[k][1], at)
            k += 1
            if k < len(units):
                look.next(units[k][2])
        if len(moved) == before:
            break
    return [st for group, _, _ in units for st in group] + glued, moved
