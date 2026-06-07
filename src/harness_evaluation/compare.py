from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from harness_evaluation.canonical import CanonicalRun, load_run, result_score
from harness_evaluation.summarize import summarize_run


SUMMARY_DELTA_FIELDS = (
    "task_count",
    "scored_task_count",
    "mean_score",
    "success_rate",
    "mean_elapsed_sec",
    "p50_elapsed_sec",
    "p95_elapsed_sec",
    "mean_cost_usd",
    "mean_total_tokens",
    "mean_tool_calls",
    "failed_tool_call_rate",
    "safety_violation_rate",
)


def _delta(baseline: Any, candidate: Any) -> float | None:
    if isinstance(baseline, (int, float)) and isinstance(candidate, (int, float)):
        return round(float(candidate) - float(baseline), 6)
    return None


def compare_runs(
    baseline: CanonicalRun | Path | str,
    candidate: CanonicalRun | Path | str,
    *,
    threshold: float = 0.05,
) -> dict[str, Any]:
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold):
        raise ValueError("threshold must be a finite non-negative number")
    if threshold < 0:
        raise ValueError("threshold must be a finite non-negative number")
    if not isinstance(baseline, CanonicalRun):
        baseline = load_run(baseline)
    if not isinstance(candidate, CanonicalRun):
        candidate = load_run(candidate)

    baseline_summary = summarize_run(baseline)
    candidate_summary = summarize_run(candidate)
    baseline_ids = set(baseline.results)
    candidate_ids = set(candidate.results)
    common_ids = sorted(baseline_ids & candidate_ids)

    task_deltas: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for task_id in common_ids:
        baseline_score = result_score(baseline.results[task_id])
        candidate_score = result_score(candidate.results[task_id])
        score_delta = _delta(baseline_score, candidate_score)
        item = {
            "task_id": task_id,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "score_delta": score_delta,
        }
        task_deltas.append(item)
        if baseline_score is None or candidate_score is None:
            continue
        if candidate_score < baseline_score - threshold:
            regressions.append(item)
        elif candidate_score > baseline_score + threshold:
            improvements.append(item)

    return {
        "baseline_run_id": baseline.metadata["run_id"],
        "candidate_run_id": candidate.metadata["run_id"],
        "threshold": float(threshold),
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "summary_delta": {
            field: _delta(baseline_summary.get(field), candidate_summary.get(field))
            for field in SUMMARY_DELTA_FIELDS
        },
        "common_task_count": len(common_ids),
        "baseline_only_task_ids": sorted(baseline_ids - candidate_ids),
        "candidate_only_task_ids": sorted(candidate_ids - baseline_ids),
        "task_deltas": task_deltas,
        "regressions": regressions,
        "improvements": improvements,
    }
