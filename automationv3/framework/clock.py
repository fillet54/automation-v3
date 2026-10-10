"""The clock a run keeps time by: Wait's timeouts and pauses

A run has one clock, given by its environment (Environment.clock): the
wall clock on real hardware, or a simulation's clock, read from a ref
(e.g. the simulation's time), in a simulated environment.
"""

import contextvars
import time
from contextlib import contextmanager


class Clock:
    def now(self):
        """Seconds, from any fixed start"""
        raise NotImplementedError

    def sleep(self, seconds):
        """Let `seconds` pass"""
        raise NotImplementedError


class WallClock(Clock):
    """Real time"""

    def now(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)


class SimClock(Clock):
    """A simulation's time, read from a ref. Sleeping waits (in real
    time) for the simulation to run that far, or, for a simulation that
    only moves when stepped, steps it: `step(seconds)`."""

    def __init__(self, time_ref, step=None, poll=0.01):
        self.time_ref, self.step, self.poll = time_ref, step, poll

    def now(self):
        from . import refs
        return float(refs.read(self.time_ref, record_it=False))

    def sleep(self, seconds):
        if self.step is not None:
            self.step(seconds)
            return
        until = self.now() + seconds
        while self.now() < until:
            time.sleep(self.poll)


default_clock = WallClock()  # tests swap in one that doesn't really wait

_clock = contextvars.ContextVar("clock", default=None)


@contextmanager
def keeping(clock):
    """Make `clock` the run's clock for the duration (None: the default)"""
    token = _clock.set(clock)
    try:
        yield
    finally:
        _clock.reset(token)


def current():
    return _clock.get() or default_clock
