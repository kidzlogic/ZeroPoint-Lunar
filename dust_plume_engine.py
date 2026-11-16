"""Geometric screening of a user-supplied lunar plume corridor against a route."""
import math


MOON_RADIUS_KM = 1737.4
MAX_ROUTE_POINTS = 10000


def _number(name, value, minimum, maximum):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    try:
        numeric_value = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.") from None
    if (
        not math.isfinite(numeric_value)
        or numeric_value < minimum
        or numeric_value > maximum
    ):
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return numeric_value


def _coordinate(name, value, minimum, maximum):
    return _number(name, value, minimum, maximum)


def _local_coordinates(source, point):
    source_lat, source_lon = map(math.radians, source)
    point_lat, point_lon = map(math.radians, point)
    delta_lon = (point_lon - source_lon + math.pi) % (2 * math.pi) - math.pi
    sin_half_lat = math.sin((point_lat - source_lat) / 2)
    sin_half_lon = math.sin(delta_lon / 2)
    haversine = (
        sin_half_lat * sin_half_lat
        + math.cos(source_lat) * math.cos(point_lat) * sin_half_lon * sin_half_lon
    )
    haversine = max(0.0, min(1.0, haversine))
    central_angle = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(max(0.0, 1.0 - haversine)),
    )
    distance = MOON_RADIUS_KM * central_angle
    if distance == 0:
        return 0.0, 0.0
    bearing = math.atan2(
        math.sin(delta_lon) * math.cos(point_lat),
        math.cos(source_lat) * math.sin(point_lat)
        - math.sin(source_lat) * math.cos(point_lat) * math.cos(delta_lon),
    )
    return distance * math.sin(bearing), distance * math.cos(bearing)


def _point_to_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    fraction = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / length_squared,
        ),
    )
    closest = (start[0] + fraction * dx, start[1] + fraction * dy)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _point_to_rectangle_distance(point, length_km, half_width_km):
    along = max(0.0, min(length_km, point[0]))
    cross = max(-half_width_km, min(half_width_km, point[1]))
    return math.hypot(point[0] - along, point[1] - cross)


def _segment_intersects_rectangle(start, end, length_km, half_width_km):
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    boundaries = (
        (-dx, start[0]),
        (dx, length_km - start[0]),
        (-dy, start[1] + half_width_km),
        (dy, half_width_km - start[1]),
    )
    for direction, distance in boundaries:
        if abs(direction) < 1e-12:
            if distance < 0:
                return False
            continue
        fraction = distance / direction
        if direction < 0:
            if fraction > upper:
                return False
            lower = max(lower, fraction)
        else:
            if fraction < lower:
                return False
            upper = min(upper, fraction)
    return True


def _destination_point(origin, bearing_degrees, distance_km):
    latitude, longitude = map(math.radians, origin)
    bearing = math.radians(bearing_degrees)
    angular_distance = distance_km / MOON_RADIUS_KM
    destination_latitude = math.asin(
        math.sin(latitude) * math.cos(angular_distance)
        + math.cos(latitude) * math.sin(angular_distance) * math.cos(bearing)
    )
    destination_longitude = longitude + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(latitude),
        math.cos(angular_distance)
        - math.sin(latitude) * math.sin(destination_latitude),
    )
    return [
        math.degrees(destination_latitude),
        (math.degrees(destination_longitude) + 180) % 360 - 180,
    ]


def screen_route_against_plume_corridor(
    route_lat_lon,
    source_latitude,
    source_longitude,
    axis_azimuth_degrees,
    downrange_extent_km,
    cross_track_half_width_km,
    evidence_source="",
):
    """Test route segments against a user-entered rectangular plume envelope."""
    source = (
        _coordinate("source_latitude", source_latitude, -90, 90),
        _coordinate("source_longitude", source_longitude, -180, 180),
    )
    azimuth = _coordinate("axis_azimuth_degrees", axis_azimuth_degrees, 0, 360)
    extent = _number("downrange_extent_km", downrange_extent_km, 0.001, 500)
    half_width = _number(
        "cross_track_half_width_km", cross_track_half_width_km, 0.001, 100
    )
    if not isinstance(route_lat_lon, list) or not 2 <= len(route_lat_lon) <= MAX_ROUTE_POINTS:
        raise ValueError(
            f"route_lat_lon must contain between 2 and {MAX_ROUTE_POINTS} points."
        )
    if not isinstance(evidence_source, str) or len(evidence_source) > 240:
        raise ValueError("evidence_source must be a string of at most 240 characters.")

    route = []
    for index, point in enumerate(route_lat_lon):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"route_lat_lon[{index}] must be a latitude/longitude pair.")
        route.append(
            (
                _coordinate(f"route_lat_lon[{index}].latitude", point[0], -90, 90),
                _coordinate(f"route_lat_lon[{index}].longitude", point[1], -180, 180),
            )
        )

    azimuth_radians = math.radians(azimuth)
    route_xy = []
    for point in route:
        east, north = _local_coordinates(source, point)
        route_xy.append(
            (
                east * math.sin(azimuth_radians)
                + north * math.cos(azimuth_radians),
                east * math.cos(azimuth_radians)
                - north * math.sin(azimuth_radians),
            )
        )

    corners = (
        (0.0, -half_width),
        (0.0, half_width),
        (extent, -half_width),
        (extent, half_width),
    )
    intersecting_segments = 0
    minimum_separation = math.inf
    for start, end in zip(route_xy, route_xy[1:]):
        if _segment_intersects_rectangle(start, end, extent, half_width):
            intersecting_segments += 1
            minimum_separation = 0.0
            continue
        minimum_separation = min(
            minimum_separation,
            _point_to_rectangle_distance(start, extent, half_width),
            _point_to_rectangle_distance(end, extent, half_width),
            *(
                _point_to_segment_distance(corner, start, end)
                for corner in corners
            ),
        )

    points_inside = sum(
        0 <= point[0] <= extent and abs(point[1]) <= half_width
        for point in route_xy
    )
    source_bearing = azimuth
    left_bearing = source_bearing - 90
    right_bearing = source_bearing + 90
    polygon = [
        _destination_point(source, left_bearing, half_width),
        _destination_point(
            _destination_point(source, source_bearing, extent),
            left_bearing,
            half_width,
        ),
        _destination_point(
            _destination_point(source, source_bearing, extent),
            right_bearing,
            half_width,
        ),
        _destination_point(source, right_bearing, half_width),
    ]
    polygon.append(polygon[0])

    overlaps = intersecting_segments > 0
    return {
        "model": "user-defined plume corridor / route intersection screen",
        "version": "1.0",
        "overlap": overlaps,
        "route_points_screened": len(route),
        "route_points_inside_envelope": points_inside,
        "route_segments_intersecting_envelope": intersecting_segments,
        "minimum_route_separation_km": round(minimum_separation, 3),
        "evidence_source": evidence_source.strip(),
        "envelope": {
            "source_latitude": source[0],
            "source_longitude": source[1],
            "axis_azimuth_degrees": azimuth % 360,
            "downrange_extent_km": extent,
            "cross_track_half_width_km": half_width,
            "polygon_lat_lon": polygon,
        },
        "interpretation": (
            "Candidate route geometrically intersects the entered corridor."
            if overlaps
            else "No geometric overlap with the entered corridor; this is not evidence of no dust exposure."
        ),
        "limitations": [
            "The corridor is user-defined; this model does not predict plume generation, particle trajectories, or deposition.",
            "No dust concentration, exposure probability, or safe/unsafe certification is calculated.",
            "Results depend on the entered envelope and route geometry; use a validated plume simulation or observation as input.",
        ],
    }
