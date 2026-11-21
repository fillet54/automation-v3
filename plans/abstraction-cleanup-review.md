# Abstraction Cleanup Plan & Implementation Review

Audit of `plans/abstraction-cleanup.md` against commits `005098b`..`4c46cf6`
(Steps 1–8) and follow-up commits `572ff45`..`a4e74e0` on
`abstraction-cleanup-fixes`.

Paths are under `automationv3/` unless they start with `test/` or `plans/`.

*(Note: the worker stuck-`"busy"` HTTP-error bug from `e89d52a` was already
addressed in `a4e74e0`, and `edn.Keyword` semantics were settled in `572ff45`.)*

---

## 1. Open Bugs & Regressions

### High Severity

- [ ] **Sphinx report export crashes with `PicklingError` (Step 4 / `6dec5b6`)**
  - **Where:** `services/reports/sphinx_ext.py:52-69`
  - **Issue:** `build_context(env)` stores `core.Context(...)` on `env.automation_context`. That `Context` holds a local `lambda` (`requirement_lookup`) and a `Snippets` instance. Sphinx pickles `self.env` whenever any document is updated (`services/reports/build.py:243` passes `-E`), and `BuildEnvironment.__getstate__()` does not strip `automation_context`, causing `_pickle.PicklingError`.
  - **Why tests missed it:** `TestExport` in `test/test_export.py:252` is skipped unless `latexmk` is installed.
  - **Fix:** Store the build context on `env.app` (which Sphinx clears in `BuildEnvironment.__getstate__`) instead of on `env`.

- [ ] **Unauthenticated `automation.css` blocked in central/auth mode (Step 4 / `6dec5b6`)**
  - **Where:** `web/ui.py:73-75` and `web/auth.py:42-43`
  - **Issue:** Moving `automation.css` from `web/static/css/` to `documents/static/` introduced `@app.route("/static/css/automation.css") def automation_css()`. However, `auth.OPEN` only exempts `"static"` and `"paper_ui.static"`, not `"automation_css"`. Unauthenticated pages (`/login`, `/link`, `/signed-out`) receive a `302` redirect to `/login` when requesting `automation.css`.
  - **Fix:** Add `"automation_css"` to `OPEN` in `web/auth.py` (and optionally use `url_for("automation_css")` in `web/templates/layout.html:16`).

- [ ] **`live_environments()` drops local workers in client mode (Step 7 / `77bd29d`)**
  - **Where:** `web/context.py:52-61` (previously `web/jobs.py:107-119`)
  - **Issue:** Previously, `live_environments()` collected local workers from the local DB and merged `central_environments()` when in client mode. `web/context.py:54-55` now returns `central_environments()` immediately when `central_client() is not None`, dropping any environments served by a local worker (`LOCAL_WORKER`).
  - **Fix:** Restore collecting local workers and merging `central_environments()` when `central_client() is not None`.

### Medium Severity

- [ ] **`Kernel._env_lock` does not guard `self.env` mutations, and `RuntimeError` fallback was removed (Step 6 / `789097e`)**
  - **Where:** `services/worker/kernel.py:262, 537-545, 565-576, 695-708, 749-752`
  - **Issue:** `self._env_lock` is only acquired in `_build_env()` and `names()`, never when `_run_forms()` / `_run()` mutate `self.env` on the kernel thread. Because `789097e` also removed `except RuntimeError:` in `names()`, concurrent bindings during `env.local_items()` can now raise an unhandled `RuntimeError: dictionary changed size during iteration`.
  - **Fix:** Guard `self.env` mutations (or snapshot/copy under lock) or protect dict access consistently between the kernel thread and `names()`.

- [ ] **Plugin rendering registry rollback has 3 leaks (Step 4 / `6dec5b6`)**
  - **Where:** `documents/registry.py:41-50`, `documents/core.py:97-108`, `framework/plugins.py:68-85, 249, 307`
  - **Issues:**
    1. `DocumentRegistry.restore()` pops from `core.RESOLVERS` / `core.ROLE_VALUES`, but never unregisters the global docutils directives/roles registered via `directives.register_directive` / `roles.register_local_role`. After a rolled-back plugin load, those docutils entries remain and fail with `KeyError` in `core.resolve()`.
    2. If `load_plugins()` starts before `documents` is imported (`backend_snap` is `None`), a plugin imports `documents` (attaching `DocumentRegistry` and replaying registrations), and a later plugin fails, `forget_rendering()` skips `restore()` because `backend_snap is None`.
    3. `set_rendering_registry()` assigns `_rendering_backend = backend` before replaying `_directives`/`_roles`/`_filters`; if a conflict raises `ValueError` mid-replay, earlier items remain registered without rollback.

- [ ] **`planning.py:symbols_in` drops optional `fn` self-name (Step 5 / `16c5c4c`)**
  - **Where:** `framework/planning.py:160-172`
  - **Issue:** Unpacks `_, signatures = parse_fn_arities(form)`, discarding `name`. A named recursive `(fn f [x] ...)` inside a filter predicate treats `f` as an unknown free symbol and raises `UnknownSymbol`.
  - **Fix:** Include `name` (when present) in the bound set for the `fn` body.

- [ ] **Transient `git archive` timeout permanently poisons mirror cache (Step 2 / `71bd151`)**
  - **Where:** `services/mirror.py:44-45, 111-116`
  - **Issue:** `MirrorWorkspaces.git()` converts `subprocess.TimeoutExpired` into `MirrorError`. `extract()` catches `MirrorError` assuming *"no scripts folder in that commit"*, sets `archive = None`, and extracts an empty directory into `out`, permanently caching a missing-scripts result for that commit.
  - **Fix:** Do not swallow timeouts as "missing scripts folder" (either let timeout errors propagate or distinguish exit-code errors from timeouts).

---

## 2. Plan Items Marked `[x]` That Were Missed or Incomplete

- [ ] **Step 2.1 (`4be69c6`):** `services/jobs.py:34` imports `now_iso` from `.util` (unused), while `services/jobs.py:330` and `:545` still call `store.now_iso()`.
- [ ] **Step 2.2 (`4be69c6`):** `services/reports/export.py:260` still uses a fixed `.zip.tmp` path (`partial = target.with_suffix(".zip.tmp")`) instead of `tempfile.mkstemp`.
- [ ] **Step 5.3 (`16c5c4c`):** Consolidation of `show` / `written` / `name_of` (`framework/value_blocks.py:29`, `plugins/core/verify.py:23`, `plugins/apollo/blocks.py:30`, `framework/steps.py:228`, `framework/markup.py:61`, `framework/language.py:86`) was skipped.
- [ ] **Step 5.4 (`16c5c4c`):** Shared block candidate resolution across `framework/block.py:337-369`, `framework/refs.py:188-199`, and `framework/analysis.py:538-553` was not unified (only `_block_id` → `block_id` was renamed).
- [ ] **Step 5.5 (`16c5c4c`):** `lsp/service.py` was missed for `source.py` typed accessors — 10 raw docutils node dict accesses remain (`block["forms"]`, `block["line"]`, `block["end"]`, `block["problems"]`, `block["content_line"]`, `block["code"]` across lines `353-595`).
- [ ] **Step 6.1 (`789097e`):** No callers in `automationv3/` or `test/` were migrated off `services/jobs.py` to `services/reports/runs.py` or `services/scratch.py`. Keeping all 22 top-level re-exports in `services/jobs.py:8-33` forced deferred `from .. import jobs` / `from . import jobs` imports inside every function of `runs.py` and `scratch.py` (trading one import cycle for another). `SCRATCH` special-casing also remains in `services/jobs.py:60, 270-273`.
- [ ] **Step 6.2 (`789097e`):** Raw SQL `INSERT OR IGNORE INTO expanded_nodes` was missed in `web/editor.py:278-285` (`expand_to`) — the last remaining `.execute*` call in `web/`.
- [ ] **Step 6.4 (`789097e`):** `services/worker/console.py:90-112` (`choices()`) was moved out of `web/console.py`, but still duplicates closure resolution, UUT plugin lookup, and hosted-environment filtering with `Kernel.__init__` (`services/worker/kernel.py:263-292`).

---

## 3. Minor Edge Cases & Cleanup Leftovers

- **`Symbol.__eq__` transitivity (`572ff45`):** In `framework/edn.py:118-123`, `Symbol("a", namespace="ns") == "ns/a"` is `True` and `Symbol("ns/a") == "ns/a"` is `True`, but `Symbol("a", namespace="ns") == Symbol("ns/a")` is `False`. Comparing `self.qualified == other.qualified` makes `__eq__` strictly transitive and directly consistent with `__hash__`.
- **Missing `raw_enabled: False` in requirement HTML (Step 4 / `6dec5b6`):** `documents/html.py:99-103` sets `file_insertion_enabled: False` but omits `raw_enabled: False` (unlike `documents/core.py:256`), even though rendered HTML is output with `| requirement_html | safe`. (Pre-existing from `framework/requirement.py`.)
- **Thread-safety caveat in `rst.local_directives` (`3e67a6b` / `6dec5b6`):** `framework/rst.py:48-62` mutates global `directives._directives` under `_directives_lock`; other docutils parses outside `local_directives` do not hold that lock. A scoped docutils `Parser` subclass would avoid global mutation completely.
- **Unused code / re-exports:**
  - `framework/block.py:297-299`: `placeholder_names()` has no callers.
  - `web/report_view.py:20`: `versions_text` (`# noqa: F401`) is unused across callers/tests.
  - `services/reports/data.py:16`: `combination_key` (`# noqa: F401`) is unused in `data.py` and by callers of `data`.
  - `plugins/core/__pycache__/value_blocks.cpython-314.pyc`: stale untracked `.pyc` file left on disk.
- **Partial reason-formatting duplication (Step 3 / `49250b9`):** `documents/report.py` colocates `failure_reason` (`L67-87`), `why` (`L133-145`), and `issue` (`L189-205`), but `why` and `issue` still repeat the `failure` / `incomplete` / `outdated` branching independently.
- **Minor ordering change in `services/builds.py:111` (Step 7 / `77bd29d`):** `choices()` previously matched `build.digest` newest-first (`reversed(...)`), whereas `matched_version()` iterates oldest-first.
- **Test cleanup leak (`6dec5b6`):** `test/test_plugins.py:179-184` only pops `"test-hello"` from `core.RESOLVERS`, leaving it in `plugins._directives` and `docutils.parsers.rst.directives._directives`.
- **Test isolation:** `test/test_client_web.py` writes to `~/.config/automation-v3` via `builds.remember_used()` without isolating `XDG_CONFIG_HOME` / builds state path, causing failures in read-only home environments.

---

## 4. Issues with `plans/abstraction-cleanup.md` Itself

- **Step 4.5 (`L123`):** Specifying *"Store build `Context` on `app.env`"* caused the Sphinx `PicklingError` regression — it should specify `env.app`.
- **Step 2.4 (`L72`):** Asked to add HTTP error checks to `ServerClient` without accounting for `Worker.run_claimed` lacking `try/finally` around `set_status("busy")` (subsequently fixed in `a4e74e0`).
- **Step 3.2 (`L89`):** Grouped `web/report_view.py`'s `WORST`/`worst()` with `documents/report.py`'s, but they rank different domains (UI dot tones vs. combination states); keeping them separate was the right call.
- **Step 5.1 (`L138`):** Assumed dict-vs-`Span` duck-typing in `framework/excerpt.py` could be removed, but `events.jsonl` callers pass deserialized dicts (so `excerpt.py` still needs `_as_span()`).
- **Step 6.3 (`L176`):** Asked to deduplicate `dirhtml` page paths between `services/requirements/render.py` and `services/requirements/sphinx/__init__.py`, which Step 4 had already made obsolete by removing HTML scraping from `sphinx/__init__.py`.
- **Ground Rules (`L17-18`):** Asked to record brief notes/commit refs as steps completed; only checkboxes were flipped, leaving no record of skipped or adjusted items.
