# AA-style Coding Agent Evaluation

This repo intentionally contains only the evaluation layer needed to mirror the
metric shape of Artificial Analysis' Coding Agents page. It does not include
agent adapters, sandbox runners, or task execution harnesses.

## Metrics

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli metrics --results-dir path/to/results
```

Expected result layout:

```text
results/
  model-a/
    task-001.json
    task-002.json
```

The parser accepts common fields:

- score: `score`, `pass`, `success`, `resolved`, `scoring.combined_score`
- time: `agent_elapsed_sec`, `agent_wall_time_sec`, `execution_time_sec`
- usage: `usage_summary` or `usage`

## Usage Logs

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli usage --file codex-or-claude.jsonl
```

Supported usage shapes include:

- Codex JSONL `token_count` events
- Claude Code JSON output with `usage` and/or `total_cost_usd`
- OpenAI/Anthropic-style API `usage` objects

## Dataset Manifest

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli manifest
```

The bundled manifest records the three components listed by Artificial
Analysis:

- SWE-Bench-Pro-Hard-AA: 150 tasks
- Terminal-Bench v2: 84 tasks
- SWE-Atlas-QnA: 124 tasks

Exact reproduction requires the same task ids, prompts, run settings, scoring
rules, and three-run aggregation protocol.

## Local Dataset Files

Public Hugging Face files can be synced with:

```bash
PYTHONPATH=src python3 scripts/sync_datasets.py
```

Then inspect local availability:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli datasets
```

Currently stored locally:

- `datasets/swe-atlas-qna/data/test-00000-of-00001.parquet`
- `datasets/swe-atlas-qna/data/test.jsonl`
- `datasets/swe-bench-pro/data/test-00000-of-00001.parquet`
- `datasets/swe-bench-pro/data/test.jsonl`

Terminal-Bench v2 is represented as a source manifest because it is a
repo/harness-style benchmark rather than a small parquet file. The AA page
reports 84 Terminal-Bench v2 tasks; public references often mention 89, so the
exact AA task ids should be pinned before using it for reproduction.
