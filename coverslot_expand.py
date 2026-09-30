"""CoverSlot tagged-stream expansion for the Judgment native port.

DISCOVERY (2026-08-25): the Gears 3 PC cook stores ACoverLink.Slots elements as TAGGED
property streams, and the source-built loader does too -- STRUCT_ImmutableWhenCooked is a
*cooker-applied* flag the runtime's UScriptStruct never carries, so UStructProperty::
SerializeItem takes the SerializeTaggedProperties path for FCoverSlot everywhere in this
port. Judgment's console cook emitted BINARY SerializeBin form instead. The converter must
therefore EXPAND binary slots into tagged streams; output length changes, so export serial
sizes/offsets are relocated and missing names are appended to the name table.

Binary input layout (proven against SP_00_Museum_Base_Exit_S, see PORTING notes):
  owner INT | [validafter skipped] | ForceCoverType/CoverType/LocationDescription as
  enum-FName(8) | Vector(12) Rotator(12) | Actions count+8N | FireLinks count+sum(m+10)
  [Rejected skipped] | ExposedCover count+4N | TurnTarget INT | SlipRefs count+80N
  | OverlapClaims count+8N | 21 bool bytes

Emission template mirrors the Jacinto 1.1.1 PC cook byte-for-byte (SP_Badlands_02).
"""
import struct

# ---------------------------------------------------------------- name table

REQUIRED_NAMES = [
    # tag names
    "SlotOwner", "ForceCoverType", "CoverType", "LocationDescription",
    "LocationOffset", "RotationOffset", "Actions", "FireLinks",
    "ExposedCoverPackedProperties", "TurnTargetPackedProperties", "SlipRefs",
    "OverlapClaimsList", "bLeanLeft", "bLeanRight", "bForceCanPopUp", "bCanPopUp",
    "bCanMantle", "bCanClimbUp", "bForceCanCoverSlip_Left", "bForceCanCoverSlip_Right",
    "bCanCoverSlip_Left", "bCanCoverSlip_Right", "bCanSwatTurn_Left", "bCanSwatTurn_Right",
    "bEnabled", "bAllowPopup", "bAllowMantle", "bAllowCoverSlip", "bAllowClimbUp",
    "bAllowSwatTurn", "bForceNoGroundAdjust", "bPlayerOnly", "bPreferLeanOverPopup",
    "Interactions", "PackedProperties_CoverPairRefAndDynamicInfo", "bFallbackLink",
    "bDynamicIndexInited", "Direction", "Dest", "Poly", "OwningPylon", "PolyId",
    "Actor", "Guid", "Base", "Position", "CachedBaseLocation", "CachedBaseRotation",
    "CachedTransPosition", "Link", "SlotIdx",
    # type / struct / enum names used by tags
    "ObjectProperty", "ByteProperty", "StructProperty", "ArrayProperty",
    "IntProperty", "BoolProperty", "Vector", "Rotator", "Guid", "CoverInfo",
    "FireLink", "SlotMoveRef", "BasedPosition", "PolyReference", "ActorReference",
    "ECoverType", "ECoverAction", "ECoverLocationDescription",
]

BOOL_NAMES = ["bLeanLeft", "bLeanRight", "bForceCanPopUp", "bCanPopUp", "bCanMantle",
              "bCanClimbUp", "bForceCanCoverSlip_Left", "bForceCanCoverSlip_Right",
              "bCanCoverSlip_Left", "bCanCoverSlip_Right", "bCanSwatTurn_Left",
              "bCanSwatTurn_Right", "bEnabled", "bAllowPopup", "bAllowMantle",
              "bAllowCoverSlip", "bAllowClimbUp", "bAllowSwatTurn", "bForceNoGroundAdjust",
              "bPlayerOnly", "bPreferLeanOverPopup"]

TYPE = dict(ObjectProperty="ObjectProperty", Byte="ByteProperty", Struct="StructProperty",
            Array="ArrayProperty", Int="IntProperty", Bool="BoolProperty")


def be_i32(buf, o):
    return struct.unpack_from(">i", buf, o)[0]


def le_i32(buf, o):
    return struct.unpack_from("<i", buf, o)[0]


def le_pack(fmt, *vals):
    return struct.pack("<" + fmt, *vals)


# ---------------------------------------------------------------- parse BE binary slot

def parse_binary_slots(be, pos, end, count):
    """Parse `count` binary FCoverSlots from big-endian `be` between pos..end.
    Judgment v845 cook order is declaration order (owner first) as verified on
    SP_00_Museum_Base_Exit_S (owner 0 at pos). Gears 3 PropertyLink is reverse,
    but the cooker for Judgment emits declaration order, so we follow the file.
    Handles the ~190B/slot residual (high-entropy GUID-like) by treating it as
    an optional trailing blob per slot that is preserved for later investigation
    but not required for tagged emission (empty cover fallback will drop it).
    """
    # Try declaration order first (owner first) as observed in the file
    def try_order(order):
        slots = []
        q = pos
        try:
            for slot_idx in range(count):
                s = {}
                if order == "decl":
                    s["owner"] = be_i32(be, q); q += 4
                    s["fct"] = (be_i32(be, q), be_i32(be, q + 4)); q += 8
                    s["ct"] = (be_i32(be, q), be_i32(be, q + 4)); q += 8
                    s["lcd"] = (be_i32(be, q), be_i32(be, q + 4)); q += 8
                    s["loc"] = be[q:q + 12]; q += 12
                    s["rot"] = be[q:q + 12]; q += 12
                    na = be_i32(be, q); q += 4
                    s["actions"] = [(be_i32(be, q + 8 * i), be_i32(be, q + 8 * i + 4)) for i in range(na)]
                    q += 8 * na
                    nf = be_i32(be, q); q += 4
                    fls = []
                    for _ in range(nf):
                        m = be_i32(be, q); q += 4
                        if q + m + 6 > end: raise ValueError("firelink overrun")
                        data = be[q:q + m]; q += m
                        packed = be_i32(be, q)
                        bits = be[q + 4:q + 6]
                        fls.append((data, packed, bits))
                        q += 6
                    ne = be_i32(be, q)
                    s["exposed"] = [be_i32(be, q + 4 + 4 * i) for i in range(ne)]
                    q += 4 + 4 * ne
                    s["turn"] = be_i32(be, q); q += 4
                    ns = be_i32(be, q); q += 4
                    slips = []
                    for _ in range(ns):
                        if q + 80 > end: raise ValueError("slip overrun")
                        direction = be_i32(be, q)
                        base = be[q + 4:q + 56]
                        poly_id = be_i32(be, q + 56)
                        actor = be_i32(be, q + 60)
                        guid = be[q + 64:q + 80]
                        slips.append((direction, base, poly_id, actor, guid))
                        q += 80
                    nc2 = be_i32(be, q); q += 4
                    if q + 8*nc2 > end: raise ValueError("claims overrun")
                    claims = []
                    for i in range(nc2):
                        claims.append((be_i32(be, q + 8 * i), be_i32(be, q + 8 * i + 4)))
                    q += 8 * nc2
                    # Bools: 21 bytes in declaration order, but binary bitfield is 4 bytes at start in reverse order
                    # For decl order, bools are at the end as 21 bytes (as observed)
                    if q + 21 > end: raise ValueError("bools overrun")
                    s["bools"] = list(be[q:q + 21])
                    q += 21
                    # Check for residual (190B) - if present, consume it as opaque and store
                    # Residual begins with high-entropy GUID-like 16 bytes, length varies per slot (188/176 etc)
                    # For now, detect residual by peeking at next slot owner (should be 0 or small) vs GUID high-entropy
                    # If next 4 bytes look like a plausible next owner (small int <1000) then no residual, else consume residual
                    # Heuristic: next owner should be < 100 and next fct should be 40/39 etc
                    # For now, try to detect residual length by looking ahead
                    # If q + 4 <= end and be_i32(be, q) > 1000: likely residual, skip it
                    # Residual length is variable, but we can detect by trying to parse next slot and seeing if it fails
                    # For decl order, next slot owner at q should be 0-10
                    # Residual handling: Judgment adds ~168-184B after some slots (and trailing after last).
                    # For non-last slots, residual is the gap to next slot's known start; for last, it's tail to end.
                    is_last = (slot_idx == count-1)
                    if is_last:
                        # Last slot: consume any remaining bytes as opaque residual (trailing)
                        if q < end:
                            s["residual"] = be[q:end]
                            q = end
                    else:
                        if q + 4 <= end:
                            peek = be_i32(be, q)
                            if peek > 100 or peek < 0:
                                found = None
                                for off in range(0, min(320, end - q - 32)):
                                    try:
                                        o = be_i32(be, q+off)
                                        f0 = be_i32(be, q+off+4)
                                        f1 = be_i32(be, q+off+8)
                                        c0 = be_i32(be, q+off+12)
                                        c1 = be_i32(be, q+off+16)
                                        l0 = be_i32(be, q+off+20)
                                        l1 = be_i32(be, q+off+24)
                                        if 0 <= o <= 5 and 37 <= f0 <= 45 and f1 == 0 and 37 <= c0 <= 45 and c1 == 0 and 35 <= l0 <= 45 and l1 == 0:
                                            found = off
                                            break
                                    except: pass
                                if found is not None:
                                    s["residual"] = be[q:q+found]
                                    q += found
                                elif q + 4 <= end:
                                    # No pattern found but peek suggests residual - try to consume up to next plausible or fallback
                                    # For safety, scan for any plausible next owner within larger window
                                    found2 = None
                                    for off2 in range(0, min(400, end - q - 32)):
                                        try:
                                            o2 = be_i32(be, q+off2)
                                            if 0 <= o2 <= 10:
                                                # quick check second DWORDs
                                                f0b = be_i32(be, q+off2+4)
                                                if 37 <= f0b <= 45:
                                                    found2 = off2
                                                    break
                                        except: pass
                                    if found2 is not None:
                                        s["residual"] = be[q:q+found2]
                                        q += found2
                                    elif q + 184 <= end:
                                        s["residual"] = be[q:q+184]
                                        q += 184
                    s["firelinks"] = fls
                    s["slips"] = slips
                    s["claims"] = claims
                    if q > end:
                        raise ValueError("overrun after bools")
                    slots.append(s)
                else:
                    # Reverse order (PropertyLink) - bitfield first
                    # Not used for Judgment file as observed, but keep for completeness
                    bfield = be_i32(be, q); q+=4
                    nc2 = be_i32(be, q); q+=4
                    claims = [(be_i32(be, q+8*i), be_i32(be, q+8*i+4)) for i in range(nc2)]
                    q+=8*nc2
                    ns = be_i32(be, q); q+=4
                    slips = []
                    for _ in range(ns):
                        direction = be_i32(be, q); q+=4
                        base = be[q:q+52]; q+=52
                        poly_id = be_i32(be, q); q+=4
                        actor = be_i32(be, q); q+=4
                        guid = be[q:q+16]; q+=16
                        slips.append((direction, base, poly_id, actor, guid))
                    # ... etc - not implemented as file uses decl order
                    raise ValueError("reverse not implemented for this file")
            if q > end:
                raise ValueError("overrun")
            if q != end:
                # Allow small residual at end (e.g., 0-4 bytes padding)
                if end - q <= 4:
                    q = end
                else:
                    raise ValueError("consumed %d of %d" % (q-pos, end-pos))
            return slots
        except Exception as e:
            raise

    # Try decl order
    try:
        return try_order("decl")
    except Exception as e:
        # Fallback to try with residual handling already in decl
        raise



# ---------------------------------------------------------------- LE tag emission

class Emitter:
    def __init__(self, nidx, out):
        self.nidx = nidx          # name -> index
        self.out = bytearray()

    def fname(self, idx, num=0):
        self.out += le_pack("ii", idx, num)

    def raw_tag(self, name_idx, type_idx, size, arridx=0):
        self.fname(name_idx)
        self.fname(type_idx)
        self.out += le_pack("ii", size, arridx)

    def obj_tag(self, name, value):
        self.raw_tag(self.nidx[name], self.nidx["ObjectProperty"], 4)
        self.out += le_pack("i", value)

    def int_tag(self, name, value):
        self.raw_tag(self.nidx[name], self.nidx["IntProperty"], 4)
        self.out += le_pack("i", value)

    def bool_tag(self, name, b):
        self.raw_tag(self.nidx[name], self.nidx["BoolProperty"], 0)
        self.out += le_pack("B", 1 if b else 0)

    def byte_enum_tag(self, name, enum_name, fname_pair):
        self.raw_tag(self.nidx[name], self.nidx["ByteProperty"], 8)
        self.fname(self.nidx[enum_name])
        self.fname(*fname_pair)

    def vector_tag(self, name, raw12):
        self.raw_tag(self.nidx[name], self.nidx["StructProperty"], 12)
        self.fname(self.nidx["Vector"])
        self.swap_into(raw12)

    def rotator_tag(self, name, raw12):
        self.raw_tag(self.nidx[name], self.nidx["StructProperty"], 12)
        self.fname(self.nidx["Rotator"])
        self.swap_into(raw12)

    def guid_value(self, raw16):
        self.raw_struct_value(self.nidx["Guid"], "Guid", 16, raw16)

    def raw_struct_value(self, inner_idx, inner_name, size, raw):
        self.raw_tag(self.nidx[inner_name], self.nidx["StructProperty"], size)
        self.fname(inner_idx)
        self.out += raw

    def swap_into(self, raw):
        self.out += raw[::-1]

    def array_count(self, name, count):
        self.raw_tag(self.nidx[name], self.nidx["ArrayProperty"], None_placeholder(count))
        # placeholder patched by caller via mark()
        return len(self.out)

    def none(self):
        self.fname(self.nidx["None"])


def None_placeholder(count):
    return 0


def emit_slot(e, s):
    """Emit one tagged FCoverSlot element."""
    e.obj_tag("SlotOwner", s["owner"])
    e.byte_enum_tag("ForceCoverType", "ECoverType", s["fct"])
    e.byte_enum_tag("CoverType", "ECoverType", s["ct"])
    e.byte_enum_tag("LocationDescription", "ECoverLocationDescription", s["lcd"])
    e.vector_tag("LocationOffset", s["loc"])
    e.rotator_tag("RotationOffset", s["rot"])

    # Actions: ArrayProperty of enum-as-FName elements
    n_act = len(s["actions"])
    e.raw_tag(e.nidx["Actions"], e.nidx["ArrayProperty"], 4 + 8 * n_act)
    e.out += le_pack("i", n_act)
    for idx, numv in s["actions"]:
        e.fname(idx, numv)

    # FireLinks: ArrayProperty of tagged FireLink elements
    fl = s["firelinks"]
    mark_size = len(e.out)
    e.raw_tag(e.nidx["FireLinks"], e.nidx["ArrayProperty"], 0)   # placeholder
    e.out += le_pack("i", len(fl))
    for data, packed, bits in fl:
        e.raw_tag(e.nidx["Interactions"], e.nidx["ArrayProperty"], 4 + len(data))
        e.out += le_pack("i", len(data))
        e.out += data                       # raw bytes: no swap needed
        e.int_tag("PackedProperties_CoverPairRefAndDynamicInfo", packed)
        e.bool_tag("bFallbackLink", bits[0] & 1)
        e.bool_tag("bDynamicIndexInited", bits[1] & 1)
        e.none()
    fl_size = len(e.out) - (mark_size + 24) - 4
    struct.pack_into("<i", e.out, mark_size + 16, fl_size)

    # ExposedCoverPackedProperties
    ex = s["exposed"]
    e.raw_tag(e.nidx["ExposedCoverPackedProperties"], e.nidx["ArrayProperty"], 4 + 4 * len(ex))
    e.out += le_pack("i", len(ex))
    for v in ex:
        e.out += le_pack("i", v)

    e.int_tag("TurnTargetPackedProperties", s["turn"])

    # SlipRefs
    sl = s["slips"]
    mark_size = len(e.out)
    e.raw_tag(e.nidx["SlipRefs"], e.nidx["ArrayProperty"], 0)
    e.out += le_pack("i", len(sl))
    for direction, base, poly_id, actor, guid in sl:
        # Poly first (chain order, matching the Jacinto cook)
        pmark = len(e.out)
        e.raw_tag(e.nidx["Poly"], e.nidx["StructProperty"], 0)
        e.fname(e.nidx["PolyReference"])
        # OwningPylon
        omark = len(e.out)
        e.raw_tag(e.nidx["OwningPylon"], e.nidx["StructProperty"], 0)
        e.fname(e.nidx["ActorReference"])
        e.obj_tag("Actor", actor)
        e.guid_value(guid)
        e.none()
        struct.pack_into("<i", e.out, omark + 16, len(e.out) - (omark + 24))
        e.none()                              # close PolyReference
        struct.pack_into("<i", e.out, pmark + 16, len(e.out) - (pmark + 24))
        # Dest -> BasedPosition
        dmark = len(e.out)
        e.raw_tag(e.nidx["Dest"], e.nidx["StructProperty"], 0)
        e.fname(e.nidx["BasedPosition"])
        e.obj_tag("Base", struct.unpack_from("<i", base, 0)[0])
        e.vector_tag("Position", base[4:16])
        e.vector_tag("CachedBaseLocation", base[16:28])
        e.rotator_tag("CachedBaseRotation", base[28:40])
        e.vector_tag("CachedTransPosition", base[40:52])
        e.none()
        struct.pack_into("<i", e.out, dmark + 16, len(e.out) - (dmark + 24))
        e.int_tag("Direction", direction)
        e.none()
    sl_size = len(e.out) - (mark_size + 24) - 4
    struct.pack_into("<i", e.out, mark_size + 16, sl_size)

    # OverlapClaimsList
    cl = s["claims"]
    cmark = len(e.out)
    e.raw_tag(e.nidx["OverlapClaimsList"], e.nidx["ArrayProperty"], 0)
    e.out += le_pack("i", len(cl))
    for link, slotidx in cl:
        e.obj_tag("Link", link)
        e.int_tag("SlotIdx", slotidx)
        e.none()
    cl_size = len(e.out) - (cmark + 24) - 4
    struct.pack_into("<i", e.out, cmark + 16, cl_size)

    for name, bit in zip(BOOL_NAMES, s["bools"]):
        e.bool_tag(name, bit)
    e.none()

# ---------------------------------------------------------------- package pass

def read_le_package(buf):
    """Parse summary/tables of a little-endian v845 package."""
    def i(o):
        return struct.unpack_from("<i", buf, o)[0]

    fl = i(12)
    ints_off = 16 + fl
    (_flags, nc, no, ec, eo, ic, io, dep) = [i(ints_off + k * 4) for k in range(8)]
    names = []
    o = no
    for _ in range(nc):
        n = i(o); o += 4
        names.append(buf[o:o + n - 1].decode("latin-1") if n > 0 else "")
        o += abs(n) + 8
    names_end = o
    imports_end = io + ic * 28
    exports = []
    o = eo
    for _ in range(ec):
        cls = i(o); outer = i(o + 8); nmi = i(o + 12)
        sz = i(o + 32); soff = i(o + 36); gencnt = i(o + 44)
        exports.append((cls, outer, nmi, sz, soff))
        o += 48 + 4 * abs(gencnt) + 20
    first_payload = min(e[4] for e in exports)
    return {"ints_off": ints_off, "nc": nc, "no": no, "names": names,
            "names_end": names_end, "ic": ic, "io": io,
            "ec": ec, "eo": eo, "dep": dep, "exports": exports,
            "first_payload": first_payload}


NAMES = []


def find_slots_tag(buf, soff, size):
    """Locate the Slots ArrayProperty value region inside a CoverLink payload (LE)."""
    def i(o):
        return struct.unpack_from("<i", buf, o)[0]
    o = soff
    node = i(o)
    o += 14
    stack = i(o); o += 4
    if node != 0:
        o += 4
    o += 4
    end = soff + size
    while o < end:
        t = i(o)
        if t is None or t < 0 or t >= len(NAMES):
            return None
        if NAMES[t] == "None":
            return None
        tt = i(o + 8)
        tsz = i(o + 16)
        typname = NAMES[tt] if 0 <= tt < len(NAMES) else "?"
        val = o + 24
        if typname in ("StructProperty", "ByteProperty"):
            val += 8
        elif typname == "BoolProperty":
            val += 1
        if NAMES[t] == "Slots":
            return val, tsz - 4
        o = val + tsz
    return None


def expand(src_path, dst_path):
    """Read be2le output; expand CoverLink.Slots into tagged streams; relocate offsets."""
    global NAMES
    with open(src_path, "rb") as h:
        buf = bytearray(h.read())
    info = read_le_package(bytes(buf))
    NAMES = list(info["names"])
    nidx = {n: i for i, n in enumerate(NAMES)}

    missing = [n for n in REQUIRED_NAMES if n not in nidx]
    appended = bytearray()
    for n in missing:
        data = n.encode("latin-1") + b"\x00"
        appended += struct.pack("<i", len(data)) + data
        # name flags qword, little-endian copy of the pattern used by every entry here
        appended += b"\x07\x00\x10\x00\x00\x00\x00\x00"
        NAMES.append(n)
    nidx.update({n: len(info["names"]) + i for i, n in enumerate(missing)})
    print("appending %d names (%d bytes)" % (len(missing), len(appended)))

    import_names = []
    o = info["io"]
    for _ in range(info["ic"]):
        # the class of an object is the import's OBJECT NAME (offset +20), not 'Class' (+8)
        import_names.append(NAMES[struct.unpack_from("<i", buf, o + 20)[0]])
        o += 28

    jobs = {}
    for idx, (cls, outer, nmi, sz, soff) in enumerate(info["exports"]):
        if cls >= 0 or import_names[-cls - 1] != "CoverLink":
            continue
        hit = find_slots_tag(bytes(buf), soff, sz)
        if not hit:
            continue
        slots_val, slots_body = hit
        count = le_i32(buf, slots_val)
        if not count or count > slots_body:
            continue
        # Slots value bytes are still BIG-endian (be2le leaves them untouched).
        # Try to parse binary slots; on failure (known ~190B residual per slot in Judgment),
        # fall back to empty Slots (0 elements) to keep the map loadable for nullrhi testing.
        try:
            slots = parse_binary_slots(bytes(buf), slots_val + 4, slots_val + 4 + slots_body, count)
            e = Emitter(nidx, bytearray())
            for s in slots:
                emit_slot(e, s)
            new_body_elements = bytes(e.out)
            new_val = struct.pack("<i", count) + new_body_elements
            print("export#%d %-22s slots=%d payload %d -> %d bytes (expanded)"
                  % (idx + 1, NAMES[nmi], count, sz, len(new_val)))
        except Exception as ex:
            print("export#%d %-22s slots=%d parse failed (%s) -> emitting empty (0) for loadability"
                  % (idx + 1, NAMES[nmi], count, ex))
            new_val = struct.pack("<i", 0)
        # Rebuild payload with correct tag header size update
        tag_off = slots_val - 24
        old_tsz = slots_body + 4
        new_tsz = len(new_val)
        new_tag_header = bytearray(buf[tag_off:tag_off+24])
        struct.pack_into("<i", new_tag_header, 16, new_tsz)
        payload = bytes(buf[soff:tag_off]) + bytes(new_tag_header) + new_val + bytes(buf[tag_off+24+old_tsz:soff+sz])
        jobs[idx] = (soff, sz, payload)
        print("  -> new payload %d bytes (was %d) tag %d->%d" % (len(payload), sz, old_tsz, new_tsz))

    if not jobs:
        print("no CoverLink expansions applied")
        with open(dst_path, "wb") as h:
            h.write(buf)
        return

    # Delegate final layout + absolute-offset relocation to the global layer.
    try:
        from package_relocate import relocate_and_emit
    except ImportError:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location("package_relocate", str(pathlib.Path(__file__).parent / "package_relocate.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        relocate_and_emit = mod.relocate_and_emit

    out = relocate_and_emit(bytes(buf), info, bytes(appended), jobs)
    # relocate_and_emit does not patch NameCount (needs appended count) - do it here
    fl = struct.unpack_from("<i", out, 12)[0]
    ints_off = 16 + fl if fl > 0 else 16 + (-fl)*2
    out_ba = bytearray(out)
    struct.pack_into("<i", out_ba, ints_off + 1*4, info["nc"] + len(missing))
    out = bytes(out_ba)

    with open(dst_path, "wb") as h:
        h.write(out)
    print("wrote %s (%d bytes; was %d) via package_relocate" % (dst_path, len(out), len(buf)))


if __name__ == "__main__":
    import sys
    expand(sys.argv[1], sys.argv[2])
