import unittest
import struct
from v845_package_rewrite import (
    retarget_shader_cache_tail,
    retarget_fvert_bulk_header,
    SyntheticPackage,
    PackageRewriteError,
)


class TestV845Rewrite(unittest.TestCase):
    def test_empty_shader_cache_retarget(self):
        # Xbox BE format: priority=10 (0x0A), platform=2 (SP_XBOXD3D), map_count=0, shaders=0, material_maps=0
        be_tail = struct.pack(">IBIII", 10, 2, 0, 0, 0)
        self.assertEqual(len(be_tail), 17)
        self.assertEqual(be_tail, b"\x00\x00\x00\x0a\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")

        le_tail = retarget_shader_cache_tail(be_tail, src_big_endian=True)
        # PC LE format: priority=10, platform=0 (SP_PCD3D_SM3), map_count=0, shaders=0, material_maps=0
        expected_le = struct.pack("<IBIII", 10, 0, 0, 0, 0)
        self.assertEqual(le_tail, expected_le)
        self.assertEqual(le_tail, b"\x0a\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")

    def test_populated_shader_cache_rejection(self):
        # Xbox BE format with non-zero map_count = 1
        be_tail_populated = struct.pack(">IBIII", 10, 2, 1, 0, 0)
        with self.assertRaisesRegex(PackageRewriteError, "Populated Xbox ShaderCache cannot be retargeted"):
            retarget_shader_cache_tail(be_tail_populated, src_big_endian=True)

    def test_empty_fvert_bulk_header_retarget(self):
        # BE console FVert bulk header: elem_size=16, count=0
        be_header = struct.pack(">II", 16, 0)
        le_header = retarget_fvert_bulk_header(be_header, src_big_endian=True)
        # LE PC FVert bulk header: elem_size=24, count=0
        expected_le = struct.pack("<II", 24, 0)
        self.assertEqual(le_header, expected_le)

    def test_populated_fvert_bulk_header_rejection(self):
        # BE console FVert bulk header: elem_size=16, count=5
        be_header_populated = struct.pack(">II", 16, 5)
        with self.assertRaisesRegex(PackageRewriteError, "Populated width-changing FVert array"):
            retarget_fvert_bulk_header(be_header_populated, src_big_endian=True)

    def test_synthetic_package_export_relocation(self):
        pkg = SyntheticPackage(header_size=100)
        exp0 = pkg.add_export("Export0", b"1234")      # offset 100, size 4
        exp1 = pkg.add_export("Export1", b"abc")       # offset 104, size 3
        exp2 = pkg.add_export("Export2", b"XYZ123")    # offset 107, size 6

        self.assertTrue(pkg.verify_invariants())
        self.assertEqual(exp0.serial_offset, 100)
        self.assertEqual(exp1.serial_offset, 104)
        self.assertEqual(exp2.serial_offset, 107)

        # Relocate exp1 by growing payload from 3 bytes to 7 bytes (+4 offset shift for downstream)
        pkg.relocate_export(1, b"abcdefg")
        self.assertTrue(pkg.verify_invariants())

        self.assertEqual(exp0.serial_offset, 100)
        self.assertEqual(exp1.serial_offset, 104)
        self.assertEqual(exp1.serial_size, 7)
        self.assertEqual(exp2.serial_offset, 111)


if __name__ == "__main__":
    unittest.main()
