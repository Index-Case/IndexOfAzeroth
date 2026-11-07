# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import hashlib
import os
import struct
import threading
import time
import zlib

import numpy as np

import game
import gamefiles
import salsa20

OFF = "WCC_NO_LOCAL_ARCHIVES"
RETRY = 60.0
KINDS = ("local", "encrypted", "missing", "error", "build")
LOCALES = {"enUS": 0x2, "koKR": 0x4, "frFR": 0x10, "deDE": 0x20, "zhCN": 0x40, "esES": 0x80, "zhTW": 0x100,
           "enGB": 0x200, "enCN": 0x400, "enTW": 0x800, "esMX": 0x1000, "ruRU": 0x2000, "ptBR": 0x4000, "itIT": 0x8000,
           "ptPT": 0x10000}
LOW_VIOLENCE, NO_NAME_HASH = 0x80, 0x10000000
ENTRY_HEAD = 30
ENCODING_BATCH = 256


class LocalError(Exception):
    pass


class Missing(LocalError):
    pass


class Encrypted(LocalError):
    pass



def build_info(text, product):
    found = [r for r in game.build_rows(text) if r.get("Product") == product]
    if not found:
        raise LocalError(f"{product} isn't in .build.info")
    return next((r for r in found if r.get("Active") == "1"), found[0])


def locale_flag(tags):
    for part in tags.split(":"):
        if part.strip().endswith("text?"):
            for word in part.split():
                if word in LOCALES:
                    return LOCALES[word]
    return LOCALES["enUS"]


def config(text):
    out = {}
    for line in text.splitlines():
        key, eq, value = line.partition(" = ")
        if eq and not key.startswith("#"):
            out[key.strip()] = value.split()
    return out


def blte_table(view):
    if view[:4] != b"BLTE" or len(view) < 9:
        raise LocalError("not BLTE")
    head = int.from_bytes(view[4:8], "big")
    if head == 0:
        return 8, None
    kind, count = view[8], int.from_bytes(view[9:12], "big")
    size = {0x0F: 24, 0x10: 40}.get(kind)
    if size is None or count < 1 or head != 12 + count * size or len(view) < head:
        raise LocalError("a BLTE block table not as documented")
    return head, [struct.unpack_from(">II", view, 12 + i * size) for i in range(count)]


def decrypt(block, index, keys):
    view = bytes(block[:32])
    try:
        name_size = view[1]
        name = int.from_bytes(view[2:2 + name_size], "little")
        iv_size = view[2 + name_size]
        iv = view[3 + name_size:3 + name_size + iv_size]
        kind = view[3 + name_size + iv_size:4 + name_size + iv_size]
    except IndexError:
        raise LocalError("an E block's head cut short") from None
    if name_size != 8 or iv_size not in (4, 8) or len(iv) != iv_size or kind not in (b"S", b"A"):
        raise LocalError("an E block's head not as documented")
    key = (keys or {}).get(name)
    if key is None or kind != b"S":
        raise Encrypted(f"an encrypted block, key {name:016X}")
    nonce = bytearray(iv.ljust(8, b"\0"))
    nonce[:4] = (int.from_bytes(nonce[:4], "little") ^ (index & 0xFFFFFFFF)).to_bytes(4, "little")
    return salsa20.xor(key, bytes(nonce), block[4 + name_size + iv_size:])


def inflate(block, logical=None, index=0, keys=None):
    mode = block[:1]
    if mode == b"E" and keys:
        block = decrypt(block, index, keys)
        mode = block[:1]
        if mode not in (b"N", b"Z"):
            raise LocalError("an E block that doesn't decrypt to an N or Z block")
    if mode == b"N":
        part = block[1:]
    elif mode == b"Z":
        try:
            part = zlib.decompress(block[1:])
        except zlib.error as e:
            raise LocalError(f"a zlib block that won't inflate ({e})") from None
    elif mode == b"E":
        raise Encrypted("an encrypted block")
    else:
        raise LocalError(f"a BLTE block of mode {bytes(mode)!r}")
    if logical is not None and len(part) != logical:
        raise LocalError("a BLTE block not the size its table says")
    return part


def blte(data):
    view = memoryview(data)
    head, table = blte_table(view)
    if table is None:
        blocks = [(view[8:], None)]
    else:
        blocks, at = [], head
        for raw, logical in table:
            blocks.append((view[at:at + raw], logical))
            at += raw
        if at != len(view):
            raise LocalError("BLTE blocks not the stream's length")
    if any(b[:1] == b"E" for b, _ in blocks):
        raise Encrypted("an encrypted block")
    known = table is not None
    out = bytearray(sum(n for _, n in blocks) if known else 0)
    at = 0
    for b, logical in blocks:
        part = inflate(b, logical)
        if not known:
            out += part
        else:
            out[at:at + logical] = part
            at += logical
    return out


class Content:

    def __init__(self, data=b""):
        self.left = [memoryview(data)]
        self.part, self.pos = memoryview(b""), 0

    def next_part(self):
        return self.left.pop() if self.left else None

    def at_end(self):
        while self.part is not None and self.pos >= len(self.part):
            self.part, self.pos = self.next_part(), 0
        return self.part is None

    def take(self, n):
        out = []
        self.walk(n, out.append)
        return b"".join(out)

    def skip(self, n):
        return self.walk(n, None)

    def walk(self, n, put):
        passed = 0
        while passed < n and not self.at_end():
            piece = self.part[self.pos:self.pos + n - passed]
            self.pos += len(piece)
            passed += len(piece)
            if put:
                put(piece)
        return passed

    def finish(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Stream(Content):

    def __init__(self, folder, archive, offset, size, ekey, ckey):
        super().__init__()
        self.ckey, self.md5, self.blocks = ckey, hashlib.md5(), []
        self.f = gamefiles.open_shared(os.path.join(folder, f"data.{archive:03d}"))
        try:
            self.f.seek(offset)
            start = entry_start(self.read(min(size, ENTRY_HEAD), "its entry is cut short"), size, ekey)
            self.f.seek(offset + start)
            length = size - start
            first = self.read(min(length, 12), "its entry is cut short")
            head = int.from_bytes(first[4:8], "big") if len(first) >= 8 else 0
            if head > length:
                raise LocalError("a BLTE block table not as documented")
            if head > len(first):
                first += self.read(head - len(first), "its entry is cut short")
            head, table = blte_table(memoryview(first))
            rest = first[head:]
            if table is None:
                table = [(length - head, None)]
            elif sum(raw for raw, _ in table) != length - head:
                raise LocalError("BLTE blocks not the stream's length")
            self.blocks, self.rest = list(reversed(table)), rest
        except BaseException:
            self.f.close()
            raise

    def read(self, n, why):
        got = self.f.read(n)
        if len(got) != n:
            raise Missing(why)
        return got

    def next_part(self):
        if not self.blocks:
            return None
        raw, logical = self.blocks.pop()
        block = self.rest + self.read(raw - len(self.rest), "its entry is cut short")
        self.rest = b""
        part = inflate(memoryview(block), logical)
        self.md5.update(part)
        return memoryview(part)

    def finish(self):
        while not self.at_end():
            self.pos = len(self.part)
        if self.md5.digest() != self.ckey:
            raise LocalError("its content isn't what root names")

    def __exit__(self, *exc):
        self.f.close()
        return False


def be64(keys):
    return np.ascontiguousarray(keys[:, :8]).view(">u8").ravel().astype(np.uint64)


def find_rows(sorted_keys, sorted_k8, keys):
    if not len(sorted_keys):
        return np.full(len(keys), -1, np.int64)
    want = be64(keys)
    order = np.argsort(want)
    at = np.empty(len(keys), np.int64)
    at[order] = np.searchsorted(sorted_k8, want[order], "left")
    at = np.minimum(at, len(sorted_keys) - 1)
    same = np.all(sorted_keys[at] == keys, axis=1)
    out = np.where(same, at, -1).astype(np.int64)
    for i in np.nonzero(~same & (sorted_k8[at] == want))[0]:
        j = at[i]
        while j < len(sorted_keys) and sorted_k8[j] == want[i]:
            if bytes(sorted_keys[j]) == bytes(keys[i]):
                out[i] = j
                break
            j += 1
    return out


def index_entries(raw):
    if len(raw) < 0x28:
        raise LocalError("an index cut short")
    version, _, extra, size_bytes, offset_bytes, key_bytes, offset_bits = struct.unpack_from("<HBBBBBB", raw, 8)
    entries = struct.unpack_from("<I", raw, 0x20)[0]
    if (version, extra, size_bytes, offset_bytes, key_bytes) != (7, 0, 4, 5, 9) or entries % 18 or 0x28 + entries > len(raw):
        raise LocalError("an index not of version 7 as documented")
    rows = np.frombuffer(raw, np.uint8, entries, 0x28).reshape(-1, 18)
    place = np.zeros(len(rows), np.uint64)
    for i in range(9, 14):
        place = (place << np.uint64(8)) | rows[:, i].astype(np.uint64)
    archive = (place >> np.uint64(offset_bits)).astype(np.uint16)
    offset = (place & np.uint64((1 << offset_bits) - 1)).astype(np.uint32)
    size = np.ascontiguousarray(rows[:, 14:18]).view("<u4").ravel().astype(np.uint32)
    return rows[:, :9].copy(), archive, offset, size


def newest_indices(folder):
    newest = {}
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".idx" or len(stem) != 10:
            continue
        try:
            bucket, version = int(stem[:2], 16), int(stem[2:], 16)
        except ValueError:
            continue
        if bucket not in newest or version > newest[bucket][0]:
            newest[bucket] = (version, os.path.join(folder, name))
    return {b: path for b, (_, path) in newest.items()}


def bucket(key):
    x = 0
    for b in key[:9]:
        x ^= b
    return (x & 0xF) ^ (x >> 4)


def locate(folder, ekey):
    found = newest_indices(folder)
    if len(found) != 16:
        raise LocalError(f"{len(found)} index buckets, not 16")
    keys, archive, offset, size = index_entries(gamefiles.read_part(found[bucket(ekey)]))
    rows = np.nonzero(np.all(keys == np.frombuffer(ekey[:9], np.uint8), axis=1))[0]
    if not len(rows):
        raise Missing(f"{ekey.hex()} isn't in the indices")
    return int(archive[rows[0]]), int(offset[rows[0]]), int(size[rows[0]])


class Index:

    def __init__(self, parts):
        keys = np.concatenate([p[0] for p in parts])
        k8 = be64(keys)
        order = np.lexsort((keys[:, 8], k8))
        keys, k8 = keys[order], k8[order]
        first = np.ones(len(keys), bool)
        first[1:] = (k8[1:] != k8[:-1]) | (keys[1:, 8] != keys[:-1, 8])
        order = order[first]
        self.keys, self.k8 = keys[first], k8[first]
        self.archive = np.concatenate([p[1] for p in parts])[order]
        self.offset = np.concatenate([p[2] for p in parts])[order]
        self.size = np.concatenate([p[3] for p in parts])[order]

    @classmethod
    def load(cls, folder):
        found = newest_indices(folder)
        if len(found) != 16:
            raise LocalError(f"{len(found)} index buckets, not 16")
        return cls([index_entries(gamefiles.read_part(path)) for _, path in sorted(found.items())])

    def find(self, keys):
        return find_rows(self.keys, self.k8, np.ascontiguousarray(keys[:, :9]))


def encoding_keys(content):
    if not isinstance(content, Content):
        content = Content(content)
    head = content.take(22)
    if len(head) < 22 or head[:2] != b"EN" or head[2] != 1 or head[3] != 16 or head[4] != 16:
        raise LocalError("an encoding file not as documented")
    page = int.from_bytes(head[5:7], "big") * 1024
    pages = int.from_bytes(head[9:13], "big")
    if page < 38:
        raise LocalError("an encoding file cut short")
    content.skip(int.from_bytes(head[18:22], "big") + pages * 32)
    ckeys, ekeys = [], []
    for first in range(0, pages, ENCODING_BATCH):
        n = min(ENCODING_BATCH, pages - first)
        raw = content.take(n * page)
        if len(raw) != n * page:
            raise LocalError("an encoding file cut short")
        ck, ek = encoding_pages(np.frombuffer(raw, np.uint8).reshape(n, page))
        ckeys += ck
        ekeys += ek
    content.finish()
    ck = np.concatenate(ckeys) if ckeys else np.zeros((0, 16), np.uint8)
    ek = np.concatenate(ekeys) if ekeys else np.zeros((0, 9), np.uint8)
    del ckeys, ekeys
    k8 = be64(ck)
    if len(ck) > 1 and not np.all(k8[1:] > k8[:-1]):
        order = np.lexsort((be64(ck[:, 8:]), k8))
        ck, ek = ck[order], ek[order]
    return np.ascontiguousarray(ck), np.ascontiguousarray(ek)


def encoding_pages(grid):
    pages, page = grid.shape
    per = page // 38
    rows = grid[:, :per * 38].reshape(pages, per, 38)
    single = np.cumprod(rows[:, :, 0] == 1, axis=1).astype(bool)
    run = single.sum(axis=1)
    after = np.where(run < per, grid[np.arange(pages), np.minimum(run, per - 1) * 38], 0)
    plain = (run == per) | (after == 0)
    take = single & plain[:, None]
    ckeys, ekeys = [rows[:, :, 6:22][take]], [rows[:, :, 22:31][take]]
    for p in np.nonzero(~plain)[0]:
        body, i = grid[p].tobytes(), 0
        while i + 22 <= page and body[i]:
            n = body[i]
            if i + 22 + 16 * n > page:
                raise LocalError("an encoding page entry past its page")
            ckeys.append(np.frombuffer(body, np.uint8, 16, i + 6).reshape(1, 16))
            ekeys.append(np.frombuffer(body, np.uint8, 9, i + 22).reshape(1, 9))
            i += 22 + 16 * n
    return ckeys, ekeys


def root_entries(content, locale):
    if not isinstance(content, Content):
        content = Content(content)
    head = content.take(12)
    if head[:4] != b"TSFM" or len(head) < 12:
        raise LocalError("a root file not of the MFST form")
    size, version = struct.unpack_from("<II", head, 4)
    if size == 0x18 and version in (1, 2):
        content.skip(size - 12)
    else:
        version = 1
    fids, ranks, keys = [], [], []
    while not content.at_end():
        if version == 2:
            block = content.take(17)
            if len(block) < 17:
                raise LocalError("a root block header cut short")
            count, flags_locale, f1, f2 = struct.unpack_from("<IIII", block)
            flags = f1 | f2 | (block[16] << 17)
        else:
            block = content.take(12)
            if len(block) < 12:
                raise LocalError("a root block header cut short")
            count, flags, flags_locale = struct.unpack_from("<III", block)
        names = 0 if flags & NO_NAME_HASH else 8
        if not (flags_locale & locale and count):
            if content.skip(count * (4 + 16 + names)) < count * (4 + 16 + names):
                raise LocalError("a root block past the file's end")
            continue
        body = content.take(count * (4 + 16))
        if len(body) < count * 20 or content.skip(count * names) < count * names:
            raise LocalError("a root block past the file's end")
        fids.append(np.cumsum(np.frombuffer(body, "<i4", count).astype(np.int64) + 1) - 1)
        ranks.append(np.full(count, 1 if flags & LOW_VIOLENCE else 0, np.int8))
        keys.append(np.frombuffer(body, np.uint8, 16 * count, 4 * count).reshape(count, 16))
    content.finish()
    if not fids:
        return np.zeros(0, np.int64), np.zeros((0, 16), np.uint8)
    fid, rank, keys = np.concatenate(fids), np.concatenate(ranks), np.concatenate(keys)
    order = np.lexsort((np.arange(len(fid)), rank, fid))
    fid, keys = fid[order], keys[order]
    first = np.ones(len(fid), bool)
    first[1:] = fid[1:] != fid[:-1]
    return fid[first], np.ascontiguousarray(keys[first])



class Install:

    def __init__(self, top, info, fids, ckeys, ekeys, archive, offset, size):
        self.top, self.data = top, os.path.join(top, "Data", "data")
        self.version, self.build_key = info.get("Version"), info.get("Build Key")
        self.fids, self.ckeys, self.ekeys = fids, ckeys, ekeys
        self.archive, self.offset, self.size = archive, offset, size

    @classmethod
    def load(cls, top, info):
        key = info.get("Build Key") or ""
        text = gamefiles.read_part(os.path.join(top, "Data", "config", key[:2], key[2:4], key)).decode("utf-8", "replace")
        cfg = config(text)
        if len(cfg.get("encoding", ())) < 2 or not cfg.get("root"):
            raise LocalError("the build config names no encoding or root file")
        data = os.path.join(top, "Data", "data")
        ce_ckey, ce_ekey = (bytes.fromhex(k) for k in cfg["encoding"][:2])
        with stream(data, ce_ekey, ce_ckey) as enc:
            ck, ek = encoding_keys(enc)
        ck8 = be64(ck)
        root_ckey = np.frombuffer(bytes.fromhex(cfg["root"][0]), np.uint8).reshape(1, 16)
        at = find_rows(ck, ck8, root_ckey)[0]
        if at < 0:
            raise LocalError("the encoding file doesn't name the root file")
        with stream(data, bytes(ek[at]), bytes(root_ckey[0])) as root:
            fids, ckeys = root_entries(root, locale_flag(info.get("Tags", "")))
        at = find_rows(ck, ck8, ckeys)
        known = at >= 0
        fids, ckeys, ekeys = fids[known], ckeys[known], ek[at[known]]
        del ck, ek, ck8, at, known
        index = Index.load(data)
        where = index.find(ekeys)
        here = where >= 0
        where = where[here]
        return cls(top, info, fids[here], np.ascontiguousarray(ckeys[here]), np.ascontiguousarray(ekeys[here]),
                   index.archive[where], index.offset[where], index.size[where])

    def __len__(self):
        return len(self.fids)

    def keys_of(self, fids):
        want = np.asarray(sorted({int(f) for f in fids}), np.int64)
        at = np.minimum(np.searchsorted(self.fids, want), max(len(self.fids) - 1, 0))
        here = (self.fids[at] == want) if len(self.fids) else np.zeros(len(want), bool)
        return {int(f): self.ckeys[i].tobytes() for f, i in zip(want[here], at[here])}

    def read(self, fid):
        i = self.row(fid)
        return bytes(entry(self.data, int(self.archive[i]), int(self.offset[i]), int(self.size[i]),
                           self.ekeys[i].tobytes(), self.ckeys[i].tobytes()))

    def read_clear(self, fid, keys=None):
        i = self.row(fid)
        return clear_entry(self.data, int(self.archive[i]), int(self.offset[i]), int(self.size[i]),
                           self.ekeys[i].tobytes(), self.ckeys[i].tobytes(), keys)

    def row(self, fid):
        i = int(np.searchsorted(self.fids, fid))
        if i >= len(self.fids) or self.fids[i] != fid:
            raise Missing(f"file {fid} isn't in the install")
        return i


def entry_start(first, size, ekey):
    if first[:4] == b"BLTE":
        return 0
    head = first[:ENTRY_HEAD]
    if size < ENTRY_HEAD or (any(head) and (head[:16][::-1][:9] != ekey[:9] or struct.unpack_from("<I", head, 16)[0] != size)):
        raise Missing("its place holds another entry")
    return ENTRY_HEAD


def entry(folder, archive, offset, size, ekey, ckey):
    raw = gamefiles.read_part(os.path.join(folder, f"data.{archive:03d}"), offset, size)
    if len(raw) != size:
        raise Missing("its entry is cut short")
    content = blte(memoryview(raw)[entry_start(raw, size, ekey):])
    if hashlib.md5(content).digest() != ckey:
        raise LocalError("its content isn't what root names")
    return content


def clear_entry(folder, archive, offset, size, ekey, ckey, keys=None):
    raw = gamefiles.read_part(os.path.join(folder, f"data.{archive:03d}"), offset, size)
    if len(raw) != size:
        raise Missing("its entry is cut short")
    view = memoryview(raw)[entry_start(raw, size, ekey):]
    head, table = blte_table(view)
    if table is None:
        content = inflate(view[8:], None, 0, keys)
        if hashlib.md5(content).digest() != ckey:
            raise LocalError("its content isn't what root names")
        return bytes(content), []
    width = 24 if view[8] == 0x0F else 40
    out, zeros, at, pos = bytearray(), [], head, 0
    for n, (raw_size, logical) in enumerate(table):
        block = view[at:at + raw_size]
        at += raw_size
        if hashlib.md5(block).digest() != bytes(view[12 + n * width + 8:12 + n * width + 24]):
            raise LocalError("a BLTE block isn't what its checksum says")
        try:
            out += inflate(block, logical, n, keys)
        except Encrypted:
            out += bytes(logical)
            zeros.append((pos, pos + logical))
        pos += logical
    if at != len(view):
        raise LocalError("BLTE blocks not the stream's length")
    if not zeros:
        if hashlib.md5(out).digest() != ckey:
            raise LocalError("its content isn't what root names")
    elif hashlib.md5(view[:head]).digest()[:len(ekey)] != ekey:
        raise LocalError("its BLTE header isn't what its encoding key says")
    return bytes(out), zeros


def stream(folder, ekey, ckey):
    return Stream(folder, *locate(folder, ekey), ekey, ckey)



class Held:

    def __init__(self, stamp=None, info=None, install=None, failed=None, at=0.0):
        self.stamp, self.info, self.install, self.failed, self.at = stamp, info, install, failed, at


_lock = threading.Lock()
_count_lock = threading.Lock()
_counts = dict.fromkeys(KINDS, 0)
_held = Held()
_said = {"error": None}


def counts():
    with _count_lock:
        return dict(_counts)


def last_error():
    return _said["error"]


def _count(kind, error=None):
    with _count_lock:
        _counts[kind] += 1
    if error is not None:
        _said["error"] = f"{type(error).__name__}: {error}"[:300]


def game_top():
    return os.path.dirname(os.path.normpath(game.data_folder()))


def _stamp(path):
    st = os.stat(path)
    return path, st.st_mtime_ns, st.st_size


def installed(build):
    global _held
    top = game_top()
    stamp = _stamp(os.path.join(top, ".build.info"))
    held = _held
    if held.stamp != stamp:
        with _lock:
            if _held.stamp != stamp:
                text = gamefiles.read_part(stamp[0]).decode("utf-8", "replace")
                _held = Held(stamp, build_info(text, game.lead_product()))
            held = _held
    if held.info.get("Version") != build:
        return None
    if held.install is not None:
        return held.install
    with _lock:
        held = _held
        if held.info.get("Version") != build:
            return None
        if held.install is not None:
            return held.install
        if held.failed is not None and time.monotonic() - held.at < RETRY:
            raise held.failed
        try:
            install = Install.load(top, held.info)
        except (LocalError, OSError, ValueError) as e:
            _held = Held(held.stamp, held.info, failed=e, at=time.monotonic())
            raise
        _held = Held(held.stamp, held.info, install)
        return install


def content_keys(fids, build):
    if os.environ.get(OFF):
        return None
    try:
        install = installed(str(build))
    except Exception as e:
        _said["error"] = f"{type(e).__name__}: {e}"[:300]
        return None
    return None if install is None else install.keys_of(fids)


def files_print(fids, build):
    fids = sorted({int(f) for f in fids})
    keys = content_keys(fids, build) or {}
    parts = [f"{f}:{keys[f].hex()}" if f in keys else f"{f}@{build}" for f in fids]
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def read(fid, build):
    if os.environ.get(OFF):
        return None
    try:
        install = installed(str(build))
        if install is None:
            _count("build")
            return None
        data = install.read(int(fid))
    except Encrypted:
        _count("encrypted")
        return None
    except Missing:
        _count("missing")
        return None
    except Exception as e:
        _count("error", e)
        return None
    _count("local")
    return data


def read_clear(fid, build, keys=None):
    if os.environ.get(OFF):
        return None
    try:
        install = installed(str(build))
        if install is None:
            _count("build")
            return None
        got = install.read_clear(int(fid), keys)
    except Encrypted:
        _count("encrypted")
        return None
    except Missing:
        _count("missing")
        return None
    except Exception as e:
        _count("error", e)
        return None
    _count("local")
    return got
