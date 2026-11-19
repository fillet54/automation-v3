Landing snippets
================
For the landing scripts, on top of the snippets of the folders above.

Flies to touchdown, keeps the trajectory as the run's files, and checks
the landing.

.. rvt:: Land and check

   (land-and-keep "#{descent}")
   (Verify (landed-within-limits?))
