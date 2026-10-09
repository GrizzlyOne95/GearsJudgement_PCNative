# Judgment / ReXGlue recompilation track

This is a **separate, experimental track** alongside this repository's existing
Unreal Engine 3 native-content converter, runtime-loading research, and Gears 3
Steam co-op patches. It is not a replacement for those tools or an integrated
replacement for `scripts/build-judgment-loader.ps1`.

## Source and provenance

- Development fork (submodule remote): https://github.com/GrizzlyOne95/gears-judgement-recomp
- Original upstream: https://github.com/OverkillLabs3/gears-judgement-recomp
- Submodule: `recomp/gears-judgement-recomp/`
- Pinned baseline: `c20e7b3db6b56e3529e6df241a9d4e4ab7f0b2ee` (upstream v0.1.0, 2026-10-03); the fork initially shares this exact commit
- Upstream license: BSD 3-Clause; see the submodule's `LICENSE` and
  `THIRD_PARTY_NOTICES.txt`. The parent repository's MIT license applies to
  our own source, **not** automatically to the separately licensed submodule.
- Runtime: [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk), tested by
  upstream with SDK 0.10.0.9-dev, commit `923c1a5`.

A Git submodule pins a specific upstream commit, preserves upstream history,
and keeps licensing and future updates distinct. **Do not commit retail game
files, generated recompiled game code, or extracted game assets.** The
submodule ignores `game/`, `generated/`, and `out/`.

## Clone or initialize

```powershell
git clone --recurse-submodules https://github.com/GrizzlyOne95/GearsJudgement_PCNative.git
cd GearsJudgement_PCNative
# Existing clones, especially those initialized before the fork URL changed:
git submodule sync --recursive
git submodule update --init --recursive
```

To verify the pinned code:

```powershell
git -C recomp/gears-judgement-recomp rev-parse HEAD
# Expected: c20e7b3db6b56e3529e6df241a9d4e4ab7f0b2ee
```

## Prerequisites and build

The upstream code generation and game loading require **your own retail Xbox
360 disc-version game files**: title ID `4D530A26`, media ID `3528321A`;
its `default.xex` is **not interchangeable** with this repository's
separately studied v845 debug executable. The complete retail game folder also
needs `GearGame/` for playing. Digital ownership alone does not guarantee
access to the exact supported disc-version executable. Use legally obtained
copies of the required files; they must remain outside Git history.

Install Windows 10/11 x64 tooling: Visual Studio 2022 C++ build tools including
Clang and the Windows SDK, CMake >= 3.25, Ninja, Python >= 3.9, and the supported
ReXGlue SDK. Refer to [upstream BUILDING.md](gears-judgement-recomp/BUILDING.md)
for the authoritative instructions.

From the **parent repo root**, assuming the compatible game executable and SDK
are already available locally:

```powershell
$port = 'recomp/gears-judgement-recomp'
New-Item -ItemType Directory -Force -Path "$port/game" | Out-Null
Copy-Item -LiteralPath 'C:\path\to\your\retail\default.xex' -Destination "$port/game/default.xex"
Push-Location $port
try {
  powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Sdk 'C:\path\to\rexglue-sdk'
} finally {
  Pop-Location
}
```

On success, the upstream build places `GearsOfWarJudgment.exe` and
`Graphics Settings.exe` in `recomp/gears-judgement-recomp/out/package/`.
At first launch, choose the **retail** game directory containing `default.xex`
and `GearGame/`.

The build has **not been run or validated as part of this integration**: the
retail game executable and external SDK are intentionally not in this repo.

## Current scope and LAN co-op roadmap

The pinned upstream release supports an early-tested **single-player** campaign;
multiplayer, Xbox Live, LAN co-op, and internet co-op are **not** implemented.
Existing Gears 3 Steamworks patch files under `patches/gears3-steam-coop/`
are a different engine/runtime target and cannot simply be applied here.

Suggested development order:

1. Establish a reproducible baseline with the **compatible retail XEX**,
   verify full-campaign progression, saving, audio, and stability.
2. Instrument Judgment's XAM/XGI session and XNet/socket calls at the first
   multiplayer/system-link menu transitions; record the actual API path before
   designing a networking shim.
3. Implement minimally functional per-PC player IDs, session create/search/join,
   IPv4 address translation, and host/client transport. ReXGlue's upstream SDK
   `XSessionSearch`/create/join behavior and several XNet address functions are
   currently placeholders. Working socket send/receive alone is insufficient.
4. Test **two PCs on LAN**: host advertisement or explicit-IP join, session
   negotiation, loading one campaign map together, replication, checkpoints,
   level transitions, and reconnect/disconnect behavior.
5. Consider internet transport only after LAN co-op is reproducible. Do not
   claim campaign co-op works until an actual two-PC test passes.

**When modifying the submodule:** changes made in a detached, pinned submodule
checkout are not automatically committed to this parent repository. Work on a
named feature branch in [our fork](https://github.com/GrizzlyOne95/gears-judgement-recomp),
push it, and merge its changes into the fork's `main` when validated. Then
update the parent repository's submodule commit pointer and commit/push the
parent change. Keep [OverkillLabs3 upstream](https://github.com/OverkillLabs3/gears-judgement-recomp)
as the canonical source for upstream updates and potential contributions.
Avoid drifting away from a reproducible baseline without documenting patches.

## Updating the submodule intentionally

```powershell
git -C recomp/gears-judgement-recomp fetch origin
git -C recomp/gears-judgement-recomp checkout <reviewed-fork-commit-sha>
git add recomp/gears-judgement-recomp
git commit -m "chore(recomp): bump pinned Judgment fork commit"
git push
```

Review upstream changes and their licenses before bumping the pointer. Never
use automatic submodule tracking of a moving branch for reproducible builds.
