========================
Boot and Image Selection
========================
Resets the bus computer in each way it can be reset and checks the boot
time, the recorded reset cause, and which software image boots.

Requirements
------------
1. :req:`VM-EXE-004`
2. :req:`VM-EXE-005`
3. :req:`VM-EXE-006`

.. rvt::

   (variations "cause primary-ok quick-resets image"
     ["power-on"            [:power-on  true  1 :primary]
      "commanded"           [:commanded true  1 :primary]
      "two-quick-resets"    [:watchdog  true  2 :primary]
      "three-quick-resets"  [:watchdog  true  3 :backup]
      "primary-corrupt"     [:power-on  false 1 :backup]])

Steps
-----

.. rvt:: The expected image follows the requirement

   (Verify (boot-image primary-ok quick-resets) = image)

.. rvt:: Prepare the images

   (TBD "Load a valid primary and backup image; if primary-ok is false, corrupt one byte of the primary image")

.. rvt:: Reset

   (TBD "Cause the variation's reset, quick-resets times, each within quick-reset-window-s (60 s) of the last boot")
   (TBD "Record the time from reset to the first housekeeping packet")

.. rvt:: After boot

   (TBD "Verify cyclic execution began within boot-time-limit-s (20 s) of the last reset")
   (TBD "Verify the reset cause in telemetry is the variation's cause")
   (TBD "Verify the running image is the variation's image")
