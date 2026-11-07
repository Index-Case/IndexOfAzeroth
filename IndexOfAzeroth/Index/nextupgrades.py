# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import gamedata
import market
import upgrades
from facts import RUN_SPEED
from mapzones import place_name, world_pos
from questplan import WALK_MARGIN

LEVELS_AHEAD = 2
PER_SLOT = 10
OTHER_CONTINENT = 15.0
FAR_MINUTES = 10.0
QUEST_MINUTES = 5.0
PURSE_MINUTES = 10.0
CRAFT_MINUTES = 15.0
CRAFT_AHEAD = 10
SKILL_POINT_MINUTES = 2.0
TAKE_UP_MINUTES = 10.0
GATHER_MINUTES = 10.0
LEVEL_MINUTES = 30.0
EASY_MINUTES = 20.0
KIND_SHARE = {"clear": 1.0, "weak": 0.75, "debatable": 0.5}
SLOT_GROUP = {12: 11, 14: 13}
SLOT_ORDER = (1, 2, 3, 15, 5, 9, 10, 6, 7, 8, 11, 13, 16, 17, 18)


def rank(worth, minutes):
    return worth / (1 + minutes / EASY_MINUTES)


def order(far, cost):
    return (bool(far), cost)


def worth(cmp):
    return (cmp.get("net") or 0) * KIND_SHARE.get(cmp.get("kind"), 0)


def yards_minutes(yards):
    return yards * WALK_MARGIN / RUN_SPEED / 60


def walk(here, there):
    if not here or not there:
        return None
    if here[0] != there[0]:
        return OTHER_CONTINENT
    return yards_minutes(math.hypot(there[1] - here[1], there[2] - here[2]))


def price_minutes(price, gold):
    return PURSE_MINUTES * (price / max(gold or 0, 1)) ** 2


def wearable(it, level, profs):
    if (it.get("rl") or 0) > level + LEVELS_AHEAD:
        return False
    if not it.get("needs"):
        return True
    name, need = it["needs"]
    have = ((profs or {}).get(name) or {}).get("rank") or 0
    return need <= have + CRAFT_AHEAD


def upgrade(it, me, profs):
    if not it or not it.get("inv") or not wearable(it, me["level"], profs):
        return None
    v = upgrades.verdict(it, {**me, "level": me["level"] + LEVELS_AHEAD})
    return v if v["up"] and v["u"]["use"] == "yes" and not v["u"].get("lower") and v["cmp"] else None


def ways(src, plan, here, gold):
    out = []

    def go(kind, minutes, away, zone=None, abroad=False, **more):
        out.append({"kind": kind, "minutes": minutes + (away or 0), "away": away, "abroad": abroad,
                    "far": abroad or (away or 0) > FAR_MINUTES, "zone": zone, **more})

    def at(there, kind, minutes, zone=None, **more):
        go(kind, minutes, walk(here, there), zone=zone or (place_name(None, *there) if there else None),
           abroad=bool(here and there and here[0] != there[0]), **more)

    for q in src["quests"]:
        first = plan.by_id.get(q["first"]) or {}
        st = (first.get("start") or [{}])[0]
        there = world_pos(st["map"], (st.get("x") or 0) / 100, (st.get("y") or 0) / 100) if st.get("map") else None
        at(there, "quest", QUEST_MINUTES * (q["before"] + 1), st.get("zone"), quest=q["name"], before=q["before"])
    v = src["vendor"]
    if v:
        price = v.get("price")
        go("vendor", price_minutes(price, gold) if price else 0, yards_minutes(v.get("yards") or 0), v.get("zone"),
           vendor=v["name"], price=price)
    ah, house = src["auction"], src.get("auctioneer")
    if ah and ah.get("value") and house:
        go("auction", price_minutes(ah["value"], gold), yards_minutes(house.get("yards") or 0), house.get("zone"),
           auctioneer=house["name"], price=ah["value"])
    for d in src["grind"]:
        chance = (d.get("kill") or 0) + (d.get("skin") or 0)
        if chance > 0:
            kills = 1 / chance
            at(d.get("near"), "drop", kills * (d.get("sec") or 0) / 60, mob=d["name"], kills=round(kills))
    for d in src.get("once") or ():
        chance = (d.get("kill") or 0) + (d.get("skin") or 0)
        if chance > 0:
            kills, wait = 1 / chance, (d.get("respawn") or 0) / 60
            at(d.get("near"), "once", (d.get("sec") or 0) / 60 + (kills - 1) * wait, mob=d["name"], kills=round(kills),
               respawn=max(1, round(wait)))
    for c in src["crafts"]:
        need, have = c.get("skill") or 0, c.get("yours")
        short = need - (have or 0)
        if short > CRAFT_AHEAD:
            continue
        go("craft", CRAFT_MINUTES + max(0, short) * SKILL_POINT_MINUTES + (TAKE_UP_MINUTES if have is None else 0), None,
           profession=c["profession"], skill=c.get("skill"), takeUp=have is None)
    for n in src["gather"]:
        go("gather", GATHER_MINUTES, None, node=n["name"])
    return out


def pass_over(look, me, gold, tips, listed=(), table=None):
    if me.get("worn") is None:
        return {"known": False, "slots": []}
    level, profs = me["level"], (look.me.get("state") or {}).get("profs")
    table = gamedata.client_table("items.json", "items")[1] if table is None else table
    picks = {}
    for item in look.items(listed):
        row = table.get(str(item))
        if not row or row[3] or (row[gamedata.ITEM_REQUIRED] if len(row) > gamedata.ITEM_REQUIRED else 0) > level + LEVELS_AHEAD:
            continue
        it = tips.stats(item)
        v = upgrade(it, me, profs)
        if not v:
            continue
        got = ways(look.sources(item), look.plan, look.me.get("here"), gold)
        if not got:
            continue
        best = min(got, key=lambda w: order(w["far"], w["minutes"]))
        later = max(0, (it.get("rl") or 0) - level)
        minutes = best["minutes"] + later * LEVEL_MINUTES
        w = worth(v["cmp"])
        picks.setdefault(SLOT_GROUP.get(v["slot"], v["slot"]), []).append(
            {"item": item, "tag": v["tag"], "kind": v["cmp"]["kind"], "worth": round(w, 2), "minutes": round(minutes, 1),
             "rank": round(rank(w, minutes), 3), "way": best, "from": it["rl"] if later else None})
    slots = []
    for slot in SLOT_ORDER:
        rows = sorted(picks.get(slot, ()), key=lambda r: (order(r["way"]["far"], -r["rank"]), r["minutes"], r["item"]))[:PER_SLOT]
        if rows:
            slots.append({"slot": slot, "items": rows})
    shown = [r["item"] for s in slots for r in s["items"]]
    infos, ah = gamedata.item_infos(shown), look.auction(shown)
    for s in slots:
        for r in s["items"]:
            info = infos.get(str(r["item"])) or {}
            r.update(name=info.get("n"), q=info.get("q"), icon=info.get("icon"), ah=ah.get(str(r["item"])),
                     iconStored=market.icon_stored(info["icon"]) if info.get("icon") else False,
                     keys=look.keys(r["item"], ah.get(str(r["item"])) or {}))
    return {"known": True, "slots": slots}


def answer(hub):
    import itemsources
    import planning
    look = itemsources.lookup(hub)
    me, _ = planning.wearer(hub)
    gold = ((hub.status or {}).get("nums") or {}).get("money") or 0
    return pass_over(look, me, gold, gamedata.ITEM_TIPS, hub.auction.listed_counts())
