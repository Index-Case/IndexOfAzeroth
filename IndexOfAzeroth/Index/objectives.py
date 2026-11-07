# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re

import datafiles
from gamedata import client_table
from geo import MapGeometry

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_POINTS = 600
MARGIN = 0.35
DROP_RATE_LEAST = 1 / 20


class ObjectiveIndex:
    def __init__(self):
        path = os.path.join(ROOT, "data", "objectives.json")
        self.ok = os.path.exists(path)
        data = datafiles.load(path, {})
        self.npcs, self.objects = dict(data.get("npcs", {})), data.get("objects", {})
        self.items, self.quests = data.get("items", {}), data.get("quests", {})
        self.source = data.get("source", "")
        self.geo = MapGeometry()
        self.forever_mobs()
        self.npc_names = {}
        for npc_id, npc in self.npcs.items():
            self.npc_names.setdefault(npc["n"].lower(), []).append(npc_id)
        self.spawns_kept = {}

    def world_spawns(self, kind, oid, side=None):
        key = (kind, str(oid), side)
        if key not in self.spawns_kept:
            rec = (self.npcs if kind == "npc" else self.objects).get(str(oid)) or {}
            mine = (rec.get("sides") or {}).get(side) or {}
            spots = mine["s"] if "s" in mine else rec.get("s")
            self.spawns_kept[key] = [(w[2], w[0], w[1], int(area)) for area, pts in (spots or {}).items() for x, y in pts
                                     for w in [self.geo.area_to_world(area, x, y)] if w and str(area).isdigit()]
        return self.spawns_kept[key]

    def forever_mobs(self):
        world = datafiles.load(os.path.join(ROOT, "data", "world.json"), {})
        spawns = world.get("mobSpawns", {})
        for mob_id, m in world.get("mobs", {}).items():
            if mob_id in spawns and mob_id not in self.npcs:
                self.npcs[mob_id] = {"n": m[0], "s": spawns[mob_id]}

    def named_in(self, text, words=False):
        text = (text or "").lower()
        whole = sorted((n for n in self.npc_names if len(n) > 3 and n in text and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text)),
                       key=len, reverse=True)
        if whole:
            return [i for i in self.npc_names[whole[0]]]
        if not words:
            return []
        keys = {w for w in re.findall(r"[a-z']{5,}", text)}
        return [i for n, ids in self.npc_names.items() if keys & set(re.findall(r"[a-z']{5,}", n)) for i in ids]


    def item_sources(self, item_id):
        item = self.items.get(str(item_id), {})
        droppers = [str(i) for i in item.get("d", [])]
        rates = {k: c / n for k, (c, n) in (item.get("dr") or {}).items() if n}
        if rates and max(rates.values()) >= DROP_RATE_LEAST:
            droppers = [i for i in droppers if rates.get(i, 1) >= DROP_RATE_LEAST]
        sources = [("npc", i) for i in droppers] + [("object", str(i)) for i in item.get("o", [])]
        return sources or [("npc", str(i)) for i in item.get("v", [])]

    @staticmethod
    def pick_by_name(candidates, names, text):
        text = (text or "").lower()
        named = [c for c in candidates if names(c) and names(c).lower() in text]
        found = {names(c).lower() for c in named}
        named = [c for c in named if not any(n != names(c).lower() and names(c).lower() in n for n in found)]
        return named or candidates

    def quest_sources(self, entry):
        quest = self.quests.get(str(entry["quest"]), {})
        creatures = quest.get("c", []) + [n for credit in quest.get("k", []) for n in credit]
        objects, items = quest.get("o", []), quest.get("i", [])
        otype, text = entry.get("type"), entry.get("text")
        npc_name = lambda i: self.npcs.get(str(i), {}).get("n")
        obj_name = lambda i: self.objects.get(str(i), {}).get("n")
        item_name = lambda i: self.items.get(str(i), {}).get("n")
        if otype == "monster" and creatures:
            return [("npc", str(i)) for i in self.pick_by_name(creatures, npc_name, text)]
        if otype == "item" and items:
            return [s for i in self.pick_by_name(items, item_name, text) for s in self.item_sources(i)]
        if otype == "object" and objects:
            return [("object", str(i)) for i in self.pick_by_name(objects, obj_name, text)]
        if not (creatures or objects or items):
            return [("npc", i) for i in self.named_in(text, words=otype == "item")]
        return ([("npc", str(i)) for i in creatures] + [("object", str(i)) for i in objects]
                + [s for i in items for s in self.item_sources(i)])

    def item_name(self, item_id):
        name = self.items.get(str(item_id), {}).get("n")
        if name:
            return name
        row = client_table("items.json", "items")[1].get(str(item_id))
        return row[0] if row else None

    def quest_item(self, quest_id, text, also=()):
        quest = self.quests.get(str(quest_id), {})
        best = None
        for item_id in dict.fromkeys([*quest.get("i", []), *also]):
            name = self.item_name(item_id)
            found = name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or "", re.I)
            if found and (best is None or len(name) > len(best[1])):
                best = (item_id, found.group(0))
        return best


    def project(self, area, points, player_map):
        return [list(p) for p in self.geo.project(area, points, player_map, MARGIN)]

    def points(self, sources, player_map):
        pts, names = [], []
        for kind, ident in sources:
            entity = (self.npcs if kind == "npc" else self.objects).get(str(ident))
            if not entity:
                continue
            found = [p for area, spawn in entity["s"].items() for p in self.project(area, spawn, player_map)]
            if found and entity["n"] not in names:
                names.append(entity["n"])
            pts.extend(found)
        if len(pts) > MAX_POINTS:
            step = len(pts) / MAX_POINTS
            pts = [pts[int(i * step)] for i in range(MAX_POINTS)]
        return pts, names
