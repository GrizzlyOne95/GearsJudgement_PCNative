import struct
import unittest

from v845_rewrite import (
    FVertError,
    NameRef,
    ShaderCacheError,
    SP_PCD3D_SM3,
    SP_XBOXD3D,
    V845Package,
    convert_fvert_bulk_array,
    convert_shader_cache_tail,
)


def create_synthetic_v845_package(endian: str = "big", export_payloads=None) -> bytes:
    """Helper to build a valid uncompressed synthetic UE3 v845 package in memory."""
    fmt32 = "<i" if endian == "little" else ">i"
    fmtU32 = "<I" if endian == "little" else ">I"
    fmtU64 = "<Q" if endian == "little" else ">Q"

    if export_payloads is None:
        export_payloads = [b"\x00" * 32, b"\x01" * 16]

    tag = 0x9E2A83C1 if endian == "little" else 0xC1832A9E

    # Build Name table
    names = ["None", "Package", "ShaderCache", "SeekFreeShaderCache", "Model", "FVertOwner"]
    name_table = bytearray()
    for name in names:
        encoded = name.encode("latin1") + b"\x00"
        name_table.extend(struct.pack(fmt32, len(encoded)))
        name_table.extend(encoded)
        name_table.extend(struct.pack(fmtU64, 0))

    # Build Import table
    import_table = bytearray()
    # 1 import: Core.Package
    # NameRef: class_package(0,0), class_name(1,0), outer(0), object_name(1,0)
    import_table.extend(struct.pack(fmt32, 0) + struct.pack(fmt32, 0))
    import_table.extend(struct.pack(fmt32, 1) + struct.pack(fmt32, 0))
    import_table.extend(struct.pack(fmt32, 0))
    import_table.extend(struct.pack(fmt32, 1) + struct.pack(fmt32, 0))

    # Header calculations
    # Build summary up to Name table
    header = bytearray()
    header.extend(struct.pack("<I", tag))
    header.extend(struct.pack(fmtU32, 845))  # packed version

    total_header_patch = len(header)
    header.extend(struct.pack(fmt32, 0))  # TotalHeaderSize placeholder

    # FolderName FString("None")
    header.extend(struct.pack(fmt32, 5) + b"None\x00")
    header.extend(struct.pack(fmtU32, 0x00000001))  # package flags

    name_count_patch = len(header)
    header.extend(struct.pack(fmt32, len(names)))
    name_offset_patch = len(header)
    header.extend(struct.pack(fmt32, 0))

    export_count_patch = len(header)
    header.extend(struct.pack(fmt32, len(export_payloads)))
    export_offset_patch = len(header)
    header.extend(struct.pack(fmt32, 0))

    import_count_patch = len(header)
    header.extend(struct.pack(fmt32, 1))
    import_offset_patch = len(header)
    header.extend(struct.pack(fmt32, 0))

    depends_offset_patch = len(header)
    header.extend(struct.pack(fmt32, 0))

    header.extend(struct.pack(fmt32, 0))  # ImportExportGuidsOffset
    header.extend(struct.pack(fmt32, 0))  # ImportGuidsCount
    header.extend(struct.pack(fmt32, 0))  # ExportGuidsCount
    header.extend(struct.pack(fmt32, 0))  # ThumbnailTableOffset
    header.extend(b"\x00" * 16)  # Guid

    header.extend(struct.pack(fmt32, 1))  # GenerationCount
    header.extend(struct.pack(fmt32, len(export_payloads)))
    header.extend(struct.pack(fmt32, len(names)))
    header.extend(struct.pack(fmt32, 0))

    header.extend(struct.pack(fmtU32, 8741))  # SavedEngineVersion
    header.extend(struct.pack(fmtU32, 134))  # CookedContentVersion
    header.extend(struct.pack(fmtU32, 0))  # CompressionFlags
    header.extend(struct.pack(fmt32, 0))  # ChunkCount
    header.extend(struct.pack(fmtU32, 0))  # PackageSource
    header.extend(struct.pack(fmt32, 0))  # AdditionalPackages count
    header.extend(struct.pack(fmt32, 0))  # TextureAllocations count

    name_offset = len(header)
    import_offset = name_offset + len(name_table)

    # Export record size: 44 + 4 + 0 + 16 + 4 = 68
    export_rec_size = 68
    export_offset = import_offset + len(import_table)
    depends_offset = export_offset + len(export_payloads) * export_rec_size

    depends_table = bytearray()
    for _ in range(len(export_payloads)):
        depends_table.extend(struct.pack(fmt32, 0))  # 0 dependencies each

    total_header_size = depends_offset + len(depends_table)

    struct.pack_into(fmt32, header, total_header_patch, total_header_size)
    struct.pack_into(fmt32, header, name_offset_patch, name_offset)
    struct.pack_into(fmt32, header, import_offset_patch, import_offset)
    struct.pack_into(fmt32, header, export_offset_patch, export_offset)
    struct.pack_into(fmt32, header, depends_offset_patch, depends_offset)

    # Build export table and payloads
    export_table = bytearray()
    payloads_bytes = bytearray()
    current_offset = total_header_size

    for i, payload in enumerate(export_payloads):
        serial_size = len(payload)
        serial_offset = current_offset

        export_table.extend(struct.pack(fmt32, -1))  # class_index -> import 1
        export_table.extend(struct.pack(fmt32, 0))  # super_index
        export_table.extend(struct.pack(fmt32, 0))  # outer_index
        name_idx = 3 if i == 0 else (4 if i == 1 else 5)
        export_table.extend(struct.pack(fmt32, name_idx) + struct.pack(fmt32, 0))  # object_name
        export_table.extend(struct.pack(fmt32, 0))  # archetype_index
        export_table.extend(struct.pack(fmtU64, 0))  # object_flags
        export_table.extend(struct.pack(fmt32, serial_size))
        export_table.extend(struct.pack(fmt32, serial_offset))
        export_table.extend(struct.pack(fmtU32, 0))  # export_flags
        export_table.extend(struct.pack(fmt32, 0))  # generation net object count
        export_table.extend(b"\x00" * 16)  # package guid
        export_table.extend(struct.pack(fmtU32, 0))  # package flags

        payloads_bytes.extend(payload)
        current_offset += serial_size

    return bytes(header + name_table + import_table + export_table + depends_table + payloads_bytes)


class TestV845Rewrite(unittest.TestCase):
    def test_package_parsing_and_invariants(self):
        raw_pkg = create_synthetic_v845_package(endian="big")
        pkg = V845Package(raw_pkg)

        self.assertEqual(pkg.endian, "big")
        self.assertEqual(pkg.engine_version, 845)
        self.assertEqual(pkg.export_count, 2)
        self.assertEqual(pkg.import_count, 1)
        self.assertEqual(len(pkg.names), 6)

        # Rewrite to little-endian without payload changes
        rewritten = pkg.rewrite_package(target_endian="little")
        pkg_le = V845Package(rewritten)
        self.assertEqual(pkg_le.endian, "little")
        self.assertEqual(pkg_le.export_count, 2)
        self.assertEqual(pkg_le.exports[0].serial_size, 32)
        self.assertEqual(pkg_le.exports[1].serial_size, 16)
        self.assertEqual(pkg_le.exports[0].serial_offset, pkg_le.total_header_size)
        self.assertEqual(pkg_le.exports[1].serial_offset, pkg_le.total_header_size + 32)

    def test_payload_growth_and_relocation(self):
        raw_pkg = create_synthetic_v845_package(endian="big")
        pkg = V845Package(raw_pkg)

        # Grow payload of export 0 from 32 bytes to 100 bytes
        new_payload_0 = b"\xAA" * 100
        pkg.set_export_payload(0, new_payload_0)

        rewritten = pkg.rewrite_package(target_endian="little")
        pkg_relocated = V845Package(rewritten)

        self.assertEqual(pkg_relocated.exports[0].serial_size, 100)
        self.assertEqual(pkg_relocated.exports[0].payload, new_payload_0)
        self.assertEqual(pkg_relocated.exports[1].serial_offset, pkg_relocated.total_header_size + 100)
        self.assertEqual(pkg_relocated.exports[1].serial_size, 16)

    def test_empty_shader_cache_tail_conversion(self):
        # Empty Xbox ShaderCache tail: priority=10, SP_XBOXD3D=2, 0, 0, 0
        prefix = b"\xFF\xFF\xFF\xFF" + b"\x00" * 8  # 12-byte UObject prefix
        xbox_tail = struct.pack(">iBiii", 10, SP_XBOXD3D, 0, 0, 0)
        payload = prefix + xbox_tail

        converted = convert_shader_cache_tail(payload, source_endian="big")
        self.assertEqual(len(converted), 29)

        # Verify target LE tail: priority=10, SP_PCD3D_SM3=0, 0, 0, 0
        p_val, platform, c_cnt, s_cnt, m_cnt = struct.unpack_from("<iBiii", converted, 12)
        self.assertEqual(p_val, 10)
        self.assertEqual(platform, SP_PCD3D_SM3)
        self.assertEqual(c_cnt, 0)
        self.assertEqual(s_cnt, 0)
        self.assertEqual(m_cnt, 0)

    def test_populated_shader_cache_rejection(self):
        prefix = b"\xFF\xFF\xFF\xFF" + b"\x00" * 8
        populated_tail = struct.pack(">iBiii", 10, SP_XBOXD3D, 1, 0, 0)
        payload = prefix + populated_tail

        with self.assertRaises(ShaderCacheError) as ctx:
            convert_shader_cache_tail(payload, source_endian="big")
        self.assertIn("Populated ShaderCache cannot be converted", str(ctx.exception))

    def test_empty_fvert_bulk_header_retargeting(self):
        # 12-byte UObject prefix + 8-byte bulk header (elem_size=16, count=0)
        prefix = b"\x00" * 12
        hdr_16 = struct.pack(">ii", 16, 0)
        payload = prefix + hdr_16

        converted = convert_fvert_bulk_array(payload, source_endian="big", offset_in_payload=12)

        elem_size, elem_cnt = struct.unpack_from("<ii", converted, 12)
        self.assertEqual(elem_size, 24)
        self.assertEqual(elem_cnt, 0)

    def test_populated_fvert_rejection_when_not_widened(self):
        prefix = b"\x00" * 12
        hdr_populated = struct.pack(">ii", 16, 2)
        data = b"\x01" * 32  # 2 elements * 16 bytes
        payload = prefix + hdr_populated + data

        with self.assertRaises(FVertError) as ctx:
            convert_fvert_bulk_array(
                payload, source_endian="big", offset_in_payload=12, widen_populated=False
            )
        self.assertIn("Populated FVert array (2 elements) retargeting rejected", str(ctx.exception))

    def test_populated_fvert_widening_and_relocation(self):
        prefix = b"\x00" * 12
        hdr_populated = struct.pack(">ii", 16, 2)
        elem1 = b"\x11" * 16
        elem2 = b"\x22" * 16
        suffix = b"END_MARKER"
        payload = prefix + hdr_populated + elem1 + elem2 + suffix

        converted = convert_fvert_bulk_array(
            payload, source_endian="big", offset_in_payload=12, widen_populated=True
        )

        elem_size, elem_cnt = struct.unpack_from("<ii", converted, 12)
        self.assertEqual(elem_size, 24)
        self.assertEqual(elem_cnt, 2)

        # Check widened element bytes
        offset = 20
        w_elem1 = converted[offset : offset + 24]
        self.assertEqual(w_elem1[:16], elem1)
        self.assertEqual(w_elem1[16:], b"\x00" * 8)

        w_elem2 = converted[offset + 24 : offset + 48]
        self.assertEqual(w_elem2[:16], elem2)
        self.assertEqual(w_elem2[16:], b"\x00" * 8)

        self.assertEqual(converted[offset + 48 :], suffix)

    def test_package_rewrite_with_fvert_widening(self):
        prefix = b"\x00" * 12
        hdr_populated = struct.pack(">ii", 16, 2)
        elem_data = b"\x05" * 32
        payload_0 = prefix + hdr_populated + elem_data
        payload_1 = b"Export1Data"

        raw_pkg = create_synthetic_v845_package(endian="big", export_payloads=[payload_0, payload_1])
        pkg = V845Package(raw_pkg)

        # Convert export 0 payload (widening FVert array from 16 -> 24 bytes per elem)
        new_payload_0 = convert_fvert_bulk_array(pkg.exports[0].payload, source_endian="big")
        pkg.set_export_payload(0, new_payload_0)

        rewritten = pkg.rewrite_package(target_endian="little")
        pkg_relocated = V845Package(rewritten)

        # Export 0 grew from 12+8+32=52 bytes to 12+8+48=68 bytes
        self.assertEqual(pkg_relocated.exports[0].serial_size, 68)
        self.assertEqual(pkg_relocated.exports[1].serial_offset, pkg_relocated.total_header_size + 68)
        self.assertEqual(pkg_relocated.exports[1].payload, payload_1)


if __name__ == "__main__":
    unittest.main()
