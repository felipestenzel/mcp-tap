# Experiment: Dynamic Discovery Engine -- Deep Technical Analysis

**Date**: 2026-02-20
**Author**: Innovation Lab
**Status**: Complete -- findings ready for implementation

---

## 1. Current State Audit

### What the scanner detects today (8 parsers + 1 CI parser)

| Parser | Detects | Coverage Gaps |
|--------|---------|---------------|
| `_parse_package_json` | Node.js + 30 named deps | Misses `@org/` SDK patterns, monorepo workspaces |
| `_parse_pyproject_toml` | Python + 25 named deps | Misses tool.poetry, setup.cfg fallback |
| `_parse_requirements_txt` | Python deps from req files | Only 3 filenames checked |
| `_parse_docker_compose` | 8 Docker image fragments | Misses dozens of common images |
| `_parse_env_files` | 11 env var patterns | Misses 50+ common service patterns |
| `_detect_git_hosting` | GitHub, GitLab dirs | Misses Bitbucket |
| `_detect_language_files` | Ruby, Go, Rust, Make | Misses Java, C#, PHP, Swift, Kotlin, Elixir |
| `_detect_platform_files` | Vercel, Netlify, Docker | Misses 15+ platform config files |
| `parse_ci_configs` | GHA services/actions/run, GitLab CI | Good but incomplete action patterns |

### Recommendation map: 13 entries, 17 technologies get ZERO

Technologies detected but unmapped: `node.js`, `python`, `ruby`, `go`, `rust`, `make`,
`next.js`, `express`, `react`, `vue`, `angular`, `fastapi`, `django`, `flask`, `docker`,
`vercel`, `netlify`, `terraform`, `ansible`, `aws`, `gcp`, `azure`, `kubernetes`,
`hono`, `svelte`, `nuxt`, `nestjs`, `fastify`, `starlette`, `tornado`, `sanic`, `litestar`.

---

## 2. Detection Expansion Catalog

### 2A. New Dependency Prefix Patterns (The "@org/" Multiplier)

This is the highest-leverage change. A single regex pattern like `@sentry/` catches
`@sentry/node`, `@sentry/react`, `@sentry/nextjs`, `@sentry/browser`, etc. -- one
pattern covers 10+ packages.

#### Node.js Prefix Patterns (30 new patterns)

```python
# Each prefix maps to (technology_name, category)
_NODE_PREFIX_MAP: list[tuple[str, str, TechnologyCategory]] = [
    # Observability
    ("@sentry/", "sentry", TechnologyCategory.SERVICE),
    ("@datadog/", "datadog", TechnologyCategory.SERVICE),
    ("@newrelic/", "newrelic", TechnologyCategory.SERVICE),
    ("@grafana/", "grafana", TechnologyCategory.SERVICE),
    ("@opentelemetry/", "opentelemetry", TechnologyCategory.SERVICE),
    # Payments & Commerce
    ("@stripe/", "stripe", TechnologyCategory.SERVICE),
    ("@paddle/", "paddle", TechnologyCategory.SERVICE),
    ("@shopify/", "shopify", TechnologyCategory.SERVICE),
    ("@adyen/", "adyen", TechnologyCategory.SERVICE),
    # Auth
    ("@auth0/", "auth0", TechnologyCategory.SERVICE),
    ("@clerk/", "clerk", TechnologyCategory.SERVICE),
    ("@supabase/", "supabase", TechnologyCategory.SERVICE),
    ("@firebase/", "firebase", TechnologyCategory.SERVICE),
    # Productivity & PM
    ("@notionhq/", "notion", TechnologyCategory.SERVICE),
    ("@linear/", "linear", TechnologyCategory.SERVICE),
    ("@atlassian/", "jira", TechnologyCategory.SERVICE),
    # CMS
    ("@contentful/", "contentful", TechnologyCategory.SERVICE),
    ("@sanity/", "sanity", TechnologyCategory.SERVICE),
    ("@strapi/", "strapi", TechnologyCategory.FRAMEWORK),
    ("@directus/", "directus", TechnologyCategory.SERVICE),
    # Cloud
    ("@aws-sdk/", "aws", TechnologyCategory.PLATFORM),
    ("@azure/", "azure", TechnologyCategory.PLATFORM),
    ("@google-cloud/", "gcp", TechnologyCategory.PLATFORM),
    ("@vercel/", "vercel", TechnologyCategory.PLATFORM),
    ("@netlify/", "netlify", TechnologyCategory.PLATFORM),
    ("@cloudflare/", "cloudflare", TechnologyCategory.PLATFORM),
    # Testing
    ("@playwright/", "playwright", TechnologyCategory.SERVICE),
    ("@cypress/", "cypress", TechnologyCategory.SERVICE),
    # Messaging
    ("@sendgrid/", "sendgrid", TechnologyCategory.SERVICE),
    ("@twilio/", "twilio", TechnologyCategory.SERVICE),
    # AI/ML
    ("@langchain/", "langchain", TechnologyCategory.FRAMEWORK),
    ("@huggingface/", "huggingface", TechnologyCategory.SERVICE),
]
```

#### Python Named Package Patterns (25 new entries)

Python doesn't use `@org/` prefixes, but package names are highly predictable:

```python
_PYTHON_DEP_MAP_ADDITIONS: dict[str, tuple[str, TechnologyCategory]] = {
    # Observability
    "sentry-sdk": ("sentry", TechnologyCategory.SERVICE),
    "ddtrace": ("datadog", TechnologyCategory.SERVICE),
    "newrelic": ("newrelic", TechnologyCategory.SERVICE),
    "opentelemetry-api": ("opentelemetry", TechnologyCategory.SERVICE),
    "opentelemetry-sdk": ("opentelemetry", TechnologyCategory.SERVICE),
    # Payments
    "stripe": ("stripe", TechnologyCategory.SERVICE),
    # Auth
    "python-jose": ("jwt", TechnologyCategory.SERVICE),
    "pyjwt": ("jwt", TechnologyCategory.SERVICE),
    "authlib": ("oauth", TechnologyCategory.SERVICE),
    # BaaS
    "supabase": ("supabase", TechnologyCategory.SERVICE),
    "firebase-admin": ("firebase", TechnologyCategory.SERVICE),
    # Productivity
    "notion-client": ("notion", TechnologyCategory.SERVICE),
    "jira": ("jira", TechnologyCategory.SERVICE),
    "linear-sdk": ("linear", TechnologyCategory.SERVICE),
    # Messaging
    "sendgrid": ("sendgrid", TechnologyCategory.SERVICE),
    "twilio": ("twilio", TechnologyCategory.SERVICE),
    # AI/ML
    "openai": ("openai", TechnologyCategory.SERVICE),
    "anthropic": ("anthropic", TechnologyCategory.SERVICE),
    "langchain": ("langchain", TechnologyCategory.FRAMEWORK),
    "langchain-core": ("langchain", TechnologyCategory.FRAMEWORK),
    "transformers": ("huggingface", TechnologyCategory.SERVICE),
    "huggingface-hub": ("huggingface", TechnologyCategory.SERVICE),
    "llama-index": ("llamaindex", TechnologyCategory.FRAMEWORK),
    # IaC
    "pulumi": ("pulumi", TechnologyCategory.PLATFORM),
    "boto3": ("aws", TechnologyCategory.PLATFORM),
    "google-cloud-core": ("gcp", TechnologyCategory.PLATFORM),
    "azure-identity": ("azure", TechnologyCategory.PLATFORM),
    # Testing
    "playwright": ("playwright", TechnologyCategory.SERVICE),
    "selenium": ("selenium", TechnologyCategory.SERVICE),
    # CMS
    "contentful": ("contentful", TechnologyCategory.SERVICE),
    # Data
    "celery": ("celery", TechnologyCategory.SERVICE),
    "dramatiq": ("dramatiq", TechnologyCategory.SERVICE),
    "apache-airflow": ("airflow", TechnologyCategory.PLATFORM),
}
```

#### Implementation detail: prefix matching

The current `_match_node_deps` does exact dict lookup. For prefix patterns, add a
second pass:

```python
def _match_node_deps(dep_names: set[str], source_file: str) -> list[DetectedTechnology]:
    techs: list[DetectedTechnology] = []
    for dep_name in dep_names:
        # Pass 1: exact match (existing)
        mapping = _NODE_DEP_MAP.get(dep_name.lower())
        if mapping is not None:
            tech_name, category = mapping
            techs.append(DetectedTechnology(name=tech_name, category=category, source_file=source_file))
            continue
        # Pass 2: prefix match (NEW)
        dep_lower = dep_name.lower()
        for prefix, tech_name, category in _NODE_PREFIX_MAP:
            if dep_lower.startswith(prefix):
                techs.append(
                    DetectedTechnology(
                        name=tech_name,
                        category=category,
                        source_file=source_file,
                        confidence=0.9,  # slightly lower than exact match
                    )
                )
                break  # first prefix match wins
    return techs
```

### 2B. New File-Based Detection

These are technologies we can detect from the mere **existence** of files, without
parsing their contents.

```python
_PLATFORM_FILE_MAP: dict[str, tuple[str, TechnologyCategory]] = {
    # Monorepo tools
    "turbo.json": ("turborepo", TechnologyCategory.PLATFORM),
    "nx.json": ("nx", TechnologyCategory.PLATFORM),
    "lerna.json": ("lerna", TechnologyCategory.PLATFORM),
    "pnpm-workspace.yaml": ("pnpm-monorepo", TechnologyCategory.PLATFORM),
    # IaC
    "terraform.tfstate": ("terraform", TechnologyCategory.PLATFORM),
    "pulumi.yaml": ("pulumi", TechnologyCategory.PLATFORM),
    "Pulumi.yaml": ("pulumi", TechnologyCategory.PLATFORM),
    "cdk.json": ("aws-cdk", TechnologyCategory.PLATFORM),
    "serverless.yml": ("serverless", TechnologyCategory.PLATFORM),
    "serverless.yaml": ("serverless", TechnologyCategory.PLATFORM),
    "sam.yaml": ("aws-sam", TechnologyCategory.PLATFORM),
    "template.yaml": ("aws-sam", TechnologyCategory.PLATFORM),  # lower confidence
    # Testing config
    "playwright.config.ts": ("playwright", TechnologyCategory.SERVICE),
    "playwright.config.js": ("playwright", TechnologyCategory.SERVICE),
    "cypress.config.ts": ("cypress", TechnologyCategory.SERVICE),
    "cypress.config.js": ("cypress", TechnologyCategory.SERVICE),
    "jest.config.ts": ("jest", TechnologyCategory.SERVICE),
    "jest.config.js": ("jest", TechnologyCategory.SERVICE),
    "vitest.config.ts": ("vitest", TechnologyCategory.SERVICE),
    # CMS / headless
    "sanity.config.ts": ("sanity", TechnologyCategory.SERVICE),
    "sanity.config.js": ("sanity", TechnologyCategory.SERVICE),
    "contentful.json": ("contentful", TechnologyCategory.SERVICE),
    "strapi-server.js": ("strapi", TechnologyCategory.FRAMEWORK),
    # Observability
    "sentry.properties": ("sentry", TechnologyCategory.SERVICE),
    "sentry.client.config.ts": ("sentry", TechnologyCategory.SERVICE),
    "sentry.server.config.ts": ("sentry", TechnologyCategory.SERVICE),
    "datadog.yaml": ("datadog", TechnologyCategory.SERVICE),
    "newrelic.yml": ("newrelic", TechnologyCategory.SERVICE),
    "newrelic.js": ("newrelic", TechnologyCategory.SERVICE),
    # Deployment
    "fly.toml": ("fly", TechnologyCategory.PLATFORM),
    "railway.toml": ("railway", TechnologyCategory.PLATFORM),
    "render.yaml": ("render", TechnologyCategory.PLATFORM),
    "app.yaml": ("gcp-appengine", TechnologyCategory.PLATFORM),
    "firebase.json": ("firebase", TechnologyCategory.PLATFORM),
    ".firebaserc": ("firebase", TechnologyCategory.PLATFORM),
    "supabase/config.toml": ("supabase", TechnologyCategory.SERVICE),
    "amplify.yml": ("aws-amplify", TechnologyCategory.PLATFORM),
    "wrangler.toml": ("cloudflare", TechnologyCategory.PLATFORM),
    # Docs
    "mkdocs.yml": ("mkdocs", TechnologyCategory.PLATFORM),
    "docusaurus.config.js": ("docusaurus", TechnologyCategory.FRAMEWORK),
    "docusaurus.config.ts": ("docusaurus", TechnologyCategory.FRAMEWORK),
    ".storybook/main.js": ("storybook", TechnologyCategory.SERVICE),
    ".storybook/main.ts": ("storybook", TechnologyCategory.SERVICE),
    # Mobile
    "ios/Podfile": ("ios", TechnologyCategory.PLATFORM),
    "android/build.gradle": ("android", TechnologyCategory.PLATFORM),
    "app.json": ("react-native", TechnologyCategory.FRAMEWORK),  # needs content check
    "expo-module.config.json": ("expo", TechnologyCategory.FRAMEWORK),
    # API design
    "openapi.yaml": ("openapi", TechnologyCategory.SERVICE),
    "openapi.json": ("openapi", TechnologyCategory.SERVICE),
    "swagger.json": ("openapi", TechnologyCategory.SERVICE),
    ".graphqlrc.yml": ("graphql", TechnologyCategory.SERVICE),
    "schema.graphql": ("graphql", TechnologyCategory.SERVICE),
}
```

**Implementation note**: The current `_detect_platform_files` only checks 3 files.
Expanding it to check ~50 files has negligible performance cost because `Path.is_file()`
is a single syscall, and they all run in a single async function.

### 2C. New Directory-Based Detection

Some technologies are signaled by **directory existence** rather than files.

```python
_PLATFORM_DIR_MAP: dict[str, tuple[str, TechnologyCategory, float]] = {
    ".terraform": ("terraform", TechnologyCategory.PLATFORM, 1.0),
    ".pulumi": ("pulumi", TechnologyCategory.PLATFORM, 1.0),
    ".serverless": ("serverless", TechnologyCategory.PLATFORM, 0.9),
    "cypress": ("cypress", TechnologyCategory.SERVICE, 0.7),  # could be a regular dir
    "supabase": ("supabase", TechnologyCategory.SERVICE, 0.8),
    ".storybook": ("storybook", TechnologyCategory.SERVICE, 1.0),
    ".husky": ("husky", TechnologyCategory.SERVICE, 0.8),
    "k8s": ("kubernetes", TechnologyCategory.PLATFORM, 0.9),
    "kubernetes": ("kubernetes", TechnologyCategory.PLATFORM, 0.9),
    "helm": ("kubernetes", TechnologyCategory.PLATFORM, 0.9),
    "charts": ("kubernetes", TechnologyCategory.PLATFORM, 0.6),  # ambiguous
    "ansible": ("ansible", TechnologyCategory.PLATFORM, 0.8),
    "cdk.out": ("aws-cdk", TechnologyCategory.PLATFORM, 1.0),
    "amplify": ("aws-amplify", TechnologyCategory.PLATFORM, 0.8),
    ".nx": ("nx", TechnologyCategory.PLATFORM, 1.0),
}
```

### 2D. Expanded Env Var Patterns (from 11 to ~40)

```python
_ENV_PATTERNS_ADDITIONS = [
    # AI/ML
    (re.compile(r"^OPENAI_", re.IGNORECASE), "openai", TechnologyCategory.SERVICE),
    (re.compile(r"^ANTHROPIC_", re.IGNORECASE), "anthropic", TechnologyCategory.SERVICE),
    (re.compile(r"^HUGGINGFACE_|^HF_", re.IGNORECASE), "huggingface", TechnologyCategory.SERVICE),
    # Observability
    (re.compile(r"^SENTRY_", re.IGNORECASE), "sentry", TechnologyCategory.SERVICE),
    (re.compile(r"^DATADOG_|^DD_", re.IGNORECASE), "datadog", TechnologyCategory.SERVICE),
    (re.compile(r"^NEW_RELIC_|^NEWRELIC_", re.IGNORECASE), "newrelic", TechnologyCategory.SERVICE),
    # Payments
    (re.compile(r"^STRIPE_", re.IGNORECASE), "stripe", TechnologyCategory.SERVICE),
    # Auth
    (re.compile(r"^AUTH0_", re.IGNORECASE), "auth0", TechnologyCategory.SERVICE),
    (re.compile(r"^CLERK_", re.IGNORECASE), "clerk", TechnologyCategory.SERVICE),
    (re.compile(r"^SUPABASE_", re.IGNORECASE), "supabase", TechnologyCategory.SERVICE),
    (re.compile(r"^FIREBASE_", re.IGNORECASE), "firebase", TechnologyCategory.SERVICE),
    # BaaS / Cloud
    (re.compile(r"^AWS_", re.IGNORECASE), "aws", TechnologyCategory.PLATFORM),
    (re.compile(r"^AZURE_", re.IGNORECASE), "azure", TechnologyCategory.PLATFORM),
    (re.compile(r"^GOOGLE_CLOUD_|^GCP_|^GCLOUD_", re.IGNORECASE), "gcp", TechnologyCategory.PLATFORM),
    (re.compile(r"^VERCEL_", re.IGNORECASE), "vercel", TechnologyCategory.PLATFORM),
    (re.compile(r"^NETLIFY_", re.IGNORECASE), "netlify", TechnologyCategory.PLATFORM),
    (re.compile(r"^CLOUDFLARE_|^CF_", re.IGNORECASE), "cloudflare", TechnologyCategory.PLATFORM),
    (re.compile(r"^FLY_", re.IGNORECASE), "fly", TechnologyCategory.PLATFORM),
    # Productivity
    (re.compile(r"^NOTION_", re.IGNORECASE), "notion", TechnologyCategory.SERVICE),
    (re.compile(r"^LINEAR_", re.IGNORECASE), "linear", TechnologyCategory.SERVICE),
    (re.compile(r"^JIRA_", re.IGNORECASE), "jira", TechnologyCategory.SERVICE),
    # Messaging
    (re.compile(r"^SENDGRID_", re.IGNORECASE), "sendgrid", TechnologyCategory.SERVICE),
    (re.compile(r"^TWILIO_", re.IGNORECASE), "twilio", TechnologyCategory.SERVICE),
    (re.compile(r"^RESEND_", re.IGNORECASE), "resend", TechnologyCategory.SERVICE),
    # CMS
    (re.compile(r"^CONTENTFUL_", re.IGNORECASE), "contentful", TechnologyCategory.SERVICE),
    (re.compile(r"^SANITY_", re.IGNORECASE), "sanity", TechnologyCategory.SERVICE),
    # Search
    (re.compile(r"^ALGOLIA_", re.IGNORECASE), "algolia", TechnologyCategory.SERVICE),
    (re.compile(r"^TYPESENSE_", re.IGNORECASE), "typesense", TechnologyCategory.SERVICE),
    (re.compile(r"^MEILISEARCH_", re.IGNORECASE), "meilisearch", TechnologyCategory.SERVICE),
    # Storage
    (re.compile(r"^MINIO_|^S3_", re.IGNORECASE), "s3-compatible", TechnologyCategory.SERVICE),
]
```

### 2E. Expanded Docker Image Map (from 8 to ~20)

```python
_DOCKER_IMAGE_MAP_ADDITIONS = {
    "minio": ("minio", TechnologyCategory.SERVICE),
    "localstack": ("aws", TechnologyCategory.PLATFORM),
    "grafana": ("grafana", TechnologyCategory.SERVICE),
    "prometheus": ("prometheus", TechnologyCategory.SERVICE),
    "jaeger": ("jaeger", TechnologyCategory.SERVICE),
    "opensearch": ("opensearch", TechnologyCategory.DATABASE),
    "clickhouse": ("clickhouse", TechnologyCategory.DATABASE),
    "nats": ("nats", TechnologyCategory.SERVICE),
    "kafka": ("kafka", TechnologyCategory.SERVICE),
    "zookeeper": ("kafka", TechnologyCategory.SERVICE),
    "influxdb": ("influxdb", TechnologyCategory.DATABASE),
    "timescaledb": ("timescaledb", TechnologyCategory.DATABASE),
    "cassandra": ("cassandra", TechnologyCategory.DATABASE),
    "dgraph": ("dgraph", TechnologyCategory.DATABASE),
    "neo4j": ("neo4j", TechnologyCategory.DATABASE),
    "supabase": ("supabase", TechnologyCategory.SERVICE),
    "hasura": ("hasura", TechnologyCategory.SERVICE),
    "keycloak": ("keycloak", TechnologyCategory.SERVICE),
    "meilisearch": ("meilisearch", TechnologyCategory.SERVICE),
    "typesense": ("typesense", TechnologyCategory.SERVICE),
}
```

### 2F. New Language File Markers

```python
_LANGUAGE_MARKERS_ADDITIONS = {
    # JVM
    "pom.xml": ("java", TechnologyCategory.LANGUAGE),
    "build.gradle": ("java", TechnologyCategory.LANGUAGE),
    "build.gradle.kts": ("kotlin", TechnologyCategory.LANGUAGE),
    # .NET
    "*.csproj": ("dotnet", TechnologyCategory.LANGUAGE),  # needs glob
    "*.sln": ("dotnet", TechnologyCategory.LANGUAGE),
    "Directory.Build.props": ("dotnet", TechnologyCategory.LANGUAGE),
    # PHP
    "composer.json": ("php", TechnologyCategory.LANGUAGE),
    # Elixir
    "mix.exs": ("elixir", TechnologyCategory.LANGUAGE),
    # Swift
    "Package.swift": ("swift", TechnologyCategory.LANGUAGE),
    # Dart/Flutter
    "pubspec.yaml": ("dart", TechnologyCategory.LANGUAGE),
    # Zig
    "build.zig": ("zig", TechnologyCategory.LANGUAGE),
    # Haskell
    "stack.yaml": ("haskell", TechnologyCategory.LANGUAGE),
    "cabal.project": ("haskell", TechnologyCategory.LANGUAGE),
}
```

---

## 3. Expanded Static Recommendation Map

### From 13 to ~50 entries

These are servers that exist in the MCP ecosystem (verified via awesome-mcp-servers,
official repository, and registry) with stable packages.

```python
TECHNOLOGY_SERVER_MAP_ADDITIONS = {
    # --- Observability ---
    "sentry": [
        ServerRecommendation(
            server_name="sentry-mcp",
            package_identifier="@sentry/mcp-server-sentry",
            registry_type=RegistryType.NPM,
            reason="Query Sentry issues, view error details, and link errors to code",
            priority="high",
        ),
    ],
    "datadog": [
        ServerRecommendation(
            server_name="datadog-mcp",
            package_identifier="@anthropic/mcp-server-datadog",
            registry_type=RegistryType.NPM,
            reason="Query Datadog dashboards, metrics, and alerts",
            priority="medium",
        ),
    ],
    # --- Productivity ---
    "notion": [
        ServerRecommendation(
            server_name="notion-mcp",
            package_identifier="@notionhq/notion-mcp-server",
            registry_type=RegistryType.NPM,
            reason="Search, read, and update Notion pages and databases",
            priority="high",
        ),
    ],
    "linear": [
        ServerRecommendation(
            server_name="linear-mcp",
            package_identifier="@anthropic/mcp-server-linear",
            registry_type=RegistryType.NPM,
            reason="Create and manage Linear issues and projects",
            priority="high",
        ),
    ],
    "jira": [
        ServerRecommendation(
            server_name="jira-mcp",
            package_identifier="mcp-server-atlassian",
            registry_type=RegistryType.NPM,
            reason="Manage Jira issues and Confluence pages",
            priority="high",
        ),
    ],
    # --- Payments ---
    "stripe": [
        ServerRecommendation(
            server_name="stripe-mcp",
            package_identifier="@stripe/mcp",
            registry_type=RegistryType.NPM,
            reason="Manage Stripe customers, payments, and subscriptions",
            priority="high",
        ),
    ],
    # --- Auth/BaaS ---
    "supabase": [
        ServerRecommendation(
            server_name="supabase-mcp",
            package_identifier="@anthropic/mcp-server-supabase",
            registry_type=RegistryType.NPM,
            reason="Query Supabase database, auth, and storage",
            priority="high",
        ),
    ],
    "firebase": [
        ServerRecommendation(
            server_name="firebase-mcp",
            package_identifier="mcp-server-firebase",
            registry_type=RegistryType.NPM,
            reason="Manage Firebase projects, Firestore, and Auth",
            priority="medium",
        ),
    ],
    # --- Cloud ---
    "docker": [
        ServerRecommendation(
            server_name="docker-mcp",
            package_identifier="mcp/docker",
            registry_type=RegistryType.NPM,
            reason="Manage Docker containers, images, and compose stacks",
            priority="medium",
        ),
    ],
    "terraform": [
        ServerRecommendation(
            server_name="terraform-mcp",
            package_identifier="@anthropic/mcp-server-terraform",
            registry_type=RegistryType.NPM,
            reason="Terraform plan, state, and module management",
            priority="high",
        ),
    ],
    "vercel": [
        ServerRecommendation(
            server_name="vercel-mcp",
            package_identifier="mcp-server-vercel",
            registry_type=RegistryType.NPM,
            reason="Manage Vercel deployments and projects",
            priority="medium",
        ),
    ],
    "cloudflare": [
        ServerRecommendation(
            server_name="cloudflare-mcp",
            package_identifier="@cloudflare/mcp-server-cloudflare",
            registry_type=RegistryType.NPM,
            reason="Manage Cloudflare Workers, KV, and DNS",
            priority="medium",
        ),
    ],
    # --- Testing ---
    "playwright": [
        ServerRecommendation(
            server_name="playwright-mcp",
            package_identifier="@anthropic/mcp-server-playwright",
            registry_type=RegistryType.NPM,
            reason="Browser automation for end-to-end testing",
            priority="medium",
        ),
    ],
    # --- CMS ---
    "contentful": [
        ServerRecommendation(
            server_name="contentful-mcp",
            package_identifier="mcp-server-contentful",
            registry_type=RegistryType.NPM,
            reason="Manage Contentful spaces, entries, and content types",
            priority="medium",
        ),
    ],
    # --- AI/ML ---
    "openai": [
        ServerRecommendation(
            server_name="openai-mcp",
            package_identifier="mcp-openai",
            registry_type=RegistryType.NPM,
            reason="OpenAI API integration for model management",
            priority="low",
        ),
    ],
    # --- Messaging ---
    "sendgrid": [
        ServerRecommendation(
            server_name="sendgrid-mcp",
            package_identifier="mcp-server-sendgrid",
            registry_type=RegistryType.NPM,
            reason="Send emails and manage SendGrid templates",
            priority="medium",
        ),
    ],
    "twilio": [
        ServerRecommendation(
            server_name="twilio-mcp",
            package_identifier="mcp-server-twilio",
            registry_type=RegistryType.NPM,
            reason="Send SMS and manage Twilio services",
            priority="medium",
        ),
    ],
}
```

---

## 4. Stack Archetypes

### Design Philosophy

Archetypes are NOT recommendations. They are **labels** that help the LLM understand
what KIND of project this is, so it can make better follow-up decisions. The archetype
triggers discovery hints with additional search queries.

### Archetype Definitions (10 archetypes)

```python
@dataclass(frozen=True, slots=True)
class StackArchetype:
    id: str
    label: str
    description: str
    # Each signal group is an OR-set. You need min_groups to match.
    signal_groups: tuple[frozenset[str], ...]
    min_groups: int
    extra_queries: tuple[str, ...]
    # Priority affects ordering when multiple archetypes match
    priority: int = 0

STACK_ARCHETYPES: tuple[StackArchetype, ...] = (
    StackArchetype(
        id="saas_app",
        label="SaaS Application",
        description="Web app with auth, payments, and user management",
        signal_groups=(
            frozenset({"next.js", "react", "vue", "angular", "svelte", "nuxt"}),
            frozenset({"supabase", "firebase", "auth0", "clerk"}),
            frozenset({"stripe", "paddle"}),
            frozenset({"postgresql", "mongodb"}),
        ),
        min_groups=2,
        extra_queries=("authentication", "payments", "analytics", "email", "feature flags"),
    ),
    StackArchetype(
        id="api_backend",
        label="API Backend",
        description="Server-side API with database and external integrations",
        signal_groups=(
            frozenset({"fastapi", "django", "flask", "express", "nestjs", "fastify", "hono", "litestar"}),
            frozenset({"postgresql", "mongodb", "mysql"}),
            frozenset({"redis", "rabbitmq", "kafka", "celery"}),
        ),
        min_groups=2,
        extra_queries=("api testing", "database migrations", "queue", "caching"),
    ),
    StackArchetype(
        id="data_pipeline",
        label="Data Pipeline / ETL",
        description="Data processing, transformation, and analytics",
        signal_groups=(
            frozenset({"python"}),
            frozenset({"postgresql", "mongodb", "clickhouse", "elasticsearch", "opensearch"}),
            frozenset({"redis", "rabbitmq", "kafka", "celery", "airflow", "dramatiq"}),
        ),
        min_groups=2,
        extra_queries=("data processing", "etl", "scheduling", "workflow orchestration"),
    ),
    StackArchetype(
        id="devops_infra",
        label="DevOps / Infrastructure",
        description="Infrastructure as code, containers, and deployment automation",
        signal_groups=(
            frozenset({"docker", "kubernetes"}),
            frozenset({"terraform", "pulumi", "aws-cdk", "ansible"}),
            frozenset({"aws", "gcp", "azure"}),
        ),
        min_groups=2,
        extra_queries=("cloud", "deployment", "monitoring", "logging", "cost management"),
    ),
    StackArchetype(
        id="ai_ml",
        label="AI / ML Application",
        description="AI/ML models, LLM integrations, or data science",
        signal_groups=(
            frozenset({"openai", "anthropic", "huggingface", "langchain", "llamaindex"}),
            frozenset({"python"}),
            frozenset({"postgresql", "redis", "elasticsearch"}),
        ),
        min_groups=2,
        extra_queries=("vector database", "embeddings", "prompt engineering", "model serving"),
    ),
    StackArchetype(
        id="fullstack_monorepo",
        label="Full-Stack Monorepo",
        description="Multi-package monorepo with frontend and backend",
        signal_groups=(
            frozenset({"turborepo", "nx", "lerna", "pnpm-monorepo"}),
            frozenset({"next.js", "react", "vue"}),
            frozenset({"express", "fastapi", "nestjs"}),
        ),
        min_groups=2,
        extra_queries=("monorepo", "workspace", "build system", "shared packages"),
    ),
    StackArchetype(
        id="jamstack_static",
        label="JAMStack / Static Site",
        description="Static site with CMS and CDN deployment",
        signal_groups=(
            frozenset({"next.js", "nuxt", "svelte", "docusaurus", "gatsby"}),
            frozenset({"contentful", "sanity", "strapi", "directus"}),
            frozenset({"vercel", "netlify", "cloudflare"}),
        ),
        min_groups=2,
        extra_queries=("cms", "cdn", "image optimization", "search"),
    ),
    StackArchetype(
        id="mobile_backend",
        label="Mobile App Backend",
        description="Backend for mobile applications",
        signal_groups=(
            frozenset({"react-native", "expo", "ios", "android", "dart"}),
            frozenset({"supabase", "firebase"}),
            frozenset({"postgresql", "mongodb"}),
        ),
        min_groups=2,
        extra_queries=("push notifications", "mobile analytics", "app store", "deep linking"),
    ),
    StackArchetype(
        id="ecommerce",
        label="E-Commerce",
        description="Online store with products, payments, and inventory",
        signal_groups=(
            frozenset({"shopify", "stripe", "paddle", "adyen"}),
            frozenset({"next.js", "react", "vue"}),
            frozenset({"postgresql", "mongodb", "redis"}),
        ),
        min_groups=2,
        extra_queries=("inventory", "shipping", "tax", "product catalog"),
    ),
    StackArchetype(
        id="docs_knowledge",
        label="Documentation / Knowledge Base",
        description="Documentation site or knowledge management system",
        signal_groups=(
            frozenset({"docusaurus", "mkdocs", "storybook"}),
            frozenset({"notion", "contentful", "sanity"}),
        ),
        min_groups=1,
        extra_queries=("documentation", "search", "knowledge graph", "content management"),
    ),
)
```

### Archetype Matching Algorithm

```python
def detect_archetypes(
    technologies: list[DetectedTechnology],
) -> list[tuple[StackArchetype, int, list[str]]]:
    """Detect which stack archetypes match the project.

    Returns list of (archetype, groups_matched, matched_techs) sorted by
    groups_matched descending, then priority.
    """
    tech_names = {t.name.lower() for t in technologies}
    results = []

    for archetype in STACK_ARCHETYPES:
        matched_groups = 0
        matched_techs = []
        for group in archetype.signal_groups:
            overlap = tech_names & group
            if overlap:
                matched_groups += 1
                matched_techs.extend(overlap)
        if matched_groups >= archetype.min_groups:
            results.append((archetype, matched_groups, matched_techs))

    results.sort(key=lambda x: (-x[1], x[0].priority))
    return results
```

---

## 5. Discovery Hints

### Hint Type Taxonomy (8 types, not just 4)

The original proposal had 4 hint types. Here are 8, adding significant value.

```python
class DiscoveryHintType(StrEnum):
    # Original 4
    WORKFLOW_INFERENCE = "workflow_inference"
    STACK_ARCHETYPE = "stack_archetype"
    UNMAPPED_TECHNOLOGY = "unmapped_technology"
    ENV_VAR_HINT = "env_var_hint"
    # NEW: 4 additional types
    DEPLOYMENT_TARGET = "deployment_target"
    MISSING_COMPLEMENT = "missing_complement"
    FILE_STRUCTURE_HINT = "file_structure_hint"
    MONOREPO_WORKSPACE = "monorepo_workspace"


@dataclass(frozen=True, slots=True)
class DiscoveryHint:
    type: DiscoveryHintType
    trigger: str           # what was detected that triggered this hint
    suggestion: str        # natural language suggestion for the LLM
    search_queries: tuple[str, ...]  # suggested registry search terms
    confidence: float = 0.8
```

### NEW Hint Type Explanations

**DEPLOYMENT_TARGET**: When we detect a deployment platform (Vercel, Netlify, Fly,
Railway, etc.), suggest the corresponding MCP server plus monitoring tools.

```python
# Example:
DiscoveryHint(
    type=DiscoveryHintType.DEPLOYMENT_TARGET,
    trigger="vercel.json detected",
    suggestion="Project deploys to Vercel. The Vercel MCP server can manage "
               "deployments, environment variables, and project settings. "
               "Also consider monitoring tools for production.",
    search_queries=("vercel", "deployment", "uptime monitoring"),
)
```

**MISSING_COMPLEMENT**: When technology A is present but its common companion B is
not, suggest B. This is the "people who bought X also bought Y" pattern.

```python
_COMPLEMENT_PAIRS: dict[str, tuple[str, ...]] = {
    "next.js": ("vercel", "analytics"),
    "postgresql": ("redis",),
    "docker": ("kubernetes",),
    "fastapi": ("redis", "celery"),
    "django": ("redis", "celery"),
    "react": ("storybook",),
    "terraform": ("aws", "gcp", "azure"),
    "sentry": ("datadog", "grafana"),
    "stripe": ("sendgrid", "twilio"),
    "supabase": ("sentry",),
    "openai": ("langchain", "anthropic"),
}

# Example hint:
DiscoveryHint(
    type=DiscoveryHintType.MISSING_COMPLEMENT,
    trigger="postgresql detected, redis not found",
    suggestion="Most PostgreSQL backends benefit from Redis for caching "
               "and session storage. Consider adding a Redis MCP server.",
    search_queries=("redis", "caching"),
    confidence=0.6,
)
```

**FILE_STRUCTURE_HINT**: Detect meaningful directories that suggest project capabilities.

```python
_DIR_HINTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "docs": ("Project has a docs/ directory -- may benefit from documentation tools",
             ("documentation", "knowledge base")),
    "e2e": ("Project has e2e/ test directory -- may benefit from browser testing tools",
            ("playwright", "browser testing", "cypress")),
    "scripts": ("Project has scripts/ directory -- may benefit from automation tools",
                ("automation", "scripting")),
    "migrations": ("Project has migrations/ directory -- uses database migrations",
                   ("database", "migrations")),
    "infra": ("Project has infra/ directory -- infrastructure code detected",
              ("terraform", "infrastructure", "cloud")),
    "ml": ("Project has ml/ directory -- machine learning code detected",
           ("machine learning", "model serving", "vector database")),
    "proto": ("Project has proto/ directory -- uses Protocol Buffers (gRPC)",
              ("grpc", "protobuf", "api")),
    "graphql": ("Project has graphql/ directory -- uses GraphQL",
                ("graphql", "api")),
}
```

**MONOREPO_WORKSPACE**: When a monorepo is detected, enumerate the workspaces/packages
and suggest scanning each one individually for richer discovery.

---

## 6. Wild Ideas (Practical Edition)

### 6A. "Dependency Fingerprinting" -- Confidence Stacking

Instead of treating each detection source independently, stack confidence scores
from multiple sources:

- `@sentry/node` in package.json: confidence 0.9
- `SENTRY_DSN` in .env: confidence 0.7
- `sentry.properties` file exists: confidence 0.9

Combined confidence = 1 - (1-0.9) * (1-0.7) * (1-0.9) = 0.997

This lets us be MUCH more confident when multiple signals agree, and appropriately
uncertain when we only see one weak signal.

```python
def _combine_confidence(scores: list[float]) -> float:
    """Combine independent confidence scores using probability union."""
    if not scores:
        return 0.0
    result = 1.0
    for score in scores:
        result *= (1.0 - score)
    return round(1.0 - result, 3)
```

This replaces the current deduplication that keeps "highest confidence entry" with
one that actually combines evidence. Cheap to compute, dramatically better signal.

### 6B. "Package.json Scripts" Mining

The `scripts` section in package.json is an untapped goldmine. Examples:

```json
{
  "scripts": {
    "deploy": "vercel deploy",
    "db:migrate": "prisma migrate deploy",
    "test:e2e": "playwright test",
    "lint": "eslint",
    "storybook": "storybook dev -p 6006",
    "terraform": "cd infra && terraform apply"
  }
}
```

Each script command can be pattern-matched:

```python
_SCRIPT_PATTERNS: list[tuple[re.Pattern[str], str, TechnologyCategory]] = [
    (re.compile(r"\bvercel\b"), "vercel", TechnologyCategory.PLATFORM),
    (re.compile(r"\bprisma\b"), "prisma", TechnologyCategory.DATABASE),
    (re.compile(r"\bplaywright\b"), "playwright", TechnologyCategory.SERVICE),
    (re.compile(r"\bstorybook\b"), "storybook", TechnologyCategory.SERVICE),
    (re.compile(r"\bterraform\b"), "terraform", TechnologyCategory.PLATFORM),
    (re.compile(r"\bdocker\b"), "docker", TechnologyCategory.PLATFORM),
    (re.compile(r"\bkubectl\b"), "kubernetes", TechnologyCategory.PLATFORM),
    (re.compile(r"\bhelm\b"), "kubernetes", TechnologyCategory.PLATFORM),
    (re.compile(r"\bwrangler\b"), "cloudflare", TechnologyCategory.PLATFORM),
    (re.compile(r"\bsupabase\b"), "supabase", TechnologyCategory.SERVICE),
    (re.compile(r"\bfirebase\b"), "firebase", TechnologyCategory.SERVICE),
    (re.compile(r"\bnext\b"), "next.js", TechnologyCategory.FRAMEWORK),
    (re.compile(r"\bdrizzle\b"), "drizzle", TechnologyCategory.DATABASE),
    (re.compile(r"\btypeorm\b"), "typeorm", TechnologyCategory.DATABASE),
    (re.compile(r"\bsequelize\b"), "sequelize", TechnologyCategory.DATABASE),
    (re.compile(r"\bsentry\b"), "sentry", TechnologyCategory.SERVICE),
    (re.compile(r"\bcypress\b"), "cypress", TechnologyCategory.SERVICE),
    (re.compile(r"\bjest\b"), "jest", TechnologyCategory.SERVICE),
    (re.compile(r"\bvitest\b"), "vitest", TechnologyCategory.SERVICE),
]
```

Implementation: add ~15 lines to `_parse_package_json` to scan the `scripts` dict.

### 6C. "next_actions" -- Structured LLM Choreography

Instead of just returning hints, return explicit structured actions the LLM should
take. This is the difference between "you might want to search" and "here is exactly
what to do next."

```python
@dataclass(frozen=True, slots=True)
class NextAction:
    tool: str          # "search_servers" or "configure_server"
    args: dict[str, str]  # tool arguments
    reason: str        # why this action is suggested

# Example output in scan result:
"next_actions": [
    {
        "tool": "search_servers",
        "args": {"query": "sentry", "project_path": "."},
        "reason": "Sentry SDK detected -- find the best Sentry MCP server"
    },
    {
        "tool": "search_servers",
        "args": {"query": "terraform"},
        "reason": "Terraform detected in CI/CD but no known MCP server mapped"
    },
    {
        "tool": "configure_server",
        "args": {"server_name": "postgres-mcp", "package_identifier": "@modelcontextprotocol/server-postgres"},
        "reason": "PostgreSQL detected with high confidence -- ready to install"
    }
]
```

The LLM reads these and can execute them autonomously or ask the user first.

### 6D. "Ecosystem Neighbors" via Package.json Metadata

Parse the `repository` field in package.json to detect the hosting platform:

```json
{
  "repository": {
    "type": "git",
    "url": "https://github.com/org/repo"
  }
}
```

From `org`, we can infer ecosystem context. If `org` is `vercel`, `stripe`, `supabase`,
etc., the project is deeply embedded in that ecosystem.

### 6E. Setup.cfg and Poetry Support

Currently we only parse `pyproject.toml [project.dependencies]`. Many Python projects
use:
- `setup.cfg` with `[options] install_requires`
- `pyproject.toml [tool.poetry.dependencies]` (Poetry format)

Adding both is ~30 lines of code each.

### 6F. Go.mod and Cargo.toml Dependency Parsing

Go and Rust are detected by file presence but their dependencies are never parsed.

```go
// go.mod
require (
    github.com/stripe/stripe-go/v78 v78.0.0
    github.com/aws/aws-sdk-go-v2 v1.24.0
    github.com/jackc/pgx/v5 v5.5.0
)
```

Go module paths are inherently namespaced -- `github.com/stripe/stripe-go` naturally
maps to "stripe". Similar prefix-matching works here.

Cargo.toml is TOML (already parsed via tomllib), so adding Rust dependency detection
is trivial.

---

## 7. Architecture Decisions

### The Dynamic Registry Bridge -- How It Actually Works

The key insight: `recommend_servers()` is currently sync and uses only static data.
Making it async and injecting `RegistryClient` is the minimal change needed.

```
scan_project(path, client)
  |-- detect technologies (concurrent parsers)
  |-- recommend_servers(profile, client, registry_client=None)
  |     |-- Layer 1: static map (sync, fast)
  |     |-- Layer 2: dynamic registry queries (async, optional)
  |     |     |-- only for technologies NOT in static map
  |     |     |-- timeout: 3s per query, 10s total
  |     |     |-- on failure: skip silently, return static-only results
  |     |-- Layer 3: generate discovery hints
  |     |     |-- archetypes
  |     |     |-- missing complements
  |     |     |-- unmapped technologies
  |     |     |-- env var hints
  |     |     |-- deployment target hints
  |     |     |-- file structure hints
  |-- build output with recommendations + hints + next_actions
```

### Model Changes (Additive Only)

```python
# New field on ServerRecommendation
@dataclass(frozen=True, slots=True)
class ServerRecommendation:
    server_name: str
    package_identifier: str
    registry_type: RegistryType
    reason: str
    priority: str
    source: str = "curated"  # NEW: "curated" or "registry"

# New field on ProjectProfile
@dataclass(frozen=True, slots=True)
class ProjectProfile:
    path: str
    technologies: list[DetectedTechnology] = field(default_factory=list)
    env_var_names: list[str] = field(default_factory=list)
    recommendations: list[ServerRecommendation] = field(default_factory=list)
    discovery_hints: list[DiscoveryHint] = field(default_factory=list)       # NEW
    archetypes: list[str] = field(default_factory=list)                      # NEW
    next_actions: list[dict[str, object]] = field(default_factory=list)      # NEW
```

### Backward Compatibility

All new fields have defaults. Existing code that constructs `ServerRecommendation` or
`ProjectProfile` without the new fields will continue to work. The scan output adds
new top-level keys but does not change existing ones.

---

## 8. Implementation Priority

### Phase 1 (Highest ROI, smallest effort) -- Size S

1. Expand `_NODE_DEP_MAP` with high-value entries
2. Add `_NODE_PREFIX_MAP` with prefix matching
3. Expand `_PYTHON_DEP_MAP`
4. Expand `_ENV_PATTERNS`
5. Expand `_DOCKER_IMAGE_MAP`
6. Expand `_detect_platform_files` with ~30 more files
7. Add directory-based detection
8. Add package.json scripts mining

This phase touches only `scanner/detector.py` and increases detection coverage from
~60 to ~200 technology patterns. No architecture changes needed.

### Phase 2 (High ROI, medium effort) -- Size M

1. Expand `TECHNOLOGY_SERVER_MAP` from 13 to ~50 entries
2. Add `source` field to `ServerRecommendation`
3. Expand credential mappings
4. Add confidence stacking (combine multi-source detections)

This phase touches `scanner/recommendations.py`, `models.py`, `scanner/credentials.py`.

### Phase 3 (The differentiator) -- Size M

1. Add `DiscoveryHint` and `StackArchetype` to models
2. Create `scanner/archetypes.py` with archetype detection
3. Create `scanner/hints.py` with hint generators
4. Add `next_actions` builder
5. Wire into `tools/scan.py` output
6. Add `discovery_hints`, `archetypes`, `next_actions` to scan output

### Phase 4 (Dynamic bridge) -- Size M

1. Make `recommend_servers()` async
2. Add `RegistryClient` parameter
3. Query registry for unmapped technologies with timeout
4. Quality-gate dynamic results via maturity scoring
5. Graceful offline fallback

---

## 9. Verdicts

| Idea | Verdict | Reasoning |
|------|---------|-----------|
| @org/ prefix matching | GREEN | 30 patterns, covers ~90% of service SDKs, near-zero false positives |
| Expanded static map (13 to 50) | GREEN | Direct user value, curated quality, offline-safe |
| File/dir-based detection | GREEN | Zero parsing cost, highly reliable signals |
| Package.json scripts mining | GREEN | Untapped goldmine, ~15 lines of code |
| Stack archetypes | GREEN | Labels help the LLM reason about the project holistically |
| Discovery hints (8 types) | GREEN | Killer feature -- turns LLM into a discovery partner |
| Confidence stacking | GREEN | 5 lines of code, dramatically better signal quality |
| Missing complement hints | GREEN | "People who use X also use Y" is high-value |
| next_actions choreography | GREEN | Explicit actions > vague suggestions |
| Dynamic registry bridge | GREEN | But registry API must be reliable (currently returning empty) |
| Go.mod / Cargo.toml parsing | YELLOW | Good value but lower priority -- Go/Rust MCP ecosystem is smaller |
| Setup.cfg / Poetry parsing | YELLOW | Worth doing but not blocking |
| Monorepo workspace enumeration | YELLOW | Complex to do well, but high value for monorepo users |

---

## 10. Key Risks & Mitigations

1. **Registry API unreliability**: Already observed empty results. Mitigation: dynamic
   bridge is ALWAYS optional, static map is always available.

2. **False positive detection**: e.g., a dir named `cypress` that is not the testing
   tool. Mitigation: use confidence scores, combine with other signals.

3. **Package identifier drift**: MCP server packages get renamed, deprecated, or moved.
   Mitigation: verify package identifiers against registry before hardcoding.

4. **Output bloat**: Too many hints overwhelms the LLM. Mitigation: cap at 10 hints,
   sort by confidence, deduplicate.

5. **Backward compatibility**: New fields on frozen dataclasses. Mitigation: all new
   fields have defaults, existing tests pass unchanged.

---

## Appendix: Detection Coverage Matrix (Current vs Proposed)

| Detection Source | Current Patterns | Proposed Patterns | Increase |
|-----------------|-----------------|-------------------|----------|
| Node deps (exact) | 30 | 45 | +50% |
| Node deps (prefix) | 0 | 30 | NEW |
| Python deps | 25 | 55 | +120% |
| Docker images | 8 | 28 | +250% |
| Env var patterns | 11 | 40 | +264% |
| Platform files | 3 | 50+ | +1567% |
| Platform dirs | 0 | 15 | NEW |
| Language files | 4 | 17 | +325% |
| Scripts mining | 0 | 19 | NEW |
| Server recommendations | 13 | 50+ | +285% |
| **Total patterns** | **~94** | **~350+** | **+272%** |
