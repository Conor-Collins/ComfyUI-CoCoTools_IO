# ComfyUI-CoCoTools_IO

A set of nodes focused on advanced image I/O operations, particularly for EXR file handling.

## Features
- Advanced EXR image input with multilayer support
- EXR layer extraction and manipulation
- High-quality image saving with format-specific options
- Standard image format loading with bit depth awareness


## Installation for comfyui portable (tested on 0.3.14)

from the python_embeded/ folder

```bash
python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-CoCoTools/requirements.txt
```

### Manual Installation
1. Clone the repository into your ComfyUI `custom_nodes` directory
2. Install dependencies
3. Restart ComfyUI



## Current Nodes

### Image I/O
- **Image Loader**: Load standard image formats (PNG, JPG, WebP, etc.) with proper bit depth handling
- **Load EXR**: Comprehensive EXR file loading with support for multiple layers, channels, and cryptomatte data
- **Load EXR Layer by Name**: Extract specific layers from EXR files (similar to Nuke's Shuffle node)
- **Cryptomatte Layer**: Specialized handling for cryptomatte layers in EXR files
- **Image Saver**: Save images in various formats with format-specific options (bit depth, compression, etc.)

### Image Processing
- **Colorspace**: Convert between sRGB and Linear colorspaces
- **Z Normalize**: Normalize depth maps and other single-channel data


## To-Do
#### IO
- [x] Implement proper EXR loading
- [ ] Implement EXR sequence loader
- [x] Implement EXR saver using OpenImageIO
- [x] Implement multilayer EXR system (render passes, AOVs, embedded images, etc.)
- [x] Add contextual menus based on selected file type in saver
- [ ] Add support for EXR sequences

#### Future Enhancements
- [ ] Add ACES or OCIO color config profiles
- [ ] Create frequency-based image processing tools
- [ ] Restore additional utility nodes (JSON handling, regex, etc.)

#### Documentation
- [ ] Add more detailed information on each node
- [ ] Add more example workflows
- [ ] Add visual examples in the readme

#### Registration
- [x] Submit to ComfyUI Registry
