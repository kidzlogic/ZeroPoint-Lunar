import unittest

from landing_sites import rank_sites


class LandingRankTests(unittest.TestCase):
    def setUp(self):
        self.metrics = [
            {"name": "Steep pole", "lat": -89.0, "lon": 0.0, "band": "pole",
             "flat": 20, "sun": 80, "earth_score": 10, "slope": 20, "earth": 1, "peak_w": 1800, "night_days": 14.8},
            {"name": "Flat mare", "lat": 8.0, "lon": 80.0, "band": "equator",
             "flat": 90, "sun": 70, "earth_score": 40, "slope": 3, "earth": 8, "peak_w": 1600, "night_days": 14.8},
        ]

    def test_cargo_to_the_equator_picks_the_flat_mare(self):
        ranked = rank_sites(self.metrics, "equator", "cargo", "flat")
        self.assertEqual(ranked[0]["name"], "Flat mare")
        self.assertEqual(len(ranked), 1)

    def test_crew_at_the_pole_stays_on_a_pole_site(self):
        ranked = rank_sites(self.metrics, "pole", "crew", "earth")
        self.assertEqual(ranked[0]["band"], "pole")

    def test_a_bad_rocket_is_rejected(self):
        with self.assertRaises(ValueError):
            rank_sites(self.metrics, "anywhere", "starship", "flat")


if __name__ == "__main__":
    unittest.main()
