"""Independent BE/LE numeric comparison of retained animation/combat data."""
import collections
import hashlib
import json
from pathlib import Path
import struct
import sys
import re

FIXTURES = Path(r"C:\Games\_judgment-scratch\e2-surface")
ARTIFACT = "SP_E2_02_S.animation-v1-20260930.le.xxx"


def tags(blob, start, end, endian, names):
    properties = {}
    pos = start
    while pos < end:
        name, number = struct.unpack_from(endian + "2i", blob, pos)
        assert 0 <= name < len(names) and number >= 0
        if names[name] == "None":
            return properties, pos + 8
        name, _, kind, _, size, index = struct.unpack_from(endian + "6i", blob, pos)
        assert size >= 0 and index >= 0
        value = pos + 24
        if names[kind] in ("StructProperty", "ByteProperty"):
            value += 8
        elif names[kind] == "BoolProperty":
            value += 1
        assert value + size <= end
        properties[names[name]] = (names[kind], value, size)
        pos = value + size
    raise AssertionError("unterminated property stream")


def parse_animation(blob, tail, end, endian, properties):
    pos = tail

    def read(fmt):
        nonlocal pos
        size = struct.calcsize("=" + fmt)
        assert pos + size <= end
        result = struct.unpack_from(endian + fmt, blob, pos)
        pos += size
        return result

    raw_count, = read("i")
    raw = []
    for _ in range(raw_count):
        fields = []
        for width, components in ((12, 3), (16, 4)):
            stride, count = read("2i")
            assert stride == width and count >= 0
            fields.append([read(str(components) + "I") for _ in range(count)])
        raw.append(fields)
    length, = read("i")
    base = pos
    assert length == end - base
    _, frames_pos, _ = properties["NumFrames"]
    frames, = struct.unpack_from(endian + "i", blob, frames_pos)
    _, offsets_pos, offsets_size = properties["CompressedTrackOffsets"]
    count, = struct.unpack_from(endian + "i", blob, offsets_pos)
    assert count % 2 == 0 and offsets_size == 4 + count * 4
    offsets = struct.unpack_from(endian + str(count) + "i", blob, offsets_pos + 4)
    tracks = []
    formats = collections.Counter()
    total_keys = 0
    frame_tables = 0
    for offset in offsets:
        if offset == -1:
            tracks.append(None)
            continue
        assert offset == pos - base and offset % 4 == 0
        header, = read("I")
        format_, flags, num_keys = header >> 28, header >> 24 & 15, header & 0xFFFFFF
        components = (3, 1, 1, 2, 1, 2, 2, 3)[flags & 7]
        assert 0 < num_keys <= frames
        bounds = read(str(components * 2) + "I") if format_ == 3 else ()
        key_format = (("4I", str(components) + "I", str(components) + "H",
                       "I", "I", "I", ""))[format_]
        keys = [read(key_format) for _ in range(num_keys)]
        padding = []
        if flags & 8:
            padding.append(read(str(-(pos - base) % 4) + "B"))
            table = read(str(num_keys) + ("B" if frames <= 255 else "H"))
            assert list(table) == sorted(table) and max(table) < frames
            frame_tables += 1
        else:
            table = ()
        padding.append(read(str(-(pos - base) % 4) + "B"))
        tracks.append((header, bounds, keys, table, padding))
        formats[format_] += 1
        total_keys += num_keys
    assert pos == end
    result = {"frames": frames, "raw": raw, "offsets": offsets, "tracks": tracks}
    stats = {"tracks": sum(t is not None for t in tracks), "keys": total_keys,
             "frame_tables": frame_tables, "formats": dict(formats)}
    return result, stats


def parse_profile(blob, start, end, endian):
    pos = start

    def read(fmt):
        nonlocal pos
        size = struct.calcsize("=" + fmt)
        assert pos + size <= end
        result = struct.unpack_from(endian + fmt, blob, pos)
        pos += size
        return result

    count, = read("i")
    profiles = []
    for _ in range(count):
        profile = [read("2i4I")]
        bones, = read("i")
        profile.append([(read("2i"), read("63I")) for _ in range(bones)])
        profile.append(read("18i"))
        profiles.append(profile)
    assert pos == end
    return profiles


def validate(runtime_log=None):
    source = (FIXTURES / "SP_E2_02_S.xxx.unc").read_bytes()
    output = (FIXTURES / ARTIFACT).read_bytes()
    metadata = json.loads((FIXTURES / "SP_E2_02_S.xxx.json").read_text())
    names = [item["name"] for item in metadata["names"]]
    rows, combat_rows, aim_rows = [], [], []
    for export in metadata["exports"]:
        off, size = export["serial_offset"], export["serial_size"]
        end = off + size
        if export["class_name"] in ("AnimSequence", "CombatZone"):
            flags = int(export["object_flags"], 16)
            start = off + 4
            if flags & 0x0200000000000000:
                node, = struct.unpack_from(">i", source, off)
                start += 18 + (4 if node else 0)
            props, tail = tags(source, start, end, ">", names)
            le_props, le_tail = tags(output, start, end, "<", names)
            assert (props, tail) == (le_props, le_tail)
            if export["class_name"] == "AnimSequence":
                original, stats = parse_animation(source, tail, end, ">", props)
                converted, le_stats = parse_animation(output, tail, end, "<", le_props)
                assert original == converted and stats == le_stats
                rows.append({"object": export["object_name"], "export": export["index"], **stats})
            else:
                count, = struct.unpack_from(">i", source, tail)
                assert tail + 4 + count * 28 == end
                assert struct.unpack_from(">" + str(1 + count * 7) + "i", source, tail) == \
                       struct.unpack_from("<" + str(1 + count * 7) + "i", output, tail)
                combat_rows.append({"object": export["object_name"], "polys": count})
        if export["class_name"] == "GearAnim_AimOffset":
            props, _ = tags(source, off + 4, end, ">", names)
            if "Profiles" in props:
                _, start, size = props["Profiles"]
                original = parse_profile(source, start, start + size, ">")
                assert original == parse_profile(output, start, start + size, "<")
                aim_rows.append({"object": export["object_name"], "profiles": len(original),
                                 "bones": sum(len(p[1]) for p in original)})
    assert len(rows) == 28 and len(combat_rows) == 4 and len(aim_rows) == 1
    report = {"artifact": ARTIFACT, "sha256": hashlib.sha256(output).hexdigest().upper(),
            "animations": rows, "combat_zones": combat_rows, "aim_profiles": aim_rows,
            "totals": {"sequences": len(rows), "tracks": sum(r["tracks"] for r in rows),
                       "keys": sum(r["keys"] for r in rows),
                       "frame_tables": sum(r["frame_tables"] for r in rows),
                       "combat_polys": sum(r["polys"] for r in combat_rows)}}
    if runtime_log:
        log = Path(runtime_log).read_text(errors="replace")
        observed = re.findall(r"\[JUDGANIM\] poses obj=(\S+) tracks=(\d+) samples=(\d+) finite=(\d+)", log)
        expected = {e["object_name"] for e in metadata["exports"] if e["class_name"] == "AnimSequence"}
        assert len(observed) == len(expected) == 28
        assert {re.split(r"[.:]", row[0])[-1] for row in observed} == expected
        assert all(int(row[1]) == 79 and int(row[2]) == 237 and row[3] == "1" for row in observed)
        report["runtime_pose_samples"] = sum(int(row[2]) for row in observed)
        report["runtime_all_sampled_poses_finite"] = True
    return report


if __name__ == "__main__":
    report = validate(sys.argv[2] if len(sys.argv) > 2 else None)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURES / "animation-20260930.validation.json"
    with path.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report["totals"]))
    print(path)
