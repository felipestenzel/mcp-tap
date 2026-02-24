"""Opt-in production recommendation feedback loop and reporting."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

from mcp_tap import __version__

_OPT_IN_ENV = "MCP_TAP_TELEMETRY_OPT_IN"
_FILE_ENV = "MCP_TAP_TELEMETRY_FILE"
_TRUE_VALUES = {"1", "true", "yes", "on"}

_EVENT_SHOWN = "recommendations_shown"
_EVENT_ACCEPTED = "recommendation_accepted"
_EVENT_REJECTED = "recommendation_rejected"
_EVENT_IGNORED = "recommendation_ignored"
_DECISION_EVENTS = frozenset({_EVENT_ACCEPTED, _EVENT_REJECTED, _EVENT_IGNORED})
_ALL_EVENTS = frozenset({_EVENT_SHOWN, *_DECISION_EVENTS})


@dataclass(frozen=True, slots=True)
class ShownRecommendation:
    """One recommendation shown to a user for a given query."""

    server_name: str
    rank: int
    source: str = ""
    intent_gate_applied: bool = False


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    """One production feedback event serialized to JSONL."""

    event_type: str
    event_id: str
    timestamp: str
    release_version: str
    query_id: str
    project_fingerprint: str
    client: str
    server_name: str = ""
    rank: int | None = None
    off_intent: bool = False
    recommendations: tuple[ShownRecommendation, ...] = field(default_factory=tuple)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VersionTrend:
    """Aggregated quality metrics for one release version."""

    release_version: str
    query_count: int
    acceptance_at_k: float
    top_1_conversion: float
    off_intent_rejection_rate: float


@dataclass(frozen=True, slots=True)
class ProductionQualityReport:
    """Aggregated production feedback report."""

    event_count: int
    query_count: int
    top_k: int
    acceptance_at_k: float
    top_1_conversion: float
    off_intent_rejection_rate: float
    status: str
    warnings: tuple[str, ...]
    failures: tuple[str, ...]
    release_trends: tuple[VersionTrend, ...]


def telemetry_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when production telemetry is explicitly opt-in enabled."""
    source = env if env is not None else os.environ
    value = source.get(_OPT_IN_ENV, "").strip().lower()
    return value in _TRUE_VALUES


def default_events_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the JSONL path used for production feedback events."""
    source = env if env is not None else os.environ
    custom = source.get(_FILE_ENV)
    if custom:
        return Path(custom).expanduser()
    return Path.home() / ".mcp-tap" / "telemetry" / "recommendation_feedback.jsonl"


def project_fingerprint(project_path: str) -> str:
    """Return a privacy-safe project fingerprint (no raw paths in telemetry)."""
    try:
        normalized = str(Path(project_path).expanduser().resolve())
    except Exception:
        normalized = project_path
    return sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def validate_event(event: FeedbackEvent) -> None:
    """Validate schema and required fields for one feedback event."""
    if event.event_type not in _ALL_EVENTS:
        raise ValueError(f"Unsupported event_type '{event.event_type}'.")
    if not event.event_id:
        raise ValueError("event_id is required.")
    if not event.timestamp:
        raise ValueError("timestamp is required.")
    if not event.release_version:
        raise ValueError("release_version is required.")
    if not event.query_id:
        raise ValueError("query_id is required.")
    if not event.project_fingerprint:
        raise ValueError("project_fingerprint is required.")

    if event.event_type == _EVENT_SHOWN:
        if not event.recommendations:
            raise ValueError("recommendations_shown event requires recommendations.")
        ranks = [rec.rank for rec in event.recommendations]
        if any(rank <= 0 for rank in ranks):
            raise ValueError("Recommendation rank must be > 0.")
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("Recommendation ranks must be contiguous starting at 1.")
    else:
        if not event.server_name:
            raise ValueError(f"{event.event_type} event requires server_name.")
        if event.rank is not None and event.rank <= 0:
            raise ValueError("rank must be > 0 when provided.")


def event_from_dict(data: dict[str, object]) -> FeedbackEvent:
    """Parse and validate one event payload from JSON."""
    raw_recommendations = data.get("recommendations", [])
    recommendations: list[ShownRecommendation] = []
    if isinstance(raw_recommendations, list):
        for item in raw_recommendations:
            if not isinstance(item, dict):
                raise ValueError("recommendations entries must be objects.")
            recommendations.append(
                ShownRecommendation(
                    server_name=str(item.get("server_name", "")).strip(),
                    rank=int(item.get("rank", 0)),
                    source=str(item.get("source", "")).strip(),
                    intent_gate_applied=bool(item.get("intent_gate_applied", False)),
                )
            )

    raw_meta = data.get("metadata", {})
    metadata: dict[str, str] = {}
    if isinstance(raw_meta, dict):
        metadata = {str(k): str(v) for k, v in raw_meta.items()}

    event = FeedbackEvent(
        event_type=str(data.get("event_type", "")).strip(),
        event_id=str(data.get("event_id", "")).strip(),
        timestamp=str(data.get("timestamp", "")).strip(),
        release_version=str(data.get("release_version", "")).strip(),
        query_id=str(data.get("query_id", "")).strip(),
        project_fingerprint=str(data.get("project_fingerprint", "")).strip(),
        client=str(data.get("client", "")).strip(),
        server_name=str(data.get("server_name", "")).strip(),
        rank=int(data["rank"]) if data.get("rank") is not None else None,
        off_intent=bool(data.get("off_intent", False)),
        recommendations=tuple(recommendations),
        metadata=metadata,
    )
    validate_event(event)
    return event


def append_event(event: FeedbackEvent, *, env: Mapping[str, str] | None = None) -> bool:
    """Append one validated event to JSONL storage if telemetry is enabled."""
    validate_event(event)
    if not telemetry_enabled(env):
        return False

    path = default_events_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")
    return True


def emit_recommendations_shown(
    *,
    project_path: str,
    client: str,
    recommendations: Sequence[dict[str, object]],
    query_id: str = "",
    release_version: str = __version__,
    metadata: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Emit recommendations_shown event and return query_id when persisted."""
    if not telemetry_enabled(env):
        return ""

    shown: list[ShownRecommendation] = []
    for rank, rec in enumerate(recommendations, start=1):
        server_name = str(rec.get("server_name") or rec.get("name") or "").strip()
        if not server_name:
            continue
        shown.append(
            ShownRecommendation(
                server_name=server_name,
                rank=rank,
                source=str(rec.get("source", "")).strip(),
                intent_gate_applied=bool(rec.get("intent_gate_applied") is True),
            )
        )

    if not shown:
        return ""

    resolved_query_id = query_id or _new_id()
    event = FeedbackEvent(
        event_type=_EVENT_SHOWN,
        event_id=_new_id(),
        timestamp=_now_iso(),
        release_version=release_version,
        query_id=resolved_query_id,
        project_fingerprint=project_fingerprint(project_path),
        client=client,
        recommendations=tuple(shown),
        metadata=dict(metadata or {}),
    )

    persisted = append_event(event, env=env)
    return resolved_query_id if persisted else ""


def emit_recommendation_decision(
    *,
    decision_type: str,
    server_name: str,
    query_id: str = "",
    project_path: str = "",
    client: str = "",
    rank: int | None = None,
    off_intent: bool = False,
    release_version: str = __version__,
    metadata: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Emit accepted/rejected/ignored recommendation feedback event."""
    if decision_type not in _DECISION_EVENTS:
        raise ValueError(
            "decision_type must be one of: "
            "recommendation_accepted, recommendation_rejected, recommendation_ignored."
        )
    if not telemetry_enabled(env):
        return False

    event = FeedbackEvent(
        event_type=decision_type,
        event_id=_new_id(),
        timestamp=_now_iso(),
        release_version=release_version,
        query_id=query_id or _new_id(),
        project_fingerprint=project_fingerprint(project_path or "unknown"),
        client=client or "unknown",
        server_name=server_name.strip(),
        rank=rank,
        off_intent=off_intent,
        metadata=dict(metadata or {}),
    )
    return append_event(event, env=env)


def load_feedback_events(path: Path, *, strict: bool = True) -> list[FeedbackEvent]:
    """Load feedback events from JSONL with optional strict validation."""
    if not path.is_file():
        return []

    events: list[FeedbackEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("event payload must be a JSON object.")
            events.append(event_from_dict(payload))
        except Exception as exc:
            if strict:
                raise ValueError(f"Invalid event at line {line_number}: {exc}") from exc
    return events


def _metrics_for_queries(
    shown_events: Sequence[FeedbackEvent],
    decisions_by_query: Mapping[str, Sequence[FeedbackEvent]],
    *,
    top_k: int,
) -> tuple[float, float, float]:
    if not shown_events:
        return 0.0, 0.0, 0.0

    acceptance_hits = 0
    top_1_hits = 0
    rejected_total = 0
    off_intent_rejected = 0

    for shown in shown_events:
        rank_by_server = {item.server_name: item.rank for item in shown.recommendations}
        decisions = list(decisions_by_query.get(shown.query_id, ()))

        accepted_servers = {
            decision.server_name
            for decision in decisions
            if decision.event_type == _EVENT_ACCEPTED and decision.server_name
        }
        if any(
            rank_by_server.get(server_name, top_k + 1) <= top_k for server_name in accepted_servers
        ):
            acceptance_hits += 1

        top_1_server = next(
            (item.server_name for item in shown.recommendations if item.rank == 1),
            "",
        )
        if top_1_server and top_1_server in accepted_servers:
            top_1_hits += 1

        rejected = [d for d in decisions if d.event_type == _EVENT_REJECTED]
        rejected_total += len(rejected)
        off_intent_rejected += sum(1 for d in rejected if d.off_intent)

    acceptance = acceptance_hits / len(shown_events)
    top_1 = top_1_hits / len(shown_events)
    off_intent_rate = off_intent_rejected / rejected_total if rejected_total else 0.0
    return round(acceptance, 4), round(top_1, 4), round(off_intent_rate, 4)


def _version_sort_key(version: str) -> tuple[object, ...]:
    parts = re.split(r"[.\-+]", version)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return tuple(key)


def build_production_report(
    events: Sequence[FeedbackEvent],
    *,
    top_k: int = 3,
    warn_drop: float = 0.10,
    block_drop: float = 0.20,
) -> ProductionQualityReport:
    """Build aggregate metrics and version trend indicators from production events."""
    if top_k <= 0:
        raise ValueError("top_k must be > 0.")

    shown_events = [event for event in events if event.event_type == _EVENT_SHOWN]
    decisions_by_query: dict[str, list[FeedbackEvent]] = {}
    for event in events:
        if event.event_type in _DECISION_EVENTS:
            decisions_by_query.setdefault(event.query_id, []).append(event)

    acceptance, top_1, off_intent = _metrics_for_queries(
        shown_events,
        decisions_by_query,
        top_k=top_k,
    )

    by_version: dict[str, list[FeedbackEvent]] = {}
    for shown in shown_events:
        by_version.setdefault(shown.release_version, []).append(shown)

    trends: list[VersionTrend] = []
    for version, version_shown in by_version.items():
        v_acceptance, v_top_1, v_off_intent = _metrics_for_queries(
            version_shown,
            decisions_by_query,
            top_k=top_k,
        )
        trends.append(
            VersionTrend(
                release_version=version,
                query_count=len(version_shown),
                acceptance_at_k=v_acceptance,
                top_1_conversion=v_top_1,
                off_intent_rejection_rate=v_off_intent,
            )
        )

    trends.sort(key=lambda item: _version_sort_key(item.release_version))

    warnings: list[str] = []
    failures: list[str] = []
    for previous, current in pairwise(trends):
        delta = round(current.acceptance_at_k - previous.acceptance_at_k, 4)
        if delta <= -block_drop:
            failures.append(
                f"acceptance@{top_k} dropped {abs(delta):.3f} from "
                f"{previous.release_version} to {current.release_version} "
                f"(block threshold {block_drop:.3f})"
            )
        elif delta <= -warn_drop:
            warnings.append(
                f"acceptance@{top_k} dropped {abs(delta):.3f} from "
                f"{previous.release_version} to {current.release_version} "
                f"(warn threshold {warn_drop:.3f})"
            )

    status = "fail" if failures else ("warn" if warnings else "pass")

    return ProductionQualityReport(
        event_count=len(events),
        query_count=len(shown_events),
        top_k=top_k,
        acceptance_at_k=acceptance,
        top_1_conversion=top_1,
        off_intent_rejection_rate=off_intent,
        status=status,
        warnings=tuple(warnings),
        failures=tuple(failures),
        release_trends=tuple(trends),
    )


def run_feedback_report(
    *,
    events_path: Path | None = None,
    top_k: int = 3,
    warn_drop: float = 0.10,
    block_drop: float = 0.20,
) -> ProductionQualityReport:
    """Load events from disk and build a production quality report."""
    path = events_path or default_events_path()
    events = load_feedback_events(path, strict=True)
    return build_production_report(
        events,
        top_k=top_k,
        warn_drop=warn_drop,
        block_drop=block_drop,
    )


def _format_report_text(report: ProductionQualityReport) -> str:
    lines = [
        "Production Recommendation Feedback Report",
        f"events: {report.event_count}",
        f"queries: {report.query_count}",
        f"acceptance@{report.top_k}: {report.acceptance_at_k:.3f}",
        f"top_1_conversion: {report.top_1_conversion:.3f}",
        f"off_intent_rejection_rate: {report.off_intent_rejection_rate:.3f}",
        f"status: {report.status.upper()}",
        "release trends:",
    ]
    for trend in report.release_trends:
        lines.append(
            f"- {trend.release_version}: queries={trend.query_count}, "
            f"acceptance={trend.acceptance_at_k:.3f}, "
            f"top_1={trend.top_1_conversion:.3f}, "
            f"off_intent_rejection={trend.off_intent_rejection_rate:.3f}"
        )

    if report.warnings:
        lines.append("warnings:")
        lines.extend(f"- {msg}" for msg in report.warnings)
    if report.failures:
        lines.append("failures:")
        lines.extend(f"- {msg}" for msg in report.failures)

    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build production recommendation feedback metrics from opt-in JSONL telemetry."
        )
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=None,
        help="Path to JSONL telemetry events. Defaults to MCP_TAP_TELEMETRY_FILE or ~/.mcp-tap/.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="K value used for acceptance@k metric.",
    )
    parser.add_argument(
        "--warn-drop",
        type=float,
        default=0.10,
        help="Warn when acceptance@k drops by this amount between releases.",
    )
    parser.add_argument(
        "--block-drop",
        type=float,
        default=0.20,
        help="Fail when acceptance@k drops by this amount between releases.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 (report-only mode).",
    )
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> int:
    """CLI runner for production recommendation feedback reports."""
    args = _parse_args(argv)
    report = run_feedback_report(
        events_path=args.events,
        top_k=args.top_k,
        warn_drop=args.warn_drop,
        block_drop=args.block_drop,
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(_format_report_text(report))

    if args.no_fail:
        return 0
    return 1 if report.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
