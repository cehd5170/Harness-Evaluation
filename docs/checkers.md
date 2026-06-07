# Deterministic Checkers

Each task may contain one `checker` object. Checkers run locally after the
external command and return `score`, `success`, `checks`, `error_type`, and
`error_message`. No LLM judge is implemented.

Scores are the fraction of individual checks that pass.

## Artifact Checker

Checks exact relative files and required text:

```json
{
  "type": "artifact",
  "expected_files": ["summary.md"],
  "required_text": {
    "summary.md": ["migration", "backups"]
  }
}
```

`required_text` may map a workspace-relative UTF-8 file to one string or a
list of strings. It may also be a string or list of strings; in that form,
text is searched across `expected_files`. Matching is literal and
case-sensitive.

## Command Checker

Runs a deterministic command in the task workspace:

```json
{
  "type": "command",
  "command": ["python3", "-m", "unittest", "-v"],
  "timeout_sec": 60
}
```

The command is an argument list, is not run through an implicit shell, and
receives an empty environment. It passes only with exit code zero.

## JSON Checker

Checks dotted field paths and exact JSON values:

```json
{
  "type": "json",
  "file": "cleaned.json",
  "required_fields": ["status", "rows.0.name"],
  "expected_values": {
    "status": "clean",
    "row_count": 3
  }
}
```

Paths and files must remain inside the task workspace. Expected values use
normal JSON equality.
