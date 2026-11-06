# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import numpy as np

SIGMA = b"expand 32-byte k"
TAU = b"expand 16-byte k"
COLUMNS = ((0, 4, 8, 12), (5, 9, 13, 1), (10, 14, 2, 6), (15, 3, 7, 11))
ROWS = ((0, 1, 2, 3), (5, 6, 7, 4), (10, 11, 8, 9), (15, 12, 13, 14))


def _rotl(v, n):
    return (v << np.uint32(n)) | (v >> np.uint32(32 - n))


def _quarter(x, a, b, c, d):
    x[b] ^= _rotl(x[a] + x[d], 7)
    x[c] ^= _rotl(x[b] + x[a], 9)
    x[d] ^= _rotl(x[c] + x[b], 13)
    x[a] ^= _rotl(x[d] + x[c], 18)


def stream(key, nonce, n, start=0):
    if len(key) not in (16, 32) or len(nonce) != 8:
        raise ValueError("Salsa20 takes a 16 or 32 byte key and an 8 byte nonce")
    const = np.frombuffer(TAU if len(key) == 16 else SIGMA, "<u4")
    k = np.frombuffer(bytes(key), "<u4")
    k1, k2 = k[:4], (k[4:] if len(key) == 32 else k[:4])
    v = np.frombuffer(bytes(nonce), "<u4")
    blocks = (n + 63) // 64
    counter = np.arange(blocks, dtype=np.uint64) + np.uint64(start)
    state = np.empty((16, blocks), np.uint32)
    for i, w in ((0, const[0]), (5, const[1]), (10, const[2]), (15, const[3]), (6, v[0]), (7, v[1])):
        state[i] = w
    state[1:5] = k1[:, None]
    state[11:15] = k2[:, None]
    state[8] = (counter & 0xFFFFFFFF).astype(np.uint32)
    state[9] = (counter >> np.uint64(32)).astype(np.uint32)
    x = state.copy()
    with np.errstate(over="ignore"):
        for _ in range(10):
            for q in COLUMNS:
                _quarter(x, *q)
            for q in ROWS:
                _quarter(x, *q)
        x += state
    return x.T.astype("<u4").tobytes()[:n]


def xor(key, nonce, data):
    pad = np.frombuffer(stream(key, nonce, len(data)), np.uint8)
    return (np.frombuffer(bytes(data), np.uint8) ^ pad).tobytes()
