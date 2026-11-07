# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re

import datafiles

GUESS = True

OPEN_WORLD = "0"
UNUSED = re.compile(r"unused|delete|\*|prototype", re.I)


def placed_maps(maps):
    out = set()
    for m in (maps or {}).values():
        if m.get("instance") is not None:
            out.add(int(m["instance"]))
        for region in m.get("regions") or ():
            if region.get("instance") is not None:
                out.add(int(region["instance"]))
    return out


def hidden_places(map_rows, maps, doors):
    placed = placed_maps(maps)
    rows = {}
    for r in map_rows or ():
        try:
            mid, wdt = int(r["ID"]), int(r.get("WdtFileDataID") or 0)
        except (KeyError, ValueError):
            continue
        if r.get("InstanceType") == OPEN_WORLD and wdt and mid not in placed and not UNUSED.search(r.get("MapName_lang") or ""):
            rows[mid] = r
    out = {}
    for d in doors or ():
        inside, outside = d.get("inside") or [], d.get("outside") or []
        if not inside or not outside or len(outside) < 3:
            continue
        mid, came = int(inside[0]), int(outside[0])
        if mid not in rows or came not in placed:
            continue
        place = out.setdefault(mid, {"name": rows[mid].get("MapName_lang") or str(mid), "from": [], "doors": []})
        if came not in place["from"]:
            place["from"].append(came)
        place["doors"].append([came, round(float(outside[1]), 1), round(float(outside[2]), 1)])
    return out


def with_runs(places, movers):
    out = {}
    for mid, place in (places or {}).items():
        runs = [float(m["seconds"]) for m in movers or () if m.get("ends") and m.get("seconds")
                and int(m.get("map", -1)) == int(mid)]
        out[mid] = {**place, **({"seconds": max(runs)} if runs else {})}
    return out


def places_now(map_rows=None):
    if not GUESS:
        return {}
    if map_rows is None:
        import client
        map_rows = client.rows("Map", stored=True)
    maps = datafiles.load(datafiles.data_path("maps.json")).get("maps", {})
    routes = datafiles.load(datafiles.data_path("routes.json"))
    return with_runs(hidden_places(map_rows, maps, routes.get("doors", [])), routes.get("movers", []))
