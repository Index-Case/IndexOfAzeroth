# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import copy
import json
import math
import threading
import time

import errands
from characters import TRAVEL_FASTEST, same_char
import planrepair
from plansteps import EPIC_CODE, step_ids
from shared import plan_notes
import ticks

CHECK_EVERY = 10.0
SOON = 1.5
WAYS_AGAIN = 60.0
RANK = {"minor": 0, "worth": 1, "needed": 2}
NEEDS = ("train", "repair", "sell", "restock")
SMALL = "has small changes"
WAYS = {"safe": "takes the safest route, on roads and well clear of mobs",
        "fight": "takes a route that grinds through the mobs worth fighting",
        "any": "takes the quickest route round the mobs"}
MOVED = "moves your errands to NPCs near where you are"
DIED = "goes on from where you came back to life"
JUMP_YARDS = 300.0
WALK_MOST = TRAVEL_FASTEST * 1.25
RIDE_SECONDS = 60.0
SPOT_EVERY = 1.0
SETTLED = 3.0
GEAR_SETTLE = 5.0
PICKS = "picks quest rewards for the gear you wear"
JUMPS_KEPT = 16


class Jumps:

    def __init__(self):
        self.lock = threading.Lock()
        self.spots = []
        self.away = False
        self.dead = False
        self.ride = None
        self.n = 0
        self.starts = {}
        self.deaths = set()

    def see(self, here, flags, now):
        flags = flags or {}
        with self.lock:
            if flags.get("taxi") or flags.get("instance") or flags.get("dead") or flags.get("ghost"):
                self.away = bool(self.spots)
                self.dead = self.dead or bool(self.spots and (flags.get("dead") or flags.get("ghost")))
                return False
            if not here:
                return False
            here = tuple(here[:3])
            start = self.start(here, now) if self.spots else None
            if start:
                self.n += 1
                self.starts[self.n] = start
                self.starts.pop(self.n - JUMPS_KEPT, None)
                if self.dead:
                    self.deaths.add(self.n)
                self.deaths.discard(self.n - JUMPS_KEPT)
                self.spots, self.ride = [], None
            self.dead = False
            if len(self.spots) > 1 and now - self.spots[-2][0] < SPOT_EVERY:
                self.spots[-1] = (now, here)
            else:
                self.spots.append((now, here))
            while len(self.spots) > 2 and now - self.spots[0][0] > RIDE_SECONDS:
                self.spots.pop(0)
            self.away = False
            return bool(start)

    def start(self, here, now):
        t, last = self.spots[-1]
        yards = lambda p: math.hypot(here[1] - p[1], here[2] - p[2])
        fast = lambda t0, p: yards(p) / max(now - t0, 1e-3) > WALK_MOST
        if last[0] != here[0]:
            return last
        if self.away:
            return last if yards(last) >= JUMP_YARDS else None
        if yards(last) >= JUMP_YARDS and fast(t, last):
            return last
        self.ride = self.ride or next((p for t0, p in self.spots if yards(p) >= JUMP_YARDS and fast(t0, p)), None)
        back = [(t0, p) for t0, p in self.spots if now - t0 >= SETTLED]
        if not self.ride or not back or fast(*back[-1]):
            return None
        start, self.ride = self.ride, None
        return start if yards(start) >= JUMP_YARDS else None

    def since(self, seen):
        with self.lock:
            if self.n <= seen:
                return None
            return self.n, self.starts.get(seen + 1, self.starts[min(self.starts)])

    def died_since(self, seen):
        with self.lock:
            return any(k > seen for k in self.deaths)


def signature(steps):
    return [(ident(s), s.get("npc"), s.get("name") if s["k"] == "S" else None) for s in steps]


def report_key(report):
    if not report:
        return report
    return {**report, "events": [(e.get("kind"), e.get("step")) for e in report.get("events") or ()]}


def plain(step):
    return {"k": EPIC_CODE.get(step["kind"]), "ids": step_ids(step), "inst": step.get("inst"), "at": step.get("at"),
            "name": step.get("questName"), "npc": step.get("npc"), "count": step.get("count"),
            **{k: step[k] for k in ("what", "key", "target", "need") if step.get(k)}}


def code(s):
    return f'{s["k"]}{".".join(str(i) for i in s["ids"])}' if s["ids"] else f'{s["k"]}{s.get("what")}:{s.get("npc")}'


def ident(s):
    if s["k"] == "D":
        return f'D@{round(s["at"][0])},{round(s["at"][1])}' if s.get("at") else "D"
    return f'{code(s)}#{s["target"]}' if s["k"] == "O" and s.get("target") else code(s)


def pair_up(a, b):
    free, pairs, rest = {}, {}, []
    for j, s in enumerate(b):
        free.setdefault(ident(s), []).append(j)
    for i, s in enumerate(a):
        got = free.get(ident(s))
        if got:
            pairs[i] = got.pop(0)
        else:
            rest.append(i)
    by_code = {}
    for js in free.values():
        for j in js:
            by_code.setdefault(code(b[j]), []).append(j)
    for i in rest:
        got = by_code.get(code(a[i])) if a[i]["k"] == "O" else None
        if got:
            pairs[i] = got.pop(0)
    return pairs


def plan_mode(mode):
    return mode if mode in ("safe", "fight") else "any"


def step_done(s, done, log):
    ids = s["ids"]
    if s["k"] == "S":
        return False
    if s["k"] == "P":
        return all(i in done or i in log for i in ids)
    if s["k"] == "T":
        return all(i in done for i in ids)
    if s["k"] == "O":
        return all(i in done or log.get(i) for i in ids)
    have = [i for i in ids if i in done or i in log]
    return bool(have) and all(i in done or log.get(i) for i in have)


def names(xs):
    xs = list(dict.fromkeys(x for x in xs if x))
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def chore_state(c):
    return c.get("errand") or {"game": c.get("facts")}


def shown_done(s, facts=None, me=None):
    return errands.shows_done(s, me if me is not None else {"game": facts}) is True


def chore_sig(s):
    return s.get("what"), s.get("key"), json.dumps(s.get("need") or {}, sort_keys=True)


def settled_chores(steps, states):
    return {chore_sig(s) for s, st in zip(steps, states or ()) if s["k"] == "S" and st in ("done", "skipped")}


def pending_chores(steps, states=(), facts=None, me=None):
    out = {}
    for i, s in enumerate(steps):
        if s["k"] != "S" or not (s.get("what") in NEEDS or ticks.declares(s.get("need"))):
            continue
        if (i < len(states) and states[i] in ("done", "skipped")) or shown_done(s, facts, me):
            continue
        out.setdefault(s["what"], []).append(s)
    return out


def restocks_due(live, plan, loaded):
    if not (live or {}).get("running"):
        return {}
    out = {}
    plan = plan or {}
    if plan.get("version") is not None and plan.get("version") == loaded:
        steps = (plan.get("epic") or {}).get("steps") or ()
        for s in pending_chores(steps, live.get("states") or ()).get("restock", ()):
            if s.get("key"):
                out.setdefault(s["key"].partition(":")[2], {k: s.get(k) for k in ("npc", "inst", "at")})
    for c in reversed(live.get("chores") or ()):
        if c.get("what") == "restock" and c.get("thing") and c.get("state") not in ("done", "skipped"):
            out[c["thing"]] = {k: c.get(k) for k in ("npc", "inst", "at")}
    return out


def new_chores(steps, pending, facts=None, me=None, settled=()):
    mine, out = pending_chores(steps, facts=facts, me=me), []
    for what, have in mine.items():
        have = [s for s in have if chore_sig(s) not in settled]
        extra = len(have) - len(pending.get(what, ()))
        if extra > 0:
            keys = {p.get("key") for p in pending.get(what, ())}
            out += ([s for s in have if s.get("key") not in keys] or have)[:extra]
    return out


def theirs(steps, me):
    owned = (me or {}).get("addon_chores") or ()
    return [s for s in steps if not (s["k"] == "S" and s.get("what") in owned)] if owned else list(steps)


def hidden_chores(steps, fresh):
    keys = {n.get("key") for n in fresh.get("errandNotes") or () if n.get("hidden")}
    return [s.get("name") or s.get("what") for s in steps if s["k"] == "S" and s.get("key") in keys]


def lead(steps):
    out = []
    for s in steps:
        if s["k"] != "S":
            break
        out.append(s)
    return out


def brought_up(before, after):
    pairs = pair_up(before, after)
    common = sorted(pairs, key=lambda i: pairs[i])
    rank = {i: r for r, i in enumerate(sorted(pairs))}
    out = []
    for r, i in enumerate(common):
        if before[i]["k"] == "P" and r < rank[i]:
            out.append(before[i].get("name"))
    return out


def moved_errands(before, after):
    was = {s.get("what"): s.get("npc") for s in lead(before)}
    return [s for s in lead(after) if s.get("what") in was and was[s["what"]] != s.get("npc")]


def errand_step(w):
    out = {"kind": "errand", "quest": None, "questName": w.get("name") or w.get("text"), "text": w.get("text"),
           "npc": w.get("npc"), "inst": w["inst"], "at": list(w["at"][:2] if w.get("guess") else w["at"])}
    return {**out, **{k: w[k] for k in ("what", "key", "need", "cost", "map", "zone", "min", "grind", "trip", "why")
                      if w.get(k) is not None}}


def run_order(left, game, moves):
    g2l = pair_up(game, left)
    placed = {m["step"] - 1 for m in moves if 0 < m["step"] <= len(game)}
    front, mine = {}, set()
    for m in moves:
        g = m["step"] - 1
        if g not in placed or g not in g2l or g2l[g] in mine:
            continue
        b = m["before"] - 1
        anchor = None if b < 0 or b in placed else next((g2l[a] for a in range(b, len(game)) if a not in placed and a in g2l), None)
        front.setdefault(anchor, []).append(g2l[g])
        mine.add(g2l[g])
    if not mine:
        return left
    out = []
    for i, s in enumerate(left):
        if i not in mine:
            out += [left[j] for j in front.get(i, ())] + [s]
    return out + [left[j] for j in front.get(None, ())]


def merge(left, planned, start, log=None, levels=None, level=None, was=None, ways=None, clocks=()):
    return planrepair.repair(left, planned, start, log, levels, level, was, ways, clocks)


class Settled:
    def __init__(self, wait=None):
        self.wait = GEAR_SETTLE if wait is None else wait
        self.seen = None

    def due(self, value, now):
        if value is None:
            return False
        if self.seen is None:
            self.seen = (value, now, False)
            return False
        was, since, due = self.seen
        if value != was:
            self.seen = (value, now, True)
            return False
        if due and now - since >= self.wait:
            self.seen = (value, since, False)
            return True
        return False


class EpicWatch:
    def __init__(self, shared, plan, dress, find_way, context, log=None, find_route=None, answers=None, unknown=None,
                 rewards=None, nexts=None, reckon=None, ways=None):
        self.shared, self.plan, self.dress, self.find_way, self.context, self.log = shared, plan, dress, find_way, context, log
        self.reckon, self.ways = reckon, ways
        self.find_route, self.answers, self.unknown = find_route, answers, unknown
        self.cv = threading.Condition()
        self.poked = False
        self.jobs = []
        self.looked = None
        self.last = None
        self.advice = None
        self.held = None
        self.starting = False
        self.wanted = None
        self.ways_at = 0.0
        self.jumps = Jumps()
        self.jump_seen = 0
        self.worn = Settled()
        self.rewards = rewards
        self.picks_from = None
        self.picks_worn = Settled()
        self.nexts = nexts
        self.next_from = None

    def moved(self, here, flags, now=None):
        if self.jumps.see(here, flags, time.time() if now is None else now):
            self.poke()

    def landing(self, c):
        got = self.jumps.since(self.jump_seen)
        here = tuple(c["here"][:3]) if got and c.get("here") else None
        if not here:
            return None
        n, start = got
        if start[0] == here[0] and math.hypot(here[1] - start[1], here[2] - start[2]) < JUMP_YARDS:
            self.jump_seen = n
            return None
        return n, here

    def poke(self):
        with self.cv:
            self.poked = True
            self.cv.notify_all()

    def ask_mode(self, key, mode, me):
        sh = self.shared
        epic = ((sh.data or {}).get("epic") or {}) if sh else {}
        mine = epic.get("key") == key and same_char(epic.get("char"), me) and not epic.get("closed")
        if not mine and not (sh and sh.working == key):
            return False
        self.queue(lambda: self.take_mode(key, plan_mode(mode), me))
        return True

    def take_mode(self, key, mode, me):
        sh = self.shared
        epic = (sh.data or {}).get("epic") or {}
        mine = epic.get("key") == key and same_char(epic.get("char"), me) and not epic.get("closed")
        if not mine and sh.working != key:
            return
        if mine and not (sh.working and sh.working_start) and sh.switch_back(key, mode, sh.loaded):
            self.wanted = self.held = None
            return
        self.wanted = {"key": key, "char": me, "mode": mode}
        self.poke()

    def queue(self, job):
        with self.cv:
            self.jobs.append(job)
            self.cv.notify_all()

    def pause(self, seconds, until_poked):
        end = time.time() + seconds
        while True:
            with self.cv:
                while not self.jobs and not (until_poked and self.poked):
                    left = end - time.time()
                    if left <= 0:
                        return False
                    self.cv.wait(left)
                jobs, self.jobs = self.jobs, []
                poked = until_poked and self.poked
                if poked:
                    self.poked = False
            for job in jobs:
                try:
                    job()
                except Exception:
                    if self.log:
                        self.log("epic watcher's job")
            if poked:
                return True

    def run(self):
        while True:
            poked = self.pause(CHECK_EVERY, True)
            if poked:
                self.pause(SOON, False)
            try:
                self.tick(forced=poked)
            except Exception:
                if self.log:
                    self.log("epic watcher")

    def tick(self, now=None, forced=True):
        now = now or time.time()
        c = self.context()
        sh = self.shared
        try:
            self.picks_look(c, now)
        except Exception:
            if self.log:
                self.log("reward picks")
        try:
            self.next_look()
        except Exception:
            if self.log:
                self.log("next zones")
        if sh and c.get("loaded"):
            sh.loaded = int(c["loaded"])
        if not sh or sh.working:
            if self.wanted:
                self.poke()
            return None
        epic = (sh.data or {}).get("epic")
        if not epic or epic.get("closed") or not same_char(epic.get("char"), c.get("me")):
            self.advice = self.held = self.wanted = None
            self.jump_seen = self.jumps.n
            return None
        w = self.wanted
        if w and (w["mode"] == (epic.get("mode") or "any") or w["key"] != epic.get("key") or not same_char(w["char"], epic.get("char"))):
            self.wanted = None
        if c.get("inside") or c.get("flying") or c.get("dead"):
            return None
        live = c.get("live") or {}
        self.starting = bool(sh.run_start) and int(c.get("loaded") or 0) < int(sh.run_start)
        on_loaded = bool(live.get("running")) and live.get("version") == c.get("loaded") and not self.starting
        blind = bool(live.get("running")) and not on_loaded
        live = live if on_loaded else {}
        if on_loaded:
            self.note_offers(c)
        ways = (repr(c.get("built")), now - self.ways_at >= WAYS_AGAIN) if epic.get("unbuilt") else None
        key = None if c.get("inputs") is None else (c["inputs"], (sh.data or {}).get("version"), repr(report_key(live)),
                                                      c.get("loaded"), repr(c.get("me")), repr(self.wanted), ways)
        wrote = None
        landing = self.landing(c)
        gear = self.gear_due(c.get("worn"), now)
        if forced or key is None or key != self.looked or landing or gear:
            wrote = self.keep_current(epic, live, c, now, landing, gear)
            self.looked = key
        self.advice = self.with_ways(self.hold(self.assess(c, live, now), blind), c)
        return wrote

    def note_offers(self, c):
        if not self.answers or not self.unknown:
            return
        who, done = c.get("who") or {}, c.get("done") or ()
        for qid in c.get("log") or ():
            giver = self.unknown(qid)
            if giver is not None:
                self.answers.note(qid, giver or None, who, done)

    def gear_due(self, worn, now):
        return self.worn.due(worn, now)

    def picks_look(self, c, now):
        if not self.rewards or not self.shared or not c:
            return False
        gear = self.picks_worn.due(c.get("worn"), now)
        wanted = self.rewards.wanted()
        if wanted is None or (wanted == self.picks_from and not gear):
            return False
        self.picks_from = wanted
        return self.shared.set_rewards(self.rewards.table(wanted))

    def next_look(self):
        if not self.nexts or not self.shared:
            return False
        wanted = self.nexts.wanted()
        if wanted is None or wanted == self.next_from:
            return False
        self.next_from = wanted
        return self.shared.set_next(self.nexts.table(wanted))

    def picks_changed(self, fresh):
        find = getattr(self.shared, "find_rewards", None)
        if not find:
            return False
        had = {tuple(s["ids"]): s.get("rw") for s in (self.shared.data or {}).get("epic", {}).get("steps") or ()
               if s.get("k") == "T"}
        now = {tuple(step_ids(s)): rw for s, rw in zip(fresh["steps"], find(fresh["steps"])) if s.get("kind") == "turnin"}
        same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        return any(not same(rw, had[q]) for q, rw in now.items() if q in had)

    def game_plan(self, c):
        loaded = self.shared.snapshot(c.get("loaded")) if c.get("loaded") else None
        if loaded and loaded.get("version") == c.get("loaded") and loaded.get("epic"):
            return loaded["epic"]
        return None

    def game_steps(self, c):
        game = self.game_plan(c)
        return game["steps"] if game else None

    def keep_current(self, epic, live, c, now=None, landing=None, gear=False):
        now = time.time() if now is None else now
        here = tuple(c["here"]) if c.get("here") else None
        anchor = tuple(epic["anchor"]) if epic.get("anchor") else here
        was = epic.get("mode") or "any"
        mode = (self.wanted or {}).get("mode") or was
        parked = set(live.get("parked") or ()) | (set(epic.get("parked") or ()) if self.starting else set())
        kept = {i for st in epic.get("steps") or () for i in st.get("ids") or ()}
        quests = self.plan(epic["key"], here or anchor, parked, kept)
        if not quests:
            self.jump_done(landing)
            return None
        done, log = c.get("done") or set(), c.get("log") or {}
        left = [s for s in epic["steps"] if not step_done(s, done, log)]
        game = self.game_steps(c) if live.get("moves") else None
        ordered = run_order(left, game, live["moves"]) if game else left
        level = (c.get("who") or {}).get("level")
        wrote_at = next((w["wl"] for w in ordered if w["k"] != "S" and isinstance(w.get("wl"), int)), None)
        merged = merge(ordered, quests["steps"], here, log, self.reckon, level, wrote_at, self.ways and self.ways(),
                       c.get("clocks") or ())
        steps, new, gone = merged if merged else (quests["steps"], [plain(s) for s in quests["steps"]], left)
        died = bool(landing) and self.jumps.died_since(self.jump_seen) and bool(merged)
        if died:
            again = planrepair.from_here(steps, here, self.reckon)
            died = [plain(s) for s in again] != [plain(s) for s in steps]
            steps = again
        held = copy.deepcopy(steps) if landing and merged else None
        fresh = self.dress(epic["key"], {**quests, "steps": steps}, here, **({"landed": True} if landing else {}))
        if not fresh:
            self.jump_done(landing)
            return None
        fsteps = [plain(s) for s in fresh["steps"] if s.get("at") and EPIC_CODE.get(s["kind"])]
        states = (live.get("states") or ()) if (self.shared.data or {}).get("version") == c.get("loaded") else ()
        me = chore_state(c)
        settled = settled_chores(self.game_steps(c) or (), live.get("states"))
        chores = theirs(new_chores(fsteps, pending_chores(epic["steps"], states, me=me), me=me, settled=settled), me)
        kept = parked if self.starting else ()
        up = brought_up([w for w in ordered if w["k"] != "S"], [plain(s) for s in steps]) if merged and not died else []
        if not new and not gone and not chores and mode == was:
            if died:
                return self.jump_done(landing, self.write(epic, fresh, anchor, here, "minor", [DIED], kept, mode))
            if up:
                return self.jump_done(landing, self.write(epic, fresh, anchor, here, "minor", [f"picks up {names(up)} on your way"]
                                                          + ([MOVED] if landing and moved_errands(left, fsteps) else []), kept, mode))
            moved = held is not None and self.after_jump(epic, quests, ordered, held, live, c, here)
            if moved:
                return self.jump_done(landing, self.write(epic, moved, anchor, here, "minor", [MOVED], kept, mode))
            self.jump_done(landing)
            hidden = hidden_chores(left, fresh)
            if hidden:
                return self.write(epic, fresh, anchor, here, "minor", [f"leaves out {names(hidden)}, which you hid"],
                                  kept, mode)
            if gear and self.picks_changed(fresh):
                return self.write(epic, fresh, anchor, here, "minor", [PICKS], kept, mode)
            if ordered != left and (self.shared.data or {}).get("version") != c.get("loaded"):
                back = names(game[m["step"] - 1].get("name") for m in live["moves"] if 0 < m["step"] <= len(game))
                return self.write(epic, fresh, anchor, here, "minor", [f"keeps {back} where you put it back in the game"],
                                  kept, mode)
            return self.ways_again(epic, fresh, anchor, here, kept, mode, now)
        if mode == was and signature(theirs(fsteps, me)) == signature(theirs(left, me)):
            self.jump_done(landing)
            return self.ways_again(epic, fresh, anchor, here, kept, mode, now)
        rating, reasons = self.judge(self.game_steps(c) or epic["steps"], fsteps, live, c)
        ways = self.ways_said(c, mode, was)
        if ways:
            rating, reasons = rating or "worth", reasons + [ways]
        if landing and moved_errands(left, fsteps):
            reasons = reasons + [MOVED]
        if died:
            reasons = reasons + [DIED]
        if up:
            reasons = reasons + [f"picks up {names(up)} on your way"]
        return self.jump_done(landing, self.write(epic, fresh, anchor, here, rating or "minor", reasons or ["has changed steps"],
                                                  kept, mode, switched=mode != was and not (new or gone or chores),
                                                  against=c.get("loaded") if self.game_steps(c) else None))

    def after_jump(self, epic, quests, ordered, held, live, c, here):
        mine = [w for w in ordered if w["k"] != "S"]
        pairs, steps, i = pair_up(mine, [plain(s) for s in held]), [], 0
        for w in ordered:
            if w["k"] == "S":
                steps.append(errand_step(w))
                continue
            if i in pairs:
                steps.append(held[pairs[i]])
            i += 1
        states = live.get("states") or ()
        done = {code(g) for g, st in zip(self.game_steps(c) or (), states) if g["k"] == "S" and st in ("done", "skipped")}
        brief = epic.get("brief") or ()
        notes = {"errandNotes": [{"text": t, **({"brief": brief[k]} if k < len(brief) and brief[k] else {})}
                                 for k, t in enumerate(epic.get("notes") or ())]
                 + [{"text": t, "hidden": True} for t in epic.get("hidden") or ()],
                 "campLater": [{"text": e["text"], "wall": {"kind": e["wall"], **({"offer": e["offer"]} if e.get("offer") else {}),
                                                            **({"prof": e["prof"]} if e.get("prof") else {})}}
                               for e in epic.get("later") or ()]}
        fresh = self.dress(epic["key"], {**quests, "steps": steps, **notes}, here, chores=False, landed=True,
                           leave=lambda st: code(plain(st)) in done)
        after = [plain(s) for s in fresh["steps"] if s.get("at") and EPIC_CODE.get(s["kind"])]
        return fresh if moved_errands(ordered, after) else None

    def jump_done(self, landing, wrote=True):
        if landing and wrote is not None:
            self.jump_seen = landing[0]
        return wrote

    def ways_again(self, epic, fresh, anchor, here, kept, mode, now):
        if not epic.get("unbuilt") or now - self.ways_at < WAYS_AGAIN:
            return None
        self.ways_at = now
        n = epic["unbuilt"]
        return self.write(epic, fresh, anchor, here, "minor", [f"has legs for {n} steps that had none"], kept, mode, fewer=n)

    def write(self, epic, fresh, anchor, here, rating, reasons, parked=(), mode=None, switched=False, fewer=None,
              against=None):
        mode = mode or epic.get("mode") or "any"
        meta = {"name": epic.get("name"), "char": epic.get("char"), "anchor": list(anchor) if anchor else None,
                "from": list(here) if here else None,
                "mode": mode, "close": epic.get("close"),
                "craft": epic.get("craft"),
                "rating": rating, "reasons": reasons, "against": against, "fresh": True if self.starting else None,
                "maybe": fresh.get("maybe"),
                "next": fresh.get("next"),
                "parked": sorted(parked) or None, "switched": switched or None, "fewer": fewer,
                **plan_notes(fresh)}
        still = lambda: (self.wanted or {}).get("mode", mode) == mode and (self.shared.data or {}).get("epic") is epic
        if not self.shared.start_epic(epic["key"], fresh["steps"], self.find_way(mode), meta, self.find_route and self.find_route(mode),
                                      still):
            return None
        self.last = (rating, reasons)
        return self.last

    def ways_said(self, c, mode, was):
        game = self.game_plan(c)
        return WAYS[mode] if mode != ((game.get("mode") if game else was) or "any") else None

    def with_ways(self, advice, c):
        game = self.game_plan(c) if advice else None
        mode = ((self.shared.data or {}).get("epic") or {}).get("mode") or "any"
        if not game or (game.get("mode") or "any") == mode:
            return advice
        return {**advice, "rating": "worth" if advice["rating"] == "minor" else advice["rating"],
                "reasons": [r for r in advice["reasons"] if r != SMALL] + [WAYS[mode]]}

    def judge(self, base, latest, live, c):
        done, log = c.get("done") or set(), c.get("log") or {}
        states = live.get("states") or ()
        reasons, rating = [], None
        unoffered = set(live.get("notOffered") or ())
        for s, st in zip(base, states):
            if st != "blocked" or (s["ids"] and s["ids"][0] in unoffered):
                continue
            why = f"{s.get('name') or 'A quest'} failed"
            if why not in reasons:
                reasons.append(why)
        if reasons:
            rating = "needed"
        todo = [s for s in base if s["k"] != "S" and not step_done(s, done, log)]
        mine = [s for s in latest if s["k"] != "S" and not step_done(s, done, log)]
        paired = pair_up(mine, todo)
        quests = {i for s in todo for i in s["ids"]}
        holds = {i for s in mine for i in s["ids"]}
        takes = [s.get("name") for s in mine if s["k"] == "P" and s["ids"][0] not in quests]
        clocks = set(c.get("clocks") or ())
        timed = [s.get("name") for s in mine if clocks & set(s["ids"]) and not quests & set(s["ids"])]
        if timed:
            rating = "needed"
            takes += timed
        again = [s.get("name") for i, s in enumerate(mine) if i not in paired and set(s["ids"]) <= quests]
        drops = [s.get("name") for s in todo if not set(s["ids"]) & holds]
        me = chore_state(c)
        chores = theirs(new_chores(latest, pending_chores(base, states, me=me), me=me, settled=settled_chores(base, states)), me)
        for words, what in (("takes in", takes), ("goes back to", again), ("leaves out", drops),
                            ("adds", [s.get("name") or s.get("what") for s in chores])):
            if what:
                reasons.append(f"{words} {names(what)}")
                rating = rating or "worth"
        return (rating, reasons) if rating else (None, [])

    def assess(self, c, live, now):
        data = self.shared.data or {}
        latest_v, loaded_v = data.get("version"), c.get("loaded")
        epic = data.get("epic")
        if not epic or not loaded_v or loaded_v == latest_v:
            return None
        game = self.game_steps(c)
        done, log = c.get("done") or set(), c.get("log") or {}
        latest = [s for s in epic["steps"] if not step_done(s, done, log)]
        if game is None:
            return {"rating": "worth", "reasons": ["replaces an old plan in the game"], "version": latest_v, "loaded": loaded_v, "at": now}
        rating, reasons = self.judge(game, latest, live, c)
        if not rating:
            rating, reasons = "minor", [SMALL]
        return {"rating": rating, "reasons": reasons, "version": latest_v, "loaded": loaded_v, "at": now}

    def hold(self, advice, blind=False):
        if not advice:
            self.held = None
            return None
        h, rank = self.held, RANK.get(advice["rating"], 0)
        if blind and h and h["loaded"] == advice["loaded"] and h["version"] == advice["version"] and RANK[h["rating"]] >= rank:
            return {**advice, "rating": h["rating"], "reasons": h["reasons"]}
        self.held = {"loaded": advice["loaded"], "version": advice["version"], "rating": advice["rating"],
                     "reasons": advice["reasons"]} if rank else None
        return advice
