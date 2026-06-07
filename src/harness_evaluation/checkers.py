from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any


class CheckerError(ValueError):
    """Raised when a deterministic checker configuration is invalid."""


def _result(
    checks: list[dict[str, Any]],
    *,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    score = round(sum(bool(check.get("success")) for check in checks) / len(checks), 6) if checks else 0.0
    return {
        "score": score,
        "success": bool(checks) and all(bool(check.get("success")) for check in checks),
        "checks": checks,
        "error_type": error_type,
        "error_message": error_message,
    }


def _safe_path(workspace_dir: Path, value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise CheckerError(f"{field} must be a safe relative path")
    workspace = workspace_dir.resolve()
    path = (workspace / value).resolve()
    if path != workspace and workspace not in path.parents:
        raise CheckerError(f"{field} escapes the task workspace")
    return path


def _dotted_get(value: Any, path: str) -> tuple[bool, Any]:
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
                return False, None
        return False, None
    return True, current


def _artifact_checker(config: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    expected = config.get("expected_files", [])
    if not isinstance(expected, list) or not all(isinstance(item, str) and item for item in expected):
        raise CheckerError("artifact checker expected_files must be a list of relative paths")
    required_text = config.get("required_text", {})
    if not isinstance(required_text, (str, list, dict)):
        raise CheckerError("artifact checker required_text must be text, a list, or a file mapping")

    checks: list[dict[str, Any]] = []
    for relative in expected:
        path = _safe_path(workspace_dir, relative, field="expected_files")
        checks.append(
            {
                "name": f"file:{relative}",
                "success": path.is_file(),
                "path": relative,
            }
        )
    mapped_text = required_text if isinstance(required_text, dict) else {}
    for relative, values in mapped_text.items():
        path = _safe_path(workspace_dir, relative, field="required_text")
        texts = [values] if isinstance(values, str) else values
        if not isinstance(texts, list) or not all(isinstance(item, str) for item in texts):
            raise CheckerError("artifact checker required_text values must be strings or lists of strings")
        try:
            content = path.read_text(encoding="utf-8")
            read_error = None
        except (OSError, UnicodeError) as exc:
            content = ""
            read_error = str(exc)
        for text in texts:
            check = {
                "name": f"text:{relative}:{text}",
                "success": read_error is None and text in content,
                "path": relative,
                "required_text": text,
            }
            if read_error:
                check["message"] = read_error
            checks.append(check)
    if isinstance(required_text, (str, list)):
        texts = [required_text] if isinstance(required_text, str) else required_text
        if not all(isinstance(item, str) for item in texts):
            raise CheckerError("artifact checker required_text list entries must be strings")
        contents: list[str] = []
        read_errors: list[str] = []
        for relative in expected:
            path = _safe_path(workspace_dir, relative, field="expected_files")
            try:
                contents.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as exc:
                read_errors.append(f"{relative}: {exc}")
        combined = "\n".join(contents)
        for text in texts:
            check = {
                "name": f"text:{text}",
                "success": text in combined,
                "required_text": text,
            }
            if read_errors:
                check["message"] = "; ".join(read_errors)
            checks.append(check)
    if not checks:
        raise CheckerError("artifact checker requires expected_files or required_text")
    return _result(checks)


def _command_checker(config: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    command = config.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise CheckerError("command checker command must be a non-empty list of strings")
    timeout = config.get("timeout_sec", 60)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise CheckerError("command checker timeout_sec must be a positive number")
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_dir,
            env={},
            capture_output=True,
            text=True,
            timeout=float(timeout),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _result(
            [{"name": "command", "success": False, "command": command, "timed_out": True}],
            error_type="checker_timeout",
            error_message=f"checker timed out after {timeout} seconds",
        )
    except OSError as exc:
        return _result(
            [{"name": "command", "success": False, "command": command}],
            error_type="checker_execution",
            error_message=str(exc),
        )
    return _result(
        [
            {
                "name": "command",
                "success": completed.returncode == 0,
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        ]
    )


def _json_checker(config: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    path = _safe_path(workspace_dir, config.get("file"), field="json checker file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return _result(
            [{"name": f"json:{config.get('file')}", "success": False, "message": str(exc)}]
        )
    except json.JSONDecodeError as exc:
        return _result(
            [{"name": f"json:{config.get('file')}", "success": False, "message": str(exc)}]
        )

    required = config.get("required_fields", [])
    expected = config.get("expected_values", {})
    if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
        raise CheckerError("json checker required_fields must be a list of dotted paths")
    if not isinstance(expected, dict) or not all(isinstance(key, str) and key for key in expected):
        raise CheckerError("json checker expected_values must be an object keyed by dotted paths")
    checks: list[dict[str, Any]] = []
    for field in required:
        found, actual = _dotted_get(value, field)
        checks.append({"name": f"field:{field}", "success": found, "field": field, "actual": actual})
    for field, expected_value in expected.items():
        found, actual = _dotted_get(value, field)
        checks.append(
            {
                "name": f"value:{field}",
                "success": found and actual == expected_value,
                "field": field,
                "expected": expected_value,
                "actual": actual,
            }
        )
    if not checks:
        raise CheckerError("json checker requires required_fields or expected_values")
    return _result(checks)


def run_checker(config: dict[str, Any] | None, workspace_dir: Path | str) -> dict[str, Any]:
    if config is None:
        return {
            "score": 1.0,
            "success": True,
            "checks": [],
            "error_type": None,
            "error_message": None,
        }
    if not isinstance(config, dict):
        return _result([], error_type="checker_config", error_message="checker must be an object")
    checker_type = config.get("type")
    try:
        if checker_type == "artifact":
            return _artifact_checker(config, Path(workspace_dir))
        if checker_type == "command":
            return _command_checker(config, Path(workspace_dir))
        if checker_type == "json":
            return _json_checker(config, Path(workspace_dir))
        raise CheckerError("checker type must be artifact, command, or json")
    except CheckerError as exc:
        return _result([], error_type="checker_config", error_message=str(exc))
    except Exception as exc:
        return _result([], error_type="checker_execution", error_message=str(exc))
