# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import io
import os
import struct
import threading

from PIL import Image

import casc
import client
import game
import mainstores

OUT = mainstores.path("icons")
LACKING = mainstores.path("icons_fallback")
SIZES = (36, 56, 64)
SLOTS = {"head": "Head", "neck": "Neck", "shoulder": "Shoulder", "chest": "Chest", "shirt": "Shirt", "tabard": "Tabard",
         "wrists": "Wrists", "hands": "Hands", "waist": "Waist", "legs": "Legs", "feet": "Feet", "finger": "Finger",
         "trinket": "Trinket", "mainhand": "MainHand", "offhand": "SecondaryHand", "ranged": "Ranged", "relic": "Relic",
         "ammo": "Ammo", "bag": "Bag"}


def names(build, stored=False):
    out, slots = {}, {f"UI-PaperDoll-Slot-{v}.blp".lower(): f"inventoryslot_{k}" for k, v in SLOTS.items()}
    for r in client.rows("ManifestInterfaceData", build, stored=stored):
        folder, file = r["FilePath"].lower().replace("/", "\\"), r["FileName"].lower()
        if folder.startswith("interface\\icons\\") and file.endswith(".blp"):
            out.setdefault(file[:-4].strip(), int(r["ID"]))
        elif folder == "interface\\paperdoll\\" and file in slots:
            out[slots[file]] = int(r["ID"])
    return out


def picture(blp):
    if blp[:4] == b"BLP2" and blp[8] == 3:
        width, height = struct.unpack_from("<II", blp, 12)
        offset = struct.unpack_from("<I", blp, 20)[0]
        im = Image.frombuffer("RGBA", (width, height), blp[offset:offset + width * height * 4], "raw", "BGRA", 0, 1)
    else:
        im = Image.open(io.BytesIO(blp))
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        back = Image.new("RGB", im.size, (0, 0, 0))
        back.paste(im, mask=im.split()[3])
        return back
    return im.convert("RGB")


def path(fid, size, out=None):
    return os.path.join(out or OUT, str(size), f"{fid}.jpg")


def have(fid, out=None):
    return all(os.path.exists(path(fid, size, out)) for size in SIZES)


def shipped(fid, size):
    where = path(fid, size, LACKING)
    return where if os.path.exists(where) else None


def keep(fid, im, out=None):
    for size in SIZES:
        where = path(fid, size, out)
        mainstores.refuse_write(where)
        os.makedirs(os.path.dirname(where), exist_ok=True)
        part = f"{where}.{os.getpid()}.{threading.get_ident()}.part"
        (im if im.size == (size, size) else im.resize((size, size), Image.LANCZOS)).save(part, "JPEG", quality=90)
        os.replace(part, where)


def make(fid, build=None, out=None):
    try:
        blp = casc.read(int(fid), build or game.installed_version())
    except (OSError, ValueError, game.GameNotFound):
        return False
    if not blp or not blp.strip(b"\0"):
        return False
    try:
        keep(fid, picture(blp), out)
    except (OSError, ValueError, SyntaxError, NotImplementedError):
        return False
    return True
