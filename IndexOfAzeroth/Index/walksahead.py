# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import multiprocessing
import os
import threading
import time

import carried
import game
import nav
import workers
from serverlog import log_error, log_note

ENV = "DGG_WALKSAHEAD"
LOOK = 5.0
STEP = 0.25
AWAY = 60.0
NEXT_NEAR = 0.8
REORDER = 500.0


def on(root=None, env=None):
    env = os.environ if env is None else env
    return game.writes_game(root) or env.get(ENV) == "1"


def queue(open_epic, level, cap, now, soon, near_next):
    ahead = level + 1 if level < cap else None
    first = [(open_epic, at) for at in (level, ahead) if open_epic and at]
    mine, next_up = [(key, level) for key in now], [(key, ahead) for key in soon if ahead]
    out = []
    for asking in first + (next_up + mine if near_next else mine + next_up):
        if asking not in out:
            out.append(asking)
    return out


class Seen:

    def __init__(self, hub, level):
        self.__dict__.update(_hub=hub, _level=level)

    def __getattr__(self, name):
        return getattr(self._hub, name)

    @property
    def state(self):
        state = self._hub.state
        if not state or state.get("level") == self._level:
            return state
        return {**state, "level": self._level, "xp": 0}


def found(paths, to_hand, args, kwargs):
    with nav.to_hand() if to_hand else contextlib.nullcontext():
        return paths.find(*args, **kwargs)


def end_with_server():
    server = multiprocessing.parent_process()
    if server is None:
        return

    def watch():
        server.join()
        os._exit(0)
    threading.Thread(target=watch, daemon=True, name="server gone").start()


def lane_process(conn):
    import storewriter
    end_with_server()
    workers._priority(workers.BELOW_NORMAL)
    nav.wm.serve_built()
    paths = nav.Paths()
    held, seen = {}, {}

    def back(*ask):
        conn.send(ask)
        return conn.recv()

    def populated(inst):
        if inst not in seen:
            got = back("populated", inst, held[inst][0] if inst in held else None)
            if got[0] == "new":
                held[inst] = got[1:]
            seen[inst] = held[inst][1]
        return seen[inst]

    paths.populated_of = populated
    paths.room_indoors = lambda *spot: back("indoors", spot)[1]
    while True:
        try:
            ask = conn.recv()
        except (EOFError, OSError):
            break
        if ask[0] == "stop":
            break
        if ask[0] == "tables":
            paths.set_tables(**ask[1])
            continue
        _, switches, to_hand, args, kwargs = ask
        seen.clear()
        try:
            answer = ("found", carried.Carried(found, switches)(paths, to_hand, args, kwargs), paths.rules)
        except nav.NotBuilt as e:
            answer = ("unbuilt", e.what)
        except Exception as e:
            answer = ("raised", e)
        try:
            conn.send(answer)
        except Exception as e:
            conn.send(("raised", RuntimeError(f"{type(e).__name__}: {e}")))
    storewriter.flush_later()


def start_process(conn):
    process = multiprocessing.get_context("spawn").Process(target=lane_process, args=(conn,), name="walks ahead",
                                                           daemon=True)
    process.start()
    conn.close()
    return process


class Lane:

    def __init__(self, hub, wanted=lambda: True, hold=lambda: False, start=start_process, sleep=time.sleep):
        self.hub, self.wanted, self.hold, self.start, self.sleep = hub, wanted, hold, start, sleep
        self.lock = threading.Lock()
        self.off = False
        self.gone = False
        self.process = self.conn = self.rules = None
        self.wilds = {}
        self.asks, self.waited = 0, 0.0

    def wait(self):
        import planning
        began = time.monotonic()
        while True:
            if self.off or not self.wanted():
                self.off = True
                raise planning.AheadOff()
            if not self.hold():
                self.waited += time.monotonic() - began
                return
            if self.process is not None and time.monotonic() - began > AWAY:
                self.down()
            self.sleep(STEP)

    def going(self, *progress):
        with self.lock:
            self.wait()

    def up(self):
        if self.process is None:
            self.conn, theirs = multiprocessing.get_context("spawn").Pipe()
            self.process = self.start(theirs)
            self.rules = None
        return self.conn

    def down(self, kill=False):
        process, conn, self.process, self.conn = self.process, self.conn, None, None
        if process is None:
            return
        with contextlib.suppress(Exception):
            if not kill:
                conn.send(("stop",))
                process.join(15)
        with contextlib.suppress(Exception):
            if process.is_alive():
                process.terminate()
            conn.close()

    def stop(self):
        self.off = True
        process = self.process
        with contextlib.suppress(Exception):
            if process is not None:
                process.terminate()

    def find(self, *args, **kwargs):
        import planning
        with self.lock:
            self.wait()
            conn, paths = self.up(), self.hub.paths
            rules = paths.rules
            try:
                if rules != self.rules:
                    tables = paths.walk_tables
                    conn.send(("tables", {"zone_levels": tables["zone_levels"], "capitals": tables["capitals"]}))
                    self.rules = rules
                conn.send(("find", carried.values(), nav._to_hand.get(), args, kwargs))
                self.asks += 1
                while True:
                    while not conn.poll(STEP):
                        if self.off or not self.process.is_alive():
                            raise EOFError
                    got = conn.recv()
                    if got[0] == "populated":
                        wilds = paths.populated_of(got[1]) if paths.populated_of else None
                        self.wilds[got[1]] = wilds
                        conn.send(("same",) if got[2] == id(wilds) else ("new", id(wilds), wilds))
                    elif got[0] == "indoors":
                        conn.send(("room", paths.room_indoors(*got[1]) if paths.room_indoors else None))
                    else:
                        break
            except (EOFError, OSError):
                self.gone = not self.off
                self.down(kill=True)
                self.off = True
                raise planning.AheadOff() from None
            if got[0] == "unbuilt":
                raise nav.NotBuilt(got[1])
            if got[0] == "raised":
                raise got[1]
            if got[2] != rules:
                self.down(kill=True)
                self.off = True
                log_note("walks ahead: the lane's walk rules differ from the server's, the asking is called off")
                raise planning.AheadOff()
            return got[1]


class Ahead:

    def __init__(self, hub, log=log_error):
        self.hub, self.log = hub, log
        self.done = {}
        self.now = None
        self.lane = None
        self.queued = None

    def idle(self):
        import planning
        hub = self.hub
        if planning.playing_now(hub) is None:
            return "nobody is playing"
        blind = planning.planned_blind(hub) or planning.objectives_unknown(hub)
        if blind:
            return blind
        fill, rebuilder = getattr(hub, "navfill", None), getattr(hub, "rebuilder", None)
        if (fill and fill.running()) or (rebuilder and rebuilder.running.locked()):
            return "the navigation or the data is being built"
        if workers.count(most=1) < 1:
            return "the machine has no room for a process beside the game"
        return workers.memory_short() or ("someone asked for a plan or a way" if planning.asked_now(hub) else None)

    def open_epic(self):
        import planning
        sh = getattr(self.hub, "shared", None)
        epic = ((sh.data or {}) if sh else {}).get("epic") or {}
        if not epic.get("key") or epic.get("closed") \
                or not planning.same_char(epic.get("char"), planning.playing_char(self.hub)):
            return None
        return epic

    def zones(self, level):
        import planning
        hub = self.hub
        here = planning.here_now(hub)
        side = ((hub.status or {}).get("strs") or {}).get("faction")
        out = []
        for zone in planning.quest_zones(Seen(hub, level)):
            band = hub.zone_levels.get(str(zone["id"]))
            whose = (getattr(hub, "zone_pvp", None) or {}).get(str(zone["id"]))
            if not band or not band[0] <= level <= band[1] or (whose in ("Alliance", "Horde") and whose != side):
                continue
            try:
                north, west, inst = hub.world.geo.to_world(zone["id"], 0.5, 0.5)[:3]
            except Exception:
                north = west = inst = None
            far = (0, ((north - here[1]) ** 2 + (west - here[2]) ** 2) ** 0.5) if here and inst == here[0] else (1, 0.0)
            out.append((far, zone["id"]))
        return [f"zone:{zone}" for _, zone in sorted(out)]

    def askings(self):
        import planning
        hub = self.hub
        state = hub.state or {}
        level, cap = state.get("level") or 1, hub.characters.max_level()
        near = bool(state.get("xpMax")) and (state.get("xp") or 0) >= NEXT_NEAR * state["xpMax"]
        opened, here = (self.open_epic() or {}).get("key"), planning.here_now(hub)
        by = (hub.characters.current, level, cap, near, opened, getattr(hub, "data_version", 0),
              here and (here[0], round(here[1] / REORDER), round(here[2] / REORDER)))
        if self.queued is None or self.queued[0] != by:
            self.queued = (by, queue(opened, level, cap, self.zones(level),
                                     self.zones(level + 1) if level < cap else [], near))
        return self.queued[1]

    def asking_sig(self, key, level):
        hub = self.hub
        side = ((hub.status or {}).get("strs") or {}).get("faction")
        return (hub.characters.current, key, level, side, getattr(hub, "data_version", 0))

    def wanted(self, sig):
        key, level = sig[1], sig[2]
        now = (self.hub.state or {}).get("level") or 0
        return sig == self.asking_sig(key, level) and level in (now, now + 1)

    def run(self, key, level):
        import planning
        hub, sig = self.hub, self.asking_sig(key, level)
        epic = self.open_epic() or {}
        mine = epic if epic.get("key") == key else {}
        here = planning.here_now(hub)
        anchor = (here[0], round(float(here[1]), 1), round(float(here[2]), 1)) if here else None
        lane = self.lane = Lane(hub, wanted=lambda: self.wanted(sig), hold=lambda: self.idle() is not None)
        self.now = {"key": key, "level": level, "since": round(time.time())}
        began = time.monotonic()
        try:
            ran = planning.ask_ahead(Seen(hub, level), lane, key, anchor, mode=mine.get("mode") or "any",
                                     parked=set(mine.get("parked") or ()),
                                     quest_levels=planning.quest_levels_of(key, mine.get("questLevels") or ()),
                                     indoors=planning.indoors_of(hub.state or {}))
            if not lane.off:
                self.done[sig] = bool(ran)
                log_note(f"walks ahead: {key} at level {level}, {lane.asks} ways asked in "
                         f"{round(time.monotonic() - began - lane.waited)} s")
        except planning.AheadOff:
            if lane.gone:
                self.done[sig] = False
                log_note(f"walks ahead: the lane's process went away during {key} at level {level}")
        except Exception:
            self.done[sig] = False
            self.log(f"the walks ahead for {key} at level {level}")
        finally:
            lane.down(kill=lane.off)
            self.now = self.lane = None

    def look(self):
        if self.idle():
            return False
        for key, level in self.askings():
            if self.asking_sig(key, level) not in self.done:
                self.run(key, level)
                return True
        return False

    def watch(self, sleep=time.sleep):
        while True:
            sleep(LOOK)
            try:
                self.look()
            except Exception:
                self.log("the walks ahead")

    def stop(self):
        lane = self.lane
        if lane is not None:
            lane.stop()

    def snapshot(self):
        return {"now": self.now, "done": len(self.done)}
