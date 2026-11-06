# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import http.client
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import mainstores
import store
import storedonly

TRIES = 3
WAIT = 1.0
AGENT = {"User-Agent": "Mozilla/5.0"}


class _Stay(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


STAY = urllib.request.build_opener(_Stay).open


def once(url, timeout=60, headers=None, follow=True):
    open_url = urllib.request.urlopen if follow else STAY
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        with open_url(urllib.request.Request(url, headers={**AGENT, **(headers or {})}), timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        note_health(host, REFUSED if e.code in REFUSALS else ANSWERED if e.code < 500 else FAILED)
        raise
    except http.client.HTTPException as e:
        note_health(host, FAILED)
        raise OSError(f"{url}: {e!r}") from e
    except OSError:
        note_health(host, FAILED)
        raise
    note_health(host, ANSWERED)
    return body


HEALTH = os.environ.get("WCC_SOURCE_HEALTH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                                                             "buildcache", "source-health.json")
REFUSALS = (403, 429)
ANSWERED, REFUSED, FAILED = "answered", "refused", "failed"
NOTHING = "nothing"
DOWN_AFTER = 86400
NOTE_EVERY = 300
_noted = {}


def note_health(host, outcome, now=None):
    now = time.time() if now is None else now
    if not host:
        return
    last = _noted.get(host)
    if outcome == ANSWERED and last and last[0] == ANSWERED and now - last[1] < NOTE_EVERY:
        return
    _noted[host] = (outcome, now)
    try:
        with store.locked(HEALTH):
            health = store.load_json(HEALTH, {})
            h = health.setdefault(host, {})
            h["asked"] = round(now)
            if outcome == ANSWERED:
                h["answered"] = round(now)
                h.pop("refusedSince", None)
                h.pop("failingSince", None)
            else:
                h.setdefault("refusedSince" if outcome == REFUSED else "failingSince", round(now))
            store.save_json(HEALTH, health, indent=None)
    except OSError:
        pass


def down(now=None, health=None):
    now = time.time() if now is None else now
    health = store.load_json(HEALTH, {}) if health is None else health
    out = []
    for host, h in (health or {}).items():
        refused, failing = h.get("refusedSince"), h.get("failingSince")
        if refused is not None and now - refused >= DOWN_AFTER:
            out.append({"host": host, "what": REFUSED, "since": refused, "answered": h.get("answered")})
        elif failing is not None and now - failing >= DOWN_AFTER:
            out.append({"host": host, "what": NOTHING, "since": failing, "answered": h.get("answered")})
    return sorted(out, key=lambda d: (d["since"], d["host"]))


def get(url, timeout=60, headers=None, tries=TRIES, follow=True):
    storedonly.refuse(url)
    last = None
    for attempt in range(tries):
        try:
            return once(url, timeout, headers, follow)
        except urllib.error.HTTPError as e:
            if storedonly.not_there(e):
                raise
            last = e
        except OSError as e:
            last = e
        if attempt < tries - 1:
            time.sleep(WAIT * 2 ** attempt)
    raise last


def kept(url, path, max_age=None, timeout=300):
    name = os.path.basename(path)
    copy = mainstores.standing(path)
    have = os.path.exists(copy)
    due = have and (store.refresh_due(name) or (max_age is not None and time.time() - os.path.getmtime(copy) >= max_age))
    if have and not due:
        with open(copy, "rb") as f:
            return f.read()
    try:
        data = get(url, timeout=timeout)
    except OSError:
        if have:
            with open(copy, "rb") as f:
                return f.read()
        raise
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.write_fetched(path, data)
    store.refreshed(name)
    return data
