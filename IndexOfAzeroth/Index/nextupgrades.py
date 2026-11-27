# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

from facts import MAX_LEVEL, RUN_SPEED, xp_table
import gamedata
from itemsources import sure
import market
import upgrades
from mapzones import place_name, world_pos
from questplan import WALK_MARGIN

LEVELS_AHEAD = 2
JOURNAL_AHEAD = MAX_LEVEL
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
BOSS_MINUTES = 8.0
RUN_TOP = 4
KIND_SHARE = {"clear": 1.0, "weak": 0.75, "debatable": 0.5}
VERDICTS = ("clear", "weak", "debatable")
SLOT_GROUP = {12: 11, 14: 13}
SLOT_ORDER = (1, 2, 3, 15, 5, 9, 10, 6, 7, 8, 11, 13, 16, 17, 18)
DUAL_WIELD = {1, 3, 4}
DUAL_WIELD_LEVEL = 10


def rank(worth, minutes):
    return worth / (1 + minutes / EASY_MINUTES)


def order(far, cost, beyond=False):
    return (bool(beyond), bool(far), cost)


def worth(cmp, wear=1.0):
    return (cmp.get("net") or 0) * KIND_SHARE.get(cmp.get("kind"), 0) * wear


def chance(of, up):
    if of is None:
        return None
    return of * (1.0 if up is None else up)


def tries(p):
    return 1 / p if p else 1.0


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


def wearable(it, level, profs, ahead=LEVELS_AHEAD):
    if (it.get("rl") or 0) > level + ahead:
        return False
    if not it.get("needs"):
        return True
    name, need = it["needs"]
    have = ((profs or {}).get(name) or {}).get("rank") or 0
    return need <= have + CRAFT_AHEAD


def upgrade(it, me, profs, ahead=LEVELS_AHEAD):
    if not it or not it.get("inv") or not wearable(it, me["level"], profs, ahead):
        return None
    v = upgrades.verdict(it, {**me, "level": max(me["level"] + LEVELS_AHEAD, it.get("rl") or 0)})
    return v if v["up"] and v["u"]["use"] == "yes" and not v["u"].get("lower") and v["cmp"] else None




def slots_of(inv, cls, level):
    slots = upgrades.SLOTS_FOR.get(inv) or []
    return slots if inv != 13 or (cls in DUAL_WIELD and level >= DUAL_WIELD_LEVEL) else slots[:1]


def worn_from(it, cls):
    level = max(1, it.get("rl") or 1)
    u = upgrades.usability_for(it, cls, level)
    if u["use"] == "later":
        level = u["level"]
        u = upgrades.usability_for(it, cls, level)
    return level if u["use"] in ("yes", "train") and not u.get("lower") else None


class Ahead:

    def __init__(self, items, cls, w, tips, table, cap=MAX_LEVEL):
        self.cap, self.best = cap, {}
        for item in items:
            row = table.get(str(item))
            if not row or row[3]:
                continue
            it = tips.stats(item)
            if not it or not it.get("inv") or not it.get("st"):
                continue
            level = worn_from(it, cls)
            if level is None or level > cap:
                continue
            for slot in slots_of(it["inv"], cls, level):
                score = upgrades.gear_score(upgrades.in_slot(it["st"], slot), w)
                best = self.best.setdefault(SLOT_GROUP.get(slot, slot), [0.0] * (cap + 1))
                best[level] = max(best[level], score)

    def replaced(self, slot, score, start):
        best = self.best.get(SLOT_GROUP.get(slot, slot)) or ()
        bar = score + max(upgrades.CLEAR_MIN, score * upgrades.CLEAR_OF)
        return next((level for level in range(start + 1, min(self.cap, len(best) - 1) + 1) if best[level] >= bar), self.cap)


def wear_share(level, start, end, cap=MAX_LEVEL):
    if level >= cap or start >= cap:
        return 1.0
    xp = xp_table()
    ahead = sum(xp.get(n) or 0 for n in range(level, cap))
    worn = sum(xp.get(n) or 0 for n in range(start, min(end, cap)))
    return min(1.0, worn / ahead) if ahead else 1.0


_ahead = {}
AHEAD_KEPT = 4


def ahead_for(look, me, tips, table):
    data = (table, look.farm.world.item_drops(), look.rewards, tips)
    key = (me.get("cls"), tuple(sorted((me.get("w") or {}).items())), look.me.get("faction"), len(look.plan.done),
           *map(id, data))
    got = _ahead.get(key)
    if got is None:
        got = (data, Ahead(look.sure_items(), me.get("cls"), me.get("w") or {}, tips, table))
        while len(_ahead) >= AHEAD_KEPT:
            _ahead.pop(next(iter(_ahead)))
        _ahead[key] = got
    return got[1]




def ways(src, plan, here, gold, level, ahead=LEVELS_AHEAD):
    out = []

    def go(kind, minutes, away, zone=None, abroad=False, **more):
        out.append({"kind": kind, "minutes": minutes + (away or 0), "away": away, "abroad": abroad,
                    "far": abroad or (away or 0) > FAR_MINUTES, "zone": zone, "sure": False, "beyond": False, **more})

    def at(there, kind, minutes, zone=None, **more):
        go(kind, minutes, walk(here, there), zone=zone or (place_name(None, *there) if there else None),
           abroad=bool(here and there and here[0] != there[0]), **more)

    runs = src.get("runs") or ()
    in_runs = {r["questId"] for r in runs if r.get("questId")}
    for q in src["quests"]:
        if q.get("id") in in_runs:
            continue
        first = plan.by_id.get(q["first"]) or {}
        st = (first.get("start") or [{}])[0]
        there = world_pos(st["map"], (st.get("x") or 0) / 100, (st.get("y") or 0) / 100) if st.get("map") else None
        at(there, "quest", QUEST_MINUTES * (q["before"] + 1), st.get("zone"), quest=q["name"], before=q["before"], sure=True)
    v = src["vendor"]
    if v:
        price = v.get("price")
        go("vendor", price_minutes(price, gold) if price else 0, yards_minutes(v.get("yards") or 0), v.get("zone"),
           vendor=v["name"], price=price, sure=True)
    ah, house = src["auction"], src.get("auctioneer")
    if ah and ah.get("value") and house:
        go("auction", price_minutes(ah["value"], gold), yards_minutes(house.get("yards") or 0), house.get("zone"),
           auctioneer=house["name"], price=ah["value"])
    for d in src["grind"]:
        p = (d.get("kill") or 0) + (d.get("skin") or 0)
        if p > 0:
            at(d.get("near"), "drop", tries(p) * (d.get("sec") or 0) / 60, mob=d["name"], kills=round(tries(p)),
               drop=p, sure=sure(p, None, False))
    for d in src.get("once") or ():
        p = chance((d.get("kill") or 0) + (d.get("skin") or 0), d.get("up"))
        if p:
            kills, wait = tries(p), (d.get("respawn") or 0) / 60
            at(d.get("near"), "once", (d.get("sec") or 0) / 60 + (kills - 1) * wait, mob=d["name"], kills=round(kills),
               respawn=max(1, round(wait)), rare=bool(d.get("rare")), up=d.get("up"),
               drop=(d.get("kill") or 0) + (d.get("skin") or 0),
               sure=sure((d.get("kill") or 0) + (d.get("skin") or 0), d.get("up"), d.get("rare")))
    for r in runs:
        if r["open"] > level + ahead:
            continue
        p = chance(r.get("chance"), r.get("up"))
        work = QUEST_MINUTES * (r["before"] + 1) if r.get("quest") else 0
        at(r.get("entrance"), "run", BOSS_MINUTES * max(1, r["bosses"]) * tries(p) + work
           + max(0, r["open"] - level) * LEVEL_MINUTES, r["dungeon"], key=r["key"], dungeon=r["dungeon"], raid=r["raid"],
           open=r["open"], runs=round(tries(p)), chance=p, rare=r["rare"], up=r.get("up"),
           drop=None if r.get("quest") else r.get("chance"),
           sure=sure(r.get("chance"), r.get("up"), r["rare"]), beyond=r["open"] > level + LEVELS_AHEAD,
           **{k: r[k] for k in ("boss", "trash", "quest", "before") if k in r})
    for c in src["crafts"]:
        need, have = c.get("skill") or 0, c.get("yours")
        short = need - (have or 0)
        if short > CRAFT_AHEAD:
            continue
        go("craft", CRAFT_MINUTES + max(0, short) * SKILL_POINT_MINUTES + (TAKE_UP_MINUTES if have is None else 0), None,
           profession=c["profession"], skill=c.get("skill"), takeUp=have is None, sure=True)
    for n in src["gather"]:
        go("gather", GATHER_MINUTES, None, node=n["name"], sure=True)
    return out


def row_order(r):
    return VERDICTS.index(r["kind"]), order(r["way"]["far"], -r["rank"], r["beyond"]), r["minutes"], r["item"]


def where_to_run(slots):
    runs = {}
    for s in slots:
        best = {}
        for r in s["items"]:
            for key, v in r["sure"].items():
                best[key] = max(best.get(key, 0.0), v)
        for key, v in best.items():
            got = runs.setdefault(key, {"key": key, "slots": [], "value": 0.0})
            got["slots"].append(s["slot"])
            got["value"] = round(got["value"] + v, 6)
    return sorted(runs.values(), key=lambda r: (-r["value"], r["key"]))[:RUN_TOP]


def pass_over(look, me, gold, tips, listed=(), table=None, kind=None):
    if me.get("worn") is None:
        return {"known": False, "slots": [], **({"runs": []} if kind else {})}
    level, profs = me["level"], (look.me.get("state") or {}).get("profs")
    ahead = JOURNAL_AHEAD if kind else LEVELS_AHEAD
    table = gamedata.client_table("items.json", "items")[1] if table is None else table
    life = ahead_for(look, me, tips, table)
    picks = {}
    for item in (look.run_items(kind == "raid") if kind else look.items(listed)):
        row = table.get(str(item))
        if not row or row[3] or (row[gamedata.ITEM_REQUIRED] if len(row) > gamedata.ITEM_REQUIRED else 0) > level + ahead:
            continue
        it = tips.stats(item)
        v = upgrade(it, me, profs, ahead)
        if not v:
            continue
        got = [w for w in ways(look.sources(item, runs_only=bool(kind)), look.plan, look.me.get("here"), gold, level, ahead)
               if not kind or w["kind"] == "run" and w["raid"] == (kind == "raid")]
        if not got:
            continue
        later = max(0, (it.get("rl") or 0) - level)
        start = level + later
        until = life.replaced(v["slot"], upgrades.gear_score(upgrades.in_slot(it.get("st"), v["slot"]), me.get("w") or {}), start)
        share = wear_share(level, start, until, life.cap)
        w = worth(v["cmp"], share)
        best = min(got, key=lambda x: order(x["far"], x["minutes"], x["beyond"]))
        minutes = best["minutes"] + later * LEVEL_MINUTES
        beyond = later > LEVELS_AHEAD or best["beyond"]
        sure_runs = {}
        for x in got:
            if x["kind"] == "run" and x["sure"] and not x["beyond"] and later <= LEVELS_AHEAD:
                sure_runs[x["key"]] = max(sure_runs.get(x["key"], 0.0), round(rank(w, x["minutes"] + later * LEVEL_MINUTES), 6))
        picks.setdefault(SLOT_GROUP.get(v["slot"], v["slot"]), []).append(
            {"item": item, "slot": v["slot"], "tag": v["tag"], "kind": v["cmp"]["kind"], "worth": round(w, 4), "minutes": round(minutes, 1),
             "rank": round(rank(w, minutes), 6), "way": best, "from": it["rl"] if later else None, "beyond": beyond,
             "until": until if until < life.cap else None, "wear": round(share, 3), "also": len(got) - 1,
             "sure": sure_runs})
    slots = []
    for slot in SLOT_ORDER:
        rows = sorted(picks.get(slot, ()), key=row_order)[:PER_SLOT]
        if rows:
            slots.append({"slot": slot, "items": rows})
    if kind:
        slots.sort(key=lambda s: row_order(s["items"][0]))
    shown = [r["item"] for s in slots for r in s["items"]]
    infos, ah = gamedata.item_infos(shown), ({} if kind else look.auction(shown))
    for s in slots:
        for r in s["items"]:
            info = infos.get(str(r["item"])) or {}
            r.update(name=info.get("n"), q=info.get("q"), icon=info.get("icon"), ah=ah.get(str(r["item"])),
                     iconStored=market.icon_stored(info["icon"]) if info.get("icon") else False,
                     keys=None if kind else look.keys(r["item"], ah.get(str(r["item"])) or {}))
    return {"known": True, "slots": slots, **({"runs": where_to_run(slots)} if kind else {})}


def answer(hub, kind=None):
    import itemsources
    import planning
    look = itemsources.lookup(hub)
    me, _ = planning.wearer(hub)
    gold = ((hub.status or {}).get("nums") or {}).get("money") or 0
    return pass_over(look, me, gold, gamedata.ITEM_TIPS, () if kind else hub.auction.listed_counts(), kind=kind)
