# Abstraction Cleanup & Deduplication Plan

Follow-up to the 2026-11-20 codebase audit (after `plans/source-tree.md`
landed). Tracks leaky abstractions, cross-layer coupling, and places where
two or more modules implement the same thing in different ways.

Paths are under `automationv3/` unless they start with `test/`, `docs/`,
or `plans/`.

## Ground Rules

- Each step should land as one commit (or a small series) with the full
  test suite passing (`python3 -m unittest discover -s test -t .`), including
  `test/test_layers.py`.
- Keep changes behavior-preserving unless a sub-item explicitly notes a
  bug fix.
- Update checkboxes (`[ ]` → `[x]`) and add brief notes/commit refs as
  steps complete.

## Decisions to Settle Before Starting Relevant Steps

| Step | Topic | Recommendation |
| --- | --- | --- |
| 1 | `edn.Keyword` equality vs. `Symbol`/`str` (`framework/edn.py`) | Make `Keyword` only equal another `Keyword` (or `":name"`), so `a == b => hash(a) == hash(b)` holds. Check callers that rely on `Keyword("a") == "a"` first. |
| 4 | `test/test_layers.py` boundary for `framework` vs. `documents` | Add `automationv3.documents` to `FORBIDDEN["framework"]` once `framework/markup.py` and `framework/plugins.py` stop importing upward. |
| 6 | Splitting `services/jobs.py` | Keep thin re-exports in `services/jobs.py` only if tests/callers benefit during transition, then delete once migrated. |
| 7 | Renaming colliding `central()` functions | Rename `web/auth.py:central()` → `accounts_enabled()` (or `is_central_server()`) and `web/client_mode.py:central()` → `central_client()`. |

---

## Step 1: Quick Fixes, Dead Code & Low-Risk Bugs

Small, self-contained wins with minimal blast radius.

- [x] **Remove dead debris**
  - Delete stale bytecode directory `plugins/vm/__pycache__/` (no `.py` sources remain).
  - Delete unused re-export shim `plugins/core/value_blocks.py`.
  - Fix `__all__` in `plugins/core/__init__.py` and `plugins/apollo/__init__.py` to contain string names instead of class objects.
- [x] **Fix `edn.Keyword` equality/hash contract** (`framework/edn.py:99-143`)
  - Fix `Keyword.__eq__` so `Keyword("a") == Symbol("a")` no longer returns `True` with mismatched hashes (`hash(":a") != hash("a")`).
  - Add regression tests in `test/test_edn_reader.py` (dict/set lookups mixing `Symbol`, `Keyword`, and `str`).
- [x] **Fix `println` analysis & `steps.py` import-order hazard**
  - Add `"println"` to `EFFECTFUL` in `framework/analysis.py:53`.
  - Explicitly ensure `steps` special forms/builtins are initialized by `framework/analysis.py` instead of relying on `load_plugins()` transitively importing `plugins/core/wait.py`.
- [x] **Fix minor service/web/CLI bugs**
  - `services/jobs.py:729`: serialize `claimed_at` as `str(job.claimed_at) if job.claimed_at else None` instead of `"None"`.
  - `services/worker/host.py:60`: replace `open(path).read()` with `Path(path).read_text()` and expose a single worker-config reader (stop `cli.py:409-417` from re-parsing `--config` separately for `"token"`).
  - `services/reports/build.py:129-161`: construct `build.json` once instead of writing, reading back, mutating, and writing again.
  - `web/auth.py:333-337`: add missing `if not central(): abort(404)` guard on `revoke_worker_token`.
  - `web/requirements.py:130`: filter target reports with `can_change(r)` to match `web/workspace.py:289-290`.
  - `services/client.py` + `cli.py:752-782`: add `CentralClient.import_requirements(...)` and replace raw `central.call("POST", "/requirements/import", ...)` in `cli.py`.

**Verify:** `python3 -m unittest discover -s test -t .`

---

## Step 2: Shared Service Primitives (Time, Atomic I/O, Git, HTTP)

Eliminate divergent low-level helpers across `services/`.

- [x] **Consolidate UTC timestamp helpers**
  - Define one canonical timestamp module/helper (e.g. `services/database.py` or a small `services/util.py`) covering ISO-8601 UTC (`now_iso`) and SQLite `CURRENT_TIMESTAMP` comparison timestamps.
  - Replace duplicates in `services/accounts.py:58`, `services/jobs.py:18`, `services/reports/store.py:56`, `services/requirements/models.py:297`, `services/requirements/flat.py:268`, and remove `services/worker/worker.py:32` importing `now_iso` from `reports.store`.
- [x] **Consolidate atomic file & JSON writes**
  - Extract one `atomic_write(path, data, mode=None)` / `write_json(path, obj, mode=None)` helper using `tempfile.mkstemp(dir=path.parent)` + `os.replace` (fixing concurrent `.tmp` collisions).
  - Use it in `services/client.py:56`, `services/builds.py:65` (currently non-atomic), `services/reports/store.py:60`, `services/reports/build.py:51`, and `web/editor.py:222`.
- [x] **Unify git subprocess & `git archive` extraction**
  - Extract a shared git helper and atomic `extract_archive(archive_bytes, target_dir, cache_dir)` helper used by both `services/workspace.py:112-174` and `services/mirror.py:37-126`.
  - Fix `services/mirror.py:104` to include `self.scripts` in its cache directory key (preventing stale cache hits if `[git] scripts` changes) and keep the `hasattr(tarfile, "data_filter")` guard.
  - Reuse the git helper in `services/client.py:228` and `services/worker/host.py:30`.
- [x] **Align `ServerClient` with `CentralClient`**
  - In `services/worker/client.py:8-69`: reuse `services/client.py:normal_server`, pass `params={"worker_url": self.worker_url}` in `pending_jobs` instead of string interpolation, guard `response.json()` on 401/403 in `check_in`, and check HTTP error status on `start`/`release`/`post_events`/`complete`.
  - Reuse `normal_server` in `cli.py:382-384`.

**Verify:** `test_workspace_handler.py`, `test_mirror.py`, `test_worker_tokens.py`, `test_client_cli.py`, `test_jobs.py`, then full suite.

---

## Step 3: Unify Report Data & Presentation Around `ReportData`

Remove double rollup computation, in-place mutation of cached data, and
three parallel copies of state-ranking / failure-reason logic.

- [x] **Make `ReportData` genuinely read-only & reusable**
  - Extract standalone `document_fields(report)` in `services/reports/data.py` and replace `ReportData.document.fget(SimpleNamespace(...))` in `services/reports/export.py:69-72`.
  - Expose `requirement_context` as a property on `ReportData` so `documents/report.py:309` stops indexing `data.report` directly.
  - Stop `documents/report.py` (`L112`, `L217`, `L236`, `L252`) from mutating `ReportData.combinations` / `ReportData.requirements` dicts in place; pass `links` / `changed` cleanly and replace `c is row` identity checks (`L170`) with combination keys.
- [x] **Single source of truth for state rankings, `why()`, `combination_name()`, and `duration()`**
  - Consolidate `WORST` / `WORDS` / `worst()`, `combination_name()`, `duration()`, `UNASSIGNED`, and failure/outdated/incomplete reason formatting (`why`) across `services/reports/data.py`, `documents/report.py`, `documents/run.py`, `web/report_view.py`, and `web/reports.py:97`.
  - Remove the verbatim copy of `duration(seconds)` in `web/reports.py:96-107` (import from `documents/run.py` or a shared formatter) and duplicate `combination_name` in `documents/report.py:68`.
- [x] **Build `web/report_view.py` on one `ReportData` instance & drop double work**
  - Refactor `web/report_view.py:build()` to consume an existing `ReportData` instead of re-calling `rollup.combinations`/`rollup.requirement_rollup` and instantiating a new `ReportData(root, ...)` inside the per-row `why()` loop (`L192`).
  - Pass that single `ReportData` / `Context` into `documents.report_document(...)` in `web/reports.py:render_page` so `GET /reports/<id>` stops computing rollups and failures twice.
  - Remove orphaned `/<report_id>/runs` code from `web/reports.py:204`, `web/report_view.py`, and `web/static/js/report.js:14-17, 83-121`.
- [x] **Encapsulate `build/` & `exports/` paths and break `build.py` ↔ `export.py` cycle**
  - Add `build.pdf_path()`, `build.log_path()`, and `export.exports_dir()` (or make `export.bundle` default `out_dir`) so `web/reports.py:448, 457, 475` stops constructing internal filenames directly.
  - Break the deferred circular imports between `services/reports/build.py` and `services/reports/export.py`.

**Verify:** `test_report_pages.py`, `test_export.py`, `test_ownership.py`, then full suite.

---

## Step 4: Untangle `framework/` ↔ `documents/` & Remove Global Docutils State

Make the layering in `test/test_layers.py` completely true in both directions
and remove process-global docutils/RST side effects.

- [ ] **Break the `framework/` ↔ `documents/` circular dependency**
  - Move `Rst` and pure RST formatting/escaping helpers (`text`, `literal`, `indent`, `heading`) into `framework/markup.py` (or `framework/rst_escape.py`), and have `documents/template.py`, `services/reports/build.py:88`, and `services/requirements/flat.py:366-377` reuse them.
  - Invert plugin rendering registration: instead of `framework/plugins.py:120-152, 207-266` mutating `documents.core.RESOLVERS`, `ROLE_VALUES`, `template.FILTERS`, and `Snippets.plugin_folders`, register a rendering-registry adapter from `documents/` (or expose a clean `documents.registry` facade with atomic snapshot/rollback that also clears `Snippets._envs`).
  - Add `"automationv3.documents"` to `FORBIDDEN["framework"]` in `test/test_layers.py`.
- [ ] **Remove process-global `:req:` lookup (`rst.set_requirement_lookup`)**
  - Carry `requirement_lookup` on `documents.core.Context` (defaulting to `None`) and pass it explicitly into `RequirementReferences` in `documents/core.py:271-277` and `services/reports/sphinx_ext.py`.
  - Remove global `_requirement_lookup` / `_requirement_key` from `framework/rst.py:29-48` and the global mutation in `web/app.py:99` and `services/reports/sphinx_ext.py:64-65`.
- [ ] **Unify requirement rendering & RST→plain-text**
  - Move HTML rendering out of `framework/requirement.py:19-35` (`Requirement.__repr_html__` using legacy `html4css1` + regex on raw HTML) into `documents/` (or `web/documents.py`), sharing the docutils `shall`-marking logic with `framework/rst.py:59-74`.
  - Consolidate `_plain()` (`framework/rst.py:50-56`) and `plain_text()` (`services/requirements/rst_source.py:153-157`).
- [ ] **Stop global docutils directive pollution in `services/requirements/rst_source.py`**
  - Replace import-time `directives.register_directive("toctree"|"only"|"index"|..., Ignored)` (`rst_source.py:71-73`) with a scoped parser/directive lookup (or local `directives._directives` context/parser subclass) so importing `rst_source` never breaks Sphinx or other docutils parsers in the same process.
  - Deduplicate `AnyOption` (currently 3 copies: `framework/source.py:117`, `services/requirements/rst_source.py:35`, `services/requirements/sphinx/__init__.py:25`).
  - In `services/requirements/sphinx/__init__.py:78-92`, record `(docname, req_id)` on `self.env` in `RequirementDirective.run()` instead of regex-scraping rendered HTML files in `write_nav`.
- [ ] **Clean up `services/reports/sphinx_ext.py` & `sphinx_conf.py`**
  - Store build `Context` on `app.env` instead of module-global `_contexts[id(env.app)]`.
  - Register `run-document` with `app.add_directive("run-document", RunDocument)` instead of global `directives.register_directive`.
  - Move shared report CSS (`automation.css` or its document rules) so `services/reports/sphinx_conf.py:14` does not reach into `automationv3/web/static/css`.

**Verify:** `test_layers.py`, `test_docutils_facts.py`, `test_requirement_documents.py`, `test_export.py`, `test_report_pages.py`, then full suite.

---

## Step 5: Tighten `framework/` Core Abstractions & Deduplicate `lsp/`

Eliminate dynamic monkey-patching, private cross-module imports, and duplicated
Lisp/core analyzers between `framework/` and `lsp/`.

- [ ] **Make `BlockResult` and `lisp.Env` explicit**
  - Add declared fields `message: str = ""`, `trace: list = field(default_factory=list)`, `placeholders: int = 0`, and `exception: Exception = None` to `BlockResult` (`framework/block.py:48-65`).
  - Keep `trace` as `list[edn.Span]` inside `framework/` and serialize with `span._asdict()` once at the observer/event boundary, removing `_get()` dict-vs-Span duck-typing in `framework/excerpt.py:11-12` and `getattr` probes in `framework/executor.py`.
  - Add `has_local(key)` and `local_items()` methods to `lisp.Env` (`framework/lisp.py:34`) and replace `dict.__contains__(env, ...)` (`executor.py:240`) and `dict.items(env)` (`kernel.py:543, 573`).
- [ ] **Remove cross-module private (`_...`) imports**
  - Make `block_id(block)` public in `framework/block.py` (used by `framework/refs.py:191`).
  - Expose `maybe_runtime()` and a `silently()` context manager in `framework/steps.py` so `framework/refs.py:206` stops importing `_runtime` and `plugins/core/wait.py:162-167` stops reaching into `runtime.within(silent=True)`.
- [ ] **Remove hardcoded `"TBD"` & deduplicate small framework helpers**
  - Replace `head(form) == "TBD"` in `framework/analysis.py:189`, `documents/script.py:161`, and `lsp/service.py:555` with a helper checking `block.kind == PLACEHOLDER`.
  - Consolidate `is_step` (`framework/language.py:79` vs. `documents/script.py:70` vs. `documents/run.py:143`) and folder-ancestor walking (`framework/closure.py:189` vs. `framework/snippets.py:103`).
  - Consolidate `show`/`written`/`name_of` helpers (`value_blocks.py`, `verify.py`, `apollo/blocks.py`, `steps.py`, `markup.py`, `language.py`) and observer dispatch (`observer.py` vs. `steps.py:172`).
- [ ] **Share one `fn`/`defn` arity parser & `core.rst` linter between `framework/` and `lsp/`**
  - Extract `parse_fn_arities(form)` in `framework/language.py` replacing the 4 copies in `lisp.py:271`, `analysis.py:97`, `analysis.py:607`, and `lsp/service.py:786`.
  - Have `framework/closure.py` linters emit `Diagnostic` objects and expose `check_core(path, text)`, so `lsp/service.py` removes its copy-pasted `core_problems()` (`L427-L440`) and string-prefix matching (`L399-L407`).
  - Share block candidate resolution between `block.py`, `refs.py`, and `analysis.py`, and align `planning.py:symbols_in` (`L125-L132`) with `analysis.py` so maps/sets/binders are handled properly.
- [ ] **Tighten `source.parse` / `Card` boundary**
  - Replace raw docutils node dict indexing across `cards.py`, `closure.py`, `snippets.py`, `documents/script.py`, `lsp/service.py`, and `web/editor.py` with typed accessors/methods on `source.py` (and stop matching cards to statements by `id(statement.block) == id(card.node)` in `documents/script.py:109-110`).

**Verify:** `test_lisp.py`, `test_lisp_control.py`, `test_analysis.py`, `test_blocks.py`, `test_refs.py`, `test_cards.py`, `test_snippets.py`, `test_lsp.py`, then full suite.

---

## Step 6: Split `services/jobs.py` & Tighten Service / Worker / Kernel Boundaries

Break up the 881-line `jobs.py` god module, stop raw SQL outside stores,
and clean up `Kernel` ↔ `executor` ↔ `worker` coupling.

- [ ] **Split `services/jobs.py` by domain**
  - Separate into focused modules:
    1. Queue & worker registry (`services/jobs.py` or `services/queue.py`)
    2. Report creation, plan additions & reruns (`services/reports/queue.py` or `services/reports/runs.py`), removing deferred circular imports with `reports/{export,rollup}`
    3. Scratch run lifecycle (`services/scratch.py`), isolating `SCRATCH` folder special-casing
  - Deduplicate the plan-to-`enqueue` loop shared by `add_plan` (`L258-L279`) and `queue_scratch` (`L836-L846`), and replace `passed_combinations`'s manual latest-run scan (`L330-L340`) with `rollup.history()`.
- [ ] **Close raw SQL & `sqlite3.Row` leaks**
  - Add `latest_import_id(conn)` to `services/requirements/models.py` and replace the 3 raw `SELECT MAX(id) FROM imports` queries in `services/jobs.py:143`, `web/app.py:36`, and `web/api.py:126`.
  - Add dataclasses for `accounts.pending_link` / `link_device` (`services/accounts.py:153-168`) and stop leaking raw `sqlite3.Row` from `services/requirements/store.py:141-149`.
  - Move `expanded_nodes` / `open_tabs` SQL out of `web/workspace.py:27-44` and `web/editor.py:291-318` into a small service/store helper.
  - Move `PRAGMA journal_mode=WAL` configuration into `services/database.py` (e.g. `connect(..., wal=True)` or `init_db`) instead of repeating it in `cli.py:264, 299`.
- [ ] **Clean up `services/requirements/` internal duplication**
  - Make `staging.py:same()` / `preview()` reuse `store.facet_changes` so `hashed: false` attributes behave identically in staging preview and import.
  - Deduplicate `as_requirement` (`models.py:65` vs. `staging.py:101`), spec validation (`export.py:149` vs. `flat.py:240`), duplicate-ID detection (`export.py:244` vs. `store.py:181`), and `dirhtml` page path (`render.py:79` vs. `sphinx/__init__.py:87`).
- [ ] **Clean up `services/worker/kernel.py` & `worker.py`**
  - Refactor `worker.versions_installed` / `install_uuts` / `handles` to take `(host, environment, uut_versions: dict[str, Version])` and delete `Kernel._job()` (`kernel.py:499-502`).
  - Move `framework_fingerprint()` out of `services/worker/host.py` so `services/reports/build.py:228` doesn't depend on `worker.host`.
  - Stop `Kernel._run_card` (`kernel.py:640-660`) from round-tripping through `cards.rvt_source` and reversing its 3-space indent; construct statements directly from parsed forms + spans.
  - Replace string-matching in `Transcript.on_step_end` (`"returned "`, `"Stopped"`, `"unknown name"`, `PRECONDITION_TEXT` regex) with structured fields from `executor.py` / `language.parse_precondition`.
  - Synchronize `Kernel.names()` with a lock instead of catching `RuntimeError` (`kernel.py:573-575`).
  - Move `Console` lifecycle manager and `choices()` out of `web/console.py:47-156` into `services/worker/console.py` (sharing validation with `Kernel.__init__`).

**Verify:** `test_jobs.py`, `test_kernel.py`, `test_console.py`, `test_accounts.py`, `test_requirement_store.py`, `test_requirement_flat.py`, `test_requirement_uploads.py`, then full suite.

---

## Step 7: Clean Up `web/` & `cli.py` Boundaries and Duplication

Eliminate duplicated workflows, naming collisions, and scattered client-mode
logic across the HTTP/CLI adapters.

- [ ] **Fix the `central()` naming collision & tighten `client_mode` boundaries**
  - Rename `web/auth.py:central()` → `accounts_enabled()` (or `is_central_server()`) and `web/client_mode.py:central()` → `central_client()`.
  - Add a lock around `web/client_mode.py`'s TTL caches (`_CENTRAL_ENVIRONMENTS`, `_CENTRAL_UUTS`).
  - Split `services/requirements/models.py:workspace_context` into `read_workspace_context(root)` + validation so `web/workspace.py:79-87` (`configured_context`) stops duplicating `automation.json` parsing.
- [ ] **Unify local UUT build upload & listing across CLI and Web**
  - Fold `cli.py:601-648` (`local_versions`, `list_builds`) onto `services/builds.py` so both CLI (`--uut name=local`) and Web (`builds.UPLOAD`) go through one digest-matching + upload + `remember_used` implementation.
- [ ] **Consolidate duplicated web helpers**
  - **Base URL**: have `web/reports.py:367-370` (`server_url`) reuse `web/auth.py:external_url` / `settings().base_url` instead of the unset `SERVER_URL` config key.
  - **Open-redirect guard**: reuse `web/auth.py:safe_next` in `web/reports.py:361` and `web/requirements.py:227`.
  - **Worker endpoint list**: keep one `WORKER_API` definition shared by `web/auth.py:46-48` and `web/jobs.py:433-435`.
  - **Path validation**: standardize on `FileNode` and one shared relative-path/filename validator (replacing ad-hoc checks in `web/workspace.py:328`, `web/api.py:177`, and the 3x copy-paste in `web/editor.py:570, 624, 652`).
  - **Cache dirs beside `DB_PATH`**: extract one helper replacing the 3 copies in `web/app.py:40`, `web/requirements.py:299`, and `web/requirements.py:473`.
  - **Static HTML in shell**: extract one helper shared by `web/docs.py:21-31` and `web/reports.py:481-494`.
  - **LSP session encapsulation**: add `Server.is_open(uri)` on `lsp/server.py` so `web/editor.py:397` stops inspecting `self.server.service.texts`.
  - **Move `web/editor.py` file mutations** (`write`, `rename`, `unlink`, `mkdir`) into `services/workspace.py`.
  - **Untangle `web/jobs.py` utility exports**: move shared `workspaces()`, `reports_root()`, and `live_environments()` helpers to a neutral `web/` module so 5 other blueprints don't import from `web/jobs.py`.

**Verify:** `test_api.py`, `test_client_cli.py`, `test_client_web.py`, `test_editor.py`, `test_scratch_first.py`, `test_sign_in.py`, `test_builds.py`, `test_requirement_handlers.py`, then full suite.

---

## Step 8: `plugins/apollo/` Internal Cleanup (Optional)

Tighten the Apollo plugin's boundary with `apollo/model/` and align it with
`plugins/core/` conventions.

- [ ] **Encapsulate `model/sim.py` mutations**
  - Add a public fixer registration function on `model/sim.py` (removing `connectors.py:220` mutating `sim._fixers` at import time).
  - Add a `sim.with_crew(flight, crew)` helper (removing `apollo/uut.py:141-142` reaching into `sim.C.fresh` and mutating cached flight dicts).
- [ ] **Reconcile duplicated domain definitions**
  - Unify `high-gate` / `low-gate` phase predicates between `model/sim.py:80-85` (`REACHED`) and `apollo/handle.py:19-28` (`PHASES`).
  - Reuse `model/vehicle.py` constants/helpers for caution lights and propellant-low checks inside `apollo/connectors.py:130-136`.
  - Consolidate `to_edn` and `edn_config` in `apollo/handle.py:35-48`.
- [ ] **Align block conventions & break circular import**
  - In `apollo/blocks.py`: use `error=True` (or raise) for invalid arguments/exceptions in `ACTION` blocks instead of returning `BlockResult(False)` (`error=False`), and use `language.is_text` instead of `isinstance(args[0], str)` (`L99, L254`).
  - Break the `apollo/blocks.py` ↔ `apollo/handle.py` circular import (`C_REF` inline import at `handle.py:247`).

**Verify:** `test_apollo_model.py`, `test_apollo_plugin.py`, `test_demo.py`, then full suite.
