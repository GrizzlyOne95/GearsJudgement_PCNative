"""Diff a UClass's declared member chain between Judgment (v845) and Gears 3 (v828).

A class's members are the exports whose object_path is "<Package>.<Class>.<Member>", so this
needs only the export table -- the layer already proven compatible between the two versions.
"""
import json
import sys


def load(path):
    with open(path) as handle:
        return json.load(handle)["exports"]


def members(exports, class_name):
    """Direct members of a class, in export-table order."""
    prefix_end = "." + class_name + "."
    out = []
    for e in exports:
        path = e.get("object_path") or ""
        i = path.find(prefix_end)
        if i < 0:
            continue
        rest = path[i + len(prefix_end):]
        if "." in rest:          # nested deeper (e.g. inside a struct/state)
            continue
        out.append((e["class_name"], rest))
    return out


def report(jex, gex, class_name):
    j = members(jex, class_name)
    g = members(gex, class_name)
    if not j and not g:
        return
    jp = [(c, n) for c, n in j if c.endswith("Property")]
    gp = [(c, n) for c, n in g if c.endswith("Property")]
    jn = [n for _, n in jp]
    gn = [n for _, n in gp]

    only_j = [n for n in jn if n not in gn]
    only_g = [n for n in gn if n not in jn]
    jt = {n: c for c, n in jp}
    gt = {n: c for c, n in gp}
    changed = [(n, gt[n], jt[n]) for n in jn if n in gt and jt[n] != gt[n]]

    status = "IDENTICAL"
    if only_j or only_g or changed:
        status = "DIFFERS"
    elif jn != gn:
        status = "REORDERED"

    print(f"=== {class_name}: {status}   (judgment {len(jp)} props / gears3 {len(gp)} props)")
    if only_j:
        print(f"    + Judgment-only: {only_j}")
    if only_g:
        print(f"    - Gears3-only  : {only_g}")
    if changed:
        print(f"    ! type changes : {changed}")
    if status == "REORDERED":
        print(f"      judgment: {jn}")
        print(f"      gears3  : {gn}")
    # non-property members (functions/states/structs) count, as a coarse signal
    jf = len(j) - len(jp)
    gf = len(g) - len(gp)
    if jf != gf:
        print(f"    ~ other members (funcs/states/structs): judgment={jf} gears3={gf}")


if __name__ == "__main__":
    jex = load(sys.argv[1])
    gex = load(sys.argv[2])
    for cls in sys.argv[3:]:
        report(jex, gex, cls)
