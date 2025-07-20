"""
Preview utilities for COCO Tools nodes
Provides standardized preview generation for ComfyUI nodes
"""

import os
import uuid
import logging
import tempfile
import numpy as np
import torch
from typing import List, Dict, Optional, Union, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


class PreviewGenerator:
    """Standardized preview generator for ComfyUI nodes"""
    
    def __init__(self, max_preview_size: int = 1024, enable_full_size: bool = False):
        self.max_preview_size = max_preview_size
        self.enable_full_size = enable_full_size
        self.temp_dir = None
        self._init_temp_dir()
    
    def _init_temp_dir(self):
        """Initialize ComfyUI temp directory"""
        try:
            import folder_paths
            self.temp_dir = folder_paths.get_temp_directory()
        except ImportError:
            # Fallback if not in ComfyUI environment
            self.temp_dir = tempfile.gettempdir()
            logger.warning("folder_paths not available, using system temp directory")
    
    def generate_preview_for_comfyui(self, image_tensor: torch.Tensor, 
                                   source_path: str = "", 
                                   is_sequence: bool = False,
                                   frame_index: int = 0,
                                   full_size: bool = False) -> Optional[List[Dict]]:
        """
        Generate preview image for ComfyUI
        
        Args:
            image_tensor: Tensor with shape [batch, height, width, channels]
            source_path: Original file path (for generating unique names)
            is_sequence: Whether this is from a sequence
            frame_index: Frame index for sequences
            full_size: Whether to generate full resolution preview
            
        Returns:
            List of preview data dicts for ComfyUI UI
        """
        try:
            if not self.temp_dir:
                return None
            
            # Override instance setting if full_size is explicitly requested
            original_full_size = self.enable_full_size
            if full_size:
                self.enable_full_size = True
                
            # Handle sequence vs single image
            if is_sequence and image_tensor.shape[0] > 1:
                # For sequences, use specified frame or first frame
                preview_tensor = image_tensor[min(frame_index, image_tensor.shape[0] - 1)]
            else:
                # For single images, use first (and only) frame
                preview_tensor = image_tensor[0]
            
            # Convert tensor to PIL Image
            pil_image = self._tensor_to_pil(preview_tensor)
            if pil_image is None:
                return None
            
            # Resize to preview size
            pil_image = self._resize_for_preview(pil_image)
            
            # Generate unique filename
            preview_filename = self._generate_preview_filename(source_path, is_sequence, frame_index)
            preview_path = os.path.join(self.temp_dir, preview_filename)
            
            # Save preview image with quality settings
            if self.enable_full_size:
                # Use highest quality for full resolution previews - no compression limit
                pil_image.save(preview_path, format='PNG', optimize=False, compress_level=0)
            else:
                # Standard quality for thumbnails
                pil_image.save(preview_path, format='PNG', optimize=True, compress_level=6)
            
            # Create preview data structure for ComfyUI
            preview_data = [{
                "filename": preview_filename,
                "subfolder": "",
                "type": "temp"
            }]
            
            sequence_info = " (sequence)" if is_sequence else ""
            size_info = f"{pil_image.width}x{pil_image.height}"
            full_size_info = " (full resolution)" if self.enable_full_size else " (thumbnail)"
            logger.info(f"Generated preview{sequence_info}{full_size_info} {size_info}: {preview_filename}")
            
            return preview_data
            
        except Exception as e:
            logger.warning(f"Failed to generate preview for {source_path}: {e}")
            return None
        finally:
            # Restore original full_size setting
            if full_size:
                self.enable_full_size = original_full_size
    
    def _tensor_to_pil(self, tensor: torch.Tensor) -> Optional[Image.Image]:
        """Convert tensor to PIL Image"""
        try:
            # Convert tensor to numpy array
            if tensor.dim() == 3:  # [H, W, C]
                image_array = tensor.cpu().numpy()
            else:
                logger.warning(f"Unexpected tensor shape: {tensor.shape}")
                return None
            
            # Ensure float32 and [0,1] range
            image_array = np.clip(image_array, 0, 1).astype(np.float32)
            
            # Convert to [0,255] uint8
            image_array = (image_array * 255).clip(0, 255).astype(np.uint8)
            
            # Handle different channel counts
            if image_array.shape[2] == 1:
                # Grayscale
                image_array = image_array.squeeze(2)
                return Image.fromarray(image_array, mode='L')
            elif image_array.shape[2] == 3:
                # RGB
                return Image.fromarray(image_array, mode='RGB')
            elif image_array.shape[2] == 4:
                # RGBA
                return Image.fromarray(image_array, mode='RGBA')
            else:
                # Use first 3 channels
                return Image.fromarray(image_array[:, :, :3], mode='RGB')
                
        except Exception as e:
            logger.warning(f"Failed to convert tensor to PIL: {e}")
            return None
    
    def _resize_for_preview(self, pil_image: Image.Image) -> Image.Image:
        """Resize image for preview while maintaining aspect ratio"""
        # If full size is enabled, never resize - preserve original resolution
        if self.enable_full_size:
            return pil_image
        
        # Standard resize logic for thumbnail mode
        if pil_image.width <= self.max_preview_size and pil_image.height <= self.max_preview_size:
            return pil_image
        
        # Calculate new size maintaining aspect ratio
        ratio = min(self.max_preview_size / pil_image.width, 
                   self.max_preview_size / pil_image.height)
        new_width = int(pil_image.width * ratio)
        new_height = int(pil_image.height * ratio)
        
        return pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def _generate_preview_filename(self, source_path: str, is_sequence: bool, frame_index: int) -> str:
        """Generate unique preview filename"""
        # Create hash from source path
        file_hash = abs(hash(source_path)) % 1000000
        
        # Add sequence info
        seq_info = f"_seq_f{frame_index:04d}" if is_sequence else ""
        
        # Generate unique ID
        unique_id = uuid.uuid4().hex[:8]
        
        return f"coco_preview_{file_hash}{seq_info}_{unique_id}.png"
    
    def generate_saver_preview(self, saved_files: List[Dict], 
                             images: torch.Tensor) -> Optional[List[Dict]]:
        """
        Generate preview for saver nodes showing saved files
        
        Args:
            saved_files: List of saved file info
            images: Original images tensor
            
        Returns:
            Preview data for ComfyUI UI
        """
        try:
            if not saved_files or images.shape[0] == 0:
                return None
            
            # Use first image for preview
            preview_data = self.generate_preview_for_comfyui(
                images, 
                source_path=f"saver_{len(saved_files)}_files",
                is_sequence=len(saved_files) > 1
            )
            
            return preview_data
            
        except Exception as e:
            logger.warning(f"Failed to generate saver preview: {e}")
            return None


# Global preview generator instance with full size enabled
preview_generator = PreviewGenerator(max_preview_size=1024, enable_full_size=True)


def generate_preview_for_comfyui(image_tensor: torch.Tensor, 
                               source_path: str = "", 
                               is_sequence: bool = False,
                               frame_index: int = 0,
                               full_size: bool = False) -> Optional[List[Dict]]:
    """Convenience function for generating ComfyUI previews"""
    # Create a temporary generator with full size if requested
    if full_size:
        temp_generator = PreviewGenerator(enable_full_size=True)
        return temp_generator.generate_preview_for_comfyui(
            image_tensor, source_path, is_sequence, frame_index
        )
    else:
        return preview_generator.generate_preview_for_comfyui(
            image_tensor, source_path, is_sequence, frame_index
        )


def generate_saver_preview(saved_files: List[Dict], 
                         images: torch.Tensor) -> Optional[List[Dict]]:
    """Convenience function for generating saver previews"""
    return preview_generator.generate_saver_preview(saved_files, images)