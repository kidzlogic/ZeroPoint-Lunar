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
        context.fillStyle = "#f4f7f8";
        context.strokeStyle = "#9ad7e4";
        context.fillRect(-48, -18, 36, 18);
        context.strokeRect(-48, -18, 36, 18);
    }
    if (has("lab")) {
        context.fillStyle = "#d5e4ea";
        context.strokeStyle = "#9ad7e4";
        context.fillRect(-8, -16, 28, 16);
        context.strokeRect(-8, -16, 28, 16);
    }
    if (has("array")) {
        context.strokeStyle = "#7af4ff";
        context.beginPath();
        context.moveTo(30, 2);
        context.lineTo(30, -30);
        context.stroke();
        context.fillStyle = "#0c3040";
        context.fillRect(22, -30, 20, 12);
        context.strokeRect(22, -30, 20, 12);
    }
    if (has("rover")) {
        context.fillStyle = "#e6c36a";
        context.fillRect(-46, 6, 18, 8);
    }
    context.restore();
}
function drawHabSite() {
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
    context.fillStyle = "#8fd8df";
    context.font = "700 11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("RETRO-THRUST VECTOR", 8, 16);
    const cx = width * 0.32;
    const cy = height * 0.78;
    const radius = Math.min(width * 0.28, height * 0.42);
    for (let index = 0; index < 18; index += 1) {
        const a0 = Math.PI + Math.PI * index / 18;
        const a1 = Math.PI + Math.PI * (index + 1) / 18;
        context.strokeStyle = "hsl(" + (120 - index * 6.5) + ", 78%, 52%)";
        context.lineWidth = 7;
        context.beginPath();
        context.arc(cx, cy, radius, a0, a1);
        context.stroke();
    }
    const needle = Math.PI + Math.PI * Math.max(0, Math.min(1, fraction));
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 2), cy + Math.sin(needle) * (radius - 2));
    context.stroke();
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(18, Math.floor(height * 0.32)) + "px Segoe UI, Arial";
    context.textAlign = "right";
    context.fillText(percentText, width - 10, height * 0.5);
    context.fillStyle = "#9ad7e4";
    context.font = "700 12px Segoe UI, Arial";
    context.fillText("THRUST", width - 10, height * 0.5 + 16);
    context.textAlign = "left";
    context.fillStyle = "#d7f4ff";
    context.font = "12px Segoe UI, Arial";
    context.fillText("Vector 0.0°   planned settle", 8, height - 8);
}
function drawVelocityGauge(canvas, ready) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#8fd8df";
    context.font = "700 11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("VELOCITY", 8, 16);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(20, Math.floor(height * 0.36)) + "px Segoe UI, Arial";
    context.fillText(ready ? "0.0 m/s" : "—", 8, height * 0.48);
    context.fillStyle = "#7af4ff";
    context.font = "600 13px Segoe UI, Arial";
    context.fillText(ready ? "↓  0.0 m/s" : "on the pad", 8, height * 0.48 + 20);
    context.fillStyle = "#9ad7e4";
    context.font = "12px Segoe UI, Arial";
    context.fillText("Touchdown speed. Not a flying model.", 8, height - 8);
}
function drawAltitudeGauge(canvas, meters) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#8fd8df";
    context.font = "700 11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("ALTITUDE", 8, 16);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(18, Math.floor(height * 0.32)) + "px Segoe UI, Arial";
    context.fillText(meters == null ? "—" : meters.toLocaleString() + " m", 8, height * 0.46);
    context.fillStyle = "#7af4ff";
    context.font = "600 13px Segoe UI, Arial";
    context.fillText(meters == null ? "LOLA pad" : "↓  0 m above the pad", 8, height * 0.46 + 18);
    context.fillStyle = "#9ad7e4";
    context.font = "12px Segoe UI, Arial";
    context.fillText("LOLA elevation of the high pad.", 8, height - 8);
}
function drawFuelGauge(canvas, fraction, text) {
    const fit = hudFrame(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    context.fillStyle = "#8fd8df";
    context.font = "700 11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText("FUEL", 8, 16);
    context.fillStyle = "#f4fbff";
    context.font = "700 " + Math.max(20, Math.floor(height * 0.34)) + "px Segoe UI, Arial";
    context.fillText(text, 8, height * 0.46);
    context.fillStyle = "#102833";
    context.fillRect(8, height * 0.58, width - 16, 12);
    const grad = context.createLinearGradient(8, 0, width - 8, 0);
    grad.addColorStop(0, "#3dff9a");
    grad.addColorStop(0.72, "#f0c14a");
    grad.addColorStop(1, "#ff4d57");
    context.fillStyle = grad;
    context.fillRect(8, height * 0.58, (width - 16) * Math.max(0, Math.min(1, fraction)), 12);
    context.fillStyle = "#9ad7e4";
    context.font = "12px Segoe UI, Arial";
    context.fillText("Battery reserve for the walk.", 8, height - 8);
}
function drawDescentStage(facts, keep) {
    const fit = opsFit(document.getElementById("des-stage"));
    if (!fit) return;
    const {context, width, height} = fit;
    context.clearRect(0, 0, width, height);
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#02040a");
    sky.addColorStop(0.42, "#07111a");
    sky.addColorStop(1, "#12160f");
    context.fillStyle = sky;
    context.fillRect(0, 0, width, height);
    for (let index = 0; index < 70; index += 1) {
        const x = (index * 97) % width;
        const y = (index * 53) % Math.floor(height * 0.48);
        context.fillStyle = "rgba(230,240,255," + (0.35 + (index % 5) * 0.1) + ")";
        context.fillRect(x, y, index % 7 === 0 ? 2 : 1, index % 7 === 0 ? 2 : 1);
    }
    const earthR = Math.min(width, height) * 0.11;
    const earthX = width * 0.16;
    const earthY = height * 0.16;
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
    const ground = context.createLinearGradient(0, groundY - 30, 0, height);
    ground.addColorStop(0, "#8a8172");
    ground.addColorStop(0.25, "#4a463e");
    ground.addColorStop(1, "#141610");
    context.fillStyle = ground;
    context.beginPath();
    context.moveTo(0, groundY + 8);
    context.lineTo(width * 0.18, groundY - 6);
    context.lineTo(width * 0.46, groundY + 18);
    context.lineTo(width * 0.72, groundY - 10);
    context.lineTo(width, groundY + 12);
    context.lineTo(width, height);
    context.lineTo(0, height);
    context.closePath();
    context.fill();
    const padX = width * 0.56;
    const padY = groundY + 4;
    context.setLineDash([7, 5]);
    context.strokeStyle = "#ff9a3c";
    context.lineWidth = 2;
    context.beginPath();
    context.ellipse(padX, padY + 8, 118, 28, -0.15, 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    context.strokeStyle = "#3dff9a";
    context.beginPath();
    context.ellipse(padX, padY + 8, 62, 16, -0.15, 0, Math.PI * 2);
    context.stroke();
    context.save();
    context.translate(padX, padY);
    context.strokeStyle = "#e7eef2";
    context.fillStyle = "#f7f8f6";
    context.lineWidth = 3;
    [[-34, 0, -16, -42], [34, 0, 16, -42], [-22, 2, -8, -34], [22, 2, 8, -34]].forEach(leg => {
        context.beginPath();
        context.moveTo(leg[0], leg[1]);
        context.lineTo(leg[2], leg[3]);
        context.stroke();
    });
    context.fillStyle = "rgba(255, 168, 70, .9)";
    context.beginPath();
    context.ellipse(0, -6, 12, 18, 0, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#f4f7f8";
    context.fillRect(-18, -86, 36, 40);
    context.strokeStyle = "#c5ced4";
    context.strokeRect(-18, -86, 36, 40);
    context.fillStyle = "#c6a15a";
    context.fillRect(-20, -64, 40, 16);
    context.fillStyle = "#1c242c";
    context.fillRect(-8, -80, 16, 8);
    context.restore();
    context.strokeStyle = "#7af4ff";
    context.lineWidth = 1.5;
    context.beginPath();
    context.moveTo(padX, padY - 86);
    context.lineTo(padX, padY - 120);
    context.stroke();
    const meters = facts.maxH == null ? "—" : Math.round(facts.maxH * 1000).toLocaleString() + " m";
    context.fillStyle = "rgba(4,12,18,.8)";
    context.fillRect(padX - 36, padY - 148, 92, 24);
    context.fillStyle = "#f4fbff";
    context.font = "700 14px Segoe UI, Arial";
    context.textAlign = "center";
    context.fillText(meters, padX + 10, padY - 131);
    context.textAlign = "left";
    context.font = "700 13px Segoe UI, Arial";
    context.fillStyle = "#d7f4ff";
    context.fillText(facts.place.toUpperCase(), 16, height * 0.08);
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
function drawDescentMap(facts) {
    const fit = opsFit(document.getElementById("des-map"));
    if (!fit) return;
    const {context, width, height} = fit;
    const pad = likelyPad(facts);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#1a1c18";
    context.fillRect(0, 0, width, height);
    const ground = context.createRadialGradient(width * 0.45, height * 0.55, 8, width * 0.5, height * 0.5, width * 0.6);
    ground.addColorStop(0, "#6a6458");
    ground.addColorStop(1, "#2a2824");
    context.fillStyle = ground;
    context.beginPath();
    context.ellipse(width * 0.48, height * 0.58, width * 0.42, height * 0.32, 0, 0, Math.PI * 2);
    context.fill();
    drawBaseGlyph(context, width * 0.46, height * 0.58, baseKit(), Math.max(0.7, Math.min(width, height) / 180));
    context.fillStyle = "#3dff9a";
    context.beginPath();
    context.arc(width * 0.7, height * 0.34, 4, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#f4fbff";
    context.font = "700 11px Segoe UI, Arial";
    context.textAlign = "left";
    context.fillText(pad && pad.clear ? "CLEAREST PAD" : "LEAST STEEP", 8, 16);
    context.font = "11px Segoe UI, Arial";
    context.fillStyle = "#9ad7e4";
    context.fillText(pad ? pad.slope.toFixed(1) + "°  landing site" : "Waiting on the path", 8, 30);
    context.textAlign = "right";
    context.fillText("N", width - 8, 14);
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
    const padMeters = facts.maxH == null ? null : Math.round(facts.maxH * 1000);
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
    drawDescentStage(facts, keep);
    drawDescentPlume(keep);
    drawDescentMap(facts);
    const rate = document.getElementById("des-water-rate");
    if (rate) rate.innerHTML = water.perDay + " <span>L/day</span>";
    const total = document.getElementById("des-water-total");
    if (total) total.textContent = "Total: " + (water.stock ? water.stock.toLocaleString() + " L" : "0 L");
    const fill = document.getElementById("des-water-fill");
    if (fill) fill.style.height = Math.round(water.fill * 100) + "%";
    const note = document.getElementById("des-water-note");
    if (note) note.textContent = water.note;
    const iceNode = document.getElementById("des-ice");
    if (iceNode) iceNode.innerHTML = "<b>ICE · " + ice.title + "</b> " + ice.detail;
    const status = document.getElementById("des-status");
    const chip = document.getElementById("des-status-chip");
    const elev = facts.maxH == null ? "" : " · " + Math.round(facts.maxH * 1000).toLocaleString() + " m";
    if (status) status.textContent = !facts.heights.length ? "WAITING ON THE PATH" : open ? "CONFIRMED" + elev : "HOLD" + elev;
    if (chip) chip.className = "des-chip " + (open ? "go" : facts.heights.length ? "stop" : "");
    const week = document.getElementById("des-water-foot");
    if (week) week.textContent = water.stock ? water.stock.toLocaleString() + " L" : "0 L";
    const cargo = document.getElementById("des-power-foot");
    if (cargo) cargo.textContent = !facts.heights.length ? "—" : pad && pad.clear ? "100%" : "HOLD";
    const missionFoot = document.getElementById("des-mission-foot");
    const missionChip = document.getElementById("des-mission-chip");
    if (missionFoot) missionFoot.textContent = facts.storm ? "STORM" : open ? "SUCCESS" : "REVIEW";
    if (missionChip) missionChip.className = "des-chip " + (facts.storm ? "stop" : open ? "go" : "");
    const caption = document.getElementById("des-caption");
    if (caption) caption.textContent = keep.safe + " m safe radius, " + keep.dust + " m dust zone. The lander is a still.";
}
