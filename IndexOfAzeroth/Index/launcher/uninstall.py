# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
for _p in (HERE, INSTALL):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import appwindow
import layout
import shortcuts
import start
import updatenews
import updater
import words

LOCAL = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"
SET_ASIDE = ("IndexOfAzeroth", "Set aside")
AN_INSTALL = tuple(layout.at(p) for p in (layout.START, shortcuts.PYTHON, shortcuts.START))
NOT_AN_INSTALL = (".git", "dev")
KEPT = (layout.PYTHON, *updater.OURS)
STOP_WAIT = 120
DELETE = r"""
$p = $env:INDEX_UNINSTALL
Wait-Process -Id $env:INDEX_WAIT -ErrorAction SilentlyContinue
for ($i = 0; $i -lt 120 -and (Test-Path -LiteralPath $p); $i++) {
  Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $p) { Start-Sleep -Seconds 1 }
}
"""


class NotAnInstall(Exception):
    pass


def is_install(folder):
    return (all(os.path.isfile(shortcuts.place(folder, rel)) for rel in AN_INSTALL)
            and not any(os.path.exists(shortcuts.place(folder, at)) for rel in NOT_AN_INSTALL
                        for at in (rel, layout.at(rel))))


def records(folder, named):
    out = []
    for top, dirs, files in os.walk(folder):
        rel_top = os.path.relpath(top, folder).replace("\\", "/")
        dirs[:] = [d for d in dirs if d != "__pycache__" and (rel_top != layout.INDEX or d not in KEPT)]
        for name in files:
            rel = name if rel_top == "." else f"{rel_top}/{name}"
            place = layout.place(rel)
            if place is None or not (place in layout.TOP or place in named or place in KEPT):
                out.append(rel)
    return sorted(out)


def set_aside(install, rels, folder):
    for rel in rels:
        target = shortcuts.place(folder, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(shortcuts.place(install, rel), target)


def game_addons():
    import game
    try:
        return game.game_addons_dir()
    except (game.GameNotFound, OSError):
        return None


def stop_index(install=INSTALL):
    if not appwindow.answers(start.PORT, 2):
        return
    print(words.say("page.launcher.uninstall-closing"))
    updatenews.ask_stop(install)
    for _ in range(STOP_WAIT):
        if not appwindow.answers(start.PORT, 2):
            return
        time.sleep(1)


def delete_later(install):
    subprocess.Popen(shortcuts.powershell(DELETE), cwd=tempfile.gettempdir(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                     env={**os.environ, "INDEX_UNINSTALL": install, "INDEX_WAIT": str(os.getpid())},
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)


def uninstall(install, name, addons=game_addons, places=shortcuts.places, named=updater.shipped,
              aside=lambda: os.path.join(shortcuts.known_folder(LOCAL), *SET_ASIDE), stop=stop_index,
              delete=delete_later, now=datetime.datetime.now):
    if not is_install(install):
        raise NotAnInstall(install)
    program = shortcuts.place(install, layout.INDEX)
    stop(program)
    try:
        for lnk in places(name):
            if os.path.isfile(lnk):
                os.remove(lnk)
    except OSError:
        pass
    folder = addons()
    addon = os.path.join(folder, start.ADDON) if folder else None
    if addon and os.path.isfile(os.path.join(addon, start.ADDON + ".toc")):
        shutil.rmtree(addon, ignore_errors=True)
    rels = records(install, named(program))
    kept = os.path.join(aside(), now().strftime("%Y-%m-%d %H.%M.%S")) if rels else None
    if kept:
        set_aside(install, rels, kept)
    delete(install)
    return kept


def main():
    def enter():
        print(words.say("page.launcher.uninstall-enter"))
        try:
            input()
        except EOFError:
            pass

    try:
        answer = input(words.say("page.launcher.uninstall-ask") + " ")
    except EOFError:
        answer = ""
    if not answer.strip().lower().startswith("y"):
        print(words.say("page.launcher.uninstall-kept"))
        enter()
        return 0
    os.chdir(tempfile.gettempdir())
    try:
        kept = uninstall(layout.install_of(INSTALL), words.say("page.launcher.title"))
    except NotAnInstall:
        print(words.say("page.launcher.uninstall-refused"))
        enter()
        return 1
    if kept:
        print(words.say("page.launcher.uninstall-set-aside", {"folder": kept}))
    print(words.say("page.launcher.uninstall-done"))
    enter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
