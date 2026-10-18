"""What came of a run, in its document

A run's document is its script (see script.py), with directives where
each step's result goes:

    .. step-result:: INDEX            one step (:row: NAME in a table block)
    .. precondition-result:: INDEX    the phases a Precondition ran
    .. table-results:: INDEX          each row of a table block, with its
                                      steps' results

and :run-state:`FIRST-LAST`, the state and duration of the steps in a
range (a titled block's). They resolve against the run's events, through
the run/ snippets; with no run (a script's own page) they write nothing.

A block can write its own result: see BuildingBlock.as_result_rst.
"""

from dataclasses import dataclass, field

from docutils import nodes, utils
from docutils.parsers.rst import directives, roles

from ..framework.block import BuildingBlock, all_blocks, find_block
from ..framework.excerpt import failure_view
from ..framework.language import DIRECTIVES, head
from .core import directive, role
from .template import Rst, filter, literal, text

# A block's state is its most telling step's: earlier wins
STATE_ORDER = ["error", "fail", "blocked", "running", "pending", "not run", "tbd", "pass"]


@dataclass
class StepResult:
    """One step's result, for snippets and BuildingBlock.as_result_rst"""

    state: str                       # pass, fail, error, tbd, running, pending, not run
    duration: float = None
    stdout: str = ""
    stderr: str = ""
    error: bool = False
    value: object = None
    data: object = None              # what the block returned in BlockResult.data
    calls: list = field(default_factory=list)        # trees: each has "children"
    attachments: list = field(default_factory=list)  # [{"name", "url"}]
    failure: dict = None             # {"message", "excerpts", "traceback"}
    ended: dict = None               # the step_end event


def step_state(ended):
    """pass, fail (an assertion came out false), error (something raised)
    or tbd (it passed, but reached steps not written yet)"""
    if ended["passed"]:
        return "tbd" if ended.get("placeholders") else "pass"
    return "error" if ended.get("error") else "fail"


def call_state(call):
    """A suppressed call (inside try-ok? or try) is true or false; any
    other passes, fails or errs"""
    if "passed" not in call:
        return "running"
    if call.get("suppressed") or call.get("checked"):  # checked: older runs
        return "true" if call["passed"] else "false"
    if call.get("block_kind") == "placeholder":
        return "tbd"
    return step_state(call)


def total_duration(durations):
    """The sum of the durations that are known, None if none is"""
    known = [d for d in durations if d is not None]
    return round(sum(known), 3) if known else None


def key(event):
    return (event.get("index"), event.get("row"))


class RunResults:
    """A run's events, by step"""

    def __init__(self, data, run):
        self.data, self.run = data, run
        self.events = data.events(run)
        self.finished = run.get("outcome") is not None
        self.closure = data.closure(run)
        self.statements = data.statements(run)
        self.started = {key(e) for e in self.events if e["kind"] == "step_start"}
        self.ended = {key(e): e for e in self.events if e["kind"] == "step_end"}
        self.calls = call_trees(self.events)
        self.attachments = {}
        for event in self.events:
            if event["kind"] == "attachment":
                self.attachments.setdefault(key(event), []).append(event)
        self.table_rows = {e["index"]: e["rows"] for e in self.events
                           if e["kind"] == "table_start"}
        self.rows = {}
        for event in self.events:
            if event["kind"] in ("row_start", "row_end"):
                self.rows.setdefault((event["index"], event["row"]), {}).update(
                    {k: v for k, v in event.items() if k not in ("seq", "ts")})
        self.phases = phases(self.events, self.calls)
        self.variation = (run.get("variation") or {}).get("name")
        self.own_results = None

    def files(self, events):
        return [{"name": e["name"],
                 "url": self.data.links.file(self.run["report_id"], self.run["id"], e["name"])}
                for e in events]

    def failure(self, ended):
        if not ended or ended.get("passed") or "message" not in ended:
            return None
        return failure_view(self.closure, ended["message"], ended.get("trace"),
                            ended.get("stderr", "") if ended.get("error") else "")

    def step(self, index, row=None):
        found = (index, row)
        ended = self.ended.get(found)
        if ended is not None:
            state = step_state(ended)
        elif found in self.started:
            state = "running"
        else:
            state = "not run" if self.finished else "pending"
        return StepResult(
            state=state,
            duration=(ended or {}).get("duration"),
            stdout=(ended or {}).get("stdout") or "",
            stderr=(ended or {}).get("stderr") or "",
            error=bool((ended or {}).get("error")),
            value=(ended or {}).get("value"),
            data=(ended or {}).get("data"),
            calls=self.calls.get(found, []),
            attachments=self.files(self.attachments.get(found, [])),
            failure=self.failure(ended),
            ended=ended)

    def is_step(self, index):
        form = self.statements[index].statement
        return isinstance(form, list) and head(form) not in DIRECTIVES

    def span_state(self, first, last):
        """The state and duration of the steps from `first` to `last`"""
        results = [self.step(i) for i in range(first, last + 1)
                   if i < len(self.statements) and self.is_step(i)
                   and not self.statements[i].definition]
        states = [r.state for r in results]
        state = min(states, key=STATE_ORDER.index) if states else None
        return state, total_duration(r.duration for r in results)

    def table(self, index):
        """A table block's rows: each with its values, state, message,
        duration and its steps' results"""
        statement = self.statements[index]
        steps = [i for i in range(index + 1, len(self.statements))
                 if self.statements[i].table == statement.table]
        steps = steps[:next((n for n, i in enumerate(steps) if i != index + 1 + n),
                            len(steps))]
        steps = [i for i in steps if not (self.variation and self.statements[i].variations
                                          and self.variation not in self.statements[i].variations)]
        names = self.table_rows.get(index)
        if names is None:  # not reached: the rows as written
            from ..framework.language import parse_table
            names = [row.name for row in parse_table("", statement.statement, [])]
        rows = []
        for name in names:
            event = self.rows.get((index, name), {})
            if "outcome" in event:
                state = event["outcome"]
            elif event:
                state = "running"
            else:
                state = "not run" if self.finished else "pending"
            results = [(i, self.step(i, name)) for i in steps if self.is_step(i)]
            if state == "pass" and any(r.state == "tbd" for _, r in results):
                state = "tbd"
            rows.append({"name": name, "values": event.get("values", {}), "state": state,
                         "message": event.get("message"), "steps": results,
                         "duration": total_duration(r.duration for _, r in results)})
        return rows


def call_trees(events):
    """(statement index, row) -> its block calls as a tree, quiet calls
    left out. Each call has its `children` (calls made inside a step
    form)."""
    calls = {}
    for event in events:
        if event["kind"] not in ("call_start", "call_end") or event.get("quiet"):
            continue
        call = calls.setdefault((*key(event), event["call"]), {"children": []})
        call.update({k: v for k, v in event.items() if k not in ("kind", "seq", "ts")})
    for call in calls.values():
        call["state"] = call_state(call)
    trees = {}
    for (index, row, _), call in sorted(calls.items(), key=lambda kv: (
            kv[0][0], str(kv[0][1]), kv[0][2])):
        parent = calls.get((index, row, call.get("parent")))
        if parent is not None:
            parent["children"].append(call)
        else:
            trees.setdefault((index, row), []).append(call)
    return trees


def phases(events, calls):
    """statement index -> the phases its precondition ran (check, heal,
    check again), in order"""
    found = {}
    for event in events:
        if event["kind"] in ("phase_start", "phase_end"):
            phase = found.setdefault((event["index"], event["phase"]), {})
            phase.update({k: v for k, v in event.items() if k not in ("kind", "seq", "ts")})
            if event["kind"] == "phase_end":
                phase["result"] = event
    by_index = {}
    for (index, number), phase in sorted(found.items()):
        if "result" not in phase:
            phase["state"] = "running"
        elif phase["action"] == "check":
            phase["state"] = "true" if phase["passed"] else "false"
        else:
            phase["state"] = step_state(phase)
        phase["calls"] = [c for c in calls.get((index, None), []) if c.get("phase") == number]
        by_index.setdefault(index, []).append(phase)
    return by_index


# Filters for run snippets

@filter
def duration(seconds):
    """A duration to the millisecond: 7 ms, 1.234 s, 2:05.012"""
    if seconds is None:
        return ""
    ms = round(seconds * 1000)
    if ms < 1000:
        return f"{ms} ms"
    if ms < 60_000:
        return f"{ms / 1000:.3f} s"
    minutes, ms = divmod(ms, 60_000)
    return f"{minutes}:{ms / 1000:06.3f}"


@filter
def classes(value):
    """A state as a class name"""
    return Rst(str(value or "").replace(" ", "-"))


@filter
def calls_rst(calls, depth=0):
    """Block calls as a nested list: each call's state, form (or title),
    what it gave back, its output and duration"""
    lines = []
    pad = "  " * depth
    for call in calls:
        state = call.get("state") or ""
        shown = text(call["title"]) if call.get("title") else literal(call.get("form", ""))
        parts = [f":verdict:`{state}`" if state else "", shown]
        if call.get("block_kind") == "value" and call.get("value") is not None \
                and state in ("pass", "true"):
            parts.append("→ " + literal(call["value"]))
        if call.get("stdout"):
            parts.append(text(call["stdout"]))
        if call.get("duration") is not None:
            parts.append(f":duration:`{duration(call['duration'])}`")
        lines.append(f"{pad}- " + " ".join(p for p in parts if p))
        if call.get("stderr"):
            lines += ["", f"{pad}  ::", ""]
            lines += [f"{pad}     {line}" for line in call["stderr"].rstrip().splitlines()]
            lines.append("")
        if call.get("children"):
            lines.append("")
            lines.append(calls_rst(call["children"], depth + 1))
            lines.append("")
    return Rst("\n".join(lines))


@filter
def excerpt_rst(found):
    """A source excerpt's lines, for a literal block: the failing part
    marked with carets on the line below it"""
    lines = []
    width = len(str(found["rows"][-1]["no"])) if found["rows"] else 1
    for row in found["rows"]:
        lines.append(f"{row['no']:>{width}} | {row['text']}")
        if row.get("mark"):
            lines.append(f"{'':>{width}} | {' ' * len(row['before'])}"
                         f"{'^' * max(1, len(row['marked']))}")
    return Rst("\n".join(lines))


@filter
def values_text(values):
    return " · ".join(f"{k} = {v}" for k, v in (values or {}).items())


def own_results():
    """The names of the blocks that write their own results"""
    return {b.name() for b in all_blocks()
            if type(b).as_result_rst is not BuildingBlock.as_result_rst}


def result_rst(results, index, row=None):
    """A step's result: the block's own, if it writes one, else the
    run/step-result.rst snippet"""
    statement = results.statements[index]
    result = results.step(index, row)
    own = None
    form = statement.statement
    if results.own_results is None:
        results.own_results = own_results()
    if isinstance(form, list) and result.ended is not None \
            and str(head(form)) in results.own_results:
        try:
            found = find_block(form)
            own = found.block.as_result_rst(result, *found.args) if found else None
        except Exception:
            own = None
    return result, own


# Resolving the directives

def run_results(context):
    """The run's results, computed once per Context"""
    if context.data is None or context.run is None:
        return None
    found = context.extra.get("run_results")
    if found is None:
        found = context.extra["run_results"] = RunResults(context.data, context.run)
    return found


def step_result(context, options):
    results = run_results(context)
    if results is None:
        return ""
    index = int(options["argument"])
    if "ended-only" in options and (index, options.get("row")) not in results.ended:
        return ""
    result, own = result_rst(results, index, options.get("row"))
    return context.render("run/step-result.rst", result=result, own=own,
                          statement=results.statements[index])


def precondition_result(context, options):
    results = run_results(context)
    if results is None:
        return ""
    index = int(options["argument"])
    statement = results.statements[index]
    return context.render("run/precondition-result.rst",
                          result=results.step(index), statement=statement,
                          p=statement.precondition, phases=results.phases.get(index, []),
                          failure_of=results.failure, statement_index=index)


def table_results(context, options):
    results = run_results(context)
    if results is None:
        return ""
    index = int(options["argument"])
    rows = results.table(index)
    for row in rows:
        row["steps"] = [(results.statements[i], r, result_rst(results, i, row["name"])[1])
                        for i, r in row["steps"]]
    return context.render("run/table-results.rst", rows=rows,
                          duration=total_duration(r["duration"] for r in rows))


def run_summary(context, options):
    if context.data is None or context.run is None:
        return ""
    return context.render("run/summary.rst")


@filter
def uut_list(versions):
    return ", ".join(f"{name} {v['id']}" for name, v in (versions or {}).items())


def span_state(context, name):
    results = run_results(context)
    if results is None:
        return ""
    first, _, last = name.partition("-")
    state, took = results.span_state(int(first), int(last or first))
    if state is None:
        return ""
    return Rst(" ".join(p for p in (f":duration:`{duration(took)}`" if took is not None else "",
                                    f":verdict:`{state}`") if p))


def duration_role(name, rawtext, value, lineno, inliner, options=None, content=None):
    """:duration:`1.234 s`: a duration, classed for outputs to style"""
    return [nodes.inline(rawtext, utils.unescape(value), classes=["duration"])], []


roles.register_local_role("duration", duration_role)

directive("step-result", step_result, {"row": directives.unchanged,
                                       "ended-only": directives.flag}, arguments=True)
directive("precondition-result", precondition_result, arguments=True)
directive("table-results", table_results, arguments=True)
directive("run-summary", run_summary)
role("run-state", span_state)
