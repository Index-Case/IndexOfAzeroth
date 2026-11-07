# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
from types import MappingProxyType

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(ROOT, "words")
SIDES = {"game": ("lua",), "page": ("js",), "both": ("lua", "js")}
KEY = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*$")
NAME = re.compile(r"\{([A-Za-z0-9]+)\}")
PLACEHOLDERS = "# placeholders:"
READ_BY_KEY = ("words", "say", "lines_of", "table")
_kept = {}


class WordsError(ValueError):
    pass


def files(folder=FOLDER):
    out = []

    def walk(rel):
        try:
            with os.scandir(os.path.join(folder, rel)) as listing:
                entries = sorted(listing, key=lambda e: e.name)
        except OSError:
            return
        dirs = [e for e in entries if e.is_dir(follow_symlinks=False)]
        out.extend((f"{rel}{e.name}", store.stamp(e)) for e in entries if e.name.endswith(".txt") and e not in dirs)
        for e in dirs:
            walk(f"{rel}{e.name}/")
    walk("")
    return tuple(out)


def parse(text, where):
    names, out = None, {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.lower().startswith(PLACEHOLDERS):
            given = line[len(PLACEHOLDERS):].strip()
            names = set() if given.lower() == "none" else {x.strip() for x in given.split(",") if x.strip()}
            continue
        if not line or line.startswith("#"):
            continue
        key, eq, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not eq or not KEY.match(key):
            raise WordsError(f"{where}:{n}: a line is key = text, the key in small letters, digits, dots and dashes")
        if key in out:
            raise WordsError(f"{where}:{n}: {key} is given twice")
        if not value:
            raise WordsError(f"{where}:{n}: {key} has no text")
        if not value.isascii():
            raise WordsError(f"{where}:{n}: {key} holds a letter outside plain ASCII, which the add-on can't read")
        if names is None:
            raise WordsError(f"{where}:{n}: the file names its placeholders first (# placeholders: none)")
        unknown = set(NAME.findall(value)) - names
        if unknown:
            raise WordsError(f"{where}:{n}: {key} uses {', '.join(sorted(unknown))}, which the file's placeholders lack")
        out[key] = value
    return out


def table(folder=FOLDER):
    folder = os.path.abspath(folder)
    stamps = files(folder)
    hit = _kept.get(folder)
    if hit and hit[0] == stamps:
        return hit[1]
    out = {}
    for rel, _ in stamps:
        with open(os.path.join(folder, rel), encoding="utf-8") as f:
            lines = lines_of(rel, f.read())
        for k, v in lines.items():
            if k in out:
                raise WordsError(f"{rel}: {k} is given in another file too")
            out[k] = v
    read = MappingProxyType(out)
    _kept[folder] = (stamps, read)
    return read


def lines_of(rel, text):
    top = rel.split("/")[0]
    if top not in SIDES or "/" not in rel:
        raise WordsError(f"{rel}: a words file sits in one of the top folders {', '.join(SIDES)}")
    lines = parse(text, rel)
    prefix = rel[:-len(".txt")].replace("/", ".")
    if not KEY.match(prefix):
        raise WordsError(f"{rel}: folder and file names are small letters, digits and dashes")
    return {f"{prefix}.{k}": v for k, v in lines.items()}


def side(key):
    return SIDES[key.split(".")[0]]


def say(key, values=None, folder=FOLDER):
    return fill(table(folder).get(key), values)


def fill(text, values=None):
    if text is None:
        return None
    values = values or {}
    if any(values.get(name) in (None, "") for name in NAME.findall(text)):
        return None

    def said(v):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    return NAME.sub(lambda m: said(values[m.group(1)]), text)
