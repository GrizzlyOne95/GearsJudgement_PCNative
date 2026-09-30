"""Independent BE/LE archives for mixed-width geometry and populated Level tails."""
import struct
import unittest

from be2le import Converter


class Archive:
    def __init__(self, endian):
        self.endian, self.data = endian, bytearray()

    def emit(self, fmt, *values):
        self.data.extend(struct.pack(self.endian + fmt, *values))

    def raw(self, data):
        self.data.extend(data)

    def string(self, value):
        data = value.encode() + b"\0"
        self.emit("i", len(data))
        self.raw(data)

    def bulk(self, fmt, rows):
        self.emit("ii", struct.calcsize("=" + fmt), len(rows))
        for row in rows:
            self.emit(fmt, *row)

    def byte_bulk(self, data):
        self.emit("4i", 0, len(data), len(data), len(self.data) + 16)
        self.raw(data)

    def lightmap(self, kind):
        self.emit("i", kind)
        if not kind:
            return
        self.emit("i4I", 1, 1, 2, 3, 4)
        if kind == 1:
            self.emit("i", -1)
            self.byte_bulk(b"\x12\x34\x56\x78\x9a\xbc\xde\xf0")
            self.emit("9f", *range(1, 10))
            self.byte_bulk(b"\x10\x20\x30\x40")
        else:
            for ref in (1, -1, 0):
                self.emit("i3f", ref, .25, .5, .75)
            self.emit("4f", .5, .25, .125, .0625)


def component_fixture(endian, kind, colors):
    a = Archive(endian)
    a.emit("iiiii", 1, 1, -1, 1, 1)  # one LOD, one of each shadow ref
    a.lightmap(kind)
    a.emit("B", int(colors))
    if colors:
        a.emit("4iI", 4, 1, 4, 1, 0x12345678)
    a.emit("i3f2I", 1, 1.5, -2.5, 3.5, 0xABCDEF12, 0x12345678)
    return bytes(a.data)


def mesh_fixture(endian, full=False, fracture=False):
    a = Archive(endian)
    a.emit("7fi6f", *range(1, 8), -1, *range(1, 7))
    a.bulk("6B", [(1, 2, 3, 4, 5, 6)])
    a.bulk("4H", [(0, 1, 2, 3)])
    a.emit("iiifii", 18, 0, 1, .5, 0, 1)  # version/source/deviations/simplified/LOD
    a.emit("4i", 32, 0, 0, -1)  # RawTriangles unused
    a.emit("ii8I", 1, -1, 1, 2, 3, 4, 5, 6, 7, 8)
    a.emit("i2iB", 1, 0, 1, 0)  # fragment, platform byte
    a.emit("ii", 12, 1)
    a.bulk("3f", [(1.5, -2.5, 3.5)])
    fmt = "2I4f" if full else "2I4H"
    a.emit("4i", 2, struct.calcsize("=" + fmt), 1, int(full))
    a.bulk(fmt, [(0x12345678, 0xABCDEF12, .25, .5, .75, 1)] if full else
           [(0x12345678, 0xABCDEF12, 0x3400, 0x3800, 0x3A00, 0x3C00)])
    a.emit("4iI", 4, 1, 4, 1, 0x11223344)
    a.emit("i", 1)
    a.bulk("H", [(0,), (0,), (0,)])
    a.bulk("H", [(0,), (0,)])
    a.emit("i3if", 1, 17, 18, 19, 20.5)
    a.string("HighRes")
    a.emit("6IifI", 21, 22, 23, 24, 25, 26, 1, .75, 1)
    if fracture:
        a.emit("ii3f", -1, 1, 1, 2, 3)
        for fmt, row in (("3f", (1, 2, 3)), ("4f", (1, 2, 3, 4)),
                         ("i", (17,)), ("3f", (1, 2, 3)), ("3f", (4, 5, 6)),
                         ("4f", (1, 2, 3, 4))):
            a.emit("i", 1)
            a.emit(fmt, *row)
        a.emit("6fB7fiB3i3fif", *range(1, 7), 1, *range(1, 8),
               1, 255, 1, 0, 1, 1, 2, 3, 1, .5)
        a.emit("14I2H", *range(1, 15), 0x1234, 0x5678)
    return bytes(a.data)


def level_fixture(endian):
    a = Archive(endian)
    a.emit("iii", 1, 1, -1)
    for value in ("unreal", "host", "SP_E2_01", "portal"):
        a.string(value)
    a.emit("i", 1)
    a.string("listen")
    a.emit("7i", 7777, 1, 1, 1, -1, 1, 1)
    a.emit("iii5f", 1, -1, 1, 1, 2, 3, 4, 5)  # texture instances
    a.emit("iii5fiif", 1, 1, 1, 1, 2, 3, 4, 5, -1, 1, 6)
    a.emit("i", 4)
    a.raw(b"APEX")
    a.bulk("B", [(0x12,), (0x34,)])
    a.emit("ii3fi", 1, -1, 1, 2, 3, 0)
    a.emit("ii", 1, 1)  # convex store, convex elements
    a.bulk("B", [(0x56,), (0x78,)])
    a.emit("ii3fi", 1, -1, 3, 2, 1, 0)
    a.emit("i", 1)
    a.bulk("B", [(0x9A,), (0xBC,)])
    a.emit("5i", 9, 10, 1, -1, 1)
    a.emit("i", 1)
    a.bulk("B", [(0xDE,), (0xF0,)])
    a.emit("7i", 11, 1, -1, 0, 1, -1, 0)
    a.emit("i5I", 1, 1, 2, 3, 4, 5)  # GUID + cover index
    a.emit("4iBii", 1, -1, 1, 0x12345678, 255, 1, 1)
    a.emit("i6fBfi", 1, *range(1, 7), 1, .5, 1)  # light volume
    a.emit("4f4B3IB", 1, 2, 3, 4, 9, 8, 7, 6,
           0x12345678, 0x9ABCDEF0, 0x11223344, 255)
    a.emit("6fi", 1, 2, 3, 4, 5, 6, 1)
    a.emit("ii3f2H", 4, 1, 1, 2, 3, 0x1234, 0x5678)
    a.emit("4i", 1, 1, 123, 4)
    a.raw(b"zlib")
    a.emit("f6fB4i2I", 100, *range(1, 7), 1, 1, 1, 2, 2, 0x12345678, 0x9ABCDEF0)
    return bytes(a.data)


def model_fixture(endian):
    a = Archive(endian)
    a.emit("7f", *range(1, 8))
    a.bulk("3f", [(0, 0, 1)])
    a.bulk("3f", [(1, 2, 3), (4, 5, 6), (7, 8, 9)])
    a.bulk("4f3i2H5i4B2i", [(0, 0, 1, 1, 0, 0, 0, 0x1234, 0x5678,
                                 0, -1, -1, -1, 0, 0, 1, 3, 0, -1, -1)])
    a.emit("ii", 1, 1)  # TTransArray owner and one surface
    a.emit("8i4ff2i", -1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, .5, 1, 0)
    a.bulk("2i2f", [(0, -1, .25, .5), (1, -1, .5, .75), (2, -1, .75, 1)])
    a.emit("iiiQQf", 3, 1, -1, 0x0102030405060708, 0x1122334455667788, 2.5)
    a.emit("i", 0)
    a.bulk("i", [(0,), (1,)])
    a.bulk("i", [(0,)])
    a.emit("ii", 1, 0)
    a.bulk("i", [(0,)])
    a.emit("i", 3)
    a.bulk("3f2I4f", [(1, 2, 3, 0x12345678, 0x9ABCDEF0, .25, .5, .75, 1)])
    a.emit("4Ii9I", 1, 2, 3, 4, 1, 0, 1, 0, 1, 2, 3, 4, 5, 6)
    return bytes(a.data)


class GeometryTests(unittest.TestCase):
    def check(self, cls, fixture, *args):
        source = fixture(">", *args)
        converter = Converter(source)
        self.assertTrue(converter.native_tail(cls, 0, len(source)))
        self.assertEqual(bytes(converter.out), fixture("<", *args))

    def test_static_mesh_half_and_full_uvs(self):
        for full in (False, True):
            self.check("StaticMesh", mesh_fixture, full)

    def test_fracture_geometry_and_word_versions(self):
        self.check("FracturedStaticMesh", mesh_fixture, False, True)

    def test_component_lightmap_variants_and_override_colors(self):
        for kind in (0, 1, 2):
            for colors in (False, True):
                self.check("StaticMeshComponent", component_fixture, kind, colors)

    def test_populated_level_maps_opaque_caches_and_dword_colors(self):
        self.check("Level", level_fixture)

    def test_populated_bsp_mixed_node_zone_and_vertex_widths(self):
        self.check("Model", model_fixture)

    def test_all_truncations_rollback_bytes_and_counters(self):
        for cls, source in (("StaticMesh", mesh_fixture(">")),
                            ("FracturedStaticMesh", mesh_fixture(">", False, True)),
                            ("Level", level_fixture(">")),
                            ("Model", model_fixture(">")),
                            ("StaticMeshComponent", component_fixture(">", 1, True))):
            for end in range(len(source)):
                with self.subTest(cls=cls, end=end):
                    converter = Converter(source[:end])
                    self.assertFalse(converter.native_tail(cls, 0, end))
                    self.assertEqual(bytes(converter.out), source[:end])
                    self.assertFalse(converter.stats)

    def test_adjacent_export_and_unknown_trailer_fail_closed(self):
        for end in (len(level_fixture(">")) - 1, len(level_fixture(">")) + 1):
            source = level_fixture(">") + b"AdjacentExport"
            converter = Converter(source)
            self.assertFalse(converter.native_tail("Level", 0, end))
            self.assertEqual(bytes(converter.out), source)

    def test_invalid_counts_refs_flags_and_widths_rollback(self):
        for cls, source, offset, value in (
            ("Level", level_fixture(">"), 4, -1),
            ("Level", level_fixture(">"), 4, 0x7FFFFFFF),
            ("Level", level_fixture(">"), 0, 999),
            ("StaticMeshComponent", component_fixture(">", 0, False), 20, 99),
            ("StaticMesh", mesh_fixture(">"), 56, 7),  # KDOP node element width
        ):
            with self.subTest(cls=cls, offset=offset):
                data = bytearray(source)
                struct.pack_into(">i", data, offset, value)
                converter = Converter(data)
                converter._import_count, converter._export_count = 1, 1
                self.assertFalse(converter.native_tail(cls, 0, len(data)))
                self.assertEqual(converter.out, data)
                self.assertFalse(converter.stats)

    def test_collection_requires_matching_tagged_component_count(self):
        source = struct.pack(">32f", *range(32))
        for count in (None, -1, 1, 2, 3):
            converter = Converter(source)
            converter._native_array_counts = {"StaticMeshComponents": count}
            self.assertEqual(converter.native_tail("StaticMeshCollectionActor", 0, len(source)), count == 2)
            self.assertEqual(bytes(converter.out), struct.pack("<32f", *range(32)) if count == 2 else source)

    def test_dominant_light_shadow_words_precede_uobject_prologue(self):
        source = struct.pack(">i3H6i", 3, 0x1234, 0x5678, 0xABCD, -1, 0, 0, 0, 0, 0)
        converter = Converter(source)
        self.assertTrue(converter.dominant_light_payload(0, len(source), ["None"]))
        self.assertEqual(bytes(converter.out), struct.pack("<i3H6i", 3, 0x1234, 0x5678, 0xABCD, -1, 0, 0, 0, 0, 0))
        for end in range(len(source)):
            converter = Converter(source[:end])
            self.assertFalse(converter.dominant_light_payload(0, end, ["None"]))
            self.assertEqual(bytes(converter.out), source[:end])


if __name__ == "__main__":
    unittest.main()
