# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import io
import json
import os
import sys
import threading

import casc
import datafiles
import mainstores
import store
import realign

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import clientfiles as wm

TILES = mainstores.path("tilecache")
WORLDMAPS = mainstores.path("worldmapcache")
GLOWS = mainstores.path("highlightcache")
CARDS = mainstores.path("cardcache")
ZONE_ART = mainstores.path("mapcache")
UI = mainstores.path("uicache")
PAPERUP = mainstores.path("paperup")
FOGMASKS = mainstores.path("fogmasks")
UI_PICTURES = {"gold": "interface/moneyframe/ui-goldicon.blp", "silver": "interface/moneyframe/ui-silvericon.blp",
               "copper": "interface/moneyframe/ui-coppericon.blp",
               "pickup": "interface/gossipframe/availablequesticon.blp", "turnin": "interface/gossipframe/activequesticon.blp",
               "incomplete": "interface/gossipframe/incompletequesticon.blp",
               "objective": "interface/cursor/attack.blp", "dungeon": "interface/targetingframe/ui-targetingframe-skull.blp",
               "train": "interface/gossipframe/trainergossipicon.blp", "vendor": "interface/gossipframe/vendorgossipicon.blp",
               "bind": "interface/gossipframe/bindergossipicon.blp", "flight": "interface/gossipframe/taxigossipicon.blp",
               "warning": "interface/dialogframe/ui-dialog-icon-alertnew.blp",
               "loot": "interface/icons/inv_misc_bag_12.blp", "grab": "interface/cursor/openhand.blp",
               "pickpocket": "interface/icons/inv_misc_bag_11.blp",
               "use": "interface/cursor/interact.blp", "talk": "interface/gossipframe/gossipgossipicon.blp",
               "heal": "interface/cursor/cast.blp", "event": "interface/cursor/questinteract.blp",
               "explore": "interface/cursor/directions.blp", "escort": "interface/gossipframe/battlemastergossipicon.blp",
               "bank": "interface/gossipframe/bankergossipicon.blp", "inn": "interface/minimap/tracking/innkeeper.blp",
               "camp": "interface/minimap/tracking/food.blp",
               "need": "interface/buttons/ui-grouploot-dice-up.blp", "greed": "interface/buttons/ui-grouploot-coin-up.blp"}
CARD_CROP = [0, 1, 0.3, 0.7]

_turns = threading.Semaphore(4)
_lock = threading.Lock()
_making = {}
_pending = {}
_noted = None


def _index(folder):
    return datafiles.load(os.path.join(folder, "index.json"), {})


def _made_from(folder, name):
    with _lock:
        if name in _pending.get(folder, {}):
            return _pending[folder][name]
    return _index(folder).get(name)


def flush():
    with _lock:
        for folder in list(_pending):
            if not mainstores.in_main(folder):
                path = os.path.join(folder, "index.json")
                os.makedirs(folder, exist_ok=True)
                store.save_json(path, {**store.load_json(path, {}), **_pending[folder]}, indent=None)
            del _pending[folder]


def _sig(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def made_of(fids, build, *how):
    return _sig(casc.files_print(fids, build), *how)


def _matches(folder, name, sig):
    return _made_from(folder, name) in (None, sig)


def _current(folder, name, path, sig):
    if not os.path.exists(path):
        return False
    if _made_from(folder, name) is None:
        _made(folder, name, sig)
    return _matches(folder, name, sig)


def _made(folder, name, sig):
    with _lock:
        _pending.setdefault(folder, {})[name] = sig
        if _noted is not None:
            _noted.append((folder, name, sig))


def record():
    global _noted
    with _lock:
        if _noted is None:
            _noted = []


def noted():
    with _lock:
        out = list(_noted or ())
        if _noted:
            _noted.clear()
    return out


def note(changes):
    with _lock:
        for folder, name, sig in changes:
            _pending.setdefault(folder, {})[name] = sig


def _once(path, make):
    with _lock:
        lock = _making.setdefault(path, threading.Lock())
    with lock:
        return make()


def _again(path, kind="map pictures"):
    return realign.working(kind, when=os.path.exists(path))


def download(fid, build):
    with _turns:
        return wm._download(wm.file_address(fid, build))


def on_hand(spec):
    if not spec or not os.path.exists(spec[2]):
        return None, False
    folder, name, path, sig = spec
    return path, sig is None or _matches(folder, name, sig)


def stamp(spec):
    if not spec or not os.path.exists(spec[2]):
        return None
    folder, name, path, _ = spec
    return _made_from(folder, name) or f"t{os.stat(path).st_mtime_ns:x}"


def floor_tiles(tiles, floors):
    keep = {str(f["instance"]) for f in (floors or {}).values() if f.get("tilesOnly") and "instance" in f}
    return {**tiles, "instances": {i: k for i, k in (tiles.get("instances") or {}).items() if i in keep}}


def tile_spec(tiles, instance, key):
    fid = tiles["instances"].get(str(instance), {}).get(key)
    return fid and (TILES, f"{instance}/{key}", os.path.join(TILES, str(instance), f"{key}.jpg"),
                    made_of([fid], tiles.get("version")))


def worldmap_spec(map_id, art, version):
    return WORLDMAPS, str(map_id), os.path.join(WORLDMAPS, f"{map_id}.jpg"), worldmap_sig(art, version)


def glow_spec(fid, version):
    return GLOWS, str(fid), os.path.join(GLOWS, f"{fid}.png"), made_of([fid], version)


def ui_spec(name):
    return name in UI_PICTURES and (UI, name, os.path.join(UI, f"{name}.png"), None)


def card_spec(d, version):
    return CARDS, d["key"], os.path.join(CARDS, f"{d['key']}.jpg"), made_of([d["card"]], version,
                                                                            d.get("cardCrop") or CARD_CROP)


def zone_art_spec(area):
    return ZONE_ART, str(area), os.path.join(ZONE_ART, f"{area}.jpg"), None


def zone_art_areas(maps):
    return [m["area"] for m in maps.values() if not m.get("art") and m.get("type") == 3 and m.get("area")]


def paper_source(map_id, area=None):
    for path in (os.path.join(WORLDMAPS, f"{map_id}.jpg"), area and os.path.join(ZONE_ART, f"{area}.jpg")):
        if path and os.path.isfile(path):
            return path
    return None


_prints = {}


def file_print(path):
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size)
    if key not in _prints:
        with open(path, "rb") as f:
            _prints[key] = hashlib.sha1(f.read()).hexdigest()[:16]
    return _prints[key]


def paperup_index():
    return _index(PAPERUP)


def paperup_sig(map_id, area=None):
    source, made = paper_source(map_id, area), os.path.join(PAPERUP, f"{map_id}.jpg")
    if not source or not os.path.isfile(made):
        return None
    sig = paperup_index().get(str(map_id))
    return sig if sig and sig == file_print(source) else None


def paperup_spec(map_id, area=None):
    return paperup_sig(map_id, area) and (PAPERUP, str(map_id), os.path.join(PAPERUP, f"{map_id}.jpg"), None)


def _save(path, img, form="PNG", **how):
    buf = io.BytesIO()
    img.save(buf, form, **how)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.write_bytes(path, buf.getvalue())


def tile(tiles, instance, key):
    from PIL import Image
    spec = tile_spec(tiles, instance, key)
    if not spec:
        return None
    fid = tiles["instances"][str(instance)][key]
    _, name, path, sig = spec
    if _current(TILES, name, path, sig):
        return path

    def make():
        if not _current(TILES, name, path, sig):
            with _again(path):
                _save(path, Image.open(io.BytesIO(download(fid, tiles["version"]))).convert("RGB"), "JPEG", quality=88)
            _made(TILES, name, sig)
        return path
    return _once(path, make)


def worldmap_sig(art, version):
    fids = [f for row in art["files"] for f in row if f] + [f for o in art.get("overlays") or () for row in o["files"]
                                                            for f in row if f]
    how = [art["files"], art["width"], art["height"]] + ([art["overlays"]] if art.get("overlays") else [])
    return made_of(fids, art.get("version") or version, *how)


def overlay_picture(overlay, size, image_of):
    from PIL import Image
    out = Image.new("RGBA", (overlay["width"], overlay["height"]), (0, 0, 0, 0))
    for r, row in enumerate(overlay["files"]):
        for c, fid in enumerate(row):
            width, height = min(size, overlay["width"] - c * size), min(size, overlay["height"] - r * size)
            if fid and width > 0 and height > 0:
                out.paste(image_of(fid).convert("RGBA").crop((0, 0, width, height)), (c * size, r * size))
    return out


def paint(sheet, overlay, size, image_of):
    part = overlay_picture(overlay, size, image_of)
    sheet.paste(part, (overlay["x"], overlay["y"]), part)


def worldmap(map_id, art, version):
    from PIL import Image
    _, name, path, sig = worldmap_spec(map_id, art, version)
    version = art.get("version") or version
    if _current(WORLDMAPS, name, path, sig):
        return path

    def picture(fid):
        return Image.open(io.BytesIO(download(fid, version)))

    def make():
        if not _current(WORLDMAPS, name, path, sig):
            size = art["tile"]
            sheet = Image.new("RGB", (len(art["files"][0]) * size, len(art["files"]) * size))
            with _again(path):
                for r, row in enumerate(art["files"]):
                    for c, fid in enumerate(row):
                        if fid:
                            sheet.paste(picture(fid).convert("RGB"), (c * size, r * size))
                for overlay in art.get("overlays", ()):
                    paint(sheet, overlay, size, picture)
                _save(path, sheet.crop((0, 0, art["width"], art["height"])), "JPEG", quality=92)
            _made(WORLDMAPS, name, sig)
        return path
    return _once(path, make)


def fogmask_spec(map_id, art, version):
    overlays = art.get("overlays")
    if not overlays:
        return None
    fids = [f for o in overlays for row in o["files"] for f in row if f]
    return FOGMASKS, str(map_id), fogmask_path(map_id), made_of(fids, art.get("version") or version, "fogmask", overlays)


def fogmask_path(map_id, folder=None):
    return os.path.join(folder or FOGMASKS, f"{map_id}.png")


def fogmask_places(art):
    out, top = [], 0
    for o in art.get("overlays") or ():
        out.append((0, top, o["width"], o["height"]))
        top += o["height"]
    return out


def fogmask(map_id, art, version):
    from PIL import Image
    spec = fogmask_spec(map_id, art, version)
    if not spec:
        return None
    _, name, path, sig = spec
    version = art.get("version") or version
    if _current(FOGMASKS, name, path, sig):
        return path

    def picture(fid):
        return Image.open(io.BytesIO(download(fid, version)))

    def make():
        if not _current(FOGMASKS, name, path, sig):
            places = fogmask_places(art)
            sheet = Image.new("L", (max(w for _, _, w, _ in places), sum(h for _, _, _, h in places)), 0)
            with _again(path):
                for overlay, (left, top, _, _) in zip(art["overlays"], places):
                    sheet.paste(overlay_picture(overlay, art["tile"], picture).getchannel("A"), (left, top))
                _save(path, sheet)
            _made(FOGMASKS, name, sig)
        return path
    return _once(path, make)


def glow(fid, version):
    from PIL import Image
    _, name, path, sig = glow_spec(fid, version)
    if _current(GLOWS, name, path, sig):
        return path

    def make():
        if not _current(GLOWS, name, path, sig):
            with _again(path):
                img = Image.open(io.BytesIO(download(fid, version))).convert("RGB")
            _save(path, img)
            _made(GLOWS, name, sig)
        return path
    return _once(path, make)


CURSORS = "interface/cursor/"
ICONS = "interface/icons/"
ICON_EDGE = 0.08
POINTER_CORNER = 0.4
SEEN_ALPHA = 16


def trim_cursor(img):
    from PIL import Image
    w, h = img.size
    alpha = img.getchannel("A").load()
    seen, patches = set(), []
    for y0 in range(h):
        for x0 in range(w):
            if (x0, y0) in seen or alpha[x0, y0] < SEEN_ALPHA:
                continue
            todo, patch = [(x0, y0)], []
            seen.add((x0, y0))
            while todo:
                x, y = todo.pop()
                patch.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and alpha[nx, ny] >= SEEN_ALPHA:
                        seen.add((nx, ny))
                        todo.append((nx, ny))
            patches.append(patch)
    tip = [p for p in patches if max(x for x, _ in p) < w * POINTER_CORNER and max(y for _, y in p) < h * POINTER_CORNER]
    keep = [p for p in patches if p not in tip]
    if not keep:
        return img
    out = img.copy()
    px = out.load()
    for x, y in (pt for p in tip for pt in p):
        px[x, y] = (0, 0, 0, 0)
    x0, y0 = min(x for p in keep for x, _ in p), min(y for p in keep for _, y in p)
    x1, y1 = max(x for p in keep for x, _ in p) + 1, max(y for p in keep for _, y in p) + 1
    side = max(x1 - x0, y1 - y0)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(out.crop((x0, y0, x1, y1)), ((side - (x1 - x0)) // 2, (side - (y1 - y0)) // 2))
    return square


def ui_picture(name, version):
    from PIL import Image, ImageChops
    fid = wm.listfile_ui().get(UI_PICTURES.get(name, ""))
    if not fid:
        return None
    cursor, icon = UI_PICTURES[name].startswith(CURSORS), UI_PICTURES[name].startswith(ICONS)
    path = os.path.join(UI, f"{name}.png")
    sig = made_of([fid], version, "alpha", *(["trim"] if cursor else ["edge"] if icon else []))
    if _current(UI, name, path, sig):
        return path

    def make():
        if not _current(UI, name, path, sig):
            with _again(path, "interface pictures"):
                img = Image.open(io.BytesIO(download(fid, version))).convert("RGBA")
                if img.getextrema()[3] == (0, 0):
                    r, g, b, _ = img.split()
                    img.putalpha(ImageChops.lighter(ImageChops.lighter(r, g), b))
                if cursor:
                    img = trim_cursor(img)
                elif icon:
                    w, h = img.size
                    img = img.crop((round(w * ICON_EDGE), round(h * ICON_EDGE), round(w * (1 - ICON_EDGE)), round(h * (1 - ICON_EDGE))))
                _save(path, img)
            _made(UI, name, sig)
        return path
    return _once(path, make)


def card(d, version):
    from PIL import Image
    crop = d.get("cardCrop") or CARD_CROP
    _, name, path, sig = card_spec(d, version)
    if _current(CARDS, name, path, sig):
        return path

    def make():
        if not _current(CARDS, name, path, sig):
            with _again(path, "dungeon pictures"):
                im = Image.open(io.BytesIO(download(d["card"], version))).convert("RGB")
                x0, x1, y0, y1 = crop
                w, h = im.size
                im = im.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
                im.thumbnail((720, 720))
                _save(path, im, "JPEG", quality=86)
            _made(CARDS, name, sig)
        return path
    return _once(path, make)
