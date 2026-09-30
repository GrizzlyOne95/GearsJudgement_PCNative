"""Verify retained geometry archives, BSP reference topology, and native load telemetry."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from be2le import Converter, load_array_types

FIXTURES = Path(r"C:\Games\_judgment-scratch\e2-surface")
ARRAY_TYPES = Path(r"C:\Games\_judgment-scratch\array-types-v845.json")
PACKAGES = {
    "SP_E2_P": ("SP_E2_P.geometry-20260930.le.xxx", 1433),
    "SP_E2_01": ("SP_E2_01.geometry-v3-20260930.le.xxx", 4919),
    "SP_E2_02": ("SP_E2_02.geometry-assessment-20260930.le.xxx", 3054),
    "SP_E2_W": ("SP_E2_W.dominantlight-20260930.le.xxx", 61),
    "SP_E2_01_S": ("SP_E2_01_S.navigation-20260930.le.xxx", 560),
    "SP_E2_Audio": ("SP_E2_Audio.navigation-assessment-20260930.le.xxx", 8),
    "SP_E2_02_S": ("SP_E2_02_S.animation-v1-20260930.le.xxx", 2669),
}


def bsp_topology(source, tail, end, endian):
    """Independent numeric parser for fields dereferenced in BuildRenderData."""
    position = tail + 28

    def unpack(fmt):
        nonlocal position
        size = struct.calcsize("=" + fmt)
        assert position + size <= end
        value = struct.unpack_from(endian + fmt, source, position)
        position += size
        return value

    def bulk(fmt):
        width, count = unpack("2i")
        assert width == struct.calcsize("=" + fmt) and count >= 0
        assert position + count * width <= end
        return [unpack(fmt) for _ in range(count)]

    bulk("3f")  # Vectors
    points = bulk("3f")
    nodes = bulk("4f3i2H5i4B2i")
    _, surfaces = unpack("2i")
    assert surfaces >= 0
    position += surfaces * 60
    verts = bulk("2i2f")
    referenced_vertices = set()
    for node in nodes:
        vert_start, surface, num_verts = node[4], node[5], node[16]
        assert 0 <= surface < surfaces
        assert 0 <= vert_start <= len(verts) and vert_start + num_verts <= len(verts)
        referenced_vertices.update(range(vert_start, vert_start + num_verts))
    assert all(0 <= verts[index][0] < len(points) for index in referenced_vertices)
    return {"points": len(points), "nodes": len(nodes), "surfaces": surfaces,
            "vertices": len(verts), "vertex_point_indices": [v[0] for v in verts],
            "node_ranges": [[n[4], n[5], n[16]] for n in nodes],
            "referenced_vertices": len(referenced_vertices),
            "unused_vertices_with_stale_point_indices": sum(
                i not in referenced_vertices and not 0 <= v[0] < len(points) for i, v in enumerate(verts))}


def validate(runtime_log=None):
    rows = []
    for package, (filename, count) in PACKAGES.items():
        source = (FIXTURES / (package + ".xxx.unc")).read_bytes()
        output = (FIXTURES / filename).read_bytes()
        manifest = json.loads((FIXTURES / filename.replace(".le.xxx", ".manifest.json")).read_text())
        converter = Converter(source, load_array_types(ARRAY_TYPES)[0])
        names = converter.read_names()
        imports = converter.read_import_class_names(names)
        converter.summary()
        exports = converter.tables()
        converter.payloads(exports, names, lambda i: imports[-i - 1] if i < 0 else ("Class" if i == 0 else "?"))
        assert len(source) == len(output) and converter.out == output
        assert converter.stats["converted"] == count and not converter.unsupported
        assert manifest["package_version"] == 845 and manifest["byte_order"] == "little"
        layout = manifest["layout_validation"]
        assert layout["imports_end"] == layout["expected_imports_end"]
        assert layout["exports_end"] == layout["expected_exports_end"]
        assert layout["invalid_name_references"] == layout["invalid_resource_or_serial_references"] == 0
        for name in ("texture2d", "sound_node_wave"):
            assert layout[name + "_payloads_checked"] == layout[name + "_payloads_structurally_valid"]
        models = []
        for entry in manifest["exports"]:
            if entry["class_name"] != "Model":
                continue
            start = entry["serial_offset"]
            end = start + entry["serial_size"]
            tag_converter = Converter(source)
            tail = tag_converter.tags(names, start + 4, end)
            assert tail is not None
            topology = bsp_topology(source, tail, end, ">")
            assert topology == bsp_topology(output, tail, end, "<")
            models.append({"name": entry["object_name"], "path": entry["object_path"].split(".le.", 1)[1],
                           "export": entry["index"], **topology})
        row = {"package": package, "converted_exports": count, "unsupported": 0,
               "bytes": len(output), "sha256": hashlib.sha256(output).hexdigest(),
               "bsp_models": models}
        if runtime_log:
            log = Path(runtime_log).read_text(errors="replace")
            runtime_package = "Judgment_" + package if package == "SP_E2_P" else package
            entries = re.findall(r"\[JUDGPRELOAD\] enter exp=(\d+) obj=(\S+) cls=(\S+) off=(\d+) size=(\d+) end=(\d+) pkg=" + re.escape(runtime_package) + r"(?:\s|$)", log)
            leaves = re.findall(r"\[JUDGPRELOAD\] leave exp=(\d+) obj=(\S+) consumed=(\d+) size=(\d+) pkg=" + re.escape(runtime_package) + r"(?:\s|$)", log)
            assert entries and len(entries) == len(leaves)
            assert len(set(e[0] for e in leaves)) == len(leaves)
            by_index = {entry["index"]: entry for entry in manifest["exports"]}
            for index, name, cls, offset, size, end in entries:
                entry = by_index[int(index)]
                assert entry["object_name"] == name and entry["class_name"] == cls
                assert entry["serial_offset"] == int(offset) and entry["serial_size"] == int(size)
                assert int(end) == int(offset) + int(size)
            assert all(consumed == size and int(size) == by_index[int(index)]["serial_size"]
                       for index, _, consumed, size in leaves)
            for model in models:
                runtime_path = runtime_package + "." + model["path"].replace("TheWorld.PersistentLevel", "TheWorld:PersistentLevel")
                pattern = r"\[JUDGMODEL\] expanded vertices=(\d+) disk-stride=16 pc-stride=24 model=" + re.escape(runtime_path) + r"(?:\s|$)"
                actual = re.findall(pattern, log)
                assert actual == [str(model["vertices"])]
            row["runtime_exact_loads"] = len(leaves)
            row["runtime_bsp_stride_expansion_matches"] = True
        rows.append(row)
    return {"packages": rows, "warning": "Headless framing/topology validation; pixel detiling, codecs, physics and visible gameplay are not established."}


if __name__ == "__main__":
    report = validate(sys.argv[1] if len(sys.argv) > 1 else None)
    destination = Path(sys.argv[2]) if len(sys.argv) > 2 else FIXTURES / "geometry-20260930.validation.json"
    if destination.exists():
        raise SystemExit("refusing to replace retained validation evidence")
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(destination), "packages": [
        {k: v for k, v in row.items() if k != "bsp_models"} for row in report["packages"]]}, indent=2))
