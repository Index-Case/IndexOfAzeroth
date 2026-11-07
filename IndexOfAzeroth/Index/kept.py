# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
UNKEPT = object()


def keep(cache, key, value, most):
    if len(cache) >= most:
        cache.clear()
    cache[key] = value
    return value
