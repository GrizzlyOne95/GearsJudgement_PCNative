import struct
import unittest

from be2le import Converter


def mesh_fixture(endian, packed=False, full_uvs=False, colors=False):
    """Small independent archive with mixed-width LOD fields and alternate weights."""
    parts = []

    def emit(fmt, *values):
        parts.append(struct.pack(endian + fmt, *values))

    emit("7f", 1, 2, 3, 4, 5, 6, 7)  # bounds
    emit("ii", 1, -1)  # material
    emit("3f3i", 1, 2, 3, 11, 22, 33)
    emit("i", 1)  # bone count
    emit("3i7f3i", 1, 0, 0, 0, 0, 0, 1, 2, 3, 4, 0, 0, 0x12345678)
    emit("ii", 1, 1)  # depth, LOD count
    emit("iHHIIB", 1, 1, 2, 0, 1, 6)  # section
    emit("iBii3H", 1, 2, 2, 3, 0, 0, 0)  # WORD index buffer
    emit("iH", 1, 0)  # active bone
    emit("i", 1)  # chunk
    emit("ii", 0, 0)  # base vertex, rigid count
    emit("i", 1)  # soft vertex count
    emit("15f", *range(15))
    parts.append(bytes([1, 2, 3, 4, 5, 6, 7, 8]))  # CPU bones/weights stay in byte order
    emit("iH3i", 1, 0, 0, 1, 4)
    emit("ii", 128, 1)  # Size, NumVertices
    emit("iB", 1, 0)  # required bone
    emit("4i", 32, 0, 0, -1)  # unused raw-point bulk
    emit("4i6f", 1, 1, int(full_uvs), int(packed), 10, 20, 30, 1, 2, 3)
    stride = 16 + (4 if packed else 12) + (8 if full_uvs else 4)
    emit("ii", stride, 1)
    emit("4I", 0x12345678, 0x11223344, 0x01020304, 0x05060708)
    if packed:
        emit("I", 0x123ABCDE)
    else:
        emit("3f", 1.25, -2.5, 3.75)
    if full_uvs:
        emit("2f", .25, .75)
    else:
        emit("2H", 0x3400, 0x3A00)
    if colors:
        emit("iiI", 4, 1, 0x12345678)
    emit("i", 1)  # alternate influences
    emit("i2I", 1, 0x05060708, 0x01020304)
    emit("i2ii2I", 1, 1, 2, 2, 0, 7)  # mapping: bone pair -> indices
    emit("3iB", 0, 0, 0, 1)  # sections, chunks, required bones, usage
    emit("i3i", 1, 1, 0, 0)  # NameIndexMap
    emit("i", 1)  # KDOP count
    emit("6f", -1, -2, -3, 1, 2, 3)
    emit("ii6B", 6, 1, 1, 2, 3, 4, 5, 6)
    emit("ii4H", 8, 1, 0, 0, 0, 2)
    emit("i3f", 1, 1, 2, 3)  # collision vertex
    emit("ii", 1, 5)
    parts.append(b"Bone\0")
    emit("iB", 1, 2)  # bone break option
    emit("ii", 1, -1)  # ClothingAssets
    emit("i4f", 4, 1, 2, 3, 4)  # streaming factors
    return b"".join(parts)


class SkeletalMeshTests(unittest.TestCase):
    def test_all_gpu_formats_and_colors_match_independent_little_endian_fixture(self):
        for packed in (False, True):
            for full_uvs in (False, True):
                for colors in (False, True):
                    with self.subTest(packed=packed, full_uvs=full_uvs, colors=colors):
                        source = mesh_fixture(">", packed, full_uvs, colors)
                        converter = Converter(source)
                        converter._skeletal_mesh_has_vertex_colors = colors
                        self.assertTrue(converter.native_tail("SkeletalMesh", 0, len(source)))
                        self.assertEqual(bytes(converter.out), mesh_fixture("<", packed, full_uvs, colors))

    def test_truncated_mesh_rolls_back_every_byte_and_counter(self):
        source = mesh_fixture(">", packed=True)
        for length in range(len(source)):
            with self.subTest(length=length):
                converter = Converter(source[:length])
                self.assertFalse(converter.native_tail("SkeletalMesh", 0, length))
                self.assertEqual(bytes(converter.out), source[:length])
                self.assertFalse(converter.stats)

    def test_mesh_cannot_consume_bytes_from_adjacent_export(self):
        source = mesh_fixture(">")
        converter = Converter(source + source)
        self.assertFalse(converter.native_tail("SkeletalMesh", 0, len(source) - 1))
        self.assertEqual(bytes(converter.out), source + source)

    def test_unknown_trailer_fails_closed(self):
        source = mesh_fixture(">") + b"unknown"
        converter = Converter(source)
        self.assertFalse(converter.native_tail("SkeletalMesh", 0, len(source)))
        self.assertEqual(bytes(converter.out), source)

    def test_negative_and_excessive_counts_fail_closed(self):
        for count in (-1, 0x7FFFFFFF):
            source = bytearray(mesh_fixture(">"))
            struct.pack_into(">i", source, 28, count)  # Materials count
            converter = Converter(source)
            self.assertFalse(converter.native_tail("SkeletalMesh", 0, len(source)))
            self.assertEqual(converter.out, source)

    def test_wrong_bulk_stride_is_rejected_even_when_other_fields_fit(self):
        source = bytearray(mesh_fixture(">", packed=True))
        header = source.index(struct.pack(">ii4I", 24, 1, 0x12345678, 0x11223344, 0x01020304, 0x05060708))
        struct.pack_into(">i", source, header, 32)
        converter = Converter(source)
        self.assertFalse(converter.native_tail("SkeletalMesh", 0, len(source)))
        self.assertEqual(converter.out, source)

    def test_bool_tags_supply_native_color_flag(self):
        source = struct.pack(">6iB2i", 1, 0, 2, 0, 0, 0, 1, 0, 0)
        converter = Converter(source)
        properties = {}
        self.assertEqual(converter.tags(["None", "bHasVertexColors", "BoolProperty"],
                                        0, len(source), bool_properties=properties), len(source))
        self.assertEqual(properties, {"bHasVertexColors": True})


if __name__ == "__main__":
    unittest.main()
