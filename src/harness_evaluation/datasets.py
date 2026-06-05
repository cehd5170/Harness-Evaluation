from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dataset_root() -> Path:
    return Path(__file__).resolve().parents[2] / "datasets"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _iter_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return rows, [str(exc)]
    for line_no, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_no}: expected JSON object")
            continue
        rows.append(value)
    return rows, errors


def init_custom_dataset(dataset_id: str, *, root: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    root = root or dataset_root()
    safe_id = dataset_id.strip().replace("/", "-")
    if not safe_id:
        raise ValueError("dataset_id is required")
    dataset_dir = root / safe_id
    data_dir = dataset_dir / "data"
    manifest_path = dataset_dir / "dataset.json"
    jsonl_path = data_dir / "test.jsonl"
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(f"dataset already exists: {manifest_path}")

    data_dir.mkdir(parents=True, exist_ok=True)
    if not jsonl_path.exists() or overwrite:
        jsonl_path.write_text(
            json.dumps(
                {
                    "task_id": "example-001",
                    "prompt": "Edit or replace this example prompt.",
                    "reference_answer": "Optional expected answer or grading reference.",
                    "metadata": {"source": "custom"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    manifest = {
        "id": safe_id,
        "name": safe_id,
        "aa_component": "custom",
        "public": False,
        "schema": "custom-jsonl-v1",
        "local_files": ["data/test.jsonl"],
        "required_fields": ["task_id", "prompt"],
        "notes": "Custom JSONL dataset. One JSON object per line.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"dataset_dir": str(dataset_dir), "manifest": str(manifest_path), "data_file": str(jsonl_path)}


def validate_dataset(dataset_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or dataset_root()
    dataset_dir = root / dataset_id
    manifest_path = dataset_dir / "dataset.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        return {"ok": False, "dataset_id": dataset_id, "errors": [f"missing or invalid manifest: {manifest_path}"]}

    required_fields = manifest.get("required_fields")
    if not isinstance(required_fields, list):
        required_fields = ["task_id", "prompt"]

    errors: list[str] = []
    warnings: list[str] = []
    files: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    row_count = 0

    local_files = manifest.get("local_files", [])
    if not isinstance(local_files, list):
        errors.append("manifest local_files must be a list")
        local_files = []
    jsonl_files = [str(item) for item in local_files if str(item).endswith(".jsonl")]
    if not jsonl_files:
        warnings.append("no JSONL files listed in local_files")

    for rel_path in jsonl_files:
        path = dataset_dir / rel_path
        if not path.is_file():
            errors.append(f"missing data file: {rel_path}")
            files.append({"path": rel_path, "exists": False})
            continue
        rows, parse_errors = _iter_jsonl(path)
        errors.extend(f"{rel_path}: {msg}" for msg in parse_errors)
        missing_count = 0
        duplicate_count = 0
        for row in rows:
            row_count += 1
            for field in required_fields:
                if field not in row or row.get(field) in ("", None):
                    missing_count += 1
            task_id = str(row.get("task_id") or "").strip()
            if task_id:
                if task_id in seen_task_ids:
                    duplicate_count += 1
                seen_task_ids.add(task_id)
        if missing_count:
            errors.append(f"{rel_path}: {missing_count} missing required field occurrence(s)")
        if duplicate_count:
            errors.append(f"{rel_path}: {duplicate_count} duplicate task_id occurrence(s)")
        files.append({"path": rel_path, "exists": True, "rows": len(rows), "bytes": path.stat().st_size})

    return {
        "ok": not errors,
        "dataset_id": dataset_id,
        "manifest": str(manifest_path),
        "row_count": row_count,
        "unique_task_ids": len(seen_task_ids),
        "required_fields": required_fields,
        "files": files,
        "warnings": warnings,
        "errors": errors,
    }


def sample_dataset(dataset_id: str, *, root: Path | None = None, limit: int = 3) -> dict[str, Any]:
    root = root or dataset_root()
    dataset_dir = root / dataset_id
    manifest = _read_json(dataset_dir / "dataset.json")
    samples: list[dict[str, Any]] = []
    for rel_path in manifest.get("local_files", []):
        if not str(rel_path).endswith(".jsonl"):
            continue
        rows, _ = _iter_jsonl(dataset_dir / str(rel_path))
        for row in rows:
            samples.append(row)
            if len(samples) >= limit:
                return {"dataset_id": dataset_id, "samples": samples}
    return {"dataset_id": dataset_id, "samples": samples}


def list_datasets(root: Path | None = None) -> dict[str, Any]:
    root = root or dataset_root()
    datasets: list[dict[str, Any]] = []
    for manifest in sorted(root.glob("*/dataset.json")):
        item = _read_json(manifest)
        local_files = []
        for rel_path in item.get("local_files", []):
            path = manifest.parent / str(rel_path)
            local_files.append(
                {
                    "path": str(path.relative_to(root)),
                    "exists": path.is_file(),
                    "bytes": path.stat().st_size if path.is_file() else None,
                }
            )
        item["local_files"] = local_files
        item["dataset_dir"] = str(manifest.parent.relative_to(root))
        datasets.append(item)
    return {"datasets_dir": str(root), "datasets": datasets}
