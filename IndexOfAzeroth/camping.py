# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re
from collections import Counter

from errands import money_note
from plansteps import gap, spot
import planunits
from questplan import open_to
import store
import ticks
from wordparts import A, ALL, P

KEY = "camp:epic"
NAME = "Camping epic"
CAMPING_SORT = -666
CAMP_AURA = "Camp Benefits"
KITS = 2
SKIP_FOR = 60
SOON = 2
CAMP_NEAR = 500.0
GATHERING = {"Mining": "mining", "Herbalism": "herbalism", "Fishing": "fishing", "Skinning": "skinning"}
COLOURS = ("orange", "yellow", "green", "grey")
SKILL_UP = {"orange": "every craft gives a point of {prof}", "yellow": "most crafts give a point of {prof}",
            "green": "some crafts give a point of {prof}", "grey": "no craft gives a point of {prof} any more"}
OTHER_SIDE = {"Alliance": "Horde", "Horde": "Alliance"}
RANK_LEVELS = {2: 10, 3: 20, 4: 35}


def category(name):
    return "".join(name.lower().split())


def counted(n, name):
    return f"{n} {name}" if n != 1 else f"a {name}"


def names(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


class CampData:

    def __init__(self, data):
        d = self.data = data or {}
        self.recipes, self.items, self.profs = d.get("recipes") or {}, d.get("items") or {}, d.get("professions") or {}
        self.names = {int(k): v.get("n") or "" for k, v in self.profs.items()}
        parts = ticks.camp_parts(d)
        self.made = parts["made"]
        self.fires = sorted(parts["fires"], key=self.place_rank)
        self.cooking = self.recipe(self.fires[0]).get("prof") if self.fires else None
        self.features = {}
        for s in sorted(set(self.made) - set(self.fires), key=lambda s: (self.place_rank(s), s)):
            self.features.setdefault(self.recipe(s).get("prof"), []).append(s)
        self.feature_items = {i for s, i in self.made.items() if s not in self.fires}
        self.blueprint = {e["teaches"]: int(i) for i, e in self.items.items() if e.get("teaches") in self.made}
        self.poles = [int(i) for i in d.get("poles") or ()]
        auras = d.get("auras") or {}
        self.aura = next((int(a) for a, e in auras.items() if e.get("n") == CAMP_AURA), None)
        said = Counter(int(m) for i in self.feature_items
                       for m in re.findall(r"share a cooldown of \$(\d+)d", self.item(i).get("use", {}).get("does") or ""))
        self.cool_aura = said.most_common(1)[0][0] if said else None
        self.teachers = {}
        self.by_name = {}
        for npc, t in (d.get("trainers") or {}).items():
            self.by_name.setdefault(t.get("n"), []).append((int(npc), t.get("prof")))
            for part in (A, P):
                for s, row in ((t.get(part) or {}).get("teaches") or {}).items():
                    self.teachers.setdefault(int(s), {}).setdefault(int(npc), []).append(row)

    def recipe(self, spell):
        return self.recipes.get(str(spell)) or {}

    def item(self, item):
        return self.items.get(str(item)) or {}

    def item_name(self, item):
        return self.item(item).get("n") or f"item {item}"

    def name(self, spell):
        return self.recipe(spell).get("n") or f"recipe {spell}"

    def prof(self, spell):
        return self.recipe(spell).get("prof")

    def place_rank(self, spell):
        needs = self.item(self.made.get(spell)).get("needs")
        return needs[1] if needs else (self.recipe(spell).get("colors") or [0])[0]

    def learn_rank(self, spell):
        needs = self.item(self.blueprint.get(spell)).get("needs")
        if needs:
            return needs[1]
        asked = [row[0] for rows in self.teachers.get(spell, {}).values() for row in rows if row[0] < 9999]
        return min(asked) if asked else self.place_rank(spell)

    def with_skill(self, spell):
        return "skill" in (self.recipe(spell).get("learnt") or ())

    def tools(self, spell):
        return {int(t) for t in self.recipe(spell).get("totems") or ()}

    def takes(self, spell):
        r = self.recipe(spell)
        return [[int(i), int(n)] for i, n in r.get("reagents") or ()] + [[t, 1] for t in sorted(self.tools(spell))]

    def sellers(self, item):
        e = self.item(item)
        out = {int(n) for part in ALL for n in (e.get(part) or {}).get("sold") or ()}
        return out | {int(n) for n, v in (self.data.get("vendors") or {}).items()
                      if str(item) in ((v.get(P) or {}).get("sells") or {})}

    def droppers(self, item):
        e, out = self.item(item), {}
        for part in (P, "loot"):
            for npc, chance in (e.get(part) or {}).get("drops") or ():
                out.setdefault(int(npc), chance or 0)
        return sorted(out.items(), key=lambda kv: -kv[1])

    def gathered_by(self, item):
        e = self.item(item).get("loot") or {}
        if e.get("skinned"):
            return "Skinning"
        if e.get("fished"):
            return "Fishing"
        nodes = self.data.get("nodes") or {}
        return next((prof for layer, prof in (("mining", "Mining"), ("herbalism", "Herbalism"))
                     if set(e.get("gathered") or ()) & set(nodes.get(layer) or ())), None)

    def rank_for(self, prof, skill):
        for r in sorted(self.profs.get(str(prof), {}).get("ranks") or (), key=lambda r: r["step"]):
            if r["cap"] >= skill:
                rows = [row for rows in self.teachers.get(r["spell"], {}).values() for row in rows]
                level = max((row[1] for row in rows), default=0) or RANK_LEVELS.get(r["step"], 0)
                return {"name": r["n"].strip(), "level": level,
                        "cost": min((row[2] for row in rows), default=None), "cap": r["cap"]}
        return None

    def for_side(self, spell, side):
        words = self.item(self.made.get(spell)).get("use", {}).get("does") or ""
        other = OTHER_SIDE.get(side)
        return not (other and re.search(rf"\b{other}\b", words))

    def colour(self, spell, skill, game=None):
        cols = self.recipe(spell).get("colors")
        if cols:
            return next((COLOURS[k] for k, at in enumerate(cols) if skill < at), COLOURS[-1])
        return game if game in COLOURS else None




def area(book, side, race, class_id, done, log, anchor, to_world):
    found = []
    for zid, z in sorted(book.zones.items()):
        mine = [i for i in z["quests"] if (book.quests.get(i) or {}).get("zone") == CAMPING_SORT
                and not open_to(book.quests[i], side, race, class_id, in_log=i in log)]
        givers = Counter((g["name"], g["map"], g["x"], g["y"]) for i in mine for g in book.quests[i].get("start") or ()
                         if g.get("map") is not None)
        at = givers and to_world(*givers.most_common(1)[0][0][1:])
        if at:
            ends = sorted({(g["name"], g["map"], g["x"], g["y"], g.get("z")) for i in mine
                           for g in book.quests[i].get("end") or () if g.get("map") is not None}, key=str)
            found.append({"zone": zid, "quests": mine, "camper": givers.most_common(1)[0][0][0], "at": tuple(at),
                          "enders": [[n, *to_world(m, x, y), h, m] for n, m, x, y, h in ends],
                          "begun": any(i in done or i in log for i in mine)})
    best = min([a for a in found if a["begun"]] or found, key=lambda a: gap(anchor, a["at"]), default=None)
    return best and {k: v for k, v in best.items() if k != "begun"}




class Chores:

    def __init__(self, cd, me, errands, anchor):
        self.cd, self.me, self.errands, self.anchor = cd, me, errands, anchor
        self.side = me.get("side") or ""
        self.skills, self.caps = dict(me.get("skills") or {}), dict(me.get("caps") or {})
        self.learnt = set()
        self.tools = set()
        self.later = []
        self.notes = []
        self.area = None


    def count(self, item):
        return (self.me.get("items") or {}).get(item, 0)

    def rank(self, prof):
        return self.skills.get(prof, 0)

    def knows(self, spell):
        return (spell in self.learnt or (self.me.get("known") or {}).get(spell) is True
                or (self.cd.with_skill(spell) and self.cd.prof(spell) in self.skills))


    def skill_wall(self, prof, need):
        cd, name, cap = self.cd, self.cd.names.get(prof, "?"), self.caps.get(prof)
        rank = cd.rank_for(prof, cap + 1) if cap is not None and cap < need else None
        if rank and rank["level"] > (self.me.get("level") or 1):
            return {"kind": "level", "text": f"Reach level {rank['level']} for {rank['name']} {name}", "offer": "level",
                    "min": rank["level"]}
        train = f"Learn {rank['name']} {name} at a trainer, then raise" if rank else "Raise"
        return {"kind": "skill", "text": f"{train} {name} to {need} (you have {self.rank(prof)})",
                "offer": GATHERING.get(name), "prof": name, "need": {"skills": [[name, need]]}}

    def blueprint_wall(self, spell):
        b = self.cd.blueprint[spell]
        drops = self.cd.droppers(b)
        if not drops:
            return {"kind": "source", "text": f"No source says yet where {self.cd.item_name(b)} comes from, and the Index asks again every day"}
        npc, chance = drops[0]
        who = (self.me.get("npc") or (lambda n: None))(npc)
        odds = f" {chance:g}% of the time" if chance else ""
        return {"kind": "source", "need": {"items": [[b, 1]]},
                "text": f"Find {self.cd.item_name(b)}, which {who[0]} (level {who[1]}) drops{odds}" if who
                else f"Find {self.cd.item_name(b)}, which NPC {npc} drops{odds}"}

    def reagent_wall(self, item, n):
        cd, prof = self.cd, self.cd.gathered_by(item)
        maker = next((cd.names.get(cd.prof(s)) for s in cd.item(item).get("made") or () if cd.prof(s)), None)
        how = f" with {prof}" if prof else f" from {maker}" if maker else ""
        return {"kind": "reagent", "offer": GATHERING.get(prof), **({"prof": prof} if prof else {}), "need": {"items": [[item, n]]},
                "text": f"Get {counted(n, cd.item_name(item))}{how} (you carry {self.count(item)})"}

    def wall(self, what, walls):
        w = walls[0]
        same = next((e for e in self.later if e["wall"]["text"] == w["text"]), None)
        if same:
            same["what"].append(what)
            same["text"] = f"{names(same['what'])}: {w['text']}"
            return
        self.later.append({"text": f"{what}: {w['text']}", "what": [what], "wall": w})


    def making(self, spell, count):
        cd, prof = self.cd, self.cd.prof(spell)
        walls, todo = [], []
        if not self.knows(spell):
            need = cd.learn_rank(spell)
            if self.rank(prof) < need:
                walls.append(self.skill_wall(prof, need))
            elif spell in cd.blueprint and self.count(cd.blueprint[spell]) < 1:
                walls.append(self.blueprint_wall(spell))
            else:
                todo.append(("learn", spell, "blueprint" if spell in cd.blueprint else "trainer"))
        if not walls and self.rank(prof) < cd.place_rank(spell):
            walls.append(self.skill_wall(prof, cd.place_rank(spell)))
        short = max(0, count - self.count(cd.made[spell]))
        for item, n in cd.takes(spell) if short else ():
            want = n if item in cd.tools(spell) else n * short
            if cd.sellers(item):
                todo.append(("buy", item, want))
            elif self.count(item) < want:
                walls.append(self.reagent_wall(item, want))
        return todo + ([("craft", spell, count)] if short else []), walls


    def place_here(self, steps, i):
        prev = next((s for s in reversed(steps[:i]) if spot(s)), None)
        if prev:
            return (prev["inst"], prev["at"][0], prev["at"][1], prev["at"][2] if len(prev["at"]) > 2 else None, prev.get("map"))
        a = self.anchor
        return (a[0], a[1], a[2], None, None) if a else None

    def here(self, steps, i, what, key, text, need, place=None, takes=None):
        p = place or self.place_here(steps, i)
        if not p:
            return None
        steps.insert(i, {**self.errands.step(what, key, text, "", p, need), "npc": "", **({"takes": takes} if takes else {})})
        return i

    def trainers(self, prof, spell=None):
        found = list(self.errands.places({category(self.cd.names.get(prof, ""))}, self.side, ids=True))
        listed = {p[3] for p in found}
        for name, inst, north, west, height, map_ in (self.area or {}).get("enders") or ():
            for npc, theirs in self.cd.by_name.get(name, ()):
                if theirs == prof and npc not in listed:
                    found.append((name, (inst, north, west, height, map_), {}, npc))
                    listed.add(npc)
        teach = self.cd.teachers.get(spell, {})
        return [p for p in found if p[3] in teach] or found

    def vendors(self, items):
        return self.errands.vendors_of(items, self.side, {i: self.cd.sellers(i) for i in items})

    def paid(self, steps, lo, places, make, cost, what, doing, brief):
        at, why = self.errands.fit_paid(steps, lo, len(steps), places, self.anchor, make, cost, self.me.get("money"))
        self.note(why, what, doing, cost, brief)
        return at, why

    def note(self, why, what, doing, cost, brief):
        if why in ("short", "unknown"):
            self.notes.append(money_note(what, why, doing, cost, self.me.get("money"), brief))

    def after(self, steps, places, lo):
        at = {p[0] for p in places}
        return max([k + 1 for k, s in enumerate(steps) if s["kind"] == "turnin" and s.get("npc") in at] + [lo])

    def do(self, steps, lo, todo):
        cd = self.cd
        for _, spell, how in [t for t in todo if t[0] == "learn"]:
            need, why = {"recipes": [spell]}, "far"
            takes = {"skills": [cd.names.get(cd.prof(spell))]}
            if how == "blueprint":
                at = self.here(steps, lo, "learn", f"learn:{spell}",
                               f"Learn {cd.name(spell)} by using {cd.item_name(cd.blueprint[spell])} from your bags", need,
                               takes={**takes, "items": [cd.blueprint[spell]]})
            else:
                cost = min((row[2] for rows in cd.teachers.get(spell, {}).values() for row in rows), default=None)
                at, why = self.paid(steps, lo, self.trainers(cd.prof(spell), spell),
                                    lambda n, p, *_: {**self.errands.step("learn", f"learn:{spell}", f"Learn {cd.name(spell)} at {n}",
                                                                          n, p, need, cost), "takes": takes},
                                    cost, "learn", f"Learning {cd.name(spell)}", cd.name(spell))
            if at is None:
                return None, why
            self.learnt.add(spell)
            lo = at + 1
        wants = {}
        for kind, item, n in todo:
            if kind == "buy":
                tool = any(item in cd.tools(s) for k, s, _ in todo if k == "craft")
                if tool and item in self.tools:
                    continue
                wants[item] = max(wants.get(item, 0), n) if tool else wants.get(item, 0) + n
        buys = {i: n for i, n in wants.items() if n > self.count(i)}
        price_of = lambda items: sum((cd.item(i).get("price") or 0) * (buys[i] - self.count(i)) for i in items)
        words_of = lambda items: names([counted(buys[i] - self.count(i), cd.item_name(i)) for i in items])
        while buys:
            bought, at, whys = [], None, []
            for rows in self.vendors(sorted(buys)):
                sells = {place[3]: items for place, items in rows}

                def make(n, p, prices, npc, sells=sells):
                    items = sells[npc]
                    bought.extend(items)
                    return self.errands.step("supplies", "supplies", f"Buy {words_of(items)} at {n}", n, p,
                                             {"items": [[i, buys[i]] for i in items]}, price_of(items))
                at, why = self.errands.fit_paid(steps, lo, len(steps), [place for place, _ in rows], self.anchor, make,
                                                lambda i, p, sells=sells: price_of(sells[p[3]]), self.me.get("money"))
                if at is not None:
                    break
                whys.append(why)
            if at is None:
                why = next((w for w in whys if w != "far"), "far")
                self.note(why, "supplies", f"Buying {words_of(sorted(buys))}", price_of(buys),
                          names([cd.item_name(i) for i in sorted(buys)]))
                return None, why
            buys = {i: n for i, n in buys.items() if i not in bought}
            self.tools |= {i for i in bought if any(i in cd.tools(s) for k, s, _ in todo if k == "craft")}
            lo = at + 1
        for _, spell, count in [t for t in todo if t[0] == "craft"]:
            item, prof = cd.made[spell], cd.prof(spell)
            colour = cd.colour(spell, self.rank(prof), (self.me.get("colours") or {}).get(spell))
            up = f" ({colour} for you, so {SKILL_UP[colour].format(prof=cd.names.get(prof))})" if colour else ""
            n = count - self.count(item)
            what = counted(n, cd.item_name(item)) + ("s" if n > 1 else "")
            at = self.here(steps, lo, "craft", f"craft:{item}", f"Craft {what}{up}", {"items": [[item, count]]},
                           takes={"items": [i for i, _ in cd.takes(spell)], "recipes": [spell],
                                  "skills": [cd.names.get(prof)]})
            if at is None:
                return None, "far"
            lo = at + 1
        return lo, None

    def due(self, sure=False):
        cd, me, now = self.cd, self.me, self.me.get("now") or 0
        if me.get("skipped") is not None and me["skipped"] < SKIP_FOR:
            return False
        auras = me.get("auras") or {}
        on = lambda a: a in auras and auras[a] is not False and (auras[a] is None or auras[a] > now)
        if cd.aura is None or on(cd.aura) or on(cd.cool_aura):
            return False
        if any(i in cd.feature_items and (e is None or e > now) for i, e in (me.get("cooldowns") or {}).items()):
            return False
        return not sure or cd.aura in auras

    def features(self):
        cd = self.cd
        out = [s for prof, spells in cd.features.items() if prof in self.skills for s in spells
               if self.knows(s) and cd.place_rank(s) <= self.rank(prof) and cd.for_side(s, self.side)]
        return sorted(out, key=lambda s: (self.count(cd.made[s]) < 1, cd.place_rank(s), s))

    def first_camp(self, steps, lo, camper):
        cd = self.cd
        fires = [s for s in cd.fires if self.knows(s) and cd.place_rank(s) <= self.rank(cd.cooking)]
        if not fires or self.me.get("camped") or not self.due():
            return lo
        fire = fires[-1]
        todo, walls = self.making(fire, KITS)
        if walls:
            self.wall(cd.name(fire), walls)
            return lo
        feature, ready = None, self.features()
        for s in ready:
            more, held = self.making(s, 1)
            if not held:
                feature, todo = s, todo + more
                break
        if ready and not feature:
            self.wall(cd.name(ready[0]), self.making(ready[0], 1)[1])
        at, _ = self.do(steps, lo, todo)
        if at is None:
            return lo
        objects =[cd.item_name(cd.made[s]) for s in (fire, feature) if s]
        p = self.place_here(steps, at)
        if camper and p and gap(p[:3], camper) <= CAMP_NEAR:
            p = (*camper, None, p[4])
        made = self.here(steps, at, "camp", "camp", f"Make camp: place your {names(objects)}, then sit a minute for {CAMP_AURA}",
                         {"auras": [cd.aura]}, p, takes={"items": [cd.made[s] for s in (fire, feature) if s]})
        return at if made is None else made + 1

    def plan(self, steps, area_=None, waiting=()):
        cd, steps, self.area = self.cd, list(steps), area_
        if not cd.fires:
            return steps, []
        cooks = self.trainers(cd.cooking)
        lo = self.after(steps, cooks, 0)
        if cd.cooking not in self.skills:
            rank = cd.rank_for(cd.cooking, 1) or {}
            name = cd.names[cd.cooking]
            least = {"min": rank["level"]} if rank.get("level", 0) > 1 else {}
            at, _ = self.paid(steps, lo, cooks,
                              lambda n, p, *_: {**self.errands.step("learn", f"learn:{cd.cooking}", f"Learn {name} at {n}", n, p,
                                                                    {"skills": [[name, 1]]}, rank.get("cost")), **least},
                              rank.get("cost"), "learn", f"Learning {name}", name)
            if at is not None:
                lo, self.skills[cd.cooking] = at + 1, 1
                if rank:
                    self.caps[cd.cooking] = rank["cap"]
        held_by = {w["skill"][0]: w for w in waiting if w.get("skill")}
        for prof in sorted(p for p in self.skills if p in cd.features and p != cd.cooking):
            spell = next((s for s in cd.features[prof] if cd.for_side(s, self.side)), None)
            if spell is None or self.knows(spell):
                continue
            todo, walls = self.making(spell, 0)
            if walls:
                h = held_by.get(prof)
                self.wall(f"{h['name']} and {cd.name(spell)}" if h else cd.name(spell), walls)
                continue
            at, why = self.do(steps, self.after(steps, self.trainers(prof, spell), 0), todo)
            if why == "far":
                self.wall(cd.name(spell), [{"kind": "source", "text": f"No {cd.names.get(prof)} trainer of yours in reach teaches {cd.name(spell)}"}])
            lo = lo if at is None else max(lo + 1, at)
        lo = self.first_camp(steps, lo, area_ and area_.get("at"))
        tier1 = min((cd.place_rank(v[0]) for p, v in cd.features.items() if p != cd.cooking), default=0)
        ahead = [s for s in cd.fires[1:]] + [s for p, v in cd.features.items() if p in self.skills or p == cd.cooking
                                            for s in v if cd.for_side(s, self.side) and (cd.place_rank(s) > tier1 or p == cd.cooking)]
        for spell in sorted(ahead, key=lambda s: (cd.place_rank(s), s not in cd.fires, s)):
            if self.count(cd.made[spell]) >= 1:
                continue
            todo, walls = self.making(spell, 1)
            if walls:
                self.wall(cd.name(spell), walls)
                continue
            at, _ = self.do(steps, lo, todo)
            lo = lo if at is None else at
        return steps, self.later

    def wall_step(self, steps):
        p = self.later and self.place_here(steps, len(steps))
        if not p:
            return None
        w = self.later[0]["wall"]
        need = {**(w.get("need") or {}), **({"level": w["min"]} if w.get("min") else {})}
        return {**self.errands.step("wall", f"wall:{w['kind']}", self.later[0]["text"], "", p, need), "npc": ""}


_restock = {"key": None, "part": None}


def restock(cd, services):
    from layers import sells
    was = _restock["key"]
    if was is not None and was[0] is cd and was[1] is services:
        return _restock["part"]
    fires = []
    for spell in cd.fires:
        wood = next(([int(i), int(n)] for i, n in cd.recipe(spell).get("reagents") or ()), None)
        if wood is None:
            continue
        tool = min(cd.tools(spell), default=None)
        fires.append([spell, cd.made[spell], wood[0], wood[1], cd.place_rank(spell), cd.names.get(cd.prof(spell), ""), tool])
    fires.sort(key=lambda f: ((cd.item(f[2]).get("price") or 0) * f[3], f[0]))
    wanted = sorted({f[2] for f in fires} | {f[6] for f in fires if f[6]})
    items = [[i, cd.item_name(i), cd.item(i).get("price") or 0,
              sorted(sv["id"] for sv in services or () if sv.get("id") is not None and sells(sv, [i]))] for i in wanted]
    _restock.update(key=(cd, services), part={"fires": fires, "items": items})
    return _restock["part"]


def make_camp(steps, cd, me, errands):
    chores = Chores(cd, me, errands, None)
    if not cd.fires or me.get("items") is None or not chores.due(sure=True):
        return steps
    kits = [s for s in cd.fires if chores.count(cd.made[s]) and cd.place_rank(s) <= chores.rank(cd.cooking)]
    feats = [s for v in cd.features.values() for s in v if chores.count(cd.made[s]) and cd.place_rank(s) <= chores.rank(cd.prof(s))]
    soon = [k for v in planunits.visits([spot(s) for s in steps])[:SOON] for k in v]
    k = next((k for k in soon if steps[k]["kind"] == "objective" and spot(steps[k])), None)
    k = next((k for k, s in enumerate(steps) if spot(s)), None) if k is None else k
    if not kits or not feats or k is None:
        return steps
    s = steps[k]
    objects = names([cd.item_name(cd.made[kits[-1]]), cd.item_name(cd.made[feats[0]])])
    p = (s["inst"], s["at"][0], s["at"][1], s["at"][2] if len(s["at"]) > 2 else None, s.get("map"))
    chore = {**errands.step("camp", "camp", f"Make camp: place your {objects}, then sit a minute for {CAMP_AURA}", "", p,
                            {"auras": [cd.aura]}), "npc": "", "takes": {"items": [cd.made[kits[-1]], cd.made[feats[0]]]}}
    return steps[:k] + [chore] + steps[k:]



HOLDS = re.compile(r"up to (\d+) additional camp features")


def plain_use(does):
    return " ".join(s.strip() for s in re.split(r"(?<=\.)\s+", (does or "").replace("\r", " ").replace("\n", " "))
                    if s.strip() and "$" not in s)


def recipe_state(chores, spell):
    cd = chores.cd
    prof = cd.prof(spell)
    if prof not in chores.skills:
        return "none"
    if chores.knows(spell):
        return "ready" if chores.rank(prof) >= cd.place_rank(spell) else "place"
    if chores.rank(prof) < cd.learn_rank(spell):
        return "skill"
    if spell in cd.blueprint and chores.count(cd.blueprint[spell]) < 1:
        return "blueprint"
    return "learn"


def panel_recipe(chores, spell, use_text):
    cd = chores.cd
    item = cd.made[spell]
    how = "skill" if cd.with_skill(spell) else "blueprint" if spell in cd.blueprint else "trainer"
    use = use_text(item) or plain_use(cd.item(item).get("use", {}).get("does"))
    out = {"spell": spell, "name": cd.name(spell), "item": item, "prof": cd.names.get(cd.prof(spell)) or "",
           "place": cd.place_rank(spell), "learn": cd.learn_rank(spell), "how": how,
           "state": recipe_state(chores, spell), "use": use,
           "takes": [[i, n, cd.item_name(i)] for i, n in cd.takes(spell)]}
    if how == "blueprint":
        lookup, drops = chores.me.get("npc") or (lambda n: None), []
        for npc, chance in cd.droppers(cd.blueprint[spell])[:3]:
            who = lookup(npc)
            drops.append({"npc": npc, "chance": chance, "name": who[0] if who else None, "level": who[1] if who else None})
        out["blueprint"] = {"item": cd.blueprint[spell], "name": cd.item_name(cd.blueprint[spell]), "drops": drops}
    return out


def panel(cd, me, use_text):
    if not cd.fires:
        return None
    chores = Chores(cd, me, None, None)
    fires = []
    for s in cd.fires:
        f = panel_recipe(chores, s, use_text)
        holds = HOLDS.search(f["use"] or "")
        f["holds"] = int(holds.group(1)) if holds else None
        fires.append(f)
    mine, others = [], 0
    for prof, spells in sorted(cd.features.items(), key=lambda kv: cd.names.get(kv[0]) or ""):
        tiers = [panel_recipe(chores, s, use_text) for s in spells if cd.for_side(s, chores.side)]
        if prof in chores.skills:
            mine.append({"prof": cd.names.get(prof) or "", "rank": chores.rank(prof), "tiers": tiers})
        elif tiers:
            others += 1
    auras, now = cd.data.get("auras") or {}, me.get("now") or 0
    lasts = lambda a: (auras.get(str(a)) or {}).get("lasts")
    welcome = ticks.CAMPFIRE_AURAS[0]
    kit_use = cd.item(cd.made[cd.fires[0]]).get("use") or {}
    camp = {"sit": lasts(welcome), "benefits": lasts(cd.aura), "fire": kit_use.get("lasts"), "cooldown": lasts(cd.cool_aura)}
    had = me.get("auras") or {}
    for key, aura in (("benefitsLeft", cd.aura), ("cooldownLeft", cd.cool_aura)):
        if aura in had:
            ends = had[aura]
            camp[key] = False if ends is False else None if ends is None else max(0, round(ends - now))
    return {"fires": fires, "features": mine, "others": others, "camp": camp,
            "known": bool(me.get("known")), "level": me.get("level")}


def opens(book):
    return min((q.get("req") or q.get("level") or 1 for q in book.quests.values() if q.get("zone") == CAMPING_SORT), default=None)


_data = {"stamp": None, "camp": None}


def load(path=None):
    path = path or ticks.PROFESSIONS
    stamp = store.stamp(path)
    if _data["stamp"] != (path, stamp) or _data["camp"] is None:
        _data.update(stamp=(path, stamp), camp=CampData(store.load_json(path, {}) if stamp is not None else {}))
    return _data["camp"]
