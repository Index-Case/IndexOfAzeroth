# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import thispc
thispc.answer()

import argparse
import os
import sys

import appwindow
import minimap_track
import trackdots
from addons import AddonManager, AddonState
from dungeons import share_stars
import storedonly
import game
from clientrunner import ClientRunner
from pending import Pending, addon_folder
from shared import Shared, quiet_table
import stepplaces
from warnmoves import WarnMoves
from gamedata import load_todo
from updates import Updates
import updatenews
from pack import Pack, apply_staged
from epicwatch import EpicWatch
from nextzones import NextZones
import questplan
import storewriter
from serverlog import ASK_WAIT, log_error, log_threads, start_thread, watch_answers
from planning import (QuestPicks, covered_points, indoor_points, dress_epic, ends_finder, epic_context, plan_epic, reward_finder,
                      plan_ways, reckon_levels, shared_ground_finder, shared_route_finder, shared_way_finder, table_spawns,
                      unknown_giver, warm_paths)
from strip import strip_loop
from npcs import warm_npcs
from handler import TYPES, PageServer, make_handler, whole
from hub import Hub, reload_data, share_nodes, share_watch
from layers import lay_gathered
import nav
import words
from navfill import Fill

ROOT = os.path.dirname(os.path.abspath(__file__))


def wtf_or_none():
    try:
        return game.wtf_dir()
    except game.GameNotFound:
        return None


def screenshots_or_none():
    try:
        return game.screenshots_dir()
    except game.GameNotFound:
        return None


def dev_module():
    path = game.dev_hooks()
    if not path:
        return None
    import importlib.util
    if game.DEV_DIR not in sys.path:
        sys.path.insert(0, game.DEV_DIR)
    spec = importlib.util.spec_from_file_location("dev_serve", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_dev(hub, dev):
    return dev.Hooks(hub, TYPES, whole) if dev else None


def start_tracker(hub):
    if not minimap_track.ON:
        return None
    from capture import WindowRegion
    tracker = minimap_track.MinimapTracker(hub, WindowRegion())
    start_thread("minimap tracker", tracker.run)
    return tracker


def start_dots(hub):
    if not trackdots.ON:
        return None
    from capture import WindowRegion
    reader = trackdots.DotReader(hub, WindowRegion(), changed=lambda: lay_gathered(hub.world, hub.gathered.all))
    start_thread("minimap dots", reader.run)
    return reader




PIPELINE, SERVING, RELEASE = "pipeline", "serving", "release"
JOBS = {
    "patch notes": PIPELINE,
    "rebuild": PIPELINE,
    "addon manager": PIPELINE,
    "navigation fill": PIPELINE,
    "client runner": RELEASE,
    "addons read": RELEASE,
    "path warm-up": SERVING,
    "NPC book": SERVING,
    "developer's additions": SERVING,
    "auction scans saved": SERVING,
    "level ups saved": SERVING,
    "talent ranks saved": SERVING,
    "day recording": SERVING,
    "epic watcher": SERVING,
    "quest book": SERVING,
    "strip reader": SERVING,
    "minimap dots": SERVING,
    "answer watch": SERVING,
}
PIPELINE_ENV = "DGG_PIPELINE"


def pipeline_on(dev, asked=False, root=None, env=None):
    env = os.environ if env is None else env
    return bool(dev) and (game.writes_game(root) or bool(asked) or env.get(PIPELINE_ENV) == "1")


def jobs_on(pipeline, release=False):
    return {job for job, kind in JOBS.items() if kind == SERVING or (kind == PIPELINE and pipeline)
            or (kind == RELEASE and release)}


def start_job(on, job, target, args=(), kwargs=None):
    if job not in on:
        return None
    return start_thread(job, target, args, kwargs)


def background_work(hub):
    rebuilder, fill = getattr(hub, "rebuilder", None), getattr(hub, "navfill", None)
    return bool((rebuilder and rebuilder.running.locked()) or (fill and fill.running()) or nav.ACTIVITY.now()["working"])




def main():
    dev = dev_module()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--window", action="store_true", help="open the page in its own window (appwindow.py) once serving")
    ap.add_argument("--on-close", choices=("keep", "stop"), default=appwindow.ON_CLOSE["dev" if dev else "release"],
                    help="what closing the last window does to the server: the dev copy keeps it, a release stops it")
    ap.add_argument("--pipeline", action="store_true",
                    help="run the rebuild pipeline from a git worktree too, for a builder's test (also DGG_PIPELINE=1)")
    if dev:
        dev.arguments(ap)
    args = ap.parse_args()
    stand_in = dev.stand_in(args) if dev else None
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    server = PageServer((host, args.port), None, bind_and_activate=False)
    try:
        if appwindow.take_port(args.port) != "free":
            raise OSError("the port is held")
        server.server_bind()
    except OSError as e:
        server.server_close()
        if args.window:
            appwindow.open_window(appwindow.page_url(args.port))
            return
        raise SystemExit(f"The Index of Azeroth can't have port {args.port}: {e}")

    log_threads()
    applied = apply_staged()
    nav.wm.serve_built()
    pipeline = pipeline_on(dev, args.pipeline)
    on = set() if stand_in else jobs_on(pipeline, release=not dev)
    hub = Hub()
    hub.navfill = Fill(log_error)
    if "navigation fill" in on:
        hub.paths.terrain.wanted = hub.navfill.want
    hub.rebuilder = hub.clientrunner = hub.tracker = hub.trackdots = hub.addons = hub.pending = hub.shared = hub.watch = None
    hub.moves = WarnMoves()
    hub.moves.took(load_todo())
    hub.updates = Updates(hub, lambda: addon_folder(game.addons_dir), log_error,
                          version=updatenews.running_version(game.RELEASE_LIST), stop=lambda: hub.pages.for_update())
    hub.updates.start()
    hub.pack = Pack(applied, log_error)
    hub.dev = load_dev(hub, dev)
    if stand_in:
        stand_in(hub)
    else:
        hub.tracker = start_tracker(hub)
        hub.trackdots = start_dots(hub)
        if pipeline:
            hub.patches = dev.PatchNotes(hub)
            hub.rebuilder = dev.Rebuilder(hub, lambda: reload_data(hub), on_client=hub.patches.see_build)
        start_job(on, "rebuild", hub.rebuilder and hub.rebuilder.watch)
        if "client runner" in on:
            hub.clientrunner = ClientRunner(hub, lambda: reload_data(hub))
        start_job(on, "client runner", hub.clientrunner and hub.clientrunner.watch)
        if pipeline:
            hub.addons = AddonManager(hub, lambda: hub.rebuilder.start("an addon installed", "sources"),
                                      site=dev.AddonSite())
        elif "addons read" in on:
            hub.addons = AddonState(hub)
        start_job(on, "path warm-up", warm_paths, (hub,))
        start_job(on, "navigation fill", hub.navfill.watch)
        start_job(on, "NPC book", warm_npcs, (hub,))
        start_job(on, "addon manager", hub.addons and hub.addons.watch)
        start_job(on, "addons read", hub.addons and hub.addons.watch)
        start_job(on, "patch notes", hub.patches and hub.patches.watch)
        if hub.dev and hasattr(hub.dev, "started") and "developer's additions" in on:
            hub.dev.started(hub, log_error, pipeline=pipeline)
        start_job(on, "auction scans saved", hub.auction.watch_saved, (wtf_or_none, log_error))
        start_job(on, "level ups saved", hub.levelreports.watch_saved, (wtf_or_none, log_error),
                  {"shots_dir": screenshots_or_none})
        start_job(on, "talent ranks saved", hub.talentranks.watch_saved, (wtf_or_none, log_error))
        start_job(on, "day recording", hub.dayrecord.watch, (), {"log_error": log_error})
        hub.pending = Pending(game.game_addons_dir, os.path.join(ROOT, "data", "pending.json"))
        hub.shared = Shared(game.game_addons_dir, os.path.join(ROOT, "data", "shared.json"))
        hub.shared.failed = lambda: log_error("a plan's way")
        hub.shared.find_ground = shared_ground_finder(hub)
        hub.shared.find_danger = lambda inst, pts: hub.dangerous.careful(
            inst, pts, ((hub.status or {}).get("strs") or {}).get("faction") or None)
        hub.shared.find_covered = lambda inst, pts: covered_points(hub, inst, pts)
        hub.shared.find_indoor = lambda inst, pts: indoor_points(hub, inst, pts)
        hub.shared.find_height = hub.heights_seen.height
        hub.shared.find_place = stepplaces.place_finder(hub)
        hub.shared.find_rewards = reward_finder(hub)
        hub.shared.find_ends = ends_finder(hub)
        hub.shared.find_spawns = table_spawns(hub, lambda: ((hub.status or {}).get("strs") or {}).get("faction") or None)
        for name, keep in (("Pending.lua", hub.pending), ("Shared.lua", hub.shared)):
            try:
                keep.ensure()
            except OSError:
                log_error(f"setting up {name}")
        hub.moves.shared = hub.shared
        try:
            hub.shared.set_quiet(quiet_table(load_todo()))
        except OSError:
            log_error("writing the quiet warnings into Shared.lua")
        try:
            share_watch(hub)
        except OSError:
            log_error("writing the watch list into Shared.lua")
        share_stars(hub)
        share_nodes(hub)
        hub.watch = EpicWatch(hub.shared, lambda key, anchor, parked, kept:
                              (lambda e: None if e and e.get("waiting") else e)(plan_epic(hub, key, anchor, parked,
                                                                                         kept=kept)),
                              lambda key, epic, at, **how: dress_epic(hub, key, epic, at, **how),
                              lambda mode: shared_way_finder(hub, mode), lambda: epic_context(hub), log_error,
                              lambda mode: shared_route_finder(hub, mode), answers=hub.offers, unknown=unknown_giver,
                              rewards=QuestPicks(hub),
                              nexts=NextZones(hub),
                              reckon=lambda steps: reckon_levels(hub, steps),
                              ways=lambda: plan_ways(hub))
        start_job(on, "epic watcher", storedonly.stored_only()(hub.watch.run))
        start_job(on, "quest book", questplan.book)
        start_job(on, "strip reader", storedonly.stored_only()(strip_loop), (hub,))
    storewriter.on_write_error(lambda path: log_error(f"saving {os.path.basename(path)}"))
    server.RequestHandlerClass = make_handler(hub)
    server.server_activate()
    start_job(on, "answer watch", watch_answers, (lambda: appwindow.answers(args.port, 4 * ASK_WAIT),))
    hub.pages = appwindow.Pages(stop=(lambda: server.shutdown()) if args.on_close == "stop" else None,
                                busy=lambda: background_work(hub),
                                tray=appwindow.Tray(words.say("page.tray.finishing"),
                                                    os.path.join(ROOT, "assets", "index.ico")))
    if args.window:
        start_thread("app window", appwindow.open_window, (appwindow.page_url(args.port),))
    print(f"The Index of Azeroth on http://localhost:{args.port}" + (" and your LAN address" if args.lan else ""))
    server.serve_forever()


if __name__ == "__main__":
    main()
