# Canonical Run Comparison

Compare two externally produced canonical runs:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli compare-runs \
  --baseline examples/canonical_runs/deepagent-main \
  --candidate examples/canonical_runs/deepagent-exp-a
```

Only tasks with the same `task_id` are compared. The output also lists task IDs
that exist in only one run.

Each common task receives a `score_delta`, calculated as:

```text
candidate_score - baseline_score
```

If a result has only `success`, its comparison score is `1.0` for true and
`0.0` for false. If both `score` and `success` exist, `score` takes precedence.

A task is:

- a regression when `score_delta < -threshold`
- an improvement when `score_delta > threshold`
- unchanged for classification purposes when its delta is within the inclusive
  threshold bounds

The default threshold is `0.05`. Override it with:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli compare-runs \
  --baseline path/to/baseline \
  --candidate path/to/candidate \
  --threshold 0.1
```

`summary_delta` uses the same candidate-minus-baseline direction for each
numeric top-level summary metric. A summary delta is `null` when either run
lacks that measurement.

The example runs intentionally contain one improvement, one regression, and
one unchanged task.
