# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import html as htmllib
import math
import os
import sys

import mainstores
import spelltext

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
SHIELD_BLOCK = mainstores.path("shield_block.json")
SHIELD = 14
sys.path[:0] = [] if TOOLS in sys.path else [TOOLS]

TABLES = ("ItemSparse", "Item", "RandPropPoints", "ItemDamageOneHand", "ItemDamageOneHandCaster", "ItemDamageTwoHand",
          "ItemDamageTwoHandCaster", "ItemDamageRanged", "ItemDamageThrown", "ItemDamageWand", "ItemArmorTotal",
          "ItemArmorQuality", "ItemArmorShield", "ArmorLocation", "ItemSubClass", "ItemNameDescription", "ItemLimitCategory",
          "ItemSet", "ItemSetSpell", "ItemEffect", "ItemXItemEffect", "ChrClasses", "ChrRaces", "CharBaseInfo",
          "HolidayNames", "Holidays", "AreaTable", "SkillLine", "Faction", "ManifestInterfaceData", *spelltext.TABLES)

SLOT_WORDS = {1: "Head", 2: "Neck", 3: "Shoulder", 4: "Shirt", 5: "Chest", 6: "Waist", 7: "Legs", 8: "Feet", 9: "Wrist",
              10: "Hands", 11: "Finger", 12: "Trinket", 13: "One-Hand", 14: "Off Hand", 15: "Ranged", 16: "Back",
              17: "Two-Hand", 19: "Tabard", 20: "Chest", 21: "Main Hand", 22: "Off Hand", 23: "Held In Off-hand",
              24: "Ammo", 25: "Thrown", 26: "Ranged", 28: "Relic"}
BINDS = {1: "Binds when picked up", 2: "Binds when equipped", 3: "Binds when used", 4: "Quest Item", 5: "Quest Item"}
SLOT_COLUMN = {1: 0, 4: 0, 5: 0, 7: 0, 17: 0, 20: 0, 3: 1, 6: 1, 8: 1, 10: 1, 12: 1, 2: 2, 9: 2, 11: 2, 14: 2, 16: 2,
               23: 2, 13: 3, 21: 3, 22: 3, 15: 4, 25: 4, 26: 4, 28: 4}
BUDGET_QUALITY = {0: "Good", 1: "Good", 2: "Good", 3: "Superior", 4: "Epic", 5: "Epic", 6: "Epic", 7: "Epic"}
CASTER = {"one": 2 / 3, "two": 0.7436}
CASTER_FLAG, SPELL_FLAG, HEALER_FLAG = 0x100, 0x200, 0x400
ATTRIBUTES = {3: "Agility", 4: "Strength", 5: "Intellect", 6: "Spirit", 7: "Stamina", 50: "Armor", 0: "Mana", 1: "Health"}
ATTRIBUTE_ORDER = [4, 3, 7, 5, 6, 50, 0, 1]
RESIST_ORDER = [(56, "Arcane"), (51, "Fire"), (55, "Nature"), (52, "Frost"), (54, "Shadow"), (53, "Holy")]
SCHOOLS = {84: "Holy", 85: "Fire", 86: "Nature", 87: "Frost", 88: "Shadow", 89: "Arcane"}
GREEN = {43: "Restores +{} mana per 5 sec.", 46: "Restores +{} health per 5 sec.", 39: "+{} Ranged Attack Power",
         47: "+{} Spell Penetration", 48: "+{} Block Value", 124: "+{} to All Resistances"}
EQUIP = {12: "Increased Defense +{}.", 38: "+{} Attack Power.", 83: "+{} Weapon Damage.",
         119: "Your spells pierce {} Fire Resistance.", 120: "Your spells pierce {} Nature Resistance.",
         121: "Your spells pierce {} Frost Resistance.", 122: "Your spells pierce {} Shadow Resistance.",
         123: "Your spells pierce {} Arcane Resistance.",
         125: "+{} Attack Power against Humanoids.", 126: "+{} Attack Power against Elementals.",
         127: "+{} Attack Power against Demons.", 128: "+{} Attack Power against Undead.",
         129: "+{} Attack Power against Dragonkin.", 130: "+{} Attack Power against Giants.",
         131: "+{} Attack Power against Beasts.", 132: "+{} Attack Power against Mechanical units.",
         133: "Increases damage done to Humanoids by magical spells and effects by up to {}.",
         134: "Increases damage done to Elementals by magical spells and effects by up to {}.",
         135: "Increases damage done to Demons by magical spells and effects by up to {}.",
         136: "Increases damage done to Undead by magical spells and effects by up to {}.",
         137: "Increases damage done to Dragonkin by magical spells and effects by up to {}.",
         138: "Increases damage done to Giants by magical spells and effects by up to {}.",
         139: "Increases damage done to Beasts by magical spells and effects by up to {}."}
PERCENT = {31: ("Improves your chance to hit by {}%.", "hit"), 32: ("Improves your chance to get a critical strike by {}%.", "crit"),
           13: ("Increases your chance to Dodge an attack by {}%.", "dodge"),
           14: ("Increases your chance to Parry an attack by {}%.", "parry"),
           15: ("Increases your chance to Block attacks with a shield by {}%.", "block")}
SPELL_POWER, HEALING, SPELL_DAMAGE = 45, 41, 42
TRIGGERS = {0: "Use: ", 1: "Equip: ", 2: "Chance on hit: ", 4: "Use: ", 5: "", 6: ""}
COINS = (("gold", 10000), ("silver", 100), ("copper", 1))
FLAG_CONJURED, FLAG_LOOT, FLAG_REAL_TIME, FLAG_UNIQUE_EQUIPPED = 0x2, 0x4, 0x10000, 0x80000
FLAG_ACCOUNT = 0x8000000
FLAG_REAGENT = 0x80000000
MOUNT = (15, 5)
MOUNTED_AURA = 78
POWER_WORDS = {0: "Mana", 1: "Rage", 2: "Focus", 3: "Energy", 6: "Runic Power"}
CHANNELED = 0x44
NEXT_MELEE = 0x404
NO_FORM_NEEDED = 0x80000
UNLIMITED = 50000
COMBO_POINTS, HEALTH_POWER = 4, -2
RANGED_KINDS = {2, 3, 16, 18, 19}
GLOBAL_COOLDOWN = 2000
REPUTATION = ["Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted"]


def visible(tooltip):
    import re
    t = re.sub(r"<!--.*?-->", "", tooltip or "")
    t = re.sub(r"<br\s*/?>|</tr>|</td>|</th>|</div>|<div[^>]*>|<table[^>]*>", "\n", t)
    t = htmllib.unescape(re.sub(r"<[^>]+>", "", t))
    return [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n") if ln.strip()]


def shield_blocks(path=None):
    import dropguard
    path = path or SHIELD_BLOCK
    held = dropguard.made(path)
    try:
        return {int(k): int(v) for k, v in held["block"].items()}
    except (AttributeError, KeyError, TypeError, ValueError):
        raise SystemExit(f"{os.path.basename(path)} holds no block values by item ID. Another step makes it: nothing "
                         f"written, the step runs again once that one has")


def num(v, default=0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return int(f) if f == int(f) else f


def round_half(v):
    return int(math.floor(abs(v) + 0.5)) * (1 if v >= 0 else -1)


def esc(text):
    return htmllib.escape(text or "", quote=False)


def marked(words):
    return esc(words).replace(spelltext.SUM_OPEN, '<span class="tip-sum">').replace(spelltext.SUM_CLOSE, "</span>")


def money(copper):
    rest = copper
    out = []
    for coin, value in COINS:
        n, rest = rest // value, rest % value
        if n:
            out.append(f'<span class="money{coin}">{n}</span>')
    return " ".join(out)


class Tables:

    def __init__(self, rows, blocks=None):
        self.blocks = shield_blocks() if blocks is None else blocks
        def by_id(table, key="ID"):
            return {int(r[key]): r for r in rows(table)}

        self.sparse = by_id("ItemSparse")
        self.item = by_id("Item")
        self.points = by_id("RandPropPoints")
        self.damage = {n: {int(r["ItemLevel"]): r for r in rows(f"ItemDamage{n}")}
                       for n in ("OneHand", "OneHandCaster", "TwoHand", "TwoHandCaster", "Ranged", "Thrown", "Wand")}
        self.armor_total = {int(r["ItemLevel"]): r for r in rows("ItemArmorTotal")}
        self.armor_quality = by_id("ItemArmorQuality")
        self.armor_shield = {int(r["ItemLevel"]): r for r in rows("ItemArmorShield")}
        self.armor_location = by_id("ArmorLocation")
        self.subclass = {(int(r["ClassID"]), int(r["SubClassID"])): r for r in rows("ItemSubClass")}
        self.name_descriptions = by_id("ItemNameDescription")
        self.limits = by_id("ItemLimitCategory")
        self.sets = by_id("ItemSet")
        self.set_spells = {}
        for r in rows("ItemSetSpell"):
            self.set_spells.setdefault(int(r["ItemSetID"]), []).append((int(r["Threshold"]), int(r["SpellID"])))
        effects = by_id("ItemEffect")
        self.effects = {}
        for r in rows("ItemXItemEffect"):
            e = effects.get(int(r["ItemEffectID"]))
            if e:
                self.effects.setdefault(int(r["ItemID"]), []).append(e)
        for v in self.effects.values():
            v.sort(key=lambda e: (int(e["LegacySlotIndex"]), int(e["ID"])))
        self.classes = {int(r["ID"]): r["Name_lang"] for r in rows("ChrClasses")}
        self.races = by_id("ChrRaces")
        combos = rows("CharBaseInfo")
        made = {int(r["RaceID"]) for r in combos}
        self.playable_races = sorted(r for r in made if r in self.races and int(self.races[r]["Alliance"]) in (0, 1)
                                     and int(self.races[r]["PlayableRaceBit"]) >= 0 and int(self.races[r]["Flags"]) & 0x600000 == 0x600000
                                     and not int(self.races[r]["Flags"]) & 0x80)
        holiday_names = {int(r["ID"]): r["Name_lang"] for r in rows("HolidayNames")}
        self.holidays = {int(r["ID"]): holiday_names.get(int(r["HolidayNameID"]), "") for r in rows("Holidays")}
        self.areas = {int(r["ID"]): r["AreaName_lang"] for r in rows("AreaTable")}
        self.skills = {int(r["ID"]): r["DisplayName_lang"] for r in rows("SkillLine")}
        self.factions = {int(r["ID"]): r["Name_lang"] for r in rows("Faction")}
        self.icons = {}
        for r in rows("ManifestInterfaceData"):
            folder, file = r["FilePath"].lower().replace("/", "\\"), r["FileName"].lower()
            if folder.startswith("interface\\icons\\") and file.endswith(".blp"):
                self.icons[int(r["ID"])] = file[:-4].strip()
        self.spells = spelltext.Spells(rows)
        self.filler = spelltext.Filler(self.spells)


class Builder:

    def __init__(self, tables):
        self.t = tables


    def budget(self, r):
        level, quality, inv = int(r["ItemLevel"]), int(r["OverallQualityID"]), int(r["InventoryType"])
        column, row = SLOT_COLUMN.get(inv, 0), self.t.points.get(level)
        if row is None:
            return None
        return num(row.get(f"{BUDGET_QUALITY.get(quality, 'Good')}_{column}"))

    def stats(self, r):
        out, gaps = {}, []
        budget = self.budget(r)
        flags = int(r["Flags_4"])
        if flags & CASTER_FLAG and int(r["ItemDelay"] or 0):
            row = self.t.points.get(int(r["ItemLevel"]))
            first = num(row.get(f"{BUDGET_QUALITY.get(int(r['OverallQualityID']), 'Good')}_0")) if row else 0
            if flags & HEALER_FLAG:
                out[HEALING] = round_half(first * 3.75)
                out[SPELL_DAMAGE] = math.floor(first * 1.25)
            elif flags & SPELL_FLAG:
                out[SPELL_POWER] = 2 * first
        for k in range(10):
            stat, share = int(r[f"StatModifier_bonusStat_{k}"]), int(r[f"StatPercentEditor_{k}"])
            if stat < 0 or not share:
                continue
            if budget is None:
                gaps.append("stat budget")
                continue
            v = round_half(share * budget / 10000)
            if v:
                out[stat] = out.get(stat, 0) + v
        return out, gaps

    def armor(self, r, cls, sub):
        level, quality, inv = int(r["ItemLevel"]), int(r["OverallQualityID"]), int(r["InventoryType"])
        if cls != 4:
            return None
        if sub == 6:
            row = self.t.armor_shield.get(level)
            return int(num(row[f"Quality_{quality}"])) if row else None
        kind = {1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate"}.get(1 if inv == 16 else sub)
        total, loc, qual = self.t.armor_total.get(level), self.t.armor_location.get(5 if inv == 20 else inv), self.t.armor_quality.get(level)
        if not kind or not total or not loc or not qual:
            return None
        column = {"Cloth": "Clothmodifier", "Leather": "Leathermodifier", "Mail": "Chainmodifier", "Plate": "Platemodifier"}[kind]
        v = num(total[kind]) * num(loc[column]) * num(qual[f"Qualitymod_{quality}"])
        return round_half(v) or None

    def weapon(self, r, cls, sub):
        if cls != 2 or not int(r["ItemDelay"]):
            return None
        level, quality, inv = int(r["ItemLevel"]), int(r["OverallQualityID"]), int(r["InventoryType"])
        hands = "two" if inv == 17 else "one" if inv in (13, 21, 22) else None
        table = {"one": "OneHand", "two": "TwoHand"}.get(hands) or (
            "Wand" if sub == 19 else "Thrown" if inv == 25 else "Ranged" if inv in (15, 26) else None)
        row = self.t.damage.get(table, {}).get(level) if table else None
        if not row:
            return None
        dps = num(row[f"Quality_{quality}"])
        if hands and int(r["Flags_4"]) & CASTER_FLAG:
            dps *= CASTER[hands]
        delay, var, extra = int(r["ItemDelay"]) / 1000, num(r["DmgVariance"]), num(r["QualityModifier"])
        avg = dps * delay
        low = max(1, math.floor(avg * (1 - var / 2) + extra * delay))
        high = max(low, math.floor(avg * (1 + var / 2) + extra * delay + 0.5))
        return low, high, delay, (low + high) / 2 / delay


    def item(self, iid):
        r = self.t.sparse.get(iid)
        if r is None:
            return None
        t = self.t
        base = t.item.get(iid) or {}
        cls, sub = int(base.get("ClassID") or 0), int(base.get("SubclassID") or 0)
        quality, level, inv = int(r["OverallQualityID"]), int(r["ItemLevel"]), int(r["InventoryType"])
        name = r["Display_lang"]
        gaps = []
        head = [f'<table><tr><td><!--nstart--><b class="q{quality}">{esc(name)}</b><!--nend--><!--ndstart-->']
        nd = t.name_descriptions.get(int(r["ItemNameDescriptionID"] or 0))
        if nd and nd["Description_lang"]:
            head.append(f'<br><span class="q2">{esc(nd["Description_lang"])}</span>')
        worn = inv in SLOT_WORDS
        head.append(f'<!--ndend--><span class="q{"" if worn else " whtt-extra whtt-ilvl"}"><br>Item Level <!--ilvl-->{level}</span><!--bo-->')
        zone = t.areas.get(int(r["ZoneBound_0"] or 0))
        if zone:
            head.append(f"<br>{esc(zone)}")
        if int(r["Flags_0"]) & FLAG_CONJURED:
            head.append("<br>Conjured Item")
        bind = "Binds to Account" if int(r["Flags_0"]) & FLAG_ACCOUNT else BINDS.get(int(r["Bonding"]))
        if bind:
            head.append(f"<br>{bind}")
        unique = self.unique(r)
        if unique:
            head.append(f"<br>{unique}")
        head.append("<!--ue--><!--ue-->")
        if (cls, sub) == MOUNT or (cls == 15 and self.mount(iid)):
            head.append('<br />Mount <span class="q0">(Account-wide)</span>')
        if int(r["StartQuestID"] or 0):
            head.append(f'<br><a href="/forever/quest={int(r["StartQuestID"])}" class="q1">This Item Begins a Quest</a>')
        dur = int(r["DurationInInventory"] or 0)
        if dur:
            real = " (real time)" if int(r["Flags_0"]) & FLAG_REAL_TIME else ""
            head.append(f"<br>Duration: {spelltext.duration(dur * 1000)}{real}")
        body = []
        if worn:
            sc = t.subclass.get((cls, sub))
            word = "" if not sc or int(sc["DisplayFlags"]) & 3 or inv == 16 else sc["DisplayName_lang"]
            body.append(f'<table width="100%"><tr><td>{SLOT_WORDS[inv]}</td><th><!--scstart{cls}:{sub}--><span class="q1">'
                        f'{esc(word)}</span><!--scend--></th></tr></table>')
        elif cls in (1, 11) and int(r["ContainerSlots"] or 0):
            sc = t.subclass.get((cls, sub))
            body.append(f'<br />{int(r["ContainerSlots"])} Slot {esc(sc["DisplayName_lang"] if sc else "Bag")}')
        body.append("<!--rf-->")
        lines = []
        armor = self.armor(r, cls, sub) if worn else None
        if armor:
            lines.append(f"<span><!--amr-->{armor} Armor</span>")
        block = t.blocks.get(iid) if inv == SHIELD else None
        if block:
            lines.append(f"{block} Block")
        weapon = self.weapon(r, cls, sub) if worn else None
        if weapon:
            low, high, speed, dps = weapon
            school = {1: "Holy ", 2: "Fire ", 3: "Nature ", 4: "Frost ", 5: "Shadow ", 6: "Arcane "}.get(int(r["DamageType"] or 0), "")
            hit = f"{low} - {high}" if high != low else f"{low}"
            lines.append(f'<table width="100%"><tr>\n    <td><span><!--dmg-->{hit} {school}Damage</span></td>\n'
                         f'    <th>Speed <!--spd-->{speed:.2f}</th>\n</tr></table><!--dps-->({dps:.2f} damage per second)')
        stats, more = self.stats(r)
        gaps += more
        for stat in sorted((s for s in stats if s in ATTRIBUTES), key=ATTRIBUTE_ORDER.index):
            v = stats[stat]
            lines.append(f'<span><!--stat{stat}-->{"+" if v > 0 else "-"}{abs(v):,} {ATTRIBUTES[stat]}</span>')
        green = [f'<span class="q2">{GREEN[s].format(f"<!--rtg{s}-->{v}")}</span>' for s, v in stats.items() if s in GREEN]
        resists = [f"+{stats[s]} {word} Resistance" for s, word in RESIST_ORDER if stats.get(s)]
        joined = "<br>".join(lines)
        body.append(joined)
        body.append("<!--ebstats-->" + ("<br>" if joined and green else "") + "<br>".join(green))
        body.append("<!--egstats--><!--eistats--><!--nameDescStats--><!--rs-->")
        body.append(("<br>" if (joined or green) and resists else "") + "<br>".join(resists) + "<!--e--><!--ps-->")
        allowed = self.classes_line(r)
        if allowed:
            body.append(allowed)
        races = self.races_line(r)
        if races:
            body.append(races)
        head += body
        head.append("</td></tr></table><table><tr><td>")
        need = []
        if int(r["RequiredLevel"] or 0) > 1:
            need.append(f"Requires Level <!--rlvl-->{int(r['RequiredLevel'])}")
        held = t.sets.get(int(r["ItemSet"] or 0)) or {}
        skill_id, rank = int(r["RequiredSkill"] or 0), int(r["RequiredSkillRank"] or 0)
        if not skill_id and int(held.get("RequiredSkill") or 0):
            skill_id, rank = int(held["RequiredSkill"]), int(held["RequiredSkillRank"] or 0)
        if skill_id:
            skill = t.skills.get(skill_id, "")
            need.append(f'Requires <a href="/forever/skill={skill_id}" class="q1">{esc(skill)}</a> ({rank})')
        if int(r["RequiredAbility"] or 0):
            spell = t.spells.name.get(int(r["RequiredAbility"]), "")
            need.append(f'Requires <a href="/forever/spell={int(r["RequiredAbility"])}" class="q1">{esc(spell)}</a>')
        if int(r["MinFactionID"] or 0):
            faction = t.factions.get(int(r["MinFactionID"]), "")
            rep = int(r["MinReputation"] or 0)
            need.append(f'Requires <a href="/forever/faction={int(r["MinFactionID"])}" class="q1">{esc(faction)}</a> - '
                        f'{REPUTATION[rep] if 0 <= rep < len(REPUTATION) else ""}')
        if int(r["RequiredHoliday"] or 0):
            need.append(f"Requires {esc(t.holidays.get(int(r['RequiredHoliday']), ''))}")
        tail = ["<br>".join(need) + ("<br>" if need else "") + "<!--rr-->"]
        equip = self.stat_equip_lines(stats, gaps)
        uses, more, told = self.effect_lines(iid, r, cls, sub)
        gaps += more
        effects = [f'<span class="q2">Equip: {e}</span>' for e in equip] + uses
        tail.append("<br>".join(effects))
        tail.append(f"<!--itemEffects:{1 if effects else 0}-->")
        if int(r["ItemSet"] or 0):
            block, more = self.set_block(int(r["ItemSet"]), iid)
            gaps += more
            tail.append(block)
        extra = []
        if int(r["Flags_1"]) & FLAG_REAGENT:
            extra.append('<span class="toycolor">Crafting Reagent</span>')
        if r["Description_lang"] and not told:
            extra.append(f'<span class="q">&quot;{esc(r["Description_lang"])}&quot;</span>')
        if int(r["Flags_0"]) & FLAG_LOOT and not int(r["LockID"] or 0):
            extra.append('<span class="q2">&lt;Right Click to Open&gt;</span>')
        if int(r["PageID"] or 0):
            extra.append('<span class="q2">&lt;Right Click to Read&gt;</span>')
        if int(r["LockID"] or 0):
            extra.append('<span class="q0">Locked</span>')
        tail += [f"<br>{x}" for x in extra]
        tail.append("<br><!--pvpEquip--><!--pvpEquip-->")
        stack = int(r["Stackable"] or 0)
        if stack > 1:
            tail.append(f'<div class="whtt-extra whtt-maxstack">Max Stack: {stack}</div>')
        sell = int(r["SellPrice"] or 0)
        if sell:
            tail.append(f'<div class="whtt-sellprice">Sell Price: {money(sell)}</div>')
        tail.append("</td></tr></table>")
        icon = t.icons.get(int(base.get("IconFileDataID") or 0))
        return {"name": name, "quality": quality, "icon": icon, "tooltip": "".join(head + tail), "gaps": sorted(set(gaps))}

    def unique(self, r):
        out = []
        n = int(r["MaxCount"] or 0)
        if n == 1:
            out.append("Unique")
        elif n > 1:
            out.append(f"Unique ({n})")
        limit = self.t.limits.get(int(r["LimitCategory"] or 0))
        if limit:
            word = "Unique-Equipped" if int(limit["Flags"]) & 1 else "Unique"
            out.append(f"{word}: {limit['Name_lang']} ({int(limit['Quantity'])})" if limit["Name_lang"] else word)
        elif not out and int(r["Flags_0"]) & FLAG_UNIQUE_EQUIPPED:
            out.append("Unique-Equipped")
        return "<br>".join(out) or None

    def classes_line(self, r):
        mask = int(r["AllowableClass"] or 0)
        every = sorted(self.t.classes)
        allowed = [c for c in every if mask == -1 or mask & (1 << (c - 1))]
        if mask in (0, -1) or not allowed or len(allowed) == len(every):
            return None
        links = ", ".join(f'<a href="/forever/class={c}" class="c{c}">{esc(self.t.classes[c])}</a>' for c in allowed)
        return f'<div class="tip-classes">Classes: {links}</div>'

    def races_line(self, r):
        lo, hi = int(r["AllowableRace_0"] or 0) & 0xFFFFFFFF, int(r["AllowableRace_1"] or 0) & 0xFFFFFFFF
        mask = lo | (hi << 32)
        if mask in (0, 0xFFFFFFFFFFFFFFFF):
            return None
        races = self.t.playable_races
        bit = {r: int(self.t.races[r]["PlayableRaceBit"]) for r in races}
        allowed = [r for r in races if mask & (1 << bit[r])]
        if not allowed or len(allowed) == len(races):
            return None
        sides = {s: [r for r in races if int(self.t.races[r]["Alliance"]) == s] for s in (0, 1)}
        for side, word in ((1, "Horde"), (0, "Alliance")):
            if sorted(allowed) == sorted(sides[side]):
                return f'<div class="tip-races">Requires any {word} race</div>'
        links = ", ".join(f'<a href="/forever/race={x}" class="q1">{esc(self.t.races[x]["Name_lang"])}</a>' for x in allowed)
        return f'<div class="tip-races">Races: {links}</div>'

    def stat_equip_lines(self, stats, gaps):
        out = []
        heal, dmg, power = stats.get(HEALING), stats.get(SPELL_DAMAGE), stats.get(SPELL_POWER)
        order = [s for s in PERCENT if s in stats] + [s for s in stats if s not in PERCENT]
        for stat in order:
            v = stats[stat]
            if stat in ATTRIBUTES or stat in GREEN or any(stat == s for s, _ in RESIST_ORDER):
                continue
            if stat == SPELL_POWER:
                out.append(f"Increases damage and healing done by magical spells and effects by up to <span><!--rtg45-->{power}</span>.")
            elif stat == HEALING:
                if dmg:
                    out.append(f"Increases healing done by up to <span><!--rtg41-->{heal}</span> and damage done by up to "
                               f"<span><!--rtg42-->{dmg}</span> for all magical spells and effects.")
                else:
                    out.append(f"Increases healing done by magical spells and effects by up to <span><!--rtg41-->{heal}</span>.")
            elif stat == SPELL_DAMAGE:
                if not heal:
                    out.append(f"Increases damage done by magical spells and effects by up to <span><!--rtg42-->{dmg}</span>.")
            elif stat in SCHOOLS:
                out.append(f"Increases damage done by {SCHOOLS[stat]} spells and effects by up to <!--rtg{stat}-->{v}.")
            elif stat in EQUIP:
                out.append(EQUIP[stat].replace("{}", f"<!--rtg{stat}-->{v}", 1))
            elif stat in PERCENT:
                import build_gear
                words, key = PERCENT[stat]
                out.append(words.format(f"{v / build_gear.RATING[key]:.1f}"))
            else:
                gaps.append(f"stat {stat}")
        return out

    def cooldown_words(self, ms):
        if ms <= GLOBAL_COOLDOWN:
            return None
        s = ms / 1000
        if s < 60:
            return f"{spelltext.fmt(s)} Sec Cooldown"
        if s < 3600:
            return f"{spelltext.fmt(round(s / 60, 1))} Min Cooldown"
        h = round(s / 3600, 1)
        return f"{spelltext.fmt(h)} Hour Cooldown" if h == 1 else f"{spelltext.fmt(h)} Hours Cooldown"

    def effect_lines(self, iid, r, cls, sub):
        out, gaps, told = [], [], False
        for e in self.t.effects.get(iid, ()):
            trigger, sid = int(e["TriggerType"]), int(e["SpellID"])
            words, more = self.t.filler.fill(sid)
            gaps += [f"spell {c}" for c in more]
            if not words.strip():
                teaches = any(int(x["TriggerType"]) == 6 for x in self.t.effects.get(iid, ()))
                if cls == 15 and trigger == 0 and teaches:
                    told = bool(r["Description_lang"])
                    out.append(f'<span class="q2">Use: {esc(r["Description_lang"])}</span>')
                continue
            words += self.proc_note(sid)
            prefix = TRIGGERS.get(trigger, "Use: ")
            ms = max(int(e["CoolDownMSec"] or 0), int(e["CategoryCoolDownMSec"] or 0))
            if ms <= 0:
                sc = self.t.spells.cooldowns.get(sid)
                ms = int(num(sc["RecoveryTime"])) if sc else 0
            cool = self.cooldown_words(ms)
            line = f'<span class="q2">{prefix}<a href="/forever/spell={sid}" class="q2">{esc(words)}</a>'
            if cool and trigger == 0:
                line += f" ({cool})"
            line += "</span>"
            charges = int(e["Charges"] or 0)
            if trigger == 0 and charges and abs(charges) > 1:
                line += f"<br />{abs(charges)} Charges"
            out.append(line)
        return out, gaps, told

    def mount(self, iid):
        for e in self.t.effects.get(iid, ()):
            for eff in (self.t.spells.effects.get(int(e["SpellID"])) or {}).values():
                if int(eff["EffectAura"]) == MOUNTED_AURA:
                    return True
        return False

    def proc_note(self, sid):
        a = self.t.spells.auras.get(sid)
        if not a:
            return ""
        chance, ms = num(a["ProcChance"]), int(num(a["ProcCategoryRecovery"]))
        parts = [f"Proc chance: {spelltext.fmt(chance)}%"] if 0 < chance < 100 else []
        if ms > 0:
            parts.append(f"{ms}ms cooldown" if ms < 1000 else f"{spelltext.fmt(ms / 1000)}s cooldown" if ms < 60000
                         else f"{spelltext.fmt(round(ms / 60000, 1))}m cooldown")
        return f" ({', '.join(parts)})" if parts else ""


    def spell(self, sid, class_id=None):
        t, sp = self.t, self.t.spells
        name = sp.name.get(sid)
        if name is None:
            return None
        head = [f'<table><tr><td><a class="whtt-name" href="/forever/spell={sid}"><b class="whtt-name">{esc(name)}</b></a>']
        cost, reach = self.spell_cost(sid), self.spell_range(sid)
        if cost and reach:
            head.append(f'<table width="100%"><tr><td>{cost}</td><th>{reach}</th></tr></table>')
        elif cost or reach:
            head.append(f"<br />{cost or reach}")
        cast, cool = self.spell_cast(sid), self.spell_cooldown(sid)
        if cool:
            head.append(f'<table width="100%"><tr><td>{cast or ""}</td><th>{cool}</th></tr></table>')
        elif cast:
            head.append(f"<br />{cast}")
        if class_id and class_id in t.classes:
            head.append(f'<div class="tip-requirements">Requires {esc(t.classes[class_id])}</div>')
        lv = sp.levels.get(sid)
        level = int(lv["SpellLevel"] or lv["BaseLevel"] or 0) if lv else 0
        if level:
            head.append(f'<span class="tip-requirements">Requires level {level}</span><br />')
        head.append("</td></tr></table>")
        sums = []
        words, gaps = t.filler.fill(sid, sums=sums)
        note = self.proc_note(sid)
        body = ["<table><tr><td>"]
        reagents = [f'{esc(t.sparse[i]["Display_lang"])}{f" ({n})" if n > 1 else ""}' for i, n in sp.reagents.get(sid, ())
                    if i in t.sparse]
        if reagents:
            body.append('Reagents:<br />' + "".join(f'<div class="indent q1">{x}</div>' for x in reagents))
        tools = [esc(sp.totems[c]) for c in sp.tools.get(sid, ()) if c in sp.totems]
        if tools:
            body.append('Tools:<br />' + "".join(f'<div class="indent q1">{x}</div>' for x in tools))
        needs = [w for w in (self.spell_weapon(sid), self.spell_forms(sid)) if w]
        body.append("<br />".join(f'<span class="tip-requirements">{w}</span>' for w in needs))
        body.append((f'<div class="q tip-desc">{marked(words)}</div>' if words else "") + note + "</td></tr></table>")
        body = "".join(body)
        misc = sp.misc.get(sid)
        icon = t.icons.get(int(misc["SpellIconFileDataID"])) if misc else None
        tip = {"name": name, "icon": icon, "tooltip": "".join(head) + body, "quality": -1,
               "gaps": sorted({f"spell {g}" for g in gaps})}
        if sums:
            tip["sums"] = sums
        if sp.ranked(sid) and not gaps:
            tip["ranks"] = [self.rank_text(sid, r) for r in range(1, sp.ranks[sid] + 1)]
        return tip

    def rank_text(self, sid, rank):
        sums = []
        words, _ = self.t.filler.fill(sid, rank=rank, sums=sums)
        return {"html": marked(words), "sums": sums}

    def spell_cost(self, sid):
        out, combo = None, ""
        for p in self.t.spells.power.get(sid, ()):
            kind, amount, pct = int(p["PowerType"]), int(num(p["ManaCost"])), num(p["PowerCostPct"])
            if kind == COMBO_POINTS:
                combo = f" / {amount} to {amount + int(num(p['OptionalCost']))} Combo Points"
            elif out is None and pct:
                out = f"{spelltext.fmt(pct)}% of base mana"
            elif out is None and kind == HEALTH_POWER and amount:
                per = int(num(p["ManaPerSecond"]))
                out = f"{amount} Health" + (f", plus {per} per sec" if per else "")
            elif out is None and amount:
                out = f"{amount // 10} Rage" if kind == 1 else f"{amount} {POWER_WORDS.get(kind, 'Mana')}"
        return (out + combo) if out else None

    def spell_range(self, sid):
        misc = self.t.spells.misc.get(sid)
        rng = self.t.spells.ranges.get(int(misc["RangeIndex"])) if misc else None
        if not rng:
            return None
        least, most = num(rng["RangeMin_0"]) or num(rng["RangeMin_1"]), num(rng["RangeMax_0"])
        if int(rng["Flags"]) & 1:
            return "Melee Range"
        if not most:
            return None
        if most >= UNLIMITED:
            return "Unlimited range"
        if least:
            return f"{spelltext.fmt(least)} - {spelltext.fmt(most)} yd range"
        return f"{spelltext.fmt(most)} yd range"

    def spell_cast(self, sid):
        misc = self.t.spells.misc.get(sid)
        if misc and int(misc["Attributes_0"]) & NEXT_MELEE:
            return "Next Melee"
        ms = self.t.spells.casts.get(int(misc["CastingTimeIndex"])) if misc else 0
        if ms and ms < 0:
            return None
        if not ms and misc and int(misc["Attributes_1"]) & CHANNELED:
            whole = self.t.spells.duration_ms(sid)
            return f"Channeled ({spelltext.duration(whole)} cast)" if whole and whole > 0 else "Channeled"
        return f"{spelltext.fmt(ms / 1000)} sec cast" if ms else "Instant"

    def spell_weapon(self, sid):
        e = self.t.spells.equipped.get(sid)
        if not e or int(e["EquippedItemClass"]) != 2:
            return None
        mask = int(e["EquippedItemSubclass"]) & 0xFFFFFFFF
        if not mask:
            return None
        kinds = [k for k in range(21) if mask & (1 << k)]
        if len(kinds) == 1:
            return None
        if all(k in RANGED_KINDS for k in kinds):
            return "Requires Ranged Weapon"
        if all(k not in RANGED_KINDS for k in kinds):
            return "Requires Melee Weapon"
        return None

    def spell_forms(self, sid):
        mask = self.t.spells.forms.get(sid, 0)
        misc = self.t.spells.misc.get(sid)
        if misc and int(misc["Attributes_2"]) & NO_FORM_NEEDED:
            return None
        names =[self.t.spells.form_names[k + 1] for k in range(32) if mask & (1 << k) and k + 1 in self.t.spells.form_names]
        return f"Requires {esc(', '.join(names))}" if names else None

    def spell_cooldown(self, sid):
        c = self.t.spells.cooldowns.get(sid)
        ms = max(int(num(c["RecoveryTime"])), int(num(c["CategoryRecoveryTime"]))) if c else 0
        if ms <= GLOBAL_COOLDOWN:
            return None
        s = ms / 1000
        words = f"{spelltext.fmt(s)} sec" if s < 60 else f"{spelltext.fmt(round(s / 60, 1))} min" if s < 3600 \
            else f"{spelltext.fmt(round(s / 3600, 1))} hour"
        return f"{words} cooldown"

    def set_block(self, set_id, iid):
        s = self.t.sets.get(set_id)
        if not s:
            return "", ["item set"]
        pieces = [int(s[f"ItemID_{k}"]) for k in range(17) if int(s.get(f"ItemID_{k}") or 0)]
        gaps = []
        names = []
        for p in pieces:
            pr = self.t.sparse.get(p)
            if pr is None:
                continue
            names.append(f'<span><!--si{p}--><a href="/forever/item={p}">{esc(pr["Display_lang"])}</a></span>')
        out = [f'<br /><br /><span class="q"><a href="/forever/item-set={set_id}" class="q">{esc(s["Name_lang"])}</a> '
               f'(0/{len(names)})</span><div class="q0 indent">{"<br />".join(names)}</div>']
        bonuses = []
        for threshold, sid in sorted(self.t.set_spells.get(set_id, ())):
            words, more = self.t.filler.fill(sid)
            words += self.proc_note(sid)
            gaps += [f"spell {c}" for c in more]
            bonuses.append(f'<span>({threshold}) Set : <a href="/forever/spell={sid}">{esc(words)}</a></span>')
        if bonuses:
            out.append(f'<br /><span class="q0">{"<br />".join(bonuses)}</span>')
        return "".join(out), gaps
