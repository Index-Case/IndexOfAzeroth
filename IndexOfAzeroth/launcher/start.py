# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import http.server
import json
import os
import re
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
for _p in (HERE, INSTALL):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import appwindow
import updatenews
import updater
import words

PORT = 8766
ADDON = "IndexOfAzeroth"
RETRY = 30.0
POLL = 5.0
GONE = 20.0
FIRST_ASK = 120.0
SHOW = 3.0
MB = 1 << 20
AUTO = 200 * MB
CHECK = 3600.0
PAGE = os.path.join(HERE, "page.html")
WEB = os.path.join(INSTALL, "web")
KINDS = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".webp": "image/webp",
         ".woff2": "font/woff2"}


def by_itself(size):
    return size <= AUTO


class WindowClosed(Exception):
    pass


class Launch:

    def __init__(self, install=INSTALL, get=updater.http_get, game=None, start=None, answer=None, sleep=time.sleep,
                 public_key=updater.PUBLIC_KEY, port_free=None):
        self.install, self.get, self.sleep, self.public_key = install, get, sleep, public_key
        self.game = game
        self.start = start or (lambda: appwindow.start_server(PORT))
        self.answer = answer or (lambda: appwindow.answers(PORT, 1))
        self.port_free = port_free or (lambda: appwindow.take_port(PORT) == "free")
        self.ready = None
        self.offered = None
        self.declined = None
        self.lock = threading.Lock()
        self.done = self.total = 0
        self.say("page.launcher.checking")
        self.choice, self.chosen = None, threading.Event()
        self.addon_waits = False
        self.news = None
        self.news_seen = False
        self.clock = time.monotonic
        self.began, self.seen_at = self.clock(), None

    def window_gone(self):
        now = self.clock()
        return now - self.seen_at > GONE if self.seen_at is not None else now - self.began > FIRST_ASK

    def still_open(self):
        if self.window_gone():
            raise WindowClosed()


    def say(self, key, **values):
        with self.lock:
            self.phase, self.values = key, values

    def state(self):
        with self.lock:
            self.seen_at = self.clock()
            line = words.say(self.phase, self.values) or ""
            out = {"phase": self.phase.rsplit(".", 1)[-1], "line": line, "done": self.done, "total": self.total,
                   "title": words.say("page.launcher.title")}
            if self.phase == "page.launcher.updated":
                out.update(size=words.say("page.launcher.update-size", self.values), update=words.say("page.launcher.update"),
                           later=words.say("page.launcher.later"), changes=self.values.get("changes", ""))
            elif self.news:
                out.update(news=words.say("page.launcher.updated", self.news), changes=self.news["changes"])
                self.news_seen = True
            return out

    def choose(self, choice):
        if choice in ("update", "later"):
            self.choice = choice
            self.chosen.set()


    def newest(self):
        while True:
            try:
                return updater.fetch_manifest(self.get, self.public_key)
            except (OSError, updater.UpdateRefused) as e:
                if updater.installed_manifest(self.install, self.public_key):
                    return None
                self.cannot(e)

    def cannot(self, why):
        if isinstance(why, updater.UpdateRefused):
            self.say("page.launcher.refused")
        else:
            self.say("page.launcher.offline")
        self.wait(RETRY)

    def wait(self, seconds):
        for _ in range(int(seconds)):
            self.still_open()
            self.sleep(1)

    def download(self, manifest, tell=None):
        todo = updater.needed(self.install, manifest, self.public_key)
        with self.lock:
            self.done, self.total = 0, updater.Manifest.total_size(todo)
        before = 0
        for pack in todo:
            def progress(got, _size, base=before):
                with self.lock:
                    was = self.done // MB
                    self.done = base + got
                    self.values = {"done": self.done // MB, "total": self.total // MB}
                if tell and self.done // MB != was:
                    tell(self.done // MB, self.total // MB)
            if tell:
                tell(before // MB, self.total // MB)
            else:
                self.still_open()
                self.say("page.launcher.installing", done=before // MB, total=self.total // MB)
            updater.download_pack(pack, self.install, self.get, progress)
            before += pack.size

    def running(self):
        return self.load_game().running()

    def put_in(self, manifest, first):
        while True:
            try:
                updater.apply_update(self.install, manifest, (lambda: False) if first else self.running, self.public_key)
                return True
            except updater.GameRunning:
                self.say("page.launcher.wait-game")
                if self.chosen_within(POLL) == "later":
                    return False

    def chosen_within(self, seconds=None):
        end = None if seconds is None else self.clock() + seconds
        while not self.chosen.wait(1):
            self.still_open()
            if end is not None and self.clock() >= end:
                return None
        self.chosen.clear()
        return self.choice

    def update(self):
        while True:
            manifest = self.newest()
            installed = updater.installed_manifest(self.install, self.public_key)
            if not manifest or (installed and installed.version == manifest.version):
                return False
            alone = False
            if installed:
                size = self.size(manifest)
                alone = by_itself(size)
                if not alone:
                    self.say("page.launcher.updated", version=manifest.version, size=max(1, round(size / MB)),
                             changes=manifest.changes)
                    if self.chosen_within() != "update":
                        self.declined = manifest.version
                        return False
            try:
                self.download(manifest)
            except (OSError, updater.UpdateRefused) as e:
                if installed:
                    return False
                self.cannot(e)
                continue
            if not alone:
                return self.put_in(manifest, first=installed is None)
            try:
                updater.apply_update(self.install, manifest, self.running, self.public_key)
            except updater.GameRunning:
                return False
            with self.lock:
                self.news = {"version": manifest.version, "changes": manifest.changes}
            self.say("page.launcher.starting")
            return True

    def size(self, manifest):
        return updater.Manifest.total_size(updater.needed(self.install, manifest, self.public_key))

    def load_game(self):
        if self.game is None:
            import game
            self.game = game
        return self.game

    def client(self):
        game = self.load_game()
        while True:
            if game.client_in(game.load_config().get("folder")):
                return
            found = game.clients()
            running = {game.norm(f) for f in game.running_folders() if f}
            pick = found if len(found) == 1 else [c for c in found if game.norm(c["folder"]) in running]
            if len(pick) == 1:
                game.install(pick[0]["folder"])
                game.storewriter.flush_later()
                return
            if found:
                self.say("page.launcher.several")
            else:
                self.say("page.launcher.no-client")
            self.wait(POLL)
            game.forget()

    def addon(self):
        if self.running():
            return False
        held = os.path.join(self.install, "addon", ADDON)
        if not os.path.isdir(held):
            return True
        put_addon(held, os.path.join(self.load_game().game_addons_dir(), ADDON))
        return True

    def serve(self):
        for attempt in range(2):
            self.say("page.launcher.starting")
            self.start()
            for _ in range(int(appwindow.START)):
                if self.answer():
                    updater.confirm_update(self.install)
                    return True
                self.sleep(1)
            if not updater.rollback_update(self.install):
                break
            with self.lock:
                self.news = None
        return False

    def news_shown(self):
        end = self.clock() + SHOW
        while self.news and not self.news_seen and self.clock() < end:
            self.sleep(0.1)

    def run(self, page=None):
        updater.recover(self.install)
        updatenews.clear(self.install)
        try:
            self.update()
            self.client()
        except WindowClosed:
            return False
        if page:
            self.news_shown()
            page.shutdown()
            page.server_close()
        if not self.serve():
            self.say("page.launcher.failed")
            if page:
                again = page_server(self, page.server_address[1])
                threading.Thread(target=again.serve_forever, daemon=True, name="launcher page").start()
                self.seen_at = None
                self.began = self.clock()
                while not self.window_gone():
                    self.sleep(1)
            return False
        self.addon_waits = not self.addon()
        return True


    def serving(self, last):
        if self.answer():
            last[0] = self.clock()
        return self.clock() - last[0] < GONE

    def watch(self):
        due, last = self.clock(), [self.clock()]
        while self.serving(last):
            if self.addon_waits:
                self.addon_waits = not self.addon()
            if self.ready:
                if not self.running():
                    self.put_in_running(*self.ready)
                    last[0] = self.clock()
            elif self.offered:
                self.answered()
            elif self.clock() >= due:
                due = self.clock() + CHECK
                self.look()
            self.sleep(POLL)

    def look(self):
        try:
            manifest = updater.fetch_manifest(self.get, self.public_key)
        except (OSError, updater.UpdateRefused):
            return
        installed = updater.installed_manifest(self.install, self.public_key)
        if not installed or manifest.version in (installed.version, self.declined):
            return
        size = self.size(manifest)
        if by_itself(size):
            self.fetch(manifest, told=False)
            return
        self.offered = manifest
        updatenews.chosen(self.install)
        updatenews.tell(self.install, {"step": "offer", "version": manifest.version, "size": max(1, round(size / MB)),
                                       "changes": manifest.changes})

    def answered(self):
        choice = updatenews.chosen(self.install)
        if choice is None:
            return
        manifest, self.offered = self.offered, None
        if choice == "update":
            self.fetch(manifest, told=True)
        else:
            self.declined = manifest.version
            updatenews.tell(self.install, None)

    def fetch(self, manifest, told):
        def progress(done, total):
            updatenews.tell(self.install, {"step": "downloading", "version": manifest.version, "done": done, "total": total})
        try:
            self.download(manifest, progress if told else (lambda done, total: None))
        except (OSError, updater.UpdateRefused):
            if told:
                updatenews.tell(self.install, None)
            return
        self.ready = (manifest, told)
        if told:
            updatenews.tell(self.install, {"step": "waiting", "version": manifest.version})

    def put_in_running(self, manifest, told):
        updatenews.ask_stop(self.install)
        while self.answer():
            self.sleep(1)
        for _ in range(int(appwindow.START)):
            if self.port_free():
                break
            self.sleep(1)
        updatenews.clear(self.install)
        self.ready = None
        try:
            updater.apply_update(self.install, manifest, self.running, self.public_key)
        except updater.GameRunning:
            self.ready = (manifest, told)
        except (OSError, updater.UpdateRefused):
            updater.rollback_update(self.install)
            self.declined = manifest.version
        self.serve()
        installed = updater.installed_manifest(self.install, self.public_key)
        if self.ready and told:
            updatenews.tell(self.install, {"step": "waiting", "version": manifest.version})
        elif not self.ready and (not installed or installed.version != manifest.version):
            self.declined = manifest.version
        self.addon_waits = not self.addon()


def toc_version(folder):
    try:
        with open(os.path.join(folder, ADDON + ".toc"), encoding="utf-8-sig") as f:
            for line in f:
                if line.lower().startswith("## version:"):
                    return updater.version_key(line.split(":", 1)[1])
    except OSError:
        pass
    return ()


def put_addon(held, target):
    if toc_version(target) > toc_version(held):
        return "newer"
    for top, _, files in os.walk(held):
        for name in files:
            src = os.path.join(top, name)
            dst = os.path.join(target, os.path.relpath(src, held))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "rb") as f, open(dst, "wb") as out:
                shutil.copyfileobj(f, out)
    return "put"


def page_files(page=PAGE):
    with open(page, encoding="utf-8") as f:
        return sorted(set(re.findall(r'(?:src|href)="([\w./-]+)"', f.read())))


def page_server(launch, port=PORT, page=PAGE, web=WEB):
    files = set(page_files(page))

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                with open(page, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            elif self.path == "/launcher/state":
                self.send(200, json.dumps(launch.state()).encode("utf-8"), "application/json")
            elif self.path[1:] in files and os.path.isfile(os.path.join(web, self.path[1:])):
                with open(os.path.join(web, self.path[1:]), "rb") as f:
                    self.send(200, f.read(), KINDS.get(os.path.splitext(self.path)[1], "application/octet-stream"))
            else:
                self.send(404, b"", "text/plain")

        def do_POST(self):
            if self.path != "/launcher/choice":
                return self.send(404, b"", "text/plain")
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1024)) or b"{}")
            except ValueError:
                body = {}
            launch.choose(body.get("choice") if isinstance(body, dict) else None)
            self.send(204, b"", "text/plain")

    return http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)


def say_alone(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, words.say("page.launcher.title"), 0x40)
    except (OSError, AttributeError):
        print(text)


def main():
    got = appwindow.take_port(PORT)
    if got == "up":
        appwindow.open_window(appwindow.page_url(PORT))
        return 0
    if got == "held":
        say_alone(words.say("page.launcher.port"))
        return 1
    launch = Launch()
    page = page_server(launch)
    threading.Thread(target=page.serve_forever, daemon=True, name="launcher page").start()
    appwindow.open_window(appwindow.page_url(PORT))
    if not launch.run(page):
        return 1
    launch.watch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
