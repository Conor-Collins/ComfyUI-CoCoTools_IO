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
- **Path tokens** — dynamic tokens in saver output paths for dates, filenames, and layer names

## Path Tokens (Image Saver)

The Image Saver supports token-based path templating in both the **file_path** (directory) and **filename** fields. Tokens are resolved at save time.

### Supported Tokens

| Token | Example Output | Description |
|-------|---------------|-------------|
| `%date%` | `2026-03-14` | Current date (ISO format) |
| `%date:dd-MM-yyyy%` | `14-03-2026` | Current date (custom format) |
| `%date:yyyyMMdd%` | `20260314` | Current date (compact) |
| `%time%` | `15-30-45` | Current time (HH-mm-ss) |
| `%time:HH-mm%` | `15-30` | Current time (custom format) |
| `%filename%` | `beauty_pass` | Base name of connected input image (requires `source_path` input) |
| `%layer%` | `diffuse` | Layer name from connected EXR data (requires `layer_name` input) |

### Format Placeholders

`yyyy` (year), `MM` (month), `dd` (day), `HH` (hour), `mm` (minute), `ss` (second)

### Examples

| file_path | filename | Result |
|-----------|----------|--------|
| `Maps/%date:dd-MM-yyyy%` | `depth_0001` | `Maps/14-03-2026/depth_0001.exr` |
| `renders/%date%` | `%filename%_####` | `renders/2026-03-14/beauty_pass_0001.exr` |
| `%date:yyyyMMdd%_%time:HH-mm%` | `%layer%` | `20260314_15-30/diffuse.exr` |

To use `%filename%` or `%layer%`, connect the optional **source_path** or **layer_name** string inputs on the Image Saver node from an upstream loader. If not connected, these tokens resolve to `FILENAME_MISSING` or `LAYER_MISSING`.

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
