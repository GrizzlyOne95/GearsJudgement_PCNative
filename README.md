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

## Native-content regression checks

The thin Judgment `GearGame_P` fixture is hash-pinned locally without committing retail data.
The verifier checks the decompressed retail input, generated v845 array schema, deterministic
converter output, and staged map before reporting success:

```powershell
.\content-converter\verify-thin-map.ps1
```

The loader build is also permanent rather than dependent on a temporary batch file. With no
version tag it refreshes the fixed development executable; a tag archives a separate artifact
and refuses to overwrite it unless `-Force` is supplied:

```powershell
.\scripts\build-judgment-loader.ps1
.\scripts\build-judgment-loader.ps1 -VersionTag v61-nativecontent
```

## Gears 3 Steam campaign co-op

The redistributable source delta and build/test notes for the Steam campaign
co-op repair are in
[`patches/gears3-steam-coop`](patches/gears3-steam-coop/README.md). The patch
restores friend lobbies and invites, routes accepted invites through Gears'
persistent-party reservation, synchronizes the session state Gears validates,
validates listen-server advertisement, and blocks late shared-Spacewar
self-kicks before the host is removed.

## Native Xbox 360 static recompilation (ReXGlue)

Our [Judgment ReXGlue fork](https://github.com/GrizzlyOne95/gears-judgement-recomp)
(of [OverkillLabs3's original project](https://github.com/OverkillLabs3/gears-judgement-recomp))
is tracked under [`recomp/gears-judgement-recomp`](recomp/gears-judgement-recomp)
**as a pinned Git submodule**, rather than vendored source. It is an independent
Windows x64/DirectX 12 port that statically recompiles the **retail Xbox 360**
PowerPC executable with ReXGlue and reads the original game content. It does
not use the v845-debug-build-to-v828-PC package conversion workflow in this
repository, and it does not replace that work.

Initialize it after cloning, or synchronize the new fork URL in an existing checkout:

```powershell
git submodule sync --recursive
git submodule update --init --recursive
```

See [`recomp/README.md`](recomp/README.md) for prerequisites, build steps,
licensing, and a realistic roadmap toward two-PC LAN campaign co-op.
**As of the pinned v0.1.0 release, only single-player campaign functionality
is supported; LAN/online co-op is not implemented.** No retail executable or
game assets are included in this repository or submodule.
