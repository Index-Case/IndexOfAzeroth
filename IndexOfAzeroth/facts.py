# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datafiles

MAX_LEVEL = 60
RUN_SPEED = 7.0
TILE_YARDS = 1600 / 3
MAP_CORNER = 32 * TILE_YARDS
FACTION_BITS = {"Alliance": 2, "Horde": 4}
LEVELS = datafiles.data_path("levels.json")
MAPS = datafiles.data_path("maps.json")


def faction_bit(side):
    return FACTION_BITS.get(side, 0)


_xp = {"from": None, "table": {}}


def xp_table():
    data = datafiles.load(LEVELS, {})
    if _xp["from"] is not data:
        _xp["table"], _xp["from"] = {int(k): v for k, v in (data.get("xpToNext") or {}).items()}, data
    return _xp["table"]


def xp_to_next(level):
    return xp_table().get(level)


def continents():
    return sorted({m["instance"] for m in (datafiles.load(MAPS, {}).get("maps") or {}).values()
                   if m.get("type") == 2 and m.get("instance") is not None})


def open_world(maps=None):
    if maps is None:
        maps = datafiles.load(MAPS, {}).get("maps") or {}
    return sorted({int(m["instance"]) for m in maps.values()
                   if m.get("type") in (2, 3) and m.get("instance") is not None and int(m["instance"]) >= 0})
