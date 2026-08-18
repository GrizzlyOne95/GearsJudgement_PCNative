"""Emit a UE3 native C++ member block for a class/struct, straight from a script package.

Why this exists: 188 owners differ between Judgment (v845) and Gears 3 (v828), and 25 of them
*reorder* existing members, so every offset in those types shifts and the block must be
regenerated rather than patched. Doing that by hand already produced two silent bugs
(guessing FLinearColor where the real type was FColor; a reordering check that never ran).

Two facts this relies on, both established by validation rather than assumption:
  * native declaration order is the REVERSE of package export order
  * a UProperty's type reference is the LAST INT32 of its payload

Self-check before trusting it on Judgment: generate a Gears 3 owner and diff against the
real header. FPostProcessSettings reproduces 82/82 exactly. If it cannot reproduce a
known-good block, do not trust it.

Known gaps -- these emit `#error UNSUPPORTED_PROPERTY` so the build breaks loudly rather
than silently mis-sizing a member:
  * MapProperty (native TMap<K,V>; AWorldInfo has three)
  * any property whose type reference does not resolve
Cosmetic-only differences from UE3's own output (identical layout, safe to ignore):
  * the optional `struct` keyword inside TArray<> parameters
  * access specifiers (public:/protected:/private:)
  * `_DEPRECATED` / `UDEPRECATED_` renames UHT applies to deprecated members and classes
  * `#if WITH_EDITORONLY_DATA` guards -- note these DO affect layout in builds that
    exclude editor-only data, so a non-editor target needs them re-added by hand

Usage:
    python gen_native_block.py <manifest.json> <package.u> <OwnerName> [--actors Manifest.txt]
"""
import json
import struct
import sys

TYPED = {
    "StructProperty": "struct",
    "ObjectProperty": "object",
    "ComponentProperty": "object",
    "ClassProperty": "class",
    "InterfaceProperty": "interface",
    "ArrayProperty": "inner",
    "ByteProperty": "enum",
}

SIMPLE = {
    "FloatProperty": "FLOAT",
    "IntProperty": "INT",
    "DoubleProperty": "DOUBLE",
    "NameProperty": "FName",
    "StrProperty": "FStringNoInit",
    "DelegateProperty": "FScriptDelegate",
}

# Byte offset of ArrayDim inside a UProperty payload (int32 index 4). Confirmed
# against two knowns: WorldInfo.BookMarks (ArrayDim 10) and
# PostProcessSettings.Bloom_Tint (ArrayDim 1). Ignoring this silently sizes a
# static array like BookMarks[10] as a single member -- 4 bytes instead of 40.
ARRAY_DIM_OFFSET = 16

# A few script structs map to a plain native type rather than an F-prefixed struct.
STRUCT_ALIAS = {"Double": "DOUBLE"}

# Inside a TArray, UE3 uses the ordinary FString, not the NoInit variant.
INNER_OVERRIDE = {"FStringNoInit": "FString"}


def load(manifest, package):
    doc = json.load(open(manifest))
    return doc["exports"], doc["imports"], open(package, "rb").read()


def array_dim(e, blob):
    """Static array length; 1 for ordinary members."""
    off, size = e["serial_offset"], e["serial_size"]
    if size < ARRAY_DIM_OFFSET + 4 or off + size > len(blob):
        return 1
    n = struct.unpack_from("<i", blob, off + ARRAY_DIM_OFFSET)[0]
    return n if 1 <= n <= 4096 else 1


def type_ref(e, blob, exports, imports):
    """Resolve a property's trailing type reference to a name."""
    off, size = e["serial_offset"], e["serial_size"]
    if size < 4 or off + size > len(blob):
        return None
    idx = struct.unpack_from("<i", blob, off + size - 4)[0]
    if idx > 0 and idx - 1 < len(exports):
        return exports[idx - 1]["object_name"]
    if idx < 0 and -idx - 1 < len(imports):
        return imports[-idx - 1]["object_name"]
    return None


def actor_classes(manifest_txt):
    """Names of Actor-derived classes, which UE3 prefixes with A instead of U."""
    import re
    out, depth_of_actor = set(), None
    for line in open(manifest_txt, encoding="utf-8", errors="replace"):
        m = re.match(r"^(\s*)(\d+)\s+(\S+)\s+(\S+)", line)
        if not m:
            continue
        depth, name = int(m.group(2)), m.group(3)
        if name == "Actor":
            depth_of_actor = depth
            out.add(name)
        elif depth_of_actor is not None:
            if depth > depth_of_actor:
                out.add(name)
            else:
                depth_of_actor = None
    return out


# Emitted for anything the generator cannot type with certainty. It is deliberately
# NOT valid C++: a wrong-but-compilable guess (void*, say) would silently mis-size the
# member and shift every offset after it, which is the failure mode this whole tool
# exists to avoid. Better to break the build loudly and fix the case by hand.
UNSUPPORTED = "#error UNSUPPORTED_PROPERTY"


def cpp_type(cls, target, actors, by_path, blob, exports, imports, owner, member):
    if cls == "BoolProperty":
        return None                       # emitted as a bitfield
    if cls in SIMPLE:
        return SIMPLE[cls]
    if cls == "ByteProperty":
        return "BYTE"                     # enum-typed bytes are still BYTE
    if cls == "StructProperty":
        # Bare "FX", never the elaborated "struct FX". Several engine types that look
        # like structs are actually declared with `class` (FVector in UnMath.h is one),
        # and UE3 builds with warnings-as-errors, so a mismatched keyword fails the
        # build with C4099. UE3's own generator does emit "struct FLUTBlender" in one
        # place, but that type is declared earlier in the header anyway, so the bare
        # form is what actually reproduces a compilable block.
        if not target:
            return UNSUPPORTED
        return STRUCT_ALIAS.get(target, "F%s" % target)
    if cls in ("ObjectProperty", "ComponentProperty"):
        if not target:
            return UNSUPPORTED
        return "class %s%s*" % ("A" if target in actors else "U", target)
    if cls == "ClassProperty":
        return "class UClass*"
    if cls == "InterfaceProperty":
        return "FScriptInterface"
    if cls == "ArrayProperty":
        inner = by_path.get("%s.%s.%s" % (owner, member, member))
        if inner is None:
            return "TArrayNoInit<%s>" % UNSUPPORTED
        it = type_ref(inner, blob, exports, imports)
        sub = cpp_type(inner["class_name"], it, actors, by_path, blob, exports, imports,
                       member, member) or "UBOOL"
        return "TArrayNoInit<%s>" % INNER_OVERRIDE.get(sub, sub)
    return "%s /* %s */" % (UNSUPPORTED, cls)


def generate(manifest, package, owner, manifest_txt=None):
    exports, imports, blob = load(manifest, package)
    actors = actor_classes(manifest_txt) if manifest_txt else set()

    by_path = {}
    members = []
    for e in exports:
        path = e.get("object_path") or ""
        parts = path.split(".")
        if len(parts) >= 3 and e["class_name"].endswith("Property"):
            by_path[".".join(parts[-3:])] = e
            if parts[-2] == owner:
                members.append(e)

    members.reverse()                      # export order -> native declaration order

    lines = []
    for e in members:
        cls, name = e["class_name"], (e["object_path"].split("."))[-1]
        if cls == "BoolProperty":
            lines.append("    BITFIELD %s:1;" % name)
            continue
        target = type_ref(e, blob, exports, imports) if cls in TYPED else None
        t = cpp_type(cls, target, actors, by_path, blob, exports, imports, owner, name)
        dim = array_dim(e, blob)
        suffix = "[%d]" % dim if dim > 1 else ""
        lines.append("    %s %s%s;" % (t, name, suffix))
    return lines


if __name__ == "__main__":
    mtxt = None
    args = sys.argv[1:]
    if "--actors" in args:
        i = args.index("--actors")
        mtxt = args[i + 1]
        del args[i:i + 2]
    for line in generate(args[0], args[1], args[2], mtxt):
        print(line)
