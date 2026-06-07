from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from harness_evaluation.canonical import CanonicalRun, load_run, result_score


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 6)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 6)


def _nested_number(result: dict[str, Any], parent: str, field: str) -> float | None:
    value = result.get(parent)
    if not isinstance(value, dict):
        return None
    return _number(value.get(field))


def _aggregate(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(results)
    scores = [score for result in items if (score := result_score(result)) is not None]
    successes = [1.0 if result["success"] else 0.0 for result in items if isinstance(result.get("success"), bool)]
    elapsed = [value for result in items if (value := _number(result.get("elapsed_sec"))) is not None]
    costs = [value for result in items if (value := _nested_number(result, "usage", "cost_usd")) is not None]
    total_tokens = [
        value for result in items if (value := _nested_number(result, "usage", "total_tokens")) is not None
    ]
    tool_calls = [
        value for result in items if (value := _nested_number(result, "metrics", "tool_calls")) is not None
    ]
    failed_tool_pairs = [
        (calls, failed)
        for result in items
        if (calls := _nested_number(result, "metrics", "tool_calls")) is not None
        and (failed := _nested_number(result, "metrics", "failed_tool_calls")) is not None
    ]
    safety_violations = [
        value
        for result in items
        if (value := _nested_number(result, "metrics", "safety_violations")) is not None
    ]
    failed_tool_call_total = sum(failed for _, failed in failed_tool_pairs)
    tool_call_total = sum(calls for calls, _ in failed_tool_pairs)

    return {
        "task_count": len(items),
        "scored_task_count": len(scores),
        "mean_score": _mean(scores),
        "success_rate": _mean(successes),
        "mean_elapsed_sec": _mean(elapsed),
        "p50_elapsed_sec": _percentile(elapsed, 0.50),
        "p95_elapsed_sec": _percentile(elapsed, 0.95),
        "mean_cost_usd": _mean(costs),
        "mean_total_tokens": _mean(total_tokens),
        "mean_tool_calls": _mean(tool_calls),
        "failed_tool_call_rate": (
            round(failed_tool_call_total / tool_call_total, 6) if tool_call_total > 0 else None
        ),
        "safety_violation_rate": (
            round(sum(value > 0 for value in safety_violations) / len(safety_violations), 6)
            if safety_violations
            else None
        ),
    }


def summarize_run(run: CanonicalRun | Path | str) -> dict[str, Any]:
    if not isinstance(run, CanonicalRun):
        run = load_run(run)
    summary = {
        "run_id": run.metadata["run_id"],
        "system": run.metadata["system"],
        "harness": run.metadata["harness"],
        "model": run.metadata["model"],
        "dataset_id": run.metadata["dataset_id"],
        **_aggregate(run.results.values()),
    }

    categories: dict[str, list[dict[str, Any]]] = {}
    for result in run.results.values():
        metadata = result.get("metadata")
        category = metadata.get("category") if isinstance(metadata, dict) else None
        if isinstance(category, str) and category:
            categories.setdefault(category, []).append(result)
    if categories:
        summary["by_category"] = {
            category: _aggregate(categories[category])
            for category in sorted(categories)
        }
    return summary
