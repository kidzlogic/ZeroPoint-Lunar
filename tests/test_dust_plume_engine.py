import unittest

from dust_plume_engine import screen_route_against_plume_corridor


class DustPlumeEngineTests(unittest.TestCase):
    def test_detects_segment_overlap_even_when_route_samples_skip_corridor(self):
        assessment = screen_route_against_plume_corridor(
            route_lat_lon=[[0, -1], [0, 1]],
            source_latitude=0,
            source_longitude=0,
            axis_azimuth_degrees=90,
            downrange_extent_km=50,
            cross_track_half_width_km=2,
            evidence_source="mission plume scenario",
        )

        self.assertTrue(assessment["overlap"])
        self.assertEqual(assessment["route_segments_intersecting_envelope"], 1)
        self.assertEqual(assessment["minimum_route_separation_km"], 0)
        self.assertEqual(
            assessment["envelope"]["polygon_lat_lon"][0],
            assessment["envelope"]["polygon_lat_lon"][-1],
        )
        self.assertIn("user-defined", assessment["model"])
        self.assertIn("does not predict plume generation", " ".join(assessment["limitations"]))

    def test_reports_nearby_route_without_claiming_no_exposure(self):
        assessment = screen_route_against_plume_corridor(
            route_lat_lon=[[0.1, 0.1], [0.1, 0.5]],
            source_latitude=0,
            source_longitude=0,
            axis_azimuth_degrees=90,
            downrange_extent_km=50,
            cross_track_half_width_km=1,
        )

        self.assertFalse(assessment["overlap"])
        self.assertGreater(assessment["minimum_route_separation_km"], 1)
        self.assertIn("not evidence of no dust exposure", assessment["interpretation"])

    def test_handles_routes_across_longitude_wrap(self):
        assessment = screen_route_against_plume_corridor(
            route_lat_lon=[[0, 179.8], [0, -179.8]],
            source_latitude=0,
            source_longitude=179.9,
            axis_azimuth_degrees=90,
            downrange_extent_km=30,
            cross_track_half_width_km=1,
        )

        self.assertTrue(assessment["overlap"])

    def test_rejects_invalid_corridor_dimensions_and_route(self):
        arguments = {
            "route_lat_lon": [[0, 0], [0, 1]],
            "source_latitude": 0,
            "source_longitude": 0,
            "axis_azimuth_degrees": 90,
            "downrange_extent_km": 10,
            "cross_track_half_width_km": 1,
        }
        with self.assertRaisesRegex(ValueError, "cross_track_half_width_km"):
            screen_route_against_plume_corridor(
                **{**arguments, "cross_track_half_width_km": 0}
            )
        with self.assertRaisesRegex(ValueError, "route_lat_lon"):
            screen_route_against_plume_corridor(
                **{**arguments, "route_lat_lon": [[0, 0]]}
            )
        with self.assertRaisesRegex(ValueError, "source_latitude"):
            screen_route_against_plume_corridor(
                **{**arguments, "source_latitude": 10**1000}
            )
