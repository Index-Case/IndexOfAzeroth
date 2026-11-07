# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import client
import game
import storedonly

SIDES = {0: "Alliance", 1: "Horde"}
NAME_KEYS = ("ClientFileString", "ClientPrefix", "Name_lang", "Name_female_lang")
WORD = 0xFFFFFFFF
CLASSIC = 0xFF
_kept = {}


def table():
    installed = client.installed_version()
    if installed in _kept:
        return _kept[installed]
    build = client.stored_build("ChrRaces", installed)
    if build is None:
        raise storedonly.NotStored("Not stored yet: the client's race table")
    if build not in _kept:
        _kept[build] = client.rows("ChrRaces", build, stored=True)
    return _kept[build]


def number(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def playable(rows=None):
    out = []
    for r in table() if rows is None else rows:
        at = number(r.get("PlayableRaceBit"))
        if at is None or at < 0 or number(r.get("ID")) is None:
            continue
        out.append({"id": number(r["ID"]), "bit": 1 << at, "side": SIDES.get(number(r.get("Alliance"))),
                    "names": {r[k] for k in NAME_KEYS if r.get(k)}, "file": r.get("ClientFileString") or None,
                    "shown": r.get("Name_lang") or None})
    return out


def bit_of(name, side, rows=None):
    try:
        found = [r for r in playable(rows) if name and name in r["names"]]
    except (OSError, ValueError, KeyError, game.GameNotFound):
        return 0
    if len({r["bit"] for r in found}) == 1:
        return found[0]["bit"]
    mine = [r for r in found if r["side"] == side]
    return mine[0]["bit"] if len(mine) == 1 else 0


def id_of(name, side, rows=None):
    bit = bit_of(name, side, rows)
    try:
        return next((r["id"] for r in playable(rows) if r["bit"] == bit), 0) if bit else 0
    except (OSError, ValueError, KeyError, game.GameNotFound):
        return 0


def shown_name(name, side, rows=None):
    bit = bit_of(name, side, rows)
    return next((r["shown"] for r in playable(rows) if r["bit"] == bit), None) if bit else None


def side_mask(side, rows=None):
    mask = 0
    for r in playable(rows):
        if r["side"] == side:
            mask |= r["bit"]
    return mask


def side_of(mask, rows=None):
    sides = {r["side"] for r in playable(rows) if mask and mask & r["bit"]} - {None}
    return sides.pop() if len(sides) == 1 else "Both"


def spell_mask(lo, hi=0):
    return (number(lo) or 0) & WORD | ((number(hi) or 0) & WORD) << 32


def every_mask(rows=None):
    every = 0
    for r in playable(rows):
        every |= r["bit"]
    return every


def every_race(mask, every):
    return not mask or mask & every == every


def twins(rows=None):
    by_file = {}
    for r in playable(rows):
        if r["side"] and r["file"]:
            by_file.setdefault(r["file"], {})[r["side"]] = r["bit"]
    return [sides for _, sides in sorted(by_file.items()) if len(sides) > 1]


def _sided_twins(sides, rows):
    wanted = {"Alliance", "Horde"} if sides in (None, "Both") else {sides}
    return [(sum(t.values()), sum(bit for side, bit in t.items() if side in wanted)) for t in twins(rows)]


def with_twins(mask, sides, rows=None):
    if not mask:
        return mask
    for every, mine in _sided_twins(sides, rows):
        if mask & every:
            mask |= mine
    return mask


def joined(mask, other, sides, rows=None):
    if not mask:
        return mask
    wanted = ("Alliance", "Horde") if sides in (None, "Both") else (sides,)
    return mask | (other or 0) & sum(side_mask(side, rows) for side in wanted)


def forever_joined(mask, other, sides, rows=None):
    return joined(mask, with_twins((other or 0) & ~CLASSIC, sides, rows), sides, rows)


def id_bits(rows=None):
    return {r["id"]: r["bit"] for r in playable(rows)}
