# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import math
import time

import farmspots
import profepics
import words
from camping import BANK_KEY, SELL_KEY, buy_line
from errands import MERCHANT, money_before, pays
from errands import vendor_price
from facts import RUN_SPEED

WAYS = ("vendor", "auction", "grind", "gather", "quest", "craft")
MODES = ("gather", "buy", "both", "cheap")
BOTH = "both"
CHEAP = "cheap"
DEPTH_MOST = 4
BATCH_YARDS = 150
BATCH = 10
KEY = "craft:"
BANK = {"bank"}


def farm_seconds(spot, short):
    return farmspots.farm_seconds(spot.get("perHour") or 0, spot.get("trip") or 0, short)


def learnable(recipe, skill=None):
    skill = recipe.get("yours") if skill is None else skill
    return bool(recipe.get("known")) or (recipe.get("skill") is not None and skill is not None and recipe["skill"] <= skill)


def goal(item, total):
    return {"item": int(item), "count": int(total)}


def craft_goals(pd, src, me, item, total, carry, picks=None, mode=BOTH):
    rec = src.recipe(item)
    up = {"goals": [], "route": [], "walls": []}
    then = rec and (1 if rec["yours"] is None else rec["yours"])
    if (rec and (carry or {}).get(item, 0) < total and not rec["known"] and rec["how"] is not None
            and rec["skill"] is not None and rec["skill"] > then):
        up = levelling(pd, src, me, rec["line"], rec["skill"], mode, picks)
    return {**up, "goals": up["goals"] + [goal(item, total)]}


def materials(goals, carry, src, picks=None, mode=BOTH, bank=None):
    picked = {int(k): v for k, v in (picks or {}).items() if str(k).lstrip("-").isdigit()}
    pool = {int(i): int(n) for i, n in (carry or {}).items()}
    tree = Tree(src, picked, mode=mode, bank={int(i): int(n) for i, n in (bank or {}).items()})
    rows, tops, seconds, cost = [], [], 0.0, 0
    for g in goals:
        seg = g.get("level")
        top = tree.take(int(g["item"]), int(g["count"]), "goal", {} if seg else pool, banked=not seg)
        if seg:
            tree.at[g["recipe"]["line"]] = seg["from"]
        tree.settle(top, 0, (), pool, g.get("recipe"))
        if seg:
            top["level"] = seg
            pool[top["item"]] = pool.get(top["item"], 0) + top["need"]
            tree.at[g["recipe"]["line"]] = seg["to"]
        tops.append(len(rows))
        flatten(top, None, 0, rows)
        seconds, cost = seconds + top["seconds"], cost + top["cost"]
    return {"rows": rows, "seconds": seconds, "cost": cost, "goals": tops}


def flatten(node, parent, depth, rows):
    at = len(rows)
    rows.append({**{k: v for k, v in node.items() if k != "children"}, "depth": depth, "parent": parent})
    for child in node["children"]:
        flatten(child, at, depth + 1, rows)


class Tree:

    def __init__(self, src, picks, tools=None, mode=BOTH, at=None, bank=None):
        self.src, self.picks, self.mode = src, picks, mode
        self.tools = set() if tools is None else tools
        self.at = {} if at is None else at
        self.bank = {} if bank is None else bank

    def skill(self, recipe):
        return self.at.get(recipe.get("line"), recipe.get("yours"))

    def take(self, item, need, kind, pool, banked=True):
        have = min(max(0, pool.get(item, 0)), need)
        pool[item] = pool.get(item, 0) - have
        out = min(max(0, self.bank.get(item, 0)), need - have) if banked else 0
        if out:
            self.bank[item] -= out
        return {"item": item, "name": self.src.name(item), "kind": kind, "need": need, "have": have + out, "banked": out,
                "short": need - have - out, "ways": None, "pick": None, "seconds": 0.0, "cost": 0, "children": []}

    def settle(self, node, depth, path, pool, recipe=None):
        if not node["short"]:
            return node
        ways = node["ways"] = self.ways(node["item"], node["short"], depth, path, node["kind"], recipe)
        node["pick"] = self.choose(node, ways, depth, path, pool)
        if node["pick"] == "craft":
            self.craft(node, ways["craft"], depth, path + (node["item"],), pool)
        elif node["pick"]:
            node["seconds"], node["cost"] = self.costs(node["pick"], ways, node["short"])
        return node

    def ways(self, item, short, depth, path, kind, recipe=None):
        src = self.src
        if recipe is None:
            recipe = src.recipe(item) if kind != "pattern" and item not in path and depth < DEPTH_MOST else None
        if kind == "goal":
            return {**dict.fromkeys(WAYS), "craft": recipe}
        grind, gather = src.spot(item, "grind", short), src.spot(item, "gather", short)
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
        vendor, house = ways["vendor"], ways["auction"]
        if vendor and vendor.get("limited"):
            return self.rule(node, {**ways, "vendor": None}, depth, path, pool) or "vendor"
        if self.mode == CHEAP:
            cheap = self.cheapest(node, ways, depth, path, pool)
            if cheap:
                return cheap
        if vendor and self.mode != "gather":
            return "vendor"
        if house and (self.mode == "buy" or self.mode == BOTH and house.get("cheaper")):
            return "auction"
        quick = self.quickest(node, ways, depth, path, pool)
        if quick:
            return quick
        if vendor:
            return "vendor"
        return "auction" if house else None

    def quickest(self, node, ways, depth, path, pool):
        times = {way: farm_seconds(ways[way], node["short"]) for way in ("grind", "gather") if ways[way]}
        if ways["quest"] and ways["quest"].get("seconds") is not None:
            times["quest"] = ways["quest"]["seconds"]
        recipe = ways["craft"]
        if recipe and self.skill(recipe) is not None and learnable(recipe, self.skill(recipe)):
            times["craft"] = self.dry(node, recipe, depth, path, pool)
        times = {w: t for w, t in times.items() if t < math.inf}
        return min(times, key=lambda w: (times[w], WAYS.index(w))) if times else None

    def cheapest(self, node, ways, depth, path, pool):
        costs = {way: (ways[way].get("price") or 0) * node["short"] for way in ("vendor", "auction") if ways[way]}
        recipe = ways["craft"]
        if recipe and self.skill(recipe) is not None and learnable(recipe, self.skill(recipe)):
            trial = self.dry(node, recipe, depth, path, pool, whole=True)

            def got(n):
                return not n["short"] or (n["pick"] is not None and all(got(k) for k in n["children"]))
            if all(got(k) for k in trial["children"]):
                costs["craft"] = trial["cost"]
        order = ("craft", "vendor", "auction")
        return min(costs, key=lambda way: (costs[way], order.index(way))) if costs else None

    def dry(self, node, recipe, depth, path, pool, whole=False):
        scratch = Tree(self.src, self.picks, set(self.tools), self.mode, self.at, dict(self.bank))
        trial = {**node, "children": []}
        scratch.craft(trial, recipe, depth, path + (node["item"],), dict(pool))
        return trial if whole else trial["seconds"]

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

    def __init__(self, look, pd, known=(), here=None, quest_seconds=None, talk=10.0, me=None):
        self.look, self.pd, self.cd = look, pd, pd.cd
        self.known, self.here, self.quest_seconds, self.talk = set(known or ()), here, quest_seconds, talk
        self.me = me or {}
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

    @staticmethod
    def sells(item):
        import gamedata
        return gamedata.item_sell_price(item)

    def info(self, c):
        cd, spell = self.cd, int(c["recipe"])
        r = cd.recipe(spell)
        learnt = r.get("learnt") or ()
        mine = c.get("yours") is not None
        how = "trainer" if "trainer" in learnt else "item" if r.get("items") else "skill" if "skill" in learnt else None
        makes = r.get("makes") or []
        tools = cd.data.get("tools") or {}
        station = (cd.data.get("stations") or {}).get(str(r.get("station"))) if r.get("station") is not None else None
        return {"spell": spell, "name": cd.name(spell), "item": int(makes[0]) if makes else None, "line": c["line"],
                "profession": c["profession"], "skill": 1 if how == "skill" else self.pd.learnt_at(spell), "yours": c.get("yours"),
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
            return {"name": v.get("name"), "price": vendor_price(self.pd.unit_price(item), self.me),
                    "seconds": (v.get("yards") or 0) / RUN_SPEED + self.talk, "limited": bool(v.get("limited"))}
        return self._kept("vendor", item, make)

    def auction(self, item, spots):
        def make():
            got = self.look.house(item, self.here, spots)
            return got and {**got, "seconds": self.talk}
        return self._kept(("auction", tuple(s.get("score") for s in spots)), item, make)

    def spot(self, item, way, short=None):
        return self._kept(("spot", way, short), item, lambda: self.look.spot(item, way, self.here, short))

    def quest(self, item):
        def make():
            found = self.look.quests(item)
            if not found:
                return None
            q = found[0]
            seconds = self.quest_seconds(item, q) if self.quest_seconds else None
            return {"id": q["id"], "name": q["name"], "seconds": seconds}
        return self._kept("quest", item, make)




def per_craft(src, recipe, mode=BOTH, picks=None):
    made = materials([{"item": recipe["item"], "count": BATCH * recipe["makes"], "recipe": recipe,
                       "level": {"from": recipe["skill"] or 1, "to": recipe["skill"] or 1}}], {}, src, picks, mode)
    nowhere = any(r["short"] and r["pick"] is None for r in made["rows"])
    return made["seconds"] / BATCH, made["cost"] / BATCH - (src.sells(recipe["item"]) or 0) * recipe["makes"], nowhere


CLOSE_COPPER = 50


def rank_cost(cost, mode=BOTH):
    seconds, copper, nowhere = cost
    return (nowhere, copper // CLOSE_COPPER, seconds) if mode == CHEAP else (nowhere, seconds, copper)


def levelling(pd, src, me, line, to, mode=BOTH, picks=None):
    cd = pd.cd
    name = cd.names.get(line, "")
    have = (me.get("profs") or {}).get(name)
    level = me.get("level") or 1
    rs = pd.ranks(line, (me.get("game_ranks") or {}).get(name), me.get("prices"))
    skill, cap = (have["rank"] or 1, have["max"] or 0) if have else (1, rs[0]["cap"] if rs else 0)
    costs = {}

    def info(spell):
        return src.info({"recipe": spell, "line": line, "profession": name, "yours": have["rank"] if have else None})

    def weighed(spell):
        if spell not in costs:
            costs[spell] = rank_cost(per_craft(src, info(spell), mode, picks), mode)
        return costs[spell]
    route = pd.route(line, skill, to, (me.get("known") or {}).get(name) or (), level, me.get("items"), per_craft=weighed,
                     cuts={r["cap"] for r in rs})
    goals, rows, walls = [], [], []
    for seg in route["segments"]:
        train = None
        if seg["from"] >= cap:
            train = next((r for r in rs if r["cap"] > cap), None)
            wall = rank_wall(train, name, level, cap)
            if wall:
                walls.append({**wall, "line": line})
                break
            cap = train["cap"]
        rec = info(seg["spell"])
        goals.append({"item": seg["made"], "count": seg["crafts"] * rec["makes"],
                      "recipe": {**rec, "known": seg["how"] == "known", "how": "trainer" if seg["how"] == "trainer" else rec["how"]},
                      "level": {"from": seg["from"], "to": seg["to"], "crafts": seg["crafts"], "colour": seg["colour"], "train": train}})
        rows.append({"from": seg["from"], "to": seg["to"], "item": cd.item_name(seg["made"]), "recipe": seg["name"],
                     "crafts": seg["crafts"], "colour": seg["colour"], "train": train and profepics.rank_words(train, name)})
    else:
        if route["stuck"] is not None:
            walls.append({"key": "stuck", "line": line, "need": {"skills": [[name, to]]},
                          "text": words.say("both.craft.stuck", {"skill": name, "at": route["stuck"]})})
    return {"goals": goals, "route": rows, "walls": walls}


def rank_wall(rank, prof, level, cap):
    if rank is None:
        return {"key": "top", "text": words.say("both.craft.top", {"skill": prof, "cap": cap}), "need": {}}
    if rank["level"] > level:
        wait = profepics.level_wait(rank, prof, False)
        return {"key": f"rank{rank['step']}", "text": wait["text"], "need": {"level": wait["min"]}}
    if rank["skill"] is None:
        return {"key": f"rank{rank['step']}", "need": {"caps": [[prof, rank["cap"]]]},
                "text": words.say("both.craft.unsaid", {"rank": profepics.rank_words(rank, prof)})}
    return None


def skill_ups(pd, src, me, goals, carry, picks=None, mode=BOTH, bank=None):
    if mode != CHEAP:
        return goals, []
    rows, raised = [], {}

    def weigh(g):
        made = materials(g, carry, src, picks, mode, bank)
        return sum(1 for r in made["rows"] if r["short"] and r["pick"] is None), made["cost"], made
    best = weigh(goals)
    while True:
        asks = {(rec["line"], rec["skill"]) for r in best[2]["rows"]
                for rec in [(r.get("ways") or {}).get("craft")] if r["short"] and r["pick"] in ("vendor", "auction") and rec
                and rec.get("yours") is not None and rec.get("skill") and not rec.get("known")
                and rec["skill"] > max(rec["yours"], raised.get(rec["line"], 0))}
        found = None
        for line, to in sorted(asks):
            up = levelling(pd, src, me, line, to, mode, picks)
            if up["walls"] or not up["goals"]:
                continue
            trial = weigh(up["goals"] + goals)
            if trial[:2] < (found or best)[:2] and trial[0] <= best[0]:
                found = (*trial, up, line, to)
        if not found:
            return goals, rows
        goals, rows, best = found[3]["goals"] + goals, found[3]["route"] + rows, found[:3]
        raised[found[4]] = found[5]




def epic_name(item):
    return words.say("both.craft.name", {"item": item})


def craft_text(item, count, station):
    said = {"item": item, "count": count, "station": profepics.station_words(station) if station else ""}
    if count == 1:
        return words.say("both.craft.craft.station", said) if station else words.say("both.craft.craft", said)
    return words.say("both.craft.craft.some.station", said) if station else words.say("both.craft.craft.some", said)


def level_text(item, seg, prof, station):
    said = {"item": item, "count": seg["crafts"], "colour": seg["colour"], "to": seg["to"], "skill": prof,
            "station": profepics.station_words(station) if station else ""}
    return words.say("both.craft.level.station", said) if station else words.say("both.craft.level", said)


def farm_text(kind, item, count):
    said = {"item": item, "count": count}
    if kind == "skin":
        return words.say("both.craft.skin", said)
    if kind == "herbalism":
        return words.say("both.craft.herbalism", said)
    if kind == "mining":
        return words.say("both.craft.mining", said)
    return words.say("both.craft.grind", said)


DAY = 86400.0


def bank_age(at, now=None):
    days = int(((time.time() if now is None else now) - at) // DAY) if at else 0
    if days < 1:
        return None
    return words.say("both.craft.age.one", {}) if days == 1 else words.say("both.craft.age", {"n": days})


def chores(steps, made, chores_, pd, me, key):
    return Placer(steps, made, chores_, pd, me, key).run()


class Placer:

    def __init__(self, steps, made, chores_, pd, me, key):
        self.steps, self.rows, self.c, self.pd, self.cd, self.me = list(steps), made["rows"], chores_, pd, pd.cd, me
        self.key = key
        self.banked = collections.Counter()
        for r in self.rows:
            self.banked[r["item"]] += r.get("banked") or 0
        bags = me.get("items") or {}
        self.carry = {i: bags.get(i, 0) + self.banked.get(i, 0) for i in set(bags) | set(self.banked)}
        self.kids = {i: [] for i in range(len(self.rows))}
        for i, r in enumerate(self.rows):
            if r["parent"] is not None:
                self.kids[r["parent"]].append(i)
        self.goals = made.get("goals") or ([0] if self.rows else [])
        self.walls, self.missing, self.learnt = [], set(), {}
        self.left = {}
        self.made = []
        self.bank_at = made.get("bankAt")
        for w in made.get("walls") or ():
            self.wall(w["key"], w["text"], w["need"])
        self.skill, self.taught, self.up, self.stopped = {}, set(), {}, set()
        self.halted = {w["line"] for w in made.get("walls") or () if w.get("line") is not None}

    def target(self, item, picks):
        return self.carry.get(item, 0) + sum(r["short"] for r in self.rows if r["item"] == item and r["pick"] in picks
                                             and not r.get("level"))

    def stretches(self):
        root, first = {}, {}
        for g in self.goals:
            todo = [g]
            while todo:
                i = todo.pop()
                root[i] = g
                todo.extend(self.kids[i])
                r = self.rows[i]
                if r["pick"] == "craft" and not r.get("level"):
                    first.setdefault(r["item"], g)
        out = {}
        for i, r in enumerate(self.rows):
            if i in root and r["parent"] is not None:
                above = self.rows[r["parent"]]
                out[i] = root[i] if above.get("level") else first.get(above["item"], root[i])
        return out

    def run(self):
        self.stretch, self.order = self.stretches(), {g: k for k, g in enumerate(self.goals)}
        self.withdraw()
        for i in self.goals:
            self.materials(i)
            self.craft(i)
        self.sell(len(self.steps), ":last")
        for w in self.walls:
            self.c.here(self.steps, len(self.steps), "wall", w["key"], w["text"], w["need"])
        return self.steps

    def withdraw(self):
        out = {i: n for i, n in sorted(self.banked.items()) if n}
        if not out:
            return
        left = [(self.cd.item_name(i), n) for i, n in out.items()]
        need = {"items": [[i, self.carry[i]] for i in out]}
        age = bank_age(self.bank_at)

        def make(n, p, *_):
            step = self.c.chore("supplies", f"{self.key}{BANK_KEY}", buy_line(left, bank=True, age=age), n, p, need)
            return {**step, **({"seen": age} if age else {})}
        at, _ = self.c.paid(self.steps, len(self.steps), self.c.errands.places(BANK, self.c.side, ids=True), make, 0)
        if at is None:
            self.missing |= set(out)

    def held(self, k):
        bags, made = collections.Counter(self.carry), {key: (item, n) for key, item, n in self.made}
        for s in self.steps[:k]:
            need = s.get("need") or {}
            for i, n in need.get("items") or ():
                bags[int(i)] = max(bags[int(i)], int(n))
            if s.get("key") in made:
                item, n = made[s["key"]]
                bags[item] += n
            for i, n in (s.get("takes") or {}).get("uses") or ():
                bags[i] = max(0, bags[i] - n)
            for i, keep, _ in need.get("most") or ():
                bags[i] = min(bags[i], keep)
            if s.get("kind") == "turnin" and s.get("want"):
                bags[int(s["want"])] += 1
        return bags

    def craft_key(self, i):
        r = self.rows[i]
        spell = r["recipe"]["spell"]
        return f"{self.key}:craft:{spell}:{r['level']['to']}" if r.get("level") else f"{self.key}:craft:{spell}"

    def sell(self, k, tag, visit=None):
        where = {s.get("key"): j for j, s in enumerate(self.steps)}
        bags, made, sold, later = self.held(k), collections.Counter(), collections.Counter(), collections.Counter()
        for key, item, n in self.made:
            if where.get(key, k) < k:
                made[item] += n
        for s in self.steps:
            for i, _, n in (s.get("need") or {}).get("most") or ():
                sold[i] += n
        for r in self.rows:
            if r["parent"] is not None and where.get(self.craft_key(r["parent"]), k) >= k:
                later[r["item"]] += r["need"]
        sells = {}
        for item in sorted(made):
            n, price = min(bags[item] - later[item], made[item] - sold[item]), Sources.sells(item)
            if n > 0 and price:
                sells[item] = (n, price)
        if not sells:
            return
        left = [(self.cd.item_name(i), n) for i, (n, _) in sells.items()]
        skills = [[self.cd.names.get(line, ""), max(to for to, key in ups if where.get(key, k) < k)]
                  for line, ups in sorted(self.up.items()) if any(where.get(key, k) < k for _, key in ups)]
        need = {"most": [[i, bags[i] - n, n] for i, (n, _) in sells.items()], "skills": skills}
        gain = int(sum(n * price for n, price in sells.values()))

        def make(n, p, *_):
            return {**self.c.chore("supplies", f"{self.key}{SELL_KEY}{tag}", buy_line(left, n, sell=True), n, p, need),
                    "gain": gain}
        vendors = self.c.errands.places(MERCHANT, self.c.side, ids=True)
        if visit is None:
            self.c.fit(self.steps, k, vendors, make)
            return
        at = visit["at"]
        if ":auction" in visit["key"]:
            near = [p for p in vendors if p[1][0] == visit["inst"] and math.dist(p[1][1:3], at[:2]) <= BATCH_YARDS]
            if not near:
                return
            name, place = min(near, key=lambda p: math.dist(p[1][1:3], at[:2]))[:2]
        else:
            name, place = visit["npc"], (visit["inst"], at[0], at[1], at[2] if len(at) > 2 else None, visit.get("map"))
        self.steps.insert(k, make(name, place))
        if "pay" in visit["need"] and pays(money_before(self.steps, k + 1, self.me.get("money")), visit["need"]["pay"]) is True:
            visit["need"] = {a: b for a, b in visit["need"].items() if a != "pay"}

    def wall(self, key, text, need):
        key = f"{self.key}:wall:{key}"
        if all(w["key"] != key for w in self.walls):
            self.walls.append({"key": key, "text": text, "need": need})

    def position(self, key):
        return next((k for k, s in enumerate(self.steps) if s.get("key") == key), None)


    def materials(self, g):
        rows = [r for i, r in enumerate(self.rows) if self.stretch.get(i) == g and r["short"]
                and r["pick"] not in (None, "craft", "quest")]
        if not rows:
            return
        later = collections.Counter()
        for i, r in enumerate(self.rows):
            if i in self.stretch and self.order[self.stretch[i]] > self.order[g]:
                later[r["item"]] += r["have"]

        def held(item, picks):
            mine = [r for r in rows if r["item"] == item and r["pick"] in picks]
            have = later[item] + sum(r["have"] for r in mine)
            return have, have + sum(r["short"] for r in mine)
        tag = f":{self.order[g] + 1}" if self.order[g] else ""
        lo, before = len(self.steps), {id(s) for s in self.steps}
        sold = {r["item"]: held(r["item"], ("vendor",)) for r in rows if r["pick"] == "vendor"}
        if sold:
            had = {id(s) for s in self.steps}
            self.c.buy(self.steps, lo, f"{self.key}:buy{tag}", {i: n for i, (_, n) in sold.items()},
                       held={i: h for i, (h, _) in sold.items()})
            got = {int(e[0]) for s in self.steps if id(s) not in had for e in ((s.get("need") or {}).get("items") or ())}
            self.missing |= set(sold) - got
        house = {r["item"]: held(r["item"], ("auction",)) for r in rows if r["pick"] == "auction"}
        if house:
            self.auction(house, rows, tag)
        for s in [s for s in self.steps if id(s) not in before and s.get("what") == "supplies"]:
            got = house if ":auction" in s["key"] else sold
            self.left[id(s)] = {int(i): got[int(i)][1] - got[int(i)][0] for i, _ in s["need"]["items"] if int(i) in got}
            self.ahead(s)
        bought = [s for s in self.steps if id(s) not in before and s.get("what") == "supplies"]
        visit = next((s for s in bought if ":auction" not in s["key"]), bought[0] if bought else None)
        if visit is not None:
            self.sell(self.steps.index(visit), tag or ":1", visit)
        for item in dict.fromkeys(r["item"] for r in rows if r["pick"] in ("grind", "gather")):
            if self.position(f"{self.key}:farm:{item}") is None:
                self.session(item, next(r for r in rows if r["item"] == item), self.target(item, ("grind", "gather")))

    def ahead(self, s):
        k = self.steps.index(s)
        prev, money, cost = self.steps[k - 1] if k else None, self.me.get("money"), s.get("cost") or 0
        if prev is None or money is None or not prev.get("at") or not s.get("at"):
            return
        if prev.get("inst") == s.get("inst") and math.dist(prev["at"][:2], s["at"][:2]) <= BATCH_YARDS:
            return
        for j in range(k - 1, -1, -1):
            e = self.steps[j]
            if id(e) in self.left and e.get("npc") == s.get("npc") and e.get("at") == s.get("at"):
                if sum(x.get("cost") or 0 for x in self.steps[:j + 1]) + cost > money:
                    return
                add, mine = self.left.pop(id(s)), self.left[id(e)]
                want, rows = {int(i): n for i, n in s["need"]["items"]}, {int(i): n for i, n in e["need"]["items"]}
                for i, n in add.items():
                    rows[i] = rows[i] + n if i in rows else want[i]
                    mine[i] = mine.get(i, 0) + n
                    for x in self.steps[j + 1:k]:
                        if id(x) in self.left:
                            x["need"]["items"] = [[a, b + n if int(a) == i else b] for a, b in x["need"]["items"]]
                e["need"] = {**e["need"], "items": [[i, rows[i]] for i in sorted(rows)]}
                if (e.get("cost") or 0) + cost:
                    e["cost"] = (e.get("cost") or 0) + cost
                    if "pay" in e["need"]:
                        e["need"]["pay"] = e["cost"]
                names = [(self.cd.item_name(i), mine[i]) for i in sorted(mine)]
                e["text"] = buy_line(names) if ":auction" in e["key"] else buy_line(names, e["npc"])
                for name in ("questName", "name"):
                    if name in e:
                        e[name] = e["text"]
                del self.steps[k]
                return

    def got(self):
        out = set()
        for s in self.steps:
            out |= {int(e[0]) for e in ((s.get("need") or {}).get("items") or ())}
            if s.get("kind") == "turnin" and s.get("want"):
                out.add(int(s["want"]))
        return out

    def auction(self, house, rows, tag):
        name = self.cd.item_name
        left = [(name(i), house[i][1] - house[i][0]) for i in sorted(house)]
        cost = sum(int(round(r["ways"]["auction"]["price"] * r["short"])) for r in rows
                   if r["item"] in house and r["pick"] == "auction")
        need = {"items": [[i, house[i][1]] for i in sorted(house)]}

        def make(n, p, *_):
            return self.c.chore("supplies", f"{self.key}:auction{tag}", buy_line(left), n, p, need, cost)
        at, _ = self.c.paid(self.steps, len(self.steps), self.c.errands.auctioneers(self.c.side), make, cost)
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
        if self.c.fit(self.steps, len(self.steps), [place], make) is None:
            self.steps.append(make(*place))


    def after(self, items):
        items = set(items)
        return max((k + 1 for k, s in enumerate(self.steps)
                    if items & {int(e[0]) for e in ((s.get("need") or {}).get("items") or ())}
                    or (s.get("kind") == "turnin" and s.get("want") in items)), default=0)

    def now(self, rec):
        return self.skill.get(rec["line"], 1 if rec["yours"] is None else rec["yours"])

    def reached(self, line, skill):
        key = next((k for to, k in self.up.get(line, ()) if to >= skill), None)
        at = None if key is None else self.position(key)
        return 0 if at is None else at + 1

    def lesson(self, rec, lo, kids):
        spell, name = rec["spell"], rec["profession"]
        key = f"{self.key}:recipe:{spell}"
        if rec["known"] or rec["how"] not in ("trainer", "item"):
            return lo
        if spell in self.taught:
            had = self.position(key)
            return lo if had is None else max(lo, had + 1)
        if rec["how"] == "trainer":
            at, _ = self.c.recipe(self.steps, lo, name, spell, key, rec["name"])
        else:
            pattern = next((p for p in rec["patterns"] if p in kids or self.carry.get(p)), rec["patterns"][0])
            at = self.c.here(self.steps, lo, "learn", key, f"Learn {rec['name']} by using {self.cd.item_name(pattern)} from your bags",
                             {"recipes": [spell]}, takes={"items": [pattern], "skills": [name]})
        if at is None:
            return None
        self.taught.add(spell)
        return at + 1

    def craft(self, i):
        r = self.rows[i]
        if not r["short"]:
            return True
        if r.get("level"):
            return self.climb(i)
        if r["pick"] != "craft":
            if r["pick"] is None:
                total = self.target(r["item"], (None,))
                self.wall(r["item"], words.say("both.craft.none", {"item": r["name"], "count": total - self.carry.get(r["item"], 0)}),
                          {"items": [[r["item"], total]]})
                return False
            return r["item"] not in self.missing
        under = [self.craft(j) for j in self.kids[i]]
        rec = r["recipe"]
        name, spell, line = rec["profession"], rec["spell"], rec["line"]
        if line in self.stopped:
            return False
        lo = self.profession(rec)
        if lo is None:
            return False
        if not rec["known"] and rec["how"] is None:
            self.wall(f"recipe:{spell}", words.say("both.craft.unlearnt", {"recipe": rec["name"]}), {"recipes": [spell]})
            return False
        if not rec["known"] and rec["skill"] is not None and rec["skill"] > self.now(rec):
            if line not in self.halted:
                self.wall(f"skill:{spell}", words.say("both.craft.skill", {"skill": name, "need": rec["skill"], "have": rec["yours"] or 0}),
                          {"skills": [[name, rec["skill"]]]})
            return False
        if not all(under):
            return False
        key = self.craft_key(i)
        if self.position(key) is not None:
            return True
        kids = [self.rows[j]["item"] for j in self.kids[i]]
        lo = max(lo, self.after(kids), self.reached(line, rec["skill"] or 0) if not rec["known"] else 0)
        lo = self.lesson(rec, lo, kids)
        if lo is None:
            return False
        mine = [j for j, x in enumerate(self.rows) if x["item"] == r["item"] and x["pick"] == "craft" and not x.get("level")]
        short = sum(self.rows[j]["short"] for j in mine)
        at = self.c.here(self.steps, lo, "craft", key, craft_text(r["name"], short, rec["station"]),
                         {"items": [[r["item"], self.held(lo)[r["item"]] + short]]},
                         takes={"items": kids, "recipes": [spell], "skills": [name], "uses": self.uses(mine)})
        return at is not None

    def uses(self, crafts):
        out = collections.Counter()
        for i in crafts:
            for j in self.kids[i]:
                out[self.rows[j]["item"]] += self.rows[j]["need"]
        return [[i, n] for i, n in sorted(out.items())]

    def climb(self, i):
        r = self.rows[i]
        seg, rec = r["level"], r["recipe"]
        line, name, spell = rec["line"], rec["profession"], rec["spell"]
        if line in self.stopped:
            return False
        under = [self.craft(j) for j in self.kids[i]]
        lo = self.profession(rec)
        if lo is None or not all(under):
            self.stopped.add(line)
            return False
        lo = max(lo, self.reached(line, seg["from"]))
        rank = seg.get("train")
        if rank:
            at, _ = self.c.learn(self.steps, {"name": name, "line": line, "rank": rank}, False,
                                 lo=max(lo, self.reached(line, rank["skill"] or 0)))
            if at is None:
                self.stopped.add(line)
                return False
            lo = max(lo, at + 1)
        kids = [self.rows[j]["item"] for j in self.kids[i]]
        lo = self.lesson(rec, max(lo, self.after(kids)), kids)
        if lo is None:
            self.stopped.add(line)
            return False
        key = self.craft_key(i)
        at = self.c.here(self.steps, lo, "craft", key, level_text(r["name"], seg, name, rec["station"]), {"skills": [[name, seg["to"]]]},
                         takes={"items": kids, "recipes": [spell], "skills": [name], "uses": self.uses([i])})
        if at is None:
            self.stopped.add(line)
            return False
        self.made.append((key, r["item"], r["need"]))
        self.steps[at]["made"] = [r["item"], self.held(at)[r["item"]] + r["need"], r["need"]]
        self.skill[line] = seg["to"]
        self.up.setdefault(line, []).append((seg["to"], key))
        return True

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
        return self.position(f"{profepics.PREFIX}{line}:learn") + 1
