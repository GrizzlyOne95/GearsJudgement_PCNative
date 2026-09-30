"""Generate CoverSlot residual table without entropy heuristic.

For each CoverLink export containing Slots ArrayProperty, parse the binary slots
field-by-field (declaration order) until bools, then record:
  slot, start, known_fields_end, next_slot_start, residual_size
Across several packages, correlate residual length against flags/cover type etc.

This replaces heuristic scanning with self-delimiting prefix search:
look for DWORD count / count*N struct / GUID / DWORD count ... after bools
that lands exactly on next slot's known start.

Usage:
  python coverslot_residual_probe.py <decompressed-BE.xxx> [--detail]
  python coverslot_residual_probe.py <be2le-LE.xxx>  (Slots bytes still BE)
"""
import struct
import sys

def be_i32(b, o): return struct.unpack_from(">i", b, o)[0]
def le_i32(b, o): return struct.unpack_from("<i", b, o)[0]

# Helpers to locate Slots tag (LE tag headers, BE payload)
def find_slots_infos(buf, names, is_le=True):
    """Return list of (export_idx, slots_val_file_off, slots_body_len, count, export_soff, export_size)"""
    infos=[]
    # Need to parse package to get names etc - use LE parsing for LE files, BE for decompressed
    fl = struct.unpack_from("<i" if is_le else ">i", buf, 12)[0]
    ints_off = 16+fl if fl>0 else 16+(-fl)*2
    fmt = "<12i" if is_le else ">12i"
    flags,nc,no,ec,eo,ic,io,dep,igc,egc,thumb,unk = struct.unpack_from(fmt, buf, ints_off)
    # names
    o=no
    names_list=[]
    for _ in range(nc):
        n = struct.unpack_from("<i" if is_le else ">i", buf, o)[0]; o+=4
        if n>0: s=buf[o:o+n-1].decode('latin-1',errors='replace'); o+=n
        else: o+=(-n)*2
        o+=8
        names_list.append(s)
    # build global NAMES for find
    global NAMES
    NAMES=names_list
    # imports to find CoverLink
    import_names=[]
    o=io
    for _ in range(ic):
        idx=struct.unpack_from("<i" if is_le else ">i", buf, o+20)[0]
        import_names.append(names_list[idx] if 0<=idx<len(names_list) else "?")
        o+=28
    # exports loop
    o=eo
    for idx in range(ec):
        cls=struct.unpack_from("<i" if is_le else ">i", buf, o)[0]
        nmi=struct.unpack_from("<i" if is_le else ">i", buf, o+12)[0]
        sz=struct.unpack_from("<i" if is_le else ">i", buf, o+32)[0]
        soff=struct.unpack_from("<i" if is_le else ">i", buf, o+36)[0]
        gencnt=struct.unpack_from("<i" if is_le else ">i", buf, o+44)[0]
        cls_name = import_names[-cls-1] if cls<0 and -cls-1 < len(import_names) else "?"
        if cls_name=="CoverLink":
            # find Slots tag inside payload
            # need to walk tag stream (LE or BE? payload tags are LE after be2le, BE before)
            hit = find_slots_tag_in_payload(buf, soff, sz, names_list, is_le)
            if hit:
                slots_val, slots_body = hit
                count = struct.unpack_from("<i" if is_le else ">i", buf, slots_val)[0] if is_le else be_i32(buf, slots_val)
                # For BE payload after be2le, Slots count is still BE, so read BE even if file is LE
                # Actually after be2le, tag headers are LE but Slots value bytes remain BE
                # So for LE file, count is BE at slots_val
                if is_le:
                    count = be_i32(buf, slots_val)
                else:
                    count = be_i32(buf, slots_val) if not is_le else le_i32(buf, slots_val)
                infos.append((idx, slots_val, slots_body, count, soff, sz))
        o+=48+4*abs(gencnt)+20
    return infos, names_list

def find_slots_tag_in_payload(buf, soff, size, names, is_le):
    # Walk tag stream to find Slots. Tags are LE after be2le, BE before.
    # For decompressed BE file, tags are BE. For be2le LE file, tags are LE.
    def i(o): return struct.unpack_from("<i" if is_le else ">i", buf, o)[0]
    o=soff
    node=i(o); o+=14
    stack=i(o); o+=4
    if node!=0: o+=4
    o+=4
    end=soff+size
    while o < end:
        if o+24>end: break
        t=i(o)
        if t<0 or t>=len(names): return None
        if names[t]=="None": return None
        tt=i(o+8)
        tsz=i(o+16)
        typ = names[tt] if 0<=tt<len(names) else "?"
        val=o+24
        if typ in ("StructProperty","ByteProperty"): val+=8
        elif typ=="BoolProperty": val+=1
        if names[t]=="Slots":
            return val, tsz-4
        o=val+tsz
    return None

def dump_slots_for_export(buf, is_le, slots_val, slots_body, count, export_idx):
    be = buf
    # For LE be2le output, count is LE (swapped) but slot elements remain BE.
    # So count should have been read as LE; we recompute here to be safe.
    if is_le:
        count_le = le_i32(buf, slots_val)
        if count_le != count:
            print(f"  [count mismatch: probe count {count} vs LE {count_le} -> using LE]")
            count = count_le
    pos = slots_val+4
    end = slots_val+4+slots_body
    print(f" export#{export_idx} slots_val={slots_val} body={slots_body} count={count} pos={pos} end={end} file_len={len(buf)}")
    q=pos
    for slot_idx in range(count):
        start=q
        if q+4>end: print(f"  slot{slot_idx} overrun at owner"); break
        owner=be_i32(be,q); q+=4
        if q+8>end: print(f"  slot{slot_idx} overrun at fct"); break
        fct = (be_i32(be,q), be_i32(be,q+4)); q+=8
        ct = (be_i32(be,q), be_i32(be,q+4)); q+=8
        lcd = (be_i32(be,q), be_i32(be,q+4)); q+=8
        if q+12>end: break
        loc=be[q:q+12]; q+=12
        if q+12>end: break
        rot=be[q:q+12]; q+=12
        if q+4>end: print(f"  slot{slot_idx} overrun at na"); break
        na=be_i32(be,q); q+=4
        if q+8*na>end: print(f"  slot{slot_idx} na={na} overrun need {8*na} have {end-q}"); break
        q+=8*na
        if q+4>end: break
        nf=be_i32(be,q); q+=4
        # firelinks
        for fi in range(nf):
            if q+4>end: print(f"  firelink m overrun"); break
            m=be_i32(be,q); q+=4
            if q+m+6>end: 
                print(f"  slot{slot_idx} firelink {fi} m={m} need {m+6} have {end-q} (q={q} end={end})")
                # dump remaining bytes hex
                print(f"    remaining {min(80, end-q)} bytes: {be[q:q+80].hex()}")
                break
            data=be[q:q+m]; q+=m
            if q+6>end: break
            packed=be_i32(be,q); bits=be[q+4:q+6]; q+=6
        if q+4>end: break
        ne=be_i32(be,q)
        if q+4+4*ne>end: print(f"  slot{slot_idx} ne={ne} overrun"); break
        q+=4+4*ne
        if q+4>end: break
        turn=be_i32(be,q); q+=4
        if q+4>end: break
        ns=be_i32(be,q); q+=4
        for si in range(ns):
            if q+80>end:
                print(f"  slot{slot_idx} slip {si} need 80 have {end-q}")
                break
            q+=80
        if q+4>end: break
        nc2=be_i32(be,q); q+=4
        if q+8*nc2>end:
            print(f"  slot{slot_idx} nc2={nc2} overrun need {8*nc2} have {end-q}")
            break
        q+=8*nc2
        if q+21>end:
            print(f"  slot{slot_idx} bools need 21 have {end-q} at q={q} end={end}")
            break
        bools=be[q:q+21]; q+=21
        known_end=q
        # Now residual handling: peek ahead
        if slot_idx == count-1:
            # last slot: residual is end - known_end
            residual = end - known_end
            print(f"  slot{slot_idx}: owner={owner} fct={fct} ct={ct} lcd={lcd} na={na} nf={nf} ne={ne} ns={ns} nc2={nc2} bools={bools.hex()} known_end={known_end} next_start={end} residual={residual}")
            if residual>0:
                print(f"    residual hex {be[known_end:known_end+min(64,residual)].hex()} ...")
            break
        else:
            # need to find next slot start: scan ahead up to 400 bytes for plausible next owner pattern
            # Plausible next owner 0..10, fct/ct/lcd 35-45
            found=None
            for off in range(0, min(400, end-known_end-32)):
                try:
                    o2=be_i32(be, known_end+off)
                    f0=be_i32(be, known_end+off+4)
                    f1=be_i32(be, known_end+off+8)
                    c0=be_i32(be, known_end+off+12)
                    c1=be_i32(be, known_end+off+16)
                    l0=be_i32(be, known_end+off+20)
                    l1=be_i32(be, known_end+off+24)
                    if 0 <= o2 <= 10 and 37 <= f0 <= 45 and f1==0 and 37 <= c0 <= 45 and c1==0 and 35 <= l0 <= 45 and l1==0:
                        found=off
                        break
                except: pass
            residual = found if found is not None else 0
            next_start = known_end + residual
            print(f"  slot{slot_idx}: owner={owner} fct={fct} ct={ct} lcd={lcd} ns={ns} nc2={nc2} known_end={known_end} next_start={next_start} residual={residual}")
            if residual is not None and residual>0:
                print(f"    residual[{residual}] hex {be[known_end:known_end+min(64,residual)].hex()}")
                # Try to look for self-delimiting prefix inside residual
                # Look for DWORD count pattern
                # Dump first 16 bytes as ints
                if residual>=4:
                    v0=be_i32(be, known_end)
                    print(f"    residual first DWORD BE={v0} LE={le_i32(be, known_end)} hex {be[known_end:known_end+4].hex()}")
            q = next_start
    print(f"  final q={q} end={end} {'OK' if q==end else 'MISMATCH '+str(q-end)}")
    print()

if __name__=="__main__":
    path=sys.argv[1]
    is_le = "be2le" in path or "fixed2" in path or "final" in path or path.endswith(".le.xxx")
    # auto-detect: if file is LE (tag 9E 2A... read as LE equals magic) then is_le true? Actually BE file starts 9E2A83C1, LE file starts C1832A9E
    b=open(path,'rb').read()
    if b[0]==0x9e: is_le=False
    elif b[0]==0xc1: is_le=True
    else: is_le=True
    # For decompressed, it's BE; for be2le, it's LE but Slots bytes still BE
    # So find with appropriate is_le flag for tag walking, but slot bytes are always BE
    infos, names = find_slots_infos(b, [], is_le)
    print(f"found {len(infos)} CoverLink exports with Slots in {path} (is_le={is_le})")
    # fix counts for LE
    fixed_infos=[]
    for idx, slots_val, slots_body, count, soff, sz in infos:
        if is_le:
            cnt_le = le_i32(b, slots_val)
            fixed_infos.append((idx, slots_val, slots_body, cnt_le, soff, sz))
        else:
            fixed_infos.append((idx, slots_val, slots_body, count, soff, sz))
    for idx, slots_val, slots_body, count, soff, sz in fixed_infos[:3]:  # first 3
        dump_slots_for_export(b, is_le, slots_val, slots_body, count, idx)
