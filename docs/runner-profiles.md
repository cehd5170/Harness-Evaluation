# Runner Profiles

A runner profile is JSON executable configuration for one external command.
Only `type: "subprocess"` is supported.

```json
{
  "id": "example-runner",
  "type": "subprocess",
  "command": ["agent", "--prompt-file", "{{prompt_file}}"],
  "cwd": "{{workspace_dir}}",
  "timeout_sec": 1800,
  "env": {
    "PATH": "/usr/local/bin:/usr/bin:/bin"
  },
  "capture": {
    "stdout": "stdout.log",
    "stderr": "stderr.log"
  },
  "artifacts": {
    "glob": ["**/*.json", "final.txt"],
    "exclude": [".git/**"]
  }
}
```

`command` is always an argument list and is executed without an implicit
shell. A profile may explicitly invoke `/bin/sh` if shell behavior is needed.
Review profiles before running them.

## Template Variables

- `{{prompt}}`: task prompt text
- `{{prompt_file}}`: absolute path to the generated `prompt.txt`
- `{{task_id}}`: task id
- `{{task_json}}`: absolute path to the generated `task.json`
- `{{workspace_dir}}`: isolated task workspace
- `{{task_run_dir}}`: task logs and workspace parent
- `{{output_dir}}`: canonical run directory

Templates are supported in `command`, `cwd`, and `env` values. Each command
list entry remains one subprocess argument after rendering.

## Fields

- `id`: non-empty profile id
- `type`: must be `subprocess`
- `command`: non-empty list of strings
- `cwd`: command working directory; defaults to `{{workspace_dir}}` and must
  resolve inside `{{task_run_dir}}`
- `timeout_sec`: positive number; defaults to 300
- `env`: string-to-string object; this is the complete subprocess environment
- `capture.stdout` / `capture.stderr`: `true` for default log names, `false`
  to skip writing, or a relative path under the task run directory
- `artifacts.glob`: string or list of glob patterns relative to the workspace
- `artifacts.exclude`: string or list of excluded workspace patterns

The process environment is not inherited. Include `PATH`, credential
locations, or other variables explicitly when an external CLI requires them.
Avoid putting secret values directly in committed profiles.

The included Codex CLI, Claude Code, Qwen CLI, and DeepAgent files are
examples, not pinned CLI integrations. Adjust their commands for installed
versions and local authentication.
