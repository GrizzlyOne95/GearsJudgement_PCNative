"""Independent source/converted comparison of all v43 navigation records."""
import collections
import hashlib
import json
from pathlib import Path
import struct
import sys

from be2le import Converter

FIXTURES = Path(r"C:\Games\_judgment-scratch\e2-surface")
BASE = {"FNavMeshEdgeBase", "FNavMeshBasicOneWayEdge"}
SPECIAL = {"FNavMeshSpecialMoveEdge", "FNavMeshMantleEdge", "FNavMeshCoverSlipEdge"}
CROSS = SPECIAL | {"FNavMeshCrossPylonEdge", "FNavMeshOneWayBackRefEdge",
                   "FNavMeshDropDownEdge", "FNavMeshPathObjectEdge"}


def parse_navigation(blob, start, end, endian, names):
    position = start

    def read(fmt):
        nonlocal position
        size = struct.calcsize("=" + fmt)
        assert position + size <= end
        values = struct.unpack_from(endian + fmt, blob, position)
        position += size
        return values

    def array(element):
        count, = read("i")
        assert 0 <= count <= end - position
        return [element() for _ in range(count)]

    version = read("2i")
    assert version[0] == 43
    verts = array(lambda: (read("3I"), array(lambda: read("H"))))
    storage = array(lambda: read("IHii"))
    classes = [names[entry[2]] for entry in storage]
    assert all(entry[3] == 0 for entry in storage)
    assert all(name in BASE | CROSS for name in classes)

    def poly():
        return (array(lambda: read("H")), array(lambda: read("H")), read("12IB"),
                array(lambda: read("6i")), read("I"))

    polys = array(poly)
    transforms = read("32I")
    borders = array(lambda: read("3H"))
    bounds = read("6IB")
    edge_start = position
    edges = []
    for name in classes:
        cross = name in CROSS
        data = [read(("4H" if cross else "2H") + "2H4I2B3I")]
        if cross:
            data.append(read("12iH"))
        if name in SPECIAL:
            data.append(read("7i3Ii"))
        elif name == "FNavMeshDropDownEdge":
            data.append(read("I"))
        elif name == "FNavMeshPathObjectEdge":
            data.append(read("6i"))
        edges.append(data)
    assert position == end
    assert all(index[0] < len(verts) for poly in polys for index in poly[0])
    assert all(index[0] < len(polys) for vertex in verts for index in vertex[1])
    return {"version": version, "verts": verts, "storage": storage, "classes": classes,
            "polys": polys, "transforms": transforms, "borders": borders, "bounds": bounds,
            "edges": edges, "edge_bytes": end - edge_start}


def validate():
    source = (FIXTURES / "SP_E2_01_S.xxx.unc").read_bytes()
    output = (FIXTURES / "SP_E2_01_S.navigation-20260930.le.xxx").read_bytes()
    manifest = json.loads((FIXTURES / "SP_E2_01_S.navigation-20260930.manifest.json").read_text())
    converter = Converter(source)
    names = converter.read_names()
    rows = []
    nav_data = {}
    obstacle_to_navigation = {}
    for entry in manifest["exports"]:
        if entry["class_name"] != "Pylon":
            continue
        start = entry["serial_offset"]
        end = start + entry["serial_size"]
        prologue_end = converter.prologue(False, False, int(entry["object_flags"], 16), start)
        tail = converter.tags(names, prologue_end, end)
        assert tail == end - 8
        primary, obstacle = struct.unpack_from(">2i", source, tail)
        assert (primary, obstacle) == struct.unpack_from("<2i", output, tail)
        obstacle_to_navigation[obstacle] = primary
    for entry in manifest["exports"]:
        if entry["class_name"] != "NavigationMeshBase":
            continue
        start = entry["serial_offset"]
        end = start + entry["serial_size"]
        tail = Converter(source).tags(names, start + 4, end)
        assert tail is not None
        original = parse_navigation(source, tail, end, ">", names)
        assert original == parse_navigation(output, tail, end, "<", names)
        nav_data[entry["package_index"]] = original
        rows.append({"name": entry["object_name"], "export": entry["index"],
                     "vertices": len(original["verts"]), "polys": len(original["polys"]),
                     "edges": len(original["edges"]), "edge_bytes": original["edge_bytes"],
                     "edge_classes": dict(collections.Counter(original["classes"]))})
    for index, mesh in nav_data.items():
        # Obstacle polys reference edges from their pylon's navigation mesh,
        # as documented in UnPath.h:1900; their own edge pool is empty.
        edge_owner = nav_data[obstacle_to_navigation.get(index, index)]
        assert all(i[0] == 65535 or i[0] < len(edge_owner["edges"])
                   for poly in mesh["polys"] for i in poly[1])
    assert len(rows) == 4 and sum(row["edges"] for row in rows) == 681
    return {"package": "SP_E2_01_S", "sha256": hashlib.sha256(output).hexdigest(),
            "navigation_source_values_preserved": True, "navigation_index_ranges_valid": True,
            "navigation_meshes": rows}


if __name__ == "__main__":
    report = validate()
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURES / "navigation-20260930.validation.json"
    with destination.open("x") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
