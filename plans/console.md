# The console: run a card or a line from the editor

While writing a script, run one card or one form against a live UUT and
see the result in a popover in the editor, without queuing a run. Behind
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
| Rendering a step | Run pages render steps from events (`web/report_view.py`, `templates/reports/`). Step 4 reuses that rendering for the popover. |

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
9. **An idle kernel closes itself** after 30 minutes with no command,
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
| `GET .../console/run/<id>?since=N` | `{events, done, html}`: the popover's rendering, so far |
| `POST .../console/{stop,reset,restart,release,close}` | The kernel's controls |

All of them 404 when the app has no local worker. They need the same
access as editing the workspace.

Tests: endpoint round trips on the demo setup, and 404 without a local
worker.

### 4. Rendering a result

The popover's HTML comes from the command's events through the run
page's step rendering (`report_view` and the `reports/` step partials),
so a Verify's comparisons, values read, block calls, stdout, failure
messages with their trace, and attachments (the trajectory plot) look
as they do on a run page. If the step partials are too tied to a
report, pull out a partial that takes events only, and use it from
both. A form's value is shown too: the REPL answer, written as edn.

Attachments are kept in the kernel's scratch folder (under the app's
data path) and served from `.../console/files/<name>`, cleared on Close.

### 5. The editor (`static/js/editor.js`, `templates/workspace.html`, css)

- **Gutter:** a `▶` button on rvt cards (not on prose cards), next to
  `..` and `::`. It's shown only when a console can be opened.
- **Shift+Enter** in an open card's editor runs the form at the cursor,
  or the selection. Finding the top-level form uses the reader's spans,
  server-side: the page sends the card's text and the cursor offset.
- **Popover** anchored under the card:
  - the result, live while it runs, with a Stop button;
  - stays until dismissed, with Escape or the close button;
  - running again replaces it;
  - one popover per card, and the card's ▶ shows the last outcome as a
    dot.
- **Console bar** at the top of the editor pane, when a kernel is open:
  - environment, versions, variation, `warm`/`fresh`;
  - idle, running, or how many are queued;
  - held values, with Release all;
  - Reset, Restart, Close.

  Opening: the first ▶ with no kernel opens a small dialog with the
  choices from `GET .../console`, defaulted, then runs.
- The whole thing is a no-op when the app has no local worker.

Tests: the existing editor page tests, extended to check the gutter
button appears with a local worker and not without.

### 6. Docs

- `docs/operating/editor.rst`: a "Trying things out" section covering
  the console, ▶ and Shift+Enter, Reset vs Restart, held values, Stop,
  and that console work isn't recorded.
- `docs/operating/local-client.rst`: that the local worker is borrowed
  while the console is open.
- `docs/blocks/writing-blocks.rst`: `context.check_stopped()` for blocks
  with loops of their own.

## Risks

- **Event rendering may be report-bound.** If the step partials need a
  whole report and run, step 4 grows. A fallback is a plain rendering
  (outcome, message, values, stdout) first, and the full one later.
- **Unstoppable blocks.** Decision 7 leaves a thread behind. It's
  acceptable on a developer's machine; the bar says so.
- **Two tabs, one kernel.** Both see the same state; commands queue. The
  bar names the script the kernel is bound to, so a second tab on
  another script isn't confused about which env it's in.
- **Warm attach to a UUT a job left mid-flight.** The kernel attaches to
  whatever state the last job left. That is the same rule as probes, and
  Restart is one click away.

## Notes as we go

(Filled in per step.)
