========================
Charging and Power Lines
========================
Checks the battery charge current limit and end of charge, power line
switching times, and the overcurrent trip.

Requirements
------------
1. :req:`VM-EPS-004`
2. :req:`VM-EPS-005`
3. :req:`VM-EPS-006`

.. rvt::

   (def battery-ah 40.0)

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Charging

   (Verify (SendTC :line-on :line :star-tracker) = :executed)
   (.set_battery vm 50.0)
   (.set_sun vm true)
   (RunFor 36000)
   (Verify (Telemetry :max-charge-current) <= (/ battery-ah 5))
   (Verify (Telemetry :soc) = 95.0)
   (Verify (Telemetry :charge-current) = 0.0)

.. rvt:: Switching

   (Verify (SendTC :line-off :line :star-tracker) = :executed)
   (Verify (line-on? :star-tracker) = false)
   (Verify (.get (Telemetry :line :star-tracker) :switch_ms) <= 100)
   (Verify (SendTC :line-on :line :star-tracker) = :executed)
   (Verify (line-on? :star-tracker))

.. rvt:: Overcurrent trip

   (.overload vm :star-tracker 1.2 5)
   (Verify (line-on? :star-tracker))
   (.overload vm :star-tracker 1.2 15)
   (Verify (line-on? :star-tracker) = false)
   (Verify (.get (Telemetry :line :star-tracker) :tripped))
   (RunFor 60)
   (Verify (line-on? :star-tracker) = false)
