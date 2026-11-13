# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re
import time

MINE = 0x1
FRIENDLY, HOSTILE = 0x10, 0x40
CONTROL_PLAYER = 0x100
PLAYER, NPC, PET, GUARDIAN = 0x400, 0x800, 0x1000, 0x2000

DAMAGE = {"SWING_DAMAGE", "RANGE_DAMAGE", "SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "ENVIRONMENTAL_DAMAGE",
          "DAMAGE_SHIELD", "SPELL_BUILDING_DAMAGE"}
MISSED = {"SWING_MISSED", "RANGE_MISSED", "SPELL_MISSED", "SPELL_PERIODIC_MISSED", "DAMAGE_SHIELD_MISSED"}
HEAL = {"SPELL_HEAL", "SPELL_PERIODIC_HEAL"}
OTHER = {"SPELL_CAST_START", "SPELL_CAST_SUCCESS", "SPELL_AURA_APPLIED", "SPELL_AURA_REMOVED", "SPELL_INTERRUPT",
         "SPELL_DISPEL", "SPELL_SUMMON", "SPELL_INSTAKILL", "SPELL_DRAIN", "SPELL_LEECH", "PARTY_KILL", "UNIT_DIED"}
FIGHT_ONLY = {"SWING_DAMAGE_LANDED", "SPELL_ABSORBED", "SPELL_AURA_BROKEN", "SPELL_AURA_BROKEN_SPELL"}
KEPT = DAMAGE | MISSED | HEAL | OTHER | FIGHT_ONLY
SPELL_PREFIX = ("SPELL_PERIODIC_", "SPELL_BUILDING_", "SPELL_", "RANGE_", "DAMAGE_SHIELD")
AURA_KINDS = {"BUFF", "DEBUFF"}
EXTRA_SPELL = {"SPELL_INTERRUPT", "SPELL_DISPEL", "SPELL_AURA_BROKEN_SPELL"}

STAMP = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))? (\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,4}))?(?:[+-]\d{1,2})?\s\s(.*)$")
GUID = re.compile(r"^(?:Player|Creature|Pet|Vehicle|GameObject|Vignette|Item|Corpse|BattlePet)-[0-9A-Za-z-]+$|^0+$")
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
INTEGER = re.compile(r"^-?\d+$")
POWERS = re.compile(r"^-?\d+(?:\|-?\d+)+$")
MISS_KIND = re.compile(r"^[A-Z]+$")
NO_GUID = "0000000000000000"


def stamp(line, now=None):
    m = STAMP.match(line.rstrip("\r\n"))
    if not m:
        return None
    mon, day, year, hh, mm, ss, frac, rest = m.groups()
    now = now or time.time()
    frac_s = int(frac) / 10 ** len(frac) if frac else 0.0

    def at(y):
        if not (1 <= int(mon) <= 12 and 1 <= int(day) <= 31 and int(hh) < 24 and int(mm) < 60 and int(ss) < 61):
            return None
        try:
            return time.mktime((y, int(mon), int(day), int(hh), int(mm), int(ss), 0, 0, -1)) + frac_s
        except (OverflowError, ValueError):
            return None
    if year:
        y = int(year)
        t = at(y + 2000 if y < 100 else y)
    else:
        y = time.localtime(now).tm_year
        t = at(y)
        if t is not None and t > now + 86400:
            t = at(y - 1)
    return None if t is None else (round(t, 3), rest)


def fields(rest):
    out, cur, quoted, i = [], [], False, 0
    while i < len(rest):
        ch = rest[i]
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).rstrip("\r\n"))
    return out


def _flags(v):
    try:
        return int(v, 16) if v.lower().startswith("0x") else int(v)
    except (ValueError, AttributeError):
        return 0


def _num(v):
    return float(v) if NUMBER.match(v or "") else None


def _int(v):
    return int(v) if INTEGER.match(v or "") else None


def prefix_size(event):
    if event.startswith("SWING_") or event in ("UNIT_DIED", "PARTY_KILL"):
        return 0
    if event.startswith("ENVIRONMENTAL_"):
        return 1
    return 3


def advanced(f, at):
    if len(f) < at + 2 or not (GUID.match(f[at]) and GUID.match(f[at + 1])):
        return 0, None
    k = at + 2
    while k < len(f) and (INTEGER.match(f[k]) or POWERS.match(f[k])):
        k += 1
    if k == at + 2 or len(f) < k + 5:
        return 0, None
    x, y, m, facing, level = _num(f[k]), _num(f[k + 1]), _int(f[k + 2]), _num(f[k + 3]), _int(f[k + 4])
    if None in (x, y, m, facing, level) or "." not in f[k + 1]:
        return 0, None
    info = {"guid": f[at], "pos": [m, x, y, round(facing, 3)]}
    if f[at + 1] != NO_GUID and not INTEGER.match(f[at + 1]):
        info["owner"] = f[at + 1]
    unit = unit_numbers([int(v.split("|", 1)[0]) for v in f[at + 2:k]], level)
    if unit:
        info["unit"] = unit
    return k + 5 - at, info


def unit_numbers(nums, last):
    if len(nums) < 9:
        return None
    out = {"h": nums[0], "mh": nums[1], "ap": nums[2], "sp": nums[3], "ar": nums[4],
           "pt": nums[-4], "p": nums[-3], "mp": nums[-2], "lv": last}
    if len(nums) >= 10:
        out["ab"] = nums[-5]
    return out


def _flag(v):
    return {"1": True, "nil": False}.get(v)


def _suffix(s, numbers, extra, least):
    newer = len(s) > numbers and all(INTEGER.match(v) for v in s[:numbers]) and _flag(s[numbers]) is not None
    older = len(s) > numbers - 1 and all(INTEGER.match(v) for v in s[:numbers - 1]) \
        and _flag(s[numbers - 1]) is not None
    if not (newer or older) or _int(s[0]) < 0:
        return None
    out = {"a": _int(s[0])}
    if newer != older:
        place = 2 if newer else 1
        more, cr = _int(s[place]), _flag(s[numbers if newer else numbers - 1])
        if more >= least:
            out[extra] = more
        if cr:
            out["cr"] = 1
    return out


def damage_suffix(s, least=0):
    return _suffix(s, 7, "ok", least)


def heal_suffix(s):
    return _suffix(s, 4, "oh", 1)


def absorbed(f):
    at = 9 if GUID.match(f[9] if len(f) > 9 else "") else 12
    if len(f) < at + 8 or not GUID.match(f[at]) or not INTEGER.match(f[at + 4]) or not INTEGER.match(f[at + 7]):
        return {}
    return {"xs": int(f[at + 4]), "xsn": f[at + 5], "a": int(f[at + 7])}


def combat(rest):
    head = rest.split(",", 1)[0]
    if head not in KEPT:
        return None
    f = fields(rest)
    if len(f) < 9:
        return None
    e = f[0]
    ev = {"e": e, "sg": f[1], "sn": f[2], "sf": _flags(f[3]), "dg": f[5], "dn": f[6], "df": _flags(f[7])}
    if e == "SPELL_ABSORBED":
        if not GUID.match(f[9] if len(f) > 9 else "") and len(f) >= 12:
            ev["sp"], ev["spn"] = _int(f[9]), f[10]
        ev.update(absorbed(f))
        return ev
    p = prefix_size(e)
    if p == 3 and len(f) >= 12:
        ev["sp"], ev["spn"] = _int(f[9]), f[10]
        if _flags(f[11]):
            ev["sc"] = _flags(f[11])
    at = 9 if p == 1 else 9 + p
    size, info = advanced(f, at)
    if info:
        ev["info"] = info
    suffix = f[at + size:]
    if p == 1 and suffix:
        ev["spn"], suffix = suffix[0], suffix[1:]
    got = damage_suffix(suffix, 1 if p == 1 else 0) if e in DAMAGE else heal_suffix(suffix) if e in HEAL else None
    if got:
        ev.update(got)
    elif e in MISSED and suffix and MISS_KIND.match(suffix[0]):
        ev["m"] = suffix[0]
    elif e in ("SPELL_DRAIN", "SPELL_LEECH") and suffix and INTEGER.match(suffix[0]) and _int(suffix[0]) >= 0:
        ev["a"] = _int(suffix[0])
    if e in EXTRA_SPELL and len(suffix) >= 2 and INTEGER.match(suffix[0]):
        ev["xs"], ev["xsn"] = int(suffix[0]), suffix[1]
        suffix = suffix[3:]
    if e.startswith("SPELL_AURA_") or e == "SPELL_DISPEL":
        if suffix and suffix[0] in AURA_KINDS:
            ev["aura"] = suffix[0]
    return ev


def mine(flags):
    return bool(flags & MINE)


def is_me(flags):
    return bool(flags & MINE) and bool(flags & PLAYER)


def player_controlled(flags):
    return bool(flags & CONTROL_PLAYER)


def hostile_player(flags):
    return bool(flags & CONTROL_PLAYER) and bool(flags & HOSTILE) and not flags & MINE


def npc_of(guid):
    parts = (guid or "").split("-")
    if len(parts) >= 7 and parts[0] in ("Creature", "Vehicle", "Pet") and parts[5].isdigit():
        return int(parts[5])
    return None



CHAT = (
    ("to", re.compile(r"^To \[?(?P<who>[^\]:]+?)\]?: (?P<text>.*)$")),
    ("whisper", re.compile(r"^\[?(?P<who>[^\[\]:]+?)\]? whispers: (?P<text>.*)$")),
    ("say", re.compile(r"^\[?(?P<who>[^\[\]:]+?)\]? says: (?P<text>.*)$")),
    ("yell", re.compile(r"^\[?(?P<who>[^\[\]:]+?)\]? yells: (?P<text>.*)$")),
    ("channel", re.compile(r"^\[(?P<chan>[^\]]+)\] \[?(?P<who>[^\[\]:]+?)\]?: (?P<text>.*)$")),
)
CHANNELS = {"party": "party", "party leader": "party", "raid": "raid", "raid leader": "raid", "raid warning": "raid",
            "guild": "guild", "officer": "officer", "instance": "party", "instance leader": "party"}


def chat(rest):
    rest = rest.rstrip("\r\n")
    for kind, rx in CHAT:
        m = rx.match(rest)
        if m:
            d = m.groupdict()
            out = {"ch": kind, "who": d["who"].strip(), "text": d["text"]}
            if kind == "channel":
                chan = d["chan"].strip()
                out["ch"] = CHANNELS.get(chan.lower(), "channel")
                if out["ch"] == "channel":
                    out["chan"] = chan
            return out
    return {"ch": "system", "who": None, "text": rest}


def first_name(name):
    return (name or "").split("-", 1)[0].strip()


def mentions(text, name):
    n = first_name(name)
    return bool(n) and re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", text or "", re.IGNORECASE) is not None
