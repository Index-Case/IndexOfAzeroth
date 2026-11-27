# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os
import re
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "data", "levelshots")
KINDS = (".jpg", ".jpeg", ".tga", ".png")
SMALL = 480
BIG = 1920
SHOT_NEAR = 20
GLOW_FROM = 2
GLOW_UNTIL = 160
SETTLED = 2
NAME = re.compile(r"^[0-9a-f]{12}-\d{1,3}(-big)?$")


def shot_id(key, level):
    return f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}-{int(level)}"


def listing(folder, now=None):
    now = now or time.time()
    out = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return out
    for e in entries:
        if not e.is_file() or os.path.splitext(e.name)[1].lower() not in KINDS:
            continue
        try:
            t = e.stat().st_mtime
        except OSError:
            continue
        if now - t >= SETTLED:
            out.append((e.path, t))
    return sorted(out, key=lambda pt: pt[1])


def find(files, at, shot_at=None):
    if shot_at:
        near = [(abs(t - shot_at), p, t) for p, t in files if abs(t - shot_at) <= SHOT_NEAR]
        return (min(near)[1], min(near)[2]) if near else None
    if not at:
        return None
    for p, t in files:
        if at + GLOW_FROM <= t <= at + GLOW_UNTIL:
            return p, t
    return None


def copy(src, key, level, dest=STORE):
    from PIL import Image
    name = shot_id(key, level)
    os.makedirs(dest, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        big = im if w <= BIG else im.resize((BIG, round(h * BIG / w)), Image.LANCZOS)
        small = im.resize((SMALL, round(h * SMALL / w)), Image.LANCZOS)
        for pic, path in ((big, os.path.join(dest, name + "-big.jpg")), (small, os.path.join(dest, name + ".jpg"))):
            part = path + ".part"
            pic.save(part, "JPEG", quality=88)
            os.replace(part, path)
        return {"id": name, "at": round(os.path.getmtime(src)), "w": big.size[0], "h": big.size[1]}


def path_of(name, dest=STORE):
    if not isinstance(name, str) or not NAME.match(name):
        return None
    path = os.path.join(dest, name + ".jpg")
    return path if os.path.isfile(path) else None
