# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import concurrent.futures
import contextvars
import importlib
import multiprocessing.process
import threading

_SWITCHES = {}


def switch(module, name, default):
    key = f"{module}.{name}"
    var = _SWITCHES.get(key)
    if var is None:
        var = _SWITCHES[key] = contextvars.ContextVar(key, default=default)
    return var


def values():
    return {key: var.get() for key, var in _SWITCHES.items()}


class Carried:

    def __init__(self, fn, switches):
        self.fn, self.switches = fn, switches

    def __call__(self, *a, **k):
        return contextvars.Context().run(self._run, a, k)

    def _run(self, a, k):
        for key, value in self.switches.items():
            if key not in _SWITCHES:
                importlib.import_module(key.rpartition(".")[0])
            _SWITCHES[key].set(value)
        return self.fn(*a, **k)


def _in_context(start):
    def start_in_context(self):
        ctx, run = contextvars.copy_context(), self.run
        self.run = lambda: ctx.run(run)
        return start(self)
    start_in_context.carries = True
    return start_in_context


def _each_in_context(submit):
    def submit_in_context(self, fn, /, *args, **kwargs):
        return submit(self, contextvars.copy_context().run, fn, *args, **kwargs)
    submit_in_context.carries = True
    return submit_in_context


def _each_carried(submit):
    def submit_carried(self, fn, /, *args, **kwargs):
        return submit(self, Carried(fn, values()), *args, **kwargs)
    submit_carried.carries = True
    return submit_carried


def _process_carried(start):
    def start_carried(self):
        if self._target is not None:
            self._target = Carried(self._target, values())
        return start(self)
    start_carried.carries = True
    return start_carried


def _install():
    for owner, attr, wrap in ((threading.Thread, "start", _in_context),
                              (concurrent.futures.ThreadPoolExecutor, "submit", _each_in_context),
                              (concurrent.futures.ProcessPoolExecutor, "submit", _each_carried),
                              (multiprocessing.process.BaseProcess, "start", _process_carried)):
        if not getattr(getattr(owner, attr), "carries", False):
            setattr(owner, attr, wrap(getattr(owner, attr)))


_install()
