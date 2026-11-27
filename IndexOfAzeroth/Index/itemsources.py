# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

from errands import vendor_price
import farmspots
from facts import MAX_LEVEL
import gamedata
import layers
from mapzones import world_pos
import profepics

QUEST_ABOVE = 4
GATHER_LAYERS = {"mining": "Mining", "herbalism": "Herbalism"}
SKINNING = "Skinning"
DROPPERS_MOST = 10
SEC = 6
RESPAWN = 7
MOB = 10
RANK = 3
COUNT_ON = 0.05

_rewards = None


def reward_index(book):
    global _rewards
    got = _rewards
    if got is None or got[0] is not book:
        index = {}
        for qid, q in book.quests.items():
            r = q.get("rewards") or {}
            for item in {*(r.get("choice") or ()), *(r.get("items") or ())}:
                index.setdefault(int(item), []).append(qid)
        got = _rewards = (book, index)
    return got[1]


def nearest_spot(rows, here):
    spots = [(inst, r) for inst, rs in rows.items() for r in rs]
    if not spots:
        return None
    if not here:
        return spots[0]
    return min(spots, key=lambda p: (p[0] != here[0], math.hypot(p[1][0] - here[1], p[1][1] - here[2])))


class Lookup:

    def __init__(self, farm, me, plan, rewards, pd, seller, auction, auctioneer=None, travel=None, dungeons=()):
        self.farm, self.me, self.plan, self.rewards, self.pd = farm, me, plan, rewards, pd
        self.seller, self.auction, self._auctioneer, self._house = seller, auction, auctioneer or (lambda: None), ()
        self.travel, self.dungeons, self._loot = travel, dungeons, None

    def auctioneer(self):
        if self._house == ():
            self._house = self._auctioneer()
        return self._house


    def gathers(self):
        profs = (self.me.get("state") or {}).get("profs")
        return None if profs is None else {layer for layer, name in GATHER_LAYERS.items() if name in profs}

    def nodes(self, item):
        can = self.gathers()
        return [(layer, node) for layer, node in self.farm.gather_nodes(item, self.me.get("skills") or {})
                if can is None or layer in can]

    def skinning(self):
        return skinning(self.me)

    def rare(self, mob):
        m = self.farm.world.mobs.get(str(mob)) or ()
        return self.farm.world.rare(str(mob), m[RANK] if len(m) > RANK else 0)

    def grind_kind(self, item):
        me = self.me
        if self.farm.grinds(item, me["level"], me["faction"], self.skinning()):
            return "grind"
        return "gather" if self.nodes(item) else None

    def spot(self, item, way, here=None, need=None):
        me = self.me
        skills = {**(me.get("skills") or {}), "skinning": self.skinning()}
        got = self.farm.spots(item, me["level"], me["faction"], here, skills, kill=way == "grind",
                              layers=() if way == "grind" else self.gathers(), need=need, travel=self.travel)["spots"]
        return got[0] if got else None

    def house(self, item, here=None, spots=()):
        price = self.farm.world.ah_prices()[1].get(item)
        if not price:
            return None
        best = max(spots, key=lambda s: s["score"], default=None)
        return {"price": price, "cheaper": self.farm.cheaper(price, best and best["perHour"], self.me["level"],
                                                             self.me["faction"], here)}

    def droppers(self, item, one_offs=False):
        world = self.farm.world
        me, gives = self.me, world.item_drops().get(item, {})
        rows = self.farm.kill_rows(item, me["level"], me["faction"], self.skinning(), one_offs=one_offs)
        by_mob = {}
        for inst, rs in rows.items():
            for p in rs:
                by_mob.setdefault(p[MOB], {}).setdefault(inst, []).append(p)
        out = []
        for mob, spots in by_mob.items():
            kill, skin = gives.get(str(mob), (0.0, 0.0))
            m = world.mobs.get(str(mob)) or [""] * 3
            lo, hi = m[1], m[2]
            inst, p = nearest_spot(spots, me.get("here"))
            out.append({"id": mob, "name": m[0], "levels": f"{lo}" if lo == hi else f"{lo}-{hi}", "kill": kill, "skin": skin,
                        "near": (inst, p[0], p[1]), "sec": p[SEC], "respawn": p[RESPAWN], "rare": self.rare(mob),
                        "up": world.creature_ups.get(str(mob))})
        out.sort(key=lambda d: (-(d["kill"] + d["skin"]), d["name"]))
        return out[:DROPPERS_MOST]

    def quests(self, item):
        plan, level, out = self.plan, self.me["level"], []
        for qid in self.rewards.get(item, ()):
            q = plan.by_id.get(qid)
            if not q or qid in plan.done or (q.get("level") or 0) > level + QUEST_ABOVE or plan.allowed(q):
                continue
            chain, _ = plan.before(q)
            if chain is None:
                continue
            first = (chain or [q])[0]
            if (first.get("req") or 0) > level:
                continue
            out.append({"id": qid, "name": q["name"], "level": q.get("level"), "before": len(chain), "first": first["id"]})
        out.sort(key=lambda d: (d["before"], d["level"] or 0, d["id"]))
        return out

    def crafts(self, item):
        cd, state = self.pd.cd, self.me.get("state") or {}
        out = []
        for spell in (cd.items.get(str(item)) or {}).get("made") or ():
            r = cd.recipes.get(str(spell)) or {}
            line = r.get("prof")
            if line is None or not profepics.room_for(self.pd, line, state):
                continue
            name = cd.names.get(line, "")
            have = (state.get("profs") or {}).get(name)
            out.append({"recipe": spell, "name": r.get("n") or "", "line": line, "profession": name,
                        "skill": (r.get("p") or {}).get("skill"), "yours": have["rank"] if have else None})
        return out

    def loot(self):
        if self._loot is None:
            index = {}
            for d in self.dungeons:
                if d.get("notOpen") or d.get("kind") not in RUN_KINDS:
                    continue
                for b in d.get("bosses") or ():
                    chances = b.get("chances") or ()
                    for n, item in enumerate(b.get("loot") or ()):
                        index.setdefault(int(item), []).append((d, {
                            "boss": b["name"], "npc": b.get("npc"), "rare": bool(b.get("rare")),
                            "chance": chances[n] / 100 if n < len(chances) and chances[n] else None}))
                for item in d.get("trash") or ():
                    index.setdefault(int(item), []).append((d, {"trash": True}))
                for q in d.get("quests") or ():
                    r = q.get("rewards") or {}
                    for item in {*(r.get("choice") or ()), *(r.get("items") or ())}:
                        index.setdefault(int(item), []).append((d, {"quest": q.get("id")}))
            self._loot = index
        return self._loot

    def trash_chance(self, item, instance):
        world, miss, seen = self.farm.world, 1.0, False
        for mob, (kill, _) in world.item_drops().get(item, {}).items():
            n = world.map_spawns.get(str(mob), {}).get(instance, 0)
            if n:
                seen, miss = True, miss * (1 - kill) ** n
        return 1 - miss if seen else None

    def runs(self, item):
        world, here, out, quests = self.farm.world, self.me.get("here"), [], None
        for d, s in self.loot().get(item, ()):
            spots = [world_pos(e["map"], (e.get("x") or 0) / 100, (e.get("y") or 0) / 100)
                     for e in d.get("entrances") or () if e.get("map")]
            spots = [p for p in spots if p]
            way = {"key": d["key"], "dungeon": d["name"], "raid": d["kind"] == "raid", "open": open_level(d),
                   "bosses": sum(1 for b in d.get("bosses") or () if not b.get("rare")), "rare": False, "up": None,
                   "entrance": min(spots, key=lambda p: (p[0] != here[0], math.hypot(p[1] - here[1], p[2] - here[2])))
                   if spots and here else (spots[0] if spots else None)}
            if "boss" in s:
                way.update(boss=s["boss"], rare=s["rare"], chance=s["chance"],
                           up=world.creature_ups.get(str(s["npc"])) if s["npc"] else None)
            elif "trash" in s:
                way.update(trash=True, chance=self.trash_chance(item, d["instance"]))
            else:
                quests = self.quests(item) if quests is None else quests
                q = next((q for q in quests if q["id"] == s["quest"]), None)
                if not q:
                    continue
                way.update(quest=q["name"], questId=q["id"], before=q["before"], chance=1.0)
            out.append(way)
        return out

    def run_items(self, raid=False):
        return {item for item, got in self.loot().items() if any((d["kind"] == "raid") == raid for d, _ in got)}

    def sure_items(self):
        world, plan, cd = self.farm.world, self.plan, self.pd.cd
        quests = {int(i) for i, ids in self.rewards.items()
                  if any(plan.by_id.get(q) and not plan.allowed(plan.by_id[q]) for q in ids)}
        drops = {int(item) for item, by_mob in world.item_drops().items()
                 if any(sure(kill + skin, world.creature_ups.get(str(mob)), self.rare(mob)) for mob, (kill, skin) in by_mob.items())}
        runs ={item for item, got in self.loot().items() for d, s in got
                if "boss" in s and sure(s["chance"], world.creature_ups.get(str(s["npc"])), s["rare"])
                or "trash" in s and sure(self.trash_chance(item, d["instance"]), None, False)}
        return (quests | set(layers.seller_index(world.services, sure=True)) | {int(i) for i, e in cd.items.items() if e.get("made")}
                | drops | runs)

    def vendor(self, item):
        cd = self.pd.cd
        stocked = cd.stocked(item)
        limited = bool(cd.sellers(item) - stocked)
        npc = self.seller(item, npcs=stocked) if limited and stocked else None
        if npc:
            limited = False
        else:
            npc = self.seller(item)
        if not npc:
            return None
        npc = {**npc, "limited": True} if limited else npc
        price = vendor_price(gamedata.item_unit_price(item), self.me.get("state"))
        return {**npc, **({"price": price} if price else {})}

    def items(self, listed=()):
        cd = self.pd.cd
        return ({int(i) for i in self.rewards} | set(layers.seller_index(self.farm.world.services, sure=True))
                | {int(i) for i in self.farm.world.item_drops()} | {int(i) for i, e in cd.items.items() if e.get("made")}
                | set(self.loot()) | {int(i) for i in listed})


    def keys(self, item, ah=None):
        quests, npc = self.quests(item), self.seller(item)
        house = None
        if not npc:
            ah = self.auction([item]).get(str(item)) if ah is None else ah
            house = (self.auctioneer() or {}).get("name") if (ah or {}).get("auctions") else None
        return {"grind": self.grind_kind(item), "quest": quests[0]["name"] if quests else None,
                "craft": True if self.crafts(item) else None, "buy": npc["name"] if npc else None, "auction": house}

    def sources(self, item, runs_only=False):
        if runs_only:
            return {"item": item, "auction": None, "auctioneer": None, "vendor": None, "grind": [], "once": [], "gather": [],
                    "quests": [], "crafts": [], "runs": self.runs(item), "keys": None}
        nodes = [{"layer": layer, "name": node["n"], "skill": node.get("skill", 0)} for layer, node in self.nodes(item)]
        ah = self.auction([item]).get(str(item))
        return {"item": item, "auction": ah, "auctioneer": self.auctioneer() if ah else None, "vendor": self.vendor(item),
                "grind": self.droppers(item), "once": self.droppers(item, one_offs=True), "gather": nodes,
                "quests": self.quests(item), "crafts": self.crafts(item), "runs": self.runs(item),
                "keys": self.keys(item, ah or {})}


RUN_KINDS = ("dungeon", "raid")


def open_level(d):
    return max((d.get("levels") or [0])[0] or (MAX_LEVEL if d.get("kind") == "raid" else 0), d.get("openFrom") or 0)


def sure(chance, up, rare):
    return not rare and chance is not None and chance * (1.0 if up is None else up) >= COUNT_ON


def skinning(me):
    profs = (me.get("state") or {}).get("profs")
    if profs is not None and SKINNING not in profs:
        return layers.NO_SKINNING
    return (me.get("skills") or {}).get("skinning") or 0


def me_of(hub):
    import planning
    s, st = hub.state or {}, hub.status or {}
    nums = st.get("nums") or {}
    return {"level": s.get("level") or 1, "faction": (st.get("strs") or {}).get("faction", ""), "state": planning.prof_state(hub),
            "here": planning.here_now(hub),
            "skills": {"mining": nums.get("miningSkill") or 0, "herbalism": nums.get("herbalismSkill") or 0,
                       "skinning": nums.get("skinningSkill") or 0}}


def lookup(hub):
    import planning
    s = hub.state or {}
    me = me_of(hub)
    faction = me["faction"]
    pos = s.get("pos")

    def seller(item, npcs=()):
        if not pos or not s.get("map"):
            return None
        return hub.world.nearest(s["map"], pos["x"], pos["y"], faction, None, goods=[item], npcs=npcs, sure=True)

    def auctioneer():
        if not pos or not s.get("map"):
            return None
        return hub.world.nearest(s["map"], pos["x"], pos["y"], faction, ["auction"])
    import questplan
    dungeons = [{**d, **hub.dungeons.open_words(d["key"])} for d in hub.dungeons.list]
    return Lookup(farmspots.farm_for(hub.world), me, planning.quest_reader(hub), reward_index(questplan.book()),
                  planning.prof_data(), seller, lambda ids: hub.auction.summaries(ids)["items"], auctioneer,
                  planning.route_travel(hub), dungeons)
