=========
Lamp Test
=========
Keys V35 and checks every DSKY light comes on, then goes back to what it
showed before once the test is over.

Requirements
------------
1. :req:`LGC-DSK-001`

.. rvt::

   (Precondition "LM at PDI, the DSKY left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----
Each light is a row: the test runs once for each, one after the other.

.. rvt:: Every light
   :table:

   ("light"
     ["PROG"      [dsky.light.prog]
      "OPR ERR"   [dsky.light.opr-err]
      "KEY REL"   [dsky.light.key-rel]
      "COMP ACTY" [dsky.light.comp-acty]
      "RESTART"   [dsky.light.restart]
      "ALT"       [dsky.light.alt]
      "VEL"       [dsky.light.vel]])

   (let [before (Read light)]
     (Keys "V35E")
     (Verify light = true)
     (RunFor (+ lamp-test-s 1))
     (Verify light = before))
