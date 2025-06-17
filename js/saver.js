import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "Coco.Saver",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // CRITICAL: Must match NODE_CLASS_MAPPINGS key
        if (nodeData.name !== "SaverNode") {
            return;
        }

        console.log("Registering dynamic widget behavior for saver node");
        
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function() {
            const me = onNodeCreated?.apply(this);
            
            // Format specifications matching Python
            const FORMAT_SPECS = {
                "exr": {
                    depths: ["16", "32"],  // EXR only supports half and full float
                    showWidgets: ["exr_compression", "bit_depth", "save_as_grayscale"]
                },
                "png": {
                    depths: ["8", "16"],  // PNG only supports integer formats
                    showWidgets: ["bit_depth", "save_as_grayscale"]
                },
                "jpg": {
                    depths: ["8"],
                    showWidgets: ["quality"]
                },
                "webp": {
                    depths: ["8"],
                    showWidgets: ["quality"]
                },
                "tiff": {
                    depths: ["8", "16", "32"],
                    showWidgets: ["bit_depth", "save_as_grayscale"]
                }
            };
            
            // Get all widgets
            const widgets = {
                fileType: this.widgets.find(w => w.name === "file_type"),
                bitDepth: this.widgets.find(w => w.name === "bit_depth"),
                exrCompression: this.widgets.find(w => w.name === "exr_compression"),
                quality: this.widgets.find(w => w.name === "quality"),
                saveAsGrayscale: this.widgets.find(w => w.name === "save_as_grayscale")
            };

            if (!widgets.fileType) {
                console.warn("Saver: file_type widget not found");
                return me;
            }

            // Store original bit depth options
            const allBitDepthOptions = ["8", "16", "32"];
            
            // Update bit depth options based on format
            const updateBitDepthOptions = (format) => {
                if (!widgets.bitDepth) return;
                
                const spec = FORMAT_SPECS[format];
                if (spec && spec.depths) {
                    // Update widget options
                    widgets.bitDepth.options.values = spec.depths;
                    
                    // If current value is not valid, reset to first valid option
                    if (!spec.depths.includes(widgets.bitDepth.value)) {
                        widgets.bitDepth.value = spec.depths[0];
                        
                        // Visual feedback - briefly highlight the change
                        const originalColor = widgets.bitDepth.color;
                        widgets.bitDepth.color = "#ff6b6b";
                        setTimeout(() => {
                            widgets.bitDepth.color = originalColor;
                            app.canvas.setDirty(true);
                        }, 300);
                    }
                }
            };

            // Update widget visibility and options
            const updateWidgets = () => {
                const format = widgets.fileType.value;
                const spec = FORMAT_SPECS[format];
                
                console.log(`Saver: Updating for format: ${format}`);
                
                // Hide all optional widgets
                Object.keys(widgets).forEach(key => {
                    if (key !== "fileType" && widgets[key]) {
                        widgets[key].hidden = true;
                    }
                });
                
                // Show relevant widgets
                if (spec && spec.showWidgets) {
                    spec.showWidgets.forEach(widgetName => {
                        const camelCaseName = widgetName.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
                        if (widgets[camelCaseName]) {
                            widgets[camelCaseName].hidden = false;
                        }
                    });
                }
                
                // Update bit depth options
                updateBitDepthOptions(format);
                
                // Resize node
                requestAnimationFrame(() => {
                    const newHeight = this.computeSize([this.size[0], this.size[1]])[1];
                    this.setSize([this.size[0], newHeight]);
                    app.canvas.setDirty(true);
                });
            };

            // Override file type callback
            const originalFileTypeCallback = widgets.fileType.callback;
            widgets.fileType.callback = function(...args) {
                if (originalFileTypeCallback) {
                    originalFileTypeCallback.apply(this, args);
                }
                updateWidgets();
            };

            // Override bit depth callback for validation
            if (widgets.bitDepth) {
                const originalBitDepthCallback = widgets.bitDepth.callback;
                widgets.bitDepth.callback = function(value) {
                    // Validate bit depth for current format
                    const currentFormat = widgets.fileType.value;
                    const spec = FORMAT_SPECS[currentFormat];
                    
                    if (spec && !spec.depths.includes(value)) {
                        console.warn(`Invalid bit depth ${value} for format ${currentFormat}`);
                        // Reset to first valid option
                        this.value = spec.depths[0];
                        app.canvas.setDirty(true);
                        return;
                    }
                    
                    if (originalBitDepthCallback) {
                        originalBitDepthCallback.apply(this, arguments);
                    }
                };
            }

            // Initial setup with delay
            setTimeout(updateWidgets, 10);

            return me;
        };
    }
});
