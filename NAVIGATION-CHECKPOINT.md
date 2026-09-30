# Judgment cover/navigation checkpoint — September 30, 2026

Continues streaming-geometry converter commit `9c14d4c` on separate branch
`judgment/skeletalmesh-20260930`. Uses the existing isolated ws10 engine build;
no additional engine edits or shared campaign mutations are needed.

Final protection verification checks **20,284 files, zero changes** across both
Gears 3 campaign installs and the shared campaign source. No Judgment test
process remains running.

## Verified result

- `SP_E2_01_S`: **560/560 exports fully converted**, zero unsupported/partial;
  1,692,797 bytes. All cover-slot properties, ActorReference/RouteList, four
  NavigationMeshBase tails and two Pylon tails now convert.
- `SP_E2_Audio`: **8/8 exports fully converted**, 6,606 bytes. This is the audio
  routing level; it does not establish audio playback or XMA codec conversion.
- Six retained packages now convert **10,035/10,035 exports**. The previous four
  geometry/weather archives regenerate byte-identically after these changes.
- Native loading: **9,006 exact-size loads, zero mismatches**, including 428
  from SP_E2_01_S and seven from SP_E2_Audio. All four navigation meshes and two
  pylons load. The world ticks and Baird is possessed.
- Startup advances to missing `SP_E2_02_S`. That package's partial assessment
  is retained in scratch and **not staged**. It has 2,669 exports: 2,636 complete,
  one partial (`Profiles` array), and 32 native tails unmodelled (28 AnimSequence
  and four CombatZone). Later gameplay packages need the same animation work.

This is a headless serializer/loading checkpoint. AI traversal and cover
behavior, collision, animations, audio and visible gameplay remain unverified.
Missing texture mip bulk-data warnings still occur. The last run raises the
explicit missing-package critical error, followed by an access violation during
error shutdown (exit `-1073741819`); it is recorded as BLOCKED_AFTER_BOOT, not PASS.

## Serializer corrections

The inherited immutable-cover parser inferred the wrong property order and
widths. Actual `UStruct::SerializeBin` follows the Children/Next property chain
in declaration order. The manifest export list is reversed relative to that
chain; its listing order is not its serialization order.

`UBoolProperty::SerializeItem` emits **one BYTE per property**, even when bools
share a C++ bitfield. CoverSlot has 21 persistent booleans; three transient bools,
RejectedFireLinks and SlotValidAfterTime are absent. Enum-backed BYTE properties
emit FNames. The CPF_Native CachedPoly field is always skipped by
ShouldSerializeValue. These are explicit source rules, not width guesses.

BasedPosition is not ImmutableWhenCooked, so a cover-slip destination inside
SlotMoveRef has its normal nested tag stream. Native navigation edges instead
use C++ FBasedPosition's operator, which writes Base plus Position only. The
converter keeps those two forms distinct. Tag header reads now check their
own region bounds before touching truncated data.

`native_navigation.py` models navigation grammar version **43**, matching the
runtime's latest version: vertex/poly WORD arrays, mixed 14-byte edge-storage
records, transforms, border segments, bounds and typed edge bodies. Unknown
versions/classes fail and roll back. Supported edge classes are base/basic one
way, cross-pylon/back-reference, special-move/mantle/cover-slip, dropdown and
path-object. PC constructors rebuild allocation offsets/sizes after loading;
converted edge bodies retain their actual field widths.

Independent navigation validation preserves every scalar/array value through
BE/LE conversion and checks index ranges, including obstacle-mesh edge links
into the owning pylon's navigation mesh:

| Mesh | Vertices | Polys | Edges | Serialized edge bytes |
| --- | ---: | ---: | ---: | ---: |
| NavigationMeshBase_898 | 1,069 | 140 | 583 | 41,250 |
| NavigationMeshBase_899 | 564 | 283 | 0 | 0 |
| NavigationMeshBase_901 | 176 | 19 | 98 | 7,656 |
| NavigationMeshBase_902 | 96 | 48 | 0 | 0 |

## Artifacts and verification

Under `C:\Games\_judgment-scratch\e2-surface`:

| Fixture | SHA-256 |
| --- | --- |
| `SP_E2_01_S.navigation-20260930.le.xxx` | `E217B50BB477CCEC05DB938EAFAF5F2EC231A4AE25AE4D30D3B074EEE853A24A` |
| `SP_E2_Audio.navigation-assessment-20260930.le.xxx` | `C4F8787F5192FC048AF6D5DD16C9B6309E5FDF74DDD2F1BC84F6A287DD8370B9` |

Matching manifests have valid tables/references and texture/sound framing.
`navigation-20260930.validation.json` checks all 681 navigation edges and their
topology. `geometry-navigation-audio-20260930.validation.json` records byte-identical
regeneration and every observed native preload offset/size across all six maps.
Previous packed skeletal-position telemetry still matches independent decoding.

Staged only in `Judgment Port Workspace\GearGame\Content\Maps`:
`SP_E2_01_S.gear` and `SP_E2_Audio.gear`, alongside the four geometry-checkpoint
maps. Loader is still `GearGame-JudgmentLoader-ws10-streaminggeometry-verts.exe`
with private source patch 0010; see `STREAMING-GEOMETRY-CHECKPOINT.md` for its hash
and recovery details. Tests use `-NOHOMEDIR` and terminate only tracked helpers.

Runtime evidence under workspace `GearGame\Logs`:
`regress-ws10-cover-navigation-sp_e2_p.log`,
`regress-ws10-navigation-audio-sp_e2_p.log`, and their results JSON files.

**59 unit tests pass**, including every cover/navigation truncation point,
nested tagged destinations, every supported edge class, invalid bool/FName/
version/ref/count rejection and rollback of earlier valid array elements.

```powershell
python -m unittest discover -q
.\run_loader_regressions.ps1 -Tag NEW_UNIQUE_TAG -Cases sp_e2_p -BootSeconds 100
python validate_geometry_fixture.py '<new runtime log>' '<new validation JSON>'
python validate_navigation_fixture.py '<new navigation validation JSON>'
python protect_campaign.py verify 'C:\Games\_judgment-scratch\campaign-protection-20260930-skeletalmesh.json'
```

The harness defaults to the verified ws10 loader and all five converted retail
streaming names; its automatic tag is unique. It refuses to overwrite evidence.
Do not add SP_E2_02_S to that list until its remaining serializers pass.
