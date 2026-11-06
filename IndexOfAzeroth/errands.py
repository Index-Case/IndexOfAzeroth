# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import director_rules as rules
from layers import sells, serving
from plansteps import FAR, cheapest, gap, spot
from ticks import need_met
import words

SOON = 6
HERE = 120.0
TRAIN_CLOSE = 150.0
TRAIN_HORIZON = 20
TRAIN_WITHIN = 8
BAGS_LOW = 2
DURABILITY_LOW = 25
FLIGHT_NEAR = 150.0
HUB_NEAR = 250.0
MERCHANT = {"general", "food", "ammo", "reagents", "poisons", "trade", "bags", "weaponvendor", "armor", "repair"}
RESTOCK = {"water": ("water", {"food"}, 10), "ammo": ("ammo", {"ammo"}, 400), "ankh": ("Ankhs", {"reagents"}, 1),
           "camp": ("wood for campfire kits", MERCHANT, rules.plain(rules.RESTOCK)["camp_stock"])}
GRADED = ("ammo", "water")
COUNTED = {"camp"}
CAMP = rules.plain(rules.RESTOCK)
KEEP = ("train:", "bind:", "flightpath:")
TODO_LINES = {"restock:water": "restock:water", "restock:ammo": "restock:ammo", "restock:ankh": "restock:ankhs",
              "restock:camp": "restock:camp", "repair": "character:repair"}
HIDDEN_NAMES = {"restock:water": "Buy water", "restock:ammo": "Buy ammo", "restock:ankh": "Buy Ankhs",
                "restock:camp": rules.line("heads", "camp_restock"), "repair": "Repair your gear"}
MADE_BY = {"water": "Conjure Water"}
ANY_NPC = ("sell", "repair", "restock", "train", "supplies")
LAND_NEAR = 150.0
ADDON_CHORES = {"train": 1, "sell": 2, "repair": 4, "restock": 8}
KINDS = ("repair", "sell", "restock", "train", "bind", "flightpath")


def addon_chores(mask):
    return {k for k, b in ADDON_CHORES.items() if int(mask or 0) & b}


def restock_words(thing, item, npc):
    return words.say("both.restock.buy", {"item": item or RESTOCK[thing][0], "npc": npc})


def chore_buy(sv, thing, me):
    buy = Errands.restock_buy(sv.get("prices") or {}, thing, me.get("level") or 1, me) if sv else None
    return buy[0] if buy else None


def own_chore_step(c, name, buy=None, item=None):
    who = name or "the vendor"
    what = c.get("what")
    if what == "train":
        text = f"Train at {name or 'your trainer'}"
    elif what == "restock" and c.get("thing") == "camp" and buy:
        text = rules.line("heads", "camp_buy", {"buy": buy["words"], "npc": who})
    elif what == "restock":
        text = restock_words(c["thing"], item, who) if c.get("thing") in RESTOCK else f"Buy supplies at {who}"
    elif c.get("junk"):
        text = f"Sell your junk at {who}, then train"
    else:
        text = f"{'Sell and repair' if c.get('both') else 'Sell' if what == 'sell' else 'Repair'} at {who}"
    return {"k": "S", "ids": [], "what": what, "text": text, "name": text, "npc": name, "inst": c.get("inst"),
            "at": list(c.get("at") or ()), **({"cost": c["cost"]} if c.get("cost") else {}),
            **({"min": c["level"]} if c.get("level") else {}), "own": True}


def planned_kinds(only, owned):
    if not owned:
        return only
    return set(KINDS if only is None else only) - set(owned)
LAND_REACH = 800.0


def landed_pick(also, here):
    best, near = None, LAND_NEAR
    for e in also or ():
        land = e.get("l")
        if not here or not land or land[0] != here[0]:
            continue
        d = math.hypot(land[1] - here[1], land[2] - here[2])
        if d <= near and (best is None or d < near):
            best, near = e, d
    return best


def teaches_all(teaches, npc, spells):
    has = (teaches or {}).get(npc)
    return has is None or set(spells) <= set(has)


def learnable(schedule, known, race, upto):
    known = set(known)
    by_id = {s["id"]: s for v in schedule.values() for s in v["spells"]}
    for sid in list(known):
        s = by_id.get(sid)
        while s and s.get("prev") and s["prev"] not in known:
            known.add(s["prev"])
            s = by_id.get(s["prev"])
    bit = race or 0
    out = []
    for lv in sorted(int(k) for k in schedule):
        if lv > upto:
            break
        for s in schedule[str(lv)]["spells"]:
            if s["id"] in known or (s.get("races") and not s["races"] & bit) or s.get("trainer") is False:
                continue
            if (s.get("prev") and s["prev"] not in known) or (s.get("needs") and not known & set(s["needs"])):
                continue
            out.append((lv, s))
    return out


def spell_states(schedule, known, race, level):
    now = {s["id"] for _, s in learnable(schedule, known or (), race, level)} if known is not None else set()
    have = set(known or ())
    by_id = {s["id"]: s for v in schedule.values() for s in v["spells"]}
    for sid in list(have):
        s = by_id.get(sid)
        while s and s.get("prev") and s["prev"] not in have:
            have.add(s["prev"])
            s = by_id.get(s["prev"])
    bit = race or 0
    out = {}
    for lv, v in schedule.items():
        for s in v["spells"]:
            if s.get("pet") and s["id"] not in have:
                ready = int(lv) <= level and (s["pet"] != "trainer" or not s.get("prev") or s["prev"] in have)
                out[s["id"]] = "unknown" if known is None and int(lv) <= level else "learn" if ready else "later"
                continue
            out[s["id"]] = ("known" if s["id"] in have else "race" if s.get("races") and not s["races"] & bit
                            else "talent" if s.get("needs") and not have & set(s["needs"])
                            else "elsewhere" if s.get("trainer") is False
                            else "learn" if s["id"] in now
                            else "unknown" if known is None and int(lv) <= level else "later")
    return out


def trained_through(me, level):
    schedule, known, seen = me.get("schedule"), me.get("known_spells"), me.get("trained")
    if schedule and known is not None:
        todo = learnable(schedule, known, me.get("race"), level)
        return max(todo[0][0] - 1 if todo else level, seen or 0)
    return seen or None


def hidden_note(what, key):
    return {"what": what, "key": key, "hidden": True, "text": HIDDEN_NAMES[key]}


def makes(me, warning):
    name, schedule, known = MADE_BY.get(warning), me.get("schedule"), me.get("known_spells")
    if not name or not schedule or not known:
        return False
    ids = {s["id"] for row in schedule.values() for s in row.get("spells") or () if s.get("name") == name}
    return bool(ids & set(known))


def better_grade(world, thing, me, map_id, fx, fy):
    if (thing == "ammo" and not me.get("ammo_kind")) or makes(me, thing):
        return None
    here = world.geo.to_world(map_id, fx, fy)
    if not here:
        return None
    level, held, side = me.get("level") or 1, (me.get("grades") or {}).get(thing) or 0, me.get("faction") or ""
    best = None
    for sv, _, spots in serving(world.services, world.geo, side, RESTOCK[thing][1], walking=world.walking(),
                                walled=world.walled(side)):
        row = Errands.restock_row(sv.get("prices") or {}, thing, level, me)
        if row and row[0] > held and any(s[2] == here[2] for s in spots) and \
                (best is None or (row[0], -row[1]) > (best[0], -best[1])):
            best = row
    near = best and world.nearest(map_id, fx, fy, side, RESTOCK[thing][1], goods=[best[2]])
    return {"item": best[2], "npc": near} if near else None


def camp_buy(me, camp):
    camps, wood = me.get("camps"), me.get("camp_wood")
    if not camp_low(me) or not camp:
        return None
    fire = next((f for f in camp.get("fires") or () if f[2] == wood), None)
    if fire is None:
        return None
    info = {e[0]: e for e in camp.get("items") or ()}
    tool = me.get("camp_tool") or None
    n = (CAMP["camp_stock"] - camps) * fire[3]
    have = ((me.get("game") or {}).get("items") or {}).get(wood, 0)
    name = lambda i: info[i][1] if i in info else f"item {i}"
    price = lambda i: info[i][2] if i in info else 0
    words = (rules.line("heads", "camp_wood_tool", {"n": n, "wood": name(wood), "tool": name(tool)}) if tool
             else rules.line("heads", "camp_wood", {"n": n, "wood": name(wood)}))
    return {"wood": wood, "n": n, "tool": tool, "items": [wood] + ([tool] if tool else []),
            "cost": n * price(wood) + (price(tool) if tool else 0), "words": words,
            "need": {"items": [[wood, have + n]] + ([[tool, 1]] if tool else [])}}


def camp_low(me):
    camps = me.get("camps")
    return camps is not None and me.get("camp_wood") is not None and camps < CAMP["camp_low"]


def low_on(me):
    return [w for w in me.get("warnings") or () if w in RESTOCK and w not in COUNTED] + (["camp"] if camp_low(me) else [])


def shows_done(step, me):
    what, need = step.get("what"), step.get("need") or {}
    declared = need_met(need, me.get("game"))
    if declared is False:
        return False
    level = me.get("level") or 1
    if what == "wall":
        return declared is True or (declared is None and need.get("level") is not None and level >= need["level"])
    if what == "bind":
        bind, here = need.get("bind"), me.get("bind") or None
        return here is not None and (here in bind if isinstance(bind, list) else bind is not None and here == bind)
    if what == "flightpath":
        known = me.get("known")
        return None if known is None else need.get("node") in set(known)
    if what == "train":
        spells, known = need.get("spells") or (), me.get("known_spells")
        if spells:
            return None if known is None else bool(set(spells) & set(known))
        return need.get("level") is not None and (me.get("trained") or 0) >= need["level"]
    if what in ("repair", "sell"):
        if me.get("bag_free") is None and me.get("durability") is None:
            return None
        worn = not need.get("durability") or (100 if me.get("durability") is None else me["durability"]) >= need["durability"]
        room = not need.get("bags") or (me.get("bag_free") or 0) >= need["bags"] or me.get("junk") == 0
        sold = not need.get("junk") or me.get("junk") == 0
        return worn and room and sold
    if what == "restock" and need.get("warning"):
        warnings = me.get("warnings")
        return None if warnings is None else not set(need["warning"]) & set(warnings)
    return declared is True


def step_money(s):
    if s.get("kind") == "turnin":
        return s.get("cash") or 0
    return (s.get("gain") or 0) - (s.get("spend", s.get("cost")) or 0)


def in_hand(steps, i):
    q = steps[i - 1].get("quest") if 0 < i <= len(steps) and steps[i - 1].get("kind") == "objective" else None
    j = i
    while q is not None and j < len(steps) and steps[j].get("kind") == "objective" and steps[j].get("quest") == q:
        j += 1
    if q is not None and j < len(steps) and steps[j].get("kind") == "turnin" and steps[j].get("quest") == q:
        j += 1
    return j


def money_before(steps, i, have):
    return None if have is None else have + sum(step_money(s) for s in steps[:i])


def pays(money, cost):
    if not cost:
        return True
    return None if money is None else money >= cost


def money_note(what, why, doing, cost, have, brief):
    if why == "unknown":
        return {"what": what, "text": f"{doing} waits for the game to say your money", "brief": f"{brief}, your money not read yet"}
    return {"what": what, "text": f"{doing} costs {coins(cost)}, and you have {coins(have)}",
            "brief": f"{brief}, {coins(max(cost - have, 0))} short"}


def restock_note(warning, why, doing, cost, have):
    thing = RESTOCK[warning][0]
    if why == "far":
        return {"what": "restock", "text": rules.line("heads", "no_vendor", {"thing": thing}), "brief": f"{thing}, no vendor in reach"}
    return money_note("restock", why, doing, cost, have, thing)


def paid_by(steps, have, price, lo=0):
    m, k = money_before(steps, lo, have), lo
    while pays(m, price) is not True:
        if m is None or k >= len(steps):
            return None
        m += step_money(steps[k])
        k += 1
    return k


def coins(copper):
    copper = int(round(copper))
    g, s, c = copper // 10000, copper // 100 % 100, copper % 100
    return " ".join(f"{v}{u}" for v, u in ((g, "g"), (s, "s"), (c, "c")) if v) or "0c"


class Errands:
    def __init__(self, services, geo, inns=(), flights=(), trainer_levels=None, trainer_costs=None, teaches=None,
                 game_prices=None, walkers=(), sellers=None, camp=None, item_name=None, walled=None):
        self.services, self.geo, self.inns, self.flights = services, geo, list(inns), list(flights)
        self.sellers, self.camp = sellers, camp or (lambda: None)
        self.item_name = item_name or (lambda item: None)
        self.walled = walled or (lambda side: frozenset())
        self.trainer_levels, self.trainer_costs = trainer_levels or {}, trainer_costs or {}
        self.teaches = teaches if teaches is not None else {}
        self.game_prices = game_prices if game_prices is not None else {}
        self.walkers = dict(walkers) if isinstance(walkers, dict) else dict.fromkeys(walkers, math.inf)
        self.places_cache = {}

    def places(self, cats, faction, detail=None, ids=False, keep=None):
        walled = self.walled(faction)
        key = (tuple(sorted(cats)), faction, detail, ids, walled)
        if keep is None and key in self.places_cache:
            return self.places_cache[key]
        area_map = getattr(self.geo, "area_map", None)
        out = [(sv["n"], (inst, north, west, sv.get("z"), area_map.get(str(area)) if area_map else None), sv.get("prices") or {})
               + ((sv.get("id"),) if ids else ())
               for sv, _, spots in serving(self.services, self.geo, faction, cats, detail, keep, self.walkers, walled)
               for north, west, inst, area in spots]
        if keep is None:
            self.places_cache[key] = out
        return out

    def vendors_of(self, items, faction, sold):
        by = {}
        for p in self.places(MERCHANT, faction, ids=True):
            mine = [i for i in items if p[3] in sold.get(i, ())]
            if mine:
                by.setdefault(len(mine), []).append((p, mine))
        return [by[n] for n in sorted(by, reverse=True)]

    @staticmethod
    def near_route(places, spots, most=12):
        spots = [s for s in spots if s]
        if not spots:
            return places[:most]
        return sorted(places, key=lambda p: min(gap(s, p[1]) for s in spots))[:most]

    def fit(self, steps, lo, hi, places, anchor, make, ok=None):
        if lo <= 0 and anchor:
            here = [p for p in places if gap(anchor, p[1]) <= HERE and (not ok or ok(0, p))]
            if here:
                steps.insert(0, make(*min(here, key=lambda p: gap(anchor, p[1]))))
                return 0
        window = [anchor] + [spot(s) for s in steps[max(0, lo - 1):min(hi, len(steps)) + 1]]
        places = self.near_route(places, window)
        best = cheapest(steps, [p[1] for p in places], max(0, lo), min(hi, len(steps)), anchor,
                        ok=ok and (lambda i, k: ok(i, places[k])))
        if best is None or best[0] >= FAR / 2:
            return None
        steps.insert(best[1], make(*places[best[2]]))
        return best[1]

    def fit_paid(self, steps, lo, hi, places, anchor, make, cost, have, fit=None):
        fit = fit or self.fit
        price = cost if callable(cost) else (lambda i, p: cost)
        at = fit(steps, lo, hi, places, anchor, make, ok=lambda i, p: pays(money_before(steps, i, have), price(i, p)) is True)
        if at is not None:
            return at, None
        if fit(list(steps), lo, hi, places, anchor, lambda *_: {}, ok=None) is None:
            return None, "far"
        return None, "unknown" if have is None else "short"

    def spell_price(self, schedule, cid):
        game = self.game_prices.get(cid) or {}
        costs = self.trainer_costs.get(cid) or {}

        def price(lv, s):
            if s["id"] in game:
                return game[s["id"]]
            if s.get("cost") is not None:
                return s["cost"]
            v = schedule[str(lv)]
            n = sum(1 for x in v["spells"] if not x.get("races") and not x.get("needs")) or 1
            return (costs.get(str(lv)) or v.get("cost") or 0) / n
        return price

    def plan_training(self, steps, me, top, at_level, money_at, faction, anchor, skipped_upto, notes, junk=0):
        schedule = me["schedule"]
        known, todo = set(me["known_spells"]), []
        while True:
            more = [(lv, s) for lv, s in learnable(schedule, known, me.get("race"), top) if lv > skipped_upto and s["id"] not in known]
            if not more:
                break
            todo += more
            known |= {s["id"] for _, s in more}
        trainers = self.places({"class"}, faction, detail=me.get("class_id"), ids=True)
        if not trainers or not todo:
            return
        todo.sort(key=lambda e: (e[0], not e[1].get("dmg")))
        price = self.spell_price(schedule, str(me.get("class_id")))
        listed, have_now = set(), set(me["known_spells"])
        known = {}

        def offer(i):
            key = ("offer", i, len(steps))
            out = known.get(key)
            if out is not None:
                return out
            out, ids, level = [], set(), at_level(i)
            for lv, s in todo:
                prev = s.get("prev")
                if s["id"] not in listed and lv <= level and (not prev or prev in have_now or prev in listed or prev in ids):
                    out.append((lv, s))
                    ids.add(s["id"])
            known[key] = out
            return out

        def money(j):
            key = ("money", j, len(steps))
            if key not in known:
                known[key] = money_at(j)
            return known[key]

        def teaches(place, spells):
            return teaches_all(self.teaches, place[3], [s["id"] for _, s in spells])

        def can_pay(j):
            o = offer(j)
            return bool(o) and pays(money(j), min(price(lv, s) for lv, s in o)) is True

        def pays_all(j):
            return pays(money(j), sum(price(lv, s) for lv, s in offer(j))) is True

        def passing(lo, hi, want):
            for j in range(lo, min(hi, len(steps)) + 1):
                if not want(j):
                    continue
                prev = next((spot(s) for s in reversed(steps[:j]) if spot(s)), anchor)
                nxt = next((spot(s) for s in steps[j:] if spot(s)), None)
                spells = offer(j)
                by = [(gap(prev, t[1]) + (gap(t[1], nxt) - gap(prev, nxt) if nxt else 0.0), t) for t in trainers if teaches(t, spells)]
                by = [b for b in by if b[0] <= TRAIN_CLOSE]
                if by:
                    steps.insert(j, make(*min(by, key=lambda b: b[0])[1]))
                    return j
            return None
        make = lambda n, p, *_: self.step("train", "train", f"Train at {n}", n, p, {})
        unplaced = False
        sold = None if junk > 0 and not any(s.get("what") == "sell" and s.get("gain") for s in steps) else False
        named = False
        sell = lambda n, p, *_: {**self.step("sell", "sell", f"Sell your junk at {n}", n, p, {"junk": True}), "gain": junk}
        i = 0
        while i <= len(steps):
            if not can_pay(i):
                o = offer(i)
                if sold is None and o and money(i) is not None and pays(money(i) + junk, min(price(lv, s) for lv, s in o)):
                    at = self.fit(steps, i, i + TRAIN_WITHIN, self.places(MERCHANT, faction), anchor, sell)
                    if at is not None:
                        sold = steps[at]
                        known.clear()
                        continue
                i += 1
                continue
            spells = offer(i)
            teachers = [t for t in trainers if teaches(t, spells)]
            where = next((spot(s) for s in reversed(steps[:i]) if spot(s)), anchor)
            close = [t for t in teachers if gap(where, t[1]) <= TRAIN_CLOSE]
            if close:
                at = self.fit(steps, i, in_hand(steps, i), close, anchor, make, ok=lambda j, p: can_pay(j))
            else:
                at = passing(i, i + TRAIN_HORIZON, lambda j: can_pay(j) and pays_all(j))
                if at is None:
                    at = passing(i, i + TRAIN_HORIZON, can_pay)
                if at is None:
                    at = self.fit(steps, i, i + TRAIN_WITHIN, teachers, anchor, make, ok=lambda j, p: can_pay(j) and teaches(p, offer(j)))
            if at is None:
                unplaced = True
                i += 1
                continue
            spells = offer(at)
            names = list(dict.fromkeys(s["name"] for _, s in spells))
            total, have, last = sum(price(lv, s) for lv, s in spells), money_at(at), max(lv for lv, _ in spells)
            what = (" and ".join(names) if len(names) <= 2 else f"{', '.join(names[:-1])} and {names[-1]}" if len(names) <= 4
                    else f"{', '.join(names[:3])} and {len(names) - 3} more")
            step = steps[at]
            step.update(key=f"train:{last}", need={"spells": [s["id"] for _, s in spells], "level": last},
                        text=f"Train at {step['npc']}: {what}",
                        why=rules.say("train_way_one" if len(names) == 1 else "train_way", {"spells": what}),
                        **({"cost": round(total)} if total else {}))
            step["questName"] = step["text"]
            if sold and not named and any(x is sold for x in steps[:at]):
                sold.update(text=f"Sell your junk at {sold['npc']}, then train: {what}")
                sold["questName"] = sold["text"]
                named = True
            if have is not None and have < total:
                have, spend = max(have, 0), 0
                for p in sorted(price(lv, s) for lv, s in spells):
                    if spend + p > have:
                        break
                    spend += p
                step.update(short=round(have), spend=round(spend))
            listed |= {s["id"] for _, s in spells}
            known.clear()
            i = at + 1
        if sold and not named:
            steps[:] = [x for x in steps if x is not sold]
        if not listed and unplaced:
            notes.append({"what": "train", "text": f"No trainer of yours on this side of the world teaches {todo[0][1]['name']}",
                          "brief": f"{todo[0][1]['name']}, no trainer this side"})
        elif not listed and money_at(0) is None:
            lv, s = min(todo, key=lambda e: price(*e))
            notes.append(money_note("train", "unknown", f"Training {s['name']}", price(lv, s), None, s["name"]))
        elif not listed:
            lv, s = min(todo, key=lambda e: price(*e))
            notes.append({"what": "train", "text": f"Training {s['name']} costs {coins(price(lv, s))}, which is more than the plan's "
                                                   f"quests bring you", "brief": f"{s['name']}, costs {coins(price(lv, s))}"})

    @staticmethod
    def step(what, key, text, name, place, need, cost=None):
        return {"kind": "errand", "what": what, "key": key, "quest": None, "questName": text, "text": text, "npc": name,
                "inst": place[0], "at": [round(place[1], 1), round(place[2], 1)] + ([round(place[3], 1)] if place[3] is not None else []),
                "need": need, **({"cost": int(round(cost))} if cost else {}),
                **({"map": int(place[4])} if len(place) > 4 and place[4] else {})}

    def serving_step(self, step, me):
        what, faction, level = step.get("what"), me.get("faction") or "", me.get("level") or 1
        if what not in ANY_NPC:
            return None
        if what == "supplies":
            items = [int(i) for i, _ in (step.get("need") or {}).get("items") or ()]
            if not items or self.sellers is None:
                return None
            sold = [self.sellers(i) for i in items]
            return [p for p in self.places(MERCHANT, faction, ids=True) if all(p[3] in s for s in sold)]
        if what in ("sell", "repair"):
            return self.places({"repair"} if what == "repair" else MERCHANT, faction, ids=True)
        warning = (step.get("key") or "").partition(":")[2]
        if what == "restock" and warning in COUNTED:
            items = [int(i) for i, _ in (step.get("need") or {}).get("items") or ()]
            return self.places(RESTOCK[warning][1], faction, ids=True, keep=lambda sv, _: sells(sv, items))
        if what == "restock" and warning in RESTOCK:
            return self.places(RESTOCK[warning][1], faction, ids=True, keep=lambda sv, _: self.restock_buy(
                sv.get("prices") or {}, warning, level, me) is not None)
        if what == "train":
            spells = set((step.get("need") or {}).get("spells") or ())
            return [t for t in self.places({"class"}, faction, detail=me.get("class_id"), ids=True)
                    if teaches_all(self.teaches, t[3], spells)]
        return None

    def moved_to(self, step, place, me):
        name, at, prices = place[0], place[1], place[2]
        cost = step.get("cost")
        text = (step.get("text") or "").replace(f" at {step.get('npc')}", f" at {name}", 1)
        warning = (step.get("key") or "").partition(":")[2]
        if step.get("what") == "restock" and warning not in COUNTED:
            buy = self.restock_buy(prices, warning, me.get("level") or 1, me)
            if buy is not None:
                cost, text = buy[1] * RESTOCK[warning][2], self.restock_text(warning, buy[0], name)
        rest = {k: v for k, v in step.items() if k not in ("npc", "inst", "at", "map", "zone", "cost", "text", "questName")}
        return {**rest, **self.step(step["what"], step["key"], text, name, at, step.get("need") or {}, cost)}

    def camp_restock(self, steps, me, faction, anchor, money_at, notes):
        buy = camp_buy(me, self.camp())
        if buy is None:
            return
        sellers = self.places(RESTOCK["camp"][1], faction, keep=lambda sv, _: sells(sv, buy["items"]))
        _, why = self.fit_paid(steps, 0, SOON, sellers, anchor,
                               lambda n, p, _: self.step("restock", "restock:camp", rules.line("heads", "camp_buy", {"buy": buy["words"], "npc": n}),
                                                         n, p, buy["need"], buy["cost"]),
                               buy["cost"], me.get("money"))
        if why == "short" and sellers:
            notes.append({"what": "restock", "text": rules.line("heads", "camp_short", {
                "buy": buy["words"], "cost": coins(buy["cost"]), "have": coins(me["money"])})})
        elif why and sellers:
            notes.append(restock_note("camp", why, f"Buying {buy['words']}", buy["cost"], me.get("money")))

    @staticmethod
    def restock_buy(prices, thing, level, me):
        if thing == "ankh":
            return (None, prices["ankh"]) if prices.get("ankh") is not None else None
        best = Errands.restock_row(prices, thing, level, me)
        return (best[2], best[1]) if best else None

    @staticmethod
    def restock_row(prices, thing, level, me):
        kind, held = me.get("ammo_kind"), (me.get("grades") or {}).get(thing) or 0
        rows = [r for r in prices.get(thing) or ()
                if held <= r[0] <= level and (thing != "ammo" or not kind or r[3] == kind)]
        return max(rows, key=lambda r: (r[0], -r[1]), default=None)

    def restock_text(self, warning, item, npc):
        return restock_words(warning, self.item_name(item) if item else None, npc)

    def plan(self, steps, levels, me, anchor=None, only=None):
        steps, notes = list(steps), []
        want = lambda kind: only is None or kind in only
        silenced = set(me.get("silenced") or ())
        never = lambda key: TODO_LINES.get(key) in silenced
        level = me.get("level") or 1
        if levels:
            levels = list(levels)
        else:
            levels, top = [], level
            for s in steps:
                top = max(top, s.get("lv", level))
                levels.append(top)
            levels.append(top)
        faction = me.get("faction") or ""
        skipped = me.get("skipped") or {}

        def gone(key):
            return key in skipped and (key.startswith(KEEP) or skipped[key] == level)

        def at_level(i):
            quests = sum(1 for s in steps[:i] if s.get("kind") != "errand")
            return levels[min(quests, len(levels) - 1)]

        def money_at(i):
            return money_before(steps, i, me.get("money"))
        junk = me.get("junk_value") or 0

        repair = (want("repair") and me.get("durability") is not None and me["durability"] <= DURABILITY_LOW
                  and not gone("repair"))
        sell = (want("sell") and me.get("bag_free") is not None and me["bag_free"] <= BAGS_LOW and not gone("sell")
                and me.get("junk") != 0)
        if repair and never("repair"):
            notes.append(hidden_note("repair", "repair"))
            repair = False
        if repair and me.get("money") == 0:
            notes.append({"what": "repair", "text": "Your gear is worn and you have no money to repair it", "brief": "repair, no money"})
            repair = False
        if repair or sell:
            what = "repair" if repair else "sell"
            said = " and ".join(w for w, on in (("Sell", sell), ("repair", repair)) if on)
            need = {k: v for k, v in (("durability", DURABILITY_LOW + 1 if repair else None), ("bags", BAGS_LOW + 1 if sell else None)) if v}
            self.fit(steps, 0, SOON, self.places({"repair"} if repair else MERCHANT, faction), anchor,
                     lambda n, p, _: {**self.step(what, what, f"{said[0].upper()}{said[1:]} at {n}", n, p, need),
                                      **({"gain": junk} if sell and junk else {})})
        for warning in low_on(me):
            if gone(f"restock:{warning}") or not want("restock") or makes(me, warning):
                continue
            thing, cats, units = RESTOCK[warning]
            if never(f"restock:{warning}"):
                notes.append(hidden_note("restock", f"restock:{warning}"))
                continue
            if warning in COUNTED:
                self.camp_restock(steps, me, faction, anchor, money_at, notes)
                continue
            buy = lambda prices, lv, w=warning: self.restock_buy(prices, w, lv, me)
            price = lambda prices, lv: (buy(prices, lv) or (None, None))[1]
            cost = lambda i, p: (price(p[2], at_level(i)) or 0) * units
            sellers = self.places(cats, faction, keep=lambda sv, _: buy(sv.get("prices") or {}, level) is not None)
            _, why = self.fit_paid(steps, 0, SOON, sellers, anchor,
                                   lambda n, p, prices, w=warning: self.step(
                                       "restock", f"restock:{w}", self.restock_text(w, buy(prices, level)[0], n), n, p,
                                       {"warning": [w]}, buy(prices, level)[1] * units),
                                   cost, me.get("money"))
            if why and sellers:
                cheapest = min(price(p[2], level) for p in sellers)
                notes.append(restock_note(warning, why, f"Buying {units} {thing}", cheapest * units, me.get("money")))

        skipped_upto = max((int(k[6:]) for k in skipped if k.startswith("train:") and k[6:].isdigit()), default=0)
        if not want("train"):
            trained = max(levels)
        elif me.get("schedule") and me.get("known_spells") is not None:
            self.plan_training(steps, me, max(levels), at_level, money_at, faction, anchor, skipped_upto, notes,
                               junk if want("sell") and not gone("sell") and me.get("junk") != 0 else 0)
            trained = max(levels)
        else:
            trained = trained_through(me, level)
        if trained is None:
            notes.append({"what": "train", "text": "Training waits for the game to say which spells you know",
                          "brief": "training, your spells not read yet"})
            trained = max(levels)
        costs = self.trainer_costs.get(str(me.get("class_id"))) or {}
        todo = [lv for lv in self.trainer_levels.get(str(me.get("class_id")), ()) if max(trained, skipped_upto) < lv <= max(levels)]
        trainers = self.places({"class"}, faction, detail=me.get("class_id")) if todo else []
        spend = lambda i: sum(costs.get(str(lv), 0) for lv in todo if lv <= at_level(i))
        while todo and trainers:
            reach = next((i for i in range(len(steps) + 1) if at_level(i) >= todo[0]), None)
            if reach is None:
                break
            at, paid = None, False
            make = lambda n, p, _: self.step("train", "train", f"Train at {n}", n, p, {})
            for lo in range(reach, len(steps) + 1):
                if pays(money_at(lo), spend(lo)) is True:
                    paid = True
                    where = next((spot(s) for s in reversed(steps[:lo]) if spot(s)), anchor)
                    close = [t for t in trainers if gap(where, t[1]) <= TRAIN_CLOSE]
                    at = (self.fit(steps, lo, lo, close, anchor, make) if close else
                          self.fit(steps, lo, lo + TRAIN_WITHIN, trainers, anchor, make, ok=lambda i, p: pays(money_at(i), spend(i)) is True))
                    if at is not None:
                        break
            if at is None and paid:
                notes.append({"what": "train", "text": f"No trainer of yours on this side of the world teaches your level {todo[0]} spells",
                              "brief": f"level {todo[0]} spells, no trainer this side"})
                break
            if at is None and money_at(0) is None:
                notes.append(money_note("train", "unknown", f"Training your level {todo[0]} spells", spend(len(steps)), None,
                                        f"level {todo[0]} spells"))
                break
            if at is None:
                notes.append({"what": "train", "text": f"Your level {todo[0]} spells cost {coins(spend(len(steps)))} to train, which is "
                                                       f"more than the plan's quests bring you",
                              "brief": f"level {todo[0]} spells, cost {coins(spend(len(steps)))}"})
                break
            got, paid = at_level(at), spend(at)
            steps[at].update(key=f"train:{got}", need={"level": got}, text=f"Train at {steps[at]['npc']}: level {got} spells",
                             **({"cost": paid} if paid else {}))
            steps[at]["questName"] = steps[at]["text"]
            todo = [lv for lv in todo if lv > got]


        known = set(me.get("known") or ())
        masters = self.places({"flight"}, faction)
        for node in self.flights if want("flightpath") else ():
            if node["id"] in known or node.get("side") not in (None, faction) or gone(f"flightpath:{node['id']}"):
                continue
            nspot = (node["map"], node["at"][0], node["at"][1])
            k = next((k for k, s in enumerate(steps) if spot(s) and s.get("kind") != "errand" and gap(spot(s), nspot) <= FLIGHT_NEAR), None)
            if k is None:
                continue
            master = min(masters, key=lambda m: gap(m[1], nspot), default=None)
            if not master or gap(master[1], nspot) > 60:
                continue
            steps.insert(k + 1, self.step("flightpath", f"flightpath:{node['id']}", f"Learn the flight path at {node['name']}",
                                          master[0], master[1], {"node": node["id"], "name": node["name"]}))

        steps = [s for s in steps if s.get("kind") != "errand" or shows_done(s, me) is not True]
        for s in steps:
            if s.get("kind") == "errand" and (s.get("need") or {}).get("level"):
                s["min"] = s["need"]["level"]
        return steps, notes
