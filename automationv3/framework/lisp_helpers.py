"""Collection functions for the default script Lisp.

Collection-producing helpers return EDN vectors, so they can be counted,
read repeatedly and written in reports. get/contains? use keys for maps
and nonnegative indexes for sequences; nth also accepts iterators.
"""

from .edn import Symbol, Vector

_MISSING = object()


def _sequence(value):
    return isinstance(value, (list, tuple, range, str)) and not isinstance(value, Symbol)


def _index(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def get(collection, key, default=None):
    """A map's key or a sequence's index; default (nil) when missing."""
    if collection is None:
        return default
    if isinstance(collection, dict):
        return collection.get(key, default)
    if _sequence(collection):
        return collection[key] if _index(key) and key < len(collection) else default
    raise TypeError("get takes a map, sequence or nil")


def get_in(collection, path, default=None):
    """Follow a path of map keys or sequence indexes, with a missing default."""
    value = collection
    for key in path if path is not None else ():
        value = get(value, key, _MISSING)
        if value is _MISSING:
            return default
    return value


def nth(collection, index, default=_MISSING):
    """The indexed item of a sequence or iterator; missing indexes raise
    IndexError unless a default was supplied. Indexes start at zero."""
    if not isinstance(index, int) or isinstance(index, bool):
        raise TypeError("nth takes an integer index")
    if isinstance(collection, (dict, set, Symbol)):
        raise TypeError("nth takes a sequence or iterator")
    if index >= 0:
        for n, value in enumerate(() if collection is None else collection):
            if n == index:
                return value
    if default is not _MISSING:
        return default
    raise IndexError(f"nth index {index} is out of range")


def contains(collection, key):
    """Whether a map/set has a key, or a sequence has an index (not a value)."""
    if collection is None:
        return False
    if isinstance(collection, (dict, set)):
        return key in collection
    if _sequence(collection):
        return _index(key) and key < len(collection)
    raise TypeError("contains? takes a map, set, sequence or nil")


def keys(collection):
    """The map's keys, in insertion order, as an EDN vector."""
    if collection is None:
        return Vector()
    if not isinstance(collection, dict):
        raise TypeError("keys takes a map or nil")
    return Vector(collection.keys())


def vals(collection):
    """The map's values, in insertion order, as an EDN vector."""
    if collection is None:
        return Vector()
    if not isinstance(collection, dict):
        raise TypeError("vals takes a map or nil")
    return Vector(collection.values())


def vector(*values):
    """Build an EDN vector from the arguments."""
    return Vector(values)


def vec(collection):
    """Copy/materialize an iterable as an EDN vector; nil gives []."""
    return Vector(() if collection is None else collection)


def filter_values(predicate, collection):
    """Keep items for which predicate returns a truthy value, as an EDN vector."""
    return Vector(value for value in (() if collection is None else collection)
                  if predicate(value))


def reduce_values(function, initial_or_collection, collection=_MISSING):
    """Reduce a collection, optionally starting with an initial value.

    Without an initial value, start with the first item; for an empty
    collection call function with no arguments. With an initial value,
    an empty collection returns that value without calling function.
    """
    if collection is _MISSING:
        values = iter(() if initial_or_collection is None else initial_or_collection)
        try:
            result = next(values)
        except StopIteration:
            return function()
    else:
        values = iter(() if collection is None else collection)
        result = initial_or_collection
    for value in values:
        result = function(result, value)
    return result


def functions():
    return {"get": get, "get-in": get_in, "nth": nth, "contains?": contains,
            "keys": keys, "vals": vals, "vector": vector, "vec": vec,
            "filter": filter_values, "reduce": reduce_values}
