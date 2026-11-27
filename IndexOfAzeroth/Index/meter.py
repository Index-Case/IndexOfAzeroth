# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import math

import gamelogs
from dayrecord import DayRecord
from pvpfight import _burst

PERIODIC = {"SPELL_PERIODIC_DAMAGE", "SPELL_PERIODIC_MISSED"}
APPLIED, REMOVED = "SPELL_AURA_APPLIED", "SPELL_AURA_REMOVED"
CARRY_MOST = 2 * 3600
MULTI_LEAST = 2
VOLLEY = 0.1
PLACE_KINDS = {"z", "i"}


def placed(where, events):
    out = dict(where or {"zone": None, "inst": None})
    for e in events:
        if e.get("k") == "z":
            out["zone"] = e.get("zone")
        elif e.get("k") == "i":
            out["inst"] = e.get("kind")
    return out


def _row(rows, e):
    by = None if gamelogs.is_me(e.get("sf", 0)) else e.get("sn")
    key = (by, e.get("sp"), e.get("spn"))
    row = rows.get(key)
    if row is None:
        row = rows[key] = {"id": e.get("sp"), "n": e.get("spn"), "by": by, "h": 0, "c": 0, "tk": 0, "d": 0,
                           "lo": None, "hi": 0, "ok": 0, "m": {}, "cs": 0, "u": {}, "nt": set(), "vl": 0, "vh": 0,
                           "v0": None}
    return row


def _volley(row, t):
    if row["v0"] is None or t - row["v0"] > VOLLEY:
        row["vl"] += 1
        row["v0"] = t
    row["vh"] += 1


def struck(row):
    return bool(row["h"] or row["tk"] or row["m"])


def _uptime(spans, start, end):
    total, upto = 0.0, start
    for a, b in sorted(spans):
        a, b = max(a, upto), min(b, end)
        if b > a:
            total, upto = total + b - a, b
    return total


def _aura_side(e):
    if e["e"] not in (APPLIED, REMOVED) or not e.get("sp"):
        return None
    if gamelogs.is_me(e.get("df", 0)):
        return "up"
    return "down" if gamelogs.mine(e.get("sf", 0)) and not gamelogs.mine(e.get("df", 0)) else None


def _aura_key(e):
    return e.get("dg"), e["sp"], e.get("spn"), gamelogs.mine(e.get("sf", 0))


def _auras(marks, carried, start, end):
    by, unknown = {}, 0
    for key in set(marks) | set(carried):
        _, sp, name, yours = key
        spans, times = [], 0
        since = start if key in carried else None
        for i, (t, on) in enumerate(marks.get(key, ())):
            if on:
                times += 1
                since = t if since is None else since
            elif since is not None:
                spans.append((since, t))
                since = None
            elif i == 0:
                spans.append((start, t))
                unknown += 1
        if since is not None:
            spans.append((since, end))
        got = by.setdefault((sp, name), {"id": sp, "n": name, "spans": [], "yours": [], "x": 0})
        got["spans"] += spans
        got["yours"] += spans if yours else []
        got["x"] += times
    out, whole = [], set()
    for a in by.values():
        on = _uptime(a["spans"], start, end)
        out.append({"id": a["id"], "n": a["n"], "s": round(on, 1), "x": a["x"],
                    "y": round(_uptime(a["yours"], start, end), 1)})
        if on > 0 and on >= end - start - 1e-6:
            whole.add(a["id"])
    return sorted((a for a in out if a["s"] > 0), key=lambda a: (-a["s"], a["n"] or "")), unknown, whole


def _first_gone(events, start, end):
    first = {}
    for e in events:
        if e.get("k") == "c" and start <= e["t"] <= end and _aura_side(e) == "up":
            first.setdefault(_aura_key(e), e["e"])
    return {k for k, kind in first.items() if kind == REMOVED}


def breakdown(events, start, end, carried=None, where=None):
    rows, on, hits, foes, acts, inside = {}, {"h": 0, "c": 0, "d": 0, "m": {}}, [], {}, [], []
    out = {"t": start, "end": end, "dmg": 0, "ok": 0, "heal": 0, "oh": 0, "died": False, "group": False}
    marks = {"up": {}, "down": {}}
    carried = carried or {"up": (), "down": ()}
    on_me = set(carried["up"]) | _first_gone(events, start, end)
    on_ids = {k[1] for k in on_me}
    for e in events:
        if e.get("k") != "c" or not start <= e["t"] <= end:
            continue
        inside.append(e)
        kind, sf, df = e["e"], e.get("sf", 0), e.get("df", 0)
        mine_s, mine_d = gamelogs.mine(sf), gamelogs.mine(df)
        amount = e.get("a") or 0
        if gamelogs.in_group(sf) or gamelogs.in_group(df):
            out["group"] = True
        if kind in gamelogs.DAMAGE or kind in gamelogs.MISSED:
            if mine_s and not mine_d:
                row = _row(rows, e)
                acts.append(e["t"])
                tick = kind in PERIODIC
                if not tick:
                    _volley(row, e["t"])
                if kind in gamelogs.MISSED:
                    miss = e.get("m") or "MISS"
                    row["m"][miss] = row["m"].get(miss, 0) + 1
                    continue
                row["d"] += amount
                row["ok"] += max(0, e.get("ok") or 0)
                crit = 1 if e.get("cr") else 0
                for a in on_ids:
                    cell = row["u"].setdefault(a, [0, 0, 0, 0])
                    cell[0] += amount
                    cell[3 if tick else 1] += 1
                    cell[2] += 0 if tick else crit
                if tick:
                    row["tk"] += 1
                else:
                    row["h"] += 1
                    row["c"] += crit
                    if e.get("a") is not None:
                        row["lo"] = amount if row["lo"] is None else min(row["lo"], amount)
                        row["hi"] = max(row["hi"], amount)
                if amount:
                    hits.append((e["t"] - start, amount))
                    unit = e.get("dg") or e.get("dn")
                    row["nt"].add(unit)
                    foe = foes.setdefault(unit, [gamelogs.npc_of(e.get("dg")), e.get("dn"), 0, None])
                    foe[2] += amount
            elif gamelogs.is_me(df) and not mine_s:
                if kind in gamelogs.MISSED:
                    miss = e.get("m") or "MISS"
                    on["m"][miss] = on["m"].get(miss, 0) + 1
                else:
                    on["h"] += 1
                    on["c"] += 1 if e.get("cr") else 0
                    on["d"] += amount
        elif kind in gamelogs.HEAL and mine_s:
            over = e.get("oh") or 0
            out["heal"] += max(0, amount - over)
            out["oh"] += over
        elif kind == "SPELL_CAST_SUCCESS" and mine_s:
            _row(rows, e)["cs"] += 1
            acts.append(e["t"])
        elif kind == "UNIT_DIED" and gamelogs.is_me(df):
            out["died"] = True
        else:
            side = _aura_side(e)
            if side:
                marks[side].setdefault(_aura_key(e), []).append((e["t"], kind == APPLIED))
            if side == "up":
                (on_me.add if kind == APPLIED else on_me.discard)(_aura_key(e))
                on_ids = {k[1] for k in on_me}
    line = [0] * max(1, math.ceil(end - start))
    for at, amount in hits:
        line[min(len(line) - 1, int(at))] += amount
    kills = DayRecord.kills_in(inside)
    for k in kills:
        foe = foes.get(k["guid"])
        if foe:
            foe[3] = round(max(0.0, k["t"] - start), 1)
    enemies = sorted(foes.values(), key=lambda f: (-f[2], f[1] or ""))
    total = sum(f[2] for f in enemies)
    out.update(ps=[round(x) for x in line], act=round(max(acts) - min(acts), 1) if acts else 0.0,
               foe=enemies[0][1] if enemies else None, kills=len(kills), en=enemies,
               multi=len(enemies) >= MULTI_LEAST, main=round(100 * enemies[0][2] / total) if total else None,
               ttk=max(f[3] for f in enemies) if enemies and all(f[3] is not None for f in enemies) else None,
               zone=(where or {}).get("zone"), inst=(where or {}).get("inst"))
    up, unknown_up, whole = _auras(marks["up"], carried["up"], start, end)
    down, unknown_down, _ = _auras(marks["down"], carried["down"], start, end)
    part = {a["id"] for a in up} - whole
    spells = sorted(rows.values(), key=lambda r: (-r["d"], r["n"] or ""))
    for row in spells:
        row["lo"] = row["lo"] or 0
        row["nt"] = len(row["nt"])
        del row["v0"]
        row["u"] = {a: v for a, v in row["u"].items() if a in part}
        for k in [k for k in ("id", "n", "by") if row[k] is None] + (["u"] if not row["u"] else []):
            del row[k]
    out.update(dmg=sum(r["d"] for r in spells), ok=sum(r["ok"] for r in spells), burst=_burst(hits), sp=spells, on=on,
               up=up, down=down, unknown=unknown_up + unknown_down, whole=sorted(whole))
    return out


def fights(events, until, since=0.0):
    return Walk(events, until).more(since=since)


class Walk:

    CHUNK = 3000

    def __init__(self, events, until, on=None):
        self.events, self.until = events, until
        self.at = 0
        self.on = on or {"up": {}, "down": {}}
        self.where = None
        self.done = not events

    def _carry(self, events):
        on = self.on
        for e in events:
            side = _aura_side(e)
            if side and e["e"] == APPLIED:
                on[side].setdefault(_aura_key(e), e["t"])
            elif side:
                on[side].pop(_aura_key(e), None)
            elif e["e"] == "UNIT_DIED":
                if gamelogs.is_me(e.get("df", 0)):
                    on["up"].clear()
                else:
                    for key in [k for k in on["down"] if k[0] == e.get("dg")]:
                        del on["down"][key]

    def more(self, most=None, since=0.0):
        out = []
        while not self.done and (most is None or len(out) < most):
            out += self._chunk(None if most is None else most - len(out), since)
        return out

    def _chunk(self, most, since):
        events, size = self.events, self.CHUNK
        while True:
            upto = min(len(events), self.at + size)
            last = upto >= len(events)
            part = events[self.at:upto]
            spans = DayRecord.fight_spans(part, self.until if last else events[upto]["t"])
            if not last and spans and spans[-1][1] >= events[upto]["t"]:
                open_from = spans.pop()[0]
                cut = bisect.bisect_left([e.get("t", 0) for e in part], open_from)
                if cut == 0:
                    size *= 2
                    continue
                part = part[:cut]
            break
        if most is not None and len(spans) > most:
            spans = spans[:most]
            part = part[:bisect.bisect_right([e.get("t", 0) for e in part], spans[-1][1])]
        combat = [e for e in part if e.get("k") == "c"]
        times = [e["t"] for e in combat]
        places = [e for e in part if e.get("k") in PLACE_KINDS]
        out, at, moved = [], 0, 0
        for start, end in spans:
            first, past = bisect.bisect_left(times, start), bisect.bisect_right(times, end)
            self._carry(combat[at:first])
            upto = bisect.bisect_right([e["t"] for e in places], start)
            self.where = placed(self.where, places[moved:upto])
            moved = max(moved, upto)
            mine = combat[first:past]
            got = None
            if end >= since:
                there = {e.get("dg") for e in mine}
                on = self.on
                carried = {"up": {k for k, t in on["up"].items() if start - t <= CARRY_MOST},
                           "down": {k for k, t in on["down"].items() if start - t <= CARRY_MOST and k[0] in there}}
                got = breakdown(mine, start, end, carried, self.where)
            self._carry(mine)
            at = past
            if got and any(map(struck, got["sp"])):
                got["after"] = {"up": dict(self.on["up"]), "down": dict(self.on["down"])}
                out.append(got)
        self._carry(combat[at:])
        self.where = placed(self.where, places[moved:])
        self.at += len(part)
        self.done = self.at >= len(events)
        return out
