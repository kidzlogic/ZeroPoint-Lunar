import unittest
from datetime import timedelta

from space_weather import (
    NEW_MOON,
    SYNODIC_DAYS,
    assess_flare_region,
    build_environment,
    feature_score,
    latest_proton_flux,
    protection_steps,
    reflected_irradiance,
    surface_temperature,
)


class SpaceWeatherTests(unittest.TestCase):
    def test_complex_sunspot_scores_higher_than_a_quiet_region(self):
        complex_region = feature_score("F", "K", "C", 2, 3, 2)
        quiet_region = feature_score("H", "X", "X", 1, 2, 1)
        self.assertGreater(complex_region, 0.7)
        self.assertLess(quiet_region, 0.2)

    def test_flare_assessment_names_the_region_and_limits_the_steps(self):
        outlook = assess_flare_region({
            "zurich_class": "F",
            "spot_size": "K",
            "distribution": "C",
            "activity": 2,
            "evolution": 3,
            "prev_flare": 2,
            "sheltered": "yes",
            "asset": "both",
        })
        self.assertEqual(outlook["region_code"], "Fkc")
        self.assertLessEqual(len(outlook["protection"]), 4)
        self.assertIn("not NOAA", outlook["caveat"])
        self.assertTrue(any("cannot be stopped" in step for step in outlook["protection"]))

    def test_bad_sunspot_code_is_rejected(self):
        with self.assertRaises(ValueError):
            assess_flare_region({"zurich_class": "Z", "spot_size": "K", "distribution": "C"})

    def test_full_moon_is_brighter_than_new_moon_at_earth(self):
        new_moon = reflected_irradiance(NEW_MOON)
        full_moon = reflected_irradiance(NEW_MOON + timedelta(days=SYNODIC_DAYS / 2))
        self.assertLess(new_moon["phase_percent"], 1)
        self.assertGreater(full_moon["phase_percent"], 99)
        self.assertGreater(full_moon["illuminance_lux"], new_moon["illuminance_lux"])

    def test_subsolar_equator_is_hot_and_the_opposite_longitude_is_cold(self):
        full_moon = NEW_MOON + timedelta(days=SYNODIC_DAYS / 2)
        noon = surface_temperature(0, 0, full_moon)
        midnight = surface_temperature(0, 180, full_moon)
        self.assertTrue(noon["sun_up"])
        self.assertGreater(noon["celsius"], 80)
        self.assertFalse(midnight["sun_up"])
        self.assertLess(midnight["celsius"], -100)
        self.assertGreater(noon["day_high_c"], noon["night_low_c"])

    def test_proton_parser_keeps_the_latest_ten_mev_channel(self):
        latest = latest_proton_flux([
            {"time_tag": "2026-11-14T00:00:00Z", "energy": ">=10 MeV", "flux": 1.5, "satellite": 18},
            {"time_tag": "2026-11-14T01:00:00Z", "energy": ">=100 MeV", "flux": 9000, "satellite": 18},
            {"time_tag": "2026-11-14T02:00:00Z", "energy": ">=10 MeV", "flux": 25, "satellite": 18},
            {"time_tag": "2026-11-14T03:00:00Z", "energy": ">=10 MeV", "flux": "bad"},
        ])
        self.assertEqual(latest["flux_pfu"], 25)
        self.assertEqual(latest["storm_scale"], "S1")

    def test_environment_keeps_the_published_baseline_when_protons_fail(self):
        report = build_environment(0, 0, when=NEW_MOON, proton_error="offline")
        self.assertFalse(report["surface_radiation"]["live_lunar_sensor"])
        self.assertEqual(report["surface_radiation"]["baseline_gcr_usv_hr"], 57.0)
        self.assertIsNone(report["surface_radiation"]["protons"])
        self.assertIn("offline", report["surface_radiation"]["proton_error"])

    def test_quiet_protection_does_not_invent_a_storm(self):
        steps = protection_steps(0.1, "B2.0", "quiet", "no", "rover", temperature_c=10)
        self.assertEqual(len(steps), 1)
        self.assertIn("No storm step", steps[0])


if __name__ == "__main__":
    unittest.main()
