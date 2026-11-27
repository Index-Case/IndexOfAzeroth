# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json

import classtrip
import director_rules
import levelreport
import mapzones
import questplan
import races
from planning import class_near, here_now, playing_char, quest_opens, quest_state, who_now

AHEAD = int(director_rules.plain()["next"]["ahead"])
LEADS_MOST = 12


def zones_ahead(book, zone_levels, level, ahead, me, done, maps, cap):
    out = []
    for z in levelreport.zones_reached(zone_levels, [level + 1, level + ahead], book, me, done, level, cap):
        info = maps.get(str(z["map"])) or {}
        if info.get("name") and info.get("instance") is not None:
            out.append({"m": z["map"], "n": info["name"], "lv": int(z["levels"][0]), "i": int(info["instance"])})
    return out


def quests_here(book, here, me, done, log, cap):
    out = {int(q): 0 for q in log}
    zone = book.zones.get(here) or {}
    for qid in zone.get("quests") or ():
        q = book.quests.get(qid)
        if q and qid not in out and questplan.open_now(q, me["side"], me["race"], me["classId"], done, log, cap):
            out[qid] = q.get("req") or 0
    return out


def next_table(book, zone_levels, maps, level, here, me, done, log, cap, ahead=AHEAD):
    zones = zones_ahead(book, zone_levels, level, ahead, me, done, maps, cap)
    here_name = (maps.get(str(here)) or {}).get("name") if here is not None else None
    if not zones or not here_name:
        return None
    mine = quests_here(book, here, me, done, log, cap)
    for z in zones:
        z["q"] = sorted(q for q, req in mine.items() if req <= z["lv"] and book.quests.get(q)
                        and book.leads_to(book.quests[q], z["m"]))[:LEADS_MOST]
    return {"here": here_name, "zones": zones}


class NextZones:
    def __init__(self, hub):
        self.hub = hub

    def wanted(self):
        hub, me = self.hub, playing_char(self.hub)
        s = hub.state or {}
        who = who_now(hub)
        if not me or not s.get("level") or not s.get("map") or not who.get("side"):
            return None
        done, log = quest_state(hub)
        return (json.dumps(me, sort_keys=True), int(s["level"]), who["side"], who.get("classId"), who.get("race"),
                int(s["map"]), tuple(sorted(log)), len(done), id(getattr(hub, "zone_levels", None)),
                hub.characters.max_level())

    def table(self, wanted):
        hub = self.hub
        char, level, side, cid, race, here = json.loads(wanted[0]), wanted[1], wanted[2], wanted[3], wanted[4], wanted[5]
        cap = wanted[9]
        done, log = quest_state(hub)
        me = {"side": side, "classId": cid, "race": races.bit_of(race, side)}
        t = next_table(questplan.book(), getattr(hub, "zone_levels", None) or {}, mapzones.MAPS, level, here, me, done, log, cap)
        cq = classtrip.offers(classtrip.chains(), cid, side, me["race"], done, log, level, AHEAD, cap,
                                class_near(hub, here_now(hub)), quest_opens(hub))
        if not t and not cq:
            return None
        return {"char": char, **(t or {}), **({"cq": cq} if cq else {})}
