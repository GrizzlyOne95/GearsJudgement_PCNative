"""Extract each UProperty's *target type* from a UE3 script package.

Property names do not determine C++ size: in FPostProcessSettings, Bloom_Tint is FColor
(4 bytes) while RimShader_Color is FLinearColor (16). Guessing corrupts every subsequent
offset silently, so the type must come from the package itself.

UProperty payload layout (UE3, little-endian script package):
    INT   NetIndex          (cooked packages)
    INT   Next              (UField, object ref)
    INT   ArrayDim
    QWORD PropertyFlags
    FName Category          (INT name index + INT number)
    INT   ArraySizeEnum     (object ref)
    [WORD RepOffset]        only when PropertyFlags & CPF_Net
    INT   <type ref>        StructProperty->Struct / ObjectProperty->PropertyClass /
                            ArrayProperty->Inner / ByteProperty->Enum
"""
import json
import struct
import sys

CPF_Net = 0x0000000000000020

TYPED = {
    "StructProperty": "Struct",
    "ObjectProperty": "PropertyClass",
    "ComponentProperty": "PropertyClass",
    "ClassProperty": "PropertyClass",
    "InterfaceProperty": "InterfaceClass",
    "ArrayProperty": "Inner",
    "ByteProperty": "Enum",
}


class Reader:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.d, self.p)[0]
        self.p += 8
        return v

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v


def resolve(idx, exports, imports):
    """UE3 package index: >0 export (1-based), <0 import (1-based), 0 null."""
    if idx > 0 and idx - 1 < len(exports):
        return exports[idx - 1]["object_name"]
    if idx < 0 and -idx - 1 < len(imports):
        return imports[-idx - 1]["object_name"]
    return None


def main(manifest_path, package_path, owner_filter=None):
    doc = json.load(open(manifest_path))
    exports, imports = doc["exports"], doc["imports"]
    blob = open(package_path, "rb").read()

    results = []
    for e in exports:
        cls = e["class_name"]
        if cls not in TYPED:
            continue
        parts = (e.get("object_path") or "").split(".")
        if len(parts) < 3:
            continue
        owner, name = parts[-2], parts[-1]
        if owner_filter and owner != owner_filter:
            continue
        off, size = e["serial_offset"], e["serial_size"]
        if size <= 0 or off + size > len(blob):
            continue
        # The type-specific object reference is serialized last, so read the
        # trailing INT32 rather than modelling every intermediate field (whose
        # widths vary by property flags and engine version). Verified against
        # Gears 3 natives: Bloom_Tint -> Color, RimShader_Color -> LinearColor.
        try:
            target = resolve(struct.unpack_from("<i", blob, off + size - 4)[0],
                             exports, imports)
        except Exception:
            target = None
        results.append((owner, name, cls, target))
    return results


if __name__ == "__main__":
    rows = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    for owner, name, cls, target in rows:
        print(f"  {cls:18s} {name:45s} -> {target}")
