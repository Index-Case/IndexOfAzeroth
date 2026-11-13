# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import camping
import gamedata
import words
from errands import bartering, vendor_price
import mapzones
from camping import RANK_LEVELS, names
from plansteps import cheapest, spot
from questitems import FISH
from wordparts import P, UNSAID

PREFIX = "prof:"
FISHING = "Fishing"
FISHES = ("learn", "train", "raise")
OFFERS = camping.GATHERING
PRIMARY_MOST = 2
TOP = 300
NEAR = 400.0
WITHIN = 8
BANDS = ((25, "orange"), (50, "yellow"), (100, "green"))
SHOWN = 2
ROUTE_MOST = 300
CONSUMABLE, BAG = 0, 1
GEAR = (2, 4)


def skin_skill(level):
    return 1 if level <= 10 else (level - 10) * 10 if level <= 20 else level * 5


def band(asks, skill):
    if asks is None or skill < asks:
        return None
    return next((colour for past, colour in BANDS if skill < asks + past), "grey")


def odds(colours, skill):
    yellow, grey = colours[0], colours[2]
    if skill < yellow:
        return 1.0
    if skill >= grey or grey <= yellow:
        return 0.0
    return (grey - skill) / (grey - yellow)


def colour_of(colours, skill):
    return next((c for c, at in zip(("orange", "yellow", "green"), colours) if skill < at), "grey")


class ProfData:

    def __init__(self, cd):
        self.cd = cd
        d = cd.data
        self.camping = {int(s) for v in (d.get("camping") or {}).values() for s in v.get("recipes") or ()}
        self.by_name = {v.get("n"): int(k) for k, v in cd.profs.items()}

    def professions(self):
        return sorted(((int(k), v.get("n") or "", v.get("kind") == "primary") for k, v in self.cd.profs.items()
                       if v.get("ranks")), key=lambda p: p[1])

    def ranks(self, line, game=None, seen=None):
        cd, by, spells = self.cd, {}, {}
        for r in sorted(cd.profs.get(str(line), {}).get("ranks") or (),
                        key=lambda r: (r["step"], r["spell"] not in cd.teachers, not (r.get("n") or "").strip(), r["spell"])):
            by.setdefault(r["step"], r)
            spells.setdefault(r["step"], []).append(r["spell"])
        out = []
        for step, r in sorted(by.items()):
            rows = [row for rows in cd.teachers.get(r["spell"], {}).values() for row in rows]
            skills = [row[0] for row in rows if row[0] < UNSAID]
            name = (r.get("n") or "").strip()
            rank = {"step": step, "name": name, "cap": r["cap"], "spell": r["spell"],
                    "skill": min(skills) if skills else (0 if step == 1 else None),
                    "level": max((row[1] for row in rows), default=0) or RANK_LEVELS.get(step, 1),
                    "cost": cd.cost(r["spell"], seen)}
            said = next((game[s] for s in spells[step] if s in (game or {})), None)
            if said:
                rank.update({k: said[k] for k in ("skill", "level", "cost") if said.get(k) is not None})
            out.append(rank)
        return out

    def learnt_at(self, spell):
        cd = self.cd
        asked = [row[0] for rows in cd.teachers.get(spell, {}).values() for row in rows if row[0] < UNSAID]
        if asked:
            return min(asked)
        said = (cd.recipe(spell).get(P) or {}).get("skill")
        if said is not None and said < UNSAID:
            return said
        needs = [cd.item(i).get("needs") for i in cd.recipe(spell).get("items") or ()]
        return min((n[1] for n in needs if n), default=None)

    def unit_price(self, item):
        return gamedata.item_unit_price(item) if self.cd.sellers(item) else None

    def useful(self, spell, level):
        made = (self.cd.recipe(spell).get("makes") or [None])[0]
        e = self.cd.item(made)
        if made is None or "cls" not in e:
            return False
        if e["cls"] == BAG:
            return True
        return e["cls"] == CONSUMABLE and (e.get("rl") or 0) <= level

    def makes(self, line):
        out = {}
        for spell in self.cd.profs.get(str(line), {}).get("recipes") or ():
            made = (self.cd.recipe(spell).get("makes") or [None])[0]
            if made is not None and spell not in self.camping:
                out.setdefault(int(made), []).append(int(spell))
        return out

    def gear(self, line):
        return any(self.cd.item(i).get("cls") in GEAR for i in self.makes(line))

    def route(self, line, skill, target, known, level, carry=None, have_prof=True, per_craft=None, cuts=()):
        cd, carry = self.cd, carry or {}
        known = set(known or ())
        options = []
        for spell in cd.profs.get(str(line), {}).get("recipes") or ():
            r = cd.recipe(spell)
            colours = r.get("colors")
            if spell in self.camping or not colours or len(colours) < 3 or not r.get("makes"):
                continue
            mine = spell in known or (have_prof and "skill" in (r.get("learnt") or ()))
            if not mine and not cd.teachers.get(spell):
                continue
            learnt = self.learnt_at(spell)
            if learnt is None and not mine:
                continue
            takes = [(int(i), int(n), self.unit_price(i)) for i, n in r.get("reagents") or ()]
            options.append({"spell": spell, "colours": colours, "learnt": learnt or 0, "how": "known" if mine else "trainer",
                            "takes": takes, "useful": self.useful(spell, level), "made": int(r["makes"][0])})
        segments, at, stuck = [], skill, None
        while at < min(target, skill + ROUTE_MOST):
            here = [(o, odds(o["colours"], at)) for o in options if (o["how"] == "known" or o["learnt"] <= at)]
            here = [(o, p) for o, p in here if p > 0]
            if not here:
                stuck = at
                break

            def rank(e):
                o, p = e
                keen = o["useful"] and colour_of(o["colours"], at) in ("orange", "yellow")
                if per_craft:
                    nowhere, first, second = per_craft(o["spell"])
                    return (not keen, nowhere, first / p, second / p, o["how"] != "known", -o["learnt"], o["spell"])
                unpriced = sum(n for _, n, price in o["takes"] if price is None)
                cost = sum(n * price for _, n, price in o["takes"] if price is not None)
                return (not keen, False, unpriced / p, cost / p, o["how"] != "known", -o["learnt"], o["spell"])
            o, p = min(here, key=rank)
            if segments and segments[-1]["spell"] == o["spell"] and at not in cuts:
                segments[-1]["to"], segments[-1]["expect"] = at + 1, segments[-1]["expect"] + 1 / p
            else:
                segments.append({"spell": o["spell"], "from": at, "to": at + 1, "expect": 1 / p, "how": o["how"],
                                 "learnt": o["learnt"], "colour": colour_of(o["colours"], at), "option": o})
            at += 1
        out = []
        for s in segments:
            o = s.pop("option")
            crafts = math.ceil(s.pop("expect") - 1e-9)
            takes = [[i, n * crafts, cd.item_name(i), price] for i, n, price in o["takes"]]
            priced = [max(0, n - carry.get(i, 0)) * price for i, n, _, price in takes if price is not None]
            station = (cd.data.get("stations") or {}).get(str(cd.recipe(o["spell"]).get("station")))
            out.append({**s, "name": cd.name(o["spell"]), "crafts": crafts, "made": o["made"], "takes": takes,
                        "cost": round(sum(priced)), "station": station})
        return {"segments": out, "stuck": stuck}

    def node_line(self, name, skill):
        layer = OFFERS.get(name)
        found = []
        for node, e in ((self.cd.data.get("nodes") or {}).get(layer) or {}).items():
            asks = e.get("skill", (e.get(P) or {}).get("skill"))
            colour = band(asks, skill)
            if colour and colour != "grey":
                found.append((("orange", "yellow", "green").index(colour), -asks, node, colour))
        return [(node, colour) for _, _, node, colour in sorted(found)]

    def beasts(self, skill):
        top = max((lv for lv in range(1, 64) if skin_skill(lv) <= skill), default=None)
        if top is None:
            return None
        sure = min((lv for lv in range(1, top + 1) if band(skin_skill(lv), skill) == "orange"), default=top)
        return top, sure

    def waters(self, skill, zone_map, at=None):
        here = mapzones.zone_holding(*at[:3]) if at else None
        found = []
        for area, asks in (self.cd.data.get("fishing") or {}).items():
            m = zone_map(int(area)) if asks <= skill else None
            name = (mapzones.MAPS.get(str(m)) or {}).get("name") if m else None
            if name:
                far = mapzones.zone_yards(m, *at[:3]) if at else math.inf
                found.append((str(m) != str(here), far, -asks, name))
        return list(dict.fromkeys(f[-1] for f in sorted(found)))


def short_list(words):
    words = list(words)
    if len(words) <= SHOWN + 1:
        return names(words) if words else ""
    return f"{', '.join(words[:SHOWN])} and {len(words) - SHOWN} more"


def station_words(name):
    low = name[:1].lower() + name[1:]
    return f"{'an' if low[:1] in 'aeiou' else 'a'} {low}"


def rank_words(rank, prof):
    return f"{rank['name']} {prof}".strip()


def asks_words(rank):
    parts = [f"skill {rank['skill']}" if rank.get("skill") else "", f"level {rank['level']}" if rank.get("level", 1) > 1 else ""]
    return " and ".join(p for p in parts if p)


def level_wait(rank, prof, learn):
    said = {"level": rank["level"], "rank": rank["name"], "skill": prof}
    why = words.say("both.prof-wait.learn", said) if learn else words.say("both.prof-wait.train", said)
    return {"state": "sleep", "min": rank["level"], "rank": rank, "why": why,
            "text": words.say("both.step-why.waiting", {"why": why}), "brief": words.say("both.prof-wait.brief", said)}


def room_for(pd, line, me):
    cd = pd.cd
    have = me.get("profs") or {}
    if cd.names.get(line, "") in have or (cd.profs.get(str(line)) or {}).get("kind") != "primary":
        return True
    return sum(1 for n in have if (cd.profs.get(str(pd.by_name.get(n))) or {}).get("kind") == "primary") < PRIMARY_MOST


def status(pd, line, me):
    cd = pd.cd
    name = cd.names.get(line, "")
    kind = (cd.profs.get(str(line)) or {}).get("kind")
    have = (me.get("profs") or {}).get(name)
    level = me.get("level") or 1
    rs = pd.ranks(line, (me.get("game_ranks") or {}).get(name), me.get("prices"))
    out = {"line": line, "name": name, "primary": kind == "primary", "gathering": name in OFFERS,
           "skill": have["rank"] if have else None, "cap": have["max"] if have else None, "min": None, "rank": None,
           "walls": [{k: r[k] for k in ("name", "cap", "skill", "level", "cost")} for r in rs], "offer": None, "route": None,
           "points": None, "target": target_of(have and have["rank"], have and have["max"], rs)}
    if not have:
        first = rs[0] if rs else None
        if not room_for(pd, line, me):
            return {**out, "state": "full", "text": f"You already have two primary professions. Unlearn one of them in the game to take up {name}"}
        if first and first["level"] > level:
            return {**out, **level_wait(first, name, True)}
        return {**out, "state": "learn", "rank": first, "text": f"Learn {name} at a trainer"}
    skill, cap = have["rank"] or 0, have["max"] or 0
    nxt = next((r for r in rs if r["cap"] > cap), None)
    out["points"] = max(0, cap - skill)
    if nxt and nxt["skill"] is not None and skill >= nxt["skill"]:
        if level >= nxt["level"]:
            asks = asks_words(nxt)
            return {**out, "state": "train", "rank": nxt,
                    "text": f"Train {rank_words(nxt, name)} at a trainer{f', which asks for {asks}' if asks else ''}"}
        if skill >= cap:
            return {**out, **level_wait(nxt, name, False)}
    if skill >= cap:
        if not nxt:
            return {**out, "state": "done", "text": f"Your {name} is at {skill}, the top of its last rank"}
        return {**out, "state": "sleep", "rank": nxt,
                "text": f"You are at the cap, and no source says yet what skill {rank_words(nxt, name)} asks for"}
    to = f"You have {out['points']} point{'s' if out['points'] != 1 else ''} to go to the cap"
    if name in OFFERS:
        offer = None if name == FISHING and lacks_pole(pd, me) else OFFERS[name]
        return {**out, "state": "raise", "offer": offer, "text": gather_text(pd, name, skill, me, to)}
    route = pd.route(line, skill, cap, me.get("known", {}).get(name) or (), level, me.get("items"))
    out["route"] = route
    if not route["segments"]:
        return {**out, "state": "raise", "text": f"No recipe of yours gives {name} points at {skill}, but a trainer may teach you a recipe that does"}
    first = route["segments"][0]
    learn = " (learn the recipe at a trainer)" if first["how"] == "trainer" else ""
    carry = me.get("items")
    short = [] if carry is None else [f"{n} {item} (you carry {carry.get(i, 0)})" for i, n, item, price in first["takes"]
                                      if price is None and carry.get(i, 0) < n]
    get = f". You need {names(short)}" if short else ""
    return {**out, "state": "raise",
            "text": f"Craft about {first['crafts']} {first['name']}{learn}, which is {first['colour']} for you, to reach {first['to']} {name}{get}"}


def target_of(skill, cap, rs):
    if skill is None:
        return rs[0]["cap"] if rs else None
    if skill < (cap or 0):
        return cap
    return next((r["cap"] for r in rs if r["cap"] > (cap or 0)), cap)


def epic_key(line, to=None, way=None):
    return f"{PREFIX}{line}" + (f":{to}:{way}" if to is not None and way else "")


def epic_of(key):
    parts = key[len(PREFIX):].split(":") if key.startswith(PREFIX) else []
    if len(parts) == 1 and parts[0].isdigit():
        return int(parts[0]), None, None
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2]:
        return int(parts[0]), int(parts[1]), parts[2]
    return None


def gather_text(pd, name, skill, me, to):
    if name in ("Mining", "Herbalism"):
        found = pd.node_line(name, skill)
        verb = "Mine" if name == "Mining" else "Gather"
        if not found:
            return f"No {name} node in our data gives points at {skill}. {to}"
        return f"{verb} {short_list(n for n, _ in found)}. {to}"
    if name == "Skinning":
        reach = pd.beasts(skill)
        if not reach:
            return f"Skin beasts. {to}"
        top, sure = reach
        each = ("Each one gives a point" if sure <= 1 else f"Beasts of level {sure} and up give a point each" if sure < top
                else f"Beasts of level {top} give a point each")
        return f"Skin beasts up to level {top}. {each}. {to}"
    waters = pd.waters(skill, me.get("zone_map") or (lambda a: None), me.get("at"))
    return f"Fish in {short_list(waters)}. {to}" if waters else f"Fish wherever your skill reaches. {to}"


def state_of(record, level, side, game_ranks=None, items=None, zone_map=None, at=None, money=None, prices=None):
    record = record or {}
    profs = None if record.get("professions") is None else \
        {p["name"]: {"rank": p.get("rank") or 0, "max": p.get("max") or 0} for p in record["professions"] if p.get("name")}
    known = {n: {int(s) for s in (b.get("known") or {})} for n, b in (record.get("recipes") or {}).items()}
    return {"level": level or 1, "side": side or "", "profs": profs, "known": known, "game_ranks": game_ranks or {},
            "items": items, "zone_map": zone_map, "at": at, "money": money, "prices": prices or {},
            "refused": camping.refusals(record), "bartering": bartering(record)}


def game_ranks(record, trainer_prices):
    out = {}
    seen = (trainer_prices or {}).get("professions") or {}
    for prof, t in ((record or {}).get("profTrainers") or {}).items():
        services = (seen.get(str(t.get("npc"))) or {}).get("services") or t.get("ranks") or ()
        for s in services:
            if s.get("rank") and s.get("spell"):
                out.setdefault(prof, {})[int(s["spell"])] = {"skill": s.get("skill"), "level": s.get("level"), "cost": s.get("cost")}
    return out


def on(record):
    return dict((record or {}).get("profEpics") or {})




def taught(name, skill):
    return {"taught": [name, int(skill)]} if skill is not None and 1 < skill < UNSAID else {}


class Chores:

    def __init__(self, pd, me, errands, anchor, own=False, notes=None):
        self.pd, self.cd, self.me, self.errands, self.anchor, self.own = pd, pd.cd, me, errands, anchor, own
        self.side = me.get("side") or ""
        self.notes = [] if notes is None else notes

    def trainers(self, name, spell):
        return camping.trainers(self.cd, self.errands, self.side, name, spell, self.me.get("refused"))

    def fit(self, steps, lo, places, make, ok=None):
        if not places:
            return None
        if self.own:
            return self.errands.fit(steps, lo, len(steps), places, self.anchor, make, ok=ok)
        hi = min(len(steps), lo + WITHIN)
        window = [self.anchor] + [spot(s) for s in steps[max(0, lo - 1):hi + 1]]
        near = self.errands.near_route(places, window)
        best = cheapest(steps, [p[1] for p in near], lo, hi, self.anchor, ok=ok and (lambda i, k: ok(i, near[k])))
        if best is None or best[0] > NEAR:
            return None
        steps.insert(best[1], make(*near[best[2]]))
        return best[1]

    def paid(self, steps, lo, places, make, cost, hi=None):
        fit = None if hi is not None else (lambda st, lo_, hi_, pl, anchor, mk, ok=None: self.fit(st, lo_, pl, mk, ok))
        return self.errands.fit_paid(steps, lo, len(steps) if hi is None else hi, places, self.anchor, make, cost,
                                     self.me.get("money"), fit=fit)

    def chore(self, what, key, text, name, place, need, cost=None, least=None, takes=None):
        step = self.errands.step(what, key, text, name, place, need, cost)
        return {**step, **({"min": least} if least and least > 1 else {}), **({"takes": takes} if takes else {})}

    def here(self, steps, i, what, key, text, need, objective=None, takes=None):
        prev = next((s for s in reversed(steps[:i]) if spot(s)), None)
        if prev:
            p = (prev["inst"], prev["at"][0], prev["at"][1], prev["at"][2] if len(prev["at"]) > 2 else None, prev.get("map"))
        elif self.anchor:
            p = (self.anchor[0], self.anchor[1], self.anchor[2], None, None)
        else:
            return None
        steps.insert(i, {**self.errands.step(what, key, text, "", p, need), "npc": "", **({"objective": objective} if objective else {}),
                         **({"takes": takes} if takes else {})})
        return i

    def plan(self, steps, statuses):
        steps, where = list(steps), {}
        for st in statuses:
            where[st["line"]] = self.one(steps, st)
        return steps, where

    def one(self, steps, st):
        name, line = st["name"], st["line"]
        if st["state"] in ("learn", "train") and st.get("rank"):
            at, why = self.learn(steps, st, st["state"] == "learn")
            return "planned" if at is not None else why
        if st.get("why") and not self.own:
            self.notes.append({"what": "learn", "text": st["why"], "brief": st["brief"]})
            return None
        if st["state"] != "raise" or not st.get("route") or not st["route"]["segments"]:
            return None
        seg = st["route"]["segments"][0]
        lo = 0
        if seg["how"] == "trainer":
            at, why = self.recipe(steps, 0, name, seg["spell"], f"{PREFIX}{line}:recipe:{seg['spell']}", seg["name"])
            if at is None:
                return why
            lo = at + 1
        carry = self.me.get("items") or {}
        buys = {i: n for i, n, _, price in seg["takes"] if price is not None and n > carry.get(i, 0)}
        if buys:
            at, why = self.buy(steps, lo, f"{PREFIX}{line}:buy:{seg['spell']}", buys)
            if at is None:
                return why
            lo = at + 1
        one = {i: n // max(1, seg["crafts"]) for i, n, _, price in seg["takes"] if price is None}
        if self.me.get("items") is None or any(carry.get(i, 0) < max(1, n) for i, n in one.items()):
            return "planned" if lo else None
        at_station = f" at {station_words(seg['station'])}" if seg.get("station") else ""
        item = self.cd.item_name(seg["made"])
        self.here(steps, lo, "craft", f"{PREFIX}{line}:craft:{seg['spell']}",
                  f"Craft about {seg['crafts']} {item}{at_station}, which is {seg['colour']} for you, to reach {seg['to']} {name}",
                  {"skills": [[name, seg["to"]]]},
                  takes={"items": [i for i, *_ in seg["takes"]], "recipes": [seg["spell"]], "skills": [name]})
        return "planned"

    def learn(self, steps, st, first, hi=None, lo=0):
        name, line, rank = st["name"], st["line"], st["rank"]
        need = {"skills": [[name, 1]]} if first else {"caps": [[name, rank["cap"]]], **taught(name, rank.get("skill"))}
        key = f"{PREFIX}{line}:learn" if first else f"{PREFIX}{line}:rank{rank['step']}"
        said = name if first else rank_words(rank, name)

        def words_at(n):
            return f"Learn {name} at {n}" if first else f"Train {said} at {n}"

        def make(n, p, _, npc):
            return camping.at_trainer(self.chore("learn", key, words_at(n), n, p, need, rank.get("cost"), rank.get("level"),
                                                 takes=None if first else {"skills": [name]}),
                                      npc, picked, words_at)
        picked = self.trainers(name, rank["spell"])
        return self.paid(steps, lo, picked, make, rank.get("cost"), hi=hi)

    def recipe(self, steps, lo, name, spell, key, label):
        cost = self.cd.cost(spell, self.me.get("prices"))
        picked = self.trainers(name, spell)
        need = {"recipes": [spell], **taught(name, self.pd.learnt_at(spell))}
        return self.paid(steps, lo, picked,
                         lambda n, p, _, npc: camping.at_trainer(
                             self.chore("learn", key, f"Learn {label} at {n}", n, p, need, cost,
                                        takes={"skills": [name]}),
                             npc, picked, lambda o: f"Learn {label} at {o}"),
                         cost)

    def buy(self, steps, lo, key, buys, held=None):
        cd, carry = self.cd, (self.me.get("items") or {}) if held is None else held
        buys = {i: n for i, n in buys.items() if n > carry.get(i, 0)}
        sold, at = {i: cd.sellers(i) for i in buys}, None
        cost_of = lambda items: sum((vendor_price(self.pd.unit_price(i), self.me) or 0) * (buys[i] - carry.get(i, 0))
                                    for i in items)
        while buys:
            at = None
            for rows in self.errands.vendors_of(sorted(buys), self.side, sold, {i: cd.stocked(i) for i in buys}):
                sells = {p[3]: items for p, items in rows}

                def make(n, p, prices, npc, sells=sells):
                    items = sells[npc]
                    left = [(cd.item_name(i), buys[i] - carry.get(i, 0)) for i in sorted(items)]
                    return self.chore("supplies", key, camping.buy_line(left, n), n, p,
                                      cd.buy_need(npc, [[i, buys[i]] for i in sorted(items)]), cost_of(items))
                at, _ = self.paid(steps, lo, [p for p, _ in rows], make, lambda i, p, sells=sells: cost_of(sells[p[3]]))
                if at is not None:
                    break
            if at is None:
                return None, "far"
            got = {int(e[0]) for e in steps[at]["need"]["items"]}
            buys, lo = {i: n for i, n in buys.items() if i not in got}, at + 1
        return at, None


def ride_along(steps, pd, me, errands, anchor, statuses, notes=None):
    return Chores(pd, me, errands, anchor, notes=notes).plan(steps, statuses)


def own_plan(steps, pd, me, errands, anchor, st):
    chores = Chores(pd, me, errands, anchor, own=True)
    steps, where = chores.plan(steps, [st])
    if not any(s.get("kind") == "errand" and (s.get("key") or "").startswith(f"{PREFIX}{st['line']}:") for s in steps):
        need = ({"level": st["min"]} if st.get("min") else {"skills": [[st["name"], st["cap"]]]} if st.get("cap") else {})
        fishes = st["name"] == FISHING and st["state"] == "raise"
        chores.here(steps, len(steps), "wall", f"wall:{PREFIX}{st['line']}", st["text"], need, FISH if fishes else None)
    return steps, where


def lacks_pole(pd, me):
    carry, poles = me.get("items"), pd.cd.poles
    return carry is not None and bool(poles) and not any(carry.get(p) for p in poles)


def fish_gear(steps, pd, me, errands, anchor, fishing=None, own=False):
    steps = list(steps)
    k = next((k for k, s in enumerate(steps) if s.get("objective") == FISH), None)
    line = pd.by_name.get(FISHING)
    if line is None or (k is None and (fishing or {}).get("state") not in FISHES):
        return steps
    chores = Chores(pd, me, errands, anchor, own=own)
    had = next((j for j, s in enumerate(steps) if s.get("key") == f"{PREFIX}{line}:learn"), None)
    if k is not None and me.get("profs") is not None and FISHING not in me["profs"]:
        st = status(pd, line, me)
        if had is not None and had > k:
            steps.pop(had)
            had = None
        if had is None and st.get("rank"):
            had, _ = chores.learn(steps, st, True, hi=k)
            k += had is not None
    lo = 0 if had is None else had + 1
    if not lacks_pole(pd, me):
        return steps
    poles = pd.cd.poles
    sold = {p: pd.cd.sellers(p) for p in poles}
    rows = [r for group in errands.vendors_of(sorted(poles), me.get("side") or "", sold,
                                              {i: pd.cd.stocked(i) for i in poles}) for r in group]
    places, sells = [p for p, _ in rows], {p[3]: items for p, items in rows}
    price = lambda i: vendor_price(pd.unit_price(i), me) or 0
    pole_of = lambda npc: min(sells[npc], key=lambda i: (price(i), i))

    def make(n, p, prices, npc):
        pole = pole_of(npc)
        return chores.chore("supplies", f"{PREFIX}{line}:pole", camping.buy_line([(pd.cd.item_name(pole), 1)], n), n, p,
                            pd.cd.buy_need(npc, [[pole, 1]]), price(pole))
    if places:
        chores.paid(steps, lo, places, make, lambda i, p: price(pole_of(p[3])), hi=k)
    return steps


def panel(pd, me, record):
    epics = on(record)
    rows, mine = [], []
    for line, name, primary in pd.professions():
        st = status(pd, line, me)
        e = epics.get(name)
        rows.append({"line": line, "name": name, "primary": primary, "skill": st["skill"], "cap": st["cap"], "on": e is not None,
                     "hidden": bool(e and e.get("hidden")), "can": st["state"] != "full",
                     "why": st["text"] if st["state"] == "full" else None})
        if e is not None:
            mine.append({**st, "hidden": bool(e.get("hidden")), "at": e.get("at")})
    have = set((me.get("profs") or {}))
    rows.sort(key=lambda r: (r["name"] not in have, r["name"]))
    return {"list": rows, "epics": mine}
