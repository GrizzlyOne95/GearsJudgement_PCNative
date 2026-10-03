import struct
import unittest

from extract_asset_package import summary
from replace_texture_pixels import Package, replace, texture


def fixture(version, *, guid=bytes(range(16)), missing_top=False, unsafe_bulk=False, single_mip=False,
            cls="Texture2D", trailer=b"", original=True):
    """`cls`/`trailer` set the destination's class import and native tail; light/shadow maps omit OriginalSizeX/Y."""
    names = ["None", "Core", "Class", "Package", "Engine", "Texture2D", "Material", "Hero",
             "Other", "SizeX", "SizeY", "OriginalSizeX", "OriginalSizeY", "Format",
             "MipTailBaseIdx", "IntProperty", "ByteProperty", "NameProperty", "BoolProperty",
             "FloatProperty", "EPixelFormat", "PF_DXT1", "TextureFileCacheName", "CharTextures",
             "FirstResourceMemMip", "SRGB", "UnpackMin", "LightMapTexture2D", "ShadowMapTexture2D"]
    n = {s: i for i, s in enumerate(names)}
    fname = lambda s: struct.pack("<2i", n[s], 0)
    def tag(name, kind, value, array=0, extra=b""):
        return fname(name) + fname(kind) + struct.pack("<2i", len(value), array) + extra + value
    width = 4 if missing_top else 8
    props = b"".join(tag(s, "IntProperty", struct.pack("<i", width if s in ("SizeX", "SizeY") else 8))
                     for s in ("SizeX", "SizeY", "OriginalSizeX", "OriginalSizeY")
                     if original or s in ("SizeX", "SizeY"))
    props += tag("Format", "ByteProperty", fname("PF_DXT1"), extra=fname("EPixelFormat"))
    levels = [8] if single_mip else [8, 4, 4, 4] if not missing_top else [4, 4, 4]
    if not (single_mip and version == 845):
        props += tag("MipTailBaseIdx", "IntProperty", struct.pack("<i", len(levels) - 1))
    if version == 845:
        props += tag("TextureFileCacheName", "NameProperty", fname("CharTextures"))
        props += tag("FirstResourceMemMip", "IntProperty", struct.pack("<i", 1))
        props += tag("SRGB", "BoolProperty", b"", extra=b"\0")
        props += b"".join(tag("UnpackMin", "FloatProperty", struct.pack("<f", -1.0), array=i)
                          for i in range(3))
    payload = bytearray(struct.pack("<i", 124) + props + fname("None"))
    payload += struct.pack("<4i", 0, 0, 0, 2048 + len(payload) + 16)
    payload += struct.pack("<i", len(levels))
    for index, w in enumerate(levels):
        count = max(1, w // 4) ** 2 * 8
        if version == 845:
            payload += struct.pack("<4i", 0x81, count, count, 5000)
        else:
            off = 2048 + len(payload) + 16
            payload += struct.pack("<4i", 0, count, count, off + int(unsafe_bulk)) + bytes([index + 31]) * count
        payload += struct.pack("<2i", w, w)
    payload += guid + bytes(4) + trailer
    name_bytes = b"".join(struct.pack("<i", len(s) + 1) + s.encode() + b"\0" + bytes(8) for s in names)
    import_bytes = (fname("Core") + fname("Package") + struct.pack("<i", 0) + fname("Engine") +
                    fname("Core") + fname("Class") + struct.pack("<i", -1) + fname(cls) +
                    fname("Core") + fname("Class") + struct.pack("<i", -1) + fname("Material"))
    other = b"Unrelated payload: \x00\x08\x00\x00 and physical padding."
    bodies = [payload, other] if version == 845 else [payload]
    records = b""
    off = 2048
    for idx, body in enumerate(bodies):
        records += struct.pack("<3i", -2 if idx == 0 else -3, 0, 0) + fname("Hero" if idx == 0 else "Other")
        records += struct.pack("<iQ4i5I", 0, 0, len(body), off, 0, 0, 0, 0, 0, 0, 0)
        off += len(body)
    no, io = 129, 129 + len(name_bytes)
    eo, dep = io + len(import_bytes), io + len(import_bytes) + len(records)
    header = summary(version, 8, bytes(16), len(names), len(bodies), 3, 0, (no, io, eo, dep, 2048))
    tables = header + name_bytes + import_bytes + records + bytes(4 * len(bodies))
    assert len(tables) < 2048
    return tables + bytes(2048 - len(tables)) + b"".join(bodies)


class TextureReplacementTests(unittest.TestCase):
    def test_only_selected_serial_fields_change_in_original_file(self):
        source, recovered = fixture(845), fixture(828)
        output, _ = replace(source, {"Hero": recovered})
        restored = bytearray(output[:len(source)])
        at = Package(source).exports[0].table_offset + 32
        restored[at:at + 8] = source[at:at + 8]
        self.assertEqual(restored, source)
        final = Package(output)
        old = Package(source)
        self.assertEqual(final.exports[1], old.exports[1])
        self.assertEqual(final.names, old.names)
        self.assertEqual(final.import_names, old.import_names)

    def test_normal_settings_and_indexed_properties_survive(self):
        source = fixture(845)
        output, _ = replace(source, {"Hero": fixture(828)})
        old, pc = Package(source), Package(output)
        before, after = texture(old, old.exports[0]), texture(pc, pc.exports[0])
        settings = lambda tex: {(t.name, t.array_index): t.raw for t in tex.tags
                                if t.name in ("SRGB", "UnpackMin")}
        self.assertEqual(settings(before), settings(after))
        self.assertEqual(after.net_index, before.net_index)
        self.assertFalse({t.name for t in after.tags} & {"TextureFileCacheName", "FirstResourceMemMip"})
        self.assertEqual([m[2][4] for m in after.mips], [bytes([31]) * 32, bytes([32]) * 8,
                                                     bytes([33]) * 8, bytes([34]) * 8])

    def test_wrong_texture_guid_rejected(self):
        with self.assertRaisesRegex(ValueError, "GUID differs"):
            replace(fixture(845), {"Hero": fixture(828, guid=bytes(16))})

    def test_single_mip_lookup_preserves_absent_packed_tail_setting(self):
        output, _ = replace(fixture(845, single_mip=True), {"Hero": fixture(828, single_mip=True)})
        pc = Package(output)
        tex = texture(pc, pc.exports[0])
        self.assertEqual(len(tex.mips), 1)
        self.assertEqual(tex.mips[0][2][4], bytes([31]) * 32)
        self.assertNotIn("MipTailBaseIdx", {t.name for t in tex.tags})

    def test_metaclass_export_is_preserved(self):
        source = bytearray(fixture(845))
        entry = Package(source).exports[1]
        struct.pack_into("<i", source, entry.table_offset, 0)
        output, _ = replace(bytes(source), {"Hero": fixture(828)})
        pc = Package(output)
        self.assertEqual(pc.class_name(pc.exports[1]), "Class")
        self.assertEqual(pc.exports[1], entry.__class__(entry.index, entry.table_offset, entry.name,
                         entry.name_pair, 0, entry.flags, entry.size, entry.offset))

    def test_stripped_top_mip_changes_base_size_without_changing_authored_size(self):
        source = bytearray(fixture(845))
        pos = source.index(struct.pack("<4i", 0x81, 32, 32, 5000))
        struct.pack_into("<4i", source, pos, 0x21, 0, -1, -1)
        output, _ = replace(bytes(source), {"Hero": fixture(828, missing_top=True)})
        package = Package(output)
        parsed = texture(package, package.exports[0])
        values = {t.name: struct.unpack("<i", t.value)[0] for t in parsed.tags if t.kind == "IntProperty"}
        self.assertEqual((values["SizeX"], values["OriginalSizeX"], len(parsed.mips)), (4, 8, 3))

    def test_resident_high_resolution_mip_cannot_be_discarded(self):
        with self.assertRaisesRegex(ValueError, "omits a resident"):
            replace(fixture(845), {"Hero": fixture(828, missing_top=True)})

    def test_stale_inline_bulk_offset_rejected(self):
        with self.assertRaisesRegex(ValueError, "physical payload"):
            replace(fixture(845), {"Hero": fixture(828, unsafe_bulk=True)})

    def test_incomplete_or_wrong_fixture_selection_rejected(self):
        with self.assertRaisesRegex(ValueError, "every texture"):
            replace(fixture(845), {})
        with self.assertRaisesRegex(ValueError, "every texture"):
            replace(fixture(845), {"AnotherHero": fixture(828)})

    def test_export_index_selection_matches_name_selection(self):
        source, recovered = fixture(845), fixture(828)
        self.assertEqual(replace(source, {0: recovered})[0], replace(source, {"Hero": recovered})[0])
        with self.assertRaisesRegex(ValueError, "does not name a Texture2D"):
            replace(source, {1: recovered})

    def test_rejected_fixture_is_recorded_and_texture_left_as_converted(self):
        source, rejected = fixture(845), []
        output, report = replace(source, {0: fixture(828, guid=bytes(16))}, rejected)
        self.assertEqual(output, source)
        self.assertEqual(report["textures_recovered"], 0)
        self.assertEqual([(r["export_index"], r["name"]) for r in rejected], [(0, "Hero")])
        self.assertIn("GUID differs", rejected[0]["reason"])

    def test_truncated_chain_rejected(self):
        source = fixture(845)
        pc = fixture(828)
        package = Package(pc)
        broken = bytearray(pc)
        # Make SizeX disagree with the physically stored mip dimensions.
        parsed = texture(package, package.exports[0])
        tag = next(t for t in parsed.tags if t.name == "SizeX")
        pos = pc.index(tag.raw, package.exports[0].offset)
        struct.pack_into("<i", broken, pos + tag.value_offset, 4)
        with self.assertRaisesRegex(ValueError, "complete PC mip chain"):
            replace(source, {"Hero": bytes(broken)})


FLAGS = struct.pack("<I", 1)


class LightAndShadowMapTests(unittest.TestCase):
    def source(self, cls, trailer):
        return fixture(845, cls=cls, trailer=trailer, original=False)

    def test_lightmap_trailer_is_preserved_unchanged_after_the_new_mips(self):
        source, recovered = self.source("LightMapTexture2D", FLAGS), fixture(828, original=False)
        output, report = replace(source, {0: recovered})
        pc = Package(output)
        entry = pc.exports[0]
        parsed = texture(pc, entry)
        self.assertEqual((parsed.cls, parsed.trailer), ("LightMapTexture2D", FLAGS))
        self.assertEqual(output[entry.offset + entry.size - 4:entry.offset + entry.size], FLAGS)
        self.assertEqual([m[2][4] for m in parsed.mips],
                         [bytes([31]) * 32, bytes([32]) * 8, bytes([33]) * 8, bytes([34]) * 8])
        self.assertFalse({t.name for t in parsed.tags} & ({"TextureFileCacheName", "FirstResourceMemMip"} |
                                                          {"OriginalSizeX", "OriginalSizeY"}))
        self.assertEqual(report["recovered_by_class"],
                         {"Texture2D": 0, "LightMapTexture2D": 1, "ShadowMapTexture2D": 0})
        self.assertEqual((report["textures"][0]["class"], report["textures"][0]["trailer_bytes"]),
                         ("LightMapTexture2D", 4))

    def test_destination_trailer_value_is_kept_not_defaulted(self):
        source = self.source("LightMapTexture2D", struct.pack("<I", 0x12345678))
        pc = Package(replace(source, {0: fixture(828, original=False)})[0])
        self.assertEqual(texture(pc, pc.exports[0]).trailer, struct.pack("<I", 0x12345678))

    def test_shadowmap_has_no_trailer(self):
        source = self.source("ShadowMapTexture2D", b"")
        output, report = replace(source, {0: fixture(828, original=False)})
        pc = Package(output)
        parsed = texture(pc, pc.exports[0])
        self.assertEqual((parsed.cls, parsed.trailer, len(parsed.mips)), ("ShadowMapTexture2D", b"", 4))
        self.assertEqual(report["recovered_by_class"]["ShadowMapTexture2D"], 1)
        pc_end = pc.exports[0].offset + pc.exports[0].size
        self.assertEqual(output[pc_end - 20:pc_end], parsed.guid + bytes(4))

    def test_wrong_trailer_length_rejected(self):
        for cls, trailer in (("LightMapTexture2D", b""), ("LightMapTexture2D", bytes(8)),
                             ("ShadowMapTexture2D", FLAGS), ("Texture2D", FLAGS)):
            source = self.source(cls, trailer)
            package = Package(source)
            with self.assertRaisesRegex(ValueError, "trailer"):
                texture(package, package.exports[0])
            with self.assertRaisesRegex(ValueError, "exact .*-byte %s trailer, found %d" % (cls, len(trailer))):
                replace(source, {0: fixture(828, original=False)})
            rejected = []
            output, report = replace(source, {0: fixture(828, original=False)}, rejected)
            self.assertEqual((output, report["textures_recovered"]), (source, 0))
            self.assertEqual([(r["class"], r["stage"]) for r in rejected], [(cls, "writer")])

    def test_fixture_must_be_plain_and_trailerless(self):
        source = self.source("LightMapTexture2D", FLAGS)
        with self.assertRaisesRegex(ValueError, "Texture2D trailer, found 4"):
            replace(source, {0: fixture(828, original=False, trailer=FLAGS)})
        with self.assertRaisesRegex(ValueError, "matching texture"):
            replace(source, {0: fixture(828, original=False, cls="LightMapTexture2D", trailer=FLAGS)})

    def test_original_size_presence_must_agree_and_stays_required_for_plain_textures(self):
        with self.assertRaisesRegex(ValueError, "authored dimensions differ"):
            replace(self.source("LightMapTexture2D", FLAGS), {0: fixture(828)})
        with self.assertRaisesRegex(ValueError, "authored dimensions differ"):
            replace(fixture(845, cls="ShadowMapTexture2D"), {0: fixture(828, original=False)})
        with self.assertRaisesRegex(ValueError, "missing required"):
            replace(fixture(845, original=False), {0: fixture(828, original=False)})

    def test_name_keyed_selection_stays_plain_texture_only(self):
        source = self.source("LightMapTexture2D", FLAGS)
        with self.assertRaisesRegex(ValueError, "every texture"):
            replace(source, {"Hero": fixture(828, original=False)})
        with self.assertRaisesRegex(ValueError, "does not name a Texture2D"):
            replace(source, {1: fixture(828, original=False)})


if __name__ == "__main__":
    unittest.main()
