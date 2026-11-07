# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math
import numbers
import os
import re
import threading
import time

import datafiles
import planreport
from gamedata import quest_item_id
import store
import storedonly
from pending import addon_folder, lua_string, write_in_place
from plansteps import EPIC_CODE, near_way, objective_icon, spot as step_spot, step_ids
from stepplaces import step_places
from serverlog import start_thread
import director_rules
from epic import other_places, step_area, walks_alone

FILE = "Shared.lua"
HEADER = "-- Written by the Index of Azeroth server: what the page and the addon both know. Read at login and /reload.\n"
WAY_MOST = 1200.0
WAY_LEAST = 8.0
CARD = (("name", "questName"), ("npc", "npc"), ("zone", "zone"), ("min", "min"), ("target", "target"), ("count", "count"),
        ("things", "things"),
        ("req", "req"),
        ("face", "face"), ("map", "map"), ("limit", "limit"),
        ("pre", "pre"), ("any", "any"), ("par", "par"), ("dis", "dis"),
        ("what", "what"), ("need", "need"), ("key", "key"), ("cost", "cost"),
        ("cash", "cash"), ("spend", "spend"), ("gain", "gain"),
        ("xp", "xp"), ("sec", "sec"),
        ("kh", "kh"), ("kn", "kn"),
        ("along", "along"),
        ("grp", "group"),
        ("grind", "grind"),
        ("talk", "talk"),
        ("fr", "friendly"),
        ("each", "each"),
        ("rs", "respawn"),
        ("maybe", "maybe"),
        ("rw", "rw"),
        ("mv", "moves"),
        ("bl", "blurb"),
        ("en", "escortNpc"),
        ("ni", "npcId"), ("oi", "objectId"),
        ("trip", "trip"), ("why", "why"),
        ("cq", "cq"),
        ("get", "get"), ("gi", "getItems"), ("ga", "getAny"),
        ("takes", "takes"))
LOOP_MOST = 40
WALK_MOST = 60
MOBS_MOST = 6
HISTORY = 8
PLANNING_KEEP = 10
ROUTE_KEEP = 5
ROUTES_KEPT = 8
PAGE_STEP = ("k", "ids", "text", "inst", "at", "name", "npc", "zone", "min", "target", "count", "mobs", "lv", "bosses",
             "things", "limit", "what", "cost", "careful", "xp", "sec", "along", "grp", "grind", "req",
             "pre", "any",
             "need",
             "key",
             "ic",
             "mv",
             "walk",
             "bl",
             "fr",
             "trip", "why",
             "cq",
             "get",
             "takes",
             "hearth",
             "it",
             "fm",
             "pl",
             "loop", "walk", "way", "alt",
             "ground",
             "al", "sp")
BOSSES_MOST = 16
TALK_CODES = ("P", "T", "S")
WAYS_AHEAD = 400
PART_HEAD = 262144
PLAN_LINE = re.compile(r"^  version = \d+,$", re.M)


def ground_height(ground):
    c, h = ground["c"], ground["h"]
    mid = (c - 1) // 2
    for r in range(0, 4):
        vals = [h[i * c + j] for i in range(mid - r, mid + r + 1) for j in range(mid - r, mid + r + 1)
                if 0 <= i < len(h) // c and 0 <= j < c and h[i * c + j] is not False]
        if vals:
            return float(vals[len(vals) // 2])
    return None


LUA_WORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in", "local", "nil", "not",
             "or", "repeat", "return", "then", "true", "until", "while"}


def lua_key(k):
    return k if re.fullmatch(r"[A-Za-z_]\w*", k, re.ASCII) and k not in LUA_WORDS else f"[{lua_string(k)}]"


def lua_value(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, numbers.Integral):
        return str(int(v))
    if isinstance(v, numbers.Real):
        return repr(round(float(v), 1))
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua_value(x) for x in v) + "}"
    return "{" + ", ".join(f"{lua_key(k)} = {lua_value(x)}" for k, x in v.items()) + "}"


def quiet_table(todo):
    silenced = todo.get("silenced") or {}
    ranks = {tid[len("bars:"):]: 0 for tid in silenced if tid.startswith("bars:")}
    low = {}
    for key, d in (todo.get("dismissed") or {}).items():
        d = d if isinstance(d, dict) else {"sig": d}
        level, _, best = str(d.get("sig")).partition("|")
        if level != "low" or d.get("todo") in silenced:
            continue
        if key.startswith("rank:"):
            if best.isdigit():
                ranks.setdefault(key[len("rank:"):], int(best))
        elif not best:
            low[key] = True
    from errands import TODO_LINES
    chores = {key: True for key, line in sorted(TODO_LINES.items()) if line in silenced}
    return {k: dict(sorted(v.items())) for k, v in (("ranks", ranks), ("low", low), ("chores", chores)) if v}


def quiet_line(quiet):
    return f"  quiet = {lua_value(quiet)}," if quiet else ""


def watch_line(watch):
    return f"  watch = {lua_value(watch)}," if watch else ""


def stars_line(stars):
    return f"  stars = {lua_value(stars)}," if stars else ""


def legacy_line(ids):
    return f"  legacy = {lua_value(list(ids))}," if ids else ""


def roles_line(roles):
    return f"  roles = {lua_value(roles)}," if roles else ""


def services_line(names):
    return f"  services = {lua_value(list(names))}," if names else ""


def towns_line(towns):
    return f"  towns = {lua_value(towns)}," if towns and towns.get("list") else ""


def places_line(places):
    return f"  places = {lua_value(places)}," if places else ""


def rewards_line(rewards):
    if not rewards or not rewards.get("quests"):
        return ""
    quests = ", ".join(f"[{int(q)}] = {lua_value(rw)}" for q, rw in sorted(rewards["quests"].items()))
    return f"  rewards = {{ char = {lua_value(rewards.get('char'))}, quests = {{ {quests} }} }},"


def has_next(nxt):
    return bool(nxt and (nxt.get("zones") or nxt.get("cq")))


def next_line(nxt):
    if not has_next(nxt):
        return ""
    return f"  next = {lua_value(nxt)},"


def render(data, quiet=None, watch=None, stars=None, legacy=None, services=None, rewards=None, nxt=None, towns=None,
           places=None, roles=None):
    if rewards and not rewards.get("quests"):
        rewards = None
    if not has_next(nxt):
        nxt = None
    if not (towns and towns.get("list")):
        towns = None
    if not data and not quiet and not watch and not stars and not legacy and not services and not rewards and not nxt \
            and not towns and not places and not roles:
        return HEADER + "IndexOfAzerothShared = nil\n"
    lines = [HEADER.rstrip("\n"), "IndexOfAzerothShared = {"]
    if data:
        lines.append(f"  version = {int(data['version'])},")
    if quiet:
        lines.append(quiet_line(quiet))
    if watch:
        lines.append(watch_line(watch))
    if stars:
        lines.append(stars_line(stars))
    if legacy:
        lines.append(legacy_line(legacy))
    if roles:
        lines.append(roles_line(roles))
    if services:
        lines.append(services_line(services))
    if rewards:
        lines.append(rewards_line(rewards))
    if nxt:
        lines.append(next_line(nxt))
    if towns:
        lines.append(towns_line(towns))
    if places:
        lines.append(places_line(places))
    epic =(data or {}).get("epic")
    if epic:
        meta = "".join(f"{k} = {lua_value(v)}, " for k, v in epic.items() if k != "steps" and v is not None)
        lines.append(f"  epic = {{ {meta}steps = {{")
        lines += [f"    {lua_value(st)}," for st in epic["steps"]]
        lines.append("  } },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def quest_skill(ids):
    import questplan
    book = questplan.book()
    for qid in ids or ():
        q = book.quests.get(qid) or {}
        skill = q.get("skillTo") or q.get("skill")
        if skill:
            name = book.skills.get(int(skill[0]))
            return [int(skill[0]), int(skill[1]) if len(skill) > 1 else 1] + ([name] if name else [])
    return None


def drawn_way(entry):
    return {"i": entry["inst"], "at": [round(v) for v in entry["at"][:2]],
            "way": [[round(p[0]), round(p[1])] for p in entry.get("way") or ()]}


def walk_key(w):
    return w[0], tuple(w[1]), tuple(w[2])


def tried_route(plan, place):
    rides, legs = [], plan.get("legs") or ()
    for k, leg in enumerate(legs):
        if leg["kind"] == "walk":
            continue
        prev = legs[k - 1] if k else None
        out = {"k": leg["kind"], "i": leg["map"], "at": [round(v) for v in leg["at"][:2]]}
        if leg.get("vehicle"):
            out["v"] = leg["vehicle"]
        if prev and prev["kind"] == "walk" and prev["map"] == leg["map"]:
            out["from"] = [round(v) for v in prev["to"][:2]]
        if leg.get("via"):
            out["via"] = [[round(p[0]), round(p[1])] for p in leg["via"]]
        rides.append(out)
    return {"rides": rides, "walks": [place[walk_key(w)] for w in plan.get("walks") or ()]}


def walk_ends(n, key):
    return {"w": n, "i": key[0], "from": [round(v) for v in key[1][:2]], "to": [round(v) for v in key[2][:2]]}


def walk_drawn(n, w, points):
    return {"w": n, "i": w[0], "way": [[round(p[0]), round(p[1])] for p in points]}


def placed_step(node):
    step = node["step"] if "step" in node else node
    code, spot = EPIC_CODE.get(node.get("kind")), node["spot"] if "spot" in node else step_spot(node)
    if not code or not spot or spot[0] is None:
        return None
    out = {"k": code, "i": spot[0], "at": [round(spot[1]), round(spot[2])]}
    icon = objective_icon(step) if code == "O" else None
    if icon:
        out["ic"] = icon
    if code == "S" and step.get("what"):
        out["what"] = step["what"]
    if node.get("quest") or step.get("quest"):
        out["q"] = node.get("quest") or step["quest"]
    return out


def picked_quest(q, picked, crumbs):
    import questplan
    out = {"id": q["id"]}
    if q.get("name"):
        out["name"] = q["name"]
    giver = next((g for g in q.get("start") or () if g.get("map") is not None), None)
    if giver:
        out["at"] = [giver["map"], round(giver["x"], 1), round(giver["y"], 1)]
    pre = [p for p in questplan.QuestPlan.pre_of(q) if p in picked]
    if pre:
        out["pre"] = pre
    if crumbs and q["id"] in crumbs:
        out["crumb"] = True
    return out


def ride_of(a, b, find_route, want=()):
    if find_route is None or (a[0] == b[0] and math.dist(a[1:3], b[1:3]) < WAY_MOST):
        return None
    return find_route(a, b, *((want,) if want else ())) or None


def epic_steps(steps, find_way, find_route=None, start=None, find_ground=None, ahead=WAYS_AHEAD, find_danger=None,
               find_covered=None, find_height=None, progress=None, failed=None, find_indoor=None):
    unbuilt = set()

    def ask(find, *args):
        try:
            return find(*args)
        except storedonly.NotBuilt:
            unbuilt.add(len(out))
        except Exception:
            if failed:
                failed()
        return None

    def asked_way(inst, a, b, want=()):
        return ask(find_way, inst, a, b, *((want,) if want else ()))

    def asked_route(a, b, want=()):
        return ask(ride_of, a, b, find_route, want)
    out, kept, prev = [], [], ({"inst": start[0], "at": list(start[1:3])} if start else None)
    base = prev
    for n, st in enumerate(steps):
        if progress:
            progress(n, len(steps), len(unbuilt), out)
        code, ids = EPIC_CODE.get(st.get("kind")), step_ids(st)
        if not code or (not ids and code != "S") or not st.get("at"):
            continue
        entry = {"k": code, "ids": ids, "inst": st["inst"], "at": [round(float(v), 1) for v in st["at"][:3]],
                 "text": st.get("text", "")}
        for key, src in CARD:
            if st.get(src) not in (None, ""):
                entry[key] = st[src]
        if code != "S" and isinstance(st.get("lv"), (int, float)) and not isinstance(st.get("lv"), bool):
            entry["wl"] = int(st["lv"])
        if st.get("hearth"):
            h = st["hearth"]
            entry["hearth"] = {"t": h["to"], "b": list(h["bind"]), "i": h["spot"][0], "s": int(h["saves"]),
                               "at": [round(float(h["spot"][1]), 1), round(float(h["spot"][2]), 1)], **({"p": True} if h.get("p") else {}),
                               **({"cd": int(h["cd"])} if h.get("cd") else {})}
        if entry.get("talk") and st.get("target"):
            entry["npc"] = st["npc"] if st.get("npc") else st["target"]
        if len(entry["at"]) < 3 and entry.get("npc") and (code in TALK_CODES or entry.get("talk")):
            entry["guess"] = True
            learnt = ask(find_height, entry["inst"], entry["at"][0], entry["at"][1], entry["npc"]) if find_height else None
            if learnt is not None:
                entry["at"].append(round(float(learnt), 1))
        if code == "D" and st.get("bosses"):
            entry["bosses"] = st["bosses"][:BOSSES_MOST]
        if code == "D" and st.get("qmobs"):
            entry["qmobs"] = st["qmobs"]
        skill = quest_skill(ids)
        if skill:
            entry["sk"] = skill
        farm = code == "S" and st.get("what") == "farm"
        if farm:
            entry["fm"], entry["it"] = st.get("farm") or "kill", st.get("item")
        if code == "O" or farm:
            if code == "O" and objective_icon(st):
                entry["ic"] = objective_icon(st)
            item = quest_item_id(st["target"]) if entry.get("ic") in ("grab", "loot") and st.get("target") else None
            if item:
                entry["it"] = item
            if st.get("who"):
                entry["mobs"] = [str(m) for m in st["who"][:MOBS_MOST]]
                entry["mi"] = list(dict.fromkeys(int(m) for m in st.get("mobs") or ()))
                if st.get("levels"):
                    entry["lv"] = [list(v) if v else [] for v in st["levels"][:MOBS_MOST]]
            if st.get("loop"):
                entry["loop"] = [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in st["loop"][:LOOP_MOST]]
            elif st.get("patrols") and walks_alone(st):
                entry["walk"] = [[round(float(n), 1), round(float(w), 1)] for n, w in max(st["patrols"], key=len)[:WALK_MOST]]
            if st.get("spawns"):
                entry["ar"] = step_area(st["spawns"])
            more = other_places(st, entry.get("ar"))
            if more:
                entry["hr"] = more
        if st.get("walker") and st.get("patrols") and (code in TALK_CODES or entry.get("talk")):
            walk = st["patrols"][0]
            keep = walk if len(walk) <= WALK_MOST else [walk[round(k * (len(walk) - 1) / (WALK_MOST - 1))] for k in range(WALK_MOST)]
            entry["walk"] = [[round(float(n), 1), round(float(w), 1)] for n, w in keep]
        if len(out) >= ahead:
            out.append(entry)
            kept.append(st)
            prev = entry
            base = entry if code != "S" else base
            continue
        own_z = len(entry["at"]) >= 3
        if find_ground:
            ground = ask(find_ground, entry["inst"], entry["at"][0], entry["at"][1])
            if ground:
                entry["ground"] = ground
                if not own_z and ground_height(ground) is not None:
                    entry["at"].append(ground_height(ground))
        near = prev and prev["inst"] == entry["inst"] and math.dist(prev["at"][:2], entry["at"][:2]) < WAY_MOST
        want = tuple(st.get("mobs") or ()) if code == "O" else ()
        escort = st.get("escort") if code == "O" and prev and prev["inst"] == entry["inst"] else None
        if escort:
            entry["way"] = escort_way(prev, escort, entry["inst"], asked_way)
            near = False
        elif prev and not near and find_route:
            route = asked_route((prev["inst"], *prev["at"]), (entry["inst"], *entry["at"]), want)
            if route:
                entry["route"] = route
            near = not route and prev["inst"] == entry["inst"]
        if near and (len(out) or start) and WAY_LEAST <= math.dist(prev["at"][:2], entry["at"][:2]):
            way = asked_way(entry["inst"], tuple(prev["at"]), tuple(entry["at"] if own_z else entry["at"][:2]), want)
            end = way and not way.get("partial") and way["points"][-1]
            if not own_z and end and len(end) > 2 and end[2] is not None:
                entry["at"][2:] = [round(float(end[2]), 1)]
            if way and not way.get("partial") and len(way["points"]) > 1:
                entry["way"] = [[round(float(v), 1) for v in p[:3]] for p in way["points"][:-1]]
                if not out and start:
                    entry["way"].insert(0, [round(float(v), 1) for v in prev["at"][:2]])
                if way.get("climbs") or way.get("drops"):
                    easy = ask(find_way, entry["inst"], tuple(prev["at"]), tuple(entry["at"] if own_z else entry["at"][:2]),
                               want, True)
                    if easy and not easy.get("partial") and len(easy["points"]) > 1:
                        ez = [[round(float(v), 1) for v in p[:3]] for p in easy["points"][:-1]]
                        if not out and start:
                            ez.insert(0, [round(float(v), 1) for v in prev["at"][:2]])
                        if ez != entry["way"]:
                            entry["ez"] = ez
        if prev is not base and base and prev.get("k") == "S" and "way" in entry and base["inst"] == entry["inst"] \
                and WAY_LEAST <= math.dist(base["at"][:2], entry["at"][:2]):
            alt = asked_way(entry["inst"], tuple(base["at"]), tuple(entry["at"] if own_z else entry["at"][:2]), want)
            if alt and not alt.get("partial") and len(alt["points"]) > 1:
                entry["alt"] = [[round(float(v), 1) for v in base["at"][:2]]] + \
                    [[round(float(v), 1) for v in p[:3]] for p in alt["points"][:-1]]
        if code == "S" and st.get("also"):
            entry["also"] = also_entries(st["also"], asked_way)
        h = entry.get("hearth")
        if h and h["i"] == entry["inst"] and WAY_LEAST <= math.dist(h["at"], entry["at"][:2]):
            way = asked_way(entry["inst"], tuple(h["at"]), tuple(entry["at"] if own_z else entry["at"][:2]), want)
            if way and not way.get("partial") and len(way["points"]) > 1:
                h["w"] = [[round(float(v), 1) for v in p[:3]] for p in way["points"][:-1]]
        if find_danger:
            pts = [p[:2] for p in entry.get("way") or []] + [entry["at"][:2]] + [p[:2] for p in entry.get("loop") or []] \
                + [p[:2] for piece in entry.get("route") or [] if piece.get("i") == entry["inst"] for p in piece.get("w") or []]
            careful = ask(find_danger, entry["inst"], pts)
            if careful:
                entry["careful"] = careful
        if find_covered and len(entry["at"]) > 2 and ask(find_covered, entry["inst"], [entry["at"]]):
            entry["under"] = True
        for key, into in (("way", "cov"), ("alt", "acov"), ("ez", "ecov")):
            if find_indoor and entry.get(key):
                got = ask(find_indoor, entry["inst"], entry[key] + [entry["at"]])
                if got:
                    entry[into] = [k + 1 for k in got]
        out.append(entry)
        kept.append(st)
        prev = entry
        base = entry if code != "S" else base
    if progress:
        progress(len(steps), len(steps), len(unbuilt), out)
    return out


def dress_steps(steps, find_spawns=None, start=None):
    for e in steps:
        if e.get("k") == "O" and "sp" not in e and find_spawns:
            sp = find_spawns(e)
            if sp:
                e["sp"] = sp
    along_legs(steps, start)


def leg(prev, e):
    legs = [piece.get("w") for piece in e.get("route") or () if piece.get("i") == e["inst"] and piece.get("w")]
    if legs:
        return [[p[:2] for p in walk] for walk in legs]
    if prev and prev["inst"] == e["inst"]:
        return [[prev["at"][:2]] + [b[:2] for b in e.get("way") or ()] + [e["at"][:2]]]
    return []


def along_legs(out, start=None):
    reach = director_rules.ALONG["reach"].value
    prev = {"inst": start[0], "at": list(start[1:3])} if start else None
    targets = [(j, e) for j, e in enumerate(out) if e["k"] == "O" and e.get("sp")]
    for k, e in enumerate(out):
        walks = leg(prev, e)
        prev = e
        if not walks:
            e.pop("al", None)
            continue
        got = [j + 1 for j, t in targets if j != k and t["inst"] == e["inst"] and near_way(t["sp"], walks, reach)]
        if got:
            e["al"] = got
        else:
            e.pop("al", None)


def also_entries(also, find_way):
    out = []
    for e in also:
        land, at = [round(float(v), 1) for v in e["l"][1:3]], [round(float(v), 1) for v in e["at"][:3]]
        got = {"l": [e["l"][0], *land], "npc": e["npc"], "inst": e["inst"], "at": at,
               **{k: e[k] for k in ("map", "zone", "cost", "text") if e.get(k)}}
        if e["l"][0] == e["inst"] and WAY_LEAST <= math.dist(land, at[:2]):
            way = find_way(e["inst"], tuple(land), tuple(at))
            if way and not way.get("partial") and len(way["points"]) > 1:
                got["way"] = [land] + [[round(float(v), 1) for v in p[:3]] for p in way["points"][:-1]]
        out.append(got)
    return out


ESCORT_LEAD = 30.0


def escort_way(prev, escort, inst, find_way):
    lead = []
    if math.dist(prev["at"][:2], escort[0][:2]) >= ESCORT_LEAD:
        way = find_way(inst, tuple(prev["at"]), tuple(escort[0]))
        if way and not way.get("partial"):
            lead = [[round(float(v), 1) for v in p[:3]] for p in way["points"]]
    return lead + [[round(float(v), 1) for v in p[:3]] for p in escort[:-1]]


class CalledOff(Exception):
    pass


def plan_notes(epic):
    shown = [n for n in epic.get("errandNotes") or () if n.get("text") and not n.get("hidden")]
    notes, brief = [n["text"] for n in shown], [n.get("brief") or "" for n in shown]
    hidden = [n["text"] for n in epic.get("errandNotes") or () if n.get("text") and n.get("hidden")]
    missing = [{"id": q["id"], "name": q["name"], **({"onWay": True} if q.get("onWay") else {})}
               for q in epic.get("later") or () if q.get("missing")]
    later = [{"text": e["text"], "wall": e["wall"]["kind"], **({"offer": e["wall"]["offer"]} if e["wall"].get("offer") else {}),
              **({"prof": e["wall"]["prof"]} if e["wall"].get("prof") else {})}
             for e in epic.get("campLater") or ()]
    short = [{"id": q["id"], "name": q["name"], "line": q["skill"][0], "need": q["skill"][1], "skill": q.get("skillName")}
             for q in epic.get("later") or () if q.get("skill") and q.get("inLog")]
    return {"notes": notes or None, "brief": brief if any(brief) else None, "hidden": hidden or None,
            "missing": missing or None, "later": later or None, "skillShort": short or None}


QUEST_TEXT = datafiles.data_path("questtext.json")
TEXT_CODES = ("P", "O", "T")


def quest_texts(steps, data=None):
    if data is None:
        data = datafiles.load(QUEST_TEXT, {}).get("quests") or {}
    out, seen = [], set()
    for st in steps:
        if st.get("k") not in TEXT_CODES:
            continue
        for qid in st.get("ids") or ():
            rec = data.get(str(qid)) or {}
            if qid in seen or not (rec.get("text") or rec.get("todo")):
                continue
            seen.add(qid)
            out.append([int(qid), rec.get("text") or "", rec.get("todo") or ""])
    return out or None


def page_form(data):
    epic = data.get("epic")
    return {"version": data.get("version"),
            "epic": epic and {**{k: v for k, v in epic.items() if k not in ("steps", "qt")},
                              "steps": [{k: s[k] for k in PAGE_STEP if k in s} for s in epic["steps"]]}}


class Shared:
    def __init__(self, addons_dir, state_path=None):
        self.addons_dir = addons_dir
        self.state_path = state_path
        self.lock = threading.Lock()
        self.data = None
        self.working = None
        self.working_start = False
        self.asks = 0
        self.progress = None
        self.planning = None
        self.routing = {}
        self.failed = None
        self.broke = None
        self.plans = {}
        self.history = {}
        self.loaded = None
        self.run_start = None
        self.stops = {}
        self.top = 0
        self.switched = None
        self.aside = None
        self.find_ground = None
        self.find_danger = None
        self.find_covered = None
        self.find_indoor = None
        self.find_height = None
        self.find_place = None
        self.quiet = {}
        self.watch = {}
        self.stars = {}
        self.legacy = []
        self.services = []
        self.rewards = None
        self.next = None
        self.towns = None
        self.places = None
        self.roles = None
        self.find_rewards = None
        self.find_ends = None
        self.find_spawns = None
        self.load()

    def path(self):
        folder = addon_folder(self.addons_dir)
        return folder and os.path.join(folder, FILE)

    def load(self):
        if not self.state_path:
            return
        saved = store.load_json(self.state_path, {})
        self.plans = saved.get("plans") or {}
        self.history = {int(v): p for v, p in (saved.get("history") or {}).items()}
        self.run_start = saved.get("run_start")
        self.top = int(saved.get("top") or 0)
        self.aside = saved.get("aside") or None
        data, path = saved.get("data"), self.path()
        if not data or not path or not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            m = re.search(r"version = (\d+)", f.read(4096))
        if m and int(m.group(1)) == int(data.get("version") or 0):
            self.data = data
            self.history.setdefault(int(data["version"]), page_form(data))

    def write(self, data):
        with self.lock:
            return self.write_locked(data)

    def write_locked(self, data, **record):
        path = self.path()
        if not path:
            return False
        write_in_place(path, self.table_text(data))
        for name, value in record.items():
            setattr(self, name, value)
        self.data = data
        self.top = max(self.top, int(data["version"]))
        self.history[int(data["version"])] = page_form(data)
        for v in sorted(self.history)[:-HISTORY]:
            if v != self.loaded:
                del self.history[v]
        if self.state_path:
            store.save_json(self.state_path, {"data": data, "plans": self.plans, "run_start": self.run_start,
                                              "top": self.top, "history": {str(v): p for v, p in self.history.items()},
                                              "aside": self.aside})
        return True

    def set_quiet(self, quiet):
        return self.set_part("quiet", quiet or {}, quiet_line)

    def set_watch(self, watch):
        return self.set_part("watch", watch or {}, watch_line)

    def set_stars(self, stars):
        return self.set_part("stars", stars or {}, stars_line)

    def set_legacy(self, ids):
        return self.set_part("legacy", list(ids or ()), legacy_line)

    def set_services(self, names):
        return self.set_part("services", list(names or ()), services_line)

    def set_towns(self, towns):
        return self.set_part("towns", towns if towns and towns.get("list") else None, towns_line)

    def set_places(self, places):
        return self.set_part("places", places or None, places_line)

    def set_roles(self, roles):
        return self.set_part("roles", roles or None, roles_line)

    def set_rewards(self, rewards):
        return self.set_part("rewards", rewards if rewards and rewards.get("quests") else None, rewards_line)

    def set_next(self, nxt):
        return self.set_part("next", nxt if has_next(nxt) else None, next_line)

    def set_part(self, name, value, line_of):
        with self.lock:
            setattr(self, name, value)
            path = self.path()
            if not path:
                return False
            head = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    head = f.read(PART_HEAD)
            line = line_of(value)
            holds = line + "\n" in head if line else f"\n  {name} = " not in head
            if holds or (self.data is None and PLAN_LINE.search(head)):
                return False
            write_in_place(path, self.table_text(self.data))
            return True

    def table_text(self, data):
        epic = (data or {}).get("epic") or {}
        if epic.get("steps"):
            anchor = epic.get("anchor")
            dress_steps(epic["steps"], self.find_spawns, tuple(anchor[:3]) if anchor and len(anchor) >= 3 else None)
        return render(data, self.quiet, self.watch, self.stars, self.legacy, self.services, self.rewards, self.next,
                      self.towns, self.places, self.roles)

    def plan_report(self, key, stage=None, finds=(), picked=None, placed=(), ordered=None, crumbs=None, at=None,
                    rounds=None, tried=None, walked=None, won=None):
        if (stage is None and not finds and picked is None and not placed and ordered is None and at is None
                and rounds is None):
            return
        with self.lock:
            p = self.planning
            if not p or p["key"] != key or (p.get("till") and time.time() > p["till"]):
                p = {"key": key, "stage": None, "finds": []}
            now = {"key": key, "stage": stage or p["stage"], "finds": planreport.first(p["finds"] + list(finds)) if finds else p["finds"]}
            begun = bool(stage) and stage != p["stage"]
            for name, said in (("at", at), ("rounds", rounds)):
                if said is not None or (name in p and not begun):
                    now[name] = p[name] if said is None else said
            if picked is not None or "picked" in p:
                now["picked"], now["crumbs"] = (p["picked"], p.get("crumbs")) if picked is None else (picked, crumbs)
            if placed or "placed" in p:
                now["placed"] = p.get("placed", [])
                now["placed"].extend(placed)
            if ordered is not None or "ordered" in p:
                now["ordered"] = p["ordered"] if ordered is None else ordered
                now["orders"] = p.get("orders", 0) + (ordered is not None)
            self.planning = now

    def plan_done(self, key, now=None):
        with self.lock:
            if self.planning and self.planning["key"] == key:
                self.planning = {**self.planning, "till": (now or time.time()) + PLANNING_KEEP}

    def progress_now(self, now=None, ways_from=None, steps_from=None, quests=False, order=False):
        g, p = self.progress, self.planning
        if g and "ways" in g:
            ways = g["ways"]
            g = {k: v for k, v in g.items() if k != "ways"}
            g["found"] = len(ways)
            if ways_from is not None:
                g["ways"] = ways[ways_from:]
        if p and p.get("till") and (now or time.time()) > p["till"]:
            p = None
        if not p or (g and g["key"] != p["key"]):
            return g
        out = {**(g or {"key": p["key"]}), "stage": p["stage"], "finds": p["finds"]}
        if p.get("at"):
            node, k, n = p["at"]
            step = placed_step(node)
            out["at"] = {"k": k, "n": n, **({"step": step} if step else {})}
        if p.get("rounds"):
            out["rounds"] = {"n": p["rounds"][0], "of": p["rounds"][1]}
        picked, placed, ordered = p.get("picked"), p.get("placed"), p.get("ordered")
        if picked is not None:
            out["picked"] = len(picked)
            if quests:
                out["quests"] = [picked_quest(q, picked, p.get("crumbs")) for q in list(picked.values())]
        if placed:
            out["placed"] = n = len(placed)
            if steps_from is not None:
                out["steps"] = [s for s in map(placed_step, placed[steps_from:n]) if s]
        if ordered is not None:
            out["ordered"] = p["orders"]
            if order:
                out["order"] = [s for s in map(placed_step, list(ordered)) if s]
        return out

    def route_report(self, ask, stage=None, finds=(), picked=None, placed=(), ordered=None, crumbs=None, at=None,
                     rounds=None, tried=None, walked=None, won=None):
        if tried is None and walked is None and won is None:
            return
        with self.lock:
            r = self.routing.get(ask)
            if r is None:
                now = time.time()
                for old in [k for k, v in self.routing.items() if v["till"] and now > v["till"]]:
                    del self.routing[old]
                while len(self.routing) >= ROUTES_KEPT:
                    del self.routing[next(iter(self.routing))]
                r = self.routing[ask] = {"tried": [], "tries": 0, "walked": [], "won": None, "till": None}
            if tried is not None:
                r["tried"], r["tries"] = tried, r["tries"] + 1
            if walked is not None:
                r["walked"].append(walked)
            if won is not None:
                r["won"] = won

    def route_done(self, ask, now=None):
        with self.lock:
            if ask in self.routing:
                self.routing[ask]["till"] = (now or time.time()) + ROUTE_KEEP

    def route_progress(self, ask, walks_from=0, tried=False, now=None):
        with self.lock:
            r = self.routing.get(ask)
            if r is None or (r["till"] and (now or time.time()) > r["till"]):
                return None
            plans, walked, won, done = r["tried"], r["walked"], r["won"], bool(r["till"])
            out = {"tries": r["tries"], "walked": len(walked), "done": done}
        keys = list(dict.fromkeys(walk_key(w) for p in plans for w in p.get("walks") or ()))
        place = {k: n for n, k in enumerate(keys)}
        out["won"] = next((n for n, p in enumerate(plans) if p is won), None)
        if tried:
            out["tried"] = [tried_route(p, place) for p in plans]
            out["ends"] = [walk_ends(n, k) for n, k in enumerate(keys)]
        out["walks"] = [walk_drawn(place[walk_key(w)], w, pts) for w, pts in walked[max(0, walks_from):out["walked"]]
                        if walk_key(w) in place]
        return out

    def next_version(self):
        return max(int(time.time()), int((self.data or {}).get("version") or 0) + 1, self.top + 1)

    def write_epic(self, key, steps, find_way, meta=None, find_route=None, since=None, still=None, ask=None):
        since = self.stops.get(key, 0) if since is None else since
        with self.lock:
            if ask is None:
                self.asks += 1
                ask = self.asks
            if self.asks == ask:
                self.working, self.working_start = key, bool((meta or {}).get("start"))
                self.progress = {"key": key, "done": 0, "of": len(steps), "unbuilt": 0, "since": round(time.time())}
                p = self.planning if self.planning and self.planning["key"] == key else {"finds": []}
                self.planning = {"key": key, "stage": "ways", "finds": p["finds"],
                                 **{k: p[k] for k in ("ordered", "orders") if k in p}}
        counted = {"unbuilt": 0}

        drawn = []

        def going(done, of, unbuilt, made):
            with self.lock:
                if self.stops.get(key, 0) != since or self.asks != ask:
                    raise CalledOff(key)
                counted["unbuilt"] = unbuilt
                drawn.extend(drawn_way(e) for e in made[len(drawn):])
                now = planreport.way_now(steps[done], done) if done < len(steps) else None
                self.progress = {**(self.progress or {}), "key": key, "done": done, "of": of, "unbuilt": unbuilt, "now": now,
                                 "ways": list(drawn)}
        try:
            start = (meta or {}).get("from") or (meta or {}).get("anchor")
            if self.find_rewards:
                steps = [{**st, "rw": rw} if rw else st for st, rw in zip(steps, self.find_rewards(steps))]
            ends = None
            try:
                ends = self.find_ends(steps) if self.find_ends else None
            except Exception:
                if self.failed:
                    self.failed()
            steps = epic_steps(steps, find_way, find_route, tuple(start) if start else None, self.find_ground,
                               find_danger=self.find_danger, find_covered=self.find_covered, find_height=self.find_height,
                               progress=going, failed=self.failed, find_indoor=self.find_indoor)
            places = None
            try:
                places = step_places(steps, self.find_place)
            except Exception:
                if self.failed:
                    self.failed()
            with self.lock:
                if self.stops.get(key, 0) != since or self.asks != ask or (still and not still()):
                    return False
                was = (self.data or {}).get("epic") or {}
                if was.get("key") == key and was.get("closed") and not (meta or {}).get("start"):
                    return False
                fewer = (meta or {}).get("fewer")
                if fewer is not None and counted["unbuilt"] >= fewer:
                    return False
                meta = meta or {}
                start = bool(meta.get("start"))
                plan = 1 if start else int(self.plans.get(key) or 0) + 1
                version = self.next_version()
                epic = {"key": key, "name": meta.get("name"), "plan": plan, "char": meta.get("char"), "anchor": meta.get("anchor"),
                        "mode": meta.get("mode"), "rating": meta.get("rating"), "reasons": meta.get("reasons"), "written": version,
                        "fresh": meta.get("fresh"), "close": meta.get("close"),
                        "craft": meta.get("craft") or None,
                        "maybe": meta.get("maybe") or None,
                        "next": meta.get("next") or None,
                        "notes": meta.get("notes") or None, "brief": meta.get("brief") or None,
                        "hidden": meta.get("hidden") or None,
                        "against": meta.get("against"),
                        "missing": meta.get("missing") or None,
                        "skillShort": meta.get("skillShort") or None,
                        "later": meta.get("later") or None,
                        "parked": meta.get("parked") or None,
                        "asked": meta.get("asked") or None,
                        "unbuilt": counted["unbuilt"] or None,
                        "ends": ends or None,
                        "places": places,
                        "qt": quest_texts(steps),
                        "steps": steps}
                before = self.data
                aside = meta.get("aside")
                if not start or aside == "keep":
                    aside = self.aside
                elif isinstance(aside, dict) and was.get("key") and was.get("key") != key:
                    aside = {"data": before, "parked": aside.get("parked") or []}
                else:
                    aside = None
                return self.write_locked(
                    {"version": version, "epic": epic}, plans={**self.plans, key: plan},
                    run_start=version if start else self.run_start, aside=aside,
                    switched={"from": before, "to": version} if meta.get("switched") and (before or {}).get("epic") else None)
        except CalledOff:
            return False
        except Exception:
            with self.lock:
                if self.asks == ask:
                    self.top = self.next_version()
                    self.broke = {"key": key, "at": self.top}
            raise
        finally:
            with self.lock:
                if self.asks == ask:
                    self.working, self.working_start, self.progress = None, False, None
                    if self.planning and self.planning["key"] == key:
                        self.planning = None

    def start_epic(self, key, steps, find_way, meta=None, find_route=None, still=None):
        start = bool((meta or {}).get("start"))
        with self.lock:
            if self.working and not start:
                return False
            self.asks += 1
            ask = self.asks
            self.working, self.working_start = key, start
            since = self.stops.get(key, 0)
        start_thread("plan writer", self.write_epic, (key, steps, find_way, meta, find_route, since, still, ask))
        return True

    def switch_back(self, key, mode, loaded):
        with self.lock:
            sw = self.switched
            before = (sw or {}).get("from") or {}
            epic = before.get("epic") or {}
            if (not sw or (self.data or {}).get("version") != sw["to"] or loaded == sw["to"] or epic.get("key") != key
                    or (epic.get("mode") or "any") != mode):
                return False
            return self.write_locked(before, switched=None, history={v: p for v, p in self.history.items() if v != sw["to"]},
                                     plans={**self.plans, key: epic.get("plan") or self.plans.get(key)})

    def close_epic(self, key=None, by="page"):
        with self.lock:
            d = self.data or {}
            epic = d.get("epic")
            key = key or (epic or {}).get("key")
            mine = epic if epic and epic.get("key") == key else None
            if not key or (not mine and self.working != key):
                return False
            game = by == "game"
            closed = (mine or {}).get("closed")
            if closed:
                if not game or closed.get("game"):
                    return False
                return self.write_locked({**d, "epic": {**mine, "closed": {**closed, "game": True}}})
            if game and ((mine or {}).get("opened") or {}).get("game"):
                return False
            self.stops[key] = self.stops.get(key, 0) + 1
            if not mine:
                return True
            kept = {k: v for k, v in mine.items() if k != "opened"}
            return self.write_locked({**d, "epic": {**kept, "closed": {"by": by, "at": int(time.time()), "game": game}}},
                                     switched=None)

    def open_epic(self, key, by="page"):
        with self.lock:
            d = self.data or {}
            epic = d.get("epic") or {}
            if not key or epic.get("key") != key or not epic.get("closed"):
                return False
            game = by == "page" and bool(epic["closed"].get("game"))
            kept = {k: v for k, v in epic.items() if k != "closed"}
            return self.write_locked({**d, "epic": {**kept, "opened": {"at": int(time.time()), "game": game}}})

    def set_pick(self, key, item, way):
        with self.lock:
            d = self.data or {}
            epic = d.get("epic") or {}
            craft = epic.get("craft") or {}
            picks = dict(craft.get("picks") or {})
            if epic.get("key") != key or not craft or picks.get(str(item)) == way:
                return False
            picks[str(item)] = way
            return self.write_locked({**d, "epic": {**epic, "craft": {**craft, "picks": picks}}})

    def back(self):
        with self.lock:
            aside = self.aside
            if not aside:
                return False
            now = ((self.data or {}).get("epic") or {}).get("key")
            if now:
                self.stops[now] = self.stops.get(now, 0) + 1
            version = self.next_version()
            epic = {k: v for k, v in aside["data"]["epic"].items() if k not in ("closed", "opened")}
            epic.update(written=version, fresh=True, parked=aside.get("parked") or None)
            return self.write_locked({**aside["data"], "version": version, "epic": epic}, run_start=version, aside=None,
                                     switched=None, plans={**self.plans, epic["key"]: epic.get("plan") or 1})

    def game_guide(self, key, running):
        if not running:
            return self.close_epic(key, by="game")
        epic = (self.data or {}).get("epic") or {}
        if epic.get("key") != key:
            return False
        if (epic.get("closed") or {}).get("game"):
            return self.open_epic(key, by="game")
        with self.lock:
            d = self.data or {}
            epic = d.get("epic") or {}
            opened = epic.get("opened") or {}
            if epic.get("key") != key or not opened.get("game"):
                return False
            return self.write_locked({**d, "epic": {**epic, "opened": {**opened, "game": False}}})

    def brief(self):
        d = self.data or {}
        epic = d.get("epic") or {}
        return {"version": d.get("version"), "working": self.working, "key": epic.get("key"), "name": epic.get("name"),
                "plan": epic.get("plan"), "char": epic.get("char"), "anchor": epic.get("anchor"), "mode": epic.get("mode"),
                "close": epic.get("close"),
                "rating": epic.get("rating"), "reasons": epic.get("reasons"), "against": epic.get("against"),
                "written": epic.get("written"), "fresh": epic.get("fresh"), "start": self.run_start, "unbuilt": epic.get("unbuilt"), "progress": self.progress_now(),
                "closed": epic.get("closed"), "opened": epic.get("opened"), "broke": self.broke,
                "asked": epic.get("asked"),
                "aside": self.aside_brief()}

    def aside_brief(self):
        epic = ((self.aside or {}).get("data") or {}).get("epic") or {}
        return {k: epic.get(k) for k in ("key", "name", "char", "anchor", "mode", "close")} if epic.get("key") else None

    def snapshot(self, version=None):
        last = version and int(version) == (self.data or {}).get("version")
        form = self.history.get(int(version)) if version and not last else None
        return {**(form or page_form(self.data or {})), "working": self.working, "progress": self.progress_now(),
                "towns": self.towns}

    def ensure(self):
        with self.lock:
            path = self.path()
            if path and not os.path.exists(path):
                write_in_place(path, render(None))
