"""Append recovered PC mip chains to a converted Judgment asset package.

The C++ probe handles Xbox cache decompression, endian conversion and detiling.
This writer consumes its standalone v828 fixtures, retaining the v845 package's
original tagged settings and every object/name index. Only selected texture
SerialSize/SerialOffset fields change in the existing file; other payload and
bulk offsets remain fixed. LightMapTexture2D/ShadowMapTexture2D exports are
recovered from the same plain-Texture2D fixtures and keep their own trailer
bytes. Retail inputs and outputs belong outside Git.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct


FORMATS = {
    "PF_DXT1": (4, 4, 8), "PF_DXT3": (4, 4, 16),
    "PF_DXT5": (4, 4, 16), "PF_BC5": (4, 4, 16),
    "PF_G8": (1, 1, 1), "PF_A8R8G8B8": (1, 1, 4), "PF_V8U8": (1, 1, 2),
}
REMOVE = {"TextureFileCacheName", "FirstResourceMemMip"}
REQUIRED = {"SizeX", "SizeY", "OriginalSizeX", "OriginalSizeY", "Format", "MipTailBaseIdx"}
ORIGINAL_SIZE = {"OriginalSizeX", "OriginalSizeY"}
# Texture classes and the exact bytes each serializes after the cached-PVRTC count: a
# LightMapTexture2D's DWORD LightmapFlags; ShadowMapTexture2D adds nothing (measured, v845).
TEXTURE_CLASSES = {"Texture2D": 0, "LightMapTexture2D": 4, "ShadowMapTexture2D": 0}


def i32(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated integer")
    return struct.unpack_from("<i", data, offset)[0]


@dataclass
class Export:
    index: int
    table_offset: int
    name: str
    name_pair: tuple
    class_index: int
    flags: int
    size: int
    offset: int


class Package:
    def __init__(self, data):
        self.data = data
        if data[:4] != b"\xc1\x83\x2a\x9e":
            raise ValueError("requires a little-endian package")
        self.version = i32(data, 4)
        if self.version not in (828, 845):
            raise ValueError("requires package version 828 or 845")
        header = i32(data, 8)
        folder = i32(data, 12)
        fields = 16 + (folder if folder >= 0 else -folder * 2)
        if folder == 0 or fields + 48 > header or header > len(data):
            raise ValueError("invalid package header")
        (_, nc, no, ec, eo, ic, io, _, _, _, _, _) = struct.unpack_from("<12i", data, fields)
        if min(nc, ec, ic) < 0 or not all(fields + 48 <= p <= header for p in (no, eo, io)):
            raise ValueError("invalid package tables")
        # Summary after GUID and generation records: engine/content versions,
        # compression flags and compressed chunk count.
        generations = i32(data, fields + 64)
        after_generations = fields + 68 + generations * 12
        if generations < 0 or after_generations + 16 > min(no, eo, io):
            raise ValueError("invalid generation table")
        if i32(data, after_generations + 8) or i32(data, after_generations + 12):
            raise ValueError("compressed package must be decompressed first")
        self.names = []
        pos = no
        for _ in range(nc):
            length = i32(data, pos)
            pos += 4
            size = length if length > 0 else -length * 2
            if not length or pos + size + 8 > header:
                raise ValueError("invalid name table")
            raw = data[pos:pos + size]
            if length > 0:
                if raw[-1:] != b"\0":
                    raise ValueError("unterminated package name")
                name = raw[:-1].decode("latin-1")
            else:
                if raw[-2:] != b"\0\0":
                    raise ValueError("unterminated wide package name")
                name = raw[:-2].decode("utf-16le")
            self.names.append(name)
            pos += size + 8
        self.import_names = []
        if io + ic * 28 > header:
            raise ValueError("invalid import table")
        for index in range(ic):
            self.import_names.append(self.name(io + index * 28 + 20))
        self.exports = []
        pos = eo
        for index in range(ec):
            if pos + 68 > header:
                raise ValueError("truncated export table")
            cls, size, offset, gens = (i32(data, pos + p) for p in (0, 32, 36, 44))
            if gens < 0 or pos + 68 + gens * 4 > header or size < 0 or offset < 0 or offset + size > len(data):
                raise ValueError("invalid export span")
            if size and offset < header:
                raise ValueError("export overlaps package header")
            self.exports.append(Export(index, pos, self.name(pos + 12),
                                       struct.unpack_from("<2i", data, pos + 12), cls,
                                       struct.unpack_from("<Q", data, pos + 24)[0], size, offset))
            pos += 68 + gens * 4

    def name(self, offset):
        index, number = i32(self.data, offset), i32(self.data, offset + 4)
        if not 0 <= index < len(self.names) or number < 0:
            raise ValueError("invalid FName")
        return self.names[index] + ("_" + str(number - 1) if number else "")

    def class_name(self, entry):
        ref = entry.class_index
        if ref == 0:
            return "Class"  # UE3's metaclass has no serialized class reference.
        if ref < 0 and -ref <= len(self.import_names):
            return self.import_names[-ref - 1]
        if 0 < ref <= len(self.exports):
            return self.exports[ref - 1].name
        raise ValueError("invalid class reference")


@dataclass
class Tag:
    name: str
    kind: str
    array_index: int
    raw: bytes
    value_offset: int
    value: bytes


@dataclass
class Texture:
    net_index: bytes
    tags: list
    terminator: bytes
    source_art: tuple
    mips: list
    guid: bytes
    trailer: bytes
    cls: str


def texture(package, entry):
    """Parse a Texture2D, LightMapTexture2D or ShadowMapTexture2D export; `trailer` is the class's tail."""
    cls = package.class_name(entry)
    if cls not in TEXTURE_CLASSES or entry.flags & (0x0200000000000000 | 0x200):
        raise ValueError("requires a plain Texture2D, LightMapTexture2D or ShadowMapTexture2D export")
    data, start, end = package.data, entry.offset, entry.offset + entry.size
    pos, tags, seen = start + 4, [], set()
    while pos + 8 <= end:
        name = package.name(pos)
        if name == "None":
            terminator = data[pos:pos + 8]
            pos += 8
            break
        if pos + 24 > end:
            raise ValueError("truncated property tag")
        kind, size, array_index = package.name(pos + 8), i32(data, pos + 16), i32(data, pos + 20)
        if size < 0 or array_index < 0 or not kind.endswith("Property") or (name, array_index) in seen:
            raise ValueError("invalid or duplicate property tag")
        seen.add((name, array_index))
        value_at = pos + 24
        if kind in ("ByteProperty", "StructProperty"):
            if value_at + 8 > end:
                raise ValueError("truncated property type")
            package.name(value_at)
            value_at += 8
        elif kind == "BoolProperty":
            if size or value_at >= end or data[value_at] > 1:
                raise ValueError("invalid boolean property")
            value_at += 1
        if value_at + size > end:
            raise ValueError("property extends beyond export")
        tags.append(Tag(name, kind, array_index, data[pos:value_at + size], value_at - pos,
                        data[value_at:value_at + size]))
        pos = value_at + size
    else:
        raise ValueError("missing property terminator")

    def bulk():
        nonlocal pos
        if pos + 16 > end:
            raise ValueError("truncated bulk header")
        flags, count, size, offset = struct.unpack_from("<4i", data, pos)
        pos += 16
        sentinel = (flags, count, size, offset) == (0x21, 0, -1, -1)
        if not sentinel and (count < 0 or size < 0 or offset < 0):
            raise ValueError("invalid bulk header")
        pixels = None
        if count and not flags & 1:
            if offset != pos or pos + size > end:
                raise ValueError("inline bulk offset is not its physical payload")
            pixels = data[pos:pos + size]
            pos += size
        return flags, count, size, offset, pixels

    art = bulk()
    count = i32(data, pos)
    pos += 4
    if not 0 < count <= 32:
        raise ValueError("invalid mip count")
    mips = []
    for _ in range(count):
        stored = bulk()
        if pos + 8 > end:
            raise ValueError("truncated mip dimensions")
        width, height = struct.unpack_from("<2i", data, pos)
        pos += 8
        if width <= 0 or height <= 0:
            raise ValueError("invalid mip dimensions")
        mips.append((width, height, stored))
    if pos + 20 > end or i32(data, pos + 16):
        raise ValueError(f"requires an exact {cls} tail with no cached PVRTC mips")
    trailer = data[pos + 20:end]
    if len(trailer) != TEXTURE_CLASSES[cls]:
        raise ValueError(f"requires an exact {TEXTURE_CLASSES[cls]}-byte {cls} trailer, found {len(trailer)}")
    return Texture(data[start:start + 4], tags, terminator, art, mips, data[pos:pos + 16], trailer, cls)


def properties(package, parsed, require_tail=True, require_original=True):
    """Validate the texture settings; baked light/shadow maps omit the zero-default OriginalSizeX/Y."""
    result = {tag.name: tag for tag in parsed.tags if tag.array_index == 0}
    required = REQUIRED if require_tail else REQUIRED - {"MipTailBaseIdx"}
    if not require_original:
        required = required - ORIGINAL_SIZE
    required = required | (REQUIRED & result.keys())
    if not required <= result.keys():
        raise ValueError("missing required Texture2D settings")
    for name in required - {"Format"}:
        if result[name].kind != "IntProperty" or len(result[name].value) != 4:
            raise ValueError("invalid integer texture setting")
    fmt = result["Format"]
    if fmt.kind != "ByteProperty" or len(fmt.value) != 8:
        raise ValueError("invalid pixel format setting")
    index, number = struct.unpack("<2i", fmt.value)
    if not 0 <= index < len(package.names) or number:
        raise ValueError("invalid pixel format name")
    format_name = package.names[index]
    if format_name not in FORMATS:
        raise ValueError("unsupported pixel format: " + format_name)
    return result, format_name


def recover(original, entry, fixture, offset):
    """Build one texture's replacement payload for placement at `offset`."""
    source = texture(original, entry)
    plain = source.cls == "Texture2D"
    old_props, fmt = properties(original, source, require_tail=False, require_original=plain)
    pc = Package(fixture)
    # The fixture is always a plain Texture2D (so it has no trailer); the source's trailer is kept below.
    if (pc.version != 828 or len(pc.exports) != 1 or pc.exports[0].name != entry.name
            or pc.class_name(pc.exports[0]) != "Texture2D"):
        raise ValueError("fixture must be a v828 package containing the matching texture")
    recovered = texture(pc, pc.exports[0])
    new_props, new_fmt = properties(pc, recovered, require_original=plain)
    if new_fmt != fmt or recovered.guid != source.guid:
        raise ValueError("fixture pixel format or texture GUID differs from source")
    if source.source_art[1:3] != (0, 0) or recovered.source_art[:3] != (0, 0, 0):
        raise ValueError("requires empty SourceArt")
    for name in sorted(ORIGINAL_SIZE):
        # Absent in both (baked light/shadow maps) is a match; presence and value must agree.
        if (old_props[name].value if name in old_props else None) != (
                new_props[name].value if name in new_props else None):
            raise ValueError("fixture authored dimensions differ")
    width, height = (i32(new_props[name].value, 0) for name in ("SizeX", "SizeY"))
    old_sizes = [(w, h) for w, h, _ in source.mips]
    sizes = [(w, h) for w, h, _ in recovered.mips]
    # A stripped high-resolution prefix is valid; a different geometry is not.
    if len(sizes) > len(old_sizes) or sizes != old_sizes[len(old_sizes) - len(sizes):]:
        raise ValueError("fixture mip geometry differs from resident source chain")
    omitted = len(old_sizes) - len(sizes)
    if any(m[2][:4] != (0x21, 0, -1, -1) for m in source.mips[:omitted]):
        raise ValueError("fixture omits a resident source mip")
    if width <= 0 or height <= 0 or width & (width - 1) or height & (height - 1):
        raise ValueError("requires power-of-two texture dimensions")
    single_mip = len(source.mips) == len(sizes) == 1
    if sizes[0] != (width, height) or (not single_mip and len(sizes) != max(width, height).bit_length()):
        raise ValueError("fixture must contain a complete PC mip chain")
    if i32(new_props["MipTailBaseIdx"].value, 0) != len(sizes) - 1:
        raise ValueError("fixture still uses a packed mip tail")
    bx, by, stride = FORMATS[fmt]
    for w, h, stored in recovered.mips:
        required_size = ((w + bx - 1) // bx) * ((h + by - 1) // by) * stride
        if stored[:3] != (0, required_size, required_size) or stored[4] is None:
            raise ValueError("fixture mip is not exact uncompressed inline PC data")
    payload = bytearray(source.net_index)
    preserved = []
    for tag in source.tags:
        if tag.name in REMOVE:
            continue
        raw = bytearray(tag.raw)
        if tag.name in ("SizeX", "SizeY", "MipTailBaseIdx") and tag.array_index == 0:
            raw[tag.value_offset:tag.value_offset + 4] = new_props[tag.name].value
        else:
            preserved.append((tag.name, tag.array_index))
        payload += raw
    payload += source.terminator

    def inline(pixels):
        absolute = offset + len(payload) + 16
        if absolute + len(pixels) >= 0x80000000:
            raise ValueError("appended bulk exceeds signed package offsets")
        payload.extend(struct.pack("<4i", 0, len(pixels), len(pixels), absolute))
        payload.extend(pixels)

    inline(b"")
    payload += struct.pack("<i", len(recovered.mips))
    for w, h, stored in recovered.mips:
        inline(stored[4])
        payload += struct.pack("<2i", w, h)
    payload += source.guid + struct.pack("<i", 0) + source.trailer
    return payload, {"export_index": entry.index, "name": entry.name, "class": source.cls,
                     "trailer_bytes": len(source.trailer), "format": fmt,
                     "old_offset": entry.offset, "old_size": entry.size,
                     "new_offset": offset, "new_size": len(payload),
                     "mips": len(recovered.mips), "base_dimensions": [width, height],
                     "linear_bytes": sum(len(m[2][4]) for m in recovered.mips),
                     "preserved_properties": preserved,
                     "fixture_sha256": hashlib.sha256(fixture).hexdigest()}


def replace(package_bytes, fixtures, rejected=None):
    """Append recovered mips for the fixtures' textures.

    `fixtures` maps every plain Texture2D's unique object name to its fixture.
    Streamed maps repeat object names across groups, so a mapping keyed by
    export index is accepted instead and may cover a subset; only that mode
    also selects LightMapTexture2D and ShadowMapTexture2D exports, whose own
    trailer bytes are kept. With a `rejected` list, a texture whose fixture
    fails validation is recorded there and left exactly as converted rather
    than aborting the package.
    """
    original = Package(package_bytes)
    if original.version != 845:
        raise ValueError("destination must remain Judgment v845")
    textures = [e for e in original.exports if original.class_name(e) == "Texture2D"]
    if fixtures and all(isinstance(key, int) for key in fixtures):
        textures = [e for e in original.exports if original.class_name(e) in TEXTURE_CLASSES]
        if not set(fixtures) <= {e.index for e in textures}:
            raise ValueError("fixture index does not name a Texture2D, LightMapTexture2D or "
                             "ShadowMapTexture2D export")
        textures = [e for e in textures if e.index in fixtures]
        selected = fixtures
    else:
        if len({e.name for e in textures}) != len(textures) or set(fixtures) != {e.name for e in textures}:
            raise ValueError("fixtures must match every texture exactly once")
        selected = {e.index: fixtures[e.name] for e in textures}
    if not textures:
        raise ValueError("no texture exports")
    output, records = bytearray(package_bytes), []
    for entry in textures:
        offset = len(output)
        try:
            payload, record = recover(original, entry, selected[entry.index], offset)
        except ValueError as error:
            if rejected is None:
                raise
            rejected.append({"export_index": entry.index, "name": entry.name,
                             "class": original.class_name(entry), "stage": "writer", "reason": str(error)})
            continue
        output += payload
        struct.pack_into("<2i", output, entry.table_offset + 32, len(payload), offset)
        records.append(record)
    # Re-read final absolute bulk offsets, with all original indices still valid.
    final = Package(output)
    for record in records:
        index = record["export_index"]
        after, before = texture(final, final.exports[index]), texture(original, original.exports[index])
        if (after.cls, after.trailer) != (before.cls, before.trailer):
            raise ValueError("texture class or trailer changed while recovering export %d" % index)
    report = {"input_sha256": hashlib.sha256(package_bytes).hexdigest(),
              "output_sha256": hashlib.sha256(output).hexdigest(),
              "original_bytes": len(package_bytes), "output_bytes": len(output),
              "exports": len(original.exports), "textures_recovered": len(records),
              "recovered_by_class": {c: sum(r["class"] == c for r in records) for c in TEXTURE_CLASSES},
              "textures": records}
    return bytes(output), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("fixtures", type=Path, help="directory of <texture-name>.upk fixtures")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    receipt = args.output.with_suffix(".textures.json")
    if args.output.exists() or receipt.exists():
        parser.error("refusing to overwrite retained package or receipt")
    package = args.package.read_bytes()
    parsed = Package(package)
    fixtures = {e.name: (args.fixtures / (e.name + ".upk")).read_bytes()
                for e in parsed.exports if parsed.class_name(e) == "Texture2D"}
    output, report = replace(package, fixtures)
    args.output.write_bytes(output)
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
