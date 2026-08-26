"""Relocation-capable UE3 v845 package rewriter and native tail converter.

This module provides tools for parsing, payload relocation, native-tail retargeting,
and byte-order conversion of UE3 version 845 packages.

Key capabilities:
- Payload relocation: grows/shrinks export payloads, recomputes export serial
  offsets and sizes, and preserves summary/name/import/export/depends invariants.
- ShaderCache native tail retargeting:
  * Accepts exact empty Xbox ShaderCache (SP_XBOXD3D = 2) and retargets to PC (SP_PCD3D_SM3 = 0).
  * Fails closed (raises ShaderCacheError) if ShaderCache contains populated shader maps.
- FVert bulk array retargeting and widening:
  * Converts empty FVert bulk header element-size from 16 to 24 bytes (count = 0).
  * Widens populated FVert bulk array elements from 16 to 24 bytes (adding 8-byte
    BackfaceShadowTexCoord), relocates payload, and updates export serial offset/size.
  * Fails closed (raises FVertError) on invalid or unsupported array framing.
"""

from __future__ import annotations

import struct
from typing import Callable, Dict, List, Optional, Tuple


PACKAGE_TAG_LE = 0x9E2A83C1
PACKAGE_TAG_BE = 0xC1832A9E

SP_PCD3D_SM3 = 0
SP_XBOXD3D = 2


class PackageRewriteError(Exception):
    """Base exception for package rewrite errors."""


class ShaderCacheError(PackageRewriteError):
    """Raised when ShaderCache conversion fails or encounters populated data."""


class FVertError(PackageRewriteError):
    """Raised when FVert bulk array conversion fails or has invalid framing."""


class FString:
    @staticmethod
    def read(data: bytes, offset: int, endian: str) -> Tuple[str, int]:
        fmt = "<i" if endian == "little" else ">i"
        (length,) = struct.unpack_from(fmt, data, offset)
        offset += 4
        if length == 0:
            return "", offset
        if length > 0:
            # ANSI
            raw = data[offset : offset + length]
            offset += length
            return raw.rstrip(b"\x00").decode("latin1", errors="replace"), offset
        else:
            # UTF-16
            units = -length
            raw = data[offset : offset + units * 2]
            offset += units * 2
            return raw.decode("utf-16le" if endian == "little" else "utf-16be", errors="replace").rstrip("\x00"), offset

    @staticmethod
    def pack(value: str, endian: str) -> bytes:
        fmt = "<i" if endian == "little" else ">i"
        encoded = value.encode("latin1") + b"\x00"
        return struct.pack(fmt, len(encoded)) + encoded


class NameRef:
    def __init__(self, index: int, number: int):
        self.index = index
        self.number = number

    @classmethod
    def read(cls, data: bytes, offset: int, endian: str) -> Tuple["NameRef", int]:
        fmt = "<ii" if endian == "little" else ">ii"
        idx, num = struct.unpack_from(fmt, data, offset)
        return cls(idx, num), offset + 8

    def pack(self, endian: str) -> bytes:
        fmt = "<ii" if endian == "little" else ">ii"
        return struct.pack(fmt, self.index, self.number)


class ManifestExportEntry:
    def __init__(
        self,
        class_index: int,
        super_index: int,
        outer_index: int,
        object_name: NameRef,
        archetype_index: int,
        object_flags: int,
        serial_size: int,
        serial_offset: int,
        export_flags: int,
        generation_net_object_counts: List[int],
        package_guid: bytes,
        package_flags: int,
        payload: bytes = b"",
    ):
        self.class_index = class_index
        self.super_index = super_index
        self.outer_index = outer_index
        self.object_name = object_name
        self.archetype_index = archetype_index
        self.object_flags = object_flags
        self.serial_size = serial_size
        self.serial_offset = serial_offset
        self.export_flags = export_flags
        self.generation_net_object_counts = generation_net_object_counts
        self.package_guid = package_guid
        self.package_flags = package_flags
        self.payload = payload


class V845Package:
    def __init__(self, data: bytes):
        self.original_data = data
        self.endian = self._detect_endian(data)
        self._parse()

    @staticmethod
    def _detect_endian(data: bytes) -> str:
        if len(data) < 4:
            raise PackageRewriteError("Package data too short")
        tag = struct.unpack_from("<I", data, 0)[0]
        if tag == PACKAGE_TAG_LE:
            return "little"
        elif tag == PACKAGE_TAG_BE:
            return "big"
        else:
            raise PackageRewriteError(f"Invalid package tag: 0x{tag:08X}")

    def _parse(self):
        data = self.original_data
        endian = self.endian
        fmt32 = "<i" if endian == "little" else ">i"
        fmtU32 = "<I" if endian == "little" else ">I"
        fmtU64 = "<Q" if endian == "little" else ">Q"

        offset = 4  # Tag
        self.packed_version = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4
        self.engine_version = self.packed_version & 0xFFFF
        self.licensee_version = self.packed_version >> 16

        self.total_header_size = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4

        self.folder_name, offset = FString.read(data, offset, endian)

        self.package_flags = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4

        self.name_count, self.name_offset = struct.unpack_from(
            "<ii" if endian == "little" else ">ii", data, offset
        )
        offset += 8

        self.export_count, self.export_offset = struct.unpack_from(
            "<ii" if endian == "little" else ">ii", data, offset
        )
        offset += 8

        self.import_count, self.import_offset = struct.unpack_from(
            "<ii" if endian == "little" else ">ii", data, offset
        )
        offset += 8

        self.depends_offset = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4

        self.import_export_guids_offset = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4
        self.import_guids_count = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4
        self.export_guids_count = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4

        self.thumbnail_table_offset = struct.unpack_from(fmt32, data, offset)[0]
        offset += 4

        self.guid = data[offset : offset + 16]
        offset += 16

        (gen_count,) = struct.unpack_from(fmt32, data, offset)
        offset += 4
        self.generations = []
        for _ in range(gen_count):
            exp_c, name_c, net_c = struct.unpack_from(
                "<iii" if endian == "little" else ">iii", data, offset
            )
            offset += 12
            self.generations.append((exp_c, name_c, net_c))

        self.saved_engine_version = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4
        self.cooked_content_version = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4
        self.compression_flags = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4

        (chunk_count,) = struct.unpack_from(fmt32, data, offset)
        offset += 4
        self.chunks = []
        for _ in range(chunk_count):
            u_off, u_sz, c_off, c_sz = struct.unpack_from(
                "<iiii" if endian == "little" else ">iiii", data, offset
            )
            offset += 16
            self.chunks.append((u_off, u_sz, c_off, c_sz))

        self.package_source = struct.unpack_from(fmtU32, data, offset)[0]
        offset += 4

        (add_count,) = struct.unpack_from(fmt32, data, offset)
        offset += 4
        self.additional_packages = []
        for _ in range(add_count):
            pkg, offset = FString.read(data, offset, endian)
            self.additional_packages.append(pkg)

        (tex_alloc_count,) = struct.unpack_from(fmt32, data, offset)
        offset += 4
        self.texture_allocations_raw_bytes = b""
        if tex_alloc_count > 0:
            start_alloc = offset
            for _ in range(tex_alloc_count):
                offset += 5 * 4
                (exp_cnt,) = struct.unpack_from(fmt32, data, offset)
                offset += 4 + exp_cnt * 4
            self.texture_allocations_raw_bytes = data[start_alloc:offset]

        self.summary_end_offset = offset

        # Parse Name Table
        self.names = []
        name_cursor = self.name_offset
        for _ in range(self.name_count):
            name_str, name_cursor = FString.read(data, name_cursor, endian)
            flags = struct.unpack_from(fmtU64, data, name_cursor)[0]
            name_cursor += 8
            self.names.append((name_str, flags))

        # Parse Import Table
        self.imports = []
        import_cursor = self.import_offset
        for _ in range(self.import_count):
            class_pkg, import_cursor = NameRef.read(data, import_cursor, endian)
            class_name, import_cursor = NameRef.read(data, import_cursor, endian)
            (outer_idx,) = struct.unpack_from(fmt32, data, import_cursor)
            import_cursor += 4
            obj_name, import_cursor = NameRef.read(data, import_cursor, endian)
            self.imports.append((class_pkg, class_name, outer_idx, obj_name))

        # Parse Export Table
        self.exports: List[ManifestExportEntry] = []
        export_cursor = self.export_offset
        for _ in range(self.export_count):
            c_idx = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            s_idx = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            o_idx = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            obj_name, export_cursor = NameRef.read(data, export_cursor, endian)
            arch_idx = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            obj_flags = struct.unpack_from(fmtU64, data, export_cursor)[0]
            export_cursor += 8
            s_size = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            s_offset = struct.unpack_from(fmt32, data, export_cursor)[0]
            export_cursor += 4
            exp_flags = struct.unpack_from(fmtU32, data, export_cursor)[0]
            export_cursor += 4

            (gen_net_cnt,) = struct.unpack_from(fmt32, data, export_cursor)
            export_cursor += 4
            gen_net_counts = []
            for _ in range(gen_net_cnt):
                gen_net_counts.append(struct.unpack_from(fmt32, data, export_cursor)[0])
                export_cursor += 4

            pkg_guid = data[export_cursor : export_cursor + 16]
            export_cursor += 16
            pkg_flags = struct.unpack_from(fmtU32, data, export_cursor)[0]
            export_cursor += 4

            payload = data[s_offset : s_offset + s_size] if s_size > 0 else b""

            self.exports.append(
                ManifestExportEntry(
                    c_idx,
                    s_idx,
                    o_idx,
                    obj_name,
                    arch_idx,
                    obj_flags,
                    s_size,
                    s_offset,
                    exp_flags,
                    gen_net_counts,
                    pkg_guid,
                    pkg_flags,
                    payload,
                )
            )

        # Parse Dependency Table
        self.depends = []
        depends_cursor = self.depends_offset
        for _ in range(self.export_count):
            (dep_cnt,) = struct.unpack_from(fmt32, data, depends_cursor)
            depends_cursor += 4
            deps = []
            for _ in range(dep_cnt):
                deps.append(struct.unpack_from(fmt32, data, depends_cursor)[0])
                depends_cursor += 4
            self.depends.append(deps)

    def get_export_name(self, index: int) -> str:
        name_ref = self.exports[index].object_name
        return self.names[name_ref.index][0]

    def get_class_name(self, class_index: int) -> str:
        if class_index < 0:
            imp_idx = -class_index - 1
            if 0 <= imp_idx < len(self.imports):
                return self.names[self.imports[imp_idx][3].index][0]
        elif class_index > 0:
            exp_idx = class_index - 1
            if 0 <= exp_idx < len(self.exports):
                return self.get_export_name(exp_idx)
        return "Class"

    def set_export_payload(self, export_index: int, new_payload: bytes):
        """Set a new payload for an export, marking serial_size accordingly."""
        if not 0 <= export_index < len(self.exports):
            raise PackageRewriteError(f"Export index {export_index} out of range")
        entry = self.exports[export_index]
        entry.payload = new_payload
        entry.serial_size = len(new_payload)

    def rewrite_package(self, target_endian: str = "little") -> bytes:
        """Build a new package binary with relocated export payloads and recomputed serial offsets."""
        fmt32 = "<i" if target_endian == "little" else ">i"
        fmtU32 = "<I" if target_endian == "little" else ">I"
        fmtU64 = "<Q" if target_endian == "little" else ">Q"

        # Re-encode Name Table
        name_table_bytes = bytearray()
        for name_str, flags in self.names:
            name_table_bytes.extend(FString.pack(name_str, target_endian))
            name_table_bytes.extend(struct.pack(fmtU64, flags))

        # Re-encode Import Table
        import_table_bytes = bytearray()
        for class_pkg, class_name, outer_idx, obj_name in self.imports:
            import_table_bytes.extend(class_pkg.pack(target_endian))
            import_table_bytes.extend(class_name.pack(target_endian))
            import_table_bytes.extend(struct.pack(fmt32, outer_idx))
            import_table_bytes.extend(obj_name.pack(target_endian))

        # Re-encode Dependency Table
        depends_table_bytes = bytearray()
        for deps in self.depends:
            depends_table_bytes.extend(struct.pack(fmt32, len(deps)))
            for d in deps:
                depends_table_bytes.extend(struct.pack(fmt32, d))

        # Build Summary bytes up to Name table
        header_buf = bytearray()
        tag = PACKAGE_TAG_LE if target_endian == "little" else PACKAGE_TAG_BE
        header_buf.extend(struct.pack("<I", tag))
        header_buf.extend(struct.pack(fmtU32, self.packed_version))

        total_header_size_patch_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, 0))  # Placeholder for TotalHeaderSize

        header_buf.extend(FString.pack(self.folder_name, target_endian))
        header_buf.extend(struct.pack(fmtU32, self.package_flags))

        name_count_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, len(self.names)))
        name_offset_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, 0))  # Placeholder

        export_count_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, len(self.exports)))
        export_offset_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, 0))  # Placeholder

        import_count_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, len(self.imports)))
        import_offset_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, 0))  # Placeholder

        depends_offset_offset = len(header_buf)
        header_buf.extend(struct.pack(fmt32, 0))  # Placeholder

        header_buf.extend(struct.pack(fmt32, self.import_export_guids_offset))
        header_buf.extend(struct.pack(fmt32, self.import_guids_count))
        header_buf.extend(struct.pack(fmt32, self.export_guids_count))
        header_buf.extend(struct.pack(fmt32, self.thumbnail_table_offset))
        header_buf.extend(self.guid)

        header_buf.extend(struct.pack(fmt32, len(self.generations)))
        for exp_c, name_c, net_c in self.generations:
            header_buf.extend(struct.pack("<iii" if target_endian == "little" else ">iii", exp_c, name_c, net_c))

        header_buf.extend(struct.pack(fmtU32, self.saved_engine_version))
        header_buf.extend(struct.pack(fmtU32, self.cooked_content_version))
        header_buf.extend(struct.pack(fmtU32, self.compression_flags))

        header_buf.extend(struct.pack(fmt32, len(self.chunks)))
        for u_off, u_sz, c_off, c_sz in self.chunks:
            header_buf.extend(
                struct.pack("<iiii" if target_endian == "little" else ">iiii", u_off, u_sz, c_off, c_sz)
            )

        header_buf.extend(struct.pack(fmtU32, self.package_source))

        header_buf.extend(struct.pack(fmt32, len(self.additional_packages)))
        for pkg in self.additional_packages:
            header_buf.extend(FString.pack(pkg, target_endian))

        if len(self.texture_allocations_raw_bytes) > 0:
            header_buf.extend(struct.pack(fmt32, 1))
            header_buf.extend(self.texture_allocations_raw_bytes)
        else:
            header_buf.extend(struct.pack(fmt32, 0))

        # Calculate exact offsets
        name_offset = len(header_buf)
        import_offset = name_offset + len(name_table_bytes)

        # Calculate Export Table size
        export_table_bytes_len = 0
        for entry in self.exports:
            rec_len = 44 + 4 + len(entry.generation_net_object_counts) * 4 + 16 + 4
            export_table_bytes_len += rec_len

        export_offset = import_offset + len(import_table_bytes)
        depends_offset = export_offset + export_table_bytes_len
        total_header_size = depends_offset + len(depends_table_bytes)

        # Patch header table offsets
        struct.pack_into(fmt32, header_buf, total_header_size_patch_offset, total_header_size)
        struct.pack_into(fmt32, header_buf, name_offset_offset, name_offset)
        struct.pack_into(fmt32, header_buf, export_offset_offset, export_offset)
        struct.pack_into(fmt32, header_buf, import_offset_offset, import_offset)
        struct.pack_into(fmt32, header_buf, depends_offset_offset, depends_offset)

        # Recompute Export serial offsets and build Export Table
        current_serial_offset = total_header_size
        export_table_bytes = bytearray()
        export_payloads = bytearray()

        for entry in self.exports:
            entry.serial_offset = current_serial_offset
            entry.serial_size = len(entry.payload)

            export_table_bytes.extend(struct.pack(fmt32, entry.class_index))
            export_table_bytes.extend(struct.pack(fmt32, entry.super_index))
            export_table_bytes.extend(struct.pack(fmt32, entry.outer_index))
            export_table_bytes.extend(entry.object_name.pack(target_endian))
            export_table_bytes.extend(struct.pack(fmt32, entry.archetype_index))
            export_table_bytes.extend(struct.pack(fmtU64, entry.object_flags))
            export_table_bytes.extend(struct.pack(fmt32, entry.serial_size))
            export_table_bytes.extend(struct.pack(fmt32, entry.serial_offset))
            export_table_bytes.extend(struct.pack(fmtU32, entry.export_flags))

            export_table_bytes.extend(struct.pack(fmt32, len(entry.generation_net_object_counts)))
            for gnc in entry.generation_net_object_counts:
                export_table_bytes.extend(struct.pack(fmt32, gnc))

            export_table_bytes.extend(entry.package_guid)
            export_table_bytes.extend(struct.pack(fmtU32, entry.package_flags))

            export_payloads.extend(entry.payload)
            current_serial_offset += entry.serial_size

        # Assemble complete package
        result = bytearray()
        result.extend(header_buf)
        result.extend(name_table_bytes)
        result.extend(import_table_bytes)
        result.extend(export_table_bytes)
        result.extend(depends_table_bytes)
        result.extend(export_payloads)

        return bytes(result)


def convert_shader_cache_tail(payload: bytes, source_endian: str) -> bytes:
    """Convert a ShaderCache export native tail from Xbox 360 to PC (SP_PCD3D_SM3).

    Payload structure:
    - UObject prefix (12 bytes): 4 bytes NetIndex + 8 bytes FName(None)
    - Native tail (17 bytes):
        4 bytes priority (int32)
        1 byte  shader_platform (uint8)
        4 bytes compressed_map_count (int32)
        4 bytes shader_map_count (int32)
        4 bytes material_shader_map_count (int32)

    Fails closed if payload is invalid or if any shader count > 0.
    """
    if len(payload) < 29:
        raise ShaderCacheError(f"ShaderCache payload too short ({len(payload)} bytes, expected >= 29)")

    prefix = payload[:12]
    tail = payload[12:29]

    fmt_tail = f"{'<' if source_endian == 'little' else '>'}iBiii"
    priority, platform, c_cnt, s_cnt, m_cnt = struct.unpack_from(fmt_tail, tail, 0)

    if platform != SP_XBOXD3D and platform != SP_PCD3D_SM3:
        raise ShaderCacheError(f"Unexpected ShaderCache platform byte: {platform}")

    if c_cnt != 0 or s_cnt != 0 or m_cnt != 0:
        raise ShaderCacheError(
            f"Populated ShaderCache cannot be converted (counts: compressed={c_cnt}, "
            f"shaders={s_cnt}, materials={m_cnt}); must fail closed."
        )

    # Convert to target LE format
    new_tail = struct.pack("<iBiii", priority, SP_PCD3D_SM3, 0, 0, 0)
    return prefix + new_tail + payload[29:]


def convert_fvert_bulk_array(
    payload: bytes,
    source_endian: str,
    offset_in_payload: int = 12,
    widen_populated: bool = True,
) -> bytes:
    """Convert an FVert bulk array header from 16 to 24 bytes per element.

    Header structure at offset_in_payload:
    - ElementSize (4 bytes int32)
    - ElementCount (4 bytes int32)

    For empty arrays (ElementCount == 0): retargets ElementSize 16 -> 24.
    For populated arrays (ElementCount > 0):
      - If widen_populated is True: widens each 16-byte FVert element to 24 bytes
        (appending 8 zero bytes for BackfaceShadowTexCoord), growing payload.
      - If widen_populated is False: raises FVertError (fails closed).
    """
    if len(payload) < offset_in_payload + 8:
        raise FVertError(
            f"FVert payload too short at offset {offset_in_payload} ({len(payload)} bytes)"
        )

    fmt_ii = "<ii" if source_endian == "little" else ">ii"
    elem_size, elem_cnt = struct.unpack_from(fmt_ii, payload, offset_in_payload)

    if elem_size != 16 and elem_size != 24:
        raise FVertError(
            f"Invalid FVert ElementSize {elem_size} (expected 16 or 24)"
        )

    if elem_cnt < 0:
        raise FVertError(f"Invalid negative FVert ElementCount {elem_cnt}")

    expected_data_len = elem_cnt * elem_size
    array_data_offset = offset_in_payload + 8
    if len(payload) < array_data_offset + expected_data_len:
        raise FVertError(
            f"FVert payload truncated: expected {expected_data_len} bytes data, "
            f"got {len(payload) - array_data_offset}"
        )

    prefix = payload[:offset_in_payload]
    suffix = payload[array_data_offset + expected_data_len :]

    if elem_cnt == 0:
        # Empty array: just retarget ElementSize 16 -> 24
        new_header = struct.pack("<ii", 24, 0)
        return prefix + new_header + suffix

    # Populated array
    if not widen_populated:
        raise FVertError(
            f"Populated FVert array ({elem_cnt} elements) retargeting rejected; must fail closed."
        )

    # Widening populated 16-byte elements to 24-byte elements
    raw_data = payload[array_data_offset : array_data_offset + expected_data_len]
    new_data = bytearray()
    for i in range(elem_cnt):
        elem = raw_data[i * elem_size : (i + 1) * elem_size]
        new_data.extend(elem)
        # Pad 8 bytes for BackfaceShadowTexCoord on PC
        new_data.extend(b"\x00" * 8)

    new_header = struct.pack("<ii", 24, elem_cnt)
    return prefix + new_header + bytes(new_data) + suffix
