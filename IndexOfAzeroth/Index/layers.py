# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import re
import statistics
import time
import os

import facts
from facts import MAX_LEVEL, RUN_SPEED
from geo import MapGeometry, height_of, reach_yards, to_map
import kept
from serverlog import start_thread
import store
import storewriter

ROOT = os.path.dirname(os.path.abspath(__file__))
MARGIN = 0.1
MAX_ABOVE = 3
ELITE_RANKS = {1, 2, 3, 4}
AGGRO_MARGIN = 2.0
AGGRO = 20.0
AGGRO_RANGE = (5.0, 45.0)
WANDER_UNKNOWN = 5.0
HEIGHT_MATCH = 5.0
POOL_MATCH = 5.0
FIGHT_ABOVE = 2


AMMO_TITLES = {"arrow": re.compile(r"Bow|Fletcher|Arrow"), "bullet": re.compile(r"Gun|Bullet")}


def sells_ammo(sub, kind):
    names = {k for k, pattern in AMMO_TITLES.items() if pattern.search(sub)}
    return len(names) != 1 or kind in names


WALKER_REACH = 50.0


def attacks(sv, bit):
    return bool(bit and sv["en"] & bit and not sv["fr"] & (1 | bit))


def npc_side(sv):
    fr, en = sv.get("fr", 0), sv.get("en", 0)
    bits = facts.FACTION_BITS
    friends = [side for side, bit in bits.items() if fr & bit]
    if not fr & 1 and len(friends) == 1:
        return friends[0]
    foes = [side for side, bit in bits.items() if en & bit]
    return next(side for side in bits if side not in foes) if not fr and len(foes) == 1 else None


def walks(services, patrols, geo):
    out = {}
    for sv in services:
        routes = patrols.get(str(sv.get("id")))
        if not routes:
            continue
        spawns = [w for area, pts in sv["s"].items() for x, y in pts for w in [geo.area_to_world(area, x, y)] if w]
        reach = max((min((math.hypot(float(p[0]) - s[0], float(p[1]) - s[1]) for s in spawns if s[2] == inst), default=0.0)
                     for inst, xy in routes for p in xy), default=0.0)
        if reach > WALKER_REACH:
            out[sv.get("id")] = reach + sum(math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
                                            for _, xy in routes for a, b in zip(xy, xy[1:]))
    return out


def sells(sv, items):
    goods = set(sv.get("goods") or ())
    return bool(items) and all(int(i) in goods for i in items)


_sellers = None


def seller_index(services):
    global _sellers
    got = _sellers
    if got is None or got[0] is not services:
        index = {}
        for sv in services:
            for i in {int(i) for i in sv.get("goods") or ()}:
                index.setdefault(i, []).append(sv)
        got = _sellers = (services, index)
    return got[1]


def sellers_of(services, item):
    return seller_index(services).get(int(item), [])


def serving(services, geo, faction, cats=None, detail=None, keep=None, walking=None, walled=frozenset()):
    bit = facts.faction_bit(faction)
    found = []
    for sv in services:
        if attacks(sv, bit):
            continue
        if cats is None:
            kind = next((c for c, _ in sv["cats"]), "vendor")
        else:
            kind = next((c for c, d in sv["cats"] if c in cats and (detail is None or d == detail)), None)
        if kind is None or (keep is not None and not keep(sv, kind)):
            continue
        found.append((sv, kind, [(w[0], w[1], w[2], area) for area, pts in sv["s"].items() for x, y in pts
                                 for w in [geo.area_to_world(area, x, y)] if w and (sv.get("id"), w[2], w[0], w[1]) not in walled]))
    walking = walking or {}
    standing = [s for sv, _, spots in found if sv.get("id") not in walking for s in spots]
    out = []
    for sv, kind, spots in found:
        walk = walking.get(sv.get("id"))
        if walk is not None:
            spots = [s for s in spots if not any(t[2] == s[2] and math.hypot(t[0] - s[0], t[1] - s[1]) <= walk for t in standing)]
        if spots:
            out.append((sv, kind, spots))
    return out


TOP = 5
MIN_SPAWNS_FOR_TOP = 5
SINGLE_SPAWNS = 2


def zero_difference(level):
    for cap, zd in ((7, 5), (9, 6), (11, 7), (15, 8), (19, 9), (29, 11), (39, 12), (44, 13), (49, 14), (54, 15), (59, 16)):
        if level <= cap:
            return zd
    return 17


def gray_level(level):
    if level <= 5:
        return 0
    if level <= 39:
        return level - 5 - level // 10
    if level <= 59:
        return level - 1 - level // 5
    return level - 9


def fights_from(mob_level, above=FIGHT_ABOVE):
    return max(1, math.ceil(mob_level - above))


def kill_xp(player, mob, cap=MAX_LEVEL):
    if player >= cap:
        return 0.0
    base = player * 5 + 45
    if mob >= player:
        return base * (1 + 0.05 * min(mob - player, 4))
    if mob <= gray_level(player):
        return 0.0
    return base * (1 - (player - mob) / zero_difference(player))


XP_RULES = {"inside": 70291, "grouped": 70291}


def client_build():
    try:
        import game
        return int(str(game.played_version()).rsplit(".", 1)[-1])
    except Exception:
        return None


class XpMeasure:
    KEEP, MIN = 400, 5

    def __init__(self, path=None, rules=None, build=None):
        self.path = path or os.path.join(ROOT, "data", "xp.json")
        kept = store.load_json(self.path, {})
        self.samples, self.inside, self.grouped = (kept.get(k, []) for k in ("samples", "inside", "grouped"))
        self.rules = XP_RULES if rules is None else rules
        self.build = build or client_build
        self.noted = len(self.samples)
        self.version = self.noted // 10
        self.shares = {}

    def counted(self, kind, rows=None):
        rows = {"world": self.samples, "inside": self.inside, "grouped": self.grouped}[kind] if rows is None else rows
        since = self.rules.get(kind)
        return rows if not since else [s for s in rows if (s.get("b") or 0) >= since]

    def note(self, level, mob_level, xp, inside=False, party=None):
        expected = kill_xp(level, mob_level)
        if expected <= 0 or not (0 if inside or party else 0.2) < xp / expected < 5:
            return False
        sample = {"l": level, "m": round(mob_level, 1), "xp": round(xp, 1), "at": round(time.time())}
        build = self.build()
        if build:
            sample["b"] = build
        if party:
            sample.update(n=party[0], ls=list(party[1]))
        if inside:
            self.inside = (self.inside + [sample])[-self.KEEP:]
        elif party:
            self.grouped = (self.grouped + [sample])[-self.KEEP:]
        else:
            self.samples = (self.samples + [sample])[-self.KEEP:]
            self.noted += 1
            self.version = self.noted // 10
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        storewriter.save_json_later(self.path, {"samples": self.samples, "inside": self.inside, "grouped": self.grouped}, indent=None)
        return True

    @staticmethod
    def _median(values):
        values = sorted(values)
        return values[len(values) // 2] if values else None

    def share(self, level, mob_level, inside=False):
        diff = round(mob_level - level)
        rows = self.inside if inside else self.samples
        kept = self.shares.get(inside)
        if kept is None or kept[0] is not rows:
            kept = self.shares[inside] = (rows, {})
        out = kept[1].get(diff)
        if out is not None:
            return out
        ratios = [(round(s["m"] - s["l"]), s["xp"] / kill_xp(s["l"], s["m"])) for s in self.counted("inside" if inside else "world", rows)
                  if kill_xp(s["l"], s["m"]) > 0]
        same = [r for d, r in ratios if d == diff]
        if len(same) >= self.MIN:
            out = self._median(same)
        else:
            out = self._median([r for _, r in ratios]) if len(ratios) >= self.MIN else 0.0 if inside else 1.0
        kept[1][diff] = out
        return out

    def measured(self, inside=False):
        return len(self.counted("inside" if inside else "world")) >= self.MIN

    def summary(self):
        ratios = [s["xp"] / kill_xp(s["l"], s["m"]) for s in self.counted("world") if kill_xp(s["l"], s["m"]) > 0]
        return {"kills": len(ratios), "share": round(self._median(ratios), 3) if len(ratios) >= self.MIN else None}


XP_AURA_EFFECTS = {1243969: (("kill", 5), ("quest", 0), (None, 0)),
                   429959: (("quest", 1), ("kill", 1)),
                   1225490: ((None, -50), ("flight", 20))}


class XpAuras:

    def __init__(self, auras, now=None):
        now = time.time() if now is None else now
        self.effects = []
        for a in auras or ():
            ends = None if a.get("ends") is None else a["ends"] - now
            effects = XP_AURA_EFFECTS.get(a.get("id"), ())
            values = a.get("points") or [each * (a.get("stacks") or 1) for _, each in effects]
            for (does, _), value in zip(effects, values):
                if does and value:
                    self.effects.append((ends, does, value))

    def factor(self, does, at=0.0):
        out = 1.0
        for ends, what, value in self.effects:
            if what == does and (ends is None or ends > at):
                out *= 1 + value / 100
        return out


class PaceMeasure:
    KEEP, MIN, GAP_MOST = 300, 10, 150.0

    def __init__(self, path=None):
        self.path = path or os.path.join(ROOT, "data", "pace.json")
        self.samples = store.load_json(self.path, {}).get("samples", [])
        self.current = None
        self.noted = len(self.samples)
        self.version = self.noted // 10

    def note(self, char, seconds, now=None):
        if not char or not 3.0 <= seconds <= self.GAP_MOST:
            return False
        self.current = char
        self.samples = (self.samples + [{"c": char, "r": round(seconds / (KILL_SECONDS + KILL_OVERHEAD), 3),
                                         "at": round(now or time.time())}])[-self.KEEP:]
        self.noted += 1
        self.version = self.noted // 10
        storewriter.save_json_later(self.path, {"samples": self.samples}, indent=None)
        return True

    def move(self, old, new):
        if not old or not new or old == new:
            return False
        moved = False
        for s in self.samples:
            if s.get("c") == old:
                s["c"] = new
                moved = True
        if self.current == old:
            self.current = new
        if moved:
            storewriter.save_json_later(self.path, {"samples": self.samples}, indent=None)
        return moved

    def factor(self):
        mine = [s["r"] for s in self.samples if s["c"] == self.current]
        use = mine if len(mine) >= self.MIN else [s["r"] for s in self.samples] if len(self.samples) >= self.MIN else None
        return max(0.5, min(4.0, sum(use) / len(use))) if use else 1.0

    def summary(self):
        mine = sum(1 for s in self.samples if s["c"] == self.current)
        n = mine if mine >= self.MIN else len(self.samples) if len(self.samples) >= self.MIN else 0
        return {"kills": n, "seconds": round((KILL_SECONDS + KILL_OVERHEAD) * self.factor()), "measured": n > 0}


def skinning_needed(level):
    if level <= 10:
        return 1
    return (level - 10) * 10 if level <= 20 else level * 5


NO_SKINNING = -1


def skinned(beast, level, skinning):
    return bool(beast) and (not skinning or skinning_needed(level) <= skinning)


SKIN_UP = ((25, 1.0), (50, 0.5), (75, 0.25))


def skin_up(skill, needed):
    return next((chance for past, chance in SKIN_UP if skill - needed < past), 0.0)


def normalise(entries):
    if not entries:
        return
    ranked = sorted(e["value"] for e in entries)
    top = ranked[min(len(ranked) - 1, int(len(ranked) * 0.95))] or ranked[-1] or 1
    for e in entries:
        e["weight"] = min(1.0, e["value"] / top)


KILL_SECONDS = 20.0
KILL_OVERHEAD = 12.0
PATROL_STEP = 12.0
CAMP_CELL = 80.0
CAMP_WALK = 500.0
LOOP_MOBS = 4
SPOT_WHOLE = 0.995
CAMP_CLEAR = 45.0
KILL_REACH = 40.0
COVER_STOPS = 14
ORDER_ALL = 7
STOP_YARDS = 10.0
TIGHTEN_STEPS = (16.0, 8.0, 4.0, 2.0)
TIGHTEN_PULLS = [(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)) for k in range(8)]
CAMP_GROW = (1, 2, 3)
RESPAWN_FALLBACK = 300
CAMP_MARGIN = 1.5
AOE_PACK = 35.0
AOE_PULL = 1.5
CASTER_NAMES = re.compile(r"shaman|mystic|seer|oracle|witch|medicine man|sorcer|mage|magus|magister|conjurer|summoner|"
                          r"warlock|necro|acolyte|priest|cleric|adept|apprentice|shadowcaster|mancer|elementalist|channeler|"
                          r"invoker|enchant|totemic|wizard|diviner|druid|healer|spellbinder|evoker|arcanist|thaumaturg|sage|"
                          r"scryer", re.I)
SHOOTER_NAMES = re.compile(r"archer|rifleman|hunter|marksman|sharpshooter|sniper|gunner|thrower", re.I)
MOB_DETECTION, MOB_CASTER = 12, 13


def aoe_poor(mob):
    caster = mob[MOB_CASTER] if len(mob) > MOB_CASTER else None
    return bool(caster if caster is not None else CASTER_NAMES.search(mob[0])) or bool(SHOOTER_NAMES.search(mob[0]))


GIVER_WALKS = os.path.join(ROOT, "data", "giver_walks.json")


def load_giver_walks(path=GIVER_WALKS):
    out = {}
    for nid, entry in (store.load_json(path, {}).get("walks") or {}).items():
        walks = [(w[0], w[1]) for w in entry.get("w") or () if isinstance(w, list) and len(w) == 2
                 and isinstance(w[1], list) and len(w[1]) >= 2]
        if walks:
            out[str(nid)] = walks
    return out


def load_patrols(homes=False, shares=False):
    import arrays
    d = arrays.load_npz(os.path.join(ROOT, "data", "patrols.npz"))
    if not d or not {"entry", "map", "xy", "start"} <= set(d):
        return {}
    entries, maps, xy, start = d["entry"], d["map"], d["xy"], d["start"]
    home, home_start = d.get("home"), d.get("home_start")
    if home is None or home_start is None:
        home, home_start = xy[:0], [0] * (len(entries) + 1)
    part = d.get("share")
    if part is None or len(part) != len(entries):
        part = [1.0] * len(entries)
    out = {}
    for i, (entry, inst) in enumerate(zip(entries, maps)):
        route = (int(inst), xy[start[i]:start[i + 1]])
        if homes:
            route += (home[home_start[i]:home_start[i + 1]],)
        if shares:
            route += (float(part[i]),)
        out.setdefault(str(int(entry)), []).append(route)
    return out


def along(route, step):
    import numpy as np
    out = [route[0]]
    for a, b in zip(route, route[1:]):
        n = max(1, int(np.hypot(*(b - a)) // step))
        out += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    return out


GATHER_CLUSTER = 40.0
GATHERED_NEAR = 12.0
GATHERED_PRIOR = 2.0
GATHERED_STACK = 2.0
GATHERED_UP = 0.2
GATHER_PULL = 8.0
GATHER_CLEAR = 10.0
GATHER_STOPS = 14
GATHER_SECONDS = 6.0
GATHER_MARGIN = 1.25
GATHER_NEAR = 20.0
COVER_YARDS = 30.0


class Coverage:

    def __init__(self, pts, weights=None):
        import numpy as np
        self.np = np
        self.xy = np.array([(p[0], p[1]) for p in pts], float).reshape(-1, 2)
        self.count = [1] * len(pts)
        self.weight = [float(v) for v in weights] if weights is not None else [1.0] * len(pts)
        self.memo = {}

    def near(self, pts):
        np = self.np
        if not len(self.xy) or not pts:
            return 0
        line = np.asarray([(p[0], p[1]) for p in pts], float)
        if len(line) == 1:
            line = np.vstack([line, line])
        hit = np.zeros(len(self.xy), bool)
        for a, b in zip(line[:-1], line[1:]):
            ab = b - a
            l2 = float(ab @ ab)
            t = np.clip(((self.xy - a) @ ab) / l2, 0.0, 1.0) if l2 > 0 else np.zeros(len(self.xy))
            hit |= np.hypot(*(self.xy - (a + t[:, None] * ab)).T) <= COVER_YARDS
        mask = 0
        for i in np.flatnonzero(hit):
            mask |= 1 << int(i)
        return mask

    def straight(self, a, b):
        key = (a[0], a[1], b[0], b[1])
        if key not in self.memo:
            self.memo[key] = self.near([a, b])
        return self.memo[key]

    def value(self, mask, of=None):
        of = self.weight if of is None else of
        if mask.bit_count() <= 6:
            total = 0
            while mask:
                low = mask & -mask
                total += of[low.bit_length() - 1]
                mask ^= low
            return total
        np = self.np
        tables = self.memo.get(("bytes", id(of)))
        if tables is None:
            nb = max(1, (len(of) + 7) // 8)
            pad = np.zeros(nb * 8)
            pad[:len(of)] = of
            bits = (np.arange(256)[:, None] >> np.arange(8)) & 1
            tables = self.memo[("bytes", id(of))] = ((bits @ pad.reshape(nb, 8).T).T, np.arange(nb), nb)
        table, at, nb = tables
        total = float(table[at, np.frombuffer(mask.to_bytes(nb, "little"), np.uint8)].sum())
        return int(round(total)) if of is self.count else total


class RangeOr:

    def __init__(self, masks):
        self.n, row = len(masks), list(masks) * 2
        self.table, span = [row], 1
        while span * 2 <= len(row):
            prev = self.table[-1]
            self.table.append([prev[i] | prev[i + span] for i in range(len(prev) - span)])
            span *= 2

    def of(self, start, length):
        if length <= 0:
            return 0
        start, level = start % self.n, length.bit_length() - 1
        row = self.table[level]
        return row[start] | row[start + length - (1 << level)]


def grouped(pts, reach=GATHER_CLUSTER, weights=None):
    groups = []
    for i, p in enumerate(pts):
        near = [g for g in groups if any(math.hypot(p[0] - pts[j][0], p[1] - pts[j][1]) <= reach for j in g)]
        merged = [i]
        for g in near:
            merged += g
            groups.remove(g)
        groups.append(merged)
    held = weights if weights is not None else [1] * len(pts)
    size = [0] * len(pts)
    out = []
    for g in groups:
        total = sum(held[j] for j in g)
        for j in g:
            size[j] = total
        out.append((sum(pts[j][0] for j in g) / len(g), sum(pts[j][1] for j in g) / len(g), total, len(g)))
    return out, size


def clusters(pts, reach=GATHER_CLUSTER):
    return grouped(pts, reach)[0]


def gather_rate(nodes, yards, speed, respawn, weighed=0.0):
    lap = (yards + weighed) / max(speed, 1.0) + nodes * GATHER_SECONDS
    return nodes * 60.0 / max(lap, respawn * GATHER_MARGIN, 1.0)


def gather_score(cover, passed, yards, speed, respawn):
    nodes = cover.value(passed)
    return {"passed": cover.value(passed, cover.count), "nodes": round(nodes, 2),
            "lap": yards / max(speed, 1.0) + nodes * GATHER_SECONDS, "rate": gather_rate(nodes, yards, speed, respawn)}


CROSS_YARDS = 100.0
BACK_SHARE = 1.0
EMPTY_SHARE = 0.5
POLISH_MOST = 16


def turn_back(a, b, c):
    ux, uy, vx, vy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if not lu or not lv:
        return 0.0
    return min(lu, lv) * max(0.0, -(ux * vx + uy * vy) / (lu * lv))


def legs_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    s1, s2, s3, s4 = side(a, b, c), side(a, b, d), side(c, d, a), side(c, d, b)
    return s1 * s2 < 0 and s3 * s4 < 0


def way_legs(route, start=None, loop=False):
    pts = [tuple(p[:2]) for p in route]
    out = list(zip(pts, pts[1:]))
    if loop and len(pts) > 2:
        out.append((pts[-1], pts[0]))
    elif start is not None and pts and not loop:
        out.insert(0, (tuple(start[:2]), pts[0]))
    return out


def way_cost(route, start=None, loop=False, empty=None):
    legs = way_legs(route, start, loop)
    walk = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in legs)
    turns = list(zip(legs, legs[1:])) + ([(legs[-1], legs[0])] if loop and len(legs) > 2 else [])
    back = sum(turn_back(a, b, c) for (a, b), (_, c) in turns)
    n, crossed = len(legs), 0
    for i in range(n):
        for j in range(i + 2, n):
            if not (loop and i == 0 and j == n - 1) and legs_cross(*legs[i], *legs[j]):
                crossed += 1
    hollow = sum(empty(a, b) for a, b in legs) if empty else 0.0
    return walk + BACK_SHARE * back + CROSS_YARDS * crossed + EMPTY_SHARE * hollow


def polished(route, start=None, loop=False, cost=None):
    route = list(route)
    if len(route) < 3 or len(route) > POLISH_MOST:
        return route
    cost = cost or (lambda r: way_cost(r, start, loop))
    best, n = cost(route), len(route)
    first = 1 if loop else 0
    improved = True
    while improved:
        improved = False
        for i in range(first, n - 1):
            for j in range(i + 1, n):
                trial = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                c = cost(trial)
                if c < best - 0.5:
                    route, best, improved = trial, c, True
        for k in (1, 2, 3):
            for i in range(first, n - k + 1):
                seg, rest = route[i:i + k], route[:i] + route[i + k:]
                for j in range(first, len(rest) + 1):
                    for piece in (seg, seg[::-1]):
                        trial = rest[:j] + piece + rest[j:]
                        if trial == route:
                            continue
                        c = cost(trial)
                        if c < best - 0.5:
                            route, best, improved = trial, c, True
                            break
                    else:
                        continue
                    break
    return route


def loop_tour(stops, start=None):
    if len(stops) < 3:
        return list(stops)
    d = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    todo = list(stops)
    tour = [min(todo, key=lambda s: d(s, start)) if start else todo[0]]
    todo.remove(tour[0])
    while todo:
        nxt = min(todo, key=lambda s: d(s, tour[-1]))
        todo.remove(nxt)
        tour.append(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(tour) - 1):
            for j in range(i + 1, len(tour)):
                a, b, c, e = tour[i - 1], tour[i], tour[j], tour[(j + 1) % len(tour)]
                if d(a, c) + d(b, e) < d(a, b) + d(c, e) - 1e-6:
                    tour[i:j + 1] = reversed(tour[i:j + 1])
                    improved = True
    return tour


def open_tour(stops, start=None):
    if len(stops) < 3:
        return sorted(stops, key=lambda s: math.hypot(s[0] - start[0], s[1] - start[1])) if start else list(stops)
    d = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])
    todo = list(stops)
    tour = [min(todo, key=lambda s: d(s, start)) if start else todo[0]]
    todo.remove(tour[0])
    while todo:
        nxt = min(todo, key=lambda s: d(s, tour[-1]))
        todo.remove(nxt)
        tour.append(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(tour) - 1):
            for j in range(i + 1, len(tour)):
                a, b, c = tour[i - 1], tour[i], tour[j]
                e = tour[j + 1] if j + 1 < len(tour) else None
                if d(a, c) + (d(b, e) if e else 0.0) < d(a, b) + (d(c, e) if e else 0.0) - 1e-6:
                    tour[i:j + 1] = reversed(tour[i:j + 1])
                    improved = True
    return tour


def cover_route(points, start=None, reach=KILL_REACH, loop=False, most=COVER_STOPS, stand=None, heights=None):
    if not points:
        return []
    key = None
    if stand is None:
        try:
            key = (tuple(tuple(p) for p in points), tuple(start) if start is not None else None, reach, loop, most,
                   tuple(height_of((0, 0, h)) for h in heights) if heights is not None else None)
            hit = _covers.get(key)
        except TypeError:
            key, hit = None, None
        if hit is not None:
            return list(hit)
    out = _cover_route(points, start, reach, loop, most, stand, heights)
    if key is not None:
        kept.keep(_covers, key, tuple(out), COVERS_KEPT)
    return out


COVERS_KEPT = 4096

_covers = {}


def height_or_nan(p):
    h = height_of(p)
    return math.nan if h is None else h


def _cover_route(points, start, reach, loop, most, stand, heights=None):
    c = Cover(points, start, reach, loop, stand, heights)
    spots = c.spots()
    if spots is None:
        return []
    routes = [c.pruned(spots)] + [c.pruned(sw) for sw in c.sweeps() if sw and c.covered(sw)]
    routes = [c.polished(c.tightened(c.pruned(c.ordered(rt)))) for rt in routes]
    fit = [rt for rt in routes if len(rt) <= most]
    best = min(fit, key=lambda rt: c.cost(rt) + STOP_YARDS * len(rt)) if fit else min(routes, key=lambda rt: (len(rt), c.cost(rt)))
    return [(round(p[0], 1), round(p[1], 1)) + ((round(p[2], 1),) if height_of(p) is not None else ()) for p in best[:most]]


def stop_heights(stops, spawns, reach=KILL_REACH, stand=None):
    here, standing = stand if stand is not None else ([math.nan] * len(stops), [True] * len(spawns))
    known = [(p[0], p[1], p[2], ok) for p, ok in zip(spawns, standing)
             if len(p) > 2 and p[2] is not None and math.isfinite(p[2])]

    def at(h, z):
        if stand is None or not math.isfinite(h):
            return True
        import nav
        return nav.ground_stands(h, z, bare=True)
    out = []
    for s, h in zip(stops, here):
        if height_of(s) is not None:
            out.append([round(s[0], 1), round(s[1], 1), round(float(s[2]), 1)])
            continue
        near = sorted((reach_yards(s, p), p) for p in known)
        near = [p for d, p in near if d <= reach]
        on = next((p for p in near if p[3] and at(h, p[2])), None)
        if on is not None:
            out.append([round(s[0], 1), round(s[1], 1), round(on[2], 1)])
        elif near and math.isfinite(h):
            out.append([round(s[0], 1), round(s[1], 1), round(h, 1)])
        else:
            out.append([round(s[0], 1), round(s[1], 1)])
    return out


class Cover:

    def __init__(self, points, start, reach, loop, stand, heights=None):
        import numpy as np
        self.start, self.loop, self.stand = start, loop, stand
        self.xy = np.array([(p[0], p[1]) for p in points], float)
        self.z = np.array([math.nan if height_of((0, 0, h)) is None else float(h) for h in heights], float) \
            if heights is not None else np.full(len(self.xy), math.nan)
        self.floor = getattr(stand, "height", None)
        self.under = getattr(stand, "under", None)
        self.stands_at = getattr(stand, "stands_at", None)
        self.r = reach - 0.25
        self.legs_seen = {}

    def height(self, p):
        return float(self.floor(p)) if self.floor is not None else math.nan

    def down(self, p):
        return self.under is not None and bool(self.under(p))

    def yards(self, n, w, z):
        import numpy as np
        flat = np.hypot(self.xy[:, 0] - n, self.xy[:, 1] - w)
        if not math.isfinite(z):
            return flat
        return np.hypot(flat, np.where(np.isfinite(self.z), self.z - z, 0.0))

    def spots(self):
        import numpy as np
        xy, r, stand = self.xy, self.r, self.stand
        lo, hi = xy.min(0) - r / 2, xy.max(0) + r / 2
        grid = np.array([(a, b) for a in np.arange(lo[0], hi[0] + 1e-6, r / 2) for b in np.arange(lo[1], hi[1] + 1e-6, r / 2)])
        cand = np.vstack([xy, grid]) if len(grid) else xy
        own = np.array([self.stands_at((p[0], p[1], h)) for p, h in zip(xy, self.z)], float) \
            if self.stands_at is not None else self.z
        cz = np.concatenate([own, [self.height((float(c[0]), float(c[1]))) for c in grid]]) if len(grid) else own
        if stand is not None:
            ok = np.array([bool(stand((float(c[0]), float(c[1])))) or k < len(xy) and self.down((c[0], c[1], cz[k]))
                           for k, c in enumerate(cand)], bool)
            cand, cz = cand[ok], cz[ok]
            if not len(cand):
                return None
        dz = cz[:, None] - self.z[None, :]
        reaches = np.hypot(np.hypot(cand[:, None, 0] - xy[None, :, 0], cand[:, None, 1] - xy[None, :, 1]),
                           np.where(np.isfinite(dz), dz, 0.0)) <= r
        if stand is not None:
            some = reaches.any(0)
            xy, reaches = xy[some], reaches[:, some]
            if not len(xy):
                return None
            self.xy, self.z = xy, self.z[some]
        left, chosen = np.ones(len(xy), bool), []
        while left.any():
            k = int(np.argmax((reaches & left).sum(1)))
            chosen.append((float(cand[k, 0]), float(cand[k, 1]), float(cz[k])))
            left &= ~reaches[k]
        start = self.start
        return (loop_tour(chosen, start) if self.loop else open_tour(chosen, start)) if len(chosen) > 1 else chosen

    def sweeps(self):
        import numpy as np
        xy, r, start, stand = self.xy, self.r, self.start, self.stand
        mid = xy.mean(0)

        def sweep_along(axis):
            side = np.array([-axis[1], axis[0]])
            s, t = (xy - mid) @ axis, (xy - mid) @ side
            lanes = max(1, math.ceil((t.max() - t.min()) / (2 * r) - 1e-9))
            offsets = t.min() + (t.max() - t.min()) * (np.arange(lanes) + 0.5) / lanes
            lane_of = np.argmin(np.abs(t[:, None] - offsets[None, :]), 1)
            out, made = [], 0
            for k in range(lanes):
                on = lane_of == k
                if not on.any():
                    continue
                give = np.sqrt(np.maximum(r * r - (t[on] - offsets[k]) ** 2, 0.0))
                a, b = float((s[on] + give).min()), float((s[on] - give).max())
                ends = [(a + b) / 2] if a >= b else [a, b]
                ends = ends if made % 2 == 0 else ends[::-1]
                made += 1
                out += [tuple(mid + e * axis + offsets[k] * side) for e in ends]
            if start and len(out) > 1 and math.hypot(out[-1][0] - start[0], out[-1][1] - start[1]) < \
                    math.hypot(out[0][0] - start[0], out[0][1] - start[1]):
                out.reverse()
            return [(float(p[0]), float(p[1]), self.height((float(p[0]), float(p[1])))) for p in out]
        long_way = np.linalg.svd(xy - mid, full_matrices=False)[2][0] if len(xy) > 1 else np.array([1.0, 0.0])
        turn = math.atan2(long_way[1], long_way[0])
        sweeps = [sweep_along(np.array([math.cos(turn + a), math.sin(turn + a)])) for a in np.arange(0, math.pi, math.pi / 4)]
        if stand is not None:
            sweeps = [sw for sw in sweeps if all(stand(p) for p in sw)]
        return sweeps

    def leg_near(self, a, b):
        import numpy as np
        za, zb = height_of(a), height_of(b)
        key = (a[0], a[1], za, b[0], b[1], zb)
        hit = self.legs_seen.get(key)
        if hit is None:
            xy, z = self.xy, self.z
            a2, b2 = np.asarray(a[:2], float), np.asarray(b[:2], float)
            ab = b2 - a2
            t = np.clip(((xy - a2) @ ab) / max(float(ab @ ab), 1e-9), 0, 1)
            d = np.hypot(*(xy - (a2 + t[:, None] * ab)).T)
            known = np.isfinite(z)
            if za is not None and zb is not None and known.any():
                p3, a3 = np.column_stack([xy, np.where(known, z, 0.0)]), np.array([a[0], a[1], za], float)
                ab3 = np.array([b[0], b[1], zb], float) - a3
                t3 = np.clip(((p3 - a3) @ ab3) / max(float(ab3 @ ab3), 1e-9), 0, 1)
                d = np.where(known, np.linalg.norm(p3 - (a3 + t3[:, None] * ab3), axis=1), d)
            hit = self.legs_seen[key] = d <= self.r + 1e-6
            hit.flags.writeable = False
        return hit

    def legs(self, route):
        return list(zip(route, route[1:])) + ([(route[-1], route[0])] if self.loop and len(route) > 2 else [])

    def covered(self, route):
        import numpy as np
        xy, r = self.xy, self.r
        if len(route) == 1:
            return bool((self.yards(route[0][0], route[0][1], height_or_nan(route[0])) <= r + 1e-6).all())
        near = np.zeros(len(xy), bool)
        for a, b in self.legs(route):
            near |= self.leg_near(a, b)
        return bool(near.all())

    def walk(self, route):
        start = self.start
        d = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in self.legs(route))
        return d + (math.hypot(route[0][0] - start[0], route[0][1] - start[1]) if start and not self.loop else 0.0)

    def empty(self, a, b):
        import numpy as np
        za, zb = height_of(a), height_of(b)
        key = ("empty", a[0], a[1], za, b[0], b[1], zb)
        hit = self.legs_seen.get(key)
        if hit is None:
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(length // 10))
            t = (np.arange(n) + 0.5) / n
            pts = np.stack([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], 1)
            d = np.hypot(pts[:, None, 0] - self.xy[None, :, 0], pts[:, None, 1] - self.xy[None, :, 1])
            if za is not None and zb is not None:
                dz = (za + (zb - za) * t)[:, None] - self.z[None, :]
                d = np.hypot(d, np.where(np.isfinite(dz), dz, 0.0))
            far = d.min(1) > self.r
            hit = self.legs_seen[key] = float(far.sum()) * length / n
        return hit

    def cost(self, route):
        return way_cost(route, self.start, self.loop, self.empty) if len(route) > 1 else self.walk(route)

    def polished(self, route):
        if len(route) <= 2:
            return route
        return polished(route, self.start, self.loop, lambda r: self.cost(r) if self.covered(r) else math.inf)

    def pruned(self, route):
        covered, walk = self.covered, self.walk
        while len(route) > 1:
            options = [k for k in range(len(route)) if covered(route[:k] + route[k + 1:])]
            if not options:
                break
            k = min(options, key=lambda k: walk(route[:k] + route[k + 1:]))
            route = route[:k] + route[k + 1:]
        return route

    def ordered(self, route):
        import numpy as np
        xy, loop, start, leg_near = self.xy, self.loop, self.start, self.leg_near
        n = len(route)
        if n < 2 or n > ORDER_ALL:
            return route
        mask = {}
        for i in range(n):
            for j in range(i + 1, n):
                mask[i, j] = mask[j, i] = sum(1 << int(k) for k in np.flatnonzero(leg_near(route[i], route[j])))
        full = (1 << len(xy)) - 1
        gap = [[math.hypot(p[0] - q[0], p[1] - q[1]) for q in route] for p in route]
        best = [math.inf, None]

        def go(order, d, got, left):
            if d >= best[0]:
                return
            if not left:
                if loop and n > 2:
                    d, got = d + gap[order[-1]][order[0]], got | mask[order[-1], order[0]]
                if got == full and d < best[0]:
                    c = self.cost([route[k] for k in order])
                    if c < best[0]:
                        best[:] = [c, order]
                return
            for k in left:
                go(order + (k,), d + gap[order[-1]][k], got | mask[order[-1], k], left - {k})
        for k in ([0] if loop else range(n)):
            go((k,), math.hypot(route[k][0] - start[0], route[k][1] - start[1]) if start and not loop else 0.0, 0,
               frozenset(range(n)) - {k})
        if best[1] is None:
            return route
        out = [route[k] for k in best[1]]
        if loop and start:
            k = min(range(n), key=lambda k: math.hypot(out[k][0] - start[0], out[k][1] - start[1]))
            out = out[k:] + out[:k]
        return out

    def tightened(self, route):
        import numpy as np
        xy, loop, stand, leg_near, walk, covered = self.xy, self.loop, self.stand, self.leg_near, self.walk, self.covered
        route = list(route)
        for step in TIGHTEN_STEPS:
            moved = True
            while moved:
                moved = False
                for i in range(len(route)):
                    n = len(route)
                    pairs = [(k, k + 1) for k in range(n - 1)] + ([(n - 1, 0)] if loop and n > 2 else [])
                    mine = [(a, b) for a, b in pairs if i in (a, b)]
                    rest = np.zeros(len(xy), bool)
                    for a, b in pairs:
                        if i not in (a, b):
                            rest |= leg_near(route[a], route[b])
                    here = walk(route)
                    if self.down(route[i]):
                        continue
                    for dx, dy in TIGHTEN_PULLS:
                        p = (route[i][0] + dx * step, route[i][1] + dy * step)
                        z = self.height(p)
                        p = (p[0], p[1], z if math.isfinite(z) else height_or_nan(route[i]))
                        if stand is not None and not stand(p):
                            continue
                        trial = route[:i] + [p] + route[i + 1:]
                        if walk(trial) >= here - 0.05:
                            continue
                        if n == 1:
                            ok = covered(trial)
                        else:
                            near = rest.copy()
                            for a, b in mine:
                                near |= leg_near(trial[a], trial[b])
                            ok = bool(near.all())
                        if ok:
                            route, here, moved = trial, walk(trial), True
            route = self.pruned(route)
        return route


def camp_timing(block):
    return sum(p[6] * p[11] for p in block), max(p[7] for p in block)


def camp_hourly(block):
    cycle = camp_cycle(block)
    return sum(p[8] * p[11] * min(1.0, cycle / p[7]) for p in block) * 3600 / cycle


def camp_cycle(block):
    return max(camp_timing(block)[0], statistics.median(p[7] for p in block), 1.0)


def camp_walked(figure, block, detour):
    cycle = camp_cycle(block)
    return figure * cycle / (cycle + max(0.0, detour))


def camp_spots(block):
    shares = {}
    for p in block:
        at = (round(float(p[0]), 1), round(float(p[1]), 1))
        shares[at] = shares.get(at, 0.0) + float(p[11])
    return [[n, w] if share >= SPOT_WHOLE else [n, w, round(share, 2)] for (n, w), share in sorted(shares.items())]


def camp_stops(block, start, line=False, stand_for=None, heights_for=None):
    heights = heights_for(block) if heights_for else None
    stops = cover_route(block, start, loop=not line, stand=stand_for(block) if stand_for else None, heights=heights)
    return stops or cover_route(block, start, loop=not line, heights=heights)


def camp_blocks(pts, near=None, danger=None, least=4, timing=None, walk_halves=CAMP_WALK, rate=None):
    import numpy as np
    cells = {}
    for p in pts:
        cells.setdefault((int(p[0] // CAMP_CELL), int(p[1] // CAMP_CELL)), []).append(p)

    def block_at(r, c, grow, kinds=None):
        block = [p for dr in range(-grow, grow + 1) for dc in range(-grow, grow + 1) for p in cells.get((r + dr, c + dc), [])
                 if kinds is None or (max(abs(dr), abs(dc)) <= CAMP_GROW[0]) or (len(p) > 10 and p[10] in kinds)]
        if len(block) < least:
            return None
        cn, cw = sum(p[0] for p in block) / len(block), sum(p[1] for p in block) / len(block)
        spread = max(np.hypot(p[0] - cn, p[1] - cw) for p in block)
        if danger is not None and len(danger) and (np.hypot(danger[:, 0] - cn, danger[:, 1] - cw) < spread + CAMP_CLEAR).any():
            return None
        return block, cn, cw

    out = []
    for (r, c) in cells:
        camp = block_at(r, c, CAMP_GROW[0])
        if not camp:
            continue
        worth = sum(p[2] for p in camp[0])
        if timing:
            lap, respawn = timing(camp[0])
            kinds = {p[10] for p in camp[0] if len(p) > 10} or None
            for grow in CAMP_GROW[1:]:
                bigger = lap < respawn * CAMP_MARGIN and block_at(r, c, grow, kinds)
                if not bigger:
                    break
                camp = bigger
                lap, respawn = timing(camp[0])
            worth *= min(1.0, lap / (respawn * CAMP_MARGIN))
        if rate:
            worth = rate(camp[0])
        walk = np.hypot(near[0] - camp[1], near[1] - camp[2]) if near else 0.0
        score = worth / (1 + walk / walk_halves)
        if score > 0:
            out.append((score, *camp))
    out.sort(key=lambda c: -c[0])
    return out


def camp_loop(pts, near=None, danger=None, least=4, timing=None, start=None, walk_halves=CAMP_WALK, line=False, stand_for=None,
              route=True, rate=None, heights_for=None):
    camps = camp_blocks(pts, near, danger, least, timing, walk_halves, rate)
    if not camps:
        return None
    score, block, cn, cw = camps[0]
    return block, cn, cw, camp_stops(block, start or near, line, stand_for, heights_for) if route else None, score


DROPS = os.path.join(ROOT, "data", "drops.json")


def load_drops(path=DROPS):
    d = store.load_json(path, {})
    d = d if isinstance(d, dict) else {}
    return {"tables": d.get("tables") or {}, "mobs": d.get("mobs") or {},
            "vendor": {int(k): v for k, v in (d.get("vendor") or {}).items()},
            "bound": {int(i) for i in d.get("bound") or ()},
            "ceiling": {int(k): v for k, v in (d.get("ceiling") or {}).items()}}


AH_CUT = 0.05
WORLD_DROP_WEIGHT = 0.5
RARE_DROP = 0.05
ITEM_SHARE_MOST = 0.5


def flat_drops(tables):
    memo = {}

    def flat(key, path=()):
        if key in memo:
            return memo[key]
        if key in path:
            return {}
        out = {}
        for what, n in tables.get(key, ()):
            if isinstance(what, str):
                for item, (own, ref) in flat(what, path + (key,)).items():
                    got = out.setdefault(item, [0.0, 0.0])
                    got[1] += n * (own + ref)
            else:
                out.setdefault(what, [0.0, 0.0])[0] += n
        memo[key] = out
        return out
    return flat


def item_price(item, drops, prices):
    vendor = drops["vendor"].get(item, 0)
    if item in drops["bound"] or not prices.get(item):
        return vendor, vendor
    house = min(prices[item], drops["ceiling"].get(item, math.inf)) * (1 - AH_CUT)
    return max(vendor, house), vendor + WORLD_DROP_WEIGHT * max(0.0, house - vendor)


def loot_parts(items, drops, prices, coin=0.0):
    parts, rare = {}, set()
    for item, (own, ref) in items.items():
        alone, shared = item_price(item, drops, prices)
        parts[item] = own * alone + ref * shared
        if own + ref < RARE_DROP:
            rare.add(item)
    most = (coin + sum(v for i, v in parts.items() if i not in rare)) * ITEM_SHARE_MOST / (1 - ITEM_SHARE_MOST)
    for item in rare:
        parts[item] = min(parts[item], most)
    return parts


def ah_worths(drops, prices, coins=None):
    flat = flat_drops(drops["tables"])
    worth = lambda key, coin=0.0: sum(loot_parts(flat(key), drops, prices, coin).values())
    return {mob: (worth(loot, (coins or {}).get(mob, 0.0)) if loot else None, worth(skin) if skin else 0.0)
            for mob, (loot, skin) in drops["mobs"].items()}


LEATHER_TABLES_LEAST = 2
LEATHER_CHANCE_LEAST = 0.1


def skin_loot(drops):
    flat = flat_drops(drops["tables"])
    return {mob: {item: own + ref for item, (own, ref) in flat(skin).items() if own + ref > 0}
            for mob, (_, skin) in drops["mobs"].items() if skin}


FARM_CHANCE_LEAST = 0.001


def drops_by_item(drops):
    flat = flat_drops(drops["tables"])
    out = {}
    for mob, (loot, skin) in drops["mobs"].items():
        got = {}
        for at, key in ((0, loot), (1, skin)):
            for item, (own, ref) in (flat(key).items() if key else ()):
                got.setdefault(item, [0.0, 0.0])[at] += own + ref
        for item, (kill, skinned) in got.items():
            if kill + skinned >= FARM_CHANCE_LEAST:
                out.setdefault(item, {})[mob] = (kill, skinned)
    return out


def item_worth(gives, skins):
    return gives[0] + (gives[1] if skins else 0.0)


SKINNABLE = 9


def with_skins(mobs, drops):
    out = dict(mobs)
    for mob, (_, skin) in drops["mobs"].items():
        row = out.get(mob)
        if skin and row is not None and len(row) > SKINNABLE and not row[SKINNABLE]:
            out[mob] = row[:SKINNABLE] + [1] + row[SKINNABLE + 1:]
    return out


def leather_kinds(drops, items):
    flat = flat_drops(drops["tables"])
    tables, best = {}, {}
    for key in {skin for _, skin in drops["mobs"].values() if skin}:
        for item, (own, ref) in flat(key).items():
            if own + ref > 0:
                tables[item] = tables.get(item, 0) + 1
                best[item] = max(best.get(item, 0.0), own + ref)
    out = {}
    for item, n in tables.items():
        row = items.get(str(item))
        if n >= LEATHER_TABLES_LEAST and best[item] >= LEATHER_CHANCE_LEAST and row and row[0]:
            out[item] = (row[0], (row[2] if len(row) > 2 else None) or "inv_misc_questionmark")
    return out


def leather_chance(by_mob, mob_id, leathers):
    mine = by_mob.get(str(mob_id), {})
    return sum(mine.get(i, 0.0) for i in leathers)


def item_table():
    import gamedata
    return gamedata.client_table("items.json", "items")[1]


def load_respawn_times():
    import numpy as np
    import datafiles
    try:
        d = datafiles.load(os.path.join(ROOT, "data", "respawns.json"), {})
        heights = {}
        for k, rows in d["spawns"].items():
            zs = d.get("heights", {}).get(k)
            if zs and len(zs) == len(rows):
                heights[k] = np.array([(r[0], r[1], r[2], z) for r, z in zip(rows, zs)], np.float32)
        return ({k: v[2] for k, v in d["npcs"].items() if v[2]}, {k: v for k, v in d.get("objects", {}).items() if v},
                {k: float(v[3]) for k, v in d["npcs"].items() if len(v) > 3}, heights)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return {}, {}, {}, {}


def load_quiet():
    import datafiles
    try:
        d = datafiles.load(os.path.join(ROOT, "data", "respawns.json"), {})
        return (dict(d.get("quiet") or {}), {k: [int(e) for e in v] for k, v in (d.get("events") or {}).items()},
                {int(k): v for k, v in (d.get("calendar") or {}).items()})
    except (OSError, ValueError, TypeError, AttributeError):
        return {}, {}, {}


SEASON_LEAST = 30 * 24 * 60
SCHEDULE_DATE, SCHEDULE_YEARLY = 1, 11


def event_on(calendar, event, now, depth=0):
    row = calendar.get(event)
    if not row or depth > 8:
        return False
    _, kind, start, end, every, length, linked = row
    if linked:
        return event_on(calendar, linked, now, depth + 1)
    if kind == SCHEDULE_DATE and every and every < SEASON_LEAST:
        return True
    if start is None or not every:
        return False
    if kind == SCHEDULE_DATE:
        return start < now < (math.inf if end is None else end) and (now - start) % (every * 60) < length * 60
    if kind == SCHEDULE_YEARLY:
        first = time.gmtime(start)
        for year in (time.gmtime(now).tm_year, time.gmtime(now).tm_year - 1):
            begun = calendar_time(year, first)
            if 0 <= now - begun < length * 60:
                return True
    return False


def calendar_time(year, first):
    import calendar as cal
    day = min(first.tm_mday, cal.monthrange(year, first.tm_mon)[1])
    return cal.timegm((year, first.tm_mon, day, first.tm_hour, first.tm_min, first.tm_sec))


def load_spawn_counts():
    import datafiles
    try:
        d = datafiles.load(os.path.join(ROOT, "data", "respawns.json"), {})
        return {k: len(rows) for k, rows in d["spawns"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def load_spawn_ups():
    import numpy as np
    import datafiles
    try:
        d = datafiles.load(os.path.join(ROOT, "data", "respawns.json"), {})
        out = {}
        for k, ups in (d.get("up") or {}).items():
            rows = d["spawns"].get(k) or ()
            if len(rows) == len(ups):
                out[k] = np.array([(r[0], r[1], r[2], u) for r, u in zip(rows, ups)], np.float32)
        return out
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return {}


def load_rare_ids():
    d = store.load_json(os.path.join(ROOT, "data", "rares.json"), {})
    try:
        return {str(r["id"]) for r in d.get("rares") or ()}
    except (TypeError, KeyError, AttributeError):
        return set()


ZONE_LEVEL_SPAWNS = 10
ZONE_LEVEL_REACH = 12
ZONE_LEVEL_CAMP = 40


def accumulate_counts(pairs):
    run = 0
    for v, n in pairs:
        run += n
        yield v, n, run


def lone_levels(rows):
    total = sum(n for _, _, n in rows)
    middle = next(v for v, n, run in accumulate_counts(sorted(((lo + hi) / 2, n) for lo, hi, n in rows)) if run * 2 >= total)
    return [(lo, hi, n) for lo, hi, n in rows if lo <= middle + ZONE_LEVEL_REACH and hi >= middle - ZONE_LEVEL_REACH]


POPULATED_CELL = 32.0
POPULATED_REACH = 120.0

CACHE_MOST = 32
CAMPS_KEPT = 64


PROFESSIONS = os.path.join(ROOT, "data", "professions.json")
ONE_NPC_YARDS = 20


def serves_none(sv):
    fr, en = sv.get("fr", 0), sv.get("en", 0)
    return all(en & (1 | bit) and not fr & (1 | bit) for bit in (facts.faction_bit("Alliance"), facts.faction_bit("Horde")))


def with_trainers(services, profs, geo):
    names = {p: (v.get("n") or "").lower().replace(" ", "") for p, v in (profs.get("professions") or {}).items()}
    crafts = {c for sv in services for c, _ in sv.get("cats") or ()}
    known = {sv["id"] for sv in services}
    by_name = {}
    for sv in services:
        by_name.setdefault(sv["n"], []).append(sv)

    def at(area, p):
        w = geo.area_to_world(area, p[0], p[1])
        return (w[2], w[0], w[1]) if w else None

    def twin(t):
        here = [at(a, p) for a, pts in t["s"].items() for p in pts]
        there = [at(a, q) for sv in by_name.get(t["n"], ()) for a, pts in sv["s"].items() if a in t["s"] for q in pts]
        here, there = [h for h in here if h], [o for o in there if o]
        return any(h[0] == o[0] and math.hypot(h[1] - o[1], h[2] - o[2]) < ONE_NPC_YARDS for h in here for o in there)

    out = list(services)
    for npc, t in (profs.get("trainers") or {}).items():
        cat = names.get(str(t.get("prof")))
        if int(npc) in known or cat not in crafts or not t.get("s") or "fr" not in t or serves_none(t) or twin(t):
            continue
        out.append({"id": int(npc), "n": t["n"], "sub": t.get("sub") or "", "cats": [[cat, None]], "fr": t["fr"],
                    "en": t.get("en", 0), "s": t["s"], "z": None})
        known.add(int(npc))
    return out


def service_names(services):
    return sorted({sv["n"] for sv in services if sv.get("n") and int(sv.get("id") or 0) > 0})


def lay_gathered(world, seen):
    return start_thread("gathered", lambda: world.apply_gathered(seen()), again=True)


class WorldLayers:
    def __init__(self):
        import datafiles
        path = os.path.join(ROOT, "data", "world.json")
        self.ok = os.path.exists(path)
        data = datafiles.load(path, {})
        self.mobs, self.spawns, self.nodes = data.get("mobs", {}), data.get("mobSpawns", {}), data.get("nodes", {})
        self.nodes_est, self.nodes_version = self.nodes, 0
        self.nodes_full, self.emptied = self.nodes, lambda: ()
        self.geo = MapGeometry()
        self.services = with_trainers(data.get("services", []), datafiles.load(PROFESSIONS, {}), self.geo)
        self.trainer_levels = data.get("trainerLevels", {})
        self.trainer_costs = data.get("trainerCosts", {})
        self.entrances = data.get("entrances", [])
        self.sources = data.get("sources", {})
        self.detection_usual = data.get("detectionUsual")
        self.cache = {}
        both = load_patrols(shares=True)
        self.patrols = {c: [r[:2] for r in rs] for c, rs in both.items()}
        self.patrol_shares = {c: [r[2] for r in rs] for c, rs in both.items()}
        self.walks_kept = None
        self.cities = None
        self.escorts = store.load_json(os.path.join(ROOT, "data", "escorts.json"), {}).get("escorts", {})
        self.giver_walks = load_giver_walks()
        self.populated_cache = {}
        self.xp = XpMeasure()
        self.pace = PaceMeasure()
        self.respawn_npcs, self.respawn_objects, self.wander, self.spawn_heights = load_respawn_times()
        self.quiet, self.event_only, self.calendar = load_quiet()
        self.event_ids = sorted({e for evs in self.event_only.values() for e in evs})
        self.clock = time.time
        self.events_off, self.on_events = None, None
        self.measured_respawn = lambda npc: None
        self.respawns_version = lambda: 0
        self.level_cap = lambda: MAX_LEVEL
        self.stand_at = None
        self.stand_heights = None
        self.drops = load_drops()
        self.mobs = with_skins(self.mobs, self.drops)
        self.ah_prices = lambda: (None, {})
        self.ah_kept = None
        self.vendor_kept = None
        self.item_table = item_table
        self.leathers_kept = None
        self.item_drops_kept = None
        self.camps_kept = {}
        self.rare_ids = load_rare_ids()
        self.spawn_counts = load_spawn_counts()
        self.spawn_ups = load_spawn_ups()
        import threading
        self.gathered_lock = threading.Lock()

    def keep(self, key, out):
        return kept.keep(self.cache, key, out, CACHE_MOST)

    def ah_book(self):
        stamp, prices = self.ah_prices()
        got = self.ah_kept
        if got is None or got[0] != stamp:
            got = self.ah_kept = (stamp, ah_worths(self.drops, prices, self.coins()))
        return got

    def vendor_book(self):
        got = self.vendor_kept
        if got is None or got[0] is not self.drops:
            got = self.vendor_kept = (self.drops, ah_worths(self.drops, {}, self.coins()))
        return got[1]

    def coins(self):
        return {k: m[7] for k, m in self.mobs.items()}

    def leathers(self):
        table = self.item_table()
        got = self.leathers_kept
        if got is None or got[0] is not self.drops or got[1] is not table:
            kinds = leather_kinds(self.drops, table)
            by_mob = {}
            for mob, items in skin_loot(self.drops).items():
                mine = {i: c for i, c in items.items() if i in kinds}
                if mine:
                    by_mob[mob] = mine
            got = self.leathers_kept = (self.drops, table, (kinds, by_mob))
        return got[2]

    def item_drops(self):
        got = self.item_drops_kept
        if got is None or got[0] is not self.drops:
            got = self.item_drops_kept = (self.drops, drops_by_item(self.drops))
        return got[1]

    def skin_kinds(self):
        return {name: {"id": item, "icon": icon} for item, (name, icon) in sorted(self.leathers()[0].items())}

    @staticmethod
    def kill_worth(mob_id, m, book=None, skinning=0, any_level=False):
        coin, loot = m[7], m[8]
        if book is None:
            return coin + loot
        got, skin = book.get(str(mob_id), (None, 0.0))
        worth = coin + (loot if got is None else got)
        if skinning and m[9] and (any_level or skinning_needed(m[2]) <= skinning):
            worth += skin
        return worth

    def populated(self, instance):
        if instance in self.populated_cache:
            return self.populated_cache[instance]
        import numpy as np
        from scipy.ndimage import binary_dilation
        pts = [at[:2] for spots in self.mob_spots().values() for at, _ in spots if at[2] == instance]
        if not pts:
            self.populated_cache[instance] = None
            return None
        a = np.array(pts, float)
        reach = int(POPULATED_REACH // POPULATED_CELL) + 1
        top, left = a[:, 0].max() + reach * POPULATED_CELL, a[:, 1].max() + reach * POPULATED_CELL
        rows = ((top - a[:, 0]) // POPULATED_CELL).astype(int)
        cols = ((left - a[:, 1]) // POPULATED_CELL).astype(int)
        grid = np.zeros((rows.max() + reach + 1, cols.max() + reach + 1), bool)
        grid[rows, cols] = True
        yy, xx = np.ogrid[-reach:reach + 1, -reach:reach + 1]
        grid = binary_dilation(grid, structure=(xx * xx + yy * yy) * POPULATED_CELL ** 2 <= POPULATED_REACH ** 2)
        self.populated_cache[instance] = (top, left, POPULATED_CELL, grid)
        return self.populated_cache[instance]

    def on_map(self, spawns, map_id):
        return [p for area, pts in spawns.items() for p in self.geo.project(area, pts, map_id, MARGIN)]

    def pois(self, map_id, faction, game_entrances=None, journal=None):
        faction_bit = facts.faction_bit(faction)
        out, from_game = [], set()
        for e in game_entrances or []:
            cat = "raid" if e["raid"] else "dungeon"
            from_game.add(e["name"].lower().removeprefix("the "))
            out.append({"cat": cat, "detail": None, "name": e["name"], "sub": f"{cat.title()} entrance, from the game",
                        "x": e["x"], "y": e["y"]})
        for e in self.entrances:
            if e["faction"] and faction and e["faction"] != faction:
                continue
            if e["n"].lower().removeprefix("the ") in from_game:
                continue
            sub = journal.entrance_words(e["n"], e["kind"]) if journal else e["kind"].title()
            for x, y in self.on_map(e["s"], map_id):
                out.append({"cat": e["kind"], "detail": None, "name": e["n"], "sub": sub, "x": x, "y": y})
        if journal:
            for w in journal.ways_in_beside([e["n"] for e in self.entrances]):
                if w["name"].lower().removeprefix("the ") in from_game:
                    continue
                for x, y in self.geo.project_from(w["map"], [(w["x"], w["y"])], map_id, MARGIN):
                    out.append({"cat": w["kind"], "detail": None, "name": w["name"], "sub": w["sub"], "x": x, "y": y,
                                **({"described": True} if w["described"] else {})})
        for sv in self.services:
            foe, side = attacks(sv, faction_bit), npc_side(sv)
            pts = self.on_map(sv["s"], map_id)
            for cat, detail in sv["cats"]:
                out.extend({"cat": cat, "detail": detail, "name": sv["n"], "sub": sv["sub"], "x": x, "y": y, "z": sv.get("z"),
                            **({"side": side} if side else {}), **({"foe": True} if foe else {})}
                           for x, y in pts)
        return {"map": map_id, "pois": out}

    def walking(self):
        got = getattr(self, "walks_kept", None)
        if got is None or got[0] is not self.services or got[1] is not self.patrols:
            got = self.walks_kept = (self.services, self.patrols, walks(self.services, self.patrols, self.geo))
        return got[2]

    def set_cities(self, capitals, cities_at):
        import struct
        import numpy as np
        services, by_inst = self.services, {}
        for sv in services:
            for area, pts in sv["s"].items():
                for x, y in pts:
                    w = self.geo.area_to_world(area, x, y)
                    if w:
                        by_inst.setdefault(w[2], []).append(((sv.get("id"), w[2], w[0], w[1]), sv.get("z")))
        found = {}
        for inst, group in by_inst.items():
            z = np.array([np.nan if h is None else h for _, h in group], np.float64)
            try:
                got = cities_at(inst, np.array([k[2] for k, _ in group], np.float64),
                                np.array([k[3] for k, _ in group], np.float64), z)
            except (OSError, ValueError, KeyError, struct.error):
                continue
            if got is not None:
                found.update({k: int(c) for (k, _), c in zip(group, got.tolist()) if c})
        self.cities = (services, capitals, found, {})

    def walled(self, faction):
        got = getattr(self, "cities", None)
        if got is None or got[0] is not self.services:
            return frozenset()
        if faction not in got[3]:
            enemy = got[1].enemy(faction)
            got[3][faction] = frozenset(k for k, city in got[2].items() if city in enemy)
        return got[3][faction]

    def nearest(self, map_id, fx, fy, faction, cats, items=(), ammo=None, detail=None, goods=()):
        here = self.geo.to_world(map_id, fx, fy)
        if not here:
            return None
        px, py, instance = here
        want, ids = set(items or ()), list(goods or ())

        def keep(sv, kind):
            if want and not want & set(sv.get("sells") or ()):
                return False
            if ids and not sells(sv, ids):
                return False
            return not (kind == "ammo" and ammo and not sells_ammo(sv.get("sub") or "", ammo))
        best, least = None, math.inf
        pool = sellers_of(self.services, ids[0]) if ids else self.services
        for sv, kind, spots in serving(pool, self.geo, faction, None if want or ids else cats, detail, keep,
                                       self.walking(), self.walled(faction)):
            for north, west, inst, area in spots:
                yards = math.hypot(north - px, west - py)
                if inst == instance and yards < least:
                    least, zone = yards, self.geo.maps[self.geo.area_map[str(area)]]["name"]
                    best = {"name": sv["n"], "sub": sv["sub"], "cat": kind, "zone": zone,
                            "wx": north, "wy": west, "wz": sv.get("z"), "yards": round(yards)}
        return best

    def service(self, who):
        if isinstance(who, int):
            return next((sv for sv in self.services if sv.get("id") == who), None)
        return next((sv for sv in self.services if who and sv.get("n") == who), None)

    def service_zone(self, sv):
        for area in (sv or {}).get("s") or {}:
            if str(area) in self.geo.area_map:
                return self.geo.maps[self.geo.area_map[str(area)]]["name"]
        return None

    def nearest_entrance(self, map_id, fx, fy, faction, kinds, journal=None):
        here = self.geo.to_world(map_id, fx, fy)
        if not here:
            return None
        px, py, instance = here
        spots = []
        for e in self.entrances:
            if e["kind"] not in kinds or (e["faction"] and faction and e["faction"] != faction):
                continue
            sub = journal.entrance_words(e["n"], e["kind"]) if journal else e["kind"].title()
            spots += [(e["n"], e["kind"], sub, self.geo.area_map.get(str(area)), x, y) for area, pts in e["s"].items() for x, y in pts]
        if journal:
            spots += [(w["name"], w["kind"], w["sub"], w["map"], w["x"], w["y"])
                      for w in journal.ways_in_beside([e["n"] for e in self.entrances]) if w["kind"] in kinds]
        best, least = None, math.inf
        for name, kind, sub, at_map, x, y in spots:
            at = self.geo.to_world(at_map, x / 100, y / 100)
            if not at or at[2] != instance:
                continue
            yards = math.hypot(at[0] - px, at[1] - py)
            if yards < least:
                least = yards
                best = {"name": name, "sub": sub, "cat": kind, "zone": self.geo.maps[at_map]["name"],
                        "wx": at[0], "wy": at[1], "wz": None, "yards": round(yards)}
        return best

    def off_events(self):
        now = self.clock()
        off = frozenset(e for e in self.event_ids if not event_on(self.calendar, e, now))
        was, self.events_off = self.events_off, off
        if was is not None and was != off:
            self.cache.clear()
            if self.on_events:
                self.on_events()
        return off

    def fightable(self, mob_id, off):
        quiet, events = self.quiet.get(mob_id), self.event_only.get(mob_id)
        side = quiet == "passive" and (self.mobs.get(mob_id) or [0] * 7)[6] & sum(facts.FACTION_BITS.values())
        return quiet not in ("unseen", "immune", "civilian") and not side and not (events and off.issuperset(events))

    def threats(self, instance, level, faction, fight=False, want=()):
        import numpy as np
        want = {str(i) for i in want}
        cap = self.level_cap()
        off = self.off_events()
        key = ("threats", instance, level, faction, fight, (), cap, tuple(sorted(off)))
        if not want:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        parts = self.threat_parts(instance, level, faction, fight, cap, off)
        if not want:
            return self.keep(key, np.concatenate([p[1] for p in parts if p[1] is not None] or [np.zeros((0, 5), np.float32)]))
        got = [p[2] if p[0] in want else p[1] for p in parts]
        return np.concatenate([g for g in got if g is not None] or [np.zeros((0, 5), np.float32)])

    def threat_parts(self, instance, level, faction, fight, cap, off):
        import numpy as np
        key = ("threat parts", instance, level, faction, fight, cap, tuple(sorted(off)))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        rows_of = lambda rows: np.array(rows, np.float32).reshape(-1, 5) if rows else None
        faction_bit = facts.faction_bit(faction)
        parts = []
        for mob_id, m in self.mobs.items():
            lo, hi, rank, friend = m[1], m[2], m[3], m[6]
            enemy = m[11] if len(m) > 11 else 1
            if friend & (1 | faction_bit) or hi <= gray_level(level):
                continue
            if not self.fightable(mob_id, off):
                continue
            hostile = bool(enemy & (1 | faction_bit)) and self.quiet.get(mob_id) != "passive"
            mob_level = (lo + hi) / 2
            radius = min(max(self.aggro(m) + mob_level - level, AGGRO_RANGE[0]), AGGRO_RANGE[1])
            worth = rank not in ELITE_RANKS and fights_from(mob_level) <= level
            spots = [s for s in self.mob_spots().get(mob_id, ()) if s[0][2] == instance]
            wanted = rows_of([(at[0], at[1], radius, -1.0 * share, math.nan) for at, share in spots]) if fight and worth else None
            if fight and worth:
                weight = -min(1.5, max(0.2, kill_xp(level, mob_level, cap) / max(1, kill_xp(level, level, cap))))
            elif hostile:
                weight = (3.0 if rank in (1, 2, 3) else 1.0) * (1 + max(0.0, mob_level - level) / 3)
            else:
                continue
            rows = []
            reach = radius + (self.wander.get(mob_id, WANDER_UNKNOWN) if weight > 0 else 0.0)
            zs = self.spot_heights(mob_id, instance, [at for at, _ in spots]) if weight > 0 else [math.nan] * len(spots)
            rows += [(at[0], at[1], reach, weight * share, z) for (at, share), z in zip(spots, zs)]
            if weight > 0:
                share = weight * min(1.0, PATROL_STEP / (2 * radius))
                shares = getattr(self, "patrol_shares", {}).get(mob_id) or ()
                for k, (inst, route) in enumerate(self.patrols.get(mob_id, ())):
                    if inst == instance:
                        mark = share * (shares[k] if k < len(shares) else 1.0)
                        rows += [(float(x), float(y), radius, mark, math.nan) for x, y in along(route, PATROL_STEP)]
            if rows or wanted is not None:
                parts.append((mob_id, rows_of(rows), wanted))
        return self.keep(key, parts)

    def aggro(self, mob):
        detect = (mob[MOB_DETECTION] if len(mob) > MOB_DETECTION else None) or self.detection_usual
        return detect + AGGRO_MARGIN if detect else AGGRO

    def mob_spots(self):
        table = getattr(self, "_mob_spots", None)
        pooled = getattr(self, "spawn_ups", None)
        if table is None or table[0] is not self.spawns or table[1] is not pooled:
            spots = {mob: [(at, self.spot_share(area, x, y)) for area, pts in areas.items() for x, y in pts
                           for at in [self.geo.area_to_world(area, x, y)] if at]
                     for mob, areas in self.spawns.items()}
            for mob in pooled or ():
                if spots.get(mob):
                    ups = self.pool_ups(mob, [at for at, _ in spots[mob]])
                    spots[mob] = [(at, share * up) for (at, share), up in zip(spots[mob], ups)]
            table = (self.spawns, pooled, spots)
            self._mob_spots = table
        return table[2]

    def pool_ups(self, mob_id, spots):
        import numpy as np
        have = getattr(self, "spawn_ups", {}).get(str(mob_id))
        if have is None or not spots:
            return [1.0] * len(spots)
        out = []
        for inst in {s[2] for s in spots}:
            here = have[have[:, 0] == inst]
            if not len(here):
                continue
            idx = [i for i, s in enumerate(spots) if s[2] == inst]
            p = np.array([(spots[i][0], spots[i][1]) for i in idx], np.float32)
            d = np.hypot(p[:, None, 0] - here[None, :, 1], p[:, None, 1] - here[None, :, 2])
            k = d.argmin(1)
            out += [(i, float(here[j, 3])) for i, j, near in zip(idx, k, d[np.arange(len(idx)), k] <= POOL_MATCH) if near]
        ups = [1.0] * len(spots)
        for i, up in out:
            ups[i] = up
        return ups

    def spot_share(self, area, x, y):
        have = getattr(self, "_spot_counts", None)
        if have is None or have[0] is not self.spawns:
            counts = {}
            for areas in self.spawns.values():
                for a, pts in areas.items():
                    for px, py in pts:
                        counts[(str(a), px, py)] = counts.get((str(a), px, py), 0) + 1
            have = self._spot_counts = (self.spawns, counts)
        return 1.0 / have[1].get((str(area), x, y), 1)

    def spot_heights(self, mob_id, instance, spots):
        import numpy as np
        have = self.spawn_heights.get(mob_id)
        here = have[have[:, 0] == instance] if have is not None else ()
        if not spots or not len(here):
            return [math.nan] * len(spots)
        p = np.array([(a[0], a[1]) for a in spots], np.float32)
        d = np.hypot(p[:, None, 0] - here[None, :, 1], p[:, None, 1] - here[None, :, 2])
        k = d.argmin(1)
        return [float(here[j, 3]) if d[i, j] <= HEIGHT_MATCH else math.nan for i, j in enumerate(k)]

    def block_heights(self, instance, block):
        out = [math.nan] * len(block)
        for mob in {p[10] for p in block if len(p) > 10}:
            ks = [k for k, p in enumerate(block) if len(p) > 10 and p[10] == mob]
            for k, z in zip(ks, self.spot_heights(str(mob), instance, [(block[k][0], block[k][1]) for k in ks])):
                out[k] = z
        return out

    def typical_health(self, level):
        if not hasattr(self, "_health"):
            by_level = {}
            for m in self.mobs.values():
                lo, hi, rank, hp_lo, hp_hi = m[1], m[2], m[3], m[4], m[5]
                if rank == 0 and lo == hi and hp_lo > 0:
                    by_level.setdefault(lo, []).append((hp_lo + hp_hi) / 2)
            self._health = {lvl: sorted(v)[len(v) // 2] for lvl, v in by_level.items() if len(v) >= 3}
        if not self._health:
            return 100.0
        near = min(self._health, key=lambda lvl: abs(lvl - level))
        return self._health[near]

    def kill_seconds(self, level, health):
        return (KILL_SECONDS * health / self.typical_health(level) + KILL_OVERHEAD) * self.pace.factor()

    def kills_per_hour(self, level, health):
        return 3600.0 / self.kill_seconds(level, health)

    def node_respawns(self, layer):
        nodes = self.nodes.get(layer, [])
        by_name = {}
        for node in sorted(nodes, key=lambda n: -sum(len(p) for p in n["s"].values())):
            if self.respawn_objects.get(str(node["id"])):
                by_name.setdefault(node["n"], self.respawn_objects[str(node["id"])])
        return {node["id"]: self.respawn_objects.get(str(node["id"])) or by_name.get(node["n"]) or RESPAWN_FALLBACK
                for node in nodes}

    def zone_scores(self, instance, level, faction, all_levels=False, skin=0, ah=False, skinning=0, leathers=()):
        book = self.ah_book() if ah else None
        leathers, off = tuple(sorted(leathers)), self.off_events()
        key = ("zones", instance, level, faction, self.xp.version, self.pace.version, self.pace.current, all_levels, skin,
               book and book[0], ah, skinning, self.level_cap(), leathers, tuple(sorted(off)))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        zones = {int(z) for z, zm in self.geo.maps.items()
                 if zm.get("instance") == instance and zm.get("type") == 3 and zm.get("world")}
        best, faction_bit = {}, facts.faction_bit(faction)
        by_mob = self.leathers()[1]
        for mob_id, m in self.mobs.items():
            if m[6] & faction_bit or m[3] in ELITE_RANKS or not (skin and m[9] and skinning_needed(m[2]) <= skin):
                continue
            if not self.fightable(mob_id, off):
                continue
            if leathers and not any(i in by_mob.get(mob_id, {}) for i in leathers):
                continue
            raises = skin_up(skin, skinning_needed(m[2])) > 0
            for area, pts in self.spawns.get(mob_id, {}).items():
                zone = self.geo.area_map.get(str(area))
                if zone in zones:
                    b = best.setdefault(zone, [0.0, 0.0, 0, 0])
                    b[2] += len(pts)
                    b[3] += len(pts) if raises else 0
        danger = self.threats(instance, level, faction, fight=True)
        danger = danger[danger[:, 3] > 0]
        for at, gold in ((0, False), (1, True)):
            plan = all_levels and gold
            rows = self.camp_rows(zones, level, faction, gold, plan, book=(book[1] if book else self.vendor_book()) if gold else None,
                                  skinning=skinning).get(instance, [])
            by_zone = {}
            for p in rows:
                by_zone.setdefault(p[9], []).append(p)
            for zone, pts in by_zone.items():
                camp = camp_loop(pts, None, None if plan else danger, timing=camp_timing, route=False, rate=camp_hourly)
                if camp:
                    best.setdefault(zone, [0.0, 0.0, 0, 0])[at] = camp[4]
        return self.keep(key, [{**self.zone_box(zone), "xp": round(xph), "gold": round(gph), "skin": n, "skinUp": up}
                               for zone, (xph, gph, n, up) in best.items()])

    def zone_leathers(self, instance, faction):
        off = self.off_events()
        key = ("leatherzones", instance, faction, tuple(sorted(off)))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        zones = {int(z) for z, zm in self.geo.maps.items()
                 if zm.get("instance") == instance and zm.get("type") == 3 and zm.get("world")}
        (named, by_mob), faction_bit, kinds = self.leathers(), facts.faction_bit(faction), {}
        for mob_id, m in self.mobs.items():
            mine = by_mob.get(mob_id)
            if m[6] & faction_bit or m[3] in ELITE_RANKS or not m[9] or not mine or not self.fightable(mob_id, off):
                continue
            needed = skinning_needed(m[2])
            for area, pts in self.spawns.get(mob_id, {}).items():
                zone = self.geo.area_map.get(str(area))
                if zone in zones:
                    for item in mine:
                        k = kinds.setdefault(zone, {}).setdefault(named[item][0], [0, needed])
                        k[0] += len(pts)
                        k[1] = min(k[1], needed)
        return self.keep(key, [{"map": zone, "leathers": got} for zone, got in sorted(kinds.items())])

    def zone_levels(self, skip=()):
        key = ("zonelevels", tuple(sorted(skip)))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        spawns = {}
        for mob_id, m in self.mobs.items():
            lo, hi, rank, friend = m[1], m[2], m[3], m[6]
            if rank != 0 or friend & 1 or (friend & 6) == 6:
                continue
            for area, pts in self.spawns.get(mob_id, {}).items():
                zone = self.geo.area_map.get(str(area))
                if zone is None or zone in skip or (self.geo.maps.get(zone) or {}).get("type") != 3:
                    continue
                spawns.setdefault(zone, []).append((lo, hi, len(pts)))
        out = {}
        for zone, rows in spawns.items():
            total = sum(n for _, _, n in rows)
            if total < ZONE_LEVEL_SPAWNS:
                continue
            rows = lone_levels(rows)
            total = sum(n for _, _, n in rows)
            nth = lambda values, q: next(v for v, n, run in accumulate_counts(values) if run > q * total)
            at = {}
            for lo, _, n in rows:
                at[lo] = at.get(lo, 0) + n
            camp = min((lv for lv, n in at.items() if n >= ZONE_LEVEL_CAMP), default=math.inf)
            low = min(nth(sorted(at.items()), 0.05), camp)
            out[zone] = (low, nth(sorted((hi, n) for _, hi, n in rows), 0.90))
        return self.keep(key, out)

    def zone_box(self, zone):
        m = self.geo.maps[zone]
        w = m["world"]
        return {"map": zone, "name": m.get("name"), "n": round((w["top"] + w["bottom"]) / 2, 1), "w": round((w["left"] + w["right"]) / 2, 1),
                "rn": round(abs(w["top"] - w["bottom"]) / 2, 1), "rw": round(abs(w["left"] - w["right"]) / 2, 1)}

    def zone_nodes(self, instance):
        key = ("nodezones", instance, self.nodes_version)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        counts, spots_of = {}, {}
        for layer, nodes in self.nodes.items():
            for node in nodes:
                for area, spots in node["s"].items():
                    zone = self.geo.area_map.get(str(area))
                    zm = self.geo.maps.get(zone) or {}
                    if zm.get("instance") != instance or zm.get("type") != 3 or not zm.get("world"):
                        continue
                    have = counts.setdefault(zone, {}).setdefault(layer, {})
                    odds = (node.get("o") or {}).get(area) or [(1.0, 1.0)] * len(spots)
                    have[node["n"]] = have.get(node["n"], 0.0) + sum(c * u for c, u in odds)
                    seen = spots_of.setdefault(zone, {}).setdefault(layer, {})
                    seen[node["n"]] = seen.get(node["n"], 0) + len(spots)
        return self.keep(key, [{**self.zone_box(zone), "nodes": {layer: {name: round(v, 2) for name, v in named.items()}
                                                                 for layer, named in nodes.items()},
                                "spots": spots_of.get(zone, {})} for zone, nodes in counts.items()])

    def apply_gathered(self, seen):
        with self.gathered_lock:
            full = self._apply_gathered(seen)
            nodes = self.without_emptied(full, set(getattr(self, "emptied", lambda: ())() or ()))
            self.nodes_full, self.nodes = full, nodes
            self.nodes_version += 1
            self.cache.clear()

    def _apply_gathered(self, seen):
        import numpy as np
        from scipy.spatial import cKDTree
        table = {layer: [{**node, "s": {a: [list(p) for p in pts] for a, pts in node["s"].items()},
                          "o": {a: [list(v) for v in odds] for a, odds in (node.get("o") or {}).items()}} for node in nodes]
                 for layer, nodes in self.nodes_est.items()}
        by_name = {}
        for nodes in table.values():
            for node in nodes:
                by_name.setdefault(node["n"], []).append(node)
        index = {}
        for nodes in table.values():
            for node in nodes:
                for area, pts in node["s"].items():
                    for i, (x, y) in enumerate(pts):
                        at = self.geo.area_to_world(area, x, y)
                        if at:
                            index.setdefault(at[2], []).append((at[0], at[1], node, area, i))
        trees = {inst: cKDTree(np.array([e[:2] for e in es])) for inst, es in index.items()}
        spots = {}
        for o in seen:
            if o["name"] not in by_name:
                continue
            tree, es = trees.get(o["inst"]), index.get(o["inst"], [])
            d, k = tree.query((o["n"], o["w"])) if tree is not None else (np.inf, None)
            if d <= GATHERED_NEAR:
                key = (o["inst"], es[k][0], es[k][1])
            else:
                key = next((s for s in spots if s[0] == o["inst"] and (s[1] - o["n"]) ** 2 + (s[2] - o["w"]) ** 2 <= GATHERED_NEAR ** 2),
                           (o["inst"], float(o["n"]), float(o["w"])))
            count = spots.setdefault(key, {})
            count[o["name"]] = count.get(o["name"], 0) + 1
        for (inst, n, w), count in spots.items():
            tree, es = trees.get(inst), index.get(inst, [])
            stack = [es[k] for k in tree.query_ball_point((n, w), GATHERED_STACK)] if tree is not None else []
            have = {e[2]["n"]: e for e in stack}
            ups = [e[2]["o"].get(e[3], [])[e[4]][1] for e in stack if e[4] < len(e[2]["o"].get(e[3], []))]
            up = ups[0] if ups else GATHERED_UP
            total = sum(count.values())
            home = (stack[0][3], *stack[0][2]["s"][stack[0][3]][stack[0][4]]) if stack else self.zone_point(inst, n, w)
            for name in set(have) | set(count):
                e = have.get(name)
                est = self.spot_odds(e[2], e[3], e[4])[0] if e else 0.0
                chance = round((count.get(name, 0) + GATHERED_PRIOR * est) / (total + GATHERED_PRIOR), 3)
                if e:
                    self.set_spot_odds(e[2], e[3], e[4], chance, up)
                elif home:
                    named = [e for e in index.get(inst, []) if e[2]["n"] == name]
                    near = min(named, key=lambda e: (e[0] - n) ** 2 + (e[1] - w) ** 2) if named else None
                    node, (area, x, y) = near[2] if near else by_name[name][0], home
                    node["s"].setdefault(area, []).append([x, y])
                    self.set_spot_odds(node, area, len(node["s"][area]) - 1, chance, up)
        return table

    def spot_key(self, layer, area, x, y):
        at = self.geo.area_to_world(area, x, y)
        return (layer, at[2], round(at[0], 1), round(at[1], 1)) if at else None

    def without_emptied(self, table, emptied):
        if not emptied:
            return table
        out = dict(table)
        for layer in {e[0] for e in emptied} & set(table):
            nodes = []
            for node in table[layer]:
                spots, odds = {}, {}
                for area, pts in node["s"].items():
                    there = (node.get("o") or {}).get(area)
                    keep = [i for i, (x, y) in enumerate(pts) if self.spot_key(layer, area, x, y) not in emptied]
                    if keep:
                        spots[area] = [pts[i] for i in keep]
                        if there is not None:
                            odds[area] = [there[i] for i in keep if i < len(there)]
                nodes.append({**node, "s": spots, "o": odds} if "o" in node else {**node, "s": spots})
            out[layer] = nodes
        return out

    @staticmethod
    def spot_odds(node, area, i):
        odds = (node.get("o") or {}).get(area) or []
        return tuple(odds[i]) if i < len(odds) and odds[i] else (1.0, 1.0)

    @staticmethod
    def set_spot_odds(node, area, i, chance, up):
        odds = node.setdefault("o", {}).setdefault(area, [])
        while len(odds) <= i:
            odds.append([1.0, 1.0])
        odds[i] = [chance, up]

    def zone_point(self, inst, n, w):
        best = None
        for m in self.geo.maps.values():
            b = m.get("world")
            if m.get("type") != 3 or m.get("instance") != inst or not b or not m.get("area"):
                continue
            if b["bottom"] <= n <= b["top"] and b["right"] <= w <= b["left"]:
                size = (b["top"] - b["bottom"]) * (b["left"] - b["right"])
                if best is None or size < best[0]:
                    x, y = to_map(b, n, w)
                    best = (size, str(m["area"]), round(x * 100, 2), round(y * 100, 2))
        return best[1:] if best else None

    def node_kinds(self):
        out = {}
        for layer, nodes in self.nodes.items():
            for node in nodes:
                out.setdefault(layer, {}).setdefault(node["n"], {"skill": node.get("skill", 0), "icon": node.get("icon")})
        return out

    def zone_spots(self, spawns, maps, odds=None, shared=False):
        for area, spots in spawns.items():
            zone = self.geo.area_map.get(str(area))
            if zone in maps:
                there = (odds or {}).get(area) or ()
                for i, (x, y) in enumerate(spots):
                    at = self.geo.area_to_world(area, x, y)
                    if not at:
                        continue
                    if odds is None:
                        yield (at[0], at[1], at[2], zone, self.spot_share(area, x, y)) if shared else (at[0], at[1], at[2], zone)
                    else:
                        chance, up = there[i] if i < len(there) and there[i] else (1.0, 1.0)
                        yield at[0], at[1], at[2], zone, chance, up

    def grind_loop(self, maps, level, faction, near=None, gold=False, near_inst=None, all_levels=False, aoe=0, skin=0,
                   ah=False, skinning=0, leathers=(), walk=None, until=None, item=None):
        from loopsearch import Camp, Walked, best_loop
        import farmspots
        maps = {int(m) for m in (maps if isinstance(maps, (list, tuple, set)) else [maps])}
        if item is not None:
            gold, skin, aoe, all_levels = False, 0, 0, False
        skin = 0 if gold else max(0, int(skin or 0))
        all_levels = all_levels and bool(gold or skin)
        aoe = 0 if gold or skin else max(0, int(aoe or 0))
        book = (self.ah_book()[1] if ah else self.vendor_book()) if gold else None
        by_inst = self.camp_rows(maps, level, faction, gold, all_levels, aoe, skin, book, skinning, leathers if skin else (), item=item)
        rate = camp_hourly if not (aoe or skin) else None
        here = (near_inst, *near) if near and near_inst is not None else None
        camps = []
        for inst, pts in by_inst.items():
            danger = None if all_levels else self.threats(inst, level, faction, fight=True)
            stops_for = (lambda block, i=inst: camp_stops(block, near if near and (near_inst is None or near_inst == i) else None,
                                                          False, (lambda b: self.stand_at(i, b)) if self.stand_at else None,
                                                          lambda b: self.block_heights(i, b)))
            for score, block, cn, cw in camp_blocks(pts, None, None if danger is None else danger[danger[:, 3] > 0],
                                                    timing=camp_timing, rate=rate):
                walked = (lambda i=inst, b=block: Walked(walk(i, sorted({p[10] for p in b})))) if walk else None
                if item is not None:
                    score = farmspots.farm_score(score, farmspots.trip_seconds(here, inst, cn, cw))
                camps.append(Camp(inst, block, cn, cw, score, stops_for, walked, RUN_SPEED))
        if not camps:
            return None
        whole = True
        if walk:
            best, whole = best_loop(lambda: max(camps, key=lambda c: c.score), until if until is not None else math.inf)
        else:
            best = max(camps, key=lambda c: c.score)
        if best is None:
            return None
        inst, block, cn, cw, stops = best.inst, best.block, best.north, best.west, best.stops
        lap, respawn = camp_timing(block)
        per_hour = camp_walked(camp_hourly(block), block, best.detour)
        names, ids, zones = {}, {}, {}
        for p in block:
            names[p[3]] = names.get(p[3], 0) + p[11]
            ids[p[10]] = ids.get(p[10], 0) + p[11]
            zones[p[9]] = zones.get(p[9], 0) + p[11]
        mobs = sorted(names, key=lambda k: -names[k])
        top = mobs[:2]
        lo, hi = min(p[4] for p in block), max(p[5] for p in block)
        spawns = [(p[0], p[1], z) for p, z in zip(block, self.block_heights(inst, block))]
        stand = self.stand_heights(inst, stops, spawns) if self.stand_heights else None
        out = {"name": " and ".join(top), "mobs": mobs[:LOOP_MOBS], "ids": sorted(ids, key=lambda k: (-ids[k], k)),
               "spots": camp_spots(block),
               "levels": f"{lo}" if lo == hi else f"{lo}-{hi}", "spawns": round(sum(p[11] for p in block)),
               "skins" if skin else "gold" if gold else "items" if item is not None else "xp":
                   round(per_hour) if gold or skin or item is not None else round(sum(p[8] * p[11] for p in block) / sum(p[11] for p in block)),
               "perHour": round(per_hour), "lap": round(lap + best.detour), "respawn": round(respawn),
               "at": [round(cn, 1), round(cw, 1)], "stops": stop_heights(stops, spawns, stand=stand),
               "map": max(zones, key=zones.get), "inst": inst, "score": round(best.score, 1)}
        if walk:
            out["whole"] = whole
        if aoe:
            out["pack"] = statistics.median(p[12] for p in block)
        if item is not None:
            out["kind"] = farmspots.camp_kind(self.item_drops().get(item, {}), block, skinning)
        return out

    def camp_rows(self, maps, level, faction, gold=False, all_levels=False, aoe=0, skin=0, book=None, skinning=0, leathers=(),
                  item=None, keep=True):
        faction_bit, cap, off = facts.faction_bit(faction), self.level_cap(), self.off_events()
        key = (tuple(sorted(maps)), level, faction, bool(gold), bool(all_levels), aoe, skin, skinning,
               tuple(sorted(leathers)), cap, tuple(sorted(off)), self.pace.current, self.respawns_version(), item)
        held = (self.mobs, self.spawns, self.rare_ids, self.spawn_counts, getattr(self, "spawn_ups", None),
                self.respawn_npcs, self.geo, self.drops, self.item_table, self.measured_respawn, self.xp,
                self.xp.samples, self.pace, self.pace.samples, book)
        got = self.camps_kept.get(key)
        if got is not None and all(a is b for a, b in zip(got[0], held)):
            return got[1]
        out = self._camp_rows(maps, level, gold, all_levels, aoe, skin, book, skinning, leathers, faction_bit, cap, off, item)
        if not keep:
            return out
        return kept.keep(self.camps_kept, key, (held, out), CAMPS_KEPT)[1]

    def _camp_rows(self, maps, level, gold, all_levels, aoe, skin, book, skinning, leathers, faction_bit, cap, off, item=None):
        by_inst, by_mob = {}, self.leathers()[1] if skin and leathers else None
        gives = self.item_drops().get(item, {}) if item is not None else None
        for mob_id, mob in self.mobs.items():
            if gives is not None and mob_id not in gives:
                continue
            name, lo, hi, rank, friend = mob[0], mob[1], mob[2], mob[3], mob[6]
            if friend & (1 | faction_bit) or rank in ELITE_RANKS or mob_id in self.rare_ids or not self.fightable(mob_id, off):
                continue
            if skin and not (mob[9] and (all_levels or skinning_needed(hi) <= skin)):
                continue
            greys = bool(skin) or gives is not None
            if not all_levels and (((hi <= gray_level(level)) and not greys) or fights_from((lo + hi) / 2, 0 if aoe else FIGHT_ABOVE) > level):
                continue
            seconds = self.kill_seconds(max(level, (lo + hi) / 2) if all_levels else level, max(1, (mob[4] + mob[5]) / 2))
            if gives is not None:
                worth = item_worth(gives[mob_id], skinned(mob[9], hi, skinning))
                weight = worth * 3600 / seconds
            elif skin:
                worth = 1.0 if by_mob is None else leather_chance(by_mob, mob_id, leathers)
                weight = 3600 / seconds * (1 + skin_up(skin, skinning_needed(hi))) * worth
            elif gold:
                worth = self.kill_worth(mob_id, mob, book, skinning, all_levels)
                weight = worth * 3600 / seconds
            else:
                worth = weight = kill_xp(level, (lo + hi) / 2, cap) * (mob[10] or 1) * self.xp.share(level, (lo + hi) / 2)
            if worth <= 0:
                continue
            respawn = self.measured_respawn(mob_id) or self.respawn_npcs.get(mob_id) or RESPAWN_FALLBACK
            up = self.up_share(mob_id)
            spots = list(self.zone_spots(self.spawns.get(mob_id, {}), maps, shared=True))
            for (n, w, inst, zone, share), pool in zip(spots, self.pool_ups(mob_id, [s[:3] for s in spots])):
                share *= pool
                by_inst.setdefault(inst, []).append((n, w, weight * share * up, name, lo, hi, seconds, respawn, worth, zone,
                                                     int(mob_id), share * up))
        if aoe:
            import numpy as np
            from scipy.spatial import cKDTree
            poor = {m[0] for m in self.mobs.values() if aoe_poor(m)}
            for inst, pts in by_inst.items():
                at = np.array([(p[0], p[1]) for p in pts])
                packs = np.minimum(cKDTree(at).query_ball_point(at, AOE_PACK, return_length=True), aoe)
                by_inst[inst] = [(*p[:2], p[2] * k * (-1 if p[3] in poor else 1), *p[3:6], p[6] * AOE_PULL / k, *p[7:], int(k))
                                 for p, k in zip(pts, packs)]
        return by_inst

    def up_share(self, mob_id):
        have = self.spawn_counts.get(mob_id, 0)
        spots = sum(len(p) for p in self.spawns.get(mob_id, {}).values())
        return have / spots if 0 < have <= SINGLE_SPAWNS and spots > have else 1.0

    def gather_rows(self, instance, level, faction, layer, types=(), daredevil=False):
        import numpy as np
        key = ("gather", instance, level, faction, layer, tuple(sorted(types)), bool(daredevil), self.nodes_version)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        want, rows, seen = set(types), [], set()
        for node in self.nodes.get(layer, []):
            if want and node["n"] not in want:
                continue
            for area, spots in node["s"].items():
                for x, y in spots:
                    at = self.geo.area_to_world(area, x, y)
                    if at and at[2] == instance and (area, x, y) not in seen:
                        seen.add((area, x, y))
                        rows.append((at[0], at[1], GATHER_PULL, -1.0, math.nan))
        mobs = [] if daredevil else [self.threats(instance, level, faction)]
        return self.keep(key, np.concatenate(mobs + [np.array(rows, np.float32).reshape(-1, 5)]))

    def unsafe_spot(self, instance, level, faction):
        import numpy as np
        from scipy.spatial import cKDTree
        rows = self.threats(instance, level, faction)
        rows = rows[rows[:, 3] > 0]
        if not len(rows):
            return lambda n, w: False
        tree, reach = cKDTree(rows[:, :2]), rows[:, 2] + np.where(rows[:, 3] > 1.0, GATHER_CLEAR, 0.0)
        far = float(reach.max())
        return lambda n, w: any(math.hypot(rows[i, 0] - n, rows[i, 1] - w) < reach[i] for i in tree.query_ball_point((n, w), far))

    def gather_setup(self, map_id, layer, types=(), skill=None, safe=None):
        return self.gather_setups([map_id], layer, types, skill, safe).get(int(map_id))

    def gather_setups(self, maps, layer, types=(), skill=None, safe=None):
        maps = {int(m) for m in maps}
        want, found, tests = set(types or ()), {}, {}
        respawn_of = self.node_respawns(layer)
        for node in self.nodes.get(layer, []):
            if (want and node["n"] not in want) or (not want and skill is not None and node.get("skill", 0) > skill):
                continue
            for n, w, inst, zone, chance, up in self.zone_spots(node["s"], maps, node.get("o") or {}):
                f = found.setdefault(zone, {"inst": inst, "spots": {}})
                spot = f["spots"].setdefault((round(n, 1), round(w, 1)), {"at": (n, w), "up": up, "chance": {}, "times": []})
                spot["chance"][node["n"]] = spot["chance"].get(node["n"], 0.0) + chance
                spot["times"].append(respawn_of[node["id"]])
        out = {}
        for zone, f in found.items():
            pts, weights, names, times, unsafe = [], [], {}, [], 0
            test = tests.get(f["inst"]) or tests.setdefault(f["inst"], self.unsafe_spot(f["inst"], *safe)) if safe else None
            for spot in f["spots"].values():
                if test and test(*spot["at"]):
                    unsafe += 1
                    continue
                pts.append(spot["at"])
                weights.append(spot["up"] * min(1.0, sum(spot["chance"].values())))
                for name, chance in spot["chance"].items():
                    names[name] = names.get(name, 0.0) + spot["up"] * chance
                times += spot["times"]
            if not pts:
                continue
            groups, sizes = grouped(pts, weights=weights)
            out[zone] = {"inst": f["inst"], "pts": pts, "weights": weights, "sizes": sizes, "groups": groups, "names": names,
                         "respawn": statistics.median(times), "unsafe": unsafe}
        return out

    def gather_result(self, setup, tour, near, lap_seconds, passed=None, nodes=None):
        if near:
            first = min(range(len(tour)), key=lambda i: math.hypot(tour[i][0] - near[0], tour[i][1] - near[1]))
            tour = tour[first:] + tour[:first]
        names = setup["names"]
        top = sorted(names, key=lambda k: -names[k])[:2]
        return {"name": " and ".join(top), "nodes": passed if passed is not None else sum(g[3] for g in tour),
                "up": round(nodes if nodes is not None else sum(g[2] for g in tour), 1),
                "at": [round(tour[0][0], 1), round(tour[0][1], 1)] if tour else None,
                "stops": [[round(g[0], 1), round(g[1], 1)] for g in tour], "counts": [g[3] for g in tour],
                "lap": round(lap_seconds), "respawn": round(setup["respawn"])}

    def build(self, map_id, level, faction, skills, all_levels=False, ah=False, leathers=()):
        book, cap, leathers, off = self.ah_book() if ah else None, self.level_cap(), tuple(sorted(leathers)), self.off_events()
        key = (map_id, level, faction, tuple(sorted(skills.items())), self.xp.version, self.pace.version, self.pace.current, all_levels,
               self.nodes_version, book and book[0], ah, cap, leathers, tuple(sorted(off)))
        out = self.cache.get(key)
        return out if out is not None else self.keep(key, self._build(map_id, level, faction, skills, all_levels,
                                                                      book[1] if book else self.vendor_book(), cap, leathers, off))

    def _build(self, map_id, level, faction, skills, all_levels=False, book=None, cap=MAX_LEVEL, leathers=(), off=frozenset()):
        faction_bit = facts.faction_bit(faction)
        xp, gold, skin = [], [], []
        (named, by_mob), kinds = self.leathers(), {}
        for mob_id, m in self.mobs.items():
            name, lo, hi, rank, hp_lo, hp_hi, friend, coin, loot, skinnable, xp_mult = m[:11]
            if friend & faction_bit or rank in ELITE_RANKS or mob_id in self.rare_ids or not self.fightable(mob_id, off):
                continue
            pts = self.on_map(self.spawns.get(mob_id, {}), map_id)
            if not pts:
                continue
            mob_level, health = (lo + hi) / 2, max(1, (hp_lo + hp_hi) / 2)
            base = {"name": name, "levels": f"{lo}" if lo == hi else f"{lo}-{hi}", "points": pts, "spawns": len(pts)}
            if mob_level <= level + MAX_ABOVE:
                per_kill = kill_xp(level, mob_level, cap) * (xp_mult or 1) * self.xp.share(level, mob_level)
                if per_kill > 0:
                    xp.append({**base, "perKill": round(per_kill), "value": per_kill / health})
            worth = self.kill_worth(mob_id, m, book, skills.get("skinned", skills.get("skinning", 0)), all_levels)
            if worth > 0 and (all_levels or (hi > gray_level(level) and fights_from(mob_level) <= level)):
                respawn = self.measured_respawn(mob_id) or self.respawn_npcs.get(mob_id) or RESPAWN_FALLBACK
                spawned = len(pts) * self.up_share(mob_id) * 3600 / respawn
                gph = worth * min(self.kills_per_hour(max(level, mob_level), health), spawned)
                gold.append({**base, "perKill": round(worth), "coin": coin, "loot": round(worth - coin), "perHour": round(gph),
                             "value": gph})
            if not skinnable:
                continue
            mine, needed = by_mob.get(mob_id, {}), skinning_needed(hi)
            for item in mine:
                k = kinds.setdefault(item, [0, needed])
                k[0] += len(pts)
                k[1] = min(k[1], needed)
            chance = leather_chance(by_mob, mob_id, leathers) if leathers else 1.0
            if skills.get("skinning") and needed <= skills["skinning"] and chance > 0:
                skin.append({**base, "perKill": needed, "value": chance})
        out = {"map": map_id, "level": level, "heat": {}, "top": {}, "dots": {}, "xpMeasured": self.xp.summary(),
               "pace": self.pace.summary(),
               "leathers": [{"id": item, "name": named[item][0], "icon": named[item][1], "skill": need, "count": n,
                             "can": skills.get("skinning", 0) >= need}
                            for item, (n, need) in sorted(kinds.items(), key=lambda kv: (kv[1][1], named[kv[0]][0]))]}
        for layer, entries in (("xp", xp), ("gold", gold), ("skinning", skin)):
            normalise(entries)
            out["heat"][layer] = [[x, y, round(e["value"]) if layer == "gold" else round(e["weight"], 3)] for e in entries for x, y in e["points"]]
            grindable = [e for e in entries if e["spawns"] >= MIN_SPAWNS_FOR_TOP]
            out["top"][layer] = [{**{k: e[k] for k in ("name", "levels", "perKill", "spawns") + (("coin", "loot", "perHour") if layer == "gold" else ())},
                                  "points": [[round(x, 4), round(y, 4)] for x, y in e["points"]]}
                                 for e in sorted(grindable, key=lambda e: (-e["value"], -e["spawns"]))[:TOP]]
        out["heatRaw"] = ["gold"]
        for layer, skill_key in (("mining", "mining"), ("herbalism", "herbalism"), ("treasure", None), ("fishing", None)):
            types, index, dots = [], {}, []
            for node in self.nodes.get(layer, []):
                pts = self.on_map_odds(node, map_id)
                if not pts:
                    continue
                if node["n"] not in index:
                    have = skills.get(skill_key, 0) if skill_key else None
                    index[node["n"]] = len(types)
                    types.append({"name": node["n"], "skill": node["skill"], "count": 0, "icon": node.get("icon"),
                                  "can": have is None or have >= node["skill"]})
                t = index[node["n"]]
                types[t]["count"] += len(pts)
                dots.extend([x, y, t, round(c, 2), round(u, 2)] for x, y, c, u in pts)
            out["dots"][layer] = {"types": types, "points": dots}
        return out

    def on_map_odds(self, node, map_id):
        odds, out = node.get("o") or {}, []
        for area, pts in node["s"].items():
            there = odds.get(area) or ()
            for i, xy in enumerate(pts):
                p = self.geo.project(area, [xy], map_id, MARGIN)
                if p:
                    chance, up = there[i] if i < len(there) and there[i] else (1.0, 1.0)
                    out.append((p[0][0], p[0][1], chance, up))
        return out
