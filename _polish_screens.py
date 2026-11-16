# -*- coding: utf-8 -*-
"""Polish gauge/status copy and sync template into lunar_web_app.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

FUEL_OLD = '''function drawFuelGauge(canvas, fraction, text) {
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
}'''

FUEL_NEW = '''function drawFuelGauge(canvas, fraction, text) {
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
}'''


def patch_status(text: str) -> str:
    # Find paintDescent status block by unique markers
    old = (
        'if (status) status.textContent = !facts.heights.length ? "WAITING ON THE PATH" : open ? "SITE CLEAR" : "REVIEW REQUIRED";\n'
        '    if (chip) chip.className = "des-chip " + (open ? "go" : facts.heights.length ? "stop" : "");\n'
        '    const week = document.getElementById("des-water-foot");\n'
        '    if (week) week.textContent = water.stock ? water.stock.toLocaleString() + " L" : "0 L";\n'
        '    const cargo = document.getElementById("des-power-foot");\n'
    )
    if old not in text:
        print("WARN: status block not found exactly")
        return text
    # Find from old through caption line
    start = text.index(old)
    caption_marker = 'if (caption) caption.textContent ='
    cap_at = text.index(caption_marker, start)
    end = text.index("\n}", cap_at) + 2
    new = '''if (status) {
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
    const caption = document.getElementById("des-caption");
    if (caption) caption.textContent = "Planning simulation · " + keep.safe + " m safe radius, " + keep.dust + " m dust zone · LOLA pad checks in side panels.";
}'''
    return text[:start] + new + text[end:]


def enhance_descent_stage(text: str) -> str:
    """Add quad engine plumes + green altitude HUD box like the reference."""
    needle = "    context.fillStyle = \"rgba(255,172,78,.75)\";\n    context.beginPath();\n    context.moveTo(-8, 10);\n    context.lineTo(-3, 32);\n    context.lineTo(3, 32);\n    context.lineTo(8, 10);\n    context.closePath();\n    context.fill();\n    context.restore();"
    if needle not in text:
        print("WARN: single plume lander block not found")
        return text
    replacement = '''    const flameOffsets = [[-18, 8], [18, 8], [-8, 10], [8, 10]];
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
    context.restore();'''
    return text.replace(needle, replacement, 1)


def enhance_altitude_callout(text: str) -> str:
    old = '''    context.fillStyle = "rgba(4,12,18,.8)";
    context.fillRect(padX - 52, padY - 150 * scale, 104, 24);
    context.fillStyle = "#f4fbff";
    context.font = "700 14px Segoe UI, Arial";
    context.textAlign = "center";
    context.fillText(meters, padX, padY - 134 * scale);'''
    new = '''    context.fillStyle = "rgba(4,18,12,.88)";
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
    context.fillText(meters, padX, padY - 134 * scale);'''
    if old not in text:
        print("WARN: altitude callout not found")
        return text
    return text.replace(old, new, 1)


def strip_css_import(text: str) -> str:
    return text.replace(
        '        @import url("https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap");\n',
        "",
        1,
    )


def hide_purpose_on_final_screens(text: str) -> str:
    """Keep purpose for a11y but tuck it under cinematic headers."""
    css = """
        .ops-board > .purpose,
        .path-board > .purpose,
        .topo-board > .purpose,
        .hab-board > .purpose {
            margin: 0 10px 6px; opacity: .72; font-size: 12px;
        }
"""
    marker = "        /* ===== FINAL SCREEN LOOK"
    if marker not in text:
        return text
    # append near end of final block — before media query inside final block if present
    anchor = "        @media(max-width:1000px) {\n            .ops-mid, .ops-low, .topo-layout, .hab-body, .des-body { grid-template-columns:1fr; }"
    if anchor in text and "ops-board > .purpose" not in text:
        text = text.replace(anchor, css + "\n" + anchor, 1)
    return text


def sync_to_app(template_text: str) -> None:
    app = APP.read_text(encoding="utf-8")
    start = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
    end = app.index('"""', start)
    body = template_text
    if not body.startswith("\n"):
        body = "\n" + body
    if not body.endswith("\n"):
        body += "\n"
    APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")


def main() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    if FUEL_OLD in text:
        text = text.replace(FUEL_OLD, FUEL_NEW, 1)
        print("fuel gauge updated")
    else:
        print("WARN: fuel gauge block not found")
    text = patch_status(text)
    text = enhance_descent_stage(text)
    text = enhance_altitude_callout(text)
    text = strip_css_import(text)
    text = hide_purpose_on_final_screens(text)
    TEMPLATE.write_text(text, encoding="utf-8")
    sync_to_app(text)
    app = APP.read_text(encoding="utf-8")
    assert "TOUCHDOWN CONFIRMED" in text
    assert "TOUCHDOWN CONFIRMED" in app
    assert "Share Tech Mono" in text
    print("polished + synced")


if __name__ == "__main__":
    main()
