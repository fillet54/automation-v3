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
   One ``rvt`` block. Its title, **Definitions**, **Table** and the
   variations it is **only for** are fields; the body is only the code.
   The ``.. rvt::`` line and the indentation are written for you.

Source
   An ``rvt-variant``, or a block that can't be read, is edited as the
   reStructuredText it is.

Click a card to edit it. **Esc** or **Ctrl+Enter** closes it and keeps what
you typed; **Cancel** drops it. Hovering a card shows **↑** and **↓** to move
it, **Delete**, and **+ Text** and **+ Block** to add a card after it.

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

**Save** (Ctrl+S) writes the tab's file. Only the cards you edited are
rewritten: every other line of the file stays exactly as it was. **Discard
edits** drops a tab's unsaved edits and shows the file again.

A script is only cut into cards in the **In work** view with every
variation showing; pick a variation, or **Checked in**, to read it that way.

Errors and completion as you type
---------------------------------

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
