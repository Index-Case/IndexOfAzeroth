# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import http.client
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
ON_CLOSE = {"dev": "keep", "release": "stop"}
FINISH_LOOK = 2.0
GRACE = 15.0
PORT = 8765
ANSWER = 15.0
FREED = 10.0
START = 90
WINDOW = (1600, 900)
MARGIN = 40

CHROMIUM = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "chromium.exe", "thorium.exe", "arc.exe"}

CHOICE = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{}"


def page_url(port=PORT):
    return f"http://localhost:{port}/"


def port_taken(port=PORT, host="127.0.0.1", make=socket.socket):
    s = make(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def answers(port=PORT, timeout=ANSWER, connect=http.client.HTTPConnection):
    conn = connect("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", "/api/state")
        conn.getresponse().close()
        return True
    except (OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def listener(port=PORT, run=subprocess.run):
    out = run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0] == "TCP" and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
            return int(parts[4])
    return None


def command_line(pid, run=subprocess.run):
    ps = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
    return (run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or "").strip()


def take_port(port=PORT, answer=answers, taken=port_taken, holder=listener, command=command_line, kill=os.kill,
              sleep=time.sleep):
    if not taken(port):
        return "free"
    if answer(port):
        return "up"
    pid = holder(port)
    if pid is not None:
        if os.path.normcase(os.path.join(ROOT, "server.py")) not in os.path.normcase(command(pid)):
            return "held"
        kill(pid, signal.SIGTERM)
    for _ in range(int(FREED / 0.1)):
        if not taken(port):
            return "free"
        sleep(0.1)
    return "held"


def start_server(port=PORT, popen=subprocess.Popen):
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    with open(os.path.join(ROOT, "data", "server.log"), "a", encoding="utf-8") as log:
        popen([pythonw if os.path.exists(pythonw) else sys.executable, os.path.join(ROOT, "server.py"), "--port", str(port)],
              cwd=ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
              creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
              | getattr(subprocess, "CREATE_NO_WINDOW", 0))


def launch(port=PORT, take=take_port, start=start_server, answer=answers, window=None, sleep=time.sleep, wait=START):
    got = take(port)
    if got == "free":
        start(port)
    for _ in range(int(wait)):
        if answer(port, 1):
            break
        sleep(1)
    (window or open_window)(page_url(port))
    return got


def exe_of(command):
    command = (command or "").strip()
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    low = command.lower()
    end = low.find(".exe")
    return command[:end + 4] if end >= 0 else command.split(" ", 1)[0]


def shell_says(what, proto="http"):
    try:
        import ctypes
        from ctypes import wintypes
        ask = ctypes.windll.shlwapi.AssocQueryStringW
        ask.argtypes = [ctypes.c_uint, ctypes.c_uint, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR,
                        ctypes.POINTER(wintypes.DWORD)]
        size = wintypes.DWORD(2048)
        buf = ctypes.create_unicode_buffer(size.value)
        verb = "open" if what == 1 else None
        if ask(0x1000, what, proto, verb, buf, ctypes.byref(size)) == 0:
            return buf.value or None
    except (OSError, AttributeError, ImportError):
        pass
    return None


def registry_says(proto="http", reg=None):
    try:
        reg = reg or __import__("winreg")
    except ImportError:
        return None, None
    progid = None
    for key in (CHOICE.format(proto) + r"\UserChoiceLatest\ProgId", CHOICE.format(proto) + r"\UserChoice"):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, key) as k:
                progid = reg.QueryValueEx(k, "ProgId")[0]
        except OSError:
            continue
        if progid:
            break
    if not progid:
        return None, None
    try:
        with reg.OpenKey(reg.HKEY_CLASSES_ROOT, progid + r"\shell\open\command") as k:
            return progid, reg.QueryValueEx(k, "")[0]
    except OSError:
        return progid, None


def default_browser(shell=shell_says, registry=registry_says):
    progid, command = shell(20), shell(1)
    if not command:
        progid, command = registry()
    exe = exe_of(command) if command else None
    return {"progid": progid, "exe": exe, "chromium": bool(exe) and os.path.basename(exe).lower() in CHROMIUM}


def work_area():
    try:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    except (OSError, AttributeError, ImportError):
        pass
    return None


def window_place(area=None, size=WINDOW, margin=MARGIN):
    if not area:
        return size[0], size[1], margin, margin
    left, top, right, bottom = area
    w = max(1, min(size[0], right - left - 2 * margin))
    h = max(1, min(size[1], bottom - top - 2 * margin))
    return w, h, left + (right - left - w) // 2, top + (bottom - top - h) // 2


def window_flags(place=None):
    w, h, x, y = place or window_place(work_area())
    return [f"--window-size={w},{h}", f"--window-position={x},{y}"]


def open_window(url=None, browser=None, popen=subprocess.Popen, tab=webbrowser.open, place=None):
    url = url or page_url()
    b = browser or default_browser()
    if b["chromium"] and b["exe"] and os.path.isfile(b["exe"]):
        try:
            popen([b["exe"], f"--app={url}", *window_flags(place)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            return "app"
        except OSError:
            pass
    tab(url)
    return "tab"


class Pages:

    def __init__(self, stop=None, grace=GRACE, timer=threading.Timer, busy=None, tray=None, sleep=time.sleep):
        self.stop, self.grace, self.timer = stop, grace, timer
        self.busy, self.tray, self.sleep = busy, tray, sleep
        self.open = 0
        self.seen = False
        self.lock = threading.Lock()
        self.waiting = None

    def opened(self):
        with self.lock:
            self.open += 1
            self.seen = True
            if self.waiting:
                self.waiting.cancel()
                self.waiting = None

    def closed(self):
        with self.lock:
            self.open = max(0, self.open - 1)
            if self.open or not self.stop or self.waiting:
                return
            self.waiting = self.timer(self.grace, self.gone)
            self.waiting.daemon = True
            self.waiting.start()

    def gone(self):
        with self.lock:
            self.waiting = None
            if self.open or not self.seen:
                return
        self.finish(closing=True)

    def for_update(self):
        if self.stop:
            self.finish(closing=False)

    def finish(self, closing):
        shown = False
        try:
            while self.busy and self.busy():
                if closing and not shown and self.tray:
                    shown = self.tray.show()
                self.sleep(FINISH_LOOK)
                if closing:
                    with self.lock:
                        if self.open:
                            return
        finally:
            if shown:
                self.tray.hide()
        self.stop()


class Tray:

    def __init__(self, tip, icon):
        self.tip, self.icon, self.window, self.data = tip, icon, None, None

    def show(self):
        try:
            import ctypes
            from ctypes import wintypes

            class NotifyIconData(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                            ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                            ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                            ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                            ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]

            user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                               wintypes.HINSTANCE, wintypes.LPVOID]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                          wintypes.UINT]
            shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
            self.window = user32.CreateWindowExW(0, "STATIC", "", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
            data = NotifyIconData(cbSize=ctypes.sizeof(NotifyIconData), hWnd=self.window, uID=1, uFlags=0x2 | 0x4)
            data.hIcon = user32.LoadImageW(None, self.icon, 1, 0, 0, 0x10 | 0x40)
            data.szTip = self.tip[:127]
            self.data = data
            return bool(self.window and shell32.Shell_NotifyIconW(0, ctypes.byref(data)))
        except (OSError, AttributeError, ImportError, ValueError):
            return False

    def hide(self):
        try:
            import ctypes
            if self.data is not None:
                ctypes.windll.shell32.Shell_NotifyIconW(2, ctypes.byref(self.data))
            if self.window:
                ctypes.windll.user32.DestroyWindow(self.window)
        except (OSError, AttributeError, ImportError):
            pass
        self.window = self.data = None
