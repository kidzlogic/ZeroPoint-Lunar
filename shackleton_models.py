"""Five traverse screens trained on NASA LOLA elevation around Shackleton.

Labels come from the elevation grid itself: slope, a ridge blocking Earth,
and a low Sun blocked by the up-sun neighbor. The held-out cells are the
check. This is not an ice map and not a footstep survey. LDEM 16 is about
1.9 km per pixel.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from mission_plan import earth_elevation_degrees
from terrain_engine import R_MOON, calculate_slope, load_moon_data, local_frame, sample_map

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models" / "shackleton"
REPORT_PATH = MODEL_DIR / "report.json"
CENTER = (-89.5, 0.0)
TRAIN_RADIUS_KM = 40.0
TRAIN_SIZE = 25
SCREEN_RADIUS_KM = 18.0
SCREEN_SIZE = 13
WALK_DEGREES = 15.0
PAD_DEGREES = 5.0
SUN_ELEVATION = 2.0
SUN_AZIMUTH = 90.0
NEIGHBORS = (
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
)
MODEL_SPECS = (
    ("walk_safe", "Can a traveler cross this cell?", f"Center slope is {WALK_DEGREES:.0f}° or less."),
    ("pad_safe", "Can a habitat sit here without tipping?", f"Center slope is {PAD_DEGREES:.0f}° or less."),
    ("earth_clear", "Can the crew still see Earth?", "The neighbor toward Earth does not rise above Earth."),
    ("sun_clear", "Does a low Sun still reach the ground?", f"A Sun {SUN_ELEVATION:.0f}° up from azimuth {SUN_AZIMUTH:.0f}° clears the up-sun neighbor."),
    ("go_zone", "Is this a go for the crew?", "Walkable, Earth is clear, and the low Sun still reaches the cell."),
)


def neighborhood(lat0, lon0, radius_km, size):
    """Sample one LOLA patch. Row increases north, column increases east."""
    axis = np.linspace(-radius_km, radius_km, size)
    dx, dy = np.meshgrid(axis, axis)
    rho = np.hypot(dx, dy)
    angle = rho / R_MOON
    center, east, north = local_frame(lat0, lon0)
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(rho > 0, np.sin(angle) / rho, 1.0 / R_MOON)
    directions = (
        center[None, None, :] * np.cos(angle)[..., None]
        + (east[None, None, :] * dx[..., None] + north[None, None, :] * dy[..., None]) * factor[..., None]
    )
    directions /= np.linalg.norm(directions, axis=-1, keepdims=True)
    latitudes = np.degrees(np.arcsin(np.clip(directions[..., 2], -1, 1)))
    longitudes = np.degrees(np.arctan2(directions[..., 1], directions[..., 0]))
    _, height = load_moon_data()
    elevations = sample_map(height, latitudes, longitudes)
    spacing = float(axis[1] - axis[0])
    slopes = calculate_slope(elevations, spacing)
    return latitudes, longitudes, elevations, slopes, spacing


def _neighbor_delta(elevations, row, col, d_row, d_col):
    return float(elevations[row + d_row, col + d_col] - elevations[row, col])


def _rise_angle(elevations, row, col, d_row, d_col, spacing_km):
    distance = spacing_km * float(np.hypot(d_row, d_col))
    rise = _neighbor_delta(elevations, row, col, d_row, d_col)
    return float(np.degrees(np.arctan2(rise, distance)))


def _closest_neighbor(azimuth_degrees):
    best = None
    best_gap = 999.0
    for d_row, d_col in NEIGHBORS:
        bearing = float(np.degrees(np.arctan2(d_col, d_row)))
        gap = abs((bearing - azimuth_degrees + 180.0) % 360.0 - 180.0)
        if gap < best_gap:
            best_gap = gap
            best = (d_row, d_col)
    return best


def cell_record(latitudes, longitudes, elevations, slopes, row, col, spacing_km):
    lat = float(latitudes[row, col])
    lon = float(longitudes[row, col])
    features = [_neighbor_delta(elevations, row, col, d_row, d_col) for d_row, d_col in NEIGHBORS]
    features.extend([lat, lon])
    east_km, north_km = _earth_offset_km(lat, lon)
    earth_azimuth = float(np.degrees(np.arctan2(east_km, north_km)))
    earth_step = _closest_neighbor(earth_azimuth)
    sun_step = _closest_neighbor((SUN_AZIMUTH + 180.0) % 360.0)
    earth_up = earth_elevation_degrees(lat, lon)
    earth_clear = _rise_angle(elevations, row, col, *earth_step, spacing_km) <= earth_up
    sun_clear = _rise_angle(elevations, row, col, *sun_step, spacing_km) <= SUN_ELEVATION
    slope = float(slopes[row, col])
    walk = slope <= WALK_DEGREES
    pad = slope <= PAD_DEGREES
    go = walk and earth_clear and sun_clear
    return {
        "row": int(row),
        "col": int(col),
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "slope": round(slope, 2),
        "features": features,
        "labels": {
            "walk_safe": int(walk),
            "pad_safe": int(pad),
            "earth_clear": int(earth_clear),
            "sun_clear": int(sun_clear),
            "go_zone": int(go),
        },
    }


def _earth_offset_km(lat, lon):
    """East and north kilometers from this cell toward the mean sub-Earth point."""
    center, east, north = local_frame(lat, lon)
    point = np.array([1.0, 0.0, 0.0])
    tangent = point - float(np.dot(center, point)) * center
    length = float(np.linalg.norm(tangent))
    if length == 0:
        return 0.0, 0.0
    direction = tangent / length
    return float(np.dot(direction, east)), float(np.dot(direction, north))


def iter_cells(latitudes, longitudes, elevations, slopes, spacing_km):
    rows, cols = slopes.shape
    records = []
    for row in range(1, rows - 1):
        for col in range(1, cols - 1):
            records.append(cell_record(latitudes, longitudes, elevations, slopes, row, col, spacing_km))
    return records


def training_tables():
    latitudes, longitudes, elevations, slopes, spacing = neighborhood(*CENTER, TRAIN_RADIUS_KM, TRAIN_SIZE)
    records = iter_cells(latitudes, longitudes, elevations, slopes, spacing)
    features = np.asarray([record["features"] for record in records], dtype=np.float32)
    labels = {
        spec[0]: np.asarray([record["labels"][spec[0]] for record in records], dtype=np.float32)
        for spec in MODEL_SPECS
    }
    return features, labels, spacing, records


def load_report():
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def screen_shackleton():
    """Run the five saved models on a fresh LOLA patch around Shackleton."""
    import tensorflow as tf

    report = load_report()
    mean = np.asarray(report["feature_mean"], dtype=np.float32)
    scale = np.asarray(report["feature_scale"], dtype=np.float32)
    latitudes, longitudes, elevations, slopes, spacing = neighborhood(*CENTER, SCREEN_RADIUS_KM, SCREEN_SIZE)
    records = iter_cells(latitudes, longitudes, elevations, slopes, spacing)
    features = (np.asarray([record["features"] for record in records], dtype=np.float32) - mean) / scale
    models = {
        spec[0]: tf.keras.models.load_model(MODEL_DIR / f"{spec[0]}.keras", compile=False)
        for spec in MODEL_SPECS
    }
    probabilities = {
        name: model.predict(features, verbose=0).reshape(-1)
        for name, model in models.items()
    }
    cells = []
    for index, record in enumerate(records):
        scores = {name: round(float(probabilities[name][index]), 3) for name in probabilities}
        cells.append({
            "row": record["row"],
            "col": record["col"],
            "lat": record["lat"],
            "lon": record["lon"],
            "slope": record["slope"],
            "scores": scores,
            "go": scores["go_zone"] >= 0.5,
        })
    go_count = sum(cell["go"] for cell in cells)
    return {
        "problem": (
            "Astronauts at Shackleton have to cross a crater rim. "
            "The next cell can be too steep to walk, a ridge can hide Earth, "
            "and a low Sun can leave the ground in shadow."
        ),
        "center": {"name": "Shackleton rim", "lat": CENTER[0], "lon": CENTER[1]},
        "spacing_km": round(spacing, 2),
        "grid_size": SCREEN_SIZE - 2,
        "cell_count": len(cells),
        "go_count": go_count,
        "cells": cells,
        "models": report["models"],
        "source": report["source"],
        "note": report["note"],
    }
