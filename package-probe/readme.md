# Judgment native package probe

This is a Windows command-line investigation tool for the UE3 package boundary shared by the
available Gears of War 3 PC source and the Gears of War: Judgment Xbox 360 debug build.

It currently:

- detects Xbox 360 big-endian and PC little-endian UE3 packages;
- parses the known Gears 3 `FPackageFileSummary` layout;
- reports package, licensee, engine, and cooked-content versions;
- reports name/import/export tables and compressed chunks;
- recognizes UE3 fully-compressed startup-package containers before package parsing;
- identifies LZX, LZO, and zlib compression flags;
- samples names when the name table is physically available without decompression;
- emits stable JSON manifests for uncompressed name/import/export maps;
- validates the source-backed `Package`, `GuidCache`, `ObjectReferencer`, `Texture2D`, and
  `SoundNodeWave` object payload layouts;
- extracts raw, LZO-compressed, or LZX-compressed UE3 bulk payloads;
- converts Xbox 360 tiled texture allocations to linear blocks with configurable block geometry
  and endian units, and decodes linear BC1/DXT1 data to BMP for inspection;
- converts the exact Judgment `GuidCache.xxx` layout to a little-endian Gears 3 PC v828
  package as the first deliberately narrow native conversion fixture;
- extracts an inline Judgment `CompressedXbox360Data` block as a standard RIFF/XMA2 file;
- uses the local Gears 3-era Ogg/Vorbis libraries to encode decoded PCM with the same quality
  mapping as `FPCSoundCooker`;
- creates a deliberately narrow v828 `SoundNodeWave` fixture with PC Ogg bulk for native loading;
- rebuilds complete audio-only packages containing multiple `SoundNodeWave` exports, with new
  serial offsets and one source-matched PC Ogg stream per wave;
- creates a minimal one-export v828 PC `Texture2D` fixture from the first three non-packed
  Judgment BC1 mips, recovering external TFC data and writing linear inline PC bulk;
- creates a `TestSounds.22Mono_TestDialogMale` alias for Jacinto's built-in Vorbis and playback tests.

It does not execute Xbox code, modify source packages, or bypass licensing. Every writing command
refuses to overwrite an output and never modifies its source package. It can reconstruct
both fully-compressed Xbox LZX containers and ordinary chunk-compressed packages. The results
remain big-endian Xbox packages until a deliberately supported object-level converter is used.
General mixed-content conversion remains the next boundary.
The fully-compressed container header does not store its codec; for these Xbox 360 cooks,
the Gears 3 source and platform configuration identify the base codec as LZX.

## Build

From a Visual Studio 2022 developer shell:

```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

When the cache variable `GEARS3_SOURCE_ROOT` points at the local September 2011 Gears 3 source/dev
tree, the probe links the source-matched 64-bit LZO library and CMake also builds
`judgment-wav-to-ogg`. Its default matches the current local corpus. The optional audio target
links the source-matched 64-bit libogg/libvorbis import libraries, copies their runtime DLLs beside
the executable, and declares their Visual C++ 2005 side-by-side dependency.

## Use

```powershell
.\build\Release\judgment-package-probe.exe --names 12 C:\path\to\package.xxx
.\build\Release\judgment-package-probe.exe --json C:\path\to\package.xxx
.\build\Release\judgment-package-probe.exe --inventory C:\path\to\cooked-game
.\build\Release\judgment-package-probe.exe --decompress-container C:\path\GearGame.xxx .\GearGame.uncompressed.xxx
.\build\Release\judgment-package-probe.exe --decompress-package C:\path\Map.xxx .\Map.uncompressed.xxx
.\build\Release\judgment-package-probe.exe --manifest .\Map.uncompressed.xxx .\Map.manifest.json
.\build\Release\judgment-package-probe.exe --extract-bulk .\Map.uncompressed.xxx 2865556 8192 8192 0 .\Mip.tiled.bin
.\build\Release\judgment-package-probe.exe --detile-xbox360 .\Mip.tiled.bin 32 64 4 8 2 .\Mip.dxt1.bin
.\build\Release\judgment-package-probe.exe --decode-dxt1-bmp .\Mip.dxt1.bin 32 64 .\Mip.bmp
.\build\Release\judgment-package-probe.exe --extract-xma .\Audio.uncompressed.xxx 4 .\Voice.xma
.\build\Release\judgment-wav-to-ogg.exe .\Voice.wav .\Voice.ogg 40
.\build\Release\judgment-package-probe.exe --convert-audio-fixture .\Audio.uncompressed.xxx 4 .\Voice.ogg .\AudioFixture.upk
.\build\Release\judgment-package-probe.exe --convert-audio-package .\Audio.uncompressed.xxx .\ogg .\AudioPackage.upk
.\build\Release\judgment-package-probe.exe --convert-texture-fixture .\SP_00_Museum_Background_1_M.uncompressed.xxx 1070 C:\path\Textures.tfc .\T_GT_Fir_Cluster_MASK.upk
.\build\Release\judgment-package-probe.exe --convert-texture-fixture-full-mips .\SP_00_Museum_Background_1_M.uncompressed.xxx 1070 C:\path\Textures.tfc .\T_GT_Fir_Cluster_MASK-full.upk
.\build\Release\judgment-package-probe.exe --make-vorbis-time-test-fixture .\AudioFixture.upk .\TestSounds.upk
.\build\Release\judgment-package-probe.exe --convert-guid-cache C:\path\GuidCache.xxx .\GuidCache.upk
./convert-audio-fixture.ps1 -Package .\Audio.uncompressed.xxx -ExportIndex 4 `
  -OutputDirectory .\audio-test -MakeEngineTestAlias
./convert-audio-package.ps1 -Package .\Audio.uncompressed.xxx `
  -OutputDirectory .\audio-package-test
```

Both decompression commands refuse to overwrite an existing output. Container decompression
recovers the exact pre-container package. Ordinary package reconstruction removes the compressed
chunk descriptors, clears `PKG_StoreCompressed`, and emits the logical uncompressed package.
Both results remain big-endian and are not yet PC packages.

The v4 manifest payload analysis follows the Gears 3 source serialization for `UTexture2D`:
tagged `UObject` properties, `SourceArt`, the regular `FTexture2DMipMap` array, texture-file-cache
GUID, and cached PVRTC mip array. Each bulk record reports flags, element count, stored size,
absolute offset, and whether the payload is inline. The parser accepts UE3's observed
`BULKDATA_StoreInSeparateFile | BULKDATA_Unused` sentinel (`0, -1, -1`) while retaining strict
range and inline-offset checks for real payloads.

`--extract-bulk` accepts numeric offsets, sizes, and flags in decimal or `0x` form. It validates
the UE3 compressed wrapper and uses the source-matched Gears 3 LZO decoder for flag `0x10` or the
existing XMem/LZX decoder for flag `0x80`. It intentionally rejects separate-file records; point
the command at the matching TFC file and clear only the separate-file bit when explicitly
extracting a known cache range.

`--detile-xbox360` operates on a complete Xbox allocation, not an already-trimmed logical mip.
Width and height are pixels; `block-pixels` and `bytes-per-block` are `4,8` for BC1/DXT1 and
`4,16` for BC2/BC3. `endian-unit=2` performs the Xenon 16-bit byte correction used by BC1. The
command walks the complete physical allocation, accepts only blocks mapping inside the logical
surface, and fails on duplicate or missing logical blocks. Packed mip tails require their
source-defined per-level offsets and are not yet converted by this command.

`--convert-texture-fixture` takes a **zero-based** export index. It is deliberately limited to an
uncompressed big-endian Judgment v845 `PF_DXT1` `Texture2D` with empty SourceArt/PVRTC data and at
least three mips before its packed tail. The command reads external bulk from the supplied TFC,
decompresses LZX as needed, detiles and endian-corrects the first three Xbox allocations, and
emits their exact linear BC1 byte counts as uncompressed inline v828 bulk. It writes a compact
package with 17 remapped names, the two imports for `Engine.Texture2D`, and one root texture export.

For this first fixture, `TextureFileCacheName` and `FirstResourceMemMip` are removed because the
output is fully inline, and `MipTailBaseIdx` is changed from 3 to 2 because mip 2 is the final
emitted level. The converter refuses an existing output, verifies every table/reference and
positive bulk offset after writing, requires the payload to close at the export boundary, and
byte-compares all emitted mip data against its in-memory detiled source.

`--convert-texture-fixture-full-mips` preserves that three-mip path and adds the six packed-tail
levels only for the validated 128x256, nine-mip `T_GT_Fir_Cluster_MASK` oracle. The packed layout
was measured with both the January 2011 Gears `XeTools.dll` and Judgment's April 2012
`Xbox360Tools.dll`; both produced the same 45-block placement. XG reports an 8,192-byte allocation,
but every meaningful block lies below byte 1,856 and Judgment serializes the first 4,096 bytes.
The converter contains the resulting dependency-free inverse map, applies the same 16-bit endian
correction per BC1 block, emits all nine levels inline, and changes `MipTailBaseIdx` from 3 to 8.
It rejects every other object, dimension chain, mip count, tail base, or tail allocation size.

The `GuidCache` converter is intentionally not a generic package converter. It accepts only the
observed uncompressed, big-endian v845 package with one `GuidCache` export. It rewrites the v828
summary, name/import/export/dependency tables, `UObject` header, and all
`TMap<FName, FGuid>` records; it also removes Xbox DVD/ECC padding. It refuses an existing output
and independently reparses the generated package before reporting success.

`--extract-xma` takes a one-based export-table index. It accepts only a big-endian,
uncompressed Xbox package and a `SoundNodeWave` export with inline Xbox audio. It scans the
tagged properties, validates all four `FUntypedBulkData` blocks, validates the internal
`FXMAInfo` sizes and XMA2 format tag, endian-converts the 52-byte `XMA2WAVEFORMATEX` and seek
table, and preserves the encoded XMA packets. It refuses an existing output.

`judgment-wav-to-ogg` reproduces the local `FPCSoundCooker` mono/stereo path. It accepts 16-bit PCM
WAV, writes the `ENCODER=UnrealEngine3` tag, and applies the engine's quality adjustment
`clamp((quality - 15) / 100, -0.1, 1.0)`. The default Unreal quality 40 therefore uses Vorbis
quality 0.25.

`--convert-audio-fixture` is intentionally a test-fixture converter, not a general audio-package
converter. It requires the selected `SoundNodeWave` to be the final export. It endian-converts the
v828 summary/tables plus the preceding `Package` and `ObjectReferencer` exports, converts all nine
observed sound properties (including Unicode/ANSI strings, `SubtitleCue`, and the 15-entry
`LocalizedSubtitles` array), removes Xbox audio, and installs the supplied Ogg in
`CompressedPCData`.

It also applies the package flags used by Jacinto PC-cooked audio, clears console forced-export
flags, and replaces the console seek-free `NetIndex` with the standalone-object sentinel.

`--convert-audio-package` handles a complete, audio-only package whose payload stream consists of
`Package`, `ObjectReferencer`, and `SoundNodeWave` exports. It requires every export to be stored
contiguously in table order and rejects unknown classes, unsupported properties, external bulk
data, missing Xbox audio, and missing PC replacements. The Ogg directory must contain
`<one-based-export-index>.ogg` for every wave. The converter rebuilds every serial size and offset,
converts all supported object payloads to little-endian v828, installs PC Ogg bulk, clears Xbox
network indices and forced-export flags, and independently reparses the result.

`convert-audio-package.ps1` automates manifest discovery plus XMA extraction, vgmstream decoding,
source-matched Vorbis encoding, package rebuilding, independent manifest validation, and SHA-256
provenance for every intermediate and final artifact.

`--make-vorbis-time-test-fixture` renames that exact narrow fixture without changing record sizes so
Jacinto's stock `TestVorbisDecompressionSpeed` and `PlaySoundWave` console commands can address it.
The output must be named `TestSounds.upk`.

`convert-audio-fixture.ps1` guards and records the complete XMA extraction → vgmstream WAV decode →
source-matched Ogg encode → v828 fixture → manifest chain. It defaults to the official 64-bit
vgmstream CLI under `build\tools\vgmstream\current`; a different executable can be supplied with
`-VgmstreamCli`. Every output artifact receives a SHA-256 entry in the pipeline JSON, and the script
refuses to overwrite any existing artifact. See `VGMSTREAM-PROVENANCE.md` for the exact retained
decoder build and hashes.

The four numbers for each compressed chunk are the logical uncompressed offset and size,
followed by the physical compressed offset and size.

## Validated local corpus

The initial scan completed without unparsed candidates:

| Corpus | Candidates | Result |
| --- | ---: | --- |
| Judgment debug tree | 1,315 | 27 little-endian v845; 1 big-endian uncompressed v845; 1,277 big-endian LZX v845; 10 big-endian fully-compressed containers |
| Gears 3 Jacinto PC `GearGame` | 2,876 | 2,524 uncompressed v828; 312 LZO v828; 40 older uncompressed packages |

These counts are evidence about the files currently present, not a claim that every serialized
object type is already compatible.

## LZX validation

The decoder uses UE Viewer's established libmspack integration and the UE3/XMem framing found in
the local Gears 3 source. Validation includes:

| Input | Decode result | Independent re-parse |
| --- | --- | --- |
| fully-compressed `Core.xxx` | 2 chunks, 192,745 bytes | v845, 758 names, 1,495 exports, 18 imports |
| fully-compressed `GearGame.xxx` | 839 chunks, 109,958,331 bytes | v845, 72,720 names, 305,867 exports, 4,820 imports |
| `SP_00_Museum_Background_1_M.xxx` | 3 package chunks, 3,096,376 decoded bytes | uncompressed v845, name table begins exactly at rewritten summary end |
| `MP_Centennial.xxx` | 112 package chunks, 118,347,641 decoded bytes | uncompressed v845 with readable name-table samples |

These checks exercise short final frames, large streams, fully-compressed containers, ordinary
package chunks, byte-swapped headers, and packages containing more than 100 logical chunks.

## Metadata and first native conversion validation

The v845 and v828 import/export record layouts close exactly at their advertised table boundaries.
Representative results include the 19,280-export Judgment `MP_Centennial` map and the 91,000-export
Gears 3 PC `GearGame.u`, both with zero invalid metadata references.

The first payload-level checks are also source-backed:

| Package | Endian/version | Payload result |
| --- | --- | --- |
| Judgment `MP_Centennial` | big/v845 | 675/675 `Package` exports match `INT NetIndex + FName(None)` |
| Judgment `GuidCache.xxx` | big/v845 | 2,065 valid `TMap<FName, FGuid>` entries consume all 49,576 export bytes |
| Jacinto PC `GuidCache.upk` | little/v828 | 1,779 entries use the same 24-byte map record layout |
| Converted Judgment `GuidCache.upk` | little/v828 | all 2,065 entries reparse with zero invalid name references |
| Judgment `AID_COMMON_SF_LOC_INT` | big/v845 | 1/1 `ObjectReferencer` and 1/1 `SoundNodeWave` payloads close exactly |
| Jacinto PC `Human_Sam_Efforts.upk` | little/v828 | 1/1 `SoundNodeWave`; its PC bulk begins with `OggS` |
| Judgment `MP_Centennial` | big/v845 | 967/967 `Texture2D` payloads and 4,513 regular mip records close exactly |
| Jacinto PC `UI_CalendarImages.upk` | little/v828 | 2/2 `Texture2D` payloads close exactly |

The converted Judgment `GuidCache.upk` has now passed both relevant checks in the actual Jacinto
Win64 executable. `PkgInfo -exports -simple` reports v828, engine 8741, cooker 134, 2,012 names,
two imports, and one 49,576-byte export with zero errors or warnings. More importantly, the
`UnrealEd.LoadPackageCommandlet` loads the package and its `UGuidCache` payload successfully with
zero errors or warnings. This is a native runtime load, not only an independent structural parse.

The first audio fixture also crosses the codec boundary. Export 4 of
`AID_COMMON_SF_LOC_INT.uncompressed.xxx` contains 10,304 bytes of Xbox audio: a 52-byte XMA2
format, no seek table, and 10,240 encoded bytes. The extractor emits a 10,320-byte RIFF/XMA2 file.
The official vgmstream command-line decoder recognizes it as mono 22,056 Hz XMA2 and decodes
35,328 PCM samples (1.602 seconds). The resulting PCM has a peak magnitude of 27,267 and RMS
6,228.81, so it is not an empty or silent false positive. See the
[vgmstream project](https://github.com/vgmstream/vgmstream) for the independent decoder.

That PCM was then encoded through a standalone clone of the local Gears 3 `FPCSoundCooker` path at
the default quality 40, yielding an 11,224-byte Ogg stream. Independent decoding preserves the
embedded mono 22,056 Hz format and all 35,328 samples. The subtitle-preserving package converter
emitted a 16,754-byte little-endian v828 fixture with four exports. The Jacinto Win64 `PkgInfo` commandlet
reported its `SoundNodeWave` export and zero errors/warnings, and `LoadPackage` then deserialized the
complete package with zero errors/warnings. For repeatable commandlet execution, run `GearGame.exe`
with `Binaries\Win64` as the working directory; launching it from the game root selects normal game
startup instead.

The native runtime test now goes beyond package loading. After normalizing the retained Xbox cook
flags to Jacinto's PC audio flags, the stock `FVorbisAudioInfo` benchmark decoded the converted
Judgment sample 1,000 times without an error (`0.793673 ms` reported per run, `0.495506 ms` per
second per channel). Jacinto's stock `PlaySoundWave TestSounds.22Mono_TestDialogMale` path then
created one active wave instance for that exact asset and registered its transient component with
the XAudio2 device. It also logged the preserved `C'mon… bring it!` subtitle (the legacy log renders
the ellipsis as `&`). The verification log contains no Vorbis, buffer-creation, or fatal errors.

The first complete multi-wave result is `AIDE_215_SF_LOC_INT`: one compressed Judgment package
reconstructs to 28 contiguous exports (nine `Package`, one `ObjectReferencer`, and 18
`SoundNodeWave`). The batch pipeline decoded and re-encoded all 18 XMA streams, converted 129
tagged properties, rebuilt all 28 export offsets, and emitted a 292,782-byte v828 package. The
independent manifest parser accepted all 18 sound payloads, and Jacinto Win64's unmodified
`LoadPackage` commandlet loaded the package with zero errors and zero warnings.

The first texture conversion slice uses `T_GT_Fir_Cluster_MASK`, present in both Judgment and the
Gears 3 PC corpus. Judgment mip 2 is a 32x64 BC1 surface stored in an 8,192-byte Xenon allocation;
the detiler selects exactly 128 logical blocks and emits the expected 1,024 linear bytes. The
same Gears 3 PC mip expands from its 225-byte LZO wrapper to 1,024 bytes. Independent BC1 decode
produces the same vertical fade mask. Across the two separately cooked 32-bit BMP pixel buffers,
59.28% of channel bytes match exactly, mean absolute error is 1.45, RMSE is 2.744, and maximum
error is 9.

The same asset also validates external texture-cache recovery. Mips 0 and 1 were read at their
manifest-reported offsets in Judgment's `Textures.tfc`, expanded from 552 and 458-byte LZX
wrappers to 16,384 and 8,192-byte Xbox allocations, and detiled to 16,384 and 4,096 linear BC1
bytes. The second case proves that physical padding is removed rather than copied into the PC
payload. Their independently cooked Gears 3 PC counterparts expand from LZO to the same linear
sizes and render as the same fade mask. Mip 0 is 95.58% byte-exact after decode (MAE 0.061, RMSE
0.312, maximum error 3); mip 1 is 65.72% byte-exact (MAE 0.961, RMSE 1.895, maximum error 9).
This validates non-packed inline and external-TFC BC1 recovery, detiling, and endian correction.
The exact-geometry packed-tail follow-up is recorded below; format remapping such as Xbox `PF_G8`
to PC `PF_A8R8G8B8` remains subsequent work.

The first writable texture package is
`build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-fixture-v2.upk` (22,440 bytes, SHA-256
`0B2D8D1A90802D90DB713B1A79BEE34CCFA956E747CAD6265C18D7037D70E95B`). Its independent v4
manifest reports little-endian v828, 17 names, two imports, one root `Texture2D` export, zero
invalid references, and exact table/export closure. The three inline mips are 128x256/16,384
bytes, 64x128/4,096 bytes, and 32x64/1,024 bytes; their SHA-256 values exactly match the retained
detiled Judgment validation artifacts.

The unmodified Jacinto 1.1.1 Win64 `UnrealEd.LoadPackageCommandlet` loaded those exact fixture
bytes with zero errors and warnings. The newer independent campaign rebuild was also assessed.
Its fresh `GearGame-Campaign-Steam.exe` is a game-only Win32 target and treats `LoadPackage` as a
map name, while `GearGame-Campaign-Editor.exe` contains the commandlet and loads fixtures. The
copied Win64 executable inside the campaign rebuild is SHA-256-identical to Jacinto 1.1.1, so it
is not an independent second engine test.

The source-derived editor now has an opt-in real-RHI extension to `LoadPackage`, implemented in
`Development\Src\UnrealEd\Src\UnPackageUtilities.cpp`. It leaves ordinary commandlet behavior
unchanged and accepts `-VERIFYTEXTURE2D`, `-EXPECTEDSIZEX`, `-EXPECTEDSIZEY`, `-EXPECTEDFORMAT`,
and `-EXPECTEDMIPS`. Because commandlets do not normally create a viewport, the extension creates
a 64x64 off-screen viewport solely to initialize the selected PC RHI device, explicitly creates
the texture resource, flushes the rendering thread, and requires initialized generic and 2D RHI
texture handles. The isolated executable was built without replacing either Jacinto runtime:
`Binaries\Win32\GearGame-JudgmentTextureTest-v3.exe` (SHA-256
`736756A0043EA69DB10A5002F56205AF344B99979813F53F6AFDC40D94AC1537`).

Run the retained fixture test from PowerShell without `-nullrhi`:

```powershell
& "C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\Binaries\Win32\GearGame-JudgmentTextureTest-v3.exe" LoadPackage `
  "C:\Games\NostalgiaBundle\projects\judgment-native\package-probe\build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-fixture-v2.upk" `
  -VERIFYTEXTURE2D=T_GT_Fir_Cluster_MASK -EXPECTEDSIZEX=128 -EXPECTEDSIZEY=256 `
  -EXPECTEDFORMAT=PF_DXT1 -EXPECTEDMIPS=3 -unattended -nopause -nosound `
  -log=JudgmentTextureResourceD3D-v3.log
```

`JudgmentTextureResourceD3D-v3.log` records a real NVIDIA D3D adapter, `PC-D3D-SM3`, a successful
128x256 `PF_DXT1` resource with three requested/resident mips, and a 21,504-byte RHI allocation.
That allocation exactly equals the three linear BC1 payload sizes. The commandlet completed with
zero errors and warnings. This proves resource creation and mip upload, but does not yet draw and
sample the texture in a visible frame.

The packed-tail follow-up is retained separately as
`build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-full-mips-v3.upk` (22,944 bytes, SHA-256
`F762E164AB0DD43D040D8280E1912B7791C3E9686458355EBA7EDCD1A845F522`). Its independent manifest
reports nine inline mips of 16,384, 4,096, 1,024, 256, 64, 16, 8, 8, and 8 bytes, `MipTailBaseIdx=8`,
zero invalid references, and exact export closure. Re-running the original three-mip command
still produces byte-identical SHA-256
`0B2D8D1A90802D90DB713B1A79BEE34CCFA956E747CAD6265C18D7037D70E95B`, and both commands refuse
overwrite.

The six recovered tail levels independently decode as the same fade sequence as the Gears 3 PC
oracle. For mips 3 through 8 respectively, decoded BGRA mean absolute errors are 1.02, 1.39, 2.94,
8.00, 27.38, and 10.05; the last three comparisons contain only one 4x4 BC1 block each. The stock
Jacinto 1.1.1 Win64 `LoadPackage` commandlet accepted the nine-mip fixture with zero errors and
warnings. The independent campaign rebuild's `GearGame-Campaign-Editor.exe` (SHA-256
`63DF8A3BE782A1100A475172515DB3EF51D85C0DFFB9B5A31A843E99C4C4CA0E`) also accepted it with zero
errors and warnings, making that editor the best clean second deserialization target. A newer
isolated diagnostic editor,
`Binaries\Win32\GearGame-JudgmentTextureTest-v4.exe` (SHA-256
`55D04B7C76AC84337DCE1B27EC2631D9E3EA1EB54ACE394543AB0001F0D996A8`), initialized all nine mips
on a real D3D11 device and reported `requested=9 resident=9 rhi-bytes=21864`, exactly the sum of
the nine linear BC1 payloads, followed by zero errors and warnings.

Reproduce the retained full-mip package from the project directory with:

```powershell
.\build\Release\judgment-package-probe.exe --convert-texture-fixture-full-mips `
  .\build\validation\SP_00_Museum_Background_1_M.uncompressed.xxx 1070 `
  "C:\Games\GearsJudgement\UnrealEngine3-Jack\GearGame\CookedXbox360\Textures.tfc" `
  .\build\validation\T_GT_Fir_Cluster_MASK.judgment-v828-full-mips-repro.upk
```

The output path must not already exist; a successful reproduction has the retained v3 hash above.
To repeat the real-RHI assertion, use the earlier
`LoadPackage` invocation with `GearGame-JudgmentTextureTest-v4.exe`, substitute the full-mip
package path, and set `-EXPECTEDMIPS=9`.

This remains a standalone single-texture fixture, not a complete Judgment PC build. Packed-tail
recovery is proven only for this exact BC1 geometry. The next texture work is to generalize and
validate tail placement across dimensions/formats, implement platform format remapping such as
Xbox `PF_G8` to PC `PF_A8R8G8B8`, and add an on-screen sampled draw before broader package or map
conversion.
