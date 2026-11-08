# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import struct

import numpy as np

import director_rules

LOADED_ONLY = ("plans",)

VERSION = 4
READ_VERSIONS = (3, VERSION)
HEADER_BLOCKS = 13
MAX_BLOCKS = 128
MAX_ROWS = 8
MAX_PAYLOAD = (MAX_BLOCKS - HEADER_BLOCKS) * 3
MAX_WIDE_PAYLOAD = MAX_PAYLOAD + (MAX_ROWS - 1) * MAX_BLOCKS * 3
ANCHOR = [(255, 0, 255), (0, 255, 0), (255, 0, 255)]
CALIBRATION = [0, 36, 73, 109, 146, 182, 219]
CHECK_PRIME, CHECK_BASE = 4294967291, 1048583
CHECK_POWERS = np.array([pow(CHECK_BASE, k, CHECK_PRIME) for k in range(3 + MAX_WIDE_PAYLOAD)], dtype=np.int64)

INSTANCE_KINDS = {0: None, 1: "party", 2: "raid", 3: "pvp", 4: "scenario"}
FLAG_POS, FLAG_FACING, FLAG_TARGET, FLAG_COMBAT, FLAG_GHOST, FLAG_RESTING, FLAG_INSTANCE, FLAG_TAXI = 1, 2, 4, 8, 16, 32, 64, 128


class StripError(Exception):
    pass


def near(a, b, tol=40):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def fletcher(data):
    s1 = s2 = 0
    for b in data:
        s1 = (s1 + b) % 255
        s2 = (s2 + s1) % 255
    return s1, s2


def frame_check(data):
    n = len(data)
    return int(np.frombuffer(data, np.uint8).astype(np.int64) @ CHECK_POWERS[:n][::-1]) % CHECK_PRIME


def checked(version, colors, data):
    if version == 3:
        return fletcher(data) == tuple(colors[12][:2])
    lo, hi, seq = colors[11]
    carried = colors[12][0] | colors[12][1] << 8 | colors[10][0] << 16 | colors[10][1] << 24
    return frame_check(bytes((lo, hi, seq)) + data) == carried


def decode_blocks(colors):
    if len(colors) < HEADER_BLOCKS or not all(near(c, a) for c, a in zip(colors[:3], ANCHOR)):
        raise StripError("anchor not found")
    ramp = colors[3:3 + len(CALIBRATION)]
    adjusted = colors[:3] != ANCHOR or any(obs != (lvl, lvl, lvl) for obs, lvl in zip(ramp, CALIBRATION))
    try:
        seq, data = _frame(colors)
    except StripError:
        if adjusted:
            moved = setting_moved([sum(c) / 3 for c in ramp])
            raise StripError("The strip's colors changed on screen" + (f": {moved}" if moved else ""))
        raise
    return seq, data, adjusted


def setting_moved(greys):
    lo = greys[0]
    if lo > 12:
        return "Brightness looks raised"
    if greys[1] < 8:
        return "Brightness looks lowered"
    a, b = CALIBRATION[1], CALIBRATION[6]
    line = greys[1] + (greys[6] - greys[1]) * (CALIBRATION[4] - a) / (b - a)
    if abs(greys[4] - line) > 6:
        return f"Gamma looks {'raised' if greys[4] > line else 'lowered'}"
    slope = (greys[6] - greys[1]) / (b - a)
    if abs(slope - 1) > 0.08:
        return f"Contrast looks {'raised' if slope > 1 else 'lowered'}"
    return None


def frame_rows(colors):
    if len(colors) <= HEADER_BLOCKS:
        return 1
    lo, hi, _ = colors[11]
    length = lo + hi * 256
    if length <= MAX_PAYLOAD or length > MAX_WIDE_PAYLOAD:
        return 1
    return 1 + -(-(length - MAX_PAYLOAD) // (MAX_BLOCKS * 3))


def _frame(colors):
    lo, hi, seq = colors[11]
    length = lo + hi * 256
    version = colors[12][2]
    if version not in READ_VERSIONS:
        raise StripError(f"The addon's strip uses protocol version {version}, and the Index reads version {VERSION}")
    if length > MAX_WIDE_PAYLOAD:
        raise StripError(f"bad length {length}")
    data = bytearray()
    for c in colors[HEADER_BLOCKS:]:
        data.extend(c)
    data = bytes(data[:length])
    if len(data) < length:
        raise StripError("The strip is cut off. Is the WoW window narrower than the strip?")
    if not checked(version, colors, data):
        raise StripError("A strip frame failed its checksum")
    return seq, data


class Reader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, fmt):
        size = struct.calcsize(fmt)
        if self.at + size > len(self.data):
            raise StripError("payload shorter than expected")
        v = struct.unpack_from(fmt, self.data, self.at)
        self.at += size
        return v[0] if len(v) == 1 else v

    def var(self):
        value, shift = 0, 0
        while True:
            b = self.take("<B")
            value |= (b & 0x7F) << shift
            if b < 0x80:
                return value
            shift += 7

    def u24(self):
        a, b, c = self.take("<3B")
        return a | b << 8 | c << 16

    def str(self):
        n = self.take("<B")
        s = self.data[self.at:self.at + n]
        self.at += n
        return s.decode("utf-8", errors="ignore")


def is_test_pattern(data):
    return data == bytes(range(256))



def item_key(item, bonuses=()):
    got = sorted({int(b) for b in bonuses or () if int(b) > 0})
    return f"{int(item)}:{':'.join(map(str, got))}" if got else int(item)


def split_key(key):
    parts = str(key).strip().split(":")
    if len(parts) > 9 or not all(p.isascii() and p.isdecimal() and len(p) <= 12 for p in parts) or not int(parts[0]):
        return None, ()
    return int(parts[0]), tuple(sorted({int(p) for p in parts[1:] if int(p)}))


def parse_key(text):
    item, bonuses = split_key(text)
    return None if item is None else item_key(item, bonuses)


def read_bonuses(r):
    return [r.var() for _ in range(r.take("<B"))]


STATUS_NUMBERS = {
    1: "money", 2: "moneyStart", 3: "bagFree", 4: "bagSlots", 5: "specialFree", 6: "durability", 7: "hearth",
    8: "quests", 9: "questsMax", 10: "questsDone", 11: "serverMinutes", 12: "sessionSeconds", 13: "sessionXP",
    14: "lastKillXP", 15: "lastKillRested", 16: "repReaction", 17: "repValue", 18: "repMax",
    19: "food", 20: "water", 21: "bandages", 22: "specialSlots",
    23: "miningSkill", 24: "herbalismSkill", 25: "skinningSkill", 26: "fishingSkill",
    27: "tree1Points", 28: "tree2Points", 29: "tree3Points",
    30: "petActive", 31: "petHappiness", 32: "petDamage", 33: "petTraining", 34: "ammo", 35: "rangedSpeed", 36: "ammoMax", 37: "petFood", 38: "talentPoints",
    40: "shards", 41: "healthstones", 42: "soulstones",
    45: "arcanePowder", 46: "runeTeleport", 47: "runePortals", 48: "lightFeather", 49: "manaGems",
    55: "poisons", 56: "mhPoisonSec", 57: "mhPoisonCharges", 58: "ohPoisonSec", 59: "ohPoisonCharges",
    60: "flashPowder", 61: "blindingPowder", 62: "mhEnchanted", 63: "ohEnchanted",
    65: "holyCandles", 66: "sacredCandles", 70: "rebirthSeeds", 71: "giftReagents",
    75: "divinitySymbols", 76: "kingsSymbols",
    80: "ankhs", 81: "reincarnation", 82: "earthTotem", 83: "fireTotem", 84: "waterTotem", 85: "airTotem",
    86: "totem1", 87: "totem2", 88: "totem3", 89: "totem4",
    90: "sharedVersion",
    91: "lineFormat",
    92: "weaponKinds", 93: "armorKinds",
    94: "playedSeconds", 95: "levelSeconds",
    96: "epicStep", 97: "epicDone",
    98: "durabilityItem",
    99: "trainedLevel",
    100: "epicBefore",
    101: "maxLevel",
    102: "epicItem",
    103: "epicUse",
    104: "bagJunk",
    105: "addonChores",
    106: "bagJunkValue",
    107: "camps", 108: "campWood", 109: "campTool",
    110: "addonOptions",
    111: "ammoKind", 112: "ammoGrade", 113: "waterGrade",
    114: "epicWay",
}
ADDON_OPTIONS = {"warningSound": (1, True)}


def addon_options(nums):
    bits = nums.get("addonOptions")
    if bits is None:
        return None
    return {name: bool(bits & bit) for name, (bit, _) in ADDON_OPTIONS.items()}
STATUS_STRINGS = {1: "bind", 2: "repName", 3: "petLoyalty", 4: "ammoName", 5: "demon", 6: "faction", 7: "petDiet",
                  8: "ammoBetter", 9: "talentRead",
                  10: "totem1", 11: "totem2", 12: "totem3", 13: "totem4"}
STATUS_WARNINGS = {1: "ammo", 2: "petUnhappy", 3: "shards", 4: "mhPoison", 5: "ohPoison", 6: "poisons", 7: "water",
                   8: "ankh", 9: "earthTotem", 10: "fireTotem", 11: "waterTotem", 12: "airTotem", 13: "durability"}
WARNING_QUIET = 4
CLASSES = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 7: "Shaman", 8: "Mage",
           9: "Warlock", 11: "Druid"}


RETIRED = 3
RELOADING = 43
RELOAD_HOW = {1: "held", 2: "hooked"}
EXPLORED = 44
QUEST_CLICKED = 45
SIDES = 46


def parse_sides(data):
    r = Reader(data)
    out = []
    for _ in range(r.take("<B")):
        version, flags = r.var(), r.take("<B")
        side = {"version": version, "running": bool(flags & 1), "closed": bool(flags & 2)}
        if flags & 1:
            side["cur"], n = r.take("<H"), r.take("<H")
            states = []
            for _ in range((n + 1) // 2):
                b = r.take("<B")
                states += [b & 15, b >> 4]
            side["states"] = [EPIC_STATES[s] if s < len(EPIC_STATES) else "todo" for s in states[:n]]
        out.append(side)
    return {"sides": out}


def parse_reloading(data):
    return {"how": RELOAD_HOW.get(data[0] if data else None, "unknown")}


def parse_quest_clicked(data):
    r = Reader(data)
    return {"quest": r.u24(), "n": r.take("<B")}


def parse_frame(data):
    if not data:
        raise StripError("empty frame")
    kind = data[0]
    if kind == 1:
        return "position", parse_payload(data[1:])
    if kind == 2:
        return "status", parse_status(data[1:])
    if kind == RETIRED:
        return "retired", None
    if kind == 4:
        return "bars", parse_bars(data[1:])
    if kind == 5:
        return "entrances", parse_entrances(data[1:])
    if kind == 6:
        return "run", parse_run(data[1:])
    if kind == 7:
        return "guide", parse_guide(data[1:])
    if kind == 8:
        return "group", parse_group(data[1:])
    if kind == 9:
        return "quests", parse_quests(data[1:])
    if kind == 10:
        return "loaded", parse_addons(data[1:])
    if kind == 17:
        return "kills", parse_kills(data[1:])
    if kind == 13:
        return "character", parse_character(data[1:])
    if kind == 14:
        return "taxi", parse_taxi(data[1:])
    if kind == 15:
        return "equipped", parse_equipped(data[1:])
    if kind == 16:
        return "container", parse_container(data[1:])
    if kind == 18:
        return "rolls", parse_rolls(data[1:])
    if kind == 19:
        return "gathers", parse_gathers(data[1:])
    if kind == 20:
        return "epic", parse_epic(data[1:])
    if kind == 21:
        return "completed", parse_completed(data[1:])
    if kind == 22:
        return "questlog", parse_questlog(data[1:])
    if kind == 23:
        return "spells", parse_completed(data[1:])
    if kind == 24:
        return "trainer", parse_trainer(data[1:])
    if kind == 25:
        return "proftrainer", parse_proftrainer(data[1:])
    if kind == 26:
        return "recipes", parse_recipes(data[1:])
    if kind == 27:
        return "heights", parse_heights(data[1:])
    if kind == 28:
        return "xp", parse_kill_xp(data[1:])
    if kind == 29:
        return "watched", parse_watched(data[1:])
    if kind == 30:
        return "queue", parse_queue(data[1:])
    if kind == 31:
        return "petspells", parse_completed(data[1:])
    if kind == 32:
        return "auction", parse_auction_head(data[1:])
    if kind == 34:
        return "hits", parse_hits(data[1:])
    if kind == 35:
        return "regen", parse_regen(data[1:])
    if kind == 33:
        return "auctions", parse_auction_chunk(data[1:])
    if kind == 36:
        return "legacy", parse_legacy(data[1:])
    if kind == 40:
        return "tracking", parse_tracking(data[1:])
    if kind == 42:
        return "camps", parse_camps(data[1:])
    if kind == 38:
        return "director", parse_director(data[1:])
    if kind == 39:
        return "directortext", parse_director_text(data[1:])
    if kind == 41:
        return "loopstops", parse_loop_stops(data[1:])
    if kind == RELOADING:
        return "reloading", parse_reloading(data[1:])
    if kind == EXPLORED:
        return "explored", parse_completed(data[1:])
    if kind == QUEST_CLICKED:
        return "questclick", parse_quest_clicked(data[1:])
    if kind == SIDES:
        return "sides", parse_sides(data[1:])
    if kind in ADDED_FRAMES:
        return added_frame(kind, data)
    raise StripError(f"unknown frame type {kind}")


def added_frame(kind, data):
    name, parse = ADDED_FRAMES[kind]
    return name, parse(data[1:])


ADDED_FRAMES = {}


def adds_frame(number, name, parse):
    if number not in ADDED_FRAMES and parse_frame_reads(number):
        raise ValueError(f"frame type {number} is read here already")
    ADDED_FRAMES[number] = (name, parse)


def parse_frame_reads(number):
    try:
        parse_frame(bytes([number]))
    except StripError as e:
        return not str(e).startswith("unknown frame type")
    except Exception:
        return True
    return True


AUCTION_STATES = {1: "asking", 2: "reading", 3: "done", 4: "stopped", 5: "failed"}
AUCTION_WHOLE = 1
AUCTION_SILENT = 2
AUCTION_BAND, AUCTION_SOLD, AUCTION_MIN_BID, AUCTION_BID, AUCTION_PART = 7, 8, 16, 32, 64


def parse_auction_head(data):
    r = Reader(data)
    out = {"scan": r.take("<I"), "state": AUCTION_STATES.get(r.take("<B"), "reading")}
    flags = r.take("<B")
    out["whole"] = bool(flags & AUCTION_WHOLE)
    out["silent"] = bool(flags & AUCTION_SILENT)
    out.update(total=r.var(), read=r.var(), sent=r.var(), chunks=r.var(), seconds=r.var())
    out["bands"] = [r.var() for _ in range(4)]
    out["realm"], out["faction"] = r.str(), r.str()
    out["next"] = r.take("<I") if r.at + 4 <= len(r.data) else None
    return out


def parse_auction_chunk(data):
    r = Reader(data)
    scan, chunk = r.take("<I"), r.var()
    auctions = []
    for _ in range(r.take("<B")):
        seller, item = r.str(), 0
        for k in range(r.var()):
            step = r.var()
            z = r.var() if step & 1 else 0
            item = step >> 1 if k == 0 else item + (step >> 1)
            sfx = z >> 1 if not z & 1 else -((z + 1) >> 1)
            for _ in range(r.var()):
                flags = r.take("<B")
                count, buyout = r.var(), r.var()
                bid = r.var() if flags & AUCTION_MIN_BID else 0
                auctions.append((item, sfx, count, buyout, bid, flags, seller))
    return {"scan": scan, "chunk": chunk, "auctions": auctions}


QUEUE_FLAGS = ("listed", "applied", "queued", "invite", "match", "group", "lead")
QUEUE_EVENTS = {1: "invite", 2: "joined", 3: "formed", 4: "full", 5: "gone"}
QUEUE_SOURCES = {1: "invite", 2: "listing", 3: "finder"}
QUEUE_NO_TIME = 65535


def parse_queue(data):
    r = Reader(data)
    flags = r.take("<B")
    out = {flag: bool(flags >> k & 1) for k, flag in enumerate(QUEUE_FLAGS)}
    out.update(what=r.str(), members=r.take("<B"), most=r.take("<B"))
    n, event = r.take("<B"), None
    if n:
        event = {"n": n, "kind": QUEUE_EVENTS.get(r.take("<B")), "source": QUEUE_SOURCES.get(r.take("<B")), "name": r.str()}
    since = r.take("<H")
    out["waited"] = None if since == QUEUE_NO_TIME else since
    if event:
        event["ago"] = r.take("<H")
    out["event"] = event
    return out


WATCHED_WHOLE = {"aurasWhole": 1, "cooldownsWhole": 2, "recipesWhole": 4}


def parse_watched(data):
    r = Reader(data)
    out = {"check": r.take("<H")}
    flags = r.take("<B")
    out.update({key: bool(flags & bit) for key, bit in WATCHED_WHOLE.items()})
    out["auras"] = []
    for _ in range(r.take("<B")):
        spell, stacks, left = r.u24(), r.take("<B"), r.take("<H")
        out["auras"].append({"id": spell, "stacks": stacks, "left": left or None})
    out["cooldowns"] = [{"id": r.u24(), "left": r.take("<H")} for _ in range(r.take("<B"))]
    out["recipes"], spell = [], 0
    for k in range(r.take("<B")):
        spell = r.u24() if k == 0 else spell + r.var()
        out["recipes"].append(spell)
    out["fires"] = [{"id": r.u24(), "ago": r.take("<H")} for _ in range(r.take("<B"))]
    return out


LEGACY_WHOLE = 1


def parse_legacy(data):
    r = Reader(data)
    out = {"currency": r.take("<H")}
    for key in ("max", "cap", "unspent", "spent"):
        v = r.var()
        out[key] = v - 1 if v else None
    out["whole"] = bool(r.take("<B") & LEGACY_WHOLE)
    names = [r.str() for _ in range(r.take("<B"))]
    out["done"], ach = [], 0
    for k in range(r.take("<B")):
        ach = r.u24() if k == 0 else ach + r.var()
        amount, who = r.take("<B"), r.take("<B")
        out["done"].append({"id": ach, "amount": amount, "by": names[who - 1] if 0 < who <= len(names) else None})
    return out


def parse_kill_xp(data):
    r = Reader(data)
    out = {"load": r.take("<H"), "auras": [], "gains": []}
    for _ in range(r.take("<B")):
        spell, stacks, left = r.u24(), r.take("<B"), r.take("<H")
        out["auras"].append({"id": spell, "stacks": stacks, "left": left or None,
                             "points": [r.take("<h") for _ in range(r.take("<B"))]})
    out["first"] = r.take("<H")
    for _ in range(r.take("<B")):
        age, level, xp, rested, flags, size = r.take("<H"), r.take("<B"), r.var(), r.var(), r.take("<B"), r.take("<B")
        levels = [r.take("<B") for _ in range(r.take("<B"))]
        out["gains"].append({"age": age, "level": level, "xp": xp, "rested": rested, "inside": bool(flags & 1),
                             "size": size, "levels": levels, "name": r.str()})
    return out


EPIC_STATES = ("todo", "done", "wait", "blocked", "parked", "skipped")
EPIC_EVENTS = {1: "done", 2: "blocked", 3: "notOffered", 4: "parked", 5: "unparked", 6: "offered", 7: "skipped"}
EPIC_UNPARKING = 1 << 23


def parse_epic(data):
    r = Reader(data)
    flags = r.take("<B")
    if not flags & 1:
        return {"running": False, "stopped": bool(flags & 2), "other": bool(flags & 4), "version": r.var()}
    wide = bool(flags & 16)
    step = (lambda: r.take("<H")) if wide else (lambda: r.take("<B"))
    out = {"running": True, "cardHidden": bool(flags & 8), "version": r.var(), "plan": r.var(), "cur": step()}
    if flags & 2:
        out["handIn"] = r.u24()
    first = r.take("<H") if wide else 1
    n, states = r.take("<B"), []
    for _ in range((n + 1) // 2):
        b = r.take("<B")
        states += [b & 15, b >> 4]
    out["states"] = ["done"] * max(0, first - 1) + [EPIC_STATES[s] if s < len(EPIC_STATES) else "todo" for s in states[:n]]
    out["events"] = []
    for _ in range(r.take("<B")):
        kind, at, ago = r.take("<B"), step(), r.take("<H")
        out["events"].append({"kind": EPIC_EVENTS.get(kind), "step": at, "ago": ago})
    out["parked"] = [r.u24() & (EPIC_UNPARKING - 1) for _ in range(r.take("<B"))]
    n = r.take("<B")
    if flags & 32:
        ids = [r.u24()] if n else []
        for _ in range(n - 1):
            ids.append(ids[-1] + r.var())
        out["notOffered"] = ids
    else:
        out["notOffered"] = [r.u24() for _ in range(n)]
    if flags & 64:
        out["skipped"] = [{"kind": r.take("<B"), "value": r.take("<H"), "level": r.take("<B")} for _ in range(r.take("<B"))]
    if flags & 128:
        out["pace"] = r.take("<B") / 50
    if r.at < len(r.data):
        out["moves"] = []
        for _ in range(r.take("<B")):
            p, before, s = r.take("<H"), r.take("<H"), r.take("<B")
            state = EPIC_STATES[s] if s < len(EPIC_STATES) else "todo"
            out["moves"].append({"step": p, "before": before, "state": state})
            if 0 < p <= len(out["states"]):
                out["states"][p - 1] = state
    if flags & 4 and r.at < len(r.data):
        out["chores"] = []
        for _ in range(r.take("<B")):
            kind, fl, before, s = r.take("<B"), r.take("<B"), r.take("<H"), r.take("<B")
            npc, inst, north, west = r.u24(), r.take("<H"), r.take("<h"), r.take("<h")
            cost, level = r.var(), r.take("<B")
            out["chores"].append({"what": CHORE_KINDS.get(kind), "thing": CHORE_THINGS.get(chore_thing(fl)), "junk": bool(fl & 4),
                                  "both": bool(fl & 8), "lead": bool(fl & 16), "putOff": bool(fl & 32), "before": before,
                                  "state": EPIC_STATES[s] if s < len(EPIC_STATES) else "todo", "npc": npc, "inst": inst,
                                  "at": [north, west], "cost": cost, "level": level})
    if flags & 4 and r.at < len(r.data):
        code = r.take("<B")
        if code & 127:
            other, n = r.take("<H"), r.take("<B")
            quest = r.u24() if code & 128 else 0
            keys = director_rules.codes()
            if (code & 127) <= len(keys):
                out["reason"] = {"key": keys[(code & 127) - 1], "other": other, "otherQuest": quest, "n": n}
        out["putOff"] = [r.take("<H") for _ in range(r.take("<B"))]
        left = len(r.data) - r.at
        if left in (1, 3):
            out["play"] = r.take("<B") / 20
        if left >= 2:
            out["then"] = r.take("<H")
    return out


def parse_loop_stops(data):
    r = Reader(data)
    out = {"version": r.var(), "steps": {}}
    for _ in range(r.take("<B")):
        step, n = r.take("<H"), r.take("<B")
        bits = [r.take("<B") for _ in range(n)]
        out["steps"][str(step)] = [b * 8 + k + 1 for b, v in enumerate(bits) for k in range(8) if v >> k & 1]
    return out


CHORE_KINDS = {1: "train", 4: "sell", 5: "repair", 6: "restock"}
CHORE_THINGS = {1: "water", 2: "ammo", 3: "ankh", 4: "camp"}


def chore_thing(flags):
    return (flags & 3) | (flags & 64) >> 4

DIRECTOR_SLIDES = {1: "drift", 2: "nextzone", 3: "levelup", 4: "classquest"}
REPLAN_MODES = {1: "here", 2: "zone", 3: "class"}


def parse_director(data):
    r = Reader(data)
    flags = r.take("<B")
    out = {"working": bool(flags & 1), "fighting": bool(flags & 2), "break": bool(flags & 4), "dry": bool(flags & 8),
           "drift": r.take("<H") / 10, "slide": None, "asked": None, "background": [], "left": None}
    if flags & 16:
        n, kind, keys, ago = r.take("<B"), r.take("<B"), r.take("<B"), r.take("<H")
        out["slide"] = {"id": n, "kind": DIRECTOR_SLIDES.get(kind), "replan": bool(keys & 1), "ago": ago, "text": None}
        if keys & 2:
            out["slide"]["zone"] = r.take("<H")
            out["slide"]["quests"] = [r.u24() for _ in range(r.take("<B"))]
        if keys & 4:
            out["slide"]["chain"] = r.u24()
    if flags & 64:
        n, mode, zone, ago = r.take("<B"), r.take("<B"), r.take("<H"), r.take("<H")
        out["asked"] = {"n": n, "mode": REPLAN_MODES.get(mode), "zone": zone or None, "ago": ago,
                        "quests": [r.u24() for _ in range(r.take("<B"))]}
    if flags & 128:
        for _ in range(r.take("<B")):
            out["background"].append({"quest": r.u24(), "line": r.take("<H"), "have": r.take("<H"), "need": r.take("<H")})
    if flags & 32:
        out["left"] = r.str()
    return out


def parse_camps(data):
    r = Reader(data)
    plan, n = r.take("<I"), r.take("<B")
    camps = []
    for _ in range(n):
        step, quest, rate, kh, at, gap, flags = r.take("<H"), r.u24(), r.take("<H"), r.take("<H"), r.take("<H"), \
            r.take("<H"), r.take("<B")
        camps.append({"step": step, "quest": quest, "rate": rate, "kh": kh, "at": at, "gap": gap or None,
                      "busy": bool(flags & 1), "here": bool(flags & 2)})
    return {"plan": plan, "camps": camps}


def parse_director_text(data):
    r = Reader(data)
    n, size = r.take("<B"), r.take("<H")
    text = r.data[r.at:r.at + size]
    if len(text) < size:
        raise StripError("payload shorter than expected")
    return {"id": n, "text": text.decode("utf-8", errors="ignore")}


def parse_completed(data):
    r = Reader(data)
    gen, page, pages, n = r.take("<B"), r.take("<B"), r.take("<B"), r.take("<H")
    ids = []
    if n:
        at = r.u24()
        ids.append(at)
        for _ in range(n - 1):
            at += r.var()
            ids.append(at)
    return {"gen": gen, "page": page, "pages": pages, "ids": ids}


def parse_trainer(data):
    r = Reader(data)
    gen, page, pages, npc, n = r.take("<B"), r.take("<B"), r.take("<B"), r.u24(), r.take("<H")
    spells, at = [], 0
    for k in range(n):
        at = r.u24() if k == 0 else at + r.var()
        spells.append((at, r.var(), r.take("<B")))
    return {"gen": gen, "page": page, "pages": pages, "npc": npc, "spells": spells}


PROF_RANK, PROF_KNOWN, PROF_NOT_YET = 1, 2, 4


def parse_proftrainer(data):
    r = Reader(data)
    gen, page, pages, npc, profession, n = r.take("<B"), r.take("<B"), r.take("<B"), r.u24(), r.str(), r.take("<H")
    services, at = [], 0
    for k in range(n):
        at = r.u24() if k == 0 else at + r.var()
        cost, level, skill, flags = r.var(), r.take("<B"), r.var(), r.take("<B")
        s = {"spell": at, "cost": cost, "level": level, "skill": skill, "known": bool(flags & PROF_KNOWN),
             "notYet": bool(flags & PROF_NOT_YET)}
        if flags & PROF_RANK:
            s["rank"] = r.str()
        services.append(s)
    return {"gen": gen, "page": page, "pages": pages, "npc": npc, "profession": profession, "services": services}


RECIPE_COLOURS = ("orange", "yellow", "green", "grey")


def parse_recipes(data):
    r = Reader(data)
    gen, page, pages = r.take("<B"), r.take("<B"), r.take("<B")
    line, skill, top, second, second_skill, second_top = [r.take("<H") for _ in range(6)]
    at = r.take("<H") | r.take("<H") << 16
    name, n = r.str(), r.take("<H")
    recipes, spell = [], 0
    for k in range(n):
        spell = r.u24() if k == 0 else spell + r.var()
        colour = r.take("<B")
        recipes.append((spell, RECIPE_COLOURS[colour] if colour < len(RECIPE_COLOURS) else None))
    return {"gen": gen, "page": page, "pages": pages, "name": name, "line": line, "skill": skill, "max": top,
            "second": {"line": second, "skill": second_skill, "max": second_top}, "at": at, "recipes": recipes}


QUESTLOG_HEADER, QUESTLOG_QUEST, QUESTLOG_FOLDED, QUESTLOG_MARKED = 1, 2, 3, 4


def parse_questlog(data):
    r = Reader(data)
    gen, page, pages = r.take("<B"), r.take("<B"), r.take("<B")
    entries = []
    for _ in range(r.take("<B")):
        kind = r.take("<B")
        if kind in (QUESTLOG_HEADER, QUESTLOG_FOLDED):
            entries.append({"header": r.str(), "folded": kind == QUESTLOG_FOLDED})
        elif kind in (QUESTLOG_QUEST, QUESTLOG_MARKED):
            qid, level, flags = r.u24(), r.take("<B"), r.take("<B")
            title = r.str()
            objectives = []
            for _ in range(r.take("<B")):
                done, need, finished = r.take("<B"), r.take("<B"), bool(r.take("<B"))
                objectives.append({"done": done, "need": need, "finished": finished, "text": r.str()})
            e = {"id": qid, "level": level, "title": title, "complete": bool(flags & 1), "failed": bool(flags & 2),
                 "group": bool(flags & 4), "objectives": objectives}
            if kind == QUESTLOG_MARKED:
                e["poi"] = {"map": r.take("<H"), "x": r.take("<H") / 10000, "y": r.take("<H") / 10000}
            if flags & 8:
                e["ends"] = r.var()
            if flags & 16:
                e["areas"] = []
            entries.append(e)
        else:
            raise StripError(f"unknown quest log entry {kind}")
    quests = [e["objectives"] for e in entries if e.get("objectives")]
    if quests and len(r.data) - r.at >= sum((len(objs) + 1) // 2 for objs in quests):
        for objs in quests:
            for k in range(0, len(objs), 2):
                b = r.take("<B")
                for o, code in zip(objs[k:k + 2], (b & 15, b >> 4)):
                    o["type"] = OBJECTIVE_TYPES.get(code)
    for e in entries:
        if "areas" in e:
            if r.at >= len(r.data):
                e.pop("areas")
                continue
            for _ in range(r.take("<B")):
                e["areas"].append({"obj": r.take("<B"), "x": r.take("<H") / 10000, "y": r.take("<H") / 10000,
                                   "r": r.take("<H")})
    return {"gen": gen, "page": page, "pages": pages, "entries": entries}


def parse_rolls(data):
    r = Reader(data)
    out = []
    for _ in range(r.take("<B")):
        item, left, cls, sub, inv = r.u24(), r.take("<B"), r.take("<B"), r.take("<B"), r.take("<B")
        il, rl, icon, usable = r.take("<H"), r.take("<B"), r.u24(), r.take("<B")
        out.append({"item": item, "left": left, "cls": cls, "sub": sub, "inv": inv, "il": il, "rl": rl, "icon": icon or None,
                    "usable": None if usable == 2 else bool(usable)})
    if r.at < len(r.data):
        for roll in out:
            roll["key"] = item_key(roll["item"], read_bonuses(r))
    return {"rolls": out}


def parse_equipped(data):
    r = Reader(data)
    items = [r.u24() for _ in range(r.take("<B"))]
    if r.at >= len(r.data):
        return {"items": items}
    return {"items": items, "keys": [item_key(i, read_bonuses(r)) for i in items]}


CONTAINERS = {1: "bags", 2: "bank", 3: "warband"}


def parse_container(data):
    r = Reader(data)
    where = CONTAINERS.get(r.take("<B"), "bags")
    at = r.take("<H") | r.take("<H") << 16
    page, pages = r.take("<B"), r.take("<B")
    free, slots = r.take("<H"), r.take("<H")
    items = [[r.u24(), r.var()] for _ in range(r.take("<B"))]
    each = []
    if r.at < len(r.data):
        each = [{"id": r.u24(), "slots": r.take("<B"), "free": r.take("<B"), "family": r.var()} for _ in range(r.take("<B"))]
    suffixed = []
    if r.at < len(r.data):
        for _ in range(r.take("<B")):
            item = r.u24()
            suffixed.append([item_key(item, read_bonuses(r)), r.var()])
    return {"where": where, "at": at, "page": page, "pages": pages, "free": free, "slots": slots, "items": items,
            "each": each, "sfx": suffixed}


def parse_run(data):
    r = Reader(data)
    flags = r.take("<B")
    out = {"inside": bool(flags & 1), "corpseRun": bool(flags & 2), "dead": bool(flags & 4), "key": r.str()}
    out["open"] = bool(flags & 9)
    out["seconds"], out["deaths"] = r.take("<H"), r.take("<B")
    out["xp"], out["money"] = r.u24(), r.u24()
    out["kills"] = [r.take("<B") for _ in range(r.take("<B"))]
    out["loot"] = [r.u24() for _ in range(r.take("<B"))]
    out["entries"] = [r.take("<B") for _ in range(r.take("<B"))]
    out["gear"] = [r.take("<H") for _ in range(r.take("<B"))]
    out["wish"] = [r.u24() for _ in range(r.take("<B"))]
    out["also"] = {}
    for _ in range(r.take("<B") if r.at < len(r.data) else 0):
        key = r.str()
        out["also"][key] = [r.take("<B") for _ in range(r.take("<B"))]
    return out


GUIDE_SOURCES = {0: None, 1: "journal", 2: "typed", 3: "corpse", 4: "pin"}


LOOP_LOOKS = {1: ("grind", "grind"), 2: ("gather", "gather"), 3: ("skin", "skin"), 4: ("grind", "xp"), 5: ("grind", "farm"),
              6: ("gather", "mining"), 7: ("gather", "herbalism"), 8: ("gather", "fishing"), 9: ("gather", "treasure")}
GUIDE_LOOKS = {0: "gold", 1: "corpse", 2: "npc"}


def parse_guide(data):
    r = Reader(data)
    source = GUIDE_SOURCES.get(r.take("<B"), "typed")
    map_id, x, y = r.take("<H"), r.take("<H") / 100, r.take("<H") / 100
    name = r.str()
    out = {"source": source, "map": map_id, "x": x, "y": y, "name": name} if source else {"source": None}
    if r.at < len(r.data):
        kind, look = LOOP_LOOKS.get(r.take("<B"), (None, None))
        loop_name = r.str()
        out["loop"] = {"kind": kind, "name": loop_name, "look": look} if kind else None
    if r.at < len(r.data):
        n, kind = r.take("<B"), r.take("<B")
        out["closed"] = {"n": n, "kind": {1: "gold", 2: "loop", 3: "epic"}.get(kind), "name": r.str()}
    if r.at < len(r.data):
        out["checks"] = {"go": r.take("<H"), "loop": r.take("<H")}
    if r.at < len(r.data):
        out["declined"] = {"go": r.take("<H"), "loop": r.take("<H")}
    if r.at < len(r.data):
        out["checks"]["target"], out["declined"]["target"] = r.take("<H"), r.take("<H")
    if r.at < len(r.data):
        out["look"] = GUIDE_LOOKS.get(r.take("<B"), "gold")
    return out


ROLES = {0: None, 1: "tank", 2: "healer", 3: "damage"}


GROUP_EPIC = 1


def parse_group(data):
    r = Reader(data)
    key, members = r.str(), []
    for _ in range(r.take("<B")):
        name = r.str()
        cls, level, hp, power, ptype, flags, role = (r.take("<B") for _ in range(7))
        bits = [r.take("<B") for _ in range(r.take("<B"))]
        members.append({"name": name, "classId": cls, "className": CLASSES.get(cls, ""), "level": level,
                        "health": None if hp == 255 else hp, "power": None if power == 255 else power, "powerType": ptype,
                        "dead": bool(flags & 1), "ghost": bool(flags & 2), "offline": bool(flags & 4), "far": bool(flags & 8),
                        "leader": bool(flags & 16), "combat": bool(flags & 32), "me": bool(flags & 64),
                        "role": ROLES.get(role),
                        "quests": [i for i in range(len(bits) * 8) if bits[i // 8] >> (i % 8) & 1]})
    out = {"key": key, "members": members}
    if r.at < len(r.data) and r.take("<B") == GROUP_EPIC:
        out["of"] = r.take("<B")
        for m in members:
            m["on"] = r.take("<B")
        away = r.take("<H")
        for k, m in enumerate(members):
            m["away"] = bool(away >> k & 1)
    return out


NO_POS = -32768
HIT_KINDS = {1: "hit", 2: "heal"}


def parse_hits(data):
    r = Reader(data)
    most, count = r.u24(), r.take("<H")
    last = [{"kind": HIT_KINDS.get(kind), "amount": amount or None}
            for kind, amount in (r.take("<BH") for _ in range(r.take("<B")))]
    return {"most": most or None, "count": count, "last": last}


SPIRIT_UNKNOWN = 65535


def parse_regen(data):
    r = Reader(data)
    most, spirit, events = r.u24(), r.take("<H"), r.take("<H")
    buffs = [{"kind": kind, "amount": amount, "period": period, "left": left}
             for kind, amount, period, left in (r.take("<BHHH") for _ in range(r.take("<B")))]
    return {"most": most or None, "spirit": None if spirit == SPIRIT_UNKNOWN else spirit, "events": events,
            "buffs": buffs}


HEALTH_UNKNOWN = 255


KILL_LEVEL_SKULL = 255


def kill_level(v):
    if v == KILL_LEVEL_SKULL:
        return "??"
    return v or None


def parse_kills(data):
    r = Reader(data)
    kills, backs = [], []
    for _ in range(r.take("<B")):
        npc = r.u24()
        spawn = r.take("<H") | r.take("<H") << 16
        age, map_id, north, west = r.take("<H"), r.take("<H"), r.take("<h"), r.take("<h")
        others = r.take("<B")
        kills.append({"npc": npc, "spawn": spawn, "age": age, "map": map_id,
                      "pos": None if north == NO_POS else [north, west], "others": others, "name": r.str(),
                      "level": None})
    if r.at < len(r.data):
        for _ in range(r.take("<B")):
            npc = r.u24()
            spawn = r.take("<H") | r.take("<H") << 16
            age, map_id, north, west = r.take("<H"), r.take("<H"), r.take("<h"), r.take("<h")
            backs.append({"npc": npc, "spawn": spawn, "age": age, "map": map_id, "pos": None if north == NO_POS else [north, west]})
    if len(r.data) - r.at >= len(kills):
        for k in kills:
            k["level"] = kill_level(r.take("<B"))
    return {"kills": kills, "backs": backs}


def parse_gathers(data):
    r = Reader(data)
    out = []
    for _ in range(r.take("<B")):
        age, map_id, north, west = r.take("<H"), r.take("<H"), r.take("<h"), r.take("<h")
        out.append({"age": age, "map": map_id, "pos": [north, west], "name": r.str()})
    return out


def parse_heights(data):
    r = Reader(data)
    out = []
    for _ in range(r.take("<B")):
        name, npc = r.str(), r.u24()
        inst, north, west, tenths, seen = r.take("<HhhhB")
        out.append({"name": name, "npc": npc or None, "inst": inst, "at": [north, west], "z": tenths / 10, "seen": seen})
    return out


def parse_character(data):
    r = Reader(data)
    out = {"name": r.str(), "surname": r.str(), "realm": r.str(), "race": r.str(), "professions": []}
    for _ in range(r.take("<B")):
        out["professions"].append({"name": r.str(), "rank": r.take("<H"), "max": r.take("<H")})
    out["guid"] = r.str() if r.at < len(r.data) else ""
    return out


def parse_taxi(data):
    r = Reader(data)
    ids = [r.take("<H") for _ in range(r.take("<B"))]
    hashes = [r.take("<H") for _ in range(r.take("<B"))]
    return {"ids": ids, "hashes": hashes}


ADDON_STATES = {1: "loaded", 2: "missing", 3: "disabled", 4: "notLoaded"}


def parse_addons(data):
    r = Reader(data)
    out = {}
    for _ in range(r.take("<B")):
        name, state, text = r.str(), r.take("<B"), r.str()
        out[name] = {"state": ADDON_STATES.get(state, "notLoaded"), "version" if state == 1 else "reason": text}
    return out


def parse_quests(data):
    r = Reader(data)
    log = []
    for _ in range(r.take("<B")):
        log.append({"id": r.u24(), "complete": bool(r.take("<B"))})
    done = {}
    for _ in range(r.take("<B")):
        index = r.take("<B")
        bits = [r.take("<B") for _ in range(r.take("<B"))]
        done[index] = [i for i in range(len(bits) * 8) if bits[i // 8] >> (i % 8) & 1]
    return {"log": log, "done": done}


OBJECTIVE_TYPES = {0: None, 1: "monster", 2: "item", 3: "object", 4: "event", 5: "log", 6: "reputation", 7: "player",
                   8: "progressbar"}


def parse_bars(data):
    r = Reader(data)
    version, page, pages = r.take("<B"), r.take("<B"), r.take("<B")
    entries = []
    for _ in range(r.take("<B")):
        kind, name = r.take("<B"), None
        name = r.str()
        if kind == 1:
            entries.append({"kind": "rank", "name": name, "have": r.take("<B"), "best": r.take("<B")})
        else:
            entries.append({"kind": "missing", "name": name})
    return {"version": version, "page": page, "pages": pages, "entries": entries}


def parse_entrances(data):
    r = Reader(data)
    map_id = r.take("<H")
    out = []
    for _ in range(r.take("<B")):
        name = r.str()
        x, y = r.take("<h") / 10000, r.take("<h") / 10000
        out.append({"name": name, "x": x, "y": y, "raid": bool(r.take("<B"))})
    return {"map": map_id, "entrances": out}


def assemble_bars(pages):
    ranks, missing = [], []
    for page in sorted(pages):
        for e in pages[page]:
            if e["kind"] == "rank":
                ranks.append({"name": e["name"], "have": e["have"], "best": e["best"]})
            else:
                missing.append(e["name"])
    return {"ranks": ranks, "missing": missing}


def parse_status(data):
    r = Reader(data)
    class_id = r.take("<B")
    nums = {}
    for _ in range(r.take("<B")):
        key = r.take("<B")
        nums[STATUS_NUMBERS.get(key, f"n{key}")] = r.var()
    strs = {}
    for _ in range(r.take("<B")):
        key = r.take("<B")
        strs[STATUS_STRINGS.get(key, f"s{key}")] = r.str()
    skills = []
    for _ in range(r.take("<B")):
        name = r.str()
        skills.append({"name": name, "rank": r.take("<H"), "max": r.take("<H")})
    warnings = []
    for _ in range(r.take("<B")):
        key, level = r.take("<B"), r.take("<B")
        w = {"key": STATUS_WARNINGS.get(key, f"w{key}"), "level": "out" if level & 3 == 2 else "low"}
        if level & WARNING_QUIET:
            w["quiet"] = True
        warnings.append(w)
    return {"classId": class_id, "className": CLASSES.get(class_id, ""), "nums": nums, "strs": strs,
            "skills": skills, "warnings": warnings}


def parse_tracking(data):
    r = Reader(data)
    radius, zoom, flags, count = r.take("<H") / 10, r.take("<B"), r.take("<B"), r.take("<B")
    listed = [{"spell": bool(r.take("<B") & 1), "id": r.u24()} for _ in range(count)]
    return {"radius": radius or None, "zoom": zoom, "shape": ("square" if flags & 1 else "round") if flags & 2 else None,
            "indoors": bool(flags & 16), "on": listed if flags & 4 else None, "more": bool(flags & 8)}


def parse_payload(data):
    r = Reader(data)
    flags = r.take("<B")
    state = {
        "flags": {
            "combat": bool(flags & FLAG_COMBAT), "ghost": bool(flags & FLAG_GHOST),
            "resting": bool(flags & FLAG_RESTING), "instance": bool(flags & FLAG_INSTANCE), "taxi": bool(flags & FLAG_TAXI),
        },
    }
    map_id = r.take("<H")
    x, y = r.take("<H") / 65535, r.take("<H") / 65535
    facing = r.take("<H") / 65535 * 2 * math.pi
    state["map"] = map_id or None
    state["pos"] = {"x": x, "y": y} if flags & FLAG_POS else None
    state["facing"] = facing if flags & FLAG_FACING else None
    state["level"] = r.take("<B")
    state["xp"], state["xpMax"], state["rested"] = r.u24(), r.u24(), r.u24()
    state["speed"] = r.take("<B") / 10
    r.take("<H")
    r.str()
    state["zone"], state["subzone"] = r.str(), r.str()
    r.str()
    for _ in range(r.take("<B")):
        r.take("<H"), r.take("<H"), r.take("<H"), r.take("<h"), r.take("<h")
    r.take("<H")
    state["instance"] = state["minimap"] = state["health"] = state["act"] = None
    state["idleLost"] = 0
    state["flags"]["dead"] = False
    while r.at < len(r.data):
        section = r.take("<B")
        if section == 1:
            inst, kind, has = r.take("<H"), r.take("<B"), r.take("<B")
            wx, wy, wz = r.take("<h"), r.take("<h"), r.take("<h")
            state["instance"] = {"id": inst, "kind": INSTANCE_KINDS.get(kind), "world": [wx, wy, wz] if has else None}
        elif section == 2:
            x, y, w, h = r.take("<H"), r.take("<H"), r.take("<H"), r.take("<H")
            zoom, flags = r.take("<B"), r.take("<B")
            state["minimap"] = {"x": x, "y": y, "w": w, "h": h, "zoom": zoom, "indoors": bool(flags & 1),
                                "rotate": bool(flags & 2), "shown": bool(flags & 4)}
        elif section == 3:
            state["flags"]["dead"] = bool(r.take("<B") & 1)
        elif section == 4:
            state["idleLost"], health = r.take("<B"), r.take("<B")
            state["health"] = None if health == HEALTH_UNKNOWN else health
        elif section == 5:
            acts, busy = r.take("<B"), r.take("<B")
            state["act"] = {"acts": acts, "busy": bool(busy & 1), "vendor": bool(busy & 2)}
        else:
            break
    return state
