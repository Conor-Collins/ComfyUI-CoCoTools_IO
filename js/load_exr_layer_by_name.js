import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "LoadExrLayerByName",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // Only handle the Load EXR Layer by Name nodes
        if (nodeData.name !== "LoadExrLayerByName" && nodeData.name !== "CryptomatteLayer") {
            return;
        }

        const isCryptomatte = nodeData.name === "CryptomatteLayer";

        // Store original methods to call them later
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        
        // Override onNodeCreated to set up node
        nodeType.prototype.onNodeCreated = function() {
            const result = onNodeCreated?.apply(this, arguments);

            // Initialize storage for layer information
            this.availableLayers = [];
            this.selectedLayer = "";
            this.connectedNodes = {}; // Track connected nodes

            // Set up click-to-matte interaction for CryptomatteLayer nodes
            if (isCryptomatte) {
                this._setupClickToMatte();
            }

            return result;
        };
        
        // Handle connections to monitor layer sources
        nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
            if (onConnectionsChange) {
                onConnectionsChange.apply(this, arguments);
            }
            
            // Only care about input connections
            if (type !== LiteGraph.INPUT || !link_info) {
                return;
            }
            
            // Check if it's connecting or disconnecting
            if (connected) {
                // Store the connected node info
                const inputName = this.inputs[index].name;
                const sourceNodeId = link_info.origin_id;
                const sourceNode = app.graph.getNodeById(sourceNodeId);
                
                if (!sourceNode) return;

                // Store only the node ID to avoid stale references
                this.connectedNodes[inputName] = {
                    nodeId: sourceNodeId,
                    outputIndex: link_info.origin_slot
                };
                
                // If this is the layers/cryptomatte input, try to get layer info immediately
                if (index === 0 && inputName.toLowerCase() === (isCryptomatte ? "cryptomatte" : "layers")) {
                    this.updateLayerOptions();
                }
            } else {
                // Remove connection info
                const inputName = this.inputs[index].name;
                delete this.connectedNodes[inputName];
                
                // If the main input was disconnected, reset layers
                if (index === 0) {
                    this.resetLayerOptions();
                }
            }
        };
        
        // Handler for when node is executed with fresh data
        nodeType.prototype.onExecuted = function(message) {
            // Call original method if it exists
            if (onExecuted) {
                onExecuted.apply(this, arguments);
            }
            
            try {
                // Check if the node execution was successful
                if (message && message.status === "executed") {
                    // Update layer options based on connected nodes
                    // This ensures the node has the most up-to-date layer information
                    this.updateLayerOptions();
                    
                    // Update node help after execution
                    this.updateNodeHelp();
                }
                
            } catch (error) {
                console.error("Error in Load EXR Layer by Name onExecuted:", error);
            }
        };
        
        // Update layer options based on connected nodes
        nodeType.prototype.updateLayerOptions = function() {
            const inputName = isCryptomatte ? "cryptomatte" : "layers";
            const connectionInfo = this.connectedNodes[inputName];

            if (!connectionInfo || !connectionInfo.nodeId) {
                return;
            }

            const sourceNode = app.graph.getNodeById(connectionInfo.nodeId);
            if (!sourceNode) {
                return;
            }
            
            // Check if the source is a LoadExr node
            const isLoadExr = sourceNode.type.includes("LoadExr");
            
            // Try multiple approaches to get layer names
            let layerNames = [];
            
            // First try: Get output data if available
            if (connectionInfo.outputIndex !== undefined) {
                const outputData = sourceNode.getOutputData(connectionInfo.outputIndex);
                if (outputData && typeof outputData === 'object') {
                    layerNames = Object.keys(outputData);
                }
            }
            
            // Second try: Get data from source node properties
            if (layerNames.length === 0 && sourceNode.layerInfo) {
                if (isCryptomatte && sourceNode.layerInfo.cryptomatte) {
                    layerNames = Object.keys(sourceNode.layerInfo.cryptomatte);
                } else if (!isCryptomatte && sourceNode.layerInfo.layers) {
                    layerNames = Object.keys(sourceNode.layerInfo.layers);
                } else if (sourceNode.layerInfo.types) {
                    layerNames = Object.keys(sourceNode.layerInfo.types);
                }
            }
            
            // Third try: Extract from metadata
            if (layerNames.length === 0 && sourceNode.widgets) {
                const metadataWidget = sourceNode.widgets.find(w => w.name === "metadata");
                if (metadataWidget && metadataWidget.value) {
                    try {
                        const metadata = JSON.parse(metadataWidget.value);
                        if (metadata.layers) {
                            layerNames = metadata.layers;
                        } else if (metadata.layer_types) {
                            layerNames = Object.keys(metadata.layer_types);
                        }
                        
                    } catch (error) {
                        // Metadata parsing failed, continue with other methods
                    }
                }
            }
            
            // Filter and update layers
            if (layerNames && layerNames.length > 0) {
                const filteredLayers = this.filterLayerNames(layerNames);

                // Store the available layers for tooltip/help
                this.availableLayers = [...filteredLayers];
                
                // Update the node tooltip and title
                this.updateNodeHelp();
            } else {
                this.availableLayers = ["none"];
                this.updateNodeHelp();
            }
        };
        
        // Filter layer names based on the node type
        nodeType.prototype.filterLayerNames = function(layerNames) {
            if (!layerNames || layerNames.length === 0) {
                return ["none"];
            }
            
            // For regular Load EXR Layer by Name, exclude system and crypto layers
            if (!isCryptomatte) {
                return layerNames.filter(name => 
                    name !== "rgb" && 
                    name !== "alpha" && 
                    !name.toLowerCase().includes("cryptomatte") && 
                    !name.toLowerCase().startsWith("crypto"));
            } 
            // For Cryptomatte Load EXR Layer by Name, include only crypto layers
            else {
                return layerNames.filter(name => 
                    name.toLowerCase().includes("cryptomatte") || 
                    name.toLowerCase().startsWith("crypto"));
            }
        };
        
        // Reset to default layers
        nodeType.prototype.resetLayerOptions = function() {
            this.availableLayers = ["none"];
            this.updateNodeHelp();
        };
        
        // Update the node tooltip and title
        nodeType.prototype.updateNodeHelp = function() {
            const layerList = this.availableLayers.join(", ");
            this.title = `${isCryptomatte ? "Cryptomatte " : ""}Load EXR Layer by Name`;
            this.help = `Available layers: ${layerList}`;
        };
        
        // Add a method to be called by other nodes (e.g., load_exr)
        // This allows direct communication between nodes
        nodeType.prototype.notifyLayersChanged = function(layerNames) {
            if (!layerNames || layerNames.length === 0) return;

            const filteredLayers = this.filterLayerNames(layerNames);
            this.availableLayers = [...filteredLayers];
            this.updateNodeHelp();
        };

        // Set up click-to-matte interaction on the node preview image area
        nodeType.prototype._setupClickToMatte = function() {
            const node = this;

            // Store the original onMouseDown to chain calls
            const origOnMouseDown = node.onMouseDown;

            node.onMouseDown = function(event, localPos, graphCanvas) {
                // Call the original handler first if it exists
                if (origOnMouseDown) {
                    const origResult = origOnMouseDown.call(this, event, localPos, graphCanvas);
                    if (origResult === true) {
                        return true;
                    }
                }

                // Only process left clicks
                if (event.button !== 0) {
                    return false;
                }

                // Find the preview image area on this node
                const imageWidget = this.imgs;
                if (!imageWidget || imageWidget.length === 0) {
                    return false;
                }

                // The preview image is rendered below widgets. Calculate the image
                // display area from the node's internal image render region.
                const img = imageWidget[0];
                if (!img || !img.naturalWidth || !img.naturalHeight) {
                    return false;
                }

                // Determine the image display area within the node
                // ComfyUI renders node images in the area below widgets
                const widgetHeight = this.computeSize()[1] - this.size[1] + LiteGraph.NODE_WIDGET_HEIGHT;
                const nodeWidth = this.size[0];
                const nodeHeight = this.size[1];

                // The image area starts after the title and widgets
                const titleHeight = LiteGraph.NODE_TITLE_HEIGHT || 30;
                let widgetsHeight = 0;
                if (this.widgets) {
                    for (const w of this.widgets) {
                        if (w.computeSize) {
                            widgetsHeight += w.computeSize()[1] + 4;
                        } else {
                            widgetsHeight += LiteGraph.NODE_WIDGET_HEIGHT + 4;
                        }
                    }
                }

                // Image display area bounds (relative to node origin)
                const imgAreaTop = titleHeight + widgetsHeight;
                const imgAreaLeft = 0;
                const imgAreaWidth = nodeWidth;
                const imgAreaHeight = nodeHeight - imgAreaTop;

                // Check if the click is within the image area
                const clickX = localPos[0];
                const clickY = localPos[1];

                if (clickX < imgAreaLeft || clickX > imgAreaLeft + imgAreaWidth ||
                    clickY < imgAreaTop || clickY > imgAreaTop + imgAreaHeight) {
                    return false;
                }

                // Calculate aspect-ratio-preserving image fit within the display area
                const imgNatWidth = img.naturalWidth;
                const imgNatHeight = img.naturalHeight;
                const scaleX = imgAreaWidth / imgNatWidth;
                const scaleY = imgAreaHeight / imgNatHeight;
                const scale = Math.min(scaleX, scaleY);

                const renderedWidth = imgNatWidth * scale;
                const renderedHeight = imgNatHeight * scale;

                // The image is centered in the display area
                const imgOffsetX = imgAreaLeft + (imgAreaWidth - renderedWidth) / 2;
                const imgOffsetY = imgAreaTop + (imgAreaHeight - renderedHeight) / 2;

                // Check if click falls within the rendered image bounds
                const relX = clickX - imgOffsetX;
                const relY = clickY - imgOffsetY;

                if (relX < 0 || relX >= renderedWidth || relY < 0 || relY >= renderedHeight) {
                    return false;
                }

                // Map click position to pixel coordinates in the original image
                const pixelX = Math.floor((relX / renderedWidth) * imgNatWidth);
                const pixelY = Math.floor((relY / renderedHeight) * imgNatHeight);

                // Clamp to valid range
                const finalX = Math.min(Math.max(pixelX, 0), imgNatWidth - 1);
                const finalY = Math.min(Math.max(pixelY, 0), imgNatHeight - 1);

                // Update the x_coord and y_coord widgets
                const xWidget = this.widgets?.find(w => w.name === "x_coord");
                const yWidget = this.widgets?.find(w => w.name === "y_coord");

                if (xWidget && yWidget) {
                    xWidget.value = finalX;
                    yWidget.value = finalY;

                    // Mark the node as needing re-execution
                    if (this.graph) {
                        this.graph.change();
                    }
                    this.setDirtyCanvas(true, true);
                    console.log("CryptomatteLayer click-to-matte: pixel (" + finalX + ", " + finalY + ")");
                    return true;
                }

                return false;
            };
        };
    },
    
    // Setup global handler for all nodes
    async setup() {
        // Listen for graph execution
        app.addEventListener("graphExecuted", (e) => {
            try {
                // Find both node types independently
                const layerNodes = findNodes("LoadExrLayerByName");
                const cryptoNodes = findNodes("CryptomatteLayer");
                const allNodes = [...layerNodes, ...cryptoNodes];

                if (allNodes.length === 0) {
                    return; // No nodes to update
                }

                // For each node, call updateLayerOptions
                for (const node of allNodes) {
                    if (node.updateLayerOptions) {
                        node.updateLayerOptions();
                    }
                }
            } catch (error) {
                console.error("Error in layer node graph execution handler:", error);
            }
        });

        function findNodes(type) {
            if (!app.graph || !app.graph._nodes) {
                return [];
            }

            return app.graph._nodes.filter(node => node.type === type);
        }
    }
});