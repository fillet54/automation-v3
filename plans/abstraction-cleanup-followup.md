# Abstraction Cleanup: Follow-up Plan

Follow-up to `plans/abstraction-cleanup.md` (Steps 1–8, commits
`005098b`..`4c46cf6`). Merges `plans/abstraction-cleanup-review.md` with a
second audit (2026-11-21); every finding below was checked against the code,
and the ones marked **confirmed** were reproduced.

Already fixed on `abstraction-cleanup-fixes`, not repeated here:

- `572ff45`: keywords compare and hash as their names (`:a`, `a`, `"a"`).
- `3e67a6b`: requirement text hashes stable again (`plain_text` ignores
  Sphinx directives); identical to pre-refactor output on 393 texts.
- `a4e74e0`: worker abandons jobs the server took back (`JobLost`), resends
  events it couldn't post, releases a job that can't start, retries
  completing, and always returns to "available".

Paths are under `automationv3/` unless they start with `test/` or `plans/`.

## Ground Rules

- One commit per item (or a small series), on `abstraction-cleanup-fixes`,
  with the full suite passing: `.venv/bin/python -m unittest discover -s test -t .`
- Every bug fix lands with a test that fails without it.
- Tick `[x]` and add the commit ref and a one-line note per item, including
  items skipped or changed (Step 6 below exists because the first plan's
  checkboxes recorded none of that).

## Severity Key

- **Regression:** introduced by Steps 1–8; worked before `005098b`.
- **Pre-existing:** older than the refactor, found during the audit.
- **Incomplete:** a Steps 1–8 item marked `[x]` but only partly done.

---

## Step 1: High-Severity Fixes

- [ ] **Report freezing fails: Sphinx can't pickle the build Context** (regression, `6dec5b6`, **confirmed**)
  - `services/reports/sphinx_ext.py:52-69` stores `core.Context` on
    `env.automation_context`. Sphinx pickles the env and doctrees; the
    Context's `Snippets` holds a Jinja environment (weakrefs) and a lambda,
    so `sphinx -b html` fails with `TypeError: cannot pickle 'weakref.ReferenceType'`.
    Every freeze/export fails at the HTML step. Before `005098b` the HTML site built.
  - Fix: keep the Context off `env`: on `env.app` (Sphinx drops `_app` when
    pickling) or in a module dict keyed by `id(app)` as before. Correct the
    plan text that asked for `app.env` (see Step 6).
  - Test: `TestExport` is skipped without `latexmk`, which is how this
    shipped. Add a test that builds only the HTML site (`build.project` +
    `build.sphinx(..., "html", ...)`) and runs everywhere.
- [ ] **Stored XSS through requirement text** (pre-existing, **confirmed**)
  - `documents/html.py:_render_requirement` parses requirement text with
    `raw_enabled` left on, and templates output it with `| safe`. A
    requirement containing `.. raw:: html` with a `<script>` renders it
    verbatim on requirement pages. Requirement text comes from imports and
    flat-file uploads.
  - Fix: add `"raw_enabled": False` (as `documents/core.py:256` and
    `documents/template.py:132` do). Audit the other `publish_*` calls that
    reach `| safe` output for the same setting.
  - Test: a requirement with `.. raw:: html` renders no `<script>`.
- [ ] **`automation.css` needs sign-in on a central server** (regression, `6dec5b6`, **confirmed**)
  - `web/ui.py:73` serves it from endpoint `automation_css`, which isn't in
    `auth.OPEN` (`web/auth.py:42`). Signed out, `/static/css/automation.css`
    redirects to `/auth/login`, so the login, link and signed-out pages are unstyled.
  - Fix: add `"automation_css"` to `OPEN`; point `templates/layout.html:16`
    at `url_for("automation_css")` so the route doesn't depend on
    shadowing the `static` endpoint.
  - Test: signed out on `Central()`, the stylesheet answers 200.
- [ ] **Client mode loses local workers' environments** (regression, `77bd29d`)
  - `web/context.py:52-61` returns `central_environments()` alone when
    `central_client()` is set; before, it merged them with this server's
    live workers (e.g. `LOCAL_WORKER`).
  - Fix: restore the merge. Test: client mode with a local worker lists both.

**Verify:** `test_export.py`, `test_sign_in.py`, `test_client_web.py`, `test_requirement_documents.py`, then the full suite.

---

## Step 2: Medium-Severity Fixes

- [ ] **Mirror caches a timed-out `git archive` as "no scripts"** (regression, `71bd151`)
  - `MirrorWorkspaces.git()` (`services/mirror.py:36-45`) turns
    `TimeoutExpired` into `MirrorError`, and `extract()` reads any
    `MirrorError` as "no scripts folder" and caches an empty folder for that
    commit for good. Before, the timeout propagated.
  - Fix: raise a distinct error for timeouts (or let `TimeoutExpired`
    through) and treat only git's "path not found" exit as "no scripts".
- [ ] **`Kernel.names()` can raise mid-run** (regression, `789097e`)
  - `names()` takes `_env_lock`, but the kernel thread mutates `self.env`
    while statements run, without the lock (so the lock can't guard it
    without blocking the names pane during long runs). `789097e` dropped
    the `except RuntimeError` fallback, so `env.local_items()`
    (`list(dict.items())`) can raise "dictionary changed size during iteration".
  - Fix: make `lisp.Env.local_items()` snapshot with `dict.copy(self)`
    (a single C call, atomic under the GIL) and drop the claim that the lock
    guards the env; keep the lock for `env`/`built`/`sources` swaps.
- [ ] **Plugin rendering rollback leaks** (`framework/plugins.py`, `documents/registry.py`)
  - (a) Regression, `6dec5b6`: `load_plugins()` starting before `documents`
    is imported snapshots no backend (`backend_snap is None`); if a plugin
    then imports `documents` and a later plugin fails, `forget_rendering()`
    skips `restore()`. Fix: snapshot lazily, or restore to "built-ins only"
    when there was no backend at the start.
  - (b) Regression, `6dec5b6`: `set_rendering_registry()` sets the backend
    before replaying; a `ValueError` mid-replay leaves earlier items
    registered. Fix: validate every name first, then register.
  - (c) Pre-existing: `restore()` removes names from `core.RESOLVERS` /
    `ROLE_VALUES` but not from docutils' `directives._directives` /
    `roles._roles`, so a rolled-back directive still parses and then
    `KeyError`s in `core.resolve()`. Fix: pop those too.
  - Also fix `test/test_plugins.py:179-184` to clean up `plugins._directives`
    and docutils' registry, not just `core.RESOLVERS`.
- [ ] **Executor never checks for a stop between steps** (pre-existing; matters more since `a4e74e0`)
  - A worker whose job was taken back stops only if `JobLost` escapes the
    executor; where it is caught, the script runs on to the end (against
    hardware) before the worker reports "lost".
  - Fix: `run_job` runs under `context.stopping(event)`; `ReportObserver`
    sets the event on `JobLost`; the executor calls
    `context.check_stopped()` before each statement (as the kernel does at
    `kernel.py:766`).
- [ ] **`symbols_in` treats a named `fn`'s own name as free** (`framework/planning.py:160`, **confirmed**)
  - `(fn f [x] (f x))` reports `{'f'}`, so a recursive filter predicate
    raises `UnknownSymbol`. Before `16c5c4c` `fn` wasn't handled at all, so
    this is an incomplete fix rather than a regression.
  - Fix: add the name from `parse_fn_arities` to each body's bound set.

**Verify:** `test_mirror.py`, `test_kernel.py`, `test_console.py`, `test_plugins.py`, `test_jobs.py` (incl. `TestPlanning`), then the full suite.

---

## Step 3: Finish `services/jobs.py` Split (incomplete Step 6.1–6.2)

- [ ] **Move callers onto `reports/runs.py` and `scratch.py`, then drop the re-exports**
  - Every caller still goes through the 22 re-exports at
    `services/jobs.py:8-33`, so `runs.py` and `scratch.py` import `jobs`
    inside every function: the cycle moved, it wasn't removed.
  - Order: (1) `runs.py` and `scratch.py` import `jobs` at the top (jobs no
    longer imports them); (2) move `web/`, `cli.py` and tests onto the new
    modules; (3) delete the re-exports. Move the `SCRATCH` special-casing
    in `jobs.py:60, 270-273` into `scratch.py` where it is ordering policy.
- [ ] **Small leftovers**
  - `services/jobs.py:34` imports `now_iso` unused while `:330` and `:545`
    call `store.now_iso()`: use `util.now_iso` throughout.
  - `services/reports/export.py:260` writes a fixed `.zip.tmp`: use a
    `mkstemp` beside the target (as `util.atomic_write` does).
  - `web/editor.py:278-285` (`expand_to`) runs `INSERT OR IGNORE INTO
    expanded_nodes` itself, the last SQL in `web/`: move it beside the other
    `expanded_nodes` helpers in the service.
  - `web/app.py:52` (`workspace_source`) still computes "beside `DB_PATH`"
    itself: use `context.cache_dir`.
  - `services/worker/console.py:90-112` (`choices()`) repeats closure
    resolution, UUT lookup and hosted-environment filtering from
    `Kernel.__init__` (`kernel.py:263-292`): share one helper.

**Verify:** `test_jobs.py`, `test_scratch_first.py`, `test_api.py`, `test_editor.py`, `test_console.py`, `test_layers.py`, then the full suite.

---

## Step 4: Finish Framework / LSP Deduplication (incomplete Step 5)

- [ ] **One `show`**: `framework/value_blocks.py:29`, `plugins/core/verify.py:23`
  and `plugins/apollo/blocks.py:30` are the same `edn.writes` wrapper; keep
  one in `framework/` and import it. Settle `steps.shown` (print's rule) and
  `markup.written` (rst rendering) as intentionally different, with a
  docstring line saying so.
- [ ] **One arity parser**: `analysis.defn_arities` (`framework/analysis.py:97`)
  and the signature builder at `lsp/service.py:760-780` still parse params
  themselves; build both on `language.parse_fn_arities`.
- [ ] **Shared block candidate resolution** across `framework/block.py:337-369`,
  `framework/refs.py:188-199` and `framework/analysis.py:538-553`.
- [ ] **Typed accessors in `lsp/service.py`**: the remaining raw node fields
  (`block["forms"]`, `["line"]`, `["end"]`, `["problems"]`, `["content_line"]`,
  `["code"]`, lines 353-595) go through `source.py` accessors like the
  other modules.
- [ ] **Keep `excerpt.py`'s dict-or-Span handling**: events read back from
  `events.jsonl` are dicts, so the plan's "remove the duck typing" was
  wrong. Document why at `framework/excerpt.py:16` instead.

**Verify:** `test_analysis.py`, `test_lisp*.py`, `test_blocks.py`, `test_refs.py`, `test_lsp.py`, then the full suite.

---

## Step 5: Minor Cleanups

- [ ] `Symbol.__eq__` (`framework/edn.py:118`): compare `qualified` names, so
  `Symbol("a", namespace="ns") == Symbol("ns/a")` like each equals
  `"ns/a"`; consistent with `__hash__`. Extend the test from `572ff45`.
- [ ] `services/builds.py:92` `matched_version` scans oldest-first; the web
  `choices()` it replaced scanned newest-first. Pick newest-first (the
  version a re-uploaded build most likely means) and test two server
  versions sharing a digest.
- [ ] `documents/report.py`: `why` (`L133`) and `issue` (`L189`) repeat the
  fail/incomplete/outdated branching beside `failure_reason` (`L67`); build
  both on one helper returning the parts.
- [ ] Remove dead code: `block.placeholder_names()` (`framework/block.py:297`),
  the unused `versions_text` re-export (`web/report_view.py:20`) and
  `combination_key` re-export (`services/reports/data.py:16`), and the stale
  `plugins/core/__pycache__/value_blocks.*.pyc`.
- [ ] `test/test_client_web.py` writes to `~/.config/automation-v3` through
  `builds.remember_used()`: set `AUTOMATION_CONFIG_HOME` to a temp folder
  in its `setUp`.

**Verify:** full suite.

---

## Step 6: Decisions and Plan Hygiene

- [ ] **Docutils global directive registry**: `framework/rst.py:local_directives`
  swaps `directives._directives` under a lock other parses don't take.
  Decide: accept (window is one short parse, only spec-only names), or
  replace with a per-thread lookup (a `dict` subclass consulting a
  thread-local overlay). Recommendation: accept and document unless a race shows up.
- [ ] **Update `plans/abstraction-cleanup.md`** with notes per item:
  - Step 2.4 asked for HTTP error checks without the worker handling
    them (fixed in `a4e74e0`).
  - Step 3.2 grouped `web/report_view.py`'s `WORST` (dot tones) with
    `documents/report.py`'s (combination states); keeping them apart was right.
  - Step 4.5 said "store the Context on `app.env`", which caused the Step 1
    pickling regression; it should have said `env.app`.
  - Step 5.1's excerpt.py item was wrong (see Step 4).
  - Step 6.3's `dirhtml` dedupe was made moot by Step 4.
  - Mark Steps 5.3–5.5 and 6.1–6.4 partial, pointing here.
- [ ] Delete `plans/abstraction-cleanup-review.md` once this plan is
  adopted (its content is merged here), and merge
  `abstraction-cleanup-fixes` to `master`.

---

## Order and Effort

| Step | Items | Size | Why this order |
|---|---|---|---|
| 1 | 4 | small each | Freezing reports is broken; XSS; login styling; client mode |
| 2 | 5 | small–medium | Correctness, mostly threading and rollback |
| 3 | 2 | medium | Removes the moved import cycle before more code lands on it |
| 4 | 5 | medium | Pure dedupe, no behavior change |
| 5 | 5 | small | Independent, any time |
| 6 | 3 | small | Close out the first plan |

Steps 1 and 2 are independent of each other and of 3–5; 4 and 5 can run in
parallel with 3.
