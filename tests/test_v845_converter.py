"""Synthetic regression test harness for v845_converter module."""

import struct
import unittest
from pathlib import Path
import tempfile

from v845_converter import (
    FNameEntry,
    FObjectExport,
    FVertConversionError,
    ShaderCacheConversionError,
    UE3Package,
    convert_fvert_bulk_array,
    convert_shader_cache_payload,
    convert_v845_package,
)


class ShaderCacheConversionTests(unittest.TestCase):
    def test_empty_xbox_shader_cache_converts_to_pc_d3d_sm3(self):
        # 12-byte UObject prefix (BE) + 17-byte Xbox tail (BE)
        # prefix: NetIndex=-1, FName None index 0, num 0
        # tail: priority=10, platform=SP_XBOXD3D (2), comp=0, shaders=0, mat=0
        prefix = struct.pack(">iii", -1, 0, 0)
        tail = struct.pack(">iBiii", 10, 2, 0, 0, 0)
        payload = prefix + tail

        converted = convert_shader_cache_payload(payload, source_endian=">")

        self.assertEqual(len(converted), 29)
        le_net_index, le_none_idx, le_none_num = struct.unpack("<iii", converted[:12])
        self.assertEqual(le_net_index, -1)
        self.assertEqual(le_none_idx, 0)
        self.assertEqual(le_none_num, 0)

        le_priority, le_platform, comp, shaders, mat = struct.unpack(
            "<iBiii", converted[12:29]
        )
        self.assertEqual(le_priority, 10)
        self.assertEqual(le_platform, 0)  # SP_PCD3D_SM3 = 0
        self.assertEqual(comp, 0)
        self.assertEqual(shaders, 0)
        self.assertEqual(mat, 0)

    def test_populated_shader_cache_fails_closed(self):
        prefix = struct.pack(">iii", -1, 0, 0)
        # Non-zero shader map count
        tail = struct.pack(">iBiii", 10, 2, 1, 0, 0)
        payload = prefix + tail

        with self.assertRaises(ShaderCacheConversionError) as ctx:
            convert_shader_cache_payload(payload, source_endian=">")
        self.assertIn("Populated Xbox ShaderCache cannot be converted", str(ctx.exception))


class FVertConversionTests(unittest.TestCase):
    def test_empty_fvert_header_retargets_16_to_24(self):
        # Bulk header: element_size=16, element_count=0
        header = struct.pack(">ii", 16, 0)
        payload = b"\x00" * 12 + header + b"\x00" * 4

        new_payload, delta = convert_fvert_bulk_array(
            payload, offset=12, source_endian=">", allow_relocation=False
        )

        self.assertEqual(delta, 0)
        self.assertEqual(len(new_payload), len(payload))
        new_size, new_count = struct.unpack("<ii", new_payload[12:20])
        self.assertEqual(new_size, 24)
        self.assertEqual(new_count, 0)

    def test_populated_fvert_fails_closed_when_relocation_disallowed(self):
        header = struct.pack(">ii", 16, 2)
        # 2 elements * 16 bytes = 32 bytes data
        data = struct.pack(">ffffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
        payload = header + data

        with self.assertRaises(FVertConversionError) as ctx:
            convert_fvert_bulk_array(
                payload, offset=0, source_endian=">", allow_relocation=False
            )
        self.assertIn("requires payload relocation; failing closed", str(ctx.exception))

    def test_populated_fvert_relocates_and_widens_when_allowed(self):
        header = struct.pack(">ii", 16, 2)
        # Element 1: 1.0, 2.0, 3.0, 4.0 | Element 2: 5.0, 6.0, 7.0, 8.0
        data = struct.pack(">ffffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
        payload = b"PREFIX_" + header + data + b"_SUFFIX"

        new_payload, delta = convert_fvert_bulk_array(
            payload, offset=7, source_endian=">", allow_relocation=True
        )

        # 2 elements * (24 - 16) = 16 bytes growth
        self.assertEqual(delta, 16)
        self.assertEqual(len(new_payload), len(payload) + 16)
        self.assertTrue(new_payload.startswith(b"PREFIX_"))
        self.assertTrue(new_payload.endswith(b"_SUFFIX"))

        new_size, new_count = struct.unpack("<ii", new_payload[7:15])
        self.assertEqual(new_size, 24)
        self.assertEqual(new_count, 2)

        elem1 = new_payload[15:39]
        elem2 = new_payload[39:63]
        v1_x, v1_y, v1_z, v1_w = struct.unpack("<ffff", elem1[:16])
        self.assertAlmostEqual(v1_x, 1.0)
        self.assertAlmostEqual(v1_y, 2.0)
        self.assertAlmostEqual(v1_z, 3.0)
        self.assertAlmostEqual(v1_w, 4.0)
        self.assertEqual(elem1[16:], b"\x00" * 8)

        v2_x, v2_y, v2_z, v2_w = struct.unpack("<ffff", elem2[:16])
        self.assertAlmostEqual(v2_x, 5.0)
        self.assertAlmostEqual(v2_y, 6.0)
        self.assertAlmostEqual(v2_z, 7.0)
        self.assertAlmostEqual(v2_w, 8.0)
        self.assertEqual(elem2[16:], b"\x00" * 8)


class SyntheticPackageRewriteTests(unittest.TestCase):
    def test_synthetic_v845_package_relocation_and_invariants(self):
        # Construct a synthetic BE v845 UE3Package
        pkg = UE3Package()
        pkg.summary.endian = ">"
        pkg.summary.engine_version = 845
        pkg.summary.licensee_version = 0
        pkg.summary.folder_name = "None"
        pkg.summary.saved_engine_version = 9580
        pkg.summary.cooked_content_version = 134

        pkg.names.append(FNameEntry("None", 0))
        pkg.names.append(FNameEntry("ShaderCache", 0))
        pkg.names.append(FNameEntry("SeekFreeShaderCache", 0))
        pkg.names.append(FNameEntry("StaticMesh", 0))
        pkg.names.append(FNameEntry("MyStaticMesh", 0))

        # Export 1: ShaderCache
        exp1 = FObjectExport()
        exp1.class_index = 0
        exp1.super_index = 0
        exp1.outer_index = 0
        exp1.object_name_index = 2  # SeekFreeShaderCache
        exp1.object_name_number = 0
        exp1.archetype_index = 0
        exp1.object_flags = 0
        exp1.export_flags = 0
        exp1.generation_net_object_counts = [0]
        exp1.package_guid = b"\x00" * 16
        exp1.package_flags = 0
        # empty Xbox ShaderCache payload
        exp1.payload = struct.pack(">iii", -1, 0, 0) + struct.pack(">iBiii", 10, 2, 0, 0, 0)
        exp1.serial_size = len(exp1.payload)
        exp1.serial_offset = 0

        # Export 2: StaticMesh with populated FVert array (2 elements)
        exp2 = FObjectExport()
        exp2.class_index = 0
        exp2.super_index = 0
        exp2.outer_index = 0
        exp2.object_name_index = 4  # MyStaticMesh
        exp2.object_name_number = 0
        exp2.archetype_index = 0
        exp2.object_flags = 0
        exp2.export_flags = 0
        exp2.generation_net_object_counts = [0]
        exp2.package_guid = b"\x00" * 16
        exp2.package_flags = 0

        fvert_header = struct.pack(">ii", 16, 2)
        fvert_data = struct.pack(">ffffffff", 1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0)
        exp2.payload = b"HEADER_" + fvert_header + fvert_data + b"_FOOTER"
        orig_exp2_payload_len = len(exp2.payload)
        exp2.serial_size = orig_exp2_payload_len
        exp2.serial_offset = 0

        pkg.exports = [exp1, exp2]
        pkg.depends = [[], []]

        # Convert package
        converted_pkg = convert_v845_package(pkg, allow_fvert_relocation=True, target_engine_version=828)
        out_bytes = converted_pkg.to_bytes(target_endian="<", target_engine_version=828)

        # Parse written package independently
        reparsed = UE3Package.from_bytes(out_bytes)
        self.assertEqual(reparsed.summary.endian, "<")
        self.assertEqual(reparsed.summary.engine_version, 828)
        self.assertEqual(len(reparsed.exports), 2)

        # Check export 1 (ShaderCache)
        sc_exp = reparsed.exports[0]
        self.assertEqual(sc_exp.serial_size, 29)
        self.assertEqual(sc_exp.payload[12 + 4], 0)  # SP_PCD3D_SM3

        # Check export 2 (StaticMesh with FVert)
        sm_exp = reparsed.exports[1]
        self.assertEqual(sm_exp.serial_size, orig_exp2_payload_len + 16)
        # Serial offset of export 2 should equal serial_offset of export 1 + serial_size of export 1
        self.assertEqual(sm_exp.serial_offset, sc_exp.serial_offset + sc_exp.serial_size)


if __name__ == "__main__":
    unittest.main()
