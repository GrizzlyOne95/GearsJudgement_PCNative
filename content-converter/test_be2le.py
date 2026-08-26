import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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

    def test_apex_cached_payload_over_16_bytes_fails_closed(self):
        source = struct.pack(">i", 17) + (b"A" * 17)
        converter = Converter(source)

        self.assertIsNone(converter.apex_cached_blob(0))
        self.assertEqual(bytes(converter.out), source)

    def test_apex_16_byte_sentinel_swaps_size_and_preserves_bytes(self):
        sentinel = bytes(range(16))
        source = struct.pack(">i", 16) + sentinel
        converter = Converter(source)

        self.assertEqual(converter.apex_cached_blob(0), len(source))
        self.assertEqual(bytes(converter.out), struct.pack("<i", 16) + sentinel)

    def test_distance_field_colors_keep_channel_order(self):
        colors = bytes.fromhex("11 22 33 44 AA BB CC DD")
        source = struct.pack(">i", 2) + colors
        converter = Converter(source)

        self.assertEqual(converter.opaque_array(0, 4), len(source))
        self.assertEqual(bytes(converter.out[:4]), struct.pack("<i", 2))
        self.assertEqual(bytes(converter.out[4:]), colors)

    def test_sound_wave_bulk_headers_convert_and_xma_bytes_stay_opaque(self):
        xma = bytes.fromhex("10 20 30 40 50 60")
        empty = struct.pack(">Iiii", 0, 0, 0, 0)
        xbox_header_offset = len(empty) * 2
        xbox_data_offset = xbox_header_offset + 16
        xbox = struct.pack(">Iiii", 0, len(xma), len(xma), xbox_data_offset) + xma
        source = empty + empty + xbox + empty
        converter = Converter(source)

        self.assertTrue(converter.native_tail("SoundNodeWave", 0, len(source)))
        self.assertEqual(bytes(converter.out[xbox_data_offset:xbox_data_offset + len(xma)]), xma)
        self.assertEqual(struct.unpack_from("<Iiii", converter.out, xbox_header_offset),
                         (0, len(xma), len(xma), xbox_data_offset))

    def test_sound_wave_inline_bulk_offset_mismatch_fails_closed(self):
        bad = struct.pack(">Iiii", 0, 4, 4, 99) + b"XMA!"
        empty = struct.pack(">Iiii", 0, 0, 0, 0)
        source = empty + empty + bad + empty
        converter = Converter(source)

        self.assertFalse(converter.native_tail("SoundNodeWave", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_exact_single_int_native_tail_converts(self):
        source = struct.pack(">i", 0)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("RB_BodySetup", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<i", 0))

    def test_single_int_native_tail_rejects_extra_data(self):
        source = struct.pack(">ii", 0, 0)
        converter = Converter(source)

        self.assertFalse(converter.native_tail("StaticMeshComponent", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_string_array_elements_convert(self):
        source = struct.pack(">i", 2) + struct.pack(">i", 3) + b"hi\0" + struct.pack(">i", 2) + b"x\0"
        converter = Converter(source, {"Labels": [{"elem": "StrProperty", "struct": None,
                                                     "widths": None}]})

        converter.array_value([], 0, len(source), 0, "Labels")
        self.assertEqual(bytes(converter.out),
                         struct.pack("<i", 2) + struct.pack("<i", 3) + b"hi\0" +
                         struct.pack("<i", 2) + b"x\0")
        self.assertEqual(converter.unsupported, {})

    def test_byte_array_elements_preserve_bytes(self):
        source = struct.pack(">i", 4) + bytes.fromhex("01 02 FE FF")
        converter = Converter(source, {"Modes": [{"elem": "ByteProperty", "struct": None,
                                                    "widths": None}]})

        converter.array_value([], 0, len(source), 0, "Modes")
        self.assertEqual(bytes(converter.out), struct.pack("<i", 4) + bytes.fromhex("01 02 FE FF"))
        self.assertEqual(converter.unsupported, {})

    def test_enum_byte_array_elements_convert_fnames(self):
        source = struct.pack(">i", 2) + struct.pack(">iiii", 7, 0, 9, 1)
        converter = Converter(source, {"Modes": [{"elem": "ByteProperty", "struct": None,
                                                    "widths": None}]})

        converter.array_value([], 0, len(source), 0, "Modes")
        self.assertEqual(bytes(converter.out), struct.pack("<iiiii", 2, 7, 0, 9, 1))
        self.assertEqual(converter.unsupported, {})


if __name__ == "__main__":
    unittest.main()
