import numpy as np
import logging

try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

try:
    from ..utils.debug_utils import debug_log
except ImportError:
    def debug_log(logger, level, simple_msg, verbose_msg=None, **kwargs):
        getattr(logger, level.lower())(simple_msg)

from comfy_api.latest import io

SRGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])


def _convert_ycbcr(pixels):
    """Convert RGB pixels to YCbCr Rec.709 scatter coordinates."""
    r, g, b = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    cb = (b - y) / 1.8556
    cr = (r - y) / 1.5748
    return cb, -cr


def _convert_hsv(pixels):
    """Convert RGB pixels to HSV polar scatter coordinates."""
    r, g, b = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    hue = np.arctan2(np.sqrt(3.0) * (g - b), 2.0 * r - g - b)
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    saturation = np.where(max_c > 0, 1.0 - min_c / max_c, 0.0)
    x = saturation * np.cos(hue)
    y = saturation * np.sin(hue)
    return x, y


def _convert_cie_xy(pixels):
    """Convert RGB pixels to CIE xy chromaticity scatter coordinates."""
    xyz = pixels @ SRGB_TO_XYZ.T
    total = xyz[:, 0] + xyz[:, 1] + xyz[:, 2]
    valid = total > 1e-10
    x_chrom = np.where(valid, xyz[:, 0] / total, 0.3127)
    y_chrom = np.where(valid, xyz[:, 1] / total, 0.3290)
    x_display = (x_chrom - 0.15) / 0.65
    y_display = (y_chrom - 0.05) / 0.65
    return x_display, y_display


class VectorscopeNode(io.ComfyNode):
    """Visualizes color distribution on a circular chromaticity display."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VectorscopeNode",
            display_name="CoCo Vectorscope",
            description="Displays a vectorscope visualization of image color distribution with selectable color models.",
            category="COCO Tools/Analysis",
            is_output_node=True,
            inputs=[
                io.Image.Input("image", tooltip="Image tensor to analyze"),
                io.Combo.Input("color_model", options=["YCbCr", "HSV", "CIE xy"], default="YCbCr", tooltip="Color model for vectorscope display"),
                io.Int.Input("sample_count", default=50000, min=5000, max=200000, tooltip="Maximum number of scatter points"),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, image, color_model="YCbCr", sample_count=50000) -> io.NodeOutput:
        try:
            frame = image[0].cpu().numpy()
            height, width, channels = frame.shape

            if channels < 3:
                debug_log(logger, "warning", f"Vectorscope requires at least 3 channels, got {channels}")
                frame = np.repeat(frame, 3 // channels + 1, axis=2)[:, :, :3]
                channels = 3

            pixels = frame.reshape(-1, channels)[:, :3]

            total_pixels = pixels.shape[0]
            if total_pixels > sample_count:
                indices = np.linspace(0, total_pixels - 1, sample_count, dtype=int)
                pixels = pixels[indices]

            converters = {
                "YCbCr": _convert_ycbcr,
                "HSV": _convert_hsv,
                "CIE xy": _convert_cie_xy,
            }
            x_coords, y_coords = converters[color_model](pixels)

            x_coords = np.round(x_coords, 4)
            y_coords = np.round(y_coords, 4)

            result = {
                "color_model": color_model,
                "x_coords": x_coords.tolist(),
                "y_coords": y_coords.tolist(),
                "point_count": len(x_coords),
                "image_info": {
                    "width": width,
                    "height": height,
                    "channels": channels,
                    "batch_size": int(image.shape[0]),
                },
            }

            debug_log(logger, "info",
                      f"Vectorscope computed: {width}x{height}, {color_model}, {len(x_coords)} points")

            return io.NodeOutput(ui={"vectorscope_data": [result]})

        except Exception as e:
            debug_log(logger, "error", "Vectorscope computation failed", f"Error computing vectorscope: {str(e)}")
            raise

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")
