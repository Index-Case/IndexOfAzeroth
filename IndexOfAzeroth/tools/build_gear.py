# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import concurrent.futures as cf
import html as htmllib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dropguard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUNGEONS = os.path.join(ROOT, "data", "dungeons.json")
OUT = os.path.join(ROOT, "data", "gear.json")
WORN = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 25, 26, 28}
ATTRIBUTES = {"Strength": "str", "Agility": "agi", "Stamina": "sta", "Intellect": "int", "Spirit": "spi"}
SCHOOLS = {"Fire": "fire", "Frost": "frost", "Shadow": "shadow", "Arcane": "arcane", "Nature": "nature", "Holy": "holy"}
RATING = {"hit": 10, "crit": 14, "dodge": 12, "parry": 20, "block": 5}
EQUIP = [
    (r"Increases healing done by up to (\d+) and damage done by up to (\d+) for all magical spells and effects", ("heal", "sp"), 1),
    (r"Increases damage and healing done by magical spells and effects by up to (\d+)", ("sp", "heal"), 1),
    (r"Increases healing done by (?:magical )?spells and effects by up to (\d+)", ("heal",), 1),
    *[(rf"Increases damage done by {school} spells and effects by up to (\d+)", ("sp" + key,), 1) for school, key in SCHOOLS.items()],
    (r"Decreases the magical resistances of your spell targets by (\d+)", ("spellpen",), 1),
    (r"\+(\d+) Spell Penetration", ("spellpen",), 1),
    (r"Your spells pierce (\d+) Magical Resistances", ("spellpen",), 1),
    *[(rf"Your spells pierce (\d+) {school} Resistance", ("pen" + key,), 1) for school, key in SCHOOLS.items() if key != "holy"],
    (r"Improves your chance to hit by (\d+\.\d)%", ("hit", "spellhit"), 1),
    (r"Improves your chance to get a critical strike by (\d+\.\d)%", ("crit", "spellcrit"), 1),
    (r"Improves your chance to hit with spells by (\d+)%", ("spellhit",), 1),
    (r"Improves your chance to get a critical strike with spells by (\d+)%", ("spellcrit",), 1),
    (r"Improves your chance to hit by (\d+)%", ("hit",), 1),
    (r"Improves your chance to get a critical strike by (\d+)%", ("crit",), 1),
    (r"Increases your hit by (\d+)", ("hit", "spellhit"), RATING["hit"]),
    (r"Increases your critical strike by (\d+)", ("crit", "spellcrit"), RATING["crit"]),
    (r"Increased Defense \+(\d+)", ("def",), 1),
    (r"Increases defense skill by (\d+)", ("def",), 1),
    (r"Increases your chance to [Dd]odge an attack by (\d+(?:\.\d)?)%", ("dodge",), 1),
    (r"Increases your dodge by (\d+)", ("dodge",), RATING["dodge"]),
    (r"Increases your chance to [Pp]arry an attack by (\d+(?:\.\d)?)%", ("parry",), 1),
    (r"Increases your parry by (\d+)", ("parry",), RATING["parry"]),
    (r"Increases your chance to [Bb]lock attacks with a shield by (\d+(?:\.\d)?)%", ("block",), 1),
    (r"Increases your shield block by (\d+)", ("block",), RATING["block"]),
    (r"Increases the block value of your shield by (\d+)", ("blockvalue",), 1),
    (r"\+(\d+) Block Value", ("blockvalue",), 1),
    (r"\b(\d+) Block\b", ("blockvalue",), 1),
    (r"\+(\d+) Attack Power in Cat, Bear, and Dire Bear forms only", ("fap",), 1),
    (r"\+(\d+) Feral Attack Power", ("fap",), 1),
    (r"\+(\d+) Attack Power when fighting [A-Za-z]+", (), 1),
    (r"\+(\d+) [Rr]anged Attack Power", ("rap",), 1),
    (r"\+(\d+) Attack Power", ("ap",), 1),
    (r"Restores \+?(\d+) mana per 5 sec", ("mp5",), 1),
    (r"Restores \+?(\d+) health per 5 sec", ("hp5",), 1),
    (r"\+(\d+) All Resistances", ("resist",), 1),
    *[(rf"\+(\d+) {school} Resistance", ("res" + key,), 1) for school, key in SCHOOLS.items() if key != "holy"],
    (r"\+(\d+) (?:Bonus )?Armor\b", ("armor",), 1),
]
RANGED = {15, 25, 26}


def text_of(tooltip):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", tooltip or ""))))


def stats(tooltip, inv):
    t, st = re.split(r"\(\d+/\d+\)", text_of(tooltip))[0], {}
    for word, key in ATTRIBUTES.items():
        for m in re.finditer(r"([+-])(\d+) " + word + r"\b", t):
            st[key] = st.get(key, 0) + int(m[2]) * (1 if m[1] == "+" else -1)
    m = re.search(r"(?<![+\d])(\d+) Armor\b", t)
    if m:
        st["armor"] = int(m[1])
    m = re.search(r"\(([\d.]+) damage per second\)", t)
    if m:
        st["wdps" if re.search(r"\bRanged Wand\b", t) else "rdps" if inv in RANGED else "dps"] = float(m[1])
    for pattern, keys, per in EQUIP:
        for m in re.finditer(pattern, t):
            numbers = [float(g) if "." in g else int(g) for g in m.groups()]
            for i, key in enumerate(keys):
                value = numbers[i if len(numbers) == len(keys) else 0]
                st[key] = round(st.get(key, 0) + value / per, 2) if per != 1 or isinstance(value, float) else st.get(key, 0) + value
            t = t.replace(m[0], "")
    return st


def tooltip(iid):
    import itemtips
    t = itemtips.item_tip(int(iid))
    return t if t and t.get("tooltip") else None


def counts(data):
    return {"stats": ("pieces with stats read", sum(1 for it in (data.get("items") or {}).values() if it.get("st")))}


def main():
    data = dropguard.made(DUNGEONS)
    items = data["items"]
    sources = {}
    for d in data["dungeons"]:
        for b in d.get("bosses", []):
            for iid in b.get("loot", []):
                sources.setdefault(str(iid), []).append({"key": d["key"], "boss": b["name"]})
        for iid in d.get("trash", []):
            sources.setdefault(str(iid), []).append({"key": d["key"], "trash": True})
        for q in d.get("quests", []):
            r = q.get("rewards", {})
            for iid in r.get("choice", []) + r.get("items", []):
                sources.setdefault(str(iid), []).append({"key": d["key"], "quest": q.get("name", "")})
    wanted = [iid for iid in sources if items.get(iid, {}).get("inv") in WORN]
    with cf.ThreadPoolExecutor(6) as pool:
        tips = dict(zip(wanted, pool.map(tooltip, wanted)))
    out_items, out_from = {}, {}
    for iid in wanted:
        it = dict(items[iid])
        it["st"] = stats((tips.get(iid) or {}).get("tooltip"), it.get("inv"))
        out_items[iid] = it
        out_from[iid] = sources[iid]
    dropguard.save_all([(OUT, {"items": out_items, "from": out_from}, ("items",), {"counts": counts})], indent=None)
    with_stats = sum(1 for it in out_items.values() if it["st"])
    print(f"gear: {len(out_items)} pieces from dungeons and raids, {with_stats} with stats read")


if __name__ == "__main__":
    import builder
    builder.run(main)
