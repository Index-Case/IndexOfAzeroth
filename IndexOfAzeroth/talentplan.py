# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import glob
import os
import threading

import savedvars
import store
import upgrades

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILDS = os.path.join(ROOT, "data", "talentbuilds.json")
SAVED_NAME = "IndexOfAzeroth.lua"
SAVED_EVERY = 5
FIRST_POINT = 10

_builds = {"stamp": None, "data": {}}


def builds():
    stamp = store.stamp(BUILDS)
    if _builds["stamp"] != stamp:
        _builds.update(data=store.load_json(BUILDS, {}), stamp=stamp)
    return _builds["data"]


def node_trees(trees):
    return {t["node"]: (i, t) for i, tree in enumerate(trees, 1) for t in tree["talents"]}


def open_now(point, taken, nodes):
    node, rank = point
    talent = nodes[node][1]
    return (taken.get(node, 0) == rank - 1 and rank <= talent["ranks"]
            and sum(taken.get(n, 0) for n in talent["counts"]) >= talent["spent"]
            and all(taken.get(n, 0) >= nodes[n][1]["ranks"] for n in talent["needs"] if n in nodes))


def plan(order, ranks, nodes):
    have, left = dict(ranks), []
    for n in order:
        if n not in nodes:
            continue
        if have.get(n, 0) > 0:
            have[n] -= 1
        else:
            left.append(n)
    taken, out = {n: r for n, r in ranks.items() if n in nodes}, []
    while left:
        i = next((i for i, n in enumerate(left) if open_now((n, taken.get(n, 0) + 1), taken, nodes)), None)
        if i is None:
            break
        n = left.pop(i)
        out.append(n)
        taken[n] = taken.get(n, 0) + 1
    return out


def live_ranks(saved, tree_points, order, nodes):
    ranks = {n: r for n, r in (saved or {}).items() if n in nodes}
    counted = [0] * len(tree_points or ())
    for n, r in ranks.items():
        if nodes[n][0] <= len(counted):
            counted[nodes[n][0] - 1] += r
    for t, (now, had) in enumerate(zip(tree_points or (), counted), 1):
        if now < had:
            ranks = {n: r for n, r in ranks.items() if nodes[n][0] != t}
            counted[t - 1] = 0
    more = [max(0, now - had) for now, had in zip(tree_points or (), counted)]
    assumed = 0
    while any(more):
        step = next((n for n in plan(order, ranks, nodes) if more[nodes[n][0] - 1] > 0), None)
        if step is None:
            break
        ranks[step] = ranks.get(step, 0) + 1
        more[nodes[step][0] - 1] -= 1
        assumed += 1
    return ranks, assumed


def your_build(class_builds, tree_points, cls, pick=None):
    class_builds = class_builds or []
    picked = next((b for b in class_builds if pick and b.get("key") == pick), None)
    if picked:
        return picked
    nums = {f"tree{i}Points": p for i, p in enumerate(tree_points or (), 1)}
    tree = upgrades.spec_tree(nums) or upgrades.LEVELING_TREE.get(cls)
    mine = [b for b in class_builds if b.get("tree") == tree]
    if not mine:
        return class_builds[0] if class_builds else None
    return max(mine, key=lambda b: len(b.get("roles") or ()))


def step_levels(count, level, unspent):
    unspent = max(0, unspent or 0)
    after = max(level, FIRST_POINT - 1)
    return [level if i < unspent else after + i - unspent + 1 for i in range(count)]


def talent_plan(c, cls, class_builds, nums, saved, level, pick=None):
    trees = (c or {}).get("trees") or []
    points = [int(nums.get(f"tree{t}Points") or 0) for t in range(1, len(trees) + 1)] if nums else []
    b = your_build(class_builds, points, cls, pick)
    if not trees or not b:
        return None
    nodes = node_trees(trees)
    ranks, assumed = live_ranks(saved, points, b["order"], nodes) if saved is not None else ({}, 0)
    left = plan(b["order"], ranks, nodes)
    taken, steps = dict(ranks), []
    for n, at in zip(left, step_levels(len(left), level or 1, nums.get("talentPoints") if nums else 0)):
        taken[n] = taken.get(n, 0) + 1
        t = nodes[n][1]
        steps.append({"level": at, "node": n, "id": t.get("id"), "name": t.get("name"), "icon": t.get("icon"),
                      "rank": taken[n], "ranks": t["ranks"], "tree": nodes[n][0]})
    levels = {}
    for n in dict.fromkeys(n for n in b["order"] if n in nodes):
        had = min(ranks.get(n, 0), b["order"].count(n))
        levels[str(n)] = [None] * had + [s["level"] for s in steps if s["node"] == n]
    fields = ("key", "name", "note", "roles", "tree")
    return {"build": {k: b.get(k) for k in fields}, "known": saved is not None,
            "assumed": assumed, "next": steps[0] if steps else None, "steps": steps,
            "ranks": {str(n): r for n, r in ranks.items()}, "levels": levels, "picked": bool(pick) and b.get("key") == pick,
            "builds": [{k: x.get(k) for k in fields} for x in class_builds or ()]}


class TalentRanks:

    def __init__(self):
        self.lock, self.seen, self.chars = threading.Lock(), {}, {}

    def saved_files(self, wtf):
        return sorted(glob.glob(os.path.join(wtf, "Account", "*", "SavedVariables", SAVED_NAME)))

    def take(self, table):
        changed = []
        for key, rec in (table or {}).items():
            if not isinstance(rec, dict) or not isinstance(rec.get("ranks"), dict):
                continue
            ranks = {int(n): int(r) for n, r in rec["ranks"].items() if str(n).isdigit() and isinstance(r, (int, float)) and r > 0}
            with self.lock:
                had = self.chars.get(key)
                if had and (had.get("at") or 0) > (rec.get("at") or 0):
                    continue
                if had != {"at": rec.get("at"), "ranks": ranks}:
                    self.chars[key] = {"at": rec.get("at"), "ranks": ranks}
                    changed.append(key)
        return changed

    def check_saved(self, wtf):
        changed = []
        for path in self.saved_files(wtf) if wtf else ():
            stamp = store.stamp(path)
            if stamp is None or self.seen.get(path) == stamp:
                continue
            self.seen[path] = stamp
            db = savedvars.read(path).get("IndexOfAzerothDB")
            if isinstance(db, dict) and isinstance(db.get("talents"), dict):
                changed += self.take(db["talents"])
        return changed

    def ranks(self, key):
        with self.lock:
            got = self.chars.get(key)
            return dict(got["ranks"]) if got else None

    def watch_saved(self, wtf_dir, log_error, stop=None, every=SAVED_EVERY):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.check_saved(wtf_dir())
            except Exception:
                log_error("reading the talent ranks from the SavedVariables")
            stop.wait(every)


