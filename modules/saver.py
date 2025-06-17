import os
import torch
import numpy as np
import tifffile
import folder_paths
from typing import Dict, Tuple, Optional
import OpenImageIO as oiio
from datetime import datetime

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2 as cv

class saver:
    """Optimized image saver node with consistent bit depth handling"""
    
    # Format specifications
    FORMAT_SPECS = {
        "exr": {"depths": [16, 32], "opencv": False},  # EXR only supports half and full float
        "png": {"depths": [8, 16], "opencv": False},  # PNG only supports integer formats
        "jpg": {"depths": [8], "opencv": True},
        "webp": {"depths": [8], "opencv": True},
        "tiff": {"depths": [8, 16, 32], "opencv": False}
    }
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "file_path": ("STRING", {"default": ""}),
                "filename": ("STRING", {"default": "ComfyUI"}),
                "use_versioning": ("BOOLEAN", {"default": False}),
                "version": ("INT", {"default": 1, "min": -1, "max": 999}),
                "file_type": (["exr", "png", "jpg", "webp", "tiff"], {"default": "png"}),
                "bit_depth": (["8", "16", "32"], {"default": "16"}),
                "exr_compression": (["none", "zip", "zips", "rle", "pxr24", "b44", "b44a", "dwaa", "dwab"], 
                                  {"default": "zips"}),
                "quality": ("INT", {"default": 95, "min": 1, "max": 100}),
                "save_as_grayscale": ("BOOLEAN", {"default": False})
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "COCO Tools/Savers"

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()

    @staticmethod
    def is_grayscale_fast(image: np.ndarray, sample_rate: float = 0.1) -> bool:
        """Fast grayscale detection by sampling pixels"""
        if len(image.shape) == 2 or image.shape[-1] == 1:
            return True
        if image.shape[-1] == 3:
            # Sample 10% of pixels for large images
            total_pixels = image.shape[0] * image.shape[1]
            if total_pixels > 1000000:  # 1MP
                indices = np.random.choice(total_pixels, int(total_pixels * sample_rate), replace=False)
                flat_img = image.reshape(-1, 3)
                sampled = flat_img[indices]
                return np.allclose(sampled[:, 0], sampled[:, 1], rtol=0.01) and \
                       np.allclose(sampled[:, 1], sampled[:, 2], rtol=0.01)
            else:
                return np.allclose(image[..., 0], image[..., 1], rtol=0.01) and \
                       np.allclose(image[..., 1], image[..., 2], rtol=0.01)
        return False

    def validate_bit_depth(self, file_type: str, bit_depth: int) -> int:
        """Validate and adjust bit depth for format"""
        valid_depths = self.FORMAT_SPECS[file_type]["depths"]
        if bit_depth not in valid_depths:
            return valid_depths[0]
        return bit_depth

    def convert_to_grayscale(self, img: np.ndarray) -> np.ndarray:
        """Proper grayscale conversion using luminance weights"""
        if len(img.shape) == 2 or img.shape[-1] == 1:
            return img if img.shape[-1] == 1 else img[..., np.newaxis]
        
        if img.shape[-1] >= 3:
            # ITU-R BT.709 luminance weights
            weights = np.array([0.2126, 0.7152, 0.0722])
            gray = np.dot(img[..., :3], weights)
            return gray[..., np.newaxis]
        
        return img[..., 0:1]  # Fallback for 2-channel images

    def prepare_image(self, img_tensor: torch.Tensor, save_as_grayscale: bool) -> np.ndarray:
        """Convert tensor to numpy and prepare channels"""
        # Convert from tensor
        if img_tensor.ndim == 4 and img_tensor.shape[0] == 1:
            img_np = img_tensor.squeeze(0).cpu().numpy()
        else:
            img_np = img_tensor.cpu().numpy()
        
        # Ensure float32 [0,1] range
        img_np = np.clip(img_np, 0, 1).astype(np.float32)
        
        # Handle channels
        if len(img_np.shape) == 2:
            img_np = img_np[..., np.newaxis]
        
        # Convert to grayscale if explicitly requested (don't auto-detect for solid colors)
        if save_as_grayscale:
            img_np = self.convert_to_grayscale(img_np)
        
        return img_np

    def save_exr(self, img: np.ndarray, path: str, bit_depth: int, compression: str) -> None:
        """Save EXR with proper float handling"""
        # Convert to appropriate type based on bit depth
        if bit_depth == 8:
            # 8-bit EXR as uint8
            data = (img * 255).astype(np.uint8)
            pixel_type = oiio.UINT8
        elif bit_depth == 16:
            data = img.astype(np.float16)
            pixel_type = oiio.HALF
        else:  # 32
            data = img.astype(np.float32)
            pixel_type = oiio.FLOAT
        
        data = np.ascontiguousarray(data)
        channels = 1 if data.ndim == 2 else data.shape[-1]
        
        spec = oiio.ImageSpec(data.shape[1], data.shape[0], channels, pixel_type)
        spec.attribute("compression", compression)
        spec.attribute("Software", "COCO Tools")
        
        buf = oiio.ImageBuf(spec)
        buf.set_pixels(oiio.ROI(), data)
        
        if not buf.write(path):
            raise RuntimeError(f"Failed to write EXR: {oiio.geterror()}")

    def save_png(self, img: np.ndarray, path: str, bit_depth: int) -> None:
        """Save PNG with proper bit depth handling"""
        # Convert to appropriate type based on bit depth
        if bit_depth == 8:
            data = (img * 255).astype(np.uint8)
            pixel_type = oiio.UINT8
        elif bit_depth == 16:
            data = (img * 65535).astype(np.uint16)
            pixel_type = oiio.UINT16
        elif bit_depth == 32:
            # 32-bit PNG as float32 (preserves full range)
            data = img.astype(np.float32)
            pixel_type = oiio.FLOAT
        else:
            # Fallback to 8-bit for unsupported depths
            data = (img * 255).astype(np.uint8)
            pixel_type = oiio.UINT8
        
        data = np.ascontiguousarray(data)
        channels = 1 if data.ndim == 2 else data.shape[-1]
        
        spec = oiio.ImageSpec(data.shape[1], data.shape[0], channels, pixel_type)
        spec.attribute("compression", "zip")
        spec.attribute("png:compressionLevel", 9)
        
        # For 32-bit float PNG, set linear color space
        if bit_depth == 32:
            spec.attribute("oiio:ColorSpace", "Linear")
        
        buf = oiio.ImageBuf(spec)
        buf.set_pixels(oiio.ROI(), data)
        
        if not buf.write(path):
            raise RuntimeError(f"Failed to write PNG: {oiio.geterror()}")

    def save_opencv_format(self, img: np.ndarray, path: str, quality: int = 95) -> None:
        """Save JPEG/WebP using OpenCV"""
        # Convert to 8-bit BGR
        data = (img * 255).astype(np.uint8)
        
        # Convert RGB to BGR only for 3+ channel images
        if data.shape[-1] >= 3:
            data = cv.cvtColor(data, cv.COLOR_RGB2BGR)
        
        # Save with quality setting
        if path.endswith(('.jpg', '.jpeg')):
            cv.imwrite(path, data, [cv.IMWRITE_JPEG_QUALITY, quality])
        else:  # webp
            cv.imwrite(path, data, [cv.IMWRITE_WEBP_QUALITY, quality])

    def save_tiff(self, img: np.ndarray, path: str, bit_depth: int) -> None:
        """Save TIFF with proper bit depth"""
        if bit_depth == 8:
            data = (img * 255).astype(np.uint8)
        elif bit_depth == 16:
            data = (img * 65535).astype(np.uint16)
        else:  # 32
            data = img.astype(np.float32)
        
        # Determine photometric interpretation
        photometric = 'minisblack' if data.shape[-1] == 1 else 'rgb'
        
        tifffile.imwrite(path, data, photometric=photometric)

    def get_unique_filepath(self, base_path: str) -> str:
        """Get unique filepath with incremental counter"""
        if not os.path.exists(base_path):
            return base_path
        
        dir_name = os.path.dirname(base_path)
        base_name = os.path.basename(base_path)
        name, ext = os.path.splitext(base_name)
        
        counter = 1
        while True:
            new_path = os.path.join(dir_name, f"{name}_{counter}{ext}")
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def save_images(self, images, file_path, filename, file_type, bit_depth,
                   quality=95, save_as_grayscale=False, use_versioning=True,
                   version=1, prompt=None, extra_pnginfo=None, exr_compression="zips"):
        """Main save function with optimized pipeline"""
        try:
            # Validate inputs
            bit_depth = int(bit_depth)
            file_type = file_type.lower()
            bit_depth = self.validate_bit_depth(file_type, bit_depth)
            
            # Build base path
            if file_path:
                full_path = os.path.join(self.output_dir, file_path) if not os.path.isabs(file_path) else file_path
                os.makedirs(full_path, exist_ok=True)
                base_path = os.path.join(full_path, filename)
            else:
                base_path = os.path.join(self.output_dir, filename)
            
            # Add version string
            version_str = f"_v{version:03d}" if use_versioning and version >= 0 else ""
            
            # Process each image
            for i, img_tensor in enumerate(images):
                # Prepare image (all formats start from float32 [0,1])
                img_np = self.prepare_image(img_tensor, save_as_grayscale)
                
                # Build output path
                frame_str = f"_{i}" if len(images) > 1 else ""
                out_path = f"{base_path}{version_str}{frame_str}.{file_type}"
                out_path = self.get_unique_filepath(out_path)
                
                # Save based on format
                if file_type == "exr":
                    self.save_exr(img_np, out_path, bit_depth, exr_compression)
                elif file_type == "png":
                    self.save_png(img_np, out_path, bit_depth)
                elif file_type in ["jpg", "jpeg", "webp"]:
                    self.save_opencv_format(img_np, out_path, quality)
                elif file_type == "tiff":
                    self.save_tiff(img_np, out_path, bit_depth)
            
            return {"ui": {"images": []}}
            
        except Exception as e:
            return {"ui": {"error": str(e)}}

NODE_CLASS_MAPPINGS = {
    "saver": saver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "saver": "Image Saver"
}
