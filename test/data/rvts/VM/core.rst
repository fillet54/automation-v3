Vehicle Manager test definitions
================================
Tests of the Vehicle Manager (VM), the flight software on the satellite
platform's bus computer. The requirements are the ``VM-*`` set in
``test/data/requirements/vehicle_manager.rst``.

The tests are written as flows first: most steps are ``(TBD "...")``
placeholders, to be replaced once the test bench can drive the VM. Steps
that can be checked already, such as a test's table of expected results
against the requirement, are real.

Numbers from the requirements
-----------------------------

.. rvt::

   (def minor-frame-ms 100)
   (def minor-frames-per-major 10)
   (def max-cpu-load 0.70)
   (def watchdog-service-ms 500)
   (def boot-time-limit-s 20)
   (def quick-reset-window-s 60)
   (def quick-resets-for-backup 3)
   (def tc-report-limit-s 2)
   (def time-tag-capacity 1000)
   (def stale-time-tag-s 10)
   (def arm-window-s 30)
   (def max-sequence-count 16383)
   (def launch-mode-minimum-min 30)
   (def safe-mode-actions-s 5)
   (def max-repeated-recoveries 3)
   (def body-rate-limit-dps 0.5)
   (def wheel-unload-fraction 0.80)
   (def burn-overrun-fraction 0.10)
   (def heater-limit 6)
   (def hk-store-bytes 268435456)
   (def hk-bytes-per-second 1024)

What the requirements say, as functions
---------------------------------------
Each test's table of cases is checked against these before anything runs
on the bench.

.. rvt::

   (defn boot-image [primary-ok quick-resets]
     (if (and primary-ok (< quick-resets quick-resets-for-backup)) :primary :backup))

   (def allowed-transitions
     {:launch   [:safe]
      :safe     [:standby]
      :standby  [:nominal :maneuver :safe]
      :nominal  [:standby :safe]
      :maneuver [:standby :safe]})

   (defn transition-allowed? [from to]
     (> (.count (.get allowed-transitions from []) to) 0))

   (defn mode-after-reset [mode cause]
     (if (or (= cause :watchdog) (= cause :exception)) :safe mode))

   (defn loads-shed [soc-percent]
     (if (< soc-percent 40) :all-but-essential
       (if (< soc-percent 50) :non-essential-heaters
         (if (< soc-percent 60) :payload :none))))

   (defn heater-on? [temperature lower upper was-on]
     (if (< temperature lower) true (if (> temperature upper) false was-on)))

   (defn next-sequence-count [n]
     (if (>= n max-sequence-count) 0 (+ n 1)))

   (defn burn-time-limit-s [commanded-s]
     (round (* commanded-s (+ 1 burn-overrun-fraction)) 3))

   (defn housekeeping-hours [store-bytes bytes-per-second]
     (/ store-bytes bytes-per-second 3600))

Driving the platform
--------------------
Shared steps of every test, not written yet.

.. rvt::

   (defn platform-in-mode? [mode]
     (TBD "Read the VM mode from housekeeping telemetry and compare it with the given mode"))

   (defn command-mode [mode]
     (TBD "Send the mode transition telecommand for the given mode and wait for its acceptance report"))

   (defn power-cycle-bus-computer []
     (TBD "Power cycle the bus computer from the bench power supply and wait for the first housekeeping packet"))
