# Judgment texture recovery and material dependency checkpoint

Session XXIV, 2026-09-30, continuing `f724d9e` on
`judgment/skeletalmesh-20260930`. All engine, content and runtime work remains in
the separate `C:\Games\Gears 3 Files\Judgment Port Workspace` copy on
`judgment/port-workspace`. Both branches have been pushed to the existing
`GrizzlyOne95/GearsJudgement_PCNative` repository. Retail content, engine source,
private patches and executables remain outside Git.

## Accepted texture surface

**30 textures / 291 mip levels** now have uncompressed, inline PC pixel data:
Baird's six textures (67 mips, 8,738,240 linear bytes) and SP_E2_P's 23 character
textures plus its night color-grading lookup (224 mips, 14,031,168 linear bytes).
The retained C++ probe recovers external LZX bulk from each texture's own cache,
detiles normal allocations, unpacks mip tails and corrects byte order. Baird uses
`CharTextures.tfc`; the cigar and LUT also exercise `Textures.tfc`.

`replace_texture_pixels.py` integrates those standalone v828 fixtures into the
converted v845 package. It retains original object/name indices, NetIndex,
texture GUID and tagged settings, including SRGB, normal unpack arrays, clamp,
compression, LOD and cinematic metadata. It removes the Xbox cache/resource
memory properties, adjusts stripped base dimensions and writes absolute inline
bulk offsets. Only each texture's two SerialSize/SerialOffset INT fields change
in the original file prefix. All remaining payload and bulk offsets stay fixed.
This append-only writer is deliberately not a compact package rebuild.

Independent C++ manifest and tagged-property audits verify all 291 mip byte
sequences, unchanged settings, 102 other Baird exports and 1,409 other map
exports. Both packages regenerate byte-identically. GUID mismatch, malformed
bulk offsets, incomplete geometry and wrong fixture selection fail closed.

## Material parents

The first recovered-texture render still reached `EngineMaterials.DefaultMaterial`
for all three player material slots. The opt-in material trace showed that the
PC parents existed but their nested package imports were not being loaded.
The extracted startup group inherited `PKG_RequireImportsAlreadyLoaded` from
the monolithic Xbox archive. `extract_asset_package.py --resolve-imports`
clears only that bit, permitting the normal PC linker to resolve dependencies.
Historical extraction mode remains unchanged unless the option is requested.

The accepted player now reaches these PC master materials:

- Body: `ALL_SoldierShaders.Rift.Materials.Master.M_Soldier_SkinShader`
- Eye: `ALL_SoldierShaders.Rift.Materials.Master.M_Eye_MASTER`
- Hair: `Hair.Materials.M_Hair_Master_Smoke`

Runtime tracing independently confirms that **all six recovered Baird textures**
are used by these materials at their emitted dimensions and mip counts.
This is a prototype using the existing PC masters; exact Judgment shader parity
and every external material dependency are still unverified.

## One-mip lookup and rejected attempt

SP_E2_P's 256x16 `PF_A8R8G8B8` `LUT_Night` has one mip and omits its tail-index
property. The first implementation assumed an omitted index meant -1 and
produced black pixels. That **base-textures-v1 artifact is rejected** even
though its native framing/render test passed. The source class default is zero.
The corrected probe treats this level as a packed allocation.

`xg-tail-oracle` measured this exact geometry with Judgment's April 2012
`Xbox360Tools.dll`: tail base zero, 32,768 allocated bytes, 16,384 useful bytes,
DWORD byte reversal, no duplicates or writes beyond allocation.
`validate_lut_fixture.py` checks **all 4,096 pixel / 16,384 byte addresses**
against that independent cooker map. The corrected output contains 4,096
distinct colors. Pixel SHA-256:
`2C4415A6AAFCD5BA66355819F937BA84A5E6AFA6753A43FF3ACC019388D259E4`.

## Private artifacts and reproduction

| Accepted artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Character `COG_Baird_Jack.asset-v4-deps.le.xxx` | 118,700,264 | BA5FBC78DD44680DD934912D12433C21EC13F7E975144C47159D28430F84371E |
| Base map `SP_E2_P.textures-v2-20260930.le.xxx` | 25,859,182 | E99602F9221A3063E771488EC09A39C9F182A5E748B7CFE961E80D847261307C |
| Loader `GearGame-JudgmentLoader-ws17-material-trace.exe` | 59,422,720 | 794CFE38D3207A69EB27793AED577337EFCFF738DC43D5F1F3CADCFC4A309C41 |

Character fixtures/manifests/reports live in `_judgment-scratch\character-surface`;
map fixtures live in `_judgment-scratch\e2-surface`. The packages are staged only
as private workspace `GearGame\Content\Maps\COG_Baird_Jack.gear` and
`Judgment_SP_E2_P.gear`. The six streamed map artifacts remain byte-identical.

Private engine patch `patches\judgment-port\0017-ws-material-trace.patch` follows
0016, SHA-256 `431D7717D05B664D610B410FE02D393C2AB489DF2DD2DA7BC52427833B3C5187`.
It passes reverse-apply validation. The trace runs once after game time 15 only
with Judgment opt-in, `JUDGPROTOTRACE`, `JUDGMATERIALTRACE`, and a real renderer.
Without the additional flag it does not inspect materials. The harness defaults
to ws17 and enables material tracing only with `-MaterialTrace`.

Build the standalone probe with `GEARS3_SOURCE_ROOT` set to the isolated copy.
Current probe SHA-256:
`E1E55B41C181D038624E20EDA1C4234ADC0464CDACDE334E9C03B6B91B98FA83`.
The rebuilt probe's six packed Baird fixtures match the retained originals.

```powershell
python extract_asset_package.py <GearGame.xxx.unc> <GearGame.xxx.json> COG_Baird_Jack <asset-base.le.xxx> <array-types-v845.json> --resolve-imports
python replace_texture_pixels.py <asset-base.le.xxx> <texture-fixture-directory> <output.le.xxx>
./run_loader_regressions.ps1 -Cases sp_e2_p -BootSeconds 100 -Renderer D3D9 -MaterialTrace -CaptureScreenshot
```

Preserve old outputs and receipts. The tools refuse to replace retained evidence.
The screenshot allocator creates a new numbered BMP on each capture.

## Verification and remaining work

The accepted Baird dependency test already passes 100 seconds, 11,374 exact
loads, zero size mismatches/fatal errors, 14 paired tick reports and 4,007
presented frames. PkgInfo, 75-second thin map and 75-second SP_E2_P NullRHI tests
also pass on ws17. **83 unit tests pass.**

The final corrected-base **100-second D3D9 test passes**: 11,374 exact native
loads, zero size mismatches/fatal errors, 15 paired tick reports, last at 98.25
seconds, and **4,319 presented frames**, last reported at 99.64 seconds.
`ScreenShot00004.bmp` is 1280x720 with 28,118 distinct colors, SHA-256
`E3DE45540FA728FB69C24971109BC1CA11E03B2A021D114B5FE7031A5BF35ABC`.
Visual inspection shows recognizable armor detail, but the blue cast and dark
environment persist. Correct LUT addressing alone did not resolve the scene.
This is not verified playable campaign gameplay.

The final corrected-base 75-second NullRHI test also passes: 11,374 exact loads,
10 paired tick reports, last at 71.19 seconds. The final protected-campaign audit
checks 20,284 files with zero changes.

Retained accepted evidence includes `baird-final-base-textures-v2-20260930.validation.json`,
`base-textures-v2-20260930.validation.json`, `lut-packed-v2-20260930.validation.json`,
`geometry-base-textures-v2-20260930.validation.json`, and
`animation-base-textures-v2-20260930.validation.json` under the private scratch roots.
The unchanged animation/navigation audits still confirm 28 sequences, 3,836
encoded tracks, 48,415 keys, 453 frame tables and 164 combat-zone polygon references.

The next major surface is streamed level textures: SP_E2_01 alone includes 270
ordinary textures, 192 lightmaps and 100 shadow maps. Light/shadow texture native
class trailers, unsupported physical masks, remaining material dependencies,
animation coverage, input/camera, collision, cover, AI, inventory and audio remain.
