# Script editor: implementation plan

Today the workspace page is a file tree and a read-only viewer. This plan
turns it into an editor: scripts open in tabs, are edited as cards (one per
section and per rvt block) rather than as one text file, and a language
server gives completion and live errors, to the web editor and to any other
LSP client.

Branch: `rst-editor`.

## Decisions (from the design interview, 2026-11-12)

| Topic | Decision |
| --- | --- |
| Where saves go | Straight to the worktree's files on disk. Git stays outside the editor. Single-user and local-client modes edit; the central server does not. |
| Edit unit | Sections as cards. A prose card and an rvt block card are each edited in place. Code inside a block is text, not per-form rows or generated fields. |
| Prose cards | One card per section heading (prose is split at headings as well as at rvt directives), so the page has an outline. Edited as rst source in CodeMirror; rendered when closed. |
| rvt cards | The header has fields: title, a Definitions toggle, a variations picker. The body is only the forms. The directive line and indentation are never typed. |
| rvt-variant | A container card with its variations in its header; the cards inside are ordinary cards and can be moved in and out. |
| Byte fidelity | Saving rewrites only the cards that changed. Untouched text stays byte-for-byte the same. |
| Tabs | The workspace page becomes the editor: same tree, the right side gains a tab strip. A file opens rendered, as now; clicking a card edits it. No separate edit mode. Open tabs are remembered per workspace in the database. |
| What opens how | Scripts and `core.rst` as cards; other text files as one plain editor; binary files view-only. |
| Saving | Explicit, per tab (Ctrl+S or Save); an unsaved dot on the tab. Unsaved text is also kept in the browser's storage, so a reload doesn't lose it. |
| Disk changes | Checked when the tab regains focus and before every save. A clean tab reloads quietly. A dirty tab shows a bar: keep mine, take the file's, or see the difference. Save never silently overwrites a file that changed since it was opened. |
| Run | Run in scratch saves the tab first, and offers to save other unsaved tabs in its closure. What ran is what is on disk. |
| New | A skeleton (title, Requirements, empty Steps block) in a folder of the tree; the file name is derived from the title and editable. Also offered from a requirement's page, pre-filling its `:req:` and text. |
| Clone | Pick a folder and a new title. The copy opens as an unsaved tab, `:req:` links kept. Nothing is on disk until it is saved. |
| File operations | Rename, move, delete (confirmed; git is the undo), new folder (optionally with a `core.rst`). |
| Undo | One history per tab covering typing in any card and card-level changes. So the tab's model is an ordered list of cards, the file text is derived from it, and the history is ours. |
| Editor widget | CodeMirror 6, built once with esbuild into one committed static file. Running the app needs no Node. |
| Language server | A real LSP server from the start: `automation-v3 lsp` over stdio for VS Code and Neovim. Hand-written (JSON-RPC and the messages we need), no new dependency, transport-free core. |
| LSP in the browser | The same core behind two web routes: POST a message, and a server-sent event stream for what the server pushes (diagnostics). No websocket, waitress stays. |
| LSP features, first version | Diagnostics (framework/analysis.py, live, on unsaved text); completion of names; hover and signature help; `:req:` id completion, hover and unknown-id errors; ref path completion; hover shows a symbol's value when it resolves statically. Go to definition is not in the first version. |
| Static values | Literals and aliases only: `(def target 60)`, `(def nav cpu1.app.nav)`. Nothing is evaluated. A ref constructor with a literal path, `(connector "sys.cpu1")`, is recognised as a ref of that kind. |
| Ref paths | A plugin hook on the Ref kind: `children(path)` gives the names below a path, each with a type and description, answered offline. Used for completion, hover and "no such path". A group offers the paths all its members share. Plugins without the hook get none. |
| Diagnostics display | Squiggles in the open card; a marker with the message on a closed card's step; an error count on the tab and on the file in the tree; a Problems panel for the open tabs that jumps to the card. |

## Steps

Each step is one commit (or a few), with tests, keeping the suite as green
as it is on master (two known failures there). Steps that change what users
see update the docs in the same commit.

- [x] **0. Plan.** This file.
- [x] **1. Cards and saving.**
  - [x] 1a. `framework/cards.py`: split a document into cards (prose per
    heading, rvt, variant containers) with exact source spans; rebuild the
    text from cards; an rvt card to and from its directive source. Round
    trip is byte-identical for untouched cards.
  - [x] 1b. Editor API: read a file as cards (with rendered HTML and a
    content hash); render one card's source; save (refused with 409 when
    the file's hash is not the one the tab opened).
  - [x] 1c. CodeMirror bundle (esbuild, committed) and how to rebuild it.
  - [x] 1d. Workspace page: tab strip, tabs remembered per workspace,
    cards that open into editors, rvt header fields, add and delete a
    card, save, unsaved dot, drafts in browser storage.
  - [x] 1e. Disk-change check on focus and on save, with the three-way bar.
  - [x] 1f. Plain-text tabs for other text files. Editing is off on the
    central server.
  - [x] 1g. Docs: operating guide for the editor.
- [x] **2. File operations.** New (skeleton, and from a requirement's
  page), clone (opens unsaved), rename, move, delete, new folder.
- [x] **3. Language server.** Transport-free core; `automation-v3 lsp`
  (stdio); the two web routes; document sync from the tab's derived text;
  diagnostics and name completion in the cards.
- [x] **4. More language features.** Hover and signature help, `:req:`
  ids, static values on hover.
- [x] **5. Ref paths.** The `children(path)` hook, completion, hover,
  "no such path".
- [ ] **6. The rest of the editor.** Tab-wide undo, variants as container
  cards with drag in and out, card reordering by drag, the Problems panel,
  counts on tabs and tree, Run saves first.

## Notes as we go

(Things found while building that the next session needs to know.)

- **How the pieces fit (step 1).** `framework/cards.py` cuts text into
  cards and builds it back. `web/editor.py` holds the routes
  (`/workspace/<id>/editor/render|state|diff|save`, `/workspace/<id>/tabs`)
  and is registered on the workspace blueprint. `static/js/editor.js` is
  the whole browser side; `frontend/` builds the CodeMirror bundle.
- **The page is the model.** Each card element keeps what the server cut
  it from (`el._card`); an edited or new card is the same with
  `source: null`. Save sends every card back, so the server needs no
  memory of the file as the tab opened it, and "keep mine" is a forced
  save. A dirty tab's cards are also kept in localStorage, keyed by
  workspace and path, with the hash of the file they were cut from.
- **Cards only show in the In work view with no variation picked.** A
  picked variation or the Checked in view renders the old way, read-only.
- **A variant is one source card for now** (step 6 makes it a container).
  The variations field on a block is a comma-separated input, not yet a
  picker of the script's declared variations.
- **A prose card's heading is rendered by us**, not docutils (a lone
  section title would be promoted to the document title and dropped), so
  inline markup in a heading shows as typed.
- **Delete and move have no undo until step 6**; Discard edits is the
  way back.
- **Editing is off when `auth.central()`**, even over local worktrees,
  and for `MirrorWorkspaces` (`editable = False`).
- **Testing in a browser.** The Chrome extension was not connected, so
  step 1 was checked with headless Chromium driven over the DevTools
  protocol from Node (no extra packages). There are no automated browser
  tests in the suite: `test/test_editor.py` covers the routes and
  `test/test_cards.py` the cutting and rebuilding.
- **Step 2 (file operations).** Routes in `web/editor.py`:
  `editor/folders|new|clone|move|delete|folder`. New and clone write
  nothing: they answer with cards, which the page stores as a draft whose
  hash is "" and opens as a tab; `/view` renders an empty document for a
  path that isn't on disk (hash ""), and the draft fills it. Tabs for such
  drafts are reopened on page load (`unsavedFiles` in editor.js).
  Discarding one closes its tab. The dialogs are one `<dialog>` filled
  from the `DIALOGS` table in editor.js.
- **"Write a script for this"** on a requirement's page links to
  `/workspace/<ws>?new=1&requirement=ID`. It only shows where editing is
  on, so not in the local client: there requirement pages are the central
  server's, which can't link back to a person's machine.
- **Rename, move and delete are for files only**, not folders.
- **Step 3 (language server).** `automationv3/lsp/`: `service.py`
  (problems and completion, no protocol), `server.py` (LSP messages in,
  messages out, no transport), `stdio.py` (`automation-v3 lsp`). The web
  route is `POST /workspace/<id>/lsp` in `web/editor.py`, one Server per
  page session.
- **No event stream, against the interview's decision.** The decision was
  POST plus a server-sent event stream. Nothing the server sends is
  asynchronous: diagnostics are computed while handling the message that
  caused them, so the POST answers with every message, responses and
  notifications. A stream would also hold one of waitress's 8 threads per
  open page. Add one if something ever needs to push on its own.
- **Unsaved text reaches the analyzer through `closure.resolve(...,
  texts=)`**, which maps paths to text standing in for the files on disk.
- **The page derives the file text itself** (`derive` in editor.js, a port
  of `cards.build` and `cards.written`: keep the two in step) and records
  where each card, and each block's code, is in it, to place diagnostics
  and to say where the cursor is.
- **Completion reads names with a regex and a small bracket scanner**, not
  the analyzer, because code being typed rarely reads cleanly. UUT handles
  and variation values come from the last closure that did.
- **Unreadable code is reported on its own**: while a block can't be read,
  only that is reported, since nothing else can be checked.
- **Diagnostics on a closed card are a list under the card**, not yet a
  marker on the step (step 6). The diagnostics drawn into the page when it
  was made are hidden once the server answers (`.ed-doc.is-live`).
- **A collapsed block** (definitions, titled) toggles when clicked; use
  the card's Edit button, or expand it and click its code.
- **Step 4 (hover, signatures, requirement ids, static values).** All in
  `lsp/service.py` (`hover`, `signatures`, `static`, `unknown_requirements`)
  and `lsp/server.py` (`textDocument/hover`, `textDocument/signatureHelp`).
- **Static values** are a `Static`: a literal, a ref (kind and path) or a
  group. A function makes refs when it is a Ref subclass or is marked with
  `refs.constructs(RefType)`; nothing is called. Step 5 builds on
  `Static.ref_type` and `Static.path`.
- **Requirements reach the service through a provider** with `find(id)`
  and `all()`: `PageRequirements` (web/editor.py) for the page's request,
  `lsp/requirements.py` for stdio (the database at `--dbpath`, if there).
  Unknown ids are only flagged when `all()` lists some, so not in the
  local client, whose central server answers one id at a time.
- **Definitions are read from what reads** of a block
  (`edn.read_all_with_spans(readable=True)`), so names defined earlier in
  a block still being typed hover and resolve.
- **The text sent to the server keeps the spaces being typed** at the end
  of an edited card (`current(card, true)`, and no `withoutTail` for fresh
  cards in `derive`): otherwise the cursor is past the end of its line
  there and the argument count is off.
- **Signature help is a line under the block's editor**, not a tooltip.
- **The editor's script addresses carry a version** (`editor.script_version`,
  the files' mtime), so a browser doesn't pair an old script with a new
  server.
- **Step 5 (ref paths).** `Ref.children(path)` classmethod returning
  `refs.Child(name, leaf, detail, doc)`s, `None` when it can't say. The
  Vehicle Manager answers from its `CONNECTORS` table
  (`sim.connector_children`). In `lsp/service.py`: `lookup` walks a path
  from the top, one `children` call per level (cached per check), and
  gives the `Child` or a `Missing`; `ref_paths` and `constructor_paths`
  complete; `missing_paths` warns.
- **Missing paths are warnings, not errors**, because the analyzer (and so
  the script's page and queuing) doesn't know about them: an error only in
  the editor would disagree with the page about whether the script can be
  queued.
- **A dotted name is only checked for what it adds** to its base; a bad
  path in a constructor call is reported there, once. Names bound by
  `fn`/`defn`/`let`, UUT handles and variation symbols are not followed.
- **Path completion replaces the whole dotted word**: the LSP item has a
  `textEdit` from the word's start; the web client's word already includes
  the dots.
