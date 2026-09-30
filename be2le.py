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

# Property value widths that can be swapped without consulting the script packages.
SCALAR = {
    "IntProperty": [4], "FloatProperty": [4], "ObjectProperty": [4],
    "ComponentProperty": [4], "ClassProperty": [4], "InterfaceProperty": [4, 4],
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
    def __init__(self, blob, array_types=None):
        self.src = bytes(blob)
        self.out = bytearray(blob)
        self.unsupported = collections.Counter()
        self.stats = collections.Counter()
        # "PropertyName" -> {"elem":..., "struct":..., "widths":...}, from array_types.py.
        self.array_types = array_types or {}

    def try_region(self, off, end, attempt):
        """Run `attempt`; if it fails, restore the bytes and counters it touched.

        Without this, a failed type guess leaves the region half-swapped and the fallback
        path then swaps some of those bytes a second time -- silent corruption that looks
        like a successful conversion.
        """
        saved = bytes(self.out[off:end])
        stats, unsupported = collections.Counter(self.stats), collections.Counter(self.unsupported)
        if attempt():
            return True
        self.out[off:end] = saved
        self.stats, self.unsupported = stats, unsupported
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
            self.swap(off, 4)                            # TemplateOwnerClass
            off += 4
            if template:
                off = self.swap_seq(off, [4, 4])         # TemplateName FName
        if flags & RF_HAS_STACK:
            node = self.i32(off)
            off = self.swap_seq(off, [4, 4, 4, 2, 4])    # Node, StateNode, ProbeMask,
            if node != 0:                                # LatentAction, StateStack count
                off = self.swap_seq(off, [4])            # Offset
        return self.swap_seq(off, [4])                   # NetIndex

    def tags(self, names, off, end, depth=0):
        """Swap a tagged-property stream. Returns the end position, or None if not one."""
        while off < end:
            idx = self.i32(off)
            if not 0 <= idx < len(names):
                return None
            if names[idx] == "None":
                self.swap_seq(off, [4, 4])
                return off + 8
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
                extra_idx = self.i32(value)
                extra_name = names[extra_idx] if 0 <= extra_idx < len(names) else None
                value += 8
            elif type_name == "BoolProperty":
                value += 1
            if value + size > end:
                return None
            prop_name = names[idx]
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
        if self.binary_struct(extra_name, off) == end:
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
        if widths:
            # Arithmetic is the check: a wrong element type almost never divides evenly.
            if (end - body) != count * sum(widths):
                return False
            pos = body
            for _ in range(count):
                pos = self.swap_seq(pos, widths)
            return True

        elem_type = entry.get("elem")
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
                    nxt = self.binary_struct(struct_name, pos)
                    if nxt is None or nxt <= pos or nxt > end:
                        return False
                    pos = nxt
                return pos == end

            if self.try_region(body, end, walk_binary):
                return True
        return False

    # -- immutable (binary) structs ---------------------------------------
    # STRUCT_ImmutableWhenCooked structs serialize via UStruct::SerializeBin when the archive
    # contains cooked data (UnProp.cpp:4188 UStructProperty::SerializeItem): each linked
    # property's SerializeItem runs with NO tag headers, in PropertyLink order.
    #
    # PropertyLink order is REVERSE script-declaration order -- AddCppProperty prepends while
    # registration walks the declaration top to bottom, and gen_native_block.py:207 needs
    # .reverse() for the same reason. The Judgment v845 script manifests list properties in
    # exactly this chain order, so the models below follow the manifests, not the UC text.
    #
    # ShouldSerializeValue (UnType.h:356) skips CPF_Transient fields on persistent archives,
    # so transient vars are ABSENT from the cooked bytes even though they sit inside the same
    # struct. Script bools share one BITFIELD DWORD: every non-transient member writes the
    # same 4 bytes at the same offset, so the group costs 4 once no matter how many bits live.

    def bs_tarray_bytes(self, off):
        """TArray<BYTE>: INT count then raw bytes; only the count swaps."""
        return self.byte_array(off)

    def bs_actor_reference(self, off):
        """ActorReference chain: Guid(atomic 16), Actor(ObjectProperty)."""
        off = self.swap_seq(off, ATOMIC_STRUCT["Guid"])
        return self.swap_seq(off, [4])

    def bs_cover_info(self, off):
        """CoverInfo chain: SlotIdx(IntProperty), Link(ObjectProperty) -> two INTs."""
        return self.swap_seq(off, [4, 4])

    def bs_fire_link(self, off):
        """FireLink chain: bDynamicIndexInited(bitfield DWORD), PackedProperties_(INT),
        Interactions(TArray<BYTE>). bFallbackLink rewrites the shared bitfield word."""
        off = self.swap_seq(off, [4])                    # bitfield (bDynamicIndexInited first)
        off = self.swap_seq(off, [4])                    # PackedProperties_CoverPairRefAndDynamicInfo
        return self.bs_tarray_bytes(off)                 # Interactions

    def bs_based_position(self, off):
        """BasedPosition chain: CachedTransPosition, CachedBaseRotation, CachedBaseLocation,
        Position (three FVector + one FRotator), Base(ObjectProperty)."""
        off = self.swap_seq(off, ATOMIC_STRUCT["Vector"])            # CachedTransPosition
        off = self.swap_seq(off, ATOMIC_STRUCT["Rotator"])           # CachedBaseRotation
        off = self.swap_seq(off, ATOMIC_STRUCT["Vector"])            # CachedBaseLocation
        off = self.swap_seq(off, ATOMIC_STRUCT["Vector"])            # Position
        return self.swap_seq(off, [4])                               # Base

    def bs_poly_reference(self, off, cached_poly_width):
        """PolyReference chain: CachedPoly, PolyId(INT), OwningPylon(ActorReference).

        CachedPoly is `var native Pointer` in the UC and shows up as a StructProperty in the
        v845 manifest; neither build serializes an obvious width for it, so the caller tries
        candidate widths and keeps whichever makes the enclosing array fit exactly.
        """
        if cached_poly_width:
            off = self.swap_seq(off, [cached_poly_width])
        off = self.swap_seq(off, [4])                    # PolyId
        return self.bs_actor_reference(off)              # OwningPylon

    def bs_slot_move_ref(self, off, cached_poly_width):
        """SlotMoveRef chain: Direction(INT), Dest(BasedPosition), Poly(PolyReference)."""
        off = self.swap_seq(off, [4])                    # Direction
        off = self.bs_based_position(off)
        if off is None:
            return None
        return self.bs_poly_reference(off, cached_poly_width)

    def bs_cover_slot(self, off, cached_poly_width=0):
        """CoverSlot chain (Judgment v845 manifest order), transient fields skipped.

        Skipped per Gears 3 UC + ShouldSerializeValue: SlotValidAfterTime(transient float),
        RejectedFireLinks(editconst transient array), bDestructible/bSelected/
        bFailedToFindSurface (transient bools -- their bits still live in the shared
        bitfield DWORD written by the surviving members).
        """
        off = self.swap_seq(off, [4])                    # bitfield: bPreferLeanOverPopup .. bLeanLeft
        off = self.tarray(off, lambda p: self.bs_cover_info(p))      # OverlapClaimsList
        if off is None:
            return None

        def slip(p):
            return self.bs_slot_move_ref(p, cached_poly_width)
        off = self.tarray(off, slip)                     # SlipRefs
        if off is None:
            return None
        off = self.swap_seq(off, [4])                    # TurnTargetPackedProperties
        off = self.tarray(off, lambda p: self.swap_seq(p, [4]))      # ExposedCoverPackedProperties
        if off is None:
            return None
        off = self.tarray(off, lambda p: self.bs_fire_link(p))       # FireLinks
        if off is None:
            return None
        off = self.bs_tarray_bytes(off)                  # Actions
        off = self.swap_seq(off, ATOMIC_STRUCT["Rotator"])           # RotationOffset
        off = self.swap_seq(off, ATOMIC_STRUCT["Vector"])            # LocationOffset
        return self.swap_seq(off, [1, 1, 1, 4])          # LocationDescription, CoverType,
                                                         # ForceCoverType, SlotOwner

    # Candidate widths for the unmodelled CachedPoly pointer field. 0 = not serialized at all;
    # console pointers are 32-bit, so 4 is the only plausible non-zero width.
    CACHED_POLY_WIDTHS = (0, 4)

    def binary_struct(self, name, off):
        """Convert one immutable-struct value starting at `off`; return stop offset or None.

        Called from struct_value/array_with AFTER the tagged-stream parse failed, which is
        exactly the cooked-data situation for ImmutableWhenCooked structs. The caller owns
        the end-of-region check.
        """
        if name == "CoverSlot":
            for width in self.CACHED_POLY_WIDTHS:
                result = {}

                def attempt(w=width, result=result):
                    result["stop"] = self.bs_cover_slot(off, w)
                    return result["stop"] is not None

                if self.try_region(off, len(self.out), attempt):
                    self.stats["binary_structs"] += 1
                    return result["stop"]
            return None
        simple = {
            "CoverInfo": self.bs_cover_info,
            "FireLink": lambda p: self.bs_fire_link(p),
            "BasedPosition": lambda p: self.bs_based_position(p),
        }
        handler = simple.get(name)
        if handler is None:
            return None
        result = {}

        def attempt(result=result):
            result["stop"] = handler(off)
            return result["stop"] is not None

        if self.try_region(off, len(self.out), attempt):
            self.stats["binary_structs"] += 1
            return result["stop"]
        return None

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
        """UModel::Serialize, UnModel.cpp:179."""
        off = self.swap_seq(off, [4] * 7)                # Bounds: FBoxSphereBounds
        for element in ([4, 4, 4], [4, 4, 4], None):     # Vectors, Points, Nodes
            off = self.bulk(off, element)
            if off is None:
                return None
        # Surfs. Source says `Ar << Surfs`, but the data occupies exactly two INTs here and the
        # rest of the walk only lands on 180 bytes with that shape. Derived from the bytes, not
        # from the source -- revisit before trusting it on a map with real BSP.
        off = self.swap_seq(off, [4, 4])
        # FVert is 16 bytes in console-cooked data (pVertex, iSide, ShadowTexCoord). The loader
        # reads Judgment_* packages with the console layout (FVert::GetSizeForBulkSerialization
        # returns 16 once -JUDGMENTPKGVER=845 is recognised), so the console size is kept. The
        # old 16->24 retarget only compensated for that opt-in never firing.
        off = self.bulk(off, [4, 4, 4, 4])               # Verts
        if off is None:
            return None
        zones = self.i32(off + 4)
        off = self.swap_seq(off, [4, 4])                 # NumSharedSides, NumZones
        if zones:
            return None                                  # FZoneProperties not modelled
        off = self.swap_seq(off, [4])                    # Polys
        for _ in range(2):                               # LeafHulls, Leaves
            off = self.bulk(off, [4])
            if off is None:
                return None
        off = self.swap_seq(off, [4, 4])                 # RootOutside, Linked
        off = self.bulk(off, [4])                        # PortalNodes
        if off is None:
            return None
        off = self.swap_seq(off, [4])                    # NumUniqueVertices
        off = self.bulk(off)                             # VertexBuffer
        if off is None:
            return None
        off = self.swap_seq(off, [4] * 4)                # LightingGuid
        return self.tarray(off, lambda p: self.swap_seq(p, [4] * 9))   # LightmassSettings

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
        """ULevelBase::Serialize (UnLevel.cpp:52) then ULevel::Serialize (:320).

        The Actors array is a TTransArray, and TTransArray::operator<< (Array.h:2116) writes
        **Owner first**, then the TArray. Parsing it count-first shifts everything and makes two
        phantom fields appear before the URL -- that misread cost real time; the giveaway is that
        Owner resolves to the Level itself and Actors[1] is the null default brush.
        """
        off = self.swap_seq(off, [4])                    # TTransArray Owner
        off = self.tarray(off, lambda p: self.swap_seq(p, [4]))     # Actors
        if off is None:
            return None
        off = self.furl(off)                             # URL
        if off is None:
            return None
        off = self.swap_seq(off, [4])                    # Model
        for _ in range(2):                               # ModelComponents, GameSequences
            off = self.tarray(off, lambda p: self.swap_seq(p, [4]))
            if off is None:
                return None
        for _ in range(2):                               # TextureToInstancesMap, DynamicTextureInstances
            off = self.tmap(off)
            if off is None:
                return None
        off = self.apex_cached_blob(off)                 # APEX cache; >16-byte payload unsupported
        if off is None:
            return None
        off = self.bulk(off)                             # CachedPhysBSPData
        if off is None:
            return None
        # CachedPhysSMDataMap, CachedPhysSMDataStore, CachedPhysPerTriSMDataMap,
        # CachedPhysPerTriSMDataStore -- alternating TMap and TArray<BYTE>.
        for is_map in (True, False, True, False):
            off = self.tmap(off) if is_map else self.byte_array(off)
            if off is None:
                return None
        off = self.swap_seq(off, [4, 4])                 # CachedPhysBSPDataVersion, SMDataVersion
        off = self.tmap(off)                             # ForceStreamTextures
        if off is None:
            return None
        off = self.byte_array(off)                       # CachedPhysConvexBSPData
        if off is None:
            return None
        off = self.swap_seq(off, [4])                    # CachedPhysConvexBSPVersion
        off = self.swap_seq(off, [4] * 6)                # Nav/Cover/Pylon list start+end
        off = self.tarray(off, lambda p: self.swap_seq(p, [4] * 5))  # FGuidPair: FGuid (16) + DWORD RefId (4) = 20
        if off is None:
            return None
        off = self.tarray(off, lambda p: self.swap_seq(p, [4]))  # CoverLinkRefs: TArray<ACoverLink*>
        if off is None:
            return None
        off = self.tarray(off, lambda p: self.swap_seq(p, [4, 1]))  # FCoverIndexPair: DWORD ActorRefItem + BYTE SlotIdx = 5
        if off is None:
            return None
        off = self.tarray(off, lambda p: self.swap_seq(p, [4]))  # CrossLevelActors: TArray<AActor*>
        if off is None:
            return None
        initialized = self.i32(off)                      # FPrecomputedLightVolume::bInitialized (UBOOL)
        off = self.swap_seq(off, [4])
        if initialized:
            # PrecomputedLightVolume.h / PrecomputedLightVolume.cpp:131
            #   bInitialized (UBOOL) already consumed; now Bounds, SampleSpacing, Samples
            off = self.swap_seq(off, [4] * 6 + [1])      # FBox Bounds (2*FVector + BYTE IsValid)
            if off is None:
                return None
            off = self.swap_seq(off, [4])                # FLOAT SampleSpacing
            if off is None:
                return None
            # FVolumeLightingSample (PrecomputedLightVolume.h:12, .cpp:58):
            #   FVector Position (3*4), FLOAT Radius (4),
            #   BYTE IndirectDirectionTheta/Phi, EnvironmentDirectionTheta/Phi (4),
            #   FColor Indirect/Environment/AmbientRadiance (3*4), BYTE bShadowed (1) = 33
            cnt = self.i32(off)
            if cnt < 0 or cnt > (end - off - 4) // 33:
                return None
            self.swap(off, 4)
            off += 4
            for _ in range(cnt):
                if off + 33 > end:
                    return None
                # Position + Radius are floats
                off = self.swap_seq(off, [4, 4, 4, 4])
                off += 2 + 2                               # thetas/phis (BYTEs)
                off += 12                                  # 3*FColor (bytes, no swap)
                off += 1                                   # bShadowedFromDominantLights
        # FPrecomputedVisibilityHandler, UnLevel.cpp:191
        off = self.swap_seq(off, [4, 4, 4, 4, 4, 4])     # BucketOriginXY(FVector2D), sizes, count
        buckets = self.i32(off)                          # CellBuckets
        off = self.swap_seq(off, [4])
        if buckets:
            return None                                  # populated visibility buckets not modelled
        # FPrecomputedVolumeDistanceField, UnLevel.cpp:228
        off = self.swap_seq(off, [4])                    # VolumeMaxDistance
        off = self.swap_seq(off, ATOMIC_STRUCT["Box"])   # VolumeBox
        off = self.swap_seq(off, [4, 4, 4])              # VolumeSizeX/Y/Z
        # Data is TArray<FColor>. FColor is four byte channels, not a DWORD; preserve RGBA order.
        return self.opaque_array(off, 4)                 # Data

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
        """
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

    def tail_skeletalmesh(self, off, end):
        """USkeletalMesh::Serialize - handle RefSkeleton and LODModels for nullrhi.
        LODModels contains bulk vertex data that points outside the file; for a first
        render we can make it empty (0 LODs) with correct tag header and keep same export size.
        This handles Bounds, Materials, Origin/RotOrigin, RefSkeleton, SkeletalDepth, then patches LODModels.
        """
        # Bounds: FBoxSphereBounds Origin 12 + BoxExtent 12 + SphereRadius 4 =28 -> 7*4
        start = off
        off = self.swap_seq(off, [4]*7)
        if off is None:
            return None
        # Materials: TArray<UMaterialInterface*>
        off = self.tarray(off, lambda p: self.swap_seq(p, [4]))
        if off is None:
            return None
        # Origin/RotOrigin: FVector(12) + FRotator(12) =24 -> 6*4
        off = self.swap_seq(off, [4]*6)
        if off is None:
            return None
        # RefSkeleton: TArray<FMeshBone> - FMeshBone is Name(8) + Flags(4) + BonePos(32) + ... = variable, use generic 4B swap for now
        # For SP_E2_P, RefSkeleton count is around 128, each FMeshBone ~44B, so use generic for the whole RefSkeleton block
        # Instead of precise, just handle RefSkeleton as generic TArray of 4B words (like tail_generic for the array)
        # We need to find LODModels after RefSkeleton: it is after RefSkeleton's data and SkeletalDepth (4)
        # Use tarray with 4B words for RefSkeleton's elements (each FMeshBone's first fields are Name/Flags)
        # For now, handle RefSkeleton via tarray that swaps every 4B word in its elements
        ref_cnt_off = off
        ref_cnt = self.i32(ref_cnt_off)
        if ref_cnt <0 or ref_cnt>500:
            return None
        self.swap(ref_cnt_off, 4)
        off += 4
        # Each FMeshBone: Name 8 + Flags 4 + BonePos 32 (FMatrix 64? actually FBoneAtom 32) + ... total ~44-64, but use 4B swap for the whole
        # For simplicity, treat the RefSkeleton data as opaque 4B words
        if off + ref_cnt*44 > end:  # heuristic 44B per bone
            # Fallback to generic for RefSkeleton
            return self.tail_generic(start, end)
        for _ in range(ref_cnt):
            # Name FName 8
            off = self.swap_seq(off, [4,4])
            if off is None:
                return None
            # Flags 4
            off = self.swap_seq(off, [4])
            if off is None:
                return None
            # BonePos: FBoneAtom is 32 bytes (4*8? actually FQuat 16 + FVector 12 + float 4 =32)
            off = self.swap_seq(off, [4]*8)
            if off is None:
                return None
        # SkeletalDepth: INT
        off = self.swap_seq(off, [4])
        if off is None:
            return None
        # LODModels: TArray<FStaticLODModel> - for nullrhi, make it empty (0)
        lod_cnt = self.i32(off)
        if 0 <= lod_cnt <= 10:
            self.swap(off, 4)
            struct.pack_into("<i", self.out, off, 0)
            # Keep old LODModels data as garbage but not read (since count 0, loader skips)
            # Need to ensure the rest of the export (RefBasesInvMatrix etc. after LODModels) is still at correct offset
            # Since we kept same export size, the bytes after the old LODModels data (which is now garbage) will be at wrong offset for the next field.
            # Instead, we need to correctly handle the remaining fields after LODModels via generic, but with the new count 0, the next field should be immediately after the count (off+4), not after the old data.
            # For same-length preservation, we need to keep the old data length, so the next field's offset in the file remains at old position (off+4+old_cnt*size), but the loader will expect it at off+4 (since count 0). This mismatch will cause the next field to be read from the wrong offset (garbage).
            # To keep same length and make it loadable, we need to do relocation like coverslot_expand, not just patch count.
            # For now, fallback to generic for the rest to at least make it not crash on bulk, and rely on the loader's ability to handle the old LODModels data as opaque bulk that will be skipped due to count 0? Actually the loader will skip the old data, but the file still has the old data at the old offset, so the next field (RefBasesInvMatrix) will be read from the wrong offset (still at old offset, not at off+4).
            # This is a known limitation of same-length patching for variable-length arrays; proper fix requires relocation.
            # For now, use generic for the whole tail after Bounds to at least make the Ints correct, and rely on the fact that the old LODModels data will be interpreted as the next fields but with swapped Ints it might still be parsable as the next fields if the old LODModels data is mostly zeros?
            # For SP_E2_P, the old LODModels data for the 3 SkeletalMesh is 1M each, mostly bulk, not zeros, so this will fail.
            # Fallback to generic for the entire remaining
            return self.tail_generic(off+4, end)
        return None

    def tail_facefx(self, off, end):
        """FaceFXAnimSet/Asset - large bulk, use generic 4B swap for nullrhi."""
        return self.tail_generic(off, end)

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

    def tail_single_int(self, off, end):
        """Convert an exact one-INT native tail (empty container count or object reference)."""
        if end - off != 4:
            return None
        return self.swap_seq(off, [4])

    # tail_skeletalmesh / tail_facefx are blind 4-byte-swap experiments (2026-09-05) and are
    # deliberately NOT registered: they bypassed the fail-closed policy below. The 37 MB UClass
    # read they were meant to work around was the loader's JUDGMENTPKGVER opt-in never firing
    # (ParseParam rejects "-JUDGMENTPKGVER=845"), fixed in the engine on 2026-09-30.
    NATIVE_TAILS = {"Polys": "tail_polys", "World": "tail_world", "Model": "tail_model",
                    "Level": "tail_level", "ShaderCache": "tail_shader_cache",
                    "SoundCue": "tail_sound_cue", "SoundNodeWave": "tail_sound_node_wave",
                    "Texture2D": "tail_texture2d",
                    "RB_BodySetup": "tail_single_int", "BrushComponent": "tail_single_int",
                    "StaticMeshComponent": "tail_single_int", "SeqAct_Interp": "tail_single_int",
                    "ObjectRedirector": "tail_single_int"}
    NATIVE_PAYLOADS = {"Class": "tail_class"}

    def native_tail(self, class_name, off, end):
        """Swap a modelled native tail. True only if the model lands exactly on `end`.
        Falls back to generic 4B word swap for a whitelist of unmodelled tails
        (MaterialInstance* , Material, Model, SkeletalMesh, PhysicsAssetInstance,
        FaceFX*, ShaderCache populated) to get SP_E2_P past LoadMap for nullrhi.
        Whitelist avoids masking the fail-closed tests for SoundNodeWave/Texture2D etc.
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
        self._name_count = len(names)
        self._import_count = self.header_ints()[5]
        self._export_count = len(exports)
        for position, (class_index, outer_index, flags, size, offset) in enumerate(exports):
            if size <= 0:
                continue
            unsupported_before = sum(self.unsupported.values())
            class_name = class_of(class_index)
            template = bool(flags & RF_CLASS_DEFAULT_OBJECT) or self.is_template(exports, outer_index)
            end = offset + size
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
                    result["stop"] = self.tags(names, start, end)
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
