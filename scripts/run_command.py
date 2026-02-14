#!/usr/bin/env python3
"""Run a command in a tmux session and print the output.

Usage:
    python3 run_command.py <session_name> <command> [--timeout SECONDS]

Examples:
    python3 run_command.py myserver "ls -la"
    python3 run_command.py myserver "kubectl get pods" --timeout 60
"""

import argparse
import sys
import os

# Add scripts directory to path so tmux_bridge can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tmux_bridge import TmuxController, TmuxError, CommandTimeoutError


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a command in a tmux session")
    parser.add_argument("session", help="tmux session name")
    parser.add_argument("command", help="Command to execute")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds (default: 30)")
    parser.add_argument("--no-markers", action="store_true", help="Use prompt detection instead of markers")
    args = parser.parse_args()

    try:
        ctrl = TmuxController(args.session, default_timeout=args.timeout)
        output = ctrl.execute_and_wait(args.command, use_markers=not args.no_markers)
        print(output)
    except CommandTimeoutError as e:
        print(f"TIMEOUT: {e}", file=sys.stderr)
        sys.exit(2)
    except TmuxError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
