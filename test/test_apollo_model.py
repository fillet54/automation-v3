"""The lunar module model on its own: does it fly?

These check the flight, not the plugin: the timeline from PDI, both
missions landing from every start point within the landing gear's
limits, the throttle never between 60% and full throttle, the 1202
alarms, aborts, the surface stays, and the ropes' differences.
"""

import time
import unittest

from automationv3.plugins.apollo.model import lgc as L
from automationv3.plugins.apollo.model import missions as M
from automationv3.plugins.apollo.model import sim
from automationv3.plugins.apollo.model.rope import RELEASES, digest, parse

LUM099, LUM131, LUM210 = (RELEASES[r] for r in ("LUM099", "LUM131", "LUM210"))


def land(rope=LUM210, **config):
    s = sim.boot(rope, config)
    sim.run_until(s, lambda s: s["landed"], 1500)
    return s


def first(s, kind, **detail):
    return next((e["t"] for e in s["events"] if e["kind"] == kind
                 and all(e.get(k) == v for k, v in detail.items())), None)


class TestLanding(unittest.TestCase):
    def test_both_missions_land_from_every_start_point(self):
        for mission in ("standard", "extended"):
            for start in ("pdi", "high-gate", "low-gate"):
                for crew, last in (("nominal", 66), ("hands-off", 65)):
                    with self.subTest(mission=mission, start=start, crew=crew):
                        s = land(mission=mission, start=start, crew=crew)
                        td = s["touchdown"]
                        self.assertFalse(s["crashed"])
                        self.assertLessEqual(abs(td["vz"]), M.TOUCHDOWN_VZ_LIMIT)
                        self.assertLessEqual(abs(td["vx"]), M.TOUCHDOWN_VX_LIMIT)
                        self.assertLess(abs(td["miss"]), 200)
                        programs = [e["program"] for e in s["events"] if e["kind"] == "program"]
                        self.assertEqual(programs[-2:], [last, 68])

    def test_the_timeline_from_pdi(self):
        for mission in ("standard", "extended"):
            s = land(mission=mission)
            down, p64 = first(s, "throttle-down"), first(s, "program", program=64)
            td = s["touchdown"]
            print(f"\n  {mission}: throttle down {down:.0f} s, P64 {p64:.0f} s, "
                  f"touchdown {td['t']:.0f} s at {td['vz']} m/s, {td['miss']} m from the "
                  f"site, {td['propellant']} kg left", end="")
            self.assertTrue(300 <= down <= 400, down)
            self.assertTrue(540 <= p64 <= 660, p64)
            self.assertTrue(660 <= td["t"] <= 840, td["t"])

    def test_a_nominal_landing_lights_no_caution(self):
        for mission in ("standard", "extended"):
            s = land(mission=mission)
            self.assertEqual([e for e in s["events"] if e["kind"] in ("caution", "warning")], [])
            self.assertGreater(L.prop_percent(s), M.PROPELLANT_LOW_PERCENT + 1)

    def test_the_throttle_is_never_between_60_percent_and_full(self):
        for mission in ("standard", "extended"):
            s = land(mission=mission)
            self.assertEqual(s["throttle_band_violations"], 0)
            throttles = {row[5] for row in s["trajectory"]}
            self.assertFalse({t for t in throttles if 60 < t < 92.5})
            self.assertIn(92.5, throttles)

    def test_ignition_waits_for_proceed(self):
        s = sim.boot(LUM210, {"crew": "manual"})
        self.assertTrue(s["lgc"]["flashing"])
        self.assertEqual(s["lgc"]["display"]["verb"], 99)
        sim.advance(s, 30)
        self.assertFalse(s["des_on"])
        L.key(s, "P")
        sim.advance(s, 1)
        self.assertTrue(s["des_on"])

    def test_without_the_landing_radar_the_landing_is_hard(self):
        s = sim.boot(LUM210, {})
        s["bench"]["lr_failed"] = True
        sim.run_until(s, lambda s: s["landed"], 1500)
        self.assertTrue(s["crashed"])

    def test_a_flight_is_repeatable_and_the_seed_adds_noise(self):
        a, b, c = land(seed=4), land(seed=4), land(seed=5)
        self.assertEqual(a["trajectory"], b["trajectory"])
        self.assertNotEqual(a["trajectory"], c["trajectory"])

    def test_a_flight_is_quick(self):
        start = time.perf_counter()
        land(mission="extended")
        self.assertLess(time.perf_counter() - start, 1.0)


class TestAlarms(unittest.TestCase):
    def test_1202_alarms_with_the_rendezvous_radar_counters_and_still_lands(self):
        s = sim.boot(LUM210, {})
        s["panel"]["rr_mode"] = "auto"
        s["bench"]["rr_cdu_fault"] = True
        sim.run_until(s, lambda s: s["landed"], 1500)
        self.assertTrue(2 <= len(s["lgc"]["alarms"]) <= 6, s["lgc"]["alarms"])
        self.assertEqual(set(s["lgc"]["alarms"]), {L.ALARM_EXECUTIVE_OVERFLOW})
        self.assertEqual(s["lgc"]["restarts"], len(s["lgc"]["alarms"]))
        self.assertFalse(s["crashed"])

    def test_no_alarms_with_the_radar_switch_at_lgc(self):
        s = sim.boot(LUM210, {})
        s["bench"]["rr_cdu_fault"] = True
        sim.run_until(s, lambda s: s["landed"], 1500)
        self.assertEqual(s["lgc"]["alarms"], [])

    def test_an_overflow_drops_the_monitor_display(self):
        s = sim.boot(LUM210, {"crew": "manual"})
        s["panel"]["rr_mode"] = "auto"
        s["bench"]["rr_cdu_fault"] = True
        for k in "PV16N68E":
            L.key(s, k)
        self.assertEqual(s["lgc"]["monitor"], 68)
        sim.run_until(s, lambda s: s["lgc"]["alarms"], 60)
        self.assertIsNone(s["lgc"]["monitor"])
        self.assertTrue(s["lgc"]["lights"]["prog"])
        self.assertTrue(s["cwea"]["master_alarm"])


class TestAborts(unittest.TestCase):
    def test_abort_climbs_from_any_altitude(self):
        for altitude in (12_000, 3_000, 300, 30):
            with self.subTest(altitude=altitude):
                s = sim.boot(LUM210, {})
                sim.run_until(s, lambda s: s["lgc"]["ignited"] is not None
                              and s["h"] <= altitude, 1500)
                s["panel"]["abort"] = True
                sim.advance(s, 20)
                self.assertEqual(s["lgc"]["program"], 70)
                self.assertGreater(s["vz"], 0)
                self.assertFalse(s["landed"])

    def test_abort_stage_needs_master_arm(self):
        s = sim.boot(LUM210, {"start": "high-gate"})
        s["panel"]["abort_stage"] = True
        sim.advance(s, 2)
        self.assertFalse(s["staged"])
        s["panel"]["master_arm"] = True
        sim.advance(s, 40)
        self.assertTrue(s["staged"])
        self.assertEqual(s["lgc"]["program"], 71)
        self.assertTrue(s["asc_on"])
        self.assertGreater(s["vz"], 0)

    def test_engine_stop_overrides_guidance(self):
        s = sim.boot(LUM210, {"start": "high-gate"})
        s["panel"]["engine_stop"] = True
        sim.advance(s, 2)
        self.assertFalse(s["des_on"])
        self.assertEqual(s["throttle"], 0.0)
        s["panel"]["engine_stop"] = False
        sim.advance(s, 1)
        self.assertTrue(s["des_on"])


class TestSurface(unittest.TestCase):
    def hours_to(self, mission, light):
        s = sim.boot(LUM210, {"mission": mission, "start": "surface"})
        for hour in range(1, 120):
            sim.advance(s, 3600)
            if light in s["cwea"]["active"]:
                return hour
        return None

    def test_each_mission_supports_its_planned_stay(self):
        for mission in ("standard", "extended"):
            stay = M.MISSIONS[mission]["stay_h"]
            s = sim.boot(LUM210, {"mission": mission, "start": "surface"})
            sim.advance(s, stay * 3600)
            self.assertEqual(s["cwea"]["active"], [], mission)

    def test_a_standard_lm_cannot_do_an_extended_stay(self):
        self.assertLess(self.hours_to("standard", "ecs"), M.MISSIONS["extended"]["stay_h"])

    def test_a_battery_fault_lights_the_caution(self):
        s = sim.boot(LUM210, {"start": "surface"})
        s["bench"]["battery_faults"] = {"2": True}
        sim.advance(s, 1)
        self.assertIn("battery", s["cwea"]["active"])
        self.assertTrue(s["cwea"]["master_alarm"])


class TestRopes(unittest.TestCase):
    def test_lum099_rejects_an_extended_load(self):
        with self.assertRaises(sim.BootRejected):
            sim.boot(LUM099, {"mission": "extended"})
        sim.boot(LUM099, {"mission": "standard"})

    def test_lum131_reads_propellant_against_the_standard_load(self):
        self.assertAlmostEqual(L.noun_values(sim.boot(LUM131, {"mission": "extended"}), 93)[0],
                               109.8)
        self.assertEqual(L.noun_values(sim.boot(LUM210, {"mission": "extended"}), 93)[0], 100.0)
        self.assertEqual(L.noun_values(sim.boot(LUM131, {"mission": "standard"}), 93)[0], 100.0)

    def test_a_load_that_does_not_match_the_vehicle_raises_1520(self):
        s = sim.boot(LUM210, {"mission": "standard", "vehicle": "extended", "crew": "manual"})
        self.assertEqual(s["lgc"]["alarms"], [L.ALARM_LOAD_MISMATCH])
        L.key(s, "P")
        sim.advance(s, 5)
        self.assertFalse(s["des_on"])

    def test_a_rope_parses_and_has_a_stable_digest(self):
        self.assertEqual(digest(LUM210), digest(dict(LUM210)))
        self.assertNotEqual(digest(LUM131), digest(LUM210))
        with self.assertRaises(ValueError):
            parse('{"revision": "X", "flags": {"warp": true}}')


class TestDsky(unittest.TestCase):
    def keyed(self, keys, **config):
        s = sim.boot(LUM210, {"crew": "manual", **config})
        for k in keys:
            L.key(s, k)
        return s

    def test_bad_entries_light_operator_error_and_reset_clears_it(self):
        for keys in ("V99E", "V16N12E", "V5E", "V37E63E", "V37E00E"):
            with self.subTest(keys=keys):
                s = self.keyed(keys)
                self.assertTrue(s["lgc"]["lights"]["opr-err"])
                L.key(s, "R")
                self.assertFalse(s["lgc"]["lights"]["opr-err"])

    def test_lamp_test(self):
        s = self.keyed("V35E")
        self.assertTrue(all(L.displayed_lights(s).values()))
        sim.advance(s, 6)
        self.assertFalse(L.displayed_lights(s)["opr-err"])

    def test_monitor_updates_every_cycle_and_v06_does_not(self):
        s = self.keyed("PV16N68E")
        before = list(s["lgc"]["display"]["r"])
        sim.advance(s, 4)
        self.assertNotEqual(s["lgc"]["display"]["r"], before)
        L.key(s, "V"), L.key(s, "0"), L.key(s, "6"), L.key(s, "N"), L.key(s, "6")
        L.key(s, "8"), L.key(s, "E")
        frozen = list(s["lgc"]["display"]["r"])
        sim.advance(s, 4)
        self.assertEqual(s["lgc"]["display"]["r"], frozen)

    def test_v57_enables_the_landing_radar(self):
        s = self.keyed("P")
        sim.run_until(s, lambda s: s["lr"]["alt_good"], 600)
        error = s["lgc"]["nav"]["h_err"]
        sim.advance(s, 10)
        self.assertEqual(s["lgc"]["nav"]["h_err"], error)
        for k in "V57E":
            L.key(s, k)
        sim.advance(s, 10)
        self.assertLess(abs(s["lgc"]["nav"]["h_err"]), abs(error) / 2)

    def test_rod_clicks_select_p66_and_change_the_rate(self):
        s = sim.boot(LUM210, {"start": "low-gate", "crew": "manual"})
        self.assertTrue(L.click_rod(s, 1))
        self.assertEqual(s["lgc"]["program"], 66)
        rate = s["lgc"]["vz_cmd"]
        L.click_rod(s, 2)
        self.assertAlmostEqual(s["lgc"]["vz_cmd"], rate + 2 * L.FT)
