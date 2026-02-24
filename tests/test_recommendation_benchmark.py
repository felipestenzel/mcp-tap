"""Tests for recommendation benchmark quality gate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_tap.benchmark.recommendation import (
    BenchmarkCase,
    build_report,
    default_dataset_path,
    evaluate_case,
    load_cases,
    run_benchmark,
)
from mcp_tap.models import MCPClient, ProjectProfile, RegistryType, ServerRecommendation


def _profile(path: str, servers: list[str]) -> ProjectProfile:
    recommendations = [
        ServerRecommendation(
            server_name=name,
            package_identifier=f"pkg/{name}",
            registry_type=RegistryType.NPM,
            reason="",
            priority="medium",
        )
        for name in servers
    ]
    return ProjectProfile(path=path, recommendations=recommendations)


class TestEvaluateCase:
    def test_perfect_precision_and_acceptance(self) -> None:
        case = BenchmarkCase(
            name="perfect",
            project_path="tests/fixtures/python_fastapi_project",
            client=MCPClient.CLAUDE_CODE,
            expected_servers=("postgres-mcp", "redis-mcp"),
            top_k=2,
        )
        result = evaluate_case(["postgres-mcp", "redis-mcp", "slack-mcp"], case)

        assert result.precision_at_k == 1.0
        assert result.accepted_top_1 is True
        assert result.hit_count == 2

    def test_empty_expected_with_no_recommendations_scores_perfect(self) -> None:
        case = BenchmarkCase(
            name="empty-expected",
            project_path="tests/fixtures/empty_project",
            client=MCPClient.CLAUDE_CODE,
            expected_servers=(),
            top_k=3,
        )
        result = evaluate_case([], case)

        assert result.precision_at_k == 1.0
        assert result.accepted_top_1 is None

    def test_empty_expected_with_unexpected_recommendations_scores_zero(self) -> None:
        case = BenchmarkCase(
            name="unexpected",
            project_path="tests/fixtures/empty_project",
            client=MCPClient.CLAUDE_CODE,
            expected_servers=(),
            top_k=3,
        )
        result = evaluate_case(["filesystem-mcp"], case)

        assert result.precision_at_k == 0.0
        assert result.accepted_top_1 is None


class TestBuildReport:
    def test_report_fails_when_thresholds_are_not_met(self) -> None:
        cases = [
            evaluate_case(
                ["good-mcp"],
                BenchmarkCase(
                    name="ok",
                    project_path="a",
                    client=MCPClient.CLAUDE_CODE,
                    expected_servers=("good-mcp",),
                    top_k=1,
                ),
            ),
            evaluate_case(
                ["bad-mcp"],
                BenchmarkCase(
                    name="bad",
                    project_path="b",
                    client=MCPClient.CLAUDE_CODE,
                    expected_servers=("good-mcp",),
                    top_k=1,
                ),
            ),
        ]

        report = build_report(
            dataset="test",
            case_results=cases,
            min_precision=0.8,
            min_acceptance=0.8,
        )

        assert report.passed is False
        assert report.failures


class TestRunBenchmark:
    @patch("mcp_tap.benchmark.recommendation.scan_project")
    async def test_runs_cases_and_builds_metrics(
        self, mock_scan: AsyncMock, tmp_path: Path
    ) -> None:
        data = {
            "name": "temp_dataset",
            "top_k": 2,
            "cases": [
                {
                    "name": "case-a",
                    "project_path": "proj-a",
                    "client": "claude_code",
                    "expected_servers": ["postgres-mcp", "redis-mcp"],
                },
                {
                    "name": "case-b",
                    "project_path": "proj-b",
                    "client": "claude_code",
                    "expected_servers": [],
                },
            ],
        }
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")

        (tmp_path / "proj-a").mkdir()
        (tmp_path / "proj-b").mkdir()

        async def _scan_side_effect(path: str, client: MCPClient | None = None) -> ProjectProfile:
            if path.endswith("proj-a"):
                return _profile(path, ["postgres-mcp", "redis-mcp"])
            return _profile(path, [])

        mock_scan.side_effect = _scan_side_effect

        report = await run_benchmark(
            dataset_path=dataset_path,
            project_root=tmp_path,
            min_precision=0.9,
            min_acceptance=0.9,
        )

        assert report.passed is True
        assert report.case_count == 2
        assert report.precision_at_k == 1.0
        assert report.acceptance_rate == 1.0


class TestDatasetLoading:
    def test_default_dataset_exists_and_loads(self) -> None:
        path = default_dataset_path()
        assert path.is_file()
        dataset_name, cases = load_cases(path)
        assert dataset_name == "recommendation_dataset_v1"
        assert cases
