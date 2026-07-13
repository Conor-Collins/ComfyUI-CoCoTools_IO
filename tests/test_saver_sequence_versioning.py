from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_runtime_stubs(output_dir: Path) -> None:
    torch = types.ModuleType("torch")
    torch.Tensor = object
    sys.modules.setdefault("torch", torch)

    tifffile = types.ModuleType("tifffile")
    tifffile.imwrite = lambda *args, **kwargs: None
    sys.modules.setdefault("tifffile", tifffile)

    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_output_directory = lambda: str(output_dir)
    folder_paths.get_temp_directory = lambda: str(output_dir / "temp")
    sys.modules["folder_paths"] = folder_paths

    oiio = types.ModuleType("OpenImageIO")
    oiio.HALF = "half"
    oiio.FLOAT = "float"
    oiio.UINT8 = "uint8"
    oiio.UINT16 = "uint16"
    oiio.ROI = lambda: None
    oiio.geterror = lambda: "OpenImageIO stub"
    oiio.ImageSpec = lambda *args, **kwargs: object()

    class _ImageBuf:
        def __init__(self, *args, **kwargs):
            pass

        def set_pixels(self, *args, **kwargs):
            pass

        def write(self, path):
            Path(path).write_bytes(b"stub")
            return True

    oiio.ImageBuf = _ImageBuf
    sys.modules.setdefault("OpenImageIO", oiio)

    cv2 = types.ModuleType("cv2")
    cv2.COLOR_RGB2BGR = 0
    cv2.IMWRITE_JPEG_QUALITY = 1
    cv2.IMWRITE_WEBP_QUALITY = 2
    cv2.cvtColor = lambda data, code: data
    cv2.imwrite = lambda path, data, options=None: Path(path).write_bytes(b"stub") or True
    sys.modules.setdefault("cv2", cv2)


def _load_saver_module(output_dir: Path):
    root = Path(__file__).resolve().parents[1]
    package = types.ModuleType("cocotools_io")
    package.__path__ = [str(root)]
    sys.modules["cocotools_io"] = package

    modules_package = types.ModuleType("cocotools_io.modules")
    modules_package.__path__ = [str(root / "modules")]
    sys.modules["cocotools_io.modules"] = modules_package

    _install_runtime_stubs(output_dir)
    spec = importlib.util.spec_from_file_location(
        "cocotools_io.modules.saver",
        root / "modules" / "saver.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.generate_preview_for_comfyui = lambda *args, **kwargs: []
    module.SaverNode.prepare_image = lambda self, image, save_as_grayscale: module.np.zeros((1, 1, 3), dtype=module.np.float32)
    module.SaverNode.save_exr = lambda self, img, path, bit_depth, compression: Path(path).write_bytes(b"stub")
    return module


class SaverSequenceVersioningTests(unittest.TestCase):
    def test_unique_sequence_counter_is_inserted_before_hash_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            module = _load_saver_module(output_dir)
            existing = output_dir / "shot.1001.exr"
            existing.write_bytes(b"already here")

            result = module.SaverNode().save_images(
                images=[object(), object()],
                file_path="",
                filename="shot.####",
                save_mode="sequence",
                file_type="exr",
                bit_depth=16,
                start_frame=1001,
                frame_step=1,
            )

        saved = [item["filename"] for item in result["ui"]["saved_files"]]
        self.assertEqual(saved, ["shot_1.1001.exr", "shot.1002.exr"])

    def test_unique_sequence_counter_is_inserted_before_generated_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            module = _load_saver_module(output_dir)
            existing = output_dir / "shot_0001.exr"
            existing.write_bytes(b"already here")

            result = module.SaverNode().save_images(
                images=[object()],
                file_path="",
                filename="shot",
                save_mode="sequence",
                file_type="exr",
                bit_depth=16,
                start_frame=1,
                frame_step=1,
            )

        saved = [item["filename"] for item in result["ui"]["saved_files"]]
        self.assertEqual(saved, ["shot_1_0001.exr"])

    def test_explicit_version_is_inserted_before_sequence_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = _load_saver_module(Path(tmp))

            result = module.SaverNode().save_images(
                images=[object()],
                file_path="",
                filename="shot.####",
                save_mode="sequence",
                file_type="exr",
                bit_depth=16,
                use_versioning=True,
                version=3,
                start_frame=1001,
                frame_step=1,
            )

        saved = [item["filename"] for item in result["ui"]["saved_files"]]
        self.assertEqual(saved, ["shot_v003.1001.exr"])


if __name__ == "__main__":
    unittest.main()
