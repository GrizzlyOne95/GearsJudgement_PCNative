# Judgment player mesh and first rendered prototype

Session XXIII, 2026-09-30. Continues converter commit `d1a4180` on
`judgment/skeletalmesh-20260930`. Engine source, builds, configuration and staged
content remain in the separate `Judgment Port Workspace` copy on
`judgment/port-workspace`. The Gears 3 campaign installs and shared source stay
protected by the retained file baseline.

## Verified result

The **100-second D3D9 prototype test passes**. It loads **11,374 exports with
exact native byte counts**, zero size mismatches and no fatal errors. Seven
levels continue ticking: 14 paired reports, last at wall-clock 96.17 seconds,
tick serial 3,901, game time 63.099. The last presentation report records
**3,825 frames at 1280×720**, at wall-clock 95.01 seconds.

Baird's existing `GearPawn_COGBairdJack` now loads its intended
`COG_Baird_Jack.Skel_Mesh.COG_Baird_Jack_CamSkel`, associated physics asset,
123 reference bones, 123 local atoms and 123 component-space bases. Its animation
tree is present and the pawn is unhidden after startup. `AnimSets.Num()` is 15;
this measures the array length, not the number of valid animation sets. The
former NULL SkeletalMesh warnings for Baird are gone.

The engine captured `GearGame\ScreenShots\ScreenShot00000.bmp`, 1280×720,
2,764,854 bytes. Visual inspection shows the player character and surrounding
level geometry. **Textures and lighting are visibly incorrect**: the scene is
mostly dark, with noisy purple/blue materials. This is the first verified
rendered prototype, not verified playable campaign gameplay.

Screenshot SHA-256:
`3F3B895D231960619F9FA2C2E2553E08BC39E8690C469E4E7476119EDB9348D0`.
Independent pixel inspection finds 20,140 distinct colors, rather than a blank
frame. No screenshot retouching or synthetic replacement was used.

Final PkgInfo, 75-second thin-map and 75-second SP_E2_P headless regressions
all pass on the same ws16-v2 executable. The gameplay cases require a valid
player mesh and continuing world ticks. SP_E2_P again loads 11,374 exact exports;
its last tick report is at 71.13 seconds. **72 unit tests pass**.

## Character asset extraction

The missing character package is embedded in Xbox `GearGame.xxx`, a fully
compressed startup archive containing 305,867 exports, including scripts.
`--decompress-container` reconstructs 109,958,331 bytes. Source SHA-256:
`78BACD43551F8D8BA691CEC6877DBA2D1D59478C1CD0D453E7FB1918F613B798`.

`extract_asset_package.py` selects the 109-object `COG_Baird_Jack` ownership
group, converts every selected object, and emits its 108 children in a separate
package. The old root becomes the package itself. External references become
56 imports; 156 typed payload reference fields are remapped. FName instance
numbers and original payload/bulk physical offsets are retained. Unselected
source bytes remain unreachable padding, so this first implementation preserves
the source file length. It is deliberately not a compact general asset writer.

The exported surface is limited to modelled mesh/socket, physics, material,
texture and related asset classes. Unknown classes and ambiguous array types
fail closed. Failed speculative parsing rolls back reference locations as well
as bytes and counters. No integer scanning is used to discover UObject references.

The first extraction exposed an ambiguity hidden by same-size endian conversion:
`Constraints` can be FloatProperty or ObjectProperty elements. Runtime v1
correctly rejected an old export index in PhysicsAssetInstance. Extraction v2
resolves this array using the exact class owner from the script type index.
Tests cover that collision, matching scalar values which must not be remapped,
instance names, reference rollback, invalid references and unsupported classes.
UInterfaceProperty's persistent value is also corrected to one object index;
its native interface pointer is reconstructed by the engine.

Artifact in `C:\Games\_judgment-scratch\character-surface`:

- `COG_Baird_Jack.asset-v2.le.xxx`, 109,958,331 bytes, SHA-256
  **CA02D1B119E74E3A0A9C2AD3898ED40E86A31F9173F459BB8E43F3C19382549E**.
- Matching extraction receipt and `COG_Baird_Jack.asset-v2.manifest.json`.
- `baird-rendered-prototype-20260930.validation.json` checks regeneration,
  table bounds, all 108 exact runtime loads, and all 17 body/16 constraint
  references against the actual extracted object classes and ownership.

Staged only as workspace `GearGame\Content\Maps\COG_Baird_Jack.gear`. Add
`COG_Baird_Jack` to the converted package whitelist. The harness now distinguishes
asset packages from streamed levels, and defaults to this character package.
The seven map artifacts regenerate byte-identically and remain unchanged.

## Engine changes and reproduction

Working loader:
`Binaries\Win32\GearGame-JudgmentLoader-ws16-render-prototype-v2.exe`,
59,420,672 bytes, SHA-256
**89C042031C526FD86A94F30600AFBC26644729A2D2704BCBF6CD47F8EFD0E646**.

Private incremental patches, following accepted 0014:

| Patch | SHA-256 |
| --- | --- |
| 0015-ws-player-mesh-trace.patch | 6BE74D3F199B523013A716D802651B574244DCDA459D9381DBA81FABF7DF69A9 |
| 0016-ws-render-prototype.patch | 205669DA2E66A23058264080AA5D4511DF83A7DC46420DD9C8440370D217686C |

0015 reports the actual possessed pawn mesh at each periodic tick checkpoint.
0016 honors an explicit `NoTextureStreaming` flag before RHI initialization,
only for Judgment opt-in. The previous late parsing permitted startup mip
transfers and the first D3D9 assessment failed in `CopyMipToMipAsync`.
Disabling streaming early fixes that prototype failure while retaining texture
resource objects. The existing NullRHI behavior remains in place.

0016 also reports successful D3D9 presentations under `JUDGPROTOTRACE` and
requests one engine screenshot after 15 seconds of world time under `JUDGSHOT`.
Normal launches without those flags do not emit the new diagnostics/capture.
Both new patches pass reverse applicability checks against current source.
Before-images are retained in scratch `ws15-engine-before` and `ws16-engine-before`.

The initial ws16 binary predates a screenshot screen-message restoration fix;
use **ws16-v2**, whose source includes that fix. Rejected asset v1 and the ws15
D3D9 failure remain retained evidence, not the accepted staged content.

```powershell
python -m unittest discover -q
.\run_loader_regressions.ps1 -Tag NEW_RENDER_TAG -Cases sp_e2_p -BootSeconds 100 -Renderer D3D9 -CaptureScreenshot
.\run_loader_regressions.ps1 -Tag NEW_HEADLESS_TAG -Cases @('pkginfo','thinmap','sp_e2_p')
python validate_asset_fixture.py '<new report JSON>' '<rendered runtime log>'
python protect_campaign.py verify 'C:\Games\_judgment-scratch\campaign-protection-20260930-skeletalmesh.json'
```

Final logs/results under workspace `GearGame\Logs`:

- `regress-ws16-d3d9-prototype-v2-sp_e2_p.log` and results JSON.
- `regress-ws16-final-regressions-{pkginfo,thinmap,sp_e2_p}.log` and results JSON.
- Earlier `regress-ws15-baird-asset-v2-sp_e2_p.log` is the 100-second headless
  character milestone. Asset v1 and the first D3D9 assessment failures are retained.

New geometry/animation reports in scratch `e2-surface` verify all seven maps
against the rendered run. All 28 animation sequences still produce 6,636 finite
native samples; independent parsing verifies 3,836 encoded tracks, 48,415 keys,
453 frame tables and 164 combat poly references. The base map's packed-position
samples still match independent decoding.

## Remaining work

Prioritize Xbox texture-cache recovery, packed mip-tail reconstruction and
detiling, with an independently verified player/environment texture fixture.
The imported material dependencies still mix incomplete Judgment asset coverage
with available PC fallback assets. Character animation-set coverage, correct
lighting/postprocessing, camera/input, collision, AI/cover behavior, inventory and
audio require further validation. The rendered run records 3,925 Accessed None
warnings, mainly AI logging. A non-null physics asset does not prove collision.

Final protection check: **20,284 protected files, zero changes**. All test helpers
were stopped at their deadlines. Proprietary source, assets, binaries, symbols,
screenshots and private engine patches remain excluded from converter commits.
