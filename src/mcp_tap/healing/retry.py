"""Orchestrate the diagnose-fix-retry healing loop."""

from __future__ import annotations

import logging

from mcp_tap.connection.tester import test_server_connection
from mcp_tap.healing.classifier import classify_error
from mcp_tap.healing.fixer import generate_fix
from mcp_tap.models import (
    ConnectionTestResult,
    HealingAttempt,
    HealingResult,
    ServerConfig,
)

logger = logging.getLogger(__name__)

# Escalating timeouts for retry attempts
_TIMEOUT_ESCALATION = (15, 30, 60)


async def heal_and_retry(
    server_name: str,
    server_config: ServerConfig,
    error: ConnectionTestResult,
    *,
    max_attempts: int = 2,
    timeout_seconds: int = 15,
) -> HealingResult:
    """Diagnose an error, apply a fix, and retry validation.

    Loops up to max_attempts times. Each iteration:
    1. Classify the error into a structured diagnosis
    2. Generate a candidate fix
    3. If the fix requires user action, stop and return guidance
    4. If auto-fixable, apply the fix and re-validate
    5. If validation passes, return success
    6. If validation fails again, loop with the new error

    Args:
        server_name: Name of the server being healed.
        server_config: Current server configuration.
        error: The ConnectionTestResult that triggered healing.
        max_attempts: Maximum number of healing iterations.
        timeout_seconds: Base timeout for re-validation.

    Returns:
        HealingResult with fixed status, all attempts, and guidance
        if user action is needed.
    """
    attempts: list[HealingAttempt] = []
    current_config = server_config
    current_error = error

    for attempt_num in range(1, max_attempts + 1):
        logger.info(
            "Healing attempt %d/%d for '%s'",
            attempt_num,
            max_attempts,
            server_name,
        )

        # 1. Classify the error
        diagnosis = classify_error(current_error)
        logger.info(
            "Diagnosed '%s' as %s (confidence=%.2f)",
            server_name,
            diagnosis.category,
            diagnosis.confidence,
        )

        # 2. Generate a candidate fix
        fix = generate_fix(diagnosis, current_config)

        # 3. If user action required, stop early
        if fix.requires_user_action:
            attempts.append(
                HealingAttempt(
                    diagnosis=diagnosis,
                    fix_applied=fix,
                    success=False,
                )
            )
            return HealingResult(
                fixed=False,
                attempts=attempts,
                fixed_config=current_config,
                user_action_needed=fix.description,
            )

        # 4. Apply auto-fix
        if fix.new_config is not None:
            current_config = fix.new_config

        # Determine timeout: escalate for TIMEOUT category, else use provided
        timeout = _resolve_timeout(diagnosis.category.value, attempt_num, timeout_seconds)

        # 5. Re-validate
        result = await test_server_connection(
            server_name,
            current_config,
            timeout_seconds=timeout,
        )

        attempts.append(
            HealingAttempt(
                diagnosis=diagnosis,
                fix_applied=fix,
                success=result.success,
            )
        )

        if result.success:
            logger.info("Healing succeeded for '%s' on attempt %d", server_name, attempt_num)
            return HealingResult(
                fixed=True,
                attempts=attempts,
                fixed_config=current_config,
            )

        # 6. Loop with the new error
        current_error = result
        logger.warning(
            "Healing attempt %d failed for '%s': %s",
            attempt_num,
            server_name,
            result.error,
        )

    # Exhausted all attempts
    return HealingResult(
        fixed=False,
        attempts=attempts,
        fixed_config=current_config,
        user_action_needed=(
            f"Auto-healing failed after {max_attempts} attempts. "
            "Manual investigation is needed. "
            f"Last error: {current_error.error}"
        ),
    )


def _resolve_timeout(category: str, attempt_number: int, base_timeout: int) -> int:
    """Pick a timeout value, escalating for timeout-class errors."""
    if category == "timeout":
        idx = min(attempt_number - 1, len(_TIMEOUT_ESCALATION) - 1)
        return _TIMEOUT_ESCALATION[idx]
    return base_timeout
