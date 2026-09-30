"""Audit Baird's extracted package, exact native loads and rendered evidence."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from be2le import load_array_types
from extract_asset_package import extract
from tagged_props import Package

FIXTURES = Path(r"C:\Games\_judgment-scratch\character-surface")
ARRAYS = Path(r"C:\Games\_judgment-scratch\array-types-v845.json")


def validate(log_path):
    source = (FIXTURES / "GearGame.xxx.unc").read_bytes()
    manifest = json.loads((FIXTURES / "GearGame.xxx.json").read_text())
    artifact = FIXTURES / "COG_Baird_Jack.asset-v2.le.xxx"
    output = artifact.read_bytes()
    regenerated, report = extract(source, manifest, "COG_Baird_Jack", load_array_types(ARRAYS)[0],
                                  json.loads(ARRAYS.read_text()))
    assert regenerated == output
    pc_manifest_path = FIXTURES / "COG_Baird_Jack.asset-v2.manifest.json"
    pc_manifest = json.loads(pc_manifest_path.read_text())
    layout = pc_manifest["layout_validation"]
    assert layout["invalid_name_references"] == layout["invalid_resource_or_serial_references"] == 0
    assert layout["imports_end"] == layout["expected_imports_end"]
    assert layout["exports_end"] == layout["expected_exports_end"]
    assert layout["texture2d_payloads_checked"] == layout["texture2d_payloads_structurally_valid"] == 6
    assert len(pc_manifest["exports"]) == report["emitted_exports"] == 108
    pc = Package(pc_manifest_path, artifact)
    # Independent tagged-property reading checks the previously ambiguous arrays
    # against the exact extracted export identities, not just in-range integers.
    physics = next(e for e in pc.doc["exports"] if e["class_name"] == "PhysicsAssetInstance")
    _, tags, slack = pc.find_prologue(physics)
    assert tags is not None and slack == 292
    for pos, name, kind, size, _, _ in tags:
        assert name in ("Bodies", "Constraints") and kind == "ArrayProperty"
        count = pc.i32(pos + 24)
        assert count == (17 if name == "Bodies" else 16) and size == count * 4 + 4
        for offset in range(pos + 28, pos + 24 + size, 4):
            ref = pc.i32(offset)
            entry = pc.doc["exports"][ref - 1]
            assert ref > 0 and entry["class_name"] == ("RB_BodyInstance" if name == "Bodies" else "RB_ConstraintInstance")
            assert entry["outer_index"] == physics["package_index"]

    text = Path(log_path).read_text(errors="replace")
    enters = re.findall(r"\[JUDGPRELOAD\] enter exp=(\d+) obj=(\S+) cls=(\S+) off=(\d+) size=(\d+) end=(\d+) pkg=COG_Baird_Jack(?:\s|$)", text)
    leaves = re.findall(r"\[JUDGPRELOAD\] leave exp=(\d+) obj=(\S+) consumed=(\d+) size=(\d+) pkg=COG_Baird_Jack(?:\s|$)", text)
    assert len(enters) == len(leaves) == 108
    assert len({row[0] for row in enters}) == len({row[0] for row in leaves}) == 108
    for index, name, cls, start, size, end in enters:
        entry = pc.doc["exports"][int(index)]
        assert (name, cls, int(start), int(size), int(end)) == (
            entry["object_name"], entry["class_name"], entry["serial_offset"], entry["serial_size"],
            entry["serial_offset"] + entry["serial_size"])
    assert all(consumed == size for _, _, consumed, size in leaves)
    players = re.findall(r"\[JUDGPROTO\] player-mesh pawn=(\S+) mesh=(\S+) physics=(\S+) bones=(\d+) local-atoms=(\d+) space-bases=(\d+) animsets=(\d+) animations=(\S+) hidden=(\d+)", text)
    assert len(players) >= 2
    latest = players[-1]
    assert latest == ("GearPawn_COGBairdJack", "COG_Baird_Jack.Skel_Mesh.COG_Baird_Jack_CamSkel",
                      "COG_Baird_Jack.Physics.COG_Baird_Jack_CamSkel_Physics", "123", "123", "123", "15", "AnimTree", "0")
    assert not re.search(r"Critical: appError called:", text)
    assert not re.search(r".*GearPawn_COGBairdJack.*NULL SkeletalMesh", text)
    report.update({"runtime_exact_asset_loads": 108, "physics_array_references_match": True,
                   "player_mesh": latest[1], "player_physics": latest[2], "player_bones": 123,
                   "player_local_atoms": 123, "player_space_bases": 123,
                   "regenerates_byte_identically": True, "log": str(log_path)})
    presents = re.findall(r"\[([0-9.]+)\].*\[JUDGPROTO\] d3d9-present frames=(\d+) width=(\d+) height=(\d+)", text)
    if presents:
        assert len(presents) >= 2 and int(presents[-1][1]) > int(presents[0][1])
        report["presented_frames_at_last_report"] = int(presents[-1][1])
        report["last_present_seconds"] = float(presents[-1][0])
    if "[JUDGPROTO] requesting rendered screenshot" in text:
        shot = Path(r"C:\Games\Gears 3 Files\Judgment Port Workspace\GearGame\ScreenShots\ScreenShot00000.bmp")
        bitmap = shot.read_bytes()
        assert bitmap[:2] == b"BM" and struct.unpack_from("<2i", bitmap, 18) == (1280, 720)
        # Verify real pixel variation; visual inspection remains a separate check.
        pixels_at = struct.unpack_from("<I", bitmap, 10)[0]
        colors = {bitmap[i:i + 3] for i in range(pixels_at, len(bitmap), 3)}
        assert len(colors) > 1000
        report["screenshot"] = str(shot)
        report["screenshot_sha256"] = hashlib.sha256(bitmap).hexdigest()
        report["screenshot_distinct_colors"] = len(colors)
    report["limits"] = "Visible character/geometry only; Xbox texture pixels, lighting, input, collision, cover, AI and audio remain unverified or incorrect."
    return report


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    if destination.exists():
        raise SystemExit("refusing to replace retained validation evidence")
    report = validate(sys.argv[2])
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
