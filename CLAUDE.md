# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tmux-for-agent is a Claude Code Skill (`tmux-terminal-executor`) that lets AI agents send commands to and read output from tmux sessions where a human has already authenticated (SSH, Kerberos, etc.). No external dependencies — standard library only, Python 3.10+.

## Project Structure

- **`SKILL.md`** — Skill definition (frontmatter + workflow instructions). This is loaded by Claude Code when the skill triggers.
- **`scripts/tmux_bridge.py`** — Core library. Contains `TmuxController` (a `@dataclass`), exception classes (`TmuxError`, `SessionNotFoundError`, `CommandTimeoutError`), and `strip_ansi` helper. All tmux interaction goes through `_run_tmux()` via `subprocess.run`.
- **`scripts/run_command.py`** — CLI wrapper: execute a command in a tmux session and print output.
- **`scripts/read_buffer.py`** — CLI wrapper: read the current pane buffer without executing anything.
- **`scripts/list_sessions.py`** — CLI wrapper: list available tmux sessions.
- **`references/api_reference.md`** — Full TmuxController API documentation.
- **`tmux-terminal-executor.skill`** — Packaged skill (zip with `.skill` extension), ready to install.

## Commands

**Run scripts directly (requires a running tmux session):**
```bash
uv run scripts/list_sessions.py
uv run scripts/run_command.py myserver "ls -la" --timeout 30
uv run scripts/read_buffer.py myserver --lines 20
```

**Re-package the skill after changes:**
```bash
# Requires the skill-creator skill's package_skill.py
uv run --with pyyaml <path-to-skill-creator>/scripts/package_skill.py .
```

## Architecture

- **Command execution** uses UUID-based echo markers (`__TMUX_BRIDGE_START_<uid>__` / `__TMUX_BRIDGE_END_<uid>__`) to reliably detect completion and extract output. A prompt-pattern fallback exists when `use_markers=False`.
- All scripts include PEP 723 inline metadata for `uv run` support (no `pip install` needed).
