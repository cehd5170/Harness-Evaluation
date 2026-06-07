# Ingest Raw Runs

`ingest-run` converts externally produced raw result files into a canonical
run. It does not launch an agent, execute tasks, score final states, or parse
vendor-specific transcripts.

## Flat JSON Example

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

The command prints:

```json
{
  "records_seen": 3,
  "records_written": 3,
  "records_skipped": 0,
  "warnings": []
}
```

Before writing, ingestion removes existing `*.json` files from the output
`results/` directory so stale tasks cannot remain in the canonical run.

## Task Directory Example

The `cli-task-dir` profile supports:

```text
raw_runs/<run_id>/
  run.json
  tasks/
    <task_id>/
      result.json
      usage.jsonl
      transcript.jsonl
      artifacts/
```

Only configured files are read. The built-in profile reads score, success,
timing, metrics, artifacts, and metadata from `result.json`, then passes
`usage.jsonl` to the existing usage parser. It does not parse
`transcript.jsonl` or inspect artifact contents.

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli ingest-run \
  --input-dir examples/raw_runs/codex-like \
  --output-dir examples/canonical_runs/codex-like \
  --profile profiles/cli-task-dir.json \
  --run-id codex-like \
  --system openai \
  --harness codex-cli \
  --model codex-example-model \
  --dataset-id workflow-lite
```

## Profile Format

Profiles are JSON objects. They describe a layout and mappings rather than
implementing harness-specific adapter code.

```json
{
  "id": "example",
  "input": {
    "layout": "flat-json",
    "glob": "*.json",
    "exclude": ["run.json"]
  },
  "fields": {
    "task_id": ["task_id", "_source_stem"],
    "score": ["score", "scoring.combined_score", "result.score"],
    "success": ["success", "pass", "resolved"],
    "elapsed_sec": ["elapsed_sec", "agent_elapsed_sec"]
  },
  "metrics": {
    "tool_calls": {
      "count_events": {
        "path": "events",
        "where": {"type": "tool_call"}
      }
    }
  },
  "usage": {
    "parser": "usage-summary",
    "source": "record"
  }
}
```

Supported layouts:

- `flat-json`: uses `input.glob` and optional `input.exclude`.
- `task-dir`: uses `input.task_glob`, `input.result_file`, optional
  `input.usage_file`, and optional `input.exclude`.

Field mappings support one dotted path or an ordered list of fallback dotted
paths. Dotted canonical destinations such as `artifacts.final_state` are also
supported. Two ingestion context fields are available:

- `_source_stem`: flat JSON filename without `.json`
- `_task_dir_name`: task directory name

Metric mappings may use fallback dotted paths or `count_events`. Event
conditions use exact equality and may themselves use dotted paths.

Usage configuration supports:

- `{"parser": "usage-summary", "source": "record"}`
- `{"parser": "usage-summary", "source": "usage-file"}`

Both modes reuse `harness_evaluation.usage`; they do not add transcript
parsers. Missing costs remain `null`, while explicitly reported zero costs
remain `0.0`.

## Built-In Profiles

- `profiles/generic-result.json`: common flat result fields
- `profiles/deepagent-result.json`: DeepAgent-style flat results and event
  counters
- `profiles/cli-task-dir.json`: task directories with separate result and
  usage files

You can add a new harness shape by creating another profile without changing
Python code, provided its scores and metadata are available through these
mapping primitives.
