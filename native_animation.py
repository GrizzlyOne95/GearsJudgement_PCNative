"""Bounded cooked aim structs and per-track animation codec serialization.

UnSkeletalAnim.cpp / AnimationEncodingFormat_PerTrackCompression.cpp and
AnimationCompression.h define the native grammar. Aim structs follow script
declaration order from AnimNodeAimOffset.uc, confirmed in Judgment's Engine.u.
"""
import struct

from native_reader import BoundedNativeWalker, NativeLayoutError


class AimWalker(BoundedNativeWalker):
    STRUCTS = {"AimTransform", "AimComponent", "AimOffsetProfile"}

    def __init__(self, converter, start, end, names=None):
        super().__init__(converter, start, end)

    def aim_transform(self):
        self.fields([4] * 7)  # Quaternion, Translation

    def aim_component(self):
        self.fname()  # BoneName
        for _ in range(9):
            self.aim_transform()  # LU LC LD CU CC CD RU RC RD

    def aim_profile(self):
        self.fname()  # ProfileName
        self.fields([4] * 4)  # HorizontalRange, VerticalRange
        self.array(self.aim_component, 260)
        for _ in range(9):
            self.fname()  # AnimName_LU ... AnimName_RD

    def walk(self, name):
        methods = {"AimTransform": self.aim_transform, "AimComponent": self.aim_component,
                   "AimOffsetProfile": self.aim_profile}
        methods[name]()
        self.converter.stats["binary_structs"] += 1
        return self.pos


class AnimationWalker(BoundedNativeWalker):
    def property(self, name, kind, size=None):
        entry = getattr(self.converter, "_native_property_ranges", {}).get(name)
        if entry is None or entry[0] != kind or (size is not None and entry[3] != size):
            raise NativeLayoutError(f"missing or invalid animation property {name}")
        _, extra, start, length = entry
        if not 0 <= start <= start + length <= len(self.converter.src):
            raise NativeLayoutError("animation property is outside the package")
        return extra, start, length

    def enum(self, name, enum_type, expected):
        extra, start, _ = self.property(name, "ByteProperty", 8)
        names = getattr(self.converter, "_names", ())
        if (extra != enum_type or not self.converter.valid_fname(start) or
                self.converter.i32(start + 4) != 0 or
                not 0 <= self.converter.i32(start) < len(names) or
                names[self.converter.i32(start)] != expected):
            raise NativeLayoutError("unsupported animation codec")

    def raw_track(self):
        self.bulk([4] * 3)  # FVector PosKeys
        self.bulk([4] * 4)  # FQuat RotKeys

    def align(self, base):
        padding = -(self.pos - base) % 4
        self.need(padding)
        self.pos += padding  # padding is byte data; preserve it

    def track(self, base, num_frames):
        header = self.integer() & 0xFFFFFFFF
        key_format, flags, keys = header >> 28, (header >> 24) & 15, header & 0xFFFFFF
        if key_format > 6 or not 0 < keys <= num_frames:
            raise NativeLayoutError("invalid per-track animation header")
        # GetAllSizesFromFormat: format flags 0 encode all XYZ components.
        components = (flags & 7).bit_count() or 3
        stride = (4, 4, 2, 4, 4, 4, 0)[key_format]
        key_components = (4, components, components, 1, 1, 1, 0)[key_format]
        if key_format == 3:
            self.fields([4] * (components * 2))  # interleaved min/range pairs
        self.need(keys * key_components * stride)
        for _ in range(keys):
            self.fields([stride] * key_components)
        if flags & 8:
            self.align(base)
            width = 1 if num_frames <= 255 else 2
            self.need(keys * width)
            previous = -1
            for _ in range(keys):
                frame = int.from_bytes(self.converter.src[self.pos:self.pos + width], "big")
                if not previous <= frame < num_frames:
                    raise NativeLayoutError("invalid animation key-frame table")
                self.fields([width])
                previous = frame
        self.align(base)
        self.converter.stats["animation_tracks"] += 1
        self.converter.stats["animation_keys"] += keys

    # AnimationEncodingFormat.cpp CompressedTranslation/RotationStrides and ...Num: (swap width, chunks per key).
    TRANSLATION = {"ACF_None": (4, 3), "ACF_Float96NoW": (4, 3), "ACF_Fixed48NoW": (4, 3),
                   "ACF_IntervalFixed32NoW": (4, 1), "ACF_Fixed32NoW": (4, 3),
                   "ACF_Float32NoW": (4, 3), "ACF_Identity": (0, 0)}
    ROTATION = {"ACF_None": (4, 4), "ACF_Float96NoW": (4, 3), "ACF_Fixed48NoW": (2, 3),
                "ACF_IntervalFixed32NoW": (4, 1), "ACF_Fixed32NoW": (4, 1),
                "ACF_Float32NoW": (4, 1), "ACF_Identity": (0, 0)}

    def enum_value(self, name, enum_type, default):
        """Enum property value by name; an omitted tag means the class default."""
        if name not in getattr(self.converter, "_native_property_ranges", {}):
            return default
        extra, start, _ = self.property(name, "ByteProperty", 8)
        names = getattr(self.converter, "_names", ())
        if (extra != enum_type or not self.converter.valid_fname(start) or
                self.converter.i32(start + 4) != 0 or
                not 0 <= self.converter.i32(start) < len(names)):
            raise NativeLayoutError("invalid animation enum property")
        return names[self.converter.i32(start)]

    def legacy_keys(self, base, keys, fmt, table, single_key_format, variable, num_frames):
        """AEFConstantKeyLerpShared / AEFVariableKeyLerpShared ByteSwap*In for one key block."""
        if not 0 <= keys <= max(num_frames, 1):
            raise NativeLayoutError("invalid legacy animation key count")
        # A one-key track is always stored uncompressed.
        effective = single_key_format if keys == 1 else fmt
        if effective not in table:
            raise NativeLayoutError("unsupported animation compression format")
        stride, components = table[effective]
        if effective == "ACF_IntervalFixed32NoW":
            self.fields([4] * 6)  # mins and ranges
        if stride:
            self.need(keys * components * stride)
            for _ in range(keys):
                self.fields([stride] * components)
        if variable and keys > 1:
            self.align(base)
            width = 2 if num_frames > 0xFF else 1
            self.need(keys * width)
            previous = -1
            for _ in range(keys):
                frame = int.from_bytes(self.converter.src[self.pos:self.pos + width], "big")
                if not previous <= frame < num_frames:
                    raise NativeLayoutError("invalid animation key-frame table")
                self.fields([width])
                previous = frame
        self.align(base)
        self.converter.stats["animation_keys"] += keys

    def legacy_tracks(self, base, offsets, key_format, num_frames):
        """AnimEncodingLegacyBase::ByteSwapIn: translation then rotation per track, read in order."""
        if len(offsets) % 4:
            raise NativeLayoutError("invalid legacy animation offsets")
        translation = self.enum_value("TranslationCompressionFormat", "AnimationCompressionFormat", "ACF_None")
        rotation = self.enum_value("RotationCompressionFormat", "AnimationCompressionFormat", "ACF_None")
        variable = key_format == "AKF_VariableKeyLerp"
        for index in range(0, len(offsets), 4):
            trans_offset, trans_keys, rot_offset, rot_keys = offsets[index:index + 4]
            if trans_offset != self.pos - base:
                raise NativeLayoutError("animation tracks overlap or leave a gap")
            self.legacy_keys(base, trans_keys, translation, self.TRANSLATION, "ACF_None", variable, num_frames)
            if rot_offset != self.pos - base:
                raise NativeLayoutError("animation tracks overlap or leave a gap")
            self.legacy_keys(base, rot_keys, rotation, self.ROTATION, "ACF_Float96NoW", variable, num_frames)
            self.converter.stats["animation_tracks"] += 1

    def walk(self):
        key_format = self.enum_value("KeyEncodingFormat", "AnimationKeyFormat", "AKF_ConstantKeyLerp")
        legacy = key_format in ("AKF_ConstantKeyLerp", "AKF_VariableKeyLerp")
        if not legacy:
            self.enum("KeyEncodingFormat", "AnimationKeyFormat", "AKF_PerTrackCompression")
            self.enum("TranslationCompressionFormat", "AnimationCompressionFormat", "ACF_Identity")
            self.enum("RotationCompressionFormat", "AnimationCompressionFormat", "ACF_Identity")
        _, frame_start, _ = self.property("NumFrames", "IntProperty", 4)
        num_frames = self.converter.i32(frame_start)
        if num_frames <= 0:
            raise NativeLayoutError("invalid animation frame count")
        _, offsets_start, offsets_size = self.property("CompressedTrackOffsets", "ArrayProperty")
        if offsets_size < 4:
            raise NativeLayoutError("truncated animation offsets")
        count = self.converter.i32(offsets_start)
        if count < 0 or count % (4 if legacy else 2) or offsets_size != 4 + count * 4:
            raise NativeLayoutError("invalid animation track offsets")
        offsets = struct.unpack_from(">" + str(count) + "i", self.converter.src, offsets_start + 4)
        self.array(self.raw_track, 16)
        length = self.integer()
        if length < 0 or length != self.end - self.pos:
            raise NativeLayoutError("invalid compressed animation size")
        base = self.pos
        if legacy:
            self.legacy_tracks(base, offsets, key_format, num_frames)
            if self.pos != self.end:
                raise NativeLayoutError("unaccounted compressed animation bytes")
            self.converter.stats["animation_sequences"] += 1
            return self.pos
        # ByteSwapIn consumes the serialized stream sequentially while writing
        # into these offsets. Require complete, ordered coverage, including
        # alignment bytes; identity tracks are represented by INDEX_NONE.
        for offset in offsets:
            if offset == -1:
                continue
            if offset < 0 or offset % 4 or offset != self.pos - base:
                raise NativeLayoutError("animation tracks overlap or leave a gap")
            self.track(base, num_frames)
        if self.pos != self.end:
            raise NativeLayoutError("unaccounted compressed animation bytes")
        self.converter.stats["animation_sequences"] += 1
        return self.pos
