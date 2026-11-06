# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
import threading

import gamedata
from npcs import fold

LIVE_MOST, FULL_MOST = 25, 250
INSIDE_FROM = 4
TYPO_FROM, TYPO_TWO = 4, 7
WORDS_MOST = 6
TEXT_MOST = 60
PLACEHOLDER = re.compile(r"^monster - |deprecated|\[ph\]|\bdnd\b|^test\b|\bunused\b|^qa\b", re.I)


def off_by(a, b, most):
    if abs(len(a) - len(b)) > most:
        return False
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
        if min(row) > most:
            return False
    return row[-1] <= most


class ItemBook:

    def __init__(self):
        self.lock = threading.Lock()
        self.made = (None, [])

    def entries(self):
        mtime, items, _ = gamedata.client_table("items.json", "items")
        with self.lock:
            if self.made[0] != mtime or mtime is None:
                rows = []
                for item_id, row in items.items():
                    name = row[0] or ""
                    if not name or PLACEHOLDER.search(name):
                        continue
                    folded = fold(name)
                    rows.append((folded, folded.split(), int(item_id), name, row[1], row[2] or "inv_misc_questionmark"))
                self.made = (mtime, rows)
            return self.made[1]


BOOK = ItemBook()


def matches(words, folded, name_words, full):
    for w in words:
        if any(n.startswith(w) for n in name_words) or (len(w) >= INSIDE_FROM and w in folded):
            continue
        most = 2 if len(w) >= TYPO_TWO else 1 if len(w) >= TYPO_FROM else 0
        if not (full and most and any(off_by(w, n[:len(w) + most], most) for n in name_words)):
            return False
    return True


def search(text, full=False, listed=None, book=None):
    book = book or BOOK
    text = fold(str(text or "")[:TEXT_MOST])
    words = text.split()[:WORDS_MOST]
    if not words:
        return [], False
    listed = listed or {}
    found, typos = [], 0
    for folded, name_words, item_id, name, q, icon in book.entries():
        if matches(words, folded, name_words, False):
            found.append((folded, item_id, name, q, icon))
        elif matches(words, folded, name_words, True):
            typos += 1
            if full:
                found.append((folded, item_id, name, q, icon))
    found.sort(key=lambda e: (e[0] != text, not e[0].startswith(text), -listed.get(e[1], 0), len(e[0]), e[0], e[1]))
    most = FULL_MOST if full else LIVE_MOST
    return [e[1:] for e in found[:most]], len(found) > most or (not full and typos > 0)


def icon_stored(name):
    fid = gamedata.icon_names().get(name)
    return bool(fid and os.path.exists(os.path.join(gamedata.ICONS, "36", f"{fid}.jpg"))) \
        or os.path.exists(os.path.join(gamedata.ICON_CACHE, f"{name}.jpg"))


def answer(auctions, text, full=False, keys=None):
    found, more = search(text, full, auctions.listed_counts())
    ah = auctions.summaries([f[0] for f in found])
    return {"house": ah["house"], "more": more,
            "items": [{"item": i, "name": n, "q": q, "icon": icon, "iconStored": icon_stored(icon),
                       "ah": ah["items"].get(str(i)), **({"keys": keys(i, ah["items"].get(str(i)) or {})} if keys else {})}
                      for i, n, q, icon in found]}


def fetch_item(item_id, tips=None, make_icon=None):
    from itemtips import MISSING
    tips = tips or gamedata.ITEM_TIPS
    info = gamedata.item_infos([item_id]).get(str(item_id))
    if not info:
        return None
    tip = tips.tooltip(item_id)
    icon = icon_stored(info["icon"])
    if not icon:
        fid = gamedata.icon_names().get(info["icon"])
        if fid:
            (make_icon or gamedata.make_icon)(fid)
            icon = icon_stored(info["icon"])
    return {"item": item_id, "tooltip": "none" if tip is None else "missing" if tip == MISSING else "stored", "icon": icon}
