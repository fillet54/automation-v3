====================
Redundancy Switching
====================
Fails each redundant unit in turn and checks the VM switches to its
partner.

Requirements
------------
1. :req:`VM-FDIR-004`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Each unit
   :table:

   ("unit failure"
     ["transponder"       [:transponder-a "no receiver lock for 24 h"]
      "star tracker"      [:star-tracker-a "no valid attitude for 30 s"]
      "reaction wheel"    [:wheel-3 "speed error above limit for 10 s"]
      "charge regulator"  [:bcr-a "output current zero in sunlight for 60 s"]])

   (TBD "Inject the row's failure on its unit with the bench fault injector")
   (TBD "Verify the VM powers off the failed unit and powers on its redundant partner")
   (TBD "Verify the function is restored and a recovery event names the failed unit")
