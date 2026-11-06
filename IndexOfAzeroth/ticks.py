# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os
import time
import zlib
from collections import Counter

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
PROFESSIONS = os.path.join(ROOT, "data", "professions.json")
CONDITIONS = ("items", "recipes", "auras", "skills", "caps")


def declares(need):
    return isinstance(need, dict) and any(need.get(k) for k in CONDITIONS)


def need_met(need, facts, now=None):
    if not declares(need):
        return None
    now = time.time() if now is None else now
    facts = facts or {}
    said = []
    items = facts.get("items")
    for entry in need.get("items") or ():
        item, count = int(entry[0]), int(entry[1]) if len(entry) > 1 else 1
        said.append(None if items is None else items.get(item, 0) >= count)
    known = facts.get("recipes") or {}
    said += [known.get(int(spell)) for spell in need.get("recipes") or ()]
    auras = facts.get("auras") or {}
    for spell in need.get("auras") or ():
        ends = auras.get(int(spell), "unknown")
        said.append(None if ends == "unknown" else ends is not False and (ends is None or ends > now))
    skills = facts.get("skills")
    said += [None if skills is None else skills.get(name, 0) >= rank for name, rank in need.get("skills") or ()]
    caps = facts.get("caps")
    said += [None if caps is None else caps.get(name, 0) >= cap for name, cap in need.get("caps") or ()]
    if False in said:
        return False
    return None if None in said else True


def watch_list(data):
    if not (data or {}).get("camping"):
        return None
    recipes, profs = data.get("recipes") or {}, data.get("professions") or {}
    p = camp_parts(data)
    lists = {"auras": sorted({int(a) for a in data.get("auras") or {}} | set(CAMPFIRE_AURAS)),
             "recipes": [[s, (profs.get(str(recipes.get(str(s), {}).get("prof"))) or {}).get("n") or ""] for s in p["spells"]],
             "items": sorted(set(p["made"].values()) | p["blueprints"] | p["woods"]),
             "fires": fire_kits(data, p)}
    return {"check": zlib.crc32(json.dumps(lists, sort_keys=True).encode()) & 0xFFFF or 1, **lists}


def camp_parts(data):
    recipes, items = (data or {}).get("recipes") or {}, (data or {}).get("items") or {}
    spells = sorted({int(s) for v in ((data or {}).get("camping") or {}).values() for s in v.get("recipes") or ()})
    made = {s: int(recipes[str(s)]["makes"][0]) for s in spells if (recipes.get(str(s)) or {}).get("makes")}
    uses = {s: (items.get(str(i)) or {}).get("use") or {} for s, i in made.items()}
    shared = Counter(u["category"] for u in uses.values() if u.get("category")).most_common(1)
    fires = [s for s, u in uses.items() if u.get("category") and shared and u["category"] != shared[0][0]]
    return {"spells": spells, "made": made, "fires": fires,
            "woods": {int(r[0]) for s in fires for r in recipes[str(s)].get("reagents") or ()},
            "blueprints": {int(i) for i, e in items.items() if e.get("teaches") in spells}}


def fire_kits(data, parts):
    items, out = (data or {}).get("items") or {}, []
    for s in parts["fires"]:
        kit = items.get(str(parts["made"][s])) or {}
        use = kit.get("use") or {}
        if use.get("spell"):
            out.append([int(use["spell"]), int(use.get("lasts") or 0), kit.get("n") or ""])
    return sorted(out)


def watched_fires():
    return {f[0]: (f[1], f[2]) for f in (_watch["list"] or {}).get("fires") or ()}


_watch = {"stamp": None, "list": None}


def load_watch(path=None):
    path = path or PROFESSIONS
    stamp = store.stamp(path)
    if stamp is None:
        return None
    if _watch["stamp"] != (path, stamp):
        _watch.update(stamp=(path, stamp), list=watch_list(store.load_json(path, {})))
    return _watch["list"]


def watched_items():
    return (_watch["list"] or {}).get("items") or ()


def game_facts(hub, watch=None):
    watched = (getattr(hub, "extra", None) or {}).get("watched")
    me = hub.characters.playing()
    out = {"items": hub.characters.bags_now(), "recipes": {}, "auras": {}, "cooldowns": {},
           "skills": {p["name"]: p.get("rank") or 0 for p in me.get("professions") or ()} if isinstance(me, dict) else None,
           "caps": {p["name"]: p.get("max") or 0 for p in me.get("professions") or ()} if isinstance(me, dict) else None}
    if not watched:
        return out
    watch = load_watch() if watch is None else watch
    same = bool(watch) and watched.get("check") == watch["check"]
    if same and watched.get("recipesWhole"):
        out["recipes"] = {spell: False for spell, _ in watch["recipes"]}
    out["recipes"].update({spell: True for spell in watched.get("recipes") or ()})
    if same and watched.get("aurasWhole"):
        out["auras"] = {spell: False for spell in watch["auras"]}
    out["auras"].update({a["id"]: a.get("ends") for a in watched.get("auras") or ()})
    out["cooldowns"] = {c["id"]: c.get("ends") for c in watched.get("cooldowns") or ()}
    import camping
    camp = camping.load().aura
    if out["auras"].get(camp, False) is not False:
        hub.characters.camped()
    return out


CAMPFIRE_AURAS = (1229739, 1283391)


def campfire_on(hub, now=None):
    now = time.time() if now is None else now
    watched = (getattr(hub, "extra", None) or {}).get("watched") or {}
    for a in watched.get("auras") or ():
        ends = a.get("ends")
        if a.get("id") in CAMPFIRE_AURAS and (ends is None or ends > now):
            return True
    return False


def named_items(steps):
    return sorted({int(e[0]) for s in steps or () for e in ((s.get("need") or {}).get("items") or ())})


def inputs(hub, now=None, watch=None, named=()):
    now = time.time() if now is None else now
    watch = load_watch() if watch is None else watch
    facts = game_facts(hub, watch)
    items = facts["items"]
    counted = sorted(set((watch or {}).get("items") or ()) | set(named))
    return {"items": None if items is None else {i: items.get(i, 0) for i in counted},
            "recipes": sorted(s for s, known in facts["recipes"].items() if known),
            "auras": sorted(s for s, ends in facts["auras"].items() if ends is not False and (ends is None or ends > now)),
            "cooldowns": sorted(i for i, ends in facts["cooldowns"].items() if ends is None or ends > now)}
