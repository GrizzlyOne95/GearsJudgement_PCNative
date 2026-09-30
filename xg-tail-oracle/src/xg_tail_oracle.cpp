/*
 * xg-tail-oracle: a standalone Win32 measurement tool for the Xbox 360 packed
 * mip tail.
 *
 * The Judgment native-port converter must stay dependency-free, so it cannot
 * call the proprietary Xenon console-tools DLL at conversion time.  This tool
 * exists purely to *measure* what that DLL does, so a closed-form model can be
 * validated against it offline.
 *
 * Unlike the earlier in-editor oracle, this host drives FConsoleTextureCooker
 * directly with synthetic geometry.  It needs no engine, no package, and no
 * real texture asset, so it can sweep arbitrary dimensions and formats.
 *
 * Method: every logical block of every packed-tail level is given a unique
 * one-based global id.  Three cook passes recover a complete byte-level map:
 *
 *   pass 0  every byte of block b = (id      ) & 0xFF   -> id low byte
 *   pass 1  every byte of block b = (id >>  8) & 0xFF   -> id high byte
 *   pass 2  byte j of every block = j                   -> intra-block order
 *
 * Destination memory is zeroed before each cook, so an output byte whose id is
 * zero was never written by the cooker.  Pass 2 exposes the byte permutation
 * the cooker applies inside a block (the 16-bit endian correction for BC1),
 * which a single-value marker scheme cannot see.
 */

// UE3 is a Unicode build, so TCHAR must be wchar_t here too.
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

// UnConsoleTools.h declares no includes of its own, so including it verbatim
// gives the exact FConsoleSupport vtable layout the engine uses.  windows.h
// already supplies every scalar it needs (INT, UINT, DWORD, BYTE, FLOAT,
// TCHAR).  It does need WIN32 to be a usable integer constant: the header
// guards its __stdcall callback typedefs with `#if WIN32`, and the Windows SDK
// defines WIN32 with no value, which makes that directive fail to compile.
#ifdef WIN32
#undef WIN32
#endif
#define WIN32 1

#include "UnConsoleTools.h"

typedef unsigned long DWORD_UE;

namespace {

// Slack appended to every destination buffer so an over-writing cooker is
// caught by inspection instead of by a heap corruption crash.
const UINT kDestinationGuard = 65536;

struct FormatInfo {
  const char* name;
  DWORD_UE unrealFormat;
  UINT blockSizeX;
  UINT blockSizeY;
  UINT blockBytes;
};

// Mirrors GPixelFormats in Engine/Src/UnRenderUtils.cpp.
const FormatInfo kFormats[] = {
    {"PF_A8R8G8B8", 2, 1, 1, 4}, {"PF_G8", 3, 1, 1, 1},
    {"PF_G16", 4, 1, 1, 2},      {"PF_DXT1", 5, 4, 4, 8},
    {"PF_DXT3", 6, 4, 4, 16},    {"PF_DXT5", 7, 4, 4, 16},
    {"PF_V8U8", 25, 1, 1, 2},    {"PF_BC5", 24, 4, 4, 16},
    {"PF_A16B16G16R16", 20, 1, 1, 8},
};

const FormatInfo* findFormat(const std::string& name) {
  for (const auto& format : kFormats) {
    if (name == format.name) return &format;
  }
  return nullptr;
}

// The console-tools DLL is proprietary and faults outright on some synthetic
// geometries.  These wrappers contain no C++ objects needing unwinding, so a
// structured-exception guard is safe here and lets a sweep record the rejected
// geometry instead of losing the whole run.
bool safeInit(FConsoleTextureCooker& cooker, DWORD_UE format, UINT width, UINT height,
              UINT numMips) {
  __try {
    cooker.Init(format, width, height, numMips, 0);
    return true;
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

bool safeQuery(FConsoleTextureCooker& cooker, INT& tailBase) {
  __try {
    tailBase = cooker.GetMipTailBase();
    return true;
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

bool safeMipSize(FConsoleTextureCooker& cooker, UINT level, UINT& size) {
  __try {
    size = cooker.GetMipSize(level);
    return true;
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

bool safeCookMipTail(FConsoleTextureCooker& cooker, void** source, UINT* pitches, void* dest) {
  __try {
    cooker.CookMipTail(source, pitches, dest);
    return true;
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    return false;
  }
}

UINT mipDimension(UINT base, UINT level) {
  const UINT value = base >> level;
  return value > 0 ? value : 1;
}

UINT blockCount(UINT pixels, UINT blockSize) {
  const UINT count = (pixels + blockSize - 1) / blockSize;
  return count > 0 ? count : 1;
}

struct Oracle {
  HMODULE module = nullptr;
  FConsoleTextureCooker* cooker = nullptr;

  bool load(const wchar_t* dllPath) {
    module = LoadLibraryW(dllPath);
    if (module == nullptr) {
      std::fprintf(stderr, "error: LoadLibrary failed (%lu) for the console-tools DLL\n",
                   GetLastError());
      return false;
    }
    auto getConsoleSupport =
        reinterpret_cast<FuncGetConsoleSupport>(GetProcAddress(module, "GetConsoleSupport"));
    if (getConsoleSupport == nullptr) {
      std::fprintf(stderr, "error: DLL has no GetConsoleSupport export\n");
      return false;
    }
    FConsoleSupport* support = getConsoleSupport();
    if (support == nullptr) {
      std::fprintf(stderr, "error: GetConsoleSupport returned null\n");
      return false;
    }
    cooker = support->GetGlobalTextureCooker();
    if (cooker == nullptr) {
      std::fprintf(stderr, "error: this DLL exposes no global texture cooker\n");
      return false;
    }
    return true;
  }

  ~Oracle() {
    if (module != nullptr) FreeLibrary(module);
  }
};

struct BlockMap {
  UINT level = 0;       // tail-relative level (0 = tail base)
  UINT blockX = 0;      // logical block coordinate inside that level
  UINT blockY = 0;
  std::vector<UINT> byteOffsets;  // output offset of each source byte j
};

// One measured geometry.
struct Measurement {
  bool hasPackedTail = false;
  INT tailBase = 0;
  UINT tailAllocationSize = 0;
  UINT tailMipCount = 0;
  std::vector<BlockMap> blocks;
  UINT unmappedBytes = 0;
  UINT duplicateBytes = 0;
  bool wroteBeyondAllocation = false;
  // Set when the geometry is measurable in principle but out of range for the
  // marker scheme; the sweep records it and moves on rather than aborting.
  const char* skipReason = nullptr;
};

bool measure(FConsoleTextureCooker& cooker, const FormatInfo& format, UINT width, UINT height,
             UINT numMips, Measurement& out) {
  if (!safeInit(cooker, format.unrealFormat, width, height, numMips)) {
    out.skipReason = "the cooker faulted during Init";
    return true;
  }
  if (!safeQuery(cooker, out.tailBase)) {
    out.skipReason = "the cooker faulted during GetMipTailBase";
    return true;
  }
  if (out.tailBase < 0 || static_cast<UINT>(out.tailBase) >= numMips) {
    out.hasPackedTail = false;
    return true;
  }
  out.hasPackedTail = true;
  if (!safeMipSize(cooker, static_cast<UINT>(out.tailBase), out.tailAllocationSize)) {
    out.skipReason = "the cooker faulted during GetMipSize";
    return true;
  }
  out.tailMipCount = numMips - static_cast<UINT>(out.tailBase);
  if (out.tailAllocationSize == 0) {
    out.skipReason = "the cooker reported a zero-byte tail allocation";
    return true;
  }

  // Per-level logical geometry, and the global block id space.
  std::vector<UINT> blocksX(out.tailMipCount);
  std::vector<UINT> blocksY(out.tailMipCount);
  std::vector<UINT> firstId(out.tailMipCount);
  UINT nextId = 1;
  for (UINT i = 0; i < out.tailMipCount; ++i) {
    const UINT level = static_cast<UINT>(out.tailBase) + i;
    blocksX[i] = blockCount(mipDimension(width, level), format.blockSizeX);
    blocksY[i] = blockCount(mipDimension(height, level), format.blockSizeY);
    firstId[i] = nextId;
    nextId += blocksX[i] * blocksY[i];
  }
  const UINT totalBlocks = nextId - 1;
  if (totalBlocks > 0xFFFF) {
    out.skipReason = "tail block count exceeds the 16-bit marker space";
    return true;
  }

  std::vector<std::vector<BYTE>> passes(3);
  for (UINT pass = 0; pass < 3; ++pass) {
    // Source buffers.  Sized defensively: the cooker may read a full
    // allocation-sized region for the tail base level.
    std::vector<std::vector<BYTE>> sourceData(out.tailMipCount);
    std::vector<void*> sourcePointers(out.tailMipCount);
    std::vector<UINT> sourcePitches(out.tailMipCount);
    for (UINT i = 0; i < out.tailMipCount; ++i) {
      const UINT logicalBytes = blocksX[i] * blocksY[i] * format.blockBytes;
      const UINT allocate =
          logicalBytes > out.tailAllocationSize ? logicalBytes : out.tailAllocationSize;
      // Same slack as the destination: the cooker sometimes reads a full
      // allocation-shaped region for a level whose logical data is smaller.
      sourceData[i].assign(allocate + kDestinationGuard, 0);
      sourcePointers[i] = sourceData[i].data();
      sourcePitches[i] = blocksX[i] * format.blockBytes;

      for (UINT block = 0; block < blocksX[i] * blocksY[i]; ++block) {
        const UINT id = firstId[i] + block;
        BYTE* target = sourceData[i].data() + block * format.blockBytes;
        for (UINT byte = 0; byte < format.blockBytes; ++byte) {
          if (pass == 0) {
            target[byte] = static_cast<BYTE>(id & 0xFF);
          } else if (pass == 1) {
            target[byte] = static_cast<BYTE>((id >> 8) & 0xFF);
          } else {
            target[byte] = static_cast<BYTE>(byte & 0xFF);
          }
        }
      }
    }

    // Pad the destination so a cooker that writes past its own reported
    // allocation is detected rather than corrupting the heap.
    passes[pass].assign(out.tailAllocationSize + kDestinationGuard, 0);
    if (!safeCookMipTail(cooker, sourcePointers.data(), sourcePitches.data(),
                         passes[pass].data())) {
      out.skipReason = "the cooker faulted during CookMipTail";
      return true;
    }
    for (UINT guard = 0; guard < kDestinationGuard; ++guard) {
      if (passes[pass][out.tailAllocationSize + guard] != 0) {
        out.wroteBeyondAllocation = true;
        break;
      }
    }
  }

  // Rebuild the byte-level map.
  std::vector<BlockMap> blocks(totalBlocks);
  for (UINT i = 0; i < out.tailMipCount; ++i) {
    for (UINT block = 0; block < blocksX[i] * blocksY[i]; ++block) {
      BlockMap& entry = blocks[firstId[i] + block - 1];
      entry.level = i;
      entry.blockX = block % blocksX[i];
      entry.blockY = block / blocksX[i];
      entry.byteOffsets.assign(format.blockBytes, 0xFFFFFFFFu);
    }
  }

  for (UINT offset = 0; offset < out.tailAllocationSize; ++offset) {
    const UINT id = static_cast<UINT>(passes[0][offset]) |
                    (static_cast<UINT>(passes[1][offset]) << 8);
    if (id == 0) {
      ++out.unmappedBytes;
      continue;
    }
    if (id > totalBlocks) {
      std::fprintf(stderr, "error: cooked output holds unknown block id %u at offset %u\n", id,
                   offset);
      return false;
    }
    const UINT sourceByte = passes[2][offset];
    if (sourceByte >= format.blockBytes) {
      std::fprintf(stderr, "error: byte index %u at offset %u exceeds the block size\n",
                   sourceByte, offset);
      return false;
    }
    BlockMap& entry = blocks[id - 1];
    // Very small surfaces are legitimately replicated by the cooker, so the
    // same source byte can land in more than one output slot.  Keep the lowest
    // offset as the canonical placement and count the rest.
    if (entry.byteOffsets[sourceByte] != 0xFFFFFFFFu) {
      ++out.duplicateBytes;
      if (offset < entry.byteOffsets[sourceByte]) entry.byteOffsets[sourceByte] = offset;
      continue;
    }
    entry.byteOffsets[sourceByte] = offset;
  }

  out.blocks = std::move(blocks);
  return true;
}

void writeJson(std::FILE* file, const char* dllName, const FormatInfo& format, UINT width,
               UINT height, UINT numMips, const Measurement& measurement) {
  std::fprintf(file, "  {\n");
  std::fprintf(file, "    \"dll\": \"%s\",\n", dllName);
  std::fprintf(file, "    \"format\": \"%s\",\n", format.name);
  std::fprintf(file, "    \"width\": %u,\n", width);
  std::fprintf(file, "    \"height\": %u,\n", height);
  std::fprintf(file, "    \"mips\": %u,\n", numMips);
  std::fprintf(file, "    \"blockSizeX\": %u,\n", format.blockSizeX);
  std::fprintf(file, "    \"blockSizeY\": %u,\n", format.blockSizeY);
  std::fprintf(file, "    \"blockBytes\": %u,\n", format.blockBytes);
  std::fprintf(file, "    \"hasPackedTail\": %s", measurement.hasPackedTail ? "true" : "false");
  if (measurement.skipReason != nullptr) {
    std::fprintf(file, ",\n    \"skipped\": \"%s\"\n  }", measurement.skipReason);
    return;
  }
  if (!measurement.hasPackedTail) {
    std::fprintf(file, "\n  }");
    return;
  }
  std::fprintf(file, ",\n    \"tailBase\": %d,\n", measurement.tailBase);
  std::fprintf(file, "    \"tailAllocationSize\": %u,\n", measurement.tailAllocationSize);
  std::fprintf(file, "    \"tailMipCount\": %u,\n", measurement.tailMipCount);
  std::fprintf(file, "    \"wroteBeyondAllocation\": %s,\n",
               measurement.wroteBeyondAllocation ? "true" : "false");
  std::fprintf(file, "    \"unmappedBytes\": %u,\n", measurement.unmappedBytes);
  std::fprintf(file, "    \"duplicateBytes\": %u,\n", measurement.duplicateBytes);

  // The byte permutation inside a block is an invariant of the format, not of
  // the individual block, so collect the distinct ones and index into them.
  // This keeps a full sweep small enough to analyse comfortably.
  std::vector<std::vector<int>> permutations;
  std::vector<std::size_t> blockPermutation(measurement.blocks.size(), 0);
  std::vector<long long> blockBase(measurement.blocks.size(), -1);
  for (std::size_t i = 0; i < measurement.blocks.size(); ++i) {
    const BlockMap& block = measurement.blocks[i];
    UINT base = 0xFFFFFFFFu;
    for (UINT offset : block.byteOffsets) {
      if (offset < base) base = offset;
    }
    if (base == 0xFFFFFFFFu) continue;
    blockBase[i] = static_cast<long long>(base);
    std::vector<int> relative;
    relative.reserve(block.byteOffsets.size());
    for (UINT offset : block.byteOffsets) {
      relative.push_back(offset == 0xFFFFFFFFu ? -1
                                               : static_cast<int>(offset - base));
    }
    std::size_t index = 0;
    for (; index < permutations.size(); ++index) {
      if (permutations[index] == relative) break;
    }
    if (index == permutations.size()) permutations.push_back(relative);
    blockPermutation[i] = index;
  }

  std::fprintf(file, "    \"bytePermutations\": [");
  for (std::size_t p = 0; p < permutations.size(); ++p) {
    std::fprintf(file, "%s[", p == 0 ? "" : ", ");
    for (std::size_t j = 0; j < permutations[p].size(); ++j) {
      std::fprintf(file, "%s%d", j == 0 ? "" : ", ", permutations[p][j]);
    }
    std::fprintf(file, "]");
  }
  std::fprintf(file, "],\n    \"blocks\": [\n");
  for (std::size_t i = 0; i < measurement.blocks.size(); ++i) {
    const BlockMap& block = measurement.blocks[i];
    std::fprintf(file, "      {\"level\": %u, \"x\": %u, \"y\": %u, \"offset\": ", block.level,
                 block.blockX, block.blockY);
    if (blockBase[i] < 0) {
      std::fprintf(file, "null, \"perm\": null}");
    } else {
      std::fprintf(file, "%lld, \"perm\": %zu}", blockBase[i], blockPermutation[i]);
    }
    std::fprintf(file, "%s\n", i + 1 == measurement.blocks.size() ? "" : ",");
  }
  std::fprintf(file, "    ]\n  }");
}

struct Geometry {
  const FormatInfo* format;
  UINT width;
  UINT height;
  UINT mips;
};

UINT fullMipCount(UINT width, UINT height) {
  UINT count = 1;
  while (width > 1 || height > 1) {
    width = width > 1 ? width >> 1 : 1;
    height = height > 1 ? height >> 1 : 1;
    ++count;
  }
  return count;
}

void usage() {
  std::fprintf(stderr,
               "usage:\n"
               "  xg-tail-oracle.exe <tools.dll> <output.json> --sweep\n"
               "  xg-tail-oracle.exe <tools.dll> <output.json> <format> <width> <height> [mips]\n"
               "\n"
               "formats:");
  for (const auto& format : kFormats) std::fprintf(stderr, " %s", format.name);
  std::fprintf(stderr, "\n");
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc < 4) {
    usage();
    return 1;
  }

  const std::wstring dllPath = argv[1];
  const std::wstring outputPath = argv[2];

  if (GetFileAttributesW(outputPath.c_str()) != INVALID_FILE_ATTRIBUTES) {
    std::fwprintf(stderr, L"error: refusing to overwrite existing output '%s'\n",
                  outputPath.c_str());
    return 1;
  }

  std::vector<Geometry> geometries;
  const std::wstring mode = argv[3];
  if (mode == L"--sweep") {
    // Square, wide, tall, and non-power-of-two-ish chains across the formats
    // whose tails actually matter for the Judgment corpus.
    const char* sweepFormats[] = {"PF_DXT1", "PF_DXT5", "PF_DXT3", "PF_G8", "PF_A8R8G8B8",
                                  "PF_BC5", "PF_V8U8", "PF_G16", "PF_A16B16G16R16"};
    const UINT sizes[] = {1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024};
    for (const char* name : sweepFormats) {
      const FormatInfo* format = findFormat(name);
      if (format == nullptr) continue;
      for (UINT width : sizes) {
        for (UINT height : sizes) {
          // Keep the sweep to sane aspect ratios and marker-space sizes.
          const UINT ratio = width > height ? width / height : height / width;
          if (ratio > 8) continue;
          geometries.push_back({format, width, height, fullMipCount(width, height)});
        }
      }
    }
  } else {
    if (argc < 6) {
      usage();
      return 1;
    }
    char formatName[64] = {};
    std::snprintf(formatName, sizeof(formatName), "%ls", argv[3]);
    const FormatInfo* format = findFormat(formatName);
    if (format == nullptr) {
      std::fprintf(stderr, "error: unknown format '%s'\n", formatName);
      usage();
      return 1;
    }
    const UINT width = static_cast<UINT>(_wtoi(argv[4]));
    const UINT height = static_cast<UINT>(_wtoi(argv[5]));
    const UINT mips = argc > 6 ? static_cast<UINT>(_wtoi(argv[6])) : fullMipCount(width, height);
    if (width == 0 || height == 0 || mips == 0) {
      std::fprintf(stderr, "error: width, height, and mip count must all be positive\n");
      return 1;
    }
    geometries.push_back({format, width, height, mips});
  }

  Oracle oracle;
  if (!oracle.load(dllPath.c_str())) return 1;

  char dllName[260] = {};
  {
    const std::wstring& path = dllPath;
    const std::size_t slash = path.find_last_of(L"\\/");
    const std::wstring leaf = slash == std::wstring::npos ? path : path.substr(slash + 1);
    std::snprintf(dllName, sizeof(dllName), "%ls", leaf.c_str());
  }

  std::FILE* out = nullptr;
  if (_wfopen_s(&out, outputPath.c_str(), L"wb") != 0 || out == nullptr) {
    std::fwprintf(stderr, L"error: could not create '%s'\n", outputPath.c_str());
    return 1;
  }
  std::fprintf(out, "[\n");

  std::size_t written = 0;
  std::size_t packed = 0;
  for (const Geometry& geometry : geometries) {
    // Flushed progress: if the proprietary cooker ever takes down the process
    // despite the guards, the last line printed names the guilty geometry.
    std::fprintf(stderr, "measuring %s %ux%u (%u mips)\n", geometry.format->name, geometry.width,
                 geometry.height, geometry.mips);
    std::fflush(stderr);
    Measurement measurement;
    if (!measure(*oracle.cooker, *geometry.format, geometry.width, geometry.height, geometry.mips,
                 measurement)) {
      std::fprintf(stderr, "error: measurement failed for %s %ux%u (%u mips)\n",
                   geometry.format->name, geometry.width, geometry.height, geometry.mips);
      std::fclose(out);
      return 1;
    }
    if (written > 0) std::fprintf(out, ",\n");
    writeJson(out, dllName, *geometry.format, geometry.width, geometry.height, geometry.mips,
              measurement);
    ++written;
    if (measurement.hasPackedTail) ++packed;
  }

  std::fprintf(out, "\n]\n");
  std::fclose(out);
  std::fprintf(stdout, "measured %zu geometries (%zu with a packed tail) using %s\n", written,
               packed, dllName);
  return 0;
}
