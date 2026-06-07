from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_evaluation.checkers import run_checker
from harness_evaluation.runner_profiles import (
    RunnerProfileError,
    load_runner_profile,
    render_command,
    render_template,
    validate_runner_profile,
)


USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "cost_usd",
)
METRIC_FIELDS = (
    "tool_calls",
    "failed_tool_calls",
    "safety_violations",
    "human_interventions",
)


class RunnerError(ValueError):
    """Raised when a suite or task cannot be run safely."""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_task_id(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in (".", "..")
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise RunnerError("task_id must be a safe non-empty filename component")
    return value


def _inside(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _safe_relative(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RunnerError(f"{field} must be a safe relative path")
    return path


def _assert_no_symlinks(path: Path) -> None:
    if path.is_symlink():
        raise RunnerError(f"workspace source may not be a symbolic link: {path}")
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_symlink():
                raise RunnerError(f"workspace source may not contain symbolic links: {child}")


def _copy_workspace(task: dict[str, Any], dataset_root: Path, workspace_dir: Path) -> None:
    workspace = task.get("workspace", {})
    if workspace is None:
        workspace = {}
    if not isinstance(workspace, dict):
        raise RunnerError("task workspace must be an object")
    files = workspace.get("files", [])
    if not isinstance(files, list):
        raise RunnerError("task workspace.files must be a list")

    dataset_root = dataset_root.resolve()
    for index, item in enumerate(files):
        if isinstance(item, str):
            source_rel = _safe_relative(item, field=f"workspace.files.{index}")
            destination_rel = Path(source_rel.name)
        elif isinstance(item, dict):
            source_rel = _safe_relative(item.get("source"), field=f"workspace.files.{index}.source")
            destination_rel = _safe_relative(
                item.get("destination", source_rel.name),
                field=f"workspace.files.{index}.destination",
            )
        else:
            raise RunnerError(f"workspace.files.{index} must be a string or object")

        source = (dataset_root / source_rel).resolve()
        if not _inside(source, dataset_root) or not source.exists():
            raise RunnerError(f"workspace source not found inside dataset root: {source_rel.as_posix()}")
        _assert_no_symlinks(source)
        destination = workspace_dir / destination_rel
        if not _inside(destination, workspace_dir):
            raise RunnerError(f"workspace destination escapes workspace: {destination_rel.as_posix()}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, destination)
        else:
            raise RunnerError(f"workspace source is not a regular file or directory: {source_rel.as_posix()}")


def _capture_path(task_run_dir: Path, capture: dict[str, Any], stream: str) -> Path | None:
    value = capture.get(stream, True)
    if value is False:
        return None
    relative = f"{stream}.log" if value is True else value
    path = task_run_dir / _safe_relative(relative, field=f"capture.{stream}")
    if not _inside(path, task_run_dir):
        raise RunnerError(f"capture.{stream} escapes the task run directory")
    return path


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _matches(path: Path, workspace_dir: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(workspace_dir).as_posix()
    return any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def _collect_artifacts(
    profile: dict[str, Any],
    workspace_dir: Path,
    task_run_dir: Path,
    run_dir: Path,
) -> tuple[dict[str, Any], list[str]]:
    config = profile.get("artifacts", {})
    globs = config.get("glob", [])
    excludes = config.get("exclude", [])
    globs = [globs] if isinstance(globs, str) else globs
    excludes = [excludes] if isinstance(excludes, str) else excludes
    seen: set[Path] = set()
    files: list[dict[str, Any]] = []
    source_files: list[str] = []
    for pattern in globs:
        for path in sorted(workspace_dir.glob(pattern)):
            if not path.is_file() or path.is_symlink() or path in seen or _matches(path, workspace_dir, excludes):
                continue
            resolved = path.resolve()
            if not _inside(resolved, workspace_dir):
                continue
            seen.add(path)
            relative = path.relative_to(workspace_dir)
            destination = task_run_dir / "artifacts" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            run_relative = _relative(destination, run_dir)
            files.append(
                {
                    "path": run_relative,
                    "workspace_path": relative.as_posix(),
                    "bytes": destination.stat().st_size,
                }
            )
            source_files.append(run_relative)
    return {"files": files}, source_files


def _empty_usage() -> dict[str, None]:
    return {field: None for field in USAGE_FIELDS}


def _empty_metrics() -> dict[str, None]:
    return {field: None for field in METRIC_FIELDS}


def _normalize_run_metadata(
    run_metadata: dict[str, Any],
    *,
    dataset_id: str,
    profile: dict[str, Any],
    dataset_jsonl: Path | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metadata: dict[str, Any] = {}
    for field in ("run_id", "system", "harness", "model"):
        value = run_metadata.get(field)
        metadata[field] = value if isinstance(value, str) and value else "unknown"
    metadata["dataset_id"] = (
        run_metadata["dataset_id"]
        if isinstance(run_metadata.get("dataset_id"), str) and run_metadata["dataset_id"]
        else dataset_id or "unknown"
    )
    for field, fallback in (
        ("dataset_version", "unknown"),
        ("code_commit", "unknown"),
        ("created_at", now),
    ):
        value = run_metadata.get(field)
        metadata[field] = value if isinstance(value, str) and value else fallback
    run_config = run_metadata.get("run_config")
    metadata["run_config"] = dict(run_config) if isinstance(run_config, dict) else {}
    metadata["run_config"].update(
        {
            "runner_profile_id": profile["id"],
            "dry_run": bool(run_metadata.get("dry_run", False)),
            "continue_on_error": bool(run_metadata.get("continue_on_error", False)),
        }
    )
    if dataset_jsonl is not None:
        metadata["run_config"]["dataset_jsonl"] = str(dataset_jsonl)
    return metadata


def _task_result(
    *,
    task: dict[str, Any],
    checker: dict[str, Any],
    elapsed_sec: float,
    exit_code: int | None,
    error_type: str | None,
    error_message: str | None,
    artifacts: dict[str, Any],
    source_files: list[str],
    command: list[str],
    profile_id: str,
) -> dict[str, Any]:
    metadata = task.get("metadata")
    result_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    result_metadata["runner_profile_id"] = profile_id
    success = checker["success"] and error_type is None
    score = checker["score"] if error_type is None else 0.0
    return {
        "task_id": task["task_id"],
        "score": score,
        "success": success,
        "error_type": error_type or checker.get("error_type"),
        "error_message": error_message or checker.get("error_message"),
        "exit_code": exit_code,
        "elapsed_sec": round(elapsed_sec, 6),
        "usage": _empty_usage(),
        "metrics": _empty_metrics(),
        "artifacts": artifacts,
        "metadata": result_metadata,
        "raw": {
            "source_files": sorted(set(source_files)),
            "command": command,
        },
        "checks": checker["checks"],
    }


def run_task(
    task: dict[str, Any],
    runner_profile: dict[str, Any],
    run_dir: Path | str,
    dataset_root: Path | str,
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    profile = validate_runner_profile(runner_profile)
    if not isinstance(task, dict):
        raise RunnerError("task must be an object")
    task_id = _safe_task_id(task.get("task_id"))
    prompt = task.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise RunnerError(f"{task_id}: prompt must be a non-empty string")
    task = dict(task)
    task["task_id"] = task_id

    run_dir = Path(run_dir).resolve()
    dataset_root = Path(dataset_root).resolve()
    tasks_dir = run_dir / "tasks"
    results_dir = run_dir / "results"
    task_run_dir = tasks_dir / task_id
    if task_run_dir.exists():
        shutil.rmtree(task_run_dir)
    workspace_dir = task_run_dir / "workspace"
    workspace_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_metadata_path = run_dir / "run.json"
    if not run_metadata_path.is_file():
        _write_json(
            run_metadata_path,
            _normalize_run_metadata(
                run_metadata,
                dataset_id=dataset_root.name,
                profile=profile,
            ),
        )

    prompt_file = task_run_dir / "prompt.txt"
    task_json = task_run_dir / "task.json"
    prompt_file.write_text(prompt, encoding="utf-8")
    _write_json(task_json, task)

    variables = {
        "prompt": prompt,
        "prompt_file": str(prompt_file),
        "task_id": task_id,
        "task_json": str(task_json),
        "workspace_dir": str(workspace_dir),
        "task_run_dir": str(task_run_dir),
        "output_dir": str(run_dir),
    }
    command = render_command(profile, variables)
    rendered_cwd = Path(render_template(profile.get("cwd", "{{workspace_dir}}"), variables))
    cwd = rendered_cwd if rendered_cwd.is_absolute() else task_run_dir / rendered_cwd
    cwd = cwd.resolve()
    if not _inside(cwd, task_run_dir):
        raise RunnerError(f"{task_id}: runner cwd must be inside the per-task run directory")
    env = {key: render_template(value, variables) for key, value in profile.get("env", {}).items()}
    timeout = float(profile.get("timeout_sec", 300))
    capture = profile.get("capture", {})
    stdout_path = _capture_path(task_run_dir, capture, "stdout")
    stderr_path = _capture_path(task_run_dir, capture, "stderr")

    _copy_workspace(task, dataset_root, workspace_dir)
    cwd.mkdir(parents=True, exist_ok=True)
    command_record = {
        "command": command,
        "cwd": str(cwd),
        "timeout_sec": timeout,
        "env_keys": sorted(env),
        "dry_run": bool(run_metadata.get("dry_run", False)),
    }
    command_path = task_run_dir / "command.json"
    _write_json(command_path, command_record)
    source_files = [
        _relative(command_path, run_dir),
        _relative(prompt_file, run_dir),
        _relative(task_json, run_dir),
    ]

    start = time.monotonic()
    exit_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    stdout = ""
    stderr = ""
    dry_run = bool(run_metadata.get("dry_run", False))
    if dry_run:
        error_type = "dry_run"
        error_message = "command was rendered but not executed"
    else:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            if exit_code != 0:
                error_type = "subprocess_exit"
                error_message = f"runner exited with code {exit_code}"
        except subprocess.TimeoutExpired as exc:
            stdout = _text(exc.stdout)
            stderr = _text(exc.stderr)
            error_type = "timeout"
            error_message = f"runner timed out after {timeout:g} seconds"
        except OSError as exc:
            error_type = "runner_execution"
            error_message = str(exc)
    elapsed_sec = time.monotonic() - start
    command_record.update(
        {
            "exit_code": exit_code,
            "elapsed_sec": round(elapsed_sec, 6),
            "error_type": error_type,
            "error_message": error_message,
        }
    )
    _write_json(command_path, command_record)

    for path, content in ((stdout_path, stdout), (stderr_path, stderr)):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            source_files.append(_relative(path, run_dir))

    checker = run_checker(task.get("checker"), workspace_dir) if not dry_run else {
        "score": 0.0,
        "success": False,
        "checks": [],
        "error_type": None,
        "error_message": None,
    }
    artifacts, artifact_sources = _collect_artifacts(profile, workspace_dir, task_run_dir, run_dir)
    source_files.extend(artifact_sources)
    result = _task_result(
        task=task,
        checker=checker,
        elapsed_sec=elapsed_sec,
        exit_code=exit_code,
        error_type=error_type,
        error_message=error_message,
        artifacts=artifacts,
        source_files=source_files,
        command=command,
        profile_id=profile["id"],
    )
    _write_json(results_dir / f"{task_id}.json", result)
    return result


def _read_dataset(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RunnerError(f"cannot read dataset JSONL {path}: {exc}") from exc
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunnerError(f"{path}: line {line_no}: invalid JSON: {exc}") from exc
        if not isinstance(task, dict):
            raise RunnerError(f"{path}: line {line_no}: expected JSON object")
        task_id = _safe_task_id(task.get("task_id"))
        if task_id in seen:
            raise RunnerError(f"{path}: duplicate task_id: {task_id}")
        seen.add(task_id)
        tasks.append(task)
    return tasks


def _dataset_identity(dataset_jsonl: Path) -> tuple[str, str]:
    dataset_root = dataset_jsonl.parent.parent
    manifest_path = dataset_root / "dataset.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    dataset_id = manifest.get("id") if isinstance(manifest, dict) else None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return (
        dataset_id if isinstance(dataset_id, str) and dataset_id else dataset_root.name,
        version if isinstance(version, str) and version else "unknown",
    )


def run_suite(
    dataset_jsonl: Path | str,
    runner_profile: dict[str, Any] | Path | str,
    output_dir: Path | str,
    run_metadata: dict[str, Any],
    max_tasks: int | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    dataset_jsonl = Path(dataset_jsonl).resolve()
    output_dir = Path(output_dir).resolve()
    if max_tasks is not None and (
        not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or max_tasks <= 0
    ):
        raise RunnerError("max_tasks must be a positive integer")
    if isinstance(runner_profile, dict):
        profile = validate_runner_profile(runner_profile)
    else:
        try:
            profile = load_runner_profile(runner_profile)
        except RunnerProfileError as exc:
            raise RunnerError(str(exc)) from exc

    tasks = _read_dataset(dataset_jsonl)
    if task_id is not None:
        task_id = _safe_task_id(task_id)
        tasks = [task for task in tasks if task.get("task_id") == task_id]
        if not tasks:
            raise RunnerError(f"task_id not found in dataset: {task_id}")
    if max_tasks is not None:
        tasks = tasks[:max_tasks]

    dataset_id, dataset_version = _dataset_identity(dataset_jsonl)
    metadata_input = dict(run_metadata)
    if not isinstance(metadata_input.get("dataset_version"), str) or not metadata_input["dataset_version"]:
        metadata_input["dataset_version"] = dataset_version
    metadata = _normalize_run_metadata(
        metadata_input,
        dataset_id=dataset_id,
        profile=profile,
        dataset_jsonl=dataset_jsonl,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = output_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    results_dir = output_dir / "results"
    results_dir.mkdir(exist_ok=True)
    for stale_result in results_dir.glob("*.json"):
        stale_result.unlink()
    _write_json(output_dir / "run.json", metadata)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for task in tasks:
        current_id = str(task.get("task_id"))
        try:
            result = run_task(task, profile, output_dir, dataset_jsonl.parent.parent, metadata_input)
        except (OSError, RunnerError, RunnerProfileError) as exc:
            errors.append({"task_id": current_id, "error": str(exc)})
            if not metadata["run_config"]["continue_on_error"]:
                break
            continue
        results.append(result)
        if result.get("error_type") not in (None, "dry_run") and not metadata["run_config"]["continue_on_error"]:
            break

    return {
        "run_id": metadata["run_id"],
        "runner_profile_id": profile["id"],
        "dataset_jsonl": str(dataset_jsonl),
        "output_dir": str(output_dir),
        "tasks_selected": len(tasks),
        "tasks_completed": len(results),
        "successful_tasks": sum(result.get("success") is True for result in results),
        "failed_tasks": sum(result.get("success") is False for result in results),
        "dry_run": metadata["run_config"]["dry_run"],
        "commands": [
            {"task_id": result["task_id"], "command": result["raw"]["command"]}
            for result in results
        ],
        "errors": errors,
    }
