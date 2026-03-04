import contextlib
import torch
import logging

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Import debug utilities and batch processing
try:
    from ..utils.debug_utils import debug_log, format_tensor_info
    from ..utils.batch_utils import validate_4d_batch, log_batch_processing
except ImportError:
    # Fallback if utils not available
    def debug_log(logger, level, simple_msg, verbose_msg=None, **kwargs):
        getattr(logger, level.lower())(simple_msg)
    def format_tensor_info(tensor_shape, tensor_dtype, name=""):
        return f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}"
    def validate_4d_batch(tensor, name="input"):
        return tensor.shape
    def log_batch_processing(tensor, operation, name="tensor"):
        pass

class ZNormalizeNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),  # Changed to accept IMAGE tensor
                "min_depth": ("FLOAT", {
                    "default": 0.0,
                    "min": -10000.0,
                    "max": 10000.0,
                    "step": 0.01,
                    "description": "Minimum depth value for normalization"
                }),
                "max_depth": ("FLOAT", {
                    "default": 1.0,
                    "min": -10000.0,
                    "max": 10000.0,
                    "step": 0.01,
                    "description": "Maximum depth value for normalization"
                }),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("normalized_depth_image",)
    FUNCTION = "normalize_depth"
    CATEGORY = "COCO Tools/Processing"

    @classmethod
    def IS_CHANGED(cls, image, min_depth, max_depth, **kwargs):
        """
        Smart caching based on input tensor properties and depth parameters.
        Only re-execute when inputs or parameters actually change.
        """
        try:
            # Hash based on tensor properties
            tensor_hash = f"{image.shape}_{image.dtype}_{image.device}"

            # Include depth range parameters
            param_hash = f"{min_depth}_{max_depth}"

            # Sample a few pixel values for content-aware caching
            # Take samples from corners and center to detect actual data changes
            sample_indices = [
                (0, 0, 0, 0),  # Top-left of first image
                (0, -1, -1, 0),  # Bottom-right of first image
                (0, image.shape[1]//2, image.shape[2]//2, 0),  # Center of first image
            ]
            samples = []
            for idx in sample_indices:
                with contextlib.suppress(IndexError, RuntimeError):
                    samples.append(f"{image[idx].item():.6f}")
            sample_hash = "_".join(samples)

            return f"{tensor_hash}_{param_hash}_{sample_hash}"
        except Exception:
            # If anything goes wrong, always execute
            return float("NaN")

    def normalize_depth(self, image, min_depth, max_depth):
        """
        Normalize depth image tensor with full batch processing support.

        Args:
            image: Input tensor in [B,H,W,C] format
            min_depth: Minimum depth value for normalization
            max_depth: Maximum depth value for normalization

        Returns:
            Normalized tensor in [B,H,W,C] format
        """
        try:
            # Log batch processing info using utility
            log_batch_processing(image, f"Normalizing depth range=[{min_depth}, {max_depth}]", "depth")

            # Validate input tensor using utility
            batch_size, _height, _width, _channels = validate_4d_batch(image, "depth image")

            # Validate depth range
            if max_depth <= min_depth:
                raise ValueError(f"max_depth ({max_depth}) must be greater than min_depth ({min_depth})")

            # Create a copy to avoid modifying the input
            normalized = image.clone()

            # Log input value range for debugging
            input_min, input_max = normalized.min().item(), normalized.max().item()
            debug_log(logger, "debug", f"Input range: [{input_min:.6f}, {input_max:.6f}]",
                     f"Input depth values range from {input_min:.6f} to {input_max:.6f}")

            # Normalize depth values - this operation is automatically batch-aware
            depth_range = max_depth - min_depth
            normalized = (normalized - min_depth) / depth_range

            # Clip values to [0,1] range - also batch-aware
            normalized = torch.clamp(normalized, 0.0, 1.0)

            # Log normalized value range
            norm_min, norm_max = normalized.min().item(), normalized.max().item()
            debug_log(logger, "debug", f"Normalized to: [{norm_min:.6f}, {norm_max:.6f}]",
                     f"After normalization, values range from {norm_min:.6f} to {norm_max:.6f}")

            # Handle single channel depth maps by replicating to RGB
            if normalized.shape[-1] == 1:
                debug_log(logger, "debug", "Converting single channel to RGB",
                         "Single channel depth detected, replicating to RGB channels")
                normalized = normalized.repeat(1, 1, 1, 3)

            debug_log(logger, "debug", f"Depth normalization complete: {format_tensor_info(normalized.shape, normalized.dtype)}",
                     f"Successfully normalized {batch_size} depth images with final shape {normalized.shape}")

            return (normalized,)

        except Exception as e:
            debug_log(logger, "error", "Depth normalization failed", f"Error normalizing depth image: {e!s}")
            raise
