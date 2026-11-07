# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import io
import os
import time
import zipfile
import zlib

import numpy as np

import mainstores
import store

UNREADABLE = (zipfile.BadZipFile, EOFError, ValueError, KeyError, zlib.error, OSError)


def save_npz(path, **arrays):
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    store.write_bytes(path, buf.getvalue())


def load_npz(path):
    for _ in range(store.SWAP_TRIES):
        try:
            with open(path, "rb") as f, np.load(f) as z:
                return {k: z[k] for k in z.files}
        except FileNotFoundError:
            return None
        except PermissionError:
            time.sleep(store.SWAP_WAIT)
        except UNREADABLE:
            set_aside(path)
            return None
    return None


def set_aside(path):
    if mainstores.in_main(path):
        return
    stamp = f"{path}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}"
    target, n = stamp, 1
    while os.path.exists(target):
        target, n = f"{stamp}-{n}", n + 1
    try:
        os.replace(path, target)
    except OSError:
        pass
