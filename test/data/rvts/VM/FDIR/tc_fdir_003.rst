==================
SAFE Mode Triggers
==================
Holds each SAFE mode trigger just below and just past its persistence
time, and checks SAFE mode is requested only past it.

Requirements
------------
1. :req:`VM-FDIR-005`

.. rvt::

   (variations "trigger held-s requests-safe"
     ["attitude-59s"      [:attitude-error-11deg 59 false]
      "attitude-61s"      [:attitude-error-11deg 61 true]
      "battery-9s"        [:soc-39-percent 9 false]
      "battery-11s"       [:soc-39-percent 11 true]
      "uplink-71h"        [:no-uplink 255600 false]
      "uplink-73h"        [:no-uplink 262800 true]
      "recovery-stuck"    [:uncleared-fault 301 true]])

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Hold the trigger

   (TBD "Apply the variation's trigger on the bench for held-s seconds, then remove it")

.. rvt:: SAFE or not

   (TBD "If requests-safe, verify the mode becomes SAFE within 1 s of the persistence time")
   (TBD "If not, verify the mode stays NOMINAL")
