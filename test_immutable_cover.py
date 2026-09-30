import struct
import unittest

from be2le import Converter
from test_native_geometry import Archive


NAMES = ["None", "CT_MidLevel", "CA_LeanLeft", "Position", "StructProperty", "Vector"]


def cover_fixture(endian):
    a = Archive(endian)
    a.emit("i6i6fi2i", -1, 1, 0, 1, 0, 1, 0, 1, 2, 3, 4, 5, 6, 1, 2, 0)
    a.emit("ii", 1, 3)  # one FireLink, three packed interaction bytes
    a.raw(b"\x12\x34\x56")
    a.emit("I2BiIi", 0x12345678, 1, 0, 1, 0xABCDEF12, -1)
    a.emit("i6i", 1, 1, 2, 3, 4, 5, -1)  # SlipRefs, Poly actor/GUID/PolyId
    # BasedPosition's nested tagged FVector, then FName(None).
    a.emit("8i3f2i", 3, 0, 4, 0, 12, 0, 5, 0, 10, 20, 30, 0, 0)
    a.emit("i3i", 17, 1, -1, 0x12345678)  # Direction, OverlapClaimsList
    a.raw(bytes([0, 1] * 10 + [1]))  # 21 independent persistent script bools
    return bytes(a.data)


class ImmutableCoverTests(unittest.TestCase):
    def test_mixed_script_widths_and_nested_tags_match(self):
        source = cover_fixture(">")
        converter = Converter(source)
        converter._name_count = len(NAMES)
        self.assertEqual(converter.binary_struct("CoverSlot", 0, len(source), exact=True, names=NAMES), len(source))
        self.assertEqual(bytes(converter.out), cover_fixture("<"))

    def test_every_cover_truncation_and_unknown_trailer_roll_back(self):
        source = cover_fixture(">")
        for data in ([source[:end] for end in range(len(source))] + [source + b"extra"]):
            converter = Converter(data)
            converter._name_count = len(NAMES)
            self.assertIsNone(converter.binary_struct("CoverSlot", 0, len(data), exact=True, names=NAMES))
            self.assertEqual(bytes(converter.out), data)
            self.assertFalse(converter.stats)

    def test_invalid_script_boolean_and_enum_name_roll_back(self):
        for offset, replacement in ((len(cover_fixture(">")) - 1, b"\x02"),
                                    (4, struct.pack(">i", 999))):
            data = bytearray(cover_fixture(">"))
            data[offset:offset + len(replacement)] = replacement
            converter = Converter(data)
            converter._name_count = len(NAMES)
            self.assertIsNone(converter.binary_struct("CoverSlot", 0, len(data), exact=True, names=NAMES))
            self.assertEqual(converter.out, data)

    def test_bad_second_array_element_restores_first_element_and_counters(self):
        valid = cover_fixture(">")
        data = valid + valid[:-1] + b"\x02"
        converter = Converter(data)
        converter._name_count = len(NAMES)
        candidate = {"elem": "StructProperty", "struct": "CoverSlot"}
        self.assertFalse(converter.array_with(NAMES, candidate, 0, len(data), 2, 0))
        self.assertEqual(bytes(converter.out), data)
        self.assertFalse(converter.stats)

    def test_actor_reference_and_route_array_validate_first_object_ref(self):
        source = struct.pack(">5i", -1, 1, 2, 3, 4)
        converter = Converter(source)
        converter._import_count, converter._export_count = 1, 1
        self.assertEqual(converter.binary_struct("ActorReference", 0, len(source), exact=True), len(source))
        self.assertEqual(bytes(converter.out), struct.pack("<5i", -1, 1, 2, 3, 4))
        data = struct.pack(">5i", 999, 1, 2, 3, 4)
        converter = Converter(data)
        converter._import_count, converter._export_count = 1, 1
        self.assertIsNone(converter.binary_struct("ActorReference", 0, len(data), exact=True))
        self.assertEqual(bytes(converter.out), data)


if __name__ == "__main__":
    unittest.main()
