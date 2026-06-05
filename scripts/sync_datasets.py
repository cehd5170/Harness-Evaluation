from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"


DOWNLOADS = {
    "swe-atlas-qna": {
        "README.md": "https://huggingface.co/datasets/ScaleAI/SWE-Atlas-QnA/resolve/main/README.md",
        "default_qa_config.yaml": "https://huggingface.co/datasets/ScaleAI/SWE-Atlas-QnA/resolve/main/default_qa_config.yaml",
        "rubric_evaluation_config.yaml": "https://huggingface.co/datasets/ScaleAI/SWE-Atlas-QnA/resolve/main/rubric_evaluation_config.yaml",
        "data/test-00000-of-00001.parquet": "https://huggingface.co/datasets/ScaleAI/SWE-Atlas-QnA/resolve/main/data/test-00000-of-00001.parquet",
    },
    "swe-bench-pro": {
        "README.md": "https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro/resolve/main/README.md",
        "data/test-00000-of-00001.parquet": "https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro/resolve/main/data/test-00000-of-00001.parquet",
    },
}


def download(url: str, dest: Path) -> dict[str, object]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    request = urllib.request.Request(url, headers={"User-Agent": "harness-evaluation/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        tmp.write_bytes(response.read())
    tmp.replace(dest)
    return {"path": str(dest.relative_to(DATASETS)), "bytes": dest.stat().st_size, "url": url}


def main() -> int:
    fetched: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for dataset_id, files in DOWNLOADS.items():
        dataset_root = DATASETS / dataset_id
        for rel_path, url in files.items():
            try:
                fetched.append(download(url, dataset_root / rel_path))
            except Exception as exc:
                errors.append({"dataset": dataset_id, "path": rel_path, "url": url, "error": str(exc)})

    out = {"fetched": fetched, "errors": errors}
    (DATASETS / "sync-report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
