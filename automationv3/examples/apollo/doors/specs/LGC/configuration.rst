The erasable load
=================

Each mission flies the same Luminary rope with its own erasable load:
the propellant it expects, its approach angle and its surface stay.

.. requirement:: LGC-CFG-001
   :satisfies: MSN-001, LM-PRP-002
   :subsystem: CFG
   :verification: Test
   :last-modified-by: doors-import

   At P63 the LGC shall compare the descent propellant the erasable load expects with the gauged quantity; if they differ by more than 3%, it shall raise program alarm 01520 and not request ignition.
