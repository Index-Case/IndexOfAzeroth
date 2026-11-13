# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import bisect
import re
import threading
import time

import dayrecord
import gamelogs
import layers
import pvpfight
from serverlog import start_thread

QUIET = 10.0
COME_BACK = 30.0
LEAD = 15.0
ON_MOB = 15.0
HONOUR_AFTER = 10.0
DUEL_AFTER = 10.0
DIED_AFTER = 2.0
SPOT_AGE = 60.0
CARRIED_BACK = 7200.0
YOU, THEM = "you", "them"
ATTACKS = gamelogs.DAMAGE | gamelogs.MISSED | {"SPELL_INSTAKILL", "SPELL_DRAIN", "SPELL_LEECH"}
ACTIONS = {"SPELL_AURA_APPLIED", "SPELL_INTERRUPT", "SPELL_DISPEL", "SPELL_AURA_BROKEN_SPELL"}
PERIODIC = {"SPELL_PERIODIC_DAMAGE", "SPELL_PERIODIC_MISSED", "SPELL_PERIODIC_HEAL"}
HEALS = gamelogs.HEAL
HONOUR = re.compile(r"^You have been awarded (\d+) honor\b", re.I)
DUEL = re.compile(r"^(.+?) has (defeated|fled from) (.+?) in a duel\b")


def side_of(flags):
    if gamelogs.mine(flags):
        return YOU
    if not gamelogs.player_controlled(flags):
        return None
    return YOU if flags & gamelogs.FRIENDLY else THEM


def is_player(guid):
    return bool(guid) and guid.startswith("Player-")


def owners_of(events):
    out = {}
    for e in events:
        if e.get("k") != "c":
            continue
        if e.get("io") and e.get("ig"):
            out[e["ig"]] = e["io"]
        if e["e"] == "SPELL_SUMMON" and is_player(e.get("sg")) and e.get("dg"):
            out[e["dg"]] = e["sg"]
    return out


def me_of(events):
    for e in events:
        if e.get("k") != "c":
            continue
        for g, n, fl in ((e.get("sg"), e.get("sn"), e.get("sf", 0)), (e.get("dg"), e.get("dn"), e.get("df", 0))):
            if g and gamelogs.is_me(fl):
                return g, n
    return None, None


def split(events, owners, me):
    out, cur, alive = [], None, True
    player = lambda g: owners.get(g, g)
    for e in events:
        if e.get("k") != "c":
            continue
        t, kind, sf, df = e["t"], e["e"], e.get("sf", 0), e.get("df", 0)
        if kind == "UNIT_DIED":
            if cur and t - cur["end"] <= QUIET and player(e.get("dg")) in cur["foes"] | cur["friends"]:
                cur["end"] = t
            if e.get("dg") == me:
                cur, alive = None, False
            continue
        if not alive and (e.get("sg") == me and kind not in PERIODIC or e.get("dg") == me and kind in ATTACKS):
            alive = True
        attack = kind in ATTACKS
        if not attack and not (kind in ACTIONS and (kind != "SPELL_AURA_APPLIED" or e.get("aura") == "DEBUFF")):
            continue
        s, d = side_of(sf), side_of(df)
        src, dst = player(e.get("sg")), player(e.get("dg"))
        if s and d and s != d:
            foe, friend = (src, dst) if s == THEM else (dst, src)
            mine = gamelogs.mine(sf) or gamelogs.mine(df)
            if not cur:
                linked = False
            elif attack:
                linked = mine or foe in cur["foes"] or friend in cur["friends"]
            else:
                linked = mine or foe in cur["foes"] and friend in cur["friends"]
            gap = t - cur["end"] if cur else None
            if linked and (gap <= QUIET or gap <= COME_BACK and foe in cur["foes"]):
                cur["end"] = t
                if attack:
                    cur["foes"].add(foe)
                    cur["friends"].add(friend)
            elif mine and attack and alive and kind not in PERIODIC:
                cur = {"t": t, "end": t, "foes": {foe}, "friends": {friend, me} - {None}}
                out.append(cur)
        elif cur and attack and s is None and d == THEM and dst in cur["foes"] and t - cur["end"] <= QUIET:
            cur["end"] = t
    return out


def _killers(window, deaths):
    out = {}
    for i in deaths:
        victim, td = window[i]["dg"], window[i]["t"]
        party = next((e for e in window if e.get("e") == "PARTY_KILL" and e.get("dg") == victim
                      and abs(e["t"] - td) <= 1.0), None)
        blows = [e for e in window[:i + 1] if e.get("k") == "c" and e["e"] in gamelogs.DAMAGE
                 and e.get("dg") == victim and td - e["t"] <= QUIET]
        over = [e for e in blows if "ok" in e]
        last = (over or blows)[-1] if blows else None
        if party and last and last.get("sg") != party.get("sg"):
            last = next((e for e in reversed(blows) if e.get("sg") == party.get("sg")), last)
        out[i] = last or party
    return out


def fight_of(events, f, owners, me, times=None):
    times = times or [e.get("t", 0) for e in events]
    player = lambda g: owners.get(g, g)
    lo, hi = bisect.bisect_left(times, f["t"] - LEAD), bisect.bisect_right(times, f["end"] + DIED_AFTER)
    combat = [e for e in events[lo:hi] if e.get("k") == "c"]
    side = _sides(combat, f, player)
    member = lambda g: player(g) in side
    fight_events = [e for e in combat if member(e.get("sg")) or member(e.get("dg"))]
    between = [e for e in fight_events if member(e.get("sg")) and member(e.get("dg"))
               and {side_of(e.get("sf", 0)), side_of(e.get("df", 0))} == {YOU, THEM}]
    start = min([f["t"]] + [e["t"] for e in between if e["e"] in ATTACKS][:1])
    first = next((e for e in between if e["e"] in ATTACKS or e["e"] == "SPELL_AURA_APPLIED"
                  and e.get("aura") == "DEBUFF"), None)
    struck = side_of(first.get("sf", 0)) if first else None
    died = _deaths(fight_events, start, side, player)
    you_died = next((d for d in died if d["who"] == me), None)
    foes_died = [d for d in died if d["side"] == THEM]
    ours = sorted(g for g, s in side.items() if s == YOU and is_player(g))
    theirs = sorted(g for g, s in side.items() if s == THEM and is_player(g))
    outcome, opponent = _outcome(fight_events, me, side, player, you_died, foes_died, theirs)
    chat = [e for e in events[lo:bisect.bisect_right(times, f["end"] + max(HONOUR_AFTER, DUEL_AFTER))]
            if e.get("k") == "m" and e.get("ch") == "system"]
    names = {}
    for e in fight_events:
        for g, n in ((e.get("sg"), e.get("sn")), (e.get("dg"), e.get("dn"))):
            if g and n:
                names.setdefault(g, n)
    duel = _duel(chat, start, f["end"], names.get(me))
    if not duel and not died and _turned(events[lo:bisect.bisect_right(times, f["end"] + DUEL_AFTER)], theirs, player):
        duel = "lost" if outcome == "fled" else "won"
    honour = sum(int(m.group(1)) for e in chat for m in [HONOUR.match(e.get("text") or "")]
                 if m and any(0 <= e["t"] - d["t"] <= HONOUR_AFTER for d in foes_died))
    zone, spot, bg = _where(events, times, start)
    logged = next((e["w"] for e in fight_events if e.get("ig") == me and e.get("w")), None)
    mine = {g for e in fight_events for g, fl in ((e.get("sg"), e.get("sf", 0)), (e.get("dg"), e.get("df", 0)))
            if g and gamelogs.mine(fl)}
    kb = [d["who"] for d in foes_died if d["by"] in mine]
    hit = {player(e.get("dg")) for e in fight_events if e["e"] in gamelogs.DAMAGE and e.get("sg") in mine}
    decided = you_died or (foes_died[0] if foes_died else None)
    return {
        "id": f"{start:.3f}", "t": start, "end": f["end"], "secs": round(f["end"] - start, 1), "me": me,
        "opponent": opponent, "ours": len(ours), "theirs": len(theirs), "friends": ours, "foes": theirs,
        "attackers": _attackers(fight_events, player),
        "one": len(ours) == 1 and len(theirs) == 1, "outcome": duel or outcome, "duel": bool(duel),
        "died": died, "killed_you": you_died, "kb": kb,
        "assists": [d["who"] for d in foes_died if d["who"] in hit and d["who"] not in kb],
        "struck": struck, "on_mob": struck == THEM and _on_mob(combat, start),
        "honour": honour or None, "zone": zone, "spot": spot, "map": logged[0] if logged else (spot or {}).get("m"),
        "bg": bg, "ttk": round(decided["t"] - start, 1) if decided else None, **_damage(fight_events),
        "recorded": {"numbers": any("iu" in e for e in fight_events),
                     "others": any(not (gamelogs.mine(e.get("sf", 0)) or gamelogs.mine(e.get("df", 0)))
                                   for e in fight_events)},
        "units": _units(fight_events, side, player), "events": fight_events,
        "auras": _auras_before(events, times, start, opponent),
    }


def _auras_before(events, times, start, guid):
    if not guid:
        return []
    lo, hi = bisect.bisect_left(times, start - CARRIED_BACK), bisect.bisect_left(times, start)
    return [{k: e[k] for k in ("t", "e", "sp", "spn") if k in e} for e in events[lo:hi]
            if e.get("k") == "c" and e.get("dg") == guid and (
                e["e"] == "SPELL_AURA_APPLIED" and e.get("aura") == "BUFF" or e["e"] in ("SPELL_AURA_REMOVED", "UNIT_DIED"))]


def _attackers(fight_events, player):
    return len({player(e.get("sg")) for e in fight_events if e["e"] in ATTACKS and gamelogs.mine(e.get("df", 0))
                and side_of(e.get("sf", 0)) == THEM and is_player(player(e.get("sg")))})


def _damage(fight_events):
    dealt, taken = {}, {}
    for e in fight_events:
        if e["e"] not in gamelogs.DAMAGE or not e.get("a"):
            continue
        if gamelogs.mine(e.get("sf", 0)) and side_of(e.get("df", 0)) == THEM and e.get("spn"):
            dealt[e["spn"]] = dealt.get(e["spn"], 0) + e["a"]
        elif gamelogs.is_me(e.get("df", 0)) and side_of(e.get("sf", 0)) == THEM:
            school = str(e.get("sc") or 1)
            taken[school] = taken.get(school, 0) + e["a"]
    return {"dealt": dealt, "taken": taken}


def _sides(combat, f, player):
    side = {g: YOU for g in f["friends"]}
    side.update({g: THEM for g in f["foes"]})
    for e in combat:
        if f["t"] <= e["t"] <= f["end"] and e["e"] in HEALS and e.get("a"):
            healer, healed = player(e.get("sg")), player(e.get("dg"))
            if healed in side and healer not in side and side_of(e.get("sf", 0)) == side[healed]:
                side[healer] = side[healed]
    return side


def _units(fight_events, side, player):
    units = {}
    for e in fight_events:
        for g, n, fl in ((e.get("sg"), e.get("sn"), e.get("sf", 0)), (e.get("dg"), e.get("dn"), e.get("df", 0))):
            if g and g != gamelogs.NO_GUID and g not in units:
                units[g] = {"name": n, "side": side.get(player(g)) or side_of(fl), "player": player(g),
                            "kind": "player" if fl & gamelogs.PLAYER else "pet" if fl & gamelogs.PET
                            else "guardian" if fl & gamelogs.GUARDIAN else "npc"}
            elif g in units and not units[g]["name"]:
                units[g]["name"] = n
    return units


def _deaths(fight_events, start, side, player):
    deaths = [i for i, e in enumerate(fight_events) if e["e"] == "UNIT_DIED" and start <= e["t"]
              and is_player(e.get("dg")) and e.get("dg") in side]
    out = []
    for i, kb in _killers(fight_events, deaths).items():
        e = fight_events[i]
        kb = None if e.get("strip") else kb
        killer = kb.get("sg") if kb else None
        out.append({"t": e["t"], "who": e["dg"], "side": side[e["dg"]], "by": killer,
                    "by_player": player(killer) if killer else None,
                    "by_side": side_of(kb.get("sf", 0)) if kb else None, "sp": (kb or {}).get("sp"),
                    "spell": (kb or {}).get("spn"), "swing": bool(kb) and kb["e"].startswith("SWING"),
                    "at": (kb or {}).get("t"), "strip": bool(e.get("strip"))})
    return out


def _outcome(fight_events, me, side, player, you_died, foes_died, theirs):
    if you_died:
        by = you_died["by_player"]
        if by in side and side[by] == THEM:
            return "lost", by
        return "lost", _most_traded(fight_events, side, player, theirs)
    if foes_died:
        d = foes_died[0]
        return ("guards" if d["by"] and d["by_side"] is None else "won"), d["who"]
    opponent = _most_traded(fight_events, side, player, theirs)
    return _got_away(fight_events, me, opponent, player), opponent


def _most_traded(fight_events, side, player, theirs):
    traded = {}
    for e in fight_events:
        if e["e"] not in ATTACKS:
            continue
        if side_of(e.get("sf", 0)) == THEM and gamelogs.mine(e.get("df", 0)):
            foe = player(e.get("sg"))
        elif side_of(e.get("df", 0)) == THEM and gamelogs.mine(e.get("sf", 0)):
            foe = player(e.get("dg"))
        else:
            continue
        if is_player(foe) and side.get(foe) == THEM:
            traded[foe] = traded.get(foe, 0) + (e.get("a") or 0) + 1e-3
    if traded:
        return max(sorted(traded), key=lambda g: traded[g])
    return theirs[0] if theirs else None


def _on_mob(combat, start):
    return any(e["e"] in ATTACKS and start - ON_MOB <= e["t"] < start
               and (gamelogs.mine(e.get("sf", 0)) and side_of(e.get("df", 0)) is None
                    or gamelogs.mine(e.get("df", 0)) and side_of(e.get("sf", 0)) is None) for e in combat)


def _where(events, times, start):
    zone, spot, inside, near = None, None, None, True
    for i in range(bisect.bisect_right(times, start) - 1, -1, -1):
        e, k = events[i], events[i].get("k")
        if k == "i" and inside is None:
            inside = e.get("kind") or ""
        elif k == "z" and zone is None:
            zone = e.get("zone")
        elif k in ("p", "g") and spot is None and near:
            if k == "g" or start - e["t"] > SPOT_AGE:
                near = False
            else:
                spot = {"m": e.get("m"), "x": e.get("x"), "y": e.get("y")}
        if inside is not None and zone is not None and (spot is not None or not near):
            break
    bg = zone if inside == "pvp" else None
    return (zone if spot or bg else None), spot, bg


def _got_away(events, me, opponent, player):
    health = {}
    for e in events:
        u = e.get("iu")
        if u and u.get("mh") and e.get("ig"):
            health[player(e["ig"])] = u["h"] / u["mh"]
    if me in health and opponent in health and health[me] != health[opponent]:
        return "fled" if health[me] < health[opponent] else "escaped"
    took = {YOU: 0, THEM: 0}
    last = None
    for e in events:
        if e["e"] not in gamelogs.DAMAGE:
            continue
        if gamelogs.mine(e.get("df", 0)) and side_of(e.get("sf", 0)) == THEM:
            took[YOU] += e.get("a") or 0
            last = YOU
        elif gamelogs.mine(e.get("sf", 0)) and side_of(e.get("df", 0)) == THEM:
            took[THEM] += e.get("a") or 0
            last = THEM
    if took[YOU] != took[THEM]:
        return "fled" if took[YOU] > took[THEM] else "escaped"
    return "fled" if last == YOU else "escaped"


def _turned(events, theirs, player):
    return any(e.get("k") == "c" and player(g) in theirs and fl & gamelogs.FRIENDLY and not gamelogs.mine(fl)
               for e in events for g, fl in ((e.get("sg"), e.get("sf", 0)), (e.get("dg"), e.get("df", 0))))


def _duel(chat, start, end, me_name):
    mine = gamelogs.first_name(me_name).lower()
    if not mine:
        return None
    for e in chat:
        m = DUEL.match(e.get("text") or "")
        if not m or not (start <= e["t"] <= end + DUEL_AFTER):
            continue
        first, verb, other = m.group(1).split(" ")[0].lower(), m.group(2), m.group(3).split(" ")[0].lower()
        if mine not in (first, other):
            continue
        winner = first if verb == "defeated" else other
        return "won" if winner == mine else "lost"
    return None


def unwritten_deaths(events, me, name):
    if not me:
        return []
    logged = [e["t"] for e in events if e.get("k") == "c" and e["e"] == "UNIT_DIED" and e.get("dg") == me]
    flags = next((fl for e in events if e.get("k") == "c"
                  for g, fl in ((e.get("sg"), e.get("sf", 0)), (e.get("dg"), e.get("df", 0))) if g == me), 0)
    out, alive = [], None
    for e in events:
        if e.get("k") != "p":
            continue
        dead = bool((e.get("fl") or 0) & (dayrecord.DEAD_BIT | dayrecord.GHOST_BIT))
        if dead and alive is not None and not any(alive - LOG_SLACK <= t <= e["t"] + LOG_SLACK for t in logged):
            out.append({"t": e["t"], "k": "c", "e": "UNIT_DIED", "dg": me, "dn": name, "df": flags, "strip": 1})
        alive = None if dead else e["t"]
    return out


def fights_of(events, owners=None):
    owners = owners_of(events) if owners is None else owners
    me, name = me_of(events)
    more = unwritten_deaths(events, me, name)
    if more:
        events = sorted(events + more, key=lambda e: e.get("t", 0))
    times = [e.get("t", 0) for e in events]
    return [fight_of(events, f, owners, me, times) for f in split(events, owners, me)]



class SpellBook:

    def __init__(self, data):
        data = data or {}
        self.classes = {}
        self.of_id = {}
        self.of_name = {}
        self.rank = {}
        self.talents = {}
        for cid, c in (data.get("classes") or {}).items():
            self.classes[cid] = c.get("name")
            for lvl, row in (c.get("levels") or {}).items():
                for s in row.get("spells") or ():
                    self.of_id[s["id"]] = cid
                    self.of_name.setdefault(s["name"], set()).add(cid)
                    self.rank[s["id"]] = max(self.rank.get(s["id"], 0), int(lvl))
            for tree in c.get("trees") or ():
                for t in tree.get("talents") or ():
                    self.talents[(cid, t["name"])] = (tree["name"], 10 + (t.get("spent") or 0))
                    self.of_name.setdefault(t["name"], set()).add(cid)

    def class_of(self, spells):
        votes = {}
        for sid, name in spells.items():
            cid = self.of_id.get(sid)
            named = self.of_name.get(name) or set()
            if cid is None and len(named) == 1:
                cid = next(iter(named))
            if cid is not None:
                votes[cid] = votes.get(cid, 0) + 1
        best = sorted(votes.items(), key=lambda kv: -kv[1])
        if not best or len(best) > 1 and best[0][1] == best[1][1]:
            return None
        return best[0][0]

    def floor(self, cid, spells):
        best = (0, None)
        for sid, name in spells.items():
            lvl = self.rank.get(sid, 0) if self.of_id.get(sid) == cid else 0
            talent = self.talents.get((cid, name))
            if talent:
                lvl = max(lvl, talent[1])
            if lvl > best[0]:
                best = (lvl, name)
        return best

    def talents_of(self, cid, spells):
        return [{"name": n, "tree": self.talents[(cid, n)][0]}
                for n in sorted({n for n in spells.values() if (cid, n) in self.talents})]


def seen_in(events, seen=None):
    seen = {} if seen is None else seen
    for e in events:
        if e.get("k") != "c":
            continue
        for g, n, fl in ((e.get("sg"), e.get("sn"), e.get("sf", 0)), (e.get("dg"), e.get("dn"), e.get("df", 0))):
            if is_player(g) and not gamelogs.mine(fl):
                p = seen.setdefault(g, {"name": n, "spells": {}, "first": e["t"], "last": e["t"], "numbers": None})
                p["name"] = n or p["name"]
                p["first"], p["last"] = min(p["first"], e["t"]), max(p["last"], e["t"])
        g = e.get("sg")
        if g in seen and e.get("sp") and e.get("spn"):
            seen[g]["spells"][e["sp"]] = e["spn"]
        u = e.get("iu")
        if u and e.get("ig") in seen:
            seen[e["ig"]]["numbers"] = {k: u[k] for k in ("lv", "h", "mh", "ap", "sp", "ar") if k in u}
            if u.get("pt") == 0:
                seen[e["ig"]]["numbers"]["mp"] = u.get("mp")
    return seen


def joined(seen, more):
    for g, p in more.items():
        was = seen.get(g)
        if not was:
            seen[g] = {**p, "spells": dict(p["spells"])}
            continue
        was["spells"].update(p["spells"])
        if p["last"] >= was["last"]:
            was["name"], was["numbers"] = p["name"] or was["name"], p["numbers"] or was["numbers"]
        was["first"], was["last"] = min(was["first"], p["first"]), max(was["last"], p["last"])
    return seen


def players(events, book, racials=None, seen=None):
    racials = racials or {}
    seen = seen_in(events) if seen is None else seen
    out = {}
    for g, p in seen.items():
        cid = book.class_of(p["spells"])
        level, by = book.floor(cid, p["spells"]) if cid else (0, None)
        used = sorted({n for n in p["spells"].values() if n in racials})
        race = {racials[n] for n in used}
        out[g] = {"name": p["name"], "cls": cid, "race": race.pop() if len(race) == 1 else None,
                  "racials": [n for n in used if n not in book.of_name],
                  "talents": book.talents_of(cid, p["spells"]) if cid else [], "floor": level or None,
                  "floor_by": by, "numbers": p["numbers"], "first": p["first"], "last": p["last"]}
    return out


def skull(yours, theirs, floor=None):
    if not yours:
        return None
    if theirs == -1:
        theirs, floor = None, max(floor or 0, yours + 10)
    least = theirs or floor
    if least and yours <= layers.gray_level(least):
        return THEM
    if theirs and theirs <= layers.gray_level(yours):
        return YOU
    return None



LEVEL_NEAR = 3600.0
REBUILT_EVERY = 20.0
OFF_JOIN = 600.0
LOG_SLACK = 10.0


def shown_name(name):
    parts = (name or "").split("-")
    return " ".join(parts[:2]) if len(parts) >= 3 else parts[0]


def your_level(reports, t):
    level = None
    for r in sorted((r for r in reports or () if isinstance(r.get("at"), (int, float))), key=lambda r: r["at"]):
        if r["at"] > t:
            return level if level is not None else r.get("from")
        level = r.get("level")
    return level


def opponent_level(levels, t, floor=None):
    near = [x for x in levels or () if x[1] and abs(x[0] - t) <= LEVEL_NEAR]
    if near:
        return min(near, key=lambda x: abs(x[0] - t))[1], None
    least = floor or 0
    for when, level, at_least in levels or ():
        if when <= t:
            least = max(least, level or 0)
        if when <= t or abs(when - t) <= LEVEL_NEAR:
            least = max(least, at_least or 0)
    return None, least or None


def log_off(events):
    times = [e["t"] for e in events if e.get("k") == "c"]
    out, joinable = [], False
    for a, b in dayrecord.DayRecord.strip_fights(events, events[-1]["t"] if events else 0):
        i = bisect.bisect_left(times, a - LOG_SLACK)
        if i < len(times) and times[i] <= b + LOG_SLACK:
            joinable = False
            continue
        if out and joinable and a - out[-1][1] <= OFF_JOIN:
            out[-1][1] = b
        else:
            out.append([a, b])
        joinable = True
    return out


def revenge(rows):
    last = {}
    for r in rows:
        opp = (r.get("opp") or {}).get("guid")
        if not opp or r["duel"] or r["outcome"] not in ("won", "lost"):
            continue
        if r["outcome"] == "won" and last.get(opp) == "lost":
            r["revenge"] = YOU
        elif r["outcome"] == "lost" and last.get(opp) == "won":
            r["revenge"] = THEM
        last[opp] = r["outcome"]
    return rows


class Fights:

    def __init__(self, record, enemies=None, reports=None, spells=None, racials=None, races=None, has_icon=None,
                 icons=None, battlegrounds=None, facts=None, prices=None, classes=None, now=None):
        self.record, self.enemies, self.reports = record, enemies, reports
        self.battlegrounds = battlegrounds or (lambda: {})
        self.spells = spells or (lambda: {})
        self.racials = racials or (lambda: {})
        self.races = races or (lambda: [])
        self.has_icon = has_icon or (lambda name: False)
        self.icons = icons or (lambda names: {})
        self.facts = facts or (lambda: {})
        self.prices = prices or (lambda key, ids: {})
        self.classes = classes or (lambda key: None)
        self.now = now or time.time
        self.lock = threading.Lock()
        self.kept = {}
        self.book = (None, SpellBook({}))
        self.warmed = False

    def _book(self):
        data = self.spells()
        if data is not self.book[0]:
            self.book = (data, SpellBook(data))
        return self.book[1]

    def day(self, key, day, size):
        with self.lock:
            kept = self.kept.get((key, day))
        now = self.now()
        if kept and (kept[0] == size or now - kept[1] < REBUILT_EVERY):
            return kept[2]
        events = self.record.day(key, day)
        got = {"fights": fights_of(events), "seen": seen_in(events), "off": log_off(events)}
        axes = self.record.axes(events) if got["fights"] else None
        for f in got["fights"]:
            f["at"] = self._place(f, axes)
        with self.lock:
            self.kept[(key, day)] = (size, now, got)
        return got

    def _place(self, f, axes):
        s = f["spot"]
        got = self.record.world(s["m"], s["x"], s["y"]) if s and s.get("m") is not None else None
        if got:
            return [got[0], round(got[1], 1), round(got[2], 1)]
        w = next((e["w"] for e in f["events"] if e.get("ig") == f["me"] and e.get("w") and e["t"] >= f["t"]), None)
        at = self.record.placed(w, axes)
        return at[:3] if at else None

    def fights(self, key):
        fights, seen, off = [], {}, []
        for d in self.record.days(key):
            got = self.day(key, d["day"], d["bytes"])
            fights += got["fights"]
            joined(seen, got["seen"])
            off += got["off"]
        return fights, players(None, self._book(), self.racials(), seen=seen), off

    def _race(self, file, race_id, sex):
        known = [r for r in self.races() if (race_id and r["id"] == race_id) or (file and r["file"] == file)]
        if not known:
            return None
        r = known[0]
        stem = "undead" if r["file"] == "Scourge" else (r["file"] or "").lower()
        icon = f"achievement_character_{stem}_{'female' if sex == 3 else 'male'}"
        return {"name": r["shown"], "icon": icon if self.has_icon(icon) else None}

    def _who(self, guid, facts):
        if not guid:
            return None
        p, s = facts.get(guid) or {}, (self.enemies.of(guid) if self.enemies else None) or {}
        cls = s.get("cls") or (int(p["cls"]) if p.get("cls") else None)
        return {"guid": guid, "name": shown_name(p.get("name")), "cls": cls, "clsName": self._book().classes.get(str(cls)),
                "race": self._race(p.get("race"), s.get("race"), s.get("sex")), "sex": s.get("sex"),
                "guild": s.get("guild") or None, "title": s.get("title") or None, "floor": p.get("floor"),
                "levels": s.get("levels") or []}

    def row(self, f, facts, reports):
        yours = your_level(reports, f["t"])
        opp = self._who(f["opponent"], facts)
        if opp:
            opp["level"], opp["least"] = opponent_level(opp.pop("levels"), f["t"], opp["floor"])
        d = f["killed_you"] or next((x for x in f["died"] if x["side"] == THEM), None)
        kb = None
        if d and not d["strip"]:
            u = f["units"].get(d["by"]) or {}
            by = (None if not d["by"] else YOU if u.get("player") == f["me"] else "friend" if u.get("side") == YOU
                  else THEM if u.get("side") == THEM else "npc")
            who = self._who(u.get("player"), facts) if is_player(u.get("player")) else None
            kb = {"by": by, "name": shown_name(u.get("name")) if u.get("kind") == "player" else u.get("name"),
                  "cls": (who or {}).get("cls"), "clsName": (who or {}).get("clsName"), "spell": d["spell"],
                  "swing": d["swing"]}
        foes = [self._who(g, facts) for g in f["foes"]]
        bg = {"name": f["bg"], "icon": self.battlegrounds().get(f["bg"])} if f["bg"] else None
        return {"id": f["id"], "t": f["t"], "secs": f["secs"], "outcome": f["outcome"], "duel": f["duel"], "bg": bg,
                "one": f["one"], "ours": f["ours"], "theirs": f["theirs"], "attackers": f["attackers"],
                "you": {"level": yours}, "opp": opp,
                "skull": skull(yours, (opp or {}).get("level"), (opp or {}).get("least")),
                "kb": kb, "kbs": len(f["kb"]), "assists": len(f["assists"]), "honour": f["honour"], "zone": f["zone"],
                "map": f["map"], "spot": f["spot"], "struck": f["struck"], "onMob": f["on_mob"], "revenge": None,
                "old": not f["recorded"]["numbers"], "dealt": f["dealt"], "taken": f["taken"], "ttk": f["ttk"],
                "foes": [{"guid": x["guid"], "name": x["name"], "cls": x["cls"], "clsName": x["clsName"]}
                         for x in foes if x]}

    def brief(self, key):
        if not self.warmed:
            self.warmed = True
            start_thread("pvp spell facts", self.facts)
        fights, facts, off = self.fights(key)
        reports = self.reports.of(key) if self.reports else []
        rows = revenge([self.row(f, facts, reports) for f in fights])
        names = {s for r in rows for s in r["dealt"]} | {r["kb"]["spell"] for r in rows if r["kb"] and r["kb"]["spell"]}
        return {"char": key, "fights": rows, "off": off, "icons": self.icons(sorted(names))}

    def _people(self, f, facts, key):
        out, fought = {}, set(f["friends"]) | set(f["foes"])
        for g, u in f["units"].items():
            owner = u["player"] if u["player"] != g else None
            p = owner or g
            if p == f["me"]:
                cls = self.classes(key)
                who = {"cls": cls, "clsName": self._book().classes.get(str(cls))}
            else:
                who = self._who(p, facts) if is_player(p) else None
            out[g] = {"name": shown_name(u["name"]) if u["kind"] == "player" else u["name"], "side": u["side"],
                      "kind": u["kind"], "owner": owner, "cls": (who or {}).get("cls"),
                      "clsName": (who or {}).get("clsName"), "fought": g in fought}
        return out

    def opened(self, key, fid):
        fights, facts, _ = self.fights(key)
        i = next((i for i, f in enumerate(fights) if f["id"] == fid), None)
        if i is None:
            return None
        reports = self.reports.of(key) if self.reports else []
        f, row = fights[i], revenge([self.row(x, facts, reports) for x in fights])[i]
        spells = self.facts()
        got = pvpfight.opened(f, spells.get, self.racials(), set(self._book().of_name), lambda ids: self.prices(key, ids))
        p = facts.get(f["opponent"]) or {}
        seen = {"talents": p.get("talents") or [], "racials": p.get("racials") or []}
        names = {x.get(k) for x in got["lines"] for k in ("sp", "x", "broke")} | {x["ab"][0] for x in got["lines"]
                                                                                 if x.get("ab")}
        names |= {u["sp"] for n in got["numbers"].values() for u in n["used"]} | set(got["carried"])
        names |= {t["name"] for t in seen["talents"]} | set(seen["racials"])
        return {**row, **got, "me": f["me"], "at": f.get("at"), "people": self._people(f, facts, key), "seen": seen,
                "icons": self.icons(sorted(n for n in names if n))}
