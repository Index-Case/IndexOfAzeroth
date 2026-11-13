# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import os
import threading

import numpy as np

import datafiles
import geo
import pictures
from serverlog import log_error, start_thread
from versioned import Versioned

ROOT = os.path.dirname(os.path.abspath(__file__))
MAPS = datafiles.load(os.path.join(ROOT, "data", "maps.json"), {}).get("maps", {})
HIGHLIGHTS = {m["highlight"] for m in MAPS.values() if m.get("highlight")}
AREAS = datafiles.load(os.path.join(ROOT, "data", "cities.json"), {}).get("cities", {})


def reload_maps():
    global MAPS, HIGHLIGHTS, AREAS
    MAPS = datafiles.load(os.path.join(ROOT, "data", "maps.json"), {}).get("maps", {})
    HIGHLIGHTS = {m["highlight"] for m in MAPS.values() if m.get("highlight")}
    AREAS = datafiles.load(os.path.join(ROOT, "data", "cities.json"), {}).get("cities", {})
    _area_cells.clear()


_area_cells = {}


def area_zone(map_id, instance, north, west):
    g, m = AREAS.get(str(map_id)), MAPS.get(str(map_id)) or {}
    w = m.get("world")
    if not g or not w or m.get("instance") != instance:
        return None
    r, c = math.floor((w["top"] - north) / g["cell"]), math.floor((w["left"] - west) / g["cell"])
    if not (0 <= r < g["rows"] and 0 <= c < g["cols"]):
        return None
    cells = _area_cells.get(map_id)
    if cells is None:
        runs = g["runs"]
        cells = _area_cells[map_id] = np.repeat(np.array(runs[0::2], np.uint8), runs[1::2])
    return g["zones"][int(cells[r * g["cols"] + c])] or None


def zone_of_area(instance, north, west):
    other = None
    for k in AREAS:
        z = area_zone(int(k), instance, north, west)
        if z == int(k):
            return z
        other = other or z
    return other


def zone_map_named(name):
    if not name:
        return None
    return next((int(k) for k, m in MAPS.items() if m.get("type") == 3 and m.get("name") == name), None)


def city_zone(map_id):
    c = MAPS.get(str(map_id)) or {}
    b = c.get("world")
    if c.get("type") != 3 or c.get("highlight") or not b:
        return None
    best, most, smallest = None, 0, math.inf
    for k, m in MAPS.items():
        w = m.get("world")
        if m.get("type") != 3 or not m.get("highlight") or not w or m.get("instance") != c.get("instance"):
            continue
        across = min(b["left"], w["left"]) - max(b["right"], w["right"])
        down = min(b["top"], w["top"]) - max(b["bottom"], w["bottom"])
        held, size = max(0, across) * max(0, down), abs((w["left"] - w["right"]) * (w["top"] - w["bottom"]))
        if held > most or (held and held == most and size < smallest):
            best, most, smallest = int(k), held, size
    return best


def world_pos(map_id, x, y):
    m = MAPS.get(str(map_id))
    w = m and m.get("world")
    if not w:
        return None
    return (m["instance"], *geo.to_world(w, x, y))


def zone_yards(map_id, instance, north, west):
    m = MAPS.get(str(map_id)) or {}
    w = m.get("world")
    if not w or m.get("instance") != instance:
        return math.inf
    return math.hypot((w["top"] + w["bottom"]) / 2 - north, (w["left"] + w["right"]) / 2 - west)


ZONE_EDGE = 0.1


def zone_holding(instance, north, west):
    known = zone_of_area(instance, north, west)
    if known is not None:
        return known
    box = zone_box(instance, north, west)
    if str(box) in AREAS:
        return zone_shaped(instance, north, west) or city_zone(box)
    if box is not None and not (MAPS.get(str(box)) or {}).get("highlight"):
        return box
    return zone_shaped(instance, north, west) or box


ZONE_GLOW_CUT, ZONE_GLOW_SPREAD = 0.08, 8

_zone_masks = {}


def zone_mask(map_id):
    if map_id not in _zone_masks:
        fid, mask = (MAPS.get(str(map_id)) or {}).get("highlight"), None
        path = fid and os.path.join(pictures.GLOWS, f"{fid}.png")
        if path and os.path.exists(path):
            try:
                from PIL import Image
                a = np.asarray(Image.open(path).convert("RGB").resize((128, 128), Image.BILINEAR), dtype=np.float32).max(axis=2)
                r = ZONE_GLOW_SPREAD
                p = np.pad(a, ((0, 0), (r, r)))
                across = np.max([p[:, k:k + 128] for k in range(2 * r + 1)], axis=0)
                p = np.pad(across, ((r, r), (0, 0)))
                mask = np.max([p[k:k + 128, :] for k in range(2 * r + 1)], axis=0) / (a.max() or 1)
            except (OSError, ValueError):
                mask = None
        _zone_masks[map_id] = mask
    return _zone_masks[map_id]


def zone_shaped(instance, north, west):
    cont = next((int(k) for k, m in MAPS.items() if m.get("type") == 2 and m.get("instance") == instance and m.get("world")), None)
    c = MAPS.get(str(cont)) if cont is not None else None
    if not c:
        return None
    cw, art = c["world"], c.get("art") or {}
    aspect = (art.get("width") or 1) / (art.get("height") or 1)
    frac = lambda n, w: geo.to_map(cw, n, w)
    fx, fy = frac(north, west)
    best, best_b = None, ZONE_GLOW_CUT
    for map_id, m in MAPS.items():
        w = m.get("world")
        if m.get("parent") != cont or m.get("type") != 3 or not m.get("highlight") or not w:
            continue
        (ax, ay), (bx, by) = frac(w["top"], w["left"]), frac(w["bottom"], w["right"])
        u, v = (fx - ax) / (bx - ax), (fy - ay) / ((bx - ax) * aspect)
        if u < 0 or v < 0 or u >= 1 or v >= 1 or fy - ay >= by - ay:
            continue
        mask = zone_mask(int(map_id))
        b = float(mask[int(v * 128), int(u * 128)]) if mask is not None else 0.0
        if b > best_b:
            best, best_b = int(map_id), b
    return best


def zone_box(instance, north, west):
    best, best_key = None, None
    for map_id, m in MAPS.items():
        w = m.get("world")
        if m.get("type") != 3 or not w or m.get("instance") != instance:
            continue
        fx, fy = geo.to_map(w, north, west)
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            continue
        key = (min(fx, 1 - fx, fy, 1 - fy) < ZONE_EDGE, abs((w["left"] - w["right"]) * (w["top"] - w["bottom"])))
        if best_key is None or key < best_key:
            best, best_key = int(map_id), key
    return best


def settle_zone(state):
    flags, pos = state.get("flags") or {}, state.get("pos")
    m = MAPS.get(str(state.get("map")))
    if not pos or not m or m.get("type") != 2 or flags.get("taxi") or flags.get("instance"):
        return
    here = world_pos(state["map"], pos["x"], pos["y"])
    zone = here and zone_holding(*here)
    if not zone:
        return
    z = MAPS[str(zone)]["world"]

    def onto(p):
        x, y = geo.to_map(z, *world_pos(state["map"], p["x"], p["y"])[1:])
        return {"x": x, "y": y}

    state["gameMap"], state["map"], state["pos"] = state["map"], zone, onto(pos)


PATROL_MARGIN = 0.35


def patrols_on(hub, map_id, npc):
    m = MAPS.get(str(map_id)) or {}
    w, out = m.get("world"), []
    if not w:
        return out
    for inst, route in hub.world.patrols.get(str(npc), ()):
        if inst != m.get("instance"):
            continue
        pts = [[round(x, 4), round(y, 4)] for x, y in (geo.to_map(w, float(n), float(wv)) for n, wv in route)]
        if any(-PATROL_MARGIN <= x <= 1 + PATROL_MARGIN and -PATROL_MARGIN <= y <= 1 + PATROL_MARGIN for x, y in pts):
            out.append(pts)
    return out


PORTAL_MARGIN = 15


def portals_in(hub, instance, bounds):
    m = PORTAL_MARGIN
    return [p for p in hub.routes.portals() if p["inst"] == instance and bounds["bottom"] - m <= p["n"] <= bounds["top"] + m
            and bounds["right"] - m <= p["w"] <= bounds["left"] + m]


def dungeon_names():
    import client
    return {int(r["ID"]): r["MapName_lang"] for r in client.rows("Map", stored=True) if r.get("InstanceType") in ("1", "2")}


DUNGEON_NAMES = Versioned(dungeon_names, lambda where: log_error(where), "dungeon names")


def dungeon_name(hub, map_id):
    names = DUNGEON_NAMES.ready(getattr(hub, "data_version", None) or 0)
    return (names or {}).get(map_id) if isinstance(map_id, int) else None


def place_name(hub, instance, north, west):
    zone = zone_holding(instance, north, west)
    return MAPS[str(zone)].get("name") if zone is not None else dungeon_name(hub, instance)


def learnt_way_in(hub, dungeon_map):
    seen = hub.entrances_seen.outside_of(dungeon_map)
    zone = seen and zone_box(*seen)
    if zone is None:
        return None
    fx, fy = geo.to_map(MAPS[str(zone)]["world"], seen[1], seen[2])
    return {"map": zone, "x": round(fx * 100, 1), "y": round(fy * 100, 1), "walked": True}


def learnt_entrances(hub, map_id, have):
    mp = MAPS.get(str(map_id))
    w = mp and mp.get("world")
    if not w:
        return []
    named = {p["name"].lower().removeprefix("the ") for p in have}
    out = []
    for name, n, wv in hub.entrances_seen.on(mp.get("instance")):
        x, y = geo.to_map(w, n, wv)
        if 0 <= x <= 1 and 0 <= y <= 1 and name.lower().removeprefix("the ") not in named:
            out.append({"cat": "dungeon", "detail": None, "name": name, "sub": "Dungeon entrance, recorded when you went in", "x": x, "y": y})
    return out


def portal_pois(hub, map_id):
    mp = MAPS.get(str(map_id))
    w = mp and mp.get("world")
    if not w:
        return []
    frac = lambda n, wv: geo.to_map(w, n, wv)
    out = []
    for p in hub.routes.portals():
        x, y = frac(p["n"], p["w"])
        if p["underground"] or p["inst"] != mp.get("instance") or not (-0.02 <= x <= 1.02 and -0.02 <= y <= 1.02):
            continue
        gx, gy = frac(p["walk"][0], p["walk"][1])
        out.append({"cat": "portal", "detail": None, "name": f"{p['dungeon']} portal", "sub": "The way in ends here, so walk into it",
                    "x": x, "y": y, "gx": gx, "gy": gy, "z": p["walk"][2]})
    return out


def dock_words(net, i):
    to = [net["stops"][b if a == i else a]["name"] for a, b in net["links"] if i in (a, b)]
    return {"name": f"Boat to {' and '.join(to)}", "sub": f"The dock at {net['stops'][i]['name']}"}


def dock_pois(hub, map_id):
    mp = MAPS.get(str(map_id))
    w = mp and mp.get("world")
    if not w:
        return []
    net = hub.routes.networks()["boat"]
    out = []
    for i, s in enumerate(net["stops"]):
        x, y = geo.to_map(w, s["n"], s["w"])
        if s["inst"] != mp.get("instance") or not (-0.02 <= x <= 1.02 and -0.02 <= y <= 1.02):
            continue
        out.append({"cat": "boat", "detail": None, **dock_words(net, i), "x": x, "y": y,
                    **({"side": s["side"]} if s["side"] else {})})
    return out


def nearest_dock(hub, map_id, fx, fy, faction):
    mp = MAPS.get(str(map_id))
    if not mp or not mp.get("world"):
        return None
    pn, pw = geo.to_world(mp["world"], fx, fy)
    net = hub.routes.networks(faction or None)["boat"]
    best, least = None, math.inf
    for i, s in enumerate(net["stops"]):
        yards = math.hypot(s["n"] - pn, s["w"] - pw)
        if s["inst"] == mp.get("instance") and yards < least:
            least = yards
            best = {**dock_words(net, i), "cat": "boat", "zone": "", "wx": s["n"], "wy": s["w"], "wz": None,
                    "yards": round(yards)}
    return best


CAPITAL = 0x100
NO_PVP = 0x800
AREA_DEPTH = 8


def area_chain(parent, area):
    yield area
    for _ in range(AREA_DEPTH):
        if not parent.get(area):
            return
        area = parent[area]
        yield area


def capital_of(rows, barred=(), sides=None):
    sides = capital_sides(rows, barred) if sides is None else sides
    parent = {int(r["ID"]): int(r["ParentAreaID"] or 0) for r in rows}
    out = {}
    for area in parent:
        city = next((at for at in area_chain(parent, area) if at in sides), 0)
        if city:
            out[area] = city
    return out


def finder_ranges(maps, rows):
    ids = {}
    for mid, m in maps.items():
        if m.get("type") == 3 and m.get("name"):
            for name in {m["name"], m["name"].removeprefix("The ")}:
                ids.setdefault(name, []).append(int(mid))
    out = {}
    for r in rows:
        top = int(r.get("MaxLevelSuggestion") or 0)
        if top and not int(r.get("MaxPlayers") or 0):
            for mid in ids.get(r.get("FullName_lang"), ()):
                out[mid] = (int(r.get("MinLevel") or 0), top)
    return out


def held_to(levels, finder):
    out = {}
    for mid, (lo, hi) in levels.items():
        band = finder.get(mid)
        if band:
            lo, hi = max(lo, band[0]), min(hi, band[1])
            lo = min(lo, hi)
        out[mid] = (lo, hi)
    return out


def zone_tables(world, barred=()):
    import client
    import numpy as np
    rows = client.rows("AreaTable", stored=True)
    parent = {int(r["ID"]): int(r["ParentAreaID"] or 0) for r in rows}
    capitals = {world.geo.area_map.get(str(a)) for a in capital_sides(rows, barred)} - {None}
    try:
        finder = finder_ranges(world.geo.maps, client.rows("GroupFinderActivity", stored=True))
    except OSError:
        finder = {}
    levels = held_to(world.zone_levels(skip=capitals), finder)
    zone_of, lowest = np.zeros(max(parent) + 1, np.int64), np.zeros(max(parent) + 1, np.int64)
    for area in parent:
        *_, zone = area_chain(parent, area)
        zone_of[area] = zone
        mid = world.geo.area_map.get(str(zone))
        if mid in levels:
            lowest[area] = levels[mid][0]
    return {str(mid): list(v) for mid, v in levels.items()}, (zone_of, lowest)


def city_areas(rows, barred=()):
    out = np.zeros(max((int(r["ID"]) for r in rows), default=0) + 1, bool)
    out[list(capital_of(rows, barred))] = True
    return out


def capital_sides(rows, barred=()):
    import facts
    import opendungeons
    shut = {(opendungeons.norm(place), side) for place, side in barred}
    sides = {}
    for r in rows:
        named = [side for side, bit in facts.FACTION_BITS.items() if int(r.get("FactionGroupMask") or 0) & bit]
        if len(named) != 1:
            continue
        others = set(facts.FACTION_BITS) - set(named)
        if int(r.get("Flags_0") or 0) & CAPITAL or any((opendungeons.norm(r.get("AreaName_lang")), o) in shut for o in others):
            sides[int(r["ID"])] = named[0]
    return sides


def zone_pvp(maps, rows):
    import facts
    by_id = {int(r["ID"]): r for r in rows}
    out = {}
    for mid, m in maps.items():
        r = by_id.get(int(m.get("area") or 0)) if m.get("type") == 3 else None
        if not r:
            continue
        named = [side for side, bit in facts.FACTION_BITS.items() if int(r.get("FactionGroupMask") or 0) & bit]
        out[str(mid)] = ("sanctuary" if int(r.get("Flags_0") or 0) & NO_PVP else named[0] if len(named) == 1
                         else "contested")
    return out


def capital_table(rows, barred=()):
    import nav
    parent = {int(r["ID"]): int(r["ParentAreaID"] or 0) for r in rows}
    sides = capital_sides(rows, barred)
    area_city = np.zeros(max(parent, default=0) + 1, np.int64)
    for area, city in capital_of(rows, sides=sides).items():
        area_city[area] = city
    rooms = []
    for k, g in AREAS.items():
        m = MAPS.get(k) or {}
        city, w = int(m.get("area") or 0), m.get("world")
        if city not in sides or not w or m.get("instance") is None:
            continue
        runs = g["runs"]
        cells = np.repeat(np.array(runs[0::2], np.int64), runs[1::2])
        named = np.array(g["zones"], np.int64)[cells].reshape(g["rows"], g["cols"])
        rooms.append((m["instance"], city, w["top"], w["left"], g["cell"], named == int(k)))
    return nav.Capitals(area_city, sides, rooms)


def city_names(hub, cities):
    caps = getattr(getattr(hub, "paths", None), "capitals", None)
    out = []
    for city in cities:
        mid = hub.world.geo.area_map.get(str(city))
        m = MAPS.get(str(mid)) if mid is not None else None
        if m:
            out.append({"name": m.get("name"), "side": caps.side.get(int(city)) if caps else None})
    return out


def zone_names(hub, areas):
    out = []
    for area in areas:
        mid = hub.world.geo.area_map.get(str(area))
        m = MAPS.get(str(mid)) if mid is not None else None
        if m:
            out.append({"name": m.get("name"), "levels": hub.zone_levels.get(str(mid))})
    return out


ZONE_TABLES = ("AreaTable", "GroupFinderActivity")
_zone_lock = threading.Lock()


def zone_inputs():
    import client
    import game
    import opendungeons
    try:
        build = game.installed_version()
    except (OSError, game.GameNotFound):
        build = None
    copies = []
    for table in ZONE_TABLES:
        found = client.stored_copy(table, build) if build else None
        path = client.path_of(table, *found) if found else None
        try:
            copies.append((path, os.stat(path).st_mtime_ns) if path else None)
        except OSError:
            copies.append((path, None))
    return build, tuple(copies), tuple(opendungeons.barred())


def renew_zone_tables(hub):
    inputs = zone_inputs()
    if inputs == hub.zone_inputs:
        return False
    hub.zone_inputs = inputs
    start_thread("zone levels", set_zone_tables, (hub,))
    return True


def zones_unknown(hub):
    if hub.zones_set.is_set():
        return None
    return "the Index is still reading the zones' level ranges, which it does in the first seconds after it starts"


def set_zone_tables(hub):
    with _zone_lock:
        try:
            import client
            import opendungeons
            barred = opendungeons.barred()
            hub.zone_levels, walk_levels = zone_tables(hub.world, barred)
            rows = client.rows("AreaTable", stored=True)
            hub.zone_pvp = zone_pvp(MAPS, rows)
            hub.city_areas = city_areas(rows, barred)
            capitals = capital_table(rows, barred)
            hub.paths.set_tables(zone_levels=walk_levels, capitals=capitals)
            hub.world.set_cities(capitals, hub.paths.cities_at)
        except Exception:
            log_error("zone levels")
        finally:
            hub.zones_set.set()


def continents():
    return sorted({m["instance"] for m in MAPS.values() if m.get("type") == 2 and m.get("instance") is not None})
