#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <ogg/ogg.h>
#include <vorbis/vorbisenc.h>

namespace fs = std::filesystem;

namespace {

struct Error : std::runtime_error {
  using std::runtime_error::runtime_error;
};

std::uint16_t littleU16(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
  if (offset + 2 > bytes.size()) throw Error("truncated WAV field");
  return static_cast<std::uint16_t>(bytes[offset] | (bytes[offset + 1] << 8));
}

std::uint32_t littleU32(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
  if (offset + 4 > bytes.size()) throw Error("truncated WAV field");
  return static_cast<std::uint32_t>(bytes[offset]) |
         (static_cast<std::uint32_t>(bytes[offset + 1]) << 8) |
         (static_cast<std::uint32_t>(bytes[offset + 2]) << 16) |
         (static_cast<std::uint32_t>(bytes[offset + 3]) << 24);
}

bool fourCC(const std::vector<std::uint8_t>& bytes, std::size_t offset, const char* expected) {
  return offset + 4 <= bytes.size() &&
         std::equal(bytes.begin() + static_cast<std::ptrdiff_t>(offset),
                    bytes.begin() + static_cast<std::ptrdiff_t>(offset + 4), expected);
}

struct Wave {
  std::uint16_t channels{};
  std::uint32_t sampleRate{};
  std::vector<std::int16_t> samples;
};

Wave readWave(const fs::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw Error("could not open input WAV");
  input.seekg(0, std::ios::end);
  const auto length = input.tellg();
  if (length < 0) throw Error("could not determine WAV size");
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
  input.seekg(0, std::ios::beg);
  input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
  if (!input || bytes.size() < 12 || !fourCC(bytes, 0, "RIFF") || !fourCC(bytes, 8, "WAVE")) {
    throw Error("input is not a RIFF/WAVE file");
  }

  std::size_t formatOffset = 0;
  std::size_t formatSize = 0;
  std::size_t dataOffset = 0;
  std::size_t dataSize = 0;
  for (std::size_t offset = 12; offset + 8 <= bytes.size();) {
    const auto size = static_cast<std::size_t>(littleU32(bytes, offset + 4));
    const auto payload = offset + 8;
    if (payload + size > bytes.size()) throw Error("WAV chunk exceeds file size");
    if (fourCC(bytes, offset, "fmt ")) {
      formatOffset = payload;
      formatSize = size;
    } else if (fourCC(bytes, offset, "data")) {
      dataOffset = payload;
      dataSize = size;
    }
    offset = payload + size + (size & 1u);
  }
  if (formatOffset == 0 || formatSize < 16 || dataOffset == 0) {
    throw Error("WAV lacks fmt or data chunk");
  }
  if (littleU16(bytes, formatOffset) != 1) throw Error("only PCM WAV input is supported");
  const auto channels = littleU16(bytes, formatOffset + 2);
  const auto sampleRate = littleU32(bytes, formatOffset + 4);
  const auto bits = littleU16(bytes, formatOffset + 14);
  if ((channels != 1 && channels != 2) || bits != 16 || sampleRate == 0) {
    throw Error("only mono or stereo 16-bit PCM WAV input is supported");
  }
  if ((dataSize & 1u) != 0 || dataSize / 2 > std::numeric_limits<std::size_t>::max()) {
    throw Error("invalid PCM data size");
  }
  Wave result;
  result.channels = channels;
  result.sampleRate = sampleRate;
  result.samples.reserve(dataSize / 2);
  for (std::size_t offset = dataOffset; offset < dataOffset + dataSize; offset += 2) {
    result.samples.push_back(static_cast<std::int16_t>(littleU16(bytes, offset)));
  }
  if (result.samples.size() % result.channels != 0) throw Error("incomplete PCM sample frame");
  return result;
}

void writePage(std::ofstream& output, const ogg_page& page) {
  output.write(reinterpret_cast<const char*>(page.header), page.header_len);
  output.write(reinterpret_cast<const char*>(page.body), page.body_len);
  if (!output) throw Error("Ogg output write failed");
}

void encode(const Wave& wave, int unrealQuality, const fs::path& outputPath) {
  // Matches FPCSoundCooker::Cook in the local Gears 3 UnAudioCompress.cpp.
  const float vorbisQuality = std::clamp((static_cast<float>(unrealQuality) - 15.0f) / 100.0f,
                                        -0.1f, 1.0f);
  vorbis_info info;
  vorbis_info_init(&info);
  if (vorbis_encode_init_vbr(&info, wave.channels, wave.sampleRate, vorbisQuality) != 0) {
    vorbis_info_clear(&info);
    throw Error("vorbis encoder rejected the channel/rate/quality combination");
  }
  vorbis_comment comment;
  vorbis_comment_init(&comment);
  char encoderTag[] = "ENCODER";
  char encoderValue[] = "UnrealEngine3";
  vorbis_comment_add_tag(&comment, encoderTag, encoderValue);
  vorbis_dsp_state dsp;
  vorbis_block block;
  ogg_stream_state stream;
  if (vorbis_analysis_init(&dsp, &info) != 0 || vorbis_block_init(&dsp, &block) != 0 ||
      ogg_stream_init(&stream, 0) != 0) {
    vorbis_comment_clear(&comment);
    vorbis_info_clear(&info);
    throw Error("could not initialize Vorbis analysis state");
  }

  std::ofstream output(outputPath, std::ios::binary | std::ios::trunc);
  if (!output) throw Error("could not create Ogg output");
  ogg_packet header;
  ogg_packet headerComment;
  ogg_packet headerCode;
  vorbis_analysis_headerout(&dsp, &comment, &header, &headerComment, &headerCode);
  ogg_stream_packetin(&stream, &header);
  ogg_stream_packetin(&stream, &headerComment);
  ogg_stream_packetin(&stream, &headerCode);
  ogg_page page;
  while (ogg_stream_flush(&stream, &page) != 0) writePage(output, page);

  constexpr std::size_t samplesPerBatch = 1024;
  const std::size_t frameCount = wave.samples.size() / wave.channels;
  for (std::size_t frame = 0;;) {
    const auto count = std::min(samplesPerBatch, frameCount - frame);
    if (count == 0) {
      vorbis_analysis_wrote(&dsp, 0);
    } else {
      float** buffer = vorbis_analysis_buffer(&dsp, static_cast<int>(samplesPerBatch));
      for (std::size_t i = 0; i < count; ++i) {
        for (std::size_t channel = 0; channel < wave.channels; ++channel) {
          buffer[channel][i] = static_cast<float>(
              wave.samples[(frame + i) * wave.channels + channel]) / 32768.0f;
        }
      }
      vorbis_analysis_wrote(&dsp, static_cast<int>(count));
      frame += count;
    }

    while (vorbis_analysis_blockout(&dsp, &block) == 1) {
      vorbis_analysis(&block, nullptr);
      vorbis_bitrate_addblock(&block);
      ogg_packet packet;
      while (vorbis_bitrate_flushpacket(&dsp, &packet) != 0) {
        ogg_stream_packetin(&stream, &packet);
        while (ogg_stream_pageout(&stream, &page) != 0) writePage(output, page);
      }
    }
    if (count == 0) break;
  }
  while (ogg_stream_flush(&stream, &page) != 0) writePage(output, page);
  output.close();
  ogg_stream_clear(&stream);
  vorbis_block_clear(&block);
  vorbis_dsp_clear(&dsp);
  vorbis_comment_clear(&comment);
  vorbis_info_clear(&info);
  if (!output) throw Error("Ogg output close failed");
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3 || argc > 4) {
    std::cout << "Usage: judgment-wav-to-ogg <input.wav> <output.ogg> [unreal-quality=40]\n";
    return 2;
  }
  const fs::path output(argv[2]);
  if (fs::exists(output)) {
    std::cerr << output.string() << ": refusing to overwrite an existing file\n";
    return 1;
  }
  try {
    int quality = 40;
    if (argc == 4) quality = std::stoi(argv[3]);
    if (quality < 1 || quality > 100) throw Error("quality must be between 1 and 100");
    const auto wave = readWave(argv[1]);
    encode(wave, quality, output);
    std::cout << "Encoded " << wave.samples.size() / wave.channels << " frame(s), "
              << wave.channels << " channel(s), " << wave.sampleRate << " Hz\n"
              << "  Unreal quality: " << quality << " (Vorbis "
              << std::clamp((static_cast<float>(quality) - 15.0f) / 100.0f, -0.1f, 1.0f)
              << ")\n"
              << "  output:         " << output.string() << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::error_code removeError;
    if (fs::exists(output)) fs::remove(output, removeError);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
