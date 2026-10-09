==================
SAFE Mode Triggers
==================
Holds each SAFE mode trigger just short of and just past its
persistence time, and checks SAFE is requested only past it.

Requirements
------------
1. :req:`VM-FDIR-005`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Each trigger
   :table:

   ("trigger held-s requests-safe"
     ["attitude, 59 s"   [:attitude-error-11deg 59 false]
      "attitude, 61 s"   [:attitude-error-11deg 61 true]
      "battery, 9 s"     [:soc-39-percent 9 false]
      "battery, 11 s"    [:soc-39-percent 11 true]
      "no uplink, 71 h"  [:no-uplink 255600 false]
      "no uplink, 73 h"  [:no-uplink 262800 true]
      "recovery stuck"   [:uncleared-fault 301 true]])

   (BringToMode :nominal)
   (TBD "Apply the row's trigger for held-s seconds, then remove it")
   (TBD "Verify the mode is SAFE exactly when requests-safe is true")
