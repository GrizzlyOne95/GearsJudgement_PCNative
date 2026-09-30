"""Native accessor proof gates using synthetic traces, without game content."""
import unittest

from campaign_graph import GraphError
from validate_campaign_fixture import audit_ai_accessor_layer


def trace():
    text = "command -JUDGAIACCESSORS\n"
    text += "[JUDGAI][PARTIAL] singleton=Transient.AISystem_0 root=1 cdo=0 native-init-pending=ETQSystem,AISpawnManager,AIDebugTool tick-pending=1\n"
    for i, name in enumerate(("Carmine", "Cole", "Paduk"), 1):
        text += (f"[JUDGAI] get-instance caller=Judgment_SP_E2_P.TheWorld:PersistentLevel.GearAI_{name}_0 "
                 f"instance=Transient.AISystem_0 root=1 cdo=0 count={i}\n")
    text += "[JUDGAI] smart-spawner instance=Transient.SmartSpawner_0 class=GearGame.SmartSpawner cdo=0\n"
    return text


class AccessorProofTests(unittest.TestCase):
    def test_real_singleton_keeps_incomplete_native_behavior_visible(self):
        result = audit_ai_accessor_layer(trace())
        self.assertEqual(len(result["companion_callers"]), 3)
        self.assertEqual(result["native_initialization_pending"],
                         ["ETQSystem", "AISpawnManager", "AIDebugTool"])
        self.assertFalse(result["native_tick_implemented"])
        self.assertFalse(result["encounter_verified"])
        self.assertFalse(result["map_cleanup_verified"])

    def test_baseline_does_not_claim_an_ai_layer(self):
        self.assertIsNone(audit_ai_accessor_layer("ordinary loader trace"))

    def test_flag_alone_and_prototype_without_flag_fail(self):
        for text in ("-JUDGAIACCESSORS", trace().replace("-JUDGAIACCESSORS", "")):
            with self.subTest(text=text[:30]), self.assertRaises(GraphError):
                audit_ai_accessor_layer(text)

    def test_omission_or_duplicate_of_partial_disclosure_fails(self):
        line = next(line for line in trace().splitlines(True) if "[PARTIAL]" in line)
        for text in (trace().replace(line, ""), trace() + line):
            with self.assertRaises(GraphError):
                audit_ai_accessor_layer(text)

    def test_wrong_init_disclosure_or_tick_claim_fails(self):
        for old, new in (("native-init-pending=ETQSystem,AISpawnManager,AIDebugTool", "native-init-pending=none"),
                         ("tick-pending=1", "tick-pending=0")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_ai_accessor_layer(trace().replace(old, new))

    def test_cdo_unrooted_or_different_instances_fail(self):
        for old, new in (("root=1", "root=0"), ("cdo=0", "cdo=1"),
                         ("caller=Judgment_SP_E2_P.TheWorld:PersistentLevel.GearAI_Cole_0 instance=Transient.AISystem_0",
                          "caller=Judgment_SP_E2_P.TheWorld:PersistentLevel.GearAI_Cole_0 instance=Transient.AISystem_1")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_ai_accessor_layer(trace().replace(old, new))

    def test_missing_repeated_or_unordered_companion_calls_fail(self):
        original = trace()
        cole = next(line for line in original.splitlines(True) if "GearAI_Cole_0" in line)
        for text in (original.replace(cole, ""), original.replace(cole, cole + cole),
                     original.replace("count=2", "count=4"),
                     original.replace("GearAI_Cole_0", "GearAI_Carmine_0")):
            with self.assertRaises(GraphError):
                audit_ai_accessor_layer(text)

    def test_missing_or_wrong_spawner_fails(self):
        original = trace()
        line = next(line for line in original.splitlines(True) if "smart-spawner" in line)
        for text in (original.replace(line, ""), original + line,
                     original.replace("class=GearGame.SmartSpawner", "class=Core.Object")):
            with self.assertRaises(GraphError):
                audit_ai_accessor_layer(text)

    def test_accessor_fallback_and_possession_warning_fail(self):
        for extra in ("[JUDGBIND][STUB] cls=AISystem#42 func=GetInstance count=1",
                      "[JUDGBIND][STUB] cls=SmartSpawner#43 func=SetInstance count=1",
                      "Function GearGame.GearAI_COGGear:Possess:0046"):
            with self.subTest(extra=extra), self.assertRaises(GraphError):
                audit_ai_accessor_layer(trace() + extra)

    def test_other_fallbacks_remain_allowed_and_disclosed_by_campaign_audit(self):
        extra = "[JUDGBIND][STUB] cls=AIDirector#44 func=Init count=1"
        self.assertEqual(audit_ai_accessor_layer(trace() + extra)["reported_calls"], 3)


if __name__ == "__main__":
    unittest.main()
