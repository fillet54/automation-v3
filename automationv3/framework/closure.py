"""Script closures: everything a script needs, resolved statically

A script's closure is the core.rvt chain from the root script path down
to the script's folder, then the core.rvt of every folder it imports
with `(import folder)`, then the script itself. That is also the load
order. Nothing is executed to resolve it.

core.rvt files hold definitions (`def`, `defn`); scripts only use them.
A deeper core.rvt in the chain overrides a shallower one, but an import
never overrides a name the chain defines: imports only add definitions.
Declarations (`uut`, `environments`) may appear in any core.rvt of the
chain or in the script, and the last one in load order wins. Imported
core.rvt files contribute definitions only.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import edn

CORE = "core.rvt"
DEFINITIONS = {"def", "defn"}
DECLARATIONS = {"uut", "environments"}
# Top-level forms that configure a script rather than run as steps
DIRECTIVES = {"import"} | DECLARATIONS


def head(form):
    """The name of a list form's first symbol, else None"""
    if isinstance(form, list) and len(form) > 0 and isinstance(form[0], edn.Symbol):
        return str(form[0])
    return None


def name_of(value):
    """'sim' for :sim, sim or "sim" """
    return str(value).lstrip(":")


@dataclass
class Closure:
    script: str
    files: dict = field(default_factory=dict)
    load_order: list = field(default_factory=list)
    imports: list = field(default_factory=list)  # load_order entries from imports
    uuts: list = field(default_factory=list)
    environments: list = field(default_factory=list)
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
                    f"{path}: core.rvt may only contain documentation, "
                    f"def, defn, uut and environments, not {edn.writes(form).strip()}"
                )
        elif name in DEFINITIONS:
            errors.append(f"{path}: {name} {name_of(form[1])} belongs in a core.rvt")
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
    errors.extend(lint(script, script_forms))

    return closure
