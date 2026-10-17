Air Segment Specification
=========================

The air segment is the unmanned air vehicle and its Vehicle Management
Computer (VMC).

Air vehicle
-----------

.. requirement:: SEG-AIR-001
   :satisfies: SYS-002
   :verification: Test

   The air vehicle shall keep a secure command and telemetry link with the ground station throughout its mission.

.. requirement:: SEG-AIR-002
   :satisfies: SYS-005
   :verification: Test

   The air vehicle shall fly missions planned on the ground and replanned in flight.

.. requirement:: SEG-AIR-003
   :satisfies: SYS-005
   :verification: Test

   The air vehicle shall control its propulsion to meet the mission's endurance and speed.

.. requirement:: SEG-AIR-004
   :satisfies: SYS-005
   :verification: Test

   The air vehicle shall manage its fuel to return to base with a 20% reserve.

.. requirement:: SEG-AIR-005
   :satisfies: SYS-003
   :verification: Test

   The air vehicle shall stop within the runway length available at every approved airfield.

.. requirement:: SEG-AIR-006
   :satisfies: SYS-003
   :verification: Test

   The air vehicle shall monitor its own health and reach a safe state on any critical failure.

.. requirement:: SEG-AIR-007
   :satisfies: SYS-005
   :verification: Test

   The air vehicle shall navigate to within 10 m of its planned track.

.. requirement:: SEG-AIR-008
   :satisfies: SYS-006
   :verification: Test

   The air vehicle shall record its state and events for post-flight analysis.
