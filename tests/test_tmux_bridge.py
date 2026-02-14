# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Unit tests for tmux_bridge.TmuxController.

These tests mock subprocess.run so they can run without a real tmux server.

    uv run tests/test_tmux_bridge.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# Ensure the project root is on sys.path so `import tmux_bridge` works
# regardless of which directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tmux_bridge import (
    CommandTimeoutError,
    SessionNotFoundError,
    TmuxController,
    strip_ansi,
)


class TestStripAnsi(unittest.TestCase):
    """Tests for the strip_ansi helper."""

    def test_plain_text_unchanged(self):
        self.assertEqual(strip_ansi("hello world"), "hello world")

    def test_removes_color_codes(self):
        colored = "\x1b[31mERROR\x1b[0m: something failed"
        self.assertEqual(strip_ansi(colored), "ERROR: something failed")

    def test_removes_bold_and_underline(self):
        text = "\x1b[1m\x1b[4mTitle\x1b[0m"
        self.assertEqual(strip_ansi(text), "Title")

    def test_removes_cursor_movement(self):
        text = "\x1b[2J\x1b[H\x1b[3;1Hfoo"
        self.assertEqual(strip_ansi(text), "foo")

    def test_removes_osc_sequences(self):
        text = "\x1b]0;user@host:~\x07$ ls"
        self.assertEqual(strip_ansi(text), "$ ls")

    def test_multiline(self):
        text = "\x1b[32mline1\x1b[0m\n\x1b[33mline2\x1b[0m"
        self.assertEqual(strip_ansi(text), "line1\nline2")

    def test_empty_string(self):
        self.assertEqual(strip_ansi(""), "")

    def test_256_color(self):
        text = "\x1b[38;5;196mred\x1b[0m"
        self.assertEqual(strip_ansi(text), "red")


def _make_run_mock(
    *,
    has_session_ok: bool = True,
    capture_output: str = "",
    list_sessions_output: str = "myserver\n",
):
    """Build a side_effect function for subprocess.run."""

    def side_effect(cmd, **kwargs):
        mock_result = MagicMock()
        if cmd[1] == "has-session":
            mock_result.returncode = 0 if has_session_ok else 1
            mock_result.stdout = ""
            mock_result.stderr = "" if has_session_ok else "session not found"
        elif cmd[1] == "capture-pane":
            mock_result.returncode = 0
            mock_result.stdout = capture_output
            mock_result.stderr = ""
        elif cmd[1] == "send-keys":
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
        elif cmd[1] == "list-sessions":
            mock_result.returncode = 0
            mock_result.stdout = list_sessions_output
            mock_result.stderr = ""
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
        return mock_result

    return side_effect


class TestTmuxControllerInit(unittest.TestCase):
    """Tests for session validation at init time."""

    @patch("tmux_bridge.subprocess.run")
    def test_valid_session(self, mock_run):
        mock_run.side_effect = _make_run_mock(has_session_ok=True)
        ctrl = TmuxController("myserver")
        self.assertEqual(ctrl.session_name, "myserver")
        self.assertEqual(ctrl._target, "myserver")

    @patch("tmux_bridge.subprocess.run")
    def test_missing_session_raises(self, mock_run):
        mock_run.side_effect = _make_run_mock(
            has_session_ok=False, list_sessions_output=""
        )
        with self.assertRaises(SessionNotFoundError):
            TmuxController("nonexistent")

    @patch("tmux_bridge.subprocess.run")
    def test_custom_target_with_colon(self, mock_run):
        mock_run.side_effect = _make_run_mock(has_session_ok=True)
        ctrl = TmuxController("myserver:0.1")
        self.assertEqual(ctrl._target, "myserver:0.1")


class TestSendKeys(unittest.TestCase):
    """Tests for send_keys."""

    @patch("tmux_bridge.subprocess.run")
    def test_send_with_enter(self, mock_run):
        mock_run.side_effect = _make_run_mock()
        ctrl = TmuxController("myserver")

        ctrl.send_keys("ls -la")
        # Find the send-keys call
        send_calls = [
            c for c in mock_run.call_args_list if "send-keys" in c[0][0]
        ]
        last_call = send_calls[-1]
        cmd = last_call[0][0]
        self.assertIn("send-keys", cmd)
        self.assertIn("Enter", cmd)

    @patch("tmux_bridge.subprocess.run")
    def test_send_without_enter(self, mock_run):
        mock_run.side_effect = _make_run_mock()
        ctrl = TmuxController("myserver")

        ctrl.send_keys("partial text", enter=False)
        send_calls = [
            c for c in mock_run.call_args_list if "send-keys" in c[0][0]
        ]
        last_call = send_calls[-1]
        cmd = last_call[0][0]
        self.assertIn("send-keys", cmd)
        self.assertNotIn("Enter", cmd)


class TestReadBuffer(unittest.TestCase):
    """Tests for read_buffer."""

    @patch("tmux_bridge.subprocess.run")
    def test_read_full_buffer(self, mock_run):
        mock_run.side_effect = _make_run_mock(
            capture_output="line1\nline2\nline3\n"
        )
        ctrl = TmuxController("myserver")
        result = ctrl.read_buffer()
        self.assertIn("line1", result)
        self.assertIn("line3", result)

    @patch("tmux_bridge.subprocess.run")
    def test_read_last_n_lines(self, mock_run):
        mock_run.side_effect = _make_run_mock(
            capture_output="line1\nline2\nline3\nline4\nline5\n"
        )
        ctrl = TmuxController("myserver")
        result = ctrl.read_buffer(lines=2)
        lines = result.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "line4")
        self.assertEqual(lines[1], "line5")

    @patch("tmux_bridge.subprocess.run")
    def test_read_strips_ansi(self, mock_run):
        mock_run.side_effect = _make_run_mock(
            capture_output="\x1b[32mgreen text\x1b[0m\n"
        )
        ctrl = TmuxController("myserver")
        result = ctrl.read_buffer()
        self.assertNotIn("\x1b", result)
        self.assertIn("green text", result)


class TestListSessions(unittest.TestCase):
    """Tests for list_sessions class method."""

    @patch("tmux_bridge.subprocess.run")
    def test_returns_session_names(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "session1\nsession2\nsession3\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        sessions = TmuxController.list_sessions()
        self.assertEqual(sessions, ["session1", "session2", "session3"])

    @patch("tmux_bridge.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "no server running"
        mock_run.return_value = mock_result

        sessions = TmuxController.list_sessions()
        self.assertEqual(sessions, [])


class TestExecuteAndWaitMarkers(unittest.TestCase):
    """Tests for execute_and_wait with marker-based synchronization."""

    @patch("tmux_bridge.subprocess.run")
    @patch("tmux_bridge.time.sleep")
    @patch("tmux_bridge.time.monotonic")
    def test_successful_execution(self, mock_monotonic, mock_sleep, mock_run):
        """Simulate a command whose output appears in the buffer with markers."""
        # Time: start at 0, advance past the first poll, still within timeout
        mock_monotonic.side_effect = [0, 0.1, 0.2, 0.3, 0.5, 0.6, 0.8]

        call_count = {"n": 0}

        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""

            if cmd[1] == "has-session":
                mock_result.stdout = ""
            elif cmd[1] == "send-keys":
                # Capture the marker IDs from the first send-keys call
                mock_result.stdout = ""
                if "TMUX_BRIDGE_START" in str(cmd):
                    # Extract the uid from the echo command
                    for arg in cmd:
                        if "__TMUX_BRIDGE_START_" in str(arg):
                            run_side_effect._start_marker_cmd = arg
                elif "TMUX_BRIDGE_END" in str(cmd):
                    for arg in cmd:
                        if "__TMUX_BRIDGE_END_" in str(arg):
                            run_side_effect._end_marker_cmd = arg
            elif cmd[1] == "capture-pane":
                call_count["n"] += 1
                if call_count["n"] >= 2:
                    # On the 2nd capture, show the complete output with markers
                    start = getattr(
                        run_side_effect, "_start_marker_text", "__TMUX_BRIDGE_START_test123__"
                    )
                    end = getattr(
                        run_side_effect, "_end_marker_text", "__TMUX_BRIDGE_END_test123__"
                    )
                    mock_result.stdout = (
                        f"$ echo '{start}'\n"
                        f"{start}\n"
                        f"$ ls -la\n"
                        f"total 0\n"
                        f"drwxr-xr-x  2 user user  40 Jan  1 00:00 .\n"
                        f"drwxr-xr-x  3 user user  60 Jan  1 00:00 ..\n"
                        f"$ echo '{end}'\n"
                        f"{end}\n"
                        f"$\n"
                    )
                else:
                    mock_result.stdout = "$ \n"
            else:
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        ctrl = TmuxController("myserver", default_timeout=5, poll_interval=0.1)

        # We need to intercept the actual marker UUIDs.  Since execute_and_wait
        # generates them internally, we'll just check that the method returns
        # plausible output by monkeypatching uuid.
        with patch("tmux_bridge.uuid.uuid4") as mock_uuid:
            mock_uuid_obj = MagicMock()
            mock_uuid_obj.hex = "test123test1"  # 12 chars
            mock_uuid.return_value = mock_uuid_obj
            # Set the expected marker text
            run_side_effect._start_marker_text = "__TMUX_BRIDGE_START_test123test__"
            run_side_effect._end_marker_text = "__TMUX_BRIDGE_END_test123test__"

            # Need to also set marker for 12-char slice
            run_side_effect._start_marker_text = "__TMUX_BRIDGE_START_test123test__"
            run_side_effect._end_marker_text = "__TMUX_BRIDGE_END_test123test__"

            # Fix: the actual code uses hex[:12]
            mock_uuid_obj.hex = "abcdef123456rest"
            run_side_effect._start_marker_text = "__TMUX_BRIDGE_START_abcdef123456__"
            run_side_effect._end_marker_text = "__TMUX_BRIDGE_END_abcdef123456__"

            mock_result_stdout = (
                f"$ echo '__TMUX_BRIDGE_START_abcdef123456__'\n"
                f"__TMUX_BRIDGE_START_abcdef123456__\n"
                f"$ ls -la\n"
                f"total 0\n"
                f"drwxr-xr-x  2 user user  40 Jan  1 00:00 .\n"
                f"drwxr-xr-x  3 user user  60 Jan  1 00:00 ..\n"
                f"$ echo '__TMUX_BRIDGE_END_abcdef123456__'\n"
                f"__TMUX_BRIDGE_END_abcdef123456__\n"
                f"$\n"
            )

            # Override capture-pane to always return the complete buffer
            original_side_effect = mock_run.side_effect

            def patched_run(cmd, **kwargs):
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                if cmd[1] == "capture-pane":
                    mock_result.stdout = mock_result_stdout
                elif cmd[1] == "has-session":
                    mock_result.stdout = ""
                else:
                    mock_result.stdout = ""
                return mock_result

            # Reset the mock for the actual test
            mock_run.side_effect = patched_run

            # Re-create controller with patched mock
            ctrl = TmuxController("myserver", default_timeout=5, poll_interval=0.1)
            result = ctrl.execute_and_wait("ls -la")

        self.assertIn("total 0", result)
        self.assertIn("drwxr-xr-x", result)
        # Markers should NOT be in the result
        self.assertNotIn("__TMUX_BRIDGE_START_", result)
        self.assertNotIn("__TMUX_BRIDGE_END_", result)

    @patch("tmux_bridge.subprocess.run")
    @patch("tmux_bridge.time.sleep")
    @patch("tmux_bridge.time.monotonic")
    def test_timeout_raises(self, mock_monotonic, mock_sleep, mock_run):
        """If the end marker never appears, CommandTimeoutError is raised."""
        # Time: immediately exceeds timeout
        mock_monotonic.side_effect = [0, 0, 100, 100]

        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            if cmd[1] == "capture-pane":
                mock_result.stdout = "$ \n"  # no markers
            else:
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        ctrl = TmuxController("myserver", default_timeout=1, poll_interval=0.1)
        with self.assertRaises(CommandTimeoutError):
            ctrl.execute_and_wait("sleep 999")


class TestCleanMarkerOutput(unittest.TestCase):
    """Tests for _clean_marker_output."""

    def test_basic_cleaning(self):
        raw = (
            "\n"
            "$ echo '__TMUX_BRIDGE_START_abc__'\n"
            "__TMUX_BRIDGE_START_abc__\n"
            "$ ls\n"
            "file1.txt\n"
            "file2.txt\n"
            "$ echo '__TMUX_BRIDGE_END_abc__'\n"
        )
        # The method receives text BETWEEN the markers, so only the inner part:
        inner = (
            "\n"
            "$ ls\n"
            "file1.txt\n"
            "file2.txt\n"
            "$ echo '__TMUX_BRIDGE_END_abc__'\n"
        )
        result = TmuxController._clean_marker_output(inner, "ls")
        self.assertIn("file1.txt", result)
        self.assertIn("file2.txt", result)
        self.assertNotIn("__TMUX_BRIDGE_", result)
        self.assertNotIn("$ ls", result)

    def test_empty_output(self):
        result = TmuxController._clean_marker_output("", "true")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
