import unittest

from night_power import plan_lunar_night


class NightPowerTests(unittest.TestCase):
    def test_equator_has_a_half_month_night_and_solar_only_fails(self):
        plan = plan_lunar_night(0, night_low_c=-170)
        self.assertGreater(plan["night_days"], 14)
        self.assertLess(plan["night_days"], 16)
        solar_only = plan["options"][0]
        self.assertEqual(solar_only["name"], "Solar only")
        self.assertFalse(solar_only["works"])
        self.assertTrue(plan["options"][1]["works"])
        self.assertIn("battery", plan["best"].lower())

    def test_high_latitude_flat_array_cannot_refill_and_tilt_can(self):
        plan = plan_lunar_night(75, night_low_c=-180)
        self.assertFalse(plan["options"][1]["works"])
        self.assertTrue(plan["options"][2]["works"])
        self.assertIn("Tilt", plan["best"])
        self.assertIn("smooth sphere", plan["cannot"][3])

    def test_steady_source_cannot_heat_a_habitat_alone(self):
        plan = plan_lunar_night(20, night_low_c=-150, goes_class="M2.0")
        steady = plan["options"][3]
        self.assertIn("cannot run a 600 W", " ".join(plan["cannot"]))
        self.assertIn("comparison", steady["line"])
        self.assertLess(plan["peak_flat_w"], plan_lunar_night(20, goes_class="B1")["peak_flat_w"])


if __name__ == "__main__":
    unittest.main()
