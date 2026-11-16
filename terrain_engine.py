"""Generate spherical local lunar terrain meshes and slope-aware traverse routes."""
import io
import pathlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
import os
import heapq
import math
from functools import lru_cache

Image.MAX_IMAGE_PIXELS = None
DATA_DIR = pathlib.Path.home() / "moon_data"
BASE_DATA_URL = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
R_MOON = 1737.4  # km
DEFAULT_RELIEF_EXAGGERATION = 2.0

def download_data(url: str, dest: pathlib.Path):
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.rename(dest)

@lru_cache(maxsize=1)
def load_moon_data():
    tex_name = "lroc_color_poles_4k.tif"
    dem_name = "ldem_16.tif"
    download_data(BASE_DATA_URL + tex_name, DATA_DIR / tex_name)
    download_data(BASE_DATA_URL + dem_name, DATA_DIR / dem_name)
    color = np.asarray(Image.open(DATA_DIR / tex_name).convert("RGB"), dtype=np.float32)
    height = np.asarray(Image.open(DATA_DIR / dem_name), dtype=np.float32)
    return color, height

@lru_cache(maxsize=1)
def load_moon_color():
    """Equirectangular LROC color map only. The elevation file stays out of this path."""
    tex_name = "lroc_color_poles_4k.tif"
    path = DATA_DIR / tex_name
    download_data(BASE_DATA_URL + tex_name, path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def moon_disk_jpeg(lat0: float, lon0: float, size: int = 640) -> bytes:
    """Orthographic LROC disk centered on the site. The site is the middle pixel."""
    size = int(max(256, min(int(size), 800)))
    cache_dir = DATA_DIR / "moon_disk"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{float(lat0):.2f}_{float(lon0):.2f}_{size}.jpg"
    if cached.exists() and cached.stat().st_size > 1000:
        return cached.read_bytes()
    color = load_moon_color()
    ys, xs = np.mgrid[0:size, 0:size]
    x = (xs + 0.5) / size * 2.0 - 1.0
    y = 1.0 - (ys + 0.5) / size * 2.0
    r2 = x * x + y * y
    visible = r2 <= 1.0
    z = np.zeros((size, size), dtype=np.float64)
    z[visible] = np.sqrt(np.maximum(0.0, 1.0 - r2[visible]))
    center, east, north = local_frame(float(lat0), float(lon0))
    px = east[0] * x + north[0] * y + center[0] * z
    py = east[1] * x + north[1] * y + center[1] * z
    pz = east[2] * x + north[2] * y + center[2] * z
    lat = np.degrees(np.arcsin(np.clip(pz, -1.0, 1.0)))
    lon = np.degrees(np.arctan2(py, px))
    sampled = sample_map(color, lat, lon)
    light = (0.72 + 0.28 * np.clip(z, 0.0, 1.0))[..., None]
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[visible] = np.clip(sampled[visible] * light[visible], 0, 255).astype(np.uint8)
    image = Image.fromarray(rgb, "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86)
    blob = buffer.getvalue()
    cached.write_bytes(blob)
    return blob


def sample_map(img: np.ndarray, lat: np.ndarray, lon: np.ndarray):
    h, w = img.shape[:2]
    x = (lon + 180.0) / 360.0 * w - 0.5
    y = (90.0 - lat) / 180.0 * h - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = x - x0
    fy = y - y0
    x0m, x1m = x0 % w, (x0 + 1) % w
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    top = img[y0c, x0m] * (1 - fx) + img[y0c, x1m] * fx
    bot = img[y1c, x0m] * (1 - fx) + img[y1c, x1m] * fx
    return top * (1 - fy) + bot * fy

def local_frame(lat0: float, lon0: float):
    p, l = np.radians(lat0), np.radians(lon0)
    n = np.array([np.cos(p) * np.cos(l), np.cos(p) * np.sin(l), np.sin(p)])
    e = np.array([-np.sin(l), np.cos(l), 0.0])
    return n, e, np.cross(n, e)


def local_to_latlon(east_km: float, north_km: float, lat0: float, lon0: float):
    """Inverse of project_to_local. East and north are kilometers on the tangent plane."""
    center, east, north = local_frame(lat0, lon0)
    offset = east * east_km + north * north_km
    distance = float(np.linalg.norm(offset))
    if distance == 0:
        return float(lat0), float(lon0)
    angle = distance / R_MOON
    direction = center * math.cos(angle) + (offset / distance) * math.sin(angle)
    lat = float(np.degrees(np.arcsin(np.clip(direction[2], -1.0, 1.0))))
    lon = float(np.degrees(np.arctan2(direction[1], direction[0])))
    return lat, lon


TREK_WAC = (
    "https://trek.nasa.gov/tiles/Moon/EQ/"
    "LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg"
)


def _trek_tile(zoom, tile_y, tile_x):
    """One cached Moon Trek LRO WAC tile, or None when Trek has no tile there."""
    folder = DATA_DIR / "trek_wac"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{zoom}_{tile_y}_{tile_x}.jpg"
    if not path.exists() or path.stat().st_size == 0:
        url = TREK_WAC.format(z=zoom, y=tile_y, x=tile_x)
        last_error = None
        for _ in range(3):
            try:
                download_data(url, path)
                last_error = None
                break
            except (OSError, urllib.error.URLError, urllib.error.HTTPError) as error:
                last_error = error
                if path.exists():
                    path.unlink()
        if last_error is not None:
            return None
    try:
        return np.asarray(Image.open(path).convert("RGB"))
    except (OSError, ValueError):
        return None


def moon_trek_patch(lat0: float, lon0: float, radius_km: float, size: int = 720):
    """North-up LRO WAC photo from Moon Trek, sampled on the local kilometer grid.

    Near a pole the equirectangular tiles wrap every longitude, so the patch
    stays on the tangent plane instead of stretching the crater into a band.
    """
    radius_km = float(max(4.0, min(radius_km, 80.0)))
    size = int(max(256, min(size, 900)))
    cache_dir = DATA_DIR / "path_basemap"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{float(lat0):.3f}_{float(lon0):.3f}_{radius_km:.1f}_{size}.jpg"
    meta = {
        "lat": round(float(lat0), 4),
        "lon": round(float(lon0), 4),
        "radius_km": round(radius_km, 2),
        "zoom": 8,
        "tiles": 0,
        "source": "NASA / USGS Moon Trek, LRO WAC global mosaic.",
    }
    if cached.exists() and cached.stat().st_size > 1000:
        return cached.read_bytes(), meta
    zoom = 8
    scale = 256 * (2 ** zoom)
    span = 2 ** zoom
    wide = span * 2
    axis = np.linspace(-radius_km, radius_km, size)
    east_km, north_km = np.meshgrid(axis, axis[::-1])
    center, east, north = local_frame(lat0, lon0)
    offset = east_km[..., None] * east + north_km[..., None] * north
    distance = np.linalg.norm(offset, axis=-1)
    angle = distance / R_MOON
    with np.errstate(invalid="ignore", divide="ignore"):
        direction = np.where(
            distance[..., None] > 0,
            offset / distance[..., None],
            0.0,
        )
    point = center * np.cos(angle)[..., None] + direction * np.sin(angle)[..., None]
    lat = np.degrees(np.arcsin(np.clip(point[..., 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(point[..., 1], point[..., 0]))
    pixel_x = (lon / 180.0 + 1.0) * scale
    pixel_y = (-lat / 180.0 + 0.5) * scale
    tile_x = np.floor(pixel_x / 256.0).astype(int) % wide
    tile_y = np.clip(np.floor(pixel_y / 256.0).astype(int), 0, span - 1)
    keys = {(int(y), int(x)) for y, x in zip(tile_y.ravel(), tile_x.ravel())}
    tiles = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        fetched = pool.map(lambda key: (key, _trek_tile(zoom, key[0], key[1])), keys)
        for key, image in fetched:
            if image is not None:
                tiles[key] = image
    picture = np.zeros((size, size, 3), dtype=np.uint8)
    for (row_index, col_index), image in tiles.items():
        mask = (tile_y == row_index) & (tile_x == col_index)
        if not np.any(mask):
            continue
        local_x = pixel_x[mask] - col_index * 256
        local_y = pixel_y[mask] - row_index * 256
        x0 = np.clip(np.floor(local_x).astype(int), 0, image.shape[1] - 2)
        y0 = np.clip(np.floor(local_y).astype(int), 0, image.shape[0] - 2)
        tx = np.clip(local_x - x0, 0.0, 1.0)[..., None]
        ty = np.clip(local_y - y0, 0.0, 1.0)[..., None]
        picture[mask] = (
            image[y0, x0] * (1 - tx) * (1 - ty)
            + image[y0, x0 + 1] * tx * (1 - ty)
            + image[y0 + 1, x0] * (1 - tx) * ty
            + image[y0 + 1, x0 + 1] * tx * ty
        )
    flat = picture.reshape(-1, 3).astype(np.float32)
    bright = flat[flat.sum(axis=1) > 8]
    if len(bright) > 32:
        low, high = np.percentile(bright, [1, 99])
        if high > low + 1:
            lifted = (picture.astype(np.float32) - low) * (210.0 / (high - low)) + 16
            picture = np.clip(lifted, 0, 255).astype(np.uint8)
    meta["tiles"] = len(tiles)
    meta["zoom"] = zoom
    encoded = io.BytesIO()
    Image.fromarray(picture, mode="RGB").save(encoded, format="JPEG", quality=86)
    payload = encoded.getvalue()
    cached.write_bytes(payload)
    return payload, meta


def project_to_local(lat: float, lon: float, lat0: float, lon0: float):
    """Project a lunar coordinate into the patch's east/north kilometer frame."""
    center, east, north = local_frame(lat0, lon0)
    p, l = np.radians(lat), np.radians(lon)
    point = np.array([np.cos(p) * np.cos(l), np.cos(p) * np.sin(l), np.sin(p)])
    angle = float(np.arccos(np.clip(np.dot(center, point), -1.0, 1.0)))
    tangent = point - np.dot(center, point) * center
    tangent_length = np.linalg.norm(tangent)
    if tangent_length == 0:
        return 0.0, 0.0
    distance = angle * R_MOON
    direction = tangent / tangent_length
    return float(np.dot(direction, east) * distance), float(np.dot(direction, north) * distance)


def calculate_slope(elevation: np.ndarray, spacing_km: float):
    dz_dy, dz_dx = np.gradient(elevation, spacing_km, spacing_km)
    return np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))


def calculate_roughness(elevation: np.ndarray):
    """Estimate multi-scale local relief after removing the neighborhood mean."""
    roughness = np.zeros_like(elevation, dtype=np.float32)
    for window_size in (3, 5):
        radius = window_size // 2
        padded = np.pad(elevation, radius, mode="edge")
        windows = np.lib.stride_tricks.sliding_window_view(
            padded, (window_size, window_size)
        )
        local_mean = windows.mean(axis=(-2, -1))
        roughness = np.maximum(roughness, np.abs(elevation - local_mean))
    return roughness


def summarize_path_screen(
    cells: list[tuple[int, int]],
    slopes: np.ndarray,
    roughness: np.ndarray,
    max_slope_degrees: float,
    distance_km: float,
):
    """Summarize sampled slope-limit exceedances along a candidate path."""
    if not cells:
        return {
            "sampled_cells": 0,
            "max_slope_degrees": None,
            "max_roughness_m": None,
            "above_slope_limit_samples": 0,
            "above_slope_limit_percent": 0.0,
            "distance_km": round(distance_km, 2),
        }
    path_slopes = [float(slopes[row, col]) for row, col in cells]
    path_roughness = [float(roughness[row, col]) for row, col in cells]
    above_limit = sum(value > max_slope_degrees for value in path_slopes)
    return {
        "sampled_cells": len(cells),
        "max_slope_degrees": round(max(path_slopes), 1),
        "max_roughness_m": round(max(path_roughness) * 1000, 1),
        "above_slope_limit_samples": above_limit,
        "above_slope_limit_percent": round(100 * above_limit / len(cells), 1),
        "distance_km": round(distance_km, 2),
    }


def _field_penalty(field: np.ndarray | None, cell: tuple[int, int], weight: float) -> float:
    """Turn a 0–1 desirability field into a step penalty (higher field = cheaper)."""
    if field is None or weight <= 0:
        return 0.0
    value = float(field[cell])
    if not math.isfinite(value):
        return weight
    return weight * (1.0 - max(0.0, min(1.0, value)))


def _normalize_field(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros_like(values, dtype=float)
    low = float(np.percentile(finite, 5))
    high = float(np.percentile(finite, 95))
    if high <= low:
        return np.zeros_like(values, dtype=float)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _priority_weights(path_priority: str) -> dict[str, float]:
    """Multi-objective A* weights for solar-to-ice traverse planning."""
    priority = (path_priority or "slope").strip().lower()
    if priority in {"sun", "sunlight", "power"}:
        return {"slope": 1.0, "rough": 0.35, "sun": 1.8, "ice": 0.55, "earth": 0.35}
    if priority in {"radio", "earth", "comms"}:
        return {"slope": 1.0, "rough": 0.4, "sun": 0.45, "ice": 0.35, "earth": 1.9}
    if priority in {"ice", "cold", "water"}:
        return {"slope": 1.05, "rough": 0.45, "sun": 0.4, "ice": 1.85, "earth": 0.3}
    return {"slope": 1.55, "rough": 0.55, "sun": 0.45, "ice": 0.55, "earth": 0.35}


def find_safe_route(
    slopes: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    spacing_km: float,
    max_slope_degrees: float = 18.0,
    roughness: np.ndarray | None = None,
    allow_over_limit: bool = False,
    path_priority: str = "slope",
    sun_field: np.ndarray | None = None,
    ice_field: np.ndarray | None = None,
    earth_field: np.ndarray | None = None,
):
    """Find a least-cost 8-connected path with multi-objective solar/ice/radio costs."""
    if not math.isfinite(max_slope_degrees) or max_slope_degrees <= 0:
        raise ValueError("The maximum slope must be a positive finite number.")
    rows, cols = slopes.shape
    if roughness is not None and roughness.shape != slopes.shape:
        raise ValueError("Slope and roughness grids must have the same shape.")
    for name, field in (
        ("sun_field", sun_field),
        ("ice_field", ice_field),
        ("earth_field", earth_field),
    ):
        if field is not None and field.shape != slopes.shape:
            raise ValueError(f"{name} must match the slope grid shape.")
    start_row, start_col = start
    goal_row, goal_col = goal
    if not (0 <= start_row < rows and 0 <= start_col < cols):
        raise ValueError("The start point is outside the terrain grid.")
    if not (0 <= goal_row < rows and 0 <= goal_col < cols):
        raise ValueError("The destination is outside the terrain grid.")

    weights = _priority_weights(path_priority)
    traversable = (
        np.ones(slopes.shape, dtype=bool)
        if allow_over_limit
        else slopes <= max_slope_degrees
    )
    if not allow_over_limit and (not traversable[start] or not traversable[goal]):
        raise ValueError("The start or destination cell exceeds the safe slope limit.")
    queue = [(0.0, start)]
    costs = {start: 0.0}
    previous = {}
    steps = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),             (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )

    while queue:
        _, current = heapq.heappop(queue)
        if current == goal:
            path = [goal]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return list(reversed(path))

        current_cost = costs[current]
        for drow, dcol in steps:
            neighbor = current[0] + drow, current[1] + dcol
            row, col = neighbor
            if not (0 <= row < rows and 0 <= col < cols):
                continue
            if not traversable[neighbor]:
                continue
            if drow and dcol and (
                not traversable[current[0] + drow, current[1]]
                or not traversable[current[0], current[1] + dcol]
            ):
                continue

            step_length = spacing_km * math.hypot(drow, dcol)
            grade = max(float(slopes[current]), float(slopes[neighbor]))
            grade_ratio = grade / max_slope_degrees
            grade_penalty = weights["slope"] * (grade_ratio ** 2)
            if allow_over_limit:
                excess_ratio = max(grade - max_slope_degrees, 0.0) / max_slope_degrees
                grade_penalty += 6.0 * excess_ratio ** 2
            roughness_penalty = 0.0
            if roughness is not None:
                local_roughness = max(
                    float(roughness[current]), float(roughness[neighbor])
                )
                roughness_penalty = (
                    weights["rough"] * min(local_roughness / 0.02, 1.0)
                )
            motive = (
                _field_penalty(sun_field, neighbor, weights["sun"])
                + _field_penalty(ice_field, neighbor, weights["ice"])
                + _field_penalty(earth_field, neighbor, weights["earth"])
            )
            # Soft turn penalty keeps the walk from zigzagging on flat ground.
            turn_penalty = 0.0
            if current in previous:
                prev = previous[current]
                prev_drow = current[0] - prev[0]
                prev_dcol = current[1] - prev[1]
                if (prev_drow, prev_dcol) != (drow, dcol):
                    turn_penalty = 0.08 * spacing_km
            step_cost = step_length * (1.0 + grade_penalty + roughness_penalty + motive)
            step_cost += turn_penalty
            new_cost = current_cost + step_cost
            if new_cost >= costs.get(neighbor, float("inf")):
                continue
            costs[neighbor] = new_cost
            previous[neighbor] = current
            heuristic = spacing_km * math.hypot(goal_row - row, goal_col - col)
            heapq.heappush(queue, (new_cost + heuristic, neighbor))

    raise ValueError(
        f"No route avoids terrain slopes above {max_slope_degrees:g} degrees."
    )


def generate_terrain_payload(
    lat0: float,
    lon0: float,
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
    radius_km: float,
    grid_size: int = 100,
    destination_is_shackleton: bool = False,
    max_slope_degrees: float = 18.0,
    path_priority: str = "slope",
):
    """Build a shaded 3D DEM mesh and a multi-objective solar-to-ice route."""
    if not math.isfinite(radius_km) or radius_km <= 0 or grid_size < 20:
        raise ValueError("Terrain radius must be positive and grid size at least 20.")
    if not math.isfinite(max_slope_degrees) or not 0 < max_slope_degrees < 90:
        raise ValueError("The maximum slope must be finite and between 0 and 90 degrees.")
    color, height = load_moon_data()

    axis = np.linspace(-radius_km, radius_km, grid_size)
    dx, dy = np.meshgrid(axis, axis)
    rho = np.hypot(dx, dy)
    angle = rho / R_MOON
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(rho > 0, np.sin(angle) / rho, 1.0 / R_MOON)

    center, east, north = local_frame(lat0, lon0)
    directions = (
        center[None, None, :] * np.cos(angle)[..., None]
        + (east[None, None, :] * dx[..., None] + north[None, None, :] * dy[..., None])
        * factor[..., None]
    )
    directions /= np.linalg.norm(directions, axis=-1, keepdims=True)
    latitudes = np.degrees(np.arcsin(np.clip(directions[..., 2], -1, 1)))
    longitudes = np.degrees(np.arctan2(directions[..., 1], directions[..., 0]))

    elevations = sample_map(height, latitudes, longitudes)
    colors = np.clip(sample_map(color, latitudes, longitudes), 0, 255).astype(np.uint8)
    spacing_km = float(axis[1] - axis[0])
    slopes = calculate_slope(elevations, spacing_km)
    roughness = calculate_roughness(elevations)
    complexity = (
        0.7 * np.clip(slopes / 18.0, 0.0, 1.0)
        + 0.3 * np.clip(roughness / 0.02, 0.0, 1.0)
    )
    # Solar shoulder proxy: higher local elevation tends to catch low polar Sun.
    sun_field = _normalize_field(elevations.astype(float))
    # Ice / cold-trap proxy: lower elevation + steeper local bowl.
    ice_field = _normalize_field(-elevations.astype(float) + 0.35 * roughness)
    # Earth-radio proxy: prefer equatorward latitude and higher standing ground.
    equatorward = -np.sign(lat0 or -1.0) * latitudes
    earth_field = _normalize_field(
        0.65 * equatorward.astype(float) + 0.35 * elevations.astype(float)
    )

    def grid_cell(lat: float, lon: float):
        x, y = project_to_local(lat, lon, lat0, lon0)
        col = int(round((x + radius_km) / spacing_km))
        row = int(round((y + radius_km) / spacing_km))
        if not (0 <= row < grid_size and 0 <= col < grid_size):
            raise ValueError("The route endpoints must fit inside the terrain patch.")
        return row, col

    start_cell = grid_cell(start_lat, start_lon)
    dest_cell = grid_cell(dest_lat, dest_lon)
    route_slopes = slopes.copy() if destination_is_shackleton else slopes
    if destination_is_shackleton:
        route_slopes[dest_cell] = max(float(route_slopes[dest_cell]), 19.0)

    def solve(priority: str, allow_over_limit: bool = False):
        return find_safe_route(
            route_slopes,
            start_cell,
            dest_cell,
            spacing_km,
            max_slope_degrees=max_slope_degrees,
            roughness=roughness,
            allow_over_limit=allow_over_limit,
            path_priority=priority,
            sun_field=sun_field,
            ice_field=ice_field,
            earth_field=earth_field,
        )

    route_message = None
    try:
        path = solve(path_priority)
    except ValueError as error:
        path = []
        route_message = str(error)
    advisory_path = []
    if not path:
        try:
            advisory_path = solve(path_priority, allow_over_limit=True)
        except ValueError:
            advisory_path = []
    elevation_offset = float(np.median(elevations))
    curvature = (R_MOON + elevation_offset) * (np.cos(angle) - 1.0)
    relief = (elevations - elevation_offset) * np.cos(angle)
    surface_x = (R_MOON + elevation_offset) * factor * dx
    surface_y = (R_MOON + elevation_offset) * factor * dy
    vertices = np.column_stack((
        surface_x.ravel(),
        surface_y.ravel(),
        (curvature + relief * DEFAULT_RELIEF_EXAGGERATION).ravel(),
    ))
    faces = []
    for row in range(grid_size - 1):
        for col in range(grid_size - 1):
            a = row * grid_size + col
            b, d = a + 1, a + grid_size
            c = d + 1
            faces.extend((a, b, c, a, c, d))

    def encode_path(cells):
        coordinates = []
        vertices = []
        route_relief = []
        route_elevation = []
        route_slope = []
        distance = 0.0
        for index, (row, col) in enumerate(cells):
            coordinates.append([float(latitudes[row, col]), float(longitudes[row, col])])
            route_relief.append(float(relief[row, col]))
            route_elevation.append(round(float(elevations[row, col]), 3))
            route_slope.append(round(float(slopes[row, col]), 1))
            vertices.extend((
                float(surface_x[row, col]),
                float(surface_y[row, col]),
                float(curvature[row, col] + relief[row, col] * DEFAULT_RELIEF_EXAGGERATION + 0.025),
            ))
            if index:
                previous_row, previous_col = cells[index - 1]
                distance += spacing_km * math.hypot(row - previous_row, col - previous_col)
        return coordinates, vertices, route_relief, distance, route_elevation, route_slope

    (
        route_latlon, route_vertices, route_relief, route_distance,
        route_elevation, route_slope,
    ) = encode_path(path)
    (
        advisory_latlon, advisory_vertices, advisory_relief, advisory_distance,
        advisory_elevation, advisory_slope,
    ) = encode_path(advisory_path)
    direct_steps = max(
        abs(dest_cell[0] - start_cell[0]),
        abs(dest_cell[1] - start_cell[1]),
        1,
    )
    direct_cells = list(dict.fromkeys(
        (
            int(round(start_cell[0] + (dest_cell[0] - start_cell[0]) * index / direct_steps)),
            int(round(start_cell[1] + (dest_cell[1] - start_cell[1]) * index / direct_steps)),
        )
        for index in range(direct_steps + 1)
    ))

    direct_distance = sum(
        spacing_km * math.hypot(row - previous_row, col - previous_col)
        for (previous_row, previous_col), (row, col) in zip(direct_cells, direct_cells[1:])
    )
    selected_path = path if path else advisory_path
    selected_distance = route_distance if path else advisory_distance
    selected_path_type = (
        "slope-constrained" if path else "least-risk-preview" if advisory_path else "unavailable"
    )

    def path_metrics(cells):
        if not cells:
            return {
                "mean_sun": None,
                "mean_ice": None,
                "mean_earth": None,
                "sun_km": 0.0,
                "ice_km": 0.0,
                "climb_m": None,
                "waypoints": [],
            }
        sun_vals = [float(sun_field[r, c]) for r, c in cells]
        ice_vals = [float(ice_field[r, c]) for r, c in cells]
        earth_vals = [float(earth_field[r, c]) for r, c in cells]
        elevs = [float(elevations[r, c]) for r, c in cells]
        sun_km = ice_km = 0.0
        for index in range(1, len(cells)):
            previous_row, previous_col = cells[index - 1]
            row, col = cells[index]
            seg = spacing_km * math.hypot(row - previous_row, col - previous_col)
            if float(sun_field[row, col]) >= 0.62:
                sun_km += seg
            if float(ice_field[row, col]) >= 0.62:
                ice_km += seg
        sun_idx = int(np.argmax(sun_vals))
        ice_idx = int(np.argmax(ice_vals))
        sun_row, sun_col = cells[sun_idx]
        ice_row, ice_col = cells[ice_idx]
        waypoints = [
            {
                "kind": "solar_shoulder",
                "index": sun_idx,
                "lat": float(latitudes[sun_row, sun_col]),
                "lon": float(longitudes[sun_row, sun_col]),
                "score": round(sun_vals[sun_idx], 3),
            },
            {
                "kind": "ice_approach",
                "index": ice_idx,
                "lat": float(latitudes[ice_row, ice_col]),
                "lon": float(longitudes[ice_row, ice_col]),
                "score": round(ice_vals[ice_idx], 3),
            },
        ]
        return {
            "mean_sun": round(float(np.mean(sun_vals)), 3),
            "mean_ice": round(float(np.mean(ice_vals)), 3),
            "mean_earth": round(float(np.mean(earth_vals)), 3),
            "sun_km": round(sun_km, 2),
            "ice_km": round(ice_km, 2),
            "climb_m": round((max(elevs) - min(elevs)) * 1000.0, 1),
            "waypoints": waypoints,
        }

    priority_key = (path_priority or "slope").strip().lower()
    priority_alias = {
        "sunlight": "sun",
        "power": "sun",
        "earth": "radio",
        "comms": "radio",
        "cold": "ice",
        "water": "ice",
    }
    selected_variant_id = priority_alias.get(priority_key, priority_key)
    route_variants = []
    for variant_id, label in (
        ("slope", "Slope-first"),
        ("sun", "Solar-first"),
        ("ice", "Ice-first"),
        ("radio", "Earth-radio"),
    ):
        if variant_id == selected_variant_id and (path or advisory_path):
            variant_cells = path or advisory_path
            cleared = bool(path)
        else:
            try:
                variant_cells = solve(variant_id)
                cleared = True
            except ValueError:
                try:
                    variant_cells = solve(variant_id, allow_over_limit=True)
                    cleared = False
                except ValueError:
                    variant_cells = []
                    cleared = False
        if not variant_cells:
            continue
        (
            variant_latlon, _, _, variant_distance, _, variant_slope,
        ) = encode_path(variant_cells)
        metrics = path_metrics(variant_cells)
        route_variants.append({
            "id": variant_id,
            "label": label,
            "cleared": cleared,
            "distance_km": round(variant_distance, 2),
            "max_slope_degrees": round(max(variant_slope), 1) if variant_slope else None,
            "route": variant_latlon,
            "metrics": metrics,
            "selected": variant_id == selected_variant_id,
        })

    selected_metrics = path_metrics(selected_path)
    route_assessment = {
        "slope_limit_degrees": max_slope_degrees,
        "grid_spacing_km": round(spacing_km, 2),
        "path_type": selected_path_type,
        "path_priority": (path_priority or "slope").strip().lower(),
        "objective_weights": _priority_weights(path_priority),
        "direct_line": summarize_path_screen(
            direct_cells,
            route_slopes,
            roughness,
            max_slope_degrees,
            direct_distance,
        ),
        "selected_path": summarize_path_screen(
            selected_path,
            route_slopes,
            roughness,
            max_slope_degrees,
            selected_distance,
        ),
        "multi_objective": selected_metrics,
        "source_resolution_note": (
            "LOLA LDEM 16 is about 1.9 km per pixel; interpolated grid samples do not "
            "resolve individual rocks or certify traversability. Sun/ice/Earth scores are "
            "DEM proxies, not illumination or ice detections."
        ),
    }

    hazard_spacing_cells = max(1, int(math.ceil(1.5 / spacing_km)))
    hazard_cells = np.argwhere((slopes >= 12.0) | (complexity >= 0.55))
    hottest_in_cell = {}
    for row, col in hazard_cells:
        cell = (int(row) // hazard_spacing_cells, int(col) // hazard_spacing_cells)
        if (
            cell not in hottest_in_cell
            or complexity[row, col] > complexity[hottest_in_cell[cell]]
        ):
            hottest_in_cell[cell] = (int(row), int(col))
    hazard_candidates = sorted(
        hottest_in_cell.values(),
        key=lambda cell: float(complexity[cell[0], cell[1]]),
        reverse=True,
    )[:240]
    hazards = []
    for row, col in hazard_candidates:
        slope = float(slopes[row, col])
        roughness_m = float(roughness[row, col] * 1000)
        footprint_radius = spacing_km * 0.7
        footprint = []
        for bearing in np.linspace(0, 2 * math.pi, 13):
            x = dx[row, col] + footprint_radius * math.cos(bearing)
            y = dy[row, col] + footprint_radius * math.sin(bearing)
            distance = math.hypot(x, y)
            arc = distance / R_MOON
            if distance == 0:
                direction = center
            else:
                direction = (
                    center * math.cos(arc)
                    + (east * x + north * y) * (math.sin(arc) / distance)
                )
            footprint.append([
                float(np.degrees(np.arcsin(np.clip(direction[2], -1, 1)))),
                float(np.degrees(np.arctan2(direction[1], direction[0]))),
            ])
        hazards.append({
            "lat": float(latitudes[row, col]),
            "lon": float(longitudes[row, col]),
            "slope": round(slope, 1),
            "roughness_m": round(roughness_m, 1),
            "complexity": round(float(complexity[row, col]) * 100, 1),
            "risk_level": "severe" if slope >= 30 else "high" if slope > 18 else "moderate",
            "kind": "DEM slope hotspot" if slope >= 12 else "DEM roughness hotspot",
            "footprint": footprint,
            "row": row,
            "col": col,
            "relief": float(relief[row, col]),
            "z": float(
                curvature[row, col]
                + relief[row, col] * DEFAULT_RELIEF_EXAGGERATION
                + 0.06
            ),
        })

    if destination_is_shackleton:
        shackleton_hazard = next(
            (item for item in hazards if item["row"] == dest_cell[0] and item["col"] == dest_cell[1]),
            None,
        )
        if shackleton_hazard is None:
            row, col = dest_cell
            shackleton_hazard = {
                "lat": float(latitudes[row, col]),
                "lon": float(longitudes[row, col]),
                "slope": round(float(slopes[row, col]), 1),
                "roughness_m": round(float(roughness[row, col] * 1000), 1),
                "complexity": round(float(complexity[row, col]) * 100, 1),
                "row": row,
                "col": col,
                "relief": float(relief[row, col]),
                "z": float(curvature[row, col] + relief[row, col] * DEFAULT_RELIEF_EXAGGERATION + 0.06),
                "footprint": [],
            }
            hazards.append(shackleton_hazard)
        shackleton_hazard["risk_level"] = "critical"
        shackleton_hazard["kind"] = "Shackleton provisional hazard"

    return {
        "center": [lat0, lon0],
        "radius_km": radius_km,
        "grid_size": grid_size,
        "path_priority": (path_priority or "slope").strip().lower(),
        "route": route_latlon,
        "route_available": bool(path),
        "route_message": route_message,
        "route_vertices": route_vertices,
        "route_relief": route_relief,
        "route_elevation_km": route_elevation,
        "route_slope_degrees": route_slope,
        "route_distance_km": round(route_distance, 2),
        "route_metrics": selected_metrics,
        "route_variants": route_variants,
        "advisory_route": advisory_latlon,
        "advisory_route_vertices": advisory_vertices,
        "advisory_route_relief": advisory_relief,
        "advisory_route_elevation_km": advisory_elevation,
        "advisory_route_slope_degrees": advisory_slope,
        "area_scan": _area_scan(latitudes, longitudes, elevations, slopes, grid_size),
        "advisory_distance_km": round(advisory_distance, 2),
        "route_assessment": route_assessment,
        "hazards": hazards,
        "hazard_counts": {
            "moderate": sum(item["risk_level"] == "moderate" for item in hazards),
            "high": sum(item["risk_level"] == "high" for item in hazards),
            "severe": sum(item["risk_level"] in {"severe", "critical"} for item in hazards),
        },
        "surface": {
            "vertices": np.round(vertices, 5).ravel().tolist(),
            "relief": np.round(relief, 5).ravel().tolist(),
            "colors": (colors.astype(np.float32) / 255.0).ravel().tolist(),
            "slopes": np.round(slopes.astype(float), 1).ravel().tolist(),
            "indices": faces,
        },
        "terrain": {
            "elevation_min_km": round(float(np.min(elevations)), 3),
            "elevation_max_km": round(float(np.max(elevations)), 3),
            "max_slope_degrees": round(float(np.max(slopes)), 1),
            "max_roughness_m": round(float(np.max(roughness) * 1000), 1),
            "mean_complexity": round(float(np.mean(complexity)) * 100, 1),
            "model": "DEM slope + multi-scale local-relief screening (not a probability)",
        },
    }


def analyze_nearby_terrain(lat0: float, lon0: float, radius_km: float = 10.0):
    """Summarize DEM-scale terrain near a supplied image location."""
    color, height = load_moon_data()
    del color
    grid_size = 11
    axis = np.linspace(-radius_km, radius_km, grid_size)
    dx, dy = np.meshgrid(axis, axis)
    rho = np.hypot(dx, dy)
    angle = rho / R_MOON
    center, east, north = local_frame(lat0, lon0)
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(rho > 0, np.sin(angle) / rho, 1.0 / R_MOON)
    directions = (
        center[None, None, :] * np.cos(angle)[..., None]
        + (east[None, None, :] * dx[..., None] + north[None, None, :] * dy[..., None])
        * factor[..., None]
    )
    directions /= np.linalg.norm(directions, axis=-1, keepdims=True)
    latitudes = np.degrees(np.arcsin(np.clip(directions[..., 2], -1, 1)))
    longitudes = np.degrees(np.arctan2(directions[..., 1], directions[..., 0]))
    elevations = sample_map(height, latitudes, longitudes)
    spacing_km = float(axis[1] - axis[0])
    slopes = calculate_slope(elevations, spacing_km)
    roughness = calculate_roughness(elevations)
    hot_cells = np.argwhere(slopes >= 12.0)
    nearby_hotspots = sorted(
        (
            {
                "lat": float(latitudes[row, col]),
                "lon": float(longitudes[row, col]),
                "slope": round(float(slopes[row, col]), 1),
            }
            for row, col in hot_cells
        ),
        key=lambda item: item["slope"],
        reverse=True,
    )[:3]
    low_cut = float(np.percentile(elevations, 30))
    dust_cells = sorted(
        (
            (int(row), int(col))
            for row, col in np.argwhere((elevations <= low_cut) & (slopes < 12.0))
        ),
        key=lambda cell: float(elevations[cell]),
    )
    dust_traps = [
        {
            "lat": float(latitudes[row, col]),
            "lon": float(longitudes[row, col]),
            "elev_km": round(float(elevations[row, col]), 3),
            "slope": round(float(slopes[row, col]), 1),
        }
        for row, col in dust_cells[:3]
    ]
    look = [
        {
            "elev_km": round(float(elevations[row, col]), 3),
            "slope": round(float(slopes[row, col]), 1),
        }
        for row in range(grid_size)
        for col in range(grid_size)
    ]
    return {
        "radius_km": radius_km,
        "grid_spacing_km": round(spacing_km, 2),
        "elevation_min_km": round(float(np.min(elevations)), 3),
        "elevation_max_km": round(float(np.max(elevations)), 3),
        "max_slope_degrees": round(float(np.max(slopes)), 1),
        "max_roughness_m": round(float(np.max(roughness) * 1000), 1),
        "slope_hotspots": nearby_hotspots,
        "dust_traps": dust_traps,
        "look": look,
        "resolution_note": "LDEM 16 is about 2 km per pixel; small rocks and boulders are unresolved.",
    }


def _area_scan(latitudes, longitudes, elevations, slopes, grid_size):
    """A small height sample for the dust cartoon. Capped so the page stays light."""
    step = max(1, (grid_size - 1) // 8)
    cells = []
    for row in range(0, grid_size, step):
        for col in range(0, grid_size, step):
            cells.append({
                "lat": round(float(latitudes[row, col]), 4),
                "lon": round(float(longitudes[row, col]), 4),
                "elev_km": round(float(elevations[row, col]), 3),
                "slope": round(float(slopes[row, col]), 1),
            })
            if len(cells) >= 81:
                return cells
    return cells


def generate_3d_mesh_renders(
    lat0,
    lon0,
    radius_km,
    out_prefix,
    upload_folder,
    incline_scale=2.0,
    mesh_points=300,
    image_size=(1600, 900),
    sun_elevation=22.0,
    sun_azimuth=300.0,
):
    color, height = load_moon_data()
    if color is None or height is None:
        return []

    n = mesh_points
    exag = float(incline_scale)
    nrm, east, north = local_frame(lat0, lon0)
    g = np.linspace(-radius_km, radius_km, n)
    dx, dy = np.meshgrid(g, g)
    rho = np.hypot(dx, dy)
    c = rho / R_MOON
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(rho > 0, np.sin(c) / rho, 1.0 / R_MOON)
    d = (nrm[None, None, :] * np.cos(c)[..., None]
         + (east[None, None, :] * dx[..., None] + north[None, None, :] * dy[..., None])
         * k[..., None])
    d /= np.linalg.norm(d, axis=-1, keepdims=True)

    lat = np.degrees(np.arcsin(np.clip(d[..., 2], -1, 1)))
    lon = np.degrees(np.arctan2(d[..., 1], d[..., 0]))

    h = sample_map(height, lat, lon)
    rgb = np.clip(sample_map(color, lat, lon), 0, 255).astype(np.uint8)
    pts = d * (R_MOON + h * exag)[..., None]

    idx = np.arange(n * n).reshape(n, n)
    a, b, c_, d_ = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    tri1 = np.stack([np.full(a.shape, 3), a, b, c_], -1).reshape(-1, 4)
    tri2 = np.stack([np.full(a.shape, 3), a, c_, d_], -1).reshape(-1, 4)
    faces = np.vstack([tri1, tri2]).ravel()

    center_h = float(sample_map(height, np.array(lat0), np.array(lon0)))
    center = nrm * (R_MOON + center_h * exag)

    try:
        import pyvista as pv
        mesh = pv.PolyData(pts.reshape(-1, 3), faces)
        mesh.point_data["rgb"] = rgb.reshape(-1, 3)
        mesh.compute_normals(inplace=True, split_vertices=False)

        pl = pv.Plotter(off_screen=True, window_size=list(image_size))
        pl.set_background("black")
        pl.remove_all_lights()

        def horiz(az_deg):
            a = np.radians(az_deg)
            return np.cos(a) * north + np.sin(a) * east

        sun = (
            np.cos(np.radians(sun_elevation)) * horiz(sun_azimuth)
            + np.sin(np.radians(sun_elevation)) * nrm
        )
        light = pv.Light(position=tuple(center + sun * radius_km * 18),
                         focal_point=tuple(center), light_type="scene light", intensity=1.1)
        pl.add_light(light)
        pl.add_mesh(mesh, scalars="rgb", rgb=True, smooth_shading=True, ambient=0.15, diffuse=0.98)
        pl.show(auto_close=False)

        views = [
            ("1_overhead", 89.0, 0.0, radius_km * 2.4),
            ("2_north_oblique", 45.0, 0.0, radius_km * 2.4),
            ("3_east_oblique", 45.0, 90.0, radius_km * 2.4),
            ("4_south_oblique", 45.0, 180.0, radius_km * 2.4),
            ("5_west_oblique", 45.0, 270.0, radius_km * 2.4),
            ("6_north_grazing", 18.0, 0.0, radius_km * 1.9),
            ("7_east_grazing", 18.0, 90.0, radius_km * 1.9),
            ("8_west_grazing", 18.0, 270.0, radius_km * 1.9),
        ]
        saved_paths = []
        for name, el, az, dist in views:
            direction = np.cos(np.radians(el)) * horiz(az) + np.sin(np.radians(el)) * nrm
            cam_pos = center + direction * dist
            pl.camera_position = [tuple(cam_pos), tuple(center), tuple(nrm if el < 80 else north)]
            pl.camera.view_angle = 30
            pl.reset_camera_clipping_range()
            pl.render()
            filename = f"{out_prefix}_{name}.png"
            full_path = os.path.join(upload_folder, filename)
            pl.screenshot(full_path)
            saved_paths.append(filename)
        pl.close()
        return saved_paths
    except Exception as e:
        print(f"3D Render Error: {e}")
        return []
