"""Estimates for flare outlook, moonlight, lunar temperature, and proton storms.

Measured NOAA values stay labeled as measurements. The flare model and the
temperature envelope are planning aids, not operational forecasts.
"""
import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from urllib.request import Request, urlopen

PROTON_URL = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json"
NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_DAYS = 29.530588853
GCR_BASELINE_USV_HR = 57.0

ZURICH_CLASSES = ("A", "B", "C", "D", "E", "F", "H")
SPOT_SIZES = ("X", "R", "S", "A", "H", "K")
DISTRIBUTIONS = ("X", "O", "I", "C")

# Sunspot rows patterned on the UCI / NOAA flare attributes supplied for this
# project. The last column is 1 when an M-class or X-class flare follows.
FLARE_ROWS = [
    ["D", "S", "O", 1, 2, 1, 0],
    ["E", "K", "C", 2, 3, 2, 1],
    ["F", "K", "C", 2, 3, 3, 1],
    ["C", "R", "O", 1, 1, 1, 0],
    ["E", "A", "I", 2, 3, 1, 1],
    ["H", "H", "X", 1, 2, 1, 0],
    ["F", "H", "C", 2, 3, 2, 1],
    ["B", "X", "O", 1, 1, 1, 0],
    ["A", "X", "X", 1, 1, 1, 0],
    ["B", "R", "O", 1, 1, 1, 0],
    ["C", "S", "I", 1, 2, 1, 0],
    ["D", "A", "I", 2, 2, 1, 0],
    ["D", "K", "C", 2, 3, 3, 1],
    ["E", "H", "C", 2, 3, 2, 1],
    ["E", "K", "I", 2, 3, 3, 1],
    ["F", "A", "O", 1, 2, 1, 0],
    ["H", "R", "O", 1, 1, 1, 0],
    ["B", "S", "I", 1, 2, 1, 0],
    ["F", "K", "I", 2, 3, 1, 1],
    ["D", "S", "X", 1, 1, 1, 0],
    ["E", "K", "C", 1, 1, 1, 0],
    ["F", "H", "O", 2, 2, 2, 1],
    ["C", "A", "C", 2, 3, 2, 1],
    ["H", "X", "X", 1, 2, 1, 0],
]


def _choice(value, allowed, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be one of {', '.join(allowed)}.")
    token = value.strip().upper()
    if token not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}.")
    return token


def _level(value, name, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer from {low} to {high}.") from None
    if number < low or number > high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")
    return number


def feature_score(zurich, spot, distribution, activity, evolution, prev_flare):
    """Transparent 24-hour score used when scikit-learn is not installed."""
    zurich_score = {"A": 0.0, "B": 0.04, "C": 0.12, "H": 0.05, "D": 0.28, "E": 0.40, "F": 0.48}
    spot_score = {"X": 0.0, "R": 0.04, "S": 0.08, "A": 0.16, "H": 0.24, "K": 0.32}
    distribution_score = {"X": 0.0, "O": 0.04, "I": 0.10, "C": 0.18}
    raw = (
        zurich_score[zurich]
        + spot_score[spot]
        + distribution_score[distribution]
        + (0.04 if activity == 2 else 0.0)
        + {1: 0.0, 2: 0.04, 3: 0.12}[evolution]
        + {1: 0.0, 2: 0.10, 3: 0.16}[prev_flare]
    )
    return max(0.02, min(0.93, raw))


@lru_cache(maxsize=1)
def _forest():
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    features = [row[:6] for row in FLARE_ROWS]
    target = [row[6] for row in FLARE_ROWS]
    model = Pipeline(steps=[
        ("preprocessor", ColumnTransformer(transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), [0, 1, 2]),
            ("num", "passthrough", [3, 4, 5]),
        ])),
        ("classifier", RandomForestClassifier(n_estimators=100, random_state=42)),
    ])
    model.fit(features, target)
    return model


def predict_major_flare(zurich, spot, distribution, activity, evolution, prev_flare):
    """Probability that the described region produces an M- or X-class flare in 24 hours."""
    region = [zurich, spot, distribution, activity, evolution, prev_flare]
    try:
        probability = float(_forest().predict_proba([region])[0][1])
        engine = "scikit-learn RandomForestClassifier"
    except ImportError:
        probability = feature_score(zurich, spot, distribution, activity, evolution, prev_flare)
        engine = "feature score (scikit-learn is not installed)"
    return {
        "probability": round(max(0.0, min(1.0, probability)), 4),
        "engine": engine,
        "training_rows": len(FLARE_ROWS),
    }


def assess_flare_region(payload):
    """Validate a sunspot description and return the demo outlook plus protection steps."""
    if not isinstance(payload, dict):
        raise ValueError("A JSON sunspot description is required.")
    zurich = _choice(payload.get("zurich_class"), ZURICH_CLASSES, "Zurich class")
    spot = _choice(payload.get("spot_size"), SPOT_SIZES, "Spot size")
    distribution = _choice(payload.get("distribution"), DISTRIBUTIONS, "Distribution")
    activity = _level(payload.get("activity", 1), "Activity", 1, 2)
    evolution = _level(payload.get("evolution", 1), "Evolution", 1, 3)
    prev_flare = _level(payload.get("prev_flare", 1), "Previous flare", 1, 3)
    sheltered = payload.get("sheltered", "no")
    if sheltered not in {"yes", "no"}:
        sheltered = "no"
    asset = payload.get("asset", "rover")
    if asset not in {"rover", "crew", "both"}:
        asset = "rover"
    outlook = predict_major_flare(zurich, spot, distribution, activity, evolution, prev_flare)
    return {
        **outlook,
        "region_code": f"{zurich}{spot.lower()}{distribution.lower()}",
        "caveat": (
            "Demo model trained on a small sunspot table patterned on published "
            "McIntosh flare tendencies. It is not NOAA’s forecast and it is not today’s sunspot."
        ),
        "protection": protection_steps(
            flare_probability=outlook["probability"],
            goes_class="",
            storm_scale="quiet",
            sheltered=sheltered,
            asset=asset,
        ),
    }


def lunar_cycle_fraction(when):
    age_days = (when - NEW_MOON).total_seconds() / 86400.0
    return age_days / SYNODIC_DAYS


def reflected_irradiance(when):
    """Moonlight at Earth from the illuminated fraction and a visual-magnitude fit."""
    cycle = lunar_cycle_fraction(when) % 1.0
    phase_percent = 100.0 * (1.0 - math.cos(2.0 * math.pi * cycle)) / 2.0
    phase_angle = math.acos(max(-1.0, min(1.0, 2.0 * (phase_percent / 100.0) - 1.0)))
    degrees = math.degrees(phase_angle)
    magnitude = -12.74 + 0.026 * abs(degrees) + 4e-9 * (degrees ** 4)
    illuminance_lux = 10 ** (-0.4 * (magnitude + 14.18))
    irradiance = illuminance_lux * 0.0079
    return {
        "phase_percent": round(phase_percent, 1),
        "visual_magnitude": round(magnitude, 2),
        "illuminance_lux": round(illuminance_lux, 4),
        "irradiance_wm2": round(irradiance, 6),
        "note": (
            "Moonlight at Earth, not a dose on the lunar surface. "
            "Phase uses the mean synodic month. The magnitude fit is weak near new moon."
        ),
    }


def surface_temperature(lat, lon, when):
    """Approximate Diviner day/night envelope at one site. Not a live reading."""
    cycle = lunar_cycle_fraction(when) % 1.0
    age_days = (when - NEW_MOON).total_seconds() / 86400.0
    subsolar_lon = (180.0 - 360.0 * cycle + 180.0) % 360.0 - 180.0
    subsolar_lat = 1.54 * math.sin(2.0 * math.pi * age_days / 346.62)
    hour = math.radians((lon - subsolar_lon + 540.0) % 360.0 - 180.0)
    sine_elev = (
        math.sin(math.radians(lat)) * math.sin(math.radians(subsolar_lat))
        + math.cos(math.radians(lat)) * math.cos(math.radians(subsolar_lat)) * math.cos(hour)
    )
    elevation = math.asin(max(-1.0, min(1.0, sine_elev)))
    daylight = max(math.cos(math.radians(lat)), 0.0)
    day_k = 100.0 + 300.0 * (daylight ** 0.25)
    night_k = 40.0 + 60.0 * daylight
    if elevation <= 0:
        kelvin = night_k
    else:
        kelvin = night_k + (day_k - night_k) * (math.sin(elevation) ** 0.25)
    return {
        "celsius": round(kelvin - 273.15, 1),
        "day_high_c": round(day_k - 273.15, 1),
        "night_low_c": round(night_k - 273.15, 1),
        "sun_up": elevation > 0,
        "note": (
            "Approximate equator-to-pole day and night envelope inspired by Diviner. "
            "Not a live Diviner measurement, and it does not resolve crater shadows."
        ),
    }


def storm_scale(pfu):
    """NOAA solar-radiation storm scale from >=10 MeV proton flux."""
    if pfu >= 100000:
        return "S5"
    if pfu >= 10000:
        return "S4"
    if pfu >= 1000:
        return "S3"
    if pfu >= 100:
        return "S2"
    if pfu >= 10:
        return "S1"
    return "quiet"


def latest_proton_flux(records):
    samples = []
    for record in records:
        if not isinstance(record, dict) or record.get("energy") != ">=10 MeV":
            continue
        flux = record.get("flux")
        time_tag = record.get("time_tag")
        if (
            isinstance(flux, bool)
            or not isinstance(flux, (int, float))
            or not math.isfinite(flux)
            or flux < 0
            or not isinstance(time_tag, str)
        ):
            continue
        samples.append({
            "time_utc": time_tag,
            "flux_pfu": float(flux),
            "satellite": record.get("satellite"),
        })
    if not samples:
        raise ValueError("NOAA returned no >=10 MeV proton readings.")
    samples.sort(key=lambda item: item["time_utc"])
    latest = samples[-1]
    return {**latest, "storm_scale": storm_scale(latest["flux_pfu"])}


def fetch_proton_records():
    request = Request(PROTON_URL, headers={"User-Agent": "ZeroPointLunar/1.0 (public proton display)"})
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("NOAA returned an unexpected proton format.")
    return payload


def protection_steps(flare_probability, goes_class, storm_scale, sheltered, asset, temperature_c=None):
    """Actions that keep hardware working. They do not stop the Sun."""
    storming = (
        str(goes_class).startswith(("M", "X"))
        or flare_probability >= 0.5
        or storm_scale not in {"quiet", "unknown", ""}
    )
    who = {"rover": "the rover", "crew": "the crew", "both": "the crew and the rover"}.get(asset, "the rover")
    if storming:
        steps = [
            f"A flare cannot be stopped. Park and pause work that leaves {who} exposed.",
        ]
        if sheltered == "yes":
            steps.append("Put people and spare electronics behind the habitat, rover body, or a regolith berm. Mass shields. Shade does not.")
        else:
            steps.append("No storm shelter is set. Stop an EVA and wait until GOES protons drop under the S1 line of 10 pfu.")
        steps.append("Leave a power margin. Arrays weaken after a flare, and dust on the panels makes that worse.")
    else:
        steps = [f"No storm step right now. Keep the normal plan for {who}."]
    if temperature_c is not None:
        if temperature_c >= 80:
            steps.append("The ground is hot. Clear dust from radiators and limit time on sunlit metal.")
        elif temperature_c <= -80:
            steps.append("The ground is in night cold. Finish the drive and turn survival heaters on before sunset.")
    return steps[:4]


def build_environment(lat, lon, when=None, proton_records=None, proton_error=None):
    moment = when or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    protons = None
    error = proton_error
    if proton_records is not None and error is None:
        try:
            protons = latest_proton_flux(proton_records)
        except ValueError as error_value:
            error = str(error_value)
    temperature = surface_temperature(lat, lon, moment)
    scale = protons["storm_scale"] if protons else "unknown"
    return {
        "timestamp_utc": moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "moonlight": reflected_irradiance(moment),
        "surface_radiation": {
            "live_lunar_sensor": False,
            "baseline_gcr_usv_hr": GCR_BASELINE_USV_HR,
            "baseline_source": "Chang'e-4 LND quiet-surface average, about 1.37 mSv per day.",
            "protons": protons,
            "proton_error": error,
        },
        "temperature": temperature,
        "protection": protection_steps(
            flare_probability=0.0,
            goes_class="",
            storm_scale=scale,
            sheltered="no",
            asset="rover",
            temperature_c=temperature["celsius"],
        ),
    }


def environment_for_site(lat, lon, when=None):
    """Live proton fetch plus the local temperature and moonlight estimates."""
    try:
        records = fetch_proton_records()
        return build_environment(lat, lon, when=when, proton_records=records)
    except (OSError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        return build_environment(lat, lon, when=when, proton_error=str(error))
