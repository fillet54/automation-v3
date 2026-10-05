"""Script closures: everything a script needs, resolved statically

A script's closure is the core.rvt chain from the root script path down
to the script's folder, then the core.rvt of every folder it imports
with `(import folder)`, then the script itself. That is also the load
order. Nothing is executed to resolve it.

Definitions (`def`, `defn`, `defblock`) live in core.rvt files and may
also appear in a script, typically in its definitions section::

    "
    .. rvt::
       :definitions:
    "
    (def stop-pressure 70)

A deeper core.rvt in the chain overrides a shallower one, but an import
never overrides a name the chain defines: imports only add definitions.
Declarations (`uut`, `environments`) may appear in any core.rvt of the
chain or in the script, and the last one in load order wins. Imported
core.rvt files contribute definitions only.

A script may declare its variations once, at the top level::

    (variations "mode trim"
      ["nominal"  [:normal default-trim]
       "degraded" [:limp-home 2]])

Each variation is a display name and the values bound to the symbols
for that run. Values are literals or expressions over core.rvt
definitions; they are kept as forms here and evaluated later.

Preconditions state what must hold before a script's steps run::

    (Precondition "Demo running" (demo-in-mode? :normal)
      :heal (start-demo :normal))

They come before the first regular step. The check and the optional
heal are step forms.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import edn

CORE = "core.rvt"
DEFINITIONS = {"def", "defn", "defblock"}
DECLARATIONS = {"uut", "environments"}
# Top-level forms that configure a script rather than run as steps
DIRECTIVES = {"import", "variations"} | DECLARATIONS

PRECONDITION = "Precondition"

REQUIREMENT_REF = re.compile(r":req:`([^`]+)`", re.IGNORECASE)


def head(form):
    """The name of a list form's first symbol, else None"""
    if isinstance(form, list) and len(form) > 0 and isinstance(form[0], edn.Symbol):
        return str(form[0])
    return None


def name_of(value):
    """'sim' for :sim, sim or "sim" """
    return str(value).lstrip(":")


@dataclass
class Variation:
    name: str
    symbols: list
    forms: list  # one unevaluated value form per symbol


def is_text(value):
    return isinstance(value, str) and not isinstance(value, (edn.Symbol, edn.Keyword))


def parse_variations(path, form, errors):
    """The Variations declared by a (variations SYMBOLS [NAME VALUES ...]) form"""
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
            errors.append(f"{path}: variation name {edn.writes(name).strip()} "
                          "must be a string")
        elif any(v.name == name for v in variations):
            errors.append(f"{path}: variation {name} is declared twice")
        elif not isinstance(values, list) or len(values) != len(symbols):
            errors.append(f"{path}: variation {name} needs {len(symbols)} values "
                          f"for {' '.join(symbols)}")
        else:
            variations.append(Variation(name, symbols, list(values)))
    return variations


def parse_precondition(form):
    """(name, check, heal) of a Precondition form, or None if malformed"""
    if len(form) not in (3, 5) or not is_text(form[1]) or not isinstance(form[2], list):
        return None
    if len(form) == 5:
        if form[3] != edn.Keyword("heal") or not isinstance(form[4], list):
            return None
        return form[1], form[2], form[4]
    return form[1], form[2], None


def lint_preconditions(path, forms):
    errors = []
    seen_step = False
    for form in forms:
        name = head(form)
        if name == PRECONDITION:
            if parse_precondition(form) is None:
                errors.append(f'{path}: Precondition takes "name" (check) '
                              "and optionally :heal (form)")
            if seen_step:
                label = form[1] if len(form) > 1 else ""
                errors.append(f"{path}: Precondition {label} "
                              "must come before the first step")
        elif isinstance(form, list) and name not in DIRECTIVES | DEFINITIONS:
            seen_step = True
    return errors


def requirement_refs(text):
    """Requirement ids referenced with :req:`ID` in a script's documentation"""
    refs = []
    for form in edn.read_all(text):
        if is_text(form):
            refs.extend(ref.strip() for ref in REQUIREMENT_REF.findall(form))
    return list(dict.fromkeys(refs))


@dataclass
class Closure:
    script: str
    files: dict = field(default_factory=dict)
    load_order: list = field(default_factory=list)
    imports: list = field(default_factory=list)  # load_order entries from imports
    uuts: list = field(default_factory=list)
    environments: list = field(default_factory=list)
    variations: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def hash(self):
        ordered = [[path, self.files[path]] for path in self.load_order]
        return hashlib.sha256(json.dumps(ordered).encode()).hexdigest()


def read_forms(path, text, errors):
    try:
        return list(edn.read_all(text))
    except Exception as e:
        errors.append(f"{path}: could not be read ({e})")
        return []


def nested_imports(form):
    """True if an (import ...) appears anywhere below the top level"""
    for item in form[1:] if isinstance(form, list) else []:
        if isinstance(item, list) and (head(item) == "import" or nested_imports(item)):
            return True
    return False


def lint(path, forms):
    errors = []
    is_core = PurePosixPath(path).name == CORE
    for form in forms:
        name = head(form)
        if nested_imports(form):
            errors.append(f"{path}: import is only allowed at the top level")
        if is_core:
            if isinstance(form, list) and name not in DEFINITIONS | DECLARATIONS:
                errors.append(
                    f"{path}: core.rvt may only contain documentation, def, defn, "
                    f"defblock, uut and environments, not {edn.writes(form).strip()}"
                )
    return errors


RVT_DIRECTIVE = re.compile(r"^\.\. rvt::\s*$", re.MULTILINE)
RVT_OPTION = re.compile(r"^\s+:([\w-]+):\s*(.*)$")
RVT_OPTIONS = {"definitions"}


def rvt_options(form):
    """The options of an `.. rvt::` directive in a doc string, or None"""
    if not is_text(form):
        return None
    match = RVT_DIRECTIVE.search(form)
    if match is None:
        return None
    options = {}
    for line in form[match.end():].splitlines()[1:]:
        option = RVT_OPTION.match(line)
        if option is None:
            break
        options[option.group(1)] = option.group(2)
    return options


def is_definition(form):
    return head(form) in DEFINITIONS


def definitions_section(forms):
    """Indexes of the script's definitions section: the doc string with
    an `.. rvt:: :definitions:` directive, and the definitions after it
    up to the next doc string or other form. Empty if there is none."""
    for index, form in enumerate(forms):
        options = rvt_options(form)
        if options is not None and "definitions" in options:
            section = [index]
            for later in range(index + 1, len(forms)):
                if not is_definition(forms[later]):
                    break
                section.append(later)
            return section
    return []


def lint_definitions(path, forms):
    """The definitions section comes first, and rvt options are known"""
    errors = []
    seen_step = False
    for form in forms:
        options = rvt_options(form)
        if options is not None:
            for option in sorted(set(options) - RVT_OPTIONS):
                errors.append(f"{path}: unknown rvt option :{option}:")
            if "definitions" in options and seen_step:
                errors.append(f"{path}: the definitions section must come before "
                              "any step or Precondition")
        elif isinstance(form, list) and head(form) not in DIRECTIVES | DEFINITIONS:
            seen_step = True
    return errors


def ancestors(script):
    """core.rvt paths from the root down to the script's folder"""
    folders = list(reversed(PurePosixPath(script).parents))
    return [str(folder / CORE) if str(folder) != "." else CORE for folder in folders]


def resolve(root, script, text=None):
    """The closure of `script` (relative to `root`), using `text` if given"""
    root = Path(root).resolve()
    script = str(PurePosixPath(script))
    closure = Closure(script)
    errors = closure.errors

    if PurePosixPath(script).name == CORE:
        errors.append(f"{script}: core.rvt files are not scripts")
    if text is None:
        text = (root / script).read_text()

    chain = [path for path in ancestors(script) if (root / path).is_file()]
    script_forms = read_forms(script, text, errors)

    imports = []
    for form in script_forms:
        if head(form) != "import":
            continue
        if len(form) != 2:
            errors.append(f"{script}: import takes exactly one folder")
            continue
        folder = name_of(form[1]).strip("/")
        path = str(PurePosixPath(folder) / CORE)
        if not (root / path).resolve().is_relative_to(root):
            errors.append(f"{script}: cannot import {folder}, it is outside the root")
        elif not (root / path).is_file():
            errors.append(f"{script}: cannot import {folder}, it has no core.rvt")
        elif path not in chain and path not in imports:
            imports.append(path)

    closure.imports = imports
    closure.load_order = chain + imports + [script]
    closure.files = {path: (root / path).read_text() for path in chain + imports}
    closure.files[script] = text

    # Declarations: chain then script, last one wins
    for path in chain + [script]:
        if path == script:
            forms = script_forms
        else:
            forms = read_forms(path, closure.files[path], errors)
            errors.extend(lint(path, forms))
        for form in forms:
            if head(form) == "uut":
                closure.uuts = [name_of(v) for v in form[1:]]
            elif head(form) == "environments":
                closure.environments = [name_of(v) for v in form[1:]]
    for path in imports:
        errors.extend(lint(path, read_forms(path, closure.files[path], errors)))

    declared = [form for form in script_forms if head(form) == "variations"]
    if len(declared) > 1:
        errors.append(f"{script}: variations may only be declared once")
    if declared:
        closure.variations = parse_variations(script, declared[0], errors)
    errors.extend(lint(script, script_forms))
    errors.extend(lint_preconditions(script, script_forms))
    errors.extend(lint_definitions(script, script_forms))

    return closure
