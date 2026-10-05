"""Observers: whatever wants to hear about a script as it runs

The executor calls on_procedure_begin, on_comment, on_step_start,
on_step_end and on_procedure_end (and workers add on_error). An observer
implements the ones it cares about.
"""

from functools import partial


class Observer:
    pass


class ObserverManager:
    """Passes each event on to several observers, in the order added"""

    def __init__(self):
        self.observers = []

    def add_observer(self, observer):
        self.observers.append(observer)

    def notify(self, event, *args, **kwargs):
        for observer in self.observers:
            if hasattr(observer, "on_" + event):
                getattr(observer, "on_" + event)(*args, **kwargs)

    def __getattr__(self, name):
        if name.startswith("on_"):
            return partial(self.notify, name[3:])
        else:
            raise AttributeError

    def on_procedure_begin(self, *args, **kwargs):
        self.notify("procedure_begin", *args, **kwargs)

    def on_step_start(self, *args, **kwargs):
        self.notify("step_start", *args, **kwargs)

    def on_step_end(self, *args, **kwargs):
        self.notify("step_end", *args, **kwargs)

    def on_procedure_end(self, *args, **kwargs):
        self.notify("procedure_end", *args, **kwargs)

    def on_comment(self, *args, **kwargs):
        self.notify("comment", *args, **kwargs)
