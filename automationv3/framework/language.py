"""The script language: the forms scripts are made of

A script's rvt blocks hold edn forms (see source.py). Most are steps,
run in order. The others:

- Definitions, `def` and `defn`, name values and functions. They live
  at the top level of core.rst files and scripts, never inside another
  form, so every name a script uses is known before it runs.
- Declarations, `(uut :name)` and `(environments :name ...)`, say what
  a script tests and where it can run.
- `(import folder)` loads the definitions of another folder's core.rst.
- `variations` declares, once per script, the variations it runs as::

      (variations "mode trim"
        ["nominal"  [:normal default-trim]
         "degraded" [:limp-home 2]])

  Each variation is a display name and the values bound to the symbols
  for that run. Values are literals or expressions over definitions;
  they are kept as forms and evaluated when the script runs.
- A table runs the steps of one rvt block once per row, in the same
  run. The block has the ``:table:`` option, and its first form names
  the symbols and gives the rows, like variations::

      .. rvt:: Command each transition
         :table:

         ("from to allowed"
           ["STANDBY to NOMINAL" [:standby :nominal true]
            "NOMINAL to MANEUVER" [:nominal :maneuver false]])

         (BringToMode from)
         (Verify (SendTC :set-mode :mode to) = ...)

  Use a variation when each case needs its own run: the unit restarted
  or set up differently (a hardware configuration, a one-time event
  like separation). Use a table when the cases can run one after the
  other on the unit as it is.
- A Precondition states what must hold before a script's steps run,
  and optionally how to get there::

      (Precondition "LM at high gate" (lm-ready? :standard :high-gate)
        :heal "Boot a standard mission at high gate" (boot :standard :high-gate))

  Preconditions come before the first regular step. The check and the
  heal are step forms; the heal may be described by a string. Unlike a
  step, the check is judged by its value: it holds if nothing in it
  failed and it comes to a truthy value.

Directives (import, variations and the declarations) configure a script
rather than run as steps.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from . import edn

DEFINITIONS = {"def", "defn"}
DECLARATIONS = {"uut", "environments"}
DIRECTIVES = {"import", "variations"} | DECLARATIONS
PRECONDITION = "Precondition"


def head(form):
    """The name of a list form's first symbol, else None"""
    if isinstance(form, list) and len(form) > 0 and isinstance(form[0], edn.Symbol):
        return str(form[0])
    return None


def is_text(value):
    return isinstance(value, str) and not isinstance(value, (edn.Symbol, edn.Keyword))


def is_definition(form):
    return head(form) in DEFINITIONS


def is_step(form):
    """True for a form that runs as a step (Preconditions included):
    a list that is neither a directive nor a definition"""
    return isinstance(form, list) and head(form) not in DIRECTIVES | DEFINITIONS


def name_of(value):
    """'sim' for :sim, sim or "sim" """
    return str(value).lstrip(":")


def ancestor_files(path, filename):
    """`filename` paths from the root down to `path`'s folder"""
    folders = list(reversed(PurePosixPath(path).parents))
    return [str(folder / filename) if str(folder) != "." else filename for folder in folders]


def parse_fn_arities(form):
    """(name_or_None, signatures) for a fn or defn form.

    For ``(defn f [x] body)`` or ``(fn f? [x] body)`` returns ``(f, [[ [x], body ]])``.
    For multi-arity ``(defn f ([x] ...) ([x y] ...))`` returns ``(f, [([x] ...), ([x y] ...)])``.
    """
    is_defn = head(form) == "defn"
    if is_defn:
        name = form[1] if len(form) >= 2 and isinstance(form[1], edn.Symbol) else None
        rest = list(form[2:])
    else:
        rest = list(form[1:])
        name = rest.pop(0) if rest and isinstance(rest[0], edn.Symbol) else None
    if rest and isinstance(rest[0], edn.Vector):
        signatures = [rest]
    else:
        signatures = rest
    return name, signatures


def fn_params(form):
    """List of parameter vectors of a fn or defn form"""
    _, signatures = parse_fn_arities(form)
    return [sig[0] for sig in signatures
            if isinstance(sig, list) and sig and isinstance(sig[0], edn.Vector)]


@dataclass
class Variation:
    name: str
    symbols: list
    forms: list  # one unevaluated value form per symbol


def parse_variations(path, form, errors, commas=False):
    """The Variations declared by a (variations SYMBOLS [NAME VALUES ...]) form.
    Variation names can't hold commas (they are listed with commas when
    picked); with `commas`, as for table rows, they can."""
    if len(form) != 3:
        errors.append(f"{path}: variations takes symbol names and a vector of rows")
        return []
    names, rows = form[1], form[2]
    if is_text(names):
        symbols = names.split()
    elif isinstance(names, list) and all(isinstance(n, edn.Symbol) for n in names):
        symbols = [str(n) for n in names]
    else:
        errors.append(
            f"{path}: variation symbols must be a string or a list of symbols"
        )
        return []
    if not symbols or not isinstance(rows, list) or len(rows) % 2:
        errors.append(f"{path}: variations need symbols and NAME [VALUES] pairs")
        return []

    variations = []
    for name, values in zip(rows[::2], rows[1::2]):
        if not is_text(name):
            errors.append(f"{path}: variation name {edn.writes(name)} "
                          "must be a string")
        elif "," in name and not commas:
            errors.append(f"{path}: variation name {name} may not contain a comma")
        elif any(v.name == name for v in variations):
            errors.append(f"{path}: variation {name} is declared twice")
        elif not isinstance(values, list) or len(values) != len(symbols):
            errors.append(f"{path}: variation {name} needs {len(symbols)} values "
                          f"for {' '.join(symbols)}")
        else:
            variations.append(Variation(name, symbols, list(values)))
    return variations


def is_table_rows(form):
    """True for a table block's first form: ("symbols" [rows])"""
    return (isinstance(form, list) and not isinstance(form, edn.Vector)
            and len(form) == 2 and is_text(form[0]) and isinstance(form[1], list))


def parse_table(path, form, errors):
    """The rows (as Variations) of a table block's first form"""
    if not is_table_rows(form):
        errors.append(f'{path}: a :table: block starts with its rows: '
                      '("symbol ..." ["row" [value ...] ...])')
        return []
    found = []
    rows = parse_variations(path, [edn.Symbol("table"), form[0], form[1]], found,
                            commas=True)
    errors.extend(message.replace("variations", "table rows")
                  .replace("variation", "row") for message in found)
    return rows


@dataclass
class PreconditionParts:
    name: str
    check: list
    heal: list = None
    heal_name: str = None  # the heal's description, if given


def parse_precondition(form):
    """The PreconditionParts of a Precondition form, or None if malformed"""
    if len(form) not in (3, 5, 6):
        return None
    if not is_text(form[1]) or not isinstance(form[2], list):
        return None
    if len(form) == 3:
        return PreconditionParts(form[1], form[2])
    heal_name = form[4] if len(form) == 6 else None
    if (form[3] != edn.Keyword("heal") or not isinstance(form[-1], list)
            or (len(form) == 6 and not is_text(heal_name))):
        return None
    return PreconditionParts(form[1], form[2], form[-1], heal_name)


# Binding patterns: what let, fn and defn bind names with
#
# A pattern is a name, or destructures a value as in Clojure:
#
# - [a b & more :as all] takes a sequence apart: items by position,
#   `& p` the rest (a list, empty when nothing is left), `:as n` the
#   whole. Missing items are nil.
# - {a :a, [x y] :pos, :keys [b c], :or {c 0}, :as m} takes a map apart:
#   each pattern key gets the value under its key, :keys (or :strs,
#   :syms, all the same here as keywords equal strings) binds names to
#   the values under their own names, :or gives defaults for keys that
#   are missing, :as the whole. A sequence is read as key value pairs,
#   so `& {:keys [a]}` takes keyword arguments.
#
# Patterns nest. A fn's parameter vector is a sequence pattern over its
# arguments, without :as.

MAP_NAMES = ("keys", "strs", "syms")


def is_name(form):
    """A symbol a pattern can bind (not a keyword, not &)"""
    return (isinstance(form, edn.Symbol) and not isinstance(form, edn.Keyword)
            and str(form) != "&")


def is_option(form, name):
    """`form` is the keyword :name (not the symbol name, which equals it)"""
    return isinstance(form, edn.Keyword) and str(form) == ":" + name


def sequence_parts(pattern):
    """(items, rest, whole) of a sequence pattern: the positional
    patterns, the pattern after &, the name after :as (None if absent).
    Raises ValueError for a malformed one."""
    items, rest, whole = [], None, None
    parts, i = list(pattern), 0
    while i < len(parts):
        part = parts[i]
        if isinstance(part, edn.Symbol) and str(part) == "&" \
                and not isinstance(part, edn.Keyword):
            if rest is not None or whole is not None or i + 1 >= len(parts):
                raise ValueError(f"& takes one pattern for the rest, in {edn.writes(pattern)}")
            rest, i = parts[i + 1], i + 2
        elif is_option(part, "as"):
            if whole is not None or i + 2 != len(parts) or not is_name(parts[i + 1]):
                raise ValueError(f":as takes a name, last, in {edn.writes(pattern)}")
            whole, i = parts[i + 1], i + 2
        else:
            if rest is not None:
                raise ValueError(f"only :as can follow & rest, in {edn.writes(pattern)}")
            items.append(part)
            i += 1
    return items, rest, whole


def map_parts(pattern):
    """([(pattern, key)], defaults {name: form}, whole) of a map
    pattern; :keys, :strs and :syms names come as (name, name).
    Raises ValueError for a malformed one."""
    pairs, defaults, whole = [], {}, None
    for target, key in pattern.items():
        option = next((n for n in MAP_NAMES + ("or", "as") if is_option(target, n)), None)
        if option in MAP_NAMES:
            if not isinstance(key, edn.Vector):
                raise ValueError(f"{target} takes a vector of names, in {edn.writes(pattern)}")
            for name in key:
                if not isinstance(name, edn.Symbol):  # :keys [:a] is :keys [a]
                    raise ValueError(f"{target} takes names, not {edn.writes(name)}")
                name = edn.Symbol(str(name).lstrip(":"))
                pairs.append((name, name))
        elif option == "or":
            if not isinstance(key, dict) or not all(is_name(n) for n in key):
                raise ValueError(f":or takes a map of names to defaults, in {edn.writes(pattern)}")
            defaults = dict(key)
        elif option == "as":
            if not is_name(key):
                raise ValueError(f":as takes a name, in {edn.writes(pattern)}")
            whole = key
        else:
            pairs.append((target, key))
    return pairs, defaults, whole


def pattern_parts(pattern):
    """The patterns directly inside `pattern` and the names it binds
    itself: ([sub-patterns], [names]). Raises ValueError if malformed."""
    if is_name(pattern):
        return [], [pattern]
    if isinstance(pattern, edn.Vector):
        items, rest, whole = sequence_parts(pattern)
        return items + ([rest] if rest is not None else []), [whole] if whole else []
    if isinstance(pattern, dict):
        pairs, _, whole = map_parts(pattern)
        return [target for target, _ in pairs], [whole] if whole else []
    raise ValueError(f"can only bind names, [vectors] or {{maps}}, not {edn.writes(pattern)}")


def pattern_names(pattern):
    """The names a well-formed pattern binds, in order"""
    subpatterns, names = pattern_parts(pattern)
    found = list(names)
    for sub in subpatterns:
        found += pattern_names(sub)
    return found


def pattern_defaults(pattern):
    """The :or default forms anywhere in a well-formed pattern (they are
    evaluated, so may reference names)"""
    found = list(map_parts(pattern)[1].values()) if isinstance(pattern, dict) else []
    for sub in pattern_parts(pattern)[0]:
        found += pattern_defaults(sub)
    return found


def pattern_names_shallow(pattern):
    """The names a map pattern binds at its own level (what :or can default)"""
    pairs, _, _ = map_parts(pattern)
    return [target for target, _ in pairs if is_name(target)]


def pattern_problem(pattern):
    """(message, form) for the first thing wrong with a pattern, or None"""
    try:
        subpatterns, _ = pattern_parts(pattern)
    except ValueError as e:
        return str(e), pattern
    if isinstance(pattern, dict):
        _, defaults, _ = map_parts(pattern)
        bound = set(map(str, pattern_names_shallow(pattern)))
        for name in defaults:
            if str(name) not in bound:
                return f":or gives a default for {name}, which the map doesn't bind", name
    for sub in subpatterns:
        found = pattern_problem(sub)
        if found:
            return found
    return None


def params_problem(params):
    """(message, form) for what is wrong with a fn's parameter vector, or None"""
    if not isinstance(params, edn.Vector):
        return "parameters must be a vector, e.g. [x y]", params
    found = pattern_problem(params)
    if found:
        return found
    if sequence_parts(params)[2] is not None:
        return "parameters can't use :as (a fn's arguments aren't one value)", params
    return None


def params_arity(params):
    """(fixed, variadic) of a parameter vector: how many arguments it
    names, and whether it takes more after them (& rest)"""
    items, rest, _ = sequence_parts(params)
    return len(items), rest is not None
