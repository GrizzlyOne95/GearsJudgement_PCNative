#include "xmem_lzx.h"

#include <lzx.h>
#include <mspack_minimal.h>

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <sstream>

namespace {

struct InputFile {
  mspack_file base{};
  std::span<const std::uint8_t> data;
  std::size_t position{};
  std::size_t frameBytesRemaining{};
  bool invalid{};
};

struct OutputFile {
  mspack_file base{};
  std::span<std::uint8_t> data;
  std::size_t position{};
  bool invalid{};
};

std::uint16_t readBig16(std::span<const std::uint8_t> data, std::size_t& offset) {
  const auto value = static_cast<std::uint16_t>(
      (static_cast<std::uint16_t>(data[offset]) << 8) | data[offset + 1]);
  offset += 2;
  return value;
}

int readInput(mspack_file* opaque, void* destination, int requested) {
  auto& file = *reinterpret_cast<InputFile*>(opaque);
  if (file.invalid || requested <= 0) return file.invalid ? -1 : 0;

  if (file.frameBytesRemaining == 0) {
    if (file.position >= file.data.size()) return 0;
    std::size_t compressedSize = 0;
    if (file.data[file.position] == 0xFF) {
      if (file.data.size() - file.position < 5) {
        file.invalid = true;
        return -1;
      }
      ++file.position;
      (void)readBig16(file.data, file.position);  // explicit uncompressed frame size
      compressedSize = readBig16(file.data, file.position);
    } else {
      if (file.data.size() - file.position < 2) {
        file.invalid = true;
        return -1;
      }
      compressedSize = readBig16(file.data, file.position);
    }
    if (compressedSize == 0) return 0;
    if (compressedSize > file.data.size() - file.position) {
      file.invalid = true;
      return -1;
    }
    file.frameBytesRemaining = compressedSize;
  }

  const auto count = std::min<std::size_t>(
      static_cast<std::size_t>(requested), file.frameBytesRemaining);
  std::memcpy(destination, file.data.data() + file.position, count);
  file.position += count;
  file.frameBytesRemaining -= count;
  return static_cast<int>(count);
}

int writeOutput(mspack_file* opaque, void* source, int requested) {
  auto& file = *reinterpret_cast<OutputFile*>(opaque);
  if (file.invalid || requested < 0 ||
      static_cast<std::size_t>(requested) > file.data.size() - file.position) {
    file.invalid = true;
    return -1;
  }
  std::memcpy(file.data.data() + file.position, source, static_cast<std::size_t>(requested));
  file.position += static_cast<std::size_t>(requested);
  return requested;
}

void* allocate(mspack_system*, std::size_t bytes) { return std::malloc(bytes); }
void release(void* value) { std::free(value); }
void copyBytes(void* source, void* destination, std::size_t bytes) {
  std::memcpy(destination, source, bytes);
}

struct LzxDeleter {
  void operator()(lzxd_stream* stream) const { lzxd_free(stream); }
};

bool validateFrameSizes(std::span<const std::uint8_t> input,
                        std::size_t expectedOutputSize,
                        std::string& error) {
  std::size_t position = 0;
  std::size_t outputSize = 0;
  while (position < input.size() && outputSize < expectedOutputSize) {
    std::size_t compressedSize = 0;
    std::size_t uncompressedSize = 0x8000;
    if (input[position] == 0xFF) {
      if (input.size() - position < 5) {
        error = "truncated XMem short-frame header";
        return false;
      }
      ++position;
      uncompressedSize = readBig16(input, position);
      compressedSize = readBig16(input, position);
    } else {
      if (input.size() - position < 2) {
        error = "truncated XMem frame header";
        return false;
      }
      compressedSize = readBig16(input, position);
    }
    if (compressedSize == 0 || uncompressedSize == 0) break;
    if (compressedSize > input.size() - position) {
      error = "XMem frame exceeds the compressed buffer";
      return false;
    }
    if (uncompressedSize > expectedOutputSize - outputSize) {
      error = "XMem frame exceeds the expected output size";
      return false;
    }
    position += compressedSize;
    outputSize += uncompressedSize;
  }
  if (outputSize != expectedOutputSize) {
    std::ostringstream message;
    message << "XMem framed output size mismatch: got " << outputSize
            << ", expected " << expectedOutputSize;
    error = message.str();
    return false;
  }
  return true;
}

}  // namespace

bool decompressXMemLzx(std::span<const std::uint8_t> input,
                       std::size_t expectedOutputSize,
                       std::vector<std::uint8_t>& output,
                       std::string& error) {
  output.clear();
  error.clear();
  if (input.size() < 4) {
    error = "XMem buffer is smaller than UE3's four-byte LZX padding";
    return false;
  }

  // UE3 includes four bytes of safety padding in the stored compressed size.
  input = input.first(input.size() - 4);
  if (!validateFrameSizes(input, expectedOutputSize, error)) return false;

  output.resize(expectedOutputSize);
  InputFile source{{}, input};
  OutputFile destination{{}, output};
  mspack_system system{
      nullptr, nullptr, readInput, writeOutput, nullptr, nullptr, nullptr,
      allocate, release, copyBytes, nullptr};

  std::unique_ptr<lzxd_stream, LzxDeleter> decoder(lzxd_init(
      &system, &source.base, &destination.base, 17, 0, 256 * 1024,
      static_cast<off_t>(expectedOutputSize)));
  if (!decoder) {
    error = "libmspack could not initialize its LZX decoder";
    output.clear();
    return false;
  }
  const int result = lzxd_decompress(decoder.get(), static_cast<off_t>(expectedOutputSize));
  if (result != MSPACK_ERR_OK || source.invalid || destination.invalid ||
      destination.position != expectedOutputSize) {
    std::ostringstream message;
    message << "libmspack LZX decode failed (code " << result << ", produced "
            << destination.position << " of " << expectedOutputSize << " bytes)";
    error = message.str();
    output.clear();
    return false;
  }
  return true;
}
