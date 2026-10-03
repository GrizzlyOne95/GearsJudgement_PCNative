"""Recover PC pixels for the plain Texture2D exports of one converted Judgment map.

Runs the C++ probe once per export (cache LZX, detiling, byte order, mip tails)
and appends the resulting fixtures to the converted v845 package with
replace_texture_pixels. A texture the probe or the writer rejects is reported
and left exactly as converted; nothing is guessed. LightMapTexture2D and
ShadowMapTexture2D exports carry native trailers and are not handled here.
Retail inputs and outputs belong outside Git.
"""
import argparse
import json
from pathlib import Path
import subprocess

from replace_texture_pixels import Package, replace

PROBE = Path(__file__).resolve().parent / "package-probe" / "build" / "Release" / "judgment-package-probe.exe"


def fixture_path(directory, entry):
    # Streamed maps repeat object names across groups; the export index keeps files unique.
    return directory / f"{entry.index:05d}-{entry.name}.upk"


def recover_fixtures(parsed, source, cache, directory, probe, rejected, run=subprocess.run):
    fixtures = {}
    for entry in parsed.exports:
        if parsed.class_name(entry) != "Texture2D":
            continue
        path = fixture_path(directory, entry)
        if not path.exists():
            done = run([str(probe), "--convert-texture-fixture-full-mips", str(source),
                        str(entry.index), str(cache), str(path)], capture_output=True, text=True)
            if done.returncode or not path.exists():
                lines = (done.stderr or done.stdout or "").strip().splitlines()
                rejected.append({"export_index": entry.index, "name": entry.name, "stage": "probe",
                                 "reason": lines[-1].strip() if lines else f"exit {done.returncode}"})
                continue
        fixtures[entry.index] = path.read_bytes()
    return fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="uncompressed big-endian v845 package (.xxx.unc)")
    parser.add_argument("package", type=Path, help="its converted little-endian v845 package")
    parser.add_argument("cache", type=Path, help="CookedXbox360 directory holding the texture file caches")
    parser.add_argument("fixtures", type=Path, help="directory for <export-index>-<name>.upk fixtures")
    parser.add_argument("output", type=Path)
    parser.add_argument("--probe", type=Path, default=PROBE)
    args = parser.parse_args()
    receipt = args.output.with_suffix(".textures.json")
    if args.output.exists() or receipt.exists():
        parser.error("refusing to overwrite retained package or receipt")
    package = args.package.read_bytes()
    args.fixtures.mkdir(parents=True, exist_ok=True)
    rejected = []
    fixtures = recover_fixtures(Package(package), args.source, args.cache, args.fixtures, args.probe, rejected)
    if not fixtures:
        parser.error("the probe recovered no textures: " + json.dumps(rejected[:3]))
    output, report = replace(package, fixtures, rejected)
    report["textures_rejected"] = rejected
    args.output.write_bytes(output)
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    reasons = {}
    for item in rejected:
        reasons[item["stage"] + ": " + item["reason"]] = reasons.get(item["stage"] + ": " + item["reason"], 0) + 1
    print(json.dumps({"textures_recovered": report["textures_recovered"], "textures_rejected": len(rejected),
                      "rejection_reasons": reasons, "original_bytes": report["original_bytes"],
                      "output_bytes": report["output_bytes"], "output_sha256": report["output_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
