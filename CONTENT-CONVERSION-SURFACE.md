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

## Session XIII: the CoverSlot format discovery (2026-08-25, evening)

Attacking `SP_00_Museum_Base_Exit_S`'s 16 partial CoverLink exports produced a finding that
changes the converter's contract.

### The runtime expects TAGGED CoverSlots, not binary

`UStructProperty::SerializeItem` (UnProp.cpp:4184) picks binary serialization only when the
*UScriptStruct object* carries `STRUCT_ImmutableWhenCooked`. That flag is applied by cookers,
never by runtime class construction - so **our loader's FCoverSlot always takes
`SerializeTaggedProperties`**. Judgment's console cook emitted BINARY SerializeBin form (the
flag was set on the Xbox). The two formats are incompatible; converting Judgment cover data
means EXPANDING binary into tagged streams - a format change with growing payloads, hence the
relocation-capable rewriter this file already called for.

Measured template (Jacinto 1.1.1 `SP_Badlands_02.gear`, LE v828, per slot element):
`SlotOwner:ObjectProperty(4)`, `ForceCoverType/CoverType/LocationDescription:ByteProperty
size=8 inner=<enum>` (enum-as-FName values), `LocationOffset/Rotator:StructProperty inner=
Vector/Rotator`, `Actions:ArrayProperty (count + 8B enum-FName elements)`,
`FireLinks:ArrayProperty (count + tagged FireLink elements {Interactions:Array<raw byte>,
PackedProperties:Int, bFallbackLink:Bool, bDynamicIndexInited:Bool, None})`,
ExposedCover/TurnTarget/SlipRefs/OverlapClaimsList, then ALL 21 non-transient bools as
explicit BoolProperty tags (size=0 + 1 value byte). No RejectedFireLinks, no SlotValidAfterTime,
no CachedPoly tag anywhere. Full dump in session log; emitter scaffolded in
`coverslot_expand.py` (binary parser + tag writer + name-table append + offset relocation).

### Serialization rules proven from source (Gears 3 Sept 2011 tree)

- `UByteProperty::SerializeItem` (UnProp.cpp:593): enum-typed bytes serialize as **8-byte
  FName** on load/save - confirmed by ECoverType/ECoverAction names sitting in the cooked bytes.
- `UBoolProperty::SerializeItem` (UnProp.cpp:1385): each script bool writes **one byte**
  (`Ar << B` then bit-mask apply) - the tail 0/1 runs.
- `ShouldSerializeValue` (UnType.h:356): CPF_Transient skipped on persistent archives ->
  SlotValidAfterTime, RejectedFireLinks, bDestructible/bSelected/bFailedToFindSurface absent.
- PDB oracle extended: `llvm-pdbutil pretty --all --include-types=^FCoverSlot$` dumps full
  member layouts from GearGame-Xbox360-Release.pdb; FCoverSlot/FFireLink/FCoverInfo match the
  Gears 3 headers exactly (no Judgment delta).

### Binary-side layout proven (Judgment BE)

Element head verified semantically across all 16 exports: owner INT, three enum-FNames
(CT_None/CT_Standing/CoverDesc_None - real per-slot values), FVector, FRotator with plausible
coordinates/yaws; Actions = count + enum-FName elements (CA_LeanLeft/CA_PopUp...); FireLinks =
count + sum(icount + packed INT + 2 bool BYTES) - stride m+10 PROVEN by 63 sequentially
increasing packed CoverRefIdx values (39..51...) inside SP_Badlands-grade link tables;
transient skips confirmed by clean field landings.

### OPEN: ~190 B/slot residual

After OverlapClaimsList + 21 bools, every element carries an additional variable-length block
(single-slot bodies: 188/176 B) that reflection-derived fields do not explain, and no width/
presence parameterization fits all 45 slots. It is INSIDE the Slots tag value, scales with
content not count, and begins with high-entropy bytes (GUID-like). Next step: runtime trace -
break on `UStruct::SerializeBin`/`UByteProperty::SerializeItem` under CDB while the v60 loader
parses this exact package and record the property walk directly (rundt.ps1 pattern works for
this; dt-at-breakpoint is the established oracle).

Also noted: GitHub PRs #3/#5 (Jules) contain synthetic ShaderCache/FVert retarget tests and a
staged campaign plan - consistent with this architecture but no CoverSlot content.

## Session XIV: SP_E2_P reaches 1,402/1,433 exports (2026-08-26)

Ox's independent audit found and closed two silent-corruption risks: populated APEX cache data
over 16 bytes now fails closed, while the exact 16-byte sentinel that UE3 explicitly ignores is
preserved; `FPrecomputedVolumeDistanceField::Data` now preserves each four-channel `FColor`
instead of reversing its RGBA bytes. The thin-map output remains byte-identical to the native-
booted hash `0849E7EA...D5353`.

The first full campaign-package measurement selected `SP_E2_P` (1,433 exports). A source-backed
`SoundNodeWave` handler converts all four `FByteBulkData` headers while preserving XMA codec bytes
in the Xbox slot. This intermediate is structurally loadable only under `-nosound`; it does not
claim PC audio playback. Exact four-byte container/reference tails and primitive/enum/string
script arrays were also added.

After the audio/array pass the package reached **1,378 fully converted, zero partial, 51
unmodelled native tails, and four native Class payloads**. Independent C++ validation reports
exact tables, zero invalid refs, and 254/254 valid SoundNodeWave payloads.

`UTexture2D::Serialize` is now covered structurally: SourceArt and mip `FByteBulkData` metadata,
mip counts/dimensions, the texture-file-cache GUID, and cached PVRTC mip framing are converted
while tiled Xbox pixel bytes stay opaque. This is a `-nullrhi` load milestone, not rendered PC
textures; invalid framing fails closed.

Current result: **1,402 fully converted, zero partial, 27 unmodelled native tails, four native
Class payloads**. Independent validation reports exact tables, zero invalid refs, 24/24 valid
Texture2D frames, and 254/254 valid SoundNodeWave frames.

The uniquely staged `Judgment_SP_E2_P.gear` reached the real v845 file reader and map loader under
`-nosound -nullrhi`, then stopped exactly at the first unconverted native payload:
`Class GearEditor.UpdateGameplayParticleSystems` in `UClass::Serialize`, with a bogus import index.
This makes the `UField`/`UStruct`/`UState`/`UClass` persistent layout the next ordered blocker.
Evidence: `C:\Games\_judgment-scratch\Judgment_SP_E2_P.structural-v1.log`.

## Session XV: UClass + FPrecomputedLightVolume close the Level blocker (2026-08-26)

`tail_class` (`UField`/`UStruct`/`UState`/`UClass`) was missing and left four Class payloads
big-endian; the loader's `UClass::Serialize` then read a bogus import index and crashed
(`IMPORT_FAIL index=-1627389953`). A source-backed handler now converts the full chain:
`Next`/`SuperStruct`/`Children` → `ScriptBytecodeSize`/`ScriptStorageSize` (zero for these
four) → `ProbeMask`/`LabelTableOffset`/`StateFlags` → `FuncMap` → `ClassFlags`/`ClassWithin`/`ConfigName`
→ `ComponentNameToDefaultObjectMap` → `Interfaces` → `DLLBindName` → `ClassDefaultObject`.
The four classes (`GearPawn_CCarmine`, `GearPawn_COGGus`, `GearAI_Barrick`, `GearPawn_COGBarrick`)
now validate and the bogus-index crash is gone.

With that fixed the next blocker surfaced in `ULevel::Serialize`: the persistent Level
`TheWorld.PersistentLevel` carries a populated `FPrecomputedLightVolume` (`bInitialized=1`,
547 samples). The previous `tail_level` deliberately failed closed on any populated volume.
The handler now swaps the volume correctly: `FBox Bounds` (6×FLOAT + BYTE) → `FLOAT SampleSpacing`
→ `TArray<FVolumeLightingSample>` (33 B each: `FVector` + `FLOAT Radius` + 4×BYTE thetas/phis +
3×`FColor` + BYTE `bShadowed`). `FVolumeLightingSample` layout confirmed against
`PrecomputedLightVolume.h:12` / `.cpp:58,131` and the 547-sample payload in `SP_E2_P`
(18,088 B) lands exactly on the visibility-handler boundary.

Re-running `be2le.py` on the decompressed `SP_E2_P.xxx.unc` with `array-types-v845.json`:

```
wrote SP_E2_P.lvfix.le.xxx (11814162 bytes)
  exports fully converted: 1407 (incl. 477 native tails)   partial: 0
  unmodelled tail: 26   fully native: 0
  tags swapped: 14945   array elements: 3635   scalars swapped: 155710
```

(`1402 → 1407` = the four `Class` payloads plus the `Level` light volume).
`test_be2le.py` still passes (21 tests). Independent C++ probe (`--manifest`) reports:

```
names_end 60971, imports_end 69119, exports_end 166663, invalid refs 0
texture2d_payloads 24/24 valid, sound_node_wave 254/254 valid
```

Artifacts: `C:\Games\_judgment-scratch\e2-surface\SP_E2_P.lvfix.le.xxx` and
`SP_E2_P.lvfix.manifest.json` (SHA256 `48B1CAF5...60BD7B`). The staged
`GearGame\Content\Maps\Judgment_SP_E2_P.gear` was updated to this output.

Headless boot (`-nosound -nullrhi -unattended`) is currently gated by the host's
desktop resolution (540×1156 reported by `WinForms.Screen`; the engine logs
`The current resolution is too low to run this game` and exits 0 before `LoadMap`).
This is environmental — the same `v59` binary booted the same package at 07:07 on the same
host. A debugger shim (`resfix.cmds`: `bp user32!GetSystemMetrics ...`) is staged for the
next run, or the session can be re-run from a larger desktop. The next ordered native-tail
blockers after `Level` remain 26:
`Polys` (3×1092 B), `MaterialInstanceConstant` (8 variants), `Model` (1600/1588 B),
`PhysicsAssetInstance`, `FaceFXAnimSet/Asset`, `Material`, `ShaderCache` (611,516 B),
`SkeletalMesh` (3× ~1 MB). Evidence for the Level fix:
`Judgment_SP_E2_P.structural-v2.log` (pre-fix UClass crash) and
`Judgment_SP_E2_P.structural-v3*.log` (current resolution gate).

## Session XVI: Resolution gate proven environmental, SP_E2_P reaches LoadMap then UClass huge-Length (2026-09-05)

### Resolution gate — PROVEN

**Root cause.** The early `The current resolution is too low` exit is a Win32
`GetSystemMetrics` check performed before `Shader platform (RHI)` init. The
engine queries `SM_CXSCREEN (0)` and `SM_CYSCREEN (1)` *and* the virtual-screen
metrics `SM_CXVIRTUALSCREEN (78)` / `SM_CYVIRTUALSCREEN (79)` (plus
`SM_CXVIRTUALSCREEN` etc. via `WinForms.Screen`). At 10:07 on 2026-08-26 the host
reported `540×1156` (primary) and `540×1156` virtual; at 07:07 and again on
2026-09-05 it reported `2560×1440` primary / `4444×3120` virtual. The check is
`if (Width < 1280 || Height < 720)`-class; `540×1156` fails, `2560×1440` passes.

Evidence: `cdb-metrics.log:1` (`SM_CXSCREEN 540 -> forced 1920`,
`SM_CYSCREEN 1156 -> 1080`, `SM_CXVIRTUALSCREEN 540`/`1156` left unforced and still
failed), `cdb-metrics4.log:1` (`GetOutermost+0x38906` caller for `SM_CXSCREEN` at
`0x01f1ded2` / `0x006a5016`), and the current host's
`[System.Windows.Forms.Screen]::AllScreens` (`2560×1440` primary, `4444×3120`
virtual) which makes the gate pass without any shim.

**Why `resfix.cmds` failed.** Three independent bugs, any one fatal:

1. `bp user32!GetSystemMetrics "r eax=1920; gc"` sets `EAX` *at function entry*;
   the callee then overwrites `EAX` with the real metric, so the forced value is
   lost. A correct shim must set `EAX` *after* `gu` (at the return site) or
   emulate the `ret 4` (`r eip=poi(@esp); r esp=@esp+4; r eax=...`).

2. The original `resfix.cmds:1` only handled `0`/`1` (`CXSCREEN`/`CYSCREEN`);
   the engine also checks `78`/`79` (`CXVIRTUALSCREEN`/`CYVIRTUALSCREEN`) and
   would still see `540×1156` and fail.

3. Handlers that used `gu` inside the breakpoint (`resfix-diag.cmds:1`,
   `resfix3.cmds:1`) triggered `Some commands were skipped because previous
   commands caused target execution inside an event handler.` and left the
   virtual-screen metrics unforced (`cdb-metrics.log:1` `78 -> keep orig 540`).

**Working launch.** No shim is needed on the current desktop. The successful
command is the same that previously failed, without `-ResX`/`-ResY` or a debugger:

```
Judgment_SP_E2_P?game=geargamecontent.GearGameAID?listen -user -JUDGMENTPKGVER=845 -JUDGNATIVEBINDOK -JUDGLIFE -forcelogflush -unattended -nopause -nosound -nullrhi -ABSLOG=C:\Games\_judgment-scratch\test_direct_res2.log
```

`Init: Base directory: ...\Binaries\Win32\` → `Object subsystem initialized` →
`Shader platform (RHI): PC-D3D-SM3` → `JUDGMENT_LOADER_READER` for
`Judgment_SP_E2_P.gear` at `0023.42` (previously blocked at `0019.82`). Evidence:
`test_direct_res.log:1`, `test_direct_res2.log:1`, and the host's current
`GetSystemMetrics` (`SM_0=2560 SM_1=1440 SM_78=4444 SM_79=3120`).

### Runtime advancement — LoadMap reached, next failure captured

* **Previous last-known point:** `0019.82` `The current resolution is too low`
  (before `Shader platform`), `structural-v3.log:1`.

* **New last-known point (lvfix, 1407):** `0023.42`
  `JUDGMENT_LOADER_READER linker=... file=..\..\GearGame\Content\Maps\Judgment_SP_E2_P.gear size=11814162`
  → `LoadMap: Judgment_SP_E2_P?Name=Player?Team=255?...` at `0024.77`
  (`test_lvfix2.log:1`, `cdb_destroy2.log:1`).

* **First new failure (both lvfix `48b1` and generic `3aad`):**

```
[0024.84] Critical: ReadFile failed: Count=11641106 Length=37092755 for ...\Judgment_SP_E2_P.gear
FArchiveFileReaderWindows::Serialize @0x57b439
UStruct::Serialize @0x60f80c
UState::Serialize @0x60fc73
UClass::Serialize @0x60fd93
ULinkerLoad::Preload @0x62b34a
```

`Count` vs `Length` are Unreal's `Count` (bytes obtained) vs `Length`
(requested) (`FFileManagerWindows.cpp:1`). `file_size 11,814,162 - Count
11,641,106 = 173,056` is the `FArchive` position before the bad read, so the
request is `file_pos 173056 length 37092755`. `Length 37,092,755` is a
*corrupted bulk-read length, likely derived from an endian-wrong
size/count* (`FString` byte count, `TArray count*element_size`, `Script`/
`ScriptStorage` length, etc.) — not proven to be a bare `TArray` count until
the caller disassembly is seen.

**Two concepts must not be conflated:**

* *Physical archive position* `173056` happens to lie inside
  `Default__GearPawn_CCarmine` `172553:622` `rel 503` (1 byte inside its
  `CylinderComponent ObjectProperty` value at `173055:19` `be2le` CDO dump
  `tag 13` at `173031: rel 478`), so a naïve file_pos→export map says
  `Default__GearPawn_CCarmine`.

* *Active object being serialized* — the stack is `UClass::Serialize`,
  not `GearPawn::Serialize`. That strongly suggests the active `UObject`
  is still the `UClass` `GearPawn_CCarmine` `172395:158` (whose legitimate
  range ends at `172553`), which overran by `503` bytes (`172553→173056`)
  before the `37 MB` `Serialize(...,37092755)` call. `173056` would then be
  *physically* inside the following CDO but *logically* still the `UClass`'s
  walk.

`ScriptBytecodeSize 0 ScriptStorageSize 0` for that `UClass` (the four tiny
`GearPawn_CCarmine`/`GearPawn_COGGus`/`GearAI_Barrick`/`GearPawn_COGBarrick`
`be2le` dump at `172411:0 172415:0`) means this overrun cannot be explained by
a `SerializeExpr` stream for this particular class — whatever needs
`SerializeExpr` is elsewhere — so the `7×12` class-tail region is suspect but
must be proven semantically, not just by byte width.

`be2le.py:940` `tail_class` does land exactly on `end` for those four
(`ProbeMask 0x3002C9E9` `StateFlags 2` `FuncMap 0` `ComponentMap 7×12=84` →
`172553` `be2le` debug `exp 0` at `172419`), yet the runtime still overruns.
`try_region` landing on `end` is necessary but not sufficient; the `7×12`
block is currently typed as `TMap<FName,UObject*>` (`FName 8+Object 4`) from
its width alone. `UClass` does contain an `Interfaces` array, and a modern
`FImplementedInterface` is three fields (`Epic Games Developers:2`), not two,
so a 12-byte repetition is suspicious and must be validated by *semantic*
validity (`FName index < NameCount`, `FName number` plausible,
`FPackageIndex` resolves or zero, counts sane) and by the runtime's actual
consumption sequence, not just by fitting `84` bytes.

A generic 4 B fallback for the 26 was tried (`1433` `3aad`) and fails
identically at `173056`, so the 37 MB is inside a *modelled* tail
(`UClass`/`Level`/`World`/`Model`/`Polys`/`Texture2D`/`SoundNodeWave`), not
the 26. Whitelist stays `set()` to preserve `1407/26`.

Evidence: `test_direct_res2.log:1` and `test_lvfix2.log:1` (same
`Count`/`Length` at `0024.84`), `structural-v2.log:1` (`IMPORT_FAIL
-1627389953` at `tell 172407` for `SuperStruct -98` when `tail_class`
disabled), `be2le` CDO dump `tag 13` at `173031` and `file_pos 173056`
arithmetic `11814162-11641106=173056` (`SP_E2_P.xxx.json:1` `total serial
11641767`).

### Validation

* `test_be2le.py:1` **21/21 OK** on the restored `48b1` staged file and on the
  `be2le.py` that now keeps the whitelist empty (the `1433` variant is retained
  only as `e2-surface/SP_E2_P.generic4.le.xxx` for comparison).

* Probe `--manifest` on the staged `Judgment_SP_E2_P.gear` (`48b1caf5...`,
  `11814162 B`): `names_end 60971 imports_end 69119 exports_end 166663
  invalid refs 0 texture2d 24/24 sound 254/254` (`SP_E2_P.lvfix.manifest.json:1`).

* Runtime: `test_direct_res2.log:1` now shows `LoadMap` for `Judgment_SP_E2_P`
  (previously blocked at `0019`), then the single `ReadFile` failure above.
  No CoverSlot is involved — `SP_E2_P`'s `CoverLink` `Slots` are not present;
  the `~190 B/slot` residual (`coverslot_expand.py:1`) remains out of scope as
  required.

### Files changed (this session)

* `C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\GearGame\Content\Maps\Judgment_SP_E2_P.gear`
  — staged as `SP_E2_P.lvfix.le.xxx` (`48b1caf5f617`, `11814162 B`, `1407`
  converted) to keep the `1407/26` baseline; the `3aad`/`generic4` variant is
  retained only in `e2-surface` for comparison.

* `C:\Games\NostalgiaBundle\projects\judgment-native\be2le.py:1126` — whitelist
  forced to `set()` with a comment explaining the `37 MB` regression; the file
  otherwise remains the `21/21` version.

* `C:\Games\_judgment-scratch\test_direct_res*.log`,
  `test_lvfix*.log`, `cdb_*.log`, `dump_*.py` — new scratch traces and
  `be2le` debug dumps (not tracked).

No `PORTING-NOTES.md` broad refactor was performed; the change is limited to
the `UClass`/`Level` boundary.

### Next recommended step — ONE action (DO NOT modify `be2le.py` before this is known)

**Measurement gate:** break on the `37,092,755`-byte `Serialize` *and*
identify which `UObject`/export `ULinkerLoad::Preload` is actually serializing.
`@esp+4` at `FArchiveFileReaderWindows::Serialize` is `Serialize`'s own
`V/Length`, not `Preload`'s `UObject*` — the stack is already
`Preload→UClass→UState→UStruct→FArchive` deep.

**Instrument both boundaries (staged `lvfix` `48b1`):**

*Preload ENTER* `ULinkerLoad::Preload @0x0062b34a` (`this=ECX`,
`UObject*=[ESP+4]`):

```
bp 0x0062b34a "r $t0=poi(@esp+4); .echo Preload UObject=; ? @$t0; r $r0=@$t0; gc"
; or for a diagnostic run: "k 2; gc" and correlate via engine Log naming
```

Stash `UObject*` in pseudo-register `$r0` (or `$t0`) so the later giant-read
breakpoint knows which `Preload` is outstanding. Even a minimal
`Preload UObject=xxxxxxxx` log plus existing `JUDGLOAD` naming is sufficient.

*Serialize* `FArchiveFileReaderWindows::Serialize @0x0057b439`
(`this=ECX`, `V=[ESP+4]`, `Length=[ESP+8]`, `Pos @this+28`, `Size @this+24`,
`Filename FString @this+8`):

```
bp 0x0057b439 "j (dwo(@esp+8)==37092755) '.echo BAD BULK; ? dwo(@ecx+28); ? dwo(@esp+8); ? poi(@esp); k 6; gc'; 'gc'"
; capture: ECX, poi(@esp) caller, poi(@esp+4) buffer, poi(@esp+8) Length,
; archive Pos, kv, plus both positions if exposed (Pos before/after)
```

`Pos` before read is definitive; `file_size - short_read_count` (`11814162-
11641106=173056`) is strong evidence but `Pos` is proof.

**One valuable observation if Outcome A happens** (`GearPawn_CCarmine`
`172395:158` `Pos=173056`):

Do not jump to the `7×12` block. First find **where runtime crosses
`172553`** (expected class end):

```
expected class end = 172553
runtime: 172395 ... 1724xx ... 172537 ... 172553 ← what field does
UClass::Serialize think comes next? 172557 ... 173056
```

Watch archive-position transitions past `172553` and disassemble in
`UClass::Serialize` to map the instruction to the field. That distinguishes:

```
converter: ComponentMap count=7 7×12 end
runtime:   <earlier collection> → another count/name/map/interface field → continues beyond 172553
```
vs
```
runtime interprets one 12-byte record differently → internal count corrupt → escapes boundary
```

**Decision tree:**

```
37,092,755-byte Serialize
        ↓
identify outstanding Preload UObject
        │
        ├── GearPawn_CCarmine : UClass 172395:158 cursor 173056
        │      → find FIRST runtime archive operation crossing 172553
        │        → map that instruction to UClass::Serialize field
        │        → correct only that grammar
        │
        └── Default__GearPawn_CCarmine 172553:622 cursor 173056 (+1 inside CylinderComponent value)
               → trace property parser near 173031–173059
               → find first runtime/converter cursor divergence
```

Exclusions remain: **NO 26-tail work, NO generic_whitelist, NO SerializeExpr,
NO CoverSlot, NO speculative CDO repair unless Outcome B is proven.** Session
XVI is now a clean measurement gate; the next debugger result tells which
serializer grammar actually needs work (current lean: **Outcome A** overrun).

## Session XVII: 37 MB Serialize owner — measurement gate (2026-09-05)

**Objective (per Work Order):** prove which `UObject`/export is being
serialized when `FArchiveFileReaderWindows::Serialize Length=37092755` and
capture the first divergence; **do not modify `be2le.py` until ownership is
proven**.

**Baseline preserved:** `SP_E2_P.lvfix.le.xxx` `48b1caf5` `1407` converted `26`
unmodelled `generic_whitelist=set()` `test_be2le 21/21` `names_end 60971`
`imports_end 69119` `exports_end 166663` (`CONTENT-CONVERSION-SURFACE.md:539`).

**Physical position (strong evidence, not yet proof):**
`file_size 11,814,162 - Count 11,641,106 = 173,056` (`FFileManagerWindows.cpp:1`
`Count` vs `Length`). `173056` lies inside `Default__GearPawn_CCarmine`
`172553:622` `rel 503` (1 byte inside `CylinderComponent ObjectProperty` value
at `173055:19` `tag 13` at `173031` `Name 760 Type 1321 Size 4`). This does **not**
prove the active object is the CDO; the stack `UClass::Serialize` suggests the
active object may still be the `UClass` `GearPawn_CCarmine` `172395:158`
(`expected end 172553`) that overran `+503` bytes.

**HARD EXCLUSIONS for this gate:** `NO 26-tail work`, `NO generic_whitelist`,
`NO SerializeExpr`, `NO CoverSlot`, `NO speculative 7×12 / Interfaces
relabeling` until the branch below is proven.

**Instrumented breakpoints (staged `lvfix` `48b1`, `dev` `07:21:39`):**

*Preload ENTER* `ULinkerLoad::Preload @0x0062b34a` (`this=ECX`,
`UObject*=[ESP+4]`):

```
bp 0x0062b34a "r $t0=poi(@esp+4); .echo PRELOAD; ? @$t0; k 2; gc"
; stash $t0 for later correlation; even minimal "PRELOAD $t0" plus existing
; JUDGLOAD naming is sufficient
```

*Serialize* `FArchiveFileReaderWindows::Serialize @0x0057b439`
(`this=ECX`, `V=[ESP+4]`, `Length=[ESP+8]`, `Pos @this+28`, `Size @this+24`,
`Filename FString @this+8`):

```
bp 0x0057b439 "j (dwo(@esp+8)==37092755) '.echo BAD_BULK; ? dwo(@ecx+28); ? dwo(@esp+8); ? poi(@esp); k 6; ? @$t0; gc'; 'gc'"
; capture Length, Pos before read, Size, caller retaddr, kv, outstanding Preload $t0
; Pos before read is authoritative; file_size-Count is supporting
```

Scripts staged as `C:/Games/_judgment-scratch/xvii_both.cmds` and
`xvii_both2.cmds`; logs `xvii_cdb.log` / `xvii_cdb2.log` (scratch, untracked).
Initial `PRELOAD` hits at `0x13e11168` etc. were captured (`xvii_cdb.log:1`
`PRELOAD Evaluate expression: 333517160 = 13e11168`), but the `BAD_BULK` for
`37092755` requires the `LoadMap` phase at `~0024.8` and needs a full `g; g`
past the two WOW64 breaks.

**Decision tree for the single observation:**

```
37,092,755-byte Serialize (Length @[ESP+8])
        ↓
Pos @ECX+28  (definitive)  vs  file_size-Count (supporting)
        ↓
outstanding Preload UObject ($t0) + stack
        │
        ├── GearPawn_CCarmine : UClass 172395:158 Pos~173056
        │      → FIRST runtime archive operation crossing 172553
        │        → disassemble UClass::Serialize at that offset
        │        → correct only that field grammar (likely post-ComponentMap
        │          Interfaces/DLLBindName/ClassDefaultObject, not 7×12 alone)
        │
        └── Default__GearPawn_CCarmine 172553:622 Pos~173056 (+1)
               → trace property parser near 173031–173059
               → find first runtime/converter cursor divergence
               → correct only that tag/value grammar (Bool Size 0 etc.)
```

**Required report fields for this gate (per Work Order):** `1 BAD_BULK Pos`,
`2 Length 37092755`, `3 Serialize caller`, `4 kv`, `5 active Preload
UObject*`, `6 object class`, `7 export index`, `8 SerialOffset:SerialSize`,
`9 Outcome A/B`, `10 first proven divergence`, `11 code change if any`,
`12 test_be2le 21/21`, `13 conversion counts`, `14 staged hash 48b1caf5`,
`15 next blocker`. Until `1`–`9` are proven, **no `be2le.py` change**.

**Status:** `PRELOAD` instrumentation proven working (many `0x13e11168` hits);
`BAD_BULK` conditional not yet hit within the 45 s window — needs a full
unattended run past `0024.8` `LoadMap` with `g; g` and `.logopen`. Next session
continues the same `lvfix` staged file; `be2le.py` remains `set()` and
`SP_E2_P` remains `48b1`.


## Session XVIII: 37 MB read root-caused in the loader; enum-byte values fixed (2026-09-30)

Supersedes the Session XVI/XVII "UClass overrun" hypothesis and the debugger plan. Full engine-side
detail is in the workspace `JUDGMENT-PORT-STATUS.md` (Session XVIII).

- The 37,092,755-byte read was the loader, not `tail_class`: `IsPackageCookedForConsole()` gates on
  `ParseParam(..., "JUDGMENTPKGVER")`, which never matches `-JUDGMENTPKGVER=845`, so the class was
  read with the PC editor `UStruct` layout. `ScriptStorageSize` came from `0x02360000` at 172431, minus
  621 buffered bytes = 37,092,755 exactly. `tail_class` output was correct all along.
- Converter bug: enum-backed `ByteProperty` tag values (Size 8, an FName) were silently left
  big-endian because `SCALAR["ByteProperty"]` is empty. `value()` now swaps them and fails closed on
  a bad FName. 840 values in SP_E2_P; 3 new tests; 24/24 pass.
- `tail_skeletalmesh` / `tail_facefx` (blind 4-byte swaps added 2026-09-05) are no longer registered
  in `NATIVE_TAILS`; they bypassed the fail-closed rule.
- Output `e2-surface\SP_E2_P.enumbyte.le.xxx` (`D681F5FC...`): 1,410/1,433 fully converted, 23
  unmodelled tails. Staged only in the isolated workspace. Runtime: 62 exports load with exact
  sizes; next stop is the unmodelled `FaceFXAnimSet` tail (export 38).

### Session XVIII continued: all loader gates on; FaceFX converts (2026-09-30)

- All four `JUDGMENTPKGVER` loader gates are now active. With the console layout on,
  `FVert::GetSizeForBulkSerialization` is 16, so `tail_model` keeps the console FVert size and
  walks Verts as `[4,4,4,4]`; the old 16->24 retarget is gone (thin map re-staged, boots and
  possesses; new stage `E7658EA5...`).
- `tail_facefx` (precise, fail-closed): `UFaceFXAnimSet`/`UFaceFXAsset` serialize two
  `TArray<BYTE>`. The FxArchive is `FACB` (big endian) SDK 1740, file format 0 - identical to the
  runtime's FaceFX SDK, which byte-swaps on load - so only the two UE3 counts are swapped. 2 tests.
- `SP_E2_P.facefx.le.xxx`: 1,413/1,433 fully converted, 20 unmodelled tails. Runtime loads 84
  exports exactly; next stop is export 69 `Helmet_MASTER` (`Material` native tail, 148 B) - the
  first rendering-side serializer (`FMaterialResource`).

### Session XVIII continued: Material, Model, PhysicsAssetInstance, shader cache (2026-09-30)

- `tail_material` / `tail_material_instance`: Judgment's `FMaterial` block matches v828
  `FMaterial::Serialize` exactly (all 4-byte fields); MICs add `FStaticParameterSet` (switch 32 B,
  mask 44 B, normal 29 B incl. one BYTE, terrain weight 32 B). 11/11 materials convert.
- `tail_model` now handles populated BSP: `FBspNode` 64 B element model, `Surfs` as a
  `TTransArray` (owner + 15-field `FBspSurf` - UnModel.h size comments are stale), zones,
  `FModelVertex` 36 B (Xbox packed normals are W,Z,Y,X so a DWORD swap is correct).
- `tail_physics_asset_instance`: `TMap<FRigidBodyIndexPair,UBOOL>`, 12 B pairs.
- Populated Xbox `ShaderCache`: only the priority is swapped; the workspace engine skips a
  foreign-platform cache in Judgment packages (`[JUDGSHADERCACHE]`).
- `SP_E2_P.shadercache.le.xxx`: 1,430/1,433 converted; only 3 `SkeletalMesh` tails remain.
  Runtime (ws7 loader) loads 557 exports exactly; next stop `COG_Barrick` (`SkeletalMesh`).

## Session XIX: complete SP_E2_P mesh conversion and native boot (2026-09-30)

Continued from `3baf313` on `judgment/skeletalmesh-20260930`, using only the separate
`Judgment Port Workspace` engine source. The inherited packed-position loader implementation
now builds, is v845/opt-in gated, validates finite positions and emits unpack telemetry.

`skeletal_mesh.py` precisely walks the complete skeleton, LODs, alternate influences and trailer;
`be2le.py` supplies the `bHasVertexColors` tag to the walker. The former speculative mesh handler
is removed. Unknown widths, bulk-storage modes, counts or export boundaries fail and roll back.

`SP_E2_P.skeletalmesh-20260930.le.xxx`: **1,433/1,433 fully converted**, zero unsupported/partial,
11,814,162 bytes, SHA-256 `6B3893A3C6830AF6DCE5F1EDB0C2502852B4D970D8B1B3F2660A19AAEB11E3B0`.
Differences from the prior shader-cache checkpoint are confined to three mesh native tails.
Independent package validation reports zero invalid references, 24/24 texture and 254/254
sound frames. Tests pass 39/39, including every synthetic-mesh truncation point.

Loader `ws9-skeletalmesh-verified` loads **1,402 exports exactly** (no mismatches), including all
three meshes, and expands four packed LODs. Logged positions match independent source decoding.
SP_E2_P reaches map-loaded/world-first-tick/Baird possession, then fails on the missing streamed
package `SP_E2_01`. PkgInfo exits 0; the thin map stays alive/possessed for 75 seconds. These are
headless tests; visible rendering and gameplay remain unverified.

Campaign protection: 20,284 files checked; zero changes in either campaign install or the shared
campaign source. Tests use `-NOHOMEDIR` and the isolated runtime only.

Next: `SP_E2_01` assesses at 3,039/4,919 converted, 1,880 unmodelled geometry/lighting/component
tails; its partial output is not staged. See `SKELETAL-MESH-CHECKPOINT.md` for retained artifacts,
private engine patch 0009, exact hashes, regression commands and the next work boundary.

## Session XX: populated geometry, lighting and retail streaming (2026-09-30)

`SP_E2_01` now converts **4,919/4,919**, SP_E2_02 **3,054/3,054**, SP_E2_W **61/61**.
`SP_E2_P` remains **1,433/1,433**. All four have zero partial or unsupported exports.
Bounded geometry serializers model mixed-width BSP/static/fractured meshes, instance LODs,
lightmaps, decals, convex-cache containers, collection matrices and populated Level data.
Native Level colors swap as DWORDs. Dominant light shadows serialize before Super/UObject,
so the converter walks that WORD array before reading the component prologue and tags.

The isolated engine explicitly whitelists retail streaming names under v845/loader opt-in.
Populated BSP exposed console FVert 16B versus PC FVert 24B: BulkSerialize consumed correct
file bytes but put records at the wrong memory stride. Per-record expansion clears the
BuildRenderData assertion. Private incremental source patch 0010 follows mesh patch 0009.

Native loading advances through SP_E2_01, SP_E2_02 and SP_E2_W: **8,571 exact-size loads**,
zero size mismatches, Baird possession and world ticks. Next failure is missing SP_E2_01_S.
PkgInfo/thin-map regressions pass; 50 unit tests pass, with populated archive truncations
and rollback checks. Independent package manifests, BSP topology, FVert counts and all loaded
export offsets/sizes match. Skeletal packed-position telemetry still agrees with the source.

SP_E2_01_S: 560 exports, 438 complete, 116 partial, six native tails unmodelled. CoverSlot
arrays, ActorReference/RouteList, four NavigationMeshBase tails and two Pylon tails remain.
Partial assessment stays in scratch and is not staged. Headless tests also report missing
shadow/sky texture mip bulk data; visible rendering/codecs/physics/gameplay remain unproven.
See `STREAMING-GEOMETRY-CHECKPOINT.md` for exact artifacts, hashes and reproduction commands.

## Session XXI: cooked cover fields and navigation v43 (2026-09-30)

Continued from streaming commit `9c14d4c`. SP_E2_01_S is now **560/560** converted,
SP_E2_Audio **8/8**; all six staged packages total **10,035/10,035** with zero unsupported.
The prior geometry archives remain byte-identical. Native runtime reaches **9,006 exact-size
loads**, zero mismatches, including all four navigation meshes/two pylons and the audio level.
Next missing package: SP_E2_02_S. Its 2,669 exports assess at 2,636 complete, one partial
Profiles array, 28 unmodelled AnimSequence tails and four unmodelled CombatZone tails;
partial output is not staged.

The inherited binary CoverSlot assumptions were wrong: manifest listing order is reversed
relative to the actual declaration-order property chain, script bools serialize one BYTE each,
enums emit FNames, CPF_Native CachedPoly is skipped, and nested BasedPosition retains tags.
`immutable_cover.py` models those rules with bounded reads; transaction rollback preserves
earlier array elements when a later one fails. Tag header reads also check their region bounds.

`native_navigation.py` models v43 vertices, edge storage, polys, transforms, border segments,
bounds and nine registered edge types. Source/LE independent parsing preserves all scalar
values and index topology: 1,905 vertices, 490 polygons, 681 typed edges. Obstacle polygons
reference their pylon's main edge pool. No extra engine modifications are needed.

59 unit tests pass; all six archives independently regenerate and match native preload
offsets/sizes. Packed skeletal-position telemetry still passes. Headless loading does not
establish AI/cover behavior, collision, visual rendering, animations or audio playback.
The final missing-package error is followed by an error-shutdown access violation; evidence
records BLOCKED_AFTER_BOOT. See `NAVIGATION-CHECKPOINT.md` for hashes, commands and next steps.

## Session XXII (2026-09-30): compressed animations and continuing headless world ticks

Continues `3acd5d1` in the isolated converter/engine branches. SP_E2_02_S now converts
2,669/2,669 exports: 28 per-track compressed animations, four built CombatZone poly maps,
and the immutable AimOffsetProfile array. Seven staged packages total 12,704 exports,
zero partial/unsupported. Independent parsing verifies 3,836 encoded tracks, 48,415 keys,
453 frame tables, 164 combat poly refs and 32 aim bones. Native codecs evaluate 6,636
finite pose samples. All archives regenerate exactly; native preload offsets/sizes match.

New opt-in diagnostics revealed that process survival after first tick concealed a texture
streaming stall. Read-only debugger stacks identified shader-cache SavePackage flushing
and forced-export Texture2D linker detachment. NoTextureStreaming is parsed too late for
startup resources. The accepted ws14-v2 helper disables streaming at NullRHI initialization
and skips local shader-cache saves under Judgment NullRHI. Renderer-enabled behavior is
unchanged. Resource omission was tested, failed in ambient occlusion, and reverted; the
accepted binary was rebuilt after a restored-source timestamp caused stale compilation.

The final 100-second headless test passes: 11,266 exact-size loads, no mismatch/critical,
seven loaded levels, and continuing completed ticks through 96.84 seconds (serial 4,196,
game time 67.850). PkgInfo and the 75-second thin map also pass. The regression checks the
four base packed LOD samples by package, allowing additional streamed meshes, and requires
recent paired tick reports. 65 unit tests pass. Campaign/source protection remains zero
changes across 20,284 files. No helper remains running after the tests.

Actual visible-gameplay blockers remain: Baird's mesh is NULL, external texture bulk mips
are missing, and script initialization warnings persist. Input/physics/AI/cover/render/audio
are unverified. Further SP_E2_03_S assessment is unstaged (687 complete/101 unmodelled of
788 exports), requiring morph data and variable-key animation grammar. See
`ANIMATION-PROTOTYPE-CHECKPOINT.md` for accepted patch/binary hashes, evidence and commands.

## Session XXIII (2026-09-30): Baird loads and D3D9 presents the first scene

Continues `d1a4180` on the isolated converter branch. The seven unchanged maps
plus an extracted 108-export Baird asset package now stage 12,812 exports.
The 100-second D3D9 run passes 11,374 exact native loads, zero mismatches/fatal
errors, continuing seven-level world ticks and 3,825 recorded presentations.
Baird uses his intended mesh/physics with 123 bones/local atoms/space bases.
The engine screenshot visibly contains the player and geometry, with incorrect
Xbox textures and lighting. Camera/input, collision, AI/cover and audio remain
unverified. This is a rendering milestone, not completed campaign gameplay.

Startup asset extraction remaps 156 typed references and preserves physical
bulk offsets. Owner-qualified array metadata resolves the `Constraints`
float/object collision. The isolated loader honors explicit NoTextureStreaming
before RHI startup, preventing the observed D3D9 mip-copy crash. New optional
player/presentation diagnostics and engine screenshot capture are retained as
private patches 0015/0016. PkgInfo, thin-map and SP_E2_P headless regressions
also pass; 72 unit tests pass and all seven map artifacts regenerate identically.
See `PLAYER-RENDER-CHECKPOINT.md` for source/artifact/binary hashes, accepted
patches, rejected evidence, reproduction and the texture recovery priority.
Final Gears 3 protection: 20,284 files checked, zero changes.


## Session XXIV (2026-09-30): texture pixels and Baird material parents

Thirty textures / 291 mip levels now contain inline linear PC data: six Baird
textures and SP_E2_P's 23 character textures plus its night color lookup.
`replace_texture_pixels.py` appends recovered C++ fixture pixels while retaining
object/name indices and original normal unpack, SRGB, LOD and clamp settings.
Independent probe/property audits verify all mip bytes and unmodified exports.
`--resolve-imports` clears the extracted startup preload-only flag; Baird's body,
eye and hair resolve their intended PC masters and select all six recovered textures.

The one-mip LUT omits MipTailBaseIdx because its class default is zero. The first
base-textures-v1 attempt incorrectly treated it as unpacked and is rejected.
The corrected packed output matches all 4,096 pixel/16,384 byte addresses measured
with Judgment's own Xbox360Tools cooker. Accepted base map is textures-v2 and
Baird is asset-v4-deps; six streamed maps remain unchanged. The final 100-second
D3D9 run passes 11,374 exact loads, 15 paired tick reports and 4,319 presents.
Armor detail is recognizable, but the dark environment and blue lighting persist;
playable campaign behavior is still unverified. 83 unit tests pass.

See `TEXTURE-PROTOTYPE-CHECKPOINT.md` for hashes, private patch 0017, reproduction
and retained validation evidence. All source/build/content work remains in the
separate Judgment workspace. The campaign baseline verifies 20,284 protected
files with zero changes. Converter and documentation branches are pushed to the
existing GearsJudgement_PCNative remote; retail assets and engine changes are excluded.
