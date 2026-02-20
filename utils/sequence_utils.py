"""
Sequence utilities for COCO Tools nodes
Provides shared functionality for handling image sequences with #### patterns
"""

import os
import glob
import re
import logging
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from .debug_utils import debug_log
except ImportError:
    # Use fallback function
    debug_log = lambda logger, level, simple_msg, verbose_msg=None, **kwargs: getattr(logger, level.lower())(simple_msg)


class SequenceHandler:
    """Shared sequence handling functionality for loader and saver nodes"""
    
    @staticmethod
    def detect_sequence_pattern(path: str) -> bool:
        """Detect if the path contains a sequence pattern (#### or ###)"""
        if not path:
            return False
        # Only check filename portion, require 2+ consecutive # characters
        basename = os.path.basename(path)
        return bool(re.search(r'#{2,}', basename))
    
    @staticmethod
    def get_padding_from_template(template: str) -> int:
        """Extract padding length from #### pattern"""
        match = re.search(r'#+', template)
        if match:
            return len(match.group(0))
        return 4  # Default padding
    
    @staticmethod
    def replace_frame_number(filename: str, frame_number: int, padding_length: int = None) -> str:
        """
        Replace frame number in filename with proper padding

        Args:
            filename: Template filename with #### placeholder or existing frame number
            frame_number: The frame number to insert
            padding_length: Number of digits to pad to (auto-detected if None)

        Returns:
            Filename with properly padded frame number
        """
        # Find the #### placeholder pattern
        match = re.search(r'#+', filename)
        if not match:
            return filename

        # Use the placeholder's length for padding if not specified
        if padding_length is None:
            padding_length = len(match.group(0))

        # Create padded frame number
        padded_frame = str(frame_number).zfill(padding_length)

        # Replace only the #### placeholder, leave all other characters untouched
        return filename[:match.start()] + padded_frame + filename[match.end():]
    
    @staticmethod
    def extract_frame_number_from_path(file_path: str, pattern: str = None) -> Optional[int]:
        """Extract frame number from a file path

        Args:
            file_path: Path to the file
            pattern: Original sequence pattern (e.g., 'render_1080p_####.exr')
                     to determine the exact frame number position
        """
        basename = os.path.basename(file_path)

        # If pattern is provided, extract from the known position
        if pattern:
            pattern_basename = os.path.basename(pattern)
            hash_match = re.search(r'#+', pattern_basename)
            if hash_match:
                hash_count = len(hash_match.group(0))
                before = re.escape(pattern_basename[:hash_match.start()])
                after = re.escape(pattern_basename[hash_match.end():])
                extraction_re = before + r'(\d{' + str(hash_count) + '})' + after
                match = re.match(extraction_re, basename)
                if match:
                    return int(match.group(1))

        # Fallback: prefer the last numeric sequence before the extension
        name_without_ext = os.path.splitext(basename)[0]
        matches = re.findall(r'\d+', name_without_ext)
        if matches:
            return int(matches[-1])
        return None
    
    @staticmethod
    def find_sequence_files(pattern_path: str) -> List[str]:
        """Find all files matching the sequence pattern"""
        # Find the hash placeholder and count its width
        hash_match = re.search(r'#+', pattern_path)
        if not hash_match:
            return []

        hash_count = len(hash_match.group(0))

        # Convert #### pattern to glob pattern (? matches single char)
        glob_pattern = pattern_path[:hash_match.start()] + '?' * hash_count + pattern_path[hash_match.end():]

        # Find all matching files
        matching_files = glob.glob(glob_pattern)

        # Build regex by escaping fixed parts and inserting digit pattern
        before = re.escape(pattern_path[:hash_match.start()])
        after = re.escape(pattern_path[hash_match.end():])
        pattern_for_regex = before + r'\d{' + str(hash_count) + '}' + after

        regex_pattern = re.compile(pattern_for_regex)

        # Debug logging
        debug_log(logger, "debug", f"Pattern matching debug",
                 f"Original: {pattern_path}\\nRegex: {pattern_for_regex}\\nMatching files: {len(matching_files)}")

        valid_files = []
        for file_path in matching_files:
            if regex_pattern.match(file_path):
                valid_files.append(file_path)
            else:
                if len(valid_files) < 3:
                    debug_log(logger, "debug", f"No match", f"File: {file_path}\\nPattern: {pattern_for_regex}")

        debug_log(logger, "info", f"Found {len(valid_files)} sequence files",
                 f"Pattern: {pattern_path}, Found {len(valid_files)} files matching pattern")

        return sorted(valid_files)
    
    @staticmethod
    def extract_frame_numbers(file_paths: List[str]) -> List[Tuple[int, str]]:
        """Extract frame numbers from file paths and return sorted list of (frame_num, path) tuples"""
        frame_info = []
        for file_path in file_paths:
            frame_num = SequenceHandler.extract_frame_number_from_path(file_path)
            if frame_num is not None:
                frame_info.append((frame_num, file_path))
        
        frame_info.sort()  # Sort by frame number
        return frame_info
    
    @staticmethod
    def generate_frame_paths(pattern_path: str, start_frame: int, end_frame: int, frame_step: int) -> List[str]:
        """Generate list of frame paths based on pattern and parameters using improved regex approach"""
        frame_paths = []
        
        current_frame = start_frame
        while current_frame <= end_frame:
            frame_path = SequenceHandler.replace_frame_number(pattern_path, current_frame)
            frame_paths.append(frame_path)
            current_frame += frame_step
        
        return frame_paths
    
    @staticmethod
    def select_sequence_frames(available_frames: List[Tuple[int, str]], start_frame: int, 
                             end_frame: int, frame_step: int) -> List[str]:
        """
        Select specific frames from available sequence based on parameters
        
        Args:
            available_frames: List of (frame_number, file_path) tuples
            start_frame: Starting frame number
            end_frame: Ending frame number
            frame_step: Step between frames
        
        Returns:
            List of selected file paths (strict selection - no fallbacks)
        """
        selected_frames = []
        
        # Generate expected frame numbers and find exact matches
        current_frame = start_frame
        while current_frame <= end_frame:
            # Find the exact matching frame
            found = False
            for frame_num, file_path in available_frames:
                if frame_num == current_frame:
                    selected_frames.append(file_path)
                    found = True
                    break
            
            # If frame not found, append None to maintain sequence positions
            if not found:
                selected_frames.append(None)
            
            current_frame += frame_step
        
        expected_count = len(range(start_frame, end_frame + 1, frame_step))
        debug_log(logger, "info", f"Selected {len([f for f in selected_frames if f is not None])} of {expected_count} frames", 
                 f"Selected {len([f for f in selected_frames if f is not None])} frames from {len(available_frames)} available " +
                 f"(start={start_frame}, end={end_frame}, step={frame_step})")
        
        return selected_frames
    
    @staticmethod
    def validate_sequence_parameters(start_frame: int, end_frame: int, frame_step: int) -> Tuple[int, int, int]:
        """Validate and sanitize sequence parameters"""
        # Ensure valid values - no fallback defaults
        if start_frame is None:
            raise ValueError("start_frame parameter is required and cannot be None. " +
                           "Make sure the node is in 'sequence' mode and the sequence widgets are visible.")
        if end_frame is None:
            raise ValueError("end_frame parameter is required and cannot be None. " +
                           "Make sure the node is in 'sequence' mode and the sequence widgets are visible.")
        if frame_step is None:
            raise ValueError("frame_step parameter is required and cannot be None. " +
                           "Make sure the node is in 'sequence' mode and the sequence widgets are visible.")
            
        start_frame = max(0, start_frame)
        end_frame = max(start_frame, end_frame)
        frame_step = max(1, frame_step)
        
        return start_frame, end_frame, frame_step
    
    @staticmethod
    def get_sequence_info(pattern_path: str) -> Dict:
        """Get information about an available sequence"""
        if not SequenceHandler.detect_sequence_pattern(pattern_path):
            return {"is_sequence": False}
        
        sequence_files = SequenceHandler.find_sequence_files(pattern_path)
        if not sequence_files:
            return {"is_sequence": True, "available_frames": 0}
        
        frame_info = SequenceHandler.extract_frame_numbers(sequence_files)
        frame_numbers = [fn for fn, fp in frame_info]
        
        return {
            "is_sequence": True,
            "available_frames": len(sequence_files),
            "first_frame": min(frame_numbers) if frame_numbers else 0,
            "last_frame": max(frame_numbers) if frame_numbers else 0,
            "frame_numbers": frame_numbers
        }


class DynamicUIHelper:
    """Helper for creating dynamic UI widgets in ComfyUI nodes"""
    
    @staticmethod
    def create_sequence_widgets(default_start: int = 1, default_end: int = 100, default_step: int = 1) -> Dict:
        """Create standard sequence control widgets"""
        return {
            "sequence": [
                ["start_frame", "INT", {"default": default_start, "min": 0, "max": 999999}],
                ["end_frame", "INT", {"default": default_end, "min": 1, "max": 999999}],
                ["frame_step", "INT", {"default": default_step, "min": 1, "max": 100}]
            ]
        }
    
    @staticmethod
    def create_versioning_widgets() -> Dict:
        """Create versioning control widgets"""
        return {
            "versioning": [
                ["version", "INT", {"default": 1, "min": -1, "max": 999}]
            ]
        }
    
    @staticmethod
    def create_save_mode_widgets() -> Dict:
        """Create save mode control widgets for saver"""
        return {
            "sequence": [
                ["start_frame", "INT", {"default": 1, "min": 0, "max": 999999}],
                ["frame_step", "INT", {"default": 1, "min": 1, "max": 100}]
            ]
        }