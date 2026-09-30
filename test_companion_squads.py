"""Synthetic evidence for existing scripted squad membership, not movement."""
import unittest

from campaign_graph import GraphError
from validate_campaign_fixture import audit_companion_squads


PLAYER = "Judgment_SP_E2_P.TheWorld:PersistentLevel.GearPC_AID_0"


def trace():
    base = "Judgment_SP_E2_P.TheWorld:PersistentLevel."
    text = "command -JUDGAISQUADTRACE\n"
    for i, name in enumerate(("Carmine", "Barrick", "Gus"), 1):
        text += (f"[JUDGAISQUAD] controller={base}GearAI_{name}_0 pawn={base}Pawn_{name}_0 "
                 f"squad-readable=1 squad={base}GearSquad_0 pri-readable=1 pri={base}GearPRI_{i} "
                 f"team-readable=1 team={base}GearTeamInfo_0 leader-readable=1 leader={PLAYER} "
                 f"members-readable=1 members=4 self-index={i}\n")
    return text + "[JUDGAISQUAD] snapshot controllers=3 scanned=4 limit=0 game-time=30.125\n"


class SquadProofTests(unittest.TestCase):
    def test_three_real_members_and_player_leader(self):
        report = audit_companion_squads(trace(), PLAYER)
        self.assertEqual([m["member_index"] for m in report["verified_ai_members"]], [2, 1, 3])
        self.assertEqual(report["leader"], PLAYER)
        self.assertEqual(report["array_entries"], 4)
        self.assertFalse(report["player_array_entry_verified"])
        self.assertFalse(report["movement_or_encounter_verified"])

    def test_without_flag_has_no_membership_claim(self):
        self.assertIsNone(audit_companion_squads("ordinary log", PLAYER))
        with self.assertRaises(GraphError):
            audit_companion_squads(trace().replace("-JUDGAISQUADTRACE", ""), PLAYER)

    def test_missing_repeated_or_limited_snapshot_fails(self):
        for text in ("-JUDGAISQUADTRACE", trace() + trace(), trace().replace("limit=0", "limit=1"),
                     trace().replace("game-time=30.125", "game-time=5.0"),
                     trace().replace("scanned=4", "scanned=64")):
            with self.subTest(text=text[:50]), self.assertRaises(GraphError):
                audit_companion_squads(text, PLAYER)

    def test_unreadable_and_missing_objects_fail(self):
        for field in ("squad", "pri", "team", "leader", "members"):
            with self.subTest(field=field), self.assertRaises(GraphError):
                audit_companion_squads(trace().replace(field + "-readable=1", field + "-readable=0"), PLAYER)
        for field in ("pawn", "squad", "pri", "team", "leader"):
            text = trace()
            start = text.index(field + "=")
            end = text.index(" ", start)
            with self.subTest(field=field), self.assertRaises(GraphError):
                audit_companion_squads(text[:start] + field + "=None" + text[end:], PLAYER)

    def test_duplicate_controller_pawn_and_pri_fail(self):
        for old, new in (("GearAI_Barrick_0", "GearAI_Carmine_0"),
                         ("Pawn_Barrick_0", "Pawn_Carmine_0"), ("GearPRI_2", "GearPRI_1")):
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_companion_squads(trace().replace(old, new), PLAYER)

    def test_wrong_squad_team_leader_and_size_fail(self):
        original = trace()
        for old, new in (("GearSquad_0", "GearSquad_1"), ("GearTeamInfo_0", "GearTeamInfo_1"),
                         ("members=4", "members=3"), (PLAYER, "Default__GearPC")):
            text = original.replace(old, new, 1)
            with self.subTest(old=old), self.assertRaises(GraphError):
                audit_companion_squads(text, PLAYER)

    def test_absent_duplicate_and_out_of_range_member_indices_fail(self):
        for value in (-1, 0, 2, 4, 999):
            with self.subTest(value=value), self.assertRaises(GraphError):
                audit_companion_squads(trace().replace("self-index=1", f"self-index={value}"), PLAYER)


if __name__ == "__main__":
    unittest.main()
