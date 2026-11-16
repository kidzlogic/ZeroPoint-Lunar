import unittest

from mission_plan import build_mission_plan, earth_elevation_degrees


class MissionPlanTests(unittest.TestCase):
    def test_earth_is_overhead_at_the_near_side_center_and_set_at_the_limb(self):
        self.assertAlmostEqual(earth_elevation_degrees(0, 0), 90.0, places=3)
        self.assertAlmostEqual(earth_elevation_degrees(0, 90), 0.0, places=3)
        self.assertLess(earth_elevation_degrees(0, 120), 0)

    def test_slope_priority_blocks_an_uncleared_path(self):
        plan = build_mission_plan({
            "priority": "slope",
            "asset": "rover",
            "sheltered": "no",
            "slope_limit": 15,
            "distance_km": 10,
            "speed_kmh": 0.5,
            "route_cleared": False,
            "samples": [
                {"lat": 0, "lon": 10, "slope": 8},
                {"lat": 0, "lon": 11, "slope": 22},
            ],
            "sun_up": True,
            "storm_scale": "quiet",
            "goes_class": "B1.0",
            "flare_probability": 0.1,
        })
        self.assertIn("not cleared", plan["decision"])
        self.assertEqual(plan["telemetry"]["samples_over_slope_limit"], 1)
        self.assertGreater(plan["telemetry"]["min_earth_elevation_degrees"], 5)
        self.assertIn("same path", plan["links"]["dust"])

    def test_radio_priority_flags_a_low_earth_angle(self):
        plan = build_mission_plan({
            "priority": "radio",
            "samples": [{"lat": 0, "lon": 89, "slope": 4}],
            "route_cleared": True,
            "distance_km": 4,
            "sun_up": False,
            "storm_scale": "quiet",
        })
        self.assertIn("horizon", plan["decision"])
        self.assertLess(plan["telemetry"]["min_earth_elevation_degrees"], 5)
        self.assertIn("night", plan["links"]["temperature"])

    def test_shelter_answer_changes_the_storm_action(self):
        storm = {
            "priority": "slope",
            "storm_scale": "S2",
            "goes_class": "M2.0",
            "samples": [{"lat": 8.4, "lon": 84.8, "slope": 6}],
            "distance_km": 20,
            "route_cleared": True,
        }
        unsheltered = build_mission_plan({**storm, "sheltered": "no"})
        sheltered = build_mission_plan({**storm, "sheltered": "yes", "asset": "crew"})
        self.assertIn("Do not start", unsheltered["shelter"])
        self.assertIn("Stop and put", sheltered["shelter"])
        self.assertIn("quiet", sheltered["links"]["radiation"])

    def test_flat_sunlit_pad_with_lower_ground_is_a_candidate(self):
        plan = build_mission_plan({
            "priority": "sun",
            "distance_km": 8,
            "speed_kmh": 0.5,
            "route_cleared": True,
            "sun_up": True,
            "storm_scale": "quiet",
            "samples": [
                {"lat": 0, "lon": 10, "slope": 3.0, "elev_km": 1.2},
                {"lat": 0.05, "lon": 10.05, "slope": 16.0, "elev_km": 0.4},
            ],
        })
        self.assertTrue(plan["site"]["candidate"])
        self.assertIn("Candidate pair", plan["site"]["verdict"])
        self.assertIn("battery", plan["links"]["mission"].lower())
        self.assertFalse(plan["power"]["options"][0]["works"])

    def test_steep_pad_is_rejected_even_when_the_sun_is_up(self):
        plan = build_mission_plan({
            "priority": "slope",
            "distance_km": 6,
            "sun_up": True,
            "route_cleared": True,
            "samples": [
                {"lat": 0, "lon": 10, "slope": 11, "elev_km": 1.0},
                {"lat": 0, "lon": 10.1, "slope": 18, "elev_km": 0.4},
            ],
        })
        self.assertFalse(plan["site"]["candidate"])
        self.assertIn("5°", plan["site"]["verdict"])

    def test_photo_fix_resets_slip_and_bad_priority_is_rejected(self):
        plan = build_mission_plan({
            "priority": "sun",
            "photo_fix": True,
            "distance_km": 40,
            "sun_up": True,
            "samples": [{"lat": 0, "lon": 0, "slope": 1}],
        })
        self.assertEqual(plan["telemetry"]["uncertainty_km"], 0.05)
        self.assertIn("crater matching is not running", plan["localization"].lower())
        with self.assertRaises(ValueError):
            build_mission_plan({"priority": "lava-tube"})


if __name__ == "__main__":
    unittest.main()
