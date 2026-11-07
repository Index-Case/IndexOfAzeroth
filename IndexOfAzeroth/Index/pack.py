# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import shutil
import threading
import time
import zipfile

from serverlog import start_thread

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
MINE = {"game.json", "addons.json", "server.log", "server.log.old", "server.stuck.log", "rebuild.log", "rebuild.log.old",
        "traffic.log", "traffic.log.old", "reloads.json"}
STAGE = ".import"


def passing(name):
    return name.endswith((".part", ".lock")) or ".part." in name or ".unreadable-" in name


def kept_out(rel):
    parts = rel.split("/")
    return parts[0] == STAGE or (len(parts) == 1 and parts[0] in MINE) or passing(parts[-1])


def packed_files():
    for folder, dirs, files in os.walk(DATA):
        rel = os.path.relpath(folder, DATA)
        if rel == ".":
            dirs[:] = [d for d in dirs if d != STAGE]
        for f in files:
            path = os.path.join(folder, f)
            name = os.path.relpath(path, DATA).replace(os.sep, "/")
            if not kept_out(name):
                yield path, name


def apply_staged():
    stage = os.path.join(DATA, STAGE)
    if not os.path.isdir(stage):
        return None
    applied, failed = 0, []
    for folder, dirs, files in os.walk(stage):
        for f in files:
            src = os.path.join(folder, f)
            rel = os.path.relpath(src, stage)
            if passing(f):
                os.remove(src)
                continue
            try:
                os.makedirs(os.path.dirname(os.path.join(DATA, rel)), exist_ok=True)
                os.replace(src, os.path.join(DATA, rel))
                applied += 1
            except OSError:
                failed.append(rel.replace(os.sep, "/"))
    for folder, dirs, files in sorted(os.walk(stage), key=lambda w: -len(w[0])):
        if not os.listdir(folder):
            os.rmdir(folder)
    return {"applied": applied, "failed": failed}


class Pack:
    def __init__(self, applied=None, log=None):
        self.state = {"state": "idle"}
        if applied and applied["failed"]:
            names = ", ".join(applied["failed"][:5]) + (" and more" if len(applied["failed"]) > 5 else "")
            self.state = {"state": "failed", "message": f"{len(applied['failed'])} of the imported files couldn't be put in "
                                                        f"place ({names}). The Index tries them again at the next start"}
        self.lock = threading.Lock()
        self.log = log

    def snapshot(self):
        return dict(self.state)

    def _run(self, state, job, *args):
        if not self.lock.acquire(blocking=False):
            return False
        self.state = {"state": state, "done": 0, "total": 0}

        def work():
            try:
                job(*args)
            except (OSError, zipfile.BadZipFile) as e:
                self.state = {"state": "failed", "message": str(e)}
            except Exception as e:
                self.state = {"state": "failed", "message": f"{type(e).__name__}: {e}"}
                if self.log:
                    self.log(f"the pack's {state}")
            finally:
                self.lock.release()
        start_thread(f"pack {state}", work)
        return True

    def export(self, folder=None):
        folder = folder or os.path.join(os.path.expanduser("~"), "Downloads")
        return self._run("exporting", self._export, folder)

    def _export(self, folder):
        files = list(packed_files())
        total = sum(os.path.getsize(p) for p, _ in files)
        target = os.path.join(folder, f"IndexOfAzeroth-data-{time.strftime('%Y-%m-%d')}.zip")
        done = 0
        self.state = {"state": "exporting", "done": 0, "total": total, "path": target}
        os.makedirs(folder, exist_ok=True)
        with zipfile.ZipFile(target + ".part", "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for path, name in files:
                try:
                    z.write(path, name)
                except OSError:
                    continue
                done += os.path.getsize(path)
                self.state["done"] = done
        os.replace(target + ".part", target)
        self.state = {"state": "exported", "path": target, "files": len(files), "total": total}

    def import_(self, path):
        return self._run("importing", self._import, path)

    def _import(self, path):
        stage = os.path.join(DATA, STAGE)
        with zipfile.ZipFile(path) as z:
            members = [m for m in z.infolist() if not m.is_dir()]
            total = sum(m.file_size for m in members)
            done, kept, staged, failed = 0, 0, 0, []
            self.state = {"state": "importing", "done": 0, "total": total, "path": path}
            for m in members:
                done += m.file_size
                self.state["done"] = done
                target = os.path.normpath(os.path.join(DATA, m.filename))
                if not target.startswith(DATA + os.sep) or kept_out(os.path.relpath(target, DATA).replace(os.sep, "/")):
                    continue
                when = time.mktime(m.date_time + (0, 0, -1))
                if os.path.exists(target) and os.path.getmtime(target) > when + 2:
                    kept += 1
                    continue
                into = os.path.join(stage, os.path.relpath(target, DATA))
                try:
                    os.makedirs(os.path.dirname(into), exist_ok=True)
                    with z.open(m) as src, open(into + ".part", "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
                    os.replace(into + ".part", into)
                    os.utime(into, (when, when))
                    staged += 1
                except (OSError, zipfile.BadZipFile, ValueError):
                    failed.append(m.filename)
        if failed:
            names = ", ".join(failed[:5]) + (" and more" if len(failed) > 5 else "")
            self.state = {"state": "failed", "path": path, "files": staged, "kept": kept,
                          "message": f"{len(failed)} files of the pack couldn't be read ({names}). The other {staged} come in "
                                     f"when you restart the Index"}
        else:
            self.state = {"state": "imported", "path": path, "files": staged, "kept": kept}
