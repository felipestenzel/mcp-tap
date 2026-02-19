"""Compute maturity scores from collected signals."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from mcp_tap.models import MaturityScore, MaturitySignals


def _days_since(iso_date: str | None) -> int | None:
    """Calculate days since an ISO 8601 date string. Returns None on failure."""
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return (datetime.now(tz=UTC) - dt).days
    except (ValueError, TypeError):
        return None


def _star_score(stars: int | None) -> float:
    """Score based on star count (log scale, max 0.2)."""
    if not stars or stars <= 0:
        return 0.0
    # log10(1)=0, log10(100)=2, log10(1000)=3, log10(5000)≈3.7
    return min(math.log10(stars) / 18.5, 0.2)


def _activity_score(last_commit_date: str | None) -> float:
    """Score based on recency of last commit (max 0.3)."""
    days = _days_since(last_commit_date)
    if days is None:
        return 0.0
    if days <= 30:
        return 0.3
    if days <= 90:
        return 0.2
    if days <= 180:
        return 0.1
    return 0.0


def score_maturity(signals: MaturitySignals) -> MaturityScore:
    """Compute a maturity score from collected signals.

    Scoring components:
    - is_official: +0.3
    - stars (log scale): up to +0.2
    - last_commit recency: up to +0.3
    - is_archived: -0.5
    - open_issues > 50: -0.1

    Tier thresholds:
    - recommended: >= 0.6
    - acceptable: >= 0.4
    - caution: >= 0.2
    - avoid: < 0.2
    """
    score = 0.0
    reasons: list[str] = []
    warning: str | None = None

    # Official bonus
    if signals.is_official:
        score += 0.3
        reasons.append("Official MCP server")

    # Stars
    star_pts = _star_score(signals.stars)
    score += star_pts
    if signals.stars and signals.stars > 0:
        if signals.stars >= 1000:
            reasons.append(f"{signals.stars / 1000:.1f}k stars")
        else:
            reasons.append(f"{signals.stars} stars")

    # Activity
    activity_pts = _activity_score(signals.last_commit_date)
    score += activity_pts
    days = _days_since(signals.last_commit_date)
    if days is not None:
        if days <= 30:
            reasons.append(f"Active development (last commit {days}d ago)")
        elif days <= 90:
            reasons.append(f"Recent activity ({days}d since last commit)")
        elif days <= 180:
            reasons.append(f"Moderate activity ({days}d since last commit)")
        else:
            reasons.append(f"Stale ({days}d since last commit)")

    # Archived penalty
    if signals.is_archived:
        score -= 0.5
        warning = "Repository is archived — no longer maintained"
        reasons.append("ARCHIVED")

    # High open issues penalty
    if signals.open_issues and signals.open_issues > 50:
        score -= 0.1
        reasons.append(f"{signals.open_issues} open issues")

    # License info
    if signals.license:
        reasons.append(f"License: {signals.license}")

    # Clamp and determine tier
    score = max(0.0, min(1.0, score))

    if score >= 0.6:
        tier = "recommended"
    elif score >= 0.4:
        tier = "acceptable"
    elif score >= 0.2:
        tier = "caution"
    else:
        tier = "avoid"

    return MaturityScore(
        score=round(score, 2),
        tier=tier,
        reasons=reasons,
        warning=warning,
    )
