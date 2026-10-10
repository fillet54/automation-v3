"""A small Lisp over edn forms, for the code in scripts

`eval(form, env)` evaluates a form read by edn: keywords and literals
evaluate to themselves, symbols are looked up in `env`, vectors, maps
and sets evaluate to new ones holding their items evaluated (write
`(quote [...])` for data as written), and a list is a special form or a
call. Special forms (if, do, def, let, quote, fn,
defn, and (.method obj args) calls on Python objects) get their
arguments unevaluated; other modules add their own with
`@special_form`. Everything else is a call: the head and arguments are
evaluated and the head called with the arguments.
"""

import copy
import math
import operator as op
from itertools import count, cycle, islice

from .edn import Keyword, List, Map, Set, Symbol, Vector, span_of


class UnboundName(KeyError):
    """A symbol with no binding"""

    def __init__(self, name):
        super().__init__(name)
        self.name = name

    def __str__(self):
        return f"{self.name} not found."


class Env(dict):
    """Bindings, falling back to an `outer` Env for names not bound here"""

    def __init__(self, params=(), args=(), outer=None):
        if len(params) != len(args):
            raise TypeError(f"Invalid arguments[{args}] received. Expected [{params}]")
        super().__init__(zip(params, args))
        self.outer = outer

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return self.outer is not None and key in self.outer

    def __getitem__(self, key):
        if super().__contains__(key):
            return super().__getitem__(key)
        if self.outer is not None and key in self.outer:
            return self.outer[key]
        raise UnboundName(key)


def partition(n, seq):
    """The items of `seq` in tuples of `n`, leaving out an incomplete last one"""
    return zip(*[islice(seq, start, None, n) for start in range(n)])


def assoc(m, *pairs):
    """A copy of map (or vector) `m` with each key set to its value"""
    m = copy.deepcopy(m)
    for k, v in partition(2, pairs):
        m[k] = v
    return m


def dissoc(m, *keys):
    """A copy of map `m` without `keys`"""
    m = copy.deepcopy(m)
    for k in keys:
        m.pop(k, None)
    return m


def _product(*xs):
    result = 1
    for x in xs:
        result *= x
    return result


def _minus(x, *rest):
    """(- x) negates; (- x y z) subtracts y and z from x"""
    if not rest:
        return -x
    for y in rest:
        x = x - y
    return x


def _divide(x, *rest):
    """(/ x) is 1/x; (/ x y z) divides x by y, then z"""
    if not rest:
        return 1 / x
    for y in rest:
        x = x / y
    return x


def _add(*xs):
    """(+ a b ...) adds numbers, or joins strings or lists"""
    if not xs:
        return 0
    total = xs[0]
    for x in xs[1:]:
        total = total + x
    return total


def standard_env():
    env = Env()
    env.update({k: v for k, v in vars(math).items() if not k.startswith("__")})
    env.update({
        # Like Clojure's, these take any number of arguments
        "+": _add,
        "-": _minus,
        "*": _product,
        "/": _divide,
        ">": op.gt,
        "<": op.lt,
        ">=": op.ge,
        "<=": op.le,
        "=": op.eq,
        "not=": op.ne,
        # Not special forms: every argument is evaluated
        "and": lambda *x: all(x),
        "or": lambda *x: any(x),
        "abs": abs,
        "append": op.add,
        "apply": lambda proc, args: proc(*args),
        "first": lambda x: next(islice(x, 0, None)),
        "rest": lambda x: islice(x, 1, None),
        "cons": lambda x, y: [x] + y,
        "eq?": op.is_,
        "expt": pow,
        "count": len,
        "list": lambda *x: List(x),
        "list?": lambda x: isinstance(x, list),
        "map": map,
        "max": max,
        "min": min,
        "not": op.not_,
        "nil?": lambda x: x is None,
        "some?": lambda x: x is not None,
        "number?": lambda x: isinstance(x, (int, float)),
        "print": print,
        "procedure?": callable,
        "round": round,
        "symbol?": lambda x: isinstance(x, Symbol),
        "cycle": cycle,
        "take": lambda n, coll: islice(coll, 0, n),
        "range": count,
        "str": lambda *x: "".join(str(i) for i in x),
        "partition": partition,
        "assoc": assoc,
        "dissoc": dissoc,
    })
    return env


global_env = standard_env()


# Special forms: by name, or by a test of the head symbol (e.g. a
# leading dot)
special_forms = {}


def special_form(name_or_test):
    """Register the decorated `fn(form, env)` as a special form"""
    def register(fn):
        special_forms[name_or_test] = fn
        return fn
    return register


def get_special_form(head):
    """The special form a list starting with `head` is, if any"""
    if not isinstance(head, Symbol):
        return None
    if head in special_forms:
        return special_forms[head]
    for test, fn in special_forms.items():
        if callable(test) and test(head):
            return fn
    return None


def _do(forms, env):
    value = None
    for form in forms:
        value = eval(form, env)
    return value


@special_form("if")
def if_form(x, env):
    _, test, then, *otherwise = x
    if eval(test, env):
        return eval(then, env)
    return eval(otherwise[0], env) if otherwise else None


@special_form("do")
def do_form(x, env):
    return _do(x[1:], env)


def named(value, name):
    """A value that takes the name it is bound to (e.g. a ref)"""
    rename = getattr(value, "__named__", None)
    return rename(str(name)) if rename is not None else value


@special_form("def")
def def_form(x, env):
    _, name, value = x
    env[name] = named(eval(value, env), name)


@special_form("let")
def let_form(x, env):
    _, bindings, *body = x
    env = Env(outer=env)
    for name, value in partition(2, bindings):
        env[name] = eval(value, env)
    return _do(body, env)


@special_form("quote")
def quote_form(x, env):
    return x[1]


@special_form("fn")
def fn_form(x, env):
    """(fn name? [params] body...) or (fn name? ([params] body...) ...)"""
    _, *rest = x
    name = rest.pop(0) if rest and isinstance(rest[0], Symbol) else None
    if rest and isinstance(rest[0], Vector):
        signatures = [rest]  # one arity: [params] body...
    else:
        signatures = rest  # several: ([params] body...) ...
    for signature in signatures:
        if not (isinstance(signature, list) and signature
                and isinstance(signature[0], Vector)):
            raise ValueError(f"Parameter declaration {signature} should be a Vector")
    by_arity = {len(params): (params, body) for params, *body in signatures}

    def fn(*args):
        if len(args) not in by_arity:
            raise RuntimeError(f"Cannot call {name} with {len(args)} arguments")
        params, body = by_arity[len(args)]
        return _do(body, Env(params, args, outer=env))

    if name is not None:
        fn.__name__ = str(name)
    return fn


@special_form("defn")
def defn_form(x, env):
    env[x[1]] = fn_form(x, env)


@special_form(lambda head: head.startswith(".") and len(head) > 1)
def dot_form(x, env):
    """(.method obj args...) calls a method; (.-attr obj) reads an attribute"""
    member, obj, *args = x
    member = member[1:]
    if member.startswith("-"):
        return getattr(eval(obj, env), member[1:])
    return getattr(eval(obj, env), member)(*[eval(arg, env) for arg in args])


def trace(e):
    """Where an exception raised while evaluating went through, innermost
    first: the form it was raised in, then each call that led there (as
    edn.Spans)"""
    return getattr(e, "lisp_trace", [])


def _note(e, x, call):
    """Record `x` in the exception's trace: the innermost form always,
    then only calls (functions and blocks), not the forms around them"""
    try:
        frames = e.__dict__.setdefault("lisp_trace", [])
    except AttributeError:
        return
    span = span_of(x)
    if span is None or (frames and frames[-1] == span):
        return
    if not frames or call:
        frames.append(span)


def dotted(name):
    """(head, rest) of a dotted name like cpu1.app.mode, or None"""
    name = str(name)
    head, dot, rest = name.partition(".")
    if not dot or not head or not rest or name.endswith(".") or ".." in name:
        return None
    return head, rest


def lookup(symbol, env):
    """The value of a symbol. A dotted name not bound as a whole, like
    cpu1.app.mode, is a path below the value of its head (a ref): see
    refs.py."""
    try:
        return env[symbol]
    except UnboundName:
        parts = dotted(symbol)
        if parts is None:
            raise
    head, rest = parts
    value = env[Symbol(head)]
    child = getattr(value, "__child__", None)
    if child is None:
        raise TypeError(f"{symbol}: {head} isn't a ref, so it has no .{rest}")
    return child(rest)


def eval(x, env=global_env):
    """Evaluate the form `x` in `env`.

    An exception raised inside records the forms it came through (see
    `trace`), so it can be reported where the script wrote them."""
    if isinstance(x, Keyword):
        return x
    if isinstance(x, Symbol):
        try:
            return lookup(x, env)
        except UnboundName as e:
            _note(e, x, call=False)
            raise
    if isinstance(x, Vector):
        return Vector(eval(item, env) for item in x)
    if isinstance(x, dict):
        return Map({eval(k, env): eval(v, env) for k, v in x.items()})
    if isinstance(x, (set, frozenset)):
        return Set(eval(item, env) for item in x)
    if not isinstance(x, List) or not x:
        return x
    special = get_special_form(x[0])
    try:
        if special:
            return special(x, env)
        proc = eval(x[0], env)
        return proc(*[eval(arg, env) for arg in x[1:]])
    except Exception as e:
        _note(e, x, call=not special or getattr(special, "is_call", False))
        raise
