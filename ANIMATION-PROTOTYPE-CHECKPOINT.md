# Judgment animation and headless prototype checkpoint

Session XXII, 2026-09-30. Continues converter commit `3acd5d1` on
`judgment/skeletalmesh-20260930`, with engine branch `judgment/port-workspace`.
Source, builds and staged content stay in the separate
`C:\Games\Gears 3 Files\Judgment Port Workspace` copy. The shared September
source and both Gears 3 campaign installs are protected by the retained baseline.

## Verified result

Seven staged packages now fully convert **12,704/12,704 exports**, with no partial
or unsupported payloads. SP_E2_02_S adds **2,669 exports** and **2,260 observed
native loads** to the previous six-package checkpoint.

The final **100-second headless run passes** loading, possession and continuing
world-tick checks: **11,266 exact-size native loads**, zero size mismatches,
seven loaded levels, and 15 paired tick reports. The last report is at wall-clock
96.84 seconds, tick serial 4,196, game time 67.850 seconds, seven levels. This is
stronger than the previous one-shot world-first-tick checkpoint. The helper was
terminated at the test deadline; exit -1 in the report is expected for that stop.

The engine evaluates all 79 bone tracks of each of the 28 converted animations
at the beginning, middle and end: **6,636 finite pose samples**. Independent BE/LE
parsing verifies **3,836 encoded tracks**, **48,415 keys**, **453 frame tables**,
four CombatZone maps containing **164 poly references**, and one aim profile
containing **32 bones**. The base map's four packed-position samples still match
independent decoding. The stream adds three more packed LODs; the regression
now checks the base samples by package instead of requiring a global count of four.

**65 unit tests pass.** Format coverage includes all seven per-track key formats,
all 16 format flags and both BYTE/WORD frame tables, raw tracks, every native
truncation point, malformed headers/offsets/counts/codecs/frame tables, immutable
aim structures and rollback of earlier valid array elements. The separate package
probe finds valid tables/references and all 32 texture/105 sound payload frames.
All seven archives regenerate byte-identically with the current converter, and
every observed preload offset, class and byte count matches its manifest.

The ws14 loader also passes PkgInfo and the 75-second thin-map regression; the
latter completes tick reports through wall-clock 71.01 seconds.

## Converter changes

`native_animation.py` implements the source-defined cooked AimTransform,
AimComponent and AimOffsetProfile declaration order, plus native raw animation
tracks and the per-track compressed codec. It reads codec/frame/offset metadata
from bounded top-level property ranges. Packed 32-bit keys swap as DWORDs,
fixed48 keys as WORDs, float keys/bounds as DWORDs, and frame indices as BYTEs or
WORDs according to NumFrames. Alignment bytes remain byte data. Identity offsets
are INDEX_NONE; all encoded tracks must cover the stream in order without gaps
or overlap. Unknown codecs remain unsupported, with complete transaction rollback.

`native_navigation.py` converts CombatZone's LinkedPolyMap only when the serialized
bCombatZoneBuilt flag is true. Each entry is a native PolyReference followed by
one INT value. No native tail is skipped or replaced by generic word swapping.

## Headless stall diagnosis and engine changes

The ws10/ws11 process survived its test deadline but stopped completing world
ticks after initial streaming. The added opt-in `-JUDGPROTOTRACE` diagnostics
exposed this; the test correctly records BLOCKED_AFTER_BOOT instead of treating
process survival as a pass. Read-only x86 debugger stack sampling identified two
texture waits:

1. Local shader-cache saving calls SavePackage, which flushes texture streaming.
2. Forced-export linker detachment calls Texture2D::UpdateResource, which waits
   for pending mip requests.

The existing NoTextureStreaming launch flag is parsed after startup texture
loads. **The accepted fix disables streaming at NullRHI initialization**, before
those loads, retaining normal texture resource objects. Local shader-cache saves
are also omitted for Judgment NullRHI launches. Both guards require Judgment
opt-in and the null renderer; rendering launches retain their normal paths.

An experiment returning NULL texture resources caused an ambient-occlusion render
thread failure and was reverted. Private patch 0013 and ws13 are rejected evidence,
not part of the working source. An initial ws14 binary retained a stale compilation
of that experiment after restoring an older-timestamp source file; the restored
source was touched and recompiled into **ws14-headless-streaming-init-v2**. Its
binary was checked to contain the accepted early-init guard and omit the rejected
resource-omission guard. Use only v2 for this checkpoint.

Accepted private incremental patches under workspace `patches\judgment-port`:

| Patch | SHA-256 |
| --- | --- |
| 0011-ws-animation-prototype-diag.patch | 05C1ECE68733982AB1A10D9123E1C23DD9FD9AB219F508CC2FFD837CAD342D58 |
| 0012-ws-nullrhi-cache-save.patch | 0242AEE327DCD1114AEC5481C9F5B78482C6233BAD8E1E6E855B5AB20F630998 |
| 0014-ws-nullrhi-streaming-init.patch | A57D5FF6CC821B4E88A1838A45F04698488BF82A003F8AFB2DCE0DA2A513A1C5 |

These follow retained patches 0009/0010. All accepted patches pass
`git apply --check --reverse --ignore-whitespace` against current source.
Before-images are in scratch `ws11-engine-before`, `ws12-engine-before` and
`ws14-engine-before`. Texture2D.cpp is byte-identical to its pre-experiment image
in `ws13-engine-before`.

## Artifacts and reproduction

New artifact in `C:\Games\_judgment-scratch\e2-surface`:

- `SP_E2_02_S.animation-v1-20260930.le.xxx`, 6,204,646 bytes,
  SHA-256 **50BB192C7B0C8161D3B2B72C760BFFD8CC1D95C60F8364626F67837759A6257E**.
- Matching `SP_E2_02_S.animation-v1-20260930.manifest.json`.
- `animation-headless-prototype-20260930.validation.json` and
  `geometry-headless-prototype-20260930.validation.json` retain independent checks.

Staged only as workspace `GearGame\Content\Maps\SP_E2_02_S.gear`, alongside the
six unchanged checkpoint maps. Add SP_E2_02_S to the explicit converted streaming
package whitelist. The harness defaults to all six retail stream names plus the
prefixed persistent map.

Working loader: workspace
`Binaries\Win32\GearGame-JudgmentLoader-ws14-headless-streaming-init-v2.exe`,
**59,417,600 bytes**, SHA-256
**C547AAA6EA69AEDD6CD0D260CAE3119FF66D3E3D90830DC9E3A51DAC0BE22DD9**.

Final logs/results in workspace `GearGame\Logs`:

- `regress-ws14-headless-streaming-init-v2-sp_e2_p.log` and results JSON.
- `regress-ws14-prototype-regressions-{pkginfo,thinmap}.log` and results JSON.

Earlier ws11/ws12 blocked runs and ws13/initial-ws14 failures are retained.
The useful stall stacks are scratch `ws11-animation-stall-stack-x86.txt` and
workspace `regress-ws12-headless-cache-stack-sp_e2_p.log.stack.log`.

```powershell
python -m unittest discover -q
.\run_loader_regressions.ps1 -Tag NEW_UNIQUE_TAG -BootSeconds 100 -Cases sp_e2_p
.\run_loader_regressions.ps1 -Tag ANOTHER_UNIQUE_TAG -Cases @('pkginfo','thinmap')
python validate_geometry_fixture.py '<runtime log>' '<new validation JSON>'
python validate_animation_fixture.py '<new validation JSON>' '<runtime log>'
python protect_campaign.py verify 'C:\Games\_judgment-scratch\campaign-protection-20260930-skeletalmesh.json'
```

PrototypeTrace is enabled by default; the harness requires completed world ticks
within the final 15 seconds. Tests use NOHOMEDIR and stop only tracked helpers.
Optional `-SampleStackAtSeconds 45 -DebuggerExe '<x86 cdb.exe>'` performs read-only,
noninvasive inspection of that exact test PID and detaches afterward.

## Limits and next work

This is a functioning **headless loading/world-tick prototype**, not verified
visible or playable gameplay. Baird's SkeletalMeshComponent still has a NULL
SkeletalMesh, producing bone/socket warnings. External texture mip bulk data is
missing; GPU detiling and texture-cache recovery remain required. The final log
also records script Accessed None warnings, mostly GearAI.AILog_Internal, plus
inventory/view-target/stat-interface initialization warnings. Collision, cover/AI
behavior, input, visible rendering and audio playback are unverified.

The next priority is player mesh/appearance initialization and a visible render
test with usable texture data. Further streaming package conversion remains
available: SP_E2_03_S assessment has 788 exports, 687 complete, 101 unmodelled
tails (93 MorphTarget, four MorphTargetSet, four variable-key AnimSequence).
That assessment remains unstaged; the converter deliberately rejects its codec.

Final protection verification: **20,284 files checked, zero changes** in the two
campaign installs and shared engine source. Proprietary content, engine source,
binaries, symbols and private patches are excluded from converter commits.
