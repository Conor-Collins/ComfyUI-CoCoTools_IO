"""
Debug utilities for COCO Tools with simple/verbose logging control.
"""
import logging
from typing import List, Dict, Any, Optional

# Global debug mode control - default to simple
DEBUG_MODE = "simple"  # "simple" or "verbose"

# Flag to prevent multiple logging configurations
_LOGGING_CONFIGURED = False

def setup_logging(level: int = logging.INFO):
    """
    Centralized logging configuration for all COCO Tools modules.
    Should be called once at module level to avoid conflicts.
    """
    global _LOGGING_CONFIGURED
    if not _LOGGING_CONFIGURED:
        # Check if root logger already has handlers to prevent duplicate setup
        if not logging.getLogger().handlers:
            logging.basicConfig(level=level)
        _LOGGING_CONFIGURED = True

def set_debug_mode(mode: str):
    """Set global debug mode"""
    global DEBUG_MODE
    DEBUG_MODE = mode.lower() if mode.lower() in ["simple", "verbose"] else "simple"

def get_debug_mode() -> str:
    """Get current debug mode"""
    return DEBUG_MODE

def debug_log(logger: logging.Logger, level: str, simple_msg: str, verbose_msg: Optional[str] = None, **kwargs):
    """
    Log with debug verbosity control.
    
    Args:
        logger: Logger instance
        level: Log level ("info", "warning", "error", "debug")
        simple_msg: Short message for simple mode
        verbose_msg: Detailed message for verbose mode (if None, uses simple_msg)
        **kwargs: Additional context for verbose mode
    """
    message = simple_msg if DEBUG_MODE == "simple" else (verbose_msg or simple_msg)
    
    # Add context info in verbose mode
    if DEBUG_MODE == "verbose" and kwargs:
        context_parts = [f"{k}={v}" for k, v in kwargs.items()]
        message += f" [{', '.join(context_parts)}]"
    
    # Log based on level
    if level.lower() == "info":
        logger.info(message)
    elif level.lower() == "warning":
        logger.warning(message)
    elif level.lower() == "error":
        logger.error(message)
    elif level.lower() == "debug":
        logger.debug(message)

def format_layer_names(layer_names: List[str], max_simple: int = None) -> str:
    """Format layer names for logging - show all layer names as they're important for users"""
    # Always show all layer names as users need to know what's available
    return ', '.join(layer_names)

def format_tensor_info(tensor_shape: tuple, tensor_dtype: Any, name: str = "") -> str:
    """Format tensor information for logging"""
    if DEBUG_MODE == "simple":
        return f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}"
    return f"{name} shape={tensor_shape}, dtype={tensor_dtype}" if name else f"shape={tensor_shape}, dtype={tensor_dtype}"

def create_fallback_functions():
    """
    Create fallback functions for cases where debug_utils import fails.
    Returns a dictionary of fallback functions following single responsibility principle.
    """
    return {
        'debug_log': lambda logger, level, simple_msg, verbose_msg=None, **kwargs: getattr(logger, level.lower())(simple_msg),
        'format_layer_names': lambda layer_names, max_simple=None: ', '.join(layer_names),
        'format_tensor_info': lambda tensor_shape, tensor_dtype, name="": f"{name} shape={tensor_shape}" if name else f"shape={tensor_shape}",
        'generate_preview_for_comfyui': lambda image_tensor, source_path="", is_sequence=False, frame_index=0: None
    }