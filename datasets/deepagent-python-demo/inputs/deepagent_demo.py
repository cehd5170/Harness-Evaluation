from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_task(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_openai_api_key() -> str:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value

    codex_auth = Path.home() / ".codex" / "auth.json"
    if codex_auth.exists():
        try:
            data = json.loads(codex_auth.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            candidate = str(data.get("OPENAI_API_KEY", "")).strip()
            if candidate:
                return candidate
            tokens = data.get("tokens")
            if isinstance(tokens, dict):
                candidate = str(tokens.get("access_token", "")).strip()
                if candidate:
                    return candidate

    raise RuntimeError("OPENAI_API_KEY is required for real DeepAgent mode")


def _write_result(workspace_dir: Path, task_id: str, message: str) -> None:
    result_path = workspace_dir / "result.txt"
    result_path.write_text(f"{message}\n", encoding="utf-8")


def _run_fallback(workspace_dir: Path, task: dict[str, Any]) -> str:
    prompt = str(task.get("prompt", "")).strip()
    task_id = str(task.get("task_id", "unknown-task"))
    message = "deepagent python demo complete"
    _write_result(workspace_dir, task_id, message)
    print(f"[fallback] {task_id}: {prompt}")
    return message


def _run_real_deepagent(workspace_dir: Path, task: dict[str, Any]) -> str:
    try:
        from deepagents import create_deep_agent
    except ImportError as exc:
        raise RuntimeError(f"deepagents is not installed: {exc}") from exc

    model = os.environ.get("DEEPAGENT_MODEL", "openai:gpt-5.4-nano").strip()
    if not model:
        raise RuntimeError("DEEPAGENT_MODEL is required for real DeepAgent mode")

    os.environ["OPENAI_API_KEY"] = _load_openai_api_key()

    prompt = str(task.get("prompt", "")).strip()
    task_id = str(task.get("task_id", "unknown-task"))

    agent = create_deep_agent(
        model=model,
        system_prompt=(
            "You are a deterministic demo agent. "
            "Respond with the completion message and do not browse the web."
        ),
    )
    response = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                    + "\n\nWrite a file named result.txt containing exactly:"
                    + "\ndeepagent python demo complete",
                }
            ]
        }
    )
    message = "deepagent python demo complete"
    _write_result(workspace_dir, task_id, message)
    print(response)
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Python DeepAgent entrypoint.")
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "fallback", "real"), default="auto")
    args = parser.parse_args()

    task_json = Path(args.task_json)
    workspace_dir = Path(args.workspace_dir)
    task = _load_task(task_json)

    if args.mode == "fallback":
        _run_fallback(workspace_dir, task)
    elif args.mode == "real":
        _run_real_deepagent(workspace_dir, task)
    else:
        if os.environ.get("DEEPAGENT_MODE", "").strip().lower() == "real":
            _run_real_deepagent(workspace_dir, task)
        else:
            _run_fallback(workspace_dir, task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
