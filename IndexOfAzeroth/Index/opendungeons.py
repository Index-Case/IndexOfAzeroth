# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datetime
import hashlib
import html
import json
import os
import re
import sys

from patchtext import Cleaner, Node, repair, text_of
import mainstores
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
KEPT = os.path.join(DATA, "open_dungeons.json")
PATCHES = os.path.join(DATA, "patches.json")
DUNGEONS = os.path.join(DATA, "dungeons.json")
AREAS = os.path.join(DATA, "area_sources.json")
RUNS = os.path.join(DATA, "runs.json")
SAID_MOST = 200

DASH = "[-:\u2013\u2014]"
NEW = re.compile(rf"^\s*new dungeons?\s*{DASH}\s*(?P<rest>.+)$", re.I)
ACCESS = re.compile(r"\b(?:now\s+)?(?:have|has|get|gets|gain|gains)\s+access\s+to\s+(?P<rest>.+)$", re.I)
NOW_OPEN = re.compile(r"^(?P<names>.+?)\s+(?:is|are)\s+now\s+(?:open|available|accessible)\b", re.I)
OPEN_FIRST = re.compile(r"^\s*(?:now\s+)?(?:open|available|accessible)(?:\s+for\s+testing)?\s*:\s*(?:the\s+)?(?:new\s+)?"
                        r"(?P<names>.+?)\s+dungeons?\s*[.!]?\s*$", re.I)
CLOSED = re.compile(r"^(?P<names>.+?)\s+(?:is|are|will)\s+(?:not|no\s+longer)\s+(?:yet\s+)?(?:be\s+)?(?:yet\s+)?"
                    r"(?:open|available|accessible)\b", re.I)
NAMES_END = re.compile(r",?\s+in\s+addition\s+to\b|:\s*$|\s+for\s+players\b", re.I)
ALREADY = re.compile(r"\balready\s+(?:available|open|accessible)\b|\bin\s+addition\s+to\b", re.I)
FOLLOWING = re.compile(r"\bthe\s+following\b.*\b(?:dungeons?)\b.*\b(?:available|open|accessible)\b"
                       r"|\b(?:available|open)\s+dungeons\b", re.I)
SPEAKS = re.compile(r"\bdungeons?\b", re.I)
STATES = re.compile(r"\bnew\s+dungeons?\b|\baccess\s+to\b|\bthe\s+following\b|\bdungeons?\s+(?:will\s+)?(?:now\s+)?"
                    r"(?:opens?|is\s+(?:now\s+)?open|are\s+(?:now\s+)?open)\b", re.I)
NAME_WORDS = 6
JOINING = {"of", "the", "a", "an", "and", "in", "de", "la"}
OPENING = re.compile(r"\b(?:access|available|accessible|open|opens|opened|unlock(?:s|ed)?|new|closed?)\b", re.I)
ENTRY = re.compile(r"^(?P<name>.+?)\s*(?:\(\s*(?:levels?\s+)?(?P<lo>\d+)\s*(?:\+|[-\u2013]\s*(?P<hi>\d+))?\s*\))?\s*[.!]?$", re.I)
SPLIT = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*;\s*", re.I)
FILLER = re.compile(r"^(?:the\s+)?(?:following\s+)?(?:dungeons?\s*:?\s*)?$", re.I)
BARRED = re.compile(r"\b(?:members\s+of\s+)?the\s+(?P<side>horde|alliance)\s+(?:is|are|will\s+be)\s+(?:now\s+)?"
                    r"(?:no\s+longer\s+welcome|attacked\s+on\s+sight)\s+in\s+(?P<place>.+?)(?=\s+under\b|\s+and\b|\s*[,.;!]|$)",
                    re.I)
UNCHANGED = re.compile(r"\bdoes\s+not\s+(?:affect|change)\s+access\s+to\s+(?:the\s+)?(?P<names>.+?)\s+dungeons?\b", re.I)



def norm(name):
    s = (name or "").replace("\u2019", "'").replace("\u2018", "'").casefold().strip()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def place(name):
    return norm(re.sub(r"^(?:the\s+)?(?:lower|upper)\s+", "", (name or "").split(":")[0], flags=re.I))


def names_of(d):
    return [d["name"], *(d.get("names") or ())]


def join(name, dungeons):
    n = norm(name)
    whole = [d["key"] for d in dungeons if any(norm(x) == n for x in names_of(d))]
    if whole or not n:
        return whole
    return [d["key"] for d in dungeons if ":" in d["name"] or re.match(r"(?i)(?:the\s+)?(?:lower|upper)\s", d["name"])
            if place(d["name"]) == n]


def entries(clause):
    out = []
    for part in SPLIT.split(clause.strip().rstrip(".:!")):
        part = part.strip()
        m = ENTRY.match(part)
        if not m or FILLER.match(m.group("name")):
            continue
        lo, hi = m.group("lo"), m.group("hi")
        name = re.sub(r"\s+dungeon$", "", m.group("name").strip(), flags=re.I)
        out.append((name, int(lo) if lo else None, int(hi) if hi else None))
    return out



def blocks(node, out=None):
    out = [] if out is None else out
    for k in node.kids:
        if not isinstance(k, Node):
            continue
        if k.tag in ("p", "li", "h3", "h4", "blockquote"):
            own = re.sub(r"\s+", " ", "".join(x if isinstance(x, str) else text_of(x) for x in k.kids
                                               if isinstance(x, str) or x.tag not in ("ul", "ol"))).strip()
            out.append((own, [t for t in under(k) if t]))
        blocks(k, out)
    return out


def under(node):
    out = []
    for k in node.kids:
        if isinstance(k, Node):
            if k.tag == "li":
                out.append(re.sub(r"\s+", " ", "".join(x if isinstance(x, str) else text_of(x) for x in k.kids
                                                       if isinstance(x, str) or x.tag not in ("ul", "ol"))).strip())
            out += under(k)
    return out


def tree(cooked):
    c = Cleaner()
    c.feed(cooked or "")
    c.close()
    repair(c.root)
    return c.root


def name_like(got):
    return bool(got) and all(0 < len(n.split()) <= NAME_WORDS and all(w[:1].isupper() or w.lower() in JOINING for w in n.split())
                             for n, _, _ in got)


def named_in(text, dungeons):
    t = norm(text)
    return [d["name"] for d in dungeons if any(norm(x) and norm(x) in t for x in names_of(d))
            or (place(d["name"]) and place(d["name"]) in t and len(place(d["name"])) > 5)]


def names_ours(text, dungeons):
    return bool(named_in(text, dungeons))


def read_post(cooked, dungeons=()):
    said = {"list": False, "open": [], "closed": [], "barred": [], "unread": [], "named": []}
    done = set()
    unchanged = []

    def joins(got):
        return any(join(n, dungeons) for n, _, _ in got)
    for own, kids in blocks(tree(cooked)):
        if own in done or not own:
            continue
        about = bool(SPEAKS.search(own)) or names_ours(own, dungeons)
        took = False
        for m in BARRED.finditer(own):
            got = entries(m.group("place"))
            if name_like(got):
                said["barred"] += [[name, m.group("side").title()] for name, _, _ in got]
                unchanged += [e[0] for u in UNCHANGED.finditer(own) for e in entries(u.group("names"))]
                took = True
        m = None if took else NEW.match(own)
        if m:
            got = entries(m.group("rest"))
            said["open"] += [list(e) for e in got]
            took = bool(got)
        m = None if took else ACCESS.search(own)
        if m:
            got = entries(NAMES_END.split(m.group("rest"))[0])
            if about or joins(got) or kids and ALREADY.search(own):
                said["open"] += [list(e) for e in got]
                took = bool(got) or bool(kids and ALREADY.search(own))
        m = None if took else CLOSED.match(own)
        if m:
            got = entries(m.group("names"))
            if name_like(got) and (about or joins(got)):
                said["closed"] += [e[0] for e in got]
                took = True
        m = None if took else OPEN_FIRST.match(own)
        if m:
            got = entries(m.group("names"))
            if name_like(got):
                said["open"] += [list(e) for e in got]
                took = True
        m = None if took else NOW_OPEN.match(own)
        if m and not FOLLOWING.search(own):
            got = entries(m.group("names"))
            if name_like(got) and (about or joins(got)):
                said["open"] += [list(e) for e in got]
                took = True
        if kids and (ALREADY.search(own) or FOLLOWING.search(own)):
            for t in kids:
                said["open"] += [list(e) for e in entries(t)]
                done.add(t)
            said["list"] = True
            took = True
        if not took and about and OPENING.search(own) and (STATES.search(own) or names_ours(own, dungeons)):
            said["unread"].append(own[:SAID_MOST])
        elif not took:
            said["named"] += [n for n in named_in(own, dungeons) if n not in said["named"]]
    if dungeons:
        for name in [e[0] for e in said["open"]] + said["closed"] + unchanged:
            if not join(name, dungeons):
                said["unread"].append(f"{name[:SAID_MOST]} (no dungeon of that name)")
    return said



def statement(post, dungeons=None):
    said = read_post(post.get("cooked") or "", dungeons or ())
    if not (said["open"] or said["closed"] or said["barred"] or said["unread"] or said["list"] or said["named"]):
        return None
    return {"post": post.get("id"), "date": post.get("date") or 0, "title": post.get("title") or "", **said}


def take(posts, path=KEPT, dungeons_path=DUNGEONS):
    kept = store.load_json(path, {"posts": {}})
    dungeons = store.load_json(dungeons_path, {}).get("dungeons") or []
    was = json.dumps(kept, sort_keys=True)
    for p in posts or ():
        if p.get("id") is None or "cooked" not in p:
            continue
        s = statement(p, dungeons)
        if s:
            kept["posts"][str(p["id"])] = s
        else:
            kept["posts"].pop(str(p["id"]), None)
    if json.dumps(kept, sort_keys=True) != was:
        store.save_json(path, kept)
    return [s for s in kept["posts"].values() if s["unread"]]


def resolve(kept, dungeons, since=0):
    ours = list(dungeons)
    state, whole, prev = {}, None, {}
    posts = [s for s in (kept or {}).get("posts", {}).values() if (s.get("date") or 0) >= since]
    for s in sorted(posts, key=lambda s: (s.get("date") or 0, str(s.get("post")))):
        said = {"date": s.get("date"), "title": s.get("title")}
        if s.get("list"):
            whole, prev, state = said, {**prev, **state}, {}
        for name, lo, hi in s.get("open") or ():
            for key in join(name, ours):
                before = state.get(key) or prev.get(key) or {}
                state[key] = {"open": True, "from": lo if lo is not None else before.get("from"),
                              "to": hi if lo is not None else before.get("to"), **said}
        for name in s.get("closed") or ():
            for key in join(name, ours):
                state[key] = {"open": False, "from": None, "to": None, **said}
    if whole:
        for d in ours:
            if d.get("kind", "dungeon") == "dungeon":
                state.setdefault(d["key"], {"open": False, "from": None, "to": None, **whole})
    return state



ORIGINS = ("game", "blizzard", "announced", "blizzard-fix", "press")
GROUPS = {"game": "game", "blizzard": "blizzard", "announced": "blizzard", "blizzard-fix": "blizzard", "press": "press"}
PRESS = re.compile(r"\barticle\b", re.I)
ELLIPSIS = re.compile(r"^\s*\.\.\.|\.\.\.\s*$")


def day_start(day):
    return int(datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time()).timestamp())


def era_start(launch, today):
    return day_start(launch) if launch and today >= launch else 0


def press_said(news, places):
    out, seen = [], set()
    groups = list((news or {}).get("areas", {}).values()) + list((news or {}).get("unmatched") or ())
    for s in (x for a in groups for x in a.get("statements") or ()):
        quote = ELLIPSIS.sub("", s.get("quote") or "").strip()
        if not PRESS.search(s.get("source") or "") or s.get("prompt") or (s.get("url"), quote) in seen:
            continue
        seen.add((s.get("url"), quote))
        said = read_post(f"<p>{html.escape(quote)}</p>", places)
        title = f"{s.get('source')}: {s.get('title') or ''}".strip(": ")
        for name, _, _ in said["open"]:
            out.append((join(name, places), True, s.get("at") or 0, title))
        for name in said["closed"]:
            out.append((join(name, places), False, s.get("at") or 0, title))
    return out


def statements(places, kept, news, runs, today, since):
    out = {d["key"]: [] for d in places}

    def add(key, origin, is_open, at, said, lo=None, hi=None):
        if key in out:
            out[key].append({"origin": origin, "open": is_open, "from": lo, "to": hi, "at": at, "said": said})
    for r in runs or ():
        if (r.get("ended") or 0) >= since:
            add(r.get("key"), "game", True, r["ended"], "a run the game showed you in")
    for key, s in resolve(kept, places, since).items():
        add(key, "blizzard", s["open"], s.get("date") or 0, s.get("title") or "", s.get("from"), s.get("to"))
    for d in places:
        if d.get("opens"):
            come = today >= d["opens"]
            add(d["key"], "announced", come, day_start(d["opens"]) if come else 0, f"announced to open on {d['opens']}")
        elif d.get("later"):
            add(d["key"], "announced", False, 0, "announced for a later release")
    for s in sorted((kept or {}).get("posts", {}).values(), key=lambda s: (s.get("date") or 0, str(s.get("post")))):
        if (s.get("date") or 0) >= since:
            for name in s.get("named") or ():
                for key in join(name, places):
                    add(key, "blizzard-fix", True, s.get("date") or 0, s.get("title") or "")
    for keys, is_open, at, said in press_said(news, places):
        if at >= since:
            for key in keys:
                add(key, "press", is_open, at, said)
    return out


def place_states(places, kept=None, news=None, runs=(), launch=None, today=None, side=None):
    today = today or datetime.date.today().isoformat()
    since = era_start(launch, today)
    shut = {(norm(p), s) for p, s in barred(kept)} if side else set()
    out = {}
    every = statements(places, kept, news, runs, today, since)
    for d in places:
        got = sorted(every[d["key"]], key=lambda s: (ORIGINS.index(s["origin"]), -(s["at"] or 0)))
        if not got:
            state = {"open": True, "from": None, "to": None, "by": None, "said": "", "sure": False, "default": True,
                     "disagree": []}
        else:
            top = got[0]
            agree = {GROUPS[s["origin"]] for s in got if s["open"] == top["open"]}
            firsts = {}
            for s in got:
                firsts.setdefault(s["origin"], s)
            state = {"open": top["open"], "from": top["from"] if top["open"] else None,
                     "to": top["to"] if top["open"] else None, "by": top["origin"], "said": top["said"],
                     "sure": "game" in agree or len(agree) > 1, "default": False,
                     "disagree": [[o, s["open"], s["said"]] for o, s in firsts.items() if s["open"] != top["open"]]}
        if not state["open"] and d.get("opens") and today < d["opens"]:
            state["opens"] = d["opens"]
        if any((norm(n), side) in shut for n in names_of(d)):
            state.update({"open": False, "from": None, "to": None, "by": "blizzard", "said": f"barred to the {side}"})
        state.update({"date": got[0]["at"] if got else None, "title": got[0]["said"] if got else ""})
        out[d["key"]] = state
    return out


def signals_of(states, places):
    names = {d["key"]: d["name"] for d in places}
    out = []
    unsaid = sorted(k for k, s in states.items() if s["default"])
    if unsaid:
        out.append({"what": "unsaid", "places": [names[k] for k in unsaid],
                    "key": hashlib.blake2b(json.dumps(unsaid).encode(), digest_size=4).hexdigest()})
    for k, s in sorted(states.items()):
        if s["disagree"]:
            out.append({"what": "disagree", "places": [names[k]], "open": s["open"], "by": s["by"], "said": s["said"],
                        "against": s["disagree"],
                        "key": hashlib.blake2b(json.dumps([k, s["open"], s["by"], s["disagree"]]).encode(), digest_size=4).hexdigest()})
    return out


def barred(kept=None):
    kept = store.load_json(KEPT, {"posts": {}}) if kept is None else kept
    out = []
    for s in sorted((kept or {}).get("posts", {}).values(), key=lambda s: (s.get("date") or 0, str(s.get("post")))):
        for place, side in s.get("barred") or ():
            if (place, side) not in out:
                out.append((place, side))
    return out


def main():
    patches = store.load_json(mainstores.standing(PATCHES), {}).get("patches") or []
    unread = take(patches)
    journal = store.load_json(DUNGEONS, {})
    dungeons = journal.get("dungeons") or []
    runs = store.load_json(RUNS, {}).get("runs") or []
    state = place_states(dungeons, store.load_json(KEPT, {}), store.load_json(AREAS, {}), runs, journal.get("launch"))
    for d in dungeons:
        s = state[d["key"]]
        print(f"{d['name']}: {'open' if s['open'] else 'not open yet'}"
              + (f", from level {s['from']}" if s.get("from") else "") + (f", opens {s['opens']}" if s.get("opens") else "")
              + (f" (by {s['by']}: {s['said'][:70]})" if s["by"] else " (no statement since the launch: open by default)")
              + (f", against {[o for o, _, _ in s['disagree']]}" if s["disagree"] else ""))
    for place, side in barred():
        print(f"{place}: barred to the {side}")
    for s in unread:
        print(f"Post {s['post']} has lines the rule can't read: {len(s['unread'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
