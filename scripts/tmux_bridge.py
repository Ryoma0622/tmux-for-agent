"""
TmuxController — A bridge for AI Agents to operate authenticated tmux sessions.

This module provides a Python class that allows an AI Agent running in one
terminal to send commands to, and read output from, a tmux session where a
human has already authenticated (SSH, Kerberos, etc.).

Usage:
    1. Human starts a tmux session:  tmux new -s myserver
    2. Human authenticates (ssh, rl, etc.) inside that session.
    3. Agent uses TmuxController("myserver") to interact with it.

Dependencies: Python 3.10+ standard library only.
"""

from __future__ import annotations

import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field


class TmuxError(Exception):
    """Base exception for tmux bridge errors."""


class SessionNotFoundError(TmuxError):
    """Raised when the target tmux session does not exist."""


class CommandTimeoutError(TmuxError):
    """Raised when execute_and_wait exceeds its timeout."""


# ---------------------------------------------------------------------------
# ANSI escape sequence pattern
# Covers: CSI sequences, OSC sequences, simple escapes
# ---------------------------------------------------------------------------
_ANSI_RE = re.compile(
    r"""
    \x1b          # ESC
    (?:
        \[        # CSI
        [0-9;?]*  # parameter bytes
        [A-Za-z]  # final byte
      |
        \]        # OSC
        .*?       # payload
        (?:\x07|\x1b\\)  # ST (BEL or ESC\)
      |
        [()][AB012]      # character set selection
      |
        [>=]             # keypad mode
      |
        \#[0-9]          # DEC line attrs
    )
    """,
    re.VERBOSE,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text* and return plain text."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# TmuxController
# ---------------------------------------------------------------------------

@dataclass
class TmuxController:
    """Control a tmux pane: send keys, read buffer, execute commands.

    Parameters
    ----------
    session_name:
        Name (or target specification ``session:window.pane``) of the tmux
        session to attach to.  The session must already exist.
    prompt_pattern:
        Regular expression used as a *fallback* completion signal in
        :meth:`execute_and_wait`.  The primary mechanism uses echo markers.
    default_timeout:
        Default timeout in seconds for :meth:`execute_and_wait`.
    poll_interval:
        Seconds between buffer polls when waiting for command completion.
    """

    session_name: str
    prompt_pattern: str = r"[\$#>] $"
    default_timeout: float = 30.0
    poll_interval: float = 0.3
    _target: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # If the caller passed a full target (session:window.pane), use it
        # directly; otherwise target the default pane.
        if ":" in self.session_name or "." in self.session_name:
            self._target = self.session_name
        else:
            self._target = self.session_name

        # Validate that the session exists.
        if not self._session_exists():
            raise SessionNotFoundError(
                f"tmux session '{self.session_name}' does not exist. "
                f"Available sessions: {self.list_sessions()}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_keys(self, text: str, *, enter: bool = True) -> None:
        """Send *text* to the target pane.

        Parameters
        ----------
        text:
            The string to type into the pane.
        enter:
            If ``True`` (default), press Enter after sending the text.
        """
        args = ["send-keys", "-t", self._target, text]
        if enter:
            args.append("Enter")
        self._run_tmux(*args)

    def read_buffer(
        self,
        lines: int | None = None,
        *,
        history: bool = False,
    ) -> str:
        """Read the current visible content of the pane.

        Parameters
        ----------
        lines:
            If given, return only the last *lines* lines of the buffer.
        history:
            If ``True``, include the scroll-back history (``-S -``).

        Returns
        -------
        str
            Plain text with ANSI escapes stripped.
        """
        args = ["capture-pane", "-t", self._target, "-p"]
        if history:
            args.extend(["-S", "-"])
        raw = self._run_tmux(*args)
        cleaned = strip_ansi(raw)
        if lines is not None:
            cleaned = "\n".join(cleaned.splitlines()[-lines:])
        return cleaned

    def execute_and_wait(
        self,
        command: str,
        *,
        timeout: float | None = None,
        poll_interval: float | None = None,
        use_markers: bool = True,
    ) -> str:
        """Send *command*, wait for completion, and return the output.

        The method uses **echo markers** (unique UUIDs printed before and
        after the command) to reliably detect when the command has finished
        and to extract only the relevant output.

        If *use_markers* is ``False``, it falls back to polling the buffer
        for the ``prompt_pattern``.

        Parameters
        ----------
        command:
            Shell command to execute.
        timeout:
            Maximum seconds to wait.  Defaults to ``self.default_timeout``.
        poll_interval:
            Override the default poll interval for this call.
        use_markers:
            When ``True`` (default), wrap the command with echo markers for
            reliable output extraction.

        Returns
        -------
        str
            The command's output (text between the markers), with ANSI
            escapes removed.

        Raises
        ------
        CommandTimeoutError
            If the command does not complete within *timeout* seconds.
        """
        timeout = timeout if timeout is not None else self.default_timeout
        interval = poll_interval if poll_interval is not None else self.poll_interval

        if use_markers:
            return self._execute_with_markers(command, timeout, interval)
        return self._execute_with_prompt(command, timeout, interval)

    # ------------------------------------------------------------------
    # Class / static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def list_sessions() -> list[str]:
        """Return a list of existing tmux session names."""
        try:
            out = TmuxController._run_tmux(
                "list-sessions", "-F", "#{session_name}"
            )
            return [s for s in out.splitlines() if s.strip()]
        except TmuxError:
            return []

    @staticmethod
    def session_exists(name: str) -> bool:
        """Check whether a tmux session *name* exists."""
        return name in TmuxController.list_sessions()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_exists(self) -> bool:
        """Check that our target session is reachable."""
        try:
            self._run_tmux("has-session", "-t", self._target)
            return True
        except TmuxError:
            return False

    def _execute_with_markers(
        self, command: str, timeout: float, interval: float
    ) -> str:
        """Marker-based synchronous execution."""
        uid = uuid.uuid4().hex[:12]
        start_marker = f"__TMUX_BRIDGE_START_{uid}__"
        end_marker = f"__TMUX_BRIDGE_END_{uid}__"

        # Send: start marker → command → end marker
        self.send_keys(f"echo '{start_marker}'", enter=True)
        # Small pause so the marker echo appears before the command
        time.sleep(0.05)
        self.send_keys(command, enter=True)
        # We chain the end marker after the command finishes via shell &&/;
        # But since we can't chain reliably (the command might fail), we
        # send the end-marker echo as a separate command.  The shell will
        # execute it after the previous command returns.
        self.send_keys(f"echo '{end_marker}'", enter=True)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            buf = self.read_buffer(history=True)
            # Look for both markers in the buffer
            start_idx = buf.rfind(start_marker)
            end_idx = buf.rfind(end_marker)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                # Extract text between markers
                output = buf[start_idx + len(start_marker): end_idx]
                return self._clean_marker_output(output, command)
            time.sleep(interval)

        raise CommandTimeoutError(
            f"Command did not complete within {timeout}s: {command!r}"
        )

    def _execute_with_prompt(
        self, command: str, timeout: float, interval: float
    ) -> str:
        """Prompt-pattern fallback for synchronous execution."""
        # Capture buffer before sending the command
        pre_buffer = self.read_buffer(history=True)

        self.send_keys(command, enter=True)
        prompt_re = re.compile(self.prompt_pattern, re.MULTILINE)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(interval)
            buf = self.read_buffer(history=True)
            # New content is everything after the old buffer
            new_content = buf[len(pre_buffer):]
            lines = new_content.splitlines()
            if lines and prompt_re.search(lines[-1]):
                # Remove the last line (prompt) and the first line (echo of
                # the typed command).
                output_lines = lines[1:-1] if len(lines) > 1 else []
                return "\n".join(output_lines)
            # Also check visible pane (last line)
            visible = self.read_buffer(lines=1)
            if prompt_re.search(visible):
                new_content = buf[len(pre_buffer):]
                output_lines = new_content.splitlines()
                if output_lines:
                    output_lines = output_lines[1:]  # remove echoed command
                if output_lines and prompt_re.search(output_lines[-1]):
                    output_lines = output_lines[:-1]  # remove prompt
                return "\n".join(output_lines)

        raise CommandTimeoutError(
            f"Prompt not detected within {timeout}s: {command!r}"
        )

    @staticmethod
    def _clean_marker_output(raw: str, command: str) -> str:
        """Clean up the output between markers.

        Removes:
        - The echo command lines for the markers themselves
        - The echoed command line
        - Leading/trailing blank lines
        """
        # Regex to strip common shell prompt prefixes (e.g. "$ ", "# ", "> ")
        prompt_prefix_re = re.compile(r"^[\$#>]\s*")

        lines = raw.splitlines()
        cleaned: list[str] = []
        cmd_stripped = command.strip()
        for line in lines:
            stripped = line.strip()
            # Strip prompt prefix for comparison purposes
            without_prompt = prompt_prefix_re.sub("", stripped)
            # Skip the echo commands for markers
            if without_prompt.startswith("echo '__TMUX_BRIDGE_"):
                continue
            # Skip the echoed command (with or without prompt prefix)
            if without_prompt == cmd_stripped:
                continue
            # Skip shell prompts that echo the marker/command
            # (e.g. "$ echo '__TMUX_BRIDGE_START_xxx__'")
            if "__TMUX_BRIDGE_" in stripped:
                continue
            cleaned.append(line)

        # Strip leading/trailing empty lines
        text = "\n".join(cleaned).strip()
        # Also remove the prompt line at the end if present
        return text

    @staticmethod
    def _run_tmux(*args: str) -> str:
        """Run a tmux subcommand and return stdout.

        Raises :class:`TmuxError` on non-zero exit.
        """
        cmd = ["tmux", *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise TmuxError(
                "tmux is not installed or not in PATH"
            ) from None
        except subprocess.TimeoutExpired:
            raise TmuxError(
                f"tmux command timed out: {' '.join(cmd)}"
            ) from None

        if result.returncode != 0:
            raise TmuxError(
                f"tmux command failed (rc={result.returncode}): "
                f"{' '.join(cmd)}\nstderr: {result.stderr.strip()}"
            )
        return result.stdout
