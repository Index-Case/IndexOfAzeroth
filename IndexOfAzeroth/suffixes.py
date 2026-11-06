# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import html as htmllib
import re
import threading

import client
import game
import storedonly

TABLES = ("ItemBonus", "ItemNameDescription", "RandPropPoints")
STAT, WORDS = 2, 5
MARK = 54
QUALITY_COLUMN = {2: "Good", 3: "Superior", 4: "Epic"}
SLOT_COLUMN = {1: 0, 4: 0, 5: 0, 7: 0, 17: 0, 20: 0, 3: 1, 6: 1, 8: 1, 10: 1, 12: 1, 2: 2, 9: 2, 11: 2, 14: 2, 16: 2,
               23: 2, 13: 3, 21: 3, 22: 3, 15: 4, 25: 4, 26: 4}
ATTRIBUTES = {3: "Agility", 4: "Strength", 5: "Intellect", 6: "Spirit", 7: "Stamina"}
RESISTANCES = {51: "Fire", 52: "Frost", 53: "Holy", 54: "Shadow", 55: "Nature", 56: "Arcane"}
SCHOOLS = {84: "Holy", 85: "Fire", 86: "Nature", 87: "Frost", 88: "Shadow", 89: "Arcane"}
HEALING, SPELL_DAMAGE = 41, 42
EQUIP = {12: "Increased Defense +{}.", 38: "+{} Attack Power.", 43: "Restores {} mana per 5 sec.",
         46: "Restores {} health per 5 sec.", 45: "Increases damage and healing done by magical spells and effects by up to {}."}
ROUNDED_DOWN = {HEALING, SPELL_DAMAGE, 45}

_lock = threading.Lock()
_kept = {}


def number(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def read(bonus_rows, word_rows, point_rows):
    lists = {}
    for r in bonus_rows:
        parent = number(r.get("ParentItemBonusListID"))
        if parent is not None:
            lists.setdefault(parent, []).append((number(r.get("OrderIndex")) or 0, number(r.get("Type")),
                                                 number(r.get("Value_0")) or 0, number(r.get("Value_1")) or 0))
    lists = {k: [e[1:] for e in sorted(v, key=lambda e: e[0])] for k, v in lists.items()}
    words = {number(r.get("ID")): r.get("Description_lang") or "" for r in word_rows}
    points = {number(r.get("ID")): r for r in point_rows}
    return lists, words, points


def tables():
    try:
        installed = client.installed_version()
        builds = tuple(client.stored_build(t, installed) for t in TABLES)
    except (OSError, game.GameNotFound):
        return None
    if None in builds:
        return None
    with _lock:
        if builds in _kept:
            return _kept[builds]
    try:
        got = read(*(client.rows(t, b, stored=True) for t, b in zip(TABLES, builds)))
    except (OSError, ValueError, storedonly.NotStored):
        return None
    with _lock:
        _kept.clear()
        _kept[builds] = got
    return got


def amount(stat, share, budget):
    total = share * budget
    return total // 10000 if stat in ROUNDED_DOWN else (2 * total + 10000) // 20000


def budget_of(tip, inv, points):
    level = re.search(r"<!--ilvl-->(\d+)", tip.get("tooltip") or "")
    row = points.get(int(level[1])) if level else None
    quality, column = QUALITY_COLUMN.get(tip.get("quality")), SLOT_COLUMN.get(inv)
    return number((row or {}).get(f"{quality}_{column}")) if quality and column is not None else None


def lines(totals):
    plain, equip, whole = [], [], True
    for stat, v in totals.items():
        if v <= 0 or (stat == SPELL_DAMAGE and totals.get(HEALING)):
            continue
        if stat in ATTRIBUTES:
            plain.append(f"<br><span><!--stat{stat}-->+{v} {ATTRIBUTES[stat]}</span>")
        elif stat in RESISTANCES:
            plain.append(f"<br>+{v} {RESISTANCES[stat]} Resistance")
        elif stat in SCHOOLS:
            equip.append(f"Increases damage done by {SCHOOLS[stat]} spells and effects by up to {v}.")
        elif stat in EQUIP:
            equip.append(EQUIP[stat].format(v))
        elif stat == HEALING:
            damage = totals.get(SPELL_DAMAGE)
            equip.append(f"Increases healing done by up to {v} and damage done by up to {damage} for all magical spells "
                         f"and effects." if damage else f"Increases healing done by spells and effects by up to {v}.")
        else:
            whole = False
    return plain, equip, whole


def apply(tip, bonuses, inv, got=None):
    got = tables() if got is None else got
    if not got:
        return None, False
    lists, words, points = got
    budget, whole = budget_of(tip, inv, points), True
    names, totals = [], {}
    for b in bonuses:
        if b not in lists:
            whole = False
            continue
        for kind, value, share in lists[b]:
            if kind == WORDS and words.get(value):
                names.append(words[value])
            elif kind == STAT and budget is not None:
                totals[value] = totals.get(value, 0) + amount(value, share, budget)
            elif kind != MARK:
                whole = False
    plain, equip, said = lines(totals)
    text = tip.get("tooltip") or ""
    if plain:
        whole = whole and "<!--ebstats-->" in text
        text = text.replace("<!--ebstats-->", "".join(plain) + "<!--ebstats-->", 1)
    if equip:
        whole = whole and "<!--rr-->" in text
        text = text.replace("<!--rr-->", "<!--rr-->" + "".join(f'<span class="q2">Equip: {e}</span><br>' for e in equip), 1)
    name = tip.get("name") or ""
    if names:
        suffix = " ".join(names)
        text, n = re.subn(r'(<!--nstart--><b class="q\d+">)(.*?)(</b>)', lambda m: f"{m[1]}{m[2]} {htmllib.escape(suffix)}{m[3]}",
                          text, count=1)
        whole = whole and n == 1
        name = f"{name} {suffix}".strip()
    return {**tip, "name": name, "tooltip": text}, whole and said
