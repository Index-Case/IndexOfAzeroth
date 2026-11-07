# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os

import store

WORK = ".update"
NEWS, CHOICE, STOP, ADDON = "news.json", "choice.json", "stop", "addon.json"
CHOICES = ("update", "later")
STEPS = ("offer", "downloading", "waiting")
ADDON_WORDS = ("waiting", "new")


def _path(root, name):
    return os.path.join(root, WORK, name)


def _write(root, name, data):
    store.save_json(_path(root, name), data, indent=None)


def _read(root, name):
    try:
        return store.load_json(_path(root, name), None)
    except OSError:
        return None


def _take(root, name):
    taken = _path(root, name + ".taken")
    try:
        os.replace(_path(root, name), taken)
    except OSError:
        return None
    data = _read(root, name + ".taken")
    try:
        os.remove(taken)
    except OSError:
        pass
    return data


def tell(root, news):
    _write(root, NEWS, {} if news is None else news)


def news(root):
    data = _read(root, NEWS)
    return data if isinstance(data, dict) and data.get("step") in STEPS else None


def choose(root, choice):
    if choice not in CHOICES:
        return False
    _write(root, CHOICE, choice)
    return True


def chosen(root):
    data = _take(root, CHOICE)
    return data if data in CHOICES else None


def ask_stop(root):
    _write(root, STOP, True)


def stop_asked(root):
    return _take(root, STOP) is True


def tell_addon(root, word):
    word = word if word in ADDON_WORDS else None
    if addon(root) != word:
        _write(root, ADDON, word)


def addon(root):
    data = _read(root, ADDON)
    return data if data in ADDON_WORDS else None


def clear(root):
    for name in (NEWS, CHOICE, STOP, ADDON):
        try:
            os.remove(_path(root, name))
        except OSError:
            pass


def running_version(listed):
    try:
        with open(listed, encoding="utf-8") as f:
            version = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return ""
    return version if isinstance(version, str) else ""
