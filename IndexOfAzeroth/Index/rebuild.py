# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import sys

import store

LOADED_ONLY = ("data",)
NAMED_ONLY = ("suites",)
ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(DATA, "rebuild.log")

COMMANDS = {"maps": ["build_maps.py"], "tiles": ["build_tiles.py"], "levels": ["build_levels.py"],"icons": ["build_icons.py"], "items": ["build_items.py"], "objectives": ["build_objectives.py"],
            "quests": ["build_quests.py"],
            "giverwalks": ["build_giver_walks.py"],
            "questtext": ["build_questtext.py"],
            "blurbs": ["build_blurbs.py"],
            "questplaces": ["build_quest_places.py"],
            "pictures": ["build_pictures.py"],
            "uipictures": ["build_ui_pictures.py"],
            "paperup": ["build_paperup.py"],
            "world": ["build_world.py"], "drops": ["build_drops.py"], "respawns": ["build_respawns.py"], "rares": ["build_rares.py"], "dungeons": ["build_dungeons.py"], "routes": ["build_routes.py"], "trails": ["build_trails.py"], "gear": ["build_gear.py"],
            "statweights": ["build_statweights.py"], "portraits": ["build_portraits.py"],
            "classfill": ["build_class_fill.py"], "classspells": ["build_class_spells.py"],
            "classquests": ["build_class_quests.py"],
            "talentbuilds": ["build_talent_builds.py"],
            "dungeonmaps": ["build_dungeon_minimaps.py"],
            "dungeonbake": ["build_dungeon_bake.py"],
            "heights": ["build_heights.py"],
            "trees": ["build_trees.py"],
            "render": ["build_render.py"],
            "detailview": ["build_detailview.py"],
            "clouds": ["build_clouds.py"],
            "sea": ["build_seafield.py"],
            "inland": ["build_inlandfield.py"],
            "seamask": ["build_seamask.py"],
            "underground": ["build_underground.py"],
            "seagiants": ["build_seagiants.py"],
            "lighttint": ["build_lighttint.py"],
            "torches": ["build_torches.py"],
            "professionfill": ["build_profession_fill.py"], "professions": ["build_professions.py"],
            "books": ["build_books.py"],
            "cities": ["build_cities.py"],
            "tables": ["build_tables.py"],
            "listfile": ["build_listfile.py"],
            "areasources": ["build_area_sources.py"],
            "tooltips": ["build_tooltips.py"],
            "shieldblock": ["build_shield_block.py"],
            "prompts": ["build_prompts.py"],
            "taxistarts": ["build_taxi_starts.py"],
            "fishingspots": ["build_fishing_spots.py"],
            "roadways": ["build_roadways.py"],
            "words": ["gen_words.py"]}
LISTED = {kind: f"buildcache/listfile-{kind}.csv" for kind in ("db2", "wmo", "m2", "terrain", "treetextures", "crests")}
LISTED["ui"] = "buildcache/listfile-ui-0e6b94bd.csv"
OUTPUTS = {"maps": ["maps.json"], "tiles": ["tiles.json"], "icons": ["icons_fallback/", "icons_fallback.json"], "items": ["items.json", "spells.json"],
           "listfile": sorted(LISTED.values()),
           "levels": ["levels.json"], "objectives": ["objectives.json"], "quests": ["quests.json"],
           "giverwalks": ["giver_walks.json"],
           "questtext": ["questtext.json"], "blurbs": ["blurbs.json"], "questplaces": ["quest_places.json"],
           "trails": ["npc_trails.npz", "patrols.npz", "escorts.json"], "world": ["world.json", "places_listed.json"],
           "drops": ["drops.json"], "classfill": ["classfill.json"], "classspells": ["classspells.json"], "classquests": ["classquests.json"], "talentbuilds": ["talentbuilds.json"], "respawns": ["respawns.json"], "rares": ["rares.json"],
           "dungeons": ["dungeons.json"], "portraits": ["portraits.json"], "gear": ["gear.json"],
           "statweights": ["stat_weights.json"], "routes": ["routes.json"], "dungeonmaps": ["dungeonmaps/", "dungeonmaps.json"],
           "dungeonbake": ["dungeonbake/", "dungeonbake.json"],
           "heights": ["heights/"], "trees": ["trees/"], "render": ["rendertiles/", "rendertiles/hidden.json"], "detailview": ["detailview/", "placenames/"],
           "clouds": ["clouds/"], "sea": ["seafield/"], "inland": ["inlandfield/"], "seamask": ["seamask/"], "underground": [], "seagiants": [], "lighttint": ["lighttint.json"], "torches": ["torches.json"], "pictures": ["pictures/"], "uipictures": ["uicache/"], "paperup": ["paperup/"], "professionfill": ["professionfill.json"], "professions": ["professions.json"],
           "books": ["books.json"], "cities": ["cities.json"], "tables": ["tables.json"],
           "areasources": ["area_sources.json"],
           "shieldblock": ["shield_block.json", "buildcache/shield_block_filled.json"],
           "tooltips": ["tooltips.json", "tooltips/", "tooltips_fallback.json"],
           "prompts": ["buildcache/prompt-rules.json"], "taxistarts": ["taxistarts.json"],
           "fishingspots": ["fishing_spots.json", "buildcache/fishing_tiles.json"], "roadways": ["roadways.json"],
           "words": []}
ELSEWHERE = {"words": ["web/words.js"], "underground": ["web/art/underground/"], "seagiants": ["web/art/seagiants/"]}
ADDON_FILES = {"words": ["Words.lua"], "dungeons": ["DungeonData.lua"],
               "classspells": ["ClassTrainers.lua", "Vendors.lua"]}
MAIN_ONLY = {"prompts"}
INPUTS = {"tiles": ["maps.json"], "cities": ["maps.json"],
          "tables": [LISTED["db2"]],
          "icons": ["classspells.json"], "objectives": ["maps.json", "items.json"], "quests": ["maps.json", "items.json"],
          "clouds": ["tiles.json"],
          "giverwalks": ["maps.json"],
          "questtext": ["quests.json"],
          "blurbs": ["quests.json", "questtext.json", "objectives.json", "items.json", "escorts.json", "maps.json",
                     "dungeons.json"],
          "questplaces": ["quests.json", "questtext.json", "objectives.json", "maps.json", "tables.json"],
          "world": ["maps.json", "patrols.npz", "quests.json", "items.json"],
          "classfill": ["world.json", "professions.json"], "classspells": ["world.json", "classfill.json"],
          "classquests": ["quests.json", "classspells.json"],
          "talentbuilds": ["classspells.json", "stat_weights.json"],
          "rares": ["maps.json", "items.json", "world.json"],
          "drops": ["world.json", "items.json"],
          "dungeons": ["maps.json", "tiles.json", "world.json", "quests.json", "tooltips.json", "items.json"],
          "portraits": ["dungeons.json", "maps.json", "quests.json"],
          "gear": ["dungeons.json", "tooltips.json"],
          "routes": ["maps.json", "world.json", "dungeons.json", LISTED["wmo"], LISTED["terrain"], LISTED["ui"]],
          "dungeonmaps": ["dungeons.json", LISTED["wmo"]],
          "dungeonbake": ["dungeonmaps.json", "dungeons.json", "tiles.json", "pictures/", "respawns.json"],
          "pictures": ["dungeons.json", "maps.json", "tiles.json"],
          "uipictures": [LISTED["ui"]],
          "paperup": ["maps.json", "dungeons.json", "pictures/"],
          "heights": ["maps.json", "tiles.json", LISTED["wmo"], LISTED["m2"], LISTED["treetextures"]],
          "trees": ["maps.json", "tiles.json", "rendertiles/"],
          "render": ["maps.json", "tiles.json", "heights/", "world.json", "area_sources.json", LISTED["wmo"], LISTED["m2"],
                     LISTED["treetextures"]],
          "lighttint": ["maps.json"],
          "torches": ["maps.json", "tiles.json", LISTED["m2"]],
          "detailview": ["maps.json", "tiles.json", "pictures/", "rendertiles/", "dungeons.json", LISTED["crests"]],
          "sea": ["rendertiles/"],
          "inland": ["rendertiles/", "heights/"],
          "seamask": ["rendertiles/", "maps.json"],
          "professionfill": ["maps.json", "world.json"], "professions": ["professionfill.json"],
          "books": ["maps.json", "items.json", "quests.json"],
          "tooltips": ["classspells.json", "shield_block.json", "buildcache/shield_block_filled.json"],
          "fishingspots": ["professions.json", "tiles.json", "maps.json", "tables.json", LISTED["wmo"], LISTED["terrain"]],
          "roadways": ["tiles.json", "maps.json", "tables.json", "heights/", LISTED["wmo"], LISTED["terrain"]]}
USUAL = ["words", "listfile", "tables", "maps", "cities", "areasources", "tiles", "icons", "items", "levels", "objectives", "quests", "giverwalks", "questtext", "blurbs", "questplaces", "trails", "world", "drops", "classfill", "classspells", "classquests",
         "respawns", "rares", "dungeons", "portraits", "gear", "statweights", "routes", "dungeonmaps", "heights", "trees", "render", "clouds", "seamask", "sea", "inland", "underground", "seagiants", "lighttint", "torches", "pictures", "uipictures", "dungeonbake", "paperup",
         "detailview", "professionfill", "professions", "fishingspots", "roadways",
         "books", "shieldblock", "tooltips", "taxistarts", "talentbuilds", "prompts"]
STORE_STEPS = {"tables", "tooltips", "prompts", "shieldblock", "questtext", "blurbs", "listfile", "words"}
ART_STEPS = {"clouds", "seamask", "underground", "seagiants", "trees"}
CLIENT_STEPS = {"maps", "items", "tooltips", "gear", "classspells", "professions", "uipictures"}


def reads(step, outputs):
    return bool(set(INPUTS.get(step, ())) & set(outputs))


def readers():
    return {s: [t for t in USUAL if reads(t, OUTPUTS.get(s, ()))] for s in USUAL}


def ordered():
    down = readers()
    waiting = {s: {t for t in USUAL if s in down[t]} for s in USUAL}
    out = []
    while len(out) < len(USUAL):
        ready = [s for s in USUAL if s not in out and not waiting[s] - set(out)]
        if not ready:
            raise ValueError(f"builders reading each other's output: {[s for s in USUAL if s not in out]}")
        out.append(ready[0])
    return out


DOWNSTREAM = readers()
ORDER = ordered()


def step_of(builder):
    if builder in COMMANDS:
        return builder
    return next((step for step, command in COMMANDS.items() if command[0] == f"build_{builder}.py"), None)


def downstream(step, steps=None):
    out, todo = set(), list(DOWNSTREAM.get(step, ()))
    while todo:
        s = todo.pop()
        if s not in out:
            out.add(s)
            todo += DOWNSTREAM.get(s, ())
    return [s for s in ORDER if s in out and (steps is None or s in steps)]


def upstream(steps):
    below = {s: set(downstream(s, steps)) for s in steps}
    return {t: {s for s in steps if s != t and t in below[s]} for t in steps}


def overlap(a, b):
    def inside(x, y):
        return x == y or (y.endswith("/") and x.startswith(y))
    return any(inside(x, y) or inside(y, x) for x in OUTPUTS.get(a, ()) for y in OUTPUTS.get(b, ()))

TRAFFIC_LOG = os.path.join(ROOT, "data", "traffic.log")
LAUNCH = []


def written(step):
    return [f"data/{name}" for name in OUTPUTS.get(step, ())] + list(ELSEWHERE.get(step, ()))


def addon_written(step):
    return list(ADDON_FILES.get(step, ()))


def running_step():
    step = step_of(store.running_builder())
    return step if step and sys.argv[1:] == COMMANDS[step][1:] else None
