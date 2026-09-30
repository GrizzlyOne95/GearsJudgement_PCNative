"""Read-only fingerprint of the campaign installs and shared campaign source."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(r"C:\Games\Gears 3 Files")
PROTECTED = [
    ROOT / "Gears 3 Campaign Rebuild v0.1",
    ROOT / "Gears 3 Jacinto 1.1.1",
    ROOT / "gears_of_war_3_2011-09-14" / "Development" / "Src",
]


def snapshot():
    result = {}
    for root in PROTECTED:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            stat = path.stat()
            entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            # Hash the source, binaries, launchers and configuration. Large cooked content
            # gets metadata checks; it is never an output destination for this project.
            if path.suffix.lower() in {".exe", ".dll", ".ini", ".cmd", ".ps1", ".sav",
                                       ".cpp", ".h", ".uc", ".cs", ".bat"}:
                entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path)] = entry
    return result


if __name__ == "__main__":
    target = Path(sys.argv[2])
    current = snapshot()
    if sys.argv[1] == "capture":
        with target.open("x", encoding="utf-8") as handle:
            json.dump(current, handle, indent=2)
        print(f"Protected baseline: {len(current)} files; {target}")
    elif sys.argv[1] == "verify":
        previous = json.loads(target.read_text(encoding="utf-8"))
        changes = [key for key in sorted(previous.keys() | current.keys())
                   if previous.get(key) != current.get(key)]
        print(f"Protected campaign verification: {len(current)} files; {len(changes)} changes")
        for key in changes:
            print(key)
        sys.exit(bool(changes))
    else:
        raise SystemExit("usage: protect_campaign.py capture|verify baseline.json")
