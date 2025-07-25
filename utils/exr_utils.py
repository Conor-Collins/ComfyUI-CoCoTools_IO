"""
EXR utility functions for COCO Tools nodes
Provides shared functionality for EXR file processing across loader nodes
"""

import os
import logging
import numpy as np
import torch
import json
from typing import Tuple, Dict, List, Optional, Union, Any

try:
    import OpenImageIO as oiio
    OIIO_AVAILABLE = True
except ImportError:
    OIIO_AVAILABLE = False

try:
    from .debug_utils import debug_log, format_layer_names, format_tensor_info, create_fallback_functions
    from .preview_utils import generate_preview_for_comfyui
except ImportError:
    # Use fallback functions
    fallbacks = {
        'debug_log': lambda logger, level, simple_msg, verbose_msg=None, **kwargs: getattr(logger, level.lower())(simple_msg),
        'format_layer_names': lambda layer_names, max_simple=None: ', '.join(layer_names),
        'format_tensor_info': lambda tensor_shape, tensor_dtype, name="": f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}",
        'generate_preview_for_comfyui': lambda image_tensor, source_path="", is_sequence=False, frame_index=0: None
    }
    debug_log = fallbacks['debug_log']
    format_layer_names = fallbacks['format_layer_names']
    format_tensor_info = fallbacks['format_tensor_info']
    generate_preview_for_comfyui = fallbacks['generate_preview_for_comfyui']

logger = logging.getLogger(__name__)


class ExrProcessor:
    """Shared EXR processing functionality for loader nodes"""
    
    @staticmethod
    def check_oiio_availability():
        """Check if OpenImageIO is available"""
        if not OIIO_AVAILABLE:
            raise ImportError("OpenImageIO is required for EXR loading but not available")
    
    @staticmethod
    def scan_exr_metadata(image_path: str) -> Dict[str, Any]:
        """
        Scan the EXR file to extract metadata about available subimages without loading pixel data.
        Returns a dictionary of subimage information including names, channels, dimensions, etc.
        """
        ExrProcessor.check_oiio_availability()

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"EXR file not found: {image_path}")
            
        input_file = None
        try:
            input_file = oiio.ImageInput.open(image_path)
            if not input_file:
                raise IOError(f"Could not open {image_path}")
                
            metadata = {}
            subimages = []
            
            current_subimage = 0
            more_subimages = True
            
            while more_subimages:
                spec = input_file.spec()
                
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                channel_names = [spec.channel_name(i) for i in range(channels)]
                
                subimage_name = "default"
                if "name" in spec.extra_attribs:
                    subimage_name = spec.getattribute("name")
                
                subimage_info = {
                    "index": current_subimage,
                    "name": subimage_name,
                    "width": width,
                    "height": height,
                    "channels": channels,
                    "channel_names": channel_names
                }
                
                extra_attribs = {}
                for i in range(len(spec.extra_attribs)):
                    name = spec.extra_attribs[i].name
                    value = spec.extra_attribs[i].value
                    extra_attribs[name] = value
                
                subimage_info["extra_attributes"] = extra_attribs
                subimages.append(subimage_info)
                
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

    @staticmethod
    def load_all_data(image_path: str) -> Dict[int, np.ndarray]:
        """
        Load all pixel data from all subimages in the EXR file.
        Returns a dictionary mapping subimage index to numpy array of shape (height, width, channels).
        """
        input_file = None
        try:
            input_file = oiio.ImageInput.open(image_path)
            if not input_file:
                raise IOError(f"Could not open {image_path}")
            
            all_subimage_data = {}
            
            current_subimage = 0
            more_subimages = True
            
            while more_subimages:
                spec = input_file.spec()
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                
                pixels = input_file.read_image()
                if pixels is None:
                    debug_log(logger, "warning", "Failed to read subimage", 
                             f"Failed to read image data for subimage {current_subimage} from {image_path}")
                else:
                    all_subimage_data[current_subimage] = np.array(pixels, dtype=np.float32).reshape(height, width, channels)
                
                more_subimages = input_file.seek_subimage(current_subimage + 1, 0)
                current_subimage += 1
            
            return all_subimage_data
            
        finally:
            if input_file:
                input_file.close()

    @staticmethod
    def is_cryptomatte_layer(group_name: str) -> bool:
        """Determine if a layer is a cryptomatte layer based on its name"""
        group_name_lower = group_name.lower()
        return (
            "cryptomatte" in group_name_lower or 
            group_name_lower.startswith("crypto") or
            any(crypto_key for crypto_key in ("cryptoasset", "cryptomaterial", "cryptoobject", "cryptoprimvar") 
                if crypto_key in group_name_lower) or
            any(part.lower().startswith("crypto") for part in group_name.split('.'))
        )

    @staticmethod
    def process_default_channels(all_data, channel_names, height, width, normalize):
        """Process default RGB and Alpha channels"""
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
        
        alpha_tensor = None
        if 'A' in channel_names:
            a_idx = channel_names.index('A')
            alpha_array = all_data[:, :, a_idx]
            
            alpha_tensor = torch.from_numpy(alpha_array).float()
            alpha_tensor = alpha_tensor.unsqueeze(0)  # [1, H, W]
            
            if normalize:
                alpha_tensor = alpha_tensor.clamp(0, 1)
        else:
            alpha_tensor = torch.ones((1, height, width))
            
        return rgb_tensor, alpha_tensor

    @staticmethod
    def process_rgb_type_layer(group_name, r_suffix, g_suffix, b_suffix, a_suffix, 
                               channel_names, all_data, normalize, is_cryptomatte, 
                               layers_dict, cryptomatte_dict):
        """Process RGB/RGBA type layers with various naming conventions"""
        try:
            r_channel = f"{group_name}.{r_suffix}"
            g_channel = f"{group_name}.{g_suffix}"
            b_channel = f"{group_name}.{b_suffix}"
            a_channel = f"{group_name}.{a_suffix}"
            
            try:
                r_idx = channel_names.index(r_channel)
                g_idx = channel_names.index(g_channel)
                b_idx = channel_names.index(b_channel)
            except ValueError:
                debug_log(logger, "warning", "Missing RGB channels", f"Could not find RGB channels for {group_name}")
                return
            
            has_alpha = False
            a_idx = -1
            try:
                a_idx = channel_names.index(a_channel)
                has_alpha = True
            except ValueError:
                pass
            
            rgb_array = np.stack([
                all_data[:, :, r_idx],
                all_data[:, :, g_idx],
                all_data[:, :, b_idx]
            ], axis=2)
            
            rgb_tensor_layer = torch.from_numpy(rgb_array).float()
            rgb_tensor_layer = rgb_tensor_layer.unsqueeze(0)  # [1, H, W, 3]
            
            if normalize:
                rgb_range = rgb_tensor_layer.max() - rgb_tensor_layer.min()
                if rgb_range > 0:
                    rgb_tensor_layer = (rgb_tensor_layer - rgb_tensor_layer.min()) / rgb_range
            
            if is_cryptomatte:
                cryptomatte_dict[group_name] = rgb_tensor_layer
            else:
                layers_dict[group_name] = rgb_tensor_layer
                
            if has_alpha:
                alpha_array = all_data[:, :, a_idx]
                
                alpha_tensor_layer = torch.from_numpy(alpha_array).float()
                alpha_tensor_layer = alpha_tensor_layer.unsqueeze(0)  # [1, H, W]
                
                if normalize:
                    alpha_tensor_layer = alpha_tensor_layer.clamp(0, 1)
                
                alpha_layer_name = f"{group_name}_alpha"
                layers_dict[alpha_layer_name] = alpha_tensor_layer
        except ValueError as e:
            debug_log(logger, "warning", "Error processing RGB layer", f"Error processing RGB layer {group_name}: {str(e)}")

    @staticmethod
    def process_xyz_type_layer(group_name, x_suffix, y_suffix, z_suffix, 
                               channel_names, all_data, normalize, layers_dict):
        """Process XYZ type vector layers with various naming conventions"""
        try:
            x_channel = f"{group_name}.{x_suffix}"
            y_channel = f"{group_name}.{y_suffix}"
            z_channel = f"{group_name}.{z_suffix}"
            
            try:
                x_idx = channel_names.index(x_channel)
                y_idx = channel_names.index(y_channel)
                z_idx = channel_names.index(z_channel)
            except ValueError:
                debug_log(logger, "warning", "Missing XYZ channels", f"Could not find XYZ channels for {group_name}")
                return
            
            xyz_array = np.stack([
                all_data[:, :, x_idx],
                all_data[:, :, y_idx],
                all_data[:, :, z_idx]
            ], axis=2)
            
            xyz_tensor = torch.from_numpy(xyz_array).float()
            xyz_tensor = xyz_tensor.unsqueeze(0)  # [1, H, W, 3]
            
            if normalize:
                max_abs = xyz_tensor.abs().max()
                if max_abs > 0:
                    xyz_tensor = xyz_tensor / max_abs
            
            layers_dict[group_name] = xyz_tensor
        except ValueError as e:
            debug_log(logger, "warning", "Error processing XYZ layer", f"Error processing XYZ layer {group_name}: {str(e)}")

    @staticmethod
    def process_single_channel(group_name, suffixes, group_indices, 
                               channel_names, all_data, normalize, layers_dict):
        """Process single channel data like depth maps or Z channels"""
        idx = -1
        if 'Z' in suffixes:
            z_channel = f"{group_name}.Z"
            z_channel_lower = f"{group_name}.z"
            try:
                idx = channel_names.index(z_channel)
            except ValueError:
                try:
                    idx = channel_names.index(z_channel_lower)
                except ValueError:
                    idx = group_indices[0]
        else:
            idx = group_indices[0]
        
        if idx >= 0:
            channel_array = all_data[:, :, idx]
            
            is_mask_type = any(keyword in group_name.lower() 
                               for keyword in ['depth', 'mask', 'matte', 'alpha', 'id', 'z'])
            
            if group_name == 'Z':
                is_mask_type = True
                debug_log(logger, "info", "Processing Z channel as mask", 
                         f"Processing Z channel as mask: shape={channel_array.shape}")
            
            if is_mask_type:
                mask_tensor = torch.from_numpy(channel_array).float().unsqueeze(0)  # [1, H, W]
                
                if normalize:
                    mask_range = mask_tensor.max() - mask_tensor.min()
                    if mask_range > 0:
                        mask_tensor = (mask_tensor - mask_tensor.min()) / mask_range
                
                debug_log(logger, "info", f"Created mask: {format_tensor_info(mask_tensor.shape, mask_tensor.dtype, group_name)}", 
                         f"Created mask tensor for {group_name}: shape={mask_tensor.shape}, " +
                         f"min={mask_tensor.min().item():.6f}, max={mask_tensor.max().item():.6f}, " +
                         f"mean={mask_tensor.mean().item():.6f}")
                
                layers_dict[group_name] = mask_tensor
            else:
                rgb_array = np.stack([channel_array] * 3, axis=2)
                
                channel_tensor = torch.from_numpy(rgb_array).float()
                channel_tensor = channel_tensor.unsqueeze(0)  # [1, H, W, 3]
                
                if normalize:
                    channel_range = channel_tensor.max() - channel_tensor.min()
                    if channel_range > 0:
                        channel_tensor = (channel_tensor - channel_tensor.min()) / channel_range
                
                debug_log(logger, "info", f"Created RGB: {format_tensor_info(channel_tensor.shape, channel_tensor.dtype, group_name)}", 
                         f"Created RGB tensor for {group_name}: shape={channel_tensor.shape}, " +
                         f"min={channel_tensor.min().item():.6f}, max={channel_tensor.max().item():.6f}, " +
                         f"mean={channel_tensor.mean().item():.6f}")
                
                layers_dict[group_name] = channel_tensor

    @staticmethod
    def process_multi_channel(group_name, group_indices, all_data, normalize,
                              is_cryptomatte, layers_dict, cryptomatte_dict):
        """Process multi-channel data that doesn't fit standard patterns"""
        channels_to_use = min(3, len(group_indices))
        array_channels = []
        
        for i in range(channels_to_use):
            array_channels.append(all_data[:, :, group_indices[i]])
        
        while len(array_channels) < 3:
            array_channels.append(array_channels[-1])
        
        multi_array = np.stack(array_channels, axis=2)
        
        multi_tensor = torch.from_numpy(multi_array).float()
        multi_tensor = multi_tensor.unsqueeze(0)  # [1, H, W, 3]
        
        if normalize:
            multi_range = multi_tensor.max() - multi_tensor.min()
            if multi_range > 0:
                multi_tensor = (multi_tensor - multi_tensor.min()) / multi_range
        
        if is_cryptomatte:
            cryptomatte_dict[group_name] = multi_tensor
        else:
            layers_dict[group_name] = multi_tensor

    @staticmethod
    def process_layer_groups(channel_groups, cryptomatte_dict, metadata):
        """Process groups of related layers (like cryptomatte layer groups)"""
        for group_name, suffixes in channel_groups.items():
            if not group_name.endswith('_layer_group'):
                continue
            
            base_name = group_name[:-12]  # Remove '_layer_group'
            
            if not suffixes:
                continue
            
            is_crypto_layer_group = ExrProcessor.is_cryptomatte_layer(base_name)
            
            in_crypto_dict = any(group_part in cryptomatte_dict for group_part in suffixes)
            
            if 'layer_groups' not in metadata:
                metadata['layer_groups'] = {}
            
            metadata['layer_groups'][base_name] = suffixes
            
            if is_crypto_layer_group or in_crypto_dict:
                cryptomatte_dict[group_name] = [cryptomatte_dict.get(part, None) for part in suffixes]

    @staticmethod
    def store_layer_type_metadata(layers_dict, metadata):
        """Store information about layer types in metadata"""
        layer_types = {}
        for layer_name, tensor in layers_dict.items():
            if len(tensor.shape) >= 4 and tensor.shape[3] == 3:  # It has 3 channels
                layer_types[layer_name] = "IMAGE"
            else:
                layer_types[layer_name] = "MASK"
        
        metadata["layer_types"] = layer_types

    @staticmethod
    def create_processed_layer_names(layers_dict, cryptomatte_dict):
        """Create a sorted list of processed layer names"""
        processed_layer_names = []
        
        for layer_name in layers_dict.keys():
            processed_layer_names.append(layer_name)
        
        for crypto_name in cryptomatte_dict.keys():
            processed_layer_names.append(f"crypto:{crypto_name}")
            
        processed_layer_names.sort()
        
        return processed_layer_names

    @staticmethod
    def get_channel_groups(channel_names: List[str]) -> Dict[str, List[str]]:
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
        layer_group_prefixes = set()
        
        for channel in channel_names:
            if '.' in channel:
                parts = channel.split('.')
                
                if len(parts) > 2:
                    prefix = '.'.join(parts[:-1])
                    suffix = parts[-1]
                else:
                    prefix, suffix = channel.split('.', 1)
                
                base_prefix = prefix
                if any(prefix.endswith(f"{i:02d}") for i in range(10)):
                    for i in range(10):
                        if prefix.endswith(f"{i:02d}"):
                            base_prefix = prefix[:-2]
                            layer_group_prefixes.add(base_prefix)
                            break
                
                if prefix not in groups:
                    groups[prefix] = []
                groups[prefix].append(suffix)
            else:
                if channel not in groups:
                    groups[channel] = []
                groups[channel].append(None)
                
                if len(channel) == 1 and channel in 'RGBAXYZ':
                    if all(c in channel_names for c in 'RGB'):
                        if 'RGB' not in groups:
                            groups['RGB'] = []
                    elif all(c in channel_names for c in 'XYZ'):
                        if 'XYZ' not in groups:
                            groups['XYZ'] = []
        
        if all(c in channel_names for c in 'RGB'):
            groups['RGB'] = ['R', 'G', 'B']
        
        if all(c in channel_names for c in 'XYZ'):
            groups['XYZ'] = ['X', 'Y', 'Z']
        
        depth_channels = [c for c in channel_names if c in ('Z', 'zDepth', 'zDepth1') or 
                          (('depth' in c.lower() or 'z' in c.lower()) and not '.' in c)]
        if depth_channels:
            if 'Depth' not in groups:
                groups['Depth'] = []
            for dc in depth_channels:
                groups['Depth'].append(dc)
        
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
        
        for crypto_base in crypto_prefixes:
            if f"{crypto_base}_layer_group" not in groups:
                groups[f"{crypto_base}_layer_group"] = []
            
            for i in range(10):
                group_name = f"{crypto_base}{i:02d}"
                if group_name in groups:
                    groups[f"{crypto_base}_layer_group"].append(group_name)
        
        for group_base in layer_group_prefixes:
            if group_base in crypto_prefixes:
                continue
                
            if f"{group_base}_layer_group" not in groups:
                groups[f"{group_base}_layer_group"] = []
            
            for i in range(10):
                group_name = f"{group_base}{i:02d}"
                if group_name in groups:
                    groups[f"{group_base}_layer_group"].append(group_name)
        
        return groups

    @staticmethod
    def process_exr_data(image_path: str, normalize: bool, node_id: str = None, layer_data: Dict = None) -> List:
        """
        Main EXR processing function that handles all layer extraction and processing.
        This replaces the _load_single_image functionality from the original LoadExr class.
        """
        if image_path is None:
            raise ValueError("image_path cannot be None. This may indicate a missing frame in the sequence.")
            
        try:
            metadata = layer_data if layer_data else ExrProcessor.scan_exr_metadata(image_path)
            
            all_subimage_data = ExrProcessor.load_all_data(image_path)
            
            layers_dict = {}
            cryptomatte_dict = {}
            all_channel_names = []
            
            for subimage_idx, subimage_info in enumerate(metadata["subimages"]):
                if subimage_idx not in all_subimage_data:
                    debug_log(logger, "warning", "No subimage data", f"No data found for subimage {subimage_idx}")
                    continue
                
                subimage_data = all_subimage_data[subimage_idx]
                subimage_name = subimage_info["name"]
                channel_names = subimage_info["channel_names"]
                
                all_channel_names.extend(channel_names)
                
                height, width, channels = subimage_data.shape
                
                if subimage_idx == 0:
                    channel_groups = ExrProcessor.get_channel_groups(channel_names)
                    metadata["channel_groups"] = channel_groups
                    
                    rgb_tensor, alpha_tensor = ExrProcessor.process_default_channels(
                        subimage_data, channel_names, height, width, normalize
                    )
                
                if subimage_name != "default":
                    if channels >= 3:
                        rgb_array = subimage_data[:, :, :3]
                        
                        rgb_tensor_layer = torch.from_numpy(rgb_array).float()
                        rgb_tensor_layer = rgb_tensor_layer.unsqueeze(0)  # [1, H, W, 3]
                        
                        if normalize:
                            rgb_range = rgb_tensor_layer.max() - rgb_tensor_layer.min()
                            if rgb_range > 0:
                                rgb_tensor_layer = (rgb_tensor_layer - rgb_tensor_layer.min()) / rgb_range
                        
                        layers_dict[subimage_name] = rgb_tensor_layer
                        
                        if channels >= 4:
                            alpha_array = subimage_data[:, :, 3]
                            
                            alpha_tensor_layer = torch.from_numpy(alpha_array).float()
                            alpha_tensor_layer = alpha_tensor_layer.unsqueeze(0)  # [1, H, W]
                            
                            if normalize:
                                alpha_tensor_layer = alpha_tensor_layer.clamp(0, 1)
                            
                            layers_dict[f"{subimage_name}_alpha"] = alpha_tensor_layer
                    
                    elif channels == 1:
                        channel_array = subimage_data[:, :, 0]
                        
                        is_mask_type = any(keyword in subimage_name.lower() 
                                        for keyword in ['depth', 'mask', 'matte', 'alpha', 'id', 'z'])
                        
                        if is_mask_type or subimage_name == 'depth':
                            mask_tensor = torch.from_numpy(channel_array).float().unsqueeze(0)  # [1, H, W]
                            
                            if normalize:
                                mask_range = mask_tensor.max() - mask_tensor.min()
                                if mask_range > 0:
                                    mask_tensor = (mask_tensor - mask_tensor.min()) / mask_range
                            
                            if mask_tensor.numel() > 1:
                                layers_dict[subimage_name] = mask_tensor
                            else:
                                layers_dict[subimage_name] = torch.zeros((1, height, width))
                        else:
                            rgb_array = np.stack([channel_array] * 3, axis=2)
                            
                            channel_tensor = torch.from_numpy(rgb_array).float()
                            channel_tensor = channel_tensor.unsqueeze(0)  # [1, H, W, 3]
                            
                            if normalize:
                                channel_range = channel_tensor.max() - channel_tensor.min()
                                if channel_range > 0:
                                    channel_tensor = (channel_tensor - channel_tensor.min()) / channel_range
                            
                            if channel_tensor.numel() > 3:
                                layers_dict[subimage_name] = channel_tensor
                            else:
                                layers_dict[subimage_name] = torch.zeros((1, height, width, 3))
                
                if subimage_idx == 0:
                    channel_groups = ExrProcessor.get_channel_groups(channel_names)
                    
                    for group_name, suffixes in channel_groups.items():
                        if group_name in ('R', 'G', 'B', 'A', 'RGB', 'XYZ'):
                            continue
                        
                        if group_name.endswith('_layer_group'):
                            continue
                        
                        is_cryptomatte = ExrProcessor.is_cryptomatte_layer(group_name)
                        
                        group_indices = []
                        for i, channel in enumerate(channel_names):
                            if (channel == group_name) or (channel.startswith(f"{group_name}.")):
                                group_indices.append(i)
                        
                        if not group_indices:
                            continue
                        
                        if all(suffix in suffixes for suffix in ['R', 'G', 'B']):
                            ExrProcessor.process_rgb_type_layer(
                                group_name, 'R', 'G', 'B', 'A', channel_names, subimage_data, 
                                normalize, is_cryptomatte, layers_dict, cryptomatte_dict
                            )
                        
                        elif all(suffix in suffixes for suffix in ['r', 'g', 'b']):
                            ExrProcessor.process_rgb_type_layer(
                                group_name, 'r', 'g', 'b', 'a', channel_names, subimage_data, 
                                normalize, is_cryptomatte, layers_dict, cryptomatte_dict
                            )
                        
                        elif all(suffix in suffixes for suffix in ['X', 'Y', 'Z']):
                            ExrProcessor.process_xyz_type_layer(
                                group_name, 'X', 'Y', 'Z', channel_names, subimage_data, 
                                normalize, layers_dict
                            )
                                
                        elif all(suffix in suffixes for suffix in ['x', 'y', 'z']):
                            ExrProcessor.process_xyz_type_layer(
                                group_name, 'x', 'y', 'z', channel_names, subimage_data, 
                                normalize, layers_dict
                            )
                        
                        elif len(group_indices) == 1 or 'Z' in suffixes:
                            ExrProcessor.process_single_channel(
                                group_name, suffixes, group_indices, channel_names,
                                subimage_data, normalize, layers_dict
                            )
                        
                        else:
                            ExrProcessor.process_multi_channel(
                                group_name, group_indices, subimage_data, normalize,
                                is_cryptomatte, layers_dict, cryptomatte_dict
                            )
            
            ExrProcessor.process_layer_groups(
                channel_groups, cryptomatte_dict, metadata
            )
            
            ExrProcessor.store_layer_type_metadata(layers_dict, metadata)
            
            metadata_json = json.dumps(metadata)
            
            debug_log(logger, "info", f"Loaded {len(layers_dict)} layers: {format_layer_names(list(layers_dict.keys()))}", 
                     f"Available EXR layers: {list(layers_dict.keys())}")
            if cryptomatte_dict:
                debug_log(logger, "info", f"Loaded {len(cryptomatte_dict)} cryptomatte layers", 
                         f"Available cryptomatte layers: {list(cryptomatte_dict.keys())}")
            
            layer_names = all_channel_names
            
            processed_layer_names = ExrProcessor.create_processed_layer_names(layers_dict, cryptomatte_dict)
            
            preview_result = generate_preview_for_comfyui(rgb_tensor, image_path, is_sequence=False, frame_index=0)
            
            result = [rgb_tensor, alpha_tensor, cryptomatte_dict, layers_dict, processed_layer_names, layer_names, metadata_json]
            
            if preview_result:
                return {"ui": {"images": preview_result}, "result": result}
            else:
                return result
            
        except Exception as e:
            debug_log(logger, "error", "Error loading EXR", f"Error loading EXR file {image_path}: {str(e)}")
            raise