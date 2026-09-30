"""Global package relocation layer - two-phase layout.

Implements the baseline's PASS1/PASS2 architecture:

  PASS 1: parse package, convert exports independently, record converted byte lengths,
          record relocatable references (file-absolute BulkData offsets).
  PASS 2: assign final SerialOffsets, build old->new physical offset map,
          patch all absolute offsets, emit package, verify ranges.

Offset domains:
  PACKAGE_ABSOLUTE - BulkDataOffsetInFile, Export SerialOffset, summary table offsets
                    (must be translated via relocation map)
  EXPORT_RELATIVE  - intra-export offsets (TArray counts, struct fields)
  LOGICAL/INDEXED  - name/object indices, FString lengths

This module is intentionally generic: coverslot_expand.py and future variable-size
transforms (SkeletalMesh LOD strip, texture detile) should NOT independently know
how to patch every UE3 physical-offset-bearing structure. They produce new export
payloads; this layer owns final placement and absolute offset patching.

Reference: FByteBulkData layout per be2le.py:618 - 16 bytes (flags, count, size, file_off)
where inline payload follows header at file_off == header_file_position + 16.
"""
import struct
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Relocation:
    """One file-absolute reference that must be translated."""
    owner_export: int          # which export owns this bulk header
    field_offset: int          # PACKAGE_ABSOLUTE: file position of BulkDataOffsetInFile field (4 bytes)
    old_file_offset: int       # PACKAGE_ABSOLUTE: value read from that field in old file
    payload_size: int          # bulk size (for range validation)
    intra_offset: int          # EXPORT_RELATIVE: offset of bulk header within its export payload
    flags: int

@dataclass
class RelocationMap:
    """Old->new translation for package-absolute offsets."""
    old_to_new_export: Dict[int, int]  # old export offset -> new export offset
    export_new_offsets: Dict[int, int] # export index -> new SerialOffset
    export_new_sizes: Dict[int, int]   # export index -> new SerialSize
    delta_names: int                   # shift caused by appended names

    def translate(self, old_file_offset: int, payload_size: int) -> int:
        """Translate an old bulk file offset to new, if it was inline.
        For inline bulk, old_file_offset == old_export_off + intra +16.
        New is new_export_off + intra_new +16.  If intra may have shifted due to
        variable-size conversion inside the export, caller should recompute via
        new header position rather than using this simple map.  This helper covers
        the common case where intra is unchanged (payload rebuilt preserves header position).
        Returns new_file_offset or old_file_offset if not inline/mapped.
        """
        # Find which old export contained this range
        for old_off, new_off in self.old_to_new_export.items():
            # Need size info - approximate: if old_file_offset falls within an old export's range
            # we translate by delta.  Caller should provide more precise intra if available.
            if old_file_offset >= old_off:
                # Heuristic: assume it belongs to nearest preceding export
                # Real translation should be new_export_off + (old_file_offset - old_export_off)
                return new_off + (old_file_offset - old_off)
        return old_file_offset


def parse_le_summary(buf: bytes):
    """Parse LE summary tables; returns dict with ints_off, nc, no, ec, eo, ic, io, dep etc."""
    fl = struct.unpack_from("<i", buf, 12)[0]
    ints_off = 16 + fl if fl > 0 else 16 + (-fl)*2
    vals = struct.unpack_from("<12i", buf, ints_off)
    flags, nc, no, ec, eo, ic, io, dep, igc, egc, thumb, unk = vals
    return {"ints_off": ints_off, "flags": flags, "nc": nc, "no": no, "ec": ec,
            "eo": eo, "ic": ic, "io": io, "dep": dep, "thumb": thumb, "vals": vals}


def read_le_package_info(buf: bytes):
    """Mirror coverslot_expand.read_le_package but with PACKAGE_ABSOLUTE annotations."""
    fl = struct.unpack_from("<i", buf, 12)[0]
    ints_off = 16 + fl if fl > 0 else 16 + (-fl)*2
    vals = struct.unpack_from("<12i", buf, ints_off)
    flags, nc, no, ec, eo, ic, io, dep, igc, egc, thumb, unk = vals
    names = []
    o = no
    for _ in range(nc):
        n = struct.unpack_from("<i", buf, o)[0]; o += 4
        if n > 0:
            names.append(buf[o:o+n-1].decode('latin-1', errors='replace')); o+=n
        else:
            o+=(-n)*2
        o+=8
    names_end = o
    imports_end = io + ic*28
    exports = []
    o = eo
    for idx in range(ec):
        cls = struct.unpack_from("<i", buf, o)[0]
        outer = struct.unpack_from("<i", buf, o+8)[0]
        nmi = struct.unpack_from("<i", buf, o+12)[0]
        sz = struct.unpack_from("<i", buf, o+32)[0]   # PACKAGE_ABSOLUTE size
        soff = struct.unpack_from("<i", buf, o+36)[0] # PACKAGE_ABSOLUTE offset
        gencnt = struct.unpack_from("<i", buf, o+44)[0]
        exports.append((cls, outer, nmi, sz, soff, gencnt, o))
        o += 48 + 4*abs(gencnt) + 20
    first_payload = min(e[4] for e in exports) if exports else 0
    return {"ints_off": ints_off, "nc": nc, "no": no, "names": names,
            "names_end": names_end, "ic": ic, "io": io, "ec": ec, "eo": eo,
            "dep": dep, "exports": exports, "first_payload": first_payload,
            "thumb": thumb}


def collect_bulk_relocations(buf: bytes, new_payloads: Dict[int, bytes],
                             new_offsets: Dict[int, int]) -> List[Relocation]:
    """Scan new export payloads for inline FByteBulkData headers and build relocations.
    new_payloads: export_idx -> new payload bytes (already converted, but file offsets still stale or zero)
    new_offsets: export_idx -> new SerialOffset (PACKAGE_ABSOLUTE final position)
    Returns list of Relocation where old_file_offset is read from payload (stale) and field_offset
    is absolute file position of the OffsetInFile integer.
    """
    relocs = []
    BULK_CLASSES = {"Texture2D", "LightMapTexture2D", "ShadowMapTexture2D",
                    "SoundNodeWave", "SoundCue"}
    # Need class names - parse from buf's import table and export records
    info = read_le_package_info(buf)
    # Build import class names
    names = info["names"]
    import_names = []
    o = info["io"]
    for _ in range(info["ic"]):
        idx = struct.unpack_from("<i", buf, o+20)[0]
        import_names.append(names[idx] if 0 <= idx < len(names) else "?")
        o += 28
    for exp_idx, payload in new_payloads.items():
        # Resolve class
        tbl_off = info["exports"][exp_idx][6]
        cls_idx = struct.unpack_from("<i", buf, tbl_off)[0]
        if cls_idx < 0 and -cls_idx-1 < len(import_names):
            cls_name = import_names[-cls_idx-1]
        else:
            cls_name = "?"
        if cls_name not in BULK_CLASSES:
            continue
        # Scan payload for bulk headers (4-aligned)
        for intra in range(0, len(payload)-16+1, 4):
            flags, cnt, sz, foff = struct.unpack_from("<4i", payload, intra)
            if flags not in (0, 32):
                continue
            if cnt != sz or cnt <= 0 or sz <= 0:
                continue
            # Inline check: payload data follows header
            if intra+16+sz > len(payload):
                continue
            # This is an inline bulk; its correct file offset after final placement is:
            # new_export_offset + intra + 16
            new_file_off = new_offsets[exp_idx] + intra + 16
            field_file_pos = new_offsets[exp_idx] + intra + 12  # position of OffsetInFile field in final file
            relocs.append(Relocation(owner_export=exp_idx,
                                     field_offset=field_file_pos,
                                     old_file_offset=foff,
                                     payload_size=sz,
                                     intra_offset=intra,
                                     flags=flags))
    return relocs


def relocate_and_emit(buf: bytes, info: dict, appended: bytes,
                      jobs: Dict[int, Tuple[int,int,bytes]]) -> bytes:
    """Two-phase emit with global relocation.

    buf: original LE bytes (with old offsets)
    info: from read_le_package_info(buf)
    appended: new name table bytes to append (already encoded LE)
    jobs: export_idx -> (old_soff, old_sz, new_payload_bytes)
          For exports not in jobs, payload is copied verbatim (old bytes).
    Returns new package bytes with patched summary, export table, and bulk offsets.
    """
    delta_names = len(appended)
    first_payload = info["first_payload"]

    # --- Build payload placement map ---
    # Gather all exports in old offset order. Supports both 5-tuple (coverslot_expand) and 7-tuple (full) forms.
    def _get_off_sz(e):
        # e is either (cls,outer,nmi,sz,soff) or (cls,outer,nmi,sz,soff,gencnt,tbl_off)
        return e[4], e[3]
    order = sorted(range(len(info["exports"])), key=lambda i: _get_off_sz(info["exports"][i])[0])
    # Precompute new offsets
    new_offsets = {}
    new_sizes = {}
    cur_new = first_payload + delta_names
    # First pass: compute sizes
    for ei in order:
        e = info["exports"][ei]
        osz, ooff = _get_off_sz(e)[1], _get_off_sz(e)[0]
        if ei in jobs:
            _, old_sz, payload = jobs[ei]
            nsz = len(payload)
        else:
            nsz = osz
        new_sizes[ei] = nsz
    # Second: assign offsets sequentially (no gaps except original gaps preserved via body copy?)
    # For simplicity, preserve original gaps (padding between exports) as in coverslot_expand:
    # We walk in offset order, copying gaps verbatim, then placing new payloads.
    # This requires tracking old position.
    body_parts = []  # list of (type, data) for assembly
    cur_old = first_payload
    placement = {}  # ei -> new_off
    for ei in order:
        e = info["exports"][ei]
        osz, ooff = _get_off_sz(e)[1], _get_off_sz(e)[0]
        gap = ooff - cur_old
        if gap > 0:
            body_parts.append(("gap", buf[cur_old:cur_old+gap]))
            cur_new += gap
            cur_old += gap
        elif gap < 0:
            raise ValueError(f"overlapping payloads at {ooff} vs {cur_old}")
        placement[ei] = cur_new
        if ei in jobs:
            payload = jobs[ei][2]
            body_parts.append(("payload", payload))
            cur_new += len(payload)
            cur_old += osz
        else:
            body_parts.append(("payload", buf[ooff:ooff+osz]))
            cur_new += osz
            cur_old += osz
    # Tail after last export (usually none, but include)
    if cur_old < len(buf):
        body_parts.append(("tail", buf[cur_old:]))

    # Build output prefix
    out = bytearray()
    out += buf[:info["names_end"]]
    out += appended
    # Import table (shifted by delta_names, content unchanged)
    out += buf[info["io"]:info["eo"]]
    # Export table + depends - will be patched later, copy verbatim for now at new position
    # The bytes from eo to first_payload are export records + depends map
    out += buf[info["eo"]:first_payload]

    base_ints = info["ints_off"]
    # Patch summary offsets (PACKAGE_ABSOLUTE). NameCount is patched by caller to avoid
    # needing to decode appended names here; we only shift the three table offsets.
    struct.pack_into("<i", out, base_ints + 4*4, info["eo"] + delta_names)
    struct.pack_into("<i", out, base_ints + 6*4, info["io"] + delta_names)
    struct.pack_into("<i", out, base_ints + 7*4, info["dep"] + delta_names if info["dep"] else 0)

    # Assemble body
    body_start = len(out)
    for typ, data in body_parts:
        out += data

    # Patch export records in new position (eo + delta_names)
    o = info["eo"] + delta_names
    for ei in range(info["ec"]):
        gencnt = struct.unpack_from("<i", out, o+44)[0]
        if ei in placement:
            struct.pack_into("<i", out, o+32, new_sizes[ei])  # SerialSize PACKAGE_ABSOLUTE
            struct.pack_into("<i", out, o+36, placement[ei])  # SerialOffset PACKAGE_ABSOLUTE
        o += 48 + 4*abs(gencnt) + 20

    # --- Patch file-absolute bulk offsets ---
    # Collect relocations from new payloads (using placement as new_offsets)
    def _get_off_sz2(e):
        return e[4], e[3]
    new_payloads = {ei: jobs[ei][2] if ei in jobs else buf[_get_off_sz2(info["exports"][ei])[0]:_get_off_sz2(info["exports"][ei])[0]+_get_off_sz2(info["exports"][ei])[1]]
                    for ei in range(info["ec"])}
    # But after placement, payloads are at placement[ei]; bulk header's file offset should be placement[ei]+intra+16
    # So iterate and patch directly in out buffer
    for ei, payload in new_payloads.items():
        new_off = placement[ei]
        # Resolve class to filter - handle both 5 and 7 tuple
        e0 = info["exports"][ei]
        tbl_old_off = e0[6] if len(e0) > 6 else None
        if tbl_old_off is None:
            continue
        # Need old buf to resolve class - use original buf's import names
        # Re-derive class_name
        import_names = []
        tmp_o = info["io"]
        names = info["names"]
        for _ in range(info["ic"]):
            idx = struct.unpack_from("<i", buf, tmp_o+20)[0]
            import_names.append(names[idx] if 0 <= idx < len(names) else "?")
            tmp_o += 28
        tbl_off_new = info["eo"] + delta_names
        # Find tbl offset for this export in new out (walk again)
        # Simpler: get class via old
        cls_idx = struct.unpack_from("<i", buf, tbl_old_off)[0]
        if cls_idx < 0 and -cls_idx-1 < len(import_names):
            cls_name = import_names[-cls_idx-1]
        else:
            cls_name = "?"
        if cls_name not in {"Texture2D","LightMapTexture2D","ShadowMapTexture2D","SoundNodeWave","SoundCue"}:
            continue
        # Scan payload for inline bulk
        for intra in range(0, len(payload)-16+1, 4):
            flags, cnt, sz, foff = struct.unpack_from("<4i", payload, intra)
            if flags not in (0,32):
                continue
            if cnt != sz or cnt <= 0:
                continue
            if intra+16+sz > len(payload):
                continue
            # Correct file offset
            correct = new_off + intra + 16
            # Patch in out buffer at file position new_off + intra +12
            field_pos = new_off + intra + 12
            if field_pos +4 <= len(out):
                cur_val = struct.unpack_from("<i", out, field_pos)[0]
                if cur_val != correct:
                    struct.pack_into("<i", out, field_pos, correct)

    return bytes(out)
