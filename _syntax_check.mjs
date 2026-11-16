
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js";
import {OrbitControls} from "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/controls/OrbitControls.js";
const map = L.map('map', {center: [null, null], zoom: 5, minZoom: 1, maxZoom: 9, crs: L.CRS.EPSG4326});
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
    const cy = height * 0.52;
    const radius = Math.min(width, height) * 0.36;
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
        context.moveTo(cx + Math.cos(angle) * (radius - 14), cy + Math.sin(angle) * (radius - 14));
        context.lineTo(cx + Math.cos(angle) * (radius - 6), cy + Math.sin(angle) * (radius - 6));
        context.stroke();
    }
    const needle = start + sweep * clamped;
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 16), cy + Math.sin(needle) * (radius - 16));
    context.stroke();
    context.fillStyle = color;
    context.beginPath();
    context.arc(cx, cy, 4, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#f4fbff";
    context.textAlign = "center";
    context.font = "bold 16px Segoe UI, Arial";
    context.fillText(caption, cx, cy + radius * 0.48);
    context.fillStyle = "#d7f6ff";
    context.font = "11px Segoe UI, Arial";
    context.fillText(label + ": " + caption, cx, height - 6);
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
    context.beginPath();
    values.forEach((value, index) => {
        const x = left + plotW * (index / Math.max(1, values.length - 1));
        const y = top + plotH * (1 - (value - min) / span);
        if (index) context.lineTo(x, y);
        else context.moveTo(x, y);
    });
    context.strokeStyle = color;
    context.shadowColor = color;
    context.shadowBlur = 8;
    context.lineWidth = 2;
    context.stroke();
    context.shadowBlur = 0;
    context.lineTo(left + plotW, top + plotH);
    context.lineTo(left, top + plotH);
    context.closePath();
    const wash = context.createLinearGradient(0, top, 0, top + plotH);
    wash.addColorStop(0, color);
    wash.addColorStop(1, "rgba(6,16,24,0)");
    context.globalAlpha = 0.35;
    context.fillStyle = wash;
    context.fill();
    context.globalAlpha = 1;
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
        fragmentShader: "varying vec3 vPos; void main(){ float line = min(abs(fract(vPos.x * 3.4) - 0.5), abs(fract(vPos.z * 3.4) - 0.5)); float grid = 1.0 - smoothstep(fwidth(line) * 0.65, fwidth(line) * 2.1, line); float r = length(vPos.xz); float rf = abs(fract(r * 5.5) - 0.5); float rings = (1.0 - smoothstep(fwidth(rf) * 0.5, fwidth(rf) * 1.9, rf)) * step(r, 0.78); float ang = atan(vPos.z, vPos.x) / 6.2831853 + 0.5; float sp = abs(fract(ang * 16.0) - 0.5); float spokes = (1.0 - smoothstep(fwidth(sp) * 0.4, fwidth(sp) * 1.7, sp)) * step(r, 0.78) * step(0.04, r); float alpha = max(grid * 0.42, max(rings * 0.95, spokes * 0.7)) * smoothstep(2.4, 0.05, r); if (alpha < 0.04) discard; gl_FragColor = vec4(0.42, 0.95, 1.0, alpha); }"
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
function createCraterView(canvas) {
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#010204");
    const camera = new THREE.PerspectiveCamera(36, 1, 0.08, 40);
    camera.position.set(0.32, 1.48, 1.82);
    camera.lookAt(0, -0.06, -0.05);
    const geo = habTerrainGeometry(260);
    const ground = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({map: habAlbedoTexture(), roughness: 0.93, metalness: 0.03}));
    ground.castShadow = true;
    ground.receiveShadow = true;
    scene.add(ground);
    scene.add(new THREE.Mesh(geo, habGridMaterial()));
    scene.add(new THREE.HemisphereLight(0xc5d4e4, 0x16110e, 0.85));
    scene.add(new THREE.AmbientLight(0x96a2b0, 0.42));
    const sun = new THREE.DirectionalLight(0xfff2df, 2.8);
    sun.position.set(-2.4, 3.4, 1.6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 0.4;
    sun.shadow.camera.far = 24;
    sun.shadow.camera.left = -6;
    sun.shadow.camera.right = 6;
    sun.shadow.camera.top = 6;
    sun.shadow.camera.bottom = -6;
    sun.shadow.bias = -0.00055;
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0xd5e7f4, 1.35);
    fill.position.set(0.6, 2.4, 1.1);
    scene.add(fill);
    const floor = habViewHeight(0, 0);
    const beamMat = new THREE.MeshBasicMaterial({color: 0xd8ffff, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false});
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.72, 12), beamMat);
    beam.position.y = floor + 0.36;
    scene.add(beam);
    const halo = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.02, 0.72, 12), new THREE.MeshBasicMaterial({color: 0x39e7ff, transparent: true, opacity: 0.28, blending: THREE.AdditiveBlending, depthWrite: false}));
    halo.position.copy(beam.position);
    scene.add(halo);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: habGlowSprite(), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false}));
    sprite.position.set(0, floor + 0.03, 0);
    sprite.scale.set(0.14, 0.14, 0.14);
    scene.add(sprite);
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
    return {
        resize() { habFitRenderer(renderer, camera, canvas); },
        render(t) {
            habFitRenderer(renderer, camera, canvas);
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
            beamMat.opacity = 0.72 + Math.sin(t * 4.2) * 0.22;
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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
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
    return {
        resize() { habFitRenderer(renderer, camera, canvas); },
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
    const samples = heights.map(value => (value - min) / span);
    context.beginPath();
    samples.forEach((value, index) => {
        const x = 2 + (width - 6) * index / (samples.length - 1);
        const y = 4 + (height - 8) * (1 - value);
        if (index) context.lineTo(x, y);
        else context.moveTo(x, y);
    });
    context.strokeStyle = "#7af4ff";
    context.shadowColor = "#3ee0f0";
    context.shadowBlur = 8;
    context.lineWidth = 1.6;
    context.stroke();
    context.lineTo(width - 4, height - 2);
    context.lineTo(2, height - 2);
    context.closePath();
    const wash = context.createLinearGradient(0, 0, 0, height);
    wash.addColorStop(0, "rgba(62,224,240,.4)");
    wash.addColorStop(1, "rgba(62,224,240,0)");
    context.shadowBlur = 0;
    context.fillStyle = wash;
    context.fill();
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
    for (let index = 1; index < climb.length; index += 1) {
        const slope = Number(climb[index].slope);
        const blocked = Number.isFinite(slope) && slope >= facts.limit;
        const close = Number.isFinite(slope) && !blocked && slope >= facts.limit - 3;
        const a = at(index - 1, climb[index - 1].height);
        const b = at(index, climb[index].height);
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.strokeStyle = blocked ? "#ff4d57" : close ? "#f0c14a" : "#39f08a";
        context.lineWidth = 2.6;
        context.stroke();
    }
    context.fillStyle = "#d7f4ff";
    context.font = "700 11px Segoe UI, Arial";
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
    const baseLine = document.getElementById("hab-base-line");
    if (baseLine) {
        const pad = likelyPad(facts);
        const kit = baseKit();
        const names = {habitat: "habitat cylinder", lab: "lab", rover: "rover", array: "solar mast"};
        const pieces = kit.map(id => names[id]).filter(Boolean).join(", ");
        baseLine.textContent = pad
            ? "Most likely base: " + (pad.clear ? "the clearest shoulder" : "the least steep ground") + " at " + pad.slope.toFixed(1) + "°. Draw " + pieces + ". " + pad.why + " The crater floor stays the cold middle, not the build site."
            : "Apply Options to place the base on the clearest shoulder beside the crater.";
    }
    const purpose = document.getElementById("hab-purpose");
    if (purpose) purpose.innerHTML = "<b>KEEP THE HABITAT ALIVE</b> " + optionLine() + ".";
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
    const walkClass = walkLabel === "GOOD WALK" ? "path-go" : "path-red";
    const speed = Number(document.getElementById("planning_speed_kmh").value) || 0;
    const point = item => Array.isArray(item) ? {lat: Number(item[0]), lon: Number(item[1])} : {lat: Number(item.lat), lon: Number(item.lon)};
    const hours = opsPlan && opsPlan.telemetry ? opsPlan.telemetry.battery_hours : null;
    const eta = km != null && speed > 0 ? (Number(km) / speed) * 60 : null;
    const site = document.getElementById("plan-destination").selectedOptions[0];
    const diameter = Number(site && site.dataset.diameter) || (Math.abs(pair[0]) > 85 ? 21 : 32);
    const craterR = diameter / 2;
    const radiusKm = Math.max(18, craterR * 1.45);
    const locLat = Number(document.getElementById("start_lat").value);
    const locLon = Number(document.getElementById("start_lon").value);
    const batteryPct = hours == null ? null : Math.max(0, Math.min(100, Math.round(Number(hours) / 24 * 100)));
    const projectKm = (lat, lon) => localProject(lat, lon, pair[0], pair[1]);
    const routeKm = route.map(item => {
        const at = point(item);
        return projectKm(at.lat, at.lon);
    });
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
    document.getElementById("path-status").innerHTML =
        "<h3>WALK CALL</h3>" +
        "<p>Call: <strong class='" + walkClass + "'>" + walkLabel + "</strong></p>" +
        "<p>Load: <strong>" + who + "</strong></p>" +
        "<p>Read: <strong class='path-go'>green is good</strong></p>" +
        "<p>Good steps: <strong class='path-go'>" + goodSteps + "</strong></p>" +
        "<p>Near limit: <strong class='path-gold'>" + nearSteps + "</strong></p>" +
        "<p>Blocked: <strong class='path-red'>" + badSteps + "</strong></p>" +
        "<p>Battery: <strong>" + (batteryPct == null ? "—" : batteryPct + "%") + "</strong></p>";
    document.getElementById("path-nav").innerHTML =
        "<h3>WHAT IS GOOD</h3>" +
        "<p>View: <strong>centered on the walk</strong></p>" +
        "<p>Target <strong>" + place + "</strong></p>" +
        "<p>Distance: <strong>" + (km != null ? Number(km).toFixed(1) + " km" : "—") + "</strong></p>" +
        "<p>ETA: <strong>" + etaText + "</strong></p>" +
        "<p>Climb limit: <strong>" + limit + "°</strong></p>" +
        "<p>Red polygons: <strong class='path-red'>" + kept.length + "</strong></p>" +
        "<p>At: <strong>" + (Number.isFinite(locLat) ? locLat.toFixed(2) : pair[0].toFixed(2)) + "°, " +
        (Number.isFinite(locLon) ? locLon.toFixed(1) : pair[1].toFixed(1)) + "°</strong></p>";
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
    const midE = (minE + maxE) / 2;
    const midN = (minN + maxN) / 2;
    let halfE = Math.max(2.4, (maxE - minE) * 0.72);
    let halfN = Math.max(2.4, (maxN - minN) * 0.72);
    const aspect = width / Math.max(1, height);
    if (halfE / halfN < aspect) halfE = halfN * aspect;
    else halfN = halfE / aspect;
    halfE *= 1.28;
    halfN *= 1.28;
    const vMinE = midE - halfE;
    const vMaxE = midE + halfE;
    const vMinN = midN - halfN;
    const vMaxN = midN + halfN;
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
    kept.forEach(item => {
        item.at = toXY(item.km.e, item.km.n);
    });
    kept.filter(item => inside(item.at)).slice(0, 5).forEach(item => {
        context.beginPath();
        context.arc(item.at.x, item.at.y, 6, 0, Math.PI * 2);
        context.fillStyle = "rgba(255, 59, 69, .82)";
        context.fill();
        context.lineWidth = 1.2;
        context.strokeStyle = "#ffd5d8";
        context.stroke();
    });
    const smooth = routeKm.map(pointKm => toXY(pointKm.e, pointKm.n));
    if (smooth.length > 1) {
        context.lineJoin = "round";
        context.lineCap = "round";
        context.strokeStyle = "rgba(0,0,0,.7)";
        context.lineWidth = 8;
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
            context.lineWidth = 4.5;
            context.stroke();
        }
    }
    const heights = opsTerrain ? ((cleared ? opsTerrain.route_elevation_km : opsTerrain.advisory_route_elevation_km) || []) : [];
    const startHigh = heights.length > 1 && Number(heights[0]) >= Number(heights[heights.length - 1]);
    const tag = (at, text, color, dy) => {
        if (!at) return;
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
    if (start) {
        context.fillStyle = "#f0d078";
        context.beginPath();
        context.arc(start.x, start.y, 6, 0, Math.PI * 2);
        context.fill();
        tag(start, startHigh ? "START · SHOULDER" : "START", "#f0d078", -16);
    }
    if (end) {
        context.fillStyle = "#7eefff";
        context.beginPath();
        context.arc(end.x, end.y, 6, 0, Math.PI * 2);
        context.fill();
        tag(end, startHigh ? "END · FLOOR" : "END", "#7eefff", 22);
    }
    if (smooth.length > 1) {
        const mid = smooth[Math.floor(smooth.length / 2)];
        tag(mid, walkLabel, walkLabel === "GOOD WALK" ? "#39f08a" : "#ffb15a", -28);
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
    requestAnimationFrame(() => {
        if (name === "ops" || name === "path" || name === "habitat" || name === "descent") paintOpsBoard();
        if (name === "terrain" && topoPayload) mountTopo(topoPayload);
        if (name === "descent") paintDescent();
    });
}
function showPage(page) {
    if (page === "home") openOptions(true);
    else if (page === "data") showScreen("habitat");
    else showScreen("ops");
}
const baseParts = [
    {id:"habitat", name:"Habitat", w:8.53, d:4.27, h:4.27, x:0, z:0, color:0xd7f6ff, size:"8.53 × 4.27 × 4.27 m · Destiny-class cylinder"},
    {id:"lab", name:"Lab", w:8.53, d:4.27, h:4.27, x:14, z:0, color:0x9ad7e8, size:"8.53 × 4.27 × 4.27 m · same cylinder"},
    {id:"rover", name:"Rover", w:3.1, d:1.8, h:1.14, x:18, z:8, color:0xf0c36a, size:"3.1 × 1.8 × 1.14 m · Lunar Roving Vehicle"},
    {id:"array", name:"Solar mast", w:3.5, d:0.4, h:10, x:0, z:30, color:0x5eebff, size:"3.5 m blanket on a 10 m mast · VSAT 10 kW goal"},
    {id:"pad", name:"Landing pad", w:20, d:20, h:0.4, x:2000, z:0, color:0xffb45e, size:"20 m marker · place it on the 2 km circle"}
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
    document.getElementById("yard-pad").addEventListener("click", () => {
        const pad = yardMeshes.pad.position;
        yardControls.target.set((yardMeshes.habitat.position.x + pad.x) / 2, 0, (yardMeshes.habitat.position.z + pad.z) / 2);
        yardCamera.position.set(yardControls.target.x + 40, 1400, yardControls.target.z + 1600);
    });
    updateLines();
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
document.getElementById("open-options").addEventListener("click", () => {
    const drawer = document.getElementById("options-drawer");
    openOptions(drawer.hidden);
});
document.getElementById("close-options").addEventListener("click", () => openOptions(false));
document.addEventListener("keydown", event => {
    if (event.key === "Escape") openOptions(false);
});
requestAnimationFrame(() => showScreen("descent"));
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
                const badge = document.getElementById("q-badge");
                if (badge) {
                    badge.dataset.tone = "wait";
                    badge.className = "q-badge wait";
                    badge.textContent = "Checking this crater";
                }
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
    boxes.forEach(box => { box.textContent = "Searching the web…"; });
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
document.getElementById("run-plan").addEventListener("click", () => {
    const name = applyChosenSite();
    const vehicle = document.getElementById("plan-vehicle").selectedOptions[0].textContent;
    const pad = document.getElementById("plan-pad").selectedOptions[0].textContent;
    document.getElementById("plan-cost").textContent =
        name + " · " + vehicle + " from " + pad + ". Reading the A* path. The answer stays on this page.";
    const badge = document.getElementById("q-badge");
    if (badge) {
        badge.dataset.tone = "wait";
        badge.className = "q-badge wait";
        badge.textContent = "Checking this crater";
    }
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
    solarStatus.textContent = "Loading measured NOAA GOES X-ray data…";
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
        state.slope + "° · " + state.speed.toFixed(1) + " km/h · " + watch + " decides the answer.";
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
        (moon.irradiance_wm2 != null ? moon.irradiance_wm2.toFixed(5) + " W/m²" : "Unavailable");
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
    badge.dataset.tone = tone;
    badge.className = "q-badge " + tone;
    badge.textContent = label;
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

const imageLook = [];
const imageDustTraps = [];

const imageLabel = null;
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
    galleryStatus.textContent = "Searching NASA's public image catalog…";
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
    const points = Array.isArray(path) ? path : [];
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
        const index = Math.floor(pos);
        const fraction = pos - index;
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
const photoLocation = null;
const imageNeedsAreaGuess = null;
const makeWaypointIcon = (label, kind) => L.divIcon({
    className: "waypoint-icon-wrap",
    html: '<span class="waypoint-pin ' + kind + '"><span>' + label + '</span></span>',
    iconSize: [38, 38],
    iconAnchor: [19, 19]
});
const startMarker = L.marker([null, null], {
    icon: makeWaypointIcon("R", "start"), title: "Rover start"
}).addTo(map);
const destMarker = L.marker([null, null], {
    icon: makeWaypointIcon("D", "destination"), title: "Destination"
}).addTo(map);
startMarker.bindPopup("START · " + null);
destMarker.bindPopup("DESTINATION · " + null);
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
    plumeScreenResult.textContent = "Screening the route against the entered corridor…";
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
                "https://ntrs.nasa.gov/citations/20220018746"
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
    cameraStatus.textContent = "Rendering target-area views from LRO color and LOLA elevation…";
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
    const query = new URLSearchParams(queryValues);
    try {
        const response = await fetch("/api/terrain?" + query.toString());
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Terrain analysis failed.");
        opsTerrain = payload;
        topoPayload = payload;
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
        const scene = new THREE.Scene();
        scene.background = new THREE.Color("#05080d");
        topoCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 5000);
        topoCamera.up.set(0, 0, 1);
        scene.add(new THREE.HemisphereLight(0xc9dcff, 0x1a140c, 0.45));
        topoLight = new THREE.DirectionalLight(0xffe6bf, 2.2);
        topoLight.position.set(-40, -20, 80);
        scene.add(topoLight);
        topoGrid = new THREE.GridHelper(1, 12, 0x1c6f86, 0x12384a);
        topoGrid.rotation.x = Math.PI / 2;
        scene.add(topoGrid);
        const geometry = new THREE.BufferGeometry();
        topoMaterial = new THREE.MeshStandardMaterial({vertexColors:true, roughness:0.85, metalness:0.02, side:THREE.DoubleSide});
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
    status.textContent = "Reading the elevation map…";
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
