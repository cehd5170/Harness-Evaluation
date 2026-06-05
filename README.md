# Harness-Evaluation

Lightweight evaluation utilities for coding-agent harness results.

This repository is intentionally focused on the pieces needed to mirror the
metric shape of Artificial Analysis' Coding Agents page:

- Performance / coding-agent index
- Token usage per task
- API cost per task
- Agent execution time per task
- Dataset/component manifest

It does not include agent adapters or a sandbox runner. Feed it result JSON
from whichever harness you use.

## Usage

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

List downloaded/source datasets:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli datasets
```

Create and validate a custom dataset:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli init-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli validate-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli sample-dataset --id my-custom
```

See [docs/aa-coding-agents.md](docs/aa-coding-agents.md).
See [docs/custom-datasets.md](docs/custom-datasets.md).
