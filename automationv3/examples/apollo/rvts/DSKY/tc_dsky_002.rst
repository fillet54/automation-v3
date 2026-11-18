==============
Operator Error
==============
Keys entries the computer can't accept and checks each lights OPR ERR,
and that RSET puts it out.

Requirements
------------
1. :req:`LGC-DSK-002`

.. rvt::

   (Precondition "LM at PDI, the DSKY left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----

.. rvt:: Each bad entry
   :table:

   ("entry"
     ["a verb only the computer flashes" ["V99E"]
      "an unknown noun"                  ["V16N12E"]
      "a one-digit verb"                 ["V5E"]
      "a noun with no verb"              ["N68E"]
      "a refused program change"         ["V37E63E"]])

   (Verify dsky.light.opr-err = false)
   (Keys entry)
   (Verify dsky.light.opr-err = true)
   (Keys "R")
   (Verify dsky.light.opr-err = false)
