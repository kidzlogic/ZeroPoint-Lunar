import json
import io
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from lunar_web_app import (
    DEFAULTS,
    _extract_exif_location,
    _filter_reference_links,
    _load_reference_links,
    app,
)


class TerrainApiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_traverses_over_100_km_are_sent_for_terrain_generation(self):
        with patch("lunar_web_app.generate_terrain_payload", return_value={"ok": True}) as generate:
            response = self.client.get(
                "/api/terrain?start_lat=0&start_lon=0&dest_lat=0&dest_lon=4"
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreater(generate.call_args.args[6], 60)
        self.assertGreater(generate.call_args.kwargs["grid_size"], 160)
        self.assertGreater(response.get_json()["straight_line_distance_km"], 100)

    def test_planning_slope_and_speed_are_validated_and_sent_to_terrain_engine(self):
        with patch(
            "lunar_web_app.generate_terrain_payload",
            return_value={"route_assessment": {"path_type": "slope-constrained"}},
        ) as generate:
            response = self.client.get(
                "/api/terrain?start_lat=0&start_lon=0&dest_lat=0&dest_lon=1"
                "&max_slope_degrees=12&planning_speed_kmh=0.8"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.kwargs["max_slope_degrees"], 12)
        self.assertEqual(response.get_json()["max_slope_degrees"], 12)
        self.assertEqual(response.get_json()["planning_speed_kmh"], 0.8)

        with patch("lunar_web_app.generate_terrain_payload") as generate:
            invalid = self.client.get(
                "/api/terrain?start_lat=0&start_lon=0&dest_lat=0&dest_lon=1"
                "&max_slope_degrees=31"
            )

        self.assertEqual(invalid.status_code, 400)
        generate.assert_not_called()

    def test_path_basemap_uses_highest_supported_moon_trek_resolution(self):
        with patch("lunar_web_app.moon_trek_patch", return_value=(b"map", {})) as render:
            response = self.client.get("/api/path-basemap.jpg?lat=-89.8&lon=0&radius=24")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(render.call_args.args[3], 900)

    def test_solar_xray_api_filters_data_and_reports_measured_flare_classes(self):
        readings = [
            {
                "time_tag": "2026-11-14T01:00:00Z",
                "satellite": 18,
                "flux": 2.5e-5,
                "energy": "0.1-0.8nm",
                "electron_contaminaton": False,
            },
            {
                "time_tag": "2026-11-14T01:01:00Z",
                "satellite": 18,
                "flux": 1.0e-2,
                "energy": "0.1-0.8nm",
                "electron_contaminaton": True,
            },
            {
                "time_tag": "2026-11-14T01:02:00Z",
                "satellite": 18,
                "flux": 4.0e-3,
                "energy": "0.05-0.4nm",
                "electron_contaminaton": False,
            },
            {
                "time_tag": "2026-11-14T01:03:00Z",
                "satellite": 18,
                "flux": 1.0e-5,
                "energy": "0.1-0.8nm",
                "electron_contaminaton": False,
            },
        ]
        with patch(
            "lunar_web_app.urlopen",
            return_value=io.BytesIO(json.dumps(readings).encode("utf-8")),
        ):
            response = self.client.get("/api/solar-xray")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["latest"]["class"], "M1.0")
        self.assertEqual(payload["peak_24h"]["class"], "M2.5")
        self.assertEqual(len(payload["samples"]), 2)

    def test_dust_plume_screen_api_returns_geometric_overlap_and_validates_inputs(self):
        response = self.client.post(
            "/api/dust-plume-screen",
            json={
                "route_lat_lon": [[0, -1], [0, 1]],
                "source_latitude": 0,
                "source_longitude": 0,
                "axis_azimuth_degrees": 90,
                "downrange_extent_km": 50,
                "cross_track_half_width_km": 2,
                "evidence_source": "test scenario",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["overlap"])
        self.assertIn("user-defined", response.get_json()["model"])
        self.assertEqual(response.get_json()["evidence_source"], "test scenario")

        invalid = self.client.post(
            "/api/dust-plume-screen",
            json={
                "route_lat_lon": [[0, 0], [0, 1]],
                "source_latitude": 91,
                "source_longitude": 0,
                "axis_azimuth_degrees": 90,
                "downrange_extent_km": 50,
                "cross_track_half_width_km": 2,
            },
        )
        self.assertEqual(invalid.status_code, 400)

    def test_shackleton_destination_is_flagged_for_provisional_hazard_handling(self):
        with patch("lunar_web_app.generate_terrain_payload", return_value={"ok": True}) as generate:
            response = self.client.get(
                "/api/terrain?start_lat=-89.8&start_lon=0&dest_lat=-89.9&dest_lon=0"
                "&dest_name=Shackleton%20Crater"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(generate.call_args.kwargs["destination_is_shackleton"])

    def test_extracts_signed_gps_coordinates_from_image_exif(self):
        gps_ifd = {
            1: "S",
            2: (12, 30, 0),
            3: "W",
            4: (45, 15, 0),
        }
        exif = Mock()
        exif.get_ifd.return_value = gps_ifd
        image = Mock()
        image.getexif.return_value = exif

        with patch("lunar_web_app.ExifTags.GPSTAGS", {
            1: "GPSLatitudeRef",
            2: "GPSLatitude",
            3: "GPSLongitudeRef",
            4: "GPSLongitude",
        }):
            location = _extract_exif_location(image)

        self.assertEqual(location, (-12.5, -45.25))

    def test_home_page_explains_dem_image_context_and_dust_model_limits(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<body data-view="mission">', response.data)
        self.assertIn(b"Image GPS latitude override", response.data)
        self.assertIn(b"nearby context", response.data)
        self.assertIn(b"does not calculate probability", response.data)
        self.assertIn(b"Solar flares", response.data)
        self.assertIn(b"Lunar radiation", response.data)
        self.assertIn(b"NOAA GOES X-ray data", response.data)
        self.assertIn(b"No live lunar radiation readings", response.data)
        self.assertIn(b'value="8.40651"', response.data)
        self.assertIn(b'value="7.0867583"', response.data)
        self.assertNotIn(b"Apollo 11", response.data)
        self.assertIn(b"WHAT TO DO NOW", response.data)
        self.assertIn(b"Check whether a dust plume could cross the route", response.data)
        self.assertIn(b"Search LROC images", response.data)
        self.assertIn(b'id="dust-workflow"', response.data)
        self.assertIn(b'id="movement-workflow"', response.data)
        self.assertIn(b'id="radiation-workflow"', response.data)
        self.assertIn(b'id="solar-workflow"', response.data)
        self.assertIn(b'class="route-layout"', response.data)
        self.assertIn(b'id="field-observations"', response.data)
        self.assertIn(b"Classifier readiness", response.data)
        self.assertIn(b'id="plume-model-panel"', response.data)
        self.assertIn(b'id="screen-plume"', response.data)
        self.assertIn(b"does not simulate gas flow, particle transport, or deposition", response.data)
        self.assertIn(b"https://ntrs.nasa.gov/citations/20180001348", response.data)
        self.assertIn(b"dataset/articles/reference_links.json", response.data)
        self.assertIn(b"NASA Science: Moon Dust Hazards", response.data)
        self.assertIn(
            b"https://science.nasa.gov/biological-physical/what-hazards-are-caused-by-lunar-regolith/",
            response.data,
        )
        self.assertIn(b"NASA Reference: The Lunar South Pole Region", response.data)
        self.assertIn(b"Predicted labels -- not_safe: 73, safe: 0", response.data)
        self.assertIn(b"not an independent or mission-representative test set", response.data)
        self.assertIn(b'id="gallery-dialog"', response.data)
        self.assertIn(b'id="sources-dialog"', response.data)
        self.assertIn(b'id="sources-open"', response.data)
        self.assertEqual(response.data.count(b'class="source-gallery-card"'), 4)
        self.assertIn(b'id="next-step-list"', response.data)
        self.assertIn(b'id="route-evidence"', response.data)
        self.assertIn(b'id="export-assessment"', response.data)
        self.assertIn(b'id="max_slope_degrees"', response.data)
        self.assertIn(b'id="planning_speed_kmh"', response.data)
        self.assertIn(b'/static/zpl-logo.png', response.data)
        self.assertIn(b'role="tablist"', response.data)
        self.assertEqual(response.data.count(b'role="tab"'), 9)
        self.assertIn(b">Home</button>", response.data)
        self.assertIn(b">Simulator</button>", response.data)
        self.assertIn(b">Data</button>", response.data)
        self.assertIn(b"Chandrayaan-3", response.data)
        self.assertIn(b'id="plan-gate"', response.data)
        self.assertIn(b'id="sun-compare"', response.data)
        self.assertIn(b'id="mission-workflow"', response.data)
        self.assertIn(b'id="data-workflow"', response.data)
        self.assertIn(b"Astronauts at Shackleton have to cross a crater rim", response.data)
        self.assertIn(b'id="landing-quiz"', response.data)
        self.assertIn(b'id="radiation-board"', response.data)
        self.assertIn(b"walk_safe.keras", response.data)
        self.assertIn(b'id="trained-record"', response.data)
        self.assertIn(b"These models do not detect water ice.", response.data)
        self.assertIn(b"It does not detect ice.", response.data)
        self.assertIn(b"What should the path watch first?", response.data)
        self.assertIn(b'id="brief-focus-note"', response.data)
        self.assertIn(b"does not change the terrain data or safety checks", response.data)
        self.assertIn(b'id="briefing"', response.data)
        self.assertIn(b"Who should this brief protect?", response.data)
        self.assertIn(b'id="elevation-stage"', response.data)
        self.assertIn(b'id="dust-look"', response.data)
        self.assertIn(b'id="temperature-workflow"', response.data)
        self.assertIn(b"A flare cannot be stopped.", response.data)
        self.assertIn(b"Advanced status &amp; model details", response.data)
        self.assertIn(b"Camera &amp; 3D terrain", response.data)

    def test_nasa_image_gallery_only_returns_trusted_reference_thumbnails(self):
        catalog = {
            "collection": {
                "items": [
                    {
                        "data": [{
                            "nasa_id": "PIA123",
                            "title": "Lunar crater",
                            "description": "LRO image of the lunar surface.",
                            "date_created": "2021-01-02T00:00:00Z",
                        }],
                        "links": [{
                            "rel": "preview",
                            "href": "https://images-assets.nasa.gov/image/PIA123/PIA123~thumb.jpg",
                        }],
                    },
                    {
                        "data": [{"nasa_id": "BAD", "title": "Untrusted image"}],
                        "links": [{
                            "rel": "preview",
                            "href": "https://example.com/image.jpg",
                        }],
                    },
                    {
                        "data": [{
                            "nasa_id": "KSC1",
                            "title": "LRO spacecraft",
                            "description": "Lunar crater and surface mission hardware.",
                            "center": "KSC",
                        }],
                        "links": [{
                            "rel": "preview",
                            "href": "https://images-assets.nasa.gov/image/KSC1/KSC1~thumb.jpg",
                        }],
                    },
                ]
            }
        }

        with patch(
            "lunar_web_app.urlopen",
            return_value=io.BytesIO(json.dumps(catalog).encode("utf-8")),
        ):
            from lunar_web_app import _fetch_nasa_reference_images

            _fetch_nasa_reference_images.cache_clear()
            try:
                response = self.client.get("/api/nasa-images")
            finally:
                _fetch_nasa_reference_images.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertIn("exact target match unverified", payload["items"][0]["match_label"])
        self.assertIn("not coordinate-verified", payload["match_policy"])

    def test_empty_traverse_fields_default_to_target_and_dem_hazard_screening(self):
        response = self.client.post(
            "/",
            data={
                "start_name": "",
                "start_lat": "",
                "start_lon": "",
                "dest_name": "",
                "dest_lat": "",
                "dest_lon": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DEFAULTS["start_lat"], 8.40651)
        self.assertEqual(DEFAULTS["dest_lat"], 7.0867583)
        self.assertNotIn("Apollo 11", DEFAULTS["start_name"])
        self.assertIn(b'value="8.40651"', response.data)
        self.assertIn(b'value="7.0867583"', response.data)
        self.assertIn(b'data-view="dust"', response.data)

    def test_route_form_preserves_slope_and_speed_assumptions(self):
        response = self.client.post(
            "/",
            data={"max_slope_degrees": "14", "planning_speed_kmh": "0.8"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="max_slope_degrees"', response.data)
        self.assertIn(b'id="planning_speed_kmh"', response.data)
        self.assertIn(b'value="14.0"', response.data)
        self.assertIn(b'value="0.8"', response.data)

        invalid = self.client.post(
            "/",
            data={"max_slope_degrees": "31", "planning_speed_kmh": "0.8"},
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn(b"Slope screen limit must be between 5 and 30", invalid.data)

    def test_uploaded_image_uses_manual_coordinates_for_nearby_dem_context(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (8, 8), color="gray").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        nearby = {
            "radius_km": 10.0,
            "max_slope_degrees": 20.0,
            "max_roughness_m": 12.0,
            "resolution_note": "LDEM resolution note",
            "slope_hotspots": [],
        }

        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("lunar_web_app.UPLOAD_FOLDER", upload_dir), patch(
                "lunar_web_app.classify_image",
                return_value=("safe", 90.0, "Test classification", {"safe": 90.0}),
            ), patch(
                "lunar_web_app.analyze_nearby_terrain", return_value=nearby
            ) as analyze:
                response = self.client.post(
                    "/",
                    data={
                        "image": (image_bytes, "rover.png"),
                        "image_lat": "12.5",
                        "image_lon": "-45.25",
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(12.5, -45.25)
        self.assertIn(b"20.0", response.data)
        self.assertIn(b"-45.25", response.data)
        self.assertIn(b"Experimental image label (not a safety decision): safe", response.data)
        self.assertIn(b'data-view="movement"', response.data)

    def test_uploaded_image_exif_location_is_placed_on_mission_tab(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (8, 8), color="gray").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        nearby = {
            "radius_km": 10.0,
            "max_slope_degrees": 20.0,
            "max_roughness_m": 12.0,
            "resolution_note": "LDEM resolution note",
            "slope_hotspots": [],
        }

        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("lunar_web_app.UPLOAD_FOLDER", upload_dir), patch(
                "lunar_web_app._extract_exif_location", return_value=(12.5, -45.25)
            ), patch(
                "lunar_web_app.classify_image",
                return_value=("safe", 90.0, "Test classification", {"safe": 90.0}),
            ), patch(
                "lunar_web_app.analyze_nearby_terrain", return_value=nearby
            ):
                response = self.client.post(
                    "/",
                    data={"image": (image_bytes, "rover.png")},
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-view="movement"', response.data)
        self.assertIn(b'"lat": 12.5', response.data)
        self.assertIn(b'"lon": -45.25', response.data)

    def test_uploaded_image_without_gps_enables_map_area_fallback(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (8, 8), color="gray").save(image_bytes, format="PNG")
        image_bytes.seek(0)

        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("lunar_web_app.UPLOAD_FOLDER", upload_dir), patch(
                "lunar_web_app.classify_image",
                return_value=("not_safe", 80.0, "Test classification", {"not_safe": 80.0}),
            ):
                response = self.client.post(
                    "/",
                    data={"image": (image_bytes, "rover.png")},
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"highest-complexity area in the selected map window", response.data)
        self.assertIn(b"const imageNeedsAreaGuess = true;", response.data)

    def test_terrain_view_api_renders_and_returns_eight_target_angles(self):
        names = (
            "1_overhead",
            "2_north_oblique",
            "3_east_oblique",
            "4_south_oblique",
            "5_west_oblique",
            "6_north_grazing",
            "7_east_grazing",
            "8_west_grazing",
        )

        def create_views(lat, lon, radius, prefix, folder, **kwargs):
            for name in names:
                path = os.path.join(folder, f"{prefix}_{name}.png")
                with open(path, "wb") as image_file:
                    image_file.write(b"png")
            return [f"{prefix}_{name}.png" for name in names]

        with tempfile.TemporaryDirectory() as output_folder:
            with patch("lunar_web_app.TERRAIN_VIEW_FOLDER", output_folder), patch(
                "lunar_web_app.generate_3d_mesh_renders", side_effect=create_views
            ) as render_views:
                response = self.client.get("/api/terrain-views")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([view["name"] for view in payload["views"]], list(names))
        self.assertEqual(
            render_views.call_args.args[:3],
            (8.40651, 84.75701, 100.0),
        )
        self.assertEqual(render_views.call_args.kwargs["mesh_points"], 500)

    def test_flare_outlook_accepts_a_sunspot_region_and_rejects_bad_codes(self):
        response = self.client.post(
            "/api/flare-outlook",
            json={
                "zurich_class": "F",
                "spot_size": "K",
                "distribution": "C",
                "activity": 2,
                "evolution": 3,
                "prev_flare": 2,
                "sheltered": "no",
                "asset": "rover",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["region_code"], "Fkc")
        self.assertGreaterEqual(payload["probability"], 0)
        self.assertLessEqual(payload["probability"], 1)
        self.assertTrue(payload["protection"])
        self.assertIn("not NOAA", payload["caveat"])

        invalid = self.client.post("/api/flare-outlook", json={"zurich_class": "Z"})
        self.assertEqual(invalid.status_code, 400)

    def test_mission_plan_uses_the_shared_answers(self):
        response = self.client.post(
            "/api/mission-plan",
            json={
                "priority": "radio",
                "asset": "rover",
                "sheltered": "no",
                "slope_limit": 18,
                "distance_km": 12,
                "speed_kmh": 0.5,
                "route_cleared": True,
                "samples": [{"lat": 0, "lon": 20, "slope": 6}],
                "sun_up": True,
                "storm_scale": "quiet",
                "goes_class": "B2.0",
                "flare_probability": 0.2,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["priority"], "radio")
        self.assertIn("dust", payload["links"])
        self.assertIsNotNone(payload["telemetry"]["dose_msv"])

        rejected = self.client.post("/api/mission-plan", json={"priority": "shortest"})
        self.assertEqual(rejected.status_code, 400)

    def test_lunar_environment_validates_coordinates_and_returns_the_estimate(self):
        sample = {
            "moonlight": {"irradiance_wm2": 0.001},
            "surface_radiation": {"baseline_gcr_usv_hr": 57.0, "protons": None},
            "temperature": {"celsius": -20.0},
            "protection": ["No storm step right now."],
        }
        with patch("lunar_web_app.environment_for_site", return_value=sample) as build:
            response = self.client.get("/api/lunar-environment?lat=8.4&lon=84.7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.args, (8.4, 84.7))
        self.assertEqual(response.get_json()["temperature"]["celsius"], -20.0)

        invalid = self.client.get("/api/lunar-environment?lat=91&lon=0")
        self.assertEqual(invalid.status_code, 400)

    def test_reference_links_load_from_dataset_articles(self):
        links = _load_reference_links()
        self.assertGreaterEqual(len(links), 11)
        titles = {link["title"] for link in links}
        self.assertIn("NASA Science: Moon Dust Hazards", titles)
        self.assertIn("NASA Reference: The Lunar South Pole Region (Moon Base Environment)", titles)
        dust = _filter_reference_links(("dust", "regolith", "plume", "ochmo"))
        self.assertTrue(any("Dust" in link["title"] or "Regolith" in link["title"] for link in dust))
        site = _filter_reference_links(("shackleton", "south pole", "power", "water", "ice"))
        self.assertTrue(any("Shackleton" in link["title"] or "South Pole" in link["title"] for link in site))


if __name__ == "__main__":
    unittest.main()
