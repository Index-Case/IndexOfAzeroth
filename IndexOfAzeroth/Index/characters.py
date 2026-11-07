# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import copy
import os
import re
import statistics
import threading
import time
import store
import storewriter
from facts import MAX_LEVEL, RUN_SPEED
from protocol import ADDON_OPTIONS, addon_options

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "characters.json")
RATE = 0.05 / 8
AWAY_RATE = RATE / 4
CAP = 1.5
CALIBRATE_AFTER = 1800
TICKING = frozenset({"lastSeen", "seenAt", "played", "levelPlayed"})
SAVE_EVERY = 15
TRAVEL_FASTEST = 14.0
TRAVEL_STEADY = 25.0
TRAVEL_FASTER = 1.05



def realm_key(realm):
    return re.sub(r"[\s'\-]", "", realm or "").lower()


_REGION_WORD = re.compile(r"(EU|NA|US)\d*", re.I)
_REGION_SHOWN = {"EU": "EU", "NA": "NA", "US": "NA"}
_TYPE_WORDS = {"pvp": {"pvp"}, "pve": {"pve"}, "rp": {"rp"}, "rppvp": {"rp", "pvp"}, "rppve": {"rp", "pve"}}


def realm_label(realm):
    words = re.split(r"[\s_\-]+", realm or "")
    regions = {_REGION_SHOWN[w[:2].upper()] for w in words if _REGION_WORD.fullmatch(w)}
    kinds = set().union(*(_TYPE_WORDS.get(w.lower(), set()) for w in words))
    if len(regions) != 1 or {"pvp", "pve"} <= kinds:
        return realm or ""
    kind = ("RP PvP" if {"rp", "pvp"} <= kinds else "RP" if "rp" in kinds else "PvP" if "pvp" in kinds
            else "PvE" if "pve" in kinds else None)
    return f"{regions.pop()} {kind}" if kind else realm


def beta_realm(realm):
    return "beta" in realm_key(realm)


def full_name(c):
    c = c or {}
    return " ".join(p for p in (c.get("name"), c.get("surname")) if p)


def name_key(c):
    full = full_name(c)
    return f"{full}-{c['realm']}" if (c or {}).get("realm") else full


def char_key(c):
    return (c or {}).get("guid") or name_key(c)


def same_char(a, b):
    if not (a and b and a.get("name") and b.get("name")):
        return False
    if a.get("guid") and b.get("guid"):
        return a["guid"] == b["guid"]
    return (a["name"] == b["name"] and (a.get("surname") is None or b.get("surname") is None or a["surname"] == b["surname"])
            and (not a.get("realm") or not b.get("realm") or a["realm"] == b["realm"]))


def char_label(c, chars):
    full = full_name(c)
    twin = any(full_name(o) == full and (o.get("realm") or "") != (c.get("realm") or "") for o in chars)
    return f"{full}-{realm_label(c['realm'])}" if twin and c.get("realm") else full


def seen_record(key, c, chars, zone_map=lambda name: None):
    if not c or not c.get("lastSeen"):
        return None
    spot = c.get("seenAt") or {}
    return {"character": key, "name": char_label(c, chars), "at": c["lastSeen"],
            "level": c.get("level"), "zone": c.get("zone"), "subzone": c.get("subzone"),
            "map": spot.get("map") or zone_map(c.get("subzone")) or zone_map(c.get("zone")),
            "pos": {"x": spot["x"], "y": spot["y"]} if spot else None, "facing": spot.get("facing")}


def char_entry(c):
    c = c or {}
    return {"name": c.get("name", ""), "surname": c.get("surname", ""), "realm": c.get("realm", ""),
            **({"guid": c["guid"]} if c.get("guid") else {})}


def names_char(c, name):
    if not name or not (c or {}).get("name"):
        return False
    head, *after = str(name).split("-")
    words = head.split() + [w.strip() for w in after]
    while words and not words[-1]:
        words.pop()
    if not words or words[0].lower() != c["name"].lower():
        return False
    rest = words[1:]
    if rest and c.get("surname") and rest[0].lower() == c["surname"].lower():
        rest = rest[1:]
    realm = [realm_key(w) for w in rest]
    return not realm or (bool(c.get("realm")) and realm_key(c["realm"]) in ("".join(realm), "".join(realm[:-1])))


def key_named(chars, name, guid=None):
    if guid:
        mine = next((k for k, c in chars.items() if c.get("guid") == guid), None)
        if mine:
            return mine
        chars = {k: c for k, c in chars.items() if not c.get("guid")}
    found = [k for k, c in chars.items() if names_char(c, name)]
    return found[0] if len(found) == 1 else None


def rested_gain(char, hours, factor=1.0):
    return char.get("xpMax", 0) * (RATE if char.get("resting") else AWAY_RATE) * hours * factor


def cap_of(char):
    return (char or {}).get("maxLevel") or MAX_LEVEL


def projected(char, now, factor=1.0):
    cap = char.get("xpMax", 0) * CAP
    hours = max(0.0, now - char.get("lastSeen", now)) / 3600
    return min(cap, char.get("rested", 0) + rested_gain(char, hours, factor)), cap


class Characters:

    def __init__(self):
        self.lock = threading.Lock()
        self.data = self.load()
        self.current = None
        self.on_move = None
        self.held = False
        self.pending = None
        self.saved = 0
        self.version = 0
        self.steady = None
        self.starting_taxi = lambda race, faction, class_id: set()
        self.leveled = None
        self.fresh = set()

    def load(self):
        d = store.load_json(STATE, {})
        d.setdefault("chars", {})
        d.setdefault("samples", [])
        return d

    def save(self):
        storewriter.save_json_later(STATE, self.data)
        self.saved = time.time()
        self.version += 1

    def factor(self):
        s = self.data["samples"]
        return statistics.median(s) if s else 1.0

    def identity(self, ch, now=None):
        now = now or time.time()
        if not ch.get("name"):
            return False
        with self.lock:
            chars, removed = self.data["chars"], self.data.setdefault("removed", {})
            key, before = self._key_of(ch), self.current
            moved, changed = self._claim(ch, key, now) if ch.get("guid") else (None, False)
            if moved and before == moved[0]:
                before = moved[1]
            if key not in chars and key in removed:
                chars[key] = removed.pop(key)
                chars[key].pop("removedAt", None)
            record = chars.setdefault(key, {"name": ch["name"], "realm": ch.get("realm", "")})
            other = before is not None and key != before
            if key != self.current:
                self.pending = dict(record) if record.get("lastSeen") and now - record["lastSeen"] > CALIBRATE_AFTER else None
                self.current, self.fresh = key, set()
            self.held = False
            record.update(name=ch["name"], surname=ch.get("surname", ""), realm=ch.get("realm", ""), race=ch.get("race", ""),
                          professions=ch.get("professions", []), **({"guid": ch["guid"]} if ch.get("guid") else {}))
            self.version += 1
            if changed:
                self.save()
        if moved and self.on_move:
            self.on_move(*moved)
        return other

    def _key_of(self, ch):
        if ch.get("guid"):
            return char_key(ch)
        every = {**self.data.get("removed", {}), **self.data["chars"]}
        named = [k for k, c in every.items() if same_char(c, ch)]
        return max(named, key=lambda k: every[k].get("lastSeen") or 0) if named else char_key(ch)

    def _claim(self, ch, key, now):
        every, old = {**self.data["removed"], **self.data["chars"]}, name_key(ch)
        named = lambda c: full_name(c) == full_name(ch) and realm_key(c.get("realm")) == realm_key(ch.get("realm"))
        kept = every.get(old)
        moved = None
        if (key not in every and kept is not None and not any(c.get("guid") and named(c) for c in every.values())
                and (not kept.get("race") or not ch.get("race") or kept["race"] == ch["race"])):
            self._move(old, key)
            moved = (old, key)
        others = [k for k, c in self.data["chars"].items() if k != key and named(c)]
        for k in others:
            self._aside(k, now)
        return moved, bool(moved or others)

    def _aside(self, key, now=None):
        record = self.data["chars"].pop(key)
        self.data.setdefault("removed", {})[key] = {**record, "removedAt": round(now or time.time())}
        if key == self.current:
            self.current = None

    def _move(self, old, new):
        where = self.data["chars"] if old in self.data["chars"] else self.data["removed"]
        where[new] = where.pop(old)
        self.data.setdefault("moved", {})[old] = new
        if self.current == old:
            self.current = new
        if self.steady and self.steady[0] == old:
            self.steady = (new, *self.steady[1:])

    def _resolve(self, key):
        known = key in self.data["chars"] or key in self.data.get("removed", {})
        return key if known else (self.data.get("moved") or {}).get(key, key)

    def resolve(self, key):
        with self.lock:
            return self._resolve(key)

    def was(self, key):
        with self.lock:
            return sorted(old for old, new in (self.data.get("moved") or {}).items() if new == key) if key else []

    def moves(self):
        with self.lock:
            return sorted((self.data.get("moved") or {}).items())

    def hold(self):
        with self.lock:
            self.held = True

    def confirmed(self):
        return None if self.held or not self.current else self.data["chars"].get(self.current)

    def talent_build(self, build=None, pick=False):
        with self.lock:
            record = self.confirmed()
            if not pick:
                return (record or {}).get("talentBuild")
            if not record or record.get("talentBuild") == build:
                return False
            if build:
                record["talentBuild"] = build
            else:
                record.pop("talentBuild", None)
            self.save()
            return True

    def records(self):
        with self.lock:
            return {k: char_entry(c) for k, c in {**self.data.get("removed", {}), **self.data["chars"]}.items()}

    def playing(self):
        with self.lock:
            return copy.deepcopy(self.data["chars"].get(self.current)) if self.current else None

    def last(self):
        with self.lock:
            return copy.deepcopy(self._last())

    def _last(self):
        chars = self.data["chars"]
        if self.current in chars:
            return chars[self.current]
        return max(chars.values(), key=lambda c: c.get("lastSeen") or 0, default=None)

    def _board(self, records):
        return {k: c for k, c in records.items() if not beta_realm(c.get("realm"))}

    def last_seen(self, zone_map=lambda name: None):
        with self.lock:
            shown = self._board(self.data["chars"])
            key = self.current if self.current in shown else max(shown, key=lambda k: shown[k].get("lastSeen") or 0, default=None)
            me = shown.get(key)
            if not me or not me.get("lastSeen"):
                return None
            return seen_record(key, me, shown.values(), zone_map)

    def realm(self):
        with self.lock:
            return (self._last() or {}).get("realm") or ""

    def taxi(self, known):
        with self.lock:
            if not self.confirmed():
                return
            record = self.data["chars"][self.current]
            if record.get("taxi") != known:
                record["taxi"] = known
                self.version += 1

    def camped(self, key=None, now=None):
        with self.lock:
            record = self.confirmed() if key is None else self.data["chars"].get(self._resolve(key))
            if not record or record.get("camped"):
                return False
            record["camped"] = round(now or time.time())
            self.save()
            return True

    def completed(self, ids, now=None):
        with self.lock:
            if not self.confirmed():
                return
            self.fresh.add("completed")
            record = self.data["chars"][self.current]
            ids = sorted(set(int(i) for i in ids))
            if record.get("completed") != ids:
                record["completed"], record["completedAt"] = ids, round(now or time.time())
                self.save()

    def spells(self, ids, now=None):
        with self.lock:
            if not self.confirmed():
                return
            record = self.data["chars"][self.current]
            ids = sorted(set(int(i) for i in ids))
            if record.get("spells") != ids:
                record["spells"], record["spellsAt"] = ids, round(now or time.time())
                self.save()

    def pet_spells(self, ids, now=None):
        with self.lock:
            if not self.confirmed():
                return
            record = self.data["chars"][self.current]
            kept = sorted(set(record.get("petSpells") or ()) | {int(i) for i in ids})
            if record.get("petSpells") != kept:
                record["petSpells"], record["petSpellsAt"] = kept, round(now or time.time())
                self.save()

    def explored(self, files, build, now=None):
        with self.lock:
            if not self.confirmed():
                return False
            record = self.data["chars"][self.current]
            files = sorted(set(int(f) for f in files))
            kept = record.get("explored") or {}
            if kept.get("files") == files and kept.get("build") == build:
                return False
            record["explored"] = {"files": files, "build": build, "at": round(now or time.time())}
            self.save()
            return True

    def explored_of(self, key):
        with self.lock:
            key = self._resolve(key)
            record = self.data["chars"].get(key) or self.data.get("removed", {}).get(key) or {}
            return copy.deepcopy(record.get("explored"))

    def known_pet_spells(self):
        with self.lock:
            c = self.data["chars"].get(self.current, {}) if self.current else {}
            return set(c.get("petSpells") or ())

    def recipes(self, read):
        with self.lock:
            if not self.confirmed() or not read.get("name"):
                return
            record = self.data["chars"][self.current]
            kept = {"line": read["line"], "skill": read["skill"], "max": read["max"], "second": read["second"],
                    "at": read["at"], "known": {str(s): c for s, c in read["recipes"]}}
            books = record.setdefault("recipes", {})
            if books.get(read["name"]) != kept:
                books[read["name"]] = kept
                self.save()

    def profession_trainer(self, profession, npc, ranks, at):
        with self.lock:
            if not self.confirmed() or not profession:
                return
            self.data["chars"][self.current].setdefault("profTrainers", {})[profession] = {"npc": npc, "at": at, "ranks": ranks}
            self.save()

    def prof_epic(self, name, do, key=None, now=None):
        with self.lock:
            record = self.confirmed() if key is None else self.data["chars"].get(self._resolve(key))
            if not record or not name:
                return False
            epics = record.setdefault("profEpics", {})
            had = epics.get(name)
            if do == "start" and not had:
                epics[name] = {"at": round(now or time.time()), "hidden": False}
            elif do == "stop" and had:
                del epics[name]
            elif do in ("hide", "unhide") and had and had.get("hidden") != (do == "hide"):
                had["hidden"] = do == "hide"
            else:
                return False
            self.save()
            return True

    def known_spells(self):
        with self.lock:
            c = self.data["chars"].get(self.current, {}) if self.current else {}
            return set(c["spells"]) if c.get("spells") is not None else None

    def completed_ids(self):
        with self.lock:
            c = self.data["chars"].get(self.current, {}) if self.current else {}
            return set(c.get("completed") or ())

    def equipped(self, items, now=None, keys=None):
        keys = keys if any(isinstance(k, str) for k in keys or ()) else None
        with self.lock:
            was = self.data["chars"][self.current].get("equipped") or {} if self.confirmed() else None
            if was is None or (was.get("items") == items and was.get("keys") == keys):
                return
            self.data["chars"][self.current]["equipped"] = {"items": items, **({"keys": keys} if keys else {}),
                                                            "at": round(now or time.time())}
            self.save()

    def containers(self, where, snap):
        with self.lock:
            if where == "warband":
                old = self.data.get("warband")
                if old and old.get("at", 0) > snap["at"] or old == snap:
                    return
                self.data["warband"] = snap
            else:
                if not self.confirmed():
                    return
                self.fresh.add(where)
                record = self.data["chars"][self.current]
                if record.get(where) == snap or (record.get(where) or {}).get("at", 0) > snap["at"]:
                    return
                record[where] = snap
            self.save()

    def legacy(self, data, now=None):
        now = round(now or time.time())
        account = {k: data.get(k) for k in ("currency", "max", "cap", "whole")}
        account["done"] = sorted(({"id": d["id"], "amount": d.get("amount") or 0, "by": d.get("by")}
                                  for d in data.get("done") or ()), key=lambda d: d["id"])
        mine = {k: data.get(k) for k in ("spent", "unspent")}
        with self.lock:
            moved = False
            old = self.data.get("legacy") or {}
            if {k: v for k, v in old.items() if k != "at"} != account:
                self.data["legacy"], moved = {**account, "at": now}, True
            me = self.confirmed()
            if me is not None and any(v is not None for v in mine.values()):
                if {k: v for k, v in (me.get("legacy") or {}).items() if k != "at"} != mine:
                    me["legacy"], moved = {**mine, "at": now}, True
            if moved:
                self.save()
            return moved

    def game_said(self):
        with self.lock:
            me = self.confirmed()
            if not me:
                return None, None, None
            done = set(me.get("completed") or ()) if "completed" in self.fresh else None
            items = lambda where: {int(i): n for i, n in ((me.get(where) or {}).get("items") or {}).items()}
            bags = items("bags") if "bags" in self.fresh else None
            bank = {"at": me["bank"].get("at"), "items": items("bank")} if me.get("bank") else None
            return done, bags, bank

    def bags_now(self):
        with self.lock:
            me = self.confirmed()
            if not me or "bags" not in self.fresh:
                return None
            return {int(i): n for i, n in ((me.get("bags") or {}).get("items") or {}).items()}

    def travel_speed(self):
        with self.lock:
            c = self.data["chars"].get(self.current, {}) if self.current else {}
            travel = c.get("travel") or 0.0
            return travel if travel >= RUN_SPEED * TRAVEL_FASTER else RUN_SPEED

    def travel(self, c, state, flags, now):
        speed = state.get("speed") or 0.0
        if flags.get("taxi") or flags.get("ghost") or not RUN_SPEED * TRAVEL_FASTER <= speed <= TRAVEL_FASTEST:
            self.steady = None
            return
        s = self.steady
        if not s or s[0] != self.current or abs(s[1] - speed) > 0.15:
            self.steady = (self.current, speed, now)
        elif now - s[2] >= TRAVEL_STEADY and speed > (c.get("travel") or RUN_SPEED):
            c["travel"] = round(speed, 1)

    def max_level(self):
        with self.lock:
            return cap_of(self.data["chars"].get(self.current) if self.current else None)

    def options(self):
        with self.lock:
            said = self.data.get("options") or {}
            return {name: said.get(name, default) for name, (_, default) in ADDON_OPTIONS.items()}

    def known_taxi(self):
        with self.lock:
            c = self.data["chars"].get(self.current, {}) if self.current else {}
            taxi, race, faction, class_id = copy.deepcopy(c.get("taxi")), c.get("race"), c.get("faction"), c.get("classId")
        starts = self.starting_taxi(race, faction, class_id) if race else set()
        if not starts:
            return taxi
        taxi = dict(taxi or {})
        taxi["ids"] = sorted(set(taxi.get("ids") or ()) | starts)
        return taxi

    def update(self, state, status, live, now=None):
        now = now or time.time()
        if not live:
            return
        with self.lock:
            c = self.confirmed()
            if c is None:
                return
            old = c.get("level")
            before = {k: c.get(k) for k in ("levelPlayed", "xpMax", "talentPoints")}
            was = self.lasting(c)
            if state:
                flags = state.get("flags") or {}
                c.update(level=state.get("level"), xp=state.get("xp"), xpMax=state.get("xpMax"), rested=state.get("rested"),
                         resting=bool(flags.get("resting")), zone=state.get("zone"), subzone=state.get("subzone"))
                pos = state.get("pos")
                if state.get("map") and pos:
                    c["seenAt"] = {"map": state["map"], "x": pos["x"], "y": pos["y"], "facing": state.get("facing")}
                self.travel(c, state, flags, now)
                if self.pending:
                    self.calibrate(self.pending, c, now)
                    self.pending = None
            if status:
                nums, strs = status.get("nums") or {}, status.get("strs") or {}
                c["classId"], c["className"] = status.get("classId"), status.get("className")
                for key in ("money", "bagFree", "bagSlots", "durability", "talentPoints"):
                    if key in nums:
                        c[key] = nums[key]
                if nums.get("maxLevel"):
                    c["maxLevel"] = nums["maxLevel"]
                said = addon_options(nums)
                if said is not None:
                    self.data["options"] = said
                if "playedSeconds" in nums:
                    c["played"], c["levelPlayed"] = nums["playedSeconds"], nums.get("levelSeconds")
                for key in ("bind", "faction"):
                    if strs.get(key):
                        c[key] = strs[key]
            c["lastSeen"] = now
            if self.leveled:
                self.leveled(self.current, old if isinstance(old, int) else None, c, now, before)
            if self.lasting(c) != was or now - self.saved > SAVE_EVERY:
                self.save()

    def lasting(self, c):
        return {k: v for k, v in c.items() if k not in TICKING}, self.data.get("options"), self.data["samples"]

    def calibrate(self, before, after, now):
        if not before.get("xpMax") or before.get("level") != after.get("level") or (after.get("level") or 0) >= cap_of(after):
            return
        hours = (now - before["lastSeen"]) / 3600
        expected = rested_gain(before, hours)
        cap = before["xpMax"] * CAP
        actual = (after.get("rested") or 0) - (before.get("rested") or 0)
        if expected < before["xpMax"] * 0.01 or (after.get("rested") or 0) >= cap * 0.98 or actual < 0:
            return
        self.data["samples"] = (self.data["samples"] + [round(actual / expected, 3)])[-8:]

    def forget(self, key):
        with self.lock:
            key = self._resolve(key)
            if key not in self.data["chars"]:
                return
            self._aside(key)
            self.save()

    def restore(self, key):
        with self.lock:
            key = self._resolve(key)
            record = self.data.get("removed", {}).pop(key, None)
            if record is None:
                return False
            record.pop("removedAt", None)
            self.data["chars"].setdefault(key, record)
            self.save()
            return True

    def snapshot(self):
        with self.lock:
            return {"chars": copy.deepcopy(self._board(self.data["chars"])), "current": self.current, "factor": self.factor(),
                    "warband": copy.deepcopy(self.data.get("warband")),
                    "legacy": copy.deepcopy(self.data.get("legacy")),
                    "removed": {k: {"name": r.get("name"), "surname": r.get("surname", ""), "realm": r.get("realm", ""),
                                    "level": r.get("level"), "className": r.get("className"), "removedAt": r.get("removedAt"),
                                    "played": r.get("played")}
                                for k, r in self._board(self.data.get("removed", {})).items()},
                    "samples": len(self.data["samples"]), "rate": RATE, "awayRate": AWAY_RATE, "cap": CAP, "maxLevel": MAX_LEVEL}
