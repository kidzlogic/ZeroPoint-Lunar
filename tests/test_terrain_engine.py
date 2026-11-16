import unittest
from unittest.mock import patch

import numpy as np

from terrain_engine import (
    analyze_nearby_terrain,
    calculate_roughness,
    calculate_slope,
    find_safe_route,
    generate_terrain_payload,
    summarize_path_screen,
)


class TerrainRoutingTests(unittest.TestCase):
    def test_route_avoids_steep_dem_cells(self):
        slopes = np.zeros((10, 10), dtype=float)
        slopes[1:9, 4] = 30

        route = find_safe_route(slopes, (4, 1), (4, 7), 1.0)

        self.assertEqual(route[0], (4, 1))
        self.assertEqual(route[-1], (4, 7))
        self.assertTrue(all(slopes[row, col] <= 18 for row, col in route))

    def test_route_slope_limit_is_configurable_and_reported_in_failure(self):
        slopes = np.full((5, 5), 15.0)
        slopes[0, 0] = 0.0
        slopes[4, 4] = 0.0

        with self.assertRaisesRegex(ValueError, "above 10 degrees"):
            find_safe_route(
                slopes, (0, 0), (4, 4), 1.0, max_slope_degrees=10.0
            )

        route = find_safe_route(
            slopes, (0, 0), (4, 4), 1.0, max_slope_degrees=20.0
        )
        self.assertEqual(route[0], (0, 0))
        self.assertEqual(route[-1], (4, 4))

    def test_route_screen_counts_direct_exceedance_samples_separately(self):
        slopes = np.array([[24.0, 4.0, 0.0], [3.0, 4.0, 5.0]])
        roughness = np.zeros_like(slopes)

        direct = summarize_path_screen(
            [(0, 0), (0, 1), (0, 2)], slopes, roughness, 18.0, 2.0
        )
        selected = summarize_path_screen(
            [(1, 0), (1, 1), (1, 2)], slopes, roughness, 18.0, 2.2
        )

        self.assertEqual(direct["above_slope_limit_samples"], 1)
        self.assertEqual(direct["above_slope_limit_percent"], 33.3)
        self.assertEqual(selected["above_slope_limit_samples"], 0)
        self.assertEqual(selected["distance_km"], 2.2)

    def test_slope_uses_elevation_change_and_grid_spacing(self):
        elevation = np.tile(np.arange(5, dtype=float), (5, 1))

        slopes = calculate_slope(elevation, spacing_km=1.0)

        self.assertTrue(np.allclose(slopes, 45.0))

    def test_roughness_detects_local_relief_without_flagging_a_plane(self):
        plane = np.tile(np.arange(9, dtype=float), (9, 1))
        roughness = calculate_roughness(plane)
        self.assertTrue(np.allclose(roughness[2:-2, 2:-2], 0))

        plane[4, 4] += 1
        roughness = calculate_roughness(plane)
        self.assertGreater(float(roughness[4, 4]), 0)

    def test_nearby_terrain_summary_uses_sampled_dem(self):
        color = np.zeros((181, 360, 3), dtype=np.float32)
        height = np.tile(np.arange(360, dtype=np.float32) * 0.1, (181, 1))
        with patch("terrain_engine.load_moon_data", return_value=(color, height)):
            summary = analyze_nearby_terrain(0, 0)

        self.assertEqual(summary["radius_km"], 10.0)
        self.assertEqual(summary["grid_spacing_km"], 2.0)
        self.assertIn("resolution_note", summary)
        self.assertGreater(summary["max_slope_degrees"], 0)
        self.assertIn("dust_traps", summary)
        self.assertEqual(len(summary["look"]), 121)

    def test_no_route_through_full_steep_barrier(self):
        slopes = np.zeros((5, 5), dtype=float)
        slopes[:, 2] = 30

        with self.assertRaisesRegex(ValueError, "No route"):
            find_safe_route(slopes, (2, 0), (2, 4), 1.0)

    def test_least_risk_preview_routes_around_steep_terrain(self):
        slopes = np.zeros((5, 5), dtype=float)
        slopes[1:4, 2] = 45

        route = find_safe_route(
            slopes, (2, 0), (2, 4), 1.0, allow_over_limit=True
        )

        self.assertEqual(route[0], (2, 0))
        self.assertEqual(route[-1], (2, 4))
        self.assertTrue(any(row != 2 for row, _ in route))

    def test_sun_priority_prefers_high_sun_field_corridor(self):
        slopes = np.zeros((7, 7), dtype=float)
        sun = np.zeros((7, 7), dtype=float)
        sun[1, :] = 1.0
        ice = np.zeros((7, 7), dtype=float)
        ice[5, :] = 1.0

        sun_route = find_safe_route(
            slopes, (3, 0), (3, 6), 1.0,
            path_priority="sun",
            sun_field=sun,
            ice_field=ice,
        )
        ice_route = find_safe_route(
            slopes, (3, 0), (3, 6), 1.0,
            path_priority="ice",
            sun_field=sun,
            ice_field=ice,
        )

        self.assertEqual(sun_route[0], (3, 0))
        self.assertEqual(sun_route[-1], (3, 6))
        self.assertTrue(sum(1 for row, _ in sun_route if row <= 2) >= sum(1 for row, _ in ice_route if row <= 2))
        self.assertTrue(sum(1 for row, _ in ice_route if row >= 4) >= sum(1 for row, _ in sun_route if row >= 4))

    def test_terrain_payload_preserves_lunar_curvature_and_separate_relief(self):
        color = np.full((181, 360, 3), 128, dtype=np.float32)
        height = np.tile(np.arange(360, dtype=np.float32) * 0.001, (181, 1))

        with patch("terrain_engine.load_moon_data", return_value=(color, height)):
            payload = generate_terrain_payload(
                0, 0, 0, 0, 0, 0.01, radius_km=10, grid_size=20,
                max_slope_degrees=12.0,
            )

        vertices = np.asarray(payload["surface"]["vertices"]).reshape(20, 20, 3)
        relief = np.asarray(payload["surface"]["relief"]).reshape(20, 20)
        assessment = payload["route_assessment"]
        self.assertLess(float(relief.min()), 0)
        self.assertGreater(float(relief.max()), 0)
        self.assertLess(float(vertices[0, 0, 2]), float(vertices[10, 10, 2]))
        self.assertEqual(len(payload["route_relief"]), len(payload["route_vertices"]) // 3)
        self.assertEqual(len(payload["route_elevation_km"]), len(payload["route_relief"]))
        self.assertEqual(len(payload["route_slope_degrees"]), len(payload["route_relief"]))
        self.assertGreater(len(payload["area_scan"]), 0)
        self.assertLessEqual(len(payload["area_scan"]), 81)
        self.assertEqual(assessment["slope_limit_degrees"], 12.0)
        self.assertGreater(assessment["direct_line"]["sampled_cells"], 0)
        self.assertGreater(assessment["selected_path"]["sampled_cells"], 0)
        self.assertEqual(assessment["path_type"], "slope-constrained")

    def test_shackleton_is_a_critical_hazard_without_a_safe_route(self):
        color = np.full((181, 360, 3), 128, dtype=np.float32)
        height = np.zeros((181, 360), dtype=np.float32)

        with patch("terrain_engine.load_moon_data", return_value=(color, height)):
            payload = generate_terrain_payload(
                0, 0, 0, 0, 0, 0.1, radius_km=20, grid_size=20,
                destination_is_shackleton=True,
            )

        shackleton = next(item for item in payload["hazards"] if item["risk_level"] == "critical")
        self.assertEqual(shackleton["kind"], "Shackleton provisional hazard")
        self.assertFalse(payload["route_available"])
        self.assertEqual(payload["route"], [])
        self.assertGreater(len(payload["advisory_route"]), 1)
        self.assertEqual(payload["hazard_counts"]["severe"], 1)


if __name__ == "__main__":
    unittest.main()
