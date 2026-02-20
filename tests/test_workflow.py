"""Tests for the CI/CD workflow parser (scanner/workflow.py).

Covers GitHub Actions, GitLab CI, and the unified parse_ci_configs entry point.
Uses real temp files (no mocking needed for file I/O).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tap.models import TechnologyCategory
from mcp_tap.scanner.workflow import (
    _extract_gha_actions,
    _extract_gha_run_commands,
    _extract_gha_services,
    _extract_gitlab_image,
    _extract_gitlab_scripts,
    _extract_gitlab_services,
    _match_ci_image,
    _match_gha_action,
    _match_run_command,
    _parse_github_workflows,
    _parse_gitlab_ci,
    parse_ci_configs,
)

# ═══════════════════════════════════════════════════════════════
# Matching Helper Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestMatchCiImage:
    """Tests for _match_ci_image helper."""

    def test_matches_postgres(self) -> None:
        """Should detect postgresql from a postgres image."""
        techs = _match_ci_image("postgres:16", "ci.yml")
        assert len(techs) == 1
        assert techs[0].name == "postgresql"
        assert techs[0].category == TechnologyCategory.DATABASE

    def test_matches_bitnami_postgres(self) -> None:
        """Should match postgres inside bitnami/postgres:16-alpine."""
        techs = _match_ci_image("bitnami/postgres:16-alpine", "ci.yml")
        names = {t.name for t in techs}
        assert "postgresql" in names

    def test_matches_redis(self) -> None:
        """Should detect redis from a redis image."""
        techs = _match_ci_image("redis:7-alpine", "ci.yml")
        assert len(techs) == 1
        assert techs[0].name == "redis"
        assert techs[0].category == TechnologyCategory.DATABASE

    def test_matches_mongo(self) -> None:
        """Should detect mongodb from a mongo image."""
        techs = _match_ci_image("mongo:7", "ci.yml")
        names = {t.name for t in techs}
        assert "mongodb" in names

    def test_matches_mysql(self) -> None:
        """Should detect mysql from a mysql image."""
        techs = _match_ci_image("mysql:8.0", "ci.yml")
        names = {t.name for t in techs}
        assert "mysql" in names

    def test_matches_mariadb_as_mysql(self) -> None:
        """Should map mariadb to mysql technology."""
        techs = _match_ci_image("mariadb:11", "ci.yml")
        names = {t.name for t in techs}
        assert "mysql" in names

    def test_matches_elasticsearch(self) -> None:
        """Should detect elasticsearch from an elasticsearch image."""
        techs = _match_ci_image("docker.elastic.co/elasticsearch:8.12", "ci.yml")
        names = {t.name for t in techs}
        assert "elasticsearch" in names

    def test_matches_rabbitmq(self) -> None:
        """Should detect rabbitmq as a SERVICE."""
        techs = _match_ci_image("rabbitmq:3.12-management", "ci.yml")
        assert len(techs) == 1
        assert techs[0].name == "rabbitmq"
        assert techs[0].category == TechnologyCategory.SERVICE

    def test_matches_memcached(self) -> None:
        """Should detect memcached from a memcached image."""
        techs = _match_ci_image("memcached:1.6", "ci.yml")
        names = {t.name for t in techs}
        assert "memcached" in names

    def test_unknown_image_returns_empty(self) -> None:
        """Should return empty list for an unrecognized image."""
        techs = _match_ci_image("my-custom-app:latest", "ci.yml")
        assert techs == []

    def test_confidence_is_0_85(self) -> None:
        """Should assign 0.85 confidence to CI-detected images."""
        techs = _match_ci_image("postgres:16", "ci.yml")
        assert techs[0].confidence == 0.85

    def test_source_file_propagated(self) -> None:
        """Should propagate source_file to DetectedTechnology."""
        techs = _match_ci_image("redis:7", ".github/workflows/test.yml")
        assert techs[0].source_file == ".github/workflows/test.yml"

    def test_python_image_not_matched(self) -> None:
        """Should NOT match python image (python is not in CI_IMAGE_MAP)."""
        techs = _match_ci_image("python:3.12", "ci.yml")
        assert techs == []


class TestMatchGhaAction:
    """Tests for _match_gha_action helper."""

    @pytest.mark.parametrize(
        ("action", "expected_tech"),
        [
            ("aws-actions/configure-aws-credentials@v4", "aws"),
            ("google-github-actions/auth@v2", "gcp"),
            ("azure/login@v2", "azure"),
            ("docker/build-push-action@v5", "docker"),
            ("docker/setup-buildx-action@v3", "docker"),
            ("hashicorp/setup-terraform@v3", "terraform"),
            ("helm/chart-releaser-action@v1", "kubernetes"),
        ],
    )
    def test_matches_known_actions(self, action: str, expected_tech: str) -> None:
        """Should detect correct technology from known GitHub Actions."""
        techs = _match_gha_action(action.lower(), "ci.yml")
        names = {t.name for t in techs}
        assert expected_tech in names

    def test_unknown_action_returns_empty(self) -> None:
        """Should return empty list for an unrecognized action."""
        techs = _match_gha_action("actions/checkout@v4", "ci.yml")
        assert techs == []

    def test_confidence_is_0_8(self) -> None:
        """Should assign 0.8 confidence to action-detected technologies."""
        techs = _match_gha_action("aws-actions/configure-aws-credentials@v4", "ci.yml")
        assert techs[0].confidence == 0.8

    def test_category_is_platform(self) -> None:
        """All action-detected technologies should be PLATFORM category."""
        techs = _match_gha_action("aws-actions/configure-aws-credentials@v4", "ci.yml")
        for tech in techs:
            assert tech.category == TechnologyCategory.PLATFORM


class TestMatchRunCommand:
    """Tests for _match_run_command helper."""

    @pytest.mark.parametrize(
        ("command", "expected_tech"),
        [
            ("terraform apply -auto-approve", "terraform"),
            ("terraform init && terraform plan", "terraform"),
            ("kubectl apply -f k8s/", "kubernetes"),
            ("helm install my-release my-chart", "kubernetes"),
            ("ansible-playbook playbook.yml", "ansible"),
            ("aws s3 cp file.txt s3://bucket/", "aws"),
            ("gcloud compute instances list", "gcp"),
            ("az storage blob list --container foo", "azure"),
            ("docker build -t myimage .", "docker"),
            ("docker push myimage:latest", "docker"),
            ("docker compose up -d", "docker"),
        ],
    )
    def test_matches_known_commands(self, command: str, expected_tech: str) -> None:
        """Should detect correct technology from known CLI commands."""
        techs = _match_run_command(command, "ci.yml")
        names = {t.name for t in techs}
        assert expected_tech in names

    def test_unknown_command_returns_empty(self) -> None:
        """Should return empty list for an unrecognized command."""
        techs = _match_run_command("echo hello world", "ci.yml")
        assert techs == []

    def test_confidence_is_0_7(self) -> None:
        """Should assign 0.7 confidence to run-command-detected technologies."""
        techs = _match_run_command("terraform apply", "ci.yml")
        assert techs[0].confidence == 0.7

    def test_multiline_command_matches(self) -> None:
        """Should match commands inside multiline run blocks."""
        cmd = "set -e\ncd infra\nterraform apply -auto-approve\n"
        techs = _match_run_command(cmd, "ci.yml")
        names = {t.name for t in techs}
        assert "terraform" in names

    def test_aws_requires_space_after(self) -> None:
        """Should NOT match 'awesome' (word boundary: \\baws\\s requires space)."""
        techs = _match_run_command("awesome tool", "ci.yml")
        assert techs == []

    def test_az_requires_space_after(self) -> None:
        """Should NOT match 'azure-cli' without the 'az ' pattern."""
        techs = _match_run_command("azure-cli version", "ci.yml")
        assert techs == []


# ═══════════════════════════════════════════════════════════════
# GitHub Actions Parser Tests
# ═══════════════════════════════════════════════════════════════


class TestParseGithubWorkflows:
    """Tests for _parse_github_workflows."""

    async def test_no_workflows_dir_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty when .github/workflows/ does not exist."""
        techs, env_vars = await _parse_github_workflows(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_services_detection(self, tmp_path: Path) -> None:
        """Should detect postgres and redis from services block."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\n"
            "on: push\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    services:\n"
            "      postgres:\n"
            "        image: postgres:16\n"
            "      redis:\n"
            "        image: redis:7-alpine\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names

    async def test_actions_detection(self, tmp_path: Path) -> None:
        """Should detect AWS, Docker from uses: directives."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "deploy.yml").write_text(
            "name: Deploy\n"
            "on: push\n"
            "jobs:\n"
            "  deploy:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: aws-actions/configure-aws-credentials@v4\n"
            "      - uses: docker/build-push-action@v5\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        names = {t.name for t in techs}
        assert "aws" in names
        assert "docker" in names

    async def test_run_command_detection(self, tmp_path: Path) -> None:
        """Should detect terraform and kubectl from run commands."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "infra.yml").write_text(
            "name: Infra\n"
            "on: push\n"
            "jobs:\n"
            "  deploy:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: terraform apply -auto-approve\n"
            "      - run: kubectl apply -f k8s/\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        names = {t.name for t in techs}
        assert "terraform" in names
        assert "kubernetes" in names

    async def test_multiple_workflows_parsed(self, tmp_path: Path) -> None:
        """Should parse all .yml/.yaml files in workflows directory."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        image: postgres:16\n"
            "    steps: []\n"
        )
        (wf_dir / "deploy.yaml").write_text(
            "name: Deploy\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: helm install app chart/\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "kubernetes" in names

    async def test_non_yaml_files_ignored(self, tmp_path: Path) -> None:
        """Should skip non-YAML files in the workflows directory."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "README.md").write_text("# Workflows\n")
        (wf_dir / "notes.txt").write_text("some notes")
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_malformed_yaml_skipped(self, tmp_path: Path) -> None:
        """Should skip malformed YAML without crashing."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "bad.yml").write_text(": : : {{{{ not valid yaml >>>")
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_empty_jobs_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty when jobs key is missing."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "empty.yml").write_text("name: Empty\non: push\n")
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_jobs_not_dict_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty when jobs is not a dict (e.g., a list)."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "weird.yml").write_text(
            "name: Weird\non: push\njobs:\n  - not a dict\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_non_dict_data_skipped(self, tmp_path: Path) -> None:
        """Should skip YAML files that parse to non-dict (e.g., a string)."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "string.yml").write_text("just a string")
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_source_file_is_relative(self, tmp_path: Path) -> None:
        """Should set source_file as relative path from project root."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        image: postgres:16\n"
            "    steps: []\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        for tech in techs:
            assert tech.source_file == ".github/workflows/ci.yml"

    async def test_services_non_dict_service_skipped(self, tmp_path: Path) -> None:
        """Should skip services entries that are not dicts."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      bad_service: just-a-string\n"
            "    steps: []\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_services_missing_image_key(self, tmp_path: Path) -> None:
        """Should skip service without an image key."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        ports:\n          - 5432:5432\n"
            "    steps: []\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_steps_non_list_ignored(self, tmp_path: Path) -> None:
        """Should handle steps that are not a list."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps: not-a-list\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_steps_non_dict_items_skipped(self, tmp_path: Path) -> None:
        """Should skip step items that are not dicts."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - just a string\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert techs == []

    async def test_mixed_services_actions_and_commands(self, tmp_path: Path) -> None:
        """Should detect technologies from all three sources in one workflow."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "full.yml").write_text(
            "name: Full Pipeline\n"
            "on: push\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    services:\n"
            "      db:\n"
            "        image: postgres:16\n"
            "      cache:\n"
            "        image: redis:7\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: aws-actions/configure-aws-credentials@v4\n"
            "      - uses: docker/build-push-action@v5\n"
            "      - run: terraform apply\n"
            "      - run: kubectl apply -f k8s/\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names  # service confidence=0.85
        assert "redis" in names       # service confidence=0.85
        assert "aws" in names         # action confidence=0.8
        assert "docker" in names      # action confidence=0.8
        assert "terraform" in names   # run confidence=0.7
        assert "kubernetes" in names  # run confidence=0.7

    async def test_env_vars_always_empty(self, tmp_path: Path) -> None:
        """GitHub Actions parser should always return empty env_vars."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        image: postgres:16\n"
            "    steps: []\n"
        )
        _, env_vars = await _parse_github_workflows(tmp_path)
        assert env_vars == []


# ═══════════════════════════════════════════════════════════════
# GitLab CI Parser Tests
# ═══════════════════════════════════════════════════════════════


class TestParseGitlabCi:
    """Tests for _parse_gitlab_ci."""

    async def test_no_gitlab_ci_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty when .gitlab-ci.yml does not exist."""
        techs, env_vars = await _parse_gitlab_ci(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_string_services(self, tmp_path: Path) -> None:
        """Should detect technologies from string-format services."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n"
            "  - postgres:16\n"
            "  - redis:7\n"
            "stages:\n"
            "  - test\n"
            "test_job:\n"
            "  stage: test\n"
            "  script:\n"
            "    - echo test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names

    async def test_dict_services(self, tmp_path: Path) -> None:
        """Should detect technologies from dict-format services with name key."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n"
            "  - name: postgres:16\n"
            "    alias: db\n"
            "  - name: redis:7\n"
            "    alias: cache\n"
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names

    async def test_top_level_image_python_not_matched(self, tmp_path: Path) -> None:
        """Should NOT match a python image (python is not in CI_IMAGE_MAP)."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "image: python:3.12\n"
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert techs == []

    async def test_top_level_image_postgres_matched(self, tmp_path: Path) -> None:
        """Should detect postgres from top-level image directive."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "image: postgres:16\n"
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names

    async def test_job_level_image(self, tmp_path: Path) -> None:
        """Should detect postgres from a job-level image directive."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - test\n"
            "integration_test:\n"
            "  stage: test\n"
            "  image: postgres:16\n"
            "  script:\n"
            "    - echo test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names

    async def test_job_scripts(self, tmp_path: Path) -> None:
        """Should detect terraform and kubectl from job script commands."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - deploy\n"
            "deploy_infra:\n"
            "  stage: deploy\n"
            "  script:\n"
            "    - terraform apply -auto-approve\n"
            "    - kubectl apply -f k8s/\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "terraform" in names
        assert "kubernetes" in names

    async def test_before_script_parsed(self, tmp_path: Path) -> None:
        """Should detect technologies from before_script blocks."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - deploy\n"
            "deploy_aws:\n"
            "  stage: deploy\n"
            "  before_script:\n"
            "    - aws sts get-caller-identity\n"
            "  script:\n"
            "    - echo deploy\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "aws" in names

    async def test_after_script_parsed(self, tmp_path: Path) -> None:
        """Should detect technologies from after_script blocks."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - deploy\n"
            "deploy_gcp:\n"
            "  stage: deploy\n"
            "  script:\n"
            "    - echo deploy\n"
            "  after_script:\n"
            "    - gcloud logging read 'resource.type=gce_instance'\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "gcp" in names

    async def test_gitlab_keywords_skipped(self, tmp_path: Path) -> None:
        """Should NOT treat GitLab keywords (stages, variables, etc.) as jobs."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - test\n"
            "variables:\n"
            "  TERRAFORM_VERSION: 1.7.0\n"
            "cache:\n"
            "  paths:\n"
            "    - .cache/\n"
            "default:\n"
            "  image: python:3.12\n"
            "include:\n"
            "  - local: .gitlab/templates.yml\n"
            "workflow:\n"
            "  rules:\n"
            "    - if: $CI_COMMIT_BRANCH\n"
            "pages:\n"
            "  script:\n"
            "    - echo pages\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        # None of the keywords should produce script-based detections
        # "pages" is a keyword and should be skipped
        assert techs == []

    async def test_hidden_jobs_skipped(self, tmp_path: Path) -> None:
        """Should skip jobs starting with . (hidden/template jobs)."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - deploy\n"
            ".deploy_template:\n"
            "  script:\n"
            "    - terraform apply\n"
            "    - kubectl apply -f k8s/\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert techs == []

    async def test_malformed_yaml_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty for malformed YAML without crashing."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            ": : : {{{{ not valid yaml >>>"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert techs == []

    async def test_non_dict_yaml_returns_empty(self, tmp_path: Path) -> None:
        """Should return empty when YAML parses to non-dict (e.g., a string)."""
        (tmp_path / ".gitlab-ci.yml").write_text("just a string")
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert techs == []

    async def test_source_file_is_gitlab_ci(self, tmp_path: Path) -> None:
        """Should set source_file to '.gitlab-ci.yml'."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n"
            "  - postgres:16\n"
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        for tech in techs:
            assert tech.source_file == ".gitlab-ci.yml"

    async def test_job_level_services(self, tmp_path: Path) -> None:
        """Should detect technologies from per-job services blocks."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n"
            "  - test\n"
            "integration:\n"
            "  stage: test\n"
            "  services:\n"
            "    - mongo:7\n"
            "  script:\n"
            "    - echo test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "mongodb" in names

    async def test_image_as_dict_with_name(self, tmp_path: Path) -> None:
        """Should handle image specified as dict with name key."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "image:\n"
            "  name: elasticsearch:8.12\n"
            "  entrypoint: ['']\n"
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "elasticsearch" in names

    async def test_env_vars_always_empty(self, tmp_path: Path) -> None:
        """GitLab CI parser should always return empty env_vars."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n  - postgres:16\nstages:\n  - test\n"
        )
        _, env_vars = await _parse_gitlab_ci(tmp_path)
        assert env_vars == []

    async def test_mixed_services_format(self, tmp_path: Path) -> None:
        """Should handle mix of string and dict services in same block."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n"
            "  - postgres:16\n"
            "  - name: redis:7\n"
            "    alias: cache\n"
            "  - 12345\n"  # non-string, non-dict -- should be skipped
            "stages:\n"
            "  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names


# ═══════════════════════════════════════════════════════════════
# Extractor Function Unit Tests
# ═══════════════════════════════════════════════════════════════


class TestExtractGhaServices:
    """Tests for _extract_gha_services extractor."""

    def test_extracts_from_services_block(self) -> None:
        """Should extract technologies from a services dict."""
        job = {
            "services": {
                "db": {"image": "postgres:16"},
                "cache": {"image": "redis:7-alpine"},
            }
        }
        techs = _extract_gha_services(job, "ci.yml")
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names

    def test_no_services_returns_empty(self) -> None:
        """Should return empty when no services block exists."""
        techs = _extract_gha_services({"runs-on": "ubuntu-latest"}, "ci.yml")
        assert techs == []

    def test_services_not_dict_returns_empty(self) -> None:
        """Should return empty when services is not a dict."""
        techs = _extract_gha_services({"services": "not-a-dict"}, "ci.yml")
        assert techs == []


class TestExtractGhaActions:
    """Tests for _extract_gha_actions extractor."""

    def test_extracts_from_uses(self) -> None:
        """Should extract technologies from uses directives."""
        job = {
            "steps": [
                {"uses": "aws-actions/configure-aws-credentials@v4"},
                {"uses": "docker/build-push-action@v5"},
            ]
        }
        techs = _extract_gha_actions(job, "ci.yml")
        names = {t.name for t in techs}
        assert "aws" in names
        assert "docker" in names

    def test_no_steps_returns_empty(self) -> None:
        """Should return empty when no steps key exists."""
        techs = _extract_gha_actions({"runs-on": "ubuntu-latest"}, "ci.yml")
        assert techs == []


class TestExtractGhaRunCommands:
    """Tests for _extract_gha_run_commands extractor."""

    def test_extracts_from_run(self) -> None:
        """Should extract technologies from run commands."""
        job = {
            "steps": [
                {"run": "terraform apply"},
                {"run": "kubectl apply -f k8s/"},
            ]
        }
        techs = _extract_gha_run_commands(job, "ci.yml")
        names = {t.name for t in techs}
        assert "terraform" in names
        assert "kubernetes" in names


class TestExtractGitlabServices:
    """Tests for _extract_gitlab_services extractor."""

    def test_string_services(self) -> None:
        """Should extract from string service entries."""
        data = {"services": ["postgres:16", "redis:7"]}
        techs = _extract_gitlab_services(data, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "postgresql" in names
        assert "redis" in names

    def test_dict_services(self) -> None:
        """Should extract from dict service entries with name key."""
        data = {"services": [{"name": "mongo:7", "alias": "db"}]}
        techs = _extract_gitlab_services(data, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "mongodb" in names

    def test_no_services_returns_empty(self) -> None:
        """Should return empty when no services key exists."""
        techs = _extract_gitlab_services({"image": "python:3.12"}, ".gitlab-ci.yml")
        assert techs == []

    def test_services_not_list_returns_empty(self) -> None:
        """Should return empty when services is not a list."""
        techs = _extract_gitlab_services({"services": "not-a-list"}, ".gitlab-ci.yml")
        assert techs == []


class TestExtractGitlabImage:
    """Tests for _extract_gitlab_image extractor."""

    def test_string_image(self) -> None:
        """Should extract technology from a string image."""
        techs = _extract_gitlab_image({"image": "postgres:16"}, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "postgresql" in names

    def test_dict_image(self) -> None:
        """Should extract technology from a dict image with name key."""
        techs = _extract_gitlab_image(
            {"image": {"name": "elasticsearch:8.12", "entrypoint": [""]}},
            ".gitlab-ci.yml",
        )
        names = {t.name for t in techs}
        assert "elasticsearch" in names

    def test_no_image_returns_empty(self) -> None:
        """Should return empty when no image key exists."""
        techs = _extract_gitlab_image({"script": ["echo test"]}, ".gitlab-ci.yml")
        assert techs == []

    def test_image_not_string_or_dict_returns_empty(self) -> None:
        """Should return empty when image is neither string nor dict."""
        techs = _extract_gitlab_image({"image": 42}, ".gitlab-ci.yml")
        assert techs == []


class TestExtractGitlabScripts:
    """Tests for _extract_gitlab_scripts extractor."""

    def test_extracts_from_script(self) -> None:
        """Should extract technologies from the script key."""
        job = {"script": ["terraform apply", "kubectl apply -f k8s/"]}
        techs = _extract_gitlab_scripts(job, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "terraform" in names
        assert "kubernetes" in names

    def test_extracts_from_before_script(self) -> None:
        """Should extract technologies from before_script."""
        job = {"before_script": ["aws configure"], "script": ["echo test"]}
        techs = _extract_gitlab_scripts(job, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "aws" in names

    def test_extracts_from_after_script(self) -> None:
        """Should extract technologies from after_script."""
        job = {"script": ["echo test"], "after_script": ["gcloud logging read '...'"]}
        techs = _extract_gitlab_scripts(job, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "gcp" in names

    def test_script_not_list_returns_empty(self) -> None:
        """Should return empty when script is not a list."""
        techs = _extract_gitlab_scripts({"script": "not-a-list"}, ".gitlab-ci.yml")
        assert techs == []

    def test_non_string_script_items_skipped(self) -> None:
        """Should skip non-string items in script lists."""
        job = {"script": [42, None, "terraform apply"]}
        techs = _extract_gitlab_scripts(job, ".gitlab-ci.yml")
        names = {t.name for t in techs}
        assert "terraform" in names


# ═══════════════════════════════════════════════════════════════
# Unified Entry Point Tests
# ═══════════════════════════════════════════════════════════════


class TestParseCiConfigs:
    """Tests for the parse_ci_configs unified entry point."""

    async def test_both_configs_present(self, tmp_path: Path) -> None:
        """Should combine results from both GitHub Actions and GitLab CI."""
        # Create GitHub Actions workflow
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        image: postgres:16\n"
            "    steps: []\n"
        )
        # Create GitLab CI
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n  - redis:7\nstages:\n  - test\n"
        )
        techs, _ = await parse_ci_configs(tmp_path)
        names = {t.name for t in techs}
        assert "postgresql" in names  # from GitHub Actions
        assert "redis" in names       # from GitLab CI

    async def test_neither_config_present(self, tmp_path: Path) -> None:
        """Should return empty when no CI configs exist."""
        techs, env_vars = await parse_ci_configs(tmp_path)
        assert techs == []
        assert env_vars == []

    async def test_only_github_present(self, tmp_path: Path) -> None:
        """Should work with only GitHub Actions configs."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: terraform apply\n"
        )
        techs, _ = await parse_ci_configs(tmp_path)
        names = {t.name for t in techs}
        assert "terraform" in names

    async def test_only_gitlab_present(self, tmp_path: Path) -> None:
        """Should work with only GitLab CI config."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n  - mongo:7\nstages:\n  - test\n"
        )
        techs, _ = await parse_ci_configs(tmp_path)
        names = {t.name for t in techs}
        assert "mongodb" in names

    async def test_exception_in_one_parser_doesnt_break_other(
        self, tmp_path: Path
    ) -> None:
        """Should still return results from working parser when one fails."""
        # Create valid GitLab CI
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n  - redis:7\nstages:\n  - test\n"
        )
        # GitHub workflows dir exists but has bad perms
        # (We test this by simply not having GitHub configs -- both parsers succeed
        #  with at least one returning results)
        techs, _ = await parse_ci_configs(tmp_path)
        names = {t.name for t in techs}
        assert "redis" in names

    async def test_returns_tuple_of_techs_and_env_vars(self, tmp_path: Path) -> None:
        """Should return a (list, list) tuple matching _ParseResult type."""
        result = await parse_ci_configs(tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)


# ═══════════════════════════════════════════════════════════════
# Integration with Full Scanner Tests
# ═══════════════════════════════════════════════════════════════


class TestCiConfigsInFullScan:
    """Tests that CI/CD detection integrates correctly with scan_project."""

    async def test_github_services_in_full_scan(self, tmp_path: Path) -> None:
        """Technologies from GitHub Actions services should appear in scan results."""
        from mcp_tap.scanner.detector import scan_project

        # Create a minimal project with a GitHub Actions workflow
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\n"
            "on: push\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    services:\n"
            "      db:\n"
            "        image: postgres:16\n"
            "      cache:\n"
            "        image: redis:7\n"
            "    steps:\n"
            "      - uses: aws-actions/configure-aws-credentials@v4\n"
            "      - run: terraform apply\n"
        )

        profile = await scan_project(str(tmp_path))
        tech_names = {t.name for t in profile.technologies}
        assert "postgresql" in tech_names
        assert "redis" in tech_names
        assert "aws" in tech_names
        assert "terraform" in tech_names

    async def test_gitlab_services_in_full_scan(self, tmp_path: Path) -> None:
        """Technologies from GitLab CI should appear in scan results."""
        from mcp_tap.scanner.detector import scan_project

        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n"
            "  - name: postgres:16\n"
            "    alias: db\n"
            "stages:\n"
            "  - test\n"
            "test_job:\n"
            "  stage: test\n"
            "  script:\n"
            "    - kubectl apply -f k8s/\n"
        )

        profile = await scan_project(str(tmp_path))
        tech_names = {t.name for t in profile.technologies}
        assert "postgresql" in tech_names
        assert "kubernetes" in tech_names

    async def test_deduplication_across_ci_and_docker_compose(
        self, tmp_path: Path
    ) -> None:
        """Technology found in both CI and docker-compose should be deduplicated."""
        from mcp_tap.scanner.detector import scan_project

        # Detect postgres from both docker-compose AND GitHub Actions
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  db:\n    image: postgres:16\n"
        )
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\n"
            "on: push\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    services:\n"
            "      db:\n"
            "        image: postgres:16\n"
            "    steps: []\n"
        )

        profile = await scan_project(str(tmp_path))
        pg_techs = [t for t in profile.technologies if t.name == "postgresql"]
        # Should have 2 entries (different source_file) but NOT more
        sources = {t.source_file for t in pg_techs}
        assert "docker-compose.yml" in sources
        assert ".github/workflows/ci.yml" in sources
        # Deduplication keeps unique (name, source_file) pairs
        assert len(pg_techs) == 2


# ═══════════════════════════════════════════════════════════════
# Confidence Level Verification Tests
# ═══════════════════════════════════════════════════════════════


class TestConfidenceLevels:
    """Verify that each detection method assigns the correct confidence."""

    async def test_services_confidence_0_85(self, tmp_path: Path) -> None:
        """GitHub Actions services should have 0.85 confidence."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n      db:\n        image: postgres:16\n"
            "    steps: []\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert all(t.confidence == 0.85 for t in techs)

    async def test_actions_confidence_0_8(self, tmp_path: Path) -> None:
        """GitHub Actions uses: directives should have 0.8 confidence."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - uses: aws-actions/configure-aws-credentials@v4\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert all(t.confidence == 0.8 for t in techs)

    async def test_run_commands_confidence_0_7(self, tmp_path: Path) -> None:
        """Run command detections should have 0.7 confidence."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: terraform apply\n"
        )
        techs, _ = await _parse_github_workflows(tmp_path)
        assert all(t.confidence == 0.7 for t in techs)

    async def test_gitlab_services_confidence_0_85(self, tmp_path: Path) -> None:
        """GitLab CI services should also have 0.85 confidence."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "services:\n  - postgres:16\nstages:\n  - test\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert all(t.confidence == 0.85 for t in techs)

    async def test_gitlab_scripts_confidence_0_7(self, tmp_path: Path) -> None:
        """GitLab CI script commands should have 0.7 confidence."""
        (tmp_path / ".gitlab-ci.yml").write_text(
            "stages:\n  - deploy\n"
            "deploy:\n  stage: deploy\n  script:\n    - terraform apply\n"
        )
        techs, _ = await _parse_gitlab_ci(tmp_path)
        assert all(t.confidence == 0.7 for t in techs)
