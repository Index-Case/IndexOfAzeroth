# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOADED_ONLY = ("data", "plans", "suites")


_logged = {}


LOG_MOST = 2_000_000
_LOGS = threading.RLock()


def fresh_log(path):
    with _LOGS:
        try:
            if os.path.getsize(path) > LOG_MOST:
                os.replace(path, path + ".old")
        except OSError:
            pass


def append_log(path, text):
    with _LOGS:
        fresh_log(path)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass


def _write(text, path=None):
    append_log(path or os.path.join(ROOT, "data", "server.log"), f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")


class Expected(Exception):
    pass


def log_error(where, error=None):
    import traceback
    error = error if error is not None else sys.exc_info()[1]
    if isinstance(error, Expected):
        err, text = str(error), f"{where}: {error}"
    else:
        err = "".join(traceback.format_exception(error)) if error is not None else traceback.format_exc()
        text = f"{where}\n{err}"
    last = _logged.get(where)
    if last and last[0] == err and time.time() - last[1] < 60:
        return
    _logged[where] = (err, time.time())
    _write(text)


def log_note(text, path=None):
    _write(text, path)


def log_threads():
    threading.excepthook = lambda a: log_error(f"thread {a.thread.name if a.thread else '?'}", a.exc_value)


AGAIN_AFTER = 60.0
AGAIN_MOST = 1800.0


def start_thread(name, work, args=(), kwargs=None, again=False):
    thread = thread_for(name, work, args, kwargs, again)
    thread.start()
    return thread


def thread_for(name, work, args=(), kwargs=None, again=False):

    def run():
        pause = AGAIN_AFTER
        while True:
            try:
                work(*args, **(kwargs or {}))
                return
            except Exception:
                log_error(f"thread {name}")
                if not again:
                    return
            time.sleep(pause)
            pause = min(pause * 2, AGAIN_MOST)
    return threading.Thread(target=run, daemon=True, name=name)


ASK_EVERY = 30.0
ASK_WAIT = 60.0


def watch_answers(ask, every=ASK_EVERY, wait=ASK_WAIT, sleep=time.sleep):
    import faulthandler
    path = os.path.join(ROOT, "data", "server.stuck.log")
    while True:
        sleep(every)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+b") as f:
            at = f.seek(0, os.SEEK_END)
            began = time.time()
            faulthandler.dump_traceback_later(wait, file=f)
            try:
                ask()
            except Exception:
                pass
            finally:
                faulthandler.cancel_dump_traceback_later()
            took = time.time() - began
            if f.seek(0, os.SEEK_END) == at:
                continue
            f.seek(at)
            stacks = f.read()
            f.truncate(at)
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(began))} the Index's ask of its own page not back "
                    f"within {wait:.0f} s, every thread's stack:\n".encode("utf-8") + stacks)
        _write(f"the Index didn't answer its own page for {took:.0f} s: every thread's stack is in data/server.stuck.log")


_STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ?(.*)$")
_FRAME = re.compile(r'^\s*File "([^"]+)", line \d+, in (\S+)')


_CHAINED = ("During handling of the above exception", "The above exception was the direct cause")


def tracebacks(path=None, since=None):
    path = path or os.path.join(ROOT, "data", "server.log")
    found = []
    for name in (path + ".old", path):
        try:
            with open(name, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        when, where, body, last = None, "", None, ""
        for line in lines + [None]:
            stamp = _STAMP.match(line) if line is not None else None
            starts = line is not None and line.startswith("Traceback") and not last.startswith(_CHAINED)
            if body is not None and (line is None or stamp or starts or line.startswith("Exception in thread")):
                if since is None or (when or "") >= since:
                    found.append(_traceback(*body))
                body = None
            if stamp:
                when, where = stamp.group(1), stamp.group(2)
            elif starts:
                body = (when, last[:-1] if last.startswith("Exception in thread") else where, [])
            elif body is not None:
                body[2].append(line)
            if line is not None and line.strip():
                last = line
    return found


def _traceback(when, where, body):
    last_frame = max((i for i, x in enumerate(body) if _FRAME.match(x)), default=-1)
    error = next((x.strip() for x in body[last_frame + 1:] if x.strip() and not x.startswith(" ")), "")
    frame = None
    python = os.path.normcase(sys.base_prefix)
    for x in body:
        m = _FRAME.match(x)
        where_from = os.path.normcase(m.group(1)) if m else ""
        if m and not (where_from.startswith(("<", python)) or "site-packages" in where_from):
            frame = f"{os.path.basename(m.group(1))} {m.group(2)}"
    kind = error.split(":", 1)[0] + (f" in {frame}" if frame else "")
    return {"when": when, "where": where, "kind": kind, "error": error}


def new_tracebacks(since, path=None):
    kinds = {}
    for t in tracebacks(path, since):
        kinds.setdefault(t["kind"], []).append(t)
    return [f"{kind}: {len(ts)} since {since}, the last at {ts[-1]['when']} ({ts[-1]['where'][:80]}): "
            f"{ts[-1]['error'][:200]}" for kind, ts in kinds.items()]
