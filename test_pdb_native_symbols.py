"""Synthetic MSF/CodeView boundaries; contains no original game/PDB bytes."""
import struct
import unittest

from pdb_native_symbols import MsfFile, SymbolFormatError, native_symbols, read_public_records


def msf(streams, bs=512):
    sizes = [0xFFFFFFFF if s is None else len(s) for s in streams]
    counts = [0 if s is None else (len(s) + bs - 1) // bs for s in streams]
    directory_size = 4 + 4 * len(streams) + 4 * sum(counts)
    directory_count = (directory_size + bs - 1) // bs
    map_count = (directory_count * 4 + bs - 1) // bs
    directory_pages = list(range(3 + map_count, 3 + map_count + directory_count))
    next_page = directory_pages[-1] + 1
    pages = []
    for count in counts:
        pages.append(list(range(next_page, next_page + count)))
        next_page += count
    result = bytearray(next_page * bs)
    result[:32] = MsfFile.MAGIC
    struct.pack_into("<6I", result, 32, bs, 1, next_page, directory_size, 0, 3)
    struct.pack_into(f"<{directory_count}I", result, bs * 3, *directory_pages)
    directory = struct.pack("<I", len(streams)) + struct.pack(f"<{len(sizes)}I", *sizes)
    directory += b"".join(struct.pack(f"<{len(p)}I", *p) for p in pages)
    for i, page in enumerate(directory_pages):
        chunk = directory[i * bs:(i + 1) * bs]
        result[page * bs:page * bs + len(chunk)] = chunk
    for stream, blocks in zip(streams, pages):
        if stream is None:
            continue
        for i, page in enumerate(blocks):
            chunk = stream[i * bs:(i + 1) * bs]
            result[page * bs:page * bs + len(chunk)] = chunk
    return bytes(result)


def public(name=b"?GetInstance@Test@@", address=32, segment=1):
    payload = struct.pack("<HIIH", 0x110E, 2, address, segment) + name + b"\0"
    return struct.pack("<H", len(payload)) + payload


def pdb_fixture(record=None, dbi_change=None):
    dbi = bytearray(64)
    struct.pack_into("<iII", dbi, 0, -1, 19990903, 7)
    struct.pack_into("<H", dbi, 20, 4)
    struct.pack_into("<i", dbi, 48, 12)
    if dbi_change:
        dbi_change(dbi)
    dbi += struct.pack("<6H", *([0xFFFF] * 5 + [5]))
    section = bytearray(40)
    section[:8] = b".text\0\0\0"
    struct.pack_into("<4I", section, 8, 2048, 0x1000, 2048, 512)
    info = struct.pack("<III", 20000404, 0, 7) + bytes(range(16))
    return msf([b"", info, b"", dbi, public() if record is None else record, section])


class MsfTests(unittest.TestCase):
    def test_multiblock_stream_and_empty_absent(self):
        source = b"abc" * 600
        doc = MsfFile(msf([source, b"", None]))
        self.assertEqual(doc.stream(0), source)
        self.assertEqual(doc.stream(1), b"")
        with self.assertRaises(SymbolFormatError):
            doc.stream(2)
        with self.assertRaises(SymbolFormatError):
            doc.stream(3)

    def test_directory_map_spans_multiple_blocks(self):
        streams = [b""] * 25000
        streams[-1] = b"last stream beyond the first map block"
        blob = msf(streams)
        directory_size = struct.unpack_from("<I", blob, 44)[0]
        self.assertGreater(((directory_size + 511) // 512) * 4, 512)
        self.assertEqual(MsfFile(blob).stream(24999), streams[-1])

    def test_reordered_data_blocks(self):
        blob = bytearray(msf([b"a" * 512 + b"b" * 512]))
        directory_page = struct.unpack_from("<I", blob, 3 * 512)[0]
        a, b = struct.unpack_from("<2I", blob, directory_page * 512 + 8)
        struct.pack_into("<2I", blob, directory_page * 512 + 8, b, a)
        self.assertEqual(MsfFile(bytes(blob)).stream(0), b"b" * 512 + b"a" * 512)

    def test_bad_magic_and_truncated_header(self):
        for blob in (b"", b"random", MsfFile.MAGIC):
            with self.subTest(size=len(blob)), self.assertRaises(SymbolFormatError):
                MsfFile(blob)

    def test_bad_block_size_length_reserved_and_directory_size(self):
        for offset, value in [(32, 0), (40, 9999), (44, 0), (48, 1), (52, 9999)]:
            blob = bytearray(msf([b"abc"]))
            struct.pack_into("<I", blob, offset, value)
            with self.subTest(offset=offset), self.assertRaises(SymbolFormatError):
                MsfFile(bytes(blob))

    def test_directory_block_outside_file(self):
        blob = bytearray(msf([b"abc"]))
        struct.pack_into("<I", blob, 3 * 512, len(blob) // 512)
        with self.assertRaises(SymbolFormatError):
            MsfFile(bytes(blob))

    def test_bad_stream_count_and_stream_size(self):
        for offset in (0, 4):
            blob = bytearray(msf([b"abc"]))
            directory_page = struct.unpack_from("<I", blob, 3 * 512)[0]
            struct.pack_into("<I", blob, directory_page * 512 + offset, 999999)
            with self.subTest(offset=offset), self.assertRaises(SymbolFormatError):
                MsfFile(bytes(blob))

    def test_duplicate_and_invalid_stream_blocks(self):
        for invalid in (True, False):
            blob = bytearray(msf([b"a" * 1024]))
            directory_page = struct.unpack_from("<I", blob, 3 * 512)[0]
            first = struct.unpack_from("<I", blob, directory_page * 512 + 8)[0]
            struct.pack_into("<I", blob, directory_page * 512 + 12,
                             len(blob) // 512 if invalid else first)
            with self.subTest(invalid=invalid), self.assertRaises(SymbolFormatError):
                MsfFile(bytes(blob))

    def test_unconsumed_directory_bytes(self):
        blob = bytearray(msf([b"abc"]))
        size = struct.unpack_from("<I", blob, 44)[0]
        struct.pack_into("<I", blob, 44, size + 4)
        with self.assertRaises(SymbolFormatError):
            MsfFile(bytes(blob))


class PublicSymbolTests(unittest.TestCase):
    def test_symbol_rva_section_and_filter(self):
        report = native_symbols(pdb_fixture(), "GetInstance")
        self.assertEqual(report["symbols"][0]["rva"], 0x1020)
        self.assertEqual(report["total_publics"], 1)
        self.assertEqual(report["dbi_age"], 7)
        self.assertEqual(report["pdb_guid"], "03020100-0504-0706-0809-0a0b0c0d0e0f")
        self.assertEqual(native_symbols(pdb_fixture(), "absent")["symbols"], [])

    def test_unknown_records_do_not_desynchronize(self):
        record = struct.pack("<HH", 6, 0x1000) + b"abcd" + public()
        self.assertEqual(len(read_public_records(record, 1)), 1)

    def test_invalid_record_lengths_and_names(self):
        for record in (b"x", b"\0\0\0\0", public()[:-1],
                       struct.pack("<HH", 2, 0x110E), public(name=b""),
                       public(name=b"\xff")):
            with self.subTest(record=record[:10]), self.assertRaises(SymbolFormatError):
                read_public_records(record, 1)

    def test_no_nul_terminator(self):
        record = public()[:-1] + b"x"
        with self.assertRaises(SymbolFormatError):
            read_public_records(record, 1)

    def test_invalid_sections(self):
        for segment in (0, 2, 0xFFFF):
            with self.subTest(segment=segment), self.assertRaises(SymbolFormatError):
                read_public_records(public(segment=segment), 1)

    def test_symbol_outside_selected_section(self):
        with self.assertRaises(SymbolFormatError):
            native_symbols(pdb_fixture(public(address=2048)))

    def test_dbi_header_and_substream_boundaries(self):
        for offset, fmt, value in [(0, "<i", 0), (4, "<I", 0), (24, "<i", -1),
                                   (24, "<i", 100000), (48, "<i", 10),
                                   (48, "<i", 13), (20, "<H", 900)]:
            blob = pdb_fixture(dbi_change=lambda b: struct.pack_into(fmt, b, offset, value))
            with self.subTest(offset=offset, value=value), self.assertRaises(SymbolFormatError):
                native_symbols(blob)

    def test_pdb_identity_is_required_and_ages_match(self):
        with self.assertRaises(SymbolFormatError):
            native_symbols(msf([b"", b"", b"", bytes(64)]))
        with self.assertRaises(SymbolFormatError):
            native_symbols(pdb_fixture(dbi_change=lambda b: struct.pack_into("<I", b, 8, 8)))


if __name__ == "__main__":
    unittest.main()
