from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness_evaluation.checkers import run_checker
from harness_evaluation.runner import RunnerError, run_suite
from harness_evaluation.runner_profiles import RunnerProfileError, render_command, validate_runner_profile
from harness_evaluation.summarize import summarize_run


class RunnerTests(unittest.TestCase):
    def _profile(self, command: list[str]) -> dict:
        return {
            "id": "test-runner",
            "type": "subprocess",
            "command": command,
            "cwd": "{{workspace_dir}}",
            "timeout_sec": 10,
            "env": {"EXPLICIT_VALUE": "visible"},
            "capture": {"stdout": "stdout.log", "stderr": "stderr.log"},
            "artifacts": {"glob": ["output.txt"], "exclude": []},
        }

    def _dataset(self, root: Path, tasks: list[dict]) -> Path:
        dataset_dir = root / "dataset"
        data_dir = dataset_dir / "data"
        data_dir.mkdir(parents=True)
        (dataset_dir / "dataset.json").write_text(
            json.dumps({"id": "runner-test", "version": "v1"}),
            encoding="utf-8",
        )
        path = data_dir / "test.jsonl"
        path.write_text("\n".join(json.dumps(task) for task in tasks) + "\n", encoding="utf-8")
        return path

    def test_run_suite_isolates_workspace_and_writes_canonical_result(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(
                root,
                [
                    {
                        "task_id": "task-001",
                        "prompt": "hello runner",
                        "metadata": {"category": "test"},
                        "checker": {
                            "type": "artifact",
                            "expected_files": ["output.txt"],
                            "required_text": {"output.txt": "hello runner"},
                        },
                    }
                ],
            )
            run_dir = root / "run"
            summary = run_suite(
                dataset,
                self._profile(
                    [
                        sys.executable,
                        "-c",
                        "import pathlib,sys; pathlib.Path('output.txt').write_text(sys.argv[1])",
                        "{{prompt}}",
                    ]
                ),
                run_dir,
                {"run_id": "test", "system": "test", "harness": "subprocess", "model": "none"},
            )
            result = json.loads((run_dir / "results" / "task-001.json").read_text(encoding="utf-8"))
            run_summary = summarize_run(run_dir)

        self.assertEqual(summary["successful_tasks"], 1)
        self.assertTrue(result["success"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["metadata"]["category"], "test")
        self.assertEqual(result["artifacts"]["files"][0]["workspace_path"], "output.txt")
        self.assertEqual(run_summary["task_count"], 1)

    def test_environment_is_not_inherited(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(
                root,
                [
                    {
                        "task_id": "env-001",
                        "prompt": "inspect env",
                        "checker": {
                            "type": "json",
                            "file": "env.json",
                            "expected_values": {"explicit": "visible", "inherited": None},
                        },
                    }
                ],
            )
            os.environ["HARNESS_EVALUATION_SHOULD_NOT_LEAK"] = "secret"
            profile = self._profile(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json,os,pathlib;"
                        "pathlib.Path('env.json').write_text(json.dumps({"
                        "'explicit':os.environ.get('EXPLICIT_VALUE'),"
                        "'inherited':os.environ.get('HARNESS_EVALUATION_SHOULD_NOT_LEAK')}))"
                    ),
                ]
            )
            profile["artifacts"]["glob"] = ["env.json"]
            run_suite(
                dataset,
                profile,
                root / "run",
                {"run_id": "env", "system": "test", "harness": "subprocess", "model": "none"},
            )
            result = json.loads((root / "run" / "results" / "env-001.json").read_text(encoding="utf-8"))

        self.assertTrue(result["success"])

    def test_dry_run_renders_without_execution(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root, [{"task_id": "dry-001", "prompt": "do not execute"}])
            summary = run_suite(
                dataset,
                self._profile([sys.executable, "-c", "raise SystemExit(99)", "{{task_id}}"]),
                root / "run",
                {
                    "run_id": "dry",
                    "system": "test",
                    "harness": "subprocess",
                    "model": "none",
                    "dry_run": True,
                },
            )
            result = json.loads((root / "run" / "results" / "dry-001.json").read_text(encoding="utf-8"))

        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["commands"][0]["command"][-1], "dry-001")
        self.assertEqual(result["error_type"], "dry_run")
        self.assertIsNone(result["exit_code"])

    def test_runner_cwd_cannot_escape_task_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(root, [{"task_id": "unsafe-001", "prompt": "unsafe"}])
            profile = self._profile([sys.executable, "-c", "pass"])
            profile["cwd"] = "{{output_dir}}"

            summary = run_suite(
                dataset,
                profile,
                root / "run",
                {"run_id": "unsafe", "system": "test", "harness": "subprocess", "model": "none"},
            )

        self.assertEqual(summary["tasks_completed"], 0)
        self.assertIn("runner cwd must be inside", summary["errors"][0]["error"])

    def test_timeout_and_continue_on_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._dataset(
                root,
                [
                    {"task_id": "slow-001", "prompt": "slow one"},
                    {"task_id": "slow-002", "prompt": "slow two"},
                ],
            )
            profile = self._profile([sys.executable, "-c", "import time; time.sleep(0.2)"])
            profile["timeout_sec"] = 0.05

            summary = run_suite(
                dataset,
                profile,
                root / "run",
                {
                    "run_id": "timeouts",
                    "system": "test",
                    "harness": "subprocess",
                    "model": "none",
                    "continue_on_error": True,
                },
            )
            results = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((root / "run" / "results").glob("*.json"))
            ]

        self.assertEqual(summary["tasks_completed"], 2)
        self.assertEqual([result["error_type"] for result in results], ["timeout", "timeout"])

    def test_profile_rejects_unknown_template_variable(self) -> None:
        profile = self._profile(["echo", "{{unknown}}"])

        with self.assertRaises(RunnerProfileError):
            validate_runner_profile(profile)

    def test_render_command_preserves_argument_boundaries(self) -> None:
        profile = self._profile(["agent", "--prompt", "{{prompt}}"])

        command = render_command(profile, {"prompt": "two words"})

        self.assertEqual(command, ["agent", "--prompt", "two words"])


class CheckerTests(unittest.TestCase):
    def test_artifact_checker_accepts_simple_required_text_list(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "answer.txt").write_text("alpha beta", encoding="utf-8")

            result = run_checker(
                {
                    "type": "artifact",
                    "expected_files": ["answer.txt"],
                    "required_text": ["alpha", "beta"],
                },
                workspace,
            )

        self.assertTrue(result["success"])

    def test_command_and_json_checkers(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "value.json").write_text('{"status":"ok","nested":{"count":2}}', encoding="utf-8")

            json_result = run_checker(
                {
                    "type": "json",
                    "file": "value.json",
                    "required_fields": ["nested.count"],
                    "expected_values": {"status": "ok", "nested.count": 2},
                },
                workspace,
            )
            command_result = run_checker(
                {"type": "command", "command": [sys.executable, "-c", "raise SystemExit(0)"]},
                workspace,
            )

        self.assertTrue(json_result["success"])
        self.assertTrue(command_result["success"])


if __name__ == "__main__":
    unittest.main()
