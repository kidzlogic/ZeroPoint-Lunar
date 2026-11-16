"""Compare south-polar landing sites and dates for the CLPS challenge.

For each region and each hour in the chosen window, this asks two questions:
is the Sun above the local LOLA ridge, and is Earth? Sun-up hours are the
power window. Earth-up hours are the direct-to-Earth radio window.

Sun and Earth directions use Meeus optical libration, good to about a degree.
The ridge line is LOLA LDEM 16, about 2 km per pixel. This is a planning
sketch, not a flight ephemeris and not a landing clearance.
"""
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np

from night_power import ARRAY_M2, DUST_KEEP, PANEL_EFFICIENCY, SOLAR_WM2
from terrain_engine import R_MOON, load_moon_data, local_frame, sample_map

EARTH_DISK_DEG = math.degrees(math.asin(6378.14 / 384400.0))
MOON_EQUATOR_TILT_DEG = 1.54242
AU_KM = 149597870.7
STEP_HOURS = 2.0
SCAN_STEP_HOURS = 6.0
SCAN_DAYS = 370
HORIZON_BINS = 36
HORIZON_RANGES_KM = (4.0, 8.0, 16.0, 32.0, 64.0, 110.0)
SHOULDER_RADIUS_KM = 22.0
TRACKING_WATTS = SOLAR_WM2 * ARRAY_M2 * PANEL_EFFICIENCY * DUST_KEEP

# Region centers already used by the crater list, plus two Artemis regions
# the walk screen did not name. Coordinates are region centers, not pins.
SITES = (
    {
        "id": "connecting-ridge",
        "name": "Connecting Ridge",
        "lat": -89.45,
        "lon": -137.4,
        "select_value": "-89.45,-137.4",
        "note": "de Gerlache–Shackleton ridge",
    },
    {
        "id": "shackleton",
        "name": "Shackleton rim",
        "lat": -89.5,
        "lon": 0.0,
        "select_value": "-89.5,0",
        "note": "Crater rim at the south pole",
    },
    {
        "id": "de-gerlache",
        "name": "de Gerlache rim",
        "lat": -88.23,
        "lon": -65.11,
        "select_value": "-88.23,-65.11",
        "note": "Artemis candidate region",
    },
    {
        "id": "faustini",
        "name": "Faustini rim",
        "lat": -87.18,
        "lon": 84.0,
        "select_value": "-87.18,84",
        "note": "Artemis candidate region",
    },
    {
        "id": "haworth",
        "name": "Haworth crater",
        "lat": -86.9,
        "lon": -4.2,
        "select_value": "-86.9,-4.2",
        "note": "South-pole crater",
    },
    {
        "id": "malapert",
        "name": "Malapert Massif",
        "lat": -85.99,
        "lon": -0.24,
        "select_value": "-85.99,-0.24",
        "note": "Artemis candidate region",
    },
    {
        "id": "nobile",
        "name": "Nobile rim",
        "lat": -85.43,
        "lon": 37.33,
        "select_value": "-85.43,37.33",
        "note": "VIPER region",
    },
)

LIMITS = (
    "Each region is scored on the open high ground within 22 km of its center, "
    "not on a crater floor. Sun and Earth use Meeus optical libration, about 1°. "
    "The ridge is LOLA LDEM 16, about 2 km per pixel, read out to 110 km. "
    "Earth is drawn as its center; the real disk is about "
    f"{EARTH_DISK_DEG * 2:.1f}° across. "
    f"The array is a planning size: {ARRAY_M2:.0f} m², {PANEL_EFFICIENCY:.0%} efficient, "
    "with 15% held back for dust. Not a flight clearance and not an ice map."
)


def _wrap180(degrees):
    return (degrees + 180.0) % 360.0 - 180.0


def julian_day(moment):
    """Julian day for a UTC datetime. J2000 noon is 2451545.0."""
    moment = moment.astimezone(timezone.utc)
    year, month = moment.year, moment.month
    day = (
        moment.day
        + (moment.hour + (moment.minute + moment.second / 60.0) / 60.0) / 24.0
    )
    if month <= 2:
        year -= 1
        month += 12
    century = year // 100
    gregorian = 2 - century + century // 4
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + gregorian
        - 1524.5
    )


def _arguments(jd):
    """Meeus fundamental arguments in degrees. Low-precision lunar theory."""
    century = (jd - 2451545.0) / 36525.0
    t2 = century * century
    t3 = t2 * century
    t4 = t2 * t2

    def spin(value):
        return value % 360.0

    return {
        "T": century,
        "Lp": spin(218.3164477 + 481267.88123421 * century - 0.0015786 * t2 + t3 / 538841 - t4 / 65194000),
        "D": spin(297.8501921 + 445267.1114034 * century - 0.0018819 * t2 + t3 / 545868 - t4 / 113065000),
        "M": spin(357.5291092 + 35999.0502909 * century - 0.0001536 * t2 + t3 / 24490000),
        "Mp": spin(134.9633964 + 477198.8675055 * century + 0.0087414 * t2 + t3 / 69699 - t4 / 14712000),
        "F": spin(93.2720950 + 483202.0175233 * century - 0.0036539 * t2 + t3 / 3526000 - t4 / 863310000),
        "Om": spin(125.0445479 - 1934.1362891 * century + 0.0020754 * t2 + t3 / 467441 - t4 / 60616000),
    }


def _optical(lam_deg, bet_deg, argument_deg, node_deg):
    """Selenographic longitude and latitude of a body. Meeus optical libration."""
    tilt = math.radians(MOON_EQUATOR_TILT_DEG)
    west = math.radians(lam_deg - node_deg)
    beta = math.radians(bet_deg)
    sin_w, cos_w = math.sin(west), math.cos(west)
    sin_b, cos_b = math.sin(beta), math.cos(beta)
    sin_i, cos_i = math.sin(tilt), math.cos(tilt)
    angle = math.atan2(sin_w * cos_b * cos_i - sin_b * sin_i, cos_w * cos_b)
    longitude = _wrap180(math.degrees(angle - math.radians(argument_deg)))
    latitude = math.degrees(math.asin(max(-1.0, min(1.0, -sin_w * cos_b * sin_i - sin_b * cos_i))))
    return longitude, latitude


def body_points(moment):
    """Sub-Earth and sub-solar selenographic longitude and latitude, degrees."""
    args = _arguments(julian_day(moment))
    elong = math.radians(args["D"])
    sun_anom = math.radians(args["M"])
    moon_anom = math.radians(args["Mp"])
    lat_arg = math.radians(args["F"])
    eccentricity = 1 - 0.002516 * args["T"] - 0.0000074 * args["T"] * args["T"]
    moon_lon = args["Lp"] + (
        6.288774 * math.sin(moon_anom)
        + 1.274027 * math.sin(2 * elong - moon_anom)
        + 0.658314 * math.sin(2 * elong)
        + 0.213618 * math.sin(2 * moon_anom)
        - 0.185116 * eccentricity * math.sin(sun_anom)
        - 0.114332 * math.sin(2 * lat_arg)
    )
    moon_lat = (
        5.128122 * math.sin(lat_arg)
        + 0.280602 * math.sin(moon_anom + lat_arg)
        + 0.277693 * math.sin(moon_anom - lat_arg)
        + 0.173237 * math.sin(2 * elong - lat_arg)
        + 0.055413 * math.sin(2 * elong - moon_anom + lat_arg)
        + 0.046271 * math.sin(2 * elong - moon_anom - lat_arg)
        + 0.032573 * math.sin(2 * elong + lat_arg)
        + 0.017198 * math.sin(2 * moon_anom + lat_arg)
    )
    earth_lon, earth_lat = _optical(moon_lon, moon_lat, args["F"], args["Om"])
    center = (
        (1.914602 - 0.004817 * args["T"] - 0.000014 * args["T"] * args["T"]) * math.sin(sun_anom)
        + (0.019993 - 0.000101 * args["T"]) * math.sin(2 * sun_anom)
        + 0.000289 * math.sin(3 * sun_anom)
    )
    sun_lon = 280.46646 + 36000.76983 * args["T"] + 0.0003032 * args["T"] * args["T"] + center
    orbit_e = 0.016708634 - 0.000042037 * args["T"]
    sun_au = 1.000001018 * (1 - orbit_e * orbit_e) / (1 + orbit_e * math.cos(sun_anom + math.radians(center)))
    moon_km = (
        385000.56
        - 20905.355 * math.cos(moon_anom)
        - 3699.111 * math.cos(2 * elong - moon_anom)
        - 2955.968 * math.cos(2 * elong)
        - 569.925 * math.cos(2 * moon_anom)
    )
    parallax = moon_km / (sun_au * AU_KM)
    sun_from_moon = sun_lon + 180.0 + math.degrees(
        parallax * math.cos(math.radians(moon_lat)) * math.sin(math.radians(sun_lon - moon_lon))
    )
    sun_lat_from_moon = math.degrees(parallax * math.radians(moon_lat))
    solar_lon, solar_lat = _optical(sun_from_moon, sun_lat_from_moon, args["F"], args["Om"])
    return {
        "earth_lon": earth_lon,
        "earth_lat": earth_lat,
        "sun_lon": solar_lon,
        "sun_lat": solar_lat,
    }


def observe(lat, lon, sub_lat, sub_lon):
    """Elevation and azimuth of a sub-point. Azimuth is degrees from north toward east."""
    phi = math.radians(lat)
    beta = math.radians(sub_lat)
    delta = math.radians(sub_lon - lon)
    sine = (
        math.sin(phi) * math.sin(beta)
        + math.cos(phi) * math.cos(beta) * math.cos(delta)
    )
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, sine))))
    east = math.sin(delta) * math.cos(beta)
    north = math.cos(phi) * math.sin(beta) - math.sin(phi) * math.cos(beta) * math.cos(delta)
    azimuth = math.degrees(math.atan2(east, north)) % 360.0
    return elevation, azimuth


def _horizon_at(mask, azimuth):
    count = len(mask)
    position = (azimuth % 360.0) / 360.0 * count
    left = int(math.floor(position)) % count
    right = (left + 1) % count
    mix = position - math.floor(position)
    return mask[left] * (1.0 - mix) + mask[right] * mix


@lru_cache(maxsize=16)
def _horizon_mask(lat_key, lon_key):
    """Highest terrain altitude in each azimuth, degrees above the local horizontal."""
    lat, lon = lat_key / 1000.0, lon_key / 1000.0
    try:
        _, height = load_moon_data()
    except (OSError, ValueError):
        return tuple(0.0 for _ in range(HORIZON_BINS)), "smooth"
    site_height = float(np.asarray(sample_map(
        height, np.asarray([lat], dtype=float), np.asarray([lon], dtype=float)
    )).reshape(-1)[0])
    azimuths = np.linspace(0.0, 360.0, HORIZON_BINS, endpoint=False)
    ranges = np.asarray(HORIZON_RANGES_KM, dtype=float)
    az_grid, range_grid = np.meshgrid(azimuths, ranges, indexing="ij")
    east_km = range_grid * np.sin(np.radians(az_grid))
    north_km = range_grid * np.cos(np.radians(az_grid))
    center, east_hat, north_hat = local_frame(lat, lon)
    offset = east_hat * east_km[..., None] + north_hat * north_km[..., None]
    distance = np.linalg.norm(offset, axis=-1)
    angle = distance / R_MOON
    direction = (
        center * np.cos(angle)[..., None]
        + offset / np.maximum(distance, 1e-9)[..., None] * np.sin(angle)[..., None]
    )
    latitudes = np.degrees(np.arcsin(np.clip(direction[..., 2], -1.0, 1.0)))
    longitudes = np.degrees(np.arctan2(direction[..., 1], direction[..., 0]))
    neighbor_km = sample_map(height, latitudes, longitudes)
    site_vec = center * (R_MOON + site_height)
    neighbor_vec = direction * (R_MOON + neighbor_km)[..., None]
    delta = neighbor_vec - site_vec
    delta /= np.linalg.norm(delta, axis=-1, keepdims=True)
    sky = np.degrees(np.arcsin(np.clip(delta @ center, -1.0, 1.0)))
    mask = tuple(round(float(value), 2) for value in sky.max(axis=1))
    return mask, "lola"


def horizon_for(lat, lon):
    mask, source = _horizon_mask(round(lat * 1000), round(lon * 1000))
    return mask, source


def _latlon_grid(lat, lon, east_km, north_km):
    center, east_hat, north_hat = local_frame(float(lat), float(lon))
    offset = east_hat * east_km[..., None] + north_hat * north_km[..., None]
    distance = np.linalg.norm(offset, axis=-1)
    angle = distance / R_MOON
    direction = (
        center * np.cos(angle)[..., None]
        + offset / np.maximum(distance, 1e-9)[..., None] * np.sin(angle)[..., None]
    )
    latitudes = np.degrees(np.arcsin(np.clip(direction[..., 2], -1.0, 1.0)))
    longitudes = np.degrees(np.arctan2(direction[..., 1], direction[..., 0]))
    return latitudes, longitudes


@lru_cache(maxsize=16)
def _shoulder(lat_key, lon_key):
    """Open high ground within the region. A crater floor is a poor lander pin."""
    lat, lon = lat_key / 1000.0, lon_key / 1000.0
    try:
        _, height = load_moon_data()
    except (OSError, ValueError):
        return lat, lon, None, 0.0
    step = 4.0
    axis = np.arange(-SHOULDER_RADIUS_KM, SHOULDER_RADIUS_KM + step * 0.5, step)
    east, north = np.meshgrid(axis, axis)
    latitudes, longitudes = _latlon_grid(lat, lon, east, north)
    elevations = sample_map(height, latitudes, longitudes)
    inside = np.hypot(east, north) <= SHOULDER_RADIUS_KM
    peak = float(elevations[inside].max()) if inside.any() else float(elevations.max())
    high = inside & (elevations >= peak - 0.5)
    azimuths = np.linspace(0.0, 360.0, 8, endpoint=False)
    ring = 16.0
    neighbor_east = east[..., None] + ring * np.sin(np.radians(azimuths))
    neighbor_north = north[..., None] + ring * np.cos(np.radians(azimuths))
    neighbor_lat, neighbor_lon = _latlon_grid(lat, lon, neighbor_east, neighbor_north)
    neighbor_height = sample_map(height, neighbor_lat, neighbor_lon)
    openness = elevations - neighbor_height.max(axis=-1)
    best_open = float(np.where(high, openness, -1.0e9).max())
    nearest = np.where(high & (openness >= best_open - 0.25), np.hypot(east, north), 1.0e9)
    row, col = np.unravel_index(int(np.argmin(nearest)), nearest.shape)
    return (
        round(float(latitudes[row, col]), 3),
        round(float(longitudes[row, col]), 3),
        round(float(elevations[row, col]), 2),
        round(float(np.hypot(east[row, col], north[row, col])), 1),
    )


def landing_shoulder(lat, lon):
    return _shoulder(round(lat * 1000), round(lon * 1000))


def _window_score(sun_hours, comm_hours, window_hours):
    """A site has to keep both windows. One closed window cannot win."""
    if window_hours <= 0:
        return 0.0
    sun_share = max(0.0, sun_hours) / window_hours
    comm_share = max(0.0, comm_hours) / window_hours
    return round(100.0 * math.sqrt(sun_share * comm_share), 1)


def _call(sun_hours, comm_hours, window_hours):
    sun_share = sun_hours / window_hours if window_hours else 0.0
    comm_share = comm_hours / window_hours if window_hours else 0.0
    if sun_share >= 0.45 and comm_share >= 0.45:
        return "Sun and Earth both stay up"
    if sun_share < 0.15:
        return "Sun stays behind the ridge"
    if comm_share < 0.15:
        return "Earth stays behind the ridge"
    return "One window is short"


def _sample(lat, lon, moment, points, mask):
    sun_el, sun_az = observe(lat, lon, points["sun_lat"], points["sun_lon"])
    earth_el, earth_az = observe(lat, lon, points["earth_lat"], points["earth_lon"])
    sun_horizon = _horizon_at(mask, sun_az)
    earth_horizon = _horizon_at(mask, earth_az)
    sun_clear = sun_el > sun_horizon
    earth_clear = earth_el > earth_horizon
    disk_clear = earth_el + EARTH_DISK_DEG > earth_horizon
    solid = earth_el > earth_horizon + 2.0
    if sun_clear:
        tracking = TRACKING_WATTS
        flat = TRACKING_WATTS * max(0.0, math.sin(math.radians(sun_el)))
    else:
        tracking = 0.0
        flat = 0.0
    return {
        "sun_el": sun_el,
        "sun_az": sun_az,
        "earth_el": earth_el,
        "earth_az": earth_az,
        "sun_horizon": sun_horizon,
        "earth_horizon": earth_horizon,
        "sun_clear": sun_clear,
        "earth_clear": earth_clear,
        "disk_clear": disk_clear,
        "solid": solid,
        "tracking": tracking,
        "flat": flat,
    }


def _summarize(samples, step_hours):
    count = len(samples) or 1
    window = step_hours * count

    def hours(flag):
        return step_hours * sum(1 for sample in samples if sample[flag])

    def energy(key):
        return step_hours * sum(sample[key] for sample in samples) / 1000.0

    sun_hours = hours("sun_clear")
    comm_hours = hours("earth_clear")
    return {
        "sun_clear_hours": round(sun_hours, 1),
        "comm_hours": round(comm_hours, 1),
        "disk_hours": round(hours("disk_clear"), 1),
        "solid_hours": round(hours("solid"), 1),
        "tracking_kwh": round(energy("tracking"), 1),
        "flat_kwh": round(energy("flat"), 1),
        "peak_sun_deg": round(max(sample["sun_el"] for sample in samples), 2),
        "min_earth_deg": round(min(sample["earth_el"] for sample in samples), 2),
        "score": _window_score(sun_hours, comm_hours, window),
        "call": _call(sun_hours, comm_hours, window),
        "window_hours": round(window, 1),
    }


def _best_fortnight(lat, lon, mask, origin):
    """Slide a 14-day window across the next year. Coarser than the chart."""
    step = timedelta(hours=SCAN_STEP_HOURS)
    count = int(SCAN_DAYS * 24 / SCAN_STEP_HOURS)
    moments = [origin + step * index for index in range(count)]
    sun_clear = []
    earth_clear = []
    for moment in moments:
        sample = _sample(lat, lon, moment, body_points(moment), mask)
        sun_clear.append(sample["sun_clear"])
        earth_clear.append(sample["earth_clear"])
    window = int(14 * 24 / SCAN_STEP_HOURS)
    best = None
    sun_sum = 0
    earth_sum = 0
    for index in range(window):
        sun_sum += sun_clear[index]
        earth_sum += earth_clear[index]
    for start in range(0, count - window + 1):
        if start:
            sun_sum += sun_clear[start + window - 1] - sun_clear[start - 1]
            earth_sum += earth_clear[start + window - 1] - earth_clear[start - 1]
        sun_hours = sun_sum * SCAN_STEP_HOURS
        comm_hours = earth_sum * SCAN_STEP_HOURS
        score = _window_score(sun_hours, comm_hours, 14 * 24)
        if best is None or score > best["score"]:
            best = {
                "start": moments[start].strftime("%Y-%m-%d"),
                "label": moments[start].strftime("%d %b %Y"),
                "sun_clear_hours": round(sun_hours, 1),
                "comm_hours": round(comm_hours, 1),
                "score": score,
            }
    return best


def _headline(ranked, start, days):
    if not ranked:
        return "No sites to compare."
    leader = ranked[0]
    end = start + timedelta(days=days)
    sentence = (
        f"From {start:%d %b %Y} to {end:%d %b %Y}, {leader['name']} leads: "
        f"{leader['sun_clear_hours']:.0f} h of Sun above the local ridge and "
        f"{leader['comm_hours']:.0f} h with Earth above it."
    )
    if len(ranked) > 1:
        other = ranked[1]
        if (
            other["sun_clear_hours"] > leader["sun_clear_hours"] + 6
            and other["comm_hours"] + 6 < leader["comm_hours"]
        ):
            sentence += (
                f" {other['name']} gets more Sun, but Earth spends longer behind its ridge."
            )
        elif (
            other["comm_hours"] > leader["comm_hours"] + 6
            and other["sun_clear_hours"] + 6 < leader["sun_clear_hours"]
        ):
            sentence += (
                f" {other['name']} keeps Earth longer, but loses more of the Sun."
            )
    return sentence


def compare_sites(start, days=14.0, scan=True):
    """Rank every south-polar region for one stay, starting at `start` (UTC)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    days = max(3.0, min(35.0, float(days)))
    step = timedelta(hours=STEP_HOURS)
    count = max(2, int(round(days * 24 / STEP_HOURS)))
    moments = [start + step * index for index in range(count)]
    points = [body_points(moment) for moment in moments]
    ranked = []
    horizon_source = "lola"
    for site in SITES:
        shoulder_lat, shoulder_lon, ground_km, shift_km = landing_shoulder(site["lat"], site["lon"])
        mask, source = horizon_for(shoulder_lat, shoulder_lon)
        if source != "lola":
            horizon_source = source
        samples = [
            _sample(shoulder_lat, shoulder_lon, moment, point, mask)
            for moment, point in zip(moments, points)
        ]
        summary = _summarize(samples, STEP_HOURS)
        series = []
        for moment, sample in zip(moments, samples):
            series.append({
                "t": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "label": moment.strftime("%d %b"),
                "sun_elev": round(sample["sun_el"], 2),
                "sun_az": round(sample["sun_az"], 1),
                "earth_elev": round(sample["earth_el"], 2),
                "earth_az": round(sample["earth_az"], 1),
                "sun_horizon": round(sample["sun_horizon"], 2),
                "earth_horizon": round(sample["earth_horizon"], 2),
                "sun_clear": sample["sun_clear"],
                "earth_clear": sample["earth_clear"],
            })
        row = {
            **site,
            **summary,
            "shoulder_lat": shoulder_lat,
            "shoulder_lon": shoulder_lon,
            "ground_km": ground_km,
            "shift_km": shift_km,
            "horizon": [{"az": index * (360 / HORIZON_BINS), "elev": elev} for index, elev in enumerate(mask)],
            "series": series,
        }
        if scan:
            row["best"] = _best_fortnight(shoulder_lat, shoulder_lon, mask, start)
        ranked.append(row)
    ranked.sort(key=lambda row: (row["score"], row["sun_clear_hours"]), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return {
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": start.strftime("%Y-%m-%d"),
        "days": round(days, 2),
        "step_hours": STEP_HOURS,
        "horizon_source": horizon_source,
        "tracking_watts": round(TRACKING_WATTS, 0),
        "limits": LIMITS,
        "headline": _headline(ranked, start, days),
        "sites": ranked,
    }
