# Canonical Run Format

The canonical run format is the boundary between an external agent harness and
this repository. External harnesses run tasks and write canonical JSON files.
Harness-Evaluation only reads those files.

This repository does not run agents, call models, automate browsers, manage
sandboxes, or implement harness internals.

## Directory Layout

```text
<run-dir>/
  run.json
  results/
    <task_id>.json
```

Result files are read directly from `results/`. The filename stem must exactly
match the result's `task_id`.

## Run Metadata

`run.json` is a JSON object with these required fields:

```json
{
  "run_id": "deepagent-exp-a-2026-06-02",
  "system": "deepagent",
  "harness": "custom-deepagent",
  "model": "example-model",
  "dataset_id": "office-tasks-example",
  "dataset_version": "v1",
  "code_commit": "2222222222222222222222222222222222222222",
  "created_at": "2026-06-02T09:00:00Z",
  "run_config": {
    "temperature": 0
  }
}
```

The first eight fields must be non-empty strings. `run_config` must be an
object and may contain harness-specific settings.

## Task Results

Each result is a JSON object with:

- `task_id`: required non-empty string
- `score`: finite numeric score, or
- `success`: boolean success result

If both `score` and `success` exist, `score` is used for score aggregation and
comparison, while `success` is used for the success rate.

Optional fields:

- `error_type`
- `error_message`
- `elapsed_sec`
- `usage`: `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`
- `metrics`: `tool_calls`, `failed_tool_calls`, `safety_violations`,
  `human_interventions`
- `artifacts`: harness-defined artifact references
- `metadata`: `category`, `difficulty`, or other task tags

Example:

```json
{
  "task_id": "doc-summary-001",
  "score": 0.84,
  "success": true,
  "elapsed_sec": 35.0,
  "usage": {
    "input_tokens": 2200,
    "output_tokens": 600,
    "total_tokens": 2800,
    "cost_usd": 0.025
  },
  "metrics": {
    "tool_calls": 7,
    "failed_tool_calls": 0,
    "safety_violations": 0,
    "human_interventions": 0
  },
  "metadata": {
    "category": "documents",
    "difficulty": "medium"
  }
}
```

Unknown fields are preserved and ignored by v0.1 aggregation.

## Summarization Rules

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli summarize-run \
  --run-dir examples/canonical_runs/deepagent-exp-a
```

- Missing optional measurements are excluded from their metric, not counted as
  zero.
- A `success` result without `score` receives a score of `1.0` or `0.0`.
- `success_rate` uses only results with an explicit boolean `success`.
- Percentiles use linear interpolation over sorted elapsed values.
- `failed_tool_call_rate` is total failed tool calls divided by total tool
  calls among results that report both fields.
- `safety_violation_rate` is the fraction of reporting tasks with one or more
  safety violations.
- Numeric outputs are rounded to six decimal places.
- `by_category` is included when at least one result has a non-empty string
  `metadata.category`. Tasks without categories are omitted from that section.
