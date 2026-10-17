Thermal control
===============

.. requirement:: VM-TCS-001
   :satisfies: SEG-SPC-008
   :subsystem: TCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall control each heater circuit with a thermostat on its
   control sensor, using the set points defined in the thermal table for
   the current mode.

.. requirement:: VM-TCS-002
   :satisfies: SEG-SPC-008
   :subsystem: TCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall turn a heater on when its control temperature falls below
   its lower set point, and off when it rises above its upper set point.

.. requirement:: VM-TCS-003
   :satisfies: SEG-SPC-008
   :subsystem: TCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall use the redundant sensor of a heater circuit when its
   control sensor reads outside -60 degC to +100 degC.

.. requirement:: VM-TCS-004
   :satisfies: SEG-SPC-008
   :subsystem: TCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall keep the battery between 0 degC and +30 degC and the
   propulsion tank and lines above +10 degC in every mode.

.. requirement:: VM-TCS-005
   :satisfies: SEG-SPC-008
   :subsystem: TCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall not have more than six heater circuits on at once.
