# Judgment vs Gears 3 PC — Engine.u native class delta

Generated 2026-08-16 by `scan_classes.py`, comparing the export tables of
`GearGame\ScriptFinalRelease\Engine.u` from each build. A class's property chain is just the
exports whose `object_path` is `Engine.<Class>.<Member>`, so this needs only the export table —
the layer already proven v845↔v828 compatible (see `PORTING-NOTES.md`).

This is the native-class reconstruction worklist. It is what currently blocks Judgment's startup
packages from loading in a native Windows build.

> **Revised 2026-08-16.** The first version of this scan matched only 3-part
> `object_path`s, which silently skipped every `ScriptStruct` whose members nest deeper.
> It therefore missed 10 differing structs — including `FPostProcessSettings` gaining
> **43** members, the largest single delta in the package and the blocker after `Pylon`.
> Numbers below are from the corrected scan (`parts[-2]`, any depth).

## Headline

| | |
| --- | ---: |
| Owners (Class + ScriptStruct) — Judgment / Gears 3 | 1,719 / 1,675 |
| Judgment-only owners | 44 (36 classes + 8 structs) |
| Shared owners with a **differing member layout** | **45 of 1,675** |
| — of which classes / structs | 35 / **10** |
| Shared owners structurally identical | 1,630 (97.3%) |

> **RETRACTED:** an earlier version of this document claimed *"every difference is purely
> additive."* That was wrong — a bug in `scan_classes.py` only tested for reordering when an
> owner had **no** additions, so reordering went unchecked for nearly every differing owner.

**Change character across both scanned packages (corrected):**

| | Engine.u | GearGame.u | total |
| --- | ---: | ---: | ---: |
| Differing owners | 45 | 143 | **188** |
| Purely additive (append only) | 43 | 103 | **146** |
| **Reordered existing members** | 2 | 23 | **25** |
| With removals | 0 | 22 | **22** |
| Type changes | 0 | 0 | **0** |

Reordering is the expensive category: when Judgment moves an existing member, **every**
offset in that type shifts, so the native block must be regenerated in Judgment's order rather
than patched. `FPostProcessSettings` is one of the two reordered types in Engine.u — it moves
`DOF_BlurBloomKernelSize` from data-member position 8 to 3 and `Bloom_Tint` after
`Bloom_ScreenBlendThreshold`, on top of its 43 additions.

Removals are expensive for a different reason: native C++ that *references* a dropped member
must also be stubbed before it will compile.

The 36 Judgment-only classes match the independent `Manifest.txt` class-hierarchy diff exactly,
which cross-validates both methods.

## The immediate blocker

`Pylon` gains 5 properties, and `AISwitchablePylon` derives from it:

```
+ VoxelFilterTM, VoxelFilterBounds, NavMeshGenerator, bAllowRecastGenerator, bUseRecast
```

Judgment integrated **Recast** navmesh generation into UE3 pathfinding. The native `APylon`
compiled into the Gears 3 exe has 33 properties while Judgment's script declares 38, so property
offsets diverge and tearing down array/struct properties walks bad pointers — exactly the observed
crash (`StaticAllocateObject → AAISwitchablePylon::~AAISwitchablePylon → UArrayProperty::DestroyValue`).

## Blocker after Pylon: FPostProcessSettings

Adding the 5 `Pylon` members to native `APylon` in `Engine\Inc\EngineClasses.h` moved the
startup crash off `AAISwitchablePylon` and onto `UCameraAnimInst`, which holds a
`FPostProcessSettings` (`LastPPSettings`). That struct gains **43** members in Judgment
(82 → 125): adaptive-luminance controls, bloom dirt mask / per-layer weights / tints, a
`Bloom_Layers` array, and the matching `bOverride_*` flags. The `Bloom_Layers` array is the
`UArrayProperty::DestroyValue` at the top of the crash stack.

Judgment's `Engine.u` also imports a package named **`EnginePCF`** (People Can Fly) that does
not exist in the Gears 3 tree — logged as `Can't find file for package 'EnginePCF'`. That is a
separate missing dependency, not yet investigated.

## Delta clusters

The 35 layout changes group into recognisable feature work:

- **Audio** (largest): `AmbientSoundSimple` +`Enveloper`; `AudioComponent` +5 panning/omni-radius;
  `AudioDevice` +4 sound-mode; `ReverbVolume` +4 EQ; `SoundCue` +`LimitsGroup`; `SoundMode`
  +`EQPriority`; `SoundNodeAmbient`/`SoundNodeAttenuation` +`OmniRadius`; `SoundNodeMixer`,
  `SoundNodeRandom` +panning; `InterpTrackSound` +`FadeOutTime`.
- **Post-processing**: `UberPostProcessEffect` +11 (adaptive luminance, `PostProcessAAType`);
  `DOFAndBloomEffect` +11 (bloom dirt mask, per-layer bloom weights).
- **Navigation**: `Pylon` + Recast (above).
- **Performance**: `SkeletalMeshComponent` +5 tick optimisation; `Engine` +5 drop-rate;
  `ParticleModuleRequired` +7 near/far particle culling.
- **Misc**: fog textures, `LocalPlayer` alternate viewport, material expression `Group`,
  `StaticMeshActor.PreCombinedStaticMeshActors`, `WorldInfo.InteractiveMusic`.

Full machine-generated listing: `engine-delta.txt`.

## Tooling: generate native blocks, don't hand-edit them

`gen_native_block.py` emits a complete UE3 native C++ member block for any class or struct
directly from a script package — correct order, correct types, bitfields, pointer prefixes.

It rests on two facts, each established by validation rather than assumption:
* native declaration order is the **reverse** of package export order;
* a UProperty's type reference is the **last INT32** of its payload.

**Self-check before trusting it:** generate the block for a Gears 3 type and diff against the
real `EngineClasses.h`. On `FPostProcessSettings` it reproduces all **82/82** members exactly
(modulo C++'s optional `struct` keyword, which it emits deliberately so forward-referenced
structs like `FLUTBlender` still compile).

```powershell
python gen_native_block.py <manifest.json> <package.u> <OwnerName> --actors <Manifest.txt>
```

The `--actors` file supplies the Actor-derived class set, since UE3 prefixes those `A` and
everything else `U`.

This matters because 25 owners are **reordered**, and one of them is `GearPawn` at 775 -> 804
members. Hand-editing that is not realistic; regenerating it is one command.

## Never infer a member's C++ type from its name

`FPostProcessSettings` proves why: `Bloom_Tint` is **`FColor`** (4 bytes) while `RimShader_Color`
is **`FLinearColor`** (16 bytes). Same "Color" naming, 4x size difference. Guessing wrong silently
shifts every subsequent property offset, and the resulting crash looks like an unrelated bug.

`proptypes.py` reads the real type out of the package instead. A UProperty's type reference
(`StructProperty->Struct`, `ObjectProperty->PropertyClass`, `ArrayProperty->Inner`,
`ByteProperty->Enum`) is serialized **last** in its payload, so reading the trailing INT32 and
resolving it as a UE3 package index (>0 export, <0 import, 1-based) is robust without modelling
the variable-width fields before it.

Validated against Gears 3 ground truth — 11/11 exact vs the native header, including
`Bloom_Tint -> Color`, `RimShader_Color -> LinearColor`, `DOF_FocusType -> EFocusType`,
`ColorGradingLUT -> LUTBlender`, `DOF_BokehTexture -> Texture2D`.

Judgment's new `FPostProcessSettings` members resolve to:
`Bloom_DirtMaskTexture -> Texture2D`, `Bloom_DirtMaskColor -> Color`,
`Bloom_TintOuter -> Color`, `Bloom_TintInner -> Color` (all `FColor`, **not** `FLinearColor`).

```powershell
python proptypes.py judg-engine.json <Judgment>\Engine.u PostProcessSettings
```

## Reproduce

```powershell
judgment-package-probe.exe --manifest <Judgment>\Engine.u judg-engine.json
judgment-package-probe.exe --manifest <Gears3>\Engine.u   g3-engine.json
python scan_classes.py judg-engine.json g3-engine.json
python class_diff.py judg-engine.json g3-engine.json Pylon AudioComponent   # single classes
```

Both `.u` files are little-endian and uncompressed in the Xbox cook, so no byte-swapping or
decompression is needed to read them.

## Not yet covered

Only `Engine.u` has been scanned. `Core.u`, `GameFramework.u`, and especially `GearGame.u`
(272,379 exports) still need the same treatment before the full native surface is known.
