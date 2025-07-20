import os
import logging
import numpy as np
import torch
import json
import glob
import re
from typing import Tuple, Dict, List, Optional, Union, Any

try:
    import OpenImageIO as oiio
    OIIO_AVAILABLE = True
except ImportError:
    OIIO_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import debug utilities and modular preview utilities
try:
    from ..utils.debug_utils import debug_log, format_layer_names, format_tensor_info
    from ..utils.preview_utils import generate_preview_for_comfyui
except ImportError:
    # Fallback if utils not available
    def debug_log(logger, level, simple_msg, verbose_msg=None, **kwargs):
        getattr(logger, level.lower())(simple_msg)
    def format_layer_names(layer_names, max_simple=None):
        return ', '.join(layer_names)
    def format_tensor_info(tensor_shape, tensor_dtype, name=""):
        return f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}"
    def generate_preview_for_comfyui(image_tensor, source_path="", is_sequence=False, frame_index=0):
        return None

class load_exr:
    @classmethod
    def INPUT_TYPES(cls):
        # Define sequence-specific widgets
        sequence_widgets = {
            "sequence": [
                ["start_frame", "INT", {"default": 1001, "min": 0, "max": 999999}],
                ["frame_count", "INT", {"default": 1, "min": 1, "max": 1000}],
                ["frame_step", "INT", {"default": 1, "min": 1, "max": 100}]
            ]
        }
        
        return {
            "required": {
                "image_path": ("STRING", {
                    "default": "path/to/image.exr",
                    "description": "Full path to the EXR file or sequence pattern (use #### for frame numbers)"
                }),
                "image_type": (["single_frame", "sequence"], {
                    "default": "single_frame",
                    "description": "Load type: single frame or sequence",
                    "formats": sequence_widgets
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

    # Return types: RGB image, Alpha mask, Metadata string, Layer dictionary, Cryptomatte dictionary
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "LAYERS", "CRYPTOMATTE", "STRING", "STRING")
    RETURN_NAMES = ("image", "alpha", "metadata", "layers", "cryptomatte", "layer names", "processed layer names")
    
    FUNCTION = "load_image"
    CATEGORY = "Image/EXR"
    
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")  # Always execute the node

    def load_image(self, image_path: str, image_type: str = "single_frame", normalize: bool = False, 
                   start_frame: int = None, frame_count: int = None, frame_step: int = None,
                   node_id: str = None, layer_data: Dict = None, **kwargs) -> List:
        """
        Load an EXR image with support for multiple layers/channel groups.
        Returns:
        - Base RGB image tensor
        - Alpha channel tensor
        - Metadata as JSON string
        - Dictionary of all non-cryptomatte layers as tensors
        - Dictionary of all cryptomatte layers as tensors
        - List of raw channel names from the file
        - List of processed layer names matching keys in the returned dictionaries
        """
        
        # Check for OIIO availability
        if not OIIO_AVAILABLE:
            raise ImportError("OpenImageIO is required for EXR loading but not available")
            
        try:
            # Provide defaults for sequence parameters when missing
            if start_frame is None:
                start_frame = 1001
            if frame_count is None:
                frame_count = 1
            if frame_step is None:
                frame_step = 1
                
            # Determine loading mode based on image_type and pattern detection
            has_sequence_pattern = self._detect_sequence_pattern(image_path)
            
            # Force sequence mode if image_type is "sequence" OR if pattern detected
            is_sequence = (image_type == "sequence") or has_sequence_pattern
            
            if is_sequence:
                # Load as sequence
                return self._load_sequence(image_path, normalize, start_frame, frame_count, frame_step, node_id, layer_data)
            else:
                # Validate single image path
                if not os.path.isfile(image_path):
                    raise FileNotFoundError(f"Image not found: {image_path}")
                # Load as single image (existing behavior)
                return self._load_single_image(image_path, normalize, node_id, layer_data)
            
        except Exception as e:
            debug_log(logger, "error", "Error loading EXR", f"Error loading EXR file {image_path}: {str(e)}")
            raise

    def _detect_sequence_pattern(self, image_path: str) -> bool:
        """Detect if the image_path contains a sequence pattern (####)"""
        if not image_path or '####' not in image_path:
            return False
        
        # A sequence pattern is detected by the presence of ####
        # We don't need to check if files exist here, that's handled in _load_sequence
        return True

    def _find_sequence_files(self, pattern_path: str) -> List[str]:
        """Find all files matching the sequence pattern"""
        # Convert #### pattern to glob pattern
        glob_pattern = pattern_path.replace('####', '*')
        
        # Find all matching files
        matching_files = glob.glob(glob_pattern)
        
        # Filter to only include files that match the exact pattern (4 digits)
        regex_pattern = pattern_path.replace('####', r'(\d{4})')
        
        valid_files = []
        for file_path in matching_files:
            if re.match(regex_pattern.replace('\\', '\\\\'), file_path):
                valid_files.append(file_path)
        
        return sorted(valid_files)

    def _generate_frame_paths(self, pattern_path: str, start_frame: int, frame_count: int, frame_step: int) -> List[str]:
        """Generate list of frame paths based on pattern and parameters"""
        frame_paths = []
        
        for i in range(0, frame_count * frame_step, frame_step):
            frame_number = start_frame + i
            frame_path = pattern_path.replace('####', f'{frame_number:04d}')
            frame_paths.append(frame_path)
        
        return frame_paths

    def _load_sequence(self, pattern_path: str, normalize: bool, start_frame: int, frame_count: int, frame_step: int, node_id: str = None, layer_data: Dict = None) -> List:
        """Load a sequence of EXR files and return batched tensors"""
        debug_log(logger, "info", f"Loading EXR sequence: {frame_count} frames", 
                 f"Loading EXR sequence: {pattern_path} (start={start_frame}, count={frame_count}, step={frame_step})")
        
        # Generate frame paths
        frame_paths = self._generate_frame_paths(pattern_path, start_frame, frame_count, frame_step)
        
        # Check if files exist
        existing_frames = []
        for frame_path in frame_paths:
            if os.path.exists(frame_path):
                existing_frames.append(frame_path)
            else:
                debug_log(logger, "warning", "Frame not found", f"Frame not found: {frame_path}")
        
        if not existing_frames:
            raise FileNotFoundError(f"No sequence frames found for pattern: {pattern_path}")
        
        # Load first frame to establish structure
        first_frame_result = self._load_single_image(existing_frames[0], normalize, node_id, layer_data)
        
        # Handle result format (dict if preview generated, list if not)
        if isinstance(first_frame_result, dict):
            first_frame_data = first_frame_result["result"]
        else:
            first_frame_data = first_frame_result
        
        # Initialize batch tensors with first frame
        batch_rgb = first_frame_data[0]  # IMAGE
        batch_alpha = first_frame_data[1]  # MASK
        batch_layers = first_frame_data[3]  # LAYERS
        batch_cryptomatte = first_frame_data[4]  # CRYPTOMATTE
        
        # Convert single frame tensors to batch tensors
        batch_rgb_list = [batch_rgb]
        batch_alpha_list = [batch_alpha]
        batch_layers_dict = {}
        batch_cryptomatte_dict = {}
        
        # Initialize layer dictionaries
        for layer_name, layer_tensor in batch_layers.items():
            batch_layers_dict[layer_name] = [layer_tensor]
        
        for crypto_name, crypto_tensor in batch_cryptomatte.items():
            batch_cryptomatte_dict[crypto_name] = [crypto_tensor]
        
        # Load remaining frames
        for frame_path in existing_frames[1:]:
            try:
                frame_result = self._load_single_image(frame_path, normalize, node_id, layer_data)
                
                # Handle result format (dict if preview generated, list if not)
                if isinstance(frame_result, dict):
                    frame_data = frame_result["result"]
                else:
                    frame_data = frame_result
                
                # Add to batch lists
                batch_rgb_list.append(frame_data[0])
                batch_alpha_list.append(frame_data[1])
                
                # Add layers to batch
                frame_layers = frame_data[3]
                for layer_name, layer_tensor in frame_layers.items():
                    if layer_name in batch_layers_dict:
                        batch_layers_dict[layer_name].append(layer_tensor)
                    else:
                        debug_log(logger, "warning", "Layer not found in first frame", 
                                  f"Layer '{layer_name}' not found in first frame, skipping")
                
                # Add cryptomatte to batch
                frame_cryptomatte = frame_data[4]
                for crypto_name, crypto_tensor in frame_cryptomatte.items():
                    if crypto_name in batch_cryptomatte_dict:
                        batch_cryptomatte_dict[crypto_name].append(crypto_tensor)
                    else:
                        debug_log(logger, "warning", "Cryptomatte not found in first frame", 
                                  f"Cryptomatte '{crypto_name}' not found in first frame, skipping")
                        
            except Exception as e:
                debug_log(logger, "error", "Error loading frame", f"Error loading frame {frame_path}: {str(e)}")
                # Continue with other frames
                continue
        
        # Stack tensors into batches
        final_rgb = torch.cat(batch_rgb_list, dim=0)
        final_alpha = torch.cat(batch_alpha_list, dim=0)
        
        # Stack layer tensors
        final_layers = {}
        for layer_name, tensor_list in batch_layers_dict.items():
            if tensor_list:
                final_layers[layer_name] = torch.cat(tensor_list, dim=0)
        
        # Stack cryptomatte tensors
        final_cryptomatte = {}
        for crypto_name, tensor_list in batch_cryptomatte_dict.items():
            if tensor_list:
                final_cryptomatte[crypto_name] = torch.cat(tensor_list, dim=0)
        
        # Update metadata to include sequence info
        metadata_str = first_frame_data[2]
        metadata = json.loads(metadata_str) if metadata_str else {}
        metadata["sequence_info"] = {
            "is_sequence": True,
            "pattern": pattern_path,
            "start_frame": start_frame,
            "frame_count": len(existing_frames),
            "frame_step": frame_step,
            "loaded_frames": existing_frames
        }
        metadata_json = json.dumps(metadata)
        
        # Generate preview for sequence (first frame) at full resolution
        preview_result = generate_preview_for_comfyui(final_rgb, pattern_path, is_sequence=True, full_size=True)
        
        # Return same structure as single image
        result = [
            final_rgb,
            final_alpha, 
            metadata_json,
            final_layers,
            final_cryptomatte,
            first_frame_data[5],  # layer names
            first_frame_data[6]   # processed layer names
        ]
        
        # Return with preview if generated
        if preview_result:
            return {"ui": {"images": preview_result}, "result": result}
        else:
            return result

    def _load_single_image(self, image_path: str, normalize: bool, node_id: str = None, layer_data: Dict = None) -> List:
        """Load a single EXR image (original functionality)"""
        try:
            # Scan the EXR metadata if not already provided
            metadata = layer_data if layer_data else self.scan_exr_metadata(image_path)
            
            # Load all pixel data from all subimages
            all_subimage_data = self.load_all_data(image_path)
            
            # Dictionary to store all non-cryptomatte layers
            layers_dict = {}
            
            # Dictionary to store all cryptomatte layers
            cryptomatte_dict = {}
            
            # List to store all channel names from all subimages
            all_channel_names = []
            
            # Process each subimage
            for subimage_idx, subimage_info in enumerate(metadata["subimages"]):
                # Get subimage data
                if subimage_idx not in all_subimage_data:
                    debug_log(logger, "warning", "No subimage data", f"No data found for subimage {subimage_idx}")
                    continue
                
                subimage_data = all_subimage_data[subimage_idx]
                subimage_name = subimage_info["name"]
                channel_names = subimage_info["channel_names"]
                
                # Add channel names to the list
                all_channel_names.extend(channel_names)
                
                # Get dimensions
                height, width, channels = subimage_data.shape
                
                # Process the first subimage as the default RGB and Alpha
                if subimage_idx == 0:
                    # Extract channel groups for the first subimage
                    channel_groups = self._get_channel_groups(channel_names)
                    metadata["channel_groups"] = channel_groups
                    
                    # Process default RGB and Alpha channels
                    rgb_tensor, alpha_tensor = self._process_default_channels(
                        subimage_data, channel_names, height, width, normalize
                    )
                
                # For all subimages, add the subimage as a layer
                # Use the subimage name as the layer name
                if subimage_name != "default":
                    # For RGB subimages (3 or 4 channels)
                    if channels >= 3:
                        # Extract RGB channels
                        rgb_array = subimage_data[:, :, :3]
                        
                        # Convert to torch tensor
                        rgb_tensor_layer = torch.from_numpy(rgb_array).float()
                        rgb_tensor_layer = rgb_tensor_layer.unsqueeze(0)  # [1, H, W, 3]
                        
                        # Normalize if requested
                        if normalize:
                            rgb_range = rgb_tensor_layer.max() - rgb_tensor_layer.min()
                            if rgb_range > 0:
                                rgb_tensor_layer = (rgb_tensor_layer - rgb_tensor_layer.min()) / rgb_range
                        
                        # Store in layers dictionary
                        layers_dict[subimage_name] = rgb_tensor_layer
                        
                        # If there's an alpha channel, process it too
                        if channels >= 4:
                            alpha_array = subimage_data[:, :, 3]
                            
                            alpha_tensor_layer = torch.from_numpy(alpha_array).float()
                            alpha_tensor_layer = alpha_tensor_layer.unsqueeze(0)  # [1, H, W]
                            
                            if normalize:
                                alpha_tensor_layer = alpha_tensor_layer.clamp(0, 1)
                            
                            # Store alpha as a mask tensor
                            layers_dict[f"{subimage_name}_alpha"] = alpha_tensor_layer
                    
                    # For single-channel subimages
                    elif channels == 1:
                        # Extract the single channel
                        channel_array = subimage_data[:, :, 0]
                        
                        # Check if it's likely to be a mask/depth type channel
                        is_mask_type = any(keyword in subimage_name.lower() 
                                        for keyword in ['depth', 'mask', 'matte', 'alpha', 'id', 'z'])
                        
                        if is_mask_type or subimage_name == 'depth':  # Explicitly handle 'depth' subimage
                            # Store as a mask tensor
                            mask_tensor = torch.from_numpy(channel_array).float().unsqueeze(0)  # [1, H, W]
                            
                            if normalize:
                                mask_range = mask_tensor.max() - mask_tensor.min()
                                if mask_range > 0:
                                    mask_tensor = (mask_tensor - mask_tensor.min()) / mask_range
                            
                            # Ensure the mask tensor has valid data
                            if mask_tensor.numel() > 1:
                                layers_dict[subimage_name] = mask_tensor
                            else:
                                # Create a placeholder mask with proper dimensions
                                layers_dict[subimage_name] = torch.zeros((1, height, width))
                        else:
                            # Replicate to 3 channels for RGB visualization
                            rgb_array = np.stack([channel_array] * 3, axis=2)
                            
                            channel_tensor = torch.from_numpy(rgb_array).float()
                            channel_tensor = channel_tensor.unsqueeze(0)  # [1, H, W, 3]
                            
                            if normalize:
                                channel_range = channel_tensor.max() - channel_tensor.min()
                                if channel_range > 0:
                                    channel_tensor = (channel_tensor - channel_tensor.min()) / channel_range
                            
                            # Ensure the tensor has valid data
                            if channel_tensor.numel() > 3:
                                layers_dict[subimage_name] = channel_tensor
                            else:
                                # Create a placeholder RGB tensor with proper dimensions
                                layers_dict[subimage_name] = torch.zeros((1, height, width, 3))
                
                # Only process channel groups for the first subimage (main image)
                # For other subimages, we've already added them as layers above
                if subimage_idx == 0:
                    # Process channel groups within this subimage
                    channel_groups = self._get_channel_groups(channel_names)
                    
                    # Process each channel group in this subimage
                    for group_name, suffixes in channel_groups.items():
                        # Skip the default RGB/A which are already handled separately
                        if group_name in ('R', 'G', 'B', 'A', 'RGB', 'XYZ'):
                            continue
                        
                        # Skip layer group tracking entries (they're metadata, not actual layers)
                        if group_name.endswith('_layer_group'):
                            continue
                        
                        # Check if this is a cryptomatte layer
                        is_cryptomatte = self._is_cryptomatte_layer(group_name)
                        
                        # Find all channel indices for this group
                        group_indices = []
                        for i, channel in enumerate(channel_names):
                            # Match exact channel name or prefix with dot
                            if (channel == group_name) or (channel.startswith(f"{group_name}.")):
                                group_indices.append(i)
                        
                        if not group_indices:
                            continue
                        
                        # Determine layer type and process accordingly
                        
                        # Case 1: RGB/RGBA layer - standard naming with RGB or RGBA components
                        if all(suffix in suffixes for suffix in ['R', 'G', 'B']):
                            self._process_rgb_type_layer(
                                group_name, 'R', 'G', 'B', 'A', channel_names, subimage_data, 
                                normalize, is_cryptomatte, layers_dict, cryptomatte_dict
                            )
                        
                        # Case 2: Lower case rgb/rgba (common in some renderers like Blender Cycles)
                        elif all(suffix in suffixes for suffix in ['r', 'g', 'b']):
                            self._process_rgb_type_layer(
                                group_name, 'r', 'g', 'b', 'a', channel_names, subimage_data, 
                                normalize, is_cryptomatte, layers_dict, cryptomatte_dict
                            )
                        
                        # Case 3: XYZ vector channels (often used for normals, positions, velocity)
                        elif all(suffix in suffixes for suffix in ['X', 'Y', 'Z']):
                            self._process_xyz_type_layer(
                                group_name, 'X', 'Y', 'Z', channel_names, subimage_data, 
                                normalize, layers_dict
                            )
                                
                        # Case 4: Lower case xyz components (like N.x, N.y, N.z)
                        elif all(suffix in suffixes for suffix in ['x', 'y', 'z']):
                            self._process_xyz_type_layer(
                                group_name, 'x', 'y', 'z', channel_names, subimage_data, 
                                normalize, layers_dict
                            )
                        
                        # Case 5: Single-channel data (like depth maps, Z channel)
                        elif len(group_indices) == 1 or 'Z' in suffixes:
                            self._process_single_channel(
                                group_name, suffixes, group_indices, channel_names,
                                subimage_data, normalize, layers_dict
                            )
                        
                        # Case 6: Handle other multi-channel data that doesn't fit the patterns above
                        else:
                            self._process_multi_channel(
                                group_name, group_indices, subimage_data, normalize,
                                is_cryptomatte, layers_dict, cryptomatte_dict
                            )
            
            # Process layer groups from the first subimage (for backward compatibility)
            
            # Handle layer groups detected by _get_channel_groups
            self._process_layer_groups(
                channel_groups, cryptomatte_dict, metadata
            )
            
            # Store layer type information in metadata
            self._store_layer_type_metadata(layers_dict, metadata)
            
            # Add metadata as JSON string
            metadata_json = json.dumps(metadata)
            
            # Log the available layers
            debug_log(logger, "info", f"Loaded {len(layers_dict)} layers: {format_layer_names(list(layers_dict.keys()))}", 
                     f"Available EXR layers: {list(layers_dict.keys())}")
            if cryptomatte_dict:
                debug_log(logger, "info", f"Loaded {len(cryptomatte_dict)} cryptomatte layers", 
                         f"Available cryptomatte layers: {list(cryptomatte_dict.keys())}")
            
            # Create a readable list of channel names from all subimages
            layer_names = all_channel_names
            
            # Create a list of processed layer names that match the keys in the returned dictionaries
            processed_layer_names = self._create_processed_layer_names(layers_dict, cryptomatte_dict)
            
            # Generate preview for ComfyUI using modular system (full resolution)
            preview_result = generate_preview_for_comfyui(rgb_tensor, image_path, is_sequence=False, full_size=True)
            
            # Return the results
            result = [rgb_tensor, alpha_tensor, metadata_json, layers_dict, cryptomatte_dict, layer_names, processed_layer_names]
            
            # Return with preview if generated
            if preview_result:
                return {"ui": {"images": preview_result}, "result": result}
            else:
                return result
            
        except Exception as e:
            debug_log(logger, "error", "Error loading EXR", f"Error loading EXR file {image_path}: {str(e)}")
            raise

    def _is_cryptomatte_layer(self, group_name: str) -> bool:
        """Determine if a layer is a cryptomatte layer based on its name"""
        group_name_lower = group_name.lower()
        return (
            "cryptomatte" in group_name_lower or 
            group_name_lower.startswith("crypto") or
            any(crypto_key for crypto_key in ("cryptoasset", "cryptomaterial", "cryptoobject", "cryptoprimvar") 
                if crypto_key in group_name_lower) or
            # Handle hierarchical naming like "CITY SCENE.CryptoAsset00"
            any(part.lower().startswith("crypto") for part in group_name.split('.'))
        )

    def _process_default_channels(self, all_data, channel_names, height, width, normalize):
        """Process default RGB and Alpha channels"""
        # Default RGB output (first 3 channels if available)
        rgb_tensor = None
        if 'R' in channel_names and 'G' in channel_names and 'B' in channel_names:
            r_idx = channel_names.index('R')
            g_idx = channel_names.index('G')
            b_idx = channel_names.index('B')
            
            rgb_array = np.stack([
                all_data[:, :, r_idx],
                all_data[:, :, g_idx],
                all_data[:, :, b_idx]
            ], axis=2)
            
            rgb_tensor = torch.from_numpy(rgb_array).float()
            rgb_tensor = rgb_tensor.unsqueeze(0)  # [1, H, W, 3]
            
            if normalize:
                rgb_range = rgb_tensor.max() - rgb_tensor.min()
                if rgb_range > 0:
                    rgb_tensor = (rgb_tensor - rgb_tensor.min()) / rgb_range
        else:
            # If no RGB channels, use first 3 channels or create placeholder
            if all_data.shape[2] >= 3:
                rgb_array = all_data[:, :, :3]
            else:
                rgb_array = np.stack([all_data[:, :, 0]] * 3, axis=2)
            
            rgb_tensor = torch.from_numpy(rgb_array).float()
            rgb_tensor = rgb_tensor.unsqueeze(0)  # [1, H, W, 3]
            
            if normalize:
                rgb_range = rgb_tensor.max() - rgb_tensor.min()
                if rgb_range > 0:
                    rgb_tensor = (rgb_tensor - rgb_tensor.min()) / rgb_range
        
        # Default Alpha channel if available
        alpha_tensor = None
        if 'A' in channel_names:
            a_idx = channel_names.index('A')
            alpha_array = all_data[:, :, a_idx]
            
            alpha_tensor = torch.from_numpy(alpha_array).float()
            alpha_tensor = alpha_tensor.unsqueeze(0)  # [1, H, W]
            
            if normalize:
                alpha_tensor = alpha_tensor.clamp(0, 1)
        else:
            # If no alpha, create a tensor of ones
            alpha_tensor = torch.ones((1, height, width))
            
        return rgb_tensor, alpha_tensor

    def _process_rgb_type_layer(self, group_name, r_suffix, g_suffix, b_suffix, a_suffix, 
                               channel_names, all_data, normalize, is_cryptomatte, 
                               layers_dict, cryptomatte_dict):
        """Process RGB/RGBA type layers with various naming conventions"""
        try:
            # Find the RGB indices
            r_channel = f"{group_name}.{r_suffix}"
            g_channel = f"{group_name}.{g_suffix}"
            b_channel = f"{group_name}.{b_suffix}"
            a_channel = f"{group_name}.{a_suffix}"
            
            # Try to find the channels in the channel_names list
            try:
                r_idx = channel_names.index(r_channel)
                g_idx = channel_names.index(g_channel)
                b_idx = channel_names.index(b_channel)
            except ValueError:
                # If we can't find the channels, log a warning and return
                debug_log(logger, "warning", "Missing RGB channels", f"Could not find RGB channels for {group_name}")
                return
            
            # Check if there's also an alpha component
            has_alpha = False
            a_idx = -1
            try:
                a_idx = channel_names.index(a_channel)
                has_alpha = True
            except ValueError:
                pass
            
            # Stack RGB channels
            rgb_array = np.stack([
                all_data[:, :, r_idx],
                all_data[:, :, g_idx],
                all_data[:, :, b_idx]
            ], axis=2)
            
            # Convert to torch tensor
            rgb_tensor_layer = torch.from_numpy(rgb_array).float()
            rgb_tensor_layer = rgb_tensor_layer.unsqueeze(0)  # [1, H, W, 3]
            
            # Normalize if requested
            if normalize:
                rgb_range = rgb_tensor_layer.max() - rgb_tensor_layer.min()
                if rgb_range > 0:
                    rgb_tensor_layer = (rgb_tensor_layer - rgb_tensor_layer.min()) / rgb_range
            
            # Store in the appropriate dictionary
            if is_cryptomatte:
                cryptomatte_dict[group_name] = rgb_tensor_layer
            else:
                layers_dict[group_name] = rgb_tensor_layer
                
            # If this layer has alpha, process it as well
            if has_alpha:
                alpha_array = all_data[:, :, a_idx]
                
                alpha_tensor_layer = torch.from_numpy(alpha_array).float()
                alpha_tensor_layer = alpha_tensor_layer.unsqueeze(0)  # [1, H, W]
                
                if normalize:
                    alpha_tensor_layer = alpha_tensor_layer.clamp(0, 1)
                
                alpha_layer_name = f"{group_name}_alpha"
                layers_dict[alpha_layer_name] = alpha_tensor_layer
        except ValueError as e:
            # Handle missing channels gracefully
            debug_log(logger, "warning", "Error processing RGB layer", f"Error processing RGB layer {group_name}: {str(e)}")

    def _process_xyz_type_layer(self, group_name, x_suffix, y_suffix, z_suffix, 
                               channel_names, all_data, normalize, layers_dict):
        """Process XYZ type vector layers with various naming conventions"""
        try:
            # Find the XYZ indices
            x_channel = f"{group_name}.{x_suffix}"
            y_channel = f"{group_name}.{y_suffix}"
            z_channel = f"{group_name}.{z_suffix}"
            
            # Try to find the channels in the channel_names list
            try:
                x_idx = channel_names.index(x_channel)
                y_idx = channel_names.index(y_channel)
                z_idx = channel_names.index(z_channel)
            except ValueError:
                # If we can't find the channels, log a warning and return
                debug_log(logger, "warning", "Missing XYZ channels", f"Could not find XYZ channels for {group_name}")
                return
            
            # Stack XYZ channels as RGB
            xyz_array = np.stack([
                all_data[:, :, x_idx],
                all_data[:, :, y_idx],
                all_data[:, :, z_idx]
            ], axis=2)
            
            xyz_tensor = torch.from_numpy(xyz_array).float()
            xyz_tensor = xyz_tensor.unsqueeze(0)  # [1, H, W, 3]
            
            # For vector data, normalize differently if requested
            if normalize:
                # Normalize based on the maximum absolute value to preserve vector directions
                max_abs = xyz_tensor.abs().max()
                if max_abs > 0:
                    xyz_tensor = xyz_tensor / max_abs
            
            # Store in the layers dictionary (vector data won't be cryptomatte)
            layers_dict[group_name] = xyz_tensor
        except ValueError as e:
            debug_log(logger, "warning", "Error processing XYZ layer", f"Error processing XYZ layer {group_name}: {str(e)}")

    def _process_single_channel(self, group_name, suffixes, group_indices, 
                               channel_names, all_data, normalize, layers_dict):
        """Process single channel data like depth maps or Z channels"""
        # Find the channel index
        idx = -1
        if 'Z' in suffixes:
            z_channel = f"{group_name}.Z"
            z_channel_lower = f"{group_name}.z"
            try:
                idx = channel_names.index(z_channel)
            except ValueError:
                # Try with lowercase z
                try:
                    idx = channel_names.index(z_channel_lower)
                except ValueError:
                    # Just use the first index
                    idx = group_indices[0]
        else:
            idx = group_indices[0]
        
        if idx >= 0:
            # Extract the single channel
            channel_array = all_data[:, :, idx]
            
            # Check if it's likely to be a mask/depth type channel
            is_mask_type = any(keyword in group_name.lower() 
                               for keyword in ['depth', 'mask', 'matte', 'alpha', 'id', 'z'])
            
            # Special case for Z channel
            if group_name == 'Z':
                is_mask_type = True
                debug_log(logger, "info", "Processing Z channel as mask", 
                         f"Processing Z channel as mask: shape={channel_array.shape}")
            
            if is_mask_type:
                # Store as a mask tensor
                mask_tensor = torch.from_numpy(channel_array).float().unsqueeze(0)  # [1, H, W]
                
                if normalize:
                    mask_range = mask_tensor.max() - mask_tensor.min()
                    if mask_range > 0:
                        mask_tensor = (mask_tensor - mask_tensor.min()) / mask_range
                
                # Log mask tensor stats
                debug_log(logger, "info", f"Created mask: {format_tensor_info(mask_tensor.shape, mask_tensor.dtype, group_name)}", 
                         f"Created mask tensor for {group_name}: shape={mask_tensor.shape}, " +
                         f"min={mask_tensor.min().item():.6f}, max={mask_tensor.max().item():.6f}, " +
                         f"mean={mask_tensor.mean().item():.6f}")
                
                layers_dict[group_name] = mask_tensor
            else:
                # Replicate to 3 channels for RGB visualization
                rgb_array = np.stack([channel_array] * 3, axis=2)
                
                channel_tensor = torch.from_numpy(rgb_array).float()
                channel_tensor = channel_tensor.unsqueeze(0)  # [1, H, W, 3]
                
                if normalize:
                    channel_range = channel_tensor.max() - channel_tensor.min()
                    if channel_range > 0:
                        channel_tensor = (channel_tensor - channel_tensor.min()) / channel_range
                
                # Log RGB tensor stats
                debug_log(logger, "info", f"Created RGB: {format_tensor_info(channel_tensor.shape, channel_tensor.dtype, group_name)}", 
                         f"Created RGB tensor for {group_name}: shape={channel_tensor.shape}, " +
                         f"min={channel_tensor.min().item():.6f}, max={channel_tensor.max().item():.6f}, " +
                         f"mean={channel_tensor.mean().item():.6f}")
                
                layers_dict[group_name] = channel_tensor

    def _process_multi_channel(self, group_name, group_indices, all_data, normalize,
                              is_cryptomatte, layers_dict, cryptomatte_dict):
        """Process multi-channel data that doesn't fit standard patterns"""
        # Create a representation based on available channels (up to 3)
        channels_to_use = min(3, len(group_indices))
        array_channels = []
        
        for i in range(channels_to_use):
            array_channels.append(all_data[:, :, group_indices[i]])
        
        # If we have fewer than 3 channels, duplicate the last one
        while len(array_channels) < 3:
            array_channels.append(array_channels[-1])
        
        # Stack the channels
        multi_array = np.stack(array_channels, axis=2)
        
        multi_tensor = torch.from_numpy(multi_array).float()
        multi_tensor = multi_tensor.unsqueeze(0)  # [1, H, W, 3]
        
        if normalize:
            multi_range = multi_tensor.max() - multi_tensor.min()
            if multi_range > 0:
                multi_tensor = (multi_tensor - multi_tensor.min()) / multi_range
        
        # Store in the appropriate dictionary
        if is_cryptomatte:
            cryptomatte_dict[group_name] = multi_tensor
        else:
            layers_dict[group_name] = multi_tensor

    def _process_layer_groups(self, channel_groups, cryptomatte_dict, metadata):
        """Process groups of related layers (like cryptomatte layer groups)"""
        for group_name, suffixes in channel_groups.items():
            if not group_name.endswith('_layer_group'):
                continue
            
            # Get the base name (without _layer_group)
            base_name = group_name[:-12]  # Remove '_layer_group'
            
            # Skip if we don't have any items in the layer group
            if not suffixes:
                continue
            
            # Check if this is a cryptomatte layer group
            is_crypto_layer_group = self._is_cryptomatte_layer(base_name)
            
            # If any part of the layer group is already in the cryptomatte dict, keep it there
            in_crypto_dict = any(group_part in cryptomatte_dict for group_part in suffixes)
            
            # Store information about this layer group in metadata
            if 'layer_groups' not in metadata:
                metadata['layer_groups'] = {}
            
            metadata['layer_groups'][base_name] = suffixes
            
            # If this is a cryptomatte layer group, make it accessible through the cryptomatte dict
            if is_crypto_layer_group or in_crypto_dict:
                # Add a reference to the layer group in the cryptomatte dict
                cryptomatte_dict[group_name] = [cryptomatte_dict.get(part, None) for part in suffixes]

    def _store_layer_type_metadata(self, layers_dict, metadata):
        """Store information about layer types in metadata"""
        layer_types = {}
        for layer_name, tensor in layers_dict.items():
            if len(tensor.shape) >= 4 and tensor.shape[3] == 3:  # It has 3 channels
                layer_types[layer_name] = "IMAGE"
            else:
                layer_types[layer_name] = "MASK"
        
        metadata["layer_types"] = layer_types

    def _create_processed_layer_names(self, layers_dict, cryptomatte_dict):
        """Create a sorted list of processed layer names"""
        processed_layer_names = []
        
        # Add standard layer names
        for layer_name in layers_dict.keys():
            processed_layer_names.append(layer_name)
        
        # Add cryptomatte layer names
        for crypto_name in cryptomatte_dict.keys():
            processed_layer_names.append(f"crypto:{crypto_name}")
            
        # Sort the layer names for consistency
        processed_layer_names.sort()
        
        return processed_layer_names

    def _get_channel_groups(self, channel_names: List[str]) -> Dict[str, List[str]]:
        """
        Group channel names by their prefix (before the dot).
        Returns a dictionary of groups with their respective channel suffixes.
        
        This method handles complex naming schemes including:
        - Standard RGB/XYZ channels
        - Cryptomatte layers and layer groups (like CryptoAsset00, CryptoMaterial00)
        - Depth channels with various naming conventions
        - Layer groups of related layers (e.g., segmentation, segmentation00, segmentation01)
        - Hierarchical naming with multiple dots (e.g., "CITY SCENE.AO.R")
        """
        groups = {}
        # Track groups of numbered layers (like layer00, layer01, etc.)
        layer_group_prefixes = set()
        
        # First pass: identify all channel groups and detect layer groups
        for channel in channel_names:
            # Handle channels with dots (indicating a group)
            if '.' in channel:
                # Handle hierarchical naming with multiple dots
                # For channels like "CITY SCENE.AO.R", we want to group by "CITY SCENE.AO"
                parts = channel.split('.')
                
                # If we have a hierarchical structure with more than 2 parts
                if len(parts) > 2:
                    # For channels like "CITY SCENE.AO.R", use "CITY SCENE.AO" as the prefix
                    # and "R" as the suffix
                    prefix = '.'.join(parts[:-1])
                    suffix = parts[-1]
                else:
                    # For standard channels like "diffuse.R", use "diffuse" as the prefix
                    # and "R" as the suffix
                    prefix, suffix = channel.split('.', 1)
                
                # Check for numbered layer group items (e.g., binary_segmentation00)
                base_prefix = prefix
                if any(prefix.endswith(f"{i:02d}") for i in range(10)):
                    # Extract the base name without the number
                    for i in range(10):
                        if prefix.endswith(f"{i:02d}"):
                            base_prefix = prefix[:-2]
                            layer_group_prefixes.add(base_prefix)
                            break
                
                # Add to the appropriate group
                if prefix not in groups:
                    groups[prefix] = []
                groups[prefix].append(suffix)
            else:
                # For channels without dots (like R, G, B, Z), use them as their own group
                if channel not in groups:
                    groups[channel] = []
                groups[channel].append(None)
                
                # Check for special case of single-letter channels that might be part of a group
                if len(channel) == 1 and channel in 'RGBAXYZ':
                    # These might be ungrouped RGB or XYZ channels, create a virtual group
                    if all(c in channel_names for c in 'RGB'):
                        if 'RGB' not in groups:
                            groups['RGB'] = []
                        # Don't add now, we'll handle this in second pass
                    elif all(c in channel_names for c in 'XYZ'):
                        if 'XYZ' not in groups:
                            groups['XYZ'] = []
                        # Don't add now, we'll handle this in second pass
        
        # Second pass: further processing for special cases
        
        # Handle top-level RGB channels if they exist
        if all(c in channel_names for c in 'RGB'):
            groups['RGB'] = ['R', 'G', 'B']
        
        # Handle top-level XYZ channels if they exist
        if all(c in channel_names for c in 'XYZ'):
            groups['XYZ'] = ['X', 'Y', 'Z']
        
        # Handle top-level depth channels (Z, zDepth, depth.Z)
        depth_channels = [c for c in channel_names if c in ('Z', 'zDepth', 'zDepth1') or 
                          (('depth' in c.lower() or 'z' in c.lower()) and not '.' in c)]
        if depth_channels:
            if 'Depth' not in groups:
                groups['Depth'] = []
            for dc in depth_channels:
                groups['Depth'].append(dc)
        
        # Handle cryptomatte layer groups - look for patterns like CryptoAsset00, CryptoMaterial00
        crypto_prefixes = set()
        for prefix in groups.keys():
            if ('crypto' in prefix.lower() or prefix.startswith('Crypto')):
                base_name = prefix
                if any(prefix.endswith(f"{i:02d}") for i in range(10)):
                    for i in range(10):
                        if prefix.endswith(f"{i:02d}"):
                            base_name = prefix[:-2]
                            crypto_prefixes.add(base_name)
                            break
        
        # Group the cryptomatte layer groups together in the metadata for easier processing
        for crypto_base in crypto_prefixes:
            # Add an entry to track this cryptomatte layer group
            if f"{crypto_base}_layer_group" not in groups:
                groups[f"{crypto_base}_layer_group"] = []
            
            # Find all indices in the layer group
            indices = []
            for i in range(10):  # Assume max 10 indices in layer group
                group_name = f"{crypto_base}{i:02d}"
                if group_name in groups:
                    indices.append(i)
                    groups[f"{crypto_base}_layer_group"].append(group_name)
        
        # Same for other detected layer groups (segmentation00, segmentation01, etc.)
        for group_base in layer_group_prefixes:
            if group_base in crypto_prefixes:
                continue  # Already handled above
                
            # Add an entry to track this layer group
            if f"{group_base}_layer_group" not in groups:
                groups[f"{group_base}_layer_group"] = []
            
            # Find all indices in the layer group
            for i in range(10):  # Assume max 10 indices in layer group
                group_name = f"{group_base}{i:02d}"
                if group_name in groups:
                    groups[f"{group_base}_layer_group"].append(group_name)
        
        return groups

    def load_all_data(self, image_path: str) -> Dict[int, np.ndarray]:
        """
        Load all pixel data from all subimages in the EXR file.
        Returns a dictionary mapping subimage index to numpy array of shape (height, width, channels).
        """
        input_file = None
        try:
            input_file = oiio.ImageInput.open(image_path)
            if not input_file:
                raise IOError(f"Could not open {image_path}")
            
            # Dictionary to store data for each subimage
            all_subimage_data = {}
            
            # Iterate through all subimages
            current_subimage = 0
            more_subimages = True
            
            while more_subimages:
                # Get specs for current subimage
                spec = input_file.spec()
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                
                # Read pixel data for current subimage
                pixels = input_file.read_image()
                if pixels is None:
                    debug_log(logger, "warning", "Failed to read subimage", 
                             f"Failed to read image data for subimage {current_subimage} from {image_path}")
                else:
                    # Convert to numpy array with correct shape
                    all_subimage_data[current_subimage] = np.array(pixels, dtype=np.float32).reshape(height, width, channels)
                
                # Move to next subimage if available
                more_subimages = input_file.seek_subimage(current_subimage + 1, 0)
                current_subimage += 1
            
            return all_subimage_data
            
        finally:
            if input_file:
                input_file.close()

    def scan_exr_metadata(self, image_path: str) -> Dict[str, Any]:
        """
        Scan the EXR file to extract metadata about available subimages without loading pixel data.
        Returns a dictionary of subimage information including names, channels, dimensions, etc.
        """
        if not OIIO_AVAILABLE:
            raise ImportError("OpenImageIO not installed. Cannot load EXR files.")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"EXR file not found: {image_path}")
            
        input_file = None
        try:
            # Open the image
            input_file = oiio.ImageInput.open(image_path)
            if not input_file:
                raise IOError(f"Could not open {image_path}")
                
            metadata = {}
            subimages = []
            
            # Iterate through all subimages (layers) in the EXR
            current_subimage = 0
            more_subimages = True
            
            while more_subimages:
                # Read the spec for current subimage
                spec = input_file.spec()
                
                # Extract basic information
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                channel_names = [spec.channel_name(i) for i in range(channels)]
                
                # Get subimage name if available
                subimage_name = "default"
                if "name" in spec.extra_attribs:
                    subimage_name = spec.getattribute("name")
                
                # Store subimage information
                subimage_info = {
                    "index": current_subimage,
                    "name": subimage_name,
                    "width": width,
                    "height": height,
                    "channels": channels,
                    "channel_names": channel_names
                }
                
                # Extract any additional metadata
                extra_attribs = {}
                for i in range(len(spec.extra_attribs)):
                    name = spec.extra_attribs[i].name
                    value = spec.extra_attribs[i].value
                    extra_attribs[name] = value
                
                subimage_info["extra_attributes"] = extra_attribs
                subimages.append(subimage_info)
                
                # Move to next subimage if available
                more_subimages = input_file.seek_subimage(current_subimage + 1, 0)
                current_subimage += 1
            
            metadata["subimages"] = subimages
            metadata["is_multipart"] = len(subimages) > 1
            metadata["subimage_count"] = len(subimages)
            metadata["file_path"] = image_path
            
            return metadata
            
        except Exception as e:
            debug_log(logger, "error", "Error scanning EXR metadata", f"Error scanning EXR metadata from {image_path}: {str(e)}")
            raise
            
        finally:
            if input_file:
                input_file.close()

    # Removed old preview generation method - now using modular system

NODE_CLASS_MAPPINGS = {
    "load_exr": load_exr
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "load_exr": "Load EXR"
}
