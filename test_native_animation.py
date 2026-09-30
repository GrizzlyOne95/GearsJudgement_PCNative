import struct
import unittest

from be2le import Converter
from test_native_geometry import Archive


NAMES = ["AKF_PerTrackCompression", "ACF_Identity", "Bone", "Profile"]


def compressed_track(endian, fmt, flags, frames):
    a = Archive(endian)
    a.emit("I", (fmt << 28) | (flags << 24) | 3)
    component_table = (3, 1, 1, 2, 1, 2, 2, 3)
    components = component_table[flags & 7]
    if fmt == 3:
        a.emit(str(components * 2) + "f", *range(components * 2))
    key_spec = ((4, "f"), (components, "f"), (components, "H"),
                (1, "I"), (1, "I"), (1, "I"), (0, "I"))[fmt]
    for key in range(3):
        count, spec = key_spec
        if count:
            a.emit(str(count) + spec, *[key * 100 + component + 1 for component in range(count)])
    if flags & 8:
        a.data.extend(b"\x55" * (-len(a.data) % 4))
        a.emit("3B" if frames <= 255 else "3H", 0, frames // 2, frames - 1)
    a.data.extend(b"\x55" * (-len(a.data) % 4))
    return bytes(a.data)


def animation_fixture(fmt=2, flags=15, frames=300, raw=False):
    tracks = [compressed_track(">", fmt, flags, frames), compressed_track(">", 1, 7, frames)]
    offsets = [0, -1, len(tracks[0]), -1]
    prefix = struct.pack(">7i", 0, 0, 1, 0, 1, 0, frames)
    prefix += struct.pack(">5i", 4, *offsets)
    properties = {
        "KeyEncodingFormat": ("ByteProperty", "AnimationKeyFormat", 0, 8),
        "TranslationCompressionFormat": ("ByteProperty", "AnimationCompressionFormat", 8, 8),
        "RotationCompressionFormat": ("ByteProperty", "AnimationCompressionFormat", 16, 8),
        "NumFrames": ("IntProperty", None, 24, 4),
        "CompressedTrackOffsets": ("ArrayProperty", None, 28, 20),
    }

    def tail(endian):
        a = Archive(endian)
        a.emit("i", int(raw))
        if raw:
            a.emit("ii3fii4f", 12, 1, 1, 2, 3, 16, 1, 0, 0, 0, 1)
        compressed = compressed_track(endian, fmt, flags, frames) + compressed_track(endian, 1, 7, frames)
        a.emit("i", len(compressed))
        a.data.extend(compressed)
        return bytes(a.data)

    return prefix + tail(">"), len(prefix), prefix + tail("<"), properties


def aim_fixture(endian):
    a = Archive(endian)
    a.emit("ii4fi", 3, 0, -1, 1, -1, 1, 2)
    for bone in range(2):
        a.emit("ii", 2, bone)
        for direction in range(9):
            a.emit("7f", .1, .2, .3, .9, bone + 1, direction + 1, .5)
    for anim in range(9):
        a.emit("ii", 2, anim)
    return bytes(a.data)


class AnimationTests(unittest.TestCase):
    def converter(self, source, properties=None):
        c = Converter(source)
        c._names, c._name_count = NAMES, len(NAMES)
        c._native_property_ranges = properties or {}
        return c

    def test_all_per_track_formats_flags_and_frame_widths(self):
        for fmt in range(7):
            for flags in range(16):
                for frames in (8, 300):
                    with self.subTest(fmt=fmt, flags=flags, frames=frames):
                        source, start, expected, properties = animation_fixture(fmt, flags, frames)
                        c = self.converter(source, properties)
                        self.assertTrue(c.native_tail("AnimSequence", start, len(source)))
                        self.assertEqual(bytes(c.out), expected)
                        self.assertEqual(c.stats["animation_tracks"], 2)
                        self.assertEqual(c.stats["animation_keys"], 6)

    def test_raw_tracks_and_every_truncation_roll_back(self):
        source, start, expected, properties = animation_fixture(raw=True)
        c = self.converter(source, properties)
        self.assertTrue(c.native_tail("AnimSequence", start, len(source)))
        self.assertEqual(bytes(c.out), expected)
        for end in range(start, len(source)):
            c = self.converter(source[:end], properties)
            self.assertFalse(c.native_tail("AnimSequence", start, end))
            self.assertEqual(bytes(c.out), source[:end])
            self.assertFalse(c.stats)

    def test_invalid_offsets_headers_frames_sizes_and_codecs_fail_closed(self):
        source, start, _, properties = animation_fixture()
        # Mutate offsets, frame count, compressed length, header format/key count,
        # the last frame, and the second offset (after a valid first track).
        for offset, spec, value in ((32, "i", -2), (32, "i", 4), (40, "i", 0),
                                    (24, "i", 0), (start + 4, "i", -1),
                                    (start + 8, "I", 0x7F000003),
                                    (start + 8, "I", 0x2F000000),
                                    (start + 32, "H", 300), (0, "i", 1),
                                    (16, "i", 0), (28, "i", 3)):
            with self.subTest(offset=offset, value=value):
                data = bytearray(source)
                struct.pack_into(">" + spec, data, offset, value)
                c = self.converter(data, properties)
                self.assertFalse(c.native_tail("AnimSequence", start, len(data)))
                self.assertEqual(c.out, data)
                self.assertFalse(c.stats)
        for missing in properties:
            c = self.converter(source, {k: v for k, v in properties.items() if k != missing})
            self.assertFalse(c.native_tail("AnimSequence", start, len(source)))
            self.assertEqual(bytes(c.out), source)

    def test_aim_profiles_match_archive_and_every_truncation_rejected(self):
        source = aim_fixture(">")
        c = self.converter(source)
        self.assertEqual(c.binary_struct("AimOffsetProfile", 0, len(source), exact=True), len(source))
        self.assertEqual(bytes(c.out), aim_fixture("<"))
        for end in range(len(source)):
            c = self.converter(source[:end])
            self.assertIsNone(c.binary_struct("AimOffsetProfile", 0, end, exact=True))
            self.assertEqual(bytes(c.out), source[:end])

    def test_later_bad_aim_array_element_restores_earlier_element(self):
        good = aim_fixture(">")
        bad = bytearray(good)
        struct.pack_into(">i", bad, 28, 999)
        source = good + bad
        c = self.converter(source)
        self.assertFalse(c.array_with(NAMES, {"elem": "StructProperty", "struct": "AimOffsetProfile"},
                                      0, len(source), 2, 0))
        self.assertEqual(bytes(c.out), source)
        self.assertFalse(c.stats)


if __name__ == "__main__":
    unittest.main()
