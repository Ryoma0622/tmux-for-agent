# tmux-for-agent

A Python bridge that allows AI Agents to operate authenticated tmux sessions.

## Overview

`TmuxController` enables an AI Agent running in one terminal to send commands to, and read output from, a tmux session where a human has already authenticated (SSH, Kerberos, etc.). This lets agents leverage existing authenticated sessions without needing direct access to credentials.

## Requirements

- Python 3.10+
- tmux installed and available in `PATH`
- No external Python dependencies (standard library only)

## Quick Start

### 1. Human sets up the tmux session

```bash
# Terminal B: Create a tmux session
tmux new -s myserver

# (Optional) Authenticate inside the session
ssh user@remote-host
```

### 2. Agent connects and runs commands

```python
from tmux_bridge import TmuxController

ctrl = TmuxController("myserver")

# Execute a command and get its output
output = ctrl.execute_and_wait("ls -la")
print(output)

# Send keys without waiting
ctrl.send_keys("vim config.yaml")

# Read the current visible buffer
visible = ctrl.read_buffer(lines=10)
```

### 3. Run the example

```bash
uv run example_agent.py
```

## API

### `TmuxController(session_name, prompt_pattern=r"[\$#>] $", default_timeout=30.0, poll_interval=0.3)`

Create a controller attached to an existing tmux session.

| Parameter | Description |
|---|---|
| `session_name` | Name of the tmux session (or full target like `session:window.pane`) |
| `prompt_pattern` | Regex for detecting shell prompts (fallback mode) |
| `default_timeout` | Maximum seconds to wait for command completion |
| `poll_interval` | Seconds between buffer polls |

### Methods

#### `send_keys(text, *, enter=True)`

Send text to the tmux pane. If `enter=True` (default), press Enter after sending.

#### `read_buffer(lines=None, *, history=False)`

Read the current visible content of the pane with ANSI escapes stripped. Pass `lines` to get only the last N lines, or `history=True` to include scroll-back.

#### `execute_and_wait(command, *, timeout=None, poll_interval=None, use_markers=True)`

Send a command, wait for it to complete, and return the output. Uses UUID-based echo markers for reliable output extraction. Falls back to prompt-pattern detection when `use_markers=False`.

#### `TmuxController.list_sessions()` (static)

Return a list of existing tmux session names.

#### `TmuxController.session_exists(name)` (static)

Check whether a tmux session exists.

### Exceptions

| Exception | Description |
|---|---|
| `TmuxError` | Base exception for all tmux bridge errors |
| `SessionNotFoundError` | The target tmux session does not exist |
| `CommandTimeoutError` | A command did not complete within the timeout |

## How It Works

1. The agent wraps each command with unique UUID-based **echo markers** (`__TMUX_BRIDGE_START_<uid>__` and `__TMUX_BRIDGE_END_<uid>__`).
2. It polls the tmux pane buffer until both markers appear.
3. The text between the markers is extracted and cleaned (ANSI escapes stripped, echo lines removed).

This approach reliably detects command completion regardless of the shell prompt format.

## Testing

```bash
uv run -m pytest tests/
```

Tests mock `subprocess.run` so they can run without a real tmux server.

## License

MIT
