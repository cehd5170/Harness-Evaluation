from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProfileError(ValueError):
    """Raised when an ingestion profile is missing or invalid."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"cannot read profile {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"invalid profile JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"expected profile JSON object: {path}")
    return value


def _path_list(value: Any, *, field: str) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise ProfileError(f"profile {field} must be a dotted path or non-empty list of dotted paths")


def _validate_profile(profile: dict[str, Any], path: Path) -> None:
    profile_id = profile.get("id")
    if not isinstance(profile_id, str) or not profile_id:
        raise ProfileError(f"{path}: id must be a non-empty string")

    input_config = profile.get("input")
    if not isinstance(input_config, dict):
        raise ProfileError(f"{path}: input must be an object")
    layout = input_config.get("layout")
    if layout not in ("flat-json", "task-dir"):
        raise ProfileError(f"{path}: input.layout must be flat-json or task-dir")
    if layout == "flat-json":
        if not isinstance(input_config.get("glob"), str) or not input_config["glob"]:
            raise ProfileError(f"{path}: flat-json input.glob must be a non-empty string")
    else:
        for field in ("task_glob", "result_file"):
            if not isinstance(input_config.get(field), str) or not input_config[field]:
                raise ProfileError(f"{path}: task-dir input.{field} must be a non-empty string")
    exclude = input_config.get("exclude", [])
    if not isinstance(exclude, (str, list)) or (
        isinstance(exclude, list) and not all(isinstance(item, str) for item in exclude)
    ):
        raise ProfileError(f"{path}: input.exclude must be a string or list of strings")

    fields = profile.get("fields")
    if not isinstance(fields, dict) or "task_id" not in fields:
        raise ProfileError(f"{path}: fields must be an object containing task_id")
    for destination, paths in fields.items():
        if not isinstance(destination, str) or not destination:
            raise ProfileError(f"{path}: canonical field destinations must be non-empty strings")
        _path_list(paths, field=f"fields.{destination}")

    metrics = profile.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ProfileError(f"{path}: metrics must be an object")
    for name, spec in metrics.items():
        if isinstance(spec, (str, list)):
            _path_list(spec, field=f"metrics.{name}")
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("count_events"), dict):
            raise ProfileError(f"{path}: metrics.{name} must be paths or a count_events object")
        counter = spec["count_events"]
        if not isinstance(counter.get("path"), str) or not counter["path"]:
            raise ProfileError(f"{path}: metrics.{name}.count_events.path must be a non-empty string")
        if "where" in counter and not isinstance(counter["where"], dict):
            raise ProfileError(f"{path}: metrics.{name}.count_events.where must be an object")

    usage = profile.get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            raise ProfileError(f"{path}: usage must be an object")
        if usage.get("parser", "usage-summary") != "usage-summary":
            raise ProfileError(f"{path}: usage.parser must be usage-summary")
        if usage.get("source", "record") not in ("record", "usage-file"):
            raise ProfileError(f"{path}: usage.source must be record or usage-file")
        if usage.get("source") == "usage-file" and not isinstance(input_config.get("usage_file"), str):
            raise ProfileError(f"{path}: usage-file source requires input.usage_file")


def load_profile(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    profile = _read_object(path)
    _validate_profile(profile, path)
    return profile


def dotted_get(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                return None
        return None
    return current


def first_value(value: Any, paths: str | list[str]) -> Any:
    for path in _path_list(paths, field="mapping"):
        found = dotted_get(value, path)
        if found is not None:
            return found
    return None


def dotted_set(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value
