"""Safe async subprocess execution for package installation."""

from __future__ import annotations

import asyncio

_OUTPUT_LIMIT = 2000


async def run_command(
    cmd: list[str],
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, str, str]:
    """Run a subprocess with timeout, return (returncode, stdout, stderr).

    Uses asyncio.create_subprocess_exec -- never shell=True.
    Output is truncated to prevent context bloat.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return (-1, "", f"Command timed out after {timeout}s")

    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace")[:_OUTPUT_LIMIT],
        stderr_bytes.decode(errors="replace")[:_OUTPUT_LIMIT],
    )
