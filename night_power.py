"""Power through one lunar day on a smooth Moon.

The Sun's path ignores mountains and crater shadows. A flat array and an
equator-tilted array are planning sizes, not hardware that has been built.
The 110 W steady source matches a published MMRTG-class electric output and
is a comparison, not equipment assigned to the site.
"""
import math

SYNODIC_HOURS = 29.530588853 * 24.0
SOLAR_WM2 = 1361.0
PANEL_EFFICIENCY = 0.22
ARRAY_M2 = 8.0
DUST_KEEP = 0.85
STORM_KEEP = 0.90
PACK_WH_PER_KG = 150.0
DEPTH_OF_DISCHARGE = 0.80
CHARGE_EFFICIENCY = 0.85
KEEP_ALIVE_W = 100.0
WARM_BOX_W = 80.0
FULL_HEAT_W = 600.0
STEADY_W = 110.0
STEPS = 49


def _clamp_lat(lat):
    return max(-89.0, min(89.0, float(lat)))


def _series(lat):
    lat = _clamp_lat(lat)
    hours, elevation, flat, tilt = [], [], [], []
    base = ARRAY_M2 * SOLAR_WM2 * PANEL_EFFICIENCY
    for index in range(STEPS):
        hour = -math.pi + (2.0 * math.pi * index / (STEPS - 1))
        elapsed = SYNODIC_HOURS * index / (STEPS - 1)
        sine = math.cos(math.radians(lat)) * math.cos(hour)
        angle = math.degrees(math.asin(max(-1.0, min(1.0, sine))))
        hours.append(elapsed)
        elevation.append(angle)
        flat.append(base * max(0.0, sine))
        tilt.append(base * max(0.0, math.cos(hour)))
    return hours, elevation, flat, tilt


def _integrate(values):
    step = SYNODIC_HOURS / (STEPS - 1)
    total = 0.0
    for index in range(STEPS - 1):
        total += 0.5 * (values[index] + values[index + 1]) * step
    return total


def _pack(load_w, night_hours):
    watt_hours = load_w * night_hours / DEPTH_OF_DISCHARGE
    return watt_hours, watt_hours / PACK_WH_PER_KG


def _closes(day_watt, day_hours, night_load, night_hours, keep):
    produced = _integrate([value * keep for value in day_watt])
    surplus = max(0.0, produced - KEEP_ALIVE_W * day_hours) * CHARGE_EFFICIENCY
    needed, mass = _pack(night_load, night_hours)
    return surplus >= needed, surplus, needed, mass


def plan_lunar_night(lat, night_low_c=None, goes_class="", max_slope=None):
    """Compare four ways to keep a site through one lunar night."""
    hours, elevation, flat, tilt = _series(lat)
    night_flag = [1.0 if angle <= 0 else 0.0 for angle in elevation]
    night_hours = _integrate(night_flag)
    day_hours = SYNODIC_HOURS - night_hours
    cold = night_low_c is None or night_low_c < -80
    hibernate_w = KEEP_ALIVE_W + (WARM_BOX_W if cold else 0.0)
    full_w = KEEP_ALIVE_W + FULL_HEAT_W
    storm = str(goes_class).startswith(("M", "X"))
    keep = DUST_KEEP * (STORM_KEEP if storm else 1.0)
    flat_ok, flat_store, hibernate_need, hibernate_mass = _closes(
        flat, day_hours, hibernate_w, night_hours, keep
    )
    tilt_ok, tilt_store, _, _ = _closes(tilt, day_hours, hibernate_w, night_hours, keep)
    full_ok, _, full_need, full_mass = _closes(flat, day_hours, full_w, night_hours, keep)
    steady_for_hibernate = int(math.ceil(hibernate_w / STEADY_W))
    steady_for_heat = int(math.ceil(full_w / STEADY_W))
    if tilt_ok and flat_ok:
        best = "Hibernate on solar power and a battery. A flat array can refill it here."
    elif tilt_ok:
        best = "Tilt the array toward the equator, then hibernate on a battery."
    else:
        best = "The day is too weak to refill a battery. A steady source has to carry the night."
    night_days = night_hours / 24.0
    options = [
        {
            "name": "Solar only",
            "works": False,
            "line": f"Blackout for {night_days:.1f} days. A panel makes nothing while the Sun is down.",
        },
        {
            "name": "Flat array + hibernation battery",
            "works": flat_ok,
            "line": (
                f"An 8 m² flat array peaks near {max(flat) * keep:.0f} W. "
                f"The night battery is about {hibernate_need / 1000:.0f} kWh "
                f"({hibernate_mass:.0f} kg at {PACK_WH_PER_KG:.0f} Wh/kg). "
                + ("The day can refill it." if flat_ok else "The day cannot refill it.")
            ),
        },
        {
            "name": "Tilted array + hibernation battery",
            "works": tilt_ok,
            "line": (
                f"Tilt the same array toward the equator by {abs(_clamp_lat(lat)):.0f}°. "
                f"Noon output rises to about {max(tilt) * keep:.0f} W. "
                + ("The day can refill the same battery." if tilt_ok else "Even tilted, the day cannot refill it.")
            ),
        },
        {
            "name": "Steady source",
            "works": True,
            "line": (
                f"A published {STEADY_W:.0f} W source (MMRTG class) covers the {KEEP_ALIVE_W:.0f} W keep-alive. "
                f"The warm box needs {steady_for_hibernate} of them. "
                f"Full habitat heat needs {steady_for_heat}. This is a comparison, not hardware on the lander."
            ),
        },
    ]
    do = [
        "At sunset, turn driving and science off. Keep 100 W alive and, in this cold, an 80 W warm box.",
        f"Tilt the array {abs(_clamp_lat(lat)):.0f}° toward the equator so the low noon sun still lands on the cells.",
        f"Size the battery for the {night_days:.1f}-day night, about {hibernate_need / 1000:.0f} kWh, not for the drive.",
    ]
    if isinstance(max_slope, (int, float)) and max_slope > 10:
        do.append(f"Keep the array off steps near the {max_slope:.0f}° limit. Use the flatter end of the path.")
    if storm:
        do.append("GOES is at M or X. This plan already takes another 10% off the array.")
    cannot = [
        "Solar panels alone cannot cross the night. There is no output when the Sun is below the horizon.",
        f"One {STEADY_W:.0f} W steady source cannot run a {FULL_HEAT_W:.0f} W habitat heater.",
        (
            "Full habitat heat asks for about "
            f"{full_need / 1000:.0f} kWh and {full_mass:.0f} kg of battery"
            + ("." if not full_ok else ", and the flat array still has to refill it.")
        ),
        "This sunlight model is a smooth sphere. It cannot see a crater rim that stays lit, and it cannot see a shadow inside a crater.",
        "LOLA here is about 1.9 km per pixel, so the picture and the height map are the region, not a place to bolt a panel.",
    ]
    curve = []
    for index in range(0, STEPS, 2):
        load = hibernate_w if elevation[index] <= 0 else KEEP_ALIVE_W
        curve.append({
            "hour": round(hours[index], 1),
            "elev": round(elevation[index], 1),
            "flat_w": round(flat[index] * keep),
            "tilt_w": round(tilt[index] * keep),
            "load_w": round(load),
        })
    return {
        "best": best,
        "verdict": best,
        "night_days": round(night_days, 1),
        "day_days": round(day_hours / 24.0, 1),
        "peak_flat_w": round(max(flat) * keep),
        "peak_tilt_w": round(max(tilt) * keep),
        "battery_kwh": round(hibernate_need / 1000.0, 1),
        "battery_kg": round(hibernate_mass),
        "hibernate_w": round(hibernate_w),
        "full_heat_w": round(full_w),
        "steady_w": STEADY_W,
        "flat_stores_kwh": round(flat_store / 1000.0, 1),
        "tilt_stores_kwh": round(tilt_store / 1000.0, 1),
        "options": options,
        "do": do,
        "cannot": cannot,
        "curve": curve,
        "note": (
            f"{ARRAY_M2:.0f} m² array, {PANEL_EFFICIENCY:.0%} cells, 1,361 W/m², "
            f"and a {int((1 - DUST_KEEP) * 100)}% dust loss. "
            "Night length is half a synodic month on a smooth Moon. Crater shadows are not included."
        ),
    }
