"""Compare the workspace's generated native headers with Judgment's script layout.

python audit_native_layouts.py <judgprops dump> <Development\\Src directory>

The dump is the loader's console output of `JUDGPROPS *` with the log prefix
removed (one header line per struct or class, then one line per own property).
Each `struct F<Name>` / `class A|U<Name>` in `*/Inc/*Classes.h` is matched by
name; its member names, in order, must equal the script's own property names.
A native struct whose members differ is laid out differently from what script
and garbage collection expect (found this way: FPlayerInfo, 184 bytes native
against 48 in script). Read-only.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

HEADER = re.compile(r"^ (\w+) (\S+) size=(\d+) super=(\S+) super-size=(\d+)")
PROPERTY = re.compile(r"^   off=(\d+) size=(\d+) dim=(\d+) (.*?) (\w+)(?: mask=[0-9A-F]+)?$")
BLOCK = re.compile(r"^(struct|class) ([FAU]\w+)[^\n{;]*\n\{(.*?)^\};", re.S | re.M)
MEMBER = re.compile(r"(\w+)\s*(?:\[[^\]]*\])?\s*(?::\s*\d+)?(?:\s+GCC_BITFIELD_MAGIC)?\s*;$")


def script_layouts(path):
    layouts = defaultdict(list)
    current = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        head = HEADER.match(line)
        if head:
            current = {"kind": head.group(1), "path": head.group(2), "size": int(head.group(3)), "props": []}
            layouts[head.group(2).split(".")[-1].split(":")[-1]].append(current)
            continue
        prop = PROPERTY.match(line)
        if prop and current is not None:
            current["props"].append(prop.group(5))
    return layouts


def native_members(body, name):
    if "//## BEGIN PROPS" in body:
        body = body.split("//## BEGIN PROPS", 1)[1].split("//## END PROPS", 1)[0]
    else:
        body = body.split("/** Constructors */", 1)[0]
    members = []
    for raw in body.splitlines():
        line = raw.split("//", 1)[0].strip()
        # "MS_ALIGN(4) BYTE Value GCC_ALIGN(4);" is how a class of only bytes is declared.
        line = re.sub(r"(MS_ALIGN|GCC_ALIGN|GCC_PACK)\(\d+\)", "", line).strip()
        if "(" in line:
            if members or "{" in line or line.endswith(")"):
                break  # first function or constructor: the data members are over
            continue
        if (not line.endswith(";") or "<<" in line or "=" in line
                or line.startswith(("SCRIPT_ALIGN", "friend", "typedef", "return", "using"))):
            continue
        # "BYTE A, B, C;" declares several members on one line.
        for part in line[:-1].split(",") if "<" not in line else [line[:-1]]:
            found = MEMBER.search(part.strip() + ";")
            if found:
                members.append(found.group(1))
    return [re.sub(r"_DEPRECATED$", "", member) for member in members]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    layouts = script_layouts(sys.argv[1])
    compared = mismatched = 0
    for header in sorted(Path(sys.argv[2]).glob("*/Inc/*Classes.h")):
        text = header.read_text(encoding="latin-1")
        for block in BLOCK.finditer(text):
            name = block.group(2)[1:]
            candidates = [c for c in layouts.get(name, [])
                          if (c["kind"] == "ScriptStruct") == (block.group(1) == "struct" and block.group(2)[0] == "F")]
            if not candidates:
                continue
            members = native_members(block.group(3), name)
            if not members and not any(c["props"] for c in candidates):
                continue
            compared += 1
            # Interface vtable slots are script-side placeholders for C++ base classes.
            for candidate in candidates:
                candidate["props"] = [prop for prop in candidate["props"] if not prop.startswith("VfTable_")]
            if any(c["props"] == members for c in candidates):
                continue
            mismatched += 1
            best = max(candidates, key=lambda c: len(set(c["props"]) & set(members)))
            extra = [m for m in members if m not in best["props"]]
            missing = [p for p in best["props"] if p not in members]
            order = "" if extra or missing else " (same names, different order)"
            print(f"{header.parent.parent.name}/{header.name}: {block.group(2)} vs {best['path']}{order}")
            if extra:
                print(f"    only in header ({len(extra)}): {', '.join(extra[:8])}")
            if missing:
                print(f"    only in script ({len(missing)}): {', '.join(missing[:8])}")
    print(f"compared {compared} native structs/classes; {mismatched} differ")


if __name__ == "__main__":
    main()
