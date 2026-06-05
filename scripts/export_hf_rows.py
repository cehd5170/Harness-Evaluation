from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"

EXPORTS = {
    "swe-atlas-qna": {
        "hf_dataset": "ScaleAI/SWE-Atlas-QnA",
        "config": "default",
        "split": "test",
        "out": "data/test.jsonl",
    },
    "swe-bench-pro": {
        "hf_dataset": "ScaleAI/SWE-bench_Pro",
        "config": "default",
        "split": "test",
        "out": "data/test.jsonl",
    },
}


def fetch_page(dataset: str, config: str, split: str, offset: int, length: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    url = f"https://datasets-server.huggingface.co/rows?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "harness-evaluation/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected response for {dataset} offset={offset}")
    return payload


def export_dataset(dataset_id: str, spec: dict[str, str], page_size: int = 100) -> dict[str, Any]:
    out_path = DATASETS / dataset_id / spec["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total: int | None = None
    written = 0
    offset = 0
    with out_path.open("w", encoding="utf-8") as fh:
        while total is None or offset < total:
            page = fetch_page(spec["hf_dataset"], spec["config"], spec["split"], offset, page_size)
            rows = page.get("rows")
            if not isinstance(rows, list):
                raise RuntimeError(f"missing rows for {dataset_id} offset={offset}")
            total_raw = page.get("num_rows_total")
            if isinstance(total_raw, int):
                total = total_raw
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                row = item.get("row")
                if isinstance(row, dict):
                    row = {"_row_idx": item.get("row_idx"), **row}
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    written += 1
            offset += len(rows)
    return {
        "dataset": dataset_id,
        "rows": written,
        "path": str(out_path.relative_to(DATASETS)),
        "bytes": out_path.stat().st_size,
    }


def main() -> int:
    exports = [export_dataset(dataset_id, spec) for dataset_id, spec in EXPORTS.items()]
    report = {"exports": exports}
    (DATASETS / "export-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
