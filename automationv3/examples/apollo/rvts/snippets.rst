Snippets
========
Pieces of scripts to start from. The editor offers them in a block
(Ctrl+Space, or the Snippets menu), and the console in its Snippets tab.
``#{name}`` is a field to fill in; Tab moves from one to the next. A
folder's own snippets.rst adds to these, and replaces one of the same
name.

Setting up
----------

Every mission and start point a script flies, one variation each.

.. rvt:: Variations by mission and start

   (variations "mission start"
     ["#{standard from PDI}" [:standard :pdi]])

Boots the LM for the variation, unless it already is, so runs of the
same variation can share a flight.

.. rvt:: Precondition: LM booted

   (Precondition "LM booted for the variation's mission, at its start point"
     (lm-ready? mission start)
     :heal "Boot the variation's mission at its start point"
     (boot mission start))

Flying
------

Lets the flight run to a phase, then checks a point.

.. rvt:: Fly to a phase and check

   (FlyTo #{:high-gate})
   (Verify #{lgc.program} = #{64})

Waits for a point to reach a value, looking once a second.

.. rvt:: Wait for a value

   (Wait #{landed} = #{true} :within #{15min} :every wait-every)

Checking the landing
--------------------

The landing gear's limits and the distance from the site.

.. rvt:: Landed within limits

   (Verify (landed-within-limits?))
   (Verify (abs (Read touchdown.miss-m)) <= site-radius-m)
