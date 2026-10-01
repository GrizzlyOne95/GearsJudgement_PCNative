# Judgment AI native accessor checkpoint (2026-09-30)

Session XXVI continues in the separate `Judgment Port Workspace` copy. The
validated ws18 loader remains the harness default. ws19 contains an explicit
`-JUDGAIACCESSORS` experiment; this is an accessor layer with incomplete native
initialization, ticking, cleanup and encounter behavior.

## Evidence from the original build

`pdb_native_symbols.py` reads MSF 7 directory/stream blocks, DBI section headers
and CodeView public records directly. The installed LLVM parser rejects the
local Release PDB's multi-page directory block map. The new reader validates
213,859 public symbols and selects 578 AI-related records without changing the
original file. It checks lengths, block indices, duplicate stream blocks,
record boundaries, names, selected symbol ranges and PDB/DBI identity ages.

Original Release PDB SHA-256:
`07fdd76b0d1edf2dc6739abbb636ec85d177fc281ce570bc3408a8715adc7fb3`.
GUID `b28657d9-f3cd-47b8-b92b-94a9ce82592f`, age 1, matches the original image's
RSDS record at image offset `0x2f5958`. The inspected image and disassembly
remain private under `_judgment-scratch/native-ai-20260930`.

Observed native contracts, using image base `0x82000000`:

| Function | Address | Observed behavior |
| --- | --- | --- |
| AISystem.GetInstance | 0x83490570 | Lazily constructs a rooted transient singleton, publishes it, then calls native Init(1). |
| AISystem.Init | 0x8348d508 | Registers callbacks; when not cooking, constructs and initializes ETQSystem, AISpawnManager and AIDebugTool; invokes the original script Init event. |
| AISystem.GetETQSystem/GetAISpawnManager/GetAIDebugTool | 0x83490608 / 0x83490630 / 0x83490658 | Return the respective member of GetInstance(). |
| AISystem.AppSeconds | 0x8348d6d0 | Returns a float from the performance counter and seconds-per-cycle scaling. |
| SmartSpawner.SetInstance | 0x83430638 | Stores the current object in its singleton slot. |
| SmartSpawner.RunVisibleSpawnPointsCheck | 0x83430670 | Submits a query through ETQSystem using the local player's pawn and the spawner as context. |
| AIDirector.Init | 0x8345d638 | Stores its SmartSpawner parent, constructs FSM_AIDirector and initializes its finite-state machine. |

The original AISystem script Init event is an empty return body. Native Init is
substantial. Replacing it with that script event alone does not initialize the
query, spawn or debug subsystems. Native map-change/checkpoint cleanup and AI
goal selection are also present in the symbols and need separate reconstruction.

Format references: [LLVM MSF](https://llvm.org/docs/PDB/MsfFile.html),
[LLVM DBI](https://llvm.org/docs/PDB/DbiStream.html) and
[LLVM CodeView records](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/DebugInfo/CodeView/SymbolRecord.h).
The local image inspection used the format described by
[Xenia's XEX headers](https://github.com/xenia-project/xenia/blob/master/src/xenia/kernel/util/xex2_info.h)
and [image loader](https://github.com/xenia-project/xenia/blob/master/src/xenia/cpu/xex_module.cc).
The committed PDB reader is original Python code and has no external parser dependency.

## Isolated prototype and validation

Private patch `0019-ws-ai-accessors-prototype.patch` adds conditional native
tables for AISystem.GetInstance/AppSeconds and SmartSpawner.SetInstance.
GetInstance constructs a real AISystem with RF_RootSet and invokes the original
script Init. Its diagnostic explicitly reports the three unported native
subsystem initializers and unported Tick. SmartSpawner's VM bridge uses only
UObject APIs on the existing loaded object; it changes no class member layout
and is never registered or constructed as a script class.

Without `-JUDGAIACCESSORS`, the original ws18 native lookup tables remain in use.
The experiment does not enable native AISystem ticking or replace mission
scripts. Map cleanup, checkpoint restoration and encounters remain unverified.

Prototype loader: `GearGame-JudgmentLoader-ws19-ai-accessors-v2.exe`,
59,433,472 bytes, SHA-256:
`78371AE6D7A9D82644DAB33D0B4F4ECB87BC86CD3C376F49F0F1175EC083D971`.
Private patch: 5,548 bytes, SHA-256:
`fabe7279a2e9c454c7dea2e51eb97bd8c7951b85d391fe90ac2142983f2d63eb`.
Reverse/forward application reproduces both source before/after images exactly.

The 100-second D3D9 prototype run passes the original campaign startup and
objective audit: 11,374 exact loads, zero framing mismatches/fatal errors,
15 paired tick reports (last wall time 98.87 s, game time 68.453 s), seven levels
and 4,010 recorded presents (last 95.37 s). All three original companion
controllers—Carmine, Barrick and Gus—obtain the same Transient.AISystem_0,
rooted and not a class default object. The live Transient.SmartSpawner_0 reaches
SetInstance. The three null AISystem possession warnings disappear, while
three missing Squad warnings remain. The existing active objective 1 is still
present with completed/failed false.

The remaining gameplay native fallbacks are AIDirector.Init,
SmartSpawner.RunVisibleSpawnPointsCheck and GearAI.PickGoal. AI logging and HUD
warnings/fallbacks remain visible. The accessor experiment does not establish
working encounters, companion movement, checkpoint restore or input.

`audit_ai_accessor_layer` requires three companion callers sharing one real
rooted singleton, sequential call evidence, the live spawner and explicit
partial-init disclosure. It rejects missing evidence, CDO/unrooted returns,
different instances, continued accessor fallbacks and null-system possession
warnings. The campaign report carries the pending native initialization, Tick,
cleanup and encounter limits alongside its startup result. 138 unit tests pass,
including 17 synthetic PDB cases and 10 accessor proof cases.

```powershell
python pdb_native_symbols.py <local-release.pdb> --match '(UAISystem|USmartSpawner|UAIDirector)' --output <new-private-report.json>
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws19-ai-accessors-v2.exe -Cases sp_e2_p -BootSeconds 100 -Renderer D3D9 -CampaignStartup -AIPrototype -MaterialTrace
```

Retained logs: `ws19-ai-accessors-null-20260930` (initial headless diagnostic),
`ws19-ai-accessors-render-20260930` (final rendered experiment),
`ws19-baseline-control-20260930` (flag-off regression suite).
The initial headless diagnostic also preserved startup/objective state for
100 seconds; its trace predates the stricter three-caller gate.

The final flag-off NullRHI controls pass PkgInfo, the thin map and SP_E2_P.
SP_E2_P still passes startup/objective validation with 11,374 exact loads,
ten paired ticks (last 71.29 s, game time 44.411 s) and seven levels. It reports
no prototype markers/layer, retains the original accessor fallbacks, and has
the same three null-system possession warnings as ws18. This confirms the
experiment is conditional in the new binary.

Next: port native subsystem Init/Tick and director FSM behavior, then validate
the first encounter. Streamed lighting/environment
textures and the main Museum campaign remain separate content milestones.
Only tooling/tests/docs are public; engine source/patches, original debug files,
disassembly, content and binaries stay private. Protected Gears 3 audit:
20,284 files, zero changes.

## Session XXVII: original squad membership verified

A strict read-only walk of the original SetSquadName function consumes exactly
506 stored / 730 logical script bytes. The warning at logical offset 0x0151
comes from reading the previous Squad.Leader before squad joining has finished.
It does not establish that squad creation failed. The original script remains
unchanged.

Private patch `0020-ws-squad-state-trace.patch` adds a separately flagged
`-JUDGAISQUADTRACE` snapshot at the first objective. Loaded property reflection
reads controller, pawn, PRI, team, squad, leader and each controller's member
index. The probe checks object/struct offsets and array lengths, scans at most
64 controllers, captures once, and writes no game state. Its application needs
`git -c core.autocrlf=false apply` to preserve this source file's existing mixed
line endings. Reverse/forward replay is byte-identical with that option.

Diagnostic loader `GearGame-JudgmentLoader-ws20-squad-trace.exe`:
59,436,032 bytes, SHA-256
`AEFAEE9B3B76BEEBEE17AA48225BE87B348E7A2EE320F9A9B76D9111DA07D3D3`.
Private patch: 4,694 bytes, SHA-256
`d88347d43171cb821fba8e3e0365faab3a54735853c3ed2789735b62f0a76f16`.

At game time 30.125 seconds, Carmine, Barrick and Gus have distinct live pawns
and PRIs, share GearTeamInfo_0 and GearSquad_0, and appear at member indices
1, 2 and 3 of a four-entry SquadMembers array. Its leader is the actual local
player GearPC_AID_0, whose objective manager holds objective 1. The probe does
not separately inspect the player's array entry; that limit is explicit in
the report. Movement and encounters are not inferred from membership.

The 100-second NullRHI run with the accessor prototype passes 11,374 exact
loads, 15 paired ticks (last 96.62 s) and the startup/objective/membership audit.
A 75-second flag-off control also verifies the same existing membership at
game time 30.127 s, with 11,374 exact loads and ten paired ticks (last 71.31 s).
Thus scripted squad formation already works independently of the new singleton
experiment. The missing native AI subsystem/director behavior remains the
next implementation surface. ws18 remains the default loader.

The audit now requires three distinct controller/pawn/PRI identities, one team
and squad, the real player as leader, four array entries and three distinct
valid member indices. Missing/unreadable objects, duplicate identities,
different squads/teams, wrong leaders, missing indices or limited snapshots
fail the membership gate. 145 unit tests pass, including seven new proof cases.
Retained tags: `ws20-squad-prototype-20260930`, `ws20-squad-baseline-20260930`.

```powershell
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws20-squad-trace.exe -Cases sp_e2_p -BootSeconds 100 -CampaignStartup -AIPrototype -AISquadTrace
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws20-squad-trace.exe -Cases sp_e2_p -CampaignStartup -AISquadTrace
```


## Session XXVIII: director-specific native initialization

Private original-code inspection identifies AIDirector.Init at `0x8345d638`
and FiniteStateMachine.Init at `0x83480d18`. The director stores its SmartSpawner,
constructs FSM_AIDirector with itself as outer, calls Init(owner, FALSE), and sets
bPerformLMsAutoSetup. The PDB type records resolve the three original booleans at
offset 248: bPendingStop `0x80000000`, bPerformLMsAutoSetup `0x40000000`,
bIsRunning `0x20000000`. This prevents confusing automatic level-marker setup
with starting the director. The PC implementation uses the loaded named property's
mask, rather than carrying those Xbox masks into PC objects. Type format reference:
[LLVM CodeView type records](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/DebugInfo/CodeView/TypeRecord.h).

The original FSM_AIDirector CDO is walked to its exact export boundary. It defines
BuildUp -> PeakSustain -> PeakFade -> Relax -> BuildUp. Its four transitions
initially have ToStateIdx=-1 and all delegates are unbound. Original FSM Init binds
enter/leave and condition delegates, resolves target indices, invokes OnInit when
bScriptInit is enabled, then sets Status=1. Its native owner casts populate MyAI
and MyGoal; GenericOwner is not assigned by that native initializer. Activation
occurs only when Init's separate argument is TRUE. The director passes FALSE.
The original overridden OnInit script assigns its AIDirector property from Owner.
No script or CDO export is changed.

Private patch `0021-ws-director-init-prototype.patch` adds only the director's
Init(FALSE) path, selected with `-JUDGAIDIRECTORINIT`. A layout-free UObject VM
bridge constructs the original loaded FSM class. Checked property types, widths,
offsets, struct strides and bounded arrays provide access to its fields. All
nested array bounds are checked before the FSM's first field write. The existing
AISystem property block is byte-identical. The general FiniteStateMachine.Init
native binding is not replaced, and its activate=TRUE path remains unported.
Native director/FSM Tick, pacing callback bodies, queries and encounter behavior
remain pending. Binding a delegate does not implement its missing native body.
The auto-setup flag is enabled; actual level-marker setup is not established.

Loader: `GearGame-JudgmentLoader-ws21-director-init.exe`, 59,453,952 bytes,
SHA-256 `981B35D0AE057A261866D75E6FC1E1D67E499BC6EBB7A60C6BDB8860BEB873C7`.
Private patch: 11,253 bytes, SHA-256
`603717765a49409681fd7fc632f79bc082aa956602eba775f6d8ec09263beb52`.
Before/after replay is byte-exact with `git -c core.autocrlf=false apply`.
Added lines were normalized to the files' original CRLF after the successful
build; C++ tokens and line numbers are unchanged.

The 100-second NullRHI run passes original startup, objective and squad proofs:
11,374 exact loads, no framing mismatches/fatal errors, 15 paired tick reports
(last 96.56 s, game time 69.295 s) and seven levels. Runtime inspection proves
Transient.AIDirector_0 has its live SmartSpawner, owns a real FSM_AIDirector,
binds 12 delegates, resolves transition indices 1/2/3/0, and obtains the correct
owner through the original OnInit script. Status=1, auto-setup=1, running=0.
AIDirector.Init no longer uses the generic fallback. SmartSpawner's visible-spawn
query and GearAI.PickGoal still do.

The initial 100-second D3D9 attempt passes startup/objective/squad/director gates
and keeps ticking to 98.80 s, but fails the late-presentation gate: its last
recorded presentation is 60.36 s (1,615 frames). This failed attempt is retained.
A second run of the same binary passes the complete rendered gate with 3,506
presentations (last 95.34 s), 15 paired ticks (last 98.93 s, game time 68.558 s),
11,374 exact loads and unchanged startup/squad proofs. Read-only monitoring of
that helper's window confirms a visible, non-minimized 1280x720 client area after
startup. It does not establish the cause of the first presentation gap. ws18
remains the harness default; this is an optional AI initialization experiment.

The campaign audit now separately verifies all four original state names,
12 delegate bindings, the four target indices, real machine outer/owner,
original script-owned director, initialized status, unchanged inactive state,
auto-setup flag, matching live spawner and explicit pending native work. Missing,
repeated, unbound, misdirected, incorrectly activated or fallback-only evidence
fails the gate. Reports explicitly leave pacing callbacks and encounters
unimplemented. 154 unit tests pass, including nine new initializer proof cases.

Retained tags: `ws21-director-init-null-20260930`,
`ws21-director-init-render-20260930` (failed presentation gate), and
`ws21-director-init-render-retry-20260930`. The final headless audit with the new
gate is retained privately as `director-init-null-final-v2.validation.json`; its
earlier automatic report predates this new gate. Original type/code/default
reports remain private.

```powershell
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws21-director-init.exe -Cases sp_e2_p -BootSeconds 100 -CampaignStartup -AIPrototype -AISquadTrace -DirectorInit
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws21-director-init.exe -Cases sp_e2_p -BootSeconds 100 -Renderer D3D9 -CampaignStartup -AIPrototype -AISquadTrace -DirectorInit -MaterialTrace
```

Next: native director/FSM Tick and pacing callbacks, ETQ initialization/query
execution and companion goal selection. Input, encounters and checkpoint restore
remain unverified. Protected Gears 3 audit: 20,284 files, zero changes.


The final `ws21-baseline-control-20260930` flag-off suite passes PkgInfo,
the thin map and SP_E2_P. Both experimental layers are absent; the original
AISystem.GetInstance, SmartSpawner.SetInstance and AIDirector.Init fallbacks
remain, and existing scripted squad membership still passes. SP_E2_P records
11,374 exact loads, ten paired ticks (last 71.75 s) and preserved objective 1.
This confirms the director initializer is conditional in the new binary.


## Session XXIX: detached FSM core and original-code numeric checks (2026-10-01)

Private patch `0022-ws-fsm-core-prototype.patch` adds the finite-state-machine
controls behind `-JUDGFSMCORE`: Init (including optional activation), Activate,
Deactivate, Pause, OnWorldEvent, forced transitions by name/index, and current
state command-class lookup. A checked reflection view accesses the original
loaded properties; UObject/AISystem layouts, scripts and CDOs are unchanged.
The original director initializer continues to pass activate=FALSE.

The native contracts preserve several significant details. Pause leaves queued
events and remaining time intact; resume does not invoke OnEnter again.
Deactivate sets inactive status before OnLeave, and forced transitions are
accepted while inactive. Initial-state lookup selects the first matching name;
forced name lookup selects the last. During an active tick, the lowest matching
transition index takes priority across all queued events. `Any` is a wildcard,
but conditions are not evaluated without an event. Events are consumed even
when the state has no transitions. Transition conditions run before the native
timer decrement. The director timer and RelaxCondition are implemented, as are
the four original empty OnLeave callbacks. Other native Tick_Impl overrides
remain unsupported. The command-class transition branch invokes the original
BeginDefaultCombatCommand script, but a non-null command-class case is unverified.

The original RelaxCondition and director Tick_Impl machine code were executed
privately with Unicorn 2.1.4. Nine condition boundaries and six timer cases
include positive/negative/zero remaining time, signed zero, both infinities,
NaN, zero/negative delta and crossing zero. All 15 PC results match the original
execution, including the unordered-comparison case (NaN transitions). The
original image, instructions, types and oracle report remain private. Emulator
reference: [Unicorn PPC sample](https://github.com/unicorn-engine/unicorn/blob/master/samples/sample_ppc.c).

`-JUDGFSMSELFTEST` constructs a separate transient FSM_AIDirector with independent
state/transition arrays. Only this detached object substitutes empty base script
delegates and RelaxCondition on every edge. It exercises the new VM native
bindings, 12 ordered control/event/timer cases and all 15 numeric boundaries.
Snapshots of the live director/FSM property blocks and nested state/transition
arrays are byte-identical before and after the test. The real FSM is initialized
and inactive; the test does not deliver synthetic events to it. It does not
prove live combat pacing, companion movement or encounters.

The campaign audit has a separate `experimental_fsm_core` report. It requires
all ordered states, event counts, remaining times, callback counts, numeric bit
results, detached object identity, correct live FSM identity and unchanged
snapshots. Missing, repeated, reordered or inconsistent evidence and generic
fallbacks for the ported natives fail the gate. Core without the self-test does
not claim tested controls. Pending pacing/query/driver work stays explicit.
168 unit tests pass, including 14 new FSM evidence-gate tests.

Private patch 0022: 29,342 bytes, SHA-256
`a3541cadcf5ae3b513b2feaa1542b384d5bf75721a74495ab0a89ea9d96d0a2b`.
Exact reverse/forward replay passes in an independent scratch Git root with
`git -c core.autocrlf=false apply`; a new CRLF include file is part of the patch.
Loader `GearGame-JudgmentLoader-ws22-fsm-core-v2.exe`: 59,490,304 bytes,
SHA-256 `064DBFF6B50DDD4985C84822195DADB5BC971C7E1C17CBE51050BDF513DB4504`.
The 100-second NullRHI run passes startup/objective/squad/director and detached
FSM proofs with 11,374 exact loads, 15 paired ticks (last 98.60 s), seven levels
and no framing/fatal errors. Tag: `ws22-fsm-selftest-null-20260930`; the final
new-gate report is retained privately as `fsm-core-null-final.validation.json`.

## Session XXX: narrow-desktop startup and rendered FSM validation (2026-10-01)

After the desktop changed to 600x1284, the ws22 D3D9 run and flag-off suite stop
before loading the mission: the engine rejects desktop widths below 640.
These failed attempts remain under tags `ws22-fsm-selftest-render-20261001`
and `ws22-baseline-control-20261001`. This differs from the earlier ws21
late-presentation gap, whose cause remains unresolved.

Private patch `0023-ws-window-resolution.patch` scopes a startup exception to
Judgment package version 845. NullRHI does not require a physical display.
For rendering, `-JUDGWINDOWRESOLUTION` additionally requires explicit windowed
mode and ResX/ResY at least 640x480. The existing check remains for other cases.
No desktop setting is changed. The engine can still resize the actual window
to fit the desktop; requested and presented dimensions are distinct.
The regression harness exposes this through `-WindowResolution` with D3D9.

Patch 0023: 1,590 bytes, SHA-256
`815b5878792a6a013accea79aeb8cec5306abf9f554b4b490ce0f2e8d5e19526`.
Exact-byte reverse/forward replay passes. Loader
`GearGame-JudgmentLoader-ws23-window-fsm.exe`: 59,490,816 bytes, SHA-256
`C503C714F4EE9E750A4EB938DFFDDAB371B06822228CE55D8188C129E76685E7`.
The 100-second D3D9 test passes every startup/objective/squad/director/FSM gate:
11,374 exact loads, 14 paired ticks (last 95.03 s, game time 63.205 s), seven
levels and 3,372 presentations (last 95.96 s). Requested window size is 1280x720;
presentations are 594x334 on the narrow desktop. Tag:
`ws23-fsm-selftest-render-20261001`. There are no native framing/fatal errors.

```powershell
./run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws23-window-fsm.exe -Cases sp_e2_p -BootSeconds 100 -Renderer D3D9 -WindowResolution -CampaignStartup -AIPrototype -AISquadTrace -DirectorInit -FSMCore -FSMSelfTest -MaterialTrace
```

The harness still defaults to ws18. The new timer/event core is tested on the
detached object; live director/FSM update integration, four pacing OnEnter
bodies, the other three conditions, ETQ/spawn queries and goal selection remain
pending. Input, encounters and checkpoint restore are unverified. All source,
content and runtime work remains in the separate Judgment copy.


The ws23 flag-off suite (`ws23-baseline-control-20261001`) passes PkgInfo, the
thin map and SP_E2_P. All three experimental AI/director/FSM reports are absent;
the original accessor/director generic fallbacks remain. SP_E2_P preserves
objective 1 and the original squad, with 11,374 exact loads and ten paired
ticks through 71.03 seconds. The new Judgment-only headless resolution path
works on the narrow desktop. A separate initializer/accessor-on, FSM-off run
(`ws23-director-core-off-20261001`) passes with the original inactive machine,
12 bindings and owner intact, 11,374 exact loads and ten ticks through 71.10 s.
The common Init refactor therefore preserves the prior guarded initializer.

Protection audit note: the September 30 fingerprint no longer matches the
campaign trees. At the October 1 snapshot, 20,811 files are present, with 600
historical differences (536 added, 9 removed, 55 altered), including six shared
source files. The user's separate active “Validate Gears 3 fixes and UI” task
is building/deploying campaign/UI/razor fixes in those trees. This Judgment
session writes only its independent workspace, tooling and scratch evidence;
no campaign changes are reverted or copied into Judgment. The previous audit
and complete difference report are retained, along with a new timestamped
snapshot. A global zero-change claim is not made while that campaign task runs.


The ws23 D3D9 flag-off negative control (`ws23-window-flag-off-20261001`)
retains the original minimum-desktop-resolution exit at 600 pixels wide,
before any native mission load. Its harness FAIL is the expected result for
this negative control. The explicit-window exception therefore remains opt-in.
