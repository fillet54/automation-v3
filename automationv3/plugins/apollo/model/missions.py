"""The two missions the lunar module flies, and where a flight can start

The figures are the model's own, loosely based on the H-mission LMs
(Apollo 11 to 14) and the extended J-mission LMs (Apollo 15 to 17).
They are not flight data. They were chosen so that:

- both vehicles land from powered descent initiation (PDI) with
  propellant to spare, the extended one on a steeper approach;
- each vehicle supports its own planned surface stay with margin, and
  the standard one can't support the extended stay (its oxygen runs
  low first, at about 44 hours).
"""

MODEL_VERSION = "1"

# The Moon
G_MOON = 1.62  # m/s^2
R_MOON = 1_737_400.0  # m
G0 = 9.80665  # m/s^2, for specific impulse

# The descent engine (TRW LMDE): throttleable from 10% to 60%, or the
# fixed full-throttle position. Never in between.
DESCENT_MAX_N = 45_040.0
DESCENT_ISP = 305.0
THROTTLE_MIN = 0.10
THROTTLE_MAX = 0.60
FULL_THROTTLE = 0.925
THROTTLE_RECOVERY = 0.57  # leave full throttle once the command is below this

# The ascent engine, used here only to abort stage
ASCENT_N = 15_600.0
ASCENT_ISP = 311.0

# Sensors
LOW_LEVEL_FRACTION = 0.056  # the descent tanks' low-level point sensor
LR_ALTITUDE_GOOD_M = 12_000.0
LR_VELOCITY_GOOD_M = 7_500.0
CONTACT_PROBE_M = 1.7

# Touchdown limits of the landing gear
TOUCHDOWN_VZ_LIMIT = 3.05
TOUCHDOWN_VX_LIMIT = 1.22

# The LGC's PROPELLANT LOW caution, in percent of the loaded propellant
PROPELLANT_LOW_PERCENT = 6.0

# Electrical power: battery capacity, bus loads, and how the bus voltage
# falls with load and with the batteries' state of charge
BATTERY_AH = 415.0
BUS_NO_LOAD_V = 32.0
BUS_V_PER_A = 0.03
BUS_V_EMPTY_DROP = 4.0
BUS_LOW_V = 26.5  # BATTERY caution below this
BUS_MIN_V = 24.0  # WARNING below this: too low for the equipment
LOAD_FLYING_A = 60.0
LOAD_SURFACE_A = 25.0

# Environmental control: use per hour
O2_FLYING_KG_H = 0.6
O2_SURFACE_KG_H = 0.45
WATER_FLYING_KG_H = 5.0
WATER_SURFACE_KG_H = 3.0
ECS_LOW_FRACTION = 0.10  # ECS caution below this share of either

# The vehicles. Masses in kg at PDI.
VEHICLES = {
    "standard": {
        "descent_dry": 2_200.0,
        "descent_propellant": 8_200.0,
        "ascent_wet": 4_700.0,
        "ascent_propellant": 2_350.0,
        "batteries": 4,
        "o2": 22.0,
        "water": 150.0,
    },
    "extended": {
        "descent_dry": 2_500.0,
        "descent_propellant": 9_000.0,
        "ascent_wet": 4_900.0,
        "ascent_propellant": 2_400.0,
        "batteries": 5,
        "o2": 44.0,
        "water": 300.0,
    },
}

# What the erasable load tells the LGC about each mission: the
# propellant it expects at PDI, the planned stay, and the descent
# targets. Positions are relative to the landing site (x downrange,
# negative before it; h altitude), velocities in m/s.
#
# PDI is placed so that braking starts at full throttle with a little to
# spare and throttles down at five to six minutes. With these figures a
# nominal landing comes at about 12 minutes from PDI, with about 9% of
# the propellant left, in both missions.
MISSIONS = {
    "standard": {
        "propellant": 8_200.0,
        "stay_h": 33.0,
        "approach_deg": 16.0,
        "pdi": {"x": -500_000.0, "h": 15_000.0, "vx": 1_690.0, "vz": 0.0},
        "high_gate": {"x": -7_900.0, "h": 2_300.0, "vx": 145.0, "vz": -40.0},
        "low_gate": {"x": -320.0, "h": 150.0, "vx": 18.0, "vz": -5.0},
    },
    "extended": {
        "propellant": 9_000.0,
        "stay_h": 75.0,
        "approach_deg": 25.0,
        "pdi": {"x": -540_000.0, "h": 15_000.0, "vx": 1_690.0, "vz": 0.0},
        "high_gate": {"x": -5_000.0, "h": 2_300.0, "vx": 100.0, "vz": -45.0},
        "low_gate": {"x": -320.0, "h": 150.0, "vx": 18.0, "vz": -5.0},
    },
}

START_POINTS = ("pdi", "high-gate", "low-gate", "surface")
CREWS = ("nominal", "hands-off", "manual")

# Where the flight is when the clock starts: mission elapsed time at
# PDI (Apollo 11's, 102:33:05)
MET_AT_PDI = 102 * 3600 + 33 * 60 + 5


def pdi_mass(vehicle):
    v = VEHICLES[vehicle]
    return v["descent_dry"] + v["descent_propellant"] + v["ascent_wet"]
