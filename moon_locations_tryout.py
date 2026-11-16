"""
moon_locations_tryout.py - 3D views of multiple traced lunar locations.
"""
import pathlib
import urllib.request
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# ============================== TRACED LOCATIONS ==============================
LOCATIONS = [
    ("Target_Basin", 8.40651, 84.75701),          # Your custom target
    ("Mare_Tranquillitatis", 0.674, 23.472),     # Apollo 11 Landing Site (Safe Plain)
    ("Shackleton_Crater", -89.9, 0.0),            # South Pole Hazard / Crater Rim
]

RADIUS_KM = 50         # Area half-width
EXAGGERATION = 2.0     # Vertical exaggeration
MESH_POINTS = 300      # Resolution
TEXTURE = "4k"
ELEVATION = "16"
SUN_ELEVATION = 22.0
SUN_AZIMUTH = 300.0
IMAGE_SIZE = [1200, 700]
DATA_DIR = pathlib.Path.home() / "moon_data"
OUT_DIR = pathlib.Path.home() / "moon_captures"
# =======================================================================

BASE = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
R_MOON = 1737.4  # km

def download(url: str, dest: pathlib.Path):
    if dest.exists() and dest.stat().st_size > 0:
        return
    print(f"Downloading {dest.name}...")
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

def load_data(data_dir: pathlib.Path, tex: str, dem: str):
    tex_name = f"lroc_color_poles_{tex}.tif"
    dem_name = f"ldem_{dem}.tif"
    download(BASE + tex_name, data_dir / tex_name)
    download(BASE + dem_name, data_dir / dem_name)
    color = np.asarray(Image.open(data_dir / tex_name).convert("RGB"), dtype=np.float32)
    height = np.asarray(Image.open(data_dir / dem_name), dtype=np.float32)
    return color, height

def sample(img: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
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
    u = np.cross(n, e)
    return n, e, u

def build_patch(color, height, lat0, lon0, radius_km, n, exag):
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

    h = sample(height, lat, lon)
    rgb = np.clip(sample(color, lat, lon), 0, 255).astype(np.uint8)
    pts = d * (R_MOON + h * exag)[..., None]

    idx = np.arange(n * n).reshape(n, n)
    a, b, c_, d_ = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    tri1 = np.stack([np.full(a.shape, 3), a, b, c_], -1).reshape(-1, 4)
    tri2 = np.stack([np.full(a.shape, 3), a, c_, d_], -1).reshape(-1, 4)
    faces = np.vstack([tri1, tri2]).ravel()

    center_h = float(sample(height, np.array(lat0), np.array(lon0)))
    center = nrm * (R_MOON + center_h * exag)
    return pts.reshape(-1, 3), faces, rgb.reshape(-1, 3), center, (nrm, east, north), h

def render(pts, faces, rgb, center, frame, radius_km, out_prefix, size, sun_el, sun_az):
    import pyvista as pv

    nrm, east, north = frame
    mesh = pv.PolyData(pts, faces)
    mesh.point_data["rgb"] = rgb
    mesh.compute_normals(inplace=True, split_vertices=False)

    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background("black")
    pl.remove_all_lights()

    def horiz(az_deg):
        a = np.radians(az_deg)
        return np.cos(a) * north + np.sin(a) * east

    sun = np.cos(np.radians(sun_el)) * horiz(sun_az) + np.sin(np.radians(sun_el)) * nrm
    light = pv.Light(position=tuple(center + sun * radius_km * 20),
                     focal_point=tuple(center), light_type="scene light", intensity=1.0)
    pl.add_light(light)
    pl.add_mesh(mesh, scalars="rgb", rgb=True, smooth_shading=True, ambient=0.18, diffuse=0.95)
    pl.show(auto_close=False)

    views = [
        ("1_overhead", 89.0, 0.0, radius_km * 2.4),
        ("2_oblique", 45.0, 180.0, radius_km * 2.4),
        ("3_grazing", 18.0, 90.0, radius_km * 1.9),
    ]
    for name, el, az, dist in views:
        direction = np.cos(np.radians(el)) * horiz(az) + np.sin(np.radians(el)) * nrm
        cam_pos = center + direction * dist
        pl.camera_position = [tuple(cam_pos), tuple(center), tuple(nrm if el < 80 else north)]
        pl.camera.view_angle = 30
        pl.reset_camera_clipping_range()
        pl.render()
        path = f"{out_prefix}_{name}.png"
        pl.screenshot(path)
        print("  saved", path)
    pl.close()

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    color, height = load_data(DATA_DIR, TEXTURE, ELEVATION)

    for name, lat, lon in LOCATIONS:
        lon = round(((lon + 180) % 360) - 180, 4)
        print(f"\n=== Tracing Location: {name} (Lat {lat}, Lon {lon}) ===")
        pts, faces, rgb, center, frame, h = build_patch(
            color, height, lat, lon, RADIUS_KM, MESH_POINTS, EXAGGERATION)
        print(f"  Elevation range: {h.min() * 1000:.0f} to {h.max() * 1000:.0f} m")
        render(pts, faces, rgb, center, frame, RADIUS_KM,
               str(OUT_DIR / f"moon_{name}"), IMAGE_SIZE, SUN_ELEVATION, SUN_AZIMUTH)

    print(f"\nAll traced locations rendered successfully in {OUT_DIR}")

if __name__ == "__main__":
    main()