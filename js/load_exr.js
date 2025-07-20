import { app } from "../../../scripts/app.js";

function chainCallback(object, property, callback) {
    if (object == undefined) {
        console.error("Tried to add callback to non-existant object");
        return;
    }
    if (property in object && object[property]) {
        const callback_orig = object[property];
        object[property] = function () {
            const r = callback_orig.apply(this, arguments);
            return callback.apply(this, arguments) ?? r;
        };
    } else {
        object[property] = callback;
    }
}

function fitHeight(node) {
    requestAnimationFrame(() => {
        const size = node.computeSize();
        node.setSize([node.size[0], size[1]]);
        app.canvas.setDirty(true);
    });
}

function addSequenceWidgets(nodeType, nodeData) {
    chainCallback(nodeType.prototype, "onNodeCreated", function() {
        var typeWidget = null;
        var typeWidgetIndex = -1;
        for(let i = 0; i < this.widgets.length; i++) {
            if (this.widgets[i].name === "image_type"){
                typeWidget = this.widgets[i];
                typeWidgetIndex = i+1;
                break;
            }
        }
        let sequenceWidgetsCount = 0;
        chainCallback(typeWidget, "callback", (value) => {
            const formats = (LiteGraph.registered_node_types[this.type]
                ?.nodeData?.input?.required?.image_type?.[1]?.formats);
            let newWidgets = [];
            if (formats?.[value]) {
                let sequenceWidgets = formats[value];
                for (let wDef of sequenceWidgets) {
                    let type = wDef[1];
                    if (Array.isArray(type)) {
                        type = "COMBO";
                    }
                    app.widgets[type](this, wDef[0], wDef.slice(1), app);
                    let w = this.widgets.pop();
                    if (['INT', 'FLOAT'].includes(type)) {
                        if (wDef.length > 2 && wDef[2]) {
                            Object.assign(w.options, wDef[2]);
                        }
                    }
                    w.config = wDef.slice(1);
                    newWidgets.push(w);
                }
            }
            let removed = this.widgets.splice(typeWidgetIndex,
                                            sequenceWidgetsCount, ...newWidgets);
            for (let w of removed) {
                w?.onRemove?.();
            }
            fitHeight(this);
            sequenceWidgetsCount = newWidgets.length;
        });
    });
}

app.registerExtension({
    name: "CocoTools.LoadExr",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "LoadExr") {
            return;
        }
        
        addSequenceWidgets(nodeType, nodeData);
    }
});