# CoCoTools_IO

Advanced image I/O nodes for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — professional EXR handling, multilayer support, color science, and scopes.

## Installation

### ComfyUI Registry (Recommended)

Search for **CoCoTools_IO** in the [Comfy Registry](https://comfyregistry.org) or ComfyUI Manager and install directly.

### Manual Installation

1. Clone the repository into your ComfyUI `custom_nodes` directory:
    ```bash
    cd ComfyUI/custom_nodes
    git clone https://github.com/Conor-Collins/ComfyUI-CoCoTools_IO.git
    ```
2. Install dependencies from the `python_embeded/` folder (portable) or your Python environment:
    ```bash
    python -m pip install -r ComfyUI/custom_nodes/ComfyUI-CoCoTools_IO/requirements.txt
    ```
3. Restart ComfyUI

### Beta Branch

The `beta` branch contains the latest features and fixes ahead of the stable release. To use it:
```bash
cd ComfyUI/custom_nodes/ComfyUI-CoCoTools_IO
git checkout beta
```

## Nodes

### Image I/O

| Node | Description |
|------|-------------|
| **Image Loader** | Load standard formats (PNG, JPG, TIFF, WebP) with proper bit depth handling (8/16/32-bit) |
| **Load EXR** | Load EXR files with full multilayer, multichannel, and cryptomatte support |
| **Load EXR Sequence** | Batch-load EXR sequences using `####` frame patterns with missing frame recovery |
| **Load EXR Layer by Name** | Extract specific layers from EXR layer dictionaries (similar to Nuke's Shuffle node) |
| **Cryptomatte Layer** | Interactive click-to-matte selection with zebra stripe preview overlay |
| **Image Saver** | Save to EXR, PNG, TIFF, JPG, or WebP with format-specific options (bit depth, compression, quality) |

### Image Processing

| Node | Description |
|------|-------------|
| **Colorspace Converter** | Convert between colorspaces: ACES2065-1, ACEScg, ACEScct, ACEScc, sRGB, Rec.709, Display P3, Rec.2020, Adobe RGB (linear and encoded variants) |
| **Z Normalize** | Normalize depth maps and single-channel data to a target range |

### Scopes

| Node | Description |
|------|-------------|
| **Histogram** | Per-channel histogram display (L/RGB/R/G/B/A) with log/linear toggle and bit depth estimation |
| **Vectorscope** | Chromaticity scatter display with YCbCr, HSV, and CIE xy color models, skin tone line, and gamut overlays |

## Features

- **Multilayer EXR** — full subimage and channel group support for render passes, AOVs, and embedded layers
- **Cryptomatte** — click-to-matte pixel picking with interactive preview canvas
- **Batch sequences** — `####` frame patterns with configurable start/end/step and white frame placeholders for missing files
- **Dynamic file browser** — interactive file/folder selection for load and save nodes
- **Format-aware saving** — per-format widgets for bit depth (8/16/32), EXR compression (zip, zips, dwaa, etc.), and JPEG/WebP quality

## Dependencies

- `torch >= 1.10.0`
- `numpy >= 1.21.0`
- `colour-science >= 0.4.2`
- `Pillow >= 9.0.0`
- `opencv-python >= 4.5.0`
- `tifffile`
- `OpenImageIO >= 2.4.13.0`
- `rich >= 10.0.0`

## Third-Party Libraries and Licensing

This project uses the following third-party libraries:

- **Colour Science for Python**: Colorspace transformations. Licensed under the New BSD License.
- **OpenColorIO**: Color space transformations. Licensed under the BSD 3-Clause License.

For detailed licensing information, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

This project is licensed under the MIT License.
