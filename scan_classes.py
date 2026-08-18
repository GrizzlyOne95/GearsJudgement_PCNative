"""Scan a whole script package for classes whose property chain differs between
Judgment (v845) and Gears 3 (v828). This is the native-class reconstruction worklist."""
import json
import sys
from collections import defaultdict


def load(path):
    with open(path) as handle:
        return json.load(handle)["exports"]


def build(exports):
    """owner name -> ordered [(propClass, propName)], plus owner name -> kind.

    Owners are matched at ANY nesting depth via parts[-2]. An earlier version of
    this scan required a 3-part path, which silently skipped every ScriptStruct
    whose members nest deeper -- it missed FPostProcessSettings gaining 43
    members, the single largest delta in the package.
    """
    props = defaultdict(list)
    owners = {}
    for e in exports:
        if e["class_name"] in ("Class", "ScriptStruct"):
            owners[e["object_name"]] = e["class_name"]
        path = e.get("object_path") or ""
        parts = path.split(".")
        if len(parts) >= 3 and e["class_name"].endswith("Property"):
            props[parts[-2]].append((e["class_name"], parts[-1]))
    return props, owners


def main(jpath, gpath, show_identical=False):
    jprops, jowners = build(load(jpath))
    gprops, gowners = build(load(gpath))
    jclasses, gclasses = set(jowners), set(gowners)

    only_j = sorted(jclasses - gclasses)
    shared = sorted(jclasses & gclasses)

    differing = []
    for c in shared:
        jn = [n for _, n in jprops.get(c, [])]
        gn = [n for _, n in gprops.get(c, [])]
        jt = {n: t for t, n in jprops.get(c, [])}
        gt = {n: t for t, n in gprops.get(c, [])}
        add = [n for n in jn if n not in gn]
        rem = [n for n in gn if n not in jn]
        chg = [(n, gt[n], jt[n]) for n in jn if n in gt and jt[n] != gt[n]]
        # Reordering must be tested on the SHARED members only, and independently
        # of additions. An earlier version wrote `not add and not rem and jn != gn`,
        # which meant reordering was never even checked for any owner that also
        # gained a member -- i.e. almost all of them. That hid FPostProcessSettings
        # moving DOF_BlurBloomKernelSize from position 8 to 3, and produced a false
        # "every difference is purely additive" headline.
        gset, jset = set(gn), set(jn)
        reordered = [n for n in jn if n in gset] != [n for n in gn if n in jset]
        if add or rem or chg or reordered:
            differing.append((c, add, rem, chg, reordered, len(gn), len(jn)))

    ncls = sum(1 for d in differing if jowners.get(d[0]) == "Class")
    nstr = sum(1 for d in differing if jowners.get(d[0]) == "ScriptStruct")
    print(f"owners (Class+ScriptStruct): judgment={len(jclasses)} gears3={len(gclasses)}")
    print(f"Judgment-only owners: {len(only_j)}")
    print(f"shared owners with DIFFERING member layout: {len(differing)} of {len(shared)}"
          f"   ({ncls} classes, {nstr} structs)")
    print()
    print("=== layout-differing shared owners (these break native object construction) ===")
    for c, add, rem, chg, reordered, gcount, jcount in differing:
        print(f"  [{jowners.get(c,'?')}] {c}  (gears3 {gcount} -> judgment {jcount} props)")
        if add:
            print(f"      + {add}")
        if rem:
            print(f"      - {rem}")
        if chg:
            print(f"      ! {chg}")
        if reordered:
            print("      ! same set, different order")
    print()
    print("=== Judgment-only classes in this package ===")
    for c in only_j:
        n = len(jprops.get(c, []))
        print(f"  {c} ({n} props)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
