import importlib.util
import os
import tempfile
import unittest


def load_sequence_utils():
    path = os.path.join(os.path.dirname(__file__), "..", "utils", "sequence_utils.py")
    spec = importlib.util.spec_from_file_location("sequence_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SequenceHandler = load_sequence_utils().SequenceHandler


class TestExtractFrameNumbers(unittest.TestCase):
    def test_pattern_with_trailing_digits(self):
        with tempfile.TemporaryDirectory() as tmp:
            pattern = os.path.join(tmp, "shot_####_v002.exr")
            for frame in (1001, 1002):
                with open(os.path.join(tmp, f"shot_{frame:04d}_v002.exr"), "w"):
                    pass

            found = SequenceHandler.find_sequence_files(pattern)
            self.assertEqual(len(found), 2)

            frame_info = SequenceHandler.extract_frame_numbers(found, pattern)
            self.assertEqual([fn for fn, _ in frame_info], [1001, 1002])

    def test_three_hash_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            pattern = os.path.join(tmp, "plate.###.exr")
            for frame in (1, 2, 3):
                with open(os.path.join(tmp, f"plate.{frame:03d}.exr"), "w"):
                    pass

            found = SequenceHandler.find_sequence_files(pattern)
            self.assertEqual(len(found), 3)

            frame_info = SequenceHandler.extract_frame_numbers(found, pattern)
            self.assertEqual([fn for fn, _ in frame_info], [1, 2, 3])

    def test_no_pattern_fallback_unchanged(self):
        # Without a pattern, the last digit run in the name is used (existing behaviour)
        frame_info = SequenceHandler.extract_frame_numbers(["/tmp/shot_1001_v002.exr"])
        self.assertEqual([fn for fn, _ in frame_info], [2])


if __name__ == "__main__":
    unittest.main()
