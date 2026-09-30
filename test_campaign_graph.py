"""Synthetic connector and boundary tests; no game package data is embedded."""
import copy
import struct
import unittest

from campaign_graph import GraphError, GraphReader, compare
from validate_campaign_fixture import audit_log


NAMES = ["None", "SequenceObjects", "ArrayProperty", "ParentSequence", "ObjectProperty",
         "OutputLinks", "InputLinks", "Links", "LinkedOp", "InputLinkIdx", "IntProperty",
         "LinkDesc", "StrProperty", "EventName", "NameProperty", "Begin", "ObjectiveName",
         "bEnabled", "BoolProperty", "FloatProperty", "Duration"]


class Fixture:
    def __init__(self, endian, target=3, input_index=0, event_number=0):
        self.endian = endian
        link = self.tags(self.tag("LinkedOp", "ObjectProperty", self.pack("i", target)),
                         self.tag("InputLinkIdx", "IntProperty", self.pack("i", input_index)))
        output = self.tags(self.tag("LinkDesc", "StrProperty", self.string("Out")),
                           self.tag("Links", "ArrayProperty", self.pack("i", 1) + link))
        input_link = self.tags(self.tag("LinkDesc", "StrProperty", self.string("Add")))
        members = self.tag("SequenceObjects", "ArrayProperty", self.pack("3i", 2, 2, 3))
        parent = self.tag("ParentSequence", "ObjectProperty", self.pack("i", 1))
        event = self.tag("EventName", "NameProperty", self.name("Begin", event_number))
        payloads = [self.pack("i", 0) + self.tags(members),
                    self.pack("i", 0) + self.tags(parent, event, self.tag("OutputLinks", "ArrayProperty", self.pack("i", 1) + output)),
                    self.pack("i", 0) + self.tags(parent, self.tag("InputLinks", "ArrayProperty", self.pack("i", 1) + input_link))]
        exports, parts, offset = [], [], 0
        for index, (name, cls, payload) in enumerate(zip(
                ["Main", "Load", "Objective"], ["Sequence", "SeqEvent_LevelLoaded", "SeqAct_ManageObjectives"], payloads), 1):
            exports.append({"package_index": index, "class_name": cls, "object_name": name,
                            "outer_index": 0 if index == 1 else 1,
                            "serial_offset": offset, "serial_size": len(payload)})
            parts.append(payload)
            offset += len(payload)
        self.blob = b"".join(parts)
        self.manifest = {"byte_order": "big" if endian == ">" else "little",
                         "names": [{"name": name} for name in NAMES], "exports": exports, "imports": []}

    def pack(self, fmt, *values):
        return struct.pack(self.endian + fmt, *values)

    def name(self, name, number=0):
        return self.pack("2i", NAMES.index(name), number)

    def tag(self, name, kind, value):
        return self.name(name) + self.name(kind) + self.pack("2i", len(value), 0) + value

    def tags(self, *tags):
        return b"".join(tags) + self.name("None")

    def string(self, text):
        raw = text.encode("latin-1") + b"\0"
        return self.pack("i", len(raw)) + raw

    def reader(self):
        return GraphReader(self.blob, self.manifest)


class CampaignGraphTests(unittest.TestCase):
    def test_big_and_little_graphs_match(self):
        a, b = Fixture(">"), Fixture("<")
        report = compare(a.blob, b.blob, a.manifest, b.manifest)
        self.assertEqual(report["sequence_objects"], 3)
        self.assertEqual(report["connected_outputs"], 1)

    def test_in_range_wrong_target_is_detected(self):
        a, b = Fixture(">"), Fixture("<", target=2)
        with self.assertRaisesRegex(GraphError, "converted graph differs"):
            compare(a.blob, b.blob, a.manifest, b.manifest)

    def test_invalid_input_connector_is_detected(self):
        with self.assertRaisesRegex(GraphError, "invalid input connector"):
            Fixture("<", input_index=1).reader().graph()

    def test_negative_input_connector_is_detected(self):
        with self.assertRaises(GraphError):
            Fixture("<", input_index=-1).reader().graph()

    def test_out_of_range_object_is_detected(self):
        with self.assertRaisesRegex(GraphError, "outside import/export"):
            Fixture(">", target=4).reader().graph()

    def test_instanced_remote_event_names_are_preserved(self):
        a, b = Fixture(">", event_number=2), Fixture("<", event_number=2)
        self.assertEqual(a.reader().graph()[2]["properties"]["EventName"]["value"], ["Begin", 2])
        self.assertEqual(a.reader().graph(), b.reader().graph())
        changed = Fixture("<", event_number=0)
        with self.assertRaises(GraphError):
            compare(a.blob, changed.blob, a.manifest, changed.manifest)

    def test_array_count_cannot_escape_tag_boundary(self):
        fixture = Fixture("<")
        raw = bytearray(fixture.blob)
        struct.pack_into("<i", raw, 28, 999)
        with self.assertRaisesRegex(GraphError, "array count"):
            GraphReader(raw, fixture.manifest).graph()

    def test_native_trailer_is_rejected(self):
        fixture = Fixture("<")
        fixture.manifest["exports"][-1]["serial_size"] += 4
        with self.assertRaisesRegex(GraphError, "native trailer"):
            GraphReader(fixture.blob + b"\0" * 4, fixture.manifest).graph()

    def test_outer_cycles_are_rejected(self):
        fixture = Fixture("<")
        fixture.manifest["exports"][0]["outer_index"] = 2
        with self.assertRaisesRegex(GraphError, "cyclic"):
            fixture.reader().graph()

    def test_parent_must_be_a_sequence(self):
        fixture = Fixture("<")
        manifest = copy.deepcopy(fixture.manifest)
        manifest["exports"][0]["class_name"] = "SeqVar_Object"
        with self.assertRaisesRegex(GraphError, "parent"):
            GraphReader(fixture.blob, manifest).graph()

    def test_unicode_strings_match_across_byte_orders(self):
        for endian, encoding in [("<", "utf-16-le"), (">", "utf-16-be")]:
            fixture = Fixture(endian)
            value = fixture.pack("i", -3) + "A\u03a9\0".encode(encoding)
            reader = GraphReader(value, fixture.manifest)
            self.assertEqual(reader.string(0, len(value)), "A\u03a9")

    def test_unterminated_string_is_rejected(self):
        fixture = Fixture("<")
        raw = fixture.pack("i", 2) + b"AB"
        with self.assertRaisesRegex(GraphError, "unterminated"):
            GraphReader(raw, fixture.manifest).string(0, len(raw))

    def test_truncated_field_is_rejected(self):
        fixture = Fixture("<")
        with self.assertRaisesRegex(GraphError, "boundary"):
            GraphReader(fixture.blob[:-1], fixture.manifest).graph()

    def test_invalid_name_is_rejected(self):
        fixture = Fixture("<")
        raw = bytearray(fixture.blob)
        struct.pack_into("<i", raw, 4, len(NAMES))
        with self.assertRaisesRegex(GraphError, "FName"):
            GraphReader(raw, fixture.manifest).graph()

    def test_empty_trace_does_not_pass(self):
        with self.assertRaises(GraphError):
            audit_log("", {})

    def test_native_framing_alone_does_not_prove_campaign(self):
        text = "-JUDGSEQUENCETRACE\n[JUDGPRELOAD] leave exp=1 obj=World consumed=8 size=8\n"
        with self.assertRaisesRegex(GraphError, "no executed"):
            audit_log(text, {})

    def test_truncated_execution_trace_is_rejected(self):
        with self.assertRaisesRegex(GraphError, "truncated"):
            audit_log("-JUDGSEQUENCETRACE\n[JUDGSEQ] trace-limit records=10000", {})

    def test_size_mismatch_rejects_campaign_proof(self):
        text = "-JUDGSEQUENCETRACE\n[JUDGPRELOAD] leave exp=1 obj=World consumed=8 size=9\n"
        with self.assertRaisesRegex(GraphError, "mismatched"):
            audit_log(text, {})


def runtime_fixture():
    root = "TheWorld.PersistentLevel.Main_Sequence."
    paths = ["Level_Startup.SeqEvent_LevelLoaded_1", "Level_Startup.SeqAct_MultiLevelStreaming_0",
             "Level_Startup.SeqAct_WaitForLevelsVisible_8", "Level_Startup.SeqAct_Checkpoint_5",
             "Level_Startup.SeqAct_ToggleCinematicMode_5", "Level_Startup.SeqAct_CameraFade_5",
             "Level_Startup.SeqAct_DisplayChapterTitle_0", "MISSION_OBJECTIVES.SeqAct_ManageObjectives_1"]
    graph, lines = {}, ["-JUDGSEQUENCETRACE", "[JUDGPRELOAD] leave exp=1 obj=World consumed=8 size=8"]
    for index, path in enumerate(paths, 1):
        cls = path.rsplit(".", 1)[1].rsplit("_", 1)[0]
        node = {"path": root + path, "class": cls, "properties": {}}
        if path.startswith("MISSION_OBJECTIVES"):
            node["properties"]["ObjectiveName"] = {"type": "NameProperty", "value": "test-objective"}
        graph[index] = node
        runtime_path = "Judgment_SP_E2_P." + node["path"].replace("TheWorld.", "TheWorld:")
        lines.append(f"[JUDGSEQ] complete op={runtime_path} class={cls} count=1 active=0 latent=0 inputs=0 outputs=0")
    for index, number in enumerate([0, 1, 6, 7], 20):
        path = root + "Spawn_COG_Squad.SeqAct_AIFactory_" + str(number)
        graph[index] = {"path": path, "class": "SeqAct_AIFactory", "properties": {
            "OutputLinks": {"type": "ArrayProperty", "value": [{
                "LinkDesc": {"type": "StrProperty", "value": "All Spawned"},
                "Links": {"type": "ArrayProperty", "value": [{"LinkedOp": {"type": "ObjectProperty", "value": None}}]},
            }]}}}
        runtime_path = "Judgment_SP_E2_P." + path.replace("TheWorld.", "TheWorld:")
        lines.append(f"[JUDGSEQ] activate op={runtime_path} class=SeqAct_AIFactory count=1 active=1 latent=1 inputs=0 outputs=1")
        lines.append(f'[JUDGSEQ] output op={runtime_path} index=0 desc="All Spawned" targets=1')
    lines += ["[JUDGSEQ] objective-state op=Fixture.SeqAct_ManageObjectives_1 manager=FixtureManager readable=1 count=1",
              "[JUDGSEQ] objective-entry index=0 name=test-objective completed=0 failed=0",
              "[0071.0] Log: [JUDGPROTO] tick-end serial=100 game-time=44.0 levels=7"]
    return "\n".join(lines), {"SP_E2_P": graph}


class CampaignMilestoneTests(unittest.TestCase):
    def test_startup_and_real_objective_state_pass(self):
        text, graphs = runtime_fixture()
        report = audit_log(text, graphs)
        self.assertEqual(report["active_objective"], "test-objective")
        self.assertFalse(report["checkpoint_save_restore_verified"])
        self.assertFalse(report["encounter_verified"])

    def test_objective_action_without_objective_state_fails(self):
        text, graphs = runtime_fixture()
        text = "\n".join(line for line in text.splitlines() if "objective-state" not in line)
        with self.assertRaisesRegex(GraphError, "objective is absent"):
            audit_log(text, graphs)

    def test_unreadable_objective_manager_fails(self):
        text, graphs = runtime_fixture()
        with self.assertRaises(GraphError):
            audit_log(text.replace("readable=1", "readable=0"), graphs)

    def test_wrong_objective_name_fails(self):
        text, graphs = runtime_fixture()
        with self.assertRaises(GraphError):
            audit_log(text.replace("name=test-objective", "name=other-objective"), graphs)

    def test_failed_objective_does_not_pass(self):
        text, graphs = runtime_fixture()
        with self.assertRaises(GraphError):
            audit_log(text.replace("failed=0", "failed=1"), graphs)

    def test_missing_checkpoint_completion_fails(self):
        text, graphs = runtime_fixture()
        text = "\n".join(line for line in text.splitlines() if "SeqAct_Checkpoint_5" not in line)
        with self.assertRaisesRegex(GraphError, "milestone missing"):
            audit_log(text, graphs)

    def test_wrong_output_description_fails(self):
        text, graphs = runtime_fixture()
        with self.assertRaisesRegex(GraphError, "output differs"):
            audit_log(text.replace('desc="All Spawned"', 'desc="Aborted"', 1), graphs)

    def test_incorrect_runtime_class_fails(self):
        text, graphs = runtime_fixture()
        with self.assertRaisesRegex(GraphError, "class differs"):
            audit_log(text.replace("class=SeqAct_Checkpoint", "class=SeqAct_Delay"), graphs)

    def test_world_without_streamed_levels_fails(self):
        text, graphs = runtime_fixture()
        with self.assertRaisesRegex(GraphError, "seven levels"):
            audit_log(text.replace("levels=7", "levels=1"), graphs)

    def test_native_fallbacks_are_disclosed(self):
        text, graphs = runtime_fixture()
        text += "\n[JUDGBIND][STUB] cls=AISystem#42 func=GetInstance obj=Default__AISystem#43 ret=object count=1"
        text += "\n[JUDGBIND][STUB] cls=AISystem#42 func=GetInstance count=10"
        self.assertEqual(audit_log(text, graphs)["native_fallbacks"], {"AISystem.GetInstance": 10})


if __name__ == "__main__":
    unittest.main()
