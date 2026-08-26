# Judgment Native-PC Campaign Conversion Architecture & Staged Path

## Overview

This document outlines the relocation-capable v845 package rewrite architecture, code reuse analysis, staged campaign/menu conversion roadmap, and downstream local-loader validation procedures for *Gears of War: Judgment* native PC conversion.

---

## 1. Relocation-Capable v845 Package Rewrite Architecture

Real campaign levels contain populated native structures that change width between Xbox 360 (big-endian) and Win32 PC (little-endian). The SAME-LENGTH converter model breaks when native structures (such as `FVert`, `FStaticMeshRenderData`, or `FShaderCache`) shrink, grow, or require element-level expansion.

### Key Components (`v845_rewrite.py`)

1. **Package Summary & Table Invariant Preservation**:
   - Re-allocates Name, Import, Export, and Dependency tables.
   - Recomputes `TotalHeaderSize` and all table offsets (`NameOffset`, `ImportOffset`, `ExportOffset`, `DependsOffset`).
   - Recomputes `SerialOffset` and `SerialSize` for every export entry upon payload growth/shrinkage.
   - Ensures zero orphaned references or negative table counts.

2. **Native Tail Retargeting**:
   - **ShaderCache (`ShaderCache.SeekFreeShaderCache`)**:
     * Accepts exact empty Xbox ShaderCache (`SP_XBOXD3D = 2`).
     * Retargets platform byte to `SP_PCD3D_SM3 = 0`.
     * **Fails closed** (raises `ShaderCacheError`) if compressed, shader, or material maps are populated (since Xbox shaders cannot run on PC D3D).
   - **FVert Bulk Array**:
     * Header conversion for empty bulk arrays (`ElementCount = 0`): retargets `ElementSize` from 16 to 24 bytes.
     * Widening & relocation for populated bulk arrays (`ElementCount > 0`): expands each 16-byte Xbox `FVert` element to 24-byte PC `FVert` by appending 8 zero bytes for `BackfaceShadowTexCoord`, relocates the payload, and recomputes export `SerialOffset`/`SerialSize`.
     * **Fails closed** (raises `FVertError`) if element size is not 16/24 or payload is truncated.

---

## 2. Tooling Reuse Analysis

Rather than duplicating logic across tools:

- **`package-probe/src/main.cpp` (C++)**:
  - **Reusable Components**: `parseSummary()`, `decompressContainer()`, `decompressPackage()`, LZX/LZO wrapper decompressors (`decompressSerializedBlob`), detiling algorithms (`xbox360TiledX`, `xbox360TiledY`, `packedMipTailCoordinatePixels`), and audio/texture bulk extraction (`extractBulkPayload`).
  - **Integration**: `package-probe` remains the primary high-performance diagnostic C++ binary for container decompression, bulk extraction, detiling, and initial manifest generation.

- **`v845_rewrite.py` (Python)**:
  - Serves as the high-level relocation and package rewrite engine. Works directly with synthetic package data as well as uncompressed package blobs.

- **`redirect_imports.py` (Python)**:
  - Handles diagnostic import redirection for missing package/class references without altering export payload layouts.

- **`proptypes.py` & `gen_native_block.py` (Python)**:
  - Resolves script property types and generates ABI-aligned native C++ headers for Judgment-specific class overrides (e.g., `AWorldInfo`, `AGearAI`, `AGearGRI`).

---

## 3. Staged Path: Thin `GearGame_P` to Campaign Level & Frontend Menu

```
[Phase 1: Proven Thin Map] ---> [Phase 2: Single Campaign Level] ---> [Phase 3: Frontend/Menu Path]
  - GearGame_P thin level         - SP_00_Museum_Background_1_M     - FrontEnd_P / Judgment UI
  - 5 native tails                - Relocated Models & StaticMeshes - Scaleform / GFX UI assets
  - GearPC_AID / Baird Jack       - Populated FVert arrays widened  - Frontend menu flow & ticks
```

### Stage 1: Thin `GearGame_P` Level (Completed Milestone)
- Verified v845 loader boots persistent level end-to-end.
- 10 exports converted; initial world tick completes; `GearPawn_COGBairdJack` spawns and is possessed.

### Stage 2: Single Campaign Level (`SP_00_Museum_Background_1_M` / `SP_01_Library`)
- **Step 2.1**: Decompress container & ordinary LZX chunks using `package-probe`.
- **Step 2.2**: Execute `v845_rewrite.py` to convert ShaderCache tails (empty -> SM3) and widen `FVert` bulk arrays (16 -> 24 bytes per element).
- **Step 2.3**: Convert external & inline textures via `convertTextureFixture` (detiling BC1/DXT5 mips, packed-tail reconstruction).
- **Step 2.4**: Convert SoundNodeWave audio packages to PC Ogg Vorbis bulk using `convertAudioPackage`.
- **Step 2.5**: Relocate all export serial offsets and verify manifest table boundaries.

### Stage 3: Retail Judgment Frontend/Menu Path (`FrontEnd_P`)
- **Step 3.1**: Convert startup containers (`GearGame.xxx`, `RefShaderCache-PC-D3D-SM3.upk`, `LocalShaderCache-PC-D3D-SM3.upk`).
- **Step 3.2**: Convert Scaleform/GFX menu packages and font textures.
- **Step 3.3**: Validate native menu controller initialization and UI tick lifecycle.

---

## 4. Downstream Local-Loader Validation Steps

Since proprietary executables are intentionally excluded from this repository, downstream developers testing on local Win32/Win64 loader environments must perform the following manual validation steps:

1. **Package Summary Verification**:
   ```powershell
   # Verify little-endian v828/v845 summary and exact table boundaries:
   ./package-probe/build/judgment-package-probe <converted_package.upk>
   ```

2. **Commandlet Load Acceptance**:
   ```powershell
   # Run Jacinto / Win32 PkgInfo commandlet:
   GearGame-JudgmentLoader-v60-nativecontent.exe PkgInfo <converted_package.upk> -JUDGMENTPKGVER=845
   # Expected: Success - 0 error(s), 0 warning(s)
   ```

3. **Runtime Deserialization (`LoadPackage`)**:
   ```powershell
   # Run Win32 loader LoadPackage:
   GearGame-JudgmentLoader-v60-nativecontent.exe LoadPackage <converted_package.upk>
   # Expected: Deserialization succeeds with zero assertions or heap corruption.
   ```

4. **Level Spawn & World Tick Verification**:
   ```powershell
   # Boot persistent campaign level:
   GearGame-JudgmentLoader-v60-nativecontent.exe GearGame_P?game=GearGame.GearGameSP
   # Expected log signatures:
   # - "GearPC_AID spawned"
   # - "GearPawn_COGBairdJack spawned and possessed"
   # - "First world tick complete"
   ```
