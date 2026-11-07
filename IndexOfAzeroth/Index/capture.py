# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import ctypes
import ctypes.wintypes as wt
import os

import game
from protocol import ANCHOR, MAX_BLOCKS, MAX_ROWS, StripError, decode_blocks, frame_rows, near

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32")

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    pass

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
SCAN_WIDTH = 8 * MAX_BLOCKS
SCAN_HEIGHT = 8 * MAX_ROWS

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def process_name(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_wow_window():
    found, programs = [], game.client_exes()

    def visit(hwnd, _):
        name = user32.IsWindowVisible(hwnd) and process_name(hwnd)
        if name in programs:
            rect = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            if rect.right > 0 and rect.bottom > 0:
                found.append((programs.index(name), len(found), hwnd))
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return min(found)[2] if found else None


class ScreenGrab:

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.bitmap = gdi32.CreateCompatibleBitmap(self.screen_dc, width, height)
        gdi32.SelectObject(self.mem_dc, self.bitmap)
        self.info = BITMAPINFOHEADER()
        self.info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        self.info.biWidth, self.info.biHeight = width, -height
        self.info.biPlanes, self.info.biBitCount = 1, 32
        self.buffer = ctypes.create_string_buffer(width * height * 4)

    def grab(self, x, y):
        gdi32.BitBlt(self.mem_dc, 0, 0, self.width, self.height, self.screen_dc, x, y, SRCCOPY)
        gdi32.GetDIBits(self.mem_dc, self.bitmap, 0, self.height, self.buffer, ctypes.byref(self.info), DIB_RGB_COLORS)
        return self.buffer.raw

    def close(self):
        gdi32.DeleteObject(self.bitmap)
        gdi32.DeleteDC(self.mem_dc)
        user32.ReleaseDC(None, self.screen_dc)


def pixel(raw, width, x, y):
    i = (y * width + x) * 4
    return raw[i + 2], raw[i + 1], raw[i]


def read_blocks(raw, width, height):
    if not near(pixel(raw, width, 0, 0), ANCHOR[0]):
        raise StripError("anchor not found")
    size = 1
    while size < width and near(pixel(raw, width, size, 0), ANCHOR[0]):
        size += 1
    if size > 8 or size > height:
        raise StripError(f"The strip's anchor block is {size} px wide, and the reader expects 2-8")
    mid = size // 2
    count = min(MAX_BLOCKS, width // size)
    colors = [pixel(raw, width, i * size + mid, mid) for i in range(count)]
    rows = min(frame_rows(colors), height // size) if count == MAX_BLOCKS else 1
    for row in range(1, rows):
        y = row * size + mid
        colors += [pixel(raw, width, i * size + mid, y) for i in range(MAX_BLOCKS)]
    return size, colors


class StripReader:
    def __init__(self):
        self.hwnd = None
        self.grabber = ScreenGrab(SCAN_WIDTH, SCAN_HEIGHT)

    def read(self):
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            self.hwnd = find_wow_window()
            if not self.hwnd:
                raise StripError("WoW window not found")
        if user32.IsIconic(self.hwnd):
            raise StripError("WoW is minimized")
        origin = wt.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        raw = self.grabber.grab(origin.x, origin.y)
        size, colors = read_blocks(raw, SCAN_WIDTH, SCAN_HEIGHT)
        seq, payload, adjusted = decode_blocks(colors)
        return seq, payload, {"block": size, "adjusted": adjusted}


class WindowRegion:

    def __init__(self):
        self.hwnd = None
        self.grabber = None

    def grab(self, x, y, w, h):
        if not self.hwnd or not user32.IsWindow(self.hwnd):
            self.hwnd = find_wow_window()
        if not self.hwnd or user32.IsIconic(self.hwnd):
            return None
        if not self.grabber or (self.grabber.width, self.grabber.height) != (w, h):
            if self.grabber:
                self.grabber.close()
            self.grabber = ScreenGrab(w, h)
        origin = wt.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        return self.grabber.grab(origin.x + x, origin.y + y)
