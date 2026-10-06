Writing scripts that read well
==============================

.. rst-class:: lead

   A script is reviewed as a document. These features exist so the rendered
   page reads like a test procedure, not like code.

Write the prose first
---------------------

Say what the test checks and why before showing how. The prose between
``rvt`` blocks is always shown, whichever variation is selected, so it should
make sense on its own. Use headings ("Requirements", "Setup", "Steps") to give
long scripts a shape the page can be skimmed by.

Title the blocks
----------------

An ``rvt`` block can take a title. A titled block collapses its forms behind
the title, so the page reads as a list of named steps:

.. code-block:: rst

   .. rvt:: Apply the variation's pressure and check it is safe

      (set-reading :brake-pressure pressure)
      (brake-pressure-ok? (reading :brake-pressure))

Expanding the title shows the forms. On a run page the title carries the
block's overall result and duration. Untitled blocks show their steps at the
top level, as before.

Describe heals
--------------

Give a precondition's heal a description, so the page says what it does in
words:

.. code-block:: clojure

   (Precondition "Demo running in normal mode"
     (demo-in-mode? :normal)
     :heal "Start the demo in normal mode"
     (start-demo :normal))

Keep variation-specific prose with its code
-------------------------------------------

Use ``.. rvt-variant::`` so the explanation of a variation-specific check is
hidden along with the check when another variation is selected. See
:doc:`variations`.

Let blocks render themselves
----------------------------

Blocks can render their arguments readably: ``StartDemo`` shows its
configuration as a table, ``Verify`` as a sentence. Prefer a block with a good
rendering over a ``defn`` that hides the same logic. If a block shows as raw
code and could read better, ask its developer to give it an ``as_html``
(:doc:`../blocks/rendering`).

Keep definitions out of the way
-------------------------------

Put a script's own definitions in a ``:definitions:`` block at the top, where
the page collapses them, and shared ones in ``core.rst`` with prose explaining
them.
