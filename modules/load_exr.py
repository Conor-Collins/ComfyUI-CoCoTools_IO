import os
import logging
from typing import List

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Import EXR utilities
try:
    from ..utils.exr_utils import ExrProcessor
except ImportError:
    raise ImportError("EXR utilities are required but not available. Please ensure utils are properly installed.")

class LoadExr:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": ("STRING", {
                    "default": "path/to/image.exr",
                    "description": "Full path to the EXR file"
                }),
                "normalize": ("BOOLEAN", {
                    "default": False,
                    "description": "Normalize image values to the 0-1 range"
                })
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
                "layer_data": "DICT"
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "CRYPTOMATTE", "LAYERS", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "alpha", "cryptomatte", "layers", "layer names", "raw layer info", "metadata")
    
    FUNCTION = "load_image"
    CATEGORY = "Image/EXR"
    
    @classmethod
    def IS_CHANGED(cls, image_path, normalize=False, **kwargs):
        """
        Smart caching based on file modification time and size.
        Only reload if file actually changed or parameters changed.
        """
        try:
            if not os.path.isfile(image_path):
                return float("NaN")  # File doesn't exist, always try to load
            
            stat = os.stat(image_path)
            # Create hash from file path, modification time, size, and normalize parameter
            return f"{image_path}_{stat.st_mtime}_{stat.st_size}_{normalize}"
        except Exception:
            # If we can't access file info, always try to load
            return float("NaN")
    
    def load_image(self, image_path: str, normalize: bool = False, 
                   node_id: str = None, layer_data: dict = None, **kwargs) -> List:
        """
        Load a single EXR image with support for multiple layers/channel groups.
        Returns:
        - Base RGB image tensor (image)
        - Alpha channel tensor (alpha)
        - Dictionary of all cryptomatte layers as tensors (cryptomatte)
        - Dictionary of all non-cryptomatte layers as tensors (layers)
        - List of processed layer names matching keys in the returned dictionaries (layer names)
        - List of raw channel names from the file (raw layer info)
        - Metadata as JSON string (metadata)
        """
        
        # Check for OIIO availability
        ExrProcessor.check_oiio_availability()
            
        try:
            # Validate single image path
            if not os.path.isfile(image_path):
                raise FileNotFoundError(f"Image not found: {image_path}")
            
            # Use shared EXR processing functionality
            return ExrProcessor.process_exr_data(image_path, normalize, node_id, layer_data)
            
        except Exception as e:
            logger.error(f"Error loading EXR file {image_path}: {str(e)}")
            raise












