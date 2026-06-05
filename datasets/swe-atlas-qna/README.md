---
dataset_info:
  config_name: default
  splits:
    - name: test
      num_examples: 124
---

Update 03/30/2026: We released the dataset in [harbor](https://github.com/harbor-framework/harbor) format in our official GitHub repo for [SWE-Atlas](https://github.com/scaleapi/SWE-Atlas). 
We recommend using the harbor scaffold with modal runtime sandboxes as the official way to run the benchmark.

# SWE-Atlas QnA

Codebase QnA is the first benchmark in the SWE-Atlas suite. It evaluates AI agents on deep code comprehension — tracing execution paths, explaining architectural decisions, and answering deeply technical questions about production-grade software systems.

124 tasks across 11 open-source repositories spanning Go, Python, C, and TypeScript.

Link to leaderboard - [https://scale.com/leaderboard/sweatlas-qna](https://scale.com/leaderboard/sweatlas-qna)


## Schema

| Column | Type | Description |
|---|---|---|
| `task_id` | string | Unique 24-char hex identifier |
| `prompt` | string | The question presented to the agent |
| `reference_answer` | string | Expert-written reference answer |
| `repository_url` | string | GitHub repo |
| `repository_base_commit` | string | 40-char commit SHA the environment is pinned to |
| `language` | string | `go`, `python`, `c`, or `ts` |
| `category` | string | Task category (see below) |
| `rubric` | string (JSON) | Evaluation criteria (see below) |
| `docker_image` | string | Docker Hub image for the sandboxed environment |

### Rubric format

Each task's `rubric` field is a JSON array:

```json
[
  {
    "id": "a33fc01cba19849aaf3b55e6b801001c",
    "title": "1.1: States that kitty uses Unix sockets for external connections...",
    "annotations": {
      "type": "positive hli verifier",
      "importance": "must have"
    }
  }
]
```

- `positive hli verifier` — a factual claim the answer must contain. If the claim is met my the agent's answer, the rubric item result is a PASS.
- `negative hli verifier` — something the answer must *not* claim. If the claim is met my the agent's answer, the rubric item result is a FAIL.


Each task includes a `docker_image` field pointing to a pre-built Docker Hub image with the repository and all dependencies installed at `/app`:


## Inference and Eval

We follow the standard SWE-Agent scaffold, and we provide a sample config (with the prompts) in  [default_qa_config.yaml](default_qa_config.yaml)

To run tasks, you can pull the docker image and run the container, and reset the environment to the base commit:

```bash
cd /app
git config --global --add safe.directory /app
git restore .
git reset --hard <repository_base_commit>
git clean -fdq
```

Evaluation is performed by an LLM judge (Claude Opus 4.5) that scores the agent's answer against each rubric criterion independently. Each criterion receives a binary score (met or not met) indicating and is then aggregated.

The primary metric is the Task Resolve Rate: the percentage of tasks for which the agent's answer is comprehensive (i.e. passes all rubric items and scores 1.0), as graded by a set of task-specific rubrics. 

The agents are also instructed to avoid modifying source-code files, and clean up any temporary scripts made. So we add a programmatic check that fails a task that has any code changes after submission. 

Our rubric evaluation prompt and other relevant details are in [rubric_evaluation_config.yaml](rubric_evaluation_config.yaml)