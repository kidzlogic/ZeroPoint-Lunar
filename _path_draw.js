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
