# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client
import dropguard
from game import installed_version

TABLES = ("ManifestInterfaceData", "Item", "ItemSparse", "SpellName", "SpellMisc")


def icon_names(build):
    names = {}
    for r in client.rows("ManifestInterfaceData", build):
        folder, file = r["FilePath"].lower().replace("/", "\\"), r["FileName"].lower()
        if folder.startswith("interface\\icons\\") and file.endswith(".blp"):
            names[int(r["ID"])] = file[:-4].strip()
    return names


def number(text):
    try:
        return int(text or 0)
    except ValueError:
        return 0


def main():
    build = installed_version()
    icons = icon_names(build)
    icon_of, quest_class = {}, set()
    for r in client.rows("Item", build):
        icon_of[number(r["ID"])] = icons.get(number(r["IconFileDataID"]))
        if number(r["ClassID"]) == 12:
            quest_class.add(number(r["ID"]))

    def quest(r):
        return int(number(r["ID"]) in quest_class or number(r["Bonding"]) == 4 or number(r["StartQuestID"]) > 0)

    def item(r):
        return [r["Display_lang"], number(r["OverallQualityID"]), icon_of.get(number(r["ID"])), quest(r),
                number(r["ItemLevel"]), number(r["RequiredLevel"]), number(r.get("BuyPrice")),
                number(r.get("VendorStackCount")) or 1, number(r.get("SellPrice"))]
    items = {r["ID"]: item(r) for r in client.rows("ItemSparse", build)}
    names = {number(r["ID"]): r["Name_lang"] for r in client.rows("SpellName", build)}
    votes = collections.defaultdict(collections.Counter)
    for r in client.rows("SpellMisc", build):
        name, icon = names.get(number(r["SpellID"])), icons.get(number(r["SpellIconFileDataID"]))
        if name and icon:
            votes[name][icon] += 1
    spells = {n: c.most_common(1)[0][0] for n, c in votes.items()}
    dropguard.save_all([(os.path.join(ROOT, "data", "items.json"), {"build": build, "items": items}, ("items",)),
                        (os.path.join(ROOT, "data", "spells.json"), {"build": build, "spells": spells}, ("spells",))],
                       indent=None)
    print(f"{len(items)} items ({sum(1 for v in items.values() if v[2])} with their icon, "
          f"{sum(v[3] for v in items.values())} quest items) and {len(spells)} spell names with an icon")


if __name__ == "__main__":
    import builder
    builder.run(main)
