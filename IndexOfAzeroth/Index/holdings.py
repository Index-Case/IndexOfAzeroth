# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
from collections import namedtuple

import errands
import plansteps

Held = namedtuple("Held", "flights quests items")
LIVE = Held(frozenset(), frozenset(), frozenset())
NONE = frozenset()


def means_of(taxi, means, held):
    if not held or held == LIVE:
        return taxi, means
    if held.flights:
        taxi = dict(taxi or {})
        taxi["ids"] = sorted(set(taxi.get("ids") or ()) | held.flights)
    if held.quests or held.items and means.get("bags") is not None:
        means = dict(means)
        if held.quests:
            means["done"] = set(means.get("done") or ()) | held.quests
        if held.items and means.get("bags") is not None:
            means["bags"] = {**means["bags"], **{i: max(1, means["bags"].get(i) or 0) for i in held.items}}
    return taxi, means


def needs_of(legs, held, names=None):
    flights, quests, items = [], [], []
    for leg in legs or ():
        for node in leg.get("hops") or () if leg.get("vehicle") == "flight" else ():
            if node in held.flights and node not in flights:
                flights.append(node)
        needs = leg.get("needs") or {}
        if needs.get("quest") in held.quests and needs["quest"] not in quests:
            quests.append(needs["quest"])
        if needs.get("item") in held.items and needs["item"] not in items:
            items.append(needs["item"])
    out = {"f": [{"node": n, "name": (names or {}).get(n)} for n in flights]} if flights else {}
    return {**out, **({"q": quests} if quests else {}), **({"i": items} if items else {})}


class Holdings:

    def __init__(self, learnable=None, ways=None, rewards=None):
        self.asked, self.found = learnable, None
        self.ways_asked, self.named = ways, None
        self.rewards = rewards or (lambda qid: ())
        self.near = {}
        self.kept = {}

    @property
    def learnable(self):
        if self.found is None:
            self.found = [(node, tuple(at[:3])) for node, at in (self.asked() if self.asked else ())]
        return self.found

    @property
    def needed(self):
        if self.named is None:
            needs = [w.get("needs") or {} for w in (self.ways_asked() if self.ways_asked else ())]
            self.named = (frozenset(n["quest"] for n in needs if n.get("quest")),
                          frozenset(n["item"] for n in needs if n.get("item")))
        return self.named

    def gains_of(self, step, at):
        kept = self.kept.get(id(step))
        if kept is not None and kept[0] is step and kept[1] == at:
            return kept[2]
        own = (step.get("need") or {}).get("node") if step.get("what") == "flightpath" else None
        own = frozenset((own,)) if own is not None else NONE
        passing, quests, items = NONE, NONE, NONE
        if at and step.get("kind") != "errand" and self.learnable:
            key = tuple(at[:3])
            near = self.near.get(key)
            if near is None:
                near = self.near[key] = tuple((node, spot) for node, spot in self.learnable
                                              if errands.learns_flight({}, key, spot))
            passing = frozenset(node for node, spot in near if errands.learns_flight(step, key, spot))
        if step.get("kind") == "turnin" and step.get("quest") is not None and any(self.needed):
            quests = frozenset((step["quest"],)) & self.needed[0]
            items = frozenset(self.rewards(step["quest"]) or ()) & self.needed[1]
        got = (own, passing, quests, items) if own or passing or quests or items else None
        self.kept[id(step)] = (step, at, got)
        return got

    def after(self, held, step, at, next_inside=False):
        got = self.gains_of(step, at)
        if got is None:
            return held
        flights = got[0] | (NONE if next_inside else got[1])
        quests, items = got[2], got[3]
        if flights <= held.flights and quests <= held.quests and items <= held.items:
            return held
        return Held(held.flights | flights, held.quests | quests, held.items | items)

    def along(self, steps, spots=None, only=None):
        spots = [plansteps.spot(s) for s in steps] if spots is None else spots
        n = len(steps)
        out = [LIVE] * (n + 1)
        held, runs, since = LIVE, None, []
        for k in range(n) if only is None else only:
            got = self.gains_of(steps[k], spots[k])
            if got is None:
                continue
            if got[1] and runs is None:
                runs = plansteps.timed_runs(steps)
            nxt = self.after(held, steps[k], spots[k], bool(got[1]) and k + 1 in runs)
            if nxt is not held:
                held = nxt
                since.append((k + 1, held))
        for (first, h), (stop, _) in zip(since, since[1:] + [(n + 1, None)]):
            out[first:stop] = [h] * (stop - first)
        return out

    def giving(self, places):
        return {k for k, ps in enumerate(places) if any(self.gains_of(st, sp) for st, sp in ps)}

    def openers(self, side, race, means, givers):
        done, bags = set(means.get("done") or ()), means.get("bags")
        out = []
        for way in self.ways_asked() if self.ways_asked else ():
            needs = way.get("needs") or {}
            if set(needs) - {"quest", "item"} or way.get("side") not in (None, side) \
                    or way.get("races") and not race & way["races"] or needs.get("item") and bags is None:
                continue
            quests = {needs["quest"]} - done if needs.get("quest") else set()
            if needs.get("item") and bags is not None and not bags.get(needs["item"]):
                by = sorted(givers(needs["item"]) or ())
                if not by:
                    continue
                quests.add(by[0])
            if not quests:
                continue
            items = frozenset(i for q in quests for i in self.rewards(q) or ()) & self.needed[1]
            out.append((way, frozenset(quests), Held(NONE, frozenset(quests) & self.needed[0], items)))
        return out
