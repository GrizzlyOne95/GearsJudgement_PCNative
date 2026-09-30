"""Independent probe/tagged-property audit of a recovered texture package."""
import argparse
import hashlib
import json
from pathlib import Path

from replace_texture_pixels import replace
from tagged_props import Package

ROOT = Path(r"C:\Games\_judgment-scratch\character-surface")


def validate(old_path=None, new_path=None, old_manifest=None, new_manifest=None, fixtures_path=None):
    old_path = old_path or ROOT / "COG_Baird_Jack.asset-v2.le.xxx"
    new_path = new_path or ROOT / "COG_Baird_Jack.asset-v3-textures.le.xxx"
    old_manifest = old_manifest or ROOT / "COG_Baird_Jack.asset-v2.manifest.json"
    new_manifest = new_manifest or ROOT / "COG_Baird_Jack.asset-v3-textures.manifest.json"
    fixtures_path = fixtures_path or ROOT / "texture-fixtures-v1"
    old, new = Package(old_manifest, old_path), Package(new_manifest, new_path)
    layout = new.doc["layout_validation"]
    assert layout["invalid_name_references"] == layout["invalid_resource_or_serial_references"] == 0
    texture_count = sum(e["class_name"] == "Texture2D" for e in old.doc["exports"])
    assert texture_count > 0
    assert layout["texture2d_payloads_checked"] == layout["texture2d_payloads_structurally_valid"] == texture_count
    def normalize(entry, path):
        result = dict(entry)
        result["object_path"] = result["object_path"].removeprefix(path.stem)
        return result
    assert new.doc["names"] == old.doc["names"]
    assert [normalize(e, new_path) for e in new.doc["imports"]] == [normalize(e, old_path) for e in old.doc["imports"]]
    assert len(old.doc["exports"]) == len(new.doc["exports"])
    fixtures, comparisons = {}, []
    for before, after in zip(old.doc["exports"], new.doc["exports"]):
        before, after = dict(before), dict(after)
        before["object_path"] = before["object_path"].removeprefix(old_path.stem)
        after["object_path"] = after["object_path"].removeprefix(new_path.stem)
        if before["class_name"] != "Texture2D":
            assert before == after
            start, size = before["serial_offset"], before["serial_size"]
            assert old.blob[start:start + size] == new.blob[start:start + size]
            continue
        for key in before.keys() - {"serial_offset", "serial_size", "payload_analysis"}:
            assert before[key] == after[key]
        fixture_path = fixtures_path / (before["object_name"] + ".upk")
        fixture_manifest = fixture_path.with_suffix(".manifest.json")
        pc = Package(fixture_manifest, fixture_path)
        fixtures[before["object_name"]] = pc.blob
        pixel_source = pc.doc["exports"][0]["payload_analysis"]
        actual = after["payload_analysis"]
        assert actual["structurally_valid"] and actual["bytes_consumed"] == after["serial_size"]
        assert actual["net_index"] == before["payload_analysis"]["net_index"]
        assert actual["texture_file_cache_guid"] == pixel_source["texture_file_cache_guid"]
        assert len(actual["mips"]) == len(pixel_source["mips"])
        mip_hashes = []
        for target, source in zip(actual["mips"], pixel_source["mips"]):
            assert (target["size_x"], target["size_y"]) == (source["size_x"], source["size_y"])
            tb, sb = target["bulk_data"], source["bulk_data"]
            assert tb["inline"] and sb["inline"]
            assert tb["flags"] == sb["flags"] == "0x00000000"
            assert tb["element_count"] == tb["size_on_disk"] == sb["element_count"] == sb["size_on_disk"]
            target_pixels = new.blob[tb["offset_in_file"]:tb["offset_in_file"] + tb["size_on_disk"]]
            source_pixels = pc.blob[sb["offset_in_file"]:sb["offset_in_file"] + sb["size_on_disk"]]
            assert len(target_pixels) == tb["element_count"] and target_pixels == source_pixels
            mip_hashes.append(hashlib.sha256(target_pixels).hexdigest())
        def raw_settings(pkg, entry):
            start, end = entry["serial_offset"] + 4, entry["serial_offset"] + entry["serial_size"]
            tags, _ = pkg.walk(start, end)
            assert tags is not None
            result = {}
            for pos, name, kind, size, array, _ in tags:
                value_at = pos + 24 + (8 if kind in ("ByteProperty", "StructProperty") else 1 if kind == "BoolProperty" else 0)
                result[name, array] = pkg.blob[pos:value_at + size]
            return result
        before_settings, after_settings = raw_settings(old, before), raw_settings(new, after)
        removed = {"TextureFileCacheName", "FirstResourceMemMip"}
        changed = {"SizeX", "SizeY", "MipTailBaseIdx"}
        assert set(after_settings) == {key for key in before_settings if key[0] not in removed}
        for key, raw in before_settings.items():
            if key[0] not in removed | changed:
                assert after_settings[key] == raw
        comparisons.append({"name": before["object_name"], "mips": len(mip_hashes),
                            "pixel_sha256": mip_hashes, "settings_preserved": True})
    regenerated, report = replace(old.blob, fixtures)
    assert regenerated == new.blob
    # Only selected textures' two typed INT fields change in the original file.
    # All remaining source bytes, including every old bulk allocation, are intact.
    restored = bytearray(new.blob[:len(old.blob)])
    fields = old.i32(12)
    ints_at = 16 + (fields if fields > 0 else -fields * 2)
    exports_at = old.i32(ints_at + 16)
    for entry in old.doc["exports"]:
        generations = old.i32(exports_at + 44)
        if entry["class_name"] == "Texture2D":
            restored[exports_at + 32:exports_at + 40] = old.blob[exports_at + 32:exports_at + 40]
        exports_at += 68 + generations * 4
    assert restored == old.blob
    report.update({"independent_probe_layout_valid": True, "original_bytes_unchanged_except_serial_fields": texture_count * 2,
                   "non_texture_exports_unchanged": len(old.doc["exports"]) - texture_count, "mips_byte_identical_to_probe": sum(c["mips"] for c in comparisons),
                   "independent_tagged_settings_preserved": True, "regenerates_byte_identically": True,
                   "comparisons": comparisons})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--base-manifest", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("refusing to overwrite retained evidence")
    report = validate(args.base, args.artifact, args.base_manifest, args.manifest, args.fixtures)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: %d textures, %d exact PC mips, %d unchanged other exports; %s" %
          (report["textures_recovered"], report["mips_byte_identical_to_probe"],
           report["non_texture_exports_unchanged"], report["output_sha256"]))
