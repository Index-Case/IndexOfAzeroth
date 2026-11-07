# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

FOLDER = "IndexOfAzeroth"
INDEX = "Index"
START = "Start the Index.bat"
UNINSTALL = "Uninstall the Index.bat"
STEPS = "README.txt"
TOP = (START, UNINSTALL, STEPS)
SERVER_WRITTEN = ("Pending.lua", "Shared.lua")


def at(place):
    return place if place in TOP else f"{INDEX}/{place}"


def place(path):
    p = path.replace("\\", "/")
    if p in TOP:
        return p
    folder, _, rest = p.partition("/")
    return rest if folder == INDEX and rest and rest not in TOP else None


def install_of(program):
    return os.path.dirname(os.path.abspath(program))
