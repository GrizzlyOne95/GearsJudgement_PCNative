# Judgment native-port - build-tree status

Living status document for the native-port work performed inside this Gears 3 source
tree (custom `Binaries\Win32\GearGame-JudgmentLoader-vN.exe` diagnostic loaders).
Full technical narrative lives in the tooling repository:
`C:\Games\NostalgiaBundle\projects\GearsJudgement_PCNative\PORTING-NOTES.md`.

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
