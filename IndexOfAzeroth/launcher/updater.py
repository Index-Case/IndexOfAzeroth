# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import base64
import binascii
import contextlib
import hashlib
import json
import os
import re
import shutil
import urllib.request
import zipfile
import zlib
from collections import namedtuple

import ed25519

REPO = "Index-Case/IndexOfAzeroth"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOADS = f"https://github.com/{REPO}/releases/download/"
MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "manifest.json.sig"
PUBLIC_KEY = base64.b64decode("qiixCysF410BwNtjZI7fFEHpmde4MytuUc+1GKL8Ewg=")
FORMAT = 2
WORK = ".update"
CHUNK = 1 << 20
MAX_LIST = 64 << 20
HEX64 = re.compile(r"[0-9a-f]{64}")
OURS = (MANIFEST_NAME, SIGNATURE_NAME, WORK)
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([a-z]+))?")
VERSION_READ = re.compile(r"\s*v?(\d+(?:\.\d+)*)(?:-([A-Za-z]+))?")


def version_key(text):
    m = VERSION_READ.match(text or "")
    if not m:
        return ()
    numbers = [int(n) for n in m.group(1).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    label = (m.group(2) or "").lower()
    return (tuple(numbers), 0 if label else 1, label)

Entry = namedtuple("Entry", "path size sha256 pack")
Pack = namedtuple("Pack", "name size sha256 url files")


class UpdateRefused(Exception):
    pass


class GameRunning(Exception):
    pass


class Manifest:
    def __init__(self, version, changes, files, raw, signature, packs):
        self.version = version
        self.changes = changes
        self.files = files
        self.packs = packs
        self.raw = raw
        self.signature = signature

    @staticmethod
    def total_size(items):
        return sum(e.size for e in items)


def http_get(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "IndexOfAzeroth", **(headers or {})})
    return urllib.request.urlopen(request, timeout=60)


def _read_all(response, limit=MAX_LIST):
    with contextlib.closing(response):
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateRefused("the update list is too large")
    return data


def _safe_path(path):
    parts = path.split("/")
    return (isinstance(path, str) and path and "\\" not in path and ":" not in path and parts[0] not in OURS
            and all(p not in ("", ".", "..") for p in parts))


def verify_manifest(raw, signature, public_key=PUBLIC_KEY):
    try:
        sig = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise UpdateRefused("the update list's signature is unreadable") from None
    if not ed25519.verify(public_key, raw, sig):
        raise UpdateRefused("the update list's signature doesn't match")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise UpdateRefused("the update list is unreadable") from None
    if not (isinstance(body, dict) and body.get("format") == FORMAT and isinstance(body.get("version"), str)
            and isinstance(body.get("changes"), str) and isinstance(body.get("files"), dict)
            and isinstance(body.get("packs"), dict)):
        raise UpdateRefused("the update list has an unknown form")
    packs = {}
    for name, p in body["packs"].items():
        if not (_sized(p) and isinstance(p.get("url"), str) and p["url"].startswith(DOWNLOADS)):
            raise UpdateRefused(f"the update list's archive {name!r} is malformed")
        packs[name] = (p["size"], p["sha256"], p["url"])
    files = {}
    for path, f in body["files"].items():
        if not (_safe_path(path) and _sized(f) and isinstance(f.get("pack"), str) and f["pack"] in packs):
            raise UpdateRefused(f"the update list's entry for {path!r} is malformed")
        files[path] = Entry(path, f["size"], f["sha256"], f["pack"])
    return Manifest(body["version"], body["changes"], files, raw, sig, packs)


def _sized(f):
    return (isinstance(f, dict) and type(f.get("size")) is int and f["size"] >= 0 and isinstance(f.get("sha256"), str)
            and bool(HEX64.fullmatch(f["sha256"])))


def fetch_manifest(get=http_get, public_key=PUBLIC_KEY):
    try:
        release = json.loads(_read_all(get(LATEST_URL, {"Accept": "application/vnd.github+json"})).decode("utf-8"))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise UpdateRefused("the newest release can't be read") from None
    if MANIFEST_NAME not in assets or SIGNATURE_NAME not in assets:
        raise UpdateRefused("the newest release has no signed update list")
    raw = _read_all(get(assets[MANIFEST_NAME]))
    signature = _read_all(get(assets[SIGNATURE_NAME]))
    return verify_manifest(raw, signature, public_key)


def _local(install_dir, path):
    return os.path.join(install_dir, *path.split("/"))


def _sha256(file):
    h = hashlib.sha256()
    with open(file, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _matches(file, entry):
    return os.path.isfile(file) and os.path.getsize(file) == entry.size and _sha256(file) == entry.sha256


def installed_manifest(install_dir, public_key=PUBLIC_KEY):
    try:
        with open(os.path.join(install_dir, MANIFEST_NAME), "rb") as f:
            raw = f.read()
        with open(os.path.join(install_dir, SIGNATURE_NAME), "rb") as f:
            signature = f.read()
        return verify_manifest(raw, signature, public_key)
    except (OSError, UpdateRefused):
        return None


def files_to_fetch(install_dir, manifest, public_key=PUBLIC_KEY):
    old = installed_manifest(install_dir, public_key)
    out = []
    for path in sorted(manifest.files):
        entry = manifest.files[path]
        target = _local(install_dir, path)
        if not os.path.isfile(target) or os.path.getsize(target) != entry.size:
            out.append(entry)
            continue
        was = old.files.get(path) if old else None
        if was and was.sha256 == entry.sha256:
            continue
        if _sha256(target) != entry.sha256:
            out.append(entry)
    return out


def removed_files(install_dir, manifest, public_key=PUBLIC_KEY):
    old = installed_manifest(install_dir, public_key)
    if not old:
        return []
    return sorted(p for p in old.files if p not in manifest.files and os.path.isfile(_local(install_dir, p)))


def _staged(install_dir, path):
    return os.path.join(install_dir, WORK, "staging", *path.split("/"))


def downloads(manifest, entries):
    packs = {}
    for e in entries:
        if e.pack not in packs:
            size, sha256, url = manifest.packs[e.pack]
            packs[e.pack] = Pack(e.pack, size, sha256, url, [])
        packs[e.pack].files.append(e)
    return list(packs.values())


def needed(install_dir, manifest, public_key=PUBLIC_KEY):
    return downloads(manifest, files_to_fetch(install_dir, manifest, public_key))


def _take(opened, size, sha256, target, what, progress=None):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = target + ".part"
    h = hashlib.sha256()
    done = 0
    try:
        with contextlib.closing(opened()) as stream, open(part, "wb") as out:
            for block in iter(lambda: stream.read(CHUNK), b""):
                done += len(block)
                if done > size:
                    break
                h.update(block)
                out.write(block)
                if progress:
                    progress(done, size)
        if done != size or h.hexdigest() != sha256:
            raise UpdateRefused(f"{what} doesn't match the update list")
        os.replace(part, target)
    finally:
        if os.path.exists(part):
            os.remove(part)


def download_pack(pack, install_dir, get=http_get, progress=None):
    if all(_matches(_staged(install_dir, e.path), e) for e in pack.files):
        if progress:
            progress(pack.size, pack.size)
        return
    held = os.path.join(install_dir, WORK, "packs", pack.sha256 + ".zip")
    try:
        _take(lambda: get(pack.url), pack.size, pack.sha256, held, pack.name, progress)
        try:
            with zipfile.ZipFile(held) as z:
                for e in pack.files:
                    _take(lambda: z.open(e.path), e.size, e.sha256, _staged(install_dir, e.path), e.path)
        except (zipfile.BadZipFile, KeyError, NotImplementedError, RuntimeError, EOFError, zlib.error):
            raise UpdateRefused(f"{pack.name} can't be unpacked") from None
    finally:
        if os.path.exists(held):
            os.remove(held)


def _state_file(install_dir):
    return os.path.join(install_dir, WORK, "state.json")


def _read_state(install_dir):
    try:
        with open(_state_file(install_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_state(install_dir, state):
    file = _state_file(install_dir)
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(file + ".tmp", file)


def _move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)


def apply_update(install_dir, manifest, game_running, public_key=PUBLIC_KEY):
    if game_running():
        raise GameRunning("the game is running")
    if _read_state(install_dir):
        raise UpdateRefused("an earlier update waits for confirm_update or rollback_update")
    incoming = files_to_fetch(install_dir, manifest, public_key)
    for entry in incoming:
        if not _matches(_staged(install_dir, entry.path), entry):
            raise UpdateRefused(f"{entry.path} isn't downloaded or doesn't match the update list")
    removed = removed_files(install_dir, manifest, public_key)
    for name, data in ((MANIFEST_NAME, manifest.raw), (SIGNATURE_NAME, base64.b64encode(manifest.signature))):
        os.makedirs(os.path.dirname(_staged(install_dir, name)), exist_ok=True)
        with open(_staged(install_dir, name), "wb") as f:
            f.write(data)
    shutil.rmtree(os.path.join(install_dir, WORK, "backup"), ignore_errors=True)
    replaced = [e.path for e in incoming] + [MANIFEST_NAME, SIGNATURE_NAME]
    touched = replaced + removed
    existed = [p for p in touched if os.path.isfile(_local(install_dir, p))]
    _write_state(install_dir, {"state": "applying", "version": manifest.version, "touched": touched, "existed": existed})
    for path in touched:
        target = _local(install_dir, path)
        if os.path.isfile(target):
            _move(target, os.path.join(install_dir, WORK, "backup", *path.split("/")))
        if path in replaced:
            _move(_staged(install_dir, path), target)
    for kept in ("staging", "packs"):
        shutil.rmtree(os.path.join(install_dir, WORK, kept), ignore_errors=True)
    _write_state(install_dir, {"state": "trial", "version": manifest.version, "touched": touched, "existed": existed})


def confirm_update(install_dir):
    state = _read_state(install_dir)
    if not state or state.get("state") != "trial":
        return False
    shutil.rmtree(os.path.join(install_dir, WORK, "backup"), ignore_errors=True)
    os.remove(_state_file(install_dir))
    return True


def rollback_update(install_dir):
    state = _read_state(install_dir)
    if not state:
        return False
    existed = set(state.get("existed", []))
    for path in reversed(state.get("touched", [])):
        target = _local(install_dir, path)
        kept = os.path.join(install_dir, WORK, "backup", *path.split("/"))
        if os.path.isfile(kept):
            _move(kept, target)
        elif path not in existed and os.path.isfile(target):
            os.remove(target)
    shutil.rmtree(os.path.join(install_dir, WORK, "backup"), ignore_errors=True)
    shutil.rmtree(os.path.join(install_dir, WORK, "staging"), ignore_errors=True)
    os.remove(_state_file(install_dir))
    return True


def recover(install_dir):
    return "rolled back" if rollback_update(install_dir) else None
