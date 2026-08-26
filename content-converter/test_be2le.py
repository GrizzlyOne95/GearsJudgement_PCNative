import struct
import unittest

from be2le import Converter


class NativePlatformTailTests(unittest.TestCase):
    def test_empty_shader_cache_retargets_xbox_to_pc_sm3(self):
        source = struct.pack(">iBiii", 10, 2, 0, 0, 0)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("ShaderCache", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<iBiii", 10, 0, 0, 0, 0))
        self.assertEqual(converter.stats["shader_platform_retargeted"], 1)

    def test_populated_shader_cache_fails_closed(self):
        source = struct.pack(">iBiii", 10, 2, 1, 0, 0)
        converter = Converter(source)

        self.assertFalse(converter.native_tail("ShaderCache", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_empty_fvert_bulk_header_retargets_16_to_24(self):
        source = struct.pack(">ii", 16, 0)
        converter = Converter(source)

        self.assertEqual(converter.empty_bulk_retarget(0, 16, 24), 8)
        self.assertEqual(bytes(converter.out), struct.pack("<ii", 24, 0))

    def test_populated_fvert_bulk_header_is_rejected(self):
        source = struct.pack(">ii", 16, 1) + (b"\0" * 16)
        converter = Converter(source)

        self.assertIsNone(converter.empty_bulk_retarget(0, 16, 24))
        self.assertEqual(bytes(converter.out), source)

    def test_empty_sound_cue_editor_map_converts(self):
        source = struct.pack(">i", 0)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("SoundCue", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<i", 0))

    def test_speculative_tarray_rejects_impossible_count_and_rolls_back(self):
        source = struct.pack(">i", 0x10000000)
        converter = Converter(source)

        accepted = converter.try_region(
            0, len(source), lambda: converter.tarray(0, lambda off: off + 1) is not None
        )
        self.assertFalse(accepted)
        self.assertEqual(bytes(converter.out), source)


if __name__ == "__main__":
    unittest.main()
