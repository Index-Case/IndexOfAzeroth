# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
import threading
import time

import store
from game import GameNotFound

LOADED_ONLY = ("plans",)

FILE = "Pending.lua"
HEADER = "-- Written by the Index of Azeroth server: the guides started on the page, picked up at login or /reload.\n"
SLOTS = {"go": "go", "r": "go", "g": "loop", "h": "loop", "k": "loop", "target": "target"}
COMMAND = r"^/(?:dgg|wcc)\s+"
LOOP_WORDS = {"h": "gather", "g": "grind", "k": "skin", "target": "target"}
LOOK_TOKENS = {"g": {"x": "xp", "g": "farm"}, "h": {"m": "mining", "h": "herbalism", "f": "fishing", "t": "treasure"}}


def line_look(line):
    m = re.match(COMMAND + r"([GgHhKk])\s+\d+\s+(?:&([A-Za-z])\s)?", line or "")
    if not m:
        return None
    verb, said = m.group(1).lower(), (m.group(2) or "").lower()
    return LOOK_TOKENS.get(verb, {}).get(said) or LOOP_WORDS[verb]


def slot_of(line):
    m = re.match(COMMAND + r"(\w+)\s", line or "")
    return m and SLOTS.get(m.group(1).lower())


WOW_SPACE = " \t\r\n"


def line_check(line):
    text = (line or "").strip(WOW_SPACE)
    m = re.match(COMMAND + r"[Rr]\s+(.+=.*)$", text)
    kind, rest = ("r", m.group(1)) if m else (None, None)
    m = None if kind else re.match(COMMAND + r"([EeGgHhKk])\s+(\d+\s+.+)$", text)
    if m:
        kind, rest = m.group(1).lower(), m.group(2)
    m = None if kind else re.match(COMMAND + r"[Gg][Oo]\s+(.+)$", text)
    if m:
        kind, rest = "go", m.group(1)
    m = None if kind else re.match(COMMAND + r"[Tt][Aa][Rr][Gg][Ee][Tt]\s+(.+)$", text)
    if m:
        kind, rest = "target", m.group(1)
    if not kind:
        return None
    check = 0
    for byte in f"{kind} {rest.strip(WOW_SPACE)}".encode("utf-8"):
        check = (check * 31 + byte) % 65536
    return check


def lua_string(s):
    out = []
    for ch in s:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(f"\\{ord(ch):03d}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


CHAR_FIELDS = ("name", "surname", "realm", "guid")


def render_one(guide):
    named = ("id", "line") + tuple(k for k in CHAR_FIELDS if k in guide)
    fields = [f"{k} = {lua_string(str(guide.get(k) or ''))}" for k in named]
    fields.append(f"at = {int(guide.get('at') or 0)}")
    return "{ " + ", ".join(fields) + " }"


def render(guides):
    guides = {k: v for k, v in (guides or {}).items() if v}
    if not guides:
        return HEADER + "IndexOfAzerothPending = nil\n"
    return HEADER + "IndexOfAzerothPending = { " + ", ".join(f"{k} = {render_one(v)}" for k, v in sorted(guides.items())) + " }\n"


def write_in_place(path, text):
    data = text.encode("utf-8")
    with open(path, "r+b" if os.path.exists(path) else "wb") as f:
        f.seek(0)
        f.write(data)
        f.truncate()


def addon_folder(addons_dir):
    try:
        folder = os.path.join(addons_dir(), "IndexOfAzeroth")
    except (GameNotFound, OSError):
        return None
    return folder if os.path.isfile(os.path.join(folder, "IndexOfAzeroth.toc")) else None


class Pending:
    def __init__(self, addons_dir, state_path=None):
        self.addons_dir = addons_dir
        self.state_path = state_path
        self.lock = threading.Lock()
        self.guides = store.load_json(state_path, {}) if state_path else {}
        for g in self.guides.values():
            if g and "check" not in g:
                g["check"] = line_check(g.get("line"))

    def path(self):
        folder = addon_folder(self.addons_dir)
        return folder and os.path.join(folder, FILE)

    def _write(self, change):
        with self.lock:
            path = self.path()
            if not path:
                return False
            guides = dict(self.guides)
            change(guides)
            write_in_place(path, render(guides))
            self.guides = guides
            if self.state_path:
                store.save_json(self.state_path, self.guides)
            return True

    def set(self, line, who=None, title="", page="", what=""):
        slot = slot_of(line)
        if not slot:
            return False
        now = time.time()
        guide = {"id": str(int(now * 1000)), "line": line, "at": now, **{k: (who or {}).get(k) or "" for k in CHAR_FIELDS},
                 "title": title, "page": page, "what": what, "check": line_check(line)}
        return self._write(lambda g: g.__setitem__(slot, guide))

    def brief(self):
        out = {}
        for slot, g in list(self.guides.items()):
            if not g:
                continue
            m = re.match(COMMAND + r"(\w+)\s", g.get("line") or "")
            k = (m.group(1).lower() if m else "")
            out[slot] = {"kind": LOOP_WORDS.get(k, "gold"), "what": g.get("what") or "", "title": g.get("title") or "",
                         "at": g.get("at"), "page": g.get("page") or "", **{f: g[f] for f in CHAR_FIELDS if f in g},
                         "check": g.get("check")}
            look = line_look(g.get("line"))
            if look:
                out[slot]["look"] = look
        return out

    def clear(self, slot=None):
        return self._write(lambda g: g.pop(slot, None) if slot else g.clear())

    def ensure(self):
        with self.lock:
            path = self.path()
            if path and not os.path.exists(path):
                write_in_place(path, render(None))
