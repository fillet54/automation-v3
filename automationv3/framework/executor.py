from .block import BuildingBlock
from .observer import ObserverManager, Observer
from .lisp import eval
from .edn import read

import automationv3.plugins

import importlib
import pkgutil
def iter_namespace(ns_pkg):
    return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + '.')

discovered_plugins = {
    name: importlib.import_module(name)
    for finder, name, ispkg
    in iter_namespace(automationv3.plugins)
}

def execute_text(text, observer):
    observer.on_test_begin()
    observer.on_test_end()
