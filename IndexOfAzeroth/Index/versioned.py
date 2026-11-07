# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import threading
import time

from serverlog import start_thread

RETRY_AFTER = 60.0


class Versioned:
    def __init__(self, build, log=None, name="data"):
        self.build = build
        self.log = log
        self.name = name
        self.cv = threading.Condition()
        self.version = None
        self.value = None
        self.building = False
        self.failed_at = 0.0

    def _behind(self, version):
        return self.version is None or version > self.version

    def get(self, version):
        with self.cv:
            while True:
                if not self._behind(version):
                    return self.value
                if not self.building:
                    self.building = True
                    break
                self.cv.wait()
        return self._make(version)

    def ready(self, version):
        with self.cv:
            if self._behind(version) and not self.building and time.time() - self.failed_at >= RETRY_AFTER:
                self.building = True
                start_thread(f"building {self.name}", self._background, (version,))
            return self.value

    def _make(self, version):
        try:
            value = self.build()
        except BaseException:
            with self.cv:
                self.building = False
                self.failed_at = time.time()
                self.cv.notify_all()
            raise
        with self.cv:
            if self._behind(version):
                self.version, self.value = version, value
            self.building, self.failed_at = False, 0.0
            self.cv.notify_all()
        return self.value

    def _background(self, version):
        try:
            self._make(version)
        except Exception:
            if self.log:
                self.log(f"building the {self.name}")
