"""Planning a queue request: which runs a selection turns into

A selection is a set of scripts (directly, or through the requirements
they reference), the environments to run in, one version per UUT type
and the variations to include. Each script runs once per environment it
supports among those selected, and once per selected variation.

Variations are included unless unticked, and an optional EDN filter
predicate further narrows them. The predicate sees each variation's
bound symbols plus `name` and `index`; a variation missing a symbol the
predicate uses is excluded. Scripts without variations ignore it. A
symbol that no variation in the request binds, and that isn't defined,
is an error rather than a silent exclusion.

The plan also lists every combination that *could* run (all declared
variations in the selected environments) so a report can count the
ones left out as not run.
"""

from dataclasses import asdict, dataclass, field
from itertools import product

from . import edn, lisp
from .closure import resolve
from .executor import build_env, variation_values
from .uut import uut_types


@dataclass
class VariationChoice:
    name: str
    index: int
    values: dict  # symbol -> value as edn text
    selected: bool = True
    reason: str = ""


@dataclass
class ScriptPlan:
    script: str
    closure: object = None
    requirements: list = field(default_factory=list)
    environments: list = field(default_factory=list)  # selected and supported
    variations: list = field(default_factory=list)  # VariationChoice, [] if none
    skipped: str = ""

    @property
    def variation_names(self):
        return [v.name for v in self.variations] or [None]

    def runs(self):
        if self.skipped:
            return []
        names = [v.name for v in self.variations if v.selected]
        if self.variations and not names:
            return []
        return list(product(self.environments or [None], names or [None]))

    def expected(self):
        """Every (environment, variation) that a complete run would cover"""
        return list(product(self.environments or [None], self.variation_names))


@dataclass
class Plan:
    workspace: str
    scripts: list = field(default_factory=list)
    requirements: dict = field(default_factory=dict)  # id -> linked scripts
    environments: list = field(default_factory=list)  # selected
    available_environments: list = field(default_factory=list)
    uut_versions: dict = field(default_factory=dict)  # name -> {id, digest}
    uut_choices: dict = field(default_factory=dict)  # name -> [version ids]
    filter: str = ""
    errors: list = field(default_factory=list)

    def runs(self):
        return [
            (script_plan, environment, variation)
            for script_plan in self.scripts
            for environment, variation in script_plan.runs()
        ]

    def summary(self):
        """What a report records about the request"""
        return {
            "workspace": self.workspace,
            "requirements": self.requirements,
            "environments": self.environments,
            "uut_versions": self.uut_versions,
            "filter": self.filter,
            "scripts": [
                {
                    "script": s.script,
                    "requirements": s.requirements,
                    "environments": s.environments,
                    "variations": [asdict(v) for v in s.variations],
                    "expected": [list(combo) for combo in s.expected()],
                    "skipped": s.skipped,
                }
                for s in self.scripts
            ],
        }


def compile_filter(source, errors):
    if not source or not source.strip():
        return None
    try:
        return edn.read(source)
    except Exception as e:
        errors.append(f"Variation filter could not be read: {e}")
        return None


class UnknownSymbol(Exception):
    pass


def symbols_in(form):
    if isinstance(form, edn.Keyword):
        return set()
    if isinstance(form, edn.Symbol):
        return {str(form)}
    if isinstance(form, list):
        return set().union(*(symbols_in(item) for item in form))
    return set()


def matches(predicate, env, values, name, index, variation_symbols):
    """True if the filter predicate holds for one variation.

    Raises UnknownSymbol for a symbol that is neither defined nor bound
    by any variation in the request.
    """
    scope = lisp.Env(outer=env)
    scope.update({edn.Symbol(k): v for k, v in values.items()})
    scope[edn.Symbol("name")] = name
    scope[edn.Symbol("index")] = index
    missing = {s for s in symbols_in(predicate) if edn.Symbol(s) not in scope}
    if missing - variation_symbols:
        raise UnknownSymbol(", ".join(sorted(missing - variation_symbols)))
    if missing:  # uses a symbol only other variations bind
        return False
    return bool(lisp.eval(predicate, scope))


def plan_variations(script_plan, selection, predicate, errors, variation_symbols):
    closure = script_plan.closure
    for index, variation in enumerate(closure.variations):
        env = build_env(closure.files, closure.load_order, closure.imports,
                        variation.name)
        try:
            values = variation_values(env, variation)
        except Exception as e:
            script_plan.skipped = (
                f"variation {variation.name} could not be evaluated: {e}"
            )
            script_plan.variations = []
            return
        choice = VariationChoice(
            variation.name,
            index,
            {k: edn.writes(v) for k, v in values.items()},
        )
        key = f"{script_plan.script}::{variation.name}"
        if selection is not None and key not in selection:
            choice.selected, choice.reason = False, "unticked"
        elif predicate is not None:
            try:
                if not matches(predicate, env, values, variation.name, index,
                               variation_symbols):
                    choice.selected, choice.reason = False, "filtered out"
            except UnknownSymbol as e:
                message = f"Variation filter uses unknown symbol {e}"
                if message not in errors:
                    errors.append(message)
                choice.selected, choice.reason = False, "filter failed"
            except Exception as e:
                errors.append(f"Variation filter failed on {key}: {e}")
                choice.selected, choice.reason = False, "filter failed"
        script_plan.variations.append(choice)


def build_plan(workspace, root, scripts, requirements=None, environments=None,
               versions=None, variations=None, filter_source="", links=None,
               texts=None):
    """Plan a queue request.

    `links` maps requirement id -> scripts referencing it; requirements
    pull in their linked scripts. `environments` None selects every
    supported environment. `variations` is None (all) or a set of
    "script::name" keys. `versions` maps UUT name -> version id. `texts`
    overrides scripts' content on disk.
    """
    links = links or {}
    texts = texts or {}
    plan = Plan(workspace, filter=filter_source or "")
    predicate = compile_filter(filter_source, plan.errors)

    wanted = list(dict.fromkeys(
        list(scripts or []) + [s for r in requirements or [] for s in links.get(r, [])]
    ))

    for script in wanted:
        script_plan = ScriptPlan(script)
        plan.scripts.append(script_plan)
        script_plan.requirements = sorted(r for r, s in links.items() if script in s)
        try:
            script_plan.closure = resolve(root, script, texts.get(script))
        except FileNotFoundError:
            script_plan.skipped = "script not found"
            continue
        closure = script_plan.closure
        if closure.errors:
            script_plan.skipped = "; ".join(closure.errors)
            continue
        for env in closure.environments:
            if env not in plan.available_environments:
                plan.available_environments.append(env)

    selected_envs = (
        plan.available_environments if environments is None else list(environments)
    )
    plan.environments = [e for e in plan.available_environments if e in selected_envs]

    variation_symbols = {
        symbol
        for s in plan.scripts
        if s.closure is not None
        for v in s.closure.variations
        for symbol in v.symbols
    }
    known = uut_types()
    for script_plan in plan.scripts:
        closure = script_plan.closure
        if script_plan.skipped:
            continue
        missing = [u for u in closure.uuts if u not in known]
        if missing:
            script_plan.skipped = f"no UUT plugin named {', '.join(missing)}"
            continue
        if closure.environments:
            script_plan.environments = [
                e for e in closure.environments if e in plan.environments
            ]
            if not script_plan.environments:
                script_plan.skipped = (
                    "supports none of the selected environments "
                    f"(it supports {', '.join(closure.environments)})"
                )
                continue
        for name in closure.uuts:
            plan.uut_choices.setdefault(
                name, [v.id for v in known[name]().list_versions()]
            )
        plan_variations(script_plan, variations, predicate, plan.errors,
                        variation_symbols)

    versions = versions or {}
    for name, ids in plan.uut_choices.items():
        uut = known[name]()
        version = uut.find_version(versions.get(name) or (ids[-1] if ids else ""))
        if version is None:
            plan.errors.append(f"UUT {name} has no version {versions.get(name)}")
            continue
        plan.uut_versions[name] = asdict(version)

    if requirements:
        plan.requirements = {r: list(links.get(r, [])) for r in requirements}
    else:
        for script_plan in plan.scripts:
            for r in script_plan.requirements:
                plan.requirements[r] = list(links.get(r, []))
    return plan
