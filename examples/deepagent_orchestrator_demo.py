from __future__ import annotations

"""
Minimal Deep Agents orchestrator demo.

Usage:
    python3 examples/deepagent_orchestrator_demo.py --mode fallback

Real Deep Agents run:
    uv run --with deepagents --with langchain-openai \
        python3 examples/deepagent_orchestrator_demo.py --mode real

Requirements for real mode:
    - OPENAI_API_KEY
    - DEEPAGENT_MODEL, optional. Defaults to openai:gpt-5.4-nano.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_TASK = (
    "幫我規劃一個 FastAPI 專案"
)

ORCHESTRATOR_PROMPT = """
You are a software-project orchestrator.

Workflow rules:
1. Always start by calling write_todos to create a concrete todo list.
2. Mark exactly one todo as in_progress before working on it.
3. After every major step, update the todo list.
4. For complex subtasks, delegate with the task tool.
5. Keep the final answer concise and include:
   - completed todos
   - what was delegated
   - implementation plan
   - risks or missing information

Do not skip the todo list.
"""


def lookup_project_context(topic: str) -> str:
    """Look up local project context for planning a demo application."""
    context = {
        "requirements": (
            "Build a FastAPI todo manager with endpoints to create todos, "
            "list todos, mark a todo complete, and delete a todo."
        ),
        "stack": "Use Python 3.10+, FastAPI, SQLite, Pydantic models, and pytest.",
        "quality": "Include focused tests for create/list/complete/delete behavior.",
    }
    key = topic.strip().lower()
    return context.get(key, f"No stored context for topic: {topic}")


def create_tracking_ticket(title: str, description: str) -> str:
    """Create a fake tracking ticket for a planned implementation task."""
    return json.dumps(
        {
            "ticket_id": "DEMO-001",
            "title": title,
            "description": description,
            "status": "created",
        },
        ensure_ascii=False,
    )


def load_openai_api_key() -> str:
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value and value.lower() not in {"none", "null"}:
        return value

    codex_auth = Path.home() / ".codex" / "auth.json"
    if codex_auth.exists():
        try:
            data = json.loads(codex_auth.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            candidate = str(data.get("OPENAI_API_KEY", "")).strip()
            if candidate and candidate.lower() not in {"none", "null"}:
                return candidate

    raise RuntimeError("OPENAI_API_KEY is required for --mode real")


def build_agent() -> Any:
    try:
        from deepagents import create_deep_agent
    except ImportError as exc:
        raise RuntimeError(
            "deepagents is not installed. Try: "
            "uv run --with deepagents --with langchain-openai "
            "python3 examples/deepagent_orchestrator_demo.py --mode real"
        ) from exc

    model = os.environ.get("DEEPAGENT_MODEL", "openai:gpt-5.4-nano").strip()
    if not model:
        raise RuntimeError("DEEPAGENT_MODEL cannot be empty")

    return create_deep_agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[lookup_project_context, create_tracking_ticket],
        name="todo-orchestrator",
    )


def run_real(task: str) -> str:
    os.environ["OPENAI_API_KEY"] = load_openai_api_key()

    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    final_message = result["messages"][-1]
    return str(getattr(final_message, "content", final_message))


def run_fallback(task: str) -> str:
    """Deterministic local preview of the intended orchestrator behavior."""
    todos = [
        {"content": "整理 FastAPI todo manager 的需求", "status": "completed"},
        {"content": "規劃 API、資料模型與測試策略", "status": "completed"},
        {"content": "審查風險與缺少資訊", "status": "completed"},
    ]
    return "\n".join(
        [
            "[fallback] Deep Agents real mode was not called.",
            "",
            f"User task: {task}",
            "",
            "Todo list preview:",
            json.dumps(todos, ensure_ascii=False, indent=2),
            "",
            "Delegation preview:",
            "- general-purpose subagent: requirements/context gathering",
            "- general-purpose subagent: implementation planning",
            "- general-purpose subagent: risk review",
            "",
            "Implementation plan:",
            "1. Create FastAPI app with Todo schema and SQLite persistence.",
            "2. Add POST /todos, GET /todos, PATCH /todos/{id}/complete, DELETE /todos/{id}.",
            "3. Add pytest coverage for create/list/complete/delete.",
            "",
            "Risk:",
            "- Real todo tool calls require --mode real with deepagents and a valid model API key.",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Agents orchestrator demo.")
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--mode", choices=("auto", "fallback", "real"), default="auto")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if args.mode == "fallback":
        output = run_fallback(args.task)
    elif args.mode == "real":
        output = run_real(args.task)
    else:
        try:
            output = run_real(args.task)
        except Exception as exc:
            output = run_fallback(args.task) + f"\n\nAuto mode fallback reason: {exc}"

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
