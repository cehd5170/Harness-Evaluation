from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


TEMPLATE_VARIABLES = {
    "prompt",
    "prompt_file",
    "task_id",
    "task_json",
    "workspace_dir",
    "task_run_dir",
    "output_dir",
}
_TEMPLATE_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


class RunnerProfileError(ValueError):
    """Raised when a runner profile is missing or invalid."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunnerProfileError(f"cannot read runner profile {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerProfileError(f"invalid runner profile JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerProfileError(f"expected runner profile JSON object: {path}")
    return value


def _string_list(value: Any, *, field: str, allow_string: bool = False) -> list[str]:
    if allow_string and isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    suffix = "string or list of strings" if allow_string else "list of strings"
    raise RunnerProfileError(f"runner profile {field} must be a {suffix}")


def _validate_template(value: str, *, field: str) -> None:
    unknown = sorted(set(_TEMPLATE_RE.findall(value)) - TEMPLATE_VARIABLES)
    if unknown:
        raise RunnerProfileError(
            f"runner profile {field} uses unsupported template variable(s): {', '.join(unknown)}"
        )
    remaining = _TEMPLATE_RE.sub("", value)
    if "{{" in remaining or "}}" in remaining:
        raise RunnerProfileError(f"runner profile {field} contains a malformed template variable")


def _validate_profile(profile: dict[str, Any], path: Path) -> None:
    profile_id = profile.get("id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise RunnerProfileError(f"{path}: id must be a non-empty string")
    if profile.get("type") != "subprocess":
        raise RunnerProfileError(f"{path}: type must be subprocess")

    command = _string_list(profile.get("command"), field="command")
    if not command:
        raise RunnerProfileError(f"{path}: command must not be empty")
    for index, item in enumerate(command):
        _validate_template(item, field=f"command.{index}")

    cwd = profile.get("cwd", "{{workspace_dir}}")
    if not isinstance(cwd, str) or not cwd:
        raise RunnerProfileError(f"{path}: cwd must be a non-empty string")
    _validate_template(cwd, field="cwd")

    timeout = profile.get("timeout_sec", 300)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise RunnerProfileError(f"{path}: timeout_sec must be a positive number")

    env = profile.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str)
        for key, value in env.items()
    ):
        raise RunnerProfileError(f"{path}: env must be an object of string values")
    for key, value in env.items():
        _validate_template(value, field=f"env.{key}")

    capture = profile.get("capture", {})
    if not isinstance(capture, dict):
        raise RunnerProfileError(f"{path}: capture must be an object")
    for stream in ("stdout", "stderr"):
        value = capture.get(stream, True)
        if not isinstance(value, (bool, str)) or isinstance(value, str) and not value:
            raise RunnerProfileError(f"{path}: capture.{stream} must be a boolean or non-empty path")

    artifacts = profile.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise RunnerProfileError(f"{path}: artifacts must be an object")
    for field in ("glob", "exclude"):
        value = artifacts.get(field, [])
        patterns = _string_list(value, field=f"artifacts.{field}", allow_string=True)
        if any(Path(pattern).is_absolute() or ".." in Path(pattern).parts for pattern in patterns):
            raise RunnerProfileError(f"{path}: artifacts.{field} patterns must be relative")


def load_runner_profile(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    profile = _read_object(path)
    _validate_profile(profile, path)
    return profile


def validate_runner_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise RunnerProfileError("runner profile must be an object")
    _validate_profile(profile, Path("<runner-profile>"))
    return profile


def render_template(value: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in TEMPLATE_VARIABLES:
            raise RunnerProfileError(f"unsupported template variable: {name}")
        return variables[name]

    return _TEMPLATE_RE.sub(replace, value)


def render_command(profile: dict[str, Any], variables: dict[str, str]) -> list[str]:
    return [render_template(item, variables) for item in profile["command"]]
