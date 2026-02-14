#!/usr/bin/env python3
"""Read the current buffer content of a tmux pane.

Usage:
    python3 read_buffer.py <session_name> [--lines N] [--history]

Examples:
    python3 read_buffer.py myserver
    python3 read_buffer.py myserver --lines 20
    python3 read_buffer.py myserver --history
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tmux_bridge import TmuxController, TmuxError


def main() -> None:
    parser = argparse.ArgumentParser(description="Read tmux pane buffer")
    parser.add_argument("session", help="tmux session name")
    parser.add_argument("--lines", type=int, default=None, help="Number of lines to read (from bottom)")
    parser.add_argument("--history", action="store_true", help="Include scroll-back history")
    args = parser.parse_args()

    try:
        ctrl = TmuxController(args.session)
        output = ctrl.read_buffer(lines=args.lines, history=args.history)
        print(output)
    except TmuxError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
