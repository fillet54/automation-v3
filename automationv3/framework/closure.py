"""Script closures: everything a script needs, resolved statically

Scripts and core.rst files are reStructuredText documents whose code is
in rvt blocks (see source.py). A script's closure is the core.rst
chain from the root script path down to the script's folder, then the
core.rst of every folder it imports with `(import folder)`, then the
script itself. That is also the load order. Nothing is executed to
resolve it.

Definitions (`def`, `defn`) live at the top level of core.rst files and
may also appear in a script, typically in its definitions section, an rvt
block marked `:definitions:` that comes before any step.

A deeper core.rst in the chain overrides a shallower one, but an import
never overrides a name the chain defines: imports only add definitions.
Declarations (`uut`, `environments`) may appear in any core.rst of the
chain or in the script, and the last one in load order wins. Imported
core.rst files contribute definitions only.

Blocks limited to variations (`:variations:` on an rvt block, or an
rvt-variant directive; see source.py) must name variations the script
declares, may not hold directives, and may only appear in scripts.

The forms a script is made of (definitions, declarations, variations,
preconditions) are described in language.py. Once the closure reads
cleanly, analysis.py checks every name and call in it statically; its
errors stop the script from queuing, its warnings are only shown.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import edn, source
from .language import (
    DECLARATIONS, DEFINITIONS, DIRECTIVES, PRECONDITION, head, is_definition, is_step,
    name_of, parse_precondition, parse_variations,
)

CORE = "core.rst"
SNIPPETS = "snippets.rst"  # see snippets.py: neither a script nor definitions


def lint_preconditions(path, forms):
    errors = []
    seen_step = False
    for form in forms:
        name = head(form)
        if name == PRECONDITION:
            if parse_precondition(form) is None:
                errors.append(f'{path}: Precondition takes "name" (check) '
                              'and optionally :heal "description" (form)')
            if seen_step:
                label = form[1] if len(form) > 1 else ""
                errors.append(f"{path}: Precondition {label} "
                              "must come before the first step")
        elif is_step(form):
            seen_step = True
    return errors


def requirement_refs(text):
    """Requirement ids referenced with :req:`ID` in a script's prose,
    each once, in order"""
    refs = source.requirement_refs(source.parse(text))
    return list(dict.fromkeys(id for id, _ in refs))


def is_script(path, text):
    """An .rst document with rvt blocks, other than a core.rst or a
    snippets.rst"""
    path = PurePosixPath(path)
    return (path.suffix == ".rst" and path.name not in (CORE, SNIPPETS)
            and source.has_rvt(text))


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
    warnings: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)  # analysis.Diagnostic

    @property
    def hash(self):
        ordered = [[path, self.files[path]] for path in self.load_order]
        return hashlib.sha256(json.dumps(ordered).encode()).hexdigest()


def read_statements(path, text, errors, diagnostics):
    """The statements of `text` (see source.statements); or, if any block
    can't be read, none, and an error for each such block, placed on it
    (a Diagnostic in `diagnostics`, its text in `errors`)"""
    from .analysis import ERROR, Diagnostic
    tree = source.parse(text, path)
    problems = source.unreadable(tree)
    for problem in problems:
        diagnostic = Diagnostic(ERROR, problem.message, problem.span, path)
        diagnostics.append(diagnostic)
        errors.append(str(diagnostic))
    return [] if problems else source.statements(tree)


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
                    f"{path}: core.rst may only contain documentation, def, defn, "
                    f"uut and environments, not {edn.writes(form)}"
                )
    return errors


def lint_definitions(path, statements):
    """The definitions section comes before any step, and holds only
    definitions"""
    errors = []
    seen_step = False
    for statement in statements:
        form = statement.form
        if statement.definitions:
            if not is_definition(form):
                errors.append(f"{path}: a :definitions: block may only hold "
                              f"definitions, not {edn.writes(form)}")
            elif seen_step:
                errors.append(f"{path}: the definitions section must come before "
                              "any step or Precondition")
        elif is_step(form):
            seen_step = True
    return errors


def lint_variation_scopes(path, text, variations):
    """`:variations:` blocks and rvt-variants name declared variations,
    and blocks hold no declarations; core.rst files can't scope blocks
    at all. Nothing is said of a file that can't be read."""
    errors = []
    tree = source.parse(text, path)
    if source.unreadable(tree):
        return errors
    is_core = PurePosixPath(path).name == CORE
    declared = {v.name for v in variations}
    reported = set()
    for node in source.walk(tree):
        names = node["variations"]
        if not names:
            continue
        forms = [form for form, _ in node["forms"]] if isinstance(node, source.rvt_block) else []
        directive = next((head(form) for form in forms if head(form) in DIRECTIVES), None)
        if is_core:
            message = f"{path}: core.rst blocks can't be limited to variations"
        elif not declared:
            message = (f"{path}: a block is limited to variations, "
                       "but the script declares none")
        elif unknown := [n for n in names if n not in declared]:
            message = (f"{path}: no variation named {', '.join(unknown)} "
                       f"(the script declares {', '.join(sorted(declared))})")
        elif directive is not None:
            message = f"{path}: {directive} can't be limited to variations"
        else:
            continue
        if message not in reported:
            reported.add(message)
            errors.append(message)
    return errors


def ancestors(script):
    """core.rst paths from the root down to the script's folder"""
    folders = list(reversed(PurePosixPath(script).parents))
    return [str(folder / CORE) if str(folder) != "." else CORE for folder in folders]


def find_imports(root, script, forms, chain, errors, texts=()):
    """The core.rst paths the script's (import folder) forms load, beyond
    its chain"""
    imports = []
    for form in forms:
        if head(form) != "import":
            continue
        if len(form) != 2:
            errors.append(f"{script}: import takes exactly one folder")
            continue
        folder = name_of(form[1]).strip("/")
        path = str(PurePosixPath(folder) / CORE)
        if not (root / path).resolve().is_relative_to(root):
            errors.append(f"{script}: cannot import {folder}, it is outside the root")
        elif path not in texts and not (root / path).is_file():
            errors.append(f"{script}: cannot import {folder}, it has no core.rst")
        elif path not in chain and path not in imports:
            imports.append(path)
    return imports


def resolve(root, script, text=None, texts=None):
    """The closure of `script` (relative to `root`), using `text` if given.
    `texts` maps paths to text that stands in for those files on disk (an
    editor's unsaved documents)."""
    texts = texts or {}
    root = Path(root).resolve()
    script = str(PurePosixPath(script))
    closure = Closure(script)
    errors = closure.errors

    if PurePosixPath(script).name == CORE:
        errors.append(f"{script}: core.rst files are not scripts")
    if text is None:
        text = texts[script] if script in texts else (root / script).read_text()
    script_statements = read_statements(script, text, errors, closure.diagnostics)
    script_forms = [statement.form for statement in script_statements]

    chain = [path for path in ancestors(script) if path in texts or (root / path).is_file()]
    closure.imports = find_imports(root, script, script_forms, chain, errors, texts)
    closure.load_order = chain + closure.imports + [script]
    core_paths = closure.load_order[:-1]
    closure.files = {path: texts[path] if path in texts else (root / path).read_text()
                     for path in core_paths}
    closure.files[script] = text

    core_forms = {}
    parsed = {script: script_statements}
    for path in core_paths:
        found = parsed[path] = read_statements(path, closure.files[path], errors,
                                               closure.diagnostics)
        core_forms[path] = [statement.form for statement in found]
        errors.extend(lint(path, core_forms[path]))
        if any(statement.table is not None for statement in found):
            errors.append(f"{path}: core.rst blocks can't be tables")
        errors.extend(lint_variation_scopes(path, closure.files[path], []))

    # Declarations: the chain's, then the script's; the last one wins.
    # Imported core.rst files only add definitions.
    for form in [form for path in chain for form in core_forms[path]] + script_forms:
        if head(form) == "uut":
            closure.uuts = [name_of(v) for v in form[1:]]
        elif head(form) == "environments":
            closure.environments = [name_of(v) for v in form[1:]]

    declared = [form for form in script_forms if head(form) == "variations"]
    if len(declared) > 1:
        errors.append(f"{script}: variations may only be declared once")
    if declared:
        closure.variations = parse_variations(script, declared[0], errors)
    errors.extend(lint(script, script_forms))
    errors.extend(lint_preconditions(script, script_forms))
    errors.extend(lint_definitions(script, script_statements))
    errors.extend(lint_variation_scopes(script, text, closure.variations))
    if not errors:
        check(closure, parsed)
    return closure


def check(closure, parsed=None):
    """Run the static analysis (over the documents' statements, if already
    `parsed`): its errors join the closure's errors, its warnings its
    warnings"""
    from .analysis import ERROR, analyze
    closure.diagnostics = analyze(closure, parsed)
    for diagnostic in closure.diagnostics:
        target = closure.errors if diagnostic.severity == ERROR else closure.warnings
        target.append(str(diagnostic))
