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


class HistogramNode(io.ComfyNode):
    """Computes and displays histogram data from IMAGE tensors."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="HistogramNode",
            display_name="CoCo Histogram",
            description="Displays an interactive histogram of image tonal distribution with per-channel statistics.",
            category="COCO Tools/Analysis",
            is_output_node=True,
            inputs=[
                io.Image.Input("image", tooltip="Image tensor to analyze"),
                io.Int.Input("num_bins", default=256, min=32, max=1024, tooltip="Number of histogram bins"),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, image, num_bins=256) -> io.NodeOutput:
        try:
            frame = image[0].cpu().numpy()
            height, width, channels = frame.shape
            original_channels = channels

            if channels < 3:
                debug_log(logger, "warning", f"Histogram requires at least 3 channels, got {channels}")
                frame = np.repeat(frame, 3 // channels + 1, axis=2)[:, :, :3]
                channels = 3

            data_min = float(frame.min())
            data_max = float(frame.max())
            bin_range = (min(data_min, 0.0), max(data_max, 1.0))

            result = {
                "image_info": {
                    "width": width,
                    "height": height,
                    "channels": original_channels,
                    "batch_size": int(image.shape[0]),
                    "data_range": [round(data_min, 6), round(data_max, 6)],
                }
            }

            channel_names = ["red", "green", "blue"]
            if channels == 4:
                channel_names.append("alpha")

            stats = {}
            for i, name in enumerate(channel_names):
                ch = frame[:, :, i].ravel()
                counts, bin_edges = np.histogram(ch, bins=num_bins, range=bin_range)
                result[name] = counts.tolist()
                stats[name] = _compute_channel_stats(ch)

            result["bins"] = [round(float(b), 6) for b in bin_edges]

            lum = 0.2126 * frame[:, :, 0] + 0.7152 * frame[:, :, 1] + 0.0722 * frame[:, :, 2]
            lum_flat = lum.ravel()
            lum_counts, _ = np.histogram(lum_flat, bins=num_bins, range=bin_range)
            result["luminance"] = lum_counts.tolist()
            stats["luminance"] = _compute_channel_stats(lum_flat)

            if channels < 4:
                result["alpha"] = None
                stats["alpha"] = None

            result["stats"] = stats

            debug_log(logger, "info",
                      f"Histogram computed: {width}x{height}, {channels}ch, range=[{data_min:.4f}, {data_max:.4f}]")

            return io.NodeOutput(ui={"histogram_data": [result]})

        except Exception as e:
            debug_log(logger, "error", "Histogram computation failed", f"Error computing histogram: {str(e)}")
            raise

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("NaN")


def _compute_channel_stats(channel_data):
    """Compute statistics for a single channel."""
    total_pixels = len(channel_data)
    return {
        "min": round(float(np.min(channel_data)), 6),
        "max": round(float(np.max(channel_data)), 6),
        "mean": round(float(np.mean(channel_data)), 6),
        "median": round(float(np.median(channel_data)), 6),
        "stddev": round(float(np.std(channel_data)), 6),
        "p5": round(float(np.percentile(channel_data, 5)), 6),
        "p95": round(float(np.percentile(channel_data, 95)), 6),
        "clip_low": round(float(np.sum(channel_data <= 0.0) / total_pixels * 100), 2),
        "clip_high": round(float(np.sum(channel_data >= 1.0) / total_pixels * 100), 2),
    }
