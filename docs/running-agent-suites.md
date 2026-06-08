# Running Agent Suites

Harness-Evaluation orchestrates external CLI agents. It does not implement
agent or model logic. A runner profile supplies the subprocess command, and a
dataset task supplies the prompt, workspace files, and deterministic checker.

## Smoke Test

`echo-runner.json` works without external tools:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli run-suite \
  --dataset-jsonl datasets/workflow-lite/data/test.jsonl \
  --runner runners/echo-runner.json \
  --output-dir runs/echo-smoke \
  --run-id echo-smoke \
  --system echo \
  --harness subprocess \
  --model none

PYTHONPATH=src python3 -m harness_evaluation.cli summarize-run \
  --run-dir runs/echo-smoke
```

Use `--max-tasks 20` to limit a suite or `run-task --task-id <id>` to run one
task. Use `--continue-on-error` to continue after subprocess timeouts, non-zero
exits, or task setup errors.

## Dry Runs

Add `--dry-run` to create task directories and print rendered command
arguments without executing them:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli run-suite \
  --dataset-jsonl datasets/workflow-lite/data/test.jsonl \
  --runner runners/codex-cli.example.json \
  --output-dir runs/codex-dry-run \
  --run-id codex-dry-run \
  --system codex \
  --harness codex-cli \
  --model configured-externally \
  --dry-run
```

Dry-run results use `error_type: "dry_run"` and are not successful evaluation
results.

## Task Isolation

For each task the runner:

1. Creates `tasks/<task_id>/workspace/`.
2. Copies only the task's declared `workspace.files`.
3. Writes `prompt.txt`, `task.json`, and `command.json` under the task run
   directory.
4. Executes the external command with a timeout and an explicitly declared
   environment.
5. Runs the task checker and copies configured artifacts.
6. Writes `results/<task_id>.json`.

The runner rejects a profile `cwd` outside the per-task run directory. It does
not create sandboxes or containers; the external command still has the host
permissions of the user running it.

## External CLI Examples

Profiles under `runners/*.example.json` are starting points. CLI argument names
and non-interactive modes change between releases, so adjust each command for
the installed CLI. Explicitly add only the environment variables that command
needs. Current shell variables, credentials, and `HOME` are not inherited
automatically.

## Python DeepAgent Demo

The `runners/deepagent-python.example.json` profile is a minimal Python
DeepAgent-style smoke test. It copies a workspace-local `deepagent_demo.py`
into the task workspace and invokes it with `python3` so the harness can
exercise a Python entrypoint without hard-coding repo paths.

By default the demo falls back to a deterministic file write so the repo can
be smoke-tested without installing `deepagents` or configuring model access.
To exercise the real `create_deep_agent(...)` code path, install the package
and set `DEEPAGENT_MODE=real` plus a valid `DEEPAGENT_MODEL` in the profile
environment.
