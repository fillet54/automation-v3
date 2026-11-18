Editing scripts
===============

.. rst-class:: lead

   The workspace page opens files in tabs and edits them a part at a time,
   straight into your worktree.

Where editing works
-------------------

The editor writes the files of a git worktree on the machine the app runs
on: a single-user server, or the :doc:`local client <local-client>`. Git
stays outside it: you commit and push as you do after editing in any other
editor. A central server shows what was pushed and doesn't edit.

Tabs
----

Picking a file in the tree opens it in a tab; a link to a script from
another page opens it in a tab too. The tabs you have open are remembered
for each workspace. A tab with edits that aren't saved has a dot.

Closing a tab with unsaved edits doesn't lose them: they are kept in the
browser, and come back when the file is opened again.

Cards
-----

A script shows as it reads, cut into parts, each one a card:

Text
   A section of prose, from its heading to the next heading or block.
   It is edited as reStructuredText.

Block
   One ``rvt`` block. Editing it shows only its code: the ``.. rvt::``
   line, its options and the indentation are written for you.

Variant
   An ``rvt-variant``: text and blocks that are only for some variations,
   marked by a rule down their left. The cards inside it are ordinary
   cards.

Source
   A block or variant that can't be read is edited as the
   reStructuredText it is.

A heading is what the page shows as one: the cards are cut the way
docutils reads the file. So:

- an underline of four characters or more makes a heading even when it is
  shorter than its title (docutils warns); a shorter one is ordinary text;
- a heading inside a variant must use a style deeper than the section the
  variant is in; one at that level or above is reported as a problem;
- headings go one level at a time: a style that skips a level (``===``,
  then ``~~~`` under a ``---`` heading) is reported as a problem;
- a ``.. rvt::`` line needs a blank line before it. Straight after a line
  of text it is part of that paragraph, not a block: it would never run,
  so it is reported as a problem.

The page shows the script and nothing else. Pointing at a card shows two
marks to its left:

``..``
   The card's menu: add text or steps below (or above) it, edit it, move
   it up or down, delete it. For a block, also give it a title, make it a
   definitions block or a table, and say which variations it is for.
``::``
   Drag it: to another place, into a variant or out of one.

Click a card to edit its text. **Esc** or **Ctrl+Enter** closes it and keeps
what you typed; **Cancel** drops it.

**Double click a title** to change it where it is: a block's title, or a
section's heading. Enter keeps it, Esc leaves it as it was.

Variations
~~~~~~~~~~

Where a script declares variations, a block's menu has **Only for**: **All**,
and each variation. Pick one or more to limit the block to them; **All**
makes it for every variation again. Scripts that declare no variations
don't show it.

**Put in a variant**, in the menu, wraps a card in a variant, for text and
blocks that belong to the same variations; the variant's own menu picks
them, and **Take out of the variant** undoes it. Moving a card up or down
steps it into a variant next to it, or out of the one it is in.

**Undo** (Ctrl+Z) and **Redo** (Ctrl+Shift+Z) walk back and forth through
everything done to a tab's cards, in order: an edit, a move, a delete, a new
title. While a card is open, Ctrl+Z undoes typing in it.

Any other text file opens as one card of its text.

New scripts, clones and folders
-------------------------------

**New script**, above the tree, asks for a title, a file name (made from
the title unless you type one) and a folder. The script starts with its
title, a Requirements section and one block with a ``(TBD)`` step.

A requirement's page offers **Write a script for this**: the new script
then starts with the requirement's text and lists it under Requirements.

**File → Clone…** copies the open script under a new title, its
requirements included.

A new script or a clone opens as a tab with unsaved edits. Nothing is
written to the worktree until you save it, so one you abandon (**Discard
edits**) leaves no file behind. Until then it is kept in the browser, and
its tab comes back if the page is reloaded.

**File → Rename or move…** gives the open file another name or folder,
and **File → Delete…** removes it from the worktree; both act at once.
Reports that already ran a script keep the name it had then, and git can
bring back a deleted file that was committed.

**New folder** makes a folder, with a ``core.rst`` for the definitions its
scripts share if you ask for one.

Saving
------

**Save** (Ctrl+S) writes the tab's file. **Run in scratch** runs the files
on disk, so it saves the script first; when files it loads have unsaved
edits in other tabs, it offers to save them too. Only the cards you edited are
rewritten: every other line of the file stays exactly as it was. **Discard
edits** drops a tab's unsaved edits and shows the file again.

A script is only cut into cards in the **In work** view with every
variation showing; pick a variation, or **Checked in**, to read it that way.

Errors and completion as you type
---------------------------------

**Problems**, above the tabs, lists every error and warning in the open
files and the files they load; picking one shows the card it is in. The
file tree counts the problems of each file too.

While a script is open, a language server checks it as its cards make it,
unsaved edits included, a moment after you stop typing. It reports what a
script's page reports: unknown names, wrong calls, code that can't be read.

- In the card being edited, the code at fault is underlined; hover it for
  the message.
- Every card lists its problems beneath it, and the tab counts the errors.
- A ``core.rst`` open in another tab is checked with: break a definition
  there and the scripts that use it say so before anything is saved.

In a block, **Ctrl+Space** completes the names it can use: blocks (offered
first after an opening parenthesis, with how they are called), builtins,
the definitions of the script and of its ``core.rst`` files, UUT handles,
variation values, and the parameters and ``let`` names around the cursor.
Completion also opens by itself as you type a name.

Hovering a name in a block says what it is: a block's calls and
documentation, a definition's code and the file it is in, a UUT handle, a
variation value with what each variation gives it. Where it can be told
without running anything, it also says what the name's value is: a literal,
or another name for one, and for a ref (or a path below one, such as
``nav.time``) its kind and full path; for a group, each member's.

While you type a call, the line under the editor shows how it is called,
with the argument you are on marked: a block's forms, or the parameters of a
function the script or a ``core.rst`` defines.

Below a ref, completion offers the paths that exist when its kind of ref
can say (see :doc:`../blocks/writing-blocks`): typing ``eps.`` after
``(def eps (connector "lm.eps"))`` offers ``bus-volts``, ``amps`` and the
rest, and so does the path inside ``(connector "lm.``. A path that doesn't
exist is marked with a warning, as it is wherever a ref is made with one.
A warning, not an error: the script still queues, and fails when a run
reaches the path.

In prose, typing ``:req:`` and a backquote completes requirement ids, with
each requirement's text; hovering an id shows its text, and an id that isn't
in the requirements the workspace verifies is marked. Ids are only checked
when there are requirements to check against, and the local client, which
asks the central server for one requirement at a time, shows a
requirement's text on hover but can't list or check them.

In another editor
~~~~~~~~~~~~~~~~~

The same server runs on its own as ``automation-v3 lsp``, speaking the
Language Server Protocol on stdin and stdout, so an editor with an LSP
client gets the same errors and completion. Start it for ``.rst`` files
with the worktree as the root; it takes the worktree's ``rvts`` folder as
the scripts root, and reads requirements from the database at ``--dbpath``
(``./automationv3.db`` unless you say) when it is there. In Neovim, for
example:

.. code-block:: lua

   vim.api.nvim_create_autocmd("FileType", {
     pattern = "rst",
     callback = function(args)
       vim.lsp.start({
         name = "automation-v3",
         cmd = { "automation-v3", "lsp" },
         root_dir = vim.fs.root(args.buf, { "rvts", ".git" }),
       })
     end,
   })

Trying things out: the console
------------------------------

While you write a script, the **console** runs a block, or a single form,
against a real UUT on this machine, and shows what it did, without queuing a
run. Change a step, run it again, read what happened, change it again.

It is there wherever the app has a worker of its own: the local client
started with ``--config``, a server started with ``--local-worker``, and
``automation-v3 demo``. **Console**, above the tabs, opens it.

Running
~~~~~~~

``▶``
   Pointing at a block shows ``▶`` left of its ``..`` mark. It runs the
   block as a run would: its definitions, its steps, a precondition's check
   and heal, a table's steps once per row. It stops at the first step that
   fails. Afterwards ``▶`` is green or red for how it went, until the block
   is edited.
**Shift+Enter**
   In a block being edited, runs the form the cursor is in (the whole
   top-level form), or the selected text. In a table block, it runs with
   the first row's values bound.
**The prompt**
   At the bottom of the console. **Enter** runs what is typed,
   **Shift+Enter** starts a new line, and **Up** and **Down** go back through
   what you ran before.

What runs is what the editor holds, unsaved edits included. Running a
definitions block again defines its functions again, so an edit to a
``defn`` takes effect without saving. A block limited to other variations
isn't run.

The first run asks what to start the console with: the environment, the
version of each UUT (newest first), and the variation, from the script that
is open. If the versions asked for are already installed, the console takes
the UUT as it is; otherwise it installs them and starts the UUT fresh, as a
run in force mode does. Then it loads the script's ``core.rst`` files and
definitions, the UUT handles and the variation's symbols, and keeps them
until it is closed: a ``def`` typed at the prompt is there for the next
command.

What it shows
~~~~~~~~~~~~~

Each command, then a line for each step it ran, with the block calls the step
made, what they printed (a Verify's comparisons, a Wait's last look), the
refs they read or set, and why a step failed. A form's value follows ``=>``.
A failure links to the line of the block it came from: clicking it opens the
block with the cursor there. Files a block attaches, such as a trajectory
plot, are links.

The header says which script the console was started on, its environment,
versions and variation, and whether the UUT was taken as it was (**warm**)
or started (**fresh**); then what is running.

Starting over
~~~~~~~~~~~~~

**Stop**
   Stops the command running, at the next place it waits, and drops the
   ones waiting behind it. The console goes on.
**Reset**
   Releases what is held, and loads the ``core.rst`` files and the script
   from disk again: use it after editing a ``core.rst``. What was typed at
   the prompt is forgotten. The UUT is left as it is.
**Restart**
   Resets, then starts the UUT fresh. If the command running doesn't stop,
   it is left running in the background and a new console carries on; the
   header says so.
**Release all**
   Values fixed with ``SetFixedValue`` stay fixed between commands, until a
   reset; the header counts them. This releases them and keeps everything
   else.
**Close**
   Releases what is held and gives the worker back.

While the console is open, this machine's worker takes no jobs: the
Workers page shows it **In the console**, and queued jobs wait for it. A
console no one has used for 30 minutes closes itself. There is one console
for the app: another workspace's page sees it is open, but has to wait for
it to be closed.

Nothing the console does is recorded: it makes no runs and changes no
report. Run the script, in scratch or in a report, for that.

When the file changes on disk
-----------------------------

A checkout, a pull or another editor can change a file that is open in a
tab. The editor checks when the window gets the focus back and before every
save.

A tab without unsaved edits just shows the new file. A tab with unsaved
edits says the file changed and offers:

**See the difference**
   What saving your version would change in the file as it is now.
**Take the file's**
   Drop your edits and show the file as it is on disk.
**Keep mine**
   Save your version over the file on disk.

Save never overwrites a file that changed since the tab opened it without
asking.

Building the editor's CodeMirror
--------------------------------

The code editor inside a card is CodeMirror, built into one file that is
checked in (``automationv3/web/static/js/codemirror.bundle.js``), so
running the app needs no Node. To change what it includes, edit
``frontend/codemirror.js`` and rebuild:

.. code-block:: console

   $ cd frontend
   $ npm install
   $ npm run build
