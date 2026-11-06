# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import contextlib
import os
import urllib.error

import carried
from serverlog import Expected

STORED_ONLY = "WCC_STORED_ONLY"


class NotStored(Expected, OSError):
    pass


class NotBuilt(NotStored):

    def __init__(self, what):
        super().__init__(f"not built yet: {what}")
        self.what = what


_stored = carried.switch(__name__, "stored", False)


@contextlib.contextmanager
def stored_only():
    token = _stored.set(True)
    try:
        yield
    finally:
        _stored.reset(token)


def is_stored_only():
    return _stored.get() or bool(os.environ.get(STORED_ONLY))


def refuse(what):
    if is_stored_only():
        raise NotStored(f"Not stored yet: {what}")


_sources = carried.switch(__name__, "sources", None)


def set_sources(sources):
    _sources.set(sources)


def sources():
    return None if is_stored_only() else _sources.get()


def not_there(error):
    return isinstance(error, urllib.error.HTTPError) and error.code < 500


class Unreadable(OSError):
    pass
