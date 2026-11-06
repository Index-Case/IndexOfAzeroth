# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datetime, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import client
import dropguard


def fetch(table, build=None):
    return client.rows(table, build)


def grid(tiles):
    rows, cols = max(r for r, _ in tiles) + 1, max(c for _, c in tiles) + 1
    return [[tiles.get((r, c), 0) for c in range(cols)] for r in range(rows)]


def overlays(overlay_rows, tile_rows):
    tiles_of = {}
    for r in tile_rows:
        if r["LayerIndex"] == "0":
            tiles_of.setdefault(int(r["WorldMapOverlayID"]), {})[(int(r["RowIndex"]), int(r["ColIndex"]))] = int(r["FileDataID"])
    out, conditional, bare = {}, 0, 0
    for r in sorted(overlay_rows, key=lambda r: int(r["ID"])):
        tiles = tiles_of.get(int(r["ID"]))
        if int(r["PlayerConditionID"] or 0):
            conditional += 1
        elif not tiles:
            bare += 1
        else:
            out.setdefault(int(r["UiMapArtID"]), []).append({
                "x": int(r["OffsetX"]), "y": int(r["OffsetY"]), "width": int(r["TextureWidth"]),
                "height": int(r["TextureHeight"]), "files": grid(tiles)})
    return out, (conditional, bare)


def counts(data):
    maps = (data.get("maps") or {}).values()
    return {"maps": ("maps", len(maps)), "zones": ("zone maps", sum(1 for m in maps if m.get("type") == 3))}


def main():

    uimaps = {int(r["ID"]): r for r in fetch("UiMap")}
    art_of = {int(r["UiMapID"]): int(r["UiMapArtID"]) for r in fetch("UiMapXMapArt") if r["PhaseID"] == "0"}
    map_art = fetch("UiMapArt")
    style_of = {int(r["ID"]): int(r["UiMapArtStyleID"]) for r in map_art}
    glow_of = {int(r["ID"]): int(r["HighlightFileDataID"]) for r in map_art if int(r["HighlightFileDataID"] or 0)}
    layer_of = {int(r["UiMapArtStyleID"]): r for r in fetch("UiMapArtStyleLayer") if r["LayerIndex"] == "0"}
    tiles_of = {}
    for r in fetch("UiMapArtTile"):
        if r["LayerIndex"] == "0":
            tiles_of.setdefault(int(r["UiMapArtID"]), {})[(int(r["RowIndex"]), int(r["ColIndex"]))] = int(r["FileDataID"])
    overlays_of, (conditional, bare) = overlays(fetch("WorldMapOverlay"), fetch("WorldMapOverlayTile"))

    def art(ui_map_id):
        art_id = art_of.get(ui_map_id)
        layer = layer_of.get(style_of.get(art_id))
        tiles = tiles_of.get(art_id)
        if not layer or not tiles:
            return None
        out = {"width": int(layer["LayerWidth"]), "height": int(layer["LayerHeight"]), "tile": int(layer["TileWidth"]),
               "files": grid(tiles)}
        if overlays_of.get(art_id):
            out["overlays"] = overlays_of[art_id]
        return out

    maps, world_regions = {}, {}
    assignments = fetch("UiMapAssignment")
    for r in assignments:
        ui_map_id = int(r["UiMapID"])
        info = uimaps.get(ui_map_id)
        if info and info["Type"] == "1" and int(r["MapID"]) not in {g["instance"] for g in world_regions.get(ui_map_id, [])}:
            world_regions.setdefault(ui_map_id, []).append({
                "instance": int(r["MapID"]),
                "ui": [float(r["UiMin_0"]), float(r["UiMin_1"]), float(r["UiMax_0"]), float(r["UiMax_1"])],
                "world": {"left": float(r["Region_4"]), "right": float(r["Region_1"]),
                          "top": float(r["Region_3"]), "bottom": float(r["Region_0"])},
            })
    for ui_map_id, regions in world_regions.items():
        info = uimaps[ui_map_id]
        maps[ui_map_id] = {"name": info["Name_lang"], "type": 1, "parent": 0, "area": 0, "instance": -1, "regions": regions}
        if art(ui_map_id):
            maps[ui_map_id]["art"] = art(ui_map_id)
    for r in assignments:
        ui_map_id = int(r["UiMapID"])
        info = uimaps.get(ui_map_id)
        if not info or float(r["UiMin_0"]) != 0 or float(r["UiMax_0"]) != 1 or ui_map_id in maps:
            continue
        maps[ui_map_id] = {
            "name": info["Name_lang"],
            "type": int(info["Type"]),
            "parent": int(info["ParentUiMapID"]),
            "area": int(r["AreaID"]),
            "instance": int(r["MapID"]),
            "world": {
                "left": float(r["Region_4"]), "right": float(r["Region_1"]),
                "top": float(r["Region_3"]), "bottom": float(r["Region_0"]),
            },
        }
        if art(ui_map_id):
            maps[ui_map_id]["art"] = art(ui_map_id)
        if glow_of.get(art_of.get(ui_map_id)):
            maps[ui_map_id]["highlight"] = glow_of[art_of[ui_map_id]]
    out = {
        "source": f"the Forever client's UiMap and UiMapAssignment tables, build {client.installed_version()}",
        "built": datetime.date.today().isoformat(),
        "maps": {str(k): v for k, v in sorted(maps.items())},
    }
    path = os.path.join(ROOT, "data", "maps.json")
    dropguard.save_all([(path, out, (), {"counts": counts})])
    print(f"{len(maps)} maps written to {path}")
    drawn = [m["art"]["overlays"] for m in maps.values() if m.get("art", {}).get("overlays")]
    files = {f for each in drawn for o in each for row in o["files"] for f in row if f}
    print(f"{sum(map(len, drawn))} overlays on {len(drawn)} of them in {len(files)} tile files ({conditional} left out for "
          f"a player condition, {bare} with no tiles)")


if __name__ == "__main__":
    import builder
    builder.run(main)
