#!/usr/bin/env python3
"""List available tmux sessions.

Usage:
    python3 list_sessions.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tmux_bridge import TmuxController


def main() -> None:
    sessions = TmuxController.list_sessions()
    if not sessions:
        print("No tmux sessions found.", file=sys.stderr)
        print("Start one with: tmux new -s <name>", file=sys.stderr)
        sys.exit(1)
    for name in sessions:
        print(name)


if __name__ == "__main__":
    main()
