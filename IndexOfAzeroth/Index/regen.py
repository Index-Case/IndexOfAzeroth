# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
TICK_S = 2
SPIRIT = {1: (0.50, 6), 2: (0.25, 6), 3: (0.25, 6), 4: (0.50, 2), 5: (0.10, 6), 7: (0.11, 7), 8: (0.10, 6),
          9: (0.07, 6), 11: (0.09, 6.5)}
SITTING = 4 / 3
TROLL_OUT, TROLL_IN = 1.10, 0.10
FOOD, EVERY = 1, 2


def spirit_tick(class_id, spirit):
    per, flat = SPIRIT.get(class_id, (0, 0))
    return max(0.0, spirit * per + flat) if spirit is not None and class_id in SPIRIT else 0.0


def gear_hp5(stats):
    return sum((st or {}).get("st", {}).get("hp5", 0) or 0 for st in stats)


def per_second(inputs, combat, now):
    buffs = [b for b in inputs.get("buffs") or () if b["period"] and (b["ends"] is None or b["ends"] > now)]
    eating = any(b["kind"] == FOOD for b in buffs)
    tick = spirit_tick(inputs.get("class"), inputs.get("spirit"))
    troll = inputs.get("race") == "Troll"
    if combat:
        tick *= TROLL_IN if troll else 0
    else:
        tick *= (TROLL_OUT if troll else 1) * (SITTING if eating else 1)
    return tick / TICK_S + (inputs.get("hp5") or 0) / 5 + sum(b["amount"] / b["period"] for b in buffs)
