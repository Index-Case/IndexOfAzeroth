# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import os
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, ROOT)
import thispc
thispc.answer()
import store
import workers

POLL = 5.0


def job_of(proc):
    if os.name != "nt":
        return None
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        job = kernel.CreateJobObjectW(None, None)
        if job and kernel.AssignProcessToJobObject(ctypes.c_void_p(job), ctypes.c_void_p(int(proc._handle))):
            return job
    except (AttributeError, OSError, ValueError):
        pass
    return None


def stop_tree(proc, job):
    if job:
        try:
            import ctypes
            ctypes.windll.kernel32.TerminateJobObject(ctypes.c_void_p(job), 1)
        except (AttributeError, OSError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def wait(proc, limit, waits=None, poll=None, clock=time.time):
    waits, poll = waits or workers.waits, poll or POLL
    ran, last = 0.0, clock()
    while True:
        try:
            return proc.wait(timeout=max(0.0, min(poll, limit - ran)))
        except subprocess.TimeoutExpired:
            now = clock()
            if not waits(proc.pid):
                ran += now - last
            last = now
            if ran >= limit:
                return None


def main(argv):
    result, limit, script, args = argv[0], float(argv[1]), argv[2], argv[3:]
    path = script if os.path.isabs(script) else os.path.join(TOOLS, script)
    began = time.time()
    proc = subprocess.Popen([sys.executable, path, *args], cwd=ROOT, stdout=sys.stdout or subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    job = job_of(proc)
    code = wait(proc, limit - (time.time() - began))
    if code is None:
        stop_tree(proc, job)
        proc.wait()
        print(f"-- {os.path.basename(script)} stopped after {limit:g} s", flush=True)
        store.save_json(result, {"stopped": limit})
        return 1
    store.save_json(result, {"code": code})
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
