# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import threading
import time

from dungeons import Dungeons, share_stars
from layers import WorldLayers, lay_gathered, service_names
from indoors import Indoors
from characters import Characters
import nav
from routes import Routes
from respawns import Respawns
from dangerous import Dangerous
from entrances import SeenEntrances
from gathered import Gathered
from heights_seen import SeenHeights
from fog import FogPictures
import moblevels
import races
from firespots import Firespots
from auction import Auctions
import questplan
from questpois import QuestPois
from offers import GiverAnswers
import mapzones
from mapzones import DUNGEON_NAMES, _zone_masks, continents, dungeon_name, renew_zone_tables, set_zone_tables
from gamedata import ITEM_TIPS, SPELL_TIPS, item_name, load_class_spells, load_rares, load_tiles, load_trainer_prices, stat_weights
import upgrades
from planning import _built, _routes_cache, _ways_cache, grade_state, measured_respawn, playing_char, stand_heights, standable
from handler import STARTED
import jsontext
import realign
import ticks
import camping
import legacy
import crates
import errands
import epicwatch
import hearth
import stepplaces
from serverlog import log_error, start_thread
from levelreport import LevelReports, unlocks
from talentplan import TalentRanks
from dayrecord import DayRecord
import game


class Hub:

    def __init__(self):
        self.cond = threading.Condition()
        self.version = 0
        self._sent, self._sent_lock = (-1, b""), threading.Lock()
        self.state = None
        self.tracking = None
        self.status = None
        self.bars = None
        self.entrances = {}
        self.link = {"ok": False, "message": "starting", "reads": 0, "errors": 0, "rate": 0.0}
        self.strip_tap = None
        self.read_at = 0.0
        self.dungeons = Dungeons()
        self.extra = {"run": None, "guide": None, "group": None, "quests": None, "data": None, "addons": None, "game": None,
                      "epic": None,
                      "questlog": None,
                      "loaded": None,
                      "auction": None,
                      "legacyPoints": None,
                      "director": None,
                      "loopStops": None,
                      "camps": None,
                      "questClick": None,
                      "updates": None}
        self.director_words = {}
        self.replan_heard = None
        self._grades = None
        self.tiles = load_tiles()
        self.world = WorldLayers()
        self.class_spells = load_class_spells()
        self.trainer_prices = load_trainer_prices()
        self.gathered = Gathered()
        self.gather_searches = {}
        self.rares = load_rares()
        self.dangerous = Dangerous()
        self.data_version = 0
        self.characters = Characters()
        self.levelreports = LevelReports()
        self.characters.leveled = self.levelreports.frame
        self.levelreports.build = lambda key, rep: level_unlocks(self, key, rep)
        self.talentranks = TalentRanks()
        self.dayrecord = DayRecord(logs_dir=logs_or_none, open_map=open_world_map, world=mapzones.world_pos,
                                   chars=self.characters.records)
        self.dayrecord.reports = self.levelreports
        self.dayrecord.spell_levels = lambda key: class_spell_levels(self, key)
        self.respawns = Respawns(realm_now=self.characters.realm)
        self.questpois = QuestPois()
        self.offers = GiverAnswers()
        nav.prune_cache()
        self.paths = nav.Paths()
        self.paths.populated_of = lambda inst: self.world.populated(inst)
        self.paths.room_indoors = lambda inst, n, w, z: room_indoors(self, inst, n, w, z)
        self.zone_levels = {}
        self.city_areas = None
        self.zone_inputs = None
        self.zones_set = threading.Event()
        renew_zone_tables(self)
        wire_world(self, self.world, wait=False)
        self.routes = Routes()
        self.entrances_seen = SeenEntrances(names=lambda map_id: dungeon_name(self, map_id))
        DUNGEON_NAMES.ready(self.data_version)
        self.routes.extra_doors = lambda: self.entrances_seen.doors({d["inside"][0] for d in self.routes.data.get("doors", ())})
        self.routes.reach = self.paths.reach
        self.characters.starting_taxi = lambda race, faction, class_id: self.routes.starting_flights(
            races.id_of(race, faction), class_id)
        self.firespots = Firespots()
        self.heights_seen = SeenHeights()
        self.fog = FogPictures()
        self.levels_seen = moblevels.learnt = moblevels.SeenLevels()
        self.auction = Auctions(realm_now=lambda: (self.characters.last() or {}).get("realm"),
                                faction_now=lambda: (self.characters.last() or {}).get("faction"))
        self.auction.told = lambda brief: self.publish(auction=brief)
        self.patches = None
        realign.REALIGN.told = self.publish
        realign.REALIGN.place_of = lambda instance, north, west: mapzones.place_name(self, instance, north, west)
        self.levelreports.resolve = self.characters.resolve
        self.characters.on_move = lambda old, new: move_character(self, old, new)
        for old, new in self.characters.moves():
            move_character(self, old, new)

    def publish(self, state=None, link=None, status=None, bars=None, **extra):
        with self.cond:
            for k, v in extra.items():
                if k == "quests" and v is not None and self.extra["quests"]:
                    v = {"log": v["log"], "done": {**self.extra["quests"]["done"], **v["done"]}}
                self.extra[k] = v
            if bars is not None:
                self.bars = bars
            if state is not None:
                self.state = state
            if status is not None:
                self.status = status
            if link is not None:
                self.link.update(link)
            self.version += 1
            self.cond.notify_all()

    def snapshot(self):
        sh = getattr(self, "shared", None)
        pd = getattr(self, "pending", None)
        dv = getattr(self, "dev", None)
        nf = getattr(self, "navfill", None)
        current = self.characters.current
        who, was = playing_char(self), self.characters.was(current)
        with self.cond:
            version = self.version
            body = {"state": self.state, "status": self.status, "bars": self.bars,
                    "link": dict(self.link), **self.extra}
        return version, {**body, "time": time.time(), "cap": self.dungeons.cap(),
                         "versions": {"respawns": self.respawns.version, "characters": self.characters.version,
                                      "patches": self.patches.version if self.patches else 0,
                                      "heights": self.heights_seen.version,
                                      "fog": self.fog.version,
                                      "auction": self.auction.version,
                                      "levels": getattr(getattr(self, "levelreports", None), "version", 0),
                                      "todo": getattr(getattr(self, "moves", None), "version", 0),
                                      **(dv.versions() if dv else {})},
                         "started": STARTED,
                         "character": current,
                         "who": who,
                         "was": was,
                         "lastSeen": self.characters.last_seen(mapzones.zone_map_named) if not body["state"] or self.strip_lost(body["link"])
                         else None,
                         "fires": self.firespots.live(current),
                         "maxLevel": self.characters.max_level(),
                         "options": self.characters.options(),
                         "stars": self.dungeons.stars_of(current),
                         "plan": {**sh.brief(), "playing": who,
                                  "advice": getattr(getattr(self, "watch", None), "advice", None)}
                                 if sh else None,
                         "pending": pd.brief() if pd else None,
                         "realign": realign.state(body.get("data")),
                         "navfill": nf.brief() if nf else None,
                         "campfire": ticks.campfire_on(self),
                         "crates": crate_lines(self, body.get("status")),
                         "grades": grade_lines(self, body.get("epic")),
                         "professions": (self.characters.playing() or {}).get("professions", [])}

    def strip_lost(self, link, now=None):
        from strip import STRIP_GAP
        return not link.get("ok") and (now or time.time()) - self.read_at > STRIP_GAP

    def encoded(self):
        with self._sent_lock:
            if self._sent[0] != self.version:
                version, snap = self.snapshot()
                message = b"data: " + jsontext.dumps(snap).encode() + b"\n\n"
                if version >= self._sent[0]:
                    self._sent = (version, message)
                return version, message
            return self._sent


def move_character(hub, old, new):
    if not old or not new or old == new:
        return False
    moved = {"levels": hub.levelreports.move(old, new), "days": hub.dayrecord.move(old, new),
             "stars": hub.dungeons.move(old, new), "fires": hub.firespots.move(old, new), "pace": hub.world.pace.move(old, new)}
    if moved["stars"] and getattr(hub, "shared", None):
        start_thread("stars", share_stars, (hub,))
    return any(moved.values())


def level_unlocks(hub, key, rep):
    try:
        return unlocks(hub, key, rep)
    except Exception:
        log_error("working out what a level opened")
        return None


def logs_or_none():
    try:
        return game.logs_dir()
    except game.GameNotFound:
        return None


def open_world_map(map_id):
    m = mapzones.MAPS.get(str(map_id))
    return bool(m and m.get("type") in (2, 3) and m.get("world"))


def class_spell_levels(hub, key):
    c = (hub.characters.data.get("chars") or {}).get(key) or {}
    sched = (((hub.class_spells or {}).get("classes") or {}).get(str(c.get("classId"))) or {}).get("levels")
    if not sched:
        return None
    out = {}
    for lv in sorted(sched, key=int):
        for s in (sched[lv] or {}).get("spells") or ():
            out.setdefault(s.get("name"), int(lv))
    return out



def wire_world(hub, world, wait):
    world.measured_respawn = measured_respawn(hub)
    world.respawns_version = lambda: hub.respawns.version
    world.stand_at = lambda inst, pts: standable(hub, inst, pts)
    world.stand_heights = lambda inst, stops, spawns: stand_heights(hub, inst, stops, spawns)
    world.ah_prices = lambda: hub.auction.loop_prices() if getattr(hub, "auction", None) else (None, {})
    world.pace.current = hub.characters.current
    world.level_cap = hub.characters.max_level
    world.on_events = lambda: forget_ways(hub)
    world.emptied = lambda: hub.trackdots.emptied() if getattr(hub, "trackdots", None) else ()
    if wait:
        world.apply_gathered(hub.gathered.all())
    else:
        lay_gathered(world, hub.gathered.all)
    start_thread("populated", lambda: [world.populated(i) for i in continents()], again=True)
    return world


def forget_ways(hub):
    hub.paths.forget_ways()
    for kept in (_ways_cache, _routes_cache, _built):
        kept.clear()


def room_indoors(hub, inst, north, west, z):
    finder = getattr(hub, "indoors", None)
    if finder is None:
        return None
    try:
        return finder.indoor_at(inst, north, west, z)
    except (OSError, ValueError, KeyError, RuntimeError):
        return None


def reload_data(hub):
    mapzones.reload_maps()
    hub.indoors = Indoors()
    was = hub.dungeons
    world = wire_world(hub, WorldLayers(), wait=True)
    hub.tiles, hub.world, hub.dungeons, hub.rares = load_tiles(), world, Dungeons(), load_rares()
    hub.class_spells = load_class_spells()
    hub.dungeons.last_run, hub.dungeons.stars, hub.dungeons.unclaimed = was.last_run, was.stars, was.unclaimed
    hub.respawns.reload()
    hub.paths.reset()
    hub.routes.reload()
    hub.dangerous.load()
    set_zone_tables(hub)
    hub.data_version += 1
    for kept in (_ways_cache, _routes_cache, _zone_masks, _built):
        kept.clear()
    ITEM_TIPS.forget()
    SPELL_TIPS.forget()
    questplan.book()
    try:
        share_watch(hub)
    except OSError:
        log_error("writing the watch list into Shared.lua")


def crate_lines(hub, status):
    try:
        bags = getattr(hub.characters, "bags_now", lambda: None)()
        return crates.lines(bags, ((status or {}).get("strs") or {}).get("faction"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log_error("the Waylaid Crates' To do lines")
        return []


GRADE_STEP = 10.0


def grade_lines(hub, live):
    try:
        s, nums = hub.state or {}, ((hub.status or {}).get("nums") or {})
        pos, world = s.get("pos"), getattr(hub, "world", None)
        if not pos or s.get("map") is None or world is None:
            return {}
        me = grade_state(hub)
        here = world.geo.to_world(s["map"], pos["x"], pos["y"])
        things = tuple(t for t in errands.GRADED if f"{t}Grade" in nums)
        key = (things, me["level"], me["faction"], me["ammo_kind"], tuple(sorted(me["grades"].items())),
               errands.makes(me, "water"), here and (here[2], round(here[0] / GRADE_STEP), round(here[1] / GRADE_STEP)))
        kept = getattr(hub, "_grades", None)
        if not kept or kept[0] != key or kept[1] is not world.services:
            found = {t: errands.better_grade(world, t, me, s["map"], pos["x"], pos["y"]) for t in things}
            kept = hub._grades = (key, world.services, {t: {"item": g["item"], "name": item_name(g["item"]) or "",
                                                            "npc": g["npc"]["name"], "zone": g["npc"]["zone"]}
                                                        for t, g in found.items() if g})
        sh = getattr(hub, "shared", None)
        due = epicwatch.restocks_due(live, sh.data if sh else None, nums.get("sharedVersion"))
        lines = {t: line for t, line in kept[2].items() if t not in due}
        for t, at in due.items():
            sv = world.service(at["npc"]) if t in things else None
            item = errands.chore_buy(sv, t, me)
            if item and at.get("at"):
                zone = world.service_zone(sv)
                lines[t] = {"item": item, "name": item_name(item) or "", "npc": sv["n"], "zone": zone, "planned": True,
                            "to": {"name": sv["n"], "sub": sv.get("sub") or "", "cat": min(errands.RESTOCK[t][1]), "zone": zone,
                                   "wx": at["at"][0], "wy": at["at"][1], "wz": sv.get("z"), "instance": at.get("inst")}}
        return {t: line for t, line in lines.items() if line["name"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log_error("the To do's lines for a better grade")
        return {}


def share_watch(hub):
    watch = ticks.load_watch()
    if not getattr(hub, "shared", None):
        return False
    world = getattr(hub, "world", None)
    if watch:
        watch = {**watch, "camps": camping.restock(camping.load(), getattr(world, "services", None) or ())}
    wrote = hub.shared.set_watch(watch)
    wrote = hub.shared.set_legacy(legacy.share_list()) or wrote
    wrote = hub.shared.set_services(service_names(world.services if world else ())) or wrote
    routes = getattr(hub, "routes", None)
    wrote = hub.shared.set_towns(hearth.towns((getattr(routes, "data", None) or {}).get("inns", ()))) or wrote
    wrote = hub.shared.set_roles(upgrades.tree_roles(stat_weights())) or wrote
    return hub.shared.set_places(stepplaces.load_compass_places(hub)) or wrote
