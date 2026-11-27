# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import ctypes
import ctypes.wintypes as wt
import msvcrt
import os

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wt.HANDLE
_k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
_k32.CloseHandle.argtypes = [wt.HANDLE]
GENERIC_READ, SHARE_ALL, OPEN_EXISTING, NORMAL = 0x80000000, 0x7, 3, 0x80
_INVALID = wt.HANDLE(-1).value


def open_shared(path):
    handle = _k32.CreateFileW(path, GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, NORMAL, None)
    if handle in (None, _INVALID):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        _k32.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")


def read_part(path, at=0, size=-1):
    with open_shared(path) as f:
        f.seek(at)
        return f.read(size)
