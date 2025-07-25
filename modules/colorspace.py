import torch
import numpy as np
import colour
import logging
from typing import Tuple

# Import batch processing utilities
try:
    from ..utils.batch_utils import BatchProcessor, log_batch_processing
except ImportError:
    # Fallback if utils not available
    class BatchProcessor:
        @staticmethod
        def validate_batch_tensor(tensor, expected_dims=4, tensor_name="input"):
            return tensor.shape
        @staticmethod
        def reshape_for_processing(tensor, preserve_alpha=True):
            img_np = tensor.cpu().numpy()
            return img_np.reshape(-1, img_np.shape[-1]), None, img_np.shape
        @staticmethod  
        def reshape_from_processing(processed_rgb, alpha_channel, original_shape, target_device):
            return torch.from_numpy(processed_rgb.reshape(original_shape)).to(target_device)
    def log_batch_processing(tensor, operation, name="tensor"):
        pass

# Import centralized logging setup
try:
    from ..utils.debug_utils import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

class ColorspaceNode:
    """Simplified colorspace converter using colour-science library."""
    
    def __init__(self):
        self.type = "ColorspaceNode"
        
        # Map user-friendly names to colour-science names
        self.colorspace_mapping = {
            # ACES colorspaces
            "ACES2065-1": "ACES2065-1",  # Linear scene-referred ACES
            "ACEScg": "ACEScg",          # Linear scene-referred ACEScg
            "ACEScct": "ACEScct",        # Log-encoded ACEScg with toe
            "ACEScc": "ACEScc",          # Log-encoded ACES
            
            # sRGB and Rec.709
            "sRGB": "sRGB",                  # Standard display-referred sRGB (non-linear)
            "sRGB Linear": "sRGB",           # Linear version of sRGB
            "Rec.709": "ITU-R BT.709",       # Standard Rec.709 (scene-referred)
            "Rec.709 Linear": "ITU-R BT.709", # Linear version of Rec.709
            
            # Display P3
            "Display P3": "Display P3",       # Apple's Display P3 (non-linear)
            "Display P3 Linear": "Display P3", # Linear version of Display P3
            
            # Rec.2020
            "Rec.2020": "ITU-R BT.2020",       # Standard Rec.2020 (non-linear)
            "Rec.2020 Linear": "ITU-R BT.2020", # Linear version of Rec.2020
            
            # Adobe RGB
            "Adobe RGB": "Adobe RGB (1998)",       # Standard Adobe RGB (non-linear)
            "Adobe RGB Linear": "Adobe RGB (1998)", # Linear version of Adobe RGB
            
            # Raw/passthrough
            "Raw": "Raw",  # No colorspace conversion
        }
        
        # Track which colorspaces need encoding/decoding
        self.encoded_spaces = {
            "sRGB",  # Standard sRGB is encoded (non-linear)
            "ACEScct",  # ACEScct is an encoded version of ACEScg
            "ACEScc",   # ACEScc is an encoded version of ACES2065-1
        }
        
        # Available colorspaces for the UI
        self.available_colorspaces = list(self.colorspace_mapping.keys())
        
        logger.info(f"Initialized with {len(self.available_colorspaces)} colorspaces")
    
    @classmethod
    def INPUT_TYPES(cls):
        """Define input types."""
        instance = cls()
        return {
            "required": {
                "images": ("IMAGE",),
                "from_colorspace": (instance.available_colorspaces,),
                "to_colorspace": (instance.available_colorspaces,),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "convert_colorspace"
    CATEGORY = "COCO Tools/Processing"
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")  # Always execute

    def _is_encoded_colorspace(self, colorspace_name: str) -> bool:
        """Check if a colorspace name indicates encoded (non-linear) data."""
        # Explicitly encoded spaces
        if colorspace_name in self.encoded_spaces:
            return True
        
        # Linear spaces are not encoded
        if "Linear" in colorspace_name:
            return False
            
        # Default encoding status for common colorspaces
        default_encoded = {
            "sRGB": True,
            "Rec.709": True,
            "Display P3": True,
            "Rec.2020": True,
            "Adobe RGB": True,
            "ACES2065-1": False,  # Linear by default
            "ACEScg": False,      # Linear by default
            "Raw": False          # Raw is always linear
        }
        
        # Check if the colorspace is in the default encoding status dictionary
        if colorspace_name in default_encoded:
            return default_encoded[colorspace_name]
            
        # For unknown colorspaces, assume they are linear
        return False

    def _apply_gamma_encoding(self, rgb: np.ndarray, colorspace: str) -> np.ndarray:
        """Apply appropriate gamma encoding based on colorspace."""
        # Handle standard colorspaces
        if colorspace == "sRGB" or "sRGB" in colorspace and "Linear" not in colorspace:
            # Apply sRGB EOTF (gamma curve)
            return colour.models.eotf_sRGB(rgb)
        elif colorspace == "Rec.709" or "Rec.709" in colorspace and "Linear" not in colorspace:
            # Rec.709 uses the same EOTF as sRGB
            return colour.models.eotf_sRGB(rgb)
        elif colorspace == "Display P3" or "Display P3" in colorspace and "Linear" not in colorspace:
            # Display P3 uses the same EOTF as sRGB
            return colour.models.eotf_sRGB(rgb)
        elif colorspace == "Rec.2020" or "Rec.2020" in colorspace and "Linear" not in colorspace:
            # Rec.2020 uses a slightly different EOTF, but we'll use sRGB for simplicity
            return colour.models.eotf_sRGB(rgb)
        elif colorspace == "Adobe RGB" or "Adobe RGB" in colorspace and "Linear" not in colorspace:
            # Adobe RGB uses a gamma of 2.2
            return np.power(np.maximum(rgb, 0), 1/2.2)
            
        # Handle ACES colorspaces
        elif colorspace == "ACEScc":
            # Apply ACEScc encoding (log encoding for ACES)
            return colour.models.log_encoding_ACEScc(rgb)
        elif colorspace == "ACEScct":
            # Apply ACEScct encoding (log encoding with toe for ACEScg)
            return colour.models.log_encoding_ACEScct(rgb)
            
        # Handle other gamma values
        elif "Gamma 2.2" in colorspace:
            return np.power(np.maximum(rgb, 0), 1/2.2)
        elif "Gamma 2.4" in colorspace:
            return np.power(np.maximum(rgb, 0), 1/2.4)
            
        # Linear colorspaces don't need encoding
        else:
            return rgb

    def _apply_gamma_decoding(self, rgb: np.ndarray, colorspace: str) -> np.ndarray:
        """Apply appropriate gamma decoding based on colorspace."""
        # Handle standard colorspaces
        if colorspace == "sRGB" or "sRGB" in colorspace and "Linear" not in colorspace:
            # Apply inverse sRGB EOTF
            return colour.models.eotf_inverse_sRGB(rgb)
        elif colorspace == "Rec.709" or "Rec.709" in colorspace and "Linear" not in colorspace:
            # Rec.709 uses the same EOTF as sRGB
            return colour.models.eotf_inverse_sRGB(rgb)
        elif colorspace == "Display P3" or "Display P3" in colorspace and "Linear" not in colorspace:
            # Display P3 uses the same EOTF as sRGB
            return colour.models.eotf_inverse_sRGB(rgb)
        elif colorspace == "Rec.2020" or "Rec.2020" in colorspace and "Linear" not in colorspace:
            # Rec.2020 uses a slightly different EOTF, but we'll use sRGB for simplicity
            return colour.models.eotf_inverse_sRGB(rgb)
        elif colorspace == "Adobe RGB" or "Adobe RGB" in colorspace and "Linear" not in colorspace:
            # Adobe RGB uses a gamma of 2.2
            return np.power(np.maximum(rgb, 0), 2.2)
            
        # Handle ACES colorspaces
        elif colorspace == "ACEScc":
            # Apply ACEScc decoding (inverse log encoding for ACES)
            return colour.models.log_decoding_ACEScc(rgb)
        elif colorspace == "ACEScct":
            # Apply ACEScct decoding (inverse log encoding with toe for ACEScg)
            return colour.models.log_decoding_ACEScct(rgb)
            
        # Handle other gamma values
        elif "Gamma 2.2" in colorspace:
            return np.power(np.maximum(rgb, 0), 2.2)
        elif "Gamma 2.4" in colorspace:
            return np.power(np.maximum(rgb, 0), 2.4)
            
        # Linear colorspaces don't need decoding
        else:
            return rgb

    def convert_colorspace(self, images: torch.Tensor, from_colorspace: str, to_colorspace: str) -> Tuple[torch.Tensor]:
        """
        Convert images between colorspaces using colour-science library.
        
        Args:
            images: Input images as torch tensor [B, H, W, C]
            from_colorspace: Source colorspace name
            to_colorspace: Target colorspace name
            
        Returns:
            Tuple containing the converted images as torch tensor
        """
        # Log batch processing info
        log_batch_processing(images, f"Converting from '{from_colorspace}' to '{to_colorspace}'", "input")
        
        # If source and target are the same, return original
        if from_colorspace == to_colorspace:
            logger.info("Source and target colorspaces are the same")
            return (images,)
        
        # Convert to numpy
        img_np = images.cpu().numpy()
        logger.info(f"Input range: min={img_np.min():.6f}, max={img_np.max():.6f}")
        
        # Handle problematic values
        if np.isnan(img_np).any() or np.isinf(img_np).any():
            logger.warning("Input contains NaN/Inf values, cleaning...")
            img_np = np.nan_to_num(img_np, nan=0.0, posinf=1.0, neginf=0.0)
            images = torch.from_numpy(img_np).to(images.device)
        
        try:
            # Handle special cases first
            if from_colorspace == "Raw" or to_colorspace == "Raw":
                logger.info("Raw colorspace detected, returning input unchanged")
                return (images,)
            
            # Get the colour-science colorspace names
            from_cs = self.colorspace_mapping.get(from_colorspace)
            to_cs = self.colorspace_mapping.get(to_colorspace)
            
            if not from_cs or not to_cs:
                logger.error(f"Unsupported colorspaces: {from_colorspace} -> {to_colorspace}")
                return (images,)
            
            # Handle encoding/decoding
            working_img = img_np.copy()
            
            # Step 1: Decode input if it's encoded
            if self._is_encoded_colorspace(from_colorspace):
                logger.info(f"Decoding {from_colorspace}")
                working_img = self._apply_gamma_decoding(working_img, from_colorspace)
            
            # Step 2: Convert between colorspaces (linear to linear)
            if from_cs != to_cs and from_cs != "Raw" and to_cs != "Raw":
                logger.info(f"Converting colorspace: {from_cs} -> {to_cs}")
                
                # Handle special case where both map to same underlying space
                if from_cs == to_cs:
                    logger.info("Same underlying colorspace, skipping conversion")
                else:
                    # Use batch processing utilities for reshaping
                    working_tensor = torch.from_numpy(working_img)
                    rgb_data, alpha_channel, original_shape = BatchProcessor.reshape_for_processing(
                        working_tensor, preserve_alpha=True
                    )
                    
                    # Apply the colorspace conversion
                    try:
                        converted_rgb = colour.RGB_to_RGB(
                            rgb_data,
                            input_colourspace=from_cs,
                            output_colourspace=to_cs,
                            apply_cctf_decoding=False,  # We handle encoding separately
                            apply_cctf_encoding=False
                        )
                        logger.info("Colorspace conversion successful")
                    except Exception as e:
                        logger.error(f"Colour-science conversion failed: {e}")
                        # Try with chromatic adaptation
                        try:
                            converted_rgb = colour.RGB_to_RGB(
                                rgb_data,
                                input_colourspace=from_cs,
                                output_colourspace=to_cs,
                                apply_cctf_decoding=False,
                                apply_cctf_encoding=False,
                                chromatic_adaptation_transform='CAT02'
                            )
                            logger.info("Colorspace conversion with CAT02 successful")
                        except Exception as e2:
                            logger.error(f"All conversion attempts failed: {e2}")
                            # Return original image
                            return (images,)
                    
                    # Use batch processing utilities to reshape back
                    working_tensor = BatchProcessor.reshape_from_processing(
                        converted_rgb, alpha_channel, original_shape, images.device
                    )
                    working_img = working_tensor.cpu().numpy()
            
            # Step 3: Encode output if needed
            if self._is_encoded_colorspace(to_colorspace):
                logger.info(f"Encoding to {to_colorspace}")
                working_img = self._apply_gamma_encoding(working_img, to_colorspace)
            
            # Handle clipping based on colorspace
            # For HDR colorspaces like ACES, we don't want to clip to 0-1
            is_hdr_colorspace = any(hdr_space in to_colorspace for hdr_space in ["ACES", "Raw", "Linear"])
            
            if not is_hdr_colorspace:
                # For display-referred spaces, clip to 0-1
                working_img = np.clip(working_img, 0.0, 1.0)
            else:
                # For HDR/scene-referred spaces, just ensure no negative values
                working_img = np.maximum(working_img, 0.0)
                
                # Log if we have values > 1.0 (common in HDR)
                if np.any(working_img > 1.0):
                    max_val = np.max(working_img)
                    logger.info(f"HDR values detected: max={max_val:.6f}")
            
            # Convert back to torch tensor
            result_tensor = torch.from_numpy(working_img).to(images.device)
            
            logger.info(f"Output range: min={result_tensor.min().item():.6f}, max={result_tensor.max().item():.6f}")
            
            return (result_tensor,)
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return (images,)

# Test function to verify colour-science setup
def test_colour_science_setup():
    """Test that colour-science is working correctly."""
    try:
        # Test basic functionality
        test_rgb = np.array([[[0.18, 0.18, 0.18]]])
        
        # Test sRGB encoding
        encoded = colour.models.eotf_sRGB(test_rgb)
        print(f"sRGB encoding test: {test_rgb.flatten()} -> {encoded.flatten()}")
        
        # Test colorspace conversion
        converted = colour.RGB_to_RGB(
            test_rgb,
            input_colourspace='ITU-R BT.709',
            output_colourspace='ACEScg',
            apply_cctf_decoding=False,
            apply_cctf_encoding=False
        )
        print(f"Rec.709 to ACEScg: {test_rgb.flatten()} -> {converted.flatten()}")
        
        print("colour-science setup test passed!")
        return True
        
    except Exception as e:
        print(f"colour-science setup test failed: {e}")
        return False

# Register the node
# NODE_CLASS_MAPPINGS = {
#     "ColorspaceNode": colorspace,
# }

# NODE_DISPLAY_NAME_MAPPINGS = {
#     "ColorspaceNode": "Colorspace",
# }

if __name__ == "__main__":
    test_colour_science_setup()
