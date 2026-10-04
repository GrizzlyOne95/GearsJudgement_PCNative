"""Disassemble original Judgment natives from the local Xbox 360 image by public symbol.

python ppc_native.py <image.bin> <publics.json> <name regex> [--out DIR] [--list]

`image.bin` is the unpacked PE image (file offset == RVA, base 0x82000000) and
`publics.json` the `pdb_native_symbols.py` report (`symbols`: name, va). Every
public whose decorated name matches the regex and lies in a code segment is
disassembled up to the next public symbol. Branch targets and `bl` calls are
annotated with the public symbol at that address, so call structure reads
without a full decompiler. `--list` prints the matches (address, size, name)
and disassembles nothing. Output goes to stdout or to one file per function in
DIR; both the image and the listings are private and stay out of the repo.
Needs `capstone`.
"""
import bisect
import json
import re
import sys
from pathlib import Path

IMAGE_BASE = 0x82000000


def load(image_path, publics_path):
    image = Path(image_path).read_bytes()
    report = json.loads(Path(publics_path).read_text(encoding="utf-8"))
    symbols = sorted({(s["va"], s["name"]) for s in report["symbols"]})
    return image, symbols, [va for va, _ in symbols]


def name_at(symbols, addresses, va):
    i = bisect.bisect_right(addresses, va) - 1
    if i < 0:
        return None
    base, name = symbols[i]
    return name if va == base else f"{name}+0x{va - base:x}"


def disassemble(image, symbols, addresses, va, name):
    from capstone import CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, Cs

    i = bisect.bisect_right(addresses, va)
    end = addresses[i] if i < len(addresses) else va + 0x400
    code = image[va - IMAGE_BASE:end - IMAGE_BASE]
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    lines = [f"; {name}", f"; va=0x{va:08x} size={end - va}"]
    offset = 0
    while offset < len(code):
        decoded = next(md.disasm(code[offset:offset + 4], va + offset), None)
        if decoded is None:
            lines.append(f"{va + offset:08x}  .long 0x{int.from_bytes(code[offset:offset + 4], 'big'):08x}")
        else:
            note = ""
            target = re.search(r"0x(8[0-9a-f]{7})\b", decoded.op_str)
            if target and decoded.mnemonic.startswith("b"):
                t = int(target.group(1), 16)
                label = name_at(symbols, addresses, t)
                if label and not (va <= t < end):
                    note = f"    ; {label}"
            lines.append(f"{decoded.address:08x}  {decoded.mnemonic:<8} {decoded.op_str}{note}")
        offset += 4
    return "\n".join(lines) + "\n"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        sys.exit(__doc__)
    out_dir = None
    if "--out" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out") + 1])
        args = [a for a in args if a != str(out_dir)]
        out_dir.mkdir(parents=True, exist_ok=True)
    image, symbols, addresses = load(args[0], args[1])
    pattern = re.compile(args[2])
    matches = [(va, name) for va, name in symbols if pattern.search(name)]
    for va, name in matches:
        i = bisect.bisect_right(addresses, va)
        size = (addresses[i] if i < len(addresses) else va) - va
        if "--list" in sys.argv:
            print(f"0x{va:08x} {size:6d} {name}")
            continue
        text = disassemble(image, symbols, addresses, va, name)
        if out_dir:
            safe = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")[:120]
            (out_dir / f"{va:08x}-{safe}.txt").write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
    print(f"{len(matches)} symbol(s) matched", file=sys.stderr)


if __name__ == "__main__":
    main()
