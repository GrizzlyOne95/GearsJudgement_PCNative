#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

#include "xmem_lzx.h"

#if defined(HAVE_GEARS3_LZOPRO)
#include <lzo/lzopro/lzo1x.h>
#endif

namespace fs = std::filesystem;

namespace {

constexpr std::uint32_t kPackageTag = 0x9E2A83C1u;
constexpr std::uint32_t kPackageTagSwapped = 0xC1832A9Eu;
constexpr std::int32_t kVerAdditionalCookPackages = 516;
constexpr std::int32_t kVerThumbnails = 584;
constexpr std::int32_t kVerCrossLevelReferences = 623;
constexpr std::int32_t kVerTexturePreallocation = 767;
constexpr std::size_t kMaxStringUnits = 1u << 20;
constexpr std::size_t kMaxArrayItems = 1u << 20;

enum class Endian { Little, Big };

struct ParseError : std::runtime_error {
  using std::runtime_error::runtime_error;
};

class Reader {
 public:
  Reader(const fs::path& path, Endian endian) : stream_(path, std::ios::binary), endian_(endian) {
    if (!stream_) throw ParseError("could not open file");
    stream_.seekg(0, std::ios::end);
    const auto end = stream_.tellg();
    if (end < 0) throw ParseError("could not determine file size");
    size_ = static_cast<std::uint64_t>(end);
    stream_.seekg(0, std::ios::beg);
  }

  std::uint64_t size() const { return size_; }

  std::uint64_t position() {
    const auto value = stream_.tellg();
    if (value < 0) throw ParseError("invalid stream position");
    return static_cast<std::uint64_t>(value);
  }

  void seek(std::uint64_t position) {
    if (position > size_) throw ParseError("seek beyond end of file");
    stream_.clear();
    stream_.seekg(static_cast<std::streamoff>(position), std::ios::beg);
    if (!stream_) throw ParseError("seek failed");
  }

  std::uint8_t u8() {
    std::array<std::uint8_t, 1> bytes{};
    read(bytes.data(), bytes.size());
    return bytes[0];
  }

  std::uint16_t u16() {
    std::array<std::uint8_t, 2> bytes{};
    read(bytes.data(), bytes.size());
    if (endian_ == Endian::Little) {
      return static_cast<std::uint16_t>(bytes[0] | (bytes[1] << 8));
    }
    return static_cast<std::uint16_t>((bytes[0] << 8) | bytes[1]);
  }

  std::uint32_t u32() {
    std::array<std::uint8_t, 4> bytes{};
    read(bytes.data(), bytes.size());
    std::uint32_t result = 0;
    if (endian_ == Endian::Little) {
      for (int i = 3; i >= 0; --i) result = (result << 8) | bytes[static_cast<std::size_t>(i)];
    } else {
      for (std::uint8_t byte : bytes) result = (result << 8) | byte;
    }
    return result;
  }

  std::int32_t i32() { return static_cast<std::int32_t>(u32()); }

  std::vector<std::uint8_t> bytes(std::size_t count) {
    std::vector<std::uint8_t> result(count);
    if (count != 0) read(result.data(), result.size());
    return result;
  }

  std::uint64_t u64() {
    std::array<std::uint8_t, 8> bytes{};
    read(bytes.data(), bytes.size());
    std::uint64_t result = 0;
    if (endian_ == Endian::Little) {
      for (int i = 7; i >= 0; --i) result = (result << 8) | bytes[static_cast<std::size_t>(i)];
    } else {
      for (std::uint8_t byte : bytes) result = (result << 8) | byte;
    }
    return result;
  }

  std::string fstring() {
    const std::int32_t length = i32();
    if (length == 0) return {};
    if (length == std::numeric_limits<std::int32_t>::min()) throw ParseError("invalid FString length");
    const std::size_t units = static_cast<std::size_t>(length < 0 ? -length : length);
    if (units > kMaxStringUnits) throw ParseError("unreasonable FString length");

    std::string result;
    if (length > 0) {
      std::vector<std::uint8_t> bytes(units);
      read(bytes.data(), bytes.size());
      const auto terminator = std::find(bytes.begin(), bytes.end(), 0);
      result.assign(bytes.begin(), terminator);
    } else {
      result.reserve(units);
      bool terminated = false;
      for (std::size_t i = 0; i < units; ++i) {
        const std::uint16_t code = u16();
        if (code == 0) {
          terminated = true;
          continue;
        }
        if (terminated) continue;
        if (code < 0x80) {
          result.push_back(static_cast<char>(code));
        } else if (code < 0x800) {
          result.push_back(static_cast<char>(0xC0 | (code >> 6)));
          result.push_back(static_cast<char>(0x80 | (code & 0x3F)));
        } else {
          result.push_back(static_cast<char>(0xE0 | (code >> 12)));
          result.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
          result.push_back(static_cast<char>(0x80 | (code & 0x3F)));
        }
      }
    }
    return result;
  }

 private:
  void read(void* output, std::size_t count) {
    const auto current = position();
    if (count > size_ - current) throw ParseError("unexpected end of file");
    stream_.read(static_cast<char*>(output), static_cast<std::streamsize>(count));
    if (!stream_) throw ParseError("read failed");
  }

  std::ifstream stream_;
  Endian endian_;
  std::uint64_t size_{};
};

void writeLittle32(std::vector<std::uint8_t>& bytes, std::uint64_t offset,
                   std::uint32_t value) {
  if (offset + 4 > bytes.size()) throw ParseError("write beyond end of file");
  for (std::size_t i = 0; i < 4; ++i) {
    bytes[static_cast<std::size_t>(offset) + i] =
        static_cast<std::uint8_t>((value >> (i * 8)) & 0xFFu);
  }
}

void writeLittle64(std::vector<std::uint8_t>& bytes, std::uint64_t offset,
                   std::uint64_t value) {
  if (offset + 8 > bytes.size()) throw ParseError("write beyond end of file");
  for (std::size_t i = 0; i < 8; ++i) {
    bytes[static_cast<std::size_t>(offset) + i] =
        static_cast<std::uint8_t>((value >> (i * 8)) & 0xFFu);
  }
}

void appendLittle32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
  for (std::size_t i = 0; i < 4; ++i) {
    bytes.push_back(static_cast<std::uint8_t>((value >> (i * 8)) & 0xFFu));
  }
}

void appendLittle64(std::vector<std::uint8_t>& bytes, std::uint64_t value) {
  for (std::size_t i = 0; i < 8; ++i) {
    bytes.push_back(static_cast<std::uint8_t>((value >> (i * 8)) & 0xFFu));
  }
}

void appendAnsiFString(std::vector<std::uint8_t>& bytes, std::string_view value) {
  if (value.size() >= static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max())) {
    throw ParseError("ANSI FString is too large");
  }
  appendLittle32(bytes, static_cast<std::uint32_t>(value.size() + 1));
  bytes.insert(bytes.end(), value.begin(), value.end());
  bytes.push_back(0);
}

void appendLittle16(std::vector<std::uint8_t>& bytes, std::uint16_t value) {
  bytes.push_back(static_cast<std::uint8_t>(value & 0xFFu));
  bytes.push_back(static_cast<std::uint8_t>(value >> 8u));
}

class LittleEndianRewriter {
 public:
  LittleEndianRewriter(const fs::path& input, Endian sourceEndian,
                       std::vector<std::uint8_t>& output)
      : reader_(input, sourceEndian), output_(output) {}

  std::uint64_t position() { return reader_.position(); }
  void seek(std::uint64_t position) { reader_.seek(position); }

  std::uint32_t u32(std::optional<std::uint32_t> replacement = std::nullopt) {
    const auto offset = position();
    const auto original = reader_.u32();
    writeLittle32(output_, offset, replacement.value_or(original));
    return original;
  }

  std::int32_t i32(std::optional<std::int32_t> replacement = std::nullopt) {
    const auto value = u32(replacement ? std::optional<std::uint32_t>(
                                            static_cast<std::uint32_t>(*replacement))
                                      : std::nullopt);
    return static_cast<std::int32_t>(value);
  }

  std::uint64_t u64() {
    const auto offset = position();
    const auto value = reader_.u64();
    writeLittle64(output_, offset, value);
    return value;
  }

  std::string fstring() {
    const auto lengthOffset = position();
    const auto length = reader_.i32();
    writeLittle32(output_, lengthOffset, static_cast<std::uint32_t>(length));
    if (length == 0) return {};
    if (length == std::numeric_limits<std::int32_t>::min()) {
      throw ParseError("invalid FString length");
    }
    const auto units = static_cast<std::size_t>(length < 0 ? -length : length);
    if (units > kMaxStringUnits) throw ParseError("unreasonable FString length");
    std::string result;
    if (length > 0) {
      const auto start = position();
      const auto begin = output_.begin() + static_cast<std::ptrdiff_t>(start);
      const auto end = begin + static_cast<std::ptrdiff_t>(units);
      const auto terminator = std::find(begin, end, 0);
      result.assign(begin, terminator);
      reader_.seek(start + units);
    } else {
      result.reserve(units);
      bool terminated = false;
      for (std::size_t i = 0; i < units; ++i) {
        const auto offset = position();
        const auto value = reader_.u16();
        if (offset + 2 > output_.size()) throw ParseError("write beyond end of file");
        output_[static_cast<std::size_t>(offset)] = static_cast<std::uint8_t>(value & 0xFFu);
        output_[static_cast<std::size_t>(offset) + 1] =
            static_cast<std::uint8_t>((value >> 8) & 0xFFu);
        if (value == 0) {
          terminated = true;
        } else if (!terminated && value < 0x80) {
          result.push_back(static_cast<char>(value));
        } else if (!terminated && value < 0x800) {
          result.push_back(static_cast<char>(0xC0 | (value >> 6)));
          result.push_back(static_cast<char>(0x80 | (value & 0x3F)));
        } else if (!terminated) {
          result.push_back(static_cast<char>(0xE0 | (value >> 12)));
          result.push_back(static_cast<char>(0x80 | ((value >> 6) & 0x3F)));
          result.push_back(static_cast<char>(0x80 | (value & 0x3F)));
        }
      }
    }
    return result;
  }

 private:
  Reader reader_;
  std::vector<std::uint8_t>& output_;
};

struct Table {
  std::int32_t count{};
  std::int32_t offset{};
};

struct Chunk {
  std::int32_t uncompressedOffset{};
  std::int32_t uncompressedSize{};
  std::int32_t compressedOffset{};
  std::int32_t compressedSize{};
};

struct SizedChunk {
  std::uint32_t compressedSize{};
  std::uint32_t uncompressedSize{};
};

struct Summary {
  Endian endian{};
  bool fullyCompressed{};
  std::uint32_t containerChunkSize{};
  std::uint32_t containerCompressedSize{};
  std::uint32_t containerUncompressedSize{};
  std::int32_t containerChunkCount{};
  std::vector<SizedChunk> containerChunks;
  std::uint32_t packedVersion{};
  std::uint16_t engineVersion{};
  std::uint16_t licenseeVersion{};
  std::int32_t totalHeaderSize{};
  std::string folderName;
  std::uint64_t packageFlagsOffset{};
  std::uint32_t packageFlags{};
  Table names;
  Table exports;
  Table imports;
  std::int32_t dependsOffset{};
  std::int32_t importExportGuidsOffset{};
  std::int32_t importGuidsCount{};
  std::int32_t exportGuidsCount{};
  std::int32_t thumbnailTableOffset{};
  std::array<std::uint8_t, 16> guid{};
  std::int32_t generationCount{};
  std::uint32_t savedEngineVersion{};
  std::uint32_t cookedContentVersion{};
  std::uint64_t compressionFlagsOffset{};
  std::uint32_t compressionFlags{};
  std::uint64_t chunkCountOffset{};
  std::uint64_t chunkTableEndOffset{};
  std::vector<Chunk> chunks;
  std::uint32_t packageSource{};
  std::vector<std::string> additionalPackages;
  std::int32_t textureAllocationCount{};
  std::uint64_t knownSummaryBytes{};
  std::vector<std::string> sampledNames;
  std::vector<std::string> warnings;
};

std::string hex32(std::uint32_t value) {
  std::ostringstream out;
  out << "0x" << std::uppercase << std::hex << std::setw(8) << std::setfill('0') << value;
  return out.str();
}

std::string compressionName(std::uint32_t flags) {
  if ((flags & 0x4u) != 0) return "LZX";
  if ((flags & 0x2u) != 0) return "LZO";
  if ((flags & 0x1u) != 0) return "ZLIB";
  return flags == 0 ? "none" : "unknown";
}

std::int32_t checkedCount(Reader& reader, std::string_view label) {
  const auto count = reader.i32();
  if (count < 0 || static_cast<std::size_t>(count) > kMaxArrayItems) {
    throw ParseError(std::string("invalid ") + std::string(label) + " count");
  }
  return count;
}

void skipGeneration(Reader& reader) {
  (void)reader.i32();  // ExportCount
  (void)reader.i32();  // NameCount
  (void)reader.i32();  // NetObjectCount
}

bool isPhysicalOffset(const Summary& summary, std::uint64_t offset) {
  for (const auto& chunk : summary.chunks) {
    if (chunk.uncompressedOffset < 0 || chunk.uncompressedSize <= 0) continue;
    const auto begin = static_cast<std::uint64_t>(chunk.uncompressedOffset);
    const auto end = begin + static_cast<std::uint64_t>(chunk.uncompressedSize);
    if (offset >= begin && offset < end) return false;
  }
  return true;
}

void validateTable(const Reader& reader, const Table& table, std::string_view label,
                   Summary& summary) {
  if (table.count < 0 || table.offset < 0) {
    summary.warnings.emplace_back(std::string(label) + " table has a negative count or offset");
    return;
  }
  std::uint64_t logicalSize = reader.size();
  for (const auto& chunk : summary.chunks) {
    if (chunk.uncompressedOffset >= 0 && chunk.uncompressedSize >= 0) {
      logicalSize = std::max(logicalSize,
          static_cast<std::uint64_t>(chunk.uncompressedOffset) +
          static_cast<std::uint64_t>(chunk.uncompressedSize));
    }
  }
  if (table.count > 0 && static_cast<std::uint64_t>(table.offset) >= logicalSize) {
    summary.warnings.emplace_back(std::string(label) + " table offset lies beyond logical package size");
  }
}

Summary parseSummary(const fs::path& path, std::size_t nameLimit) {
  std::ifstream tagStream(path, std::ios::binary);
  std::array<std::uint8_t, 4> tagBytes{};
  tagStream.read(reinterpret_cast<char*>(tagBytes.data()), tagBytes.size());
  if (tagStream.gcount() != static_cast<std::streamsize>(tagBytes.size())) {
    throw ParseError("file is too small to be a UE3 package");
  }
  const std::uint32_t rawLittle = static_cast<std::uint32_t>(tagBytes[0]) |
      (static_cast<std::uint32_t>(tagBytes[1]) << 8) |
      (static_cast<std::uint32_t>(tagBytes[2]) << 16) |
      (static_cast<std::uint32_t>(tagBytes[3]) << 24);
  Endian endian;
  if (rawLittle == kPackageTag) {
    endian = Endian::Little;
  } else if (rawLittle == kPackageTagSwapped) {
    endian = Endian::Big;
  } else {
    throw ParseError("not a UE3 package (tag is " + hex32(rawLittle) + ")");
  }

  Reader reader(path, endian);
  Summary summary;
  summary.endian = endian;
  (void)reader.u32();
  summary.packedVersion = reader.u32();
  if (summary.packedVersion == 0x20000u || summary.packedVersion == kPackageTag) {
    summary.fullyCompressed = true;
    summary.containerChunkSize = summary.packedVersion == kPackageTag ? 0x20000u : summary.packedVersion;
    summary.containerCompressedSize = reader.u32();
    summary.containerUncompressedSize = reader.u32();
    if (summary.containerChunkSize == 0 || summary.containerUncompressedSize == 0) {
      throw ParseError("invalid fully-compressed container summary");
    }
    const auto count = (static_cast<std::uint64_t>(summary.containerUncompressedSize) +
                        summary.containerChunkSize - 1) / summary.containerChunkSize;
    if (count > kMaxArrayItems) throw ParseError("invalid fully-compressed container chunk count");
    summary.containerChunkCount = static_cast<std::int32_t>(count);
    summary.containerChunks.reserve(static_cast<std::size_t>(summary.containerChunkCount));
    std::uint64_t compressedTotal = 0;
    std::uint64_t uncompressedTotal = 0;
    for (std::int32_t i = 0; i < summary.containerChunkCount; ++i) {
      const auto compressedSize = reader.u32();
      const auto uncompressedSize = reader.u32();
      summary.containerChunks.push_back({compressedSize, uncompressedSize});
      compressedTotal += compressedSize;
      uncompressedTotal += uncompressedSize;
    }
    if (uncompressedTotal != summary.containerUncompressedSize) {
      summary.warnings.emplace_back("container chunk sizes do not sum to advertised uncompressed size");
    }
    if (compressedTotal != summary.containerCompressedSize) {
      summary.warnings.emplace_back("container chunk sizes do not sum to advertised compressed size");
    }
    summary.knownSummaryBytes = reader.position();
    return summary;
  }
  summary.engineVersion = static_cast<std::uint16_t>(summary.packedVersion & 0xFFFFu);
  summary.licenseeVersion = static_cast<std::uint16_t>(summary.packedVersion >> 16);
  summary.totalHeaderSize = reader.i32();
  summary.folderName = reader.fstring();
  summary.packageFlagsOffset = reader.position();
  summary.packageFlags = reader.u32();
  summary.names = {reader.i32(), reader.i32()};
  summary.exports = {reader.i32(), reader.i32()};
  summary.imports = {reader.i32(), reader.i32()};
  summary.dependsOffset = reader.i32();

  if (summary.engineVersion >= kVerCrossLevelReferences) {
    summary.importExportGuidsOffset = reader.i32();
    summary.importGuidsCount = reader.i32();
    summary.exportGuidsCount = reader.i32();
  }
  if (summary.engineVersion >= kVerThumbnails) summary.thumbnailTableOffset = reader.i32();
  for (auto& byte : summary.guid) byte = reader.u8();

  summary.generationCount = checkedCount(reader, "generation");
  for (std::int32_t i = 0; i < summary.generationCount; ++i) skipGeneration(reader);
  summary.savedEngineVersion = reader.u32();
  summary.cookedContentVersion = reader.u32();
  summary.compressionFlagsOffset = reader.position();
  summary.compressionFlags = reader.u32();
  summary.chunkCountOffset = reader.position();
  const auto chunkCount = checkedCount(reader, "compressed chunk");
  summary.chunks.reserve(static_cast<std::size_t>(chunkCount));
  for (std::int32_t i = 0; i < chunkCount; ++i) {
    summary.chunks.push_back({reader.i32(), reader.i32(), reader.i32(), reader.i32()});
  }
  summary.chunkTableEndOffset = reader.position();
  summary.packageSource = reader.u32();

  if (summary.engineVersion >= kVerAdditionalCookPackages) {
    const auto count = checkedCount(reader, "additional package");
    summary.additionalPackages.reserve(static_cast<std::size_t>(count));
    for (std::int32_t i = 0; i < count; ++i) summary.additionalPackages.push_back(reader.fstring());
  }

  if (summary.engineVersion >= kVerTexturePreallocation) {
    summary.textureAllocationCount = checkedCount(reader, "texture allocation");
    for (std::int32_t i = 0; i < summary.textureAllocationCount; ++i) {
      (void)reader.i32();  // SizeX
      (void)reader.i32();  // SizeY
      (void)reader.i32();  // NumMips
      (void)reader.i32();  // Format
      (void)reader.u32();  // TexCreateFlags
      const auto exportCount = checkedCount(reader, "texture allocation export");
      for (std::int32_t j = 0; j < exportCount; ++j) (void)reader.i32();
    }
  }
  summary.knownSummaryBytes = reader.position();

  validateTable(reader, summary.names, "name", summary);
  validateTable(reader, summary.exports, "export", summary);
  validateTable(reader, summary.imports, "import", summary);

  if (nameLimit > 0 && summary.names.count > 0 && summary.names.offset >= 0) {
    const auto offset = static_cast<std::uint64_t>(summary.names.offset);
    if (!isPhysicalOffset(summary, offset)) {
      summary.warnings.emplace_back("name table is inside a compressed logical region; decompression is required");
    } else if (offset >= reader.size()) {
      summary.warnings.emplace_back("name table is not physically present at its logical offset");
    } else {
      try {
        reader.seek(offset);
        const auto count = std::min<std::size_t>(nameLimit, static_cast<std::size_t>(summary.names.count));
        for (std::size_t i = 0; i < count; ++i) {
          summary.sampledNames.push_back(reader.fstring());
          (void)reader.u64();  // EObjectFlags
        }
      } catch (const ParseError& error) {
        summary.sampledNames.clear();
        summary.warnings.emplace_back(std::string("could not sample name table: ") + error.what());
      }
    }
  }
  return summary;
}

std::string escapeJson(std::string_view value) {
  std::ostringstream out;
  for (const unsigned char c : value) {
    switch (c) {
      case '"': out << "\\\""; break;
      case '\\': out << "\\\\"; break;
      case '\b': out << "\\b"; break;
      case '\f': out << "\\f"; break;
      case '\n': out << "\\n"; break;
      case '\r': out << "\\r"; break;
      case '\t': out << "\\t"; break;
      default:
        if (c < 0x20) {
          out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
        } else {
          out << c;
        }
    }
  }
  return out.str();
}

void printJson(const fs::path& path, const Summary& value) {
  std::cout << "{\n"
            << "  \"path\": \"" << escapeJson(path.string()) << "\",\n"
            << "  \"byte_order\": \"" << (value.endian == Endian::Big ? "big" : "little") << "\",\n"
            << "  \"fully_compressed\": " << (value.fullyCompressed ? "true" : "false") << ",\n"
            << "  \"package_version\": " << value.engineVersion << ",\n"
            << "  \"licensee_version\": " << value.licenseeVersion << ",\n"
            << "  \"header_size\": " << value.totalHeaderSize << ",\n"
            << "  \"folder\": \"" << escapeJson(value.folderName) << "\",\n"
            << "  \"package_flags\": \"" << hex32(value.packageFlags) << "\",\n"
            << "  \"tables\": {\"names\": [" << value.names.count << ", " << value.names.offset
            << "], \"exports\": [" << value.exports.count << ", " << value.exports.offset
            << "], \"imports\": [" << value.imports.count << ", " << value.imports.offset << "]},\n"
            << "  \"saved_engine_version\": " << value.savedEngineVersion << ",\n"
            << "  \"cooked_content_version\": " << value.cookedContentVersion << ",\n"
            << "  \"compression_flags\": \"" << hex32(value.compressionFlags) << "\",\n"
            << "  \"compression\": \"" << compressionName(value.compressionFlags) << "\",\n"
            << "  \"compressed_chunks\": [";
  for (std::size_t i = 0; i < value.chunks.size(); ++i) {
    const auto& c = value.chunks[i];
    if (i != 0) std::cout << ", ";
    std::cout << "[" << c.uncompressedOffset << ", " << c.uncompressedSize << ", "
              << c.compressedOffset << ", " << c.compressedSize << "]";
  }
  std::cout << "],\n  \"known_summary_bytes\": " << value.knownSummaryBytes << ",\n  \"sample_names\": [";
  for (std::size_t i = 0; i < value.sampledNames.size(); ++i) {
    if (i != 0) std::cout << ", ";
    std::cout << "\"" << escapeJson(value.sampledNames[i]) << "\"";
  }
  std::cout << "],\n  \"warnings\": [";
  for (std::size_t i = 0; i < value.warnings.size(); ++i) {
    if (i != 0) std::cout << ", ";
    std::cout << "\"" << escapeJson(value.warnings[i]) << "\"";
  }
  std::cout << "]\n}\n";
}

void printHuman(const fs::path& path, const Summary& value) {
  std::cout << path.string() << '\n'
            << "  byte order:       " << (value.endian == Endian::Big ? "big (Xbox 360)" : "little") << '\n'
            << "  container:        " << (value.fullyCompressed ? "fully compressed" : "standard package") << '\n';
  if (value.fullyCompressed) {
    std::cout << "  chunk size/count: " << value.containerChunkSize << " / " << value.containerChunkCount << '\n'
              << "  compressed size:  " << value.containerCompressedSize << '\n'
              << "  original size:    " << value.containerUncompressedSize << '\n'
              << "  parsed header:    " << value.knownSummaryBytes << " bytes\n";
    for (const auto& warning : value.warnings) std::cout << "  warning:          " << warning << '\n';
    return;
  }
  std::cout
            << "  package version:  " << value.engineVersion << " (licensee " << value.licenseeVersion << ")\n"
            << "  header size:      " << value.totalHeaderSize << '\n'
            << "  package flags:    " << hex32(value.packageFlags) << '\n'
            << "  names:            " << value.names.count << " @ " << value.names.offset << '\n'
            << "  exports:          " << value.exports.count << " @ " << value.exports.offset << '\n'
            << "  imports:          " << value.imports.count << " @ " << value.imports.offset << '\n'
            << "  engine/content:   " << value.savedEngineVersion << " / " << value.cookedContentVersion << '\n'
            << "  compression:      " << compressionName(value.compressionFlags) << " "
            << hex32(value.compressionFlags) << ", " << value.chunks.size() << " chunk(s)\n"
            << "  parsed summary:   " << value.knownSummaryBytes << " bytes\n";
  if (!value.sampledNames.empty()) {
    std::cout << "  sample names:     ";
    for (std::size_t i = 0; i < value.sampledNames.size(); ++i) {
      if (i != 0) std::cout << ", ";
      std::cout << value.sampledNames[i];
    }
    std::cout << '\n';
  }
  for (const auto& warning : value.warnings) std::cout << "  warning:          " << warning << '\n';
}

void usage() {
  std::cout << "Usage:\n"
            << "  judgment-package-probe [--json] [--names N] <package> [package...]\n"
            << "  judgment-package-probe --inventory <directory>\n"
            << "  judgment-package-probe --decompress-container <input> <output>\n"
            << "  judgment-package-probe --decompress-package <input> <output>\n"
            << "  judgment-package-probe --extract-bulk <input> <offset> <size-on-disk> <element-count> <flags> <output.bin>\n"
            << "  judgment-package-probe --detile-xbox360 <input.bin> <width-pixels> <height-pixels> <block-pixels> <bytes-per-block> <endian-unit> <output.bin>\n"
            << "  judgment-package-probe --decode-dxt1-bmp <input.bin> <width-pixels> <height-pixels> <output.bmp>\n"
            << "  judgment-package-probe --manifest <uncompressed-package> <output.json>\n"
            << "  judgment-package-probe --extract-xma <uncompressed-package> <export-index> <output.xma>\n"
            << "  judgment-package-probe --convert-audio-fixture <uncompressed-package> <export-index> <pc.ogg> <output.upk>\n"
            << "  judgment-package-probe --convert-audio-package <uncompressed-package> <ogg-directory> <output.upk>\n"
            << "  judgment-package-probe --convert-texture-fixture <uncompressed-package> <zero-based-export-index> <Textures.tfc> <output.upk>\n"
            << "  judgment-package-probe --convert-texture-fixture-full-mips <uncompressed-package> <zero-based-export-index> <Textures.tfc> <output.upk>\n"
            << "  judgment-package-probe --make-vorbis-time-test-fixture <audio-fixture.upk> <TestSounds.upk>\n"
            << "  judgment-package-probe --convert-guid-cache <input> <output.upk>\n";
}

int decompressContainer(const fs::path& input, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (!summary.fullyCompressed) {
    std::cerr << input.string() << ": not a fully-compressed UE3 container\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  std::ifstream source(input, std::ios::binary);
  source.seekg(static_cast<std::streamoff>(summary.knownSummaryBytes), std::ios::beg);
  if (!source) {
    std::cerr << input.string() << ": could not seek to container payload\n";
    return 1;
  }
  std::error_code directoryError;
  if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
  if (directoryError) {
    std::cerr << output.string() << ": could not create output directory: "
              << directoryError.message() << '\n';
    return 1;
  }
  std::ofstream destination(output, std::ios::binary | std::ios::trunc);
  if (!destination) {
    std::cerr << output.string() << ": could not create output file\n";
    return 1;
  }

  std::uint64_t written = 0;
  for (std::size_t i = 0; i < summary.containerChunks.size(); ++i) {
    const auto& chunk = summary.containerChunks[i];
    std::vector<std::uint8_t> compressed(chunk.compressedSize);
    source.read(reinterpret_cast<char*>(compressed.data()),
                static_cast<std::streamsize>(compressed.size()));
    if (!source) {
      std::cerr << input.string() << ": truncated container payload at chunk " << i << '\n';
      destination.close();
      fs::remove(output);
      return 1;
    }
    std::vector<std::uint8_t> uncompressed;
    std::string error;
    if (!decompressXMemLzx(compressed, chunk.uncompressedSize, uncompressed, error)) {
      std::cerr << input.string() << ": chunk " << i << ": " << error << '\n';
      destination.close();
      fs::remove(output);
      return 1;
    }
    destination.write(reinterpret_cast<const char*>(uncompressed.data()),
                      static_cast<std::streamsize>(uncompressed.size()));
    if (!destination) {
      std::cerr << output.string() << ": write failed\n";
      destination.close();
      fs::remove(output);
      return 1;
    }
    written += uncompressed.size();
  }
  destination.close();
  if (written != summary.containerUncompressedSize) {
    std::cerr << output.string() << ": reconstructed size mismatch\n";
    fs::remove(output);
    return 1;
  }
  std::cout << "Decompressed " << summary.containerChunks.size() << " LZX chunk(s), "
            << written << " bytes -> " << output.string() << '\n';
  return 0;
}

std::uint32_t readMemoryU32(std::span<const std::uint8_t> data, std::size_t& offset,
                            Endian endian) {
  if (data.size() - offset < 4) throw ParseError("truncated compressed-wrapper header");
  std::uint32_t value = 0;
  if (endian == Endian::Big) {
    for (int i = 0; i < 4; ++i) value = (value << 8) | data[offset + static_cast<std::size_t>(i)];
  } else {
    for (int i = 3; i >= 0; --i) value = (value << 8) | data[offset + static_cast<std::size_t>(i)];
  }
  offset += 4;
  return value;
}

void writeMemoryU32(std::vector<std::uint8_t>& data, std::size_t offset,
                    std::uint32_t value, Endian endian) {
  if (data.size() - offset < 4) throw ParseError("header patch lies outside the buffer");
  for (std::size_t i = 0; i < 4; ++i) {
    const auto shift = endian == Endian::Big ? (3 - i) * 8 : i * 8;
    data[offset + i] = static_cast<std::uint8_t>(value >> shift);
  }
}

enum class SerializedCompression { Lzx, Lzo };

bool decompressSerializedBlob(std::span<const std::uint8_t> blob,
                              std::size_t expectedOutputSize,
                              std::vector<std::uint8_t>& output,
                              std::string& error,
                              SerializedCompression compression = SerializedCompression::Lzx) {
  output.clear();
  if (blob.size() < 16) {
    error = "UE3 compressed wrapper is too small";
    return false;
  }
  Endian endian;
  if (blob[0] == 0x9E && blob[1] == 0x2A && blob[2] == 0x83 && blob[3] == 0xC1) {
    endian = Endian::Big;
  } else if (blob[0] == 0xC1 && blob[1] == 0x83 && blob[2] == 0x2A && blob[3] == 0x9E) {
    endian = Endian::Little;
  } else {
    error = "UE3 compressed wrapper has an invalid package tag";
    return false;
  }

  try {
    std::size_t position = 0;
    (void)readMemoryU32(blob, position, endian);
    const auto chunkSize = readMemoryU32(blob, position, endian);
    const auto aggregateCompressed = readMemoryU32(blob, position, endian);
    const auto aggregateUncompressed = readMemoryU32(blob, position, endian);
    if (chunkSize == 0 || aggregateUncompressed != expectedOutputSize) {
      error = "UE3 compressed wrapper size metadata does not match its package chunk";
      return false;
    }
    const std::size_t count = (static_cast<std::size_t>(aggregateUncompressed) + chunkSize - 1) /
                              chunkSize;
    if (count > kMaxArrayItems || blob.size() - position < count * 8) {
      error = "UE3 compressed wrapper has an invalid chunk table";
      return false;
    }
    std::vector<SizedChunk> chunks;
    chunks.reserve(count);
    std::uint64_t compressedTotal = 0;
    std::uint64_t uncompressedTotal = 0;
    for (std::size_t i = 0; i < count; ++i) {
      const auto compressed = readMemoryU32(blob, position, endian);
      const auto uncompressed = readMemoryU32(blob, position, endian);
      chunks.push_back({compressed, uncompressed});
      compressedTotal += compressed;
      uncompressedTotal += uncompressed;
    }
    if (compressedTotal != aggregateCompressed || uncompressedTotal != aggregateUncompressed ||
        compressedTotal > blob.size() - position) {
      error = "UE3 compressed wrapper aggregate sizes are inconsistent";
      return false;
    }
    output.reserve(expectedOutputSize);
    for (std::size_t i = 0; i < chunks.size(); ++i) {
      const auto& chunk = chunks[i];
      std::vector<std::uint8_t> decoded;
      std::string chunkError;
      if (compression == SerializedCompression::Lzx) {
        if (!decompressXMemLzx(blob.subspan(position, chunk.compressedSize),
                               chunk.uncompressedSize, decoded, chunkError)) {
          error = "inner LZX chunk " + std::to_string(i) + ": " + chunkError;
          output.clear();
          return false;
        }
      } else {
#if defined(HAVE_GEARS3_LZOPRO)
        decoded.resize(chunk.uncompressedSize);
        lzo_uint decodedSize = static_cast<lzo_uint>(decoded.size());
        const auto compressedChunk = blob.subspan(position, chunk.compressedSize);
        const int result = lzopro_lzo1x_decompress_safe(
            compressedChunk.data(), static_cast<lzo_uint>(compressedChunk.size()),
            decoded.data(), &decodedSize, nullptr);
        if (result != LZO_E_OK || decodedSize != chunk.uncompressedSize) {
          error = "inner LZO chunk " + std::to_string(i) + " failed (code " +
                  std::to_string(result) + ", produced " + std::to_string(decodedSize) +
                  " of " + std::to_string(chunk.uncompressedSize) + " bytes)";
          output.clear();
          return false;
        }
#else
        error = "LZO support was not built (Gears 3 lzopro library not found)";
        output.clear();
        return false;
#endif
      }
      output.insert(output.end(), decoded.begin(), decoded.end());
      position += chunk.compressedSize;
    }
  } catch (const std::exception& exception) {
    error = exception.what();
    output.clear();
    return false;
  }
  return output.size() == expectedOutputSize;
}

int extractBulkPayload(const fs::path& input, std::uint64_t offset,
                       std::uint64_t sizeOnDisk, std::uint64_t elementCount,
                       std::uint32_t flags, const fs::path& outputPath) {
  if (fs::exists(outputPath)) {
    std::cerr << outputPath.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  if ((flags & 1u) != 0) {
    std::cerr << input.string() << ": bulk-data header refers to a separate file\n";
    return 1;
  }
  if (sizeOnDisk > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
      elementCount > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
    std::cerr << input.string() << ": bulk payload is too large for this build\n";
    return 1;
  }
  const auto inputSize = fs::file_size(input);
  if (offset > inputSize || sizeOnDisk > inputSize - offset) {
    std::cerr << input.string() << ": bulk payload lies outside the input file\n";
    return 1;
  }

  std::vector<std::uint8_t> stored(static_cast<std::size_t>(sizeOnDisk));
  std::ifstream source(input, std::ios::binary);
  source.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
  if (!source || (sizeOnDisk > 0 &&
                  !source.read(reinterpret_cast<char*>(stored.data()),
                               static_cast<std::streamsize>(stored.size())))) {
    std::cerr << input.string() << ": could not read bulk payload\n";
    return 1;
  }

  constexpr std::uint32_t compressedZlib = 1u << 1;
  constexpr std::uint32_t compressedLzo = 1u << 4;
  constexpr std::uint32_t compressedLzx = 1u << 7;
  const auto compressionFlags = flags & (compressedZlib | compressedLzo | compressedLzx);
  std::vector<std::uint8_t> decoded;
  if (compressionFlags == 0) {
    if (sizeOnDisk != elementCount) {
      std::cerr << input.string() << ": uncompressed bulk size differs from element count\n";
      return 1;
    }
    decoded = std::move(stored);
  } else if (compressionFlags == compressedLzo || compressionFlags == compressedLzx) {
    std::string error;
    const auto compression = compressionFlags == compressedLzo
                                 ? SerializedCompression::Lzo
                                 : SerializedCompression::Lzx;
    if (!decompressSerializedBlob(stored, static_cast<std::size_t>(elementCount), decoded,
                                  error, compression)) {
      std::cerr << input.string() << ": bulk decompression failed: " << error << '\n';
      return 1;
    }
  } else {
    std::cerr << input.string() << ": unsupported or ambiguous bulk compression flags "
              << hex32(compressionFlags) << '\n';
    return 1;
  }

  std::error_code directoryError;
  if (!outputPath.parent_path().empty()) {
    fs::create_directories(outputPath.parent_path(), directoryError);
  }
  std::ofstream output(outputPath, std::ios::binary | std::ios::trunc);
  if (!output || directoryError ||
      (decoded.size() > 0 &&
       !output.write(reinterpret_cast<const char*>(decoded.data()),
                     static_cast<std::streamsize>(decoded.size())))) {
    std::cerr << outputPath.string() << ": could not write extracted bulk payload\n";
    std::error_code removeError;
    fs::remove(outputPath, removeError);
    return 1;
  }
  std::cout << "Extracted " << decoded.size() << " bulk byte(s) from " << input.string()
            << " -> " << outputPath.string() << '\n';
  return 0;
}

std::uint32_t xbox360TiledX(std::uint32_t blockOffset, std::uint32_t widthInBlocks,
                           std::uint32_t bytesPerBlock) {
  const auto alignedWidth = (widthInBlocks + 31u) & ~31u;
  const auto logBpp = (bytesPerBlock >> 2u) +
                      ((bytesPerBlock >> 1u) >> (bytesPerBlock >> 2u));
  const auto offsetByte = blockOffset << logBpp;
  const auto offsetTile = ((offsetByte & ~0xFFFu) >> 3u) +
                          ((offsetByte & 0x700u) >> 2u) + (offsetByte & 0x3Fu);
  const auto offsetMacro = offsetTile >> (7u + logBpp);
  const auto macroX = (offsetMacro % (alignedWidth >> 5u)) << 2u;
  const auto tile = (((offsetTile >> (5u + logBpp)) & 2u) + (offsetByte >> 6u)) & 3u;
  const auto macro = (macroX + tile) << 3u;
  const auto micro = ((((offsetTile >> 1u) & ~0xFu) + (offsetTile & 0xFu)) &
                      ((bytesPerBlock << 3u) - 1u)) >> logBpp;
  return macro + micro;
}

std::uint32_t xbox360TiledY(std::uint32_t blockOffset, std::uint32_t widthInBlocks,
                           std::uint32_t bytesPerBlock) {
  const auto alignedWidth = (widthInBlocks + 31u) & ~31u;
  const auto logBpp = (bytesPerBlock >> 2u) +
                      ((bytesPerBlock >> 1u) >> (bytesPerBlock >> 2u));
  const auto offsetByte = blockOffset << logBpp;
  const auto offsetTile = ((offsetByte & ~0xFFFu) >> 3u) +
                          ((offsetByte & 0x700u) >> 2u) + (offsetByte & 0x3Fu);
  const auto offsetMacro = offsetTile >> (7u + logBpp);
  const auto macroY = (offsetMacro / (alignedWidth >> 5u)) << 2u;
  const auto tile = ((offsetTile >> (6u + logBpp)) & 1u) +
                    ((offsetByte & 0x800u) >> 10u);
  const auto macro = (macroY + tile) << 3u;
  const auto micro = (((offsetTile & (((bytesPerBlock << 6u) - 1u) & ~0x1Fu)) +
                       ((offsetTile & 0xFu) << 1u)) >> (3u + logBpp)) & ~1u;
  return macro + micro + ((offsetTile & 0x10u) >> 4u);
}

int detileXbox360(const fs::path& input, std::uint32_t widthPixels,
                  std::uint32_t heightPixels, std::uint32_t blockPixels,
                  std::uint32_t bytesPerBlock, std::uint32_t endianUnit,
                  const fs::path& outputPath) {
  if (fs::exists(outputPath)) {
    std::cerr << outputPath.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  if (widthPixels == 0 || heightPixels == 0 || blockPixels == 0 ||
      (bytesPerBlock != 1 && bytesPerBlock != 2 && bytesPerBlock != 4 &&
       bytesPerBlock != 8 && bytesPerBlock != 16) ||
      (endianUnit != 1 && endianUnit != 2 && endianUnit != 4 && endianUnit != 8)) {
    std::cerr << input.string() << ": invalid Xbox 360 detile geometry\n";
    return 1;
  }
  const auto inputSize = fs::file_size(input);
  if (inputSize == 0 || inputSize % bytesPerBlock != 0 || inputSize % endianUnit != 0 ||
      inputSize > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
    std::cerr << input.string() << ": tiled input size is incompatible with its block geometry\n";
    return 1;
  }
  const auto widthInBlocks = (widthPixels + blockPixels - 1u) / blockPixels;
  const auto heightInBlocks = (heightPixels + blockPixels - 1u) / blockPixels;
  const auto outputBlockCount = static_cast<std::uint64_t>(widthInBlocks) * heightInBlocks;
  const auto outputSize = outputBlockCount * bytesPerBlock;
  if (outputSize > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
    std::cerr << input.string() << ": linear texture output is too large\n";
    return 1;
  }

  std::vector<std::uint8_t> tiled(static_cast<std::size_t>(inputSize));
  std::ifstream source(input, std::ios::binary);
  if (!source.read(reinterpret_cast<char*>(tiled.data()),
                   static_cast<std::streamsize>(tiled.size()))) {
    std::cerr << input.string() << ": could not read tiled texture data\n";
    return 1;
  }
  if (endianUnit > 1) {
    for (std::size_t position = 0; position < tiled.size(); position += endianUnit) {
      std::reverse(tiled.begin() + static_cast<std::ptrdiff_t>(position),
                   tiled.begin() + static_cast<std::ptrdiff_t>(position + endianUnit));
    }
  }

  std::vector<std::uint8_t> linear(static_cast<std::size_t>(outputSize));
  std::vector<bool> written(static_cast<std::size_t>(outputBlockCount));
  std::size_t mappedBlocks = 0;
  const auto physicalBlockCount = inputSize / bytesPerBlock;
  if (physicalBlockCount > std::numeric_limits<std::uint32_t>::max()) {
    std::cerr << input.string() << ": tiled texture has too many physical blocks\n";
    return 1;
  }
  for (std::uint32_t sourceBlock = 0;
       sourceBlock < static_cast<std::uint32_t>(physicalBlockCount); ++sourceBlock) {
    const auto x = xbox360TiledX(sourceBlock, widthInBlocks, bytesPerBlock);
    const auto y = xbox360TiledY(sourceBlock, widthInBlocks, bytesPerBlock);
    if (x >= widthInBlocks || y >= heightInBlocks) continue;
    const auto destinationBlock = static_cast<std::size_t>(y) * widthInBlocks + x;
    if (written[destinationBlock]) {
      std::cerr << input.string() << ": Xbox 360 detile mapping produced a duplicate block\n";
      return 1;
    }
    written[destinationBlock] = true;
    ++mappedBlocks;
    const auto sourceOffset = static_cast<std::size_t>(sourceBlock) * bytesPerBlock;
    const auto destinationOffset = destinationBlock * bytesPerBlock;
    std::copy_n(tiled.begin() + static_cast<std::ptrdiff_t>(sourceOffset), bytesPerBlock,
                linear.begin() + static_cast<std::ptrdiff_t>(destinationOffset));
  }
  if (mappedBlocks != outputBlockCount ||
      std::find(written.begin(), written.end(), false) != written.end()) {
    std::cerr << input.string() << ": Xbox 360 allocation does not cover every linear block ("
              << mappedBlocks << " of " << outputBlockCount << ")\n";
    return 1;
  }

  std::ofstream output(outputPath, std::ios::binary | std::ios::trunc);
  if (!output || !output.write(reinterpret_cast<const char*>(linear.data()),
                               static_cast<std::streamsize>(linear.size()))) {
    std::cerr << outputPath.string() << ": could not write detiled texture data\n";
    std::error_code removeError;
    fs::remove(outputPath, removeError);
    return 1;
  }
  std::cout << "Detiled " << mappedBlocks << " Xbox 360 block(s), " << tiled.size()
            << " physical byte(s) -> " << linear.size() << " linear byte(s): "
            << outputPath.string() << '\n';
  return 0;
}

int decodeDxt1Bmp(const fs::path& input, std::uint32_t width,
                  std::uint32_t height, const fs::path& outputPath) {
  if (fs::exists(outputPath)) {
    std::cerr << outputPath.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  if (width == 0 || height == 0) {
    std::cerr << input.string() << ": DXT1 dimensions must be positive\n";
    return 1;
  }
  const auto blocksX = (static_cast<std::uint64_t>(width) + 3u) / 4u;
  const auto blocksY = (static_cast<std::uint64_t>(height) + 3u) / 4u;
  const auto expectedSize = blocksX * blocksY * 8u;
  if (fs::file_size(input) != expectedSize) {
    std::cerr << input.string() << ": DXT1 byte count does not match its dimensions\n";
    return 1;
  }
  std::vector<std::uint8_t> dxt(static_cast<std::size_t>(expectedSize));
  std::ifstream source(input, std::ios::binary);
  if (!source.read(reinterpret_cast<char*>(dxt.data()),
                   static_cast<std::streamsize>(dxt.size()))) {
    std::cerr << input.string() << ": could not read DXT1 data\n";
    return 1;
  }
  const auto pixelBytes = static_cast<std::uint64_t>(width) * height * 4u;
  if (pixelBytes > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
      pixelBytes > std::numeric_limits<std::uint32_t>::max() - 54u) {
    std::cerr << input.string() << ": decoded bitmap is too large\n";
    return 1;
  }
  std::vector<std::uint8_t> pixels(static_cast<std::size_t>(pixelBytes));
  struct Color {
    std::uint8_t r{};
    std::uint8_t g{};
    std::uint8_t b{};
    std::uint8_t a{};
  };
  const auto expand565 = [](std::uint16_t value) {
    Color color;
    color.r = static_cast<std::uint8_t>((((value >> 11u) & 31u) * 255u + 15u) / 31u);
    color.g = static_cast<std::uint8_t>((((value >> 5u) & 63u) * 255u + 31u) / 63u);
    color.b = static_cast<std::uint8_t>(((value & 31u) * 255u + 15u) / 31u);
    color.a = 255;
    return color;
  };
  std::size_t sourceOffset = 0;
  for (std::uint32_t blockY = 0; blockY < blocksY; ++blockY) {
    for (std::uint32_t blockX = 0; blockX < blocksX; ++blockX) {
      const auto color0 = static_cast<std::uint16_t>(
          dxt[sourceOffset] | (static_cast<std::uint16_t>(dxt[sourceOffset + 1]) << 8u));
      const auto color1 = static_cast<std::uint16_t>(
          dxt[sourceOffset + 2] |
          (static_cast<std::uint16_t>(dxt[sourceOffset + 3]) << 8u));
      std::array<Color, 4> palette{expand565(color0), expand565(color1), {}, {}};
      if (color0 > color1) {
        palette[2] = {static_cast<std::uint8_t>((2u * palette[0].r + palette[1].r) / 3u),
                      static_cast<std::uint8_t>((2u * palette[0].g + palette[1].g) / 3u),
                      static_cast<std::uint8_t>((2u * palette[0].b + palette[1].b) / 3u), 255};
        palette[3] = {static_cast<std::uint8_t>((palette[0].r + 2u * palette[1].r) / 3u),
                      static_cast<std::uint8_t>((palette[0].g + 2u * palette[1].g) / 3u),
                      static_cast<std::uint8_t>((palette[0].b + 2u * palette[1].b) / 3u), 255};
      } else {
        palette[2] = {static_cast<std::uint8_t>((palette[0].r + palette[1].r) / 2u),
                      static_cast<std::uint8_t>((palette[0].g + palette[1].g) / 2u),
                      static_cast<std::uint8_t>((palette[0].b + palette[1].b) / 2u), 255};
        palette[3] = {0, 0, 0, 0};
      }
      const auto indices = static_cast<std::uint32_t>(dxt[sourceOffset + 4]) |
                           (static_cast<std::uint32_t>(dxt[sourceOffset + 5]) << 8u) |
                           (static_cast<std::uint32_t>(dxt[sourceOffset + 6]) << 16u) |
                           (static_cast<std::uint32_t>(dxt[sourceOffset + 7]) << 24u);
      for (std::uint32_t y = 0; y < 4; ++y) {
        for (std::uint32_t x = 0; x < 4; ++x) {
          const auto pixelX = blockX * 4u + x;
          const auto pixelY = blockY * 4u + y;
          if (pixelX >= width || pixelY >= height) continue;
          const auto& color = palette[(indices >> (2u * (y * 4u + x))) & 3u];
          const auto destination =
              (static_cast<std::size_t>(pixelY) * width + pixelX) * 4u;
          pixels[destination] = color.b;
          pixels[destination + 1] = color.g;
          pixels[destination + 2] = color.r;
          pixels[destination + 3] = color.a;
        }
      }
      sourceOffset += 8;
    }
  }

  std::vector<std::uint8_t> bitmap;
  bitmap.reserve(54u + pixels.size());
  bitmap.push_back('B');
  bitmap.push_back('M');
  appendLittle32(bitmap, static_cast<std::uint32_t>(54u + pixels.size()));
  appendLittle16(bitmap, 0);
  appendLittle16(bitmap, 0);
  appendLittle32(bitmap, 54);
  appendLittle32(bitmap, 40);
  appendLittle32(bitmap, width);
  appendLittle32(bitmap, static_cast<std::uint32_t>(-static_cast<std::int32_t>(height)));
  appendLittle16(bitmap, 1);
  appendLittle16(bitmap, 32);
  appendLittle32(bitmap, 0);
  appendLittle32(bitmap, static_cast<std::uint32_t>(pixels.size()));
  appendLittle32(bitmap, 2835);
  appendLittle32(bitmap, 2835);
  appendLittle32(bitmap, 0);
  appendLittle32(bitmap, 0);
  bitmap.insert(bitmap.end(), pixels.begin(), pixels.end());
  std::ofstream output(outputPath, std::ios::binary | std::ios::trunc);
  if (!output || !output.write(reinterpret_cast<const char*>(bitmap.data()),
                               static_cast<std::streamsize>(bitmap.size()))) {
    std::cerr << outputPath.string() << ": could not write decoded bitmap\n";
    std::error_code removeError;
    fs::remove(outputPath, removeError);
    return 1;
  }
  std::cout << "Decoded " << width << 'x' << height << " DXT1 -> "
            << outputPath.string() << '\n';
  return 0;
}

int decompressPackage(const fs::path& input, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || summary.chunks.empty() ||
      (summary.compressionFlags & 0x4u) == 0) {
    std::cerr << input.string() << ": not an ordinary LZX-compressed UE3 package\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  const auto& firstChunk = summary.chunks.front();
  if (firstChunk.compressedOffset <= 0 || firstChunk.uncompressedOffset < 0 ||
      summary.chunkTableEndOffset > static_cast<std::uint64_t>(firstChunk.compressedOffset)) {
    std::cerr << input.string() << ": invalid first compressed-chunk boundary\n";
    return 1;
  }

  std::ifstream source(input, std::ios::binary);
  std::vector<std::uint8_t> header(static_cast<std::size_t>(firstChunk.compressedOffset));
  source.read(reinterpret_cast<char*>(header.data()), static_cast<std::streamsize>(header.size()));
  if (!source) {
    std::cerr << input.string() << ": could not read the physical package header\n";
    return 1;
  }
  try {
    writeMemoryU32(header, static_cast<std::size_t>(summary.packageFlagsOffset),
                   summary.packageFlags & ~0x02000000u, summary.endian);
    writeMemoryU32(header, static_cast<std::size_t>(summary.compressionFlagsOffset), 0, summary.endian);
    writeMemoryU32(header, static_cast<std::size_t>(summary.chunkCountOffset), 0, summary.endian);
    header.erase(header.begin() + static_cast<std::ptrdiff_t>(summary.chunkCountOffset + 4),
                 header.begin() + static_cast<std::ptrdiff_t>(summary.chunkTableEndOffset));
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (header.size() != static_cast<std::size_t>(firstChunk.uncompressedOffset)) {
    std::cerr << input.string() << ": rewritten header size " << header.size()
              << " does not meet first logical chunk at " << firstChunk.uncompressedOffset << '\n';
    return 1;
  }

  std::error_code directoryError;
  if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
  std::ofstream destination(output, std::ios::binary | std::ios::trunc);
  if (!destination || directoryError) {
    std::cerr << output.string() << ": could not create output\n";
    return 1;
  }
  destination.write(reinterpret_cast<const char*>(header.data()),
                    static_cast<std::streamsize>(header.size()));

  std::uint64_t decodedBytes = 0;
  for (std::size_t i = 0; i < summary.chunks.size(); ++i) {
    const auto& chunk = summary.chunks[i];
    if (chunk.compressedOffset < 0 || chunk.compressedSize <= 0 ||
        chunk.uncompressedOffset < 0 || chunk.uncompressedSize <= 0) {
      std::cerr << input.string() << ": invalid package chunk " << i << '\n';
      destination.close();
      fs::remove(output);
      return 1;
    }
    std::vector<std::uint8_t> compressed(static_cast<std::size_t>(chunk.compressedSize));
    source.clear();
    source.seekg(chunk.compressedOffset, std::ios::beg);
    source.read(reinterpret_cast<char*>(compressed.data()),
                static_cast<std::streamsize>(compressed.size()));
    if (!source) {
      std::cerr << input.string() << ": could not read package chunk " << i << '\n';
      destination.close();
      fs::remove(output);
      return 1;
    }
    std::vector<std::uint8_t> decoded;
    std::string error;
    if (!decompressSerializedBlob(compressed, static_cast<std::size_t>(chunk.uncompressedSize),
                                  decoded, error)) {
      std::cerr << input.string() << ": package chunk " << i << ": " << error << '\n';
      destination.close();
      fs::remove(output);
      return 1;
    }
    destination.seekp(chunk.uncompressedOffset, std::ios::beg);
    destination.write(reinterpret_cast<const char*>(decoded.data()),
                      static_cast<std::streamsize>(decoded.size()));
    if (!destination) {
      std::cerr << output.string() << ": write failed\n";
      destination.close();
      fs::remove(output);
      return 1;
    }
    decodedBytes += decoded.size();
  }
  destination.close();
  std::cout << "Reconstructed " << summary.chunks.size() << " package chunk(s), "
            << decodedBytes << " decoded bytes -> " << output.string() << '\n';
  return 0;
}

struct NameRef {
  std::int32_t index{};
  std::int32_t number{};
};

void appendNameRef(std::vector<std::uint8_t>& bytes, NameRef value) {
  appendLittle32(bytes, static_cast<std::uint32_t>(value.index));
  appendLittle32(bytes, static_cast<std::uint32_t>(value.number));
}

struct ManifestName {
  std::string value;
  std::uint64_t flags{};
};

struct ManifestImport {
  NameRef classPackage;
  NameRef className;
  std::int32_t outerIndex{};
  NameRef objectName;
};

struct ManifestExport {
  std::int32_t classIndex{};
  std::int32_t superIndex{};
  std::int32_t outerIndex{};
  NameRef objectName;
  std::int32_t archetypeIndex{};
  std::uint64_t objectFlags{};
  std::int32_t serialSize{};
  std::int32_t serialOffset{};
  std::uint32_t exportFlags{};
  std::vector<std::int32_t> generationNetObjectCount;
  std::array<std::uint8_t, 16> packageGuid{};
  std::uint32_t packageFlags{};
};

struct PackagePayloadAnalysis {
  bool examined{};
  bool structurallyCompatible{};
  std::int32_t netIndex{};
  NameRef propertyTerminator{};
  std::uint64_t bytesConsumed{};
  std::string error;
};

struct GuidCachePayloadAnalysis {
  bool examined{};
  bool structurallyCompatible{};
  std::int32_t netIndex{};
  NameRef propertyTerminator{};
  std::int32_t entryCount{};
  std::size_t invalidNameReferences{};
  std::uint64_t bytesConsumed{};
  std::string error;
};

struct ObjectReferencerPayloadAnalysis {
  bool examined{};
  bool structurallyCompatible{};
  std::int32_t netIndex{};
  NameRef propertyName{};
  NameRef propertyType{};
  std::int32_t propertySize{};
  std::int32_t arrayIndex{};
  std::int32_t referencedObjectCount{};
  std::size_t invalidObjectReferences{};
  NameRef propertyTerminator{};
  std::uint64_t bytesConsumed{};
  std::string error;
};

struct BulkDataAnalysis {
  std::uint32_t flags{};
  std::int32_t elementCount{};
  std::int32_t sizeOnDisk{};
  std::int32_t offsetInFile{};
  bool inlinePayload{};
};

struct TaggedPropertyAnalysis {
  NameRef name{};
  NameRef type{};
  std::int32_t size{};
  std::int32_t arrayIndex{};
  NameRef extraName{};
  bool hasExtraName{};
  std::uint32_t boolValue{};
  bool hasBoolValue{};
  std::int32_t intValue{};
  bool hasIntValue{};
  NameRef nameValue{};
  bool hasNameValue{};
  std::uint8_t byteValue{};
  bool hasByteValue{};
  std::uint64_t dataOffset{};
};

struct Texture2DMipAnalysis {
  BulkDataAnalysis bulkData;
  std::int32_t sizeX{};
  std::int32_t sizeY{};
};

struct Texture2DPayloadAnalysis {
  bool examined{};
  bool structurallyValid{};
  std::int32_t netIndex{};
  std::size_t taggedPropertyCount{};
  NameRef propertyTerminator{};
  std::vector<TaggedPropertyAnalysis> taggedProperties;
  BulkDataAnalysis sourceArt;
  std::vector<Texture2DMipAnalysis> mips;
  std::array<std::uint8_t, 16> textureFileCacheGuid{};
  std::vector<Texture2DMipAnalysis> cachedPvrtcMips;
  std::uint64_t bytesConsumed{};
  std::string error;
};

struct SoundNodeWavePayloadAnalysis {
  bool examined{};
  bool structurallyValid{};
  std::int32_t netIndex{};
  std::size_t taggedPropertyCount{};
  NameRef propertyTerminator{};
  std::vector<TaggedPropertyAnalysis> taggedProperties;
  std::vector<BulkDataAnalysis> bulkData;
  std::uint64_t bytesConsumed{};
  std::string error;
};

NameRef readNameRef(Reader& reader) { return {reader.i32(), reader.i32()}; }

NameRef rewriteNameRef(LittleEndianRewriter& rewriter) {
  return {rewriter.i32(), rewriter.i32()};
}

std::string manifestHex64(std::uint64_t value) {
  std::ostringstream out;
  out << "0x" << std::uppercase << std::hex << std::setw(16) << std::setfill('0') << value;
  return out.str();
}

std::string guidString(const std::array<std::uint8_t, 16>& guid) {
  std::ostringstream out;
  out << std::hex << std::uppercase << std::setfill('0');
  for (std::size_t i = 0; i < guid.size(); ++i) {
    if (i == 4 || i == 6 || i == 8 || i == 10) out << '-';
    out << std::setw(2) << static_cast<unsigned>(guid[i]);
  }
  return out.str();
}

class ManifestResolver {
 public:
  ManifestResolver(std::string packageName, const std::vector<ManifestName>& names,
                   const std::vector<ManifestImport>& imports,
                   const std::vector<ManifestExport>& exports)
      : packageName_(std::move(packageName)), names_(names), imports_(imports), exports_(exports) {}

  std::string name(NameRef ref) const {
    if (ref.index < 0 || static_cast<std::size_t>(ref.index) >= names_.size()) {
      return "<invalid-name:" + std::to_string(ref.index) + ">";
    }
    std::string result = names_[static_cast<std::size_t>(ref.index)].value;
    if (ref.number != 0) result += "_" + std::to_string(ref.number - 1);
    return result;
  }

  std::string resourceName(std::int32_t packageIndex) const {
    if (packageIndex > 0 && static_cast<std::size_t>(packageIndex) <= exports_.size()) {
      return name(exports_[static_cast<std::size_t>(packageIndex - 1)].objectName);
    }
    if (packageIndex < 0 && static_cast<std::size_t>(-packageIndex) <= imports_.size()) {
      return name(imports_[static_cast<std::size_t>(-packageIndex - 1)].objectName);
    }
    return packageIndex == 0 ? "Class" : "<invalid-resource:" + std::to_string(packageIndex) + ">";
  }

  std::string importPath(std::size_t index) const {
    std::vector<std::int32_t> stack;
    return resourcePath(-static_cast<std::int32_t>(index) - 1, stack);
  }

  std::string exportPath(std::size_t index) const {
    std::vector<std::int32_t> stack;
    return resourcePath(static_cast<std::int32_t>(index) + 1, stack);
  }

 private:
  std::string resourcePath(std::int32_t packageIndex, std::vector<std::int32_t>& stack) const {
    if (std::find(stack.begin(), stack.end(), packageIndex) != stack.end()) return "<outer-cycle>";
    stack.push_back(packageIndex);
    std::string objectName;
    std::int32_t outer = 0;
    bool isExport = false;
    if (packageIndex > 0 && static_cast<std::size_t>(packageIndex) <= exports_.size()) {
      const auto& value = exports_[static_cast<std::size_t>(packageIndex - 1)];
      objectName = name(value.objectName);
      outer = value.outerIndex;
      isExport = true;
    } else if (packageIndex < 0 && static_cast<std::size_t>(-packageIndex) <= imports_.size()) {
      const auto& value = imports_[static_cast<std::size_t>(-packageIndex - 1)];
      objectName = name(value.objectName);
      outer = value.outerIndex;
    } else {
      stack.pop_back();
      return "<invalid-resource:" + std::to_string(packageIndex) + ">";
    }
    std::string result;
    if (outer == 0) {
      result = isExport ? packageName_ + "." + objectName : objectName;
    } else {
      result = resourcePath(outer, stack) + "." + objectName;
    }
    stack.pop_back();
    return result;
  }

  std::string packageName_;
  const std::vector<ManifestName>& names_;
  const std::vector<ManifestImport>& imports_;
  const std::vector<ManifestExport>& exports_;
};

std::size_t scanTaggedProperties(Reader& reader, std::uint16_t packageVersion,
                                 std::uint64_t exportEnd,
                                 const ManifestResolver& resolver,
                                 NameRef& terminator,
                                 std::vector<TaggedPropertyAnalysis>* properties = nullptr) {
  std::size_t count = 0;
  while (true) {
    if (reader.position() + 8 > exportEnd) {
      throw ParseError("tagged properties run beyond export payload");
    }
    TaggedPropertyAnalysis property;
    property.name = readNameRef(reader);
    if (resolver.name(property.name) == "None" && property.name.number == 0) {
      terminator = property.name;
      return count;
    }
    if (++count > kMaxArrayItems) throw ParseError("too many tagged properties");
    if (reader.position() + 16 > exportEnd) {
      throw ParseError("truncated FPropertyTag");
    }
    property.type = readNameRef(reader);
    property.size = reader.i32();
    property.arrayIndex = reader.i32();
    if (property.size < 0) throw ParseError("negative tagged-property size");
    const auto typeName = resolver.name(property.type);
    if (typeName == "StructProperty") {
      property.extraName = readNameRef(reader);
      property.hasExtraName = true;
    } else if (typeName == "BoolProperty") {
      if (packageVersion < 673) {
        property.boolValue = reader.u32();
      } else {
        property.boolValue = reader.u8();
      }
      property.hasBoolValue = true;
    } else if (typeName == "ByteProperty" && packageVersion >= 633) {
      property.extraName = readNameRef(reader);
      property.hasExtraName = true;
    }
    property.dataOffset = reader.position();
    const auto dataEnd = reader.position() + static_cast<std::uint64_t>(property.size);
    if (dataEnd > exportEnd) throw ParseError("tagged-property data exceeds export payload");
    if ((typeName == "IntProperty" || typeName == "ObjectProperty" ||
         typeName == "ClassProperty") && property.size == 4) {
      property.intValue = reader.i32();
      property.hasIntValue = true;
    } else if ((typeName == "NameProperty" || typeName == "ByteProperty") &&
               property.size == 8) {
      property.nameValue = readNameRef(reader);
      property.hasNameValue = true;
    } else if (typeName == "ByteProperty" && property.size == 1) {
      property.byteValue = reader.u8();
      property.hasByteValue = true;
    }
    reader.seek(dataEnd);
    if (properties != nullptr) properties->push_back(property);
  }
}

BulkDataAnalysis scanBulkData(Reader& reader, std::uint64_t exportEnd,
                              std::string_view context) {
  if (reader.position() + 16 > exportEnd) {
    throw ParseError("truncated " + std::string(context) + " bulk-data header");
  }
  BulkDataAnalysis bulk;
  bulk.flags = reader.u32();
  bulk.elementCount = reader.i32();
  bulk.sizeOnDisk = reader.i32();
  bulk.offsetInFile = reader.i32();
  constexpr std::uint32_t storeInSeparateFile = 1u << 0;
  constexpr std::uint32_t unused = 1u << 5;
  const bool unusedExternalSentinel =
      (bulk.flags & (storeInSeparateFile | unused)) == (storeInSeparateFile | unused) &&
      bulk.elementCount == 0 && bulk.sizeOnDisk == -1 && bulk.offsetInFile == -1;
  if (bulk.elementCount < 0 || (bulk.sizeOnDisk < 0 && !unusedExternalSentinel) ||
      (bulk.sizeOnDisk > 0 && bulk.offsetInFile < 0)) {
    throw ParseError("invalid " + std::string(context) + " bulk-data header (flags=" +
                     hex32(bulk.flags) + ", elements=" +
                     std::to_string(bulk.elementCount) + ", disk_size=" +
                     std::to_string(bulk.sizeOnDisk) + ", offset=" +
                     std::to_string(bulk.offsetInFile) + ")");
  }
  bulk.inlinePayload = (bulk.flags & storeInSeparateFile) == 0 && bulk.sizeOnDisk > 0;
  if (bulk.inlinePayload) {
    if (static_cast<std::uint64_t>(bulk.offsetInFile) != reader.position()) {
      throw ParseError(std::string(context) + " inline bulk-data offset mismatch");
    }
    const auto bulkEnd = reader.position() + static_cast<std::uint64_t>(bulk.sizeOnDisk);
    if (bulkEnd > exportEnd) {
      throw ParseError(std::string(context) + " bulk data exceeds export payload");
    }
    reader.seek(bulkEnd);
  }
  return bulk;
}

Texture2DMipAnalysis scanTextureMip(Reader& reader, std::uint64_t exportEnd,
                                    std::string_view context) {
  Texture2DMipAnalysis mip;
  mip.bulkData = scanBulkData(reader, exportEnd, context);
  if (reader.position() + 8 > exportEnd) {
    throw ParseError("truncated " + std::string(context) + " dimensions");
  }
  mip.sizeX = reader.i32();
  mip.sizeY = reader.i32();
  if (mip.sizeX < 0 || mip.sizeY < 0) {
    throw ParseError("negative " + std::string(context) + " dimensions");
  }
  return mip;
}

void appendConvertedFString(Reader& reader, std::vector<std::uint8_t>& output) {
  const auto length = reader.i32();
  appendLittle32(output, static_cast<std::uint32_t>(length));
  if (length == 0) return;
  if (length == std::numeric_limits<std::int32_t>::min()) {
    throw ParseError("invalid FString length");
  }
  const auto units = static_cast<std::size_t>(length < 0 ? -length : length);
  if (units > kMaxStringUnits) throw ParseError("unreasonable FString length");
  if (length > 0) {
    const auto value = reader.bytes(units);
    output.insert(output.end(), value.begin(), value.end());
  } else {
    // UE3 serializes the signed length using package byte order, but the
    // cooked FString character payload itself is UTF-16LE in this corpus,
    // including in big-endian Xbox packages.  Preserve those code-unit bytes.
    const auto value = reader.bytes(units * sizeof(std::uint16_t));
    output.insert(output.end(), value.begin(), value.end());
  }
}

std::size_t appendConvertedTaggedStruct(Reader& reader, std::uint64_t sourceEnd,
                                        const ManifestResolver& resolver,
                                        std::vector<std::uint8_t>& output);

void appendConvertedPropertyData(Reader& reader, std::uint64_t sourceEnd,
                                 std::string_view propertyName, std::string_view typeName,
                                 const ManifestResolver& resolver,
                                 std::vector<std::uint8_t>& output) {
  if (typeName == "StrProperty") {
    appendConvertedFString(reader, output);
  } else if (typeName == "IntProperty" || typeName == "FloatProperty" ||
             typeName == "ObjectProperty" || typeName == "ClassProperty") {
    appendLittle32(output, reader.u32());
  } else if (typeName == "NameProperty") {
    appendNameRef(output, readNameRef(reader));
  } else if (typeName == "ArrayProperty") {
    const auto count = reader.i32();
    if (count < 0 || static_cast<std::size_t>(count) > kMaxArrayItems) {
      throw ParseError("invalid converted tagged-array count");
    }
    appendLittle32(output, static_cast<std::uint32_t>(count));
    if (propertyName != "Subtitles" && propertyName != "LocalizedSubtitles") {
      throw ParseError("unsupported structured tagged array '" + std::string(propertyName) + "'");
    }
    for (std::int32_t i = 0; i < count; ++i) {
      (void)appendConvertedTaggedStruct(reader, sourceEnd, resolver, output);
    }
  } else if (typeName != "BoolProperty") {
    throw ParseError("unsupported tagged-property conversion type '" + std::string(typeName) + "'");
  }
  if (reader.position() != sourceEnd) {
    throw ParseError("converted tagged-property data did not close exactly");
  }
}

std::size_t appendConvertedTaggedStruct(Reader& reader, std::uint64_t sourceEnd,
                                        const ManifestResolver& resolver,
                                        std::vector<std::uint8_t>& output) {
  std::size_t count = 0;
  while (true) {
    if (reader.position() + 8 > sourceEnd) {
      throw ParseError("converted tagged struct exceeds its containing array");
    }
    const auto propertyNameRef = readNameRef(reader);
    appendNameRef(output, propertyNameRef);
    const auto propertyName = resolver.name(propertyNameRef);
    if (propertyName == "None" && propertyNameRef.number == 0) return count;
    if (++count > kMaxArrayItems || reader.position() + 16 > sourceEnd) {
      throw ParseError("invalid converted tagged struct");
    }
    const auto typeRef = readNameRef(reader);
    const auto typeName = resolver.name(typeRef);
    const auto size = reader.i32();
    const auto arrayIndex = reader.i32();
    if (size < 0) throw ParseError("negative converted tagged-property size");
    appendNameRef(output, typeRef);
    appendLittle32(output, static_cast<std::uint32_t>(size));
    appendLittle32(output, static_cast<std::uint32_t>(arrayIndex));
    if (typeName == "StructProperty" || typeName == "ByteProperty") {
      appendNameRef(output, readNameRef(reader));
    } else if (typeName == "BoolProperty") {
      output.push_back(reader.u8());
    }
    const auto dataStart = reader.position();
    const auto dataEnd = dataStart + static_cast<std::uint64_t>(size);
    if (dataEnd > sourceEnd) throw ParseError("converted struct property exceeds array data");
    const auto outputStart = output.size();
    appendConvertedPropertyData(reader, dataEnd, propertyName, typeName, resolver, output);
    if (output.size() - outputStart != static_cast<std::size_t>(size)) {
      throw ParseError("converted struct property changed serialized size");
    }
  }
}

std::uint16_t readBigU16(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
  if (offset + 2 > bytes.size()) throw ParseError("truncated XMA2 format");
  return static_cast<std::uint16_t>((static_cast<std::uint16_t>(bytes[offset]) << 8) |
                                    bytes[offset + 1]);
}

std::uint32_t readBigU32(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
  if (offset + 4 > bytes.size()) throw ParseError("truncated XMA2 data");
  return (static_cast<std::uint32_t>(bytes[offset]) << 24) |
         (static_cast<std::uint32_t>(bytes[offset + 1]) << 16) |
         (static_cast<std::uint32_t>(bytes[offset + 2]) << 8) |
         static_cast<std::uint32_t>(bytes[offset + 3]);
}

void writeFourCC(std::ostream& output, std::string_view value) {
  output.write(value.data(), static_cast<std::streamsize>(value.size()));
}

void writeLittleU16(std::ostream& output, std::uint16_t value) {
  const std::array<char, 2> bytes{
      static_cast<char>(value & 0xFF), static_cast<char>((value >> 8) & 0xFF)};
  output.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void writeLittleU32(std::ostream& output, std::uint32_t value) {
  const std::array<char, 4> bytes{
      static_cast<char>(value & 0xFF), static_cast<char>((value >> 8) & 0xFF),
      static_cast<char>((value >> 16) & 0xFF), static_cast<char>((value >> 24) & 0xFF)};
  output.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

int extractXma(const fs::path& input, std::size_t requestedExport, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty()) {
    std::cerr << input.string() << ": decompress the package before extracting audio\n";
    return 1;
  }
  if (summary.endian != Endian::Big) {
    std::cerr << input.string() << ": XMA extraction expects a big-endian Xbox 360 package\n";
    return 1;
  }
  if (requestedExport == 0 || requestedExport > static_cast<std::size_t>(summary.exports.count)) {
    std::cerr << input.string() << ": export index is outside the 1-based export table\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  try {
    Reader reader(input, summary.endian);
    std::vector<ManifestName> names;
    std::vector<ManifestImport> imports;
    std::vector<ManifestExport> exports;

    reader.seek(static_cast<std::uint64_t>(summary.names.offset));
    names.reserve(static_cast<std::size_t>(summary.names.count));
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      names.push_back({reader.fstring(), reader.u64()});
    }
    reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
    imports.reserve(static_cast<std::size_t>(summary.imports.count));
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      ManifestImport value;
      value.classPackage = readNameRef(reader);
      value.className = readNameRef(reader);
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      imports.push_back(value);
    }
    reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
    exports.reserve(static_cast<std::size_t>(summary.exports.count));
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      ManifestExport value;
      value.classIndex = reader.i32();
      value.superIndex = reader.i32();
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      value.archetypeIndex = reader.i32();
      value.objectFlags = reader.u64();
      value.serialSize = reader.i32();
      value.serialOffset = reader.i32();
      value.exportFlags = reader.u32();
      const auto generationCount = checkedCount(reader, "export generation");
      for (std::int32_t generation = 0; generation < generationCount; ++generation) {
        value.generationNetObjectCount.push_back(reader.i32());
      }
      for (auto& byte : value.packageGuid) byte = reader.u8();
      value.packageFlags = reader.u32();
      exports.push_back(std::move(value));
    }

    std::string packageName = input.stem().string();
    constexpr std::string_view reconstructedSuffix = ".uncompressed";
    if (packageName.ends_with(reconstructedSuffix)) {
      packageName.resize(packageName.size() - reconstructedSuffix.size());
    }
    const ManifestResolver resolver(packageName, names, imports, exports);
    const auto& object = exports[requestedExport - 1];
    if (resolver.resourceName(object.classIndex) != "SoundNodeWave") {
      throw ParseError("requested export is not a SoundNodeWave");
    }
    if (object.serialOffset < 0 || object.serialSize <= 0) {
      throw ParseError("SoundNodeWave has an invalid serialized range");
    }

    const auto exportStart = static_cast<std::uint64_t>(object.serialOffset);
    const auto exportEnd = exportStart + static_cast<std::uint64_t>(object.serialSize);
    reader.seek(exportStart);
    (void)reader.i32();  // NetIndex
    NameRef terminator;
    (void)scanTaggedProperties(reader, summary.engineVersion, exportEnd, resolver, terminator);
    if (resolver.name(terminator) != "None" || terminator.number != 0) {
      throw ParseError("SoundNodeWave tagged properties lack a valid terminator");
    }

    std::vector<std::uint8_t> xboxBulk;
    for (int slot = 0; slot < 4; ++slot) {
      if (reader.position() + 16 > exportEnd) throw ParseError("truncated bulk-data header");
      const auto flags = reader.u32();
      const auto elementCount = reader.i32();
      const auto sizeOnDisk = reader.i32();
      const auto offsetInFile = reader.i32();
      if (elementCount < 0 || sizeOnDisk < 0 || offsetInFile < 0) {
        throw ParseError("negative bulk-data field");
      }
      constexpr std::uint32_t storeInSeparateFile = 1u << 0;
      if ((flags & storeInSeparateFile) != 0 && sizeOnDisk > 0) {
        if (slot == 2) throw ParseError("Xbox audio is stored in a separate bulk-data file");
        continue;
      }
      if (sizeOnDisk > 0) {
        if (static_cast<std::uint64_t>(offsetInFile) != reader.position()) {
          throw ParseError("inline bulk-data offset mismatch");
        }
        if (reader.position() + static_cast<std::uint64_t>(sizeOnDisk) > exportEnd) {
          throw ParseError("inline bulk data exceeds SoundNodeWave export");
        }
        auto bytes = reader.bytes(static_cast<std::size_t>(sizeOnDisk));
        if (slot == 2) xboxBulk = std::move(bytes);
      }
    }
    if (reader.position() != exportEnd) throw ParseError("SoundNodeWave payload did not close exactly");
    if (xboxBulk.size() < 12) throw ParseError("SoundNodeWave has no inline Xbox 360 audio");

    const auto formatSize = readBigU32(xboxBulk, 0);
    const auto seekSize = readBigU32(xboxBulk, 4);
    const auto encodedSize = readBigU32(xboxBulk, 8);
    if (formatSize != 52) throw ParseError("Xbox audio is not an XMA2WAVEFORMATEX payload");
    if ((seekSize & 3u) != 0) throw ParseError("XMA seek table is not DWORD-aligned");
    const std::uint64_t declaredSize = 12ull + formatSize + seekSize + encodedSize;
    if (declaredSize != xboxBulk.size()) throw ParseError("XMA component sizes do not close exactly");
    const std::size_t formatOffset = 12;
    if (readBigU16(xboxBulk, formatOffset) != 0x0166) {
      throw ParseError("Xbox audio format tag is not WAVE_FORMAT_XMA2");
    }

    const std::uint32_t riffSize = 4u + (8u + formatSize) +
                                   (seekSize == 0 ? 0u : 8u + seekSize) +
                                   8u + encodedSize + (encodedSize & 1u);
    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    if (!destination) throw ParseError("could not create output file");
    writeFourCC(destination, "RIFF");
    writeLittleU32(destination, riffSize);
    writeFourCC(destination, "WAVE");
    writeFourCC(destination, "fmt ");
    writeLittleU32(destination, formatSize);
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 0));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 2));
    writeLittleU32(destination, readBigU32(xboxBulk, formatOffset + 4));
    writeLittleU32(destination, readBigU32(xboxBulk, formatOffset + 8));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 12));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 14));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 16));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 18));
    for (std::size_t offset = 20; offset <= 44; offset += 4) {
      writeLittleU32(destination, readBigU32(xboxBulk, formatOffset + offset));
    }
    destination.put(static_cast<char>(xboxBulk[formatOffset + 48]));
    destination.put(static_cast<char>(xboxBulk[formatOffset + 49]));
    writeLittleU16(destination, readBigU16(xboxBulk, formatOffset + 50));
    if (seekSize != 0) {
      writeFourCC(destination, "seek");
      writeLittleU32(destination, seekSize);
      const auto seekOffset = formatOffset + formatSize;
      for (std::size_t offset = 0; offset < seekSize; offset += 4) {
        writeLittleU32(destination, readBigU32(xboxBulk, seekOffset + offset));
      }
    }
    writeFourCC(destination, "data");
    writeLittleU32(destination, encodedSize);
    const auto encodedOffset = formatOffset + formatSize + seekSize;
    destination.write(reinterpret_cast<const char*>(xboxBulk.data() + encodedOffset), encodedSize);
    if ((encodedSize & 1u) != 0) destination.put('\0');
    destination.close();
    if (!destination) throw ParseError("XMA output write failed");
    const auto expectedFileSize = static_cast<std::uint64_t>(riffSize) + 8;
    if (fs::file_size(output) != expectedFileSize) throw ParseError("XMA output size mismatch");

    std::cout << "Extracted " << resolver.exportPath(requestedExport - 1) << "\n"
              << "  channels/rate: " << readBigU16(xboxBulk, formatOffset + 2) << " / "
              << readBigU32(xboxBulk, formatOffset + 4) << " Hz\n"
              << "  XMA2 data:     " << encodedSize << " bytes\n"
              << "  output:        " << output.string() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << input.string() << ": XMA extraction failed: " << error.what() << '\n';
    return 1;
  }
}

int convertAudioFixture(const fs::path& input, std::size_t requestedExport,
                        const fs::path& pcOgg, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty() || summary.compressionFlags != 0 ||
      summary.endian != Endian::Big || summary.engineVersion != 845 ||
      summary.licenseeVersion != 0) {
    std::cerr << input.string()
              << ": audio fixture conversion requires an uncompressed big-endian Judgment v845 package\n";
    return 1;
  }
  if (requestedExport == 0 || requestedExport > static_cast<std::size_t>(summary.exports.count)) {
    std::cerr << input.string() << ": export index is outside the 1-based export table\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  try {
    std::vector<std::uint8_t> ogg;
    {
      const auto size = fs::file_size(pcOgg);
      if (size < 4 || size > std::numeric_limits<std::uint32_t>::max()) {
        throw ParseError("PC Ogg input has an invalid size");
      }
      ogg.resize(static_cast<std::size_t>(size));
      std::ifstream source(pcOgg, std::ios::binary);
      source.read(reinterpret_cast<char*>(ogg.data()), static_cast<std::streamsize>(ogg.size()));
      if (!source || !std::equal(ogg.begin(), ogg.begin() + 4, "OggS")) {
        throw ParseError("PC audio input is not an Ogg stream");
      }
    }

    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(fs::file_size(input)));
    {
      std::ifstream source(input, std::ios::binary);
      source.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
      if (!source) throw ParseError("could not read complete package");
    }

    std::vector<ManifestName> names;
    std::vector<ManifestImport> imports;
    std::vector<ManifestExport> exports;
    {
      Reader reader(input, summary.endian);
      reader.seek(static_cast<std::uint64_t>(summary.names.offset));
      for (std::int32_t i = 0; i < summary.names.count; ++i) {
        names.push_back({reader.fstring(), reader.u64()});
      }
      reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
      for (std::int32_t i = 0; i < summary.imports.count; ++i) {
        ManifestImport value;
        value.classPackage = readNameRef(reader);
        value.className = readNameRef(reader);
        value.outerIndex = reader.i32();
        value.objectName = readNameRef(reader);
        imports.push_back(value);
      }
      reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
      for (std::int32_t i = 0; i < summary.exports.count; ++i) {
        ManifestExport value;
        value.classIndex = reader.i32();
        value.superIndex = reader.i32();
        value.outerIndex = reader.i32();
        value.objectName = readNameRef(reader);
        value.archetypeIndex = reader.i32();
        value.objectFlags = reader.u64();
        value.serialSize = reader.i32();
        value.serialOffset = reader.i32();
        value.exportFlags = reader.u32();
        const auto generationCount = checkedCount(reader, "export generation");
        for (std::int32_t generation = 0; generation < generationCount; ++generation) {
          value.generationNetObjectCount.push_back(reader.i32());
        }
        for (auto& byte : value.packageGuid) byte = reader.u8();
        value.packageFlags = reader.u32();
        exports.push_back(std::move(value));
      }
    }

    const ManifestResolver resolver(input.stem().string(), names, imports, exports);
    const auto& waveExport = exports[requestedExport - 1];
    if (resolver.resourceName(waveExport.classIndex) != "SoundNodeWave") {
      throw ParseError("requested export is not a SoundNodeWave");
    }
    if (requestedExport != exports.size() || waveExport.serialOffset < 0 ||
        waveExport.serialSize <= 0 ||
        static_cast<std::uint64_t>(waveExport.serialOffset) +
                static_cast<std::uint64_t>(waveExport.serialSize) !=
            bytes.size()) {
      throw ParseError("fixture converter requires SoundNodeWave to be the final export and file range");
    }

    std::vector<TaggedPropertyAnalysis> properties;
    NameRef terminator;
    std::int32_t netIndex = 0;
    {
      Reader reader(input, summary.endian);
      const auto start = static_cast<std::uint64_t>(waveExport.serialOffset);
      reader.seek(start);
      netIndex = reader.i32();
      (void)scanTaggedProperties(reader, summary.engineVersion,
                                 start + static_cast<std::uint64_t>(waveExport.serialSize),
                                 resolver, terminator, &properties);
    }

    std::vector<std::uint8_t> wavePayload;
    // NetIndex belongs to the source console seek-free network-object table.
    // This deliberately standalone PC fixture has no such table, so preserve
    // the UObject sentinel instead of an index that Jacinto cannot register.
    constexpr std::int32_t kStandaloneNetIndex = -1;
    appendLittle32(wavePayload, static_cast<std::uint32_t>(kStandaloneNetIndex));
    std::size_t preservedProperties = 0;
    for (const auto& property : properties) {
      const auto typeName = resolver.name(property.type);
      if (typeName != "BoolProperty" && typeName != "IntProperty" &&
          typeName != "FloatProperty" && typeName != "StrProperty" &&
          typeName != "ArrayProperty") {
        continue;
      }
      appendNameRef(wavePayload, property.name);
      appendNameRef(wavePayload, property.type);
      appendLittle32(wavePayload, static_cast<std::uint32_t>(property.size));
      appendLittle32(wavePayload, static_cast<std::uint32_t>(property.arrayIndex));
      if (typeName == "BoolProperty") {
        wavePayload.push_back(static_cast<std::uint8_t>(property.boolValue));
      } else {
        Reader valueReader(input, summary.endian);
        valueReader.seek(property.dataOffset);
        const auto outputStart = wavePayload.size();
        appendConvertedPropertyData(
            valueReader, property.dataOffset + static_cast<std::uint64_t>(property.size),
            resolver.name(property.name), typeName, resolver, wavePayload);
        if (wavePayload.size() - outputStart != static_cast<std::size_t>(property.size)) {
          throw ParseError("converted top-level property changed serialized size");
        }
      }
      ++preservedProperties;
    }
    appendNameRef(wavePayload, terminator);

    const auto waveStart = static_cast<std::uint64_t>(waveExport.serialOffset);
    const auto appendBulkHeader = [&](std::uint32_t count, std::uint32_t size,
                                      std::uint32_t offset) {
      appendLittle32(wavePayload, 0u);
      appendLittle32(wavePayload, count);
      appendLittle32(wavePayload, size);
      appendLittle32(wavePayload, offset);
    };
    appendBulkHeader(0, 0, static_cast<std::uint32_t>(waveStart + wavePayload.size() + 16));
    appendBulkHeader(static_cast<std::uint32_t>(ogg.size()), static_cast<std::uint32_t>(ogg.size()),
                     static_cast<std::uint32_t>(waveStart + wavePayload.size() + 16));
    wavePayload.insert(wavePayload.end(), ogg.begin(), ogg.end());
    appendBulkHeader(0, 0, static_cast<std::uint32_t>(waveStart + wavePayload.size() + 16));
    appendBulkHeader(0, 0, static_cast<std::uint32_t>(waveStart + wavePayload.size() + 16));
    if (wavePayload.size() > static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max())) {
      throw ParseError("converted SoundNodeWave is too large");
    }

    LittleEndianRewriter rewrite(input, summary.endian, bytes);
    rewrite.u32(kPackageTag);
    rewrite.u32(828u);
    rewrite.i32();
    rewrite.fstring();
    // Normalize the console-cooked package flags to the flags used by Jacinto's
    // ordinary PC-cooked audio packages.  In particular, retaining
    // PKG_RequireImportsAlreadyLoaded/PKG_FilterEditorOnly changes linker and
    // archive behavior even after the payload byte order has been converted.
    constexpr std::uint32_t kPcCookedAudioPackageFlags = 0x20080009u;
    rewrite.u32(kPcCookedAudioPackageFlags);
    for (int i = 0; i < 7; ++i) rewrite.i32();
    for (int i = 0; i < 3; ++i) rewrite.i32();
    rewrite.i32();
    for (int i = 0; i < 4; ++i) rewrite.u32();
    const auto summaryGenerationCount = rewrite.i32();
    if (summaryGenerationCount < 0 ||
        static_cast<std::size_t>(summaryGenerationCount) > kMaxArrayItems) {
      throw ParseError("invalid package generation count");
    }
    for (std::int32_t i = 0; i < summaryGenerationCount; ++i) {
      rewrite.i32();
      rewrite.i32();
      rewrite.i32();
    }
    rewrite.u32(8741u);
    rewrite.u32();
    rewrite.u32(0u);
    if (rewrite.i32(0) != 0) throw ParseError("unexpected compressed chunk table");
    rewrite.u32();
    const auto additionalCount = rewrite.i32();
    if (additionalCount < 0 || static_cast<std::size_t>(additionalCount) > kMaxArrayItems) {
      throw ParseError("invalid additional-package count");
    }
    for (std::int32_t i = 0; i < additionalCount; ++i) rewrite.fstring();
    const auto textureCount = rewrite.i32();
    if (textureCount != 0) throw ParseError("fixture converter does not support texture allocations");
    if (rewrite.position() != static_cast<std::uint64_t>(summary.names.offset)) {
      throw ParseError("summary does not close at name table");
    }
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      rewrite.fstring();
      rewrite.u64();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.imports.offset)) {
      throw ParseError("name table does not close at import table");
    }
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      rewriteNameRef(rewrite);
      rewriteNameRef(rewrite);
      rewrite.i32();
      rewriteNameRef(rewrite);
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.exports.offset)) {
      throw ParseError("import table does not close at export table");
    }
    for (std::size_t i = 0; i < exports.size(); ++i) {
      rewrite.i32();
      rewrite.i32();
      rewrite.i32();
      rewriteNameRef(rewrite);
      rewrite.i32();
      rewrite.u64();
      rewrite.i32(i + 1 == requestedExport
                      ? std::optional<std::int32_t>(static_cast<std::int32_t>(wavePayload.size()))
                      : std::nullopt);
      rewrite.i32();
      // EF_ForcedExport is a console seek-free cook artifact.  A standalone PC
      // package uses normal exports, including for SoundNodeWave objects.
      rewrite.u32(0u);
      const auto generationCount = rewrite.i32();
      if (generationCount < 0 || static_cast<std::size_t>(generationCount) > kMaxArrayItems) {
        throw ParseError("invalid export generation count");
      }
      for (std::int32_t generation = 0; generation < generationCount; ++generation) rewrite.i32();
      for (int guidPart = 0; guidPart < 4; ++guidPart) rewrite.u32();
      rewrite.u32();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.dependsOffset)) {
      throw ParseError("export table does not close at dependency table");
    }
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      const auto dependencyCount = rewrite.i32();
      if (dependencyCount < 0 || static_cast<std::size_t>(dependencyCount) > kMaxArrayItems) {
        throw ParseError("invalid dependency count");
      }
      for (std::int32_t dependency = 0; dependency < dependencyCount; ++dependency) rewrite.i32();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.totalHeaderSize)) {
      throw ParseError("dependency table does not close at payload boundary");
    }

    for (std::size_t i = 0; i + 1 < exports.size(); ++i) {
      const auto& object = exports[i];
      rewrite.seek(static_cast<std::uint64_t>(object.serialOffset));
      const auto className = resolver.resourceName(object.classIndex);
      if (className == "Package") {
        rewrite.i32(-1);
        rewriteNameRef(rewrite);
      } else if (className == "ObjectReferencer") {
        rewrite.i32(-1);
        rewriteNameRef(rewrite);
        rewriteNameRef(rewrite);
        rewrite.i32();
        rewrite.i32();
        const auto count = rewrite.i32();
        if (count < 0 || static_cast<std::size_t>(count) > kMaxArrayItems) {
          throw ParseError("invalid ObjectReferencer count");
        }
        for (std::int32_t reference = 0; reference < count; ++reference) rewrite.i32();
        rewriteNameRef(rewrite);
      } else {
        throw ParseError("fixture contains an unsupported non-audio export class");
      }
      if (rewrite.position() != static_cast<std::uint64_t>(object.serialOffset) +
                                    static_cast<std::uint64_t>(object.serialSize)) {
        throw ParseError("rewritten non-audio export does not close exactly");
      }
    }

    bytes.resize(static_cast<std::size_t>(waveExport.serialOffset));
    bytes.insert(bytes.end(), wavePayload.begin(), wavePayload.end());
    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    destination.write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size()));
    destination.close();
    if (!destination) throw ParseError("converted package write failed");

    const auto reparsed = parseSummary(output, 0);
    if (reparsed.endian != Endian::Little || reparsed.engineVersion != 828 ||
        reparsed.savedEngineVersion != 8741 || reparsed.exports.count != summary.exports.count) {
      throw ParseError("independent converted-package summary validation failed");
    }
    std::cout << "Converted audio fixture " << resolver.exportPath(requestedExport - 1) << "\n"
              << "  properties: " << preservedProperties << "/" << properties.size()
              << " tagged properties endian-converted (including text/subtitles)\n"
              << "  NetIndex:   " << netIndex << " -> -1 (standalone fixture)\n"
              << "  PC Ogg:     " << ogg.size() << " bytes\n"
              << "  PC flags:   0x20080009; forced-export flags cleared\n"
              << "  output:     " << output.string() << " (" << bytes.size() << " bytes)\n";
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << input.string() << ": audio fixture conversion failed: " << error.what() << '\n';
    return 1;
  }
}

std::vector<std::uint8_t> readOgg(const fs::path& path) {
  const auto size = fs::file_size(path);
  if (size < 4 || size > static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
    throw ParseError(path.string() + ": Ogg input has an invalid size");
  }
  std::vector<std::uint8_t> ogg(static_cast<std::size_t>(size));
  std::ifstream source(path, std::ios::binary);
  source.read(reinterpret_cast<char*>(ogg.data()), static_cast<std::streamsize>(ogg.size()));
  if (!source || !std::equal(ogg.begin(), ogg.begin() + 4, "OggS")) {
    throw ParseError(path.string() + ": input is not an Ogg stream");
  }
  return ogg;
}

std::vector<std::uint8_t> convertPackagePayload(const fs::path& input, Endian endian,
                                                const ManifestExport& object) {
  Reader reader(input, endian);
  reader.seek(static_cast<std::uint64_t>(object.serialOffset));
  (void)reader.i32();
  const auto terminator = readNameRef(reader);
  if (reader.position() != static_cast<std::uint64_t>(object.serialOffset) +
                               static_cast<std::uint64_t>(object.serialSize)) {
    throw ParseError("Package payload does not close exactly");
  }
  std::vector<std::uint8_t> payload;
  appendLittle32(payload, std::numeric_limits<std::uint32_t>::max());
  appendNameRef(payload, terminator);
  return payload;
}

std::vector<std::uint8_t> convertObjectReferencerPayload(const fs::path& input, Endian endian,
                                                         const ManifestExport& object) {
  Reader reader(input, endian);
  reader.seek(static_cast<std::uint64_t>(object.serialOffset));
  (void)reader.i32();
  const auto propertyName = readNameRef(reader);
  const auto propertyType = readNameRef(reader);
  const auto propertySize = reader.i32();
  const auto arrayIndex = reader.i32();
  const auto count = reader.i32();
  if (propertySize < 4 || count < 0 || static_cast<std::size_t>(count) > kMaxArrayItems) {
    throw ParseError("invalid ObjectReferencer payload");
  }
  std::vector<std::int32_t> references;
  references.reserve(static_cast<std::size_t>(count));
  for (std::int32_t i = 0; i < count; ++i) references.push_back(reader.i32());
  const auto terminator = readNameRef(reader);
  if (reader.position() != static_cast<std::uint64_t>(object.serialOffset) +
                               static_cast<std::uint64_t>(object.serialSize)) {
    throw ParseError("ObjectReferencer payload does not close exactly");
  }

  std::vector<std::uint8_t> payload;
  appendLittle32(payload, std::numeric_limits<std::uint32_t>::max());
  appendNameRef(payload, propertyName);
  appendNameRef(payload, propertyType);
  appendLittle32(payload, static_cast<std::uint32_t>(propertySize));
  appendLittle32(payload, static_cast<std::uint32_t>(arrayIndex));
  appendLittle32(payload, static_cast<std::uint32_t>(count));
  for (const auto reference : references) {
    appendLittle32(payload, static_cast<std::uint32_t>(reference));
  }
  appendNameRef(payload, terminator);
  return payload;
}

std::vector<std::uint8_t> convertSoundNodeWavePayload(
    const fs::path& input, const Summary& summary, const ManifestResolver& resolver,
    const ManifestExport& object, std::uint64_t targetOffset,
    const std::vector<std::uint8_t>& ogg, std::size_t& propertyCount,
    std::int32_t& sourceNetIndex) {
  const auto sourceStart = static_cast<std::uint64_t>(object.serialOffset);
  const auto sourceEnd = sourceStart + static_cast<std::uint64_t>(object.serialSize);
  Reader reader(input, summary.endian);
  reader.seek(sourceStart);
  sourceNetIndex = reader.i32();
  NameRef terminator;
  std::vector<TaggedPropertyAnalysis> properties;
  (void)scanTaggedProperties(reader, summary.engineVersion, sourceEnd, resolver, terminator,
                             &properties);

  bool hasXboxData = false;
  for (int slot = 0; slot < 4; ++slot) {
    if (reader.position() + 16 > sourceEnd) {
      throw ParseError("truncated SoundNodeWave bulk-data header");
    }
    (void)reader.u32();
    const auto elementCount = reader.i32();
    const auto sizeOnDisk = reader.i32();
    const auto offsetInFile = reader.i32();
    if (elementCount < 0 || sizeOnDisk < 0 || offsetInFile < 0) {
      throw ParseError("negative SoundNodeWave bulk-data field");
    }
    if (sizeOnDisk != 0) {
      if (static_cast<std::uint64_t>(offsetInFile) != reader.position()) {
        throw ParseError("audio package converter requires inline SoundNodeWave bulk data");
      }
      const auto bulkEnd = reader.position() + static_cast<std::uint64_t>(sizeOnDisk);
      if (bulkEnd > sourceEnd) throw ParseError("SoundNodeWave bulk data exceeds export");
      if (slot == 2) hasXboxData = true;
      reader.seek(bulkEnd);
    }
  }
  if (reader.position() != sourceEnd) throw ParseError("SoundNodeWave payload does not close exactly");
  if (!hasXboxData) throw ParseError("SoundNodeWave has no inline Xbox 360 audio");

  std::vector<std::uint8_t> payload;
  appendLittle32(payload, std::numeric_limits<std::uint32_t>::max());
  for (const auto& property : properties) {
    const auto propertyName = resolver.name(property.name);
    const auto typeName = resolver.name(property.type);
    if (typeName != "BoolProperty" && typeName != "IntProperty" &&
        typeName != "FloatProperty" && typeName != "StrProperty" &&
        typeName != "ArrayProperty" && typeName != "NameProperty" &&
        typeName != "ObjectProperty" && typeName != "ClassProperty") {
      throw ParseError("unsupported SoundNodeWave property '" + propertyName +
                       "' of type '" + typeName + "'");
    }
    appendNameRef(payload, property.name);
    appendNameRef(payload, property.type);
    appendLittle32(payload, static_cast<std::uint32_t>(property.size));
    appendLittle32(payload, static_cast<std::uint32_t>(property.arrayIndex));
    if (typeName == "BoolProperty") {
      payload.push_back(static_cast<std::uint8_t>(property.boolValue));
    } else {
      Reader valueReader(input, summary.endian);
      valueReader.seek(property.dataOffset);
      const auto outputStart = payload.size();
      appendConvertedPropertyData(
          valueReader, property.dataOffset + static_cast<std::uint64_t>(property.size),
          propertyName, typeName, resolver, payload);
      if (payload.size() - outputStart != static_cast<std::size_t>(property.size)) {
        throw ParseError("converted SoundNodeWave property changed serialized size");
      }
    }
  }
  propertyCount = properties.size();
  appendNameRef(payload, terminator);

  const auto appendBulkHeader = [&](std::uint32_t count, std::uint32_t size) {
    const auto absoluteOffset = targetOffset + payload.size() + 16;
    if (absoluteOffset > std::numeric_limits<std::uint32_t>::max()) {
      throw ParseError("converted SoundNodeWave bulk offset exceeds UE3 range");
    }
    appendLittle32(payload, 0u);
    appendLittle32(payload, count);
    appendLittle32(payload, size);
    appendLittle32(payload, static_cast<std::uint32_t>(absoluteOffset));
  };
  appendBulkHeader(0, 0);
  appendBulkHeader(static_cast<std::uint32_t>(ogg.size()),
                   static_cast<std::uint32_t>(ogg.size()));
  payload.insert(payload.end(), ogg.begin(), ogg.end());
  appendBulkHeader(0, 0);
  appendBulkHeader(0, 0);
  return payload;
}

int convertAudioPackage(const fs::path& input, const fs::path& oggDirectory,
                        const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty() || summary.compressionFlags != 0 ||
      summary.endian != Endian::Big || summary.engineVersion != 845 ||
      summary.licenseeVersion != 0) {
    std::cerr << input.string()
              << ": audio package conversion requires an uncompressed big-endian Judgment v845 package\n";
    return 1;
  }
  if (!fs::is_directory(oggDirectory)) {
    std::cerr << oggDirectory.string() << ": Ogg input directory was not found\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  try {
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(fs::file_size(input)));
    {
      std::ifstream source(input, std::ios::binary);
      source.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
      if (!source) throw ParseError("could not read complete package");
    }

    std::vector<ManifestName> names;
    std::vector<ManifestImport> imports;
    std::vector<ManifestExport> exports;
    {
      Reader reader(input, summary.endian);
      reader.seek(static_cast<std::uint64_t>(summary.names.offset));
      for (std::int32_t i = 0; i < summary.names.count; ++i) {
        names.push_back({reader.fstring(), reader.u64()});
      }
      reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
      for (std::int32_t i = 0; i < summary.imports.count; ++i) {
        ManifestImport value;
        value.classPackage = readNameRef(reader);
        value.className = readNameRef(reader);
        value.outerIndex = reader.i32();
        value.objectName = readNameRef(reader);
        imports.push_back(value);
      }
      reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
      for (std::int32_t i = 0; i < summary.exports.count; ++i) {
        ManifestExport value;
        value.classIndex = reader.i32();
        value.superIndex = reader.i32();
        value.outerIndex = reader.i32();
        value.objectName = readNameRef(reader);
        value.archetypeIndex = reader.i32();
        value.objectFlags = reader.u64();
        value.serialSize = reader.i32();
        value.serialOffset = reader.i32();
        value.exportFlags = reader.u32();
        const auto generationCount = checkedCount(reader, "export generation");
        for (std::int32_t generation = 0; generation < generationCount; ++generation) {
          value.generationNetObjectCount.push_back(reader.i32());
        }
        for (auto& byte : value.packageGuid) byte = reader.u8();
        value.packageFlags = reader.u32();
        exports.push_back(std::move(value));
      }
    }

    const ManifestResolver resolver(input.stem().string(), names, imports, exports);
    std::vector<std::vector<std::uint8_t>> payloads(exports.size());
    std::vector<std::int32_t> targetOffsets(exports.size());
    std::uint64_t sourceCursor = static_cast<std::uint64_t>(summary.totalHeaderSize);
    std::uint64_t targetCursor = sourceCursor;
    std::size_t waveCount = 0;
    std::size_t propertyCount = 0;
    for (std::size_t i = 0; i < exports.size(); ++i) {
      const auto& object = exports[i];
      if (object.serialOffset < 0 || object.serialSize <= 0 ||
          static_cast<std::uint64_t>(object.serialOffset) != sourceCursor) {
        throw ParseError("audio package exports are not a contiguous table-order payload stream");
      }
      sourceCursor += static_cast<std::uint64_t>(object.serialSize);
      if (targetCursor > static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
        throw ParseError("converted export offset exceeds UE3 range");
      }
      targetOffsets[i] = static_cast<std::int32_t>(targetCursor);
      const auto className = resolver.resourceName(object.classIndex);
      if (className == "Package") {
        payloads[i] = convertPackagePayload(input, summary.endian, object);
      } else if (className == "ObjectReferencer") {
        payloads[i] = convertObjectReferencerPayload(input, summary.endian, object);
      } else if (className == "SoundNodeWave") {
        const auto oggPath = oggDirectory / (std::to_string(i + 1) + ".ogg");
        if (!fs::is_regular_file(oggPath)) {
          throw ParseError(oggPath.string() + ": missing Ogg for SoundNodeWave export " +
                           std::to_string(i + 1));
        }
        const auto ogg = readOgg(oggPath);
        std::size_t convertedProperties = 0;
        std::int32_t sourceNetIndex = 0;
        payloads[i] = convertSoundNodeWavePayload(
            input, summary, resolver, object, targetCursor, ogg,
            convertedProperties, sourceNetIndex);
        propertyCount += convertedProperties;
        ++waveCount;
      } else {
        throw ParseError("unsupported export class '" + className + "' at export " +
                         std::to_string(i + 1));
      }
      if (payloads[i].size() >
          static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max())) {
        throw ParseError("converted export is too large");
      }
      targetCursor += payloads[i].size();
    }
    if (sourceCursor != bytes.size()) {
      throw ParseError("audio package payload stream does not close at end of file");
    }
    if (waveCount == 0) throw ParseError("package contains no SoundNodeWave exports");

    LittleEndianRewriter rewrite(input, summary.endian, bytes);
    rewrite.u32(kPackageTag);
    rewrite.u32(828u);
    rewrite.i32();
    rewrite.fstring();
    constexpr std::uint32_t kPcCookedAudioPackageFlags = 0x20080009u;
    rewrite.u32(kPcCookedAudioPackageFlags);
    for (int i = 0; i < 7; ++i) rewrite.i32();
    for (int i = 0; i < 3; ++i) rewrite.i32();
    rewrite.i32();
    for (int i = 0; i < 4; ++i) rewrite.u32();
    const auto summaryGenerationCount = rewrite.i32();
    if (summaryGenerationCount < 0 ||
        static_cast<std::size_t>(summaryGenerationCount) > kMaxArrayItems) {
      throw ParseError("invalid package generation count");
    }
    for (std::int32_t i = 0; i < summaryGenerationCount; ++i) {
      rewrite.i32();
      rewrite.i32();
      rewrite.i32();
    }
    rewrite.u32(8741u);
    rewrite.u32();
    rewrite.u32(0u);
    if (rewrite.i32(0) != 0) throw ParseError("unexpected compressed chunk table");
    rewrite.u32();
    const auto additionalCount = rewrite.i32();
    if (additionalCount < 0 || static_cast<std::size_t>(additionalCount) > kMaxArrayItems) {
      throw ParseError("invalid additional-package count");
    }
    for (std::int32_t i = 0; i < additionalCount; ++i) rewrite.fstring();
    const auto textureCount = rewrite.i32();
    if (textureCount != 0) throw ParseError("audio package converter does not support texture allocations");
    if (rewrite.position() != static_cast<std::uint64_t>(summary.names.offset)) {
      throw ParseError("summary does not close at name table");
    }
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      rewrite.fstring();
      rewrite.u64();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.imports.offset)) {
      throw ParseError("name table does not close at import table");
    }
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      rewriteNameRef(rewrite);
      rewriteNameRef(rewrite);
      rewrite.i32();
      rewriteNameRef(rewrite);
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.exports.offset)) {
      throw ParseError("import table does not close at export table");
    }
    for (std::size_t i = 0; i < exports.size(); ++i) {
      rewrite.i32();
      rewrite.i32();
      rewrite.i32();
      rewriteNameRef(rewrite);
      rewrite.i32();
      rewrite.u64();
      rewrite.i32(static_cast<std::int32_t>(payloads[i].size()));
      rewrite.i32(targetOffsets[i]);
      rewrite.u32(0u);
      const auto generationCount = rewrite.i32();
      if (generationCount < 0 || static_cast<std::size_t>(generationCount) > kMaxArrayItems) {
        throw ParseError("invalid export generation count");
      }
      for (std::int32_t generation = 0; generation < generationCount; ++generation) rewrite.i32();
      for (int guidPart = 0; guidPart < 4; ++guidPart) rewrite.u32();
      rewrite.u32();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.dependsOffset)) {
      throw ParseError("export table does not close at dependency table");
    }
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      const auto dependencyCount = rewrite.i32();
      if (dependencyCount < 0 || static_cast<std::size_t>(dependencyCount) > kMaxArrayItems) {
        throw ParseError("invalid dependency count");
      }
      for (std::int32_t dependency = 0; dependency < dependencyCount; ++dependency) rewrite.i32();
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.totalHeaderSize)) {
      throw ParseError("dependency table does not close at payload boundary");
    }

    bytes.resize(static_cast<std::size_t>(summary.totalHeaderSize));
    for (const auto& payload : payloads) bytes.insert(bytes.end(), payload.begin(), payload.end());
    if (bytes.size() != targetCursor) throw ParseError("converted package size accounting failed");
    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    destination.write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size()));
    destination.close();
    if (!destination) throw ParseError("converted package write failed");

    const auto reparsed = parseSummary(output, 0);
    if (reparsed.endian != Endian::Little || reparsed.engineVersion != 828 ||
        reparsed.savedEngineVersion != 8741 || reparsed.exports.count != summary.exports.count) {
      throw ParseError("independent converted-package summary validation failed");
    }
    std::cout << "Converted multi-wave audio package\n"
              << "  waves:       " << waveCount << "\n"
              << "  properties:  " << propertyCount << " tagged properties endian-converted\n"
              << "  exports:     " << exports.size() << " offsets and sizes rebuilt\n"
              << "  PC flags:    0x20080009; forced-export flags cleared\n"
              << "  output:      " << output.string() << " (" << bytes.size() << " bytes)\n";
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << input.string() << ": audio package conversion failed: " << error.what() << '\n';
    return 1;
  }
}

int makeVorbisTimeTestFixture(const fs::path& input, const fs::path& output) {
  constexpr std::string_view oldName = "AID_COMMON_SF_LOC_INT";
  constexpr std::string_view testName = "22Mono_TestDialogMale";
  static_assert(oldName.size() == testName.size());
  if (output.stem().string() != "TestSounds") {
    std::cerr << output.string() << ": output must be named TestSounds.upk\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  try {
    const auto summary = parseSummary(input, 0);
    if (summary.fullyCompressed || !summary.chunks.empty() ||
        summary.endian != Endian::Little || summary.engineVersion != 828 ||
        summary.exports.count != 4) {
      throw ParseError("expected the narrow uncompressed little-endian v828 audio fixture");
    }
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(fs::file_size(input)));
    {
      std::ifstream source(input, std::ios::binary);
      source.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
      if (!source) throw ParseError("could not read complete input fixture");
    }

    std::vector<ManifestName> names;
    std::vector<ManifestImport> imports;
    std::vector<ManifestExport> exports;
    std::vector<std::uint64_t> exportRecordOffsets;
    Reader reader(input, summary.endian);
    reader.seek(static_cast<std::uint64_t>(summary.names.offset));
    const auto firstNameRecord = reader.position();
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      names.push_back({reader.fstring(), reader.u64()});
    }
    if (names.empty() || names.front().value != oldName) {
      throw ParseError("fixture's first name is not the expected replaceable alias slot");
    }
    Reader nameReader(input, summary.endian);
    nameReader.seek(firstNameRecord);
    if (nameReader.i32() != static_cast<std::int32_t>(oldName.size() + 1)) {
      throw ParseError("alias name is not stored as the expected ANSI FString");
    }
    const auto nameDataOffset = nameReader.position();
    std::copy(testName.begin(), testName.end(),
              bytes.begin() + static_cast<std::ptrdiff_t>(nameDataOffset));
    bytes[static_cast<std::size_t>(nameDataOffset + testName.size())] = 0;

    reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      ManifestImport value;
      value.classPackage = readNameRef(reader);
      value.className = readNameRef(reader);
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      imports.push_back(value);
    }
    reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      exportRecordOffsets.push_back(reader.position());
      ManifestExport value;
      value.classIndex = reader.i32();
      value.superIndex = reader.i32();
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      value.archetypeIndex = reader.i32();
      value.objectFlags = reader.u64();
      value.serialSize = reader.i32();
      value.serialOffset = reader.i32();
      value.exportFlags = reader.u32();
      const auto generationCount = checkedCount(reader, "export generation");
      for (std::int32_t generation = 0; generation < generationCount; ++generation) {
        value.generationNetObjectCount.push_back(reader.i32());
      }
      for (auto& byte : value.packageGuid) byte = reader.u8();
      value.packageFlags = reader.u32();
      exports.push_back(std::move(value));
    }
    const ManifestResolver resolver(input.stem().string(), names, imports, exports);
    if (resolver.resourceName(exports.back().classIndex) != "SoundNodeWave") {
      throw ParseError("fixture's final export is not SoundNodeWave");
    }
    const auto waveRecord = exportRecordOffsets.back();
    writeLittle32(bytes, waveRecord + 8, 0u);   // OuterIndex: root of TestSounds package
    writeLittle32(bytes, waveRecord + 12, 0u);  // ObjectName: renamed name-table entry 0
    writeLittle32(bytes, waveRecord + 16, 0u);  // ObjectName number

    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    destination.write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size()));
    destination.close();
    if (!destination) throw ParseError("time-test fixture write failed");
    const auto reparsed = parseSummary(output, 0);
    if (reparsed.endian != Endian::Little || reparsed.engineVersion != 828 ||
        reparsed.exports.count != 4) {
      throw ParseError("independent time-test fixture validation failed");
    }
    std::cout << "Created engine Vorbis time-test alias\n"
              << "  asset:  TestSounds." << testName << "\n"
              << "  output: " << output.string() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << input.string() << ": time-test fixture conversion failed: "
              << error.what() << '\n';
    return 1;
  }
}

std::vector<std::uint8_t> readFileRange(const fs::path& path, std::uint64_t offset,
                                        std::uint64_t size) {
  const auto fileSize = fs::file_size(path);
  if (offset > fileSize || size > fileSize - offset ||
      size > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
    throw ParseError(path.string() + ": requested byte range lies outside the file");
  }
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
  std::ifstream stream(path, std::ios::binary);
  stream.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
  if (!stream || (size != 0 &&
                  !stream.read(reinterpret_cast<char*>(bytes.data()),
                               static_cast<std::streamsize>(bytes.size())))) {
    throw ParseError(path.string() + ": could not read requested byte range");
  }
  return bytes;
}

std::vector<std::uint8_t> loadTextureBulk(const fs::path& package,
                                          const fs::path& textureCache,
                                          const BulkDataAnalysis& bulk) {
  constexpr std::uint32_t storeInSeparateFile = 1u << 0;
  constexpr std::uint32_t compressedZlib = 1u << 1;
  constexpr std::uint32_t compressedLzo = 1u << 4;
  constexpr std::uint32_t compressedLzx = 1u << 7;
  if (bulk.elementCount <= 0 || bulk.sizeOnDisk <= 0 || bulk.offsetInFile < 0) {
    throw ParseError("texture mip has no recoverable bulk payload");
  }
  const auto& storage = (bulk.flags & storeInSeparateFile) != 0 ? textureCache : package;
  const auto stored = readFileRange(storage, static_cast<std::uint64_t>(bulk.offsetInFile),
                                    static_cast<std::uint64_t>(bulk.sizeOnDisk));
  const auto compression = bulk.flags & (compressedZlib | compressedLzo | compressedLzx);
  if (compression == 0) {
    if (bulk.sizeOnDisk != bulk.elementCount) {
      throw ParseError("uncompressed texture bulk size differs from its element count");
    }
    return stored;
  }
  if (compression != compressedLzo && compression != compressedLzx) {
    throw ParseError("texture bulk uses an unsupported compression flag combination");
  }
  std::vector<std::uint8_t> decoded;
  std::string error;
  const auto codec = compression == compressedLzo ? SerializedCompression::Lzo
                                                   : SerializedCompression::Lzx;
  if (!decompressSerializedBlob(stored, static_cast<std::size_t>(bulk.elementCount),
                                decoded, error, codec)) {
    throw ParseError("texture bulk decompression failed: " + error);
  }
  return decoded;
}

// Block geometry and Xenon element swizzle for the pixel formats that appear
// in the Judgment texture corpus.  The endian unit was measured per format with
// xg-tail-oracle rather than assumed; PF_G16 and PF_A16B16G16R16 use a
// different element swizzle and are deliberately absent.
struct TextureFormatInfo {
  std::uint32_t blockSizeX;
  std::uint32_t blockSizeY;
  std::uint32_t bytesPerBlock;
  std::uint32_t endianUnit;
};

const std::map<std::string, TextureFormatInfo>& supportedTextureFormats() {
  static const std::map<std::string, TextureFormatInfo> formats{
      {"PF_DXT1", {4, 4, 8, 2}},   {"PF_DXT3", {4, 4, 16, 2}},
      {"PF_DXT5", {4, 4, 16, 2}},  {"PF_BC5", {4, 4, 16, 2}},
      {"PF_G8", {1, 1, 1, 1}},     {"PF_A8R8G8B8", {1, 1, 4, 4}},
      {"PF_V8U8", {1, 1, 2, 2}}};
  return formats;
}

std::vector<std::uint8_t> detileXbox360Surface(std::vector<std::uint8_t> tiled,
                                               std::uint32_t widthPixels,
                                               std::uint32_t heightPixels,
                                               const TextureFormatInfo& format) {
  const auto blockSizeX = format.blockSizeX;
  const auto blockSizeY = format.blockSizeY;
  const auto bytesPerBlock = format.bytesPerBlock;
  const auto endianUnit = format.endianUnit;
  if (tiled.empty() || tiled.size() % bytesPerBlock != 0) {
    throw ParseError("Xbox texture allocation has an invalid physical byte count");
  }
  for (std::size_t offset = 0; offset < tiled.size(); offset += endianUnit) {
    std::reverse(tiled.begin() + static_cast<std::ptrdiff_t>(offset),
                 tiled.begin() + static_cast<std::ptrdiff_t>(offset + endianUnit));
  }
  const auto widthInBlocks = std::max(1u, (widthPixels + blockSizeX - 1u) / blockSizeX);
  const auto heightInBlocks = std::max(1u, (heightPixels + blockSizeY - 1u) / blockSizeY);
  const auto outputBlockCount = static_cast<std::uint64_t>(widthInBlocks) * heightInBlocks;
  const auto outputSize = outputBlockCount * bytesPerBlock;
  if (outputBlockCount == 0 ||
      outputSize > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
      tiled.size() / bytesPerBlock > std::numeric_limits<std::uint32_t>::max()) {
    throw ParseError("Xbox texture dimensions exceed the supported range");
  }
  std::vector<std::uint8_t> linear(static_cast<std::size_t>(outputSize));
  std::vector<bool> written(static_cast<std::size_t>(outputBlockCount));
  std::size_t mapped = 0;
  for (std::uint32_t sourceBlock = 0;
       sourceBlock < static_cast<std::uint32_t>(tiled.size() / bytesPerBlock);
       ++sourceBlock) {
    const auto x = xbox360TiledX(sourceBlock, widthInBlocks, bytesPerBlock);
    const auto y = xbox360TiledY(sourceBlock, widthInBlocks, bytesPerBlock);
    if (x >= widthInBlocks || y >= heightInBlocks) continue;
    const auto destinationBlock = static_cast<std::size_t>(y) * widthInBlocks + x;
    if (written[destinationBlock]) {
      throw ParseError("Xbox detile mapping produced a duplicate logical block");
    }
    written[destinationBlock] = true;
    ++mapped;
    std::copy_n(tiled.begin() + static_cast<std::ptrdiff_t>(sourceBlock * bytesPerBlock),
                bytesPerBlock,
                linear.begin() + static_cast<std::ptrdiff_t>(destinationBlock * bytesPerBlock));
  }
  if (mapped != outputBlockCount ||
      std::find(written.begin(), written.end(), false) != written.end()) {
    throw ParseError("Xbox texture allocation does not cover every logical block");
  }
  return linear;
}

// Forward Xenon 2D tiled address: logical block coordinate -> block slot.
// The existing xbox360TiledX/Y pair inverts a tiled allocation, which suits a
// whole-surface detile.  The packed tail instead needs to ask "where did this
// particular block go", so the forward direction is required.
std::uint32_t xbox360TiledBlockOffset(std::uint32_t x, std::uint32_t y,
                                      std::uint32_t alignedWidthInBlocks,
                                      std::uint32_t bytesPerBlock) {
  const auto logBpp = (bytesPerBlock >> 2u) +
                      ((bytesPerBlock >> 1u) >> (bytesPerBlock >> 2u));
  const auto macro = ((x >> 5u) + (y >> 5u) * (alignedWidthInBlocks >> 5u))
                     << (logBpp + 7u);
  const auto micro = ((x & 7u) + ((y & 6u) << 2u)) << logBpp;
  const auto offset = macro + ((micro & ~15u) << 1u) + (micro & 15u) +
                      ((y & 8u) << (3u + logBpp)) + ((y & 1u) << 4u);
  return (((offset & ~511u) << 3u) + ((offset & 448u) << 2u) + (offset & 63u) +
          ((y & 16u) << 7u) +
          (((((y & 8u) >> 2u) + (x >> 3u)) & 3u) << 6u)) >> logBpp;
}

// Pixel-space coordinate of one packed-tail level inside the shared tail
// surface.  Measured with xg-tail-oracle against Judgment's own April 2012
// Xbox360Tools cooker over 585 synthetic geometries; it reproduces the cooker
// exactly for every pixel format present in the Judgment corpus (DXT1, DXT3,
// DXT5, BC5, G8, A8R8G8B8, V8U8), including the retained 45-block
// T_GT_Fir_Cluster_MASK map.  Expressing it in pixels rather than blocks is
// what makes it format-independent.
//
// The two 16-bit-element formats (G16, A16B16G16R16) use a different element
// swizzle and are deliberately unsupported; neither appears in the corpus.
void packedMipTailCoordinatePixels(std::uint32_t tailLevel, bool wide,
                                   std::uint32_t mipWidthPixels,
                                   std::uint32_t mipHeightPixels, std::uint32_t& outX,
                                   std::uint32_t& outY) {
  const std::uint32_t stepped = tailLevel < 3 ? (16u >> tailLevel) : 0u;
  if (stepped >= 4u) {
    outX = wide ? 0u : stepped;
    outY = wide ? stepped : 0u;
  } else {
    outX = wide ? 4u * mipWidthPixels : 0u;
    outY = wide ? 0u : 4u * mipHeightPixels;
  }
}

struct MipTailGeometry {
  std::uint32_t widthPixels = 0;
  std::uint32_t heightPixels = 0;
  std::uint32_t tailBaseIndex = 0;
  std::uint32_t mipCount = 0;
  std::uint32_t blockSizeX = 0;
  std::uint32_t blockSizeY = 0;
  std::uint32_t bytesPerBlock = 0;
  std::uint32_t endianUnit = 0;  // 1 = none, 2 = 16-bit, 4 = 32-bit
};

// Unpacks every level stored in a packed mip tail into its linear PC payload.
std::vector<std::vector<std::uint8_t>> extractPackedMipTail(
    const std::vector<std::uint8_t>& tail, const MipTailGeometry& geometry) {
  if (geometry.tailBaseIndex >= geometry.mipCount) {
    throw ParseError("packed mip tail base is outside the mip chain");
  }
  if (geometry.bytesPerBlock == 0 || geometry.blockSizeX == 0 || geometry.blockSizeY == 0) {
    throw ParseError("packed mip tail geometry has an invalid block description");
  }
  if (geometry.endianUnit != 1 && geometry.endianUnit != 2 && geometry.endianUnit != 4) {
    throw ParseError("packed mip tail endian unit must be 1, 2, or 4 bytes");
  }
  if (geometry.bytesPerBlock % geometry.endianUnit != 0) {
    throw ParseError("packed mip tail block size is not a multiple of its endian unit");
  }

  const auto mipPixels = [](std::uint32_t base, std::uint32_t level) {
    const auto value = base >> level;
    return value > 0 ? value : 1u;
  };
  const auto blocksFor = [](std::uint32_t pixels, std::uint32_t blockSize) {
    const auto count = (pixels + blockSize - 1u) / blockSize;
    return count > 0 ? count : 1u;
  };

  // The tail surface is addressed as a 32-block-wide Xenon surface; this held
  // for every measured geometry, including those whose packed levels reach
  // beyond block column 32.
  constexpr std::uint32_t kTailAlignedWidthInBlocks = 32u;

  const bool wide = mipPixels(geometry.widthPixels, geometry.tailBaseIndex) >
                    mipPixels(geometry.heightPixels, geometry.tailBaseIndex);
  const auto tailLevels = geometry.mipCount - geometry.tailBaseIndex;

  std::vector<std::vector<std::uint8_t>> levels(tailLevels);
  std::vector<bool> consumed(tail.size() / geometry.bytesPerBlock, false);

  for (std::uint32_t tailLevel = 0; tailLevel < tailLevels; ++tailLevel) {
    const auto level = geometry.tailBaseIndex + tailLevel;
    const auto mipWidth = mipPixels(geometry.widthPixels, level);
    const auto mipHeight = mipPixels(geometry.heightPixels, level);
    const auto blocksX = blocksFor(mipWidth, geometry.blockSizeX);
    const auto blocksY = blocksFor(mipHeight, geometry.blockSizeY);

    std::uint32_t originX = 0;
    std::uint32_t originY = 0;
    packedMipTailCoordinatePixels(tailLevel, wide, mipWidth, mipHeight, originX, originY);
    if (originX % geometry.blockSizeX != 0 || originY % geometry.blockSizeY != 0) {
      throw ParseError("packed mip tail origin is not block aligned");
    }
    originX /= geometry.blockSizeX;
    originY /= geometry.blockSizeY;

    auto& linear = levels[tailLevel];
    linear.resize(static_cast<std::size_t>(blocksX) * blocksY * geometry.bytesPerBlock);
    for (std::uint32_t blockY = 0; blockY < blocksY; ++blockY) {
      for (std::uint32_t blockX = 0; blockX < blocksX; ++blockX) {
        const auto slot = xbox360TiledBlockOffset(originX + blockX, originY + blockY,
                                                  kTailAlignedWidthInBlocks,
                                                  geometry.bytesPerBlock);
        const auto sourceOffset = static_cast<std::size_t>(slot) * geometry.bytesPerBlock;
        if (sourceOffset + geometry.bytesPerBlock > tail.size()) {
          throw ParseError("packed mip tail block lies outside the serialized tail data");
        }
        if (consumed[slot]) {
          throw ParseError("packed mip tail maps two logical blocks onto one allocation slot");
        }
        consumed[slot] = true;

        const auto destination =
            (static_cast<std::size_t>(blockY) * blocksX + blockX) * geometry.bytesPerBlock;
        for (std::uint32_t byte = 0; byte < geometry.bytesPerBlock;
             byte += geometry.endianUnit) {
          for (std::uint32_t part = 0; part < geometry.endianUnit; ++part) {
            linear[destination + byte + part] =
                tail[sourceOffset + byte + geometry.endianUnit - 1u - part];
          }
        }
      }
    }
  }
  return levels;
}

void appendConvertedGuid(std::vector<std::uint8_t>& output,
                         const std::array<std::uint8_t, 16>& source,
                         Endian sourceEndian) {
  for (std::size_t part = 0; part < 4; ++part) {
    const auto begin = source.begin() + static_cast<std::ptrdiff_t>(part * 4);
    if (sourceEndian == Endian::Big) {
      output.insert(output.end(), std::make_reverse_iterator(begin + 4),
                    std::make_reverse_iterator(begin));
    } else {
      output.insert(output.end(), begin, begin + 4);
    }
  }
}

int convertTextureFixture(const fs::path& input, std::size_t requestedExport,
                          const fs::path& textureCache, const fs::path& output,
                          bool includePackedTail) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty() || summary.compressionFlags != 0 ||
      summary.endian != Endian::Big || summary.engineVersion != 845 ||
      summary.licenseeVersion != 0) {
    std::cerr << input.string()
              << ": texture fixture conversion requires an uncompressed big-endian Judgment v845 package\n";
    return 1;
  }
  if (requestedExport >= static_cast<std::size_t>(summary.exports.count)) {
    std::cerr << input.string() << ": zero-based export index is outside the export table\n";
    return 1;
  }
  if (!fs::is_regular_file(textureCache) && !fs::is_directory(textureCache)) {
    std::cerr << textureCache.string()
              << ": texture cache file or cache directory was not found\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  try {
    std::vector<ManifestName> names;
    std::vector<ManifestImport> imports;
    std::vector<ManifestExport> exports;
    Reader reader(input, summary.endian);
    reader.seek(static_cast<std::uint64_t>(summary.names.offset));
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      names.push_back({reader.fstring(), reader.u64()});
    }
    reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      ManifestImport value;
      value.classPackage = readNameRef(reader);
      value.className = readNameRef(reader);
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      imports.push_back(value);
    }
    reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      ManifestExport value;
      value.classIndex = reader.i32();
      value.superIndex = reader.i32();
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      value.archetypeIndex = reader.i32();
      value.objectFlags = reader.u64();
      value.serialSize = reader.i32();
      value.serialOffset = reader.i32();
      value.exportFlags = reader.u32();
      const auto generationCount = checkedCount(reader, "export generation");
      for (std::int32_t generation = 0; generation < generationCount; ++generation) {
        value.generationNetObjectCount.push_back(reader.i32());
      }
      for (auto& byte : value.packageGuid) byte = reader.u8();
      value.packageFlags = reader.u32();
      exports.push_back(std::move(value));
    }

    std::string sourcePackageName = input.stem().string();
    constexpr std::string_view reconstructedSuffix = ".uncompressed";
    if (sourcePackageName.ends_with(reconstructedSuffix)) {
      sourcePackageName.resize(sourcePackageName.size() - reconstructedSuffix.size());
    }
    const ManifestResolver resolver(sourcePackageName, names, imports, exports);
    const auto& object = exports[requestedExport];
    if (resolver.resourceName(object.classIndex) != "Texture2D" ||
        object.classIndex >= 0 || object.serialOffset < 0 || object.serialSize <= 0) {
      throw ParseError("requested export is not a serialized Texture2D");
    }
    const auto classImportIndex = static_cast<std::size_t>(-object.classIndex - 1);
    if (classImportIndex >= imports.size()) throw ParseError("Texture2D class import is invalid");
    const auto& textureClassImport = imports[classImportIndex];
    if (textureClassImport.outerIndex >= 0 || resolver.name(textureClassImport.objectName) != "Texture2D") {
      throw ParseError("Texture2D class import does not have the expected Engine outer");
    }
    const auto engineImportIndex = static_cast<std::size_t>(-textureClassImport.outerIndex - 1);
    if (engineImportIndex >= imports.size()) throw ParseError("Engine package import is invalid");
    const auto& engineImport = imports[engineImportIndex];
    if (engineImport.outerIndex != 0 || resolver.name(engineImport.objectName) != "Engine") {
      throw ParseError("Texture2D class outer is not the Engine package import");
    }

    const auto sourceStart = static_cast<std::uint64_t>(object.serialOffset);
    const auto sourceEnd = sourceStart + static_cast<std::uint64_t>(object.serialSize);
    reader.seek(sourceStart);
    const auto sourceNetIndex = reader.i32();
    NameRef terminator;
    std::vector<TaggedPropertyAnalysis> properties;
    (void)scanTaggedProperties(reader, summary.engineVersion, sourceEnd, resolver, terminator,
                               &properties);
    const auto sourceArt = scanBulkData(reader, sourceEnd, "Texture2D source art");
    const auto mipCount = checkedCount(reader, "Texture2D mips");
    std::vector<Texture2DMipAnalysis> sourceMips;
    for (std::int32_t i = 0; i < mipCount; ++i) {
      sourceMips.push_back(scanTextureMip(reader, sourceEnd,
                                          "Texture2D mip " + std::to_string(i)));
    }
    std::array<std::uint8_t, 16> textureGuid{};
    for (auto& byte : textureGuid) byte = reader.u8();
    const auto pvrtcCount = checkedCount(reader, "Texture2D cached PVRTC mips");
    for (std::int32_t i = 0; i < pvrtcCount; ++i) {
      (void)scanTextureMip(reader, sourceEnd,
                           "Texture2D cached PVRTC mip " + std::to_string(i));
    }
    if (reader.position() != sourceEnd) throw ParseError("Texture2D source payload does not close exactly");
    if (sourceArt.elementCount != 0 || sourceArt.sizeOnDisk != 0 || pvrtcCount != 0) {
      throw ParseError("first texture fixture requires empty SourceArt and cached PVRTC data");
    }
    if (sourceMips.size() < 3) throw ParseError("texture does not contain three non-packed mips");

    const TaggedPropertyAnalysis* formatProperty = nullptr;
    const TaggedPropertyAnalysis* mipTailProperty = nullptr;
    const TaggedPropertyAnalysis* cacheNameProperty = nullptr;
    std::map<std::string, const TaggedPropertyAnalysis*> requiredProperties;
    for (const auto& property : properties) {
      const auto name = resolver.name(property.name);
      if (name == "SizeX" || name == "SizeY" || name == "OriginalSizeX" ||
          name == "OriginalSizeY" || name == "Format" || name == "MipTailBaseIdx") {
        if (requiredProperties.contains(name)) {
          throw ParseError("duplicate required Texture2D property '" + name + "'");
        }
        requiredProperties[name] = &property;
      }
      if (name == "Format") formatProperty = &property;
      if (name == "MipTailBaseIdx") mipTailProperty = &property;
      if (name == "TextureFileCacheName") cacheNameProperty = &property;
    }
    const std::array<std::string_view, 6> requiredNames{
        "SizeX", "SizeY", "OriginalSizeX", "OriginalSizeY", "Format", "MipTailBaseIdx"};
    for (const auto name : requiredNames) {
      if (!requiredProperties.contains(std::string(name))) {
        throw ParseError("Texture2D lacks required property '" + std::string(name) + "'");
      }
    }
    if (formatProperty == nullptr || !formatProperty->hasNameValue) {
      throw ParseError("Texture2D has no usable Format property");
    }
    const auto formatName = std::string(resolver.name(formatProperty->nameValue));
    const auto formatEntry = supportedTextureFormats().find(formatName);
    if (formatEntry == supportedTextureFormats().end()) {
      throw ParseError("texture conversion does not support pixel format '" + formatName + "'");
    }
    const auto& textureFormat = formatEntry->second;
    if (mipTailProperty == nullptr || !mipTailProperty->hasIntValue ||
        mipTailProperty->intValue < 0 ||
        static_cast<std::size_t>(mipTailProperty->intValue) >= sourceMips.size()) {
      throw ParseError("Texture2D has no usable MipTailBaseIdx");
    }
    if (sourceMips[0].sizeX != requiredProperties["SizeX"]->intValue ||
        sourceMips[0].sizeY != requiredProperties["SizeY"]->intValue) {
      throw ParseError("Texture2D base dimensions disagree with mip zero");
    }

    // Judgment splits external mips across three caches (Textures, Lighting,
    // and CharTextures), so the texture's own TextureFileCacheName selects one.
    // A directory argument resolves "<name>.tfc" inside it; an explicit file
    // path is still honoured as-is.
    fs::path resolvedCache = textureCache;
    if (fs::is_directory(textureCache)) {
      if (cacheNameProperty == nullptr || !cacheNameProperty->hasNameValue) {
        throw ParseError("texture has external mips but no TextureFileCacheName to resolve");
      }
      const auto cacheName = std::string(resolver.name(cacheNameProperty->nameValue));
      resolvedCache = textureCache / (cacheName + ".tfc");
      if (!fs::is_regular_file(resolvedCache)) {
        throw ParseError("texture cache '" + cacheName + ".tfc' was not found in the cache directory");
      }
    }

    // Everything above the tail base is an ordinary tiled allocation; the tail
    // base level and everything below it share one packed allocation.
    const auto tailBase = static_cast<std::size_t>(mipTailProperty->intValue);

    // Shipped cooks routinely strip the highest-resolution levels of a
    // streaming texture, leaving UE3's unused sentinel (flags 0x21, zero
    // elements, -1 size and offset) in their place.  Those levels carry no
    // data in this cook, so conversion starts at the first resident mip and
    // the emitted PC texture is simply that much smaller.  The packed-tail
    // geometry still uses the original dimensions and level indices, because
    // that is what XG packed the tail against.
    const auto isUnusedSentinel = [](const Texture2DMipAnalysis& mip) {
      constexpr std::int32_t unusedSentinelFlags = 0x21;
      return mip.bulkData.flags == unusedSentinelFlags && mip.bulkData.elementCount == 0 &&
             mip.bulkData.sizeOnDisk == -1 && mip.bulkData.offsetInFile == -1;
    };
    std::size_t firstResident = 0;
    while (firstResident < sourceMips.size() && isUnusedSentinel(sourceMips[firstResident])) {
      ++firstResident;
    }
    if (firstResident > tailBase) {
      throw ParseError("every mip above the packed tail is an unused streaming sentinel");
    }

    const auto nonPackedCount = includePackedTail
                                    ? tailBase - firstResident
                                    : std::min<std::size_t>(3, tailBase - firstResident);
    if (!includePackedTail && tailBase - firstResident < 3) {
      throw ParseError("the non-packed path requires three resident mips before the packed tail");
    }

    std::vector<std::vector<std::uint8_t>> linearMips(nonPackedCount);
    for (std::size_t i = 0; i < nonPackedCount; ++i) {
      const auto& sourceMip = sourceMips[firstResident + i];
      if (sourceMip.sizeX <= 0 || sourceMip.sizeY <= 0) {
        throw ParseError("non-packed mip has invalid dimensions");
      }
      if (isUnusedSentinel(sourceMip)) {
        throw ParseError("an unused streaming sentinel appears between resident mips");
      }
      auto allocation = loadTextureBulk(input, resolvedCache, sourceMip.bulkData);
      linearMips[i] = detileXbox360Surface(std::move(allocation),
          static_cast<std::uint32_t>(sourceMip.sizeX),
          static_cast<std::uint32_t>(sourceMip.sizeY), textureFormat);
    }
    if (includePackedTail) {
      // The packed tail is no longer a table measured for one asset: the
      // layout is computed from the texture's own geometry and pixel format.
      if (sourceMips.size() <= tailBase) {
        throw ParseError("full-mip conversion requires at least one packed-tail level");
      }
      MipTailGeometry geometry;
      geometry.widthPixels = static_cast<std::uint32_t>(sourceMips[0].sizeX);
      geometry.heightPixels = static_cast<std::uint32_t>(sourceMips[0].sizeY);
      geometry.tailBaseIndex = static_cast<std::uint32_t>(tailBase);
      geometry.mipCount = static_cast<std::uint32_t>(sourceMips.size());
      geometry.blockSizeX = textureFormat.blockSizeX;
      geometry.blockSizeY = textureFormat.blockSizeY;
      geometry.bytesPerBlock = textureFormat.bytesPerBlock;
      geometry.endianUnit = textureFormat.endianUnit;

      const auto tailAllocation =
          loadTextureBulk(input, resolvedCache, sourceMips[tailBase].bulkData);
      auto tailMips = extractPackedMipTail(tailAllocation, geometry);
      for (auto& mip : tailMips) linearMips.push_back(std::move(mip));
    }

    std::map<std::int32_t, std::int32_t> nameRemap;
    const auto requireName = [&](NameRef ref) {
      if (ref.index < 0 || static_cast<std::size_t>(ref.index) >= names.size()) {
        throw ParseError("fixture contains an invalid source name reference");
      }
      nameRemap.try_emplace(ref.index, -1);
    };
    requireName(object.objectName);
    requireName(terminator);
    for (const auto& [name, property] : requiredProperties) {
      (void)name;
      requireName(property->name);
      requireName(property->type);
      if (property->hasExtraName) requireName(property->extraName);
      if (property->hasNameValue) requireName(property->nameValue);
    }
    const auto collectImportNames = [&](const ManifestImport& value) {
      requireName(value.classPackage);
      requireName(value.className);
      requireName(value.objectName);
    };
    collectImportNames(textureClassImport);
    collectImportNames(engineImport);
    std::int32_t nextName = 0;
    for (auto& [oldIndex, newIndex] : nameRemap) {
      (void)oldIndex;
      newIndex = nextName++;
    }
    const auto remapName = [&](NameRef ref) {
      const auto found = nameRemap.find(ref.index);
      if (found == nameRemap.end()) throw ParseError("uncollected fixture name reference");
      return NameRef{found->second, ref.number};
    };

    std::vector<std::uint8_t> nameTable;
    for (const auto& [oldIndex, newIndex] : nameRemap) {
      (void)newIndex;
      const auto& name = names[static_cast<std::size_t>(oldIndex)];
      if (std::any_of(name.value.begin(), name.value.end(),
                      [](unsigned char c) { return c >= 0x80; })) {
        throw ParseError("first texture fixture requires ASCII metadata names");
      }
      appendAnsiFString(nameTable, name.value);
      appendLittle64(nameTable, name.flags);
    }
    std::vector<std::uint8_t> importTable;
    appendNameRef(importTable, remapName(textureClassImport.classPackage));
    appendNameRef(importTable, remapName(textureClassImport.className));
    appendLittle32(importTable, static_cast<std::uint32_t>(-2));
    appendNameRef(importTable, remapName(textureClassImport.objectName));
    appendNameRef(importTable, remapName(engineImport.classPackage));
    appendNameRef(importTable, remapName(engineImport.className));
    appendLittle32(importTable, 0);
    appendNameRef(importTable, remapName(engineImport.objectName));

    std::vector<std::uint8_t> packageSummary;
    appendLittle32(packageSummary, kPackageTag);
    appendLittle32(packageSummary, 828u);
    const auto totalHeaderPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    appendAnsiFString(packageSummary, "None");
    constexpr std::uint32_t kPcCookedPackageFlags = 0x20080009u;
    appendLittle32(packageSummary, kPcCookedPackageFlags);
    const auto nameCountPatch = packageSummary.size();
    appendLittle32(packageSummary, static_cast<std::uint32_t>(nameRemap.size()));
    const auto nameOffsetPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    appendLittle32(packageSummary, 1);  // ExportCount
    const auto exportOffsetPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    appendLittle32(packageSummary, 2);  // ImportCount
    const auto importOffsetPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    const auto dependsOffsetPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    const auto importExportGuidsPatch = packageSummary.size();
    appendLittle32(packageSummary, 0);
    appendLittle32(packageSummary, 0);  // ImportGuidsCount
    appendLittle32(packageSummary, 0);  // ExportGuidsCount
    appendLittle32(packageSummary, 0);  // ThumbnailTableOffset
    for (int i = 0; i < 4; ++i) appendLittle32(packageSummary, 0);  // package GUID
    appendLittle32(packageSummary, 1);  // GenerationCount
    appendLittle32(packageSummary, 1);  // generation ExportCount
    appendLittle32(packageSummary, static_cast<std::uint32_t>(nameRemap.size()));
    appendLittle32(packageSummary, 0);  // generation NetObjectCount
    appendLittle32(packageSummary, 8741u);
    appendLittle32(packageSummary, 134u);
    appendLittle32(packageSummary, 0);  // CompressionFlags
    appendLittle32(packageSummary, 0);  // CompressedChunks
    appendLittle32(packageSummary, summary.packageSource);
    appendLittle32(packageSummary, 0);  // AdditionalPackages
    appendLittle32(packageSummary, 0);  // TextureAllocations
    (void)nameCountPatch;

    constexpr std::uint32_t exportRecordSize = 68;
    constexpr std::uint32_t dependencyTableSize = 4;
    const auto nameOffset = static_cast<std::uint32_t>(packageSummary.size());
    const auto importOffset = nameOffset + static_cast<std::uint32_t>(nameTable.size());
    const auto exportOffset = importOffset + static_cast<std::uint32_t>(importTable.size());
    const auto dependsOffset = exportOffset + exportRecordSize;
    const auto totalHeaderSize = dependsOffset + dependencyTableSize;
    writeLittle32(packageSummary, totalHeaderPatch, totalHeaderSize);
    writeLittle32(packageSummary, nameOffsetPatch, nameOffset);
    writeLittle32(packageSummary, importOffsetPatch, importOffset);
    writeLittle32(packageSummary, exportOffsetPatch, exportOffset);
    writeLittle32(packageSummary, dependsOffsetPatch, dependsOffset);
    writeLittle32(packageSummary, importExportGuidsPatch, totalHeaderSize);

    std::vector<std::uint8_t> texturePayload;
    appendLittle32(texturePayload, std::numeric_limits<std::uint32_t>::max());
    for (const auto& property : properties) {
      const auto propertyName = resolver.name(property.name);
      if (!requiredProperties.contains(propertyName)) continue;
      const auto typeName = resolver.name(property.type);
      appendNameRef(texturePayload, remapName(property.name));
      appendNameRef(texturePayload, remapName(property.type));
      appendLittle32(texturePayload, static_cast<std::uint32_t>(property.size));
      appendLittle32(texturePayload, static_cast<std::uint32_t>(property.arrayIndex));
      if (typeName == "IntProperty" && property.size == 4 && property.hasIntValue) {
        // SizeX/SizeY describe the emitted texture, which starts at the first
        // resident mip; OriginalSizeX/Y keep the authored dimensions.
        std::int32_t value = property.intValue;
        if (propertyName == "MipTailBaseIdx") {
          value = static_cast<std::int32_t>(linearMips.size() - 1);
        } else if (propertyName == "SizeX") {
          value = sourceMips[firstResident].sizeX;
        } else if (propertyName == "SizeY") {
          value = sourceMips[firstResident].sizeY;
        }
        appendLittle32(texturePayload, static_cast<std::uint32_t>(value));
      } else if (typeName == "ByteProperty" && property.size == 8 &&
                 property.hasExtraName && property.hasNameValue) {
        appendNameRef(texturePayload, remapName(property.extraName));
        appendNameRef(texturePayload, remapName(property.nameValue));
      } else {
        throw ParseError("required Texture2D property has an unsupported serialized form");
      }
    }
    appendNameRef(texturePayload, remapName(terminator));
    const auto appendInlineBulk = [&](std::span<const std::uint8_t> data) {
      const auto absoluteOffset = static_cast<std::uint64_t>(totalHeaderSize) +
                                  texturePayload.size() + 16;
      if (absoluteOffset > std::numeric_limits<std::uint32_t>::max() ||
          data.size() > static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max())) {
        throw ParseError("texture fixture bulk offset or size exceeds UE3 range");
      }
      appendLittle32(texturePayload, 0);  // uncompressed, inline
      appendLittle32(texturePayload, static_cast<std::uint32_t>(data.size()));
      appendLittle32(texturePayload, static_cast<std::uint32_t>(data.size()));
      appendLittle32(texturePayload, static_cast<std::uint32_t>(absoluteOffset));
      texturePayload.insert(texturePayload.end(), data.begin(), data.end());
    };
    appendInlineBulk({});  // SourceArt
    appendLittle32(texturePayload, static_cast<std::uint32_t>(linearMips.size()));
    for (std::size_t i = 0; i < linearMips.size(); ++i) {
      appendInlineBulk(linearMips[i]);
      appendLittle32(texturePayload, static_cast<std::uint32_t>(sourceMips[firstResident + i].sizeX));
      appendLittle32(texturePayload, static_cast<std::uint32_t>(sourceMips[firstResident + i].sizeY));
    }
    appendConvertedGuid(texturePayload, textureGuid, summary.endian);
    appendLittle32(texturePayload, 0);  // CachedPVRTCMips
    if (texturePayload.size() >
        static_cast<std::size_t>(std::numeric_limits<std::int32_t>::max())) {
      throw ParseError("texture fixture payload is too large");
    }

    std::vector<std::uint8_t> exportTable;
    appendLittle32(exportTable, static_cast<std::uint32_t>(-1));  // Engine.Texture2D
    appendLittle32(exportTable, 0);  // SuperIndex
    appendLittle32(exportTable, 0);  // root export
    appendNameRef(exportTable, remapName(object.objectName));
    appendLittle32(exportTable, 0);  // ArchetypeIndex
    appendLittle64(exportTable, object.objectFlags);
    appendLittle32(exportTable, static_cast<std::uint32_t>(texturePayload.size()));
    appendLittle32(exportTable, totalHeaderSize);
    appendLittle32(exportTable, 0);  // no seek-free forced export
    appendLittle32(exportTable, 0);  // no generation net-object counts
    for (int i = 0; i < 4; ++i) appendLittle32(exportTable, 0);
    appendLittle32(exportTable, 0);
    if (exportTable.size() != exportRecordSize) throw ParseError("texture export record size mismatch");

    std::vector<std::uint8_t> bytes;
    bytes.reserve(static_cast<std::size_t>(totalHeaderSize) + texturePayload.size());
    bytes.insert(bytes.end(), packageSummary.begin(), packageSummary.end());
    bytes.insert(bytes.end(), nameTable.begin(), nameTable.end());
    bytes.insert(bytes.end(), importTable.begin(), importTable.end());
    bytes.insert(bytes.end(), exportTable.begin(), exportTable.end());
    appendLittle32(bytes, 0);  // empty dependency array for the sole export
    if (bytes.size() != totalHeaderSize) throw ParseError("texture fixture header accounting failed");
    bytes.insert(bytes.end(), texturePayload.begin(), texturePayload.end());

    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create texture fixture output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    destination.write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size()));
    destination.close();
    if (!destination) throw ParseError("texture fixture write failed");

    const auto converted = parseSummary(output, 0);
    if (converted.endian != Endian::Little || converted.engineVersion != 828 ||
        converted.savedEngineVersion != 8741 || converted.cookedContentVersion != 134 ||
        converted.names.count != static_cast<std::int32_t>(nameRemap.size()) ||
        converted.imports.count != 2 || converted.exports.count != 1 ||
        converted.names.offset != static_cast<std::int32_t>(nameOffset) ||
        converted.imports.offset != static_cast<std::int32_t>(importOffset) ||
        converted.exports.offset != static_cast<std::int32_t>(exportOffset) ||
        converted.dependsOffset != static_cast<std::int32_t>(dependsOffset) ||
        converted.totalHeaderSize != static_cast<std::int32_t>(totalHeaderSize)) {
      throw ParseError("independent texture fixture summary validation failed");
    }

    Reader verify(output, Endian::Little);
    std::vector<ManifestName> verifyNames;
    verify.seek(nameOffset);
    for (std::int32_t i = 0; i < converted.names.count; ++i) {
      verifyNames.push_back({verify.fstring(), verify.u64()});
    }
    if (verify.position() != importOffset) throw ParseError("emitted name table does not close exactly");
    std::vector<ManifestImport> verifyImports;
    for (int i = 0; i < 2; ++i) {
      ManifestImport value;
      value.classPackage = readNameRef(verify);
      value.className = readNameRef(verify);
      value.outerIndex = verify.i32();
      value.objectName = readNameRef(verify);
      verifyImports.push_back(value);
    }
    const auto validVerifyName = [&](NameRef ref) {
      return ref.index >= 0 && static_cast<std::size_t>(ref.index) < verifyNames.size();
    };
    for (const auto& value : verifyImports) {
      if (!validVerifyName(value.classPackage) || !validVerifyName(value.className) ||
          !validVerifyName(value.objectName) ||
          (value.outerIndex != 0 && value.outerIndex != -2)) {
        throw ParseError("emitted import contains an invalid name or outer reference");
      }
    }
    if (verify.position() != exportOffset) throw ParseError("emitted import table does not close exactly");
    ManifestExport verifyExport;
    verifyExport.classIndex = verify.i32();
    verifyExport.superIndex = verify.i32();
    verifyExport.outerIndex = verify.i32();
    verifyExport.objectName = readNameRef(verify);
    verifyExport.archetypeIndex = verify.i32();
    verifyExport.objectFlags = verify.u64();
    verifyExport.serialSize = verify.i32();
    verifyExport.serialOffset = verify.i32();
    verifyExport.exportFlags = verify.u32();
    if (checkedCount(verify, "fixture export generation") != 0) {
      throw ParseError("emitted texture export unexpectedly has generation counts");
    }
    for (auto& byte : verifyExport.packageGuid) byte = verify.u8();
    verifyExport.packageFlags = verify.u32();
    if (!validVerifyName(verifyExport.objectName)) {
      throw ParseError("emitted export contains an invalid object-name reference");
    }
    if (verify.position() != dependsOffset || checkedCount(verify, "fixture dependency") != 0 ||
        verify.position() != totalHeaderSize) {
      throw ParseError("emitted export/dependency tables do not close exactly");
    }
    const std::vector<ManifestExport> verifyExports{verifyExport};
    const ManifestResolver verifyResolver(output.stem().string(), verifyNames,
                                           verifyImports, verifyExports);
    if (verifyResolver.resourceName(verifyExport.classIndex) != "Texture2D" ||
        verifyExport.serialOffset != static_cast<std::int32_t>(totalHeaderSize) ||
        static_cast<std::uint64_t>(verifyExport.serialOffset) +
                static_cast<std::uint64_t>(verifyExport.serialSize) != bytes.size()) {
      throw ParseError("emitted Texture2D export boundary or class reference is invalid");
    }
    verify.seek(totalHeaderSize);
    if (verify.i32() != -1) throw ParseError("emitted Texture2D NetIndex is not standalone");
    NameRef verifyTerminator;
    std::vector<TaggedPropertyAnalysis> verifyProperties;
    (void)scanTaggedProperties(verify, 828, bytes.size(), verifyResolver,
                               verifyTerminator, &verifyProperties);
    if (!validVerifyName(verifyTerminator) || verifyResolver.name(verifyTerminator) != "None") {
      throw ParseError("emitted Texture2D property terminator is invalid");
    }
    for (const auto& property : verifyProperties) {
      if (!validVerifyName(property.name) || !validVerifyName(property.type) ||
          (property.hasExtraName && !validVerifyName(property.extraName)) ||
          (property.hasNameValue && !validVerifyName(property.nameValue))) {
        throw ParseError("emitted Texture2D property contains an invalid name reference");
      }
    }
    const auto verifySourceArt = scanBulkData(verify, bytes.size(), "fixture SourceArt");
    if (verifySourceArt.flags != 0 || verifySourceArt.elementCount != 0 ||
        verifySourceArt.sizeOnDisk != 0 ||
        verifySourceArt.offsetInFile != static_cast<std::int32_t>(verify.position())) {
      throw ParseError("emitted fixture SourceArt is not empty inline bulk");
    }
    if (checkedCount(verify, "fixture Texture2D mips") !=
        static_cast<std::int32_t>(linearMips.size())) {
      throw ParseError("emitted fixture mip count differs from the requested conversion scope");
    }
    for (std::size_t i = 0; i < linearMips.size(); ++i) {
      const auto mip = scanTextureMip(verify, bytes.size(), "fixture Texture2D mip");
      if (mip.bulkData.flags != 0 ||
          mip.bulkData.elementCount != static_cast<std::int32_t>(linearMips[i].size()) ||
          mip.bulkData.sizeOnDisk != static_cast<std::int32_t>(linearMips[i].size()) ||
          mip.sizeX != sourceMips[firstResident + i].sizeX ||
          mip.sizeY != sourceMips[firstResident + i].sizeY) {
        throw ParseError("emitted fixture mip metadata differs from the linear PC data");
      }
      const auto emitted = readFileRange(output,
          static_cast<std::uint64_t>(mip.bulkData.offsetInFile),
          static_cast<std::uint64_t>(mip.bulkData.sizeOnDisk));
      if (emitted != linearMips[i]) throw ParseError("emitted fixture mip bytes changed after writing");
    }
    std::array<std::uint8_t, 16> verifyGuid{};
    for (auto& byte : verifyGuid) byte = verify.u8();
    if (checkedCount(verify, "fixture cached PVRTC mips") != 0 ||
        verify.position() != bytes.size()) {
      throw ParseError("emitted Texture2D payload does not close at the export boundary");
    }

    std::cout << "Converted Texture2D fixture " << resolver.exportPath(requestedExport) << "\n"
              << "  source NetIndex: " << sourceNetIndex << " -> -1 (standalone fixture)\n"
              << "  properties:      6 preserved; TextureFileCacheName/FirstResourceMemMip removed\n"
              << "  mips:            " << linearMips.size() << " " << formatName
              << " levels, inline and uncompressed\n"
              << "  linear bytes:    ";
    for (std::size_t i = 0; i < linearMips.size(); ++i) {
      if (i != 0) std::cout << ", ";
      std::cout << linearMips[i].size();
    }
    std::cout << "\n"
              << "  MipTailBaseIdx:  " << mipTailProperty->intValue << " -> "
              << (linearMips.size() - 1) << "\n"
              << "  metadata:        " << nameRemap.size()
              << " names, 2 imports, 1 export; all references validated\n"
              << "  output:          " << output.string() << " (" << bytes.size() << " bytes)\n";
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << input.string() << ": texture fixture conversion failed: "
              << error.what() << '\n';
    return 1;
  }
}

int writeManifest(const fs::path& input, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty()) {
    std::cerr << input.string() << ": decompress the package before creating a manifest\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  std::vector<ManifestName> names;
  std::vector<ManifestImport> imports;
  std::vector<ManifestExport> exports;
  std::uint64_t namesEnd = 0;
  std::uint64_t importsEnd = 0;
  std::uint64_t exportsEnd = 0;
  try {
    Reader reader(input, summary.endian);
    reader.seek(static_cast<std::uint64_t>(summary.names.offset));
    names.reserve(static_cast<std::size_t>(summary.names.count));
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      names.push_back({reader.fstring(), reader.u64()});
    }
    namesEnd = reader.position();

    reader.seek(static_cast<std::uint64_t>(summary.imports.offset));
    imports.reserve(static_cast<std::size_t>(summary.imports.count));
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      ManifestImport value;
      value.classPackage = readNameRef(reader);
      value.className = readNameRef(reader);
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      imports.push_back(value);
    }
    importsEnd = reader.position();

    reader.seek(static_cast<std::uint64_t>(summary.exports.offset));
    exports.reserve(static_cast<std::size_t>(summary.exports.count));
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      ManifestExport value;
      value.classIndex = reader.i32();
      value.superIndex = reader.i32();
      value.outerIndex = reader.i32();
      value.objectName = readNameRef(reader);
      value.archetypeIndex = reader.i32();
      value.objectFlags = reader.u64();
      value.serialSize = reader.i32();
      value.serialOffset = reader.i32();
      value.exportFlags = reader.u32();
      const auto generationCount = checkedCount(reader, "export generation");
      value.generationNetObjectCount.reserve(static_cast<std::size_t>(generationCount));
      for (std::int32_t generation = 0; generation < generationCount; ++generation) {
        value.generationNetObjectCount.push_back(reader.i32());
      }
      for (auto& byte : value.packageGuid) byte = reader.u8();
      value.packageFlags = reader.u32();
      exports.push_back(std::move(value));
    }
    exportsEnd = reader.position();
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": metadata parse failed: " << error.what() << '\n';
    return 1;
  }

  std::size_t invalidNameRefs = 0;
  std::size_t invalidResourceRefs = 0;
  const auto checkName = [&](NameRef ref) {
    if (ref.index < 0 || static_cast<std::size_t>(ref.index) >= names.size()) ++invalidNameRefs;
  };
  const auto checkResource = [&](std::int32_t index) {
    if ((index > 0 && static_cast<std::size_t>(index) > exports.size()) ||
        (index < 0 && static_cast<std::size_t>(-index) > imports.size())) ++invalidResourceRefs;
  };
  for (const auto& value : imports) {
    checkName(value.classPackage);
    checkName(value.className);
    checkName(value.objectName);
    checkResource(value.outerIndex);
  }
  for (const auto& value : exports) {
    checkName(value.objectName);
    checkResource(value.classIndex);
    checkResource(value.superIndex);
    checkResource(value.outerIndex);
    checkResource(value.archetypeIndex);
    if (value.serialSize < 0 || value.serialOffset < 0 ||
        static_cast<std::uint64_t>(value.serialOffset) + static_cast<std::uint64_t>(value.serialSize) >
            fs::file_size(input)) {
      ++invalidResourceRefs;
    }
  }

  std::string packageName = input.stem().string();
  constexpr std::string_view reconstructedSuffix = ".uncompressed";
  if (packageName.ends_with(reconstructedSuffix)) {
    packageName.resize(packageName.size() - reconstructedSuffix.size());
  }
  const ManifestResolver resolver(packageName, names, imports, exports);

  std::vector<PackagePayloadAnalysis> packagePayloads(exports.size());
  std::vector<GuidCachePayloadAnalysis> guidCachePayloads(exports.size());
  std::vector<ObjectReferencerPayloadAnalysis> objectReferencerPayloads(exports.size());
  std::vector<Texture2DPayloadAnalysis> texture2DPayloads(exports.size());
  std::vector<SoundNodeWavePayloadAnalysis> soundNodeWavePayloads(exports.size());
  std::size_t packagePayloadsChecked = 0;
  std::size_t packagePayloadsCompatible = 0;
  std::size_t guidCachePayloadsChecked = 0;
  std::size_t guidCachePayloadsCompatible = 0;
  std::size_t objectReferencerPayloadsChecked = 0;
  std::size_t objectReferencerPayloadsCompatible = 0;
  std::size_t texture2DPayloadsChecked = 0;
  std::size_t texture2DPayloadsValid = 0;
  std::size_t soundNodeWavePayloadsChecked = 0;
  std::size_t soundNodeWavePayloadsValid = 0;
  for (std::size_t i = 0; i < exports.size(); ++i) {
    const auto className = resolver.resourceName(exports[i].classIndex);
    if (className == "Package") {
      auto& analysis = packagePayloads[i];
      analysis.examined = true;
      ++packagePayloadsChecked;
      try {
        Reader payloadReader(input, summary.endian);
        payloadReader.seek(static_cast<std::uint64_t>(exports[i].serialOffset));
        analysis.netIndex = payloadReader.i32();
        analysis.propertyTerminator = readNameRef(payloadReader);
        analysis.bytesConsumed = payloadReader.position() -
                                 static_cast<std::uint64_t>(exports[i].serialOffset);
        analysis.structurallyCompatible =
            exports[i].serialSize == 12 && analysis.bytesConsumed == 12 &&
            resolver.name(analysis.propertyTerminator) == "None" &&
            analysis.propertyTerminator.number == 0;
        if (analysis.structurallyCompatible) {
          ++packagePayloadsCompatible;
        } else {
          analysis.error = "expected exactly INT NetIndex followed by FName(None)";
        }
      } catch (const std::exception& error) {
        analysis.error = error.what();
      }
    } else if (className == "GuidCache") {
      auto& analysis = guidCachePayloads[i];
      analysis.examined = true;
      ++guidCachePayloadsChecked;
      try {
        Reader payloadReader(input, summary.endian);
        payloadReader.seek(static_cast<std::uint64_t>(exports[i].serialOffset));
        analysis.netIndex = payloadReader.i32();
        analysis.propertyTerminator = readNameRef(payloadReader);
        analysis.entryCount = checkedCount(payloadReader, "GuidCache map");
        for (std::int32_t entry = 0; entry < analysis.entryCount; ++entry) {
          const auto key = readNameRef(payloadReader);
          if (key.index < 0 || static_cast<std::size_t>(key.index) >= names.size()) {
            ++analysis.invalidNameReferences;
          }
          for (int guidPart = 0; guidPart < 4; ++guidPart) (void)payloadReader.u32();
        }
        analysis.bytesConsumed = payloadReader.position() -
                                 static_cast<std::uint64_t>(exports[i].serialOffset);
        analysis.structurallyCompatible =
            resolver.name(analysis.propertyTerminator) == "None" &&
            analysis.propertyTerminator.number == 0 && analysis.invalidNameReferences == 0 &&
            analysis.bytesConsumed == static_cast<std::uint64_t>(exports[i].serialSize);
        if (analysis.structurallyCompatible) {
          ++guidCachePayloadsCompatible;
        } else {
          analysis.error = "expected UObject header followed by complete TMap<FName, FGuid>";
        }
      } catch (const std::exception& error) {
        analysis.error = error.what();
      }
    } else if (className == "ObjectReferencer") {
      auto& analysis = objectReferencerPayloads[i];
      analysis.examined = true;
      ++objectReferencerPayloadsChecked;
      try {
        Reader payloadReader(input, summary.endian);
        const auto start = static_cast<std::uint64_t>(exports[i].serialOffset);
        payloadReader.seek(start);
        analysis.netIndex = payloadReader.i32();
        analysis.propertyName = readNameRef(payloadReader);
        analysis.propertyType = readNameRef(payloadReader);
        analysis.propertySize = payloadReader.i32();
        analysis.arrayIndex = payloadReader.i32();
        analysis.referencedObjectCount = checkedCount(payloadReader, "ReferencedObjects");
        for (std::int32_t reference = 0; reference < analysis.referencedObjectCount; ++reference) {
          const auto objectIndex = payloadReader.i32();
          if ((objectIndex > 0 && static_cast<std::size_t>(objectIndex) > exports.size()) ||
              (objectIndex < 0 && static_cast<std::size_t>(-objectIndex) > imports.size())) {
            ++analysis.invalidObjectReferences;
          }
        }
        analysis.propertyTerminator = readNameRef(payloadReader);
        analysis.bytesConsumed = payloadReader.position() - start;
        const auto expectedPropertySize = 4 + analysis.referencedObjectCount * 4;
        analysis.structurallyCompatible =
            resolver.name(analysis.propertyName) == "ReferencedObjects" &&
            analysis.propertyName.number == 0 &&
            resolver.name(analysis.propertyType) == "ArrayProperty" &&
            analysis.propertyType.number == 0 &&
            analysis.propertySize == expectedPropertySize && analysis.arrayIndex == 0 &&
            analysis.invalidObjectReferences == 0 &&
            resolver.name(analysis.propertyTerminator) == "None" &&
            analysis.propertyTerminator.number == 0 &&
            analysis.bytesConsumed == static_cast<std::uint64_t>(exports[i].serialSize);
        if (analysis.structurallyCompatible) {
          ++objectReferencerPayloadsCompatible;
        } else {
          analysis.error = "expected tagged ReferencedObjects ArrayProperty and FName(None)";
        }
      } catch (const std::exception& error) {
        analysis.error = error.what();
      }
    } else if (className == "Texture2D") {
      auto& analysis = texture2DPayloads[i];
      analysis.examined = true;
      ++texture2DPayloadsChecked;
      try {
        Reader payloadReader(input, summary.endian);
        const auto start = static_cast<std::uint64_t>(exports[i].serialOffset);
        const auto end = start + static_cast<std::uint64_t>(exports[i].serialSize);
        payloadReader.seek(start);
        analysis.netIndex = payloadReader.i32();
        analysis.taggedPropertyCount = scanTaggedProperties(
            payloadReader, summary.engineVersion, end, resolver, analysis.propertyTerminator,
            &analysis.taggedProperties);

        analysis.sourceArt = scanBulkData(payloadReader, end, "Texture2D source art");

        const auto mipCount = checkedCount(payloadReader, "Texture2D mips");
        analysis.mips.reserve(static_cast<std::size_t>(mipCount));
        for (std::int32_t mipIndex = 0; mipIndex < mipCount; ++mipIndex) {
          analysis.mips.push_back(scanTextureMip(
              payloadReader, end, "Texture2D mip " + std::to_string(mipIndex)));
        }

        if (summary.engineVersion >= 567) {
          if (payloadReader.position() + analysis.textureFileCacheGuid.size() > end) {
            throw ParseError("truncated Texture2D file-cache GUID");
          }
          for (auto& byte : analysis.textureFileCacheGuid) byte = payloadReader.u8();
        }

        if (summary.engineVersion >= 674) {
          const auto cachedPvrtcMipCount = checkedCount(payloadReader, "Texture2D cached PVRTC mips");
          analysis.cachedPvrtcMips.reserve(static_cast<std::size_t>(cachedPvrtcMipCount));
          for (std::int32_t mipIndex = 0; mipIndex < cachedPvrtcMipCount; ++mipIndex) {
            analysis.cachedPvrtcMips.push_back(scanTextureMip(
                payloadReader, end, "Texture2D cached PVRTC mip " + std::to_string(mipIndex)));
          }
        }

        analysis.bytesConsumed = payloadReader.position() - start;
        analysis.structurallyValid =
            resolver.name(analysis.propertyTerminator) == "None" &&
            analysis.propertyTerminator.number == 0 && payloadReader.position() == end;
        if (analysis.structurallyValid) {
          ++texture2DPayloadsValid;
        } else {
          analysis.error = "Texture2D data did not consume the complete export payload";
        }
      } catch (const std::exception& error) {
        analysis.error = error.what();
      }
    } else if (className == "SoundNodeWave") {
      auto& analysis = soundNodeWavePayloads[i];
      analysis.examined = true;
      ++soundNodeWavePayloadsChecked;
      try {
        Reader payloadReader(input, summary.endian);
        const auto start = static_cast<std::uint64_t>(exports[i].serialOffset);
        const auto end = start + static_cast<std::uint64_t>(exports[i].serialSize);
        payloadReader.seek(start);
        analysis.netIndex = payloadReader.i32();
        analysis.taggedPropertyCount = scanTaggedProperties(
            payloadReader, summary.engineVersion, end, resolver, analysis.propertyTerminator,
            &analysis.taggedProperties);
        analysis.bulkData.reserve(4);
        for (int bulkIndex = 0; bulkIndex < 4; ++bulkIndex) {
          analysis.bulkData.push_back(scanBulkData(payloadReader, end, "SoundNodeWave"));
        }
        analysis.bytesConsumed = payloadReader.position() - start;
        analysis.structurallyValid =
            resolver.name(analysis.propertyTerminator) == "None" &&
            analysis.propertyTerminator.number == 0 && analysis.bulkData.size() == 4 &&
            payloadReader.position() == end;
        if (analysis.structurallyValid) {
          ++soundNodeWavePayloadsValid;
        } else {
          analysis.error = "SoundNodeWave data did not consume the complete export payload";
        }
      } catch (const std::exception& error) {
        analysis.error = error.what();
      }
    }
  }

  std::error_code directoryError;
  if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
  std::ofstream stream(output, std::ios::binary | std::ios::trunc);
  if (!stream || directoryError) {
    std::cerr << output.string() << ": could not create manifest\n";
    return 1;
  }

  stream << "{\n  \"format\": \"judgment-native-metadata-v4\",\n"
         << "  \"source\": \"" << escapeJson(input.string()) << "\",\n"
         << "  \"byte_order\": \"" << (summary.endian == Endian::Big ? "big" : "little") << "\",\n"
         << "  \"package_version\": " << summary.engineVersion << ",\n"
         << "  \"saved_engine_version\": " << summary.savedEngineVersion << ",\n"
         << "  \"layout_validation\": {\n"
         << "    \"names_end\": " << namesEnd << ",\n"
         << "    \"imports_end\": " << importsEnd << ",\n"
         << "    \"expected_imports_end\": " << summary.exports.offset << ",\n"
         << "    \"exports_end\": " << exportsEnd << ",\n"
         << "    \"expected_exports_end\": " << summary.dependsOffset << ",\n"
         << "    \"invalid_name_references\": " << invalidNameRefs << ",\n"
         << "    \"invalid_resource_or_serial_references\": " << invalidResourceRefs << ",\n"
         << "    \"package_payloads_checked\": " << packagePayloadsChecked << ",\n"
         << "    \"package_payloads_v828_structurally_compatible\": "
         << packagePayloadsCompatible << ",\n"
         << "    \"guid_cache_payloads_checked\": " << guidCachePayloadsChecked << ",\n"
         << "    \"guid_cache_payloads_v828_structurally_compatible\": "
         << guidCachePayloadsCompatible << ",\n"
         << "    \"object_referencer_payloads_checked\": "
         << objectReferencerPayloadsChecked << ",\n"
         << "    \"object_referencer_payloads_v828_structurally_compatible\": "
         << objectReferencerPayloadsCompatible << ",\n"
         << "    \"texture2d_payloads_checked\": " << texture2DPayloadsChecked << ",\n"
         << "    \"texture2d_payloads_structurally_valid\": "
         << texture2DPayloadsValid << ",\n"
         << "    \"sound_node_wave_payloads_checked\": " << soundNodeWavePayloadsChecked
         << ",\n"
         << "    \"sound_node_wave_payloads_structurally_valid\": "
         << soundNodeWavePayloadsValid << "\n  },\n";

  stream << "  \"names\": [\n";
  for (std::size_t i = 0; i < names.size(); ++i) {
    if (i != 0) stream << ",\n";
    stream << "    {\"index\": " << i << ", \"name\": \"" << escapeJson(names[i].value)
           << "\", \"flags\": \"" << manifestHex64(names[i].flags) << "\"}";
  }
  stream << "\n  ],\n  \"imports\": [\n";
  for (std::size_t i = 0; i < imports.size(); ++i) {
    const auto& value = imports[i];
    if (i != 0) stream << ",\n";
    stream << "    {\"index\": " << i << ", \"package_index\": " << (-static_cast<std::int64_t>(i) - 1)
           << ", \"class_package\": \"" << escapeJson(resolver.name(value.classPackage))
           << "\", \"class_name\": \"" << escapeJson(resolver.name(value.className))
           << "\", \"outer_index\": " << value.outerIndex
           << ", \"object_name\": \"" << escapeJson(resolver.name(value.objectName))
           << "\", \"object_path\": \"" << escapeJson(resolver.importPath(i)) << "\"}";
  }
  stream << "\n  ],\n  \"exports\": [\n";
  for (std::size_t i = 0; i < exports.size(); ++i) {
    const auto& value = exports[i];
    if (i != 0) stream << ",\n";
    stream << "    {\"index\": " << i << ", \"package_index\": " << (i + 1)
           << ", \"class_index\": " << value.classIndex
           << ", \"class_name\": \"" << escapeJson(resolver.resourceName(value.classIndex))
           << "\", \"super_index\": " << value.superIndex
           << ", \"outer_index\": " << value.outerIndex
           << ", \"archetype_index\": " << value.archetypeIndex
           << ", \"object_name\": \"" << escapeJson(resolver.name(value.objectName))
           << "\", \"object_path\": \"" << escapeJson(resolver.exportPath(i))
           << "\", \"object_flags\": \"" << manifestHex64(value.objectFlags)
           << "\", \"serial_size\": " << value.serialSize
           << ", \"serial_offset\": " << value.serialOffset
           << ", \"export_flags\": \"" << hex32(value.exportFlags)
           << "\", \"generation_net_object_counts\": [";
    for (std::size_t generation = 0; generation < value.generationNetObjectCount.size(); ++generation) {
      if (generation != 0) stream << ", ";
      stream << value.generationNetObjectCount[generation];
    }
    stream << "], \"package_guid\": \"" << guidString(value.packageGuid)
           << "\", \"package_flags\": \"" << hex32(value.packageFlags) << "\"";
    const auto& payload = packagePayloads[i];
    if (payload.examined) {
      stream << ", \"payload_analysis\": {\"layout\": \"INT NetIndex + FName(None)\""
             << ", \"net_index\": " << payload.netIndex
             << ", \"property_terminator\": \""
             << escapeJson(resolver.name(payload.propertyTerminator)) << "\""
             << ", \"property_terminator_number\": " << payload.propertyTerminator.number
             << ", \"bytes_consumed\": " << payload.bytesConsumed
             << ", \"pc_v828_structurally_compatible\": "
             << (payload.structurallyCompatible ? "true" : "false");
      if (!payload.error.empty()) {
        stream << ", \"error\": \"" << escapeJson(payload.error) << "\"";
      }
      stream << "}";
    }
    const auto& guidCache = guidCachePayloads[i];
    if (guidCache.examined) {
      stream << ", \"payload_analysis\": {\"layout\": "
                "\"INT NetIndex + FName(None) + TMap<FName, FGuid>\""
             << ", \"net_index\": " << guidCache.netIndex
             << ", \"property_terminator\": \""
             << escapeJson(resolver.name(guidCache.propertyTerminator)) << "\""
             << ", \"entry_count\": " << guidCache.entryCount
             << ", \"invalid_name_references\": " << guidCache.invalidNameReferences
             << ", \"bytes_consumed\": " << guidCache.bytesConsumed
             << ", \"pc_v828_structurally_compatible\": "
             << (guidCache.structurallyCompatible ? "true" : "false");
      if (!guidCache.error.empty()) {
        stream << ", \"error\": \"" << escapeJson(guidCache.error) << "\"";
      }
      stream << "}";
    }
    const auto& objectReferencer = objectReferencerPayloads[i];
    if (objectReferencer.examined) {
      stream << ", \"payload_analysis\": {\"layout\": "
                "\"INT NetIndex + tagged ReferencedObjects ArrayProperty + FName(None)\""
             << ", \"net_index\": " << objectReferencer.netIndex
             << ", \"property_name\": \""
             << escapeJson(resolver.name(objectReferencer.propertyName)) << "\""
             << ", \"property_type\": \""
             << escapeJson(resolver.name(objectReferencer.propertyType)) << "\""
             << ", \"property_size\": " << objectReferencer.propertySize
             << ", \"array_index\": " << objectReferencer.arrayIndex
             << ", \"referenced_object_count\": "
             << objectReferencer.referencedObjectCount
             << ", \"invalid_object_references\": "
             << objectReferencer.invalidObjectReferences
             << ", \"property_terminator\": \""
             << escapeJson(resolver.name(objectReferencer.propertyTerminator)) << "\""
             << ", \"bytes_consumed\": " << objectReferencer.bytesConsumed
             << ", \"pc_v828_structurally_compatible\": "
             << (objectReferencer.structurallyCompatible ? "true" : "false");
      if (!objectReferencer.error.empty()) {
        stream << ", \"error\": \"" << escapeJson(objectReferencer.error) << "\"";
      }
      stream << "}";
    }
    const auto& texture2D = texture2DPayloads[i];
    if (texture2D.examined) {
      stream << ", \"payload_analysis\": {\"layout\": "
                "\"INT NetIndex + tagged properties + SourceArt bulk + Texture2D mips + "
                "file-cache GUID + cached PVRTC mips\""
             << ", \"net_index\": " << texture2D.netIndex
             << ", \"tagged_property_count\": " << texture2D.taggedPropertyCount
             << ", \"property_terminator\": \""
             << escapeJson(resolver.name(texture2D.propertyTerminator)) << "\""
             << ", \"tagged_properties\": [";
      for (std::size_t propertyIndex = 0;
           propertyIndex < texture2D.taggedProperties.size(); ++propertyIndex) {
        if (propertyIndex != 0) stream << ", ";
        const auto& property = texture2D.taggedProperties[propertyIndex];
        stream << "{\"name\": \"" << escapeJson(resolver.name(property.name))
               << "\", \"type\": \"" << escapeJson(resolver.name(property.type))
               << "\", \"size\": " << property.size
               << ", \"array_index\": " << property.arrayIndex
               << ", \"data_offset\": " << property.dataOffset;
        if (property.hasExtraName) {
          stream << ", \"extra_name\": \""
                 << escapeJson(resolver.name(property.extraName)) << "\"";
        }
        if (property.hasBoolValue) {
          stream << ", \"bool_value\": " << property.boolValue;
        }
        if (property.hasIntValue) {
          stream << ", \"int_value\": " << property.intValue;
        }
        if (property.hasNameValue) {
          stream << ", \"name_value\": \""
                 << escapeJson(resolver.name(property.nameValue)) << "\"";
        }
        if (property.hasByteValue) {
          stream << ", \"byte_value\": " << static_cast<unsigned>(property.byteValue);
        }
        stream << "}";
      }
      const auto writeBulk = [&](const BulkDataAnalysis& bulk) {
        stream << "{\"flags\": \"" << hex32(bulk.flags)
               << "\", \"element_count\": " << bulk.elementCount
               << ", \"size_on_disk\": " << bulk.sizeOnDisk
               << ", \"offset_in_file\": " << bulk.offsetInFile
               << ", \"inline\": " << (bulk.inlinePayload ? "true" : "false") << "}";
      };
      stream << "], \"source_art\": ";
      writeBulk(texture2D.sourceArt);
      stream << ", \"mips\": [";
      for (std::size_t mipIndex = 0; mipIndex < texture2D.mips.size(); ++mipIndex) {
        if (mipIndex != 0) stream << ", ";
        const auto& mip = texture2D.mips[mipIndex];
        stream << "{\"index\": " << mipIndex << ", \"size_x\": " << mip.sizeX
               << ", \"size_y\": " << mip.sizeY << ", \"bulk_data\": ";
        writeBulk(mip.bulkData);
        stream << "}";
      }
      stream << "], \"texture_file_cache_guid\": \""
             << guidString(texture2D.textureFileCacheGuid)
             << "\", \"cached_pvrtc_mips\": [";
      for (std::size_t mipIndex = 0; mipIndex < texture2D.cachedPvrtcMips.size(); ++mipIndex) {
        if (mipIndex != 0) stream << ", ";
        const auto& mip = texture2D.cachedPvrtcMips[mipIndex];
        stream << "{\"index\": " << mipIndex << ", \"size_x\": " << mip.sizeX
               << ", \"size_y\": " << mip.sizeY << ", \"bulk_data\": ";
        writeBulk(mip.bulkData);
        stream << "}";
      }
      stream << "], \"bytes_consumed\": " << texture2D.bytesConsumed
             << ", \"structurally_valid\": "
             << (texture2D.structurallyValid ? "true" : "false");
      if (!texture2D.error.empty()) {
        stream << ", \"error\": \"" << escapeJson(texture2D.error) << "\"";
      }
      stream << "}";
    }
    const auto& soundNodeWave = soundNodeWavePayloads[i];
    if (soundNodeWave.examined) {
      stream << ", \"payload_analysis\": {\"layout\": "
                "\"INT NetIndex + tagged properties + 4 FUntypedBulkData blocks\""
             << ", \"net_index\": " << soundNodeWave.netIndex
             << ", \"tagged_property_count\": " << soundNodeWave.taggedPropertyCount
             << ", \"property_terminator\": \""
             << escapeJson(resolver.name(soundNodeWave.propertyTerminator)) << "\""
             << ", \"tagged_properties\": [";
      for (std::size_t propertyIndex = 0;
           propertyIndex < soundNodeWave.taggedProperties.size(); ++propertyIndex) {
        if (propertyIndex != 0) stream << ", ";
        const auto& property = soundNodeWave.taggedProperties[propertyIndex];
        stream << "{\"name\": \"" << escapeJson(resolver.name(property.name))
               << "\", \"type\": \"" << escapeJson(resolver.name(property.type))
               << "\", \"size\": " << property.size
               << ", \"array_index\": " << property.arrayIndex
               << ", \"data_offset\": " << property.dataOffset;
        if (property.hasExtraName) {
          stream << ", \"extra_name\": \""
                 << escapeJson(resolver.name(property.extraName)) << "\"";
        }
        if (property.hasBoolValue) {
          stream << ", \"bool_value\": " << property.boolValue;
        }
        if (property.hasIntValue) {
          stream << ", \"int_value\": " << property.intValue;
        }
        if (property.hasNameValue) {
          stream << ", \"name_value\": \""
                 << escapeJson(resolver.name(property.nameValue)) << "\"";
        }
        if (property.hasByteValue) {
          stream << ", \"byte_value\": " << static_cast<unsigned>(property.byteValue);
        }
        stream << "}";
      }
      stream << "], \"bulk_data\": [";
      for (std::size_t bulkIndex = 0; bulkIndex < soundNodeWave.bulkData.size(); ++bulkIndex) {
        if (bulkIndex != 0) stream << ", ";
        const auto& bulk = soundNodeWave.bulkData[bulkIndex];
        stream << "{\"slot\": " << bulkIndex << ", \"flags\": \""
               << hex32(bulk.flags) << "\", \"element_count\": " << bulk.elementCount
               << ", \"size_on_disk\": " << bulk.sizeOnDisk
               << ", \"offset_in_file\": " << bulk.offsetInFile
               << ", \"inline\": " << (bulk.inlinePayload ? "true" : "false") << "}";
      }
      stream << "], \"bytes_consumed\": " << soundNodeWave.bytesConsumed
             << ", \"structurally_valid\": "
             << (soundNodeWave.structurallyValid ? "true" : "false");
      if (!soundNodeWave.error.empty()) {
        stream << ", \"error\": \"" << escapeJson(soundNodeWave.error) << "\"";
      }
      stream << "}";
    }
    stream << "}";
  }
  stream << "\n  ]\n}\n";
  stream.close();
  if (!stream) {
    std::cerr << output.string() << ": manifest write failed\n";
    fs::remove(output);
    return 1;
  }

  const bool importsExact = importsEnd == static_cast<std::uint64_t>(summary.exports.offset);
  const bool exportsExact = summary.dependsOffset == 0 ||
                            exportsEnd == static_cast<std::uint64_t>(summary.dependsOffset);
  std::cout << "Manifested " << names.size() << " names, " << imports.size() << " imports, "
            << exports.size() << " exports -> " << output.string() << '\n'
            << "  import layout: " << (importsExact ? "exact" : "MISMATCH") << " (end "
            << importsEnd << ", expected " << summary.exports.offset << ")\n"
            << "  export layout: " << (exportsExact ? "exact" : "MISMATCH") << " (end "
            << exportsEnd << ", expected " << summary.dependsOffset << ")\n"
            << "  invalid refs:  " << invalidNameRefs << " name, " << invalidResourceRefs
            << " resource/serial\n"
            << "  Package payloads: " << packagePayloadsCompatible << "/"
            << packagePayloadsChecked << " match the v828 UObject layout\n"
            << "  GuidCache payloads: " << guidCachePayloadsCompatible << "/"
            << guidCachePayloadsChecked << " match the v828 native layout\n"
            << "  ObjectReferencer payloads: " << objectReferencerPayloadsCompatible << "/"
            << objectReferencerPayloadsChecked << " match the v828 tagged-property layout\n"
            << "  Texture2D payloads: " << texture2DPayloadsValid << "/"
            << texture2DPayloadsChecked << " have valid tagged/bulk-data/mip framing\n"
            << "  SoundNodeWave payloads: " << soundNodeWavePayloadsValid << "/"
            << soundNodeWavePayloadsChecked << " have valid tagged/bulk-data framing\n";
  return importsExact && exportsExact && invalidNameRefs == 0 && invalidResourceRefs == 0 ? 0 : 1;
}

int convertGuidCache(const fs::path& input, const fs::path& output) {
  Summary summary;
  try {
    summary = parseSummary(input, 0);
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": " << error.what() << '\n';
    return 1;
  }
  if (summary.fullyCompressed || !summary.chunks.empty() || summary.compressionFlags != 0) {
    std::cerr << input.string() << ": GuidCache conversion requires an uncompressed package\n";
    return 1;
  }
  if (summary.endian != Endian::Big || summary.engineVersion != 845 ||
      summary.licenseeVersion != 0) {
    std::cerr << input.string() << ": expected a big-endian Judgment v845 package\n";
    return 1;
  }
  if (summary.exports.count != 1 || summary.imports.count != 2 ||
      (summary.importExportGuidsOffset > 0 &&
       summary.importExportGuidsOffset != summary.totalHeaderSize) ||
      summary.importGuidsCount != 0 ||
      summary.exportGuidsCount != 0 || summary.thumbnailTableOffset != 0) {
    std::cerr << input.string() << ": not the source-backed one-export GuidCache layout\n";
    return 1;
  }
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }

  std::vector<std::uint8_t> bytes;
  try {
    const auto size = fs::file_size(input);
    if (size > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
      throw ParseError("file is too large");
    }
    bytes.resize(static_cast<std::size_t>(size));
    std::ifstream source(input, std::ios::binary);
    source.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (!source) throw ParseError("could not read complete input");

    LittleEndianRewriter rewrite(input, summary.endian, bytes);
    rewrite.u32(kPackageTag);
    const auto pcPackedVersion = static_cast<std::uint32_t>(828u) |
                                 (static_cast<std::uint32_t>(summary.licenseeVersion) << 16);
    rewrite.u32(pcPackedVersion);
    rewrite.i32();  // TotalHeaderSize
    rewrite.fstring();
    rewrite.u32();  // PackageFlags
    for (int i = 0; i < 7; ++i) rewrite.i32();  // three tables and DependsOffset
    for (int i = 0; i < 3; ++i) rewrite.i32();  // cross-level GUID metadata
    rewrite.i32();  // ThumbnailTableOffset
    for (int i = 0; i < 4; ++i) rewrite.u32();  // package FGuid
    const auto generationCount = rewrite.i32();
    if (generationCount < 0 || static_cast<std::size_t>(generationCount) > kMaxArrayItems) {
      throw ParseError("invalid generation count");
    }
    for (std::int32_t i = 0; i < generationCount; ++i) {
      rewrite.i32();
      rewrite.i32();
      rewrite.i32();
    }
    rewrite.u32(8741u);  // Gears 3 PC saved-engine version
    rewrite.u32();       // cooked-content version (134 in both local builds)
    rewrite.u32(0u);     // compression flags
    const auto chunkCount = rewrite.i32(0);
    if (chunkCount != 0) throw ParseError("unexpected compressed chunks");
    rewrite.u32();  // PackageSource
    const auto additionalCount = rewrite.i32();
    if (additionalCount < 0 || static_cast<std::size_t>(additionalCount) > kMaxArrayItems) {
      throw ParseError("invalid additional-package count");
    }
    for (std::int32_t i = 0; i < additionalCount; ++i) rewrite.fstring();
    const auto textureAllocationCount = rewrite.i32();
    if (textureAllocationCount < 0 ||
        static_cast<std::size_t>(textureAllocationCount) > kMaxArrayItems) {
      throw ParseError("invalid texture-allocation count");
    }
    for (std::int32_t i = 0; i < textureAllocationCount; ++i) {
      for (int field = 0; field < 5; ++field) rewrite.i32();
      const auto exportCount = rewrite.i32();
      if (exportCount < 0 || static_cast<std::size_t>(exportCount) > kMaxArrayItems) {
        throw ParseError("invalid texture-allocation export count");
      }
      for (std::int32_t item = 0; item < exportCount; ++item) rewrite.i32();
    }
    if (rewrite.position() != summary.knownSummaryBytes ||
        summary.knownSummaryBytes != static_cast<std::uint64_t>(summary.names.offset)) {
      throw ParseError("summary does not end exactly at the name table");
    }

    std::vector<ManifestName> names;
    rewrite.seek(static_cast<std::uint64_t>(summary.names.offset));
    names.reserve(static_cast<std::size_t>(summary.names.count));
    for (std::int32_t i = 0; i < summary.names.count; ++i) {
      names.push_back({rewrite.fstring(), rewrite.u64()});
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.imports.offset)) {
      throw ParseError("name table does not end exactly at import table");
    }

    std::vector<ManifestImport> imports;
    imports.reserve(static_cast<std::size_t>(summary.imports.count));
    for (std::int32_t i = 0; i < summary.imports.count; ++i) {
      ManifestImport value;
      value.classPackage = rewriteNameRef(rewrite);
      value.className = rewriteNameRef(rewrite);
      value.outerIndex = rewrite.i32();
      value.objectName = rewriteNameRef(rewrite);
      imports.push_back(value);
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.exports.offset)) {
      throw ParseError("import table does not end exactly at export table");
    }

    std::vector<ManifestExport> exports;
    exports.reserve(static_cast<std::size_t>(summary.exports.count));
    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      ManifestExport value;
      value.classIndex = rewrite.i32();
      value.superIndex = rewrite.i32();
      value.outerIndex = rewrite.i32();
      value.objectName = rewriteNameRef(rewrite);
      value.archetypeIndex = rewrite.i32();
      value.objectFlags = rewrite.u64();
      value.serialSize = rewrite.i32();
      value.serialOffset = rewrite.i32();
      value.exportFlags = rewrite.u32();
      const auto exportGenerationCount = rewrite.i32();
      if (exportGenerationCount < 0 ||
          static_cast<std::size_t>(exportGenerationCount) > kMaxArrayItems) {
        throw ParseError("invalid export generation count");
      }
      for (std::int32_t generation = 0; generation < exportGenerationCount; ++generation) {
        value.generationNetObjectCount.push_back(rewrite.i32());
      }
      for (int guidPart = 0; guidPart < 4; ++guidPart) rewrite.u32();
      value.packageFlags = rewrite.u32();
      exports.push_back(std::move(value));
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.dependsOffset)) {
      throw ParseError("export table does not end exactly at dependency table");
    }

    for (std::int32_t i = 0; i < summary.exports.count; ++i) {
      const auto dependencyCount = rewrite.i32();
      if (dependencyCount < 0 ||
          static_cast<std::size_t>(dependencyCount) > kMaxArrayItems) {
        throw ParseError("invalid dependency count");
      }
      for (std::int32_t dependency = 0; dependency < dependencyCount; ++dependency) {
        rewrite.i32();
      }
    }
    if (rewrite.position() != static_cast<std::uint64_t>(summary.totalHeaderSize)) {
      throw ParseError("dependency table does not end exactly at payload boundary");
    }

    const ManifestResolver resolver(input.stem().string(), names, imports, exports);
    const auto& guidExport = exports.front();
    const auto logicalEnd = static_cast<std::uint64_t>(guidExport.serialOffset) +
                            static_cast<std::uint64_t>(guidExport.serialSize);
    if (resolver.resourceName(guidExport.classIndex) != "GuidCache" ||
        guidExport.serialOffset != summary.totalHeaderSize || guidExport.serialSize < 16 ||
        logicalEnd > bytes.size()) {
      throw ParseError("export is not an exact GuidCache payload");
    }

    rewrite.seek(static_cast<std::uint64_t>(guidExport.serialOffset));
    rewrite.i32();  // UObject NetIndex
    const auto terminator = rewriteNameRef(rewrite);
    if (resolver.name(terminator) != "None" || terminator.number != 0) {
      throw ParseError("GuidCache UObject properties do not end with FName(None)");
    }
    const auto mapCount = rewrite.i32();
    if (mapCount < 0 || static_cast<std::size_t>(mapCount) > kMaxArrayItems) {
      throw ParseError("invalid GuidCache map count");
    }
    for (std::int32_t i = 0; i < mapCount; ++i) {
      const auto packageName = rewriteNameRef(rewrite);
      if (packageName.index < 0 || static_cast<std::size_t>(packageName.index) >= names.size()) {
        throw ParseError("GuidCache map contains an invalid name reference");
      }
      for (int guidPart = 0; guidPart < 4; ++guidPart) rewrite.u32();
    }
    if (rewrite.position() != logicalEnd) {
      throw ParseError("GuidCache map does not consume the complete export payload");
    }
    bytes.resize(static_cast<std::size_t>(logicalEnd));  // discard Xbox DVD/ECC padding

    std::error_code directoryError;
    if (!output.parent_path().empty()) fs::create_directories(output.parent_path(), directoryError);
    if (directoryError) throw ParseError("could not create output directory");
    std::ofstream destination(output, std::ios::binary | std::ios::trunc);
    destination.write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size()));
    destination.close();
    if (!destination) {
      fs::remove(output);
      throw ParseError("output write failed");
    }

    const auto converted = parseSummary(output, 0);
    if (converted.endian != Endian::Little || converted.engineVersion != 828 ||
        converted.savedEngineVersion != 8741 || converted.cookedContentVersion != 134 ||
        converted.names.count != summary.names.count ||
        converted.imports.count != summary.imports.count ||
        converted.exports.count != summary.exports.count) {
      fs::remove(output);
      throw ParseError("converted package failed independent summary validation");
    }
    std::cout << "Converted GuidCache v845 Xbox -> v828 PC: " << mapCount
              << " FName/FGuid entries, " << bytes.size() << " bytes -> "
              << output.string() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << input.string() << ": GuidCache conversion failed: " << error.what() << '\n';
    return 1;
  }
}

struct InventoryKey {
  Endian endian{};
  bool fullyCompressed{};
  std::uint16_t engineVersion{};
  std::uint16_t licenseeVersion{};
  std::uint32_t compressionFlags{};
  auto operator<=>(const InventoryKey&) const = default;
};

bool packageExtension(fs::path path) {
  auto extension = path.extension().string();
  std::transform(extension.begin(), extension.end(), extension.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return extension == ".xxx" || extension == ".u" || extension == ".upk" ||
         extension == ".gear" || extension == ".udk";
}

int printInventory(const fs::path& root) {
  if (!fs::is_directory(root)) {
    std::cerr << root.string() << ": not a directory\n";
    return 1;
  }
  std::map<InventoryKey, std::size_t> groups;
  std::map<std::string, std::size_t> errors;
  std::map<std::string, std::vector<fs::path>> errorExamples;
  std::size_t candidates = 0;
  for (const auto& entry : fs::recursive_directory_iterator(
           root, fs::directory_options::skip_permission_denied)) {
    if (!entry.is_regular_file() || !packageExtension(entry.path())) continue;
    ++candidates;
    try {
      const auto summary = parseSummary(entry.path(), 0);
      ++groups[{summary.endian, summary.fullyCompressed, summary.engineVersion, summary.licenseeVersion,
                summary.compressionFlags}];
    } catch (const std::exception& error) {
      ++errors[error.what()];
      auto& examples = errorExamples[error.what()];
      if (examples.size() < 8) examples.push_back(entry.path());
    }
  }
  std::cout << "Inventory: " << root.string() << '\n'
            << "Candidates: " << candidates << '\n'
            << "Parsed:     ";
  std::size_t parsed = 0;
  for (const auto& [key, count] : groups) {
    (void)key;
    parsed += count;
  }
  std::cout << parsed << "\n\n"
            << "Count  Byte order  Version  Licensee  Storage       Flags\n";
  for (const auto& [key, count] : groups) {
    std::cout << std::left << std::setw(7) << count
              << std::setw(12) << (key.endian == Endian::Big ? "big" : "little")
              << std::setw(9) << (key.fullyCompressed ? "--" : std::to_string(key.engineVersion))
              << std::setw(10) << (key.fullyCompressed ? "--" : std::to_string(key.licenseeVersion))
              << std::setw(15) << (key.fullyCompressed ? "full container" : compressionName(key.compressionFlags))
              << hex32(key.compressionFlags) << '\n';
  }
  if (!errors.empty()) {
    std::cout << "\nUnparsed candidates:\n";
    for (const auto& [error, count] : errors) {
      std::cout << "  " << count << "  " << error << '\n';
      for (const auto& example : errorExamples[error]) {
        std::cout << "      " << example.string() << '\n';
      }
    }
  }
  return errors.empty() ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 1 && std::string_view(argv[1]) == "--decompress-container") {
    if (argc != 4) {
      usage();
      return 2;
    }
    return decompressContainer(argv[2], argv[3]);
  }
  if (argc > 1 && std::string_view(argv[1]) == "--decompress-package") {
    if (argc != 4) {
      usage();
      return 2;
    }
    return decompressPackage(argv[2], argv[3]);
  }
  if (argc > 1 && std::string_view(argv[1]) == "--extract-bulk") {
    if (argc != 8) {
      usage();
      return 2;
    }
    try {
      const auto offset = std::stoull(argv[3], nullptr, 0);
      const auto sizeOnDisk = std::stoull(argv[4], nullptr, 0);
      const auto elementCount = std::stoull(argv[5], nullptr, 0);
      const auto flagsValue = std::stoull(argv[6], nullptr, 0);
      if (flagsValue > std::numeric_limits<std::uint32_t>::max()) {
        throw std::out_of_range("bulk flags");
      }
      return extractBulkPayload(argv[2], offset, sizeOnDisk, elementCount,
                                static_cast<std::uint32_t>(flagsValue), argv[7]);
    } catch (...) {
      std::cerr << "bulk offset, sizes, and flags must be non-negative integers\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--detile-xbox360") {
    if (argc != 9) {
      usage();
      return 2;
    }
    try {
      const auto width = std::stoull(argv[3], nullptr, 0);
      const auto height = std::stoull(argv[4], nullptr, 0);
      const auto blockPixels = std::stoull(argv[5], nullptr, 0);
      const auto bytesPerBlock = std::stoull(argv[6], nullptr, 0);
      const auto endianUnit = std::stoull(argv[7], nullptr, 0);
      if (width > std::numeric_limits<std::uint32_t>::max() ||
          height > std::numeric_limits<std::uint32_t>::max() ||
          blockPixels > std::numeric_limits<std::uint32_t>::max() ||
          bytesPerBlock > std::numeric_limits<std::uint32_t>::max() ||
          endianUnit > std::numeric_limits<std::uint32_t>::max()) {
        throw std::out_of_range("Xbox 360 detile geometry");
      }
      return detileXbox360(argv[2], static_cast<std::uint32_t>(width),
                           static_cast<std::uint32_t>(height),
                           static_cast<std::uint32_t>(blockPixels),
                           static_cast<std::uint32_t>(bytesPerBlock),
                           static_cast<std::uint32_t>(endianUnit), argv[8]);
    } catch (...) {
      std::cerr << "Xbox 360 detile geometry must use non-negative integers\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--decode-dxt1-bmp") {
    if (argc != 6) {
      usage();
      return 2;
    }
    try {
      const auto width = std::stoull(argv[3], nullptr, 0);
      const auto height = std::stoull(argv[4], nullptr, 0);
      if (width > std::numeric_limits<std::uint32_t>::max() ||
          height > std::numeric_limits<std::uint32_t>::max()) {
        throw std::out_of_range("DXT1 dimensions");
      }
      return decodeDxt1Bmp(argv[2], static_cast<std::uint32_t>(width),
                           static_cast<std::uint32_t>(height), argv[5]);
    } catch (...) {
      std::cerr << "DXT1 dimensions must be non-negative integers\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--manifest") {
    if (argc != 4) {
      usage();
      return 2;
    }
    return writeManifest(argv[2], argv[3]);
  }
  if (argc > 1 && std::string_view(argv[1]) == "--extract-xma") {
    if (argc != 5) {
      usage();
      return 2;
    }
    try {
      return extractXma(argv[2], static_cast<std::size_t>(std::stoull(argv[3])), argv[4]);
    } catch (...) {
      std::cerr << argv[3] << ": export index must be a positive integer\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--convert-audio-fixture") {
    if (argc != 6) {
      usage();
      return 2;
    }
    try {
      return convertAudioFixture(argv[2], static_cast<std::size_t>(std::stoull(argv[3])),
                                 argv[4], argv[5]);
    } catch (...) {
      std::cerr << argv[3] << ": export index must be a positive integer\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--convert-audio-package") {
    if (argc != 5) {
      usage();
      return 2;
    }
    return convertAudioPackage(argv[2], argv[3], argv[4]);
  }
  if (argc > 1 && std::string_view(argv[1]) == "--convert-texture-fixture") {
    if (argc != 6) {
      usage();
      return 2;
    }
    try {
      return convertTextureFixture(argv[2],
          static_cast<std::size_t>(std::stoull(argv[3])), argv[4], argv[5], false);
    } catch (...) {
      std::cerr << argv[3] << ": export index must be a non-negative integer\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--convert-texture-fixture-full-mips") {
    if (argc != 6) {
      usage();
      return 2;
    }
    try {
      return convertTextureFixture(argv[2],
          static_cast<std::size_t>(std::stoull(argv[3])), argv[4], argv[5], true);
    } catch (...) {
      std::cerr << argv[3] << ": export index must be a non-negative integer\n";
      return 2;
    }
  }
  if (argc > 1 && std::string_view(argv[1]) == "--make-vorbis-time-test-fixture") {
    if (argc != 4) {
      usage();
      return 2;
    }
    return makeVorbisTimeTestFixture(argv[2], argv[3]);
  }
  if (argc > 1 && std::string_view(argv[1]) == "--convert-guid-cache") {
    if (argc != 4) {
      usage();
      return 2;
    }
    return convertGuidCache(argv[2], argv[3]);
  }
  bool json = false;
  std::optional<fs::path> inventoryRoot;
  std::size_t nameLimit = 8;
  std::vector<fs::path> paths;
  for (int i = 1; i < argc; ++i) {
    const std::string_view arg(argv[i]);
    if (arg == "--json") {
      json = true;
    } else if (arg == "--inventory") {
      if (++i >= argc) {
        usage();
        return 2;
      }
      inventoryRoot = fs::path(argv[i]);
    } else if (arg == "--names") {
      if (++i >= argc) {
        usage();
        return 2;
      }
      try {
        nameLimit = static_cast<std::size_t>(std::stoull(argv[i]));
      } catch (...) {
        std::cerr << "Invalid --names value\n";
        return 2;
      }
    } else if (arg == "--help" || arg == "-h") {
      usage();
      return 0;
    } else {
      paths.emplace_back(argv[i]);
    }
  }
  if (inventoryRoot) {
    if (json || !paths.empty()) {
      std::cerr << "--inventory cannot be combined with --json or package paths\n";
      return 2;
    }
    return printInventory(*inventoryRoot);
  }
  if (paths.empty()) {
    usage();
    return 2;
  }

  int failures = 0;
  for (std::size_t i = 0; i < paths.size(); ++i) {
    try {
      const auto summary = parseSummary(paths[i], nameLimit);
      if (json) {
        if (paths.size() > 1) std::cout << (i == 0 ? "[\n" : ",\n");
        printJson(paths[i], summary);
      } else {
        if (i != 0) std::cout << '\n';
        printHuman(paths[i], summary);
      }
    } catch (const std::exception& error) {
      ++failures;
      if (json) {
        if (paths.size() > 1) std::cout << (i == 0 ? "[\n" : ",\n");
        std::cout << "{\"path\": \"" << escapeJson(paths[i].string())
                  << "\", \"error\": \"" << escapeJson(error.what()) << "\"}\n";
      } else {
        std::cerr << paths[i].string() << ": " << error.what() << '\n';
      }
    }
  }
  if (json && paths.size() > 1) std::cout << "]\n";
  return failures == 0 ? 0 : 1;
}
