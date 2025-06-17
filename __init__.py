
# Import all available modules
from .modules.image_loader import coco_loader
from .modules.load_exr import load_exr
from .modules.saver import saver
from .modules.load_exr_layer_by_name import load_exr_layer_by_name, shamble_cryptomatte
from .modules.colorspace import colorspace
from .modules.znormalize import znormalize

# Initialize node mappings
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Explicitly set the web directory path relative to this file
import os
NODE_DIR = os.path.dirname(os.path.realpath(__file__))
WEB_DIRECTORY = os.path.join(NODE_DIR, "js")

# Add all available node classes
NODE_CLASS_MAPPINGS.update({
    "ImageLoader": coco_loader,
    "LoadExr": load_exr,  
    "SaverNode": saver,
    "LoadExrLayerByName": load_exr_layer_by_name,
    "CryptomatteLayer": shamble_cryptomatte,
    "ColorspaceNode": colorspace,
    "ZNormalizeNode": znormalize
})

# Add display names for better UI presentation
NODE_DISPLAY_NAME_MAPPINGS.update({
    "ImageLoader": "coco Loader",
    "LoadExr": "coco Load EXR", 
    "SaverNode": "coco Saver",
    "LoadExrLayerByName": "Load EXR Layer by Name",
    "CryptomatteLayer": "Cryptomatte Layer",
    "ColorspaceNode": "Colorspace",
    "ZNormalizeNode": "Z Normalize"
})

# Expose what ComfyUI needs
__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
