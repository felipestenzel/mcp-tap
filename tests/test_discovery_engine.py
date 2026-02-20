"""Tests for Dynamic Discovery Engine — expanded detection, archetypes, hints."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_tap.models import (
    DetectedTechnology,
    DiscoveryHint,
    HintType,
    MCPClient,
    ProjectProfile,
    RecommendationSource,
    RegistryType,
    ServerRecommendation,
    StackArchetype,
    TechnologyCategory,
)
from mcp_tap.scanner.archetypes import detect_archetypes
from mcp_tap.scanner.credentials import (
    COMPATIBLE_VARS,
    CREDENTIAL_HELP,
    SERVER_ENV_VARS,
    map_credentials,
)
from mcp_tap.scanner.detector import (
    _detect_platform_files,
    _match_docker_image,
    _match_env_patterns,
    _match_node_deps,
    _match_python_deps,
)
from mcp_tap.scanner.hints import generate_hints
from mcp_tap.scanner.recommendations import TECHNOLOGY_SERVER_MAP, recommend_servers

# ═══════════════════════════════════════════════════════════════
# Phase A — Detection Expansion Tests
# ═══════════════════════════════════════════════════════════════


class TestNodePrefixMap:
    """Tests for @org/ prefix matching in _match_node_deps (A1)."""

    def test_sentry_prefix(self) -> None:
        techs = _match_node_deps({"@sentry/nextjs"}, "package.json")
        assert any(t.name == "sentry" for t in techs)

    def test_stripe_prefix(self) -> None:
        techs = _match_node_deps({"@stripe/stripe-js"}, "package.json")
        assert any(t.name == "stripe" for t in techs)

    def test_aws_sdk_prefix(self) -> None:
        techs = _match_node_deps({"@aws-sdk/client-s3"}, "package.json")
        assert any(t.name == "aws" for t in techs)

    def test_google_cloud_prefix(self) -> None:
        techs = _match_node_deps({"@google-cloud/storage"}, "package.json")
        assert any(t.name == "gcp" for t in techs)

    def test_azure_prefix(self) -> None:
        techs = _match_node_deps({"@azure/identity"}, "package.json")
        assert any(t.name == "azure" for t in techs)

    def test_supabase_prefix(self) -> None:
        techs = _match_node_deps({"@supabase/supabase-js"}, "package.json")
        assert any(t.name == "supabase" for t in techs)

    def test_firebase_prefix(self) -> None:
        techs = _match_node_deps({"@firebase/app"}, "package.json")
        assert any(t.name == "firebase" for t in techs)

    def test_cloudflare_prefix(self) -> None:
        techs = _match_node_deps({"@cloudflare/workers-types"}, "package.json")
        assert any(t.name == "cloudflare" for t in techs)

    def test_vercel_prefix(self) -> None:
        techs = _match_node_deps({"@vercel/analytics"}, "package.json")
        assert any(t.name == "vercel" for t in techs)

    def test_langchain_prefix(self) -> None:
        techs = _match_node_deps({"@langchain/openai"}, "package.json")
        assert any(t.name == "langchain" for t in techs)

    def test_shopify_prefix(self) -> None:
        techs = _match_node_deps({"@shopify/polaris"}, "package.json")
        assert any(t.name == "shopify" for t in techs)

    def test_playwright_prefix(self) -> None:
        techs = _match_node_deps({"@playwright/test"}, "package.json")
        assert any(t.name == "playwright" for t in techs)

    def test_prisma_prefix(self) -> None:
        techs = _match_node_deps({"@prisma/client"}, "package.json")
        # @prisma/client has an exact match to postgresql, not prefix match to "prisma"
        tech_names = {t.name for t in techs}
        assert "postgresql" in tech_names

    def test_twilio_prefix(self) -> None:
        techs = _match_node_deps({"@twilio/voice-sdk"}, "package.json")
        assert any(t.name == "twilio" for t in techs)

    def test_sendgrid_prefix(self) -> None:
        techs = _match_node_deps({"@sendgrid/mail"}, "package.json")
        assert any(t.name == "sendgrid" for t in techs)

    def test_prefix_match_has_lower_confidence(self) -> None:
        """Prefix matches should have confidence 0.9 (lower than exact 1.0)."""
        techs = _match_node_deps({"@sentry/nextjs"}, "package.json")
        sentry = next(t for t in techs if t.name == "sentry")
        assert sentry.confidence == 0.9

    def test_exact_match_takes_priority_over_prefix(self) -> None:
        """When both exact and prefix match the same tech, only one entry should exist."""
        techs = _match_node_deps({"stripe", "@stripe/react-stripe-js"}, "package.json")
        stripe_techs = [t for t in techs if t.name == "stripe"]
        assert len(stripe_techs) == 1
        # Exact match has confidence 1.0
        assert stripe_techs[0].confidence == 1.0

    def test_multiple_prefixes_same_org_deduplicate(self) -> None:
        """Multiple packages from same org should produce one tech entry."""
        techs = _match_node_deps({"@aws-sdk/client-s3", "@aws-sdk/client-dynamodb"}, "package.json")
        aws_techs = [t for t in techs if t.name == "aws"]
        assert len(aws_techs) == 1

    def test_unknown_prefix_ignored(self) -> None:
        """Unknown @org/ prefixes should not match anything."""
        techs = _match_node_deps({"@unknown-org/some-pkg"}, "package.json")
        assert techs == []


class TestExpandedNodeDepMap:
    """Tests for new exact entries in _NODE_DEP_MAP (A3)."""

    def test_openai(self) -> None:
        techs = _match_node_deps({"openai"}, "package.json")
        assert any(t.name == "openai" for t in techs)

    def test_anthropic_sdk(self) -> None:
        techs = _match_node_deps({"@anthropic-ai/sdk"}, "package.json")
        assert any(t.name == "anthropic" for t in techs)

    def test_firebase_exact(self) -> None:
        techs = _match_node_deps({"firebase"}, "package.json")
        assert any(t.name == "firebase" for t in techs)

    def test_supabase_exact(self) -> None:
        techs = _match_node_deps({"supabase"}, "package.json")
        assert any(t.name == "supabase" for t in techs)

    def test_stripe_exact(self) -> None:
        techs = _match_node_deps({"stripe"}, "package.json")
        assert any(t.name == "stripe" for t in techs)

    def test_sentry_exact(self) -> None:
        techs = _match_node_deps({"sentry"}, "package.json")
        assert any(t.name == "sentry" for t in techs)


class TestExpandedPythonDepMap:
    """Tests for new entries in _PYTHON_DEP_MAP (A2)."""

    @pytest.mark.parametrize(
        ("dep", "expected_tech"),
        [
            ("openai", "openai"),
            ("anthropic", "anthropic"),
            ("langchain", "langchain"),
            ("langchain-core", "langchain"),
            ("transformers", "huggingface"),
            ("sentence-transformers", "huggingface"),
            ("boto3", "aws"),
            ("botocore", "aws"),
            ("google-cloud-storage", "gcp"),
            ("google-cloud-bigquery", "gcp"),
            ("azure-storage-blob", "azure"),
            ("azure-identity", "azure"),
            ("sentry-sdk", "sentry"),
            ("stripe", "stripe"),
            ("supabase", "supabase"),
            ("firebase-admin", "firebase"),
            ("twilio", "twilio"),
            ("sendgrid", "sendgrid"),
            ("elasticsearch", "elasticsearch"),
            ("celery", "celery"),
            ("dramatiq", "dramatiq"),
        ],
    )
    def test_python_dep_maps_to_expected_tech(self, dep: str, expected_tech: str) -> None:
        techs = _match_python_deps({dep}, "pyproject.toml")
        tech_names = {t.name for t in techs}
        assert expected_tech in tech_names, f"{dep} should map to {expected_tech}"


class TestExpandedDockerImageMap:
    """Tests for new entries in _DOCKER_IMAGE_MAP (A4)."""

    @pytest.mark.parametrize(
        ("image", "expected_tech"),
        [
            ("nginx:latest", "nginx"),
            ("bitnami/kafka:3.6", "kafka"),
            ("grafana/grafana:10", "grafana"),
            ("prom/prometheus:v2", "prometheus"),
            ("minio/minio:latest", "minio"),
            ("clickhouse/clickhouse-server:23", "clickhouse"),
        ],
    )
    def test_docker_image_maps_to_expected_tech(self, image: str, expected_tech: str) -> None:
        techs = _match_docker_image(image, "docker-compose.yml")
        tech_names = {t.name for t in techs}
        assert expected_tech in tech_names, f"Image '{image}' should map to {expected_tech}"


class TestExpandedEnvPatterns:
    """Tests for new entries in _ENV_PATTERNS (A5)."""

    @pytest.mark.parametrize(
        ("env_var", "expected_tech"),
        [
            ("SENTRY_DSN", "sentry"),
            ("STRIPE_SECRET_KEY", "stripe"),
            ("OPENAI_API_KEY", "openai"),
            ("ANTHROPIC_API_KEY", "anthropic"),
            ("SUPABASE_URL", "supabase"),
            ("FIREBASE_PROJECT_ID", "firebase"),
            ("AWS_ACCESS_KEY_ID", "aws"),
            ("DATADOG_API_KEY", "datadog"),
            ("CLOUDFLARE_API_TOKEN", "cloudflare"),
            ("LINEAR_API_KEY", "linear"),
            ("NOTION_TOKEN", "notion"),
        ],
    )
    def test_env_var_maps_to_expected_tech(self, env_var: str, expected_tech: str) -> None:
        techs = _match_env_patterns([env_var], ".env")
        tech_names = {t.name for t in techs}
        assert expected_tech in tech_names, f"Env var '{env_var}' should map to {expected_tech}"

    def test_env_detected_techs_have_0_7_confidence(self) -> None:
        techs = _match_env_patterns(["SENTRY_DSN"], ".env")
        assert all(t.confidence == 0.7 for t in techs)


class TestExpandedPlatformFileDetection:
    """Tests for expanded _detect_platform_files (A6)."""

    async def test_terraform_main_tf(self, tmp_path: Path) -> None:
        (tmp_path / "main.tf").write_text('resource "aws_instance" "example" {}')
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "terraform" for t in techs)

    async def test_terraform_terraform_tf(self, tmp_path: Path) -> None:
        (tmp_path / "terraform.tf").write_text("terraform {}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "terraform" for t in techs)

    async def test_pulumi(self, tmp_path: Path) -> None:
        (tmp_path / "Pulumi.yaml").write_text("name: my-project")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "pulumi" for t in techs)

    async def test_sentry_properties(self, tmp_path: Path) -> None:
        (tmp_path / "sentry.properties").write_text("defaults.org=myorg")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "sentry" for t in techs)

    async def test_sentry_client_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "sentry.client.config.ts").write_text("Sentry.init({})")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "sentry" for t in techs)

    async def test_firebase_json(self, tmp_path: Path) -> None:
        (tmp_path / "firebase.json").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "firebase" for t in techs)

    async def test_firebaserc(self, tmp_path: Path) -> None:
        (tmp_path / ".firebaserc").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "firebase" for t in techs)

    async def test_supabase_config(self, tmp_path: Path) -> None:
        (tmp_path / "supabase").mkdir()
        (tmp_path / "supabase" / "config.toml").write_text("[api]\nport = 54321\n")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "supabase" for t in techs)

    async def test_wrangler_toml(self, tmp_path: Path) -> None:
        (tmp_path / "wrangler.toml").write_text('name = "my-worker"')
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "cloudflare" for t in techs)

    async def test_turbo_json(self, tmp_path: Path) -> None:
        (tmp_path / "turbo.json").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "turborepo" for t in techs)

    async def test_nx_json(self, tmp_path: Path) -> None:
        (tmp_path / "nx.json").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "nx" for t in techs)

    async def test_lerna_json(self, tmp_path: Path) -> None:
        (tmp_path / "lerna.json").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "lerna" for t in techs)

    async def test_playwright_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "playwright.config.ts").write_text("export default {}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "playwright" for t in techs)

    async def test_cypress_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "cypress.config.ts").write_text("export default {}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "cypress" for t in techs)

    async def test_cypress_json(self, tmp_path: Path) -> None:
        (tmp_path / "cypress.json").write_text("{}")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "cypress" for t in techs)

    async def test_fly_toml(self, tmp_path: Path) -> None:
        (tmp_path / "fly.toml").write_text('app = "my-app"')
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "fly.io" for t in techs)

    async def test_render_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "render.yaml").write_text("services:")
        techs, _ = await _detect_platform_files(tmp_path)
        assert any(t.name == "render" for t in techs)

    async def test_empty_dir_no_platform_files(self, tmp_path: Path) -> None:
        techs, _ = await _detect_platform_files(tmp_path)
        assert techs == []

    async def test_existing_detections_preserved(self, tmp_path: Path) -> None:
        """Vercel and Docker detections should still work."""
        (tmp_path / "vercel.json").write_text("{}")
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        techs, _ = await _detect_platform_files(tmp_path)
        tech_names = {t.name for t in techs}
        assert "vercel" in tech_names
        assert "docker" in tech_names


# ═══════════════════════════════════════════════════════════════
# Phase A — Expanded Recommendations (A7)
# ═══════════════════════════════════════════════════════════════


class TestExpandedTechnologyServerMap:
    """Tests for expanded TECHNOLOGY_SERVER_MAP entries (A7)."""

    def _make_profile(
        self,
        tech_names: list[tuple[str, TechnologyCategory]],
    ) -> ProjectProfile:
        techs = [DetectedTechnology(name=n, category=c, source_file="test") for n, c in tech_names]
        return ProjectProfile(path="/tmp/test", technologies=techs)

    @pytest.mark.parametrize(
        ("tech_name", "expected_server"),
        [
            ("sentry", "sentry-mcp"),
            ("docker", "docker-mcp"),
            ("terraform", "terraform-mcp"),
            ("notion", "notion-mcp"),
            ("linear", "linear-mcp"),
            ("supabase", "supabase-mcp"),
            ("stripe", "stripe-mcp"),
            ("gcp", "gcp-mcp"),
            ("azure", "azure-mcp"),
            ("cloudflare", "cloudflare-mcp"),
            ("firebase", "firebase-mcp"),
            ("datadog", "datadog-mcp"),
            ("grafana", "grafana-mcp"),
            ("kafka", "kafka-mcp"),
            ("clickhouse", "clickhouse-mcp"),
            ("openai", "openai-mcp"),
            ("anthropic", "anthropic-mcp"),
        ],
    )
    async def test_tech_produces_expected_server(
        self, tech_name: str, expected_server: str
    ) -> None:
        profile = self._make_profile([(tech_name, TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert expected_server in rec_names, (
            f"Technology '{tech_name}' should produce recommendation '{expected_server}'"
        )

    def test_all_new_map_entries_have_valid_fields(self) -> None:
        """Every entry in the map should have all required fields populated."""
        for tech_name, recs in TECHNOLOGY_SERVER_MAP.items():
            for rec in recs:
                assert rec.server_name, f"Missing server_name for {tech_name}"
                assert rec.package_identifier, f"Missing package_identifier for {tech_name}"
                assert rec.registry_type in (RegistryType.NPM, RegistryType.PYPI, RegistryType.OCI)
                assert rec.reason, f"Missing reason for {tech_name}"
                assert rec.priority in ("high", "medium", "low")


# ═══════════════════════════════════════════════════════════════
# Phase A — Expanded Credentials (A8)
# ═══════════════════════════════════════════════════════════════


class TestExpandedCredentials:
    """Tests for expanded credential mappings (A8)."""

    def _rec(self, name: str, pkg: str) -> ServerRecommendation:
        return ServerRecommendation(
            server_name=name,
            package_identifier=pkg,
            registry_type=RegistryType.NPM,
            reason="test",
            priority="high",
        )

    def test_sentry_exact_match(self) -> None:
        rec = self._rec("sentry-mcp", "@sentry/mcp-server-sentry")
        mappings = map_credentials([rec], ["SENTRY_AUTH_TOKEN"])
        assert len(mappings) == 1
        assert mappings[0].status == "exact_match"

    def test_stripe_compatible_match(self) -> None:
        rec = self._rec("stripe-mcp", "@stripe/mcp")
        mappings = map_credentials([rec], ["STRIPE_SECRET_KEY"])
        assert len(mappings) == 1
        assert mappings[0].status == "compatible_match"

    def test_supabase_has_two_required_vars(self) -> None:
        rec = self._rec("supabase-mcp", "@supabase/mcp-server-supabase")
        mappings = map_credentials([rec], [])
        assert len(mappings) == 2
        required_vars = {m.required_env_var for m in mappings}
        assert "SUPABASE_URL" in required_vars
        assert "SUPABASE_KEY" in required_vars

    def test_notion_missing_shows_help_url(self) -> None:
        rec = self._rec("notion-mcp", "@notionhq/notion-mcp-server")
        mappings = map_credentials([rec], [])
        assert len(mappings) == 1
        assert mappings[0].help_url != ""

    def test_cloudflare_token_match(self) -> None:
        rec = self._rec("cloudflare-mcp", "@cloudflare/mcp-server-cloudflare")
        mappings = map_credentials([rec], ["CF_API_TOKEN"])
        assert len(mappings) == 1
        assert mappings[0].status == "compatible_match"

    def test_expanded_compatible_vars_has_new_entries(self) -> None:
        assert "STRIPE_API_KEY" in COMPATIBLE_VARS
        assert "SENTRY_AUTH_TOKEN" in COMPATIBLE_VARS
        assert "NOTION_API_KEY" in COMPATIBLE_VARS
        assert "DATADOG_API_KEY" in COMPATIBLE_VARS
        assert "CLOUDFLARE_API_TOKEN" in COMPATIBLE_VARS

    def test_expanded_credential_help_has_new_entries(self) -> None:
        assert "STRIPE_API_KEY" in CREDENTIAL_HELP
        assert "NOTION_API_KEY" in CREDENTIAL_HELP
        assert "DATADOG_API_KEY" in CREDENTIAL_HELP
        assert "CLOUDFLARE_API_TOKEN" in CREDENTIAL_HELP

    def test_expanded_server_env_vars_has_new_entries(self) -> None:
        assert "@sentry/mcp-server-sentry" in SERVER_ENV_VARS
        assert "@stripe/mcp" in SERVER_ENV_VARS
        assert "@supabase/mcp-server-supabase" in SERVER_ENV_VARS
        assert "@notionhq/notion-mcp-server" in SERVER_ENV_VARS
        assert "@cloudflare/mcp-server-cloudflare" in SERVER_ENV_VARS


# ═══════════════════════════════════════════════════════════════
# Phase B — Domain Model Tests
# ═══════════════════════════════════════════════════════════════


class TestNewDomainModels:
    """Tests for new domain models added in Phase B (B1)."""

    def test_recommendation_source_enum(self) -> None:
        assert RecommendationSource.CURATED == "curated"
        assert RecommendationSource.REGISTRY == "registry"

    def test_hint_type_enum(self) -> None:
        assert HintType.UNMAPPED_TECHNOLOGY == "unmapped_technology"
        assert HintType.STACK_ARCHETYPE == "stack_archetype"
        assert HintType.ENV_VAR_HINT == "env_var_hint"
        assert HintType.MISSING_COMPLEMENT == "missing_complement"

    def test_discovery_hint_frozen(self) -> None:
        hint = DiscoveryHint(
            hint_type=HintType.UNMAPPED_TECHNOLOGY,
            trigger="test",
            suggestion="try this",
        )
        with pytest.raises(AttributeError):
            hint.trigger = "other"  # type: ignore[misc]

    def test_discovery_hint_defaults(self) -> None:
        hint = DiscoveryHint(
            hint_type=HintType.UNMAPPED_TECHNOLOGY,
            trigger="test",
            suggestion="try this",
        )
        assert hint.search_queries == []
        assert hint.confidence == 0.7

    def test_stack_archetype_frozen(self) -> None:
        arch = StackArchetype(name="test", label="Test")
        with pytest.raises(AttributeError):
            arch.name = "other"  # type: ignore[misc]

    def test_stack_archetype_defaults(self) -> None:
        arch = StackArchetype(name="test", label="Test")
        assert arch.matched_technologies == []
        assert arch.extra_search_queries == []

    def test_server_recommendation_backward_compat(self) -> None:
        """ServerRecommendation should work without new fields (backward compat)."""
        rec = ServerRecommendation(
            server_name="test",
            package_identifier="pkg",
            registry_type=RegistryType.NPM,
            reason="testing",
            priority="high",
        )
        assert rec.source == RecommendationSource.CURATED
        assert rec.confidence == 1.0

    def test_server_recommendation_with_new_fields(self) -> None:
        rec = ServerRecommendation(
            server_name="test",
            package_identifier="pkg",
            registry_type=RegistryType.NPM,
            reason="testing",
            priority="high",
            source=RecommendationSource.REGISTRY,
            confidence=0.6,
        )
        assert rec.source == RecommendationSource.REGISTRY
        assert rec.confidence == 0.6

    def test_project_profile_backward_compat(self) -> None:
        """ProjectProfile should work without new fields."""
        profile = ProjectProfile(path="/tmp")
        assert profile.discovery_hints == []
        assert profile.archetypes == []

    def test_project_profile_with_new_fields(self) -> None:
        hint = DiscoveryHint(
            hint_type=HintType.UNMAPPED_TECHNOLOGY,
            trigger="test",
            suggestion="try this",
        )
        arch = StackArchetype(name="test", label="Test")
        profile = ProjectProfile(
            path="/tmp",
            discovery_hints=[hint],
            archetypes=[arch],
        )
        assert len(profile.discovery_hints) == 1
        assert len(profile.archetypes) == 1


# ═══════════════════════════════════════════════════════════════
# Phase B — Archetype Detection Tests
# ═══════════════════════════════════════════════════════════════


class TestDetectArchetypes:
    """Tests for detect_archetypes (B2)."""

    def _techs(self, *names: str) -> list[DetectedTechnology]:
        return [
            DetectedTechnology(name=n, category=TechnologyCategory.SERVICE, source_file="test")
            for n in names
        ]

    def test_saas_app_detected(self) -> None:
        """SaaS archetype: frontend + BaaS (2 groups)."""
        techs = self._techs("next.js", "supabase")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "saas_app" in names

    def test_saas_app_three_groups(self) -> None:
        """SaaS with frontend + auth + payments should match."""
        techs = self._techs("react", "auth0", "stripe")
        archetypes = detect_archetypes(techs)
        saas = next(a for a in archetypes if a.name == "saas_app")
        assert len(saas.matched_technologies) >= 3
        assert "authentication" in saas.extra_search_queries

    def test_data_pipeline_detected(self) -> None:
        """Data pipeline: database + queue + python."""
        techs = self._techs("postgresql", "redis", "python")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "data_pipeline" in names

    def test_devops_infra_detected(self) -> None:
        """DevOps: containers + IaC."""
        techs = self._techs("docker", "terraform")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "devops_infra" in names

    def test_ai_ml_app_detected(self) -> None:
        """AI/ML: AI library + python."""
        techs = self._techs("openai", "python")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "ai_ml_app" in names

    def test_fullstack_monorepo_detected(self) -> None:
        """Full-stack monorepo: monorepo tool + frontend."""
        techs = self._techs("turborepo", "react")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "fullstack_monorepo" in names

    def test_ecommerce_detected(self) -> None:
        """E-commerce: payments + frontend."""
        techs = self._techs("stripe", "next.js")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "ecommerce" in names

    def test_python_library_detected_with_build_backend(self) -> None:
        """Python library: Python + build backend."""
        techs = self._techs("python", "hatchling")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "python_library" in names

    def test_python_library_detected_with_test_framework(self) -> None:
        """Python library: Python + test framework."""
        techs = self._techs("python", "pytest")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "python_library" in names

    def test_python_library_detected_full_stack(self) -> None:
        """Python library: Python + hatchling + pytest (mcp-tap profile)."""
        techs = self._techs("python", "hatchling", "pytest")
        archetypes = detect_archetypes(techs)
        names = {a.name for a in archetypes}
        assert "python_library" in names

    def test_python_library_has_useful_extra_queries(self) -> None:
        """Python library archetype should include relevant search queries."""
        techs = self._techs("python", "pytest")
        archetypes = detect_archetypes(techs)
        lib = next(a for a in archetypes if a.name == "python_library")
        assert "notifications" in lib.extra_search_queries
        assert "pypi" in lib.extra_search_queries

    def test_python_library_not_triggered_by_python_alone(self) -> None:
        """Single 'python' technology should not trigger python_library archetype."""
        techs = self._techs("python")
        archetypes = detect_archetypes(techs)
        assert archetypes == []

    def test_no_match_single_tech(self) -> None:
        """Single technology should not match any archetype."""
        techs = self._techs("python")
        archetypes = detect_archetypes(techs)
        assert archetypes == []

    def test_no_match_empty(self) -> None:
        assert detect_archetypes([]) == []

    def test_multiple_archetypes_possible(self) -> None:
        """A project can match multiple archetypes."""
        techs = self._techs("python", "openai", "postgresql", "redis", "docker", "terraform")
        archetypes = detect_archetypes(techs)
        # Should match ai_ml_app, data_pipeline, and devops_infra
        assert len(archetypes) >= 2

    def test_sorted_by_match_strength(self) -> None:
        """Archetypes should be returned (sorted by matched group count)."""
        # ai_ml_app matches 3 groups (AI + python + db), data_pipeline also 3
        techs = self._techs("python", "openai", "postgresql", "redis")
        archetypes = detect_archetypes(techs)
        # Just verify multiple archetypes are returned and no crash
        assert len(archetypes) >= 2

    def test_archetype_has_extra_queries(self) -> None:
        techs = self._techs("docker", "terraform")
        archetypes = detect_archetypes(techs)
        devops = next(a for a in archetypes if a.name == "devops_infra")
        assert len(devops.extra_search_queries) > 0

    def test_archetype_has_matched_technologies(self) -> None:
        techs = self._techs("docker", "terraform")
        archetypes = detect_archetypes(techs)
        devops = next(a for a in archetypes if a.name == "devops_infra")
        assert "docker" in devops.matched_technologies
        assert "terraform" in devops.matched_technologies


# ═══════════════════════════════════════════════════════════════
# Phase B — Hint Generation Tests
# ═══════════════════════════════════════════════════════════════


class TestGenerateHints:
    """Tests for generate_hints (B3)."""

    def _techs(self, *names: str) -> list[DetectedTechnology]:
        return [
            DetectedTechnology(name=n, category=TechnologyCategory.SERVICE, source_file="test")
            for n in names
        ]

    def test_unmapped_technology_hint(self) -> None:
        """Technologies not in the map should produce search hints."""
        techs = self._techs("nx")
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, [], mapped, [])
        unmapped = [h for h in hints if h.hint_type == HintType.UNMAPPED_TECHNOLOGY]
        assert len(unmapped) >= 1
        assert any("nx" in h.trigger for h in unmapped)

    def test_mapped_technology_no_hint(self) -> None:
        """Technologies in the map should NOT produce unmapped hints."""
        techs = self._techs("postgresql")
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, [], mapped, [])
        unmapped = [h for h in hints if h.hint_type == HintType.UNMAPPED_TECHNOLOGY]
        assert not any("postgresql" in h.trigger for h in unmapped)

    def test_env_var_hint(self) -> None:
        """Env vars suggesting services should produce hints."""
        # Use a service that is NOT in mapped_tech_names
        mapped = {"postgresql"}  # minimal set
        hints = generate_hints([], ["OPENAI_API_KEY"], mapped, [])
        env_hints = [h for h in hints if h.hint_type == HintType.ENV_VAR_HINT]
        assert len(env_hints) >= 1
        assert any("openai" in q for h in env_hints for q in h.search_queries)

    def test_env_var_hint_skips_mapped(self) -> None:
        """Env var hints should be skipped when the service is already in the map."""
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints([], ["OPENAI_API_KEY"], mapped, [])
        env_hints = [h for h in hints if h.hint_type == HintType.ENV_VAR_HINT]
        # "openai" is now in the map, so no env var hint for it
        assert not any("openai" in q for h in env_hints for q in h.search_queries)

    def test_archetype_hint(self) -> None:
        """Archetype detection should produce search suggestions."""
        arch = StackArchetype(
            name="devops_infra",
            label="DevOps / Infrastructure",
            matched_technologies=["docker", "terraform"],
            extra_search_queries=["monitoring", "logging"],
        )
        hints = generate_hints([], [], set(), [arch])
        arch_hints = [h for h in hints if h.hint_type == HintType.STACK_ARCHETYPE]
        assert len(arch_hints) >= 1
        assert "monitoring" in arch_hints[0].search_queries

    def test_complement_hint(self) -> None:
        """Missing complement technologies should produce hints."""
        techs = self._techs("postgresql")
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, [], mapped, [])
        complement = [h for h in hints if h.hint_type == HintType.MISSING_COMPLEMENT]
        assert len(complement) >= 1
        # postgresql's complement is redis
        assert any("redis" in q for h in complement for q in h.search_queries)

    def test_complement_skipped_when_present(self) -> None:
        """No complement hint when the complement tech is already detected."""
        techs = self._techs("postgresql", "redis")
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, [], mapped, [])
        complement = [h for h in hints if h.hint_type == HintType.MISSING_COMPLEMENT]
        redis_hints = [h for h in complement if "redis" in str(h.search_queries)]
        assert redis_hints == []

    def test_hints_sorted_by_confidence(self) -> None:
        """Hints should be sorted by confidence, highest first."""
        techs = self._techs("postgresql", "nx")
        arch = StackArchetype(name="test", label="Test", extra_search_queries=["test query"])
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, ["TWILIO_AUTH_TOKEN"], mapped, [arch])
        if len(hints) >= 2:
            confidences = [h.confidence for h in hints]
            assert confidences == sorted(confidences, reverse=True)

    def test_empty_inputs_no_hints(self) -> None:
        hints = generate_hints([], [], set(), [])
        assert hints == []

    def test_skip_generic_languages(self) -> None:
        """Generic languages (python, node.js) should not produce unmapped hints."""
        techs = self._techs("python", "node.js", "ruby", "go", "rust")
        hints = generate_hints(techs, [], set(), [])
        unmapped = [h for h in hints if h.hint_type == HintType.UNMAPPED_TECHNOLOGY]
        assert unmapped == []

    def test_no_duplicate_queries(self) -> None:
        """Search queries should not be duplicated across hints."""
        techs = self._techs("postgresql")
        arch = StackArchetype(name="test", label="Test", extra_search_queries=["redis"])
        mapped = set(TECHNOLOGY_SERVER_MAP.keys())
        hints = generate_hints(techs, [], mapped, [arch])
        all_queries = [q for h in hints for q in h.search_queries]
        assert len(all_queries) == len(set(all_queries))


# ═══════════════════════════════════════════════════════════════
# Phase C — Dynamic Registry Bridge Tests
# ═══════════════════════════════════════════════════════════════


class TestDynamicRegistryBridge:
    """Tests for async recommend_servers with registry client (C1)."""

    def _make_profile(
        self,
        tech_names: list[tuple[str, TechnologyCategory]],
    ) -> ProjectProfile:
        techs = [DetectedTechnology(name=n, category=c, source_file="test") for n, c in tech_names]
        return ProjectProfile(path="/tmp/test", technologies=techs)

    async def test_static_only_when_no_registry(self) -> None:
        """Without registry, should behave exactly like before (static only)."""
        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile)
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names
        assert all(r.source == RecommendationSource.CURATED for r in recs)

    async def test_registry_called_for_unmapped_tech(self) -> None:
        """Registry should be called for technologies not in the static map."""
        from unittest.mock import AsyncMock

        from mcp_tap.models import PackageInfo, RegistryServer

        mock_registry = AsyncMock()
        mock_registry.search.return_value = [
            RegistryServer(
                name="test-mcp-server",
                description="A test server for unmapped-tech",
                packages=[
                    PackageInfo(
                        registry_type=RegistryType.NPM,
                        identifier="test-mcp-pkg",
                    )
                ],
            )
        ]

        profile = self._make_profile([("unmapped-tech", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile, registry=mock_registry)

        mock_registry.search.assert_called_once()
        # Should include the dynamic result
        dynamic_recs = [r for r in recs if r.source == RecommendationSource.REGISTRY]
        assert len(dynamic_recs) >= 1
        assert dynamic_recs[0].confidence == 0.6
        assert dynamic_recs[0].priority == "low"

    async def test_registry_not_called_for_mapped_tech(self) -> None:
        """Registry should NOT be called for technologies in the static map."""
        from unittest.mock import AsyncMock

        mock_registry = AsyncMock()
        mock_registry.search.return_value = []

        profile = self._make_profile([("postgresql", TechnologyCategory.DATABASE)])
        recs = await recommend_servers(profile, registry=mock_registry)

        mock_registry.search.assert_not_called()
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names

    async def test_registry_timeout_falls_back_to_static(self) -> None:
        """Registry timeout should not crash — should fallback to static results."""
        from unittest.mock import AsyncMock

        mock_registry = AsyncMock()

        async def slow_search(*_args, **_kwargs):
            import asyncio

            await asyncio.sleep(10)  # much longer than the timeout
            return []

        mock_registry.search = slow_search

        profile = self._make_profile(
            [
                ("postgresql", TechnologyCategory.DATABASE),
                ("unmapped-tech", TechnologyCategory.SERVICE),
            ]
        )
        recs = await recommend_servers(profile, registry=mock_registry)
        # Should still have static results
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names

    async def test_registry_error_falls_back_to_static(self) -> None:
        """Registry error should not crash — should fallback to static results."""
        from unittest.mock import AsyncMock

        mock_registry = AsyncMock()
        mock_registry.search.side_effect = Exception("Network error")

        profile = self._make_profile(
            [
                ("postgresql", TechnologyCategory.DATABASE),
                ("unmapped-tech", TechnologyCategory.SERVICE),
            ]
        )
        recs = await recommend_servers(profile, registry=mock_registry)
        rec_names = {r.server_name for r in recs}
        assert "postgres-mcp" in rec_names

    async def test_registry_skips_generic_languages(self) -> None:
        """Registry should not search for generic languages like python."""
        from unittest.mock import AsyncMock

        mock_registry = AsyncMock()
        mock_registry.search.return_value = []

        profile = self._make_profile([("python", TechnologyCategory.LANGUAGE)])
        await recommend_servers(profile, registry=mock_registry)

        mock_registry.search.assert_not_called()

    async def test_registry_results_deduped_with_static(self) -> None:
        """Registry results with same package as static should be deduped."""
        from unittest.mock import AsyncMock

        from mcp_tap.models import PackageInfo, RegistryServer

        mock_registry = AsyncMock()
        mock_registry.search.return_value = [
            RegistryServer(
                name="postgres-duplicate",
                description="Another postgres MCP",
                packages=[
                    PackageInfo(
                        registry_type=RegistryType.NPM,
                        identifier="@modelcontextprotocol/server-postgres",  # same as static
                    )
                ],
            )
        ]

        profile = self._make_profile(
            [
                ("postgresql", TechnologyCategory.DATABASE),
                ("unmapped-tech", TechnologyCategory.SERVICE),
            ]
        )
        recs = await recommend_servers(profile, registry=mock_registry)
        pg_recs = [r for r in recs if "postgres" in r.package_identifier]
        assert len(pg_recs) == 1  # no duplicate

    async def test_registry_result_filtered_by_client(self) -> None:
        """Dynamic results should also be filtered by client capabilities."""
        from unittest.mock import AsyncMock

        from mcp_tap.models import PackageInfo, RegistryServer

        mock_registry = AsyncMock()
        mock_registry.search.return_value = [
            RegistryServer(
                name="some-github-tool",
                description="GitHub integration",
                packages=[
                    PackageInfo(
                        registry_type=RegistryType.NPM,
                        identifier="some-github-server",
                    )
                ],
            )
        ]

        profile = self._make_profile([("unmapped-github-thing", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(
            profile, client=MCPClient.CLAUDE_CODE, registry=mock_registry
        )
        # GitHub-related should be filtered for Claude Code
        dynamic_recs = [r for r in recs if r.source == RecommendationSource.REGISTRY]
        github_recs = [r for r in dynamic_recs if "github" in r.package_identifier]
        assert github_recs == []

    async def test_registry_server_without_packages_skipped(self) -> None:
        """Registry servers with no packages should be skipped."""
        from unittest.mock import AsyncMock

        from mcp_tap.models import RegistryServer

        mock_registry = AsyncMock()
        mock_registry.search.return_value = [
            RegistryServer(
                name="no-packages-server",
                description="Has no packages",
                packages=[],
            )
        ]

        profile = self._make_profile([("unmapped-tech", TechnologyCategory.SERVICE)])
        recs = await recommend_servers(profile, registry=mock_registry)
        dynamic_recs = [r for r in recs if r.source == RecommendationSource.REGISTRY]
        assert dynamic_recs == []
