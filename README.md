# Zero-Point Lunar

A lunar mission planning and simulator web app. Pick a crater, set climb limits and shelter rules, then walk through Ops, pathfinding, 3D terrain, habitat checks, and a descent touchdown screen.

**Main app:** `lunar_web_app.py` (also launched by `run_zeropoint_lunar.py`)  
**URL after start:** [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## Commands to run before / to start

From the project folder (`ZeroPoint-Lunar`):

### 1. Create and activate the virtual environment (first time)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```powershell
pip install flask tensorflow pillow numpy scikit-learn pyvista
```

If the project already has a `venv` folder with packages installed, you can skip this and only activate it.

### 3. (Optional) Train models if they are missing

Trained files normally already live under `models/`. Only retrain if those files are gone or you changed the dataset.

```powershell
# Image hazard / terrain classifier (used for photo uploads)
python train.py

# Shackleton rim walk / pad / sun / Earth / go-zone models
python train_shackleton_models.py
```

### 4. Start the main app


```powershell
python lunar_web_app.py
```

Then open **http://127.0.0.1:5000** in your browser.

Stop the server with `Ctrl+C` in the terminal.

### 5. Public link that stays up after you close the terminal

Public URL: **https://banshee-bok-depletion.ngrok-free.dev**

From the project folder, start the app and the tunnel as their own processes:

```powershell
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "lunar_web_app.py" -WorkingDirectory "c:\Users\kidzl\OneDrive\Coding\ZeroPoint-Lunar" -WindowStyle Hidden

Start-Process -FilePath "ngrok" -ArgumentList "http","5000","--url","https://banshee-bok-depletion.ngrok-free.dev" -WindowStyle Hidden
```

You can close the terminal after that. The link keeps working while this computer is on.

Shutting down or restarting the computer stops the site. Turn the PC back on, then run the two commands above again.

Force stop later (this app and the ngrok tunnel only):

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*lunar_web_app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Stop-Process -Name ngrok -Force
```

---

## How to use / “play” the app

### Top tabs

| Tab | What it is |
|-----|------------|
| **Home** | Mission briefing and Options (site setup) |
| **Simulator** | The interactive mission screens |
| **Data** | Deeper side checks (surface, flares, power path, radiation, sun & cold) |

### Options (do this first)

1. Click **Options**.
2. Choose a **crater or region** (Haworth, Shackleton rim, de Gerlache, etc.).
3. Set:
   - Who to protect (habitat / crew / both)
   - Storm shelter yes/no
   - Steepest tether **slope** (°)
   - Path priority (slope / sun / Earth radio)
   - Walk speed
   - Base kit (habitat, lab, rover, solar mast)
   - Launch vehicle and Earth pad
4. Click **Apply to every screen**.

That scoring and climb limit drive Pathfinder, Terrain, Habitat, and Descent.

### Simulator screens

Use the screen buttons across the top:

1. **Mission & Launch Ops** — site call, pros/cons, telemetry gauges, altitude & slope along the walk.
2. **Solar-to-Ice Pathfinder** — map of the walk: green = under climb limit, gold = close, red = blocked.
3. **3D Topography Inspector** — drag / use sliders for azimuth, elevation, zoom; toggle wireframe, slope heatmap, sun light, grid.
4. **AI Habitat Scanner** — habitat viability, dust/flare/radiation/thermal bars, crater shoulder for the base.
5. **Descent Simulator** — touchdown concept, plume stand-off, water/ice planning band, surface map zoom.

Suggested loop: **Options → Apply → Pathfinder → Terrain → Habitat → Descent → Ops**.

### Data / Home extras

On **Home** / **Data** you can also:

- Run **Where are you landing?** quiz → **Show the best place**
- Click **Try the Shackleton rim** for the five trained LOLA cell models
- Check **Solar flares** (live NOAA GOES X-ray when online)
- Upload a lunar image for experimental classifier labels (not a flight clearance)
- Screen a candidate route against a dust-plume corridor after terrain analysis

---

## Quick tip

Internet helps for NOAA X-ray and some NASA map/terrain fetches. Core screens still work with the local models and bundled logic if a live feed fails.

This app is **decision support / simulation**, not real flight guidance or a safety clearance.
