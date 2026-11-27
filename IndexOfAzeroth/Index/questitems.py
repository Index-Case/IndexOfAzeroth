# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

import datafiles
from facts import faction_bit
from mapzones import world_pos
from plansteps import BUY_WORD

ROOT = os.path.dirname(os.path.abspath(__file__))
GET_FIRST = "get"
GROUP = "items"
ANY = "any"
FRIEND_MASK = 6
DEPTH = 4
FISH = "fish"

SKIPS = {
    "from the giver": "The quest hands the item over when you take it.",
    "earlier quest": "A quest before it in its chain hands the item over or gives it as a reward.",
    "own objective": "The quest collects the item as an objective of its own.",
    "own targets": "The item comes from the mobs or objects the quest's own objectives are about.",
    "in the run": "The quest is done inside a dungeon, and its run gets the item.",
    "dungeon drop": "The item comes only from inside a dungeon, a raid or a battleground.",
    "unplaced": "The sources name where the item comes from but place none of it out in the open world.",
    "unsourced": "No source says where the item comes from.",
}
FAILING = ("unplaced", "unsourced")


def shut():
    d = datafiles.load(os.path.join(ROOT, "data", "dungeons.json"), {})
    return {x["instance"] for x in (d.get("dungeons") or []) + (d.get("battlegrounds") or []) if x.get("instance") is not None}


def dungeon_areas():
    d = datafiles.load(os.path.join(ROOT, "data", "dungeons.json"), {})
    return {x["area"] for x in d.get("dungeons") or () if x.get("area")}


def spots_of(index, kind, oid, closed=()):
    rec = (index.npcs if kind == "npc" else index.objects).get(str(oid)) or {}
    out, inside = [], 0
    for area, pts in (rec.get("s") or {}).items():
        map_id = index.geo.area_map.get(str(area))
        inside += sum(1 for x, y in pts if x < 0 or y < 0)
        if map_id is None:
            continue
        for x, y in pts:
            if x < 0 or y < 0:
                continue
            w = world_pos(map_id, x / 100, y / 100)
            if w and w[0] not in closed:
                out.append([map_id, round(x, 1), round(y, 1)])
            elif w:
                inside += 1
    return out, inside


def before(quests, q):
    seen, todo = set(), list((q.get("preAll") or []) + (q.get("preAny") or []) + ([q["parent"]] if q.get("parent") else []))
    while todo:
        p = todo.pop()
        if p in seen or p not in quests:
            continue
        seen.add(p)
        o = quests[p]
        todo += (o.get("preAll") or []) + (o.get("preAny") or []) + ([o["parent"]] if o.get("parent") else [])
    return seen


def hands(q):
    return ({q["item"]} if q.get("item") else set()) | set(q.get("provided") or ())


def rewards(q):
    r = q.get("rewards") or {}
    return {i[0] if isinstance(i, list) else i for i in (r.get("items") or []) + (r.get("choice") or [])}


class Items:
    def __init__(self, index, side, mobs=None, quests=None, professions=None, shores=None):
        self.professions = professions if professions is not None else \
            datafiles.load(os.path.join(ROOT, "data", "professions.json"), {}).get("items") or {}
        self.shores = shores if shores is not None else \
            datafiles.load(os.path.join(ROOT, "data", "fishing_spots.json"), {}).get("areas") or {}
        if mobs is None:
            mobs = datafiles.load(os.path.join(ROOT, "data", "world.json"), {}).get("mobs", {})
        if quests is None:
            import questplan
            quests = questplan.book().quests
        self.index, self.side, self.mobs, self.quests = index, side, mobs, quests
        self.bit, self.closed, self.dungeons = faction_bit(side), shut(), dungeon_areas()

    def name(self, kind, i):
        return ((self.index.npcs if kind == "npc" else self.index.objects).get(str(i)) or {}).get("n")

    def classify(self, q, item, count=None, depth=0):
        rec = self.index.items.get(str(item)) or {}
        full = {**(self.quests.get(q["id"]) or {}), **q}
        for k in ("item", "provided", "itemCounts", "preAll", "preAny", "parent"):
            if not q.get(k) and full.get(k):
                q = {**q, k: full[k]}
        count = count or int((q.get("itemCounts") or {}).get(str(item)) or 1)
        given = hands(q)
        if item in given or set(rec.get("i") or ()) & given:
            return [], "from the giver"
        for p in before(self.quests, q):
            o = self.quests[p]
            if item in hands(o) | rewards(o) or set(rec.get("i") or ()) & hands(o) or p in (rec.get("r") or ()):
                return [], "earlier quest"
        name = rec.get("n")
        targets = q.get("targets") or []
        if name and any(t["kind"] in ("loot", "talk") and t["name"] == name and not t.get(GET_FIRST) for t in targets):
            return [], "own objective"
        if rec.get("pp"):
            return self.pocket(item, name, rec["pp"], count)
        fished = self.fished(item, name, count)
        if name and any(rec.get(k) for k in ("d", "o", "v")):
            got, why = self.found(q, item, rec, count)
            if fished and why in FAILING + ("dungeon drop",):
                return fished, None
            if why not in FAILING or not rec.get("m"):
                return got, why
        if fished:
            return fished, None
        if rec.get("m") and depth < DEPTH:
            out, whys = [], []
            for reagent, n in rec["m"]:
                got, why = self.classify(q, reagent, count * n, depth + 1)
                if why in FAILING:
                    return [], why
                out, whys = out + got, whys + [why] if why else whys
            return out, None if out else whys[0]
        if name and any(rec.get(k) for k in ("d", "o", "v")):
            return self.found(q, item, rec, count)
        return [], "in the run" if q.get("zone") in self.dungeons else "unsourced"

    def fished(self, item, name, count):
        areas = ((self.professions.get(str(item)) or {}).get("loot") or {}).get("fished") or ()
        spots = []
        for a in areas:
            spots += [s for s in self.shores.get(str(a)) or () if s not in spots]
        name = name or (self.professions.get(str(item)) or {}).get("n")
        if not spots or not name:
            return []
        return [{"kind": FISH, "name": name, "count": count, "spots": spots, GET_FIRST: int(item),
                 "text": f"Fish for {f'{count} ' if count > 1 else ''}{name}"}]

    def pocket(self, item, name, npcs, count):
        spots = [s for n in npcs for s in spots_of(self.index, "npc", n, self.closed)[0]]
        if not spots:
            return [], "dungeon drop"
        who = self.name("npc", npcs[0])
        return [{"kind": "pickpocket", "name": name, "count": count, "spots": spots, GET_FIRST: int(item), "mobs": list(npcs),
                 "text": f"Pick {who}'s pocket for {name}" if len(npcs) == 1 and who else f"Pick pockets for {name}"}], None

    def found(self, q, item, rec, count):
        targets = q.get("targets") or []
        sources = self.index.item_sources(item)
        npcs = [int(i) for kind, i in sources if kind == "npc"]
        objects = [int(i) for kind, i in sources if kind == "object"]
        own_mobs = {m for t in targets for m in t.get("mobs") or ()}
        own_objects = {o for t in targets for o in t.get("objects") or ()}
        if targets and set(npcs) <= own_mobs and set(objects) <= own_objects:
            return [], "own targets"
        fights = [m for m in npcs if str(m) in self.mobs and not self.mobs[str(m)][FRIEND_MASK] & self.bit]
        friends = [m for m in npcs if m not in fights]
        sold = {int(i) for i in rec.get("v") or ()}
        inside, whose, spots = 0, [], []
        for fights, objects, friends in ((fights, objects, []), ([], [], friends), ([], [], sorted(sold))):
            whose = [("npc", m) for m in fights + friends] + [("object", o) for o in objects]
            spots = []
            for kind, oid in whose:
                got, shut_in = spots_of(self.index, kind, oid, self.closed)
                spots, inside = spots + got, inside + shut_in
            if spots:
                break
        else:
            return [], "in the run" if q.get("zone") in self.dungeons else "dungeon drop" if inside else "unplaced"
        name = rec["n"]
        t = {"name": name, "count": count, "spots": spots, GET_FIRST: int(item)}
        if fights or objects:
            one = len(fights) == 1 and not objects and self.name("npc", fights[0])
            t["kind"] = "kill" if one else "loot"
            if one:
                t["text"] = f"Kill {one} for {f'{count} ' if count > 1 else ''}{name}"
        else:
            buy = all(m in sold for m in friends)
            one = len(friends) == 1 and self.name("npc", friends[0])
            t["kind"], t["buy"] = "talk", buy
            if one:
                t["who"] = one
            t["text"] = f"{BUY_WORD if buy else 'Get'} {f'{count} ' if count > 1 else ''}{name}" + (f" from {one}" if one else "")
        mob_ids = [i for kind, i in whose if kind == "npc"]
        if t["kind"] == "talk":
            t["names"] = {str(m): self.name("npc", m) for m in mob_ids if self.name("npc", m)}
        return [{**t, **({"mobs": mob_ids} if mob_ids else {}), **({"objects": objects} if objects else {})}], None

    def get_targets(self, q):
        out = []
        for i in q.get("items") or ():
            got, _ = self.classify(q, i)
            out += [t for t in got if not any(o[GET_FIRST] == t[GET_FIRST] for o in out)]
        return grouped(q, out)

    def reasons(self, q):
        return [(i, self.classify(q, i)[1]) for i in q.get("items") or ()]


def grouped(q, targets):
    out, by = [], {}
    for t in targets:
        key = (t["kind"], tuple(t.get("mobs") or ()), tuple(t.get("objects") or ()))
        if key in by:
            by[key].append(t)
        else:
            by[key] = [t]
            out.append(key)
    merged = []
    for key in out:
        ts = by[key]
        if len(ts) == 1:
            merged.append(ts[0])
            continue
        first, names = ts[0], [t["name"] for t in ts]
        listed = ", ".join(names[:-1]) + " and " + names[-1]
        t = {**first, GROUP: [x[GET_FIRST] for x in ts], "count": 1}
        if first["kind"] == "talk":
            who = first.get("who")
            verb, has = (BUY_WORD, "sells") if first.get("buy") else ("Get", "hands over")
            t[ANY] = True
            t["text"] = (f"{verb} what {q['name']} needs from {who}. {who} {has} {listed}." if who else
                         f"{verb} what {q['name']} needs from the nearest NPC who {has} {listed}.")
        else:
            t["text"] = f"Collect {listed}"
        merged.append(t)
    return merged


def get_targets(index, q, side, mobs=None, quests=None):
    return Items(index, side, mobs, quests).get_targets(q)


def kept_out(t, bags):
    have = [i in bags for i in t.get(GROUP) or [t[GET_FIRST]]]
    return any(have) if t.get(ANY) else all(have)


def adder(index, bags=(), side=None, mobs=None, quests=None):
    bags, kept, world = set(bags), {}, Items(index, side, mobs, quests)

    def with_gets(q):
        if not q.get("items"):
            return q
        if q["id"] not in kept:
            kept[q["id"]] = world.get_targets(q)
        gets = [t for t in kept[q["id"]] if not kept_out(t, bags)]
        return {**q, "targets": gets + list(q.get("targets") or ())} if gets else q
    return with_gets
