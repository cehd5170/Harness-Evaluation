from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness_evaluation.datasets import init_custom_dataset, list_datasets, sample_dataset, validate_dataset
from harness_evaluation.metrics import summarize_result_dir
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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
