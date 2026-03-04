import os
import logging
import numpy as np
import torch
from PIL import Image, ImageOps
from typing import Tuple

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


class ImageLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": ("STRING", {
                    "default": "path/to/image.png",
                    "description": "Full path to the image file"
                }),
                "normalize": ("BOOLEAN", {
                    "default": True,
                    "description": "Normalize image values to the 0-1 range"
                })
            },
            "hidden": {"node_id": "UNIQUE_ID"}
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "metadata")
    FUNCTION = "load_regular_image"
    CATEGORY = "COCO Tools/Loaders"
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")  # Always execute

    def load_regular_image(
        self, image_path: str, normalize: bool = True, node_id: str = None
    ) -> Tuple[torch.Tensor, torch.Tensor, str]:
        """
        Main function to load and process a regular image.
        Supports formats like PNG, JPG, and WebP.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image path not found: {image_path}")

        try:
            with Image.open(image_path) as img:
                # Preserve original format before any transforms
                original_format = img.format

                # Apply EXIF orientation
                img = ImageOps.exif_transpose(img)

                # Detect bit depth from original mode BEFORE RGB conversion
                original_mode = img.mode
                info = self.detect_bit_depth(image_path, original_mode, original_format)
                bit_depth = info["bit_depth"]

                # Extract alpha channel before RGB conversion
                has_alpha = original_mode in ("RGBA", "LA", "PA")
                if has_alpha:
                    alpha_tensor = self.pil2tensor(img.split()[-1], 8).unsqueeze(0)

                # High bit depth grayscale modes — bypass PIL's destructive convert("RGB")
                if bit_depth > 8 and original_mode in ("I;16", "I;16B", "I;16L", "I", "F"):
                    image_np = np.array(img)
                    if image_np.ndim == 2:
                        image_np = np.stack([image_np, image_np, image_np], axis=-1)
                    rgb_tensor = self.pil2tensor_numpy(image_np, bit_depth)
                else:
                    rgb_image = img.convert("RGB")
                    rgb_tensor = self.pil2tensor(rgb_image, bit_depth)

                # Default opaque alpha mask matching MASK format [B,H,W]
                if not has_alpha:
                    alpha_tensor = torch.ones(1, rgb_tensor.shape[1], rgb_tensor.shape[2])

                # Apply min-max range normalization if requested
                if normalize:
                    rgb_tensor = self.normalize_image(rgb_tensor)
                    alpha_tensor = alpha_tensor.clamp(0, 1)

                # Prepare metadata
                metadata = {
                    "file_path": image_path,
                    "tensor_shape": tuple(rgb_tensor.shape),
                    "format": os.path.splitext(image_path)[1].lower(),
                    "bit_depth": bit_depth
                }

                return rgb_tensor, alpha_tensor, str(metadata)

        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            raise ValueError(f"Error loading image {image_path}: {e}")

    @staticmethod
    def normalize_image(image: torch.Tensor) -> torch.Tensor:
        """
        Normalize a tensor to the 0-1 range via min-max stretching.
        Returns the image unchanged if all values are identical.
        """
        min_val, max_val = image.min(), image.max()
        if min_val == max_val:
            return image
        return (image - min_val) / (max_val - min_val)

    @staticmethod
    def detect_bit_depth(image_path: str, original_mode: str = None, original_format: str = None) -> dict:
        """
        Detect the bit depth of an image from its original mode before any conversion.
        """
        mode_to_bit_depth = {
            "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8,
            "LA": 8, "PA": 8,
            "I;16": 16, "I;16B": 16, "I;16L": 16,
            "I": 32, "F": 32
        }

        if original_mode is not None:
            mode = original_mode
            fmt = original_format
        else:
            with Image.open(image_path) as img:
                mode = img.mode
                fmt = img.format

        bit_depth = mode_to_bit_depth.get(mode, 8)
        return {"bit_depth": bit_depth, "mode": mode, "format": fmt}

    @staticmethod
    def pil2tensor(image: Image.Image, bit_depth: int) -> torch.Tensor:
        """
        Convert a PIL Image to a PyTorch tensor, scaled to the 0-1 range.
        """
        image_np = np.array(image)
        if bit_depth == 8:
            image_tensor = torch.from_numpy(image_np.astype(np.float32) / 255.0)
        elif bit_depth == 16:
            image_tensor = torch.from_numpy(image_np.astype(np.float32) / 65535.0)
        elif bit_depth == 32:
            image_tensor = torch.from_numpy(image_np.astype(np.float32))
        else:
            logger.warning(f"Unsupported bit depth: {bit_depth}. Defaulting to 8-bit normalization.")
            image_tensor = torch.from_numpy(image_np.astype(np.float32) / 255.0)

        # Add a batch dimension if not present
        if len(image_tensor.shape) == 3:
            image_tensor = image_tensor.unsqueeze(0)

        return image_tensor

    @staticmethod
    def pil2tensor_numpy(image_np: np.ndarray, bit_depth: int) -> torch.Tensor:
        """Convert a numpy array to a PyTorch tensor, scaled to 0-1 range based on bit depth."""
        if bit_depth == 16:
            image_tensor = torch.from_numpy(image_np.astype(np.float32) / 65535.0)
        elif bit_depth == 32:
            # PIL "I" mode stores int32 values; scale by dtype max to get 0-1 range
            if np.issubdtype(image_np.dtype, np.integer):
                max_val = np.iinfo(image_np.dtype).max
                image_tensor = torch.from_numpy(image_np.astype(np.float32) / max_val)
            else:
                image_tensor = torch.from_numpy(image_np.astype(np.float32))
        else:
            image_tensor = torch.from_numpy(image_np.astype(np.float32) / 255.0)

        if len(image_tensor.shape) == 3:
            image_tensor = image_tensor.unsqueeze(0)

        return image_tensor
