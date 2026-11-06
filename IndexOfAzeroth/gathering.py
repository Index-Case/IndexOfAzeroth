# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import math
import threading
import time

from serverlog import log_error, start_thread


GATHER_SEARCH_SECONDS = 120.0

GRIND_SEARCH_SECONDS = 60.0

GATHER_SEARCH_KEEP = 600

GATHER_WORKERS = 4


def safest_way(daredevil):
    import nav
    return contextlib.nullcontext() if daredevil else nav.easy_way(falls_only=True)


def loop_walk(find, dry=False):
    from nav import STROKE
    from routes import WALK_MARGIN

    def walk(a, b):
        try:
            body = find((a[0], a[1]), (b[0], b[1]))
        except OSError:
            body = None
        if body and body.get("points"):
            if dry and (body.get("offshore") or 0.0) > STROKE:
                return body["length"], math.inf, None
            gap = (body.get("gap") or 0.0) if body.get("partial") else 0.0
            return body["length"], gap, [[round(v, 1) for v in p] for p in body["points"]]
        return math.hypot(a[0] - b[0], a[1] - b[1]) * WALK_MARGIN, 0.0, None
    return walk


def gather_walk(hub, inst, level, faction, layer, types, daredevil=False):
    avoid = (("gather", level, faction, layer, tuple(types), daredevil),
             hub.world.gather_rows(inst, level, faction, layer, tuple(types), daredevil=daredevil), "gather")

    def find(a, b):
        with safest_way(daredevil):
            return hub.paths.find(inst, a, b, None, None, None, False, avoid, level=level, side=faction or None)
    return loop_walk(find, dry=not daredevil)


def camp_walk(hub, inst, level, faction, ids):
    from planning import round_or_through, wanted
    want = wanted(ids)
    avoid = (("round", level, faction, want), hub.world.threats(inst, level, faction, want=want))
    return loop_walk(lambda a, b: round_or_through(hub, inst, a, b, None, None, None, False, avoid, level, "round",
                                                   side=faction or None))


def loop_ways(hub, inst, level, faction, stops, walked):
    from planning import covered_points, danger_stretches
    terrain = getattr(hub.paths, "terrain", None)
    threats = None if terrain is not None and terrain.is_dungeon(inst) else hub.world.threats(inst, level, faction)
    notes = getattr(hub, "dangerous", None)
    by_stops = {tuple(round(v, 1) for v in k): w for k, w in walked.items()}
    out = []
    for i, a in enumerate(stops):
        b = stops[(i + 1) % len(stops)]
        way = by_stops.get((a[0], a[1], b[0], b[1]))
        if way:
            danger = danger_stretches(way["points"], threats)
            way = {**way, "covered": covered_points(hub, inst, way["points"]), "danger": danger,
                   "dangerNotes": notes.span_notes(inst, danger, faction or None) if notes else [[] for _ in danger]}
        out.append(way)
    return out


GRIND_MAPS_MOST = 300

SEARCHES_MOST = 4

_searches_lock = threading.Lock()


class GatherSearch:

    def __init__(self, hub, params):
        import secrets
        self.id, self.hub, self.params = secrets.token_hex(6), hub, params
        self.state, self.total, self.tested, self.best, self.loop, self.error = "running", 0, [], None, None, None
        self.zones = []
        self.stopped, self.finished = False, None
        self.lock = threading.Lock()
        start_thread(f"gather-search-{self.id}", self.run)

    def run(self):
        from loopsearch import Field, Walked, best_loop
        p, world = self.params, self.hub.world
        try:
            found = world.gather_setups(p["maps"], p["layer"], p["types"], p["skill"],
                                        None if p.get("daredevil") else (p["level"], p["faction"]))
            setups = [(m, found[m]) for m in p["maps"] if m in found]
            if not setups:
                return self.end("done")
            until, walkers, fields = time.time() + GATHER_SEARCH_SECONDS, {}, []
            stopped = lambda: self.stopped
            for m, setup in setups:
                if setup["inst"] not in walkers:
                    walkers[setup["inst"]] = Walked(gather_walk(self.hub, setup["inst"], p["level"], p["faction"], p["layer"],
                                                                  p["types"], daredevil=bool(p.get("daredevil"))),
                                                      GATHER_WORKERS)
                fields.append(Field(m, setup, p["speed"], walkers[setup["inst"]], stopped))
            self.zones = [{"map": f.zone, "groups": f.n} for f in fields]

            def propose():
                loops = [loop for loop in (f.propose() for f in fields) if loop is not None]
                return max(loops, key=lambda loop: loop.score, default=None)
            best, whole = best_loop(propose, until, self.add, stopped)
            if best is not None:
                field = best.field
                stops, ways, _ = best.route()
                figures = best.figures()
                loop = world.gather_result(field.setup, stops, p["near"], figures["lap"], figures["passed"], figures["nodes"])
                self.loop = {**loop, "map": field.zone, "unsafe": field.setup.get("unsafe", 0), "whole": whole,
                             "ways": self.loop_ways(field.setup["inst"], loop["stops"], ways)}
                with self.lock:
                    self.best = next((i for i, t in enumerate(self.tested) if t["key"] == best.key), self.best)
            self.end("stopped" if self.stopped and self.loop is None else "done")
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            log_error("gathering loop search")
            self.end("failed")

    def add(self, loop):
        stops, _, bends = loop.route()
        figures = loop.figures()
        entry = {"map": loop.field.zone, "stops": [[round(g[0], 1), round(g[1], 1)] for g in stops], "ways": bends,
                 "passed": figures["passed"], "nodes": figures["nodes"], "lap": round(figures["lap"]),
                 "rate": round(figures["rate"], 3), "key": loop.key, "score": loop.score}
        with self.lock:
            self.tested.append(entry)
            if self.best is None or loop.score > self.tested[self.best]["score"]:
                self.best = len(self.tested) - 1

    def loop_ways(self, inst, stops, walked):
        try:
            return loop_ways(self.hub, inst, self.params["level"], self.params["faction"], stops, walked)
        except Exception:
            log_error("gathering loop's ways")
            return None

    def end(self, state):
        self.state, self.finished = state, time.time()

    def snapshot(self, since=0):
        with self.lock:
            tested = [{k: v for k, v in t.items() if k not in ("key", "score")} for t in self.tested[since:]]
            return {"id": self.id, "state": self.state, "total": self.total, "tested": tested, "count": len(self.tested),
                    "best": self.best, "loop": self.loop, "error": self.error, "zones": self.zones}
