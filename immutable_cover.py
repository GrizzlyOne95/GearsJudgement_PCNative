"""Cooked SerializeBin cover structs, following persistent property-link order."""
from native_reader import BoundedNativeWalker, NativeLayoutError


class CoverWalker(BoundedNativeWalker):
    def __init__(self, converter, start, end, names=None):
        super().__init__(converter, start, end)
        self.names = names

    def boolean(self):
        # UBoolProperty::SerializeItem emits one BYTE per property, irrespective
        # of the shared in-memory bitfield (UnProp.cpp:1385).
        if self.byte() not in (0, 1):
            raise NativeLayoutError("invalid immutable script boolean")

    def actor_reference(self):
        self.object_ref()
        self.fields([4] * 4)  # Guid

    def cover_info(self):
        self.object_ref()  # Link
        self.fields([4])  # SlotIdx

    def fire_link(self):
        self.fixed_array([1])  # packed interaction bytes
        self.fields([4])  # PackedProperties
        self.boolean()  # bFallbackLink
        self.boolean()  # bDynamicIndexInited

    def based_position(self):
        # BasedPosition is not ImmutableWhenCooked; nested SerializeItem uses
        # its normal tag stream even inside immutable SlotMoveRef.
        if self.names is None:
            raise NativeLayoutError("BasedPosition needs the package name table")
        stop = self.converter.tags(self.names, self.pos, self.end, depth=1)
        if stop is None:
            raise NativeLayoutError("invalid tagged BasedPosition")
        self.pos = stop

    def poly_reference(self):
        self.actor_reference()
        self.fields([4])  # PolyId
        # CachedPoly is CPF_Native and ShouldSerializeValue always skips it.

    def slot_move_ref(self):
        self.poly_reference()
        self.based_position()
        self.fields([4])

    def cover_slot(self):
        # 24 declared bools minus three CPF_Transient members. Transient
        # RejectedFireLinks and SlotValidAfterTime are also absent.
        self.object_ref()  # SlotOwner
        for _ in range(3):
            self.fname()  # ForceCoverType, CoverType, LocationDescription
        self.fields([4] * 6)  # LocationOffset, RotationOffset
        self.array(self.fname, 8)  # Actions: enum-backed BYTE properties emit FNames
        self.array(self.fire_link, 10)
        self.fixed_array([4])  # ExposedCoverPackedProperties
        self.fields([4])  # TurnTargetPackedProperties
        self.array(self.slot_move_ref, 36)
        self.array(self.cover_info, 8)
        for _ in range(21):
            self.boolean()

    def walk(self, name):
        methods = {"ActorReference": self.actor_reference, "CoverInfo": self.cover_info,
                   "FireLink": self.fire_link, "BasedPosition": self.based_position,
                   "PolyReference": self.poly_reference,
                   "SlotMoveRef": self.slot_move_ref,
                   "CoverSlot": self.cover_slot}
        if name not in methods:
            raise NativeLayoutError("unknown immutable cover struct")
        methods[name]()
        self.converter.stats["binary_structs"] += 1
        return self.pos
