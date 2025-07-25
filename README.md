# CoCoTools_IO

A set of nodes focused on advanced image I/O operations, particularly for EXR file handling.

## Features
- Advanced EXR image input with multilayer support
- EXR layer extraction and manipulation
- High-quality image saving with format-specific options
- Standard image format loading with bit depth awareness


## Installation for comfyui portable (tested on 0.3.44)



### Manual Installation
1. Clone the repository into your ComfyUI `custom_nodes` directory
2. Install dependencies
    from the python_embeded/ folder

    ```bash
    python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-CoCoTools/requirements.txt
    ```
3. Restart ComfyUI



## Current Nodes

### Image I/O
- **Image Loader**: Load standard image formats (PNG, JPG, WebP, etc.) with proper bit depth handling
- **Load EXR**: Comprehensive EXR file loading with support for multiple layers, channels, and cryptomatte data
- **Load EXR Sequence**: Load EXR image sequences with #### frame patterns and batch processing
- **Load EXR Layer by Name**: Extract specific layers from EXR files (similar to Nuke's Shuffle node)
- **Cryptomatte Layer**: Specialized handling for cryptomatte layers in EXR files (WIP - not fully implemented)
- **Image Saver**: Save images in various formats with format-specific options (bit depth, compression, etc.)

### Image Processing
- **Colorspace Converter**: Convert between various colorspaces (sRGB, Linear, ACEScg, etc.)
- **Z Normalize**: Normalize depth maps and other single-channel data


## To-Do
#### IO
- [x] Implement proper EXR loading
- [x] Implement EXR sequence loader
- [x] Implement EXR saver using OpenImageIO
- [x] Implement multilayer EXR system (render passes, AOVs, embedded images, etc.)
- [x] Add contextual menus based on selected file type in saver
- [x] Add support for EXR sequences
- [ ] Complete cryptomatte layer implementation
- [ ] Adopt filename parsing for saving files into datestamped folders



## Third-Party Libraries and Licensing

This project uses the following third-party libraries:

- **Colour Science for Python**: Used for colorspace transformations in the Colorspace Converter node. Licensed under the New BSD License.
- **OpenColorIO**: Used for color space transformations. Licensed under the BSD 3-Clause License.

For detailed licensing information, please see the [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) file.

This project is licensed under the MIT License. The BSD 3-Clause License used by OpenColorIO and the New BSD License used by colour-science are compatible with the MIT License, allowing us to include and use these components within this MIT-licensed project.
