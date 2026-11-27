# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import html
import re

from gamedata import ITEM_TIPS, client_table, item_ids
from itemtips import MISSING
import questplan

CRATE = "Waylaid Crate"
LABELLED = re.compile(r"^Waylaid Crate: (.+)$")
SEALED = re.compile(r"^Sealed (\w+) Crate$")
QUEST_NAME = "A Sealed Crate"
BUNDLE = re.compile(r"<br\s*/?>\s*-\s*(\d+)\s+([^<]+)")
SIDES = ("Alliance", "Horde")

_bundles = {}
_kinds = {"mtime": None, "kinds": None}
_depots = {"book": None, "depots": None}


def kinds():
    mtime, items, _ = client_table("items.json", "items")
    if _kinds["kinds"] is not None and _kinds["mtime"] == mtime:
        return _kinds["kinds"]
    out = {"open": set(), "fill": {}, "sealed": {}}
    for k, row in items.items():
        name = row[0] if row else ""
        if name == CRATE:
            out["open"].add(int(k))
        elif LABELLED.match(name):
            out["fill"][int(k)] = name
        elif SEALED.match(name):
            out["sealed"][int(k)] = SEALED.match(name).group(1)
    _kinds.update(mtime=mtime, kinds=out)
    return out


def bundles(item):
    if item in _bundles:
        return _bundles[item]
    tip = ITEM_TIPS.tooltip(item)
    if tip == MISSING:
        return None
    found = [[int(n), html.unescape(name).strip()] for n, name in BUNDLE.findall((tip or {}).get("tooltip") or "")]
    ids = item_ids([name for _, name in found])
    _bundles[item] = [[n, name, ids.get(name)] for n, name in found]
    return _bundles[item]


def depots(book=None):
    book = book or questplan.book()
    if _depots["book"] is book:
        return _depots["depots"]
    named = {}
    for q in book.quests.values():
        if q.get("name") == QUEST_NAME:
            for who in (q.get("start") or []) + (q.get("end") or []):
                if who.get("name") and who.get("map") is not None:
                    named.setdefault(who["name"], {k: who.get(k) for k in ("name", "map", "x", "y", "zone")})
    out = {}
    for q in book.quests.values():
        if q.get("side") in SIDES:
            for who in q.get("end") or ():
                if who.get("name") in named:
                    out.setdefault(q["side"], named[who["name"]])
    _depots.update(book=book, depots=out)
    return out


def counted(n, name):
    return f"{n} {name}"


def lines(bags, side, book=None):
    if not isinstance(bags, dict) or not bags:
        return []
    k, out = kinds(), []
    _, items, _ = client_table("items.json", "items")
    name = lambda i: (items.get(str(i)) or [f"item {i}"])[0]
    unopened = sum(bags.get(i, 0) for i in k["open"])
    if unopened:
        out.append({"id": "crate:open", "text": f"Open your {unopened} {CRATE}s" if unopened > 1 else f"Open your {CRATE}",
                    "detail": "Use the crate from your bags to see what it's missing", "item": {"name": CRATE, "words": CRATE, "id": min(k["open"])}})
    for item, label in sorted(k["fill"].items(), key=lambda kv: kv[1]):
        if not bags.get(item):
            continue
        listed = bundles(item)
        if listed is None:
            detail = "The crate's tooltip shows what the crate takes"
        elif not listed:
            detail = "Fill the crate with one of the bundles that its tooltip lists"
        else:
            ready = [b for b in listed if b[2] and bags.get(b[2], 0) >= b[0]]
            have = ", ".join(f"{counted(n, nm)} (you carry {bags.get(i, 0) if i else '?'})" for n, nm, i in listed)
            detail = (f"You carry {counted(ready[0][0], ready[0][1])}, so use the crate to fill it" if ready
                      else f"The crate takes one of these: {have}")
        out.append({"id": f"crate:fill:{item}", "text": f"Fill {label}", "detail": detail,
                    "item": {"name": label, "words": label, "id": item}})
    sealed = {i: bags[i] for i in k["sealed"] if bags.get(i)}
    if sealed:
        n = sum(sealed.values())
        depot = depots(book).get(side)
        where = f" at {depot['name']}" if depot else ""
        kinds_held = sorted({k["sealed"][i] for i in sealed})
        tiers = kinds_held[0] if len(kinds_held) == 1 else ", ".join(kinds_held[:-1]) + " and " + kinds_held[-1]
        line = {"id": "crate:handin", "text": f"Hand in {n} sealed crate{'s' if n > 1 else ''}{where}",
                "detail": f"Your {tiers} crates give Merchant's Favor" + (
                    f". The trade representative is in {depot['zone']}" if depot and depot.get("zone") else
                    ". Your side's trade representative takes the crates" if not depot else ""),
                "item": {"name": name(min(sealed)), "words": "sealed crate", "id": min(sealed)}}
        if depot:
            line["to"] = depot
        out.append(line)
    return out
