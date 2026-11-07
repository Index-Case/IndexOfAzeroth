# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import gamedata
import market
import nextupgrades
from camping import category

UPGRADES_MOST = 30
KIND_ORDER = {"clear": 0, "weak": 1, "debatable": 2}
HOW_ORDER = {"known": 0, "trainer": 1, "vendor": 2}


def learn_way(cd, spell, known, have):
    r = cd.recipe(spell)
    if spell in known or (have and "skill" in (r.get("learnt") or ())):
        return {"how": "known"}
    teach = cd.teachers.get(spell)
    if teach:
        return {"how": "trainer", "npcs": sorted(teach)}
    sold = [int(p) for p in r.get("items") or () if cd.sellers(p)]
    return {"how": "vendor", "pattern": sold[0]} if sold else None


def best_recipe(pd, spells, known, have):
    found = [(s, learn_way(pd.cd, s, known, have)) for s in spells]
    found = [(s, w) for s, w in found if w]
    return min(found, key=lambda f: (HOW_ORDER[f[1]["how"]], pd.learnt_at(f[0]) or 0, f[0]), default=None)


def rows(pd, line, me, profs, known, tips, items=None):
    cd, name = pd.cd, pd.cd.names.get(line, "")
    have = (profs or {}).get(name)
    yours = have["rank"] if have else None
    makes = pd.makes(line)
    out = []
    for item in (makes if items is None else [i for i in items if i in makes]):
        got = best_recipe(pd, makes[item], known, have)
        if not got:
            continue
        spell, learn = got
        it = tips.stats(item)
        v = nextupgrades.upgrade(it, me, profs) if me.get("worn") is not None else None
        skill = pd.learnt_at(spell)
        later = v and (it.get("rl") or 0) > me["level"]
        out.append({"item": item, "spell": spell, "recipe": cd.name(spell), "learn": learn, "skill": skill, "yours": yours,
                    "short": max(0, (skill or 0) - (yours or 0)), "tag": v["tag"] if v else None,
                    "kind": v["cmp"]["kind"] if v else None, "worth": round(nextupgrades.worth(v["cmp"]), 2) if v else None,
                    "from": it["rl"] if later else None})
    return out


def marks(pd, me, profs, tips):
    out = {}
    for name in sorted(profs or ()):
        line = pd.by_name.get(name)
        if line is None or not pd.gear(line):
            continue
        for item, spells in pd.makes(line).items():
            v = nextupgrades.upgrade(tips.stats(item), me, profs)
            if v:
                out.update(dict.fromkeys(spells, v["cmp"]["kind"]))
    return out


def upgrades_of(found):
    ups = [r for r in found if r["kind"]]
    ups.sort(key=lambda r: (KIND_ORDER.get(r["kind"], 3), -(r["worth"] or 0), r["item"]))
    return ups[:UPGRADES_MOST]


def dress(found, listed, nearest, seller):
    infos = gamedata.item_infos([r["item"] for r in found] + [r["learn"]["pattern"] for r in found if r["learn"].get("pattern")])
    for r in found:
        info = infos.get(str(r["item"])) or {}
        learn = r["learn"]
        if learn["how"] == "trainer":
            learn["npc"] = (nearest(learn["npcs"]) or {}).get("name")
        elif learn["how"] == "vendor":
            learn["npc"] = (seller(learn["pattern"]) or {}).get("name")
            learn["patternName"] = (infos.get(str(learn["pattern"])) or {}).get("n")
        r.update(name=info.get("n"), q=info.get("q"), icon=info.get("icon"), ah=listed.get(str(r["item"])),
                 iconStored=market.icon_stored(info["icon"]) if info.get("icon") else False)
    return found


def answer(hub, line, text=None):
    import itemsources
    import planning
    pd = planning.prof_data()
    if not pd.gear(line):
        return None
    look = itemsources.lookup(hub)
    me, _ = planning.wearer(hub)
    state = look.me.get("state") or {}
    name = pd.cd.names.get(line, "")
    known = (state.get("known") or {}).get(name) or set()
    s, faction = hub.state or {}, look.me.get("faction") or ""
    pos = s.get("pos")

    def nearest(npcs):
        if not pos or not s.get("map"):
            return None
        return hub.world.nearest(s["map"], pos["x"], pos["y"], faction, {category(name)}, npcs=npcs)

    out = {"line": line, "name": name, "known": me.get("worn") is not None}
    if text:
        found, more = market.search(text, True, hub.auction.listed_counts(), only=set(pd.makes(line)))
        got = rows(pd, line, me, state.get("profs"), known, gamedata.ITEM_TIPS, [f[0] for f in found])
        out.update(finds=got, more=more)
    else:
        got = upgrades_of(rows(pd, line, me, state.get("profs"), known, gamedata.ITEM_TIPS))
        out["upgrades"] = got
    dress(got, hub.auction.summaries([r["item"] for r in got])["items"], nearest, look.seller)
    return out
