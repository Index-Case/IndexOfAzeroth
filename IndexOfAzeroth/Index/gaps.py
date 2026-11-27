# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import re

import signals
import words

LOADED_ONLY = ("data", "plans")

ID = re.compile(r"^[A-Za-z0-9 :'_-]{1,60}$")
NAME_MOST = 80


def kind_names():
    return {"item-tip": words.say("page.gaps.kind.item-tip"),
            "spell-tip": words.say("page.gaps.kind.spell-tip"),
            "mob-level": words.say("page.gaps.kind.mob-level"),
            "npc-place": words.say("page.gaps.kind.npc-place")}


def place_names():
    return {"tooltip": words.say("page.gaps.place.tooltip"),
            "npcs": words.say("page.gaps.place.npcs"),
            "rares": words.say("page.gaps.place.rares"),
            "dungeons": words.say("page.gaps.place.dungeons")}


KINDS = tuple(kind_names())
PLACES = tuple(place_names())


def thing(oid):
    if isinstance(oid, bool):
        return None
    if isinstance(oid, int):
        return oid if oid > 0 else None
    oid = str(oid or "").strip()
    if not ID.match(oid):
        return None
    return int(oid) if oid.isdigit() and int(oid) > 0 else oid


def note(kind, oid, where, name=None):
    oid = thing(oid)
    if kind not in KINDS or where not in PLACES or oid is None:
        raise ValueError(f"not a gap: {kind!r} {oid!r} at {where!r}")
    name = str(name).strip()[:NAME_MOST] if isinstance(name, str) and name.strip() else None
    return signals.send("gap", gap=kind, id=oid, where=where, name=name)
