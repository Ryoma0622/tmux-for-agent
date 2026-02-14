---
name: tmux-terminal-executor
description: >
  Execute commands in another terminal via tmux sessions. Use this skill when the agent needs to:
  run commands in a remote server where a human has already authenticated (SSH, Kerberos, etc.),
  read terminal output from another session, interact with a running process in a separate terminal,
  or perform any task that requires operating in a pre-authenticated tmux session.
  Triggers: "run in tmux", "execute in session", "send command to terminal",
  "read terminal output", "check tmux session", operating on remote/authenticated environments.
---

# tmux-terminal-executor

Execute commands in pre-authenticated tmux sessions. The human sets up the session and authenticates; the agent operates within it.

## Prerequisites

- tmux installed and in PATH
- Python 3.10+ (standard library only, no pip installs needed)
- A running tmux session created by the human (e.g., `tmux new -s myserver`)

## Workflow

### 1. Discover available sessions

```bash
python3 {SKILL_DIR}/scripts/list_sessions.py
```

If no sessions exist, ask the human to create one:
```
tmux new -s <session-name>
```

### 2. Execute a command and get output

```bash
python3 {SKILL_DIR}/scripts/run_command.py <session> "<command>" --timeout 30
```

The script uses UUID echo markers to reliably detect command completion and extract output. ANSI escape sequences are automatically stripped.

For long-running commands, increase the timeout:
```bash
python3 {SKILL_DIR}/scripts/run_command.py myserver "make build" --timeout 120
```

### 3. Read current terminal state (without executing)

```bash
python3 {SKILL_DIR}/scripts/read_buffer.py <session>
python3 {SKILL_DIR}/scripts/read_buffer.py <session> --lines 20
python3 {SKILL_DIR}/scripts/read_buffer.py <session> --history
```

Use this to observe what's currently on screen, check prompts, or monitor running processes.

## Important Notes

- **Never create or destroy tmux sessions** — only the human manages session lifecycle
- **Commands execute in the human's authenticated context** — respect the trust boundary
- **Timeout handling**: If a command times out (exit code 2), read the buffer to check progress rather than re-running
- **Interactive commands**: Avoid commands that require interactive input (e.g., `vim`, `less`). Use non-interactive alternatives (`cat`, `head`, flags like `-y` or `--non-interactive`)
- **Multiple commands**: Chain with `&&` or `;` in a single `run_command.py` call rather than running multiple sequential calls

## API Reference

For the full Python API and advanced usage, see [references/api_reference.md](references/api_reference.md).
