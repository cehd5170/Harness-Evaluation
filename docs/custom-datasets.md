# Custom Datasets

Custom datasets are plain JSONL files under `datasets/<dataset-id>/data/`.
Each line is one task.

Minimal required fields:

- `task_id`: stable unique id
- `prompt`: instruction given to the agent or harness

Recommended optional fields:

- `reference_answer`: expected answer or grading reference
- `rubric`: grading rubric text or structured object
- `repository_url`: source repository, if the task needs code
- `repository_base_commit`: commit to check out
- `docker_image`: execution image
- `metadata`: arbitrary tags such as difficulty/category/source

## Create A Dataset

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli init-dataset --id my-custom
```

Edit:

```text
datasets/my-custom/data/test.jsonl
datasets/my-custom/dataset.json
```

Validate:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli validate-dataset --id my-custom
```

Preview:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli sample-dataset --id my-custom
```

## Use With A Runner

`Harness-Evaluation` does not execute tasks by itself. A runner should read the
JSONL rows, run each task with your agent/harness, then write result JSON files
that include at least one score-like field:

```json
{
  "task_id": "custom-001",
  "score": 1.0,
  "agent_elapsed_sec": 42.5,
  "usage_summary": {
    "available": true,
    "input_tokens": 1000,
    "output_tokens": 200,
    "total_tokens": 1200,
    "cost_total": 0.01
  }
}
```

Then summarize:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli metrics --results-dir path/to/results
```
