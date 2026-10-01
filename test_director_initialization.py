"""Synthetic proof gates for director initialization, not pacing or encounters."""
import unittest

from campaign_graph import GraphError
from validate_campaign_fixture import audit_director_initialization


DIRECTOR = "Transient.AIDirector_0"
FSM = DIRECTOR + ":FSM_AIDirector_0"


def trace():
    names = ("BuildUp", "PeakSustain", "PeakFade", "Relax")
    text = "command -JUDGAIDIRECTORINIT\n"
    for i, name in enumerate(names):
        text += (f"[JUDGDIRECTOR] state fsm={FSM} index={i} name={name} enter={name}OnEnter "
                 f"enter-bound=1 leave={name}OnLeave leave-bound=1 transitions=1\n")
        text += (f"[JUDGDIRECTOR] transition fsm={FSM} state={i} index=0 condition={name}Condition "
                 f"bound=1 target={names[(i + 1) % 4]} target-index={(i + 1) % 4}\n")
    text += (f"[JUDGDIRECTOR] fsm-init fsm={FSM} class=GearGame.FSM_AIDirector outer={DIRECTOR} "
             f"owner={DIRECTOR} script-owner={DIRECTOR} states=4 transitions=4 delegates=12 "
             "status=1 script-init=1 activate=0\n")
    return text + (f"[JUDGDIRECTOR][PARTIAL] director={DIRECTOR} class=GearGame.AIDirector "
                   f"spawner=Transient.SmartSpawner_0 fsm={FSM} cdo=0 auto-setup=1 running=0 "
                   "native-pending=DirectorTick,FSMTick,PacingCallbacks,ETQQueries\n")


class DirectorInitializationProofTests(unittest.TestCase):
    def test_original_four_state_machine_is_initialized_and_inactive(self):
        report = audit_director_initialization(trace())
        self.assertEqual(report["transition_indices"], [1, 2, 3, 0])
        self.assertEqual(report["bound_delegates"], 12)
        self.assertTrue(report["original_script_owner_verified"])
        self.assertTrue(report["auto_level_marker_setup_enabled"])
        self.assertFalse(report["pacing_callbacks_implemented"])
        self.assertFalse(report["activated"])
        self.assertFalse(report["running"])
        self.assertFalse(report["encounter_verified"])

    def test_unflagged_or_absent_proof_does_not_pass(self):
        self.assertIsNone(audit_director_initialization("ordinary log"))
        for text in (trace().replace("-JUDGAIDIRECTORINIT", ""), "-JUDGAIDIRECTORINIT"):
            with self.assertRaises(GraphError):
                audit_director_initialization(text)

    def test_partial_or_repeated_snapshots_fail(self):
        for text in (trace() + trace(), trace().replace("delegates=12", "delegates=11"),
                     trace().replace("states=4", "states=3"),
                     trace().replace("native-pending=DirectorTick,FSMTick,PacingCallbacks,ETQQueries", "native-pending=None")):
            with self.subTest(text=text[-160:]), self.assertRaises(GraphError):
                audit_director_initialization(text)

    def test_wrong_owner_class_or_cdo_fails(self):
        for old, new in (("script-owner=" + DIRECTOR, "script-owner=None"),
                         ("outer=" + DIRECTOR, "outer=Transient"),
                         ("class=GearGame.FSM_AIDirector", "class=GearGame.FiniteStateMachine"),
                         ("class=GearGame.AIDirector", "class=Core.Object"), ("cdo=0", "cdo=1")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_director_initialization(trace().replace(old, new))

    def test_missing_or_wrong_delegate_binding_fails(self):
        for old, new in (("enter-bound=1", "enter-bound=0"), ("leave-bound=1", "leave-bound=0"),
                         ("condition=BuildUpCondition", "condition=RelaxCondition"),
                         ("name=PeakFade", "name=OtherState")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_director_initialization(trace().replace(old, new, 1))

    def test_invalid_transition_index_target_or_count_fails(self):
        for old, new in (("target-index=1", "target-index=-1"), ("target-index=1", "target-index=3"),
                         ("target=PeakSustain", "target=Relax"), ("transitions=1", "transitions=2")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_director_initialization(trace().replace(old, new, 1))

    def test_unintended_activation_or_uninitialized_status_fails(self):
        for old, new in (("running=0", "running=1"), ("activate=0", "activate=1"),
                         ("status=1", "status=0"), ("script-init=1", "script-init=0"),
                         ("auto-setup=1", "auto-setup=0")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_director_initialization(trace().replace(old, new))

    def test_continued_native_fallback_fails(self):
        with self.assertRaises(GraphError):
            audit_director_initialization(trace() + "[JUDGBIND][STUB] cls=AIDirector#1 func=Init count=1\n")

    def test_director_must_use_the_actual_singleton_spawner(self):
        self.assertIsNotNone(audit_director_initialization(trace(), "Transient.SmartSpawner_0"))
        with self.assertRaises(GraphError):
            audit_director_initialization(trace(), "Transient.SmartSpawner_1")


if __name__ == "__main__":
    unittest.main()
