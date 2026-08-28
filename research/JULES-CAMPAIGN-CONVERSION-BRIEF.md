# Judgment native-PC campaign conversion research brief

## Goal

Advance an independently built, native Win32 Gears of War: Judgment campaign/menu build.
Multiplayer is out of scope for now. The eventual campaign co-op model should mirror the
Gears 2 Hollow Steam co-op systems.

Do not add retail game packages, extracted assets, XEX/PDB files, keys, or other proprietary
binaries to this repository. Work from the source/tooling already present and synthetic fixtures.

## Proven local milestone (2026-08-25)

The direct v845 Win32 loader and the offline platform converter now boot a converted Judgment
`GearGame_P` thin persistent level end to end. This is not the older Gears 3 control map.

Verified lifecycle:

- package version 845, 98 names, 14 imports, 10 exports;
- all 10 exports convert, including five modeled native tails;
- map load, first render, and first world tick complete;
- `GearPC_AID` spawns;
- `GearPawn_COGBairdJack` spawns and is possessed.

A fresh local executable was built from the source tree as
`GearGame-JudgmentLoader-v60-nativecontent.exe`. The proprietary engine source and binary are
intentionally not part of this repository.

## Two platform-boundary corrections found by the live loader

### Empty seek-free ShaderCache

The 29-byte `ShaderCache.SeekFreeShaderCache` export contains a 12-byte UObject/property prefix
and this 17-byte native tail:

```
BE source: 00 00 00 0A | 02 | 00 00 00 00 | 00 00 00 00 | 00 00 00 00
fields:    priority=10 | SP_XBOXD3D | compressed-map count | shaders | material maps
LE target: 0A 00 00 00 | 00 | 00 00 00 00 | 00 00 00 00 | 00 00 00 00
```

The target byte is `SP_PCD3D_SM3=0`, confirmed by the Win32 runtime loading
`LocalShaderCache-PC-D3D-SM3.upk`. Conversion accepts only the exact empty Xbox shape. Any
non-zero cache count fails closed because populated Xbox shader data must be rebuilt for PC.

### Empty FVert bulk array

`FVert` is 16 bytes in console-cooked data and 24 bytes on PC because PC adds an 8-byte
`BackfaceShadowTexCoord`. `TArray::BulkSerialize` validates its serialized element-size word even
when count is zero. For the thin map's empty array, changing only the header from 16 to 24 is safe.
For a populated array, elements must be widened and all following offsets rebuilt; same-length
field swapping must fail closed.

## Expected next boundary

Real campaign maps contain populated native structures. The current same-length converter can
handle property graphs and empty/minimal native tails, but populated Models, static meshes,
textures, audio, collision, visibility, and level maps will require one or both of:

1. explicit per-class element converters where source and target widths match; and
2. a relocation-capable package reserializer when Xbox and PC widths differ.

The package summary, names, imports, exports, depends table, generation data, and serial offsets
must remain internally consistent after any growth. Bulk-data and external-cache references must
not be treated as ordinary package-relative offsets without evidence.

## Jules work requested

Produce an evidence-backed implementation contribution in this repository, using only synthetic
fixtures and the checked-in tools.

Priority order:

1. Design a relocation-capable v845 package rewrite layer that can grow/shrink export payloads,
   recompute export serial offsets/sizes, and preserve every other table/reference invariant.
2. Add synthetic regression fixtures/tests for:
   - the empty ShaderCache tail above;
   - an empty FVert bulk header retarget 16 -> 24;
   - rejection of a populated ShaderCache;
   - rejection or relocation of a populated width-changing FVert array.
3. Identify which code in `package-probe/src/main.cpp` and the existing Python tools can be reused
   rather than duplicated.
4. Document a staged path from the thin `GearGame_P` success to one real campaign level and then
   the retail Judgment frontend/menu path.

Prefer small reviewable commits. Do not claim runtime success without a local Win32 log; Jules
cannot run the proprietary loader, so mark those checks as downstream local validation steps.

## Relevant repository files

- `package-probe/src/main.cpp` — package summary/tables, decompression, manifest and fixture work.
- `package-probe/readme.md` — current probe workflows.
- `PORTING-NOTES.md` — port history and known boundaries.
- `redirect_imports.py`, `proptypes.py`, `gen_native_block.py` — existing binary/package helpers.
- `tests/` — existing Python test style.

