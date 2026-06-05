from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _score(result: dict[str, Any]) -> float | None:
    for key in ("score", "pass", "success", "resolved"):
        value = result.get(key)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        score = _safe_float(value)
        if score is not None:
            return score
    for parent_key, child_keys in (
        ("scoring", ("combined_score", "score", "outcome_score")),
        ("combined_result", ("combined_score", "score")),
        ("oracle_result", ("outcome_score", "score")),
    ):
        parent = result.get(parent_key)
        if not isinstance(parent, dict):
            continue
        for child_key in child_keys:
            score = _safe_float(parent.get(child_key))
            if score is not None:
                return score
    return None


def _elapsed(result: dict[str, Any]) -> float | None:
    for key in ("agent_elapsed_sec", "agent_wall_time_sec", "execution_time_sec", "elapsed_sec"):
        elapsed = _safe_float(result.get(key))
        if elapsed is not None:
            return elapsed
    adapter = result.get("adapter_result")
    if isinstance(adapter, dict):
        metadata = adapter.get("metadata")
        if isinstance(metadata, dict):
            elapsed = _safe_float(metadata.get("agent_elapsed_sec"))
            if elapsed is not None:
                return elapsed
    return None


def _usage(result: dict[str, Any]) -> dict[str, Any] | None:
    usage = result.get("usage_summary") or result.get("usage")
    return usage if isinstance(usage, dict) and usage.get("available", True) else None


def summarize_result_dir(results_dir: Path) -> dict[str, Any]:
    model_dirs = sorted(path for path in results_dir.iterdir() if path.is_dir())
    if not model_dirs:
        model_dirs = [results_dir]

    models: dict[str, Any] = {}
    for model_dir in model_dirs:
        result_files = sorted(model_dir.glob("*.json"))
        results = [item for item in (_read_json(path) for path in result_files) if item]
        scores: list[float] = []
        elapsed_values: list[float] = []
        token_available = 0
        cost_available = 0
        input_tokens: list[float] = []
        cache_read_tokens: list[float] = []
        cache_write_tokens: list[float] = []
        output_tokens: list[float] = []
        total_tokens: list[float] = []
        cost_total: list[float] = []

        for result in results:
            score = _score(result)
            if score is not None:
                scores.append(score)
            elapsed = _elapsed(result)
            if elapsed is not None:
                elapsed_values.append(elapsed)
            usage = _usage(result)
            if usage is None:
                continue
            token_available += 1
            for key, target in (
                ("input_tokens", input_tokens),
                ("cache_read_tokens", cache_read_tokens),
                ("cache_write_tokens", cache_write_tokens),
                ("output_tokens", output_tokens),
                ("total_tokens", total_tokens),
            ):
                value = _safe_float(usage.get(key))
                if value is not None:
                    target.append(value)
            cost = _safe_float(usage.get("cost_total") or usage.get("total_cost_usd") or usage.get("cost_usd"))
            if cost is not None:
                cost_total.append(cost)
                cost_available += 1

        index = _mean(scores)
        models[model_dir.name] = {
            "task_count": len(results),
            "performance": {
                "coding_agent_index": index,
                "coding_agent_index_pct": round(index * 100, 3) if index is not None else None,
                "scored_task_count": len(scores),
                "score_source": "mean of per-task score/pass/success/resolved fields",
            },
            "token_usage": {
                "available_task_count": token_available,
                "mean_input_tokens_per_task": _mean(input_tokens),
                "mean_cached_input_tokens_per_task": _mean(cache_read_tokens),
                "mean_cache_write_tokens_per_task": _mean(cache_write_tokens),
                "mean_output_tokens_per_task": _mean(output_tokens),
                "mean_total_tokens_per_task": _mean(total_tokens),
            },
            "cost": {
                "available_task_count": cost_available,
                "mean_api_cost_usd_per_task": _mean(cost_total),
            },
            "execution_time": {
                "available_task_count": len(elapsed_values),
                "mean_agent_wall_time_sec_per_task": _mean(elapsed_values),
            },
        }

    return {
        "metric_style": "artificial-analysis-coding-agents",
        "results_dir": str(results_dir),
        "models": models,
    }
