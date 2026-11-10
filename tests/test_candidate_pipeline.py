import unittest

from agent.pipeline import CandidatePipeline
from agent.round_validator import TableEvidence
from agent.site_adapter import ExtractedEvidence
from agent.adapters.dom import load_dom_config
from agent.adapters.structured import StructuredExportAdapter
from agent.site_adapter import CapturedFrame
from pathlib import Path


def record(frame_id, phase, result=None, revision="revA", *, source="approved-source"):
    return ExtractedEvidence(
        source_id=source,
        captured_at_utc="2026-10-19T12:00:00Z",
        evidence_ref=f"private://evidence/{frame_id}",
        evidence=TableEvidence("B51", frame_id, phase, "R100", result, revision, True),
    )


class CandidatePipelineTests(unittest.TestCase):
    def test_dom_template_loads_but_structured_ids_default_untrusted(self):
        path = Path(__file__).resolve().parents[1] / "config/real_dom.example.yaml"
        config = load_dom_config(path)
        self.assertEqual(config.source_id, "approved-provider-01")
        self.assertEqual(config.tables[0].table_id, "B51")
        adapter = StructuredExportAdapter(config.source_id)
        frame = CapturedFrame(config.source_id, "f1", "2026-10-19T00:00:00Z", "demo://f1",
                              payload={"tables": [{"table_id": "B51", "shoe_id": "s1",
                                                   "round_id": "r1", "phase": "RESULT",
                                                   "final_result": "BANKER",
                                                   "roadmap_revision": "v2"}]})
        self.assertFalse(adapter.extract(frame)[0].evidence.round_id_trusted)

    def test_emits_one_traced_candidate_after_two_result_frames(self):
        pipeline = CandidatePipeline("approved-source")
        self.assertIsNone(pipeline.accept(record("f1", "BETTING")))
        self.assertIsNone(pipeline.accept(record("f2", "DEALING")))
        self.assertIsNone(pipeline.accept(record("f3", "RESULT", "BANKER", "revB")))
        candidate = pipeline.accept(record("f4", "RESULT", "BANKER", "revB"))
        self.assertEqual(candidate.result, "BANKER")
        self.assertEqual(candidate.evidence_frames, ("f3", "f4"))
        self.assertEqual(candidate.evidence_refs, ("private://evidence/f3", "private://evidence/f4"))
        self.assertEqual(candidate.observed_result_at_utc, "2026-10-19T12:00:00+00:00")
        self.assertIsNone(pipeline.accept(record("f5", "RESULT", "BANKER", "revB")))

    def test_a01_hundred_identical_frames_confirm_nothing(self):
        pipeline = CandidatePipeline("approved-source")
        for _ in range(100):
            self.assertIsNone(pipeline.accept(record("same", "RESULT", "BANKER", "revB")))
        pipeline.accept(record("f1", "BETTING"))
        pipeline.accept(record("f2", "DEALING"))
        self.assertIsNone(pipeline.accept(record("f3", "RESULT", "BANKER", "revB")))
        results = [pipeline.accept(record("f3", "RESULT", "BANKER", "revB")) for _ in range(100)]
        self.assertEqual(results, [None] * 100)

    def test_marker_paths_never_reference_round_writers(self):
        import ast
        root = Path(__file__).resolve().parents[1]
        writers = {"insert_verified_round", "save_candidate", "SourceCoordinator", "CandidatePipeline"}
        for path in (root / "agent/vision.py", root / "agent/config.py"):
            names = {node.id for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                     if isinstance(node, ast.Name)}
            self.assertFalse(names & writers, path.name)
        tree = ast.parse((root / "agent/browser.py").read_text(encoding="utf-8"))
        monitor = next(node for node in tree.body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "monitor_browser")
        called = {node.func.id for node in ast.walk(monitor)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertIn("record_observations", called)
        self.assertFalse(called & writers)

    def test_gap_and_changed_result_fail_closed(self):
        pipeline = CandidatePipeline("approved-source")
        pipeline.accept(record("f1", "BETTING"))
        pipeline.accept(record("f2", "DEALING"))
        pipeline.accept(record("f3", "RESULT", "BANKER", "revB"))
        self.assertIsNone(pipeline.accept(record("f4", "RESULT", "PLAYER", "revB")))
        pipeline.gap("B51")
        self.assertIsNone(pipeline.accept(record("f5", "RESULT", "PLAYER", "revB")))
        self.assertIsNone(pipeline.accept(record("f6", "RESULT", "PLAYER", "revB")))

    def test_rejects_unapproved_source_and_naive_time(self):
        pipeline = CandidatePipeline("approved-source")
        with self.assertRaises(ValueError):
            pipeline.accept(record("f1", "BETTING", source="other"))
        bad = ExtractedEvidence("approved-source", "2026-10-19T12:00:00", "ref",
                                TableEvidence("B51", "f1", "BETTING", "R100", None, "revA", True))
        with self.assertRaises(ValueError):
            pipeline.accept(bad)


if __name__ == "__main__":
    unittest.main()
