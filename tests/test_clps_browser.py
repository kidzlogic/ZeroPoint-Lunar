import unittest
from datetime import datetime, timedelta, timezone

from clps_browser import (
    MOON_EQUATOR_TILT_DEG,
    body_points,
    compare_sites,
    horizon_for,
    julian_day,
    observe,
)


class ClpsBrowserTests(unittest.TestCase):
    def test_j2000_noon_is_the_standard_julian_day(self):
        moment = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
        self.assertAlmostEqual(julian_day(moment), 2451545.0, places=5)

    def test_subsolar_latitude_stays_inside_the_lunar_tilt(self):
        start = datetime(2006, 1, 1, tzinfo=timezone.utc)
        peak = 0.0
        for month in range(19 * 12):
            points = body_points(start + timedelta(days=30 * month))
            peak = max(peak, abs(points["sun_lat"]))
            self.assertLess(abs(points["earth_lat"]), 10.0)
            self.assertLess(abs(points["earth_lon"]), 12.0)
        self.assertGreater(peak, 1.35)
        self.assertLess(peak, MOON_EQUATOR_TILT_DEG + 0.15)

    def test_the_sun_walks_once_around_the_moon_in_a_synodic_month(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = body_points(start)["sun_lon"]
        later = body_points(start + timedelta(days=29))["sun_lon"]
        turned = (later - first) % 360.0
        self.assertTrue(turned < 30.0 or turned > 330.0)

    def test_the_south_pole_sees_the_sun_at_the_subsolar_latitude(self):
        points = body_points(datetime(2026, 11, 15, tzinfo=timezone.utc))
        elevation, _azimuth = observe(-90.0, 0.0, points["sun_lat"], points["sun_lon"])
        self.assertAlmostEqual(elevation, -points["sun_lat"], places=4)

    def test_earth_is_overhead_on_the_near_side_and_on_the_limb_at_90_degrees(self):
        points = body_points(datetime(2026, 6, 1, tzinfo=timezone.utc))
        overhead, _ = observe(0.0, 0.0, points["earth_lat"], points["earth_lon"])
        self.assertGreater(overhead, 75.0)
        limb_lon = points["earth_lon"] + 90.0
        limb, _ = observe(0.0, limb_lon, points["earth_lat"], points["earth_lon"])
        self.assertAlmostEqual(limb, 0.0, delta=2.0)

    def test_lola_horizon_is_a_real_ridge_not_a_flat_line(self):
        mask, source = horizon_for(-89.5, 0.0)
        self.assertEqual(source, "lola")
        self.assertEqual(len(mask), 36)
        self.assertTrue(all(-20.0 < value < 40.0 for value in mask))
        self.assertGreater(max(mask) - min(mask), 0.3)

    def test_compare_ranks_a_fortnight_with_both_windows(self):
        report = compare_sites(datetime(2026, 11, 15, tzinfo=timezone.utc), days=7, scan=False)
        self.assertEqual(len(report["sites"]), 7)
        scores = [site["score"] for site in report["sites"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        leader = report["sites"][0]
        self.assertGreaterEqual(leader["sun_clear_hours"], 0.0)
        self.assertLessEqual(leader["sun_clear_hours"], leader["window_hours"])
        self.assertLessEqual(leader["comm_hours"], leader["window_hours"])
        self.assertIn("leads", report["headline"])
        self.assertTrue(leader["series"])
        self.assertIn("not a flight clearance", report["limits"].lower())
        faustini = next(site for site in report["sites"] if site["id"] == "faustini")
        self.assertGreater(faustini["ground_km"], -1.0)


if __name__ == "__main__":
    unittest.main()
