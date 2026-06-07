from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUN_FIELDS = (
    "run_id",
    "system",
    "harness",
    "model",
    "dataset_id",
    "dataset_version",
    "code_commit",
    "created_at",
    "run_config",
)


class CanonicalFormatError(ValueError):
    """Raised when a canonical run does not match the expected layout."""


@dataclass(frozen=True)
class CanonicalRun:
    run_dir: Path
    metadata: dict[str, Any]
    results: dict[str, dict[str, Any]]


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CanonicalFormatError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CanonicalFormatError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CanonicalFormatError(f"expected JSON object: {path}")
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_run_metadata(metadata: dict[str, Any], path: Path) -> None:
    missing = [field for field in RUN_FIELDS if field not in metadata]
    if missing:
        raise CanonicalFormatError(f"{path}: missing required field(s): {', '.join(missing)}")
    for field in RUN_FIELDS[:-1]:
        if not isinstance(metadata[field], str) or not metadata[field].strip():
            raise CanonicalFormatError(f"{path}: {field} must be a non-empty string")
    if not isinstance(metadata["run_config"], dict):
        raise CanonicalFormatError(f"{path}: run_config must be an object")


def _validate_result(result: dict[str, Any], path: Path) -> str:
    task_id = result.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise CanonicalFormatError(f"{path}: task_id must be a non-empty string")
    if task_id != path.stem:
        raise CanonicalFormatError(f"{path}: task_id must match the result filename")
    if "score" not in result and "success" not in result:
        raise CanonicalFormatError(f"{path}: expected score or success")
    if "score" in result and not _is_number(result["score"]):
        raise CanonicalFormatError(f"{path}: score must be a finite number")
    if "success" in result and not isinstance(result["success"], bool):
        raise CanonicalFormatError(f"{path}: success must be a boolean")
    for field in ("usage", "metrics", "artifacts", "metadata", "raw"):
        if field in result and not isinstance(result[field], dict):
            raise CanonicalFormatError(f"{path}: {field} must be an object")
    if "checks" in result and not isinstance(result["checks"], list):
        raise CanonicalFormatError(f"{path}: checks must be a list")
    raw = result.get("raw")
    if isinstance(raw, dict) and "source_files" in raw:
        source_files = raw["source_files"]
        if not isinstance(source_files, list) or not all(isinstance(item, str) for item in source_files):
            raise CanonicalFormatError(f"{path}: raw.source_files must be a list of strings")
    return task_id


def result_score(result: dict[str, Any]) -> float | None:
    score = result.get("score")
    if _is_number(score):
        return float(score)
    success = result.get("success")
    if isinstance(success, bool):
        return 1.0 if success else 0.0
    return None


def load_run(run_dir: Path | str) -> CanonicalRun:
    run_dir = Path(run_dir)
    metadata_path = run_dir / "run.json"
    results_dir = run_dir / "results"
    if not run_dir.is_dir():
        raise CanonicalFormatError(f"run directory not found: {run_dir}")
    if not metadata_path.is_file():
        raise CanonicalFormatError(f"run metadata not found: {metadata_path}")
    if not results_dir.is_dir():
        raise CanonicalFormatError(f"results directory not found: {results_dir}")

    metadata = _read_object(metadata_path)
    _validate_run_metadata(metadata, metadata_path)

    results: dict[str, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        result = _read_object(path)
        task_id = _validate_result(result, path)
        if task_id in results:
            raise CanonicalFormatError(f"{path}: duplicate task_id: {task_id}")
        results[task_id] = result
    return CanonicalRun(run_dir=run_dir, metadata=metadata, results=results)
