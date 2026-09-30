# Judgment original campaign startup and first objective

Session XXV, 2026-09-30, continuing `f00dd1a` in the separate Judgment workspace.
The original Aftermath startup graph now has independently checked execution
evidence: streaming completes, four squad factories emit All Spawned, the
startup checkpoint action completes, cinematic mode is released, the camera
fades up, the chapter-title action executes and objective **1** is created in
the local player's real `GearObjectiveManager`. Its completed/failed flags are
both false. The trace does not inject events, force objectives or bypass waits.

This is a startup milestone. Encounters, checkpoint save/restore, player input,
AI navigation and full campaign progression remain unverified. The test uses
Aftermath `SP_E2_P` with `GearGameContent.GearGameAID`; it does not establish
main-campaign Museum/Kilo gameplay or the normal frontend campaign route.

## Original graph preservation

`campaign_graph.py` reads both byte orders independently of the converter.
It compares sequence membership, parent relationships, typed connectors,
remote-event names/instances, objective identifiers/settings, selected variable
values and startup streaming settings. References resolve to exact resource
identities and outer chains. Invalid references/input indices, cyclic outers,
malformed tags/counts and unmodelled native trailers fail. In-range references
to the wrong object also fail the original/converted comparison.

| Package | Sequence objects | Connected outputs | Variable references |
| --- | ---: | ---: | ---: |
| SP_E2_P | 226 | 83 | 76 |
| SP_E2_01_S | 58 | 23 | 27 |
| SP_E2_02_S | 226 | 104 | 122 |
| Total | 510 | 210 | 225 |

The 510 objects include eight `InterpData` sequence members. Their group
references and stored lengths are checked; full cinematic track behavior is
outside this audit. Omitted class defaults are not inferred. Nonempty
`SeqAct_Interp.SavedActorTransforms` maps are deliberately rejected.
All three comparisons pass against prior accepted artifacts. The runtime
validator requires staged workspace maps to match those artifacts byte-for-byte.

## Runtime evidence and regression gate

Private loader `GearGame-JudgmentLoader-ws18-sequence-objectives.exe`:
59,429,888 bytes, SHA-256
`8C0D1079302C8039CE6C082570A19F82C62BD33F8FF55F4327280CB9BB2AC312`.
Private patch `patches/judgment-port/0018-ws-sequence-objectives.patch`:
SHA-256 `E82C494919B013A44E4B0BA475B0D206169C9D05BF8530152043D3441E01637A`.
Reverse/forward replay reproduce the before-image and built source byte-for-byte
in a private scratch copy.

`-JUDGSEQUENCETRACE` enables bounded read-only execution logging. After the
objective action completes, loaded script reflection reads the local player's
objective manager and actual array entries. It does not guess Judgment-only
offsets or add a GearGame dependency to Engine.

`validate_campaign_fixture.py` regenerates the three graph comparisons and
checks runtime operation classes, connector descriptions/counts, ordered
startup milestones, four factory outputs, resulting objective state and
continuing seven-level ticks. Native framing alone, an objective action without
objective state, wrong objective names and truncated traces cannot pass.
Fallback calls and script warnings remain visible. Fallback counts are the
highest reported logging thresholds, not exact totals.

Final 75-second NullRHI PkgInfo, thin-map and SP_E2_P tests pass, including the
campaign gate. SP_E2_P records 11,374 exact loads, zero size mismatches/fatal
errors, ten paired ticks and a final tick at 71.18 wall-clock seconds.
The separate 100-second D3D9 test passes with the same loads, 15 paired ticks
(last 98.36 seconds) and 4,319 presented frames (last 99.73). Both runs validate
41 activation, 46 completion and 68 output reports against the original graphs.
The first objective is observed at 56.87 seconds in the diagnostic headless run
and 59.91 seconds in the rendered run.

`ScreenShot00005.bmp` remains dark and blue; no rendering fix is claimed.
Screenshot SHA-256:
`33E92967F7B78E308690640432899FB64A8026F97F88E2B93518A202E5646E32`.
111 unit tests pass, including 28 new synthetic graph/milestone tests.

```powershell
./run_loader_regressions.ps1 -Cases sp_e2_p -CampaignStartup
./run_loader_regressions.ps1 -Cases sp_e2_p -CampaignStartup -BootSeconds 100 -Renderer D3D9 -MaterialTrace -CaptureScreenshot
```

The harness defaults to ws18. `-CampaignStartup` enables the trace and requires
the independent campaign audit; loader survival alone cannot satisfy that
option. Graph reports live under `_judgment-scratch/e2-surface`. Runtime tags:
`ws18-objectives-null-20260930`, `ws18-campaign-render-20260930` and
`ws18-final-campaign-20260930`.

## Remaining campaign work

Observed gameplay fallbacks include `AIDirector.Init`, `AISystem.GetInstance`,
`SmartSpawner.SetInstance`, `SmartSpawner.RunVisibleSpawnPointsCheck` and
`GearAI.PickGoal`. `AISystem.GetInstance` currently returns the generic zero
result; companion possession warns about missing AI-system/squad data. These
need evidence-backed implementations before encounters can be considered
working. HUD fallbacks include `CacheProjectionMatrix`, `DrawWeaponInfo` and
`Canvas.DrawIcon`. Repeated AI logging warnings are retained.

Next work should reconstruct the required director/spawn-system interfaces and
validate the first encounter, alongside streamed lightmap/environment texture
recovery. Checkpoint restoration and a transition into another mission remain
separate milestones.

All source/build/content/runtime work stays in
`C:\Games\Gears 3 Files\Judgment Port Workspace`. The protected Gears 3 audit
checks 20,284 files with zero changes. Only original tooling and documentation
are committed; packages, engine patches/source, reports and binaries stay private.

Session XXVI adds a separately flagged ws19 native-accessor experiment. Three
original companion AI controllers now share a real rooted AISystem singleton,
and the live SmartSpawner reaches SetInstance. The null-system possession
warnings disappear while missing Squad warnings remain. Native subsystem
initialization, Tick, cleanup and encounters are explicitly still incomplete.
The rendered experiment preserves this startup/objective milestone; ws18
remains the harness default. See `AI-NATIVE-CHECKPOINT.md`.
