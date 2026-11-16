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
from clps_browser import compare_sites
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
﻿
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Zero-Point Lunar | Shackleton traverse</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap">
    <style>
        :root { color-scheme: dark; --bg:#070b12; --panel:#101822; --line:#253442; --muted:#91a5b6; --cyan:#53e0d0; --blue:#65a9ff; --amber:#f4bd65; --red:#ff6b73; }
        * { box-sizing:border-box; }
        body { margin:0; background:radial-gradient(ellipse at 50% -20%,#142638 0,#070b12 55%); color:#e4edf3; font:16px/1.6 "Segoe UI",Arial,sans-serif; }
        .shell { width:100%; min-height:100vh; margin:auto; padding:0; }
        .workspace { min-width:0; padding:12px 16px 18px; }
        header { display:flex; justify-content:space-between; align-items:center; gap:18px; min-height:56px; margin-bottom:10px; padding:7px 10px 12px; border-bottom:1px solid #123747; background:radial-gradient(ellipse at 82% 0%,#12303b 0,transparent 42%); }
        .brand { display:flex; align-items:center; gap:12px; min-width:290px; }
        .mission-patch { display:grid; place-items:center; width:43px; height:43px; border:1px solid #149bae; border-radius:50%; color:var(--cyan); background:#041923; }
        .mission-patch svg { width:36px; height:36px; }
        h1 { margin:0; font-size:21px; letter-spacing:2.2px; font-weight:750; }
        .mission-name { color:#b6c8d1; font-size:12px; }
        .mission-name strong { color:#4de3ed; }
        .subtitle,.eyebrow { color:var(--muted); font-size:11px; letter-spacing:1.6px; text-transform:uppercase; }
        .live { display:flex; align-items:center; gap:8px; border:1px solid #157c50; border-radius:5px; padding:7px 10px; color:#67f29a; font-size:11px; font-weight:700; letter-spacing:.8px; white-space:nowrap; }
        .live-dot { width:8px; height:8px; border-radius:50%; background:#4dff8d; box-shadow:0 0 10px #4dff8d; }
        .workflow-tabs { display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 12px; border-bottom:1px solid #153e4c; }
        .workflow-tabs button { border:1px solid transparent; border-bottom:0; border-radius:6px 6px 0 0; background:transparent; color:var(--muted); padding:10px 15px; }
        .workflow-tabs button[aria-selected="true"] { border-color:#157b90; background:#0b2833; color:#75f2f1; }
        .workflow-tabs button:focus-visible { outline:2px solid var(--cyan); outline-offset:2px; }
        .what-now-panel { margin-bottom:10px; }
        .decision-banner { margin-top:10px; border-left:4px solid var(--amber); border-radius:4px; padding:12px 14px; background:#241d0e; color:#f3dda9; font-weight:650; }
        .decision-banner.clear { border-color:#53d9a2; background:#0b211d; color:#d5f8e9; }
        .decision-banner.critical { border-color:#ff6b73; background:#291219; color:#ffdadd; }
        .next-steps { max-width:860px; margin-top:12px; color:#c8d6e0; }
        .next-steps li { margin:6px 0; padding-left:3px; }
        .now-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:10px; }
        .now-card { min-width:0; border:1px solid #264456; border-radius:6px; padding:10px; background:#07141e; }
        .now-card strong { display:block; margin-top:3px; color:#e8f4fa; font-size:14px; }
        .now-card small { color:var(--muted); }
        .mission-links { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
        .mission-links a { border:1px solid #176a7d; border-radius:4px; padding:6px 9px; color:var(--cyan); font-size:11px; text-decoration:none; }
        .mission-links a:hover { background:#06232d; }
        .metrics { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:8px; margin-bottom:10px; }
        .metric,.panel { background:linear-gradient(145deg,#071c26,#06131c); border:1px solid #125066; border-radius:9px; box-shadow:0 6px 24px #0005; }
        .metric { min-height:65px; display:flex; align-items:center; gap:11px; padding:9px 12px; }
        .metric-icon { color:#12d4e4; font-size:23px; line-height:1; }
        .metric strong { display:block; margin-top:2px; color:#e8f4fa; font-size:15px; font-weight:650; }
        .layout { display:grid; grid-template-columns:minmax(0,1fr) minmax(310px,360px); gap:10px; align-items:start; }
        .panel { min-width:0; padding:11px; }
        .panel-heading { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:12px; }
        h2 { margin:0; font-size:13px; font-weight:650; letter-spacing:.7px; }
        .tag { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:1px; }
        #map,.model-viewport { width:100%; height:360px; border:1px solid #14718a; border-radius:6px; background:#02090e; overflow:hidden; }
        #map { height:clamp(390px,58vh,680px); }
        .model-viewport { position:relative; }
        #terrain-canvas { display:block; width:100%; height:100%; }
        .model-status { position:absolute; inset:0; display:grid; place-items:center; padding:20px; color:var(--muted); text-align:center; pointer-events:none; }
        .model-status[hidden] { display:none; }
        .model-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-top:10px; color:var(--muted); font-size:11px; }
        .model-toolbar label { display:flex; align-items:center; gap:7px; }
        .model-toolbar input[type="checkbox"] { width:auto; accent-color:var(--cyan); }
        input[type="range"] { width:110px; accent-color:var(--cyan); }
        .legend { display:flex; flex-wrap:wrap; gap:14px; padding:9px 0 0; color:var(--muted); font-size:11px; }
        .legend span { display:flex; align-items:center; gap:6px; }
        .swatch { width:9px; height:9px; border-radius:50%; background:var(--cyan); }
        .swatch.green { background:#7be6a2; }
        .swatch.red { background:var(--red); }
        .swatch.yellow { background:#f4d35e; }
        .swatch.orange { background:#ff965e; }
        .swatch.purple { background:#b18bff; }
        .plume-swatch { width:16px; height:8px; border:1px dashed #c39cff; background:#b27dff55; }
        .direct-route-swatch { width:16px; height:0; border-top:1px dotted #a6b0b8; }
        .unsafe-route-swatch { width:16px; height:0; border-top:3px dashed #f4bd65; }
        .complexity-legend { display:flex; align-items:center; flex-wrap:wrap; gap:9px; margin-top:5px; }
        .complexity-gradient { width:min(240px,45vw); height:10px; border:1px solid #80909b; border-radius:8px; background:linear-gradient(90deg,#53e0d0 0%,#7be6a2 25%,#f4d35e 50%,#ff965e 75%,#ff6b73 100%); }
        form { margin-top:14px; }
        .form-grid { display:grid; grid-template-columns:1.1fr 1fr 1fr; gap:9px; }
        .field { min-width:0; }
        .field label { display:block; margin-bottom:4px; color:var(--muted); font-size:10px; letter-spacing:.7px; text-transform:uppercase; }
        input,textarea,select { width:100%; border:1px solid #34495b; border-radius:5px; background:#09111a; color:#e4edf3; padding:9px 10px; font:inherit; }
        input:focus,textarea:focus,select:focus { outline:1px solid var(--blue); border-color:var(--blue); }
        input[type="file"] { padding:7px; font-size:11px; }
        textarea { min-height:84px; resize:vertical; }
        .section-label { margin:14px 0 8px; color:#c8d6e0; font-size:11px; font-weight:600; letter-spacing:.8px; text-transform:uppercase; }
        .button-row { display:flex; gap:8px; margin-top:12px; }
        button { border:1px solid #369b9a; border-radius:5px; padding:10px 14px; background:#125552; color:#efffff; font-weight:650; letter-spacing:.4px; cursor:pointer; }
        button:hover { background:#176c68; }
        button:disabled { opacity:.55; cursor:not-allowed; }
        .calculate-button { width:100%; min-height:48px; border:1px solid #22d7e8; border-radius:7px; background:linear-gradient(180deg,#0eb7d2,#087992); color:#f4feff; font-weight:800; letter-spacing:1px; box-shadow:0 6px 20px #00b8d533; cursor:pointer; }
        .calculate-button:hover { background:linear-gradient(180deg,#22d9e8,#0b8da6); }
        .note,.result,.warning { margin-top:10px; border-radius:5px; padding:11px 12px; font-size:12px; }
        .note { border:1px solid #314457; background:#0b141e; color:var(--muted); }
        .result { border:1px solid #286353; background:#0b211d; color:#d5f8e9; }
        .warning { border:1px solid #765d37; background:#211a10; color:#f3d9aa; }
        .result strong,.warning strong { color:#fff; }
        .score-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:7px; }
        .score { border:1px solid #345363; border-radius:4px; padding:3px 7px; color:#cde4ee; font-size:11px; }
        .image-preview { display:grid; grid-template-columns:minmax(0,1.3fr) minmax(180px,.7fr); gap:12px; align-items:center; margin-top:10px; padding:10px; border:1px solid #31495a; border-radius:6px; background:#080d14; }
        .image-preview[hidden] { display:none; }
        .image-preview img { display:block; width:100%; max-height:260px; object-fit:contain; border-radius:4px; background:#05080c; }
        .image-preview img.enhanced { filter:contrast(1.12) brightness(1.04) saturate(.92); }
        .image-preview-copy { color:var(--muted); font-size:11px; }
        .image-preview-copy label { display:flex; align-items:center; gap:7px; margin-top:10px; }
        .image-preview-copy input { width:auto; accent-color:var(--cyan); }
        .source-links { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
        .source-links a { color:var(--cyan); }
        .error-banner { margin-bottom:12px; border:1px solid #9a4650; border-radius:6px; background:#281319; color:#ffdadd; padding:10px 12px; }
        .map .leaflet-popup-content-wrapper { background:#101822; color:#e4edf3; }
        .map .leaflet-popup-tip { background:#101822; }
        .leaflet-container { font:12px/1.4 "Segoe UI",Arial,sans-serif; }
        .leaflet-control-scale-line { border-color:#9eb3c1; background:#0b141ecc; color:#e4edf3; }
        .route-readout { display:flex; justify-content:space-between; gap:10px; margin-top:8px; color:var(--muted); font-size:11px; }
        .route-evidence { margin-top:8px; border:1px solid #264456; border-radius:5px; background:#07141e; }
        .route-evidence summary { padding:7px 9px; color:#79dfe6; cursor:pointer; font-size:10px; font-weight:700; letter-spacing:.5px; text-transform:uppercase; }
        .route-evidence-body { padding:0 9px 9px; }
        .route-evidence-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; }
        .route-evidence-grid div { min-width:0; border-top:1px solid #193646; padding-top:5px; }
        .route-evidence-grid small { display:block; color:var(--muted); font-size:9px; }
        .route-evidence-grid strong { display:block; margin-top:2px; color:#e7f6fb; font-size:12px; }
        .route-evidence-note { margin:7px 0 0; color:var(--muted); font-size:10px; }
        .console-header { align-items:center; }
        .map-heading { display:flex; align-items:center; gap:8px; }
        .map-heading svg { width:26px; height:26px; fill:none; stroke:#2be0ea; stroke-width:1.8; }
        .map-tools { display:flex; flex-wrap:wrap; gap:6px; }
        .map-tools button,.camera-arrow,.camera-dot { border:1px solid #176a7d; background:#061923; color:#d5faff; cursor:pointer; }
        .map-tools button { padding:6px 9px; font-size:10px; }
        .map-tools button[aria-pressed="false"] { color:#748b96; border-color:#31434b; }
        .camera-panel { padding:10px; }
        .camera-frame { position:relative; min-height:170px; aspect-ratio:16/9; overflow:hidden; border:1px solid #145168; border-radius:7px; background:radial-gradient(ellipse at 50% 80%,#29353b,#030b10 72%); }
        .camera-frame img { display:block; width:100%; height:100%; position:absolute; inset:0; object-fit:cover; }
        .camera-frame img[hidden] { display:none; }
        .camera-arrow { position:absolute; top:50%; z-index:2; width:32px; height:36px; transform:translateY(-50%); border-radius:5px; font-size:22px; }
        .camera-arrow.prev { left:7px; }
        .camera-arrow.next { right:7px; }
        .camera-status { position:absolute; inset:0; display:grid; place-content:center; padding:18px; color:#b9c9d0; text-align:center; font-size:11px; }
        .camera-status[hidden] { display:none; }
        .camera-meta { display:flex; justify-content:space-between; gap:8px; margin-top:8px; color:#91a5b6; font-size:10px; }
        .camera-dots { display:flex; justify-content:center; gap:7px; margin-top:8px; }
        .camera-dot { width:9px; height:9px; padding:0; border-radius:50%; }
        .camera-dot[aria-current="true"] { border-color:#55f4ff; background:#25e4ef; box-shadow:0 0 8px #21dbe8; }
        .status-list { display:grid; gap:7px; margin-top:7px; }
        .status-row { display:flex; align-items:center; justify-content:space-between; gap:10px; border-bottom:1px solid #15313d; padding:5px 2px; color:#bdccd3; font-size:11px; }
        .status-row strong { color:#ebf8fc; font-weight:600; text-align:right; }
        .status-good { color:#64f09b !important; }
        .alert-list { display:grid; gap:6px; }
        .alert-item { border:1px solid #66522b; border-radius:5px; padding:7px 8px; background:#211b0d; color:#f0d595; font-size:10px; }
        .alert-item.clear { border-color:#1b614b; background:#09231b; color:#9be7c0; }
        .alert-item.critical { border-color:#803b46; background:#291219; color:#ffb0b4; }
        .input-drawer { margin-top:14px; padding-top:9px; }
        .input-drawer summary { color:#51dce8; cursor:pointer; font-size:12px; font-weight:700; letter-spacing:.6px; text-transform:uppercase; }
        .target-note { color:#99adb8; font-size:10px; }
        .toolbar-button { border-radius:5px; }
        .camera-controls { display:flex; justify-content:center; gap:7px; margin-top:7px; }
        #terrain-model-panel { margin-top:10px; }
        #terrain-model-panel .model-viewport { height:480px; }
        .model-panel.is-expanded { position:fixed; z-index:2000; inset:16px; overflow:auto; background:#07111a; box-shadow:0 0 0 100vmax #000c; }
        #terrain-model-panel.is-expanded .model-viewport { height:min(78vh,1000px); }
        .waypoint-icon-wrap { background:transparent; border:0; }
        .waypoint-pin { display:grid; place-items:center; width:36px; height:36px; border:2px solid #fff; border-radius:50% 50% 50% 4px; transform:rotate(-45deg); box-shadow:0 2px 9px #000b; color:#06131b; font-size:13px; font-weight:900; }
        .waypoint-pin span { transform:rotate(45deg); }
        .waypoint-pin.start { background:#7be6a2; }
        .waypoint-pin.destination { background:#ff6b73; }
        .waypoint-pin.photo { background:#53e0d0; }
        .waypoint-pin.candidate { background:#b18bff; }
        .hazard-marker { filter:drop-shadow(0 1px 3px #000d); }
        .telemetry-disclaimer { margin-top:8px; color:#8196a1; font-size:10px; }
        @media(max-width:1050px) { .layout { grid-template-columns:minmax(0,1fr) 300px; } .workspace { padding:10px; } }
        @media(max-width:820px) { .layout { grid-template-columns:1fr; } .right-rail { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); align-items:start; gap:9px; } .right-rail .panel { margin:0; } .camera-panel { grid-row:span 2; } }
        @media(max-width:1000px) { .layout { grid-template-columns:1fr; } }
        @media(max-width:650px) { .workspace { padding:8px; } header { align-items:flex-start; flex-wrap:wrap; gap:8px; } .brand { min-width:0; } h1 { font-size:16px; } .mission-name { font-size:10px; } .workflow-tabs button { flex:1; padding:9px 5px; font-size:11px; } .metrics,.now-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .metric { padding:8px; } .layout { grid-template-columns:1fr; } .right-rail { display:flex; flex-direction:column; } .form-grid { grid-template-columns:1fr 1fr; } #map { height:360px; min-height:320px; } #terrain-model-panel .model-viewport { height:340px; } }
        html,body { height:100%; }
        body { overflow:hidden; }
        .shell { height:100vh; min-height:0; }
        .workspace { display:grid; grid-template-rows:auto auto minmax(0,1fr); gap:7px; height:100%; min-height:0; padding:7px 12px 10px; overflow:hidden; }
        .console-header { min-height:52px; margin:0; padding:3px 8px 7px; }
        .brand { min-width:0; }
        .mission-patch { display:block; width:48px; height:48px; flex:none; object-fit:cover; padding:0; }
        .mission-command { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:6px 12px; min-width:0; }
        .mission-directive { min-width:0; }
        .decision-banner { margin-top:3px; padding:7px 10px; font-size:12px; line-height:1.35; }
        .action-sequence { margin-top:4px; color:var(--muted); font-size:10px; }
        .action-sequence summary { width:max-content; cursor:pointer; color:#7edce5; }
        .action-sequence ol { margin:5px 0 0; padding-left:20px; }
        .action-sequence li { margin:2px 0; }
        .command-controls { display:flex; align-items:center; justify-content:flex-end; gap:6px; }
        .command-controls button { min-height:36px; padding:7px 10px; white-space:nowrap; font-size:11px; }
        .command-controls .calculate-button { width:auto; min-height:36px; }
        .error-banner { grid-column:1/-1; margin:0; }
        .system-drawer { grid-column:1/-1; color:var(--muted); }
        .system-drawer summary { width:max-content; cursor:pointer; color:#7edce5; font-size:10px; letter-spacing:.6px; text-transform:uppercase; }
        .system-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:6px; }
        .system-grid .panel { padding:8px 10px; }
        #mission-workflow { display:grid; grid-template-rows:auto minmax(0,1fr); gap:7px; min-height:0; overflow:hidden; }
        .metrics { gap:7px; margin:0; }
        .metric { min-height:48px; height:52px; gap:8px; padding:5px 8px; }
        .metric-icon { font-size:19px; }
        .metric strong { font-size:13px; }
        .eyebrow { font-size:9px; letter-spacing:1px; }
        .layout { grid-template-columns:minmax(0,1.55fr) minmax(320px,.82fr); gap:8px; min-height:0; height:100%; align-items:stretch; }
        #map-panel { display:flex; flex-direction:column; min-height:0; padding:9px; overflow:hidden; }
        .mission-map-content { display:flex; flex:1; flex-direction:column; min-height:0; overflow:hidden; }
        .mission-map-content .panel-heading { flex:none; margin-bottom:6px; }
        #map { flex:1; height:auto; min-height:150px; }
        .legend { flex:none; gap:5px 10px; padding-top:5px; font-size:9px; }
        .legend.complexity-legend { gap:4px 8px; margin-top:2px; }
        .complexity-gradient { width:90px; height:7px; }
        .route-readout { flex:none; margin-top:4px; font-size:9px; }
        .mission-links { flex:none; gap:4px 7px; margin-top:4px; }
        .mission-links a { padding:3px 5px; font-size:9px; }
        .right-rail { display:grid; grid-template-rows:minmax(145px,.8fr) minmax(190px,1.2fr); gap:8px; min-height:0; height:100%; overflow:hidden; }
        .camera-panel,.model-panel { display:flex; flex-direction:column; min-height:0; margin:0 !important; padding:8px; overflow:hidden; }
        .camera-panel .panel-heading,.model-panel .panel-heading { flex:none; margin-bottom:5px; }
        .camera-frame { flex:1; min-height:0; aspect-ratio:auto; }
        .camera-meta,.camera-dots,.target-note,.model-toolbar { flex:none; }
        .camera-source-footer { display:flex; align-items:center; justify-content:space-between; gap:5px; flex:none; margin-top:4px; color:var(--muted); font-size:9px; }
        .camera-source-footer button { padding:4px 7px; font-size:9px; }
        #terrain-model-panel .model-viewport { flex:1; height:auto; min-height:130px; }
        .model-toolbar { gap:7px; margin-top:5px; font-size:9px; }
        .input-drawer { margin-top:0; padding-top:0; }
        .input-drawer > summary { display:none; }
        .modal-dialog { width:min(940px,calc(100vw - 28px)); max-width:940px; max-height:min(90vh,900px); margin:auto; padding:16px; overflow:auto; border:1px solid #19738a; border-radius:10px; background:#08131d; color:#e4edf3; box-shadow:0 22px 80px #000b; }
        .modal-dialog::backdrop { background:#02070dcc; backdrop-filter:blur(4px); }
        .dialog-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
        .dialog-heading h2 { margin-top:2px; font-size:17px; }
        .dialog-close { min-height:34px; padding:6px 10px; }
        .gallery-disclaimer { margin:0 0 10px; color:#b6c8d1; font-size:12px; }
        .gallery-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }
        .gallery-card { min-width:0; overflow:hidden; border:1px solid #234657; border-radius:7px; background:#0b1822; }
        .gallery-card img { display:block; width:100%; aspect-ratio:4/3; object-fit:cover; background:#03090e; }
        .gallery-card-copy { padding:8px; }
        .gallery-card-copy strong { display:block; margin-bottom:4px; color:#e8f4fa; font-size:12px; }
        .gallery-card-copy p { margin:0; color:var(--muted); font-size:10px; line-height:1.4; }
        .gallery-card-copy a { display:inline-block; margin-top:6px; color:var(--cyan); font-size:10px; }
        .sources-dialog { width:min(980px,calc(100vw - 28px)); }
        .source-gallery-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
        .source-gallery-card { min-width:0; overflow:hidden; border:1px solid #234657; border-radius:7px; background:#0b1822; }
        .source-gallery-card img { display:block; width:100%; aspect-ratio:16/7; object-fit:cover; background:#03090e; }
        .source-gallery-card > div { padding:9px; }
        .source-gallery-card h3 { margin:0 0 4px; color:#e8f4fa; font-size:13px; }
        .source-gallery-card p { margin:0; color:var(--muted); font-size:11px; line-height:1.45; }
        .source-gallery-card a { display:inline-block; margin-top:7px; color:var(--cyan); font-size:11px; }
        @media(max-width:1000px) {
            body { overflow:auto; }
            .shell { height:auto; min-height:100vh; }
            .workspace { height:auto; min-height:100vh; overflow:visible; grid-template-rows:auto auto auto; }
            #mission-workflow { overflow:visible; }
            .layout { height:auto; }
            #map-panel { min-height:560px; }
            #map { flex:none; height:55vh; min-height:320px; }
            .right-rail { height:auto; grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-rows:auto; overflow:visible; }
            .camera-frame { flex:none; height:auto; min-height:180px; aspect-ratio:16/9; }
            #terrain-model-panel .model-viewport { flex:none; height:320px; }
        }
        @media(max-width:650px) {
            .workspace { padding:8px; }
            .console-header { flex-wrap:wrap; }
            .mission-command { grid-template-columns:1fr; }
            .command-controls { justify-content:flex-start; flex-wrap:wrap; }
            .metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .metric { height:auto; min-height:54px; }
            .layout { grid-template-columns:1fr; }
            .right-rail { display:flex; flex-direction:column; }
            .system-grid,.gallery-grid,.source-gallery-grid { grid-template-columns:1fr; }
            .modal-dialog { padding:12px; }
        }
        .workflow-tabs { display:flex; flex:none; gap:5px; margin:0; padding:0 2px; border-bottom:1px solid #153e4c; }
        .workflow-tabs button { flex:1; min-height:38px; border:1px solid transparent; border-bottom:0; border-radius:6px 6px 0 0; padding:7px 10px; background:#09141e; color:var(--muted); font-size:11px; }
        .workflow-tabs button[aria-selected="true"] { border-color:#157b90; background:#0b2833; color:#75f2f1; box-shadow:inset 0 -2px #31d9e3; }
        .workflow-panel { min-width:0; min-height:0; height:100%; overflow:hidden; }
        .workflow-panel[hidden] { display:none !important; }
        #mission-workflow { display:flex; flex-direction:column; gap:7px; }
        #mission-workflow .metrics { flex:none; }
        #mission-workflow .layout { display:block; flex:1; min-height:0; height:auto; }
        #mission-workflow #map-panel { height:100%; }
        #camera-workflow { overflow:hidden; }
        #camera-workflow .right-rail { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(360px,1fr); grid-template-rows:minmax(0,1fr); gap:10px; height:100%; overflow:hidden; }
        #camera-workflow #camera-view,#camera-workflow #terrain-model-panel { height:100%; min-height:0; }
        #camera-workflow .camera-frame { flex:1; min-height:250px; height:auto; aspect-ratio:auto; }
        #camera-workflow .camera-frame img { object-fit:contain; background:#02090e; }
        #camera-workflow #terrain-model-panel .model-viewport { flex:1; width:100%; height:auto; min-height:220px; }
        #status-workflow { overflow:hidden; padding:0; }
        #status-workflow .mission-command {
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            grid-template-rows:minmax(0,1fr) minmax(0,.75fr);
            align-items:stretch;
            gap:8px;
            height:100%;
            min-height:0;
        }
        #status-workflow .mission-command > .panel,
        #status-workflow .system-grid > .panel { min-height:0; padding:8px; overflow:hidden; }
        #status-workflow .system-grid { display:contents; }
        #status-workflow .mission-directive { grid-column:1; grid-row:1; }
        #status-workflow #rover-status { grid-column:2; grid-row:1; }
        #status-workflow #mission-alerts-panel { grid-column:3; grid-row:1; }
        #status-workflow .model-readiness { grid-column:1/3; grid-row:2; }
        #status-workflow .nasa-operations { grid-column:3; grid-row:2; }
        #status-workflow .panel-heading { margin-bottom:6px; }
        #status-workflow .status-list { gap:2px; margin-top:3px; }
        #status-workflow .status-row { padding:3px 2px; font-size:10px; line-height:1.2; }
        #status-workflow .telemetry-disclaimer { margin-top:5px; font-size:9px; line-height:1.25; }
        #status-workflow .model-readiness-grid { gap:5px; }
        #status-workflow .model-readiness-grid > div { padding:6px 7px; }
        #status-workflow .model-readiness-grid p { margin-top:3px; font-size:9px; line-height:1.3; }
        .model-readiness-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
        #status-workflow .nasa-operations .mission-links { gap:4px; margin-top:3px; }
        #status-workflow .nasa-operations .mission-links a { padding:3px 5px; font-size:8px; }
        #status-workflow .nasa-operations .telemetry-disclaimer { margin-top:4px; font-size:8px; }
        .model-readiness-grid > div { border:1px solid #234657; border-radius:6px; padding:10px; background:#09141e; }
        .model-readiness-grid strong { color:#b9edf0; font-size:11px; }
        .model-readiness-grid p { margin:5px 0 0; color:var(--muted); font-size:10px; line-height:1.45; }
        #route-workflow { overflow:auto; padding:0 2px 6px; }
        #route-workflow .route-panel { min-height:100%; }
        #route-workflow .route-layout { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr); gap:12px; align-items:start; }
        #route-workflow .route-controls-column,#route-workflow .route-context-column { min-width:0; }
        #route-workflow .route-context-column { display:grid; align-content:start; gap:8px; }
        #route-workflow .route-context-column .note,
        #route-workflow .route-context-column .result,
        #route-workflow .route-context-column .warning { margin:0; padding:9px 10px; font-size:11px; }
        #route-workflow .route-model-note { border-left:3px solid #e8b45a; }
        #route-workflow .plume-model-panel { border:1px solid #3b3155; border-left:3px solid #b89bfa; border-radius:6px; padding:9px; background:#0b101b; }
        #route-workflow .plume-model-panel summary { color:#d5c7ff; cursor:pointer; font-size:11px; font-weight:700; letter-spacing:.4px; text-transform:uppercase; }
        #route-workflow .plume-model-panel[open] summary { margin-bottom:8px; }
        #route-workflow .plume-model-panel .note { margin:6px 0; }
        #route-workflow .plume-model-panel .form-grid { gap:7px; margin-top:8px; }
        #route-workflow .plume-model-panel .field label { font-size:10px; }
        #route-workflow .plume-model-panel .field input { padding:7px; font-size:11px; }
        #route-workflow .plume-model-panel .source-links { gap:5px; margin-top:7px; }
        #route-workflow .plume-model-panel .source-links a { padding:5px 7px; font-size:9px; }
        #route-workflow .field-observations { margin-top:10px; border:1px solid #284353; border-radius:6px; padding:8px; background:#08131c; }
        #route-workflow .field-observations summary,
        #route-workflow .source-limits summary { color:#7de1e8; cursor:pointer; font-size:10px; font-weight:700; letter-spacing:.5px; text-transform:uppercase; }
        #route-workflow .field-observations[open] summary,
        #route-workflow .source-limits[open] summary { margin-bottom:8px; }
        #route-workflow .source-limits { border:1px solid #284353; border-radius:6px; padding:8px; background:#08131c; }
        #route-workflow .source-limits .note { margin-top:7px; }
        #route-workflow .route-settings .section-label { margin:10px 0 6px; }
        #route-workflow form { margin-top:0; }
        #route-workflow .input-drawer { margin-top:0; }
        #route-workflow .input-drawer > summary { display:block; }
        #route-workflow .route-panel > .panel-heading { position:sticky; top:-11px; z-index:2; margin:-11px -11px 10px; padding:10px 11px; border-bottom:1px solid #1c4555; background:#08131df2; }
        @media(max-width:1000px) {
            .workspace { grid-template-rows:auto auto auto; }
            .workflow-panel { height:auto; min-height:70vh; overflow:visible; }
            #mission-workflow { min-height:75vh; }
            #mission-workflow .layout { flex:none; }
            #mission-workflow #map-panel { min-height:560px; }
            #camera-workflow .right-rail { height:auto; grid-template-columns:1fr; grid-template-rows:auto auto; overflow:visible; }
            #camera-workflow #camera-view { min-height:65vh; }
            #camera-workflow .camera-frame { min-height:48vh; }
            #camera-workflow #terrain-model-panel { min-height:55vh; }
            #camera-workflow #terrain-model-panel .model-viewport { height:45vh; }
            #route-workflow .route-layout { grid-template-columns:1fr; }
            #route-workflow .route-context-column { grid-template-columns:repeat(2,minmax(0,1fr)); }
            #route-workflow .route-model-note,#route-workflow .source-limits { grid-column:1/-1; }
            #status-workflow { overflow:auto; padding-right:3px; }
            #status-workflow .mission-command { grid-template-columns:1fr; grid-template-rows:auto; height:auto; }
            #status-workflow .mission-command > *,
            #status-workflow .system-grid > .panel { grid-column:1; grid-row:auto; }
            #status-workflow .system-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
            #status-workflow .model-readiness-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .model-readiness-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        @media(max-width:650px) {
            .workflow-tabs { flex-wrap:wrap; }
            .workflow-tabs button { flex:1 1 45%; }
            #status-workflow .system-grid,.model-readiness-grid { grid-template-columns:1fr; }
                    .route-evidence-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        body { overflow:auto; }
        .shell { height:auto; min-height:100vh; }
        .workspace { height:auto; min-height:100vh; display:flex; flex-direction:column; gap:12px; overflow:visible; padding:16px clamp(14px,3vw,42px) 28px; }
        .console-header { min-height:72px; }
        h1 { font-size:24px; }
        .subtitle,.eyebrow { font-size:13px; letter-spacing:1.2px; }
        .workflow-tabs { gap:8px; border-bottom:1px solid #245064; }
        .workflow-tabs button { flex:1; min-height:52px; border:1px solid #264657; border-radius:8px 8px 0 0; padding:12px 16px; background:#0b141e; color:#c2d0d8; font-size:16px; font-weight:700; }
        .workflow-tabs button[aria-selected="true"] { border-color:#24bdc9; background:#10313b; color:#b9fbff; box-shadow:inset 0 -3px #31d9e3; }
        .workflow-panel { height:auto; min-height:65vh; overflow:visible; }
        #movement-workflow { min-height:70vh; }
        #movement-workflow .metrics { grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); }
        #movement-workflow .metric { height:auto; min-height:86px; align-items:flex-start; }
        #movement-workflow .metric .eyebrow { min-height:2.7em; font-size:11px; line-height:1.35; letter-spacing:.8px; }
        #movement-workflow .layout { display:block; height:auto; }
        #movement-workflow #map-panel { min-height:620px; }
        #movement-workflow #map { height:min(62vh,680px); min-height:420px; }
        #camera-workflow { height:auto; min-height:600px; overflow:visible; }
        #camera-workflow .right-rail { height:auto; grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-rows:auto; overflow:visible; }
        #camera-workflow #camera-view,#camera-workflow #terrain-model-panel { min-height:520px; height:auto; }
        #camera-workflow .camera-frame { min-height:300px; height:auto; aspect-ratio:16/9; }
        #camera-workflow #terrain-model-panel .model-viewport { height:400px; }
        .panel { padding:18px; }
        h2 { font-size:20px; letter-spacing:.2px; }
        .tag,.field label,.status-row,.note,.result,.warning { font-size:14px; }
        .panel-heading { margin-bottom:16px; }
        .simple-intro { max-width:860px; margin:4px 0 18px; color:#d5e0e6; font-size:18px; }
        .simple-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin-top:16px; }
        .simple-card { border:1px solid #264657; border-radius:9px; padding:16px; background:#091720; }
        .simple-card h3 { margin:0 0 8px; color:#c5f7fb; font-size:17px; }
        .simple-card p { margin:0; color:#b6c5ce; }
        .data-links { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
        .data-links a,.data-links button { border:1px solid #276778; border-radius:6px; padding:9px 12px; color:#a5f4f4; background:#0a1d27; font-size:14px; text-decoration:none; }
        .solar-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:16px 0; }
        .solar-value { border:1px solid #334453; border-radius:8px; padding:15px; background:#0a131c; }
        .solar-value span { display:block; color:#aabac4; font-size:13px; }
        .solar-value strong { display:block; margin-top:4px; font-size:24px; }
        #solar-chart { display:block; width:100%; height:300px; border:1px solid #263d4c; border-radius:8px; background:#07111a; }
        #radiation-board, #landing-bars, #landing-rank { display:block; width:100%; border:1px solid #263d4c; border-radius:8px; background:#07111a; }
        #radiation-board { height:220px; }
        #landing-bars { height:180px; margin-top:12px; }
        #landing-rank { height:160px; margin-top:8px; }
        .quiz-row { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 16px; }
        .quiz-row button { border:1px solid #355062; background:#10202b; color:#e7f2f6; border-radius:999px; padding:8px 14px; cursor:pointer; }
        .quiz-row button[aria-pressed="true"] { background:#1c6b62; border-color:#7ef0e4; }
        .landing-name { font-size:28px; margin:8px 0 0; }
        .landing-coords { color:#9af6ff; margin:0 0 8px; }
        .landing-notes { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .landing-notes ul { margin:8px 0; padding-left:18px; }
        .photo-strip { display:flex; gap:8px; overflow:auto; margin-top:10px; }
        .photo-strip img { height:140px; border-radius:8px; flex:0 0 auto; }
        .rover-pin { background:transparent; border:0; }
        .rover-pin span { display:block; width:18px; height:10px; margin:2px auto 0; background:#f4fbff; border-radius:3px 7px 3px 3px; box-shadow:0 0 12px #53e0d0; position:relative; }
        .rover-pin span:before, .rover-pin span:after { content:""; position:absolute; bottom:-5px; width:6px; height:6px; border-radius:50%; background:#16323a; border:1px solid #9af6ff; }
        .rover-pin span:before { left:0; }
        .rover-pin span:after { right:0; }
        .feature-stage .simple-intro, .feature-stage .simple-card, .feature-stage .protect-list, .feature-stage .simple-grid { display:none; }
        #mission-workflow .simple-intro { display:none; }
        .app-tabs { display:flex; gap:8px; margin:14px 0; }
        .app-tabs button { flex:1; min-height:52px; border:1px solid #264657; border-radius:8px; background:#0b141e; color:#d5e7ee; font-size:18px; font-weight:700; cursor:pointer; }
        .app-tabs button[aria-selected="true"] { background:#10313b; border-color:#24bdc9; color:#b9fbff; box-shadow:inset 0 -3px #31d9e3; }
        #sun-compare, #sun-preview { display:block; width:100%; height:300px; border:1px solid #263d4c; border-radius:8px; background:#07111a; }
        .mission-table { width:100%; border-collapse:collapse; font-size:14px; }
        .mission-table th, .mission-table td { border-bottom:1px solid #263d4c; padding:8px 6px; text-align:left; }
        .plan-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
        @media(max-width:800px) { .plan-grid { grid-template-columns:1fr; } }
        .radiation-status { border-left:4px solid #e6b95e; border-radius:4px; padding:14px 16px; background:#211b10; color:#ffedc5; }
        .small-print { color:#9fb0bb; font-size:13px; }
        .model-readiness { margin-top:14px; }
        .dataset-counts { margin-top:10px; color:#c7e4eb; font-size:14px; }
        #dust-workflow .route-layout { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr); gap:12px; align-items:start; }
        @media(max-width:800px) {
            #camera-workflow .right-rail { grid-template-columns:1fr; }
            #movement-workflow #map-panel { min-height:500px; }
            #movement-workflow #map { height:55vh; min-height:350px; }
            .solar-summary { grid-template-columns:1fr; }
            #dust-workflow .route-layout { grid-template-columns:1fr; }
        }
        @media(max-width:650px) {
            .workspace { padding:10px; }
            .workflow-tabs button { flex:1 1 45%; font-size:14px; }
            .panel { padding:13px; }
            .workflow-panel { min-height:0; }
            #camera-workflow #camera-view,#camera-workflow #terrain-model-panel { min-height:0; }
            #dust-workflow .form-grid { grid-template-columns:1fr 1fr; }
        }
        .briefing { flex:none; }
        .briefing .simple-intro { margin:0 0 12px; font-size:16px; }
        .briefing-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
        .link-line { margin:0 0 12px; padding:8px 10px; border-left:3px solid #24bdc9; border-radius:4px; background:#0a1822; color:#d5e7ee; }
        #mission-workflow .solar-summary { grid-template-columns:repeat(4,minmax(140px,1fr)); }
        @media(max-width:1100px) { #mission-workflow .solar-summary { grid-template-columns:1fr 1fr; } }
        @media(max-width:1100px) { .briefing-grid { grid-template-columns:1fr 1fr; } }
        .stage-card { margin:0 0 12px; }
        .stage-canvas { display:block; width:100%; height:210px; max-width:100%; border:1px solid #263d4c; border-radius:8px; background:#071018; overflow:hidden; }
        #dust-look { height:360px; }
        .look-row { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(210px,.7fr); gap:12px; align-items:start; margin:0 0 14px; }
        .look-copy { max-height:210px; overflow:auto; }
        .protect-list { margin:8px 0 0; padding-left:18px; }
        .protect-list li { margin:4px 0; }
        .flare-questions { margin-top:12px; border:1px solid #284353; border-radius:8px; padding:10px 12px; background:#08131c; }
        .flare-questions summary { cursor:pointer; color:#7de1e8; font-weight:700; }
        #temperature-workflow .stage-canvas { height:280px; }
        @media(max-width:800px) {
            .briefing-grid,.look-row { grid-template-columns:1fr; }
            .look-copy { max-height:160px; }
        }
        .night-hero { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr); gap:12px; align-items:stretch; }
        .site-figure { margin:0; }
        .site-figure img,.photo-strip img { display:block; width:100%; height:168px; object-fit:cover; border:1px solid #264657; border-radius:8px; background:#071018; }
        .site-figure figcaption { margin-top:6px; color:#9fb0bb; font-size:12px; }
        .graph-stack { display:grid; gap:8px; }
        .site-canvas { display:block; width:100%; height:160px; border:1px solid #263d4c; border-radius:8px; background:#071018; }
        .site-power { height:210px; margin:12px 0; }
        .shackleton-grid { height:420px; margin:8px 0 12px; }
        #shackleton-counts { grid-template-columns:repeat(5,minmax(120px,1fr)); }
        .trained-table-wrap { overflow-x:auto; }
        .trained-table { width:100%; border-collapse:collapse; margin-top:8px; }
        .trained-table th,.trained-table td { border-bottom:1px solid #264657; padding:10px 8px; text-align:left; vertical-align:top; }
        .trained-table th { color:#8fd8df; font-size:12px; letter-spacing:.6px; text-transform:uppercase; }
        .trained-table td { color:#d5e0e6; font-size:15px; }
        @media(max-width:800px) { #shackleton-counts { grid-template-columns:1fr 1fr; } }
        .photo-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:10px 0 4px; }
        .photo-strip img { height:92px; }
        .option-card.works { border-color:#1f8a72; }
        .option-card.fails { border-color:#8a3a44; }
        .option-card .tag { display:inline-block; margin-bottom:6px; }
        @media(max-width:800px) {
            .night-hero,.photo-strip { grid-template-columns:1fr 1fr; }
        }
        .stage { display:grid; grid-template-columns:minmax(0,1fr) 210px; gap:14px; align-items:start; }
        .stage.feature-open { grid-template-columns:minmax(420px,1.15fr) minmax(360px,.95fr); }
        .stage-main { min-width:0; }
        .feature-rail { display:flex; flex-direction:column; gap:10px; min-width:0; }
        .feature-label { margin:0; color:#8fd8df; font-size:12px; letter-spacing:1.4px; text-transform:uppercase; }
        .stage .workflow-tabs { flex-direction:column; gap:6px; border-bottom:0; }
        .stage .workflow-tabs button { flex:none; width:100%; min-height:42px; border:1px solid #264657; border-radius:8px; padding:8px 12px; background:#0b141e; color:#c2d0d8; font-size:15px; font-weight:700; text-align:left; box-shadow:none; }
        .stage .workflow-tabs button[aria-selected="true"] { border-color:#24bdc9; background:#10313b; color:#b9fbff; box-shadow:inset 3px 0 #31d9e3; }
        .feature-stage .workflow-panel { height:auto; min-height:0; overflow:visible; }
        .feature-stage #dust-workflow .route-layout,
        .feature-stage #camera-workflow .right-rail { grid-template-columns:1fr; }
        .feature-stage #camera-workflow #camera-view,
        .feature-stage #camera-workflow #terrain-model-panel { min-height:0; }
        .feature-stage #movement-workflow #map { height:360px; min-height:280px; }
        @media(max-width:1000px) {
            .stage,.stage.feature-open { grid-template-columns:1fr; }
            .stage .workflow-tabs { flex-direction:row; flex-wrap:wrap; }
            .stage .workflow-tabs button { width:auto; flex:1 1 30%; text-align:center; }
        }
        body { background:
            radial-gradient(900px 380px at 88% -8%, #1c6d86 0%, transparent 58%),
            radial-gradient(640px 320px at 0% 0%, #12324c 0%, transparent 52%),
            #07131c; color:#f4fbff; }
        .panel { background:linear-gradient(180deg, rgba(16,52,72,.94), rgba(7,22,34,.96)); border:1px solid #3d8ea8; border-radius:16px; box-shadow:inset 0 0 0 1px #ffffff14, 0 16px 40px #0007; }
        h1 { font-size:30px; color:#fff; letter-spacing:3px; }
        h2 { font-size:26px; color:#f7fdff; }
        .app-tabs { gap:10px; }
        .app-tabs button { min-height:58px; border-radius:14px; letter-spacing:1.6px; text-transform:uppercase; background:#0a2230; color:#d7f4ff; font-size:18px; }
        .app-tabs button[aria-selected="true"] { background:linear-gradient(180deg,#1ec4e0,#0b7590); color:#fff; border-color:#9af6ff; box-shadow:0 0 22px #2ad8ff55; }
        .choice-board { margin:0 0 14px; }
        .choice-title { margin:0 0 8px; color:#9ae7f5; font-size:13px; letter-spacing:1.4px; text-transform:uppercase; }
        .choice-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(148px,1fr)); gap:8px; }
        html, body { height:100%; overflow:hidden; }
        .shell { height:100vh; overflow:hidden; display:flex; flex-direction:column; }
        .workspace { flex:1; min-height:0; display:flex; flex-direction:column; overflow:hidden; }
        .app-tabs, .kept-record { position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; clip:rect(0 0 0 0) !important; }
        #page-simulator-panel { display:contents; }
        .screen-nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)) 128px; gap:8px; padding:0 10px 8px; }
        .screen-nav button { min-height:42px; border-radius:10px; border:1px solid #5eb4cc; background:#0a2230; color:#f4fbff; font:700 13px/1.15 "Segoe UI", Arial, sans-serif; letter-spacing:.8px; text-transform:uppercase; }
        .screen-nav button[aria-pressed="true"] { background:linear-gradient(180deg,#5eebff,#12a4c4); color:#042028; border-color:#fff; }
        #open-options { background:transparent; border-style:dashed; letter-spacing:.4px; }
        #open-options[aria-expanded="true"] { background:#12384c; color:#fff; }
        .screen { font-family:"Segoe UI", Arial, sans-serif; }
        .screen[hidden] { display:none !important; }
        .screen.is-on { display:flex; flex-direction:column; flex:1; min-height:0; overflow:hidden; margin:0 10px 10px; }
        .screen h2 { font-size:18px !important; letter-spacing:1.4px; font-weight:700; text-shadow:none; }
        .screen .ops-kicker, .screen .choice-title, .screen h3 { font-size:11px; letter-spacing:1.2px; }
        #page-home-panel.is-on { gap:8px; padding:0; }
        #briefing, #plan-gate { min-height:0; }
        #plan-gate.is-on, #page-home-panel.is-on #plan-gate { flex:1; display:flex; flex-direction:column; overflow:hidden; }
        #choice-boards { flex:none; min-height:0; overflow:visible; }
        #sun-preview { height:72px; flex:0 0 72px; }
        #live-finds { max-height:132px; overflow:auto; margin-top:6px; }
        #live-finds a { min-height:0; padding:6px 8px; }
        .ops-board.is-on, .path-board.is-on, .topo-board.is-on { padding:8px; }
        .ops-mid, .ops-low, .path-stage, .topo-layout { flex:1; min-height:0; }
        .ops-pane, .topo-stage { min-height:0; display:flex; flex-direction:column; }
        #ops-arc, #path-map, #topo-canvas { flex:1; height:auto; min-height:0; }
        .ops-gauges { flex:1; min-height:0; }
        .ops-gauges canvas, #ops-alt, #ops-slope { height:100%; min-height:0; }
        #plan-gate { order:0; }
        #briefing { order:0; padding:0; background:transparent; border:0; box-shadow:none; }
        #briefing .eyebrow, #briefing > h2 { display:none; }
        .q-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-end; }
        .q-head h2 { margin:0; font-size:22px !important; letter-spacing:.3px; }
        .q-lead { margin:0; max-width:460px; color:#d7f4ff; font-size:14px; line-height:1.35; }
        .q-layout { flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,1.2fr) minmax(280px,.85fr); gap:12px; margin-top:10px; }
        .q-ask, .q-verdict { min-height:0; overflow:auto; }
        .q-ask { display:flex; flex-direction:column; gap:4px; }
        #page-home-panel .briefing-grid { display:flex; flex-direction:column; gap:12px; }
        #page-home-panel .field label { color:#9ae7f5; font-size:12px; letter-spacing:1px; }
        #page-home-panel .choice-card { min-height:44px; padding:8px 10px; font-size:14px; border-radius:10px; }
        .q-why { margin:6px 0 0; color:#9ad7e4; font-size:12px; line-height:1.35; }
        .q-native { position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; clip:rect(0 0 0 0) !important; }
        .q-slope { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
        #brief-slope { width:100%; accent-color:#5eebff; }
        .q-slope b { color:#f4fbff; font-size:18px; }
        .q-verdict { border:1px solid #1c6f86; border-radius:12px; background:#061018; padding:12px; display:flex; flex-direction:column; gap:8px; }
        .q-badge { margin:0; align-self:flex-start; padding:4px 10px; border-radius:999px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; font-size:12px; background:#1a3a4a; color:#9af6ff; }
        .q-badge.go { background:#114b3a; color:#b8ffd8; }
        .q-badge.stop, .q-badge.hold { background:#4a1c24; color:#ffc1c6; }
        .q-decision { margin:0; color:#f4fbff; font-size:15px; line-height:1.4; }
        .q-meters { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .q-meters div { padding:8px; border-top:1px solid #1c6f86; }
        .q-meters span, .q-meters small { display:block; color:#8fd8df; font-size:11px; letter-spacing:.6px; }
        .q-meters strong { color:#f4fbff; font-size:20px; }
        .q-actions { flex-wrap:wrap; margin-top:0; }
        .q-actions button { flex:1 1 140px; }
        .q-foot { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(220px,.85fr); gap:10px; align-items:center; margin-top:8px; }
        .q-record { margin:8px 0; border:1px solid #284353; border-radius:8px; padding:8px 10px; background:#08131c; }
        .q-record summary { cursor:pointer; color:#7de1e8; font-weight:700; }
        #page-home-panel #sun-preview { height:96px; flex:0 0 96px; }
        #page-home-panel #open-yard, #page-home-panel #open-terrain, #page-home-panel #q-open-next { min-height:42px; min-width:0; background:#12384c; color:#f4fbff; border-color:#5eb4cc; }
        @media(max-width:900px) { .q-layout, .q-foot, .q-head { display:grid; grid-template-columns:1fr; } }
        .choice-card { min-height:72px; border-radius:14px; border:1px solid #5eb4cc; background:#12384c; color:#f4fbff; text-align:left; padding:12px 14px; font-size:16px; font-weight:700; cursor:pointer; }
        .choice-card:hover { background:#1a5270; color:#fff; }
        .choice-card[aria-pressed="true"],
        .choice-card[aria-pressed="true"]:hover { border-color:#fff; background:linear-gradient(180deg,#5eebff,#12a4c4); color:#042028; box-shadow:0 0 18px #5eebff88; }
        .app-tabs button:hover { background:#12384c; }
        .app-tabs button[aria-selected="true"]:hover { background:linear-gradient(180deg,#1ec4e0,#0b7590); color:#fff; }
        .plan-grid { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }
        .briefing .simple-intro, .feature-stage .small-print, .feature-stage .link-line, .feature-stage .radiation-status { display:none; }
        #sun-compare { height:340px; border-color:#3d8ea8; background:#06141e; }
        #sun-preview { height:220px; border-color:#3d8ea8; background:#06141e; }
        .live-finds { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; margin-top:12px; }
        .live-finds a { display:grid; gap:4px; min-height:88px; padding:12px; border-radius:12px; border:1px solid #2f6d84; background:#0a1e2c; color:#f4fbff; text-decoration:none; }
        .live-finds small { color:#9ad7e4; font-size:13px; }
        .rover-pin span { width:22px; height:12px; box-shadow:0 0 16px #7ef6ff; }
        #run-plan, #open-yard, #open-terrain { min-height:54px; min-width:180px; border-radius:12px; letter-spacing:.4px; background:linear-gradient(180deg,#1ec4e0,#0b7590); border-color:#9af6ff; }
        #base-tools button { background:#12384c; border-color:#5eb4cc; color:#f4fbff; min-height:48px; border-radius:12px; }
        #base-tools button:hover { background:#1a5270; }
        .yard-layout { display:grid; grid-template-columns:minmax(0,1.45fr) minmax(240px,.55fr); gap:14px; align-items:start; }
        #base-canvas { display:block; width:100%; height:560px; border-radius:14px; border:1px solid #3d8ea8; background:#061018; touch-action:none; }
        .yard-readout { list-style:none; margin:8px 0 0; padding:0; }
        .ops-board { margin:0 0 14px; padding:12px; border:1px solid #1c6f86; border-radius:12px; background:#061018; color:#e9f7ff; box-shadow:inset 0 0 0 1px #12384a; }
        .ops-top { display:grid; grid-template-columns:minmax(0,1.4fr) auto minmax(220px,.7fr); gap:12px; align-items:center; padding:8px 10px; border-radius:8px; background:linear-gradient(90deg,#2a2414,#102028 55%); border-bottom:3px solid #e6c36a; }
        .ops-brand { display:flex; gap:10px; align-items:center; }
        .ops-brand img { width:42px; height:42px; }
        .ops-brand h2 { margin:0; font-size:22px; letter-spacing:1px; color:#f4e2a8; }
        .ops-brand p { margin:0; color:#9ad7e4; letter-spacing:.6px; font-size:13px; }
        .ops-met { text-align:center; }
        .ops-met span, .ops-kicker { display:block; color:#8fd8df; letter-spacing:1.4px; font-size:11px; }
        .ops-met strong { color:#f4fbff; font-size:22px; letter-spacing:1px; }
        .ops-lights { display:grid; grid-template-columns:1fr 1fr; gap:4px 12px; margin:0; padding:0; list-style:none; font-size:12px; letter-spacing:.6px; }
        .ops-lights b { color:#d7f6ff; }
        .ops-lights i { display:inline-block; width:8px; height:8px; margin-right:6px; border-radius:50%; background:#3ddea0; box-shadow:0 0 8px #3ddea0; }
        .ops-lights i.warn { background:#e6c84a; box-shadow:0 0 8px #e6c84a; }
        .ops-lights i.bad { background:#ff5a62; box-shadow:0 0 8px #ff5a62; }
        .ops-mid, .ops-low { display:grid; gap:10px; margin-top:10px; }
        .ops-mid { grid-template-columns:minmax(0,1.6fr) minmax(220px,.55fr); }
        .ops-low { grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); }
        .ops-pane { min-width:0; padding:8px; border:1px solid #1c6f86; border-radius:8px; background:#07141e; }
        .ops-kicker { margin:0 0 6px; }
        #ops-arc { display:block; width:100%; height:280px; }
        #ops-alt, #ops-slope { display:block; width:100%; flex:1; height:auto; min-height:0; }
        .ops-gauges { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:4px; }
        .ops-gauges canvas { width:100%; height:100%; min-height:96px; }
        .ops-figures { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:6px; flex:none; }
        .ops-figures div { padding-top:6px; border-top:1px solid #1c6f86; }
        .ops-figures span { display:block; color:#8fd8df; font-size:11px; letter-spacing:.8px; }
        .ops-figures strong { color:#f4fbff; font-size:22px; }
        #ops-log { list-style:none; margin:0; padding:0; flex:1; min-height:0; overflow:auto; }
        #ops-log li { margin:0 0 7px; color:#d7f4ff; font-size:12px; letter-spacing:.5px; line-height:1.35; }
        .ops-note { margin:8px 2px 0; color:#9ad7e4; font-size:12px; }
        .path-board { margin:0 0 14px; padding:6px 8px 10px; border:1px solid rgba(52,117,139,.9); border-radius:12px; background:radial-gradient(ellipse at 50% 0%,#071d2a 0%,#050b11 40%,#02070d 100%); box-shadow:inset 0 0 28px rgba(29,110,136,.18), 0 0 30px rgba(0,0,0,.28); font-family:"Rajdhani","Segoe UI",sans-serif; }
        .path-board h2 { margin:0 0 6px; text-align:center; color:#66edf3 !important; letter-spacing:.16em !important; font-size:clamp(24px,2.6vw,48px) !important; font-weight:800; text-transform:uppercase; text-shadow:0 0 18px rgba(72,219,232,.85), 0 0 2px rgba(214,255,255,.9) !important; }
        .path-stage { position:relative; min-height:0; height:clamp(520px,62vh,820px); overflow:hidden; border:1px solid rgba(51,121,146,.95); background:linear-gradient(180deg,#0a1015 0%,#0b141b 100%); box-shadow:inset 0 0 30px rgba(4,9,14,.7); }
        .path-card { position:absolute; top:12px; z-index:3; width:min(214px,26vw); border:1px solid rgba(132,203,212,.9); border-radius:4px; background:rgba(5,12,18,.78); padding:8px 10px 9px; color:#e7f7ff; font-size:13px; line-height:1.35; box-shadow:0 0 0 1px rgba(4,16,24,.8), 0 10px 28px rgba(0,0,0,.38); backdrop-filter:blur(2px); }
        .path-card-left { left:12px; }
        .path-card-right { right:12px; }
        .path-card h3 { margin:0 0 6px; color:#c8f8ff; font-size:12px; letter-spacing:.18em; font-weight:700; text-transform:uppercase; }
        .path-card p { margin:0 0 2px; letter-spacing:.2px; }
        .path-card strong { color:#f4fbff; font-weight:700; }
        .path-card .path-surface { color:#f6ffd8; }
        .path-card .path-surface strong { color:#dffbf4; }
        .path-go { color:#7bf7a8; text-shadow:0 0 8px rgba(106,247,155,.8); }
        .path-gold { color:#f6d77a; }
        .path-cyan { color:#7eefff; }
        .path-red { color:#ff6b72; }
        #path-map { position:absolute; inset:0; display:block; width:100%; height:100%; min-height:0; background:#040a0f; }
        .path-legend { position:absolute; left:50%; bottom:10px; transform:translateX(-50%); z-index:4; display:flex; flex-wrap:wrap; justify-content:center; gap:4px 14px; padding:8px 12px; border:1px solid rgba(143,216,223,.82); border-radius:8px; background:rgba(4,12,18,.9); font-size:13px; letter-spacing:.04em; color:#eaf7ff; box-shadow:0 6px 18px rgba(0,0,0,.38); }
        .path-legend span { display:flex; align-items:center; opacity:.92; }
        .path-legend i { display:inline-block; width:18px; height:4px; margin-right:6px; border-radius:2px; }
        .path-legend i.good { background:#39f08a; }
        .path-legend i.near { background:#f0c14a; }
        .path-legend i.bad { background:#ff4d57; }
        .path-legend i.gold { background:#e6c36a; }
        .path-legend i.floor { background:#7eefff; }
        @media(max-width:900px) { .path-card { width:min(172px,34vw); padding:6px 8px; font-size:12px; } .path-card h3 { font-size:11px; } .path-stage { height:480px; } }
        .topo-board { margin:0 0 14px; padding:12px; border:1px solid #1c6f86; border-radius:12px; background:#05080d; color:#d7f6ff; }
        .topo-head, .topo-foot { display:flex; justify-content:space-between; gap:12px; font-size:12px; letter-spacing:1px; color:#8fd8df; }
        .topo-head h2 { margin:0; color:#f4fbff; letter-spacing:1.4px; font-size:22px; }
        .topo-layout { display:grid; grid-template-columns:minmax(0,1fr) 250px; gap:10px; margin-top:8px; }
        .topo-stage { position:relative; min-width:0; overflow:hidden; border:1px solid #1c6f86; border-radius:8px; background:#000; }
        #topo-canvas { display:block; width:100%; height:560px; }
        .topo-compass { position:absolute; top:12px; right:12px; width:72px; height:72px; border:1px solid #2f8ea8; border-radius:50%; display:grid; place-items:center; background:#071018cc; }
        .topo-compass b { position:absolute; font-size:11px; color:#9af6ff; }
        .topo-compass b.n { top:4px; } .topo-compass b.s { bottom:4px; } .topo-compass b.w { left:6px; } .topo-compass b.e { right:6px; }
        .topo-needle { width:2px; height:28px; background:linear-gradient(#ff5a62, #3ee0f0); transform-origin:center 22px; }
        .topo-legend, .topo-side { border:1px solid #1c6f86; border-radius:8px; background:#071018; padding:10px; }
        .topo-legend { position:absolute; left:12px; bottom:12px; }
        .topo-legend div { display:flex; align-items:center; gap:8px; margin:3px 0; font-size:12px; }
        .swatch { width:14px; height:10px; border-radius:2px; }
        .topo-side h3 { margin:8px 0 6px; color:#8fd8df; font-size:12px; letter-spacing:1px; }
        .topo-side label { display:grid; grid-template-columns:1fr auto; gap:8px; align-items:center; margin:6px 0; font-size:12px; }
        .topo-side input[type=range] { width:100%; grid-column:1 / -1; }
        .topo-row { display:flex; justify-content:space-between; gap:8px; margin:4px 0; font-size:13px; }
        .topo-row strong { color:#f4fbff; }
        .topo-facts { position:absolute; inset:0; pointer-events:none; }
        .topo-chip { position:absolute; display:flex; align-items:center; gap:6px; min-width:0; min-height:0; transform:translate(0,-50%); margin:0; padding:0; border:0; background:transparent; color:#e7f7ff; font-weight:650; letter-spacing:0; cursor:pointer; pointer-events:auto; }
        .topo-chip i { width:9px; height:9px; border-radius:50%; background:currentColor; box-shadow:0 0 8px currentColor; flex:none; }
        .topo-chip span { padding:2px 7px; border:1px solid #1c6f86; border-radius:999px; background:#071018e6; font-size:11px; letter-spacing:.2px; white-space:nowrap; }
        .topo-chip.is-left { transform:translate(-100%,-50%); }
        .topo-chip:hover span, .topo-chip:focus span { border-color:#9af6ff; color:#fff; }
        .topo-fact { position:absolute; top:12px; left:12px; z-index:2; max-width:min(320px,70%); padding:10px 12px; border:1px solid #2f8ea8; border-radius:8px; background:#071018ee; color:#e7f7ff; pointer-events:none; }
        .topo-fact strong { display:block; margin-bottom:4px; color:#9af6ff; letter-spacing:.6px; font-size:12px; }
        .topo-fact p { margin:0; font-size:13px; line-height:1.35; }
        .topo-fact[hidden], .topo-facts[hidden], .topo-chip[hidden] { display:none; }
        @media(max-width:900px) { .topo-layout { grid-template-columns:1fr; } #topo-canvas { height:380px; } }
        @media(max-width:900px) {
            .ops-top, .ops-mid, .ops-low { grid-template-columns:1fr; }
            .ops-gauges { grid-template-columns:1fr 1fr; }
        }
        .yard-readout li { padding:8px 0; border-bottom:1px solid #245066; color:#f4fbff; font-size:15px; }
        .yard-readout strong { color:#9af6ff; }
        @media(max-width:900px) { .yard-layout { grid-template-columns:1fr; } #base-canvas { height:420px; } }
        .solar-value { background:#0c2433; border-color:#3d8ea8; }
        .solar-value strong { color:#fff; font-size:28px; }
        .console-header, .screen-nav { flex:0 0 auto; }
        .console-header { position:sticky; top:0; z-index:20; }
        .purpose { margin:0 0 8px; padding:7px 10px; border-left:3px solid #5eebff; background:#0a1c28; color:#d7f4ff; font-size:13px; line-height:1.35; }
        .purpose b { color:#7af4ff; letter-spacing:1px; font-size:11px; margin-right:8px; }
        .options-drawer { position:fixed; z-index:40; top:108px; right:16px; bottom:16px; width:min(980px, calc(100vw - 32px)); overflow:auto; padding:14px; border:1px solid #5eb4cc; border-radius:16px; background:rgba(6,16,24,.98); box-shadow:0 24px 80px #000c; }
        .options-drawer[hidden] { display:none !important; }
        .options-drawer #plan-gate { display:flex; flex-direction:column; }
        .q-close { min-height:36px; border-radius:8px; border:1px solid #5eb4cc; background:#12384c; color:#f4fbff; font-weight:700; }
        .pros-cons { flex:1; min-height:0; display:grid; grid-template-columns:1fr 1fr; gap:8px; overflow:auto; }
        .pro-kicker { color:#7dffa8 !important; }
        .con-kicker { color:#ff9aa0 !important; }
        #ops-pros, #ops-cons { margin:0; padding-left:16px; }
        #ops-pros li, #ops-cons li { margin:5px 0; font-size:13px; line-height:1.35; }
        #ops-pros li { color:#d9ffe8; }
        #ops-cons li { color:#ffd8dc; }
        .path-legend { position:absolute; left:50%; bottom:10px; transform:translateX(-50%); z-index:3; display:flex; flex-wrap:wrap; justify-content:center; gap:6px 14px; width:max-content; max-width:calc(100% - 24px); margin:0; padding:8px 12px; border:1px solid #8fd8df; border-radius:8px; background:rgba(4,12,18,.96); color:#f4fbff; font-size:13px; letter-spacing:.2px; box-shadow:0 4px 18px #000b; }
        .path-legend i { display:inline-block; width:18px; height:4px; margin-right:6px; vertical-align:middle; border-radius:2px; }
        .path-legend i.good { background:#39f08a; }
        .path-legend i.near { background:#f0c14a; }
        .path-legend i.bad { background:#ff4d57; }
        .path-legend i.gold { background:#e6c36a; }
        .path-legend i.floor { background:#7eefff; }
        .hab-track.bad b { background:linear-gradient(90deg,#8a2430,#ff6b73); box-shadow:0 0 8px #ff6b7388; }
        .descent-board { border:1px solid #14566c; border-radius:4px; background:#05080f; color:#e7f6ff; font-family:"Rajdhani","Segoe UI",sans-serif; }
        .descent-board.is-on { padding:0; }
        .des-top { display:flex; align-items:center; gap:16px; min-height:54px; padding:8px 14px; background:linear-gradient(90deg,#071018,#0c2433 40%, #071018); border-bottom:1px solid #1a6d86; }
        .des-brand { display:flex; align-items:center; gap:10px; min-width:240px; }
        .des-mark { display:grid; place-items:center; width:36px; height:36px; border:1px solid #3ee0f0; border-radius:50%; color:#7af4ff; font-size:20px; }
        .des-brand strong { display:block; letter-spacing:1.6px; font-size:16px; }
        .des-brand small { color:#8fd8df; letter-spacing:1.2px; font-size:11px; }
        .des-live { display:flex; align-items:center; gap:8px; color:#67f29a; font-weight:700; letter-spacing:1px; font-size:13px; }
        .des-live i { width:8px; height:8px; border-radius:50%; background:#4dff8d; box-shadow:0 0 10px #4dff8d; }
        .des-mission { margin-left:auto; letter-spacing:1px; color:#9ad7e4; font-size:13px; }
        .des-mission b, .des-clock b { color:#f4fbff; }
        .des-clock { letter-spacing:1px; font-size:14px; }
        .des-body { flex:1; min-height:0; display:grid; grid-template-columns:220px minmax(0,1fr) 240px; gap:10px; padding:10px; }
        .des-side, .des-stage { min-width:0; min-height:0; }
        .des-side { display:flex; flex-direction:column; gap:8px; }
        .des-pane { min-height:0; border:1px solid #1a6d86; border-radius:10px; background:linear-gradient(180deg,#0c1c28,#071018); padding:8px; display:flex; flex-direction:column; }
        .des-pane p { margin:0; color:#8fd8df; letter-spacing:1px; font-size:11px; font-weight:700; }
        .des-gauges { flex:1; min-height:0; display:grid; grid-template-rows:repeat(4,minmax(0,1fr)); gap:6px; }
        .des-safe { flex:0 0 auto; }
        .des-safe strong { display:block; margin-top:2px; color:#3dff9a; font-size:22px; letter-spacing:.4px; }
        .des-safe strong.hold { color:#ffb15a; }
        .des-safe span { color:#9ad7e4; font-size:12px; letter-spacing:.3px; }
        .des-water-row { display:flex; align-items:center; justify-content:space-between; gap:8px; }
        .des-ice { margin-top:6px; color:#d7f4ff; font-size:12px; line-height:1.35; font-weight:500; letter-spacing:0; }
        .des-ice b { color:#7af4ff; letter-spacing:.4px; }
        .des-concept { position:absolute; top:12px; left:12px; z-index:2; max-width:min(310px,52%); padding:7px 10px; border:1px solid #7bb9d8; border-radius:8px; background:rgba(3,10,18,.84); color:#e6f4ff; font-size:12px; line-height:1.35; }
        .des-concept strong { display:block; color:#a9d8ff; letter-spacing:.7px; font-size:11px; }
        .des-foot { background:#061018; border-top:1px solid #14566c; padding-top:8px; }
        .des-gauges canvas, #des-plume, #des-map, #des-stage { width:100%; height:100%; min-height:60px; display:block; }
        #des-stage { position:absolute; inset:0; height:100%; }
        .des-stage { position:relative; min-height:280px; border:1px solid #1a6d86; border-radius:12px; overflow:hidden; background:#02060c; }
        .des-caption { position:absolute; left:12px; bottom:12px; z-index:2; margin:0; max-width:68%; padding:5px 8px; border:1px solid #537d90; border-radius:5px; background:rgba(3,10,16,.86); color:#d7f4ff; font-size:11px; letter-spacing:.2px; line-height:1.35; text-shadow:0 1px 2px #000; }
        .des-water { flex:0 0 190px; }
        .des-rate { margin:2px 0; color:#7af4ff; font-size:28px; letter-spacing:.5px; }
        .des-rate span { font-size:14px; color:#9ad7e4; }
        .des-tank { position:relative; width:34px; height:78px; margin:0; flex:none; border:1px solid #3ec6ff; border-radius:8px; background:#041018; overflow:hidden; }
        .des-tank i { position:absolute; left:0; right:0; bottom:0; background:linear-gradient(180deg,#b8fbff,#1278c8); }
        .des-note { color:#9ad7e4 !important; font-weight:500 !important; letter-spacing:0 !important; line-height:1.3; }
        .des-plume, .des-map { flex:1; }
        .des-map {
            min-height:0;
            padding:7px !important;
            border-color:#2a8aa8 !important;
            background:linear-gradient(180deg,#0e2432,#071018) !important;
            box-shadow:inset 0 0 24px rgba(40,160,190,.08);
        }
        .des-map-head {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:6px;
            margin:0 0 4px;
        }
        .des-map-head > div { min-width:0; }
        .des-map-kicker {
            margin:0 !important;
            color:#7af4ff !important;
            letter-spacing:1.1px !important;
            font-size:11px !important;
            font-weight:700 !important;
        }
        .des-map-sub {
            margin:2px 0 0 !important;
            color:#9eb6c2 !important;
            font-size:10px !important;
            font-weight:500 !important;
            letter-spacing:.2px !important;
            line-height:1.25 !important;
        }
        .des-map-modes {
            display:flex;
            flex-wrap:wrap;
            gap:3px;
            justify-content:flex-end;
        }
        .des-map-modes button {
            min-height:22px;
            padding:2px 7px;
            border-radius:999px;
            border:1px solid #2a6173;
            background:#0a1c28;
            color:#9ad7e4;
            font-size:10px;
            letter-spacing:.3px;
            cursor:pointer;
        }
        .des-map-modes button[aria-pressed="true"] {
            background:#134a5c;
            border-color:#7af4ff;
            color:#e8fbff;
            box-shadow:0 0 10px rgba(122,244,255,.18);
        }
        .des-map-tools {
            display:flex;
            align-items:center;
            gap:4px;
            margin:0 0 5px;
        }
        .des-map-tools button {
            min-width:28px;
            min-height:26px;
            padding:2px 6px;
            border-radius:6px;
            border:1px solid #2a7a96;
            background:#0d2a38;
            color:#d7f4ff;
            font-size:11px;
            cursor:pointer;
        }
        .des-map-tools button:hover { border-color:#7af4ff; }
        #des-map-readout {
            flex:1;
            min-width:0;
            margin:0 0 0 4px;
            color:#b9d2df;
            font-size:10px;
            line-height:1.25;
            text-align:right;
        }
        .des-map-frame {
            position:relative;
            flex:1;
            min-height:0;
            border:1px solid #1f5f74;
            border-radius:8px;
            overflow:hidden;
            background:#050b12;
        }
        #des-map { cursor:crosshair; width:100%; height:100%; min-height:88px; display:block; }
        .des-map-legend {
            display:flex;
            align-items:center;
            gap:6px;
            margin-top:5px;
            color:#9ad7e4;
            font-size:9px;
            letter-spacing:.2px;
        }
        .des-map-swatch {
            flex:1;
            height:7px;
            border-radius:999px;
            border:1px solid #2a6173;
            background:linear-gradient(90deg,#2a4b58,#5d6864 28%,#898271 58%,#b1a58b);
        }
        .des-map-swatch.slope {
            background:linear-gradient(90deg,#1f8f72,#c4923a 55%,#8d3d48);
        }
        .des-map-stats {
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:4px;
            margin-top:5px;
        }
        .des-map-stats div {
            padding:4px 5px;
            border-radius:6px;
            border:1px solid #1d4f60;
            background:rgba(6,18,26,.9);
        }
        .des-map-stats span {
            display:block;
            color:#7eafc0;
            font-size:9px;
            letter-spacing:.4px;
        }
        .des-map-stats strong {
            display:block;
            margin-top:1px;
            color:#f4fbff;
            font-size:12px;
            letter-spacing:.2px;
        }
        .des-foot { display:grid; grid-template-columns:1.5fr repeat(3,minmax(0,1fr)); gap:8px; padding:0 8px 8px; }
        .des-chip { border:1px solid #14566c; border-radius:8px; padding:8px 10px; background:#07141e; }
        .des-chip span { display:block; color:#8fd8df; font-size:11px; letter-spacing:1px; }
        .des-chip strong { display:block; color:#f4fbff; font-size:16px; letter-spacing:.4px; }
        .des-chip.go strong { color:#3dff9a; }
        .des-chip.stop strong { color:#ff8a90; }
        .hab-concept { position:absolute; top:10px; left:10px; z-index:3; width:min(310px,52%); border:1px solid #54bfd1; background:rgba(4,10,16,.92); color:#e7f7ff; box-shadow:0 8px 22px #0008; }
        .hab-concept summary { padding:7px 9px; color:#7af4ff; font-size:11px; font-weight:700; letter-spacing:.5px; cursor:pointer; }
        .hab-concept ul { margin:0; padding:0 12px 9px 26px; font-size:12px; line-height:1.4; }
        .hab-concept li { margin:4px 0; }
        @media(max-width:900px) {
            .screen-nav { grid-template-columns:repeat(3,minmax(0,1fr)); }
            .des-body { grid-template-columns:1fr; overflow-y:auto; }
            .des-stage { min-height:min(62vh,520px); }
            .des-water { flex:0 0 auto; }
            .des-gauges { grid-template-rows:none; grid-template-columns:repeat(4,minmax(0,1fr)); min-height:120px; }
            .pros-cons { grid-template-columns:1fr; }
        }
        .hab-board { border:1px solid #14566c; border-radius:4px; background:#05080d; color:#d7f4ff; font-family:"Rajdhani","Segoe UI",sans-serif; }
        .hab-board.is-on { padding:0; }
        .hab-top { display:flex; align-items:center; gap:12px; min-height:36px; padding:4px 10px; background:linear-gradient(180deg,#0c1822,#071016); border-bottom:1px solid #1a6a82; white-space:nowrap; overflow:hidden; }
        .hab-brand { display:flex; align-items:center; gap:8px; color:#7eebf8; font-weight:700; letter-spacing:.8px; font-size:15px; }
        .hab-nasa { width:26px; height:26px; flex:none; }
        .hab-meta { display:flex; gap:12px; align-items:center; color:#b7e4ef; font-size:13px; font-weight:600; letter-spacing:.4px; }
        .hab-meta b { color:#e9fbff; font-weight:700; }
        .hab-meta b.ok { color:#3dff9a; }
        .hab-body { flex:1; min-height:0; display:grid; grid-template-columns:minmax(210px,.92fr) minmax(0,1.72fr) minmax(200px,.96fr); gap:7px; padding:7px; }
        .hab-left, .hab-center, .hab-right { min-width:0; min-height:0; display:flex; flex-direction:column; gap:7px; }
        .hab-pane { min-height:0; display:flex; flex-direction:column; border:1px solid #1a6d86; background:linear-gradient(180deg,rgba(8,20,30,.96),rgba(4,9,14,.98)); padding:6px 8px; box-shadow:inset 0 0 18px rgba(30,120,150,.08); }
        .hab-kicker { margin:0; color:#e7f7ff; font-size:13px; font-weight:700; letter-spacing:1px; }
        .hab-model { margin:0 0 4px; color:#7eafc0; font-size:11px; letter-spacing:.3px; }
        .hab-headers { flex:0 0 86px; }
        .hab-headers-row { flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:6px; align-items:center; }
        #hab-alt { width:100%; height:52px; display:block; }
        .hab-alt-read { display:flex; flex-direction:column; justify-content:center; gap:2px; color:#9fd4e2; font-size:12px; letter-spacing:.3px; }
        .hab-alt-read b { color:#f4fbff; font-weight:700; }
        .hab-ice { flex:1; }
        .hab-ice-top { flex:0 0 108px; height:108px; display:grid; grid-template-columns:minmax(0,1fr) 108px; gap:4px; align-items:end; }
        #hab-heat { width:100%; height:108px; display:block; }
        .hab-left { overflow:auto; }
        .hab-briefs { display:flex; flex-direction:column; gap:6px; margin-top:6px; }
        .hab-briefs p { margin:0; color:#e7f7ff; font-size:12px; line-height:1.35; }
        .hab-briefs b { display:block; color:#7af4ff; letter-spacing:.5px; font-size:11px; }
        .hab-ice-side { display:flex; flex-direction:column; justify-content:flex-end; min-width:0; }
        #hab-scatter { width:100%; height:78px; display:block; }
        .hab-ice-side p { margin:4px 0 0; color:#9fd4e2; font-size:11px; line-height:1.2; }
        .hab-ice-side strong { display:block; color:#f4fbff; font-size:13px; }
        .hab-bars { margin-top:4px; }
        .hab-bar { margin:4px 0; }
        .hab-bar p { display:flex; justify-content:space-between; gap:8px; margin:0 0 2px; color:#d5eef6; font-size:11px; letter-spacing:.5px; font-weight:600; }
        .hab-track { height:7px; background:#0d2430; border-radius:1px; overflow:hidden; }
        .hab-track b { display:block; height:100%; width:0; background:linear-gradient(90deg,#128eaa,#7af4ff); box-shadow:0 0 8px #3ee0f088; }
        .hab-track.amber b { background:linear-gradient(90deg,#c45a12,#ffb15a); box-shadow:0 0 8px #ff8a2a88; }
        .hab-foot { margin:4px 0 0; color:#8ec9d6; font-size:11px; letter-spacing:.2px; }
        .hab-crater { flex:1.62; position:relative; padding:0; overflow:hidden; background:#100e0c; }
        .hab-base-line { position:absolute; left:8px; right:8px; bottom:8px; z-index:3; margin:0; padding:7px 8px; border:1px solid #1c8eaa; background:rgba(4,10,16,.88); color:#e7f7ff; font-size:12px; line-height:1.35; }
        #hab-crater { position:absolute; inset:0; width:100%; height:100%; display:block; }
        .hab-badges { position:absolute; top:10px; right:10px; z-index:3; display:flex; flex-direction:column; align-items:flex-end; gap:6px; }
        .hab-badge { display:flex; align-items:center; gap:6px; padding:2px 8px; font-size:12px; font-weight:700; letter-spacing:.7px; background:rgba(4,10,16,.55); }
        .hab-badge.warn { color:#f0b429; }
        .hab-badge.ok { color:#3dff9a; border:1px solid #2dcca0; }
        .hab-badge svg { width:13px; height:13px; }
        .hab-leaders { position:absolute; inset:0; width:100%; height:100%; z-index:2; pointer-events:none; }
        .hab-leaders line { stroke:#e7f7ff; stroke-width:1.2; vector-effect:non-scaling-stroke; }
        .hab-call { position:absolute; z-index:3; color:#f4fbff; font-size:13px; font-weight:600; letter-spacing:.3px; text-shadow:0 1px 2px #000, 0 0 8px #042028; }
        .hab-laser { position:absolute; right:12px; bottom:8px; z-index:3; color:#9ae7f4; font-size:11px; letter-spacing:.4px; }
        .hab-scale { position:absolute; left:8px; top:46%; z-index:3; color:#9ae7f4; font-size:11px; letter-spacing:.6px; }
        .hab-thermal { flex:0.92; }
        .hab-thermal-body { flex:1; min-height:0; display:grid; grid-template-columns:86px minmax(0,1fr) 168px; gap:8px; }
        #hab-net, #hab-temp { width:100%; height:100%; display:block; min-height:0; }
        .hab-temp-wrap { min-width:0; min-height:0; display:flex; flex-direction:column; }
        #hab-temp { flex:1; }
        .hab-temp-scale { margin:0; text-align:center; color:#8ec9d6; font-size:11px; }
        .hab-conf-side .hab-kicker { margin-bottom:4px; }
        .hab-tsr { margin:6px 0 0; color:#d7f4ff; font-size:12px; font-weight:600; }
        .hab-network { flex:0 0 112px; }
        #hab-network { flex:1; width:100%; min-height:0; display:block; }
        .hab-geo { flex:1; }
        .hab-lat { margin:2px 0; color:#d7f4ff; font-size:12px; font-weight:600; letter-spacing:.4px; }
        #hab-rim { flex:1; width:100%; min-height:70px; display:block; }
        #hab-wave { width:100%; height:26px; display:block; }
        @media(max-width:900px) {
            .ops-top { grid-template-columns:minmax(0,1fr) auto; }
            .ops-mid, .ops-low { grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr); }
            .path-card { top:8px; }
            .topo-layout { grid-template-columns:minmax(0,1fr) 180px; }
            .hab-body { grid-template-columns:minmax(160px,.8fr) minmax(0,1.2fr) minmax(150px,.8fr); }
            .hab-thermal-body { grid-template-columns:70px minmax(0,1fr) 120px; }
            #topo-canvas, #ops-arc { height:auto; }
        }
        .screen { font-size:15px; line-height:1.45; }
        .screen h2 { font-size:clamp(20px,1.6vw,24px) !important; }
        .screen .ops-kicker, .screen .choice-title, .screen h3 { font-size:13px; letter-spacing:.8px; }
        .screen .purpose { font-size:14px; line-height:1.45; }
        .screen-nav button { min-height:46px; font-size:clamp(14px,1vw,16px); letter-spacing:.5px; }
        .path-board h2 { font-size:clamp(22px,2.4vw,34px) !important; }
        .path-card { font-size:14px; }
        .path-card h3 { font-size:14px; }
        .path-legend { font-size:14px; }
        .ops-note { font-size:14px; line-height:1.4; }
        .topo-head, .topo-foot, .topo-side label, .topo-row { font-size:13px; }
        .topo-legend div, .topo-chip span, .topo-fact p { font-size:12px; }
        .hab-meta { font-size:12px; }
        .hab-kicker { font-size:14px; }
        .hab-model, .hab-foot, .hab-lat, .hab-temp-scale, .hab-tsr { font-size:12px; }
        .hab-briefs p, .hab-base-line { font-size:13px; }
        .hab-bar p { font-size:12px; }
        .hab-concept summary { font-size:12px; }
        .hab-concept ul { font-size:13px; }
        .des-pane p, .des-note { font-size:12px; }
        .des-ice { font-size:13px; line-height:1.4; }
        .des-rate { font-size:clamp(28px,2.3vw,34px); }
        .des-chip span { font-size:12px; }
        .des-chip strong { font-size:clamp(16px,1.2vw,20px); }
        .des-caption { font-size:12px; }
        @media(max-width:900px) {
            .screen { font-size:14px; }
            .screen h2 { font-size:20px !important; }
            .path-card { width:min(180px,40vw); font-size:12px; }
            .path-card h3 { font-size:12px; }
            .path-legend { font-size:12px; }
            .des-body { gap:8px; padding:8px; }
            .des-foot { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .hab-concept { width:min(280px,70%); }
        }
        @media(max-width:1100px) {
            .des-body { grid-template-columns:minmax(0,1fr); overflow-y:auto; }
            .des-stage { min-height:min(58vh,520px); }
            .des-water { flex:0 0 auto; }
            .des-gauges { grid-template-rows:none; grid-template-columns:repeat(4,minmax(0,1fr)); min-height:120px; }
            .des-foot { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
        @media(min-width:901px) {
            .path-stage { min-height:clamp(280px,45vh,620px); }
        }
        :root { --bg:#0b1521; --panel:#172735; --line:#3c566a; --muted:#a9bfce; --cyan:#8ce4ef; --blue:#83c2f2; }
        body { background:radial-gradient(ellipse at 50% -24%,#29485e 0,#142432 42%,#0b1521 78%); color:#edf5fa; }
        .workspace { color:#edf5fa; }
        .console-header { border-color:#47657a; background:linear-gradient(90deg,rgba(24,44,59,.96),rgba(14,29,42,.92)); }
        .subtitle,.eyebrow,.tag { color:#b0c5d3; }
        .mission-name { color:#c6d6e0; }
        .mission-name strong { color:#a0e8f0; }
        .live { border-color:#468c78; background:#15362f; color:#a8f0cb; }
        .workflow-tabs,.screen-nav { border-color:#49677a; }
        .screen-nav button { border-color:#607f95; background:linear-gradient(180deg,#213c50,#182d3e); color:#e7f2f8; }
        .screen-nav button:hover { background:linear-gradient(180deg,#2c4e65,#20394e); }
        .screen-nav button[aria-pressed="true"] { border-color:#b8eff4; background:linear-gradient(180deg,#b8e9f2,#71b9d1); color:#0d2533; }
        #open-options { background:#152838; }
        .panel,.ops-board,.topo-board,.hab-board,.descent-board {
            border-color:#496b80;
            background:linear-gradient(155deg,rgba(28,48,64,.98),rgba(16,30,43,.98));
            box-shadow:inset 0 1px rgba(255,255,255,.07),0 12px 30px rgba(0,0,0,.24);
        }
        .ops-pane,.topo-side,.des-pane,.hab-pane,.des-chip {
            border-color:#405f75;
            background:linear-gradient(160deg,rgba(28,48,64,.96),rgba(17,32,45,.98));
            box-shadow:inset 0 1px rgba(255,255,255,.055);
        }
        .ops-top,.des-top,.hab-top { border-color:#496b80; background:linear-gradient(90deg,#1b3143,#142638 58%,#1b3143); }
        .ops-top { border-bottom-color:#78a7bd; }
        .ops-brand h2,.hab-brand,.ops-met span,.ops-kicker,.hab-kicker,.des-pane p { color:#c0e0ec; }
        .ops-brand h2 { color:#eaf5fa; }
        .ops-met strong,.ops-figures strong,.des-chip strong,.hab-alt-read b,.hab-ice-side strong,.topo-row strong { color:#f2f7fa; }
        .ops-lights b,.des-mission b,.des-clock b { color:#f1f7fa; }
        .purpose { border-left-color:#7fc8df; background:#1b3447; color:#e1edf3; }
        .purpose b,.topo-side h3,.hab-concept summary { color:#a9e3ed; }
        .path-board { border-color:#496b80; border-radius:8px; background:linear-gradient(160deg,#172b3b,#101e2b); }
        .path-board h2 { color:#b5eff5 !important; text-shadow:0 1px 10px rgba(74,178,204,.38) !important; }
        .path-card,.path-legend { border-color:#81a7b9; background:rgba(13,28,40,.92); color:#edf5fa; }
        .path-card h3 { color:#bdeaf0; }
        .path-card strong { color:#f2f7fa; }
        .path-go { color:#9cf2bd; text-shadow:none; }
        .path-gold { color:#ffe09a; }
        .path-cyan { color:#a5eaf2; }
        .path-red { color:#ff9da1; }
        .ops-note,.hab-model,.hab-foot,.hab-lat,.hab-temp-scale,.hab-tsr,.des-note,.des-ice { color:#b4c9d6 !important; }
        .hab-base-line,.des-caption,.des-concept { border-color:#7091a5; background:rgba(12,25,37,.9); color:#edf5fa; }
        .hab-meta { color:#c3d9e3; }
        .hab-meta b { color:#eff6fa; }
        .des-safe span,.des-chip span,.hab-bar p,.ops-figures span { color:#b9d2df; }
        .des-water { border-color:#52758b; }
        .des-tank { background:#102333; }
        .hab-track { background:#233b4b; }
        .topo-legend,.topo-fact { border-color:#52758b; background:rgba(15,30,43,.94); }
        .topo-chip span { border-color:#63859a; background:rgba(15,30,43,.95); }
        button,.choice-card { border-color:#668ba0; background:linear-gradient(180deg,#2b4a60,#20394e); color:#edf5fa; }
        button:hover,.choice-card:hover { background:linear-gradient(180deg,#385e76,#29465d); color:#fff; }
        button[aria-pressed="true"],.choice-card[aria-pressed="true"] { border-color:#b9edf2; background:linear-gradient(180deg,#b3e8f0,#6db4cc); color:#102838; box-shadow:0 3px 12px rgba(70,160,188,.18); }
        .calculate-button,#run-plan,#open-yard,#open-terrain { border-color:#a6e2eb; background:linear-gradient(180deg,#6bbbd2,#3a829f); color:#071c28; box-shadow:0 4px 14px rgba(38,137,166,.2); }
        input,textarea,select { border-color:#506b7e; background:#142535; color:#edf5fa; }
        input:focus,textarea:focus,select:focus { outline-color:#94d9e8; border-color:#94d9e8; }
        .note,.result,.warning { border-color:#506b7e; background:#192d3d; color:#c4d5df; }
        .result { border-color:#4b856c; background:#17352f; color:#d5f2e3; }
        .warning { border-color:#927b52; background:#3a3122; color:#f4e3bf; }
        .status-row,.route-evidence,.now-card,.score,.q-record { border-color:#49677a; background:#172a3a; }
        .map .leaflet-popup-content-wrapper,.map .leaflet-popup-tip { background:#1b2e3e; color:#edf5fa; }
        .leaflet-control-scale-line { background:rgba(20,37,53,.9); color:#edf5fa; }
        .screen.is-on { border-radius:10px; }
        @media(max-width:650px) {
            .screen-nav { grid-template-columns:repeat(3,minmax(0,1fr)); }
            .hab-body { grid-template-columns:1fr; overflow:auto; }
            .hab-crater { min-height:300px; }
            .hab-thermal { min-height:230px; }
        }

        /* ===== FINAL SCREEN LOOK · reference fidelity + ZPL data ===== */
        .screen-nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)) 128px; gap:8px; padding:0 10px 10px; }
        .screen-nav button {
            min-height:46px; border-radius:4px; border:1px solid #2a7a96;
            background:linear-gradient(180deg,#0d2433,#081820); color:#b6d6e2;
            font:700 12px/1.15 "Orbitron","Rajdhani",sans-serif; letter-spacing:.6px; text-transform:uppercase;
            box-shadow:inset 0 0 0 1px rgba(0,229,255,.08);
        }
        .screen-nav button[aria-pressed="true"] {
            background:linear-gradient(180deg,#1a4a5c,#0e3040); color:#7af4ff;
            border-color:#5eebff; box-shadow:0 0 16px rgba(0,229,255,.25), inset 0 0 12px rgba(0,229,255,.12);
        }

        /* --- OPS / SITE CALL (Artemisite layout) --- */
        .ops-board {
            margin:0 0 14px; padding:0; border:1px solid #1c6f86; border-radius:4px;
            background:#050a0e; color:#e9f7ff; box-shadow:inset 0 0 40px rgba(0,40,60,.35);
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
        }
        .ops-top {
            display:grid; grid-template-columns:minmax(0,1.5fr) auto minmax(240px,.75fr);
            gap:14px; align-items:center; padding:10px 14px;
            background:linear-gradient(90deg,#1a1810 0%,#0b151e 45%,#081018 100%);
            border-bottom:2px solid #c9a227;
        }
        .ops-brand img { width:44px; height:44px; border:1px solid #c9a227; border-radius:4px; background:#041018; }
        .ops-brand h2 {
            margin:0; font:800 20px/1.1 "Orbitron",sans-serif; letter-spacing:2px;
            color:#ffd700; text-shadow:0 0 12px rgba(255,215,0,.35); text-transform:uppercase;
        }
        .ops-brand p { margin:2px 0 0; color:#9ad7e4; letter-spacing:1.4px; font-size:11px; text-transform:uppercase; font-family:"Share Tech Mono",monospace; }
        .ops-met {
            text-align:center; padding:8px 14px; border:1px solid #149bae; border-radius:4px;
            background:rgba(4,16,24,.85); box-shadow:0 0 12px rgba(0,229,255,.12);
        }
        .ops-met span { display:block; color:#8fd8df; letter-spacing:1.6px; font-size:10px; font-family:"Orbitron",sans-serif; }
        .ops-met strong { color:#00e5ff; font:700 18px "Share Tech Mono",monospace; letter-spacing:1px; }
        .ops-lights { display:grid; grid-template-columns:1fr 1fr; gap:3px 14px; margin:0; padding:0; list-style:none; font-size:11px; letter-spacing:.8px; font-family:"Share Tech Mono",monospace; }
        .ops-lights b { color:#d7f6ff; }
        .ops-lights i { display:inline-block; width:8px; height:8px; margin-right:6px; border-radius:50%; background:#4dff8d; box-shadow:0 0 8px #4dff8d; }
        .ops-lights i.warn { background:#f4bd65; box-shadow:0 0 8px #f4bd65; }
        .ops-lights i.bad { background:#ff6b73; box-shadow:0 0 8px #ff6b73; }
        .ops-mid { display:grid; grid-template-columns:minmax(0,1.65fr) minmax(260px,.55fr); gap:10px; margin:10px; }
        .ops-low { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:10px; margin:0 10px 10px; }
        .ops-pane {
            min-width:0; padding:10px; border:1px solid #1c6f86; border-radius:4px;
            background:linear-gradient(180deg,#0b151e,#071018); box-shadow:inset 0 0 20px rgba(0,80,100,.1);
        }
        .ops-kicker {
            margin:0 0 8px; color:#8fd8df; letter-spacing:1.6px; font-size:10px;
            font-family:"Orbitron",sans-serif; text-transform:uppercase;
        }
        #ops-arc { display:block; width:100%; height:min(42vh,340px); background:#040c14; border:1px solid #12384a; }
        .ops-gauges { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
        .ops-gauges canvas {
            width:100%; height:118px; border:1px solid #1a4a5c; border-radius:4px;
            background:radial-gradient(circle at 50% 60%,#0e2430,#050a0e);
        }
        .ops-figures { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:10px; }
        .ops-figures div { padding-top:8px; border-top:1px solid #1c6f86; }
        .ops-figures span { display:block; color:#8fd8df; font-size:10px; letter-spacing:1.2px; font-family:"Orbitron",sans-serif; }
        .ops-figures strong { color:#00e5ff; font:700 22px "Share Tech Mono",monospace; }
        #ops-alt, #ops-slope {
            display:block; width:100%; height:130px; margin-top:6px;
            border:1px solid #12384a; background:#040c14;
        }
        .pros-cons { display:grid; grid-template-columns:1fr; gap:10px; max-height:min(42vh,340px); overflow:auto; }
        #ops-pros, #ops-cons { margin:0; padding-left:18px; }
        #ops-pros li, #ops-cons li {
            margin:6px 0; font-size:12px; line-height:1.4; font-family:"Share Tech Mono",monospace; letter-spacing:.3px;
        }

        /* --- PATHFINDER --- */
        .path-board {
            margin:0 0 14px; padding:0; border:1px solid rgba(52,117,139,.95); border-radius:4px;
            background:#02070d; box-shadow:inset 0 0 40px rgba(29,110,136,.2); overflow:hidden;
            font-family:"Rajdhani","Segoe UI",sans-serif;
        }
        .path-board h2 {
            margin:0; padding:14px 12px 8px; text-align:center;
            color:#66edf3 !important; letter-spacing:.18em !important;
            font:800 clamp(20px,2.4vw,36px)/1.1 "Orbitron",sans-serif !important;
            text-transform:uppercase;
            text-shadow:0 0 22px rgba(72,219,232,.9), 0 0 4px rgba(214,255,255,.95) !important;
        }
        .path-board > .purpose { margin:0 12px 8px; }
        .path-stage {
            position:relative; min-height:0; height:clamp(540px,64vh,860px); overflow:hidden;
            border-top:1px solid rgba(51,121,146,.95);
            background:#040a0f; box-shadow:inset 0 0 40px rgba(0,0,0,.55);
        }
        .path-card {
            position:absolute; top:14px; z-index:3; width:min(230px,28vw);
            border:1px solid rgba(0,229,255,.75); border-radius:2px;
            background:rgba(4,12,18,.82); padding:10px 12px;
            color:#e7f7ff; font-size:13px; line-height:1.4;
            box-shadow:0 0 18px rgba(0,229,255,.15), inset 0 0 0 1px rgba(0,229,255,.08);
            backdrop-filter:blur(6px);
        }
        .path-card h3 {
            margin:0 0 8px; color:#7af4ff; font:700 11px "Orbitron",sans-serif;
            letter-spacing:.2em; text-transform:uppercase;
        }
        .path-card p { margin:0 0 3px; font-family:"Share Tech Mono",monospace; font-size:12px; }
        .path-go { color:#4dff8d; text-shadow:0 0 10px rgba(77,255,141,.75); font-weight:700; }
        .path-legend {
            position:absolute; left:50%; bottom:12px; transform:translateX(-50%); z-index:4;
            display:flex; flex-wrap:wrap; justify-content:center; gap:6px 16px;
            padding:8px 14px; border:1px solid rgba(143,216,223,.85); border-radius:4px;
            background:rgba(4,12,18,.92); font-size:12px; letter-spacing:.06em; color:#eaf7ff;
            box-shadow:0 8px 24px rgba(0,0,0,.4); backdrop-filter:blur(4px);
        }

        /* --- TOPOGRAPHY --- */
        .topo-board {
            margin:0 0 14px; padding:0; border:1px solid #1c6f86; border-radius:4px;
            background:#05080d; color:#d7f6ff; overflow:hidden;
            font-family:"Rajdhani","Segoe UI",sans-serif;
        }
        .topo-head {
            display:flex; justify-content:space-between; align-items:center; gap:12px;
            padding:10px 14px; border-bottom:1px solid #1c6f86;
            background:linear-gradient(90deg,#0c1822,#071016);
            font:12px "Share Tech Mono",monospace; letter-spacing:1px; color:#8fd8df;
        }
        .topo-head h2 {
            margin:0; color:#7af4ff; letter-spacing:2px;
            font:800 16px "Orbitron",sans-serif; text-transform:uppercase;
            text-shadow:0 0 12px rgba(0,229,255,.35);
        }
        .topo-layout { display:grid; grid-template-columns:minmax(0,1fr) 268px; gap:0; min-height:0; }
        .topo-stage {
            position:relative; min-width:0; overflow:hidden;
            border-right:1px solid #1c6f86; background:#000;
        }
        #topo-canvas { display:block; width:100%; height:min(68vh,640px); }
        .topo-compass {
            position:absolute; top:14px; right:14px; width:84px; height:84px;
            border:1px solid #2f8ea8; border-radius:50%;
            display:grid; place-items:center; background:rgba(7,16,24,.88);
            box-shadow:0 0 16px rgba(0,229,255,.2);
        }
        .topo-legend {
            position:absolute; left:12px; bottom:12px; border:1px solid #1c6f86; border-radius:4px;
            background:rgba(7,16,24,.92); padding:10px 12px; backdrop-filter:blur(4px);
        }
        .topo-legend strong {
            display:block; margin-bottom:6px; color:#7af4ff;
            font:700 10px "Orbitron",sans-serif; letter-spacing:1.4px;
        }
        .topo-side {
            border:0; border-radius:0; background:#071018; padding:12px 14px;
            display:flex; flex-direction:column; gap:4px; overflow:auto;
        }
        .topo-side h3 {
            margin:12px 0 8px; padding-bottom:4px; border-bottom:1px solid #1c6f86;
            color:#7af4ff; font:700 11px "Orbitron",sans-serif; letter-spacing:1.6px;
        }
        .topo-side h3:first-child { margin-top:0; }
        .topo-side label {
            display:grid; grid-template-columns:1fr auto; gap:6px; align-items:center;
            margin:8px 0; font-size:12px; font-family:"Share Tech Mono",monospace;
        }
        .topo-side input[type=range] {
            width:100%; grid-column:1 / -1; accent-color:#00e5ff; height:4px;
        }
        .topo-row {
            display:flex; justify-content:space-between; align-items:center; gap:8px;
            margin:6px 0; font-size:13px; font-family:"Share Tech Mono",monospace;
        }
        .topo-row strong { color:#f4fbff; font-size:15px; }
        .topo-row input[type=checkbox] {
            appearance:none; width:42px; height:22px; border-radius:11px;
            border:1px solid #1c6f86; background:#0a1820; position:relative; cursor:pointer;
        }
        .topo-row input[type=checkbox]::after {
            content:"OFF"; position:absolute; inset:2px; border-radius:9px;
            background:#1a2a34; color:#8fd8df; font:700 9px "Orbitron",sans-serif;
            display:grid; place-items:center; letter-spacing:.5px;
        }
        .topo-row input[type=checkbox]:checked {
            border-color:#00e5ff; box-shadow:0 0 10px rgba(0,229,255,.35);
        }
        .topo-row input[type=checkbox]:checked::after {
            content:"ON"; background:linear-gradient(90deg,#0a5a6e,#00e5ff); color:#041018;
        }
        .topo-foot {
            display:flex; justify-content:space-between; gap:12px; padding:8px 14px;
            border-top:1px solid #1c6f86; font:11px "Share Tech Mono",monospace;
            letter-spacing:1px; color:#8fd8df; background:#071016;
        }

        /* --- REAL CRATER / INFO HUD UPGRADES --- */
        .hab-hud, .des-hud {
            position:absolute; z-index:4; display:grid; gap:4px;
            padding:8px 10px; border:1px solid #3ec6ff66; border-radius:2px;
            background:rgba(3,10,16,.88); backdrop-filter:blur(5px);
            font:11px "Share Tech Mono",monospace; color:#d7f4ff;
            box-shadow:0 0 18px rgba(62,198,255,.12);
        }
        .hab-hud { left:10px; bottom:42px; min-width:210px; max-width:46%; }
        .des-hud { right:12px; top:56px; min-width:200px; max-width:42%; }
        .hab-hud b, .des-hud b { color:#7af4ff; font-weight:700; }
        .hab-hud strong, .des-hud strong {
            display:block; margin-bottom:2px; color:#4da3ff;
            font:700 10px "Orbitron",sans-serif; letter-spacing:1.2px;
        }
        .hab-scale, .des-lola-badge {
            position:absolute; z-index:4; left:10px; top:12px;
            padding:4px 8px; border:1px solid #39ff1466; border-radius:2px;
            background:rgba(4,18,12,.86); color:#39ff14;
            font:700 10px "Orbitron",sans-serif; letter-spacing:1px;
            box-shadow:0 0 12px rgba(57,255,20,.2);
        }
        .des-lola-badge { left:auto; right:12px; top:12px; }
        .hab-base-line {
            position:absolute; left:10px; right:10px; bottom:8px; z-index:3;
            margin:0; padding:6px 8px; border:1px solid #537d90;
            border-radius:2px; background:rgba(3,10,16,.84);
            color:#d7f4ff; font:11px "Share Tech Mono",monospace; line-height:1.35;
        }
        #ops-alt, #ops-slope, #hab-rim, #hab-alt, #hab-temp {
            background:
                linear-gradient(180deg, rgba(12,28,40,.2), rgba(2,6,10,.55)),
                radial-gradient(ellipse at 50% 120%, rgba(62,198,255,.12), transparent 55%),
                #061018;
        }
        .hab-crater, .des-stage {
            background: radial-gradient(ellipse at 50% 18%, #1a2a38 0%, #05080d 55%, #020406 100%);
        }
        .topo-stage {
            box-shadow:inset 0 0 60px rgba(0,30,50,.45), 0 0 24px rgba(62,198,255,.08);
        }

        /* --- HABITAT SCANNER --- */
        .hab-board {
            border:1px solid #14566c; border-radius:4px; background:#05080d; color:#d7f4ff;
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
        }
        .hab-top {
            display:flex; align-items:center; gap:14px; min-height:48px; padding:8px 14px;
            background:linear-gradient(90deg,#0c1822,#071016 40%,#0c1822);
            border-bottom:1px solid #1a6a82; overflow:hidden;
        }
        .hab-brand {
            display:flex; align-items:center; gap:10px; color:#f4fbff;
            font:800 15px "Orbitron",sans-serif; letter-spacing:1.2px; text-transform:uppercase;
            white-space:nowrap;
        }
        .hab-brand img, .hab-nasa { width:32px; height:32px; flex:none; border-radius:4px; border:1px solid #2f8ea8; }
        .hab-meta {
            display:flex; flex-wrap:wrap; gap:10px 16px; align-items:center; margin-left:auto;
            color:#b7e4ef; font:12px "Share Tech Mono",monospace; letter-spacing:.4px;
        }
        .hab-meta b.ok { color:#4dff8d; text-shadow:0 0 8px rgba(77,255,141,.5); }
        .hab-body {
            flex:1; min-height:0;
            display:grid; grid-template-columns:minmax(220px,.95fr) minmax(0,1.7fr) minmax(210px,.95fr);
            gap:8px; padding:8px;
        }
        .hab-pane {
            min-height:0; display:flex; flex-direction:column;
            border:1px solid #1a6d86; border-radius:2px;
            background:linear-gradient(180deg,rgba(8,20,30,.98),rgba(4,9,14,.99));
            padding:8px 10px; box-shadow:inset 0 0 24px rgba(30,120,150,.1);
        }
        .hab-kicker {
            margin:0 0 6px; color:#7af4ff; font:700 11px "Orbitron",sans-serif; letter-spacing:1.4px;
        }
        .hab-bar p {
            display:flex; justify-content:space-between; gap:8px; margin:0 0 3px;
            color:#d5eef6; font:600 11px "Share Tech Mono",monospace; letter-spacing:.4px;
        }
        .hab-track { height:8px; background:#0d2430; border-radius:1px; overflow:hidden; border:1px solid #12384a; }
        .hab-track b { display:block; height:100%; background:linear-gradient(90deg,#128eaa,#7af4ff); box-shadow:0 0 10px #3ee0f088; }
        .hab-track.amber b { background:linear-gradient(90deg,#c45a12,#ffb15a); box-shadow:0 0 10px #ff8a2a88; }
        .hab-badge {
            display:flex; align-items:center; gap:6px; padding:4px 10px;
            font:700 11px "Orbitron",sans-serif; letter-spacing:.8px;
            background:rgba(4,10,16,.75); border:1px solid #1c6f86;
        }
        .hab-badge.ok { color:#4dff8d; border-color:#4dff8d; box-shadow:0 0 10px rgba(77,255,141,.25); }
        .hab-badge.warn { color:#ffb15a; border-color:#ffb15a; box-shadow:0 0 10px rgba(255,177,90,.25); }

        /* --- DESCENT SIMULATOR --- */
        .descent-board {
            border:1px solid #14566c; border-radius:4px; background:#050b14; color:#e7f6ff;
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
            box-shadow:inset 0 0 40px rgba(0,60,100,.2);
        }
        .des-top {
            display:flex; align-items:center; gap:18px; min-height:56px; padding:10px 16px;
            background:linear-gradient(90deg,#071018,#0c2433 40%,#071018);
            border-bottom:1px solid #1a6d86;
        }
        .des-brand { display:flex; align-items:center; gap:12px; min-width:250px; }
        .des-mark {
            display:grid; place-items:center; width:40px; height:40px;
            border:2px solid #4da3ff; border-radius:50%; color:#7af4ff; font-size:18px;
            box-shadow:0 0 14px rgba(77,163,255,.45); background:#041018;
        }
        .des-brand strong {
            display:block; letter-spacing:2px; font:800 16px "Orbitron",sans-serif; color:#e8f4ff;
        }
        .des-brand small {
            color:#4da3ff; letter-spacing:1.6px; font:700 10px "Orbitron",sans-serif;
        }
        .des-live {
            display:flex; align-items:center; gap:8px; color:#39ff14;
            font:700 12px "Orbitron",sans-serif; letter-spacing:1.2px;
        }
        .des-live i { width:9px; height:9px; border-radius:50%; background:#39ff14; box-shadow:0 0 12px #39ff14; }
        .des-mission { margin-left:auto; letter-spacing:1px; color:#9ad7e4; font:13px "Share Tech Mono",monospace; }
        .des-mission b, .des-clock b { color:#f4fbff; }
        .des-clock { letter-spacing:1px; font:14px "Share Tech Mono",monospace; color:#9ad7e4; }
        .des-body {
            flex:1; min-height:0;
            display:grid; grid-template-columns:230px minmax(0,1fr) 250px;
            gap:10px; padding:10px;
        }
        .des-pane {
            min-height:0; border:1px solid #4da3ff55; border-radius:2px;
            background:linear-gradient(180deg,#0c1c28,#071018);
            padding:10px; display:flex; flex-direction:column;
            box-shadow:0 0 0 1px rgba(77,163,255,.08), inset 0 0 20px rgba(0,80,140,.08);
            clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
        }
        .des-pane > p:first-child {
            margin:0 0 6px; color:#4da3ff; letter-spacing:1.4px;
            font:700 10px "Orbitron",sans-serif;
        }
        .des-gauges {
            flex:1; min-height:0; display:grid; grid-template-rows:repeat(4,minmax(0,1fr)); gap:8px;
        }
        .des-gauges canvas {
            width:100%; height:100%; min-height:72px; display:block;
            border:1px solid #1a4a5c; border-radius:2px;
            background:radial-gradient(circle at 50% 55%,#0e2430,#050a0e);
        }
        .des-safe strong { display:block; margin-top:4px; color:#39ff14; font:800 24px "Orbitron",sans-serif; letter-spacing:.5px; text-shadow:0 0 12px rgba(57,255,20,.4); }
        .des-safe strong.hold { color:#ff8c00; text-shadow:0 0 12px rgba(255,140,0,.4); }
        .des-stage {
            position:relative; min-height:320px; border:1px solid #4da3ff66; border-radius:2px;
            overflow:hidden; background:#02060c;
            box-shadow:inset 0 0 40px rgba(0,40,80,.35), 0 0 20px rgba(77,163,255,.1);
        }
        .des-concept {
            position:absolute; top:12px; left:12px; z-index:2; max-width:min(300px,50%);
            padding:8px 12px; border:1px solid #4da3ff88; border-radius:2px;
            background:rgba(3,10,18,.86); color:#e6f4ff; font-size:12px; line-height:1.35;
            backdrop-filter:blur(4px);
        }
        .des-concept strong { display:block; color:#4da3ff; letter-spacing:1px; font:700 10px "Orbitron",sans-serif; }
        .des-caption {
            position:absolute; left:12px; bottom:12px; z-index:2; margin:0; max-width:70%;
            padding:6px 10px; border:1px solid #4da3ff66; border-radius:2px;
            background:rgba(3,10,16,.88); color:#d7f4ff; font:11px "Share Tech Mono",monospace;
        }
        .des-rate { margin:2px 0; color:#4da3ff; font:800 28px "Share Tech Mono",monospace; letter-spacing:.5px; text-shadow:0 0 10px rgba(77,163,255,.35); }
        .des-tank {
            position:relative; width:36px; height:84px; margin:0; flex:none;
            border:1px solid #3ec6ff; border-radius:6px; background:#041018; overflow:hidden;
            box-shadow:0 0 14px rgba(62,198,255,.35), inset 0 0 12px rgba(62,198,255,.15);
        }
        .des-tank i { position:absolute; left:0; right:0; bottom:0; background:linear-gradient(180deg,#b8fbff,#1278c8); box-shadow:0 0 16px #3ec6ff; }
        .des-foot {
            display:grid; grid-template-columns:1.6fr repeat(3,minmax(0,1fr)); gap:8px;
            padding:10px; background:#061018; border-top:1px solid #39ff1455;
        }
        .des-chip {
            border:1px solid #14566c; border-radius:2px; padding:10px 12px; background:#07141e;
            clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
        }
        .des-chip span { display:block; color:#8fd8df; font:700 10px "Orbitron",sans-serif; letter-spacing:1.2px; margin-bottom:2px; }
        .des-chip strong { display:block; color:#f4fbff; font:700 16px "Share Tech Mono",monospace; letter-spacing:.4px; }
        .des-chip.go { border-color:#39ff1466; box-shadow:0 0 14px rgba(57,255,20,.15); }
        .des-chip.go strong { color:#39ff14; text-shadow:0 0 10px rgba(57,255,20,.4); }
        .des-chip.stop strong { color:#ff6b73; }


        .ops-board > .purpose,
        .path-board > .purpose,
        .topo-board > .purpose,
        .hab-board > .purpose {
            margin: 0 10px 6px; opacity: .72; font-size: 12px;
        }

        @media(max-width:1000px) {
            .ops-mid, .ops-low, .topo-layout, .hab-body, .des-body { grid-template-columns:1fr; }
            .path-stage { height:480px; }
            #topo-canvas { height:420px; }
            .des-gauges { grid-template-rows:none; grid-template-columns:repeat(4,minmax(0,1fr)); min-height:110px; }
            .des-foot { grid-template-columns:1fr 1fr; }
            .screen-nav { grid-template-columns:repeat(3,minmax(0,1fr)); }
        }


        /* ===== NO-OVERLAP LAYOUT FIX ===== */
        html, body { height:100%; overflow:hidden; }
        .workspace { overflow:hidden; }
        .screen.is-on {
            display:flex; flex-direction:column; flex:1; min-height:0;
            overflow:auto; margin:0 10px 10px;
        }
        .ops-board.is-on, .path-board.is-on, .topo-board.is-on,
        .hab-board.is-on, .descent-board.is-on {
            overflow:auto;
        }

        /* Ops: room for dials + figures, no clipped stacks */
        .ops-board.is-on { overflow:auto; gap:0; }
        .ops-mid, .ops-low {
            display:grid !important;
            grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) !important;
            gap:12px !important; align-items:start; margin:10px !important;
        }
        .ops-gauges { gap:10px; align-items:stretch; }
        .ops-gauges canvas {
            width:100%; height:148px; min-height:148px;
            border:1px solid #1a4a5c; border-radius:4px;
            background:radial-gradient(circle at 50% 55%,#0e2430,#050a0e);
        }
        .ops-figures {
            display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
            gap:10px; margin-top:10px; flex:none;
        }
        .ops-figures div {
            padding:8px 6px 6px; border-top:1px solid #1c6f86;
            min-width:0;
        }
        .ops-figures span {
            display:block; color:#8fd8df; font-size:10px;
            letter-spacing:1.2px; font-family:"Orbitron",sans-serif;
            margin-bottom:2px;
        }
        .ops-figures strong {
            display:block; color:#00e5ff;
            font:700 20px/1.2 "Share Tech Mono",monospace;
            word-break:break-word;
        }
        .ops-pane {
            overflow:visible; min-height:0; height:auto !important;
            display:block !important;
        }
        .ops-pane #ops-alt, .ops-pane #ops-slope {
            height:130px !important; min-height:130px; margin-top:8px;
        }
        .pros-cons { max-height:none; overflow:visible; }
        .purpose {
            white-space:normal; overflow-wrap:anywhere; line-height:1.4;
        }
        @media(max-width:1100px) {
            .ops-mid, .ops-low {
                grid-template-columns:1fr !important;
            }
        }

        /* Pathfinder: cards beside the map, legend under it */
        .path-stage {
            display:grid !important;
            grid-template-columns:minmax(200px,240px) minmax(0,1fr) minmax(200px,240px);
            grid-template-rows:minmax(320px,1fr) auto;
            gap:10px; padding:10px;
            position:relative; min-height:0;
            height:clamp(480px,62vh,780px);
            overflow:hidden;
            border-top:1px solid rgba(51,121,146,.95);
            background:#040a0f;
        }
        .path-map-wrap {
            grid-column:2; grid-row:1; position:relative;
            min-width:0; min-height:0; overflow:hidden;
            border:1px solid rgba(51,121,146,.7); background:#02070d;
        }
        #path-map {
            position:absolute !important; inset:0 !important;
            display:block; width:100%; height:100%; min-height:0;
            background:#040a0f;
        }
        .path-card {
            position:static !important; top:auto !important;
            left:auto !important; right:auto !important;
            z-index:auto; width:auto !important;
            max-width:none; align-self:stretch;
            overflow:auto; max-height:100%;
        }
        .path-card-left { grid-column:1; grid-row:1; }
        .path-card-right { grid-column:3; grid-row:1; }
        .path-legend {
            grid-column:1 / -1; grid-row:2;
            position:static !important; left:auto !important; bottom:auto !important;
            transform:none !important; z-index:auto;
            width:auto; max-width:none; margin:0;
            justify-content:center;
        }

        /* Habitat: stop overlays eating the drawing / columns */
        .hab-board.is-on { overflow:auto; }
        .hab-body {
            flex:1; min-height:min(72vh,820px);
            align-items:stretch;
        }
        .hab-left, .hab-center, .hab-right {
            min-height:0; overflow:auto;
            display:flex; flex-direction:column; gap:8px;
        }
        .hab-pane { overflow:auto; }
        .hab-crater {
            flex:1.4; min-height:280px; position:relative;
            overflow:hidden; padding:0;
        }
        .hab-concept {
            position:absolute; top:10px; left:10px; z-index:4;
            width:min(280px,46%); max-height:42%;
            overflow:auto; border:1px solid #54bfd1;
            background:rgba(4,10,16,.94); color:#e7f7ff;
            box-shadow:0 8px 22px #0008;
        }
        .hab-concept[open] { max-height:min(58%,320px); }
        .hab-base-line {
            position:absolute; left:8px; right:8px; bottom:8px; z-index:3;
            margin:0; padding:7px 8px; max-height:28%; overflow:auto;
            border:1px solid #1c8eaa; background:rgba(4,10,16,.9);
            color:#e7f7ff; font-size:12px; line-height:1.35;
        }
        .hab-badges { z-index:4; }
        .hab-thermal { flex:0 0 auto; min-height:210px; }
        .hab-ice-side p {
            display:flex; flex-direction:column; gap:2px;
            margin:4px 0 0; color:#9fd4e2; font-size:11px; line-height:1.25;
        }
        .hab-ice-side strong { display:block; color:#f4fbff; font-size:13px; }
        .hab-bar p {
            display:flex; justify-content:space-between; align-items:baseline;
            gap:10px; margin:0 0 3px;
        }
        .hab-bar p > span:last-child {
            flex:none; text-align:right; color:#f4fbff; white-space:nowrap;
        }
        .hab-geo { overflow:auto; }
        .hab-briefs p { margin:0 0 6px; }

        /* Descent overlays: keep readable, don't cover the whole stage */
        .des-concept {
            max-width:min(260px,40%); max-height:30%; overflow:auto;
        }
        .des-caption {
            max-width:min(55%,420px); max-height:22%; overflow:auto;
        }
        .des-body { overflow:auto; }
        .des-stage { min-height:300px; }

        /* Topo chips / fact card stay clear of the compass */
        .topo-fact { max-width:min(280px,42%); }
        .topo-legend { max-width:min(200px,40%); }

        .screen-nav {
            display:grid !important; grid-template-columns:repeat(6,minmax(0,1fr)) !important;
            gap:12px !important; padding:0 10px 12px !important;
        }
        .screen-nav button { min-width:0; padding:10px 8px; white-space:normal; line-height:1.2; }
        .path-card { overflow:visible; max-height:none; }
        .path-card p { overflow-wrap:anywhere; }
        .path-map-wrap { min-height:0; height:100%; }
        @media(max-width:1200px) {
            .path-stage {
                grid-template-columns:minmax(0,1fr) !important;
                grid-template-rows:auto auto minmax(380px,52vh) auto !important;
                height:auto; min-height:640px; gap:10px;
            }
            .path-card-left { grid-column:1; grid-row:1; }
            .path-card-right { grid-column:1; grid-row:2; }
            .path-map-wrap { grid-column:1; grid-row:3; min-height:380px; height:auto; }
            .path-legend { grid-column:1; grid-row:4; flex-wrap:wrap; }
            .hab-body { grid-template-columns:1fr; min-height:0; }
            .hab-crater { min-height:320px; }
            .screen-nav { grid-template-columns:repeat(3,minmax(0,1fr)) !important; }
        }
        @media(min-width:1201px) {
            .path-stage {
                grid-template-columns:minmax(200px,240px) minmax(0,1fr) minmax(200px,240px) !important;
                grid-template-rows:minmax(320px,1fr) auto !important;
            }
            .path-card-left { grid-column:1; grid-row:1; }
            .path-card-right { grid-column:3; grid-row:1; }
            .path-map-wrap { grid-column:2; grid-row:1; }
            .path-legend { grid-column:1 / -1; grid-row:2; }
        }
        @media(max-width:700px) {
            .ops-gauges { grid-template-columns:1fr 1fr; }
            .ops-gauges canvas { height:132px; min-height:132px; }
            .screen-nav { grid-template-columns:repeat(2,minmax(0,1fr)) !important; }
            .path-stage { grid-template-rows:auto auto minmax(300px,48vh) auto !important; }
            .path-map-wrap { min-height:300px; }
        }


        /* ===== CHROME + FIT + PATH TOOLS ===== */
        html, body {
            height:100% !important; max-height:100dvh !important;
            overflow:hidden !important; margin:0 !important; padding:0 !important;
        }
        .shell {
            position:fixed !important; inset:0 !important;
            height:100dvh !important; max-height:100dvh !important;
            overflow:hidden !important; margin:0 !important;
        }
        .workspace {
            position:absolute !important; inset:0 !important;
            display:flex !important; flex-direction:column !important;
            gap:0 !important; padding:44px 6px 4px !important; min-height:0 !important;
            height:auto !important; max-height:none !important;
            overflow:hidden !important; margin:0 !important; box-sizing:border-box !important;
        }
        #page-simulator-panel {
            display:flex !important; flex-direction:column !important;
            flex:1 1 auto !important; min-height:0 !important; overflow:hidden !important;
        }
        .screen[hidden], .screen:not(.is-on) { display:none !important; }
        #stage, .feature-stage, .kept-record, #page-home-panel:not(.is-on) {
            position:absolute !important; width:1px !important; height:1px !important;
            overflow:hidden !important; clip:rect(0 0 0 0) !important; pointer-events:none !important;
        }
        .options-drawer #page-home-panel {
            position:static !important; width:auto !important; height:auto !important;
            clip:auto !important; overflow:visible !important; pointer-events:auto !important;
        }
        .chrome-toggle {
            position:fixed; z-index:80; top:10px; left:10px;
            width:44px; height:40px; padding:9px 10px;
            display:flex; flex-direction:column; justify-content:space-between;
            border:1px solid #5eb4cc; border-radius:8px;
            background:rgba(6,18,28,.96); box-shadow:0 8px 24px #000a;
            cursor:pointer;
        }
        .chrome-toggle span {
            display:block; height:3px; border-radius:2px;
            background:#7af4ff; box-shadow:0 0 8px rgba(122,244,255,.45);
        }
        .chrome-toggle[aria-expanded="true"] {
            border-color:#9af6ff; background:#12384c;
        }
        .chrome-panel {
            position:fixed; z-index:75; top:56px; left:10px;
            width:min(440px, calc(100vw - 20px));
            max-height:calc(100vh - 70px); overflow:auto;
            padding:10px; border:1px solid #5eb4cc; border-radius:12px;
            background:rgba(5,14,22,.98); box-shadow:0 18px 50px #000c;
        }
        .chrome-panel[hidden] { display:none !important; }
        .chrome-panel .console-header {
            position:static !important; flex-wrap:wrap; gap:8px;
            min-height:0; margin:0 0 10px; padding:0 0 10px;
            border-bottom:1px solid #1c6f86; background:transparent;
        }
        .chrome-panel .screen-nav {
            display:grid !important; grid-template-columns:1fr !important;
            gap:8px !important; padding:0 !important;
        }
        .chrome-panel .screen-nav button {
            min-height:42px; text-align:left; padding:10px 12px;
        }
        .chrome-backdrop {
            position:fixed; inset:0; z-index:70; background:rgba(2,8,14,.45);
        }
        .chrome-backdrop[hidden] { display:none !important; }
        .workspace > .console-header,
        .workspace > .screen-nav,
        .workspace > .app-tabs { display:none !important; }

        .screen.is-on {
            display:flex !important; flex-direction:column !important;
            flex:1 1 auto !important; min-height:0 !important;
            height:100% !important; max-height:none !important;
            overflow:hidden !important; margin:0 !important; padding:0 !important;
        }
        .screen .purpose, .screen .ops-note, .path-board > h2,
        .topo-board > .purpose, .hab-board > .purpose { display:none !important; }
        .ops-board.is-on, .path-board.is-on, .topo-board.is-on,
        .hab-board.is-on, .descent-board.is-on {
            overflow:hidden !important; height:100% !important;
            max-height:calc(100dvh - 48px) !important;
        }

        /* Ops fit */
        .ops-board.is-on {
            display:grid !important;
            grid-template-rows:auto auto minmax(0,1.15fr) minmax(0,.95fr) !important;
            gap:6px !important;
        }
        .ops-pane.is-focus {
            outline:1px solid #7af4ff;
            box-shadow:0 0 18px rgba(122,244,255,.25);
        }
        .ops-top { min-height:0; padding:6px 10px !important; }
        .ops-mid, .ops-low {
            min-height:0 !important; margin:0 6px !important; gap:8px !important;
            grid-template-columns:minmax(0,1.25fr) minmax(0,1fr) !important;
            overflow:hidden !important;
        }
        .ops-low { margin-bottom:6px !important; }
        .ops-pane { min-height:0 !important; overflow:hidden !important; padding:6px 8px !important; }
        .ops-gauges canvas { height:min(14vh,110px) !important; min-height:88px !important; }
        #ops-arc { height:100% !important; min-height:0 !important; }
        #ops-alt, #ops-slope { height:42% !important; min-height:70px !important; }
        .ops-figures { margin-top:4px !important; }
        .ops-figures strong { font-size:16px !important; }
        .pros-cons { max-height:100% !important; overflow:auto !important; }
        .ops-interact {
            display:flex; flex-wrap:wrap; gap:6px; margin:0 6px 4px;
        }
        .ops-interact button {
            min-height:30px; padding:5px 9px; font-size:11px;
            border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; cursor:pointer;
        }
        .ops-interact button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
        }

        /* Path fit + tools */
        .path-board.is-on {
            display:grid !important;
            grid-template-rows:auto minmax(0,1fr) !important;
            gap:4px !important; padding:4px !important;
            max-height:calc(100dvh - 48px) !important;
        }
        .path-tools {
            display:flex; flex-wrap:wrap; align-items:center; gap:4px;
            padding:2px;
            max-height:36px; overflow:hidden;
        }
        .path-tools button, .path-tools label {
            min-height:30px; border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; padding:4px 9px;
            font:700 11px "Share Tech Mono",monospace; cursor:pointer;
        }
        .path-tools button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
            box-shadow:0 0 10px rgba(122,244,255,.2);
        }
        .path-tools label {
            display:flex; align-items:center; gap:6px; cursor:default;
        }
        .path-tools input[type=range] { width:90px; accent-color:#5eebff; }
        .path-stage {
            display:grid !important;
            grid-template-columns:minmax(180px,220px) minmax(0,1fr) minmax(180px,220px) !important;
            grid-template-rows:minmax(0,1fr) auto !important;
            height:100% !important; min-height:0 !important;
            gap:8px !important; padding:6px !important; overflow:hidden !important;
        }
        .path-card {
            position:static !important; width:auto !important;
            max-height:100%; overflow:auto; font-size:12px !important;
        }
        .path-card-left { grid-column:1; grid-row:1; }
        .path-card-right { grid-column:3; grid-row:1; }
        .path-map-wrap {
            grid-column:2; grid-row:1; position:relative;
            min-height:0 !important; height:100% !important;
            border:1px solid #1c6f86; overflow:hidden; cursor:crosshair;
        }
        .path-map-wrap.is-panning { cursor:grabbing; }
        #path-map { position:absolute !important; inset:0 !important; width:100%; height:100%; }
        .path-legend {
            grid-column:1 / -1; grid-row:2;
            position:static !important; transform:none !important;
            left:auto !important; bottom:auto !important;
            width:auto; max-width:none; margin:0; justify-content:center;
            padding:5px 8px !important; font-size:11px !important;
        }
        .path-probe {
            position:absolute; z-index:5; left:10px; bottom:10px;
            max-width:min(280px,70%); padding:7px 9px;
            border:1px solid #5eb4cc; border-radius:6px;
            background:rgba(4,12,18,.94); color:#e7f7ff;
            font:12px "Share Tech Mono",monospace; pointer-events:none;
        }
        .path-probe[hidden] { display:none !important; }
        .path-probe strong { color:#7af4ff; }

        /* Topo / habitat / descent fill */
        .topo-board.is-on {
            display:grid !important; grid-template-rows:auto minmax(0,1fr) auto !important;
            gap:4px !important; padding:6px !important;
        }
        .topo-layout { min-height:0 !important; height:100% !important; margin:0 !important; }
        #topo-canvas { height:100% !important; min-height:0 !important; }

        /* ===== BASE PLACEMENT / HABITAT PRODUCTION ===== */
        .hab-board.is-on {
            display:grid !important;
            grid-template-rows:auto auto auto minmax(0,1fr) !important;
            gap:4px !important; padding:6px !important;
            max-height:calc(100dvh - 48px) !important;
            overflow:hidden !important;
        }
        .hab-top {
            display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between;
            gap:8px; padding:4px 8px; border:1px solid #1f6f88; border-radius:8px;
            background:linear-gradient(180deg,#0b2432,#07141e);
        }
        .hab-brand span {
            font:800 13px "Share Tech Mono",monospace; letter-spacing:.12em;
            color:#7af4ff; text-transform:uppercase;
        }
        .hab-meta { display:flex; flex-wrap:wrap; gap:10px; font:11px "Share Tech Mono",monospace; color:#9ad7e2; }
        .hab-meta b { color:#e7f7ff; }
        .hab-meta b.ok { color:#39f08a; }
        .hab-meta b.warn { color:#f0c14a; }
        .hab-meta b.bad { color:#ff6b75; }
        .hab-tools {
            display:flex; flex-wrap:wrap; align-items:center; gap:4px;
            max-height:40px; overflow:auto; padding:2px 4px;
        }
        .hab-tools button, .hab-tools label {
            min-height:30px; border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; padding:4px 9px;
            font:700 11px "Share Tech Mono",monospace; cursor:pointer;
        }
        .hab-tools button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
            box-shadow:0 0 10px rgba(122,244,255,.2);
        }
        .hab-body {
            display:grid !important;
            grid-template-columns:minmax(210px,250px) minmax(0,1.4fr) minmax(220px,280px) !important;
            gap:8px !important; min-height:0 !important; height:100% !important;
            overflow:hidden !important; margin:0 !important;
        }
        .hab-left, .hab-right, .hab-center {
            display:flex; flex-direction:column; gap:6px; min-height:0; overflow:hidden;
        }
        .hab-pane {
            border:1px solid #1c5f78; border-radius:8px; background:#07141c;
            padding:7px 8px; min-height:0; overflow:auto;
        }
        .hab-pane.hab-crater, .hab-pane.hab-yard {
            position:relative; flex:1; overflow:hidden; padding:0;
        }
        .hab-kicker {
            margin:0 0 5px; color:#7af4ff; font:700 10px "Share Tech Mono",monospace;
            letter-spacing:.14em; text-transform:uppercase;
        }
        .hab-endurance {
            display:grid; gap:5px;
        }
        .hab-endurance .hab-end-row {
            display:flex; justify-content:space-between; gap:8px;
            border-top:1px solid #16384a; padding-top:4px;
            font:12px "Share Tech Mono",monospace; color:#9ad7e2;
        }
        .hab-endurance strong { color:#e7f7ff; }
        .hab-endurance strong.good { color:#39f08a; }
        .hab-endurance strong.watch { color:#f0c14a; }
        .hab-endurance strong.bad { color:#ff6b75; }
        .hab-end-meter {
            height:7px; border-radius:99px; background:#102633; overflow:hidden; margin-top:3px;
        }
        .hab-end-meter > i {
            display:block; height:100%; width:20%;
            background:linear-gradient(90deg,#2bb8c9,#7af4ff);
        }
        .hab-comp-grid {
            display:grid; grid-template-columns:1fr 1fr; gap:4px;
        }
        .hab-comp-grid button {
            text-align:left; min-height:44px; padding:6px 8px;
            border:1px solid #2a6078; border-radius:7px; background:#0a1c28;
            color:#d7f4ff; cursor:pointer; font:700 11px "Share Tech Mono",monospace;
        }
        .hab-comp-grid button small {
            display:block; margin-top:2px; color:#7ea8b8; font-weight:500; font-size:9px;
        }
        .hab-comp-grid button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
        }
        .hab-split {
            display:grid; grid-template-rows:minmax(0,1.15fr) minmax(0,.85fr);
            gap:6px; min-height:0; height:100%;
        }
        #hab-crater, #base-canvas {
            position:absolute; inset:0; width:100%; height:100%; display:block;
        }
        .hab-hud, .hab-yard-hud {
            position:absolute; z-index:3; left:8px; top:8px;
            max-width:min(280px,55%); padding:7px 9px;
            border:1px solid #2f8ea8; border-radius:7px;
            background:rgba(4,12,18,.9); color:#e7f7ff;
            font:11px "Share Tech Mono",monospace; pointer-events:none;
        }
        .hab-hud strong, .hab-yard-hud strong { display:block; color:#7af4ff; margin-bottom:3px; }
        .hab-hud span, .hab-yard-hud span { display:block; margin-top:2px; color:#9ad7e2; }
        .hab-hud b, .hab-yard-hud b { color:#f4fbff; }
        .hab-scale {
            position:absolute; right:8px; top:8px; z-index:3;
            padding:4px 7px; border:1px solid #2a7a96; border-radius:5px;
            background:rgba(4,12,18,.88); color:#7af4ff;
            font:700 10px "Share Tech Mono",monospace;
        }
        .hab-badges {
            position:absolute; right:8px; bottom:8px; z-index:3;
            display:flex; flex-direction:column; gap:4px; align-items:flex-end;
        }
        .hab-badge {
            padding:4px 8px; border-radius:5px; font:700 10px "Share Tech Mono",monospace;
            border:1px solid #3a7a90; background:rgba(8,24,36,.9); color:#d7f4ff;
        }
        .hab-badge.ok { border-color:#2f9a68; color:#7dffa8; }
        .hab-badge.warn { border-color:#b8882a; color:#f0c14a; }
        .hab-base-line {
            position:absolute; left:8px; right:8px; bottom:8px; z-index:2;
            margin:0; padding:6px 8px; border-radius:6px;
            background:rgba(4,12,18,.82); color:#b8d7e2;
            font:11px "Share Tech Mono",monospace; pointer-events:none;
        }
        .hab-yard-tools {
            position:absolute; z-index:4; left:8px; bottom:8px;
            display:flex; flex-wrap:wrap; gap:4px; pointer-events:auto;
        }
        .hab-yard-tools button {
            min-height:28px; padding:4px 8px; border:1px solid #2a7a96; border-radius:5px;
            background:#0a2230; color:#d7f4ff; font:700 10px "Share Tech Mono",monospace; cursor:pointer;
        }
        .yard-readout {
            list-style:none; margin:0; padding:0; display:grid; gap:5px;
            font:11px "Share Tech Mono",monospace; color:#9ad7e2;
        }
        .yard-readout li {
            border-top:1px solid #16384a; padding-top:4px;
        }
        .yard-readout strong { color:#e7f7ff; }
        #base-yard { display:none !important; }
        @media (max-width:1100px) {
            .hab-body {
                grid-template-columns:1fr !important;
                grid-template-rows:auto minmax(280px,1fr) auto !important;
                overflow:auto !important;
            }
            .hab-split { min-height:420px; }
        }

        .hab-board.is-on {
            display:flex !important; flex-direction:column !important;
            overflow:hidden !important;
        }
        .hab-tools {
            display:flex; flex-wrap:wrap; gap:6px; padding:4px 8px 0;
        }
        .hab-tools button {
            min-height:30px; padding:5px 9px; font-size:11px;
            border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; cursor:pointer;
        }
        .hab-body { flex:1; min-height:0 !important; height:auto !important; overflow:hidden !important; }
        .descent-board.is-on {
            display:grid !important;
            grid-template-rows:auto minmax(0,1fr) auto !important;
            overflow:hidden !important; height:100% !important;
        }
        .des-top { min-height:0 !important; padding:6px 10px !important; }
        .des-body {
            flex:1 !important; min-height:0 !important; height:100% !important;
            overflow:hidden !important;
            display:grid !important;
            grid-template-columns:minmax(150px,190px) minmax(0,1fr) minmax(200px,250px) !important;
            gap:6px !important; padding:6px !important;
        }
        .des-stage { min-height:0 !important; height:100% !important; overflow:hidden !important; }
        #des-stage { position:absolute !important; inset:0 !important; width:100% !important; height:100% !important; min-height:0 !important; }
        .des-gauges canvas { min-height:0 !important; }
        .des-water { flex:0 0 auto !important; max-height:28% !important; overflow:hidden !important; }
        .des-foot { padding:4px 6px 6px !important; gap:6px !important; }
        .des-chip { padding:5px 8px !important; }
        .des-chip strong { font-size:13px !important; }
        .des-concept, .des-caption { max-width:min(240px,46%) !important; font-size:10px !important; padding:5px 7px !important; }

        @media(max-width:1100px) {
            .path-stage {
                grid-template-columns:minmax(140px,180px) minmax(0,1fr) minmax(140px,180px) !important;
                grid-template-rows:minmax(0,1fr) auto !important;
            }
            .path-card-left { grid-column:1; grid-row:1; max-height:none; }
            .path-card-right { grid-column:3; grid-row:1; max-height:none; }
            .path-map-wrap { grid-column:2; grid-row:1; }
            .path-legend { grid-column:1 / -1; grid-row:2; }
            .ops-mid, .ops-low { grid-template-columns:1fr 1fr !important; }
        }
        @media(max-width:800px) {
            .ops-board.is-on { grid-template-rows:auto auto minmax(0,1fr) minmax(0,1fr) !important; }
            .ops-mid, .ops-low { grid-template-columns:1fr !important; }
            .path-stage {
                grid-template-columns:1fr !important;
                grid-template-rows:auto auto minmax(0,1fr) auto !important;
            }
            .path-card-left, .path-card-right { grid-column:1; max-height:70px; }
            .path-map-wrap { grid-column:1; }
            .des-body {
                grid-template-columns:minmax(120px,150px) minmax(0,1fr) minmax(130px,160px) !important;
            }
            .des-gauges { grid-template-columns:1fr !important; grid-template-rows:repeat(4,minmax(0,1fr)) !important; }
        }

        /* Judge / demo strip */
        .screen-nav button[aria-pressed="true"] {
            background:linear-gradient(180deg,#1a6a82,#0f4254) !important;
            border-color:#7af4ff !important;
            color:#f4fbff !important;
            box-shadow:0 0 14px rgba(122,244,255,.2);
        }
        .judge-strip {
            display:grid;
            grid-template-columns:minmax(0,1.4fr) auto auto;
            gap:10px 14px;
            align-items:center;
            margin:0 0 8px;
            padding:10px 12px;
            border:1px solid #2a8aa8;
            border-radius:12px;
            background:linear-gradient(135deg,#0c2836 0%,#071820 55%,#0a1f2a 100%);
            box-shadow:0 8px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(122,244,255,.12);
        }
        .judge-challenge {
            margin:0;
            color:#9ad7e4;
            font-size:12px;
            letter-spacing:.4px;
            line-height:1.35;
        }
        .judge-challenge strong { color:#7af4ff; letter-spacing:.8px; }
        .judge-help { margin:4px 0 0; color:#c6d6e0; font-size:12px; line-height:1.35; }
        .judge-verdict {
            display:flex;
            flex-direction:column;
            gap:4px;
            min-width:140px;
            padding:8px 12px;
            border-radius:10px;
            border:1px solid #2a6173;
            background:#0a1c28;
            text-align:center;
        }
        .judge-verdict .q-badge { align-self:center; font-size:14px; padding:6px 14px; }
        .judge-verdict small { color:#9ad7e4; font-size:11px; }
        .judge-actions { display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }
        .judge-actions button {
            min-height:36px;
            padding:6px 10px;
            border-radius:8px;
            border:1px solid #5eb4cc;
            background:#12384c;
            color:#f4fbff;
            cursor:pointer;
            font-size:12px;
        }
        .judge-actions button[aria-pressed="true"] {
            background:#1a5a4a;
            border-color:#7dffc2;
            color:#d8ffe9;
        }
        .validity-badge {
            margin:0 0 8px;
            padding:6px 10px;
            border-left:3px solid #5eebff;
            background:#0a1c28;
            color:#b6c8d1;
            font-size:11px;
            line-height:1.35;
            letter-spacing:.2px;
        }
        .accuracy-chips {
            display:flex;
            flex-wrap:wrap;
            gap:6px;
            margin:8px 0 10px;
        }
        .accuracy-chips span {
            display:inline-flex;
            align-items:center;
            gap:6px;
            padding:4px 8px;
            border-radius:999px;
            border:1px solid #2a6173;
            background:#0d2230;
            color:#d7f4ff;
            font-size:11px;
        }
        .accuracy-chips b { color:#7af4ff; }
        .story-caption {
            margin:0 0 8px;
            padding:8px 10px;
            border:1px dashed #3a7a8c;
            border-radius:8px;
            color:#d7f4ff;
            font-size:13px;
            line-height:1.4;
            background:#081820;
        }
        .story-caption[hidden] { display:none !important; }
        body.demo-mode .feature-rail,
        body.demo-mode .kept-record,
        body.demo-mode #page-data-panel { display:none !important; }
        body.demo-mode .screen .purpose,
        body.demo-mode .screen .ops-note,
        body.demo-mode .path-board > h2,
        body.demo-mode .topo-board > .purpose,
        body.demo-mode .hab-board > .purpose {
            display:block !important;
            margin:6px 10px 8px !important;
        }
        @media (max-width:900px) {
            .judge-strip { grid-template-columns:1fr; }
            .judge-actions { justify-content:flex-start; }
        }

        .clps-board.is-on { gap:8px; padding:8px 10px !important; }
        .clps-head { display:flex; flex-wrap:wrap; gap:8px 14px; align-items:flex-end; justify-content:space-between; }
        .clps-head h2 { margin:0; font-size:18px; letter-spacing:.8px; color:#f4fbff; }
        .clps-head p { margin:3px 0 0; max-width:680px; color:#9ad7e4; font-size:12px; line-height:1.35; }
        .clps-controls { display:flex; flex-wrap:wrap; gap:6px; align-items:center; color:#d5e8ef; font-size:12px; }
        .clps-controls input, .clps-controls button {
            min-height:34px; border-radius:8px; border:1px solid #5eb4cc;
            background:#0c2433; color:#f4fbff; padding:4px 8px; font:600 12px "Segoe UI", Arial, sans-serif;
        }
        .clps-controls button[aria-pressed="true"] { background:#b8e9f2; color:#0d2533; border-color:#fff; }
        .clps-headline {
            margin:0; padding:8px 12px; border-radius:10px; border:1px solid #2a8aa8;
            background:#102838; color:#f4fbff; font-size:14px; line-height:1.4;
        }
        .clps-grid {
            flex:1 1 auto; min-height:0;
            display:grid; grid-template-columns:minmax(210px,270px) minmax(0,1fr) minmax(190px,240px);
            gap:8px;
        }
        .clps-list { overflow:auto; min-height:0; display:flex; flex-direction:column; gap:6px; padding-right:2px; }
        .clps-site {
            text-align:left; border-radius:10px; border:1px solid #2a6173;
            background:#0c2230; color:#f4fbff; padding:8px 10px; cursor:pointer;
        }
        .clps-site[aria-pressed="true"] { border-color:#b8eff4; background:#14384a; }
        .clps-site strong { display:block; font-size:13px; }
        .clps-site .clps-meta, .clps-site .clps-call { display:block; color:#9ad7e4; font-size:11px; }
        .clps-site .clps-hours { display:block; margin-top:3px; color:#f0c14a; font-size:12px; }
        .clps-site.rank-1 .clps-hours { color:#d8ffe9; }
.clps-best {
    margin:-2px 0 4px 10px; padding:0; border:0; background:transparent; color:#7af4ff;
    font:600 11px "Segoe UI", Arial, sans-serif; cursor:pointer; text-align:left;
}
        .clps-stage, .clps-rose-wrap {
            min-width:0; min-height:0; display:flex; flex-direction:column;
            border:1px solid #2a6173; border-radius:12px; background:#07141c; overflow:hidden;
        }
        .clps-stage canvas, .clps-rose-wrap canvas { flex:1 1 auto; width:100%; min-height:140px; }
        .clps-legend, .clps-rose-caption {
            margin:0; padding:6px 8px; color:#9ad7e4; font-size:11px; line-height:1.35;
        }
        .clps-foot { display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; }
        .clps-foot p { margin:0; flex:1 1 280px; color:#8fb4c2; font-size:11px; line-height:1.35; }
        .clps-foot button {
            min-height:36px; border-radius:8px; border:1px solid #5eb4cc; background:#12384c;
            color:#f4fbff; padding:6px 12px; cursor:pointer; font-weight:700;
        }
        @media (max-width:1000px) {
            .clps-grid { grid-template-columns:1fr; }
            .clps-board.is-on { overflow:auto !important; }
            .clps-stage canvas, .clps-rose-wrap canvas { height:240px; flex:0 0 auto; }
        }

    </style>
</head>
<body data-view="{{ active_view }}">
<main class="shell">
    <div class="workspace">
    <button type="button" id="chrome-toggle" class="chrome-toggle" aria-expanded="false" aria-controls="chrome-panel" aria-label="Open mission menu">
        <span></span><span></span><span></span>
    </button>
    <div id="chrome-backdrop" class="chrome-backdrop" hidden></div>
    <div id="chrome-panel" class="chrome-panel" hidden>
    <header id="mission" class="console-header">
        <div class="brand">
            <img class="mission-patch" src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar logo">
            <div><h1>ZERO-POINT LUNAR</h1><div class="subtitle">SHACKLETON TRAVERSE</div></div>
        </div>
        <div class="mission-name"><strong>Site call:</strong> walk, weather, and the touchdown corridor</div>
        <div class="live"><i class="live-dot"></i>NOAA X-RAY · NASA LRO DATA</div>
    </header>

    <nav class="app-tabs" role="tablist" aria-label="Zero-Point Lunar">
        <button id="page-home" type="button" role="tab" aria-selected="true" data-page="home">Home</button>
        <button id="page-simulator" type="button" role="tab" aria-selected="false" data-page="simulator">Simulator</button>
        <button id="page-data" type="button" role="tab" aria-selected="false" data-page="data">Data</button>
    </nav>
    <nav class="screen-nav" aria-label="Mission screens">
        <button type="button" data-screen="clps" aria-pressed="true">Sites &amp; Dates</button>
        <button type="button" data-screen="ops" aria-pressed="false">Mission &amp; Launch Ops</button>
        <button type="button" data-screen="path" aria-pressed="false">Solar-to-Ice Pathfinder</button>
        <button type="button" data-screen="terrain" aria-pressed="false">3D Topography Inspector</button>
        <button type="button" data-screen="habitat" aria-pressed="false">Base Placement</button>
        <button type="button" data-screen="descent" aria-pressed="false">Descent Simulator</button>
        <button type="button" id="open-options" aria-expanded="false" aria-controls="options-drawer">Options</button>
    </nav>
    </div>
    <section class="judge-strip" aria-label="Challenge fit and planning verdict">
        <div>
            <p class="judge-challenge"><strong>BUILT FOR</strong> NASA Space Apps 2026 · CLPS Lunar Mission Browser</p>
            <p class="judge-help">Compare south-pole sites and dates by Sun and Earth above the local horizon — power and direct-to-Earth radio.</p>
        </div>
        <div class="judge-verdict" id="judge-verdict" aria-live="polite">
            <p class="q-badge wait" id="judge-badge" data-tone="wait">Waiting on the path</p>
            <small id="judge-badge-note">GO / HOLD updates when you Apply Options</small>
        </div>
        <div class="judge-actions">
            <button type="button" id="open-clps">Compare sites &amp; dates</button>
            <button type="button" id="demo-mode-toggle" aria-pressed="false">Demo mode</button>
            <button type="button" id="try-story">Try the story</button>
        </div>
    </section>
    <p class="validity-badge" id="validity-badge">LOLA LDEM 16 · ~3 km cells · NOAA GOES X-ray · decision support · not flight clearance · not ice detection</p>
    <p class="story-caption" id="story-caption" hidden></p>
    <div id="options-drawer" class="options-drawer" hidden>
    <div id="page-home-panel" data-page-panel="home">
    <section class="panel q-desk" id="plan-gate">
        <header class="q-head">
            <div>
                <div class="eyebrow">Options · these answers land on every screen · Artemis south-polar traverse planning</div>
                <h2>Change the site, then read the boards</h2>
            </div>
            <button type="button" class="q-close" id="close-options">Close</button>
        </header>
        <p class="q-lead" id="briefing-summary">Haworth crater · protecting the habitat · no shelter · climb limit {{ max_slope_degrees }}° · slope decides the answer.</p>
        <div class="q-layout">
            <div class="q-ask">
                <div id="choice-boards"></div>
                <p class="q-why">The crater sets the latitude, the night length, and the A* path. Picking one scores the walk with the questions below.</p>
                <section class="briefing" id="briefing">
                    <form id="briefing-form" class="briefing-grid">
                        <div class="field">
                            <label for="brief-asset">Who should this brief protect?</label>
                            <select id="brief-asset" class="q-native" tabindex="-1">
                                <option value="rover" selected>Habitat hardware</option>
                                <option value="crew">Crew</option>
                                <option value="both">Crew and habitat</option>
                            </select>
                            <div class="choice-grid" data-choice-for="brief-asset"></div>
                            <p class="q-why">This sets the battery draw on the walk. Crew is the light load. Habitat hardware is heavier. Both carries both.</p>
                        </div>
                        <div class="field">
                            <label for="brief-shelter">Is there mass to hide behind in a storm?</label>
                            <select id="brief-shelter" class="q-native" tabindex="-1">
                                <option value="no" selected>No storm shelter yet</option>
                                <option value="yes">Yes · habitat, rover body, or berm</option>
                            </select>
                            <div class="choice-grid" data-choice-for="brief-shelter"></div>
                            <p class="q-why">If GOES is at M or X and this stays no, the answer is hold. Yes records a stop behind that mass. It is not a mapped shelter.</p>
                        </div>
                        <div class="field">
                            <div class="q-slope"><label for="brief-slope">Steepest tether slope (°)</label><b id="brief-slope-label">{{ max_slope_degrees }}°</b></div>
                            <input id="brief-slope" type="range" min="5" max="30" step="1" value="{{ max_slope_degrees }}">
                            <p class="q-why">Path and terrain mark red at this angle. 15° is a cautious tether. 25° is a steep walk. Releasing the slider reloads the path.</p>
                        </div>
                        <div class="field">
                            <label for="brief-priority">What should the path watch first?</label>
                            <select id="brief-priority" class="q-native" tabindex="-1">
                                <option value="slope" selected>Slope under the limit</option>
                                <option value="sun">Sunlight for power</option>
                                <option value="radio">Earth radio</option>
                            </select>
                            <div class="choice-grid" data-choice-for="brief-priority"></div>
                            <p class="q-why">This picks the answer on the right, and which board opens next. The other boards still use the same climb limit, shelter, and load.</p>
                        </div>
                        <div class="field">
                            <label for="brief-focus-note">Any other planning focus? (optional)</label>
                            <input id="brief-focus-note" type="text" maxlength="120" placeholder="For example: keep close to the ice prospect">
                            <p class="q-why">Your note appears in the briefing. It does not change the terrain data or safety checks.</p>
                        </div>
                        <div class="field">
                            <div class="q-slope"><label for="brief-speed">Planning walk speed (km/h)</label><b id="brief-speed-label">{{ planning_speed_kmh }}</b></div>
                            <input id="brief-speed" type="range" min="0.2" max="2" step="0.1" value="{{ planning_speed_kmh }}">
                            <p class="q-why">Path uses this for the ETA. It does not move the line. Terrain still uses the climb limit.</p>
                        </div>
                        <div class="field">
                            <label>What sits in the base?</label>
                            <div class="choice-grid" id="base-kit">
                                <button type="button" class="choice-card" data-kit="habitat" aria-pressed="true">Habitat cylinder</button>
                                <button type="button" class="choice-card" data-kit="lab" aria-pressed="true">Lab</button>
                                <button type="button" class="choice-card" data-kit="rover" aria-pressed="false">Rover</button>
                                <button type="button" class="choice-card" data-kit="array" aria-pressed="true">Solar mast</button>
                            </div>
                            <p class="q-why">Descent and Habitat draw this kit on the clearest shoulder. The habitat stays. Turn the rover on when the brief protects the crew.</p>
                        </div>
                    </form>
                </section>
                <details class="q-record">
                    <summary>Recorded launch · the rocket stays on the Ops record</summary>
                    <div id="recorded-launch"></div>
                </details>
                <p class="choice-title">Pages about this crater</p>
                <div id="live-finds" class="live-finds"></div>
            </div>
            <aside class="q-verdict" id="question-verdict" aria-live="polite">
                <p class="choice-title">Answer for these questions</p>
                <p class="q-badge wait" id="q-badge" data-tone="wait">Waiting on the path</p>
                <p class="q-decision" id="q-decision">Check this site to score the crater with the climb limit, the shelter, and who you protect. The answer stays on this page.</p>
                <div class="q-meters" id="q-meters">
                    <div><span>Climb limit</span><strong id="q-climb">{{ max_slope_degrees }}°</strong><small id="q-climb-note">Path not loaded</small></div>
                    <div><span>Battery</span><strong id="q-battery">—</strong><small id="q-battery-note">Habitat load</small></div>
                    <div><span>Earth</span><strong id="q-earth">—</strong><small id="q-earth-note">Lowest on the path</small></div>
                    <div><span>Storm step</span><strong id="q-storm">—</strong><small id="q-storm-note">No shelter recorded</small></div>
                </div>
                <p class="small-print" id="q-next">Slope is the question until you change it. The path board marks irregular slope shapes at or over the climb limit.</p>
                <div class="button-row q-actions">
                    <button type="button" id="run-plan">Apply to every screen</button>
                    <button type="button" id="q-open-next">Open the path</button>
                    <button type="button" id="open-yard">Path board</button>
                    <button type="button" id="open-terrain">Terrain board</button>
                </div>
                <p class="small-print" id="q-assumptions"></p>
            </aside>
        </div>
        <div class="plan-grid">
            <div class="field"><label for="plan-destination">Crater or region</label>
                <select id="plan-destination">
                    <option value="-86.9,-4.2" data-name="Haworth crater" data-diameter="35" data-start="-86.306,-6.758" data-dest="-86.372,-0.554" selected>Haworth crater</option>
                    <option value="-89.5,0" data-name="Shackleton rim" data-diameter="21">Shackleton rim</option>
                    <option value="-89.45,-137.4" data-name="Connecting Ridge">Connecting Ridge</option>
                    <option value="-88.23,-65.11" data-name="de Gerlache rim" data-diameter="32">de Gerlache rim</option>
                    <option value="-85.99,-0.24" data-name="Malapert Massif">Malapert Massif</option>
                    <option value="-85.43,37.33" data-name="Nobile rim">Nobile rim</option>
                    <option value="-87.18,84" data-name="Faustini rim">Faustini rim</option>
                    <option value="-69.374,32.32" data-name="Statio Shiv Shakti">Statio Shiv Shakti</option>
                    <option value="-13.316,25.251" data-name="Shioli">Shioli</option>
                    <option value="8.40651,84.75701" data-name="East limb mare">East limb mare</option>
                </select>
            </div>
            <div class="field"><label for="plan-vehicle">What are you launching?</label>
                <select id="plan-vehicle">
                    <option value="sls">SLS · NASA</option>
                    <option value="lvm3" selected>LVM3 · ISRO</option>
                    <option value="falcon9">Falcon 9</option>
                    <option value="longmarch5">Long March 5 · CNSA</option>
                    <option value="h3">H3 · JAXA</option>
                </select>
            </div>
            <div class="field"><label for="plan-pad">Where does it leave Earth?</label>
                <select id="plan-pad">
                    <option value="13.72" selected>Satish Dhawan · 13.7° N</option>
                    <option value="28.57">Kennedy Space Center · 28.6° N</option>
                    <option value="19.61">Wenchang · 19.6° N</option>
                    <option value="30.40">Tanegashima · 30.4° N</option>
                </select>
            </div>
        </div>
        <div class="q-foot">
            <canvas id="sun-preview" role="img" aria-label="Equator, mid-latitude, and polar temperature across one lunar day"></canvas>
            <div>
                <p class="small-print">A polar site stays colder and darker than the equator across one lunar day. Sunlight-first uses that, then the habitat night budget.</p>
                <p class="small-print" id="plan-cost">The lunar path is an A* search on LOLA slope. The rocket and pad stay on the Ops record. Check this site to score the walk.</p>
            </div>
        </div>
    </section>
    </div>
    </div>
    <div id="page-simulator-panel" data-page-panel="simulator">
    <section class="clps-board screen" id="clps-board" data-screen="clps" hidden>
        <div class="clps-head">
            <div>
                <h2>SITES &amp; DATES</h2>
                <p>Pick a landing date. Seven south-pole regions are ranked by hours the Sun and Earth clear the local LOLA ridge. Sun hours feed the array. Earth hours are the direct-to-Earth radio window.</p>
            </div>
            <div class="clps-controls">
                <label>Land on <input id="clps-date" type="date" aria-label="Landing date"></label>
                <button type="button" data-clps-days="7">7 days</button>
                <button type="button" data-clps-days="14" aria-pressed="true">14 days</button>
                <button type="button" data-clps-days="29.53">Lunar day</button>
            </div>
        </div>
        <p class="clps-headline" id="clps-headline">Reading the ridges for this date.</p>
        <div class="clps-grid">
            <div class="clps-list" id="clps-list" aria-label="Landing regions"></div>
            <div class="clps-stage">
                <canvas id="clps-chart" aria-label="Sun and Earth elevation during the stay"></canvas>
                <p class="clps-legend" id="clps-legend">Gold is the Sun. Cyan is Earth. A dashed line is the ridge in that direction. The body is up when its solid line is above the matching dash.</p>
            </div>
            <div class="clps-rose-wrap">
                <canvas id="clps-rose" aria-label="Horizon rose for the selected region"></canvas>
                <p class="clps-rose-caption" id="clps-rose-caption">The circle is a smooth horizon. Ridge outside the circle blocks the sky. A bright dot has cleared it.</p>
            </div>
        </div>
        <div class="clps-foot">
            <p id="clps-status"></p>
            <button type="button" id="clps-walk">Walk this site</button>
        </div>
    </section>
    <section class="ops-board screen" id="ops-board" data-screen="ops" hidden>
        <header class="ops-top">
            <div class="ops-brand">
                <img src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar">
                <div>
                    <h2>ZERO-POINT // SITE CALL</h2>
                    <p id="ops-subtitle">Waiting for a site</p>
                </div>
            </div>
            <div class="ops-met"><span>MISSION ELAPSED TIME</span><strong id="ops-met">00d 00h 00m 00s</strong></div>
            <ul class="ops-lights">
                <li><i id="ops-dot-comms"></i>COMMS <b id="ops-comms">SET</b></li>
                <li><i id="ops-dot-guide"></i>GUIDANCE <b id="ops-guide">IDLE</b></li>
                <li><i id="ops-dot-prop" class="warn"></i>WALK <b id="ops-prop">RECORDED</b></li>
                <li><i id="ops-dot-sys"></i>SYSTEMS <b id="ops-sys">QUIET</b></li>
            </ul>
        </header>
        <p class="purpose" id="ops-purpose"><b>DECIDE THE SITE</b> Pros and cons of this crater for the options you set.</p>
        <div class="ops-interact" aria-label="Ops actions">
            <button type="button" data-ops-action="prev-site">Prev site</button>
            <button type="button" data-ops-action="next-site">Next site</button>
            <button type="button" data-ops-action="toggle-shelter">Toggle shelter</button>
            <button type="button" data-ops-action="focus-gauges">Focus gauges</button>
        </div>
        <div class="ops-mid">
            <div class="ops-pane">
                <p class="ops-kicker">ORBITAL TRAJECTORY ARC</p>
                <canvas id="ops-arc" role="img" aria-label="LROC Moon photo with the transfer arc and the target crater"></canvas>
            </div>
            <div class="ops-pane">
                <p class="ops-kicker">EVENT LOG // SITE CALL</p>
                <div class="pros-cons" id="ops-call">
                    <div>
                        <p class="ops-kicker pro-kicker">WORKS HERE</p>
                        <ul id="ops-pros"></ul>
                    </div>
                    <div>
                        <p class="ops-kicker con-kicker">WORKS AGAINST</p>
                        <ul id="ops-cons"></ul>
                    </div>
                </div>
            </div>
        </div>
        <div class="ops-low">
            <div class="ops-pane">
                <p class="ops-kicker">FLIGHT DIRECTOR TELEMETRY</p>
                <div class="ops-gauges">
                    <canvas id="ops-g-path" aria-label="Thrust as a share of the 5 km/h planning speed"></canvas>
                    <canvas id="ops-g-earth" aria-label="Battery hours as a share of one day"></canvas>
                    <canvas id="ops-g-power" aria-label="Tilted array power as a share of 2200 W"></canvas>
                    <canvas id="ops-g-shelter" aria-label="Life support from storm, Earth, and the plan"></canvas>
                </div>
                <div class="ops-figures" id="ops-figures"></div>
            </div>
            <div class="ops-pane">
                <p class="ops-kicker">ALTITUDE &amp; SLOPE ALONG THE WALK</p>
                <canvas id="ops-alt" role="img" aria-label="LOLA elevation along the path"></canvas>
                <canvas id="ops-slope" role="img" aria-label="Slope along the path with the climb limit"></canvas>
            </div>
        </div>
    </section>
    <section class="path-board screen" id="path-board" data-screen="path" hidden>
        <h2>SOLAR-TO-ICE PROXIMITY PATHFINDER</h2>
        <p class="purpose" id="path-purpose"><b>CAN THE CREW WALK IT</b> Green holds the climb limit. Gold is the power shoulder. Cyan is the cold-floor prospecting corridor — not ice detection. Red is blocked.</p>
        <div class="path-tools" role="toolbar" aria-label="Pathfinder tools">
            <button type="button" data-path-layer="route" aria-pressed="true">Route</button>
            <button type="button" data-path-layer="variants" aria-pressed="true">Variants</button>
            <button type="button" data-path-layer="hazard" aria-pressed="true">Hazards</button>
            <button type="button" data-path-layer="waypoints" aria-pressed="true">Waypoints</button>
            <button type="button" data-path-layer="profile" aria-pressed="true">Profile</button>
            <button type="button" data-path-layer="grid" aria-pressed="true">Grid</button>
            <button type="button" data-path-layer="labels" aria-pressed="true">Labels</button>
            <button type="button" id="path-zoom-in" title="Zoom in">+</button>
            <button type="button" id="path-zoom-out" title="Zoom out">−</button>
            <button type="button" id="path-zoom-reset" title="Reset view">Reset</button>
            <button type="button" id="path-inspect" aria-pressed="false">Inspect</button>
            <button type="button" id="path-replan" title="Re-run multi-objective A*">Replan</button>
            <label>Climb <input id="path-climb-live" type="range" min="5" max="30" step="1" value="{{ max_slope_degrees }}"><b id="path-climb-live-label">{{ max_slope_degrees }}°</b></label>
        </div>
        <div class="path-stage">
            <aside class="path-card path-card-left" id="path-status"></aside>
            <div class="path-map-wrap" id="path-map-wrap">
                <canvas id="path-map" role="img" aria-label="Moon photo centered on the walk, colored by slope against the climb limit"></canvas>
                <div id="path-probe" class="path-probe" hidden></div>
            </div>
            <aside class="path-card path-card-right" id="path-nav"></aside>
            <div class="path-legend" aria-label="Path legend">
                <span><i class="good"></i>Good · under the limit</span>
                <span><i class="near"></i>Close · within 3°</span>
                <span><i class="bad"></i>Blocked · at or over</span>
                <span><i class="gold"></i>Shoulder · start</span>
                <span><i class="floor"></i>Floor · low end</span>
            </div>
        </div>
        <p class="ops-note">Drag to pan · scroll to zoom · Inspect taps a slope sample · Climb re-scores the walk live.</p>
    </section>
    <section class="topo-board screen" id="topo-board" data-screen="terrain" hidden>
        <header class="topo-head">
            <h2>3D TOPOGRAPHY &amp; SLOPE INSPECTOR</h2>
            <div><span id="topo-system">SYSTEM WAIT</span> · <span id="topo-utc">UTC</span> · <span>ZERO-POINT LUNAR</span></div>
        </header>
        <p class="purpose" id="topo-purpose"><b>SEE THE GROUND</b> Drag the view. Color is slope. The climb limit from Options is the line between a walk and a stop.</p>
        <div class="topo-layout">
            <div class="topo-stage">
                <canvas id="topo-canvas" aria-label="LOLA terrain mesh colored by slope"></canvas>
                <div class="topo-compass" aria-hidden="true"><b class="n">N</b><b class="e">E</b><b class="s">S</b><b class="w">W</b><div class="topo-needle" id="topo-needle"></div></div>
                <div class="topo-legend" id="topo-legend">
                    <strong>SLOPE ANGLE</strong>
                    <div><i class="swatch" style="background:#34d6e6"></i>0°–5°</div>
                    <div><i class="swatch" style="background:#3fbf72"></i>5°–15°</div>
                    <div><i class="swatch" style="background:#f2d133"></i>15°–25°</div>
                    <div><i class="swatch" style="background:#f27a2e"></i>25°–35°</div>
                    <div><i class="swatch" style="background:#f23840"></i>&gt;35°</div>
                </div>
                <div class="topo-facts" id="topo-facts"></div>
                <div class="topo-fact" id="topo-fact" hidden>
                    <strong id="topo-fact-title">LOLA sample</strong>
                    <p id="topo-fact-body"></p>
                </div>
            </div>
            <aside class="topo-side">
                <h3>NAVIGATION CONTROLS</h3>
                <label>CAMERA AZIMUTH <b id="topo-az-label">210°</b><input id="topo-az" type="range" min="0" max="360" value="210"></label>
                <label>ELEVATION <b id="topo-el-label">28°</b><input id="topo-el" type="range" min="8" max="80" value="28"></label>
                <label>ZOOM <b id="topo-zoom-label">1.6×</b><input id="topo-zoom" type="range" min="0.6" max="4" step="0.1" value="1.6"></label>
                <h3>SLOPE ANALYSIS</h3>
                <div class="topo-row"><span>MAX SLOPE</span><strong id="topo-max">—</strong></div>
                <div class="topo-row"><span>AVG SLOPE</span><strong id="topo-avg">—</strong></div>
                <div class="topo-row"><span>SAMPLE AREA</span><strong id="topo-area">—</strong></div>
                <div class="topo-row"><span>RELIEF</span><strong id="topo-relief">—</strong></div>
                <h3>LAYER SETTINGS</h3>
                <div class="topo-row"><span>WIREFRAME</span><input id="topo-wire" type="checkbox" checked></div>
                <div class="topo-row"><span>SHADED RELIEF</span><input id="topo-shade" type="checkbox" checked></div>
                <div class="topo-row"><span>SLOPE HEATMAP</span><input id="topo-heat" type="checkbox" checked></div>
                <div class="topo-row"><span>SUN LIGHT</span><input id="topo-sun" type="checkbox" checked></div>
                <div class="topo-row"><span>GRID</span><input id="topo-grid" type="checkbox" checked></div>
                <div class="topo-row"><span>ANNOTATIONS</span><input id="topo-notes" type="checkbox" checked></div>
            </aside>
        </div>
        <footer class="topo-foot"><span id="topo-place">Waiting for LOLA</span><span>Dots mark LOLA samples. Hover one for its fact.</span></footer>
    </section>
    <section class="hab-board screen" id="hab-board" data-screen="habitat" hidden>
        <header class="hab-top">
            <div class="hab-brand">
                <img class="hab-nasa" src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar">
                <span>BASE PLACEMENT · HABITAT OPS</span>
            </div>
            <div class="hab-meta">
                <span>STATUS: <b class="ok" id="hab-status">STANDBY</b></span>
                <span>SITE: <b id="hab-site">WAITING</b></span>
                <span>ENDURANCE: <b id="hab-end-meta">—</b></span>
                <span>TIME: <b id="hab-clock">14:48:21 UTC</b></span>
            </div>
        </header>
        <p class="purpose" id="hab-purpose"><b>PLACE THE BASE</b> Drag modules in the yard. Dangers stay on the left. Endurance scores how long the camp can run.</p>
        <div class="hab-tools" role="toolbar" aria-label="Base placement tools">
            <button type="button" data-hab-action="orbit">Reset orbit</button>
            <button type="button" data-hab-action="snap-pad">Snap to shoulder</button>
            <button type="button" data-hab-action="camp-view">Camp view</button>
            <button type="button" data-hab-action="pad-view">2 km pad view</button>
            <button type="button" data-hab-action="next-site">Next site</button>
            <button type="button" data-hab-action="toggle-shelter">Toggle shelter</button>
            <button type="button" data-hab-layer="dangers" aria-pressed="true">Dangers</button>
            <button type="button" data-hab-layer="yard" aria-pressed="true">Yard</button>
            <button type="button" data-hab-layer="models" aria-pressed="true">3D models</button>
            <button type="button" data-hab-action="replan">Recompute endurance</button>
        </div>
        <div class="hab-body">
            <aside class="hab-left">
                <div class="hab-pane hab-ice" id="hab-danger-pane">
                    <p class="hab-kicker">DANGERS · KEEP WATCH</p>
                    <p class="hab-model" id="hab-env-model">Dust, flare, radiation, and thermal stay live while you place the camp.</p>
                    <div class="hab-ice-top">
                        <canvas id="hab-heat" aria-label="Cold floor in the center, warmer rim at the edge"></canvas>
                        <div class="hab-ice-side">
                            <canvas id="hab-scatter" aria-label="Spread of slope samples"></canvas>
                            <p id="hab-ice-side-note">Low floor samples over the limit <strong id="hab-floor-count">—</strong></p>
                        </div>
                    </div>
                    <div class="hab-bars">
                        <div class="hab-bar"><p><span>DUST PLUME</span><span id="hab-dust-read">Waiting</span></p><div class="hab-track" id="hab-dust-track"><b id="hab-dust-bar" style="width:8%"></b></div></div>
                        <div class="hab-bar"><p><span>SOLAR FLARE</span><span id="hab-flare-read">Waiting</span></p><div class="hab-track amber" id="hab-flare-track"><b id="hab-flare-bar" style="width:8%"></b></div></div>
                        <div class="hab-bar"><p><span>RADIATION</span><span id="hab-rad-read">Waiting</span></p><div class="hab-track" id="hab-rad-track"><b id="hab-rad-bar" style="width:8%"></b></div></div>
                        <div class="hab-bar"><p><span>COLD / HOT</span><span id="hab-hot-read">Waiting</span></p><div class="hab-track" id="hab-hot-track"><b id="hab-hot-bar" style="width:8%"></b></div></div>
                    </div>
                    <div class="hab-briefs" id="hab-briefs">
                        <p id="hab-dust-note"><b>LUNAR DUST PLUME</b> Waiting for the vehicle keep-out.</p>
                        <p id="hab-flare-note"><b>SOLAR FLARE</b> Waiting on GOES.</p>
                        <p id="hab-rad-note"><b>LUNAR RADIATION</b> Waiting on the surface dose.</p>
                    </div>
                </div>
                <div class="hab-pane hab-endurance" id="hab-endurance-pane">
                    <p class="hab-kicker">HOW LONG IT CAN WORK</p>
                    <p class="hab-model" id="hab-end-model">Battery, night length, array power, shelter, and kit load set the endurance clock.</p>
                    <div class="hab-end-row"><span>Nominal ops</span><strong id="hab-end-ops" class="good">—</strong></div>
                    <div class="hab-end-meter" aria-hidden="true"><i id="hab-end-ops-bar" style="width:12%"></i></div>
                    <div class="hab-end-row"><span>Night survival</span><strong id="hab-end-night" class="watch">—</strong></div>
                    <div class="hab-end-meter" aria-hidden="true"><i id="hab-end-night-bar" style="width:12%"></i></div>
                    <div class="hab-end-row"><span>Storm hold</span><strong id="hab-end-storm">—</strong></div>
                    <div class="hab-end-meter" aria-hidden="true"><i id="hab-end-storm-bar" style="width:12%"></i></div>
                    <div class="hab-end-row"><span>Power margin</span><strong id="hab-end-power">—</strong></div>
                    <div class="hab-end-row"><span>Consumables gate</span><strong id="hab-end-life">—</strong></div>
                    <p class="hab-foot" id="hab-end-foot">Endurance is a planning band, not a flight clearance.</p>
                </div>
            </aside>
            <div class="hab-center">
                <div class="hab-split">
                    <div class="hab-pane hab-crater">
                        <canvas id="hab-crater" aria-label="Selected crater with placed base components"></canvas>
                        <div class="hab-scale" id="hab-scale">LOLA DEM</div>
                        <div class="hab-hud" id="hab-hud" aria-live="polite">
                            <strong>SITE · PAD READOUT</strong>
                            <span>Crater <b id="hab-hud-name">—</b></span>
                            <span>Lat/Lon <b id="hab-hud-ll">—</b></span>
                            <span>Diameter <b id="hab-hud-diam">—</b></span>
                            <span>Pad slope <b id="hab-hud-pad">—</b></span>
                            <span>Relief <b id="hab-hud-relief">—</b></span>
                            <span>Walk <b id="hab-hud-walk">—</b></span>
                            <span>Viability <b id="hab-hud-score">—</b></span>
                        </div>
                        <div class="hab-badges">
                            <div class="hab-badge warn" id="hab-badge-floor">FLOOR CHECK</div>
                            <div class="hab-badge ok" id="hab-badge-temp">THERMAL CHECK</div>
                        </div>
                        <p class="hab-base-line" id="hab-base-line">Place modules in the yard. The crater view mirrors the kit.</p>
                    </div>
                    <div class="hab-pane hab-yard" id="hab-yard-pane">
                        <canvas id="base-canvas" aria-label="3D base yard in meters. Drag a block to place it."></canvas>
                        <div class="hab-yard-hud">
                            <strong>BASE YARD · METERS</strong>
                            <span id="hab-yard-hint">Drag modules. Orange ring = 2 km lander keep-out.</span>
                        </div>
                        <div class="hab-yard-tools">
                            <button type="button" id="yard-camp">Camp</button>
                            <button type="button" id="yard-pad">2 km pad</button>
                            <button type="button" id="yard-reset-layout">Reset layout</button>
                        </div>
                    </div>
                </div>
            </div>
            <aside class="hab-right">
                <div class="hab-pane">
                    <p class="hab-kicker">BUILD MAIN COMPONENTS</p>
                    <p class="hab-model">Toggle modules into the yard and crater. Habitat stays on.</p>
                    <div class="hab-comp-grid" id="hab-comp-grid" role="group" aria-label="Base components"></div>
                </div>
                <div class="hab-pane">
                    <p class="hab-kicker">PLACEMENT DISTANCES</p>
                    <ul class="yard-readout" id="base-readout"></ul>
                </div>
                <div class="hab-pane hab-geo">
                    <p class="hab-kicker">CLIMB · RELIEF</p>
                    <canvas id="hab-alt" aria-label="Elevation along the walk" hidden></canvas>
                    <canvas id="hab-net" aria-label="How shelter, load, and sunlight connect" hidden></canvas>
                    <canvas id="hab-temp" aria-label="Temperature across one lunar day" hidden></canvas>
                    <canvas id="hab-network" aria-label="Habitat sensor network" hidden></canvas>
                    <div class="hab-alt-read" hidden><span>RELIEF <b id="hab-relief">—</b></span><span>LIMIT <b id="hab-limit">—</b></span></div>
                    <p class="hab-lat" id="hab-climb-meta">Waiting for the path</p>
                    <canvas id="hab-rim" aria-label="Elevation of the feasible climb out of the crater"></canvas>
                    <div class="hab-bars">
                        <div class="hab-bar"><p><span>CLIMB UNDER LIMIT</span><span id="hab-good-read">—</span></p><div class="hab-track"><b id="hab-good-bar" style="width:8%"></b></div></div>
                        <div class="hab-bar"><p><span>TOUGH FLOOR</span><span id="hab-tough-read">—</span></p><div class="hab-track bad"><b id="hab-tough-bar" style="width:8%"></b></div></div>
                    </div>
                    <div class="hab-conf-side" hidden>
                        <span id="hab-night-read">—</span><b id="hab-night-bar"></b>
                        <span id="hab-day-read">—</span><b id="hab-day-bar"></b>
                        <span id="hab-sun-read">—</span><b id="hab-sun-bar"></b>
                        <p id="hab-shelter-line"></p><p id="hab-proton-line"></p>
                        <p id="hab-temp-scale"></p><p id="hab-thermal-model"></p><p id="hab-env-foot"></p>
                        <span id="hab-cycle">384</span>
                    </div>
                    <p class="hab-foot" id="hab-climb-foot">Relief appears after the path loads.</p>
                </div>
            </aside>
        </div>
    </section>

    <section class="descent-board screen" id="descent-board" data-screen="descent" hidden>
        <header class="des-top">
            <div class="des-brand">
                <span class="des-mark" aria-hidden="true">◇</span>
                <div>
                    <strong>LUNAR EXPLORER</strong>
                    <small>DESCENT SIMULATOR</small>
                </div>
            </div>
            <div class="des-live"><i></i> LIVE TELEMETRY</div>
            <div class="des-mission">MISSION: <b id="des-mission">HAWORTH</b></div>
            <div class="des-clock">T+ <b id="des-clock">00:00:00</b></div>
        </header>
        <div class="des-body">
            <aside class="des-side">
                <div class="des-gauges">
                    <canvas id="des-g-thrust" aria-label="Planned settle thrust for the selected vehicle"></canvas>
                    <canvas id="des-g-velocity" aria-label="Velocity on the pad"></canvas>
                    <canvas id="des-g-altitude" aria-label="LOLA elevation of the pad"></canvas>
                    <canvas id="des-g-fuel" aria-label="Battery reserve for the walk"></canvas>
                </div>
                <div class="des-pane des-safe">
                    <p>SAFE ZONE · LANDING AREA</p>
                    <strong id="des-safe-call">—</strong>
                    <span id="des-safe-note">Landing area</span>
                </div>
            </aside>
            <div class="des-stage">
                <div class="des-concept"><strong>TOUCHDOWN · SELECTED CRATER</strong>LOLA DEM when loaded · stand-off rings are vehicle keep-out geometry, not plume CFD. Site Relief (right) places the pad on the clearest shoulder.</div>
                <div class="des-lola-badge" id="des-lola-badge">LOLA DEM</div>
                <div class="des-hud" id="des-hud" aria-live="polite">
                    <strong>PAD TELEMETRY</strong>
                    <span>Site <b id="des-hud-name">—</b></span>
                    <span>Pad elev <b id="des-hud-elev">—</b></span>
                    <span>Pad slope <b id="des-hud-slope">—</b></span>
                    <span>Safe / dust <b id="des-hud-plume">—</b></span>
                    <span>Ice case <b id="des-hud-ice">—</b></span>
                    <span>Battery <b id="des-hud-batt">—</b></span>
                </div>
                <p class="des-caption" id="des-caption">Waiting for the selected crater DEM.</p>
                <canvas id="des-stage" aria-label="Selected crater touchdown with plume stand-off rings"></canvas>
            </div>
            <aside class="des-side">
                <div class="des-pane des-water">
                    <p>WATER EXTRACTION</p>
                    <div class="des-water-row">
                        <div>
                            <div class="des-rate" id="des-water-rate">— <span>L/day</span></div>
                            <p class="des-note" id="des-water-total">Total: —</p>
                        </div>
                        <div class="des-tank" aria-hidden="true"><i id="des-water-fill" style="height:8%"></i></div>
                    </div>
                    <p class="des-note" id="des-water-note">Resource planning band. Not a measured yield.</p>
                    <p class="des-ice" id="des-ice"><b>ICE PROSPECT</b> Waiting on the latitude.</p>
                </div>
                <div class="des-pane des-plume">
                    <p>PLUME DISPERSION</p>
                    <canvas id="des-plume" aria-label="Safe radius and dust zone for the selected vehicle"></canvas>
                </div>
                <div class="des-pane des-map">
                    <div class="des-map-head">
                        <div>
                            <p class="des-map-kicker">SITE RELIEF</p>
                            <p class="des-map-sub">Surface map · pad on clearest shoulder</p>
                        </div>
                        <div class="des-map-modes" role="group" aria-label="Relief view mode">
                            <button type="button" data-des-map-mode="relief" aria-pressed="true">Relief</button>
                            <button type="button" data-des-map-mode="slope" aria-pressed="false">Slope</button>
                            <button type="button" data-des-map-mode="contour" aria-pressed="false">Contours</button>
                        </div>
                    </div>
                    <div class="des-map-tools" aria-label="Surface map controls">
                        <button type="button" id="des-map-zoom-out" aria-label="Zoom out">−</button>
                        <button type="button" id="des-map-zoom-in" aria-label="Zoom in">+</button>
                        <button type="button" id="des-map-reset">Reset</button>
                        <button type="button" id="des-map-pad" title="Center on pad">Pad</button>
                        <p id="des-map-readout" role="status">Click to inspect · planning only</p>
                    </div>
                    <div class="des-map-frame">
                        <canvas id="des-map" aria-label="Site relief map with pad and cold-trap band"></canvas>
                    </div>
                    <div class="des-map-legend" id="des-map-legend">
                        <span>Low</span>
                        <i class="des-map-swatch" id="des-map-swatch" aria-hidden="true"></i>
                        <span>High</span>
                    </div>
                    <div class="des-map-stats" aria-live="polite">
                        <div><span>PAD SLOPE</span><strong id="des-map-pad-slope">—</strong></div>
                        <div><span>INSPECT</span><strong id="des-map-inspect">—</strong></div>
                        <div><span>ZOOM</span><strong id="des-map-zoom">1.0×</strong></div>
                    </div>
                </div>
            </aside>
        </div>
        <footer class="des-foot">
            <div class="des-chip" id="des-status-chip"><span>TOUCHDOWN SCREEN</span><strong id="des-status">WAITING ON THE PATH</strong></div>
            <div class="des-chip"><span>WATER EXTRACTED</span><strong id="des-water-foot">—</strong></div>
            <div class="des-chip"><span>CARGO READY</span><strong id="des-power-foot">—</strong></div>
            <div class="des-chip" id="des-mission-chip"><span>MISSION STATUS</span><strong id="des-mission-foot">SET OPTIONS</strong></div>
        </footer>
    </section>
    <section class="panel kept-record" id="base-yard" hidden aria-hidden="true"></section>

    <div class="stage kept-record{% if active_view != 'mission' %} feature-open{% endif %}" id="stage">
    <div class="stage-main">
    <section id="mission-workflow" class="workflow-panel" data-view="mission">
        <section class="panel landing-quiz" id="landing-quiz">
            <div class="eyebrow">Start</div>
            <h2>Where are you landing?</h2>
            <div class="quiz-row" id="quiz-region">
                <button type="button" data-value="pole" aria-pressed="true">South pole</button>
                <button type="button" data-value="equator" aria-pressed="false">Near the equator</button>
                <button type="button" data-value="anywhere" aria-pressed="false">Anywhere</button>
            </div>
            <h2>What is the rocket?</h2>
            <div class="quiz-row" id="quiz-rocket">
                <button type="button" data-value="hopper" aria-pressed="false">Small hopper</button>
                <button type="button" data-value="crew" aria-pressed="true">Crew lander</button>
                <button type="button" data-value="cargo" aria-pressed="false">Cargo lander</button>
            </div>
            <h2>What matters most?</h2>
            <div class="quiz-row" id="quiz-priority">
                <button type="button" data-value="flat" aria-pressed="true">Flat ground</button>
                <button type="button" data-value="sun" aria-pressed="false">Sunlight</button>
                <button type="button" data-value="earth" aria-pressed="false">Earth radio</button>
            </div>
            <div class="button-row"><button type="button" id="run-quiz">Show the best place</button></div>
            <p class="small-print" id="quiz-status" role="status"></p>
            <div id="landing-result" hidden>
                <p class="landing-name" id="landing-name"></p>
                <p class="landing-coords" id="landing-coords"></p>
                <canvas id="landing-bars" role="img" aria-label="Flat, sun, and Earth scores for the chosen place"></canvas>
                <canvas id="landing-rank" role="img" aria-label="How the named places ranked"></canvas>
                <div class="landing-notes">
                    <ul id="landing-pros"></ul>
                    <ul id="landing-cons"></ul>
                </div>
                <div id="landing-photos" class="photo-strip"></div>
            </div>
        </section>
        <section class="panel">
            <div class="eyebrow">The problem</div>
            <h2>Astronauts at Shackleton have to cross a crater rim</h2>
            <p class="simple-intro">The next cell can be too steep to walk, a ridge can hide Earth, and a low Sun can leave the ground in shadow. Zero-Point Lunar runs five TensorFlow models, trained on NASA LOLA elevation from this crater, and marks the cells where a traveler can go.</p>
            <p class="link-line" id="shackleton-call">Running the five trained models on the Shackleton rim…</p>
            <div class="accuracy-chips" id="accuracy-chips" aria-label="Held-out model accuracy">
                <span>walk_safe <b id="acc-walk_safe">—</b></span>
                <span>pad_safe <b id="acc-pad_safe">—</b></span>
                <span>earth_clear <b id="acc-earth_clear">—</b></span>
                <span>sun_clear <b id="acc-sun_clear">—</b></span>
                <span>go_zone <b id="acc-go_zone">—</b></span>
            </div>
            <canvas id="shackleton-grid" class="site-canvas shackleton-grid" role="img" aria-label="Shackleton cells colored by the go model"></canvas>
            <div class="solar-summary" id="shackleton-counts" aria-live="polite">
                <div class="solar-value"><span>Walkable</span><strong id="count-walk_safe">…</strong></div>
                <div class="solar-value"><span>Flat enough to camp</span><strong id="count-pad_safe">…</strong></div>
                <div class="solar-value"><span>Earth in view</span><strong id="count-earth_clear">…</strong></div>
                <div class="solar-value"><span>Low Sun reaches</span><strong id="count-sun_clear">…</strong></div>
                <div class="solar-value"><span>Go for the crew</span><strong id="count-go_zone">…</strong></div>
            </div>
            <p class="small-print">Green cells are a go. Amber cells can be walked but fail Earth or the low Sun. Red cells are too steep. Each cell is about 3 km across because LOLA LDEM 16 is about 1.9 km per pixel. Accuracy chips are held-out checks on 106 Shackleton cells.</p>
            <p class="link-line" id="link-mission">The path check uses the same slope limit.</p>
            <p class="small-print" id="mission-shelter">Shelter action follows the storm state and the shelter answer.</p>
            <p class="small-print" id="mission-localization">Position check follows the path distance and any photo fix.</p>
            <p class="small-print" id="mission-assumptions"></p>
            <div class="data-links">
                <button type="button" id="load-shackleton">Try the Shackleton rim</button>
            </div>
            {% if site_reference_links %}
            <div class="source-links" aria-label="South-pole site and power research">
                {% for link in site_reference_links %}
                <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a>
                {% endfor %}
            </div>
            {% endif %}
        </section>
    </section>
    </div>
    <aside class="feature-rail">
        <p class="feature-label">Side checks</p>
        <nav class="workflow-tabs" role="tablist" aria-label="Side checks for this site">
            <button id="tab-dust" type="button" role="tab" aria-controls="dust-workflow"
                    aria-selected="{{ 'true' if active_view == 'dust' else 'false' }}" data-view="dust">Surface</button>
            <button id="tab-solar" type="button" role="tab" aria-controls="solar-workflow"
                    aria-selected="{{ 'true' if active_view == 'solar' else 'false' }}" data-view="solar">Solar flares</button>
            <button id="tab-movement" type="button" role="tab" aria-controls="movement-workflow"
                    aria-selected="{{ 'true' if active_view == 'movement' else 'false' }}" data-view="movement">Power path</button>
            <button id="tab-radiation" type="button" role="tab" aria-controls="radiation-workflow"
                    aria-selected="{{ 'true' if active_view == 'radiation' else 'false' }}" data-view="radiation">Radiation</button>
            <button id="tab-temperature" type="button" role="tab" aria-controls="temperature-workflow"
                    aria-selected="{{ 'true' if active_view == 'temperature' else 'false' }}" data-view="temperature">Sun &amp; cold</button>
            <button id="tab-data" type="button" role="tab" aria-controls="data-workflow"
                    aria-selected="{{ 'true' if active_view == 'data' else 'false' }}" data-view="data">Data</button>
        </nav>
        <div class="feature-stage">
    <section id="solar-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-solar"
             data-view="solar" {{ 'hidden' if active_view != 'solar' else '' }}>
        <section class="panel">
            <div class="eyebrow">Solar flares · NOAA GOES observations</div>
            <h2>Watch the Sun's X-ray activity</h2>
            <p class="link-line" id="link-solar">The flare steps use the shelter answer.</p>
            <p class="simple-intro">The chart is measured NOAA GOES X-ray data. The chance beside it comes from a small sunspot model. Neither one is a radiation dose at the Moon.</p>
            <div class="solar-summary" aria-live="polite">
                <div class="solar-value"><span>Latest X-ray level</span><strong id="solar-current">Loading…</strong></div>
                <div class="solar-value"><span>Highest level in past 24 hours</span><strong id="solar-peak">Loading…</strong></div>
                <div class="solar-value"><span>Last reading time (UTC)</span><strong id="solar-updated">Waiting for NOAA</strong></div>
            </div>
            <canvas id="solar-chart" role="img" aria-label="NOAA GOES X-ray measurements over the recent period"></canvas>
            <p class="small-print" id="solar-status" role="status" aria-live="polite">Loading NOAA satellite readingsâ€¦</p>
            <div class="solar-summary">
                <div class="solar-value"><span>Example sunspot · 24h M/X chance</span><strong id="flare-probability">Checkingâ€¦</strong></div>
                <div class="solar-value"><span>Hardware plan</span><strong id="flare-action">Waiting for the check</strong></div>
            </div>
            <ul class="protect-list" id="flare-protection"></ul>
            <p class="small-print" id="flare-caveat"></p>
            <details class="flare-questions" id="flare-questions">
                <summary>Change the sunspot questions</summary>
                <div class="form-grid">
                    <div class="field"><label for="zurich_class">Zurich class</label>
                        <select id="zurich_class"><option>A</option><option>B</option><option>C</option><option>D</option><option>E</option><option selected>F</option><option>H</option></select></div>
                    <div class="field"><label for="spot_size">Largest spot</label>
                        <select id="spot_size"><option>X</option><option>R</option><option>S</option><option>A</option><option>H</option><option selected>K</option></select></div>
                    <div class="field"><label for="distribution">Distribution</label>
                        <select id="distribution"><option>X</option><option>O</option><option>I</option><option selected>C</option></select></div>
                    <div class="field"><label for="activity">Recent activity</label>
                        <select id="activity"><option value="1">1 · reduced</option><option value="2" selected>2 · unchanged</option></select></div>
                    <div class="field"><label for="evolution">Evolution</label>
                        <select id="evolution"><option value="1">1 · decay</option><option value="2">2 · no growth</option><option value="3" selected>3 · growth</option></select></div>
                    <div class="field"><label for="prev_flare">Previous 24h</label>
                        <select id="prev_flare"><option value="1">1 · below M1</option><option value="2" selected>2 · one M1</option><option value="3">3 · above M1</option></select></div>
                </div>
                <div class="button-row"><button id="run-flare" type="button">Update the 24-hour chance</button></div>
            </details>
            <div class="data-links">
                <a href="https://www.swpc.noaa.gov/products/goes-x-ray-flux" target="_blank" rel="noopener">NOAA · GOES X-ray flux</a>
                <a href="https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json" target="_blank" rel="noopener">View the raw 24-hour data</a>
            </div>
            <div class="simple-card" style="margin-top:16px">
                <h3>How to read this</h3>
                <p>GOES measures X-rays near Earth. The letter (A, B, C, M, or X) is the standard X-ray class. A solar flare is not the same as a radiation dose on the lunar surface. A flare cannot be stopped. The steps under the chance are how to keep hardware working.</p>
            </div>
        </section>
    </section>

    <section id="radiation-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-radiation"
             data-view="radiation" {{ 'hidden' if active_view != 'radiation' else '' }}>
        <section class="panel">
            <div class="eyebrow">Lunar radiation</div>
            <h2>Radiation needs a Moon-side sensor</h2>
            <canvas id="radiation-board" role="img" aria-label="Moonlight, the quiet-surface reference, and the GOES proton scale"></canvas>
            <p class="link-line" id="link-radiation">The dose uses the drive time from the path.</p>
            <p class="simple-intro">This app has no radiation detector connected, so it cannot show a current dose or declare a site safe.</p>
            <div class="radiation-status"><strong>No live lunar radiation readings.</strong> Earth-orbit solar data is not a measurement of radiation at a rover on the Moon.</div>
            <div class="solar-summary" aria-live="polite">
                <div class="solar-value"><span>Moonlight at Earth</span><strong id="moonlight-value">Checkingâ€¦</strong></div>
                <div class="solar-value"><span>Quiet-surface reference</span><strong id="gcr-value">57 µSv/hr</strong></div>
                <div class="solar-value"><span>GOES protons â‰¥10 MeV</span><strong id="proton-value">Checkingâ€¦</strong></div>
            </div>
            <p class="small-print" id="radiation-note">The 57 µSv/hr figure is the published Chang'e-4 quiet-surface average, not a live rover dose.</p>
            <ul class="protect-list" id="radiation-protection"></ul>
            <div class="simple-grid">
                <article class="simple-card">
                    <h3>What a real reading needs</h3>
                    <p>A calibrated radiation instrument at the rover, its location, timestamp, and dose units. Solar flare alerts alone cannot tell the surface dose.</p>
                </article>
                <article class="simple-card">
                    <h3>Research data to start with</h3>
                    <p>Use measured lunar datasets to build a traceable model. Archived readings are research data, not a live safety warning.</p>
                </article>
            </div>
            <div class="data-links" aria-label="Radiation research data">
                <a href="https://pds-geosciences.wustl.edu/missions/lro/crater.htm" target="_blank" rel="noopener">NASA PDS · LRO CRaTER data</a>
                <a href="https://pds.nasa.gov/" target="_blank" rel="noopener">NASA Planetary Data System</a>
                <a href="https://science.nasa.gov/heliophysics/" target="_blank" rel="noopener">NASA · space radiation research</a>
            </div>
            <p class="small-print">Next step: use instrument-checked CRaTER records with documented units and timestamps. Do not treat this page as a radiation forecast.</p>
            <details class="model-readiness">
                <summary>Models &amp; training data status</summary>
                <div class="dataset-counts">Current image dataset: {{ dataset_summary }}. No labeled dust, solar-flare image, or lunar-radiation training set is installed.</div>
                <p class="small-print">These archives are starting points, not ready-to-train labels. Review the data, units, location, and licensing before adding any model training.</p>
                <div class="data-links" aria-label="Model training data sources">
                    <a href="https://wms.lroc.asu.edu/lroc/search" target="_blank" rel="noopener">LROC · lunar images</a>
                    <a href="https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json" target="_blank" rel="noopener">NOAA · solar X-rays</a>
                    <a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">NASA PDS · LOLA elevation</a>
                    <a href="https://pds-geosciences.wustl.edu/missions/lro/crater.htm" target="_blank" rel="noopener">NASA PDS · CRaTER radiation</a>
                </div>
                <div class="model-readiness-grid">
                    <div><strong>Moon dust</strong><p>Experimental image labels: {{ model_classes or "Training required" }}. These labels do not detect dust or estimate risk.</p></div>
                    <div><strong>Solar flares</strong><p>Measured GOES X-rays sit next to a small sunspot model. That model is not NOAA's forecast.</p></div>
                    <div><strong>Movement</strong><p>LOLA elevation data supports a coarse route screen. It is not a rover clearance.</p></div>
                    <div><strong>Lunar radiation</strong><p>No live sensor or radiation model is connected. NASA PDS links above provide research data to review.</p></div>
                </div>
            </details>
        </section>
        <details class="panel">
            <summary>Advanced status &amp; model details</summary>
        <div class="mission-command">
            <section class="panel mission-directive">
                <div class="panel-heading"><h2>WHAT TO DO NOW</h2><span class="tag">Decision support · not flight guidance</span></div>
                <div class="decision-banner" id="next-action">Loading the selected terrain window and checking the traverse endpointsâ€¦</div>
                <div class="section-label">Recommended sequence</div>
                <ol id="next-step-list"><li>Review the terrain-screened route and colored map areas.</li></ol>
            </section>
            <div class="system-grid">
                <section class="panel" id="rover-status">
                    <div class="panel-heading"><h2>ROVER STATUS</h2><span class="tag">Terrain simulation</span></div>
                    <div class="status-list">
                        <div class="status-row"><span>Route state</span><strong id="route-status">Awaiting DEM analysis</strong></div>
                        <div class="status-row"><span>Surface model</span><strong>LRO WAC / LOLA</strong></div>
                        <div class="status-row"><span>Grid resolution</span><strong id="grid-status">Pending</strong></div>
                        <div class="status-row"><span>Slope screen</span><strong id="slope-limit-status">{{ max_slope_degrees }}° threshold</strong></div>
                        <div class="status-row"><span>Planning speed</span><strong id="planning-speed-status">{{ planning_speed_kmh }} km/h assumption</strong></div>
                        <div class="status-row"><span>Target coordinates</span><strong>{{ start_lat }}°, {{ start_lon }}°</strong></div>
                        <div class="status-row"><span>Photo GPS</span><strong>{{ "EXIF / supplied" if image_result and image_result.location else "No photo fix" }}</strong></div>
                        <div class="status-row"><span>Satellite telemetry</span><strong>Not connected</strong></div>
                    </div>
                    <div class="telemetry-disclaimer">No live rover or satellite telemetry is connected. Speed and time are planning estimates, never live measurements.</div>
                </section>
                <section class="panel" id="mission-alerts-panel">
                    <div class="panel-heading"><h2>MISSION ALERTS</h2><span class="tag">DEM screening</span></div>
                    <div class="alert-list" id="mission-alerts" aria-live="polite">
                        <div class="alert-item">Awaiting route and hazard analysis.</div>
                    </div>
                </section>
            </div>
            <section class="panel model-readiness">
                <div class="panel-heading"><h2>ANALYSIS MODELS &amp; DATA LIMITS</h2><span class="tag">Evidence before prediction</span></div>
                <div class="model-readiness-grid">
                    <div><strong>LOLA terrain screen</strong><p>Multi-scale slope and local-relief routing from LDEM 16 (~1.9 km/pixel). Broad hazards only; individual rocks are unresolved.</p></div>
                    <div><strong>Rover image classifier</strong><p>Available labels: {{ model_classes or "Training required" }}. Outputs are uncalibrated labels, not probabilities or coordinates.</p></div>
                    <div><strong>Image geolocation</strong><p>Uses embedded or supplied GPS only. No validated lunar image-matching model is installed.</p></div>
                    <div><strong>Dust-plume corridor screen</strong><p>Checks route overlap with a user-entered plume envelope. It is not a plume-physics model or probability forecast.</p></div>
                </div>
            </section>
            <section class="panel nasa-operations">
                <div class="panel-heading"><h2>NASA DATA &amp; OPERATIONS REFERENCES</h2><span class="tag">External research links</span></div>
                <div class="mission-links" aria-label="Basemap and archive portals">
                    <a href="https://trek.nasa.gov/moon/" target="_blank" rel="noopener">Moon Trek · regional basemap</a>
                    <a href="https://quickmap.lroc.asu.edu/" target="_blank" rel="noopener">LROC QuickMap · orbital layers</a>
                    <a href="https://wms.lroc.asu.edu/lroc/search" target="_blank" rel="noopener">LROC image search</a>
                    <a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">LOLA PDS archive</a>
                </div>
                {% if reference_links %}
                <div class="section-label" style="margin-top:10px">Curated research corpus · dataset/articles</div>
                <div class="mission-links" aria-label="Curated NASA and research article links">
                    {% for link in reference_links %}
                    <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a>
                    {% endfor %}
                </div>
                {% endif %}
                <p class="telemetry-disclaimer">These publications inform engineering context; they do not supply a local forecast or qualify this prototype as flight software.</p>
            </section>
        </div>
        </details>
    </section>

    <section id="movement-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-movement"
             data-view="movement" {{ 'hidden' if active_view != 'movement' else '' }}>
    <section class="panel">
        <div class="eyebrow">Elevation · rover movement</div>
        <h2>See the climb, then where to go</h2>
        <p class="link-line" id="link-path">The climb limit comes from the questions.</p>
        <p class="small-print">The profile uses orbital elevation along the path. Red marks are steps steeper than the rover's limit, and they stay inside the frame.</p>
        <div class="stage-card">
            <canvas id="elevation-stage" class="stage-canvas" role="img" aria-label="Cartoon elevation profile of the rover route"></canvas>
            <p class="small-print" id="elevation-readout">The climb profile appears after the terrain map loads.</p>
        </div>
        <p class="small-print">The map below compares paths. It is a planning aid, not live rover tracking or a safety approval.</p>
        <div class="data-links"><button id="edit-route-inputs" type="button">Edit route in Moon dust</button></div>
    </section>
    <section class="metrics" aria-label="Mission planning summary">
        <div class="metric"><span class="metric-icon">âŒ–</span><div><div class="eyebrow">Candidate traverse</div><strong id="distance-value">Computing routeâ€¦</strong></div></div>
        <div class="metric"><span class="metric-icon">â†”</span><div><div class="eyebrow">Direct separation</div><strong id="mission-direct-distance">Calculatingâ€¦</strong></div></div>
        <div class="metric"><span class="metric-icon">â—·</span><div><div class="eyebrow">Estimated time</div><strong id="mission-eta-value">Pending route</strong></div></div>
        <div class="metric"><span class="metric-icon">â–³</span><div><div class="eyebrow">Terrain areas to review</div><strong id="hazard-summary">Waiting for map data</strong></div></div>
        <div class="metric"><span class="metric-icon">âŒ</span><div><div class="eyebrow">Rover planning speed</div><strong id="mission-speed">{{ planning_speed_kmh }} km/h assumption</strong></div></div>
    </section>
    <div class="layout">
        <section class="panel" id="map-panel">
            <div class="mission-map-content" id="mission-map-content">
            <div class="panel-heading">
                <div class="map-heading"><svg viewBox="0 0 28 28"><path d="m2 8 7-4 8 4 9-5v17l-9 5-8-4-7 4zM9 4v17m8-13v17"/></svg><h2>LUNAR SURFACE &amp; TERRAIN</h2></div>
                <div class="map-tools">
                    <button id="hazard-toggle" class="toolbar-button" type="button" aria-pressed="true">Hazards · ON</button>
                    <button id="center-map" class="toolbar-button" type="button">Center map</button>
                    <button id="export-assessment" class="toolbar-button" type="button" disabled>Download evidence</button>
                </div>
            </div>
            <div id="map" role="application" aria-label="Lunar surface map with route and slope hazards"></div>
            <div class="legend">
                <span><i class="swatch green"></i>Start</span><span><i class="swatch red"></i>Destination</span>
                <span><i class="swatch"></i>Terrain-safe route</span>
                <span><i class="unsafe-route-swatch"></i>Least-risk preview · not cleared</span>
                <span><i class="direct-route-swatch"></i>Direct reference</span>
                <span><i class="swatch purple"></i>DEM candidate · not photo location</span>
                <span><i class="plume-swatch"></i>User-defined plume corridor</span>
            </div>
            <div class="legend complexity-legend" aria-label="Relative terrain complexity color scale">
                <span>Relative DEM complexity</span>
                <span><i class="swatch"></i>0–34</span><span><i class="swatch green"></i>35–54</span>
                <span><i class="swatch yellow"></i>55–69</span><span><i class="swatch orange"></i>70–84</span>
                <span><i class="swatch red"></i>85–100</span><i class="complexity-gradient"></i>
                <span>Colors rank slope + local relief; they are not probabilities.</span>
            </div>
            <div class="route-readout"><span id="route-detail">Route profile pending</span><span id="hazard-detail">Hazard markers pending</span><span id="plume-detail">Plume corridor screen pending</span></div>
            <details class="route-evidence" id="route-evidence">
                <summary>Route decision evidence · DEM samples</summary>
                <div class="route-evidence-body">
                    <div class="route-evidence-grid">
                        <div><small>Direct-line samples over limit</small><strong id="direct-exceedance">Pending</strong></div>
                        <div><small>Selected-path samples over limit</small><strong id="path-exceedance">Pending</strong></div>
                        <div><small>Selected-path maximum slope</small><strong id="path-max-slope">Pending</strong></div>
                        <div><small>Path / direct distance</small><strong id="route-detour">Pending</strong></div>
                    </div>
                    <p class="route-evidence-note" id="route-evidence-note">The terrain screen uses a coarse orbital DEM; these samples are not a safety certification.</p>
                </div>
            </details>
            <div class="mission-links" aria-label="NASA and LROC target-area imagery">
                <a href="https://trek.nasa.gov/moon/" target="_blank" rel="noopener">NASA Moon Trek · regional basemap</a>
                <a href="https://quickmap.lroc.asu.edu/" target="_blank" rel="noopener">LROC QuickMap · orbital imagery</a>
                <a href="https://wms.lroc.asu.edu/lroc/search" target="_blank" rel="noopener">Search LROC images</a>
                <a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">LOLA archive</a>
            </div>
            </div>
        </section>
    </div>
    </section>

    <section id="dust-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-dust"
             data-view="dust" {{ 'hidden' if active_view != 'dust' else '' }}>
        <section class="panel route-panel">
            <div class="eyebrow">Moon dust</div>
            <h2>Check whether a dust plume could cross the route</h2>
            <p class="link-line" id="link-dust">Dust uses the same path as the other boards.</p>
            <p class="simple-intro">This board only looks for where dust can settle and where the ground is steep. The path itself stays on Elevation.</p>
            <div class="look-row">
                <canvas id="dust-look" class="stage-canvas" role="img" aria-label="Hillshade of the ground around the route"></canvas>
                <div class="look-copy">
                    <p class="small-print" id="dust-look-readout">Looking around the route. Upload a picture with GPS to switch this view to the ground around the photo.</p>
                    <div class="score-row" id="dust-hazard-chips"></div>
                </div>
            </div>
            <p class="small-print">The corridor check still needs a documented plume area. This tool does not detect dust in real time or predict how dust moves.</p>
            <div class="panel-heading"><div><div class="eyebrow">Route and field setup</div><h2>Choose where to screen</h2></div><span class="tag">Edit coordinates · recalculate</span></div>
            {% if form_error %}<div class="error-banner">{{ form_error }}</div>{% endif %}
            <div class="route-layout">
            <div class="route-controls-column">
            <form id="route-form" method="post" enctype="multipart/form-data">
            <details class="input-drawer" id="route-settings" open>
                <summary>Mission route inputs</summary>
                <div class="section-label">Traverse endpoints · lunar coordinates</div>
                <div class="form-grid">
                    <div class="field"><label for="start_name">Start site</label><input id="start_name" name="start_name" value="{{ start_name }}" maxlength="80" required></div>
                    <div class="field"><label for="start_lat">Start latitude (°)</label><input id="start_lat" name="start_lat" type="number" step="any" min="-90" max="90" value="{{ start_lat }}" required></div>
                    <div class="field"><label for="start_lon">Start longitude (°)</label><input id="start_lon" name="start_lon" type="number" step="any" min="-180" max="180" value="{{ start_lon }}" required></div>
                    <div class="field"><label for="dest_name">Destination site</label><input id="dest_name" name="dest_name" value="{{ dest_name }}" maxlength="80" required></div>
                    <div class="field"><label for="dest_lat">Destination latitude (°)</label><input id="dest_lat" name="dest_lat" type="number" step="any" min="-90" max="90" value="{{ dest_lat }}" required></div>
                    <div class="field"><label for="dest_lon">Destination longitude (°)</label><input id="dest_lon" name="dest_lon" type="number" step="any" min="-180" max="180" value="{{ dest_lon }}" required></div>
                </div>
                <div class="section-label">Rover planning assumptions · editable scenario values</div>
                <div class="form-grid">
                    <div class="field"><label for="max_slope_degrees">Slope screen limit (°)</label><input id="max_slope_degrees" name="max_slope_degrees" type="number" step="any" min="5" max="30" value="{{ max_slope_degrees }}" required></div>
                    <div class="field"><label for="planning_speed_kmh">Planning speed (km/h)</label><input id="planning_speed_kmh" name="planning_speed_kmh" type="number" step="any" min="0.1" max="5" value="{{ planning_speed_kmh }}" required></div>
                </div>
                <details class="field-observations" id="field-observations">
                <summary>Optional field observations · image, GPS and notes</summary>
                <div class="field"><label for="image">Rover image · local terrain classifier</label><input id="image" name="image" type="file" accept="image/png,image/jpeg,image/webp,image/gif"></div>
                <div class="image-preview" id="image-preview" hidden>
                    <img id="image-preview-img" alt="Selected rover terrain image preview">
                    <div class="image-preview-copy">
                        Preview only; enhancement does not change the original image used by the classifier.
                        <label><input id="image-enhance" type="checkbox"> Improve preview contrast</label>
                    </div>
                </div>
                <div class="form-grid" style="margin-top:9px">
                    <div class="field"><label for="image_lat">Image GPS latitude override (°) · optional</label><input id="image_lat" name="image_lat" type="number" step="any" min="-90" max="90" value="{{ image_lat }}" placeholder="EXIF GPS is read automatically"></div>
                    <div class="field"><label for="image_lon">Image GPS longitude override (°) · optional</label><input id="image_lon" name="image_lon" type="number" step="any" min="-180" max="180" value="{{ image_lon }}" placeholder="EXIF GPS is read automatically"></div>
                </div>
                <div class="note" id="photo-gps-state">EXIF GPS is checked automatically after upload. A photo without GPS cannot be located by the installed terrain-label classifier; no coordinate is invented.</div>
                <div class="note">When image GPS is available, nearby context is sampled from the LRO elevation DEM. This finds regional slope/relief features, not individual objects visible in the photo.</div>
                <div class="field" style="margin-top:9px"><label for="article_text">Article / mission-note excerpt · explainable keyword screening</label><textarea id="article_text" name="article_text" maxlength="12000" placeholder="Paste text to surface mentions of lunar dust, plumes, steep slopes, boulders, or other configured risk terms.">{{ article_text }}</textarea></div>
                </details>
                <div class="button-row"><button class="calculate-button" type="submit">Update route &amp; check dust corridor</button></div>
            </details>
            </form>
            </div>
            <aside class="route-context-column" aria-label="Model readiness and mission data context">
            <details class="plume-model-panel" id="plume-model-panel">
                <summary>New model · dust-plume corridor screen</summary>
                <div class="note">Enter a source and directional envelope from an observed event or a documented plume simulation. This model checks geometric route overlap; it does not simulate gas flow, particle transport, or deposition.</div>
                <div class="form-grid">
                    <div class="field"><label for="plume_source_lat">Plume source latitude (°)</label><input id="plume_source_lat" type="number" step="any" min="-90" max="90" placeholder="Required"></div>
                    <div class="field"><label for="plume_source_lon">Plume source longitude (°)</label><input id="plume_source_lon" type="number" step="any" min="-180" max="180" placeholder="Required"></div>
                    <div class="field"><label for="plume_azimuth">Axis azimuth (° clockwise from north)</label><input id="plume_azimuth" type="number" step="any" min="0" max="360" placeholder="0–360"></div>
                    <div class="field"><label for="plume_extent">Downrange extent (km)</label><input id="plume_extent" type="number" step="any" min="0.001" max="500" placeholder="From evidence / scenario"></div>
                    <div class="field"><label for="plume_half_width">Cross-track half-width (km)</label><input id="plume_half_width" type="number" step="any" min="0.001" max="100" placeholder="From evidence / scenario"></div>
                    <div class="field"><label for="plume_evidence_source">Event / simulation reference · optional</label><input id="plume_evidence_source" type="text" maxlength="240" placeholder="Report ID, URL, or scenario note"></div>
                </div>
                <button class="calculate-button" id="screen-plume" type="button" disabled>Screen candidate route</button>
                <div class="note plume-screen-result" id="plume-screen-result" role="status" aria-live="polite">Waiting for terrain-route analysis and a plume-envelope input.</div>
                <div class="source-links" aria-label="NASA dust plume research">
                    <a href="https://ntrs.nasa.gov/citations/20180001348" target="_blank" rel="noopener">NASA · plume-impingement contamination</a>
                    <a href="https://ntrs.nasa.gov/citations/20240009989" target="_blank" rel="noopener">NASA · thermal impacts</a>
                    <a href="https://ntrs.nasa.gov/citations/20250005201" target="_blank" rel="noopener">NASA · VIPER dust mitigation</a>
                    <a href="https://ntrs.nasa.gov/citations/20220018746" target="_blank" rel="noopener">NASA · mitigation guide</a>
                    {% for link in dust_reference_links %}
                    <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a>
                    {% endfor %}
                </div>
            </details>
            {% if image_result %}
            <div class="result">
                <strong>Experimental image label (not a safety decision): {{ image_result.label }} · {{ image_result.confidence }}% raw score</strong><br>
                {{ image_result.reason }}
                <div class="score-row">{% for name, score in image_result.scores.items() %}<span class="score">{{ name }} raw score {{ score }}%</span>{% endfor %}</div>
                Raw scores are uncalibrated and must not be interpreted as hazard probabilities.
                {% if image_result.location %}Image location: {{ image_result.location.lat|round(4) }}°, {{ image_result.location.lon|round(4) }}°.
                    {% if image_result.nearby %}
                    Nearby DEM context: {{ image_result.nearby.max_slope_degrees }}° max slope and {{ image_result.nearby.max_roughness_m }} m max local relief across {{ image_result.nearby.radius_km }} km.
                    {{ image_result.nearby.resolution_note }}
                    {% if image_result.nearby.slope_hotspots %}<div class="score-row">{% for hotspot in image_result.nearby.slope_hotspots %}<span class="score">Nearby slope {{ hotspot.slope }}° · {{ hotspot.lat|round(3) }}, {{ hotspot.lon|round(3) }}</span>{% endfor %}</div>{% endif %}
                    {% endif %}
                {% else %}Image location is unknown. The map will mark the highest-complexity area in the selected map window as a fallback candidate; this is not a prediction of the photo's actual location.{% endif %}
                {% if not image_result.location %}<div class="note" id="image-fallback-note" hidden></div>{% endif %}
            </div>
            {% endif %}
            {% if image_error %}<div class="warning"><strong>Image analysis unavailable:</strong> {{ image_error }}</div>{% endif %}
            {% if image_context_error %}<div class="warning"><strong>Nearby terrain context unavailable:</strong> {{ image_context_error }}</div>{% endif %}
            {% if article_result %}
            <div class="{% if article_result.findings %}warning{% else %}note{% endif %}">
                <strong>Article text review:</strong> {{ article_result.summary }}
                {% for finding in article_result.findings %}
                    <div style="margin-top:5px"><strong>{{ finding.category }}:</strong> {{ finding.evidence|join(", ") }}</div>
                {% endfor %}
                This is explainable keyword screening, not a TensorFlow model or a probability estimate.
            </div>
            {% endif %}
            <div class="note route-model-note"><strong>Classifier readiness · review required:</strong> {{ model_classes or "Training required" }}. {{ model_validation }} Scores are uncalibrated and must not drive mission decisions.</div>
            <div class="note"><strong>Route details:</strong> The planner compares slope and local terrain shape using a coarse orbital map. Review route evidence on the Movement tab. This is not a rover safety approval.</div>
            <details class="source-limits">
                <summary>Dust forecast limits &amp; NASA research</summary>
                <div class="note"><strong>Forecast unavailable:</strong> lunar dust plumes are transient, event-driven phenomena rather than Earth-like weather storms. Static imagery and DEMs cannot forecast plume activity. The corridor screen below requires a user-supplied envelope and does not calculate probability.
                <div class="source-links">
                    <a href="https://ntrs.nasa.gov/citations/20180001348" target="_blank" rel="noopener">NASA · plume-impingement contamination modeling</a>
                    <a href="https://ntrs.nasa.gov/citations/20240009989" target="_blank" rel="noopener">NASA · Thermal impacts of lunar dust</a>
                    <a href="https://ntrs.nasa.gov/citations/20250005201" target="_blank" rel="noopener">NASA · VIPER dust mitigation</a>
                    <a href="https://ntrs.nasa.gov/citations/20220018746" target="_blank" rel="noopener">NASA · Lunar dust mitigation guide</a>
                    <a href="https://ntrs.nasa.gov/citations/20260001844" target="_blank" rel="noopener">NASA · Dust mitigation roadmap</a>
                    {% for link in dust_reference_links %}
                    <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a>
                    {% endfor %}
                </div>
                </div>
            </details>
            </aside>
            </div>
        </section>
    </section>

    <section id="temperature-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-temperature"
             data-view="temperature" {{ 'hidden' if active_view != 'temperature' else '' }}>
        <section class="panel">
            <div class="eyebrow">Temperature</div>
            <h2>Day heat and night cold</h2>
            <p class="link-line" id="link-temperature">Temperature uses the start of the same path.</p>
            <p class="simple-intro">A lunar day swings from sunlit heat to hard cold. This envelope is for the start site. It is not a live Diviner reading.</p>
            <div class="solar-summary" aria-live="polite">
                <div class="solar-value"><span>Estimated now</span><strong id="temp-now">Checkingâ€¦</strong></div>
                <div class="solar-value"><span>Day high at this latitude</span><strong id="temp-day">Checkingâ€¦</strong></div>
                <div class="solar-value"><span>Night low at this latitude</span><strong id="temp-night">Checkingâ€¦</strong></div>
            </div>
            <canvas id="sun-compare" role="img" aria-label="Equator, 45 degrees, and 85 degrees across one lunar day"></canvas>
            <canvas id="temperature-stage" class="stage-canvas" role="img" aria-label="Temperature between the night low and the day high"></canvas>
            <p class="small-print" id="temp-note">Waiting for the site estimate.</p>
            <ul class="protect-list" id="temperature-protection"></ul>
            <div class="data-links">
                <a href="https://www.diviner.ucla.edu/" target="_blank" rel="noopener">UCLA · Diviner lunar radiometer</a>
                <a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">NASA PDS · LRO data</a>
            </div>
        </section>
    </section>

    <section id="data-workflow" class="workflow-panel" role="tabpanel" aria-labelledby="tab-data"
             data-view="data" {{ 'hidden' if active_view != 'data' else '' }}>
        <section class="panel">
            <div class="eyebrow">Models and databases</div>
            <h2>What is trained, and what the boards read</h2>
            <p class="simple-intro">One TensorFlow image model is installed. It does not detect ice. The site screen is topography, sunlight, and Earth angle.</p>
            <div class="simple-grid">
                <article class="simple-card">
                    <h3>Surface image model</h3>
                    <p>File <code>zeropoint_model.keras</code>. Labels: {{ model_classes or "not loaded" }}. An upload on Surface gets one of those labels. It is not an ice, frost, or boulder detector.</p>
                </article>
                <article class="simple-card">
                    <h3>Flare model</h3>
                    <p>A scikit-learn random forest on sunspot class, size, and recent activity. It scores an example region on Solar flares. It is not NOAA's forecast.</p>
                </article>
                <article class="simple-card">
                    <h3>Site screen</h3>
                    <p>LOLA slopes, one Sun angle, and the geometric height of Earth. A neighbor counts only if it is lower or steeper. That is not a permanently shadowed crater map and not a water-ice detection.</p>
                </article>
            </div>
            <div class="data-links" aria-label="Source databases">
                <a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">NASA PDS · LOLA elevation</a>
                <a href="https://wms.lroc.asu.edu/lroc/search" target="_blank" rel="noopener">LROC · surface images</a>
                <a href="https://www.swpc.noaa.gov/products/goes-x-ray-flux" target="_blank" rel="noopener">NOAA · GOES X-rays</a>
                <a href="https://www.swpc.noaa.gov/products/goes-proton-flux" target="_blank" rel="noopener">NOAA · GOES protons</a>
                <a href="https://www.diviner.ucla.edu/" target="_blank" rel="noopener">UCLA · Diviner temperatures</a>
                <a href="https://pds-geosciences.wustl.edu/missions/lro/crater.htm" target="_blank" rel="noopener">NASA PDS · CRaTER radiation</a>
            </div>
            <p class="small-print">Retrain the image model with <code>python train.py</code> only after real labeled pictures are added. The current holdout is not a mission test, and this app will not invent ice or thermal labels.</p>
        </section>
    </section>

    <section id="camera-workflow" class="workflow-panel" data-view="movement"
             {{ 'hidden' if active_view != 'movement' else '' }}>
        <aside class="right-rail" aria-label="Lunar camera and interactive terrain model">
            <section class="panel camera-panel" id="camera-view">
                <div class="panel-heading"><h2>CAMERA VIEW · LRO TERRAIN</h2><span class="tag">8 render angles</span></div>
                <div class="camera-frame">
                    <img id="camera-image" alt="Rendered lunar terrain view at the selected target" hidden>
                    <div class="camera-status" id="camera-status">Waiting for LRO elevation and color dataâ€¦</div>
                    <button class="camera-arrow prev" id="camera-prev" type="button" aria-label="Previous terrain view">â€¹</button>
                    <button class="camera-arrow next" id="camera-next" type="button" aria-label="Next terrain view">â€º</button>
                </div>
                <div class="camera-meta"><strong id="camera-view-name">Terrain render pending</strong><span>CAM 01 / 08</span></div>
                <div class="camera-dots" id="camera-dots" aria-label="Choose terrain render angle"></div>
                <div class="target-note">Target: 8.40651° N, 84.75701° E · 100 km radius · 500 × 500 mesh · LOLA LDEM 16 + LROC color</div>
                <div class="camera-source-footer">
                    <span>NASA / LROC / LOLA data</span>
                    <button id="gallery-open" type="button">NASA image library</button>
                    <button id="sources-open" type="button">Images &amp; source notes</button>
                </div>
            </section>

            <section class="panel model-panel" id="terrain-model-panel">
                <div class="panel-heading"><h2>INTERACTIVE 3D MODEL</h2><button id="expand-model" type="button" aria-pressed="false">Expand model</button></div>
                <div class="model-viewport" id="model-viewport">
                    <canvas id="terrain-canvas" aria-label="Interactive 3D lunar elevation mesh"></canvas>
                    <div class="model-status" id="model-status">Loading LRO elevation and color dataâ€¦</div>
                </div>
                <div class="model-toolbar">
                    <label for="relief-scale">Relief <input id="relief-scale" type="range" min="1" max="6" step="0.5" value="2"><span id="relief-label">2×</span></label>
                    <label><input id="wireframe" type="checkbox"> Wireframe</label>
                </div>
                <div class="target-note" id="terrain-summary">Waiting for terrain mesh</div>
            </section>
        </aside>
    </section>
    </div>
    </aside>
    </div>
    </div>
    <div id="page-data-panel" class="kept-record" data-page-panel="data" hidden>

    <section class="panel" id="trained-record">
        <div class="eyebrow">Trained on NASA LOLA</div>
        <h2>Five models, and how they scored on ground they had not seen</h2>
        <p class="simple-intro">423 Shackleton cells taught each model. 106 other cells from the same crater were held out. The number is that held-out accuracy. These models do not detect water ice.</p>
        <div class="trained-table-wrap">
            <table class="trained-table">
                <thead>
                    <tr><th>Model</th><th>What an astronaut asks</th><th>Rule learned from LOLA</th><th>Held-out accuracy</th></tr>
                </thead>
                <tbody id="trained-rows">
                    <tr><td colspan="4">Loading walk_safe.keras, pad_safe.keras, earth_clear.keras, sun_clear.keras, and go_zone.kerasâ€¦</td></tr>
                </tbody>
            </table>
        </div>
        <p class="small-print" id="trained-note">NASA LOLA LDEM 16. A cell is not a footstep.</p>
        {% if reference_links %}
        <div class="section-label" style="margin-top:12px">Research links used by this app</div>
        <div class="data-links" aria-label="Curated research article links">
            {% for link in reference_links %}
            <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.title }}</a>
            {% endfor %}
        </div>
        <p class="small-print">Loaded from dataset/articles/reference_links.json. These are engineering context sources, not live forecasts.</p>
        {% endif %}
    </section>
    <section class="panel" id="mission-catalog">
        <div class="eyebrow">Landings already flown</div>
        <h2>Who has reached the surface</h2>
        <p class="small-print">Published positions from NASA's catalog of spacecraft on the Moon. These rows are not a TensorFlow model, and they are not a new landing prediction. The cards below are live DuckDuckGo pages for the place you picked.</p>
        <div id="live-finds-data" class="live-finds"></div>
        <table class="mission-table">
            <thead><tr><th>Mission</th><th>Agency</th><th>Date</th><th>Place</th><th>Latitude</th><th>Longitude</th></tr></thead>
            <tbody>
                <tr><td>Chandrayaan-3</td><td>ISRO</td><td>2023-08-23</td><td>Statio Shiv Shakti</td><td>âˆ’69.374°</td><td>32.320°</td></tr>
                <tr><td>SLIM</td><td>JAXA</td><td>2024-01-19</td><td>Shioli</td><td>âˆ’13.316°</td><td>25.251°</td></tr>
                <tr><td>Chang'e-4</td><td>CNSA</td><td>2019-01-03</td><td>Von KÃ¡rmÃ¡n</td><td>âˆ’45.456°</td><td>177.589°</td></tr>
                <tr><td>Chang'e-6</td><td>CNSA</td><td>2024-06-01</td><td>South Pole–Aitken</td><td>âˆ’41.639°</td><td>âˆ’153.985°</td></tr>
                <tr><td>IM-1 Odysseus</td><td>Intuitive Machines</td><td>2024-02-22</td><td>Malapert A</td><td>âˆ’80.130°</td><td>1.440°</td></tr>
                <tr><td>IM-2</td><td>Intuitive Machines</td><td>2025-03-06</td><td>Mons Mouton</td><td>âˆ’84.791°</td><td>29.196°</td></tr>
                <tr><td>Blue Ghost 1</td><td>Firefly</td><td>2025-03-02</td><td>Mare Crisium</td><td>18.562°</td><td>61.810°</td></tr>
                <tr><td>Artemis III</td><td>NASA</td><td>Not landed</td><td>South-polar candidate regions</td><td>within 6° of the pole</td><td>—</td></tr>
            </tbody>
        </table>
    </section>
    </div>

    <dialog id="gallery-dialog" class="modal-dialog gallery-dialog" aria-labelledby="gallery-dialog-title">
        <div class="dialog-heading">
            <div><div class="eyebrow">External catalog · loaded on request</div><h2 id="gallery-dialog-title">NASA lunar image library</h2></div>
            <button class="dialog-close" type="button" data-close-dialog="gallery-dialog">Close</button>
        </div>
        <p class="gallery-disclaimer">NASA catalog results are lunar surface references, not confirmed photographs of this exact coordinate. The eight LROC/LOLA camera renders in the Camera &amp; 3D terrain tab are target-area views; use the official source links to search for matched observations.</p>
        <div id="gallery-status" class="note" role="status">Open the gallery to search NASA's public image catalog.</div>
        <div id="gallery-grid" class="gallery-grid"></div>
    </dialog>
    <dialog id="sources-dialog" class="modal-dialog sources-dialog" aria-labelledby="sources-dialog-title">
        <div class="dialog-heading">
            <div><div class="eyebrow">Target-area previews · official data portals</div><h2 id="sources-dialog-title">Imagery &amp; data sources</h2></div>
            <button class="dialog-close" type="button" data-close-dialog="sources-dialog">Close</button>
        </div>
        <p class="gallery-disclaimer">The thumbnails are local 3D views of the selected target built from LROC color and LOLA elevation data. They are not screenshots of the linked sites or individual NAC observation frames. Follow each link to explore its official maps and records.</p>
        <div class="source-gallery-grid">
            <article class="source-gallery-card">
                <img data-source-view="0" alt="Overhead target-area render">
                <div><h3>NASA Moon Trek</h3><p>NASA/USGS regional lunar basemaps and terrain context. Use the viewer to inspect the broader area around the rover target.</p><a href="https://trek.nasa.gov/moon/" target="_blank" rel="noopener">Open Moon Trek â†—</a></div>
            </article>
            <article class="source-gallery-card">
                <img data-source-view="2" alt="East oblique target-area render">
                <div><h3>LROC QuickMap</h3><p>Arizona State University's orbital map for exploring LROC imagery and lunar data layers. Available image coverage varies by layer and location.</p><a href="https://quickmap.lroc.asu.edu/" target="_blank" rel="noopener">Open QuickMap â†—</a></div>
            </article>
            <article class="source-gallery-card">
                <img data-source-view="4" alt="West oblique target-area render">
                <div><h3>LROC Image Search</h3><p>Search Narrow Angle and Wide Angle Camera observation records by footprint and product. Check around 8.40651° N, 84.75701° E and confirm a scene footprint before treating it as a local photograph.</p><a href="https://wms.lroc.asu.edu/lroc/search" target="_blank" rel="noopener">Search LROC records â†—</a></div>
            </article>
            <article class="source-gallery-card">
                <img data-source-view="7" alt="West grazing target-area render">
                <div><h3>LOLA PDS archive</h3><p>Planetary Data System archive for LRO laser-altimeter products. The LDEM 16 terrain used here resolves broad relief at roughly 1.9 km per pixel, not individual rocks.</p><a href="https://pds-geosciences.wustl.edu/missions/lro/" target="_blank" rel="noopener">Open LOLA archive â†—</a></div>
            </article>
        </div>
    </dialog>
    </div>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js"}}
</script>
<script type="module">
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js";
import {OrbitControls} from "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/controls/OrbitControls.js";
const REFERENCE_LINKS = {{ reference_links|tojson }};
const map = L.map('map', {center: [{{ start_lat }}, {{ start_lon }}], zoom: 5, minZoom: 1, maxZoom: 9, crs: L.CRS.EPSG4326});
let latestTerrainPayload = null;
let latestEnvironment = null;
let solarSamples = [];
const moonTiles = "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg";
L.tileLayer(moonTiles, {attribution: "NASA / USGS Moon Trek", noWrap: true}).addTo(map);
L.control.scale({metric:true, imperial:false, position:"bottomleft"}).addTo(map);
const workflowTabs = Array.from(document.querySelectorAll(".workflow-tabs [role='tab']"));
const workflowPanels = Array.from(document.querySelectorAll(".workflow-panel"));
function activateWorkflow(view) {
    document.body.dataset.view = view;
    const stage = document.getElementById("stage");
    if (stage) stage.classList.toggle("feature-open", view !== "mission");
    workflowTabs.forEach(tab => {
        const selected = tab.dataset.view === view;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
    });
    workflowPanels.forEach(panel => {
        if (panel.id === "mission-workflow") {
            panel.hidden = false;
            return;
        }
        panel.hidden = panel.dataset.view !== view;
    });
    if (view === "movement") {
        requestAnimationFrame(() => {
            map.invalidateSize({pan:false});
            if (currentMapBounds) map.fitBounds(currentMapBounds, {padding:[25,25], maxZoom:8});
            if (latestTerrainPayload) drawElevationProfile(latestTerrainPayload);
        });
    }
    if (view === "dust") requestAnimationFrame(() => drawDustLook(latestTerrainPayload));
    if (view === "solar" && solarSamples.length) requestAnimationFrame(() => drawSolarChart(solarSamples));
    if (view === "temperature" && latestEnvironment) requestAnimationFrame(() => drawTemperature(latestEnvironment));
    if (view === "radiation") requestAnimationFrame(() => drawRadiation(latestEnvironment));
}
workflowTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
        activateWorkflow(tab.getAttribute("aria-selected") === "true" ? "mission" : tab.dataset.view);
    });
    tab.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const nextIndex = event.key === "Home" ? 0 :
            event.key === "End" ? workflowTabs.length - 1 :
                (index + (event.key === "ArrowRight" ? 1 : -1) + workflowTabs.length) % workflowTabs.length;
        workflowTabs[nextIndex].focus();
        activateWorkflow(workflowTabs[nextIndex].dataset.view);
    });
});
document.getElementById("edit-route-inputs").addEventListener("click", () =>
    activateWorkflow("dust")
);
const opsStarted = Date.now();
let opsTerrain = null;
let opsPlan = null;
let shackletonScreen = null;
let pathPhoto = null;
let pathPhotoKey = "";
let moonDisk = null;
let moonDiskKey = "";
function opsFit(canvas) {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return null;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return {context, width, height};
}
function opsGauge(canvas, fraction, caption, label, color) {
    const fit = opsFit(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    const cx = width / 2;
    const cy = height * 0.46;
    const radius = Math.min(width * 0.38, height * 0.32);
    const start = Math.PI * 0.75;
    const sweep = Math.PI * 1.5;
    const clamped = Math.max(0, Math.min(1, fraction));
    context.clearRect(0, 0, width, height);
    context.beginPath();
    context.arc(cx, cy, radius + 8, 0, Math.PI * 2);
    context.strokeStyle = "#12384a";
    context.lineWidth = 1;
    context.stroke();
    context.lineWidth = 10;
    context.strokeStyle = "#102833";
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep);
    context.stroke();
    context.strokeStyle = color;
    context.shadowColor = color;
    context.shadowBlur = 12;
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep * clamped);
    context.stroke();
    context.shadowBlur = 0;
    context.strokeStyle = "#8fd8df";
    context.lineWidth = 1;
    for (let tick = 0; tick <= 8; tick += 1) {
        const angle = start + sweep * (tick / 8);
        context.beginPath();
        context.moveTo(cx + Math.cos(angle) * (radius - 12), cy + Math.sin(angle) * (radius - 12));
        context.lineTo(cx + Math.cos(angle) * (radius - 5), cy + Math.sin(angle) * (radius - 5));
        context.stroke();
    }
    const needle = start + sweep * clamped;
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 14), cy + Math.sin(needle) * (radius - 14));
    context.stroke();
    context.fillStyle = color;
    context.beginPath();
    context.arc(cx, cy, 4, 0, Math.PI * 2);
    context.fill();
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#f4fbff";
    const valueSize = Math.max(13, Math.min(18, Math.floor(width * 0.12)));
    context.font = "700 " + valueSize + "px Share Tech Mono, monospace";
    context.fillText(String(caption), cx, cy + 2);
    context.textBaseline = "alphabetic";
    context.fillStyle = "#8fd8df";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.fillText(String(label), cx, Math.min(height - 10, cy + radius + 22));
}
function opsSeries(canvas, values, color, title, unit, marks, hline) {
    const fit = opsFit(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#8fd8df";
    context.font = "11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText(title, 8, 14);
    if (!values.length) {
        context.fillStyle = "#9ad7e4";
        context.fillText("NO PATH", 8, height / 2);
        return;
    }
    const dataMin = Math.min.apply(null, values);
    const dataMax = Math.max.apply(null, values);
    const guide = hline != null && Number.isFinite(Number(hline)) ? Number(hline) : null;
    let min = guide == null ? dataMin : Math.min(dataMin, guide);
    let max = guide == null ? dataMax : Math.max(dataMax, guide);
    if (unit === "km/h") {
        min = 0;
        max = Math.max(5, dataMax);
    }
    const span = Math.max(0.001, max - min);
    const left = 28;
    const top = 18;
    const plotW = width - 40;
    const plotH = height - 34;
    context.strokeStyle = "#1c4a5c";
    context.lineWidth = 1;
    context.font = "10px Segoe UI, Arial";
    context.fillStyle = "#8fd8df";
    for (let row = 0; row <= 3; row += 1) {
        const y = top + plotH * (row / 3);
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillText((max - span * row / 3).toFixed(1), 2, y + 3);
    }
    const depth = Math.max(5, Math.min(12, height * 0.08));
    const pts = values.map((value, index) => ({
        x: left + plotW * (index / Math.max(1, values.length - 1)),
        y: top + plotH * (1 - (value - min) / span)
    }));
    context.beginPath();
    pts.forEach((p, index) => { if (index) context.lineTo(p.x, p.y + depth); else context.moveTo(p.x, p.y + depth); });
    context.lineTo(pts[pts.length - 1].x, top + plotH + depth);
    context.lineTo(pts[0].x, top + plotH + depth);
    context.closePath();
    context.fillStyle = "rgba(4,12,18,.7)";
    context.fill();
    context.beginPath();
    pts.forEach((p, index) => {
        if (index) context.lineTo(p.x, p.y);
        else context.moveTo(p.x, p.y);
    });
    context.strokeStyle = color;
    context.shadowColor = color;
    context.shadowBlur = 12;
    context.lineWidth = 2.4;
    context.stroke();
    context.shadowBlur = 0;
    context.lineTo(pts[pts.length - 1].x, top + plotH);
    context.lineTo(pts[0].x, top + plotH);
    context.closePath();
    const wash = context.createLinearGradient(0, top, 0, top + plotH);
    wash.addColorStop(0, color);
    wash.addColorStop(1, "rgba(6,16,24,0)");
    context.globalAlpha = 0.42;
    context.fillStyle = wash;
    context.fill();
    context.globalAlpha = 1;
    pts.forEach((p, index) => {
        if (index % Math.max(1, Math.floor(pts.length / 8))) return;
        context.fillStyle = "#f4fbff";
        context.beginPath();
        context.arc(p.x, p.y, 2.1, 0, Math.PI * 2);
        context.fill();
    });
    context.fillStyle = "#d7f4ff";
    context.textAlign = "left";
    context.fillText(unit, left + plotW - 18, 12);
    if (hline != null && Number.isFinite(Number(hline))) {
        const line = Number(hline);
        const y = top + plotH * (1 - (line - min) / span);
        if (y >= top && y <= top + plotH) {
            context.setLineDash([4, 4]);
            context.strokeStyle = "#ff5a62";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(left, y);
            context.lineTo(left + plotW, y);
            context.stroke();
            context.setLineDash([]);
            context.fillStyle = "#ff8a90";
            context.textAlign = "right";
            context.fillText(line.toFixed(0) + unit, left + plotW, Math.max(top + 10, y - 3));
            context.textAlign = "left";
        }
    }
    (marks || []).forEach(mark => {
        const x = left + plotW * mark.t;
        context.strokeStyle = "rgba(230,195,106,.7)";
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(x, top);
        context.lineTo(x, top + plotH);
        context.stroke();
        context.fillStyle = "#e6c36a";
        context.font = "10px Segoe UI, Arial";
        context.textAlign = "center";
        context.fillText(mark.text, x, height - 2);
    });
}
let lolaHeightField = null;
function buildLolaHeightField(payload) {
    if (!payload || !payload.surface || !payload.surface.vertices) return null;
    const verts = payload.surface.vertices;
    const slopes = payload.surface.slopes || [];
    const colors = payload.surface.colors || [];
    const n = verts.length / 3;
    const grid = Math.round(Math.sqrt(n));
    if (grid * grid !== n || grid < 8) return null;
    let minZ = Infinity;
    let maxZ = -Infinity;
    const elev = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
        const z = verts[i * 3 + 2];
        elev[i] = z;
        if (z < minZ) minZ = z;
        if (z > maxZ) maxZ = z;
    }
    const span = Math.max(0.08, maxZ - minZ);
    return {
        grid,
        radius: Number(payload.radius_km) || 20,
        elev,
        slopes,
        colors,
        minZ,
        maxZ,
        span,
        center: payload.center || null,
        terrain: payload.terrain || {},
        source: "LOLA LDEM"
    };
}
function sampleLolaHeight(field, x, z) {
    if (!field) return habCraterHeight(x, z);
    const u = (x / 2 + 0.5) * (field.grid - 1);
    const v = (0.5 - z / 2) * (field.grid - 1);
    const x0 = Math.max(0, Math.min(field.grid - 2, Math.floor(u)));
    const y0 = Math.max(0, Math.min(field.grid - 2, Math.floor(v)));
    const tx = Math.max(0, Math.min(1, u - x0));
    const ty = Math.max(0, Math.min(1, v - y0));
    const at = (ix, iy) => field.elev[iy * field.grid + ix];
    const h00 = at(x0, y0);
    const h10 = at(x0 + 1, y0);
    const h01 = at(x0, y0 + 1);
    const h11 = at(x0 + 1, y0 + 1);
    const h = h00 * (1 - tx) * (1 - ty) + h10 * tx * (1 - ty) + h01 * (1 - tx) * ty + h11 * tx * ty;
    return ((h - field.minZ) / field.span) * 0.95 - 0.42;
}
function siteSurfaceHeight(x, z) {
    return sampleLolaHeight(lolaHeightField, x, z);
}
function lolaAlbedoTexture(field) {
    const size = Math.min(512, Math.max(128, field.grid * 4));
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d", {willReadFrequently: true});
    const image = context.createImageData(size, size);
    const data = image.data;
    for (let y = 0; y < size; y += 1) {
        for (let x = 0; x < size; x += 1) {
            const wx = (x / (size - 1)) * 2 - 1;
            const wz = 1 - (y / (size - 1)) * 2;
            const h = siteSurfaceHeight(wx, wz);
            const dx = siteSurfaceHeight(wx + 0.01, wz) - siteSurfaceHeight(wx - 0.01, wz);
            const dz = siteSurfaceHeight(wx, wz + 0.01) - siteSurfaceHeight(wx, wz - 0.01);
            let shade = 118 + (-dx + dz) * 90;
            shade += (habFbm(wx * 4.2 + 2, wz * 4.2 + 1, 3) - 0.4) * 28;
            if (h < -0.25) shade -= 18;
            if (h > 0.2) shade += 16;
            shade = Math.max(36, Math.min(220, shade));
            const i = (y * size + x) * 4;
            data[i] = shade * 1.04;
            data[i + 1] = shade * 0.98;
            data[i + 2] = shade * 0.9;
            data[i + 3] = 255;
            if (field.colors && field.colors.length === field.elev.length * 3) {
                const gx = Math.max(0, Math.min(field.grid - 1, Math.round((x / (size - 1)) * (field.grid - 1))));
                const gy = Math.max(0, Math.min(field.grid - 1, Math.round((y / (size - 1)) * (field.grid - 1))));
                const ci = (gy * field.grid + gx) * 3;
                data[i] = Math.round(field.colors[ci] * 255 * 0.72 + shade * 0.28);
                data[i + 1] = Math.round(field.colors[ci + 1] * 255 * 0.72 + shade * 0.26);
                data[i + 2] = Math.round(field.colors[ci + 2] * 255 * 0.72 + shade * 0.22);
            }
        }
    }
    context.putImageData(image, 0, 0);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    return tex;
}
function lolaTerrainGeometry(segments) {
    const span = 8;
    const geo = new THREE.PlaneGeometry(span, span, segments, segments);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i += 1) {
        const x = pos.getX(i);
        const z = pos.getZ(i);
        pos.setY(i, siteSurfaceHeight(x / (span * 0.5), z / (span * 0.5)));
    }
    geo.computeVertexNormals();
    return geo;
}
function syncCraterTerrainViews(payload) {
    lolaHeightField = buildLolaHeightField(payload);
    if (habCraterView && habCraterView.applyTerrain) habCraterView.applyTerrain(lolaHeightField);
    if (descentThreeView && descentThreeView.applyTerrain) descentThreeView.applyTerrain(lolaHeightField);
    if (habRimView && habRimView.applyTerrain) habRimView.applyTerrain(lolaHeightField);
}
function habHash(ix, iz) {
    let n = Math.imul(ix | 0, 374761393) + Math.imul(iz | 0, 668265263);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
}
function habNoise(x, z) {
    const ix = Math.floor(x);
    const iz = Math.floor(z);
    const fx = x - ix;
    const fz = z - iz;
    const ux = fx * fx * (3 - 2 * fx);
    const uz = fz * fz * (3 - 2 * fz);
    const a = habHash(ix, iz);
    const b = habHash(ix + 1, iz);
    const c = habHash(ix, iz + 1);
    const d = habHash(ix + 1, iz + 1);
    return a + (b - a) * ux + (c - a) * uz + (a - b - c + d) * ux * uz;
}
function habFbm(x, z, octaves) {
    let v = 0;
    let a = 0.5;
    let f = 1;
    const count = octaves || 5;
    for (let i = 0; i < count; i += 1) {
        v += a * habNoise(x * f, z * f);
        f *= 2.03;
        a *= 0.5;
    }
    return v;
}
function habDent(x, z, cx, cz, rad, depth) {
    const d = Math.hypot(x - cx, z - cz);
    return Math.exp(-((d - rad) * (d - rad)) / (rad * rad * 0.18)) * depth * 0.7 - Math.exp(-(d * d) / (rad * rad * 0.45)) * depth;
}
function habCraterHeight(x, z) {
    const r = Math.hypot(x, z);
    const rim = Math.exp(-((r - 0.48) * (r - 0.48)) / 0.011) * 0.4;
    const bowl = -Math.exp(-(r * r) / 0.09) * 0.72;
    const peak = Math.exp(-(r * r) / 0.004) * 0.24;
    const ang = Math.atan2(z, x);
    const scallop = Math.exp(-((r - 0.48) * (r - 0.48)) / 0.008) * (0.06 * Math.sin(ang * 5 + 0.7) + 0.03 * Math.sin(ang * 11 + 1.4));
    const terrace = Math.sin(r * 42) * Math.exp(-((r - 0.3) * (r - 0.3)) / 0.018) * 0.014;
    let h = bowl + rim + peak + scallop + terrace;
    h += (habFbm(x * 3.2 + 2.2, z * 3.2 + 8.4) - 0.35) * (0.05 + r * 0.055);
    h += (habFbm(x * 12 + 1.4, z * 12 + 4.2, 3) - 0.4) * 0.02;
    h += habDent(x, z, 0.68, -0.22, 0.1, 0.065);
    h += habDent(x, z, -0.58, 0.46, 0.08, 0.048);
    h += habDent(x, z, 0.22, 0.72, 0.055, 0.032);
    h += habDent(x, z, -0.78, -0.32, 0.07, 0.038);
    h += habDent(x, z, -0.16, -0.72, 0.05, 0.026);
    return h;
}
function habViewHeight(x, z) {
    if (lolaHeightField) return siteSurfaceHeight(x * 0.92, z * 0.92);
    return habCraterHeight(x * 0.72, z * 0.72) * 0.5;
}
let habAlbedo = null;
function habAlbedoTexture() {
    if (habAlbedo) return habAlbedo;
    const size = 768;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d", {willReadFrequently: true});
    const image = context.createImageData(size, size);
    const data = image.data;
    for (let y = 0; y < size; y += 1) {
        const v = y / (size - 1);
        for (let x = 0; x < size; x += 1) {
            const u = x / (size - 1);
            const px = u * 2 - 1;
            const pz = v * 2 - 1;
            const r = Math.hypot(px, pz);
            let shade = 126 + (habFbm(u * 5.2 + 3, v * 5.2 + 1, 3) - 0.42) * 46;
            shade += (habHash(x, y) - 0.5) * 18;
            const ang = Math.atan2(pz, px);
            shade += Math.pow(Math.max(0, Math.cos(ang * 6 + 0.5)), 16) * 28 * Math.exp(-r * 1.25);
            shade += Math.exp(-((r - 0.48) * (r - 0.48)) / 0.012) * 18;
            if (habHash(x * 3 + 11, y * 5 + 2) > 0.992) shade += 55;
            if (habHash(x * 9 + 4, y * 2 + 7) > 0.996) shade -= 32;
            shade = Math.max(38, Math.min(220, shade));
            const i = (y * size + x) * 4;
            data[i] = shade * 1.05;
            data[i + 1] = shade * 0.99;
            data[i + 2] = shade * 0.91;
            data[i + 3] = 255;
        }
    }
    context.putImageData(image, 0, 0);
    habAlbedo = new THREE.CanvasTexture(canvas);
    habAlbedo.colorSpace = THREE.SRGBColorSpace;
    habAlbedo.anisotropy = 8;
    return habAlbedo;
}
function habTerrainGeometry(segments) {
    const span = 8;
    const geo = new THREE.PlaneGeometry(span, span, segments, segments);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i += 1) pos.setY(i, habViewHeight(pos.getX(i), pos.getZ(i)));
    geo.computeVertexNormals();
    return geo;
}
function habGridMaterial() {
    return new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
        vertexShader: "varying vec3 vPos; void main(){ vec3 lifted = position + normal * 0.016; vPos = lifted; gl_Position = projectionMatrix * modelViewMatrix * vec4(lifted, 1.0); }",
        fragmentShader: "varying vec3 vPos; void main(){ float line = min(abs(fract(vPos.x * 3.4) - 0.5), abs(fract(vPos.z * 3.4) - 0.5)); float grid = 1.0 - smoothstep(fwidth(line) * 0.65, fwidth(line) * 2.1, line); float r = length(vPos.xz); float rf = abs(fract(r * 5.5) - 0.5); float rings = (1.0 - smoothstep(fwidth(rf) * 0.5, fwidth(rf) * 1.9, rf)) * step(r, 0.78); float ang = atan(vPos.z, vPos.x) / 6.2831853 + 0.5; float sp = abs(fract(ang * 16.0) - 0.5); float spokes = (1.0 - smoothstep(fwidth(sp) * 0.4, fwidth(sp) * 1.7, sp)) * step(r, 0.78) * step(0.04, r); float alpha = max(grid * 0.14, max(rings * 0.34, spokes * 0.18)) * smoothstep(2.4, 0.05, r); if (alpha < 0.035) discard; gl_FragColor = vec4(0.2, 0.62, 0.72, alpha); }"
    });
}
function habGlowSprite() {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const context = canvas.getContext("2d");
    const glow = context.createRadialGradient(64, 64, 0, 64, 64, 64);
    glow.addColorStop(0, "rgba(235,255,255,1)");
    glow.addColorStop(0.22, "rgba(80,225,255,.75)");
    glow.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = glow;
    context.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(canvas);
}
function habFitRenderer(renderer, camera, canvas) {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    if (canvas.width !== Math.round(width * renderer.getPixelRatio()) || canvas.height !== Math.round(height * renderer.getPixelRatio())) {
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
    }
}

function darkMaterial() {
    return new THREE.MeshStandardMaterial({color:0x1b2b35,roughness:0.72,metalness:0.12});
}
function matWhite() { return new THREE.MeshStandardMaterial({color:0xdde8ed,roughness:0.58,metalness:0.22}); }
function matBlue() { return new THREE.MeshStandardMaterial({color:0x287a9c,roughness:0.42,metalness:0.24}); }
function matGold() { return new THREE.MeshStandardMaterial({color:0xd2a85c,roughness:0.62,metalness:0.18}); }
function matOrange() { return new THREE.MeshStandardMaterial({color:0xe08a3a,roughness:0.55,metalness:0.2}); }
function matSteel() { return new THREE.MeshStandardMaterial({color:0x9aa7b0,roughness:0.4,metalness:0.55}); }
function matDark() { return darkMaterial(); }
function matRegolith() { return new THREE.MeshStandardMaterial({color:0x6b5a45,roughness:0.95,metalness:0.02}); }
function matGreen() { return new THREE.MeshStandardMaterial({color:0x3d8f6e,roughness:0.5,metalness:0.18}); }

function buildModuleHabitat() {
    const g = new THREE.Group(); g.name = "habitat";
    const white = matWhite(); const gold = matGold();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.13,0.13,0.48,24), white);
    body.rotation.z = Math.PI / 2; body.position.set(0,0.19,0); g.add(body);
    [-0.24,0.24].forEach(x => {
        const cap = new THREE.Mesh(new THREE.SphereGeometry(0.13,16,12), white);
        cap.scale.set(0.28,1,1); cap.position.set(x,0.19,0); g.add(cap);
    });
    for (let i = 0; i < 4; i += 1) {
        const port = new THREE.Mesh(new THREE.TorusGeometry(0.045,0.008,8,20), gold);
        port.rotation.y = Math.PI / 2; port.position.set(-0.26 + i * 0.17, 0.19, 0.132); g.add(port);
    }
    const cupola = new THREE.Mesh(new THREE.SphereGeometry(0.055,14,10), matBlue());
    cupola.position.set(0.05,0.33,0); g.add(cupola);
    return g;
}
function buildModuleLab() {
    const g = new THREE.Group(); g.name = "lab";
    const white = matWhite();
    const lab = new THREE.Mesh(new THREE.CylinderGeometry(0.09,0.09,0.36,18), white);
    lab.rotation.z = Math.PI / 2; lab.position.set(0,0.15,0); g.add(lab);
    const node = new THREE.Mesh(new THREE.BoxGeometry(0.12,0.12,0.12), matSteel());
    node.position.set(0.22,0.15,0); g.add(node);
    const rack = new THREE.Mesh(new THREE.BoxGeometry(0.18,0.08,0.06), matBlue());
    rack.position.set(0,0.22,0.08); g.add(rack);
    return g;
}
function buildModuleAirlock() {
    const g = new THREE.Group(); g.name = "airlock";
    const tunnel = new THREE.Mesh(new THREE.CylinderGeometry(0.07,0.07,0.18,14), matGold());
    tunnel.rotation.z = Math.PI / 2; tunnel.position.set(0,0.15,0); g.add(tunnel);
    const hatch = new THREE.Mesh(new THREE.CylinderGeometry(0.075,0.075,0.03,14), matSteel());
    hatch.rotation.z = Math.PI / 2; hatch.position.set(-0.1,0.15,0); g.add(hatch);
    return g;
}
function buildModuleArray() {
    const g = new THREE.Group(); g.name = "array";
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.012,0.018,0.42,10), matSteel());
    mast.position.y = 0.22; g.add(mast);
    [-0.2,0.2].forEach((x, idx) => {
        const panel = new THREE.Mesh(new THREE.BoxGeometry(0.36,0.012,0.28), matBlue());
        panel.position.set(x,0.38,0); panel.rotation.z = idx ? 0.18 : -0.18; panel.rotation.x = -0.25; g.add(panel);
        for (let i = 0; i < 4; i += 1) {
            const cell = new THREE.Mesh(new THREE.BoxGeometry(0.008,0.004,0.28), matWhite());
            cell.position.set(x - 0.12 + i * 0.08, 0.388, 0); cell.rotation.copy(panel.rotation); g.add(cell);
        }
    });
    return g;
}
function buildModuleRadiator() {
    const g = new THREE.Group(); g.name = "radiator";
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.01,0.01,0.2,8), matSteel());
    post.position.y = 0.1; g.add(post);
    for (let i = 0; i < 5; i += 1) {
        const fin = new THREE.Mesh(new THREE.BoxGeometry(0.28,0.006,0.08), matWhite());
        fin.position.set(0, 0.12 + i * 0.03, 0); fin.rotation.y = 0.2; g.add(fin);
    }
    return g;
}
function buildModuleRover() {
    const g = new THREE.Group(); g.name = "rover";
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.22,0.08,0.14), matGold());
    body.position.set(0,0.09,0); g.add(body);
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(0.1,0.06,0.12), matWhite());
    cabin.position.set(-0.02,0.15,0); g.add(cabin);
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.008,0.008,0.16,8), matSteel());
    mast.position.set(0.06,0.2,0); g.add(mast);
    const cam = new THREE.Mesh(new THREE.BoxGeometry(0.04,0.03,0.03), matDark());
    cam.position.set(0.06,0.28,0); g.add(cam);
    for (const x of [-0.08,0.08]) for (const z of [-0.08,0.08]) {
        const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.045,0.045,0.03,14), matDark());
        wheel.rotation.z = Math.PI / 2; wheel.position.set(x,0.045,z); g.add(wheel);
        const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.018,0.018,0.034,10), matSteel());
        hub.rotation.z = Math.PI / 2; hub.position.copy(wheel.position); g.add(hub);
    }
    return g;
}
function buildModuleTanks() {
    const g = new THREE.Group(); g.name = "tanks";
    [-0.1,0.1].forEach(x => {
        const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.06,0.06,0.22,16), matOrange());
        tank.position.set(x,0.12,0); g.add(tank);
        const cap = new THREE.Mesh(new THREE.SphereGeometry(0.06,12,8), matOrange());
        cap.position.set(x,0.23,0); g.add(cap);
    });
    const rack = new THREE.Mesh(new THREE.BoxGeometry(0.28,0.02,0.14), matSteel());
    rack.position.y = 0.02; g.add(rack);
    return g;
}
function buildModuleComms() {
    const g = new THREE.Group(); g.name = "comms";
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.012,0.02,0.5,10), matSteel());
    mast.position.y = 0.26; g.add(mast);
    const dish = new THREE.Mesh(new THREE.SphereGeometry(0.1,16,12,0,Math.PI*2,0,Math.PI/2), matWhite());
    dish.scale.set(1,0.35,1); dish.position.set(0,0.5,0.02); dish.rotation.x = -0.6; g.add(dish);
    const feed = new THREE.Mesh(new THREE.CylinderGeometry(0.008,0.008,0.08,8), matGold());
    feed.position.set(0,0.46,0.06); g.add(feed);
    return g;
}
function buildModuleBerm() {
    const g = new THREE.Group(); g.name = "berm";
    const berm = new THREE.Mesh(new THREE.TorusGeometry(0.34,0.07,10,28,Math.PI*1.2), matRegolith());
    berm.rotation.x = -Math.PI / 2; berm.position.set(0,0.04,0); g.add(berm);
    return g;
}
function buildModuleIsru() {
    const g = new THREE.Group(); g.name = "isru";
    const unit = new THREE.Mesh(new THREE.BoxGeometry(0.18,0.14,0.16), matGreen());
    unit.position.y = 0.09; g.add(unit);
    const hopper = new THREE.Mesh(new THREE.ConeGeometry(0.07,0.12,10), matSteel());
    hopper.position.set(0,0.22,0); g.add(hopper);
    const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.015,0.015,0.2,8), matGold());
    pipe.rotation.z = Math.PI / 2; pipe.position.set(0.14,0.1,0); g.add(pipe);
    return g;
}
function buildModulePad() {
    const g = new THREE.Group(); g.name = "pad";
    const deck = new THREE.Mesh(new THREE.CylinderGeometry(0.28,0.3,0.03,24), matDark());
    deck.position.y = 0.02; g.add(deck);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.26,0.008,6,40), matOrange());
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.04; g.add(ring);
    for (let i = 0; i < 4; i += 1) {
        const mark = new THREE.Mesh(new THREE.BoxGeometry(0.04,0.004,0.18), matOrange());
        const a = i * Math.PI / 2;
        mark.position.set(Math.cos(a)*0.12, 0.04, Math.sin(a)*0.12);
        mark.rotation.y = a; g.add(mark);
    }
    return g;
}
function buildModulePower() {
    const g = new THREE.Group(); g.name = "power";
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.14,0.1,0.12), matSteel());
    box.position.y = 0.07; g.add(box);
    const vent = new THREE.Mesh(new THREE.BoxGeometry(0.12,0.02,0.04), matBlue());
    vent.position.set(0,0.13,0); g.add(vent);
    return g;
}
function buildModuleEva() {
    const g = new THREE.Group(); g.name = "eva";
    const locker = new THREE.Mesh(new THREE.BoxGeometry(0.1,0.18,0.08), matWhite());
    locker.position.y = 0.1; g.add(locker);
    const door = new THREE.Mesh(new THREE.BoxGeometry(0.02,0.14,0.06), matGold());
    door.position.set(0.06,0.1,0); g.add(door);
    return g;
}

const HAB_MODULE_BUILDERS = {
    habitat: buildModuleHabitat,
    lab: buildModuleLab,
    airlock: buildModuleAirlock,
    array: buildModuleArray,
    radiator: buildModuleRadiator,
    rover: buildModuleRover,
    tanks: buildModuleTanks,
    comms: buildModuleComms,
    berm: buildModuleBerm,
    isru: buildModuleIsru,
    pad: buildModulePad,
    power: buildModulePower,
    eva: buildModuleEva
};

const HAB_COMPONENT_DEFS = [
    {id:"habitat", name:"Habitat", detail:"Pressurized cylinder", kit:true},
    {id:"lab", name:"Lab", detail:"Science node", kit:true},
    {id:"airlock", name:"Airlock", detail:"Dust lock", kit:false, defaultOn:true},
    {id:"array", name:"Solar mast", detail:"Power arrays", kit:true},
    {id:"radiator", name:"Radiators", detail:"Heat rejection", kit:false, defaultOn:true},
    {id:"rover", name:"Rover", detail:"Surface mobility", kit:true},
    {id:"tanks", name:"Tank farm", detail:"Water / propellant", kit:false, defaultOn:true},
    {id:"comms", name:"Comms mast", detail:"Earth / relay dish", kit:false, defaultOn:true},
    {id:"berm", name:"Regolith berm", detail:"Radiation shelter mass", kit:false, defaultOn:false},
    {id:"isru", name:"ISRU unit", detail:"Ice / O2 plant", kit:false, defaultOn:false},
    {id:"pad", name:"Landing pad", detail:"20 m pad marker", kit:false, defaultOn:true},
    {id:"power", name:"Power node", detail:"Battery / PCU", kit:false, defaultOn:true},
    {id:"eva", name:"EVA locker", detail:"Suit / tool cache", kit:false, defaultOn:false}
];

const habBaseOffsets = {
    habitat: {x:0, z:0},
    lab: {x:0.48, z:0.04},
    airlock: {x:-0.34, z:0},
    array: {x:0.05, z:0.55},
    radiator: {x:-0.45, z:0.35},
    rover: {x:0.32, z:-0.42},
    tanks: {x:0.55, z:-0.25},
    comms: {x:-0.55, z:-0.2},
    berm: {x:0, z:0},
    isru: {x:0.7, z:0.2},
    pad: {x:1.35, z:0.1},
    power: {x:0.2, z:0.28},
    eva: {x:-0.2, z:-0.28}
};

function activeHabComponents() {
    const pressed = [];
    document.querySelectorAll("#hab-comp-grid [data-hab-comp]").forEach(btn => {
        if (btn.getAttribute("aria-pressed") === "true") pressed.push(btn.dataset.habComp);
    });
    if (!pressed.length) {
        const kit = typeof baseKit === "function" ? baseKit() : ["habitat"];
        return HAB_COMPONENT_DEFS.filter(def => {
            if (def.id === "habitat") return true;
            if (def.kit) return kit.indexOf(def.id) >= 0;
            return Boolean(def.defaultOn);
        }).map(def => def.id);
    }
    if (pressed.indexOf("habitat") < 0) pressed.unshift("habitat");
    return pressed;
}

function syncHabComponentGrid() {
    const grid = document.getElementById("hab-comp-grid");
    if (!grid) return;
    if (!grid.childElementCount) {
        const kit = typeof baseKit === "function" ? baseKit() : ["habitat"];
        HAB_COMPONENT_DEFS.forEach(def => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.dataset.habComp = def.id;
            const on = def.id === "habitat" || (def.kit ? kit.indexOf(def.id) >= 0 : Boolean(def.defaultOn));
            btn.setAttribute("aria-pressed", String(on));
            if (def.id === "habitat") btn.disabled = true;
            btn.innerHTML = def.name + "<small>" + def.detail + "</small>";
            btn.addEventListener("click", () => {
                if (def.id === "habitat") return;
                const next = btn.getAttribute("aria-pressed") !== "true";
                btn.setAttribute("aria-pressed", String(next));
                if (def.kit) {
                    const kitBtn = document.querySelector('#base-kit [data-kit="' + def.id + '"]');
                    if (kitBtn) kitBtn.setAttribute("aria-pressed", String(next));
                }
                if (habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
                if (typeof paintHabitat === "function") paintHabitat();
                if (typeof updateYardVisibility === "function") updateYardVisibility();
            });
            grid.appendChild(btn);
        });
    } else {
        const kit = typeof baseKit === "function" ? baseKit() : ["habitat"];
        grid.querySelectorAll("[data-hab-comp]").forEach(btn => {
            const def = HAB_COMPONENT_DEFS.find(item => item.id === btn.dataset.habComp);
            if (!def || !def.kit || def.id === "habitat") return;
            btn.setAttribute("aria-pressed", String(kit.indexOf(def.id) >= 0));
        });
    }
}

function computeBaseEndurance(facts) {
    const kit = activeHabComponents();
    const batteryH = Number(facts.batteryH);
    const nightDays = Number(facts.night);
    const peakW = Number(facts.peakW);
    const hotel = 80 + kit.length * 18 + (kit.indexOf("lab") >= 0 ? 40 : 0) + (kit.indexOf("isru") >= 0 ? 90 : 0);
    const dayLoad = hotel + (kit.indexOf("rover") >= 0 ? 60 : 0) + (kit.indexOf("comms") >= 0 ? 25 : 0);
    const arrayW = Number.isFinite(peakW) && peakW > 0 ? peakW : Math.max(200, kit.filter(id => id === "array").length * 900 + 400);
    const powerMargin = arrayW - dayLoad;
    const nightHoursNeeded = Number.isFinite(nightDays) ? nightDays * 24 : 14 * 24;
    const batt = Number.isFinite(batteryH) && batteryH > 0 ? batteryH : 18;
    const nightSurviveH = batt * (hotel > 0 ? (arrayW * 0.15 + 120) / hotel : 1);
    const nightSurviveDays = nightSurviveH / 24;
    const nightOk = nightSurviveH >= nightHoursNeeded * 0.85;
    const stormHoldH = facts.sheltered ? Math.max(18, batt * 0.55) : Math.max(4, batt * 0.18);
    const opsDays = Math.max(2, Math.min(180, Math.round(
        (arrayW / Math.max(80, dayLoad)) * 18 + (facts.sheltered ? 12 : 0) + (kit.indexOf("tanks") >= 0 ? 8 : 0) + (kit.indexOf("berm") >= 0 ? 6 : 0)
    )));
    const lifeDays = Math.max(3, Math.round(opsDays * (kit.indexOf("tanks") >= 0 ? 1.15 : 0.85) * (kit.indexOf("isru") >= 0 ? 1.25 : 1)));
    return {
        opsDays,
        nightSurviveDays,
        nightOk,
        stormHoldH,
        powerMargin,
        dayLoad,
        arrayW,
        lifeDays,
        hotel,
        nightHoursNeeded
    };
}

function createCraterView(canvas, role) {
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#010204");
    const camera = new THREE.PerspectiveCamera(role === "descent" ? 42 : 36, 1, 0.08, 40);
    camera.position.set(0.32, role === "descent" ? 1.9 : 2.0, role === "descent" ? 2.45 : 2.7);
    camera.lookAt(0, -0.06, -0.05);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.minDistance = 1.2;
    controls.maxDistance = 5.5;
    controls.target.set(0, -0.06, -0.05);
    const geo = lolaHeightField ? lolaTerrainGeometry(200) : habTerrainGeometry(200);
    const groundMat = new THREE.MeshStandardMaterial({
        map: lolaHeightField ? lolaAlbedoTexture(lolaHeightField) : habAlbedoTexture(),
        roughness: 0.94,
        metalness: 0.02,
        envMapIntensity: 0.35
    });
    const ground = new THREE.Mesh(geo, groundMat);
    ground.castShadow = true;
    ground.receiveShadow = true;
    scene.add(ground);
    scene.add(new THREE.Mesh(geo, habGridMaterial()));
    scene.fog = new THREE.FogExp2(0x010204, 0.045);
    scene.add(new THREE.HemisphereLight(0xd7e4f2, 0x1a120c, 0.95));
    scene.add(new THREE.AmbientLight(0xa8b4c2, 0.38));
    const sun = new THREE.DirectionalLight(0xfff1df, 3.15);
    sun.position.set(-2.6, 3.8, 1.4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 0.4;
    sun.shadow.camera.far = 28;
    sun.shadow.camera.left = -7;
    sun.shadow.camera.right = 7;
    sun.shadow.camera.top = 7;
    sun.shadow.camera.bottom = -7;
    sun.shadow.bias = -0.0004;
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0xcfe4f6, 1.55);
    fill.position.set(0.8, 2.6, 1.3);
    scene.add(fill);
    const rimLight = new THREE.DirectionalLight(0x7ad7ff, 0.55);
    rimLight.position.set(1.8, 1.2, -2.2);
    scene.add(rimLight);
    const floor = habViewHeight(0, 0);
    let beamMat = null;
    if (role === "descent") {
        const lander = new THREE.Group();
        const shell = new THREE.MeshStandardMaterial({color:0xd9e1e5, roughness:0.62, metalness:0.28});
        const foil = new THREE.MeshStandardMaterial({color:0xc68a3a, roughness:0.7, metalness:0.24});
        const dark = new THREE.MeshStandardMaterial({color:0x182b38, roughness:0.48, metalness:0.32});
        const cabin = new THREE.Mesh(new THREE.CylinderGeometry(0.13,0.2,0.22,6), shell);
        cabin.position.y = 0.34;
        lander.add(cabin);
        const ascent = new THREE.Mesh(new THREE.CylinderGeometry(0.1,0.13,0.2,6), shell);
        ascent.position.y = 0.55;
        lander.add(ascent);
        const window = new THREE.Mesh(new THREE.BoxGeometry(0.13,0.08,0.018), dark);
        window.position.set(0,0.57,0.126);
        lander.add(window);
        const foilBand = new THREE.Mesh(new THREE.CylinderGeometry(0.205,0.205,0.12,6,1,true), foil);
        foilBand.position.y = 0.3;
        lander.add(foilBand);
        const legMaterial = new THREE.MeshStandardMaterial({color:0xcbd6dc, roughness:0.5, metalness:0.45});
        const up = new THREE.Vector3(0,1,0);
        [[-1,-1],[1,-1],[-1,1],[1,1]].forEach(([x,z]) => {
            const from = new THREE.Vector3(x*0.12,0.31,z*0.12);
            const to = new THREE.Vector3(x*0.29,0.04,z*0.29);
            const axis = new THREE.Vector3().subVectors(to,from);
            const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.012,0.018,axis.length(),8),legMaterial);
            leg.position.copy(from).add(to).multiplyScalar(0.5);
            leg.quaternion.setFromUnitVectors(up,axis.normalize());
            lander.add(leg);
            const foot = new THREE.Mesh(new THREE.BoxGeometry(0.12,0.018,0.09),dark);
            foot.position.copy(to);
            lander.add(foot);
        });
        const engine = new THREE.Mesh(new THREE.ConeGeometry(0.055,0.16,12),dark);
        engine.position.y = 0.16;
        engine.rotation.x = Math.PI;
        lander.add(engine);
        lander.position.y = floor;
        lander.traverse(node => { if (node.isMesh) { node.castShadow = true; node.receiveShadow = true; } });
        scene.add(lander);
        [0.52,0.88].forEach((radius,index) => {
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(radius,0.009,6,96),
                new THREE.MeshBasicMaterial({color:index ? 0xf0b15c : 0x70e8b3,transparent:true,opacity:index ? 0.82 : 0.9})
            );
            ring.rotation.x = -Math.PI / 2;
            ring.position.y = floor + 0.015;
            scene.add(ring);
        });
    } else {
        const baseRoot = new THREE.Group();
        baseRoot.name = "baseRoot";
        scene.add(baseRoot);
        const rebuildBase = () => {
            while (baseRoot.children.length) {
                const child = baseRoot.children.pop();
                child.traverse(node => {
                    if (node.geometry) node.geometry.dispose();
                });
            }
            const showModels = !(window.habViewState && window.habViewState.layers && window.habViewState.layers.models === false);
            if (!showModels) return;
            const active = activeHabComponents();
            const pad = typeof likelyPad === "function" ? likelyPad(siteFacts()) : null;
            let bx = 0.82, bz = -0.18;
            if (pad && pad.km) {
                const span = 12;
                bx = Math.max(-1.4, Math.min(1.4, pad.km.e / span));
                bz = Math.max(-1.4, Math.min(1.4, -pad.km.n / span));
            }
            const camp = new THREE.Group();
            active.forEach(id => {
                const builder = HAB_MODULE_BUILDERS[id];
                if (!builder) return;
                const module = builder();
                const off = habBaseOffsets[id] || {x:0, z:0};
                module.position.set(off.x, 0, off.z);
                camp.add(module);
            });
            camp.position.set(bx, habViewHeight(bx, bz), bz);
            camp.traverse(node => { if (node.isMesh) { node.castShadow = true; node.receiveShadow = true; } });
            baseRoot.add(camp);
            // Connector tubes between habitat and nearby modules
            const links = [["habitat","lab"],["habitat","airlock"],["habitat","power"]];
            links.forEach(([a,b]) => {
                if (active.indexOf(a) < 0 || active.indexOf(b) < 0) return;
                const oa = habBaseOffsets[a], ob = habBaseOffsets[b];
                const dx = ob.x - oa.x, dz = ob.z - oa.z;
                const len = Math.hypot(dx, dz) || 0.01;
                const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.025,0.025,len,10), matSteel());
                tube.position.set((oa.x+ob.x)/2, 0.14, (oa.z+ob.z)/2);
                tube.rotation.z = Math.PI / 2;
                tube.rotation.y = Math.atan2(dz, dx);
                camp.add(tube);
            });
        };
        rebuildBase();
        beamMat = new THREE.MeshBasicMaterial({color:0xd8ffff,transparent:true,opacity:0.95,blending:THREE.AdditiveBlending,depthWrite:false});
        const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.004,0.004,0.72,12),beamMat);
        beam.position.y = floor + 0.36;
        scene.add(beam);
        const halo = new THREE.Mesh(new THREE.CylinderGeometry(0.014,0.02,0.72,12),new THREE.MeshBasicMaterial({color:0x39e7ff,transparent:true,opacity:0.28,blending:THREE.AdditiveBlending,depthWrite:false}));
        halo.position.copy(beam.position);
        scene.add(halo);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map:habGlowSprite(),transparent:true,blending:THREE.AdditiveBlending,depthWrite:false}));
        sprite.position.set(0,floor+0.03,0);
        sprite.scale.set(0.14,0.14,0.14);
        scene.add(sprite);
        scene.userData.rebuildBase = rebuildBase;
    }
    const sweepGeo = new THREE.BufferGeometry();
    const sweepPos = new Float32Array(72 * 3);
    sweepGeo.setAttribute("position", new THREE.BufferAttribute(sweepPos, 3));
    const sweep = new THREE.Line(sweepGeo, new THREE.LineBasicMaterial({color: 0xb8fbff, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false}));
    scene.add(sweep);
    const stars = [];
    for (let i = 0; i < 240; i += 1) {
        const a = habHash(i, 3) * Math.PI * 2;
        stars.push(Math.cos(a) * 6, 0.7 + habHash(i, 8) * 2.4, -0.2 + Math.sin(a) * 2.2);
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.Float32BufferAttribute(stars, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({color: 0xe7f7ff, size: 0.012})));
    let groundMesh = ground;
    let gridMesh = scene.children.find(child => child.material && child.material.type === "ShaderMaterial");
    return {
        camera,
        controls,
        rebuildBase() {
            if (scene.userData.rebuildBase) scene.userData.rebuildBase();
        },
        resize() { habFitRenderer(renderer, camera, canvas); },
        resetView() {
            camera.position.set(0.32, role === "descent" ? 1.9 : 2.0, role === "descent" ? 2.45 : 2.7);
            controls.target.set(0, -0.06, -0.05);
            controls.update();
        },
        applyTerrain(field) {
            if (!field) return;
            const next = lolaTerrainGeometry(220);
            const map = lolaAlbedoTexture(field);
            if (groundMesh.material.map && groundMesh.material.map.dispose) groundMesh.material.map.dispose();
            groundMesh.geometry.dispose();
            groundMesh.geometry = next;
            groundMesh.material.map = map;
            groundMesh.material.needsUpdate = true;
            if (gridMesh) {
                gridMesh.geometry.dispose();
                gridMesh.geometry = next;
            }
            const badge = document.getElementById(role === "descent" ? "des-lola-badge" : "hab-scale");
            if (badge) badge.textContent = "LOLA DEM · LIVE";
        },
        render(t) {
            habFitRenderer(renderer, camera, canvas);
            controls.update();
            sun.position.x = -2.4 + Math.sin(t * 0.08) * 0.35;
            const angle = t * 0.55;
            for (let i = 0; i < 72; i += 1) {
                const radius = (i / 71) * 0.78;
                const x = Math.cos(angle) * radius;
                const z = Math.sin(angle) * radius;
                sweepPos[i * 3] = x;
                sweepPos[i * 3 + 1] = habViewHeight(x, z) + 0.012;
                sweepPos[i * 3 + 2] = z;
            }
            sweepGeo.attributes.position.needsUpdate = true;
            if (beamMat) beamMat.opacity = 0.72 + Math.sin(t * 4.2) * 0.22;
            renderer.render(scene, camera);
        }
    };
}
function habBlockGeometry(n) {
    const positions = [];
    const normals = [];
    const uvs = [];
    const colors = [];
    const indices = [];
    const top = new Float32Array((n + 1) * (n + 1));
    let minY = 10;
    const at = (i, j) => j * (n + 1) + i;
    for (let j = 0; j <= n; j += 1) {
        for (let i = 0; i <= n; i += 1) {
            const y = habCraterHeight((-1 + 2 * i / n) * 0.85, (-1 + 2 * j / n) * 0.85) * 0.42;
            top[at(i, j)] = y;
            if (y < minY) minY = y;
        }
    }
    const base = minY - 0.14;
    const push = (x, y, z, nx, ny, nz, u, v, shade) => {
        positions.push(x, y, z);
        normals.push(nx, ny, nz);
        uvs.push(u, v);
        colors.push(shade, shade * 0.98, shade * 0.94);
        return positions.length / 3 - 1;
    };
    for (let j = 0; j <= n; j += 1) {
        for (let i = 0; i <= n; i += 1) {
            const x = -1 + 2 * i / n;
            const z = -1 + 2 * j / n;
            const i0 = Math.max(0, i - 1);
            const i1 = Math.min(n, i + 1);
            const j0 = Math.max(0, j - 1);
            const j1 = Math.min(n, j + 1);
            const dx = (top[at(i1, j)] - top[at(i0, j)]) / Math.max(0.001, (i1 - i0) * 2 / n);
            const dz = (top[at(i, j1)] - top[at(i, j0)]) / Math.max(0.001, (j1 - j0) * 2 / n);
            const len = Math.hypot(-dx, 2, -dz) || 1;
            push(x, top[at(i, j)], z, -dx / len, 2 / len, -dz / len, i / n, 1 - j / n, 1);
        }
    }
    for (let j = 0; j < n; j += 1) {
        for (let i = 0; i < n; i += 1) {
            const a = at(i, j);
            indices.push(a, a + 1, a + n + 1, a + 1, a + n + 2, a + n + 1);
        }
    }
    const edges = [];
    for (let i = 0; i < n; i += 1) edges.push([i, 0, i + 1, 0]);
    for (let j = 0; j < n; j += 1) edges.push([n, j, n, j + 1]);
    for (let i = n; i > 0; i -= 1) edges.push([i, n, i - 1, n]);
    for (let j = n; j > 0; j -= 1) edges.push([0, j, 0, j - 1]);
    edges.forEach(edge => {
        const x0 = -1 + 2 * edge[0] / n;
        const z0 = -1 + 2 * edge[1] / n;
        const x1 = -1 + 2 * edge[2] / n;
        const z1 = -1 + 2 * edge[3] / n;
        const y0 = top[at(edge[0], edge[1])];
        const y1 = top[at(edge[2], edge[3])];
        const ox = x0 + x1;
        const oz = z0 + z1;
        const len = Math.hypot(ox, oz) || 1;
        const a = push(x0, y0, z0, ox / len, 0, oz / len, 0, 1, 0.72);
        const b = push(x1, y1, z1, ox / len, 0, oz / len, 1, 1, 0.72);
        const c = push(x0, base, z0, ox / len, 0, oz / len, 0, 0, 0.5);
        const d = push(x1, base, z1, ox / len, 0, oz / len, 1, 0, 0.5);
        indices.push(a, c, b, b, c, d);
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
    geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.setIndex(indices);
    return geo;
}
function habPin(x, z, color) {
    const group = new THREE.Group();
    const y = habCraterHeight(x * 0.85, z * 0.85) * 0.42;
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.1, 8), new THREE.MeshBasicMaterial({color}));
    pole.position.y = y + 0.05;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.016, 16, 12), new THREE.MeshBasicMaterial({color}));
    head.position.y = y + 0.11;
    group.add(pole, head);
    group.position.set(x, 0, z);
    return group;
}
function createRimView(canvas) {
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#05080c");
    const camera = new THREE.PerspectiveCamera(48, 1, 0.05, 30);
    camera.position.set(1.35, 1.22, 1.5);
    camera.up.set(0, 1, 0);
    camera.lookAt(0.0, 0.02, 0.0);
    const block = new THREE.Mesh(habBlockGeometry(88), new THREE.MeshStandardMaterial({
        map: habAlbedoTexture(),
        vertexColors: true,
        roughness: 0.86,
        metalness: 0.04,
        side: THREE.DoubleSide
    }));
    scene.add(block);
    scene.add(habPin(0.48, 0.32, 0xff8a1e));
    scene.add(habPin(-0.18, 0.55, 0xfff6ea));
    scene.add(habPin(0.58, -0.12, 0xffb03a));
    scene.add(new THREE.HemisphereLight(0xd5e4f2, 0x1a140f, 0.95));
    scene.add(new THREE.AmbientLight(0xb0bcc8, 0.55));
    const sun = new THREE.DirectionalLight(0xfff4e6, 2.4);
    sun.position.set(-0.6, 3.2, 0.8);
    scene.add(sun);
    let blockMesh = block;
    return {
        resize() { habFitRenderer(renderer, camera, canvas); },
        applyTerrain(field) {
            if (!field) return;
            const next = lolaTerrainGeometry(96);
            blockMesh.geometry.dispose();
            blockMesh.geometry = next;
            if (blockMesh.material.map) {
                const map = lolaAlbedoTexture(field);
                blockMesh.material.map.dispose();
                blockMesh.material.map = map;
                blockMesh.material.needsUpdate = true;
            }
        },
        render() {
            habFitRenderer(renderer, camera, canvas);
            renderer.render(scene, camera);
        }
    };
}
function drawHabAlt() {
    const fit = opsFit(document.getElementById("hab-alt"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const facts = siteFacts();
    const heights = facts.heights.length ? facts.heights : [0.2, 0.35, 0.55, 0.8, 0.62, 0.4, 0.28];
    const min = Math.min.apply(null, heights);
    const max = Math.max.apply(null, heights);
    const span = Math.max(0.001, max - min);
    const depth = Math.max(4, height * 0.12);
    const pts = heights.map((value, index) => ({
        x: 4 + (width - 10) * index / Math.max(1, heights.length - 1),
        y: 6 + (height - 14 - depth) * (1 - (value - min) / span)
    }));
    context.beginPath();
    pts.forEach((p, index) => { if (index) context.lineTo(p.x, p.y + depth); else context.moveTo(p.x, p.y + depth); });
    context.lineTo(pts[pts.length - 1].x, height - 2);
    context.lineTo(pts[0].x, height - 2);
    context.closePath();
    context.fillStyle = "rgba(4,14,20,.7)";
    context.fill();
    context.beginPath();
    pts.forEach((p, index) => { if (index) context.lineTo(p.x, p.y); else context.moveTo(p.x, p.y); });
    context.strokeStyle = "#7af4ff";
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 10;
    context.lineWidth = 2;
    context.stroke();
    context.lineTo(width - 4, height - 2 - depth);
    context.lineTo(4, height - 2 - depth);
    context.closePath();
    const wash = context.createLinearGradient(0, 0, 0, height);
    wash.addColorStop(0, "rgba(62,224,240,.5)");
    wash.addColorStop(1, "rgba(62,224,240,0)");
    context.shadowBlur = 0;
    context.globalAlpha = 0.55;
    context.fillStyle = wash;
    context.fill();
    context.globalAlpha = 1;
}
function drawHabHeat() {
    const fit = opsFit(document.getElementById("hab-heat"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const radius = Math.min(width, height) * 0.46;
    const cx = width * 0.5;
    const cy = height * 0.5;
    context.save();
    context.beginPath();
    context.arc(cx, cy, radius, 0, Math.PI * 2);
    context.clip();
    const base = context.createRadialGradient(cx, cy, radius * 0.05, cx, cy, radius);
    base.addColorStop(0, "#082f36");
    base.addColorStop(0.55, "#0c7490");
    base.addColorStop(1, "#062838");
    context.fillStyle = base;
    context.fillRect(0, 0, width, height);
    [[0.58, 2.2, 0.55, "rgba(255,58,44,.95)"], [0.62, 2.7, 0.5, "rgba(255,176,0,.9)"], [0.5, 1.7, 0.48, "rgba(255,225,74,.85)"], [0.68, 3.3, 0.52, "rgba(255,90,20,.9)"], [0.6, 3.9, 0.46, "rgba(255,140,20,.8)"], [0.46, 4.6, 0.4, "rgba(47,224,200,.7)"], [0.72, 1.4, 0.36, "rgba(255,70,40,.75)"]].forEach(blob => {
        const x = cx + Math.cos(blob[1]) * radius * blob[0];
        const y = cy + Math.sin(blob[1]) * radius * blob[0];
        const spot = context.createRadialGradient(x, y, 0, x, y, radius * blob[2]);
        spot.addColorStop(0, blob[3]);
        spot.addColorStop(1, "rgba(0,0,0,0)");
        context.fillStyle = spot;
        context.beginPath();
        context.arc(x, y, radius * blob[2], 0, Math.PI * 2);
        context.fill();
    });
    const core = context.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.34);
    core.addColorStop(0, "rgba(110,245,255,.9)");
    core.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = core;
    context.fillRect(0, 0, width, height);
    context.restore();
    context.beginPath();
    context.arc(cx, cy, radius, 0, Math.PI * 2);
    context.strokeStyle = "#8af6ff";
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 10;
    context.lineWidth = 1.5;
    context.stroke();
    context.shadowBlur = 0;
}
function drawHabScatter() {
    const fit = opsFit(document.getElementById("hab-scatter"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "#1c6f86";
    context.strokeRect(18, 6, width - 26, height - 20);
    context.fillStyle = "#8ec9d6";
    context.font = "600 10px Rajdhani, Segoe UI, sans-serif";
    context.fillText("Cold", 1, height * 0.45);
    context.fillText("Warm", width * 0.42, height - 2);
    for (let i = 0; i < 72; i += 1) {
        const t = habHash(i, 21);
        const j = habHash(i, 44);
        context.fillStyle = j > 0.55 ? "#7ee7ff" : "#2f7dff";
        context.fillRect(20 + (width - 32) * (0.08 + t * 0.82), 8 + (height - 30) * (0.82 - t * 0.68 + (j - 0.5) * 0.25), 2.4, 2.4);
    }
}
function drawHabNet() {
    const fit = opsFit(document.getElementById("hab-net"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const layers = [[0.16, 0.38, 0.6, 0.82], [0.1, 0.28, 0.46, 0.64, 0.84], [0.26, 0.5, 0.74]];
    const xs = [width * 0.16, width * 0.5, width * 0.84];
    const nodes = layers.map((layer, index) => layer.map(t => ({x: xs[index], y: 6 + (height - 12) * t})));
    context.lineWidth = 1;
    context.strokeStyle = "rgba(100, 214, 232, .6)";
    nodes.forEach((layer, index) => {
        if (!nodes[index + 1]) return;
        layer.forEach(from => nodes[index + 1].forEach(to => {
            context.beginPath();
            context.moveTo(from.x, from.y);
            context.lineTo(to.x, to.y);
            context.stroke();
        }));
    });
    nodes.forEach(layer => layer.forEach(node => {
        context.beginPath();
        context.arc(node.x, node.y, 4.2, 0, Math.PI * 2);
        context.fillStyle = "#071820";
        context.fill();
        context.strokeStyle = "#7af4ff";
        context.shadowColor = "#3ee0f0";
        context.shadowBlur = 8;
        context.stroke();
        context.shadowBlur = 0;
    }));
}
function drawHabTemp() {
    const fit = opsFit(document.getElementById("hab-temp"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const temperature = latestEnvironment && latestEnvironment.temperature;
    const night = temperature && temperature.night_low_c != null ? Number(temperature.night_low_c) : -170;
    const day = temperature && temperature.day_high_c != null ? Number(temperature.day_high_c) : 110;
    const temps = [];
    for (let index = 0; index < 16; index += 1) {
        const phase = index / 15;
        const sun = Math.max(0, Math.sin((phase - 0.15) * Math.PI));
        temps.push(night + (day - night) * Math.pow(sun, 0.65));
    }
    const min = Math.min(night, day) - 12;
    const max = Math.max(night, day) + 12;
    const left = 42;
    const top = 16;
    const plotW = width - left - 6;
    const plotH = height - 26;
    context.font = "600 11px Rajdhani, Segoe UI, sans-serif";
    context.fillStyle = "#d7f4ff";
    context.fillText("One lunar day (°C)", left, 12);
    context.font = "600 10px Rajdhani, Segoe UI, sans-serif";
    [max, (max + min) / 2, min].forEach(mark => {
        const y = top + plotH * (1 - (mark - min) / (max - min));
        context.strokeStyle = "#143848";
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillStyle = "#8ec9d6";
        context.textAlign = "right";
        context.fillText(Math.round(mark) + "°", left - 3, y + 3);
    });
    context.beginPath();
    temps.forEach((temp, index) => {
        const x = left + plotW * index / (temps.length - 1);
        const y = top + plotH * (1 - (temp - min) / (max - min));
        if (index) context.lineTo(x, y);
        else context.moveTo(x, y);
    });
    context.strokeStyle = "#7af4ff";
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 8;
    context.lineWidth = 1.7;
    context.stroke();
    context.shadowBlur = 0;
    context.textAlign = "left";
}
function drawHabNetwork() {
    const fit = opsFit(document.getElementById("hab-network"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const nodes = [[0.16, 0.32], [0.3, 0.68], [0.46, 0.26], [0.52, 0.74], [0.68, 0.42], [0.84, 0.2], [0.8, 0.76], [0.38, 0.48], [0.6, 0.55]].map(pair => [pair[0] * width, pair[1] * height]);
    [[0, 2], [0, 7], [1, 7], [2, 4], [2, 8], [3, 8], [4, 5], [4, 6], [7, 3], [8, 4]].forEach(link => {
        context.beginPath();
        context.moveTo(nodes[link[0]][0], nodes[link[0]][1]);
        context.lineTo(nodes[link[1]][0], nodes[link[1]][1]);
        context.strokeStyle = "rgba(130, 226, 244, .75)";
        context.stroke();
    });
    nodes.forEach(node => {
        context.beginPath();
        context.arc(node[0], node[1], 3.1, 0, Math.PI * 2);
        context.fillStyle = "#7af4ff";
        context.shadowColor = "#3ee0f0";
        context.shadowBlur = 8;
        context.fill();
    });
    context.shadowBlur = 0;
}
function drawHabWave(t) {
    const canvas = document.getElementById("hab-wave");
    const fit = canvas ? opsFit(canvas) : null;
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    context.beginPath();
    for (let x = 0; x <= width; x += 2) {
        const y = height * 0.55 + Math.sin(x * 0.075 + t * 2.4) * (height * 0.22) + Math.sin(x * 0.19 + t) * (height * 0.08);
        if (x) context.lineTo(x, y);
        else context.moveTo(0, y);
    }
    context.strokeStyle = "#7af4ff";
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 6;
    context.lineWidth = 1.2;
    context.stroke();
    context.shadowBlur = 0;
}
let habCraterView = null;
let habRimView = null;
let descentThreeView = null;
let habAnim = 0;
const habBoot = Date.now();
function tickHabitat(now) {
    const board = document.getElementById("hab-board");
    if (!board || board.hidden) {
        habAnim = 0;
        return;
    }
    habAnim = requestAnimationFrame(tickHabitat);
    const t = now * 0.001;
    if (habCraterView) habCraterView.render(t);
    if (habRimView) habRimView.render(t);
    drawHabWave(t);
}
function paintHabitat() {
    const board = document.getElementById("hab-board");
    if (!board || board.hidden) return;
    syncHabComponentGrid();
    drawHabAlt();
    drawHabHeat();
    drawHabScatter();
    drawHabNet();
    drawHabTemp();
    drawHabNetwork();
    drawHabClimb();
    drawHabSite();
    updateHabitatReadout();
}
function optionLine() {
    const state = briefingState();
    const place = document.getElementById("plan-destination").selectedOptions[0].dataset.name;
    const who = state.asset === "both" ? "crew and habitat" : state.asset === "crew" ? "crew" : "habitat";
    const shelter = state.sheltered === "yes" ? "shelter on" : "no shelter";
    const watch = state.priority === "sun" ? "sunlight first" : state.priority === "radio" ? "Earth radio first" : "slope first";
    const speed = Number(document.getElementById("planning_speed_kmh").value) || 0.5;
    return place + " · " + who + " · " + shelter + " · climb " + state.slope + "° · " + watch + " · " + speed.toFixed(1) + " km/h";
}
function siteFacts() {
    const site = document.getElementById("plan-destination");
    const pair = site.value.split(",").map(Number);
    const cleared = Boolean(opsTerrain && opsTerrain.route_available);
    const km = opsTerrain ? (cleared ? opsTerrain.route_distance_km : opsTerrain.advisory_distance_km) : null;
    const slopes = ((opsTerrain ? (cleared ? opsTerrain.route_slope_degrees : opsTerrain.advisory_route_slope_degrees) : []) || []).map(Number).filter(Number.isFinite);
    const heights = ((opsTerrain ? (cleared ? opsTerrain.route_elevation_km : opsTerrain.advisory_route_elevation_km) : []) || []).map(Number).filter(Number.isFinite);
    const limit = Number(document.getElementById("max_slope_degrees").value) || 18;
    const telemetry = opsPlan && opsPlan.telemetry ? opsPlan.telemetry : {};
    const power = opsPlan && opsPlan.power ? opsPlan.power : {};
    const goes = (document.getElementById("solar-current").textContent || "").trim();
    const scan = (opsTerrain && opsTerrain.area_scan) || [];
    const elevs = scan.map(cell => Number(cell.elev_km)).filter(Number.isFinite).sort((a, b) => a - b);
    const cut = elevs.length ? elevs[Math.floor(elevs.length * 0.3)] : null;
    const floor = cut == null ? [] : scan.filter(cell => Number(cell.elev_km) <= cut);
    let good = 0;
    let near = 0;
    let bad = 0;
    slopes.forEach(slope => {
        if (slope >= limit) bad += 1;
        else if (slope >= limit - 3) near += 1;
        else good += 1;
    });
    return {
        place: site.selectedOptions[0].dataset.name,
        pair, cleared, km, slopes, heights, limit,
        maxSlope: slopes.length ? Math.max.apply(null, slopes) : null,
        minH: heights.length ? Math.min.apply(null, heights) : null,
        maxH: heights.length ? Math.max.apply(null, heights) : null,
        good, near, bad,
        earth: telemetry.min_earth_elevation_degrees,
        batteryH: telemetry.battery_hours,
        peakW: power.peak_tilt_w,
        night: power.night_days,
        goes,
        storm: /^(M|X)/.test(goes),
        sheltered: document.getElementById("brief-shelter").value === "yes",
        floorCount: floor.length,
        floorTough: floor.filter(cell => Number(cell.slope) >= limit).length
    };
}
function siteProsCons() {
    const facts = siteFacts();
    const pros = [];
    const cons = [];
    const lat = Math.abs(facts.pair[0]);
    if (lat >= 80) pros.push("Polar latitude. A ridge can hold sunlight, and the floor is the water case.");
    else cons.push("This latitude is a weak water case. A polar floor is the ice target.");
    if (facts.cleared && facts.bad === 0) pros.push("The walk stays under the " + facts.limit + "° climb limit" + (facts.km != null ? " for " + Number(facts.km).toFixed(1) + " km." : "."));
    else if (facts.km == null) cons.push("The path has not loaded yet. Apply Options to score the walk.");
    else cons.push("The walk is not cleared. " + facts.bad + " steps are at or over " + facts.limit + "°.");
    if (facts.near) cons.push(facts.near + " steps sit within 3° of the climb limit. Leave margin.");
    if (facts.earth != null && facts.earth >= 5) pros.push("Earth stays " + Number(facts.earth).toFixed(1) + "° up, so radio can hold.");
    else if (facts.earth != null) cons.push("Earth drops to " + Number(facts.earth).toFixed(1) + "°. The rim can hide the radio.");
    if (facts.peakW != null && facts.peakW >= 800) pros.push("The tilted array peaks near " + Math.round(facts.peakW) + " W.");
    else if (facts.peakW != null) cons.push("Array peak is " + Math.round(facts.peakW) + " W for this load.");
    if (facts.night != null && Number(facts.night) > 5) cons.push("Night lasts about " + facts.night + " days. The battery has to cover it.");
    else if (facts.night != null) pros.push("Night is about " + facts.night + " days.");
    if (facts.sheltered) pros.push("A shelter mass is recorded for an M or X flare.");
    else cons.push("No shelter mass. An M or X flare means hold.");
    if (facts.storm) cons.push("GOES is " + facts.goes + ". Storm watch is on.");
    else if (facts.goes && facts.goes !== "Loading…") pros.push("Latest GOES reading is " + facts.goes + ".");
    if (facts.floorTough) cons.push(facts.floorTough + " of " + facts.floorCount + " low-floor samples are over the climb limit. That middle ground is the tough part.");
    else if (facts.floorCount) pros.push("The low-floor samples in this window stay under the climb limit.");
    if (!pros.length) pros.push("Pick a crater in Options.");
    if (!cons.length) cons.push("No hard stop on the current options.");
    return {pros, cons};
}
function setMeter(barId, textId, pct, text) {
    const bar = document.getElementById(barId);
    const label = document.getElementById(textId);
    if (bar) bar.style.width = Math.max(4, Math.min(100, pct)) + "%";
    if (label) label.textContent = text;
}
function climbSeries(facts) {
    const pairs = facts.heights.map((height, index) => ({
        height,
        slope: facts.slopes[index] != null ? facts.slopes[index] : null
    }));
    if (pairs.length < 2) return pairs;
    let low = 0;
    let high = 0;
    pairs.forEach((point, index) => {
        if (point.height < pairs[low].height) low = index;
        if (point.height > pairs[high].height) high = index;
    });
    const step = high >= low ? 1 : -1;
    const climb = [];
    for (let index = low; index !== high; index += step) climb.push(pairs[index]);
    climb.push(pairs[high]);
    return climb;
}
function drawHabClimb() {
    const canvas = document.getElementById("hab-rim");
    const fit = canvas ? opsFit(canvas) : null;
    if (!fit) return;
    const {context, width, height} = fit;
    const facts = siteFacts();
    const climb = climbSeries(facts);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#061018";
    context.fillRect(0, 0, width, height);
    if (climb.length < 2) {
        context.fillStyle = "#9ad7e4";
        context.font = "13px Segoe UI, Arial";
        context.fillText("Apply Options to draw the climb.", 12, height / 2);
        return;
    }
    const min = Math.min.apply(null, climb.map(point => point.height));
    const max = Math.max.apply(null, climb.map(point => point.height));
    const span = Math.max(0.001, max - min);
    const left = 8;
    const top = 16;
    const plotW = width - 16;
    const plotH = height - 34;
    const at = (index, value) => ({
        x: left + plotW * index / (climb.length - 1),
        y: top + plotH * (1 - (value - min) / span)
    });
    context.beginPath();
    climb.forEach((point, index) => {
        const spot = at(index, point.height);
        if (index) context.lineTo(spot.x, spot.y);
        else context.moveTo(spot.x, spot.y);
    });
    context.lineTo(at(climb.length - 1, min).x, top + plotH);
    context.lineTo(at(0, min).x, top + plotH);
    context.closePath();
    const wash = context.createLinearGradient(0, top, 0, top + plotH);
    wash.addColorStop(0, "rgba(62,224,240,.28)");
    wash.addColorStop(1, "rgba(8,20,28,0)");
    context.fillStyle = wash;
    context.fill();
    const depth = Math.max(6, Math.min(14, height * 0.09));
    for (let index = 1; index < climb.length; index += 1) {
        const slope = Number(climb[index].slope);
        const blocked = Number.isFinite(slope) && slope >= facts.limit;
        const close = Number.isFinite(slope) && !blocked && slope >= facts.limit - 3;
        const a = at(index - 1, climb[index - 1].height);
        const b = at(index, climb[index].height);
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(a.x, a.y + depth);
        context.lineTo(b.x, b.y + depth);
        context.lineTo(b.x, b.y);
        context.closePath();
        context.fillStyle = blocked ? "rgba(255,77,87,.28)" : close ? "rgba(240,193,74,.26)" : "rgba(57,240,138,.24)";
        context.fill();
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.strokeStyle = blocked ? "#ff4d57" : close ? "#f0c14a" : "#39f08a";
        context.lineWidth = 2.8;
        context.shadowColor = context.strokeStyle;
        context.shadowBlur = 8;
        context.stroke();
        context.shadowBlur = 0;
    }
    context.fillStyle = "#d7f4ff";
    context.font = "700 11px Orbitron, Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("FLOOR", left, height - 8);
    context.textAlign = "center";
    context.fillStyle = facts.floorTough ? "#ffb15a" : "#7eefff";
    context.fillText(facts.floorTough ? "TOUGH MIDDLE" : "CRATER FLOOR", width / 2, height - 8);
    context.textAlign = "right";
    context.fillStyle = "#7dffa8";
    context.fillText("RIM", width - 8, height - 8);
    const meta = document.getElementById("hab-climb-meta");
    if (meta) meta.textContent = "Floor " + min.toFixed(2) + " km · rim " + max.toFixed(2) + " km · climb " + Math.round((max - min) * 1000) + " m";
    const note = document.getElementById("hab-floor-note");
    if (note) {
        note.textContent = facts.floorTough
            ? facts.floorTough + " of " + facts.floorCount + " low-floor samples are steeper than " + facts.limit + "°. That middle is the tough ground. Take the green climb."
            : "The low floor in this window stays under " + facts.limit + "°. The green line is the way up.";
    }
    const foot = document.getElementById("hab-climb-foot");
    if (foot) foot.textContent = (facts.cleared && facts.bad === 0 ? "Cleared walk." : "Not a cleared walk.") + " Limit " + facts.limit + "°.";
}
function updateHabitatReadout() {
    const facts = siteFacts();
    const temperature = latestEnvironment && latestEnvironment.temperature ? latestEnvironment.temperature : {};
    const radiation = latestEnvironment && latestEnvironment.surface_radiation ? latestEnvironment.surface_radiation : {};
    const protons = radiation.protons;
    const site = document.getElementById("hab-site");
    if (site) site.textContent = facts.place.toUpperCase();
    const relief = facts.minH == null ? null : Math.round((facts.maxH - facts.minH) * 1000);
    const reliefNode = document.getElementById("hab-relief");
    const limitNode = document.getElementById("hab-limit");
    if (reliefNode) reliefNode.textContent = relief == null ? "—" : relief + " m";
    if (limitNode) limitNode.textContent = facts.limit + "°";
    const plume = typeof latestPlumeAssessment !== "undefined" ? latestPlumeAssessment : null;
    if (plume) {
        setMeter("hab-dust-bar", "hab-dust-read", plume.overlap ? 88 : 22, plume.overlap ? "Route crosses it" : "Route clears it");
    } else {
        setMeter("hab-dust-bar", "hab-dust-read", 12, "No envelope yet");
    }
    const flarePct = facts.storm ? 92 : /^C/.test(facts.goes) ? 48 : 16;
    setMeter("hab-flare-bar", "hab-flare-read", flarePct, facts.goes && facts.goes !== "Loading…" ? facts.goes : "Waiting");
    const gcr = radiation.baseline_gcr_usv_hr || 57;
    const scale = protons && protons.storm_scale ? protons.storm_scale : "S0";
    setMeter("hab-rad-bar", "hab-rad-read", Math.min(100, gcr / 2), gcr + " µSv/hr · " + scale);
    const night = temperature.night_low_c;
    const day = temperature.day_high_c;
    const hotText = night == null ? "Waiting" : Math.round(night) + "° to " + Math.round(day) + "°C";
    setMeter("hab-hot-bar", "hab-hot-read", night == null ? 8 : Math.min(100, Math.abs(night) / 2), hotText);
    setMeter("hab-night-bar", "hab-night-read", night == null ? 8 : Math.min(100, Math.abs(night) / 2), night == null ? "—" : Math.round(night) + "°C");
    setMeter("hab-day-bar", "hab-day-read", day == null ? 8 : Math.min(100, Math.max(0, day) / 1.3), day == null ? "—" : Math.round(day) + "°C");
    setMeter("hab-sun-bar", "hab-sun-read", temperature.sun_up ? 74 : 18, temperature.sun_up ? "Up" : "Down");
    const goodPct = facts.good + facts.bad ? Math.round(100 * facts.good / (facts.good + facts.near + facts.bad)) : 0;
    const toughPct = facts.floorCount ? Math.round(100 * facts.floorTough / facts.floorCount) : 0;
    setMeter("hab-good-bar", "hab-good-read", goodPct || 8, facts.heights.length ? facts.good + " steps" : "—");
    setMeter("hab-tough-bar", "hab-tough-read", toughPct || 8, facts.floorCount ? facts.floorTough + " / " + facts.floorCount : "—");
    const floorCount = document.getElementById("hab-floor-count");
    if (floorCount) floorCount.textContent = facts.floorCount ? facts.floorTough + " / " + facts.floorCount : "—";
    const floorBadge = document.getElementById("hab-badge-floor");
    if (floorBadge) {
        floorBadge.textContent = facts.floorTough ? "FLOOR IS TOUGH" : "FLOOR IS OPEN";
        floorBadge.className = "hab-badge " + (facts.floorTough ? "warn" : "ok");
    }
    const tempBadge = document.getElementById("hab-badge-temp");
    if (tempBadge) {
        const cold = night != null && night < -100;
        const hot = day != null && day > 80;
        tempBadge.textContent = cold && hot ? "COLD NIGHT · HOT DAY" : cold ? "NIGHT IS COLD" : hot ? "DAY IS HOT" : "THERMAL SET";
        tempBadge.className = "hab-badge " + (cold || hot ? "warn" : "ok");
    }
    const tempScale = document.getElementById("hab-temp-scale");
    if (tempScale) tempScale.textContent = night == null ? "Waiting for the site temperature" : "Night " + Math.round(night) + "°C · day " + Math.round(day) + "°C";
    const shelterLine = document.getElementById("hab-shelter-line");
    if (shelterLine) shelterLine.textContent = facts.sheltered ? "Shelter mass is recorded." : "No shelter. Hold on M or X.";
    const protonLine = document.getElementById("hab-proton-line");
    if (protonLine) protonLine.textContent = "Protons " + (protons ? protons.storm_scale : "unavailable") + ".";
    const keep = plumeKeepout();
    const craft = document.getElementById("plan-vehicle").selectedOptions[0].textContent.split("·")[0].trim();
    const dustNote = document.getElementById("hab-dust-note");
    if (dustNote) {
        const crossing = plume ? (plume.overlap ? "The corridor you entered crosses the walk." : "The corridor you entered stays off the walk.") : "No plume corridor is entered yet.";
        dustNote.innerHTML = "<b>LUNAR DUST PLUME</b> A lander throws dust across the surface. " + craft + " stand-off on this board is " + keep.safe + " m safe and " + keep.dust + " m of dust. " + crossing + " That stand-off is a vehicle keep-out, not a plume-physics model.";
    }
    const flareNote = document.getElementById("hab-flare-note");
    if (flareNote) {
        const quiet = !facts.goes || facts.goes === "Loading…";
        const line = quiet
            ? "Waiting on the GOES X-ray reading."
            : facts.storm
                ? facts.goes + " is M or X class. Protons can follow. " + (facts.sheltered ? "Shelter mass is recorded, so the step is to get behind it." : "No shelter is recorded, so the call is hold.")
                : facts.goes + " is below M-class. The habitat stays on a quiet X-ray watch.";
        flareNote.innerHTML = "<b>SOLAR FLARE</b> " + line + " Mass stops particles. A visor does not.";
    }
    const radNote = document.getElementById("hab-rad-note");
    if (radNote) {
        radNote.innerHTML = "<b>LUNAR RADIATION</b> The quiet-surface reference here is " + gcr + " µSv/hr from galactic cosmic rays. Proton scale is " + scale + ". A long stay needs regolith or a water wall. This is a reference dose, not a personal dosimeter.";
    }
    syncHabComponentGrid();
    const endurance = computeBaseEndurance(facts);
    const endMeta = document.getElementById("hab-end-meta");
    if (endMeta) endMeta.textContent = endurance.opsDays + " d ops";
    const setEnd = (id, text, cls) => {
        const node = document.getElementById(id);
        if (!node) return;
        node.textContent = text;
        node.className = cls || "";
    };
    setEnd("hab-end-ops", endurance.opsDays + " days", endurance.opsDays >= 30 ? "good" : endurance.opsDays >= 10 ? "watch" : "bad");
    setEnd("hab-end-night", endurance.nightSurviveDays.toFixed(1) + " d" + (endurance.nightOk ? "" : " · short"), endurance.nightOk ? "good" : "bad");
    setEnd("hab-end-storm", Math.round(endurance.stormHoldH) + " h", facts.sheltered ? "good" : "watch");
    setEnd("hab-end-power", (endurance.powerMargin >= 0 ? "+" : "") + Math.round(endurance.powerMargin) + " W", endurance.powerMargin >= 0 ? "good" : "bad");
    setEnd("hab-end-life", endurance.lifeDays + " d gate", "watch");
    const barEnd = (id, pct) => { const node = document.getElementById(id); if (node) node.style.width = Math.max(6, Math.min(100, pct)) + "%"; };
    barEnd("hab-end-ops-bar", endurance.opsDays / 1.2);
    barEnd("hab-end-night-bar", Math.min(100, endurance.nightSurviveDays / Math.max(0.5, endurance.nightHoursNeeded / 24) * 100));
    barEnd("hab-end-storm-bar", Math.min(100, endurance.stormHoldH));
    const endFoot = document.getElementById("hab-end-foot");
    if (endFoot) {
        endFoot.textContent = "Day load ~" + Math.round(endurance.dayLoad) + " W vs array ~" + Math.round(endurance.arrayW) +
            " W. Night needs ~" + Math.round(endurance.nightHoursNeeded) + " h. Planning band only.";
    }
    const status = document.getElementById("hab-status");
    if (status) {
        const ok = endurance.nightOk && endurance.powerMargin >= 0 && !facts.storm;
        status.textContent = !facts.heights.length ? "STANDBY" : ok ? "BASE READY" : "WATCH";
        status.className = !facts.heights.length ? "" : ok ? "ok" : "warn";
    }
    if (habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
    if (typeof updateYardVisibility === "function") updateYardVisibility();
    const baseLine = document.getElementById("hab-base-line");
    if (baseLine) {
        const pad = likelyPad(facts);
        const kit = activeHabComponents();
        const names = Object.fromEntries(HAB_COMPONENT_DEFS.map(def => [def.id, def.name.toLowerCase()]));
        const pieces = kit.map(id => names[id] || id).filter(Boolean).join(", ");
        if (pad) {
            baseLine.textContent = "Pad on " + (pad.clear ? "clearest shoulder" : "least-steep ground") + " at " + pad.slope.toFixed(1) +
                "°. Placed: " + pieces + ". Endurance ~" + endurance.opsDays + " days ops / night " + endurance.nightSurviveDays.toFixed(1) + " d.";
        } else {
            baseLine.textContent = "Place modules in the yard. Dangers stay live. Endurance waits on terrain + power inputs.";
        }
    }
    const destOpt = document.getElementById("plan-destination").selectedOptions[0];
    const diam = destOpt && destOpt.dataset.diameter ? destOpt.dataset.diameter + " km" : "—";
    const padHud = likelyPad(facts);
    const setHud = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
    setHud("hab-hud-name", facts.place);
    setHud("hab-hud-ll", facts.pair.map(v => Number(v).toFixed(2) + "°").join(", "));
    setHud("hab-hud-diam", diam);
    setHud("hab-hud-pad", padHud ? padHud.slope.toFixed(1) + "°" : "—");
    setHud("hab-hud-relief", relief == null ? "—" : relief + " m");
    setHud("hab-hud-walk", facts.km == null ? "waiting" : (facts.cleared ? "cleared " : "preview ") + Number(facts.km).toFixed(1) + " km");
    const score = !facts.heights.length ? "—" : Math.max(0, Math.min(100, Math.round(100 * facts.good / Math.max(1, facts.good + facts.near + facts.bad) - (facts.floorTough ? 12 : 0) + (facts.sheltered ? 6 : 0))));
    setHud("hab-hud-score", score === "—" ? "—" : score + " / 100");
    const scaleNode = document.getElementById("hab-scale");
    if (scaleNode) scaleNode.textContent = lolaHeightField ? "LOLA DEM · LIVE" : "LOLA DEM · waiting";
    const purpose = document.getElementById("hab-purpose");
    if (purpose) {
        const baseText = likelyPad(facts)
            ? optionLine()
            : "No base is selected yet; the habitat review is focused on the environmental risks and laydown choices";
        purpose.innerHTML = "<b>KEEP THE HABITAT ALIVE</b> " + baseText + ".";
    }
}
function plumeKeepout() {
    const id = document.getElementById("plan-vehicle").value;
    const table = {sls: [150, 800], lvm3: [80, 250], falcon9: [120, 500], longmarch5: [140, 700], h3: [70, 200]};
    const pair = table[id] || [100, 300];
    return {safe: pair[0], dust: pair[1]};
}
function waterPlan(facts) {
    const lat = Math.abs(facts.pair[0]);
    const relief = facts.minH == null ? 0 : facts.maxH - facts.minH;
    if (lat < 80) return {perDay: 0, fill: 0.06, stock: 0, note: "Below 80° this crater is not the water case."};
    if (relief < 0.15) return {perDay: 0, fill: 0.08, stock: 0, note: "The path has not dropped onto the floor yet."};
    const perDay = lat >= 85 ? 180 : 60;
    return {
        perDay,
        fill: lat >= 85 ? 0.72 : 0.4,
        stock: perDay * 7,
        note: "Planning band for a small extractor. Not a measured yield."
    };
}
function baseKit() {
    const kit = [];
    document.querySelectorAll("#base-kit [data-kit]").forEach(button => {
        if (button.getAttribute("aria-pressed") === "true") kit.push(button.dataset.kit);
    });
    if (kit.indexOf("habitat") < 0) kit.unshift("habitat");
    return kit;
}
function likelyPad(facts) {
    const scan = (opsTerrain && opsTerrain.area_scan) || [];
    const cells = scan.map(cell => ({
        elev: Number(cell.elev_km),
        slope: Number(cell.slope),
        km: localProject(Number(cell.lat), Number(cell.lon), facts.pair[0], facts.pair[1])
    })).filter(cell => Number.isFinite(cell.elev) && Number.isFinite(cell.slope));
    if (!cells.length) return null;
    const elevs = cells.map(cell => cell.elev).sort((a, b) => a - b);
    const highCut = elevs[Math.min(elevs.length - 1, Math.floor(elevs.length * 0.62))];
    const shoulder = cells.filter(cell => cell.elev >= highCut && cell.slope < facts.limit);
    const under = cells.filter(cell => cell.slope < facts.limit);
    const pool = shoulder.length ? shoulder : (under.length ? under : cells);
    pool.sort((a, b) => a.slope - b.slope || b.elev - a.elev);
    const best = pool[0];
    return {
        elev: best.elev,
        slope: best.slope,
        km: best.km,
        clear: best.slope < facts.limit,
        why: best.slope < facts.limit
            ? "Clearest nearby shoulder, under the " + facts.limit + "° climb limit."
            : "Every nearby sample is over the climb limit. This is the least steep."
    };
}
function iceProspect(facts) {
    const lat = Math.abs(facts.pair[0]);
    if (lat >= 85) return {title: "COLD-TRAP CASE", detail: "This latitude can hide ice in shadow on the floor. It is a case, not a detection."};
    if (lat >= 80) return {title: "WEAK ICE CASE", detail: "High latitude, short of the polar cold traps. Not a detection."};
    return {title: "NO ICE CASE", detail: "Below 80° this floor is not a cold-trap target. Not a detection."};
}
function drawBaseGlyph(context, x, y, kit, scale) {
    const s = scale || 1;
    context.save();
    context.translate(x, y);
    context.scale(s, s);
    const has = id => kit.indexOf(id) >= 0;
    context.lineWidth = 2;
    if (has("habitat")) {
        context.fillStyle = "#c8d8dc";
        context.strokeStyle = "#e7f7ff";
        context.beginPath();
        context.moveTo(-50, -12);
        context.lineTo(-50, -20);
        context.quadraticCurveTo(-50, -27, -42, -27);
        context.lineTo(-20, -27);
        context.quadraticCurveTo(-12, -27, -12, -19);
        context.lineTo(-12, -12);
        context.closePath();
        context.fill();
        context.stroke();
        context.fillStyle = "#183847";
        context.fillRect(-42, -23, 5, 5);
        context.fillRect(-33, -23, 5, 5);
        context.fillStyle = "#9ad7e4";
        context.fillRect(-11, -18, 6, 8);
        context.strokeStyle = "rgba(227,190,126,.75)";
        context.lineWidth = 4;
        context.beginPath();
        context.moveTo(-53, -8);
        context.quadraticCurveTo(-32, -2, -8, -8);
        context.stroke();
        context.lineWidth = 2;
        context.strokeStyle = "#d8c29a";
        context.beginPath();
        context.moveTo(-48, -5);
        context.lineTo(-48, 0);
        context.moveTo(-16, -5);
        context.lineTo(-16, 0);
        context.stroke();
    }
    if (has("lab")) {
        context.fillStyle = "#bacad0";
        context.strokeStyle = "#9ad7e4";
        context.fillRect(-4, -23, 24, 17);
        context.strokeRect(-4, -23, 24, 17);
        context.fillStyle = "#284451";
        context.fillRect(1, -19, 5, 5);
        context.fillRect(10, -19, 5, 5);
        context.strokeStyle = "#d8c29a";
        context.lineWidth = 4;
        context.beginPath();
        context.moveTo(-7, -4);
        context.lineTo(22, -4);
        context.stroke();
    }
    if (has("array")) {
        context.strokeStyle = "#d7f4ff";
        context.beginPath();
        context.moveTo(30, 2);
        context.lineTo(30, -30);
        context.stroke();
        context.fillStyle = "#0c3040";
        context.fillRect(18, -32, 27, 15);
        context.strokeStyle = "#7af4ff";
        context.strokeRect(18, -32, 27, 15);
        context.beginPath();
        context.moveTo(27, -32);
        context.lineTo(27, -17);
        context.moveTo(36, -32);
        context.lineTo(36, -17);
        context.moveTo(18, -24);
        context.lineTo(45, -24);
        context.stroke();
    }
    if (has("rover")) {
        context.fillStyle = "#e6c36a";
        context.fillRect(2, 1, 21, 7);
        context.beginPath();
        context.arc(7, 9, 3, 0, Math.PI * 2);
        context.arc(20, 9, 3, 0, Math.PI * 2);
        context.fill();
        context.strokeStyle = "#f2db9d";
        context.beginPath();
        context.moveTo(8, 1);
        context.lineTo(11, -5);
        context.lineTo(17, 1);
        context.stroke();
    }
    context.restore();
}
function drawHabSite() {
    if (habCraterView) return;
    const canvas = document.getElementById("hab-crater");
    const fit = canvas ? opsFit(canvas) : null;
    if (!fit) return;
    const {context, width, height} = fit;
    const facts = siteFacts();
    const pad = likelyPad(facts);
    const pair = facts.pair;
    context.clearRect(0, 0, width, height);
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#07080c");
    sky.addColorStop(0.42, "#16130f");
    sky.addColorStop(1, "#3a342c");
    context.fillStyle = sky;
    context.fillRect(0, 0, width, height);
    const bowl = context.createRadialGradient(width * 0.42, height * 0.62, 16, width * 0.46, height * 0.58, Math.min(width, height) * 0.48);
    bowl.addColorStop(0, "#12181e");
    bowl.addColorStop(0.5, "#3c3932");
    bowl.addColorStop(1, "#7a7368");
    context.fillStyle = bowl;
    context.beginPath();
    context.ellipse(width * 0.44, height * 0.6, width * 0.4, height * 0.34, -0.15, 0, Math.PI * 2);
    context.fill();
    const origin = pad ? pad.km : {e: 0, n: 0};
    const half = 7;
    const toXY = (east, north) => ({
        x: (east - origin.e + half) / (2 * half) * width,
        y: (half - (north - origin.n)) / (2 * half) * height
    });
    const scan = ((opsTerrain && opsTerrain.area_scan) || []).map(cell => ({
        elev: Number(cell.elev_km),
        slope: Number(cell.slope),
        km: localProject(Number(cell.lat), Number(cell.lon), pair[0], pair[1])
    })).filter(cell => Number.isFinite(cell.elev) && Number.isFinite(cell.slope));
    if (scan.length) {
        const elevs = scan.map(cell => cell.elev);
        const min = Math.min.apply(null, elevs);
        const max = Math.max.apply(null, elevs);
        const span = Math.max(0.001, max - min);
        scan.forEach(cell => {
            const at = toXY(cell.km.e, cell.km.n);
            if (at.x < -12 || at.y < -12 || at.x > width + 12 || at.y > height + 12) return;
            const t = (cell.elev - min) / span;
            const steep = cell.slope >= facts.limit;
            const shade = Math.round(36 + t * 150);
            context.fillStyle = steep ? "rgba(196, 48, 56, .9)" : "rgba(" + shade + "," + Math.max(0, shade - 6) + "," + Math.max(0, shade - 14) + ",.92)";
            context.beginPath();
            context.arc(at.x, at.y, steep ? 6 : 8, 0, Math.PI * 2);
            context.fill();
        });
    }
    const route = opsTerrain ? ((facts.cleared ? opsTerrain.route : opsTerrain.advisory_route) || []) : [];
    const slopes = opsTerrain ? ((facts.cleared ? opsTerrain.route_slope_degrees : opsTerrain.advisory_route_slope_degrees) || []) : [];
    const point = item => Array.isArray(item) ? {lat: Number(item[0]), lon: Number(item[1])} : {lat: Number(item.lat), lon: Number(item.lon)};
    const routeKm = route.map(item => {
        const at = point(item);
        return localProject(at.lat, at.lon, pair[0], pair[1]);
    });
    context.lineCap = "round";
    context.lineJoin = "round";
    context.lineWidth = 3;
    for (let index = 1; index < routeKm.length; index += 1) {
        const slope = Number(slopes[index] != null ? slopes[index] : slopes[index - 1]);
        const blocked = Number.isFinite(slope) && slope >= facts.limit;
        const close = Number.isFinite(slope) && !blocked && slope >= facts.limit - 3;
        const a = toXY(routeKm[index - 1].e, routeKm[index - 1].n);
        const b = toXY(routeKm[index].e, routeKm[index].n);
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.strokeStyle = blocked ? "#ff4d57" : close ? "#f0c14a" : "#39f08a";
        context.stroke();
    }
    const spot = pad ? toXY(pad.km.e, pad.km.n) : {x: width * 0.68, y: height * 0.28};
    drawBaseGlyph(context, spot.x, spot.y, baseKit(), Math.max(0.85, Math.min(width, height) / 520));
    context.font = "700 12px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillStyle = "#f4fbff";
    context.fillText(pad && pad.clear ? "LIKELY BASE" : "LEAST STEEP", spot.x + 8, spot.y - 22);
    context.fillStyle = "#9ad7e4";
    context.font = "12px Segoe UI, Arial";
    context.fillText(pad ? pad.slope.toFixed(1) + "° slope" : "waiting", spot.x + 8, spot.y - 6);
    context.fillStyle = "#7eefff";
    context.fillText("CRATER FLOOR", 12, height * 0.7);
}
function hudFrame(canvas) {
    const fit = canvas ? opsFit(canvas) : null;
    if (!fit) return null;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#07141c";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#1c8eaa";
    context.lineWidth = 1.5;
    context.strokeRect(1, 1, width - 2, height - 2);
    return fit;
}
function drawThrustGauge(canvas, fraction, percentText) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#4da3ff";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.textAlign = "left";
    context.fillText("RETRO-THRUST VECTOR", 8, 14);
    const cx = width * 0.34;
    const cy = height * 0.78;
    const radius = Math.min(width * 0.28, height * 0.44);
    for (let index = 0; index < 20; index += 1) {
        const a0 = Math.PI + Math.PI * index / 20;
        const a1 = Math.PI + Math.PI * (index + 1) / 20;
        context.strokeStyle = "hsl(" + (125 - index * 7) + ", 85%, " + (48 + index) + "%)";
        context.lineWidth = 8;
        context.beginPath();
        context.arc(cx, cy, radius, a0, a1);
        context.stroke();
    }
    const needle = Math.PI + Math.PI * Math.max(0, Math.min(1, fraction));
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2.5;
    context.shadowColor = "#4da3ff";
    context.shadowBlur = 8;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 2), cy + Math.sin(needle) * (radius - 2));
    context.stroke();
    context.shadowBlur = 0;
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(18, Math.floor(height * 0.34)) + "px Share Tech Mono, monospace";
    context.textAlign = "right";
    context.fillText(percentText, width - 10, height * 0.48);
    context.fillStyle = "#9ad7e4";
    context.font = "700 11px Orbitron, sans-serif";
    context.fillText("THRUST", width - 10, height * 0.48 + 16);
    context.textAlign = "left";
    context.fillStyle = "#d7f4ff";
    context.font = "11px Share Tech Mono, monospace";
    context.fillText("Vector: 0.2°  ↔  0.1° ↑", 8, height - 8);
}
function drawVelocityGauge(canvas, ready) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#4da3ff";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.textAlign = "left";
    context.fillText("VELOCITY", 8, 14);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(22, Math.floor(height * 0.38)) + "px Share Tech Mono, monospace";
    context.fillText(ready ? "1.8 m/s" : "—", 8, height * 0.5);
    context.fillStyle = "#39ff14";
    context.font = "700 13px Share Tech Mono, monospace";
    context.fillText(ready ? "↓  settle rate" : "on the pad", 8, height * 0.5 + 20);
    context.fillStyle = "#9ad7e4";
    context.font = "11px Share Tech Mono, monospace";
    context.fillText("Planning settle · not a flying model", 8, height - 8);
}
function drawAltitudeGauge(canvas, meters) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#4da3ff";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.textAlign = "left";
    context.fillText("ALTITUDE", 8, 14);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(20, Math.floor(height * 0.34)) + "px Share Tech Mono, monospace";
    context.fillText(meters == null ? "—" : meters.toLocaleString() + " m", 8, height * 0.48);
    context.fillStyle = "#7af4ff";
    context.font = "600 12px Share Tech Mono, monospace";
    context.fillText(meters == null ? "Waiting for LOLA pad" : "LOLA pad elevation", 8, height * 0.48 + 18);
    context.fillStyle = "#9ad7e4";
    context.font = "11px Share Tech Mono, monospace";
    context.fillText("Highest selected pad sample", 8, height - 8);
}
function drawFuelGauge(canvas, fraction, text) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#4da3ff";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.textAlign = "left";
    context.fillText("FUEL", 8, 14);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(22, Math.floor(height * 0.36)) + "px Share Tech Mono, monospace";
    context.fillText(text, 8, height * 0.46);
    context.fillStyle = "#0a1820";
    context.strokeStyle = "#1a6d86";
    context.lineWidth = 1;
    context.fillRect(8, height * 0.58, width - 16, 14);
    context.strokeRect(8, height * 0.58, width - 16, 14);
    const grad = context.createLinearGradient(8, 0, width - 8, 0);
    grad.addColorStop(0, "#39ff14");
    grad.addColorStop(0.55, "#f0c14a");
    grad.addColorStop(1, "#ff8c00");
    context.fillStyle = grad;
    context.shadowColor = "#39ff14";
    context.shadowBlur = 8;
    context.fillRect(8, height * 0.58, (width - 16) * Math.max(0, Math.min(1, fraction)), 14);
    context.shadowBlur = 0;
    context.fillStyle = "#9ad7e4";
    context.font = "11px Share Tech Mono, monospace";
    context.fillText("Battery reserve for the walk", 8, height - 8);
}
function drawDescentStage(facts, pad) {
    if (descentThreeView) {
        descentThreeView.resize();
        descentThreeView.render();
        return;
    }
    const fit = opsFit(document.getElementById("des-stage"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#02040a");
    sky.addColorStop(0.52, "#101c2a");
    sky.addColorStop(1, "#252720");
    context.fillStyle = sky;
    context.fillRect(0, 0, width, height);
    for (let index = 0; index < 110; index += 1) {
        const x = (index * 97) % width;
        const y = (index * 53) % Math.floor(height * 0.5);
        context.fillStyle = "rgba(230,240,255," + (0.35 + (index % 5) * 0.1) + ")";
        context.fillRect(x, y, index % 9 === 0 ? 2 : 1, index % 9 === 0 ? 2 : 1);
    }
    const earthR = Math.min(width, height) * 0.12;
    const earthX = width * 0.17;
    const earthY = height * 0.22;
    const earth = context.createRadialGradient(earthX - earthR * 0.3, earthY - earthR * 0.3, earthR * 0.2, earthX, earthY, earthR);
    earth.addColorStop(0, "#d7f4ff");
    earth.addColorStop(0.35, "#3d8fd4");
    earth.addColorStop(1, "#1a4e96");
    context.fillStyle = earth;
    context.beginPath();
    context.arc(earthX, earthY, earthR, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "rgba(255,255,255,.55)";
    context.beginPath();
    context.ellipse(earthX - earthR * 0.15, earthY + earthR * 0.1, earthR * 0.45, earthR * 0.22, -0.4, 0, Math.PI * 2);
    context.fill();
    const groundY = height * 0.72;
    context.fillStyle = "#282b2a";
    context.beginPath();
    context.moveTo(0, groundY + 6);
    context.lineTo(width * 0.1, groundY - height * 0.1);
    context.lineTo(width * 0.22, groundY - height * 0.03);
    context.lineTo(width * 0.36, groundY - height * 0.12);
    context.lineTo(width * 0.51, groundY - height * 0.02);
    context.lineTo(width * 0.67, groundY - height * 0.1);
    context.lineTo(width * 0.82, groundY - height * 0.04);
    context.lineTo(width, groundY - height * 0.12);
    context.lineTo(width, height);
    context.lineTo(0, height);
    context.closePath();
    context.fill();
    const ground = context.createLinearGradient(0, groundY - 30, 0, height);
    ground.addColorStop(0, "#b2a38e");
    ground.addColorStop(0.24, "#625b50");
    ground.addColorStop(1, "#171a18");
    context.fillStyle = ground;
    context.beginPath();
    context.moveTo(0, groundY + 8);
    context.lineTo(width * 0.14, groundY + 2);
    context.lineTo(width * 0.29, groundY + 16);
    context.lineTo(width * 0.43, groundY + 5);
    context.lineTo(width * 0.58, groundY + 12);
    context.lineTo(width * 0.78, groundY - 1);
    context.lineTo(width, groundY + 11);
    context.lineTo(width, height);
    context.lineTo(0, height);
    context.closePath();
    context.fill();
    for (let index = 0; index < 11; index += 1) {
        const x = (index * 149 + 37) % width;
        const y = groundY + 24 + (index * 31) % Math.max(1, Math.floor(height * 0.2));
        const rx = 10 + (index * 7) % 29;
        const ry = 2 + (index * 3) % 6;
        context.strokeStyle = "rgba(206,194,174," + (0.12 + (index % 4) * 0.04) + ")";
        context.lineWidth = 1;
        context.beginPath();
        context.ellipse(x, y, rx, ry, -0.12, Math.PI, Math.PI * 2);
        context.stroke();
    }
    const padX = width * 0.56;
    const padY = groundY + 6;
    const plumeTop = padY - Math.min(height * 0.38, 150);
    const plume = context.createRadialGradient(padX, plumeTop + 40, 4, padX, padY, height * 0.48);
    plume.addColorStop(0, "rgba(255,244,213,.96)");
    plume.addColorStop(0.2, "rgba(255,190,103,.74)");
    plume.addColorStop(0.64, "rgba(212,197,173,.34)");
    plume.addColorStop(1, "rgba(212,197,173,0)");
    context.fillStyle = plume;
    context.beginPath();
    context.moveTo(padX - 18, plumeTop);
    context.lineTo(padX - width * 0.25, padY + 18);
    context.quadraticCurveTo(padX, padY + 44, padX + width * 0.25, padY + 18);
    context.lineTo(padX + 18, plumeTop);
    context.closePath();
    context.fill();
    for (let index = 0; index < 36; index += 1) {
        const spread = ((index * 37) % 100) / 100;
        const x = padX + (index % 2 ? 1 : -1) * spread * width * 0.29;
        const y = padY - 16 + (index * 19) % 54;
        context.fillStyle = "rgba(214,204,186," + (0.13 + (index % 4) * 0.06) + ")";
        context.beginPath();
        context.ellipse(x, y, 4 + (index % 8), 2 + (index % 3), 0, 0, Math.PI * 2);
        context.fill();
    }
    context.setLineDash([7, 5]);
    context.strokeStyle = "#ff9a3c";
    context.lineWidth = 2;
    context.beginPath();
    context.ellipse(padX, padY + 11, Math.min(width * 0.26, 150), 26, -0.15, 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    context.strokeStyle = "#3dff9a";
    context.beginPath();
    context.ellipse(padX, padY + 11, Math.min(width * 0.13, 74), 17, -0.15, 0, Math.PI * 2);
    context.stroke();
    context.save();
    const scale = Math.max(0.72, Math.min(1.35, Math.min(width / 780, height / 500)));
    context.translate(padX, padY - 66);
    context.scale(scale, scale);
    context.strokeStyle = "#e7eef2";
    context.fillStyle = "#f7f8f6";
    context.lineWidth = 2.5;
    [[-38, 4, -54, 28], [38, 4, 54, 28], [-24, 6, -32, 29], [24, 6, 32, 29]].forEach(leg => {
        context.beginPath();
        context.moveTo(leg[0], leg[1]);
        context.lineTo(leg[2], leg[3]);
        context.stroke();
    });
    context.fillStyle = "#f4f7f8";
    context.beginPath();
    context.moveTo(-26, -54);
    context.lineTo(-18, -76);
    context.lineTo(18, -76);
    context.lineTo(26, -54);
    context.lineTo(22, 4);
    context.lineTo(-22, 4);
    context.closePath();
    context.fill();
    context.strokeStyle = "#c5ced4";
    context.stroke();
    context.fillStyle = "#c6a15a";
    context.fillRect(-28, -50, 56, 20);
    context.fillStyle = "#152834";
    context.fillRect(-10, -70, 20, 12);
    context.strokeStyle = "#61d9f4";
    context.lineWidth = 1.5;
    context.strokeRect(-10, -70, 20, 12);
    context.fillStyle = "#1c242c";
    context.fillRect(-13, 2, 26, 8);
    const flameOffsets = [[-18, 8], [18, 8], [-8, 10], [8, 10]];
    flameOffsets.forEach((off, i) => {
        const flame = context.createLinearGradient(off[0], off[1], off[0], off[1] + 36);
        flame.addColorStop(0, "rgba(255,244,200,.95)");
        flame.addColorStop(0.35, "rgba(255,160,60,.85)");
        flame.addColorStop(1, "rgba(255,90,20,0)");
        context.fillStyle = flame;
        context.beginPath();
        context.moveTo(off[0] - 5, off[1]);
        context.lineTo(off[0] - 2 - (i % 2), off[1] + 30 + (i % 3) * 2);
        context.lineTo(off[0] + 2 + (i % 2), off[1] + 30 + (i % 3) * 2);
        context.lineTo(off[0] + 5, off[1]);
        context.closePath();
        context.fill();
    });
    context.restore();
    context.strokeStyle = "#7af4ff";
    context.lineWidth = 1.5;
    context.beginPath();
    context.moveTo(padX, padY - 76 * scale);
    context.lineTo(padX, padY - 122 * scale);
    context.stroke();
    const meters = pad ? Number(pad.elev).toFixed(2) + " km" : "—";
    context.fillStyle = "rgba(4,18,12,.88)";
    context.strokeStyle = "#39ff14";
    context.lineWidth = 1.5;
    context.shadowColor = "#39ff14";
    context.shadowBlur = 10;
    context.fillRect(padX - 56, padY - 154 * scale, 112, 28);
    context.strokeRect(padX - 56, padY - 154 * scale, 112, 28);
    context.shadowBlur = 0;
    context.fillStyle = "#39ff14";
    context.font = "700 15px Share Tech Mono, monospace";
    context.textAlign = "center";
    context.fillText(meters, padX, padY - 134 * scale);
    context.textAlign = "right";
    context.fillStyle = "#d7f4ff";
    context.font = "700 12px Segoe UI, Arial";
    context.fillText(facts.place.toUpperCase(), width - 14, 24);
}
function drawDescentPlume(keep) {
    const fit = opsFit(document.getElementById("des-plume"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const cx = width * 0.4;
    const cy = height * 0.56;
    const radius = Math.min(width, height) * 0.32;
    context.strokeStyle = "rgba(80, 160, 180, .35)";
    context.lineWidth = 1;
    context.beginPath();
    context.arc(cx, cy, radius * 1.15, 0, Math.PI * 2);
    context.stroke();
    context.strokeStyle = "#ff9a3c";
    context.lineWidth = 2;
    context.setLineDash([4, 3]);
    context.beginPath();
    context.arc(cx, cy, radius, 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    context.strokeStyle = "#3dff9a";
    context.beginPath();
    context.arc(cx, cy, radius * 0.48, 0, Math.PI * 2);
    context.stroke();
    context.fillStyle = "#7af4ff";
    context.beginPath();
    context.arc(cx, cy, 3, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#3dff9a";
    context.font = "700 12px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("Safe Radius", 8, 18);
    context.font = "12px Segoe UI, Arial";
    context.fillText(keep.safe + " m", 8, 34);
    context.fillStyle = "#ff9a3c";
    context.font = "700 12px Segoe UI, Arial";
    context.fillText("Dust Zone", 8, height - 28);
    context.font = "12px Segoe UI, Arial";
    context.fillText(keep.dust + " m", 8, height - 12);
}
let desMapZoom = 1;
let desMapCenter = {x: 0, z: 0};
let desMapInspect = null;
let desMapMode = "relief";
function padMapPoint(pad) {
    if (!pad || !pad.km) return {x: -0.12, z: -0.12};
    return {
        x: Math.max(-0.9, Math.min(0.9, pad.km.e / 22)),
        z: Math.max(-0.9, Math.min(0.9, pad.km.n / 22))
    };
}
function slopeAtMap(wx, wz) {
    const dx = siteSurfaceHeight(wx + 0.014, wz) - siteSurfaceHeight(wx - 0.014, wz);
    const dz = siteSurfaceHeight(wx, wz + 0.014) - siteSurfaceHeight(wx, wz - 0.014);
    return Math.min(45, Math.sqrt(dx * dx + dz * dz) * 180);
}
function reliefColor(h, shade, mode, climbLimit) {
    if (mode === "slope") {
        const t = Math.max(0, Math.min(1, h / Math.max(8, climbLimit * 1.35)));
        if (t < 0.45) return [
            Math.round(31 + t * 80),
            Math.round(143 - t * 40),
            Math.round(114 - t * 30)
        ].map(v => Math.round(v * shade));
        if (t < 0.75) return [
            Math.round(196),
            Math.round(146 - (t - 0.45) * 40),
            Math.round(58)
        ].map(v => Math.round(v * shade));
        return [
            Math.round(141 + (t - 0.75) * 40),
            Math.round(61),
            Math.round(72)
        ].map(v => Math.round(v * shade));
    }
    const base = h < -0.3 ? [36, 78, 96] : h < -0.08 ? [78, 98, 102] : h < 0.12 ? [128, 124, 108] : h < 0.28 ? [168, 156, 128] : [204, 188, 150];
    return base.map(v => Math.round(v * shade));
}
function drawDescentMap(facts, ice, pad) {
    const fit = opsFit(document.getElementById("des-map"));
    if (!fit) return;
    const {context, width, height} = fit;
    const climbLimit = Number((document.getElementById("brief-slope") || {}).value || 15);
    const mode = desMapMode || "relief";
    context.clearRect(0, 0, width, height);
    const bg = context.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, "#0a1520");
    bg.addColorStop(1, "#050a10");
    context.fillStyle = bg;
    context.fillRect(0, 0, width, height);
    const side = Math.max(24, Math.min(width - 10, height - 10));
    const left = (width - side) / 2;
    const top = (height - side) / 2;
    const size = Math.max(110, Math.min(280, Math.round(side)));
    const raster = context.createImageData(size, size);
    const point = (x, z) => ({
        x: left + side * (0.5 + (x - desMapCenter.x) * desMapZoom / 2),
        y: top + side * (0.5 - (z - desMapCenter.z) * desMapZoom / 2)
    });
    for (let y = 0; y < size; y += 1) {
        for (let x = 0; x < size; x += 1) {
            const wx = desMapCenter.x + (x / (size - 1) - 0.5) * 2 / desMapZoom;
            const wz = desMapCenter.z + (0.5 - y / (size - 1)) * 2 / desMapZoom;
            const h = siteSurfaceHeight(wx, wz);
            const dx = siteSurfaceHeight(wx + 0.012, wz) - siteSurfaceHeight(wx - 0.012, wz);
            const dz = siteSurfaceHeight(wx, wz + 0.012) - siteSurfaceHeight(wx, wz - 0.012);
            const shade = Math.max(0.58, Math.min(1.32, 0.92 + (-dx + dz) * 3.4));
            const sample = mode === "slope" ? slopeAtMap(wx, wz) : h;
            const rgb = reliefColor(sample, mode === "contour" ? 0.78 + shade * 0.22 : shade, mode === "contour" ? "relief" : mode, climbLimit);
            const i = (y * size + x) * 4;
            raster.data[i] = rgb[0];
            raster.data[i + 1] = rgb[1];
            raster.data[i + 2] = rgb[2];
            raster.data[i + 3] = 255;
        }
    }
    const terrain = document.createElement("canvas");
    terrain.width = size;
    terrain.height = size;
    terrain.getContext("2d").putImageData(raster, 0, 0);
    context.save();
    context.beginPath();
    context.roundRect ? context.roundRect(left, top, side, side, 6) : context.rect(left, top, side, side);
    context.clip();
    context.imageSmoothingEnabled = true;
    context.drawImage(terrain, left, top, side, side);
    const ringCount = mode === "contour" ? 14 : 9;
    for (let ring = 0; ring < ringCount; ring += 1) {
        const radius = 0.14 + ring * (mode === "contour" ? 0.055 : 0.082);
        context.beginPath();
        for (let step = 0; step <= 180; step += 1) {
            const angle = step / 180 * Math.PI * 2;
            const wobble = 1 + 0.03 * Math.sin(angle * 5 + ring) + 0.016 * Math.sin(angle * 11 - ring);
            const at = point(Math.cos(angle) * radius * wobble, Math.sin(angle) * radius * wobble);
            if (step) context.lineTo(at.x, at.y);
            else context.moveTo(at.x, at.y);
        }
        context.closePath();
        if (mode === "contour") {
            context.strokeStyle = ring % 3 === 0 ? "rgba(232,244,255,.72)" : "rgba(180,210,220,.34)";
            context.lineWidth = ring % 3 === 0 ? 1.35 : 0.7;
        } else {
            context.strokeStyle = ring === 3 ? "rgba(233,203,145,.7)" : "rgba(226,224,205,.28)";
            context.lineWidth = ring === 3 ? 1.3 : 0.65;
        }
        context.stroke();
    }
    [[-0.58, 0.42, 0.11], [0.62, 0.36, 0.075], [0.48, -0.63, 0.09], [-0.38, -0.68, 0.06]].forEach(crater => {
        const at = point(crater[0], crater[1]);
        context.beginPath();
        context.ellipse(at.x, at.y, side * crater[2] * desMapZoom, side * crater[2] * desMapZoom * 0.72, -0.18, 0, Math.PI * 2);
        context.strokeStyle = "rgba(18,22,22,.78)";
        context.lineWidth = 1.4;
        context.stroke();
        context.beginPath();
        context.ellipse(at.x - 1, at.y - 1, side * crater[2] * desMapZoom * 0.64, side * crater[2] * desMapZoom * 0.42, -0.18, Math.PI, Math.PI * 2);
        context.strokeStyle = "rgba(228,211,175,.42)";
        context.lineWidth = 1;
        context.stroke();
    });
    const icePossible = ice && ice.title !== "NO ICE CASE";
    if (icePossible) {
        const center = point(0, 0);
        context.fillStyle = "rgba(67,205,238,.16)";
        context.beginPath();
        context.ellipse(center.x, center.y, side * 0.14 * desMapZoom, side * 0.09 * desMapZoom, -0.12, 0, Math.PI * 2);
        context.fill();
        context.strokeStyle = "#69e5ff";
        context.setLineDash([4, 3]);
        context.lineWidth = 1.5;
        context.stroke();
        context.setLineDash([]);
    }
    const padLocal = padMapPoint(pad);
    const baseAt = point(padLocal.x, padLocal.z);
    const baseX = baseAt.x;
    const baseY = baseAt.y;
    context.strokeStyle = "rgba(61,255,154,.35)";
    context.lineWidth = 1;
    context.setLineDash([3, 3]);
    context.beginPath();
    context.arc(baseX, baseY, Math.max(14, side * 0.08), 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    drawBaseGlyph(context, baseX, baseY, baseKit(), Math.max(0.75, Math.min(width, height) / 170));
    context.strokeStyle = "#49e6b0";
    context.lineWidth = 1.6;
    context.beginPath();
    context.arc(baseX, baseY, 9, 0, Math.PI * 2);
    context.stroke();
    context.fillStyle = "rgba(4,16,14,.88)";
    context.fillRect(baseX + 10, baseY - 18, 54, 16);
    context.fillStyle = "#3dff9a";
    context.font = "700 10px Share Tech Mono, monospace";
    context.textAlign = "left";
    context.fillText("PAD", baseX + 14, baseY - 6);
    context.fillStyle = "rgba(4,12,18,.82)";
    context.fillRect(left + 4, top + 4, Math.min(168, side * 0.72), 34);
    context.fillStyle = "#f4fbff";
    context.font = "700 10px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText(icePossible ? "COLD-TRAP BAND · NOT DETECTED" : "NO POLAR ICE CASE", left + 8, top + 16);
    context.fillStyle = "#9ad7e4";
    context.font = "10px Segoe UI, Arial";
    context.fillText(
        (lolaHeightField ? "LOLA · " : "Synth · ") +
        (pad ? (pad.clear ? "clearest pad " : "least steep ") + pad.slope.toFixed(1) + "°" : "waiting on path"),
        left + 8,
        top + 30
    );
    context.fillStyle = "rgba(4,12,18,.78)";
    context.fillRect(left + side - 28, top + 4, 24, 16);
    context.fillStyle = "#e8fbff";
    context.font = "700 10px Segoe UI, Arial";
    context.textAlign = "center";
    context.fillText("N↑", left + side - 16, top + 15);
    if (desMapInspect) {
        const at = point(desMapInspect.x, desMapInspect.z);
        context.strokeStyle = "#fff6ae";
        context.lineWidth = 1.6;
        context.beginPath();
        context.moveTo(at.x - 8, at.y); context.lineTo(at.x + 8, at.y);
        context.moveTo(at.x, at.y - 8); context.lineTo(at.x, at.y + 8);
        context.stroke();
        context.strokeStyle = "rgba(255,246,174,.45)";
        context.beginPath();
        context.arc(at.x, at.y, 11, 0, Math.PI * 2);
        context.stroke();
    }
    const barW = Math.max(28, 48 / desMapZoom);
    context.strokeStyle = "rgba(255,255,255,.88)";
    context.fillStyle = "rgba(255,255,255,.88)";
    context.lineWidth = 1.2;
    context.beginPath();
    context.moveTo(left + side - 12 - barW, top + side - 10);
    context.lineTo(left + side - 12, top + side - 10);
    context.moveTo(left + side - 12 - barW, top + side - 13);
    context.lineTo(left + side - 12 - barW, top + side - 7);
    context.moveTo(left + side - 12, top + side - 13);
    context.lineTo(left + side - 12, top + side - 7);
    context.stroke();
    context.font = "9px Segoe UI, Arial";
    context.textAlign = "right";
    context.fillText(Math.max(1, Math.round(22 / desMapZoom)) + " km", left + side - 12, top + side - 14);
    context.restore();
    context.strokeStyle = "rgba(122,244,255,.35)";
    context.lineWidth = 1;
    context.strokeRect(left + 0.5, top + 0.5, side - 1, side - 1);
    const swatch = document.getElementById("des-map-swatch");
    if (swatch) swatch.classList.toggle("slope", mode === "slope");
    const legend = document.getElementById("des-map-legend");
    if (legend) {
        const labels = legend.querySelectorAll("span");
        if (labels.length >= 2) {
            labels[0].textContent = mode === "slope" ? "Flat" : "Low";
            labels[1].textContent = mode === "slope" ? "Steep" : "High";
        }
    }
    const setMapStat = (id, text) => {
        const node = document.getElementById(id);
        if (node) node.textContent = text;
    };
    setMapStat("des-map-pad-slope", pad ? pad.slope.toFixed(1) + "°" : "—");
    setMapStat("des-map-zoom", desMapZoom.toFixed(1) + "×");
    if (desMapInspect) {
        const h = siteSurfaceHeight(desMapInspect.x, desMapInspect.z);
        const s = slopeAtMap(desMapInspect.x, desMapInspect.z);
        setMapStat("des-map-inspect", (h * 1000).toFixed(0) + " m · " + s.toFixed(0) + "°");
    } else {
        setMapStat("des-map-inspect", "click map");
    }
}
function paintDescent() {
    const board = document.getElementById("descent-board");
    if (!board || board.hidden) return;
    const facts = siteFacts();
    const keep = plumeKeepout();
    const water = waterPlan(facts);
    const ice = iceProspect(facts);
    const pad = likelyPad(facts);
    const mission = document.getElementById("des-mission");
    if (mission) mission.textContent = facts.place.toUpperCase();
    const open = Boolean(facts.cleared && facts.bad === 0 && facts.heights.length);
    const vehicleId = document.getElementById("plan-vehicle").value;
    const settleTable = {sls: 72, lvm3: 64, falcon9: 68, longmarch5: 74, h3: 60};
    const settle = settleTable[vehicleId] || 66;
    const thrustPct = facts.heights.length ? Math.max(48, Math.min(88, settle + (open ? 4 : -6))) : 0;
    const batteryPct = facts.batteryH == null ? 0 : Math.max(0, Math.min(1, Number(facts.batteryH) / 24));
    const padMeters = pad ? Math.round(pad.elev * 1000) : null;
    drawThrustGauge(document.getElementById("des-g-thrust"), thrustPct / 100, facts.heights.length ? thrustPct + "%" : "—");
    drawVelocityGauge(document.getElementById("des-g-velocity"), Boolean(facts.heights.length));
    drawAltitudeGauge(document.getElementById("des-g-altitude"), padMeters);
    drawFuelGauge(document.getElementById("des-g-fuel"), batteryPct, facts.batteryH == null ? "—" : Math.round(batteryPct * 100) + "%");
    const safeCall = document.getElementById("des-safe-call");
    const safeNote = document.getElementById("des-safe-note");
    if (safeCall) {
        safeCall.textContent = !facts.heights.length ? "—" : open ? "OPTIMAL" : "HOLD";
        safeCall.className = open ? "" : "hold";
    }
    if (safeNote) safeNote.textContent = !facts.heights.length ? "Landing area" : open ? "Landing area: optimal" : "Landing area: over the climb limit";
    drawDescentStage(facts, pad);
    drawDescentPlume(keep);
    drawDescentMap(facts, ice, pad);
    const rate = document.getElementById("des-water-rate");
    if (rate) rate.innerHTML = water.perDay + " <span>L/day</span>";
    const total = document.getElementById("des-water-total");
    if (total) total.textContent = "Total: " + (water.stock ? water.stock.toLocaleString() + " L" : "0 L");
    const fill = document.getElementById("des-water-fill");
    if (fill) fill.style.height = Math.round(water.fill * 100) + "%";
    const note = document.getElementById("des-water-note");
    if (note) note.textContent = water.note;
    const iceNode = document.getElementById("des-ice");
    if (iceNode) iceNode.innerHTML = "<b>ICE PROSPECT · " + ice.title + "</b> " + ice.detail;
    const status = document.getElementById("des-status");
    const chip = document.getElementById("des-status-chip");
    if (status) {
        const padM = padMeters == null ? "" : " – " + padMeters + " m";
        status.textContent = !facts.heights.length
            ? "WAITING ON THE PATH"
            : open
                ? ("TOUCHDOWN CONFIRMED! " + facts.place + padM)
                : "REVIEW REQUIRED";
    }
    if (chip) chip.className = "des-chip " + (open ? "go" : facts.heights.length ? "stop" : "");
    const week = document.getElementById("des-water-foot");
    if (week) week.textContent = water.stock ? water.stock.toLocaleString() + " L" : "0 L";
    const cargo = document.getElementById("des-power-foot");
    if (cargo) cargo.textContent = !facts.heights.length ? "—" : Math.min(100, baseKit().length * 25) + "%";
    const missionFoot = document.getElementById("des-mission-foot");
    const missionChip = document.getElementById("des-mission-chip");
    if (missionFoot) missionFoot.textContent = facts.storm ? "STORM WATCH" : open ? "SUCCESS" : "REVIEW";
    if (missionChip) missionChip.className = "des-chip " + (facts.storm ? "stop" : open ? "go" : "");
    const setDesHud = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
    setDesHud("des-hud-name", facts.place);
    setDesHud("des-hud-elev", padMeters == null ? "—" : padMeters + " m");
    setDesHud("des-hud-slope", pad ? pad.slope.toFixed(1) + "°" : "—");
    setDesHud("des-hud-plume", keep.safe + " / " + keep.dust + " m");
    setDesHud("des-hud-ice", ice.title);
    setDesHud("des-hud-batt", facts.batteryH == null ? "—" : Math.round(batteryPct * 100) + "%");
    const lolaBadge = document.getElementById("des-lola-badge");
    if (lolaBadge) lolaBadge.textContent = lolaHeightField ? "LOLA DEM · LIVE" : "LOLA DEM · waiting";
    const caption = document.getElementById("des-caption");
    if (caption) caption.textContent = (lolaHeightField ? "Selected crater DEM · " : "Waiting on DEM · ") + keep.safe + " m safe radius, " + keep.dust + " m dust zone · pad checks from LOLA route.";
}

function paintOpsBoard() {
    const board = document.getElementById("ops-board");
    if (!board) return;
    const site = document.getElementById("plan-destination");
    const vehicle = document.getElementById("plan-vehicle").selectedOptions[0].textContent;
    const pad = document.getElementById("plan-pad").selectedOptions[0].textContent;
    const place = site.selectedOptions[0].dataset.name;
    const pair = site.value.split(",").map(Number);
    document.getElementById("ops-subtitle").textContent = vehicle + "  //  " + place.toUpperCase();
    const elapsed = Date.now() - opsStarted;
    const total = Math.floor(elapsed / 1000);
    const pad2 = n => String(n).padStart(2, "0");
    document.getElementById("ops-met").textContent =
        pad2(Math.floor(total / 86400)) + "d " + pad2(Math.floor((total % 86400) / 3600)) + "h " +
        pad2(Math.floor((total % 3600) / 60)) + "m " + pad2(total % 60) + "s";
    const cleared = Boolean(opsTerrain && opsTerrain.route_available);
    const km = opsTerrain ? (cleared ? opsTerrain.route_distance_km : opsTerrain.advisory_distance_km) : null;
    const slopes = opsTerrain ? ((cleared ? opsTerrain.route_slope_degrees : opsTerrain.advisory_route_slope_degrees) || []) : [];
    const heights = opsTerrain ? ((cleared ? opsTerrain.route_elevation_km : opsTerrain.advisory_route_elevation_km) || []) : [];
    const earth = opsPlan && opsPlan.telemetry ? opsPlan.telemetry.min_earth_elevation_degrees : null;
    const power = opsPlan && opsPlan.power ? opsPlan.power.peak_tilt_w : null;
    const sheltered = document.getElementById("brief-shelter").value === "yes";
    const goes = (document.getElementById("solar-current").textContent || "").trim();
    const storm = /^(M|X)/.test(goes);
    const setLight = (id, text, kind) => {
        document.getElementById(id.replace("ops-", "ops-dot-")).className = kind || "";
        document.getElementById(id).textContent = text;
    };
    const night = opsPlan && opsPlan.power ? opsPlan.power.night_days : null;
    const telemetry = opsPlan && opsPlan.telemetry ? opsPlan.telemetry : {};
    const batteryH = telemetry.battery_hours;
    const dose = telemetry.dose_msv;
    const sunUp = telemetry.sun_up;
    const speed = Number(document.getElementById("planning_speed_kmh").value) || 0;
    const limit = Number(document.getElementById("max_slope_degrees").value) || 18;
    const craftName = vehicle.split("·")[0].trim();
    const region = Math.abs(pair[0]) >= 80
        ? (pair[0] < 0 ? "LUNAR SOUTH POLE" : "LUNAR NORTH POLE")
        : (Math.abs(pair[0]) >= 30 ? (pair[0] < 0 ? "SOUTHERN LATITUDES" : "NORTHERN LATITUDES") : "EQUATORIAL REGION");
    document.getElementById("ops-subtitle").textContent = place.toUpperCase() + "  //  " + craftName;
    setLight("ops-comms", earth == null ? "WAIT" : earth >= 5 ? "STABLE" : "LOW", earth == null || earth < 5 ? "warn" : "");
    setLight("ops-guide", opsTerrain ? (cleared ? "ACTIVE" : "HOLD") : "IDLE", opsTerrain && !cleared ? "warn" : "");
    setLight("ops-prop", km != null && speed > 0 ? "ON" : "OFF", km != null && speed > 0 ? "" : "warn");
    setLight("ops-sys", storm ? "WATCH" : (opsPlan || opsTerrain) ? "GO" : "QUIET", storm ? "bad" : "");
    ensureMoonDisk(pair[0], pair[1]);
    const lowAlt = heights.length ? Math.min.apply(null, heights) : null;
    const highAlt = heights.length ? Math.max.apply(null, heights) : null;
    const midAlt = heights.length ? Number(heights[Math.floor((heights.length - 1) / 2)]) : null;
    drawOpsArc(place, craftName, region, midAlt, speed);
    drawPathfinder(place, vehicle, pair, km, cleared);
    const thrustPct = speed > 0 ? Math.max(0, Math.min(1, speed / 5)) : 0;
    const fuelPct = batteryH == null ? 0 : Math.max(0, Math.min(1, Number(batteryH) / 24));
    const powerPct = power == null ? 0 : Math.max(0, Math.min(1, power / 2200));
    const lifeOk = !storm && (earth == null || earth >= 0);
    const lifeText = (opsPlan || opsTerrain) ? (lifeOk ? "NOMINAL" : "WATCH") : "—";
    const slopeNums = slopes.map(Number).filter(Number.isFinite);
    const maxSlope = slopeNums.length ? Math.max.apply(null, slopeNums) : null;
    const margin = maxSlope == null ? 0 : Math.max(0, Math.min(1, (limit - maxSlope) / Math.max(limit, 1)));
    opsGauge(document.getElementById("ops-g-path"), margin, maxSlope == null ? "—" : maxSlope.toFixed(0) + "°", "STEEPEST", margin > 0.15 ? "#3ddea0" : "#ff8a90");
    opsGauge(document.getElementById("ops-g-earth"), fuelPct, batteryH == null ? "—" : Math.round(Number(batteryH)) + " h", "BATTERY", "#e6c84a");
    opsGauge(document.getElementById("ops-g-power"), powerPct, power == null ? "—" : Math.round(power) + " W", "ARRAY", "#3ddea0");
    opsGauge(document.getElementById("ops-g-shelter"), lifeText === "—" ? 0 : (lifeOk ? 0.92 : 0.38), lifeText, sheltered ? "SHELTER" : "EXPOSED", lifeOk ? "#3ddea0" : "#e6c84a");
    const reliefM = lowAlt == null || highAlt == null ? null : (highAlt - lowAlt) * 1000;
    const figure = (label, value) => "<div><span>" + label + "</span><strong>" + value + "</strong></div>";
    document.getElementById("ops-figures").innerHTML =
        figure("CLIMB", reliefM == null ? "—" : Math.round(reliefM) + " m") +
        figure("EARTH", earth == null ? "—" : Number(earth).toFixed(1) + "°") +
        figure("LATITUDE", Math.abs(pair[0]).toFixed(1) + "°");
    opsSeries(document.getElementById("ops-alt"), heights, "#3ee0f0", "ELEVATION", "km", [{t: 0.08, text: "START"}, {t: 0.5, text: "MID"}, {t: 0.92, text: "END"}]);
    opsSeries(document.getElementById("ops-slope"), slopeNums, "#ffb15a", "SLOPE", "°", [], limit);
    const call = siteProsCons();
    const pros = document.getElementById("ops-pros");
    const cons = document.getElementById("ops-cons");
    if (pros) pros.innerHTML = call.pros.map(line => "<li>" + line + "</li>").join("");
    if (cons) cons.innerHTML = call.cons.map(line => "<li>" + line + "</li>").join("");
    const opsPurpose = document.getElementById("ops-purpose");
    if (opsPurpose) opsPurpose.innerHTML = "<b>DECIDE THE SITE</b> " + optionLine() + ".";
    const pathPurpose = document.getElementById("path-purpose");
    if (pathPurpose) pathPurpose.innerHTML = "<b>CAN THE CREW WALK IT</b> " + optionLine() + ".";
    const topoPurpose = document.getElementById("topo-purpose");
    if (topoPurpose) topoPurpose.innerHTML = "<b>SEE THE GROUND</b> Climb limit " + limit + "°. " + optionLine() + ".";
    void thrustPct;
    paintHabitat();
    paintDescent();
}
function ensureMoonDisk(lat, lon) {
    const key = Number(lat).toFixed(2) + "|" + Number(lon).toFixed(2);
    if (key === moonDiskKey) return;
    moonDiskKey = key;
    moonDisk = null;
    const image = new Image();
    image.onload = () => {
        if (moonDiskKey !== key) return;
        moonDisk = image;
        paintOpsBoard();
    };
    image.src = "/api/moon-disk.jpg?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon);
}
function drawOpsArc(place, craftName, region, altitude, speed) {
    const arc = opsFit(document.getElementById("ops-arc"));
    if (!arc) return;
    const {context, width, height} = arc;
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#061018";
    context.fillRect(0, 0, width, height);
    const moonR = Math.min(width * 0.34, height * 0.46);
    const moonX = width - moonR * 0.72;
    const moonY = height * 0.48;
    context.save();
    context.beginPath();
    context.arc(moonX, moonY, moonR, 0, Math.PI * 2);
    context.clip();
    if (moonDisk && moonDisk.naturalWidth) {
        context.drawImage(moonDisk, moonX - moonR, moonY - moonR, moonR * 2, moonR * 2);
    } else {
        context.fillStyle = "#101820";
        context.fillRect(moonX - moonR, moonY - moonR, moonR * 2, moonR * 2);
        context.fillStyle = "#8fd8df";
        context.font = "12px Segoe UI, Arial";
        context.textAlign = "center";
        context.fillText("LROC", moonX, moonY);
    }
    context.restore();
    context.beginPath();
    context.arc(moonX, moonY, moonR, 0, Math.PI * 2);
    context.strokeStyle = "#d5dde4";
    context.lineWidth = 1.5;
    context.stroke();
    const x0 = 28;
    const y0 = height * 0.76;
    const bendX = width * 0.36;
    const bendY = Math.max(18, height * 0.14);
    const bez = t => {
        const u = 1 - t;
        return {
            x: u * u * x0 + 2 * u * t * bendX + t * t * moonX,
            y: u * u * y0 + 2 * u * t * bendY + t * t * moonY
        };
    };
    let limbT = 0.72;
    for (let step = 0; step <= 48; step += 1) {
        const t = step / 48;
        const at = bez(t);
        if (Math.hypot(at.x - moonX, at.y - moonY) <= moonR * 0.86) {
            limbT = Math.max(0.2, t);
            break;
        }
    }
    const gradient = context.createLinearGradient(x0, y0, moonX, moonY);
    gradient.addColorStop(0, "#3ee0f0");
    gradient.addColorStop(0.45, "#3ddea0");
    gradient.addColorStop(0.75, "#e6c84a");
    gradient.addColorStop(1, "#ff5a62");
    context.strokeStyle = gradient;
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 12;
    context.lineWidth = 8;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    for (let step = 0; step <= 40; step += 1) {
        const at = bez(limbT * step / 40);
        if (step) context.lineTo(at.x, at.y);
        else context.moveTo(at.x, at.y);
    }
    context.stroke();
    context.shadowBlur = 0;
    const limb = bez(limbT);
    const aimX = limb.x - moonX;
    const aimY = limb.y - moonY;
    const aim = Math.hypot(aimX, aimY) || 1;
    context.strokeStyle = "#e6c36a";
    context.lineWidth = 1.5;
    context.beginPath();
    context.moveTo(limb.x, limb.y);
    context.lineTo(moonX + aimX / aim * 26, moonY + aimY / aim * 26);
    context.stroke();
    const craftAt = (t, label) => {
        const at = bez(Math.min(t, limbT * 0.92));
        context.save();
        context.translate(at.x, at.y);
        context.fillStyle = "#f4fbff";
        context.strokeStyle = "#9af6ff";
        context.lineWidth = 1.4;
        context.beginPath();
        context.moveTo(8, 0);
        context.lineTo(-6, 5);
        context.lineTo(-3, 0);
        context.lineTo(-6, -5);
        context.closePath();
        context.fill();
        context.stroke();
        context.restore();
        context.fillStyle = "#e6c36a";
        context.font = "12px Segoe UI, Arial";
        context.textAlign = "center";
        context.shadowColor = "#000";
        context.shadowBlur = 4;
        context.fillText(label, at.x, at.y + (t < 0.2 ? 22 : -16));
        context.shadowBlur = 0;
    };
    craftAt(0.08, "NRHO GATEWAY");
    craftAt(limbT * 0.42, craftName.toUpperCase());
    context.strokeStyle = "#e6c36a";
    context.shadowColor = "#000";
    context.shadowBlur = 4;
    context.lineWidth = 1.6;
    [7, 14, 22].forEach(ring => {
        context.beginPath();
        context.arc(moonX, moonY, ring, 0, Math.PI * 2);
        context.stroke();
    });
    context.fillStyle = "#e6c36a";
    context.beginPath();
    context.arc(moonX, moonY, 3, 0, Math.PI * 2);
    context.fill();
    const name = place.toUpperCase();
    const rows = [
        {font: "bold 12px Segoe UI, Arial", text: name},
        {font: "11px Segoe UI, Arial", text: region},
        {font: "11px Segoe UI, Arial", text: "TARGET:"},
        {font: "bold 12px Segoe UI, Arial", text: name}
    ];
    let widest = 0;
    rows.forEach(row => {
        context.font = row.font;
        widest = Math.max(widest, context.measureText(row.text).width);
    });
    const leading = 16;
    let labelX = moonX + 10;
    if (labelX + widest > width - 8) labelX = width - 8 - widest;
    const labelTop = Math.max(moonY - moonR + 22, moonY - 74);
    context.fillStyle = "rgba(4, 10, 16, 0.62)";
    context.fillRect(labelX - 6, labelTop - 13, widest + 12, rows.length * leading + 6);
    context.fillStyle = "#e6c36a";
    context.textAlign = "left";
    rows.forEach((row, index) => {
        context.font = row.font;
        context.fillText(row.text, labelX, labelTop + index * leading);
    });
    context.shadowBlur = 0;
    const call = bez(Math.min(0.62, limbT * 0.78));
    context.textAlign = "left";
    context.fillStyle = "#f4fbff";
    context.font = "13px Segoe UI, Arial";
    context.shadowColor = "#000";
    context.shadowBlur = 4;
    const callX = Math.max(16, Math.min(call.x - 20, moonX - moonR - 8));
    const callY = Math.max(32, call.y - 26);
    context.fillText("ALTITUDE: " + (altitude == null ? "—" : Number(altitude).toFixed(2) + " km"), callX, callY);
    context.fillText("VELOCITY: " + (speed > 0 ? speed + " km/h" : "—"), callX, callY + 16);
    context.shadowBlur = 0;
}
function localProject(lat, lon, lat0, lon0) {
    const rad = Math.PI / 180;
    const p = lat0 * rad;
    const l = lon0 * rad;
    const center = [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)];
    const east = [-Math.sin(l), Math.cos(l), 0];
    const north = [
        center[1] * east[2] - center[2] * east[1],
        center[2] * east[0] - center[0] * east[2],
        center[0] * east[1] - center[1] * east[0]
    ];
    const point = [Math.cos(lat * rad) * Math.cos(lon * rad), Math.cos(lat * rad) * Math.sin(lon * rad), Math.sin(lat * rad)];
    const dot = center[0] * point[0] + center[1] * point[1] + center[2] * point[2];
    const tangent = [point[0] - dot * center[0], point[1] - dot * center[1], point[2] - dot * center[2]];
    const length = Math.hypot(tangent[0], tangent[1], tangent[2]);
    if (!length) return {e: 0, n: 0};
    const distance = Math.acos(Math.max(-1, Math.min(1, dot))) * 1737.4;
    return {
        e: (tangent[0] * east[0] + tangent[1] * east[1] + tangent[2] * east[2]) / length * distance,
        n: (tangent[0] * north[0] + tangent[1] * north[1] + tangent[2] * north[2]) / length * distance
    };
}
function ensurePathPhoto(lat, lon, radius) {
    const key = lat.toFixed(3) + "|" + lon.toFixed(3) + "|" + radius;
    if (key === pathPhotoKey) return;
    pathPhotoKey = key;
    pathPhoto = null;
    const image = new Image();
    image.onload = () => {
        if (pathPhotoKey !== key) return;
        pathPhoto = image;
        paintOpsBoard();
    };
    image.src = "/api/path-basemap.jpg?lat=" + lat + "&lon=" + lon + "&radius=" + radius;
}
function drawPathfinder(place, vehicle, pair, km, cleared) {
    const canvas = document.getElementById("path-map");
    const route = opsTerrain ? ((cleared ? opsTerrain.route : opsTerrain.advisory_route) || []) : [];
    const limit = Number(document.getElementById("max_slope_degrees").value) || 18;
    const routeSlopes = opsTerrain ? ((cleared ? opsTerrain.route_slope_degrees : opsTerrain.advisory_route_slope_degrees) || []) : [];
    let goodSteps = 0;
    let nearSteps = 0;
    let badSteps = 0;
    routeSlopes.forEach(value => {
        const slope = Number(value);
        if (!Number.isFinite(slope)) return;
        if (slope >= limit) badSteps += 1;
        else if (slope >= limit - 3) nearSteps += 1;
        else goodSteps += 1;
    });
    const walkLabel = !opsTerrain ? "WAITING" : (cleared && badSteps === 0 ? "GOOD WALK" : "NOT CLEARED");
    const walkClass = !opsTerrain ? "path-gold" : walkLabel === "GOOD WALK" ? "path-go" : "path-red";
    const speed = Number(document.getElementById("planning_speed_kmh").value) || 0;
    const point = item => Array.isArray(item) ? {lat: Number(item[0]), lon: Number(item[1])} : {lat: Number(item.lat), lon: Number(item.lon)};
    const hours = opsPlan && opsPlan.telemetry ? opsPlan.telemetry.battery_hours : null;
    const eta = km != null && speed > 0 ? (Number(km) / speed) * 60 : null;
    const site = document.getElementById("plan-destination").selectedOptions[0];
    const diameter = Number(site && site.dataset.diameter) || (Math.abs(pair[0]) > 85 ? 21 : 32);
    const craterR = diameter / 2;
    const locLat = Number(document.getElementById("start_lat").value);
    const locLon = Number(document.getElementById("start_lon").value);
    const batteryPct = hours == null ? null : Math.max(0, Math.min(100, Math.round(Number(hours) / 24 * 100)));
    const projectKm = (lat, lon) => localProject(lat, lon, pair[0], pair[1]);
    const routeKm = route.map(item => {
        const at = point(item);
        return projectKm(at.lat, at.lon);
    });
    const routeRadiusKm = routeKm.reduce((radius, at) => Math.max(radius, Math.hypot(at.e, at.n)), 0);
    const radiusKm = Math.min(80, Math.max(12, craterR * 1.05, routeRadiusKm * 1.15 + 1.5));
    const nearRoute = (east, north, gap) => {
        if (routeKm.length < 2) return false;
        for (let index = 1; index < routeKm.length; index += 1) {
            const a = routeKm[index - 1];
            const b = routeKm[index];
            const abe = b.e - a.e;
            const abn = b.n - a.n;
            const len2 = abe * abe + abn * abn || 1;
            let t = ((east - a.e) * abe + (north - a.n) * abn) / len2;
            t = Math.max(0, Math.min(1, t));
            if (Math.hypot(a.e + abe * t - east, a.n + abn * t - north) < gap) return true;
        }
        return false;
    };
    const pool = ((opsTerrain && opsTerrain.hazards) || [])
        .filter(item => Number(item.slope) >= limit)
        .map(item => ({slope: Number(item.slope), km: projectKm(item.lat, item.lon)}))
        .filter(item => Math.hypot(item.km.e, item.km.n) <= radiusKm * 0.98 && !nearRoute(item.km.e, item.km.n, 1.8))
        .sort((a, b) => b.slope - a.slope);
    const kept = [];
    const sep = Math.max(2.4, craterR * 0.22);
    pool.forEach(item => {
        if (kept.length >= 14) return;
        if (kept.every(other => Math.hypot(other.km.e - item.km.e, other.km.n - item.km.n) >= sep)) kept.push(item);
    });
    const etaText = eta == null ? "—" : (eta > 180 ? (eta / 60).toFixed(1) + "h" : Math.round(eta) + "m");
    const who = briefingState().asset === "crew" ? "CREW WALK" : briefingState().asset === "both" ? "CREW + HABITAT" : "HABITAT MOVE";
    const metrics = (opsTerrain && (opsTerrain.route_metrics || (opsTerrain.route_assessment && opsTerrain.route_assessment.multi_objective))) || {};
    const variants = (opsTerrain && opsTerrain.route_variants) || [];
    const priority = (opsTerrain && opsTerrain.path_priority) || ((document.getElementById("brief-priority") || {}).value) || "slope";
    const priorityLabel = priority === "sun" || priority === "sunlight" || priority === "power" ? "SOLAR-FIRST"
        : priority === "ice" || priority === "cold" || priority === "water" ? "ICE-FIRST"
        : priority === "radio" || priority === "earth" || priority === "comms" ? "EARTH-RADIO"
        : "SLOPE-FIRST";
    const pct = value => value == null ? "—" : Math.round(Number(value) * 100) + "%";
    const leftStatus = [
        "<p>Mission Status: <strong class='" + walkClass + "'>" + (opsTerrain ? (cleared ? "ACTIVE" : "HOLD") : "STANDBY") + "</strong></p>",
        "<p>Vehicle: <strong>" + who + "</strong></p>",
        "<p>Battery: <strong>" + (batteryPct == null ? "—" : batteryPct + "%") + "</strong></p>",
        "<p>Location: <strong>" + (Number.isFinite(locLat) ? locLat.toFixed(2) : pair[0].toFixed(2)) + "°, " +
        (Number.isFinite(locLon) ? locLon.toFixed(1) : pair[1].toFixed(1)) + "°</strong></p>",
        "<p>Walk call: <strong class='" + walkClass + "'>" + walkLabel + "</strong></p>",
        "<p>A* objective: <strong class='path-gold'>" + priorityLabel + "</strong></p>",
        "<p>Solar score: <strong>" + pct(metrics.mean_sun) + "</strong> · Ice: <strong>" + pct(metrics.mean_ice) + "</strong></p>",
        "<p>Earth score: <strong>" + pct(metrics.mean_earth) + "</strong> · Climb: <strong>" + (metrics.climb_m == null ? "—" : metrics.climb_m + " m") + "</strong></p>"
    ].join("");
    const variantLines = variants.slice(0, 4).map(item => {
        const mark = item.selected ? "▸ " : "· ";
        const state = item.cleared ? "" : " (preview)";
        return "<p>" + mark + item.label + ": <strong>" + Number(item.distance_km).toFixed(1) + " km</strong>" + state + "</p>";
    }).join("");
    const rightStatus = [
        "<p>Target B: <strong>" + place.toUpperCase() + "</strong></p>",
        "<p>Dist to Go: <strong>" + (km != null ? Number(km).toFixed(1) + " km" : "—") + "</strong></p>",
        "<p>ETA: <strong>" + etaText + "</strong></p>",
        "<p>Mode: <strong class='" + (opsTerrain ? walkClass : "path-gold") + "'>" + (opsTerrain ? "MULTI-OBJECTIVE A*" : "WAITING FOR TERRAIN") + "</strong></p>",
        "<p>Sun band: <strong>" + (metrics.sun_km == null ? "—" : metrics.sun_km + " km") + "</strong> · Ice band: <strong>" + (metrics.ice_km == null ? "—" : metrics.ice_km + " km") + "</strong></p>",
        "<p>Hazardous Terrain Avoided: <strong>" + kept.length + " samples</strong></p>",
        "<p>Slope samples: <strong class='path-go'>" + goodSteps + " good</strong> · <strong class='path-gold'>" + nearSteps + " close</strong> · <strong class='path-red'>" + badSteps + " blocked</strong></p>",
        variantLines,
        "<p>View: <strong>" + (typeof pathView === "undefined" ? "1.0" : pathView.zoom.toFixed(2)) + "×</strong> · drag pan · wheel zoom · inspect</p>"
    ].join("");
    document.getElementById("path-status").innerHTML =
        "<h3>MISSION STATUS</h3>" + leftStatus;
    document.getElementById("path-nav").innerHTML =
        "<h3>NAVIGATION PANEL</h3>" + rightStatus;
    void vehicle;
    ensurePathPhoto(pair[0], pair[1], radiusKm);
    const fit = canvas ? opsFit(canvas) : null;
    if (!fit) return;
    const {context, width, height} = fit;
    let minE = Infinity;
    let maxE = -Infinity;
    let minN = Infinity;
    let maxN = -Infinity;
    routeKm.forEach(pointKm => {
        minE = Math.min(minE, pointKm.e);
        maxE = Math.max(maxE, pointKm.e);
        minN = Math.min(minN, pointKm.n);
        maxN = Math.max(maxN, pointKm.n);
    });
    if (!Number.isFinite(minE)) {
        minE = -6;
        maxE = 6;
        minN = -6;
        maxN = 6;
    }
    let midE = (minE + maxE) / 2;
    let midN = (minN + maxN) / 2;
    let halfE = Math.max(1.8, (maxE - minE) * 0.58);
    let halfN = Math.max(1.8, (maxN - minN) * 0.58);
    const aspect = width / Math.max(1, height);
    if (halfE / halfN < aspect) halfE = halfN * aspect;
    else halfN = halfE / aspect;
    halfE *= 1.12;
    halfN *= 1.12;
    if (typeof pathView !== "undefined") {
        halfE /= pathView.zoom;
        halfN /= pathView.zoom;
        midE += pathView.panE;
        midN += pathView.panN;
    }
    const vMinE = midE - halfE;
    const vMaxE = midE + halfE;
    const vMinN = midN - halfN;
    const vMaxN = midN + halfN;
    if (typeof pathView !== "undefined") {
        pathView.project = {
            vMinE, vMaxE, vMinN, vMaxN,
            kmPerPx: (vMaxE - vMinE) / Math.max(1, width),
            samples: kept.map(item => ({e: item.km.e, n: item.km.n, slope: item.slope}))
        };
    }
    context.fillStyle = "#23241f";
    context.fillRect(0, 0, width, height);
    const wash = context.createRadialGradient(width / 2, height / 2, 30, width / 2, height / 2, Math.max(width, height) * 0.72);
    wash.addColorStop(0, "#3c3d36");
    wash.addColorStop(1, "#161714");
    context.fillStyle = wash;
    context.fillRect(0, 0, width, height);
    if (pathPhoto && pathPhoto.width) {
        const full = 2 * radiusKm;
        const sx0 = (vMinE + radiusKm) / full * pathPhoto.width;
        const sy0 = (radiusKm - vMaxN) / full * pathPhoto.height;
        const sw0 = (vMaxE - vMinE) / full * pathPhoto.width;
        const sh0 = (vMaxN - vMinN) / full * pathPhoto.height;
        const sx = Math.max(0, sx0);
        const sy = Math.max(0, sy0);
        const sx2 = Math.min(pathPhoto.width, sx0 + sw0);
        const sy2 = Math.min(pathPhoto.height, sy0 + sh0);
        if (sx2 > sx && sy2 > sy && sw0 > 0 && sh0 > 0) {
            context.drawImage(
                pathPhoto,
                sx, sy, sx2 - sx, sy2 - sy,
                (sx - sx0) / sw0 * width,
                (sy - sy0) / sh0 * height,
                (sx2 - sx) / sw0 * width,
                (sy2 - sy) / sh0 * height
            );
        }
    }
    const vignette = context.createRadialGradient(width / 2, height / 2, Math.min(width, height) * 0.42, width / 2, height / 2, Math.max(width, height) * 0.72);
    vignette.addColorStop(0, "rgba(0,0,0,0)");
    vignette.addColorStop(1, "rgba(0,0,0,.22)");
    context.fillStyle = vignette;
    context.fillRect(0, 0, width, height);
    const toXY = (east, north) => ({
        x: (east - vMinE) / (vMaxE - vMinE) * width,
        y: (vMaxN - north) / (vMaxN - vMinN) * height
    });
    const inside = at => at.x > -30 && at.y > -30 && at.x < width + 30 && at.y < height + 30;
    const layersOn = typeof pathView === "undefined"
        ? {route: true, variants: true, hazard: true, waypoints: true, profile: true, grid: true, labels: true}
        : pathView.layers;
    if (layersOn.variants && variants.length) {
        const colors = {slope: "rgba(180,200,210,.45)", sun: "rgba(240,200,80,.55)", ice: "rgba(90,210,255,.55)", radio: "rgba(180,140,255,.5)"};
        variants.forEach(item => {
            if (item.selected) return;
            const pts = (item.route || []).map(entry => {
                const at = point(entry);
                return toXY(projectKm(at.lat, at.lon).e, projectKm(at.lat, at.lon).n);
            });
            if (pts.length < 2) return;
            context.beginPath();
            pts.forEach((at, index) => index ? context.lineTo(at.x, at.y) : context.moveTo(at.x, at.y));
            context.strokeStyle = colors[item.id] || "rgba(200,200,200,.4)";
            context.lineWidth = 1.6;
            context.setLineDash([5, 5]);
            context.stroke();
            context.setLineDash([]);
        });
    }
    kept.forEach(item => { item.at = toXY(item.km.e, item.km.n); });
    if (layersOn.hazard) kept.filter(item => inside(item.at)).slice(0, 6).forEach((item, index) => {
        context.beginPath();
        context.arc(item.at.x, item.at.y, 6, 0, Math.PI * 2);
        context.fillStyle = "rgba(255, 59, 69, .82)";
        context.fill();
        context.lineWidth = 1.2;
        context.strokeStyle = "#ffd5d8";
        context.stroke();
        if (layersOn.labels) {
            const labelX = Math.min(width - 120, Math.max(12, item.at.x + 12));
            const labelY = Math.max(24, Math.min(height - 24, item.at.y - 10));
            context.fillStyle = "rgba(255, 79, 89, 0.12)";
            context.beginPath();
            context.moveTo(item.at.x, item.at.y);
            context.lineTo(labelX, labelY + 8);
            context.lineTo(labelX + 18, labelY + 8);
            context.closePath();
            context.fill();
            context.fillStyle = "#ff5f6d";
            context.font = "700 12px Rajdhani, Segoe UI, Arial";
            context.textAlign = "left";
            context.fillText("HAZARD-" + String(index + 1).padStart(2, "0") + " · SLOPE ≥ " + limit.toFixed(0) + "°", labelX + 20, labelY + 12);
        }
    });
    const smooth = routeKm.map(pointKm => toXY(pointKm.e, pointKm.n));
    if (layersOn.route && smooth.length > 1) {
        context.lineJoin = "round";
        context.lineCap = "round";
        context.strokeStyle = "rgba(0,0,0,.7)";
        context.lineWidth = 7;
        context.beginPath();
        smooth.forEach((at, index) => index ? context.lineTo(at.x, at.y) : context.moveTo(at.x, at.y));
        context.stroke();
        for (let index = 1; index < smooth.length; index += 1) {
            const slope = Number(routeSlopes[index] != null ? routeSlopes[index] : routeSlopes[index - 1]);
            const blocked = Number.isFinite(slope) && slope >= limit;
            const close = Number.isFinite(slope) && !blocked && slope >= limit - 3;
            context.beginPath();
            context.moveTo(smooth[index - 1].x, smooth[index - 1].y);
            context.lineTo(smooth[index].x, smooth[index].y);
            context.strokeStyle = blocked ? "#ff4d57" : close ? "#f0c14a" : "#39f08a";
            context.lineWidth = 3.4;
            context.stroke();
        }
    }
    const tag = (at, text, color, dy) => {
        if (!at || !layersOn.labels) return;
        context.font = "700 13px Rajdhani, Segoe UI, Arial";
        const box = context.measureText(text).width + 10;
        const x = Math.max(8, Math.min(width - box - 8, at.x + 8));
        const y = Math.max(16, Math.min(height - 46, at.y + (dy || -12)));
        context.fillStyle = "rgba(4,10,16,.84)";
        context.fillRect(x - 4, y - 13, box, 18);
        context.fillStyle = color;
        context.textAlign = "left";
        context.fillText(text, x, y);
    };
    const start = smooth.length ? smooth[0] : null;
    const end = smooth.length ? smooth[smooth.length - 1] : null;
    if (layersOn.route && start) {
        context.fillStyle = "#f0d078";
        context.beginPath();
        context.arc(start.x, start.y, 6, 0, Math.PI * 2);
        context.fill();
        tag(start, "START POINT A", "#7eefff", -18);
    }
    if (layersOn.route && end) {
        context.fillStyle = "#7eefff";
        context.beginPath();
        context.arc(end.x, end.y, 6, 0, Math.PI * 2);
        context.fill();
        tag(end, "END POINT B", "#7eefff", 18);
    }
    if (layersOn.route && smooth.length > 1) {
        const mid = smooth[Math.floor(smooth.length / 2)];
        tag(mid, walkLabel, walkLabel === "GOOD WALK" ? "#39f08a" : "#ffb15a", -28);
    }
    const craterCenter = toXY(0, 0);
    const craterRadiusX = craterR / Math.max(0.001, vMaxE - vMinE) * width;
    const craterRadiusY = craterR / Math.max(0.001, vMaxN - vMinN) * height;
    context.save();
    context.beginPath();
    context.ellipse(craterCenter.x, craterCenter.y, craterRadiusX, craterRadiusY, 0, 0, Math.PI * 2);
    context.fillStyle = "rgba(90,196,202,.055)";
    context.fill();
    context.setLineDash([7, 6]);
    context.strokeStyle = "rgba(153,219,220,.62)";
    context.lineWidth = 1.4;
    context.stroke();
    context.setLineDash([]);
    if (layersOn.labels) {
        context.fillStyle = "rgba(231,247,255,.9)";
        context.font = "700 12px Rajdhani, Segoe UI, Arial";
        context.textAlign = "center";
        context.fillText(place.toUpperCase() + " · " + diameter + " KM", craterCenter.x, craterCenter.y);
    }
    context.restore();
    if (layersOn.grid) {
        context.save();
        context.strokeStyle = "rgba(220,237,245,.14)";
        context.fillStyle = "rgba(235,246,250,.72)";
        context.lineWidth = 1;
        context.font = "10px Rajdhani, Segoe UI, Arial";
        for (let index = 1; index < 8; index += 1) {
            const x = width * index / 8;
            context.beginPath();
            context.moveTo(x, 0);
            context.lineTo(x, height);
            context.stroke();
        }
        for (let index = 1; index < 6; index += 1) {
            const y = height * index / 6;
            context.beginPath();
            context.moveTo(0, y);
            context.lineTo(width, y);
            context.stroke();
        }
        context.textAlign = "left";
        context.fillText(Math.abs(pair[0]).toFixed(2) + "° " + (pair[0] < 0 ? "S" : "N"), 10, height - 12);
        context.textAlign = "right";
        context.fillText(Math.abs(pair[1]).toFixed(2) + "° " + (pair[1] < 0 ? "W" : "E"), width - 10, height - 12);
        context.restore();
    }
    if (layersOn.route) for (let index = 2; index < smooth.length; index += 5) {
        const a = smooth[index - 1];
        const b = smooth[index];
        const angle = Math.atan2(b.y - a.y, b.x - a.x);
        const x = (a.x + b.x) / 2;
        const y = (a.y + b.y) / 2;
        context.save();
        context.translate(x, y);
        context.rotate(angle);
        context.beginPath();
        context.moveTo(7, 0);
        context.lineTo(-5, -4);
        context.lineTo(-5, 4);
        context.closePath();
        context.fillStyle = "#b8ffd0";
        context.fill();
        context.restore();
    }
    if (layersOn.waypoints && metrics.waypoints) {
        metrics.waypoints.forEach(mark => {
            const at = point(mark);
            const xy = toXY(projectKm(at.lat, at.lon).e, projectKm(at.lat, at.lon).n);
            if (!inside(xy)) return;
            const solar = mark.kind === "solar_shoulder";
            context.beginPath();
            context.arc(xy.x, xy.y, 7, 0, Math.PI * 2);
            context.fillStyle = solar ? "#f0d078" : "#7eefff";
            context.fill();
            context.strokeStyle = "#041018";
            context.lineWidth = 1.4;
            context.stroke();
            tag(xy, solar ? "SOLAR SHOULDER" : "ICE APPROACH", solar ? "#f0d078" : "#7eefff", solar ? -22 : 22);
        });
    }
    if (layersOn.profile && routeKm.length > 1) {
        const heights = opsTerrain ? ((cleared ? opsTerrain.route_elevation_km : opsTerrain.advisory_route_elevation_km) || []) : [];
        const boxX = 12;
        const boxY = height - 92;
        const boxW = Math.min(220, width * 0.42);
        const boxH = 58;
        context.fillStyle = "rgba(4,10,16,.78)";
        context.fillRect(boxX, boxY, boxW, boxH);
        context.strokeStyle = "rgba(110,210,220,.55)";
        context.strokeRect(boxX + 0.5, boxY + 0.5, boxW - 1, boxH - 1);
        context.fillStyle = "#9ad7e2";
        context.font = "700 10px Rajdhani, Segoe UI, Arial";
        context.textAlign = "left";
        context.fillText("ELEVATION · SOLAR→ICE", boxX + 8, boxY + 12);
        if (heights.length > 1) {
            const nums = heights.map(Number).filter(Number.isFinite);
            const lo = Math.min.apply(null, nums);
            const hi = Math.max.apply(null, nums);
            const span = Math.max(0.001, hi - lo);
            context.beginPath();
            nums.forEach((value, index) => {
                const x = boxX + 8 + (boxW - 16) * index / Math.max(1, nums.length - 1);
                const y = boxY + boxH - 8 - (boxH - 24) * ((value - lo) / span);
                if (index) context.lineTo(x, y);
                else context.moveTo(x, y);
            });
            context.strokeStyle = "#5eebff";
            context.lineWidth = 1.8;
            context.stroke();
            context.fillStyle = "#d7f4ff";
            context.font = "10px Rajdhani, Segoe UI, Arial";
            context.fillText(lo.toFixed(2) + "–" + hi.toFixed(2) + " km", boxX + 8, boxY + boxH - 6);
        }
    }
    const pxPerKm = width / (vMaxE - vMinE);
    const barSteps = [0.5, 1, 2, 5, 10];
    const nice = barSteps.find(step => step * pxPerKm >= 70 && step * pxPerKm <= 160) || 5;
    const bar = nice * pxPerKm;
    const bx = width - bar - 24;
    const by = height - 56;
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(bx, by);
    context.lineTo(bx + bar, by);
    context.moveTo(bx, by - 5);
    context.lineTo(bx, by + 5);
    context.moveTo(bx + bar, by - 5);
    context.lineTo(bx + bar, by + 5);
    context.stroke();
    context.fillStyle = "#f4fbff";
    context.font = "600 12px Rajdhani, Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText((nice < 1 ? nice.toFixed(1) : String(nice)) + " km", bx, by - 8);
    context.save();
    context.translate(width / 2, 26);
    context.strokeStyle = "#e7f7ff";
    context.fillStyle = "#e7f7ff";
    context.lineWidth = 1.4;
    context.beginPath();
    context.arc(0, 0, 13, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.moveTo(0, -11);
    context.lineTo(4, 4);
    context.lineTo(0, 1);
    context.lineTo(-4, 4);
    context.closePath();
    context.fill();
    context.font = "700 11px Rajdhani, Segoe UI, Arial";
    context.textAlign = "center";
    context.fillText("N", 0, -18);
    context.restore();

}
setInterval(() => {
    const stamp = "UTC " + new Date().toISOString().slice(0, 19).replace("T", " ");
    const utc = document.getElementById("topo-utc");
    if (utc) utc.textContent = stamp;
    const habClock = document.getElementById("hab-clock");
    if (habClock && !document.getElementById("hab-board").hidden) {
        const now = new Date();
        const p = n => String(n).padStart(2, "0");
        habClock.textContent = p(now.getUTCHours()) + ":" + p(now.getUTCMinutes()) + ":" + p(now.getUTCSeconds()) + " UTC";
        const cycle = document.getElementById("hab-cycle");
        if (cycle) cycle.textContent = String(384 + Math.floor((Date.now() - habBoot) / 3200));
    }
    const desClock = document.getElementById("des-clock");
    if (desClock && !document.getElementById("descent-board").hidden) {
        const elapsed = Math.floor((Date.now() - opsStarted) / 1000);
        const p = n => String(n).padStart(2, "0");
        desClock.textContent = p(Math.floor(elapsed / 3600)) + ":" + p(Math.floor((elapsed % 3600) / 60)) + ":" + p(elapsed % 60);
    }
    const node = document.getElementById("ops-met");
    if (!node || document.getElementById("ops-board").closest("[hidden]")) return;
    const total = Math.floor((Date.now() - opsStarted) / 1000);
    const pad2 = n => String(n).padStart(2, "0");
    node.textContent = pad2(Math.floor(total / 86400)) + "d " + pad2(Math.floor((total % 86400) / 3600)) + "h " +
        pad2(Math.floor((total % 3600) / 60)) + "m " + pad2(total % 60) + "s";
}, 1000);
window.addEventListener("resize", () => {
    paintOpsBoard();
    paintDescent();
});
function openOptions(open) {
    const drawer = document.getElementById("options-drawer");
    const button = document.getElementById("open-options");
    if (!drawer) return;
    drawer.hidden = !open;
    if (button) button.setAttribute("aria-expanded", String(open));
}
function showScreen(name) {
    if (name === "questions") {
        openOptions(true);
        return;
    }
    document.querySelectorAll(".screen[data-screen]").forEach(node => {
        const on = node.dataset.screen === name;
        node.classList.toggle("is-on", on);
        node.hidden = !on;
    });
    document.querySelectorAll(".screen-nav button[data-screen]").forEach(button => {
        button.setAttribute("aria-pressed", String(button.dataset.screen === name));
    });
    const page = name === "habitat" ? "data" : "simulator";
    document.querySelectorAll(".app-tabs [role='tab']").forEach(tab => {
        tab.setAttribute("aria-selected", String(tab.dataset.page === page));
    });
    openOptions(false);
    setChromeOpen(false);
    requestAnimationFrame(() => {
        if (name === "habitat" && !habCraterView) {
            syncHabComponentGrid();
            habCraterView = createCraterView(document.getElementById("hab-crater"), "habitat");
            if (lolaHeightField) habCraterView.applyTerrain(lolaHeightField);
            habCraterView.resize();
        }
        if (name === "habitat") {
            syncHabComponentGrid();
            startBaseYard();
            if (habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
        }
        if (name === "habitat" && !habAnim) habAnim = requestAnimationFrame(tickHabitat);
        if (name === "descent" && descentThreeView) {
            if (lolaHeightField) descentThreeView.applyTerrain(lolaHeightField);
            descentThreeView.resize();
        }
        if (name === "ops" || name === "path" || name === "habitat" || name === "descent") paintOpsBoard();
        if (name === "terrain" && topoPayload) mountTopo(topoPayload);
        if (name === "descent") paintDescent();
        if (name === "clps") ensureClps(false);
    });
}
const chromeToggle = document.getElementById("chrome-toggle");
const chromePanel = document.getElementById("chrome-panel");
const chromeBackdrop = document.getElementById("chrome-backdrop");
function setChromeOpen(open) {
    if (!chromePanel || !chromeToggle) return;
    chromePanel.hidden = !open;
    if (chromeBackdrop) chromeBackdrop.hidden = !open;
    chromeToggle.setAttribute("aria-expanded", String(open));
}
if (chromeToggle) {
    chromeToggle.addEventListener("click", () => setChromeOpen(chromePanel.hidden));
}
if (chromeBackdrop) {
    chromeBackdrop.addEventListener("click", () => setChromeOpen(false));
}
document.querySelectorAll(".screen-nav button[data-screen]").forEach(button => {
    button.addEventListener("click", () => setChromeOpen(false));
});
const openOptionsBtn = document.getElementById("open-options");
if (openOptionsBtn) {
    openOptionsBtn.addEventListener("click", () => setChromeOpen(false));
}
document.addEventListener("keydown", event => {
    if (event.key === "Escape") setChromeOpen(false);
});

const pathView = {
    zoom: 1,
    panE: 0,
    panN: 0,
    layers: {route: true, variants: true, hazard: true, waypoints: true, profile: true, grid: true, labels: true},
    inspect: false,
    probe: null,
    dragging: false,
    moved: false,
    lastX: 0,
    lastY: 0,
    project: null
};
function pathLayerPressed() {
    document.querySelectorAll("[data-path-layer]").forEach(btn => {
        const key = btn.dataset.pathLayer;
        btn.setAttribute("aria-pressed", String(Boolean(pathView.layers[key])));
    });
    const inspectBtn = document.getElementById("path-inspect");
    if (inspectBtn) inspectBtn.setAttribute("aria-pressed", String(pathView.inspect));
}
document.querySelectorAll("[data-path-layer]").forEach(btn => {
    btn.addEventListener("click", () => {
        const key = btn.dataset.pathLayer;
        pathView.layers[key] = !pathView.layers[key];
        pathLayerPressed();
        paintOpsBoard();
    });
});
const pathZoomIn = document.getElementById("path-zoom-in");
const pathZoomOut = document.getElementById("path-zoom-out");
const pathReset = document.getElementById("path-zoom-reset");
const pathInspect = document.getElementById("path-inspect");
const pathClimb = document.getElementById("path-climb-live");
const pathClimbLabel = document.getElementById("path-climb-live-label");
if (pathZoomIn) pathZoomIn.addEventListener("click", () => { pathView.zoom = Math.min(4, pathView.zoom * 1.25); paintOpsBoard(); });
if (pathZoomOut) pathZoomOut.addEventListener("click", () => { pathView.zoom = Math.max(0.7, pathView.zoom / 1.25); paintOpsBoard(); });
if (pathReset) pathReset.addEventListener("click", () => {
    pathView.zoom = 1; pathView.panE = 0; pathView.panN = 0; pathView.probe = null;
    const probe = document.getElementById("path-probe");
    if (probe) probe.hidden = true;
    paintOpsBoard();
});
if (pathInspect) pathInspect.addEventListener("click", () => {
    pathView.inspect = !pathView.inspect;
    pathLayerPressed();
});
if (pathClimb) {
    pathClimb.value = String((document.getElementById("max_slope_degrees") || {}).value || 18);
    if (pathClimbLabel) pathClimbLabel.textContent = pathClimb.value + "°";
    pathClimb.addEventListener("input", () => {
        if (pathClimbLabel) pathClimbLabel.textContent = pathClimb.value + "°";
        paintOpsBoard();
    });
    pathClimb.addEventListener("change", () => {
        const slope = document.getElementById("max_slope_degrees");
        const brief = document.getElementById("brief-slope");
        if (slope) slope.value = pathClimb.value;
        if (brief) {
            brief.value = pathClimb.value;
            brief.dispatchEvent(new Event("input", {bubbles: true}));
        }
        if (pathClimbLabel) pathClimbLabel.textContent = pathClimb.value + "°";
        const briefLabel = document.getElementById("brief-slope-label");
        if (briefLabel) briefLabel.textContent = pathClimb.value + "°";
        loadTerrain();
    });
}
const pathReplan = document.getElementById("path-replan");
if (pathReplan) pathReplan.addEventListener("click", () => loadTerrain());
const pathMap = document.getElementById("path-map");
const pathWrap = document.querySelector(".path-map-wrap");
if (pathMap && pathWrap) {
    pathMap.addEventListener("wheel", event => {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
        pathView.zoom = Math.max(0.7, Math.min(4, pathView.zoom * factor));
        paintOpsBoard();
    }, {passive: false});
    pathMap.addEventListener("pointerdown", event => {
        pathView.dragging = true;
        pathView.moved = false;
        pathView.lastX = event.clientX;
        pathView.lastY = event.clientY;
        pathWrap.classList.add("is-panning");
        pathMap.setPointerCapture(event.pointerId);
    });
    pathMap.addEventListener("pointermove", event => {
        if (!pathView.dragging || !pathView.project) return;
        const dx = event.clientX - pathView.lastX;
        const dy = event.clientY - pathView.lastY;
        if (Math.abs(dx) + Math.abs(dy) > 2) pathView.moved = true;
        pathView.lastX = event.clientX;
        pathView.lastY = event.clientY;
        const scale = pathView.project.kmPerPx;
        pathView.panE -= dx * scale;
        pathView.panN += dy * scale;
        paintOpsBoard();
    });
    pathMap.addEventListener("pointerup", event => {
        pathView.dragging = false;
        pathWrap.classList.remove("is-panning");
        try { pathMap.releasePointerCapture(event.pointerId); } catch (err) {}
    });
    pathMap.addEventListener("click", event => {
        if (!pathView.inspect || !pathView.project || pathView.moved) return;
        const rect = pathMap.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const east = pathView.project.vMinE + (x / rect.width) * (pathView.project.vMaxE - pathView.project.vMinE);
        const north = pathView.project.vMaxN - (y / rect.height) * (pathView.project.vMaxN - pathView.project.vMinN);
        let nearest = null;
        let best = Infinity;
        (pathView.project.samples || []).forEach(sample => {
            const d = Math.hypot(sample.e - east, sample.n - north);
            if (d < best) { best = d; nearest = sample; }
        });
        const probe = document.getElementById("path-probe");
        if (!probe) return;
        if (!nearest || best > 3.2) {
            pathView.probe = {text: "Probe · E " + east.toFixed(2) + " km · N " + north.toFixed(2) + " km · no hazard sample"};
            probe.innerHTML = pathView.probe.text;
        } else {
            pathView.probe = nearest;
            probe.innerHTML = "<strong>HAZARD SAMPLE</strong><br>Slope " + nearest.slope.toFixed(1) +
                "° · E " + nearest.e.toFixed(2) + " km · N " + nearest.n.toFixed(2) + " km";
        }
        probe.hidden = false;
        paintOpsBoard();
    });
}
pathLayerPressed();

function cycleSite(delta) {
    const dest = document.getElementById("plan-destination");
    if (!dest || !dest.options.length) return;
    dest.selectedIndex = (dest.selectedIndex + delta + dest.options.length) % dest.options.length;
    dest.dispatchEvent(new Event("change", {bubbles: true}));
}
function toggleShelterPlan() {
    const shelter = document.getElementById("brief-shelter");
    if (!shelter) return;
    shelter.value = shelter.value === "yes" ? "no" : "yes";
    shelter.dispatchEvent(new Event("change", {bubbles: true}));
}
document.querySelectorAll("[data-ops-action]").forEach(btn => {
    btn.addEventListener("click", () => {
        const action = btn.dataset.opsAction;
        if (action === "next-site") cycleSite(1);
        else if (action === "prev-site") cycleSite(-1);
        else if (action === "toggle-shelter") toggleShelterPlan();
        else if (action === "focus-gauges") {
            document.querySelectorAll(".ops-pane").forEach(pane => pane.classList.remove("is-focus"));
            const gauges = document.querySelector(".ops-low .ops-pane");
            if (gauges) gauges.classList.add("is-focus");
        }
        paintOpsBoard();
    });
});
const habViewState = window.habViewState = {layers: {dangers: true, yard: true, models: true}};
document.querySelectorAll("[data-hab-action]").forEach(btn => {
    btn.addEventListener("click", () => {
        const action = btn.dataset.habAction;
        if (action === "next-site") cycleSite(1);
        else if (action === "toggle-shelter") toggleShelterPlan();
        else if (action === "orbit" && habCraterView && typeof habCraterView.resetView === "function") {
            habCraterView.resetView();
        } else if (action === "camp-view") {
            const camp = document.getElementById("yard-camp");
            if (camp) camp.click();
        } else if (action === "pad-view") {
            const pad = document.getElementById("yard-pad");
            if (pad) pad.click();
        } else if (action === "snap-pad") {
            const facts = siteFacts();
            const pad = likelyPad(facts);
            if (pad && yardMeshes.habitat) {
                // keep habitat origin; move pad marker toward 2km on shoulder azimuth
                const az = Math.atan2(pad.km.e, pad.km.n || 0.001);
                if (yardMeshes.pad) {
                    yardMeshes.pad.position.x = Math.sin(az) * 2000;
                    yardMeshes.pad.position.z = Math.cos(az) * 2000;
                }
            }
            if (habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
            startBaseYard();
        } else if (action === "replan") {
            paintHabitat();
        }
        paintOpsBoard();
    });
});
document.querySelectorAll("[data-hab-layer]").forEach(btn => {
    btn.addEventListener("click", () => {
        const key = btn.dataset.habLayer;
        habViewState.layers[key] = !habViewState.layers[key];
        btn.setAttribute("aria-pressed", String(habViewState.layers[key]));
        const danger = document.getElementById("hab-danger-pane");
        const yard = document.getElementById("hab-yard-pane");
        if (key === "dangers" && danger) danger.style.display = habViewState.layers.dangers ? "" : "none";
        if (key === "yard" && yard) yard.style.display = habViewState.layers.yard ? "" : "none";
        if (key === "models" && habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
    });
});
function showPage(page) {
    if (page === "home") openOptions(true);
    else if (page === "data") showScreen("habitat");
    else showScreen("ops");
}
const baseParts = [
    {id:"habitat", name:"Habitat", w:8.53, d:4.27, h:4.27, x:0, z:0, color:0xd7f6ff, size:"8.53 × 4.27 × 4.27 m · Destiny-class cylinder"},
    {id:"lab", name:"Lab", w:8.53, d:4.27, h:4.27, x:14, z:0, color:0x9ad7e8, size:"8.53 × 4.27 × 4.27 m · science node"},
    {id:"airlock", name:"Airlock", w:3.2, d:3.2, h:3.0, x:-8, z:0, color:0xd2a85c, size:"3.2 m dust lock"},
    {id:"array", name:"Solar mast", w:3.5, d:0.4, h:10, x:0, z:30, color:0x5eebff, size:"3.5 m blanket on a 10 m mast"},
    {id:"radiator", name:"Radiators", w:6.0, d:0.4, h:3.5, x:-12, z:18, color:0xe8f0f4, size:"6 m heat-rejection fins"},
    {id:"rover", name:"Rover", w:3.1, d:1.8, h:1.14, x:18, z:8, color:0xf0c36a, size:"3.1 × 1.8 × 1.14 m rover"},
    {id:"tanks", name:"Tank farm", w:4.5, d:3.2, h:3.0, x:22, z:-10, color:0xe08a3a, size:"Twin tank skid"},
    {id:"comms", name:"Comms mast", w:1.2, d:1.2, h:12, x:-18, z:-12, color:0xb8c4cc, size:"12 m dish mast"},
    {id:"berm", name:"Regolith berm", w:16, d:16, h:2.2, x:0, z:-22, color:0x6b5a45, size:"Shelter berm arc"},
    {id:"isru", name:"ISRU unit", w:4.0, d:3.5, h:3.2, x:28, z:12, color:0x3d8f6e, size:"Ice / O2 plant"},
    {id:"power", name:"Power node", w:2.4, d:2.0, h:1.8, x:8, z:12, color:0x9aa7b0, size:"Battery / PCU skid"},
    {id:"eva", name:"EVA locker", w:1.8, d:1.4, h:2.2, x:-6, z:10, color:0xdde8ed, size:"Suit / tool cache"},
    {id:"pad", name:"Landing pad", w:20, d:20, h:0.4, x:2000, z:0, color:0xffb45e, size:"20 m marker · place on the 2 km circle"}
];
function yardLabel(text, wide) {
    const board = document.createElement("canvas");
    board.width = 512;
    board.height = 128;
    const context = board.getContext("2d");
    context.fillStyle = "rgba(8, 24, 36, 0.9)";
    context.fillRect(0, 16, 512, 96);
    context.strokeStyle = "#9af6ff";
    context.lineWidth = 4;
    context.strokeRect(2, 16, 508, 96);
    context.fillStyle = "#f4fbff";
    context.font = "bold 58px Segoe UI, Arial";
    context.fillText(text, 20, 82);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(board),
        transparent: true
    }));
    sprite.scale.set(wide ? 80 : 14, wide ? 20 : 3.5, 1);
    return sprite;
}
let yardReady = false;
let yardCamera, yardControls, yardRenderer, yardDragging = null;
const yardMeshes = {};
const yardLines = {};
function updateYardVisibility() {
    const active = activeHabComponents();
    Object.keys(yardMeshes).forEach(id => {
        const mesh = yardMeshes[id];
        if (!mesh) return;
        const on = active.indexOf(id) >= 0 || id === "habitat";
        mesh.visible = on;
        if (yardLines[id]) yardLines[id].visible = on;
    });
}
function startBaseYard(attempt) {
    const canvas = document.getElementById("base-canvas");
    if (!canvas) return;
    if (yardReady) {
        yardRenderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
        return;
    }
    if (!canvas.clientWidth) {
        if ((attempt || 0) < 8) requestAnimationFrame(() => startBaseYard((attempt || 0) + 1));
        return;
    }
    yardReady = true;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#07131c");
    yardCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 8000);
    yardRenderer = new THREE.WebGLRenderer({canvas, antialias:true});
    yardRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    yardRenderer.outputColorSpace = THREE.SRGBColorSpace;
    yardControls = new OrbitControls(yardCamera, canvas);
    yardControls.enableDamping = true;
    yardControls.target.set(8, 2, 12);
    yardCamera.position.set(52, 34, 56);
    scene.add(new THREE.HemisphereLight(0xd7f4ff, 0x1a3344, 1.1));
    const sun = new THREE.DirectionalLight(0xfff1d2, 1.6);
    sun.position.set(40, 80, 20);
    scene.add(sun);
    scene.add(new THREE.GridHelper(200, 20, 0x7ee7f6, 0x1d4e63));
    const ground = new THREE.Mesh(
        new THREE.CircleGeometry(2200, 80),
        new THREE.MeshStandardMaterial({color:0x0c2433, roughness:1})
    );
    ground.rotation.x = -Math.PI / 2;
    ground.name = "ground";
    scene.add(ground);
    const ringPoints = [];
    for (let i = 0; i < 128; i += 1) {
        const angle = (i / 128) * Math.PI * 2;
        ringPoints.push(new THREE.Vector3(Math.cos(angle) * 2000, 0.2, Math.sin(angle) * 2000));
    }
    scene.add(new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(ringPoints),
        new THREE.LineBasicMaterial({color:0xffb45e})
    ));
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const hit = new THREE.Vector3();
    baseParts.forEach(part => {
        const mesh = new THREE.Mesh(
            new THREE.BoxGeometry(part.w, part.h, part.d),
            new THREE.MeshStandardMaterial({color:part.color, roughness:0.45, metalness:0.05})
        );
        mesh.position.set(part.x, part.h / 2, part.z);
        mesh.userData.part = part;
        const edges = new THREE.LineSegments(
            new THREE.EdgesGeometry(mesh.geometry),
            new THREE.LineBasicMaterial({color:0xffffff})
        );
        mesh.add(edges);
        const label = yardLabel(part.name, part.id === "pad");
        label.position.y = part.h / 2 + (part.id === "pad" ? 12 : 2.2);
        mesh.add(label);
        scene.add(mesh);
        yardMeshes[part.id] = mesh;
        if (part.id === "habitat") return;
        const line = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
            new THREE.LineDashedMaterial({color:0x9af6ff, dashSize:3, gapSize:1.5})
        );
        scene.add(line);
        yardLines[part.id] = line;
    });
    const resize = () => {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        if (!width || !height) return;
        yardRenderer.setSize(width, height, false);
        yardCamera.aspect = width / height;
        yardCamera.updateProjectionMatrix();
    };
    new ResizeObserver(resize).observe(canvas);
    resize();
    const updateLines = () => {
        const home = yardMeshes.habitat.position;
        const rows = [];
        baseParts.forEach(part => {
            const mesh = yardMeshes[part.id];
            if (part.id !== "habitat") {
                const line = yardLines[part.id];
                line.geometry.setFromPoints([
                    new THREE.Vector3(home.x, 0.3, home.z),
                    new THREE.Vector3(mesh.position.x, 0.3, mesh.position.z)
                ]);
                line.computeLineDistances();
                const meters = Math.hypot(mesh.position.x - home.x, mesh.position.z - home.z);
                const keep = part.id !== "pad" ? ""
                    : Math.abs(meters - 2000) < 8 ? " · on the 2 km circle"
                    : meters > 2000 ? " · outside the 2 km circle"
                    : " · inside the 2 km circle";
                rows.push("<li><strong>" + part.name + "</strong> " + meters.toFixed(1) + " m from the habitat" + keep + "<br>" + part.size + "</li>");
            } else {
                rows.push("<li><strong>Habitat</strong> origin · " + part.size + "</li>");
            }
        });
        document.getElementById("base-readout").innerHTML = rows.join("");
    };
    const pointOnPlane = event => {
        const rect = canvas.getBoundingClientRect();
        pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, yardCamera);
        return raycaster.ray.intersectPlane(plane, hit) ? hit : null;
    };
    canvas.addEventListener("pointerdown", event => {
        const rect = canvas.getBoundingClientRect();
        pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, yardCamera);
        const hits = raycaster.intersectObjects(Object.values(yardMeshes), true);
        if (!hits.length) return;
        let object = hits[0].object;
        while (object && !object.userData.part) object = object.parent;
        if (!object) return;
        yardDragging = object;
        yardControls.enabled = false;
        canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
        if (!yardDragging) return;
        const point = pointOnPlane(event);
        if (!point) return;
        yardDragging.position.x = Math.max(-2400, Math.min(2400, point.x));
        yardDragging.position.z = Math.max(-2400, Math.min(2400, point.z));
        updateLines();
    });
    canvas.addEventListener("pointerup", () => {
        yardDragging = null;
        yardControls.enabled = true;
    });
    document.getElementById("yard-camp").addEventListener("click", () => {
        yardCamera.position.set(52, 34, 56);
        yardControls.target.set(8, 2, 12);
    });
    const yardReset = document.getElementById("yard-reset-layout");
    if (yardReset) yardReset.addEventListener("click", () => {
        baseParts.forEach(part => {
            const mesh = yardMeshes[part.id];
            if (!mesh) return;
            mesh.position.set(part.x, part.h / 2, part.z);
        });
        updateLines();
        updateYardVisibility();
        if (habCraterView && habCraterView.rebuildBase) habCraterView.rebuildBase();
    });
    document.getElementById("yard-pad").addEventListener("click", () => {
        const pad = yardMeshes.pad.position;
        yardControls.target.set((yardMeshes.habitat.position.x + pad.x) / 2, 0, (yardMeshes.habitat.position.z + pad.z) / 2);
        yardCamera.position.set(yardControls.target.x + 40, 1400, yardControls.target.z + 1600);
    });
    updateLines();
    updateYardVisibility();
    const animate = () => {
        requestAnimationFrame(animate);
        yardControls.update();
        yardRenderer.render(scene, yardCamera);
    };
    animate();
}
document.querySelectorAll(".app-tabs [role='tab']").forEach(tab => {
    tab.addEventListener("click", () => showPage(tab.dataset.page));
});
document.querySelectorAll(".screen-nav button[data-screen]").forEach(button => {
    button.addEventListener("click", () => showScreen(button.dataset.screen));
});
const desMapCanvas = document.getElementById("des-map");
const desMapReadout = document.getElementById("des-map-readout");
function syncDesMapModes() {
    document.querySelectorAll("[data-des-map-mode]").forEach(button => {
        button.setAttribute("aria-pressed", String(button.dataset.desMapMode === desMapMode));
    });
}
document.querySelectorAll("[data-des-map-mode]").forEach(button => {
    button.addEventListener("click", () => {
        desMapMode = button.dataset.desMapMode || "relief";
        syncDesMapModes();
        paintDescent();
    });
});
syncDesMapModes();
document.getElementById("des-map-zoom-in").addEventListener("click", () => {
    desMapZoom = Math.min(4, desMapZoom * 1.35);
    paintDescent();
});
document.getElementById("des-map-zoom-out").addEventListener("click", () => {
    desMapZoom = Math.max(0.8, desMapZoom / 1.35);
    paintDescent();
});
document.getElementById("des-map-reset").addEventListener("click", () => {
    desMapZoom = 1;
    desMapCenter = {x: 0, z: 0};
    desMapInspect = null;
    if (desMapReadout) desMapReadout.textContent = "Click to inspect · planning only";
    paintDescent();
});
const desMapPadBtn = document.getElementById("des-map-pad");
if (desMapPadBtn) {
    desMapPadBtn.addEventListener("click", () => {
        const pad = likelyPad(siteFacts());
        const local = padMapPoint(pad);
        desMapCenter = {x: local.x, z: local.z};
        desMapZoom = Math.max(desMapZoom, 1.8);
        desMapInspect = {x: local.x, z: local.z};
        if (desMapReadout) {
            desMapReadout.textContent = pad
                ? "PAD · slope " + pad.slope.toFixed(1) + "° · " + (pad.clear ? "clearest" : "least steep")
                : "Pad waiting on path";
        }
        paintDescent();
    });
}
desMapCanvas.addEventListener("click", event => {
    const rect = desMapCanvas.getBoundingClientRect();
    const side = Math.min(rect.width - 10, rect.height - 10);
    const left = (rect.width - side) / 2;
    const top = (rect.height - side) / 2;
    const x = (event.clientX - rect.left - left) / side;
    const y = (event.clientY - rect.top - top) / side;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    desMapInspect = {
        x: desMapCenter.x + (x - 0.5) * 2 / desMapZoom,
        z: desMapCenter.z + (0.5 - y) * 2 / desMapZoom
    };
    desMapCenter = {x: desMapInspect.x, z: desMapInspect.z};
    const h = siteSurfaceHeight(desMapInspect.x, desMapInspect.z);
    const s = slopeAtMap(desMapInspect.x, desMapInspect.z);
    if (desMapReadout) {
        desMapReadout.textContent =
            "E " + desMapInspect.x.toFixed(2) + " / N " + desMapInspect.z.toFixed(2) +
            " · " + (h * 1000).toFixed(0) + " m · " + s.toFixed(0) + "° · planning";
    }
    paintDescent();
});
document.getElementById("open-options").addEventListener("click", () => {
    const drawer = document.getElementById("options-drawer");
    openOptions(drawer.hidden);
});
document.getElementById("close-options").addEventListener("click", () => openOptions(false));
document.addEventListener("keydown", event => {
    if (event.key === "Escape") openOptions(false);
});
descentThreeView = createCraterView(document.getElementById("des-stage"), "descent");
descentThreeView.resize();
requestAnimationFrame(() => showScreen("clps"));
function setDemoMode(on) {
    document.body.classList.toggle("demo-mode", on);
    const toggle = document.getElementById("demo-mode-toggle");
    if (toggle) toggle.setAttribute("aria-pressed", String(on));
    try { localStorage.setItem("zpl-demo-mode", on ? "1" : "0"); } catch (error) {}
}
const demoToggle = document.getElementById("demo-mode-toggle");
if (demoToggle) {
    let savedDemo = false;
    try { savedDemo = localStorage.getItem("zpl-demo-mode") === "1"; } catch (error) {}
    setDemoMode(savedDemo);
    demoToggle.addEventListener("click", () => setDemoMode(!document.body.classList.contains("demo-mode")));
}
function syncChoiceCards(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const grid = document.querySelector('[data-choice-for="' + selectId + '"]');
    if (!grid) return;
    grid.querySelectorAll("button").forEach(button => {
        const match = Array.from(select.options).find(option => option.textContent === button.textContent);
        button.setAttribute("aria-pressed", String(Boolean(match && match.selected)));
    });
}
function setBriefSlope(degrees) {
    const slope = document.getElementById("brief-slope");
    const label = document.getElementById("brief-slope-label");
    const live = document.getElementById("path-climb-live");
    const liveLabel = document.getElementById("path-climb-live-label");
    if (slope) slope.value = String(degrees);
    if (label) label.textContent = degrees + "°";
    if (live) live.value = String(degrees);
    if (liveLabel) liveLabel.textContent = degrees + "°";
}
function applyJudgeStoryStep(step) {
    const caption = document.getElementById("story-caption");
    const dest = document.getElementById("plan-destination");
    const shelter = document.getElementById("brief-shelter");
    const priority = document.getElementById("brief-priority");
    const asset = document.getElementById("brief-asset");
    if (dest) {
        dest.value = "-86.9,-4.2";
        Array.from(dest.options).forEach(option => { option.selected = option.value === dest.value; });
    }
    if (asset) asset.value = "rover";
    if (priority) priority.value = "slope";
    if (shelter) shelter.value = step === 1 ? "no" : "yes";
    setBriefSlope(step === 1 ? 10 : 18);
    syncChoiceCards("brief-asset");
    syncChoiceCards("brief-shelter");
    syncChoiceCards("brief-priority");
    if (typeof refreshBriefingSummary === "function") refreshBriefingSummary();
    if (caption) {
        caption.hidden = false;
        caption.textContent = step === 1
            ? "Story beat 1 · Haworth, climb 10°, no storm shelter. Apply, then watch red cells and a planning HOLD/STOP."
            : "Story beat 2 · Same crater, climb 18°, shelter recorded. Apply again — the corridor opens and the verdict softens.";
    }
    document.getElementById("run-plan").click();
    showScreen("path");
}
let judgeStoryStep = 0;
const tryStoryBtn = document.getElementById("try-story");
if (tryStoryBtn) {
    tryStoryBtn.addEventListener("click", () => {
        setDemoMode(true);
        judgeStoryStep = judgeStoryStep === 1 ? 2 : 1;
        applyJudgeStoryStep(judgeStoryStep);
        tryStoryBtn.textContent = judgeStoryStep === 1 ? "Story: relax the walk" : "Try the story";
    });
}
function paintChoices(selectId, title) {
    const select = document.getElementById(selectId);
    const board = document.createElement("div");
    board.className = "choice-board";
    const heading = document.createElement("p");
    heading.className = "choice-title";
    heading.textContent = title;
    const row = document.createElement("div");
    row.className = "choice-grid";
    Array.from(select.options).forEach(option => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "choice-card";
        button.textContent = option.textContent;
        button.setAttribute("aria-pressed", String(option.selected));
        button.addEventListener("click", () => {
            select.value = option.value;
            row.querySelectorAll("button").forEach(other => other.setAttribute("aria-pressed", "false"));
            button.setAttribute("aria-pressed", "true");
            if (selectId === "plan-destination") {
                applyChosenSite();
                refreshBriefingSummary();
                loadLiveFinds((option.dataset.name || option.textContent) + " crater");
                setPlanningBadge("wait", "Checking this crater");
                const cost = document.getElementById("plan-cost");
                if (cost) cost.textContent = (option.dataset.name || option.textContent) + " · reading the A* path for these questions.";
                activateWorkflow("movement");
                loadEnvironment();
                loadTerrain();
            }
            paintOpsBoard();
        });
        row.appendChild(button);
    });
    board.append(heading, row);
    return board;
}
document.getElementById("choice-boards").append(
    paintChoices("plan-destination", "Which crater are you walking?")
);
const recordedLaunch = document.getElementById("recorded-launch");
if (recordedLaunch) {
    recordedLaunch.append(
        paintChoices("plan-vehicle", "Rocket on the record"),
        paintChoices("plan-pad", "Earth pad on the record")
    );
}
document.querySelectorAll("[data-choice-for]").forEach(row => {
    const select = document.getElementById(row.dataset.choiceFor);
    if (!select) return;
    Array.from(select.options).forEach(option => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "choice-card";
        button.textContent = option.textContent;
        button.setAttribute("aria-pressed", String(option.selected));
        button.addEventListener("click", () => {
            select.value = option.value;
            row.querySelectorAll("button").forEach(other => other.setAttribute("aria-pressed", "false"));
            button.setAttribute("aria-pressed", "true");
            select.dispatchEvent(new Event("change"));
        });
        row.appendChild(button);
    });
});
function applyChosenSite() {
    const destination = document.getElementById("plan-destination");
    const option = destination.selectedOptions[0];
    const pair = destination.value.split(",").map(Number);
    const name = option.dataset.name;
    const start = (option.dataset.start || "").split(",").map(Number);
    const dest = (option.dataset.dest || "").split(",").map(Number);
    const hasEnds = start.length === 2 && dest.length === 2 && start.concat(dest).every(Number.isFinite);
    if (hasEnds) {
        document.getElementById("start_lat").value = start[0];
        document.getElementById("start_lon").value = start[1];
        document.getElementById("dest_lat").value = dest[0];
        document.getElementById("dest_lon").value = dest[1];
        document.getElementById("start_name").value = name + " rim habitat";
        document.getElementById("dest_name").value = name + " drill site";
    } else {
        document.getElementById("start_lat").value = pair[0];
        document.getElementById("start_lon").value = pair[1];
        document.getElementById("start_name").value = name;
        const destLat = Math.max(-89.9, Math.min(89.9, pair[0] + (pair[0] < 0 ? 0.35 : -0.35)));
        document.getElementById("dest_lat").value = destLat.toFixed(5);
        document.getElementById("dest_lon").value = pair[1];
        document.getElementById("dest_name").value = name + " walk";
    }
    return name;
}
async function loadLiveFinds(name) {
    const boxes = ["live-finds", "live-finds-data"].map(id => document.getElementById(id)).filter(Boolean);
    boxes.forEach(box => { box.textContent = "Searching the webâ€¦"; });
    try {
        const response = await fetch("/api/live-search?q=" + encodeURIComponent(name + " Moon landing"));
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Search failed.");
        const items = payload.items || [];
        boxes.forEach(box => {
            if (!items.length) {
                box.textContent = "No lunar pages came back for this place.";
                return;
            }
            box.replaceChildren();
            items.forEach(item => {
                const link = document.createElement("a");
                link.href = item.url;
                link.target = "_blank";
                link.rel = "noopener";
                const title = document.createElement("strong");
                title.textContent = item.title;
                const snippet = document.createElement("small");
                snippet.textContent = item.snippet;
                link.append(title, snippet);
                box.appendChild(link);
            });
        });
    } catch (error) {
        boxes.forEach(box => { box.textContent = error.message; });
    }
}
loadLiveFinds("Haworth crater");
function setPlanningBadge(tone, label) {
    ["q-badge", "judge-badge"].forEach(id => {
        const badge = document.getElementById(id);
        if (!badge) return;
        badge.dataset.tone = tone;
        badge.className = "q-badge " + tone;
        badge.textContent = label;
    });
    const judgeNote = document.getElementById("judge-badge-note");
    if (judgeNote) {
        if (tone === "go") judgeNote.textContent = "Planning GO for these Options — still not a flight clearance.";
        else if (tone === "hold" || tone === "stop") judgeNote.textContent = "Planning HOLD / STOP — change Options or pick another corridor.";
        else judgeNote.textContent = "GO / HOLD updates when you Apply Options";
    }
}
document.getElementById("run-plan").addEventListener("click", () => {
    const name = applyChosenSite();
    const vehicle = document.getElementById("plan-vehicle").selectedOptions[0].textContent;
    const pad = document.getElementById("plan-pad").selectedOptions[0].textContent;
    document.getElementById("plan-cost").textContent =
        name + " · " + vehicle + " from " + pad + ". Reading the A* path. The answer stays on this page.";
    setPlanningBadge("wait", "Checking this crater");
    activateWorkflow("movement");
    loadEnvironment();
    loadTerrain();
});
document.getElementById("q-open-next").addEventListener("click", () => {
    const state = briefingState();
    const tone = document.getElementById("q-badge").dataset.tone;
    if (tone === "hold") {
        showScreen("ops");
        return;
    }
    if (state.priority === "sun") showScreen("habitat");
    else if (state.priority === "radio") {
        showScreen("terrain");
        activateWorkflow("movement");
    } else showScreen("path");
});
document.getElementById("open-yard").addEventListener("click", () => {
    showScreen("path");
});
document.getElementById("open-terrain").addEventListener("click", () => {
    showScreen("terrain");
    activateWorkflow("movement");
    loadTerrain();
});

const solarCurrent = document.getElementById("solar-current");
const solarPeak = document.getElementById("solar-peak");
const solarUpdated = document.getElementById("solar-updated");
const solarStatus = document.getElementById("solar-status");
const solarChart = document.getElementById("solar-chart");

function drawSolarChart(samples) {
    const ratio = window.devicePixelRatio || 1;
    const width = solarChart.clientWidth;
    const height = solarChart.clientHeight;
    if (!width || !height || !samples.length) return;
    solarChart.width = Math.round(width * ratio);
    solarChart.height = Math.round(height * ratio);
    const context = solarChart.getContext("2d");
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    const left = 46, right = 12, top = 14, bottom = 28;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    context.font = "12px Segoe UI, Arial";
    context.fillStyle = "#afc0ca";
    context.strokeStyle = "#29404e";
    context.lineWidth = 1;
    const bands = ["#3a2430", "#3a3020", "#243428", "#1c3040", "#1a2838", "#182430"];
    const point = (sample, index) => {
        const x = left + plotWidth * index / Math.max(1, samples.length - 1);
        const value = Math.max(1e-8, Math.min(1e-3, sample.flux));
        const y = top + plotHeight * (1 - (Math.log10(value) + 8) / 5);
        return [x, y];
    };
    [0, 1, 2, 3, 4, 5].forEach(step => {
        const y = top + plotHeight * step / 5;
        context.fillStyle = bands[step];
        context.fillRect(left, y, plotWidth, plotHeight / 5);
        context.strokeStyle = "#29404e";
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(width - right, y);
        context.stroke();
        context.fillStyle = "#afc0ca";
        context.fillText(["X10","X","M","C","B","A"][step], 10, y + 4);
    });
    context.beginPath();
    samples.forEach((sample, index) => {
        const [x, y] = point(sample, index);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
    });
    context.strokeStyle = "#62e9ec";
    context.lineWidth = 2;
    context.stroke();
    const last = point(samples[samples.length - 1], samples.length - 1);
    context.lineTo(last[0], top + plotHeight);
    context.lineTo(point(samples[0], 0)[0], top + plotHeight);
    context.closePath();
    context.fillStyle = "rgba(98, 233, 236, 0.18)";
    context.fill();
    context.fillStyle = "#f4fbff";
    context.beginPath();
    context.arc(last[0], last[1], 5, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#d5e6ef";
    context.fillText("GOES 0.1–0.8 nm", left, height - 8);
}

async function loadSolarActivity() {
    solarStatus.textContent = "Loading measured NOAA GOES X-ray dataâ€¦";
    try {
        const response = await fetch("/api/solar-xray");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "NOAA X-ray readings are unavailable.");
        solarSamples = payload.samples;
        solarCurrent.textContent = payload.latest.class;
        solarPeak.textContent = payload.peak_24h.class;
        solarUpdated.textContent = payload.latest.time_utc.replace("T", " ").replace("Z", "");
        solarStatus.textContent = "Measured by GOES-" + payload.latest.satellite +
            " · refreshed " + payload.fetched_at_utc.replace("T", " ").replace("Z", "") +
            " · checks every 5 minutes.";
        drawSolarChart(solarSamples);
    } catch (error) {
        solarCurrent.textContent = "Unavailable";
        solarPeak.textContent = "Unavailable";
        solarUpdated.textContent = "No current reading";
        solarStatus.textContent = error.message;
    }
}
loadSolarActivity();
window.addEventListener("resize", () => {
    if (solarSamples.length) drawSolarChart(solarSamples);
    if (latestPower) drawPowerCurve(latestPower);
    if (latestTerrainPayload) drawSiteCharts(latestTerrainPayload);
});
window.setInterval(async () => {
    await loadSolarActivity();
}, 5 * 60 * 1000);

let latestFlareProbability = 0;
let slopeReloadTimer = null;
function briefingState() {
    return {
        asset: document.getElementById("brief-asset").value,
        sheltered: document.getElementById("brief-shelter").value,
        slope: Number(document.getElementById("brief-slope").value),
        priority: document.getElementById("brief-priority").value,
        focusNote: document.getElementById("brief-focus-note").value.trim(),
        speed: Number(document.getElementById("brief-speed").value)
    };
}
function refreshBriefingSummary() {
    const state = briefingState();
    const who = state.asset === "both" ? "crew and habitat" : state.asset === "crew" ? "crew" : "habitat";
    const shelter = state.sheltered === "yes" ? "shelter available" : "no shelter";
    const watch = state.priority === "sun" ? "sunlight" : state.priority === "radio" ? "Earth radio" : "slope";
    const place = document.getElementById("plan-destination").selectedOptions[0].dataset.name;
    document.getElementById("briefing-summary").textContent =
        place + " · protecting the " + who + " · " + shelter + " · climb limit " +
        state.slope + "° · " + state.speed.toFixed(1) + " km/h · " + watch + " decides the answer." +
        (state.focusNote ? " · planning note: " + state.focusNote : "");
    const slopeInput = document.getElementById("max_slope_degrees");
    if (Number.isFinite(state.slope)) slopeInput.value = state.slope;
    const slopeLabel = document.getElementById("brief-slope-label");
    if (slopeLabel) slopeLabel.textContent = state.slope + "°";
}
["brief-asset", "brief-shelter", "brief-slope", "brief-priority"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => {
        if (id === "brief-asset") {
            const rover = document.querySelector("#base-kit [data-kit='rover']");
            const asset = document.getElementById("brief-asset").value;
            if (rover) rover.setAttribute("aria-pressed", String(asset === "crew" || asset === "both"));
        }
        refreshBriefingSummary();
        loadFlareOutlook();
        refreshMissionPlan();
        if (id === "brief-slope") {
            clearTimeout(slopeReloadTimer);
            slopeReloadTimer = setTimeout(() => {
                activateWorkflow("movement");
                loadTerrain();
            }, 400);
        }
    });
});
document.getElementById("brief-slope").addEventListener("input", refreshBriefingSummary);
document.getElementById("brief-focus-note").addEventListener("input", refreshBriefingSummary);
const speedSlider = document.getElementById("brief-speed");
if (speedSlider) {
    speedSlider.addEventListener("input", () => {
        const value = Number(speedSlider.value);
        document.getElementById("planning_speed_kmh").value = String(value);
        const speedLabel = document.getElementById("brief-speed-label");
        if (speedLabel) speedLabel.textContent = value.toFixed(1);
        refreshBriefingSummary();
        paintOpsBoard();
    });
}
document.querySelectorAll("#base-kit [data-kit]").forEach(button => {
    button.addEventListener("click", () => {
        if (button.dataset.kit === "habitat") return;
        button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true"));
        paintOpsBoard();
    });
});
refreshBriefingSummary();
document.querySelectorAll("[data-open-view]").forEach(button => {
    button.addEventListener("click", () => activateWorkflow(button.dataset.openView));
});
document.getElementById("load-shackleton").addEventListener("click", () => {
    document.getElementById("start_name").value = "Shackleton rim";
    document.getElementById("start_lat").value = "-89.5";
    document.getElementById("start_lon").value = "0";
    document.getElementById("dest_name").value = "Shackleton Crater";
    document.getElementById("dest_lat").value = "-89.9";
    document.getElementById("dest_lon").value = "0";
    activateWorkflow("movement");
    loadTerrain();
});

function paintList(id, steps) {
    const list = document.getElementById(id);
    if (!list) return;
    list.replaceChildren();
    (steps || []).forEach(step => {
        const item = document.createElement("li");
        item.textContent = step;
        list.appendChild(item);
    });
}
async function loadFlareOutlook() {
    const state = briefingState();
    const body = {
        zurich_class: document.getElementById("zurich_class").value,
        spot_size: document.getElementById("spot_size").value,
        distribution: document.getElementById("distribution").value,
        activity: Number(document.getElementById("activity").value),
        evolution: Number(document.getElementById("evolution").value),
        prev_flare: Number(document.getElementById("prev_flare").value),
        sheltered: state.sheltered,
        asset: state.asset
    };
    const probability = document.getElementById("flare-probability");
    const action = document.getElementById("flare-action");
    try {
        const response = await fetch("/api/flare-outlook", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "The sunspot check failed.");
        const percent = Math.round(payload.probability * 1000) / 10;
        probability.textContent = percent.toFixed(1) + "% · " + payload.region_code;
        action.textContent = payload.probability >= 0.5
            ? "Example only · would protect hardware"
            : "Example only · no extra step";
        latestFlareProbability = payload.probability;
        paintList("flare-protection", [
            "For example region " + payload.region_code + " only. This is not the GOES chart."
        ].concat(payload.protection).slice(0, 4));
        refreshMissionPlan();
        document.getElementById("flare-caveat").textContent =
            payload.caveat + " Engine: " + payload.engine + " · " + payload.training_rows + " training rows.";
    } catch (error) {
        probability.textContent = "Unavailable";
        action.textContent = "Check the measured X-ray chart";
        document.getElementById("flare-caveat").textContent = error.message;
    }
}
document.getElementById("run-flare").addEventListener("click", loadFlareOutlook);
["zurich_class", "spot_size", "distribution", "activity", "evolution", "prev_flare"].forEach(id => {
    document.getElementById(id).addEventListener("change", loadFlareOutlook);
});
loadFlareOutlook();

function paintEnvironment(payload) {
    latestEnvironment = payload;
    const moon = payload.moonlight || {};
    const radiation = payload.surface_radiation || {};
    const protons = radiation.protons;
    const temperature = payload.temperature || {};
    document.getElementById("moonlight-value").textContent =
        (moon.irradiance_wm2 != null ? moon.irradiance_wm2.toFixed(5) + " W/mÂ²" : "Unavailable");
    document.getElementById("gcr-value").textContent =
        (radiation.baseline_gcr_usv_hr || 57) + " µSv/hr";
    document.getElementById("proton-value").textContent = protons
        ? protons.flux_pfu.toFixed(2) + " pfu · " + protons.storm_scale
        : "Unavailable";
    const protonNote = protons
        ? "GOES >=10 MeV flux at " + protons.time_utc + ". Storm scale " + protons.storm_scale + ". "
        : (radiation.proton_error ? "Proton feed unavailable. " : "");
    document.getElementById("radiation-note").textContent =
        protonNote + (radiation.baseline_source || "") + " " + (moon.note || "");
    paintList("radiation-protection", payload.protection);
    document.getElementById("temp-now").textContent =
        temperature.celsius != null ? temperature.celsius.toFixed(1) + " °C" : "Unavailable";
    document.getElementById("temp-day").textContent =
        temperature.day_high_c != null ? temperature.day_high_c.toFixed(1) + " °C" : "Unavailable";
    document.getElementById("temp-night").textContent =
        temperature.night_low_c != null ? temperature.night_low_c.toFixed(1) + " °C" : "Unavailable";
    document.getElementById("temp-note").textContent = temperature.note || "";
    paintList("temperature-protection", payload.protection);
    drawTemperature(payload);
    drawRadiation(payload);
    refreshMissionPlan();
}
function drawRadiation(payload) {
    const canvas = document.getElementById("radiation-board");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted) return;
    const {context, width, height} = fitted;
    context.clearRect(0, 0, width, height);
    const moon = (payload && payload.moonlight) || {};
    const radiation = (payload && payload.surface_radiation) || {};
    const protons = radiation.protons || {};
    const moonValue = moon.irradiance_wm2;
    const moonFrac = moonValue == null ? 0 : Math.max(0, Math.min(1, (Math.log10(Math.max(moonValue, 1e-6)) + 6) / 6));
    const gcr = radiation.baseline_gcr_usv_hr || 57;
    const scale = String(protons.storm_scale || "S0");
    const sNum = Number(scale.replace(/[^0-9]/g, "")) || 0;
    const dials = [
        {label: "Moonlight", value: moonFrac, color: "#e2a15a", caption: moonValue == null ? "—" : moonValue.toFixed(4)},
        {label: "Reference", value: Math.max(0, Math.min(1, gcr / 200)), color: "#79c7e8", caption: gcr + " µSv/hr"},
        {label: "Protons", value: Math.max(0, Math.min(1, sNum / 5)), color: "#ff8b92", caption: scale}
    ];
    dials.forEach((dial, index) => {
        const cx = width * (index + 0.5) / 3;
        const cy = height * 0.58;
        const radius = Math.min(width / 7, height * 0.32);
        context.beginPath();
        context.strokeStyle = "#1c3040";
        context.lineWidth = 10;
        context.arc(cx, cy, radius, Math.PI * 0.85, Math.PI * 2.15);
        context.stroke();
        context.beginPath();
        context.strokeStyle = dial.color;
        context.arc(cx, cy, radius, Math.PI * 0.85, Math.PI * 0.85 + Math.PI * 1.3 * dial.value);
        context.stroke();
        context.fillStyle = "#f4fbff";
        context.font = "13px Segoe UI, Arial";
        context.textAlign = "center";
        context.fillText(dial.caption, cx, cy + 4);
        context.fillStyle = "#afc0ca";
        context.fillText(dial.label, cx, height - 12);
        context.textAlign = "left";
    });
}
function applyMissionPlan(plan) {
    opsPlan = plan;
    const links = plan.links || {};
    ["mission", "path", "dust", "solar", "radiation", "temperature"].forEach(name => {
        const node = document.getElementById("link-" + name);
        if (node && links[name]) node.textContent = links[name];
    });
    const telemetry = plan.telemetry || {};
    const battery = document.getElementById("mission-battery");
    const dose = document.getElementById("mission-dose");
    const slope = document.getElementById("mission-slope");
    const radio = document.getElementById("mission-radio");
    if (battery) {
        battery.textContent = telemetry.battery_hours != null
            ? telemetry.battery_hours + " h available"
            : "Waiting";
    }
    if (dose) {
        dose.textContent = telemetry.dose_msv != null
            ? telemetry.dose_msv + " mSv"
            : "Waiting";
    }
    if (slope) {
        slope.textContent = telemetry.max_slope_degrees != null
            ? telemetry.max_slope_degrees + "°"
            : "Waiting";
    }
    if (radio) {
        radio.textContent = telemetry.min_earth_elevation_degrees != null
            ? telemetry.min_earth_elevation_degrees + "°"
            : "Waiting";
    }
    const site = plan.site || {};
    const pad = document.getElementById("mission-pad");
    const sun = document.getElementById("mission-sun");
    const ice = document.getElementById("mission-ice");
    const tether = document.getElementById("mission-tether");
    if (pad) pad.textContent = site.pad_slope != null ? site.pad_slope + "°" : "Waiting";
    if (sun) sun.textContent = site.sun_state === "day" ? "Up" : site.sun_state === "night" ? "Down" : "Waiting";
    if (ice) ice.textContent = site.neighbor || "Waiting";
    if (tether) tether.textContent = site.tether_km != null ? site.tether_km + " km" : "Waiting";
    const shelter = document.getElementById("mission-shelter");
    const localization = document.getElementById("mission-localization");
    const assumptions = document.getElementById("mission-assumptions");
    if (shelter) shelter.textContent = plan.shelter || "";
    if (localization) localization.textContent = plan.localization || "";
    if (assumptions) assumptions.textContent = plan.assumptions || "";
    paintQuestionVerdict(plan);
    paintNight(plan.power);
    paintOpsBoard();
}
function paintQuestionVerdict(plan) {
    const badge = document.getElementById("q-badge");
    if (!badge || !plan) return;
    const telemetry = plan.telemetry || {};
    const power = plan.power || {};
    const state = briefingState();
    const stormHold = /Do not start/.test(plan.shelter || "");
    const stormStep = /storm step is on/i.test(plan.shelter || "");
    const samples = telemetry.sample_count || 0;
    let tone = "wait";
    let label = "Waiting on the path";
    if (stormHold) {
        tone = "hold";
        label = "Do not start";
    } else if (!samples) {
        tone = "wait";
        label = "Need a site check";
    } else if (state.priority === "sun") {
        if (telemetry.sun_up === true) { tone = "go"; label = "Sun can help"; }
        else if (telemetry.sun_up === false) { tone = "stop"; label = "Night load only"; }
        else { tone = "wait"; label = "Sun not loaded"; }
    } else if (state.priority === "radio") {
        const earth = telemetry.min_earth_elevation_degrees;
        if (earth == null) { tone = "wait"; label = "Radio not loaded"; }
        else if (earth >= 5) { tone = "go"; label = "Earth stays up"; }
        else { tone = "stop"; label = "Earth drops low"; }
    } else if (telemetry.route_cleared && telemetry.samples_over_slope_limit === 0) {
        tone = "go";
        label = "Climb stays in limit";
    } else if (telemetry.samples_over_slope_limit === 0) {
        tone = "wait";
        label = "Preview, not cleared";
    } else {
        tone = "stop";
        label = "Climb is not clear";
    }
    setPlanningBadge(tone, label);
    const decision = document.getElementById("q-decision");
    if (decision) decision.textContent = [plan.decision, plan.shelter, power.verdict].filter(Boolean).join(" ");
    const setText = (id, text) => {
        const node = document.getElementById(id);
        if (node) node.textContent = text;
    };
    setText("q-climb", state.slope + "°");
    const over = telemetry.samples_over_slope_limit || 0;
    const climbNote = telemetry.max_slope_degrees == null
        ? "Path not loaded"
        : over
            ? "Path max " + telemetry.max_slope_degrees + "° · " + over + " samples over the limit"
            : telemetry.route_cleared
                ? "Path max " + telemetry.max_slope_degrees + "°. Samples stay under the limit."
                : "Path max " + telemetry.max_slope_degrees + "°. Samples stay under the limit. The route is still a preview.";
    setText("q-climb-note", climbNote);
    setText("q-battery", telemetry.battery_hours != null ? telemetry.battery_hours + " h" : "—");
    setText("q-battery-note", state.asset === "crew" ? "Crew load" : state.asset === "both" ? "Crew and habitat" : "Habitat load");
    setText("q-earth", telemetry.min_earth_elevation_degrees != null ? telemetry.min_earth_elevation_degrees + "°" : "—");
    setText("q-earth-note", telemetry.drive_hours != null ? telemetry.drive_hours + " h on this path" : "Drive time after the path");
    setText("q-storm", stormHold ? "Hold" : stormStep ? "Stop behind mass" : "Same path");
    setText("q-storm-note", state.sheltered === "yes" ? "Shelter is recorded" : "No shelter recorded");
    const next = document.getElementById("q-next");
    const open = document.getElementById("q-open-next");
    if (stormHold) {
        if (next) next.textContent = "The Sun is active and this plan has no shelter. Answer yes to record a mass to stop behind, or open Ops for the watch light. This is a planning hold, not a radiation dose.";
        if (open) open.textContent = "See the watch on Ops";
    } else if (!samples) {
        if (next) next.textContent = "Check this site to run the A* path. The answer stays on this page.";
        if (open) open.textContent = "Open the path";
    } else if (state.priority === "sun") {
        if (next) next.textContent = "Sunlight is the question. Habitat shows night length and array watts for this latitude.";
        if (open) open.textContent = "Open habitat";
    } else if (state.priority === "radio") {
        if (next) next.textContent = "Earth radio is the question. Terrain shows the ground along this path.";
        if (open) open.textContent = "Open terrain";
    } else {
        if (next) next.textContent = "Slope is the question. The path board marks irregular slope shapes at or over " + state.slope + "°.";
        if (open) open.textContent = "Open the path";
    }
    const assumptionNote = document.getElementById("q-assumptions");
    if (assumptionNote) assumptionNote.textContent = plan.assumptions || "";
}
let latestPower = null;
function paintListInto(id, lines) {
    const list = document.getElementById(id);
    if (!list) return;
    list.replaceChildren();
    (lines || []).forEach(line => {
        const item = document.createElement("li");
        item.textContent = line;
        list.appendChild(item);
    });
}
function paintNight(power) {
    latestPower = power || null;
    if (!power) return;
    const length = document.getElementById("night-length");
    const peak = document.getElementById("night-peak");
    const battery = document.getElementById("night-battery");
    const note = document.getElementById("power-note");
    if (length) length.textContent = power.night_days + " days";
    if (peak) peak.textContent = power.peak_flat_w + " W";
    if (battery) battery.textContent = power.battery_kwh + " kWh";
    if (note) note.textContent = power.note || "";
    const box = document.getElementById("power-options");
    if (box) {
        box.replaceChildren();
        (power.options || []).forEach(option => {
            const card = document.createElement("article");
            card.className = "simple-card option-card " + (option.works ? "works" : "fails");
            const tag = document.createElement("div");
            tag.className = "tag";
            tag.textContent = option.works ? "Can carry the night" : "Cannot carry the night";
            const title = document.createElement("h3");
            title.textContent = option.name;
            const copy = document.createElement("p");
            copy.textContent = option.line;
            card.append(tag, title, copy);
            box.appendChild(card);
        });
    }
    paintListInto("power-do", power.do);
    paintListInto("power-cannot", power.cannot);
    requestAnimationFrame(() => drawPowerCurve(power));
}
function drawPowerCurve(power) {
    const canvas = document.getElementById("site-power");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted || !power || !power.curve || power.curve.length < 2) return;
    const {context, width, height} = fitted;
    const curve = power.curve;
    const left = 46, right = 12, top = 16, bottom = 26;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    context.clearRect(0, 0, width, height);
    const maxW = Math.max(200, ...curve.map(point => Math.max(point.flat_w, point.tilt_w, point.load_w)));
    const xOf = index => left + plotW * index / (curve.length - 1);
    const yOf = value => top + plotH * (1 - value / maxW);
    context.fillStyle = "#102033";
    curve.forEach((point, index) => {
        if (point.elev > 0 || index === curve.length - 1) return;
        const next = curve[index + 1];
        if (!next || next.elev > 0) return;
        context.fillRect(xOf(index), top, Math.max(1, xOf(index + 1) - xOf(index)), plotH);
    });
    function stroke(key, color) {
        context.beginPath();
        curve.forEach((point, index) => {
            const x = xOf(index);
            const y = yOf(point[key]);
            if (index === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
        });
        context.strokeStyle = color;
        context.lineWidth = 2;
        context.stroke();
    }
    stroke("load_w", "#e0b15a");
    stroke("flat_w", "#7ec8ff");
    stroke("tilt_w", "#7ef0c2");
    context.fillStyle = "#d5e6ef";
    context.font = "12px Segoe UI, Arial";
    context.fillText("One lunar day · blue flat array · green tilted array · gold keep-alive load", left, height - 8);
    context.fillText(Math.round(maxW) + " W", 4, top + 10);
}
function drawSiteCharts(payload) {
    const elevCanvas = document.getElementById("site-elevation");
    const areaCanvas = document.getElementById("site-area");
    const elevFit = elevCanvas && fittedCanvas(elevCanvas);
    const areaFit = areaCanvas && fittedCanvas(areaCanvas);
    if (elevFit && payload) {
        const {context, width, height} = elevFit;
        const usingAdvisory = !payload.route_available;
        const elevations = (usingAdvisory ? payload.advisory_route_elevation_km : payload.route_elevation_km) || [];
        context.clearRect(0, 0, width, height);
        context.fillStyle = "#d5e6ef";
        context.font = "12px Segoe UI, Arial";
        if (elevations.length < 2) {
            context.fillText("Elevation appears with the path.", 12, 28);
        } else {
            const minE = Math.min.apply(null, elevations);
            const maxE = Math.max.apply(null, elevations);
            const span = Math.max(0.05, maxE - minE);
            context.beginPath();
            elevations.forEach((value, index) => {
                const x = 12 + (width - 24) * index / (elevations.length - 1);
                const y = 22 + (height - 36) * (1 - (value - minE) / span);
                if (index === 0) context.moveTo(x, y);
                else context.lineTo(x, y);
            });
            context.strokeStyle = "#7ef0e4";
            context.lineWidth = 2;
            context.stroke();
            context.fillText("Path elevation · " + minE.toFixed(2) + " to " + maxE.toFixed(2) + " km", 12, 14);
        }
    }
    if (areaFit && payload && payload.area_scan && payload.area_scan.length) {
        const {context, width, height} = areaFit;
        const cells = payload.area_scan;
        const side = Math.round(Math.sqrt(cells.length));
        const minE = Math.min.apply(null, cells.map(cell => cell.elev_km));
        const maxE = Math.max.apply(null, cells.map(cell => cell.elev_km));
        const span = Math.max(0.001, maxE - minE);
        context.clearRect(0, 0, width, height);
        const cellW = width / side;
        const cellH = (height - 16) / side;
        cells.forEach((cell, index) => {
            const column = index % side;
            const row = Math.floor(index / side);
            const shade = (cell.elev_km - minE) / span;
            const red = Math.round(40 + 180 * shade);
            const green = Math.round(70 + 80 * (1 - Math.abs(shade - 0.5) * 2));
            const blue = Math.round(120 + 80 * (1 - shade));
            context.fillStyle = "rgb(" + red + "," + green + "," + blue + ")";
            context.fillRect(column * cellW, 16 + row * cellH, cellW + 0.5, cellH + 0.5);
        });
        context.fillStyle = "#d5e6ef";
        context.font = "12px Segoe UI, Arial";
        context.fillText("Nearby height · low is blue, high is warm · " + minE.toFixed(2) + "–" + maxE.toFixed(2) + " km", 8, 12);
    }
}
let planRequest = 0;
async function refreshMissionPlan() {
    const ticket = ++planRequest;
    const state = briefingState();
    const terrain = latestTerrainPayload;
    const cleared = Boolean(terrain && terrain.route_available);
    const route = terrain ? (cleared ? terrain.route : terrain.advisory_route) || [] : [];
    const slopes = terrain ? (cleared ? terrain.route_slope_degrees : terrain.advisory_route_slope_degrees) || [] : [];
    const elevations = terrain
        ? (cleared ? terrain.route_elevation_km : terrain.advisory_route_elevation_km) || []
        : [];
    const samples = route.map((pair, index) => ({
        lat: pair[0],
        lon: pair[1],
        slope: slopes[index] || 0,
        elev_km: elevations[index]
    }));
    const env = latestEnvironment || {};
    const protons = env.surface_radiation && env.surface_radiation.protons;
    const body = {
        priority: state.priority,
        asset: state.asset,
        sheltered: state.sheltered,
        slope_limit: state.slope,
        distance_km: terrain ? (cleared ? terrain.route_distance_km : terrain.advisory_distance_km) : null,
        speed_kmh: terrain && terrain.planning_speed_kmh
            ? terrain.planning_speed_kmh
            : Number(document.getElementById("planning_speed_kmh").value),
        route_cleared: cleared,
        samples,
        lat: Number(document.getElementById("start_lat").value),
        night_low_c: env.temperature ? env.temperature.night_low_c : null,
        sun_up: env.temperature ? env.temperature.sun_up : null,
        storm_scale: protons ? protons.storm_scale : "unknown",
        goes_class: document.getElementById("solar-current").textContent,
        photo_fix: typeof photoLocation !== "undefined" && Boolean(photoLocation)
    };
    try {
        const response = await fetch("/api/mission-plan", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        });
        const plan = await response.json();
        if (ticket !== planRequest) return;
        if (!response.ok) throw new Error(plan.error || "The mission plan failed.");
        applyMissionPlan(plan);
    } catch (error) {
        if (ticket !== planRequest) return;
        const mission = document.getElementById("link-mission");
        if (mission) mission.textContent = error.message;
    }
}
async function loadEnvironment() {
    const lat = document.getElementById("start_lat").value;
    const lon = document.getElementById("start_lon").value;
    try {
        const response = await fetch("/api/lunar-environment?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lon));
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "The lunar environment check failed.");
        paintEnvironment(payload);
    } catch (error) {
        document.getElementById("radiation-note").textContent = error.message;
        document.getElementById("temp-note").textContent = error.message;
        document.getElementById("moonlight-value").textContent = "Unavailable";
        document.getElementById("proton-value").textContent = "Unavailable";
        document.getElementById("temp-now").textContent = "Unavailable";
    }
}
applyChosenSite();
loadEnvironment();

function fittedCanvas(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return null;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return {context, width, height};
}
function drawTemperature(payload) {
    const canvas = document.getElementById("temperature-stage");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted || !payload || !payload.temperature) return;
    const {context, width, height} = fitted;
    const temperature = payload.temperature;
    const low = temperature.night_low_c;
    const high = temperature.day_high_c;
    const now = temperature.celsius;
    context.clearRect(0, 0, width, height);
    const left = 36, right = 16, top = 16, bottom = 28;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const mid = (high + low) / 2;
    const amp = Math.max(1, (high - low) / 2);
    const phase = Math.acos(Math.max(-1, Math.min(1, (now - mid) / amp))) / (Math.PI * 2);
    const yFor = value => top + plotH * (1 - (value - low) / Math.max(1, high - low));
    context.beginPath();
    for (let step = 0; step <= 80; step += 1) {
        const t = step / 80;
        const value = mid + amp * Math.cos(Math.PI * 2 * t);
        const x = left + plotW * t;
        const y = yFor(value);
        if (step === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
    }
    context.lineTo(left + plotW, top + plotH);
    context.lineTo(left, top + plotH);
    context.closePath();
    const wash = context.createLinearGradient(0, top, 0, top + plotH);
    wash.addColorStop(0, "rgba(226, 161, 90, 0.45)");
    wash.addColorStop(1, "rgba(121, 199, 232, 0.35)");
    context.fillStyle = wash;
    context.fill();
    context.beginPath();
    for (let step = 0; step <= 80; step += 1) {
        const t = step / 80;
        const value = mid + amp * Math.cos(Math.PI * 2 * t);
        const x = left + plotW * t;
        const y = yFor(value);
        if (step === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
    }
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.stroke();
    const nowX = left + plotW * phase;
    const nowY = yFor(now);
    context.fillStyle = "#9af6ff";
    context.beginPath();
    context.arc(nowX, nowY, 5, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#d5e6ef";
    context.font = "12px Segoe UI, Arial";
    context.fillText(low.toFixed(0) + "°", 4, top + plotH);
    context.fillText(high.toFixed(0) + "°", 4, top + 12);
    context.fillText("now " + now.toFixed(0) + "°", Math.min(width - 70, nowX + 8), Math.max(16, nowY - 8));
}
let roverDrive = 0;
function drawElevationProfile(payload) {
    const canvas = document.getElementById("elevation-stage");
    const readout = document.getElementById("elevation-readout");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted) return;
    const {context, width, height} = fitted;
    context.clearRect(0, 0, width, height);
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#10243a");
    sky.addColorStop(1, "#071018");
    context.fillStyle = sky;
    context.fillRect(0, 0, width, height);
    const usingAdvisory = !(payload && payload.route_available);
    const elevations = payload
        ? (usingAdvisory ? payload.advisory_route_elevation_km : payload.route_elevation_km) || []
        : [];
    const slopes = payload
        ? (usingAdvisory ? payload.advisory_route_slope_degrees : payload.route_slope_degrees) || []
        : [];
    context.fillStyle = "#d5e6ef";
    context.font = "13px Segoe UI, Arial";
    if (!payload || elevations.length < 2) {
        context.fillText("Waiting for the route profile.", 16, 32);
        if (readout) readout.textContent = "The climb profile appears after the terrain map loads.";
        return;
    }
    const padL = 18, padR = 18, padT = 28, padB = 26;
    const plotW = Math.max(10, width - padL - padR);
    const plotH = Math.max(10, height - padT - padB);
    const minE = Math.min.apply(null, elevations);
    const maxE = Math.max.apply(null, elevations);
    const span = Math.max(0.05, maxE - minE);
    const xs = elevations.map((_, index) => padL + plotW * index / (elevations.length - 1));
    const ys = elevations.map(value => padT + plotH * (1 - (value - minE) / span));
    context.save();
    context.beginPath();
    context.rect(padL, padT, plotW, plotH);
    context.clip();
    context.beginPath();
    context.moveTo(xs[0], ys[0]);
    xs.forEach((x, index) => context.lineTo(x, ys[index]));
    context.lineTo(xs[xs.length - 1], padT + plotH);
    context.lineTo(xs[0], padT + plotH);
    context.closePath();
    context.fillStyle = "#6e624c";
    context.fill();
    context.beginPath();
    context.moveTo(xs[0], ys[0]);
    xs.forEach((x, index) => context.lineTo(x, ys[index]));
    context.strokeStyle = "#7ef0e4";
    context.lineWidth = 2.5;
    context.stroke();
    const limit = payload.max_slope_degrees || 18;
    let spikes = 0;
    let tallest = 0;
    slopes.forEach(slope => { if (slope > tallest) tallest = slope; });
    for (let index = 1; index < elevations.length; index += 1) {
        if ((slopes[index] || 0) <= limit) continue;
        spikes += 1;
        const x = (xs[index - 1] + xs[index]) / 2;
        const base = Math.max(ys[index - 1], ys[index]);
        const apex = Math.max(padT + 4, base - 22);
        context.beginPath();
        context.moveTo(x - 7, base);
        context.lineTo(x, apex);
        context.lineTo(x + 7, base);
        context.closePath();
        context.fillStyle = "#ff6b73";
        context.fill();
    }
    const roverIndex = Math.max(0, Math.min(xs.length - 1, Math.round(roverDrive * (xs.length - 1))));
    const roverX = Math.max(padL + 16, Math.min(padL + plotW - 16, xs[roverIndex]));
    const roverY = Math.max(padT + 16, Math.min(padT + plotH - 8, ys[roverIndex] - 10));
    context.fillStyle = "#d7fff8";
    context.fillRect(roverX - 12, roverY - 8, 24, 10);
    context.beginPath();
    context.arc(roverX - 7, roverY + 4, 4, 0, Math.PI * 2);
    context.arc(roverX + 7, roverY + 4, 4, 0, Math.PI * 2);
    context.fillStyle = "#16323a";
    context.fill();
    context.strokeStyle = "#9af6ff";
    context.beginPath();
    context.moveTo(roverX + 6, roverY - 8);
    context.lineTo(roverX + 12, roverY - 16);
    context.stroke();
    context.restore();
    context.fillStyle = "#b7d2c0";
    context.fillRect(xs[0] - 2, Math.max(padT, ys[0] - 16), 3, 16);
    context.fillStyle = "#ffb4b8";
    context.fillRect(xs[xs.length - 1] - 2, Math.max(padT, ys[ys.length - 1] - 16), 3, 16);
    context.fillStyle = "#d5e6ef";
    context.font = "12px Segoe UI, Arial";
    context.fillText(usingAdvisory ? "Preview path · not cleared" : "Route the rover can attempt", padL, 18);
    if (readout) {
        readout.textContent = "Rover limit " + limit + "°. Tallest sampled slope " +
            tallest.toFixed(1) + "°. " + spikes + " spike" + (spikes === 1 ? "" : "s") +
            " steeper than the rover. " +
            (usingAdvisory ? "This amber case is a preview, not a cleared route." : "Start flag is green, destination flag is red.");
    }
}
let sunSweep = 0;
function latitudeTemperature(lat, hour) {
    const daylight = Math.max(Math.cos(lat * Math.PI / 180), 0);
    const dayK = 100 + 300 * Math.pow(daylight, 0.25);
    const nightK = 40 + 60 * daylight;
    const sine = Math.cos(lat * Math.PI / 180) * Math.cos(hour);
    const elevation = Math.asin(Math.max(-1, Math.min(1, sine)));
    const kelvin = elevation <= 0
        ? nightK
        : nightK + (dayK - nightK) * Math.pow(Math.sin(elevation), 0.25);
    return kelvin - 273.15;
}
function drawSunCanvas(canvasId) {
    const canvas = document.getElementById(canvasId);
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted) return;
    const {context, width, height} = fitted;
    context.clearRect(0, 0, width, height);
    const bands = [
        {lat: 0, color: "#e2a15a", label: "Equator"},
        {lat: 45, color: "#79c7e8", label: "45°"},
        {lat: 85, color: "#d7fff8", label: "85°"}
    ];
    const left = 48, right = 12, top = 16, bottom = 28;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const yFor = value => top + plotH * (1 - (value + 240) / 380);
    context.font = "12px Segoe UI, Arial";
    context.strokeStyle = "#1c3040";
    context.fillStyle = "#8fb0bf";
    [-200, -100, 0, 100].forEach(mark => {
        const y = yFor(mark);
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(width - right, y);
        context.stroke();
        context.fillText(String(mark), 4, y + 4);
    });
    bands.forEach(band => {
        context.beginPath();
        for (let step = 0; step <= 90; step += 1) {
            const t = step / 90;
            const x = left + plotW * t;
            const y = yFor(latitudeTemperature(band.lat, -Math.PI + Math.PI * 2 * t));
            if (step === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
        }
        context.strokeStyle = band.color;
        context.lineWidth = 3;
        context.shadowColor = band.color;
        context.shadowBlur = 8;
        context.stroke();
        context.shadowBlur = 0;
        const x = left + plotW * sunSweep;
        const y = yFor(latitudeTemperature(band.lat, -Math.PI + Math.PI * 2 * sunSweep));
        context.fillStyle = "#fff";
        context.beginPath();
        context.arc(x, y, 4, 0, Math.PI * 2);
        context.fill();
    });
    bands.forEach((band, index) => {
        const x = left + index * 110;
        context.fillStyle = band.color;
        context.fillRect(x, height - 16, 14, 8);
        context.fillStyle = "#f4fbff";
        context.fillText(band.label, x + 18, height - 8);
    });
}
function driveTheRover() {
    roverDrive = (performance.now() % 12000) / 12000;
    sunSweep = (performance.now() % 16000) / 16000;
    if (document.body.dataset.view === "movement" && latestTerrainPayload) {
        drawElevationProfile(latestTerrainPayload);
    }
    drawSunCanvas("sun-preview");
    drawSunCanvas("sun-compare");
    requestAnimationFrame(driveTheRover);
}
requestAnimationFrame(driveTheRover);
{% if image_result and image_result.nearby and image_result.nearby.look %}
const imageLook = {{ image_result.nearby.look|tojson }};
const imageDustTraps = {{ image_result.nearby.dust_traps|tojson }};
{% else %}
const imageLook = [];
const imageDustTraps = [];
{% endif %}
const imageLabel = {{ image_result.label|tojson if image_result else "null" }};
function classifyGround(cells) {
    if (!cells.length) return [];
    const heights = cells.map(cell => cell.elev_km).slice().sort((a, b) => a - b);
    const cut = heights[Math.floor((heights.length - 1) * 0.3)];
    return cells.map(cell => ({
        elev_km: cell.elev_km,
        slope: cell.slope,
        dust: cell.elev_km <= cut && cell.slope < 12,
        spike: cell.slope >= 12
    }));
}
function drawDustLook(payload) {
    const canvas = document.getElementById("dust-look");
    const readout = document.getElementById("dust-look-readout");
    const chips = document.getElementById("dust-hazard-chips");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted) return;
    const {context, width, height} = fitted;
    const fromPhoto = imageLook.length > 0;
    const cells = classifyGround(fromPhoto ? imageLook : ((payload && payload.area_scan) || []));
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#071018";
    context.fillRect(0, 0, width, height);
    if (chips) chips.replaceChildren();
    const addChip = text => {
        if (!chips) return;
        const chip = document.createElement("span");
        chip.className = "score";
        chip.textContent = text;
        chips.appendChild(chip);
    };
    if (imageLabel) addChip("Picture label: " + imageLabel);
    imageDustTraps.slice(0, 3).forEach(trap => {
        addChip("Dust can settle · " + trap.elev_km + " km · " + trap.slope + "°");
    });
    if (!cells.length) {
        context.fillStyle = "#d5e6ef";
        context.font = "13px Segoe UI, Arial";
        context.fillText("Waiting for the area around the route.", 16, 32);
        if (readout) readout.textContent = "The hillshade appears after the terrain map loads.";
        return;
    }
    const columns = Math.max(1, Math.round(Math.sqrt(cells.length)));
    const rows = Math.ceil(cells.length / columns);
    const elev = cells.map(cell => cell.elev_km);
    const finite = elev.filter(value => Number.isFinite(value));
    const minE = Math.min.apply(null, finite);
    const maxE = Math.max.apply(null, finite);
    const span = Math.max(0.0001, maxE - minE);
    const shade = document.createElement("canvas");
    shade.width = columns;
    shade.height = rows;
    const image = shade.getContext("2d").createImageData(columns, rows);
    for (let row = 0; row < rows; row += 1) {
        for (let col = 0; col < columns; col += 1) {
            const index = row * columns + col;
            const here = Number.isFinite(elev[index]) ? elev[index] : minE;
            const west = col ? elev[index - 1] : here;
            const north = row ? elev[index - columns] : here;
            const light = Math.max(0.28, Math.min(1, 0.62 + ((here - west) * 0.8 - (here - north)) / span * 4));
            const tone = (here - minE) / span;
            const pixel = index * 4;
            image.data[pixel] = Math.round((48 + tone * 90) * light);
            image.data[pixel + 1] = Math.round((58 + tone * 72) * light);
            image.data[pixel + 2] = Math.round((64 + tone * 40) * light);
            image.data[pixel + 3] = 255;
        }
    }
    shade.getContext("2d").putImageData(image, 0, 0);
    const plotX = 12, plotY = 24, plotW = width - 24, plotH = height - 48;
    context.imageSmoothingEnabled = false;
    context.drawImage(shade, plotX, plotY, plotW, plotH);
    context.strokeStyle = "rgba(244, 251, 255, 0.85)";
    context.lineWidth = 1.5;
    const cellW = plotW / columns;
    const cellH = plotH / rows;
    for (let level = 1; level <= 4; level += 1) {
        const cut = minE + span * level / 5;
        context.beginPath();
        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < columns; col += 1) {
                const here = elev[row * columns + col];
                if (!Number.isFinite(here)) continue;
                const east = col + 1 < columns ? elev[row * columns + col + 1] : NaN;
                const south = row + 1 < rows ? elev[(row + 1) * columns + col] : NaN;
                if (Number.isFinite(east) && (here - cut) * (east - cut) <= 0) {
                    const fraction = (cut - here) / ((east - here) || 1);
                    const x = plotX + (col + fraction) * cellW;
                    context.moveTo(x, plotY + row * cellH);
                    context.lineTo(x, plotY + (row + 1) * cellH);
                }
                if (Number.isFinite(south) && (here - cut) * (south - cut) <= 0) {
                    const fraction = (cut - here) / ((south - here) || 1);
                    const y = plotY + (row + fraction) * cellH;
                    context.moveTo(plotX + col * cellW, y);
                    context.lineTo(plotX + (col + 1) * cellW, y);
                }
            }
        }
        context.stroke();
    }
    cells.forEach((cell, index) => {
        if (!cell.spike) return;
        const column = index % columns;
        const row = Math.floor(index / columns);
        context.fillStyle = "#ff6b73";
        context.fillRect(plotX + column * cellW + cellW - 7, plotY + row * cellH + 3, 5, 5);
    });
    const dusty = cells.filter(cell => cell.dust).length;
    const steep = cells.filter(cell => cell.spike).length;
    if (!imageDustTraps.length && dusty) addChip(dusty + " low gentle cells where dust can settle");
    if (steep) addChip(steep + " cells steeper than 12°");
    context.fillStyle = "#d5e6ef";
    context.font = "12px Segoe UI, Arial";
    context.fillText(minE.toFixed(2) + " km", 14, height - 10);
    const highLabel = maxE.toFixed(2) + " km";
    context.fillText(highLabel, width - 16 - context.measureText(highLabel).width, 16);
    if (readout) {
        readout.textContent = (fromPhoto ? "Around the photo GPS. " : "Around the route. ") +
            "Light comes from the upper left. Brighter ground is higher. White lines are equal height. Red marks are 12° or steeper.";
    }
}
window.addEventListener("resize", () => {
    if (latestTerrainPayload) {
        drawElevationProfile(latestTerrainPayload);
        drawDustLook(latestTerrainPayload);
    } else {
        drawDustLook(null);
    }
    if (latestEnvironment) {
        drawTemperature(latestEnvironment);
        drawRadiation(latestEnvironment);
    }
});
requestAnimationFrame(() => drawDustLook(null));

const galleryDialog = document.getElementById("gallery-dialog");
const sourcesDialog = document.getElementById("sources-dialog");
document.getElementById("sources-open").addEventListener("click", () => sourcesDialog.showModal());
document.querySelectorAll("[data-close-dialog]").forEach(button => {
    button.addEventListener("click", () =>
        document.getElementById(button.dataset.closeDialog).close()
    );
});
document.querySelectorAll("dialog").forEach(dialog => {
    dialog.addEventListener("click", event => {
        if (event.target === dialog) dialog.close();
    });
});

let nasaGalleryLoaded = false;
document.getElementById("gallery-open").addEventListener("click", () => {
    galleryDialog.showModal();
    if (nasaGalleryLoaded) return;
    const galleryStatus = document.getElementById("gallery-status");
    const galleryGrid = document.getElementById("gallery-grid");
    galleryStatus.className = "note";
    galleryStatus.textContent = "Searching NASA's public image catalogâ€¦";
    fetch("/api/nasa-images")
        .then(async response => {
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "NASA image catalog is unavailable.");
            return payload;
        })
        .then(payload => {
            const items = payload.items || [];
            nasaGalleryLoaded = true;
            galleryGrid.replaceChildren();
            if (!items.length) {
                galleryStatus.textContent = "NASA's catalog returned no lunar reference images for this query.";
                return;
            }
            galleryStatus.textContent = items.length +
                " lunar reference images from NASA. None are verified against the selected coordinates.";
            items.forEach(item => {
                const card = document.createElement("article");
                card.className = "gallery-card";
                const image = document.createElement("img");
                image.src = item.image_url;
                image.alt = item.title;
                image.loading = "lazy";
                const copy = document.createElement("div");
                copy.className = "gallery-card-copy";
                const title = document.createElement("strong");
                title.textContent = item.title;
                const description = document.createElement("p");
                description.textContent = item.description || item.match_label;
                const link = document.createElement("a");
                link.href = item.details_url;
                link.target = "_blank";
                link.rel = "noopener";
                link.textContent = "NASA record" + (item.date_created ? " · " + item.date_created : "");
                copy.append(title, description, link);
                card.append(image, copy);
                galleryGrid.appendChild(card);
            });
        })
        .catch(error => {
            galleryStatus.className = "warning";
            galleryStatus.textContent = error.message;
        });
});
let routeLayer = null;
let roverMarker = null;
let roverFrame = 0;
function startRoverOnMap(path) {
    const points = (Array.isArray(path) ? path : []).map(item => {
        if (!item) return [NaN, NaN];
        const lat = Number(Array.isArray(item) ? item[0] : item.lat);
        const lon = Number(Array.isArray(item) ? item[1] : item.lon);
        return [lat, lon];
    }).filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]));
    if (roverFrame) cancelAnimationFrame(roverFrame);
    if (roverMarker) {
        map.removeLayer(roverMarker);
        roverMarker = null;
    }
    if (points.length < 2) return;
    roverMarker = L.marker(points[0], {
        icon: L.divIcon({className: "rover-pin", html: "<span></span>", iconSize: [22, 18], iconAnchor: [11, 10]}),
        interactive: false,
        zIndexOffset: 800
    }).addTo(map);
    const started = performance.now();
    const step = now => {
        if (!roverMarker) return;
        const t = ((now - started) % 12000) / 12000;
        const pos = t * (points.length - 1);
        const index = Math.min(points.length - 2, Math.floor(pos));
        const fraction = Math.max(0, Math.min(1, pos - index));
        const start = points[index];
        const end = points[Math.min(index + 1, points.length - 1)];
        roverMarker.setLatLng([
            start[0] + (end[0] - start[0]) * fraction,
            start[1] + (end[1] - start[1]) * fraction
        ]);
        roverFrame = requestAnimationFrame(step);
    };
    roverFrame = requestAnimationFrame(step);
}
let routeHaloLayer = null;
let directRouteLayer = null;
let advisoryRouteLayer = null;
let hazardLayer = null;
let plumeEnvelopeLayer = null;
let plumeSourceMarker = null;
let photoMarker = null;
let fallbackMarker = null;
let currentMapBounds = null;
let hazardsVisible = true;
let latestPlumeAssessment = null;
let routeInputsDirty = false;
const photoLocation = {{ photo_location|tojson }};
const imageNeedsAreaGuess = {{ (image_result is not none and not image_result.location)|tojson }};
const makeWaypointIcon = (label, kind) => L.divIcon({
    className: "waypoint-icon-wrap",
    html: '<span class="waypoint-pin ' + kind + '"><span>' + label + '</span></span>',
    iconSize: [38, 38],
    iconAnchor: [19, 19]
});
const startMarker = L.marker([{{ start_lat }}, {{ start_lon }}], {
    icon: makeWaypointIcon("R", "start"), title: "Rover start"
}).addTo(map);
const destMarker = L.marker([{{ dest_lat }}, {{ dest_lon }}], {
    icon: makeWaypointIcon("D", "destination"), title: "Destination"
}).addTo(map);
startMarker.bindPopup("START · " + {{ start_name|tojson }});
destMarker.bindPopup("DESTINATION · " + {{ dest_name|tojson }});
document.getElementById("hazard-toggle").addEventListener("click", event => {
    hazardsVisible = !hazardsVisible;
    event.currentTarget.setAttribute("aria-pressed", String(hazardsVisible));
    event.currentTarget.textContent = hazardsVisible ? "Hazards · ON" : "Hazards · OFF";
    if (!hazardLayer) return;
    if (hazardsVisible) hazardLayer.addTo(map);
    else map.removeLayer(hazardLayer);
});
document.getElementById("center-map").addEventListener("click", () => {
    if (currentMapBounds) map.fitBounds(currentMapBounds, {padding:[25,25], maxZoom:8});
});
const plumeScreenButton = document.getElementById("screen-plume");
const plumeScreenResult = document.getElementById("plume-screen-result");
plumeScreenButton.addEventListener("click", async () => {
    const terrain = latestTerrainPayload;
    const route = terrain && terrain.route_available
        ? terrain.route
        : terrain && terrain.advisory_route;
    if (!route || route.length < 2) {
        plumeScreenResult.className = "warning";
        plumeScreenResult.textContent = "No candidate route is available to screen.";
        return;
    }
    const requiredFields = [
        "plume_source_lat", "plume_source_lon", "plume_azimuth",
        "plume_extent", "plume_half_width"
    ];
    if (requiredFields.some(id => !document.getElementById(id).value.trim())) {
        plumeScreenResult.className = "warning";
        plumeScreenResult.textContent = "Enter the source coordinates, axis azimuth, downrange extent, and cross-track half-width.";
        return;
    }
    const requestBody = {
        route_lat_lon: route,
        source_latitude: Number(document.getElementById("plume_source_lat").value),
        source_longitude: Number(document.getElementById("plume_source_lon").value),
        axis_azimuth_degrees: Number(document.getElementById("plume_azimuth").value),
        downrange_extent_km: Number(document.getElementById("plume_extent").value),
        cross_track_half_width_km: Number(document.getElementById("plume_half_width").value),
        evidence_source: document.getElementById("plume_evidence_source").value.trim()
    };
    plumeScreenButton.disabled = true;
    plumeScreenResult.className = "note";
    plumeScreenResult.textContent = "Screening the route against the entered corridorâ€¦";
    try {
        const response = await fetch("/api/dust-plume-screen", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify(requestBody)
        });
        const assessment = await response.json();
        if (!response.ok) throw new Error(assessment.error || "Plume screen failed.");
        latestPlumeAssessment = assessment;
        drawPlumeAssessment(assessment);
        paintOpsBoard();
        const routeKind = terrain.route_available
            ? "slope-constrained DEM route"
            : "least-risk preview route (not cleared)";
        const evidenceNote = assessment.evidence_source
            ? " Envelope basis: " + assessment.evidence_source + "."
            : " No event or simulation reference was supplied.";
        plumeScreenResult.className = assessment.overlap ? "warning" : "note";
        plumeScreenResult.textContent =
            (assessment.overlap ? "CORRIDOR OVERLAP" : "NO OVERLAP UNDER ENTERED ENVELOPE") +
            " · " + routeKind + " · " +
            assessment.route_segments_intersecting_envelope + " intersecting segments · " +
            assessment.minimum_route_separation_km + " km minimum geometric separation. " +
            assessment.interpretation + evidenceNote +
            " No plume probability or deposition is estimated.";
        document.getElementById("plume-detail").textContent =
            assessment.overlap
                ? "Plume corridor overlap · user-defined scenario"
                : "No geometric overlap · not a no-exposure finding";
    } catch (error) {
        plumeScreenResult.className = "warning";
        plumeScreenResult.textContent = "Plume corridor screen failed: " + error.message;
    } finally {
        const current = latestTerrainPayload;
        const currentRoute = current && current.route_available
            ? current.route
            : current && current.advisory_route;
        plumeScreenButton.disabled =
            routeInputsDirty || !currentRoute || currentRoute.length < 2;
    }
});
const exportAssessmentButton = document.getElementById("export-assessment");
[
    "start_name", "start_lat", "start_lon",
    "dest_name", "dest_lat", "dest_lon",
    "max_slope_degrees", "planning_speed_kmh"
].forEach(id => {
    document.getElementById(id).addEventListener("input", () => {
        routeInputsDirty = true;
        exportAssessmentButton.disabled = true;
        plumeScreenButton.disabled = true;
        plumeScreenResult.className = "note";
        plumeScreenResult.textContent =
            "Route inputs changed. Recalculate the traverse before screening a plume corridor or exporting evidence.";
        document.getElementById("plume-detail").textContent =
            "Route inputs changed · recalculate before plume screening";
    });
});
exportAssessmentButton.addEventListener("click", () => {
    if (!latestTerrainPayload || routeInputsDirty) return;
    const payload = latestTerrainPayload;
    const selectedRoute = payload.route_available ? payload.route : payload.advisory_route;
    const hasCandidateRoute = selectedRoute && selectedRoute.length > 1;
    const report = {
        schema: "zero-point-lunar.route-assessment.v1",
        exported_at_utc: new Date().toISOString(),
        mission: {
            start: {
                name: document.getElementById("start_name").value,
                latitude_degrees: Number(document.getElementById("start_lat").value),
                longitude_degrees: Number(document.getElementById("start_lon").value)
            },
            destination: {
                name: document.getElementById("dest_name").value,
                latitude_degrees: Number(document.getElementById("dest_lat").value),
                longitude_degrees: Number(document.getElementById("dest_lon").value)
            },
            planning_assumptions: {
                maximum_slope_degrees: payload.max_slope_degrees,
                speed_km_per_hour: payload.planning_speed_kmh
            }
        },
        decision: {
            status: payload.route_available
                ? "slope-constrained DEM route"
                : hasCandidateRoute ? "preview only; no slope-constrained route" : "route unavailable",
            route_message: payload.route_message,
            direct_distance_km: payload.straight_line_distance_km,
            selected_path_distance_km: hasCandidateRoute
                ? payload.route_available ? payload.route_distance_km : payload.advisory_distance_km
                : null,
            selected_path_lat_lon: hasCandidateRoute ? selectedRoute : [],
            route_screen: payload.route_assessment,
            hazard_counts: payload.hazard_counts,
            plume_corridor_screen: latestPlumeAssessment
        },
        data: {
            terrain_model: payload.terrain,
            grid_size: payload.grid_size,
            radius_km: payload.radius_km,
            source: "NASA LRO LOLA LDEM 16 elevation with LROC color context",
            references: [
                "https://trek.nasa.gov/moon/",
                "https://quickmap.lroc.asu.edu/",
                "https://pds-geosciences.wustl.edu/missions/lro/",
                "https://ntrs.nasa.gov/citations/20180001348",
                "https://ntrs.nasa.gov/citations/20240009989",
                "https://ntrs.nasa.gov/citations/20250005201",
                "https://ntrs.nasa.gov/citations/20220018746",
                ...REFERENCE_LINKS.map(link => link.url)
            ]
        },
        limitations: [
            "LOLA LDEM 16 is about 1.9 km per pixel; small rocks and boulders are unresolved.",
            "A DEM route screen is not a safety certification or rover clearance.",
            "Route and time are planning estimates; no rover or satellite telemetry is connected.",
            "No plume gas-flow, particle-trajectory, or deposition simulation is connected; the plume overlay is a user-defined geometry screen."
        ]
    };
    const file = new Blob([JSON.stringify(report, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "zero-point-lunar-assessment-" +
        new Date().toISOString().replace(/[:.]/g, "-") + ".json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
});

let terrainViews = [];
let currentTerrainView = 0;
const cameraImage = document.getElementById("camera-image");
const cameraStatus = document.getElementById("camera-status");
const cameraViewName = document.getElementById("camera-view-name");

function showTerrainView(index) {
    if (!terrainViews.length) return;
    currentTerrainView = (index + terrainViews.length) % terrainViews.length;
    const view = terrainViews[currentTerrainView];
    cameraImage.src = view.url;
    cameraImage.hidden = false;
    cameraStatus.hidden = true;
    cameraViewName.textContent = view.label;
    document.querySelector(".camera-meta span").textContent =
        "CAM " + String(currentTerrainView + 1).padStart(2, "0") + " / " +
        String(terrainViews.length).padStart(2, "0");
    Array.from(document.querySelectorAll(".camera-dot")).forEach((dot, dotIndex) => {
        dot.setAttribute("aria-current", String(dotIndex === currentTerrainView));
    });
}

async function loadTerrainViews() {
    cameraStatus.hidden = false;
    cameraStatus.textContent = "Rendering target-area views from LRO color and LOLA elevationâ€¦";
    try {
        const response = await fetch("/api/terrain-views");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Terrain views are unavailable.");
        terrainViews = payload.views;
        document.querySelectorAll("[data-source-view]").forEach(image => {
            const sourceView = terrainViews[Number(image.dataset.sourceView)];
            if (sourceView) image.src = sourceView.url;
        });
        const dots = document.getElementById("camera-dots");
        dots.replaceChildren();
        terrainViews.forEach((view, index) => {
            const dot = document.createElement("button");
            dot.className = "camera-dot";
            dot.type = "button";
            dot.title = view.label;
            dot.setAttribute("aria-label", view.label);
            dot.setAttribute("aria-current", "false");
            dot.addEventListener("click", () => showTerrainView(index));
            dots.appendChild(dot);
        });
        showTerrainView(0);
        const hero = document.getElementById("site-photo");
        const caption = document.getElementById("site-photo-caption");
        if (hero && terrainViews[0]) hero.alt = terrainViews[0].label + " view of the target area";
        if (caption && payload.location) {
            caption.textContent = "LROC color and LOLA elevation at " +
                payload.location.latitude + "°, " + payload.location.longitude +
                "°. Regional render, not a picture of one rock.";
        }
    } catch (error) {
        cameraStatus.textContent = error.message;
    }
}

document.getElementById("camera-prev").addEventListener("click", () =>
    showTerrainView(currentTerrainView - 1)
);
document.getElementById("camera-next").addEventListener("click", () =>
    showTerrainView(currentTerrainView + 1)
);
cameraImage.addEventListener("error", () => {
    cameraImage.hidden = true;
    cameraStatus.hidden = false;
    cameraStatus.textContent = "Rendered view could not be loaded.";
});

const canvas = document.getElementById("terrain-canvas");
const status = document.getElementById("model-status");
const terrainSummary = document.getElementById("terrain-summary");
let renderer, scene, camera, controls, modelGroup, surfaceMaterial;
let routeLength = null;
let reliefTargets = [];
const defaultReliefExaggeration = 2;
const modelPanel = document.getElementById("terrain-model-panel");
const expandModelButton = document.getElementById("expand-model");
expandModelButton.addEventListener("click", () => {
    const expanded = modelPanel.classList.toggle("is-expanded");
    expandModelButton.setAttribute("aria-pressed", String(expanded));
    expandModelButton.textContent = expanded ? "Close expanded model" : "Expand model";
});
document.addEventListener("keydown", event => {
    if (event.key === "Escape" && modelPanel.classList.contains("is-expanded")) {
        modelPanel.classList.remove("is-expanded");
        expandModelButton.setAttribute("aria-pressed", "false");
        expandModelButton.textContent = "Expand model";
    }
});

const imageInput = document.getElementById("image");
const imagePreview = document.getElementById("image-preview");
const imagePreviewImage = document.getElementById("image-preview-img");
let previewUrl = null;
imageInput.addEventListener("change", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const file = imageInput.files && imageInput.files[0];
    if (!file) {
        imagePreview.hidden = true;
        imagePreviewImage.removeAttribute("src");
        return;
    }
    previewUrl = URL.createObjectURL(file);
    imagePreviewImage.src = previewUrl;
    imagePreview.hidden = false;
});
document.getElementById("image-enhance").addEventListener("change", event => {
    imagePreviewImage.classList.toggle("enhanced", event.target.checked);
});
imageInput.addEventListener("change", () => {
    const gpsState = document.getElementById("photo-gps-state");
    gpsState.textContent = imageInput.files && imageInput.files.length
        ? "Image selected. EXIF GPS will be read automatically on analysis; if it is absent, the photo location stays unknown."
        : "EXIF GPS is checked automatically after upload. If the photo has no GPS, this app does not invent a location.";
});

function registerReliefGeometry(geometry, relief, recomputeNormals = false) {
    const positions = geometry.attributes.position;
    const baseZ = new Float32Array(relief.length);
    for (let i = 0; i < relief.length; i++) {
        baseZ[i] = positions.array[i * 3 + 2] - relief[i] * defaultReliefExaggeration;
    }
    reliefTargets.push({geometry, relief, baseZ, recomputeNormals});
}

function registerReliefObject(object, relief) {
    reliefTargets.push({
        object,
        relief,
        baseZ: object.position.z - relief * defaultReliefExaggeration
    });
}

function updateRelief(scale) {
    for (const target of reliefTargets) {
        if (target.geometry) {
            const positions = target.geometry.attributes.position;
            for (let i = 0; i < target.relief.length; i++) {
                positions.array[i * 3 + 2] = target.baseZ[i] + target.relief[i] * scale;
            }
            positions.needsUpdate = true;
            if (target.recomputeNormals) target.geometry.computeVertexNormals();
        } else {
            target.object.position.z = target.baseZ + target.relief * scale;
        }
    }
}

function showFailure(message) {
    status.textContent = message;
    document.getElementById("route-status").textContent = "Analysis unavailable";
    terrainSummary.textContent = "Terrain mesh unavailable";
}

async function loadTerrain() {
    const fields = ["start_lat", "start_lon", "dest_lat", "dest_lon"];
    const values = fields.map(name => document.getElementById(name).value);
    if (values.some(value => value === "" || !Number.isFinite(Number(value)))) {
        showFailure("Enter valid start and destination coordinates.");
        return;
    }
    const queryValues = Object.fromEntries(fields.map((name, i) => [name, values[i]]));
    queryValues.dest_name = document.getElementById("dest_name").value;
    queryValues.max_slope_degrees = document.getElementById("max_slope_degrees").value;
    queryValues.planning_speed_kmh = document.getElementById("planning_speed_kmh").value;
    const priority = document.getElementById("brief-priority");
    queryValues.path_priority = priority ? priority.value : "slope";
    const query = new URLSearchParams(queryValues);
    try {
        const response = await fetch("/api/terrain?" + query.toString());
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Terrain analysis failed.");
        opsTerrain = payload;
        topoPayload = payload;
        syncCraterTerrainViews(payload);
        drawTerrain(payload);
        mountTopo(payload);
        drawMap(payload);
        paintOpsBoard();
        const cost = document.getElementById("plan-cost");
        if (cost) {
            const cleared = payload.route_available;
            const km = cleared ? payload.route_distance_km : payload.advisory_distance_km;
            const vehicle = document.getElementById("plan-vehicle").selectedOptions[0].textContent;
            const pad = document.getElementById("plan-pad").selectedOptions[0].textContent;
            const place = document.getElementById("plan-destination").selectedOptions[0].dataset.name;
            cost.textContent = place + " · " + vehicle + " from " + pad + ". " +
                (cleared ? "A* path " : "A* preview, not cleared, ") +
                (km != null ? Number(km).toFixed(2) + " km. " : "") +
                (payload.route_message || "");
        }
        loadTerrainViews();
    } catch (error) {
        showFailure(error.message);
    }
}

function drawPlumeAssessment(assessment) {
    if (plumeEnvelopeLayer) map.removeLayer(plumeEnvelopeLayer);
    if (plumeSourceMarker) map.removeLayer(plumeSourceMarker);
    const envelope = assessment.envelope;
    plumeEnvelopeLayer = L.polygon(envelope.polygon_lat_lon, {
        color:"#c39cff", weight:2, dashArray:"6 5",
        fillColor:"#b27dff", fillOpacity:.22
    }).bindPopup("User-defined plume corridor · geometric scenario only").addTo(map);
    plumeSourceMarker = L.circleMarker(
        [envelope.source_latitude, envelope.source_longitude],
        {radius:5, color:"#f2d8ff", fillColor:"#b27dff", fillOpacity:1, weight:2}
    ).bindPopup("User-provided plume source · not an observed event unless cited").addTo(map);
    if (currentMapBounds) {
        currentMapBounds.extend(plumeEnvelopeLayer.getBounds());
        currentMapBounds.extend(plumeSourceMarker.getLatLng());
    }
}

function drawMap(payload) {
    latestTerrainPayload = payload;
    routeInputsDirty = false;
    exportAssessmentButton.disabled = false;
    if (plumeEnvelopeLayer) map.removeLayer(plumeEnvelopeLayer);
    if (plumeSourceMarker) map.removeLayer(plumeSourceMarker);
    plumeEnvelopeLayer = null;
    plumeSourceMarker = null;
    latestPlumeAssessment = null;
    const candidateRoute = payload.route_available ? payload.route : payload.advisory_route;
    plumeScreenButton.disabled = !candidateRoute || candidateRoute.length < 2;
    plumeScreenResult.className = "note";
    plumeScreenResult.textContent = candidateRoute && candidateRoute.length > 1
        ? "Route updated. Enter plume-source coordinates and a documented or illustrative corridor to screen."
        : "A candidate route is not available for plume screening.";
    document.getElementById("plume-detail").textContent =
        "Dust check ready when plume details are entered in Moon dust.";
    startMarker.setLatLng([Number(document.getElementById("start_lat").value), Number(document.getElementById("start_lon").value)]);
    destMarker.setLatLng([Number(document.getElementById("dest_lat").value), Number(document.getElementById("dest_lon").value)]);
    if (routeLayer) map.removeLayer(routeLayer);
    if (routeHaloLayer) map.removeLayer(routeHaloLayer);
    if (directRouteLayer) map.removeLayer(directRouteLayer);
    if (advisoryRouteLayer) map.removeLayer(advisoryRouteLayer);
    if (hazardLayer) map.removeLayer(hazardLayer);
    if (fallbackMarker) map.removeLayer(fallbackMarker);
    routeLayer = null;
    routeHaloLayer = null;
    advisoryRouteLayer = null;
    hazardLayer = null;
    directRouteLayer = L.polyline([
        startMarker.getLatLng(),
        destMarker.getLatLng()
    ], {color:"#e5edf2", weight:1.5, opacity:.55, dashArray:"2 8"}).addTo(map);
    if (payload.route_available && payload.route.length > 1) {
        routeHaloLayer = L.polyline(payload.route, {color:"#06151b", weight:8, opacity:0.9}).addTo(map);
        routeLayer = L.polyline(payload.route, {color:"#53e0d0", weight:3, opacity:1}).addTo(map);
        startRoverOnMap(payload.route);
    } else if (payload.advisory_route && payload.advisory_route.length > 1) {
        advisoryRouteLayer = L.polyline(payload.advisory_route, {
            color:"#f4bd65", weight:5, opacity:.95, dashArray:"10 7"
        }).bindPopup("Least-risk terrain preview · not safety-cleared").addTo(map);
        startRoverOnMap(payload.advisory_route);
    } else {
        startRoverOnMap([]);
    }
    hazardLayer = L.layerGroup(payload.hazards.map(hazard => {
        const color = complexityColor(hazard.complexity);
        const layers = [];
        if (hazard.footprint && hazard.footprint.length) {
            layers.push(L.polygon(hazard.footprint, {
                color, weight:1.5, opacity:.8, fillColor:color, fillOpacity:.2
            }));
        }
        layers.push(L.circleMarker([hazard.lat, hazard.lon], {
            radius: hazard.risk_level === "critical" ? 8 : hazard.risk_level === "high" ? 6 : 4,
            color, fillColor:color,
            fillOpacity: 0.95, weight: 2, className:"hazard-marker"
        }).bindPopup(hazard.kind + " · " + hazard.slope + "° slope · " +
            hazard.roughness_m + " m relief · " + hazard.complexity + "% relative complexity" +
            (hazard.risk_level === "critical" ? " · provisional critical flag" : "")));
        return layers;
    }).flat());
    if (hazardsVisible) hazardLayer.addTo(map);
    const fallbackNote = document.getElementById("image-fallback-note");
    if (imageNeedsAreaGuess && !photoLocation && fallbackNote) {
        if (payload.hazards.length) {
            const candidate = payload.hazards.reduce((best, hazard) =>
                hazard.complexity > best.complexity ? hazard : best
            );
            fallbackMarker = L.marker([candidate.lat, candidate.lon], {
                icon:makeWaypointIcon("?", "candidate"), title:"DEM screening candidate"
            }).bindPopup("DEM screening candidate · " + candidate.complexity +
                "% relative DEM complexity. Not an image geolocation.").addTo(map);
            fallbackNote.textContent = "Fallback candidate: " + candidate.kind + " near " +
                candidate.lat.toFixed(3) + "°, " + candidate.lon.toFixed(3) +
                "° (" + candidate.complexity +
                "% relative complexity). This is the highest-ranked area in the selected map window, not a model-derived photo location.";
            fallbackNote.hidden = false;
        } else {
            fallbackNote.textContent = "No qualifying DEM hazard area was found in the selected map window, so no fallback candidate is available.";
            fallbackNote.hidden = false;
        }
    }
    if (photoLocation) {
        if (photoMarker) map.removeLayer(photoMarker);
        photoMarker = L.marker([photoLocation.lat, photoLocation.lon], {
            icon:makeWaypointIcon("GPS", "photo"), title:"Image EXIF GPS location"
        }).bindPopup("Image GPS location · nearby DEM terrain context").addTo(map);
    }
    const displayRouteLayer = routeLayer || advisoryRouteLayer || directRouteLayer;
    const points = displayRouteLayer ? displayRouteLayer.getBounds() : L.latLngBounds([]);
    points.extend(startMarker.getLatLng());
    points.extend(destMarker.getLatLng());
    if (photoMarker) points.extend(photoMarker.getLatLng());
    if (fallbackMarker) points.extend(fallbackMarker.getLatLng());
    currentMapBounds = points;
    if (map.getSize().x > 0 && map.getSize().y > 0) {
        map.fitBounds(currentMapBounds, {padding:[25,25], maxZoom:8});
    }
    const hasCandidateRoute = payload.route_available ||
        (payload.advisory_route && payload.advisory_route.length > 1);
    routeLength = payload.route_available
        ? payload.route_distance_km
        : payload.advisory_distance_km;
    const directDistance = payload.straight_line_distance_km || 0;
    const planningSpeed = payload.planning_speed_kmh;
    const slopeLimit = payload.max_slope_degrees;
    document.getElementById("mission-direct-distance").textContent =
        directDistance.toFixed(2) + " km";
    document.getElementById("mission-speed").textContent =
        planningSpeed + " km/h assumption";
    document.getElementById("planning-speed-status").textContent =
        planningSpeed + " km/h assumption";
    document.getElementById("slope-limit-status").textContent =
        slopeLimit + "° threshold";
    document.getElementById("distance-value").textContent = payload.route_available
        ? routeLength.toFixed(2) + " km"
        : hasCandidateRoute ? routeLength.toFixed(2) + " km · preview" : "Unavailable";
    const estimatedHours = hasCandidateRoute ? routeLength / planningSpeed : null;
    document.getElementById("mission-eta-value").textContent =
        estimatedHours === null ? "Unavailable" : estimatedHours.toFixed(1) + " h · estimate";
    const routeStatus = document.getElementById("route-status");
    routeStatus.textContent = payload.route_available
        ? routeLength.toFixed(2) + " km · DEM route"
        : hasCandidateRoute
            ? "No safe route · preview only"
            : "No route · hazard flagged";
    document.getElementById("route-detail").textContent = payload.route_available
        ? "Planned distance " + routeLength.toFixed(2) + " km"
        : (payload.route_message || "No route meets the current slope constraint.") +
            (hasCandidateRoute ? " Least-risk preview: " + routeLength.toFixed(2) +
                " km · not safety-cleared." : "");
    document.getElementById("hazard-summary").textContent =
        payload.hazards.length + " terrain areas · " + payload.hazard_counts.severe + " severe";
    document.getElementById("hazard-detail").textContent =
        payload.hazard_counts.moderate + " moderate · " + payload.hazard_counts.high +
        " high · " + payload.hazard_counts.severe + " severe / critical · relative complexity areas";
    document.getElementById("grid-status").textContent =
        payload.grid_size + " × " + payload.grid_size + " cells";
    const assessment = payload.route_assessment;
    const directScreen = assessment.direct_line;
    const selectedScreen = assessment.selected_path;
    const formatExceedance = screen => screen.sampled_cells
        ? screen.above_slope_limit_samples + " / " + screen.sampled_cells +
            " (" + screen.above_slope_limit_percent + "%)"
        : "Unavailable";
    document.getElementById("direct-exceedance").textContent =
        formatExceedance(directScreen);
    document.getElementById("path-exceedance").textContent =
        assessment.path_type === "unavailable"
            ? "No path"
            : formatExceedance(selectedScreen);
    document.getElementById("path-max-slope").textContent =
        selectedScreen.max_slope_degrees === null
            ? "Unavailable"
            : selectedScreen.max_slope_degrees + "°";
    document.getElementById("route-detour").textContent =
        hasCandidateRoute && directDistance > 0
            ? (routeLength / directDistance).toFixed(2) + "× · " +
                (routeLength - directDistance >= 0 ? "+" : "") +
                (routeLength - directDistance).toFixed(2) + " km"
            : "Unavailable";
    document.getElementById("route-evidence-note").textContent =
        "Path type: " + assessment.path_type.replace(/-/g, " ") +
        " · limit " + slopeLimit + "° · " + assessment.source_resolution_note;
    drawElevationProfile(payload);
    drawSiteCharts(payload);
    drawDustLook(payload);
    refreshMissionPlan();
    const nextAction = document.getElementById("next-action");
    nextAction.className = "decision-banner " + (payload.route_available ? "clear" : "critical");
    nextAction.textContent = payload.route_available
        ? "A path meets the selected slope limit in this coarse terrain map. Check it against sharper images before planning."
        : (payload.route_message || "No safe route meets the " + slopeLimit + "° slope constraint.") +
            (hasCandidateRoute
                ? " A curved least-risk preview is shown for review only; it is not cleared for rover travel."
                : " Change the endpoints before treating this area as traversable.");
    const nextSteps = document.getElementById("next-step-list");
    nextSteps.replaceChildren();
    const instructions = payload.route_available
        ? [
            "Inspect the climb drawing and colored terrain areas on Elevation.",
            "Check the image and field observations for GPS/context before any planning decision.",
            "Treat the " + planningSpeed + " km/h speed and traverse time as assumptions, not rover telemetry."
        ]
        : [
            "Do not dispatch: no path satisfies the " + slopeLimit + "° terrain-slope screen.",
            "Change the start or destination in Moon dust, then update the route.",
            "Use the amber line only as a least-risk visual preview; it may cross unsafe slopes."
        ];
    instructions.forEach(instruction => {
        const item = document.createElement("li");
        item.textContent = instruction;
        nextSteps.appendChild(item);
    });
    const alerts = document.getElementById("mission-alerts");
    alerts.replaceChildren();
    if (!payload.route_available) {
        addMissionAlert(payload.route_message || "No route meets the terrain slope limit.", "critical");
        if (hasCandidateRoute) {
            addMissionAlert("Curved least-risk preview shown; it may cross unsafe slopes.", "critical");
        }
    } else {
        addMissionAlert("A terrain-screened route is available: " +
            payload.route_distance_km.toFixed(2) + " km.", "clear");
    }
    if (payload.hazard_counts.severe > 0) {
        addMissionAlert(payload.hazard_counts.severe +
            " severe or provisional critical DEM area(s) in this map window.", "critical");
    } else if (payload.hazards.length > 0) {
        addMissionAlert(payload.hazards.length +
            " relative slope/roughness screening areas need review.", "");
    } else {
        addMissionAlert("No DEM screening areas exceeded the display threshold.", "clear");
    }
}

function addMissionAlert(message, severity) {
    const item = document.createElement("div");
    item.className = "alert-item " + severity;
    item.textContent = message;
    document.getElementById("mission-alerts").appendChild(item);
}

function complexityColor(complexity) {
    if (complexity >= 85) return "#ff6b73";
    if (complexity >= 70) return "#ff965e";
    if (complexity >= 55) return "#f4d35e";
    if (complexity >= 35) return "#7be6a2";
    return "#53e0d0";
}

function drawTerrain(payload) {
    if (!renderer) {
        renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:false});
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        scene = new THREE.Scene();
        scene.background = new THREE.Color("#080d14");
        camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
        camera.up.set(0, 0, 1);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.07;
        scene.add(new THREE.HemisphereLight(0xc9dcff, 0x332a1c, 0.55));
        const sun = new THREE.DirectionalLight(0xffe6bf, 2.0);
        const sunAzimuth = THREE.MathUtils.degToRad(300);
        const sunElevation = THREE.MathUtils.degToRad(22);
        sun.position.set(
            Math.sin(sunAzimuth) * Math.cos(sunElevation),
            Math.cos(sunAzimuth) * Math.cos(sunElevation),
            Math.sin(sunElevation)
        ).multiplyScalar(100);
        scene.add(sun);
        modelGroup = new THREE.Group();
        scene.add(modelGroup);
        const resize = () => {
            const rect = canvas.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            renderer.setSize(rect.width, rect.height, false);
            camera.aspect = rect.width / rect.height;
            camera.updateProjectionMatrix();
        };
        new ResizeObserver(resize).observe(canvas.parentElement);
        resize();
        const animate = () => {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        };
        animate();
    }

    modelGroup.clear();
    reliefTargets = [];
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(payload.surface.vertices, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(payload.surface.colors, 3));
    geometry.setIndex(payload.surface.indices);
    geometry.computeVertexNormals();
    surfaceMaterial = new THREE.MeshStandardMaterial({vertexColors:true, roughness:1, metalness:0, side:THREE.DoubleSide});
    modelGroup.add(new THREE.Mesh(geometry, surfaceMaterial));
    registerReliefGeometry(geometry, payload.surface.relief, true);

    const renderRoute = payload.route_available
        ? payload.route_vertices
        : (payload.advisory_route_vertices || []);
    const renderRelief = payload.route_available
        ? payload.route_relief
        : (payload.advisory_route_relief || []);
    if (renderRoute.length >= 6) {
        const routeGeometry = new THREE.BufferGeometry();
        routeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(renderRoute, 3));
        const routeMaterial = payload.route_available
            ? new THREE.LineBasicMaterial({color:"#53e0d0"})
            : new THREE.LineDashedMaterial({color:"#f4bd65", dashSize:1.2, gapSize:.7});
        const routeLine = new THREE.Line(routeGeometry, routeMaterial);
        if (!payload.route_available) routeLine.computeLineDistances();
        modelGroup.add(routeLine);
        registerReliefGeometry(routeGeometry, renderRelief);
    }

    const cellSpacing = 2 * payload.radius_km / (payload.grid_size - 1);
    const markerGeometry = new THREE.SphereGeometry(Math.max(cellSpacing * 0.38, payload.radius_km * 0.002), 18, 12);
    const routePoints = renderRoute;
    if (routePoints.length >= 3) {
        const start = new THREE.Mesh(markerGeometry, new THREE.MeshStandardMaterial({color:"#7be6a2"}));
        start.position.set(routePoints[0], routePoints[1], routePoints[2]);
        const end = new THREE.Mesh(markerGeometry, new THREE.MeshStandardMaterial({color:"#ff6b73"}));
        end.position.set(routePoints[routePoints.length - 3], routePoints[routePoints.length - 2], routePoints[routePoints.length - 1]);
        modelGroup.add(start, end);
        registerReliefObject(start, renderRelief[0]);
        registerReliefObject(end, renderRelief[renderRelief.length - 1]);
    }
    payload.hazards.slice(0, 60).forEach(hazard => {
        const marker = new THREE.Mesh(
            new THREE.SphereGeometry(Math.max(cellSpacing * 0.24, payload.radius_km * 0.0015), 12, 10),
            new THREE.MeshStandardMaterial({color:
                hazard.risk_level === "severe" || hazard.risk_level === "critical" ? "#ff6b73" :
                    hazard.risk_level === "high" ? "#ff965e" : "#f4d35e"})
        );
        marker.position.set(
            payload.surface.vertices[(hazard.row * payload.grid_size + hazard.col) * 3],
            payload.surface.vertices[(hazard.row * payload.grid_size + hazard.col) * 3 + 1],
            hazard.z
        );
        modelGroup.add(marker);
        registerReliefObject(marker, hazard.relief);
    });

    camera.position.set(0, -payload.radius_km * 1.65, payload.radius_km * 1.5);
    camera.far = Math.max(1000, payload.radius_km * 8);
    camera.updateProjectionMatrix();
    controls.maxDistance = payload.radius_km * 4;
    controls.target.set(0, 0, 0);
    controls.update();
    document.getElementById("relief-scale").oninput = event => {
        const scale = Number(event.target.value);
        updateRelief(scale);
        document.getElementById("relief-label").textContent = scale + "×";
    };
    updateRelief(Number(document.getElementById("relief-scale").value));
    document.getElementById("wireframe").onchange = event => {
        surfaceMaterial.wireframe = event.target.checked;
    };
    status.hidden = true;
    terrainSummary.textContent = payload.terrain.elevation_min_km + " to " + payload.terrain.elevation_max_km +
        " km elevation · " + payload.hazards.length + " slope hotspots";
}

let topoPayload = null;
let topoRenderer = null;
let topoCamera = null;
let topoMaterial = null;
let topoWire = null;
let topoGrid = null;
let topoLight = null;
let topoLroc = null;
let topoSlope = null;
const topoFactDots = [];
const topoFactVector = new THREE.Vector3();
function slopeCss(degrees) {
    const color = slopeColor(degrees);
    return "rgb(" + Math.round(color[0] * 255) + "," + Math.round(color[1] * 255) + "," + Math.round(color[2] * 255) + ")";
}
function localLatLon(eastKm, northKm, lat0, lon0) {
    const latRad = lat0 * Math.PI / 180;
    const lonRad = lon0 * Math.PI / 180;
    const center = [Math.cos(latRad) * Math.cos(lonRad), Math.cos(latRad) * Math.sin(lonRad), Math.sin(latRad)];
    const east = [-Math.sin(lonRad), Math.cos(lonRad), 0];
    const north = [
        -center[2] * east[1],
        center[2] * east[0],
        center[0] * east[1] - center[1] * east[0]
    ];
    const distance = Math.hypot(eastKm, northKm);
    if (distance === 0) return [lat0, lon0];
    const angle = distance / 1737.4;
    const scale = Math.sin(angle) / distance;
    const direction = [
        center[0] * Math.cos(angle) + (east[0] * eastKm + north[0] * northKm) * scale,
        center[1] * Math.cos(angle) + (east[1] * eastKm + north[1] * northKm) * scale,
        center[2] * Math.cos(angle) + (east[2] * eastKm + north[2] * northKm) * scale
    ];
    return [
        Math.asin(Math.max(-1, Math.min(1, direction[2]))) * 180 / Math.PI,
        Math.atan2(direction[1], direction[0]) * 180 / Math.PI
    ];
}
function describeSlope(slope) {
    if (slope > 35) return "A very steep face in this orbital sample.";
    if (slope > 25) return "Steep ground, well above the 18° route limit.";
    if (slope > 15) return "A hard grade. The route limit on this app is 18°.";
    if (slope > 5) return "A gentle grade, under the 18° route limit.";
    return "Nearly flat here. Rocks smaller than one LOLA pixel stay hidden.";
}
function collectTerrainFacts(payload) {
    const grid = payload.grid_size;
    const slopes = payload.surface.slopes || [];
    const verts = payload.surface.vertices || [];
    const relief = payload.surface.relief || [];
    const radius = payload.radius_km || 20;
    const center = payload.center || [0, 0];
    if (!grid || slopes.length < grid * grid || verts.length < grid * grid * 3) return [];
    const spacing = (2 * radius) / (grid - 1);
    const margin = Math.max(2, Math.floor(grid * 0.08));
    const picks = [];
    const used = new Set();
    function consider(index, label) {
        if (used.has(index) || index < 0 || index >= slopes.length) return;
        used.add(index);
        const row = Math.floor(index / grid);
        const col = index % grid;
        const eastKm = -radius + col * spacing;
        const northKm = -radius + row * spacing;
        const place = localLatLon(eastKm, northKm, center[0], center[1]);
        const lat = place[0];
        const lon = place[1];
        picks.push({
            label,
            slope: Number(slopes[index]) || 0,
            height: Number(relief[index]) || 0,
            lat,
            lon,
            x: verts[index * 3],
            y: verts[index * 3 + 1],
            z: verts[index * 3 + 2]
        });
    }
    let steep = -1;
    let flat = -1;
    let high = -1;
    let low = -1;
    let steepV = -1;
    let flatV = Infinity;
    let highV = -Infinity;
    let lowV = Infinity;
    for (let row = margin; row < grid - margin; row++) {
        for (let col = margin; col < grid - margin; col++) {
            const index = row * grid + col;
            const slope = Number(slopes[index]) || 0;
            const height = Number(relief[index]) || 0;
            if (slope > steepV) { steepV = slope; steep = index; }
            if (slope < flatV) { flatV = slope; flat = index; }
            if (height > highV) { highV = height; high = index; }
            if (height < lowV) { lowV = height; low = index; }
        }
    }
    consider(steep, "Steepest sample");
    consider(flat, "Flattest sample");
    consider(high, "Highest ground");
    consider(low, "Lowest ground");
    const step = Math.max(8, Math.floor(grid / 3));
    for (let row = step; row < grid - margin; row += step) {
        const shift = (Math.floor(row / step) % 2) * Math.floor(step / 2);
        for (let col = step + shift; col < grid - margin; col += step) consider(row * grid + col, "LOLA sample");
    }
    return picks.slice(0, 10);
}
function shortTerrainFact(dot) {
    if (dot.label === "Highest ground" || dot.label === "Lowest ground") {
        return dot.label.split(" ")[0] + " · " + (dot.height >= 0 ? "+" : "") + dot.height.toFixed(2) + " km";
    }
    if (dot.label === "LOLA sample") return dot.slope.toFixed(1) + "° slope";
    return dot.label.split(" ")[0] + " · " + dot.slope.toFixed(1) + "°";
}
function fullTerrainFact(dot) {
    const height = (dot.height >= 0 ? "+" : "") + dot.height.toFixed(2) + " km from the median height of this window";
    const place = dot.lat.toFixed(2) + "°, " + dot.lon.toFixed(2) + "°";
    return {
        title: dot.label,
        body: place + ". Slope " + dot.slope.toFixed(1) + "°. " + describeSlope(dot.slope) + " " + height + ". LOLA LDEM 16 is about 1.9 km per pixel."
    };
}
function showTopoFact(fact) {
    const card = document.getElementById("topo-fact");
    if (!card || !document.getElementById("topo-notes").checked) return;
    document.getElementById("topo-fact-title").textContent = fact.title;
    document.getElementById("topo-fact-body").textContent = fact.body;
    card.hidden = false;
}
function hideTopoFact() {
    const card = document.getElementById("topo-fact");
    if (card) card.hidden = true;
}
function syncTopoFacts() {
    const layer = document.getElementById("topo-facts");
    if (!layer || !topoCamera) return;
    const notesOn = document.getElementById("topo-notes").checked;
    layer.hidden = !notesOn;
    if (!notesOn) {
        hideTopoFact();
        return;
    }
    const canvas = document.getElementById("topo-canvas");
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    topoCamera.updateMatrixWorld();
    topoFactDots.forEach(dot => {
        topoFactVector.set(dot.x, dot.y, dot.z);
        topoFactVector.project(topoCamera);
        const inside = topoFactVector.z >= -1 && topoFactVector.z <= 1 &&
            Math.abs(topoFactVector.x) <= 1 && Math.abs(topoFactVector.y) <= 1;
        dot.node.hidden = !inside;
        if (!inside) return;
        dot.node.classList.remove("is-left");
        dot.node.style.left = ((topoFactVector.x * 0.5 + 0.5) * width) + "px";
        dot.node.style.top = ((-topoFactVector.y * 0.5 + 0.5) * height) + "px";
        if (dot.node.offsetLeft + dot.node.offsetWidth > width - 8) dot.node.classList.add("is-left");
    });
}
function placeTerrainFacts(payload) {
    const layer = document.getElementById("topo-facts");
    if (!layer) return;
    layer.replaceChildren();
    topoFactDots.length = 0;
    hideTopoFact();
    collectTerrainFacts(payload).forEach(dot => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "topo-chip";
        const mark = document.createElement("i");
        mark.style.color = slopeCss(dot.slope);
        const text = document.createElement("span");
        text.textContent = shortTerrainFact(dot);
        button.append(mark, text);
        const fact = fullTerrainFact(dot);
        button.addEventListener("pointerenter", () => showTopoFact(fact));
        button.addEventListener("focus", () => showTopoFact(fact));
        button.addEventListener("pointerleave", hideTopoFact);
        button.addEventListener("blur", hideTopoFact);
        layer.appendChild(button);
        topoFactDots.push({x: dot.x, y: dot.y, z: dot.z, node: button});
    });
    syncTopoFacts();
}
function slopeColor(degrees) {
    if (degrees > 35) return [0.95, 0.22, 0.25];
    if (degrees > 25) return [0.95, 0.48, 0.12];
    if (degrees > 15) return [0.95, 0.82, 0.2];
    if (degrees > 5) return [0.25, 0.75, 0.45];
    return [0.2, 0.84, 0.9];
}
function aimTopo() {
    if (!topoCamera || !topoPayload) return;
    const azimuth = Number(document.getElementById("topo-az").value);
    const elevation = Number(document.getElementById("topo-el").value);
    const zoom = Number(document.getElementById("topo-zoom").value);
    const radius = (topoPayload.radius_km || 20) * (3.2 / zoom);
    const az = azimuth * Math.PI / 180;
    const el = elevation * Math.PI / 180;
    topoCamera.position.set(
        radius * Math.cos(el) * Math.sin(az),
        -radius * Math.cos(el) * Math.cos(az),
        radius * Math.sin(el)
    );
    topoCamera.lookAt(0, 0, 0);
    document.getElementById("topo-az-label").textContent = Math.round(azimuth) + "°";
    document.getElementById("topo-el-label").textContent = Math.round(elevation) + "°";
    document.getElementById("topo-zoom-label").textContent = zoom.toFixed(1) + "×";
    document.getElementById("topo-needle").style.transform = "rotate(" + azimuth + "deg)";
    syncTopoFacts();
}
function applyTopoLayers() {
    if (!topoMaterial) return;
    const heat = document.getElementById("topo-heat").checked;
    const colors = heat ? topoSlope : topoLroc;
    const attribute = topoMaterial.userData.geometry.getAttribute("color");
    if (colors && attribute && colors.length === attribute.array.length) {
        attribute.array.set(colors);
        attribute.needsUpdate = true;
    }
    topoMaterial.color.set(document.getElementById("topo-shade").checked ? "#ffffff" : "#24343c");
    if (topoWire) topoWire.visible = document.getElementById("topo-wire").checked;
    if (topoLight) topoLight.intensity = document.getElementById("topo-sun").checked ? 2.2 : 0.15;
    if (topoGrid) topoGrid.visible = document.getElementById("topo-grid").checked;
    document.getElementById("topo-legend").hidden = !document.getElementById("topo-notes").checked;
    syncTopoFacts();
}
function mountTopo(payload, attempt) {
    const canvas = document.getElementById("topo-canvas");
    if (!canvas || !payload || !payload.surface || !payload.surface.vertices) return;
    if (canvas.closest("[hidden]") || !canvas.clientWidth) {
        if ((attempt || 0) < 8) requestAnimationFrame(() => mountTopo(payload, (attempt || 0) + 1));
        return;
    }
    topoPayload = payload;
    if (!topoRenderer) {
        topoRenderer = new THREE.WebGLRenderer({canvas, antialias:true});
        topoRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        topoRenderer.outputColorSpace = THREE.SRGBColorSpace;
        topoRenderer.toneMapping = THREE.ACESFilmicToneMapping;
        topoRenderer.toneMappingExposure = 1.18;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color("#05080d");
        scene.fog = new THREE.FogExp2(0x05080d, 0.0045);
        topoCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 5000);
        topoCamera.up.set(0, 0, 1);
        scene.add(new THREE.HemisphereLight(0xd5e6ff, 0x1a140c, 0.62));
        scene.add(new THREE.AmbientLight(0x9aabbc, 0.28));
        topoLight = new THREE.DirectionalLight(0xffe6bf, 2.65);
        topoLight.position.set(-40, -20, 80);
        scene.add(topoLight);
        const topoFill = new THREE.DirectionalLight(0x9fd0ff, 0.7);
        topoFill.position.set(30, 40, 35);
        scene.add(topoFill);
        topoGrid = new THREE.GridHelper(1, 16, 0x2a90aa, 0x12384a);
        topoGrid.rotation.x = Math.PI / 2;
        scene.add(topoGrid);
        const geometry = new THREE.BufferGeometry();
        topoMaterial = new THREE.MeshStandardMaterial({vertexColors:true, roughness:0.88, metalness:0.04, side:THREE.DoubleSide});
        topoMaterial.userData.geometry = geometry;
        scene.add(new THREE.Mesh(geometry, topoMaterial));
        topoWire = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({color:0x9af6ff, wireframe:true, transparent:true, opacity:0.28}));
        scene.add(topoWire);
        const resize = () => {
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            if (!width || !height) return;
            topoRenderer.setSize(width, height, false);
            topoCamera.aspect = width / height;
            topoCamera.updateProjectionMatrix();
        };
        new ResizeObserver(resize).observe(canvas.parentElement);
        resize();
        const animate = () => {
            requestAnimationFrame(animate);
            syncTopoFacts();
            topoRenderer.render(scene, topoCamera);
        };
        animate();
        ["topo-az", "topo-el", "topo-zoom"].forEach(id => {
            document.getElementById(id).addEventListener("input", aimTopo);
        });
        ["topo-wire", "topo-shade", "topo-heat", "topo-sun", "topo-grid", "topo-notes"].forEach(id => {
            document.getElementById(id).addEventListener("change", applyTopoLayers);
        });
    }
    topoGrid.scale.setScalar((payload.radius_km || 20) * 2.4);
    const geometry = topoMaterial.userData.geometry;
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(payload.surface.vertices, 3));
    geometry.setIndex(payload.surface.indices);
    const count = payload.surface.vertices.length / 3;
    topoLroc = Float32Array.from(payload.surface.colors);
    topoSlope = new Float32Array(count * 3);
    const slopes = payload.surface.slopes || [];
    let sum = 0;
    for (let index = 0; index < count; index++) {
        const value = Number(slopes[index]) || 0;
        const color = slopeColor(value);
        topoSlope[index * 3] = color[0];
        topoSlope[index * 3 + 1] = color[1];
        topoSlope[index * 3 + 2] = color[2];
        sum += value;
    }
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(topoSlope.slice(), 3));
    geometry.computeVertexNormals();
    const terrain = payload.terrain || {};
    const maxSlope = terrain.max_slope_degrees != null ? terrain.max_slope_degrees : 0;
    document.getElementById("topo-max").textContent = maxSlope + "°";
    document.getElementById("topo-avg").textContent = slopes.length ? (sum / slopes.length).toFixed(1) + "°" : "—";
    document.getElementById("topo-area").textContent = payload.radius_km ? (4 * payload.radius_km * payload.radius_km).toFixed(1) + " km²" : "—";
    const relief = terrain.elevation_max_km != null && terrain.elevation_min_km != null
        ? (terrain.elevation_max_km - terrain.elevation_min_km) : null;
    document.getElementById("topo-relief").textContent = relief != null ? relief.toFixed(2) + " km" : "—";
    const center = payload.center || [];
    document.getElementById("topo-place").textContent = center.length
        ? center[0].toFixed(2) + "°, " + center[1].toFixed(2) + "° · " + (payload.radius_km || "") + " km sample"
        : "LOLA sample";
    document.getElementById("topo-system").textContent = "SYSTEM OK";
    topoCamera.far = Math.max(1000, (payload.radius_km || 20) * 12);
    topoCamera.updateProjectionMatrix();
    applyTopoLayers();
    placeTerrainFacts(payload);
    aimTopo();
}
loadTerrain();

async function loadShackletonScreen() {
    const call = document.getElementById("shackleton-call");
    try {
        const response = await fetch("/api/shackleton-screen");
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "The Shackleton screen failed.");
        shackletonScreen = payload;
        if (call) {
            call.textContent = payload.go_count + " of " + payload.cell_count +
                " cells are a go for the crew. " + payload.problem;
        }
        ["walk_safe", "pad_safe", "earth_clear", "sun_clear", "go_zone"].forEach(name => {
            const node = document.getElementById("count-" + name);
            if (!node) return;
            const count = payload.cells.filter(cell => cell.scores[name] >= 0.5).length;
            node.textContent = count + " / " + payload.cell_count;
        });
        (payload.models || []).forEach(model => {
            const acc = document.getElementById("acc-" + model.id);
            if (acc && model.held_out_accuracy != null) {
                acc.textContent = Math.round(model.held_out_accuracy * 100) + "% held-out";
            }
        });
        const rows = document.getElementById("trained-rows");
        if (rows) {
            rows.replaceChildren();
            payload.models.forEach(model => {
                const row = document.createElement("tr");
                [model.file, model.question, model.rule, Math.round(model.held_out_accuracy * 100) + "%"].forEach(text => {
                    const cell = document.createElement("td");
                    cell.textContent = text;
                    row.appendChild(cell);
                });
                rows.appendChild(row);
            });
        }
        const note = document.getElementById("trained-note");
        if (note) note.textContent = payload.source + " " + payload.note;
        drawShackletonGrid(payload);
    } catch (error) {
        if (call) call.textContent = error.message;
    }
    if (!document.getElementById("path-board").hidden) paintOpsBoard();
}
function drawShackletonGrid(payload) {
    const canvas = document.getElementById("shackleton-grid");
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted) return;
    const {context, width, height} = fitted;
    const size = payload.grid_size;
    const cells = payload.cells || [];
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#d5e6ef";
    context.font = "13px Segoe UI, Arial";
    context.fillText("Shackleton rim · north is up · green is a go", 12, 16);
    const cell = Math.min((width - 24) / size, (height - 28) / size);
    const originX = (width - cell * size) / 2;
    cells.forEach(item => {
        const go = item.scores.go_zone >= 0.5;
        const walk = item.scores.walk_safe >= 0.5;
        context.fillStyle = go ? "#1f8f72" : walk ? "#c4923a" : "#8d3d48";
        const x = originX + (item.col - 1) * cell;
        const y = 24 + (size - item.row) * cell;
        context.fillRect(x, y, Math.max(1, cell - 1), Math.max(1, cell - 1));
    });
}
function quizChoice(id) {
    const button = document.querySelector("#" + id + " [aria-pressed='true']");
    return button ? button.dataset.value : "";
}
document.querySelectorAll(".quiz-row").forEach(row => {
    row.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", () => {
            row.querySelectorAll("button").forEach(other => other.setAttribute("aria-pressed", "false"));
            button.setAttribute("aria-pressed", "true");
        });
    });
});
function paintScoreBars(canvasId, rows, color) {
    const canvas = document.getElementById(canvasId);
    const fitted = canvas && fittedCanvas(canvas);
    if (!fitted || !rows.length) return;
    const {context, width, height} = fitted;
    context.clearRect(0, 0, width, height);
    rows.forEach((row, index) => {
        const band = (height - 20) / rows.length;
        const y = 10 + index * band;
        const barH = Math.max(8, band - 8);
        context.fillStyle = "#1c3040";
        context.fillRect(110, y, width - 128, barH);
        context.fillStyle = color;
        context.fillRect(110, y, (width - 128) * Math.max(0, Math.min(100, row.value)) / 100, barH);
        context.fillStyle = "#d5e6ef";
        context.font = "12px Segoe UI, Arial";
        context.fillText(row.label, 8, y + barH * 0.75);
    });
}
document.getElementById("run-quiz").addEventListener("click", async () => {
    const status = document.getElementById("quiz-status");
    status.textContent = "Reading the elevation mapâ€¦";
    try {
        const response = await fetch("/api/landing-quiz", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                region: quizChoice("quiz-region"),
                rocket: quizChoice("quiz-rocket"),
                priority: quizChoice("quiz-priority")
            })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "The landing check failed.");
        const winner = payload.winner;
        document.getElementById("landing-result").hidden = false;
        document.getElementById("landing-name").textContent = winner.name;
        document.getElementById("landing-coords").textContent =
            winner.lat.toFixed(3) + "°,  " + winner.lon.toFixed(3) + "°";
        const pros = document.getElementById("landing-pros");
        const cons = document.getElementById("landing-cons");
        pros.replaceChildren();
        cons.replaceChildren();
        winner.advantages.forEach(text => {
            const item = document.createElement("li");
            item.textContent = text;
            pros.appendChild(item);
        });
        winner.cons.forEach(text => {
            const item = document.createElement("li");
            item.textContent = text;
            cons.appendChild(item);
        });
        paintScoreBars("landing-bars", winner.bars, "#7ef0e4");
        paintScoreBars("landing-rank", payload.ranked.map(site => ({
            label: site.name, value: site.score
        })), "#e2a15a");
        document.getElementById("start_lat").value = winner.lat;
        document.getElementById("start_lon").value = winner.lon;
        document.getElementById("start_name").value = winner.name;
        const destLat = Math.max(-89.9, Math.min(89.9, winner.lat + (winner.lat < 0 ? 0.35 : -0.35)));
        document.getElementById("dest_lat").value = destLat.toFixed(5);
        document.getElementById("dest_lon").value = winner.lon;
        document.getElementById("dest_name").value = winner.name + " walk";
        status.textContent = payload.note || "";
        loadTerrain();
        const photos = document.getElementById("landing-photos");
        photos.replaceChildren();
        fetch("/api/nasa-images").then(imageResponse => imageResponse.json()).then(data => {
            (data.items || []).slice(0, 6).forEach(item => {
                const image = document.createElement("img");
                image.src = item.image_url;
                image.alt = item.title;
                photos.appendChild(image);
            });
        }).catch(() => {});
    } catch (error) {
        status.textContent = error.message;
    }
});
loadShackletonScreen();

let clpsReport = null;
let clpsDays = 14;
let clpsFocusId = null;
let clpsToken = 0;
let clpsPaintTries = 0;

function clpsFocus() {
    if (!clpsReport) return null;
    return clpsReport.sites.find(site => site.id === clpsFocusId) || clpsReport.sites[0];
}
function ensureClps(force) {
    const input = document.getElementById("clps-date");
    if (input && !input.value) input.value = new Date().toISOString().slice(0, 10);
    const date = input ? input.value : new Date().toISOString().slice(0, 10);
    const key = date + "|" + clpsDays;
    if (!force && clpsReport && clpsReport._key === key) {
        paintClps();
        return;
    }
    const token = ++clpsToken;
    const status = document.getElementById("clps-status");
    if (status) status.textContent = "Reading LOLA ridges and the Sun and Earth for this date…";
    const url = "/api/clps-compare?date=" + encodeURIComponent(date) + "&days=" + encodeURIComponent(clpsDays) + "&scan=1";
    fetch(url).then(response => response.json().then(body => ({ ok: response.ok, body }))).then(result => {
        if (token !== clpsToken) return;
        if (!result.ok) throw new Error(result.body.error || "The site compare failed.");
        result.body._key = key;
        clpsReport = result.body;
        if (!clpsFocusId || !clpsReport.sites.some(site => site.id === clpsFocusId)) {
            clpsFocusId = clpsReport.sites[0].id;
        }
        paintClps();
    }).catch(error => {
        if (token !== clpsToken) return;
        if (status) status.textContent = error.message;
    });
}
function paintClps() {
    const report = clpsReport;
    const focus = clpsFocus();
    if (!report || !focus) return;
    const headline = document.getElementById("clps-headline");
    if (headline) headline.textContent = report.headline;
    const list = document.getElementById("clps-list");
    if (list) {
        list.replaceChildren();
        report.sites.forEach(site => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "clps-site" + (site.rank === 1 ? " rank-1" : "");
            button.setAttribute("aria-pressed", String(site.id === focus.id));
            const name = document.createElement("strong");
            name.textContent = "#" + site.rank + "  " + site.name;
            const meta = document.createElement("span");
            meta.className = "clps-meta";
            const shift = site.shift_km >= 3 ? " · open ground " + site.shift_km + " km from the pin" : "";
            meta.textContent = site.note + shift;
            const hours = document.createElement("span");
            hours.className = "clps-hours";
            hours.textContent = site.sun_clear_hours + " h Sun · " + site.comm_hours + " h Earth · score " + site.score;
            const call = document.createElement("span");
            call.className = "clps-call";
            call.textContent = site.call;
            button.append(name, meta, hours, call);
            button.addEventListener("click", () => {
                clpsFocusId = site.id;
                paintClps();
            });
            list.appendChild(button);
            if (site.best && site.best.score > site.score + 3) {
                const best = document.createElement("button");
                best.type = "button";
                best.className = "clps-best";
                best.textContent = "Better fortnight starts " + site.best.label + " · score " + site.best.score;
                best.addEventListener("click", () => {
                    const dateInput = document.getElementById("clps-date");
                    if (dateInput) dateInput.value = site.best.start;
                    clpsDays = 14;
                    document.querySelectorAll("[data-clps-days]").forEach(other => {
                        other.setAttribute("aria-pressed", String(other.dataset.clpsDays === "14"));
                    });
                    clpsFocusId = site.id;
                    ensureClps(true);
                });
                list.appendChild(best);
            }
        });
    }
    const legend = document.getElementById("clps-legend");
    if (legend) {
        legend.textContent = focus.name + " · gold Sun, cyan Earth, dashes are the ridge in that direction. Sun peaks at " +
            focus.peak_sun_deg + "°. An 8 m² sun-facing array makes " + focus.tracking_kwh +
            " kWh. Laid flat, the same panel makes " + focus.flat_kwh + " kWh, because the Sun stays low.";
    }
    const caption = document.getElementById("clps-rose-caption");
    if (caption) {
        caption.textContent = "Earth center is up " + focus.comm_hours + " h. Counting the " +
            "disk, it still grazes the ridge for " + focus.disk_hours + " h. A 2° radio margin holds for " +
            focus.solid_hours + " h.";
    }
    const status = document.getElementById("clps-status");
    if (status) status.textContent = report.limits;
    clpsPaintTries = 0;
    paintClpsCharts();
}
function paintClpsCharts() {
    const focus = clpsFocus();
    const chart = document.getElementById("clps-chart");
    const rose = document.getElementById("clps-rose");
    if (!focus || !chart || !rose) return;
    const rect = chart.getBoundingClientRect();
    if ((rect.width < 20 || rect.height < 20) && clpsPaintTries < 8) {
        clpsPaintTries += 1;
        requestAnimationFrame(paintClpsCharts);
        return;
    }
    drawClpsChart(chart, focus);
    drawClpsRose(rose, focus);
}
function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(20, rect.width);
    const height = Math.max(20, rect.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width, height };
}
function drawClpsChart(canvas, site) {
    const { ctx, width, height } = fitCanvas(canvas);
    const series = site.series || [];
    ctx.clearRect(0, 0, width, height);
    if (series.length < 2) return;
    const pad = { l: 42, r: 12, t: 14, b: 26 };
    const values = [];
    series.forEach(point => values.push(point.sun_elev, point.earth_elev, point.sun_horizon, point.earth_horizon));
    let minE = Math.min(-3, ...values);
    let maxE = Math.max(4, ...values);
    const span = Math.max(1, maxE - minE);
    const xOf = index => pad.l + (index / (series.length - 1)) * (width - pad.l - pad.r);
    const yOf = elev => pad.t + (maxE - elev) / span * (height - pad.t - pad.b);
    ctx.strokeStyle = "rgba(154,215,228,0.18)";
    ctx.lineWidth = 1;
    for (let elev = Math.ceil(minE); elev <= maxE; elev += 2) {
        ctx.beginPath();
        ctx.moveTo(pad.l, yOf(elev));
        ctx.lineTo(width - pad.r, yOf(elev));
        ctx.stroke();
        ctx.fillStyle = "#8fb4c2";
        ctx.font = "11px Segoe UI, Arial, sans-serif";
        ctx.fillText(elev + "°", 4, yOf(elev) + 4);
    }
    const band = (flag, color) => {
        ctx.fillStyle = color;
        series.forEach((point, index) => {
            if (!point[flag]) return;
            const x0 = index === 0 ? xOf(0) : (xOf(index - 1) + xOf(index)) / 2;
            const x1 = index === series.length - 1 ? xOf(index) : (xOf(index) + xOf(index + 1)) / 2;
            const top = yOf(point.sun_elev);
            const bottom = yOf(flag === "sun_clear" ? point.sun_horizon : point.earth_horizon);
            const sky = flag === "earth_clear" ? yOf(point.earth_elev) : top;
            const floor = flag === "earth_clear" ? yOf(point.earth_horizon) : bottom;
            ctx.fillRect(x0, Math.min(sky, floor), Math.max(1, x1 - x0), Math.abs(floor - sky));
        });
    };
    band("earth_clear", "rgba(122,244,255,0.14)");
    band("sun_clear", "rgba(240,193,74,0.22)");
    const stroke = (key, color, widthPx, dash) => {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = widthPx;
        ctx.setLineDash(dash || []);
        series.forEach((point, index) => {
            const x = xOf(index);
            const y = yOf(point[key]);
            if (index) ctx.lineTo(x, y);
            else ctx.moveTo(x, y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
    };
    stroke("sun_horizon", "rgba(240,193,74,0.7)", 1.4, [4, 3]);
    stroke("earth_horizon", "rgba(122,244,255,0.55)", 1.4, [4, 3]);
    stroke("earth_elev", "#7af4ff", 2.2);
    stroke("sun_elev", "#f0c14a", 2.4);
    ctx.fillStyle = "#9ad7e4";
    ctx.font = "11px Segoe UI, Arial, sans-serif";
    ctx.fillText(series[0].label, pad.l, height - 8);
    const end = series[series.length - 1].label;
    ctx.fillText(end, width - pad.r - ctx.measureText(end).width, height - 8);
}
function drawClpsRose(canvas, site) {
    const { ctx, width, height } = fitCanvas(canvas);
    ctx.clearRect(0, 0, width, height);
    const cx = width / 2;
    const cy = height / 2 - 4;
    const px = Math.min(width, height) * 0.016;
    const r0 = Math.min(width, height) * 0.26;
    const pointAt = (azimuth, elev) => {
        const angle = (azimuth - 90) * Math.PI / 180;
        const radius = Math.max(6, r0 + elev * px);
        return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
    };
    ctx.strokeStyle = "rgba(244,251,255,0.28)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    (site.horizon || []).forEach((bin, index) => {
        const [x, y] = pointAt(bin.az, bin.elev);
        if (index) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = "#9ad7e4";
    ctx.lineWidth = 1.6;
    ctx.stroke();
    (site.series || []).forEach(point => {
        const [sx, sy] = pointAt(point.sun_az, point.sun_elev);
        ctx.fillStyle = point.sun_clear ? "#f0c14a" : "rgba(240,193,74,0.28)";
        ctx.beginPath();
        ctx.arc(sx, sy, point.sun_clear ? 2.4 : 1.6, 0, Math.PI * 2);
        ctx.fill();
        const [ex, ey] = pointAt(point.earth_az, point.earth_elev);
        ctx.fillStyle = point.earth_clear ? "#7af4ff" : "rgba(122,244,255,0.28)";
        ctx.beginPath();
        ctx.arc(ex, ey, 2.2, 0, Math.PI * 2);
        ctx.fill();
    });
    ctx.fillStyle = "#d5e8ef";
    ctx.font = "12px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", cx, 16);
    ctx.fillText("S", cx, height - 8);
    ctx.textAlign = "left";
    ctx.fillText("E", width - 16, cy);
    ctx.fillText("W", 6, cy);
}
function walkClpsSite() {
    const site = clpsFocus();
    if (!site) return;
    const card = Array.from(document.querySelectorAll("#choice-boards .choice-card")).find(button => button.textContent === site.name);
    if (card) card.click();
    else {
        const dest = document.getElementById("plan-destination");
        if (dest) dest.value = site.select_value;
        const run = document.getElementById("run-plan");
        if (run) run.click();
    }
    showScreen("path");
}
function bindClps() {
    const dateInput = document.getElementById("clps-date");
    if (dateInput) {
        dateInput.value = new Date().toISOString().slice(0, 10);
        dateInput.addEventListener("change", () => ensureClps(true));
    }
    document.querySelectorAll("[data-clps-days]").forEach(button => {
        button.addEventListener("click", () => {
            clpsDays = Number(button.dataset.clpsDays);
            document.querySelectorAll("[data-clps-days]").forEach(other => {
                other.setAttribute("aria-pressed", String(other === button));
            });
            ensureClps(true);
        });
    });
    const walk = document.getElementById("clps-walk");
    if (walk) walk.addEventListener("click", walkClpsSite);
    const open = document.getElementById("open-clps");
    if (open) open.addEventListener("click", () => showScreen("clps"));
    window.addEventListener("resize", () => {
        if (clpsFocus()) paintClpsCharts();
    });
}
bindClps();
</script>
</body>
</html>
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them.
"""


def _validate_coordinate(name):
    try:
        value = float(request.args[name])
    except (KeyError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if name.endswith("_lat") and not -90 <= value <= 90:
        raise ValueError(f"{name} must be between -90 and 90 degrees.")
    if name.endswith("_lon") and not -180 <= value <= 180:
        raise ValueError(f"{name} must be between -180 and 180 degrees.")
    return value


def _bounded_number(value, name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")
    return number


def _validate_planning_number(name, minimum, maximum):
    return _bounded_number(
        request.args.get(name, str(DEFAULTS[name])),
        name.replace("_", " "),
        minimum,
        maximum,
    )


def _great_circle_distance(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * 1737.4 * math.asin(min(1.0, math.sqrt(value)))


def _extract_exif_location(image):
    """Return embedded GPS coordinates when an uploaded image contains them."""
    exif = image.getexif()
    if not exif:
        return None
    gps_ifd = exif.get_ifd(34853)
    gps = {ExifTags.GPSTAGS.get(key, key): value for key, value in gps_ifd.items()}
    try:
        def decimal_degrees(values, reference):
            degrees, minutes, seconds = (float(value) for value in values)
            coordinate = degrees + minutes / 60 + seconds / 3600
            if reference in (b"S", b"W", "S", "W"):
                coordinate = -coordinate
            return coordinate

        latitude = decimal_degrees(gps["GPSLatitude"], gps["GPSLatitudeRef"])
        longitude = decimal_degrees(gps["GPSLongitude"], gps["GPSLongitudeRef"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


@lru_cache(maxsize=1)
def _fetch_nasa_reference_images():
    query = urlencode({
        "q": "Moon lunar surface crater",
        "media_type": "image",
        "page_size": 30,
    })
    req = Request(
        f"https://images-api.nasa.gov/search?{query}",
        headers={"User-Agent": "ZeroPointLunar/1.0"},
    )
    with urlopen(req, timeout=8) as response:
        payload = json.load(response)

    if not isinstance(payload, dict) or not isinstance(payload.get("collection"), dict):
        raise ValueError("NASA image catalog returned an unexpected response.")
    results = []
    items = payload["collection"].get("items")
    if not isinstance(items, list):
        raise ValueError("NASA image catalog returned no image collection.")
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata_items = item.get("data", [])
        if not isinstance(metadata_items, list) or not metadata_items:
            continue
        metadata = metadata_items[0]
        if not isinstance(metadata, dict):
            continue
        keywords = metadata.get("keywords")
        if not isinstance(keywords, list):
            keywords = []
        text = " ".join([
            str(metadata.get("title", "")),
            str(metadata.get("description", "")),
            " ".join(str(keyword) for keyword in keywords),
        ]).casefold()
        if any(term in text for term in (
            "earth",
            "apollo",
            "booster",
            "launch",
            "cape canaveral",
            "spacecraft",
            "prelaunch",
        )):
            continue
        if str(metadata.get("center", "")).casefold() == "ksc":
            continue
        if not any(term in text for term in (
            "lunar surface",
            "surface of the moon",
            "moon’s surface",
            "moon's surface",
            "crater",
            "craters",
        )):
            continue
        media_links = item.get("links", [])
        if not isinstance(media_links, list):
            continue
        image_link = next((
            link.get("href", "")
            for link in media_links
            if link.get("rel") == "preview"
        ), "")
        image_host = urlparse(image_link)
        if image_host.scheme != "https" or image_host.hostname != "images-assets.nasa.gov":
            continue

        nasa_id = str(metadata.get("nasa_id", ""))
        title = str(metadata.get("title", "")).strip()
        if not nasa_id or not title:
            continue
        description = " ".join(str(metadata.get("description", "")).split())[:360]
        results.append({
            "title": title,
            "description": description,
            "image_url": image_link,
            "details_url": f"https://images.nasa.gov/details/{quote(nasa_id, safe='')}",
            "date_created": str(metadata.get("date_created", ""))[:10],
            "nasa_id": nasa_id,
            "match_label": "Lunar reference · exact target match unverified",
        })
        if len(results) == 9:
            break
    return results


def _midpoint(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    lambda1, lambda2 = math.radians(lon1), math.radians(lon2)
    delta = lambda2 - lambda1
    bx = math.cos(phi2) * math.cos(delta)
    by = math.cos(phi2) * math.sin(delta)
    latitude = math.atan2(
        math.sin(phi1) + math.sin(phi2),
        math.sqrt((math.cos(phi1) + bx) ** 2 + by ** 2),
    )
    longitude = lambda1 + math.atan2(by, math.cos(phi1) + bx)
    longitude = (math.degrees(longitude) + 180) % 360 - 180
    return math.degrees(latitude), longitude


def _xray_class(flux):
    for level, threshold in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux >= threshold:
            return f"{level}{flux / threshold:.1f}"
    return "< A1"


def _fetch_goes_xray_data():
    request_object = Request(
        GOES_XRAY_URL,
        headers={"User-Agent": "ZeroPointLunar/1.0 (public solar observation display)"},
    )
    with urlopen(request_object, timeout=12) as response:
        raw_data = response.read()
    records = json.loads(raw_data.decode("utf-8"))
    if not isinstance(records, list):
        raise ValueError("NOAA returned an unexpected X-ray data format.")

    samples = []
    for record in records:
        if not isinstance(record, dict) or record.get("energy") != "0.1-0.8nm":
            continue
        if record.get("electron_contaminaton") is True:
            continue
        flux = record.get("flux")
        time_tag = record.get("time_tag")
        if (
            not isinstance(flux, (int, float))
            or isinstance(flux, bool)
            or not math.isfinite(flux)
            or flux <= 0
            or not isinstance(time_tag, str)
        ):
            continue
        samples.append({
            "time_utc": time_tag,
            "flux": float(flux),
            "satellite": record.get("satellite"),
        })
    if not samples:
        raise ValueError("NOAA returned no usable GOES X-ray readings.")
    samples.sort(key=lambda sample: sample["time_utc"])
    latest = samples[-1]
    peak = max(samples, key=lambda sample: sample["flux"])
    return {
        "latest": {
            **latest,
            "class": _xray_class(latest["flux"]),
        },
        "peak_24h": {
            **peak,
            "class": _xray_class(peak["flux"]),
        },
        "samples": samples[-180:],
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _image_dataset_summary():
    training_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset", "train")
    suffixes = {".bmp", ".gif", ".jpeg", ".jpg", ".png"}
    class_counts = []
    if os.path.isdir(training_dir):
        for class_name in sorted(os.listdir(training_dir)):
            class_dir = os.path.join(training_dir, class_name)
            if not os.path.isdir(class_dir):
                continue
            count = sum(
                1 for name in os.listdir(class_dir)
                if os.path.isfile(os.path.join(class_dir, name))
                and os.path.splitext(name)[1].lower() in suffixes
            )
            if count:
                class_counts.append((class_name, count))
    total = sum(count for _, count in class_counts)
    if not total:
        return "no labeled training images found"
    labels = ", ".join(f"{name}: {count}" for name, count in class_counts)
    return f"{total} images ({labels})"


REFERENCE_LINKS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "dataset",
    "articles",
    "reference_links.json",
)
_DUST_LINK_TERMS = ("dust", "regolith", "plume", "ochmo")
_SITE_LINK_TERMS = (
    "site",
    "south pole",
    "shackleton",
    "shadow",
    "water",
    "ice",
    "power",
)


def _normalize_reference_link(entry):
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    url = str(entry.get("url") or "").strip()
    if not title or not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return {"title": title, "url": url}


@lru_cache(maxsize=1)
def _load_reference_links():
    try:
        with open(REFERENCE_LINKS_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, list):
        return []
    links = []
    seen = set()
    for entry in payload:
        link = _normalize_reference_link(entry)
        if link is None or link["url"] in seen:
            continue
        seen.add(link["url"])
        links.append(link)
    return links


def _filter_reference_links(terms):
    needles = tuple(term.casefold() for term in terms)
    matched = []
    for link in _load_reference_links():
        haystack = f"{link['title']} {link['url']}".casefold()
        if any(term in haystack for term in needles):
            matched.append(link)
    return matched


@app.route("/api/clps-compare")
def clps_compare_api():
    raw_date = (request.args.get("date") or "").strip()
    try:
        if raw_date:
            start = datetime.fromisoformat(raw_date)
        else:
            start = datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        days = float(request.args.get("days") or 14)
        if not math.isfinite(days):
            raise ValueError("Stay length has to be a number of days.")
        report = compare_sites(start, days=days, scan=request.args.get("scan", "1") != "0")
        return jsonify(report)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except OSError:
        app.logger.error("CLPS compare could not read LOLA elevation")
        return jsonify({"error": "LOLA elevation could not be loaded."}), 503


@app.route("/api/terrain")
def terrain_api():
    try:
        start_lat = _validate_coordinate("start_lat")
        start_lon = _validate_coordinate("start_lon")
        dest_lat = _validate_coordinate("dest_lat")
        dest_lon = _validate_coordinate("dest_lon")
        max_slope_degrees = _validate_planning_number(
            "max_slope_degrees", 5.0, 30.0
        )
        planning_speed_kmh = _validate_planning_number(
            "planning_speed_kmh", 0.1, 5.0
        )
        distance = _great_circle_distance(start_lat, start_lon, dest_lat, dest_lon)
        radius_km = max(40.0, distance / 2.0 + 8.0)
        center_lat, center_lon = _midpoint(start_lat, start_lon, dest_lat, dest_lon)
        grid_size = min(320, max(200, int(math.ceil(2 * radius_km / 1.5)) + 1))
        destination_is_shackleton = (
            "shackleton" in request.args.get("dest_name", "").casefold()
            or _great_circle_distance(dest_lat, dest_lon, -89.9, 0.0) <= 12.0
        )
        path_priority = (request.args.get("path_priority") or "slope").strip().lower()
        if path_priority not in {"slope", "sun", "sunlight", "power", "ice", "cold", "water", "radio", "earth", "comms"}:
            path_priority = "slope"
        payload = generate_terrain_payload(
            center_lat,
            center_lon,
            start_lat,
            start_lon,
            dest_lat,
            dest_lon,
            radius_km,
            grid_size=grid_size,
            destination_is_shackleton=destination_is_shackleton,
            max_slope_degrees=max_slope_degrees,
            path_priority=path_priority,
        )
        payload["straight_line_distance_km"] = round(distance, 2)
        payload["max_slope_degrees"] = max_slope_degrees
        payload["planning_speed_kmh"] = planning_speed_kmh
        payload["path_priority"] = path_priority
        return jsonify(payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except OSError as error:
        app.logger.error("Unable to load lunar terrain data: %s", error)
        return jsonify({"error": "Lunar terrain data could not be loaded. Check the cached files or network connection."}), 503


@app.route("/api/mission-plan", methods=["POST"])
def mission_plan_api():
    payload = request.get_json(silent=True)
    try:
        return jsonify(build_mission_plan(payload if isinstance(payload, dict) else {}))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/api/flare-outlook", methods=["POST"])
def flare_outlook_api():
    payload = request.get_json(silent=True)
    try:
        return jsonify(assess_flare_region(payload if isinstance(payload, dict) else {}))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/api/lunar-environment")
def lunar_environment_api():
    try:
        latitude = float(request.args["lat"])
        longitude = float(request.args["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon must be numbers."}), 400
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        return jsonify({"error": "lat must be between -90 and 90 degrees."}), 400
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        return jsonify({"error": "lon must be between -180 and 180 degrees."}), 400
    return jsonify(environment_for_site(latitude, longitude))


@app.route("/api/solar-xray")
def solar_xray_api():
    try:
        return jsonify(_fetch_goes_xray_data())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as error:
        app.logger.warning("Unable to load NOAA GOES X-ray data: %s", error)
        return jsonify({"error": "NOAA GOES X-ray readings are unavailable. Try again later."}), 502


@app.route("/api/dust-plume-screen", methods=["POST"])
def dust_plume_screen_api():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON plume-screen request is required."}), 400
    try:
        assessment = screen_route_against_plume_corridor(
            route_lat_lon=payload.get("route_lat_lon"),
            source_latitude=payload.get("source_latitude"),
            source_longitude=payload.get("source_longitude"),
            axis_azimuth_degrees=payload.get("axis_azimuth_degrees"),
            downrange_extent_km=payload.get("downrange_extent_km"),
            cross_track_half_width_km=payload.get("cross_track_half_width_km"),
            evidence_source=payload.get("evidence_source", ""),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(assessment)


@app.route("/api/nasa-images")
def nasa_images_api():
    try:
        return jsonify({
            "items": _fetch_nasa_reference_images(),
            "match_policy": "NASA catalog records are not coordinate-verified for the selected target.",
        })
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as error:
        return jsonify({"error": f"NASA image catalog is unavailable: {error}"}), 502


_SEARCH_CACHE = {}


def _search_web(query):
    if query in _SEARCH_CACHE:
        return _SEARCH_CACHE[query]
    from ddgs import DDGS

    try:
        rows = DDGS(timeout=8).text(query, max_results=8) or []
    except Exception:
        return ()
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("href") or row.get("url") or "")
        title = re.split(r"(?<=[a-z.)])(?=[A-Z])", str(row.get("title") or "").strip(), maxsplit=1)[0].strip(" |-")
        snippet = " ".join(str(row.get("body") or "").split())
        host = urlparse(url).hostname or ""
        blob = f"{title} {snippet}".casefold()
        if not url.startswith("http") or not title or "bing.com" in host or "aclick" in url:
            continue
        if not any(word in blob for word in ("moon", "lunar", "crater", "nasa", "artemis")):
            continue
        items.append({
            "title": title[:140],
            "url": url,
            "snippet": snippet[:160],
        })
    packed = tuple(tuple(item.items()) for item in items[:4])
    if packed:
        _SEARCH_CACHE[query] = packed
    return packed


@app.route("/api/live-search")
def live_search_api():
    query = " ".join(str(request.args.get("q", "Artemis lunar landing")).split())[:100]
    if len(query) < 3:
        return jsonify({"error": "Ask for a place."}), 400
    items = [dict(pairs) for pairs in _search_web(query)]
    if not items:
        fallback = " ".join(query.split()[:2] + ["Moon"])
        items = [dict(pairs) for pairs in _search_web(fallback)]
    return jsonify({
        "query": query,
        "items": items,
        "source": "DuckDuckGo search. These are web pages, not measurements.",
    })


@app.route("/api/landing-quiz", methods=["POST"])
def landing_quiz_api():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(choose_landing(
            str(body.get("region", "")),
            str(body.get("rocket", "")),
            str(body.get("priority", "")),
        ))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except (OSError, RuntimeError, ImportError) as error:
        return jsonify({"error": f"The landing check could not sample the map: {error}"}), 503


@app.route("/api/shackleton-screen")
def shackleton_screen_api():
    try:
        return jsonify(screen_shackleton())
    except (OSError, ValueError, ImportError, RuntimeError) as error:
        return jsonify({"error": f"The Shackleton models could not run: {error}"}), 503


@app.route("/api/path-basemap.jpg")
def path_basemap():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon must be numbers."}), 400
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "lat or lon is out of range."}), 400
    try:
        radius = float(request.args.get("radius", "24"))
    except (TypeError, ValueError):
        radius = 24.0
    try:
        blob, _meta = moon_trek_patch(lat, lon, radius, 900)
    except (OSError, ValueError) as error:
        return jsonify({"error": f"Moon Trek photo could not be built: {error}"}), 503
    return Response(blob, mimetype="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.route("/api/moon-disk.jpg")
def moon_disk():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lon must be numbers."}), 400
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "lat or lon is out of range."}), 400
    try:
        blob = moon_disk_jpeg(lat, lon, 640)
    except (OSError, ValueError) as error:
        return jsonify({"error": f"Moon photo could not be built: {error}"}), 503
    return Response(blob, mimetype="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.route("/api/terrain-views")
def terrain_views_api():
    filenames = [f"{TERRAIN_VIEW_PREFIX}_{name}.png" for name in TERRAIN_VIEW_NAMES]
    paths = [os.path.join(TERRAIN_VIEW_FOLDER, filename) for filename in filenames]
    if not all(os.path.isfile(path) and os.path.getsize(path) > 0 for path in paths):
        os.makedirs(TERRAIN_VIEW_FOLDER, exist_ok=True)
        try:
            generate_3d_mesh_renders(
                TERRAIN_VIEW_LOCATION[0],
                TERRAIN_VIEW_LOCATION[1],
                100.0,
                TERRAIN_VIEW_PREFIX,
                TERRAIN_VIEW_FOLDER,
                incline_scale=2.0,
                mesh_points=500,
                image_size=(1600, 900),
                sun_elevation=22.0,
                sun_azimuth=300.0,
            )
        except (OSError, RuntimeError, ValueError) as error:
            app.logger.error("Unable to render target-area views: %s", error)
            return jsonify({"error": "The lunar camera views could not be rendered."}), 503

    if not all(os.path.isfile(path) and os.path.getsize(path) > 0 for path in paths):
        app.logger.error("Terrain renderer did not create all target-area views.")
        return jsonify({"error": "The lunar camera views could not be rendered."}), 503

    labels = (
        "Overhead",
        "North oblique",
        "East oblique",
        "South oblique",
        "West oblique",
        "North grazing",
        "East grazing",
        "West grazing",
    )
    return jsonify({
        "location": {
            "latitude": TERRAIN_VIEW_LOCATION[0],
            "longitude": TERRAIN_VIEW_LOCATION[1],
        },
        "views": [
            {
                "name": name,
                "label": label,
                "url": url_for("static", filename=f"terrain_views/{filename}"),
            }
            for name, label, filename in zip(TERRAIN_VIEW_NAMES, labels, filenames)
        ],
    })


@app.route("/", methods=["GET", "POST"])
def index():
    values = DEFAULTS.copy()
    active_view = "mission"
    image_result = None
    image_error = None
    article_result = None
    form_error = None
    article_text = ""
    image_lat = ""
    image_lon = ""
    image_context_error = None

    if request.method == "POST":
        for key in ("start_name", "dest_name"):
            values[key] = (request.form.get(key) or DEFAULTS[key]).strip()[:80]
        try:
            for key in ("start_lat", "start_lon", "dest_lat", "dest_lon"):
                value = float(request.form.get(key) or str(DEFAULTS[key]))
                lower, upper = (-90, 90) if key.endswith("_lat") else (-180, 180)
                if not math.isfinite(value) or not lower <= value <= upper:
                    raise ValueError(f"{key.replace('_', ' ')} is out of range.")
                values[key] = value
        except ValueError:
            form_error = "Coordinates must be valid finite lunar latitude/longitude values."

        try:
            max_slope_degrees = _bounded_number(
                request.form.get(
                    "max_slope_degrees", str(DEFAULTS["max_slope_degrees"])
                ),
                "Slope screen limit",
                5.0,
                30.0,
            )
            planning_speed_kmh = _bounded_number(
                request.form.get(
                    "planning_speed_kmh", str(DEFAULTS["planning_speed_kmh"])
                ),
                "Planning speed",
                0.1,
                5.0,
            )
            values["max_slope_degrees"] = max_slope_degrees
            values["planning_speed_kmh"] = planning_speed_kmh
        except ValueError as error:
            form_error = str(error) if form_error is None else form_error + " " + str(error)

        article_text = request.form.get("article_text", "")[:12000]
        if article_text.strip():
            article_result = analyze_article(article_text)

        image_lat = request.form.get("image_lat", "").strip()
        image_lon = request.form.get("image_lon", "").strip()
        supplied_location = None
        if image_lat or image_lon:
            try:
                if not image_lat or not image_lon:
                    raise ValueError("Enter both image coordinates, or leave both blank.")
                supplied_location = (float(image_lat), float(image_lon))
                if (
                    not all(math.isfinite(value) for value in supplied_location)
                    or not -90 <= supplied_location[0] <= 90
                    or not -180 <= supplied_location[1] <= 180
                ):
                    raise ValueError("Image latitude or longitude is out of range.")
            except ValueError as error:
                image_error = str(error)

        upload = request.files.get("image")
        if upload and upload.filename:
            extension = os.path.splitext(secure_filename(upload.filename))[1].lower()
            if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                image_error = "Choose a PNG, JPEG, GIF, or WebP image."
            elif image_error is None:
                target_path = os.path.join(UPLOAD_FOLDER, uuid.uuid4().hex + extension)
                exif_location = None
                try:
                    upload.stream.seek(0)
                    with Image.open(upload.stream) as image:
                        image.verify()
                    upload.stream.seek(0)
                    with Image.open(upload.stream) as image:
                        exif_location = _extract_exif_location(image)
                    upload.stream.seek(0)
                    upload.save(target_path)
                    label, confidence, reason, scores = classify_image(target_path)
                    image_result = {
                        "label": label,
                        "confidence": confidence,
                        "reason": reason,
                        "scores": scores,
                        "location": {
                            "lat": supplied_location[0],
                            "lon": supplied_location[1],
                        } if supplied_location else (
                            {"lat": exif_location[0], "lon": exif_location[1]}
                            if exif_location else None
                        ),
                    }
                except (OSError, ValueError, RuntimeError, UnidentifiedImageError) as error:
                    image_error = str(error) or "The image could not be analyzed."
                    if os.path.exists(target_path):
                        os.remove(target_path)
                if image_result and image_result["location"]:
                    try:
                        image_result["nearby"] = analyze_nearby_terrain(
                            image_result["location"]["lat"],
                            image_result["location"]["lon"],
                        )
                    except (OSError, ValueError) as error:
                        image_context_error = str(error) or "Nearby terrain could not be sampled."

    if image_result and image_result["location"]:
        active_view = "movement"

    try:
        class_names = ", ".join(available_model_classes())
    except (OSError, ValueError):
        class_names = "Label metadata unavailable · retrain required"

    reference_links = _load_reference_links()
    return render_template_string(
        HTML_TEMPLATE,
        **values,
        active_view=active_view,
        image_lat=image_lat,
        image_lon=image_lon,
        photo_location=image_result["location"] if image_result else None,
        model_classes=class_names,
        model_validation=model_validation_summary(),
        dataset_summary=_image_dataset_summary(),
        reference_links=reference_links,
        dust_reference_links=_filter_reference_links(_DUST_LINK_TERMS),
        site_reference_links=_filter_reference_links(_SITE_LINK_TERMS),
        image_result=image_result,
        image_error=image_error,
        image_context_error=image_context_error,
        article_result=article_result,
        article_text=article_text,
        form_error=form_error,
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
