import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// --- File Browser Modal ---

async function fetchDirectory(dirPath, extensions) {
    const params = new URLSearchParams();
    if (dirPath) params.set("path", dirPath);
    if (extensions) params.set("extensions", extensions);
    const resp = await api.fetchApi(`/cocotools/browse?${params.toString()}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || `HTTP ${resp.status}`);
    }
    return resp.json();
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
}

function clearChildren(el) {
    while (el.firstChild) {
        el.removeChild(el.firstChild);
    }
}

function openFileBrowser({ startPath = "", extensions = "", title = "Browse", mode = "file", onSelect, onClose }) {
    // Overlay
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;";

    // Modal container
    const modal = document.createElement("div");
    modal.style.cssText = "background:#1a1a1a;border:1px solid #444;border-radius:8px;width:600px;max-height:80vh;display:flex;flex-direction:column;font-family:monospace;color:#ddd;box-shadow:0 8px 32px rgba(0,0,0,0.5);";

    // Header
    const header = document.createElement("div");
    header.style.cssText = "padding:12px 16px;border-bottom:1px solid #333;display:flex;align-items:center;gap:8px;";

    const titleEl = document.createElement("span");
    titleEl.textContent = title;
    titleEl.style.cssText = "font-size:14px;font-weight:bold;color:#fff;";
    header.appendChild(titleEl);

    const spacer = document.createElement("span");
    spacer.style.cssText = "flex:1;";
    header.appendChild(spacer);

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "\u2715";
    closeBtn.style.cssText = "background:none;border:none;color:#888;font-size:18px;cursor:pointer;padding:0 4px;";
    closeBtn.addEventListener("click", close);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // Path bar
    const pathBar = document.createElement("div");
    pathBar.style.cssText = "padding:8px 16px;border-bottom:1px solid #333;display:flex;gap:6px;align-items:center;";

    const upBtn = document.createElement("button");
    upBtn.textContent = "\u2191";
    upBtn.title = "Parent directory";
    upBtn.style.cssText = "background:#2a2a2a;border:1px solid #444;color:#ddd;font-size:14px;cursor:pointer;padding:4px 8px;border-radius:4px;";
    pathBar.appendChild(upBtn);

    const pathInput = document.createElement("input");
    pathInput.type = "text";
    pathInput.style.cssText = "flex:1;background:#111;border:1px solid #444;color:#ddd;font-family:monospace;font-size:12px;padding:6px 8px;border-radius:4px;outline:none;";
    pathInput.placeholder = "Enter path...";
    pathBar.appendChild(pathInput);
    modal.appendChild(pathBar);

    // Error display
    const errorEl = document.createElement("div");
    errorEl.style.cssText = "padding:4px 16px;color:#f66;font-size:11px;display:none;";
    modal.appendChild(errorEl);

    // File list
    const listContainer = document.createElement("div");
    listContainer.style.cssText = "flex:1;overflow-y:auto;min-height:200px;max-height:50vh;";
    modal.appendChild(listContainer);

    // Footer (for directory mode)
    const footer = document.createElement("div");
    footer.style.cssText = "padding:10px 16px;border-top:1px solid #333;display:flex;justify-content:flex-end;gap:8px;";

    if (mode === "directory") {
        const selectFolderBtn = document.createElement("button");
        selectFolderBtn.textContent = "Select This Folder";
        selectFolderBtn.style.cssText = "background:#2563eb;border:none;color:#fff;font-family:monospace;font-size:12px;padding:6px 16px;border-radius:4px;cursor:pointer;";
        selectFolderBtn.addEventListener("click", () => {
            const currentPath = pathInput.value.trim();
            if (currentPath) {
                onSelect(currentPath);
                close();
            }
        });
        footer.appendChild(selectFolderBtn);
    }

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "background:#333;border:1px solid #555;color:#ddd;font-family:monospace;font-size:12px;padding:6px 16px;border-radius:4px;cursor:pointer;";
    cancelBtn.addEventListener("click", close);
    footer.appendChild(cancelBtn);
    modal.appendChild(footer);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    let currentPath = "";

    function close() {
        document.body.removeChild(overlay);
        document.removeEventListener("keydown", onKey);
        onClose?.();
    }

    function onKey(e) {
        if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);

    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) close();
    });

    async function navigate(dirPath) {
        errorEl.style.display = "none";
        clearChildren(listContainer);

        const loading = document.createElement("div");
        loading.textContent = "Loading...";
        loading.style.cssText = "padding:20px;text-align:center;color:#888;";
        listContainer.appendChild(loading);

        try {
            const data = await fetchDirectory(dirPath, extensions);
            currentPath = data.path || "";
            pathInput.value = currentPath;
            clearChildren(listContainer);

            if (data.items.length === 0) {
                const empty = document.createElement("div");
                empty.textContent = "Empty directory";
                empty.style.cssText = "padding:20px;text-align:center;color:#666;";
                listContainer.appendChild(empty);
                return;
            }

            for (const item of data.items) {
                const row = document.createElement("div");
                row.style.cssText = "padding:6px 16px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:12px;border-bottom:1px solid #222;";

                row.addEventListener("mouseenter", () => { row.style.background = "#2a2a2a"; });
                row.addEventListener("mouseleave", () => { row.style.background = "none"; });

                const icon = document.createElement("span");
                icon.style.cssText = "font-size:14px;width:20px;text-align:center;flex-shrink:0;";

                const name = document.createElement("span");
                name.style.cssText = "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
                name.textContent = item.name;

                if (item.type === "directory") {
                    icon.textContent = "\uD83D\uDCC1";
                    name.style.color = "#7cb3f0";
                    row.addEventListener("click", () => {
                        navigate(item.path || (currentPath ? currentPath + "/" + item.name : item.name));
                    });
                } else {
                    icon.textContent = "\uD83D\uDCC4";
                    const sizeEl = document.createElement("span");
                    sizeEl.textContent = formatSize(item.size || 0);
                    sizeEl.style.cssText = "color:#888;font-size:11px;flex-shrink:0;";
                    row.appendChild(icon);
                    row.appendChild(name);
                    row.appendChild(sizeEl);

                    if (mode === "file") {
                        row.addEventListener("click", () => {
                            const filePath = currentPath ? currentPath + "/" + item.name : item.name;
                            onSelect(filePath);
                            close();
                        });
                    }
                    listContainer.appendChild(row);
                    continue;
                }

                row.appendChild(icon);
                row.appendChild(name);
                listContainer.appendChild(row);
            }
        } catch (err) {
            clearChildren(listContainer);
            errorEl.textContent = err.message;
            errorEl.style.display = "block";
        }
    }

    upBtn.addEventListener("click", () => {
        if (currentPath) {
            const parent = currentPath.replace(/[\\/][^\\/]*$/, "") || "";
            navigate(parent);
        }
    });

    pathInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            navigate(pathInput.value.trim());
        }
    });

    navigate(startPath);
}

// --- Sequence pattern detection ---

function detectSequencePattern(filePath) {
    const dir = filePath.replace(/[\\/][^\\/]*$/, "");
    const filename = filePath.split(/[\\/]/).pop();
    // Find trailing digits before extension: render_0001.exr -> render_####.exr
    const match = filename.match(/^(.*?)(\d+)(\.[^.]+)$/);
    if (!match) return filePath;
    const prefix = match[1];
    const digits = match[2];
    const ext = match[3];
    const hashes = "#".repeat(digits.length);
    return dir + "/" + prefix + hashes + ext;
}

// --- Text helpers (adapted from VHS) ---

function pathStem(path) {
    const i = path.lastIndexOf("/");
    if (i >= 0) return [path.slice(0, i + 1), path.slice(i + 1)];
    const j = path.lastIndexOf("\\");
    if (j >= 0) return [path.slice(0, j + 1), path.slice(j + 1)];
    return ["", path];
}

function fitText(ctx, text, maxWidth) {
    if (maxWidth <= 0) return ["", 0];
    const full = ctx.measureText(text).width;
    if (full <= maxWidth) return [text, full];
    const cutoff = Math.max(0, (maxWidth / full * text.length | 0) - 2);
    const shortened = text.slice(0, cutoff) + "\u2026";
    return [shortened, ctx.measureText(shortened).width];
}

function fitPath(ctx, path, maxWidth) {
    const full = ctx.measureText(path).width;
    if (full <= maxWidth) return [path, full];
    const len = (maxWidth / full * path.length | 0) - 1;
    const filename = pathStem(path)[1];
    if (filename.length > len - 2) return [filename.substr(0, len), ctx.measureText(filename.substr(0, len)).width];
    const isAbs = path[0] === "/" || (path.length > 1 && path[1] === ":");
    const partial = path.substr(path.length - (isAbs ? len - 2 : len - 1));
    const cutoff = partial.indexOf("/");
    const backCutoff = cutoff < 0 ? partial.indexOf("\\") : cutoff;
    let displayPath;
    if (backCutoff < 0) {
        displayPath = path.substr(path.length - len);
    } else {
        displayPath = (isAbs ? "/\u2026" : "\u2026") + partial.substr(backCutoff);
    }
    return [displayPath, ctx.measureText(displayPath).width];
}

// --- Browse button injection (adapted from VHS VHSPATH pattern) ---

const BROWSE_TARGETS = [
    { nodeClass: "ImageLoader", widget: "image_path", extensions: "png,jpg,jpeg,tiff,tif,webp,bmp,exr", mode: "file" },
    { nodeClass: "LoadExr", widget: "image_path", extensions: "exr", mode: "file" },
    { nodeClass: "LoadExrSequence", widget: "sequence_path", extensions: "exr", mode: "file" },
    { nodeClass: "SaverNode", widget: "file_path", extensions: "", mode: "directory" },
];

const ICON_ZONE = 28;

function drawFolderIcon(ctx, cx, cy, size) {
    const s = size * 0.4;
    ctx.fillStyle = "#b0b0b0";
    ctx.beginPath();
    ctx.moveTo(cx - s, cy - s * 0.6);
    ctx.lineTo(cx - s * 0.3, cy - s * 0.6);
    ctx.lineTo(cx - s * 0.1, cy - s * 0.95);
    ctx.lineTo(cx - s, cy - s * 0.95);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.roundRect(cx - s, cy - s * 0.6, s * 2, s * 1.4, 1.5);
    ctx.fill();
}

// Custom draw: renders the widget background, label, path value, and folder icon
// Adapted from VHS VHSPATH draw + LiteGraph drawNodeWidgets default
function pathWidgetDraw(ctx, node, widget_width, y, H) {
    const show_text = app.canvas.ds.scale >= (app.canvas.low_quality_zoom_threshold ?? 0.5);
    const margin = 15;
    const text_color = LiteGraph.WIDGET_TEXT_COLOR;
    const secondary_text_color = LiteGraph.WIDGET_SECONDARY_TEXT_COLOR;

    // Background pill
    ctx.textAlign = "left";
    ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR;
    ctx.fillStyle = LiteGraph.WIDGET_BGCOLOR;
    ctx.beginPath();
    if (show_text)
        ctx.roundRect(margin, y, widget_width - margin * 2, H, [H * 0.5]);
    else
        ctx.rect(margin, y, widget_width - margin * 2, H);
    ctx.fill();

    if (!show_text) return;
    if (!this.disabled) ctx.stroke();

    ctx.save();
    ctx.beginPath();
    ctx.rect(margin, y, widget_width - margin * 2, H);
    ctx.clip();

    // Label on left
    let freeWidth = widget_width - (margin * 2 + ICON_ZONE + 20);
    ctx.fillStyle = secondary_text_color;
    const label = this.label || this.name;
    if (label != null) {
        const [labelDisplay, labelWidth] = fitText(ctx, label, freeWidth);
        freeWidth -= labelWidth;
        ctx.fillText(labelDisplay, margin * 2, y + H * 0.7);
    }

    // Path value on right (before icon zone)
    ctx.fillStyle = this.value ? text_color : "#777";
    ctx.textAlign = "right";
    const valueText = String(this.value || this.options?.placeholder || "");
    const [displayText] = fitPath(ctx, valueText, freeWidth);
    ctx.fillText(displayText, widget_width - margin - ICON_ZONE, y + H * 0.7);

    ctx.restore();

    // Folder icon on right edge
    ctx.save();
    const iconCx = widget_width - margin - ICON_ZONE / 2;
    const iconCy = y + H / 2;

    // Subtle separator line
    ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(widget_width - margin - ICON_ZONE, y + 3);
    ctx.lineTo(widget_width - margin - ICON_ZONE, y + H - 3);
    ctx.stroke();

    drawFolderIcon(ctx, iconCx, iconCy, H * 0.7);
    ctx.restore();
}

// Mouse handler: opens file browser on pointer-down only (VHS searchBox pattern)
// Returning truthy tells LiteGraph we handled this event — skip default prompt
function pathWidgetMouse(event, pos, node) {
    if (event.type !== "pointerdown") return true;
    if (this._browseOpen) return true;
    this._browseOpen = true;

    const widget = this;
    const config = this._browseConfig;
    const currentValue = this.value || "";
    let startPath = "";
    if (currentValue) {
        const dirPart = currentValue.replace(/[\\/][^\\/]*$/, "");
        if (dirPart && dirPart !== currentValue) startPath = dirPart;
        else startPath = currentValue;
    }

    openFileBrowser({
        startPath,
        extensions: config.extensions,
        title: config.mode === "directory" ? "Select Folder" : "Select File",
        mode: config.mode,
        onSelect: (selectedPath) => {
            widget.value = config.isSequence ? detectSequencePattern(selectedPath) : selectedPath;
            widget.callback?.(widget.value);
            app.graph.setDirtyCanvas(true);
        },
        onClose: () => {
            widget._browseOpen = false;
        },
    });
    return true;
}

function injectBrowseWidget(node, target) {
    const widgetIndex = node.widgets?.findIndex(w => w.name === target.widget);
    if (widgetIndex == null || widgetIndex < 0) return;
    const original = node.widgets[widgetIndex];
    if (original._hasBrowse) return;

    // Replace the original STRING widget with a fresh custom-typed widget.
    // Changing type on an existing "text" widget is not enough — LiteGraph
    // still treats it as text internally and opens the default "Value" prompt.
    // Creating a new widget object (like VHS VHSPATH) ensures it was never
    // type "text", so processNodeWidgets skips the prompt entirely.
    const replacement = {
        name: original.name,
        type: "COCO.PATH",
        value: original.value || "",
        options: original.options || {},
        callback: original.callback,
        y: original.y,
        last_y: original.last_y,
        _hasBrowse: true,
        _browseOpen: false,
        _browseConfig: {
            extensions: target.extensions,
            mode: target.mode,
            isSequence: target.nodeClass === "LoadExrSequence",
        },
        draw: pathWidgetDraw,
        mouse: pathWidgetMouse,
        computeSize(width) {
            return [width, LiteGraph.NODE_WIDGET_HEIGHT];
        },
    };
    node.widgets[widgetIndex] = replacement;
}

app.registerExtension({
    name: "CocoTools.FileBrowser",
    async nodeCreated(node) {
        const nodeClass = node.constructor.type || node.type;
        for (const target of BROWSE_TARGETS) {
            if (nodeClass === target.nodeClass) {
                injectBrowseWidget(node, target);
                break;
            }
        }
    },
});
