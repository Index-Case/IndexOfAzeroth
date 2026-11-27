# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import gamelogs
import pvp

BURST = 3.0
RECAP = 10.0
COOLDOWN = 60.0
SNARE = "snare"
RESULTS = gamelogs.DAMAGE | gamelogs.MISSED | gamelogs.HEAL | {"SPELL_INSTAKILL", "SPELL_DRAIN", "SPELL_LEECH",
                                                               "SPELL_INTERRUPT", "SPELL_DISPEL"}


def other(side):
    return {pvp.YOU: pvp.THEM, pvp.THEM: pvp.YOU}.get(side)


def _column(e, units):
    side = lambda g: (units.get(g) or {}).get("side")
    if e["e"] == "UNIT_DIED" or e["e"] == "ENVIRONMENTAL_DAMAGE":
        return side(e.get("dg")) or pvp.YOU
    return side(e.get("sg")) or other(side(e.get("dg"))) or pvp.YOU


def _result(e):
    return e["e"] in RESULTS or e["e"] == "SPELL_AURA_APPLIED" and e.get("aura") == "DEBUFF"


def _shown_casts(events):
    shown, results = set(), set()
    same = {(e.get("sg"), e.get("sp"), e["t"]) for e in events if _result(e)}
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        key = (e.get("sg"), e.get("sp"))
        if e["e"] == "SPELL_CAST_SUCCESS":
            if key not in results and (*key, e["t"]) not in same:
                shown.add(i)
            results.discard(key)
        elif _result(e):
            results.add(key)
    return shown


def _held(events, i):
    e = events[i]
    broke = None
    for later in events[i + 1:]:
        if later.get("dg") != e.get("dg") or later.get("sp") != e.get("sp"):
            continue
        if later["e"] == "SPELL_AURA_BROKEN_SPELL":
            broke = later.get("xsn") or ""
        elif later["e"] == "SPELL_AURA_BROKEN":
            broke = ""
        elif later["e"] == "SPELL_AURA_REMOVED":
            return round(later["t"] - e["t"], 1), broke
    return None, broke


def _after(e, landed):
    u = e.get("iu") if e.get("ig") and e.get("ig") == e.get("dg") else None
    if u is None and e["e"] == "SWING_DAMAGE":
        got = landed.get((e["t"], e.get("sg"), e.get("dg")))
        u = got.pop(0) if got else None
    return (u["h"], u["mh"]) if u and u.get("mh") else None


def sequence(f, facts):
    events, units, start = f["events"], f["units"], f["t"]
    landed, shields = {}, {}
    for e in events:
        if e["e"] == "SWING_DAMAGE_LANDED" and e.get("iu") and e.get("ig") == e.get("dg"):
            landed.setdefault((e["t"], e.get("sg"), e.get("dg")), []).append(e["iu"])
    killing = {(d["at"], d["by"], d["who"], d["spell"]) for d in f["died"] if d["by"]}
    casts = _shown_casts(events)
    out = []
    for i, e in enumerate(events):
        kind = e["e"]
        line = {"s": round(e["t"] - start, 1), "c": _column(e, units), "by": e.get("sg"), "on": e.get("dg")}
        if kind == "SPELL_ABSORBED":
            shields[(e["t"], e.get("sg"), e.get("dg"), e.get("spn"))] = [e.get("xsn"), e.get("a")]
            continue
        if kind in gamelogs.DAMAGE or kind in ("SPELL_INSTAKILL", "SPELL_DRAIN", "SPELL_LEECH"):
            line["k"] = "hit"
        elif kind in gamelogs.MISSED:
            line["k"], line["m"] = "miss", e.get("m")
        elif kind in gamelogs.HEAL:
            line["k"] = "heal"
        elif kind == "SPELL_AURA_APPLIED" and e.get("aura") == "DEBUFF":
            fact = facts(e.get("sp")) or {}
            if fact.get("cc"):
                line["k"], line["cc"] = "cc", fact["cc"]
                line["held"], line["broke"] = _held(events, i)
            elif _column(e, units) != (units.get(e.get("dg")) or {}).get("side"):
                line["k"] = "debuff"
            else:
                continue
        elif kind == "SPELL_INTERRUPT":
            line["k"], line["x"] = "interrupt", e.get("xsn")
        elif kind == "SPELL_DISPEL":
            purge = e.get("aura") == "BUFF" and _column(e, units) != (units.get(e.get("dg")) or {}).get("side")
            line["k"], line["x"] = ("purge" if purge else "dispel"), e.get("xsn")
        elif kind == "UNIT_DIED":
            if not (units.get(e.get("dg")) or {}).get("side"):
                continue
            line["k"], line["by"] = "death", None
        elif kind == "SPELL_CAST_SUCCESS" and i in casts:
            line["k"] = "cast"
            if not e.get("dg"):
                line["on"] = None
        else:
            continue
        if e.get("spn") and not kind.startswith("SWING") and kind != "UNIT_DIED":
            line["sp"], line["id"] = e["spn"], e.get("sp")
        for k in ("a", "cr", "oh", "sc"):
            if e.get(k) is not None and kind != "UNIT_DIED":
                line[k] = e[k]
        if line["k"] in ("hit", "heal"):
            after = _after(e, landed)
            if after:
                line["h"], line["mh"] = after
        if line["k"] in ("hit", "miss"):
            soaked = shields.pop((e["t"], e.get("sg"), e.get("dg"), e.get("spn")), None)
            if soaked:
                line["ab"] = soaked
            if kind.startswith("SWING") or (facts(e.get("sp")) or {}).get("auto"):
                line["auto"] = 1
        if line["k"] == "hit" and (e["t"], e.get("sg"), e.get("dg"), None if kind.startswith("SWING") else
                                   e.get("spn")) in killing:
            line["kb"] = 1
            killing.discard((e["t"], e.get("sg"), e.get("dg"), None if kind.startswith("SWING") else e.get("spn")))
        out.append(line)
    return out


def health(f, guids):
    start, out = f["t"], {}
    for e in f["events"]:
        g, u = e.get("ig"), e.get("iu")
        if g not in guids or not u or not u.get("mh"):
            continue
        s = round(e["t"] - start, 1)
        got = out.setdefault(g, [])
        if s <= 0 and got and got[-1][0] <= 0:
            got.pop()
        if not got or (got[-1][1], got[-1][2]) != (u["h"], u["mh"]):
            got.append([max(s, 0.0), u["h"], u["mh"]])
    return out


def _burst(hits):
    best, total, j = 0, 0, 0
    for i, (s, a) in enumerate(hits):
        total += a
        while s - hits[j][0] > BURST:
            total -= hits[j][1]
            j += 1
        best = max(best, total)
    return best


def numbers(f, lines, facts, racials, classed, prices):
    units = f["units"]
    side = lambda g: (units.get(g) or {}).get("side")
    sides = (pvp.YOU, pvp.THEM)
    out = {s: {"damage": 0, "healing": 0, "biggest": None, "burst": 0, "held": 0.0, "interrupts": 0, "dispels": 0,
               "purges": 0, "immune": 0, "school": {}, "used": [], "spent": 0} for s in sides}
    hits = {s: [] for s in sides}
    for x in lines:
        c, k = x["c"], x["k"]
        if k == "hit" and x.get("a") and side(x["on"]) == other(c) and side(x["by"]) == c:
            n = out[c]
            n["damage"] += x["a"]
            hits[c].append((x["s"], x["a"]))
            school = str(x.get("sc") or 1)
            n["school"][school] = n["school"].get(school, 0) + x["a"]
            if not n["biggest"] or x["a"] > n["biggest"]["a"]:
                n["biggest"] = {"sp": x.get("sp"), "a": x["a"], "cr": x.get("cr")}
        elif k == "heal" and side(x["on"]) == c and side(x["by"]) == c:
            out[c]["healing"] += max(0, (x.get("a") or 0) - (x.get("oh") or 0))
        elif k == "cc" and x["cc"] != SNARE and side(x["on"]):
            out[side(x["on"])]["held"] += x["held"] if x["held"] is not None else f["end"] - f["t"] - x["s"]
        elif k == "interrupt" and side(x["by"]) == c:
            out[c]["interrupts"] += 1
        elif k in ("dispel", "purge") and side(x["by"]) == c:
            out[c][f"{k}s"] += 1
        elif k == "miss" and x.get("m") == "IMMUNE" and side(x["on"]):
            out[side(x["on"])]["immune"] += 1
    for c in sides:
        out[c]["burst"] = _burst(hits[c])
        out[c]["held"] = round(out[c]["held"], 1)
    _used(f, facts, racials, classed, prices, out)
    return out


def used_kind(name, fact, racials, classed):
    own = name not in classed
    if own and name in racials:
        return "racial"
    if own and fact.get("use") in ("trinket", "consumable"):
        return fact["use"]
    return "cooldown" if fact.get("cd", 0) >= COOLDOWN else None


def _used(f, facts, racials, classed, prices, out):
    units = f["units"]
    counts, procs = {}, {}
    for e in f["events"]:
        g, name = e.get("sg"), e.get("spn")
        s = (units.get(g) or {}).get("side")
        if not s or not name or (units.get(g) or {}).get("kind") not in ("player", "pet"):
            continue
        fact = facts(e.get("sp")) or {}
        kind = used_kind(name, fact, racials, classed)
        if not kind:
            continue
        key = (s, name)
        if e["e"] == "SPELL_CAST_SUCCESS":
            got = counts.setdefault(key, {"sp": name, "id": e.get("sp"), "kind": kind, "n": 0, "item": fact.get("item")})
            got["n"] += 1
        elif kind == "racial":
            procs.setdefault(key, {"sp": name, "id": e.get("sp"), "at": set()})["at"].add(round(e["t"], 1))
    for key, got in procs.items():
        counts.setdefault(key, {"sp": got["sp"], "id": got["id"], "kind": "racial", "n": len(got["at"]), "item": None})
    items = sorted({u["item"] for u in counts.values() if u["kind"] == "consumable" and u["item"]})
    cost = prices(items) if items else {}
    for (s, _), u in sorted(counts.items(), key=lambda kv: (kv[1]["kind"], kv[1]["sp"])):
        u["cost"] = cost.get(u["item"]) * u["n"] if u["kind"] == "consumable" and cost.get(u["item"]) else None
        out[s]["used"].append(u)
        out[s]["spent"] += u["cost"] or 0


def recap(f, lines):
    d = f.get("killed_you")
    if not d:
        return None
    died = round(d["t"] - f["t"], 1)
    return {"s": died, "lines": [i for i, x in enumerate(lines) if x["k"] == "hit" and x["on"] == f["me"]
                                 and died - RECAP <= x["s"] <= died]}


def carried(f, facts):
    on = {}
    for e in f.get("auras") or ():
        if e["e"] == "UNIT_DIED":
            on.clear()
        elif e["e"] == "SPELL_AURA_REMOVED":
            on.pop(e.get("spn"), None)
        elif e.get("spn"):
            on[e["spn"]] = e
    return sorted(name for name, e in on.items()
                  if f["t"] - e["t"] <= ((facts(e.get("sp")) or {}).get("dur") or float("inf")))


def card(f, opponent):
    u = next((e["iu"] for e in reversed(f["events"]) if e.get("ig") == opponent and e.get("iu")), None)
    if not u:
        return None
    out = {k: u[k] for k in ("lv", "mh", "ap", "sp", "ar") if k in u}
    if u.get("pt") == 0:
        out["mp"] = u.get("mp")
    return out


def opened(f, facts, racials, classed, prices):
    lines = sequence(f, facts)
    return {"lines": lines, "health": health(f, {g for g in (f["me"], f["opponent"]) if g}),
            "numbers": numbers(f, lines, facts, racials, classed, prices), "recap": recap(f, lines),
            "numbersOf": card(f, f["opponent"]), "carried": carried(f, facts),
            "missing": [k for k in ("others", "numbers") if not f["recorded"][k]]}
