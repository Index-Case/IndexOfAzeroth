# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os
import re
import shutil
import threading
import time

import game
from serverlog import start_thread
import store

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "addons.json")
CHECK_EVERY = 6 * 3600
TICK = 30
KEEP_OLD = 5
SKIP_COPY = re.compile(r"^(ForeverSVFix.*|\.git.*|__pycache__|Pending\.lua|Shared\.lua)$", re.I)


MANAGED = [
    {"key": "indexofazeroth", "label": "IndexOfAzeroth", "folders": ["IndexOfAzeroth"], "local": True},
]
BY_KEY = {a["key"]: a for a in MANAGED}



def is_link(path):
    return os.path.islink(path) or os.path.isjunction(path)


def client_interface():
    try:
        major, minor, patch_ = (int(v) for v in game.played_version().split(".")[:3])
        return str(major * 10000 + minor * 100 + patch_)
    except Exception:
        return None


def toc_version(folder):
    name = os.path.basename(folder)
    try:
        tocs = [f for f in os.listdir(folder) if f.lower().endswith(".toc") and
                (f.lower() == f"{name}.toc".lower() or f.lower().startswith((f"{name}_".lower(), f"{name}-".lower())))]
    except OSError:
        return None
    if not tocs:
        return None
    heads = {}
    for f in tocs:
        try:
            with open(os.path.join(folder, f), encoding="utf-8-sig", errors="replace") as fh:
                heads[f] = [l.strip() for l in fh if l.startswith("##")]
        except OSError:
            heads[f] = []
    want = client_interface()
    fits = [f for f in tocs if want and any(l.startswith("## Interface:") and want in l.replace(" ", "").split(":", 1)[1].split(",")
                                           for l in heads[f])]
    plain = [f for f in tocs if f.lower() == f"{name}.toc".lower()]
    pick = (fits or plain or sorted(tocs))[0]
    return next((l.split(":", 1)[1].strip() for l in heads[pick] if l.startswith("## Version")), "") or "?"


def walk_files(top):
    out = []
    stack = [""]
    while stack:
        rel = stack.pop()
        with os.scandir(os.path.join(top, rel)) as it:
            for e in it:
                sub = os.path.join(rel, e.name)
                if is_link(e.path):
                    continue
                if e.is_dir():
                    stack.append(sub)
                else:
                    out.append(sub)
    return out


def unlink_links(top):
    removed = []
    stack = [top]
    while stack:
        folder = stack.pop()
        with os.scandir(folder) as it:
            entries = list(it)
        for e in entries:
            if is_link(e.path):
                removed.append((e.path, os.readlink(e.path)))
                os.rmdir(e.path) if os.path.isdir(e.path) else os.unlink(e.path)
            elif e.is_dir():
                stack.append(e.path)
    return removed


def safe_rmtree(top):
    unlink_links(top)
    shutil.rmtree(top)


def fresh_folder(path):
    n = 1
    while True:
        at = path if n == 1 else f"{path}-{n}"
        try:
            os.makedirs(at)
            return at
        except FileExistsError:
            n += 1


def tree_hash(folder):
    h = hashlib.sha1()
    for rel in sorted(walk_files(folder)):
        if SKIP_COPY.match(rel.split(os.sep)[0]) or rel.endswith(".toc"):
            continue
        h.update(rel.lower().encode())
        with open(os.path.join(folder, rel), "rb") as f:
            h.update(hashlib.sha1(f.read()).digest())
    return h.hexdigest()[:12]



class NoSite:

    def check(self, manager):
        pass

    def step(self, manager, a, e, running, missing_part):
        if e.get("linked"):
            e.update(status="linked", message=f"Linked to {e['linked']}, so the Index leaves the addon alone")
        elif e["installed"] is None:
            e.update(status="unknown", message="Not installed yet. The Index has no release of it to install")
        else:
            e.update(status="ok", message="Installed")
        return False


class AddonState:

    def __init__(self, hub):
        self.hub = hub
        self.lock = threading.Lock()
        self.state = self.load()
        self.folder = None
        self.last_check = 0

    def load(self):
        return {}

    def entry(self, key):
        return self.state.setdefault(key, {})

    def publish(self):
        running = game.running()
        rows = []
        for a in MANAGED:
            e = self.state.get(a["key"], {})
            rows.append({"key": a["key"], "label": a["label"], "folder": a["folders"][0], "url": a.get("url"), **{k: e.get(k) for k in (
                "installed", "latest", "latestName", "status", "message", "checked", "changed", "restart", "linked", "error")}})
        self.hub.publish(addons={"list": rows, "running": running, "at": round(time.time())},
                         game={"folder": self.folder})


    def watch(self):
        while True:
            self.run_check(force_check=time.time() - self.last_check > CHECK_EVERY)
            time.sleep(TICK)

    def check_now(self):
        return start_thread("addon check", self.run_check, kwargs={"force_check": True})

    def run_check(self, force_check=False):
        try:
            self.tick(force_check=force_check)
        except Exception as e:
            self.note_all_error(f"The addon check failed: {e}")

    def note_all_error(self, message):
        for a in MANAGED:
            self.entry(a["key"])["error"] = message[:200]
        self.publish()

    def found_folder(self):
        try:
            self.folder = game.folder()
            return True
        except game.GameNotFound as e:
            self.folder = None
            for a in MANAGED:
                self.entry(a["key"]).update(status="nogame", message=str(e))
            self.publish()
            return False

    def read(self, a, addons):
        e = self.entry(a["key"])
        main = os.path.join(addons, a["folders"][0])
        was, e["installed"] = e.get("installed"), toc_version(main)
        if was and e["installed"] and was != e["installed"]:
            e["changed"] = round(time.time())
        e["linked"] = os.readlink(main).removeprefix("\\\\?\\") if is_link(main) else None
        return e, main

    def tick(self, force_check=False):
        with self.lock:
            if not self.found_folder():
                return
            addons = game.addons_dir()
            for a in MANAGED:
                e, _ = self.read(a, addons)
                e.update(status="ok" if e["installed"] else "unknown", message=None)
            self.publish()


class AddonManager(AddonState):

    def __init__(self, hub, after_install=None, site=None):
        super().__init__(hub)
        self.after_install = after_install
        self.site = site or NoSite()

    def load(self):
        return store.load_json(STATE, {})

    def save(self):
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        store.save_json(STATE, self.state)

    def tick(self, force_check=False):
        if force_check and self.lock.locked():
            return
        with self.lock:
            if not self.found_folder():
                return
            if force_check:
                self.last_check = time.time()
                self.check_latest()
                for a in MANAGED:
                    self.entry(a["key"]).pop("failedFile", None)
            installed_any = False
            for a in MANAGED:
                installed_any |= self.step(a)
            self.save()
            self.publish()
        if installed_any and self.after_install:
            self.after_install()

    def check_latest(self):
        for a in MANAGED:
            self.entry(a["key"])["checked"] = round(time.time())
        self.site.check(self)

    def step(self, a):
        addons = game.game_addons_dir()
        e, main = self.read(a, addons)
        missing_part = e["installed"] and any(toc_version(os.path.join(addons, f)) is None for f in a["folders"][1:])
        running = game.running()
        if not running:
            e["restart"] = False
        if a.get("local"):
            return self.step_local(a, e, main, running)
        return self.site.step(self, a, e, running, missing_part)

    def step_local(self, a, e, main, running):
        source = self.local_source(main)
        if not source:
            e.update(status="error", message="IndexOfAzeroth's source folder wasn't found")
            return False
        e["latestName"] = f"{toc_version(source) or '?'} from {source}"
        if not os.path.exists(main):
            os.makedirs(os.path.dirname(main), exist_ok=True)
            import _winapi
            _winapi.CreateJunction(source, main)
            e.update(status="installed", message="Linked in", restart=running, changed=round(time.time()))
            return True
        if e.get("linked"):
            e.update(status="ok", message=f"Linked to {e['linked']}, so your edits reach the game with a /reload", restart=False)
            return False
        if tree_hash(main) == tree_hash(source):
            e.update(status="ok", message="The installed copy is the same as the source")
            return False
        if running:
            e.update(status="waiting", message="A newer copy installs when you exit the game")
            return False
        return self.replace(a, e, lambda staged: copy_tree(source, os.path.join(staged, a["folders"][0])), "updated", running)

    def local_source(self, main):
        if is_link(main):
            target = os.readlink(main).removeprefix("\\\\?\\")
            if os.path.isdir(target):
                return target
        for folder in (game.load_config().get("indexOfAzerothSource"), game.ADDON_HELD):
            if folder and os.path.isfile(os.path.join(folder, "IndexOfAzeroth.toc")):
                return folder
        return None


    def replace(self, a, e, fill, verb, running):
        addons = game.game_addons_dir()
        base = os.path.join(game.folder(), "WCC")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        staged = fresh_folder(os.path.join(base, "staging", f"{a['key']}-{stamp}"))
        try:
            fill(staged)
            folders = sorted(n for n in os.listdir(staged) if os.path.isdir(os.path.join(staged, n)))
            for name in folders:
                target = os.path.join(addons, name)
                if is_link(target):
                    raise ValueError(f"{name} is a link to {os.readlink(target)}, so the Index won't replace it")
            if running and any(os.path.exists(os.path.join(addons, n)) for n in folders):
                raise ValueError("the game is running")
            moved, old = [], None
            try:
                for name in folders:
                    target = os.path.join(addons, name)
                    if os.path.exists(target):
                        old = old or fresh_folder(os.path.join(base, "old", f"{stamp}-{a['key']}"))
                        backup_settings(name, os.path.join(old, "settings"))
                        unlink_links(target)
                        os.rename(target, os.path.join(old, name))
                        moved.append(name)
                    os.rename(os.path.join(staged, name), target)
            except OSError:
                for name in moved:
                    target = os.path.join(addons, name)
                    if os.path.exists(target):
                        os.rename(target, os.path.join(staged, name))
                    os.rename(os.path.join(old, name), target)
                raise
            prune(os.path.join(base, "old"))
        except Exception as ex:
            e.update(status="error", message=f"{verb.capitalize()} failed: {ex}"[:200])
            return False
        finally:
            if os.path.isdir(staged):
                safe_rmtree(staged)
        e.update(status=verb, installed=toc_version(os.path.join(addons, a["folders"][0])), restart=running,
                 changed=round(time.time()),
                 message=(f"{verb.capitalize()}. Restart the game to load the addon" if running else f"{verb.capitalize()}. The addon loads the next time you start the game"))
        return True


def copy_tree(source, dest):
    for rel in walk_files(source):
        if SKIP_COPY.match(rel.split(os.sep)[0]):
            continue
        os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
        shutil.copy2(os.path.join(source, rel), os.path.join(dest, rel))


def backup_settings(addon, dest):
    wtf = game.wtf_dir()
    patterns = [os.path.join(wtf, "Account", "*", "SavedVariables", f"{addon}.lua*"),
                os.path.join(wtf, "Account", "*", "*", "*", "SavedVariables", f"{addon}.lua*")]
    import glob
    for pattern in patterns:
        for path in glob.glob(pattern):
            rel = os.path.relpath(path, wtf)
            os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
            shutil.copy2(path, os.path.join(dest, rel))


def prune(old_root):
    try:
        stashes = sorted(os.listdir(old_root))
    except OSError:
        return
    for name in stashes[:-KEEP_OLD]:
        safe_rmtree(os.path.join(old_root, name))
