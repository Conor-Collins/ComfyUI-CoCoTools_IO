"""
Batch processing utilities for COCO Tools nodes
Provides shared functionality for handling tensor batch operations
"""

import torch
import numpy as np
import logging
from typing import Tuple, Union, Optional

logger = logging.getLogger(__name__)

try:
    from .debug_utils import debug_log, format_tensor_info
except ImportError:
    def debug_log(logger, level, simple_msg, verbose_msg=None, **kwargs):
        getattr(logger, level.lower())(simple_msg)
    def format_tensor_info(tensor_shape, tensor_dtype, name=""):
        return f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}"


class BatchProcessor:
    """Utility class for batch tensor operations"""
    
    @staticmethod
    def validate_batch_tensor(tensor: torch.Tensor, expected_dims: int = 4, 
                            tensor_name: str = "input") -> Tuple[int, int, int, int]:
        """
        Validate and extract batch tensor dimensions
        
        Args:
            tensor: Input tensor to validate
            expected_dims: Expected number of dimensions (default 4 for [B,H,W,C])
            tensor_name: Name for error messages
            
        Returns:
            Tuple of (batch_size, height, width, channels)
            
        Raises:
            ValueError: If tensor doesn't match expected format
        """
        if len(tensor.shape) != expected_dims:
            raise ValueError(f"Expected {expected_dims}D {tensor_name} tensor, got {len(tensor.shape)}D with shape {tensor.shape}")
        
        if expected_dims == 4:
            batch_size, height, width, channels = tensor.shape
            debug_log(logger, "debug", f"Validated {tensor_name}: B={batch_size}, H={height}, W={width}, C={channels}",
                     f"Validated {tensor_name} tensor: batch_size={batch_size}, height={height}, width={width}, channels={channels}")
            return batch_size, height, width, channels
        else:
            raise NotImplementedError(f"Validation for {expected_dims}D tensors not implemented")
    
    @staticmethod
    def reshape_for_processing(tensor: torch.Tensor, preserve_alpha: bool = True) -> Tuple[np.ndarray, Optional[np.ndarray], Tuple]:
        """
        Reshape batch tensor for element-wise processing (like colorspace conversion)
        
        Args:
            tensor: Input tensor [B, H, W, C]
            preserve_alpha: Whether to separate alpha channel (for RGBA inputs)
            
        Returns:
            Tuple of (reshaped_rgb, alpha_channel_or_none, original_shape)
        """
        # Convert to numpy and store original shape
        img_np = tensor.cpu().numpy()
        original_shape = img_np.shape
        batch_size, height, width, channels = original_shape
        
        debug_log(logger, "debug", f"Reshaping for processing: {format_tensor_info(original_shape, img_np.dtype)}",
                 f"Reshaping tensor from {original_shape} for batch processing")
        
        # Reshape to [B*H*W, C] for element-wise processing
        reshaped = img_np.reshape(-1, channels)
        
        alpha_channel = None
        if preserve_alpha and channels == 4:
            # Separate alpha channel
            alpha_channel = reshaped[..., 3:4]
            rgb_data = reshaped[..., :3]
            debug_log(logger, "debug", "Separated alpha channel", 
                     f"Separated alpha channel: RGB shape={rgb_data.shape}, Alpha shape={alpha_channel.shape}")
            return rgb_data, alpha_channel, original_shape
        elif channels != 3 and not preserve_alpha:
            # Handle non-RGB channels
            if channels == 1:
                # Replicate single channel to RGB
                rgb_data = np.repeat(reshaped, 3, axis=-1)
                debug_log(logger, "debug", "Replicated single channel to RGB",
                         f"Replicated single channel to RGB: {rgb_data.shape}")
            elif channels > 3:
                # Take first 3 channels
                rgb_data = reshaped[..., :3]
                debug_log(logger, "debug", f"Truncated to RGB from {channels} channels",
                         f"Truncated from {channels} channels to RGB: {rgb_data.shape}")
            else:
                # Pad to 3 channels
                padding = np.zeros((reshaped.shape[0], 3 - channels))
                rgb_data = np.concatenate([reshaped, padding], axis=-1)
                debug_log(logger, "debug", f"Padded {channels} channels to RGB",
                         f"Padded from {channels} channels to RGB: {rgb_data.shape}")
            return rgb_data, None, original_shape
        else:
            return reshaped, None, original_shape
    
    @staticmethod
    def reshape_from_processing(processed_rgb: np.ndarray, alpha_channel: Optional[np.ndarray], 
                              original_shape: Tuple, target_device: torch.device) -> torch.Tensor:
        """
        Reshape processed data back to original batch format
        
        Args:
            processed_rgb: Processed RGB data [B*H*W, 3]
            alpha_channel: Optional alpha channel [B*H*W, 1] 
            original_shape: Original tensor shape (B, H, W, C)
            target_device: Device to place result tensor on
            
        Returns:
            Reshaped tensor [B, H, W, C]
        """
        batch_size, height, width, original_channels = original_shape
        
        # Reshape RGB back to batch dimensions
        rgb_reshaped = processed_rgb.reshape(batch_size, height, width, 3)
        
        # Reattach alpha if present
        if alpha_channel is not None:
            alpha_reshaped = alpha_channel.reshape(batch_size, height, width, 1)
            final_array = np.concatenate([rgb_reshaped, alpha_reshaped], axis=-1)
            debug_log(logger, "debug", "Reattached alpha channel",
                     f"Reattached alpha channel: final shape={final_array.shape}")
        else:
            final_array = rgb_reshaped
        
        # Convert back to torch tensor
        result_tensor = torch.from_numpy(final_array).to(target_device)
        
        debug_log(logger, "debug", f"Reshaped back to batch: {format_tensor_info(result_tensor.shape, result_tensor.dtype)}",
                 f"Reshaped processed data back to batch format: {result_tensor.shape}")
        
        return result_tensor
    
    @staticmethod
    def normalize_batch_range(tensor: torch.Tensor, target_min: float = 0.0, target_max: float = 1.0,
                            source_min: Optional[float] = None, source_max: Optional[float] = None) -> torch.Tensor:
        """
        Normalize batch tensor values to target range
        
        Args:
            tensor: Input tensor to normalize
            target_min: Target minimum value
            target_max: Target maximum value  
            source_min: Source minimum (if None, use tensor.min())
            source_max: Source maximum (if None, use tensor.max())
            
        Returns:
            Normalized tensor
        """
        if source_min is None:
            source_min = tensor.min().item()
        if source_max is None:
            source_max = tensor.max().item()
        
        debug_log(logger, "debug", f"Normalizing range: [{source_min:.6f}, {source_max:.6f}] -> [{target_min:.6f}, {target_max:.6f}]",
                 f"Batch normalization: source range [{source_min:.6f}, {source_max:.6f}] to target range [{target_min:.6f}, {target_max:.6f}]")
        
        # Avoid division by zero
        if source_max == source_min:
            debug_log(logger, "warning", "Source range is zero, returning target_min",
                     f"Source min/max are equal ({source_min}), returning constant value {target_min}")
            return torch.full_like(tensor, target_min)
        
        # Normalize to [0,1] then scale to target range
        normalized = (tensor - source_min) / (source_max - source_min)
        scaled = normalized * (target_max - target_min) + target_min
        
        return scaled
    
    @staticmethod
    def log_batch_info(tensor: torch.Tensor, operation: str, tensor_name: str = "tensor"):
        """
        Log information about a batch tensor
        
        Args:
            tensor: Tensor to log info about
            operation: Operation being performed
            tensor_name: Name of the tensor for logging
        """
        if len(tensor.shape) == 4:
            batch_size = tensor.shape[0]
            debug_log(logger, "info", f"{operation}: {batch_size} images, {format_tensor_info(tensor.shape, tensor.dtype, tensor_name)}",
                     f"{operation} - Batch processing {batch_size} images: {tensor_name} {format_tensor_info(tensor.shape, tensor.dtype)} " +
                     f"range=[{tensor.min().item():.6f}, {tensor.max().item():.6f}]")
        else:
            debug_log(logger, "info", f"{operation}: {format_tensor_info(tensor.shape, tensor.dtype, tensor_name)}",
                     f"{operation} - Processing {tensor_name}: {format_tensor_info(tensor.shape, tensor.dtype)} " +
                     f"range=[{tensor.min().item():.6f}, {tensor.max().item():.6f}]")


# Convenience functions for common operations
def validate_4d_batch(tensor: torch.Tensor, name: str = "input") -> Tuple[int, int, int, int]:
    """Convenience function for 4D batch validation"""
    return BatchProcessor.validate_batch_tensor(tensor, 4, name)

def log_batch_processing(tensor: torch.Tensor, operation: str, name: str = "tensor"):
    """Convenience function for batch logging"""
    BatchProcessor.log_batch_info(tensor, operation, name)