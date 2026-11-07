# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import words



def class_bit(cls):
    return 1 << ((cls or 1) - 1)


ARMOR_OK = {1: {1: 1, 2: 1, 3: 1, 4: 40, 6: 1}, 2: {1: 1, 2: 1, 3: 1, 4: 40, 6: 1, 7: 1}, 3: {1: 1, 2: 1, 3: 40}, 4: {1: 1, 2: 1},
            5: {1: 1}, 7: {1: 1, 2: 1, 3: 40, 6: 1, 9: 1}, 8: {1: 1}, 9: {1: 1}, 11: {1: 1, 2: 1, 8: 1}}
WEAPON_OK = {1: [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18], 2: [0, 1, 4, 5, 6, 7, 8], 3: [0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18],
             4: [0, 2, 3, 4, 7, 13, 15, 16, 18], 5: [4, 10, 15, 19], 7: [0, 1, 4, 5, 10, 13, 15], 8: [7, 10, 15, 19], 9: [7, 10, 15, 19],
             11: [4, 5, 10, 13, 15]}
WEAPON_SKILL = {0: "Axes", 1: "Two-Handed Axes", 2: "Bows", 3: "Guns", 4: "Maces", 5: "Two-Handed Maces", 6: "Polearms",
                7: "Swords", 8: "Two-Handed Swords", 10: "Staves", 13: "Fist Weapons", 15: "Daggers", 16: "Thrown", 18: "Crossbows",
                19: "Wands"}
ARMOR_SKILL = {1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate Mail", 6: "Shield"}
ARMOR_TOP = {1: [3, 4], 2: [3, 4], 3: [2, 3], 7: [2, 3], 4: [2], 11: [2], 5: [1], 8: [1], 9: [1]}
BODY_ARMOR = {1, 3, 5, 20, 6, 7, 8, 9, 10}
SLOTS_FOR = {1: [1], 2: [2], 3: [3], 5: [5], 20: [5], 6: [6], 7: [7], 8: [8], 9: [9], 10: [10], 11: [11, 12], 12: [13, 14],
             16: [15], 13: [16, 17], 17: [16], 21: [16], 22: [17], 14: [17], 23: [17], 15: [18], 26: [18], 25: [18], 28: [18]}


def usability_for(it, cls, level=1, n=None):
    n = n or {}
    if not cls or not it:
        return {"use": "yes"}
    if it.get("classes") and not it["classes"] & class_bit(cls):
        return {"use": "never"}
    if it.get("cls") == 4 and it.get("sub"):
        need, skill = ARMOR_OK.get(cls, {}).get(it["sub"]), ARMOR_SKILL.get(it["sub"])
        if not need:
            return {"use": "never"}
        if not skill:
            return {"use": "yes"}
        known = n.get("armorKinds") if (n.get("armorKinds") or 0) & 2 else None
        if (known & (1 << it["sub"])) if known is not None else level >= need:
            best = best_armor_for(cls, level, n)
            return {"use": "yes", "lower": best} if best and it.get("inv") in BODY_ARMOR and it["sub"] < best else {"use": "yes"}
        return {"use": "later", "skill": skill, "level": need} if level < need else {"use": "train", "skill": skill}
    if it.get("cls") == 2 and WEAPON_SKILL.get(it.get("sub")):
        if it["sub"] not in WEAPON_OK.get(cls, []):
            return {"use": "never"}
        known = n.get("weaponKinds") or None
        return {"use": "yes"} if known is None or known & (1 << it["sub"]) else {"use": "train", "skill": WEAPON_SKILL[it["sub"]]}
    return {"use": "yes"}


def best_armor_for(cls, level=1, n=None):
    n = n or {}
    top = ARMOR_TOP.get(cls)
    if not top:
        return None
    known = n.get("armorKinds") if (n.get("armorKinds") or 0) & 2 else None
    return top[1] if len(top) > 1 and ((known & (1 << top[1])) if known is not None else level >= 40) else top[0]


def is_upgrade(it, gear):
    slots = SLOTS_FOR.get(it.get("inv")) if it else None
    if not gear or not slots or not it.get("il") or not any(v > 0 for v in gear):
        return False
    return it["il"] > min((gear[s - 1] if s - 1 < len(gear) else 0) or 0 for s in slots)


def tag(it, u, up, cmp, small=False):
    if not up:
        return ""
    if u["use"] == "train":
        return words.say("both.upgrades.train", {"skill": u["skill"]})
    if u.get("lower"):
        return words.say("both.upgrades.lower")
    kind = (cmp or {}).get("kind")
    return (words.say("both.upgrades.clear") if kind == "clear" else words.say("both.upgrades.weak") if kind == "weak"
            else words.say("both.upgrades.debatable") if kind == "debatable"
            else words.say("both.upgrades.small") if small else words.say("both.upgrades.item-level"))



MIN_GAIN = 0.5
SLIGHT = 0.05
CLEAR_MIN = 2
CLEAR_OF = 0.1
CHASE_SHARE = 0.5
CLEAR_LOSS = 0.5
CHASE_OF = 0.4
OURS_OF = 0.15
KIN_OF = 0.075
OTHERS_SHARE = 0.4
WEAPON_OWN = 1
EVERYONE = {"sta", "armor", "hp5", "resist", "resfire", "resfrost", "resarcane", "resshadow", "resnature"}
PAIR = {"hit": "spellhit", "spellhit": "hit", "crit": "spellcrit", "spellcrit": "crit"}
SPEC_AFTER = 5
LEVELING_TREE = {1: 1, 2: 3, 3: 1, 4: 2, 5: 3, 7: 2, 8: 3, 9: 1, 11: 2}
PER_BUDGET = {"ap": 2, "rap": 2.5, "fap": 2.5, "sp": 1.17, "heal": 2.2, "spfire": 1.4, "spfrost": 1.4, "sparcane": 1.4,
              "spshadow": 1.4, "spnature": 1.4, "spholy": 1.4, "hit": 0.1, "spellhit": 0.1, "crit": 0.071, "spellcrit": 0.071,
              "dodge": 0.083, "parry": 0.05, "block": 0.2, "def": 0.83, "blockvalue": 1.5, "mp5": 0.4, "hp5": 0.33, "armor": 10,
              "resist": 0.25, "dps": 0.2, "ohdps": 0.2, "rdps": 0.2, "wdps": 0.2}
WEAPON_DAMAGE = ("dps", "ohdps", "rdps", "wdps")


def spec_tree(nums):
    trees = [nums.get(f"tree{t}Points") or 0 for t in (1, 2, 3)]
    return trees.index(max(trees)) + 1 if max(trees) >= SPEC_AFTER else 0


def specs_for(weights, cls, tree, role):
    specs = (((weights or {}).get("classes") or {}).get(str(cls)) or {}).get("specs") or []
    if tree:
        in_tree = [s for s in specs if s.get("tree") == tree]
        as_role = [s for s in in_tree if s.get("role") == ("tank" if role == "tank" else "damage")]
        return (as_role or in_tree)[:1]
    as_role = [s for s in specs if s.get("role") == role] if role else []
    return as_role or specs


def spec_info(weights, cls, nums, role=None):
    got = specs_for(weights, cls, spec_tree(nums) or LEVELING_TREE.get(cls), role)
    s = got[0] if got else None
    return {"name": (s or {}).get("name") or "", "w": (s or {}).get("w") or {}}


def tree_roles(weights):
    out = {}
    for cls, c in sorted(((weights or {}).get("classes") or {}).items(), key=lambda kv: int(kv[0])):
        trees = [[], [], []]
        for s in c.get("specs") or ():
            tree, role = s.get("tree"), s.get("role")
            if isinstance(tree, int) and 1 <= tree <= len(trees) and role and role not in trees[tree - 1]:
                trees[tree - 1].append(role)
        out[str(cls)] = trees
    return out


def add_up(values):
    total = 0
    for v in values:
        total = total + v
    return total


def gear_score(st, w):
    return add_up((w.get(k) or 0) * (v or 0) for k, v in (st or {}).items())


def per_budget(w, k):
    return (w.get(k) or 0) * PER_BUDGET.get(k, 1)


def best_per_budget(w):
    return max([0] + [per_budget(w, k) for k in w if k not in WEAPON_DAMAGE])


def chase_stats(w):
    best = best_per_budget(w)
    chase = {k for k in w if k not in WEAPON_DAMAGE and per_budget(w, k) >= best * CHASE_OF}
    return chase | {k for k in WEAPON_DAMAGE if (w.get(k) or 0) >= WEAPON_OWN}


def own_stats(w):
    best = best_per_budget(w)
    own = {k for k in w if k not in WEAPON_DAMAGE and per_budget(w, k) >= best * OURS_OF}
    return own | {k for k in WEAPON_DAMAGE if (w.get(k) or 0) >= WEAPON_OWN}


def others_stats(st, w, weights):
    classes = list(((weights or {}).get("classes") or {}).values())
    kin = next((c for c in classes if any(s["w"] is w for s in c["specs"])), None)
    specs = [s for c in classes if c is not kin for s in c["specs"]]
    best = best_per_budget(w)

    def own(k):
        return per_budget(w, k) >= best * OURS_OF or bool(PAIR.get(k) and st.get(PAIR[k]) == st[k]
                                                          and per_budget(w, PAIR[k]) >= best * OURS_OF) \
            or (per_budget(w, k) >= best * KIN_OF and any(k in chase_stats(s["w"]) for s in (kin or {}).get("specs", ())))
    return [k for k in st if st[k] > 0 and k not in EVERYONE and k not in WEAPON_DAMAGE and not own(k)
            and any(k in chase_stats(s["w"]) for s in specs)]


def class_weapon_budget(st, w, weights):
    classes = list(((weights or {}).get("classes") or {}).values())
    kin = next((c for c in classes if any(s["w"] is w for s in c["specs"])), None)
    k = next((d for d in WEAPON_DAMAGE if (st.get(d) or 0) > 0 and d in chase_stats(w)
              and not any(c is not kin and any(d in chase_stats(s["w"]) for s in c["specs"]) for c in classes)), None)
    return st[k] / PER_BUDGET[k] if k else 0


def budget_of(st, keys):
    return add_up(st[k] / PER_BUDGET.get(k, 1) for k in keys
                  if st[k] > 0 and k != "armor" and k not in WEAPON_DAMAGE and not (k.startswith("spell") and PAIR.get(k) and st.get(PAIR[k]) == st[k]))


def compare_gear(item, worn, w, weights):
    a, b, gains, losses = item or {}, worn or {}, [], []
    for k in dict.fromkeys([*a, *b]):
        d = (a.get(k) or 0) - (b.get(k) or 0)
        v = (w.get(k) or 0) * d
        if v > 0.001:
            gains.append((k, d, v))
        elif v < -0.001:
            losses.append((k, d, -v))
    gain, loss = add_up(g[2] for g in gains), add_up(x[2] for x in losses)
    net = gain - loss
    chase, own = chase_stats(w), own_stats(w)
    chased = add_up(g[2] for g in gains if g[0] in chase)
    owned = add_up(g[2] for g in gains if g[0] in own) - add_up(x[2] for x in losses if x[0] in own)
    others = others_stats(a, w, weights)
    others_share = budget_of(a, others) / ((budget_of(a, list(a)) + class_weapon_budget(a, w, weights)) or 1)
    base = max(0, gear_score(b, w))
    real = max(MIN_GAIN, base * SLIGHT)
    kind = why = None
    if net >= real and owned >= 0:
        rest = sorted((g for g in gains if g[0] not in own), key=lambda g: -g[2])
        holder = rest[0][0] if rest else None
        if others_share >= OTHERS_SHARE:
            kind, why = "debatable", "others"
        elif owned < real:
            kind, why = "debatable", "holder" if holder in WEAPON_DAMAGE else "barely"
        elif owned >= max(CLEAR_MIN, base * CLEAR_OF) and chased >= gain * CHASE_SHARE and loss <= gain * CLEAR_LOSS:
            kind = "clear"
        else:
            kind, why = "weak", "offstats" if chased < gain * CHASE_SHARE else "trade" if loss > gain * CLEAR_LOSS else "small"
    return {"kind": kind, "why": why, "others": others, "gain": gain, "loss": loss, "net": net}


def damage_as(st, key):
    if not (st or {}).get("dps") or st.get(key):
        return st
    return {**{k: v for k, v in st.items() if k != "dps"}, key: st["dps"]}


def as_ranged(st):
    return damage_as(st, "rdps")


def in_slot(st, slot):
    return as_ranged(st) if slot == 18 else damage_as(st, "ohdps") if slot == 17 else st


UNKNOWN = object()


def worn_in(worn, slot):
    if worn is None:
        return UNKNOWN
    it = worn.get(slot, UNKNOWN)
    return {**it, "st": in_slot(it.get("st"), slot)} if isinstance(it, dict) else it


def replaced(inv, worn, w):
    off = worn_in(worn, 17)
    slots = [16] if inv == 13 and not (isinstance(off, dict) and (off.get("st") or {}).get("ohdps")) else SLOTS_FOR.get(inv) or []
    have = [(s, worn_in(worn, s)) for s in slots]
    if not have or any(it is UNKNOWN for _, it in have):
        return False, None, None
    slot, against = sorted(have, key=lambda p: gear_score(p[1]["st"], w) if p[1] else float("-inf"))[0]
    return True, against, slot


PICK_ORDER = {"clear": 0, "weak": 1, "debatable": 2}
SMALL_GAIN = 4


def small_gain(v):
    return not v["up"] and v["u"]["use"] in ("yes", "train") and ((v["cmp"] or {}).get("net") or 0) > 0


def reward_picks(choices, me, worn_ids, want=None):
    ids, ranked, slots = [iid for iid, _ in choices], [], set()
    if want is not None and want in ids:
        return {"ids": ids, "picks": [{"id": want, "v": words.say("both.upgrades.wanted"), "want": True}], "known": True, "worn": []}, None
    for iid, it in choices:
        if it is None:
            return {"ids": ids, "picks": [], "known": False, "worn": []}, None
        v = verdict(it, me)
        if v["u"]["use"] in ("yes", "train"):
            slots.update(SLOTS_FOR.get(it.get("inv")) or ())
        small = small_gain(v)
        empty = me["worn"] is not None and all(not worn_ids.get(s) for s in SLOTS_FOR.get(it.get("inv")) or (None,))
        if (v["up"] or small) and (not v["u"].get("lower") or empty):
            cmp = v["cmp"] or {}
            if small:
                v = {**v, "tag": tag(it, v["u"], True, None, small=True)}
            ranked.append(((v["u"]["use"] == "train", SMALL_GAIN if small else PICK_ORDER.get(cmp.get("kind"), 3),
                            -cmp.get("net", 0), -(it.get("il") or 0)), iid, it, v))
    ranked.sort(key=lambda r: r[0])
    worn = [[s, worn_ids.get(s) or 0] for s in sorted(slots)] if me["worn"] is not None else []
    top = ranked[0] if ranked and ranked[0][3]["u"]["use"] == "yes" else None
    picks = [{"id": iid, "v": v["tag"]} for _, iid, _, v in ranked]
    upgrade = {iid for _, iid, _, _ in ranked}
    priced = [(it["sell"], iid) for iid, it in choices if iid not in upgrade and (it.get("sell") or 0) > 0]
    if priced:
        sell, iid = max(priced, key=lambda p: p[0])
        picks.append({"id": iid, "v": words.say("both.upgrades.vendor"), "sell": sell})
    return {"ids": ids, "picks": picks, "known": True, "worn": worn}, top and (top[1], top[2], top[3]["slot"])


def verdict(it, me):
    u = usability_for(it, me["cls"], me["level"], me["nums"])
    usable = u["use"] in ("yes", "train")
    known, against, slot = replaced(it.get("inv"), me["worn"], me["w"]) if usable else (False, None, None)
    st = in_slot(it.get("st"), slot)
    cmp = compare_gear(st, against and against.get("st"), me["w"], me["weights"]) \
        if usable and st is not None and known and me.get("weights") else None
    up = usable and (bool(cmp["kind"]) if cmp else is_upgrade(it, me.get("gear")))
    return {"u": u, "cmp": cmp, "up": up, "tag": tag(it, u, up, cmp), "slot": slot}
