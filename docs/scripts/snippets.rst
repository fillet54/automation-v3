Snippets
========

.. rst-class:: lead

   Named pieces of scripts to start from: a precondition, a variations
   table, a check you write again and again. The editor and the console
   insert them, with the parts to change ready to fill in.

Where they live
---------------

A folder may hold one ``snippets.rst``. Each titled ``rvt`` block in it is
a snippet: the title is its name, the paragraph just before the block says
what it is for, and the block's code is what gets inserted:

.. code-block:: rst

   Flying
   ------

   Lets the flight run to a phase, then checks a point.

   .. rvt:: Fly to a phase and check

      (FlyTo #{:high-gate})
      (Verify #{lgc.program} = #{64})

``#{...}`` marks a **field**: when the snippet is inserted, the first field
is selected, you type over it, and **Tab** moves to the next. Fields with
the same name are filled in together. ``#{}`` is a stop with nothing in it.
Fields are edn sets, so the block still reads and the page renders it like
any other.

A script sees the snippets of every ``snippets.rst`` from the workspace
root down to its folder, the way it sees ``core.rst`` files. A folder's own
snippet replaces one of the same name from a folder above, and is offered
first. So the root holds what every script uses, and a subsystem's folder
what only its scripts do.

A ``snippets.rst`` is neither a script nor definitions: nothing in it
runs, it can't be queued, and it is checked only for code that can't be
read, blocks without a name and names used twice. A snippet that uses a
definition only works where that definition is in scope; the editor checks
the code once it is inserted.

Using them
----------

In the editor
   **Snippets**, above the tabs, lists the snippets the open file can use,
   with what each is for and where it comes from. Picking one inserts it at
   the cursor of the block being edited, or, if none is, in a new block at
   the end. In a block, **Ctrl+Space** offers snippets too, after the
   names, wherever a whole form can go; the list shows a snippet's code
   before you pick it.

In the console
   The side pane's **Snippets** tab lists the snippets of the console's
   script. Clicking one puts it in the prompt, its fields ready to fill in;
   **Enter** runs it.

The Apollo example has a ``snippets.rst`` at its root (variations, a
precondition, flying, waiting and the landing checks) and one in ``LND/``:

.. literalinclude:: ../../automationv3/examples/apollo/rvts/LND/snippets.rst
   :language: rst
