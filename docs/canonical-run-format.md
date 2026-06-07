# Canonical Run Format

The canonical run format is the stable boundary between external agent
harnesses and Harness-Evaluation. Harness-Evaluation can ingest external
results or orchestrate profile-defined external commands, then summarize and
compare canonical runs.

This repository does not implement agents, call models directly, automate
browsers or desktop GUIs, provide a sandbox, or perform LLM judging.

## Directory Layout

```text
canonical_runs/<run_id>/
  run.json
  tasks/
    <task_id>/
  results/
    <task_id>.json
```

Result files are read directly from `results/`. The filename stem must exactly
match the result's `task_id`.

## Run Metadata

`run.json` requires:

```json
{
  "run_id": "deepagent-exp-a",
  "system": "deepagent-custom",
  "harness": "deepagent",
  "model": "qwen3-coder",
  "dataset_id": "workflow-lite",
  "dataset_version": "v1",
  "code_commit": "2222222222222222222222222222222222222222",
  "created_at": "2026-06-02T09:00:00Z",
  "run_config": {
    "temperature": 0
  }
}
```

The first eight fields must be non-empty strings. `run_config` must be an
object. During ingestion, command-line metadata takes precedence over the raw
run's `run.json`; absent optional command-line metadata falls back to the raw
run metadata and then to `"unknown"`.

## Task Results

Only `task_id` plus at least one of `score` or `success` is required.
Ingestion writes a consistent optional-field shape:

```json
{
  "task_id": "doc-summary-001",
  "score": 0.84,
  "success": true,
  "error_type": null,
  "error_message": null,
  "exit_code": 0,
  "elapsed_sec": 35.0,
  "usage": {
    "input_tokens": 2200,
    "output_tokens": 600,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "total_tokens": 2800,
    "cost_usd": 0.025
  },
  "metrics": {
    "tool_calls": 7,
    "failed_tool_calls": 0,
    "safety_violations": 0,
    "human_interventions": 0
  },
  "artifacts": {
    "final_state": {
      "document_written": true
    }
  },
  "metadata": {
    "category": "documents",
    "difficulty": "medium"
  },
  "raw": {
    "source_files": [
      "doc-summary-001.json"
    ]
  },
  "checks": []
}
```

Missing optional scalar measurements may be `null` or omitted. Missing
optional measurements are excluded from summaries rather than treated as
zero. `raw.source_files` records task logs or input files used to create the
result. Runner-produced results include deterministic checker details in
`checks`.

If both `score` and `success` exist, `score` is used for score aggregation and
comparison, while `success` is used for the success rate. A result containing
only `success` receives a comparison score of `1.0` or `0.0`.

## Summarization Rules

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli summarize-run \
  --run-dir examples/canonical_runs/deepagent-exp-a
```

- Percentiles use linear interpolation over sorted elapsed values.
- `failed_tool_call_rate` is total failed tool calls divided by total tool
  calls among results that report both fields.
- `safety_violation_rate` is the fraction of reporting tasks with one or more
  safety violations.
- Numeric outputs are rounded to six decimal places.
- `by_category` is included when at least one result has a non-empty string
  `metadata.category`.
