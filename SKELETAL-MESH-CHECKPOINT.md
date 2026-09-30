# Judgment skeletal-mesh checkpoint — September 30, 2026

Continued from converter commit `3baf313` in branch
`judgment/skeletalmesh-20260930`. Engine source/build/output stays in
`C:\Games\Gears 3 Files\Judgment Port Workspace`, branch `judgment/port-workspace`.
The shared September Gears 3 source and both campaign installs are protected.

## Result

- `SP_E2_P`: **1,433/1,433 exports fully converted**, zero partial or unsupported
  exports, unchanged package length of 11,814,162 bytes.
- The only output changes since `SP_E2_P.shadercache.le.xxx` are inside the
  three skeletal-mesh native tails. All skeletons, sections, indices, chunks,
  GPU vertices, alternate influences, bone mappings and trailers are preserved.
- The Win32 loader expands console packed positions into the PC float vertex
  format. This path requires v845 and the opted-in Judgment console archive.
- Native run: **1,402 exact-size export loads, zero mismatches**. All three
  meshes load; four packed LODs expand. Their first decoded positions agree
  with independent source-DWORD decoding within 0.0001 Unreal units.
- `Judgment_SP_E2_P` reaches map-loaded, first world tick, Baird spawn and
  player possession. It then stops because streamed package `SP_E2_01` is
  absent. This is a headless loading milestone; visible rendering and a
  playable Judgment campaign remain unverified.

The meshes are `COG_Barrick` (1,071,037 bytes), `COG_Clayton_Carmine`
(893,257 bytes), and `COG_Gus_Summer_CamSkel` (1,149,623 bytes). Each has
two LODs; Carmine uses packed positions in both, the others only in LOD1.

## Retained artifacts

All paths below are relative to `C:\Games`.

| Artifact | Path / SHA-256 |
| --- | --- |
| Converted fixture | `_judgment-scratch\e2-surface\SP_E2_P.skeletalmesh-20260930.le.xxx` |
| Fixture hash | `6B3893A3C6830AF6DCE5F1EDB0C2502852B4D970D8B1B3F2660A19AAEB11E3B0` |
| Staged runtime map | `Gears 3 Files\Judgment Port Workspace\GearGame\Content\Maps\Judgment_SP_E2_P.gear` (same hash) |
| Verified loader | `Gears 3 Files\Judgment Port Workspace\Binaries\Win32\GearGame-JudgmentLoader-ws9-skeletalmesh-verified.exe` |
| Loader hash | `C0B765E284970D0A53447C0D2C7BF465FA457A9E9A0D3BF6A70A08FD09EB5AE7` |
| Private engine patch | `Gears 3 Files\Judgment Port Workspace\patches\judgment-port\0009-ws-packed-skeletalmesh.patch` |
| Patch hash | `DA25ED22E896252C3275B8810E952763649152705E266745505E8D988C61016E` |
| Previous stage backup | `_judgment-scratch\e2-surface\Judgment_SP_E2_P.before-skeletalmesh-20260930.gear` |
| Independent package manifest | `_judgment-scratch\e2-surface\SP_E2_P.skeletalmesh-20260930.manifest.json` |
| Fixture/position validation | `_judgment-scratch\e2-surface\SP_E2_P.skeletalmesh-20260930.validation.json` |
| Runtime results | `Gears 3 Files\Judgment Port Workspace\GearGame\Logs\regress-ws9-skeletalmesh-results.json` |

The engine patch is deliberately private/untracked, following the build-tree
repository's source exclusion policy. It applies to the retained
`gears_of_war_3_2011-09-14\_Backups\src-judgment-20260919\Engine\Src\UnSkeletalMesh.cpp`
baseline. Reverse application was checked against the current isolated source.

## Verification

`python -m unittest test_be2le test_skeletal_mesh -q` passes **39 tests**.
The mesh tests cover all eight packed/float, half/full UV and color variants,
every truncation point in a synthetic mesh, negative/excessive counts,
incorrect strides, adjacent-export bounds and rollback of bytes/counters.

The independent C++ package probe reports zero invalid name/resource/serial
references, exact import/export table boundaries, 24/24 valid texture frames
and 254/254 valid sound frames. This validates framing, not platform texture
or audio codec conversion.

`run_loader_regressions.ps1` runs only the isolated loader and adds
`-NOHOMEDIR` to keep configuration/save writes local. PkgInfo passes with
exit 0; the thin map stays alive for 75 seconds with possession; SP_E2_P
reports `BLOCKED_AFTER_BOOT` with the missing streamed package. The harness
returns 2 for that known blocker, rather than calling it a playable-map pass.

`protect_campaign.py verify` reports **20,284 files, zero changes** against
`_judgment-scratch\campaign-protection-20260930-skeletalmesh.json`. It covers
the campaign rebuild, Jacinto 1.1.1 and shared September `Development\Src`;
source, binaries, configuration, launchers and saves are SHA-256 checked,
while large cooked content receives size/mtime checks.

## Next work

The missing `SP_E2_01.xxx.unc` is already available under `e2-surface`.
An assessment-only output, `SP_E2_01.skeletalmesh-20260930.le.xxx`, converts
3,039/4,919 exports with 1,880 unmodelled tails. It has **not** been staged.
Most remaining classes are StaticMeshComponent, BrushComponent, static meshes,
LightMapTexture2D/ShadowMapTexture2D, and light component tails.

Continue by modelling the streaming package's remaining serializers and
their lighting/geometry dependencies. Keep native layout conversion distinct
from Xbox texture detiling, audio transcoding and PC shader generation; each
still needs its own render/playback validation. Preserve the fully converted
persistent-map fixture and the protected campaign baseline as regression controls.
