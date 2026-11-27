# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import subprocess
import sys
import time

import game
import rebuild
import store
import storedonly
from serverlog import fresh_log, log_error

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
BUILT = os.path.join(ROOT, "data", "clientbuild.json")
STEPS = [step for step in rebuild.ORDER if step in rebuild.CLIENT_STEPS]
CLIENT_EVERY = 600
CLIENT_POLL = 30


def run_step(step, log):
    command = rebuild.COMMANDS[step]
    log.write(f"-- {command[0]}, started {time.strftime('%H:%M:%S')}\n")
    log.flush()
    done = subprocess.run([sys.executable or "python", os.path.join(TOOLS, command[0]), *command[1:]], cwd=ROOT,
                          env={**os.environ, storedonly.STORED_ONLY: "1"}, stdout=log, stderr=subprocess.STDOUT,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log.write(f"-- {command[0]} ended {time.strftime('%H:%M:%S')}, exit {done.returncode}\n")
    log.flush()
    return done.returncode == 0


class ClientRunner:
    def __init__(self, hub, reload, run=run_step, installed=game.installed_version):
        self.hub, self.reload, self.run, self.installed = hub, reload, run, installed
        self.tried = None

    def built(self):
        return (store.load_json(BUILT, {}) or {}).get("build")

    def check(self):
        try:
            installed = self.installed()
        except game.GameNotFound:
            return None
        built = self.built()
        if not installed or installed == built or installed == self.tried:
            return None
        fresh_log(rebuild.LOG)
        with open(rebuild.LOG, "a", encoding="utf-8") as log:
            log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} the client build stages for build {installed} "
                      f"({f'they last ran for {built}' if built else 'their first run here'})\n")
            log.flush()
            needs, through, failed, held = rebuild.upstream(STEPS), [], [], []
            for step in STEPS:
                if needs[step] - set(through):
                    log.write(f"-- {rebuild.COMMANDS[step][0]} held back: it reads what "
                              f"{', '.join(rebuild.COMMANDS[s][0] for s in STEPS if s in needs[step] and s not in through)} makes\n")
                    held.append(step)
                else:
                    (through if self.run(step, log) else failed).append(step)
        if failed:
            self.tried = installed
            log_error("the client build stages", RuntimeError(
                f"{', '.join(rebuild.COMMANDS[s][0] for s in failed)} failed for build {installed}"
                + (f", {', '.join(rebuild.COMMANDS[s][0] for s in held)} held back" if held else "")))
        else:
            store.save_json(BUILT, {"build": installed})
        if through:
            self.reload()
        return not failed

    def watch(self):
        while True:
            try:
                self.check()
            except Exception:
                log_error("the client build stages' check")
            self.wait(CLIENT_EVERY)

    def wait(self, most):
        try:
            path = game.build_info_path(game.data_folder())
        except game.GameNotFound:
            path = None
        was, end = store.stamp(path) if path else None, time.time() + most
        while time.time() < end:
            time.sleep(min(CLIENT_POLL, max(0.0, end - time.time())))
            if path and store.stamp(path) != was:
                return True
        return False
