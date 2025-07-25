
# Import all available modules
from .modules.image_loader import ImageLoader
from .modules.load_exr import LoadExr
from .modules.load_exr_sequence import LoadExrSequence
from .modules.saver import SaverNode
from .modules.load_exr_layer_by_name import LoadExrLayerByName, CryptomatteLayer
from .modules.colorspace import ColorspaceNode
from .modules.znormalize import ZNormalizeNode

# Initialize node mappings
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Explicitly set the web directory path relative to this file
import os
NODE_DIR = os.path.dirname(os.path.realpath(__file__))
WEB_DIRECTORY = os.path.join(NODE_DIR, "js")

# Add all available node classes
NODE_CLASS_MAPPINGS.update({
    "ImageLoader": ImageLoader,
    "LoadExr": LoadExr,
    "LoadExrSequence": LoadExrSequence,  
    "SaverNode": SaverNode,
    "LoadExrLayerByName": LoadExrLayerByName,
    "CryptomatteLayer": CryptomatteLayer,
    "ColorspaceNode": ColorspaceNode,
    "ZNormalizeNode": ZNormalizeNode
})

# Add display names for better UI presentation
NODE_DISPLAY_NAME_MAPPINGS.update({
    "ImageLoader": "CoCo Loader",
    "LoadExr": "CoCo Load EXR",
    "LoadExrSequence": "CoCo Load EXR Sequence", 
    "SaverNode": "CoCo Saver",
    "LoadExrLayerByName": "CoCo Load EXR Layer by Name",
    "CryptomatteLayer": "CoCo Cryptomatte Layer",
    "ColorspaceNode": "CoCo Colorspace",
    "ZNormalizeNode": "CoCo Z Normalize"
})

# Expose what ComfyUI needs
__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
