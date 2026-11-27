# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

import mainstores

ROOT = os.path.dirname(os.path.abspath(__file__))
STORES = frozenset({"auction", "replay", "characters.json"})


def under(where, env=None, root=None):
    base = mainstores.main_data(env, root)
    if not base:
        return None
    try:
        rel = os.path.relpath(os.path.abspath(where), os.path.join(root or ROOT, "data"))
    except ValueError:
        return None
    first = rel.split(os.sep)[0]
    if first in (os.pardir, os.curdir) or os.path.normcase(first) not in STORES:
        return None
    return os.path.join(base, rel)


def standing(where, env=None, root=None):
    if os.path.exists(where):
        return where
    return under(where, env, root) or where


def listing(folder, env=None, root=None):
    out = {}
    for at in (folder, under(folder, env, root)):
        try:
            names = os.listdir(at) if at else ()
        except OSError:
            names = ()
        for name in names:
            out.setdefault(name, os.path.join(at, name))
    return out
