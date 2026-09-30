"""Read and compare cooked Kismet graphs without executing or rewriting packages.

The audit covers sequence membership, input/output/event/variable connectors,
remote-event names, objectives and startup streaming settings. It does not infer
omitted class defaults or claim that a completed action performed its gameplay
side effects. Native trailers are accepted only for Interp's empty saved-transform
map. Original map data and detailed reports belong in private scratch storage.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct


class GraphError(ValueError):
    pass


ARRAY_TYPES = {
    "SequenceObjects": "object", "LinkedVariables": "object", "LinkedEvents": "object",
    "InterpGroups": "object",
    "PrestreamTexturesLocations": "object", "FallbackTeleportActors": "object",
    "TeleportVolumes": "object", "LevelNames": "name",
    "InputLinks": "SeqOpInputLink", "OutputLinks": "SeqOpOutputLink",
    "VariableLinks": "SeqVarLink", "EventLinks": "SeqEventLink",
    "Links": "SeqOpOutputInputLink", "Levels": "LevelStreamingNameCombo",
    "SubLevelsToLoad": "LevelRecord",
}
FIELDS = set(ARRAY_TYPES) | {
    "ParentSequence", "EventName", "ConsoleEventName", "ObjComment", "ObjName",
    "ObjectiveName", "ObjectiveDesc", "ObjValue", "VarName", "FindVarName",
    "ExpectedType", "Duration", "FadeTime", "FadeOpacity", "bEnabled",
    "bDisabled", "bPlayerOnly", "MaxTriggerCount", "ReTriggerDelay",
    "bAllPlayers", "PlayerIdx", "bShowInList", "bNotifyPlayer", "bShowAlways",
    "bUnloadAllOtherLevels", "AutoCloseCount", "CurrentCloseCount", "InterpLength",
}


class GraphReader:
    def __init__(self, blob, manifest):
        self.blob, self.manifest = blob, manifest
        order = manifest.get("byte_order")
        if order not in ("big", "little"):
            raise GraphError("unknown package byte order")
        self.endian = ">" if order == "big" else "<"
        self.names = [row["name"] for row in manifest["names"]]
        self.exports, self.imports = manifest["exports"], manifest["imports"]

    def read(self, fmt, pos, end):
        size = struct.calcsize("=" + fmt)
        if pos < 0 or pos + size > end or end > len(self.blob):
            raise GraphError("field exceeds its serialized boundary")
        return struct.unpack_from(self.endian + fmt, self.blob, pos), pos + size

    def fname(self, pos, end):
        (index, number), pos = self.read("2i", pos, end)
        if not 0 <= index < len(self.names) or number < 0:
            raise GraphError("invalid FName")
        return (self.names[index] if number == 0 else [self.names[index], number]), pos

    def reference(self, index):
        if index == 0:
            return None
        rows, slot = (self.exports, index - 1) if index > 0 else (self.imports, -index - 1)
        if not 0 <= slot < len(rows):
            raise GraphError("object reference outside import/export tables")
        entry = rows[slot]
        parts, seen, outer = [entry["object_name"]], {index}, entry["outer_index"]
        while outer:
            if outer in seen:
                raise GraphError("cyclic resource outer chain")
            seen.add(outer)
            parents, slot = (self.exports, outer - 1) if outer > 0 else (self.imports, -outer - 1)
            if not 0 <= slot < len(parents):
                raise GraphError("invalid outer reference")
            parent = parents[slot]
            parts.append(parent["object_name"])
            outer = parent["outer_index"]
        return {"index": index, "path": ".".join(reversed(parts)), "class": entry["class_name"]}

    def string(self, pos, end):
        (count,), pos = self.read("i", pos, end)
        size = abs(count) * (2 if count < 0 else 1)
        if pos + size != end:
            raise GraphError("FString length does not match tag")
        if count == 0:
            return ""
        raw = self.blob[pos:end]
        if count < 0:
            if raw[-2:] != b"\0\0":
                raise GraphError("unterminated wide FString")
            return raw[:-2].decode("utf-16-be" if self.endian == ">" else "utf-16-le")
        if raw[-1:] != b"\0":
            raise GraphError("unterminated FString")
        return raw[:-1].decode("latin-1")

    def value(self, name, kind, extra, pos, end, depth):
        size = end - pos
        if kind in ("ObjectProperty", "ComponentProperty", "ClassProperty", "InterfaceProperty"):
            if size != 4:
                raise GraphError("unexpected object property width")
            return self.reference(self.read("i", pos, end)[0][0])
        if kind == "NameProperty" or (kind == "ByteProperty" and extra != "None" and size == 8):
            value, stop = self.fname(pos, end)
            if stop != end:
                raise GraphError("unexpected name property width")
            return value
        if kind in ("IntProperty", "FloatProperty"):
            if size != 4:
                raise GraphError("unexpected scalar property width")
            value = self.read("i" if kind == "IntProperty" else "f", pos, end)[0][0]
            if isinstance(value, float) and not math.isfinite(value):
                raise GraphError("non-finite graph setting")
            return value
        if kind == "ByteProperty" and size == 1:
            return self.blob[pos]
        if kind == "StrProperty":
            return self.string(pos, end)
        if kind == "ArrayProperty":
            element = ARRAY_TYPES.get(name)
            if element is None:
                raise GraphError(f"unmodelled graph array: {name}")
            (count,), pos = self.read("i", pos, end)
            minimum = 4 if element == "object" else 8
            if count < 0 or count > (end - pos) // minimum:
                raise GraphError("array count exceeds property boundary")
            values = []
            for _ in range(count):
                if element == "object":
                    (ref,), pos = self.read("i", pos, end)
                    values.append(self.reference(ref))
                elif element == "name":
                    value, pos = self.fname(pos, end)
                    values.append(value)
                else:
                    value, pos = self.tags(pos, end, depth + 1, selected=False)
                    values.append(value)
            if pos != end:
                raise GraphError("array does not end at property boundary")
            return values
        raise GraphError(f"unmodelled graph value: {name} {kind} {extra}")

    def tags(self, pos, end, depth=0, selected=True):
        if depth > 8:
            raise GraphError("tag recursion limit")
        result = {}
        while pos < end:
            name, pos = self.fname(pos, end)
            if name == "None":
                return result, pos
            if not isinstance(name, str):
                raise GraphError("instanced property name")
            kind, pos = self.fname(pos, end)
            if not isinstance(kind, str) or not kind.endswith("Property"):
                raise GraphError("invalid property type")
            (size, array_index), pos = self.read("2i", pos, end)
            if size < 0 or array_index < 0:
                raise GraphError("negative property size/index")
            extra, boolean = None, None
            if kind in ("StructProperty", "ByteProperty"):
                extra, pos = self.fname(pos, end)
            elif kind == "BoolProperty":
                (boolean,), pos = self.read("B", pos, end)
                if boolean not in (0, 1) or size != 0:
                    raise GraphError("invalid tagged boolean")
            if pos + size > end:
                raise GraphError("tag exceeds object boundary")
            if not selected or name in FIELDS:
                key = name if array_index == 0 else f"{name}[{array_index}]"
                if key in result:
                    raise GraphError("duplicate graph property")
                value = bool(boolean) if kind == "BoolProperty" else self.value(name, kind, extra, pos, pos + size, depth)
                result[key] = {"type": kind, "value": value}
            pos += size
        raise GraphError("missing None tag terminator")

    def graph(self):
        nodes = {}
        for row in self.exports:
            if not row["class_name"].startswith(("Seq", "GearSeq")) and row["class_name"] != "InterpData":
                continue
            start, end = row["serial_offset"], row["serial_offset"] + row["serial_size"]
            self.read("i", start, end)  # SequenceObject's UObject NetIndex.
            properties, stop = self.tags(start + 4, end)
            if stop != end:
                # USeqAct_Interp::Serialize writes SavedActorTransforms. Only
                # the measured empty TMap case is covered by this graph audit.
                if row["class_name"] != "SeqAct_Interp" or end - stop != 4 or self.read("i", stop, end)[0] != (0,):
                    raise GraphError("unmodelled sequence native trailer")
            ref = self.reference(row["package_index"])
            nodes[row["package_index"]] = {"path": ref["path"], "class": row["class_name"], "properties": properties}
        if not nodes:
            raise GraphError("package contains no sequence objects")
        self.validate_connectors(nodes)
        return nodes

    @staticmethod
    def validate_connectors(nodes):
        for node in nodes.values():
            p = node["properties"]
            for member in p.get("SequenceObjects", {}).get("value", []):
                if member is None or member["index"] not in nodes:
                    raise GraphError("sequence member is not a local graph object")
            parent = p.get("ParentSequence", {}).get("value")
            if parent and (parent["index"] not in nodes or nodes[parent["index"]]["class"] != "Sequence"):
                raise GraphError("parent is not a local Sequence")
            for output in p.get("OutputLinks", {}).get("value", []):
                for link in output.get("Links", {}).get("value", []):
                    target = link.get("LinkedOp", {}).get("value")
                    if target is None:
                        continue  # Persisted disconnected connector.
                    if target["index"] not in nodes:
                        raise GraphError("output target is not a local graph object")
                    index = link.get("InputLinkIdx", {}).get("value", 0)
                    inputs = nodes[target["index"]]["properties"].get("InputLinks")
                    if index < 0 or (inputs is not None and index >= len(inputs["value"])):
                        raise GraphError("output targets an invalid input connector")


def compare(source, converted, source_manifest, converted_manifest):
    original = GraphReader(source, source_manifest).graph()
    emitted = GraphReader(converted, converted_manifest).graph()
    if original != emitted:
        differing = [i for i in original.keys() | emitted.keys() if original.get(i) != emitted.get(i)]
        raise GraphError(f"converted graph differs at package indices: {differing[:12]}")
    classes = Counter(node["class"] for node in original.values())
    output_links = variables = edges = 0
    for node in original.values():
        properties = node["properties"]
        for output in properties.get("OutputLinks", {}).get("value", []):
            output_links += 1
            edges += sum(bool(link.get("LinkedOp", {}).get("value")) for link in output.get("Links", {}).get("value", []))
        for variable in properties.get("VariableLinks", {}).get("value", []):
            variables += sum(bool(ref) for ref in variable.get("LinkedVariables", {}).get("value", []))
    return {
        "sequence_objects": len(original), "classes": dict(sorted(classes.items())),
        "output_connectors": output_links, "connected_outputs": edges,
        "linked_variables": variables, "source_sha256": hashlib.sha256(source).hexdigest(),
        "converted_sha256": hashlib.sha256(converted).hexdigest(),
        "graph_sha256": hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest(),
        "graph": original,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("converted", type=Path)
    parser.add_argument("converted_manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise GraphError("refusing to overwrite retained evidence")
    report = compare(args.source.read_bytes(), args.converted.read_bytes(),
                     json.loads(args.source_manifest.read_text(encoding="utf-8")),
                     json.loads(args.converted_manifest.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "graph"}, indent=2))


if __name__ == "__main__":
    main()
