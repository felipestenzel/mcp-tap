"""Tests for opt-in production recommendation feedback loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tap.benchmark.production_feedback import (
    FeedbackEvent,
    ShownRecommendation,
    append_event,
    build_production_report,
    emit_recommendation_decision,
    emit_recommendations_shown,
    load_feedback_events,
    validate_event,
)


def _shown_event(
    *,
    query_id: str,
    release_version: str,
    recs: tuple[tuple[str, int], ...],
) -> FeedbackEvent:
    recommendations = tuple(ShownRecommendation(server_name=name, rank=rank) for name, rank in recs)
    return FeedbackEvent(
        event_type="recommendations_shown",
        event_id=f"evt-{query_id}",
        timestamp="2026-02-24T00:00:00+00:00",
        release_version=release_version,
        query_id=query_id,
        project_fingerprint="abc123abc123abcd",
        client="claude_code",
        recommendations=recommendations,
    )


def _decision_event(
    *,
    event_type: str,
    query_id: str,
    server_name: str,
    release_version: str,
    rank: int | None = None,
    off_intent: bool = False,
) -> FeedbackEvent:
    return FeedbackEvent(
        event_type=event_type,
        event_id=f"{event_type}-{query_id}-{server_name}",
        timestamp="2026-02-24T00:10:00+00:00",
        release_version=release_version,
        query_id=query_id,
        project_fingerprint="abc123abc123abcd",
        client="claude_code",
        server_name=server_name,
        rank=rank,
        off_intent=off_intent,
    )


class TestEventValidation:
    def test_recommendations_shown_requires_ranked_entries(self) -> None:
        event = FeedbackEvent(
            event_type="recommendations_shown",
            event_id="evt-1",
            timestamp="2026-02-24T00:00:00+00:00",
            release_version="0.6.7",
            query_id="q1",
            project_fingerprint="abc123abc123abcd",
            client="claude_code",
            recommendations=(),
        )
        with pytest.raises(ValueError, match="requires recommendations"):
            validate_event(event)

    def test_decision_requires_server_name(self) -> None:
        event = FeedbackEvent(
            event_type="recommendation_accepted",
            event_id="evt-2",
            timestamp="2026-02-24T00:00:00+00:00",
            release_version="0.6.7",
            query_id="q1",
            project_fingerprint="abc123abc123abcd",
            client="claude_code",
            server_name="",
        )
        with pytest.raises(ValueError, match="requires server_name"):
            validate_event(event)


class TestEventEmission:
    def test_append_event_requires_opt_in(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        env = {
            "MCP_TAP_TELEMETRY_OPT_IN": "false",
            "MCP_TAP_TELEMETRY_FILE": str(path),
        }
        persisted = append_event(
            _decision_event(
                event_type="recommendation_accepted",
                query_id="q1",
                server_name="vercel",
                release_version="0.6.7",
            ),
            env=env,
        )
        assert persisted is False
        assert not path.exists()

    def test_emit_shown_and_decision_persist_when_enabled(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        env = {
            "MCP_TAP_TELEMETRY_OPT_IN": "true",
            "MCP_TAP_TELEMETRY_FILE": str(path),
        }
        query_id = emit_recommendations_shown(
            project_path=str(tmp_path / "project-a"),
            client="claude_code",
            recommendations=[{"server_name": "vercel", "source": "registry"}],
            env=env,
        )
        assert query_id

        persisted = emit_recommendation_decision(
            decision_type="recommendation_accepted",
            server_name="vercel",
            query_id=query_id,
            project_path=str(tmp_path / "project-a"),
            client="claude_code",
            rank=1,
            env=env,
        )
        assert persisted is True

        events = load_feedback_events(path)
        assert len(events) == 2
        assert events[0].event_type == "recommendations_shown"
        assert events[0].recommendations[0].rank == 1
        assert events[1].event_type == "recommendation_accepted"
        assert events[1].query_id == query_id


class TestProductionReport:
    def test_report_metrics_and_version_drift_detection(self) -> None:
        events = [
            _shown_event(
                query_id="q1",
                release_version="0.6.6",
                recs=(("sentry", 1), ("datadog", 2)),
            ),
            _decision_event(
                event_type="recommendation_accepted",
                query_id="q1",
                server_name="sentry",
                release_version="0.6.6",
                rank=1,
            ),
            _shown_event(
                query_id="q2",
                release_version="0.6.6",
                recs=(("sentry", 1), ("datadog", 2)),
            ),
            _decision_event(
                event_type="recommendation_rejected",
                query_id="q2",
                server_name="sentry",
                release_version="0.6.6",
                rank=1,
                off_intent=True,
            ),
            _decision_event(
                event_type="recommendation_accepted",
                query_id="q2",
                server_name="datadog",
                release_version="0.6.6",
                rank=2,
            ),
            _shown_event(
                query_id="q3",
                release_version="0.6.7",
                recs=(("newrelic", 1), ("sentry", 2)),
            ),
            _decision_event(
                event_type="recommendation_rejected",
                query_id="q3",
                server_name="newrelic",
                release_version="0.6.7",
                rank=1,
                off_intent=True,
            ),
            _shown_event(
                query_id="q4",
                release_version="0.6.7",
                recs=(("newrelic", 1), ("sentry", 2)),
            ),
            _decision_event(
                event_type="recommendation_accepted",
                query_id="q4",
                server_name="sentry",
                release_version="0.6.7",
                rank=2,
            ),
        ]

        report = build_production_report(events, top_k=2, warn_drop=0.1, block_drop=0.4)

        assert report.query_count == 4
        assert report.acceptance_at_k == 0.75
        assert report.top_1_conversion == 0.25
        assert report.off_intent_rejection_rate == 1.0
        assert len(report.release_trends) == 2
        assert report.release_trends[0].release_version == "0.6.6"
        assert report.release_trends[0].acceptance_at_k == 1.0
        assert report.release_trends[1].release_version == "0.6.7"
        assert report.release_trends[1].acceptance_at_k == 0.5
        assert report.status == "fail"
        assert report.failures
