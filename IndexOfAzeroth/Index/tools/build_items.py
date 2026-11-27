# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client
import dropguard
import vendorprice
from game import installed_version

TABLES = ("ManifestInterfaceData", "Item", "ItemSparse", "ItemSubClass", "SpellName", "SpellMisc",
          "ItemModifiedAppearance", "ItemAppearance", *vendorprice.TABLES)


def icon_names(build):
    names = {}
    for r in client.rows("ManifestInterfaceData", build):
        folder, file = r["FilePath"].lower().replace("/", "\\"), r["FileName"].lower()
        if folder.startswith("interface\\icons\\") and file.endswith(".blp"):
            names[int(r["ID"])] = file[:-4].strip()
    return names


def appearance_icons(build):
    looks = {number(r["ID"]): number(r["DefaultIconFileDataID"]) for r in client.rows("ItemAppearance", build)}
    return {number(r["ItemID"]): looks.get(number(r["ItemAppearanceID"]), 0)
            for r in client.rows("ItemModifiedAppearance", build) if number(r["ItemAppearanceModifierID"]) == 0}


def number(text):
    try:
        return int(text or 0)
    except ValueError:
        return 0


FIXED_PRICE = 0x4000


def sell_of(r):
    if number(r.get("Flags_1")) & FIXED_PRICE or not vendorprice.by_level(number(r.get("InventoryType"))):
        return number(r.get("SellPrice"))
    return None


def priced_of(r):
    def share(text):
        try:
            return float(text or 0)
        except ValueError:
            return 0.0
    return [number(r.get("InventoryType")), share(r.get("PriceVariance")), share(r.get("PriceRandomValue"))]


def main():
    build = installed_version()
    icons = icon_names(build)
    icon_of, quest_class, filed, looks = {}, set(), {}, appearance_icons(build)
    for r in client.rows("Item", build):
        icon_of[number(r["ID"])] = icons.get(number(r["IconFileDataID"]) or looks.get(number(r["ID"]), 0))
        filed[number(r["ID"])] = [number(r["ClassID"]), number(r["SubclassID"])]
        if number(r["ClassID"]) == 12:
            quest_class.add(number(r["ID"]))
    prices = vendorprice.figures(lambda table: client.rows(table, build))
    classes = {r["ClassID"]: r["ClassName_lang"] for r in client.rows("ItemClass", build) if r.get("ClassName_lang")}
    subs = {f'{r["ClassID"]}.{r["SubClassID"]}': r["DisplayName_lang"] for r in client.rows("ItemSubClass", build)
            if r.get("DisplayName_lang")}

    def quest(r):
        return int(number(r["ID"]) in quest_class or number(r["Bonding"]) == 4 or number(r["StartQuestID"]) > 0)

    def item(r):
        sell = sell_of(r)
        return [r["Display_lang"], number(r["OverallQualityID"]), icon_of.get(number(r["ID"])), quest(r),
                number(r["ItemLevel"]), number(r["RequiredLevel"]), number(r.get("BuyPrice")),
                number(r.get("VendorStackCount")) or 1, sell,
                *(filed.get(number(r["ID"])) or [None, None]), number(r.get("Stackable")),
                *([priced_of(r)] if sell is None else [])]
    items = {str(i): item(r) for i, r in client.items_held(build).items()}
    names = {number(r["ID"]): r["Name_lang"] for r in client.rows("SpellName", build)}
    votes = collections.defaultdict(collections.Counter)
    for r in client.rows("SpellMisc", build):
        name, icon = names.get(number(r["SpellID"])), icons.get(number(r["SpellIconFileDataID"]))
        if name and icon:
            votes[name][icon] += 1
    spells = {n: c.most_common(1)[0][0] for n, c in votes.items()}
    dropguard.save_all([(os.path.join(ROOT, "data", "items.json"), {"build": build, "items": items, "classes": classes, "subs": subs,
                                                                    "prices": prices},
                            ("items",)),
                        (os.path.join(ROOT, "data", "spells.json"), {"build": build, "spells": spells}, ("spells",))],
                       indent=None)
    print(f"{len(items)} items ({sum(1 for v in items.values() if v[2])} with their icon, "
          f"{sum(v[3] for v in items.values())} quest items) and {len(spells)} spell names with an icon")


if __name__ == "__main__":
    import builder
    builder.run(main)
