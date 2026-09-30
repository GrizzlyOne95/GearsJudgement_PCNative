# Judgment streaming geometry checkpoint — September 30, 2026

Continues the skeletal checkpoint `56f9dfe` on the separate converter branch
`judgment/skeletalmesh-20260930`. Engine changes, builds, map staging and tests
use only `C:\Games\Gears 3 Files\Judgment Port Workspace`, branch
`judgment/port-workspace`. The shared campaign source is protected.

## Verified result

| Package | Fully converted exports | Native exact-size loads | Bytes |
| --- | ---: | ---: | ---: |
| SP_E2_P | 1,433/1,433 | 1,402 | 11,814,162 |
| SP_E2_01 | 4,919/4,919 | 4,756 | 26,658,916 |
| SP_E2_02 | 3,054/3,054 | 2,359 | 7,763,000 |
| SP_E2_W | 61/61 | 54 | 319,459 |

All four archives have zero partial/unsupported exports. Runtime loads total
**8,571**, with zero serialized-size mismatches. Baird is possessed and the
world ticks. SP_E2_01, SP_E2_02 and SP_E2_W deserialize and post-load; startup
then fails explicitly on missing `SP_E2_01_S`. Not every export is requested
by the runtime, so offline conversion counts and observed load counts differ.

This remains a headless loading checkpoint. Logs report missing texture mip
bulk data, including shadow and sky textures. Pixel detiling, external texture
caches, audio codecs, collision behavior, visible rendering and playable
Judgment campaign behavior are not established by these checks.

## Changes and evidence

- Bounded serializers cover static/fractured meshes, component LODs, vertex and
  texture lightmaps, override/painted colors, decals, BSP model/components,
  cooked convex caches, light volumes, collection matrices, and populated Level
  maps/visibility/distance-field data. Half UVs and WORD indices swap at their
  actual widths. PhysX and compressed visibility bytes remain opaque.
- Native Level light-sample and distance-field colors use `FColor.DWColor()`:
  each DWORD swaps. Tagged Color properties retain their existing script layout.
- Dominant light components write `TArray<WORD>` before `Super::Serialize`.
  Their shadow data is converted before the component prologue and tag stream.
- `IsJudgmentConvertedPackage` requires v845 and the explicit loader opt-in.
  Retail streaming names require the exact comma-separated command-line list;
  `Parse(..., FALSE)` preserves commas. Ordinary PC packages retain their layout.
- `UModel::Serialize` expands console 16-byte FVert records into PC 24-byte
  records, initializing backface UVs from front-face UVs. The old bulk read
  consumed the correct file size but packed records at the wrong in-memory
  stride, causing `UModelComponent::BuildRenderData` to assert. The expansion
  clears that assertion. No assertion or geometry is bypassed.
- Package-qualified preload logs verify each loaded export's index, class,
  offset and size against an independent C++ package manifest. Independent BSP
  checks validate all node-referenced vertex/point indices. SP_E2_01 includes
  unused vertices with stale indices; checks distinguish these from used data.
- 50 unit tests pass, including every truncation point of populated Level,
  BSP, mesh, component and dominant-light synthetic archives. Invalid counts,
  refs, widths and collection counts reject and roll back. All prior skeletal
  tests and four packed-position telemetry checks still pass.
- PkgInfo exits 0. The thin-map boot regression remains alive and possessed
  for 75 seconds. Source patch reverse-application checks pass.

## Retained artifacts

Fixtures/evidence are in `C:\Games\_judgment-scratch\e2-surface`:

| Converted fixture | SHA-256 |
| --- | --- |
| `SP_E2_P.geometry-20260930.le.xxx` | `6C53F7DEA1DAD18B7BA4A0BF1EC27297FD8B7581B437B60D9A432498F879F98C` |
| `SP_E2_01.geometry-v3-20260930.le.xxx` | `6E4F864B7B15FF53049CA1E8852456BE437441A92CD4B8E6246A97AFDF5E8409` |
| `SP_E2_02.geometry-assessment-20260930.le.xxx` | `A588A9899BFA3FBF11005A2011FFF5E36956FE529742E12428113598F2CAFD32` |
| `SP_E2_W.dominantlight-20260930.le.xxx` | `F5BD79F422DB1B0AEBF27E4FBB9868B719AD8B8CCB09F5EEEEEFCC2FA6067681` |

Each has a matching `*.manifest.json`. `geometry-e2w-20260930.validation.json`
records byte-identical regeneration, valid package tables and BSP topology,
8,571 runtime matches and FVert expansion counts. The earlier two-package
validation and original skeletal fixture/evidence are also preserved.

Staged files are only under the workspace's `GearGame\Content\Maps`:
`Judgment_SP_E2_P.gear`, `SP_E2_01.gear`, `SP_E2_02.gear`, `SP_E2_W.gear`.
`Judgment_SP_E2_P.before-geometry-20260930.gear` preserves the previous stage.

Loader `Binaries\Win32\GearGame-JudgmentLoader-ws10-streaminggeometry-verts.exe`:
59,413,504 bytes; SHA-256
`9710D48EE86D3F39C8BF41EF96B2D83CA34BE38212F76CFDD75E60D59FF17A82`.
Private/untracked incremental source patch
`patches\judgment-port\0010-ws-streaming-geometry.patch`, SHA-256
`D023A7A6F637B5E2E00A4238F73126D3495601A7CDB857ECCA8391BC3B1105F9`.
Apply after patch 0009/current skeletal checkpoint, not directly to the campaign
source. Before-images are in `_judgment-scratch\ws10-engine-before`.
Reverse check: `git apply --check --reverse --ignore-whitespace <patch>`.

Runtime logs/results are under workspace `GearGame\Logs`:
`regress-ws10-streaminggeometry-verts-{pkginfo,thinmap,sp_e2_p}.log`,
`regress-ws10-streaminggeometry-e202-sp_e2_p.log`,
`regress-ws10-streaminggeometry-e2w-sp_e2_p.log`, and their `*-results.json`.
The first ws10 run preserves the BSP stride assertion for comparison.

## Reproduce and continue

```powershell
python -m unittest test_be2le test_skeletal_mesh test_native_geometry -q
.\run_loader_regressions.ps1 -Exe GearGame-JudgmentLoader-ws10-streaminggeometry-verts.exe -Tag NEW_UNIQUE_TAG -StreamingPackages 'SP_E2_01,SP_E2_02,SP_E2_W'
python validate_geometry_fixture.py '<new SP_E2_P log>' '<new validation JSON>'
python protect_campaign.py verify 'C:\Games\_judgment-scratch\campaign-protection-20260930-skeletalmesh.json'
```

Every launch uses `-user -NOHOMEDIR -nullrhi -nosound`, keeps config/save writes
in the isolated copy, and stops only its tracked Judgment process. Do not stage
partial conversion outputs or whitelist unconverted packages.

Next: `SP_E2_01_S`, the gameplay/navigation package, assesses at 438 fully
converted exports, 116 partial and six unmodelled native tails. Its partial
output is retained in scratch and is **not staged**. Most failures are immutable
CoverSlot arrays; ActorReference and native Pylon/navigation tails also need
explicit models. The later SP_E2_02_S/SP_E2_03_S packages will need the same
gameplay/navigation work. Missing texture mip data is a separate rendering task.
