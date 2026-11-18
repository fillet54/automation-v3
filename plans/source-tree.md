# One docutils tree for script source: implementation plan

Section 2 of `plans/cleanup-audit.md`. Today a script's text is cut up
five ways (`document.split`, `document.Part`, `statements.Statement`,
`grouping.statement_item`, `cards.Card`), with regexes beside them for
`:req:`, headings, definitions and UUTs. This plan replaces them with one
docutils parse of the whole file, and derives everything else from that
tree.

Branch: `source-tree`, off master. Paths are under `automationv3/`
unless they start with `test/`, `docs/` or `plans/`.

## What was checked before writing this (2026-11-15, docutils 0.23)

These facts shape the design. Step 0 pins each one in a test, so a
docutils upgrade that changes one fails loudly.

| Checked | Result |
| --- | --- |
| Whole-file parse of every script and `core.rst` in `test/data` and `demo` (410 files), with `rvt`, `rvt-variant` and `:req:` registered | No docutils message at warning level or above in any of them. |
| Section titles docutils finds, against the headings `cards.headings` finds, same 410 files | Identical in every file. |
| Cost of a whole-file parse | About 3 ms a file on average, 18 ms for the slowest. Today's code runs docutils once per directive, so this should not be slower; step 0 measures it. |
| A directive's position | Exact. `self.lineno` is its first line, `self.block_text` its lines, `self.content_offset` the line before its content, and each content line knows its own file line. This holds inside a nested parse too. |
| A title's position | Not reliable. At the top level `title.line` is the underline's line, not the title's. Inside a directive's nested parse it is `None`. |
| An inline node's position (a `:req:` role) | Line of the paragraph only. docutils gives no column. |
| Sections | Nest. An `rvt` block under a heading is a child of that section, not a top-level node. |
| A directive docutils rejects (unknown option) | Becomes a `system_message` whose `.line` is `None`; its `["line"]` attribute holds the directive's first line. |
| A directive whose option spec accepts any name | Works: the unknown option reaches `run()`. The spec must be truthy (a `dict` subclass with `__bool__`), since docutils reads an empty spec as "no options". A typed converter (a flag given a value) still makes docutils reject the directive, so the converters have to accept anything too. |
| A heading whose style skips a level (`===` then `~~~` under `---`) | An error in docutils. Today's cards accept it, because each prose card is rendered on its own. |
| The first title (step 0) | With docutils' default `doctitle_xform` a lone top section's title is lifted onto the document, so the tree stops mirroring the file. `source.parse` sets `doctitle_xform: False`. |
| A heading inside a nested parse (step 0) | Needs `nested_parse(..., match_titles=True)`, and then only a style deeper than the enclosing section's makes a title; one at that level or above is an error ("A level 2 section cannot be used here"). No `rvt-variant` in the repository holds a heading today. |
| An underline shorter than its title | Under 4 characters: ordinary text. 4 or more: a heading, with a warning. Today's cards say it is never a heading, while the rendered page (docutils) already shows one. |

Two consequences:

- docutils says **what** is in the file; for titles and `:req:` roles a
  small locator has to say **where**, by finding the node's own text in
  the lines its parent covers. That is one function each, in one module.
- "A card is a top-level node's line range" (the audit's wording) is
  wrong, since sections nest. A card is a line range **between**
  directive nodes, cut again at each title.

## Decisions

All settled (2026-11-15). The three that were open, marked **yours**,
were answered then.

| Topic | Decision |
| --- | --- |
| Backwards compatibility | None needed (your answer, 2026-11-15): this is v1, so existing scripts and stored results don't have to keep working. Statement numbers, page HTML and heading rules are free to change. |
| The one parse | `framework/source.py`: `parse(text, path=None)` returns a docutils `document`, cached by text and path. It never raises. Everything that reads a script calls it. |
| Directives | `rvt` and `rvt-variant` are real directives in that parse. `rvt-variant` parses its content with `nested_parse`, so its blocks and prose are child nodes rather than a second document. |
| A directive never fails | Both take any option and any argument, with every option read as plain text, and check them in `run()`. A wrong option or value becomes a `problems` entry on the node. So a bad block still has a node with exact lines, and nothing is scraped from `system_message` text. |
| Nodes | `rvt_block`: title, options, first and last line, content line and indent, code text, `forms` (each with its span, already in file coordinates), and the reader's error if the code stops reading. `rvt_variant`: variations, lines, children. `requirement_reference`: the id. |
| `:req:` | The role only records the id. Looking the requirement up moves to render time (a transform), so a parse no longer depends on the requirements store and the cache key loses `requirement_key`. |
| Where things are | Directive positions from docutils. Title and `:req:` positions from `source.locate`, the only place that searches lines. |
| Statements | `source.statements(tree)` is the flat list the executor, analyzer and closure use: one entry per form, carrying its block. Prose is not a statement any more. It replaces `Part` and `Statement`. |
| Statement numbers | A statement's index is its place among the script's forms. Results stored before this change will not line up; the demo data is generated again. |
| Cards | `cards.split` is derived from the tree. `Card` stays, as what the editor sends and receives, and `cards.build` stays as it is. The second line scanner and the regex headings go. |
| Byte-exact saving | Stays a requirement. Cards are line ranges, so their sources still join to the file. |
| Headings | docutils is the only authority. An underline of 4 or more characters that is shorter than its title now cuts a card, and a level skip is reported as a problem on the file. No script in the repository is affected. |
| Unreadable code | A block whose code doesn't read no longer makes the whole file unreadable. Its node carries the error with a span; the closure reports it there. |
| Rendering | One renderer that takes tree nodes. The whole-script page, a single card, a picked variation and a run page all call it. Pages follow the tree: each block is its own entry, so today's merging of neighbouring blocks goes. Run pages get the card layout too (**yours**, answered): a run page is the script's cards, read only, with each card's results posted into it as the run goes, using the page's existing refresh while a run is in progress. Cards are only editable in the editor. This settles the grouped-view question in audit section 4. |
| The browser's copy of `cards.build` (**yours**, answered) | Remove it. The page already posts to our own language-server route; it sends its cards instead of text, and the server builds the text and maps positions back to cards. About 120 lines of `editor.js` go (`assemble`, `written`, `variantWritten`, `unchangedPlaces`, `placeOf`). |
| Regexes that remain | `has_rvt` (a cheap line test, used to tell scripts apart when listing a folder), and the language server's `REQ_OPEN`, `CONSTRUCTOR_STRING` and `PREFIX`, which read what is being typed at the cursor, not document structure. |
| Module name (**yours**, answered) | `framework/source.py`, and `framework/document.py` is deleted at the end; the new name makes it obvious which callers have moved. |

## What the tree looks like

For the script in `test/test_cards.py`:

```
document
  section                         "Brake Monitoring"
    title, paragraph
    section                       "Requirements"
      title
      enumerated_list … requirement_reference id=VMCBRA00001
      rvt_block  lines 10-14  definitions  forms=[(def target 60)]
    section                       "Steps"
      title, paragraph
      rvt_block  lines 20-27  title="Apply the brakes fully"
                 variations=[degraded, limp-home]  forms=[…, …]
      rvt_variant lines 28-36  variations=[emergency]
        paragraph
        rvt_block lines 33-36  forms=[(Verify 1 = 1)]
      section                     "Notes"
        title, paragraph
```

What is derived from it:

| Derived | How |
| --- | --- |
| `source.blocks(tree)` | The `rvt_block` and `rvt_variant` nodes in file order, a variant's children under it. |
| `source.statements(tree)` | Each form of each block in file order, carrying its block (options, title, table, the variant's variations). |
| `source.problems(tree)` | Node problems, reader errors, and docutils messages at error level, each with a span. |
| `source.requirement_refs(tree)` | Each `requirement_reference` with its located span. |
| `source.title(tree)` | The first `title` node. |
| `cards.split(text)` | `blocks`, plus the prose line ranges between them cut at each located title. A block with problems is a "source" card. |

## Steps

Each step is one commit or a few, with the full suite passing (745
today). Steps 1 to 4 change no behaviour except where a step says so; step 5
changes how pages group blocks.

- [x] **0. Pin the facts and the baseline.**
  - `test/test_docutils_facts.py`: the table above as tests (directive
    lines, nested lines, title lines, the permissive option spec, short
    underlines, level skips, the doctitle transform, headings in a
    nested parse, every script parsing whole without messages).
  - `test/baseline.py`, a helper used only during this plan, wrote
    `test/baseline.json`: for every `.rst` git tracks (160 files), the
    old cards, and for the 87 with an rvt block, the old
    `document.parse` parts with their options, titles, table marks and
    every span inside each form. `test/test_baseline.py` compares the
    code with it; steps 2 and 3 point it at the new code. The demo's
    scripts are copies of `test/data/rvts`, so they are left out.
  - `test/bench_closures.py`: resolve every closure in the demo. The
    "before" numbers are in the notes below.

- [x] **1. `framework/source.py`.** The node classes, the two directives,
  the `:req:` role as a recorder, `parse`, `locate`, `blocks`,
  `problems`, `title`. Old code is untouched and nothing calls the new
  module yet.
  - Registering the directives and the role here means removing them
    from `document.py` and `rst.py` in the same commit. To keep those
    two working until steps 2 and 4, the old `parse_directive` reads the
    new node's attributes, and the role keeps rendering through a
    transform that `documents/core.py` applies.
  - Spans: a form's span is moved to the file with the content lines'
    own positions, replacing `content_position`. A variant inside a
    variant must come out right; test three levels.
  - Tests: `test/test_source.py`. Positions for every node kind; CRLF
    files; a block with a wrong option; a variant with no
    `:variations:`; code that stops reading halfway; a file that is not
    a script (Sphinx directives are ignored, not problems).

- [x] **2. Statements from the tree.** `source.statements`, then move its
  users one at a time: `closure.py` (`read_parts`, the lints),
  `analysis.py`, `executor.py` (`_execute`, `load_definitions`,
  `load_script_definitions`, `find_variation`), `lsp/service.py`
  (`core_errors`).
  - Parity test: `test_baseline.py` compares `source.statements` with
    the baseline's parts, prose left out: the same forms in order, with
    the same spans, options, titles and table marks.
  - The executor no longer reports prose (`on_comment`): nothing reads
    those events. `observer.py` and the worker lose it. Statement
    indexes in events count forms only.
  - Generate the demo's runs again, so its pages line up.
  - `closure.resolve` keeps today's messages for an unreadable file in
    this step (it turns `source.problems` into "could not be read").
    Better messages come in step 4.
  - Deleted: `document.split`, `document.parse`, `document.forms`,
    `document.Part`, `limit`, `table_block` and `definitions_section`
    (moved to `source.py`). `parse_directive`, `content_position` and
    `RvtError` stay until step 3: `cards.py` still uses them.

- [x] **3. Cards from the tree.** `cards.split` built on `source.blocks`
  and `source.locate`.
  - Deleted from `cards.py`: `chunks`, `headings`, `is_adornment`,
    `prose_cards`, `rvt_card`, `variant_card`, `moved`. `Card`,
    `build`, `written`, `rvt_source`, `variant_source`, `walk` stay.
  - Deleted from `document.py`: `RVT_START`, `VARIANT_START`,
    `HEADING_LINE`, `document_title`.
  - Tests: `test_cards.py` passes unchanged except
    `test_not_headings`, which gains the new short-underline rule. Every
    `.rst` in the repository, `docs/` included, still joins back to its
    text and builds to itself. `test_baseline.py`: cards equal the
    baseline cards for all 160 files, except where the short-underline
    rule changes one (listed in the notes).
  - `web/editor.py`: `heading_lines` and the re-split of an edited prose
    card in `card_html` use the tree.
  - Behaviour change: update `docs/operating/editor.rst`. Also say
    there that a heading inside an `rvt-variant` must use a style deeper
    than the section around it (see the notes).

- [x] **4. Requirements, problems and names from the tree.**
  - `source.requirement_refs` replaces the language server's `REQ`
    regex and (`closure.requirement_refs` already answers from it, since
    step 2)
    `Service.requirement_refs`. `services/requirements/links.py` calls
    the new one.
  - `rst.requirement_role` is gone; a transform in `documents/` turns
    `requirement_reference` nodes into today's inline nodes when a page
    is rendered. `statements._statements` and `script._parsed` drop
    `requirement_key` from their cache keys.
  - Closure errors for unreadable blocks carry spans (a behaviour
    change: one message per bad block, placed on it, instead of one for
    the file). `Service.unreadable` and its message scrubbing regex are
    deleted.
  - The language server's `DEFINITION` and `UUTS` regexes are deleted:
    `Service.names` uses `Service.definitions`, which reads the block's
    `forms`, and UUT handles come from the `uut` forms with
    `language.head`. A block still being typed gives the forms that
    read, as `readable=True` does today.
  - `Service.code_before`, `missing_paths` and `definitions` take blocks
    from `source.blocks` instead of calling `cards.split`.

- [x] **5. One renderer.** `documents/script.py` takes tree nodes.
  - `render(nodes, variation=None, results=False, diagnostics=())`
    writes the page rst for any run of blocks and prose. The whole
    script is all of them; a card is one.
  - Structure comes from the tree instead of being rebuilt: a titled
    entry is an `rvt_block` with a title, a scoped entry is a block or
    variant with variations, a definitions entry is a `:definitions:`
    block. `grouping.group`, `group_blocks`, `group_definitions`,
    `titled_block` and `statement_item` are deleted. What stays in
    `grouping.py`: `roll_up_definitions` for a picked variation,
    `block_state` and the durations.
  - `framework/statements.py` is deleted. `documents/run.py`,
    `services/reports/data.py` and `services/reports/sphinx_ext.py` read
    `source.statements`; a statement's page rst comes from
    `rst.repr_rst(form)` where it is used.
  - `web/editor.card_html` and `web/workspace.render_file` both call
    `render`.
  - Run pages use the card layout, read only: `documents/run.py`
    renders the script's cards with `results=True`, so each card's
    step results sit in it. While a run is in progress the page's
    existing refresh (`reports/page.html`, every 3 s) fills cards in as
    steps finish. Nothing on a run page is editable.
  - Tests: `test_statements.py`, `test_titled_blocks.py`,
    `test_variation_scopes.py`, `test_tables.py` and
    `test_report_pages.py` are rewritten against the new pages where
    they assert on merged entries or statement indexes. Check a script
    page, a picked variation and a run page in headless Chromium.

- [x] **6. The browser stops building text.**
  - `cards.build` also returns places: for each card its first and last
    line and where its code starts. Tested against the positions
    `cards.split` gives for the same text.
  - The language-server route accepts `{path, cards}` for a sync, builds
    the text, and answers positions as (card, line, column). Hover,
    completion and signature requests name a card and an offset in it.
  - `editor.js` loses `assemble`, `derive`, `written`, `variantWritten`,
    `unchangedPlaces`, `placeOf` and `VARIANT_HEAD`. `showProblems`
    reads the card from the answer.
  - Check in headless Chromium: squiggles land on the right characters
    in a block inside a variant, before and after an edit above it.

- [ ] **7. Finish.**
  - Delete `test/baseline.py`, `test/baseline.json`,
    `test/test_baseline.py` and `test/bench_closures.py`.
    (`framework/document.py` went in step 3.)
  - Docs: `README.md` code map, `docs/scripts/` where it describes how a
    script is read, `docs/blocks/writing-blocks.rst` if it names
    `Statement`.
  - Tick section 2 in `plans/cleanup-audit.md` and record what is left.

## What exists at the end

| Representation | What it is | Module |
| --- | --- | --- |
| The tree | docutils nodes, one parse | `framework/source.py` |
| Statements | A flat view of the tree for running and checking | `framework/source.py` |
| `Card` | What the editor sends and receives: a line range, or fields for a fresh card | `framework/cards.py` |
| The page document | rst the renderer writes from tree nodes, parsed by docutils into HTML | `documents/script.py` |

`Part`, `Statement`, statement item dicts, the second line scanner, and
seven regexes are gone. Blocks still write rst through `as_rst`; that
plugin API does not change.

## Risks

- **Old results.** Runs stored before step 2 show results beside the
  wrong statements. Accepted; anyone with a database worth keeping
  would have to run again.
- **Shared, cached trees.** docutils trees are mutable and the renderer
  runs transforms. `parse` returns the cached tree; anything that
  changes a tree must copy it first, as `documents/core.resolved` does.
- **Speed.** Planning a report resolves many closures. If step 0's
  benchmark is slower after step 2, cache statements per text, not only
  trees.
- **docutils upgrades.** Title lines and nested positions are
  undocumented behaviour. Step 0's tests are the guard.
- **Files that aren't scripts.** The editor opens any `.rst`. Sphinx
  directives and roles are unknown to docutils; they must stay part of a
  prose card and never count as problems.

## Notes as we go

**Step 0 (2026-11-15).** Suite: 745 tests passing before, 769 after
(22 facts tests, 2 parity tests).

- The plan's "410 files" was 82 scripts in `test/data/rvts` plus four
  copies of them in the demo. The baseline uses every tracked `.rst`
  instead: 160 files, 87 with rvt blocks (the extra five are in
  `docs/scripts/`), 612 parts. None fails to read today.
- Benchmark before (`python -m test.bench_closures`, 312 closures over
  the demo's four workspaces, x86_64, 12 cores): cold 8.9 to 11.2 s,
  best warm 8.9 to 9.4 s, about 30 ms a closure. A profile puts 85% of
  it in `document.parse`, two thirds of that in `parse_directive`
  (3,180 `publish_doctree` calls, about 6 ms each). One whole-file
  parse (about 3 ms) should cut it a lot. After: (step 2).
- New fact: docutils' doctitle transform lifts the first title onto the
  document, so `source.parse` turns it off to keep the tree shaped
  like the file.
- New fact, a decision that falls out of it: `rvt-variant` has to parse
  its content with `match_titles=True` to allow headings at all, and
  then a heading inside a variant must use a style deeper than the
  section the variant sits in; one at that level or above becomes a
  problem on the file. Today's cards accept any heading there. No file
  in the repository has a heading inside a variant, so nothing breaks;
  it goes in the editor docs with the other heading rules (step 3).

**Step 1 (2026-11-15).** Suite: 789 passing (20 new in
`test/test_source.py`). Parity with the baseline holds: the old reader
and cards, now reading directives through `source.parse`, give exactly
the snapshot for all 160 files. Checked by hand as well (not yet a
test, steps 2 to 4 make it one): the new blocks' 452 forms equal the old
parts, spans and nested spans included; the 511 titles `locate` finds
are the old cards' headings, line for line; every `:req:` span covers
exactly its role.

- `source.parse` runs the parser alone, with no transforms (so no
  doctitle lift, and no reference or substitution errors that only
  Sphinx would resolve). Messages are collected by a reporter
  observer into `tree.messages`; the file's lines are `tree.lines`.
- A directive works out its own columns from `block_text` plus the
  indent of the variant it is in, so it needs nothing from `parse` and
  works under any publisher.
- The reader's error is `node["error"]`, apart from `node["problems"]`
  (options, title): the old cards treat a bad option as a source card
  but unreadable code as an rvt card. `source.problems` returns both.
- An unknown option keeps docutils' wording (`unknown option: "x"`);
  two tests assert on it.
- The `:req:` transform (`rst.RequirementReferences`) is applied by
  `documents/core.parse`, by `core.parse_many` (fragments), and by the
  reports' Sphinx extension (`app.add_transform`); checked with a small
  Sphinx build, since the export tests skip without latexmk.
  `documents/core.py` imports it inside a function: `framework/rst.py`
  imports `documents` through `markup`.
- `source.walk` and `source.requirement_refs` are in already (the
  latter is step 4's; nothing calls it yet).
- Found for step 4: the old `REQUIREMENT_REF` regex counts `:req:`
  inside ``literal`` text (three files in `docs/`); the tree doesn't.
- A level-skip message is placed on the offending title's line.
- Benchmark after step 1: cold 3.2 to 3.4 s, warm about 3.0 s, about
  10 ms a closure (from 30). The old reader still parses each
  directive separately, but through the bare parser and with the
  repeated directive texts cached.

**Step 2 (2026-11-15).** Suite: 790 passing. `test_baseline` now reads
the parts from the tree (`source.statements`, with the prose from
`statements.parts`) and still equals the snapshot for all 87 scripts,
prose included.

- `source.Statement` is the form, its span, its block node and its
  index, with the block's fields as properties (`options`,
  `variations`, `title`, `line`, `table`, `definitions`, `applies`).
  `source.statements` keeps the list on the tree; `source.table_steps`
  replaces `document.table_block`; `source.unreadable` is the problems
  that make a file unreadable (blocks' and variants' problems, and code
  that doesn't read), apart from docutils' messages about prose, which
  never made a file unreadable before.
- The executor runs on copies of the forms (`executor.read`): the
  tree, and so its forms, is cached and shared.
- `closure.read_parts` became `read_statements`, with the same "could
  not be read (...)" message (the first problem's).
- `closure.lint_variation_scopes` takes the file's text and walks the
  tree, so an rvt-variant's names are checked even when it holds only
  prose. With forms-only statements that check was lost (a test
  caught it): before, the variant's prose parts carried its names.
- `closure.requirement_refs` answers from `source.requirement_refs`
  now, not in step 4: there was no other reason to keep the old reader
  for it. The one change: `:req:` in ``literal`` text no longer counts.
- Pages: `statements.parts(tree)` gives the rendered list (prose and
  forms, as before) from the tree, until step 5; each rendered
  statement carries its form `index` (None for prose).
  `documents/script.py` numbers its items with it, and `documents/run.py`
  and `reports/data.step_name` look results up among the forms only.
- No test rendered a run page with its results, so nothing would have
  caught results beside the wrong step. `test_statements.TestRunPage`
  runs a script with prose between its steps and checks each result
  sits by its step; shifting the indexes by one fails it.
- The demo stores no runs (its database has no jobs, `reports/` is
  empty), so there was nothing to generate again.
- Benchmark after step 2: cold 1.8 to 1.9 s, warm about 1.5 s, about
  5 ms a closure (from 30 before step 1). Cold is flattered: the
  demo's four workspaces hold the same scripts at the same paths, so
  three of four parses come from the cache.

**Step 3 (2026-11-15).** Suite: 795 passing. Cards from the tree equal
the baseline cards for every tracked `.rst` not edited since (all but
`docs/operating/editor.rst`, edited in this step). The snapshot now
holds each file's SHA-256 as it was, and `test_baseline` leaves out a
file edited since (failing if ten or more are).

- `cards.split` cuts the text at `source.blocks` (each directive runs
  through the blank lines after it, as before) and cuts prose again at
  each title `source.locate` finds, from its overline if it has one. A
  card's `level` is the number of sections around its title. A block
  or variant with problems is a source card; one whose code doesn't
  read is still an rvt card, as before.
- `framework/document.py` is deleted, not in step 7: all that was left
  was `has_rvt`, now `source.has_rvt`. Report titles use
  `source.title` (the title's text, inline markup read, where the old
  `document_title` gave the line as written).
- `web/editor.heading_lines` reads the card's first title from the
  tree; it agrees with the old rule on all 511 headings in the
  repository. The re-split of an edited prose card in `card_html`
  goes through the new `cards.split` unchanged.
- Found while doing this, a behaviour change step 2 had brought in
  silently: a `.. rvt::` line straight after a line of text, with no
  blank line, is part of that paragraph to docutils, so since step 2 it
  wasn't a block and never ran (the old regex splitter ran it).
  `source.swallowed` now reports each such line, as part of
  `source.unreadable`: the script can't be read until the blank line
  is added, and the editor shows it on the line. `.. rvt::` inside a
  literal block is still just text. `test_cards` had used such a line
  as a fixture; it now has the blank line, and two new tests pin the
  rule and the short-underline heading. `test_not_headings` passes
  unchanged (its short underline is under four characters).
- docutils' own errors about a script's rst (a level skip, a heading
  inside a variant at its section's level) were not shown anywhere.
  `Service.prose_problems` shows them in the editor, as errors on their
  line. They don't stop a script being queued; step 4 decides that with
  the rest of the closure's messages.
- `docs/operating/editor.rst` says how headings are found now, and that
  a directive needs a blank line before it.

**Step 4 (2026-11-15).** Suite: 800 passing (four new tests: each
unreadable block placed on itself, in a script and in a core.rst, as
closure errors and in the editor; completion before the closure is
read; a cached page showing a requirement's text as it is now).

- `:req:` is looked up when a page is rendered: `core.resolved` and
  `core.resolved_block` apply `rst.RequirementReferences` after
  resolving, and `core.parse` no longer does. So `script._parsed`,
  `statements.get_statements` (now cached directly) and
  `web/documents.parsed_report` are cached by their text alone. The
  finished run page's HTML cache keeps `requirement_key`: that HTML
  holds the text. A test helper that wrote a parsed tree without
  resolving it now resolves it, as every page does.
- Closure errors for blocks that can't be read: one per block, as a
  `Diagnostic` with its span (`closure.read_statements` takes the
  closure's diagnostics), so the error reads `s.rst:2:4: unknown
  option: "defs"` and the editor places it on the option; the reader's
  error sits where reading stopped. The reader's message no longer
  carries its own "(line: n, col: m)", relative to the block's code.
  `Service.unreadable` and its message scrubbing are deleted; the
  editor's problems for a core.rst come from `Service.core_problems`.
- The language server's `REQ`, `DEFINITION` and `UUTS` regexes are
  deleted. `requirement_refs` and hover read `source.requirement_refs`
  (hover hits the role's own span); `names` reads `definitions`, and
  the UUT handles of a script not yet resolved come from its `uut`
  forms. `definitions`, `missing_paths` and `code_before` walk the
  tree's blocks (`Service.blocks`: those without problems, at any
  depth); `code_before` still counts the blank lines after a block as
  the block's.
- Decided here: docutils' own errors about prose (a level skip, a
  heading inside a variant at its section's level) are shown in the
  editor (step 3) but don't stop a script being queued. They change
  how the page looks, not what runs.
- Benchmark: about 5.7 ms a closure, within the noise of step 2's.

**Step 5 (2026-11-15, finished 2026-11-16).** Suite: 798 passing.
`documents/script.py` renders pages from the cards (`render(text,
found=None, ...)`): each rvt block is its own `block` container (titled
and definitions blocks collapsible, a block's own variations wrapped
`scoped`), a variant a `scoped variant` container, prose top-level so
its headings stay sections. `script.view(statement)` gives a
statement's rst and precondition where pages and snippets use them.
Cards keep their tree node (`Card.node`). `framework/statements.py` and
`documents/grouping.py` are deleted (`block_state` and the durations
too: only their own tests used them). `run.py`, `reports/data.py` and
the Sphinx extension read `source.statements` and `script.render`; the
editor and the workspace page reach `render` through
`documents.script_document`. Tests are rewritten against the page
(`test/rvt.page_entries`).

- `automation.css`: a `block` outside the editor has 20px above and
  below, about what two editor cards give, and the rule that joins
  neighbouring collapsibles into one bordered run no longer joins two
  blocks. Inside the editor the card does the spacing, so a block there
  is left alone.
- Checked in headless Chromium against a throwaway demo
  (tc_bra_00004.rst): the script page (editor) looks as before; with
  `emergency` picked, the limp-home definitions roll up into the one
  `headroom` section, the normal/limp-home variant is left out and the
  emergency variant shows; a scratch run of `emergency` shows each
  result inside its block, the variant's step inside the variant.

**Step 6 (2026-11-17).** Suite: 808 passing (10 new).

- `cards.placed(cards, count)` gives `build`'s text and a `Place` for
  each card in walk order (a variant before what it holds): its lines,
  and the line and column where what its editor holds starts. A fresh
  card's place comes from how it is written; a kept card's from cutting
  its own source again, so a kept variant's children are placed without
  the page saying where they were (`code_offset`, `line_in`,
  `code_indent` and `indent` are gone from the card payload). `build` is
  `placed` without the places. `test_cards.TestPlaced` checks the
  places against `split`'s positions of the built text: kept, fresh,
  only blocks fresh, a fresh variant around kept cards, a kept variant
  inside a fresh one.
- The `/lsp` route speaks cards, not JSON-RPC: `{session, start, sync:
  [{path, cards, count}], close, request: {method, path, card, line,
  character}}`, answered with `problems` per path (each with its card,
  `from`/`to` in that card's editor, and its `line` in the file for the
  Problems panel) and the request's `result` in card coordinates.
  `web/editor.PageSession` wraps the `Server` and does the
  translation; the `Server` and the stdio server are unchanged. A
  session the server forgot answers `reset`, as before.
- `editor.js` keeps, per tab, `order`: the card elements of the cards
  the server has, set when that sync's answer arrives (posts are
  queued, so answers and orders line up). An unchanged sync (undo
  draws the same cards again) only updates `order`, after whatever is
  on its way. Gone: `assemble`, `derive`, `written`, `variantWritten`,
  `unchangedPlaces`, `placeOf`, `VARIANT_HEAD`, the text helpers and
  the didSave message (about 125 lines).
- A fix on the way: a prose card inside a variant is now placed at its
  indent (the old browser code used column 0), so a docutils problem
  in it would land 3 columns off.
- Checked in headless Chromium (driven over the DevTools protocol from
  Node, a throwaway demo): `max-pressure` misspelt in the block inside
  the `emergency` variant of tc_bra_00004.rst is underlined on exactly
  `max-presure`; after three lines are added to the first section, the
  block (and so its variant) written again, it still is, the Problems
  panel says line 59 (56 + 3), and clicking it reveals the block.
