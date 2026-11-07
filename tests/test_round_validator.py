import unittest
from agent.round_validator import ConservativeRoundValidator, TableEvidence


def ev(fid, phase, result=None, revision="hist-A", round_id="R100", trusted=True, table="B51"):
    return TableEvidence(table, fid, phase, round_id, result, revision, trusted)


class FSMTests(unittest.TestCase):
    def test_two_stable_frames_and_trusted_id(self):
        v = ConservativeRoundValidator("B51")
        self.assertIsNone(v.accept(ev("f1", "BETTING")))
        self.assertIsNone(v.accept(ev("f2", "DEALING")))
        self.assertIsNone(v.accept(ev("f3", "RESULT", "BANKER", "hist-B")))
        confirmed = v.accept(ev("f4", "RESULT", "BANKER", "hist-B"))
        self.assertIsNotNone(confirmed)
        self.assertEqual(confirmed.result, "BANKER")
        self.assertIsNone(v.accept(ev("f5", "RESULT", "BANKER", "hist-B")))

    def test_color_or_result_without_round_sequence_not_confirmed(self):
        v = ConservativeRoundValidator("B51")
        self.assertIsNone(v.accept(ev("f1", "RESULT", "BANKER", "hist-B")))
        self.assertIsNone(v.accept(ev("f2", "RESULT", "BANKER", "hist-B")))

    def test_untrusted_id_not_confirmed(self):
        v = ConservativeRoundValidator("B51")
        for i,phase in enumerate(["BETTING","DEALING","RESULT","RESULT"]):
            self.assertIsNone(v.accept(ev(f"f{i}",phase,"BANKER","hist-B",trusted=False)))

    def test_gap_resets_state(self):
        v = ConservativeRoundValidator("B51")
        v.accept(ev("f1","BETTING"))
        v.accept(ev("f2","DEALING"))
        v.accept(ev("f3","RESULT","BANKER","hist-B"))
        v.gap()
        self.assertIsNone(v.accept(ev("f4","RESULT","BANKER","hist-B")))
        self.assertIsNone(v.accept(ev("f5","RESULT","BANKER","hist-B")))

if __name__ == "__main__":
    unittest.main()
