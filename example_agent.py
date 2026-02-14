#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Example: An AI Agent using TmuxController to execute commands on a
human-authenticated tmux session.

Prerequisites
-------------
1. Create a tmux session on Terminal B:
       tmux new -s myserver

2. (Optional) SSH into a remote host inside that session:
       ssh user@remote-host

3. Run this script from Terminal A:
       uv run example_agent.py

The script will:
  - Connect to the 'myserver' tmux session
  - Run `ls -la` and count the files
  - Run `whoami` and `hostname`
  - Demonstrate reading the visible buffer
"""

from __future__ import annotations

import sys

from tmux_bridge import (
    CommandTimeoutError,
    SessionNotFoundError,
    TmuxController,
)

SESSION_NAME = "myserver"


def main() -> None:
    # ----------------------------------------------------------------
    # 1. Connect to the tmux session
    # ----------------------------------------------------------------
    print(f"[*] Connecting to tmux session '{SESSION_NAME}' ...")
    try:
        ctrl = TmuxController(SESSION_NAME, default_timeout=15)
    except SessionNotFoundError as exc:
        print(f"[!] {exc}")
        print(f"    Hint: run 'tmux new -s {SESSION_NAME}' first.")
        sys.exit(1)

    print(f"[+] Connected.  Available sessions: {ctrl.list_sessions()}")

    # ----------------------------------------------------------------
    # 2. Run `ls -la` and parse the output
    # ----------------------------------------------------------------
    print("\n[*] Executing: ls -la")
    try:
        output = ctrl.execute_and_wait("ls -la")
    except CommandTimeoutError:
        print("[!] Command timed out.")
        sys.exit(1)

    print("--- output ---")
    print(output)
    print("--- end ---")

    # Count entries (skip the 'total' header line and empty lines)
    entries = [
        line for line in output.splitlines()
        if line.strip() and not line.startswith("total")
    ]
    print(f"\n[+] Number of entries (including . and ..): {len(entries)}")

    # ----------------------------------------------------------------
    # 3. Run `whoami` and `hostname`
    # ----------------------------------------------------------------
    for cmd in ("whoami", "hostname"):
        print(f"\n[*] Executing: {cmd}")
        result = ctrl.execute_and_wait(cmd)
        print(f"    => {result.strip()}")

    # ----------------------------------------------------------------
    # 4. Read the current visible buffer
    # ----------------------------------------------------------------
    print("\n[*] Current visible buffer (last 5 lines):")
    visible = ctrl.read_buffer(lines=5)
    for line in visible.splitlines():
        print(f"    | {line}")

    # ----------------------------------------------------------------
    # 5. Non-blocking send (e.g. for interactive programs)
    # ----------------------------------------------------------------
    print("\n[*] Sending Ctrl-L (clear screen) without waiting ...")
    ctrl.send_keys("", enter=False)  # just demonstrate send_keys
    print("[+] Done.")


if __name__ == "__main__":
    main()
