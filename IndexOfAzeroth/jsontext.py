# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json


def plain(o):
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def dumps(obj, indent=None, sort_keys=False):
    return json.dumps(obj, default=plain, indent=indent, sort_keys=sort_keys,
                      separators=(",", ":") if indent is None else None)
