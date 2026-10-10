Automation v3
=============

.. rst-class:: lead

   Test scripts that read as documents, run anywhere a worker can reach the
   hardware, and report results you can trust to have come from exactly the
   configuration they say they did.

Automation v3 runs verification scripts against units under test (UUTs) in
simulators and on benches, and rolls the results up against the requirements
they verify. A script is a reStructuredText document: the prose explains the
test, the ``rvt`` blocks hold the steps, and the web app renders it as a page a
reviewer can read without knowing the language.

Where to start
--------------

**New here?**
   Read :doc:`overview/motivation` for why the framework is shaped the way it
   is, then :doc:`overview/concepts` for the vocabulary, and
   :doc:`overview/getting-started` to run the sample set on your machine.

**Writing test scripts?**
   :doc:`scripts/index` walks through a script from its first line to
   variations, preconditions and shared definitions.

**Writing BuildingBlocks, UUTs or environments?**
   :doc:`blocks/index` covers the Python side: the blocks scripts call, how
   they render, and how to plug in new hardware.

**Running the system?**
   :doc:`operating/index` covers the server, workers, reports, reruns and the
   scratch space.

.. toctree::
   :maxdepth: 2
   :caption: Overview

   overview/motivation
   overview/concepts
   overview/getting-started

.. toctree::
   :maxdepth: 2
   :caption: Script writers

   scripts/index
   scripts/first-script
   scripts/steps
   scripts/definitions
   scripts/variations
   scripts/preconditions
   scripts/refs
   scripts/composing
   scripts/documenting
   scripts/planning
   scripts/blocks

.. toctree::
   :maxdepth: 2
   :caption: Block developers

   blocks/index
   blocks/writing-blocks
   blocks/rendering
   blocks/attachments
   blocks/uuts-and-environments

.. toctree::
   :maxdepth: 2
   :caption: Operating

   operating/index
   operating/workers
   operating/reports
   operating/configuration-management
   operating/scratch

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference/language
   reference/cli
   reference/requirements
   reference/api
   reference/glossary
