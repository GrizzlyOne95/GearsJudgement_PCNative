# Judgment native-port - build-tree status

## Session XXVI (2026-09-30): guarded AI singleton/accessor experiment

All work stays in this separate source/game copy. The new PDB reader validates
213,859 public symbols and selects 578 AI interface records from the original
Release debug file. Its GUID/age matches the original image. Native inspection
shows that full AISystem behavior needs ETQSystem, AISpawnManager and AIDebugTool
Init/Tick; AIDirector needs its finite-state machine. These remain unported.

Experimental loader: GearGame-JudgmentLoader-ws19-ai-accessors-v2.exe,
59,433,472 bytes, SHA-256
78371AE6D7A9D82644DAB33D0B4F4ECB87BC86CD3C376F49F0F1175EC083D971.
Private patch 0019-ws-ai-accessors-prototype.patch: 5,548 bytes, SHA-256
fabe7279a2e9c454c7dea2e51eb97bd8c7951b85d391fe90ac2142983f2d63eb.
Reverse/forward application reproduces both source files exactly.

-JUDGAIACCESSORS selects prototype native bindings. Three original companion
controllers (Carmine, Barrick, Gus) get the same rooted Transient.AISystem_0,
not a CDO, and live Transient.SmartSpawner_0 reaches SetInstance. The three
null AISystem possession warnings disappear. Missing Squad and AI logging
warnings remain. Native Init/Tick and map cleanup are explicitly incomplete;
this layer does not establish an encounter or companion movement.

100-second D3D9 test passes original startup and objective 1: 11,374 exact
loads, zero size mismatches/fatal errors, 15 paired ticks (last 98.87 seconds,
game time 68.453), seven levels and 4,010 presents (last 95.37 seconds).
The campaign gate verifies three callers, a real singleton/live spawner, and
the explicit partial-init disclosure. Its report retains the limits.
138 unit tests pass, including 17 PDB and 10 accessor evidence cases.

The harness still defaults to ws18. With the AI flag off, ws19 uses the old
native lookup tables. Full encounters, checkpoint restoration, AI movement,
main-campaign route, input and streamed lighting remain unverified.
Final flag-off PkgInfo/thin-map/SP_E2_P controls pass; the mission passes its
startup/objective gate with 11,374 exact loads and ten paired ticks (last 71.29 s).
There are no prototype markers, and the prior three null-system possession
warnings/accessor fallbacks remain, confirming that the new behavior is conditional.
See NostalgiaBundle/projects/judgment-native/AI-NATIVE-CHECKPOINT.md.
Protected Gears 3 verification: 20,284 files, zero changes.

## Session XXV (2026-09-30): original campaign startup and first objective

Read-only sequence tracing confirms the original Aftermath startup graph runs
through streaming, four squad factories, the checkpoint action, cinematic-mode
release, camera fade, chapter title and the first objective. Loaded script
reflection confirms objective 1 in the real local-player GearObjectiveManager,
with completed/failed false. The probe injects no events or objectives.

Independent original/converted comparisons preserve 510 sequence objects,
210 connected outputs and 225 variable references across the three mission
script maps. 111 unit tests pass. The harness -CampaignStartup option requires
ordered startup and objective state; loader survival alone cannot pass it.

Accepted loader: GearGame-JudgmentLoader-ws18-sequence-objectives.exe,
59,429,888 bytes, SHA-256 8C0D1079302C8039CE6C082570A19F82C62BD33F8FF55F4327280CB9BB2AC312.
Private patch 0018-ws-sequence-objectives.patch:
E82C494919B013A44E4B0BA475B0D206169C9D05BF8530152043D3441E01637A.
Reverse/forward replay reproduce source before/after byte-for-byte.

100-second D3D9 test passes 11,374 exact loads, 15 paired ticks, 4,319 presents;
final 75-second PkgInfo/thin-map/SP_E2_P suite passes with campaign proof.
Screenshot00005 remains dark/blue. No rendering fix or playable encounter claim.

Observed gameplay fallbacks: AIDirector.Init, AISystem.GetInstance,
SmartSpawner.SetInstance, SmartSpawner.RunVisibleSpawnPointsCheck, GearAI.PickGoal.
AI-system/squad warnings remain. Native director/spawn reconstruction, checkpoint
save/restore, input, encounters and main-campaign route still require validation.
See NostalgiaBundle/projects/judgment-native/CAMPAIGN-STARTUP-CHECKPOINT.md.
All work stays in this separate copy. Protected Gears 3: 20,284 files, zero changes.


## Session XXIV (2026-09-30): texture recovery and resolved Baird materials

The separate workspace now stages 30 recovered textures / 291 inline PC mips.
Baird's six textures select the intended PC body, eye and hair master materials.
The missing parents were caused by inheriting PKG_RequireImportsAlreadyLoaded
from the monolithic startup package; explicit extraction --resolve-imports clears
only that flag. All source, binaries, content and tests remain in this copy.

Accepted artifacts:
- Baird asset-v4-deps: 118,700,264 bytes, BA5FBC78DD44680DD934912D12433C21EC13F7E975144C47159D28430F84371E.
- SP_E2_P textures-v2: 25,859,182 bytes, E99602F9221A3063E771488EC09A39C9F182A5E748B7CFE961E80D847261307C.
- ws17-material-trace loader: 59,422,720 bytes, 794CFE38D3207A69EB27793AED577337EFCFF738DC43D5F1F3CADCFC4A309C41.
- Private patch 0017-ws-material-trace.patch: 431D7717D05B664D610B410FE02D393C2AB489DF2DD2DA7BC52427833B3C5187.

Final corrected-base 100-second D3D9 test passes: 11,374 exact native loads,
zero size mismatches/fatal errors, 15 paired ticks (last 98.25 seconds), 4,319
presented frames (last 99.64 seconds). ScreenShot00004.bmp shows recognizable
armor detail but remains dark with a blue cast. Screenshot SHA-256:
E3DE45540FA728FB69C24971109BC1CA11E03B2A021D114B5FE7031A5BF35ABC.
PkgInfo, thin-map and SP_E2_P headless tests on ws17 also pass. 83 unit tests pass.

The first LUT attempt incorrectly assumed omitted MipTailBaseIdx meant -1 and
produced black pixels; base-textures-v1 is rejected. The actual default is zero.
The corrected 256x16 one-mip lookup matches all 4,096 pixel/16,384 byte addresses
measured using Judgment's own Xbox360Tools cooker. Six streamed map archives,
animations and navigation data remain unchanged. Streamed lightmaps, shadow maps,
environment pixels, material dependency coverage and playable input, collision,
AI/cover, inventory and audio remain outstanding.

Tooling/evidence: NostalgiaBundle\projects\judgment-native\TEXTURE-PROTOTYPE-CHECKPOINT.md.
Protected Gears 3 baseline: 20,284 files, zero changes. Only original tooling and
docs are pushed on the two separate Judgment branches; retail assets, engine
source and private patches/binaries stay outside Git.


## Session XXIII (2026-09-30): Baird mesh and first rendered prototype

The isolated `judgment/port-workspace` now runs a 100-second D3D9 prototype
with 11,374 exact native loads, zero size mismatches/fatal errors, seven levels
and 3,825 recorded 1280x720 presentations. Baird uses the intended Judgment
mesh and physics asset with 123 bones/local atoms/space bases. The engine's
`GearGame\ScreenShots\ScreenShot00000.bmp` shows the player and geometry,
although textures and lighting remain visibly incorrect. Gameplay is unverified.

Current accepted loader: `GearGame-JudgmentLoader-ws16-render-prototype-v2.exe`,
59,420,672 bytes, SHA-256
`89C042031C526FD86A94F30600AFBC26644729A2D2704BCBF6CD47F8EFD0E646`.
Use v2, which includes screenshot screen-message restoration. Private patches
0015 (player mesh trace) and 0016 (early explicit NoTextureStreaming, D3D9
presentation trace and opted-in screenshot) pass reverse applicability checks.

`COG_Baird_Jack.gear` adds 108 extracted startup asset exports to the seven
unchanged maps: 12,812 staged exports. The converter remaps 156 typed references
and emits 56 imports without relocating bulk data. Source asset v1 and ws15's
D3D9 mip-copy failure are retained rejected evidence. Only asset v2 is staged.

Final ws16-v2 PkgInfo, 75-second thin-map and SP_E2_P headless tests all pass.
72 unit tests pass, all seven maps regenerate identically, native animations
and base packed-position samples retain their independent validation. Next:
texture caches, mip tails and detiling, then camera/input and gameplay checks.
All helpers stopped; 20,284 protected files verified, zero changes.

Full checkpoint: `C:\Games\NostalgiaBundle\projects\judgment-native\PLAYER-RENDER-CHECKPOINT.md`.

## Session XXII (2026-09-30): animations load and headless world ticks continue

Converter continues from `3acd5d1` on `judgment/skeletalmesh-20260930`; this full
copy remains on `judgment/port-workspace`. Seven staged maps total **12,704 fully
converted exports**, zero partial/unsupported. Newly staged SP_E2_02_S has 2,669
exports and 2,260 observed loads. Current accepted loader is
`GearGame-JudgmentLoader-ws14-headless-streaming-init-v2.exe`, 59,417,600 bytes,
SHA-256 `C547AAA6EA69AEDD6CD0D260CAE3119FF66D3E3D90830DC9E3A51DAC0BE22DD9`.

- Final 100-second headless test: **PASS**, 11,266 exact-size native loads, zero
  mismatches/critical errors, seven loaded levels, 15 paired tick reports through
  wall-clock 96.84 seconds (serial 4,196, game time 67.850). Baird is possessed.
- All 28 animations evaluate 6,636 finite native pose samples. Independent BE/LE
  parsing preserves 3,836 encoded tracks, 48,415 keys, 453 frame tables, four
  combat maps/164 poly refs and a 32-bone aim profile. Base packed positions match.
- **65 unit tests pass**, all seven packages regenerate identically and observed
  preload offsets/classes/sizes match manifests. PkgInfo and 75-second thin-map
  regressions also pass; thin-map ticks continue through wall-clock 71.01 seconds.
- Opt-in diagnostics exposed that a live process had stopped world ticking.
  Read-only debugger stacks traced shader-cache saving and Texture2D linker
  detachment waits. The accepted fix disables texture streaming at NullRHI init,
  before startup loads, and omits local cache saves for Judgment NullRHI. The
  later NoTextureStreaming launch flag alone was insufficient. Renderer-enabled
  behavior remains normal. Native package serialization is fully exercised.
- Private patches **0011, 0012, 0014** are accepted after 0009/0010 and pass
  reverse application checks. **0013/ws13 are rejected**: omitting texture objects
  crashed ambient occlusion and was reverted. Initial ws14 contained a stale
  object from that experiment; restored Texture2D.cpp was touched and rebuilt
  into **ws14-v2**, checked to exclude the rejected code. Texture2D.cpp remains
  byte-identical to its ws13 before-image.
- This is a headless loading/world-tick prototype. Player SkeletalMesh is still
  NULL; external texture bulk mips and script initialization warnings remain.
  Visible rendering, input, physics, AI/cover behavior and audio are unverified.
  Next work: player appearance/mesh initialization and texture data for rendering.

New map `GearGame\Content\Maps\SP_E2_02_S.gear` has SHA-256
`50BB192C7B0C8161D3B2B72C760BFFD8CC1D95C60F8364626F67837759A6257E`.
The harness defaults to ws14-v2, all six converted retail streaming names,
NOHOMEDIR, NoTextureStreaming and recent completed-tick checks. Evidence:
`regress-ws14-headless-streaming-init-v2-sp_e2_p.log`,
`regress-ws14-prototype-regressions-{pkginfo,thinmap}.log`, their results JSON,
scratch animation/geometry-headless-prototype validation JSON. See converter
`ANIMATION-PROTOTYPE-CHECKPOINT.md` for exact accepted patch hashes and reproduction.

Final protected campaign/source verification: **20,284 files, zero changes**.
All helpers were stopped by their test deadlines; no Judgment helper remains.

## Session XXI (2026-09-30): cover/navigation package loads; next blocker is animations

Converter continues from `9c14d4c` in its isolated branch. No additional engine
changes: retained ws10 streaming/BSP loader and private patch 0010 are still used.
Final campaign protection: **20,284 files checked, zero changes** in both campaign
installs and shared source. No Judgment helper remains running.

- SP_E2_01_S **560/560** and SP_E2_Audio **8/8** exports fully convert. All six
  staged packages total **10,035/10,035**, zero unsupported/partial.
- Native loading: **9,006 exact-size loads**, zero mismatches. Four navigation
  meshes/two pylons load, including all 681 typed edges; world ticks/Baird possession.
  SP_E2_01_S contributes 428 loads, audio level seven. Headless serialization only;
  AI traversal, cover behavior, collision, rendering and audio remain unverified.
- Cooked cover structs use declaration-order property chains, one BYTE per script
  bool, FName enums, skipped native/transient fields and tagged BasedPosition values.
  Navigation v43 matches engine grammar: WORD indices, mixed storage records,
  transforms, border segments, bounds, typed edges. No serializer bypasses.
- 59 unit tests pass. Independent conversion regeneration, package tables,
  source/LE navigation values and topology, every native preload offset/size, BSP
  expansion and packed skeletal-position checks all pass.
- Next failure: missing `SP_E2_02_S`; error shutdown then access-violates. That
  run is recorded as BLOCKED_AFTER_BOOT. SP_E2_02_S assessment: 2,669 exports,
  2,636 complete, one partial Profiles array, 28 AnimSequence and four CombatZone
  native tails unmodelled. Partial output remains in scratch, not staged.

New staged files only in this workspace's Content\Maps: `SP_E2_01_S.gear` and
`SP_E2_Audio.gear`. Launch whitelist now includes those two plus SP_E2_01,
SP_E2_02 and SP_E2_W. Every test uses `-NOHOMEDIR` in this copy.
Evidence: `GearGame\Logs\regress-ws10-navigation-audio-sp_e2_p.log` and results JSON;
scratch `geometry-navigation-audio-20260930.validation.json` and
`navigation-20260930.validation.json`. Converter `NAVIGATION-CHECKPOINT.md`
contains exact artifact hashes and reproduction commands.

## Session XX (2026-09-30): three retail streaming maps load; BSP stride fixed

All work stays in this isolated `judgment/port-workspace` copy and converter branch
`judgment/skeletalmesh-20260930`. Builds never touch shared campaign source.

- Fully converted exports: SP_E2_P **1,433/1,433**, SP_E2_01 **4,919/4,919**,
  SP_E2_02 **3,054/3,054**, SP_E2_W **61/61**, zero unsupported/partial.
- Native runtime: **8,571 exact-size loads**, zero size mismatches. Three streaming
  maps deserialize/post-load; Baird is possessed and the world ticks. Next explicit
  blocker: missing `SP_E2_01_S` gameplay/navigation package.
- Bounded native serializers now cover static/fractured geometry, BSP, component
  LODs, lightmaps, decals, convex cache containers, collections and populated Level
  lighting/visibility. Native FColor values swap as DWORDs. Dominant lights require
  a WORD shadow-map array before the normal UObject prologue.
- Retail names require `-JUDGMENTSTREAMINGPACKAGES=SP_E2_01,SP_E2_02,SP_E2_W`,
  in addition to v845 and loader opt-in. PC content keeps its normal layout.
- Populated BSP exposed a memory-stride bug: console FVert 16B bulk data was being
  packed into PC FVert 24B arrays. Explicit per-record expansion clears the
  `UModelComponent::BuildRenderData` assertion. Preload telemetry includes package
  names; independent manifest/topology checks match all loaded records.
- PkgInfo and thin-map regression pass. 50 converter tests pass; previous packed
  skeletal-position telemetry remains valid. Tests use `-NOHOMEDIR` in this copy.
- Headless loading only. Missing mip bulk data warnings remain; visible rendering,
  external texture caches, codecs, collision and campaign gameplay need validation.

Loader: `Binaries\Win32\GearGame-JudgmentLoader-ws10-streaminggeometry-verts.exe`,
SHA-256 `9710D48EE86D3F39C8BF41EF96B2D83CA34BE38212F76CFDD75E60D59FF17A82`.
Private incremental patch: `patches\judgment-port\0010-ws-streaming-geometry.patch`
(apply after 0009; reverse check passes with `--ignore-whitespace`).
Staged maps only under this workspace's `GearGame\Content\Maps`:
`Judgment_SP_E2_P.gear`, `SP_E2_01.gear`, `SP_E2_02.gear`, `SP_E2_W.gear`.
Prior map-stage backups and original checkpoint artifacts are retained in scratch.

See converter `STREAMING-GEOMETRY-CHECKPOINT.md` for exact artifact hashes,
reproduction/recovery commands and retained regression logs. Final runtime evidence:
`GearGame\Logs\regress-ws10-streaminggeometry-e2w-sp_e2_p.log` and results JSON.
`_judgment-scratch\e2-surface\geometry-e2w-20260930.validation.json` independently
checks the four retained archives, BSP references and all 8,571 native loads.

Next package SP_E2_01_S: 560 exports; 438 fully converted, 116 partial, six native
tails unmodelled. CoverSlot arrays, ActorReference/RouteList, NavigationMeshBase
and Pylon need explicit models. Its partial output is not staged.

## Session XIX (2026-09-30): skeletal meshes complete; SP_E2_P boots and possesses Baird

Continued from converter `3baf313` on separate branch `judgment/skeletalmesh-20260930`.
All source/build/map staging stayed in this isolated `judgment/port-workspace` copy.
Campaign rebuild, Jacinto 1.1.1 and shared campaign source: 20,284 protected files,
zero changes; test launches use `-NOHOMEDIR` for local config/save writes.

- Converter: **1,433/1,433 exports** fully converted, zero unsupported or partial.
  Complete skeleton/LOD/influence/trailer model preserves mesh data; packed positions
  are expanded by the PC loader. Only the three mesh tails differ from checkpoint ws7.
- Native test: **1,402 exact-size export loads**, zero mismatches. All three meshes
  load, four packed LODs expand; first-position telemetry matches independent decoding.
- `Judgment_SP_E2_P` reaches map-loaded, first world tick, Baird spawn and possession.
  Next failure: `Couldn't find file for package SP_E2_01 requested by async loading code.`
  Headless boot is proven; visible map rendering and a playable campaign remain unverified.
- PkgInfo exits 0; the thin-map possession regression stays alive for 75 seconds.
  Converter tests: 39/39. Independent package parser: zero invalid references,
  24/24 valid texture frames, 254/254 valid sound frames.

Loader: `Binaries\Win32\GearGame-JudgmentLoader-ws9-skeletalmesh-verified.exe`,
59,406,336 bytes, SHA-256
`C0B765E284970D0A53447C0D2C7BF465FA457A9E9A0D3BF6A70A08FD09EB5AE7`.
Private/untracked source patch: `patches\judgment-port\0009-ws-packed-skeletalmesh.patch`.

Staged map: `GearGame\Content\Maps\Judgment_SP_E2_P.gear`, 11,814,162 bytes,
SHA-256 `6B3893A3C6830AF6DCE5F1EDB0C2502852B4D970D8B1B3F2660A19AAEB11E3B0`.
Runtime evidence: `GearGame\Logs\regress-ws9-skeletalmesh-{pkginfo,thinmap,sp_e2_p}.log`
and `regress-ws9-skeletalmesh-results.json` (SP_E2_P is explicitly BLOCKED_AFTER_BOOT).

The converter is now a git repo at
`C:\Games\NostalgiaBundle\projects\judgment-native`.
`SKELETAL-MESH-CHECKPOINT.md` there records reproducible commands, hashes and source-patch
recovery details. Do not replace it with the older tooling repo's converter.

Next fixture `SP_E2_01` has 4,919 exports: 3,039 convert, 1,880 geometry/lighting/component
tails remain. Its assessment output is retained in scratch and is not staged into the runtime.

## Session XVIII (2026-09-30): isolated workspace; 37 MB UClass read and enum-byte blockers closed

### Isolation (read first)

`gears_of_war_3_2011-09-14\Development\Src` is now the **Gears 3 campaign / Steam co-op source** -
the shipping `GearGame-Campaign-Steam-coopfix-*` executables are built from it. Judgment work must
never build or edit there. All Judgment work now happens in:

- `C:\Games\Gears 3 Files\Judgment Port Workspace` - git worktree, branch `judgment/port-workspace`,
  plus an untracked full copy of the build tree. `Development\Src` was seeded from
  `_Backups\src-judgment-20260919` (the Session XIV source; `Development\Src.judgment-20260919`
  in the shared tree has partially regenerated headers - do not use it). Campaign object files were
  not copied, so the first build was clean.
- Tooling repo `GearsJudgement_PCNative`, branch `judgment/workspace-isolation`: every script that
  hard-coded the shared tree (`apply-deltas.py`, `fix_member_deltas.py`, `sweep_v3.py`,
  `verify-thin-map.ps1`, `build-judgment-loader.ps1`, `xg-tail-oracle\build.ps1`) now points at the
  workspace. Build with the working directory at `Development\Src`:
  `scripts\build-judgment-loader.ps1 -SourceRoot "<workspace>" -VersionTag <tag>`.
- The newest converter is `C:\Games\NostalgiaBundle\projects\judgment-native` (now under git; it is
  ahead of the tooling repo's `content-converter`).

### Blocker 1 - 37 MB `ReadFile` during `GearPawn_CCarmine` (Session XVI/XVII) - ROOT-CAUSED, FIXED

`IsPackageCookedForConsole()` (`UnScriptPatcher.h`) opts `Judgment_*` packages into the console
cooked layout via `ParseParam(appCmdLine(), "JUDGMENTPKGVER")`. `ParseParam` only matches a flag
followed by whitespace/end (`UnMisc.cpp:2322`); every documented launch passes
`-JUDGMENTPKGVER=845`, so the opt-in **never fired**. `UStruct::Serialize` therefore read the PC
editor layout (+ScriptText/CppText/Line/TextPos) over the stripped class and took
`ScriptStorageSize` from bytes 172431..172434 = `0x02360000` = 37,093,376. The reader copied the 621
buffered bytes up to its 1 KB boundary (172435 -> 173056) and requested the remaining
**37,092,755** - the exact logged length. The class bytes and `tail_class` were always correct; the
Session XVI "UClass overran by 503 bytes" reading and the XVII debugger plan are superseded.

Fix: accept `-JUDGMENTPKGVER=<n>` via `Parse()` in that one gate.

Follow-up (same day, user-approved): the three other gates with the same broken
`ParseParam(..., "JUDGMENTPKGVER")` - rooted linkers (`UnLinker.cpp:854`), forced sync tables
(`:884`) and plain file readers (`:1100`) - had **never been active in any logged run**, so the
"Exonerated mechanisms" v21/v22 results were tested with them off. All four gates now call
`JudgmentPackageVersionOptIn()` (`UnScriptPatcher.h`). Turning them on exposed:

- a latent crash: `JUDGMENT_LINKER_ROOTED` passed `*Filename` (one TCHAR) to `%s`; fixed.
- the converter's Session XII "FVert empty-bulk 16 -> 24 retarget" was compensating for the
  console layout being off. `FVert::GetSizeForBulkSerialization` returns the console size 16
  under the opt-in, so `tail_model` now keeps 16 and walks Verts as a normal `[4,4,4,4]` bulk.
  The thin map's pinned hash therefore changes (new stage `E7658EA5...`).

FaceFX (same day): Judgment FaceFX payloads are `FACB` FxArchives from SDK 1740 / file format 0,
exactly what this engine's FaceFX SDK loads (it byte-swaps big-endian archives itself). The
converter now swaps only the two UE3 array counts. `SP_E2_P` loads **84** exports exactly; the
next blocker is export 69 `Helmet_MASTER` (`Material` native tail - `FMaterialResource`).

Regression runner: `GearsJudgement_PCNative\scripts\run-judgment-regressions.ps1 -Exe <loader>`
(PkgInfo clean exit / converted thin-map boot + possession / SP_E2_P exact-size preloads).
`GearGame-JudgmentLoader-ws4-optin-all.exe` (`0D4AF80E...`) passes all three.

### Blocker 2 - `Bad name index -553451520/1773` in `GSG_COG_Barrick` - ROOT-CAUSED, FIXED (converter)

`be2le.py` mapped `ByteProperty` to an empty width list, so an enum-backed byte tag (Size 8, value
is an FName) was skipped **silently** - left big-endian and not counted as unsupported. Only byte
*arrays* had been fixed in Session XIV. SP_E2_P had 840 such values (GearSoundGroup `Id`s,
Texture2D/SoundCue enums, ...). Now swapped explicitly, fail-closed on an out-of-range FName;
3 new tests (24/24 pass).

The 2026-09-05 blind 4-byte-swap handlers `tail_skeletalmesh` / `tail_facefx` were unregistered:
they bypassed the fail-closed policy and were motivated by blocker 1, which they could not fix.

### Result

- Converter: `SP_E2_P.enumbyte.le.xxx` SHA256 `D681F5FC...A166FB`: 1,410/1,433 fully converted,
  0 partial, 23 unmodelled tails. Diff vs the old `48B1CAF5` stage = the structured `Polys` model
  plus 840 enum words, all now valid name indices.
- Loader `Binaries\Win32\GearGame-JudgmentLoader-ws2-consolelayout.exe`
  (SHA256 `CBEBCEC3...8B3559`): `Judgment_SP_E2_P` loads 62 exports with exact
  `consumed == SerialSize` (was 0 before blocker 1, 27 before blocker 2).
- Next blocker: export 38 `COG_Gus_Summer_FaceFX_Efforts` (`FaceFXAnimSet`, 177,135 B) - an
  unmodelled native tail, so it fails closed exactly as intended (`Array.h:756 ArrayNum >= 0`).
  FaceFX payloads are FaceFX's own endian-specific archive, so this needs a real format model.
- New diagnostics: `-JUDGPRELOADTRACE` logs `[JUDGPRELOAD] enter/leave` with export index, class,
  offset, size and consumed bytes for `Judgment_*` packages; the file-reader failure now reports
  `Pos`/`Size`. Engine changes: `patches\judgment-port\0007-ws-consolelayout-optin-preloadtrace.patch`.

Repro:

```
GearGame-JudgmentLoader-ws2-consolelayout.exe Judgment_SP_E2_P?game=geargamecontent.GearGameAID?listen
  -user -JUDGMENTPKGVER=845 -JUDGNATIVEBINDOK -JUDGLIFE -JUDGPRELOADTRACE -forcelogflush
  -unattended -nopause -nosound -nullrhi -ABSLOG=<log>
```

## Session XIV (2026-08-26): first campaign package is 96.2% structurally converted

- `SP_E2_P` was decompressed and measured as the first full campaign package: 1,433 exports,
  291 imports, 11.1 MB serialized payload.
- The converter now rewrites `SoundNodeWave` bulk headers without touching Xbox XMA bytes. This
  is an explicit `-nosound` structural-load stage; Ogg transcoding remains future work.
- Source-backed empty native tails and primitive/enum/string arrays raised the result to
  **1,378/1,433 fully converted exports**, zero partial property exports.
- Independent package-probe validation: exact import/export table ends, zero invalid references,
  and 254/254 SoundNodeWave payloads with valid tagged/bulk framing.
- Thin-map regression remains hash-identical and its converter/staged-map/schema inputs are now
  verified by a permanent script. The temporary build batch was replaced by a permanent loader
  build script; it reproduced the 59,447,808-byte executable successfully.
- Remaining `SP_E2_P` frontier: 24 textures and 31 other native payload/tail exports, led by
  Model/Polys/Level, material/physics, FaceFX, meshes, populated ShaderCache and four Class exports.

<!-- NEXT SESSION: start at "Session V" below (CameraAnim blocker CLOSED -
dup FPointer vtable slots stripped from 10 classes). PkgInfo now exits clean;
next frontier = live gameplay instantiation / map load against the remaining
19 MEMBER_DELTA / 29 SIZE_MISMATCH sweep buckets - re-baseline several as
F-prefixed-interface dups or +N tail artifacts using compile-time probes
([JUDGPROBE-*] pattern in GearGame.cpp). Known-good binary:
Binaries\Win32\GearGame-JudgmentLoader-v54.exe (=v55-fix content).
Build with Temp\opencodeuild-judgmentloader.bat; camera trace flag
-JUDGCAMTRACE; sweep via python Temp\opencode\rerun-sweep.py. -->


Living status document for the native-port work performed inside this Gears 3 source
tree (custom `Binaries\Win32\GearGame-JudgmentLoader-vN.exe` diagnostic loaders).
Full technical narrative lives in the tooling repository:
`C:\Games\NostalgiaBundle\projects\GearsJudgement_PCNative\PORTING-NOTES.md`.

## Session III (2026-08-24, later): member-delta sweep - 99 classes fixed; new blocker exposed

- `fix_member_deltas.py` (committed): for each MEMBER_DELTA class, generates decls
  for v845-added members from package payloads (VfTable_IInterface_* emitted as
  `FPointer` per Infantry precedent; `_DEPRECATED` members renamed back to their
  v845 names), reorders to chain order, simulation-verifies before staging.
  100 staged -> 99 applied (WorldInfo correctly refused: padding-member judgment call).
- Compiler-driven cleanup of stale references (`fixbuild.py` loop: C2065/C3861 ->
  rename or drop stale VERIFY anchors). BUILD CLEAN.
- Result: sweep verdicts improved 1,886->1,982 OK; MEMBER_DELTA 109->19;
  SIZE_MISMATCH 29 unchanged. Patches for the full round exported as
  patches/judgment-port/0005-member-delta-sweep-v845.patch (30 files).
- NEW BLOCKER (regression vs v51 clean exit): exit purge now fails fast on
  `Default__GearPC_MP` `PostProcessPresets` (num=4 max=4 data=NULL). Evidence:
  `[JUDGLOAD][REPLACE] cls=GearPC_MP old=5260 new=5256`; AController verified by
  compile-time probes as exactly 880 (=v845), so ancestor drift is RULED OUT and
  the old!=new replace deltas are a separate benign registration-vs-relink size
  artifact. Working hypothesis: the class-replace/defaults-reload path drops the
  Data pointer of dynamic-array CDO defaults (Num/Max survive) - likely latent,
  first VISIBLE now because the 99 fixes let more CDO defaults deserialize at all
  (v51 silently had num=0). Next step: instrument FArrayProperty default reload
  under -JUDGMENTREPLACEWATCH (log Inner ElementSize + Data around replace), then
  fix the reload path rather than layouts.

### Session III addendum (same night): replace-artifact confirmed; tolerance flag shipped

- Compile-time probes prove sizeof(AController)==884 vs relinked 880 (+4 tail
  alignment from 8-aligned members like Actor.HiddenEditorViews). Registration-
  size vs relinked-size deltas ([JUDGLOAD][REPLACE] old!=new) are therefore a
  BENIGN, systemic artifact - not the corruption source.
- Real mechanism of the GearPC_MP failure: during exit purge a NESTED
  StaticAllocateObject re-creates the CDO mid-destroy; the fresh object's
  defaults reload leaves SOME dynamic arrays as Num==Max>0 with Data==NULL.
  Neither ImportText nor SerializeItem creates that state (both instrumented,
  zero hits) -> the writer is still unidentified (suspect: custom copy/reload
  glue in the fork).
- Shipped -JUDGMENTARRAYNULLOK: DestroyValue tolerates the Num==Max>0/Data==
  NULL signature (nothing to free), logs every instance, continues. First run
  with it: 4 arrays tolerated; purge then progressed to a DIFFERENT, genuine
  garbage-layout victim (GearPawn:BodyStance.Stance num=0 max=54706792 on
  Default__GearPawn_LocustBoomerBase) - consistent with the 19 MEMBER_DELTA /
  29 SIZE_MISMATCH classes still outstanding.
- UnObj.cpp was restored from _Backups/src-port-snapshot-20260824 after a bad
  auto-edit, then today's intended edits were re-applied (probe printer +
  exit/CDO guard + widened name-gated suppression experiment).

### Session III finale: MI double-count root-caused and fixed; purge blocker GONE

ROOT CAUSE of the GearPC_MP / post-delta regressions: my member-delta generator
added explicit `FPointer VfTable_*` props for chain entries that were ALREADY
provided by multiple-inheritance interface bases in the C++ headers
(e.g. AController : public AActor, public IInterface_NavigationHandle).
The MI secondary-base vptr occupies exactly the slot the chain lists; adding the
prop double-counted +4 per interface, cascading through every descendant
(AController 884 vs 880, AGearPawn 5680 vs 5660, LocustBase/BoomerBase +32 ...).

FIX: strip-dup script removed 64 duplicate `FPointer VfTable_*` decls across all
Inc headers where a matching `public I<Name>` base exists. Compile-time probe
verification after rebuild:
  sizeof(AController)=880 (=v845)   sizeof(AGearPawn)=5664 w/ every probed
  member offset == v845 chain       sizeof(LocustBase)=6048 (=v845)
  sizeof(BoomerBase)=6192 (=v845)   BoomerBS_WeaponFire=6052 (=v845)

RESULT: exit-purge GearPC_MP blocker ELIMINATED. Load now progresses deeper than
ever (into Effects_Gameplay packages) before hitting the next genuine victim:

NEW LIVE VICTIM: UCameraAnim::PostLoad -> CalcLocalAABB fatal during startup
package load. CameraAnim chain: BoundingBox @68 (28B), BasePPSettings @96
(elem=312 = FPostProcessSettings). Prime suspects: FPostProcessSettings/Canvas
family (+8 SIZE_MISMATCH still outstanding) and/or InterpTrackInstMove (+12).
NOTE: v51 also loaded this path successfully - so either a delta fix changed an
Interp/Camera dependency layout incorrectly, or previously-garbage reads happened
to be benign and correct data now exposes a real bug in CalcLocalAABB's walk.
Investigate with probes on UCameraAnim/InterpGroup offsets first.

SWEEP TOOLING TODO: teach sweep_v3 that VfTable_<IF> chain entries satisfied by
an MI base are OK without explicit decls (removes ~64 phantom MEMBER_DELTA
verdicts; current counts show them as noise).

Remaining known buckets: 19 MEMBER_DELTA / 29 SIZE_MISMATCH (pre-strip counts;
re-baseline after MI-aware sweep).

## Milestone reached (2026-08-24, session II): CLEAN EXIT - PURGE COMPLETES

`PkgInfo` on v845 now runs end-to-end: full script load (`Success - 0 error(s),
0 warning(s)`) AND `StaticExit` incremental purge completes with exit code 0
(`JudgmentLoader-v51.log`, ~28 s). The reorder-class purge crash family is closed.

What fixed it (all verified by offset simulation BEFORE build):

| Change | Effect |
| --- | --- |
| `AGearAI` props block reordered to v845 chain order | first observed victim (~AGearAI TArray free) |
| FileWriter / GearEngine / GearGRI / GearPawn_LocustCorpserLarvaUndergroundBase / GearSpawner / SeqAct_DummyWeaponFire reordered | second victim wave (UGearEngine FString free et al.) |
| `AGamePlayerController`: removed `FName CurrentSoundMode` (+ its VERIFY line) â€” v845 dropped it | parent-size delta shifted every GearPC-family descendant; was masquerading as a GearPC/FortUpgradeList issue |

Tooling added this session:

- `-JUDGMENTLAYOUTALL` / `-JUDGMENTLAYOUTCLASSES=`: generic per-class relinked-chain
  dump at destroy time (UnObj.cpp ExitProperties), one `[JUDGLAYOUT][CLS:name]`
  table per class. A full-run database (4,778 classes) lands in the log.
- Hierarchy-aware sweep (`sweep_v3.py`, committed in the GearsJudgement_PCNative tooling repo): parses all
  CLS tables, builds the class/parent graph from headers, anchors each class at
  its parent's logged v845 size, simulates x86 packing (align<=4, bitfield dword
  runs), and only stages a reorder when EVERY simulated offset reproduces the
  v845 table exactly. Verdict buckets over the whole tree: 1,886 OK / 114
  reorders applied / 109 MEMBER_DELTA / 29 SIZE_MISMATCH / 3 EXTRA_IN_HEADER /
  10 NO_PARENT_CHAIN.
- Lessons: anchor child layouts at PARENT size, never min-own-offset (min
  hides parent-size drift); classify member add/remove separately from pure
  reorder before staging anything; multiset-check both sides symmetrically.

Known remaining deltas (do NOT block script load/PkgInfo, will matter when
instantiating live gameplay objects): the 109 MEMBER_DELTA + 29 SIZE_MISMATCH
classes listed by sweep_v3 (Canvas +8, GamePlayerCamera +12, LandscapeComponent
+20 ...). Next phase: extend gen_native_block.py to emit BEGIN/END PROPS blocks
from package payloads (member names/types/order from the v845 exports), then
sweep those two buckets until every dumped class verifies OK.

## Milestone reached (2026-08-24): FULL SCRIPT LOAD SUCCEEDS

`PkgInfo` on the v845 Judgment startup script set now completes in the v828-native
Win32 runtime with **`Success - 0 error(s), 0 warning(s)`**
(`JudgmentLoader-v46.log`, 36 s run). Core.u / Engine.u / GameFramework.u / IpDrv.u /
UnrealEd.u / GearGame.u all load; 1,834 bytecode windows walked by the new flight
recorder without a single stream desync. The original `GearAI_Cover:CheckForVehicleImpl`
crash is gone.

## Remaining blocker (next phase)

Exit-time (`StaticExit`) incremental purge still faults on classes whose v845 layout
was *reordered* rather than resized â€” first observed `AGearAI::~AGearAI` freeing a
`TArray<AActor*>`. Proof collected (`-JUDGMENTLAYOUTDUMP`): GearAI totals match
exactly (both 1924) but member offsets are shuffled (TetherPosition 960â†’1460,
CombatMood 1800â†’961 with elem 4â†’1, etc.), so post-relink destruction reads wrong
slots. Same family already fixed by exact-layout matching: MIC editor class
(v45â†’v47: ParameterGroups refactor, old arrays kept native-only).

Next phase plan: build a generator that emits each affected class's `BEGIN/END PROPS`
block directly from the runtime `-JUDGMENTLAYOUTDUMP` tables (names+types from current
headers, order/bitfields from v845 offsets), then sweep all GearGame/Engine classes
until purge completes. Diagnostics to keep: allocation-size ledger, array-destroy
validator, flight recorder, layout dumper â€” all flag-gated and fail-fast.

## Root cause of the old wall (proven)

The "linker heap smash" was never a loader-stream problem. Chain:

1. Several replaced classes had native sizes â‰  v845 reflected sizes
   (`SeqAct_ControlGameMovie +4`, `OnlinePlaylistManager +16`,
   `Gear_GrappleHookMarker +60` via missing base `SpawnPoint`,
   `GearSeqVar_Player +16`, `SeqAct_ChapterComplete +16` via re-parent to
   `SeqAct_Latent`, `GearPawn_Infantry +16` via removed MI bases +
   removed tail floats in `AGearPawn`).
2. After the script UClass relinked, replacing the older, smaller native
   allocation ran `appMemzero(Obj, InClass->GetPropertiesSize())`
   (UnObj.cpp StaticAllocateObject) past the end of the block,
   smashing whichever permanent-pool/heap neighbor followed â€” linker
   fields in one layout, object tables in another (explains every prior
   shifting victim and the "ExportMap flips" observations).
3. On the destroy side, ExitProperties walked the relinked property chain over
   old-layout memory â†’ `UArrayProperty::DestroyValue` freed wild pointers
   (now fail-fast guarded).

Diagnostics kept behind flags (all fail-fast, SEH-guarded, safe-formatted):
allocation-size ledger + `-JUDGMENTREPLACEWATCH`, array-destroy validator (always on),
bytecode flight recorder + `-JUDGMENTLAYOUTDUMP`, `-JUDGMENTCEXLIMIT=`.
v31 lesson recorded: previous silent traces died inside their own `debugf` on
bad `%s` args â€” never pass unsanitized pointers into Logf.

## Class fixes this session

| Class | Fix |
| --- | --- |
| GameFramework.SeqAct_ControlGameMovie | + `BITFIELD InputSkipLock:1;` |
| IpDrv.OnlinePlaylistManager | + `FContentOfferId` struct, `ContentOfferIds`, `DataCenterIdOverride` |
| GearGame.ASpawnPoint | new intermediate base (+60 B) between Actor and grapple/spawn markers |
| GearGame.Gear_GrappleHookMarker | re-parented AActor â†’ ASpawnPoint |
| GearSeqVar_Player | + `bHumanOnly`, `PlayerSlotObjs` |
| SeqAct_ChapterComplete | re-parented SequenceAction â†’ SeqAct_Latent |
| AGearPawn | removed native-only `LastTaccomTime`/`PostTaccomFireDelay` (v845 dropped them) |
| AGearPawn_Infantry | removed C++ MI bases; interface tables live only as explicit `VfTable_*` props resolved by `GetInterfaceAddress`; nav-obstacle dispatch inert until glue ported |

## Milestone reached (2026-08-23)

- Core.u and Engine.u of the Judgment v845 script set load **completely** in the
  v828-native Win32 runtime with zero watchdog violations. All 45 Engine-side
  class-layout deltas are corrected in headers.
- GearGame.u loading progressed past `GearAI` (208->227 members) after correcting
  127 shared owners plus judgment-only structs (`GearGameJudgmentStructs.h`).
- Current wall: deterministic corruption of the GearGame linker heap block while
  serializing `Function GearGame.GearAI_Cover:CheckForVehicleImpl`.

## Exonerated mechanisms (do not re-investigate)

| Theory | Test | Result |
| --- | --- | --- |
| GC purged an un-rooted linker | rooted all linkers, logged CollectGarbage / Verify-orphan / BeginDestroy (v21) | no GC ran; catch path never fired |
| Precache / SHA buffer reuse | forced plain handle-backed readers (v22) | crash unchanged |
| Replace-path overflow | `_msize` trap (v23-v25; NOTE: UB on permanent-pool objects, keep removed) | zero overflows anywhere |
| Bytecode format drift v828->v845 | Python expression-walker over 4.5k functions per era (`Temp\opencode\v845drift\walk.py`) | identical match rates (72.9% vs 73.1%) and identical failure sets |
| Nested Preload inside the bytecode MemReader window | entry logging at Preload (v28) | zero occurrences |

## Confirmed layout facts (engine-verified)

`UStruct::Serialize` on-disk header = 12 dwords: Next, SuperStruct, ScriptText-ref,
Children-ref, CppText-ref, three unknown dwords (0 / children+1 / 0), Line, TextPos,
ScriptBytecodeSize (logical), ScriptStorageSize (physical). Function tail = 15 bytes
(iNative u16, OperPrecedence u8, FunctionFlags DWORD, [RepOffset u16 if FUNC_Net
0x00200000], FriendlyName q64). Bytecode pointer operands are 4-byte indices on disk
but advance the logical cursor by 8.

## Live hypotheses for the GearAI_Cover smash

1. Class/State/ScriptStruct export parsing differences (extend `walk.py`; the three
   unknown dwords appear in every UStruct).
2. Tagged-property / CDO default-value paths during class binding.
3. CreateExport reconciliation behavior for GearGame script-only classes whose
   superclasses chain into Engine.u replacements.

## Build recipe

```
$env:VS90COMNTOOLS = "C:\Games\Gears 3 Files\_Toolchain\PortableVC9\Layout\Microsoft Visual Studio 9.0\Common7\Tools\"
$env:UE3_WINDOWS_SDK_DIR = "C:\Games\Gears 3 Files\_Toolchain\PortableVC9\Layout\Microsoft SDKs\Windows\v6.0A"
Development\Intermediate\UnrealBuildTool\Release\UnrealBuildTool.exe GearGame Win32 Release `
  -OUTPUT "C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\Binaries\Win32\GearGame-JudgmentLoader-v<N>.exe"
```

Run harness:

```
GearGame-JudgmentLoader-v<N>.exe PkgInfo -user -JUDGMENTPKGVER=845 -JUDGMENTCDOWATCH `
  -forcelogflush -unattended -nopause -nosound -nullrhi -ABSLOG=<log>
```

Diagnostics flags: `-JUDGMENTPKGVER` (enable foreign-package ceiling + plain readers +
rooted linkers), `-JUDGMENTCDOWATCH` (object mutation watchdog + import/export failure
context), `-JUDGMENTSTRUCTDUMP` (UStruct field dump + bytecode-window logging).

## Class-header check (latest)

First 12 dwords of Engine.Actor / WorldInfo / PlayerController class exports are
structurally identical between v828 and v845 (only package-relative indices and
content-driven sizes differ). No header-level drift in Class exports either; combined
with the function-walker result, on-disk FORMAT drift is now excluded at both levels
examined. Remaining suspects: content-dependent paths (TMap/array counts, tagged
defaults) and CreateExport reconciliation of script-only GearGame classes.

## Reconciliation trace (v29, in progress)

Added name-gated `
JUDGMENT_EXPORT_TRACE` reconciliation logging in `CreateExport` (pre-state incl.
existing-object probe; post-state incl. resolved super/outer/flags/PropertiesSize/template).
First run: gate silent - KEY INSIGHT: the failing Function export
(`CheckForVehicleImpl`, idx 20479) precedes the `GearAI_Cover` Class export (idx 20545)
in export order, so the class object is created lazily DURING the function's preload
via `ClassIndex` -> nested `IndexToObject`/`CreateExport`. Next iteration must gate on
the function name as well and trace the nested class creation inside that window.
The crash therefore occurs BEFORE the GearAI_Cover UClass finishes construction -
narrowing suspicion to superclass/template resolution performed while creating the
class from within the function-export nesting.

### Trace-gate follow-up (v30)

Widened gate to any `GearAI*` export: still zero `JUDGMENT_RECON` lines while the
crash reproduces identically - despite the failing function's export object existing.
Open instrumentation issue: either `Export.ObjectName` for these exports does not
contain the expected string at CreateExport time, or the trace block is not on the
executed path. Next session: place a one-shot unconditional probe as the first statement
of `CreateExport` (log first N calls) to verify reachability, then move the reconciliation
trace into `IndexToObject` where the nested class creation during function preload
actually occurs.
# Judgment native-port - build-tree status

<!-- NEXT SESSION: start at "Session V" below (CameraAnim blocker CLOSED -
dup FPointer vtable slots stripped from 10 classes). PkgInfo now exits clean;
next frontier = live gameplay instantiation / map load against the remaining
19 MEMBER_DELTA / 29 SIZE_MISMATCH sweep buckets - re-baseline several as
F-prefixed-interface dups or +N tail artifacts using compile-time probes
([JUDGPROBE-*] pattern in GearGame.cpp). Known-good binary:
Binaries\Win32\GearGame-JudgmentLoader-v54.exe (=v55-fix content).
Build with Temp\opencodeuild-judgmentloader.bat; camera trace flag
-JUDGCAMTRACE; sweep via python Temp\opencode\rerun-sweep.py. -->


Living status document for the native-port work performed inside this Gears 3 source
tree (custom `Binaries\Win32\GearGame-JudgmentLoader-vN.exe` diagnostic loaders).
Full technical narrative lives in the tooling repository:
`C:\Games\NostalgiaBundle\projects\GearsJudgement_PCNative\PORTING-NOTES.md`.

## Session III (2026-08-24, later): member-delta sweep - 99 classes fixed; new blocker exposed

- `fix_member_deltas.py` (committed): for each MEMBER_DELTA class, generates decls
  for v845-added members from package payloads (VfTable_IInterface_* emitted as
  `FPointer` per Infantry precedent; `_DEPRECATED` members renamed back to their
  v845 names), reorders to chain order, simulation-verifies before staging.
  100 staged -> 99 applied (WorldInfo correctly refused: padding-member judgment call).
- Compiler-driven cleanup of stale references (`fixbuild.py` loop: C2065/C3861 ->
  rename or drop stale VERIFY anchors). BUILD CLEAN.
- Result: sweep verdicts improved 1,886->1,982 OK; MEMBER_DELTA 109->19;
  SIZE_MISMATCH 29 unchanged. Patches for the full round exported as
  patches/judgment-port/0005-member-delta-sweep-v845.patch (30 files).
- NEW BLOCKER (regression vs v51 clean exit): exit purge now fails fast on
  `Default__GearPC_MP` `PostProcessPresets` (num=4 max=4 data=NULL). Evidence:
  `[JUDGLOAD][REPLACE] cls=GearPC_MP old=5260 new=5256`; AController verified by
  compile-time probes as exactly 880 (=v845), so ancestor drift is RULED OUT and
  the old!=new replace deltas are a separate benign registration-vs-relink size
  artifact. Working hypothesis: the class-replace/defaults-reload path drops the
  Data pointer of dynamic-array CDO defaults (Num/Max survive) - likely latent,
  first VISIBLE now because the 99 fixes let more CDO defaults deserialize at all
  (v51 silently had num=0). Next step: instrument FArrayProperty default reload
  under -JUDGMENTREPLACEWATCH (log Inner ElementSize + Data around replace), then
  fix the reload path rather than layouts.

### Session III addendum (same night): replace-artifact confirmed; tolerance flag shipped

- Compile-time probes prove sizeof(AController)==884 vs relinked 880 (+4 tail
  alignment from 8-aligned members like Actor.HiddenEditorViews). Registration-
  size vs relinked-size deltas ([JUDGLOAD][REPLACE] old!=new) are therefore a
  BENIGN, systemic artifact - not the corruption source.
- Real mechanism of the GearPC_MP failure: during exit purge a NESTED
  StaticAllocateObject re-creates the CDO mid-destroy; the fresh object's
  defaults reload leaves SOME dynamic arrays as Num==Max>0 with Data==NULL.
  Neither ImportText nor SerializeItem creates that state (both instrumented,
  zero hits) -> the writer is still unidentified (suspect: custom copy/reload
  glue in the fork).
- Shipped -JUDGMENTARRAYNULLOK: DestroyValue tolerates the Num==Max>0/Data==
  NULL signature (nothing to free), logs every instance, continues. First run
  with it: 4 arrays tolerated; purge then progressed to a DIFFERENT, genuine
  garbage-layout victim (GearPawn:BodyStance.Stance num=0 max=54706792 on
  Default__GearPawn_LocustBoomerBase) - consistent with the 19 MEMBER_DELTA /
  29 SIZE_MISMATCH classes still outstanding.
- UnObj.cpp was restored from _Backups/src-port-snapshot-20260824 after a bad
  auto-edit, then today's intended edits were re-applied (probe printer +
  exit/CDO guard + widened name-gated suppression experiment).

### Session III finale: MI double-count root-caused and fixed; purge blocker GONE

ROOT CAUSE of the GearPC_MP / post-delta regressions: my member-delta generator
added explicit `FPointer VfTable_*` props for chain entries that were ALREADY
provided by multiple-inheritance interface bases in the C++ headers
(e.g. AController : public AActor, public IInterface_NavigationHandle).
The MI secondary-base vptr occupies exactly the slot the chain lists; adding the
prop double-counted +4 per interface, cascading through every descendant
(AController 884 vs 880, AGearPawn 5680 vs 5660, LocustBase/BoomerBase +32 ...).

FIX: strip-dup script removed 64 duplicate `FPointer VfTable_*` decls across all
Inc headers where a matching `public I<Name>` base exists. Compile-time probe
verification after rebuild:
  sizeof(AController)=880 (=v845)   sizeof(AGearPawn)=5664 w/ every probed
  member offset == v845 chain       sizeof(LocustBase)=6048 (=v845)
  sizeof(BoomerBase)=6192 (=v845)   BoomerBS_WeaponFire=6052 (=v845)

RESULT: exit-purge GearPC_MP blocker ELIMINATED. Load now progresses deeper than
ever (into Effects_Gameplay packages) before hitting the next genuine victim:

NEW LIVE VICTIM: UCameraAnim::PostLoad -> CalcLocalAABB fatal during startup
package load. CameraAnim chain: BoundingBox @68 (28B), BasePPSettings @96
(elem=312 = FPostProcessSettings). Prime suspects: FPostProcessSettings/Canvas
family (+8 SIZE_MISMATCH still outstanding) and/or InterpTrackInstMove (+12).
NOTE: v51 also loaded this path successfully - so either a delta fix changed an
Interp/Camera dependency layout incorrectly, or previously-garbage reads happened
to be benign and correct data now exposes a real bug in CalcLocalAABB's walk.
Investigate with probes on UCameraAnim/InterpGroup offsets first.

SWEEP TOOLING TODO: teach sweep_v3 that VfTable_<IF> chain entries satisfied by
an MI base are OK without explicit decls (removes ~64 phantom MEMBER_DELTA
verdicts; current counts show them as noise).

Remaining known buckets: 19 MEMBER_DELTA / 29 SIZE_MISMATCH (pre-strip counts;
re-baseline after MI-aware sweep).

## Milestone reached (2026-08-24, session II): CLEAN EXIT - PURGE COMPLETES

`PkgInfo` on v845 now runs end-to-end: full script load (`Success - 0 error(s),
0 warning(s)`) AND `StaticExit` incremental purge completes with exit code 0
(`JudgmentLoader-v51.log`, ~28 s). The reorder-class purge crash family is closed.

What fixed it (all verified by offset simulation BEFORE build):

| Change | Effect |
| --- | --- |
| `AGearAI` props block reordered to v845 chain order | first observed victim (~AGearAI TArray free) |
| FileWriter / GearEngine / GearGRI / GearPawn_LocustCorpserLarvaUndergroundBase / GearSpawner / SeqAct_DummyWeaponFire reordered | second victim wave (UGearEngine FString free et al.) |
| `AGamePlayerController`: removed `FName CurrentSoundMode` (+ its VERIFY line) â€” v845 dropped it | parent-size delta shifted every GearPC-family descendant; was masquerading as a GearPC/FortUpgradeList issue |

Tooling added this session:

- `-JUDGMENTLAYOUTALL` / `-JUDGMENTLAYOUTCLASSES=`: generic per-class relinked-chain
  dump at destroy time (UnObj.cpp ExitProperties), one `[JUDGLAYOUT][CLS:name]`
  table per class. A full-run database (4,778 classes) lands in the log.
- Hierarchy-aware sweep (`sweep_v3.py`, committed in the GearsJudgement_PCNative tooling repo): parses all
  CLS tables, builds the class/parent graph from headers, anchors each class at
  its parent's logged v845 size, simulates x86 packing (align<=4, bitfield dword
  runs), and only stages a reorder when EVERY simulated offset reproduces the
  v845 table exactly. Verdict buckets over the whole tree: 1,886 OK / 114
  reorders applied / 109 MEMBER_DELTA / 29 SIZE_MISMATCH / 3 EXTRA_IN_HEADER /
  10 NO_PARENT_CHAIN.
- Lessons: anchor child layouts at PARENT size, never min-own-offset (min
  hides parent-size drift); classify member add/remove separately from pure
  reorder before staging anything; multiset-check both sides symmetrically.

Known remaining deltas (do NOT block script load/PkgInfo, will matter when
instantiating live gameplay objects): the 109 MEMBER_DELTA + 29 SIZE_MISMATCH
classes listed by sweep_v3 (Canvas +8, GamePlayerCamera +12, LandscapeComponent
+20 ...). Next phase: extend gen_native_block.py to emit BEGIN/END PROPS blocks
from package payloads (member names/types/order from the v845 exports), then
sweep those two buckets until every dumped class verifies OK.

## Milestone reached (2026-08-24): FULL SCRIPT LOAD SUCCEEDS

`PkgInfo` on the v845 Judgment startup script set now completes in the v828-native
Win32 runtime with **`Success - 0 error(s), 0 warning(s)`**
(`JudgmentLoader-v46.log`, 36 s run). Core.u / Engine.u / GameFramework.u / IpDrv.u /
UnrealEd.u / GearGame.u all load; 1,834 bytecode windows walked by the new flight
recorder without a single stream desync. The original `GearAI_Cover:CheckForVehicleImpl`
crash is gone.

## Remaining blocker (next phase)

Exit-time (`StaticExit`) incremental purge still faults on classes whose v845 layout
was *reordered* rather than resized â€” first observed `AGearAI::~AGearAI` freeing a
`TArray<AActor*>`. Proof collected (`-JUDGMENTLAYOUTDUMP`): GearAI totals match
exactly (both 1924) but member offsets are shuffled (TetherPosition 960â†’1460,
CombatMood 1800â†’961 with elem 4â†’1, etc.), so post-relink destruction reads wrong
slots. Same family already fixed by exact-layout matching: MIC editor class
(v45â†’v47: ParameterGroups refactor, old arrays kept native-only).

Next phase plan: build a generator that emits each affected class's `BEGIN/END PROPS`
block directly from the runtime `-JUDGMENTLAYOUTDUMP` tables (names+types from current
headers, order/bitfields from v845 offsets), then sweep all GearGame/Engine classes
until purge completes. Diagnostics to keep: allocation-size ledger, array-destroy
validator, flight recorder, layout dumper â€” all flag-gated and fail-fast.

## Root cause of the old wall (proven)

The "linker heap smash" was never a loader-stream problem. Chain:

1. Several replaced classes had native sizes â‰  v845 reflected sizes
   (`SeqAct_ControlGameMovie +4`, `OnlinePlaylistManager +16`,
   `Gear_GrappleHookMarker +60` via missing base `SpawnPoint`,
   `GearSeqVar_Player +16`, `SeqAct_ChapterComplete +16` via re-parent to
   `SeqAct_Latent`, `GearPawn_Infantry +16` via removed MI bases +
   removed tail floats in `AGearPawn`).
2. After the script UClass relinked, replacing the older, smaller native
   allocation ran `appMemzero(Obj, InClass->GetPropertiesSize())`
   (UnObj.cpp StaticAllocateObject) past the end of the block,
   smashing whichever permanent-pool/heap neighbor followed â€” linker
   fields in one layout, object tables in another (explains every prior
   shifting victim and the "ExportMap flips" observations).
3. On the destroy side, ExitProperties walked the relinked property chain over
   old-layout memory â†’ `UArrayProperty::DestroyValue` freed wild pointers
   (now fail-fast guarded).

Diagnostics kept behind flags (all fail-fast, SEH-guarded, safe-formatted):
allocation-size ledger + `-JUDGMENTREPLACEWATCH`, array-destroy validator (always on),
bytecode flight recorder + `-JUDGMENTLAYOUTDUMP`, `-JUDGMENTCEXLIMIT=`.
v31 lesson recorded: previous silent traces died inside their own `debugf` on
bad `%s` args â€” never pass unsanitized pointers into Logf.

## Class fixes this session

| Class | Fix |
| --- | --- |
| GameFramework.SeqAct_ControlGameMovie | + `BITFIELD InputSkipLock:1;` |
| IpDrv.OnlinePlaylistManager | + `FContentOfferId` struct, `ContentOfferIds`, `DataCenterIdOverride` |
| GearGame.ASpawnPoint | new intermediate base (+60 B) between Actor and grapple/spawn markers |
| GearGame.Gear_GrappleHookMarker | re-parented AActor â†’ ASpawnPoint |
| GearSeqVar_Player | + `bHumanOnly`, `PlayerSlotObjs` |
| SeqAct_ChapterComplete | re-parented SequenceAction â†’ SeqAct_Latent |
| AGearPawn | removed native-only `LastTaccomTime`/`PostTaccomFireDelay` (v845 dropped them) |
| AGearPawn_Infantry | removed C++ MI bases; interface tables live only as explicit `VfTable_*` props resolved by `GetInterfaceAddress`; nav-obstacle dispatch inert until glue ported |

## Milestone reached (2026-08-23)

- Core.u and Engine.u of the Judgment v845 script set load **completely** in the
  v828-native Win32 runtime with zero watchdog violations. All 45 Engine-side
  class-layout deltas are corrected in headers.
- GearGame.u loading progressed past `GearAI` (208->227 members) after correcting
  127 shared owners plus judgment-only structs (`GearGameJudgmentStructs.h`).
- Current wall: deterministic corruption of the GearGame linker heap block while
  serializing `Function GearGame.GearAI_Cover:CheckForVehicleImpl`.

## Exonerated mechanisms (do not re-investigate)

| Theory | Test | Result |
| --- | --- | --- |
| GC purged an un-rooted linker | rooted all linkers, logged CollectGarbage / Verify-orphan / BeginDestroy (v21) | no GC ran; catch path never fired |
| Precache / SHA buffer reuse | forced plain handle-backed readers (v22) | crash unchanged |
| Replace-path overflow | `_msize` trap (v23-v25; NOTE: UB on permanent-pool objects, keep removed) | zero overflows anywhere |
| Bytecode format drift v828->v845 | Python expression-walker over 4.5k functions per era (`Temp\opencode\v845drift\walk.py`) | identical match rates (72.9% vs 73.1%) and identical failure sets |
| Nested Preload inside the bytecode MemReader window | entry logging at Preload (v28) | zero occurrences |

## Confirmed layout facts (engine-verified)

`UStruct::Serialize` on-disk header = 12 dwords: Next, SuperStruct, ScriptText-ref,
Children-ref, CppText-ref, three unknown dwords (0 / children+1 / 0), Line, TextPos,
ScriptBytecodeSize (logical), ScriptStorageSize (physical). Function tail = 15 bytes
(iNative u16, OperPrecedence u8, FunctionFlags DWORD, [RepOffset u16 if FUNC_Net
0x00200000], FriendlyName q64). Bytecode pointer operands are 4-byte indices on disk
but advance the logical cursor by 8.

## Live hypotheses for the GearAI_Cover smash

1. Class/State/ScriptStruct export parsing differences (extend `walk.py`; the three
   unknown dwords appear in every UStruct).
2. Tagged-property / CDO default-value paths during class binding.
3. CreateExport reconciliation behavior for GearGame script-only classes whose
   superclasses chain into Engine.u replacements.

## Build recipe

```
$env:VS90COMNTOOLS = "C:\Games\Gears 3 Files\_Toolchain\PortableVC9\Layout\Microsoft Visual Studio 9.0\Common7\Tools\"
$env:UE3_WINDOWS_SDK_DIR = "C:\Games\Gears 3 Files\_Toolchain\PortableVC9\Layout\Microsoft SDKs\Windows\v6.0A"
Development\Intermediate\UnrealBuildTool\Release\UnrealBuildTool.exe GearGame Win32 Release `
  -OUTPUT "C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\Binaries\Win32\GearGame-JudgmentLoader-v<N>.exe"
```

Run harness:

```
GearGame-JudgmentLoader-v<N>.exe PkgInfo -user -JUDGMENTPKGVER=845 -JUDGMENTCDOWATCH `
  -forcelogflush -unattended -nopause -nosound -nullrhi -ABSLOG=<log>
```

Diagnostics flags: `-JUDGMENTPKGVER` (enable foreign-package ceiling + plain readers +
rooted linkers), `-JUDGMENTCDOWATCH` (object mutation watchdog + import/export failure
context), `-JUDGMENTSTRUCTDUMP` (UStruct field dump + bytecode-window logging).

## Class-header check (latest)

First 12 dwords of Engine.Actor / WorldInfo / PlayerController class exports are
structurally identical between v828 and v845 (only package-relative indices and
content-driven sizes differ). No header-level drift in Class exports either; combined
with the function-walker result, on-disk FORMAT drift is now excluded at both levels
examined. Remaining suspects: content-dependent paths (TMap/array counts, tagged
defaults) and CreateExport reconciliation of script-only GearGame classes.

## Reconciliation trace (v29, in progress)

Added name-gated `
JUDGMENT_EXPORT_TRACE` reconciliation logging in `CreateExport` (pre-state incl.
existing-object probe; post-state incl. resolved super/outer/flags/PropertiesSize/template).
First run: gate silent - KEY INSIGHT: the failing Function export
(`CheckForVehicleImpl`, idx 20479) precedes the `GearAI_Cover` Class export (idx 20545)
in export order, so the class object is created lazily DURING the function's preload
via `ClassIndex` -> nested `IndexToObject`/`CreateExport`. Next iteration must gate on
the function name as well and trace the nested class creation inside that window.
The crash therefore occurs BEFORE the GearAI_Cover UClass finishes construction -
narrowing suspicion to superclass/template resolution performed while creating the
class from within the function-export nesting.

### Trace-gate follow-up (v30)

Widened gate to any `GearAI*` export: still zero `JUDGMENT_RECON` lines while the
crash reproduces identically - despite the failing function's export object existing.
Open instrumentation issue: either `Export.ObjectName` for these exports does not
contain the expected string at CreateExport time, or the trace block is not on the
executed path. Next session: place a one-shot unconditional probe as the first statement
of `CreateExport` (log first N calls) to verify reachability, then move the reconciliation
trace into `IndexToObject` where the nested class creation during function preload
actually occurs.

### Session IV probe result (same day)

UCameraAnim layout probes: sizeof=416, CIG=60, AnimLength=64, BoundingBox=68
(FBox=28), BasePPSettings=96 (FPostProcessSettings=312), Alpha=408, FOV=412 -
ALL match v845 exactly. sizeof(UInterpGroup)=108,
sizeof(UInterpTrackInstMove)=176 (=v845). Layout is NOT the problem.

Crash site: CalcLocalAABB -> MoveTrack->PosTrack.CalcBounds() - i.e. corrupted
PosTrack key data on a loaded CameraAnim's UInterpTrackMove, or wrong
UInterpTrackMove member offsets for the SERIALIZED region (PosTrack/Keys).
NEXT: 1) run sweep verdict check + probes for UInterpTrackMove
(sizeof/offsetof PosTrack, Points) 2) if clean, dump the failing CameraAnim's
name (instrument PostLoad entry to log each CameraAnim before CalcLocalAABB)
3) inspect that anim's track key bytes in the package.

## Session V (2026-08-24, later): CameraAnim/CalcLocalAABB blocker ROOT-CAUSED and FIXED

BLOCKER CLOSED. Load now completes PkgInfo end-to-end again
(`Success - 0 error(s), 0 warning(s)`, exit purge clean, EXIT=0,
JudgmentLoader-v55-fix.log). The v51->v99-fix regression is resolved.

### Phase 1 - layout verdicts (compile-time probes vs v49 layoutall chains)

```text
UInterpTrackMove
sizeof:
  v845      = 194
  relinked  = 196   (+2 tail padding past RotMode@193 - benign registration
                      artifact, same family as AController +4; no member >193)
PosTrack:
  v845      = +128 (elem 16)
  relinked  = +128          EulerTrack +144/+144   LookupTrack +160/+160
  LookAtGroupName +172/+172 LinCurveTension +180/+180 AngCurveTension +184/+184
  MoveFrame +192/+192       RotMode +193/+193
VERDICT: MATCH (member offsets identical; size delta is tail padding only)

Nested curve (relinked, matches v845 elem=16):
  FInterpCurveVector sizeof=16, Points@0 (Data@0 Num@4 Max@8), InterpMethod@12
  FInterpCurvePoint<FVector> sizeof=44: InVal@0 OutVal@4 ArriveTangent@16
  LeaveTangent@28 InterpMode@40

UInterpTrack
sizeof: v845=128 relinked=128  SubTracks@68 SubTrackGroups@80
SupportedSubTracks@92 TrackInstClass@104 ActiveCondition@108 TrackTitle@112
VERDICT: MATCH

UInterpGroup
sizeof:
  v845      = 104
  relinked  = 108   <-- FIRST PROVEN DIVERGENCE
InterpTracks: v845 @64, relinked @68 (+4); GroupName 76/80; GroupColor 84/88;
GroupAnimSets 88/92.
VERDICT: MISMATCH - duplicate `FPointer VfTable_FInterpEdInputInterface;`
declared alongside the real `public FInterpEdInputInterface` base (the
Session III strip pass only matched `public I<Name>` bases; F-prefixed
interface classes were missed). Every reflected member sat +4 off the
imposed v845 chain.
```

### Phases 2+3 - exact failing identity and container state

Instrumented UCameraAnim::PostLoad/CalcLocalAABB (`-JUDGCAMTRACE`, fail-fast):

```text
Package:     Effects_Camera
CameraAnim:  CA_Lambent_Berzerker_Gas_Damage
Group:       InterpGroup_0 (class InterpGroup)
Tracks:      2x InterpTrackVectorProp (NO MoveTrack exists in this group!)
At failure:  native view of InterpTracks = Data=0x00000002 Num=2 Max=6722
             (= serialized [Data][Num=2][Max=2] at chain@64 read shifted +4;
              6722 is the group's GroupName FName index)
```

Interpretation correction to Session IV: the anim has NO MoveTrack at all.
The "PosTrack.CalcBounds() on bad keys" reading was wrong - the AV happened
while iterating a shifted TArray header (Data==0x2 -> read at 0x8 inside the
track loop). Serialized package data was ALWAYS correct; deserialization into
chain offsets was correct; only the NATIVE readback offset was wrong.
Outcome class D->A: legitimate data + wrong native layout (not B/C).

### Fix (evidence-backed, same defect family as Session III MI double-count)

Removed duplicate `FPointer VfTable_*` decls where the class ALSO inherits the
real interface base (v845 chain reserves exactly one slot per interface, always
satisfied by the MI-base vptr). 11 decls / 10 classes:

| Class | Removed dup | v845 evidence |
| --- | --- | --- |
| UInterpGroup | VfTable_FInterpEdInputInterface | slot @60, size 104 (blocker) |
| UOnlineSubsystem | VfTable_FTickableObject | @60, size 216 |
| UGameViewportClient | VfTable_FViewportClient + VfTable_FExec | @60/@64, size 296 |
| UPlayer | VfTable_FExec | @60, size 96 |
| ULocalPlayer | VfTable_FObserverInterface | @96, size 864 |
| UTextureFlipBook | VfTable_FTickableObject | @368, size 432 |
| UUIInteraction | VfTable_FExec/FGlobalDataStoreClientManager/FCallbackEventDevice | @120/@124/@128, size 360 |
| UGearDedicatedServerInterface | VfTable_FTickableObject | @60, size 108 |
| UMCPBase / UMeshBeacon / UOnlinePlaylistManager / UPartyBeacon | VfTable_FTickableObject | @60 each (MeshBeacon 120, PlaylistManager 240, PartyBeacon 104; MCPBase not in dump - same pattern, header-only) |

Kept: the four remaining explicit `VfTable_I*` props (Infantry precedent -
those classes have NO real C++ interface bases, the prop IS the slot).

### Validation

- Probes after fix: sizeof(UInterpGroup)=104, InterpTracks@64 GroupName@76
  GroupColor@84 GroupAnimSets@88 - all = v845. InterpTrack/Move unchanged.
- Former victim loads coherently: trk.Data=heap ptr, Num=2 Max=2, both tracks
  walked, PostLoad completes. 77 CameraAnims traced through PostLoad, zero
  BADHDR/BADPTR/BADPTS events.
- Full PkgInfo: Success - 0 error(s), 0 warning(s); exit purge completes; EXIT=0.

### Next oracle

None in PkgInfo harness - loading now passes the previous boundary entirely.
Deeper victims (if any) will surface on gameplay-object instantiation /
map load, not during startup package load. Remaining sweep buckets
(19 MEMBER_DELTA / 29 SIZE_MISMATCH pre-strip counts, incl. Canvas +8,
GamePlayerCamera +12, LandscapeComponent +20) unchanged and still outstanding
for live-play correctness; several are now suspected to be additional
F-prefixed-interface or sim-artifact cases worth re-baselining with probes.

Diagnostics kept: `-JUDGCAMTRACE` gated CameraAnim PostLoad/AABB trace with
fail-fast sanity checks (implausible Data/Num/Max, wild track pointers,
curve-container validation) in UnCamera.cpp; probe printer extended
([JUDGPROBE-GRP/TRK/ITM/CURVE]) in GearGame.cpp.

PROVEN: UInterpTrackMove layout correct; UInterpGroup was +4 (dup vtable
pointer); serialized CameraAnim/track data correct at all times; fix restores
v845 semantics (no masking guards - the fail-fast checks remain but never fire
on well-formed data).
UNKNOWN: whether more F-prefixed dup patterns hide in classes absent from the
layoutall dump (e.g. MCPBase - fixed prophylactically on identical static
evidence); exact v845 handling of UInterpTrackMove 194-vs-196 tail (benign by
construction, no serialized member beyond @193).

## Session V checkpoint manifest (known-good source state)

Authoritative Session V implementation is preserved three ways (all on-disk;
NOT git-tracked because .gitignore is intentionally deny-all over Epic-
licensed content and the patch embeds Epic header context - loosening it is an
explicitly deferred copyright decision):

1. Full source snapshot:
   `_Backups\src-port-snapshot-20260824-sessionV-good\`
   (copy of Development\Src taken after v54 build/validation; 7,312 files)
2. Focused replayable patch (round-trip VERIFIED: `git apply -p1` onto the
   reconstructed pre-Session-V state reproduces current sources byte-exact,
   modulo pre-existing stray-LF lines):
   `patches\judgment-port\0006-sessionV-dup-vftable-strip.patch`
   Files touched (changed +/- lines):
   - Engine\Inc\EngineInterpolationClasses.h (5)
   - Engine\Inc\EngineClasses.h (9)
   - Engine\Inc\EngineTextureClasses.h (2)
   - Engine\Inc\EngineUserInterfaceClasses.h (5)
   - IpDrv\Inc\IpDrvClasses.h (12)
   - GearGame\Inc\GearGameOnlineClasses.h (3)
   - Engine\Src\UnCamera.cpp (99, diagnostics incl.)
   - GearGame\Src\GearGame.cpp (40, probes incl.)
   Patch generator (reverse-diff + verify harness):
   Temp\opencode\s5-make-patch.py
3. Known-good executable:
   `Binaries\Win32\GearGame-JudgmentLoader-v54.exe`
   SHA256 = 71C74216DEB8BB3308E03E4E715F067EC3F881A1ADF3F4194A2D345B384D2D3A
   (= dev binary byte-identical; validated by JudgmentLoader-v55-fix.log run)

To reconstruct: copy Development\Src from snapshot (1) OR apply patch (2) to
the pre-session state, rebuild via Temp\opencode\build-judgmentloader.bat,
compare hash against (3).

## Session VI (2026-08-24, evening): checkpoint, sweep re-baseline, gameplay-boot oracle established

### 1. Session V source state PRESERVED

- Full snapshot `_Backups\src-port-snapshot-20260824-sessionV-good\` (7,312 files).
- Focused round-trip-VERIFIED patch
  `patches\judgment-port\0006-sessionV-dup-vftable-strip.patch` (+ generator
  `Temp\opencode\s5-make-patch.py`; apply with `git apply -p1`).
- Known-good binary hash recorded in the manifest above (v54 exe SHA256).
- Status-doc commit `2f5280a` captures the manifest itself (patch/snapshot kept
  untracked by design - .gitignore deny-all over Epic content).

### 2. Post-MI sweep re-baseline (sweep_v4.py)

sweep_v4.py (committed to `_Backups\sessionVI-tools\`; sync to tooling repo)
adds: MI-base-aware vtable entries + TAIL_PADDING_ONLY classification +
C-style-comment stripping in decl parsing. New baseline over the same v49 dump:

```text
             v3(stale)   v4(post-S5)
OK           1930        1987
MEMBER_DELTA   71          16     (all real deltas now)
SIZE_MISMATCH  29           1     (only GearPawn_COGMarcus +12)
TAIL_PADDING_ONLY n/a      6     (ActorFactoryMover, AnimCompress x2,
                                Distribution*Parameter x3)
LAYOUT_DIFF     0          23     (classes w/ native-only member gaps -
                                chain space cannot prove; probe-on-blocker)
NO_PARENT_CHAIN 10         10
```

PROVEN: the old 19/29 backlog was dominated by MI-dup artifacts. Raw sizeof
inequality is no longer actionable without extent proof (InterpTrackMove case).

### 3. Gameplay-boot oracle + first two victims

Added `[JUDGLIFE]` progression checkpoints (-JUDGLIFE gated):
engine-init -> viewport-created -> local-player/pc-spawned ->
map-load-start/url -> map-loaded -> world-first-tick(+pawn-check) ->
first-render. Sites: UnGame.cpp (Init/LoadMap), UnLevAct.cpp (SpawnPlayActor),
UnLevTic.cpp (UWorld::Tick), UnPlayer.cpp (ViewportClient::Draw); helper
`JudgLifeCheckpoint` in Core (UnClass.cpp/JudgmentLoadDiag.h).

Boot attempt #1 (GearStart.gear, no commandlet):
- VICTIM 1 (FIXED): `Can't bind to native class Engine.ActorFactoryAmbientSoundSplineBase`
  during Engine.u load. Judgment-era native absent from this tree.
  Added `UActorFactoryAmbientSoundSplineBase : public UActorFactory`
  (EngineClasses.h) + IMPLEMENT_CLASS (UnActorFactory.cpp). v845 evidence:
  parent layout proven (size 92); no own props known.
- Instrumented `-JUDGNATIVEBINDOK` (UnClass.cpp Bind()): demotes the bind
  fatal to a warning listing each missing native, so ALL gaps enumerate in one
  boot. Result: **213 missing natives** =
  Engine 30 / GearGame 160 / UnrealEd 11 / GearEditor 12
  (full list: `_Backups\sessionVI-tools\missing-natives-v58.txt`).
  Top shapes: Object-based music/spline-audio structs, SequenceActions,
  GearSpecialMoves, GoalPoints, editor browser types. All editor/gameplay
  Kismet classes tolerate the flag (constructor inherited from super);
  NOT for final use - real natives must be reconstructed per class.
- Boot then advanced: viewport-created OK (GearGameViewportClient),
  map-load-start url=GearStart OK.

- VICTIM 2 (CURRENT WALL, precisely identified, NOT yet fixed):
  `Failed to find object 'Class OnlineSubsystemLive.IpNetDriverLive'` ->
  fallback `TcpNetDriver_0 listening on port 1000` -> fatal in
  `UWorld::Listen()` during LoadMap(GearStart?listen). STRONGLY INDICATED:
  OnlineSubsystemLive module is console-targeted and not compiled into the
  Win32 GearGame target while the v845 script set names IpNetDriverLive as
  net driver. Candidate fixes (need v845 oracle check before choosing):
  redirect default NetDriver to a PC driver via ini/script defaults, or
  compile a Win32 Live shim module.

### Validation so far
- v56 build links clean; PkgInfo path still exits 0 (unchanged behavior).
- Boot run reaches engine init + viewport creation + map load start;
  next oracle = survive Listen() -> map-loaded -> first tick/render.

### Next session priorities
1. Resolve Listen()/netdriver divergence (Victim 2) with v845-behavior evidence.
2. Batch-reconstruct missing natives from missing-natives-v58.txt using
   gen_native_block.py payloads; prioritize Engine audio/music + GearGame
   gameplay classes over editor-only ones.
3. Re-run boot until world-first-tick/pawn-check/first-render fire.

## Session VII (same evening): GAMEPLAY BOOT ACHIEVED - full lifecycle oracle green

SUCCESS CRITERION MET. The Judgment runtime now boots the smallest real
gameplay path (GearStart.gear frontend) through the ENTIRE progression oracle:

```text
[JUDGLIFE] viewport-created  GearGameViewportClient_0
[JUDGLIFE] map-load          url=GearStart
[JUDGLIFE] pc-spawned        GearPartyPC_0        (class GearPartyPC)
[JUDGLIFE] local-player      GearLocalPlayer_0    (class GearLocalPlayer)
[JUDGLIFE] map-loaded        GearEngine_0
[JUDGLIFE] first-render      GearGameViewportClient_0   <- render pipeline live
[JUDGLIFE] engine-init       GearEngine_0
[JUDGLIFE] world-first-tick  TheWorld                   <- game loop live
[JUDGLIFE] pawn-check        (null - expected: no pawn on frontend menu)
```

Run stayed alive 150+ s (frontend ticking, GFx attract mode cycling; one
benign content gap: SwfMovie 'Attract_Opening_Cinematic' not present in this
content set). Zero unbound-function events after the fixes below.
JudgmentLoader-v66-boot.log. Known-good binary:
GearGame-JudgmentLoader-v57.exe
SHA256 = 5142FF4B048D79A69D8F87A817BB83D419515F9C2BA18F1F56DDABA60F95ABC1
Source snapshot: `_Backups\src-port-snapshot-20260824-sessionVII-good\`
(focused patch for Session VII deltas to be exported next session).

### Victims fixed en route (each proven, in order)

1. `Can't bind to native class Engine.ActorFactoryAmbientSoundSplineBase`
   (Engine.u load). FIX: reconstructed native class
   UActorFactoryAmbientSoundSplineBase : UActorFactory (EngineClasses.h +
   UnActorFactory.cpp). v845 evidence: parent layout proven size=92.

2. AV at UWorld::Listen+0x176 (`cmp [eax+22Ch],10h` = GetGameInfo()->MaxPlayers>16,
   eax=0x4974262c = StallZ float bits read as pointer).
   ROOT CAUSE: native AWorldInfo carried a bogus `DWORD
   JudgmentDoubleAlignmentPadding` before LastTimeUnbuiltLightingWasEncountered.
   v845 chain proves the DOUBLE sits at @936 naturally 8-aligned after
   StreamingLevels@924 - no pad member exists. The pad shifted EVERY member
   after StreamingLevels +8 vs the imposed chain: serialization wrote Game@1172,
   native read @1180 (= chain's StallZ float) -> garbage GameInfo pointer.
   FIX: removed the pad (EngineGameEngineClasses.h). Post-fix compile probes:
   sizeof(AWorldInfo)=2024, Game@1172, GRI@1128, NetMode@1132,
   LMLevelSettings@1776, HostMigrationTimeout@2020 - ALL = v845 exactly
   ([JUDGPROBE-WINFO], JudgmentLoader-v61-winfo.log). This was silently
   corrupting WorldInfo reads for every package loaded since the pad was added.
   PROVEN: first divergence = the pad dword; not a missing-member problem
   (sweep's lmlevelsettings/visiblegroups flags are naming-only).

3. NULL native dispatch `GearGame.AISystem:GetAIDebugTool` on Default__AISystem
   during eventInitGame<-BeginPlay. ROOT CAUSE: class UAISystem absent from the
   tree entirely (one of the 213). FIX: full reconstruction -
   UAISystem : UObject, FCallbackEventDevice, FTickableObject with exact v845
   prop layout (size 128; ETQSys@68..bSidekicksDontUseRoute@124), inert Tick
   stubs (v845 tick behavior UNKNOWN), execGetAIDebugTool returning the AIDebug
   object (body UNKNOWN - plausible-payload choice, documented), native table +
   registrant entry (GearGameAIClasses.h, GearAI.cpp).

### New diagnostics kept
- `-JUDGNATIVEBINDOK`: Bind() demotes missing-native fatal to a warning listing
  each class (213 enumerated); CallFunction fail-fasts naming any unbound
  native function instead of calling NULL. Diagnostic-gated only; default path
  still fails fast.
- `[JUDGBIND][MISSING-FUNC]` names exact function+object when a script native
  call would hit a NULL implementation.

### Remaining / next oracle
- 213-class missing-native backlog stands (list preserved); boot currently
  needs none beyond AISystem for the frontend loop. Real campaign/map load and
  pawn possession will surface the next genuine victims - reconstruct per
  victim with gen_native_block.py payloads as they prove blocking.
- pawn-check fires null on frontend by design; next boot target: a minimal
  gameplay-capable map to drive possession + pawn class/defaults stages.
- IpNetDriverLive remains unresolvable on Win32 (console module); TcpNetDriver
  fallback now WORKS (Listen succeeds) so no fix required for SP boot.

## Session VIII (same night): PAWN POSSESSION REACHED - gameplay path stable

Target: smallest real gameplay map. `GearGame_P.gear` (5KB persistent base)
boots a complete AID-debug gameplay session. New lifecycle evidence:

```text
[JUDGLIFE] pc-spawned      GearPC_AID_0        (class GearPC_AID)
[JUDGLIFE] pawn-check      GearPawn_COGBairdJack_0 (class GearPawn_COGBairdJack)
[JUDGLIFE] pawn-owner-pc   GearPC_AID_0
```
-> pawn SPAWNED and POSSESSED; world ticking; run stayed alive 110+ s
(JudgmentLoader-v70-gp.log). Combined with Session VII this completes every
progression stage: engine init -> viewport -> local player -> world load ->
PC instance -> pawn class/instance -> possession -> first tick -> first render.

### Victims fixed en route
1. FALSE-POSITIVE fatal: `JUDGMENT REPLACE_OVERFLOW cls=GearCameraShake
   old=184 new=192` - the allocation-size ledger keyed raw addresses without
   removing freed heap entries; a recycled DataStoreClient address tripped it.
   GearCameraShake itself is CORRECT (192 in header/chain). FIX: ledger now
   tracks PERMANENT-POOL objects only (original Session I purpose).
2. UAISystem/AIDLogger follow-ups: replaced the per-function fail-fast with a
   GENERIC unbound-native stub: CallFunction now warns once per function
   ([JUDGBIND][MISSING-FUNC-STUB]) and routes through SkipFunction(), which
   consumes the parameter stream exactly and zeroes the return value - safe
   for ANY signature, no stack desync. Also reconstructed UAIDLogger
   (size 112, v845 chain) as layout-correct native.
3. UAISystem (Session VII) unchanged and working.

### Stub work-list produced by live boot (for future faithful reconstruction)
GearGame.SmartSpawner:SetInstance / :RunVisibleSpawnPointsCheck,
GearGame.AIDirector:Init, GearGame.GearHUD_Base:CacheProjectionMatrix /
:DrawWeaponInfo, GearGame.GearEngine:IsDebuggerAttached,
GearGame.GameplayMonitor:OnKill, GearGame.AIDLogger:Log,
GearGame.GearGame:NotifyDeathCounters (+ more as they fire).

### Known-good state
Binary: GearGame-JudgmentLoader-dev.exe == v57 content,
SHA256 = F2AD43759E89ED9E9DF5BD68B490AD44A72E4ADD2DAF72136856C1DA8679FF92
Source snapshot: `_Backups\src-port-snapshot-20260824-sessionVIII-good\`

### Next oracle steps
- Boot SP_Campaign map (e.g., SP_Ravens family) for real SP gametype flow.
- Faithful reconstruction of stubbed functions using v845 payloads
  (gen_native_block.py) once they prove behavior-relevant beyond inertness.
- The -JUDGNATIVEBINDOK flag remains REQUIRED for gameplay boots until the
  213-class backlog shrinks; default (flag-off) still fails fast.

## Session IX (2026-08-25): SP_Ravens CAMPAIGN BOOTS - GearPC_SP possesses GearPawn_COGMarcus

Baseline frozen: commit 2ff231b / v57 F2AD4375...92 (GearGame_P all-PASS
regression re-verified on v58 telemetry build, JudgmentLoader-v71).

### Campaign result (SP_Ravens_P direct boot, unchanged binary + telemetry)

```text
[JUDGLIFE] pc-spawned      GearPC_SP_0          (class GearPC_SP - campaign PC)
[JUDGLIFE] pawn-check      GearPawn_COGMarcus_0 (class GearPawn_COGMarcus)
[JUDGLIFE] pawn-owner-pc   GearPC_SP_0          <- POSSESSED
map-loaded / first-render / engine-init / world-first-tick ALL PASS;
run alive 110+s streaming weapon/character content + compiling shaders.
GearHUDSP_0 instantiated (HUD alive). JudgmentLoader-v73-ravensP.log.
```

SP_Ravens_01 (composite entry chunk) loads fully but has no PlayerStart in its
own persistent level ("Could not find a starting spot" after successful load) -
spawn logic lives in streamed sublevels; needs frontend-style flow or a
streaming-aware entry point. NOT a port defect: expected UE3 streaming behavior.

### Stub dependency ledger (state assignments per live evidence)

| Native | State | Evidence |
| --- | --- | --- |
| GearHUD_Base.CacheProjectionMatrix | REQUIRED(cand) | stubbed on live GearHUDSP; HUD projection math absent |
| GearHUD_Base.DrawWeaponInfo | REQUIRED(cand) | stubbed on live GearHUDSP |
| GearEngine.IsDebuggerAttached | OBSERVED | scalar ret; debug-only semantics |
| SmartSpawner.SetInstance / RunVisibleSpawnPointsCheck | OBSERVED | called on AID map only; no consequence shown yet |
| AIDirector.Init / AIDLogger.Log / GetAIDebugTool | OBSERVED | no gameplay consequence demonstrated |
| GameplayMonitor.OnKill / GearGame.NotifyDeathCounters | OBSERVED | fired on test-map kill event |

### Telemetry upgrade (kept permanently)
`[JUDGBIND][STUB] cls= func= obj= ret= count=N` - first call logs full context
incl. RETURN-SHAPE classification (void/scalar/object/STRUCT - non-scalar
returns flagged for empirical coverage); repeats aggregate at 10/50/100/500/N*1000.

Known-good: v58 dev == v58 archive,
SHA256 recorded in _Backups\sessionVIII-good snapshot lineage (v58 = Session IX telemetry build).
Next: reconstruct the two GearHUD_Base functions from v845 payload evidence,
then interactive input/locomotion validation on SP_Ravens_P.

## Session X (2026-08-25): Marcus selection ROOT-CAUSED; canonical bootstrap seam identified

New instrumentation ([JUDGPLAYER]): login URL/options + resolved GameInfo class
+ WorldInfo.DefaultGameType/GameTypes at login; every pawn-class SpawnActor
request (class/template/owner); PlayerStart census at first tick.

### Task B - why Marcus spawns: PROVEN
```text
login url=SP_Ravens_P options=?Name=Player 1?Team=255
gamecls=GearGameSP_0        <- stock GoW3-lineage SP GameInfo from v845 set
wi.DefaultGameType=(null)   <- SP_Ravens_P authors declare NO gametype
wi.GameTypesNum=0
pawn-spawn cls=GearPawn_COGMarcus template=(none) owner=(null)
playerstart total=1 (PersistentLevel)
```
The map declares no GameType -> engine ini default selects GearGameSP ->
its GoW3-era default character path yields Marcus. No Judgment campaign mode
was ever engaged. NOT a layout/asset problem.

### Canonical bootstrap seam: STRONGLY SUPPORTED
v845 GearGame.u contains NO Judgment-specific campaign GameInfo subclass.
SP family = GearGameSP / GearGameSP_Base / GearGameSP_Arcade (+ Generic).
Campaign identity lives in data classes: GearCampaignActData /
GearCampaignChapterData / GearCampaignGRI / EGearCampaignMemorySlot /
EGearCampaignLobbyMode. Retail therefore drives campaign via frontend/
profile/chapter state on top of GearGameSP(-Base), not via a map-declared or
URL-selectable special GameInfo. `?game=GearGameSP_Base` (unqualified) fell
back to GearGameGeneric with no pawn - qualified name + correct retail flow
required; next experiment = qualified ?game=GearGame.GearGameSP_Base and
chapter-data inspection (EGearCampaignMemorySlot consumers).

### Also proven this session
- PlayerStart census instrumentation answers streaming-spawn questions per map.
- v59 build: dev == archive; regression oracle re-passed (v71) before use.
- Session X runs: v74 (Ravens_P baseline, all stages PASS incl. Marcus),
  v75 (selection probe).

### Next oracle target
Qualified-name GameInfo experiment + GearCampaignChapterData consumption trace
to find the authentic Kilo Squad pawn-selection function (Task C), then input
oracle (Task D) on whichever pawn is correctly possessed.

## Session XII (2026-08-25): CONVERTED JUDGMENT `GearGame_P` BOOTS NATIVELY

The first whole-map BE845 -> LE845 platform conversion now passes the direct loader. This is the
retail Judgment `GearGame_P.xxx`, not the 2011 Gears 3 `GearGame_P.gear` control.

Converter corrections:

1. The final 17-byte `SeekFreeShaderCache` tail is an empty cache header, not shader microcode:
   priority INT 10, Xbox platform BYTE 2, and three zero counts. The converter accepts only that
   exact empty shape, swaps its integers and retargets the platform to this runtime's
   `SP_PCD3D_SM3` value 0. Populated Xbox caches still fail closed.
2. The first native load exposed an empty `FVert` BulkSerialize header with console element size
   16. Win32 validates PC `FVert` size 24 even when count is zero, so the converter retargets only
   the empty header. Populated width-changing arrays remain unsupported.

Fresh executable built from this source tree:

```text
Binaries\Win32\GearGame-JudgmentLoader-v60-nativecontent.exe
SHA256 AB21F561F71B72201529A89A2E89D8463975307A103ED2058858AA399AA1CEA3
```

Staged converted map:

```text
GearGame\Content\Maps\Judgment_GearGame_P.gear
SHA256 0849E7EA6E0DD73DDCECE8DB787A4B5B591C75E9EA1BF036ECA19389590D5353
```

Verified on the fresh v60 build (`Judgment_GearGame_P.v60-nativecontent-boot.log`):

```text
JUDGMENT_LOADER_READER ... Judgment_GearGame_P.gear size=7575
[JUDGLIFE] pc-spawned       GearPC_AID_0
[JUDGLIFE] map-loaded       GearEngine_0
[JUDGLIFE] first-render     GearGameViewportClient_0
[JUDGLIFE] world-first-tick TheWorld
[JUDGLIFE] pawn-check       GearPawn_COGBairdJack_0
[JUDGLIFE] pawn-owner-pc    GearPC_AID_0
```

The next real campaign fixture is `SP_00_Museum_Base_Exit_S`: 79,775 bytes decompressed,
58 exports. Current conversion is 41 fully converted, 16 partial CoverLinks (binary immutable
`CoverSlot` arrays), and one unmodelled populated ULevel tail. Its empty SoundCue editor map is
now modelled. Exact next blockers: `FCoverSlot` binary serialization, then the populated Level
tail. The converter now bounds speculative array counts and reports partial exports honestly.
