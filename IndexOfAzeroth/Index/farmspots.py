# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import datafiles
import director_rules
from facts import RUN_SPEED
import layers
from layers import camp_blocks, camp_hourly, camp_spots, camp_timing

NODE_LAYERS = ("mining", "herbalism")
NODE_YIELD = 1.0
FARM_SECONDS = 3600.0
OTHER_CONTINENT_SECONDS = 1200.0
RIDE_TEDIUM = director_rules.COST["far"].value / RUN_SPEED
SPOTS_MOST = 5
TRIPS_ASKED = 80
APART = 3 * layers.CAMP_CELL
NODE_WALK_MOST = APART
LEAST = 4


def farm_seconds(per_hour, trip, need=None):
    if per_hour <= 0:
        return math.inf
    return max(0.0, trip) + (FARM_SECONDS if need is None else need * 3600.0 / per_hour)


def farm_score(per_hour, trip, need=None):
    seconds = farm_seconds(per_hour, trip, need)
    return 0.0 if seconds == math.inf else (per_hour if need is None else need) * 3600.0 / max(seconds, 1e-9)


def ranked(camps, here, need=None, travel=None):
    cheap = sorted(((farm_score(c[0], trip_seconds(here, *c[1:4]), need), trip_seconds(here, *c[1:4]), c) for c in camps),
                   key=lambda r: -r[0])
    if travel is None or not here:
        return cheap
    ridden = getattr(travel, "ridden", lambda a, b: a[0] != b[0])
    out = []
    for k, (guess, line, c) in enumerate(cheap):
        if k >= TRIPS_ASKED or sum(1 for r in out if r[0] >= guess) >= SPOTS_MOST:
            break
        try:
            trip = travel(here, tuple(c[1:4]))
            if trip is not None and ridden(here, tuple(c[1:4])):
                trip += RIDE_TEDIUM
        except Exception:
            trip = line
        if trip is not None:
            out.append((farm_score(c[0], trip, need), trip, c))
    return sorted(out, key=lambda r: -r[0])


def camp_kind(gives, block, skinning=0):
    skins = sum(gives[str(p[10])][1] * p[11] for p in block if layers.skinned(True, p[5], skinning))
    return "skin" if skins > sum(gives[str(p[10])][0] * p[11] for p in block) else "kill"


def trip_seconds(here, inst, north, west):
    if not here:
        return 0.0
    if here[0] != inst:
        return OTHER_CONTINENT_SECONDS + RIDE_TEDIUM
    return math.hypot(here[1] - north, here[2] - west) / RUN_SPEED


def apart(picked, inst, north, west):
    return all(p["inst"] != inst or math.hypot(p["at"][0] - north, p["at"][1] - west) >= APART for p in picked)


def node_items(professions):
    out = {}
    for item, e in (professions.get("items") or {}).items():
        names = (e.get("loot") or {}).get("gathered")
        if names and str(item).isdigit():
            out[int(item)] = set(names)
    return out


_farm = None


def farm_for(world):
    global _farm
    professions, got = datafiles.load(layers.PROFESSIONS, {}), _farm
    if got is None or got[0] is not world or got[1] is not professions:
        got = _farm = (world, professions, Farm(world, professions))
    return got[2]


class Farm:

    def __init__(self, world, professions=None):
        self.world = world
        self.gathered = node_items(professions if professions is not None else datafiles.load(layers.PROFESSIONS, {}))
        self.names_kept = None


    def names(self):
        table, drops, nodes = self.world.item_table(), self.world.item_drops(), self.world.nodes
        got = self.names_kept
        if got is not None and all(a is b for a, b in zip(got[0], (table, drops, nodes))):
            return got[1]
        out = {}
        for item in set(drops) | {i for i in self.gathered if self.nodes_of(i)}:
            row = table.get(str(item))
            if row and row[0]:
                out[item] = (row[0], (row[2] if len(row) > 2 else None) or "inv_misc_questionmark", row[1] if len(row) > 1 else 1)
        self.names_kept = ((table, drops, nodes), out)
        return out

    def nodes_of(self, item):
        names = self.gathered.get(item) or set()
        return [(layer, node) for layer in NODE_LAYERS for node in self.world.nodes.get(layer, []) if node["n"] in names]

    def gather_nodes(self, item, skills):
        return [(layer, node) for layer, node in self.nodes_of(item)
                if not skills.get(layer) or node.get("skill", 0) <= skills[layer]]

    def kill_rows(self, item, level, faction, skinning, keep=True, one_offs=False):
        return self.world.camp_rows(self.zones(), level, faction, item=item, skinning=skinning, keep=keep, one_offs=one_offs)

    def grinds(self, item, level, faction, skinning):
        return any(self.kill_rows(item, level, faction, skinning, keep=False).values())


    def zones(self):
        return {int(z) for z, zm in self.world.geo.maps.items() if zm.get("type") == 3 and zm.get("world")}

    def kill_camps(self, item, level, faction, skinning):
        out, gives = [], self.world.item_drops().get(item, {})
        for inst, pts in self.kill_rows(item, level, faction, skinning).items():
            danger = self.world.threats(inst, level, faction, fight=True)
            danger = danger[danger[:, 3] > 0]
            for score, block, cn, cw in camp_blocks(pts, None, danger, LEAST, timing=camp_timing, rate=camp_hourly):
                out.append((score, camp_kind(gives, block, skinning), block, inst, cn, cw))
        return out

    def node_rows(self, item, level, faction, skills):
        import numpy as np
        from scipy.spatial import cKDTree
        zones, by_layer, unsafe = self.zones(), {}, {}
        for layer, node in self.gather_nodes(item, skills):
            respawn = self.world.node_respawns(layer).get(node["id"]) or layers.RESPAWN_FALLBACK
            for n, w, inst, zone, chance, up in self.world.zone_spots(node["s"], zones, odds=node.get("o") or {}):
                if inst not in unsafe:
                    unsafe[inst] = self.world.unsafe_spot(inst, level, faction)
                if not unsafe[inst](n, w):
                    by_layer.setdefault((inst, layer), []).append([n, w, 0.0, node["n"], node.get("skill", 0), node.get("skill", 0),
                                                                   0.0, respawn, NODE_YIELD, zone, node["id"], chance * up])
        out = {}
        for key, rows in by_layer.items():
            at = np.array([(r[0], r[1]) for r in rows])
            gaps = cKDTree(at).query(at, k=2)[0][:, 1] if len(rows) > 1 else np.array([NODE_WALK_MOST])
            for r, gap in zip(rows, gaps):
                r[6] = layers.GATHER_SECONDS + min(float(gap), NODE_WALK_MOST) / RUN_SPEED
                r[2] = r[8] * r[11] * 3600 / r[6]
            out[key] = [tuple(r) for r in rows]
        return out

    def gather_camps(self, item, level, faction, skills, layers=None):
        return [(score, layer, block, inst, cn, cw) for (inst, layer), pts in self.node_rows(item, level, faction, skills).items()
                if layers is None or layer in layers
                for score, block, cn, cw in camp_blocks(pts, None, None, LEAST, timing=camp_timing, rate=camp_hourly)]

    def spots(self, item, level, faction, here=None, skills=None, kill=True, layers=None, need=None, travel=None):
        skills = skills or {}
        camps = (self.kill_camps(item, level, faction, skills.get("skinning") or 0) if kill else []) \
            + (self.gather_camps(item, level, faction, skills, layers) if layers is None or layers else [])
        picked = []
        for score, trip, (per_hour, inst, cn, cw, kind, block) in ranked(
                [(per_hour, inst, cn, cw, kind, block) for per_hour, kind, block, inst, cn, cw in camps], here, need, travel):
            if len(picked) >= SPOTS_MOST:
                break
            if score > 0 and apart(picked, inst, cn, cw):
                picked.append(self.spot(kind, block, inst, cn, cw, per_hour, score, trip))
        name, icon, _ = self.names().get(item, (None, None, None))
        price = self.world.ah_prices()[1].get(item)
        return {"item": item, "name": name, "icon": icon, "spots": picked, "price": price,
                "cheaper": self.cheaper(price, picked[0]["perHour"] if picked else None, level, faction, here)}

    def cheaper(self, price, per_hour, level, faction, here):
        return bool(price and per_hour and self.gold_hour(level, faction, here) > price * per_hour)

    @staticmethod
    def spot(kind, block, inst, cn, cw, per_hour, score, trip):
        names, zones, ids = {}, {}, {}
        for p in block:
            names[p[3]] = names.get(p[3], 0) + p[11]
            zones[p[9]] = zones.get(p[9], 0) + p[11]
            ids[p[10]] = ids.get(p[10], 0) + p[11]
        lo, hi = min(p[4] for p in block), max(p[5] for p in block)
        out = {"kind": kind, "perHour": round(per_hour, 1), "at": [round(cn, 1), round(cw, 1)], "inst": inst,
               "map": max(zones, key=zones.get), "names": sorted(names, key=lambda k: -names[k])[:layers.LOOP_MOBS],
               "ids": [int(i) for i in sorted(ids, key=lambda k: -ids[k])],
               "trip": round(trip), "score": round(score, 2), "spawns": camp_spots(block)}
        gathered = kind in NODE_LAYERS
        out["skill" if gathered else "levels"] = lo if gathered else f"{lo}" if lo == hi else f"{lo}-{hi}"
        return out

    def gold_hour(self, level, faction, here):
        if not here:
            return 0.0
        zones = self.world.zone_scores(here[0], level, faction, ah=True)
        return max((z["gold"] for z in zones), default=0.0)
