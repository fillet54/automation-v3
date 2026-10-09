"""Tests. Scripts run here don't really wait: (Wait 2s) and Wait's
polling move a virtual clock instead of sleeping."""

from automationv3.framework import connectors


class VirtualClock:
    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds


connectors.wall_clock = VirtualClock()
