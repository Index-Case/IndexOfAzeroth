# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import heapq
import json
import math
import os

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
ALTERNATIVE_WITHIN = 1.5


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


def yours(item, side=None, race=0):
    return (not side or item.get("side") in (None, side)) and (not item.get("races") or bool(race & item["races"]))


SIDES = ("Alliance", "Horde")


def served_sides(item):
    return {item["side"]} if item.get("side") else set(SIDES)


def one_side(sides):
    return next(iter(sides)) if len(sides) == 1 else None


class Routes:
    def __init__(self):
        self.data = load()
        self.starts = load_starts()
        self.extra_doors = lambda: []
        self.reach = None
        self.fly = FLY

    def reload(self):
        self.data = load()
        self.starts = load_starts()

    def starting_flights(self, race_id=0, class_id=0):
        have = {n["id"] for n in self.data.get("flights", {}).get("nodes", ())}
        got = set(self.starts.get("races", {}).get(str(race_id or 0), ()))
        got |= set(self.starts.get("classes", {}).get(str(class_id or 0), ()))
        return got & have

    def portals(self):
        out, seen = [], set()
        for d in self.data.get("doors", ()):
            p = d.get("portal")
            if not p or math.dist(p[1:3], d["outside"][1:3]) < PORTAL_APART:
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

    def landings(self, side=None, taxi=None, binds=(), nodes=(), race=0, spells=None):
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
            if door.get("oneWay") and door.get("to") and yours(door, side, race):
                add(*door["inside"][:3])
        for port in self.data.get("teleports", ()) if spells else ():
            if port["spell"] in spells:
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

    def graph(self, start, goal, side=None, taxi=None, hearth=None, speed=RUN, ghost=False, race=0, spells=None, bags=None):
        mine = lambda item: yours(item, side, race)
        points = [("start", tuple(start)), ("goal", tuple(goal))]
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
        inn = hearth and not ghost and self.inn(hearth)
        if inn:
            points.append((hearth, (inn["map"], *inn["at"])))
            links.append((0, len(points) - 1, (HEARTH_COST + HEARTH_WORTH) * speed,
                          {"kind": "hearth", "name": f"Hearthstone to {hearth}", "minutes": HEARTH_COST / 60, "worth": HEARTH_WORTH}))
        for port in () if ghost or not spells else self.data.get("teleports", ()):
            if port["spell"] not in spells or (bags is not None and any(not bags.get(r) for r in port.get("reagents", ()))):
                continue
            worth = HEARTH_WORTH * min(1.0, port.get("cooldown", 0) / HEARTH_COOLDOWN)
            points.append((port["name"], tuple(port["to"])))
            links.append((0, len(points) - 1, (HEARTH_COST + worth) * speed,
                          {"kind": "teleport", "name": port["name"], "minutes": HEARTH_COST / 60, "spell": port["spell"],
                           **({"worth": worth} if worth else {})}))
        known = set() if ghost else self.known_flights(taxi, side)
        nodes = {n["id"]: n for n in self.data.get("flights", {}).get("nodes", ()) if mine(n)}
        flights = {fid: n for fid, n in nodes.items() if fid in known}
        learnable = {fid: n for fid, n in nodes.items() if fid not in known and not n.get("unseen")} if known else {}
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
        for door in filter(mine, self.data["doors"] + self.extra_doors()):
            io_, ii = len(points), len(points) + 1
            outside = tuple(door.get("front") or door.get("portal") or door["outside"])
            way_in = f"the portal to {door['to']}" if door.get("oneWay") and door.get("to") else f"{door['dungeon']} entrance"
            points += [(way_in, outside), (f"inside {door['dungeon']}", tuple(door["inside"]))]
            door_points.update((io_, ii))
            if door.get("oneWay"):
                name = (f"Take the portal to {door['to']}" if door.get("to") else f"Enter {door['into']}" if door.get("into")
                        else f"Leave {door['outOf']}" if door.get("outOf") else door["dungeon"])
                links.append((io_, ii, DOOR_COST, {"kind": "door", "name": name, **({"portal": True} if door.get("to") else {})}))
                continue
            links.append((io_, ii, DOOR_COST, {"kind": "door", "name": f"Enter {door['dungeon']}"}))
            links.append((ii, io_, DOOR_COST, {"kind": "door", "name": f"Leave {door['dungeon']}"}))
            dungeon_inside.add(ii)
        n = len(points)
        adj = [[] for _ in range(n)]
        for link, (i, j, cost, leg) in enumerate(links):
            adj[i].append((j, cost, leg, link))
        for i in range(n):
            for j in range(n):
                if (i in dungeon_inside and j in door_points) or (j in dungeon_inside and i in door_points):
                    continue
                if i != j and points[i][1][0] == points[j][1][0]:
                    pi, pj = points[i][1], points[j][1]
                    adj[i].append((j, math.hypot(pi[1] - pj[1], pi[2] - pj[2]) * WALK_MARGIN, None, None))
        return points, adj

    @staticmethod
    def search(adj, banned=frozenset(), ride=False, cut=frozenset()):
        begin = (0, not ride, False)
        best, prev, goal = {begin: 0.0}, {}, None
        queue = [(0.0, *begin)]
        while queue:
            d, i, took, learned = heapq.heappop(queue)
            if i == 1 and took:
                goal = (i, took, learned)
                break
            if d > best.get((i, took, learned), math.inf):
                continue
            for j, cost, leg, link in adj[i]:
                if link in banned or (leg is None and (i, j) in cut):
                    continue
                learns = bool(leg and leg.get("learn"))
                if learns and learned:
                    continue
                rode = took or (leg is not None and (leg["kind"] != "door" or leg.get("portal", False)))
                state, nd = (j, rode, learned or learns), d + cost
                if nd < best.get(state, math.inf):
                    best[state], prev[state] = nd, ((i, took, learned), cost, leg, link)
                    heapq.heappush(queue, (nd, *state))
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
                legs[-1].update(name=leg["name"], at=list(p[1:]), minutes=legs[-1]["minutes"] + leg["minutes"] - FLIGHT_COST / 60,
                                via=legs[-1].get("via", []) + leg.get("via", []))
            else:
                legs.append({**leg, "map": p[0], "at": list(p[1:])})
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

    def plans(self, start, goal, goal_name="", side=None, taxi=None, hearth=None, speed=RUN, most=4, ghost=False, race=0,
              spells=None, bags=None, allow=frozenset(), cuts=None, wait=False):
        points, adj = self.graph(start, goal, side, taxi, hearth, speed, ghost, race, spells, bags)
        out, seen, tried, todo = [], set(), set(), [frozenset()]
        walkable, cut = self.walkable(points, ghost, allow, wait), set()
        plain = start[0] == goal[0] and walkable(0, 1)
        if start[0] == goal[0] and not plain and cuts is not None:
            cuts.append(self.walk_of(points, 0, 1))
        while todo and len(out) < most:
            banned = todo.pop(0)
            if banned in tried:
                continue
            tried.add(banned)
            while True:
                found = self.search(adj, banned, start[0] == goal[0], frozenset(cut))
                gone = [(s[0], s[1]) for s in found[1] if s[3] is None and not walkable(s[0], s[1])] if found else []
                if not gone:
                    break
                cut.update(gone)
                if cuts is not None:
                    cuts += [self.walk_of(points, i, j) for i, j in gone]
            if not found:
                continue
            cost, steps = found
            links = tuple(s[4] for s in steps if s[4] is not None)
            if not links or links in seen:
                continue
            seen.add(links)
            if self.pointless(steps):
                todo += [banned | {link} for link in links]
                continue
            legs, walks = self.legs_of(points, steps, goal_name)
            charged = legs[0].get("worth", 0.0) * speed
            out.append({"legs": legs, "yards": cost - charged, "cost": cost, "walks": walks})
            todo += [banned | {link} for link in links]
        if plain:
            straight = math.hypot(start[1] - goal[1], start[2] - goal[2]) * WALK_MARGIN
            out = [p for p in out if p["cost"] <= straight * SAME_MAP_SAVING * ALTERNATIVE_WITHIN]
            out.append({"legs": [], "yards": straight, "cost": straight * SAME_MAP_SAVING,
                        "walks": [(start[0], tuple(start[1:]), tuple(goal[1:]), straight)]})
        out.sort(key=lambda p: p["cost"])
        seen_rides, kept = set(), []
        for p in out:
            rides = tuple(leg["name"] for leg in p["legs"] if leg["kind"] != "walk")
            if rides not in seen_rides:
                seen_rides.add(rides)
                kept.append(p)
        return kept

    def plan(self, start, goal, goal_name="", side=None, taxi=None, hearth=None, speed=RUN, race=0, spells=None, bags=None):
        found = self.plans(start, goal, goal_name, side, taxi, hearth, speed, most=1, race=race, spells=spells, bags=bags)
        if not found or not found[0]["legs"]:
            return None
        return {"legs": found[0]["legs"], "yards": round(found[0]["yards"])}
