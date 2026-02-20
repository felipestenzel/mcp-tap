"""Project scanner — detect technologies from project files.

Scans a directory for common project files (package.json, pyproject.toml,
docker-compose.yml, .env, etc.) and builds a ProjectProfile describing the
technology stack.  All file I/O is async; all parsing is defensive (malformed
files are skipped with a warning, never crash).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_tap.errors import ScanError
from mcp_tap.models import (
    DetectedTechnology,
    MCPClient,
    ProjectProfile,
    TechnologyCategory,
)
from mcp_tap.scanner.recommendations import recommend_servers
from mcp_tap.scanner.workflow import parse_ci_configs

if TYPE_CHECKING:
    from mcp_tap.registry.base import RegistryClientPort

logger = logging.getLogger(__name__)


# ─── Public API ──────────────────────────────────────────────


async def scan_project(
    path: str,
    *,
    client: MCPClient | None = None,
    registry: RegistryClientPort | None = None,
) -> ProjectProfile:
    """Scan a project directory and return a complete ProjectProfile.

    Args:
        path: Absolute or relative path to the project root.
        client: The MCP client where servers will be installed. When set,
            recommendations redundant with the client's native capabilities
            are filtered out (e.g. filesystem MCP is skipped for Claude Code).
        registry: Optional registry client for dynamic server discovery.
            When provided, technologies without curated mappings trigger
            a registry search. On error/timeout, silently falls back to
            static-only recommendations.

    Returns:
        A ProjectProfile with detected technologies, env var names,
        and server recommendations.

    Raises:
        ScanError: If the path does not exist or is not a directory.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise ScanError(f"Cannot scan '{root}': path does not exist or is not a directory.")

    technologies: list[DetectedTechnology] = []
    env_var_names: list[str] = []

    # Run all parsers concurrently (including CI/CD workflow analysis)
    results = await asyncio.gather(
        _parse_package_json(root),
        _parse_pyproject_toml(root),
        _parse_requirements_txt(root),
        _parse_docker_compose(root),
        _parse_env_files(root),
        _detect_git_hosting(root),
        _detect_language_files(root),
        _detect_platform_files(root),
        parse_ci_configs(root),
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Scanner task failed: %s", result)
            continue
        techs, env_vars = result
        technologies.extend(techs)
        env_var_names.extend(env_vars)

    # Deduplicate technologies by (name, source_file)
    technologies = _deduplicate_technologies(technologies)
    env_var_names = sorted(set(env_var_names))

    # Build partial profile, then derive recommendations
    profile = ProjectProfile(
        path=str(root),
        technologies=technologies,
        env_var_names=env_var_names,
    )
    recommendations = await recommend_servers(profile, client=client, registry=registry)

    return replace(profile, recommendations=recommendations)


# ─── Type alias for parser return values ─────────────────────

_ParseResult = tuple[list[DetectedTechnology], list[str]]


# ─── Individual Parsers ──────────────────────────────────────


async def _parse_package_json(root: Path) -> _ParseResult:
    """Parse package.json for Node.js dependencies."""
    filepath = root / "package.json"
    if not filepath.is_file():
        return [], []

    text = await _read_file(filepath)
    if text is None:
        return [], []

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Malformed package.json at %s", filepath)
        return [], []

    techs: list[DetectedTechnology] = []
    source = str(filepath.relative_to(root))

    # Node.js itself
    techs.append(
        DetectedTechnology(
            name="node.js",
            category=TechnologyCategory.LANGUAGE,
            source_file=source,
        )
    )

    # Merge all dependency sections
    all_deps: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(section)
        if isinstance(deps, dict):
            all_deps.update(deps)

    techs.extend(_match_node_deps(all_deps, source))
    return techs, []


async def _parse_pyproject_toml(root: Path) -> _ParseResult:
    """Parse pyproject.toml for Python dependencies."""
    filepath = root / "pyproject.toml"
    if not filepath.is_file():
        return [], []

    text = await _read_file(filepath)
    if text is None:
        return [], []

    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        logger.warning("Malformed pyproject.toml at %s", filepath)
        return [], []

    techs: list[DetectedTechnology] = []
    source = str(filepath.relative_to(root))

    # Python itself
    techs.append(
        DetectedTechnology(
            name="python",
            category=TechnologyCategory.LANGUAGE,
            source_file=source,
        )
    )

    # Collect dependency names from [project.dependencies]
    dep_names: set[str] = set()
    project = data.get("project", {})
    if isinstance(project, dict):
        raw_deps = project.get("dependencies", [])
        if isinstance(raw_deps, list):
            for dep in raw_deps:
                if isinstance(dep, str):
                    dep_names.add(_normalize_python_dep(dep))

        # Optional dependencies
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group_deps in optional.values():
                if isinstance(group_deps, list):
                    for dep in group_deps:
                        if isinstance(dep, str):
                            dep_names.add(_normalize_python_dep(dep))

    techs.extend(_match_python_deps(dep_names, source))
    return techs, []


async def _parse_requirements_txt(root: Path) -> _ParseResult:
    """Parse requirements.txt for Python dependencies."""
    techs: list[DetectedTechnology] = []

    for filename in ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt"):
        filepath = root / filename
        if not filepath.is_file():
            continue

        text = await _read_file(filepath)
        if text is None:
            continue

        source = str(filepath.relative_to(root))

        # Add Python language detection (only once across all req files)
        if not any(t.name == "python" for t in techs):
            techs.append(
                DetectedTechnology(
                    name="python",
                    category=TechnologyCategory.LANGUAGE,
                    source_file=source,
                )
            )

        dep_names: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            # Skip comments, blank lines, flags (-r, -e, etc.)
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            dep_names.add(_normalize_python_dep(line))

        techs.extend(_match_python_deps(dep_names, source))

    return techs, []


async def _parse_docker_compose(root: Path) -> _ParseResult:
    """Parse docker-compose.yml for service images using regex.

    Uses simple regex/string parsing to avoid a PyYAML dependency.
    Looks for ``image:`` keys and maps known image names to technologies.
    """
    techs: list[DetectedTechnology] = []

    for filename in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        filepath = root / filename
        if not filepath.is_file():
            continue

        text = await _read_file(filepath)
        if text is None:
            continue

        source = str(filepath.relative_to(root))

        # Match lines like "  image: postgres:16" or "  image: redis/redis-stack"
        image_pattern = re.compile(r"^\s*image:\s*['\"]?([^'\"#\s]+)", re.MULTILINE)
        for match in image_pattern.finditer(text):
            image_name = match.group(1).lower()
            techs.extend(_match_docker_image(image_name, source))

    return techs, []


async def _parse_env_files(root: Path) -> _ParseResult:
    """Extract env var names from .env / .env.example / .env.local files.

    Only reads KEY names, never values.  Detects patterns like
    ``*_TOKEN``, ``*_KEY``, ``DATABASE_URL``, ``SLACK_*``, ``GITHUB_*``.
    """
    all_env_vars: list[str] = []
    techs: list[DetectedTechnology] = []

    for filename in (".env", ".env.example", ".env.local", ".env.sample"):
        filepath = root / filename
        if not filepath.is_file():
            continue

        text = await _read_file(filepath)
        if text is None:
            continue

        source = str(filepath.relative_to(root))

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Split on first '=' to get the key
            if "=" not in line:
                continue
            key = line.split("=", maxsplit=1)[0].strip()
            if not key or key.startswith("#"):
                continue
            all_env_vars.append(key)

        # Detect technologies from env var patterns
        techs.extend(_match_env_patterns(all_env_vars, source))

    return techs, all_env_vars


async def _detect_git_hosting(root: Path) -> _ParseResult:
    """Detect Git hosting provider from CI/CD config files."""
    techs: list[DetectedTechnology] = []

    if (root / ".github").is_dir():
        techs.append(
            DetectedTechnology(
                name="github",
                category=TechnologyCategory.SERVICE,
                source_file=".github/",
            )
        )

    if (root / ".gitlab-ci.yml").is_file():
        techs.append(
            DetectedTechnology(
                name="gitlab",
                category=TechnologyCategory.SERVICE,
                source_file=".gitlab-ci.yml",
            )
        )

    return techs, []


async def _detect_language_files(root: Path) -> _ParseResult:
    """Detect languages from presence of well-known project files."""
    techs: list[DetectedTechnology] = []

    language_markers: dict[str, str] = {
        "Gemfile": "ruby",
        "go.mod": "go",
        "Cargo.toml": "rust",
    }

    for filename, language in language_markers.items():
        if (root / filename).is_file():
            techs.append(
                DetectedTechnology(
                    name=language,
                    category=TechnologyCategory.LANGUAGE,
                    source_file=filename,
                )
            )

    if (root / "Makefile").is_file():
        techs.append(
            DetectedTechnology(
                name="make",
                category=TechnologyCategory.PLATFORM,
                source_file="Makefile",
                confidence=0.8,
            )
        )

    return techs, []


async def _detect_platform_files(root: Path) -> _ParseResult:
    """Detect deployment platforms from config files."""
    techs: list[DetectedTechnology] = []

    if (root / "vercel.json").is_file():
        techs.append(
            DetectedTechnology(
                name="vercel",
                category=TechnologyCategory.PLATFORM,
                source_file="vercel.json",
            )
        )

    if (root / "netlify.toml").is_file():
        techs.append(
            DetectedTechnology(
                name="netlify",
                category=TechnologyCategory.PLATFORM,
                source_file="netlify.toml",
            )
        )

    if (root / "Dockerfile").is_file():
        techs.append(
            DetectedTechnology(
                name="docker",
                category=TechnologyCategory.PLATFORM,
                source_file="Dockerfile",
            )
        )

    # IaC
    if any((root / f).is_file() for f in ("main.tf", "terraform.tf")):
        techs.append(
            DetectedTechnology(
                name="terraform",
                category=TechnologyCategory.PLATFORM,
                source_file="*.tf",
            )
        )
    if (root / "Pulumi.yaml").is_file():
        techs.append(
            DetectedTechnology(
                name="pulumi",
                category=TechnologyCategory.PLATFORM,
                source_file="Pulumi.yaml",
            )
        )

    # Services
    if any(
        (root / f).is_file()
        for f in ("sentry.properties", "sentry.client.config.ts", "sentry.client.config.js")
    ):
        techs.append(
            DetectedTechnology(
                name="sentry",
                category=TechnologyCategory.SERVICE,
                source_file="sentry config",
            )
        )
    if any((root / f).is_file() for f in ("firebase.json", ".firebaserc")):
        techs.append(
            DetectedTechnology(
                name="firebase",
                category=TechnologyCategory.SERVICE,
                source_file="firebase config",
            )
        )
    if (root / "supabase" / "config.toml").is_file():
        techs.append(
            DetectedTechnology(
                name="supabase",
                category=TechnologyCategory.SERVICE,
                source_file="supabase/config.toml",
            )
        )
    if (root / "wrangler.toml").is_file():
        techs.append(
            DetectedTechnology(
                name="cloudflare",
                category=TechnologyCategory.PLATFORM,
                source_file="wrangler.toml",
            )
        )

    # Monorepo
    if (root / "turbo.json").is_file():
        techs.append(
            DetectedTechnology(
                name="turborepo",
                category=TechnologyCategory.PLATFORM,
                source_file="turbo.json",
            )
        )
    if (root / "nx.json").is_file():
        techs.append(
            DetectedTechnology(
                name="nx",
                category=TechnologyCategory.PLATFORM,
                source_file="nx.json",
            )
        )
    if (root / "lerna.json").is_file():
        techs.append(
            DetectedTechnology(
                name="lerna",
                category=TechnologyCategory.PLATFORM,
                source_file="lerna.json",
            )
        )

    # Testing
    if any((root / f).is_file() for f in ("playwright.config.ts", "playwright.config.js")):
        techs.append(
            DetectedTechnology(
                name="playwright",
                category=TechnologyCategory.SERVICE,
                source_file="playwright config",
            )
        )
    if any(
        (root / f).is_file() for f in ("cypress.config.ts", "cypress.config.js", "cypress.json")
    ):
        techs.append(
            DetectedTechnology(
                name="cypress",
                category=TechnologyCategory.SERVICE,
                source_file="cypress config",
            )
        )

    # Deployment
    if (root / "fly.toml").is_file():
        techs.append(
            DetectedTechnology(
                name="fly.io",
                category=TechnologyCategory.PLATFORM,
                source_file="fly.toml",
            )
        )
    if (root / "render.yaml").is_file():
        techs.append(
            DetectedTechnology(
                name="render",
                category=TechnologyCategory.PLATFORM,
                source_file="render.yaml",
            )
        )

    return techs, []


# ─── Dependency Matching Helpers ─────────────────────────────

# Node.js dependency name → (technology_name, category)
_NODE_DEP_MAP: dict[str, tuple[str, TechnologyCategory]] = {
    # Frameworks
    "next": ("next.js", TechnologyCategory.FRAMEWORK),
    "express": ("express", TechnologyCategory.FRAMEWORK),
    "react": ("react", TechnologyCategory.FRAMEWORK),
    "vue": ("vue", TechnologyCategory.FRAMEWORK),
    "angular": ("angular", TechnologyCategory.FRAMEWORK),
    "@angular/core": ("angular", TechnologyCategory.FRAMEWORK),
    "svelte": ("svelte", TechnologyCategory.FRAMEWORK),
    "nuxt": ("nuxt", TechnologyCategory.FRAMEWORK),
    "fastify": ("fastify", TechnologyCategory.FRAMEWORK),
    "nestjs": ("nestjs", TechnologyCategory.FRAMEWORK),
    "@nestjs/core": ("nestjs", TechnologyCategory.FRAMEWORK),
    "hono": ("hono", TechnologyCategory.FRAMEWORK),
    # Databases
    "pg": ("postgresql", TechnologyCategory.DATABASE),
    "postgres": ("postgresql", TechnologyCategory.DATABASE),
    "mysql2": ("mysql", TechnologyCategory.DATABASE),
    "mysql": ("mysql", TechnologyCategory.DATABASE),
    "redis": ("redis", TechnologyCategory.DATABASE),
    "ioredis": ("redis", TechnologyCategory.DATABASE),
    "mongodb": ("mongodb", TechnologyCategory.DATABASE),
    "mongoose": ("mongodb", TechnologyCategory.DATABASE),
    "better-sqlite3": ("sqlite", TechnologyCategory.DATABASE),
    "sqlite3": ("sqlite", TechnologyCategory.DATABASE),
    "@prisma/client": ("postgresql", TechnologyCategory.DATABASE),
    "typeorm": ("postgresql", TechnologyCategory.DATABASE),
    # Services
    "slack-bolt": ("slack", TechnologyCategory.SERVICE),
    "@slack/bolt": ("slack", TechnologyCategory.SERVICE),
    "@slack/web-api": ("slack", TechnologyCategory.SERVICE),
    "@octokit/core": ("github", TechnologyCategory.SERVICE),
    "@octokit/rest": ("github", TechnologyCategory.SERVICE),
    "octokit": ("github", TechnologyCategory.SERVICE),
    # AI/ML
    "openai": ("openai", TechnologyCategory.SERVICE),
    "@anthropic-ai/sdk": ("anthropic", TechnologyCategory.SERVICE),
    # Services
    "stripe": ("stripe", TechnologyCategory.SERVICE),
    "sentry": ("sentry", TechnologyCategory.SERVICE),
    # BaaS
    "firebase": ("firebase", TechnologyCategory.SERVICE),
    "supabase": ("supabase", TechnologyCategory.SERVICE),
}

# Node.js @org/ prefix patterns → (technology_name, category)
# Checked after exact match; enables detection via any scoped package
_NODE_PREFIX_MAP: list[tuple[str, str, TechnologyCategory]] = [
    ("@sentry/", "sentry", TechnologyCategory.SERVICE),
    ("@stripe/", "stripe", TechnologyCategory.SERVICE),
    ("@datadog/", "datadog", TechnologyCategory.SERVICE),
    ("@supabase/", "supabase", TechnologyCategory.SERVICE),
    ("@firebase/", "firebase", TechnologyCategory.SERVICE),
    ("@auth0/", "auth0", TechnologyCategory.SERVICE),
    ("@clerk/", "clerk", TechnologyCategory.SERVICE),
    ("@notionhq/", "notion", TechnologyCategory.SERVICE),
    ("@linear/", "linear", TechnologyCategory.SERVICE),
    ("@aws-sdk/", "aws", TechnologyCategory.PLATFORM),
    ("@google-cloud/", "gcp", TechnologyCategory.PLATFORM),
    ("@azure/", "azure", TechnologyCategory.PLATFORM),
    ("@cloudflare/", "cloudflare", TechnologyCategory.PLATFORM),
    ("@vercel/", "vercel", TechnologyCategory.PLATFORM),
    ("@langchain/", "langchain", TechnologyCategory.SERVICE),
    ("@huggingface/", "huggingface", TechnologyCategory.SERVICE),
    ("@contentful/", "contentful", TechnologyCategory.SERVICE),
    ("@sanity/", "sanity", TechnologyCategory.SERVICE),
    ("@shopify/", "shopify", TechnologyCategory.SERVICE),
    ("@playwright/", "playwright", TechnologyCategory.SERVICE),
    ("@pulumi/", "pulumi", TechnologyCategory.PLATFORM),
    ("@prisma/", "prisma", TechnologyCategory.SERVICE),
    ("@twilio/", "twilio", TechnologyCategory.SERVICE),
    ("@sendgrid/", "sendgrid", TechnologyCategory.SERVICE),
]

# Python dependency name → (technology_name, category)
_PYTHON_DEP_MAP: dict[str, tuple[str, TechnologyCategory]] = {
    # Frameworks
    "fastapi": ("fastapi", TechnologyCategory.FRAMEWORK),
    "django": ("django", TechnologyCategory.FRAMEWORK),
    "flask": ("flask", TechnologyCategory.FRAMEWORK),
    "starlette": ("starlette", TechnologyCategory.FRAMEWORK),
    "tornado": ("tornado", TechnologyCategory.FRAMEWORK),
    "sanic": ("sanic", TechnologyCategory.FRAMEWORK),
    "litestar": ("litestar", TechnologyCategory.FRAMEWORK),
    # Databases
    "psycopg2": ("postgresql", TechnologyCategory.DATABASE),
    "psycopg2-binary": ("postgresql", TechnologyCategory.DATABASE),
    "psycopg": ("postgresql", TechnologyCategory.DATABASE),
    "asyncpg": ("postgresql", TechnologyCategory.DATABASE),
    "sqlalchemy": ("postgresql", TechnologyCategory.DATABASE),
    "redis": ("redis", TechnologyCategory.DATABASE),
    "pymongo": ("mongodb", TechnologyCategory.DATABASE),
    "motor": ("mongodb", TechnologyCategory.DATABASE),
    "mysqlclient": ("mysql", TechnologyCategory.DATABASE),
    "pymysql": ("mysql", TechnologyCategory.DATABASE),
    "sqlite3": ("sqlite", TechnologyCategory.DATABASE),
    "aiosqlite": ("sqlite", TechnologyCategory.DATABASE),
    # Services
    "slack-sdk": ("slack", TechnologyCategory.SERVICE),
    "slack-bolt": ("slack", TechnologyCategory.SERVICE),
    "pygithub": ("github", TechnologyCategory.SERVICE),
    "githubkit": ("github", TechnologyCategory.SERVICE),
    # AI/ML
    "openai": ("openai", TechnologyCategory.SERVICE),
    "anthropic": ("anthropic", TechnologyCategory.SERVICE),
    "langchain": ("langchain", TechnologyCategory.SERVICE),
    "langchain-core": ("langchain", TechnologyCategory.SERVICE),
    "transformers": ("huggingface", TechnologyCategory.SERVICE),
    "sentence-transformers": ("huggingface", TechnologyCategory.SERVICE),
    # Cloud
    "boto3": ("aws", TechnologyCategory.PLATFORM),
    "botocore": ("aws", TechnologyCategory.PLATFORM),
    "google-cloud-storage": ("gcp", TechnologyCategory.PLATFORM),
    "google-cloud-bigquery": ("gcp", TechnologyCategory.PLATFORM),
    "azure-storage-blob": ("azure", TechnologyCategory.PLATFORM),
    "azure-identity": ("azure", TechnologyCategory.PLATFORM),
    # Services (continued)
    "sentry-sdk": ("sentry", TechnologyCategory.SERVICE),
    "stripe": ("stripe", TechnologyCategory.SERVICE),
    "supabase": ("supabase", TechnologyCategory.SERVICE),
    "firebase-admin": ("firebase", TechnologyCategory.SERVICE),
    "twilio": ("twilio", TechnologyCategory.SERVICE),
    "sendgrid": ("sendgrid", TechnologyCategory.SERVICE),
    # Databases (continued)
    "elasticsearch": ("elasticsearch", TechnologyCategory.DATABASE),
    # Task queues
    "celery": ("celery", TechnologyCategory.SERVICE),
    "dramatiq": ("dramatiq", TechnologyCategory.SERVICE),
}

# Docker image name fragments → (technology_name, category)
_DOCKER_IMAGE_MAP: dict[str, tuple[str, TechnologyCategory]] = {
    "postgres": ("postgresql", TechnologyCategory.DATABASE),
    "redis": ("redis", TechnologyCategory.DATABASE),
    "elasticsearch": ("elasticsearch", TechnologyCategory.DATABASE),
    "mongo": ("mongodb", TechnologyCategory.DATABASE),
    "rabbitmq": ("rabbitmq", TechnologyCategory.SERVICE),
    "mysql": ("mysql", TechnologyCategory.DATABASE),
    "mariadb": ("mysql", TechnologyCategory.DATABASE),
    "memcached": ("memcached", TechnologyCategory.DATABASE),
    "nginx": ("nginx", TechnologyCategory.SERVICE),
    "kafka": ("kafka", TechnologyCategory.SERVICE),
    "grafana": ("grafana", TechnologyCategory.SERVICE),
    "prometheus": ("prometheus", TechnologyCategory.SERVICE),
    "minio": ("minio", TechnologyCategory.SERVICE),
    "clickhouse": ("clickhouse", TechnologyCategory.DATABASE),
}

# Env var patterns → technology name
_ENV_PATTERNS: list[tuple[re.Pattern[str], str, TechnologyCategory]] = [
    (re.compile(r"^DATABASE_URL$", re.IGNORECASE), "postgresql", TechnologyCategory.DATABASE),
    (re.compile(r"^POSTGRES", re.IGNORECASE), "postgresql", TechnologyCategory.DATABASE),
    (re.compile(r"^PG_", re.IGNORECASE), "postgresql", TechnologyCategory.DATABASE),
    (re.compile(r"^REDIS", re.IGNORECASE), "redis", TechnologyCategory.DATABASE),
    (re.compile(r"^MONGO", re.IGNORECASE), "mongodb", TechnologyCategory.DATABASE),
    (re.compile(r"^MYSQL", re.IGNORECASE), "mysql", TechnologyCategory.DATABASE),
    (re.compile(r"^SLACK_", re.IGNORECASE), "slack", TechnologyCategory.SERVICE),
    (re.compile(r"^GITHUB_", re.IGNORECASE), "github", TechnologyCategory.SERVICE),
    (re.compile(r"^GITLAB_", re.IGNORECASE), "gitlab", TechnologyCategory.SERVICE),
    (re.compile(r"^ELASTICSEARCH", re.IGNORECASE), "elasticsearch", TechnologyCategory.DATABASE),
    (re.compile(r"^RABBITMQ", re.IGNORECASE), "rabbitmq", TechnologyCategory.SERVICE),
    (re.compile(r"^SENTRY_", re.IGNORECASE), "sentry", TechnologyCategory.SERVICE),
    (re.compile(r"^STRIPE_", re.IGNORECASE), "stripe", TechnologyCategory.SERVICE),
    (re.compile(r"^OPENAI_", re.IGNORECASE), "openai", TechnologyCategory.SERVICE),
    (re.compile(r"^ANTHROPIC_", re.IGNORECASE), "anthropic", TechnologyCategory.SERVICE),
    (re.compile(r"^SUPABASE_", re.IGNORECASE), "supabase", TechnologyCategory.SERVICE),
    (re.compile(r"^FIREBASE_", re.IGNORECASE), "firebase", TechnologyCategory.SERVICE),
    (re.compile(r"^AWS_", re.IGNORECASE), "aws", TechnologyCategory.PLATFORM),
    (re.compile(r"^DATADOG_", re.IGNORECASE), "datadog", TechnologyCategory.SERVICE),
    (re.compile(r"^CLOUDFLARE_", re.IGNORECASE), "cloudflare", TechnologyCategory.PLATFORM),
    (re.compile(r"^LINEAR_", re.IGNORECASE), "linear", TechnologyCategory.SERVICE),
    (re.compile(r"^NOTION_", re.IGNORECASE), "notion", TechnologyCategory.SERVICE),
]


def _match_node_deps(
    dep_names: set[str],
    source_file: str,
) -> list[DetectedTechnology]:
    """Map Node.js dependency names to detected technologies."""
    techs: list[DetectedTechnology] = []
    matched_techs: set[str] = set()

    # Pass 1: exact match (highest confidence)
    for dep_name in dep_names:
        mapping = _NODE_DEP_MAP.get(dep_name.lower())
        if mapping is not None:
            tech_name, category = mapping
            matched_techs.add(tech_name)
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source_file,
                )
            )

    # Pass 2: @org/ prefix match (slightly lower confidence)
    for dep_name in dep_names:
        dep_lower = dep_name.lower()
        for prefix, tech_name, category in _NODE_PREFIX_MAP:
            if dep_lower.startswith(prefix) and tech_name not in matched_techs:
                matched_techs.add(tech_name)
                techs.append(
                    DetectedTechnology(
                        name=tech_name,
                        category=category,
                        source_file=source_file,
                        confidence=0.9,
                    )
                )
                break

    return techs


def _match_python_deps(
    dep_names: set[str],
    source_file: str,
) -> list[DetectedTechnology]:
    """Map Python dependency names to detected technologies."""
    techs: list[DetectedTechnology] = []
    for dep_name in dep_names:
        mapping = _PYTHON_DEP_MAP.get(dep_name.lower())
        if mapping is not None:
            tech_name, category = mapping
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source_file,
                )
            )
    return techs


def _match_docker_image(
    image_name: str,
    source_file: str,
) -> list[DetectedTechnology]:
    """Map a Docker image name to detected technologies.

    Checks if any known image name fragment appears in the full image string.
    For example, ``bitnami/postgresql:16`` matches the ``postgres`` fragment.
    """
    techs: list[DetectedTechnology] = []
    for fragment, (tech_name, category) in _DOCKER_IMAGE_MAP.items():
        if fragment in image_name:
            techs.append(
                DetectedTechnology(
                    name=tech_name,
                    category=category,
                    source_file=source_file,
                )
            )
    return techs


def _match_env_patterns(
    env_vars: list[str],
    source_file: str,
) -> list[DetectedTechnology]:
    """Detect technologies from env var naming patterns."""
    techs: list[DetectedTechnology] = []
    seen: set[str] = set()
    for var_name in env_vars:
        for pattern, tech_name, category in _ENV_PATTERNS:
            if pattern.search(var_name) and tech_name not in seen:
                seen.add(tech_name)
                techs.append(
                    DetectedTechnology(
                        name=tech_name,
                        category=category,
                        source_file=source_file,
                        confidence=0.7,
                    )
                )
    return techs


# ─── Utility Helpers ─────────────────────────────────────────


def _normalize_python_dep(raw: str) -> str:
    """Extract the bare package name from a pip requirement specifier.

    Examples:
        ``fastapi>=0.100`` → ``fastapi``
        ``psycopg2-binary[pool]`` → ``psycopg2-binary``
        ``django ~= 4.2`` → ``django``
    """
    # Strip version specifiers and extras
    name = re.split(r"[><=!~;\[\s]", raw, maxsplit=1)[0]
    return name.strip().lower()


def _deduplicate_technologies(
    techs: list[DetectedTechnology],
) -> list[DetectedTechnology]:
    """Remove duplicate technologies, keeping the highest confidence entry."""
    best: dict[tuple[str, str], DetectedTechnology] = {}
    for tech in techs:
        key = (tech.name, tech.source_file)
        existing = best.get(key)
        if existing is None or tech.confidence > existing.confidence:
            best[key] = tech
    return list(best.values())


async def _read_file(filepath: Path) -> str | None:
    """Read a file's text content asynchronously.

    Returns None if the file cannot be read (permissions, encoding, etc.).
    """
    try:
        return await asyncio.to_thread(filepath.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", filepath, exc)
        return None
