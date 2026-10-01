"""Detached FSM evidence gates. Fixtures contain no original game assets/code."""
import unittest

from campaign_graph import GraphError
from test_director_initialization import trace as director_trace
from validate_campaign_fixture import audit_director_initialization, audit_fsm_core


PARTIAL = ("[JUDGFSM][PARTIAL] core=1 director-timer=1 relax-condition=1 "
           "live-director-tick=0 pacing-enter-pending=4 query-pending=1\n")
CASES = """condition-before-timer 4 0 0 -0.250 1 0
expired-event-transition 4 1 0 -0.250 2 1
pause-preserves-event-and-time 3 1 1 -0.250 2 1
resume-does-not-reenter 4 1 1 -0.250 2 1
resumed-event-transition 4 2 0 -0.500 3 2
forced-and-invalid-state-controls 4 0 0 -0.500 5 4
no-event-does-not-transition 4 0 0 -0.750 5 4
inactive-preserves-event-and-time 2 0 1 -0.750 5 5
force-while-inactive 2 1 1 -0.750 6 6
reactivate-resets-initial-state 4 0 1 -0.750 7 6
transition-priority-over-event-order 4 1 0 -0.750 8 7
wildcard-event-transition 4 1 0 -0.750 10 9"""


def trace(self_test=True):
    text = director_trace() + "command -JUDGFSMCORE\n" + PARTIAL
    if not self_test:
        return text
    text += "command -JUDGFSMSELFTEST\n"
    for row in CASES.splitlines():
        name, status, state, queued, remaining, enter, leave = row.split()
        text += (f"[JUDGFSMTEST] case={name} status={status} state={state} queued={queued} "
                 f"remaining={remaining} enter={enter} leave={leave}\n")
    for i, (value, result) in enumerate((
            ("3f800000", 0), ("3e800000", 0), ("00000000", 1), ("80000000", 1),
            ("be800000", 1), ("bf800000", 1), ("7f800000", 0), ("ff800000", 1), ("7fc00000", 1))):
        text += f"[JUDGFSMTEST] oracle kind=relax index={i} input={value} result={result}\n"
    for i, (value, delta, result) in enumerate((
            ("0.250", "0.500", "be800000"), ("0.000", "0.500", "bf000000"),
            ("-0.250", "0.500", "bf400000"), ("1.000", "0.000", "3f800000"),
            ("1.000", "-0.500", "3fc00000"), ("1.000", "1.000", "00000000"))):
        text += (f"[JUDGFSMTEST] oracle kind=timer index={i} input={value} "
                 f"delta={delta} result={result}\n")
    return text + ("[JUDGFSMTEST] complete cases=12 shadow=Transient.FSM_AIDirector_1 "
                   "class=GearGame.FSM_AIDirector live-fsm=Transient.AIDirector_0:FSM_AIDirector_0 "
                   "detached=1 live-unchanged=1 command-class=None oracle-cases=15 encounter=0\n")


def audit(text):
    return audit_fsm_core(text, audit_director_initialization(text))


class FSMCoreProofTests(unittest.TestCase):
    def assert_rejected_changes(self, pairs):
        for old, new in pairs:
            with self.subTest(old=old, new=new), self.assertRaises(GraphError):
                audit(trace().replace(old, new, 1))

    def test_detached_controls_and_original_numeric_probes_pass(self):
        report = audit(trace())
        self.assertTrue(report["detached_self_test_verified"])
        self.assertTrue(report["live_objects_unchanged"])
        self.assertEqual(len(report["control_cases"]), 12)
        self.assertEqual(report["original_code_numeric_cases"], 15)
        for key in ("live_director_tick_implemented", "pacing_enter_callbacks_implemented",
                    "native_queries_implemented", "state_command_class_path_verified", "encounter_verified"):
            self.assertFalse(report[key])

    def test_core_without_self_test_does_not_claim_tested_controls(self):
        report = audit(trace(False))
        self.assertFalse(report["detached_self_test_verified"])
        self.assertEqual(report["control_cases"], [])
        self.assertEqual(report["original_code_numeric_cases"], 0)

    def test_unflagged_baseline_has_no_experiment(self):
        self.assertIsNone(audit_fsm_core("ordinary trace"))

    def test_missing_flags_or_director_proof_fail(self):
        for text in (trace().replace("-JUDGFSMCORE", ""),
                     trace().replace("-JUDGFSMSELFTEST", ""), "-JUDGFSMCORE -JUDGFSMSELFTEST"):
            with self.assertRaises(GraphError):
                audit(text)
        with self.assertRaises(GraphError):
            audit_fsm_core(trace(), None)

    def test_partial_disclosure_cannot_omit_pending_work(self):
        self.assert_rejected_changes((
            (PARTIAL, ""), ("core=1", "core=0"), ("director-timer=1", "director-timer=0"),
            ("relax-condition=1", "relax-condition=0"), ("live-director-tick=0", "live-director-tick=1"),
            ("pacing-enter-pending=4", "pacing-enter-pending=0"), ("query-pending=1", "query-pending=0")))
        with self.assertRaises(GraphError):
            audit(trace() + PARTIAL)

    def test_missing_repeated_or_reordered_controls_fail(self):
        lines = trace().splitlines(True)
        first = next(line for line in lines if "case=condition-before-timer" in line)
        second = next(line for line in lines if "case=expired-event-transition" in line)
        for text in (trace().replace(first, ""), trace() + first,
                     trace().replace(first + second, second + first)):
            with self.assertRaises(GraphError):
                audit(text)

    def test_pause_cannot_consume_events_or_decrement_time(self):
        self.assert_rejected_changes((
            ("case=pause-preserves-event-and-time status=3 state=1 queued=1",
             "case=pause-preserves-event-and-time status=3 state=1 queued=0"),
            ("case=pause-preserves-event-and-time status=3 state=1 queued=1 remaining=-0.250",
             "case=pause-preserves-event-and-time status=3 state=1 queued=1 remaining=-1.250")))

    def test_resume_cannot_invoke_enter_again(self):
        self.assert_rejected_changes((
            ("case=resume-does-not-reenter status=4 state=1 queued=1 remaining=-0.250 enter=2",
             "case=resume-does-not-reenter status=4 state=1 queued=1 remaining=-0.250 enter=3"),))

    def test_priority_and_timer_order_must_match_original(self):
        self.assert_rejected_changes((
            ("case=transition-priority-over-event-order status=4 state=1",
             "case=transition-priority-over-event-order status=4 state=3"),
            ("case=condition-before-timer status=4 state=0", "case=condition-before-timer status=4 state=1"),
            ("case=wildcard-event-transition status=4 state=1", "case=wildcard-event-transition status=4 state=0")))

    def test_complete_requires_detached_original_class_and_live_identity(self):
        self.assert_rejected_changes((
            ("shadow=Transient.FSM_AIDirector_1", "shadow=Transient.AIDirector_0:FSM_AIDirector_0"),
            ("shadow=Transient.FSM_AIDirector_1", "shadow=Transient.Default__FSM_AIDirector"),
            ("live-fsm=Transient.AIDirector_0:FSM_AIDirector_0", "live-fsm=Transient.FSM_AIDirector_2"),
            ("detached=1", "detached=0"), ("live-unchanged=1", "live-unchanged=0"),
            ("encounter=0", "encounter=1"), ("command-class=None", "command-class=GearGame.CombatCommand"),
            ("complete cases=12", "complete cases=11"), ("oracle-cases=15", "oracle-cases=14")))
        # The initializer's class proof must also remain valid.
        with self.assertRaises(GraphError):
            audit(trace().replace("class=GearGame.FSM_AIDirector", "class=Core.Object"))

    def test_all_numeric_cases_are_required_in_order(self):
        first = next(line for line in trace().splitlines(True) if "oracle kind=relax index=0" in line)
        for text in (trace().replace(first, ""), trace() + first,
                     trace().replace("oracle kind=relax index=0", "oracle kind=relax index=1")):
            with self.assertRaises(GraphError):
                audit(text)

    def test_nan_signed_zero_and_timer_bits_must_match_ppc(self):
        self.assert_rejected_changes((
            ("input=7fc00000 result=1", "input=7fc00000 result=0"),
            ("input=80000000 result=1", "input=80000000 result=0"),
            ("result=be800000", "result=00000000"), ("delta=-0.500", "delta=0.500")))

    def test_unrecognized_or_reordered_marker_lines_fail(self):
        first = next(line for line in trace().splitlines(True) if "oracle kind=relax index=0" in line)
        first_case = next(line for line in trace().splitlines(True) if "case=condition-before-timer" in line)
        for text in (trace() + "[JUDGFSMTEST] unknown=1\n", trace() + trace(),
                     trace().replace(first, "").replace(first_case, first + first_case)):
            with self.assertRaises(GraphError):
                audit(text)

    def test_ported_natives_cannot_fall_back_but_pending_callbacks_can(self):
        for cls, functions in (("FiniteStateMachine", ("Init", "Activate", "Deactivate", "Pause",
                               "OnWorldEvent", "ForceTransitionToState", "ForceTransitionToStateIndex",
                               "GetCurrentStateCommandClass")),
                               ("FSM_AIDirector", ("RelaxCondition", "BuildUpOnLeave", "PeakSustainOnLeave",
                                "PeakFadeOnLeave", "RelaxOnLeave"))):
            for function in functions:
                with self.subTest(function=function), self.assertRaises(GraphError):
                    audit(trace() + f"[JUDGBIND][STUB] cls={cls}#1 func={function} count=1\n")
        report = audit(trace() + "[JUDGBIND][STUB] cls=FSM_AIDirector#1 func=BuildUpOnEnter count=1\n")
        self.assertFalse(report["pacing_enter_callbacks_implemented"])


if __name__ == "__main__":
    unittest.main()
