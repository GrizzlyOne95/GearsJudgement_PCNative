# Judgment content conversion surface (measured 2026-08-25)

Produced by `conversion_surface.py`. Scope is `GearGame\CookedXbox360` **only** — the earlier
1,315-candidate inventory in `PORTING-NOTES.md` scanned a wider root and its 27 little-endian
entries are script packages, not cooked content.

## Corpus

| Group | Count |
| --- | ---: |
| big-endian v845, LZX chunk-compressed | 1,277 |
| big-endian, fully-compressed container | 10 |
| big-endian v845, uncompressed | 1 |
| little-endian v845, uncompressed | 1 |
| **parsed / candidates** | **1,289 / 1,289** |

4.3 GB total. 437 `SP_*` packages across 14 persistent `_P` maps. Reading is a solved problem:
`--decompress-package` then `--manifest` succeeded on every package tried, and the probe
recovers names, imports, exports and object paths from all of them.

## Two level families, measured

| | SP_E4 (4 pkgs) | SP_00_Museum (4 pkgs) |
| --- | ---: | ---: |
| exports | 9,485 | 5,125 |
| serial payload | 52.7 MB | 30.5 MB |
| distinct classes | 170 | 197 |

`serial_size` excludes bulk data held in `.tfc` files, so every texture figure below is a
**lower bound**.

### Bytes concentrate in a handful of binary formats

| SP_E4 | SP_00_Museum |
| --- | --- |
| Texture2D 12.21 MB (581) | SoundNodeWave 13.58 MB (323) |
| StaticMesh 7.89 MB (250) | Texture2D 6.53 MB (94) |
| SoundNodeWave 7.80 MB (358) | SkeletalMesh 2.36 MB (5) |
| ShaderCache 7.14 MB (4) | NavigationMeshBase 1.56 MB (20) |
| LightMapTexture2D 5.40 MB (92) | ShaderCache 1.41 MB (4) |
| SkeletalMesh 2.97 MB (3) | StaticMesh 0.92 MB (33) |

Top six classes are ~86% of SP_E4's payload.

### Export *count* concentrates in ordinary tagged-property objects

SP_E4: StaticMeshComponent 2,723 · ShadowMap2D 722 · Package 704 · MaterialExpression\* ~950
combined · BrushComponent 263 · BlockingVolume 256 · SoundCue 218.
SP_00_Museum adds CoverLink 149 · SeqEvent_RemoteEvent 133 · SeqAct_\* several hundred ·
CylinderComponent 381.

These hold little data individually but are ~90% of all objects, and nothing loads without them.

## Worklist, in the order the measurements imply

1. **Generic tagged-property BE→LE translator — not started, highest leverage.**
   Property tags are name-table-indexed and self-describing, so one translator retires
   thousands of objects across every class at once: World, Level, Actor, Component, Sequence.
   This is the piece that turns "we can read a map" into "we can rewrite a map."
2. **Texture family** (Texture2D + LightMapTexture2D + ShadowMapTexture2D) — 37% of SP_E4 bytes.
   Partially solved: exact BC1 packed-tail recovery works for one geometry. Needs generalized
   tail placement across dimensions/formats and Xbox→PC format remapping (e.g. `PF_G8`).
3. **SoundNodeWave** — 15–45% of bytes depending on family. Already has a working multi-wave
   package rebuild with source-matched Ogg encoding. Mostly a matter of running it at scale.
4. **ShaderCache** — 7.14 MB in 4 objects. Xbox microcode; **not convertible**. It must be
   dropped and recompiled for PC. Judgment ships `Binaries\Win32\UE3ShaderCompileWorker.exe`,
   worth probing as an oracle.
5. **StaticMesh / SkeletalMesh** — 10.9 MB (SP_E4). Untouched and the hardest binary work:
   vertex/index buffer byte order plus platform vertex element formats.
6. **NavigationMeshBase** — 1.56 MB (SP_00_Museum). Recast-era, and connects to the `APylon`
   Judgment members already reconstructed for the direct loader.

## Recommended first whole-map fixture: `GearGame_P.xxx`

Ten exports, no meshes, no textures, a 29-byte ShaderCache:

```
Package · World · Level · WorldInfo · PlayerStart · CylinderComponent
Model · Polys · Sequence · ShaderCache
```

It is also the exact map the retail campaign travels to —
`GearGame_P?game=geargamecontent.GearGameAID?chapter=0?listen`. Converting it swaps the Gears 3
hub for the Judgment hub and makes campaign start genuinely Judgment-side. It exercises the
tagged-property translator (item 1) against a complete, real map while avoiding every unsolved
binary format.

## Progress: tagged-property reader (item 1) — reading half works

`tagged_props.py` walks the big-endian tag stream of any cooked export. Measured:

| package | exports parsed | tags recovered | zero-slack (high confidence) |
| --- | --- | ---: | ---: |
| `SP_E4_01.xxx` | 7,439 / 7,485 (99.4%) | 48,979 | 2,962 |
| `SP_E4_P.xxx` | 1,909 / 1,943 (98.3%) | 8,509 | 1,283 |
| `GearGame_P.xxx` | 5 / 10 tagged, 5 native | 9 | 5 |

Non-parsing exports are exactly the native-payload classes — `Model`, `Polys`, `World`,
`ShaderCache`, `StaticMesh`, `ShadowMap1D`, `FaceFXAsset`, `Class`. That is the expected result,
not a failure: their tag stream is followed by native data.

Two findings worth keeping:

1. **The FPropertyTag header is 24 bytes, not 20.** Name and Type are both full FNames
   (index + number). Dropping the Type's number field shifts Size and ArrayIndex by one INT and
   fails *quietly* — the first tag still decodes with a believable name and type, and only the
   sizes are wrong (`ObjectProperty sz=0 arr=4` instead of `sz=4 arr=0`).
2. **Each export has a native prologue before the tag stream and its length varies by class.**
   Observed lengths cluster at 4 (Package, Sequence, most SP_E4_P objects), 8 (Components),
   16, and 26 (Actors).

**Caveat before anything rewrites bytes:** `tagged_props.py` *discovers* the prologue by trying
lengths until one parses, so a minority of those parses may be coincidental. The zero-slack subset
is the trustworthy one. The prologue layouts must be confirmed against the Gears 3 source
(`UObject::Serialize` / `UComponent::Serialize` / `AActor`) before writing the LE emitter —
a guessed prologue silently corrupts every offset that follows it.

**Next:** confirm prologues against source, then write the LE emitter and convert `GearGame_P.xxx`
end to end as the first whole-map fixture.

## Progress: BE->LE emitter (`be2le.py`) — header, tables and property graph convert

Prologue model **confirmed from source**, not inferred. `FStateFrame` (`Core\Inc\UnStack.h:336`)
declares `DWORD ProbeMask` and `WORD LatentAction`, which makes the actor prologue come out at
exactly 26 bytes:

```
[component]   TemplateOwnerClass INT                                   4
              [+ CDO template] TemplateName FName                      8
[RF_HasStack] Node + StateNode + ProbeMask + LatentAction + StateStack 18
              [+ Node != 0] Offset INT                                 4
              NetIndex INT                                             4
```

Reading `ProbeMask` as a QWORD instead is the trap: it still "parses", but leaves StateStack
looking like -1 and shifts everything after it.

Byte-swapping preserves field widths, so output is the same length as input and every summary
offset stays valid — the conversion is a field-wise swap, not a re-serialization. And because the
direct loader reads v845 natively, **no version change is involved**: 845 stays 845.

### Validation

`GearGame_P.xxx` converted, then re-parsed with the independent C++ probe:

```
byte order: big -> little     version 845 -> 845     engine 9580 -> 9580
names 98 -> 98    imports 14 -> 14    exports 10 -> 10
names identical: True      import names identical: True
exports identical (class, name, offset, size, flags): True
object paths identical after normalising the filename-derived package name
```

### Scale

| package | size | fully converted | native tail | fully native | tags | scalars |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `GearGame_P` | 7.5 KB | 5 | 5 | 0 | 11 | 623 |
| `SP_E4_P` | 13.8 MB | 1,259 | 644 | 40 | 9,292 | 114,772 |
| `SP_E4_01` | 42.0 MB | 2,926 | 4,522 | 37 | 57,414 | 593,578 |

### What is still big-endian, and why — two buckets

1. **ArrayProperty values** (~2,700 × 8B, 1,775 × 20B, … in `SP_E4_01`). The element type is not
   recorded in the map; it lives in the script packages. `proptypes.py` already resolves a
   UProperty's target type from a package, so this is a dependency to wire up, not an unknown.
2. **Native tails** — per-class C++ serializers, each needing its own model:
   `StaticMeshComponent`, `BrushComponent`, `Texture2D`, `SoundNodeWave`, `SoundCue`,
   `RB_BodySetup`, and for the stub map `Level`, `Model`, `World`, `Polys`, `ShaderCache`.

**These outputs are not loadable yet** — arrays and native tails are still big-endian. What is
proven is the summary/name/import/export/prologue/tagged-property layer, end to end, on real
40 MB map packages, validated by an independent parser.

`TextureAllocations` (`Engine\Src\Texture2D.cpp:216`) is populated on real maps and had to be
modelled before any of them would convert; the tool fails closed on unmodelled summary structures
rather than writing a corrupt package.

## ArrayProperty resolution — item 1 property layer is COMPLETE

`array_types.py` resolves each ArrayProperty's element type from Judgment's script packages,
using the same trick as `proptypes.py`: a UProperty serialises its type reference **last**, so the
trailing INT32 of the payload is the reference. `ArrayProperty -> Inner UProperty -> class_name`,
and for struct elements one more hop to the named `UScriptStruct`.

Indexed from Judgment's `GearGame\Script` set (little-endian, uncompressed — no decompression
needed, unlike cooked content): **3,333 keys / 3,335 declarations** — 1,661 fixed-width elements,
1,257 struct elements, 0 unresolved imports.

Keys are collapsed to property name for lookup, because the tag stream records only the name and
the declaring class may be a superclass. Collisions are kept as **candidate lists**, not dropped:
`Materials` alone is 2,644 arrays in `SP_E4_01` and has four declarations (ObjectProperty plus
three different struct types). The converter tries candidates and validates each against
`count * element width`, rolling back on failure — so a wrong candidate is rejected, never written.

### Result: every property-level value now converts

| package | exports | fully converted | native tail | tags | array elements | scalars |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `GearGame_P` | 10 | 5 | 5 | 11 | 0 | 623 |
| `SP_E4_P` | 1,943 | 1,292 | 647 | 20,765 | 7,767 | 208,875 |
| `SP_E4_01` | 7,485 | 2,962 | 4,522 | 73,946 | 58,066 | 840,640 |

Zero non-native failures remain across all three. The only unswapped bytes are per-class native
payloads.

### Round-trip validation

Re-walking each converted package's property streams little-endian and comparing to the
big-endian original, tag for tag:

```
GearGame_P   10 / 10        identical prologue + tag stream
SP_E4_P    1,943 / 1,943    identical
SP_E4_01   7,485 / 7,485    identical
```

That check earned its keep — it caught two real bugs that the conversion reports called success:

1. **`Distribution*` classes derive from `UComponent` without saying so in the name.** A
   name-substring test gave them a 4-byte prologue instead of 8 and shifted every following tag.
   The converter now tries both variants and keeps whichever parses.
2. **`RF_ClassDefaultObject` is `0x200`, not `0x10000`** (`Core\Inc\UnObjBas.h:319`). With the
   wrong constant, template components silently got prologue 8 instead of 16. And the flag must be
   tested up the **outer chain**, not just on the object — `UComponent::PreSerialize` calls
   `IsTemplate()`, so a component merely *living inside* an archetype still carries `TemplateName`.

### Remaining: native tails only

Per-class C++ serializers, each needing its own model. By instance count in `SP_E4_01`:
`StaticMeshComponent`, `BrushComponent`, `Texture2D`, `SoundNodeWave`, `SoundCue`, `RB_BodySetup`,
plus `Level`, `Model`, `World`, `Polys`, `ShaderCache`. Converted packages are **still not
loadable** until those are done.

## Native tails: World, Polys, Model modelled

Three of the five classes in `GearGame_P` now convert, each validated by requiring the model to
land **exactly** on the payload end before the result is kept (`try_region` rolls back otherwise).

| class | source | shape | check |
| --- | --- | --- | --- |
| `UWorld` | `UnWorld.cpp:84` | PersistentLevel + PersistentFaceFXAnimSet + 4×FLevelViewportInfo(28) + SaveGameSummary + TArray | 4+4+112+4+4 = **128** ✓ |
| `UPolys` | `UnFPoly.cpp:1381` | DbNum, DbMax, ElementOwner | `[0, 0, 6]` = **12** ✓ |
| `UModel` | `UnModel.cpp:179` | Bounds(28) + bulk arrays + zones + refs + LightingGuid + LightmassSettings | **180** ✓ |

`FLevelViewportInfo` being FVector+FRotator+FLOAT = 28 was predicted from the byte arithmetic
before the header confirmed it, which is a good sign the World model is right rather than merely
fitting. The `Levels`/`CurrentLevel`/`URL`/`NetDriver` block in `UWorld::Serialize` is guarded by
`!IsLoading && !IsSaving`, so it never appears on disk.

**One honest caveat:** in `UModel`, the source says `Ar << Surfs`, but the data occupies exactly
two INTs and the rest of the 45-INT walk only lands on 180 with that shape. That field is derived
from the bytes, not from the source, and must be revisited before trusting it on a map with real
BSP geometry.

`bulk()` implements `TArray::BulkSerialize` (INT ElementSize, INT Count, then the data) and
**refuses** a non-empty array when it has no element model, rather than swapping opaque bytes.
That is why real maps convert only 2-3 native tails: their Models carry actual BSP, so
`FBspNode`, `FVert` and `FBspSurf` element models are needed next.

### `GearGame_P` status: 8 of 10 exports fully converted (historical)

Remaining:

- **`ULevel` (270B)** — the real blocker for a first loadable map. `ULevel::Serialize`
  (`UnLevel.cpp:320`) carries `TextureToInstancesMap` and `DynamicTextureInstances` (TMaps), an
  APEX size-prefixed blob, several `CachedPhys*` bulk arrays and TMaps, the nav/cover/pylon list
  refs, cross-level actor arrays and `FPrecomputedLightVolume`. It needs its own pass.
- **`ShaderCache` (17B)** — was initially treated as out of scope. The later byte-exact audit
  below proves this particular fixture contains only an empty cache header, not microcode.

## `ULevel` tail: modelled and converting

**Correction.** An earlier version of this section reported "two unexplained INTs" between
`Actors` and `URL` and proposed disassembling the Judgment XEX to explain them. There is no gap.
`Actors` is a `TTransArray`, and `TTransArray::operator<<` (`Core\Inc\Array.h:2116`) serialises
**Owner first, then the array**:

```cpp
Ar << A.Owner;
Ar << (Super&)A;   // TArray: count, then elements
```

Parsing it count-first consumed the Owner as the count and lost one element, which pushed two
phantom fields in front of the URL. Read correctly, `GearGame_P` decodes as:

```
Owner       = PersistentLevel          <- the Level owns its own Actors array
ArrayNum    = 3
Actors[0]   = WorldInfo_3              <- UE3 convention: WorldInfo first
Actors[1]   = NULL                     <-   then the default brush, absent in this stub
Actors[2]   = PlayerStart_0
URL         = unreal :// "" / "GearStart" : 7777, Valid 1
Model       = Model_4
...
NavListStart/End = PlayerStart_0       <- a NavigationPoint, exactly as expected
```

The PDB was still worth pulling: `llvm-pdbutil pretty --include-types='^ULevelBase$'` on
`GearGame-Xbox360-Release.pdb` (166 MB, `HasPrivateSymbols`) confirms Judgment's `ULevelBase` is
`UObject`(60) + `TTransArray<AActor*> Actors`(16) + `FURL URL`(68) = 144 with **no added members**,
which ruled out the "Judgment engine delta" hypothesis and pointed at the serialiser instead.
That PDB is now a proven, queryable oracle for any future layout question.

Note `FURL`'s **serialisation order differs from its memory order** — the PDB shows `Port` between
`Host` and `Map`, while `operator<<` writes Protocol, Host, Map, Portal, Op, Port, Valid.

The remaining 93 bytes are all zero and the model accounts for them exactly: four cross-level
arrays (16) + `FPrecomputedLightVolume` (4, uninitialised) + `FPrecomputedVisibilityHandler` (28)
+ `FPrecomputedVolumeDistanceField` (45) = **93**.

### `GearGame_P`: 9 of 10 exports fully converted (superseded)

Round-trip 10/10, and the converted little-endian package re-reads correctly: Owner
`PersistentLevel`, Actors `[WorldInfo_3, NULL, PlayerStart_0]`, `URL.Protocol` "unreal",
`NavListStart` `PlayerStart_0`.

At this point the final **`ShaderCache` (17B)** tail was still believed to contain Xbox shader
microcode. The byte-exact source audit and native boot below supersede that interpretation.

Populated TMaps, a populated `FPrecomputedLightVolume`, non-empty visibility buckets and
non-empty bulk arrays all **fail closed** rather than guessing — which is what real maps will hit.

## `GearGame_P`: 10 of 10 exports convert and the Judgment map boots natively

The 29-byte `SeekFreeShaderCache` export is **not** a microcode payload. After the four-byte
`NetIndex` and eight-byte `None` property terminator, its 17-byte native tail is exactly:

```
ShaderCachePriority INT = 10
Platform BYTE = SP_XBOXD3D (2)
CompressedShaderCode TMap count INT = 0
NumShaders INT = 0
NumMaterialShaderMaps INT = 0
```

This follows `UShaderCache::Load` / `FShaderCache::Load` at package version 845. The converter now
accepts only that exact empty-Xbox shape, swaps the four integers, and retargets the platform byte
to this port's active `SP_PCD3D_SM3` RHI (0). Any populated cache fails closed and still requires
PC shader rebuilding.

The first native load exposed one more header-only console/PC delta in the otherwise-empty Model:
`FVert` is 16 bytes in console-cooked data and 24 bytes on PC because PC adds
`BackfaceShadowTexCoord`. `TArray::BulkSerialize` validates its element-size word even for a zero
count, so the converter retargets 16 -> 24 only when the array is empty. A populated FVert array
remains unsupported because it would require widening each element and rebuilding package offsets.

### Verified result (2026-08-25)

- output remains 7,575 bytes, v845, with all 98 names, 14 imports and 10 exports unchanged;
- independent C++ manifest validation reports exact import/export table ends and zero invalid refs;
- converter reports **10/10 exports fully converted**, five of them native tails, zero unsupported;
- fail-closed mutation test rejects a non-empty ShaderCache count without changing its bytes;
- the converted package staged as `GearGame/Content/Maps/Judgment_GearGame_P.gear` passes the
  direct v845 loader and reaches `map-loaded`, `first-render`, `world-first-tick`, spawns
  `GearPC_AID`, and possesses `GearPawn_COGBairdJack`.

Boot evidence: `C:\Games\_judgment-scratch\Judgment_GearGame_P.shaderfixed-boot3.log`.
This is the first end-to-end native boot of the converted Judgment map; it does not use the older
Gears 3 `GearGame_P.gear` control fixture.
## Next real campaign fixture: SP_00_Museum_Base_Exit_S

The next fixture is a small actual Judgment campaign streaming level rather than another empty
persistent shell:

- retail input: 32,768-byte LZX package;
- decompressed package: 79,775 bytes, 217 names, 34 imports and 58 exports;
- exports include 16 CoverLinks, 17 CylinderComponents, Level, Model, World, Polys, Sequence,
  ShaderCache, SoundCue and gameplay sequence objects.

The v845 script manifests were regenerated for all 13 script packages and produced an
ArrayProperty index with 3,571 owner/property keys and 3,573 declarations. With that index the
converter now finishes this fixture deterministically and reports:

- 41 exports fully converted;
- 16 partial CoverLink exports whose `Slots` arrays contain binary-serialized immutable
  `CoverSlot` structs;
- one unmodelled populated Level tail (2,932 bytes);
- no remaining SoundCue tail: its stripped four-byte empty `EditorData` TMap is now modelled.

A bogus speculative ArrayProperty candidate originally produced an enormous loop count. The
shared TArray walker and binary-struct candidate walker now apply file/region-derived count bounds,
turning that case into an immediate fail-closed result. Export statistics also distinguish partial
property conversion from fully converted exports, so unsupported `CoverSlot` data can no longer be
reported as complete.

The next implementation boundary is therefore exact and local: model `FCoverSlot`'s
`STRUCT_ImmutableWhenCooked` binary serialization, then decode the populated ULevel tail. A
populated width-changing structure must use relocation-capable rewriting rather than same-length
swapping.

## Correctness and reproducibility audit (2026-08-26)

An independent four-lane Ox Alpha audit found two places where a real Level could have been
reported as converted while retaining invalid bytes. Both now have explicit fail-closed rules and
regression tests:

- APEX cached data is serialized as a size plus raw bytes. `ULevel::Serialize` only hands the
  buffer to APEX when `Size > 16`; the observed thin and Museum levels both carry exactly the
  ignored 16-byte sentinel. The converter swaps its length and preserves the byte-oriented
  sentinel, but rejects any payload larger than 16 until that platform-native format is modelled.
- `FPrecomputedVolumeDistanceField::Data` is `TArray<FColor>`. Its four channels are serialized as
  bytes, so only the array count is endian-swapped; reversing each four-byte color would change
  RGBA channel order.

The verified thin-map output remains byte-for-byte identical after these guards:
`0849E7EA6E0DD73DDCECE8DB787A4B5B591C75E9EA1BF036ECA19389590D5353`.
`verify-thin-map.ps1` now pins the retail input, array-schema index, converted output, and staged
map hashes. `scripts/build-judgment-loader.ps1` makes the previously temporary loader build recipe
reproducible.

The first full-package measurements also establish the next work order:

- `SP_E2_P`: 1,077/1,433 exports fully converted; remaining serial mass is primarily 254
  `SoundNodeWave`, three `SkeletalMesh`, 24 `Texture2D`, and one populated `ShaderCache`.
- `GearStartTransition`: 147/193 exports fully converted, but still depends on textures, three
  large audio waves, populated shader data, Model/Level data, and one native light component.
- retail `GearStart`: 622/1,676 exports fully converted and is dominated by 955 `Texture2D`
  exports (86 MB), plus 30 `SwfMovie` and 29 `SoundNodeWave` exports.

Therefore the authentic frontend is not a thin next fixture: package-wide texture/audio
conversion and relocation are the shortest path shared by both campaign and menu content.

### `SP_E2_P` structural conversion increment

`USoundNodeWave::Serialize` stores four `FByteBulkData` slots (raw, PC, Xbox 360, PS3). The
converter now rewrites their flags/count/size/absolute-offset headers and preserves inline codec
bytes as opaque data. All 254 Xbox XMA payloads remain in the Xbox slot; this is deliberately a
structural-load milestone, not audio transcoding. Runtime testing of this intermediate package
must use `-nosound`, which prevents PC audio precaching. Invalid inline offsets fail closed.

Several source-proven exact four-byte native tails are also covered: empty `PreCachedPhysData` on
`RB_BodySetup`, empty `CachedPhysBrushData`, empty `StaticMeshComponent.LODData`, empty
`SeqAct_Interp.SavedActorTransforms`, and `ObjectRedirector.DestinationObject`. Primitive script
arrays now handle strings, scalar/object/name values, byte/bool values, and enum-backed byte values
(which UE3 serializes as FNames).

Measured result: **1,378/1,433 exports fully converted**, zero partial property exports, 51
unmodelled native tails, and four fully native `Class` payloads. The independent C++ manifest pass
reports exact import/export table ends, zero invalid references, and **254/254 valid
SoundNodeWave tagged/bulk-data payloads**. The remaining campaign blockers are now concentrated in
24 textures and a small set of Model/Polys/Level, material, physics, FaceFX, mesh, and populated
shader-cache serializers.
