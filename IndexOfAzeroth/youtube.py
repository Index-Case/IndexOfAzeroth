# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import html
import json
import re
import threading
import urllib.error
import urllib.parse

import downloads
import storedonly

VIDEO = re.compile(r"^[\w-]{11}$")
HANDLE = re.compile(r"^@[\w.-]{3,30}$")
CHANNEL_ID = r"(UC[\w-]{22})"
CANONICAL = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/' + CHANNEL_ID + '"')
EXTERNAL = re.compile(r'"externalId":"' + CHANNEL_ID + '"')
TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
TIMEOUT = 20
KEPT = {}
LOCK = threading.Lock()


def _page(url, get):
    try:
        return get(url, timeout=TIMEOUT).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if storedonly.not_there(e):
            return None
        raise


def _from_handle(handle, get):
    page = _page("https://www.youtube.com/" + urllib.parse.quote(handle, safe="@"), get)
    if page is None:
        return None
    found = CANONICAL.search(page) or EXTERNAL.search(page)
    if not found:
        raise storedonly.Unreadable(f"YouTube's page for {handle} names no channel ID")
    title = TITLE.search(page)
    return {"channel": found.group(1), "name": html.unescape(title.group(1)) if title else handle, "handle": handle}


def _from_video(video, get):
    watch = urllib.parse.quote("https://www.youtube.com/watch?v=" + video, safe="")
    body = _page(f"https://www.youtube.com/oembed?url={watch}&format=json", get)
    if body is None:
        return None
    try:
        info = json.loads(body)
    except ValueError as e:
        raise storedonly.Unreadable("YouTube's oEmbed answer isn't JSON") from e
    link = info.get("author_url") if isinstance(info, dict) else None
    if not isinstance(link, str):
        raise storedonly.Unreadable("YouTube's oEmbed answer links no channel")
    name = info.get("author_name") if isinstance(info.get("author_name"), str) else ""
    direct = re.search(r"/channel/" + CHANNEL_ID + "$", link)
    if direct:
        return {"channel": direct.group(1), "name": name, "handle": None}
    handle = link.rsplit("/", 1)[-1]
    if not HANDLE.match(handle):
        raise storedonly.Unreadable(f"YouTube's oEmbed answer links its channel as {link!r}")
    found = _from_handle(handle, get)
    return found and {**found, "name": name or found["name"]}


def channel(video=None, handle=None, get=downloads.get):
    if video is not None and not VIDEO.match(video):
        raise ValueError(f"not a YouTube video ID: {video!r}")
    if video is None and not (handle and HANDLE.match(handle)):
        raise ValueError(f"not a YouTube @name: {handle!r}")
    key = f"v:{video}" if video else handle.lower()
    with LOCK:
        if key in KEPT:
            return KEPT[key]
    found = _from_video(video, get) if video else _from_handle(handle, get)
    with LOCK:
        KEPT[key] = found
    return found
