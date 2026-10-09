========================================
Vehicle Manager Software Requirements
========================================

.. note::

   Written for this project as a realistic sample, not taken from any
   program. Every number is illustrative.

The Vehicle Manager (VM) is the flight software that runs on the bus
computer of a low Earth orbit satellite platform. It schedules the
on-board software, handles telecommands and telemetry, manages the
platform's modes, protects it against faults, and manages power, thermal
control, attitude control, time and on-board storage. The payload has its
own computer and is outside this specification.

Each requirement is an ``.. requirement::`` directive with its id; the
subsystem is the middle part of the id (``VM-TC-003`` is ``TC``).

Executive
=========

.. requirement:: VM-EXE-001

   The VM shall execute its scheduled tasks in a fixed cyclic schedule
   with a major frame of 1 s divided into 10 minor frames of 100 ms.

.. requirement:: VM-EXE-002

   The VM shall complete every task scheduled in a minor frame before the
   start of the next minor frame. A minor frame overrun shall be counted
   in telemetry and reported as an event.

.. requirement:: VM-EXE-003

   The VM shall service the hardware watchdog at least once every 500 ms
   while all of the following hold:

   - every scheduled task has run within its last two scheduled periods;
   - no minor frame overrun has occurred in the last 10 consecutive minor
     frames.

.. requirement:: VM-EXE-004

   On power-on or processor reset, the VM shall complete its boot sequence
   and begin cyclic execution within 20 s.

.. requirement:: VM-EXE-005

   The VM shall record the cause of each processor reset (power-on,
   watchdog, commanded, or exception) in non-volatile memory, and report
   it in telemetry after the next boot.

.. requirement:: VM-EXE-006

   The VM shall boot from the primary software image unless one of the
   following holds, in which case it shall boot from the backup image:

   - the primary image fails its integrity check;
   - three consecutive resets have occurred, each within 60 s of boot.

.. requirement:: VM-EXE-007

   The VM shall not use more than 70% of the processor's capacity,
   averaged over any major frame, in any mode.

Telecommand
===========

.. requirement:: VM-TC-001

   The VM shall accept telecommands as CCSDS space packets received from
   either transponder.

.. requirement:: VM-TC-002

   The VM shall reject a telecommand, without executing it, if any of the
   following checks fails:

   - the packet's CRC;
   - the packet length against the length defined for its command code;
   - every argument against the range defined for it;
   - the command's authentication, when command authentication is
     enabled.

.. requirement:: VM-TC-003

   The VM shall report the acceptance or rejection of every telecommand
   in telemetry within 2 s of its receipt, with the reason for any
   rejection.

.. requirement:: VM-TC-004

   The VM shall execute accepted telecommands in the order they were
   received.

.. requirement:: VM-TC-005

   The VM shall store up to 1000 time-tagged telecommands and execute
   each within 1 s of its time tag.

.. requirement:: VM-TC-006

   The VM shall discard a time-tagged telecommand whose time tag is more
   than 10 s in the past when it is received, and report it as rejected.

.. requirement:: VM-TC-007

   The VM shall require a hazardous telecommand to be preceded, within
   30 s, by an arm telecommand for the same command code, and shall
   reject it otherwise. The hazardous telecommands include:

   - propulsion valve open;
   - deployment actuator fire;
   - software image overwrite.

.. requirement:: VM-TC-008

   The VM shall execute the hardware-decoded reset and safe-mode commands
   independently of the VM's own telecommand processing.

Telemetry
=========

.. requirement:: VM-TM-001

   The VM shall generate housekeeping telemetry as CCSDS space packets.

.. requirement:: VM-TM-002

   The VM shall generate each housekeeping packet at its defined rate,
   selectable by telecommand from 0.1 Hz to 10 Hz, with the rates at
   power-on taken from the default telemetry table.

.. requirement:: VM-TM-003

   The VM shall time-stamp each telemetry packet with the on-board time at
   which its data was sampled, to a resolution of 1 ms.

.. requirement:: VM-TM-004

   The VM shall downlink real-time telemetry at 32 kbit/s on the S-band
   link when a ground station is in contact.

.. requirement:: VM-TM-005

   The VM shall record all housekeeping telemetry to on-board storage
   whether or not a ground station is in contact.

.. requirement:: VM-TM-006

   The VM shall generate an event packet within 1 s of each of the
   following:

   - a mode transition;
   - a telecommand rejection;
   - a fault detection or recovery action;
   - a parameter limit violation.

.. requirement:: VM-TM-007

   The VM shall maintain a monotonic packet sequence count for each
   telemetry application, wrapping at 16383.

Mode management
===============

.. requirement:: VM-MOD-001

   The VM shall operate the platform in exactly one of the following
   modes at a time:

   - LAUNCH: from separation until the first commanded transition;
   - SAFE: Sun-pointing, minimum power, payload off;
   - STANDBY: nominal attitude, payload off;
   - NOMINAL: payload operations;
   - MANEUVER: orbit control with propulsion.

.. requirement:: VM-MOD-002

   The VM shall enter LAUNCH mode on its first boot after separation is
   detected, and shall remain in LAUNCH mode for at least 30 minutes.

.. requirement:: VM-MOD-003

   The VM shall make only the following mode transitions on telecommand:

   - LAUNCH to SAFE;
   - SAFE to STANDBY;
   - STANDBY to NOMINAL, STANDBY to MANEUVER and STANDBY to SAFE;
   - NOMINAL to STANDBY and NOMINAL to SAFE;
   - MANEUVER to STANDBY and MANEUVER to SAFE.

   Any other commanded transition shall be rejected.

.. requirement:: VM-MOD-004

   The VM shall transition to SAFE mode autonomously, from any mode other
   than LAUNCH, when FDIR requests it.

.. requirement:: VM-MOD-005

   On entering SAFE mode, the VM shall within 5 s:

   - command the payload off;
   - command the AOCS to Sun-pointing;
   - shed the non-essential loads;
   - suspend the time-tagged telecommand queue.

.. requirement:: VM-MOD-006

   The VM shall leave SAFE mode only on telecommand.

.. requirement:: VM-MOD-007

   The VM shall restore the mode it was in before a processor reset,
   except that it shall enter SAFE mode if the reset was caused by the
   watchdog or an exception.

Fault detection, isolation and recovery
=======================================

.. requirement:: VM-FDIR-001

   The VM shall monitor each parameter in the monitoring table against its
   limits every major frame, and declare a limit violation after the
   number of consecutive out-of-limit samples defined for it.

.. requirement:: VM-FDIR-002

   The VM shall execute the recovery action defined for a limit violation
   within 1 s of declaring it.

.. requirement:: VM-FDIR-003

   The VM shall allow each monitor and each recovery action to be enabled
   and disabled individually by telecommand.

.. requirement:: VM-FDIR-004

   The VM shall switch to the redundant unit when a unit fails, for each
   of the following:

   - transponder;
   - star tracker;
   - reaction wheel (from four to the remaining three);
   - battery charge regulator.

.. requirement:: VM-FDIR-005

   The VM shall request SAFE mode if any of the following persists for
   more than its stated time:

   - attitude error greater than 10 deg, for 60 s;
   - battery state of charge below 40%, for 10 s;
   - loss of uplink, for 72 hours;
   - any FDIR recovery action that does not clear its fault, for 300 s.

.. requirement:: VM-FDIR-006

   The VM shall not take the same autonomous recovery action more than
   three times within 24 hours without a telecommand acknowledging it.

.. requirement:: VM-FDIR-007

   The VM shall keep a log of the last 256 fault detections and recovery
   actions in non-volatile memory.

Attitude and orbit control interface
====================================

.. requirement:: VM-AOCS-001

   The VM shall run the AOCS control task at 10 Hz in every mode.

.. requirement:: VM-AOCS-002

   The VM shall command the AOCS to the attitude mode required by the
   platform mode:

   - Sun-pointing in LAUNCH (after rate damping) and SAFE;
   - Nadir-pointing in STANDBY and NOMINAL;
   - the commanded inertial attitude in MANEUVER.

.. requirement:: VM-AOCS-003

   In LAUNCH mode, the VM shall command rate damping until the body rates
   are below 0.5 deg/s on every axis for 60 s, then Sun acquisition.

.. requirement:: VM-AOCS-004

   The VM shall enable propulsion only in MANEUVER mode.

.. requirement:: VM-AOCS-005

   The VM shall end a thruster burn when the commanded delta-v is reached,
   or when the burn duration exceeds the commanded duration by 10%,
   whichever comes first.

.. requirement:: VM-AOCS-006

   The VM shall unload reaction wheel momentum with the magnetorquers when
   the momentum of any wheel exceeds 80% of its capacity.

Electrical power
================

.. requirement:: VM-EPS-001

   The VM shall compute the battery state of charge every major frame from
   the battery voltage, current and temperature.

.. requirement:: VM-EPS-002

   The VM shall shed loads in the order of the load shedding table when
   the battery state of charge falls below each of the following
   thresholds:

   - 60%: the payload;
   - 50%: the non-essential heaters;
   - 40%: everything except the essential loads (bus computer,
     receivers, essential heaters).

.. requirement:: VM-EPS-003

   The VM shall restore loads shed for low state of charge only on
   telecommand.

.. requirement:: VM-EPS-004

   The VM shall limit battery charge current to C/5 and stop charging at a
   state of charge of 95%.

.. requirement:: VM-EPS-005

   The VM shall switch each power line on or off within 100 ms of the
   telecommand or autonomous action that requests it, and report its
   state and current in telemetry.

.. requirement:: VM-EPS-006

   The VM shall switch off a power line whose current exceeds its trip
   limit for more than 10 ms, and shall not switch it back on
   autonomously.

Thermal control
===============

.. requirement:: VM-TCS-001

   The VM shall control each heater circuit with a thermostat on its
   control sensor, using the set points defined in the thermal table for
   the current mode.

.. requirement:: VM-TCS-002

   The VM shall turn a heater on when its control temperature falls below
   its lower set point, and off when it rises above its upper set point.

.. requirement:: VM-TCS-003

   The VM shall use the redundant sensor of a heater circuit when its
   control sensor reads outside -60 degC to +100 degC.

.. requirement:: VM-TCS-004

   The VM shall keep the battery between 0 degC and +30 degC and the
   propulsion tank and lines above +10 degC in every mode.

.. requirement:: VM-TCS-005

   The VM shall not have more than six heater circuits on at once.

Time management
===============

.. requirement:: VM-TIM-001

   The VM shall maintain on-board time as seconds and subseconds since
   2000-01-01T12:00:00 TAI, with a resolution of 1 microsecond.

.. requirement:: VM-TIM-002

   The VM shall synchronise on-board time to the GNSS receiver's pulse per
   second when the receiver reports a valid fix, to within 10
   microseconds.

.. requirement:: VM-TIM-003

   Without a valid GNSS fix, the VM shall propagate on-board time from its
   oscillator, and report the time since the last synchronisation in
   telemetry.

.. requirement:: VM-TIM-004

   The VM shall allow on-board time to be set and adjusted by telecommand,
   and shall reject a time adjustment of more than 1 s while a time-tagged
   telecommand is due within the next 60 s.

.. requirement:: VM-TIM-005

   The VM shall preserve on-board time across a processor reset with an
   error of less than 1 ms.

Data storage and memory
=======================

.. requirement:: VM-MEM-001

   The VM shall store telemetry in on-board mass memory in separate
   packet stores for housekeeping, events and payload data.

.. requirement:: VM-MEM-002

   The VM shall store at least 72 hours of housekeeping telemetry before a
   packet store wraps.

.. requirement:: VM-MEM-003

   The VM shall downlink a packet store's contents, oldest first, on
   telecommand, at up to 2 Mbit/s on the X-band link, and keep them until
   the ground confirms receipt.

.. requirement:: VM-MEM-004

   The VM shall scrub its EDAC-protected memory completely at least once
   every 24 hours, correcting single-bit errors and reporting double-bit
   errors as events.

.. requirement:: VM-MEM-005

   The VM shall accept a software image upload in segments, verify the
   complete image against its CRC, and write it to the non-active image
   slot only on a separate telecommand.

.. requirement:: VM-MEM-006

   The VM shall allow any memory address to be dumped and patched by
   telecommand, with a patch to code memory treated as a hazardous
   telecommand.
