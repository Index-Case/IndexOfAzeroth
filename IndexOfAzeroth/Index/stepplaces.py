# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import math
import os

import datafiles
import geo
import mapzones

PLACES = datafiles.data_path("placenames")
EDGE = 100.0
RINGS = 4
AROUND = 16


def records(folder=PLACES):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return
    for name in names:
        if not name.endswith(".json") or name.startswith("banner-"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        yield name[:-len(".json")], [p for p in ((rec.get("got") or {}).get("names") or ()) if isinstance(p, dict)]


def lettered(folder=PLACES):
    return {place["area"] for _, places in records(folder) for place in places if isinstance(place.get("area"), int)}


def area_places(rows, places):
    parent, name = {}, {}
    for r in rows:
        try:
            a = int(r["ID"])
        except (KeyError, ValueError, TypeError):
            continue
        parent[a] = int(r.get("ParentAreaID") or 0)
        name[a] = r.get("AreaName_lang") or ""
    out = {}
    for a in parent:
        at = next((at for at in mapzones.area_chain(parent, a) if at in places and name.get(at)), None)
        if at is not None:
            out[a] = name[at]
    return out


def zone_areas(rows):
    out = set()
    for r in rows:
        try:
            if not int(r.get("ParentAreaID") or 0):
                out.add(int(r["ID"]))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def place_finder(hub, rows=None, folder=PLACES):
    kept = {}

    def table():
        version = getattr(hub, "data_version", None)
        if kept.get("version") != version or "areas" not in kept:
            got = rows
            if got is None:
                try:
                    import client
                    got = client.rows("AreaTable", stored=True)
                except Exception:
                    got = []
            kept.update(version=version, areas=area_places(got, lettered(folder)), zones=zone_areas(got))
        return kept["areas"]

    def ground(inst, north, west):
        import nav
        with nav.wm.background():
            got, _ = hub.paths.ground_at(inst, north, west)
        return [int(a) for a in got]

    def find(inst, points):
        areas, zones = table(), kept["zones"]
        if not areas or not points:
            return [None] * len(points or ())
        got = ground(inst, [p[0] for p in points], [p[1] for p in points])
        out = [areas.get(a) for a in got]
        edge = [k for k, a in enumerate(got) if out[k] is None and a in zones]
        if edge:
            ring = [(EDGE * (r + 1) / RINGS, 2 * math.pi * j / AROUND) for r in range(RINGS) for j in range(AROUND)]
            north = [points[k][0] + d * math.cos(t) for k in edge for d, t in ring]
            west = [points[k][1] + d * math.sin(t) for k in edge for d, t in ring]
            around = ground(inst, north, west)
            for n, k in enumerate(edge):
                for a in around[n * len(ring):(n + 1) * len(ring)]:
                    if areas.get(a):
                        out[k] = areas[a]
                        break
        return out
    return find


def landmarks(pois):
    areas, names = set(), set()
    for r in pois or ():
        try:
            if int(r.get("Importance") or 0) <= 0:
                continue
            area = int(r.get("AreaID") or 0)
        except (ValueError, TypeError):
            continue
        if area > 0:
            areas.add(area)
        if r.get("Name_lang"):
            names.add(r["Name_lang"])
    return areas, names


def entrance_marks(dungeons, maps):
    spots = {}
    for d in dungeons if isinstance(dungeons, list) else ():
        for e in d.get("entrances") or ():
            m = maps.get(str(e.get("map")))
            if not (m and m.get("world")) or e.get("x") is None or e.get("y") is None:
                continue
            key = (str(e["map"]), round(float(e["x"]), 1), round(float(e["y"]), 1))
            spot = spots.setdefault(key, {"names": [], "kinds": set()})
            if d.get("name") and d["name"] not in spot["names"]:
                spot["names"].append(d["name"])
            spot["kinds"].add(d.get("kind"))
    out = {}
    for (mid, x, y), spot in spots.items():
        if not spot["names"]:
            continue
        heads = {n.split(":")[0].strip() for n in spot["names"]}
        name = heads.pop() if len(heads) == 1 else None
        north, west = geo.to_world(maps[mid]["world"], x / 100, y / 100)
        out.setdefault(mid, []).append((name, "dungeon" if "dungeon" in spot["kinds"] else "raid", north, west, spot["names"]))
    return out


def compass_places(maps, rows, pois, capitals, dungeons, folder=PLACES):
    marked_areas, marked_names = landmarks(pois)
    area_name = {}
    for r in rows or ():
        try:
            area_name[int(r["ID"])] = r.get("AreaName_lang") or ""
        except (KeyError, ValueError, TypeError):
            continue
    zone_of = {city: str(c.get("zone")) for city, c in (capitals or {}).items()
               if (maps.get(str(c.get("zone"))) or {}).get("world")}
    boxes = [(m["instance"], m["world"]) for mid, m in maps.items() if mid in (capitals or {}) and m.get("world")]

    def in_capital(inst, north, west):
        return any(i == inst and w["bottom"] <= north <= w["top"] and w["right"] <= west <= w["left"] for i, w in boxes)
    lettered_at = {}
    for mid, places in records(folder):
        m = maps.get(mid) or {}
        if not m.get("world") or mid in (capitals or {}):
            continue
        for p in places:
            name = area_name.get(p.get("area")) if isinstance(p.get("area"), int) else None
            lines = [ln for ln in p.get("lines") or () if isinstance(ln, dict)]
            if not name or not lines or any(q[0] == name for q in lettered_at.get(mid, ())):
                continue
            try:
                fx = (min(ln["x0"] for ln in lines) + max(ln["x1"] for ln in lines)) / 2
                fy = (min(ln["base"] - ln["cap"] for ln in lines) + max(ln["base"] for ln in lines)) / 2
            except (KeyError, TypeError):
                continue
            north, west = geo.to_world(m["world"], fx, fy)
            if not in_capital(m.get("instance"), north, west):
                town = p["area"] in marked_areas or name in marked_names
                lettered_at.setdefault(mid, []).append((name, north, west, town))
    out = {}

    def add(mid, name, kind, north, west):
        here = out.setdefault(mid, {"inst": (maps.get(mid) or {}).get("instance"), "at": []})
        if not any(p["n"] == name for p in here["at"]):
            here["at"].append({"n": name, "k": kind, "x": round(north, 1), "y": round(west, 1)})
    for city, zone in sorted(zone_of.items()):
        c = capitals[city]
        if c.get("name") and c.get("n") is not None:
            add(zone, c["name"], "city", c["n"], c["w"])
    gone = {}
    for mid, marks in entrance_marks(dungeons, maps).items():
        zone = zone_of.get(mid, mid) if mid in (capitals or {}) else mid
        for name, kind, north, west, names in marks:
            if name is None:
                near = [(math.hypot(n - north, w - west), q) for q, n, w, _ in lettered_at.get(zone, ())]
                near = min((x for x in near if x[0] <= EDGE), default=None)
                name = near[1] if near else ", ".join(names)
            add(zone, name, kind, north, west)
            gone.setdefault(zone, set()).update([name, *names])
    for mid, places in lettered_at.items():
        for name, north, west, town in places:
            if name not in gone.get(mid, ()):
                add(mid, name, "town" if town else "area", north, west)
    for city, zone in zone_of.items():
        if zone in out:
            out[city] = out[zone]
    return {mid: v for mid, v in sorted(out.items()) if v["at"]}


def load_compass_places(hub, folder=PLACES):
    import client
    import mainstores
    import mapzones
    import store

    def stored(table):
        try:
            return client.rows(table, stored=True)
        except Exception:
            return []
    index = store.load_json(os.path.join(mainstores.path("detailview"), "index.json"), {})
    capitals = index.get("capitals") if isinstance(index, dict) and isinstance(index.get("capitals"), dict) else {}
    dungeons = getattr(getattr(hub, "dungeons", None), "list", None)
    return compass_places(mapzones.MAPS, stored("AreaTable"), stored("AreaPOI"), capitals, dungeons, folder)


def step_places(steps, find):
    if not find:
        return None
    by_inst = {}
    for k, st in enumerate(steps):
        if st.get("at") and st.get("inst") is not None:
            by_inst.setdefault(st["inst"], []).append(k)
    names, number = [], {}
    found = {}
    for inst, ks in by_inst.items():
        got = find(inst, [steps[k]["at"][:2] for k in ks]) or []
        for k, name in zip(ks, got):
            if name:
                found[k] = name
    for k in sorted(found):
        name = found[k]
        if name not in number:
            names.append(name)
            number[name] = len(names)
        steps[k]["pl"] = number[name]
    return names or None
