import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, render_template_string, request, url_for
from PIL import ExifTags, Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from article_analysis import analyze_article
from dust_plume_engine import screen_route_against_plume_corridor
from landing_sites import choose_landing
from mission_plan import build_mission_plan
from shackleton_models import screen_shackleton
from space_weather import assess_flare_region, environment_for_site
from hazard_classifier import (
    available_model_classes,
    classify_image,
    model_validation_summary,
)
from terrain_engine import (
    analyze_nearby_terrain,
    generate_3d_mesh_renders,
    generate_terrain_payload,
    moon_disk_jpeg,
    moon_trek_patch,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
TERRAIN_VIEW_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "terrain_views")
TERRAIN_VIEW_PREFIX = "target_8_40651_84_75701_r100_m500_v2"
TERRAIN_VIEW_LOCATION = (8.40651, 84.75701)
GOES_XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"
TERRAIN_VIEW_NAMES = (
    "1_overhead",
    "2_north_oblique",
    "3_east_oblique",
    "4_south_oblique",
    "5_west_oblique",
    "6_north_grazing",
    "7_east_grazing",
    "8_west_grazing",
)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DEFAULTS = {
    "start_name": "LRO target",
    "start_lat": 8.40651,
    "start_lon": 84.75701,
    "dest_name": "DEM hotspot",
    "dest_lat": 7.0867583,
    "dest_lon": 85.4850388,
    "max_slope_degrees": 18.0,
    "planning_speed_kmh": 0.5,
}

HTML_TEMPLATE = """
