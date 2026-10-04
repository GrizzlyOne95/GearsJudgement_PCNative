"""Install Judgment's own gameplay config into the Judgment port workspace.

The workspace started from the Gears 3 PC config, so every config key Judgment added
(e.g. GearWeapon.GearEquipTime) read as zero.  This replaces Default<Name>.ini with the
merged Gear<Name>.ini extracted from the Xbox Coalesced_INT.bin (see coalesced_extract.py)
and removes the generated Gear<Name>.ini so the engine regenerates it on the next start.

Only the workspace config directory is written; originals are copied to the backup
directory first and are never overwritten there.

Usage: python install_judgment_config.py <coalesced_dir> <workspace_dir> <backup_dir> <Name> [<Name> ...]
       e.g. ... Weapon Pawn AI Camera
"""
import shutil
import stat
import sys
from pathlib import Path

MARKER = "; Judgment config installed by install_judgment_config.py from Coalesced_INT.bin"


def install(coalesced_dir, workspace_dir, backup_dir, name):
    source = Path(coalesced_dir) / "GearGame" / "Config" / f"Gear{name}.ini"
    config_dir = Path(workspace_dir) / "GearGame" / "Config"
    default_ini = config_dir / f"Default{name}.ini"
    generated_ini = config_dir / f"Gear{name}.ini"
    if not source.is_file():
        raise FileNotFoundError(source)
    if not default_ini.is_file():
        raise FileNotFoundError(default_ini)

    body = source.read_text(encoding="utf-8")
    try:
        body.encode("latin-1")
    except UnicodeEncodeError as error:
        raise ValueError(f"{source} has characters outside latin-1") from error
    new_text = f"{MARKER}\n; source: GearGame\\Config\\Gear{name}.ini\n\n{body}"

    current = default_ini.read_text(encoding="latin-1")
    if current == new_text:
        return f"{name}: already installed"

    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    for original in (default_ini, generated_ini):
        target = backup_root / original.name
        # Keep the first (pre-Judgment) copy; later runs must not replace it.
        if original.is_file() and not target.exists() and MARKER not in original.read_text(encoding="latin-1"):
            shutil.copy2(original, target)

    # Stock Default*.ini files carry the source drop's read-only attribute.
    default_ini.chmod(stat.S_IWRITE | stat.S_IREAD)
    default_ini.write_text(new_text, encoding="latin-1", newline="\r\n")
    if generated_ini.is_file():
        generated_ini.unlink()
    return f"{name}: installed {default_ini.name} ({len(body)} chars), removed generated {generated_ini.name}"


def main(argv):
    if len(argv) < 5:
        sys.exit(__doc__)
    coalesced_dir, workspace_dir, backup_dir = argv[1:4]
    for name in argv[4:]:
        print(install(coalesced_dir, workspace_dir, backup_dir, name))


if __name__ == "__main__":
    main(sys.argv)
