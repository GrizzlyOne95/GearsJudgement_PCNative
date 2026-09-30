"""Measure the BE->LE conversion surface of Judgment cooked packages, by object class.

Answers the question that orders all remaining content work: for a real map, which
object classes actually hold the bytes, and which hold the export *count*? Those two
rankings disagree completely, and each drives a different piece of work:

  - by BYTES  -> Texture2D / StaticMesh / SoundNodeWave / ShaderCache / SkeletalMesh.
                 These need per-format binary converters (untile, deswizzle, format
                 remap, vertex-buffer swap). Few objects, most of the megabytes.
  - by COUNT  -> StaticMeshComponent / CoverLink / SeqAct_* / SeqEvent_* / components.
                 These are ordinary tagged-property objects. ONE generic tagged-property
                 BE->LE translator retires thousands of them at once.

Pitfalls this tool exists to avoid:

  - 1,277 of 1,289 cooked packages are LZX *chunk*-compressed and the name/import/export
    tables live inside the compressed region. Running --manifest on a raw .xxx silently
    yields nothing useful; --decompress-package must run first. This script always does
    both, in order.
  - Rank by `serial_size`, not by file size on disk. Bulk data (mip chains, audio) may be
    stored in a separate .tfc and is NOT counted in serial_size, so texture totals here are
    a LOWER bound on the real conversion volume.
  - A "level" is not one package. Judgment maps are a persistent `_P` plus many streaming
    sublevels; measure a whole family or the numbers are meaningless.

Usage:
    python conversion_surface.py <work-dir> <package.xxx> [package.xxx ...]
"""
import collections
import json
import os
import subprocess
import sys

PROBE = r"C:\Games\NostalgiaBundle\projects\judgment-native\package-probe\build\Release\judgment-package-probe.exe"
COOK = r"C:\Games\GearsJudgement\UnrealEngine3-Jack\GearGame\CookedXbox360"


def manifest_for(work_dir, name):
    """Decompress then manifest one cooked package; return its parsed manifest or None."""
    src = os.path.join(COOK, name)
    unc = os.path.join(work_dir, name + ".unc")
    man = os.path.join(work_dir, name + ".json")
    # The probe refuses to overwrite an output, so reuse anything already produced.
    if not os.path.exists(unc):
        subprocess.run([PROBE, "--decompress-package", src, unc],
                       capture_output=True, text=True)
    if not os.path.exists(unc):
        return None
    if not os.path.exists(man):
        subprocess.run([PROBE, "--manifest", unc, man], capture_output=True, text=True)
    if not os.path.exists(man):
        return None
    with open(man) as handle:
        return json.load(handle)


def main(work_dir, names):
    os.makedirs(work_dir, exist_ok=True)
    by_count, by_bytes, failed = collections.Counter(), collections.Counter(), []

    for name in names:
        doc = manifest_for(work_dir, name)
        if doc is None:
            failed.append(name)
            print(f"  {name}: FAILED")
            continue
        for e in doc["exports"]:
            cls = e["class_name"]
            by_count[cls] += 1
            by_bytes[cls] += max(0, e.get("serial_size") or 0)
        print(f"  {name}: {len(doc['exports'])} exports, {len(doc['imports'])} imports")

    print("\n=== by serial bytes (per-format binary converters) ===")
    for cls, size in by_bytes.most_common(20):
        print(f"  {size / 1048576:9.2f} MB  {by_count[cls]:6d}x  {cls}")

    print("\n=== by export count (generic tagged-property translator) ===")
    for cls, count in by_count.most_common(20):
        print(f"  {count:6d}x  {by_bytes[cls] / 1048576:8.2f} MB  {cls}")

    total_b = sum(by_bytes.values()) / 1048576
    print(f"\ntotal exports={sum(by_count.values())} serial={total_b:.1f} MB "
          f"distinct classes={len(by_count)}")
    if failed:
        print(f"failed packages: {failed}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
