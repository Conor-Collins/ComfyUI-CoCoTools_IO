import { app } from "../../../scripts/app.js";

const CANVAS_WIDTH = 400;
const CANVAS_HEIGHT = 200;
const COLORS = {
    bg: "#1a1a1a",
    grid: "#333333",
    text: "#cccccc",
    textDim: "#888888",
    red: { fill: "rgba(220,50,50,0.4)", stroke: "rgba(220,50,50,0.8)", solid: "rgba(220,50,50,0.7)" },
    green: { fill: "rgba(50,200,50,0.4)", stroke: "rgba(50,200,50,0.8)", solid: "rgba(50,200,50,0.7)" },
    blue: { fill: "rgba(50,100,220,0.4)", stroke: "rgba(50,100,220,0.8)", solid: "rgba(50,100,220,0.7)" },
    alpha: { fill: "rgba(255,255,255,0.4)", stroke: "rgba(255,255,255,0.8)", solid: "rgba(255,255,255,0.7)" },
    luminance: { fill: "rgba(200,200,200,0.4)", stroke: "rgba(200,200,200,0.8)", solid: "rgba(200,200,200,0.7)" },
};
const MODES = ["unified", "rgb", "red", "green", "blue", "alpha"];
const MODE_LABELS = { unified: "L", rgb: "RGB", red: "R", green: "G", blue: "B", alpha: "A" };

function drawHistogram(canvas, data, mode, useLog) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    if (!data) {
        ctx.fillStyle = COLORS.textDim;
        ctx.font = "12px monospace";
        ctx.textAlign = "center";
        ctx.fillText("No histogram data", w / 2, h / 2);
        return;
    }

    // Draw grid
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 0.5;
    for (let i = 1; i < 4; i++) {
        const x = (w * i) / 4;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }
    for (let i = 1; i < 4; i++) {
        const y = (h * i) / 4;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // Determine which channels to draw
    let channels = [];
    if (mode === "unified") {
        channels = [{ key: "luminance", colors: COLORS.luminance, solid: true }];
    } else if (mode === "rgb") {
        channels = [
            { key: "red", colors: COLORS.red, solid: false },
            { key: "green", colors: COLORS.green, solid: false },
            { key: "blue", colors: COLORS.blue, solid: false },
        ];
    } else {
        channels = [{ key: mode, colors: COLORS[mode], solid: true }];
    }

    // Find global max for scaling
    let globalMax = 0;
    for (const ch of channels) {
        const counts = data[ch.key];
        if (!counts) continue;
        for (const c of counts) {
            const val = useLog ? Math.log1p(c) : c;
            if (val > globalMax) globalMax = val;
        }
    }
    if (globalMax === 0) return;

    // Draw each channel
    for (const ch of channels) {
        const counts = data[ch.key];
        if (!counts) continue;

        const binCount = counts.length;
        if (binCount === 0) continue;
        const binWidth = w / binCount;

        ctx.fillStyle = ch.solid ? ch.colors.solid : ch.colors.fill;
        ctx.strokeStyle = ch.colors.stroke;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, h);

        for (let i = 0; i < binCount; i++) {
            const val = useLog ? Math.log1p(counts[i]) : counts[i];
            const barH = (val / globalMax) * h;
            const x = i * binWidth;
            ctx.lineTo(x, h - barH);
        }

        // Extend to right edge at last bin's height before dropping to baseline
        const lastVal = useLog ? Math.log1p(counts[binCount - 1]) : counts[binCount - 1];
        const lastBarH = (lastVal / globalMax) * h;
        ctx.lineTo(w, h - lastBarH);
        ctx.lineTo(w, h);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
    }
}

function formatStat(val) {
    if (val === null || val === undefined) return "N/A";
    return val.toFixed(4);
}

function createStatsSpan(className, text) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    return span;
}

app.registerExtension({
    name: "CocoTools.Histogram",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "HistogramNode") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            this._histogramData = null;
            this._histogramMode = "rgb";
            this._histogramLog = false;

            // Create container
            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px;";

            // Stats bar (top) — using safe DOM methods
            const statsTop = document.createElement("div");
            statsTop.style.cssText = "width:100%;font:10px monospace;color:#ccc;display:flex;justify-content:space-between;padding:0 4px;";
            const rangeSpan = createStatsSpan("hist-range", "Range: --");
            const bitDepthSpan = createStatsSpan("hist-bitdepth", "");
            bitDepthSpan.style.color = "#aaa";
            const clipSpan = createStatsSpan("hist-clip", "Clip: --");
            statsTop.appendChild(rangeSpan);
            statsTop.appendChild(bitDepthSpan);
            statsTop.appendChild(clipSpan);
            container.appendChild(statsTop);

            // Canvas
            const canvas = document.createElement("canvas");
            canvas.width = CANVAS_WIDTH;
            canvas.height = CANVAS_HEIGHT;
            canvas.style.cssText = "width:100%;border-radius:3px;";
            container.appendChild(canvas);

            // Stats bar (bottom) — using safe DOM methods
            const statsBottom = document.createElement("div");
            statsBottom.style.cssText = "width:100%;font:10px monospace;color:#888;padding:0 4px;line-height:1.4;";
            const statsLine1 = document.createElement("div");
            statsLine1.textContent = "Mean: -- StdDev: -- Median: --";
            const statsLine2 = document.createElement("div");
            statsLine2.textContent = "P5: -- P95: --";
            statsBottom.appendChild(statsLine1);
            statsBottom.appendChild(statsLine2);
            container.appendChild(statsBottom);

            // Mode buttons
            const btnRow = document.createElement("div");
            btnRow.style.cssText = "display:flex;gap:3px;align-items:center;flex-wrap:wrap;";

            for (const mode of MODES) {
                const btn = document.createElement("button");
                btn.textContent = MODE_LABELS[mode] || mode;
                btn.dataset.mode = mode;
                btn.style.cssText = "padding:2px 6px;font:10px monospace;border:1px solid #555;background:#2a2a2a;color:#ccc;border-radius:3px;cursor:pointer;";
                btn.addEventListener("click", () => {
                    this._histogramMode = mode;
                    this._updateHistogram();
                });
                btnRow.appendChild(btn);
            }

            // Separator
            const sep = document.createElement("span");
            sep.style.cssText = "color:#555;margin:0 2px;";
            sep.textContent = "|";
            btnRow.appendChild(sep);

            // Log/Lin toggle
            const logBtn = document.createElement("button");
            logBtn.textContent = "Lin";
            logBtn.dataset.role = "logToggle";
            logBtn.style.cssText = "padding:2px 6px;font:10px monospace;border:1px solid #555;background:#2a2a2a;color:#ccc;border-radius:3px;cursor:pointer;";
            logBtn.addEventListener("click", () => {
                this._histogramLog = !this._histogramLog;
                this._updateHistogram();
            });
            btnRow.appendChild(logBtn);
            container.appendChild(btnRow);

            // Store references
            this._histCanvas = canvas;
            this._histRangeSpan = rangeSpan;
            this._histBitDepthSpan = bitDepthSpan;
            this._histClipSpan = clipSpan;
            this._histStatsLine1 = statsLine1;
            this._histStatsLine2 = statsLine2;
            this._histBtnRow = btnRow;

            // Add as ComfyUI widget
            const widget = this.addDOMWidget("histogram_display", "custom", container, {
                serialize: false,
                getMinHeight: () => CANVAS_HEIGHT + 80,
            });
            widget.computeSize = () => [CANVAS_WIDTH, CANVAS_HEIGHT + 80];

            this._updateHistogram = () => {
                const data = this._histogramData;
                drawHistogram(this._histCanvas, data, this._histogramMode, this._histogramLog);

                // Update button highlights
                const buttons = this._histBtnRow.querySelectorAll("button[data-mode]");
                buttons.forEach((btn) => {
                    const isActive = btn.dataset.mode === this._histogramMode;
                    btn.style.background = isActive ? "#4a4a4a" : "#2a2a2a";
                    btn.style.borderColor = isActive ? "#888" : "#555";
                });

                // Update log toggle
                const logToggle = this._histBtnRow.querySelector('[data-role="logToggle"]');
                if (logToggle) {
                    logToggle.textContent = this._histogramLog ? "Log" : "Lin";
                    logToggle.style.background = this._histogramLog ? "#4a4a4a" : "#2a2a2a";
                }

                // Hide alpha button if no alpha channel
                const alphaBtn = this._histBtnRow.querySelector('[data-mode="alpha"]');
                if (alphaBtn && data) {
                    alphaBtn.style.display = data.alpha ? "" : "none";
                }

                // Update stats
                this._updateStats();
            };

            this._updateStats = () => {
                const data = this._histogramData;
                if (!data || !data.stats) {
                    this._histRangeSpan.textContent = "Range: --";
                    this._histBitDepthSpan.textContent = "";
                    this._histClipSpan.textContent = "Clip: --";
                    this._histStatsLine1.textContent = "Mean: -- StdDev: -- Median: --";
                    this._histStatsLine2.textContent = "P5: -- P95: --";
                    return;
                }

                const info = data.image_info || {};
                const range = info.data_range || [0, 1];
                this._histRangeSpan.textContent =
                    "Range: [" + range[0].toFixed(4) + " - " + range[1].toFixed(4) + "]  " + (info.width || "?") + "x" + (info.height || "?");

                // Bit depth readout
                const bd = info.bit_depth;
                this._histBitDepthSpan.textContent = bd ? (bd === 32 ? "32-bit float" : bd + "-bit") : "";

                // Get stats for current mode
                const mode = this._histogramMode;
                let statKeys = [];
                if (mode === "unified") statKeys = ["luminance"];
                else if (mode === "rgb") statKeys = ["red", "green", "blue"];
                else statKeys = [mode];

                // Average clip across displayed channels
                let clipLow = 0, clipHigh = 0, count = 0;
                for (const key of statKeys) {
                    const s = data.stats[key];
                    if (!s) continue;
                    clipLow += s.clip_low;
                    clipHigh += s.clip_high;
                    count++;
                }
                if (count > 0) {
                    clipLow /= count;
                    clipHigh /= count;
                }
                this._histClipSpan.textContent = "Clip: " + clipLow.toFixed(1) + "%/" + clipHigh.toFixed(1) + "%";

                // Show first channel stats in detail
                const primary = data.stats[statKeys[0]];
                if (primary) {
                    this._histStatsLine1.textContent =
                        "Mean: " + formatStat(primary.mean) + "  StdDev: " + formatStat(primary.stddev) + "  Median: " + formatStat(primary.median);
                    this._histStatsLine2.textContent =
                        "P5: " + formatStat(primary.p5) + "  P95: " + formatStat(primary.p95);
                }
            };

            // Initial draw
            drawHistogram(canvas, null, "rgb", false);

            return result;
        };

        nodeType.prototype.onExecuted = function (message) {
            if (onExecuted) onExecuted.apply(this, arguments);

            if (message && message.histogram_data && message.histogram_data.length > 0) {
                this._histogramData = message.histogram_data[0];
                this._updateHistogram();
            }
        };
    },
});
