# Harness-Evaluation

Lightweight ingestion and evaluation utilities for external agent harness
results.

External harnesses and CLI agents, including custom DeepAgent harnesses,
Claude Code, Codex, and Qwen CLI, remain responsible for running and scoring
tasks. This repository only:

1. ingests raw result files through mapping profiles,
2. writes canonical run JSON,
3. summarizes canonical runs, and
4. compares canonical runs.

It does not run agents, call model APIs, automate browsers or desktop GUIs,
execute sandboxes, implement harness internals, or perform LLM judging.

## v0.2 Workflow

Ingest a flat DeepAgent-style raw run:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli ingest-run \
  --input-dir examples/raw_runs/deepagent-exp-a \
  --output-dir examples/canonical_runs/deepagent-exp-a \
  --profile profiles/deepagent-result.json \
  --run-id deepagent-exp-a \
  --system deepagent-custom \
  --harness deepagent \
  --model qwen3-coder \
  --dataset-id workflow-lite
```

Summarize the canonical run:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli summarize-run \
  --run-dir examples/canonical_runs/deepagent-exp-a
```

Compare a candidate against a baseline:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli compare-runs \
  --baseline examples/canonical_runs/deepagent-main \
  --candidate examples/canonical_runs/deepagent-exp-a \
  --threshold 0.05
```

The example comparison contains one improved task, one regressed task, and one
unchanged task.

## Existing Commands

Summarize legacy/common harness result shapes into AA-style metrics:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli metrics --results-dir path/to/results
```

Parse a Codex / Claude Code / API usage log:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli usage --file path/to/usage.jsonl
```

With token pricing:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli usage \
  --file path/to/usage.jsonl \
  --pricing-json examples/pricing.example.json
```

Print the bundled AA-style component manifest:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli manifest
```

Manage local datasets:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli datasets
PYTHONPATH=src python3 -m harness_evaluation.cli init-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli validate-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli sample-dataset --id my-custom
```

## Documentation

- [Canonical run format](docs/canonical-run-format.md)
- [Raw run ingestion and profiles](docs/ingest-run.md)
- [Run comparison](docs/run-comparison.md)
- [AA-style metrics](docs/aa-coding-agents.md)
- [Custom datasets](docs/custom-datasets.md)
