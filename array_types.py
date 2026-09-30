"""Build an ArrayProperty element-type index from Judgment's script packages.

`be2le.py` can swap every tagged property whose width it can derive from the map package alone.
ArrayProperty is the exception: the tag records the property name and the total byte size, but the
*element* type lives in the script packages, as the `Inner` UProperty the ArrayProperty points at.
This tool resolves that link once and writes a lookup table the converter can consume.

Resolution follows the same trick `proptypes.py` uses, and for the same reason -- a UProperty's
type reference is serialized **last**, so the trailing INT32 of its payload is the reference,
without having to model every preceding field whose width varies by flags:

    ArrayProperty payload -> trailing INT32 -> Inner UProperty export
    Inner is StructProperty -> its trailing INT32 -> the UScriptStruct it names

Package index convention is UE3's: >0 is an export (1-based), <0 an import (1-based), 0 is null.

Keys are "Owner.PropertyName", where Owner is `object_path` component [-2] -- matched at ANY
nesting depth, exactly as `scan_classes.py` does, so that properties declared inside nested
ScriptStructs are not silently skipped. Function locals land in the table too; they are harmless
because they never appear in a serialized tagged stream.

Judgment's script packages are little-endian and uncompressed even in the Xbox cook, so they are
read directly with no decompression step -- unlike the cooked content packages.

Usage:
    python array_types.py <out-index.json> <script-manifest.json> [<manifest.json> ...]

Each manifest is expected to sit beside the .u it was generated from, or the .u path can be given
as "manifest.json=package.u".
"""
import collections
import json
import os
import struct
import sys

# Element types whose serialized width is fixed and knowable without further lookups.
FIXED_WIDTH = {
    "IntProperty": [4], "FloatProperty": [4], "ObjectProperty": [4],
    "ComponentProperty": [4], "ClassProperty": [4], "QWordProperty": [8],
    "NameProperty": [4, 4],
}


def resolve(index, exports, imports):
    """UE3 package index -> (kind, entry) or (None, None)."""
    if index > 0 and index - 1 < len(exports):
        return "export", exports[index - 1]
    if index < 0 and -index - 1 < len(imports):
        return "import", imports[-index - 1]
    return None, None


def trailing_ref(blob, export):
    """The type reference an UProperty serializes last."""
    off, size = export["serial_offset"], export["serial_size"]
    if size < 4 or off + size > len(blob):
        return None
    return struct.unpack_from("<i", blob, off + size - 4)[0]


def owner_and_name(export):
    parts = (export.get("object_path") or "").split(".")
    if len(parts) < 2:
        return None, None
    return parts[-2], parts[-1]


def index_package(manifest_path, package_path, table, stats):
    with open(manifest_path) as handle:
        doc = json.load(handle)
    with open(package_path, "rb") as handle:
        blob = handle.read()
    exports, imports = doc["exports"], doc["imports"]

    for export in exports:
        if export["class_name"] != "ArrayProperty":
            continue
        owner, name = owner_and_name(export)
        if owner is None:
            continue
        stats["arrays"] += 1

        ref = trailing_ref(blob, export)
        if ref is None:
            stats["no_ref"] += 1
            continue
        kind, inner = resolve(ref, exports, imports)
        if kind != "export":
            # An imported Inner cannot be inspected from this package alone.
            stats["inner_imported"] += 1
            continue

        element = inner["class_name"]
        struct_name = None
        if element == "StructProperty":
            struct_ref = trailing_ref(blob, inner)
            if struct_ref is not None:
                skind, sentry = resolve(struct_ref, exports, imports)
                if sentry is not None:
                    struct_name = sentry["object_name"]

        entry = {"elem": element, "struct": struct_name,
                 "widths": FIXED_WIDTH.get(element)}
        # Keep every distinct declaration rather than collapsing collisions to "unknown".
        # `Materials`, for instance, is an ObjectProperty array on one class and three different
        # struct arrays elsewhere; the converter picks between them with the count * width check,
        # so throwing the alternatives away would lose thousands of convertible arrays.
        candidates = table.setdefault(f"{owner}.{name}", [])
        if entry not in candidates:
            candidates.append(entry)
            if len(candidates) > 1:
                stats["multi_declaration"] += 1
        stats["indexed"] += 1


def main(out_path, manifest_args):
    table, stats = {}, collections.Counter()
    for arg in manifest_args:
        if "=" in arg:
            manifest_path, package_path = arg.split("=", 1)
        else:
            manifest_path = arg
            stem = os.path.splitext(os.path.basename(manifest_path))[0]
            package_path = os.path.join(os.path.dirname(manifest_path) or ".", stem + ".u")
        if not os.path.exists(package_path):
            print(f"  skip {manifest_path}: package not found at {package_path}")
            continue
        before = stats["indexed"]
        index_package(manifest_path, package_path, table, stats)
        print(f"  {os.path.basename(package_path)}: +{stats['indexed'] - before} entries")

    with open(out_path, "w") as handle:
        json.dump(table, handle, indent=0, sort_keys=True)

    entries = [e for candidates in table.values() for e in candidates]
    resolved = sum(1 for e in entries if e.get("widths"))
    structs = sum(1 for e in entries if e.get("elem") == "StructProperty")
    print(f"\nwrote {out_path}: {len(table)} keys, {len(entries)} declarations")
    print(f"  fixed-width elements: {resolved}   struct elements: {structs}")
    print(f"  arrays seen: {stats['arrays']}   inner imported: {stats['inner_imported']}   "
          f"keys with several declarations: {stats['multi_declaration']}")
    kinds = collections.Counter(e.get("elem") for e in entries)
    print("  element types: " + ", ".join(f"{k}={n}" for k, n in kinds.most_common(10)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
