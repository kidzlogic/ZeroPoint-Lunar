"""Connect briefing answers to one traverse plan.

Earth height is the geometric elevation of Earth above a smooth horizon.
Sunlight is regional for the timestamp, not a permanently shadowed crater map.
Wheel-slip growth is an assumption. Crater matching is not run.
"""
import math

from night_power import plan_lunar_night

PRIORITIES = ("slope", "sun", "radio")
DRIVE_WATTS = {"rover": 180.0, "crew": 120.0, "both": 220.0}
HOTEL_WATTS = 80.0
SOLAR_OFFSET_WATTS = 120.0
BATTERY_WH = 1500.0
SLIP_FRACTION = 0.05
GCR_USV_HR = 57.0


def earth_elevation_degrees(lat, lon):
    """Elevation of Earth above a smooth lunar horizon. Negative means below it."""
    sine = math.cos(math.radians(lat)) * math.cos(math.radians(lon))
    return math.degrees(math.asin(max(-1.0, min(1.0, sine))))


def _number(value, fallback=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return number


def _samples(raw):
    samples = []
    if not isinstance(raw, list):
        return samples
    for item in raw[:400]:
        if not isinstance(item, dict):
            continue
        lat = _number(item.get("lat"))
        lon = _number(item.get("lon"))
        slope = _number(item.get("slope"), 0.0)
        if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        sample = {
            "lat": lat,
            "lon": lon,
            "slope": slope,
            "earth_elevation": round(earth_elevation_degrees(lat, lon), 1),
        }
        elevation = _number(item.get("elev_km"))
        if elevation is not None:
            sample["elev_km"] = elevation
        samples.append(sample)
    return samples


def score_site(samples, sun_up, sun_known, distance_km):
    """Score a pad-to-lower-ground pair. This is not a PSR or ice detection."""
    if len(samples) < 2:
        return {
            "verdict": "Set a flat pad and a lower, steeper neighbor, then the site screen can score the pair.",
            "pad_slope": None,
            "sun_state": "unknown",
            "neighbor": "unknown",
            "earth": None,
            "tether_km": distance_km,
            "candidate": False,
        }
    pad = samples[0]
    neighbor = samples[-1]
    pad_slope = pad["slope"]
    earth = pad["earth_elevation"]
    drop = None
    if "elev_km" in pad and "elev_km" in neighbor:
        drop = pad["elev_km"] - neighbor["elev_km"]
    pad_ok = pad_slope <= 5.0
    lower = drop is not None and drop >= 0.05
    steeper = neighbor["slope"] >= 12.0
    neighbor_ok = lower or steeper
    sun_state = "day" if sun_up else "night" if sun_known else "unknown"
    close = distance_km is not None and distance_km <= 30.0
    earth_ok = earth >= 5.0
    reasons = []
    if not pad_ok:
        reasons.append(f"The pad is {pad_slope:.1f}°. A habitat needs about 5° or less so it does not tip.")
    if sun_state == "night":
        reasons.append("The pad is in night at this time, so solar power is not available.")
    elif sun_state == "unknown":
        reasons.append("The Sun angle has not loaded.")
    if not neighbor_ok:
        reasons.append("The far end is not lower or steeper, so there is no colder-ground neighbor in this path.")
    if not earth_ok:
        reasons.append(f"Earth is {earth:.1f}° at the pad, too low for a reliable link.")
    if distance_km is None:
        reasons.append("Tether length is unknown.")
    elif not close:
        reasons.append(f"The neighbor is {distance_km:.1f} km away, past a 30 km tether.")
    candidate = pad_ok and sun_state == "day" and neighbor_ok and earth_ok and close
    if candidate:
        neighbor_text = "lower ground" if lower else "steeper ground"
        verdict = (
            f"Candidate pair. The pad is {pad_slope:.1f}°, the Sun is up, "
            f"{neighbor_text} is {distance_km:.1f} km away, and Earth is {earth:.1f}° high."
        )
    else:
        verdict = "Not a survival pair yet. " + " ".join(reasons)
    if lower:
        neighbor_label = f"{drop:.2f} km lower"
    elif steeper:
        neighbor_label = f"{neighbor['slope']:.1f}° steeper"
    else:
        neighbor_label = "no cold-ground neighbor"
    return {
        "verdict": verdict,
        "pad_slope": round(pad_slope, 1),
        "sun_state": sun_state,
        "neighbor": neighbor_label,
        "earth": earth,
        "tether_km": round(distance_km, 2) if distance_km is not None else None,
        "candidate": candidate,
    }


def build_mission_plan(payload):
    """One plan from the shared answers, the path samples, and the weather already loaded."""
    if not isinstance(payload, dict):
        raise ValueError("A JSON mission plan request is required.")
    priority = payload.get("priority", "slope")
    if priority not in PRIORITIES:
        raise ValueError("Priority must be slope, sun, or radio.")
    asset = payload.get("asset", "rover")
    if asset not in DRIVE_WATTS:
        asset = "rover"
    sheltered = payload.get("sheltered") == "yes"
    slope_limit = _number(payload.get("slope_limit"), 18.0)
    slope_limit = 18.0 if slope_limit is None else min(30.0, max(5.0, slope_limit))
    distance_km = _number(payload.get("distance_km"))
    speed_kmh = _number(payload.get("speed_kmh"), 0.5)
    if speed_kmh is None or speed_kmh <= 0:
        speed_kmh = 0.5
    samples = _samples(payload.get("samples"))
    sun_known = isinstance(payload.get("sun_up"), bool)
    sun_up = payload.get("sun_up") is True
    storm_scale = payload.get("storm_scale") or "unknown"
    if storm_scale not in {"quiet", "S1", "S2", "S3", "S4", "S5", "unknown"}:
        storm_scale = "unknown"
    goes_class = str(payload.get("goes_class") or "")
    xray_storm = len(goes_class) > 1 and goes_class[0] in {"M", "X"} and goes_class[1].isdigit()
    flare_probability = _number(payload.get("flare_probability"), 0.0) or 0.0
    flare_probability = min(1.0, max(0.0, flare_probability))
    photo_fix = payload.get("photo_fix") is True
    route_cleared = payload.get("route_cleared") is True

    slopes = [sample["slope"] for sample in samples]
    earth = [sample["earth_elevation"] for sample in samples]
    max_slope = max(slopes) if slopes else None
    min_earth = min(earth) if earth else None
    over_limit = sum(value > slope_limit for value in slopes)
    radio_ok = sum(value >= 5.0 for value in earth)
    hours = (distance_km / speed_kmh) if distance_km and distance_km > 0 else None
    drive_watts = DRIVE_WATTS[asset] + HOTEL_WATTS - (SOLAR_OFFSET_WATTS if sun_up else 0.0)
    drive_watts = max(40.0, drive_watts)
    battery_hours = BATTERY_WH / drive_watts
    dose_msv = round(hours * GCR_USV_HR / 1000.0, 3) if hours is not None else None
    if photo_fix:
        uncertainty_km = 0.05
        localization = "A photo coordinate is the position fix. Wheel slip is not being integrated, and crater matching is not running."
    elif distance_km:
        uncertainty_km = round(distance_km * SLIP_FRACTION, 2)
        localization = (
            f"No photo fix and no lunar GPS. A 5% wheel-slip allowance puts the rover within about {uncertainty_km} km. "
            "Crater matching is not running."
        )
    else:
        uncertainty_km = None
        localization = "Position uncertainty appears after a path distance is known. Crater matching is not running."

    storm = storm_scale not in {"quiet", "unknown"} or xray_storm or flare_probability >= 0.5
    if not storm:
        shelter = "No radiation stop. The same path stays in the plan."
    elif sheltered:
        shelter = "A storm step is on. Stop and put the chosen mass between the crew or hardware and the Sun. This is not a mapped lava tube."
    else:
        shelter = "A storm step is on, and this plan has no shelter. Do not start the traverse."

    if priority == "slope":
        if not samples:
            decision = "Slope is first. The path has not loaded, so the climb limit is not applied yet."
        elif route_cleared and over_limit == 0:
            decision = f"Slope is first. This path stays at or under {slope_limit:.0f}°."
        else:
            decision = f"Slope is first. This path is not cleared at {slope_limit:.0f}°."
    elif priority == "sun":
        if not sun_known:
            decision = "Sunlight is first. The Sun angle for this site has not loaded."
        elif sun_up:
            decision = "Sunlight is first. The region is in day, so the battery plan includes a solar offset."
        else:
            decision = "Sunlight is first. The region is in night, so the battery carries the full load."
    else:
        if min_earth is None:
            decision = "Earth radio is first. The path has not loaded, so Earth height is unknown."
        elif min_earth >= 5:
            decision = f"Earth radio is first. The lowest Earth height on this path is {min_earth:.1f}°."
        else:
            decision = f"Earth radio is first. Earth drops to {min_earth:.1f}° on this path, near or below the horizon."

    who = {"rover": "the habitat", "crew": "the crew", "both": "the crew and the habitat"}[asset]
    links = {
        "mission": decision,
        "path": f"Path board uses the {slope_limit:.0f}° limit from the questions for {who}.",
        "dust": "Dust board screens this same path. A plume check still needs a corridor you enter.",
        "solar": shelter,
        "radiation": (
            f"Quiet-surface dose along this drive is {dose_msv} mSv."
            if dose_msv is not None
            else "Radiation dose uses the drive time from this path once the path loads."
        ),
        "temperature": (
            "Temperature board uses the start of this same path."
            + (" The region is in daylight." if sun_up else " The region is in night." if sun_known else "")
        ),
    }
    if dose_msv is not None and storm_scale not in {"quiet", "unknown"}:
        links["radiation"] += " Proton storm dose is not added; the number stays the quiet Chang'e-4 rate."

    site = score_site(samples, sun_up, sun_known, distance_km)
    site_lat = samples[0]["lat"] if samples else _number(payload.get("lat"))
    power = None
    if site_lat is not None:
        power = plan_lunar_night(
            site_lat,
            night_low_c=_number(payload.get("night_low_c")),
            goes_class=str(payload.get("goes_class") or ""),
            max_slope=max_slope if max_slope is not None else _number(payload.get("slope_limit")),
        )
        links["mission"] = power["verdict"]
    else:
        links["mission"] = site["verdict"]
    return {
        "priority": priority,
        "decision": decision,
        "site": site,
        "power": power,
        "links": links,
        "shelter": shelter,
        "localization": localization,
        "telemetry": {
            "battery_hours": round(battery_hours, 1),
            "drive_hours": round(hours, 1) if hours is not None else None,
            "dose_msv": dose_msv,
            "max_slope_degrees": round(max_slope, 1) if max_slope is not None else None,
            "samples_over_slope_limit": over_limit,
            "min_earth_elevation_degrees": min_earth,
            "radio_samples_clear": radio_ok,
            "sample_count": len(samples),
            "sun_up": sun_up if sun_known else None,
            "uncertainty_km": uncertainty_km,
            "route_cleared": route_cleared,
        },
        "assumptions": (
            f"{BATTERY_WH:.0f} Wh battery, {DRIVE_WATTS[asset]:.0f} W motion plus {HOTEL_WATTS:.0f} W hotel load, "
            f"and {SOLAR_OFFSET_WATTS:.0f} W offset only while the region is in daylight. "
            "Earth height ignores local horizons. Sunlight is one angle for the whole route, not a PSR map."
        ),
    }
