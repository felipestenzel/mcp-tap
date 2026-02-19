"""Classify raw connection errors into structured diagnoses."""

from __future__ import annotations

import re

from mcp_tap.models import ConnectionTestResult, DiagnosisResult, ErrorCategory


def classify_error(error: ConnectionTestResult) -> DiagnosisResult:
    """Map a failed ConnectionTestResult to a structured DiagnosisResult.

    Pattern-matches on error.error to determine the ErrorCategory, then
    produces a human-readable explanation and suggested fix.

    Args:
        error: A ConnectionTestResult with success=False.

    Returns:
        DiagnosisResult with category, explanation, and suggested_fix.
    """
    text = error.error
    lower = text.lower()

    # ── Command not found ────────────────────────────────────
    if _matches_any(lower, ("command not found", "filenotfounderror", "enoent")):
        command = _extract_command(text)
        return DiagnosisResult(
            category=ErrorCategory.COMMAND_NOT_FOUND,
            original_error=text,
            explanation=(
                f"The command '{command}' could not be found on this system. "
                "The package may not be installed, or the binary is not in PATH."
            ),
            suggested_fix=(
                f"Resolve the full path for '{command}' via shutil.which(), "
                "or try an alternative runner (npx/uvx)."
            ),
            confidence=0.95,
        )

    # ── Permission denied ────────────────────────────────────
    if _matches_any(lower, ("permission denied", "eacces")):
        return DiagnosisResult(
            category=ErrorCategory.PERMISSION_DENIED,
            original_error=text,
            explanation=(
                "The server process was denied permission to execute or access "
                "a required resource. This is often caused by file permissions "
                "on the binary or a protected port."
            ),
            suggested_fix=(
                "Check file permissions on the server binary. For npm packages, "
                "try installing with --prefix ~/.local. For protected ports, "
                "use a non-privileged port instead."
            ),
            confidence=0.9,
        )

    # ── Connection refused ───────────────────────────────────
    if _matches_any(lower, ("connection refused", "econnrefused")):
        return DiagnosisResult(
            category=ErrorCategory.CONNECTION_REFUSED,
            original_error=text,
            explanation=(
                "The server's network endpoint refused the connection. "
                "This usually means the backing service (database, API) "
                "is not running or is on a different port."
            ),
            suggested_fix=(
                "Verify that the backing service is running and reachable. "
                "Check the port number in the server config against the "
                "actual service port."
            ),
            confidence=0.9,
        )

    # ── Timeout ──────────────────────────────────────────────
    if _matches_any(lower, ("did not respond within", "timeouterror")):
        return DiagnosisResult(
            category=ErrorCategory.TIMEOUT,
            original_error=text,
            explanation=(
                "The server did not respond within the allotted time. "
                "It may need more time to start, or it may be hanging "
                "due to a missing dependency or misconfigured transport."
            ),
            suggested_fix="Retry with an increased timeout (30s, then 60s).",
            confidence=0.85,
        )

    # ── Auth failed ──────────────────────────────────────────
    if _matches_any(lower, ("401", "403", "authentication", "unauthorized", "auth")):
        return DiagnosisResult(
            category=ErrorCategory.AUTH_FAILED,
            original_error=text,
            explanation=(
                "Authentication failed. The server rejected the provided "
                "credentials or an API key is missing/invalid."
            ),
            suggested_fix=(
                "Check that all required API keys and credentials are set "
                "correctly in the server's env vars. Verify the values are "
                "valid and not expired."
            ),
            confidence=0.8,
        )

    # ── Missing env var ──────────────────────────────────────
    if _looks_like_env_var_error(text, lower):
        var_name = _extract_env_var(text)
        hint = f" ({var_name})" if var_name else ""
        return DiagnosisResult(
            category=ErrorCategory.MISSING_ENV_VAR,
            original_error=text,
            explanation=(
                f"A required environment variable{hint} is not set. "
                "The server cannot start without it."
            ),
            suggested_fix=(
                f"Set the environment variable{hint} in the server's env "
                "config, or pass it via the env_vars parameter when configuring."
            ),
            confidence=0.85,
        )

    # ── Unknown ──────────────────────────────────────────────
    return DiagnosisResult(
        category=ErrorCategory.UNKNOWN,
        original_error=text,
        explanation=(
            f"The server failed with an unrecognized error: {text}. "
            "Manual investigation is needed."
        ),
        suggested_fix="Review the error message and server logs for clues.",
        confidence=0.3,
    )


# ─── Helpers ─────────────────────────────────────────────────


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Return True if any pattern appears in text."""
    return any(p in text for p in patterns)


_ENV_VAR_RE = re.compile(r"[A-Z][A-Z0-9_]{2,}")


def _has_env_var_pattern(text: str) -> bool:
    """Return True if text contains something that looks like an env var name."""
    return bool(_ENV_VAR_RE.search(text))


def _looks_like_env_var_error(text: str, lower: str) -> bool:
    """Return True if the error looks related to a missing env var.

    Matches when keywords (not set / missing / required) are present AND
    either an explicit env var name exists or the phrase "environment variable"
    appears in the message.
    """
    keywords = ("not set", "missing", "required")
    if not _matches_any(lower, keywords):
        return False
    return _has_env_var_pattern(text) or "environment variable" in lower


def _extract_env_var(text: str) -> str:
    """Extract the most likely env var name from an error message."""
    match = _ENV_VAR_RE.search(text)
    return match.group(0) if match else ""


def _extract_command(text: str) -> str:
    """Extract the command name from a 'not found' error message."""
    # Pattern: "Command not found: <command>"
    for pattern in (
        r"Command not found:\s*(\S+)",
        r"FileNotFoundError.*?'([^']+)'",
        r"'(\S+)'.*not found",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "unknown"
