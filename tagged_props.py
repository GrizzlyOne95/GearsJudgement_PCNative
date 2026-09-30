"""Walk the tagged-property stream of a big-endian Judgment cooked export.

This is the reading half of the generic tagged-property BE->LE translator, which is the
highest-leverage remaining content piece: property tags are name-table-indexed and
self-describing, so one translator retires ~90% of a map's exports (components, actors,
Kismet sequence objects, material expressions) without any per-class knowledge.

UE3 FPropertyTag, as measured against Judgment v845 big-endian packages:

    FName Name          INT name index + INT name number      8 bytes
    (stop when Name resolves to "None")
    FName Type          INT name index + INT name number      8 bytes
    INT   Size                                                4 bytes
    INT   ArrayIndex                                          4 bytes
    -- 24 bytes so far --
    StructProperty -> FName StructName                        8 bytes
    ByteProperty   -> FName EnumName                          8 bytes
    BoolProperty   -> BYTE  value                             1 byte
    <Size bytes of value>

Two things cost real time to find, so they are stated plainly:

  1. The tag header is **24 bytes, not 20**. Both Name and Type are full FNames; dropping the
     Type's *number* field shifts Size and ArrayIndex by one INT each. The failure is quiet and
     plausible-looking -- the first tag still decodes with a sensible name and type, and only
     the sizes are nonsense (an ObjectProperty reporting `sz=0 arr=4` instead of `sz=4 arr=0`).
  2. Every export has a **native prologue before the tag stream, and its length varies by
     class**. Measured on GearGame_P.xxx: Actor 26 bytes, Component 8, Package/Sequence 4.
     These are empirical. Confirm them against the Gears 3 source before writing any converter
     that *rewrites* bytes -- guessing a prologue silently corrupts every following offset.

Objects with native payloads (Level, Model, Polys, World, ShaderCache) have their tag stream
followed by native data, so a walk that ends early with slack left over is expected for them and
is not a parse failure. For purely tagged objects the walk should end with **zero slack**; that
exact fit is the validation signal.

Usage:
    python tagged_props.py <manifest.json> <decompressed.xxx> [object_name]
"""
import json
import struct
import sys

TAG_HEADER = 24
MAX_PROLOGUE = 44


class Package:
    def __init__(self, manifest_path, package_path):
        with open(manifest_path) as handle:
            self.doc = json.load(handle)
        with open(package_path, "rb") as handle:
            self.blob = handle.read()
        self.endian = ">" if self.doc["byte_order"] == "big" else "<"
        self.names = [n["name"] for n in self.doc["names"]]

    def i32(self, pos):
        return struct.unpack_from(self.endian + "i", self.blob, pos)[0]

    def name(self, pos):
        """Resolve a name index to text, or None if it is not a valid index."""
        idx = self.i32(pos)
        return self.names[idx] if 0 <= idx < len(self.names) else None

    def walk(self, start, end):
        """Return (tags, stop_pos), or (None, fail_pos) if this is not a tag stream."""
        tags, pos = [], start
        while pos < end:
            name = self.name(pos)
            if name is None or self.i32(pos + 4) < 0:
                return None, pos
            if name == "None":
                return tags, pos + 8
            type_name = self.name(pos + 8)
            if type_name is None or self.i32(pos + 12) != 0 or not type_name.endswith("Property"):
                return None, pos
            size, array_index = self.i32(pos + 16), self.i32(pos + 20)
            if size < 0 or array_index < 0:
                return None, pos
            value_at, extra = pos + TAG_HEADER, ""
            if type_name in ("StructProperty", "ByteProperty"):
                extra = self.name(value_at) or "?"
                value_at += 8
            elif type_name == "BoolProperty":
                extra = str(self.blob[value_at])
                value_at += 1
            if value_at + size > end:
                return None, pos
            tags.append((pos, name, type_name, size, array_index, extra))
            pos = value_at + size
        return None, pos

    def find_prologue(self, export):
        """Discover the native prologue length by finding the offset that parses cleanly."""
        start, end = export["serial_offset"], export["serial_offset"] + export["serial_size"]
        for prologue in range(MAX_PROLOGUE):
            tags, stop = self.walk(start + prologue, end)
            if tags is not None and (tags or export["serial_size"] <= 16):
                return prologue, tags, end - stop
        return None, None, None


def main(manifest_path, package_path, want=None):
    pkg = Package(manifest_path, package_path)
    for export in sorted(pkg.doc["exports"], key=lambda e: e["serial_offset"]):
        if want and export["object_name"] != want:
            continue
        prologue, tags, slack = pkg.find_prologue(export)
        head = f"{export['class_name']} {export['object_name']} size={export['serial_size']}"
        if prologue is None:
            print(f"--- {head}: no tag stream found "
                  f"(expected for native-payload classes)")
            continue
        print(f"--- {head} prologue={prologue} tags={len(tags)} slack={slack}")
        for pos, name, type_name, size, array_index, extra in tags:
            print(f"    @{pos:<7d} {name:26s} {type_name:18s} "
                  f"size={size:<6d} arr={array_index} {extra}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
