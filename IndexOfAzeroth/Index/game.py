# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import ctypes
import ctypes.wintypes as wt
import glob
import os
import re
import string
import sys
import tempfile
import threading
import time
import gamefiles
import mainstores
import store
import storewriter
import words

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("WCC_GAME_CONFIG") or os.path.join(ROOT, "data", "game.json")
VERSION = re.compile(r"\d+(?:\.\d+)+")
CLIENT_EXES = ("WowB.exe", "Wow.exe", "WowClassic.exe", "WowT.exe", "WowClassicT.exe", "WowClassicB.exe")
BATTLENET_DB = r"%ProgramData%\Battle.net\Agent\product.db"
ADDON_HELD = os.path.join(ROOT, "addon", "IndexOfAzeroth")
SCAN_KEEP = 5.0
RECORDS_KEEP = 1.0
OFF = "WCC_NO_LIVE_GAME"
DEV_DIR = os.path.join(ROOT, "dev")
RELEASE_LIST = os.path.join(ROOT, "manifest.json")


class GameNotFound(RuntimeError):
    pass


def live_off():
    return bool(os.environ.get(OFF))


def in_temp(path):
    return os.path.normcase(os.path.realpath(path)).startswith(os.path.normcase(os.path.realpath(tempfile.gettempdir())) + os.sep)


def client_exe(folder):
    return next((exe for exe in CLIENT_EXES if os.path.isfile(os.path.join(folder, exe))), None)


def valid(folder):
    return bool(folder) and (not live_off() or in_temp(folder)) and bool(client_exe(folder)) \
        and os.path.isfile(build_info_path(folder))


def build_info_path(folder):
    return os.path.join(os.path.dirname(os.path.normpath(folder)), ".build.info")


def build_rows(text):
    rows = [line.split("|") for line in text.splitlines() if line.strip()]
    head = [h.split("!")[0] for h in rows[0]] if rows else []
    return [dict(zip(head, row)) for row in rows[1:]]


def norm(folder):
    return os.path.normcase(os.path.realpath(folder))



class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def running_folders():
    if live_off():
        return []
    programs = {exe.lower() for exe in CLIENT_EXES}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (None, wt.HANDLE(-1).value):
        return []
    found = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in programs:
                handle = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
                folder = ""
                if handle:
                    try:
                        buf = ctypes.create_unicode_buffer(1024)
                        size = wt.DWORD(len(buf))
                        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                            folder = os.path.dirname(buf.value)
                    finally:
                        kernel32.CloseHandle(handle)
                found.append(folder)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return found


def running():
    return bool(running_folders())


def writes_game(root=None):
    return not os.path.isfile(os.path.join(root or ROOT, ".git"))


def dev_hooks():
    path = os.path.join(DEV_DIR, "serve.py")
    return path if os.path.isfile(path) and not os.path.isfile(RELEASE_LIST) else None


def console_python():
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "pythonw.exe":
        beside = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(beside):
            return beside
    return exe


def dev_checkout():
    return dev_hooks() is not None


def may_write(path, root=None):
    return writes_game(root) or in_temp(path)


def game_addons_dir():
    path = addons_dir()
    if not may_write(path):
        raise GameNotFound("a worktree's server never writes the game's addon folder")
    return path


def addon_copy():
    for folder in (os.environ.get("WCC_ADDON"), load_config().get("indexOfAzerothSource"), ADDON_HELD):
        if folder and os.path.isdir(folder):
            return folder
    try:
        installed = os.path.join(addons_dir(), "IndexOfAzeroth")
    except GameNotFound:
        return None
    if os.path.islink(installed) or os.path.isjunction(installed):
        target = os.readlink(installed).removeprefix("\\\\?\\")
        if os.path.isdir(target):
            return target
    return None


def addon_to_write():
    if os.environ.get("WCC_ADDON"):
        return os.environ["WCC_ADDON"]
    return addon_copy() if writes_game() else None


_memo_lock = threading.Lock()
_looked = threading.Condition(_memo_lock)
_scan = {"at": None, "folders": []}
_records = {"at": None, "key": None}
_found = {"key": None, "tops": None, "looking": False, "round": 0}
_resolved = {"key": None, "infos": (), "out": None}
_versions = {}


def seen_running():
    with _memo_lock:
        if _scan["at"] is not None and time.monotonic() - _scan["at"] < SCAN_KEEP:
            return list(_scan["folders"])
    folders = running_folders()
    with _memo_lock:
        _scan.update(at=time.monotonic(), folders=list(folders))
    return list(folders)


def forget():
    with _memo_lock:
        _scan.update(at=None, folders=[])
        _records.update(at=None, key=None)
        _found.update(key=None, tops=None, round=_found["round"] + 1)
        _resolved.update(key=None, out=None)
        _versions.clear()



def proto_fields(data):
    out, at, end = [], 0, len(data)

    def varint():
        nonlocal at
        value = shift = 0
        while True:
            if at >= end or shift > 63:
                raise ValueError("a varint runs past the message")
            byte = data[at]
            at += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value
            shift += 7
    while at < end:
        key = varint()
        number, kind = key >> 3, key & 7
        if kind == 0:
            out.append((number, varint()))
        elif kind == 2:
            size = varint()
            if at + size > end:
                raise ValueError("a field runs past the message")
            out.append((number, data[at:at + size]))
            at += size
        elif kind in (1, 5):
            at += 8 if kind == 1 else 4
        else:
            raise ValueError(f"field {number} has wire type {kind}")
    if at > end:
        raise ValueError("a fixed field runs past the message")
    return out


def battlenet_installs():
    path = os.path.expandvars(BATTLENET_DB)
    if live_off() and not in_temp(path):
        return []
    try:
        records = proto_fields(gamefiles.read_part(path))
    except (OSError, ValueError):
        return []
    out = []
    for number, install in records:
        if number != 1 or not isinstance(install, bytes):
            continue
        try:
            fields = dict(proto_fields(install))
            settings = dict(proto_fields(fields.get(3, b"")))
            product, top, sub = (v.decode("utf-8") if isinstance(v, bytes) else None
                                 for v in (fields.get(2), settings.get(1), settings.get(13)))
        except (ValueError, TypeError, UnicodeDecodeError):
            continue
        if product and top:
            top = os.path.normpath(top)
            out.append({"product": product, "top": top, "folder": os.path.join(top, sub) if sub else None})
    return out


def from_battlenet():
    return [i["top"] for i in battlenet_installs()]


def from_registry():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft") as k:
            return [winreg.QueryValueEx(k, "InstallPath")[0]]
    except OSError:
        return []


def fixed_drives():
    kernel32 = ctypes.WinDLL("kernel32")
    mask = kernel32.GetLogicalDrives()
    return [f"{d}:\\" for i, d in enumerate(string.ascii_uppercase) if mask >> i & 1 and kernel32.GetDriveTypeW(f"{d}:\\") == 3]


def install_top(path):
    path = os.path.normpath(path.strip().strip('"'))
    return next((top for top in (path, os.path.dirname(path)) if os.path.isfile(os.path.join(top, ".build.info"))
                 and (not live_off() or in_temp(top))), None)


def looked_on():
    if live_off():
        return None
    with _memo_lock:
        if _records["at"] is not None and time.monotonic() - _records["at"] < RECORDS_KEEP:
            return _records["key"]
    key = (tuple(fixed_drives()), store.stamp(os.path.expandvars(BATTLENET_DB)), tuple(from_registry()),
           tuple(sorted({os.path.normcase(f) for f in seen_running() if f})))
    with _memo_lock:
        _records.update(at=time.monotonic(), key=key)
    return key


def candidates():
    if live_off():
        return []
    key = looked_on()
    with _looked:
        while _found["key"] != key or _found["tops"] is None:
            if not _found["looking"]:
                break
            _looked.wait()
        else:
            return list(_found["tops"])
        _found["looking"], begun = True, _found["round"]
    tops = None
    try:
        tops = look_over()
    finally:
        with _looked:
            if tops is not None and _found["round"] == begun:
                _found.update(key=key, tops=tops)
            _found["looking"] = False
            _looked.notify_all()
    return list(tops)


def look_over():
    paths = [f for f in running_folders() if f] + from_battlenet() + from_registry()
    for drive in fixed_drives():
        paths += [os.path.join(drive, "World of Warcraft"), os.path.join(drive, "Program Files (x86)", "World of Warcraft"),
                  os.path.join(drive, "Program Files", "World of Warcraft"), os.path.join(drive, "Games", "World of Warcraft"),
                  *glob.glob(os.path.join(drive, "*", "World of Warcraft")), *glob.glob(os.path.join(drive, "*", "*", "World of Warcraft"))]
    seen, out = set(), []
    for p in paths:
        top = p and install_top(p)
        if top and norm(top) not in seen:
            seen.add(norm(top))
            out.append(top)
    return out



def product_of(folder):
    try:
        text = gamefiles.read_part(os.path.join(folder, ".flavor.info")).decode("utf-8")
        named = [line.strip() for line in text.splitlines() if line.strip()][1:2]
        if named:
            return named[0]
    except OSError:
        pass
    recorded = next((i["product"] for i in battlenet_installs() if i["folder"] and norm(i["folder"]) == norm(folder)), None)
    if recorded:
        return recorded
    try:
        listed = {r.get("Product") for r in build_rows(gamefiles.read_part(build_info_path(folder)).decode("utf-8"))}
    except OSError:
        return None
    return listed.pop() if len(listed) == 1 else None


def clients_at(top):
    try:
        rows = build_rows(gamefiles.read_part(os.path.join(top, ".build.info")).decode("utf-8"))
        names = sorted(os.listdir(top))
    except OSError:
        return []
    folders = {}
    for name in names:
        folder = os.path.join(top, name)
        product = os.path.isdir(folder) and valid(folder) and product_of(folder)
        if product:
            folders.setdefault(product, folder)
    lead, out = load_config().get("lead"), []
    for row in rows:
        product = row.get("Product")
        if product in folders and all(c["product"] != product for c in out):
            out.append({"product": product, "folder": folders[product], "exe": client_exe(folders[product]),
                        "build": row.get("Version"), "lead": product == lead})
    return out


def install_tops():
    seen, out = set(), []
    for path in candidates() + [load_config().get("folder") or ""]:
        top = install_top(path)
        if top and norm(top) not in seen:
            seen.add(norm(top))
            out.append(top)
    return out


def clients():
    return sorted((c for top in install_tops() for c in clients_at(top)), key=lambda c: not c["lead"])


def client_in(folder):
    top = valid(folder) and install_top(folder)
    return next((c for c in clients_at(top) if norm(c["folder"]) == norm(folder)), None) if top else None



def config_path():
    return mainstores.standing(CONFIG)


def load_config():
    return store.load_json(config_path(), {})


def save_config(cfg):
    storewriter.save_json_later(CONFIG, cfg)
    with _memo_lock:
        _resolved.update(key=None, out=None)


def settled_on(infos):
    return store.stamp(config_path()), looked_on(), tuple(store.stamp(path) for path in infos)


def _settled():
    with _memo_lock:
        infos, key, out = _resolved["infos"], _resolved["key"], _resolved["out"]
    if out is not None and settled_on(infos) == key:
        return out
    infos = tuple(os.path.join(top, ".build.info") for top in install_tops())
    key = settled_on(infos)
    out = _resolve()
    with _memo_lock:
        _resolved.update(key=key, infos=infos, out=out)
    return out


def version_key(build):
    return tuple(map(int, build.split("."))) if isinstance(build, str) and VERSION.fullmatch(build) else ()


def build_number(client):
    last = (client.get("build") or "").rsplit(".", 1)[-1]
    return int(last) if last.isdigit() else -1


def first_lead(found):
    if dev_checkout():
        return max(found, key=build_number, default=None)
    return found[0] if len(found) == 1 else None


def _resolve():
    cfg = load_config()
    named, kept, lead = client_in(cfg.get("folder")), cfg.get("lead"), None
    if named and named["product"] == kept:
        lead = named
    elif kept:
        near = clients_at(install_top(named["folder"])) if named else []
        lead = (next((c for c in near if c["product"] == kept), None)
                or next((c for c in clients() if c["product"] == kept), None))
    else:
        lead = first_lead(clients())
        if lead:
            save_config({**cfg, "lead": lead["product"]})
    return named or lead, lead


def install(folder):
    client = client_in(folder)
    if client:
        save_config({**load_config(), "lead": client["product"], "folder": client["folder"]})
    return client


def tied():
    return _settled()[0]


def folder():
    tied_now = tied()
    if not tied_now:
        data_folder()
    return tied_now["folder"]


def data_folder():
    lead = _settled()[1]
    if lead:
        return lead["folder"]
    kept = load_config().get("lead")
    if kept:
        raise GameNotFound(words.say("page.client.lead-missing", {"product": kept}))
    if clients():
        raise GameNotFound(words.say("page.client.several"))
    raise GameNotFound(words.say("page.client.none"))


def lead_product():
    folder_now = data_folder()
    product = product_of(folder_now)
    if not product:
        raise GameNotFound(f"The launcher's records name no product for {folder_now}")
    return product


def client_exes():
    try:
        first = (tied() or {}).get("exe")
    except OSError:
        first = None
    return tuple(dict.fromkeys(exe.lower() for exe in (first, *CLIENT_EXES) if exe))


def addons_dir():
    return os.path.join(folder(), "Interface", "AddOns")


def wtf_dir():
    return os.path.join(folder(), "WTF")


def screenshots_dir():
    return os.path.join(folder(), "Screenshots")


def logs_dir():
    return os.path.join(folder(), "Logs")


def version_of(folder, product):
    path = build_info_path(folder)
    key = (path, store.stamp(path), product)
    with _memo_lock:
        if key in _versions:
            return _versions[key]
    rows = [r for r in build_rows(gamefiles.read_part(path).decode("utf-8")) if r.get("Product") == product]
    if not rows:
        raise GameNotFound(f"{product} not found in {path}")
    version = next((r for r in rows if r.get("Active") == "1"), rows[0]).get("Version")
    with _memo_lock:
        for old in [k for k in _versions if k[0] == path and k[1] != key[1]]:
            del _versions[old]
        _versions[key] = version
    return version


def installed_version():
    return version_of(data_folder(), lead_product())


def played_version():
    tied_now = tied()
    if not tied_now:
        folder()
    return version_of(tied_now["folder"], tied_now["product"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["install"] and len(sys.argv) == 3:
        recorded = install(sys.argv[2])
        storewriter.flush_later()
        print("recorded:", recorded)
        sys.exit(0 if recorded else 1)
    print("running:", running_folders())
    print("candidates:", candidates())
    print("tied:", tied())
    print("lead:", _settled()[1])
