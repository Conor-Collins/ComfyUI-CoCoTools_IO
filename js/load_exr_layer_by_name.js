import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "LoadExrLayerByName",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        // Only handle the Load EXR Layer by Name nodes
        if (nodeData.name !== "LoadExrLayerByName" && nodeData.name !== "CryptomatteLayer") {
            return;
        }

        const isCryptomatte = nodeData.name === "CryptomatteLayer";
        console.log(`Registering ${isCryptomatte ? "Cryptomatte " : ""}Load EXR Layer by Name node`);
        
        // Store original methods to call them later
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        const onWidgetChange = nodeType.prototype.onWidgetChange;
        
        // Override onNodeCreated to set up node
        nodeType.prototype.onNodeCreated = function() {
            const result = onNodeCreated?.apply(this, arguments);
            
            // Initialize storage for layer information
            this.availableLayers = [];
            this.selectedLayer = "";
            this.connectedNodes = {}; // Track connected nodes
            
            console.log(`${isCryptomatte ? "Cryptomatte " : ""}Load EXR Layer by Name node created`);
            
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
                
                console.log(`Connection made to ${inputName} from node ${sourceNode.title || sourceNode.type}`);
                
                // Store connection in a structured way
                this.connectedNodes[inputName] = {
                    nodeId: sourceNodeId,
                    node: sourceNode,
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
                    console.log(`${isCryptomatte ? "Cryptomatte " : ""}Load EXR Layer by Name executed successfully`);
                    
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
            
            if (!connectionInfo || !connectionInfo.node) {
                return;
            }
            
            const sourceNode = connectionInfo.node;
            console.log(`Finding available layers from ${sourceNode.title || sourceNode.type}`);
            
            // Check if the source is a LoadExr node
            const isLoadExr = sourceNode.type.includes("LoadExr");
            
            // Try multiple approaches to get layer names
            let layerNames = [];
            
            // First try: Get output data if available
            if (connectionInfo.outputIndex !== undefined) {
                const outputData = sourceNode.getOutputData(connectionInfo.outputIndex);
                if (outputData && typeof outputData === 'object') {
                    layerNames = Object.keys(outputData);
                    if (layerNames.length > 0) {
                        console.log(`Found ${layerNames.length} layers in direct output data`);
                    }
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
                
                if (layerNames.length > 0) {
                    console.log(`Found ${layerNames.length} layers in source node layerInfo`);
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
                        
                        if (layerNames.length > 0) {
                            console.log(`Found ${layerNames.length} layers in metadata`);
                        }
                    } catch (error) {
                        console.error("Failed to parse metadata:", error);
                    }
                }
            }
            
            // Filter and update layers
            if (layerNames && layerNames.length > 0) {
                const filteredLayers = this.filterLayerNames(layerNames);
                console.log(`After filtering: ${filteredLayers.length} layers available`);
                
                // Store the available layers for tooltip/help
                this.availableLayers = [...filteredLayers];
                
                // Update the node tooltip and title
                this.updateNodeHelp();
            } else {
                console.warn("No layers found by any method");
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
        
        // Track when widgets change
        nodeType.prototype.onWidgetChange = function(name, value) {
            if (onWidgetChange) {
                onWidgetChange.apply(this, arguments);
            }
        };
        
        // Add a method to be called by other nodes (e.g., load_exr)
        // This allows direct communication between nodes
        nodeType.prototype.notifyLayersChanged = function(layerNames) {
            if (!layerNames || layerNames.length === 0) return;
            
            const filteredLayers = this.filterLayerNames(layerNames);
            this.availableLayers = [...filteredLayers];
            this.updateNodeHelp();
        };
    },
    
    // Setup global handler for all nodes
    async setup() {
        // Listen for graph execution
        app.addEventListener("graphExecuted", (e) => {
            try {
                // Get all matched nodes
                const matchedNodes = findNodes(isCryptomatte ? "CryptomatteLayer" : "LoadExrLayerByName");
                
                if (matchedNodes.length === 0) {
                    return; // No nodes to update
                }
                
                console.log(`Found ${matchedNodes.length} ${isCryptomatte ? "cryptomatte " : ""}layer nodes to update after execution`);
                
                // For each node, call updateLayerOptions
                for (const node of matchedNodes) {
                    if (node.updateLayerOptions) {
                        node.updateLayerOptions();
                    }
                }
            } catch (error) {
                console.error(`Error in ${isCryptomatte ? "cryptomatte " : ""}layer node graph execution handler:`, error);
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