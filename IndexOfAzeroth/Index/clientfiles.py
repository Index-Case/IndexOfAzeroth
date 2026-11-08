# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import contextvars
import glob
import hashlib
import threading
import io, math, os, re, struct, time, urllib.error
import concurrent.futures as cf

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "buildcache")
TILE_YARDS = 128.0
IMAGE_PX = 2.0
MAX_SIDE = 4096

import store
from game import installed_version, version_key
import client
import mainstores
from facts import MAP_CORNER
import storedonly
from storedonly import NotBuilt
from storedonly import is_stored_only, stored_only
import carried
import casc
import navstore


DOWNLOADS = 6
_flight, _flight_lock = {}, threading.Lock()

_NAME = __name__
_bg = carried.switch(_NAME, "bg", False)
_fill = carried.switch(_NAME, "fill", False)
_rec = contextvars.ContextVar(f"{_NAME}.rec", default=())
_unbuilt = contextvars.ContextVar(f"{_NAME}.unbuilt", default=())


@contextlib.contextmanager
def _set(var, value):
    token = var.set(value)
    try:
        yield
    finally:
        var.reset(token)


def background():
    return _set(_bg, True)


def in_background():
    return _bg.get()


def carrying(fn):
    return fn


_serving = False


def serve_built():
    global _serving
    _serving = True


def serving():
    return _serving and not _fill.get()


def filling():
    return _set(_fill, True)


@contextlib.contextmanager
def noting_unbuilt():
    found = set()
    with _set(_unbuilt, _unbuilt.get() + (found,)):
        yield found


def note_unbuilt(what):
    for found in _unbuilt.get():
        found.add(what)




def kept_file(name):
    path = mainstores.standing(os.path.join(CACHE, name))
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        raise NotBuilt(("file", name)) from None
    if not data:
        raise NotBuilt(("file", name))
    return data


@contextlib.contextmanager
def kept_only(when=True):
    if not when:
        yield
        return
    with stored_only():
        yield


SWITCH = os.path.join(CACHE, "client-build.json")
BEFORE_NOTES = "1.60.1.70532"
PART_AGE = 600
_switch = {"at": None, "data": {}}
_switch_lock = threading.Lock()
_mine = {"pid": None, "file": None, "build": None, "names": set()}
_changed = {"seen": None, "names": set()}


def _switch_data():
    path = mainstores.standing(SWITCH)
    try:
        at = os.path.getmtime(path)
    except OSError:
        return {}
    if _switch["at"] != at:
        try:
            _switch["data"] = store.load_json(path, {})
        except OSError:
            return _switch["data"]
        _switch["at"] = at
    return _switch["data"]


def changed_dir():
    return os.path.splitext(SWITCH)[0] + "-changed"


def switched_since():
    return float(_switch_data().get("since", 0))


def switched_build():
    return _switch_data().get("build")


def _arrivals(data):
    return list(data.get("before") or ()) + ([{"build": data["build"], "since": data.get("since", 0)}]
                                             if data.get("build") else [])


def build_at(when):
    at = [a["build"] for a in _arrivals(_switch_data()) if float(a.get("since") or 0) <= when]
    return at[-1] if at else BEFORE_NOTES


def note_switch(build):
    with _switch_lock, store.locked(SWITCH):
        _switch["at"] = None
        had = _switch_data()
        if had.get("build") == build:
            return
        store.save_json(SWITCH, {"build": build, "since": time.time(), "before": _arrivals(had)}, indent=None)


def _note_changed(name):
    with _switch_lock:
        if _mine["pid"] != os.getpid():
            _mine.update(pid=os.getpid(), file=f"{os.getpid()}-{os.urandom(4).hex()}.json", build=None, names=set())
        build = switched_build()
        if _mine["build"] != build:
            _mine.update(build=build, names=set())
        _mine["names"].add(name)
        os.makedirs(changed_dir(), exist_ok=True)
        store.save_json(os.path.join(changed_dir(), _mine["file"]), {"build": build, "changed": sorted(_mine["names"])},
                        indent=None)


def changed_copies():
    folder, build = changed_dir(), switched_build()
    try:
        seen = tuple(sorted((e.name, e.stat().st_mtime_ns) for e in os.scandir(folder) if e.name.endswith(".json")))
    except OSError:
        seen = ()
    with _switch_lock:
        if _changed["seen"] != (build, seen):
            names, whole = set(), True
            for name, _ in seen:
                try:
                    note = store.load_json(os.path.join(folder, name), {})
                except OSError:
                    whole = False
                    continue
                if note.get("build") == build:
                    names.update(note.get("changed") or ())
            _changed.update(seen=(build, seen) if whole else None, names=names)
        return _changed["names"]


def clean_leftovers(now=None):
    now = time.time() if now is None else now
    gone, build = [], switched_build()
    folder = changed_dir()
    try:
        notes = [os.path.join(folder, n) for n in os.listdir(folder)]
    except OSError:
        notes = []
    for path in glob.glob(glob.escape(SWITCH) + ".*.part") + [p for p in notes if p.endswith(".part")]:
        try:
            if now - os.path.getmtime(path) >= PART_AGE:
                os.remove(path)
                gone.append(path)
        except OSError:
            pass
    for path in notes:
        if path.endswith(".json"):
            try:
                if store.load_json(path, {}).get("build") != build:
                    os.remove(path)
                    gone.append(path)
            except OSError:
                pass
    return gone


@contextlib.contextmanager
def recording():
    used = set()
    with _set(_rec, _rec.get() + (used,)):
        yield used


def note_sources(names):
    for used in _rec.get():
        used.update(names)


def casc_url(name):
    m = re.match(r"[a-z0-9]+-([0-9]+)[.]", name)
    return m and file_address(m[1], installed_version())


def touch(path):
    now = time.time()
    navstore.make_loose(path)
    os.utime(path, (now, now))


def mark_checked(path):
    if not is_stored_only():
        touch(path)


UNKNOWN_SOURCE = "unknown"


def still_good(path, sources):
    since = switched_since()
    if navstore.getmtime(path) >= since:
        return True
    if not sources:
        return False
    for name in sources:
        url = casc_url(name)
        if not url:
            return False
        if not is_stored_only():
            try:
                fetch(url, name)
            except OSError as e:
                if storedonly.not_there(e):
                    continue
                return True
        if name in changed_copies():
            return False
    mark_checked(path)
    return True



_ADDRESS = re.compile(r"(?:^|/)casc/(\d+)[?]version=([^&#]+)$")


def file_address(fid, build):
    return f"casc/{fid}?version={build}"


def addressed_file(url):
    m = _ADDRESS.search(url)
    return (int(m[1]), m[2]) if m else None


class Absent(urllib.error.HTTPError):

    def __init__(self, url):
        super().__init__(url, 404, "empty answer: the build doesn't hold the file", {}, None)


def kept_or_installed(url, cache=None):
    if cache:
        try:
            return kept_file(cache)
        except NotBuilt:
            pass
    file = addressed_file(url)
    data = casc.read(*file) if file else None
    if not data:
        raise NotBuilt(("file", cache or url))
    if cache:
        os.makedirs(CACHE, exist_ok=True)
        store.write_fetched(os.path.join(CACHE, cache), data)
    return data


def _download(url):
    file = addressed_file(url)
    if file is None:
        raise ValueError(f"{url} isn't a client file's address")
    data = casc.read(*file)
    data = data if data is not None else _remote(url)
    if not data:
        raise Absent(url)
    return data


def _remote(url):
    sources = storedonly.sources()
    if sources is None:
        raise storedonly.NotStored(f"Not stored yet: the client's file {url}")
    return sources.file(*addressed_file(url))


_builds = []


def older_builds(build):
    names = mainstores.listing(CACHE)
    key = version_key

    def before(builds):
        return sorted((b for b in builds if key(b)[:2] == key(build)[:2] and key(b) < key(build)), key=key, reverse=True)
    found = before({m[1] for m in (re.search(r"-(\d+(?:\.\d+)+)\.csv$", n) for n in names) if m})
    if found:
        return found
    sources = storedonly.sources()
    if not _builds and sources is not None:
        try:
            _builds.extend(sources.builds())
        except (OSError, ValueError):
            return []
    return before(_builds)


OLDER_TRIES = 3


def from_older(url):
    file = addressed_file(url)
    if not file:
        return None
    fid, newer = file
    for build in older_builds(newer)[:OLDER_TRIES]:
        try:
            return _download(file_address(fid, build))
        except OSError:
            continue
    return None


def fetch_dropped(url, cache):
    try:
        return fetch(url, cache)
    except Absent:
        if is_stored_only():
            raise
        data = from_older(url)
        if data is None:
            raise
        os.makedirs(CACHE, exist_ok=True)
        store.write_fetched(os.path.join(CACHE, cache), data)
        return data


def fetch(url, cache=None, max_age=None):
    if is_stored_only():
        return kept_or_installed(url, cache)
    path = cache and os.path.join(CACHE, cache)
    versioned = "version=" in url
    if cache and versioned:
        note_sources([cache])

    def kept():
        copy = path and mainstores.standing(path)
        if copy and os.path.exists(copy) and (max_age is None or time.time() - os.path.getmtime(copy) < max_age) and not (
                versioned and os.path.getmtime(copy) < switched_since()) and not (not versioned and store.refresh_due(cache)):
            with open(copy, "rb") as f:
                data = f.read()
            if data or not versioned:
                return data
        return None
    data = kept()
    if data is not None:
        return data
    mine = True
    if path:
        with _flight_lock:
            event = _flight.get(path)
            mine = event is None
            if mine:
                event = _flight[path] = threading.Event()
        if not mine:
            event.wait()
            data = kept()
            if data is not None:
                return data
    old, ours = None, True
    copy = path and mainstores.standing(path)
    if copy and os.path.exists(copy):
        with open(copy, "rb") as f:
            old = f.read()
        ours = copy == path
        if versioned and not old:
            old = None
    try:
        try:
            data = _download(url)
        except OSError as e:
            if old is not None:
                if isinstance(e, Absent) and ours:
                    touch(path)
                return old
            raise
        if path and old is not None and data == old and ours:
            touch(path)
        elif path:
            os.makedirs(CACHE, exist_ok=True)
            store.write_fetched(path, data)
            if old is not None and versioned and data != old:
                _note_changed(cache)
        if path and not versioned:
            store.refreshed(cache)
        return data
    finally:
        if path and mine:
            with _flight_lock:
                _flight.pop(path, None)
            event.set()


def chunks(b):
    at, out = 0, {}
    while at + 8 <= len(b):
        tag = b[at:at + 4][::-1].decode("latin1")
        size = struct.unpack_from("<I", b, at + 4)[0]
        out.setdefault(tag, b[at + 8:at + 8 + size])
        at += 8 + size
    return out




def listed(name, want, kept=False, url=None):
    path = os.path.join(CACHE, name)
    copy = mainstores.standing(path)
    have = os.path.exists(copy)
    sources = None if kept else storedonly.sources()
    if sources is None and not have:
        return []
    if sources is not None and (not have or _read_sign(copy + ".want") != filter_sign(want)):
        try:
            raw = sources.listfile(url)
        except OSError:
            if not have:
                raise
        else:
            make_listed({"name": name, "want": want}, raw)
    with open(mainstores.standing(path), encoding="utf-8") as f:
        return f.read().splitlines()


def make_listed(copy, raw):
    path = os.path.join(CACHE, copy["name"])
    lines = [line for line in raw.splitlines() if copy["want"](line)]
    os.makedirs(CACHE, exist_ok=True)
    store.write_fetched(path, "\n".join(lines).encode("utf-8"))
    store.save_json(path + ".want", filter_sign(copy["want"]))
    return len(lines)


def filter_sign(want):
    import types
    code = getattr(want, "__code__", None)
    if code is None:
        return repr(want)

    def body(c):
        consts = tuple(body(k) if isinstance(k, types.CodeType) else repr(k) for k in c.co_consts)
        return c.co_code + repr((consts, c.co_names)).encode()
    return hashlib.sha1(body(code)).hexdigest()[:16]


def _read_sign(path):
    try:
        return store.load_json(path, None)
    except (OSError, ValueError):
        return None


def wmo_line(line):
    return line.endswith(".wmo") or "minimaps/wmo/" in line


def m2_line(line):
    return line.endswith(".m2")


def terrain_line(line):
    return ";tileset/" in line.lower()


WMO = {"name": "listfile-wmo.csv", "want": wmo_line}
M2 = {"name": "listfile-m2.csv", "want": m2_line}
TERRAIN = {"name": "listfile-terrain.csv", "want": terrain_line}


def listfile(kept=False):
    wmos, minimaps = {}, {}
    for line in listed(**WMO, kept=kept):
        fid, _, name = line.strip().partition(";")
        if not fid.isdigit():
            continue
        if name.endswith(".wmo"):
            wmos[int(fid)] = name
        else:
            minimaps[name] = int(fid)
    return wmos, minimaps


UI_PATHS = ("interface/moneyframe/", "interface/gossipframe/", "interface/cursor/", "interface/targetingframe/",
            "interface/dialogframe/", "interface/minimap/tracking/", "interface/icons/inv_misc_bag_",
            "interface/buttons/ui-grouploot-")


def ui_line(line):
    return line.partition(";")[2].lower().startswith(UI_PATHS)


UI = {"name": "listfile-ui-0e6b94bd.csv", "want": ui_line}


def listfile_ui():
    out = {}
    for line in listed(**UI):
        fid, _, name = line.strip().partition(";")
        if fid.isdigit():
            out[name.lower()] = int(fid)
    return out


def add_placements(body, corner, seen, out):
    for i in range(0, len(body) - 63, 64):
        m = struct.unpack_from("<II3f3f3f3fHHHH", body, i)
        if m[1] in seen and m[1] != 0xFFFFFFFF:
            continue
        seen.add(m[1])
        px, py, pz = m[2:5]
        ox, oy = (corner - pz, corner - px) if corner else (-pz, -px)
        (x1, _, z1), (x2, _, z2) = m[8:11], m[11:14]
        box = (min(corner - z1, corner - z2), max(corner - z1, corner - z2), min(corner - x1, corner - x2), max(corner - x1, corner - x2))
        out.append((m[0], ox, oy, py, m[6], m[1], box))


def map_file(map_row, version):
    return chunks(fetch(file_address(map_row['WdtFileDataID'], version), f"wdt-{map_row['WdtFileDataID']}.wdt"))


def tile_placements(wdt, cells, version, seen=None, out=None):
    seen, out = (set() if seen is None else seen), ([] if out is None else out)
    maid = wdt.get("MAID", b"")
    for col, row in cells:
        if not (0 <= col < 64 and 0 <= row < 64):
            continue
        e = struct.unpack_from("<8I", maid, (row * 64 + col) * 32) if len(maid) >= (row * 64 + col + 1) * 32 else None
        if e and e[1]:
            obj = chunks(fetch(file_address(e[1], version), f"obj-{e[1]}.adt"))
            if "MODF" in obj:
                add_placements(obj["MODF"], MAP_CORNER, seen, out)
    return out


def placements(map_row, version):
    c = map_file(map_row, version)
    out, seen = [], set()
    if "MODF" in c:
        add_placements(c["MODF"], 0, seen, out)
    if "MAID" in c:
        tile_placements(c, [(col, row) for row in range(64) for col in range(64)], version, seen, out)
    return out


def building(fid, version):
    return [box for _, box in building_rooms(fid, version)]


INDOOR_ROOM = 0x2000


def building_rooms(fid, version):
    root = chunks(fetch_dropped(file_address(fid, version), f"wmo-{fid}.wmo"))
    mogi = root.get("MOGI", b"")
    return [(v[0], v[1:7]) for v in (struct.unpack_from("<I6fi", mogi, i) for i in range(0, len(mogi) - 31, 32))]


def outdoors(map_row, version):
    return any(not flags & INDOOR_ROOM for fid, *_ in placements(map_row, version) for flags, _ in building_rooms(fid, version))


def wmo_id(fid, version):
    root = chunks(fetch_dropped(file_address(fid, version), f"wmo-{fid}.wmo"))
    mohd = root.get("MOHD", b"")
    return struct.unpack_from("<I", mohd, 32)[0] if len(mohd) >= 36 else None


_textures = {}


def wmo_tiles(fid, version):
    if version not in _textures:
        table = {}
        for r in client.rows("WMOMinimapTexture", version):
            table.setdefault(int(r["WMOID"]), {})[(int(r["GroupNum"]), int(r["BlockX"]), int(r["BlockY"]))] = int(r["FileDataID"])
        _textures[version] = table
    try:
        own = wmo_id(fid, version)
    except OSError:
        return {}
    return _textures[version].get(own) or {}


def tile_image(fid, version):
    try:
        raw = fetch(file_address(fid, version), f"mm-{fid}.blp")
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        try:
            os.remove(os.path.join(CACHE, f"mm-{fid}.blp"))
        except OSError:
            pass
        return None
    return np.array(im.transpose(Image.TRANSPOSE).transpose(Image.FLIP_LEFT_RIGHT))


def minimap_index():
    wmos, minimaps = listfile()
    by_prefix = {}
    for name, fid in minimaps.items():
        m = re.match(r"(.*)_(\d{3})_(\d{2})_(\d{2})\.blp$", name)
        if m:
            by_prefix.setdefault(m[1], {})[(int(m[2]), int(m[3]), int(m[4]))] = fid
    return wmos, by_prefix


def room_pictures(fid, version, wmos, by_prefix):
    path = wmos.get(fid)
    prefix = path and path[:-4].replace("world/wmo/", "world/minimaps/wmo/", 1)
    return (prefix and by_prefix.get(prefix)) or wmo_tiles(fid, version), prefix


def pieces_of(places, version, wmos, by_prefix, consulted=None):
    pieces = []
    for fid, ox, oy, oz, yaw, *_ in places:
        tiles, prefix = room_pictures(fid, version, wmos, by_prefix)
        if consulted is not None:
            consulted[str(fid)] = prefix
        if not tiles:
            continue
        groups = building(fid, version)
        a = math.radians(180 + yaw)
        ca, sa = math.cos(a), math.sin(a)
        for (g, i, j), tfid in tiles.items():
            if g >= len(groups):
                continue
            gx0, gy0 = groups[g][0], groups[g][1]
            lx0, ly0 = gx0 + i * TILE_YARDS, gy0 + j * TILE_YARDS
            pieces.append((tfid, (ox, oy, ca, sa, lx0, ly0), oz + (groups[g][2] + groups[g][5]) / 2,
                           (fid, groups[g][2], groups[g][5])))
    return pieces


BLANK = 248
WATER_RGB = (64, 144, 165)
WATER_SLACK = 1.0


def building_water(fid, version):
    import wmonav
    return wmonav.building_geometry(fid, version)["water"]


def watered(img, room, corner, version):
    blank = (img[..., :3] >= BLANK).all(axis=2) & (img[..., 3] > 0)
    if not blank.any():
        return img
    import wmonav
    fid, z0, z1 = room
    x0, y0 = corner
    h, w = img.shape[:2]
    half = wmonav.UNIT / 2
    water = building_water(fid, version)
    x, y, z = (water[:, k] for k in range(3))
    near = ((z >= z0 - WATER_SLACK) & (z <= z1 + WATER_SLACK) & (x + half > x0) & (x - half < x0 + h / IMAGE_PX)
            & (y + half > y0) & (y - half < y0 + w / IMAGE_PX))
    wet = np.zeros((h, w), bool)
    for wx, wy in zip(x[near], y[near]):
        r0, r1 = max(0, math.floor((wx - half - x0) * IMAGE_PX)), min(h, math.ceil((wx + half - x0) * IMAGE_PX))
        c0, c1 = max(0, math.floor((wy - half - y0) * IMAGE_PX)), min(w, math.ceil((wy + half - y0) * IMAGE_PX))
        wet[r0:r1, c0:c1] = True
    blank &= wet
    if not blank.any():
        return img
    out = img.copy()
    out[blank, :3] = WATER_RGB
    return out


def room_image(fid, room, corner, version):
    img = tile_image(fid, version)
    if img is None:
        return None
    try:
        return watered(img, room, corner, version)
    except OSError:
        return None


def compose(pieces, version, max_side=MAX_SIDE, missing=None):
    rooms = {}
    for fid, t, _, room in pieces:
        rooms.setdefault(fid, (room, t[4:6]))
    with cf.ThreadPoolExecutor(8) as pool:
        unique = sorted(rooms)
        images = dict(zip(unique, pool.map(lambda fid: room_image(fid, *rooms[fid], version), unique)))
    if missing is not None:
        missing.extend(fid for fid in unique if images[fid] is None)
    pieces = [p for p in pieces if images.get(p[0]) is not None]
    if not pieces:
        return None

    def world_of(t, u, v, size):
        ox, oy, ca, sa, lx0, ly0 = t
        s = 1 / IMAGE_PX
        lx, ly = lx0 + v * s, ly0 + u * s
        return ox + lx * ca - ly * sa, oy + lx * sa + ly * ca
    corners = [world_of(t, u, v, images[fid].shape[1]) for fid, t, *_ in pieces for u, v in ((0, 0), (images[fid].shape[1], 0),
               (0, images[fid].shape[0]), images[fid].shape[1::-1])]
    X0, X1 = min(c[0] for c in corners), max(c[0] for c in corners)
    Y0, Y1 = min(c[1] for c in corners), max(c[1] for c in corners)
    PX = min(IMAGE_PX, max_side / max(Y1 - Y0, X1 - X0))
    W, H = int(math.ceil((Y1 - Y0) * PX)) + 2, int(math.ceil((X1 - X0) * PX)) + 2
    canvas = np.zeros((H, W, 4), np.float32)
    for fid, t, *_ in sorted(pieces, key=lambda p: p[2]):
        img = images[fid].astype(np.float32)
        size = img.shape[1]
        p0, pu, pv = world_of(t, 0, 0, size), world_of(t, 1, 0, size), world_of(t, 0, 1, size)
        col = lambda w: (Y1 - w[1]) * PX
        line = lambda w: (X1 - w[0]) * PX
        M = np.array([[col(pu) - col(p0), col(pv) - col(p0), col(p0)],
                      [line(pu) - line(p0), line(pv) - line(p0), line(p0)]], np.float32)
        h, w = img.shape[:2]
        cs = [M @ np.array([u, v, 1.0]) for u, v in ((0, 0), (w, 0), (0, h), (w, h))]
        c0, r0 = max(0, int(min(c[0] for c in cs)) - 2), max(0, int(min(c[1] for c in cs)) - 2)
        c1, r1 = min(W, int(max(c[0] for c in cs)) + 3), min(H, int(max(c[1] for c in cs)) + 3)
        if c1 <= c0 or r1 <= r0:
            continue
        Mp = M.copy()
        Mp[0, 2] -= c0
        Mp[1, 2] -= r0
        size_p = (c1 - c0, r1 - r0)
        color = cv2.warpAffine(img[..., :3], Mp, size_p, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        cover = cv2.warpAffine(img[..., 3], Mp, size_p, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        alpha = np.clip(cover * 2.0 / 255.0, 0, 1)[..., None]
        patch = canvas[r0:r1, c0:c1]
        patch[..., :3] = color * alpha + patch[..., :3] * (1 - alpha)
        patch[..., 3:4] = np.maximum(patch[..., 3:4], alpha * 255)
    out = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGBA")
    return out, {"left": Y1, "right": Y0, "top": X1, "bottom": X0}
