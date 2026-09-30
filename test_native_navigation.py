import struct
import unittest

from be2le import Converter
from native_navigation import NavigationWalker
from test_native_geometry import Archive


EDGE_NAMES = sorted(NavigationWalker.BASE_EDGES | NavigationWalker.CROSS_EDGES)


def navigation_fixture(endian):
    a = Archive(endian)
    a.emit("3i", 43, 43, 1)
    a.emit("3fiH", 1, 2, 3, 1, 0)
    a.emit("i", len(EDGE_NAMES))
    for index, name in enumerate(EDGE_NAMES):
        a.emit("IHii", index * 128, 128, index, 0)
    a.emit("iiHiH6f6fBi6If", 1, 1, 0, 1, 0, 1, 2, 3, 0, 0, 1,
           *range(1, 7), 1, 1, 0, 1, 2, 3, 4, 5, 6)
    a.emit("32f", *range(32))
    a.emit("i3H6fB", 1, 0, 0, 0, *range(1, 7), 1)
    for name in EDGE_NAMES:
        cross = name in NavigationWalker.CROSS_EDGES
        a.emit("4H" if cross else "2H", *([0] * (4 if cross else 2)))
        a.emit("2H4f2B3f", 0, 0, .5, 1, 2, 3, 1, 2, 4, 5, 6)
        if cross:
            a.emit("12iH", 1, 2, 3, 4, 5, -1, -1, 6, 7, 8, 9, -1, 0x1234)
        if name in NavigationWalker.SPECIAL_EDGES:
            a.emit("7i3fi", 1, 2, 3, 4, 5, 6, -1, 1, 2, 3, 7)
        elif name == "FNavMeshDropDownEdge":
            a.emit("f", 10.5)
        elif name == "FNavMeshPathObjectEdge":
            a.emit("6i", -1, 1, 2, 3, 4, 99)
    return bytes(a.data)


class NavigationTests(unittest.TestCase):
    def converter(self, source):
        converter = Converter(source)
        converter._names = EDGE_NAMES
        converter._name_count = len(EDGE_NAMES)
        return converter

    def test_all_native_edge_classes_match_independent_archive(self):
        source = navigation_fixture(">")
        converter = self.converter(source)
        self.assertTrue(converter.native_tail("NavigationMeshBase", 0, len(source)))
        self.assertEqual(bytes(converter.out), navigation_fixture("<"))
        self.assertEqual(converter.stats["navigation_edges"], len(EDGE_NAMES))

    def test_every_navigation_truncation_rolls_back(self):
        source = navigation_fixture(">")
        for end in range(len(source)):
            converter = self.converter(source[:end])
            self.assertFalse(converter.native_tail("NavigationMeshBase", 0, end))
            self.assertEqual(bytes(converter.out), source[:end])
            self.assertFalse(converter.stats)

    def test_unknown_version_edge_class_and_count_rejected(self):
        source = navigation_fixture(">")
        for offset, value in ((0, 44), (8, -1), (8, 0x7FFFFFFF), (40, 999)):
            with self.subTest(offset=offset):
                data = bytearray(source)
                struct.pack_into(">i", data, offset, value)
                converter = self.converter(data)
                self.assertFalse(converter.native_tail("NavigationMeshBase", 0, len(data)))
                self.assertEqual(converter.out, data)

    def test_pylon_exact_persistent_refs_and_boundaries(self):
        source = struct.pack(">2i", 1, -1)
        converter = Converter(source)
        converter._import_count, converter._export_count = 1, 1
        self.assertTrue(converter.native_tail("Pylon", 0, len(source)))
        self.assertEqual(bytes(converter.out), struct.pack("<2i", 1, -1))
        for data in (source[:-1], source + b"dynamic", struct.pack(">2i", 999, -1)):
            converter = Converter(data)
            converter._import_count, converter._export_count = 1, 1
            self.assertFalse(converter.native_tail("Pylon", 0, len(data)))
            self.assertEqual(bytes(converter.out), data)


if __name__ == "__main__":
    unittest.main()
