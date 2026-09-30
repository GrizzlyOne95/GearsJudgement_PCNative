import struct
import unittest

from be2le import Converter


class CoverSlotFailureTests(unittest.TestCase):
    def test_invalid_actions_count_rejects_candidate_and_rolls_back(self):
        source = struct.pack(">7i", 0, 0, 0, 0, 0, 0, -1)
        converter = Converter(source)
        self.assertIsNone(converter.binary_struct("CoverSlot", 0))
        self.assertEqual(bytes(converter.out), source)
        self.assertFalse(converter.stats)


class EnumBytePropertyTests(unittest.TestCase):
    NAMES = ["None", "Id", "ByteProperty", "EGearSoundId", "GSID_Foley"]

    def tag_stream(self, fmt, size, value):
        return b"".join([
            struct.pack(fmt + "ii", 1, 0),                 # Name = Id
            struct.pack(fmt + "ii", 2, 0),                 # Type = ByteProperty
            struct.pack(fmt + "ii", size, 0),              # Size, ArrayIndex
            struct.pack(fmt + "ii", 3 if size == 8 else 0, 0),  # EnumName
            value,
            struct.pack(fmt + "ii", 0, 0),                 # None
        ])

    def test_enum_byte_value_fname_is_swapped(self):
        source = self.tag_stream(">", 8, struct.pack(">ii", 4, 0))
        converter = Converter(source)

        self.assertEqual(converter.tags(self.NAMES, 0, len(source)), len(source))
        self.assertEqual(bytes(converter.out), self.tag_stream("<", 8, struct.pack("<ii", 4, 0)))

    def test_plain_byte_value_is_left_as_one_byte(self):
        source = self.tag_stream(">", 1, b"\x07")
        converter = Converter(source)

        self.assertEqual(converter.tags(self.NAMES, 0, len(source)), len(source))
        self.assertEqual(bytes(converter.out), self.tag_stream("<", 1, b"\x07"))

    def test_enum_byte_with_out_of_range_name_fails_closed(self):
        bad = struct.pack(">ii", 99, 0)
        source = self.tag_stream(">", 8, bad)
        converter = Converter(source)

        converter.tags(self.NAMES, 0, len(source))
        self.assertEqual(bytes(converter.out[32:40]), bad)
        self.assertEqual(converter.unsupported["ByteProperty enum value: bad FName"], 1)


class MaterialTailTests(unittest.TestCase):
    # Helmet_MASTER's FMaterial: no errors, empty dependency map, max length 1, GUID, 1 texcoord,
    # 4 textures, 5 UBOOLs + UsingTransforms, 1 texture lookup, dropped-fallback DWORD.
    FMATERIAL = [0, 0, 1, 11, 22, 33, 44, 1, 4, -286, -285, -278, -279,
                 0, 0, 0, 0, 0, 0, 1, 0, 0, 1065353216, 1065353216, 0]

    def pack(self, fmt, ints):
        return struct.pack(fmt + "%di" % len(ints), *ints)

    def test_material_resource_converts_exactly(self):
        source = self.pack(">", self.FMATERIAL)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("Material", 0, len(source)))
        self.assertEqual(bytes(converter.out), self.pack("<", self.FMATERIAL))

    def test_material_instance_static_parameters_convert(self):
        static = [5, 6, 7, 8,                       # BaseMaterialId
                  1, 451, 0, 1, 1, 9, 10, 11, 12,   # one static switch
                  0, 0, 0]                          # no masks, normals, terrain weights
        source = self.pack(">", self.FMATERIAL + static)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("MaterialInstanceConstant", 0, len(source)))
        self.assertEqual(bytes(converter.out), self.pack("<", self.FMATERIAL + static))

    def test_material_instance_without_static_permutation_is_empty(self):
        converter = Converter(b"")
        self.assertTrue(converter.native_tail("MaterialInstanceConstant", 0, 0))

    def test_material_with_trailing_unknown_data_fails_closed(self):
        source = self.pack(">", self.FMATERIAL + [7])
        converter = Converter(source)

        self.assertFalse(converter.native_tail("Material", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)


class PopulatedShaderCacheTests(unittest.TestCase):
    def test_populated_xbox_cache_swaps_priority_and_keeps_microcode(self):
        body = bytes(range(40))
        source = struct.pack(">iB", 10, 2) + body
        converter = Converter(source)

        self.assertTrue(converter.native_tail("ShaderCache", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<iB", 10, 2) + body)

    def test_populated_non_xbox_cache_fails_closed(self):
        source = struct.pack(">iB", 10, 1) + bytes(40)
        converter = Converter(source)

        self.assertFalse(converter.native_tail("ShaderCache", 0, len(source)))


class FaceFXTailTests(unittest.TestCase):
    def archive(self, sdk=1740, file_format=0):
        return b"FACB" + struct.pack(">II", sdk, file_format) + bytes(range(9))

    def test_big_endian_archive_counts_swap_and_bytes_stay_opaque(self):
        blob = self.archive()
        source = struct.pack(">i", len(blob)) + blob + struct.pack(">i", 0)
        converter = Converter(source)

        self.assertTrue(converter.native_tail("FaceFXAnimSet", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<i", len(blob)) + blob + struct.pack("<i", 0))

    def test_newer_facefx_sdk_fails_closed(self):
        blob = self.archive(sdk=1750)
        source = struct.pack(">i", len(blob)) + blob + struct.pack(">i", 0)
        converter = Converter(source)

        self.assertFalse(converter.native_tail("FaceFXAsset", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)


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

    def test_texture2d_metadata_converts_while_mip_bytes_stay_opaque(self):
        empty_bulk = struct.pack(">Iiii", 0, 0, 0, 0)
        pixels = bytes.fromhex("DE AD BE EF")
        mip_header_offset = 20
        mip_data_offset = mip_header_offset + 16
        mip = struct.pack(">Iiii", 0, len(pixels), len(pixels), mip_data_offset)
        guid_words = (0x11223344, 0x55667788, 0x10203040, 0x50607080)
        source = (empty_bulk + struct.pack(">i", 1) + mip + pixels +
                  struct.pack(">ii", 64, 32) + struct.pack(">IIII", *guid_words) +
                  struct.pack(">i", 0))
        converter = Converter(source)

        self.assertTrue(converter.native_tail("Texture2D", 0, len(source)))
        self.assertEqual(bytes(converter.out[mip_data_offset:mip_data_offset + len(pixels)]), pixels)
        self.assertEqual(struct.unpack_from("<ii", converter.out, mip_data_offset + len(pixels)),
                         (64, 32))
        self.assertEqual(struct.unpack_from("<IIII", converter.out,
                                            mip_data_offset + len(pixels) + 8), guid_words)

    def test_texture2d_impossible_mip_count_fails_closed(self):
        source = struct.pack(">Iiii", 0, 0, 0, 0) + struct.pack(">i", 0x10000000)
        converter = Converter(source)

        self.assertFalse(converter.native_tail("Texture2D", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_zero_script_uclass_payload_converts_all_persistent_containers(self):
        source = b"".join([
            struct.pack(">iii", 0, -98, 0),              # Next, SuperStruct, Children
            struct.pack(">ii", 0, 0),                   # logical/stored script sizes
            struct.pack(">IHI", 0x3002C9E9, 0xFFFF, 2), # UState fields
            struct.pack(">i", 0),                       # empty FuncMap
            struct.pack(">Iiii", 0x00800236, -10, 0x543, 0),
            struct.pack(">i", 1),                       # one component map pair
            struct.pack(">iii", 0x2D5, 0, 19),
            struct.pack(">i", 0),                       # no interfaces
            struct.pack(">iii", 0x51E, 0, 2),           # DLLBindName, CDO
        ])
        expected = b"".join([
            struct.pack("<iii", 0, -98, 0),
            struct.pack("<ii", 0, 0),
            struct.pack("<IHI", 0x3002C9E9, 0xFFFF, 2),
            struct.pack("<i", 0),
            struct.pack("<Iiii", 0x00800236, -10, 0x543, 0),
            struct.pack("<i", 1),
            struct.pack("<iii", 0x2D5, 0, 19),
            struct.pack("<i", 0),
            struct.pack("<iii", 0x51E, 0, 2),
        ])
        converter = Converter(source)

        self.assertTrue(converter.native_payload("Class", 0, len(source)))
        self.assertEqual(bytes(converter.out), expected)

    def test_uclass_with_bytecode_fails_closed_until_expr_walker_exists(self):
        source = struct.pack(">iiiii", 0, -98, 0, 1, 1) + b"\x53"
        converter = Converter(source)

        self.assertFalse(converter.native_payload("Class", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_uclass_out_of_range_reference_fails_closed(self):
        source = struct.pack(">iiiii", 0, -999, 0, 0, 0)
        converter = Converter(source)
        converter._name_count = 10
        converter._import_count = 100
        converter._export_count = 100

        self.assertFalse(converter.native_payload("Class", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)


if __name__ == "__main__":
    unittest.main()
