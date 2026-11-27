# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
from collections import Counter
import threading

import client
from game import GameNotFound, installed_version
from serverlog import start_thread
import storedonly
from spelltext import MULTIPLY_POINTS, on_curve

TABLES = ("TraitNodeEntry", "TraitDefinition", "TraitDefinitionEffectPoints", "CurvePoint", "TraitNodeXTraitNodeEntry",
          "TraitCurrencySource", "TraitCurrency")


def _int(v):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


class Tables:

    def __init__(self, rows):
        defs = {_int(r["ID"]): _int(r.get("SpellID")) for r in rows("TraitDefinition")}
        self.spell = {}
        self.definition = {}
        for r in rows("TraitNodeEntry"):
            d = _int(r.get("TraitDefinitionID"))
            self.definition[_int(r["ID"])], self.spell[_int(r["ID"])] = d, defs.get(d, 0)
        curves = {}
        for r in rows("CurvePoint"):
            curves.setdefault(_int(r.get("CurveID")), []).append((float(r.get("Pos_0") or 0), float(r.get("Pos_1") or 0)))
        self.curves = {}
        for r in rows("TraitDefinitionEffectPoints"):
            points = sorted(curves.get(_int(r.get("CurveID")), ()))
            if points:
                self.curves[(_int(r.get("TraitDefinitionID")), _int(r.get("EffectIndex")))] = (_int(r.get("OperationType")), points)
        self.node_entries = {}
        for r in rows("TraitNodeXTraitNodeEntry"):
            self.node_entries.setdefault(_int(r.get("TraitNodeID")), []).append(_int(r.get("TraitNodeEntryID")))
        self.levels = {}
        self.given = {}
        for r in rows("TraitCurrencySource"):
            currency, level, amount, entry = (_int(r.get(k)) for k in ("TraitCurrencyID", "PlayerLevel", "Amount", "TraitNodeEntryID"))
            if not level or not currency:
                continue
            if entry:
                self.given.setdefault(entry, []).append((currency, level, amount))
            elif not _int(r.get("QuestID")) and not _int(r.get("AchievementID")):
                self.levels.setdefault(currency, Counter())[level] += amount
        self.most = {_int(r["ID"]): _int(r.get("SourcedMax")) for r in rows("TraitCurrency")}

    def value(self, taken, spell, index):
        for _node, entry, rank in taken or ():
            if self.spell.get(entry) == spell:
                held = self.curves.get((self.definition.get(entry), index))
                if not held or held[0] == MULTIPLY_POINTS:
                    return None
                return on_curve(held[1], rank)
        return 0

    def has(self, taken, spell):
        return any(self.spell.get(entry) == spell for _node, entry, _rank in taken or ())

    def points(self, taken):
        got, currency = Counter(), None
        for node, entry, _rank in taken or ():
            mine = self.given.get(entry)
            if not mine:
                continue
            currency, start = mine[0][0], min(level for _, level, _ in mine)
            for other in self.node_entries.get(node) or [entry]:
                for c, level, amount in self.given.get(other) or ():
                    if c == currency and level >= start:
                        got[level] += amount
        if currency is None:
            return None
        got.update(self.levels.get(currency) or {})
        levels = sorted(level for level, n in got.items() for _ in range(n))
        most = self.most.get(currency)
        return levels[:most] if most else levels


_kept = {"build": None, "tables": None}
_loading = threading.Lock()


def _build():
    try:
        return installed_version()
    except (GameNotFound, OSError, ValueError):
        return None


def load(build):
    try:
        _kept.update(tables=Tables(lambda t: client.rows(t, build, stored=True)), build=build)
    except (storedonly.NotStored, GameNotFound, OSError, ValueError, KeyError):
        pass


def _load(build):
    try:
        load(build)
    finally:
        _loading.release()


def tables(wait=False):
    build = _build()
    if _kept["tables"] is not None and _kept["build"] == build:
        return _kept["tables"]
    if wait:
        with _loading:
            if _kept["tables"] is None or _kept["build"] != build:
                load(build)
        return _kept["tables"] if _kept["build"] == build else None
    if _loading.acquire(blocking=False):
        start_thread("legacy tables", _load, (build,))
    return None


def taken(char):
    return ((char or {}).get("legacy") or {}).get("nodes") or []


def known(char):
    return not taken(char) or tables() is not None


def value(char, spell, index):
    nodes = taken(char)
    t = tables() if nodes else None
    got = t.value(nodes, spell, index) if t else 0
    return got or 0


def has(char, spell):
    nodes = taken(char)
    t = tables() if nodes else None
    return bool(t and t.has(nodes, spell))


def points(char):
    nodes = taken(char)
    t = tables() if nodes else None
    return t.points(nodes) if t else None
