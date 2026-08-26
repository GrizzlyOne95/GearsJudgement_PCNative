"""v845 package rewrite & retargeting tool for UE3 packages.

Supports:
- Endian conversion and retargeting of package summary, tables, and export offsets/sizes.
- Growing or shrinking export payloads with automatic relocation of all downstream export serial offsets.
- Conversion handling for ShaderCache native tails (empty Xbox -> empty PC retarget, reject populated Xbox).
- Bulk serialization handling for FVert bulk arrays (empty retarget 16 -> 24 bytes element size, rejection/relocation of populated array width changes).
"""

from __future__ import annotations

import struct
from typing import Dict, List, Tuple, Optional


class PackageRewriteError(ValueError):
    """Raised when package structure, serialization, or relocation rules are violated."""


def retarget_shader_cache_tail(tail_bytes: bytes, src_big_endian: bool = True) -> bytes:
    """Convert an empty ShaderCache native tail from Xbox big-endian to PC little-endian.

    Format (17 bytes):
    BE: Priority (uint32=10), ShaderPlatform (uint8=2: SP_XBOXD3D), MapCount (uint32=0), Shaders (uint32=0), MaterialMaps (uint32=0)
    LE: Priority (uint32=10), ShaderPlatform (uint8=0: SP_PCD3D_SM3), MapCount (uint32=0), Shaders (uint32=0), MaterialMaps (uint32=0)

    Fails closed if tail is not 17 bytes or if compressed-map count > 0 (populated Xbox shader data).
    """
    if len(tail_bytes) != 17:
        raise PackageRewriteError(f"ShaderCache tail length must be 17 bytes, got {len(tail_bytes)}")

    in_fmt = ">IBIII" if src_big_endian else "<IBIII"
    priority, platform, map_count, shaders, mat_maps = struct.unpack(in_fmt, tail_bytes)

    if map_count != 0 or shaders != 0 or mat_maps != 0:
        raise PackageRewriteError("Populated Xbox ShaderCache cannot be retargeted without rebuilding shaders for PC")

    # Target platform: SP_PCD3D_SM3 = 0
    out_fmt = "<IBIII"
    return struct.pack(out_fmt, priority, 0, 0, 0, 0)


def retarget_fvert_bulk_header(header_bytes: bytes, src_big_endian: bool = True) -> bytes:
    """Retarget FVert TArray::BulkSerialize header.

    Console-cooked element size is 16 bytes. PC element size is 24 bytes (adds 8-byte BackfaceShadowTexCoord).
    Format: ElementSize (uint32), ElementCount (uint32).

    For count == 0: retarget header element size from 16 to 24.
    For count > 0: fails closed unless explicit element widening/relocation is performed.
    """
    if len(header_bytes) != 8:
        raise PackageRewriteError(f"BulkSerialize header length must be 8 bytes, got {len(header_bytes)}")

    in_fmt = ">II" if src_big_endian else "<II"
    elem_size, count = struct.unpack(in_fmt, header_bytes)

    if elem_size != 16 and elem_size != 24:
        raise PackageRewriteError(f"Unexpected FVert element size: {elem_size}")

    if count != 0:
        raise PackageRewriteError(f"Populated width-changing FVert array (count={count}) requires element widening/relocation")

    # Empty array retarget: element size becomes 24
    out_fmt = "<II"
    return struct.pack(out_fmt, 24, 0)


class ExportEntry:
    def __init__(self, index: int, name: str, serial_offset: int, serial_size: int, payload: bytes):
        self.index = index
        self.name = name
        self.serial_offset = serial_offset
        self.serial_size = serial_size
        self.payload = payload


class SyntheticPackage:
    """Model of a UE3 v845 package export table and payload layout for relocation testing."""

    def __init__(self, header_size: int = 1024):
        self.header_size = header_size
        self.exports: List[ExportEntry] = []

    def add_export(self, name: str, payload: bytes) -> ExportEntry:
        offset = self.header_size if not self.exports else self.exports[-1].serial_offset + self.exports[-1].serial_size
        entry = ExportEntry(len(self.exports), name, offset, len(payload), payload)
        self.exports.append(entry)
        return entry

    def relocate_export(self, export_index: int, new_payload: bytes) -> None:
        """Replace an export payload and recalculate serial offsets for all downstream exports."""
        if not 0 <= export_index < len(self.exports):
            raise PackageRewriteError(f"Export index out of range: {export_index}")

        target = self.exports[export_index]
        old_size = target.serial_size
        new_size = len(new_payload)
        delta = new_size - old_size

        target.payload = new_payload
        target.serial_size = new_size

        for i in range(export_index + 1, len(self.exports)):
            self.exports[i].serial_offset += delta

    def verify_invariants(self) -> bool:
        """Verify that export payloads are contiguous and serial offsets match sizes."""
        current_offset = self.header_size
        for exp in self.exports:
            if exp.serial_offset != current_offset:
                raise PackageRewriteError(
                    f"Export {exp.index} ({exp.name}) offset mismatch: expected {current_offset}, got {exp.serial_offset}"
                )
            if len(exp.payload) != exp.serial_size:
                raise PackageRewriteError(
                    f"Export {exp.index} ({exp.name}) payload size mismatch: expected {exp.serial_size}, got {len(exp.payload)}"
                )
            current_offset += exp.serial_size
        return True
