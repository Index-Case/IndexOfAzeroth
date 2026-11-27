# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import json
import os
import subprocess
import uuid

PYTHON = "python/pythonw.exe"
START = "launcher/start.py"
ICON = "assets/index.ico"
DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"
FIELDS = ("target", "arguments", "folder", "icon")
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$shell = New-Object -ComObject WScript.Shell
$asked = $env:INDEX_SHORTCUTS | ConvertFrom-Json
foreach ($one in $asked) {
  if ($one.write) {
    $s = $shell.CreateShortcut($one.path)
    $s.TargetPath = $one.target
    $s.Arguments = $one.arguments
    $s.WorkingDirectory = $one.folder
    $s.IconLocation = $one.icon
    $s.Save()
  } elseif (Test-Path -LiteralPath $one.path) {
    $s = $shell.CreateShortcut($one.path)
    [Console]::WriteLine((@{path = $one.path; target = $s.TargetPath; arguments = $s.Arguments;
                           folder = $s.WorkingDirectory; icon = $s.IconLocation} | ConvertTo-Json -Compress))
  }
}
"""


def place(install, rel):
    return os.path.join(install, *rel.split("/"))


def wanted(install):
    return {"target": place(install, PYTHON), "arguments": f'"{place(install, START)}"', "folder": install,
            "icon": place(install, ICON) + ",0"}


def same(have, want):
    return have is not None and all(os.path.normcase(have.get(k) or "") == os.path.normcase(want[k]) for k in FIELDS)


def known_folder(guid):
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    folder = GUID()
    folder.bytes[:] = uuid.UUID(guid).bytes_le
    path = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(path)):
        raise OSError(f"no known folder {guid}")
    try:
        return path.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def places(name, known=known_folder):
    return [os.path.join(known(guid), f"{name}.lnk") for guid in (DESKTOP, PROGRAMS)]


def powershell(script):
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0",
                       "powershell.exe")
    return [exe, "-NoProfile", "-NonInteractive", "-Command", script]


def shell(asked):
    done = subprocess.run(powershell(SCRIPT), stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                          env={**os.environ, "INDEX_SHORTCUTS": json.dumps(asked)})
    if done.returncode:
        raise OSError(done.stderr.decode("utf-8", "replace").strip())
    return done.stdout.decode("utf-8").splitlines()


def read(paths):
    found = (json.loads(line) for line in shell([{"path": p, "write": False} for p in paths]) if line.strip())
    return {one["path"]: one for one in found}


def write(paths, want):
    shell([{"path": p, "write": True, **want} for p in paths])


def keep(install, name, read=read, write=write, places=places):
    want = wanted(install)
    try:
        paths = [p for p in places(name) if os.path.isdir(os.path.dirname(p))]
        have = read(paths)
        stale = [p for p in paths if not same(have.get(p), want)]
        if stale:
            write(stale, want)
        return stale
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
