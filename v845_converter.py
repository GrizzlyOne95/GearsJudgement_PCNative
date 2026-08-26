"""UE3 v845 package conversion and relocation module.

Provides a relocation-capable package rewrite layer for UE3 v845/v828 packages,
supporting ShaderCache tail conversion, FVert BulkSerialize 16-to-24 header
retargeting, and relocation of populated width-changing FVert arrays.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


class ConversionError(ValueError):
    """Base exception for conversion errors."""


class ShaderCacheConversionError(ConversionError):
    """Raised when a ShaderCache payload cannot be converted safely."""


class FVertConversionError(ConversionError):
    """Raised when an FVert bulk array cannot be converted safely."""


def convert_shader_cache_payload(payload: bytes, source_endian: str = ">") -> bytes:
    """Convert a ShaderCache export native tail from Xbox 360 BE to PC LE.

    Payload format (29 bytes minimum):
    - 12-byte UObject prefix: NetIndex (int32), FName None (8 bytes: name_idx, num)
    - 17-byte native tail:
      priority (int32, 4 bytes)
      shader_platform (uint8, 1 byte) -- SP_XBOXD3D (2) -> SP_PCD3D_SM3 (0)
      compressed_map_count (int32, 4 bytes)
      shaders_count (int32, 4 bytes)
      material_maps_count (int32, 4 bytes)
    """
    if len(payload) < 29:
        raise ShaderCacheConversionError(
            f"ShaderCache payload too short: {len(payload)} bytes (expected at least 29)"
        )

    prefix = payload[:12]
    tail = payload[12:29]

    net_index, none_index, none_num = struct.unpack(f"{source_endian}iii", prefix)
    priority, platform, comp_count, shaders_count, mat_count = struct.unpack(
        f"{source_endian}iBiii", tail
    )

    if comp_count != 0 or shaders_count != 0 or mat_count != 0:
        raise ShaderCacheConversionError(
            f"Populated Xbox ShaderCache cannot be converted (compressed_maps={comp_count}, "
            f"shaders={shaders_count}, material_maps={mat_count}); failing closed"
        )

    le_prefix = struct.pack("<iii", -1, none_index, none_num)
    le_tail = struct.pack("<iBiii", priority, 0, 0, 0, 0)

    return le_prefix + le_tail + payload[29:]


def convert_fvert_bulk_array(
    payload: bytes,
    offset: int = 0,
    source_endian: str = ">",
    allow_relocation: bool = True,
) -> Tuple[bytes, int]:
    """Convert an FVert TArray::BulkSerialize header and payload.

    Header:
    - element_size (int32, 4 bytes): 16 on Xbox, 24 on PC
    - element_count (int32, 4 bytes): count of FVert vertices

    Returns (new_payload, size_delta).
    """
    if offset + 8 > len(payload):
        raise FVertConversionError("Truncated FVert bulk array header")

    elem_size, elem_count = struct.unpack(
        f"{source_endian}ii", payload[offset : offset + 8]
    )

    if elem_size != 16 and elem_size != 24:
        raise FVertConversionError(
            f"Unexpected FVert element size: {elem_size} (expected 16 or 24)"
        )

    if elem_count < 0:
        raise FVertConversionError(f"Negative FVert element count: {elem_count}")

    data_offset = offset + 8
    expected_data_size = elem_count * elem_size
    if data_offset + expected_data_size > len(payload):
        raise FVertConversionError("FVert bulk array data exceeds payload boundary")

    if elem_count == 0:
        new_header = struct.pack("<ii", 24, 0)
        new_payload = payload[:offset] + new_header + payload[data_offset:]
        return new_payload, 0

    if not allow_relocation:
        raise FVertConversionError(
            f"Populated FVert array ({elem_count} elements) requires payload relocation; failing closed"
        )

    old_data = payload[data_offset : data_offset + expected_data_size]
    new_header = struct.pack("<ii", 24, elem_count)

    new_data_blocks = []
    for i in range(elem_count):
        elem_16 = old_data[i * 16 : (i + 1) * 16]
        if source_endian == ">":
            d1, d2, d3, d4 = struct.unpack(">ffff", elem_16)
            elem_16_le = struct.pack("<ffff", d1, d2, d3, d4)
        else:
            elem_16_le = elem_16
        new_elem_24 = elem_16_le + (b"\x00" * 8)
        new_data_blocks.append(new_elem_24)

    new_data = b"".join(new_data_blocks)
    delta = len(new_data) - len(old_data)

    new_payload = (
        payload[:offset]
        + new_header
        + new_data
        + payload[data_offset + expected_data_size :]
    )
    return new_payload, delta


class FPackageFileSummary:
    def __init__(self):
        self.tag: int = 0x9E2A83C1
        self.engine_version: int = 845
        self.licensee_version: int = 0
        self.total_header_size: int = 0
        self.folder_name: str = "None"
        self.package_flags: int = 1
        self.name_count: int = 0
        self.name_offset: int = 0
        self.export_count: int = 0
        self.export_offset: int = 0
        self.import_count: int = 0
        self.import_offset: int = 0
        self.depends_offset: int = 0
        self.import_export_guids_offset: int = 0
        self.import_guids_count: int = 0
        self.export_guids_count: int = 0
        self.thumbnail_table_offset: int = 0
        self.guid: bytes = b"\x00" * 16
        self.generations: List[Dict[str, int]] = []
        self.saved_engine_version: int = 8741
        self.cooked_content_version: int = 134
        self.compression_flags: int = 0
        self.compressed_chunks: List[Tuple[int, int, int, int]] = []
        self.package_source: int = 0
        self.additional_packages: List[str] = []
        self.texture_allocations: List[bytes] = []
        self.endian: str = ">"


class FNameEntry:
    def __init__(self, name: str = "", flags: int = 0):
        self.name = name
        self.flags = flags


class FObjectImport:
    def __init__(self):
        self.class_package_index: int = 0
        self.class_package_number: int = 0
        self.class_name_index: int = 0
        self.class_name_number: int = 0
        self.outer_index: int = 0
        self.object_name_index: int = 0
        self.object_name_number: int = 0


class FObjectExport:
    def __init__(self):
        self.class_index: int = 0
        self.super_index: int = 0
        self.outer_index: int = 0
        self.object_name_index: int = 0
        self.object_name_number: int = 0
        self.archetype_index: int = 0
        self.object_flags: int = 0
        self.serial_size: int = 0
        self.serial_offset: int = 0
        self.export_flags: int = 0
        self.generation_net_object_counts: List[int] = []
        self.package_guid: bytes = b"\x00" * 16
        self.package_flags: int = 0
        self.payload: bytes = b""


class UE3Package:
    def __init__(self):
        self.summary = FPackageFileSummary()
        self.names: List[FNameEntry] = []
        self.imports: List[FObjectImport] = []
        self.exports: List[FObjectExport] = []
        self.depends: List[List[int]] = []

    @classmethod
    def from_bytes(cls, data: bytes) -> UE3Package:
        pkg = cls()
        if len(data) < 4:
            raise ConversionError("File too small to be a UE3 package")

        raw_tag = struct.unpack(">I", data[:4])[0]
        if raw_tag == 0x9E2A83C1:
            endian = ">"
        elif raw_tag == 0xC1832A9E:
            endian = "<"
        else:
            raise ConversionError(f"Invalid UE3 package tag: {raw_tag:#010x}")

        pkg.summary.endian = endian
        pos = 4
        packed_ver = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4
        pkg.summary.engine_version = packed_ver & 0xFFFF
        pkg.summary.licensee_version = (packed_ver >> 16) & 0xFFFF

        pkg.summary.total_header_size = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
        pos += 4

        # Read FolderName FString
        folder_len = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
        pos += 4
        if folder_len > 0:
            pkg.summary.folder_name = data[pos : pos + folder_len - 1].decode("latin1")
            pos += folder_len

        pkg.summary.package_flags = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4

        pkg.summary.name_count, pkg.summary.name_offset = struct.unpack(
            f"{endian}ii", data[pos : pos + 8]
        )
        pos += 8
        pkg.summary.export_count, pkg.summary.export_offset = struct.unpack(
            f"{endian}ii", data[pos : pos + 8]
        )
        pos += 8
        pkg.summary.import_count, pkg.summary.import_offset = struct.unpack(
            f"{endian}ii", data[pos : pos + 8]
        )
        pos += 8
        pkg.summary.depends_offset = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
        pos += 4

        if pkg.summary.engine_version >= 623:
            pkg.summary.import_export_guids_offset, pkg.summary.import_guids_count, pkg.summary.export_guids_count = struct.unpack(
                f"{endian}iii", data[pos : pos + 12]
            )
            pos += 12

        if pkg.summary.engine_version >= 584:
            pkg.summary.thumbnail_table_offset = struct.unpack(
                f"{endian}i", data[pos : pos + 4]
            )[0]
            pos += 4

        pkg.summary.guid = data[pos : pos + 16]
        pos += 16

        gen_count = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
        pos += 4
        for _ in range(gen_count):
            exp_cnt, nm_cnt, net_cnt = struct.unpack(f"{endian}iii", data[pos : pos + 12])
            pos += 12
            pkg.summary.generations.append(
                {"export_count": exp_cnt, "name_count": nm_cnt, "net_object_count": net_cnt}
            )

        pkg.summary.saved_engine_version = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4
        pkg.summary.cooked_content_version = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4
        pkg.summary.compression_flags = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4

        chunk_count = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
        pos += 4
        for _ in range(chunk_count):
            c = struct.unpack(f"{endian}iiii", data[pos : pos + 16])
            pos += 16
            pkg.summary.compressed_chunks.append(c)

        pkg.summary.package_source = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
        pos += 4

        if pkg.summary.engine_version >= 516:
            add_count = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
            pos += 4
            for _ in range(add_count):
                slen = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
                pos += 4
                if slen > 0:
                    pkg.summary.additional_packages.append(
                        data[pos : pos + slen - 1].decode("latin1")
                    )
                    pos += slen

        if pkg.summary.engine_version >= 767:
            tex_alloc_count = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
            pos += 4
            if tex_alloc_count != 0:
                raise ConversionError("Texture allocations parsing not implemented")

        # Parse Name Table
        pos = pkg.summary.name_offset
        for _ in range(pkg.summary.name_count):
            nlen = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
            pos += 4
            name_str = ""
            if nlen > 0:
                name_str = data[pos : pos + nlen - 1].decode("latin1")
                pos += nlen
            flags = struct.unpack(f"{endian}Q", data[pos : pos + 8])[0]
            pos += 8
            pkg.names.append(FNameEntry(name_str, flags))

        # Parse Import Table
        pos = pkg.summary.import_offset
        for _ in range(pkg.summary.import_count):
            imp = FObjectImport()
            (
                imp.class_package_index,
                imp.class_package_number,
                imp.class_name_index,
                imp.class_name_number,
                imp.outer_index,
                imp.object_name_index,
                imp.object_name_number,
            ) = struct.unpack(f"{endian}iiiiiii", data[pos : pos + 28])
            pos += 28
            pkg.imports.append(imp)

        # Parse Export Table
        pos = pkg.summary.export_offset
        for _ in range(pkg.summary.export_count):
            exp = FObjectExport()
            (
                exp.class_index,
                exp.super_index,
                exp.outer_index,
                exp.object_name_index,
                exp.object_name_number,
                exp.archetype_index,
            ) = struct.unpack(f"{endian}iiiiii", data[pos : pos + 24])
            pos += 24
            exp.object_flags = struct.unpack(f"{endian}Q", data[pos : pos + 8])[0]
            pos += 8
            exp.serial_size, exp.serial_offset, exp.export_flags = struct.unpack(
                f"{endian}iii", data[pos : pos + 12]
            )
            pos += 12
            gen_cnt = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
            pos += 4
            for _ in range(gen_cnt):
                exp.generation_net_object_counts.append(
                    struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
                )
                pos += 4
            exp.package_guid = data[pos : pos + 16]
            pos += 16
            exp.package_flags = struct.unpack(f"{endian}I", data[pos : pos + 4])[0]
            pos += 4

            if exp.serial_size > 0 and exp.serial_offset > 0:
                exp.payload = data[exp.serial_offset : exp.serial_offset + exp.serial_size]

            pkg.exports.append(exp)

        # Parse Depends Table
        pos = pkg.summary.depends_offset
        for _ in range(pkg.summary.export_count):
            dep_cnt = struct.unpack(f"{endian}i", data[pos : pos + 4])[0]
            pos += 4
            deps = []
            for _ in range(dep_cnt):
                deps.append(struct.unpack(f"{endian}i", data[pos : pos + 4])[0])
                pos += 4
            pkg.depends.append(deps)

        return pkg

    def get_name(self, index: int) -> str:
        if 0 <= index < len(self.names):
            return self.names[index].name
        return ""

    def get_resource_name(self, index: int) -> str:
        if index > 0 and index <= len(self.exports):
            return self.get_name(self.exports[index - 1].object_name_index)
        if index < 0 and -index <= len(self.imports):
            return self.get_name(self.imports[-index - 1].object_name_index)
        return "Class" if index == 0 else ""

    def to_bytes(
        self, target_endian: str = "<", target_engine_version: int = 828
    ) -> bytes:
        """Re-serialize package into binary format preserving all table invariants."""
        # Build Name Table
        name_bytes = bytearray()
        for n in self.names:
            encoded = n.name.encode("latin1") + b"\x00"
            name_bytes += struct.pack(f"{target_endian}i", len(encoded))
            name_bytes += encoded
            name_bytes += struct.pack(f"{target_endian}Q", n.flags)

        # Build Import Table
        import_bytes = bytearray()
        for imp in self.imports:
            import_bytes += struct.pack(
                f"{target_endian}iiiiiii",
                imp.class_package_index,
                imp.class_package_number,
                imp.class_name_index,
                imp.class_name_number,
                imp.outer_index,
                imp.object_name_index,
                imp.object_name_number,
            )

        # Build Depends Table
        depends_bytes = bytearray()
        for deps in self.depends:
            depends_bytes += struct.pack(f"{target_endian}i", len(deps))
            for dep in deps:
                depends_bytes += struct.pack(f"{target_endian}i", dep)

        # Build Summary
        summary_bytes = bytearray()
        tag = 0x9E2A83C1
        summary_bytes += struct.pack(f"{target_endian}I", tag)
        packed_ver = target_engine_version | (self.summary.licensee_version << 16)
        summary_bytes += struct.pack(f"{target_endian}I", packed_ver)

        # TotalHeaderSize placeholder
        total_header_patch_offset = len(summary_bytes)
        summary_bytes += struct.pack(f"{target_endian}i", 0)

        folder_encoded = self.summary.folder_name.encode("latin1") + b"\x00"
        summary_bytes += struct.pack(f"{target_endian}i", len(folder_encoded))
        summary_bytes += folder_encoded

        summary_bytes += struct.pack(f"{target_endian}I", self.summary.package_flags)

        name_offset_patch = len(summary_bytes) + 4
        summary_bytes += struct.pack(
            f"{target_endian}ii", len(self.names), 0
        )
        export_offset_patch = len(summary_bytes) + 4
        summary_bytes += struct.pack(
            f"{target_endian}ii", len(self.exports), 0
        )
        import_offset_patch = len(summary_bytes) + 4
        summary_bytes += struct.pack(
            f"{target_endian}ii", len(self.imports), 0
        )
        depends_offset_patch = len(summary_bytes)
        summary_bytes += struct.pack(f"{target_endian}i", 0)

        if target_engine_version >= 623:
            import_export_guids_patch = len(summary_bytes)
            summary_bytes += struct.pack(f"{target_endian}iii", 0, 0, 0)

        if target_engine_version >= 584:
            summary_bytes += struct.pack(f"{target_endian}i", 0)

        summary_bytes += self.summary.guid

        summary_bytes += struct.pack(f"{target_endian}i", len(self.summary.generations))
        for gen in self.summary.generations:
            summary_bytes += struct.pack(
                f"{target_endian}iii",
                gen["export_count"],
                gen["name_count"],
                gen["net_object_count"],
            )

        summary_bytes += struct.pack(f"{target_endian}I", self.summary.saved_engine_version)
        summary_bytes += struct.pack(f"{target_endian}I", self.summary.cooked_content_version)
        summary_bytes += struct.pack(f"{target_endian}I", 0)  # compression flags cleared
        summary_bytes += struct.pack(f"{target_endian}i", 0)  # no compressed chunks
        summary_bytes += struct.pack(f"{target_endian}I", self.summary.package_source)

        if target_engine_version >= 516:
            summary_bytes += struct.pack(f"{target_endian}i", len(self.summary.additional_packages))
            for pkg_name in self.summary.additional_packages:
                pkg_enc = pkg_name.encode("latin1") + b"\x00"
                summary_bytes += struct.pack(f"{target_endian}i", len(pkg_enc))
                summary_bytes += pkg_enc

        if target_engine_version >= 767:
            summary_bytes += struct.pack(f"{target_endian}i", len(self.summary.texture_allocations))

        # Calculate table offsets
        name_offset = len(summary_bytes)
        import_offset = name_offset + len(name_bytes)
        export_table_size = 0
        for exp in self.exports:
            export_table_size += 24 + 8 + 12 + 4 + len(exp.generation_net_object_counts) * 4 + 16 + 4
        export_offset = import_offset + len(import_bytes)
        depends_offset = export_offset + export_table_size
        total_header_size = depends_offset + len(depends_bytes)

        # Patch summary offsets
        struct.pack_into(f"{target_endian}i", summary_bytes, total_header_patch_offset, total_header_size)
        struct.pack_into(f"{target_endian}i", summary_bytes, name_offset_patch, name_offset)
        struct.pack_into(f"{target_endian}i", summary_bytes, import_offset_patch, import_offset)
        struct.pack_into(f"{target_endian}i", summary_bytes, export_offset_patch, export_offset)
        struct.pack_into(f"{target_endian}i", summary_bytes, depends_offset_patch, depends_offset)
        if target_engine_version >= 623:
            struct.pack_into(f"{target_endian}i", summary_bytes, import_export_guids_patch, total_header_size)

        # Build Export Table and Payloads with Relocation
        export_bytes = bytearray()
        payload_bytes = bytearray()
        current_serial_offset = total_header_size

        for exp in self.exports:
            new_serial_size = len(exp.payload)
            new_serial_offset = current_serial_offset if new_serial_size > 0 else 0

            export_bytes += struct.pack(
                f"{target_endian}iiiiii",
                exp.class_index,
                exp.super_index,
                exp.outer_index,
                exp.object_name_index,
                exp.object_name_number,
                exp.archetype_index,
            )
            export_bytes += struct.pack(f"{target_endian}Q", exp.object_flags)
            export_bytes += struct.pack(
                f"{target_endian}iii",
                new_serial_size,
                new_serial_offset,
                exp.export_flags & ~0x4,  # Clear EF_ForcedExport
            )
            export_bytes += struct.pack(f"{target_endian}i", len(exp.generation_net_object_counts))
            for net_cnt in exp.generation_net_object_counts:
                export_bytes += struct.pack(f"{target_endian}i", net_cnt)
            export_bytes += exp.package_guid
            export_bytes += struct.pack(f"{target_endian}I", exp.package_flags)

            if new_serial_size > 0:
                payload_bytes += exp.payload
                current_serial_offset += new_serial_size

        result = summary_bytes + name_bytes + import_bytes + export_bytes + depends_bytes + payload_bytes
        return bytes(result)


def convert_v845_package(
    pkg: UE3Package,
    allow_fvert_relocation: bool = True,
    target_engine_version: int = 828,
) -> UE3Package:
    """Apply ShaderCache and FVert payload conversions to a v845 UE3Package."""
    source_endian = pkg.summary.endian

    for i, exp in enumerate(pkg.exports):
        cls_name = pkg.get_resource_name(exp.class_index)
        obj_name = pkg.get_name(exp.object_name_index)

        # ShaderCache conversion
        if cls_name == "ShaderCache" or obj_name == "SeekFreeShaderCache":
            exp.payload = convert_shader_cache_payload(exp.payload, source_endian)

        # FVert conversion
        # Check if payload contains an FVert BulkSerialize header (element_size=16)
        if len(exp.payload) >= 8:
            # Simple heuristic / scanner for FVert bulk array in export payload
            for offset in range(0, len(exp.payload) - 7):
                try:
                    elem_size, elem_cnt = struct.unpack(
                        f"{source_endian}ii", exp.payload[offset : offset + 8]
                    )
                    if elem_size == 16 and elem_cnt >= 0:
                        data_end = offset + 8 + elem_cnt * elem_size
                        if data_end <= len(exp.payload):
                            new_payload, delta = convert_fvert_bulk_array(
                                exp.payload,
                                offset=offset,
                                source_endian=source_endian,
                                allow_relocation=allow_fvert_relocation,
                            )
                            exp.payload = new_payload
                            break
                except FVertConversionError:
                    raise
                except Exception:
                    pass

    return pkg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert UE3 v845 packages to LE v828/v845 with payload relocation."
    )
    parser.add_argument("input", type=Path, help="Input UE3 package (.xxx / .upk)")
    parser.add_argument("output", type=Path, help="Output UE3 package")
    parser.add_argument(
        "--disallow-fvert-relocation",
        action="store_true",
        help="Fail closed on populated FVert arrays requiring relocation",
    )
    parser.add_argument(
        "--target-version",
        type=int,
        default=828,
        help="Target UE3 engine version (default: 828)",
    )
    args = parser.parse_args()

    if args.output.exists():
        parser.error(f"Output file already exists: {args.output}")

    try:
        data = args.input.read_bytes()
        pkg = UE3Package.from_bytes(data)
        convert_v845_package(
            pkg,
            allow_fvert_relocation=not args.disallow_fvert_relocation,
            target_engine_version=args.target_version,
        )
        out_bytes = pkg.to_bytes(
            target_endian="<", target_engine_version=args.target_version
        )
        args.output.write_bytes(out_bytes)
        print(f"Successfully converted {args.input} -> {args.output} ({len(out_bytes)} bytes)")
        return 0
    except Exception as exc:
        parser.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
