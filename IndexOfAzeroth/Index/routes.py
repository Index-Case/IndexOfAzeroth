# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import heapq
import itertools
import json
import math
import os
import threading
from collections import OrderedDict

from facts import RUN_SPEED as RUN

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "routes.json")
WALK_MARGIN = 1.3
DOOR_COST = 20.0
PORTAL_APART = 20.0
DOCK_SAME = 15.0
FLY = 28.0
FLIGHT_COST = 15.0
HEARTH_COST = 20.0
HEARTH_WORTH = 300.0
HEARTH_COOLDOWN = 3600.0
SAME_MAP_SAVING = 1.0
WALKED, NOWHERE = -2, -1
MOST = 4
NETWORKS_KEPT = 4


def load():
    try:
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"rides": [], "doors": [], "movers": [], "flights": {"nodes": [], "hops": []}, "inns": []}


STARTS = os.path.join(ROOT, "data", "taxistarts.json")


def load_starts():
    try:
        with open(STARTS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"races": {}, "classes": {}}


def name_hash(name):
    h = 0
    for b in name.encode("utf-8"):
        h = (h * 31 + b) % 65521
    return h


def bound_at(inn, bind):
    return bool(bind) and bind in (inn.get("binds") or ())


RIDE_WORDS = {"boat": "Boat", "zeppelin": "Zeppelin", "airship": "Airship"}


def place_of(node_name):
    return node_name.split(",", 1)[0].strip()


def ride_names(name):
    parts = name.split(" and ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (name, name)


def ride_seconds(mover):
    return mover["seconds"] + mover.get("wait", 0)


def ride_stops(ride):
    if ride.get("stops"):
        return [(s["name"], (s["at"][0], *s["board"]) if s.get("board") else tuple(s["at"]), s["next"]) for s in ride["stops"]]
    a_name, b_name = ride_names(ride["name"])
    board = lambda end, key: (end[0], *ride[key]) if ride.get(key) else tuple(end)
    return [(a_name, board(ride["a"], "aBoard"), ride["minutes"]), (b_name, board(ride["b"], "bBoard"), ride["minutes"])]


def yours(item, side=None, race=0, spells=None, bags=None, done=None, skills=None, level=None):
    if side and item.get("side") not in (None, side) or item.get("races") and not race & item["races"]:
        return False
    needs = item.get("needs") or {}
    return ((not needs.get("quest") or bool(done) and needs["quest"] in done)
            and (not needs.get("item") or bool(bags) and bool(bags.get(needs["item"])))
            and (not needs.get("spell") or bool(spells) and needs["spell"] in spells)
            and (not needs.get("skill") or bool(skills) and (skills.get(needs["skill"][0]) or 0) >= needs["skill"][1])
            and (not needs.get("level") or bool(level) and level >= needs["level"]))


SIDES = ("Alliance", "Horde")


def served_sides(item):
    return {item["side"]} if item.get("side") else set(SIDES)


def one_side(sides):
    return next(iter(sides)) if len(sides) == 1 else None


def way_of(start, legs):
    out, at = [], tuple(start[:3])
    for leg in legs:
        if leg["kind"] == "walk":
            at = (leg["map"], *leg["to"][:2])
            continue
        out.append((leg["name"], at[0], round(at[1]), round(at[2])))
        if leg.get("at"):
            at = (leg["map"], *leg["at"][:2])
    return tuple(out)


def walk_cost(a, b):
    return math.hypot(a[1] - b[1], a[2] - b[2]) * WALK_MARGIN


class Network:

    def __init__(self, points, links, dungeon_inside, door_points):
        self.points, self.dungeon_inside, self.door_points = points, dungeon_inside, door_points
        self.links_from = [[] for _ in points]
        for link, (i, j, cost, leg) in enumerate(links):
            self.links_from[i].append((j, cost, leg, link))
        self.walks = {}

    def walks_of(self, i):
        got = self.walks.get(i)
        if got is None:
            pts, inside, doors = self.points, self.dungeon_inside, self.door_points
            got = self.walks[i] = [(j, walk_cost(pts[i][1], pts[j][1]), None, None) for j in range(2, len(pts))
                                   if j != i and pts[i][1][0] == pts[j][1][0]
                                   and not ((i in inside and j in doors) or (j in inside and i in doors))]
        return got


class Adjacency:

    def __init__(self, network, points):
        self.network, self.points, self.rows = network, points, {}

    def __len__(self):
        return len(self.points)

    def __iter__(self):
        return (self[i] for i in range(len(self.points)))

    def __getitem__(self, i):
        row = self.rows.get(i)
        if row is None:
            pts, net = self.points, self.network
            ends = [(j, walk_cost(pts[i][1], pts[j][1]), None, None) for j in (0, 1)
                    if j != i and pts[i][1][0] == pts[j][1][0]]
            far = net.walks_of(i) if i >= 2 else [(j, walk_cost(pts[i][1], pts[j][1]), None, None)
                                                  for j in range(2, len(pts)) if pts[i][1][0] == pts[j][1][0]]
            row = self.rows[i] = net.links_from[i] + ends + far
        return row


class Routes:
    def __init__(self):
        self.data = load()
        self.starts = load_starts()
        self.extra_doors = lambda: []
        self.reach = None
        self.fly = FLY
        self.networks_kept, self.lock = OrderedDict(), threading.Lock()

    def reload(self):
        self.data = load()
        self.starts = load_starts()
        with self.lock:
            self.networks_kept.clear()

    def starting_flights(self, race_id=0, class_id=0):
        have = {n["id"] for n in self.data.get("flights", {}).get("nodes", ())}
        got = set(self.starts.get("races", {}).get(str(race_id or 0), ()))
        got |= set(self.starts.get("classes", {}).get(str(class_id or 0), ()))
        return got & have

    def portals(self, near=False):
        out, seen = [], set()
        for d in self.data.get("doors", ()):
            p = d.get("portal")
            if not p or (not near and math.dist(p[1:3], d["outside"][1:3]) < PORTAL_APART):
                continue
            key = (p[0], round(p[1]), round(p[2]))
            if key in seen:
                continue
            seen.add(key)
            front = d.get("front") or p
            out.append({"dungeon": d["dungeon"], "inst": p[0], "n": p[1], "w": p[2], "z": p[3], "walk": front[1:4],
                        "underground": bool(d.get("underground"))})
        return out

    def networks(self, side=None):
        out = {kind: {"stops": [], "links": []} for kind in ("flight", "zeppelin", "boat")}
        sides = {kind: {} for kind in out}

        def stop(net, name, inst, n, w):
            for i, s in enumerate(net["stops"]):
                if s["inst"] == inst and math.hypot(s["n"] - n, s["w"] - w) < DOCK_SAME:
                    return i
            net["stops"].append({"name": name, "inst": inst, "n": round(n, 1), "w": round(w, 1)})
            return len(net["stops"]) - 1

        def link(net, i, j):
            if i != j and [i, j] not in net["links"] and [j, i] not in net["links"]:
                net["links"].append([i, j])
        for ride in self.data.get("rides", ()):
            if not yours(ride, side):
                continue
            kind = "boat" if ride["kind"] == "boat" else "zeppelin"
            net = out[kind]
            at = [stop(net, name, where[0], where[1], where[2]) for name, where, _ in ride_stops(ride)]
            for i in at:
                sides[kind].setdefault(i, set()).update(served_sides(ride))
            for k in range(len(at) if len(at) > 2 else 1):
                link(net, at[k], at[(k + 1) % len(at)])
        net, index = out["flight"], {}
        nodes = {n["id"]: n for n in self.data.get("flights", {}).get("nodes", ())}
        for n in nodes.values():
            if yours(n, side) and not n.get("unseen"):
                index[n["id"]] = stop(net, place_of(n["name"]), n["map"], n["at"][0], n["at"][1])
                sides["flight"].setdefault(index[n["id"]], set()).update(served_sides(n))
        hop_sides = {}
        for a, b, *_ in self.data.get("flights", {}).get("hops", ()):
            if a in index and b in index:
                link(net, index[a], index[b])
                pair = frozenset((index[a], index[b]))
                hop_sides.setdefault(pair, set()).update(served_sides(nodes[a]) & served_sides(nodes[b]))
        for kind, served in sides.items():
            for i, s in enumerate(out[kind]["stops"]):
                s["side"] = one_side(served.get(i, set()))
        for k, (i, j) in enumerate(net["links"]):
            net["links"][k] = [i, j, one_side(hop_sides[frozenset((i, j))])]
        return out

    def known_flights(self, taxi, side):
        if not taxi:
            return set()
        ids, hashes = set(taxi.get("ids") or ()), set(taxi.get("hashes") or ())
        return {n["id"] for n in self.data.get("flights", {}).get("nodes", ())
                if n["id"] in ids or (name_hash(n["name"]) in hashes and n.get("side") in (None, side))}

    def inn(self, bind):
        return next((i for i in self.data.get("inns", ()) if bound_at(i, bind)), None)

    def opened(self, side=None, race=0, **means):
        return frozenset((kind, w.get("dungeon") or w.get("name")) for kind in ("doors", "teleports")
                         for w in self.data.get(kind, ()) if w.get("needs") and yours(w, side, race, **means))

    def open_doors(self, side=None, race=0, **means):
        opened, out = self.opened(side, race, **means), []
        for door in self.data.get("doors", ()):
            if ("doors", door["dungeon"]) not in opened or door["outside"][0] != door["inside"][0]:
                continue
            a = tuple((door.get("front") or door.get("portal") or door["outside"])[:3])
            b = tuple(door["inside"][:3])
            out.append((a, b, DOOR_COST))
            if not door.get("oneWay"):
                out.append((b, a, DOOR_COST))
        return out

    def landings(self, side=None, taxi=None, binds=(), nodes=(), race=0, spells=None, bags=None, done=None, skills=None,
                 level=None):
        means = {"spells": spells, "bags": bags, "done": done, "skills": skills, "level": level}
        out, seen = [], set()

        def add(inst, n, w):
            key = (inst, round(n), round(w))
            if key not in seen:
                seen.add(key)
                out.append((inst, float(n), float(w)))
        for bind in binds:
            inn = bind and self.inn(bind)
            if inn:
                add(inn["map"], *inn["at"][:2])
        known = self.known_flights(taxi, side) | set(nodes)
        for n in self.data.get("flights", {}).get("nodes", ()):
            if n["id"] in known and yours(n, side, race):
                add(n["map"], *n["at"][:2])
        for ride in self.data.get("rides", ()):
            if yours(ride, side, race):
                for _, at, _ in ride_stops(ride):
                    add(*at[:3])
        for m in self.data.get("movers", ()):
            if m.get("ends") and yours(m, side, race):
                for end in m.get("stops") or (m["a"], m["b"]):
                    add(m["map"], *end[:2])
        for door in self.data.get("doors", ()):
            if door.get("oneWay") and door.get("to") and yours(door, side, race, **means):
                add(*door["inside"][:3])
        for port in self.data.get("teleports", ()):
            if yours(port, side, race, **means):
                add(*port["to"][:3])
        return out

    @staticmethod
    def walk_of(points, i, j):
        return points[i][1][0], tuple(points[i][1][1:]), tuple(points[j][1][1:])

    def walkable(self, points, ghost=False, allow=frozenset(), wait=False):
        if self.reach is None:
            return lambda i, j: True
        known = {}

        def ok(i, j):
            if self.walk_of(points, i, j) in allow:
                return True
            if (i, j) not in known:
                end, reverse = (j, True) if j == 1 else (i, False)
                at = points[end][1]
                others = [k for k in range(len(points)) if k != end and points[k][1][0] == at[0]]
                got = self.reach(at[0], tuple(at[1:]), [tuple(points[k][1][1:]) for k in others], ghost, reverse, wait)
                for k, v in zip(others, got):
                    known[(k, end) if reverse else (end, k)] = v
            return known.get((i, j)) is not False
        return ok

    def graph(self, start, goal, side=None, taxi=None, hearth=None, speed=RUN, ghost=False, race=0, spells=None, bags=None,
              done=None, skills=None, level=None):
        net = self.network(side, taxi, hearth, speed, ghost, race, spells, bags, done, skills, level)
        points = [("start", tuple(start)), ("goal", tuple(goal))] + net.points[2:]
        return points, Adjacency(net, points)

    def network(self, side=None, taxi=None, hearth=None, speed=RUN, ghost=False, race=0, spells=None, bags=None,
                done=None, skills=None, level=None):
        means = {"spells": spells, "bags": bags, "done": done, "skills": skills, "level": level}
        inn = hearth and not ghost and self.inn(hearth)
        ports = [] if ghost else [
            p for p in self.data.get("teleports", ())
            if yours(p, side, race, **means) and not (bags is not None and any(not bags.get(r) for r in p.get("reagents", ())))]
        known = set() if ghost else self.known_flights(taxi, side)
        doors = self.extra_doors()
        opened = self.opened(side, race, **means)
        key = (side, race, speed, self.fly, ghost, hearth if inn else None, tuple((p["spell"], p["name"]) for p in ports),
               opened, frozenset(known), repr(doors))
        with self.lock:
            got = self.networks_kept.get(key)
            if got is not None:
                self.networks_kept.move_to_end(key)
                return got
        got = self.network_of(side, race, speed, ghost, hearth, inn, ports, known, doors, opened)
        with self.lock:
            self.networks_kept[key] = got
            while len(self.networks_kept) > NETWORKS_KEPT:
                self.networks_kept.popitem(last=False)
        return got

    def network_of(self, side, race, speed, ghost, hearth, inn, ports, known, doors, opened=frozenset()):
        mine = lambda item: ("doors", item["dungeon"]) in opened if item.get("needs") else yours(item, side, race)
        points = [("start", None), ("goal", None)]
        links = []
        for ride in () if ghost else filter(mine, self.data["rides"]):
            stops, first = ride_stops(ride), len(points)
            points += [(name, at) for name, at, _ in stops]
            wait = sum(s[2] for s in stops) / 2
            kind = RIDE_WORDS.get(ride["kind"], "Boat")
            for i in range(len(stops)):
                crossing = 0.0
                for step in range(1, len(stops)):
                    crossing += stops[(i + step - 1) % len(stops)][2]
                    j = (i + step) % len(stops)
                    links.append((first + i, first + j, (crossing + wait) * 60 * speed,
                                  {"kind": "ride", "name": f"{kind} to {stops[j][0]}", "minutes": round(crossing, 1), "vehicle": ride["kind"],
                                   "line": ride["name"]}))
        if inn:
            points.append((hearth, (inn["map"], *inn["at"])))
            links.append((0, len(points) - 1, (HEARTH_COST + HEARTH_WORTH) * speed,
                          {"kind": "hearth", "name": f"Hearthstone to {hearth}", "minutes": HEARTH_COST / 60, "worth": HEARTH_WORTH}))
        for port in ports:
            worth = HEARTH_WORTH * min(1.0, port.get("cooldown", 0) / HEARTH_COOLDOWN)
            points.append((port["name"], tuple(port["to"])))
            links.append((0, len(points) - 1, (HEARTH_COST + worth) * speed,
                          {"kind": "teleport", "name": port["name"], "minutes": HEARTH_COST / 60, "spell": port["spell"],
                           **({"worth": worth} if worth else {}), **({"needs": port["needs"]} if port.get("needs") else {})}))
        nodes = {n["id"]: n for n in self.data.get("flights", {}).get("nodes", ()) if mine(n)}
        flights = {fid: n for fid, n in nodes.items() if fid in known}
        given = {i for ids in self.starts.get("classes", {}).values() for i in ids}
        learnable = {fid: n for fid, n in nodes.items()
                     if fid not in known and fid not in given and not n.get("unseen")} if known else {}
        where, learn_at = {}, {}
        for fid, n in flights.items():
            where[fid] = len(points)
            points.append((f"the {place_of(n['name'])} flight master", (n["map"], *n["at"][:3])))
        for fid, n in learnable.items():
            learn_at[fid] = len(points)
            points.append((f"the {place_of(n['name'])} flight master, to learn its flight path", (n["map"], *n["at"][:3])))
        for a, b, yards, *rest in self.data.get("flights", {}).get("hops", ()):
            if b not in where or (a not in where and a not in learn_at):
                continue
            seconds = yards / self.fly + FLIGHT_COST
            leg = {"kind": "ride", "name": f"Fly to {place_of(flights[b]['name'])}", "minutes": seconds / 60, "vehicle": "flight",
                   "from": place_of(nodes[a]["name"]), "via": rest[0] if rest else [], "node": b}
            if a in learn_at:
                leg["learn"] = place_of(nodes[a]["name"])
            links.append((where.get(a, learn_at.get(a)), where[b], seconds * speed, leg))
        for m in () if ghost else filter(mine, self.data.get("movers", [])):
            if not m.get("ends"):
                continue
            ia, ib = len(points), len(points) + 1
            a, b = m.get("stops") or (m["a"], m["b"])
            points += [(m["ends"][0], (m["map"], *a[:2])), (m["ends"][1], (m["map"], *b[:2]))]
            cost = ride_seconds(m) * speed
            for i, j, end in ((ia, ib, m["ends"][1]), (ib, ia, m["ends"][0])):
                links.append((i, j, cost, {"kind": "ride", "name": f"Tram to {end}", "minutes": m["seconds"] / 60, "vehicle": "tram"}))
        dungeon_inside, door_points = set(), set()
        for door in filter(mine, self.data["doors"] + doors):
            io_, ii = len(points), len(points) + 1
            outside = tuple(door.get("front") or door.get("portal") or door["outside"])
            way_in = f"the portal to {door['to']}" if door.get("oneWay") and door.get("to") else f"{door['dungeon']} entrance"
            points += [(way_in, outside), (f"inside {door['dungeon']}", tuple(door["inside"]))]
            door_points.update((io_, ii))
            needs = {"needs": door["needs"]} if door.get("needs") else {}
            if door.get("oneWay"):
                name = (f"Take the portal to {door['to']}" if door.get("to") else f"Enter {door['into']}" if door.get("into")
                        else f"Leave {door['outOf']}" if door.get("outOf") else door["dungeon"])
                links.append((io_, ii, DOOR_COST, {"kind": "door", "name": name, **({"portal": True} if door.get("to") else {}),
                                                   **needs}))
                continue
            links.append((io_, ii, DOOR_COST, {"kind": "door", "name": f"Enter {door['dungeon']}", **needs}))
            links.append((ii, io_, DOOR_COST, {"kind": "door", "name": f"Leave {door['dungeon']}", **needs}))
            dungeon_inside.add(ii)
        return Network(points, links, dungeon_inside, door_points)

    @staticmethod
    def rides_on(leg):
        return leg is not None and (leg["kind"] != "door" or leg.get("portal", False))

    @staticmethod
    def step_id(step):
        return step[4] if step[4] is not None else (step[0], step[1])

    @classmethod
    def state_after(cls, begin, steps):
        _, took, learned, came = begin
        for i, j, _, leg, _ in steps:
            took, learned = took or cls.rides_on(leg), learned or bool(leg and leg.get("learn"))
            came = WALKED if leg is None else i
        return (steps[-1][1] if steps else begin[0], took, learned, came)

    @classmethod
    def search(cls, adj, weight, begin, banned=frozenset(), avoid=frozenset(), cut=frozenset()):
        best, prev, goal = {begin: 0.0}, {}, None
        queue = [(0.0, *begin)]
        while queue:
            d, i, took, learned, came = heapq.heappop(queue)
            state = (i, took, learned, came)
            if d > best.get(state, math.inf):
                continue
            if i == 1:
                if took:
                    goal = state
                    break
                continue
            for j, cost, leg, link in adj[i]:
                if j == begin[0] or j in avoid:
                    continue
                if leg is None:
                    if came == WALKED or (i, j) in cut or (i, j) in banned:
                        continue
                elif link in banned or j == came:
                    continue
                learns = bool(leg and leg.get("learn"))
                if learns and learned:
                    continue
                to = (j, took or cls.rides_on(leg), learned or learns, WALKED if leg is None else i)
                nd = d + weight(i, j, cost, leg)
                if nd < best.get(to, math.inf):
                    best[to], prev[to] = nd, (state, cost, leg, link)
                    heapq.heappush(queue, (nd, *to))
        if goal is None or goal not in prev:
            return None
        steps, at = [], goal
        while at != begin:
            before, cost, leg, link = prev[at]
            steps.append((before[0], at[0], cost, leg, link))
            at = before
        steps.reverse()
        return best[goal], steps

    @staticmethod
    def pointless(steps):
        been = [steps[0][0]] + [s[1] for s in steps]
        rides = [s[3] for s in steps]
        return len(set(been)) < len(been) or any(a and b and a.get("line") and a.get("line") == b.get("line")
                                                 for a, b in zip(rides, rides[1:]))

    @staticmethod
    def legs_of(points, steps, goal_name):
        legs, walks = [], []
        for j, i, cost, leg, _ in steps:
            name, p = points[i]
            if leg is None:
                if legs and legs[-1]["kind"] == "walk":
                    legs[-1]["to"], legs[-1]["name"] = list(p[1:]), name
                    walks[-1][2], walks[-1][3] = p[1:], walks[-1][3] + cost
                else:
                    legs.append({"kind": "walk", "map": p[0], "to": list(p[1:]), "name": goal_name if i == 1 else name})
                    walks.append([p[0], points[j][1][1:], p[1:], cost])
            elif leg.get("vehicle") == "flight" and legs and legs[-1].get("vehicle") == "flight":
                legs[-1].update(name=leg["name"], node=leg["node"], at=list(p[1:]),
                                minutes=legs[-1]["minutes"] + leg["minutes"] - FLIGHT_COST / 60,
                                via=legs[-1].get("via", []) + leg.get("via", []), hops=legs[-1]["hops"] + [leg["node"]])
            else:
                legs.append({**leg, "map": p[0], "at": list(p[1:]), **({"hops": [leg["node"]]} if leg.get("vehicle") == "flight" else {})})
        for k, leg in enumerate(legs):
            if leg["kind"] == "walk" and k + 1 < len(legs):
                nxt = legs[k + 1]
                place = nxt["name"].split(" ", 1)[1] if nxt["kind"] == "door" and " " in nxt["name"] else nxt["name"]
                bare = place[4:] if place.startswith("The ") else place
                if nxt.get("vehicle") == "flight":
                    leg["name"] = f"the {nxt['from']} flight master{', to learn its flight path' if nxt.get('learn') else ''}"
                elif nxt["kind"] == "ride":
                    leg["name"] = f"the {nxt['vehicle']} to {nxt['name'].split(' to ', 1)[1]}"
                elif nxt["name"].startswith("Enter"):
                    leg["name"] = f"the {bare} entrance"
                elif nxt["name"].startswith("Leave"):
                    leg["name"] = f"the way out of {place}"
                else:
                    leg["name"] = place
            elif leg["kind"] == "walk":
                leg["name"] = goal_name or "the target"
        return legs, [(w[0], tuple(w[1]), tuple(w[2]), w[3]) for w in walks]

    def plans(self, start, goal, goal_name="", side=None, taxi=None, hearth=None, speed=RUN, most=MOST, ghost=False, race=0,
              spells=None, bags=None, allow=frozenset(), cuts=None, wait=False, done=None, skills=None, level=None):
        found = self.ways(start, goal, goal_name, side, taxi, hearth, speed, ghost, race, spells, bags, allow, cuts, wait,
                          done, skills, level)
        out = list(itertools.islice((p for p in found if p["legs"]), most)) + ([found.plain] if found.plain else [])
        return sorted(out, key=lambda p: p["cost"])

    def ways(self, start, goal, goal_name="", side=None, taxi=None, hearth=None, speed=RUN, ghost=False, race=0,
             spells=None, bags=None, allow=frozenset(), cuts=None, wait=False, done=None, skills=None, level=None,
             floor=None, weighed=None):
        return Ways(self, start, goal, goal_name, speed, ghost, allow, cuts, wait, floor, weighed,
                    self.graph(start, goal, side, taxi, hearth, speed, ghost, race, spells, bags, done, skills, level))

    def plan(self, start, goal, goal_name="", side=None, taxi=None, hearth=None, speed=RUN, race=0, spells=None, bags=None,
             done=None, skills=None, level=None):
        found = self.plans(start, goal, goal_name, side, taxi, hearth, speed, most=1, race=race, spells=spells, bags=bags,
                           done=done, skills=skills, level=level)
        if not found or not found[0]["legs"]:
            return None
        return {"legs": found[0]["legs"], "yards": round(found[0]["yards"])}


class Ways:

    def __init__(self, routes, start, goal, goal_name, speed, ghost, allow, cuts, wait, floor, weighed, graph):
        self.start, self.goal_name, self.speed, self.cuts = start, goal_name, speed, cuts
        self.weighed = {} if weighed is None else weighed
        self.points, self.adj = graph
        self.walkable, self.cut = routes.walkable(self.points, ghost, allow, wait), set()
        self.floor, self.floors, self.pairs, self.learned = floor, {}, {}, 0
        self.same, self.plain = start[0] == goal[0], None
        if self.same and self.walkable(0, 1):
            straight = math.hypot(start[1] - goal[1], start[2] - goal[2]) * WALK_MARGIN
            self.plain = {"legs": [], "yards": straight, "cost": straight * SAME_MAP_SAVING,
                          "walks": [(start[0], tuple(start[1:]), tuple(goal[1:]), straight)],
                          "floor": self.weight(0, 1, straight * SAME_MAP_SAVING, None)}
        elif self.same and cuts is not None:
            cuts.append(Routes.walk_of(self.points, 0, 1))

    def weight(self, i, j, cost, leg):
        if leg is not None or self.floor is None:
            return cost
        got = self.floors.get((i, j))
        if got is None:
            walk = Routes.walk_of(self.points, i, j)
            got = self.floors[(i, j)] = self.weighed[walk] if walk in self.weighed else self.floor(walk)
            self.pairs.setdefault(walk, []).append((i, j))
        return got

    def learn(self):
        if len(self.weighed) > self.learned:
            for walk in itertools.islice(self.weighed, self.learned, None):
                for pair in self.pairs.get(walk, ()):
                    self.floors[pair] = self.weighed[walk]
            self.learned = len(self.weighed)

    def floor_of(self, steps):
        return sum(self.weight(*s[:4]) for s in steps)

    def joins(self, i, j):
        if (i, j) in self.cut:
            return False
        walk = Routes.walk_of(self.points, i, j)
        if self.weighed.get(walk) == math.inf:
            self.cut.add((i, j))
            return False
        if not self.walkable(i, j):
            self.cut.add((i, j))
            if self.cuts is not None:
                self.cuts.append(walk)
            return False
        return True

    def __iter__(self):
        R, begin, plain = Routes, (0, not self.same, False, NOWHERE), self.plain
        queue, order, drawn = [], itertools.count(), set()

        def split(key, root, banned, avoid):
            heapq.heappush(queue, (key, next(order), None, root, banned, avoid))

        def walks_join(steps):
            return all([self.joins(s[0], s[1]) for s in steps if s[3] is None])
        split(0.0, (), frozenset(), frozenset())
        while queue or plain is not None:
            self.learn()
            if plain is not None:
                plain["floor"] = self.weight(0, 1, plain["cost"], None)
                if not queue or plain["floor"] < queue[0][0]:
                    yield plain
                    plain = None
                    continue
            key, _, steps, root, banned, avoid = heapq.heappop(queue)
            if not walks_join(root):
                continue
            if steps is None or not walks_join(steps[len(root):]) or self.floor_of(steps) != key:
                got = R.search(self.adj, self.weight, R.state_after(begin, root), banned, avoid, frozenset(self.cut))
                if got:
                    found = root + tuple(got[1])
                    heapq.heappush(queue, (self.floor_of(found), next(order), found, root, banned, avoid))
                continue
            ids = tuple(map(R.step_id, steps))
            split(key, root, banned | {ids[len(root)]}, avoid)
            for m in range(len(root) + 1, len(steps)):
                split(key, steps[:m], frozenset({ids[m]}), frozenset(s[0] for s in steps[:m]))
            if not any(s[4] is not None for s in steps) or R.pointless(steps):
                continue
            legs, walks = R.legs_of(self.points, steps, self.goal_name)
            way = way_of(self.start, legs)
            if way in drawn:
                continue
            drawn.add(way)
            cost = sum(s[2] for s in steps)
            charged = legs[0].get("worth", 0.0) * self.speed
            yield {"legs": legs, "yards": cost - charged, "cost": cost, "walks": walks, "floor": key}
