# Third-party code

## LZX decoder

`third_party/libmspack` contains UE Viewer's established libmspack LZX integration revision.
The underlying files are licensed under GNU LGPL version 2.1. A copy is included as
`COPYING.LIB`.

- Upstream source: <https://github.com/kyz/libmspack>
- Integration source: <https://github.com/gildor2/UEViewer/tree/master/libs/mspack>
- License: <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html>

The small `mspack_minimal.h` adapter is local glue that exposes only the system callbacks
needed by `lzxd.c`.
