"""The script language: the forms scripts are made of

A script's rvt blocks hold edn forms (see document.py). Most are steps,
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

      (Precondition "Demo running" (demo-in-mode? :normal)
        :heal "Start the demo in normal mode" (start-demo :normal))

  Preconditions come before the first regular step. The check and the
  heal are step forms; the heal may be described by a string. Unlike a
  step, the check is judged by its value: it holds if nothing in it
  failed and it comes to a truthy value.

Directives (import, variations and the declarations) configure a script
rather than run as steps.
"""

from dataclasses import dataclass

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
