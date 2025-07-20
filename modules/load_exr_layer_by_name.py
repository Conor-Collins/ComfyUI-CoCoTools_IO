import torch
import logging
from typing import Dict, List, Union, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import debug utilities
try:
    from ..utils.debug_utils import debug_log, format_layer_names, format_tensor_info, DEBUG_MODE
except ImportError:
    # Fallback if utils not available
    def debug_log(logger, level, simple_msg, verbose_msg=None, **kwargs):
        getattr(logger, level.lower())(simple_msg)
    def format_layer_names(layer_names, max_simple=None):
        return ', '.join(layer_names)
    def format_tensor_info(tensor_shape, tensor_dtype, name=""):
        return f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}"
    DEBUG_MODE = "simple"

class load_exr_layer_by_name:
    """
    The Load EXR Layer by Name node allows selecting a specific layer from an EXR layer dictionary.
    It works like Nuke's Shuffle node, allowing users to pick a specific layer to output.
    """
    
    # Class variables to store available layer names
    available_layers = ["none"]
    
    def __init__(self):
        debug_log(logger, "info", "Layer selector initialized", "load_exr_layer_by_name class initialized")

    @classmethod
    def INPUT_TYPES(cls):
        debug_log(logger, "info", f"Available layers: {len(cls.available_layers)}", 
                 f"INPUT_TYPES called - available layers: {cls.available_layers}")
        return {
            "required": {
                "layers": ("LAYERS",),
                "layer_name": ("STRING", {
                    "default": "none",
                    "multiline": False,
                    "description": "Name of the layer to extract from the EXR. You can find layer names in the metadata output of the Load EXR node."
                })
            },
            "optional": {
                "conversion": (["Auto", "To RGB", "To Mask"], {
                    "default": "Auto"
                })
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "process_layer"
    CATEGORY = "Image/EXR"
    
    def process_layer(self, layers: Dict[str, torch.Tensor], layer_name: str, 
                     conversion: str = "Auto") -> List[Union[torch.Tensor, None]]:
        """
        Extract a specific layer from the layers dictionary.
        
        Args:
            layers: Dictionary of layer names to tensors
            layer_name: Name of the layer to extract
            conversion: How to convert the layer (Auto, To RGB, To Mask)
            
        Returns:
            List containing [image, mask] tensors
        """
        # Check if we have any layers at all
        if not layers or len(layers) == 0:
            debug_log(logger, "warning", "No layers available", "No layers available in the input")
            return [torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1))]
            
        # Log the available layers for debugging
        debug_log(logger, "info", f"Found {len(layers)} layers: {format_layer_names(list(layers.keys()))}", 
                 f"Available layers: {list(layers.keys())}")
        if DEBUG_MODE == "verbose":
            for layer_key, layer_tensor in layers.items():
                debug_log(logger, "info", "", f"Layer '{layer_key}' has shape {layer_tensor.shape} and type {layer_tensor.dtype}")
        
        # Update the class variable with available layer names
        self.__class__.available_layers = ["none"] + sorted(list(layers.keys()))
        
        # If the layer doesn't exist, try to find a close match
        if layer_name not in layers and layer_name != "none":
            # Try to find an exact match ignoring case
            case_insensitive_matches = [l for l in layers.keys() if l.lower() == layer_name.lower()]
            if case_insensitive_matches:
                layer_name = case_insensitive_matches[0]
                debug_log(logger, "info", "Found layer with different case", 
                         f"Layer name '{layer_name}' found with different case: '{layer_name}'")
            else:
                # Try to find a partial match
                matches = [l for l in layers.keys() if layer_name.lower() in l.lower()]
                if matches:
                    # Sort matches by length to find the closest match
                    matches.sort(key=len)
                    layer_name = matches[0]
                    debug_log(logger, "info", "Using closest layer match", 
                             f"Layer name '{layer_name}' not found exactly, using closest match: '{layer_name}'")
                else:
                    # Try to match hierarchical names (e.g., "CITY SCENE.AO" when user enters "AO")
                    hierarchical_matches = []
                    for l in layers.keys():
                        if '.' in l:
                            parts = l.split('.')
                            # Check if any part matches the layer name
                            if any(part.lower() == layer_name.lower() for part in parts):
                                hierarchical_matches.append(l)
                    
                    if hierarchical_matches:
                        layer_name = hierarchical_matches[0]
                        debug_log(logger, "info", "Found hierarchical match", 
                                 f"Found hierarchical layer match: '{layer_name}'")
                    else:
                        # Try to match subimage names (e.g., "AO" for a subimage)
                        subimage_matches = [l for l in layers.keys() if l.split('.')[0].lower() == layer_name.lower()]
                        if subimage_matches:
                            layer_name = subimage_matches[0]
                            debug_log(logger, "info", "Found subimage match", 
                                     f"Found subimage match: '{layer_name}'")
                        else:
                            debug_log(logger, "warning", "Layer not found", 
                                     f"Layer '{layer_name}' not found and no close matches")
                            # Use the first available layer as fallback
                            if len(layers) > 0:
                                layer_name = list(layers.keys())[0]
                                debug_log(logger, "info", "Using first available layer", 
                                         f"Using first available layer: {layer_name}")
                            else:
                                return [torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1))]
        
        # If no layer is specified or "none" is selected, return empty tensors
        if not layer_name or layer_name == "none":
            debug_log(logger, "warning", "No layer specified", "No layer specified, returning empty tensors")
            return [torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1))]
        
        # Get the requested layer
        layer_tensor = layers[layer_name]
        
        # Log the layer processing
        debug_log(logger, "info", f"Processing layer '{layer_name}'", 
                 f"Processing layer '{layer_name}' with shape {layer_tensor.shape} and type {layer_tensor.dtype}")
        
        # Debug: Print the requested layer name
        debug_log(logger, "info", "", f"Requested layer: '{layer_name}'")
        
        # Special handling for alpha layers only (not depth or Z)
        is_alpha_layer = 'alpha' in layer_name.lower()
        
        # Check tensor shape to determine its type
        if len(layer_tensor.shape) == 4 and layer_tensor.shape[3] == 3:
            # It's an RGB tensor [1, H, W, 3]
            if conversion == "To Mask" or (conversion == "Auto" and is_alpha_layer):
                # Convert RGB to mask by taking the mean across channels
                mask_output = layer_tensor.mean(dim=3, keepdim=False)
                image_output = None
                debug_log(logger, "info", "Converted to mask", f"Converted RGB tensor to mask: shape={mask_output.shape}")
            else:
                # Keep as an image
                image_output = layer_tensor
                mask_output = None
                debug_log(logger, "info", "Using as RGB image", f"Using RGB tensor as image: shape={image_output.shape}")
        elif len(layer_tensor.shape) == 3:
            # It's a single-channel tensor [1, H, W]
            # Special handling for depth and Z channels
            is_depth_or_z = 'depth' in layer_name.lower() or layer_name.lower() == 'z'
            
            if conversion == "To RGB":
                # Convert to RGB by replicating to 3 channels
                image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                mask_output = None
                debug_log(logger, "info", "Converted to RGB", f"Converted single-channel tensor to RGB: shape={image_output.shape}")
            elif is_depth_or_z:
                # For depth and Z channels, return as image by default
                image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                mask_output = None
                debug_log(logger, "info", "Converted depth to RGB", f"Converted depth/Z tensor to RGB: shape={image_output.shape}")
            elif 'alpha' in layer_name.lower():
                # For alpha channels, return as mask
                mask_output = layer_tensor
                image_output = None
                debug_log(logger, "info", "Using alpha as mask", f"Using alpha tensor as mask: shape={mask_output.shape}")
            else:
                # For other single-channel data, use the conversion setting
                if conversion == "To Mask":
                    mask_output = layer_tensor
                    image_output = None
                    debug_log(logger, "info", "Using as mask", f"Using single-channel tensor as mask: shape={mask_output.shape}")
                else:
                    # Default to RGB for Auto mode for non-alpha channels
                    image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                    mask_output = None
                    debug_log(logger, "info", "Using as RGB (Auto)", f"Using single-channel tensor as RGB (Auto): shape={image_output.shape}")
        # Special case for empty tensors or tensors with shape [1, 1, 1, 3]
        elif len(layer_tensor.shape) == 4 and layer_tensor.shape[1] == 1 and layer_tensor.shape[2] == 1:
            # This is likely an empty tensor or a placeholder
            # Check if it's an alpha or depth layer
            if 'alpha' in layer_name.lower() or 'depth' in layer_name.lower():
                # Create a proper mask tensor
                # Get dimensions from another layer if possible
                height, width = 720, 1280  # Default size
                for other_name, other_tensor in layers.items():
                    if other_name != layer_name and len(other_tensor.shape) >= 3:
                        if len(other_tensor.shape) == 4:  # RGB tensor [1, H, W, 3]
                            height, width = other_tensor.shape[1], other_tensor.shape[2]
                        elif len(other_tensor.shape) == 3:  # Mask tensor [1, H, W]
                            height, width = other_tensor.shape[1], other_tensor.shape[2]
                        break
                
                # Create a mask tensor with the correct dimensions
                mask_output = torch.zeros((1, height, width))
                image_output = None
            else:
                # Keep as an image
                image_output = layer_tensor
                mask_output = None
        else:
            # Unknown format, log error
            debug_log(logger, "error", "Unsupported tensor shape", 
                     f"Layer '{layer_name}' has an unsupported tensor shape: {layer_tensor.shape}")
            return [torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1))]
        
        # Set placeholder for any None outputs
        if image_output is None:
            image_output = torch.zeros((1, 1, 1, 3))
        if mask_output is None:
            mask_output = torch.zeros((1, 1, 1))
        
        return [image_output, mask_output]

# Define a copy of the main class for cryptomatte layers
class shamble_cryptomatte(load_exr_layer_by_name):
    """
    The Cryptomatte Shamble node allows selecting a specific cryptomatte layer from an EXR dictionary.
    It is identical to the Load EXR Layer by Name node but filters for cryptomatte layers only.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cryptomatte": ("CRYPTOMATTE",),
                "layer_name": ("STRING", {
                    "default": "none",
                    "multiline": False,
                    "description": "Name of the cryptomatte layer to extract. Look for names starting with 'crypto' in the metadata."
                })
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "process_cryptomatte"
    CATEGORY = "Image/EXR"
    
    def process_cryptomatte(self, cryptomatte: Dict[str, torch.Tensor], layer_name: str) -> List[torch.Tensor]:
        """
        Extract a specific cryptomatte layer.
        
        Args:
            cryptomatte: Dictionary of cryptomatte layer names to tensors
            layer_name: Name of the cryptomatte layer to extract
            
        Returns:
            List containing the cryptomatte image tensor
        """
        # Check if we have any layers at all
        if not cryptomatte or len(cryptomatte) == 0:
            debug_log(logger, "warning", "No cryptomatte layers available", "No cryptomatte layers available in the input")
            return [torch.zeros((1, 1, 1, 3))]
        
        # Update the class variable with available cryptomatte layer names
        self.__class__.available_layers = ["none"] + sorted(list(cryptomatte.keys()))
            
        # If the layer doesn't exist, try to find a close match
        if layer_name not in cryptomatte and layer_name != "none":
            # Try to find an exact match ignoring case
            case_insensitive_matches = [l for l in cryptomatte.keys() if l.lower() == layer_name.lower()]
            if case_insensitive_matches:
                layer_name = case_insensitive_matches[0]
                debug_log(logger, "info", "Found cryptomatte with different case", 
                         f"Cryptomatte layer name '{layer_name}' found with different case: '{layer_name}'")
            else:
                # Try to find a partial match
                matches = [l for l in cryptomatte.keys() if layer_name.lower() in l.lower()]
                if matches:
                    # Sort matches by length to find the closest match
                    matches.sort(key=len)
                    layer_name = matches[0]
                    debug_log(logger, "info", "Using closest cryptomatte match", 
                             f"Cryptomatte layer name '{layer_name}' not found exactly, using closest match: '{layer_name}'")
                else:
                    # Try to match hierarchical names (e.g., "CITY SCENE.CryptoAsset00" when user enters "CryptoAsset")
                    hierarchical_matches = []
                    for l in cryptomatte.keys():
                        if '.' in l:
                            parts = l.split('.')
                            # Check if any part matches the layer name
                            if any(part.lower() == layer_name.lower() for part in parts):
                                hierarchical_matches.append(l)
                    
                    if hierarchical_matches:
                        layer_name = hierarchical_matches[0]
                        debug_log(logger, "info", "Found hierarchical cryptomatte match", 
                                 f"Found hierarchical cryptomatte layer match: '{layer_name}'")
                    else:
                        debug_log(logger, "warning", "Cryptomatte layer not found", 
                                 f"Cryptomatte layer '{layer_name}' not found and no close matches")
                        # Use the first available layer as fallback
                        if len(cryptomatte) > 0:
                            layer_name = list(cryptomatte.keys())[0]
                            debug_log(logger, "info", "Using first available cryptomatte", 
                                     f"Using first available cryptomatte layer: {layer_name}")
                        else:
                            return [torch.zeros((1, 1, 1, 3))]
        
        # If no layer is specified or "none" is selected, return an empty tensor
        if not layer_name or layer_name == "none":
            debug_log(logger, "warning", "No cryptomatte layer specified", "No cryptomatte layer specified, returning empty tensor")
            return [torch.zeros((1, 1, 1, 3))]
        
        # Return the requested cryptomatte layer
        return [cryptomatte[layer_name]]

NODE_CLASS_MAPPINGS = {
    "load_exr_layer_by_name": load_exr_layer_by_name,
    "shamble_cryptomatte": shamble_cryptomatte
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "load_exr_layer_by_name": "Load EXR Layer by Name",
    "shamble_cryptomatte": "Cryptomatte Layer"
}
