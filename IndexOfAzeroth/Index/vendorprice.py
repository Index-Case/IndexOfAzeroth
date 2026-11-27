# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
TABLES = ("ItemPriceBase", "ImportPriceArmor", "ImportPriceShield", "ImportPriceWeapon", "ImportPriceQuality",
          "ItemClass")

ROBE, CHEST, SHIELD = 20, 5, 14
ARMOR_SLOTS = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 16, 23}
WEAPON_ROW = {21: 1, 22: 2, 13: 3, 17: 4, 15: 5, 26: 5, 28: 5}
WEAPON_BASE = {13, 17, 21, 22, 15, 26}
SHIELD_ROW = 2
UNPROVEN = {22, 28}
ARMOR_COLUMN = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3}
ARMOR_COLUMNS = ("ClothModifier", "LeatherModifier", "ChainModifier", "PlateModifier")


def _number(v):
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def slot_of(inv):
    return CHEST if inv == ROBE else inv


def by_level(inv):
    inv = slot_of(inv)
    return inv in ARMOR_SLOTS or inv == SHIELD or inv in WEAPON_ROW


def figures(rows):
    one = lambda table: {r["ID"]: _number(r["Data"]) for r in rows(table)}
    return {"base": {r["ItemLevel"]: [_number(r["Armor"]), _number(r["Weapon"])] for r in rows("ItemPriceBase")},
            "armor": {r["ID"]: [_number(r[c]) for c in ARMOR_COLUMNS] for r in rows("ImportPriceArmor")},
            "shield": one("ImportPriceShield"), "weapon": one("ImportPriceWeapon"), "quality": one("ImportPriceQuality"),
            "classes": {r["ClassID"]: _number(r["PriceModifier"]) for r in rows("ItemClass")}}


def sell(got, inv, item_class, subclass, quality, level, variance, random_value, stack):
    inv = slot_of(inv)
    if inv in UNPROVEN:
        return None
    base = got["base"].get(str(level))
    quality_factor = got["quality"].get(str(quality + 1))
    modifier = got["classes"].get(str(item_class))
    if inv in ARMOR_SLOTS:
        row = got["armor"].get(str(inv))
        factor = None if row is None else row[ARMOR_COLUMN[subclass]] if subclass in ARMOR_COLUMN else 1.0
    elif inv == SHIELD:
        factor = got["shield"].get(str(SHIELD_ROW))
    else:
        factor = got["weapon"].get(str(WEAPON_ROW.get(inv)))
    if None in (base, quality_factor, modifier, factor):
        return None
    buy = int(variance * factor * base[1 if inv in WEAPON_BASE else 0] * quality_factor * random_value)
    return int(buy * modifier / max(1, stack or 1))
