# Code base audit: cleanup, source text, and what needs more work

An audit of the repository on 2026-11-14, after the script editor was
merged. It read the framework, documents, language server and web layers
and scanned for names nothing else refers to. The scan was by name, not
by coverage, so it misses code that is referenced but never reached; CSS
and templates were not audited for unused rules.

The short version: there is very little dead code. The real problem is
that a script's source text is cut up five different ways, none of them
a docutils tree.

## 1. Cleanup (small, safe, first)

- [ ] **Unused functions.** `document.parse_rvt`,
  `documents/core.parse_fragment`, `steps.as_result`, `steps.usage_of`,
  `Statement._repr_rst_`, `edn.Span.as_dict`: named nowhere else in the
  app or its tests.
- [ ] **Empty and shim files.** `plugins/core/cli.py` is empty.
  `web/grouping.py` only re-exports `documents/grouping.py`, and only two
  tests import it.
- [ ] **Removed-form tombstones.** `defblock` and `passes?` still have
  error stubs in both `analysis.py` and `steps.py`. Drop them once no
  script uses those forms.
- [ ] **Simulator methods no script calls.** `had_event` and `set_sun`
  in `plugins/vm/sim.py`.
- [ ] **Packaging drift.** `requirements.txt` lists `schema` and
  `sphinx-tabs`, which nothing imports, and lacks `pygments` and
  `openpyxl`, which `setup.py` has. One source of truth.
- [ ] **Stale docs.** The README's code map omits `documents/` and
  `lsp/`.
- [ ] **Deprecations.** 18 `datetime.utcnow()` calls and one docutils
  `parser_name`.
- [ ] **Failing tests.** Two have failed since before the requirements
  work (URL-encoding expectations):
  `test_jobs...test_requirements_page_lists_linked_scripts` and
  `test_requirement_features.TestPages.test_a_spec_as_a_page`.
- [ ] **Test-only code that should be wired in.**
  `accounts.forget_expired` is only called by tests, so expired sign-in
  links and sessions are never purged on a real server.

## 2. Source text: one docutils tree (the main structural work)

A script is represented today as:

1. `document.split`: line regexes for `.. rvt::`.
2. `document.Part`: docutils per directive, edn per block.
3. `statements.Statement`: a Part plus its rendered rst.
4. `grouping.statement_item` dicts, for pages.
5. `cards.Card`: a second line scanner, with its own regex heading
   detection.

On top of that:

- `:req:` is found by regex in three places (`closure.py`,
  `lsp/service.py`, and the role itself).
- The language server finds definitions and UUTs by regex, separately
  from the analyzer.
- `editor.js` carries a hand port of `cards.build`.
- The workspace has two renderers for the same script: cards for the In
  work view, and the grouped statement view for a picked variation,
  Checked in, and run pages.

Direction: parse a script once with docutils into one tree. `rvt` and
`rvt-variant` become real directives whose nodes carry their source
lines, options and parsed forms; sections and `:req:` come from
docutils. Everything else is derived from that tree: the closure and the
analysis, the executor's statements, cards (a card is a top-level node's
line range), page rendering, and the language server's positions.

Decisions this forces:

- Whether byte-exact saving stays a requirement. It can, if cards are
  line ranges of nodes.
- Whether the browser keeps deriving the file's text itself or asks the
  server.

Write this up as its own plan before touching code.

## 3. Features that need more development

- **Project configuration.** Settings are spread over `automation.json`,
  the server TOML, the worker JSON and `client.json`. A single project
  file (plugins, UUTs and their configuration, server addresses) was
  raised earlier and is not started.
- **Editor.** No automated browser tests for its JavaScript. Problems on
  a closed card are a list, not a marker on the step. No folder rename
  or delete. No go to definition.
- **Language server.** No push channel. Never tried in a real editor. In
  the local client requirements can't be listed, so ids don't complete
  and aren't checked there.
- **Ref paths.** Only the Vehicle Manager implements `children`. Wrong
  paths are warnings in the editor only: the analyzer and the queue
  don't know about them.
- **Requirements import.** After a spreadsheet import the browser stays
  on the mapping URL. The client-mode CLI still writes an unused local
  database without `--server`.
- **Predicates.** No built-ins such as `between?`. `WaitSame` still only
  takes a group.

## 4. Parts that need definition

- Which plugin is the reference example? `sample` and `vm` both ship,
  and the demo uses both.
- Is `services/jobs.py` (876 lines, 58 definitions, no module
  description) one concept or several: the queue, workers, scratch,
  report planning?
- Should the grouped statement view survive, or should cards become the
  only way a script is shown, run pages included?
- Should a ref path that doesn't exist block queuing? Today it doesn't.
