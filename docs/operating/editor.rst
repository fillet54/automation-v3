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
