import os
import torch
import numpy as np
import logging

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
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

class LoadExrLayerByName:
    """
    The Load EXR Layer by Name node allows selecting a specific layer from an EXR layer dictionary.
    It works like Nuke's Shuffle node, allowing users to pick a specific layer to output.
    """

    # Class variables to store available layer names
    available_layers = ["none"]

    def __init__(self):
        debug_log(logger, "debug", "Layer selector initialized", "load_exr_layer_by_name class initialized")

    @classmethod
    def INPUT_TYPES(cls):
        # debug_log(logger, "info", f"Available layers: {len(cls.available_layers)}",
        #          f"INPUT_TYPES called - available layers: {cls.available_layers}")
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

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")  # Always execute

    def process_layer(self, layers: dict[str, torch.Tensor], layer_name: str,
                     conversion: str = "Auto") -> tuple[torch.Tensor, torch.Tensor]:
        """
        Extract a specific layer from the layers dictionary.

        Args:
            layers: Dictionary of layer names to tensors
            layer_name: Name of the layer to extract
            conversion: How to convert the layer (Auto, To RGB, To Mask)

        Returns:
            Tuple containing (image, mask) tensors
        """
        # Check if we have any layers at all
        if not layers or len(layers) == 0:
            debug_log(logger, "warning", "No layers available", "No layers available in the input")
            return (torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1)))

        # Log the available layers for debugging
        # debug_log(logger, "info", f"Found {len(layers)} layers: {format_layer_names(list(layers.keys()))}",
        #          f"Available layers: {list(layers.keys())}")
        if DEBUG_MODE == "verbose":
            for layer_key, layer_tensor in layers.items():
                debug_log(logger, "info", "", f"Layer '{layer_key}' has shape {layer_tensor.shape} and type {layer_tensor.dtype}")

        # Update the class variable with available layer names
        self.__class__.available_layers = ["none", *sorted(layers.keys())]

        # If the layer doesn't exist, try to find a close match
        if layer_name not in layers and layer_name != "none":
            original_name = layer_name
            # Try to find an exact match ignoring case
            case_insensitive_matches = [l for l in layers if l.lower() == layer_name.lower()]
            if case_insensitive_matches:
                layer_name = case_insensitive_matches[0]
                debug_log(logger, "debug", "Found layer with different case",
                         f"Layer name '{original_name}' found with different case: '{layer_name}'")
            else:
                # Try to find a partial match
                matches = [l for l in layers if layer_name.lower() in l.lower()]
                if matches:
                    # Sort matches by length to find the closest match
                    matches.sort(key=len)
                    layer_name = matches[0]
                    debug_log(logger, "debug", "Using closest layer match",
                             f"Layer name '{original_name}' not found exactly, using closest match: '{layer_name}'")
                else:
                    # Try to match hierarchical names (e.g., "CITY SCENE.AO" when user enters "AO")
                    hierarchical_matches = []
                    for l in layers:
                        if '.' in l:
                            parts = l.split('.')
                            # Check if any part matches the layer name
                            if any(part.lower() == layer_name.lower() for part in parts):
                                hierarchical_matches.append(l)

                    if hierarchical_matches:
                        layer_name = hierarchical_matches[0]
                        debug_log(logger, "debug", "Found hierarchical match",
                                 f"Found hierarchical layer match for '{original_name}': '{layer_name}'")
                    else:
                        # Try to match subimage names (e.g., "AO" for a subimage)
                        subimage_matches = [l for l in layers if l.split('.')[0].lower() == layer_name.lower()]
                        if subimage_matches:
                            layer_name = subimage_matches[0]
                            debug_log(logger, "debug", "Found subimage match",
                                     f"Found subimage match for '{original_name}': '{layer_name}'")
                        else:
                            debug_log(logger, "warning", "Layer not found",
                                     f"Layer '{original_name}' not found and no close matches")
                            # Use the first available layer as fallback
                            if len(layers) > 0:
                                layer_name = next(iter(layers.keys()))
                                debug_log(logger, "debug", "Using first available layer",
                                         f"Using first available layer: {layer_name}")
                            else:
                                return (torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1)))

        # If no layer is specified or "none" is selected, return empty tensors
        if not layer_name or layer_name == "none":
            debug_log(logger, "warning", "No layer specified", "No layer specified, returning empty tensors")
            return (torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1)))

        # Get the requested layer
        layer_tensor = layers[layer_name]

        debug_log(logger, "debug", f"Processing layer '{layer_name}'",
                 f"Processing layer '{layer_name}' with shape {layer_tensor.shape} and type {layer_tensor.dtype}")

        # Special handling for alpha layers only (not depth or Z)
        is_alpha_layer = 'alpha' in layer_name.lower()

        # Check tensor shape to determine its type
        if len(layer_tensor.shape) == 4 and layer_tensor.shape[3] == 3:
            # It's an RGB tensor [1, H, W, 3]
            if conversion == "To Mask" or (conversion == "Auto" and is_alpha_layer):
                # Convert RGB to mask by taking the mean across channels
                mask_output = layer_tensor.mean(dim=3, keepdim=False)
                image_output = None
                debug_log(logger, "debug", "Converted to mask", f"Converted RGB tensor to mask: shape={mask_output.shape}")
            else:
                # Keep as an image
                image_output = layer_tensor
                mask_output = None
                debug_log(logger, "debug", "Using as RGB image", f"Using RGB tensor as image: shape={image_output.shape}")
        elif len(layer_tensor.shape) == 3:
            # It's a single-channel tensor [1, H, W]
            # Special handling for depth and Z channels
            is_depth_or_z = 'depth' in layer_name.lower() or layer_name.lower() == 'z'

            if conversion == "To RGB":
                # Convert to RGB by replicating to 3 channels
                image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                mask_output = None
                debug_log(logger, "debug", "Converted to RGB", f"Converted single-channel tensor to RGB: shape={image_output.shape}")
            elif is_depth_or_z:
                # For depth and Z channels, return as image by default
                image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                mask_output = None
                debug_log(logger, "debug", "Converted depth to RGB", f"Converted depth/Z tensor to RGB: shape={image_output.shape}")
            elif 'alpha' in layer_name.lower():
                # For alpha channels, return as mask
                mask_output = layer_tensor
                image_output = None
                debug_log(logger, "debug", "Using alpha as mask", f"Using alpha tensor as mask: shape={mask_output.shape}")
            else:
                # For other single-channel data, use the conversion setting
                if conversion == "To Mask":
                    mask_output = layer_tensor
                    image_output = None
                    debug_log(logger, "debug", "Using as mask", f"Using single-channel tensor as mask: shape={mask_output.shape}")
                else:
                    # Default to RGB for Auto mode for non-alpha channels
                    image_output = torch.cat([layer_tensor.unsqueeze(3)] * 3, dim=3)
                    mask_output = None
                    debug_log(logger, "debug", "Using as RGB (Auto)", f"Using single-channel tensor as RGB (Auto): shape={image_output.shape}")
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
                        if len(other_tensor.shape) == 4 or len(other_tensor.shape) == 3:  # RGB tensor [1, H, W, 3]
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
            return (torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1)))

        # Set placeholder for any None outputs
        if image_output is None:
            image_output = torch.zeros((1, 1, 1, 3))
        if mask_output is None:
            mask_output = torch.zeros((1, 1, 1))

        return (image_output, mask_output)

# Define a copy of the main class for cryptomatte layers
class CryptomatteLayer(LoadExrLayerByName):
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
            },
            "optional": {
                "preview_image": ("IMAGE", {
                    "description": "Connect the beauty/rendered image here to enable click-to-matte selection."
                }),
                "x_coord": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 16384,
                    "step": 1,
                    "description": "X pixel coordinate for click-to-matte selection. Set to -1 to disable."
                }),
                "y_coord": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 16384,
                    "step": 1,
                    "description": "Y pixel coordinate for click-to-matte selection. Set to -1 to disable."
                })
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "process_cryptomatte"
    CATEGORY = "Image/EXR"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")  # Always execute

    def process_cryptomatte(self, cryptomatte: dict[str, torch.Tensor], layer_name: str,
                            preview_image=None, x_coord: int = -1, y_coord: int = -1):
        """
        Extract a specific cryptomatte layer, optionally generating a matte mask
        from the object ID at a clicked pixel position.
        """
        empty_result = {"result": (torch.zeros((1, 1, 1, 3)), torch.zeros((1, 1, 1))), "ui": {}}

        if not cryptomatte or len(cryptomatte) == 0:
            debug_log(logger, "warning", "No cryptomatte layers available")
            return empty_result

        self.__class__.available_layers = ["none", *sorted(cryptomatte.keys())]

        # Resolve layer name with fuzzy matching
        layer_name = self._resolve_layer_name(cryptomatte, layer_name)
        if not layer_name:
            return empty_result

        layer_tensor = cryptomatte[layer_name]

        # Ensure image output is [1, H, W, 3] for IMAGE type compatibility
        image_output = self._ensure_rgb_output(layer_tensor)

        # Generate matte mask from click coordinates
        mask_output, selected_pixels = self._generate_matte_mask(layer_tensor, x_coord, y_coord)

        # Build UI data with preview image for click-to-matte JS widget
        ui_data = self._build_preview_ui(preview_image, mask_output, selected_pixels)

        return {"result": (image_output, mask_output), "ui": ui_data}

    def _resolve_layer_name(self, cryptomatte, layer_name):
        """Resolve a layer name against the cryptomatte dict with fuzzy matching."""
        if not layer_name or layer_name == "none":
            debug_log(logger, "warning", "No cryptomatte layer specified")
            return None

        if layer_name in cryptomatte:
            return layer_name

        original_name = layer_name

        # Case-insensitive match
        for key in cryptomatte:
            if key.lower() == layer_name.lower():
                debug_log(logger, "debug", f"Found cryptomatte '{key}' (case-insensitive)")
                return key

        # Partial match
        matches = sorted([k for k in cryptomatte if layer_name.lower() in k.lower()], key=len)
        if matches:
            debug_log(logger, "debug", f"Using closest cryptomatte match: '{matches[0]}'")
            return matches[0]

        # Hierarchical match
        for key in cryptomatte:
            if '.' in key:
                parts = key.split('.')
                if any(part.lower() == layer_name.lower() for part in parts):
                    debug_log(logger, "debug", f"Found hierarchical match: '{key}'")
                    return key

        # Fallback to first available
        debug_log(logger, "warning", f"Cryptomatte layer '{original_name}' not found")
        if cryptomatte:
            first = next(iter(cryptomatte.keys()))
            debug_log(logger, "debug", f"Using first available: '{first}'")
            return first
        return None

    @staticmethod
    def _ensure_rgb_output(layer_tensor):
        """Ensure tensor is [1, H, W, 3] for IMAGE type output."""
        if len(layer_tensor.shape) == 4:
            if layer_tensor.shape[0] > 1:
                layer_tensor = layer_tensor[0:1]
            channels = layer_tensor.shape[3]
            if channels == 3:
                return layer_tensor
            elif channels > 3:
                return layer_tensor[:, :, :, :3]
            else:
                return layer_tensor[:, :, :, :1].repeat(1, 1, 1, 3)
        elif len(layer_tensor.shape) == 3:
            return layer_tensor[0:1].unsqueeze(3).repeat(1, 1, 1, 3)
        return torch.zeros((1, 1, 1, 3))

    def _generate_matte_mask(self, layer_tensor, x_coord, y_coord):
        """
        Generate a matte mask from a cryptomatte layer by sampling the object ID
        hash at the given pixel and selecting all pixels with the same hash.

        Returns:
            Tuple of (mask_tensor [1, H, W], selected_pixel_count)
        """
        # Get spatial dimensions
        if len(layer_tensor.shape) == 4:
            height, width = layer_tensor.shape[1], layer_tensor.shape[2]
        elif len(layer_tensor.shape) == 3:
            height, width = layer_tensor.shape[1], layer_tensor.shape[2]
        else:
            return torch.zeros((1, 1, 1)), 0

        if x_coord < 0 or y_coord < 0:
            return torch.zeros((1, height, width)), 0

        x_clamped = min(max(x_coord, 0), width - 1)
        y_clamped = min(max(y_coord, 0), height - 1)

        debug_log(logger, "debug", f"Click-to-matte at ({x_clamped}, {y_clamped})")

        # Sample the cryptomatte hash at clicked pixel
        # Search across all ranks (batch dim) and ID channels (even indices)
        epsilon = 1e-6
        hash_value = None

        if len(layer_tensor.shape) == 4:
            num_ranks = layer_tensor.shape[0]
            num_channels = layer_tensor.shape[3]
            for b in range(num_ranks):
                for ch in range(0, num_channels, 2):
                    val = layer_tensor[b, y_clamped, x_clamped, ch].item()
                    if abs(val) > epsilon:
                        hash_value = val
                        break
                if hash_value is not None:
                    break
        else:
            val = layer_tensor[0, y_clamped, x_clamped].item()
            if abs(val) > epsilon:
                hash_value = val

        if hash_value is None:
            debug_log(logger, "debug", "No object at clicked position")
            return torch.zeros((1, height, width)), 0

        debug_log(logger, "debug", f"Sampled hash: {hash_value}")

        # Build mask: match hash across all ranks and ID channels
        match_mask = torch.zeros((1, height, width), dtype=torch.float32)

        if len(layer_tensor.shape) == 4:
            num_ranks = layer_tensor.shape[0]
            num_channels = layer_tensor.shape[3]
            for b in range(num_ranks):
                for ch in range(0, num_channels, 2):
                    channel_data = layer_tensor[b:b+1, :, :, ch]
                    channel_match = (torch.abs(channel_data - hash_value) < epsilon).float()
                    match_mask = torch.max(match_mask, channel_match)
        else:
            match_mask = (torch.abs(layer_tensor[0:1] - hash_value) < epsilon).float()

        selected = int(match_mask.sum().item())
        debug_log(logger, "debug", f"Matte mask: {selected} pixels selected")

        return match_mask, selected

    def _build_preview_ui(self, preview_image, mask_output, selected_pixels):
        """Save preview image as temp file and build UI data dict for JS."""
        if preview_image is None:
            return {}

        try:
            import folder_paths
            from PIL import Image

            frame = preview_image[0].cpu().numpy()
            height, width = frame.shape[0], frame.shape[1]

            # Convert to uint8 for preview
            preview_np = (np.clip(frame, 0.0, 1.0) * 255).astype(np.uint8)

            # Overlay zebra stripe pattern on selected matte pixels
            if selected_pixels > 0 and mask_output is not None:
                mask_np = mask_output[0].cpu().numpy()
                if mask_np.shape[0] == height and mask_np.shape[1] == width:
                    # Diagonal stripe pattern: (x + y) mod period < half_period
                    stripe_period = 6
                    yy, xx = np.mgrid[:height, :width]
                    stripe = ((xx + yy) % stripe_period) < (stripe_period // 2)
                    # Where mask is active: darken on dark stripes, lighten on light stripes
                    active = mask_np > 0.5
                    overlay = preview_np.astype(np.int16)
                    overlay[active & stripe] = np.clip(overlay[active & stripe] + 40, 0, 255)
                    overlay[active & ~stripe] = np.clip(overlay[active & ~stripe] - 40, 0, 255)
                    preview_np = overlay.astype(np.uint8)

            img = Image.fromarray(preview_np)
            temp_dir = folder_paths.get_temp_directory()
            filename = f"cryptomatte_preview_{id(self) % 100000:05d}.png"
            filepath = os.path.join(temp_dir, filename)
            img.save(filepath, compress_level=4)

            return {
                "preview_image": [{"filename": filename, "subfolder": "", "type": "temp"}],
                "image_width": [width],
                "image_height": [height],
                "selected_pixels": [selected_pixels],
            }
        except Exception as e:
            debug_log(logger, "warning", f"Preview save failed: {e}")
            return {}
