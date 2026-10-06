"""Observers: whatever wants to hear about a script as it runs

The executor calls on_procedure_begin, on_comment, on_step_start and
on_step_end, on_phase_start and on_phase_end (a precondition's check
and heal), on_call_start and on_call_end (block calls within a step),
and on_procedure_end; workers add on_job and on_error. Blocks attach
files through on_attach (see steps.attach). An observer implements the
ones it cares about, taking keyword arguments.
"""

from functools import partial


class ObserverManager:
    """Passes each event on to several observers, in the order added"""

    def __init__(self):
        self.observers = []

    def add_observer(self, observer):
        self.observers.append(observer)

    def notify(self, event, **details):
        for observer in self.observers:
            handler = getattr(observer, "on_" + event, None)
            if handler is not None:
                handler(**details)

    def __getattr__(self, name):
        if name.startswith("on_"):
            return partial(self.notify, name[3:])
        raise AttributeError(name)
