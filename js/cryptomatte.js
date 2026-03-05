import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const PREVIEW_WIDTH = 400;
const PREVIEW_HEIGHT = 300;

app.registerExtension({
    name: "CocoTools.CryptomatteSelect",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "CryptomatteLayer") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            this._cryptoPreviewImg = null;
            this._cryptoImgWidth = 0;
            this._cryptoImgHeight = 0;

            // Container
            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px;";

            // Status bar
            const statusBar = document.createElement("div");
            statusBar.style.cssText = "width:100%;font:10px monospace;color:#888;display:flex;justify-content:space-between;padding:0 4px;";
            const coordSpan = document.createElement("span");
            coordSpan.textContent = "Click image to select object";
            const pixelSpan = document.createElement("span");
            pixelSpan.textContent = "";
            statusBar.appendChild(coordSpan);
            statusBar.appendChild(pixelSpan);
            container.appendChild(statusBar);

            // Canvas
            const canvas = document.createElement("canvas");
            canvas.width = PREVIEW_WIDTH;
            canvas.height = PREVIEW_HEIGHT;
            canvas.style.cssText = "width:100%;border-radius:3px;cursor:crosshair;background:#1a1a1a;";
            container.appendChild(canvas);

            this._cryptoCanvas = canvas;
            this._cryptoCoordSpan = coordSpan;
            this._cryptoPixelSpan = pixelSpan;

            // Compute draw rect for aspect-ratio-preserving image placement
            const computeDrawRect = () => {
                if (!this._cryptoImgWidth || !this._cryptoImgHeight) return null;
                const imgAspect = this._cryptoImgWidth / this._cryptoImgHeight;
                const canvasAspect = canvas.width / canvas.height;
                let drawX, drawY, drawW, drawH;
                if (imgAspect > canvasAspect) {
                    drawW = canvas.width;
                    drawH = canvas.width / imgAspect;
                    drawX = 0;
                    drawY = (canvas.height - drawH) / 2;
                } else {
                    drawH = canvas.height;
                    drawW = canvas.height * imgAspect;
                    drawX = (canvas.width - drawW) / 2;
                    drawY = 0;
                }
                return { drawX, drawY, drawW, drawH };
            };

            // Draw preview with optional crosshair
            const drawPreview = (crossCanvasX, crossCanvasY) => {
                const ctx = canvas.getContext("2d");
                ctx.fillStyle = "#1a1a1a";
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                if (!this._cryptoPreviewImg) {
                    ctx.fillStyle = "#888";
                    ctx.font = "12px monospace";
                    ctx.textAlign = "center";
                    ctx.fillText("Connect preview_image to enable click-to-matte", canvas.width / 2, canvas.height / 2);
                    return;
                }

                const rect = computeDrawRect();
                if (!rect) return;
                ctx.drawImage(this._cryptoPreviewImg, rect.drawX, rect.drawY, rect.drawW, rect.drawH);

                // Draw crosshair at click position
                if (crossCanvasX != null && crossCanvasY != null) {
                    ctx.save();
                    ctx.strokeStyle = "rgba(255, 220, 0, 0.85)";
                    ctx.lineWidth = 1;
                    ctx.setLineDash([4, 4]);

                    ctx.beginPath();
                    ctx.moveTo(rect.drawX, crossCanvasY);
                    ctx.lineTo(rect.drawX + rect.drawW, crossCanvasY);
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.moveTo(crossCanvasX, rect.drawY);
                    ctx.lineTo(crossCanvasX, rect.drawY + rect.drawH);
                    ctx.stroke();

                    ctx.setLineDash([]);
                    ctx.beginPath();
                    ctx.arc(crossCanvasX, crossCanvasY, 6, 0, Math.PI * 2);
                    ctx.strokeStyle = "rgba(255, 220, 0, 1)";
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    ctx.restore();
                }
            };

            this._drawCryptoPreview = drawPreview;

            // Click handler
            canvas.addEventListener("click", (e) => {
                if (!this._cryptoPreviewImg) return;

                const rect = computeDrawRect();
                if (!rect) return;

                const canvasBounds = canvas.getBoundingClientRect();
                const scaleX = canvas.width / canvasBounds.width;
                const scaleY = canvas.height / canvasBounds.height;

                const canvasX = (e.clientX - canvasBounds.left) * scaleX;
                const canvasY = (e.clientY - canvasBounds.top) * scaleY;

                // Check click is within drawn image area
                if (canvasX < rect.drawX || canvasX > rect.drawX + rect.drawW ||
                    canvasY < rect.drawY || canvasY > rect.drawY + rect.drawH) {
                    return;
                }

                // Map to pixel coordinates
                const pixelX = Math.floor(((canvasX - rect.drawX) / rect.drawW) * this._cryptoImgWidth);
                const pixelY = Math.floor(((canvasY - rect.drawY) / rect.drawH) * this._cryptoImgHeight);
                const x = Math.max(0, Math.min(pixelX, this._cryptoImgWidth - 1));
                const y = Math.max(0, Math.min(pixelY, this._cryptoImgHeight - 1));

                // Update widgets
                const xWidget = this.widgets?.find((w) => w.name === "x_coord");
                const yWidget = this.widgets?.find((w) => w.name === "y_coord");
                if (xWidget) xWidget.value = x;
                if (yWidget) yWidget.value = y;

                drawPreview(canvasX, canvasY);
                this._cryptoCoordSpan.textContent = `Selected: (${x}, ${y})`;

                app.queuePrompt(0);
            });

            // Mouse move for hover coordinate display
            canvas.addEventListener("mousemove", (e) => {
                if (!this._cryptoPreviewImg) return;

                const rect = computeDrawRect();
                if (!rect) return;

                const canvasBounds = canvas.getBoundingClientRect();
                const scaleX = canvas.width / canvasBounds.width;
                const scaleY = canvas.height / canvasBounds.height;

                const canvasX = (e.clientX - canvasBounds.left) * scaleX;
                const canvasY = (e.clientY - canvasBounds.top) * scaleY;

                if (canvasX >= rect.drawX && canvasX <= rect.drawX + rect.drawW &&
                    canvasY >= rect.drawY && canvasY <= rect.drawY + rect.drawH) {
                    const px = Math.floor(((canvasX - rect.drawX) / rect.drawW) * this._cryptoImgWidth);
                    const py = Math.floor(((canvasY - rect.drawY) / rect.drawH) * this._cryptoImgHeight);
                    this._cryptoPixelSpan.textContent = `(${px}, ${py})`;
                } else {
                    this._cryptoPixelSpan.textContent = "";
                }
            });

            canvas.addEventListener("mouseleave", () => {
                this._cryptoPixelSpan.textContent = "";
            });

            // Add as ComfyUI widget
            const widget = this.addDOMWidget("crypto_preview", "custom", container, {
                serialize: false,
                getMinHeight: () => PREVIEW_HEIGHT + 30,
            });
            widget.computeSize = () => [PREVIEW_WIDTH, PREVIEW_HEIGHT + 30];

            drawPreview();
            return result;
        };

        nodeType.prototype.onExecuted = function (message) {
            if (onExecuted) onExecuted.apply(this, arguments);
            if (!message) return;

            // Load preview image from UI data
            if (message.preview_image && message.preview_image.length > 0) {
                const preview = message.preview_image[0];
                const img = new Image();
                img.onload = () => {
                    this._cryptoPreviewImg = img;
                    this._cryptoImgWidth = message.image_width?.[0] || img.width;
                    this._cryptoImgHeight = message.image_height?.[0] || img.height;

                    // Redraw with crosshair if we have active coordinates
                    const xWidget = this.widgets?.find((w) => w.name === "x_coord");
                    const yWidget = this.widgets?.find((w) => w.name === "y_coord");

                    if (xWidget && yWidget && xWidget.value >= 0 && yWidget.value >= 0) {
                        const canvas = this._cryptoCanvas;
                        const imgAspect = this._cryptoImgWidth / this._cryptoImgHeight;
                        const canvasAspect = canvas.width / canvas.height;
                        let drawX, drawY, drawW, drawH;
                        if (imgAspect > canvasAspect) {
                            drawW = canvas.width;
                            drawH = canvas.width / imgAspect;
                            drawX = 0;
                            drawY = (canvas.height - drawH) / 2;
                        } else {
                            drawH = canvas.height;
                            drawW = canvas.height * imgAspect;
                            drawX = (canvas.width - drawW) / 2;
                            drawY = 0;
                        }
                        const crossX = drawX + (xWidget.value / this._cryptoImgWidth) * drawW;
                        const crossY = drawY + (yWidget.value / this._cryptoImgHeight) * drawH;
                        this._drawCryptoPreview(crossX, crossY);
                    } else {
                        this._drawCryptoPreview();
                    }

                    // Update status with pixel count
                    if (message.selected_pixels && message.selected_pixels.length > 0) {
                        const pixels = message.selected_pixels[0];
                        if (pixels > 0) {
                            this._cryptoCoordSpan.textContent =
                                `Selected: (${xWidget?.value ?? "?"}, ${yWidget?.value ?? "?"}) - ${pixels} pixels`;
                        }
                    }
                };
                const url = api.apiURL(
                    `/view?filename=${encodeURIComponent(preview.filename)}&type=${preview.type}&subfolder=${encodeURIComponent(preview.subfolder || "")}`
                );
                img.src = url;
            }
        };
    },
});
