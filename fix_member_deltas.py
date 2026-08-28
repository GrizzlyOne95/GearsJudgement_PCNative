"""Stage corrected BEGIN/END PROPS blocks for MEMBER_DELTA classes.

For every class sweep_v3 classified MEMBER_DELTA (v845 gained/lost members vs
header):
  - ADDED members get freshly generated declarations from the v845 package
    payloads (reusing gen_native_block.py's type resolution).
  - KEPT members reuse existing header declaration text verbatim.
  - Order comes from the v845 relinked chain (sorted by offset).
Staged only if the packing simulation reproduces EVERY v845 offset exactly.

Removed members: dropped only when the class is a LEAF in the dumped
hierarchy (removing would shrink the parent and cascade drift into children);
otherwise the class is flagged REMOVED_AT_PARENT for hand treatment.
"""
import os, re, sys, json

sys.path.insert(0, r"C:\Games\NostalgiaBundle\projects\GearsJudgement_PCNative")
sys.path.insert(0, r"C:\Users\iestu\AppData\Local\Temp\opencode")

import gen_native_block as gnb          # noqa: E402
import sweep_v3 as sw                   # noqa: E402

SCRIPT_DIR = r"C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\GearGame\Script"
MANIFEST_TXT = os.path.join(SCRIPT_DIR, "Manifest.txt")
STAGE = r"C:\Users\iestu\AppData\Local\Temp\opencode\delta-staging"

PACKAGES = ["Engine", "GearGame", "GameFramework", "IpDrv", "UnrealEd", "Core"]


def load_pkg(pkg):
    mpath = os.path.join(r"C:\Games\NostalgiaBundle\projects\GearsJudgement_PCNative",
                         "package-probe", "build", "runtime-v4", "%s.v845.manifest.json" % pkg)
    if not os.path.exists(mpath):
        return None
    doc = json.load(open(mpath))
    src = doc.get("source") or os.path.join(SCRIPT_DIR, pkg + ".u")
    if not os.path.exists(src):
        src = os.path.join(SCRIPT_DIR, pkg + ".u")
    if not os.path.exists(src):
        return None
    exports, imports, blob = doc["exports"], doc.get("imports", []), open(src, "rb").read()
    return dict(exports=exports, imports=imports, blob=blob,
                by_path={(".".join((e.get("object_path") or "").split(".")[-3:])): e
                         for e in exports if e.get("object_path")}, name=pkg)



def _with_identifier(line, new_id):
    """Replace the declared identifier in a decl line, preserving true case."""
    m2 = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?::\d+)?\s*(?:\[[^\]]*\])?\s*;", line)
    if not m2:
        return line
    return line[:m2.start(1)] + new_id + line[m2.end(1):]

def main():
    chains = sw.parse_log()
    blocks, classes = sw.scan_headers()
    pkgs = {}
    for p in PACKAGES:
        d = load_pkg(p)
        if d:
            pkgs[p] = d
    actors = set()
    try:
        actors = gnb.actor_classes(MANIFEST_TXT)
    except Exception as e:
        print("actor list unavailable (%s) -> object refs will use U-prefix" % e)

    cls_pkg_index = {}
    for p, d in pkgs.items():
        for e in d["exports"]:
            path = e.get("object_path") or ""
            parts = path.split(".")
            if len(parts) >= 3 and parts[-2] not in cls_pkg_index:
                cls_pkg_index[parts[-2]] = p

    def class_pkg(cname):
        p = cls_pkg_index.get(cname)
        return (p, pkgs[p]) if p else (None, None)

    # re-run sweep_v3 verdict logic to obtain MEMBER_DELTA set + details
    verdicts = sw_sweep(chains, blocks, classes)

    os.makedirs(STAGE, exist_ok=True)
    staged, skipped = [], []
    for cname, (cat, detail) in sorted(verdicts.items()):
        if cat != "MEMBER_DELTA":
            continue
        data = chains[cname]
        path, bstart, bend, decls = blocks[cname]
        hmap = dict(decls)
        hset = set(hmap)
        raw_hmap = {}
        _txt = open(path, encoding="utf-8", errors="replace").read()
        for _ln in _txt[bstart:bend].splitlines():
            _s = _ln.strip()
            if not _s or _s.startswith("//"):
                continue
            _m2 = sw.NAME_RE.search(_s)
            if _m2:
                raw_hmap[_m2.group(1).lower()] = _s
        par = parent_of_local.get(cname)
        par_size = chains[par]["size"] if (par and par in chains) else 0
        cand = [e for e in data["entries"] if e["off"] >= par_size]
        cand_names = {e["name"].lower() for e in cand}
        added = sorted(cand_names - hset)
        removed = sorted(hset - cand_names)

        leaf = all(parent_of_local.get(ch) != cname for ch in chains)
        if removed and not leaf:
            skipped.append((cname, "REMOVED_AT_PARENT %s (has children)" % removed))
            continue

        needs_pkg = [m for m in added
                     if not m.startswith("vftable_") and (m + "_deprecated") not in raw_hmap]
        pkgname, pkgd = class_pkg(cname)
        if needs_pkg and pkgd is None:
            skipped.append((cname, "package not found for added %s" % sorted(needs_pkg)))
            continue

        gen_lines = {}
        fail = None
        if added:
            if pkgd is None:
                skipped.append((cname, "package unavailable for %s" % sorted(added)[:4]))
                continue
            exports, imports, blob = pkgd["exports"], pkgd["imports"], pkgd["blob"]
            by_path = {}
            for e in exports:
                pathstr = e.get("object_path") or ""
                parts = pathstr.split(".")
                if len(parts) >= 3 and parts[-2] == cname and e["class_name"].endswith("Property"):
                    by_path[".".join(parts[-3:])] = e
            for m in added:
                if m.startswith("vftable_"):
                    # engine-synthesized interface vtable slot (Infantry precedent):
                    gen_lines[m] = raw_hmap.get(m) or ("    FPointer %s;" %
                                                       "_".join(w.capitalize() for w in m.split("_")))
                    continue
                dep = raw_hmap.get(m + "_deprecated")
                if dep is not None:
                    # v845 un-deprecated the member: reuse original decl, rename id
                    gen_lines[m] = re.sub(re.escape(m + "_deprecated"), m, dep,
                                          flags=re.IGNORECASE)
                    continue
                pe = by_path.get("%s.%s" % (cname, m)) or pkgd["by_path"].get("%s.%s.%s" % (pkgname, cname, m))
                if pe is None:
                    fail = "no export for added %s" % m
                    break
                cls = pe["class_name"]
                target = gnb.type_ref(pe, blob, exports, imports) if cls in gnb.TYPED else None
                if cls == "BoolProperty":
                    gen_lines[m] = "    BITFIELD %s:1;" % m
                    continue
                if cls == "MapProperty":
                    fail = "MapProperty %s needs reference-header (unsupported)" % m
                    break
                t = gnb.cpp_type(cls, target, actors, pkgd["by_path"], blob,
                                 exports, imports, cname, m)
                if t == gnb.UNSUPPORTED or t.startswith(gnb.UNSUPPORTED):
                    fail = "unsupported type for %s (%s)" % (m, cls)
                    break
                dim = gnb.array_dim(pe, blob)
                suffix = "[%d]" % dim if dim > 1 else ""
                if cls == "StructProperty":
                    t = gnb.STRUCT_ALIAS.get(target, "F%s" % target)
                gen_lines[m] = "    %s %s%s;" % (t, m, suffix)
            if fail:
                skipped.append((cname, fail))
                continue

        by_name = {e["name"].lower(): e for e in cand}
        # true-case display names straight from the relinked chain
        true_name = {e["name"].lower(): e["name"] for e in cand}
        seq = sorted(cand, key=lambda e: e["off"])
        lines = []
        for e in seq:
            n = e["name"].lower()
            if n in hmap:
                lines.append(hmap[n])
            else:
                # generated line: rebuild with true-case identifier
                base = gen_lines[n]
                lines.append(_with_identifier(base, true_name[n]))
        offs, end = sw.simulate(
            [dict(name=e["name"], elem=e["elem"], dim=e["dim"], propcls=e["propcls"]) for e in seq],
            par_size)
        bad = [(n, by_name[n.lower()]["off"], o) for (n, o) in offs if by_name[n.lower()]["off"] != o]
        if bad or end != data["size"]:
            skipped.append((cname, "sim mismatch %s end=%d want=%d" %
                            (bad[:2], end, data["size"])))
            continue
        out = os.path.join(STAGE, "%s.block.txt" % cname)
        open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        staged.append((cname, len(added), len(removed)))

    print("staged %d, skipped %d" % (len(staged), len(skipped)))
    for s in staged:
        print("  STAGE %s (+%d added / -%d removed)" % s)
    for s in skipped:
        print("  SKIP  %s: %s" % s)


# --- minimal re-run of sweep_v3 verdict computation (import-safe copy) ---
parent_of_local = {}

def sw_sweep(chains, blocks, classes):
    global parent_of_local
    for sn, (cpp, par, p) in classes.items():
        parent_of_local[sn] = sw.strip_prefix(par)

    def depth(sn, seen=None):
        seen = seen or set()
        if sn in seen or sn not in parent_of_local:
            return 0
        seen.add(sn)
        return 1 + depth(parent_of_local[sn], seen)

    targets = [c for c in chains if c in blocks]
    targets.sort(key=lambda c: (depth(c), c))
    verdicts = {}
    for cname in targets:
        data = chains[cname]
        path, bstart, bend, decls = blocks[cname]
        hnames = [n for n, _ in decls]
        hset = set(hnames)
        own_entries = [e for e in data["entries"] if e["name"].lower() in hset]
        par = parent_of_local.get(cname)
        par_size = chains[par]["size"] if (par and par in chains) else None
        cand = [e for e in data["entries"] if (par_size is None or e["off"] >= par_size)]
        cand_names = {e["name"].lower() for e in cand}
        if par_size is None:
            verdicts[cname] = ("NO_PARENT_CHAIN", "")
            continue
        extra_hdr = hset - cand_names
        if extra_hdr:
            verdicts[cname] = ("MEMBER_DELTA", "removed=%s" % sorted(extra_hdr)[:6])
            continue
        added = cand_names - hset
        if added:
            verdicts[cname] = ("MEMBER_DELTA", "added=%s" % sorted(added)[:6])
            continue
        if Counter_check(own_entries, hset):
            verdicts[cname] = ("DUP", "")
            continue
        by_name = {e["name"].lower(): e for e in cand}
        seq_hdr = [by_name[n] for n in hnames]
        offs, end = sw.simulate(seq_hdr, par_size)
        bad = [(n, by_name[n.lower()]["off"], o) for (n, o) in offs if by_name[n.lower()]["off"] != o]
        if not bad and end == data["size"]:
            verdicts[cname] = ("OK", "")
            continue
        seq_sorted = sorted(cand, key=lambda e: e["off"])
        offs2, end2 = sw.simulate(seq_sorted, par_size)
        bad2 = [(n, by_name[n.lower()]["off"], o) for (n, o) in offs2 if by_name[n.lower()]["off"] != o]
        if not bad2 and end2 == data["size"]:
            verdicts[cname] = ("REORDER", "")
        elif end2 != data["size"]:
            verdicts[cname] = ("SIZE_MISMATCH", "end=%d v845=%d" % (end2, data["size"]))
        else:
            verdicts[cname] = ("LAYOUT_DIFF", str(bad[:2]))
    return verdicts


def Counter_check(entries, hset):
    from collections import Counter
    return Counter(e["name"].lower() for e in entries) != Counter({n: 1 for n in hset})


if __name__ == "__main__":
    main()
