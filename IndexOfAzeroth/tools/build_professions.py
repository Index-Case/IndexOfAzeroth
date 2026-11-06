# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import client
from client import PLACEHOLDER
import dropguard

OUT = os.path.join(ROOT, "data", "professions.json")
FILL_FILE = os.path.join(ROOT, "data", "professionfill.json")
CLIENT_TABLES = ("SkillLine", "SkillLineAbility", "SpellName", "Spell", "SpellEffect", "SpellReagents", "SpellTotems",
                 "TotemCategory", "SpellCastingRequirements", "SpellFocusObject", "TradeSkillCategory", "ItemXItemEffect",
                 "ItemEffect", "ItemSparse", "Item", "Lock", "LockType", "CurrencyTypes", "SpellMisc", "SpellDuration", "FactionTemplate")
PROFESSIONS, SECONDARY = 11, 9
WITH_SKILL = 1
CREATE_ITEM, LEARN_SPELL, SKILL_STEP, SKILL = 24, 36, 44, 118
LEARNS = 6
WEAPON, FISHING_POLE = 2, 20
STEP = 75
CAMPING = "Camping"
ON_USE = 0
AURA_DEPTH = 3
SPELL_REF = re.compile(r"\$(?:\?a|@[a-z]+)?(\d+)")
FILL = {"trainers": "the game: a trainer's window as the addon reports it, with what it teaches and the skill, level "
                    "and price each asks",
        "ranks": "the game: a trainer's window as the addon reports it, with the skill, level and price each rank asks",
        "levels": "the game: a trainer's window as the addon reports it, with the level each rank asks",
        "recipes": "the game: the trainers' windows and the recipes you know as the addon reports them",
        "items": "the game: a vendor's window and your bags as the addon reports them",
        "places": "the game: where you stand when its window opens, as the addon reports it",
        "nodes": "the game: the skill a node's tooltip or a failed gather names, as the addon reports it"}


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def by_spell(rows):
    out = {}
    for r in rows:
        out.setdefault(num(r.get("SpellID")), r)
    return out


def keyed(d):
    return {str(k): d[k] for k in sorted(d)}



def professions(lines, abilities, trained=()):
    rows = {num(r["ID"]): r for r in lines}
    under = {}
    for i, r in rows.items():
        if num(r.get("ParentSkillLineID")):
            under.setdefault(num(r["ParentSkillLineID"]), []).append(i)
    top = {i: r for i, r in rows.items() if num(r.get("CategoryID")) in (PROFESSIONS, SECONDARY)
           and not num(r.get("ParentSkillLineID")) and not PLACEHOLDER.search(r.get("DisplayName_lang") or "")}
    owner = {line: i for i in top for line in [i] + under.get(i, [])}
    crafted = {owner[num(a.get("SkillLine"))] for a in abilities if num(a.get("SkillLine")) in owner
               and num(a.get("TrivialSkillLineRankHigh")) and not num(a.get("ClassMask"))}
    crafted |= {owner[line] for line in trained if line in owner}
    return {i: {"n": top[i].get("DisplayName_lang") or "",
                "kind": "primary" if num(top[i]["CategoryID"]) == PROFESSIONS else "secondary",
                "lines": [i] + sorted(under.get(i, [])), "icon": num(top[i].get("SpellIconFileID"))} for i in sorted(crafted)}


def line_owner(profs):
    return {line: p for p, v in profs.items() for line in v["lines"]}


def effects_by_spell(effects):
    out = {}
    for e in effects:
        if not num(e.get("DifficultyID")):
            out.setdefault(num(e.get("SpellID")), []).append(e)
    return out


def ranks(profs, abilities, effects, subtexts):
    owner, steps = line_owner(profs), {}
    for a in abilities:
        prof, sid = owner.get(num(a.get("SkillLine"))), num(a.get("Spell"))
        for e in effects.get(sid, ()):
            if prof is not None and num(e.get("Effect")) in (SKILL_STEP, SKILL) and owner.get(num(e.get("EffectMiscValue_0"))) == prof:
                steps.setdefault(prof, {})[sid] = float(e.get("EffectBasePointsF") or 0)
    out = {}
    for prof, found in steps.items():
        order = sorted(set(found.values()))
        out[prof] = [{"spell": sid, "n": subtexts.get(sid, ""), "step": order.index(v) + 1, "cap": STEP * (order.index(v) + 1)}
                     for sid, v in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))]
    return out


def makes(effects):
    e = next((e for e in effects if num(e.get("Effect")) == CREATE_ITEM and num(e.get("EffectItemType"))), None)
    return [num(e["EffectItemType"]), max(1, round(float(e.get("EffectBasePointsF") or 1)))] if e else None


def reagents(row):
    return [[num(row.get(f"Reagent_{i}")), max(1, num(row.get(f"ReagentCount_{i}")))] for i in range(8)
            if num(row.get(f"Reagent_{i}"))]


def recipes(profs, abilities, effects, names, tables, rank_spells):
    owner, out = line_owner(profs), {}
    mats, totems = by_spell(tables["SpellReagents"]), by_spell(tables["SpellTotems"])
    focus = by_spell(tables["SpellCastingRequirements"])
    for a in abilities:
        prof, sid = owner.get(num(a.get("SkillLine"))), num(a.get("Spell"))
        low, high = num(a.get("TrivialSkillLineRankLow")), num(a.get("TrivialSkillLineRankHigh"))
        made, needs = makes(effects.get(sid, ())), reagents(mats.get(sid, {}))
        if prof is None or sid in rank_spells or sid in out or not (high or made or needs):
            continue
        r = out[sid] = {"n": names.get(sid, ""), "prof": prof}
        if num(a.get("TradeSkillCategoryID")):
            r["group"] = num(a["TradeSkillCategoryID"])
        if high:
            r["colors"] = [low, (low + high) // 2, high]
        r["learnt"] = ["skill"] if num(a.get("AcquireMethod")) == WITH_SKILL else []
        for key, value in (("makes", made), ("reagents", needs)):
            if value:
                r[key] = value
        t = totems.get(sid, {})
        for key, column in (("tools", "RequiredTotemCategoryID"), ("totems", "Totem")):
            got = [num(t.get(f"{column}_{i}")) for i in range(2) if num(t.get(f"{column}_{i}"))]
            if got:
                r[key] = got
        if num(focus.get(sid, {}).get("RequiresSpellFocus")):
            r["station"] = num(focus[sid]["RequiresSpellFocus"])
        if num(a.get("NumSkillUps")) > 1:
            r["points"] = num(a["NumSkillUps"])
    return out


def recipe_items(links, item_effects, effects, known):
    by_id, out = {num(r["ID"]): r for r in item_effects}, {}
    for link in links:
        e = by_id.get(num(link.get("ItemEffectID")))
        sid = num(e.get("SpellID")) if e else 0
        if e and num(e.get("TriggerType")) == LEARNS and sid in known:
            out[num(link["ItemID"])] = sid
            continue
        taught = next((num(x.get("EffectTriggerSpell")) for x in effects.get(sid, ())
                       if num(x.get("Effect")) == LEARN_SPELL and num(x.get("EffectTriggerSpell")) in known), None)
        if taught:
            out[num(link["ItemID"])] = taught
    return out


def learnt_by(effects, known):
    return {sid: num(e.get("EffectTriggerSpell")) for sid, es in effects.items() for e in es
            if num(e.get("Effect")) == LEARN_SPELL and num(e.get("EffectTriggerSpell")) in known}


def item_facts(sparse, wanted, base=()):
    classes = {num(r["ID"]): num(r.get("ClassID")) for r in base if num(r["ID"]) in wanted}
    out = {}
    for r in sparse:
        i = num(r["ID"])
        if i not in wanted:
            continue
        e = out[i] = {"n": r.get("Display_lang") or ""}
        if num(r.get("BuyPrice")):
            e["price"] = num(r["BuyPrice"])
        if num(r.get("VendorStackCount")) > 1:
            e["per"] = num(r["VendorStackCount"])
        if num(r.get("RequiredSkill")):
            e["needs"] = [num(r["RequiredSkill"]), num(r.get("RequiredSkillRank"))]
        if num(r.get("RequiredLevel")) > 1:
            e["rl"] = num(r["RequiredLevel"])
        if i in classes:
            e["cls"] = classes[i]
    return out


def fishing_poles(base):
    return {num(r["ID"]) for r in base if num(r.get("ClassID")) == WEAPON and num(r.get("SubclassID")) == FISHING_POLE}


def tools(categories, sparse, used):
    cats = {num(r["ID"]): r for r in categories}
    of = {}
    for r in sparse:
        if num(r.get("TotemCategoryID")) in cats:
            of.setdefault(num(r["TotemCategoryID"]), []).append(num(r["ID"]))
    out = {}
    for c in sorted(used):
        need = cats.get(c)
        if need is None:
            out[c] = {"n": "", "items": []}
            continue
        kind, mask = num(need.get("TotemCategoryType")), num(need.get("TotemCategoryMask"))
        fits = [i for k, items in of.items() for i in items if num(cats[k].get("TotemCategoryType")) == kind
                and mask and num(cats[k].get("TotemCategoryMask")) & mask == mask]
        out[c] = {"n": need.get("Name_lang") or "", "items": sorted(fits)}
    return out


def groups(profs, categories):
    owner, rows = line_owner(profs), {num(r["ID"]): r for r in categories}
    out, camp = {}, {}
    for i, r in rows.items():
        prof = owner.get(num(r.get("SkillLineID")))
        if prof is None:
            continue
        out.setdefault(prof, {})[i] = {"n": r.get("Name_lang") or "", "parent": num(r.get("ParentTradeSkillCategoryID")) or None,
                                       "order": num(r.get("OrderIndex"))}
        at, seen = i, set()
        while at in rows and at not in seen:
            seen.add(at)
            if rows[at].get("Name_lang") == CAMPING:
                camp[i] = prof
                break
            at = num(rows[at].get("ParentTradeSkillCategoryID"))
    return out, camp


def camping(camp, found):
    out = {}
    for group, prof in sorted(camp.items()):
        out.setdefault(prof, {"groups": [], "recipes": []})["groups"].append(group)
    for sid, r in sorted(found.items(), key=lambda kv: ((kv[1].get("colors") or [0])[0], kv[0])):
        if r.get("group") in camp:
            out[camp[r["group"]]]["recipes"].append(sid)
    return out


def durations(misc, lengths):
    ms = {num(r["ID"]): num(r.get("Duration")) for r in lengths}
    out = {}
    for r in misc:
        if not num(r.get("DifficultyID")) and ms.get(num(r.get("DurationIndex")), 0) > 0:
            out.setdefault(num(r.get("SpellID")), ms[num(r["DurationIndex"])] // 1000)
    return out


def uses(wanted, links, item_effects, words, lasts):
    by_id, out = {num(r["ID"]): r for r in item_effects}, {}
    for link in links:
        item, e = num(link.get("ItemID")), by_id.get(num(link.get("ItemEffectID")))
        if item not in wanted or item in out or not e or num(e.get("TriggerType")) != ON_USE or not num(e.get("SpellID")):
            continue
        sid = num(e["SpellID"])
        said = {"spell": sid, "category": num(e.get("SpellCategoryID")),
                "cooldown": max(num(e.get("CategoryCoolDownMSec")), num(e.get("CoolDownMSec"))) // 1000,
                "lasts": lasts.get(sid), "does": words.get(sid, ("", ""))[0].strip()}
        out[item] = {k: v for k, v in said.items() if v}
    return out


def camp_auras(used, effects, words, names, lasts):
    starts = {u["spell"] for u in used.values()}
    seen, todo, out = set(), [(sid, 0) for sid in sorted(starts)], {}
    while todo:
        sid, depth = todo.pop(0)
        if sid in seen:
            continue
        seen.add(sid)
        desc, aura = words.get(sid, ("", ""))
        if sid not in starts:
            said = {"n": names[sid], "lasts": lasts.get(sid), "does": (aura or desc).strip()}
            out[sid] = {k: v for k, v in said.items() if v}
        if depth < AURA_DEPTH:
            refs = {int(i) for i in SPELL_REF.findall(f"{desc} {aura}")} | \
                   {num(e.get("EffectTriggerSpell")) for e in effects.get(sid, ())}
            todo += [(r, depth + 1) for r in sorted(refs) if r in names]
    return out


def client_part(tables, trained=()):
    abilities, effects = tables["SkillLineAbility"], effects_by_spell(tables["SpellEffect"])
    names = {num(r["ID"]): r.get("Name_lang") or "" for r in tables["SpellName"]}
    subtexts = {num(r["ID"]): r.get("NameSubtext_lang") or "" for r in tables["Spell"]}
    profs = professions(tables["SkillLine"], abilities, trained)
    steps = ranks(profs, abilities, effects, subtexts)
    rank_spells = {r["spell"]: p for p, rs in steps.items() for r in rs}
    found = recipes(profs, abilities, effects, names, tables, rank_spells)
    taught = {**{sid: r["prof"] for sid, r in found.items()}, **rank_spells}
    teaching = recipe_items(tables["ItemXItemEffect"], tables["ItemEffect"], effects, set(found))
    for item, sid in sorted(teaching.items()):
        found[sid].setdefault("items", []).append(item)
    by_prof, camp = groups(profs, tables["TradeSkillCategory"])

    used_tools = {c for r in found.values() for c in r.get("tools", ())}
    tool_list = tools(tables["TotemCategory"], tables["ItemSparse"], used_tools)
    poles = fishing_poles(tables.get("Item") or ())
    wanted = (set(teaching) | {i for r in found.values() for i, _ in r.get("reagents", ())}
              | {i for t in tool_list.values() for i in t["items"]} | {i for r in found.values() for i in r.get("totems", ())}
              | poles)
    made = {}
    for sid, r in found.items():
        if r.get("makes"):
            made.setdefault(r["makes"][0], []).append(sid)
    items = item_facts(tables["ItemSparse"], wanted | set(made), tables.get("Item") or ())
    for i, sid in teaching.items():
        items.setdefault(i, {"n": ""})["teaches"] = sid
    for i, sids in made.items():
        items.setdefault(i, {"n": ""})["made"] = sorted(sids)
    camp_part = camping(camp, found)
    words = {num(r["ID"]): (r.get("Description_lang") or "", r.get("AuraDescription_lang") or "") for r in tables["Spell"]}
    lasts = durations(tables["SpellMisc"], tables["SpellDuration"])
    used = uses({found[sid]["makes"][0] for v in camp_part.values() for sid in v["recipes"] if found[sid].get("makes")},
                tables["ItemXItemEffect"], tables["ItemEffect"], words, lasts)
    for i, u in used.items():
        items[i]["use"] = u
    return {"effects": effects, "names": names, "profs": profs, "steps": steps, "rank_spells": rank_spells, "found": found,
            "taught": taught, "teaching": teaching, "by_prof": by_prof, "camp": camp, "tools": tool_list, "poles": poles,
            "wanted": wanted, "items": items, "camping": camp_part, "words": words, "lasts": lasts, "used": used}


def build(tables, fill, build_id=None):
    c = client_part(tables, fill.get("trained") or ())
    found, items, profs = c["found"], c["items"], c["profs"]
    for sid, word in (fill.get("recipes") or {}).items():
        if num(sid) in found:
            found[num(sid)].update(word)
    for i, word in (fill.get("items") or {}).items():
        items.setdefault(num(i), {"n": ""}).update(word)
    for i in sorted(c["wanted"]):
        items.setdefault(i, {"n": ""})

    ways = fill.get("ways") or {}
    for sid, r in found.items():
        if "listed" in ways.get(str(sid), ()) and "trainer" not in r["learnt"]:
            r["learnt"].append("trainer")
    placed = {num(i) for i, word in (fill.get("items") or {}).items() if any(word.values())}
    sourced = {i for i, e in items.items() if e.get("made") or i in placed}
    for sid, r in found.items():
        told = "told" in ways.get(str(sid), ()) and ["trainer"]
        bought = r.get("items") and any(i in sourced for i in r["items"]) and ["item"]
        if "skill" not in r["learnt"]:
            r["learnt"] = sorted(set(r["learnt"]) | set(told or ()) | set(bought or ()))
    rank_taught = fill.get("rankTaught") or {}
    rows_of = {p: [rank_taught[str(sid)] for sid, q in c["rank_spells"].items() if q == p and str(sid) in rank_taught]
               for p in profs}
    theirs = fill.get("unknown") or {}

    def part(key, ids):
        what = (theirs.get(key) or {}).get("what")
        return {**({"what": what} if what else {}), "ids": ids, "fill": FILL[key]}
    unknown = {"recipes": part("recipes", sorted(sid for sid, r in found.items() if not r["learnt"])),
               "items": part("items", sorted(i for i in c["wanted"] if i not in sourced)),
               "trainers": theirs.get("trainers") or part("trainers", []),
               "ranks": part("ranks", sorted(p for p in profs if not rows_of[p])),
               "levels": part("levels", sorted(p for p in profs if not any(rows_of[p]))),
               "places": theirs.get("places") or part("places", []),
               "nodes": theirs.get("nodes") or {"fill": FILL["nodes"], "names": {}, "skills": {}}}

    for p, v in profs.items():
        v["ranks"] = c["steps"].get(p, [])
        v["groups"] = keyed(c["by_prof"].get(p, {}))
        v["recipes"] = sorted(sid for sid, r in found.items() if r["prof"] == p)
    stations = {num(r["ID"]): r.get("Name_lang") or "" for r in tables["SpellFocusObject"]}
    currencies = {num(i) for i in fill.get("currencies") or ()}
    return {
        "build": build_id, "built": datetime.date.today().isoformat(),
        **({"sources": fill["sources"]} if "sources" in fill else {}),
        "camping": keyed(c["camping"]),
        "auras": keyed(camp_auras(c["used"], c["effects"], c["words"], c["names"], c["lasts"])),
        "professions": keyed(profs),
        "recipes": keyed(found),
        "trainers": fill.get("trainers") or {},
        "vendors": fill.get("vendors") or {},
        "items": keyed(items),
        "tools": keyed(c["tools"]),
        "stations": keyed({f: stations.get(f, "") for f in {r["station"] for r in found.values() if r.get("station")}}),
        "currencies": keyed({num(r["ID"]): r.get("Name_lang") or "" for r in tables["CurrencyTypes"] if num(r["ID"]) in currencies}),
        "nodes": fill.get("nodes") or {},
        "fishing": fill.get("fishing") or {},
        "poles": sorted(c["poles"]),
        "unknown": unknown,
    }


def counts(data):
    return {key: (key, len(data.get(key) or ())) for key in ("professions", "recipes", "trainers", "vendors", "items")}


def main():
    fill = dropguard.made(FILL_FILE)
    tables = {name: client.rows(name) for name in CLIENT_TABLES}
    data = build(tables, fill, client.installed_version())
    dropguard.save_all([(OUT, data, (), {"counts": counts})], indent=None)
    u = data["unknown"]
    print(f"{len(data['professions'])} professions, {len(data['recipes'])} recipes "
          f"({sum(len(v['recipes']) for v in data['camping'].values())} for camping, "
          f"{sum(1 for e in data['items'].values() if 'use' in e)} camping items' uses, {len(data['auras'])} camp auras), "
          f"{sum(len(v['ranks']) for v in data['professions'].values())} ranks, {len(data['items'])} items, "
          f"{len(data['trainers'])} trainers, {len(data['vendors'])} vendors")
    print(f"unknown, for the game to fill: where to learn {len(u['recipes']['ids'])} recipes, where to get "
          f"{len(u['items']['ids'])} items, what {len(u['trainers']['ids'])} trainers teach, what "
          f"{len(u['ranks']['ids'])} professions' ranks ask and at what level for {len(u['levels']['ids'])}, where "
          f"{len(u['places']['ids'])} trainers and vendors stand, the skill of "
          f"{sum(len(v) for v in u['nodes']['names'].values())} nodes and which nodes ask "
          f"{sum(len(v) for v in u['nodes']['skills'].values())} of the client's gathering skills")
    print(f"{os.path.getsize(OUT) // 1024} KB written to {OUT}")


if __name__ == "__main__":
    import builder
    builder.run(main)
