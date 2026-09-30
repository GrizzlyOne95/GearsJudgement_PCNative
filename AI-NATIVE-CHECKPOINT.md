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
