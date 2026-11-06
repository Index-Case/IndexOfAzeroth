# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import profepics
import words
from camping import counted, names
from facts import RUN_SPEED

WAYS = ("vendor", "auction", "grind", "gather", "quest", "craft")
DEPTH_MOST = 4
HOUR = 3600.0
KEY = "craft:"
AUCTION = {"auction"}


def farm_seconds(spot, short):
    per_hour = spot.get("perHour") or 0
    return (spot.get("trip") or 0) + (short / per_hour * HOUR if per_hour > 0 else math.inf)


def learnable(recipe):
    return bool(recipe.get("known")) or (recipe.get("skill") is not None and recipe.get("yours") is not None
                                         and recipe["skill"] <= recipe["yours"])


def materials(item, total, carry, src, picks=None):
    picked = {int(k): v for k, v in (picks or {}).items() if str(k).lstrip("-").isdigit()}
    pool = {int(i): int(n) for i, n in (carry or {}).items()}
    tree = Tree(src, picked)
    top = tree.take(int(item), int(total), "goal", pool)
    tree.settle(top, 0, (), pool)
    rows = []
    flatten(top, None, 0, rows)
    return {"rows": rows, "seconds": top["seconds"], "cost": top["cost"]}


def flatten(node, parent, depth, rows):
    at = len(rows)
    rows.append({**{k: v for k, v in node.items() if k != "children"}, "depth": depth, "parent": parent})
    for child in node["children"]:
        flatten(child, at, depth + 1, rows)


class Tree:

    def __init__(self, src, picks, tools=None):
        self.src, self.picks = src, picks
        self.tools = set() if tools is None else tools

    def take(self, item, need, kind, pool):
        have = min(max(0, pool.get(item, 0)), need)
        pool[item] = pool.get(item, 0) - have
        return {"item": item, "name": self.src.name(item), "kind": kind, "need": need, "have": have, "short": need - have,
                "ways": None, "pick": None, "seconds": 0.0, "cost": 0, "children": []}

    def settle(self, node, depth, path, pool):
        if not node["short"]:
            return node
        ways = node["ways"] = self.ways(node["item"], node["short"], depth, path, node["kind"])
        node["pick"] = self.choose(node, ways, depth, path, pool)
        if node["pick"] == "craft":
            self.craft(node, ways["craft"], depth, path + (node["item"],), pool)
        elif node["pick"]:
            node["seconds"], node["cost"] = self.costs(node["pick"], ways, node["short"])
        return node

    def ways(self, item, short, depth, path, kind):
        src = self.src
        recipe = src.recipe(item) if kind != "pattern" and item not in path and depth < DEPTH_MOST else None
        if kind == "goal":
            return {**dict.fromkeys(WAYS), "craft": recipe}
        grind, gather = src.spot(item, "grind"), src.spot(item, "gather")
        return {"vendor": src.vendor(item), "auction": src.auction(item, [s for s in (grind, gather) if s]),
                "grind": grind, "gather": gather, "quest": src.quest(item) if short == 1 else None, "craft": recipe}

    def choose(self, node, ways, depth, path, pool):
        if node["kind"] == "goal":
            return "craft" if ways["craft"] else None
        asked = self.picks.get(node["item"])
        if asked in WAYS and ways.get(asked):
            return asked
        return self.rule(node, ways, depth, path, pool)

    def rule(self, node, ways, depth, path, pool):
        if ways["vendor"]:
            return "vendor"
        house = ways["auction"]
        if house and house.get("cheaper"):
            return "auction"
        times = {way: farm_seconds(ways[way], node["short"]) for way in ("grind", "gather") if ways[way]}
        if ways["quest"] and ways["quest"].get("seconds") is not None:
            times["quest"] = ways["quest"]["seconds"]
        recipe = ways["craft"]
        if recipe and recipe.get("yours") is not None and learnable(recipe):
            times["craft"] = self.dry(node, recipe, depth, path, pool)
        times = {w: t for w, t in times.items() if t < math.inf}
        if times:
            return min(times, key=lambda w: (times[w], WAYS.index(w)))
        return "auction" if house else None

    def dry(self, node, recipe, depth, path, pool):
        scratch = Tree(self.src, self.picks, set(self.tools))
        trial = {**node, "children": []}
        scratch.craft(trial, recipe, depth, path + (node["item"],), dict(pool))
        return trial["seconds"]

    def craft(self, node, recipe, depth, path, pool):
        crafts = math.ceil(node["short"] / max(1, recipe.get("makes") or 1))
        node["recipe"] = {**recipe, "crafts": crafts}
        kids = []
        if not recipe.get("known") and recipe.get("how") == "item" and recipe.get("patterns"):
            held = next((p for p in recipe["patterns"] if pool.get(p, 0) > 0), None)
            if held is not None:
                pool[held] -= 1
            else:
                kids.append(self.take(recipe["patterns"][0], 1, "pattern", pool))
        for category, items in recipe.get("tools") or ():
            if ("tool", category) not in self.tools and not any(pool.get(i, 0) > 0 for i in items):
                self.tools.add(("tool", category))
                kids.append(self.take(next((i for i in items if self.src.vendor(i)), items[0]), 1, "tool", pool))
        for item in recipe.get("totems") or ():
            if ("item", item) not in self.tools and pool.get(item, 0) <= 0:
                self.tools.add(("item", item))
                kids.append(self.take(item, 1, "tool", pool))
        for item, count in recipe.get("reagents") or ():
            kids.append(self.take(int(item), int(count) * crafts, "material", pool))
        for kid in kids:
            self.settle(kid, depth + 1, path, pool)
        node["children"] = kids
        talk = self.src.talk
        node["seconds"] = sum(k["seconds"] for k in kids) + (0.0 if recipe.get("known") else talk) + talk * crafts
        node["cost"] = sum(k["cost"] for k in kids)

    def costs(self, pick, ways, short):
        way = ways[pick]
        if pick in ("grind", "gather"):
            return farm_seconds(way, short), 0
        if pick in ("vendor", "auction"):
            return way.get("seconds") or self.src.talk, int(round((way.get("price") or 0) * short))
        return way.get("seconds") or 0.0, 0


class Sources:

    def __init__(self, look, pd, known=(), here=None, quest_seconds=None, talk=10.0):
        self.look, self.pd, self.cd = look, pd, pd.cd
        self.known, self.here, self.quest_seconds, self.talk = set(known or ()), here, quest_seconds, talk
        self.kept = {}

    def _kept(self, what, item, make):
        key = (what, item)
        if key not in self.kept:
            self.kept[key] = make()
        return self.kept[key]

    def name(self, item):
        return self.cd.item_name(item)

    def recipe(self, item):
        return self._kept("recipe", item, lambda: self._recipe(item))

    def _recipe(self, item):
        found = [self.info(c) for c in self.look.crafts(item)]
        short = lambda r: max(0, (r["skill"] or 0) - (r["yours"] or 0))
        return min(found, key=lambda r: (r["yours"] is None, not r["known"], short(r), r["spell"]), default=None)

    def info(self, c):
        cd, spell = self.cd, int(c["recipe"])
        r = cd.recipe(spell)
        learnt = r.get("learnt") or ()
        mine = c.get("yours") is not None
        how = "trainer" if "trainer" in learnt else "item" if r.get("items") else "skill" if "skill" in learnt else None
        makes = r.get("makes") or []
        tools = cd.data.get("tools") or {}
        station = (cd.data.get("stations") or {}).get(str(r.get("station"))) if r.get("station") is not None else None
        return {"spell": spell, "name": cd.name(spell), "line": c["line"], "profession": c["profession"],
                "skill": 1 if how == "skill" else self.pd.learnt_at(spell), "yours": c.get("yours"),
                "known": spell in self.known or (mine and "skill" in learnt), "how": how,
                "patterns": [int(i) for i in r.get("items") or ()], "makes": int(makes[1]) if len(makes) > 1 else 1,
                "reagents": [[int(i), int(n)] for i, n in r.get("reagents") or ()],
                "tools": [[int(t), [int(i) for i in (tools.get(str(t)) or {}).get("items") or ()]] for t in r.get("tools") or ()
                          if (tools.get(str(t)) or {}).get("items")],
                "totems": [int(t) for t in r.get("totems") or ()], "station": station}

    def vendor(self, item):
        def make():
            v = self.look.vendor(item)
            if not v:
                return None
            return {"name": v.get("name"), "price": self.pd.unit_price(item), "seconds": (v.get("yards") or 0) / RUN_SPEED + self.talk}
        return self._kept("vendor", item, make)

    def auction(self, item, spots):
        def make():
            got = self.look.house(item, self.here, spots)
            return got and {**got, "seconds": self.talk}
        return self._kept(("auction", tuple(s.get("score") for s in spots)), item, make)

    def spot(self, item, way):
        return self._kept(("spot", way), item, lambda: self.look.spot(item, way, self.here))

    def quest(self, item):
        def make():
            found = self.look.quests(item)
            if not found:
                return None
            q = found[0]
            seconds = self.quest_seconds(item, q) if self.quest_seconds else None
            return {"id": q["id"], "name": q["name"], "seconds": seconds}
        return self._kept("quest", item, make)




def epic_name(item):
    return words.say("both.craft.name", {"item": item})


def craft_text(item, count, station):
    said = {"item": item, "count": count, "station": profepics.station_words(station) if station else ""}
    if count == 1:
        return words.say("both.craft.craft.station", said) if station else words.say("both.craft.craft", said)
    return words.say("both.craft.craft.some.station", said) if station else words.say("both.craft.craft.some", said)


def farm_text(kind, item, count):
    said = {"item": item, "count": count}
    if kind == "skin":
        return words.say("both.craft.skin", said)
    if kind == "herbalism":
        return words.say("both.craft.herbalism", said)
    if kind == "mining":
        return words.say("both.craft.mining", said)
    return words.say("both.craft.grind", said)


def chores(steps, made, chores_, pd, me):
    return Placer(steps, made, chores_, pd, me).run()


class Placer:

    def __init__(self, steps, made, chores_, pd, me):
        self.steps, self.rows, self.c, self.pd, self.cd, self.me = list(steps), made["rows"], chores_, pd, pd.cd, me
        self.carry = me.get("items") or {}
        self.kids = {i: [] for i in range(len(self.rows))}
        for i, r in enumerate(self.rows):
            if r["parent"] is not None:
                self.kids[r["parent"]].append(i)
        self.key = f"{KEY}{self.rows[0]['item']}"
        self.walls, self.missing, self.learnt = [], set(), {}

    def target(self, item, picks):
        return self.carry.get(item, 0) + sum(r["short"] for r in self.rows if r["item"] == item and r["pick"] in picks)

    def run(self):
        self.materials()
        self.craft(0)
        for w in self.walls:
            self.c.here(self.steps, len(self.steps), "wall", w["key"], w["text"], w["need"])
        return self.steps

    def wall(self, key, text, need):
        self.walls.append({"key": f"{self.key}:wall:{key}", "text": text, "need": need})


    def materials(self):
        rows = [r for r in self.rows if r["short"] and r["pick"] not in (None, "craft", "quest")]
        sold = {r["item"]: self.target(r["item"], ("vendor",)) for r in rows if r["pick"] == "vendor"}
        if sold:
            self.c.buy(self.steps, 0, f"{self.key}:buy", sold, words.say("both.craft.materials", {"item": self.rows[0]["name"]}))
            self.missing |= set(sold) - self.got()
        house = {r["item"]: r for r in rows if r["pick"] == "auction"}
        if house:
            self.auction(house)
        for item in dict.fromkeys(r["item"] for r in rows if r["pick"] in ("grind", "gather")):
            self.session(item, next(r for r in rows if r["item"] == item), self.target(item, ("grind", "gather")))

    def got(self):
        out = set()
        for s in self.steps:
            out |= {int(e[0]) for e in ((s.get("need") or {}).get("items") or ())}
            if s.get("kind") == "turnin" and s.get("want"):
                out.add(int(s["want"]))
        return out

    def auction(self, house):
        name = self.cd.item_name
        said = names([counted(r["short"], name(i)) for i, r in sorted(house.items())])
        cost = sum(int(round(r["ways"]["auction"]["price"] * r["short"])) for r in house.values())
        need = {"items": [[i, self.target(i, ("auction",))] for i in sorted(house)]}

        def make(n, p, *_):
            return self.c.chore("supplies", f"{self.key}:auction", words.say("both.craft.auction", {"items": said}), n, p, need, cost)
        at, _ = self.c.paid(self.steps, 0, self.c.errands.places(AUCTION, self.c.side, ids=True), make, cost, "supplies",
                            words.say("both.craft.buying", {"items": said}), said)
        if at is None:
            self.missing |= set(house)

    def session(self, item, row, target):
        spot = row["ways"][row["pick"]]
        kind = spot.get("kind") or "kill"
        text = farm_text(kind, row["name"], target)
        place = ("", (spot["inst"], spot["at"][0], spot["at"][1], None, spot.get("map")), {}, None)

        def make(n, p, *_):
            step = self.c.errands.step("farm", f"{self.key}:farm:{item}", text, "", p, {"items": [[item, target]]})
            return {**step, "npc": "", "farm": kind, "item": item, "target": row["name"],
                    "spawns": [list(s[:2]) for s in spot.get("spawns") or ()],
                    **({"mobs": list(spot.get("ids") or ())} if kind in ("kill", "skin") else {})}
        if self.c.fit(self.steps, 0, [place], make) is None:
            self.steps.append(make(*place))


    def after(self, items):
        items = set(items)
        return max((k + 1 for k, s in enumerate(self.steps)
                    if items & {int(e[0]) for e in ((s.get("need") or {}).get("items") or ())}
                    or (s.get("kind") == "turnin" and s.get("want") in items)), default=0)

    def craft(self, i):
        r = self.rows[i]
        if not r["short"]:
            return True
        if r["pick"] != "craft":
            if r["pick"] is None:
                self.wall(r["item"], words.say("both.craft.none", {"item": r["name"], "count": r["short"]}),
                          {"items": [[r["item"], self.carry.get(r["item"], 0) + r["short"]]]})
                return False
            return r["item"] not in self.missing
        under = [self.craft(j) for j in self.kids[i]]
        rec = r["recipe"]
        name, spell = rec["profession"], rec["spell"]
        lo = self.profession(rec)
        if lo is None:
            return False
        if not rec["known"] and rec["how"] is None:
            self.wall(f"recipe:{spell}", words.say("both.craft.unlearnt", {"recipe": rec["name"]}), {"recipes": [spell]})
            return False
        then = 1 if rec["yours"] is None else rec["yours"]
        if not rec["known"] and rec["skill"] is not None and rec["skill"] > then:
            self.wall(f"skill:{spell}", words.say("both.craft.skill", {"skill": name, "need": rec["skill"], "have": rec["yours"] or 0}),
                      {"skills": [[name, rec["skill"]]]})
            return False
        if not all(under):
            return False
        kids = [self.rows[j]["item"] for j in self.kids[i]]
        lo = max(lo, self.after(kids))
        if not rec["known"] and rec["how"] == "trainer":
            at, _ = self.c.recipe(self.steps, lo, name, spell, f"{self.key}:recipe:{spell}", rec["name"])
            if at is None:
                return False
            lo = at + 1
        elif not rec["known"] and rec["how"] == "item":
            pattern = next((p for p in rec["patterns"] if p in kids or self.carry.get(p)), rec["patterns"][0])
            at = self.c.here(self.steps, lo, "learn", f"{self.key}:recipe:{spell}",
                             f"Learn {rec['name']} by using {self.cd.item_name(pattern)} from your bags", {"recipes": [spell]},
                             takes={"items": [pattern], "skills": [name]})
            if at is None:
                return False
            lo = at + 1
        at = self.c.here(self.steps, lo, "craft", f"{self.key}:craft:{spell}", craft_text(r["name"], r["short"], rec["station"]),
                         {"items": [[r["item"], self.target(r["item"], ("craft",))]]},
                         takes={"items": kids, "recipes": [spell], "skills": [name]})
        return at is not None

    def profession(self, rec):
        line = rec["line"]
        if rec["yours"] is not None:
            return 0
        if line not in self.learnt:
            st = profepics.status(self.pd, line, self.me)
            if st["state"] == "learn":
                self.learnt[line] = self.c.learn(self.steps, st, True)[0] is not None
            else:
                self.wall(f"learn:{line}", st.get("why") or st["text"], {"level": st["min"]} if st.get("min") else {})
                self.learnt[line] = False
        if not self.learnt[line]:
            return None
        key = f"{profepics.PREFIX}{line}:learn"
        return next(k + 1 for k, s in enumerate(self.steps) if s.get("key") == key)
