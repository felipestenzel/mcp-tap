"""Tests for the context-aware scoring module (scanner/scoring.py)."""

from __future__ import annotations

from mcp_tap.models import DetectedTechnology, ProjectProfile, TechnologyCategory
from mcp_tap.scanner.scoring import relevance_sort_key, score_result

# --- Helpers ---------------------------------------------------------------


def _profile_with_techs(
    techs: list[tuple[str, TechnologyCategory]],
) -> ProjectProfile:
    """Build a ProjectProfile with the given technologies."""
    return ProjectProfile(
        path="/tmp/project",
        technologies=[
            DetectedTechnology(name=name, category=cat, source_file="pyproject.toml")
            for name, cat in techs
        ],
    )


def _empty_profile() -> ProjectProfile:
    """Build a ProjectProfile with no technologies."""
    return ProjectProfile(path="/tmp/empty")


# === score_result Tests =====================================================


class TestScoreExactTechMatch:
    """Tests for exact technology name match -> high relevance."""

    def test_tech_name_in_result_name(self):
        """Should return 'high' when project tech name appears in result name."""
        profile = _profile_with_techs([("postgresql", TechnologyCategory.DATABASE)])

        relevance, reason = score_result(
            result_name="postgresql-mcp",
            result_description="PostgreSQL MCP server",
            profile=profile,
        )

        assert relevance == "high"
        assert "postgresql" in reason.lower()

    def test_tech_name_in_result_description(self):
        """Should return 'high' when project tech name appears in description."""
        profile = _profile_with_techs([("redis", TechnologyCategory.DATABASE)])

        relevance, reason = score_result(
            result_name="cache-server",
            result_description="A caching server built on Redis",
            profile=profile,
        )

        assert relevance == "high"
        assert "redis" in reason.lower()


class TestScoreCategoryMatch:
    """Tests for category-level keyword match -> medium relevance."""

    def test_database_category_keyword_match(self):
        """Should return 'medium' when project has database tech and result mentions 'database'."""
        profile = _profile_with_techs([("mysql", TechnologyCategory.DATABASE)])

        relevance, reason = score_result(
            result_name="generic-db-tool",
            result_description="A universal database management tool",
            profile=profile,
        )

        # "mysql" is NOT in "generic-db-tool" or "universal database management tool"
        # But "database" keyword IS in the description, and project has DATABASE category
        assert relevance == "medium"
        assert "database" in reason.lower()

    def test_framework_category_keyword_match(self):
        """Should return 'medium' when project has framework and result mentions 'web'."""
        profile = _profile_with_techs([("fastapi", TechnologyCategory.FRAMEWORK)])

        # "fastapi" is not in the result name or description,
        # but "web" is a FRAMEWORK category keyword
        relevance, reason = score_result(
            result_name="http-toolkit",
            result_description="A web development helper",
            profile=profile,
        )

        assert relevance == "medium"
        assert "framework" in reason.lower()

    def test_platform_category_keyword_match(self):
        """Should return 'medium' when project has platform tech and result mentions 'deploy'."""
        profile = _profile_with_techs([("docker", TechnologyCategory.PLATFORM)])

        relevance, _reason = score_result(
            result_name="release-manager",
            result_description="Automate deploy pipelines",
            profile=profile,
        )

        assert relevance == "medium"


class TestScoreNoMatch:
    """Tests for no match -> low relevance."""

    def test_no_tech_overlap(self):
        """Should return 'low' when no technology matches result."""
        profile = _profile_with_techs([("golang", TechnologyCategory.LANGUAGE)])

        relevance, reason = score_result(
            result_name="slack-notifier",
            result_description="Send messages to Slack channels",
            profile=profile,
        )

        assert relevance == "low"
        assert reason == ""


class TestScoreCaseInsensitive:
    """Tests for case-insensitive matching."""

    def test_uppercase_tech_matches_lowercase_result(self):
        """Should match regardless of case differences."""
        profile = _profile_with_techs([("PostgreSQL", TechnologyCategory.DATABASE)])

        relevance, _reason = score_result(
            result_name="postgresql-server",
            result_description="connects to POSTGRESQL databases",
            profile=profile,
        )

        assert relevance == "high"

    def test_mixed_case_in_description(self):
        """Should find tech name even when description has mixed casing."""
        profile = _profile_with_techs([("redis", TechnologyCategory.DATABASE)])

        relevance, _reason = score_result(
            result_name="some-server",
            result_description="Integrates with REDIS clusters",
            profile=profile,
        )

        assert relevance == "high"


class TestScoreMultipleTechs:
    """Tests for profiles with multiple technologies."""

    def test_best_match_wins(self):
        """Should return highest relevance when multiple techs present."""
        profile = _profile_with_techs(
            [
                ("python", TechnologyCategory.LANGUAGE),
                ("postgresql", TechnologyCategory.DATABASE),
            ]
        )

        # "postgresql" exact match should give "high" even though "python" doesn't match
        relevance, reason = score_result(
            result_name="pg-admin-mcp",
            result_description="PostgreSQL admin tool",
            profile=profile,
        )

        assert relevance == "high"
        assert "postgresql" in reason.lower()

    def test_first_exact_match_takes_precedence(self):
        """Should return the first matching tech in iteration order."""
        profile = _profile_with_techs(
            [
                ("python", TechnologyCategory.LANGUAGE),
                ("redis", TechnologyCategory.DATABASE),
            ]
        )

        relevance, reason = score_result(
            result_name="python-redis-bridge",
            result_description="Bridge between Python and Redis",
            profile=profile,
        )

        # "python" appears first in the profile technologies list
        assert relevance == "high"
        assert "python" in reason.lower()

    def test_category_match_when_no_exact_match(self):
        """Should fall through to category match when no exact name match."""
        profile = _profile_with_techs(
            [
                ("mysql", TechnologyCategory.DATABASE),
                ("react", TechnologyCategory.FRAMEWORK),
            ]
        )

        relevance, _reason = score_result(
            result_name="data-explorer",
            result_description="Explore and query your databases",
            profile=profile,
        )

        # "mysql" and "react" are not in result, but "database" keyword IS
        assert relevance == "medium"


class TestScoreEmptyProfile:
    """Tests for scoring with an empty project profile."""

    def test_empty_profile_returns_low(self):
        """Should return 'low' with empty reason for empty profile."""
        profile = _empty_profile()

        relevance, reason = score_result(
            result_name="any-server",
            result_description="Any description at all",
            profile=profile,
        )

        assert relevance == "low"
        assert reason == ""


# === relevance_sort_key Tests ===============================================


class TestRelevanceSortKey:
    """Tests for the relevance_sort_key helper function."""

    def test_high_is_lowest_value(self):
        """Should return 0 for 'high' (highest priority)."""
        assert relevance_sort_key("high") == 0

    def test_medium_is_middle_value(self):
        """Should return 1 for 'medium'."""
        assert relevance_sort_key("medium") == 1

    def test_low_is_highest_value(self):
        """Should return 2 for 'low' (lowest priority)."""
        assert relevance_sort_key("low") == 2

    def test_unknown_relevance_returns_99(self):
        """Should return 99 for unknown relevance levels."""
        assert relevance_sort_key("unknown") == 99

    def test_sort_order_correct(self):
        """Should sort high before medium before low."""
        items = ["low", "high", "medium", "low", "high"]
        sorted_items = sorted(items, key=relevance_sort_key)

        assert sorted_items == ["high", "high", "medium", "low", "low"]
