#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <vector>

// Decodes a single buffer produced by the Xbox 360 XMem LZX codec. UE3 wraps
// these buffers in its own chunk tables; this function handles only XMem's
// internal 32 KiB framing and the four-byte safety padding added by UE3.
bool decompressXMemLzx(std::span<const std::uint8_t> input,
                       std::size_t expectedOutputSize,
                       std::vector<std::uint8_t>& output,
                       std::string& error);

