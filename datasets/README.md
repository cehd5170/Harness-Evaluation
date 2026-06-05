# Datasets

This directory stores local copies or source manifests for AA-style coding-agent
benchmark components.

Local data files are intentionally separated by source:

- `swe-atlas-qna/`: public Hugging Face dataset `ScaleAI/SWE-Atlas-QnA`.
- `swe-bench-pro/`: public Hugging Face split `ScaleAI/SWE-bench_Pro`.
- `terminal-bench-v2/`: source manifest for Terminal-Bench v2. The exact
  84-task AA subset is not publicly pinned here.

Refresh public downloadable files with:

```bash
PYTHONPATH=src python3 scripts/sync_datasets.py
```

Export Hugging Face rows into readable JSONL with:

```bash
PYTHONPATH=src python3 scripts/export_hf_rows.py
```
