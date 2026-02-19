"""Generate candidate fixes from structured diagnoses."""

from __future__ import annotations

import shutil
from dataclasses import replace

from mcp_tap.models import (
    CandidateFix,
    DiagnosisResult,
    ErrorCategory,
    ServerConfig,
)


def generate_fix(
    diagnosis: DiagnosisResult,
    current_config: ServerConfig,
) -> CandidateFix:
    """Produce a CandidateFix for the given diagnosis and current config.

    Some categories yield auto-applicable fixes (new_config is set,
    requires_user_action=False). Others require human intervention
    and return guidance text instead.

    Args:
        diagnosis: The structured error diagnosis.
        current_config: The server's current ServerConfig.

    Returns:
        A CandidateFix describing the proposed remedy.
    """
    category = diagnosis.category

    if category == ErrorCategory.COMMAND_NOT_FOUND:
        return _fix_command_not_found(current_config)

    if category == ErrorCategory.TIMEOUT:
        return _fix_timeout(current_config)

    if category == ErrorCategory.TRANSPORT_MISMATCH:
        return _fix_transport_mismatch(current_config)

    if category == ErrorCategory.CONNECTION_REFUSED:
        return CandidateFix(
            description=(
                "The backing service is not reachable. Verify that the "
                "service (database, API, etc.) is running and the port in "
                "the server config matches the actual service port."
            ),
            requires_user_action=True,
        )

    if category == ErrorCategory.AUTH_FAILED:
        return CandidateFix(
            description=(
                "Authentication failed. Check that all API keys and "
                "credentials in the server's env vars are correct and "
                "not expired."
            ),
            env_var_hint=(
                "Review the env vars configured for this server. Ensure each key/token is valid."
            ),
            requires_user_action=True,
        )

    if category == ErrorCategory.MISSING_ENV_VAR:
        return CandidateFix(
            description=(
                "A required environment variable is missing. Set it in "
                "the server's env config or pass it via env_vars when "
                "calling configure_server."
            ),
            env_var_hint=diagnosis.suggested_fix,
            requires_user_action=True,
        )

    if category == ErrorCategory.PERMISSION_DENIED:
        return CandidateFix(
            description=(
                "Permission denied. Check file permissions on the server "
                "binary and ensure it is executable. For npm global packages, "
                "consider using --prefix ~/.local."
            ),
            requires_user_action=True,
        )

    # UNKNOWN
    return CandidateFix(
        description=(
            f"Unrecognized error: {diagnosis.original_error}. Manual investigation is needed."
        ),
        requires_user_action=True,
    )


# ─── Auto-fix strategies ────────────────────────────────────


def _fix_command_not_found(config: ServerConfig) -> CandidateFix:
    """Try to resolve the command via full path lookup or alternative runner."""
    command = config.command

    # Try full path resolution
    full_path = shutil.which(command)
    if full_path and full_path != command:
        new_config = replace(config, command=full_path)
        return CandidateFix(
            description=(f"Resolved '{command}' to full path '{full_path}'."),
            new_config=new_config,
        )

    # If the command is a direct binary name (not npx/uvx), try wrapping it
    if command not in ("npx", "uvx", "node", "python", "python3"):
        # Try npx wrapper
        npx_path = shutil.which("npx")
        if npx_path:
            new_args = ["-y", command, *config.args]
            new_config = replace(config, command=npx_path, args=new_args)
            return CandidateFix(
                description=f"Wrapped '{command}' with npx runner.",
                new_config=new_config,
            )

        # Try uvx wrapper
        uvx_path = shutil.which("uvx")
        if uvx_path:
            new_args = [command, *config.args]
            new_config = replace(config, command=uvx_path, args=new_args)
            return CandidateFix(
                description=f"Wrapped '{command}' with uvx runner.",
                new_config=new_config,
            )

    # Cannot auto-fix
    return CandidateFix(
        description=(
            f"Command '{command}' not found and no alternative runner "
            "is available. Install the package manually or ensure the "
            "binary is in PATH."
        ),
        requires_user_action=True,
    )


def _fix_timeout(config: ServerConfig) -> CandidateFix:
    """Suggest retrying with an increased timeout."""
    return CandidateFix(
        description=(
            "The server timed out. Will retry with increased timeout. "
            "If it keeps failing, the server may be hanging due to a "
            "missing dependency."
        ),
        new_config=config,
    )


def _fix_transport_mismatch(config: ServerConfig) -> CandidateFix:
    """Add --stdio flag if not present."""
    if "--stdio" not in config.args:
        new_args = [*config.args, "--stdio"]
        new_config = replace(config, args=new_args)
        return CandidateFix(
            description="Added '--stdio' flag to server args.",
            new_config=new_config,
        )

    return CandidateFix(
        description=(
            "The server already has --stdio but transport still fails. "
            "Check if the server expects a different transport protocol."
        ),
        requires_user_action=True,
    )
