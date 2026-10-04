"""ppc_str.py <addr hex>...: print the UTF-16BE (or ASCII) string and nearest public at each VA of the Xbox image."""
import sys, json, bisect
from pathlib import Path
D = Path(r"C:\Games\_judgment-scratch\native-ai-20260930")
img = (D / "release-image.private.bin").read_bytes()
syms = sorted({(s["va"], s["name"]) for s in json.loads((D / "release-publics.json").read_text(encoding="utf-8"))["symbols"]})
vas = [v for v, _ in syms]
for a in sys.argv[1:]:
    va = int(a, 16); o = va - 0x82000000
    w = []
    for i in range(o, o + 400, 2):
        c = int.from_bytes(img[i:i+2], "big")
        if c == 0: break
        w.append(chr(c))
    s = "".join(w)
    asc = img[o:o+80].split(b"\0")[0].decode("latin1")
    i = bisect.bisect_right(vas, va) - 1
    print(f"{va:08x} u16={s!r} ascii={asc!r} near={syms[i][1]}+0x{va-syms[i][0]:x}")
