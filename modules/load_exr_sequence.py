import os
import logging
import torch
import json
from typing import List

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Import EXR and sequence utilities
try:
    from ..utils.exr_utils import ExrProcessor
    from ..utils.sequence_utils import SequenceHandler
    from ..utils.debug_utils import debug_log, format_tensor_info
    from ..utils.preview_utils import generate_preview_for_comfyui
except ImportError as e:
    raise ImportError(f"Required utilities are not available: {str(e)}. Please ensure utils are properly installed.")


class LoadExrSequence:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sequence_path": ("STRING", {
                    "default": "path/to/sequence_####.exr",
                    "description": "Path with #### pattern for frame numbers (e.g., render_####.exr)"
                }),
                "start_frame": ("INT", {
                    "default": 1,
                    "min": 0,
                    "max": 999999,
                    "description": "Starting frame number"
                }),
                "end_frame": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 999999,
                    "description": "Ending frame number"
                }),
                "frame_step": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "description": "Step between frames"
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

    RETURN_TYPES = ("IMAGE", "MASK", "CRYPTOMATTE", "LAYERS", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("sequence", "alpha", "cryptomatte", "layers", "layer names", "raw layer info", "metadata")
    
    FUNCTION = "load_sequence"
    CATEGORY = "Image/EXR"
    
    @classmethod
    def IS_CHANGED(cls, sequence_path, start_frame, end_frame, frame_step, normalize=False, **kwargs):
        """
        Smart caching based on file modification times and sequence parameters.
        Only reload if files actually changed or parameters changed.
        """
        try:
            # Validate sequence pattern first
            if not SequenceHandler.detect_sequence_pattern(sequence_path):
                return float("NaN")  # Invalid pattern, always try
            
            # Validate and sanitize sequence parameters
            try:
                start_frame, end_frame, frame_step = SequenceHandler.validate_sequence_parameters(
                    start_frame, end_frame, frame_step
                )
            except Exception:
                return float("NaN")  # Invalid parameters, always try
            
            # Find existing sequence files
            try:
                existing_sequence_files = SequenceHandler.find_sequence_files(sequence_path)
                if not existing_sequence_files:
                    return float("NaN")  # No files found, always try
                
                # Extract frame numbers and select frames that would be loaded
                frame_info = SequenceHandler.extract_frame_numbers(existing_sequence_files)
                selected_frames = SequenceHandler.select_sequence_frames(
                    frame_info, start_frame, end_frame, frame_step
                )
                
                if not selected_frames:
                    return float("NaN")  # No frames selected, always try
            except Exception:
                return float("NaN")  # Error in sequence processing, always try
            
            # Create hash from all file stats and parameters
            file_stats = []
            for frame_path in selected_frames:
                if frame_path and os.path.isfile(frame_path):
                    try:
                        stat = os.stat(frame_path)
                        file_stats.append(f"{stat.st_mtime}_{stat.st_size}")
                    except Exception:
                        file_stats.append("error")
                else:
                    file_stats.append("missing")
            
            # Include all parameters that affect the result
            param_hash = f"{sequence_path}_{start_frame}_{end_frame}_{frame_step}_{normalize}"
            files_hash = "_".join(file_stats)
            
            return f"{param_hash}_{files_hash}"
            
        except Exception:
            # If anything goes wrong, always try to load
            return float("NaN")

    def load_sequence(self, sequence_path: str, start_frame: int, end_frame: int, frame_step: int,
                     normalize: bool = False, node_id: str = None, layer_data: dict = None, **kwargs) -> List:
        """
        Load a sequence of EXR files and return batched tensors.
        Returns:
        - Batched RGB image tensors [B, H, W, 3] (sequence)
        - Batched Alpha channel tensors [B, H, W] (alpha)
        - Dictionary of all cryptomatte layers as batched tensors (cryptomatte)
        - Dictionary of all non-cryptomatte layers as batched tensors (layers)
        - List of processed layer names matching keys in the returned dictionaries (layer names)
        - List of raw channel names from the files (raw layer info)
        - Metadata as JSON string with sequence info (metadata)
        """
        
        # Check for OIIO availability
        ExrProcessor.check_oiio_availability()
            
        try:
            # Validate sequence pattern
            if not SequenceHandler.detect_sequence_pattern(sequence_path):
                raise ValueError(f"Sequence path must contain #### pattern for frame numbers: {sequence_path}")
            
            # Validate and sanitize sequence parameters
            start_frame, end_frame, frame_step = SequenceHandler.validate_sequence_parameters(
                start_frame, end_frame, frame_step
            )
            
            frame_count = len(range(start_frame, end_frame + 1, frame_step))
            debug_log(logger, "info", f"Loading EXR sequence: {frame_count} frames", 
                     f"Loading EXR sequence: {sequence_path} (start={start_frame}, end={end_frame}, step={frame_step})")
            
            # Find existing sequence files
            existing_sequence_files = SequenceHandler.find_sequence_files(sequence_path)
            debug_log(logger, "info", f"Found {len(existing_sequence_files)} sequence files",
                     f"SequenceHandler found {len(existing_sequence_files)} files for pattern: {sequence_path}")
            
            if not existing_sequence_files:
                logger.error(f"No sequence files found for pattern: {sequence_path}")
                logger.error(f"Pattern path: {sequence_path}")
                logger.error(f"Expected frame range: {start_frame} to {end_frame} step {frame_step}")
                raise FileNotFoundError(f"No sequence frames found for pattern: {sequence_path}")
            
            # Extract frame numbers and select frames
            frame_info = SequenceHandler.extract_frame_numbers(existing_sequence_files)
            selected_frames = SequenceHandler.select_sequence_frames(
                frame_info, start_frame, end_frame, frame_step
            )
            
            if not selected_frames:
                logger.error(f"No frames selected from sequence")
                logger.error(f"Available frames: {len(existing_sequence_files)}")
                logger.error(f"Frame range requested: {start_frame} to {end_frame} step {frame_step}")
                if frame_info:
                    available_frame_numbers = [frame_num for frame_num, _ in frame_info]
                    logger.error(f"Available frame numbers: {sorted(available_frame_numbers)}")
                raise ValueError(f"No frames selected from sequence for range {start_frame}-{end_frame} step {frame_step}")
            
            debug_log(logger, "info", f"Selected {len(selected_frames)} frames for loading", 
                     f"Loading {len(selected_frames)} frames from sequence")
            
            # Find first valid frame to establish structure
            first_valid_frame = None
            first_frame_index = 0
            for i, frame_path in enumerate(selected_frames):
                if frame_path is not None:
                    first_valid_frame = frame_path
                    first_frame_index = i
                    break
            
            if first_valid_frame is None:
                raise ValueError(f"No valid frames found in sequence range {start_frame}-{end_frame} step {frame_step}")
            
            # Load first valid frame to establish structure
            try:
                first_frame_result = ExrProcessor.process_exr_data(first_valid_frame, normalize, node_id, layer_data)
            except Exception as e:
                logger.error(f"Failed to load first frame: {first_valid_frame}")
                logger.error(f"Error: {str(e)}")
                raise
            
            # Handle result format (dict if preview generated, list if not)
            if isinstance(first_frame_result, dict):
                first_frame_data = first_frame_result["result"]
            else:
                first_frame_data = first_frame_result
            
            # Initialize batch tensors with first frame
            batch_rgb_list = [first_frame_data[0]]
            batch_alpha_list = [first_frame_data[1]]
            batch_layers_dict = {}
            batch_cryptomatte_dict = {}
            
            # Initialize layer dictionaries
            for layer_name, layer_tensor in first_frame_data[3].items():
                batch_layers_dict[layer_name] = [layer_tensor]
            
            for crypto_name, crypto_tensor in first_frame_data[2].items():
                batch_cryptomatte_dict[crypto_name] = [crypto_tensor]
            
            # Load remaining frames (skip the first valid frame we already loaded)
            for i, frame_path in enumerate(selected_frames):
                # Skip the first valid frame (already loaded) and None paths
                if i == first_frame_index or frame_path is None:
                    if frame_path is None:
                        logger.warning(f"Skipping missing frame {i+1}/{len(selected_frames)}: frame not found in sequence")
                        # Create white placeholder frames for missing frames
                        white_rgb = torch.ones_like(first_frame_data[0])
                        white_alpha = torch.ones_like(first_frame_data[1])
                        batch_rgb_list.append(white_rgb)
                        batch_alpha_list.append(white_alpha)
                        
                        # Create white placeholders for layers
                        for layer_name, layer_tensor in first_frame_data[3].items():
                            if layer_name in batch_layers_dict:
                                white_layer = torch.ones_like(layer_tensor)
                                batch_layers_dict[layer_name].append(white_layer)
                        
                        # Create white placeholders for cryptomatte
                        for crypto_name, crypto_tensor in first_frame_data[2].items():
                            if crypto_name in batch_cryptomatte_dict:
                                white_crypto = torch.ones_like(crypto_tensor)
                                batch_cryptomatte_dict[crypto_name].append(white_crypto)
                    continue
                    
                try:
                    frame_result = ExrProcessor.process_exr_data(frame_path, normalize, node_id, layer_data)
                    
                    # Handle result format (dict if preview generated, list if not)
                    if isinstance(frame_result, dict):
                        frame_data = frame_result["result"]
                    else:
                        frame_data = frame_result
                    
                    # Add to batch lists
                    batch_rgb_list.append(frame_data[0])
                    batch_alpha_list.append(frame_data[1])
                    
                    # Add layers to batch
                    for layer_name, layer_tensor in frame_data[3].items():
                        if layer_name in batch_layers_dict:
                            batch_layers_dict[layer_name].append(layer_tensor)
                        else:
                            logger.warning(f"Layer '{layer_name}' not found in first frame, skipping for this frame")
                    
                    # Add cryptomatte to batch
                    for crypto_name, crypto_tensor in frame_data[2].items():
                        if crypto_name in batch_cryptomatte_dict:
                            batch_cryptomatte_dict[crypto_name].append(crypto_tensor)
                        else:
                            logger.warning(f"Cryptomatte '{crypto_name}' not found in first frame, skipping for this frame")
                            
                except Exception as e:
                    logger.error(f"Failed to load frame {i+1}/{len(selected_frames)}: {frame_path}")
                    logger.error(f"Error: {str(e)}")
                    # Create white placeholder frame for failed loads
                    white_rgb = torch.ones_like(first_frame_data[0])
                    white_alpha = torch.ones_like(first_frame_data[1])
                    batch_rgb_list.append(white_rgb)
                    batch_alpha_list.append(white_alpha)
                    
                    # Create white placeholders for layers
                    for layer_name, layer_tensor in first_frame_data[3].items():
                        if layer_name in batch_layers_dict:
                            white_layer = torch.ones_like(layer_tensor)
                            batch_layers_dict[layer_name].append(white_layer)
                    
                    # Create white placeholders for cryptomatte
                    for crypto_name, crypto_tensor in first_frame_data[2].items():
                        if crypto_name in batch_cryptomatte_dict:
                            white_crypto = torch.ones_like(crypto_tensor)
                            batch_cryptomatte_dict[crypto_name].append(white_crypto)
            
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
            
            # Update metadata with sequence information
            metadata_str = first_frame_data[6]  # metadata is at index 6
            metadata = json.loads(metadata_str) if metadata_str else {}
            metadata["sequence_info"] = {
                "is_sequence": True,
                "pattern": sequence_path,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "frame_step": frame_step,
                "total_frames": len(selected_frames),
                "loaded_frames": [f for f in selected_frames if f is not None],
                "missing_frames": [i for i, f in enumerate(selected_frames) if f is None]
            }
            metadata_json = json.dumps(metadata)
            
            # Log final batch information
            debug_log(logger, "info", f"Sequence loaded: {len(selected_frames)} frames, RGB shape: {format_tensor_info(final_rgb.shape, final_rgb.dtype)}",
                     f"Successfully loaded sequence: {len(selected_frames)} frames, RGB batch shape: {final_rgb.shape}, "
                     f"Alpha batch shape: {final_alpha.shape}, {len(final_layers)} layer types, {len(final_cryptomatte)} cryptomatte types")
            
            # Generate preview for sequence (first frame) at full resolution
            preview_result = generate_preview_for_comfyui(final_rgb, sequence_path, is_sequence=True, frame_index=0)
            
            # Return same structure as single image but with batched tensors
            result = [
                final_rgb,                # sequence
                final_alpha,              # alpha
                final_cryptomatte,        # cryptomatte
                final_layers,             # layers
                first_frame_data[4],      # layer names (processed layer names)
                first_frame_data[5],      # raw layer info (layer names)
                metadata_json             # metadata
            ]
            
            # Return with preview if generated
            if preview_result:
                return {"ui": {"images": preview_result}, "result": result}
            else:
                return result
            
        except Exception as e:
            logger.error(f"Error loading EXR sequence {sequence_path}: {str(e)}")
            raise