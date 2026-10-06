Python API
==========

.. rst-class:: lead

   The parts of the framework block developers use.

BuildingBlocks
--------------

.. automodule:: automationv3.framework.block
   :members: BuildingBlock, BlockResult, code_block, raw_html
   :no-undoc-members:

The running script
------------------

.. automodule:: automationv3.framework.context
   :members: lookup, evaluate

.. autofunction:: automationv3.framework.steps.attach

Rendering helpers
-----------------

.. automodule:: automationv3.framework.html
   :members: text, mapping, table

UUTs and environments
---------------------

.. automodule:: automationv3.framework.uut
   :members: Version, Environment, UUT, uut_types, environment_types

edn
---

.. automodule:: automationv3.framework.edn
   :members: read, read_all, writes, Symbol, Keyword, List, Vector, Map, Set, ParseError

Observers
---------

.. automodule:: automationv3.framework.observer
   :members: ObserverManager
