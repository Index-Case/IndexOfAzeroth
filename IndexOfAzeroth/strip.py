# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import time

from dungeons import share_stars
from protocol import WATCHED_WHOLE, StripError, assemble_bars, is_test_pattern, parse_frame
from linkstats import LinkStats
from epicwatch import report_key
import errands
from layers import XpAuras, lay_gathered
import questplan
from mapzones import settle_zone, world_pos
from planning import OBJECTIVES, camp_purchase, epic_stop_or_start, grade_state, note_profession_trainer, note_trainer, replan_asked
from routes import FLY
from serverlog import log_error, log_note, start_thread
import game
from reloads import Reloads
import ticks
import regen
from gamedata import ITEM_TIPS
from gamedata import item_name


READ_INTERVAL = 1 / 15
SCAN_READ_INTERVAL = 1 / 30

STRIP_GAP = 2.0


def note_walked(hub, state, last):
    flags = state.get("flags") or {}
    pos = state.get("pos")
    if not pos or not state.get("map") or flags.get("taxi") or flags.get("ghost") or flags.get("instance"):
        return None
    here = world_pos(state["map"], pos["x"], pos["y"])
    if not here:
        return None
    now = time.time()
    if last and last[0] == here[0]:
        dist = math.hypot(here[1] - last[1], here[2] - last[2])
        if 0.5 < dist < 60 and dist / max(0.05, now - last[3]) < 40:
            hub.paths.terrain.walked(here[0], last[1:3], here[1:3])
        elif dist <= 0.5:
            return last
    return (*here, now)


DUNGEON_KINDS = ("party", "raid")


def no_place_inside(state):
    inst = state.get("instance")
    if inst and inst.get("kind") in DUNGEON_KINDS:
        inst["world"] = state["pos"] = None


class Pages:

    def __init__(self):
        self.sends = {}

    def add(self, key, page, pages, content):
        got = self.sends.setdefault(key, {})
        got[page] = content
        if len(got) < pages:
            return None
        self.sends.clear()
        return [got[k] for k in sorted(got)]


def name_items(index, e, q):
    also = [q["item"]] if q and q.get("item") else []
    for line in [*e["objectives"], *([e] if e.get("text") else [])]:
        found = index.quest_item(e["id"], line.get("text"), also)
        if found:
            line["item"], line["itemName"] = found


def take_questlog(hub, coming, data):
    pages = coming.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data["entries"])
    if pages is None:
        return None
    entries = [e for page in pages for e in page]
    book = questplan.book()
    if hub.questpois.note(entries, book, lambda m, x, y: world_pos(m, x / 100, y / 100)) and getattr(hub, "watch", None):
        hub.watch.poke()
    for e in entries:
        q = "id" in e and not e["objectives"] and book.quests.get(e["id"])
        if q and q.get("objective"):
            e["text"] = q["objective"]
    index = OBJECTIVES.ready(hub.data_version)
    for e in entries if index else ():
        if "id" in e:
            name_items(index, e, book.quests.get(e["id"]))
    for e in entries:
        learnt = "id" in e and "poi" not in e and not e.get("failed") and hub.questpois.kept(e["id"], e.get("complete"))
        if learnt:
            e["poiLearnt"] = learnt
    held, char = hub.extra.get("questlog") or {}, hub.characters.current
    if not hub.characters.confirmed() or (held.get("char") == char and held.get("entries") == entries):
        return None
    return {"char": char, "at": round(time.time()), "entries": entries}


PARTY_GONE_LEAST = 10.0


def party_gone_after(stats, now):
    return max(PARTY_GONE_LEAST, 2 * (stats.most("group", now) or 0))


CHARACTER_EXTRAS = ("run", "guide", "group", "quests", "epic", "questlog", "loaded", "equipped", "rolls", "auras",
                    "watched", "queue", "legacyPoints", "director", "loopStops", "camps")


def game_epic_report(hub, report):
    watch = getattr(hub, "watch", None)
    if watch:
        watch.queue(lambda: epic_stop_or_start(hub, report))
        watch.poke()


class Reading:

    def __init__(self):
        self.bar_pages, self.bar_report = Pages(), None
        self.containers = {}
        self.completed = Pages()
        self.spellbook = Pages()
        self.petbook = Pages()
        self.trainer = Pages()
        self.proftrainer = Pages()
        self.recipes = Pages()
        self.questlog = Pages()
        self.explored = Pages()
        self.group_seen = 0.0
        self.new_character()
        self.worn = None, 0
        self.read()

    def new_character(self):
        self.health_guess = HealthGuess()
        self.idle = IdleWatch()
        self.kill_xp_seen = {"xp": None, "at": 0.0, "level": None}
        self.kill_xp = KillXp()
        self.pace_seen = {}
        self.walked = None

    def read(self):
        self.state = self.status = self.bars = None
        self.extra = {}


FRAME_KINDS = {}


def handles(kind):
    def register(handler):
        FRAME_KINDS[kind] = handler
        return handler
    return register


def keep_extra(hub, r, kind, data):
    if hub.extra.get(kind) != data:
        r.extra[kind] = data


def day_record(hub):
    rec = getattr(hub, "dayrecord", None)
    return rec if rec and hub.characters.confirmed() is not None else None


class HealthGuess:
    SETTLE_S = 6

    def __init__(self):
        self.sent, self.health, self.fighting, self.dead = None, None, False, False
        self.most, self.at, self.inputs = None, None, {}
        self.events, self.moved, self.hit = None, None, None
        self.quiet, self.framed, self.calm = None, None, None

    def grow(self, now):
        if self.health is not None and self.most and self.at is not None and not self.dead:
            got = regen.per_second(self.inputs, self.fighting, now) * (now - self.at) * 100 / self.most
            self.health = min(100.0, self.health + got)
        self.at = now

    def regen_frame(self, data, now):
        self.grow(now)
        self.most = data["most"] or self.most
        self.inputs.update(spirit=data["spirit"], buffs=[{**b, "ends": now + b["left"] if b["left"] else None}
                                                          for b in data["buffs"]])
        if self.events is not None and data["events"] > self.events and not self.fighting:
            self.moved = now
        if data["events"] != self.events:
            self.quiet = now
        self.events, self.framed = data["events"], now

    def take(self, hits, flags, now):
        self.grow(now)
        combat, dead = flags.get("combat"), bool(flags.get("dead") or flags.get("ghost"))
        if self.dead and not dead:
            self.health = None
        self.dead = dead
        if combat and not self.fighting:
            self.health = 100.0 if self.health is None else self.health
        if combat or dead:
            self.moved = None
        self.fighting = combat
        self.calm = None if combat or dead else now if self.calm is None else self.calm
        self.take_hits(hits, now)
        if self.calm is not None and (self.hit is None or now - self.hit >= self.SETTLE_S) and self.settled(now):
            self.health = 100.0
            self.moved = None
        return None if self.health is None else round(self.health, 1)

    def settled(self, now):
        if self.moved is not None:
            return now - self.moved >= self.SETTLE_S
        return self.framed is not None and self.framed - max(self.quiet, self.calm) >= self.SETTLE_S

    def take_hits(self, hits, now):
        if hits is None:
            return
        self.most = hits["most"] or self.most
        count = hits["count"]
        new = 0 if self.sent is None else count - self.sent if count >= self.sent else count
        self.sent = count
        for e in hits["last"][-new:] if new else ():
            if self.health is not None and hits["most"] and e["amount"]:
                share = e["amount"] * 100 / hits["most"]
                self.health = min(100.0, max(0.0, self.health + (share if e["kind"] == "heal" else -share)))
                self.hit = now if e["kind"] == "hit" else self.hit


class IdleWatch:

    def __init__(self):
        self.top, self.acts = None, None

    def take(self, act, fighting, health):
        if act is None:
            return None
        if act["acts"] != self.acts:
            self.top = None
        self.acts = act["acts"]
        if not fighting or act["busy"] or health is None:
            self.top = health
            return 0
        self.top = health if self.top is None else max(self.top, health)
        return int(self.top - health + 1e-6)


def health_now(r, state, hits=None):
    guess = r.health_guess.take(hits, state.get("flags") or {}, time.time())
    state["healthGuess"] = guess
    lost = r.idle.take(state.get("act"), (state.get("flags") or {}).get("combat"), guess)
    if lost is not None:
        state["idleLost"] = lost


@handles("hits")
def take_hits(hub, r, data):
    if r.state is not None:
        health_now(r, r.state, data)
    else:
        r.health_guess.take(data, (hub.state or {}).get("flags") or {}, time.time())


@handles("regen")
def take_regen(hub, r, data):
    me = hub.characters.confirmed() or {}
    worn = me.get("equipped") or {}
    keys = [k for k in worn.get("keys") or worn.get("items") or () if k]
    if keys != r.worn[0]:
        r.worn = keys, regen.gear_hp5(ITEM_TIPS.stats(k) for k in keys)
    r.health_guess.inputs.update({"class": (r.status or hub.status or {}).get("classId"), "race": me.get("race"),
                                  "hp5": r.worn[1]})
    r.health_guess.regen_frame(data, time.time())
    if getattr(hub, "levelreports", None) and hub.characters.confirmed() is not None:
        hub.levelreports.vitals(hub.characters.current, data.get("most"), data.get("spirit"))


@handles("position")
def take_position(hub, r, data):
    no_place_inside(data)
    settle_zone(data)
    health_now(r, data)
    r.state, r.player_map = data, data["map"]
    here = data.get("pos") and world_pos(data["map"], data["pos"]["x"], data["pos"]["y"])
    if here:
        hub.respawns.watch(here)
    hub.entrances_seen.watch(data, here)
    r.walked = note_walked(hub, data, r.walked)
    watch = getattr(hub, "watch", None)
    if watch:
        watch.moved(here or None, data.get("flags"))
    note_kill_pace(hub, data, r.pace_seen)
    rec = day_record(hub)
    if rec:
        rec.position(hub.characters.current, data)
    if r.kill_xp.gains:
        note_gains(hub, r.kill_xp)


@handles("status")
def take_status(hub, r, data):
    r.status = data
    n = data.get("nums") or {}
    hub.updates.note_status(n)
    rec = day_record(hub)
    if rec:
        rec.money(hub.characters.current, n.get("money"))
    if getattr(hub, "moves", None):
        hub.moves.seen(data, r.bars)
    if r.kill_xp.frames:
        return
    gained, seen = n.get("lastKillXP"), r.kill_xp_seen
    if gained and gained != seen["xp"]:
        seen.update(xp=gained, at=time.time(), level=(hub.state or {}).get("level"),
                    rested=bool(n.get("lastKillRested")), group=bool((hub.extra.get("group") or {}).get("members")))
    elif gained is not None:
        seen["xp"] = gained


@handles("retired")
def take_retired(hub, r, data):
    pass


@handles("bars")
def take_bars(hub, r, data):
    pages = r.bar_pages.add(data["version"], data["page"], data["pages"], data["entries"])
    report = assemble_bars(dict(enumerate(pages, 1))) if pages else None
    if report and report != r.bar_report:
        r.bars = r.bar_report = report


@handles("entrances")
def take_entrances(hub, r, data):
    if data["entrances"] or data["map"] in hub.entrances:
        hub.entrances[data["map"]] = data["entrances"]


@handles("run")
def take_run(hub, r, data):
    hub.dungeons.note_run(data)
    if hub.characters.confirmed() is not None and hub.dungeons.merge_wish(hub.characters.current, data.get("wish") or ()):
        start_thread("stars", share_stars, (hub,))
    keep_extra(hub, r, "run", data)


@handles("guide")
def take_guide(hub, r, data):
    keep_extra(hub, r, "guide", data)


@handles("group")
def take_group(hub, r, data):
    r.group_seen = time.time()
    keep_extra(hub, r, "group", data)


@handles("quests")
def take_quests(hub, r, data):
    if getattr(hub, "watch", None) and (hub.extra.get("quests") or {}).get("log") != data.get("log"):
        hub.watch.poke()
    r.extra["quests"] = data


@handles("loaded")
def take_loaded(hub, r, data):
    keep_extra(hub, r, "loaded", data)


@handles("kills")
def take_kills(hub, r, data):
    hub.levels_seen.note(data["kills"])
    changed = hub.respawns.note(data["kills"], zone=(hub.state or {}).get("zone"))
    if hub.respawns.note_backs(data["backs"]) or changed:
        r.extra["respawnsAt"] = time.time()
    note_kill_xp(hub, data["kills"], r.kill_xp_seen, r.kill_xp.used)
    r.kill_xp.take_kills(data["kills"], time.time())
    note_gains(hub, r.kill_xp)


@handles("xp")
def take_kill_xp(hub, r, data):
    now = time.time()
    auras = held_ends(hub.extra.get("auras"), data["auras"], now)
    keep_extra(hub, r, "auras", auras)
    hub.routes.fly = FLY * XpAuras(auras, now).factor("flight")
    r.kill_xp_seen["at"] = 0.0
    r.kill_xp.take_gains(data, auras, now)
    note_gains(hub, r.kill_xp, now)


def held_ends(held, reported, now):
    before = {a["id"]: a.get("ends") for a in held or ()}
    out = []
    for a in reported:
        ends = None if a["left"] is None else round(now + a["left"])
        if ends is not None and before.get(a["id"]) is not None and abs(before[a["id"]] - ends) <= 2:
            ends = before[a["id"]]
        out.append({**{k: v for k, v in a.items() if k != "left"}, "ends": ends})
    return out


@handles("watched")
def take_watched(hub, r, data):
    held, now = hub.extra.get("watched") or {}, time.time()
    watched = {**{k: data[k] for k in ("check", *WATCHED_WHOLE)}, "recipes": sorted(data["recipes"]),
               "auras": held_ends(held.get("auras"), data["auras"], now),
               "cooldowns": held_ends(held.get("cooldowns"), data["cooldowns"], now)}
    said = lambda w: [sorted(e["id"] for e in w.get(k) or ()) for k in ("auras", "cooldowns")] + [w.get("recipes")]
    if said(held) != said(watched) and getattr(hub, "watch", None):
        hub.watch.poke()
    keep_extra(hub, r, "watched", watched)
    spots = getattr(hub, "firespots", None)
    if spots and data.get("fires"):
        spots.note(hub.characters.current, r.state, data["fires"], ticks.watched_fires(), world_pos)


def held_time(held, ago, now):
    if ago is None:
        return None
    at = round(now - ago)
    return held if held is not None and abs(held - at) <= 2 else at


@handles("queue")
def take_queue(hub, r, data):
    held, now = hub.extra.get("queue") or {}, time.time()
    queue = {k: v for k, v in data.items() if k not in ("waited", "event")}
    queue["since"] = held_time(held.get("since"), data["waited"], now)
    event = data["event"]
    if event:
        was = held.get("event") or {}
        same = all(was.get(k) == event[k] for k in ("n", "kind", "source", "name"))
        queue["event"] = {**{k: v for k, v in event.items() if k != "ago"},
                          "at": held_time(was.get("at") if same else None, event["ago"], now)}
    else:
        queue["event"] = None
    keep_extra(hub, r, "queue", queue)


@handles("character")
def take_character(hub, r, data):
    if hub.characters.identity(data):
        r.extra.update(dict.fromkeys(CHARACTER_EXTRAS))
        r.new_character()
        hub.routes.fly = FLY
    hub.world.pace.current = hub.characters.current
    hub.respawns.sync()


@handles("taxi")
def take_taxi(hub, r, data):
    hub.characters.taxi(data)


@handles("equipped")
def take_equipped(hub, r, data):
    hub.characters.equipped(data["items"], keys=data.get("keys"))
    keep_extra(hub, r, "equipped", data)


@handles("container")
def take_container(hub, r, data):
    got = r.containers.setdefault(data["where"], Pages())
    pages = got.add((data["at"], data["pages"]), data["page"], data["pages"], data)
    if pages:
        snap = {"at": data["at"], "free": data["free"], "slots": data["slots"],
                "items": {str(i): n for page in pages for i, n in page["items"]}}
        each = next((page["each"] for page in pages if page["page"] == 1 and page.get("each")), None)
        if each:
            snap["each"] = each
        suffixed = {str(k): n for page in pages for k, n in page.get("sfx") or ()}
        if suffixed:
            snap["sfx"] = suffixed
        watched = ticks.watched_items() if data["where"] == "bags" else ()
        counts = lambda: [(hub.characters.bags_now() or {}).get(i, 0) for i in watched]
        was = counts()
        hub.characters.containers(data["where"], snap)
        if watched and counts() != was and getattr(hub, "watch", None):
            hub.watch.poke()


@handles("legacy")
def take_legacy(hub, r, data):
    hub.characters.legacy(data)
    keep_extra(hub, r, "legacyPoints", {"spent": data.get("spent"), "unspent": data.get("unspent")})


@handles("rolls")
def take_rolls(hub, r, data):
    keep_extra(hub, r, "rolls", data)


@handles("gathers")
def take_gathers(hub, r, data):
    if hub.gathered.note(data):
        lay_gathered(hub.world, hub.gathered.all)


@handles("tracking")
def take_tracking(hub, r, data):
    hub.tracking = (data, time.time())


@handles("heights")
def take_heights(hub, r, data):
    hub.heights_seen.note(data)


@handles("epic")
def take_epic(hub, r, data):
    if data.get("chores"):
        services = getattr(getattr(hub, "world", None), "services", None) or ()
        npcs = {sv.get("id"): sv for sv in services if sv.get("id") in {c["npc"] for c in data["chores"]}}
        buy = camp_purchase(hub) if any(c.get("thing") == "camp" for c in data["chores"]) else None
        me = grade_state(hub) if any(c.get("thing") in errands.GRADED for c in data["chores"]) else None
        for c in data["chores"]:
            sv = npcs.get(c["npc"])
            item = errands.chore_buy(sv, c["thing"], me) \
                if me is not None and c.get("what") == "restock" and c.get("thing") in errands.GRADED else None
            c["step"] = errands.own_chore_step(c, sv and sv["n"], buy, item and item_name(item))
    rec = day_record(hub)
    if rec:
        rec.lead(hub.characters.current, data)
    was = hub.extra.get("epic")
    if report_key(lead_free(was)) != report_key(lead_free(data)):
        r.extra["epic"] = data
        game_epic_report(hub, data)
    elif any((was or {}).get(k) != data.get(k) for k in PAGE_ONLY):
        r.extra["epic"] = data


@handles("loopstops")
def take_loop_stops(hub, r, data):
    keep_extra(hub, r, "loopStops", data)


PAGE_ONLY = ("reason", "play", "then")
ASKED_FRESH = 60


@handles("director")
def take_director(hub, r, data):
    slide = data.get("slide")
    if slide:
        slide["text"] = hub.director_words.get(slide["id"])
    was = hub.extra.get("director")
    if was != data:
        r.extra["director"] = data
    asked = data.get("asked")
    if not asked or asked["ago"] > ASKED_FRESH:
        return
    at, heard = time.time() - asked["ago"], hub.replan_heard
    if heard and heard[0] == asked["n"] and abs(at - heard[1]) <= ASKED_FRESH:
        return
    hub.replan_heard = (asked["n"], at)
    if hub.watch:
        hub.watch.queue(lambda: replan_asked(hub, asked))
        hub.watch.poke()


@handles("camps")
def take_camps(hub, r, data):
    keep_extra(hub, r, "camps", data)
    r.pace_seen["busy"] = any(c["busy"] and c["here"] for c in data.get("camps") or ())


WORDS_KEPT = 8


@handles("directortext")
def take_director_text(hub, r, data):
    words = hub.director_words
    words.pop(data["id"], None)
    words[data["id"]] = data["text"]
    while len(words) > WORDS_KEPT:
        del words[next(iter(words))]
    cur = r.extra.get("director") or hub.extra.get("director")
    slide = (cur or {}).get("slide")
    if slide and slide["id"] == data["id"] and slide.get("text") != data["text"]:
        r.extra["director"] = {**cur, "slide": {**slide, "text": data["text"]}}


def lead_free(report):
    return {k: v for k, v in report.items() if k not in PAGE_ONLY} if report else report


@handles("completed")
def take_completed(hub, r, data):
    pages = r.completed.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data["ids"])
    if pages:
        hub.characters.completed([i for page in pages for i in page])


@handles("questlog")
def take_questlog_frame(hub, r, data):
    logged = take_questlog(hub, r.questlog, data)
    if logged:
        r.extra["questlog"] = logged
        if getattr(hub, "watch", None):
            hub.watch.poke()


@handles("spells")
def take_spells(hub, r, data):
    pages = r.spellbook.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data["ids"])
    if pages:
        known = hub.characters.known_spells()
        hub.characters.spells([i for page in pages for i in page])
        if known != hub.characters.known_spells() and getattr(hub, "watch", None):
            hub.watch.poke()


@handles("petspells")
def take_petspells(hub, r, data):
    pages = r.petbook.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data["ids"])
    if pages:
        hub.characters.pet_spells([i for page in pages for i in page])


def played_build():
    try:
        return game.played_version()
    except (OSError, game.GameNotFound):
        return None


@handles("explored")
def take_explored(hub, r, data):
    pages = r.explored.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data["ids"])
    if pages and hub.characters.explored([i for page in pages for i in page], played_build()):
        hub.fog.moved()


@handles("trainer")
def take_trainer(hub, r, data):
    pages = r.trainer.add((hub.characters.current, data["gen"], data["npc"]), data["page"], data["pages"], data["spells"])
    if pages:
        note_trainer(hub, data["npc"], [s for page in pages for s in page])


@handles("proftrainer")
def take_proftrainer(hub, r, data):
    pages = r.proftrainer.add((hub.characters.current, data["gen"], data["npc"]), data["page"], data["pages"], data["services"])
    if pages:
        note_profession_trainer(hub, data["npc"], data["profession"], [s for page in pages for s in page])


@handles("recipes")
def take_recipes(hub, r, data):
    pages = r.recipes.add((hub.characters.current, data["gen"]), data["page"], data["pages"], data)
    if pages:
        hub.characters.recipes({**pages[0], "recipes": [x for page in pages for x in page["recipes"]]})


@handles("auction")
def take_auction(hub, r, data):
    r.extra["auction"] = hub.auction.take_head(data)


@handles("auctions")
def take_auctions(hub, r, data):
    r.extra["auction"] = hub.auction.take_chunk(data)


@handles("reloading")
def take_reloading(hub, r, data):
    pass


@handles("questclick")
def take_quest_click(hub, r, data):
    was = hub.extra.get("questClick")
    if was and (was["quest"], was["n"]) == (data["quest"], data["n"]):
        return
    r.extra["questClick"] = {**data, "at": time.time()}


def reload_frame(reloads, kind, now):
    if kind == "reloading":
        reloads.signal(now)
    else:
        reloads.back(now)


def strip_loop(hub):
    from capture import StripReader
    reader = StripReader()
    r = Reading()
    reloads = Reloads()
    reloading = None
    stats = LinkStats()
    last_frame, last_message, reads, errors = None, None, 0, 0
    trails_saved = time.time()
    last_read = 0.0
    window_start = time.time()
    while True:
        started, seq, payload = time.time(), None, None
        try:
            seq, payload, info = reader.read()
            tap = getattr(hub, "strip_tap", None)
            if tap:
                tap(seq, payload, info)
            if time.time() - last_read > STRIP_GAP:
                hub.characters.hold()
            last_read = hub.read_at = time.time()
            hub.auction.strip_read(last_read)
            reads += 1
            r.read()
            stale = False
            if is_test_pattern(payload):
                message = "Test pattern OK: all 256 byte values read back correctly"
            else:
                message = "reading strip"
                new = (seq, payload) != last_frame
                stale = new and stats.behind(seq, time.time())
                if new and not stale:
                    try:
                        kind, data = parse_frame(payload)
                        stats.frame(seq, kind, time.time())
                    except StripError as e:
                        kind, data = "unread", None
                        if stats.unread(seq, str(e), time.time()):
                            log_note(f"a strip frame this server doesn't read: {e}")
                    reload_frame(reloads, kind, time.time())
                    handler = FRAME_KINDS.get(kind)
                    if handler:
                        handler(hub, r, data)
            if hub.paths.terrain.trails_dirty and time.time() - trails_saved > 60:
                hub.paths.terrain.save_trails()
                trails_saved = time.time()
            if hub.extra.get("group") and time.time() - r.group_seen > party_gone_after(stats, time.time()):
                r.extra["group"] = None
            if r.state or r.status:
                hub.characters.update(r.state, r.status, live=True)
            if r.state or r.status or r.bars or r.extra or message != last_message:
                hub.publish(state=r.state, status=r.status, bars=r.bars,
                            link={"ok": True, "message": message, "block": info["block"]}, **r.extra)
            last_frame, last_message = (last_frame if stale else (seq, payload)), message
            stats.work(time.time() - started, time.time())
        except StripError as e:
            errors += 1
            reloads.lost()
            message = str(e)
            tap = getattr(hub, "strip_tap", None)
            if tap:
                tap(None, None, {"error": message})
            if message == "anchor not found":
                message = "The strip isn't visible. Is the WoW window on screen and uncovered, with /ioa strip on?"
            if message != last_message:
                hub.publish(link={"ok": False, "message": message})
                last_message = message
            if "not found" in message or "minimized" in message:
                time.sleep(1)
        except Exception as e:
            errors += 1
            log_error("strip reader")
            last_frame = (seq, payload) if seq is not None else last_frame
            message = f"The Index hit an error reading the strip ({type(e).__name__}). data/server.log has the details"
            if message != last_message:
                hub.publish(link={"ok": False, "message": message})
                last_message = message
        note = reloads.link(time.time())
        if note != reloading:
            hub.publish(link={"reloading": note})
            reloading = note
        elapsed = time.time() - window_start
        if elapsed >= 2:
            hub.publish(link={"reads": reads, "errors": errors, "rate": round(reads / elapsed, 1), **stats.summary(time.time()),
                              "gameRunning": bool(game.seen_running())})
            reads = errors = 0
            window_start = time.time()
        interval = SCAN_READ_INTERVAL if hub.auction.running() else READ_INTERVAL
        time.sleep(max(0, interval - (time.time() - started)))


KILL_AFTER_FIGHT = 1.5


def note_kill_pace(hub, state, seen, now=None):
    now = now or time.time()
    xp, level, combat = state.get("xp"), state.get("level"), bool((state.get("flags") or {}).get("combat"))
    if xp is None or level is None:
        return
    if seen.get("combat") and not combat:
        seen["ended"] = now
    seen["combat"] = combat
    was, was_level = seen.get("xp"), seen.get("level")
    seen["xp"], seen["level"] = xp, level
    if was is None or (xp <= was and level == was_level) or level < was_level:
        return
    if not combat and now - seen.get("ended", 0.0) > KILL_AFTER_FIGHT:
        return
    last, seen["kill"] = seen.get("kill"), now
    if last and not seen.get("busy"):
        hub.world.pace.note(hub.characters.current, now - last, now)


def note_kill_xp(hub, kills, seen, used=None):
    if not seen.get("at") or seen.get("level") is None or seen.get("rested") or seen.get("group"):
        return
    for k in kills:
        key = (k["npc"], k.get("spawn"))
        if abs((time.time() - k["age"]) - seen["at"]) > 4 or (used is not None and key in used):
            continue
        m = hub.world.mobs.get(str(k["npc"]))
        if not m or m[3] in (1, 2, 3, 4) or m[2] - m[1] > 2:
            continue
        if hub.world.xp.note(seen["level"], (m[1] + m[2]) / 2, seen["xp"]):
            seen["at"] = 0.0
            if used is not None:
                used[key] = time.time()
        return


PAIR_NEAR = 4.0
PAIR_SETTLE = 2.0
PAIR_APART = 1.5
PAIR_WAIT = 30.0
USED_KEPT = 1500.0


class KillXp:

    def __init__(self, started=None):
        self.started = time.time() if started is None else started
        self.load, self.upto = None, 0
        self.frames = False
        self.gains = []
        self.kills = {}
        self.used = {}

    def take_gains(self, data, auras, now):
        self.frames = True
        if data["load"] != self.load:
            self.load, self.upto = data["load"], 0
        for k, gain in enumerate(data["gains"]):
            number = (data["first"] + k) % 65536
            if not 0 < (number - self.upto) % 65536 < 32768:
                continue
            self.upto, at = number, now - gain["age"]
            if at >= self.started - 1:
                self.gains.append({**gain, "n": number, "at": at, "auras": auras})

    def take_kills(self, kills, now):
        for k in kills:
            key, at = (k["npc"], k.get("spawn")), now - k["age"]
            if key not in self.used and key not in self.kills and now - at <= PAIR_WAIT:
                self.kills[key] = {"at": at, "npc": k["npc"], "name": k.get("name") or ""}

    def pair(self, now):
        out = []
        for gain in [g for g in self.gains if now - g["at"] >= PAIR_NEAR + PAIR_SETTLE]:
            named = gain["name"]
            near = sorted(((abs(k["at"] - gain["at"]), key) for key, k in self.kills.items()
                           if abs(k["at"] - gain["at"]) <= PAIR_NEAR and (not named or k["name"] in ("", named))),
                          key=lambda e: e[0])
            if not near:
                continue
            self.gains.remove(gain)
            gap, key = near[0]
            if any(other - gap < PAIR_APART and self.kills[k]["npc"] != self.kills[key]["npc"] for other, k in near[1:]):
                continue
            out.append((gain, self.kills.pop(key)))
            self.used[key] = now
        self.gains = [g for g in self.gains if now - g["at"] <= PAIR_WAIT]
        self.kills = {key: k for key, k in self.kills.items() if now - k["at"] <= PAIR_WAIT}
        self.used = {key: t for key, t in self.used.items() if now - t <= USED_KEPT}
        return out


def note_gains(hub, gains, now=None):
    for gain, kill in gains.pair(time.time() if now is None else now):
        m = hub.world.mobs.get(str(kill["npc"]))
        if not m or m[2] - m[1] > 2 or m[3] not in ((0, 1) if gain["inside"] else (0,)):
            continue
        xp = (gain["xp"] - gain["rested"]) / XpAuras(gain["auras"], gain["at"]).factor("kill")
        hub.world.xp.note(gain["level"], (m[1] + m[2]) / 2, xp, inside=gain["inside"],
                          party=(gain["size"], gain["levels"]) if gain["size"] > 1 else None)
