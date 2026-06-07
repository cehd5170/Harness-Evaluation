from __future__ import annotations

import unittest
from pathlib import Path

from harness_evaluation.canonical import CanonicalRun
from harness_evaluation.compare import compare_runs
from harness_evaluation.summarize import summarize_run


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "canonical_runs"


class CanonicalRunTests(unittest.TestCase):
    def _run(self, run_id: str, results: dict[str, dict]) -> CanonicalRun:
        return CanonicalRun(
            run_dir=Path("."),
            metadata={
                "run_id": run_id,
                "system": "test",
                "harness": "test",
                "model": "test",
                "dataset_id": "test",
            },
            results=results,
        )

    def test_summarize_example_run(self) -> None:
        summary = summarize_run(EXAMPLES / "deepagent-exp-a")

        self.assertEqual(summary["run_id"], "deepagent-exp-a-2026-06-02")
        self.assertEqual(summary["task_count"], 3)
        self.assertEqual(summary["scored_task_count"], 3)
        self.assertEqual(summary["mean_score"], 0.823333)
        self.assertEqual(summary["success_rate"], 0.666667)
        self.assertEqual(summary["p50_elapsed_sec"], 48.0)
        self.assertEqual(summary["p95_elapsed_sec"], 94.8)
        self.assertEqual(sorted(summary["by_category"]), ["calendar", "documents", "spreadsheets"])

    def test_compare_example_runs(self) -> None:
        comparison = compare_runs(EXAMPLES / "deepagent-main", EXAMPLES / "deepagent-exp-a")

        self.assertEqual(comparison["common_task_count"], 3)
        self.assertEqual(comparison["baseline_only_task_ids"], [])
        self.assertEqual(comparison["candidate_only_task_ids"], [])
        self.assertEqual([item["task_id"] for item in comparison["improvements"]], ["doc-summary-001"])
        self.assertEqual(
            [item["task_id"] for item in comparison["regressions"]],
            ["spreadsheet-cleanup-001"],
        )
        deltas = {item["task_id"]: item["score_delta"] for item in comparison["task_deltas"]}
        self.assertEqual(deltas["calendar-scheduling-001"], 0.0)

    def test_success_only_results_are_scored(self) -> None:
        run = self._run(
            "success-only",
            {
                "task-a": {"task_id": "task-a", "success": True},
                "task-b": {"task_id": "task-b", "success": False},
            },
        )

        summary = summarize_run(run)

        self.assertEqual(summary["scored_task_count"], 2)
        self.assertEqual(summary["mean_score"], 0.5)
        self.assertEqual(summary["success_rate"], 0.5)

    def test_threshold_boundary_is_not_classified(self) -> None:
        baseline = self._run("baseline", {"task-a": {"task_id": "task-a", "score": 0.5}})
        candidate = self._run("candidate", {"task-a": {"task_id": "task-a", "score": 0.55}})

        comparison = compare_runs(baseline, candidate, threshold=0.05)

        self.assertEqual(comparison["improvements"], [])
        self.assertEqual(comparison["regressions"], [])


if __name__ == "__main__":
    unittest.main()
