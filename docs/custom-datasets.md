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
- `workspace.files`: files copied from the dataset directory into the isolated
  task workspace
- `checker`: deterministic artifact, command, or JSON checker

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

Runner-ready tasks can declare workspace files as strings or source/destination
objects:

```json
{
  "task_id": "custom-001",
  "prompt": "Update report.txt.",
  "workspace": {
    "files": [
      {
        "source": "inputs/custom-001/report.txt",
        "destination": "report.txt"
      }
    ]
  },
  "checker": {
    "type": "artifact",
    "expected_files": ["report.txt"],
    "required_text": {
      "report.txt": "complete"
    }
  }
}
```

A string workspace entry copies the source to the workspace root using its
basename. Sources are relative to the dataset directory; destinations are
relative to the isolated workspace. Symbolic links and escaping paths are
rejected.

Then run and summarize:

```bash
PYTHONPATH=src python3 -m harness_evaluation.cli run-suite \
  --dataset-jsonl datasets/my-custom/data/test.jsonl \
  --runner runners/echo-runner.json \
  --output-dir runs/my-custom \
  --run-id my-custom \
  --system echo \
  --harness subprocess \
  --model none
```
