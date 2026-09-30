"""Extract a bounded asset group from a decompressed Judgment startup archive.

Only typed UObject reference fields are remapped. Original physical payload and
bulk offsets remain fixed; unselected bytes are unreachable padding, not exports.
This deliberately avoids guessing references by scanning arbitrary DWORD values.
The first supported surface is Baird's mesh, sockets, physics and materials.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from be2le import Converter, load_array_types

SUPPORTED = {
    "Package", "SkeletalMesh", "SkeletalMeshSocket", "PhysicsAsset",
    "PhysicsAssetInstance", "RB_BodySetup", "RB_BodyInstance",
    "RB_ConstraintSetup", "RB_ConstraintInstance", "Material",
    "MaterialInstanceConstant", "Texture2D", "PhysicalMaterial", "FaceFXAsset",
}


def fname(index, number=0):
    return struct.pack("<2i", index, number)


def ansi(value):
    body = value.encode("latin-1") + b"\0"
    return struct.pack("<i", len(body)) + body


def summary(version, flags, guid, names, exports, imports, net_count, offsets):
    name_offset, import_offset, export_offset, depends_offset, header_end = offsets
    result = struct.pack("<3I", 0x9E2A83C1, version, header_end) + ansi("None")
    result += struct.pack("<12I", flags, names, name_offset, exports, export_offset,
                          imports, import_offset, depends_offset, 0, 0, 0, 0)
    result += guid + struct.pack("<4i", 1, exports, names, net_count)
    # Saved engine, cooked content, compression, chunks, source, extra packages,
    # texture preallocation. The latter cannot retain old export indices.
    result += struct.pack("<7I", 9580, 0, 0, 0, 0, 0, 0)
    return result


def extract(source, manifest, root_name, array_types, array_owners=None, resolve_imports=False):
    if source[:4] != b"\x9e\x2a\x83\xc1" or manifest["package_version"] != 845:
        raise ValueError("requires a decompressed big-endian Judgment v845 archive")
    exports, imports = manifest["exports"], manifest["imports"]
    roots = [e for e in exports if e["outer_index"] == 0 and
             e["class_name"] == "Package" and e["object_name"] == root_name]
    if len(roots) != 1:
        raise ValueError("asset root must be one top-level Package export")
    root = roots[0]
    root_index = root["package_index"]
    selected = []
    for entry in exports:
        index = entry["package_index"]
        seen = set()
        while index > 0 and index != root_index:
            if index in seen:
                raise ValueError("cyclic export ownership")
            seen.add(index)
            index = exports[index - 1]["outer_index"]
        if index == root_index:
            selected.append(entry)
    bad = Counter(e["class_name"] for e in selected if e["class_name"] not in SUPPORTED)
    if bad:
        raise ValueError("reference tracking is not approved for classes: %s" % dict(bad))

    converter = Converter(source, array_types, track_references=True, array_owners=array_owners)
    names = [entry["name"] for entry in manifest["names"]]
    names_by_text = {name: index for index, name in enumerate(names)}
    selected_indices = {e["index"] for e in selected}
    records = export_records(source, converter.header_ints())
    source_exports = [(e["class_index"], e["outer_index"], int(e["object_flags"], 16),
                       e["serial_size"] if e["index"] in selected_indices else 0,
                       e["serial_offset"]) for e in exports]
    converter.payloads(source_exports, names,
                       lambda index: imports[-index - 1]["object_name"] if index < 0
                       else exports[index - 1]["object_name"] if index else "Class")
    if converter.unsupported or converter.stats["converted"] != len(selected):
        raise ValueError("asset conversion incomplete: %s" % dict(converter.unsupported))

    emitted = [e for e in selected if e["package_index"] != root_index]
    remap = {root_index: 0, 0: 0}
    remap.update((e["package_index"], index + 1) for index, e in enumerate(emitted))
    new_imports, import_keys = [], {}
    active = set()

    def map_ref(index):
        if index in remap:
            return remap[index]
        if index in active:
            raise ValueError("cyclic import ownership")
        active.add(index)
        if index < 0:
            entry = imports[-index - 1]
            class_package, class_name = entry["class_package"], entry["class_name"]
        else:
            entry = exports[index - 1]
            class_name = entry["class_name"]
            class_index = entry["class_index"]
            if class_index == 0:
                class_package = "Core"
            else:
                cls = imports[-class_index - 1] if class_index < 0 else exports[class_index - 1]
                while cls["outer_index"]:
                    owner = cls["outer_index"]
                    cls = imports[-owner - 1] if owner < 0 else exports[owner - 1]
                class_package = cls["object_name"]
        outer = map_ref(entry["outer_index"])
        # Identical source imports and external exports collapse to the same import.
        if index < 0:
            table = converter.header_ints()[6] + (-index - 1) * 28
            object_name = struct.unpack_from(">2i", source, table + 20)
        else:
            object_name = records[index - 1][0]
        key = class_package, class_name, outer, object_name
        if key not in import_keys:
            new_imports.append(key)
            import_keys[key] = -len(new_imports)
        mapped = import_keys[key]
        remap[index] = mapped
        active.remove(index)
        return mapped

    dependencies = []
    ref_count = 0
    for entry in emitted:
        for field in ("class_index", "super_index", "outer_index", "archetype_index"):
            map_ref(entry[field])
        start, end = entry["serial_offset"], entry["serial_offset"] + entry["serial_size"]
        refs = [off for off in converter.object_reference_offsets if start <= off < end]
        if len(refs) != len(set(refs)):
            raise ValueError("a reference field was visited twice")
        deps = set()
        for off in refs:
            old_ref = struct.unpack_from(">i", source, off)[0]
            new_ref = map_ref(old_ref)
            struct.pack_into("<i", converter.out, off, new_ref)
            if new_ref > 0:
                deps.add(new_ref)
        dependencies.append(sorted(deps))
        ref_count += len(refs)

    name_bytes = bytearray()
    for entry in manifest["names"]:
        value = entry["name"]
        try:
            name_bytes += ansi(value)
        except UnicodeEncodeError:
            data = value.encode("utf-16le") + b"\0\0"
            name_bytes += struct.pack("<i", -len(data) // 2) + data
        name_bytes += struct.pack("<Q", int(entry["flags"], 16))
    import_bytes = bytearray()
    for class_package, class_name, outer, object_name in new_imports:
        import_bytes += fname(names_by_text[class_package]) + fname(names_by_text[class_name])
        import_bytes += struct.pack("<i", outer) + fname(*object_name)
    export_bytes = bytearray()
    for entry in emitted:
        # FName instance numbers are part of the name, and cannot be discarded.
        # The manifest renders suffixes; preserve the original FName pair.
        (name_index, number), package_guid = records[entry["index"]]
        export_bytes += struct.pack("<3i", map_ref(entry["class_index"]), map_ref(entry["super_index"]),
                                    map_ref(entry["outer_index"])) + fname(name_index, number)
        export_bytes += struct.pack("<iQ3i", map_ref(entry["archetype_index"]), int(entry["object_flags"], 16),
                                    entry["serial_size"], entry["serial_offset"],
                                    int(entry["export_flags"], 16) & ~1)
        generations = entry["generation_net_object_counts"]
        export_bytes += struct.pack("<i", len(generations))
        export_bytes += struct.pack("<%di" % len(generations), *generations)
        export_bytes += struct.pack("<4I", *package_guid)
        export_bytes += struct.pack("<I", int(entry["package_flags"], 16))
    depends_bytes = b"".join(struct.pack("<i", len(refs)) + struct.pack("<%di" % len(refs), *refs)
                              for refs in dependencies)
    guid = struct.pack("<4I", *records[root["index"]][1])
    net_count = max(root["generation_net_object_counts"] or [0])
    fields = converter.header_ints()
    package_flags = fields[0] & 0xFFFFFFFF
    if resolve_imports:
        # The startup cook preloads all of its ownership groups together. An
        # extracted group instead imports its external dependencies, including
        # nested material parents. Permit the normal PC linker to load them.
        package_flags &= ~0x00800000  # PKG_RequireImportsAlreadyLoaded
    header_size = len(summary(845, package_flags, guid, len(names), len(emitted),
                              len(new_imports), net_count, (0, 0, 0, 0, 0)))
    offsets = [header_size]
    offsets.append(offsets[-1] + len(name_bytes))
    offsets.append(offsets[-1] + len(import_bytes))
    offsets.append(offsets[-1] + len(export_bytes))
    offsets.append(offsets[-1] + len(depends_bytes))
    header = summary(845, package_flags, guid, len(names), len(emitted), len(new_imports), net_count, offsets)
    old_header_end = struct.unpack_from(">i", source, 8)[0]
    if offsets[-1] > old_header_end or any(e["serial_offset"] < old_header_end for e in emitted):
        raise ValueError("compact tables do not fit before the retained payloads")
    converter.out[:old_header_end] = bytes(old_header_end)
    tables = header + name_bytes + import_bytes + export_bytes + depends_bytes
    converter.out[:len(tables)] = tables
    report = {"root": root_name, "source_sha256": hashlib.sha256(source).hexdigest(),
              "source_exports": len(exports), "selected_exports": len(selected),
              "emitted_exports": len(emitted), "imports": len(new_imports),
              "remapped_payload_references": ref_count,
              "classes": dict(Counter(e["class_name"] for e in emitted)),
              "physical_offsets_preserved": True,
              "external_dependencies": [names[key[3][0]] for key in new_imports if key[2] == 0],
              "sha256": hashlib.sha256(converter.out).hexdigest()}
    if resolve_imports:
        report["resolve_external_imports"] = True
        report["package_flags"] = "0x%08X" % package_flags
    return bytes(converter.out), report


def export_records(source, fields):
    pos = fields[4]
    result = []
    for index in range(fields[3]):
        name = struct.unpack_from(">2i", source, pos + 12)
        count = struct.unpack_from(">i", source, pos + 44)[0]
        if count < 0:
            raise ValueError("invalid export generation count")
        guid = struct.unpack_from(">4I", source, pos + 48 + 4 * count)
        result.append((name, guid))
        pos += 68 + 4 * count
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("root")
    parser.add_argument("output", type=Path)
    parser.add_argument("array_types", type=Path)
    parser.add_argument("--resolve-imports", action="store_true",
                        help="permit PC dependency loading for the extracted ownership group")
    args = parser.parse_args()
    report_path = args.output.with_suffix(".extraction.json")
    if args.output.exists() or report_path.exists():
        raise SystemExit("refusing to overwrite retained evidence")
    output, report = extract(args.source.read_bytes(), json.loads(args.manifest.read_text()),
                             args.root, load_array_types(args.array_types)[0],
                             json.loads(args.array_types.read_text()), args.resolve_imports)
    args.output.write_bytes(output)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
