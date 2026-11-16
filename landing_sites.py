"""Pick a named landing site from the quiz using LOLA slope, Earth height, and sunlight.

The catalog is a short list of published places. The score uses this app's
elevation sample, the geometric height of Earth, and the smooth-Moon array
estimate. It is not a certified landing site.
"""
from mission_plan import earth_elevation_degrees
from night_power import plan_lunar_night
from terrain_engine import analyze_nearby_terrain

SITES = (
    {"name": "Shackleton rim", "lat": -89.5, "lon": 0.0, "band": "pole"},
    {"name": "Connecting Ridge", "lat": -89.45, "lon": -137.4, "band": "pole"},
    {"name": "Nobile", "lat": -85.4, "lon": 31.4, "band": "pole"},
    {"name": "Malapert", "lat": -84.9, "lon": 12.9, "band": "pole"},
    {"name": "East limb mare", "lat": 8.40651, "lon": 84.75701, "band": "equator"},
    {"name": "Taurus-Littrow", "lat": 20.1908, "lon": 30.7717, "band": "equator"},
)
ROCKETS = ("hopper", "crew", "cargo")
REGIONS = ("pole", "equator", "anywhere")
PRIORITIES = ("flat", "sun", "earth")
_METRICS = None


def _clamp(value):
    return max(0.0, min(100.0, value))


def measure_sites():
    """Sample each named site once. Later quizzes only reweight these numbers."""
    global _METRICS
    if _METRICS is not None:
        return _METRICS
    measured = []
    for site in SITES:
        ground = analyze_nearby_terrain(site["lat"], site["lon"], radius_km=8.0)
        earth = earth_elevation_degrees(site["lat"], site["lon"])
        power = plan_lunar_night(site["lat"])
        slope = float(ground["max_slope_degrees"] or 0.0)
        measured.append({
            **site,
            "slope": round(slope, 1),
            "earth": round(earth, 1),
            "peak_w": power["peak_tilt_w"],
            "night_days": power["night_days"],
            "flat": round(_clamp(100.0 - slope * 4.0), 1),
            "sun": round(_clamp(power["peak_tilt_w"] / 22.0), 1),
            "earth_score": round(_clamp((earth + 5.0) * 4.0), 1),
        })
    _METRICS = measured
    return measured


def _phrases(site):
    advantages = []
    cons = []
    if site["flat"] >= 60:
        advantages.append("Flatter than the other choices")
    else:
        cons.append("Slope is the problem")
    if site["sun"] >= 60:
        advantages.append("A tilted array still makes power")
    else:
        cons.append("Noon sun is weak")
    if site["earth_score"] >= 60:
        advantages.append("Earth stays up")
    else:
        cons.append("Earth sits near the horizon")
    if not advantages:
        advantages.append("Best match for this rocket and region")
    if not cons:
        cons.append("No single bar is failing")
    return advantages[:2], cons[:2]


def rank_sites(metrics, region, rocket, priority):
    """Weight already-measured sites. Region drops the other band when one remains."""
    if region not in REGIONS or rocket not in ROCKETS or priority not in PRIORITIES:
        raise ValueError("Choose a region, a rocket, and what the landing should favor.")
    pool = [dict(site) for site in metrics]
    if region != "anywhere":
        narrowed = [site for site in pool if site["band"] == region]
        if narrowed:
            pool = narrowed
    weights = {"hopper": {"flat": 1.5, "sun": 0.7, "earth": 0.6},
               "crew": {"flat": 1.0, "sun": 1.0, "earth": 1.4},
               "cargo": {"flat": 1.7, "sun": 0.8, "earth": 0.7}}[rocket]
    weights[priority] *= 1.6
    ranked = []
    for site in pool:
        score = (
            site["flat"] * weights["flat"]
            + site["sun"] * weights["sun"]
            + site["earth_score"] * weights["earth"]
        ) / sum(weights.values())
        advantages, cons = _phrases(site)
        ranked.append({
            **site,
            "score": round(score, 1),
            "bars": [
                {"label": "Flat", "value": site["flat"]},
                {"label": "Sun", "value": site["sun"]},
                {"label": "Earth", "value": site["earth_score"]},
            ],
            "advantages": advantages,
            "cons": cons,
        })
    ranked.sort(key=lambda site: site["score"], reverse=True)
    return ranked


def choose_landing(region, rocket, priority):
    ranked = rank_sites(measure_sites(), region, rocket, priority)
    winner = ranked[0]
    return {
        "winner": winner,
        "ranked": [
            {"name": site["name"], "lat": site["lat"], "lon": site["lon"], "score": site["score"]}
            for site in ranked
        ],
        "note": "Named places scored with LOLA slope, Earth height, and a smooth-Moon array. Not a certified landing site.",
    }
