import os
import logging
import numpy as np
import torch
from PIL import Image, ImageOps
from typing import Tuple

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
                # Apply EXIF orientation and convert to RGB
                img = ImageOps.exif_transpose(img)
                rgb_image = img.convert("RGB")

                # Detect bit depth and convert to tensor
                info = self.detect_bit_depth(image_path, rgb_image)
                bit_depth = info["bit_depth"]
                rgb_tensor = self.pil2tensor(rgb_image, bit_depth)

                # Handle alpha channel if present
                alpha_tensor = (
                    self.pil2tensor(img.split()[-1], bit_depth).unsqueeze(-1)
                    if img.mode == "RGBA" else torch.ones_like(rgb_tensor[:, :, :, :1])
                )

                # Normalize tensors if requested
                if normalize:
                    rgb_tensor = self.normalize_image(rgb_tensor)
                    alpha_tensor = self.normalize_image(alpha_tensor)

                # Prepare metadata
                metadata = {
                    "file_path": image_path,
                    "tensor_shape": tuple(rgb_tensor.shape),
                    "format": os.path.splitext(image_path)[1].lower()
                }

                return rgb_tensor, alpha_tensor, str(metadata)

        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            raise ValueError(f"Error loading image {image_path}: {e}")

    @staticmethod
    def normalize_image(image: torch.Tensor) -> torch.Tensor:
        """
        Normalize a tensor to the 0-1 range.
        """
        min_val, max_val = image.min(), image.max()
        return (image - min_val) / (max_val - min_val) if min_val != max_val else torch.zeros_like(image)

    @staticmethod
    def detect_bit_depth(image_path: str, image: Image.Image = None) -> dict:
        """
        Detect the bit depth of an image. Supports a range of bit depths for accurate conversion.
        """
        mode_to_bit_depth = {
            "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8,
            "I;16": 16, "I": 32, "F": 32
        }

        if image is None:
            with Image.open(image_path) as img:
                mode = img.mode
                fmt = img.format
        else:
            mode = image.mode
            fmt = image.format

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


# NODE_CLASS_MAPPINGS = {
#     "coco_loader": coco_loader
# }

# NODE_DISPLAY_NAME_MAPPINGS = {
#     "coco_loader": "Load Image (supports jpg, png, tif, avif, webp)"
# }
