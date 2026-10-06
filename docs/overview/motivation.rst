Motivation
==========

.. rst-class:: lead

   Why Automation v3 exists, and the handful of ideas every other part of it
   follows from.

Verification of a vehicle controller (or any embedded unit) produces two
things: evidence that each requirement holds, and the scripts that produced
that evidence. In practice both rot. Scripts become opaque code that only
their author can review; results end up in spreadsheets detached from the
exact software, test code and bench that produced them; and rerunning a test
"the same way" is a matter of hope.

Automation v3 is built around a few commitments that address those problems
directly.

Scripts are documents
---------------------

A test script is a reStructuredText document. Its prose says what is being
tested and why; its ``rvt`` blocks hold the steps. The web app renders the
script as a readable page, where each BuildingBlock can present its arguments
in the clearest form (a configuration as a table rather than a nested map).

The aim is that a reviewer who has never seen the script language can read a
script and agree it tests what the requirement says. Features such as titled
blocks, ``rvt-variant`` sections and described heals exist to make the
rendered document read well, not just to make the script run.

.. seealso:: :doc:`../scripts/documenting`

Requirements are the unit of progress
-------------------------------------

Scripts reference the requirements they verify (``:req:`VMCBRA00001```).
A report rolls every run up to those requirements: a requirement is
:status:`passed` (green) only when every linked script passed in every
environment and variation it should run in, :status:`failed` (red) if any
of them failed, and :status:`partial` otherwise. The question a report
answers is "which requirements are verified?", not "which scripts ran?".

A result is only as good as its configuration
---------------------------------------------

Every run records exactly what produced it:

- the **closure**: the script and every ``core.rst`` and import it loaded,
  stored with the run;
- the **variation** values it ran with;
- the **UUT versions** and the digests of the installed bits;
- the **environment fingerprint**: facts about the simulator or bench, and
  the framework's own version and commit.

These hash to an **identity**. A rerun reproduces the original identity or
says plainly that it did not: if no worker's environment matches any more,
the rerun is refused with a diff of what drifted, and can only be forced as
:status:`not identical`.

.. seealso:: :doc:`../operating/configuration-management`

Workers pull, and keep hardware warm
------------------------------------

Benches are scarce and slow to set up. Workers live next to the hardware and
pull jobs from the server, so a lab machine needs no inbound access. They
prefer the job whose **preconditions** already hold (or can be healed) in the
environment as it is, and only reinstall and restart UUTs fresh when nothing
queued fits. Scripts say what state they need instead of always starting from
scratch, and the scheduler takes advantage of it.

.. seealso:: :doc:`../scripts/preconditions`, :doc:`../operating/workers`

A small language, extended in Python
------------------------------------

Script code is a small Lisp written in `edn <https://github.com/edn-format/edn>`_.
It is deliberately limited: definitions, a few special forms, and calls to
**BuildingBlocks**. Anything that touches hardware, needs a library or
deserves careful engineering is a BuildingBlock written in Python by a block
developer, with its own syntax check and rendering. Script writers compose
blocks; block developers make them trustworthy.

.. seealso:: :doc:`../blocks/index`

Authored in git, viewed in the app
----------------------------------

Scripts live in git and are reviewed like code. The web app's workspace is a
read-only viewer over a checkout: it renders scripts, lints them and queues
them, but never edits them. While a script is under development, the
:doc:`scratch space <../operating/scratch>` runs it straight from the working
tree without touching any report.
