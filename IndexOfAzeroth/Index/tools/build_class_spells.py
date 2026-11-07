# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import client
import dropguard
import gamedata
from game import version_key as game_version
import races


OUT = os.path.join(ROOT, "data", "classspells.json")
FILL = os.path.join(ROOT, "data", "classfill.json")
CLASS_SKILLS = 7
FROM_TRAINER = "0"
NEVER_LEARNT = "3"
SCHOOL_DAMAGE = 2
CREATE_ITEM = 24
MOUNTED = 78
LEARN_SPELL = 36
AT_PET = "5"
WEAPON_SKILLS = 6
SECOND_SPEC = "Activate Secondary Spec"
FIRST_TIME = re.compile(r"Reach Level (\d+) for the first time on an? (.+)$")


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def talent_spells(names, classes_of):
    tabs = {as_int(r["ID"]): as_int(r.get("ClassMask")) for r in client.rows("TalentTab")}
    ranks, by_class = set(), {}

    def note(sid, mask):
        ranks.add(sid)
        for cid in range(1, 12):
            if mask & (1 << (cid - 1)) and names.get(sid):
                by_class.setdefault(str(cid), {}).setdefault(names[sid], []).append(sid)
    for r in client.rows("Talent"):
        for k, v in r.items():
            if k.startswith("SpellRank_") and as_int(v):
                note(as_int(v), tabs.get(as_int(r.get("TabID")), 0))
    for r in client.rows("TraitDefinition"):
        if as_int(r.get("SpellID")):
            note(as_int(r["SpellID"]), classes_of.get(as_int(r["SpellID"]), 0))
    triggered = {as_int(e.get("EffectTriggerSpell")) for e in client.rows("SpellEffect")
                 if as_int(e.get("SpellID")) in ranks and as_int(e.get("EffectTriggerSpell"))}
    return ranks | triggered, by_class


def rank_of(subtext):
    words = (subtext or "").split()
    return as_int(words[1]) if len(words) == 2 and words[0] == "Rank" else 0


def chain(levels, talents):
    by_name = {}
    for lv, v in levels.items():
        for s in v["spells"]:
            by_name.setdefault(s["name"], []).append((rank_of(s["rank"]), int(lv), s))
    for name, entries in by_name.items():
        ranked = {r: s for r, _, s in sorted(entries, key=lambda e: e[1]) if r}
        for r, s in ranked.items():
            if r - 1 in ranked:
                s["prev"] = ranked[r - 1]["id"]
        if name in talents:
            for _, _, s in entries:
                s["needs"] = sorted(set(talents[name]))


def tameable(beasts, zones):
    out = [{"name": b["name"], "lo": b["lo"], "hi": b["hi"], **({"zone": zones[b["area"]]} if zones.get(b["area"]) else {})}
           for b in beasts]
    return sorted(out, key=lambda b: (b["lo"], b["name"]))


def pet_sources(c, effects, pets):
    teaches = {as_int(e.get("SpellID")): as_int(e.get("EffectTriggerSpell")) for e in effects
               if as_int(e.get("Effect")) == LEARN_SPELL and str(e.get("ImplicitTarget_0")) == AT_PET}
    mine = [s for v in c["levels"].values() for s in v["spells"] if s["id"] in teaches]
    if not mine:
        return
    for s in mine:
        s["petSpell"] = teaches[s["id"]]
    whose = {pet: sid for sid, pet in teaches.items()}
    sold, prices = set(), {}
    for taught in (pets.get("trainers") or {}).values():
        for sid, (_, cost) in taught.items():
            sid = whose.get(sid, sid)
            sold.add(sid)
            if cost is not None:
                prices.setdefault(sid, Counter())[cost] += 1
    listed, zones = pets.get("taught"), None
    if not sold and not listed:
        for s in mine:
            s["pet"] = "unread"
        return
    for s in mine:
        one_says, other_says = s["id"] in sold, listed is not None and s["id"] in listed
        if one_says or other_says:
            s["pet"] = "trainer"
            if s["id"] in prices:
                s["petCost"] = prices[s["id"]].most_common(1)[0][0]
            if sold and listed is not None and one_says != other_says:
                s["petDisputed"] = True
            continue
        s["pet"] = "beast"
        beasts = (pets.get("beasts") or (lambda sid: None))(teaches[s["id"]])
        if beasts is not None:
            if zones is None:
                zones = {as_int(r["ID"]): r.get("AreaName_lang") or "" for r in client.rows("AreaTable")}
            s["beasts"] = tameable(beasts, zones)


def talent_steps(classes):
    sources, out = client.rows("TraitCurrencySource"), {}
    most = {as_int(r["ID"]): as_int(r.get("SourcedMax")) for r in client.rows("TraitCurrency")}
    by_name = {name: cid for cid, name in classes.items()}

    def put(cid, level, entry):
        out.setdefault(str(cid), {}).setdefault(str(level), []).append(entry)
    points = {}
    for r in sources:
        if as_int(r.get("PlayerLevel")) and not any(as_int(r.get(k)) for k in ("TraitNodeEntryID", "QuestID", "AchievementID")):
            points.setdefault(as_int(r.get("TraitCurrencyID")), Counter())[as_int(r["PlayerLevel"])] += as_int(r.get("Amount"))
    spent = {}
    for r in client.rows("TraitCond"):
        if as_int(r.get("SpentAmountRequired")) > 0:
            spent.setdefault(as_int(r.get("TraitCurrencyID")), set()).add(as_int(r["SpentAmountRequired"]))
    for currency, got in points.items():
        first, last, total, had = min(got), max(got), sum(got.values()), 0
        opens = {}
        for level in sorted(got):
            had += got[level]
            for need in spent.get(currency, ()):
                if need <= had and need > got[first]:
                    opens.setdefault(need, level)
        for cid in classes:
            put(cid, first, {"kind": "talent", "name": "Talent points", "text": f"{got[first]} at level {first}, {total} by level {last}"})
            for need, level in sorted(opens.items()):
                put(cid, level, {"kind": "talent", "name": f"Talents for {need} points spent", "spent": need})
    seen = set()
    for r in sources:
        said = FIRST_TIME.match(r.get("Requirement_lang") or "")
        cid = said and by_name.get(said.group(2).strip())
        if cid and (cid, said.group(1)) not in seen:
            seen.add((cid, said.group(1)))
            put(cid, as_int(said.group(1)), {"kind": "milestone", "name": "Milestone talent point", "text": r["Requirement_lang"],
                                             **({"of": most[as_int(r.get("TraitCurrencyID"))]} if most.get(as_int(r.get("TraitCurrencyID"))) else {})})
    return out


def trainer_skills(skills, classes, prices):
    lines = {as_int(r["ID"]): as_int(r.get("CategoryID")) for r in client.rows("SkillLine")}
    of, masks = {}, {}
    for r in client.rows("SkillLineAbility"):
        of.setdefault(as_int(r.get("Spell")), lines.get(as_int(r.get("SkillLine"))))
        masks[as_int(r.get("Spell"))] = masks.get(as_int(r.get("Spell")), 0) | as_int(r.get("ClassMask"))
    names = {as_int(r["ID"]): r.get("Name_lang") or "" for r in client.rows("SpellName")}
    icons = {as_int(r["SpellID"]): as_int(r.get("SpellIconFileDataID")) for r in client.rows("SpellMisc") if as_int(r.get("DifficultyID")) == 0}
    found = {}
    for riding, sid, level, cost in skills:
        what = "riding" if riding else "weapon" if of.get(sid) == WEAPON_SKILLS else None
        if what and names.get(sid):
            found.setdefault((what, sid, level), Counter())[cost] += 1
    out = {}
    for (what, sid, level), costs in sorted(found.items(), key=lambda kv: (kv[0][2], kv[0][1])):
        entry = {"kind": what, "id": sid, "name": names[sid], "icon": icons.get(sid, 0), "classic": True,
                 **({"cost": prices[sid], "forever": True} if sid in prices else {"cost": costs.most_common(1)[0][0]})}
        for cid in classes:
            if not masks.get(sid) or masks[sid] & (1 << (as_int(cid) - 1)):
                out.setdefault(str(cid), {}).setdefault(str(level), []).append(entry)
    return out


def level_gated(classes, skills=None, prices=None, ranks=None):
    out = talent_steps(classes)
    for cid, levels in (trainer_skills(skills, classes, prices or {}) if skills else {}).items():
        for lv, entries in levels.items():
            out.setdefault(cid, {}).setdefault(lv, []).extend(entries)
    names = {r.get("Name_lang"): as_int(r["ID"]) for r in client.rows("SpellName")}
    icons = {as_int(r["SpellID"]): as_int(r.get("SpellIconFileDataID")) for r in client.rows("SpellMisc") if as_int(r.get("DifficultyID")) == 0}
    dual = names.get(SECOND_SPEC)
    unknown = {str(cid): [{"kind": "spec", "id": dual, "name": "Dual specialization", "icon": icons.get(dual, 0),
                           "text": f"The game has it ({SECOND_SPEC})"}] for cid in classes} if dual else {}
    return {"classes": {cid: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for cid, v in sorted(out.items(), key=lambda kv: int(kv[0]))},
            "unknown": unknown, "professions": ranks or {}}


TIERS = ("core", "useful", "minor")
KINDS = ("class", "spec")
TAB_GAP = 1200
STRAY_Y = 10000
FIRST_TALENT = 10


EDGE_NEEDS = {2, 3}


def talent_trees():
    names = {as_int(r["ID"]): r.get("Name_lang") or "" for r in client.rows("SpellName")}
    defs = {as_int(r["ID"]): r for r in client.rows("TraitDefinition")}
    entries = {as_int(r["ID"]): r for r in client.rows("TraitNodeEntry")}
    icons = {as_int(r["SpellID"]): as_int(r.get("SpellIconFileDataID")) for r in client.rows("SpellMisc") if as_int(r.get("DifficultyID")) == 0}
    node_entries, node_groups, group_nodes, group_cond = {}, {}, {}, {}
    for r in client.rows("TraitNodeXTraitNodeEntry"):
        node_entries.setdefault(as_int(r["TraitNodeID"]), []).append(as_int(r["TraitNodeEntryID"]))
    for r in client.rows("TraitNodeGroupXTraitNode"):
        node_groups.setdefault(as_int(r["TraitNodeID"]), []).append(as_int(r["TraitNodeGroupID"]))
        group_nodes.setdefault(as_int(r["TraitNodeGroupID"]), []).append(as_int(r["TraitNodeID"]))
    conds = {as_int(r["ID"]): r for r in client.rows("TraitCond")}
    for r in client.rows("TraitNodeGroupXTraitCond"):
        c = conds.get(as_int(r["TraitCondID"]))
        if c and as_int(c.get("TraitCurrencyID")):
            g = as_int(r["TraitNodeGroupID"])
            if as_int(c.get("SpentAmountRequired")) >= group_cond.get(g, (0, 0))[0]:
                group_cond[g] = (as_int(c.get("SpentAmountRequired")), as_int(c.get("TraitNodeGroupID")))
    needs = {}
    for r in client.rows("TraitEdge"):
        if as_int(r.get("Type")) in EDGE_NEEDS:
            needs.setdefault(as_int(r["RightTraitNodeID"]), []).append(as_int(r["LeftTraitNodeID"]))
    mask_of = {}
    for r in client.rows("SkillLineAbility"):
        sid = as_int(r.get("Spell"))
        mask_of[sid] = mask_of.get(sid, 0) | as_int(r.get("ClassMask"))
    tabs = {}
    for r in client.rows("TalentTab"):
        tabs.setdefault(as_int(r.get("ClassMask")), []).append((as_int(r.get("OrderIndex")), r.get("Name_lang") or ""))
    windows = {as_int(r.get("TraitTreeID")) for r in client.rows("SkillLineXTraitTree")}
    trees = {}
    for r in client.rows("TraitNode"):
        if as_int(r.get("PosY")) < STRAY_Y and as_int(r["TraitTreeID"]) in windows:
            trees.setdefault(as_int(r["TraitTreeID"]), []).append(r)
    out = {}
    for nodes in trees.values():
        spells = {}
        for n in nodes:
            for e in node_entries.get(as_int(n["ID"]), ()):
                entry = entries.get(e)
                d = defs.get(as_int(entry["TraitDefinitionID"])) if entry else None
                sid = as_int(d.get("SpellID")) if d else 0
                if sid and names.get(sid):
                    spells[as_int(n["ID"])] = (sid, as_int(entry.get("MaxRanks")), as_int(d.get("OverrideIcon")) or icons.get(sid, 0))
                    break
        masks = Counter(mask_of.get(sid, 0) for sid, _, _ in spells.values() if mask_of.get(sid))
        mask = masks.most_common(1)[0][0] if masks else 0
        named = [name for _, name in sorted(tabs.get(mask, ()))]
        if not mask or not named or mask & (mask - 1):
            continue
        bands, band, last = [[] for _ in named], 0, None
        for n in sorted(nodes, key=lambda n: as_int(n.get("PosX"))):
            x = as_int(n.get("PosX"))
            if last is not None and x - last > TAB_GAP:
                band += 1
            last = x
            if as_int(n["ID"]) in spells and band < len(named):
                bands[band].append(n)
        own, top = [], min((as_int(n.get("PosY")) for b in bands for n in b), default=0)
        step = grid_step([as_int(n.get("PosY")) for b in bands for n in b])
        for name, band in zip(named, bands):
            left = min((as_int(n.get("PosX")) for n in band), default=0)
            talents = []
            for n in sorted(band, key=lambda n: (as_int(n.get("PosY")), as_int(n.get("PosX")))):
                nid = as_int(n["ID"])
                sid, ranks, icon = spells[nid]
                spent, counted = max((group_cond.get(g, (0, 0)) for g in node_groups.get(nid, ())), default=(0, 0))
                talents.append({"node": nid, "id": sid, "name": names[sid], "icon": icon, "ranks": ranks,
                                "row": line_index(as_int(n.get("PosY")), top, step), "col": line_index(as_int(n.get("PosX")), left, step),
                                "spent": spent, "counts": sorted(group_nodes.get(counted, ())) if spent else [],
                                "needs": sorted(set(needs.get(nid, ())))})
            own.append({"name": name, "talents": sorted(talents, key=lambda t: (t["row"], t["col"]))})
        out[str(mask.bit_length())] = own
    return out


SNAP = 100


def lines_of(values):
    out = []
    for v in sorted(set(values)):
        if not out or v - out[-1] >= SNAP:
            out.append(v)
    return out


def grid_step(values):
    starts = lines_of(values)
    return min((b - a for a, b in zip(starts, starts[1:])), default=1) or 1


def line_index(v, first, step):
    return round((v - first) / step)


def forever_talents(trees=None):
    trees = talent_trees() if trees is None else trees
    return {cid: {t["id"]: {"name": t["name"], "tree": tree["name"], "level": FIRST_TALENT + t["spent"], "ranks": t["ranks"]}
                  for tree in own for t in tree["talents"]} for cid, own in trees.items()}


def rated(entry):
    value, kind = entry.get("value"), entry.get("kind")
    return {"value": value, **({"kind": kind} if kind else {}), "why": entry.get("why"),
            **({"source": entry["source"]} if entry.get("source") else {})}


def values(data, classes, talents=None):
    talents = talents or {}
    for c in data["classes"].values():
        c["talents"] = []
    by_name = {c["name"]: cid for cid, c in data["classes"].items()}
    unmatched = []
    for cname, rows in (classes or {}).items():
        cid = by_name.get(cname)
        c = data["classes"].get(cid) if cid else None
        if not c:
            unmatched.append(f"{cname}: no such class")
            continue
        spells = [s for v in c["levels"].values() for s in v["spells"] if s.get("trainer") is not False]
        for s in spells:
            for k in ("value", "kind", "why", "source", "specs", "rule"):
                s.pop(k, None)
        at ={(s["name"], rank_of(s["rank"]) or 1): s for s in spells}
        named = set()
        for e in rows.get("spells") or ():
            s = at.get((e.get("name"), e.get("rank") or 1))
            if not s:
                unmatched.append(f"{cname}: {e.get('name')} rank {e.get('rank') or 1}")
                continue
            named.add(e["name"])
            if e.get("spec"):
                s.setdefault("specs", {})[e["spec"]] = rated(e)
            else:
                s.update(rated(e))
        for s in spells:
            if s["name"] in named and (rank_of(s["rank"]) or 1) > 1 and "value" not in s and "specs" not in s:
                s.update({"value": "minor", "rule": "rank"})
        own = talents.get(cid) or {}
        rated_talents = []
        for e in rows.get("talents") or ():
            sid = e.get("id") if e.get("id") in own else next((i for i, t in own.items() if t["name"] == e.get("name")), None)
            t = own.get(sid)
            if not t:
                unmatched.append(f"{cname}: talent {e.get('name')}")
                continue
            rated_talents.append({"id": sid, "name": e.get("short") or t["name"], "talent": t["name"], "tree": t["tree"],
                                  "level": t["level"], **({"spec": e["spec"]} if e.get("spec") else {}), **rated(e)})
        c["talents"] = sorted(rated_talents, key=lambda t: (t["level"], t["tree"], t["name"]))
    return unmatched


def build(costs=None, taught=None, game=None, listed=None, pets=None, gated=None, partial=None, lists=None):
    costs, taught_by, listed = costs or {}, taught or {}, listed or {}
    installed = client.installed_version()
    lists_build, known = lists or (installed, None)

    def newer(sid):
        return known is not None and sid not in known

    def price(s, cost, build):
        had = s.get("guess") or installed if s.get("cost") is not None else None
        if had is not None and game_version(build) < game_version(had):
            return
        s["cost"] = cost
        if build == installed:
            s.pop("guess", None)
        else:
            s["guess"] = build
    classes = {as_int(r["ID"]): r.get("Name_lang") or r.get("Name_male_lang") for r in client.rows("ChrClasses")}
    every_line = {as_int(r["ID"]): r.get("DisplayName_lang") or "" for r in client.rows("SkillLine")}
    lines = {as_int(r["ID"]): r.get("DisplayName_lang") for r in client.rows("SkillLine") if as_int(r.get("CategoryID")) == CLASS_SKILLS}
    names = {as_int(r["ID"]): r.get("Name_lang") or "" for r in client.rows("SpellName")}
    subtext = {as_int(r["ID"]): r.get("NameSubtext_lang") or "" for r in client.rows("Spell")}
    levels = {}
    for r in client.rows("SpellLevels"):
        if as_int(r.get("DifficultyID")) == 0:
            levels[as_int(r["SpellID"])] = as_int(r.get("SpellLevel"))
    icons = {}
    for r in client.rows("SpellMisc"):
        if as_int(r.get("DifficultyID")) == 0:
            icons[as_int(r["SpellID"])] = as_int(r.get("SpellIconFileDataID"))
    classes_of, line_mask, lines_of, never, learnt = {}, {}, {}, set(), set()
    for r in client.rows("SkillLineAbility"):
        sid, line, mask = as_int(r.get("Spell")), as_int(r.get("SkillLine")), as_int(r.get("ClassMask"))
        classes_of[sid] = classes_of.get(sid, 0) | mask
        line_mask[line] = line_mask.get(line, 0) | mask
        lines_of.setdefault(sid, set()).add(line)
        (never if str(r.get("AcquireMethod")) == NEVER_LEARNT else learnt).add(sid)
    never -= learnt
    for sid in [s for s, mask in classes_of.items() if not mask]:
        for line in lines_of[sid]:
            classes_of[sid] |= line_mask.get(line, 0)
    talents, talent_names = talent_spells(names, classes_of)
    sold = {sid for taught in taught_by.values() for sid, (_, cost) in taught.items() if cost is not None}
    sold |= {sid for rows in listed.values() for sid, sells in rows.items() if sells}
    talents -= sold
    talent_names = {cid: {name: [i for i in ids if i not in sold] for name, ids in by_name.items() if set(ids) - sold}
                    for cid, by_name in talent_names.items()}
    effects = client.rows("SpellEffect")
    hits = {as_int(e.get("SpellID")) for e in effects if as_int(e.get("Effect")) == SCHOOL_DAMAGE}
    makes = {as_int(e.get("SpellID")) for e in effects if as_int(e.get("Effect")) == CREATE_ITEM}
    mounts = {as_int(e.get("SpellID")) for e in effects if as_int(e.get("EffectAura")) == MOUNTED}
    every = races.every_mask(client.rows("ChrRaces"))

    def race_mask(r):
        mask = races.spell_mask(r.get("RaceMasks_0"), r.get("RaceMasks_1"))
        return 0 if races.every_race(mask, every) else mask
    out, line_of, race_of, any_line = {}, {}, {}, {}
    for r in client.rows("SkillLineAbility"):
        sid, line = as_int(r.get("Spell")), as_int(r.get("SkillLine"))
        level = levels.get(sid, 0)
        any_line.setdefault(sid, (every_line.get(line, ""), as_int(r.get("SupercedesSpell"))))
        if line in lines:
            line_of.setdefault(sid, lines[line])
            race_of.setdefault(sid, race_mask(r))
        if line not in lines or str(r.get("AcquireMethod")) != FROM_TRAINER or level < 2 or sid in talents or not names.get(sid):
            continue
        mask = as_int(r.get("ClassMask")) or sum(1 << (cid - 1) for cid in classes if line_mask.get(line, 0) & (1 << (cid - 1))
                                                 and names[sid] in talent_names.get(str(cid), {}))
        for cid in classes:
            if not mask & (1 << (cid - 1)):
                continue
            c = out.setdefault(str(cid), {"name": classes[cid], "levels": {}})
            spells = c["levels"].setdefault(str(level), {"spells": []})["spells"]
            if any(s["id"] == sid for s in spells):
                continue
            own = race_mask(r)
            spells.append({"id": sid, "name": names[sid], "rank": subtext.get(sid, ""), "icon": icons.get(sid, 0),
                           "line": lines[line], "prev": as_int(r.get("SupercedesSpell")),
                           **({"races": own} if own else {}), **({"dmg": True} if sid in hits else {})})
    for cid, taught in taught_by.items():
        c = out.get(cid)
        if not c or not taught:
            continue
        have = {s["id"]: s for v in c["levels"].values() for s in v["spells"]}
        for sid, s in have.items():
            if sid not in taught:
                if not newer(sid):
                    s["trainer"] = False
            elif taught[sid][1] is not None:
                price(s, taught[sid][1], lists_build)
        for sid, (level, cost) in sorted(taught.items()):
            if sid in have or sid in talents or sid in never or not names.get(sid) or sid not in lines_of:
                continue
            if cost is None and (sid in makes or level < 2):
                continue
            own = race_of.get(sid, 0)
            s = {"id": sid, "name": names[sid], "rank": subtext.get(sid, ""), "icon": icons.get(sid, 0),
                 "line": line_of.get(sid) or any_line.get(sid, ("", 0))[0], "prev": 0,
                 **({"races": own} if own else {}), **({"dmg": True} if sid in hits else {})}
            if cost is not None:
                price(s, cost, lists_build)
            c["levels"].setdefault(str(max(level, 1)), {"spells": []})["spells"].append(s)
    for cid, seen in ((game or {}).get("levels") or {}).items():
        c = out.get(str(cid))
        if not c:
            continue
        prices = ((game or {}).get("classes") or {}).get(str(cid)) or {}
        builds = ((game or {}).get("builds") or {}).get(str(cid)) or {}
        have = {s["id"]: s for v in c["levels"].values() for s in v["spells"]}
        for sid, level in sorted((as_int(s), as_int(lv)) for s, lv in seen.items()):
            on = builds.get(str(sid)) or installed
            if sid in have:
                if game_version(on) >= game_version(lists_build):
                    have[sid].pop("trainer", None)
                if str(sid) in prices:
                    price(have[sid], prices[str(sid)], on)
                continue
            if sid in talents or not names.get(sid) or (sid not in lines_of and on != installed):
                continue
            line, prev = any_line.get(sid, ("", 0))
            s = {"id": sid, "name": names[sid], "rank": subtext.get(sid, ""), "icon": icons.get(sid, 0),
                 "line": line_of.get(sid) or line, "prev": prev, "game": True, **({"dmg": True} if sid in hits else {})}
            if str(sid) in prices:
                price(s, prices[str(sid)], on)
            c["levels"].setdefault(str(max(level, 1)), {"spells": []})["spells"].append(s)
    for cid, rows in listed.items():
        c = out.get(cid)
        if not c or not rows:
            continue
        for lv in list(c["levels"]):
            kept = [s for s in c["levels"][lv]["spells"] if s["id"] in rows or s.get("trainer") is not False or s["id"] in mounts]
            if kept:
                c["levels"][lv]["spells"] = kept
            else:
                del c["levels"][lv]
    for c in out.values():
        pet_sources(c, effects, pets or {})

    def level_cost(cid, lv, spells):
        own = [s for s in spells if s.get("trainer") is not False and not s.get("races") and not s.get("needs")]
        share = (costs.get(cid) or {}).get(lv, 0) / (sum(1 for s in spells if not s.get("races") and not s.get("needs")) or 1)
        if not own:
            return (costs.get(cid) or {}).get(lv, 0)
        return round(sum(s["cost"] if s.get("cost") is not None else share for s in own))
    for cid, c in out.items():
        chain(c["levels"], talent_names.get(cid, {}))
        c["levels"] = {lv: {**v, "cost": level_cost(cid, lv, v["spells"]),
                            "spells": sorted(v["spells"], key=lambda s: (s["line"], s["name"], s["rank"]))}
                       for lv, v in sorted(c["levels"].items(), key=lambda kv: int(kv[0]))}
    return {"build": client.installed_version() if hasattr(client, "installed_version") else None,
            "classes": dict(sorted(out.items(), key=lambda kv: int(kv[0]))), "trainers": partial or {},
            "gated": level_gated({cid: c["name"] for cid, c in out.items()}, **(gated or {}))}


def read_fill(fill):
    def ids(d, value=lambda v: v):
        return {as_int(k): value(v) for k, v in (d or {}).items()}
    return {**fill,
            "trainers": {cid: ids(taught, tuple) for cid, taught in (fill.get("trainers") or {}).items()},
            "listed": {cid: ids(rows) for cid, rows in (fill.get("listed") or {}).items()},
            "petTrainers": ids(fill.get("petTrainers"), lambda t: ids(t, tuple)),
            "petTaught": set(fill["petTaught"]) if fill.get("petTaught") is not None else None,
            "beasts": ids(fill.get("beasts")), "riding": ids(fill.get("riding"))}


def from_fill(costs, fill, game, beasts=None):
    pets = {"trainers": fill.get("petTrainers"), "taught": fill.get("petTaught"),
            "beasts": beasts or (fill.get("beasts") or {}).get}
    lists = (fill["build"], {as_int(s) for s in fill.get("lineSpells") or ()}) if fill.get("build") else None
    return build(costs, fill.get("trainers"), gamedata.class_sightings(fill.get("seen"), game), fill.get("listed"), pets,
                 {"skills": fill.get("skills"), "prices": fill.get("riding"), "ranks": fill.get("ranks")}, fill.get("partial"),
                 lists)


def class_line_spells(build):
    lines = {as_int(r["ID"]) for r in client.rows("SkillLine", build) if as_int(r.get("CategoryID")) == CLASS_SKILLS}
    named = {as_int(r["ID"]) for r in client.rows("SpellName", build) if r.get("Name_lang")}
    return {as_int(r.get("Spell")) for r in client.rows("SkillLineAbility", build)
            if as_int(r.get("SkillLine")) in lines and as_int(r.get("Spell")) in named}


def counts(data):
    return {f"class {cid}": (f"{c.get('name')} spells",
                             sum(len(v.get("spells") or ()) for v in (c.get("levels") or {}).values()))
            for cid, c in (data.get("classes") or {}).items()}


def write(data):
    dropguard.save_all([(OUT, data, ("trainers",), {"counts": counts})], indent=None)


def main():
    world, fill = dropguard.made(os.path.join(ROOT, "data", "world.json")), read_fill(dropguard.made(FILL))
    data = from_fill(world.get("trainerCosts"), fill, gamedata.load_trainer_prices())
    trees = talent_trees()
    say_values(values(data, fill.get("values"), forever_talents(trees)), data)
    put_trees(data, trees)
    write(data)
    import build_addon_chores
    build_addon_chores.write_from_data()
    print(f"{len(data['trainers'])} trainers teach only part of their class's spells")
    for cid, c in data["classes"].items():
        spells = [s for v in c["levels"].values() for s in v["spells"]]
        priced = sum(1 for s in spells if s.get("cost") is not None)
        off = sum(1 for s in spells if s.get("trainer") is False)
        print(f"{c['name']:8} {len(spells):4} spells over {len(c['levels'])} levels, {priced} priced by Forever's trainers, "
              f"{off} no trainer's")
    pet_skills = [s for c in data["classes"].values() for v in c["levels"].values() for s in v["spells"] if s.get("pet")]
    if pet_skills:
        print(f"Pet skills: {len(pet_skills)}, {sum(1 for s in pet_skills if s['pet'] == 'trainer')} a pet trainer's, "
              f"{sum(1 for s in pet_skills if s.get('petDisputed'))} the trainers' lists disagree on, "
              f"{sum(1 for s in pet_skills if s['pet'] == 'beast')} from a beast tamed "
              f"({sum(1 for s in pet_skills if s.get('beasts'))} with beasts named)")
    g = data["gated"]
    gated = [e for c in g["classes"].values() for v in c.values() for e in v] + [e for v in g["unknown"].values() for e in v] \
        + [e for p in g["professions"].values() for v in p.values() for e in v]
    kinds = Counter(e["kind"] for e in gated)
    print(f"what else a level opens: {', '.join(f'{n} {k}' for k, n in sorted(kinds.items())) or 'nothing'}, "
          f"{len(g['professions'])} professions' ranks")
    mage = data["classes"].get("8", {}).get("levels", {})
    for lv in ("4", "6", "10"):
        print("mage", lv, [f"{s['name']} {s['rank']}".strip() for s in mage.get(lv, {}).get("spells", [])], mage.get(lv, {}).get("cost"))


def put_trees(data, trees):
    for cid, c in data["classes"].items():
        c.pop("trees", None)
        if trees.get(cid):
            c["trees"] = trees[cid]
    for c in data["classes"].values():
        said = ", ".join(f"{t['name']} {len(t['talents'])}" for t in c.get("trees") or ())
        if said:
            print(f"{c['name']:8} talent trees: {said}")


def say_values(unmatched, data):
    for c in data["classes"].values():
        spells = [s for v in c["levels"].values() for s in v["spells"]]
        tiers = Counter(s["value"] for s in spells if s.get("value"))
        specs = sum(len(s.get("specs") or ()) for s in spells)
        print(f"{c['name']:8} values: {', '.join(f'{tiers[t]} {t}' for t in TIERS)}, {specs} for one spec, "
              f"{sum(1 for s in spells if s.get('rule'))} by the rank rule, {len(c.get('talents') or ())} talents")
    for line in unmatched:
        print(f"not in the data: {line}")


if __name__ == "__main__":
    import builder
    builder.run(main)
