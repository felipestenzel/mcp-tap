"""Tests for installer/subprocess.py -- orphan process prevention (Fix C3)."""

from __future__ import annotations

import signal
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_tap.installer.subprocess import run_command

# === Normal execution ========================================================


class TestRunCommandNormal:
    """Tests for successful, non-timeout command execution."""

    async def test_returns_exit_code_stdout_stderr(self):
        """Should return (returncode, stdout, stderr) on normal completion."""
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"hello", b""))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            code, out, err = await run_command(["echo", "hello"])

        assert code == 0
        assert out == "hello"
        assert err == ""

    async def test_start_new_session_is_passed(self):
        """Should pass start_new_session=True to create_subprocess_exec."""
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await run_command(["ls"])

        _, kwargs = mock_exec.call_args
        assert kwargs["start_new_session"] is True

    async def test_nonzero_exit_code_returned(self):
        """Should return the actual nonzero exit code from the process."""
        proc = AsyncMock()
        proc.returncode = 42
        proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            code, _out, err = await run_command(["false"])

        assert code == 42
        assert err == "error"

    async def test_none_returncode_treated_as_zero(self):
        """Should treat None returncode as 0 (proc.returncode or 0)."""
        proc = AsyncMock()
        proc.returncode = None
        proc.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            code, _, _ = await run_command(["true"])

        assert code == 0

    async def test_output_truncated_to_limit(self):
        """Should truncate stdout and stderr to _OUTPUT_LIMIT (2000) chars."""
        big_output = b"x" * 5000
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(big_output, big_output))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            _, out, err = await run_command(["big"])

        assert len(out) == 2000
        assert len(err) == 2000

    async def test_env_passed_to_subprocess(self):
        """Should pass env dict to create_subprocess_exec."""
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        custom_env = {"PATH": "/usr/bin", "MY_VAR": "value"}

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await run_command(["cmd"], env=custom_env)

        _, kwargs = mock_exec.call_args
        assert kwargs["env"] == custom_env

    async def test_decode_errors_replaced(self):
        """Should decode with errors='replace' for invalid UTF-8."""
        bad_bytes = b"hello \xff world"
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(bad_bytes, b""))

        with patch(
            "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            _, out, _ = await run_command(["cmd"])

        # Should not raise, should replace invalid byte
        assert "hello" in out
        assert "\ufffd" in out


# === Timeout handling ========================================================


class TestRunCommandTimeout:
    """Tests for timeout behavior and process group killing."""

    async def test_timeout_returns_negative_one_with_message(self):
        """Should return (-1, '', timeout message) when command times out."""
        proc = AsyncMock()
        proc.pid = 12345
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("mcp_tap.installer.subprocess.os.killpg"),
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=12345),
        ):
            code, out, err = await run_command(["slow"], timeout=5.0)

        assert code == -1
        assert out == ""
        assert "timed out after 5.0s" in err

    async def test_timeout_calls_killpg_with_sigkill(self):
        """Should call os.killpg with SIGKILL on timeout."""
        proc = AsyncMock()
        proc.pid = 99
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("mcp_tap.installer.subprocess.os.killpg") as mock_killpg,
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=999),
        ):
            await run_command(["slow"], timeout=1.0)

        mock_killpg.assert_called_once_with(999, signal.SIGKILL)

    async def test_timeout_falls_back_to_proc_kill_on_process_lookup_error(self):
        """Should fall back to proc.kill() when killpg raises ProcessLookupError."""
        proc = AsyncMock()
        proc.pid = 99
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch(
                "mcp_tap.installer.subprocess.os.killpg",
                side_effect=ProcessLookupError("No such process"),
            ),
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=999),
        ):
            code, _, _err = await run_command(["slow"], timeout=1.0)

        proc.kill.assert_called_once()
        assert code == -1

    async def test_timeout_falls_back_to_proc_kill_on_oserror(self):
        """Should fall back to proc.kill() when killpg raises OSError."""
        proc = AsyncMock()
        proc.pid = 99
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch(
                "mcp_tap.installer.subprocess.os.killpg",
                side_effect=OSError("Operation not permitted"),
            ),
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=999),
        ):
            code, _, _err = await run_command(["slow"], timeout=1.0)

        proc.kill.assert_called_once()
        assert code == -1

    async def test_timeout_calls_proc_wait_after_kill(self):
        """Should call proc.wait() after killing process on timeout."""
        proc = AsyncMock()
        proc.pid = 99
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("mcp_tap.installer.subprocess.os.killpg"),
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=999),
        ):
            await run_command(["slow"], timeout=1.0)

        proc.wait.assert_awaited_once()

    async def test_timeout_message_includes_duration(self):
        """Should include the actual timeout duration in the error message."""
        proc = AsyncMock()
        proc.pid = 99
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with (
            patch(
                "mcp_tap.installer.subprocess.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("mcp_tap.installer.subprocess.os.killpg"),
            patch("mcp_tap.installer.subprocess.os.getpgid", return_value=999),
        ):
            _, _, err = await run_command(["slow"], timeout=30.0)

        assert "30.0s" in err
