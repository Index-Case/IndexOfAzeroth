# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = "DGG_MAINDATA"
SHIPS, PLAYER, HERE = "ships", "player", "here"
IN_RELEASE = {
    "icons": PLAYER, "icons_fallback": SHIPS, "icons_fallback.json": SHIPS, "iconcache": HERE,
    "worldmapcache": SHIPS, "mapcache": SHIPS, "tilecache": SHIPS, "highlightcache": SHIPS,
    "cardcache": SHIPS, "uicache": PLAYER, "paperup": SHIPS,
    "fogmasks": SHIPS,
    "rendertiles": SHIPS, "detailview": SHIPS, "heights": SHIPS, "trees": SHIPS,
    "seafield": SHIPS, "seamask": SHIPS, "inlandfield": SHIPS,
    "indoorcache": PLAYER, "dungeonmaps": SHIPS, "dungeonmaps.json": SHIPS,
    "dungeonbake": SHIPS, "dungeonbake.json": SHIPS,
    "tooltips": PLAYER, "tooltips.json": PLAYER, "tooltips_fallback.json": SHIPS, "shield_block.json": SHIPS,
    "navcache": PLAYER, "navpack": SHIPS,
    "buildcache": PLAYER,
    "buildcache/listfile-wmo.csv": SHIPS, "buildcache/listfile-terrain.csv": SHIPS,
    "buildcache/listfile-ui-14232c66.csv": SHIPS, "buildcache/shield_block_filled.json": SHIPS,
    "buildcache/listfile-db2.csv": HERE, "buildcache/listfile-m2.csv": HERE, "buildcache/listfile-treetextures.csv": HERE,
    "buildcache/listfile-crests.csv": HERE, "buildcache/fishing_tiles.json": HERE, "buildcache/prompt-rules.json": HERE,
    "tabledefs": SHIPS,
    "sources": HERE, "patches.json": HERE, "tooltips-stale": HERE,
    "game.json": PLAYER,
    "trainerprices.json": PLAYER,
}
STORES = frozenset(IN_RELEASE)
_main = []


def how(rel):
    parts = rel.replace("\\", "/").strip("/").split("/")
    owner = next((name for name in ("/".join(parts[:n]) for n in range(len(parts), 0, -1)) if name in IN_RELEASE),
                 None)
    return IN_RELEASE.get(owner)


def _key(path):
    return os.path.normcase(os.path.realpath(path))


def main_data(env=None, root=None):
    if env is None and root is None and _main:
        return _main[0]
    import game
    base = (os.environ if env is None else env).get(ENV) or None
    own = os.path.join(root or ROOT, "data")
    out = None if not base or game.writes_game(root) or _key(base) == _key(own) else os.path.abspath(base)
    if env is None and root is None:
        _main[:] = [out]
    return out


def path(name, env=None, root=None):
    if name not in STORES:
        raise KeyError(f"{name} isn't one of main's stores")
    base = main_data(env, root)
    return os.path.join(base, name) if base else own(name, root)


def own(name, root=None):
    return os.path.join(root or ROOT, "data", name)


def find(name, *parts, env=None, root=None):
    return standing(os.path.join(own(name, root), *parts), env, root)


def under(where, env=None, root=None):
    base = main_data(env, root)
    if not base:
        return None
    try:
        rel = os.path.relpath(os.path.abspath(where), os.path.join(root or ROOT, "data"))
    except ValueError:
        return None
    parts = rel.split(os.sep)
    if parts[0] in (os.pardir, os.curdir) or os.path.normcase(parts[0]) not in STORES:
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


def in_main(where, env=None, root=None):
    base = main_data(env, root)
    if not base:
        return False
    top, it = _key(base), _key(where)
    return it == top or it.startswith(top.rstrip(os.sep) + os.sep)


def refuse_write(where, env=None, root=None):
    if in_main(where, env, root):
        raise PermissionError(f"{where}: main's stores are read only from a worktree ({ENV})")
