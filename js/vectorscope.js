import { app } from "../../../scripts/app.js";

const CANVAS_SIZE = 400;
const CENTER = CANVAS_SIZE / 2;
const RADIUS = 180;

const COLORS = {
    bg: "#1a1a1a",
    graticule: "#333333",
    graticuleLabel: "#666666",
    text: "#cccccc",
    textDim: "#888888",
    dot: "rgba(255,255,255,0.05)",
    skinTone: "rgba(255,180,100,0.6)",
    btnActive: "#4a4a4a",
    btnInactive: "#2a2a2a",
    borderActive: "#888",
    borderInactive: "#555",
};

const YCBCR_TARGETS = [
    { name: "R", angle: 103.5, color: "#ff4444" },
    { name: "Y", angle: 167, color: "#ffff44" },
    { name: "G", angle: 241, color: "#44ff44" },
    { name: "C", angle: 283.5, color: "#44ffff" },
    { name: "B", angle: 347, color: "#4444ff" },
    { name: "M", angle: 61, color: "#ff44ff" },
];

const SKIN_TONE_ANGLE_DEG = 123;

const SRGB_GAMUT_NORMALIZED = {
    r: { x: (0.64 - 0.15) / 0.65, y: (0.33 - 0.05) / 0.65 },
    g: { x: (0.30 - 0.15) / 0.65, y: (0.60 - 0.05) / 0.65 },
    b: { x: (0.15 - 0.15) / 0.65, y: (0.06 - 0.05) / 0.65 },
    d65: { x: (0.3127 - 0.15) / 0.65, y: (0.3290 - 0.05) / 0.65 },
};

function drawGraticule(ctx) {
    ctx.strokeStyle = COLORS.graticule;
    ctx.lineWidth = 0.5;

    ctx.beginPath();
    ctx.arc(CENTER, CENTER, RADIUS, 0, Math.PI * 2);
    ctx.stroke();

    for (const frac of [0.25, 0.5, 0.75]) {
        ctx.beginPath();
        ctx.arc(CENTER, CENTER, RADIUS * frac, 0, Math.PI * 2);
        ctx.stroke();
    }

    ctx.beginPath();
    ctx.moveTo(CENTER - RADIUS, CENTER);
    ctx.lineTo(CENTER + RADIUS, CENTER);
    ctx.moveTo(CENTER, CENTER - RADIUS);
    ctx.lineTo(CENTER, CENTER + RADIUS);
    ctx.stroke();
}

function drawYCbCrTargets(ctx) {
    for (const target of YCBCR_TARGETS) {
        const rad = (target.angle * Math.PI) / 180;
        const dist = RADIUS * 0.75;
        const x = CENTER + Math.cos(rad) * dist;
        const y = CENTER - Math.sin(rad) * dist;

        ctx.strokeStyle = target.color;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x - 4, y - 4, 8, 8);

        ctx.fillStyle = target.color;
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const labelDist = RADIUS * 0.9;
        const lx = CENTER + Math.cos(rad) * labelDist;
        const ly = CENTER - Math.sin(rad) * labelDist;
        ctx.fillText(target.name, lx, ly);
    }
}

function drawSkinToneLine(ctx) {
    const rad = (SKIN_TONE_ANGLE_DEG * Math.PI) / 180;
    const endX = CENTER + Math.cos(rad) * RADIUS;
    const endY = CENTER - Math.sin(rad) * RADIUS;

    ctx.strokeStyle = COLORS.skinTone;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(CENTER, CENTER);
    ctx.lineTo(endX, endY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = COLORS.skinTone;
    ctx.font = "9px monospace";
    ctx.textAlign = "center";
    const labelDist = RADIUS * 0.95;
    ctx.fillText("Skin", CENTER + Math.cos(rad) * labelDist, CENTER - Math.sin(rad) * labelDist - 8);
}

function drawHSVHueRing(ctx) {
    for (let deg = 0; deg < 360; deg++) {
        const startRad = -(deg * Math.PI) / 180;
        const endRad = -((deg + 2) * Math.PI) / 180;

        ctx.strokeStyle = "hsl(" + deg + ", 100%, 50%)";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(CENTER, CENTER, RADIUS + 6, startRad, endRad, true);
        ctx.stroke();
    }
}

function drawCIExyOverlays(ctx) {
    const mapX = function (nx) { return CENTER + (nx - 0.5) * 2 * RADIUS; };
    const mapY = function (ny) { return CENTER - (ny - 0.5) * 2 * RADIUS; };

    ctx.strokeStyle = "rgba(255,255,255,0.4)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(mapX(SRGB_GAMUT_NORMALIZED.r.x), mapY(SRGB_GAMUT_NORMALIZED.r.y));
    ctx.lineTo(mapX(SRGB_GAMUT_NORMALIZED.g.x), mapY(SRGB_GAMUT_NORMALIZED.g.y));
    ctx.lineTo(mapX(SRGB_GAMUT_NORMALIZED.b.x), mapY(SRGB_GAMUT_NORMALIZED.b.y));
    ctx.closePath();
    ctx.stroke();

    ctx.fillStyle = "rgba(255,255,255,0.6)";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillText("R", mapX(SRGB_GAMUT_NORMALIZED.r.x), mapY(SRGB_GAMUT_NORMALIZED.r.y) + 14);
    ctx.fillText("G", mapX(SRGB_GAMUT_NORMALIZED.g.x), mapY(SRGB_GAMUT_NORMALIZED.g.y) - 8);
    ctx.fillText("B", mapX(SRGB_GAMUT_NORMALIZED.b.x), mapY(SRGB_GAMUT_NORMALIZED.b.y) + 14);

    const d65x = mapX(SRGB_GAMUT_NORMALIZED.d65.x);
    const d65y = mapY(SRGB_GAMUT_NORMALIZED.d65.y);
    ctx.strokeStyle = "rgba(255,255,255,0.6)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(d65x - 4, d65y);
    ctx.lineTo(d65x + 4, d65y);
    ctx.moveTo(d65x, d65y - 4);
    ctx.lineTo(d65x, d65y + 4);
    ctx.stroke();
    ctx.fillText("D65", d65x + 16, d65y - 4);
}

function mapScatterPoint(x, y, colorModel) {
    if (colorModel === "YCbCr") {
        return [CENTER + x * 2 * RADIUS, CENTER + y * 2 * RADIUS];
    } else if (colorModel === "HSV") {
        return [CENTER + x * RADIUS, CENTER - y * RADIUS];
    }
    return [CENTER + (x - 0.5) * 2 * RADIUS, CENTER - (y - 0.5) * 2 * RADIUS];
}

function drawVectorscope(canvas, data, showGuides, showSkin) {
    const ctx = canvas.getContext("2d");

    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    if (!data) {
        ctx.fillStyle = COLORS.textDim;
        ctx.font = "12px monospace";
        ctx.textAlign = "center";
        ctx.fillText("No vectorscope data", CENTER, CENTER);
        return;
    }

    drawGraticule(ctx);

    const colorModel = data.color_model;

    if (!data.x_coords || !data.y_coords) return;

    if (showGuides) {
        if (colorModel === "YCbCr") {
            drawYCbCrTargets(ctx);
        } else if (colorModel === "HSV") {
            drawHSVHueRing(ctx);
        } else if (colorModel === "CIE xy") {
            drawCIExyOverlays(ctx);
        }
    }

    if (showSkin && colorModel === "YCbCr") {
        drawSkinToneLine(ctx);
    }

    ctx.save();
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, RADIUS, 0, Math.PI * 2);
    ctx.clip();

    ctx.fillStyle = COLORS.dot;
    const xCoords = data.x_coords;
    const yCoords = data.y_coords;

    for (let i = 0; i < xCoords.length; i++) {
        const pt = mapScatterPoint(xCoords[i], yCoords[i], colorModel);
        ctx.fillRect(pt[0], pt[1], 1, 1);
    }

    ctx.restore();
}

app.registerExtension({
    name: "CocoTools.Vectorscope",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "VectorscopeNode") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        const origOnExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onNodeCreated = function () {
            const result = origOnNodeCreated?.apply(this, arguments);

            this._vectorscopeData = null;
            this._showGuides = true;
            this._showSkin = true;

            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px;";

            const infoBar = document.createElement("div");
            infoBar.style.cssText = "width:100%;font:10px monospace;color:#ccc;padding:0 4px;";
            infoBar.textContent = "No data";
            container.appendChild(infoBar);

            const canvas = document.createElement("canvas");
            canvas.width = CANVAS_SIZE;
            canvas.height = CANVAS_SIZE;
            canvas.style.cssText = "width:100%;border-radius:3px;";
            container.appendChild(canvas);

            const btnRow = document.createElement("div");
            btnRow.style.cssText = "display:flex;gap:3px;align-items:center;";

            const guidesBtn = document.createElement("button");
            guidesBtn.textContent = "Guides";
            guidesBtn.style.cssText = "padding:2px 6px;font:10px monospace;border:1px solid #888;background:#4a4a4a;color:#ccc;border-radius:3px;cursor:pointer;";
            guidesBtn.addEventListener("click", () => {
                this._showGuides = !this._showGuides;
                this._updateVectorscope();
            });
            btnRow.appendChild(guidesBtn);

            const skinBtn = document.createElement("button");
            skinBtn.textContent = "Skin";
            skinBtn.style.cssText = "padding:2px 6px;font:10px monospace;border:1px solid #888;background:#4a4a4a;color:#ccc;border-radius:3px;cursor:pointer;";
            skinBtn.addEventListener("click", () => {
                this._showSkin = !this._showSkin;
                this._updateVectorscope();
            });
            btnRow.appendChild(skinBtn);

            container.appendChild(btnRow);

            this._vsCanvas = canvas;
            this._vsInfoBar = infoBar;
            this._vsGuidesBtn = guidesBtn;
            this._vsSkinBtn = skinBtn;

            const widget = this.addDOMWidget("vectorscope_display", "custom", container, {
                serialize: false,
                getMinHeight: function () { return CANVAS_SIZE + 60; },
            });
            widget.computeSize = function () { return [CANVAS_SIZE, CANVAS_SIZE + 60]; };

            this._updateVectorscope = () => {
                const data = this._vectorscopeData;
                drawVectorscope(this._vsCanvas, data, this._showGuides, this._showSkin);

                this._vsGuidesBtn.style.background = this._showGuides ? COLORS.btnActive : COLORS.btnInactive;
                this._vsGuidesBtn.style.borderColor = this._showGuides ? COLORS.borderActive : COLORS.borderInactive;

                const isYCbCr = data && data.color_model === "YCbCr";
                this._vsSkinBtn.style.display = isYCbCr ? "" : "none";
                this._vsSkinBtn.style.background = this._showSkin ? COLORS.btnActive : COLORS.btnInactive;
                this._vsSkinBtn.style.borderColor = this._showSkin ? COLORS.borderActive : COLORS.borderInactive;

                if (data) {
                    const info = data.image_info || {};
                    this._vsInfoBar.textContent =
                        data.color_model + "  " +
                        (info.width || "?") + "x" + (info.height || "?") + "  " +
                        data.point_count + " pts";
                } else {
                    this._vsInfoBar.textContent = "No data";
                }
            };

            drawVectorscope(canvas, null, true, true);

            return result;
        };

        nodeType.prototype.onExecuted = function (message) {
            if (origOnExecuted) origOnExecuted.apply(this, arguments);

            if (message && message.vectorscope_data && message.vectorscope_data.length > 0) {
                this._vectorscopeData = message.vectorscope_data[0];
                this._updateVectorscope();
            }
        };
    },
});
