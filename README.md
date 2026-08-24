# GearsJudgement_PCNative

Tooling and original technical work to help port *Gears of War: Judgment* to
a native PC build.

## Repository scope

This repository is for material that can be redistributed, including original
source code, build scripts, documentation, technical notes, manifests that do
not reproduce game content, and third-party components whose licenses permit
redistribution.

Do not commit retail game files or extracted copyrighted assets. This includes
packages, executables, maps, textures, audio, movies, or other content copied
from any release of the game. Keep those inputs in `local-game-content/` (or
another ignored local directory) and pass their paths to the tools as needed.

Likely game-content extensions are ignored by default. A demonstrably original
or redistributable fixture with one of those extensions may be added explicitly
only after its provenance and license have been documented.

## Import redirection diagnostics

`redirect_imports.py` can redirect a missing UE3 import to a compatible import
that already exists in the same little-endian package. It consumes a manifest
created by `package-probe`, validates the fixed-size import table and every
record it touches, requires matching import classes, and writes a new file
without modifying or overwriting either input.

```powershell
python redirect_imports.py <manifest.json> <input.u> <output.u> `
  --replace MissingPackage.Group.Asset=ExistingPackage.Group.Asset
```

Repeat `--replace` for multiple imports. This is a diagnostic tool, not a
general asset replacement system: the selected target must also be semantically
safe for the code path being tested. Keep manifests and generated packages made
from retail inputs outside Git (the ignored `package-probe/build/` directory is
suitable for local work).

Run its synthetic tests with:

```powershell
python -m unittest discover -s tests -v
```
