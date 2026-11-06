# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse

import jsontext
from serverlog import append_log

LOADED_ONLY = ("data", "plans", "suites")

HIDDEN = re.compile(r"key|token|secret|auth|sig|pass", re.I)
KEEP = 400
GRAPH_SECONDS = 120


def shown_url(url):
    try:
        p = urllib.parse.urlsplit(url)
        q = [(k, "hidden" if HIDDEN.search(k) else v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)]
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q, safe=":/,"), ""))
    except ValueError:
        return str(url)[:300]


class Counted:

    def __init__(self, resp, done):
        self._resp, self._done, self.counted = resp, done, 0

    def read(self, *args):
        data = self._resp.read(*args)
        self.counted += len(data)
        return data

    def close(self):
        done, self._done = self._done, None
        if done:
            done(self.counted)
        self._resp.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __iter__(self):
        for line in self._resp:
            self.counted += len(line)
            yield line

    def __getattr__(self, name):
        return getattr(self._resp, name)


def wrap(urlopen, note):
    def opened(req, *args, **kwargs):
        url, t0 = getattr(req, "full_url", req), time.time()
        try:
            resp = urlopen(req, *args, **kwargs)
        except urllib.error.HTTPError as e:
            note(url, e.code, 0, time.time() - t0)
            raise
        except Exception as e:
            note(url, type(e).__name__, 0, time.time() - t0)
            raise
        return Counted(resp, lambda n: note(url, getattr(resp, "status", None), n, time.time() - t0))
    return opened


_plain = []


def watch(note, waiting_on):
    import urllib.request
    if not _plain:
        _plain.append(urllib.request.urlopen)
    plain = _plain[0]

    def waited(req, *args, **kwargs):
        with waiting_on(urllib.parse.urlsplit(str(getattr(req, "full_url", req))).hostname or "?"):
            return plain(req, *args, **kwargs)
    urllib.request.urlopen = wrap(waited, note)


class Traffic:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = collections.deque(maxlen=KEEP)
        self.last = 0
        self.seconds = collections.OrderedDict()

    def note(self, url, status, nbytes, seconds, who="server", at=None):
        at = time.time() if at is None else at
        with self.lock:
            self.last += 1
            self.calls.append({"id": self.last, "at": round(at, 1), "url": shown_url(url),
                               "host": urllib.parse.urlsplit(str(url)).hostname or "", "bytes": int(nbytes or 0),
                               "ms": round((seconds or 0) * 1000), "status": status, "who": who})
            s = self.seconds.setdefault(int(at), [0, 0])
            s[0] += int(nbytes or 0)
            s[1] += 1
            while self.seconds and next(iter(self.seconds)) < time.time() - GRAPH_SECONDS - 5:
                self.seconds.popitem(last=False)

    def snapshot(self, since=0):
        now = int(time.time())
        with self.lock:
            calls = [c for c in self.calls if c["id"] > since]
            span = range(now - GRAPH_SECONDS + 1, now + 1)
            return {"calls": calls, "bytes": [self.seconds.get(t, [0, 0])[0] for t in span],
                    "count": [self.seconds.get(t, [0, 0])[1] for t in span], "now": now, "last": self.last}

    def tail(self, path, every=2.0):
        at = os.path.getsize(path) if os.path.exists(path) else 0
        while True:
            time.sleep(every)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size < at:
                at = 0
            if size == at:
                continue
            try:
                with open(path, "rb") as f:
                    f.seek(at)
                    chunk = f.read(size - at)
            except OSError:
                continue
            at = size
            for line in chunk.decode("utf-8", "replace").splitlines():
                try:
                    c = json.loads(line)
                    if not isinstance(c["url"], str):
                        continue
                    self.note(c["url"], c.get("status"), c.get("bytes"), c.get("seconds"), who="rebuild", at=c.get("at"))
                except (ValueError, KeyError, TypeError):
                    continue


def log_to_file(path):
    import urllib.request

    def note(url, status, nbytes, seconds):
        line = jsontext.dumps({"url": shown_url(url), "status": status, "bytes": nbytes, "seconds": round(seconds, 3), "at": round(time.time(), 1)})
        append_log(path, line + "\n")
    urllib.request.urlopen = wrap(urllib.request.urlopen, note)
