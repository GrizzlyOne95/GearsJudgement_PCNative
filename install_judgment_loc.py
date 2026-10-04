"""Install Judgment's INT localization into the Judgment port workspace.

python install_judgment_loc.py <coalesced_dir> <workspace_dir> <backup_dir>

<coalesced_dir> is the tree written by coalesced_extract.py. Every
GearGame/Localization/INT/*.int in it replaces the same-named workspace file:
Judgment's sections and keys come first, and keys only the workspace's Gears 3
file has are kept after them, so strings the Gears 3 engine code still asks for
do not turn into ?INT? markers. The workspace original is copied to
<backup_dir> once. Output is UTF-16 with a byte-order mark, as the engine's
own files are. Retail text belongs outside Git.
"""
import stat
import sys
from pathlib import Path

LOC = Path("GearGame") / "Localization" / "INT"


def read_text(path):
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8")
    return data.decode("utf-8", errors="replace")


def parse(text):
    """Ordered [(section, [(key, value)])]; key order and duplicates preserved."""
    sections, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = (line[1:-1], [])
            sections.append(current)
        elif current is not None and "=" in raw:
            key, value = raw.split("=", 1)
            current[1].append((key.strip(), value))
    return sections


def merge(judgment, gears3):
    merged = [(name, list(pairs)) for name, pairs in judgment]
    index = {name.lower(): pairs for name, pairs in merged}
    kept = 0
    for name, pairs in gears3:
        target = index.get(name.lower())
        if target is None:
            target = []
            merged.append((name, target))
            index[name.lower()] = target
        have = {key.lower() for key, _ in target}
        for key, value in pairs:
            if key.lower() not in have:
                target.append((key, value))
                kept += 1
    return merged, kept


def render(sections):
    lines = []
    for name, pairs in sections:
        lines.append(f"[{name}]")
        lines.extend(f"{key}={value}" for key, value in pairs)
        lines.append("")
    return "\r\n".join(lines)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    coalesced, workspace, backup = (Path(arg) for arg in sys.argv[1:])
    source_dir, target_dir = coalesced / LOC, workspace / LOC
    if not source_dir.is_dir() or not target_dir.is_dir():
        sys.exit("missing localization directory")
    backup.mkdir(parents=True, exist_ok=True)
    existing = {path.name.lower(): path for path in target_dir.iterdir() if path.is_file()}
    for source in sorted(source_dir.glob("*.int")):
        target = existing.get(source.name.lower(), target_dir / source.name)
        saved = backup / target.name
        # Merge against the saved Gears 3 original so a re-run does not compound.
        if target.is_file() and not saved.exists():
            saved.write_bytes(target.read_bytes())
        gears3 = parse(read_text(saved)) if saved.is_file() else []
        merged, kept = merge(parse(read_text(source)), gears3)
        if target.exists():
            # The source drop marks its files read-only.
            target.chmod(stat.S_IWRITE | stat.S_IREAD)
        target.write_bytes(b"\xff\xfe" + render(merged).encode("utf-16-le"))
        print(f"{target.name}: {sum(len(p) for _, p in merged)} keys ({kept} kept from Gears 3)")


if __name__ == "__main__":
    main()
