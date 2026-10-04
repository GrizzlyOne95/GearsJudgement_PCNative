"""Turn the loader's JUDGDISASM token dump into readable pseudo-UnrealScript.

python judg_decompile.py <dump or log> [function-name filter] [--raw-offsets]

Input is the console output of `JUDGDISASM <Function> [Class]` (or
`JUDGDISASM * <Class>`), straight from a loader log or with the log prefix
removed. Judgment ships no script source; this rebuilds each statement as an
expression tree from the token stream using the token grammar of
Core/Inc/ScriptSerialization.h (v845) and prints one line per statement with
its bytecode offset, so a `[JUDGRUNAWAY] offset=` or ScriptWarning offset can
be read in context. Jumps print as `if (!(cond)) goto 0xNNNN`; no control-flow
structuring is attempted. Operators print infix, optional arguments that were
omitted print as nothing. A reading aid, not a compiler: output is never fed
back into the build.
"""
import re
import sys

TOKEN = re.compile(r"^([0-9A-F]{4}): *(?:native (\d+) (\S+)|(\w+))$")
PREFIX = re.compile(r"^(?:\[\d+\.\d+\] Log: )?\[JUDGDISASM\] ?|^D ")
LEAF = set("""LocalVariable InstanceVariable DefaultVariable LocalOutVariable NativeParm Jump Stop Nothing EndOfScript
IntZero IntOne True False NoObject Self EmptyParmValue EndFunctionParms IteratorPop IteratorNext EmptyDelegate IntConst
FloatConst StringConst UnicodeStringConst ObjectConst NameConst RotationConst VectorConst ByteConst IntConstByte
LabelTable EndParmValue DelegateProperty InstanceDelegate JumpIfFilterEditorOnly DebugInfo ReturnNothing""".split())
CHILDREN = {"PrimitiveCast": 1, "InterfaceCast": 1, "Let": 2, "LetBool": 2, "LetDelegate": 2, "BoolVariable": 1,
            "InterfaceContext": 1, "EatReturnValue": 1, "Return": 1, "ClassContext": 2, "Context": 2,
            "DynArrayIterator": 3, "ArrayElement": 2, "DynArrayElement": 2, "DynArrayLength": 1, "DynArrayAdd": 3,
            "DynArrayInsert": 4, "DynArrayRemove": 4, "DynArrayAddItem": 3, "DynArrayRemoveItem": 3,
            "DynArrayInsertItem": 4, "DynArrayFind": 3, "DynArrayFindStruct": 4, "DynArraySort": 3, "Conditional": 3,
            "New": 4, "MetaCast": 1, "DynamicCast": 1, "JumpIfNot": 1, "Iterator": 1, "Switch": 1, "Assert": 1,
            "GotoLabel": 1, "Skip": 1, "DefaultParmValue": 1, "StructCmpEq": 2, "StructCmpNe": 2, "StructMember": 1}
CALLS = {"FinalFunction", "VirtualFunction", "GlobalFunction", "DelegateFunction", "EqualEqual_DelDel",
         "NotEqual_DelDel", "EqualEqual_DelFunc", "NotEqual_DelFunc", "ExtendedNative"}
INFIX = {"AndAnd": "&&", "OrOr": "||", "XorXor": "^^", "EqualEqual": "==", "NotEqual": "!=", "Less": "<", "Greater": ">",
         "LessEqual": "<=", "GreaterEqual": ">=", "Add": "+", "Subtract": "-", "Multiply": "*", "Divide": "/",
         "Percent": "%", "Concat": "$", "At": "@", "AddEqual": "+=", "SubtractEqual": "-=", "MultiplyEqual": "*=",
         "DivideEqual": "/=", "ConcatEqual": "$=", "AtEqual": "@=", "And": "&", "Or": "|", "ComplementEqual": "~=",
         "LessLess": "<<", "GreaterGreater": ">>", "Dot": "dot", "Cross": "cross"}
PREFIX_OPS = {"Not_PreBool": "!", "Subtract_PreInt": "-", "Subtract_PreFloat": "-", "Subtract_PreVector": "-",
              "Complement_PreInt": "~"}


class Node:
    def __init__(self, offset, name, native=None):
        self.offset, self.name, self.native = offset, name, native
        self.operands, self.children = [], []


def tokens(lines):
    """Token nodes in stream order with their operand lines; opcode and look-ahead bytes dropped."""
    out, pending, after_end = [], [], False
    for line in lines:
        m = TOKEN.match(line)
        if m:
            if pending and pending[-1][0] == "byte":
                pending.pop()                      # the opcode byte of this token
            if out:
                out[-1].operands.extend(pending)
            pending = []
            node = Node(int(m.group(1), 16), m.group(3) or m.group(4), m.group(2))
            out.append(node)
            after_end = node.name == "EndFunctionParms"
            continue
        text = line.strip()
        kind, _, rest = text.partition(" ")
        if kind == "native" and out and out[-1].name == "ExtendedNative":
            out[-1].native, out[-1].name = rest.split(" ")[0], rest.split(" ", 1)[1]
            after_end = False
            continue
        if kind.isdigit() and rest == "bytes":
            kind, rest = "bytes", kind
        if after_end and kind == "byte":
            after_end = False                      # debug-info look-ahead after a call's parameter list
            continue
        after_end = False
        if kind in ("byte", "word", "int", "obj", "name", "bytes"):
            pending.append((kind, rest))
    if out:
        out[-1].operands.extend(pending)
    return out


def build(stream, pos):
    node = stream[pos]
    pos += 1
    if node.native is not None or node.name in CALLS:
        while pos < len(stream):
            child, pos = build(stream, pos)
            node.children.append(child)
            if child.name == "EndFunctionParms":
                break
    elif node.name == "Case":
        if not node.operands or not node.operands[0][1].startswith("FFFF"):
            child, pos = build(stream, pos)
            node.children.append(child)
    elif node.name not in LEAF:
        for _ in range(CHILDREN.get(node.name, 0)):
            if pos >= len(stream):
                break
            child, pos = build(stream, pos)
            node.children.append(child)
    return node, pos


def short(path):
    path = path.split(" ", 1)[-1]
    return re.split(r"[.:]", path)[-1]


def number(operand):
    return int(re.search(r"\((-?\d+)\)", operand[1]).group(1)) if "(" in operand[1] else operand[1]


def render(n):
    name, ops, kids = n.name, n.operands, n.children
    args = [k for k in kids if k.name != "EndFunctionParms"]
    if n.native is not None or name in CALLS:
        if name in PREFIX_OPS and len(args) == 1:
            return f"{PREFIX_OPS[name]}{render(args[0])}"
        base = name.split("_")[0]
        if n.native is not None and base in INFIX and len(args) == 2:
            return f"({render(args[0])} {INFIX[base]} {render(args[1])})"
        if n.native is not None and base in ("AddAdd", "SubtractSubtract") and len(args) == 1:
            sign = "++" if base == "AddAdd" else "--"
            return f"{sign}{render(args[0])}" if "Pre" in name else f"{render(args[0])}{sign}"
        if name in ("FinalFunction",):
            callee = short(next(o[1] for o in ops if o[0] == "obj"))
        elif name in ("VirtualFunction", "GlobalFunction", "DelegateFunction"):
            callee = next((o[1] for o in ops if o[0] == "name"), "?")
        else:
            callee = name
        return f"{callee}({', '.join(render(a) for a in args)})"
    if name in ("LocalVariable", "InstanceVariable", "LocalOutVariable", "NativeParm"):
        return short(ops[0][1])
    if name == "DefaultVariable":
        return "default." + short(ops[0][1])
    if name in ("Let", "LetBool", "LetDelegate"):
        return f"{render(kids[0])} = {render(kids[1])}"
    if name in ("Context", "ClassContext"):
        return f"{render(kids[0])}.{render(kids[1])}"
    if name == "StructMember":
        return f"{render(kids[0])}.{short(ops[0][1])}"
    if name in ("BoolVariable", "InterfaceContext", "Skip", "EatReturnValue"):
        return render(kids[0])
    if name in ("DynamicCast", "MetaCast", "InterfaceCast"):
        return f"{short(ops[0][1])}({render(kids[0])})"
    if name == "PrimitiveCast":
        return f"cast{number(ops[0])}({render(kids[0])})"
    if name in ("ArrayElement", "DynArrayElement"):
        return f"{render(kids[1])}[{render(kids[0])}]"
    if name == "DynArrayLength":
        return f"{render(kids[0])}.Length"
    if name.startswith("DynArray"):
        return f"{render(args[0])}.{name[8:]}({', '.join(render(a) for a in args[1:])})"
    if name == "JumpIfNot":
        return f"if (!({render(kids[0])})) goto 0x{ops[0][1].split(' ')[0]}"
    if name == "Jump":
        return f"goto 0x{ops[0][1].split(' ')[0]}"
    if name == "Return":
        return f"return {render(kids[0])}".rstrip()
    if name == "Iterator":
        # The end offset follows the iterator call, so it was filed under the call's last token.
        last = kids[0]
        while last.children:
            last = last.children[-1]
        end = next((o[1].split(" ")[0] for o in reversed(last.operands) if o[0] == "word"), "?")
        return f"foreach {render(kids[0])}  (end 0x{end})"
    if name == "Switch":
        return f"switch ({render(kids[0])})"
    if name == "Case":
        return f"case {render(kids[0])}:" if kids else "default:"
    if name == "Conditional":
        return f"({render(kids[0])} ? {render(kids[1])} : {render(kids[2])})"
    if name == "New":
        return f"new({', '.join(render(k) for k in kids[:3])}) {render(kids[3])}" if len(kids) == 4 else "new(?)"
    if name in ("StructCmpEq", "StructCmpNe"):
        return f"({render(kids[0])} {'==' if name.endswith('Eq') else '!='} {render(kids[1])})"
    if name == "IntConst":
        return ops[0][1].split(" ")[0]
    if name == "FloatConst":
        return ops[0][1].split("float ")[-1].rstrip("0").rstrip(".") or "0"
    if name in ("ByteConst", "IntConstByte"):
        return str(number(ops[0]))
    if name == "StringConst":
        return '"' + "".join(chr(number(o)) for o in ops if o[0] == "byte" and number(o)) + '"'
    if name == "UnicodeStringConst":
        return '"' + "".join(chr(number(o)) for o in ops if o[0] == "word" and number(o)) + '"'
    if name == "NameConst":
        return f"'{ops[0][1]}'"
    if name == "ObjectConst":
        kind, _, path = ops[0][1].partition(" ")
        return f"{kind}'{short(path)}'" if path else "None"
    if name == "VectorConst":
        return "vect(" + ",".join(o[1].split("float ")[-1].rstrip("0").rstrip(".") or "0" for o in ops[:3]) + ")"
    if name == "RotationConst":
        return "rot(" + ",".join(o[1].split(" ")[0] for o in ops[:3]) + ")"
    if name in ("DelegateProperty", "InstanceDelegate"):
        return next((o[1] for o in ops if o[0] == "name"), "?")
    if name == "DefaultParmValue":
        return f"/*default*/ {render(kids[0])}"
    simple = {"IntZero": "0", "IntOne": "1", "True": "true", "False": "false", "NoObject": "None", "Self": "self",
              "EmptyParmValue": "", "EmptyDelegate": "None", "Nothing": "", "EndOfScript": "", "IteratorPop": "end foreach",
              "IteratorNext": "continue foreach", "Stop": "stop", "ReturnNothing": "", "EndFunctionParms": ")?"}
    if name in simple:
        return simple[name]
    return f"{name}({', '.join(render(k) for k in kids)})"


def decompile(lines):
    stream = tokens(lines)
    pos, out = 0, []
    while pos < len(stream):
        node, pos = build(stream, pos)
        try:
            text = render(node)
        except (IndexError, StopIteration, AttributeError) as error:
            text = f"?? {node.name}: {error!r}"   # one odd statement must not hide the rest
        if text:
            out.append(f"  {node.offset:04X}  {text}")
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    want = args[1].lower() if len(args) > 1 else ""
    current, header = None, ""
    for raw in open(args[0], encoding="utf-8", errors="replace"):
        line = PREFIX.sub("", raw.rstrip("\n").lstrip("﻿"))
        if line.startswith("begin "):
            header, current = line[6:], []
        elif line.startswith("end ") and current is not None:
            if want in header.lower():
                print(header)
                try:
                    print("\n".join(decompile(current)))
                except Exception as error:      # a grammar slip must not hide the other functions
                    print(f"  !! could not rebuild: {error!r}")
                print()
            current = None
        elif current is not None:
            current.append(line)


if __name__ == "__main__":
    main()
