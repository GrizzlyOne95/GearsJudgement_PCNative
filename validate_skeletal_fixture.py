"""Verify the real SP_E2_P fixture and compare native packed-position telemetry."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from be2le import Converter, load_array_types
from skeletal_mesh import SkeletalMeshWalker

FIXTURES = Path(r"C:\Games\_judgment-scratch\e2-surface")
SOURCE = FIXTURES / "SP_E2_P.xxx.unc"
OUTPUT = FIXTURES / "SP_E2_P.skeletalmesh-20260930.le.xxx"
PREVIOUS = FIXTURES / "SP_E2_P.shadercache.le.xxx"
MANIFEST = FIXTURES / "SP_E2_P.skeletalmesh-20260930.manifest.json"


class RecordingWalker(SkeletalMeshWalker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lods = []

    def gpu_vertices(self, lod_uvs, lod_vertices):
        pos = self.pos
        source = self.converter.src
        uvs, full, packed = struct.unpack_from(">iii", source, pos)
        extension = struct.unpack_from(">3f", source, pos + 12)
        origin = struct.unpack_from(">3f", source, pos + 24)
        stride, count = struct.unpack_from(">ii", source, pos + 36)
        row = {"uvs": uvs, "full_precision_uvs": bool(full), "packed": bool(packed),
               "stride": stride, "vertices": count}
        if count and packed:
            word = struct.unpack_from(">I", source, pos + 60)[0]
            # PC signed 11:11:10 bitfields; independently decode the source DWORD.
            components = []
            for bits, shift, divisor in ((11, 0, 1023), (11, 11, 1023), (10, 22, 511)):
                value = (word >> shift) & ((1 << bits) - 1)
                if value & (1 << (bits - 1)):
                    value -= 1 << bits
                components.append(value / divisor)
            row["first_decoded_position"] = [components[i] * extension[i] + origin[i] for i in range(3)]
        super().gpu_vertices(lod_uvs, lod_vertices)
        self.lods.append(row)


def validate(runtime_log=None):
    source = SOURCE.read_bytes()
    output = OUTPUT.read_bytes()
    previous = PREVIOUS.read_bytes()
    assert len(source) == len(output) == len(previous), "package size changed"
    converter = Converter(source, load_array_types(r"C:\Games\_judgment-scratch\array-types-v845.json")[0])
    names = converter.read_names()
    imports = converter.read_import_class_names(names)
    converter.summary()
    exports = converter.tables()
    converter.payloads(exports, names, lambda index: imports[-index - 1] if index < 0 else ("Class" if index == 0 else "?"))
    assert converter.stats["converted"] == 1433
    assert not converter.unsupported
    assert converter.out == output, "stored artifact differs from current converter"
    manifest = json.loads(MANIFEST.read_text())
    validation = manifest["layout_validation"]
    assert manifest["byte_order"] == "little" and manifest["package_version"] == 845
    assert validation["invalid_name_references"] == 0
    assert validation["invalid_resource_or_serial_references"] == 0
    assert validation["texture2d_payloads_structurally_valid"] == 24
    assert validation["sound_node_wave_payloads_structurally_valid"] == 254
    rows = []
    ranges = []
    for entry in manifest["exports"]:
        if entry["class_name"] != "SkeletalMesh":
            continue
        start, size = entry["serial_offset"], entry["serial_size"]
        tail_converter = Converter(source)
        flags = {}
        tail = tail_converter.tags(names, start + 4, start + size, bool_properties=flags)
        assert tail is not None
        walker = RecordingWalker(tail_converter, tail, start + size, flags.get("bHasVertexColors", False))
        assert walker.walk() == start + size, "mesh tail does not close exactly"
        assert tail_converter.out[tail:start + size] == output[tail:start + size]
        ranges.append((tail, start + size))
        rows.append({"name": entry["object_name"], "export": entry["index"], "serial_size": size,
                     "tail_start": tail, "lods": walker.lods})
    assert len(rows) == 3
    position = 0
    for start, end in sorted(ranges):
        assert previous[position:start] == output[position:start], "changed bytes outside skeletal-mesh tails"
        position = end
    assert previous[position:] == output[position:]
    packed = [lod for row in rows for lod in row["lods"] if lod["packed"]]
    assert len(packed) == 4
    report = {"source_sha256": hashlib.sha256(source).hexdigest(),
              "output_sha256": hashlib.sha256(output).hexdigest(), "bytes": len(output),
              "converted_exports": 1433, "unsupported": 0, "changed_only_mesh_tails": True,
              "meshes": rows}
    if runtime_log:
        log = Path(runtime_log).read_text(errors="replace")
        observed = re.findall(r"\[JUDGMESH\] unpacked vertices=(\d+) texcoords=(\d+) first=\(([^)]+)\)", log)
        assert len(observed) == len(packed), "unexpected native unpack count"
        for actual, expected in zip(observed, packed):
            count, uvs, first = actual
            assert int(count) == expected["vertices"] and int(uvs) == expected["uvs"]
            values = [float(value) for value in first.split(",")]
            assert all(abs(a - b) < 0.0001 for a, b in zip(values, expected["first_decoded_position"])), "native position disagrees with independent decoding"
        report["runtime_packed_positions_match"] = True
    return report


if __name__ == "__main__":
    print(json.dumps(validate(sys.argv[1] if len(sys.argv) > 1 else None), indent=2))
