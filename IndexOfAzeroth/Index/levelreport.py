# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import glob
import os
import re
import threading
import time

import levelshots
import savedvars
from serverlog import start_thread
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "levelreports.json")
SAVED_NAME = "IndexOfAzeroth.lua"
SAVED_EVERY = 5
GAINS = ("health", "mana", "talents", "str", "agi", "sta", "int", "spi")
UNLOCK_RULES = 3
VITALS_WAIT = 30


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class LevelReports:
    def __init__(self, path=STATE):
        self.path = path
        self.lock = threading.Lock()
        self.data = store.load_json(path, {})
        self.data.setdefault("chars", {})
        self.version = 0
        self.saved_seen = {}
        self.build = None
        self.building = set()
        self.fresh = set()
        self.shots = levelshots.STORE
        self.resolve = lambda key: key

    def _char(self, key):
        return self.data["chars"].setdefault(key, {"reports": {}})

    def move(self, old, new):
        with self.lock:
            had = self.data["chars"].pop(old, None)
            if had is None:
                return False
            ch = self._char(new)
            for level, rep in (had.get("reports") or {}).items():
                ch["reports"][level] = {**rep, **ch["reports"].get(level, {})}
            for field, value in had.items():
                ch.setdefault(field, value)
            self.fresh = {(new if k == old else k, lv) for k, lv in self.fresh}
            self._save()
            return True

    def _save(self):
        storewriter.save_json_later(self.path, self.data)
        self.version += 1


    def frame(self, key, old, c, now=None, before=None):
        new = c.get("level")
        if not key or not isinstance(new, int) or new < 1:
            return
        now = now or time.time()
        with self.lock:
            ch = self._char(key)
            start = ch.get("start")
            if old and new > old:
                made = []
                for level in range(old + 1, new + 1):
                    rep = self._report(ch, level)
                    one = new == old + 1
                    rep["by"] = sorted(set(rep.get("by") or ()) | {"strip"})
                    rep["at"] = rep.get("at") or round(now)
                    for k, v in (("zone", c.get("zone")), ("className", c.get("className")), ("class", c.get("classId")),
                                 ("race", c.get("race")), ("faction", c.get("faction"))):
                        if v and not rep.get(k):
                            rep[k] = v
                    if one:
                        before = before or {}
                        if start and start.get("level") == old and start.get("seen") and not rep.get("began"):
                            rep["began"] = start.get("at")
                        total = _num(c.get("played"))
                        if not rep.get("played") and start and start.get("level") == old and start.get("seen") \
                                and total is not None and _num(start.get("played")) is not None \
                                and total > start["played"]:
                            rep["played"] = total - start["played"]
                        if not rep.get("played") and (_num(before.get("levelPlayed")) or 0) > 0:
                            rep["played"] = before["levelPlayed"]
                        if rep.get("xpLevel") is None and _num(before.get("xpMax")):
                            rep["xpLevel"] = before["xpMax"]
                        money = _num(c.get("money"))
                        if rep.get("gold") is None and start and start.get("level") == old and start.get("seen") \
                                and money is not None and _num(start.get("money")) is not None:
                            rep["gold"] = money - start["money"]
                        if money is not None and rep.get("money") is None:
                            rep["money"] = money
                        tp = _num(before.get("talentPoints"))
                        if tp is not None and _num(c.get("talentPoints")) is not None and c["talentPoints"] > tp:
                            rep.setdefault("stats", {}).setdefault("talents", c["talentPoints"] - tp)
                        v = ch.get("vitals") or {}
                        stats = rep.setdefault("stats", {})
                        for name in ("health", "spirit"):
                            if _num(v.get(name)) is not None and "was" + name.title() not in stats:
                                stats["was" + name.title()] = v[name]
                    made.append(rep)
                    self.fresh.add((key, level))
                ch["start"] = {"level": new, "money": _num(c.get("money")), "played": _num(c.get("played")),
                               "at": round(now), "seen": True}
                self._save()
                for rep in made:
                    self._build_later(key, rep)
                return
            if not start or start.get("level") != new:
                ch["start"] = {"level": new, "money": _num(c.get("money")), "played": _num(c.get("played")),
                               "at": round(now), "seen": False}
                self._save()
            elif start.get("money") is None and _num(c.get("money")) is not None:
                start["money"] = c["money"]

    def vitals(self, key, most=None, spirit=None, now=None):
        if not key:
            return
        now = now or time.time()
        with self.lock:
            ch = self._char(key)
            v = ch.setdefault("vitals", {})
            moved = False
            for name, value in (("health", _num(most)), ("spirit", _num(spirit))):
                if value is None or v.get(name) == value:
                    continue
                v[name] = value
                rep = self._newest(ch)
                if rep and now - (rep.get("at") or 0) <= VITALS_WAIT:
                    stats = rep.setdefault("stats", {})
                    was = stats.get("was" + name.title())
                    if was is not None and value != was:
                        stats["now" + name.title()] = value
                        moved = True
            if moved:
                self._save()


    def take_saved(self, table, now=None):
        changed = []
        if not isinstance(table, dict):
            return changed
        for key, entry in table.items():
            records = entry.get("list") if isinstance(entry, dict) else None
            if not isinstance(key, str) or not isinstance(records, (list, dict)):
                continue
            key = self.resolve(key)
            records = list(records.values() if isinstance(records, dict) else records)
            totals = {int(r["level"]): r["played"] for r in records if isinstance(r, dict) and _num(r.get("level"))
                      and (_num(r.get("played")) or 0) > 0}
            for rec in records:
                level = _num(rec.get("level")) if isinstance(rec, dict) else None
                if not level or level < 2:
                    continue
                with self.lock:
                    ch = self._char(key)
                    had = str(int(level)) in ch["reports"]
                    rep = self._report(ch, int(level))
                    before = repr(rep)
                    self._fill(rep, rec, totals.get(int(level) - 1))
                    if repr(rep) == before:
                        continue
                    self._save()
                changed.append((key, int(level)))
                if not had or rep.get("unlocks") is None:
                    self._build_later(key, rep)
        return changed

    @staticmethod
    def _fill(rep, rec, total_before=None):
        rep["by"] = sorted(set(rep.get("by") or ()) | {"saved"})
        if _num(rec.get("at")) and not rep.get("at"):
            rep["at"] = int(rec["at"])
        for mine, theirs in (("played", "levelPlayed"), ("gold", "gold"), ("money", "money")):
            if _num(rec.get(theirs)) is not None and (mine != "played" or rec[theirs] > 0):
                rep[mine] = rec[theirs]
        total = _num(rec.get("played"))
        if not rep.get("played") and total_before and total and total > total_before:
            rep["played"] = total - total_before
        for k in ("zone", "race", "className"):
            if isinstance(rec.get(k), str) and rec[k] and not rep.get(k):
                rep[k] = rec[k]
        if _num(rec.get("class")) and not rep.get("class"):
            rep["class"] = int(rec["class"])
        if _num(rec.get("shot")) and rep.get("shotAt") != int(rec["shot"]):
            rep["shotAt"] = int(rec["shot"])
            if rep.get("shot") is False:
                del rep["shot"]
        stats = rep.setdefault("stats", {})
        for k in GAINS:
            if _num(rec.get(k)) is not None:
                stats[k] = rec[k]

    def saved_files(self, wtf):
        return sorted(glob.glob(os.path.join(wtf, "Account", "*", "SavedVariables", SAVED_NAME)))

    def check_saved(self, wtf):
        changed = []
        for path in self.saved_files(wtf) if wtf else ():
            stamp = store.stamp(path)
            if stamp is None or self.saved_seen.get(path) == stamp:
                continue
            self.saved_seen[path] = stamp
            db = savedvars.read(path).get("IndexOfAzerothDB")
            if isinstance(db, dict) and isinstance(db.get("levels"), dict):
                changed += self.take_saved(db["levels"])
        return changed


    def check_shots(self, folder, now=None):
        now = now or time.time()
        with self.lock:
            wanted = [(key, int(lv), rep.get("at"), rep.get("shotAt"))
                      for key, ch in self.data["chars"].items() for lv, rep in (ch.get("reports") or {}).items()
                      if "shot" not in rep and (rep.get("shotAt") or (key, int(lv)) in self.fresh)]
        if not wanted:
            return []
        files = levelshots.listing(folder, now) if folder else []
        changed = []
        for key, level, at, shot_at in wanted:
            hit = levelshots.find(files, at, shot_at)
            try:
                got = levelshots.copy(hit[0], key, level, self.shots) if hit else None
            except (OSError, ValueError):
                got, hit = None, False
            if not got and hit is None and now <(shot_at + levelshots.SHOT_NEAR + 60 if shot_at else (at or 0) + levelshots.GLOW_UNTIL + 60):
                continue
            with self.lock:
                rep = (self.data["chars"].get(key) or {}).get("reports", {}).get(str(level))
                if rep is None or "shot" in rep:
                    continue
                rep["shot"] = got or False
                self._save()
            self.fresh.discard((key, level))
            changed.append((key, level))
        return changed

    def watch_saved(self, wtf_dir, log_error, stop=None, every=SAVED_EVERY, shots_dir=None):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.check_saved(wtf_dir())
            except Exception:
                log_error("reading the level ups from the SavedVariables")
            try:
                if shots_dir:
                    self.check_shots(shots_dir())
            except Exception:
                log_error("copying the level-up pictures")
            stop.wait(every)


    def _report(self, ch, level):
        return ch["reports"].setdefault(str(level), {"level": level, "from": level - 1, "at": None, "zone": None, "played": None,
                                                     "gold": None, "money": None, "xpLevel": None, "stats": {},
                                                     "kills": None, "spell": None,
                                                     "seen": False, "unlocks": None})

    @staticmethod
    def _newest(ch):
        reps = ch.get("reports") or {}
        return reps[max(reps, key=int)] if reps else None

    def _build_later(self, key, rep):
        if not self.build or (key, rep["level"]) in self.building:
            return
        self.building.add((key, rep["level"]))
        start_thread("level report", self._build, (key, rep["level"]))

    def _build(self, key, level):
        try:
            with self.lock:
                rep = dict(self.data["chars"].get(key, {}).get("reports", {}).get(str(level)) or {})
            got = self.build(key, rep) if rep else None
            if got is None:
                return
            with self.lock:
                live = self.data["chars"].get(key, {}).get("reports", {}).get(str(level))
                if live is not None:
                    live["unlocks"], live["rules"] = got, UNLOCK_RULES
                    self._save()
        finally:
            self.building.discard((key, level))

    def ensure(self, key):
        with self.lock:
            reps = [dict(r) for r in ((self.data["chars"].get(key) or {}).get("reports") or {}).values()
                    if r.get("unlocks") is None or r.get("rules") != UNLOCK_RULES]
        for rep in reps:
            self._build_later(key, rep)

    def rebuild(self, key, level):
        self._build(key, level)

    def of(self, key):
        with self.lock:
            reps = (self.data["chars"].get(key) or {}).get("reports") or {}
            return [dict(reps[k]) for k in sorted(reps, key=int)]


    def wanting(self, key, version):
        with self.lock:
            reps = (self.data["chars"].get(key) or {}).get("reports") or {}
            out = []
            for k, rep in reps.items():
                if rep.get("figures") == version or not _num(rep.get("at")):
                    continue
                since = rep.get("began")
                left = int(rep.get("from") or 0)
                prev = reps.get(str(left or int(k) - 1))
                if not _num(since) and prev and _num(prev.get("at")) and left == int(k) - 1:
                    since = prev["at"]
                if not _num(since) and left == 1 and (_num(rep.get("played")) or 0) > 0:
                    since = rep["at"] - rep["played"]
                if _num(since) and since < rep["at"]:
                    out.append((int(k), since, rep["at"]))
            return sorted(out)

    def characters(self):
        with self.lock:
            return list(self.data["chars"])

    def set_figures(self, key, level, fig, version):
        with self.lock:
            rep = ((self.data["chars"].get(key) or {}).get("reports") or {}).get(str(level))
            if rep is None:
                return
            for k in ("kills", "deaths", "dealt", "taken", "fighting"):
                if _num(fig.get(k)) is not None:
                    rep[k] = fig[k]
            if fig.get("spell"):
                rep["spell"] = fig["spell"]
            rep["figures"] = version
            self._save()

    def seen(self, key, level):
        with self.lock:
            reps = (self.data["chars"].get(key) or {}).get("reports") or {}
            moved = False
            for k, rep in reps.items():
                if int(k) <= level and not rep.get("seen"):
                    rep["seen"] = moved = True
            if moved:
                self._save()
            return moved



ARMOR, WEAPON = 4, 2


def level_range(rep):
    return range(int(rep.get("from") or rep["level"] - 1) + 1, int(rep["level"]) + 1)


def class_spells(cs, cid, race_bit, known, levels):
    sched = ((cs.get("classes") or {}).get(str(cid)) or {}).get("levels") or {}
    out = []
    for lv in levels:
        for s in (sched.get(str(lv)) or {}).get("spells") or ():
            if s.get("pet") == "beast" or s.get("trainer") is False:
                continue
            if s.get("races") and race_bit and not s["races"] & race_bit:
                continue
            if s.get("needs") and not set(s["needs"]) & set(known or ()):
                continue
            out.append({"id": s["id"], "name": s["name"], "rank": s.get("rank"), "icon": s.get("icon"), "cost": s.get("cost"),
                        "level": lv, **({"pet": True} if s.get("pet") else {})})
    return out


def other_gated(gated_by_level, levels):
    out = []
    for lv in levels:
        for e in gated_by_level.get(str(lv)) or ():
            out.append({k: e[k] for k in ("kind", "name", "icon", "spent", "skill", "id", "at") if e.get(k) is not None} | {"level": lv})
    return out


def open_level(d):
    lv = d.get("levels") or []
    return max((lv[0] if lv and lv[0] else (60 if d.get("kind") == "raid" else 0)), d.get("openFrom") or 0)


def dungeons_opened(dungeons, levels):
    lo, hi = levels[0], levels[-1]
    out = []
    for d in dungeons:
        if d.get("kind") not in ("dungeon", "raid") or d.get("notOpen"):
            continue
        lv = d.get("levels") or []
        why = "door" if lo <= open_level(d) <= hi else "range" if len(lv) > 1 and lv[1] and lo <= lv[1] <= hi else None
        if why:
            out.append({"key": d["key"], "name": d["name"], "kind": d["kind"], "levels": lv[1:3], "why": why})
    return out


def quests_opened(book, side, race_bit, cid, done, levels, cap, open_to):
    from epic import closed_by
    lo, hi = levels[0], levels[-1]
    out = []
    for q in book.for_side(side, cid).quests.values():
        req = q.get("req") or 0
        if not lo <= req <= hi or q["id"] in done:
            continue
        if open_to(q, side, race_bit, cid, None, in_log=False, cap=cap) or closed_by(q, done, ()) is not None:
            continue
        if q.get("preAll") and not set(q["preAll"]) <= done or q.get("preAny") and not set(q["preAny"]) & done:
            continue
        start = (q.get("start") or [{}])[0]
        out.append({"id": q["id"], "name": q["name"], "level": q.get("level"), "req": req, "map": start.get("map") or q.get("map"),
                    "zone": start.get("zone"), "giver": start.get("name"), "x": start.get("x"), "y": start.get("y")})
    return sorted(out, key=lambda q: (q["zone"] or "~", q["level"] or 0, q["name"]))


def gear_opened(bags, stats_of, levels, cid, armor_kinds=None, weapon_kinds=None):
    lo, hi = levels[0], levels[-1]
    out = []
    for item in sorted(bags or ()):
        st = stats_of(item)
        if not st or not st.get("inv") or not lo <= (st.get("rl") or 0) <= hi:
            continue
        if st.get("classes") and cid and not st["classes"] & (1 << (cid - 1)):
            continue
        kinds = armor_kinds if st.get("cls") == ARMOR else weapon_kinds if st.get("cls") == WEAPON else None
        if kinds and st.get("sub") and not kinds & (1 << st["sub"]):
            continue
        out.append({"id": item, "name": st.get("n"), "q": st.get("q"), "slot": st.get("slot"), "level": st["rl"]})
    return out


def zone_gives(book, zone, band, level, me, done, cap):
    import questplan
    from epic import closed_by
    to_next, book = questplan.xp_table(), book.for_side(me["side"], me.get("classId"))
    left = []
    for qid in (book.zones.get(zone) or {}).get("quests") or ():
        q = book.quests.get(qid)
        if q and qid not in done and questplan.in_band(q, band) and not questplan.open_to(
                q, me["side"], me.get("race"), me.get("classId"), None, in_log=False, cap=cap):
            left.append(q)
    left.sort(key=lambda q: (questplan.opens_at(q), q.get("level") or 0, q["id"]))
    taken, at, xp, start = set(done), level, 0, level
    while True:
        q = next((q for q in left if set(q.get("preAll") or ()) <= taken
                  and (not q.get("preAny") or set(q["preAny"]) & taken) and closed_by(q, taken, ()) is None), None)
        if not q:
            break
        left.remove(q)
        taken.add(q["id"])
        xp += questplan.quest_xp(q, at, cap)
        while at < cap and to_next.get(at) and xp >= to_next[at]:
            xp -= to_next[at]
            at += 1
    return at - start + (xp / to_next[at] if at < cap and to_next.get(at) else 0)


ZONE_LEAST = 1.0


def zones_reached(zone_levels, levels, book, me, done, level, cap):
    lo, hi = levels[0], levels[-1]
    at = hi if level is None else level
    done, side = set(done or ()), me["side"]
    mine = {q.get("map") for q in book.quests.values() if q.get("side") in (None, side)}
    out = []
    for m, lv in zone_levels.items():
        if lv and lo <= lv[0] <= hi and int(m) in mine:
            gives = zone_gives(book, int(m), lv, at, me, done, cap)
            if gives >= ZONE_LEAST:
                out.append({"map": int(m), "levels": list(lv), "gives": round(gives, 1)})
    return sorted(out, key=lambda z: (-z["gives"], z["levels"][0], z["map"]))


def unlocks(hub, key, rep):
    import questplan
    import races
    from characters import cap_of
    from gamedata import ITEM_TIPS
    from handler import gated_levels
    with hub.characters.lock:
        me = dict(hub.characters.data["chars"].get(key) or {})
    cid = rep.get("class") or me.get("classId")
    if not cid:
        return None
    levels, cap = list(level_range(rep)), cap_of(me)
    side = me.get("faction") or rep.get("faction") or ""
    bit = races.bit_of(me.get("race") or rep.get("race"), side)
    cs = hub.class_spells or {}
    known = set(me.get("spells") or ())
    gated, _ = gated_levels(cs.get("gated") or {}, cid, me, known, levels[-1])
    playing = key == hub.characters.current
    nums = ((hub.status or {}).get("nums") or {}) if playing else {}
    bags = [int(i) for i in ((me.get("bags") or {}).get("items") or {})]
    dungeons = [{**d, **hub.dungeons.open_words(d["key"])} for d in hub.dungeons.list]
    return {"spells": class_spells(cs, cid, bit, known, levels),
            "gated": other_gated(gated, levels),
            "dungeons": dungeons_opened(dungeons, levels),
            "quests": quests_opened(questplan.book(), side, bit, cid, set(me.get("completed") or ()), levels,
                                    cap, questplan.open_to),
            "gear": gear_opened(bags, ITEM_TIPS.stats, levels, cid, nums.get("armorKinds") or None, nums.get("weaponKinds") or None),
            "zones": zones_reached(getattr(hub, "zone_levels", None) or {}, levels, questplan.book(),
                                   {"side": side, "race": bit, "classId": cid}, set(me.get("completed") or ()),
                                   levels[-1], cap),
            "talents": talents_to_take(hub, key, cid, nums, levels) if playing else []}


def talents_to_take(hub, key, cid, nums, levels):
    import talentplan
    c = ((hub.class_spells or {}).get("classes") or {}).get(str(cid))
    ranks = getattr(hub, "talentranks", None)
    got = talentplan.talent_plan(c, int(cid), (talentplan.builds().get("classes") or {}).get(str(cid)), nums,
                                 ranks.ranks(key) if ranks else None, levels[-1], hub.characters.talent_build())
    return [s for s in (got or {}).get("steps") or () if s["level"] in levels]


KEY_PART = re.compile(r"^[^\x00-\x1f]{1,120}$")


def valid_key(key):
    return isinstance(key, str) and bool(KEY_PART.fullmatch(key))
