"""Tests for the project scanner engine (detector + recommendations)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_tap.errors import ScanError
from mcp_tap.models import (
    DetectedTechnology,
    MCPClient,
    ProjectProfile,
    RegistryType,
    ServerRecommendation,
    TechnologyCategory,
)
from mcp_tap.scanner.detector import (
    _deduplicate_technologies,
    _detect_git_hosting,
    _match_docker_image,
    _match_env_patterns,
    _match_node_deps,
    _match_python_deps,
    _normalize_python_dep,
    _parse_docker_compose,
    _parse_env_files,
    _parse_package_json,
    _parse_pyproject_toml,
    _parse_requirements_txt,
    scan_project,
)
from mcp_tap.scanner.recommendations import TECHNOLOGY_SERVER_MAP, recommend_servers

# ─── Fixture paths ───────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PYTHON_FASTAPI = FIXTURES_DIR / "python_fastapi_project"
NODE_EXPRESS = FIXTURES_DIR / "node_express_project"
MINIMAL = FIXTURES_DIR / "minimal_project"
EMPTY = FIXTURES_DIR / "empty_project"


# ═══════════════════════════════════════════════════════════════
# Parser Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestParsePackageJson:
    """Tests for _parse_package_json parser."""

    async def test_detects_nodejs_and_dependencies(self):
        """Should detect Node.js language and all known deps from fixture."""
        techs, _env_vars = await _parse_package_json(NODE_EXPRESS)

        tech_names = {t.name for t in techs}
        assert "node.js" in tech_names
        assert "express" in tech_names
        assert "postgresql" in tech_names  # from "pg" dep
        assert "redis" in tech_names
        assert "slack" in tech_names  # from "@slack/bolt"

    async def test_all_technologies_reference_source_file(self):
        """Should set source_file to 'package.json' for all detected techs."""
        techs, _ = await _parse_package_json(NODE_EXPRESS)
        for tech in techs:
            assert tech.source_file == "package.json"

    async def test_returns_no_env_vars(self):
        """Should return empty env_vars list (package.json has no env info)."""
        _, env_vars = await _parse_package_json(NODE_EXPRESS)
        assert env_vars == []

    async def test_missing_file_returns_empty(self):
        """Should return empty result when package.json does not exist."""
        techs, env_vars = await _parse_package_json(EMPTY)
        assert techs == []
        assert env_vars == []

    async def test_malformed_json_returns_empty(self, tmp_path: Path):
        """Should gracefully handle invalid JSON without crashing."""
        (tmp_path / "package.json").write_text("{this is not valid json!!!")
        techs, env_vars = await _parse_package_json(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_empty_dependencies_still_detects_nodejs(self, tmp_path: Path):
        """Should detect Node.js even with no dependencies listed."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "empty-app"}))
        techs, _ = await _parse_package_json(tmp_path)
        tech_names = {t.name for t in techs}
        assert "node.js" in tech_names
        assert len(techs) == 1  # only Node.js, no deps

    async def test_reads_dev_and_peer_dependencies(self, tmp_path: Path):
        """Should scan devDependencies and peerDependencies sections too."""
        pkg = {
            "name": "test",
            "devDependencies": {"pg": "^8.0.0"},
            "peerDependencies": {"redis": "^4.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        techs, _ = await _parse_package_json(tmp_path)
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names
        assert "redis" in tech_names


class TestParsePyprojectToml:
    """Tests for _parse_pyproject_toml parser."""

    async def test_detects_python_and_dependencies(self):
        """Should detect Python language and FastAPI, psycopg2, redis from fixture."""
        techs, _env_vars = await _parse_pyproject_toml(PYTHON_FASTAPI)

        tech_names = {t.name for t in techs}
        assert "python" in tech_names
        assert "fastapi" in tech_names
        assert "postgresql" in tech_names  # from psycopg2-binary
        assert "redis" in tech_names

    async def test_detects_optional_dependencies(self):
        """Should pick up slack-sdk from optional [dev] dependencies."""
        techs, _ = await _parse_pyproject_toml(PYTHON_FASTAPI)
        tech_names = {t.name for t in techs}
        assert "slack" in tech_names  # from slack-sdk in optional-dependencies.dev

    async def test_all_technologies_reference_source_file(self):
        """Should set source_file to 'pyproject.toml' for all detected techs."""
        techs, _ = await _parse_pyproject_toml(PYTHON_FASTAPI)
        for tech in techs:
            assert tech.source_file == "pyproject.toml"

    async def test_missing_file_returns_empty(self):
        """Should return empty result when pyproject.toml does not exist."""
        techs, env_vars = await _parse_pyproject_toml(EMPTY)
        assert techs == []
        assert env_vars == []

    async def test_malformed_toml_returns_empty(self, tmp_path: Path):
        """Should gracefully handle invalid TOML without crashing."""
        (tmp_path / "pyproject.toml").write_text("[broken\nthis is = not valid toml !!!")
        techs, env_vars = await _parse_pyproject_toml(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_categories_are_correct(self):
        """Should assign correct categories (LANGUAGE, FRAMEWORK, DATABASE)."""
        techs, _ = await _parse_pyproject_toml(PYTHON_FASTAPI)
        tech_map = {t.name: t for t in techs}

        assert tech_map["python"].category == TechnologyCategory.LANGUAGE
        assert tech_map["fastapi"].category == TechnologyCategory.FRAMEWORK
        assert tech_map["postgresql"].category == TechnologyCategory.DATABASE
        assert tech_map["redis"].category == TechnologyCategory.DATABASE


class TestParseRequirementsTxt:
    """Tests for _parse_requirements_txt parser."""

    async def test_detects_python_and_flask(self):
        """Should detect Python language and Flask framework from fixture."""
        techs, _ = await _parse_requirements_txt(MINIMAL)

        tech_names = {t.name for t in techs}
        assert "python" in tech_names
        assert "flask" in tech_names

    async def test_source_file_is_requirements_txt(self):
        """Should set source_file to 'requirements.txt'."""
        techs, _ = await _parse_requirements_txt(MINIMAL)
        for tech in techs:
            assert tech.source_file == "requirements.txt"

    async def test_missing_file_returns_empty(self):
        """Should return empty result when requirements.txt does not exist."""
        techs, _ = await _parse_requirements_txt(EMPTY)
        assert techs == []

    async def test_handles_version_specifiers(self, tmp_path: Path):
        """Should strip version specifiers from package names."""
        (tmp_path / "requirements.txt").write_text(
            "psycopg2-binary>=2.9.9\nredis~=5.0\ndjango==4.2.10\n"
        )
        techs, _ = await _parse_requirements_txt(tmp_path)
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names
        assert "redis" in tech_names
        assert "django" in tech_names

    async def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        """Should ignore comments and blank lines."""
        (tmp_path / "requirements.txt").write_text(
            "# This is a comment\n\nflask>=3.0\n  # Another comment\n\n"
        )
        techs, _ = await _parse_requirements_txt(tmp_path)
        tech_names = {t.name for t in techs}
        assert "flask" in tech_names
        # Only python + flask should be detected
        assert len(techs) == 2

    async def test_skips_flags(self, tmp_path: Path):
        """Should ignore lines starting with flags like -r, -e, etc."""
        (tmp_path / "requirements.txt").write_text(
            "-r base.txt\n-e git+https://example.com/repo.git\nflask>=3.0\n"
        )
        techs, _ = await _parse_requirements_txt(tmp_path)
        tech_names = {t.name for t in techs}
        assert "flask" in tech_names


class TestParseDockerCompose:
    """Tests for _parse_docker_compose parser."""

    async def test_detects_postgres_and_redis(self):
        """Should detect PostgreSQL and Redis from Python FastAPI fixture."""
        techs, _ = await _parse_docker_compose(PYTHON_FASTAPI)

        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names
        assert "redis" in tech_names

    async def test_detects_postgres_from_node_fixture(self):
        """Should detect PostgreSQL from Node Express fixture."""
        techs, _ = await _parse_docker_compose(NODE_EXPRESS)
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names

    async def test_all_technologies_are_database_or_service(self):
        """Should assign DATABASE or SERVICE category to docker services."""
        techs, _ = await _parse_docker_compose(PYTHON_FASTAPI)
        for tech in techs:
            assert tech.category in (TechnologyCategory.DATABASE, TechnologyCategory.SERVICE)

    async def test_source_file_is_docker_compose(self):
        """Should set source_file to 'docker-compose.yml'."""
        techs, _ = await _parse_docker_compose(PYTHON_FASTAPI)
        for tech in techs:
            assert tech.source_file == "docker-compose.yml"

    async def test_missing_file_returns_empty(self):
        """Should return empty result when no docker-compose file exists."""
        techs, _ = await _parse_docker_compose(EMPTY)
        assert techs == []

    async def test_handles_various_compose_filenames(self, tmp_path: Path):
        """Should detect technologies from compose.yaml (alternative filename)."""
        (tmp_path / "compose.yaml").write_text("services:\n  db:\n    image: mongo:7\n")
        techs, _ = await _parse_docker_compose(tmp_path)
        tech_names = {t.name for t in techs}
        assert "mongodb" in tech_names

    async def test_handles_image_with_registry_prefix(self, tmp_path: Path):
        """Should match known image fragments inside full image URIs."""
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  mq:\n    image: 'bitnami/rabbitmq:3.12'\n"
        )
        techs, _ = await _parse_docker_compose(tmp_path)
        tech_names = {t.name for t in techs}
        assert "rabbitmq" in tech_names


class TestParseEnvFile:
    """Tests for _parse_env_files parser."""

    async def test_extracts_env_var_names_not_values(self):
        """Should extract var names from .env.example, never their values."""
        _techs, env_vars = await _parse_env_files(PYTHON_FASTAPI)

        assert "DATABASE_URL" in env_vars
        assert "REDIS_URL" in env_vars
        assert "SLACK_BOT_TOKEN" in env_vars
        assert "SECRET_KEY" in env_vars
        # Values must NOT appear
        assert not any("postgresql://" in v for v in env_vars)
        assert not any("xoxb-" in v for v in env_vars)

    async def test_detects_technologies_from_env_patterns(self):
        """Should detect PostgreSQL, Redis, Slack from env var naming patterns."""
        techs, _ = await _parse_env_files(PYTHON_FASTAPI)
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names  # from DATABASE_URL
        assert "redis" in tech_names  # from REDIS_URL
        assert "slack" in tech_names  # from SLACK_BOT_TOKEN

    async def test_env_detected_techs_have_lower_confidence(self):
        """Should assign confidence 0.7 to env-pattern-detected technologies."""
        techs, _ = await _parse_env_files(PYTHON_FASTAPI)
        for tech in techs:
            assert tech.confidence == 0.7

    async def test_reads_dotenv_file(self):
        """Should extract env vars from .env file (node fixture)."""
        _techs, env_vars = await _parse_env_files(NODE_EXPRESS)
        assert "DATABASE_URL" in env_vars
        assert "GITHUB_TOKEN" in env_vars

    async def test_detects_github_from_env(self):
        """Should detect GitHub service from GITHUB_TOKEN env var."""
        techs, _ = await _parse_env_files(NODE_EXPRESS)
        tech_names = {t.name for t in techs}
        assert "github" in tech_names

    async def test_missing_env_files_returns_empty(self):
        """Should return empty result when no .env files exist."""
        techs, env_vars = await _parse_env_files(EMPTY)
        assert techs == []
        assert env_vars == []

    async def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        """Should ignore comments and blank lines in .env files."""
        (tmp_path / ".env").write_text(
            "# This is a comment\n"
            "\n"
            "DATABASE_URL=postgres://localhost/db\n"
            "  # Another comment\n"
            "API_KEY=secret\n"
        )
        _, env_vars = await _parse_env_files(tmp_path)
        assert "DATABASE_URL" in env_vars
        assert "API_KEY" in env_vars
        assert len(env_vars) == 2


class TestDetectGitHosting:
    """Tests for _detect_git_hosting."""

    async def test_detects_github_from_github_dir(self):
        """Should detect GitHub when .github/ directory exists."""
        techs, _ = await _detect_git_hosting(PYTHON_FASTAPI)
        tech_names = {t.name for t in techs}
        assert "github" in tech_names

    async def test_github_technology_has_correct_category(self):
        """Should assign SERVICE category to GitHub detection."""
        techs, _ = await _detect_git_hosting(PYTHON_FASTAPI)
        github_tech = next(t for t in techs if t.name == "github")
        assert github_tech.category == TechnologyCategory.SERVICE

    async def test_github_source_file(self):
        """Should set source_file to '.github/' for GitHub detection."""
        techs, _ = await _detect_git_hosting(PYTHON_FASTAPI)
        github_tech = next(t for t in techs if t.name == "github")
        assert github_tech.source_file == ".github/"

    async def test_no_github_dir_returns_empty(self):
        """Should return empty when .github/ does not exist."""
        techs, _ = await _detect_git_hosting(EMPTY)
        assert techs == []

    async def test_detects_gitlab_from_ci_file(self, tmp_path: Path):
        """Should detect GitLab when .gitlab-ci.yml exists."""
        (tmp_path / ".gitlab-ci.yml").write_text("stages:\n  - test\n")
        techs, _ = await _detect_git_hosting(tmp_path)
        tech_names = {t.name for t in techs}
        assert "gitlab" in tech_names


# ═══════════════════════════════════════════════════════════════
# Malformed Input Tests
# ═══════════════════════════════════════════════════════════════


class TestMalformedInputHandling:
    """Tests for graceful handling of malformed/unexpected input."""

    async def test_parse_malformed_json(self, tmp_path: Path):
        """Should return empty result for malformed package.json."""
        (tmp_path / "package.json").write_text("{ not valid }")
        techs, env_vars = await _parse_package_json(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_parse_malformed_toml(self, tmp_path: Path):
        """Should return empty result for malformed pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("= broken [[ toml content")
        techs, env_vars = await _parse_pyproject_toml(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_parse_missing_file(self):
        """Should return empty result when files do not exist (no crash)."""
        techs_json, _ = await _parse_package_json(EMPTY)
        techs_toml, _ = await _parse_pyproject_toml(EMPTY)
        techs_req, _ = await _parse_requirements_txt(EMPTY)
        techs_dc, _ = await _parse_docker_compose(EMPTY)
        techs_env, env_vars = await _parse_env_files(EMPTY)

        assert all(t == [] for t in [techs_json, techs_toml, techs_req, techs_dc, techs_env])
        assert env_vars == []

    async def test_json_with_wrong_type_for_deps(self, tmp_path: Path):
        """Should handle package.json where dependencies is not a dict."""
        pkg = {"name": "test", "dependencies": "not-a-dict"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        techs, _ = await _parse_package_json(tmp_path)
        # Should still detect Node.js but not crash on non-dict deps
        tech_names = {t.name for t in techs}
        assert "node.js" in tech_names

    async def test_toml_with_no_project_section(self, tmp_path: Path):
        """Should handle pyproject.toml with no [project] section."""
        (tmp_path / "pyproject.toml").write_text('[build-system]\nrequires = ["hatchling"]\n')
        techs, _ = await _parse_pyproject_toml(tmp_path)
        # Should still detect Python
        tech_names = {t.name for t in techs}
        assert "python" in tech_names
        assert len(techs) == 1


# ═══════════════════════════════════════════════════════════════
# Helper Function Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestNormalizePythonDep:
    """Tests for _normalize_python_dep helper."""

    def test_strips_version_gte(self):
        assert _normalize_python_dep("fastapi>=0.100") == "fastapi"

    def test_strips_version_tilde(self):
        assert _normalize_python_dep("django~=4.2") == "django"

    def test_strips_version_exact(self):
        assert _normalize_python_dep("flask==3.0.0") == "flask"

    def test_strips_extras(self):
        assert _normalize_python_dep("psycopg2-binary[pool]") == "psycopg2-binary"

    def test_lowercases(self):
        assert _normalize_python_dep("FastAPI>=0.100") == "fastapi"

    def test_bare_name(self):
        assert _normalize_python_dep("requests") == "requests"

    def test_leading_spaces_not_handled(self):
        """Leading whitespace is NOT stripped by _normalize_python_dep itself.

        Callers (e.g., _parse_requirements_txt) strip lines before passing them
        to this function, so this is expected behavior -- not a bug.
        """
        # The regex splits on \s, so leading spaces produce an empty result
        assert _normalize_python_dep("  django ~= 4.2  ") == ""
        # Pre-stripped input works correctly
        assert _normalize_python_dep("django ~= 4.2") == "django"


class TestDeduplicateTechnologies:
    """Tests for _deduplicate_technologies helper."""

    def test_removes_exact_duplicates(self):
        techs = [
            DetectedTechnology("python", TechnologyCategory.LANGUAGE, "a.txt"),
            DetectedTechnology("python", TechnologyCategory.LANGUAGE, "a.txt"),
        ]
        result = _deduplicate_technologies(techs)
        assert len(result) == 1

    def test_keeps_different_sources(self):
        """Same tech from different files should be kept as separate entries."""
        techs = [
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "pyproject.toml"),
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "docker-compose.yml"),
        ]
        result = _deduplicate_technologies(techs)
        assert len(result) == 2

    def test_keeps_highest_confidence(self):
        """When same (name, source_file), should keep highest confidence."""
        techs = [
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "env", confidence=0.7),
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "env", confidence=1.0),
        ]
        result = _deduplicate_technologies(techs)
        assert len(result) == 1
        assert result[0].confidence == 1.0

    def test_empty_input(self):
        assert _deduplicate_technologies([]) == []


class TestMatchHelpers:
    """Tests for _match_node_deps, _match_python_deps, _match_docker_image, _match_env_patterns."""

    def test_match_node_deps_known(self):
        techs = _match_node_deps({"pg", "express", "unknown-lib"}, "package.json")
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names
        assert "express" in tech_names
        # unknown-lib should be silently ignored
        assert len(techs) == 2

    def test_match_python_deps_known(self):
        techs = _match_python_deps({"fastapi", "psycopg2-binary", "unknown"}, "pyproject.toml")
        tech_names = {t.name for t in techs}
        assert "fastapi" in tech_names
        assert "postgresql" in tech_names
        assert len(techs) == 2

    def test_match_docker_image_postgres(self):
        techs = _match_docker_image("postgres:16-alpine", "docker-compose.yml")
        assert len(techs) == 1
        assert techs[0].name == "postgresql"
        assert techs[0].category == TechnologyCategory.DATABASE

    def test_match_docker_image_unknown(self):
        techs = _match_docker_image("my-custom-app:latest", "docker-compose.yml")
        assert techs == []

    def test_match_env_patterns_database_url(self):
        techs = _match_env_patterns(["DATABASE_URL"], ".env")
        assert len(techs) == 1
        assert techs[0].name == "postgresql"
        assert techs[0].confidence == 0.7

    def test_match_env_patterns_deduplicates(self):
        """Multiple POSTGRES-prefixed vars should produce only one technology."""
        techs = _match_env_patterns(["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB"], ".env")
        pg_techs = [t for t in techs if t.name == "postgresql"]
        assert len(pg_techs) == 1

    def test_match_env_patterns_empty(self):
        assert _match_env_patterns([], ".env") == []


# ═══════════════════════════════════════════════════════════════
# Integration Tests — Full Project Scans
# ═══════════════════════════════════════════════════════════════


class TestScanFullPythonProject:
    """Integration tests scanning the python_fastapi fixture."""

    async def test_detects_all_expected_technologies(self):
        """Should detect Python, FastAPI, PostgreSQL, Redis, Slack, GitHub."""
        profile = await scan_project(str(PYTHON_FASTAPI))

        tech_names = {t.name for t in profile.technologies}
        assert "python" in tech_names
        assert "fastapi" in tech_names
        assert "postgresql" in tech_names
        assert "redis" in tech_names
        assert "slack" in tech_names
        assert "github" in tech_names

    async def test_path_is_resolved(self):
        """Should store the resolved absolute path in the profile."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        assert Path(profile.path).is_absolute()

    async def test_env_vars_extracted(self):
        """Should extract env var names from .env.example."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        assert "DATABASE_URL" in profile.env_var_names
        assert "REDIS_URL" in profile.env_var_names
        assert "SLACK_BOT_TOKEN" in profile.env_var_names

    async def test_recommendations_populated(self):
        """Should have non-empty recommendations list."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        assert len(profile.recommendations) > 0

    async def test_postgres_recommendation_present(self):
        """Should recommend postgres-mcp server."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "postgres-mcp" in rec_names

    async def test_redis_recommendation_present(self):
        """Should recommend redis-mcp server."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "redis-mcp" in rec_names

    async def test_github_recommendation_present(self):
        """Should recommend github-mcp server."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "github-mcp" in rec_names

    async def test_filesystem_recommendation_always_present(self):
        """Should always include filesystem-mcp recommendation."""
        profile = await scan_project(str(PYTHON_FASTAPI))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "filesystem-mcp" in rec_names


class TestScanFullNodeProject:
    """Integration tests scanning the node_express fixture."""

    async def test_detects_all_expected_technologies(self):
        """Should detect Node.js, Express, PostgreSQL, Redis, Slack, GitHub."""
        profile = await scan_project(str(NODE_EXPRESS))

        tech_names = {t.name for t in profile.technologies}
        assert "node.js" in tech_names
        assert "express" in tech_names
        assert "postgresql" in tech_names
        assert "redis" in tech_names
        assert "slack" in tech_names

    async def test_env_vars_from_dotenv(self):
        """Should extract env var names from .env file."""
        profile = await scan_project(str(NODE_EXPRESS))
        assert "DATABASE_URL" in profile.env_var_names
        assert "GITHUB_TOKEN" in profile.env_var_names

    async def test_github_detected_from_env(self):
        """Should detect GitHub from GITHUB_TOKEN in .env."""
        profile = await scan_project(str(NODE_EXPRESS))
        tech_names = {t.name for t in profile.technologies}
        assert "github" in tech_names

    async def test_recommendations_include_slack(self):
        """Should recommend slack-mcp server."""
        profile = await scan_project(str(NODE_EXPRESS))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "slack-mcp" in rec_names


class TestScanMinimalProject:
    """Integration tests scanning the minimal fixture."""

    async def test_detects_python_and_flask(self):
        """Should detect Python and Flask from requirements.txt."""
        profile = await scan_project(str(MINIMAL))

        tech_names = {t.name for t in profile.technologies}
        assert "python" in tech_names
        assert "flask" in tech_names

    async def test_detects_makefile(self):
        """Should detect Make build tool from Makefile presence."""
        profile = await scan_project(str(MINIMAL))
        tech_names = {t.name for t in profile.technologies}
        assert "make" in tech_names

    async def test_makefile_has_lower_confidence(self):
        """Should assign 0.8 confidence to Makefile detection."""
        profile = await scan_project(str(MINIMAL))
        make_tech = next(t for t in profile.technologies if t.name == "make")
        assert make_tech.confidence == 0.8

    async def test_no_database_recommendations(self):
        """Should not recommend database servers for a minimal project."""
        profile = await scan_project(str(MINIMAL))
        db_recs = [
            r
            for r in profile.recommendations
            if r.server_name in ("postgres-mcp", "redis-mcp", "mongodb-mcp", "mysql-mcp")
        ]
        assert db_recs == []

    async def test_filesystem_always_recommended(self):
        """Should still recommend filesystem-mcp even for minimal projects."""
        profile = await scan_project(str(MINIMAL))
        rec_names = {r.server_name for r in profile.recommendations}
        assert "filesystem-mcp" in rec_names


class TestScanEmptyProject:
    """Integration tests scanning the empty fixture."""

    async def test_returns_valid_profile(self):
        """Should return a valid ProjectProfile (no crash)."""
        profile = await scan_project(str(EMPTY))
        assert isinstance(profile, ProjectProfile)

    async def test_no_technologies_detected(self):
        """Should detect no technologies in an empty project."""
        profile = await scan_project(str(EMPTY))
        assert profile.technologies == []

    async def test_no_env_vars(self):
        """Should have empty env_var_names."""
        profile = await scan_project(str(EMPTY))
        assert profile.env_var_names == []

    async def test_only_filesystem_recommendation(self):
        """Should only recommend filesystem-mcp for an empty project."""
        profile = await scan_project(str(EMPTY))
        assert len(profile.recommendations) == 1
        assert profile.recommendations[0].server_name == "filesystem-mcp"


class TestScanNonexistentPath:
    """Tests for scanning paths that do not exist."""

    async def test_raises_scan_error(self, tmp_path: Path):
        """Should raise ScanError when path does not exist."""
        fake_path = str(tmp_path / "nonexistent_dir")
        with pytest.raises(ScanError, match="does not exist or is not a directory"):
            await scan_project(fake_path)

    async def test_raises_for_file_path(self, tmp_path: Path):
        """Should raise ScanError when path is a file, not a directory."""
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        with pytest.raises(ScanError, match="does not exist or is not a directory"):
            await scan_project(str(f))


# ═══════════════════════════════════════════════════════════════
# Recommendation Tests
# ═══════════════════════════════════════════════════════════════


class TestRecommendServers:
    """Tests for the recommend_servers function."""

    def _make_profile(
        self,
        tech_names: list[tuple[str, TechnologyCategory]] | None = None,
    ) -> ProjectProfile:
        """Helper to build a ProjectProfile with specified technologies."""
        techs = []
        if tech_names:
            for name, category in tech_names:
                techs.append(
                    DetectedTechnology(
                        name=name,
                        category=category,
                        source_file="test",
                    )
                )
        return ProjectProfile(path="/tmp/test", technologies=techs)

    async def test_recommend_postgres(self):
        """Should recommend postgres-mcp when PostgreSQL is detected."""
        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names

    async def test_recommend_postgres_package(self):
        """Should recommend the correct npm package for postgres."""
        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile)
        pg_rec = next(r for r in recs if r.server_name == "postgres-mcp")
        assert pg_rec.package_identifier == "@modelcontextprotocol/server-postgres"
        assert pg_rec.registry_type == RegistryType.NPM

    async def test_recommend_multiple(self):
        """Should recommend multiple servers for multiple technologies."""
        profile = self._make_profile(
            [
                ("postgresql", TechnologyCategory.DATABASE),
                ("redis", TechnologyCategory.DATABASE),
            ]
        )
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names
        assert "redis-mcp" in rec_names

    async def test_recommend_deduplication(self):
        """Same technology from different sources should produce one recommendation."""
        techs = [
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "pyproject.toml"),
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, "docker-compose.yml"),
            DetectedTechnology("postgresql", TechnologyCategory.DATABASE, ".env"),
        ]
        profile = ProjectProfile(path="/tmp/test", technologies=techs)
        recs = await recommend_servers(profile)
        pg_recs = [r for r in recs if r.server_name == "postgres-mcp"]
        assert len(pg_recs) == 1

    async def test_recommend_empty_profile(self):
        """Should return only filesystem recommendation for empty profile."""
        profile = self._make_profile()
        recs = await recommend_servers(profile)
        # Only filesystem should be recommended
        non_fs = [r for r in recs if r.server_name != "filesystem-mcp"]
        assert non_fs == []
        assert len(recs) == 1

    async def test_filesystem_always_included(self):
        """Should always include filesystem-mcp regardless of technologies."""
        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert "filesystem-mcp" in rec_names

    async def test_recommendations_sorted_by_priority(self):
        """Should sort recommendations: high > medium > low."""
        profile = self._make_profile(
            [
                ("postgresql", TechnologyCategory.DATABASE),
                ("redis", TechnologyCategory.DATABASE),
            ]
        )
        recs = await recommend_servers(profile)
        priorities = [r.priority for r in recs]
        # High should come before medium, medium before low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        priority_values = [priority_order[p] for p in priorities]
        assert priority_values == sorted(priority_values)

    async def test_unknown_technology_no_recommendation(self):
        """Should not crash or produce recommendations for unknown technologies."""
        profile = self._make_profile([("obscure-framework", TechnologyCategory.FRAMEWORK)])
        recs = await recommend_servers(profile)
        # Only filesystem should be present
        non_fs = [r for r in recs if r.server_name != "filesystem-mcp"]
        assert non_fs == []

    async def test_all_mapped_technologies_produce_recommendations(self):
        """Every technology in TECHNOLOGY_SERVER_MAP should produce recommendations."""
        for tech_name, expected_recs in TECHNOLOGY_SERVER_MAP.items():
            if tech_name == "filesystem":
                continue  # filesystem is always added
            profile = self._make_profile([(tech_name, TechnologyCategory.DATABASE)])
            recs = await recommend_servers(profile)
            rec_packages = {r.package_identifier for r in recs}
            for expected in expected_recs:
                assert expected.package_identifier in rec_packages, (
                    f"Technology '{tech_name}' should produce recommendation "
                    f"'{expected.package_identifier}'"
                )

    # ─── Client-aware filtering ───────────────────────────────

    async def test_claude_code_filters_filesystem(self):
        """Claude Code should NOT get filesystem-mcp (has native Read/Write/Edit)."""
        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile, client=MCPClient.CLAUDE_CODE)
        rec_names = {r.server_name for r in recs}
        assert "filesystem-mcp" not in rec_names
        assert "postgres-mcp" in rec_names  # real recommendation kept

    async def test_claude_code_filters_github(self):
        """Claude Code should NOT get github-mcp (has native gh CLI)."""
        profile = self._make_profile([("github", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile, client=MCPClient.CLAUDE_CODE)
        rec_names = {r.server_name for r in recs}
        assert "github-mcp" not in rec_names

    async def test_claude_desktop_keeps_everything(self):
        """Claude Desktop has no native tools — should get all recommendations."""
        profile = self._make_profile(
            [
                ("github", TechnologyCategory.SERVICE),
                ("postgresql", TechnologyCategory.DATABASE),
            ]
        )
        recs = await recommend_servers(profile, client=MCPClient.CLAUDE_DESKTOP)
        rec_names = {r.server_name for r in recs}
        assert "github-mcp" in rec_names
        assert "postgres-mcp" in rec_names
        assert "filesystem-mcp" in rec_names

    async def test_cursor_filters_filesystem_only(self):
        """Cursor should filter filesystem but keep github."""
        profile = self._make_profile([("github", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile, client=MCPClient.CURSOR)
        rec_names = {r.server_name for r in recs}
        assert "github-mcp" in rec_names
        assert "filesystem-mcp" not in rec_names

    async def test_no_client_keeps_everything(self):
        """No client specified — should recommend everything (backward compat)."""
        profile = self._make_profile([("github", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert "github-mcp" in rec_names
        assert "filesystem-mcp" in rec_names

    async def test_claude_code_empty_profile_no_filesystem(self):
        """Claude Code with empty profile should get NO recommendations."""
        profile = self._make_profile()
        recs = await recommend_servers(profile, client=MCPClient.CLAUDE_CODE)
        assert len(recs) == 0  # filesystem filtered, nothing else

    async def test_claude_code_filters_gitlab(self):
        """Claude Code should NOT get gitlab-mcp (has native glab CLI)."""
        profile = self._make_profile([("gitlab", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile, client=MCPClient.CLAUDE_CODE)
        rec_names = {r.server_name for r in recs}
        assert "gitlab-mcp" not in rec_names


class TestIsRedundant:
    """Tests for keyword-based capability matching via _is_redundant."""

    def test_matches_github_in_any_package(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_CODE]
        # Official Docker-based GitHub server
        assert _is_redundant("github-mcp", "ghcr.io/github/github-mcp-server", caps)
        # NPM-based GitHub server
        assert _is_redundant("github-mcp", "@modelcontextprotocol/server-github", caps)

    def test_matches_git_server_variants(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_CODE]
        assert _is_redundant("git-mcp", "mcp-server-git", caps)
        assert _is_redundant("git", "@modelcontextprotocol/server-git", caps)

    def test_matches_filesystem_variants(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_CODE]
        assert _is_redundant("filesystem-mcp", "@modelcontextprotocol/server-filesystem", caps)
        assert _is_redundant("fs-server", "some-filesystem-server", caps)

    def test_matches_fetch_variants(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_CODE]
        assert _is_redundant("fetch", "mcp-server-fetch", caps)

    def test_does_not_match_postgres(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_CODE]
        assert not _is_redundant("postgres-mcp", "@modelcontextprotocol/server-postgres", caps)

    def test_desktop_matches_nothing(self) -> None:
        from mcp_tap.scanner.recommendations import CLIENT_NATIVE_CAPABILITIES, _is_redundant

        caps = CLIENT_NATIVE_CAPABILITIES[MCPClient.CLAUDE_DESKTOP]
        assert not _is_redundant("github-mcp", "ghcr.io/github/github-mcp-server", caps)
        assert not _is_redundant("filesystem-mcp", "server-filesystem", caps)


# ═══════════════════════════════════════════════════════════════
# Domain Model Tests
# ═══════════════════════════════════════════════════════════════


class TestScannerModels:
    """Tests for scanner-related domain models."""

    def test_detected_technology_frozen(self):
        """DetectedTechnology should be immutable."""
        tech = DetectedTechnology("python", TechnologyCategory.LANGUAGE, "pyproject.toml")
        with pytest.raises(AttributeError):
            tech.name = "other"  # type: ignore[misc]

    def test_detected_technology_default_confidence(self):
        """DetectedTechnology should default to confidence 1.0."""
        tech = DetectedTechnology("python", TechnologyCategory.LANGUAGE, "pyproject.toml")
        assert tech.confidence == 1.0

    def test_project_profile_frozen(self):
        """ProjectProfile should be immutable."""
        profile = ProjectProfile(path="/tmp")
        with pytest.raises(AttributeError):
            profile.path = "/other"  # type: ignore[misc]

    def test_project_profile_defaults(self):
        """ProjectProfile should have empty defaults for lists."""
        profile = ProjectProfile(path="/tmp")
        assert profile.technologies == []
        assert profile.env_var_names == []
        assert profile.recommendations == []

    def test_server_recommendation_frozen(self):
        """ServerRecommendation should be immutable."""
        rec = ServerRecommendation(
            server_name="test",
            package_identifier="test-pkg",
            registry_type=RegistryType.NPM,
            reason="testing",
            priority="high",
        )
        with pytest.raises(AttributeError):
            rec.server_name = "other"  # type: ignore[misc]

    def test_technology_category_values(self):
        """TechnologyCategory should have all expected values."""
        assert TechnologyCategory.LANGUAGE == "language"
        assert TechnologyCategory.FRAMEWORK == "framework"
        assert TechnologyCategory.DATABASE == "database"
        assert TechnologyCategory.SERVICE == "service"
        assert TechnologyCategory.PLATFORM == "platform"
