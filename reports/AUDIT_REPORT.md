# CoCoTools_IO Modernization Audit Report

**Date**: 2026-02-20
**Version Audited**: 0.4.2
**Last Updated**: ~October 2025 (5 months stale)

---

## Table of Contents

1. [Errors and Mishandled Areas](#1-errors-and-mishandled-areas)
2. [Bit Depth Output/Settings Analysis](#2-bit-depth-outputsettings-analysis)
3. [Modernization Complexity Assessment](#3-modernization-complexity-assessment)
4. [Virtual ComfyUI Tester Feasibility](#4-virtual-comfyui-tester-feasibility)
5. [OpenEXR Migration Feasibility](#5-openexr-migration-feasibility)
6. [Cryptomatte Masking Implementation](#6-cryptomatte-masking-implementation)
7. [Dynamic Outputs for EXR Channels](#7-dynamic-outputs-for-exr-channels)
8. [OpenEXR vs OIIO Performance Analysis](#8-openexr-vs-oiio-performance-analysis)
9. [Preview System Optimization for Sequences](#9-preview-system-optimization-for-sequences)

---

## 1. Errors and Mishandled Areas

### Critical Issues

#### 1.1 `index.js` imports a non-existent file
**File**: `js/index.js:3`
```js
import "./load_exr.js";
```
This file does not exist in `js/`. Only `saver.js` and `load_exr_layer_by_name.js` exist. This will cause a JavaScript import error on load, potentially breaking all JS extensions for the package.

**Severity**: HIGH - Could prevent JS widgets from loading entirely.

#### 1.2 Colorspace `_apply_gamma_encoding` uses EOTF instead of OETF
**File**: `modules/colorspace.py:162-196`

The method `_apply_gamma_encoding` is supposed to encode linear values to display gamma, but it calls `colour.models.eotf_sRGB()` (Electro-Optical Transfer Function), which *decodes* gamma to linear. The encoding method should use `colour.models.eotf_inverse_sRGB()` (OETF-equivalent).

Similarly, `_apply_gamma_decoding` (lines 198-233) calls `eotf_inverse_sRGB()` which encodes, when it should decode.

**The encoding and decoding functions are swapped.** This means every colorspace conversion that involves gamma will produce incorrect results.

```python
# Current (WRONG):
def _apply_gamma_encoding(self, rgb, colorspace):
    return colour.models.eotf_sRGB(rgb)  # This DECODES, not encodes

def _apply_gamma_decoding(self, rgb, colorspace):
    return colour.models.eotf_inverse_sRGB(rgb)  # This ENCODES, not decodes
```

**Severity**: CRITICAL - All colorspace conversions involving gamma are producing wrong results.

#### 1.3 Operator precedence bug in colorspace conditionals
**File**: `modules/colorspace.py:164,167,171,173,201,204,208,210,213`

Multiple conditionals like:
```python
if colorspace == "sRGB" or "sRGB" in colorspace and "Linear" not in colorspace:
```
Due to Python operator precedence, `and` binds tighter than `or`, so this evaluates as:
```python
if colorspace == "sRGB" or ("sRGB" in colorspace and "Linear" not in colorspace):
```
While this happens to work for "sRGB" (the exact match catches it), the pattern is dangerous and misleading for Rec.709, Display P3, etc. The intent was likely:
```python
if (colorspace == "sRGB" or "sRGB" in colorspace) and "Linear" not in colorspace:
```

**Severity**: MEDIUM - Could cause unexpected behavior for some colorspace selections.

#### 1.4 `prepare_image` clips EXR data to [0,1] range
**File**: `modules/saver.py:167`
```python
img_np = np.clip(img_np, 0, 1).astype(np.float32)
```
EXR files should preserve full HDR range. Clipping to [0,1] before saving EXR destroys HDR data. The clip should only apply to non-HDR formats (PNG, JPG, TIFF 8/16-bit).

**Severity**: HIGH - Destroys HDR data when saving EXR files.

#### 1.5 `ImageLoader.normalize_image` can produce all-zeros
**File**: `modules/image_loader.py:94-95`
```python
return (image - min_val) / (max_val - min_val) if min_val != max_val else torch.zeros_like(image)
```
When all pixels are the same value (e.g., a solid white image), this returns all zeros instead of preserving the value. A solid white image becomes solid black.

**Severity**: MEDIUM - Solid color images are destroyed by normalization.

#### 1.6 `ImageLoader` double-normalizes when `normalize=True`
**File**: `modules/image_loader.py:62-74`

The `pil2tensor` method already converts to [0,1] range (line 125: `/255.0`), and then `normalize_image` is applied on top, which remaps the actual min/max to [0,1]. This double-normalization changes the meaning of pixel values. A dark image (e.g., all pixels at value 10/255) would be stretched to fill [0,1].

**Severity**: MEDIUM - Double normalization distorts image values.

#### 1.7 `ImageLoader.detect_bit_depth` always returns 8-bit for RGB
**File**: `modules/image_loader.py:102-116`

After `img.convert("RGB")` on line 58, the mode is always `"RGB"` regardless of the original bit depth. The detection runs on the already-converted image, so 16-bit PNGs and 32-bit TIFFs will be incorrectly treated as 8-bit.

The `format` attribute is also lost after `.convert("RGB")` since PIL doesn't preserve it.

**Severity**: HIGH - 16-bit and 32-bit images lose precision during loading.

#### 1.8 Saver's `save_mode_widgets` and `versioning_widgets` use non-standard `formats` key
**File**: `modules/saver.py:91-98`

The `formats` key in INPUT_TYPES metadata is non-standard ComfyUI API. This relies entirely on the custom JS in `saver.js` to parse. If the JS fails to load (see issue 1.1), these widgets won't appear and the save_mode/versioning parameters may be missing.

**Severity**: MEDIUM - Widget system fragile, depends on custom JS.

#### 1.9 JS: `isCryptomatte` variable out of scope in `setup()`
**File**: `js/load_exr_layer_by_name.js:243`
```javascript
const matchedNodes = findNodes(isCryptomatte ? "CryptomatteLayer" : "LoadExrLayerByName");
```
`isCryptomatte` is defined inside `beforeRegisterNodeDef` (line 11) but referenced in `setup()` (line 240), which is a sibling method outside that closure. This causes a `ReferenceError` at runtime when the graph executes, breaking the layer update listener.

**Severity**: HIGH - Layer auto-discovery breaks at runtime.

#### 1.10 `process_layer_groups` stores lists instead of tensors in cryptomatte_dict
**File**: `utils/exr_utils.py:426`
```python
cryptomatte_dict[group_name] = [cryptomatte_dict.get(part, None) for part in suffixes]
```
Stores a Python list of tensors/None values instead of a single tensor. Downstream code in `load_exr_sequence.py` calls `torch.cat()` on cryptomatte_dict entries, which will crash on a list containing None values.

**Severity**: HIGH - Sequence loading with cryptomatte layer groups will crash.

#### 1.11 `process_exr_data` calls `get_channel_groups` twice for subimage 0
**File**: `utils/exr_utils.py:585,652`

The `channel_groups` variable is computed twice for the first subimage: once at line 585 and again at line 652. The second call overwrites the first but both do identical work. Additionally, `channel_groups` at line 708 could reference the variable from the wrong scope if there's only one subimage.

**Severity**: LOW - Redundant computation, minor performance impact.

#### 1.12 `process_exr_data` may reference `rgb_tensor`/`alpha_tensor` before assignment
**File**: `utils/exr_utils.py:727`

If there are no subimages in the metadata (empty `subimages` list), the code reaches line 727 where `rgb_tensor` and `alpha_tensor` are referenced but were never assigned. This would raise `UnboundLocalError`.

**Severity**: LOW - Edge case, unlikely with valid EXR files.

#### 1.13 Metadata JSON serialization may fail with OIIO types
**File**: `utils/exr_utils.py:713`
```python
metadata_json = json.dumps(metadata)
```
The `metadata` dict may contain OIIO attribute values that aren't JSON serializable (numpy types, Imath types), causing `TypeError` at runtime.

**Severity**: MEDIUM - Could crash on EXR files with certain metadata attributes.

#### 1.14 `replace_frame_number` replaces ALL digit sequences
**File**: `utils/sequence_utils.py:57-67`

The pattern `r'#+|\d+'` matches both `####` placeholders AND any existing digits in the filename. A filename like `shot25_####.exr` would have `25` replaced with the frame number too, producing `shot0001_0001.exr` instead of `shot25_0001.exr`.

**Severity**: HIGH - Frame numbering corrupts filenames containing digits.

#### 1.15 EXR 16-bit uses numpy float16 before OIIO
**File**: `modules/saver.py:183`
```python
data = img.astype(np.float16)
```
OIIO typically expects float32 input and handles half-float conversion internally based on the pixel type spec. Passing numpy float16 may cause precision issues or silent data corruption depending on OIIO version.

**Severity**: MEDIUM - May cause subtle precision loss in half-float EXR output.

#### 1.16 `LoadExrLayerByName.process_layer` returns list instead of tuple
**File**: `modules/load_exr_layer_by_name.py:242`

ComfyUI expects `FUNCTION` methods to return tuples matching `RETURN_TYPES`. This node returns lists like `[image_output, mask_output]`. While Python may coerce these in some contexts, it's technically incorrect.

**Severity**: LOW - Works in practice but violates ComfyUI convention.

#### 1.17 ImageLoader alpha tensor shape mismatch
**File**: `modules/image_loader.py:67`
```python
alpha_tensor = self.pil2tensor(img.split()[-1], bit_depth).unsqueeze(-1)
```
`pil2tensor` returns `[1, H, W]` for a single-channel image, then `.unsqueeze(-1)` produces `[1, H, W, 1]`. ComfyUI's MASK type expects `[B, H, W]` (3D). The extra trailing dimension may cause issues with downstream mask-consuming nodes.

**Severity**: MEDIUM - Mask shape incompatibility with standard ComfyUI expectations.

#### 1.18 XYZ layer normalization is scalar, not per-vector
**File**: `utils/exr_utils.py:306-309`
```python
max_abs = xyz_tensor.abs().max()
if max_abs > 0:
    xyz_tensor = xyz_tensor / max_abs
```
Normal maps are normalized by dividing all values by a single global scalar maximum. Proper normal map normalization should be per-vector (each pixel's XYZ vector normalized to unit length). The current approach distorts normal vectors.

**Severity**: MEDIUM - Normal/vector data incorrect after normalization.

#### 1.19 `detect_sequence_pattern` is too broad
**File**: `utils/sequence_utils.py:30`
```python
return bool(re.search(r'#+', path))
```
Matches a single `#` anywhere in the path. A path like `/my#project/image.exr` or even `C:\Users\#admin\file.exr` would be falsely detected as a sequence pattern.

**Severity**: MEDIUM - False positive sequence detection on paths with `#` characters.

#### 1.20 `find_sequence_files` only handles `####` pattern
**File**: `utils/sequence_utils.py:90-106`

The glob replacement and regex only handle exactly four `#` characters (`####`). Patterns like `###` (3-digit) or `#####` (5-digit) won't work correctly - the glob will match but the regex validation will reject valid files.

**Severity**: MEDIUM - Only 4-digit padding supported despite documentation suggesting `###` works.

#### 1.21 `extract_frame_number_from_path` fragile heuristic
**File**: `utils/sequence_utils.py:72-83`

The heuristic prioritizes 3-4 digit numbers but can pick wrong numbers. For `render_1080p_0001.exr`, it finds `['1080', '0001']`, reversed iteration checks `0001` first (4 digits, matches) but `1080` is also 4 digits. For `render_1080p_01.exr`, it would return `1080` instead of `01`.

**Severity**: MEDIUM - Frame number extraction fails for filenames with resolution numbers.

### Code Quality Issues

#### 1.22 `ColorspaceNode.INPUT_TYPES` creates instance in classmethod
**File**: `modules/colorspace.py:86-87`
```python
@classmethod
def INPUT_TYPES(cls):
    instance = cls()
```
Creating an instance inside a classmethod is wasteful. The colorspace list should be a class-level constant.

#### 1.23 Excessive fallback/try-except patterns
Every module has large try/except import blocks with inline fallback function definitions. While defensive, this creates maintenance burden and can mask real import errors during development.

#### 1.24 Commented-out NODE_CLASS_MAPPINGS in every module
Dead code artifacts at the bottom of every module file. Should be removed.

#### 1.25 `is_grayscale_fast` uses random sampling
**File**: `modules/saver.py:120-136`
The `np.random.choice` call is non-deterministic, meaning the same image could produce different grayscale detection results on different runs. Should use a fixed seed or deterministic sampling pattern.

#### 1.26 `WEB_DIRECTORY` uses absolute path
**File**: `__init__.py:18`
```python
WEB_DIRECTORY = os.path.join(NODE_DIR, "js")
```
Some ComfyUI versions expect relative paths like `"./js"`. Modern ComfyUI supports automatic web directory detection via `pyproject.toml`.

#### 1.27 Save mode/versioning dynamic widgets not handled by JS
**File**: `modules/saver.py:89-98` vs `js/saver.js`
The `save_mode` and `use_versioning` inputs have `"formats"` keys for dynamic widgets, but `saver.js` only handles the `file_type` format switching. The save_mode/versioning dynamic widgets never show/hide.

#### 1.28 Rec.2020 uses wrong transfer function
**File**: `modules/colorspace.py:174`
Rec.2020 has a distinct transfer function (BT.1886/BT.2020) but the code uses sRGB EOTF "for simplicity". This introduces visible inaccuracy for wide-gamut content.

#### 1.29 Bare `except:` in IS_CHANGED pixel sampling
**Files**: `modules/colorspace.py:123`, `modules/znormalize.py:80`
Silently swallows all exceptions during pixel sampling. Should use specific exception types.

### Issue Count Summary

| Severity | Count |
|----------|-------|
| Critical | 2 (gamma swap, JS missing file) |
| High | 6 (HDR clip, bit depth, frame regex, JS scope, cryptomatte list, sequence pattern) |
| Medium | 11 (operator precedence, normalization, float16, metadata JSON, alpha shape, XYZ normalize, etc.) |
| Low/Quality | 10 (return types, dead code, comments, sampling, etc.) |
| **Total** | **29** |

---

## 2. Bit Depth Output/Settings Analysis

### Format-by-Format Analysis

| Format | Declared Depths | Conversion Math | OIIO/lib Config | Correct? |
|--------|----------------|-----------------|------------------|----------|
| **EXR 16** | half float | `np.float16` | `oiio.HALF` | PARTIAL - float16 before OIIO is risky |
| **EXR 32** | full float | `np.float32` | `oiio.FLOAT` | YES - but input clipped to [0,1] |
| **PNG 8** | uint8 | `img * 255 → uint8` | `oiio.UINT8` | YES |
| **PNG 16** | uint16 | `img * 65535 → uint16` | `oiio.UINT16` | YES |
| **TIFF 8** | uint8 | `img * 255 → uint8` | tifffile | YES |
| **TIFF 16** | uint16 | `img * 65535 → uint16` | tifffile | YES |
| **TIFF 32** | float32 | `img.astype(float32)` | tifffile | YES |
| **JPG** | 8 only | `img * 255 → uint8` | OpenCV | YES |
| **WebP** | 8 only | `img * 255 → uint8` | OpenCV | YES |

### Issues Found

1. **EXR HDR data loss**: `prepare_image()` clips ALL formats to [0,1] before format-specific saving. EXR 16 and 32 should preserve full float range.

2. **EXR 16-bit numpy conversion**: Passing float16 to OIIO instead of letting OIIO handle the conversion from float32 to half. May cause precision issues.

3. **PNG bit depth fallback is silent**: If an unsupported bit depth gets through validation, PNG falls back to 8-bit without warning.

4. **Loading bit depth detection broken for ImageLoader**: 16-bit PNGs loaded through ImageLoader get treated as 8-bit (issue 1.7). EXR loaders are unaffected since they read float data directly.

5. **TIFF RGBA not handled**: No handling for 4-channel TIFF. `photometric='rgb'` is set for 3+ channels but RGBA needs explicit alpha handling.

### Verdict

The bit depth pipeline is **mostly correct for saver output math**, with the critical exception of EXR HDR clipping. The ImageLoader's bit depth detection is fundamentally broken for non-8-bit images. EXR loading through the dedicated EXR nodes works correctly.

---

## 3. Modernization Complexity Assessment

### Current ComfyUI API State (as of Feb 2026)

Based on documentation analysis:

**V1 API (Current - Still Supported):**
- **`pyproject.toml`**: Required for registry publishing with `[tool.comfy]` section. CoCoTools has this but needs fields updated for current registry standards.
- **Lazy evaluation**: Supported via `{"lazy": True}` in input config + `check_lazy_status()` method. Not yet adopted here. Low cost to implement, recommended for optional inputs.
- **`VALIDATE_INPUTS`**: Classmethod for input validation before execution. Not used.
- **`DESCRIPTION`**: Class attribute for node documentation in the UI. Not used.
- **`IS_CHANGED`**: Still supported. Returns a fingerprint value (NOT a boolean). `float("NaN")` for always-execute is correct.
- **Hidden inputs**: `UNIQUE_ID`, `PROMPT`, `EXTRA_PNGINFO`, `DYNPROMPT` available.
- **Wildcard type (`*`)**: Supported for inputs/outputs that accept any type.
- **Dynamic inputs**: `ContainsAnyDict` pattern for accepting arbitrary kwargs.

**V3 API (New - Future Direction):**
- **All new features are V3-only.** V1 continues to work but is effectively frozen.
- **Stateless execution**: Nodes inherit from `io.ComfyNode`, execute is `@classmethod`
- **Unified `define_schema()`**: Replaces 7 separate class properties (`INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`, `CATEGORY`, etc.)
- **Dynamic I/O (V3 only)**:
  - `Autogrow`: Variable-length input lists with templates
  - `DynamicCombo`: Show/hide inputs based on dropdown selection
  - `MatchType`: Enforce type consistency at runtime
- **Async execution**: `async def execute()` with `await` support
- **`fingerprint_inputs()`**: V3 rename of `IS_CHANGED` with clearer semantics
- **`ComfyExtension`**: New registration pattern replacing `NODE_CLASS_MAPPINGS`
- **API is still stabilizing** (current version `v0_0_2`)

**Breaking Changes Since Oct 2025:**
- **Nodes 2.0 Frontend**: LiteGraph Canvas → Vue-based architecture. Legacy Canvas still toggleable.
- **v0.3.75 (Nov 2025)**: 47 new node types, legacy sampler nodes deprecated
- **PyTorch 2.4+** now required
- **Caching changes**: New EasyCache & LazyCache systems, dependency-aware caching fixes
- **`pyproject.toml` web folder auto-registration** (v0.3.41) - `WEB_DIRECTORY` may not be needed

### Modernization Tasks (Ranked by Complexity)

#### Low Complexity (1-2 days each)
1. Fix `index.js` broken import
2. Fix colorspace gamma swap
3. Fix operator precedence bugs
4. Fix EXR HDR clipping
5. Fix `replace_frame_number` regex
6. Clean up commented-out code
7. Fix return types (list to tuple)
8. Add `DESCRIPTION` class attribute to all nodes
9. Update `pyproject.toml` for registry compliance

#### Medium Complexity (3-5 days each)
10. Fix ImageLoader bit depth detection
11. Modernize INPUT_TYPES patterns (class-level constants)
12. Add `VALIDATE_INPUTS` classmethod to nodes
13. Improve error handling (meaningful errors instead of empty tensors)
14. Add lazy evaluation where appropriate
15. Update JS to modern ComfyUI frontend API

#### High Complexity (1-2 weeks each)
16. Implement dynamic outputs (Section 7)
17. Implement proper cryptomatte masking (Section 6)
18. Migrate to OpenEXR (Section 5)
19. Add comprehensive test suite (Section 4)
20. Full registry publishing compliance

### Backward Compatibility Assessment

**Safe changes (won't break workflows):**
- All bug fixes (items 1-8)
- Code cleanup (item 9)
- Internal refactoring (items 10-14)

**Potentially breaking changes:**
- **JS updates (item 15)**: Widget state serialization may differ. Saved workflows with old widget configs need migration handling.
- **Dynamic outputs (item 16)**: Changing `RETURN_TYPES` from static to dynamic means existing node connections may break if output slot indices change.
- **New nodes vs updated nodes**: Safest approach is adding new node types (e.g., `LoadExrV2`) and deprecating old ones.

**Recommended approach**: Use a major version bump (0.5.0) for breaking changes. Keep existing node IDs and add new ones for major API changes.

### Overall Complexity Rating: **MODERATE**

The core codebase is well-structured with good utility separation. Most changes are surgical fixes. The main complexity is in dynamic outputs and testing infrastructure.

---

## 4. Virtual ComfyUI Tester Feasibility

### Current Testing State

The `testing/` directory contains 15+ test files, but they are **standalone scripts** that mock ComfyUI's environment. They test individual functions in isolation but don't validate node behavior within ComfyUI's execution graph. The tests mock `folder_paths` and test saver/loader functions directly.

### Feasibility: YES - Multiple official tools exist

#### Approach 1: Official ComfyUI Test Framework (Recommended for Integration Tests)

The **ComfyUI-test-framework** (https://github.com/Comfy-Org/ComfyUI-test-framework) is the official solution:

- **Two components**: Custom assertion nodes + `comfyci` CLI tool
- **7 assertion node types**:
  - `Assert Executed` - Confirms upstream nodes ran
  - `Assert Equal` / `Assert Not Equal` - Deep equality
  - `Assert Image Match` - Perceptual hashing (dHash) comparison
  - `Assert Contains Color` - Verify specific colors
  - `Assert Tensor Shape` - Validate dimensions
  - `Assert In Range` - Ensure values within bounds
- **CLI**: `comfyci ./tests/**/*.json --server localhost:8188 --cpu -v`
- **Usage**: Create workflow JSON files with test definition + processing + assertion nodes

#### Approach 2: `comfy-test` (Progressive Testing, Best for CI)

**`comfy-test`** (https://pypi.org/project/comfy-test/) is a pip-installable tool with 7 progressive test levels:

| Level | Tests | Requires ComfyUI? |
|-------|-------|--------------------|
| SYNTAX | Python syntax validation | No |
| INSTALL | Dependency installation | No |
| REGISTRATION | Node class registration | Yes (headless) |
| INSTANTIATION | Node instantiation | Yes |
| STATIC_CAPTURE | Static analysis | Yes |
| VALIDATION | Input validation | Yes |
| EXECUTION | Full execution | Yes |

```bash
pip install comfy-test
comfy-test run --platform linux --level registration
```

Configuration via `comfy-test.toml`. No pytest code needed for basic levels.

#### Approach 3: `comfy-action` (GitHub Actions CI)

The **comfy-action** (https://github.com/Comfy-Org/comfy-action) GitHub Action:
- Sets up ComfyUI on GitHub Actions runners (Linux/Mac/Windows)
- Runs workflow JSON files
- Downloads required models
- Uploads results to CI/CD Dashboard at ci.comfy.org

#### Approach 4: Headless ComfyUI API Testing

ComfyUI can run headless via its HTTP/WebSocket API:

```bash
python main.py --listen 0.0.0.0 --port 8188 --cpu --dont-print-server
```

Custom nodes can then be tested by:
1. Install ComfyUI + custom node package in a virtualenv
2. Start ComfyUI in headless mode
3. Send workflow JSON via the `/prompt` API endpoint
4. Poll `/history` for execution results
5. Validate outputs programmatically

```python
import requests
import json

def test_load_exr_node():
    workflow = {
        "prompt": {
            "1": {
                "class_type": "LoadExr",
                "inputs": {
                    "image_path": "/path/to/test.exr",
                    "normalize": False
                }
            }
        }
    }
    response = requests.post("http://localhost:8188/prompt", json=workflow)
    assert response.status_code == 200
    # Poll for completion and validate
```

**Pros**: Tests the full pipeline including type checking, execution order, and node registration.
**Cons**: Requires ComfyUI installed, slower than unit tests, needs test EXR files.

#### Approach 5: Pytest with Module Mocking

Build on the existing `mock_folder_paths.py` pattern:

```python
# conftest.py
import sys
import types

# Mock ComfyUI modules before importing custom nodes
folder_paths = types.ModuleType('folder_paths')
folder_paths.get_output_directory = lambda: '/tmp/comfyui_output'
folder_paths.get_temp_directory = lambda: '/tmp/comfyui_temp'
sys.modules['folder_paths'] = folder_paths

# Now import nodes
from cocotools_io.modules.load_exr import LoadExr
from cocotools_io.modules.saver import SaverNode
```

**Pros**: Fast, no ComfyUI dependency, can test logic in isolation.
**Cons**: Doesn't test ComfyUI integration (type system, graph execution).

**Real-world examples**: `ComfyUI-Lora-Visualizer` uses `conftest.py` mocking; `ComfyUI_Selectors` has `tests/mocks/` + `tests/unit/` + `tests/integration/` directories.

#### Approach 6: Docker-Based CI

```dockerfile
FROM python:3.11-slim
RUN pip install torch numpy pillow tifffile opencv-python-headless colour-science
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /comfyui
COPY . /comfyui/custom_nodes/cocotools_io/
WORKDIR /comfyui
RUN pip install -r requirements.txt
CMD ["python", "-m", "pytest", "custom_nodes/cocotools_io/tests/"]
```

**Pros**: Reproducible, CI/CD ready, tests real environment.
**Cons**: Docker image size. Note: `comfyui-ci-container` (https://github.com/Comfy-Org/comfyui-ci-container) provides a pre-built Docker image with Playwright, Node.js, Python, PyTorch CPU, and ComfyUI backend.

### Recommendation

Use a **layered testing strategy**:

| Layer | What | Tool | Dependency |
|-------|------|------|------------|
| **Syntax/Install** | Basic validation | `comfy-test` (levels 1-2) | None |
| **Unit tests** | Utils (exr_utils, batch_utils, etc.) | pytest directly | None |
| **Node tests** | Individual node functions | pytest + conftest.py mocks | Mocked ComfyUI |
| **Registration** | Node registration | `comfy-test` (level 3) | Headless ComfyUI |
| **Integration tests** | Full workflow execution | ComfyUI-test-framework + `comfyci` | Full ComfyUI |
| **CI** | All of the above | `comfy-action` GitHub Action | GitHub Actions |

The existing test files in `testing/` can be refactored into proper pytest test cases. The utility modules are particularly well-suited for pure unit testing since they contain self-contained processing logic.

---

## 5. OpenEXR Migration Feasibility

### Current Dependencies

| Library | Used For | Required By |
|---------|----------|-------------|
| `OpenImageIO` (oiio) | EXR read/write, PNG write | LoadExr, LoadExrSequence, Saver |
| `colour-science` | Colorspace transforms | ColorspaceNode |
| `opencv-python` | JPG/WebP saving | SaverNode |
| `tifffile` | TIFF writing | SaverNode |
| `Pillow` | Non-EXR image loading, previews | ImageLoader, PreviewGenerator |
| `torch` | Tensor operations | All nodes |
| `numpy` | Array operations | All nodes |
| `rich` | Enhanced logging | Optional |

### Important Clarification

The question asks about "opencolorio and colourscience" but:

- **OpenColorIO is NOT currently used.** The project uses `colour-science` (the `colour` Python package).
- **These are different concerns:**
  - `OpenEXR` / `OpenImageIO` = file I/O (reading/writing pixels)
  - `colour-science` / `OpenColorIO` = color math (transforming colorspaces)

They solve different problems and one cannot replace the other.

### Key Finding: OIIO Is Now Pip-Installable

**This changes the calculus significantly.** OpenImageIO (v3.1.10.0) is now available via:
```bash
pip install OpenImageIO
```
With proper wheels for Windows/Linux/macOS, Python 3.9-3.14. The old installation pain point (needing conda or system packages) is **resolved**.

### Can OpenEXR Replace OpenImageIO for EXR I/O?

**Technically yes, but no longer recommended.** The modern `openexr` Python package (v3.4.4) supports:

- Multipart/multilayer EXR files via `File.parts[]` API
- Numpy arrays for pixel data
- Metadata/attributes
- Half-float and full-float pixel types
- `pip install openexr` (easy installation)
- Designed for "maximum simplicity, not high performance"

**Migration map:**

| Current (OIIO) | Replacement (OpenEXR) |
|----------------|----------------------|
| `oiio.ImageInput.open()` | `OpenEXR.InputFile()` or `Imath`-based API |
| `input.spec()` | `file.header()` |
| `input.read_image()` | `file.channels()` |
| `input.seek_subimage()` | Multi-part file API |
| `oiio.ImageBuf` + `write()` | `OpenEXR.OutputFile()` |
| PNG writing via OIIO | Pillow `Image.save()` (already available) |

### What About Non-EXR Formats?

OpenImageIO is also used for PNG writing in the saver. If you migrate EXR to OpenEXR, PNG writing can move to Pillow (already a dependency):

```python
# Current (OIIO):
spec = oiio.ImageSpec(width, height, channels, pixel_type)
buf = oiio.ImageBuf(spec)
buf.set_pixels(oiio.ROI(), data)
buf.write(path)

# Replacement (Pillow):
img = Image.fromarray(data)
img.save(path, format='PNG', compress_level=9)
```

### Can colour-science Be Replaced?

Options:
1. **Keep `colour-science`** - Fix the gamma swap bugs and it works well. Easy to install.
2. **Switch to PyOpenColorIO** - More industry-standard, uses OCIO configs. Harder to install (`pip install PyOpenColorIO`), but provides standardized color management workflows familiar to VFX artists.
3. **Manual matrix math** - Not recommended. Error-prone and hard to maintain.

### Revised Recommendation (Given OIIO is now pip-installable)

**The motivation to switch has significantly diminished.** OIIO is now as easy to install as OpenEXR, handles multiple formats in one API, and the codebase is well-structured around it.

| Option | Action | Effort | Recommendation |
|--------|--------|--------|----------------|
| **A (Recommended)** | Keep OIIO, fix bugs | 2-3 days | **Best ROI** |
| **B** | Migrate to OpenEXR + Pillow | 2-3 weeks | Only if OIIO causes issues |
| **C** | Add OpenEXR as fallback | 1-2 weeks | If supporting environments without OIIO |

Keep `colour-science` for colorspace transforms. Consider adding optional OpenColorIO support in the future for users with OCIO configs.

### Cryptomatte Library: `decryptomatte`

The `decryptomatte` package (MIT license, PyPI, 2024) provides:
- `list_layers()`, `get_mattes_by_names()`, `get_mask_for_id()`, `id_to_name()`
- Produces greyscale NumPy mask arrays
- **Depends on OpenImageIO** (aligns with keeping OIIO)

Could be used to accelerate cryptomatte implementation (Section 6).

---

## 6. Cryptomatte Masking Implementation

### Current State

The project has **partial cryptomatte support**:
- Cryptomatte layers detected by name pattern (`is_cryptomatte_layer`)
- Raw cryptomatte channel data extracted and stored in a dict
- `CryptomatteLayer` node can select and output cryptomatte layers as raw RGB
- Layer groups tracked (e.g., `CryptoAsset00`, `CryptoAsset01`)

**What's missing**: The raw data is output as RGB images but is NOT decoded into actual object masks. The R,G channels of cryptomatte data contain encoded hash+coverage pairs, not viewable image data.

### How Cryptomatte Works

Cryptomatte stores object identification data across multiple "levels" in an EXR file:

```
CryptoAsset00.R  = float32 (bits encode uint32 object ID hash #1)
CryptoAsset00.G  = float32 (coverage/alpha for object #1)
CryptoAsset00.B  = float32 (bits encode uint32 object ID hash #2)
CryptoAsset00.A  = float32 (coverage/alpha for object #2)
CryptoAsset01.R  = float32 (object ID hash #3)
CryptoAsset01.G  = float32 (coverage for #3)
...
```

The EXR metadata contains a **manifest** mapping object names to their hashes:
```json
{"Car": "3a2b1c4d", "Building": "5e6f7a8b", ...}
```

### Implementation Requirements

#### Step 1: Parse Manifest from EXR Metadata

```python
def parse_cryptomatte_manifest(exr_metadata):
    """Extract name-to-hash mapping from EXR header attributes"""
    manifests = {}
    for attr_name, attr_value in exr_metadata.items():
        # Cryptomatte manifest keys look like: cryptomatte/abc123/manifest
        if 'cryptomatte' in attr_name.lower() and 'manifest' in attr_name.lower():
            try:
                manifest_data = json.loads(attr_value)
                manifests.update(manifest_data)
            except json.JSONDecodeError:
                pass
    return manifests  # {"ObjectName": "hex_hash", ...}
```

#### Step 2: Decode Float32 to ID Hash

```python
import struct

def float_to_id(float_val):
    """Convert float32 bits to uint32 ID hash"""
    return struct.unpack('I', struct.pack('f', float_val))[0]

def id_to_float(id_val):
    """Convert uint32 ID hash to float32 representation"""
    return struct.unpack('f', struct.pack('I', id_val))[0]
```

#### Step 3: Extract Mask for Named Object

```python
def extract_object_mask(crypto_channels, object_name, manifest, height, width):
    """Generate a mask for a specific object from cryptomatte data"""
    if object_name not in manifest:
        return np.zeros((height, width), dtype=np.float32)

    target_hash = int(manifest[object_name], 16)
    target_float = id_to_float(target_hash)
    mask = np.zeros((height, width), dtype=np.float32)

    # Each level contains 2 ID/coverage pairs in RGBA channels
    for level_idx in range(num_levels):
        level_data = crypto_channels[f'CryptoAsset{level_idx:02d}']  # [H,W,4]

        # First pair: R=ID, G=coverage
        id_channel_1 = level_data[:, :, 0]
        coverage_1 = level_data[:, :, 1]
        matches_1 = np.isclose(id_channel_1, target_float, rtol=0, atol=1e-10)
        mask += np.where(matches_1, coverage_1, 0.0)

        # Second pair: B=ID, A=coverage
        id_channel_2 = level_data[:, :, 2]
        coverage_2 = level_data[:, :, 3]
        matches_2 = np.isclose(id_channel_2, target_float, rtol=0, atol=1e-10)
        mask += np.where(matches_2, coverage_2, 0.0)

    return np.clip(mask, 0.0, 1.0)
```

#### Step 4: ComfyUI Node

```python
class CryptomatteExtractMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cryptomatte": ("CRYPTOMATTE",),
                "metadata": ("STRING", {"forceInput": True}),
                "object_name": ("STRING", {"default": "", "description": "Object name from manifest"}),
                "output_mode": (["greyscale_mask", "rgb_preview", "both"],),
            }
        }

    RETURN_TYPES = ("MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("mask", "preview", "available_objects")
    FUNCTION = "extract_mask"
    CATEGORY = "COCO Tools/Cryptomatte"
```

### RGB vs Greyscale Output

| Mode | Output | Use Case |
|------|--------|----------|
| **Greyscale mask** | Single-channel [B,H,W] values 0-1 | Compositing, masking operations |
| **RGB preview** | 3-channel [B,H,W,3] colored by object | Visualization, debugging, QC |
| **ID visualization** | Each object gets a unique color | Overview of all objects in scene |

All three are straightforward once the core mask extraction is working.

### Estimated Effort

| Task | Effort |
|------|--------|
| Manifest parsing + hash decoding | 2-3 days |
| Single-object mask extraction | 2-3 days |
| Multi-object selection | 1-2 days |
| ComfyUI node + JS for object picker | 3-5 days |
| Testing with real cryptomatte EXRs | 2-3 days |
| **Total** | **1.5-2.5 weeks** |

---

## 7. Dynamic Outputs for EXR Channels

### The Question

Can ComfyUI dynamically generate output slots based on what channels/layers are present in an EXR file?

### Current ComfyUI Support (Feb 2026)

**V1 API (Current codebase):**
1. **`RETURN_TYPES` is static**: Defined at class level, evaluated once during node registration
2. **`OUTPUT_IS_LIST`**: Marks outputs as list types but doesn't change the count
3. **Wildcard type (`*`)**: Can connect to any type, useful for pass-through
4. **JavaScript manipulation**: The most practical approach for dynamic slots in V1

**V3 API (New - supports dynamic I/O natively):**
5. **`Autogrow`**: Variable-length input/output lists with template-based expansion (up to 50 slots)
6. **`DynamicCombo`**: Show/hide inputs based on dropdown selection
7. **`MatchType`**: Enforce type consistency across linked I/O at runtime
8. These are **V3-only features** - not available in V1 schema

### Current Approach (What You Have)

A single `LAYERS` dictionary output with a secondary node to extract individual layers:

```
[LoadExr] --LAYERS--> [LoadExrLayerByName] --IMAGE/MASK-->
```

This is clean and works well. The question is whether you can eliminate the intermediate node.

### Option A: Keep Current Architecture (Recommended Short-Term)

**Pros**: Already works, backward compatible, clean design
**Cons**: Requires extra node for each layer extraction

**Enhancement**: Improve the LoadExrLayerByName JS to show a dropdown of available layers instead of requiring manual string entry.

### Option B: JavaScript-Driven Dynamic Outputs (Most Viable Today)

Use JavaScript to dynamically add/remove output slots based on execution results:

```javascript
nodeType.prototype.onExecuted = function(message) {
    if (!message || !message.channel_names) return;

    const channels = message.channel_names;
    const baseOutputCount = 2; // image + alpha always present

    // Remove old dynamic outputs
    while (this.outputs.length > baseOutputCount) {
        this.removeOutput(this.outputs.length - 1);
    }

    // Add new outputs for each channel
    for (const channel of channels) {
        this.addOutput(channel, "IMAGE");
    }

    this.setSize(this.computeSize());
    app.graph.setDirtyCanvas(true, true);
};
```

The Python side would need to:
1. Return channel names in the UI message
2. Return all channel tensors in a list/dict
3. Handle the mapping between dynamic slot indices and channel data

**Pros**: Responsive UI, each channel gets its own output slot
**Cons**:
- Output connections break when EXR file changes and channels differ
- Complex JS code to maintain
- Requires executing the node once to discover channels
- Saved workflows may break if loaded with a different EXR file

### Option C: Fixed Maximum Slots

Pre-declare a maximum number of layer outputs:

```python
RETURN_TYPES = ("IMAGE", "MASK") + ("IMAGE",) * 16 + ("STRING",)
```

**Pros**: Simple, no JS needed
**Cons**: Cluttered UI with 16+ unused slots, confusing UX

### Option D: Migrate to V3 Schema with Native Dynamic I/O

The V3 API provides first-class dynamic I/O via `Autogrow`:

```python
from comfy_api.latest import io

class LoadExrV3(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CoCoTools_LoadExrV3",
            inputs=[io.String.Input("image_path"), io.Boolean.Input("normalize")],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="alpha"),
                io.Autogrow.Output("layers", template=io.Image.Output(), max=50),
            ],
        )
```

**Pros**: Native support, clean API, no JS hacks
**Cons**: V3 API still stabilizing (`v0_0_2`), would require full node rewrite

### Recommendation

1. **Now**: Improve the current LAYERS + LoadExrLayerByName approach with better JS (layer dropdown with autocomplete from metadata)
2. **Medium-term**: Implement Option B (JS-driven dynamic outputs) as a separate "LoadExrDynamic" node (keep existing nodes for compatibility)
3. **Long-term**: When V3 API stabilizes, migrate to V3 schema with native `Autogrow` outputs - this is the cleanest solution and eliminates all JS complexity

---

## Summary of Priorities

### Must Fix (Before Any Release)

| # | Issue | File | Severity |
|---|-------|------|----------|
| 1 | Colorspace gamma encoding/decoding SWAPPED | `modules/colorspace.py:162-233` | CRITICAL |
| 2 | `index.js` imports non-existent `load_exr.js` | `js/index.js:3` | HIGH |
| 3 | EXR HDR data clipped to [0,1] in saver | `modules/saver.py:167` | HIGH |
| 4 | JS `isCryptomatte` out of scope in `setup()` | `js/load_exr_layer_by_name.js:243` | HIGH |
| 5 | `replace_frame_number` replaces all digits | `utils/sequence_utils.py:57-67` | HIGH |
| 6 | `process_layer_groups` stores lists not tensors | `utils/exr_utils.py:426` | HIGH |
| 7 | Operator precedence bugs in colorspace | `modules/colorspace.py` (10 locations) | MEDIUM |

### Should Fix (Next Version)

| # | Issue | File | Severity |
|---|-------|------|----------|
| 8 | ImageLoader bit depth detection broken | `modules/image_loader.py:58,102-116` | HIGH |
| 9 | ImageLoader double-normalization | `modules/image_loader.py:62-74` | MEDIUM |
| 10 | ImageLoader alpha tensor shape [1,H,W,1] vs [B,H,W] | `modules/image_loader.py:67` | MEDIUM |
| 11 | EXR 16-bit float16 before OIIO | `modules/saver.py:183` | MEDIUM |
| 12 | Metadata JSON serialization with OIIO types | `utils/exr_utils.py:713` | MEDIUM |
| 13 | XYZ normalization scalar vs per-vector | `utils/exr_utils.py:306-309` | MEDIUM |
| 14 | Sequence pattern detection too broad | `utils/sequence_utils.py:30` | MEDIUM |
| 15 | Frame number extraction heuristic fragile | `utils/sequence_utils.py:72-83` | MEDIUM |
| 16 | Return tuples from node functions | `modules/load_exr_layer_by_name.py` | LOW |
| 17 | Update pyproject.toml for registry | `pyproject.toml` | LOW |

### Nice to Have (Future Roadmap)

| # | Feature | Effort |
|---|---------|--------|
| 18 | Proper cryptomatte mask extraction | 1.5-2.5 weeks |
| 19 | Dynamic outputs (V3 Autogrow or JS-driven) | 1-2 weeks |
| 20 | Testing infrastructure (comfy-test + pytest) | 1-2 weeks |
| 21 | Lazy evaluation support | 3-5 days |
| 22 | V3 schema migration (future-proofing) | 2-3 weeks |
| 23 | Rec.2020 proper transfer function | 1-2 days |

### Estimated Total Modernization Effort

| Phase | Scope | Effort |
|-------|-------|--------|
| Critical bug fixes | Items 1-7 | 2-3 days |
| Code quality fixes | Items 8-17 | 3-5 days |
| Cryptomatte masking | Item 18 | 1.5-2.5 weeks |
| Dynamic outputs | Item 19 | 1-2 weeks |
| Testing infrastructure | Item 20 | 1-2 weeks |
| V3 migration (when stable) | Item 22 | 2-3 weeks |
| **Full modernization** | **All items** | **7-10 weeks** |

---

## 8. OpenEXR vs OIIO Performance Analysis

### Your Assumption: "OpenEXR is much faster than OIIO"

**This is incorrect.** OIIO is not a competing EXR implementation -- it uses OpenEXR internally as its EXR format plugin. The actual call chain is:

```
Your Python code → OIIO Python bindings → OIIO C++ → OpenEXR C/C++ library → disk
```

When built against OpenEXR 3.1+, OIIO can use either the traditional C++ API (`Imf::InputFile`) or the newer, faster OpenEXRCore C API (`exr_*` functions), selected at runtime. The overhead OIIO adds on top of raw OpenEXR is minimal: channel name parsing, attribute mapping, and thread synchronization.

### The OpenEXR Python Module Is Explicitly Slow

The official OpenEXR Python module states it is **"designed for maximum simplicity, not high performance."** Specific issues:

- **Single-threaded**: The loader reads data line-by-line in a loop. `Imf::setGlobalThreadCount` is NOT exposed in the Python module (open issue #1655, still unresolved as of 2024).
- **No ImageCache equivalent**: Every read hits disk directly, no caching tier.
- **No non-blocking I/O**: Unlike OIIO's zero-copy architecture.

A Rust `exr` crate benchmark showed files loading in seconds that took **over a minute** with the OpenEXR Python module, purely due to threading differences.

### Raw Compression Benchmarks (OpenEXR 3.1.1, 16 threads)

From Aras Pranckevicus (Unity/Blender developer), 1,057 MB RGBA half-float test data:

| Compression | Write Speed | Read Speed | Ratio |
|------------|-------------|------------|-------|
| Uncompressed | ~430 MB/s | ~1,744 MB/s | 1.0x |
| ZIP level 6 (default) | ~213 MB/s | ~1,697 MB/s | 2.45x |
| ZIP level 4 | ~456 MB/s | ~1,600 MB/s | 2.42x |
| PIZ (lossless) | ~600 MB/s | ~1,264 MB/s | 2.4x |
| **ZIP l4 + libdeflate** | **640 MB/s** | **~2,000 MB/s** | 2.43x |
| **Zstd level 1** | **837 MB/s** | **~2,020 MB/s** | 2.46x |

Key finding: Zstd level 1 is 2x faster to write than uncompressed and 1.16x faster to read, while achieving 2.46x compression. ZIP level 4 is 2x faster to write than level 6 with nearly identical compression.

### OpenEXR 3.4: HTJ2K Compression

OpenEXR 3.4 added HTJ2K (High Throughput JPEG 2000):
- `htj2k32`: 4-6x faster encoding/decoding than `htj2k256`
- Described as "one of the fastest compression types available in OpenEXR"

### Where OIIO Can Be Slower (Multilayer Files)

OIIO's ImageCache historically had a problem: `get_pixels()` would decode ALL layers regardless of which channels were requested. This was fixed in PR #1226, reducing peak memory from 768 MB to 96 MB for 32-channel files when requesting 4 channels. A regression in OIIO 1.6-1.7 showed 3.4x slower wall time for channel stripping from 50-channel files (traced to tiling/caching overhead, not OpenEXR).

**For CoCoTools**: The current code reads full files via `read_image()`, so this specific issue isn't a concern.

### Verdict

| | OpenEXR Python | OIIO Python |
|---|---|---|
| **Raw read speed** | Good (uses same C library) | Good (calls OpenEXR internally) |
| **Python threading** | Single-threaded, no multithreading | Inherits C++ multithreading |
| **Caching** | None | 3-tier ImageCache (10ns hot tile access) |
| **Format support** | EXR only | EXR + PNG + TIFF + 100+ formats |
| **Installation** | `pip install openexr` | `pip install OpenImageIO` |
| **Multilayer handling** | Manual part iteration | Automatic with channel caching |

**Recommendation**: Stay with OIIO. If speed is a concern, ensure your OIIO build links against OpenEXR 3.1+ with `openexr:core` enabled, and consider ZIP level 4 or Zstd compression for output.

---

## 9. Preview System Optimization for Sequences

### Current Implementation (CoCoTools)

`utils/preview_utils.py` writes full-resolution PNGs with UUID filenames to temp directory. For sequences, only the first frame is shown. The preview flow is:

```
Tensor → numpy → PIL Image → PNG encode → write to disk → ComfyUI serves via HTTP /view
```

Problems:
- `enable_full_size=True` by default (line 211) - encodes at full resolution
- PNG format is slow to encode
- UUID filenames prevent caching/reuse
- Only shows one frame from sequences
- Every preview is a disk write + HTTP round-trip

### ComfyUI Preview Mechanisms

ComfyUI supports **two fundamentally different preview delivery mechanisms**:

#### Mechanism A: Temp File + HTTP `/view` (What You Use Now)

The built-in `PreviewImage` node does this. The node writes a file to `temp/`, returns a `{"ui": {"images": [{"filename": ..., "type": "temp"}]}}` dict, and the frontend fetches via GET `/view?filename=...&type=temp`.

Key detail: ComfyUI's built-in `PreviewImage` uses `compress_level=1` (not 6 or 9), and the `/view` endpoint supports on-the-fly format conversion via `?preview=webp;90` or `?preview=jpeg;80`.

#### Mechanism B: WebSocket Binary (Zero Disk I/O)

ComfyUI has a binary websocket protocol that can send image data directly to the frontend with NO temp files:

```python
from server import PromptServer, BinaryEventTypes

server = PromptServer.instance
server.send_sync(
    BinaryEventTypes.UNENCODED_PREVIEW_IMAGE,
    ["JPEG", pil_image, max_size],  # [format, PIL.Image, max_dimension_or_None]
    server.client_id,
)
```

Wire format: `[4B event_type][4B format_type][image_bytes]` -- 8 bytes overhead then raw JPEG/PNG.

This is what the latent preview system uses during generation -- zero disk writes, immediate display.

### Fastest Possible Preview Approaches (Ranked)

#### 1. WebSocket JPEG (Fastest Single Frame, Zero Disk)

```python
from server import PromptServer, BinaryEventTypes
from PIL import Image
import numpy as np

def send_preview_ws(tensor, max_size=512):
    """Send preview via websocket. Zero disk I/O."""
    arr = (255.0 * tensor[0].cpu().numpy()).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    server = PromptServer.instance
    server.send_sync(
        BinaryEventTypes.UNENCODED_PREVIEW_IMAGE,
        ["JPEG", img, max_size],
        server.client_id,
    )
    return {"ui": {"images": [{"source": "websocket", "content-type": "image/jpeg", "type": "output"}]}}
```

- No temp files written
- JPEG at quality 95 is ~10-20x smaller than PNG
- `max_size=512` auto-downscales via `ImageOps.contain()` with BILINEAR
- Each frame replaces the previous in the preview area

#### 2. Animated WEBP to Temp (Best for Sequences)

Write a single animated WEBP file containing all frames, served via `/view`. Requires JS extension to handle the custom `"gifs"` UI key (same pattern as VideoHelperSuite):

```python
# Python side
frames = []
for i in range(batch_size):
    arr = (255.0 * images[i].cpu().numpy()).clip(0, 255).astype(np.uint8)
    frames.append(Image.fromarray(arr).resize((preview_w, preview_h), Image.BILINEAR))

output_path = os.path.join(temp_dir, f"preview_{uuid4()}.webp")
frames[0].save(output_path, save_all=True, append_images=frames[1:],
               duration=round(1000/24), loop=0, quality=70)

return {"ui": {"gifs": [{"filename": os.path.basename(output_path),
    "subfolder": "", "type": "temp", "format": "image/webp", "frame_rate": 24}]}}
```

```javascript
// JS extension
chainCallback(nodeType.prototype, "onExecuted", function(message) {
    if (message?.gifs) {
        const img = new Image();
        img.src = api.apiURL(`/view?filename=${message.gifs[0].filename}&type=temp`);
        // Display in node widget
    }
});
```

- Single file for entire sequence
- WEBP animated is much smaller than individual PNGs
- Supports >256 colors (unlike GIF)
- Shows all frames as animation in the node

#### 3. JPEG Temp Files at Reduced Resolution (Simple Improvement)

Simplest change to existing code -- switch from full-res PNG to downscaled JPEG:

```python
# Instead of:
img.save(path, format='PNG')

# Use:
small = img.resize((min(512, img.width), min(512, img.height)), Image.BILINEAR)
small.save(path, format='JPEG', quality=80)
```

- 10-50x faster encode than PNG
- 5-20x smaller files
- Still uses disk, but much less I/O

#### 4. WebSocket Streaming for Sequences (Live Progress)

Send each frame via websocket as it loads, giving a live-updating preview:

```python
server = PromptServer.instance
for i in range(batch_size):
    arr = (255.0 * images[i].cpu().numpy()).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    server.send_sync(
        BinaryEventTypes.UNENCODED_PREVIEW_IMAGE,
        ["JPEG", img, 512],
        server.client_id,
    )
```

Shows each frame briefly as it processes. The user sees a "flipbook" effect during loading.

### Comparison Matrix

| Approach | Disk I/O | Encode Speed | Multi-Frame | JS Required | Complexity |
|----------|----------|-------------|-------------|-------------|------------|
| WebSocket JPEG | None | Fastest | Last only | No | Low |
| Animated WEBP | 1 file | Medium | All frames | Yes | Medium |
| JPEG temp files | Per frame | Fast | Gallery | No | Lowest |
| WS streaming | None | Fast | Flipbook | No | Low |
| Current (PNG) | Per frame | Slow | First only | No | N/A |

### Recommendation

**Immediate win**: Replace PNG previews with JPEG at 512px max and quality 80. This alone will be ~10-50x faster.

**Best UX for sequences**: Implement the animated WEBP approach with a small JS extension. One file, all frames, animated playback in the node.

**Fastest possible**: WebSocket binary with JPEG -- zero disk I/O, instant display. Use this for single-frame previews and the "loading progress" indicator during sequence loads.
