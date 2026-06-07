from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness_evaluation.canonical import CanonicalRun
from harness_evaluation.compare import compare_runs
from harness_evaluation.ingest import ingest_run
from harness_evaluation.profiles import dotted_get, first_value
from harness_evaluation.summarize import summarize_run
from harness_evaluation.usage import summarize_usage_text


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "canonical_runs"
RAW_EXAMPLES = ROOT / "examples" / "raw_runs"
PROFILES = ROOT / "profiles"


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

        self.assertEqual(summary["run_id"], "deepagent-exp-a")
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

    def test_dotted_path_fallback(self) -> None:
        record = {"result": {"score": 0.7}, "events": [{"type": "tool_call"}]}

        self.assertEqual(dotted_get(record, "result.score"), 0.7)
        self.assertEqual(first_value(record, ["missing", "result.score"]), 0.7)

    def test_ingest_flat_deepagent_profile(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "canonical"
            summary = ingest_run(
                input_dir=RAW_EXAMPLES / "deepagent-exp-a",
                output_dir=output_dir,
                profile_path=PROFILES / "deepagent-result.json",
                run_metadata={
                    "run_id": "deepagent-exp-a",
                    "system": "deepagent-custom",
                    "harness": "deepagent",
                    "model": "qwen3-coder",
                    "dataset_id": "workflow-lite",
                },
            )
            run_summary = summarize_run(output_dir)
            doc_result = json.loads(
                (output_dir / "results" / "doc-summary-001.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["records_written"], 3)
        self.assertEqual(summary["warnings"], [])
        self.assertEqual(run_summary["mean_score"], 0.823333)
        self.assertEqual(doc_result["metrics"]["tool_calls"], 7)
        self.assertEqual(doc_result["artifacts"]["final_state"], {"document_written": True})
        self.assertEqual(doc_result["raw"]["source_files"], ["doc-summary-001.json"])

    def test_ingest_task_dir_uses_existing_usage_parser(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "canonical"
            summary = ingest_run(
                input_dir=RAW_EXAMPLES / "codex-like",
                output_dir=output_dir,
                profile_path=PROFILES / "cli-task-dir.json",
                run_metadata={
                    "run_id": "codex-like",
                    "system": "openai",
                    "harness": "codex-cli",
                    "model": "codex-example-model",
                    "dataset_id": "workflow-lite",
                },
            )
            run_summary = summarize_run(output_dir)
            doc_result = json.loads(
                (output_dir / "results" / "doc-summary-001.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["records_seen"], 3)
        self.assertEqual(run_summary["task_count"], 3)
        self.assertEqual(doc_result["usage"]["total_tokens"], 3300)
        self.assertIsNone(doc_result["usage"]["cost_usd"])
        self.assertEqual(
            doc_result["raw"]["source_files"],
            [
                "tasks/doc-summary-001/result.json",
                "tasks/doc-summary-001/usage.jsonl",
            ],
        )

    def test_ingest_generic_profile_fallbacks(self) -> None:
        with TemporaryDirectory() as directory:
            input_dir = Path(directory) / "raw"
            output_dir = Path(directory) / "canonical"
            input_dir.mkdir()
            (input_dir / "task-001.json").write_text(
                json.dumps(
                    {
                        "scoring": {"combined_score": 0.75},
                        "pass": 1,
                        "execution_time_sec": 12,
                        "usage_summary": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                        },
                    }
                ),
                encoding="utf-8",
            )
            summary = ingest_run(
                input_dir=input_dir,
                output_dir=output_dir,
                profile_path=PROFILES / "generic-result.json",
                run_metadata={
                    "run_id": "generic",
                    "system": "test",
                    "harness": "generic",
                    "model": "test",
                    "dataset_id": "test",
                },
            )
            result = json.loads((output_dir / "results" / "task-001.json").read_text(encoding="utf-8"))

        self.assertEqual(summary["records_written"], 1)
        self.assertEqual(result["task_id"], "task-001")
        self.assertEqual(result["score"], 0.75)
        self.assertIs(result["success"], True)
        self.assertEqual(result["usage"]["total_tokens"], 120)
        self.assertIsNone(result["usage"]["cost_usd"])

    def test_usage_cost_availability_distinguishes_missing_and_zero(self) -> None:
        missing = summarize_usage_text(
            '{"usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12,"cost_usd":null}}',
            source="test",
            include_cost_availability=True,
        )
        zero = summarize_usage_text(
            '{"usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12,"cost_usd":0}}',
            source="test",
            include_cost_availability=True,
        )

        self.assertIsNotNone(missing)
        self.assertIsNotNone(zero)
        self.assertIs(missing["cost_available"], False)
        self.assertIs(zero["cost_available"], True)


if __name__ == "__main__":
    unittest.main()
