# Apollo lunar module samples: implementation plan

Replace every sample UUT, environment, script and requirement set with one
coherent, runnable example: the Apollo lunar module's powered descent. The
UUT is a small simulation of the LM and its guidance computer (the LGC,
running a "Luminary" software load). It is limited, but it really flies:
scripts key the DSKY, flip panel switches, inject faults, run time forward
and check what the vehicle and the computer did.

The point of the example is to show automation-v3's features with tests
that make sense. The most important one is **variations**: the software
supports two missions, a **standard** mission and an **extended** mission
(extra descent propellant, batteries, oxygen and water), and the
simulation can start from several **start points**. These are startup
parameters, so a script's variations become runs that really are
different.

When this is done, the Apollo example is the **only** demo code in the
repository and the only demo code shipped with the application. No other
UUT, environment, sample script or sample requirement set exists
anywhere, test code included.

Branch: `apollo-samples`, off master at a24a4dc (`source-tree` was
fast-forwarded into master on 2026-11-17, after all 806 tests passed).
Paths are under `automationv3/` unless they start with `test/`, `docs/`
or `plans/`.

## What was checked before writing this (2026-11-17)

| Checked | Result |
| --- | --- |
| Sample plugins | `plugins/vm` (the Vehicle Manager, 950 lines), and `plugins/sample` (the `demo` stub UUT, the `sim` and `bench` environments, `StartDemo`, `SnapshotDemo`, `SetupSimulation`, `Table-Driven`, and the `attached-files` document directive with its snippet). |
| Sample data | `test/data/rvts` (BRA, FUE, VM: about 80 scripts), `test/data/doors` (5 specs plus `history.json`, the DOORS history), `test/data/worker.json`. |
| Who reads the sample data | `demo.py` (`automation-v3 demo`: `SAMPLES = test/data`), `test/data/load_sample.py`, `make_workspaces.py`, and 27 test modules. Most of those tests write their own small scripts inline with `(uut :demo)` and `(environments :sim)`; a few read `test/data/rvts` files directly (`test_example_set`, `test_export`, `test_demo`, `test_report_pages`, `test_jobs`). |
| How UUTs are found | `uut._registry` walks `UUT.__subclasses__()` after `load_plugins()`. Any imported subclass counts, so a UUT defined in the test package registers once it is imported. |
| How plugins are found | `pkgutil.iter_modules(automationv3.plugins.__path__)` plus entry points (`setup.py`). |
| Variations | `(variations "sym ..." ["name" [values...] ...])`, once per script. `:variations:` on `rvt` blocks (including `:definitions:` blocks) and `rvt-variant` sections. Queue filter predicates over the bound symbols, `name` and `index`. Every variation is its own run. |
| Table blocks | `.. rvt::` with `:table:`: the block's steps run once per row, all in one run. |
| Warm scheduling | Workers run first the job whose preconditions already hold or can heal. `start(version, env)` only happens in force mode. So the "start the UUT in this configuration" step belongs in a precondition's heal. `tc_bra_00004` already uses this pattern. |
| Clocks | `Environment.clock(handles)`. `SimClock(ref, step=...)` for a simulation that only moves when stepped; `SimClock(ref)` without `step` waits for the simulation to get there. |
| Reference model | `~/Work/apollo11` (heddle + loom, C++). Its figures (masses, engine, Isp, throttle limits, timeline) and its DSC requirements are the source for this model. Nothing is copied from the Airbus requirement set (MPL-2.0). |

## Decisions

1. **One demo domain, everywhere.** The `vm` plugin, the `sample`
   plugin (the `demo` UUT, the `sim` and `bench` environments and its
   blocks), `test/data/rvts`, `test/data/doors` and
   `test/data/worker.json` are all deleted. Nothing is kept for
   compatibility, and no stub is kept for the tests.
2. **The framework's unit tests stay, and run against `lm`.** The
   tests in `test/*.py` check the framework itself (jobs, reports,
   the LSP, the editor, requirements import) and are kept. Every test
   that uses `(uut :demo)`, `(environments :sim :bench)`, the `demo`
   handle, `StartDemo`/`SnapshotDemo`/`Table-Driven`,
   `AUTOMATION_DEMO_BUILDS`, or the old sample scripts and requirements
   is rewritten against the `lm` UUT, the `sim`/`lms` environments, the
   Apollo blocks, `AUTOMATION_LM_BUILDS`, and the Apollo scripts and
   requirement history. A test that only needs "some UUT" uses `lm`
   with the cheapest boot (`:start :surface`, or a DSKY-only check),
   so the suite doesn't fly descents it doesn't need.
3. **The example ships inside the package**, in
   `automationv3/examples/apollo/`: `rvts/` (scripts), `doors/` (specs
   and history), `worker.json`, and `README.rst` (the outcome matrix).
   `demo.py` reads from there, so `automation-v3 demo` works from an
   installed package, not just from a checkout. Package data has to be
   declared (there is no `MANIFEST.in` today: check how `web/templates`
   and `plugins/sample/snippets` get shipped now, and do the same, or
   add `package_data`). The built docs still come from a checkout's
   `docs/`: from an installed package the demo runs without them (as
   `--no-docs` does today).
4. **Version = the software (rope). Variation = how the vehicle is
   loaded and started.** This matches how Apollo worked. The Luminary
   software was woven into fixed memory. Each mission's constants went
   into erasable memory (the "erasable load"). Propellant and tanks were
   hardware. So the UUT version is a Luminary revision, and the mission
   and start point are chosen at boot, which makes them variations.
5. **The plugin is `plugins/apollo`, the UUT is `lm`, and its handle is
   `lm`.** The model itself is plain Python with no framework imports, so
   it can be unit tested on its own.
6. **Fidelity: limited, deterministic, fast.** A 2-D point mass over a
   flat Moon with a centrifugal term. No attitude dynamics beyond a
   pitch-rate limit, no RCS. Noise only from a seed. A full descent from
   powered descent initiation (PDI) to touchdown takes under 1 s of CPU
   time in `sim`.
7. **The test script is the crew.** A built-in "nominal crew" can be
   switched on, so long scripts don't have to click through every step of
   P66. Scripts that test what the crew does switch it off and do it
   themselves.
8. **Requirements are written fresh** for this example, with this
   project's own IDs. The texts follow the DSC requirements in
   `~/Work/apollo11`, which are this project's own work, not Airbus's.

## The UUT

### Versions (Luminary revisions)

| Version | Flew on | Standard mission | Extended mission | Behaviour in the model |
| --- | --- | --- | --- | --- |
| `LUM099` | Apollo 11 | yes | **rejects the load** | Can't be booted with an extended erasable load. A precondition that heals by booting extended fails, so the run is **blocked**. |
| `LUM131` | Apollo 13 | yes | yes | **Seeded defect:** propellant remaining (N93, see below) is computed against the standard load's capacity. With an extended load it reads about 106% at PDI, and the LGC's PROPELLANT LOW caution comes on late. Standard missions are unaffected. |
| `LUM210` | Apollo 15–17 | yes | yes | Fixed. The newest version, so it is the default. |

The revision numbers and the missions they flew on are real. Their
mission support is close to history: extended LMs first flew with
Luminary 1E on Apollo 15. **The defect in `LUM131` is invented.** The
module docstring and the README must say so.

The version digest is the SHA-256 of a canonical "rope" JSON:
`{"revision": "LUM210", "flags": {...}}`. Flags such as
`"prop_capacity_from_load": true` turn behaviours on and off. Local builds
use the same format, so a developer can "fix" `LUM131` in a local build,
upload it, and see the scratch run pass. That covers the
`find_local_build` / `upload_build` / `report_versions` path that the
`demo` stub covers today. The build repository is a folder named by
`AUTOMATION_LM_BUILDS`, and a build file is `luminary.json`.

### Missions (the erasable load and the vehicle)

The model's own figures, loosely based on the H-mission and J-mission
LMs. They are not flight data.

| | `:standard` | `:extended` |
| --- | --- | --- |
| Mass at PDI | 15,100 kg | 16,400 kg |
| Descent propellant | 8,200 kg | 8,700 kg (longer tanks) |
| Descent batteries | 4 × 415 Ah | 5 × 415 Ah |
| Descent O₂ tanks | 1 (22 kg) | 2 (44 kg) |
| Descent water tanks | 1 (150 kg) | 2 (225 kg) |
| Planned surface stay | 33 h | 75 h |
| Approach angle in P64 | 16° | 25° |
| PROPELLANT LOW caution (LGC) | 6% of the load | 6% of the load |

The model chooses consumption rates so that a standard LM lasts about
38 h on the surface and an extended one about 80 h: each meets its own
planned stay with margin, and a standard LM can't do an extended stay.

The **vehicle** (hardware: tanks, batteries) and the **erasable load**
(software constants) are set separately at boot, and normally match. A
mismatch is a test case in its own right (`CFG/tc_cfg_001`): the LGC
compares its load against the gauged quantities at P63 entry and raises
program alarm `01520` (the model's own code) instead of igniting.

### Start points

| `:start` | State | Sim time to touchdown |
| --- | --- | --- |
| `:pdi` | P63, V99 N62 flashing for ignition: 15 km altitude, 1,690 m/s, about 470 km uprange | about 12 min |
| `:high-gate` | P64 just entered, about 2,300 m altitude, landing site in view | about 3.5 min |
| `:low-gate` | P64 at 150 m, about to take P66 | about 1.5 min |
| `:surface` | P68 after touchdown, engine safed, surface stay begins | — |

Start points after `:pdi` are produced by flying from PDI with the
nominal crew. The result is cached in the environment's work directory,
keyed by (rope digest, mission, model version). Every start point is
therefore a state the model really reaches, and stays consistent as the
model changes. The first boot to a given start point costs one flight.
Later boots load the cached state.

### Boot configuration

`(StartLM {...})` (a block) and `(.boot lm {...})` (the handle) take:

| Key | Values | Default |
| --- | --- | --- |
| `:mission` | `:standard` `:extended` | `:standard` |
| `:vehicle` | `:standard` `:extended` | same as `:mission` |
| `:start` | `:pdi` `:high-gate` `:low-gate` `:surface` | `:pdi` |
| `:crew` | `:nominal` `:hands-off` `:manual` | `:nominal` |
| `:seed` | integer | `0` |

`UUT.start(version, env)` (force mode) boots the defaults. Boot returns
`:accepted` or `:rejected-load` (for `LUM099` with an extended load).
`StartLM` fails its step on a rejection, so a heal that needs it fails
and the run is blocked.

`:crew :nominal` flies the procedure: PRO at V99, V57 once the landing
radar data is good, V16 N68, P66 at low gate, and rate-of-descent (ROD)
clicks down to contact. `:hands-off` does PRO and V57 only, so guidance
lands in P65. `:manual` does nothing: the script does all of it.

### What is modelled

| Part | Model |
| --- | --- |
| Dynamics | Downrange `x`, altitude `h`, velocities, and mass. g = 1.62 m/s², minus vx²/(R+h) with R = 1,737.4 km. Thrust along the commanded pitch, rate-limited to 10°/s. 10 Hz while the engine burns, coarser while coasting, and 60 s steps on the surface. |
| Descent engine | 45,040 N at 100%, Isp 305 s. Throttle 10–60%, or the fixed full-throttle position at 92.5%. The DECA never commands anything in between. |
| Ascent stage | Used only by ABORT STAGE: staging drops the descent stage, 15,600 N at Isp 311 s, P71 climbs. No ascent to orbit. |
| Guidance (2 s cycle) | P63 braking and P64 approach: a simplified quadratic (Klumpp-style) law to each phase's target position, velocity and acceleration. Full throttle until the commanded thrust falls below 57%, then throttling (the "throttle down" event). P64 targets follow the mission's approach angle. P65: vertical descent at 1 m/s. P66: holds the commanded rate of descent, ±0.3048 m/s per ROD click. P68: engine off at contact. P70/P71: abort. |
| Navigation | Integrates the true acceleration plus a small bias. Computed altitude starts with a +900 m error. The landing radar corrects it only after V57, and only while its data is good. |
| Landing radar | Altitude good below 12,000 m, velocity good below 7,500 m (after windows-up). Noise from the seed. Can be failed from the bench. |
| Executive | Load = program base load + monitor display job (V16 N68: +10%) + rendezvous radar counter interrupts (RR switch at AUTO with the CDU phase fault: +15%). Above 100%, overload builds up until program alarm 1202 and a restart, which drops the display job. Navigation and guidance carry on. |
| DSKY | Keys `V N 0-9 + - E(ENTR) P(PRO) R(RSET) K(KEY REL) C(CLR)`. Shows PROG, VERB, NOUN, R1–R3, flashing, and lights (PROG, OPR ERR, KEY REL, COMP ACTY, RESTART, ALT, VEL). Verbs: 06, 16, 35 (lamp test), 37, 57, 99. Nouns: 60, 62, 63, 64, 68, 93 (propellant remaining %, the model's own). Any other verb/noun gives OPR ERR, cleared by RSET. |
| Panel switches | ABORT, ABORT STAGE, ENGINE STOP, MASTER ARM, ENGINE ARM (`:off :des :asc`), ROD switch (clicks), RR MODE (`:lgc :auto :slew`), MASTER ALARM pushbutton. |
| Caution and warning | MASTER ALARM, CAUTION, WARNING. Caution lights: PROG (program alarm), DES QTY (the hardware low-level sensor at 5.6% remaining), PRPLNT LOW (the LGC's 6% caution), BATTERY, ECS, LDG RDR. |
| EPS | Descent and ascent batteries, bus volts as a function of load and state of charge. BATTERY caution on a battery fault or a low bus; WARNING when the bus is below the equipment's minimum. |
| ECS | O₂ and water, used at fixed rates per vehicle mode (descent, surface active, surface rest). ECS caution under 10% of either. |
| Contact | Contact light at 1.7 m (the probes). Touchdown records vertical and horizontal velocity and the distance from the landing site. |
| Trajectory | 1 Hz history of time, x, h, vx, vz, throttle, program and propellant. Used by attachments and by checks over the whole flight ("the throttle was never between 60% and 92.5%"). |

Out of scope: three axes, the DAP, landing point redesignation geometry
beyond a downrange shift (P64 redesignation is a TBD flow, see the
scripts), lunar ascent and rendezvous, comms, thermal.

### Environments

`lms` keeps its name. The Lunar Module Mission Simulator was the real
crew-training simulator, and the generic alternatives (`realtime`,
`paced`, `hil`) either describe only the clock or claim hardware that
isn't there. `sim` is the fast one.

| Environment | What it is | Clock | Fingerprint |
| --- | --- | --- | --- |
| `sim` | Software-only. Stepped and deterministic. | `SimClock(lm.time.sim, step=...)`: Wait runs the LM forward | environment, platform, python, model version |
| `lms` | A stand-in for the Lunar Module Mission Simulator: the same model, paced against the wall clock (`pace`, default 20× real time). DSKY keys take 0.3 s of simulated time each, and terrain makes the landing radar drop out. | `SimClock(lm.time.sim)` without a step. Each access catches the simulation up to `wall × pace`, so no background process is needed. | the above, plus `pace` and the terrain model's version |

Most scripts declare `(environments :sim :lms)`. A few are `:lms`-only
(display timing) or `:sim`-only (the 75-hour surface stay).

`worker.json` for the demo:

```json
{"environments": {"sim": {}, "lms": {"pace": 20}}}
```

### Connectors (refs) and the handle

Points are connectors, as `vm` has today, so `Read`, `Verify`, `Wait`,
`SetValue`, `SetFixedValue` and `ClearFixedValue` all work on them.

- `lm.time.sim` (s), `lm.time.met` (mission elapsed time, "h:mm:ss")
- `lm.lgc.program`, `lm.lgc.alarms` (vector of codes), `lm.lgc.restarts`,
  `lm.lgc.load` (executive load fraction), `lm.lgc.config.mission`
- `lm.dsky.verb`, `.noun`, `.r1`, `.r2`, `.r3`, `.flashing`,
  `lm.dsky.light.{prog,opr-err,key-rel,comp-acty,restart,alt,vel}`
- `lm.nav.altitude`, `.altitude-rate`, `.delta-h`, `lm.lr.alt-good`,
  `.vel-good`
- `lm.truth.altitude`, `.altitude-rate`, `.downrange`, `.vx`
- `lm.deca.throttle` (%), `lm.engine.descent.on`, `lm.engine.ascent.on`,
  `lm.staged`
- `lm.prop.descent-kg`, `.ascent-kg`, `.low-level` (hardware sensor),
  `lm.lgc.prop-percent`
- `lm.cwea.master-alarm`, `.caution`, `.warning`,
  `lm.cwea.light.{prog,des-qty,prplnt-low,battery,ecs,ldg-rdr}`
- `lm.eps.bus-volts`, `lm.eps.battery.{1..5}.{ah,fault}`
- `lm.ecs.o2-kg`, `lm.ecs.water-kg`
- `lm.contact`, `lm.landed`, `lm.touchdown.{vz,vx,miss-m}`
- Panel (settable): `lm.panel.{abort,abort-stage,engine-stop,master-arm,engine-arm,rr-mode}`
- Bench (settable, fixable): `lm.bench.lr-failed`,
  `lm.bench.rr-cdu-fault`, `lm.bench.battery.N.fault`,
  `lm.bench.bus-load-amps`, `lm.bench.o2-leak-kg-h`

Handle methods: `boot`, `config`, `at_start` (true until the vehicle has
moved since boot), `version`, `run_for(s)`, `run_until(ref-path, value,
limit)`, `keys(str)`, `click_rod(n)`, `push_master_alarm()`,
`trajectory()` (vector of maps), `throttle_history()`,
`alarm_history()`, `snapshot()`.

### Blocks (`plugins/apollo/blocks.py`)

| Block | Kind | |
| --- | --- | --- |
| `(StartLM {:mission m :start s ...})` | action | Boots. Renders the configuration as a table (as `StartDemo` does). |
| `(Keys "V16N68E")` | action | Keys the DSKY. Returns the DSKY's display afterwards. Renders as key caps. |
| `(Proceed)` | action | PRO |
| `(ClickROD n)` | action | n clicks of the ROD switch, negative for down |
| `(RunFor s)` | action | Runs simulated time forward |
| `(FlyTo :high-gate)` | action | Runs until a phase (`:throttle-down :high-gate :low-gate :contact`), with a limit |
| `(Telemetry name)` | value | Shorthand for a few derived values (`:touchdown`, `:max-alarm-rate`) |
| `(AttachTrajectory "label")` | action | Attaches `label.csv`, and `label.svg` (an altitude/downrange and throttle plot, drawn by hand in SVG with no plotting dependency). Replaces `SnapshotDemo`. |
| `Read`, `SetValue`, `SetFixedValue`, `ClearFixedValue` | | For `lm` connectors, as in `vm/blocks.py` today |

The `attached-files` document directive and its snippet move from
`plugins/sample` to `plugins/apollo`, unchanged except for names.
`SetupSimulation` and `Table-Driven` are deleted. They were stubs, and
`:table:` blocks replace them. Check `test_blocks`, `test_compose`,
`test_plugins` and `docs/blocks/writing-blocks.rst`: whatever block
feature they exercise (`execute_forms`, unevaluated arguments, a block
that renders itself as a table) must be exercised by a real Apollo block
instead. `StartLM` renders its configuration as a table, and `Keys`
renders itself as key caps. If a feature has no natural home in an
Apollo block, the test defines its own block class inside the test
module: that is a test of the block API, not a UUT.

### Module layout

```
plugins/apollo/
  __init__.py      exports, register() (connector function, document directive)
  model/           pure Python, no automationv3 imports
    missions.py    the mission and vehicle tables, start points
    vehicle.py     dynamics, engines, tanks, batteries, ECS, sensors, CWEA hardware
    lgc.py         executive, programs, guidance, navigation, DSKY, alarms; rope flags
    crew.py        the nominal and hands-off crews
    sim.py         LM: one state dict, step(dt), the event log, the trajectory
  uut.py           LunarModule(UUT): versions, ropes, builds, install/start, state file
  environments.py  Sim, Lms (clock, fingerprint, pacing)
  handle.py        LunarModuleHandle
  connectors.py    the connector table and children()
  blocks.py        the blocks above
  documents.py     the attached-files directive
  plot.py          the trajectory SVG
  snippets/apollo/attached-files.rst
```

The state is one JSON-serialisable dict, loaded and saved per handle call
as `vm` does. The trajectory is kept at 1 Hz, so a 12-minute flight is
about 720 rows.

## Requirements (the DOORS sample)

Three specs in `examples/apollo/doors/specs/`, in the same rst format as
today's specs:

| Key | Title | Level | Parent | About |
| --- | --- | --- | --- | --- |
| `MSN` | Lunar Landing Mission Requirements | system | — | 8–10: land safely, abort at any time, support the crew for the planned surface stay, extended missions |
| `LM` | Lunar Module Specification | segment | `MSN` | 15–20: touchdown limits, engine throttle positions, tanks and batteries per configuration, caution and warning, the low-level sensor |
| `LGC` | Guidance Computer Software Requirements (Luminary) | software | `LM` | 30–35: programs and their transitions, DSKY verbs/nouns and OPR ERR, ignition on PRO, landing radar incorporation, P66 ROD, P65, abort, 1202 handling, the erasable load check, propellant remaining and its caution |

IDs look like `LGC-GDN-004`, with subsystems `DSKY`, `GDN`, `NAV`, `ALM`,
`CFG`, `PRP`, `ABT`, `EPS`, `ECS`. Attributes stay as today:
`subsystem`, `verification` (Test / Analysis / Inspection /
Demonstration), and `last-modified-by` (not hashed).

A few requirements are verified by Analysis or Inspection and have no
scripts, on purpose, so that rollup has requirements without scripts to
show.

`history.json` tells a story in four runs. The new history must use
**every edit kind the current one uses** (old/new text, remove, move,
append, baselines, sets), because the requirement tests depend on them.
List those kinds before writing it.

1. **2026-09-01 Release 1, H missions.** `MSN`, `LM`, `LGC` at baseline
   1.0, set "Release 1". Standard missions only.
2. **2026-09-02.** Nothing changed (the import logs nothing).
3. **2026-09-15.** Edits: the P66 ROD increment is reworded (scripts on
   it become suspect, then still pass); one `LGC` requirement moves
   between files; one is removed.
4. **2026-10-01 Release 2, J missions.** Appends the extended-mission
   requirements (`MSN` extended stay; `LM` extended tanks and batteries;
   `LGC-CFG-*` erasable load and the configuration check; `LGC-PRP-002`
   propellant remaining against the configured load). Baselines 2.0, set
   "Release 2".

This is also the story the demo tells: the extended-mission requirements
arrive in Release 2, the scripts that cover them use the `:extended`
variation, and `LUM131` fails them.

## The example scripts

`examples/apollo/rvts/core.rst` declares `(uut :lm)`,
`(environments :sim :lms)`, the connectors, the numbers from the
requirements, and the shared helpers:

```clojure
(defn lm-ready? [mission start]
  (and (= (Read lgc.config.mission) mission)
       (.at_start lm start)))

(defn boot [mission start]
  (StartLM {:mission mission :start start}))
```

Variation scripts all use one precondition shape, so warm scheduling
reuses a booted LM across runs of the same variation:

```clojure
(variations "mission start"
  ["standard from PDI"       [:standard :pdi]
   "standard from high gate" [:standard :high-gate]
   "extended from PDI"       [:extended :pdi]
   "extended from high gate" [:extended :high-gate]])

(Precondition "LM booted for the variation's mission, at its start point"
  (lm-ready? mission start)
  :heal "Boot the LM for the variation"
  (boot mission start))
```

### Scripts

The rule (written into the README and `core.rst`): cases that can run one
after another on the same LM are **table rows**; cases that need their
own boot (another mission, another start point, an abort that ends the
flight) are **variations**.

| Script | Tests | Shows | `LUM099` | `LUM131` | `LUM210` |
| --- | --- | --- | --- | --- | --- |
| `DSKY/tc_dsky_001` lamp test (V35) | DSKY | `:table:` rows over the lights, connector groups | pass | pass | pass |
| `DSKY/tc_dsky_002` operator error | DSKY | table of bad entries, OPR ERR, RSET | pass | pass | pass |
| `DSKY/tc_dsky_003` program change (V37) | DSKY | table of allowed and refused changes, rules as `defn`s checked against the table first | pass | pass | pass |
| `DSKY/tc_dsky_004` display updates every 2 s | DSKY | `:lms`-only, Wait against the clock | pass | pass | pass |
| `DSKY/tc_dsky_005` late precondition | — | **lint error, refuses to queue (on purpose)** | — | — | — |
| `GDN/tc_gdn_001` ignition only on PRO | GDN | V99 flashing, Verify no thrust, Proceed | pass | pass | pass |
| `GDN/tc_gdn_002` throttle positions | GDN | `mission` variations, a check over the whole trajectory | pass / blocked | pass | pass |
| `GDN/tc_gdn_003` high gate, P63 → P64 | GDN | `mission` variations; the approach angle from a `:variations:` definitions block | pass / blocked | pass | pass |
| `GDN/tc_gdn_004` P66 rate of descent | GDN | start `:low-gate`, `:crew :manual`, table of click cases | pass | pass | pass |
| `GDN/tc_gdn_005` P65 when hands off | GDN | `:crew :hands-off` | pass | pass | pass |
| `GDN/tc_gdn_006` landing radar after V57 | NAV | table: before V57, after, LR failed from the bench | pass | pass | pass |
| `GDN/tc_gdn_007` landing point redesignation | GDN | **TBD flow, incomplete (on purpose)** | incomplete | incomplete | incomplete |
| `LND/tc_lnd_001` landing within touchdown limits | MSN, LM | the 4 `mission start` variations; `AttachTrajectory`; `rvt-variant` prose per mission | pass, extended blocked | pass | pass |
| `LND/tc_lnd_002` hover margin at low gate | LM | `mission` variations; the expected margin from per-variation definitions | pass / blocked | pass | pass |
| `LND/tc_lnd_003` dispersed landings | MSN | `seed` variations 1–5; a queue filter by `index` | pass | pass | pass |
| `ABT/tc_abt_001` abort from any altitude | ABT | variations over abort altitude (12 km, 3 km, 300 m, 30 m); filter `(< abort-alt 1000)` | pass | pass | pass |
| `ABT/tc_abt_002` abort stage (P71) | ABT | MASTER ARM interlock as a table, then staging | pass | pass | pass |
| `ABT/tc_abt_003` ENGINE STOP overrides guidance | ABT | `try-ok?`, `quietly` | pass | pass | pass |
| `ALM/tc_alm_001` 1202 alarms | ALM | `rr-mode` variations (`:lgc`: none; `:auto` with the CDU fault: alarms, restarts, still lands), the Apollo 11 story in the prose | pass | pass | pass |
| `ALM/tc_alm_002` master alarm and caution | ALM, EPS | battery fault from the bench, MASTER ALARM until pushed | pass | pass | pass |
| `ALM/tc_alm_003` propellant remaining and PRPLNT LOW | PRP | `mission` variations | pass / blocked | **standard pass, extended FAIL** | pass |
| `CFG/tc_cfg_001` erasable load against the vehicle | CFG | `load vehicle` variations including the two mismatches → alarm 01520 | pass / blocked | pass | pass |
| `CFG/tc_cfg_002` extended load needs Luminary 1E | CFG | version-aware expectation: `(if (supports-extended? (.version lm)) :accepted :rejected-load)` | pass | pass | pass |
| `SFC/tc_sfc_001` consumables last the planned stay | MSN, ECS, EPS | `mission` variations, start `:surface`, `RunFor` hours; `:sim`-only | pass / blocked | pass | pass |
| `SFC/tc_sfc_002` a standard LM can't do an extended stay | ECS | expects the ECS caution before 75 h | pass | pass | pass |
| `SFC/tc_sfc_003` bus voltage cautions | EPS | table of bus loads with `SetFixedValue`, `ClearFixedValue` | pass | pass | pass |
| `ECS/*` (3 scripts) | ECS | **flows of `(TBD "...")` steps, incomplete (on purpose)** | incomplete | incomplete | incomplete |

"pass / blocked" means: the standard variations pass, and the extended
ones are blocked on `LUM099`, because the heal can't boot an extended
load.

That gives every outcome (pass, fail, blocked, incomplete, refused) for a
reason a tester would recognise, and none of them is a fixture with a
silly name. `examples/apollo/README.rst` carries the table above, as
`test/data/rvts/README.rst` does today.

`(import FOLDER)` is shown by `ABT/core.rst` importing `GDN`'s helpers.
The definitions section and the config table appear in `LND/core.rst`.

## Steps

Each step ends green (`.venv/bin/python -m unittest`, 806 tests at the
start) and is its own commit.

### 1. Inventory the tests that touch the samples

No code. List every test module and test that uses `(uut :demo)`,
`:sim`/`:bench`, the `demo` or `vm` handles, the sample blocks,
`AUTOMATION_DEMO_BUILDS`, `test/data/rvts`, `test/data/doors` or
`test/data/worker.json`, and tag each test:

- **any-UUT**: it needs a UUT, but not this one's behaviour. It moves to
  `lm` with the cheapest boot.
- **behaviour**: it relies on the stub's behaviour (modes, readings,
  faults, version 1.0.0 vs 1.1.0). It maps to an `lm` equivalent
  (a mission or start point, a connector, a bench fault, `LUM099` vs
  `LUM210`).
- **sample-data**: it reads the old scripts or the old DOORS history.
  It is rewritten against the Apollo scripts or history (step 5), or
  against a small inline script if it tests mechanics.

Also check how tests run workers (in-process `Host`/`Worker`,
`LocalServer`, any CLI subprocess in `test_cli` or `central.py`). The
`lm` plugin ships in the package, so a subprocess sees it, but its
state files and build folder must follow the test's temporary
directories. Write the inventory into "Notes as we go".

### 2. The model, on its own

- `plugins/apollo/model/` as laid out above, with
  `test/test_apollo_model.py`:
  - a nominal standard landing and a nominal extended landing from each
    start point: touchdown within 3.05 m/s vertical and 1.22 m/s
    horizontal, in P66 for the nominal crew and P65 hands-off;
  - the timeline from PDI is in the right ballpark (throttle down at
    about 6.5 min, high gate at about 8.5 min, touchdown at about 12 min)
    and is printed, as `apollo11`'s `make test` does;
  - the throttle is never between 60% and 92.5%;
  - 1202 alarms with RR at AUTO plus the CDU fault, none at LGC, and the
    vehicle still lands;
  - aborts at 12 km, 3 km, 300 m and 30 m all climb;
  - surface stay: standard runs out between 33 h and 75 h, extended
    lasts past 75 h;
  - the `LUM131` flag: prop percent reads about 106% at PDI with an
    extended load, and 100% with the flag off;
  - determinism: the same seed gives the same trajectory;
  - speed: one PDI-to-touchdown flight in under 1 s.
- Tune the guidance targets, crew timing and consumption rates here, and
  write the chosen figures into `missions.py` with the reason for each.
  Lessons from `~/Work/apollo11/docs/model.md` apply: the crew watches
  the held rate and clicks once, then waits; landing radar incorporation
  must happen before high gate or the landing misses.

### 3. The plugin, replacing the sample environments

- `uut.py`, `environments.py`, `handle.py`, `connectors.py`, `blocks.py`,
  `plot.py`, and `documents.py` (the `attached-files` directive, moved).
- `sim` and `lms` come from `plugins/apollo` from now on, so in this same
  step `plugins/sample` loses its `Sim` and `Bench` environments (two
  plugins can't both define `sim`). Tests that use `:bench` switch to
  `:lms`. Both environments give the wall clock when `lm` isn't under
  test, so the remaining `demo` tests still pass until step 6.
- Start points: fly from PDI and cache them, keyed by rope digest,
  mission and model version.
- `lms` pacing: catch-up on access, plus the clock without a step.
- `test/test_apollo_plugin.py`:
  - versions and digests, `report_versions` without uploaded builds,
    and a local build round trip;
  - `install`/`start`/`installed_version`;
  - boot accepted and rejected;
  - connectors read, set and fixed, and `children()` for completion in
    the editor and LSP;
  - each block's `execute`, `check_syntax` and `as_rst`;
  - an `lms` clock that advances with a fake wall clock.

### 4. Requirements

- `examples/apollo/doors/specs/{MSN,LM,LGC}/` and `history.json`, as
  above.
- Each `LGC` requirement says one testable thing with numbers that match
  `missions.py` and the model.
- `examples/apollo/README.rst`: the requirements table, with which
  scripts cover each requirement and which have none on purpose.

### 5. The scripts

- Write `examples/apollo/rvts/` as tabled above, `core.rst` files first.
- Rewrite `test/test_example_set.py` against them. `EXPECTED` becomes
  keyed by version: `(script, environment, variation) -> outcome` for
  each of `LUM099`, `LUM131`, `LUM210`. Run `sim` only in the unit test
  (`lms` pacing would slow it down) and check the `:lms` scripts are
  planned but not run.
- Check the rollup per requirement for `LUM210` (green except the TBD
  ones) and for `LUM131` (the PRP requirement red).
- Budget: the whole set on one version in `sim` in under 60 s.

### 6. Move every test onto `lm`, and delete the old samples

Work through the inventory from step 1, module by module:

- **any-UUT** tests: `(uut :lm)`, `(environments :sim)`, boot with
  `:start :surface` or test through the DSKY.
- **behaviour** tests: their `lm` equivalents. For example, version
  selection (was `demo` 1.0.0 vs 1.1.0) becomes `LUM099` vs `LUM210`
  with an extended load. A mode-based precondition with a heal (was
  `StartDemo` with a mode) becomes `StartLM` with a mission. A fault
  (was `.fault demo`) becomes a bench battery fault. Snapshots become
  `AttachTrajectory`, and table rendering moves to `:table:` blocks.
- `test_builds` and the client tests: `AUTOMATION_LM_BUILDS` and
  `luminary.json` builds.
- **sample-data** tests (`test_export`, `test_report_pages`,
  `test_jobs`, the `test_requirement_*` modules, `test_demo`): use the
  Apollo scripts and history. The requirement tests depend on specific
  edits in today's history, so check each assertion against the new
  history and, where an edit kind is missing, add it to the new history
  rather than keep the old one.

Then delete `plugins/vm/`, `plugins/sample/`, `test/data/rvts/`,
`test/data/doors/`, `test/data/worker.json`, `test/data/load_sample.py`
and `test/data/make_workspaces.py` (the last two move into `demo.py`
if anything still needs them). These must all come back empty:

```
grep -rn -E '\bdemo\b|\bvm\b|:bench|VMC|VM-|tc_bra|tc_fue|SRS-VM|StartDemo|SnapshotDemo|Table-Driven|SetupSimulation|AUTOMATION_DEMO_BUILDS' automationv3 test
```

The only exceptions are the `automation-v3 demo` command itself
(`cli.py`, `demo.py`, `test_demo.py`) and `lsp/server.py`,
`lsp/service.py`, `language.py`, `verify.py`, `web/*.py` and
`services/*.py`. Those mention the samples in docstrings or examples:
read each one and update it to the Apollo example.

### 7. The demo command and packaging

- `demo.py`: `SAMPLES` becomes `automationv3/examples/apollo` (found
  with `importlib.resources`, not relative to a checkout), the
  environments are `("sim", "lms")`, and the worker config comes from
  `examples/apollo/worker.json` with each environment's workdir filled
  in. `AUTOMATION_LM_BUILDS` is set to a folder in the demo directory,
  with one ready-made local build (`LUM131` with the defect flag off)
  so the local-client upload story can be shown.
- `check_source()` no longer requires a checkout. Docs are built only
  when a checkout's `docs/` is there.
- Package data: make sure `examples/apollo/**` and
  `plugins/apollo/snippets/**` are in a built wheel. Build one
  (`python -m build` or `pip wheel .`), install it into a scratch venv,
  and run `automation-v3 demo --no-docs` from it.
- Run `automation-v3 demo` by hand and walk the story: Requirements →
  queue Release 2 on `LUM131` → the extended PRP failure → rerun on
  `LUM210` → green; a scratch run of the local build; one `lms` run
  watched live.

### 8. Documentation

- `README.md` (the quick start, the example table, `--uut lm=...` in
  examples), `docs/overview/getting-started.rst`, `concepts.rst`,
  `docs/scripts/*` (first-script, preconditions, planning, steps,
  composing, definitions, documenting), `docs/blocks/*` (attachments,
  rendering, uuts-and-environments, writing-blocks), `docs/operating/*`
  (reports, requirements, local-client, editor, accounts, deployment),
  `docs/reference/*` (cli, language, requirements, requirements-export).
- The examples in the docs come from the Apollo set, ideally quoted from
  the real files (`literalinclude` with `:lines:` or `:start-after:`) so
  they can't drift.
- `uuts-and-environments.rst` uses `lm` as its worked example:
  versions vs variations (the rope vs the erasable load) is exactly the
  distinction that page needs to explain.
- Run the step 6 grep over `docs/` and `README.md` too.
- Build the docs and look at every changed page.

## What exists at the end

- `automationv3/plugins/core` and `automationv3/plugins/apollo`, and
  nothing else in `plugins/`.
- `automationv3/examples/apollo/`: scripts, specs and history,
  `worker.json`, and a README with the outcome matrix. Shipped in the
  wheel.
- `test/`: the framework's unit tests, all on `lm`, plus the model and
  plugin tests. No other UUT, environment, sample script or requirement
  set.
- `automation-v3 demo` builds from the installed package.

## Risks

| Risk | Mitigation |
| --- | --- |
| Guidance tuning eats time (it did in `apollo11`) | Keep it 2-D and the law simple. Accept "lands within limits from every start point in both missions" as done, not a match to the flight's timeline. Step 2 comes before anything depends on it. |
| Moving the unit tests onto `lm` is the biggest step | The inventory in step 1 sizes it first. Tests that need "some UUT" get the cheapest boot. Step 6 can be split into several commits, one per group of modules. |
| The requirement tests assert on specific edits of today's history | Map each assertion to the new history in step 6. The new history adds whatever edit kind is missing. |
| Tests become slow because `lm` is heavier than the stub | Cheap boots (`:surface`, cached start points), no full flights outside `test_apollo_model` and `test_example_set`. Compare the suite's time (93 s today) at the end of step 6. |
| JSON load/save per call is slow during long Waits | Measure in step 3. If it matters, keep the state in memory per (environment, process) and write it through on each change. |
| Package data missing from the wheel | Step 7 installs the wheel into a scratch venv and runs the demo from it. |
| Seeded defect mistaken for history | The docstring, the README and the `LUM131` version description say the defect is invented. |

## Notes as we go

- 2026-11-17: answered: environments `sim` and `lms`; the example ships
  inside the package; `source-tree` fast-forwarded into master, branch
  `apollo-samples` off it; every existing sample and UUT goes, and the
  framework's unit tests move onto `lm` (no test-only stub).

### Step 1: the inventory (2026-11-17)

No test starts a worker in a subprocess (`test_mirror` runs git,
`test_plugins` runs a fresh interpreter to load plugins), so the `lm`
plugin is seen everywhere it is needed.

- **any-UUT / behaviour** (inline scripts with `(uut :demo)`,
  `:sim`/`:bench`, the `demo` handle, the sample blocks):
  `test_jobs` (85 mentions: versions 1.0.0/1.1.0, install/kept,
  `StartDemo`/`SnapshotDemo`, `(.mode demo)`, a `vm` version in a page),
  `test_builds` (local builds, `AUTOMATION_DEMO_BUILDS`), `test_lsp`
  (the `demo` handle in completion), `test_cli`, `test_analysis`,
  `test_placeholders`, `test_plugins`, `test_cards`, `test_editor`,
  `test_workspace_handler`, `test_source`, `test_worker_tokens`,
  `test_client_web`, `test_blocks`, `test_variation_scopes`,
  `test_statements`, `test_compose`, `test_api`, `test_filetree`,
  `central.py`.
- **vm**: `test_refs` (23 mentions) tests connectors on the
  `VehicleManager` directly; it moves to the `lm` connectors.
- **sample-data**: `test_example_set`, `test_demo`, `test_export`,
  `test_report_pages` (the BRA scripts), `test_requirement_store`,
  `test_requirement_flat`, `test_requirement_documents`,
  `test_requirement_features`, `test_docutils_facts` (the DOORS sample
  or the sample scripts), `test_mirror` (2 mentions).

### Step 2: the model (2026-11-17)

- The quadratic law with a fixed time to high gate was unworkable: it
  asked for more than full throttle at PDI, and then more than 60%
  after throttle-down, and crashed. A time-to-go search for full
  throttle was unstable (the throttle a plan needs is U-shaped in its
  time). What works: downrange, the constant deceleration that reaches
  the gate's speed at the gate; time to go from that; vertically, the
  quadratic law in that time to go. Ahead of plan, it asks for less,
  so throttle-down comes on its own. P64 uses the same law to low gate.
- Once throttled down, P63 and P64 never go back to full throttle
  (only P70 does).
- PDI ranges: 500 km (standard), 540 km (extended). The extended LM got
  9,000 kg of propellant and a 2,500 kg dry descent stage (16,400 kg at
  PDI), so a nominal landing ends with about 9% left in both missions
  and lights no caution.
- Timeline (seed 0): standard throttle-down 328 s, P64 562 s, touchdown
  730 s at 2.4 m/s, 24 m from the site, 751 kg left; extended 364 s,
  630 s, 781 s, 828 kg left. One flight is about 0.1 s.
- The nominal crew clicks up to three times per look in P66, and stops
  re-selecting V16 N68 after three 1202s (17 alarms otherwise).

### Step 3: the plugin (2026-11-17)

- The `vm` plugin and its VM scripts went in this step rather than
  step 6: it registers the `connector` function and `Read`/`RunFor`
  blocks that the `apollo` plugin now owns. The `SRS-VM` spec stays
  until the DOORS history is replaced, because the history edits it.
  `test_refs`, `test_lsp` (ref paths) and `test_plugins` moved to the
  `lm` connectors for good; the VM example tests in `test_placeholders`
  and `test_example_set` went with the VM scripts.
- `sample` lost `Sim`, `Bench` and the `attached-files` directive (now
  `apollo`'s). Old tests and scripts using `bench` now use `lms`,
  until step 6 rewrites them.
- Blocks: no `Telemetry` (connectors cover it); added
  `PushMasterAlarm`. `ClickROD` fails when the switch does nothing.
  Fixed inputs are applied after the crew acts, so they hold.
- Handle extras that scripts will use: `ready`, `booted`,
  `supports_extended`, `throttles`, `events`, `touchdown`.

### Step 4 and 5: requirements and scripts (2026-11-17)

- 40 requirements in Release 1 (MSN, LM, LGC), 6 more appended in
  Release 2. The history keeps every edit kind the old one had: text,
  attribute, formatting only, append, remove, move, a `:satisfies:` to a
  requirement that doesn't exist (`LM-NAV-099`), text outside the
  requirements, baselines and sets (Release 1, 1.1, 2).
- 28 scripts. Differences from the plan: no hover-margin script (it
  tested nothing the requirements say); `tc_lnd_002` is the dispersed
  landings; `CFG/tc_cfg_002` asks for an extended load and fails on
  LUM099 (a version-aware expectation would have hidden the gap in the
  rollup); `tc_alm_003` also covers the DES QTY sensor (`LM-PRP-003`).
- Low gate comes at about 8.5 m/s and 200 m rather than the 5 m/s and
  150 m targeted: the gate-to-gate law arrives fast. The nominal crew
  copes; `tc_gdn_004` clicks in fives.
- `test_example_set`: the whole set on LUM210 by requirement in sim
  (15 s), then LUM131 and LUM099 on the scripts where they differ. The
  queue form, once `configured`, needs every variation ticked.
- `lm.lgc.rate-command` connector added; `.throttles` takes the event
  to start from.

### Step 6: every test on `lm`, the old samples gone (2026-11-17)

- `plugins/sample`, `test/data` (rvts, doors, worker.json,
  load_sample.py, make_workspaces.py) are deleted. Repository helpers
  moved to `test/gitutil.py`; `test/examples.py` says where the Apollo
  example is.
- Mappings used: demo 1.0.0 → LUM099, 1.1.0 → LUM210 (newest);
  `(.mode demo)` → `(.mission lm)`; `StartDemo`/`SnapshotDemo` →
  `StartLM`/`AttachTrajectory`; the old pass + version-fail pair
  (tc_bra_00004, tc_bra_00003) → `ALM/tc_alm_001` (passes all variations
  on every version) and `CFG/tc_cfg_002` (fails on LUM099).
  `SetupSimulation` became a `Configure` block inside `test_compose`.
- `demo.py` moved onto the packaged example in this step (the store test
  reads the history through it), with the build repository
  (`builds/`, `AUTOMATION_LM_BUILDS`, also set by `existing()` for the
  reloader) and a ready local build of LUM131 with its defect fixed.
- The trace check found LGC requirements satisfying MSN ones directly.
  LM got `LM-GNC-001..003` and `LM-ABT-003`, and every LGC requirement
  traces to LM now; the only trace issue left is the deliberate
  `LM-NAV-099`.
- Docstrings, comments, placeholders and inline fixtures that spoke of
  the VM, brakes or the demo UUT now use the lunar module.
- 853 tests, 90 s.
