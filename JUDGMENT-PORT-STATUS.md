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
| `AGamePlayerController`: removed `FName CurrentSoundMode` (+ its VERIFY line) — v845 dropped it | parent-size delta shifted every GearPC-family descendant; was masquerading as a GearPC/FortUpgradeList issue |

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
was *reordered* rather than resized — first observed `AGearAI::~AGearAI` freeing a
`TArray<AActor*>`. Proof collected (`-JUDGMENTLAYOUTDUMP`): GearAI totals match
exactly (both 1924) but member offsets are shuffled (TetherPosition 960→1460,
CombatMood 1800→961 with elem 4→1, etc.), so post-relink destruction reads wrong
slots. Same family already fixed by exact-layout matching: MIC editor class
(v45→v47: ParameterGroups refactor, old arrays kept native-only).

Next phase plan: build a generator that emits each affected class's `BEGIN/END PROPS`
block directly from the runtime `-JUDGMENTLAYOUTDUMP` tables (names+types from current
headers, order/bitfields from v845 offsets), then sweep all GearGame/Engine classes
until purge completes. Diagnostics to keep: allocation-size ledger, array-destroy
validator, flight recorder, layout dumper — all flag-gated and fail-fast.

## Root cause of the old wall (proven)

The "linker heap smash" was never a loader-stream problem. Chain:

1. Several replaced classes had native sizes ≠ v845 reflected sizes
   (`SeqAct_ControlGameMovie +4`, `OnlinePlaylistManager +16`,
   `Gear_GrappleHookMarker +60` via missing base `SpawnPoint`,
   `GearSeqVar_Player +16`, `SeqAct_ChapterComplete +16` via re-parent to
   `SeqAct_Latent`, `GearPawn_Infantry +16` via removed MI bases +
   removed tail floats in `AGearPawn`).
2. After the script UClass relinked, replacing the older, smaller native
   allocation ran `appMemzero(Obj, InClass->GetPropertiesSize())`
   (UnObj.cpp StaticAllocateObject) past the end of the block,
   smashing whichever permanent-pool/heap neighbor followed — linker
   fields in one layout, object tables in another (explains every prior
   shifting victim and the "ExportMap flips" observations).
3. On the destroy side, ExitProperties walked the relinked property chain over
   old-layout memory → `UArrayProperty::DestroyValue` freed wild pointers
   (now fail-fast guarded).

Diagnostics kept behind flags (all fail-fast, SEH-guarded, safe-formatted):
allocation-size ledger + `-JUDGMENTREPLACEWATCH`, array-destroy validator (always on),
bytecode flight recorder + `-JUDGMENTLAYOUTDUMP`, `-JUDGMENTCEXLIMIT=`.
v31 lesson recorded: previous silent traces died inside their own `debugf` on
bad `%s` args — never pass unsanitized pointers into Logf.

## Class fixes this session

| Class | Fix |
| --- | --- |
| GameFramework.SeqAct_ControlGameMovie | + `BITFIELD InputSkipLock:1;` |
| IpDrv.OnlinePlaylistManager | + `FContentOfferId` struct, `ContentOfferIds`, `DataCenterIdOverride` |
| GearGame.ASpawnPoint | new intermediate base (+60 B) between Actor and grapple/spawn markers |
| GearGame.Gear_GrappleHookMarker | re-parented AActor → ASpawnPoint |
| GearSeqVar_Player | + `bHumanOnly`, `PlayerSlotObjs` |
| SeqAct_ChapterComplete | re-parented SequenceAction → SeqAct_Latent |
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
| `AGamePlayerController`: removed `FName CurrentSoundMode` (+ its VERIFY line) — v845 dropped it | parent-size delta shifted every GearPC-family descendant; was masquerading as a GearPC/FortUpgradeList issue |

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
was *reordered* rather than resized — first observed `AGearAI::~AGearAI` freeing a
`TArray<AActor*>`. Proof collected (`-JUDGMENTLAYOUTDUMP`): GearAI totals match
exactly (both 1924) but member offsets are shuffled (TetherPosition 960→1460,
CombatMood 1800→961 with elem 4→1, etc.), so post-relink destruction reads wrong
slots. Same family already fixed by exact-layout matching: MIC editor class
(v45→v47: ParameterGroups refactor, old arrays kept native-only).

Next phase plan: build a generator that emits each affected class's `BEGIN/END PROPS`
block directly from the runtime `-JUDGMENTLAYOUTDUMP` tables (names+types from current
headers, order/bitfields from v845 offsets), then sweep all GearGame/Engine classes
until purge completes. Diagnostics to keep: allocation-size ledger, array-destroy
validator, flight recorder, layout dumper — all flag-gated and fail-fast.

## Root cause of the old wall (proven)

The "linker heap smash" was never a loader-stream problem. Chain:

1. Several replaced classes had native sizes ≠ v845 reflected sizes
   (`SeqAct_ControlGameMovie +4`, `OnlinePlaylistManager +16`,
   `Gear_GrappleHookMarker +60` via missing base `SpawnPoint`,
   `GearSeqVar_Player +16`, `SeqAct_ChapterComplete +16` via re-parent to
   `SeqAct_Latent`, `GearPawn_Infantry +16` via removed MI bases +
   removed tail floats in `AGearPawn`).
2. After the script UClass relinked, replacing the older, smaller native
   allocation ran `appMemzero(Obj, InClass->GetPropertiesSize())`
   (UnObj.cpp StaticAllocateObject) past the end of the block,
   smashing whichever permanent-pool/heap neighbor followed — linker
   fields in one layout, object tables in another (explains every prior
   shifting victim and the "ExportMap flips" observations).
3. On the destroy side, ExitProperties walked the relinked property chain over
   old-layout memory → `UArrayProperty::DestroyValue` freed wild pointers
   (now fail-fast guarded).

Diagnostics kept behind flags (all fail-fast, SEH-guarded, safe-formatted):
allocation-size ledger + `-JUDGMENTREPLACEWATCH`, array-destroy validator (always on),
bytecode flight recorder + `-JUDGMENTLAYOUTDUMP`, `-JUDGMENTCEXLIMIT=`.
v31 lesson recorded: previous silent traces died inside their own `debugf` on
bad `%s` args — never pass unsanitized pointers into Logf.

## Class fixes this session

| Class | Fix |
| --- | --- |
| GameFramework.SeqAct_ControlGameMovie | + `BITFIELD InputSkipLock:1;` |
| IpDrv.OnlinePlaylistManager | + `FContentOfferId` struct, `ContentOfferIds`, `DataCenterIdOverride` |
| GearGame.ASpawnPoint | new intermediate base (+60 B) between Actor and grapple/spawn markers |
| GearGame.Gear_GrappleHookMarker | re-parented AActor → ASpawnPoint |
| GearSeqVar_Player | + `bHumanOnly`, `PlayerSlotObjs` |
| SeqAct_ChapterComplete | re-parented SequenceAction → SeqAct_Latent |
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
