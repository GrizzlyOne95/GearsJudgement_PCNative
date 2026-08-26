# Judgment native-port investigation

## Current evidence

The local Judgment debug build is not source-complete, but it is unusually useful for a
native port investigation: it contains Xbox 360 executables plus PDB/XDB symbols and cooked
UE3 packages. The local Gears 3 tree supplies the closest known PC-native engine/game source
baseline.

The package boundary is confirmed rather than hypothetical:

| Input | Byte order | UE3 package version | Immediate consequence |
| --- | --- | ---: | --- |
| Judgment cooked `.xxx` | Xbox 360 big-endian | 845 in sampled debug files | byte-swap summary and serialized fields |
| Judgment script `.u` | little-endian in sampled file | 845 | useful control sample |
| Gears 3 PC package | little-endian | 828 | source-backed native baseline |

Public reports of retail Judgment packages commonly show version 846. The local debug build
is therefore its own version target; assuming retail layouts would be unsafe.

The first complete local inventory produced these groups:

- 1,277 big-endian version-845 packages with LZX chunk compression;
- 1 big-endian uncompressed version-845 package;
- 27 little-endian uncompressed version-845 packages;
- 10 big-endian fully-compressed UE3 containers, including `GearGame.xxx`;
- zero unrecognized package candidates out of 1,315 scanned.

The comparison Jacinto PC `GearGame` tree also parsed all 2,876 candidates. Its dominant groups
are 2,524 uncompressed and 312 LZO-compressed version-828 packages. This gives the converter a
large source-backed control corpus for both ordinary and chunk-compressed UE3 packages.

## Recommended native path

1. Inventory and parse every package summary, grouping files by endian, version, compression,
   and any summary-layout exceptions.
2. ~~Add read-only Xbox LZX chunk decompression for both package chunks and fully-compressed
   containers, then verify reconstructed bytes against UE3 table offsets and package invariants.~~
   Completed for representative small, large, ordinary, and fully-compressed packages.
3. Diff version 845 serialization against the Gears 3 version 828 source one object type at a
   time, starting with names, imports, exports, bulk data, textures, meshes, and scripts. Name,
   import, export, `Package`, `GuidCache`, `ObjectReferencer`, and `SoundNodeWave` framing are now
   confirmed for the sampled corpus.
4. Build an offline converter that emits PC-native packages accepted by the Gears 3 PC runtime.
5. Only after content conversion is repeatable, port Judgment-specific native classes using
   the PDB/XDB symbols as an interface map. Symbols aid reconstruction; they are not source.

This is a native-data and native-code reconstruction route. Xenia or a runtime Xbox-to-PC
instruction translator can remain a behavioral oracle for testing, but is not part of the
shipping architecture.

## First tool

`package-probe` implements step 1 without altering any game files. Its output should be kept
as the baseline manifest for later decompressor and converter tests.

The ten fully-compressed startup containers use the `FArchive::SerializeCompressed` framing
documented in the local Gears 3 source: package tag, compression chunk size, aggregate sizes,
per-chunk size pairs, then payloads. Codec integration is complete in the probe.

Ordinary packages require one additional reconstruction step. Their physical summary contains
an `FCompressedChunk` table that makes it larger than the logical summary and overlaps the first
logical compressed range. The tool now removes those 16-byte descriptors, writes a zero chunk
count and compression flags, clears `PKG_StoreCompressed`, and places decoded ranges at their
logical offsets. The resulting name-table offset exactly matches the shortened summary boundary.

## First native v828 artifact

`package-probe --convert-guid-cache` now emits the first complete native PC package fixture from
Judgment content. `GuidCache.xxx` is unusually good for this purpose: it is already uncompressed,
contains one export, and the Gears 3 PC source defines its entire native payload as
`UObject::Serialize` followed by `TMap<FName, FGuid>`.

The converter rewrites the full summary, name/import/export maps, dependency map, and 2,065 payload
records from big- to little-endian; changes package version 845 to 828 and saved engine 9580 to the
local PC value 8741; preserves cooked-content version 134; and strips Xbox alignment padding. The
111,698-byte output independently reparses as little-endian v828 with exact table boundaries and a
49,576-byte map payload containing zero invalid name references. A real Jacinto PC `GuidCache.upk`
uses the same payload structure with 1,779 entries.

This proves an offline native conversion is practical, but does not imply arbitrary asset payloads
are compatible. It has also passed the actual Jacinto Win64 `PkgInfo` and `LoadPackage`
commandlets. `LoadPackage` deserialized the converted `UGuidCache` and exited with zero errors and
zero warnings. This is the first genuine native-runtime acceptance result.

## First audio boundary

The generic tagged-property scanner now handles the UE3 v845 property-tag framing used by the
sampled `SoundNodeWave`, including struct, byte-enum, and version-dependent bool metadata. It then
parses the four source-defined bulk slots in order: raw, PC, Xbox 360, and PS3. In Judgment
`AID_COMMON_SF_LOC_INT`, the PC slot is empty and the Xbox slot contains exactly 10,304 inline
bytes. In the Jacinto PC control `Human_Sam_Efforts.upk`, the Xbox slot is empty and the PC slot
contains 5,070 bytes beginning with `OggS`. This demonstrates why sound needs transcoding rather
than only endian conversion.

The Xbox block matches the local `FXMAInfo` source exactly: three big-endian sizes followed by a
52-byte `XMA2WAVEFORMATEX`, a zero-byte seek table, and 10,240 XMA packet bytes. The new
`--extract-xma` command validates that structure and emits a conventional little-endian RIFF/XMA2
file. An independent vgmstream decode produced 35,328 mono PCM samples at the embedded 22,056 Hz
rate (1.602 seconds), with nonzero peak and RMS. Xbox audio extraction is therefore solved for
this framing.

The decoded PCM has now passed through a standalone implementation of the local
`FPCSoundCooker::Cook` algorithm, linked against the exact Gears 3-era libogg/libvorbis binaries.
At the default Unreal compression quality 40, it produced an 11,224-byte Ogg that independently
decodes to the same 35,328-frame, mono 22,056 Hz stream.

A deliberately narrow converter then produced a 16,754-byte little-endian v828 package. It converts
all nine observed sound properties, including the Unicode `SpokenText`, ANSI translator comment,
tagged `SubtitleCue` array, and all 15 tagged `LocalizedSubtitle` records. It replaces the Xbox bulk
with PC Ogg bulk and endian-converts the surrounding `Package` and `ObjectReferencer` exports.
Independent parsing reports exact table and payload boundaries with no invalid references. The
actual Jacinto Win64 `PkgInfo` commandlet sees all four exports, and its `LoadPackage` commandlet
deserializes the complete subtitle-preserving package with zero errors and zero warnings.

The first game-mode attempt retained `PKG_RequireImportsAlreadyLoaded`, `PKG_FilterEditorOnly`, and
`EF_ForcedExport` from the Xbox seek-free cook. Jacinto reached the wave but faulted when accessing
its PC bulk-data member. Matching an ordinary PC audio package's `0x20080009` package flags and
clearing the forced-export bits corrected the linker/archive behavior. The fixture also maps the
source network index to `INDEX_NONE`, because the standalone PC package has no console network
object table.

This is now a native media decode and playback-queue result, not only a native load. Jacinto's unmodified
`TestVorbisDecompressionSpeed` command loaded the aliased asset, initialized `CompressedPCData`, and
ran the stock `FVorbisAudioInfo::ReadCompressedInfo`/`ExpandFile` path 1,000 times without error. A
clean subtitle-preserving run reported `0.793673 ms` per decode and `0.495506 ms` per second per
`PlaySoundWave` command also loaded the same Judgment-derived wave, produced one active wave
instance, registered its transient audio component with the XAudio2 device, and logged the expected
`C'mon… bring it!` subtitle (with the old logger reducing the ellipsis to `&`). There were no
Vorbis, buffer-creation, or fatal errors. The full single-wave chain is now automated by a guarded
PowerShell pipeline with SHA-256 provenance.

## Complete multi-wave audio package

The single-wave result now scales to a real package rather than a renamed fixture.
`AIDE_215_SF_LOC_INT.xxx` reconstructs to a contiguous 246,189-byte package containing nine
`Package` exports, one `ObjectReferencer`, and 18 `SoundNodeWave` exports. All 18 waves have valid
inline Xbox bulk framing.

The new batch pipeline extracts every XMA stream, decodes it with the retained vgmstream build,
encodes it through the source-matched Gears 3 Vorbis path, and supplies the resulting Oggs to a
package-wide converter. That converter endian-converts 129 tagged properties, replaces every Xbox
bulk payload with PC bulk, clears seek-free network indices and forced-export flags, and rebuilds
all 28 serial offsets and sizes. It deliberately rejects gaps, unknown export classes, unsupported
properties, external bulk data, and missing replacement streams.

The 292,782-byte result independently reparses as little-endian v828: all names/imports/exports are
valid, all nine `Package` and the `ObjectReferencer` payloads close exactly, and all 18 sound
payloads retain valid tagged-property and four-slot bulk framing. Most importantly, the unmodified
Jacinto Win64 `LoadPackage` commandlet deserialized the complete package with zero errors and zero
warnings. This completes multi-wave/package audio conversion. Texture bulk data is now the next
high-value content boundary.

## First texture boundary

The probe now follows the complete source-defined `UTexture2D::Serialize` layout on both versions:
tagged `UObject` properties, `SourceArt` bulk, the regular mip array, the texture-file-cache GUID,
and cached PVRTC mips. It also records decoded scalar/name values for common property tags such as
`SizeX`, `SizeY`, `Format`, `TextureFileCacheName`, `MipTailBaseIdx`, and
`FirstResourceMemMip`.

This layout closes exactly for all 967 `Texture2D` exports in the reconstructed Judgment
`MP_Centennial` package (4,513 regular mip records), all 19 textures in
`SP_00_Museum_Background_1_M`, and the sampled v828 PC controls. The corpus revealed a legitimate
UE3 unused-streaming sentinel: flags `0x21` (`StoreInSeparateFile | Unused`) with element count 0,
stored size -1, and offset -1. Real inline payloads still require an exact absolute offset and
complete export-boundary closure.

The regular Judgment mip flags in `MP_Centennial` split into 1,696 inline Xbox allocations
(`0x00`), 1,075 LZX-compressed external TFC records (`0x81`), and 1,742 unused external sentinels
(`0x21`). This means texture conversion must handle both package-resident allocations and the
three Judgment TFC files; blindly copying only inline data would discard higher-resolution mips.

Bulk extraction now supports uncompressed, Gears-source-matched LZO, and XMem/LZX wrappers. The
first exact cross-platform asset oracle is `T_GT_Fir_Cluster_MASK`, which exists in Judgment's
`SP_00_Museum_Background_1_M` and Gears 3 PC's `GOW_Forests.upk`. Judgment mip 2 is a 32x64 BC1
surface occupying an 8,192-byte Xenon allocation. The new Xbox 360 detiler applies 16-bit endian
correction, maps exactly 128 useful BC1 blocks out of that allocation, and emits the required
1,024 linear bytes. The corresponding PC mip independently decompresses from a 225-byte LZO
wrapper to the same linear size.

Both linear payloads now pass the probe's BC1 decoder and render as the same vertical fade mask.
Because Judgment and Gears 3 are separate cooks, the compressed blocks are not byte-identical,
but their decoded pixels are tightly aligned: 59.28% exact channel bytes, mean absolute error
1.45, RMSE 2.744, and maximum error 9. This is the first validated Xbox texture-data conversion
slice.

External cache recovery is now validated on the same asset's two higher-resolution mips.
Manifest offsets in Judgment's `Textures.tfc` locate 552 and 458-byte LZX wrappers, which expand
to 16,384 and 8,192-byte Xbox allocations. Mip 0 (128x256) detiles to 16,384 linear BC1 bytes;
mip 1 (64x128) detiles to 4,096, correctly discarding half of its padded physical allocation.
The matching Gears 3 PC LZO payloads expand to the same linear sizes, and all four decoded images
show the same fade mask. Against those separate PC cooks, Judgment mip 0 is 95.58% exact channel
bytes with MAE 0.061, RMSE 0.312, and maximum error 3; mip 1 is 65.72% exact with MAE 0.961,
RMSE 1.895, and maximum error 9.

At that point, the remaining texture blockers were packed mip-tail offsets, platform format
changes such as the 8x64 smoke fade being `PF_G8` on Xbox but `PF_A8R8G8B8` on PC, and v828
`Texture2D` package emission. The next section completes the first narrowly scoped emission
fixture. The later exact-tail section then resolves one BC1 geometry; format remapping remains
unresolved.

## First writable v828 Texture2D fixture

`package-probe --convert-texture-fixture` now emits a compact, standalone PC package for
`T_GT_Fir_Cluster_MASK` directly from the reconstructed Judgment package plus its original
`Textures.tfc`. The command uses zero-based export index 1070, recovers/decompresses the first two
external LZX allocations and the third inline allocation, then performs the already validated
Xenon BC1 detile and 16-bit endian correction in memory.

The emitted package is little-endian v828 with PC package flags, saved engine version 8741, cooked
content version 134, 17 remapped names, two imports (`Engine` and `Engine.Texture2D`), and one root
texture export. It preserves the six required scalar/name properties (`SizeX`, `SizeY`, original
sizes, `Format=PF_DXT1`, and `MipTailBaseIdx`), removes the now-inapplicable
`TextureFileCacheName` and `FirstResourceMemMip`, maps the console NetIndex to `INDEX_NONE`, and
clears the seek-free forced-export bit. Because only the three proven non-packed levels are
written, `MipTailBaseIdx` changes from 3 to 2.

All three PC mip records are uncompressed inline bulk whose element counts describe linear BC1
data rather than Xbox allocation padding: 16,384 bytes at 128x256, 4,096 bytes at 64x128, and
1,024 bytes at 32x64. The writer independently reparses every table and property, validates all
name/import/export and positive bulk offsets, requires exact export-boundary closure, and compares
the written payload bytes with the in-memory detiled data. A separate v4 manifest reports 1/1
valid Texture2D payloads and zero invalid references. Re-extracted mip SHA-256 values match the
retained detiled artifacts exactly.

The retained reproducible artifact is
`package-probe\build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-fixture-v2.upk`: 22,440 bytes,
SHA-256 `0B2D8D1A90802D90DB713B1A79BEE34CCFA956E747CAD6265C18D7037D70E95B`.
Unmodified Jacinto 1.1.1 Win64 `LoadPackage` accepted these bytes with `0 error(s), 0 warning(s)`.
The independent campaign rebuild's fresh Win32 editor executable accepts the fixtures with the
same result. Its shipped campaign game executable is a valid fresh game build but omits editor
commandlets, and its copied Win64 executable is byte-identical to Jacinto 1.1.1; therefore the
campaign editor is the meaningful second deserialization target while stock Win64 remains the
best fast commandlet baseline.

This proves a writable single-texture boundary, not a Judgment PC build. Render-resource creation
is now asserted by an isolated source-derived Win32 editor build. An opt-in extension to
`UnrealEd.LoadPackageCommandlet` finds the named `UTexture2D`, checks caller-supplied dimensions,
format, and mip count, creates a 64x64 off-screen viewport to trigger UE3's normal PC D3D device
initialization, creates the texture resource explicitly despite commandlet `GIsUCC`, flushes the
rendering thread, and requires initialized `FTextureResource`, `TextureRHI`, and `Texture2DRHI`
handles. Default `LoadPackage` behavior is unchanged.

The retained diagnostic executable is
`gears_of_war_3_2011-09-14\Binaries\Win32\GearGame-JudgmentTextureTest-v3.exe`, 59,526,144 bytes,
SHA-256 `736756A0043EA69DB10A5002F56205AF344B99979813F53F6AFDC40D94AC1537`.
Its `JudgmentTextureResourceD3D-v3.log` run selected a real NVIDIA adapter and `PC-D3D-SM3`, then
reported `size=128x256 format=PF_DXT1 mips=3 requested=3 resident=3 rhi-bytes=21504` followed by
`Success - 0 error(s), 0 warning(s)`. The 21,504-byte allocation is exactly
16,384 + 4,096 + 1,024, so all three emitted linear BC1 levels reached the RHI upload path. A
separate ordinary `-nullrhi` regression run on the same executable also completed with zero
errors and warnings. Hashes confirm the existing Jacinto 1.1.1 executable, campaign rebuild, and
pre-existing fresh editor were not overwritten.

This still proves only a standalone single-texture package and render-resource upload, not a
Judgment PC build or an on-screen sampled draw. The isolated source editor is now the strongest
diagnostic texture target; the fresh campaign executable remains the better eventual gameplay
and visible-render target once it has an isolated package-loader hook.

## Exact BC1 packed-tail recovery

The next narrow step resolves the packed tail for this one oracle without introducing a runtime
dependency. The January 2011 Gears `XeTools.dll` contains the source-backed XG cooker path, while
Judgment ships its April 2012 `Xbox360Tools.dll` and matching PDB. An opt-in extension in a new,
isolated `GearGame-JudgmentTextureTest-v4.exe` loaded each DLL separately and cooked a marker
texture with one unique byte value per logical BC1 block. The `FConsoleSupport` vtable slot used
by both DLLs was checked against the private symbols before calling it. Neither existing runtime
nor the earlier diagnostic editor was overwritten.

Both cooker versions produced the same mapping for all 45 logical blocks in tail mips 3 through
8. `GetMipSize(3)` reports an 8,192-byte XG allocation, but all markers fall between bytes 8 and
1,855 and the upper 4 KiB is zero. This explains Judgment's 4,096-byte serialized bulk rather
than indicating an XDK incompatibility. The ordinary per-level detiler was demonstrably wrong for
this data; the marker-derived map recovers 256, 64, 16, 8, 8, and 8 linear bytes with per-block
16-bit endian correction.

`package-probe --convert-texture-fixture-full-mips` now applies that dependency-free inverse map.
It is deliberately restricted to `T_GT_Fir_Cluster_MASK` with the validated 128x256 dimensions,
nine exact mip dimensions, tail base 3, and a 4,096-byte tail allocation. Every mismatch fails
closed. The original `--convert-texture-fixture` remains the three-mip path and still emits bytes
identical to the retained v2 artifact.

The new artifact is
`package-probe\build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-full-mips-v3.upk`: 22,944
bytes, SHA-256 `F762E164AB0DD43D040D8280E1912B7791C3E9686458355EBA7EDCD1A845F522`.
It contains nine uncompressed inline PC BC1 payloads of 16,384, 4,096, 1,024, 256, 64, 16, 8,
8, and 8 bytes, with `MipTailBaseIdx` rewritten from 3 to the PC-style last mip index 8. The
independent manifest reports one valid Texture2D payload, zero invalid references, and exact
export-boundary closure. The writer's overwrite refusal was rechecked without changing the hash.

All six tail payloads were extracted again and decoded independently beside the matching Gears 3
PC LZO mips. Their BGRA mean absolute errors for mips 3 through 8 are 1.02, 1.39, 2.94, 8.00,
27.38, and 10.05 respectively; the last three samples are single 4x4 blocks. The images retain
the expected fade instead of the white stripe/black corruption produced by the naive detiler.

Unmodified Jacinto 1.1.1 Win64 `LoadPackage` accepted the full-mip artifact with
`0 error(s), 0 warning(s)`. The independent campaign rebuild's
`GearGame-Campaign-Editor.exe` (59,524,608 bytes, SHA-256
`63DF8A3BE782A1100A475172515DB3EF51D85C0DFFB9B5A31A843E99C4C4CA0E`) independently produced
the same zero-error/warning result and is the best clean second deserialization target. The
isolated v4 diagnostic editor (59,531,264 bytes, SHA-256
`55D04B7C76AC84337DCE1B27EC2631D9E3EA1EB54ACE394543AB0001F0D996A8`) selected the NVIDIA D3D11
adapter and reported `size=128x256 format=PF_DXT1 mips=9 requested=9 resident=9 rhi-bytes=21864`,
then completed with zero errors and warnings. The RHI byte count exactly equals the nine emitted
linear payload sizes.

This is still one standalone texture, not a Judgment PC build. Packed-tail recovery is now
reproducible only for this exact BC1 geometry. The next blockers are generalizing tail placement
across dimensions/formats, remapping platform formats such as Xbox `PF_G8` to PC
`PF_A8R8G8B8`, and proving an on-screen sampled draw. Broad map conversion remains out of scope
until those texture cases are repeatable.

## Direct v845 native-loader layout reconstruction

A separate diagnostic path now loads the original little-endian Judgment v845 script packages
inside the source-built Gears 3 Win32 runtime. This is intentionally a reconstruction oracle, not
the shipping content strategy: the offline v845 -> v828 converter remains the preferred final
content path.

The direct loader has progressed by fixing native ABI mismatches reported by startup crashes.
`APylon` first required Judgment's five Recast-era members, then `FPostProcessSettings` required
its complete Judgment ordering rather than an append-only patch. The next reproducible failure was
`AWorldInfo` destruction while `Engine.u` was loading.

Package metadata proves that Judgment `WorldInfo` has 162 native properties versus Gears 3's 161.
The only added member is `InteractiveMusic`, and its exact generated position/type is:

```cpp
class UPostProcessChain* WorldPostProcessChain;
class AInteractiveMusicSubsystem* InteractiveMusic;
BITFIELD bPersistPostProcessToNextLevel:1;
```

`InteractiveMusicSubsystem` is Actor-derived in the Judgment manifest, so the `A` prefix is
required. On 2026-08-17, `Development/Src/Engine/Inc/EngineGameEngineClasses.h` was updated at this
exact position. A byte-preserving backup was retained in Drive before the edit.

The native-block generator was also hardened for this class. `gen_native_block.py` now accepts
`--reference-header`; when package metadata reaches `MapProperty` or UE3's `Map_Mirror` form, it
reuses the exact declaration of an already-existing native member from the reference UHT block
instead of guessing a `TMap<K,V>` ABI. A Judgment-only map still emits an unsupported-property
error and fails closed.

Validation before the source edit used the original v828 Gears 3 `Engine.u` as a control. With the
Gears 3 manifest and `EngineGameEngineClasses.h` as the reference header, the generator reproduced
all 161 `AWorldInfo` properties in declaration order with zero normalized differences. Running the
same path against Judgment v845 produced 162 properties with no unsupported members; after adding
`InteractiveMusic`, the live header likewise matches all 162 generated properties with zero
normalized differences.

The next runtime check is therefore to rebuild the same Win32 Judgment loader and rerun the v845
startup/`PkgInfo` test unchanged. If the previous `AWorldInfo` destruction crash moves, the new
stack identifies the next startup-reachable native owner. The repeated missing `EnginePCF` import
is a separate dependency and should be investigated as its own minimal reconstruction problem
rather than hidden behind layout padding or a broad fake package.

### 2026-08-20 direct-loader result: WorldInfo and Engine ABI corrected

The rebuilt loader initially stopped at the same `AWorldInfo` destructor. Guarded destruction
tracing identified the exact value as
`WorldInfo.PeerHostMigration.HostMigrationTravelURL`. Its supposed Win32 `FString` header was
`data=0x390, num=646, max=883`, proving that cleanup was reading neighboring fields rather than a
constructed string.

The v828 and v845 `FHostMigrationState` declarations are identical. The real mismatch was
cumulative in the owning class:

- Judgment's Xbox layout places `LastTimeUnbuiltLightingWasEncountered` four bytes later than the
  Gears 3 Win32 `/Zp4` layout, so the compatibility header needs an explicit four-byte pad before
  that `DOUBLE`.
- Judgment expands `FLightmassWorldInfoSettings` from 60 to 88 bytes with
  `bEnableAdvancedEnvironmentColor`, `EnvironmentSunColor`, `EnvironmentSunIntensity`,
  `EnvironmentLightTerminatorAngle`, and `EnvironmentLightDirection`.

Together these account exactly for the observed native/reflected offset difference:
`PeerHostMigration` was native offset 1960 but v845 offset 1992. Loader v8 rebuilt with both ABI
corrections destroyed `HostMigrationTravelURL` as `data=0, num=0, max=0` and advanced past
`AWorldInfo`.

The next destructor was `UGameEngine`. `GameEngine` itself is structurally identical between the
packages, but its `UEngine` base is 16 bytes larger in Judgment. Regenerating the v845 native block
identified two added flags (`UseSkeletalMeshTickOptimization`,
`bDebug_DisableConnectionTimeout`) and three trailing floats (`DropRate1Range`, `DropRate2Range`,
`DropRateSlowMultiplier`). Adding them aligned `NamedNetDrivers` at v845 offset 1856. Loader v9
then destroyed that array as `data=0, num=0, max=0` and passed the complete prior cleanup path.

The next reproducible blocker is no longer an invalid property value. During replacement of
`Engine.Default__LevelStreamingDistance`, `StaticFindObjectFastInternal` finds the existing CDO
with `RF_Unreachable` and asserts at `UnObj.cpp:3401`. This object-lifecycle/replacement invariant
is the next direct-loader task.

`EnginePCF` was tested independently with `redirect_imports.py`: all five package/object imports
were redirected to same-class imports already present in `Engine.u`, eliminating every
`EnginePCF` diagnostic without changing the original WorldInfo crash. It is therefore a separate
content dependency and not the cause of either ABI mismatch above. The generated package and
manifests remained local and were not added to Git.

### 2026-08-23 session: heap-smash root cause, full Engine+GearGame ABI batch, loader-stream issue

#### Root cause of the RF_Unreachable assert (v10 watchdog build)

A new `-JUDGMENTCDOWATCH` diagnostic snapshots every live object at first `LoadAllObjects`
and re-verifies lifecycle flags/name/outer before each export creation. First run with
loader v10 produced exactly two violations before the v9 assert:

| victim | old flags | new flags | corrupting export |
| --- | --- | --- | --- |
| `Engine.Default__LevelStreamingDistance` | `0x0000020400100200` | `0x00ffffff40800000` | `Engine.DOFAndBloomEffect` (export 10652) |
| `Engine.Default__SkeletalMeshSocket` | `0x0000020400100200` | `0x000000003e4ccccd` | `Engine.SoundMode` (export 15352) |

`0x3e4ccccd` is the float `0.2f`. This proved the assert had nothing to do with garbage
collection: oversized script-class CDO replacements (`appMemzero(Obj,
InClass->GetPropertiesSize())` over the old native-sized allocation in
`StaticAllocateObject`) were writing past their heap blocks into adjacent natively
registered objects, setting stray bits including `RF_Unreachable`
(`0x200000000` = a TArray header straddling `ObjectFlags`). The fix is the same
methodology as FPostProcessSettings: regenerate native member blocks from the v845
package metadata.

#### Batched ABI correction

`gen_native_block.py` runs against new manifests (`Engine.v845.manifest.json`,
`GearGame.v845.manifest.json`, generated via `judgment-package-probe --manifest`;
GearGame: 66,858 names / 6,302 imports / 273,455 exports, exact layout) produced blocks
for all remaining differing owners. Integrated into headers this session:

- Engine: all 38 remaining unfixed owners (14 pre-`LevelStreamingDistance` suspects plus
  the rest), including `AudioDevice`/`AudioComponent` map members resolved through
  reference-header reuse plus hand declarations (`TMap<FName,DWORD>
  SoundClassToStatIdMapping`, `TMap<USoundNode*,UINT> SoundNodeOffsetMap`), judgment-only
  structs `FPreCombinedStaticMeshActor` and `FAskedClient`, a byte-exact
  `FJudgmentAudioEQEffectStandIn` for ReverbVolume's embedded EQSettings (the real audio
  header cannot be included from EngineClasses.h), and typed-pointer restoration where
  the package only says "pointer" but engine code needs the real type
  (`Sources`/`FreeSources`/`Effects`/`TextToSpeech`/`WaveInstances`/`ViewState`/
  `ArchivePtr`/`DLCConfigCacheChanges`/`NavMeshPathParams.Interface`/`LinkedOutputs`).
- GearGame: 127 shared differing owners across 11 headers plus markerless structs
  (`ActionReloadBarData`, `DeathData`, `EnemySpawnInfo`, `KillPointInfo`,
  `LoadedEnemyList`, `ObjectiveInfo`, `AISpawnInfo`, `AITypeInfo`, `ExtraGUDCollection`,
  `LocalEnemyInfo`, `PlayerInfo`); `GearSquad.DecayedCoverMap` and five GUDManager maps
  resolved via reference-header mode; 56 delta entries proved script-only (no native
  declaration needed) and `CheckpointRecord` confirmed as a scan artifact of per-class
  structs.
- New `GearGame\Inc\GearGameJudgmentStructs.h` holds judgment-only structs referenced by
  value from multiple headers (`FEnemySelection` moved there, `FPlayerInfoCache`,
  `FUltimateAIConstraint`, `FAIDEnemySelection`, `FCustomAnimInfo`, `FEnemyListRecord`,
  seven `FHvBLocust*Level` structs, `FGearSimpleLaserInfo`), wrapped in the same
  `#pragma pack(push,4)` discipline.
- Minimal .cpp migrations updated for renamed/dropped v845 members
  (`*_DEPRECATED` lightmap/chapter/sort-mode migrations now no-ops or renamed;
  GearPawn keeps `LastTaccomTime`/`PostTaccomFireDelay` as native-only members).

Loader builds are produced with the portable VC9 toolchain:
`VS90COMNTOOLS=...\_Toolchain\PortableVC9\Layout\Microsoft Visual Studio 9.0\Common7\Tools\`
plus `UE3_WINDOWS_SDK_DIR=...\Layout\Microsoft SDKs\Windows\v6.0A`, then
`UnrealBuildTool.exe GearGame Win32 Release -OUTPUT <exe>`.

#### Result and the one remaining blocker

Loader v12 loaded Core.u and Engine.u completely (zero watchdog violations - the entire
Engine ABI is now clean) and progressed deep into GearGame.u, passing `GearAI` (208->227
members) which was the previous blocker. The new failure is not an ABI issue:

`Bad import index 5932/32` inside `Function GearGame.GearAI_Cover:CheckForVehicleImpl`.
Instrumented degradation (v20 returns NULL instead of aborting on bad indices) exposed
the mechanism: between two consecutive reads of the same linker object,
`ExportMap.Num()` changed from the correct 273,455 to 0, the summary counters read as
garbage (`Summary.ExportCount=369098752`), and `LinkerRoot` became an unaligned junk
pointer, while `Filename` stayed correct and `Tell()` returned 172 inside a ~25 MB file.
The ULinkerLoad block itself is being overwritten/reused mid-read - i.e., a loader-stream
lifetime problem (precache buffer/handle loss after the missing-content storms for
`EnginePCF`, `AIEditorResources_Tmp`, `UI_BvH`, `Effects_POC`; earlier dumps show
`GetLastError: The system cannot find the file specified`), not package-layout damage.

All instrumentation remains in place behind flags (`-JUDGMENTCDOWATCH`,
`JUDGMENT_LINKER_SUMMARY_SMASH`, `JUDGMENT_IMPORT_FAIL`/`JUDGMENT_BAD_EXPORT_INDEX`
context dumps, `UStruct::Link` cross-linker check). Next session should reproduce with
missing-content imports redirected away (or stub packages supplied) to see whether the
stream corruption disappears, then harden `ULinkerLoad::Preload`'s precache path.

Artifacts retained: `Binaries\Win32\GearGame-JudgmentLoader-v10..v20.exe`,
staging blocks under `package-probe\build\abi-fix-staging\`, run logs
`JudgmentLoader-v10..v20*.log` in `NostalgiaBundle\logs\GearsJudgement_PCNative-runtime\`.

### 2026-08-23 session II: linker-smash forensics - exonerations, instrumentation, and the expression-stream lead

Build lineage this session (all `Binaries\Win32\GearGame-JudgmentLoader-v2*.exe`,
logs alongside in `GearsJudgement_PCNative-runtime\`):

- v21 rooted every linker (`RF_RootSet` under `-JUDGMENTPKGVER`) and added
  `JUDGMENT_GC`, `JUDGMENT_VERIFY_ORPHAN` (Verify() catch), and
  `JUDGMENT_LINKER_BEGINDESTROY` diagnostics. Result: crash unchanged, and NONE of
  those fired - garbage collection never runs, Verify()'s orphaning path never fires,
  no BeginDestroy/Detach occurs. The GC/orphan theory from the research pass is dead.
- v22 forced plain handle-backed file readers (no precache buffer, no SHA buffer,
  `JUDGMENT_LOADER_READER` logs each linker's concrete reader). GearGame.u opens as a
  40,342,788-byte file whose manifest export coverage ends at exactly 40,342,788 (the
  probe's `exports_end: 21045426` is the export TABLE end, not payload end). Crash
  unchanged -> reader-buffer lifetime theories are dead too.
- v23/v24/v25 attempted a `_msize()` replace-overflow trap in `StaticAllocateObject`.
  Lesson recorded: calling `_msize` on permanent-pool objects (registration time, or the
  global `None` object during early Core.u replaces) is undefined behavior and crashed or
  distorted runs; even flag-gated versions perturbed behavior. Trap removed in v26;
  v26 reproduces the exact baseline failure. Do not reintroduce without pool-range guards
  AND validation that early-init behavior is unchanged.

Established facts about the failure:

1. Deterministic: fails inside `Preload(Function GearGame.GearAI_Cover:CheckForVehicleImpl)`
   at archive position `Tell()==172` while resolving import index -5933.
2. At that moment the linker object itself reads back corrupted: `ExportMap.Num()`
   flips 273455 -> 0 between consecutive calls, Summary counters are float-like garbage,
   `LinkerRoot` becomes unaligned junk, while `Filename` stays intact. Something wrote
   over the linker heap block during this one function's serialization.
3. No GC, no detach, no reader swap, and zero `_msize`-detectable replace overflows
   anywhere in Engine.u or GearGame.u up to that point: every replaced object's
   allocation was big enough.

Serialization-format findings (offline analysis, `Temp\opencode\v845drift\`):

- `Engine.Actor.GetTerminalVelocity` is byte-identical in structure across the v828
  control and the v845 file (same slots, only package-relative indices differ), so there
  is no naive fixed-header drift for functions.
- CRITICAL correction to the working model: UE3 does NOT store function bodies as raw
  byte arrays. `UStruct::Serialize` reads `ScriptBytecodeSize` (logical) +
  `ScriptStorageSize` (physical) and then executes the `SerializeExpr` state machine over
  the stream; consumption depends on opcode semantics. A flat-slot parser can never fit,
  which is why the brute-force fits failed.
- Remaining open question: the exact UStruct/UState/UClass/UFunction on-disk field order
  for these packages (candidate orders differ on where `ScriptText`/`CppText` refs sit
  relative to `Children`, and whether `Line`/`TextPos` serialize here), and whether a
  v842+ era expression-opcode change makes the Sept-2011 `SerializeExpr` miswalk v845
  streams. The observed wild import index (-5933), float-garbage patterns, and heap
  smashes are all consistent with an expression-stream desync writing through bogus
  operands.

Recommended next session plan:

1. Finish fitting the UStruct header against the v828 CONTROL by simulating the actual
   `SerializeExpr` machine from `UnClass.cpp` (opcode table in `UnScript.h`), not flat
   slots; validate on thousands of control functions until consumption == serial_size.
2. Run the fitted walker over v845 Engine/GearGame exports in export order; the first
   divergent opcode identifies the format delta precisely.
3. Patch the Sept-2011 `SerializeExpr`/serializers behind the `-JUDGMENTPKGVER` gate for
   any confirmed delta, rebuild, and rerun the watchdog suite.

### 2026-08-23 session III: expression-walker built; bytecode-format drift EXCLUDED

`Temp\opencode\v845drift\walk.py` implements a faithful Python model of the on-disk
function serialization, validated against an in-engine field dump
(`JUDGMENT_STRUCT`, loader v27): for `Function Engine.Actor:Sleep` the runtime reads
`line=1535 textpos=42659 logical=11 physical=7`. Established layout:

- Header (12 dwords): Next, SuperStruct, ScriptText-ref, Children-ref, CppText-ref,
  three unknown dwords (0 / children+1 / 0 - identical in both eras), Line, TextPos,
  ScriptBytecodeSize (logical), ScriptStorageSize (physical).
- Storage: `SerializeExpr` stream, physical bytes.
- Tail (15 bytes): iNative u16, OperPrecedence u8, FunctionFlags **DWORD**,
  [RepOffset u16 if FUNC_Net(0x00200000)], FriendlyName FName q64.
- Bytecode pointer operands (`XFERPTR`) are **4-byte indices on disk** but advance the
  logical cursor by 8 (memory QWORD width) - this explains logical>physical sizes.

Walker results: control v828 Engine.u functions 72.9% exact-consumption match;
v845 Engine.u functions **73.1%** with the IDENTICAL failure set; v845 GearGame.u 47.6%
(walker gaps in debug-info/net variants, equally present in the control).

CONCLUSION: there is no v828->v845 bytecode format drift. The engine parses v845
function streams exactly as it parses its own v828 files, mismatches included. The
GearAI_Cover linker-smash therefore originates elsewhere - prime suspects are now (a)
Class/State/ScriptStruct export parsing of v845 content (the three unknown header dwords
appear in ALL UStructs and are consumed by the real engine, so they are reader-known),
(b) tagged-property/default serialization paths, or (c) an interaction inside
CreateExport class-binding for GearGame script-only classes. The walker and header map
are retained as the foundation for extending the simulation to Class exports next.

### 2026-08-23 session III addendum: bytecode-window theory also excluded

Loader v28 added `JUDGMENT_BYTECODE_NESTED_PRELOAD` logging at `ULinkerLoad::Preload`
entry: it fires if any preload runs while the linker's Loader is swapped to the
stack-local bytecode MemReader inside `UStruct::Serialize`. Result: zero occurrences -
the MemReader window never experiences nested preloads, excluding that corruption route
as well. A living short-form status document now exists in the build tree at
`C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\JUDGMENT-PORT-STATUS.md`, containing
the milestone summary, the full exonerated-mechanisms table, confirmed layout facts,
live hypotheses, and the exact build/run recipe for the diagnostic loaders.


### 2026-08-24 session II: layout sweep industrialized; exit purge completes (exit code 0)

Built on the session-I milestone (full script load). The remaining blocker was
exit-time purge faulting on classes whose v845 layout was REORDERED relative to
the alpha headers.

- Generalized the ExitProperties layout dumper: `-JUDGMENTLAYOUTALL` /
  `-JUDGMENTLAYOUTCLASSES=` now emit a `[JUDGLAYOUT][CLS:<name>]` property-chain
  table for every destroyed class. A single instrumented run yields the full
  4,778-class relinked-layout database used for offline sweeping
  (`JudgmentLoader-v49-layoutall.log`).
- Wrote a hierarchy-aware verifier (staged at `Temp\opencode\sweep_v3.py`):
  parent graph from header declarations, child base anchored at the PARENT'S
  logged v845 PropertiesSize, x86 packing simulation (align<=4 + bitfield dword
  runs), and a stage-only-if-every-offset-reproduces rule. Key methodology
  corrections recorded: (1) anchoring at min-own-offset masks parent-size drift -
  GamePlayerController had LOST `CurrentSoundMode` in v845 and the resulting -8
  byte shift of every GearPC-family object masqueraded as a GearPC/FortUpgradeList
  stride bug; (2) member add/remove must be classified separately from pure
  reorder before staging (109 MEMBER_DELTA classes hide inside what naive
  offset-diffing calls "reorders"); (3) multiset-check both sides symmetrically.
- Applied 7 simulation-proven reorders (AGearAI, GearEngine, FileWriter, GearGRI,
  GearPawn_LocustCorpserLarvaUndergroundBase, GearSpawner,
  SeqAct_DummyWeaponFire) plus the AGamePlayerController member removal.
- RESULT: `GearGame-JudgmentLoader-v51.exe PkgInfo -JUDGMENTPKGVER=845` completes
  with `Success - 0 error(s), 0 warning(s)` AND exits 0 through StaticExit purge
  (`JudgmentLoader-v51.log`). The reorder-crash family is closed.
- Remaining known deltas for the next phase (live-object instantiation readiness):
  109 MEMBER_DELTA + 29 SIZE_MISMATCH classes from sweep_v3's buckets; plan is to
  extend gen_native_block.py to emit full BEGIN/END PROPS blocks from package
  payloads and sweep both buckets to OK.

## Local Win32 Loader Validation Steps

Because Jules operates in a headless Linux sandbox without the proprietary Win32 loader executable, the following checks must be performed locally in the Win32 loader environment:

1. **ShaderCache Native Tail Validation**:
   - Verify that converted `ShaderCache` exports deserialize with `SP_PCD3D_SM3=0` (converted from Xbox `SP_XBOXD3D=2`).
   - Confirm that the runtime correctly binds `LocalShaderCache-PC-D3D-SM3.upk`.
   - Verify that any non-zero Xbox shader/compressed-map counts trigger fail-closed rejection during package conversion.

2. **FVert Bulk Array & Relocation Validation**:
   - Verify that `TArray::BulkSerialize` validates element size 24 for PC vertex streams (compared to 16 for console).
   - Test static/skeletal mesh loading in `GearGame-JudgmentLoader-v60-nativecontent.exe` to confirm no vertex attribute desynchronization occurs.
   - Validate that relocated package export serial offsets and summary invariants pass `LoadPackage` commandlet checks with zero errors or warnings.

3. **Runtime Execution & Log Verification**:
   - Run local Win32 loader with `-log` and verify clean deserialization logs:
     ```powershell
     .\GearGame-JudgmentLoader-v60-nativecontent.exe LoadPackage GearGame_P.upk -log=JudgmentWin32Loader.log
     ```
   - Confirm world tick, pawn possession (`GearPawn_COGBairdJack`), and native AID spawning (`GearPC_AID`) complete without asserts or heap corruption.

## Code and Tooling Reuse Analysis

To avoid duplicating package-parsing logic across tools:

- **`package-probe/src/main.cpp`**:
  - Reuses C++ routines for summary/table parsing (`parseSummary`), LZX/LZO chunk decompression (`decompressXMemLzx`, `decompressSerializedBlob`), and bulk payload extraction.
  - Reuses `ManifestResolver` for object path resolution and verification.

- **Python Tooling (`v845_converter.py`, `redirect_imports.py`, `proptypes.py`)**:
  - `v845_converter.py` provides the relocation-capable package rewrite layer, converting native export tails (`ShaderCache`, `FVert`) and recalculating export serial offsets and package summary fields.
  - `redirect_imports.py` reuses manifest import table offsets to perform targeted import redirects without altering package structures.
  - `proptypes.py` extracts property target types directly from script package manifests for ABI layout generation.

## Staged Path to Retail Judgment Frontend and Campaign Levels

Following the 2026-08-25 milestone where the Win32 loader booted a converted thin `GearGame_P` level end-to-end, the path forward is staged as follows:

1. **Stage 1: Thin Level End-to-End Boot (Completed 2026-08-25)**
   - Converted Judgment `GearGame_P` thin persistent level loaded successfully.
   - All 10 exports converted, first render and world tick completed, `GearPC_AID` and `GearPawn_COGBairdJack` possessed.

2. **Stage 2: Synthetic Fixtures & Relocation Layer (Current)**
   - Implement `v845_converter.py` relocation layer for `ShaderCache` native tails and `FVert` 16-to-24 header retargeting/relocation.
   - Synthetic regression test harness in `tests/test_v845_converter.py` ensuring table invariants and fail-closed safety.

3. **Stage 3: First Full Campaign Level (`SP_00_Museum_P`)**
   - Apply relocation converter to populated native structures in campaign maps (Models, StaticMeshes, Textures, Audio, Collision, Visibility).
   - Convert `SP_00_Museum_Background_1_M` and `SP_00_Museum_P`, verifying level streaming and static mesh vertex buffer uploads on PC D3D3/SM3.

4. **Stage 4: Retail Judgment Frontend and Menu Path**
   - Convert Judgment frontend UI and menu packages (`UI_Frontend`, `UI_Main`).
   - Validate Judgment menu state machine and character selection screens in the native Win32 loader.
