"""Compare all night-LUT pixels to Judgment's cooker-measured byte addresses."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\Games\_judgment-scratch\e2-surface")


def validate():
    measurements = json.loads((ROOT / "lut-256x16-xg-oracle-20260930.json").read_text())
    assert len(measurements) == 1
    measured = measurements[0]
    assert (measured["format"], measured["width"], measured["height"], measured["mips"]) == ("PF_A8R8G8B8", 256, 16, 1)
    assert measured["hasPackedTail"] and measured["tailBase"] == 0 and measured["tailAllocationSize"] == 32768
    assert not measured["wroteBeyondAllocation"] and measured["duplicateBytes"] == 0
    source_manifest = json.loads((ROOT / "SP_E2_P.xxx.json").read_text())
    source = next(e for e in source_manifest["exports"] if e["object_name"] == "LUT_Night")
    bulk = source["payload_analysis"]["mips"][0]["bulk_data"]
    raw = (ROOT / "SP_E2_P.xxx.unc").read_bytes()
    raw = raw[bulk["offset_in_file"]:bulk["offset_in_file"] + bulk["size_on_disk"]]
    fixtures = ROOT / "base-texture-fixtures-v2"
    manifest = json.loads((fixtures / "LUT_Night.manifest.json").read_text())
    bulk = manifest["exports"][0]["payload_analysis"]["mips"][0]["bulk_data"]
    pc = (fixtures / "LUT_Night.upk").read_bytes()
    pixels = pc[bulk["offset_in_file"]:bulk["offset_in_file"] + bulk["size_on_disk"]]
    assert len(raw) == 32768 and len(pixels) == 16384
    seen, occupied = set(), set()
    for block in measured["blocks"]:
        x, y = block["x"], block["y"]
        assert block["level"] == 0 and 0 <= x < 256 and 0 <= y < 16
        assert (x, y) not in seen
        seen.add((x, y))
        permutation = measured["bytePermutations"][block["perm"]]
        assert sorted(permutation) == [0, 1, 2, 3]
        addresses = [block["offset"] + byte for byte in permutation]
        assert all(0 <= at < len(raw) and at not in occupied for at in addresses)
        occupied.update(addresses)
        expected = bytes(raw[at] for at in addresses)
        at = (y * 256 + x) * 4
        assert pixels[at:at + 4] == expected
    assert len(seen) == 4096 and len(occupied) == 16384
    assert len(set(pixels[i:i + 4] for i in range(0, len(pixels), 4))) == 4096
    return {"cooker": measured["dll"], "pixel_addresses_matched": 4096,
            "byte_addresses_matched": 16384, "packed_tail_default": 0,
            "source_allocation_bytes": 32768, "linear_bytes": 16384,
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(),
            "limits": "Cooker address/endian agreement only; rendered color grading is assessed separately."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("refusing to overwrite retained evidence")
    report = validate()
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
