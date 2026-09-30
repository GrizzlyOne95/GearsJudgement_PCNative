"""Read native public symbols from local MSF 7 PDBs, including large block maps.

Read-only format inspection; neither source/debug files nor extracted reports
belong in the public repository. Format references are documented in
AI-NATIVE-CHECKPOINT.md. No DIA, LLVM, XDK or third-party parser is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import uuid
from pathlib import Path


class SymbolFormatError(ValueError):
    pass


def _unpack(fmt, blob, offset):
    if offset < 0 or offset + struct.calcsize(fmt) > len(blob):
        raise SymbolFormatError("truncated structure")
    return struct.unpack_from(fmt, blob, offset)


class MsfFile:
    MAGIC = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0"

    def __init__(self, blob: bytes):
        if blob[:32] != self.MAGIC:
            raise SymbolFormatError("expected MSF 7 magic")
        self.blob = blob
        bs, _, blocks, size, reserved, block_map = _unpack("<6I", blob, 32)
        if bs not in (512, 1024, 2048, 4096) or blocks * bs != len(blob):
            raise SymbolFormatError("invalid block size or file length")
        if reserved or size < 4 or size > len(blob):
            raise SymbolFormatError("invalid directory size/header")
        self.block_size = bs
        self.block_count = blocks
        count = (size + bs - 1) // bs
        # The local Xbox PDB has a contiguous, three-page directory block map.
        # Reading only one block silently truncates it (638 indices at 1024 B).
        pages = _unpack(f"<{count}I", blob, block_map * bs)
        directory = self._pages(pages, size)
        stream_count, = _unpack("<I", directory, 0)
        if stream_count > (len(directory) - 4) // 4:
            raise SymbolFormatError("invalid stream count")
        self.sizes = _unpack(f"<{stream_count}I", directory, 4)
        self.stream_pages = []
        offset = 4 + 4 * stream_count
        for stream_size in self.sizes:
            if stream_size != 0xFFFFFFFF and stream_size > len(blob):
                raise SymbolFormatError("stream larger than file")
            n = 0 if stream_size == 0xFFFFFFFF else (stream_size + bs - 1) // bs
            page_list = _unpack(f"<{n}I", directory, offset)
            self._validate_pages(page_list)
            self.stream_pages.append(page_list)
            offset += 4 * n
        if offset != len(directory):
            raise SymbolFormatError("unconsumed directory bytes")

    def _validate_pages(self, pages):
        if any(p >= self.block_count for p in pages):
            raise SymbolFormatError("block index outside file")
        if len(set(pages)) != len(pages):
            raise SymbolFormatError("duplicate blocks in stream/directory")

    def _pages(self, pages, size):
        self._validate_pages(pages)
        bs = self.block_size
        return b"".join(self.blob[p * bs:(p + 1) * bs] for p in pages)[:size]

    def stream(self, index):
        if not 0 <= index < len(self.sizes) or self.sizes[index] == 0xFFFFFFFF:
            raise SymbolFormatError("missing stream")
        return self._pages(self.stream_pages[index], self.sizes[index])


def read_public_records(blob, section_count):
    """Decode S_PUB32 records, validating even records outside the selection."""
    result = []
    offset = 0
    while offset < len(blob):
        length, kind = _unpack("<HH", blob, offset)
        end = offset + length + 2
        if length < 2 or end > len(blob):
            raise SymbolFormatError("invalid symbol record length")
        if kind == 0x110E:  # S_PUB32: flags, offset, segment, zero-terminated name.
            if length < 13:
                raise SymbolFormatError("truncated public record")
            flags, address, segment = _unpack("<IIH", blob, offset + 4)
            start = offset + 14
            nul = blob.find(b"\0", start, end)
            if nul < 0 or start == nul:
                raise SymbolFormatError("missing public symbol name/terminator")
            if not 1 <= segment <= section_count:
                raise SymbolFormatError("public symbol has invalid section")
            try:
                name = blob[start:nul].decode("utf8")
            except UnicodeDecodeError as exc:
                raise SymbolFormatError("invalid symbol name encoding") from exc
            result.append({"name": name, "offset": address,
                           "section": segment, "flags": flags})
        offset = end
    return result


def native_symbols(blob, pattern=".*"):
    msf = MsfFile(blob)
    info = msf.stream(1)
    info_version, _, info_age = _unpack("<III", info, 0)
    if len(info) < 28 or info_version != 20000404:
        raise SymbolFormatError("unsupported PDB identity header")
    guid = str(uuid.UUID(bytes_le=info[12:28]))
    dbi = msf.stream(3)
    signature, version, age = _unpack("<iII", dbi, 0)
    if signature != -1 or version != 19990903 or len(dbi) < 64:
        raise SymbolFormatError("unsupported DBI header")
    if age != info_age:
        raise SymbolFormatError("PDB/DBI ages differ")
    symbol_stream, = _unpack("<H", dbi, 20)
    sizes = [_unpack("<i", dbi, off)[0] for off in (24, 28, 32, 36, 40, 52)]
    optional_size, = _unpack("<i", dbi, 48)
    if any(s < 0 for s in sizes) or optional_size < 12 or optional_size % 2:
        raise SymbolFormatError("invalid DBI substream sizes")
    optional = 64 + sum(sizes)
    if optional + optional_size != len(dbi):
        raise SymbolFormatError("DBI substreams do not frame the stream")
    section_stream, = _unpack("<H", dbi, optional + 10)
    section_blob = msf.stream(section_stream)
    if not section_blob or len(section_blob) % 40:
        raise SymbolFormatError("invalid PE section header stream")
    sections = []
    for offset in range(0, len(section_blob), 40):
        try:
            name = section_blob[offset:offset + 8].rstrip(b"\0").decode("ascii")
        except UnicodeDecodeError as exc:
            raise SymbolFormatError("invalid section name encoding") from exc
        virtual_size, rva, raw_size, raw_offset = _unpack("<4I", section_blob, offset + 8)
        sections.append({"name": name, "rva": rva, "virtual_size": virtual_size,
                         "raw_size": raw_size, "raw_offset": raw_offset})
    matcher = re.compile(pattern)
    symbols = read_public_records(msf.stream(symbol_stream), len(sections))
    selected = []
    for symbol in symbols:
        if matcher.search(symbol["name"]):
            section = sections[symbol["section"] - 1]
            if symbol["offset"] >= max(section["virtual_size"], section["raw_size"]):
                raise SymbolFormatError("selected symbol outside section")
            selected.append({**symbol, "rva": section["rva"] + symbol["offset"]})
    return {"format": "MSF7/S_PUB32", "sha256": hashlib.sha256(blob).hexdigest(),
            "block_size": msf.block_size, "dbi_age": age,
            "pdb_guid": guid,
            "total_publics": len(symbols), "sections": sections,
            "symbols": sorted(selected, key=lambda s: (s["rva"], s["name"]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdb", type=Path)
    parser.add_argument("--match", default=".*", help="regular expression for symbol names")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = native_symbols(args.pdb.read_bytes(), args.match)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"{len(report['symbols'])} selected / {report['total_publics']} public symbols")


if __name__ == "__main__":
    main()
