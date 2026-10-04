"""Extract the ini/int files held in an Xbox 360 UE3 Coalesced_*.bin.

Layout (Judgment v845): big-endian int32 counts; FStrings are int32 length followed by
either ANSI bytes (positive length, NUL included) or UTF-16LE code units (negative length,
NUL included).  File -> sections -> (key, value) pairs, duplicate keys preserved in order.

Usage: python coalesced_extract.py <Coalesced_INT.bin> <out_dir>
"""
import struct
import sys
from pathlib import Path, PureWindowsPath


class Reader:
    def __init__(self, blob):
        self.blob = blob
        self.off = 0

    def i32(self):
        value = struct.unpack_from(">i", self.blob, self.off)[0]
        self.off += 4
        return value

    def fstring(self):
        length = self.i32()
        if length == 0:
            return ""
        if length > 0:
            raw = self.blob[self.off:self.off + length]
            self.off += length
            return raw[:-1].decode("latin-1")
        count = -length
        raw = self.blob[self.off:self.off + count * 2]
        self.off += count * 2
        return raw[:-2].decode("utf-16-le")


def parse(blob):
    """Return [(file_name, [(section_name, [(key, value), ...]), ...]), ...]."""
    reader = Reader(blob)
    files = []
    for _ in range(reader.i32()):
        name = reader.fstring()
        sections = []
        for _ in range(reader.i32()):
            section = reader.fstring()
            pairs = [(reader.fstring(), reader.fstring()) for _ in range(reader.i32())]
            sections.append((section, pairs))
        files.append((name, sections))
    if reader.off != len(blob):
        raise ValueError(f"trailing data: parsed {reader.off} of {len(blob)} bytes")
    return files


def render(sections):
    lines = []
    for section, pairs in sections:
        lines.append(f"[{section}]")
        lines.extend(f"{key}={value}" for key, value in pairs)
        lines.append("")
    return "\n".join(lines)


def safe_relative(name):
    """Drop drive/.. components so every file lands inside the output directory."""
    parts = [p for p in PureWindowsPath(name).parts if p not in ("..", ".", "\\", "/") and ":" not in p]
    return Path(*parts)


def main(src, out_dir):
    files = parse(Path(src).read_bytes())
    out_root = Path(out_dir)
    for name, sections in files:
        target = out_root / safe_relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(sections), encoding="utf-8")
    pairs = sum(len(p) for _, sections in files for _, p in sections)
    print(f"files={len(files)} sections={sum(len(s) for _, s in files)} pairs={pairs} -> {out_root}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
