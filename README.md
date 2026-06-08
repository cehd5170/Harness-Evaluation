# Harness-Evaluation

Dependency-light orchestration, ingestion, and evaluation utilities for
external CLI agents.

Harness-Evaluation can run configurable external commands such as Codex CLI,
Claude Code, Qwen CLI, or a custom DeepAgent runner against the same JSONL
tasks. It creates isolated per-task workspaces, runs deterministic checkers,
and writes canonical results.

This repository does **not** implement those agents, call model APIs directly,
run browser automation, or perform LLM judging. Runner profiles only describe
external subprocess commands.

## v0.3 Run Workflow

The bundled echo runner requires no external agent and is the smoke test:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli run-suite \
  --dataset-jsonl datasets/workflow-lite/data/test.jsonl \
  --runner runners/echo-runner.json \
  --output-dir runs/echo-smoke \
  --run-id echo-smoke \
  --system echo \
  --harness subprocess \
  --model none
```

Summarize the canonical run:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli summarize-run \
  --run-dir runs/echo-smoke
```

Run one task:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli run-task \
  --dataset-jsonl datasets/workflow-lite/data/test.jsonl \
  --task-id doc-summary-001 \
  --runner runners/codex-cli.example.json \
  --output-dir runs/codex-debug \
  --run-id codex-debug \
  --system codex \
  --harness codex-cli \
  --model gpt-5.4-codex
```

The Codex, Claude Code, Qwen CLI, and DeepAgent profiles are examples. Adjust
their commands and explicitly declared environment variables for the versions
installed on your machine.

## Real Python DeepAgent

The bundled `runners/deepagent-python.example.json` profile exercises a real
Python Deep Agent entrypoint through `create_deep_agent(...)`.

Important:

- This harness does **not** inherit your shell environment.
- The runner profile only sees the variables listed in its `env` block.
- If you want to use a real OpenAI-backed Deep Agent, put a valid
  `OPENAI_API_KEY` into the runner profile you pass to `run-suite`.

Recommended setup:

1. Keep your secret in a local `.env` file or `~/.deepagents/.env`.
2. Copy `runners/deepagent-python.example.json` to a local untracked file.
3. Add your `OPENAI_API_KEY` to that local copy's `env` block.
4. Run the suite with that local profile.

Example:

```bash
cp runners/deepagent-python.example.json /tmp/deepagent-python.local.json
# edit /tmp/deepagent-python.local.json and add OPENAI_API_KEY under env

PYTHONPATH=src python3 -m harness_evaluation.cli run-suite \
  --dataset-jsonl datasets/deepagent-python-demo/data/test.jsonl \
  --runner /tmp/deepagent-python.local.json \
  --output-dir runs/deepagent-python-real \
  --run-id deepagent-python-real \
  --system deepagent \
  --harness python \
  --model demo
```

That profile uses `uv run --with deepagents --with langchain-openai` and a
workspace-local `deepagent_demo.py` script. The demo writes `result.txt` in the
task workspace and the checker verifies that output.

The script itself is here:

- [examples/deepagent_python_demo.py](examples/deepagent_python_demo.py)

## Safety

- Every task runs inside `tasks/<task_id>/workspace/`, never in the repository
  root.
- Runner `cwd` is rejected unless it is inside the per-task run directory.
- Subprocesses receive only environment variables explicitly listed in the
  runner profile. The current process environment is not inherited.
- `--dry-run` renders and reports commands without executing them.
- Timeouts are required and enforced.
- `--continue-on-error` continues after task execution or setup errors.
- Workspace source paths and destinations cannot escape the dataset or task
  workspace.

Runner profiles are executable configuration. Review profiles before running
them.

## Canonical Runs

Runner and ingestion workflows write:

```text
runs/<run-id>/
  run.json
  tasks/<task-id>/
  results/<task-id>.json
```

Compare two runs:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli compare-runs \
  --baseline runs/deepagent-main \
  --candidate runs/codex-exp-a \
  --threshold 0.05
```

## Existing Commands

The v0.2 commands remain available:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli metrics --results-dir path/to/results
PYTHONPATH=src python3 -m harness_evaluation.cli usage --file path/to/usage.jsonl
PYTHONPATH=src python3 -m harness_evaluation.cli manifest
PYTHONPATH=src python3 -m harness_evaluation.cli datasets
PYTHONPATH=src python3 -m harness_evaluation.cli init-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli validate-dataset --id my-custom
PYTHONPATH=src python3 -m harness_evaluation.cli sample-dataset --id my-custom
```

Raw external harness results can still be converted with `ingest-run`; see
[Raw run ingestion and profiles](docs/ingest-run.md).

## Documentation

- [Running agent suites](docs/running-agent-suites.md)
- [Runner profiles](docs/runner-profiles.md)
- [Deterministic checkers](docs/checkers.md)
- [Canonical run format](docs/canonical-run-format.md)
- [Raw run ingestion and profiles](docs/ingest-run.md)
- [Run comparison](docs/run-comparison.md)
- [Custom datasets](docs/custom-datasets.md)
