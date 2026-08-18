cmake_minimum_required(VERSION 3.20)

project(judgment_package_probe LANGUAGES C CXX)

add_executable(judgment-package-probe
  src/main.cpp
  src/xmem_lzx.cpp
  third_party/libmspack/lzxd.c
)
target_compile_features(judgment-package-probe PRIVATE cxx_std_20)
target_include_directories(judgment-package-probe PRIVATE src third_party/libmspack)

if(MSVC)
  target_compile_options(judgment-package-probe PRIVATE /W4 /permissive-)
  set_source_files_properties(third_party/libmspack/lzxd.c PROPERTIES COMPILE_OPTIONS "/W0")
else()
  target_compile_options(judgment-package-probe PRIVATE -Wall -Wextra -Wpedantic)
endif()

set(GEARS3_SOURCE_ROOT
  "C:/Games/Gears 3 Files/gears_of_war_3_2011-09-14"
  CACHE PATH "Optional Gears 3 source/dev root used to build the source-matched Ogg cooker fixture")

set(GEARS3_VORBIS_ROOT "${GEARS3_SOURCE_ROOT}/Development/External/libvorbis-1.1.2")
set(GEARS3_OGG_ROOT "${GEARS3_SOURCE_ROOT}/Development/External/libogg-1.1.3")
set(GEARS3_LZO_ROOT "${GEARS3_SOURCE_ROOT}/Development/External/lzopro")
if(EXISTS "${GEARS3_LZO_ROOT}/include/lzo/lzopro/lzo1x.h"
   AND EXISTS "${GEARS3_LZO_ROOT}/lib/lzopro_64.lib")
  target_compile_definitions(judgment-package-probe PRIVATE HAVE_GEARS3_LZOPRO=1)
  target_include_directories(judgment-package-probe PRIVATE
    "${GEARS3_LZO_ROOT}/include"
    "${GEARS3_LZO_ROOT}/include/lzo")
  target_link_libraries(judgment-package-probe PRIVATE "${GEARS3_LZO_ROOT}/lib/lzopro_64.lib")
endif()
if(EXISTS "${GEARS3_VORBIS_ROOT}/include/vorbis/vorbisenc.h"
   AND EXISTS "${GEARS3_OGG_ROOT}/include/ogg/ogg.h"
   AND EXISTS "${GEARS3_VORBIS_ROOT}/win32/x64/Release/vorbisenc_64.lib")
  add_executable(judgment-wav-to-ogg src/wav_to_ogg.cpp)
  target_compile_features(judgment-wav-to-ogg PRIVATE cxx_std_20)
  target_include_directories(judgment-wav-to-ogg PRIVATE
    "${GEARS3_VORBIS_ROOT}/include"
    "${GEARS3_OGG_ROOT}/include")
  target_link_libraries(judgment-wav-to-ogg PRIVATE
    "${GEARS3_VORBIS_ROOT}/win32/x64/Release/vorbisenc_64.lib"
    "${GEARS3_VORBIS_ROOT}/win32/x64/Release/vorbis_64.lib"
    "${GEARS3_OGG_ROOT}/win32/x64/Release/ogg_64.lib")
  if(MSVC)
    target_compile_options(judgment-wav-to-ogg PRIVATE /W4 /permissive-)
    target_link_options(judgment-wav-to-ogg PRIVATE
      "/MANIFESTDEPENDENCY:type='win32' name='Microsoft.VC80.CRT' version='8.0.50727.9680' processorArchitecture='amd64' publicKeyToken='1fc8b3b9a1e18e3b'")
  endif()
  foreach(runtime_dll vorbisenc_64.dll vorbis_64.dll vorbisfile_64.dll)
    add_custom_command(TARGET judgment-wav-to-ogg POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${GEARS3_SOURCE_ROOT}/Binaries/Win64/${runtime_dll}"
        "$<TARGET_FILE_DIR:judgment-wav-to-ogg>")
  endforeach()
  add_custom_command(TARGET judgment-wav-to-ogg POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "${GEARS3_SOURCE_ROOT}/Binaries/Win64/ogg_64.dll"
      "$<TARGET_FILE_DIR:judgment-wav-to-ogg>")
endif()
