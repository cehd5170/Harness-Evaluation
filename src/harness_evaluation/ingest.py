from __future__ import annotations

import fnmatch
import json
import math
from pathlib import Path
from typing import Any, Iterable

from harness_evaluation.profiles import ProfileError, dotted_get, dotted_set, first_value, load_profile
from harness_evaluation.usage import summarize_usage_file, summarize_usage_text


CANONICAL_METRICS = (
    "tool_calls",
    "failed_tool_calls",
    "safety_violations",
    "human_interventions",
)
CANONICAL_USAGE = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "cost_usd",
)


class IngestError(ValueError):
    """Raised when a raw run cannot be ingested."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IngestError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IngestError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IngestError(f"expected JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise IngestError(f"cannot write {path}: {exc}") from exc


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return None


def _safe_task_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    task_id = value.strip()
    if (
        not task_id
        or task_id in (".", "..")
        or "/" in task_id
        or "\\" in task_id
        or Path(task_id).name != task_id
    ):
        return None
    return task_id


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _matches_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    relative = _relative(path, root)
    return any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def _event_count(record: dict[str, Any], counter: dict[str, Any]) -> int | None:
    events = dotted_get(record, counter["path"])
    if not isinstance(events, list):
        return None
    where = counter.get("where", {})
    return sum(
        1
        for event in events
        if isinstance(event, dict) and all(dotted_get(event, path) == expected for path, expected in where.items())
    )


def _canonical_usage(summary: dict[str, Any] | None) -> dict[str, Any]:
    usage = {field: None for field in CANONICAL_USAGE}
    if summary is None:
        return usage
    for field in CANONICAL_USAGE[:-1]:
        value = _number(summary.get(field))
        if value is not None:
            usage[field] = int(value)
    cost = _number(summary.get("cost_total") if "cost_total" in summary else summary.get("cost_usd"))
    if cost is not None and (summary.get("cost_available") or cost != 0):
        usage["cost_usd"] = round(cost, 8)
    return usage


def _usage_from_record(record: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_usage_text(
        json.dumps(record, ensure_ascii=False),
        source="record",
        include_cost_availability=True,
    )
    return _canonical_usage(summary)


def _usage_from_file(path: Path) -> dict[str, Any]:
    return _canonical_usage(summarize_usage_file(path, include_cost_availability=True))


def _empty_result(source_files: list[str]) -> dict[str, Any]:
    return {
        "error_type": None,
        "error_message": None,
        "elapsed_sec": None,
        "usage": {field: None for field in CANONICAL_USAGE},
        "metrics": {field: None for field in CANONICAL_METRICS},
        "artifacts": {},
        "metadata": {},
        "raw": {"source_files": source_files},
    }


def _convert_record(
    record: dict[str, Any],
    profile: dict[str, Any],
    *,
    source_files: list[str],
    usage_path: Path | None,
) -> tuple[dict[str, Any] | None, str | None]:
    result = _empty_result(source_files)
    for destination, paths in profile["fields"].items():
        value = first_value(record, paths)
        if value is not None:
            dotted_set(result, destination, value)

    task_id = _safe_task_id(result.get("task_id"))
    if task_id is None:
        return None, "missing task_id"
    result["task_id"] = task_id

    if "score" in result:
        score = _number(result["score"])
        if score is None:
            result.pop("score")
        else:
            result["score"] = score
    if "success" in result:
        success = _boolean(result["success"])
        if success is None:
            result.pop("success")
        else:
            result["success"] = success
    if "score" not in result and "success" not in result:
        return None, f"{result['task_id']}: missing score or success"

    elapsed = _number(result.get("elapsed_sec"))
    result["elapsed_sec"] = elapsed
    for name, spec in profile.get("metrics", {}).items():
        if isinstance(spec, dict):
            value = _event_count(record, spec["count_events"])
        else:
            value = _number(first_value(record, spec))
        if value is not None:
            result["metrics"][name] = int(value) if float(value).is_integer() else value

    usage_config = profile.get("usage")
    if usage_config:
        if usage_config.get("source", "record") == "usage-file":
            if usage_path is not None and usage_path.is_file():
                result["usage"] = _usage_from_file(usage_path)
        else:
            result["usage"] = _usage_from_record(record)

    for field in ("artifacts", "metadata"):
        if not isinstance(result.get(field), dict):
            result[field] = {"value": result[field]}
    return result, None


def _flat_records(
    input_dir: Path,
    profile: dict[str, Any],
) -> Iterable[tuple[dict[str, Any] | None, list[str], Path | None, str | None]]:
    input_config = profile["input"]
    exclude = input_config.get("exclude", [])
    if isinstance(exclude, str):
        exclude = [exclude]
    for path in sorted(input_dir.glob(input_config["glob"])):
        if not path.is_file() or _matches_exclude(path, input_dir, exclude):
            continue
        source_files = [_relative(path, input_dir)]
        try:
            record = _read_object(path)
        except IngestError as exc:
            yield None, source_files, None, str(exc)
            continue
        record["_source_stem"] = path.stem
        yield record, source_files, None, None


def _task_dir_records(
    input_dir: Path,
    profile: dict[str, Any],
) -> Iterable[tuple[dict[str, Any] | None, list[str], Path | None, str | None]]:
    input_config = profile["input"]
    exclude = input_config.get("exclude", [])
    if isinstance(exclude, str):
        exclude = [exclude]
    for task_dir in sorted(input_dir.glob(input_config["task_glob"])):
        if not task_dir.is_dir() or _matches_exclude(task_dir, input_dir, exclude):
            continue
        result_path = task_dir / input_config["result_file"]
        usage_path = task_dir / input_config["usage_file"] if input_config.get("usage_file") else None
        source_paths = [result_path]
        if usage_path is not None and usage_path.is_file():
            source_paths.append(usage_path)
        source_files = [_relative(path, input_dir) for path in source_paths]
        try:
            record = _read_object(result_path)
        except IngestError as exc:
            yield None, source_files, usage_path, str(exc)
            continue
        record["_task_dir_name"] = task_dir.name
        yield record, source_files, usage_path, None


def _run_metadata(input_dir: Path, overrides: dict[str, Any]) -> dict[str, Any]:
    source_path = input_dir / "run.json"
    source = _read_object(source_path) if source_path.is_file() else {}
    metadata: dict[str, Any] = {}
    for field in ("run_id", "system", "harness", "model", "dataset_id"):
        value = overrides.get(field)
        source_value = source.get(field)
        metadata[field] = (
            value
            if isinstance(value, str) and value
            else source_value
            if isinstance(source_value, str) and source_value
            else "unknown"
        )
    for field in ("dataset_version", "code_commit", "created_at"):
        value = overrides.get(field)
        source_value = source.get(field)
        metadata[field] = (
            value
            if isinstance(value, str) and value
            else source_value
            if isinstance(source_value, str) and source_value
            else "unknown"
        )
    run_config = source.get("run_config")
    metadata["run_config"] = run_config if isinstance(run_config, dict) else {}
    return metadata


def ingest_run(
    *,
    input_dir: Path | str,
    output_dir: Path | str,
    profile_path: Path | str,
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    if not input_dir.is_dir():
        raise IngestError(f"input directory not found: {input_dir}")
    try:
        profile = load_profile(profile_path)
    except ProfileError as exc:
        raise IngestError(str(exc)) from exc

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IngestError(f"cannot create output directory {output_dir}: {exc}") from exc
    results_dir = output_dir / "results"
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IngestError(f"cannot create results directory {results_dir}: {exc}") from exc
    for stale_result in results_dir.glob("*.json"):
        try:
            stale_result.unlink()
        except OSError as exc:
            raise IngestError(f"cannot remove stale result {stale_result}: {exc}") from exc

    metadata = _run_metadata(input_dir, run_metadata)
    _write_object(output_dir / "run.json", metadata)

    iterator = _flat_records if profile["input"]["layout"] == "flat-json" else _task_dir_records
    records_seen = 0
    records_written = 0
    warnings: list[str] = []
    seen_task_ids: set[str] = set()
    for record, source_files, usage_path, warning in iterator(input_dir, profile):
        records_seen += 1
        if warning:
            warnings.append(warning)
            continue
        assert record is not None
        usage_config = profile.get("usage", {})
        if usage_config.get("source") == "usage-file" and (usage_path is None or not usage_path.is_file()):
            warnings.append(f"{source_files[0]}: configured usage file not found")
        canonical, warning = _convert_record(
            record,
            profile,
            source_files=source_files,
            usage_path=usage_path,
        )
        if warning:
            warnings.append(f"{source_files[0]}: {warning}")
            continue
        assert canonical is not None
        task_id = canonical["task_id"]
        if task_id in seen_task_ids:
            warnings.append(f"{source_files[0]}: duplicate task_id: {task_id}")
            continue
        seen_task_ids.add(task_id)
        _write_object(results_dir / f"{task_id}.json", canonical)
        records_written += 1

    return {
        "profile_id": profile["id"],
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "run_id": metadata["run_id"],
        "records_seen": records_seen,
        "records_written": records_written,
        "records_skipped": records_seen - records_written,
        "warnings": warnings,
    }
