# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import contextlib
import contextvars
import itertools
import threading
import time

import carried

RING = 1024
NEXT = 8
_NOTE = contextvars.ContextVar("picks_note", default=None)
_CARRIED_BY = carried
_runs = {}
_lock = threading.Lock()
_ids = itertools.count(1)


class Run:

    def __init__(self, key):
        self.key, self.id, self.seq, self.done, self.ran = key, next(_ids), 0, False, True
        self.ring, self.counts = collections.deque(maxlen=RING), collections.Counter()
        self.began, self.ended = time.time(), None
        self.rows = self.listing = self.held = None
        self.listed = None
        self.fresh = None
        self.lock = threading.Lock()

    def add(self, e, facts):
        if e == "list":
            self.rows, self.listing, self.fresh = facts["rows"], facts["listing"], facts.get("fresh")
            facts = {}
        elif e == "held":
            self.held, facts = facts["held"], {"count": len(facts["held"])}
        self.seq += 1
        self.counts[e] += 1
        if e == "sell":
            self.counts["sell." + (facts.get("way") or "none")] += 1
        self.ring.append({**facts, "n": self.seq, "e": e, "t": round((time.time() - self.began) * 1000)})

    def end(self, ran=True):
        self.done, self.ran, self.ended = True, ran, time.time()


def note(e, **facts):
    run = _NOTE.get()
    if run is None:
        return
    try:
        run.add(e, facts)
    except Exception:
        pass


def listening():
    return _NOTE.get() is not None


def weighed(key, cand, kept, rows):
    if _NOTE.get() is None:
        return
    if cand is None:
        note("aside", i=key, why="ladder" if sum(1 for r in rows if r[3] > 0 and r[2] > 0) < 2 else "figures")
        return
    b = cand["best"]
    note("good" if b["mean"] > 0 else "bad", i=key, cost=round(b["cost"]), gold=round(b["mean"]), units=b["units"],
         **({"kept": 1} if kept else {}))


def funded(cand, k, more, spent):
    if _NOTE.get() is not None:
        note("fund", i=cand["key"], units=cand["curve"][k - 1].get("units"), more=round(more), spent=round(spent))


def begin(folder, which):
    run = Run((folder, which))
    with _lock:
        _runs[(folder, which)] = run
    return run


@contextlib.contextmanager
def noting(run):
    token = _NOTE.set(run)
    try:
        yield run
    finally:
        _NOTE.reset(token)


def since(folder, which, n=0):
    with _lock:
        run = _runs.get((folder, which))
    if run is None:
        return None
    steps = [s for s in list(run.ring) if s["n"] > n]
    first = steps[0]["n"] if steps else run.seq + 1
    return {"run": run.id, "seq": run.seq, "done": run.done, "ran": run.ran, "counts": dict(run.counts),
            "listed": len(_listed(run)), "fresh": run.fresh, "held": len(run.held or ()), "skipped": max(0, first - n - 1),
            "steps": steps, "next": _next(run)}


def _listed(run):
    with run.lock:
        if run.listed is None and run.rows is not None:
            run.listed = [r["item"] for r in run.rows if run.listing.get(r["item"]) and r.get("sales")]
        return run.listed or []


def _next(run):
    c = run.counts
    if run.held is not None:
        k = c["sell"]
        return list(itertools.islice(run.held, k, k + NEXT))
    k = c["good"] + c["bad"] + c["aside"]
    return _listed(run)[k:k + NEXT]
