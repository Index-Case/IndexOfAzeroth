# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os
import threading
import time

import game
import icons
import mainstores
import moblevels
import store
from itemtips import ItemTips
from wordparts import F

ROOT = os.path.dirname(os.path.abspath(__file__))


ICONS = mainstores.path("icons")

ICON_CACHE = mainstores.path("iconcache")


def load_class_spells():
    return store.load_json(os.path.join(ROOT, "data", "classspells.json"), {})


TRAINER_PRICES = os.path.join(ROOT, "data", "trainerprices.json")


def load_trainer_prices():
    return seen_builds(store.load_json(mainstores.standing(TRAINER_PRICES), {}))


def recipe_prices(prices, recipes, build_at=None):
    if build_at is None:
        import clientfiles
        build_at = clientfiles.build_at
    seen = []
    for spell, r in (recipes or {}).items():
        said = (r or {}).get(F) or {}
        if said.get("cost") is not None:
            seen.append((int(spell), said["cost"], said.get("build"), (0,)))
    for t in ((prices or {}).get("professions") or {}).values():
        build = build_at(t.get("at") or 0)
        for s in t.get("services") or ():
            if s.get("spell") and s.get("cost") is not None:
                seen.append((int(s["spell"]), s["cost"], build, (1, t.get("at") or 0)))
    return {spell: {"cost": cost, "build": build} for spell, (cost, build) in newest_seen(seen).items()}


def newest_seen(seen):
    out, best = {}, {}
    for key, price, build, rank in seen:
        k = (game.version_key(build), rank)
        if key not in best or k > best[key]:
            best[key], out[key] = k, (price, build)
    return out


def shipped_class_prices(prices):
    levels, builds = prices.get("levels") or {}, prices.get("builds") or {}
    return {cid: {sid: [(levels.get(cid) or {}).get(sid), copper, (builds.get(cid) or {}).get(sid)]
                  for sid, copper in sorted(costs.items(), key=lambda kv: int(kv[0]))}
            for cid, costs in sorted((prices.get("classes") or {}).items(), key=lambda kv: int(kv[0])) if costs}


def class_sightings(shipped, own):
    seen = [((cid, sid), (level, copper), build, 0)
            for cid, rows in (shipped or {}).items() for sid, (level, copper, build) in rows.items()]
    own = own or {}
    for cid, costs in (own.get("classes") or {}).items():
        for sid, copper in costs.items():
            seen.append(((cid, sid), (((own.get("levels") or {}).get(cid) or {}).get(sid), copper),
                         ((own.get("builds") or {}).get(cid) or {}).get(sid), 1))
    out = {"classes": {}, "levels": {}, "builds": {}}
    for (cid, sid), ((level, copper), build) in newest_seen(seen).items():
        out["classes"].setdefault(cid, {})[sid] = copper
        out["levels"].setdefault(cid, {})[sid] = level
        out["builds"].setdefault(cid, {})[sid] = build
    return out


def seen_builds(prices):
    import clientfiles
    seen = prices.get("seen") or {}
    when = {}
    for npc, spells in (prices.get("trainers") or {}).items():
        at = (seen.get(npc) or {}).get("at") or 0
        for sid in spells:
            when[str(sid)] = max(when.get(str(sid), 0), at)
    for cid, costs in (prices.get("classes") or {}).items():
        mine = prices.setdefault("builds", {}).setdefault(cid, {})
        for sid in costs:
            if sid not in mine:
                mine[sid] = clientfiles.build_at(when.get(sid, 0))
    return prices


_icon_index = {"mtime": None, "names": {}}

_wanted = {"names": None, "lock": threading.Lock()}

INDEX_LOOK = 60
_indexed = {"at": float("-inf"), "tried": set(), "lock": threading.Lock()}
_unmade = set()


def icon_names():
    index_install()
    path = os.path.join(ICONS, "index.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _icon_index["mtime"] != mtime:
        _icon_index.update(mtime=mtime, names=store.load_json(path, {}).get("names", {}))
    return _icon_index["names"]


def index_install():
    now = time.monotonic()
    if now - _indexed["at"] < INDEX_LOOK or mainstores.in_main(ICONS):
        return
    with _indexed["lock"]:
        if now - _indexed["at"] < INDEX_LOOK:
            return
        _indexed["at"] = now
        try:
            build = game.installed_version()
        except (OSError, ValueError, game.GameNotFound):
            return
        path = os.path.join(ICONS, "index.json")
        if build in _indexed["tried"] or (store.load_json(path, {}) or {}).get("build") == build:
            return
        _indexed["tried"].add(build)
        try:
            names = icons.names(build, stored=True)
        except (OSError, ValueError, KeyError):
            return
        store.save_json(path, {"build": build, "names": names}, indent=None)


def make_icon(fid):
    fid = int(fid)
    if fid in _unmade or mainstores.in_main(ICONS):
        return False
    if icons.make(fid, out=ICONS):
        return True
    _unmade.add(fid)
    return False


def note_wanted(name):
    with _wanted["lock"]:
        if mainstores.in_main(ICONS):
            return
        path = os.path.join(ICONS, "wanted.json")
        if _wanted["names"] is None:
            _wanted["names"] = set(store.load_json(path, []))
        if name in _wanted["names"] or len(_wanted["names"]) >= 2000:
            return
        _wanted["names"].add(name)
        os.makedirs(ICONS, exist_ok=True)
        store.save_json(path, sorted(_wanted["names"]), indent=None)


def stored_icon(size, name=None, fid=None):
    names = icon_names()
    fid = fid or names.get(name)
    path = fid and os.path.join(ICONS, str(size), f"{fid}.jpg")
    if path and (os.path.exists(path) or make_icon(fid) and os.path.exists(path)):
        return True, path
    lacked = fid and icons.shipped(fid, size)
    if lacked:
        return True, lacked
    old = (os.path.join(ICON_CACHE, f"f{fid}.jpg") if size == 64 and fid
           else os.path.join(ICON_CACHE if size == 36 else os.path.join(ICON_CACHE, "large"), f"{name}.jpg") if name else None)
    if old and os.path.exists(old):
        return True, old
    note_wanted(name or f"f{fid}")
    q = names.get("inv_misc_questionmark")
    for path in (q and os.path.join(ICONS, str(size), f"{q}.jpg"), os.path.join(ICON_CACHE, "inv_misc_questionmark.jpg")):
        if path and os.path.exists(path):
            return False, path
    return False, None


BUILD_CACHE = os.path.join(ROOT, "data", "buildcache")

ITEM_TIPS = ItemTips()
SPELL_TIPS = ItemTips("spell")


_tables = {}


def client_table(name, key):
    path = os.path.join(ROOT, "data", name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, {}, {}
    got = _tables.get(name)
    if not got or got[0] != mtime:
        data = store.load_json(path, {}).get(key, {})
        got = _tables[name] = (mtime, data, {k.lower(): v for k, v in data.items()})
    return got


def spell_icons(names):
    _, _, lower = client_table("spells.json", "spells")
    return {n: lower[n.lower()] for n in names if n.lower() in lower}


def item_name(item):
    return (client_table("items.json", "items")[1].get(str(item)) or [None])[0]


ITEM_BUY = 6
ITEM_REQUIRED = 5


def item_buy_price(item):
    row = client_table("items.json", "items")[1].get(str(item)) or ()
    return (row[ITEM_BUY] if len(row) > ITEM_BUY else 0) or None


def item_infos(ids):
    _, items, _ = client_table("items.json", "items")
    out = {}
    for i in ids:
        it = items.get(str(i))
        if it:
            out[str(i)] = {"n": it[0], "q": it[1], "icon": it[2] or "inv_misc_questionmark"}
            if len(it) > 3 and it[3]:
                out[str(i)]["quest"] = 1
    return out


_names = {"mtime": None, "ids": {}}


def item_ids(names):
    mtime, items, _ = client_table("items.json", "items")
    if _names["mtime"] != mtime:
        ids = {}
        for item_id, row in items.items():
            ids[row[0]] = None if row[0] in ids else int(item_id)
        _names.update(mtime=mtime, ids=ids)
    return {n: _names["ids"][n] for n in names if _names["ids"].get(n)}


_quest_names = {"mtime": None, "ids": {}}


def quest_item_id(name):
    mtime, items, _ = client_table("items.json", "items")
    if _quest_names["mtime"] != mtime:
        ids = {}
        for item_id, row in items.items():
            if len(row) > 3 and row[3]:
                ids[row[0]] = None if row[0] in ids else int(item_id)
        _quest_names.update(mtime=mtime, ids=ids)
    if name in _quest_names["ids"]:
        return _quest_names["ids"][name]
    return item_ids([name]).get(name)


STAT_WEIGHTS = os.path.join(ROOT, "data", "stat_weights.json")

STAT_WEIGHTS_MINE = os.path.join(ROOT, "data", "stat_weights_mine.json")


_weights = {"stamps": None, "data": None}


def stat_weights():
    stamps = (store.stamp(STAT_WEIGHTS), store.stamp(STAT_WEIGHTS_MINE))
    if _weights["stamps"] != stamps:
        _weights.update(data=read_stat_weights(), stamps=stamps)
    return _weights["data"]


def read_stat_weights():
    data = store.load_json(STAT_WEIGHTS, None)
    if not data:
        return None
    try:
        with open(STAT_WEIGHTS_MINE, encoding="utf-8") as f:
            mine = json.load(f)
        data["mine"] = "applied"
    except FileNotFoundError:
        mine = {}
    except ValueError as e:
        mine, data["mine"] = {}, f"data/stat_weights_mine.json doesn't read: {e}"
    for cls, specs in mine.items() if isinstance(mine, dict) else ():
        for spec in data["classes"].get(cls, {}).get("specs", []):
            for name in ("*", spec["name"]):
                for stat, weight in (specs.get(name) or {}).items() if isinstance(specs, dict) else ():
                    if isinstance(weight, (int, float)):
                        spec["w"][stat] = weight
    return data


def load_rares():
    try:
        with open(os.path.join(ROOT, "data", "rares.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"by_map": {}, "items": {}}
    by_map = {}
    for r in data["rares"]:
        levels, kind = moblevels.from_text(r.get("level"))
        r.update(levels=moblevels.game(r.get("id"), levels or moblevels.of_data(r.get("id"))), kind=kind)
        by_map.setdefault(r["map"], []).append(r)
    for rares in by_map.values():
        rares.sort(key=lambda r: r["name"])
    return {"by_map": by_map, "items": data["items"]}


def load_tiles():
    path = os.path.join(ROOT, "data", "tiles.json")
    if not os.path.exists(path):
        return {"version": None, "instances": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


TODO_PATH = os.path.join(ROOT, "data", "todo.json")

todo_lock = threading.Lock()


def load_todo():
    return {"silenced": {}, "dismissed": {}, **store.load_json(TODO_PATH, {})}


def save_todo(todo):
    store.save_json(TODO_PATH, todo)


def silenced_todos():
    with todo_lock:
        return set(load_todo().get("silenced") or ())
