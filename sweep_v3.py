"""Hierarchy-aware layout sweep (v3).

Per dumped class (chain + logged v845 PropertiesSize):
  - find parent via header 'class [AU]<Name> : public <Parent>' declarations
  - process parents first; child base = parent's logged v845 size
    (requires parent native size == parent v845 size, enforced top-down)
  - simulate header decl order and sorted order against the chain
Verdicts: OK / REORDER / SIZE_MISMATCH / MISSING_MEMBERS / EXTRA_MEMBERS / NO_CHAIN
Stages reordered blocks for REORDER classes.
"""
import os
import re
import sys
import json
import struct
from collections import Counter, defaultdict

LOG = r"C:\Games\NostalgiaBundle\logs\GearsJudgement_PCNative-runtime\JudgmentLoader-v49-layoutall.log"
SRC = r"C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\Development\Src"
STAGE = r"C:\Users\iestu\AppData\Local\Temp\opencode\sweep-staging"

HDR_LINE_RE = re.compile(r"\[JUDGLAYOUT\]\[CLS:([^\]]+)\]\s*(.+?)\s*$")
ENTRY_RE = re.compile(r"^(\S+) @(-?\d+) elem=(\d+) dim=(\d+) cls=(\w+)$")
SIZE_RE = re.compile(r"^PropertiesSize=(-?\d+)$")
NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?::\d+)?\s*(?:\[[^\]]*\])?\s*;")


def parse_log():
    chains = {}
    cur = None
    with open(LOG, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = HDR_LINE_RE.search(ln)
            if not m:
                continue
            cname, payload = m.groups()
            ms = SIZE_RE.match(payload)
            if ms:
                cur = chains.setdefault(cname, {"size": int(ms.group(1)), "entries": []})
                continue
            me = ENTRY_RE.match(payload)
            if me and cur is not None:
                n, o, e, d, c = me.groups()
                cur["entries"].append(dict(name=n, off=int(o), elem=int(e),
                                           dim=int(d), propcls=c))
    return chains


def scan_headers():
    """returns blocks{owner:(file,bstart,bend,decls)}, classes{scriptname:(cppname,parent_cpp,file)}"""
    blocks = {}
    classes = {}
    cls_re = re.compile(r"\bclass\s+([AU])([A-Za-z0-9_]+)\s*:\s*public\s+([A-Za-z0-9_]+)")
    for root, _, files in os.walk(SRC):
        if not root.endswith("Inc"):
            continue
        for fn in files:
            if not fn.endswith(".h"):
                continue
            p = os.path.join(root, fn)
            txt = open(p, encoding="utf-8", errors="replace").read()
            for m in cls_re.finditer(txt):
                pfx, sn, parent = m.groups()
                classes.setdefault(sn, (pfx + sn, parent, p))
            for m in re.finditer(r"//## BEGIN PROPS ([A-Za-z0-9_]+)", txt):
                owner = m.group(1)
                eidx = txt.find(f"//## END PROPS {owner}", m.end())
                if eidx < 0:
                    continue
                decls = []
                for raw in txt[m.end():eidx].splitlines():
                    s = raw.strip()
                    if not s or s.startswith("//"):
                        continue
                    nm = NAME_RE.search(s)
                    if not nm:
                        continue
                    ln = nm.group(1).lower()
                    if ln == "script_align" or ln.endswith("_deprecated"):
                        continue
                    decls.append((ln, s))
                if owner not in blocks:
                    blocks[owner] = (p, m.end(), eidx, decls)
    return blocks, classes


def strip_prefix(cpp):
    return cpp[1:] if cpp and cpp[0] in "AU" else cpp


def align(v, a):
    return -(-v // a) * a


def simulate(seq, base):
    """seq: list of dicts(name, elem, dim, propcls). returns list offsets,end"""
    out = []
    cur = base
    bf_base = None
    bf_bits = 0

    def close_bf():
        nonlocal cur, bf_base, bf_bits
        if bf_base is not None:
            cur = max(cur, bf_base + 4)
            bf_base = None
            bf_bits = 0

    for e in seq:
        if e["propcls"] == "BoolProperty":
            if bf_base is None:
                cur = align(cur, 4)
                bf_base, bf_bits = cur, 0
            elif bf_bits >= 32:
                cur = bf_base + 4
                bf_base, bf_bits = cur, 0
            out.append((e["name"], bf_base))
            bf_bits += 1
            continue
        close_bf()
        a = 1 if (e["propcls"] == "ByteProperty" and e["elem"] == 1) else 4
        cur = align(cur, a)
        out.append((e["name"], cur))
        cur += e["elem"] * e["dim"]
    close_bf()
    return out, cur


def main():
    chains = parse_log()
    blocks, classes = scan_headers()
    print(f"classes dumped: {len(chains)}  header owners: {len(blocks)}  cpp classes known: {len(classes)}")

    # depth via parent links (script names)
    parent_of = {}
    for sn, (cpp, par, p) in classes.items():
        parent_of[sn] = strip_prefix(par)

    def depth(sn, seen=None):
        seen = seen or set()
        if sn in seen or sn not in parent_of:
            return 0
        seen.add(sn)
        return 1 + depth(parent_of[sn], seen)

    targets = [c for c in chains if c in blocks]
    targets.sort(key=lambda c: (depth(c), c))

    verdicts = {}
    stage_ok = {}

    for cname in targets:
        data = chains[cname]
        entries = data["entries"]
        path, bstart, bend, decls = blocks[cname]
        hnames = [n for n, _ in decls]
        hset = set(hnames)
        own_entries = [e for e in entries if e["name"].lower() in hset]
        chain_own_names = {e["name"].lower() for e in own_entries}
        missing_in_hdr = sorted({e["name"].lower() for e in entries
                                 } - {e['name'].lower() for e in own_entries})
        # only consider members ABOVE parent size as potentially ours
        par = parent_of.get(cname)
        par_size = chains[par]["size"] if (par and par in chains) else None

        # candidates for own block: chain entries >= par_size (or all if unknown)
        cand = [e for e in entries if (par_size is None or e["off"] >= par_size)]
        cand_missing = sorted(hset - {e["name"].lower() for e in cand})
        extra = sorted({e["name"].lower() for e in cand} - hset)

        if par_size is None:
            verdicts[cname] = ("NO_PARENT_CHAIN", f"parent={par}")
            continue
        if cand_missing:
            verdicts[cname] = ("EXTRA_IN_HEADER", f"{cand_missing} not in v845 above @{par_size}")
            continue
        if len(own_entries) != len(hset) or Counter(e['name'].lower() for e in own_entries) != Counter({n: 1 for n in hset}):
            verdicts[cname] = ("MISSING_MEMBERS", f"set-diff; below-parent: {sorted(set(missing_in_hdr))[:6]}")
            continue

        by_name = {e["name"].lower(): e for e in cand}
        if not set(hnames) <= set(by_name):
            gone = sorted(set(hnames) - set(by_name))
            verdicts[cname] = ("MOVED_TO_PARENT", f"{gone[:6]} now live at/below @{par_size}")
            continue
        seq_hdr = [by_name[n] for n in hnames]
        offs_hdr, end_hdr = simulate(seq_hdr, par_size)
        bad_hdr = [(n, by_name[n.lower()]["off"], o) for (n, o) in offs_hdr if by_name[n.lower()]["off"] != o]

        if not bad_hdr and end_hdr == data["size"]:
            verdicts[cname] = ("OK", "")
            stage_ok[cname] = None
            continue

        cand_names = {e["name"].lower() for e in cand}
        if cand_names != hset:
            added = sorted(cand_names - hset)
            removed = sorted(hset - cand_names)
            verdicts[cname] = ("MEMBER_DELTA", f"added={added[:6]} removed={removed[:6]}")
            continue
        seq_sorted = sorted(cand, key=lambda e: e["off"])
        offs_s, end_s = simulate(seq_sorted, par_size)
        bad_s = [(n, by_name[n.lower()]["off"], o) for (n, o) in offs_s if by_name[n.lower()]["off"] != o]
        if not bad_s and end_s == data["size"]:
            verdicts[cname] = ("REORDER", "")
            stage_ok[cname] = [dict(e) for e in seq_sorted]
            continue

        if end_hdr != data["size"]:
            verdicts[cname] = ("SIZE_MISMATCH",
                               f"native-sim end={end_hdr} v845={data['size']} (par_size={par_size})")
        else:
            verdicts[cname] = ("LAYOUT_DIFF",
                               f"{len(bad_hdr)} mismatches, first {bad_hdr[0]}")

    counts = Counter(v[0] for v in verdicts.values())
    print("\n=== counts ===")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")

    for cat in ("REORDER", "SIZE_MISMATCH", "LAYOUT_DIFF", "MISSING_MEMBERS",
                "EXTRA_IN_HEADER", "NO_PARENT_CHAIN", "MEMBER_DELTA"):
        items = [(c, v[1]) for c, v in sorted(verdicts.items()) if v[0] == cat]
        print(f"\n--- {cat} ({len(items)}) ---")
        for c, d in items[:40]:
            print(f"  {c}: {d}")
        if len(items) > 40:
            print(f"  ... +{len(items)-40} more")

    os.makedirs(STAGE, exist_ok=True)
    for cname, seq in stage_ok.items():
        if not seq:
            continue
        path, bstart, bend, decls = blocks[cname]
        hmap = dict(decls)
        lines = [hmap[e["name"].lower()] for e in seq]
        with open(os.path.join(STAGE, f"{cname}.block.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    print(f"\nstaged reorder blocks -> {STAGE}")


if __name__ == "__main__":
    main()
