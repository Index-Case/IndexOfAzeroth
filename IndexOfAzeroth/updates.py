# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import threading
import time

import updatenews
from serverlog import start_thread

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
LOOK_EVERY = 5.0
SLACK = 2.0
NOT_ADDON = {"pending.lua", "shared.lua"}


def page_version(root=ROOT):
    git = os.path.join(root, ".git")
    try:
        if os.path.isfile(git):
            with open(git, encoding="utf-8") as f:
                git = f.read().split("gitdir:", 1)[1].strip()
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref, common = head[5:], git
        if os.path.isfile(os.path.join(git, "commondir")):
            with open(os.path.join(git, "commondir"), encoding="utf-8") as f:
                common = os.path.normpath(os.path.join(git, f.read().strip()))
        for base in (git, common):
            if os.path.isfile(os.path.join(base, ref)):
                with open(os.path.join(base, ref), encoding="utf-8") as f:
                    return f.read().strip()[:7]
        with open(os.path.join(common, "packed-refs"), encoding="utf-8") as f:
            for line in f:
                if line.strip().endswith(" " + ref):
                    return line.split()[0][:7]
    except (OSError, IndexError):
        pass
    return ""


def newest(folder, pick):
    try:
        return max((e.stat().st_mtime for e in os.scandir(folder) if e.is_file() and pick(e.name.lower())), default=0.0)
    except OSError:
        return 0.0


class Updates:
    def __init__(self, hub, addon_folder, log=None, version="", stop=None, root=ROOT):
        self.hub = hub
        self.addon_folder = addon_folder
        self.loaded_at = None
        self.wake = threading.Event()
        self.log = log
        self.version = version
        self.stop, self.root = stop, root

    def note_status(self, nums):
        seconds = nums.get("sessionSeconds")
        if seconds:
            at = time.time() - seconds
            if self.loaded_at is None or abs(at - self.loaded_at) > SLACK:
                self.loaded_at = at
                self.wake.set()

    def look(self):
        out = {"web": round(newest(WEB, lambda n: n.endswith((".js", ".css", ".html")))), "addon": None}
        folder = self.addon_folder()
        if folder and self.loaded_at:
            since = self.loaded_at + SLACK
            if newest(folder, lambda n: n.endswith(".toc")) > since:
                out["addon"] = "restart"
            elif newest(folder, lambda n: n.endswith((".lua", ".xml")) and n not in NOT_ADDON) > since:
                out["addon"] = "reload"
        if self.version:
            if self.stop and updatenews.stop_asked(self.root):
                start_thread("update stop", self.stop)
            out["index"] = {"version": self.version, "news": updatenews.news(self.root)}
        return out

    def watch(self):
        last = None
        while True:
            try:
                now = self.look()
                if now != last:
                    self.hub.publish(updates=now)
                    last = now
            except Exception:
                if self.log:
                    self.log("looking for updates")
            self.wake.wait(LOOK_EVERY)
            self.wake.clear()

    def start(self):
        start_thread("updates", self.watch)
