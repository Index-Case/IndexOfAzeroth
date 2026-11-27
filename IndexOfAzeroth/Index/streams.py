# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import re
import threading
import time
import urllib.error

import downloads
import storedonly

CHANNEL = {"YouTube": re.compile(r"^UC[\w-]{22}$"), "Twitch": re.compile(r"^\w{2,25}$"), "Kick": re.compile(r"^[\w-]{2,30}$")}
KEEP = 60
TIMEOUT = 15
TRIES = 2
DETAILS = '"videoDetails":'
KEPT = {}
LOCK = threading.Lock()


def _ask(url, follow=True, headers=None):
    return downloads.get(url, timeout=TIMEOUT, headers=headers, tries=TRIES, follow=follow)


def _youtube(channel, ask):
    try:
        page = ask(f"https://www.youtube.com/channel/{channel}/live").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise OSError(f"YouTube answered {e.code}") from e
    at = page.find(DETAILS)
    if at < 0:
        return False
    try:
        details, _ = json.JSONDecoder().raw_decode(page, at + len(DETAILS))
    except ValueError:
        details = None
    if not isinstance(details, dict):
        raise storedonly.Unreadable("YouTube's live page reads differently now")
    return details.get("isLive") is True


def _twitch(channel, ask):
    try:
        ask(f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel.lower()}-80x45.jpg", follow=False)
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400 or e.code == 404:
            return False
        raise OSError(f"Twitch answered {e.code}") from e
    return True


def _kick(channel, ask):
    try:
        body = ask(f"https://kick.com/api/v2/channels/{channel.lower()}", headers={"Accept": "application/json"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise OSError(f"Kick answered {e.code}") from e
    try:
        details = json.loads(body)
    except ValueError:
        details = None
    if not isinstance(details, dict):
        raise storedonly.Unreadable("Kick's answer isn't a channel's details")
    stream = details.get("livestream")
    return isinstance(stream, dict) and stream.get("is_live", True) is not False


SITES = {"YouTube": _youtube, "Twitch": _twitch, "Kick": _kick}


def live(site, channel, ask=_ask):
    if site not in CHANNEL or not CHANNEL[site].match(channel or ""):
        raise ValueError(f"not a stream the dots know: {site!r} {channel!r}")
    key = (site, channel if site == "YouTube" else channel.lower())
    with LOCK:
        kept = KEPT.get(key)
        if kept and time.time() - kept[0] < KEEP:
            return kept[1]
    answer = SITES[site](channel, ask)
    with LOCK:
        now = time.time()
        for old in [k for k, (at, _) in KEPT.items() if now - at >= KEEP]:
            del KEPT[old]
        KEPT[key] = (now, answer)
    return answer
