# The console: run a card or a line from the editor

While writing a script, run one card or one form against a live UUT and
see what happened in a console panel on the editor page, without
queuing a run, then edit the step and run it again. Behind
it is a **kernel**: a long-lived interpreter, like a Jupyter kernel. It
keeps the script's Lisp env, the UUT handles and the environment's clock
between commands. The kernel can be reset (fresh definitions, fixed
values released) or restarted (the UUT started fresh too).

Paths are under `automationv3/` unless they start with `test/`, `docs/`
or `plans/`.

## Scope

- **Local only.** A kernel runs only where the app has a worker in its
  own process: `automation-v3 client --config ...` (the local client
  with a local worker), `automation-v3 server --local-worker`, and
  `automation-v3 demo`. With no local worker the console isn't offered.
  Remote workers are out of scope; nothing here changes the worker HTTP
  protocol.
- **One kernel per app.** One environment, one UUT setup, one person at a
  time. A second page that opens the console joins the same kernel and
  sees it as busy if a command is running.
- **Not recorded.** Console commands are not runs: no report, no
  fingerprint, no job. They count as nothing toward a report. Results
  live in the page until it closes.

## What was checked before writing this (2026-11-18)

| Checked | Result |
| --- | --- |
| Running a script | `framework/executor.py`. `build_env(files, load_order, imports, variation)` loads the `core.rst` chain and the script's definitions without running a step. `execute_closure` then binds handles and variation symbols and runs under `clock.keeping(clock)`. `execute_script` opens `context.running(env)` and `context.cleanups()`. `_run_step`, `_define` and `_run_table` run and report one statement; `run_cleanups` releases what blocks held. All of these are reusable as they are. |
| Context | `context.running`, `context.cleanups` and `clock.keeping` are **contextvars**. A kernel therefore runs every command on **one dedicated thread** that holds them open for the kernel's life, not on Flask request threads. |
| Workers | `services/worker/worker.py`. `Worker.work_once` probes and then forces jobs. `run_job` installs and starts UUTs (`install_uuts`, `uut.start`), binds handles (`handles`) and takes the env's clock (`env.clock(bound)`). The in-process worker is `start_local_worker` in `cli.py`, a `Worker(LocalServer(...), Host.from_file(config))`, started for `client` (with `--config`), `server --local-worker` and `demo`. |
| Environment state | UUT state lives in the environment's workdir (`lm-state.json`), shared by every handle on that `Host`. A second worker with the same config would fight the first over it. So the kernel must **borrow the local worker's `Host`** and stop that worker taking jobs meanwhile. |
| Waiting | `plugins/core/wait.py` sleeps only through `clock.current().sleep`. `SimClock.sleep` without `step` polls `time.sleep`; the lms handle's `run_for` and `fly_to` loop on `self.sleep`. These are the points where a Stop has to take effect. |
| Editor | `web/editor.py` keeps a `PageSession` (the language server) per page, keyed by workspace and session. `static/js/editor.js` gives every card a gutter (`..` menu, `::` grip) in `decorate()` and keeps each card's data in `el._card`; `dataOf(card, true)` is what an open card's editor holds now, unsaved. |
| Rendering a step | Run pages render steps from events (`web/report_view.py`, `templates/reports/`). The console does **not** reuse it: it is a development tool, and a compact transcript (step 4) is what a quick edit-and-run loop wants. |

## Decisions

1. **The kernel borrows the local worker.** Opening the console asks the
   in-process `Worker` to stand aside. It finishes the job it is running,
   if any, then stops claiming jobs. It checks in with status
   `"console"`, so the Workers page and the queue show why it isn't
   taking work. Closing the console (or its idle timeout) hands the
   worker back. Queued jobs simply wait meanwhile.
2. **A kernel is bound to a script.** The script gives it its `core.rst`
   chain, its UUTs (`(uut ...)`), the environments it allows and its
   variations. Opening the console on a script picks:
   - **environment:** one of the script's that the local worker hosts;
   - **UUT versions:** newest by default, any listed version allowed;
   - **variation:** the first by default, if the script has any.

   The kernel then builds the env as a run would (`build_env`, handles,
   variation symbols, clock). Moving to a script with a different
   `core.rst` chain or different UUTs offers to reopen the kernel on it.
   A script in the same folder shares the chain: its definitions card is
   loaded the first time one of its cards runs.
3. **Starting is warm when it can be.** If the installed versions are
   the ones picked, the kernel attaches to the UUTs as they are, like a
   probe. Otherwise it installs and starts them, like force mode. The
   bar says which happened.
4. **Two ways back to a clean slate:**
   - **Reset** runs the cleanups (releasing fixed values) and rebuilds
     the env from the files as they are now. The UUT is not touched, so
     this is cheap: use it after editing `core.rst`.
   - **Restart** does Reset, then `install` (if needed) and `start` on
     every UUT, as force mode does: the UUT comes back fresh. Use it when
     the UUT is in a state you don't want.

   Changing the environment, a version or the variation is a Restart.
5. **What runs:**
   - **A card** runs its forms in order, as a script runs its statements.
     Definitions are evaluated; a `defn` or `def` already defined is
     redefined, so editing and re-running a definitions card works.
     Steps, preconditions (check, heal, check again) and table blocks
     (once per row) run as they do in a run. The first failing step
     stops the card.
   - **A line** (Shift+Enter in a card's editor) runs the top-level form
     the cursor is in, or the selected text if there is a selection.
   - **The text sent is the editor's,** unsaved edits included. The
     `core.rst` files come from disk, as Reset found them.
   - **Variation limits:** a card limited to other variations
     (`:variations:`, or inside an `rvt-variant` for others) is refused,
     with the reason. Prose cards have nothing to run.
6. **Fixed values stay fixed.** In a run, cleanups happen at the end. In
   the console they happen on Reset, Restart or Close. The bar lists
   what is held, and offers Release all, which runs the cleanups without
   rebuilding anything.
7. **Stop is cooperative.** Stop sets a flag that every clock sleep
   checks, raising `Stopped`. The command ends as an error ("stopped"),
   and the kernel stays usable. `context.check_stopped()` is public, so
   plugins with their own loops can check it too; the lms handle's
   `run_for`/`fly_to` loops do. A block stuck in code that never checks
   can't be stopped. In that case Restart abandons the kernel's thread
   (a daemon) and starts a new kernel. The bar says the old thread may
   still be running.
8. **Commands run one at a time, asynchronously.** `POST run` queues the
   command and returns its id; the page polls for its events every
   300 ms until it ends. A lunar landing in `lms` takes about 40 s of
   wall time, too long for one request. A command sent while one runs
   waits in the queue, and the bar shows it.
9. **The console is a panel on the editor page, not a results page.**
   It is docked at the bottom of the editor pane, like an IDE's
   terminal, so the card being edited and what it did are on screen
   together. It shows a transcript, newest at the bottom: each command
   (the card's title, or the form typed or run), then one compact line
   per step, with what it read, any output, and why it failed. Below the
   transcript is a prompt for typing forms directly. There is no
   per-card popover and no run-page rendering.
10. **An idle kernel closes itself** after 30 minutes with no command,
   and hands the worker back. The time can be configured
   (`CONSOLE_IDLE`).

## Steps

### 1. The kernel (`services/worker/kernel.py`)

`Kernel(host, files, load_order, imports, script, environment, versions,
variation)`:

- a dedicated daemon thread, and a command queue;
- `open()`: warm or fresh start (decision 3), then build the env;
- `run(text, kind)`: queue a command (`kind` is `"card"` or `"form"`) and
  return its id;
- `events(id, since)`: a command's events so far, and whether it is
  done;
- `stop()`, `reset(files)`, `restart(files)`, `release_all()`,
  `close()`;
- `state()`: environment, versions, variation, `warm`/`fresh`, busy or
  idle, queue length, held values (from the cleanups registry), last
  used.

Card and form commands share the executor. Factor out of `_run_statements`
a `run_statements(statements, env, observer, variation)` that both the
executor and the kernel call, so console and runs can't drift apart. The
observer collects events into the command's list, reusing the
`ReportObserver` event shapes. Statement indexes are the card's own:
0, 1, 2 and so on.

Also in this step: `clock.WallClock.sleep` and `SimClock.sleep` sleep
in short slices and check the stop flag; `context.check_stopped()` and
the `Stopped` exception are added.

Tests (`test/test_kernel.py`, on `lm` in `sim`):
- warm and fresh open;
- a definitions card, then a step that uses it;
- redefining a `defn`;
- a failing Verify;
- a precondition that heals;
- a table card;
- SetFixedValue held across commands, then released by Reset;
- Restart bringing the LM back to its default boot;
- Stop interrupting a long `(Wait ...)` in sim;
- a card limited to another variation being refused.

### 2. Borrowing the worker (`services/worker/worker.py`)

- `Worker.borrow()` and `Worker.give_back()`, with a lock around
  `work_once`. `borrow` waits for the current job to finish (with a
  timeout that is reported) and sets status `"console"`. `give_back`
  sets `"available"`.
- The work loop skips claiming while the worker is borrowed.
- `start_local_worker` stores the worker in the app config
  (`LOCAL_WORKER_INSTANCE`), so the web layer can reach it. The kernel
  registry, one per app, lives next to it.
- The Workers page shows `console` as a status, with a word on what it
  means.

Tests: a queued job waits while the worker is borrowed and runs once it
is given back; the worker finishes a job in progress before the borrow.

### 3. Endpoints (`web/console.py`, on the workspace blueprint)

| Endpoint | Does |
| --- | --- |
| `GET .../console` | The kernel's state, or whether a console can be opened here, and the choices: environments, versions and variations for the script. |
| `POST .../console/open` | `{script, environment, versions, variation}` |
| `POST .../console/run` | `{text, kind}`, returning `{id}` |
| `GET .../console/run/<id>?since=N` | `{lines, done}`: the command's transcript lines from `N` on |
| `POST .../console/{stop,reset,restart,release,close}` | The kernel's controls |

All of them 404 when the app has no local worker. They need the same
access as editing the workspace.

Tests: endpoint round trips on the demo setup, and 404 without a local
worker.

### 4. The transcript (`services/worker/kernel.py`)

A command's events become transcript lines on the server, as they come
in (`transcript(events) -> [line]`). The page only draws them. A line is
`{kind, text, card?, at?}`:

| kind | Shows | From |
| --- | --- | --- |
| `command` | `▶ Verify the touchdown` (a card's title or first form), or `» (Read lm.nav.altitude)` | the command |
| `step` | `✓ (Keys "V16N68E")  0.3s`, or `✗ ...` | `step_end`, its form shortened to one line |
| `check` | `  lm.landed (true) = true` | Verify/Wait comparisons in the step's data |
| `value` | `  lm.nav.altitude = 1523.4` | `ref` events (reads, sets, fixes, clears) |
| `out` | `  ...` | stdout and stderr, folded after 5 lines |
| `fail` | `  Expected ... came out ...`, linked to the card and line | `message` and the innermost `trace` span |
| `result` | `=> :accepted` | the value of a typed or Shift+Enter form, as edn |
| `table` / `row` | `  row "extended": ✓` | `table_start`, `row_end` |
| `phase` | `  check ✗, heal ✓, check ✓` | precondition `phase_end`s |
| `file` | `  📎 trajectory.svg` (opens it) | `attachment` |
| `note` | `stopped`, `reset`, `restarted (fresh)`, `released 2 values` | the kernel |

Attachments are kept in the kernel's scratch folder (under the app's
data path) and served from `.../console/files/<name>`, cleared on Close.

Tests: the transcript of a passing card, a failing Verify (with its
card and line), a table card, a healed precondition, a typed form's
value, and an attachment.

### 5. The editor (`static/js/editor.js`, `templates/workspace.html`, css)

- **Console panel** docked at the bottom of the editor pane:
  - **Resizing:** it can be resized by dragging its top edge, and
    collapsed to its header. Its height and whether it's open are
    remembered per browser (localStorage, wrapped in try/catch).
  - **The header is the kernel's bar:**
    - which script it's bound to, the environment, versions and
      variation, and `warm`/`fresh`;
    - idle, running, or how many are queued;
    - held values, with Release all;
    - Stop, Reset, Restart, Close, and Clear (empties the transcript
      only).
  - **The transcript:**
    - It follows new lines while scrolled to the bottom.
    - A `fail` line jumps to its card and puts the cursor on the failing
      line.
    - A `command` line jumps to the card it ran.
  - **The prompt:**
    - A one-line CodeMirror with the same language mode and completion
      as cards.
    - Enter runs the form, Shift+Enter adds a line, and Up/Down walk
      the history (kept per browser).
- **Gutter:** a `▶` button on rvt cards (not on prose cards), next to
  `..` and `::`, that runs the card. After a run it shows a dot for the
  card's last outcome, until the card is edited.
- **Shift+Enter** in an open card's editor runs the form at the cursor,
  or the selection, without leaving the card. Finding the top-level form
  uses the reader's spans, server-side: the page sends the card's text
  and the cursor offset. So the loop is: edit the step, Shift+Enter,
  read the transcript, edit again.
- **Opening:** the first ▶, Shift+Enter or prompt entry with no kernel
  opens the panel with a small form of choices from `GET .../console`,
  defaulted, then runs. When no console is possible (no local worker),
  there is no panel, no ▶, and Shift+Enter does nothing.

Tests: the existing editor page tests, extended to check that the panel
and the gutter button appear with a local worker and not without.

### 6. Docs

- `docs/operating/editor.rst`: a "Trying things out" section covering
  the console panel and its prompt, ▶ and Shift+Enter, Reset vs Restart, held values, Stop,
  and that console work isn't recorded.
- `docs/operating/local-client.rst`: that the local worker is borrowed
  while the console is open.
- `docs/blocks/writing-blocks.rst`: `context.check_stopped()` for blocks
  with loops of their own.

## Risks

- **Transcript too terse for some blocks.** Blocks that report rich
  data (tables, plots) show only as a line and an attachment link. If
  that turns out to hurt, a line can expand into the block's own
  `as_rst` rendering later. It's not planned now.
- **Unstoppable blocks.** Decision 7 leaves a thread behind. It's
  acceptable on a developer's machine; the bar says so.
- **Two tabs, one kernel.** Both see the same state; commands queue. The
  bar names the script the kernel is bound to, so a second tab on
  another script isn't confused about which env it's in.
- **Warm attach to a UUT a job left mid-flight.** The kernel attaches to
  whatever state the last job left. That is the same rule as probes, and
  Restart is one click away.

## Notes as we go

### Step 1 (the kernel)

- The transcript is made in the kernel as events come (step 4's lines
  land here), so the kernel and its transcript are one module,
  `services/worker/kernel.py`.
- A step's line is written when the step ends, with its calls under
  it, so no line ever changes once written. What runs now is the
  kernel's state (`running`), for the panel's header.
- The transcript is one stream for the kernel, not per command: every
  line has `n` and its command's id, and a page asks for lines after
  the last `n` it has. Two tabs then see the same transcript.
- `executor.run_statements` is the statement loop that both scripts and
  the kernel run; `redefine=True` (the kernel) evaluates a definitions
  card again even though its names exist. `_run_step` and `_define`
  are now `run_step` and `define`.
- A form typed at the prompt can be anything, including a plain symbol
  or number (`mission`, `42`). `steps._run_statement` no longer assumes
  a list.
- Restart's abandon waits up to 2 s for the command to finish after
  Stop. The thread itself is always alive (it waits on its queue), so
  that is the test, not `thread.is_alive()`.
- Stop checks are in `WallClock.sleep` (0.1 s slices), `SimClock.sleep`
  and the lms handle's `run_for`/`fly_to` loops.

### Step 2 (borrowing the worker)

- `Worker.lock` is held while the worker looks for or runs a job
  (`work_once`), so `borrow()` waits for the running job by taking it.
- `console` is a worker status (`jobs.ALLOWED_STATUS`), shown on the
  Workers page as "In the console", with a tooltip.
- `cli.py` keeps the in-process worker as `app.config["CONSOLE_WORKER"]`
  for `client --config`, `server --local-worker` and `demo`.

### Step 3 (endpoints)

- `web/console.py`. A `Console` per app (`app.config["_CONSOLE"]`, made
  on first use) holds the borrowed worker and the kernel. A watcher
  thread closes an idle console even when no page asks.
- One transcript stream, as step 1 found: `GET console/lines?since=N`
  replaces the per-command `run/<id>` of the table above. Its `state`
  has `last` (the newest line's `n`), so a page that sees `last` go
  below what it has knows the transcript was cleared.
- `POST console/run` takes three kinds: `card` (a card's fields),
  `form` (a card's code and the cursor; the server finds the form) and
  `forms` (text typed at the prompt).
- `variations` on a run is a list of lists: the card's own
  `:variations:` and those of each `rvt-variant` it is in. Each must
  allow the console's variation.
- A console is bound to its workspace. Another workspace's page sees
  its state, but gets 409 if it tries to run in it.
- A script that isn't saved yet can't be opened (400): the console loads
  the script from disk.
- Tracebacks are left out of the transcript for unknown names and
  missing blocks, where they say nothing more than the message.

### Step 4 (the transcript)

- Done in step 1: `kernel.Transcript` makes the lines as events come.
  The table of kinds above holds, with `call` lines (block calls a step
  made, indented by depth) and `error` (a traceback, folded on the
  page).
- A Precondition is named by its description ("Precondition: LM at
  PDI…"), on its step line and as an untitled card's command line.
- A step stopped by Stop has no failure line: the kernel's `stopped`
  note says it.
- The kernel's state has `outcomes` (command id → outcome, the last
  100), which the page uses to colour a card's ▶.

### Step 5 (the editor)

- All in `editor.js`, in a section of its own ("The console"), because
  it needs the cards' private state (`dataOf`, `openCard`, the card
  elements). The template only says whether there is a console
  (`data-console` on `#ed`, and a **Console** button in the bar).
- The panel is `position: sticky; bottom: 0` inside `#ed`, so it stays
  at the foot of the window as the cards scroll. The editor's panes are
  padded by the panel's height (`--ed-console-h`), so the last card can
  always be scrolled above it.
- **Not done: completion in the prompt.** The language server completes
  names in a card, by its place in a file it has been sent. The prompt
  isn't in a file, so it would need a request of its own. It's left
  for later.
- Shift+Enter in a **table** block binds the table's first row before
  running the form (`table` on the run request), so `(Verify light = true)`
  inside a table's steps can be tried on its own. Without it, every
  form in a table card failed with an unknown name.
- Checked by hand in the demo (Chrome):
  - opening from the bar and from ▶;
  - a precondition card healing;
  - a table card running every row;
  - Shift+Enter on a nested form, with the failure link putting the
    cursor on the failing call;
  - Shift+Enter in a table card;
  - the prompt;
  - Stop on a Wait that never holds;
  - a reload picking the open console up;
  - the Workers page showing "In the console";
  - Close giving the worker back.

### Step 6 (docs)

- `docs/operating/editor.rst`: a "Trying things out: the console"
  section.
- `docs/operating/local-client.rst`: `--config` gives the client a
  console, which borrows its worker.
- `docs/blocks/writing-blocks.rst`: `context.check_stopped()`.
