# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import platform
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(ROOT, "tools", "startup")


def uname():
    ver = sys.getwindowsversion()
    numbers = (ver.major, ver.minor, ver.build)
    releases = platform._WIN32_CLIENT_RELEASES if ver.product_type == 1 else platform._WIN32_SERVER_RELEASES
    release = next((name for since, name in releases if since <= numbers), "")
    machine = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    return "Windows", platform._node(), release, "{}.{}.{}".format(*numbers), machine


def answer(environ=None):
    if sys.platform != "win32":
        return
    if platform._uname_cache is None:
        platform._uname_cache = platform.uname_result(*uname())
    platform._wmi = None
    environ = os.environ if environ is None else environ
    paths = [p for p in environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not any(os.path.normcase(os.path.abspath(p)) == os.path.normcase(HOOK) for p in paths):
        environ["PYTHONPATH"] = os.pathsep.join(paths + [HOOK])
