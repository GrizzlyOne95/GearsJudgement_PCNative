"""Offset domain annotations for UE3 package conversion.

Three domains are conceptually different and must not be handled by a generic
\"swap integers\" mindset.  Even though they are all 32-bit ints on disk, they
have different relocation semantics:

  PACKAGE_ABSOLUTE - file-absolute byte offsets (BulkDataOffsetInFile,
                     Export SerialOffset, summary table offsets NameOffset etc.)
                     Must be translated via RelocationMap when package layout changes.

  EXPORT_RELATIVE  - offsets/counts internal to a serialized UObject payload
                     (TArray counts, intra-export offsets).  Never relocated
                     against file.

  LOGICAL/INDEXED  - name/object indices, FString lengths, array counts that are
                     table indices, not byte offsets.

This module provides typed helpers and NewType aliases so the converter can
distinguish them statically and the relocation layer knows what to patch.
"""
from typing import NewType
import struct

PackageAbsolute = NewType("PackageAbsolute", int)
ExportRelative = NewType("ExportRelative", int)
LogicalIndex = NewType("LogicalIndex", int)
Count = NewType("Count", int)

def read_package_absolute(buf: bytes, off: int) -> PackageAbsolute:
    """Read a PACKAGE_ABSOLUTE file offset (SerialOffset, BulkDataOffsetInFile, table offsets)."""
    return PackageAbsolute(struct.unpack_from("<i", buf, off)[0])

def write_package_absolute(buf: bytearray, off: int, val: PackageAbsolute) -> None:
    struct.pack_into("<i", buf, off, int(val))

def read_export_relative(buf: bytes, off: int) -> ExportRelative:
    """Read an EXPORT_RELATIVE intra-payload offset/count."""
    return ExportRelative(struct.unpack_from("<i", buf, off)[0])

def read_count(buf: bytes, off: int) -> Count:
    """Read a LOGICAL count (TArray/TMap element count)."""
    return Count(struct.unpack_from("<i", buf, off)[0])

def read_object_index(buf: bytes, off: int) -> LogicalIndex:
    """Read a LOGICAL object reference (export>0 / import<0 / null==0)."""
    return LogicalIndex(struct.unpack_from("<i", buf, off)[0])

def read_name_index(buf: bytes, off: int) -> LogicalIndex:
    """Read a LOGICAL FName table index."""
    return LogicalIndex(struct.unpack_from("<i", buf, off)[0])

# BE variants for still-BE payloads (e.g., CoverSlot binary after be2le)
def read_package_absolute_be(buf: bytes, off: int) -> PackageAbsolute:
    return PackageAbsolute(struct.unpack_from(">i", buf, off)[0])

def read_count_be(buf: bytes, off: int) -> Count:
    return Count(struct.unpack_from(">i", buf, off)[0])
