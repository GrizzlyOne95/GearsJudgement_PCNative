"""Compare native exec thunks with the parameter lists Judgment's script passes.

python audit_native_thunks.py <judgfuncs dump> <Development\\Src directory> [--all]

The dump is the loader's console output of `JUDGFUNCS *` with the log prefix
removed, one line per function:
    native CoverLink.CoverLink :: Bool IsValidClaim(Pawn ChkClaim, Int SlotIdx, optional Bool bSkipTeamCheck)
Each bound native is matched to `[AU]<Class>::exec<Function>`: a
`DECLARE_FUNCTION(exec...) { P_GET_...; P_FINISH; }` thunk in `*/Inc/*.h` or a
hand-written `void X::exec...(FFrame& Stack, RESULT_DECL)` body in `*/Src/*.cpp`.
The P_GET_ macros before the first P_FINISH are the parameters the native reads.

Why it matters: Judgment's bytecode passes Judgment's parameter list. A thunk
that reads fewer leaves the code pointer short; P_FINISH then skips one byte of
the next argument and the caller spins on a stray EndFunctionParms (found this
way: CoverLink.IsValidClaim, 5 passed against 4 read, the "AI runaway" in
AICmd_Move_Run2Cover and AICmd_Move_Mantle). A thunk that reads a different
type writes the wrong size into its local. Reading more than is passed is
harmless (EndFunctionParms re-reads as zero) unless the extra one is not last.

Severity: SHORT (script passes more), KIND (type differs at a position),
LONG (native reads more), FLAGS (optional/out differ; listed with --all).
Script enums and object classes print alike, so either matches BYTE or OBJECT;
a static-array read (P_GET_ARRAY_REF) matches any type. Natives the port wrote
itself and interface thunks are not parsed ("without a parsed thunk"); the
loader logs `[JUDGNATIVE] short parameter read` for any of those at run time.
Read-only.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

FUNC_LINE = re.compile(r"^\s*(native|script|UNBOUND) (\w+)\.(\w+) :: (.*?) (\w+)\((.*)\)\s*$")
CLASS_DECL = re.compile(r"^class\s+(?:\w+_API\s+)?(\w+)\b[^;\n]*$", re.M)
HEADER_THUNK = re.compile(r"DECLARE_FUNCTION\(exec(\w+)\)\s*(;|\{)")
CPP_THUNK = re.compile(r"^void\s+(\w+)::exec(\w+)\s*\(\s*FFrame\s*&\s*Stack\s*,\s*RESULT_DECL\s*\)\s*\{", re.M)
P_GET = re.compile(r"\bP_GET_(\w+?)\s*\(")
SIMPLE = {"Int": "INT", "Float": "FLOAT", "Bool": "UBOOL", "byte": "BYTE", "Name": "NAME", "Str": "STR",
          "Delegate": "DELEGATE", "Interface": "INTERFACE", "QWord": "QWORD", "Map": "MAP"}
NATIVE_KIND = {"ACTOR": "OBJECT", "STRUCT_INIT": "STRUCT", "VECTOR": "STRUCT", "ROTATOR": "STRUCT",
               "VECTOR2D": "STRUCT", "MATRIX": "STRUCT", "TINTERFACE": "INTERFACE", "DWORD": "INT"}


def script_functions(path):
    funcs = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = FUNC_LINE.match(line)
        if not m or m.group(1) != "native":
            continue
        parms = []
        for text in filter(None, (p.strip() for p in m.group(6).split(", "))):
            words = text.split(" ")
            optional = "optional" in words[:2]
            out = "out" in words[:2]
            kind_text = " ".join(w for w in words[:-1] if w not in ("optional", "out"))
            if kind_text.startswith("struct "):
                kind = "STRUCT"
            elif kind_text.startswith("array<"):
                kind = "TARRAY"
            else:
                kind = SIMPLE.get(kind_text, "OBJECT|BYTE")
            parms.append((kind, optional, out, words[-1], kind_text))
        funcs[(m.group(2), m.group(5))] = {"outer": m.group(3), "parms": parms, "line": line.strip()}
    return funcs


def read_parms(body):
    """The P_GET_ macros a thunk runs before its first P_FINISH; None when it has no P_FINISH."""
    end = body.find("P_FINISH")
    if end < 0:
        return None
    parms = []
    for m in P_GET.finditer(body[:end]):
        name = m.group(1)
        if name == "SKIP_OFFSET":
            continue
        out = name.endswith("_REF")
        if out:
            name = name[:-4]
        optional = name.endswith("_OPTX")
        if optional:
            name = name[:-5]
        parms.append((NATIVE_KIND.get(name, name), optional, out))
    return parms


def native_thunks(src):
    thunks = defaultdict(list)
    for header in sorted(Path(src).glob("*/Inc/*.h")):
        text = header.read_text(encoding="utf-8", errors="replace")
        classes = [(m.start(), m.group(1)) for m in CLASS_DECL.finditer(text)]
        found = list(HEADER_THUNK.finditer(text))
        for i, m in enumerate(found):
            if m.group(2) == ";":
                continue
            owner = next((name for pos, name in reversed(classes) if pos < m.start()), None)
            stop = found[i + 1].start() if i + 1 < len(found) else m.end() + 4000
            parms = read_parms(text[m.end():stop])
            if owner and parms is not None:
                thunks[(owner[1:], m.group(1))].append((parms, f"{header.parent.parent.name}/Inc/{header.name}"))
    for cpp in sorted(Path(src).glob("*/Src/*.cpp")):
        text = cpp.read_text(encoding="utf-8", errors="replace")
        for m in CPP_THUNK.finditer(text):
            close = text.find("\n}", m.end())
            parms = read_parms(text[m.end():close if close > 0 else m.end() + 8000])
            if parms is not None:
                thunks[(m.group(1)[1:], m.group(2))].append((parms, f"{cpp.parent.parent.name}/Src/{cpp.name}"))
    return thunks


def kinds_match(script_kind, native_kind):
    # P_GET_ARRAY_REF is a static array of any element type; the dump does not print dimensions.
    return native_kind == "ARRAY" or native_kind in script_kind.split("|")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    show_flags = "--all" in sys.argv[3:]
    funcs = script_functions(sys.argv[1])
    thunks = native_thunks(sys.argv[2])
    findings = defaultdict(list)
    compared = unmatched = 0
    for key, func in sorted(funcs.items()):
        if key not in thunks:
            unmatched += 1
            continue
        compared += 1
        native, where = thunks[key][0]
        script = func["parms"]
        shown = f"{key[0]}.{key[1]}  [{where}]\n      script: {func['line'].split(' :: ', 1)[1]}\n      native: " + \
            ", ".join(("optional " if o else "") + ("out " if r else "") + k for k, o, r in native)
        common = min(len(script), len(native))
        kind_diff = [i for i in range(common) if not kinds_match(script[i][0], native[i][0])]
        if kind_diff:
            findings["KIND"].append(shown + f"\n      differs at parameter(s) {', '.join(str(i + 1) for i in kind_diff)}")
        elif len(script) > len(native):
            findings["SHORT"].append(shown + f"\n      script passes {len(script)}, native reads {len(native)}")
        elif len(native) > len(script):
            findings["LONG"].append(shown + f"\n      script passes {len(script)}, native reads {len(native)}")
        elif any(script[i][1] != native[i][1] or script[i][2] != native[i][2] for i in range(common)):
            findings["FLAGS"].append(shown)
    print(f"{len(funcs)} bound script natives, {compared} matched to a thunk, {unmatched} without a parsed thunk")
    for severity in ("SHORT", "KIND", "LONG") + (("FLAGS",) if show_flags else ()):
        print(f"\n== {severity}: {len(findings[severity])}")
        for item in findings[severity]:
            print("  " + item)
    if not show_flags:
        print(f"\n(FLAGS: {len(findings['FLAGS'])}; --all lists them)")


if __name__ == "__main__":
    main()
