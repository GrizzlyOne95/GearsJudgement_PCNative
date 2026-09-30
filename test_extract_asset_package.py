import copy
import struct
import unittest

from be2le import Converter
from extract_asset_package import extract


def fixture():
    names = ["None", "Core", "Class", "Package", "Engine", "PhysicsAsset",
             "ObjectProperty", "IntProperty", "ArrayProperty", "Target", "Self",
             "Alias", "Unrelated", "Constraints", "Hero", "Asset", "Other", "OtherAsset"]
    n = {name: index for index, name in enumerate(names)}
    def tag(name, kind, value):
        return struct.pack(">6i", n[name], 0, n[kind], 0, len(value), 0) + value
    payload = struct.pack(">i", -1)
    fields = {}
    for name, kind, value in (("Target", "ObjectProperty", 4), ("Self", "ObjectProperty", 2),
                               ("Alias", "ObjectProperty", -2), ("Unrelated", "IntProperty", 4)):
        fields[name] = 2060 + len(payload) + 24
        payload += tag(name, kind, struct.pack(">i", value))
    fields["Constraints"] = 2060 + len(payload) + 28
    payload += tag("Constraints", "ArrayProperty", struct.pack(">3i", 2, 2, 4))
    payload += struct.pack(">2i", n["None"], 0)
    empty = struct.pack(">3i", -1, n["None"], 0)
    data = [empty, payload, empty, empty]
    offsets = [2048, 2060, 2060 + len(payload), 2072 + len(payload)]
    export_names = [("Hero", 0), ("Asset", 4), ("Other", 0), ("OtherAsset", 0)]
    owners = [0, 1, 0, 3]
    classes = ["Package", "PhysicsAsset", "Package", "PhysicsAsset"]
    es = []
    for index, ((name, number), cls, owner, body, offset) in enumerate(zip(export_names, classes, owners, data, offsets)):
        es.append({"index": index, "package_index": index + 1, "object_name": name if not number else name + "_" + str(number - 1),
                   "object_path": "Fixture." + ("Hero." if owner == 1 else "Other." if owner == 3 else "") + name,
                   "class_name": cls, "class_index": -4 if cls == "Package" else -2,
                   "super_index": 0, "outer_index": owner, "archetype_index": 0,
                   "object_flags": "0x0007000400000000", "serial_size": len(body), "serial_offset": offset,
                   "export_flags": "0x00000001", "generation_net_object_counts": [],
                   "package_guid": "00000000-0000-0000-0000-000000000000", "package_flags": "0x00000000"})
    ins = [{"index": i, "package_index": -i - 1, "class_package": "Core", "class_name": cls,
            "outer_index": outer, "object_name": name} for i, (cls, outer, name) in enumerate(
                [("Package", 0, "Engine"), ("Class", -1, "PhysicsAsset"), ("Package", 0, "Core"), ("Class", -3, "Package")])]
    ns = [{"index": i, "name": name, "flags": "0x0007001000000000"} for i, name in enumerate(names)]
    name_bytes = b"".join(struct.pack(">i", len(e["name"]) + 1) + e["name"].encode() + b"\0" +
                           struct.pack(">Q", int(e["flags"], 16)) for e in ns)
    import_bytes = b"".join(struct.pack(">7i", n[e["class_package"]], 0, n[e["class_name"]], 0,
                                          e["outer_index"], n[e["object_name"]], 0) for e in ins)
    export_bytes = b""
    for e, (name, number) in zip(es, export_names):
        export_bytes += struct.pack(">6iQ4i5I", e["class_index"], 0, e["outer_index"], n[name], number, 0,
                                    int(e["object_flags"], 16), e["serial_size"], e["serial_offset"], 1, 0, 0, 0, 0, 0, 0)
    name_offset = 129
    import_offset = name_offset + len(name_bytes)
    export_offset = import_offset + len(import_bytes)
    depends_offset = export_offset + len(export_bytes)
    header = struct.pack(">3I", 0x9E2A83C1, 845, 2048) + struct.pack(">i", 5) + b"None\0"
    header += struct.pack(">12I", 8, len(ns), name_offset, len(es), export_offset, len(ins), import_offset, depends_offset, 0, 0, 0, 0)
    header += bytes(16) + struct.pack(">4i", 1, len(es), len(ns), 0) + struct.pack(">7i", 9580, 0, 0, 0, 0, 0, 0)
    assert len(header) == name_offset
    source = bytearray(2084 + len(payload))
    tables = header + name_bytes + import_bytes + export_bytes + bytes(16)
    source[:len(tables)] = tables
    for offset, body in zip(offsets, data):
        source[offset:offset + len(body)] = body
    manifest = {"package_version": 845, "names": ns, "exports": es, "imports": ins}
    arrays = {"Constraints": [{"elem": "FloatProperty", "widths": [4]}, {"elem": "ObjectProperty", "widths": [4]}]}
    owners = {"PhysicsAsset.Constraints": [arrays["Constraints"][1]]}
    return bytes(source), manifest, arrays, owners, fields


class AssetExtractionTests(unittest.TestCase):
    def test_typed_references_change_but_matching_integer_does_not(self):
        source, manifest, arrays, owners, fields = fixture()
        output, report = extract(source, manifest, "Hero", arrays, owners)
        self.assertEqual(report["emitted_exports"], 1)
        self.assertEqual(report["remapped_payload_references"], 5)
        self.assertLess(struct.unpack_from("<i", output, fields["Target"])[0], 0)
        self.assertEqual(struct.unpack_from("<i", output, fields["Self"])[0], 1)
        self.assertEqual(struct.unpack_from("<i", output, fields["Unrelated"])[0], 4)
        self.assertEqual(struct.unpack_from("<i", output, fields["Constraints"])[0], 1)
        self.assertLess(struct.unpack_from("<i", output, fields["Constraints"] + 4)[0], 0)
        # Source is immutable, and external payload offsets/bytes remain untouched.
        self.assertEqual(struct.unpack_from(">i", source, fields["Target"])[0], 4)
        other = manifest["exports"][3]
        self.assertEqual(output[other["serial_offset"]:], source[other["serial_offset"]:])
        self.assertEqual(len(output), len(source))

    def test_fname_instance_and_export_outer_are_preserved(self):
        source, manifest, arrays, owners, _ = fixture()
        output, _ = extract(source, manifest, "Hero", arrays, owners)
        folder = struct.unpack_from("<i", output, 12)[0]
        header = struct.unpack_from("<12i", output, 16 + folder)
        export_at = header[4]
        self.assertEqual(struct.unpack_from("<3i", output, export_at)[2], 0)
        self.assertEqual(struct.unpack_from("<2i", output, export_at + 12), (15, 4))
        self.assertEqual(struct.unpack_from("<i", output, export_at + 40)[0], 0)
        self.assertEqual(struct.unpack_from("<i", output, export_at + 36)[0], 2060)

    def test_ambiguous_same_width_arrays_require_an_owner(self):
        source, manifest, arrays, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "ambiguous extracted array"):
            extract(source, manifest, "Hero", arrays)

    def test_invalid_reference_and_unsupported_class_fail_closed(self):
        source, manifest, arrays, owners, fields = fixture()
        invalid = bytearray(source)
        struct.pack_into(">i", invalid, fields["Target"], 9999)
        with self.assertRaisesRegex(ValueError, "invalid extracted object"):
            extract(invalid, manifest, "Hero", arrays, owners)
        unsupported = copy.deepcopy(manifest)
        unsupported["exports"][1]["class_name"] = "MorphTarget"
        with self.assertRaisesRegex(ValueError, "not approved"):
            extract(source, unsupported, "Hero", arrays, owners)

    def test_failed_speculation_rolls_back_reference_locations(self):
        converter = Converter(struct.pack(">2i", 1, 2), track_references=True)
        converter.record_object_ref(0)
        def attempt():
            converter.record_object_ref(4)
            converter.swap(4, 4)
            return False
        self.assertFalse(converter.try_region(4, 8, attempt))
        self.assertEqual(converter.object_reference_offsets, [0])
        self.assertEqual(converter.out, converter.src)

    def test_interface_serializes_only_its_object_reference(self):
        # UInterfaceProperty::SerializeItem persists the UObject, then rebuilds
        # the native interface address at load time; it is not an eight-byte pair.
        converter = Converter(struct.pack(">i", 3), track_references=True)
        converter.value([], "InterfaceProperty", None, 0, 4, 0, "Interface")
        self.assertEqual(converter.out, struct.pack("<i", 3))
        self.assertEqual(converter.object_reference_offsets, [0])
        self.assertFalse(converter.unsupported)

    def test_deterministic_output(self):
        source, manifest, arrays, owners, _ = fixture()
        self.assertEqual(extract(source, manifest, "Hero", arrays, owners),
                         extract(source, manifest, "Hero", arrays, owners))


if __name__ == "__main__":
    unittest.main()
