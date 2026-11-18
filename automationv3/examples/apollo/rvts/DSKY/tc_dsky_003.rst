==============
Program Change
==============
Asks for each program change V37 must refuse in flight, then for the one
it must accept: P70, an abort.

Requirements
------------
1. :req:`LGC-ABT-002`

.. rvt::
   :definitions:

   (defn program-change-allowed? [program landed]
     (if landed
       (= program 0)
       (or (= program 70) (= program 71))))

.. rvt::

   (Precondition "LM at high gate, the DSKY left to the script"
     (lm-ready-for? :standard :high-gate :manual)
     :heal "Boot a standard mission at high gate with a manual crew"
     (boot-for :standard :high-gate :manual))

Steps
-----

.. rvt:: Changes refused in flight
   :table:

   ("program keys"
     ["P00, before landing"  [0 "V37E00E"]
      "P63, from P64"        [63 "V37E63E"]
      "P66, by keyboard"     [66 "V37E66E"]
      "P12, not in this rope" [12 "V37E12E"]])

   (Verify (program-change-allowed? program false) = false)
   (Keys keys)
   (Verify dsky.light.opr-err = true)
   (Verify lgc.program = 64)
   (Keys "R")

.. rvt:: P70 is accepted, and climbs

   (Verify (program-change-allowed? 70 false))
   (Keys "V37E70E")
   (Verify lgc.program = 70)
   (Wait truth.altitude-rate > 0 :within 1min)
