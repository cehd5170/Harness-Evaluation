from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness_evaluation.canonical import CanonicalFormatError
from harness_evaluation.compare import compare_runs
from harness_evaluation.datasets import init_custom_dataset, list_datasets, sample_dataset, validate_dataset
from harness_evaluation.ingest import IngestError, ingest_run
from harness_evaluation.metrics import summarize_result_dir
from harness_evaluation.runner import RunnerError, run_suite
from harness_evaluation.summarize import summarize_run
from harness_evaluation.usage import apply_pricing, summarize_usage_file


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    metrics = sub.add_parser("metrics", help="Summarize result JSON files into AA-style metrics")
    metrics.add_argument("--results-dir", required=True)

    usage = sub.add_parser("usage", help="Parse usage JSON/JSONL from Codex, Claude Code, or API logs")
    usage.add_argument("--file", required=True)
    usage.add_argument("--pricing-json", default=None, help="Optional pricing JSON file")

    manifest = sub.add_parser("manifest", help="Print the bundled AA-style suite manifest")
    manifest.add_argument(
        "--file",
        default=str(Path(__file__).resolve().parents[2] / "manifests" / "aa-coding-agents-suite.json"),
    )

    datasets = sub.add_parser("datasets", help="List local dataset manifests and downloaded files")
    datasets.add_argument("--root", default=None)

    init_dataset = sub.add_parser("init-dataset", help="Create a custom JSONL dataset scaffold")
    init_dataset.add_argument("--id", required=True)
    init_dataset.add_argument("--root", default=None)
    init_dataset.add_argument("--overwrite", action="store_true")

    validate = sub.add_parser("validate-dataset", help="Validate a dataset manifest and JSONL files")
    validate.add_argument("--id", required=True)
    validate.add_argument("--root", default=None)

    sample = sub.add_parser("sample-dataset", help="Print a few rows from a dataset")
    sample.add_argument("--id", required=True)
    sample.add_argument("--root", default=None)
    sample.add_argument("--limit", type=int, default=3)

    ingest = sub.add_parser("ingest-run", help="Convert a raw external-harness run into canonical JSON")
    ingest.add_argument("--input-dir", required=True)
    ingest.add_argument("--output-dir", required=True)
    ingest.add_argument("--profile", required=True)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--system", required=True)
    ingest.add_argument("--harness", required=True)
    ingest.add_argument("--model", required=True)
    ingest.add_argument("--dataset-id", required=True)
    ingest.add_argument("--dataset-version", default=None)
    ingest.add_argument("--code-commit", default=None)
    ingest.add_argument("--created-at", default=None)

    def add_runner_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--dataset-jsonl", required=True)
        command.add_argument("--runner", required=True, help="Runner profile JSON")
        command.add_argument("--output-dir", required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--system", required=True)
        command.add_argument("--harness", required=True)
        command.add_argument("--model", required=True)
        command.add_argument("--dataset-id", default=None)
        command.add_argument("--dataset-version", default=None)
        command.add_argument("--code-commit", default=None)
        command.add_argument("--created-at", default=None)
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--continue-on-error", action="store_true")

    run_task = sub.add_parser("run-task", help="Run one dataset task through an external CLI profile")
    add_runner_arguments(run_task)
    run_task.add_argument("--task-id", required=True)

    run_suite_parser = sub.add_parser("run-suite", help="Run dataset tasks through an external CLI profile")
    add_runner_arguments(run_suite_parser)
    run_suite_parser.add_argument("--max-tasks", type=int, default=None)

    summarize = sub.add_parser("summarize-run", help="Summarize a canonical run directory")
    summarize.add_argument("--run-dir", required=True)

    compare = sub.add_parser("compare-runs", help="Compare two canonical run directories")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--threshold", type=float, default=0.05)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "metrics":
        print(json.dumps(summarize_result_dir(Path(args.results_dir)), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "usage":
        summary = summarize_usage_file(Path(args.file))
        if summary is None:
            raise SystemExit("no usage records found")
        pricing = _load_json(Path(args.pricing_json)) if args.pricing_json else None
        print(json.dumps(apply_pricing(summary, pricing), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "manifest":
        print(Path(args.file).read_text(encoding="utf-8"))
        return 0
    if args.cmd == "datasets":
        root = Path(args.root) if args.root else None
        print(json.dumps(list_datasets(root), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "init-dataset":
        root = Path(args.root) if args.root else None
        print(json.dumps(init_custom_dataset(args.id, root=root, overwrite=args.overwrite), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "validate-dataset":
        root = Path(args.root) if args.root else None
        result = validate_dataset(args.id, root=root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "sample-dataset":
        root = Path(args.root) if args.root else None
        print(json.dumps(sample_dataset(args.id, root=root, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "ingest-run":
        try:
            result = ingest_run(
                input_dir=Path(args.input_dir),
                output_dir=Path(args.output_dir),
                profile_path=Path(args.profile),
                run_metadata={
                    "run_id": args.run_id,
                    "system": args.system,
                    "harness": args.harness,
                    "model": args.model,
                    "dataset_id": args.dataset_id,
                    "dataset_version": args.dataset_version,
                    "code_commit": args.code_commit,
                    "created_at": args.created_at,
                },
            )
        except IngestError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.cmd in ("run-task", "run-suite"):
        metadata = {
            "run_id": args.run_id,
            "system": args.system,
            "harness": args.harness,
            "model": args.model,
            "dataset_id": args.dataset_id,
            "dataset_version": args.dataset_version,
            "code_commit": args.code_commit,
            "created_at": args.created_at,
            "dry_run": args.dry_run,
            "continue_on_error": args.continue_on_error,
        }
        try:
            result = run_suite(
                dataset_jsonl=Path(args.dataset_jsonl),
                runner_profile=Path(args.runner),
                output_dir=Path(args.output_dir),
                run_metadata=metadata,
                max_tasks=args.max_tasks if args.cmd == "run-suite" else None,
                task_id=args.task_id if args.cmd == "run-task" else None,
            )
        except RunnerError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["errors"] else 1
    if args.cmd == "summarize-run":
        try:
            summary = summarize_run(Path(args.run_dir))
        except CanonicalFormatError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "compare-runs":
        try:
            comparison = compare_runs(Path(args.baseline), Path(args.candidate), threshold=args.threshold)
        except (CanonicalFormatError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
