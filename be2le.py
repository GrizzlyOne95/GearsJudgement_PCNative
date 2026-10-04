"""Convert a decompressed big-endian Judgment v845 package to little-endian, in place.

Byte-swapping preserves every field width, so the output is the SAME LENGTH as the input and
every offset in the summary stays valid. That is what makes this tractable: the conversion is a
field-wise swap, not a re-serialization. No version change is involved either -- the direct
loader reads v845 natively, so 845 stays 845 and only the byte order moves.

Layouts are taken from the Gears 3 September 2011 source, not guessed:

  FPackageFileSummary       Core\\Src\\UnLinker.cpp:307
  FObjectExport             Core\\Src\\UnLinker.cpp:197
  FObjectImport             Core\\Src\\UnLinker.cpp:246
  FGenerationInfo           Core\\Src\\UnLinker.cpp:293
  UObject::Serialize        Core\\Src\\UnObj.cpp:1600  (state frame, NetIndex, then properties)
  UComponent::PreSerialize  Core\\Src\\UnCoreNative.cpp:1212
  FStateFrame               Core\\Inc\\UnStack.h:336   (ProbeMask is DWORD, LatentAction is WORD)

The export payload prologue length follows from flags and class, and is NOT a constant:

    [component]   TemplateOwnerClass INT                    4
                  [+ CDO template]   TemplateName FName     8
    [RF_HasStack] Node + StateNode + ProbeMask + LatentAction + StateStack count
                                                            18
                  [+ Node != 0]      Offset INT             4
                  NetIndex INT                              4

which reproduces every prologue measured on real packages: 4 plain, 8 component,
16 CDO-component, 26 actor-with-stack. ProbeMask being a DWORD rather than a QWORD is the detail
that makes 26 come out right -- reading it as 8 bytes leaves StateStack looking like -1.

Struct property values are nested tag streams for non-atomic structs and raw bytes for atomic
ones (Guid, Vector, Color...). This walker tries the nested parse first and falls back to an
atomic table. Anything it cannot type -- unknown atomic structs, and array element types, which
live in the script packages rather than in the map -- is left UNSWAPPED and counted, so the
report says exactly what is still wrong instead of silently corrupting it.

Usage:
    python be2le.py <decompressed-be.xxx> <out-le.xxx> [array-index.json]

The optional array index comes from `array_types.py` and is what lets ArrayProperty values be
swapped; without it they are counted as unsupported and left big-endian.
"""
import collections
import json
import struct
import sys

# FaceFX SDK the Win32 runtime links (External\FaceFX\FxSDK: FxSDK.cpp FX_SDK_VERSION,
# FxVersionInfo.h FxFileFormatVersion). FxArchive refuses anything newer.
FACEFX_SDK_VERSION = 1740
FACEFX_FILE_FORMAT_VERSION = 0

# Property value widths that can be swapped without consulting the script packages.
SCALAR = {
    "IntProperty": [4], "FloatProperty": [4], "ObjectProperty": [4],
    "ComponentProperty": [4], "ClassProperty": [4], "InterfaceProperty": [4],
    "NameProperty": [4, 4], "QWordProperty": [8], "ByteProperty": [],
    "BoolProperty": [],
}

# Atomic (natively serialized) structs, as lists of scalar widths. Color is bytes: no swap.
ATOMIC_STRUCT = {
    "Guid": [4, 4, 4, 4], "Vector": [4, 4, 4], "Vector4": [4, 4, 4, 4],
    "Vector2D": [4, 4], "Rotator": [4, 4, 4], "LinearColor": [4, 4, 4, 4],
    "Quat": [4, 4, 4, 4], "Plane": [4, 4, 4, 4], "IntPoint": [4, 4],
    "Matrix": [4] * 16,
    # FBox is two FVectors plus a BYTE IsValid: a width of 1 is a no-op swap that keeps the
    # arithmetic check honest instead of needing a separate "trailing bytes" concept.
    "Box": [4] * 6 + [1],
    "Color": [],
}

# Core\Inc\UnObjBas.h:319, :367. These are 64-bit flags and the two live far apart -- do not
# guess them: RF_ClassDefaultObject is 0x200, NOT 0x10000.
RF_HAS_STACK = 0x0200000000000000
RF_CLASS_DEFAULT_OBJECT = 0x0000000000000200
PACKAGE_FILE_TAG_BE = b"\x9e\x2a\x83\xc1"


class Converter:
    def __init__(self, blob, array_types=None, track_references=False, array_owners=None):
        self.src = bytes(blob)
        self.out = bytearray(blob)
        self.unsupported = collections.Counter()
        self.stats = collections.Counter()
        # "PropertyName" -> {"elem":..., "struct":..., "widths":...}, from array_types.py.
        self.array_types = array_types or {}
        # Physical locations, not guessed integer values. Asset extraction uses
        # these typed fields to remap package indices without touching scalar data.
        self.object_reference_offsets = [] if track_references else None
        self.array_owners = array_owners or {}

    def try_region(self, off, end, attempt):
        """Run `attempt`; if it fails, restore the bytes and counters it touched.

        Without this, a failed type guess leaves the region half-swapped and the fallback
        path then swaps some of those bytes a second time -- silent corruption that looks
        like a successful conversion.
        """
        saved = bytes(self.out[off:end])
        stats, unsupported = collections.Counter(self.stats), collections.Counter(self.unsupported)
        reference_count = len(self.object_reference_offsets or [])
        if attempt():
            return True
        self.out[off:end] = saved
        self.stats, self.unsupported = stats, unsupported
        if self.object_reference_offsets is not None:
            del self.object_reference_offsets[reference_count:]
        return False

    # -- primitives ------------------------------------------------------
    def i32(self, off):
        return struct.unpack_from(">i", self.src, off)[0]

    def u64(self, off):
        return struct.unpack_from(">Q", self.src, off)[0]

    def valid_object_ref(self, value):
        """Validate a package index when payload-table bounds are available."""
        imports = getattr(self, "_import_count", None)
        exports = getattr(self, "_export_count", None)
        if imports is None or exports is None:
            return True
        return value == 0 or (0 < value <= exports) or (-imports <= value < 0)

    def record_object_ref(self, off):
        if self.object_reference_offsets is not None:
            if not self.valid_object_ref(self.i32(off)):
                raise ValueError("invalid extracted object reference at %d" % off)
            self.object_reference_offsets.append(off)

    def valid_fname(self, off):
        """Validate an FName's table index and nonnegative instance number when possible."""
        count = getattr(self, "_name_count", None)
        if count is None or off < 0 or off + 8 > len(self.src):
            return count is None
        index, number = self.i32(off), self.i32(off + 4)
        return 0 <= index < count and number >= 0

    def swap(self, off, width):
        self.out[off:off + width] = self.src[off:off + width][::-1]
        self.stats["scalars"] += 1

    def swap_seq(self, off, widths):
        for width in widths:
            self.swap(off, width)
            off += width
        return off

    def fstring(self, off):
        """FString: INT length; >0 ANSI including null, <0 UTF-16 of -length units."""
        length = self.i32(off)
        self.swap(off, 4)
        off += 4
        if length < 0:
            for i in range(-length):
                self.swap(off + i * 2, 2)
            return off + (-length) * 2
        return off + length

    def tarray(self, off, element):
        """TArray<T>: INT count then count elements; `element` advances past one element."""
        if off is None or off < 0 or off + 4 > len(self.src):
            return None
        count = self.i32(off)
        self.swap(off, 4)
        off += 4
        # Every serialized element consumes at least one byte in the layouts modelled here.
        # This bound prevents a speculative parse from spending minutes walking a bogus count.
        if count < 0 or count > len(self.src) - off:
            return None
        for _ in range(count):
            off = element(off)
            if off is None or off > len(self.src):
                return None
        return off

    def folder_len(self):
        length = self.i32(12)
        return 4 + (length if length >= 0 else (-length) * 2)

    def header_ints(self):
        """The 12 INTs after FolderName: flags, table counts/offsets, guid offsets, thumbnails."""
        return struct.unpack_from(">12i", self.src, 12 + self.folder_len())

    # -- header ----------------------------------------------------------
    def summary(self):
        off = self.swap_seq(0, [4, 4, 4])                # Tag, FileVersion, TotalHeaderSize
        off = self.fstring(off)                          # FolderName
        off = self.swap_seq(off, [4] * 12)
        off = self.swap_seq(off, [4, 4, 4, 4])           # Guid
        off = self.tarray(off, lambda p: self.swap_seq(p, [4, 4, 4]))      # Generations
        off = self.swap_seq(off, [4, 4, 4])              # Engine, CookedContent, CompressionFlags
        off = self.tarray(off, lambda p: self.swap_seq(p, [4, 4, 4, 4]))   # CompressedChunks
        off = self.swap_seq(off, [4])                    # PackageSource
        off = self.tarray(off, self.fstring)             # AdditionalPackagesToCook
        # FTextureAllocations: TArray<FTextureType>, each 5 INTs plus TArray<INT> ExportIndices.
        # Engine\Src\Texture2D.cpp:216. Real map packages populate this; only stub maps have none.
        self.tarray(off, self.texture_type)

    def texture_type(self, off):
        off = self.swap_seq(off, [4] * 5)                # SizeX, SizeY, NumMips, Format, Flags
        return self.tarray(off, lambda p: self.swap_seq(p, [4]))    # ExportIndices

    def tables(self):
        (_flags, name_count, name_off, export_count, export_off,
         import_count, import_off, depends_off, _ieg, _igc, _egc, _thumb) = self.header_ints()

        off = name_off
        for _ in range(name_count):
            off = self.fstring(off)
            self.swap(off, 8)                            # name flags QWORD
            off += 8

        off = import_off
        for _ in range(import_count):
            off = self.swap_seq(off, [4] * 7)            # 2 FNames, OuterIndex, FName

        exports = []
        off = export_off
        for _ in range(export_count):
            class_index, outer_index = self.i32(off), self.i32(off + 8)
            off = self.swap_seq(off, [4] * 6)            # Class, Super, Outer, ObjectName, Archetype
            flags = self.u64(off)
            self.swap(off, 8)                            # ObjectFlags QWORD
            off += 8
            size, offset = self.i32(off), self.i32(off + 4)
            off = self.swap_seq(off, [4, 4, 4])          # SerialSize, SerialOffset, ExportFlags
            off = self.tarray(off, lambda p: self.swap_seq(p, [4]))   # GenerationNetObjectCount
            off = self.swap_seq(off, [4] * 5)            # PackageGuid, PackageFlags
            exports.append((class_index, outer_index, flags, size, offset))

        if depends_off:
            off = depends_off
            for _ in range(export_count):
                off = self.tarray(off, lambda p: self.swap_seq(p, [4]))
        return exports

    def read_names(self):
        _f, name_count, name_off = self.header_ints()[:3]
        names, off = [], name_off
        for _ in range(name_count):
            length = self.i32(off)
            off += 4
            if length > 0:
                names.append(self.src[off:off + length - 1].decode("latin-1"))
                off += length
            else:
                names.append("")
                off += (-length) * 2
            off += 8
        return names

    def read_import_class_names(self, names):
        header = self.header_ints()
        import_count, import_off = header[5], header[6]
        out, off = [], import_off
        for _ in range(import_count):
            idx = self.i32(off + 20)                     # ObjectName index
            out.append(names[idx] if 0 <= idx < len(names) else "?")
            off += 28
        return out

    # -- payloads --------------------------------------------------------
    def prologue(self, is_component, template, flags, start):
        """Swap the native prologue fields; return the offset the tag stream starts at."""
        off = start
        if is_component:
            self.record_object_ref(off)
            self.swap(off, 4)                            # TemplateOwnerClass
            off += 4
            if template:
                off = self.swap_seq(off, [4, 4])         # TemplateName FName
        if flags & RF_HAS_STACK:
            self.record_object_ref(off)
            self.record_object_ref(off + 4)
            node = self.i32(off)
            off = self.swap_seq(off, [4, 4, 4, 2, 4])    # Node, StateNode, ProbeMask,
            if node != 0:                                # LatentAction, StateStack count
                off = self.swap_seq(off, [4])            # Offset
        return self.swap_seq(off, [4])                   # NetIndex

    def tags(self, names, off, end, depth=0, bool_properties=None, array_counts=None,
             property_ranges=None):
        """Swap a tagged-property stream. Returns the end position, or None if not one."""
        if not 0 <= off <= end <= len(self.src):
            return None
        while off < end:
            if off + 8 > end:
                return None
            idx = self.i32(off)
            if not 0 <= idx < len(names):
                return None
            if names[idx] == "None":
                self.swap_seq(off, [4, 4])
                return off + 8
            if off + 24 > end:
                return None
            type_idx = self.i32(off + 8)
            if not 0 <= type_idx < len(names) or self.i32(off + 12) != 0:
                return None
            type_name = names[type_idx]
            if not type_name.endswith("Property"):
                return None
            size, array_index = self.i32(off + 16), self.i32(off + 20)
            if size < 0 or array_index < 0:
                return None
            value, extra_name = off + 24, None
            if type_name in ("StructProperty", "ByteProperty"):
                if value + 8 > end:
                    return None
                extra_idx = self.i32(value)
                extra_name = names[extra_idx] if 0 <= extra_idx < len(names) else None
                value += 8
            elif type_name == "BoolProperty":
                value += 1
            if value + size > end:
                return None
            prop_name = names[idx]
            if property_ranges is not None:
                property_ranges[prop_name] = (type_name, extra_name, value, size)
            if bool_properties is not None and type_name == "BoolProperty":
                bool_properties[prop_name] = bool(self.src[value - 1])
            if array_counts is not None and type_name == "ArrayProperty" and size >= 4:
                array_counts[prop_name] = self.i32(value)
            self.swap_seq(off, [4] * 6)                  # Name, Type, Size, ArrayIndex
            if extra_name is not None:
                self.swap_seq(off + 24, [4, 4])
            self.value(names, type_name, extra_name, value, size, depth, prop_name)
            self.stats["tags"] += 1
            off = value + size
        return None

    def value(self, names, type_name, extra_name, off, size, depth, prop_name):
        if size == 0:
            return
        if type_name == "StrProperty":
            self.fstring(off)
            return
        if type_name == "ByteProperty":
            # UByteProperty::SerializeItem writes an FName when the property has an enum
            # (tag EnumName != None, Size 8) and a single byte otherwise. The enum case must be
            # swapped explicitly: SCALAR's empty width list would otherwise skip it silently.
            if size == 8 and extra_name not in (None, "None"):
                if 0 <= self.i32(off) < len(names) and self.i32(off + 4) >= 0:
                    self.swap_seq(off, [4, 4])
                else:
                    self.unsupported["ByteProperty enum value: bad FName"] += 1
            elif size != 1:
                self.unsupported["ByteProperty (size %d)" % size] += 1
            return
        if type_name in SCALAR:
            widths = SCALAR[type_name]
            if sum(widths) == size:
                if type_name in ("ObjectProperty", "ComponentProperty", "ClassProperty", "InterfaceProperty"):
                    # UInterfaceProperty serializes the object; the interface pointer is rebuilt.
                    for position in range(off, off + size, 4):
                        self.record_object_ref(position)
                self.swap_seq(off, widths)
            elif widths:
                self.unsupported["%s (size %d)" % (type_name, size)] += 1
            return
        if type_name == "StructProperty":
            self.struct_value(names, extra_name, off, size, depth)
            return
        if type_name == "ArrayProperty":
            self.array_value(names, off, size, depth, prop_name)
            return
        self.unsupported["%s (%dB)" % (type_name, size)] += 1

    def struct_value(self, names, extra_name, off, size, depth):
        """A struct value is a nested tag stream for script structs, raw bytes for atomic ones."""
        end = off + size
        if self.try_region(off, end,
                           lambda: self.tags(names, off, end, depth + 1) == end):
            return
        widths = ATOMIC_STRUCT.get(extra_name)
        if widths is not None and sum(widths) in (size, 0):
            self.swap_seq(off, widths)
            return
        if self.binary_struct(extra_name, off, end, exact=True, names=names) == end:
            return
        self.unsupported["struct %s (%dB)" % (extra_name, size)] += 1

    def array_value(self, names, off, size, depth, prop_name):
        """TArray value: INT count, then count elements typed by the script-package index."""
        count = self.i32(off)
        self.swap(off, 4)                                # the count is an INT regardless
        body, end = off + 4, off + size
        if count <= 0 or body >= end:
            return

        candidates = self.array_types.get(prop_name)
        if self.object_reference_offsets is not None:
            owner_key = getattr(self, "_current_class_name", "") + "." + prop_name
            candidates = self.array_owners.get(owner_key, candidates)
            if candidates and len(candidates) > 1:
                raise ValueError("ambiguous extracted array type: %s" % owner_key)
        if not candidates:
            self.unsupported["array %s: type unknown (%dB)" % (prop_name, size)] += 1
            return

        for entry in candidates:
            if self.array_with(names, entry, body, end, count, depth):
                self.stats["array_elements"] += count
                return
        self.unsupported["array %s: no candidate fits (%dB)" % (prop_name, size)] += 1

    def array_with(self, names, entry, body, end, count, depth):
        """Try one candidate element type. Returns False without writing if it does not fit."""
        widths = entry.get("widths")
        elem_type = entry.get("elem")
        if widths:
            # Arithmetic is the check: a wrong element type almost never divides evenly.
            if (end - body) != count * sum(widths):
                return False
            pos = body
            for _ in range(count):
                if elem_type in ("ObjectProperty", "ComponentProperty", "ClassProperty"):
                    self.record_object_ref(pos)
                elif self.object_reference_offsets is not None and elem_type == "StructProperty" and entry.get("struct") not in ATOMIC_STRUCT:
                    raise ValueError("untyped fixed-width struct references: %s" % entry.get("struct"))
                pos = self.swap_seq(pos, widths)
            return True

        if elem_type == "ByteProperty":
            # Plain byte arrays serialize one byte each; enum-backed bytes serialize FNames.
            if end - body == count:
                return True
            if end - body == count * 8:
                pos = body
                for _ in range(count):
                    pos = self.swap_seq(pos, [4, 4])
                return True
            return False
        primitive = {
            "BoolProperty": [],
            "IntProperty": [4], "FloatProperty": [4], "ObjectProperty": [4],
            "ClassProperty": [4], "NameProperty": [4, 4],
        }.get(elem_type)
        if primitive is not None:
            width = sum(primitive) if primitive else 1
            if end - body != count * width:
                return False
            if primitive:
                pos = body
                for _ in range(count):
                    if elem_type in ("ObjectProperty", "ComponentProperty", "ClassProperty"):
                        self.record_object_ref(pos)
                    pos = self.swap_seq(pos, primitive)
            return True
        if elem_type == "StrProperty":
            def walk_strings():
                pos = body
                for _ in range(count):
                    pos = self.fstring(pos)
                    if pos is None or pos > end:
                        return False
                return pos == end
            return self.try_region(body, end, walk_strings)
        if elem_type != "StructProperty":
            return False

        def walk_elements():
            # A tagged struct needs at least its 8-byte FName(None) terminator. A wrong
            # candidate can otherwise turn corrupt/random bytes into an enormous loop count.
            if count > (end - body) // 8:
                return False
            pos = body
            for _ in range(count):
                nxt = self.tags(names, pos, end, depth + 1)
                if nxt is None:
                    return False
                pos = nxt
            return pos == end

        if self.try_region(body, end, walk_elements):
            return True

        atomic = ATOMIC_STRUCT.get(entry.get("struct"))
        if atomic and (end - body) == count * sum(atomic):
            pos = body
            for _ in range(count):
                pos = self.swap_seq(pos, atomic)
            return True

        # ImmutableWhenCooked structs cook to binary SerializeBin form, not tag streams.
        # Every element must consume bytes without overrunning `end`, and the last one must
        # land exactly on it. The outer try_region keeps earlier elements' swaps from leaking
        # when a later element fails; the inner one rejects a wrong candidate per element.
        struct_name = entry.get("struct")
        if struct_name:
            def walk_binary():
                pos = body
                for _ in range(count):
                    nxt = self.binary_struct(struct_name, pos, end, names=names)
                    if nxt is None or nxt <= pos:
                        return False
                    pos = nxt
                return pos == end
            if self.try_region(body, end, walk_binary):
                return True
        return False

    def binary_struct(self, name, off, end=None, exact=False, names=None):
        """Walk persistent script fields at their serialized widths within a bounded region."""
        from immutable_cover import CoverWalker
        from native_animation import AimWalker
        from native_reader import NativeLayoutError
        end = len(self.src) if end is None else end
        result = {}
        def attempt():
            try:
                walker = AimWalker if name in AimWalker.STRUCTS else CoverWalker
                result["stop"] = walker(self, off, end, names).walk(name)
                return result["stop"] == end if exact else True
            except NativeLayoutError:
                return False
        return result["stop"] if self.try_region(off, end, attempt) else None

    # -- native tails ----------------------------------------------------
    # Per-class C++ serializers. Each returns the position it consumed up to, or None if it
    # cannot model the data; payloads() requires an EXACT landing on the payload end before
    # keeping the result, so a wrong model is rejected rather than written.

    def bulk(self, off, element=None):
        """TArray::BulkSerialize -> INT ElementSize, INT Count, then Count * ElementSize bytes.

        With no element model, a non-empty array fails: its elements are structs whose internal
        field widths are unknown here, and swapping them as opaque bytes would corrupt them.
        """
        element_size, count = self.i32(off), self.i32(off + 4)
        off = self.swap_seq(off, [4, 4])
        if count < 0 or element_size < 0:
            return None
        if count == 0:
            return off
        if element is None or sum(element) != element_size:
            return None
        for _ in range(count):
            off = self.swap_seq(off, element)
        return off

    def empty_bulk_retarget(self, off, source_element_size, target_element_size):
        """Retarget an empty BulkSerialize header when platform struct sizes differ.

        The element-size word is validated even when Count is zero.  Rewriting that word is
        safe only for an empty array; a populated array would require widening every element
        and rebuilding all following package offsets, so it deliberately fails closed.
        """
        if self.i32(off) != source_element_size or self.i32(off + 4) != 0:
            return None
        struct.pack_into("<i", self.out, off, target_element_size)
        self.stats["scalars"] += 1
        self.stats["bulk_element_sizes_retargeted"] += 1
        self.swap(off + 4, 4)
        return off + 8

    def byte_bulk_data(self, off, end):
        """Convert one FByteBulkData header and preserve byte-oriented payload data.

        The four fields are flags, element count, on-disk size, and absolute file offset.
        Inline payload bytes are codec data rather than host-endian scalars, so they remain
        untouched. External/unused entries carry no bytes at the current archive position.
        """
        if off is None or off < 0 or off + 16 > end:
            return None
        flags = struct.unpack_from(">I", self.src, off)[0]
        count, size, file_off = self.i32(off + 4), self.i32(off + 8), self.i32(off + 12)
        separate_file, unused = 1 << 0, 1 << 5
        unused_sentinel = ((flags & (separate_file | unused)) == (separate_file | unused)
                           and count == 0 and size == -1 and file_off == -1)
        if count < 0 or (size < 0 and not unused_sentinel) or (size > 0 and file_off < 0):
            return None
        data_off = off + 16
        inline = not (flags & separate_file) and size > 0
        if inline and (file_off != data_off or data_off + size > end):
            return None
        self.swap_seq(off, [4, 4, 4, 4])
        return data_off + size if inline else data_off

    def tail_polys(self, off, end):
        """UPolys::Serialize, UnFPoly.cpp:1381 -- DbNum, DbMax, ElementOwner + FPoly array.
        Empty Polys (12B) is common (SP_00). Non-empty (e.g., SP_E2_P 1092B =12+1080) contains
        TArray<FPoly> where each FPoly is Base 12 + Normal 12 + TextureU 12 + TextureV 12 +
        Vertices TArray<FVector> (count+12*Num) + PolyFlags 4 + Actor 4 + Material 4 + ... - for
        nullrhi load we can byte-swap every 4B word in the FPoly payload (floats as ints) which
        is correct for the whole array and keeps the export size unchanged.
        """
        size = end - off
        if size < 12:
            return None
        # DbNum, DbMax, ElementOwner
        off = self.swap_seq(off, [4, 4, 4])
        if off is None:
            return None
        remaining = end - off
        if remaining == 0:
            return off
        # For non-empty, remaining should be multiple of 4 (all fields are 4B-aligned)
        if remaining % 4 != 0:
            return None
        # Swap every 4B word in the FPoly data (covers Vertices count, FVector floats, etc.)
        for i in range(remaining // 4):
            self.swap(off + i * 4, 4)
        return end

    def tail_world(self, off, end):
        """UWorld::Serialize, UnWorld.cpp:84.

        The Levels/CurrentLevel/URL/NetDriver block is guarded by !IsLoading && !IsSaving, so it
        is absent from anything on disk. FLevelViewportInfo is FVector + FRotator + FLOAT = 28.
        """
        off = self.swap_seq(off, [4, 4])                 # PersistentLevel, PersistentFaceFXAnimSet
        for _ in range(4):
            off = self.swap_seq(off, [4] * 7)            # EditorViews[0..3]
        off = self.swap_seq(off, [4])                    # SaveGameSummary_DEPRECATED
        return self.tarray(off, lambda p: self.swap_seq(p, [4]))    # ExtraReferencedObjects

    def tail_model(self, off, end):
        """Bounded console UModel, including mixed-width BSP nodes and FVert records."""
        return self.tail_geometry(off, end, "model")

    def tmap(self, off, pair=None):
        """UE3 TMap serialises as its Pairs TArray: INT count, then count key/value pairs."""
        count = self.i32(off)
        self.swap(off, 4)
        if count == 0:
            return off + 4
        if pair is None:
            return None                                  # pair layout not modelled
        off += 4
        for _ in range(count):
            off = self.swap_seq(off, pair)
        return off

    def byte_array(self, off):
        """TArray<BYTE>: INT count then count raw bytes. Bytes need no swapping."""
        count = self.i32(off)
        self.swap(off, 4)
        return off + 4 + count if count >= 0 else None

    def opaque_array(self, off, element_size):
        """TArray of byte-oriented elements: swap the count, preserve element bytes."""
        if off is None or off < 0 or off + 4 > len(self.src) or element_size < 0:
            return None
        count = self.i32(off)
        self.swap(off, 4)
        data_off = off + 4
        if count < 0 or count > (len(self.src) - data_off) // max(element_size, 1):
            return None
        return data_off + count * element_size

    def apex_cached_blob(self, off):
        """Convert the APEX cache length and preserve only its ignored short sentinel bytes.

        ULevel::Serialize feeds cache data to APEX only when Size > 16. Values through 16 are
        consumed byte-by-byte and ignored, so their bytes are endian-neutral. A larger payload
        is platform-native APEX data and deliberately fails closed until explicitly modelled.
        """
        if off is None or off < 0 or off + 4 > len(self.src):
            return None
        size = self.i32(off)
        if size < 0 or size > 16 or off + 4 + size > len(self.src):
            return None
        self.swap(off, 4)
        return off + 4 + size

    def furl(self, off):
        """FURL, UnURL.cpp:79. Serialisation order is NOT the struct's memory order --
        Protocol, Host, Map, Portal, Op, Port, Valid (the PDB shows Port sitting between
        Host and Map in memory)."""
        for _ in range(4):                               # Protocol, Host, Map, Portal
            off = self.fstring(off)
        off = self.tarray(off, self.fstring)             # Op
        return self.swap_seq(off, [4, 4])                # Port, Valid

    def tail_level(self, off, end):
        """Bounded ULevelBase/ULevel layout, including populated maps and lighting."""
        return self.tail_geometry(off, end, "level")

    def tail_shader_cache(self, off, end):
        """Convert the empty seek-free cache emitted into Judgment's thin P-levels.

        At v845 UShaderCache::Load serialises ShaderCachePriority (INT), then
        FShaderCache::Load serialises Platform (BYTE), the compressed-code TMap count
        (INT), the shader-map count (INT), and finally UShaderCache::Load serialises the
        material-map count (INT).  A 17-byte tail is therefore an empty cache header,
        not Xbox shader microcode.

        Only accept the exact empty Xbox shape.  Populated caches need their shader data
        rebuilt for PC and deliberately remain unsupported.  The empty cache can safely
        be retargeted from SP_XBOXD3D (2) to SP_PCD3D_SM3 (0) without changing its size.

        A populated Xbox cache (> 17 bytes) keeps its platform byte and body untouched: the
        body is Xbox GPU microcode that no PC could use. The workspace engine recognises a
        foreign-platform cache in a Judgment package and seeks past it (ShaderCache.cpp,
        [JUDGSHADERCACHE]), so only ShaderCachePriority is converted.
        """
        if end - off > 17 and self.src[off + 4] == 2:
            self.swap_seq(off, [4])                      # ShaderCachePriority
            self.stats["xbox_shader_cache_skipped_by_engine"] += 1
            return end
        if end - off != 17 or self.src[off + 4] != 2:
            return None
        if any(self.i32(pos) != 0 for pos in (off + 5, off + 9, off + 13)):
            return None
        off = self.swap_seq(off, [4])                    # ShaderCachePriority
        self.out[off] = 0                                # Platform: Xbox -> PC D3D SM3
        self.stats["shader_platform_retargeted"] += 1
        off += 1
        return self.swap_seq(off, [4, 4, 4])             # empty compressed/shader/material maps

    def tail_sound_cue(self, off, end):
        """USoundCue::Serialize's stripped EditorData TMap (UnAudioNodes.cpp:200)."""
        if end - off != 4 or self.i32(off) != 0:
            return None
        return self.swap_seq(off, [4])                   # empty EditorData map

    def tail_sound_node_wave(self, off, end):
        """USoundNodeWave::Serialize: Raw, PC, Xbox360, and PS3 FByteBulkData slots.

        This makes Xbox-cooked waves structurally loadable but does not transcode XMA to Ogg.
        Runtime validation of such packages must use -nosound until PC audio is supplied.
        """
        for _ in range(4):
            off = self.byte_bulk_data(off, end)
            if off is None:
                return None
        return off

    def texture_mips(self, off, end):
        """Convert TIndirectArray<FTexture2DMipMap> framing, preserving opaque mip bytes."""
        if off is None or off + 4 > end:
            return None
        count = self.i32(off)
        self.swap(off, 4)
        off += 4
        if count < 0 or count > (end - off) // 24:
            return None
        for _ in range(count):
            off = self.byte_bulk_data(off, end)
            if off is None or off + 8 > end:
                return None
            off = self.swap_seq(off, [4, 4])            # SizeX, SizeY
        return off

    def tail_texture2d(self, off, end):
        """Structurally convert UTexture/UTexture2D native data without detiling pixels.

        SourceArt and mip allocations are byte-oriented bulk payloads. Their metadata, counts,
        dimensions and cache GUID are endian-converted; tiled Xbox pixels remain opaque. Use
        -nullrhi for runtime validation until the package-wide detiler supplies PC mip data.
        """
        off = self.byte_bulk_data(off, end)              # UTexture::SourceArt
        off = self.texture_mips(off, end)                # UTexture2D::Mips
        if off is None or off + 16 > end:
            return None
        off = self.swap_seq(off, [4, 4, 4, 4])           # TextureFileCacheGuid
        return self.texture_mips(off, end)               # CachedPVRTCMips

    def tail_lightmap_texture(self, off, end):
        """ULightMapTexture2D adds a DWORD LightmapFlags after UTexture2D."""
        if end - off < 4:
            return None
        stop = self.tail_texture2d(off, end - 4)
        if stop != end - 4:
            return None
        return self.swap_seq(stop, [4])

    def tail_geometry(self, off, end, method):
        from native_geometry import GeometryWalker
        from native_reader import NativeLayoutError
        try:
            return getattr(GeometryWalker(self, off, end), method)()
        except NativeLayoutError:
            return None

    def tail_static_component(self, off, end):
        return self.tail_geometry(off, end, "static_component")

    def tail_brush_component(self, off, end):
        return self.tail_geometry(off, end, "brush_component")

    def tail_light_component(self, off, end):
        return self.tail_geometry(off, end, "light_component")

    def tail_navigation(self, off, end, method="walk"):
        from native_navigation import NavigationWalker
        from native_reader import NativeLayoutError
        try:
            return getattr(NavigationWalker(self, off, end), method)()
        except NativeLayoutError:
            return None

    def tail_pylon(self, off, end):
        return self.tail_navigation(off, end, "pylon")

    def tail_combat_zone(self, off, end):
        if not getattr(self, "_native_bool_properties", {}).get("bCombatZoneBuilt", False):
            return None
        return self.tail_navigation(off, end, "combat_zone")

    def tail_animation(self, off, end):
        from native_animation import AnimationWalker
        from native_reader import NativeLayoutError
        try:
            return AnimationWalker(self, off, end).walk()
        except NativeLayoutError:
            return None

    def dominant_light_payload(self, off, end, names, template=False, flags=0):
        """Dominant lights serialize their WORD shadow array BEFORE Super/UObject."""
        from native_geometry import GeometryWalker
        from native_reader import NativeLayoutError

        def attempt():
            try:
                walker = GeometryWalker(self, off, end)
                walker.fixed_array([2])
                if flags & RF_HAS_STACK:
                    return False
                walker.need(24 if template else 16)  # prologue plus terminating FName
                start = self.prologue(True, template, flags, walker.pos)
                stop = self.tags(names, start, end)
                if stop is None:
                    return False
                return GeometryWalker(self, stop, end).light_component() == end
            except NativeLayoutError:
                return False

        return self.try_region(off, end, attempt)

    def tail_body_setup(self, off, end):
        return self.tail_geometry(off, end, "body_setup")

    def tail_model_component(self, off, end):
        return self.tail_geometry(off, end, "model_component")

    def tail_static_mesh(self, off, end):
        return self.tail_geometry(off, end, "static_mesh")

    def tail_shadow_map_1d(self, off, end):
        return self.tail_geometry(off, end, "shadow_map_1d")

    def tail_decal_component(self, off, end):
        return self.tail_geometry(off, end, "decal_component")

    def tail_fractured_mesh(self, off, end):
        return self.tail_geometry(off, end, "fractured_mesh")

    def tail_texture(self, off, end):
        return self.byte_bulk_data(off, end)

    def tail_collection(self, off, end, property_name):
        from native_geometry import GeometryWalker
        from native_reader import NativeLayoutError
        try:
            return GeometryWalker(self, off, end).collection(property_name)
        except NativeLayoutError:
            return None

    def tail_static_mesh_collection(self, off, end):
        return self.tail_collection(off, end, "StaticMeshComponents")

    def tail_static_light_collection(self, off, end):
        return self.tail_collection(off, end, "LightComponents")

    def tail_class(self, off, end):
        """Convert the cooked-console v845 UField/UStruct/UState/UClass payload.

        Class objects do not have a tagged-property stream after NetIndex. The persistent
        inheritance chain is serialized directly. Script bytecode needs an opcode-aware
        SerializeExpr walker, so this first implementation accepts only the four measured
        SP_E2_P classes whose logical and stored script sizes are both zero.
        """
        if off is None or off + 20 > end:
            return None
        if not all(self.valid_object_ref(self.i32(pos)) for pos in (off, off + 4, off + 8)):
            return None
        off = self.swap_seq(off, [4, 4, 4])               # Next, SuperStruct, Children
        logical_size, storage_size = self.i32(off), self.i32(off + 4)
        off = self.swap_seq(off, [4, 4])                  # ScriptBytecodeSize, ScriptStorageSize
        if logical_size != 0 or storage_size != 0:
            return None

        if off + 14 > end:
            return None
        off = self.swap_seq(off, [4, 2, 4])               # ProbeMask, LabelTableOffset, StateFlags

        def fname_object_map(pos):
            if pos + 4 > end:
                return None
            count = self.i32(pos)
            self.swap(pos, 4)
            pos += 4
            if count < 0 or count > (end - pos) // 12:
                return None
            for _ in range(count):
                if not self.valid_fname(pos) or not self.valid_object_ref(self.i32(pos + 8)):
                    return None
                pos = self.swap_seq(pos, [4, 4, 4])       # FName key, UObject value
            return pos

        off = fname_object_map(off)                       # UState::FuncMap
        if off is None or off + 16 > end:
            return None
        if not self.valid_object_ref(self.i32(off + 4)) or not self.valid_fname(off + 8):
            return None
        off = self.swap_seq(off, [4, 4, 4, 4])            # ClassFlags, ClassWithin, Config FName
        off = fname_object_map(off)                       # ComponentNameToDefaultObjectMap
        if off is None or off + 4 > end:
            return None

        interface_count = self.i32(off)
        self.swap(off, 4)
        off += 4
        if interface_count < 0 or interface_count > (end - off) // 8:
            return None
        for _ in range(interface_count):
            if not self.valid_object_ref(self.i32(off)) or not self.valid_object_ref(self.i32(off + 4)):
                return None
            off = self.swap_seq(off, [4, 4])              # Class, PointerProperty

        # Console-cooked packages omit editor-only category/header data. v845 is newer than
        # VER_SCRIPT_BIND_DLL_FUNCTIONS (655), so DLLBindName is always present here.
        if off + 12 > end:
            return None
        if not self.valid_fname(off) or not self.valid_object_ref(self.i32(off + 8)):
            return None
        return self.swap_seq(off, [4, 4, 4])              # DLLBindName FName, ClassDefaultObject

    def fmaterial(self, off, end):
        """FMaterial::Serialize (MaterialShared.cpp:1210); every scalar is four bytes."""
        off = self.tarray(off, self.fstring)                          # CompileErrors
        if off is None:
            return None
        def dependency(p):
            self.record_object_ref(p)
            return self.swap_seq(p, [4, 4])
        off = self.tarray(off, dependency)  # TextureDependencyLengthMap
        if off is None or off + 24 > end:
            return None
        off = self.swap_seq(off, [4, 4, 4, 4, 4, 4])     # MaxTextureDependencyLength, Id, NumUserTexCoords
        def texture(p):
            self.record_object_ref(p)
            return self.swap_seq(p, [4])
        off = self.tarray(off, texture)     # UniformExpressionTextures
        if off is None or off + 24 > end:
            return None
        # bUsesSceneColor, bUsesSceneDepth, bUsesDynamicParameter, bUsesLightmapUVs,
        # bUsesMaterialVertexPositionOffset (UBOOLs serialize as DWORDs), UsingTransforms.
        off = self.swap_seq(off, [4] * 6)
        off = self.tarray(off, lambda p: self.swap_seq(p, [4, 4, 4, 4]))  # TextureLookups
        if off is None or off + 4 > end:
            return None
        return self.swap_seq(off, [4])                   # DummyDroppedFallbackComponents

    def tail_material(self, off, end):
        """UMaterial::Serialize: the SM3 FMaterialResource only (VER_REMOVED_SHADER_MODEL_2)."""
        return self.fmaterial(off, end)

    def tail_material_instance(self, off, end):
        """UMaterialInstance::Serialize: nothing unless bHasStaticPermutationResource, then the
        FMaterialResource plus FStaticParameterSet (MaterialShared.h:1643)."""
        if off == end:
            return end
        off = self.fmaterial(off, end)
        if off is None or off + 16 > end:
            return None
        off = self.swap_seq(off, [4, 4, 4, 4])            # BaseMaterialId
        for element in ([4, 4, 4, 4, 4, 4, 4, 4],        # StaticSwitch: Name, Value, bOverride, GUID
                        [4, 4] + [4] * 5 + [4] * 4,        # ComponentMask: Name, RGBA, bOverride, GUID
                        [4, 4, 1, 4, 4, 4, 4, 4],          # Normal: Name, BYTE CompressionSettings, bOverride, GUID
                        [4, 4, 4, 4, 4, 4, 4, 4]):         # TerrainLayerWeight: Name, Index, bOverride, GUID
            off = self.tarray(off, lambda p, widths=element: self.swap_seq(p, widths))
            if off is None:
                return None
        return off

    def tail_physics_asset_instance(self, off, end):
        """UPhysicsAssetInstance::Serialize (UnPhysAsset.cpp:1925): CollisionDisableTable,
        TMap<FRigidBodyIndexPair (INT Indices[2]), UBOOL>."""
        if off + 4 > end or not 0 <= self.i32(off) <= (end - off - 4) // 12:
            return None
        return self.tmap(off, [4, 4, 4])

    def tail_skeletalmesh(self, off, end):
        """Precisely walk the v845 console skeleton, LODs, influences and trailer.

        Packed vertices retain their disk format; the isolated PC loader expands
        positions after loading. Unknown widths/storage modes fail and roll back.
        """
        from skeletal_mesh import MeshLayoutError, SkeletalMeshWalker
        try:
            return SkeletalMeshWalker(self, off, end,
                                     getattr(self, "_skeletal_mesh_has_vertex_colors", False)).walk()
        except MeshLayoutError:
            return None

    def tail_facefx(self, off, end):
        """UFaceFXAnimSet / UFaceFXAsset::Serialize: two TArray<BYTE> (UnFaceFXAnimSet.cpp:348).

        The first array is a FaceFX FxArchive that records its own byte order ('FACB' = big
        endian) and is byte-swapped by the FaceFX SDK while loading, so its bytes stay opaque;
        only the UE3 array counts are swapped. The second array is the (mini)session blob,
        which FaceFX reads the same way. Only the version this engine's SDK accepts is taken.
        """
        pos = off
        for index in range(2):
            if pos + 4 > end:
                return None
            count = self.i32(pos)
            if count < 0 or pos + 4 + count > end:
                return None
            body = pos + 4
            if count:
                # FxArchive header: magic, SDK version, file-format version (FxArchive.cpp:298).
                if count < 12 or self.src[body:body + 3] != b"FAC" or self.src[body + 3:body + 4] not in (b"B", b"E"):
                    return None
                big_endian = self.src[body + 3:body + 4] == b"B"
                sdk, file_format = struct.unpack_from(">II" if big_endian else "<II", self.src, body + 4)
                if sdk > FACEFX_SDK_VERSION or file_format > FACEFX_FILE_FORMAT_VERSION:
                    return None
            self.swap(pos, 4)
            pos = body + count
            self.stats["facefx_archives_kept_opaque"] += 1 if count else 0
        return pos

    def tail_generic(self, off, end):
        """Fallback for unmodelled native tails: byte-swap every 4B word.
        Many native tails are just TArrays of ints/floats or structs of ints/floats,
        so swapping every 4B word is correct for the Ints/Floats and harmless for the
        few byte fields (which are preserved via the 1B width handling in ATOMIC_STRUCT).
        Handles any size by swapping the aligned 4B prefix and leaving the 1-3 byte tail.
        """
        size = end - off
        if size < 0:
            return None
        aligned = (size // 4) * 4
        for i in range(aligned // 4):
            self.swap(off + i*4, 4)
        # Trailing 1-3 bytes are byte-oriented (e.g., FColor, BYTE) - no swap needed, but still need to account for them
        return end

    def tail_morph_target(self, off, end):
        """UMorphTarget: TArray<FMorphTargetLODModel> (delta, packed normal, index per vertex; base count)."""
        from native_reader import BoundedNativeWalker, NativeLayoutError
        walker = BoundedNativeWalker(self, off, end)
        def lod():
            walker.fixed_array([4, 4, 4, 4, 4])  # FVector PositionDelta, FPackedNormal, DWORD SourceIdx
            walker.fields([4])  # NumBaseMeshVerts
        try:
            walker.array(lod, 8)
        except NativeLayoutError:
            return None
        return walker.pos

    def tail_morph_target_set(self, off, end):
        """UMorphTargetSet: TArray<TArray<DWORD>> RawWedgePointIndices (emptied by the cooker)."""
        from native_reader import BoundedNativeWalker, NativeLayoutError
        walker = BoundedNativeWalker(self, off, end)
        try:
            walker.array(lambda: walker.fixed_array([4]), 4)
        except NativeLayoutError:
            return None
        return walker.pos

    def tail_single_int(self, off, end):
        """Convert an exact one-INT native tail (empty container count or object reference)."""
        if end - off != 4:
            return None
        return self.swap_seq(off, [4])

    NATIVE_TAILS = {"Polys": "tail_polys", "World": "tail_world", "Model": "tail_model",
                    "NavigationMeshBase": "tail_navigation", "Pylon": "tail_pylon",
                    "CombatZone": "tail_combat_zone", "AnimSequence": "tail_animation",
                    "SkeletalMesh": "tail_skeletalmesh",
                    "MorphTarget": "tail_morph_target", "MorphTargetSet": "tail_morph_target_set",
                    "FaceFXAnimSet": "tail_facefx", "FaceFXAsset": "tail_facefx",
                    "Material": "tail_material",
                    "DecalMaterial": "tail_material", "StaticMesh": "tail_static_mesh",
                    "FracturedStaticMesh": "tail_fractured_mesh",
                    "PhysicsAssetInstance": "tail_physics_asset_instance",
                    "MaterialInstanceConstant": "tail_material_instance",
                    "MaterialInstanceTimeVarying": "tail_material_instance",
                    "Level": "tail_level", "ShaderCache": "tail_shader_cache",
                    "SoundCue": "tail_sound_cue", "SoundNodeWave": "tail_sound_node_wave",
                    "Texture2D": "tail_texture2d", "ShadowMapTexture2D": "tail_texture2d",
                    "TextureRenderTarget2D": "tail_texture", "TextureRenderTargetCube": "tail_texture",
                    "LightMapTexture2D": "tail_lightmap_texture",
                    "RB_BodySetup": "tail_body_setup", "BrushComponent": "tail_brush_component",
                    "StaticMeshComponent": "tail_static_component", "SeqAct_Interp": "tail_single_int",
                    "FracturedStaticMeshComponent": "tail_static_component",
                    "ShadowMap1D": "tail_shadow_map_1d", "DecalComponent": "tail_decal_component",
                    "ModelComponent": "tail_model_component",
                    "PointLightComponent": "tail_light_component", "SpotLightComponent": "tail_light_component",
                    "DirectionalLightComponent": "tail_light_component", "SkyLightComponent": "tail_light_component",
                    "StaticMeshCollectionActor": "tail_static_mesh_collection",
                    "StaticLightCollectionActor": "tail_static_light_collection",
                    "ObjectRedirector": "tail_single_int"}
    NATIVE_PAYLOADS = {"Class": "tail_class"}

    def native_tail(self, class_name, off, end):
        """Swap a modelled tail only when its serializer lands exactly on `end`.

        Unknown tails keep their original bytes and are counted as unsupported.
        """
        method = self.NATIVE_TAILS.get(class_name)
        result = {}
        def attempt_specific():
            result["stop"] = getattr(self, method)(off, end) if method else None
            return result["stop"] == end
        if method and self.try_region(off, end, attempt_specific):
            return True
        # Whitelist for generic fallback - intentionally empty to preserve the
        # proven 1407/26 baseline (see CONTENT-CONVERSION-SURFACE.md Session XVI).
        # Enabling generic 4B swaps for the 26 unmodelled tails (Material, Model,
        # SkeletalMesh, etc.) was tried in v3aad and introduced a 37 MB
        # FArchive read regression (UClass huge Length). Keep it fail-closed
        # until each tail has a per-class model.
        generic_whitelist = set()  # was {"MaterialInstanceConstant", ...}
        if class_name not in generic_whitelist:
            return False
        # ShaderCache populated 17B case must stay fail-closed (test expects it), only allow generic for large caches (>17)
        if class_name == "ShaderCache" and (end - off) == 17:
            return False
        def attempt_generic():
            result["stop"] = self.tail_generic(off, end)
            return result["stop"] == end
        return self.try_region(off, end, attempt_generic)

    def native_payload(self, class_name, off, end):
        """Swap a fully native payload after the ordinary UObject prologue."""
        method = self.NATIVE_PAYLOADS.get(class_name)
        if method is None:
            return False
        return self.try_region(off, end, lambda: getattr(self, method)(off, end) == end)

    def is_template(self, exports, index):
        """UObject::IsTemplate(RF_ClassDefaultObject) walks the OUTER chain, not just self.

        UComponent::PreSerialize serialises TemplateName only for templates, so a component that
        merely *lives inside* an archetype has an 8-byte-longer prologue than its own flags
        suggest. That is the difference between prologue 8 and prologue 16.
        """
        seen = set()
        while index > 0 and index - 1 < len(exports) and index not in seen:
            seen.add(index)
            entry = exports[index - 1]
            if entry[2] & RF_CLASS_DEFAULT_OBJECT:
                return True
            index = entry[1]
        return False

    def payloads(self, exports, names, class_of):
        self._names = names
        self._name_count = len(names)
        self._import_count = self.header_ints()[5]
        self._export_count = len(exports)
        for position, (class_index, outer_index, flags, size, offset) in enumerate(exports):
            if size <= 0:
                continue
            unsupported_before = sum(self.unsupported.values())
            class_name = class_of(class_index)
            self._current_class_name = class_name
            template = bool(flags & RF_CLASS_DEFAULT_OBJECT) or self.is_template(exports, outer_index)
            end = offset + size
            if class_name in ("DominantDirectionalLightComponent", "DominantSpotLightComponent"):
                if self.dominant_light_payload(offset, end, names, template, flags):
                    self.stats["dominant_light_payload_converted"] += 1
                    self.stats["converted" if sum(self.unsupported.values()) == unsupported_before else "partial"] += 1
                else:
                    self.unsupported["native payload: %s (%dB)" % (class_name, size)] += 1
                    self.stats["native"] += 1
                continue
            if class_name in self.NATIVE_PAYLOADS:
                # UClass serializes its UField/UStruct/UState/UClass hierarchy directly after
                # UObject's prologue; interpreting UField::Next as a property-name index is wrong.
                native_start = self.prologue(False, template, flags, offset)
                if self.native_payload(class_name, native_start, end):
                    self.stats["native_payload_converted"] += 1
                    self.stats["converted"] += 1
                else:
                    self.unsupported["native payload: %s (%dB)" % (class_name, size)] += 1
                    self.stats["native"] += 1
                continue
            # Whether an object is a UComponent cannot be read off its class name: UE3's
            # Distribution* classes derive from UComponent without saying so, and getting this
            # wrong shifts the whole tag stream by 4 bytes. Try the name-based guess first, then
            # the alternative, and keep whichever yields a parsable stream.
            guess = "Component" in class_name
            stop = None
            for is_component in (guess, not guess):
                result = {}

                def attempt(is_component=is_component, result=result):
                    start = self.prologue(is_component, template, flags, offset)
                    result["bools"] = {}
                    result["arrays"] = {}
                    result["properties"] = {}
                    result["stop"] = self.tags(names, start, end, bool_properties=result["bools"],
                                               array_counts=result["arrays"], property_ranges=result["properties"])
                    return result["stop"] is not None

                if self.try_region(offset, end, attempt):
                    stop = result["stop"]
                    if is_component != guess:
                        self.stats["prologue_corrected"] += 1
                    break
            if stop is None:
                # Neither variant parsed: fall back to the guess so the prologue is still swapped.
                self.prologue(guess, template, flags, offset)
            if stop is None:
                # No tag stream at all: the whole payload is native data.
                self.unsupported["native payload: %s (%dB)" % (class_name, size)] += 1
                self.stats["native"] += 1
            elif stop < end:
                # Tags terminated, but native data follows. Its layout is per-class C++, so it
                # needs an explicit model; without one the bytes stay big-endian.
                self._skeletal_mesh_has_vertex_colors = result["bools"].get("bHasVertexColors", False)
                self._native_array_counts = result["arrays"]
                self._native_bool_properties = result["bools"]
                self._native_property_ranges = result["properties"]
                if self.native_tail(class_name, stop, end):
                    self.stats["native_tail_converted"] += 1
                    if sum(self.unsupported.values()) == unsupported_before:
                        self.stats["converted"] += 1
                    else:
                        self.stats["partial"] += 1
                else:
                    self.unsupported["native tail: %s (%dB)" % (class_name, end - stop)] += 1
                    self.stats["native_tail"] += 1
            else:
                if sum(self.unsupported.values()) == unsupported_before:
                    self.stats["converted"] += 1
                else:
                    self.stats["partial"] += 1


def load_array_types(index_path):
    """Collapse the "Owner.Property" index to property-name -> [candidate element types].

    The tag stream records only the property name, and the declaring class may be a superclass
    of the object being converted, so resolving by owner would need the full script hierarchy.
    Collapsing by name is safe because the converter validates each candidate against
    count * element width and rolls back on failure, so a wrong candidate is rejected rather
    than written. Keeping candidates instead of discarding collisions matters: `Materials` alone
    is 2,644 arrays in one level and has four different declarations.
    """
    with open(index_path) as handle:
        table = json.load(handle)
    by_name = {}
    for key, candidates in table.items():
        name = key.rsplit(".", 1)[-1]
        bucket = by_name.setdefault(name, [])
        for entry in candidates:
            if entry not in bucket:
                bucket.append(entry)
    # Try fixed-width candidates first: they are validated by exact arithmetic.
    for bucket in by_name.values():
        bucket.sort(key=lambda e: 0 if e.get("widths") else 1)
    multi = sum(1 for bucket in by_name.values() if len(bucket) > 1)
    return by_name, multi


def main(src_path, out_path, index_path=None):
    with open(src_path, "rb") as handle:
        blob = handle.read()
    if blob[:4] != PACKAGE_FILE_TAG_BE:
        raise SystemExit("not a big-endian UE3 package (still compressed?)")

    array_types, dropped = {}, 0
    if index_path:
        array_types, dropped = load_array_types(index_path)
        print("array index: %d property names (%d with several declarations)"
              % (len(array_types), dropped))

    conv = Converter(blob, array_types)
    names = conv.read_names()
    import_names = conv.read_import_class_names(names)

    def class_of(class_index):
        if class_index < 0 and -class_index - 1 < len(import_names):
            return import_names[-class_index - 1]
        return "Class" if class_index == 0 else "?"

    conv.summary()
    exports = conv.tables()
    conv.payloads(exports, names, class_of)

    with open(out_path, "wb") as handle:
        handle.write(conv.out)

    print("wrote %s (%d bytes, same length as input)" % (out_path, len(conv.out)))
    print("  exports fully converted: %d (incl. %d native tails)   partial: %d   "
          "unmodelled tail: %d   fully native: %d"
          % (conv.stats["converted"], conv.stats["native_tail_converted"],
             conv.stats["partial"], conv.stats["native_tail"], conv.stats["native"]))
    print("  tags swapped: %d   array elements: %d   scalars swapped: %d"
          % (conv.stats["tags"], conv.stats["array_elements"], conv.stats["scalars"]))
    if conv.unsupported:
        print("  LEFT UNSWAPPED:")
        for key, count in conv.unsupported.most_common(20):
            print("    %5dx %s" % (count, key))


if __name__ == "__main__":
    main(*sys.argv[1:4])
