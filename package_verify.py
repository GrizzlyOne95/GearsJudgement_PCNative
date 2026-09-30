"""Package verifier for Judgment native port - qualification fixture.

Implements the reproducible check from the baseline:

  Package summary
  NameOffset / ImportOffset / ExportOffset / DependsOffset
  Every export: SerialOffset / SerialSize / end
  Every BulkData: ElementCount / BulkDataSizeOnDisk / BulkDataOffsetInFile / target range
  File size
  first loader/package error
  last successfully loaded export

Critical invariants (must hold before UE3 touches file):
  0 <= SerialOffset
  SerialOffset + SerialSize <= FileSize
  0 <= BulkDataOffsetInFile
  BulkDataOffsetInFile + BulkDataSizeOnDisk <= FileSize

Offset domains are explicitly annotated:
  PACKAGE_ABSOLUTE - BulkDataOffsetInFile, Export SerialOffset, summary table offsets
  EXPORT_RELATIVE  - intra-export offsets/counts
  LOGICAL/INDEXED  - name/object indices, counts, FString lengths

Usage:
  python package_verify.py <package.le.xxx> [--json-out result.json]
  Returns 0 if all invariants hold, 1 otherwise.
"""
import struct
import sys
import json
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------- offset domains
# These helpers are semantically distinct even though they all read a 32-bit LE int.
# They exist so the converter can distinguish PACKAGE_ABSOLUTE (needs relocation)
# from EXPORT_RELATIVE / LOGICAL (does not).  Call the right one.

def read_package_absolute(buf: bytes, off: int) -> int:
    """PACKAGE_ABSOLUTE: file-absolute byte offset (BulkDataOffsetInFile, SerialOffset, table offsets)."""
    return struct.unpack_from("<i", buf, off)[0]

def read_export_relative(buf: bytes, off: int) -> int:
    """EXPORT_RELATIVE: offset/count internal to a UObject serial payload."""
    return struct.unpack_from("<i", buf, off)[0]

def read_count(buf: bytes, off: int) -> int:
    """LOGICAL: element count (TArray / TMap)."""
    return struct.unpack_from("<i", buf, off)[0]

def read_object_index(buf: bytes, off: int) -> int:
    """LOGICAL: UObject reference (export>0 / import<0 / null==0)."""
    return struct.unpack_from("<i", buf, off)[0]

def read_name_index(buf: bytes, off: int) -> int:
    """LOGICAL: FName table index."""
    return struct.unpack_from("<i", buf, off)[0]


@dataclass
class BulkInfo:
    export_index: int
    export_name: str
    bulk_header_offset_in_export: int  # EXPORT_RELATIVE
    flags: int
    element_count: int
    bulk_size: int
    file_offset: int  # PACKAGE_ABSOLUTE
    target_range: tuple  # (start, end) PACKAGE_ABSOLUTE
    valid: bool
    reason: str = ""

@dataclass
class ExportInfo:
    index: int
    name: str
    class_name: str
    serial_offset: int  # PACKAGE_ABSOLUTE
    serial_size: int
    end: int  # PACKAGE_ABSOLUTE
    valid: bool
    reason: str = ""

@dataclass
class VerifyResult:
    path: str
    file_size: int
    folder_name: str
    package_version: int
    summary_valid: bool
    summary_errors: List[str] = field(default_factory=list)
    name_offset: int = 0
    import_offset: int = 0
    export_offset: int = 0
    depends_offset: int = 0
    name_count: int = 0
    import_count: int = 0
    export_count: int = 0
    names_end: int = 0
    imports_end: int = 0
    exports_end: int = 0
    exports: List[ExportInfo] = field(default_factory=list)
    bulks: List[BulkInfo] = field(default_factory=list)
    first_error: Optional[str] = None
    last_success_export: Optional[int] = None
    invariants_ok: bool = True
    errors: List[str] = field(default_factory=list)


def parse_summary(buf: bytes):
    fl = struct.unpack_from("<i", buf, 12)[0]
    if fl > 0:
        ints_off = 16 + fl
        folder = buf[16:16+fl-1].decode('latin-1') if fl>1 else ""
    else:
        ints_off = 16 + (-fl)*2
        folder = ""
    if len(buf) < ints_off + 48:
        raise ValueError(f"file too short for summary ints_off={ints_off} len={len(buf)}")
    vals = struct.unpack_from("<12i", buf, ints_off)
    flags, nc, no, ec, eo, ic, io, dep, igc, egc, thumb, unk = vals
    # also read version/tag
    tag = buf[0:4]
    ver = struct.unpack_from("<i", buf, 4)[0]
    hdr_size = struct.unpack_from("<i", buf, 8)[0]
    return {
        "ints_off": ints_off, "folder": folder, "tag": tag, "version": ver,
        "header_size": hdr_size, "flags": flags, "nc": nc, "no": no, "ec": ec,
        "eo": eo, "ic": ic, "io": io, "dep": dep, "thumb": thumb,
        "raw_vals": vals,
    }


def verify_package(path: str) -> VerifyResult:
    buf = open(path, "rb").read()
    res = VerifyResult(path=path, file_size=len(buf), folder_name="", package_version=0,
                       summary_valid=True)
    # --- summary
    try:
        s = parse_summary(buf)
    except Exception as e:
        res.summary_valid = False
        res.summary_errors.append(str(e))
        res.first_error = str(e)
        res.invariants_ok = False
        return res
    res.folder_name = s["folder"]
    res.package_version = s["version"]
    res.name_offset = s["no"]
    res.import_offset = s["io"]
    res.export_offset = s["eo"]
    res.depends_offset = s["dep"]
    res.name_count = s["nc"]
    res.import_count = s["ic"]
    res.export_count = s["ec"]

    # table landing checks
    o = s["no"]
    names = []
    try:
        for _ in range(s["nc"]):
            n = read_count(buf, o); o += 4
            if n > 0:
                # FString including null
                if o + n > len(buf):
                    raise ValueError(f"name table overrun at {o} len {n}")
                names.append(buf[o:o+n-1].decode('latin-1', errors='replace'))
                o += n
            elif n < 0:
                # UTF16
                need = (-n)*2
                if o + need > len(buf):
                    raise ValueError(f"utf16 name overrun at {o} need {need}")
                o += need
            else:
                names.append("")
            # name flags QWORD
            if o + 8 > len(buf):
                raise ValueError(f"name flags overrun at {o}")
            o += 8
        res.names_end = o
        if o != s["io"]:
            res.summary_errors.append(f"names_end {o} != ImportOffset {s['io']} (delta {o - s['io']})")
            res.summary_valid = False
    except Exception as e:
        res.summary_errors.append(f"name walk: {e}")
        res.summary_valid = False

    imports_end = s["io"] + s["ic"]*28
    res.imports_end = imports_end
    if res.names_end and imports_end != s["eo"]:
        # only if names walk succeeded
        if res.summary_valid:
            res.summary_errors.append(f"imports_end {imports_end} != ExportOffset {s['eo']} (delta {imports_end - s['eo']})")
            res.summary_valid = False

    # exports table walk
    o = s["eo"]
    exports = []
    try:
        for i in range(s["ec"]):
            if o + 48 > len(buf):
                raise ValueError(f"export {i} table overrun at {o}")
            nmi = read_name_index(buf, o+12)
            sz = read_package_absolute(buf, o+32)
            soff = read_package_absolute(buf, o+36)
            gencnt = read_count(buf, o+44)
            name = names[nmi] if 0 <= nmi < len(names) else f"?nmi={nmi}"
            # class name via import table (defer)
            exports.append((i, nmi, name, sz, soff, gencnt, o))
            o += 48 + 4*abs(gencnt) + 20
        res.exports_end = o
        if s["dep"] and o != s["dep"]:
            res.summary_errors.append(f"exports_end {o} != DependsOffset {s['dep']} (delta {o - s['dep']})")
            res.summary_valid = False
    except Exception as e:
        res.summary_errors.append(f"export table: {e}")
        res.summary_valid = False

    # build export infos with invariants
    # need class names for reporting - resolve via import table
    import_class_names = []
    try:
        io = s["io"]
        for _ in range(s["ic"]):
            idx = read_name_index(buf, io+20)
            import_class_names.append(names[idx] if 0 <= idx < len(names) else "?")
            io += 28
    except:
        pass

    ex_off = s["eo"]
    for i, nmi, name, sz, soff, gencnt, tbl_off in exports:
        cls_idx = struct.unpack_from("<i", buf, tbl_off)[0]
        if cls_idx < 0 and -cls_idx-1 < len(import_class_names):
            cls_name = import_class_names[-cls_idx-1]
        elif cls_idx == 0:
            cls_name = "Class"
        else:
            cls_name = f"exp{cls_idx}"
        end = soff + sz if sz >=0 else soff
        valid = True
        reason = ""
        if sz < 0:
            valid = False; reason = f"negative size {sz}"
        elif soff < 0:
            valid = False; reason = f"negative offset {soff}"
        elif soff + sz > len(buf):
            valid = False; reason = f"export range [{soff},{soff+sz}) exceeds file {len(buf)} (need {soff+sz - len(buf)} beyond EOF)"
        # also check that soff >= first_payload (not strictly required but warn)
        info = ExportInfo(index=i, name=name, class_name=cls_name,
                          serial_offset=soff, serial_size=sz, end=end,
                          valid=valid, reason=reason)
        res.exports.append(info)
        if not valid and not res.first_error:
            res.first_error = f"export#{i} {name} ({cls_name}): {reason}"
        if not valid:
            res.invariants_ok = False
            res.errors.append(f"export#{i} {name}: {reason}")

    # track last successfully loaded export (in table order, valid)
    last_ok = None
    for e in res.exports:
        if e.valid:
            last_ok = e.index
        else:
            break
    res.last_success_export = last_ok

    # BulkData scan - only for classes that actually serialize FByteBulkData inline.
    # Scanning every payload (CoverLink, CylinderComponent) produced thousands of false positives
    # where random binary cover data happened to match {flags=0, cnt==sz}.  Restrict to the
    # UE3 classes that own FByteBulkData per be2le.py: SoundNodeWave (4 slots), Texture2D (mips),
    # SoundCue, ShaderCache uses byte array, Level uses BulkSerialize (8-byte, not file-absolute).
    # This is a whitelist, not a heuristic: if a class is not known to emit file-absolute bulk,
    # a matching 16-byte pattern inside it is by definition spurious.
    BULK_CLASSES = {"Texture2D", "LightMapTexture2D", "ShadowMapTexture2D",
                    "SoundNodeWave", "SoundCue", "Texture2D", "SkeletalMesh"}
    # Note: SkeletalMesh/StaticMesh LOD bulk is BulkSerialize (elementSize+count, 8 bytes) not
    # FByteBulkData (16 bytes) and is not file-absolute, so it is not checked here.
    ALLOWED_INLINE_FLAGS = {0, 32}
    for exp in res.exports:
        if not exp.valid or exp.serial_size <= 0:
            continue
        if exp.class_name not in BULK_CLASSES:
            continue
        payload_off = exp.serial_offset
        payload_end = exp.end
        if payload_off + 16 > len(buf):
            continue
        blob = buf[payload_off:payload_end]
        # Only scan 4-byte aligned positions - FByteBulkData is DWORD-aligned per UE3
        for intra in range(0, len(blob) - 16 + 1, 4):
            flags = struct.unpack_from("<I", blob, intra)[0]
            if flags not in ALLOWED_INLINE_FLAGS:
                # allow 1/33 only for external sentinel, but we skip those later
                if flags not in (1, 33):
                    continue
            cnt = struct.unpack_from("<i", blob, intra+4)[0]
            sz = struct.unpack_from("<i", blob, intra+8)[0]
            foff = struct.unpack_from("<i", blob, intra+12)[0]  # PACKAGE_ABSOLUTE
            unused_sentinel = (flags == 33 and cnt == 0 and sz == -1 and foff == -1)
            if unused_sentinel:
                continue  # external/unused - not a file-range invariant
            if cnt < 0 or sz < 0:
                continue
            if cnt > 50000000 or sz > 50000000:
                continue
            # For inline byte bulk, elementSize==1 so cnt must == sz
            inline = (flags & 1) == 0 and sz > 0
            if inline:
                if cnt != sz:
                    continue
                expected = payload_off + intra + 16
                target_start = foff
                target_end = foff + sz
                valid = (foff == expected) and (target_end <= len(buf)) and (intra+16+sz <= len(blob))
                reason = ""
                if foff != expected:
                    valid = False
                    reason = f"stale file_offset {foff} != expected {expected} (delta {foff-expected})"
                elif target_end > len(buf):
                    valid = False; reason = f"bulk range [{foff},{target_end}) exceeds file {len(buf)}"
                elif intra+16+sz > len(blob):
                    valid = False; reason = f"bulk data exceeds export payload"
                else:
                    reason = "inline ok"
                # Require that the bulk data bytes are not obviously inside another valid header region
                # (already covered by alignment) - accept
                bi = BulkInfo(export_index=exp.index, export_name=exp.name,
                              bulk_header_offset_in_export=intra,
                              flags=flags, element_count=cnt, bulk_size=sz,
                              file_offset=foff, target_range=(target_start, target_end),
                              valid=valid, reason=reason)
                # Only record if foff is within plausible range (near expected or at 0 for stale)
                # This filters random false positives where foff==0 but expected ~15k - those are still recorded as stale,
                # but with cnt==sz filter they are mostly eliminated. Keep stale only if abs delta < 10MB or foff==expected
                if not valid and abs(foff - expected) > 10000000 and foff != 0:
                    continue
                res.bulks.append(bi)
                if not valid and not res.first_error:
                    res.first_error = f"bulk#{exp.index}:{intra} {exp.name} flags={flags} cnt={cnt} sz={sz} foff={foff}: {reason}"
                if not valid:
                    res.invariants_ok = False
                    res.errors.append(f"bulk exp#{exp.index} {exp.name}@{intra}: {reason} (flags={flags} cnt={cnt} sz={sz} foff={foff})")
            else:
                # external/unused sentinel already handled; other flags==1 with sz==0 are external and not file-range checked
                continue

    if res.summary_errors:
        if not res.first_error:
            res.first_error = res.summary_errors[0]
        res.invariants_ok = False
        res.errors = res.summary_errors + res.errors

    # summary tables within file
    for tbl_name, off in [("NameOffset", s["no"]), ("ImportOffset", s["io"]), ("ExportOffset", s["eo"]), ("DependsOffset", s["dep"])]:
        if off < 0 or off > len(buf):
            res.errors.append(f"{tbl_name} {off} outside file {len(buf)}")
            res.invariants_ok = False
            if not res.first_error:
                res.first_error = f"{tbl_name} out of range"

    return res


def format_result(res: VerifyResult) -> str:
    lines = []
    lines.append(f"FILE: {res.path}")
    lines.append(f"  size: {res.file_size} bytes  version: {res.package_version}  folder: '{res.folder_name}'")
    lines.append(f"  tables: NameOffset={res.name_offset} ImportOffset={res.import_offset} ExportOffset={res.export_offset} DependsOffset={res.depends_offset}")
    lines.append(f"  counts: names={res.name_count} imports={res.import_count} exports={res.export_count}")
    lines.append(f"  landing: names_end={res.names_end} ({'OK' if res.names_end==res.import_offset else 'MISMATCH'}) "
                 f"imports_end={res.imports_end} ({'OK' if res.imports_end==res.export_offset else 'MISMATCH'}) "
                 f"exports_end={res.exports_end} ({'OK' if not res.depends_offset or res.exports_end==res.depends_offset else 'MISMATCH'})")
    lines.append(f"  summary_valid: {res.summary_valid}  invariants_ok: {res.invariants_ok}")
    if res.summary_errors:
        lines.append("  summary_errors:")
        for e in res.summary_errors:
            lines.append(f"    - {e}")
    lines.append(f"  exports ({len(res.exports)}):")
    for e in res.exports:
        status = "OK" if e.valid else f"FAIL: {e.reason}"
        lines.append(f"    #{e.index:02d} {e.name:40s} ({e.class_name:20s}) off={e.serial_offset:6d} size={e.serial_size:6d} end={e.end:6d} {status}")
    if res.bulks:
        lines.append(f"  bulks ({len(res.bulks)} inline candidates):")
        for b in res.bulks:
            status = "OK" if b.valid else f"FAIL: {b.reason}"
            lines.append(f"    exp#{b.export_index} {b.export_name} header@+{b.bulk_header_offset_in_export} flags={b.flags} cnt={b.element_count} size={b.bulk_size} foff={b.file_offset} range={b.target_range} {status}")
    else:
        lines.append("  bulks: none inline detected")
    lines.append(f"  first_error: {res.first_error}")
    lines.append(f"  last_success_export: {res.last_success_export}")
    if res.errors:
        lines.append("  errors:")
        for er in res.errors[:20]:
            lines.append(f"    - {er}")
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Verify UE3 LE package invariants")
    ap.add_argument("package", help="LE package file")
    ap.add_argument("--json-out", dest="json_out", default=None, help="write JSON result")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    res = verify_package(args.package)
    if not args.quiet:
        print(format_result(res))
    if args.json_out:
        # serialize
        d = {
            "path": res.path,
            "file_size": res.file_size,
            "tables": {"NameOffset": res.name_offset, "ImportOffset": res.import_offset,
                       "ExportOffset": res.export_offset, "DependsOffset": res.depends_offset},
            "counts": {"names": res.name_count, "imports": res.import_count, "exports": res.export_count},
            "landing": {"names_end": res.names_end, "imports_end": res.imports_end, "exports_end": res.exports_end},
            "summary_valid": res.summary_valid,
            "invariants_ok": res.invariants_ok,
            "first_error": res.first_error,
            "last_success_export": res.last_success_export,
            "errors": res.errors,
            "exports": [{"index": e.index, "name": e.name, "class": e.class_name,
                         "SerialOffset": e.serial_offset, "SerialSize": e.serial_size, "end": e.end,
                         "valid": e.valid, "reason": e.reason} for e in res.exports],
            "bulks": [{"export": b.export_index, "name": b.export_name, "header_off": b.bulk_header_offset_in_export,
                       "flags": b.flags, "cnt": b.element_count, "size": b.bulk_size, "foff": b.file_offset,
                       "range": b.target_range, "valid": b.valid, "reason": b.reason} for b in res.bulks],
        }
        with open(args.json_out, "w") as f:
            json.dump(d, f, indent=2)
    sys.exit(0 if res.invariants_ok else 1)

if __name__ == "__main__":
    main()
