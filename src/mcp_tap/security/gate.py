"""Pre-install security gate for MCP server packages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from mcp_tap.evaluation.github import _parse_github_url, fetch_repo_metadata
from mcp_tap.models import SecurityReport, SecurityRisk, SecuritySignal

logger = logging.getLogger(__name__)

# ─── Thresholds ──────────────────────────────────────────────

_MIN_STARS = 5
_SUSPICIOUS_COMMANDS = frozenset({"bash", "sh", "cmd", "powershell", "curl", "wget"})
_SHELL_METACHARACTERS = ("|", "&&", ">>", "$(", "`")


async def run_security_gate(
    package_identifier: str,
    repository_url: str,
    command: str,
    args: list[str],
    http_client: httpx.AsyncClient | None = None,
) -> SecurityReport:
    """Run all security checks and return an aggregated report."""
    signals: list[SecuritySignal] = []

    # Check command safety
    signals.extend(_check_command(command, args))

    # Check GitHub signals if URL available and http_client provided
    if repository_url and http_client is not None:
        signals.extend(await _check_github(repository_url, http_client))

    # Determine overall risk
    if any(s.risk == SecurityRisk.BLOCK for s in signals):
        overall = SecurityRisk.BLOCK
    elif any(s.risk == SecurityRisk.WARN for s in signals):
        overall = SecurityRisk.WARN
    else:
        overall = SecurityRisk.PASS

    return SecurityReport(overall_risk=overall, signals=signals)


def _check_command(command: str, args: list[str]) -> list[SecuritySignal]:
    """Check server command for suspicious patterns."""
    signals: list[SecuritySignal] = []

    # Extract the base command name (strip path separators)
    cmd_base = command.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()

    if cmd_base in _SUSPICIOUS_COMMANDS:
        signals.append(
            SecuritySignal(
                category="command",
                risk=SecurityRisk.BLOCK,
                message=(
                    f"Server uses suspicious command '{cmd_base}'. "
                    "This could execute arbitrary code."
                ),
            )
        )

    # Check for shell-like patterns in args
    args_str = " ".join(args)
    if any(pattern in args_str for pattern in _SHELL_METACHARACTERS):
        signals.append(
            SecuritySignal(
                category="command",
                risk=SecurityRisk.WARN,
                message="Server arguments contain shell metacharacters. Review carefully.",
            )
        )

    return signals


async def _check_github(
    repository_url: str,
    http_client: httpx.AsyncClient,
) -> list[SecuritySignal]:
    """Check GitHub repository signals."""
    signals: list[SecuritySignal] = []

    parsed = _parse_github_url(repository_url)
    if not parsed:
        return signals

    try:
        metadata = await fetch_repo_metadata(repository_url, http_client)

        if metadata is None:
            signals.append(
                SecuritySignal(
                    category="repository",
                    risk=SecurityRisk.WARN,
                    message=(
                        "Could not fetch repository metadata. Unable to verify package safety."
                    ),
                )
            )
            return signals

        # Check if archived
        if metadata.is_archived:
            signals.append(
                SecuritySignal(
                    category="archived",
                    risk=SecurityRisk.BLOCK,
                    message=(
                        "Repository is archived. This package is no longer maintained "
                        "and should not be installed."
                    ),
                )
            )

        # Check stars
        if metadata.stars is not None and metadata.stars < _MIN_STARS:
            signals.append(
                SecuritySignal(
                    category="stars",
                    risk=SecurityRisk.WARN,
                    message=(
                        f"Repository has only {metadata.stars} stars. "
                        "Low adoption may indicate limited review."
                    ),
                )
            )

        # Check license
        if metadata.license is None:
            signals.append(
                SecuritySignal(
                    category="license",
                    risk=SecurityRisk.WARN,
                    message=(
                        "No license detected. Using unlicensed code may have legal implications."
                    ),
                )
            )

        # Check last commit date (stale > 1 year)
        if metadata.last_commit_date:
            try:
                last_commit = datetime.fromisoformat(
                    metadata.last_commit_date.replace("Z", "+00:00")
                )
                days_since = (datetime.now(UTC) - last_commit).days
                if days_since > 365:
                    signals.append(
                        SecuritySignal(
                            category="stale",
                            risk=SecurityRisk.WARN,
                            message=(
                                f"Last commit was {days_since} days ago. Package may be abandoned."
                            ),
                        )
                    )
            except (ValueError, TypeError):
                pass

    except Exception:
        logger.debug("Security gate GitHub check failed", exc_info=True)

    return signals
