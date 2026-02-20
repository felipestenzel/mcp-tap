"""Workflow understanding — detect technologies from CI/CD configs.

Parses GitHub Actions workflows and GitLab CI configs to discover
databases, services, and deployment targets that static file scanning
might miss.  Uses PyYAML for reliable YAML parsing; malformed files
are skipped with a warning, never crash.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import yaml

from mcp_tap.models import DetectedTechnology, TechnologyCategory

logger = logging.getLogger(__name__)

# ─── Public API ──────────────────────────────────────────────

_ParseResult = tuple[list[DetectedTechnology], list[str]]


async def parse_ci_configs(root: Path) -> _ParseResult:
    """Parse all CI/CD configs in a project directory.

    Runs GitHub Actions and GitLab CI parsers concurrently.

    Returns:
        Tuple of (detected technologies, env var names).
    """
    results = await asyncio.gather(
        _parse_github_workflows(root),
        _parse_gitlab_ci(root),
        return_exceptions=True,
    )

    technologies: list[DetectedTechnology] = []
    env_vars: list[str] = []

    for result in results:
        if isinstance(result, BaseException):
            logger.warning("CI parser failed: %s", result)
            continue
        techs, envs = result
        technologies.extend(techs)
        env_vars.extend(envs)

    return technologies, env_vars


# ─── GitHub Actions Parser ───────────────────────────────────


async def _parse_github_workflows(root: Path) -> _ParseResult:
    """Parse .github/workflows/*.yml files for technologies."""
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return [], []

    technologies: list[DetectedTechnology] = []

    try:
        workflow_files = list(workflows_dir.iterdir())
    except OSError as exc:
        logger.warning("Cannot list %s: %s", workflows_dir, exc)
        return [], []

    for filepath in workflow_files:
        if filepath.suffix not in (".yml", ".yaml"):
            continue

        text = await _read_file(filepath)
        if text is None:
            continue

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            logger.warning("Malformed workflow YAML at %s", filepath)
            continue

        if not isinstance(data, dict):
            continue

        source = str(filepath.relative_to(root))
        jobs = data.get("jobs")
        if not isinstance(jobs, dict):
            continue

        for job_data in jobs.values():
            if not isinstance(job_data, dict):
                continue
            technologies.extend(_extract_gha_services(job_data, source))
            technologies.extend(_extract_gha_actions(job_data, source))
            technologies.extend(_extract_gha_run_commands(job_data, source))

    return technologies, []


def _extract_gha_services(
    job: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from a GitHub Actions job's services block.

    Example YAML::

        services:
          postgres:
            image: postgres:16
          redis:
            image: redis:7-alpine
    """
    techs: list[DetectedTechnology] = []
    services = job.get("services")
    if not isinstance(services, dict):
        return techs

    for service_data in services.values():
        if not isinstance(service_data, dict):
            continue
        image = service_data.get("image")
        if not isinstance(image, str):
            continue
        techs.extend(_match_ci_image(image.lower(), source))

    return techs


def _extract_gha_actions(
    job: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from GitHub Actions `uses:` directives.

    Detects deployment targets and cloud providers from action names.

    Example YAML::

        steps:
          - uses: aws-actions/configure-aws-credentials@v4
          - uses: google-github-actions/auth@v2
          - uses: azure/login@v2
          - uses: docker/build-push-action@v5
    """
    techs: list[DetectedTechnology] = []
    steps = job.get("steps")
    if not isinstance(steps, list):
        return techs

    for step in steps:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if not isinstance(uses, str):
            continue
        techs.extend(_match_gha_action(uses.lower(), source))

    return techs


def _extract_gha_run_commands(
    job: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from `run:` commands in GitHub Actions steps.

    Detects infrastructure tools like terraform, kubectl, helm, ansible.

    Example YAML::

        steps:
          - run: terraform apply
          - run: kubectl apply -f k8s/
          - run: helm install my-release my-chart
    """
    techs: list[DetectedTechnology] = []
    steps = job.get("steps")
    if not isinstance(steps, list):
        return techs

    for step in steps:
        if not isinstance(step, dict):
            continue
        run_cmd = step.get("run")
        if not isinstance(run_cmd, str):
            continue
        techs.extend(_match_run_command(run_cmd, source))

    return techs


# ─── GitLab CI Parser ────────────────────────────────────────


async def _parse_gitlab_ci(root: Path) -> _ParseResult:
    """Parse .gitlab-ci.yml for technologies.

    Detects databases/services from ``services:`` blocks and images,
    and infrastructure tools from job scripts.
    """
    filepath = root / ".gitlab-ci.yml"
    if not filepath.is_file():
        return [], []

    text = await _read_file(filepath)
    if text is None:
        return [], []

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        logger.warning("Malformed .gitlab-ci.yml at %s", filepath)
        return [], []

    if not isinstance(data, dict):
        return [], []

    source = ".gitlab-ci.yml"
    technologies: list[DetectedTechnology] = []

    # Top-level services
    technologies.extend(_extract_gitlab_services(data, source))

    # Top-level image
    technologies.extend(_extract_gitlab_image(data, source))

    # Per-job analysis
    for key, value in data.items():
        if key.startswith(".") or not isinstance(value, dict):
            continue
        # Skip GitLab CI keywords
        if key in _GITLAB_KEYWORDS:
            continue
        technologies.extend(_extract_gitlab_services(value, source))
        technologies.extend(_extract_gitlab_image(value, source))
        technologies.extend(_extract_gitlab_scripts(value, source))

    return technologies, []


def _extract_gitlab_services(
    data: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from GitLab CI services block.

    Handles both string and dict service formats::

        services:
          - postgres:16
          - name: redis:7
            alias: cache
    """
    techs: list[DetectedTechnology] = []
    services = data.get("services")
    if not isinstance(services, list):
        return techs

    for service in services:
        image: str | None = None
        if isinstance(service, str):
            image = service
        elif isinstance(service, dict):
            name = service.get("name")
            if isinstance(name, str):
                image = name
        if image:
            techs.extend(_match_ci_image(image.lower(), source))

    return techs


def _extract_gitlab_image(
    data: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from GitLab CI image directive."""
    techs: list[DetectedTechnology] = []
    image = data.get("image")
    if isinstance(image, str):
        techs.extend(_match_ci_image(image.lower(), source))
    elif isinstance(image, dict):
        name = image.get("name")
        if isinstance(name, str):
            techs.extend(_match_ci_image(name.lower(), source))
    return techs


def _extract_gitlab_scripts(
    job: dict[str, object],
    source: str,
) -> list[DetectedTechnology]:
    """Extract technologies from GitLab CI job scripts."""
    techs: list[DetectedTechnology] = []
    for key in ("script", "before_script", "after_script"):
        scripts = job.get(key)
        if not isinstance(scripts, list):
            continue
        for cmd in scripts:
            if isinstance(cmd, str):
                techs.extend(_match_run_command(cmd, source))
    return techs


# ─── GitLab CI known keywords (not job names) ────────────────

_GITLAB_KEYWORDS: frozenset[str] = frozenset(
    {
        "image",
        "services",
        "stages",
        "variables",
        "cache",
        "before_script",
        "after_script",
        "default",
        "include",
        "workflow",
        "pages",
    }
)


# ─── Matching Helpers ────────────────────────────────────────

# Docker image fragments → (technology_name, category)
_CI_IMAGE_MAP: dict[str, tuple[str, TechnologyCategory]] = {
    "postgres": ("postgresql", TechnologyCategory.DATABASE),
    "redis": ("redis", TechnologyCategory.DATABASE),
    "mongo": ("mongodb", TechnologyCategory.DATABASE),
    "mysql": ("mysql", TechnologyCategory.DATABASE),
    "mariadb": ("mysql", TechnologyCategory.DATABASE),
    "elasticsearch": ("elasticsearch", TechnologyCategory.DATABASE),
    "rabbitmq": ("rabbitmq", TechnologyCategory.SERVICE),
    "memcached": ("memcached", TechnologyCategory.DATABASE),
}

# Confidence for CI-detected services (lower than direct dependency detection)
_CI_SERVICE_CONFIDENCE = 0.85

# GitHub Actions patterns → (technology_name, category)
_GHA_ACTION_PATTERNS: list[tuple[re.Pattern[str], str, TechnologyCategory]] = [
    (re.compile(r"aws-actions/"), "aws", TechnologyCategory.PLATFORM),
    (re.compile(r"google-github-actions/"), "gcp", TechnologyCategory.PLATFORM),
    (re.compile(r"azure/"), "azure", TechnologyCategory.PLATFORM),
    (re.compile(r"docker/(build|setup)-"), "docker", TechnologyCategory.PLATFORM),
    (re.compile(r"hashicorp/setup-terraform"), "terraform", TechnologyCategory.PLATFORM),
    (re.compile(r"helm/chart-"), "kubernetes", TechnologyCategory.PLATFORM),
]

_GHA_ACTION_CONFIDENCE = 0.8

# CLI tool patterns in run commands → (technology_name, category)
_RUN_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str, TechnologyCategory]] = [
    (re.compile(r"\bterraform\b"), "terraform", TechnologyCategory.PLATFORM),
    (re.compile(r"\bkubectl\b"), "kubernetes", TechnologyCategory.PLATFORM),
    (re.compile(r"\bhelm\b"), "kubernetes", TechnologyCategory.PLATFORM),
    (re.compile(r"\bansible\b"), "ansible", TechnologyCategory.PLATFORM),
    (re.compile(r"\baws\s"), "aws", TechnologyCategory.PLATFORM),
    (re.compile(r"\bgcloud\b"), "gcp", TechnologyCategory.PLATFORM),
    (re.compile(r"\baz\s"), "azure", TechnologyCategory.PLATFORM),
    (re.compile(r"\bdocker\s+(build|push|compose)\b"), "docker", TechnologyCategory.PLATFORM),
]

_RUN_COMMAND_CONFIDENCE = 0.7


def _match_ci_image(
    image: str,
    source: str,
) -> list[DetectedTechnology]:
    """Match a Docker image name from CI services to known technologies."""
    techs: list[DetectedTechnology] = []
    for fragment, (tech_name, category) in _CI_IMAGE_MAP.items():
        if fragment in image:
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source,
                    confidence=_CI_SERVICE_CONFIDENCE,
                )
            )
    return techs


def _match_gha_action(
    action: str,
    source: str,
) -> list[DetectedTechnology]:
    """Match a GitHub Actions `uses:` directive to known technologies."""
    techs: list[DetectedTechnology] = []
    for pattern, tech_name, category in _GHA_ACTION_PATTERNS:
        if pattern.search(action):
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source,
                    confidence=_GHA_ACTION_CONFIDENCE,
                )
            )
    return techs


def _match_run_command(
    command: str,
    source: str,
) -> list[DetectedTechnology]:
    """Match CLI tools in run commands to known technologies."""
    techs: list[DetectedTechnology] = []
    for pattern, tech_name, category in _RUN_COMMAND_PATTERNS:
        if pattern.search(command):
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source,
                    confidence=_RUN_COMMAND_CONFIDENCE,
                )
            )
    return techs


# ─── Utility ─────────────────────────────────────────────────


async def _read_file(filepath: Path) -> str | None:
    """Read a file's text content asynchronously."""
    try:
        return await asyncio.to_thread(filepath.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", filepath, exc)
        return None
