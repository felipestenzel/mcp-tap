# Test Architect Memory -- mcp-tap

## Testing Setup
- pytest + pytest-asyncio (asyncio_mode="auto")
- Test dir: `tests/`
- Run: `pytest tests/`
- Linter: `ruff check src/ tests/`
- Current: 1160 tests passing (config, registry, models, scanner, scoring, tools, healing, subprocess, server, evaluation, lockfile, differ, verify, conflicts, restore, workflow, stacks, smithery_client, registry_aggregator, smithery_installer)
- Mock all external I/O (httpx, subprocess, filesystem)
- Target: >80% coverage on new code

## Project Conventions
- `from __future__ import annotations` in ALL files
- All dataclasses frozen=True, slots=True
- Ruff rules: E, F, W, I, UP, B, SIM, RUF (import sorting enforced via I001)
- Unused unpacked vars must use `_` prefix (RUF059)
- RUF012: Mutable class attributes need ClassVar annotation. Use tuples for module-level parametrize data.
- Line length: 100 chars
- Python target: 3.11+
- IMPORTANT: VS Code linter auto-removes unused imports between Edit calls. When adding imports + new code, use Write to replace the entire file atomically -- do NOT do two separate edits (import then code)
- After writing new files, ALWAYS run `ruff check --fix <file>` to fix import sorting (I001)

## Test Patterns Established
- Test classes grouped by component (e.g., TestClassifier, TestFixer, TestRetryLoop)
- Fixtures stored in `tests/fixtures/` as realistic project directories
- `tmp_path` fixture used for tests needing writable temp directories
- Async test methods work directly (no decorator needed; asyncio_mode="auto")
- Private functions tested directly via import (e.g., `_parse_package_json`, `_cache_get`)
- MCP Context mocked with: `ctx = MagicMock(); ctx.info = AsyncMock(); ctx.error = AsyncMock()`
- For search tool context: also set `ctx.request_context.lifespan_context.registry`
- Tool functions return `dict[str, object]` (serialized via `dataclasses.asdict`)
- Patch targets at the module where imported, not where defined
- For subprocess tests: mock `asyncio.create_subprocess_exec` at `mcp_tap.installer.subprocess` level

## Resilience Fix Tests (2026-02-19)
- **C3 (Orphan Process)**: `test_subprocess.py` -- 13 tests covering start_new_session, killpg+SIGKILL, ProcessLookupError/OSError fallback to proc.kill(), timeout messaging
- **C4 (Health Semaphore)**: `test_tools_health.py::TestHealthSemaphoreConcurrency` -- 4 tests covering _MAX_CONCURRENT_CHECKS=5, concurrency tracking with asyncio.Lock, failures under semaphore
- **C1 (File Locking)**: `test_config.py::TestWriteServerConfigLocking` -- 5 tests covering .lock file creation, unique temp files via mkstemp, concurrent thread writes (10 threads), mixed write+remove concurrency
- **C2 (GitHub Cache)**: `test_evaluation.py` -- 14 new tests across TestGitHubCacheGet, TestGitHubCacheClear, TestGitHubRateLimit, TestGitHubHeaders, TestFetchRepoMetadataCache
- **H1 (HTTP Retries)**: `test_server.py` -- 5 tests covering retries=3 transport, timeout config, follow_redirects, RegistryClient creation, client cleanup

## Healing Module Tests (tests/test_healing.py)
- 85 tests: classifier (42), fixer (14), retry loop (14), model validation (15)
- Classifier: parametrized across all ErrorCategory values + edge cases
- Fixer: mock `mcp_tap.healing.fixer.shutil.which` for COMMAND_NOT_FOUND
- Retry: mock classify_error, generate_fix, test_server_connection at healing.retry level
- Models: HealingAttempt(diagnosis, fix_applied, success), HealingResult(fixed, attempts, fixed_config, user_action_needed)
- Timeout escalation: [15, 30, 60] for TIMEOUT category
- User-action-required: AUTH, MISSING_ENV, CONN_REFUSED, PERMISSION, UNKNOWN stop immediately

## Parallel Agent Gotcha (Critical)
- When working in parallel with implementation agents, models.py can change mid-session
- Python import cache may differ from file-on-disk content
- Always verify runtime fields: `python -c "from mcp_tap.models import X; print(list(X.__dataclass_fields__.keys()))"`
- Write tests atomically using Write tool to avoid partial state from concurrent modifications
- Read source files immediately before writing tests, not at session start

## Fixture Projects Available
- `tests/fixtures/python_fastapi_project/` -- pyproject.toml, docker-compose.yml, .env.example
- `tests/fixtures/node_express_project/` -- package.json, docker-compose.yml, .env
- `tests/fixtures/minimal_project/` -- requirements.txt, Makefile
- `tests/fixtures/empty_project/` -- empty directory

## Known Edge Cases
- Classifier env var detection requires uppercase [A-Z][A-Z0-9_]{2,} token in error message
- `_normalize_python_dep()` does NOT strip leading whitespace before regex split
- Docker image matching uses substring search (`fragment in image_name`)
- Env-pattern-detected techs get confidence=0.7 (lower than file-based detection)
- `recommend_servers()` always adds filesystem-mcp recommendation
- Health check timeout clamped to 5-60 seconds
- `_scan_project_safe` returns None on any exception
- GitHub cache TTL is 900s (15min); test by patching `time.monotonic`
- Rate limit uses `time.monotonic()` comparison; reset via `clear_cache()`
- httpx.Response can be constructed with just status_code + headers for rate limit tests

## Tools Module Structure
- `src/mcp_tap/tools/scan.py` -- scan_project tool
- `src/mcp_tap/tools/configure.py` -- configure_server tool
- `src/mcp_tap/tools/health.py` -- check_health tool (with _MAX_CONCURRENT_CHECKS=5 semaphore)
- `src/mcp_tap/tools/search.py` -- search_servers tool
- `src/mcp_tap/healing/` -- classifier.py, fixer.py, retry.py (self-healing module)
- `src/mcp_tap/scanner/scoring.py` -- score_result + relevance_sort_key
- `src/mcp_tap/errors.py` -- McpTapError hierarchy
- `src/mcp_tap/installer/subprocess.py` -- run_command with start_new_session + killpg
- `src/mcp_tap/config/writer.py` -- atomic writes with threading.Lock + fcntl.flock
- `src/mcp_tap/evaluation/github.py` -- cache + rate limit + GITHUB_TOKEN

## Lockfile Differ + Verify Tests (2026-02-19)
- **test_differ.py** -- 44 tests: empty inputs (3), MISSING drift (2), EXTRA drift (2), no-drift matching (3), CONFIG_CHANGED (6), TOOLS_CHANGED (4), tools check skip conditions (6), combined drift (3), _check_config_drift helper (5), _check_tools_drift helper (7), DriftEntry model (3)
- **test_verify.py** -- 25 tests: no lockfile (3), no client detected (2), explicit client (2), clean state (4), with drift (3), data flow verification (4), error handling (6), lockfile name constant (1)
- differ.py is pure function -- no mocks needed, construct domain objects directly
- verify.py patch targets: `mcp_tap.tools.verify.{read_lockfile,detect_clients,resolve_config_path,read_config,parse_servers,diff_lockfile}`
- VerifyResult serialized via `dataclasses.asdict` -- drift entries become plain dicts with StrEnum values as strings
- Verify tool catches McpTapError (returns error dict) vs unexpected Exception (logs to ctx.error + returns "Internal error")

## Restore Tool Tests (2026-02-19)
- **test_restore.py** -- 50 tests across 12 test classes
- Classes: TestNoLockfile (4), TestEmptyLockfile (3), TestNoClientDetected (2), TestDryRun (6), TestSuccessfulRestore (6), TestEnvKeysReporting (3), TestInstallFailure (2), TestMultipleServers (2), TestValidationFailure (2), TestInstallerNotFound (1), TestMcpTapErrorOuter (2), TestUnexpectedException (3), TestRestoreServerHelper (5), TestBuildDryRunResult (4), TestDataFlow (4), TestLockfileName (1)
- Patch targets: `mcp_tap.tools.restore.{read_lockfile,resolve_config_locations,resolve_installer,write_server_config,test_server_connection}`
- restore.py returns raw dicts (not dataclass), so assert dict keys directly
- `_restore_server` has its own McpTapError + Exception catch -- test both paths
- `_build_dry_run_result` is pure function -- test directly without mocks
- Installer mock pattern: `MagicMock(install=AsyncMock(return_value=InstallResult(...)))`
- Key behavior: overall success=True if at least one server restored; env_vars_needed only appears when env_keys non-empty

## Mock Patterns for Tools
- Installer: `MagicMock()` with `install=AsyncMock(return_value=InstallResult(...))`
- Connection tester: `AsyncMock(return_value=ConnectionTestResult(...))`
- Config detection: `patch("mcp_tap.tools.X.detect_clients", ...)`
- For healing retry: patch `mcp_tap.healing.retry.test_server_connection`
- For healing fixer: patch `mcp_tap.healing.fixer.shutil.which`
- For healing classifier: just construct ConnectionTestResult directly (pure function)
- For subprocess: patch `mcp_tap.installer.subprocess.asyncio.create_subprocess_exec`, `os.killpg`, `os.getpgid`
- For GitHub headers: `patch.dict("os.environ", {"GITHUB_TOKEN": "..."})`
- For GitHub cache TTL: `patch("mcp_tap.evaluation.github.time.monotonic", return_value=...)`
- For httpx transport verification: access `client._transport._pool._retries` (httpx internal)
- For httpx pool limits: When `transport=` is passed explicitly to AsyncClient, the `limits=` param does NOT apply to pool -- must verify via patching AsyncClient.__init__ and inspecting captured kwargs
- For healing retry: `heal_and_retry` default `max_attempts=2` (reduced from 3 in H2 fix)
- For configure transactional: `_try_heal` accepts `original_error` param; `_configure_single` writes config ONLY after validation passes
- For connection tester: `_run_connection_test` is a separate coroutine for asyncio.wait_for; timeout msg contains "process cleanup was attempted"
- For async config reader: `aread_config` uses `asyncio.to_thread(read_config, ...)`
- For env var parsing: `_parse_env_vars` uses regex `r",(?=\s*[A-Za-z_][A-Za-z0-9_]*\s*=)"` -- commas followed by non-KEY= text are preserved in value

## Production Hardening R2 Tests (2026-02-19)
- **H2 (Healing loop)**: `test_healing.py::TestHealAndRetryDefaultMaxAttempts` (3 tests) + `TestTryHealForwardsOriginalError` (1 test) -- default max_attempts=2, signature inspection, no redundant test_server_connection
- **H3 (Transactional config)**: `test_tools_configure.py::TestConfigureTransactionalWrite` (3 tests) -- config written after validation, NOT written on failure, multi-client NOT written on failure
- **H2 in configure**: `test_tools_configure.py::TestConfigureNoRedundantValidation` (1 test) -- test_server_connection called once, not again after healing
- **H4 (Connection cleanup)**: `test_connection.py::TestConnectionTesterCleanup` (3 tests) -- _run_connection_test exists, timeout mentions "process cleanup", timeout includes seconds value
- **M1 (Pool limits)**: `test_server.py::TestAppLifespan::test_creates_http_client_with_pool_limits` (1 test) -- verifies httpx.Limits(max_connections=10) via constructor patching
- **M2 (Async reader)**: `test_config.py::TestAsyncReadConfig` (2 tests) -- aread_config matches sync, returns empty for nonexistent
- **M3 (Env commas)**: `test_tools_configure.py::TestParseEnvVars` (3 new tests) -- commas in values preserved when not followed by KEY=

## Workflow CI/CD Parser Tests (tests/test_workflow.py)
- 107 tests across 15 test classes covering scanner/workflow.py
- **TestMatchCiImage** (13): all _CI_IMAGE_MAP entries, bitnami prefix, unknown, confidence=0.85, source propagation, python not matched
- **TestMatchGhaAction** (10): parametrized 7 actions (aws/gcp/azure/docker/terraform/helm), unknown, confidence=0.8, category=PLATFORM
- **TestMatchRunCommand** (17): parametrized 11 CLI patterns (terraform/kubectl/helm/ansible/aws/gcloud/az/docker), unknown, confidence=0.7, multiline, word-boundary edge cases
- **TestParseGithubWorkflows** (17): services/actions/run detection, multiple workflows, non-YAML ignored, malformed YAML, empty/missing jobs, non-dict guards, source_file relative path
- **TestParseGitlabCi** (17): string+dict services, top-level+job-level images, scripts/before/after, keywords skipped, hidden jobs, dict image, mixed formats
- **TestExtractGha***: 8 tests for GHA extractor helpers (services, actions, run commands)
- **TestExtractGitlab***: 12 tests for GitLab extractor helpers (services, image, scripts)
- **TestParseCiConfigs** (6): both/neither/only-one present, exception resilience, return type
- **TestCiConfigsInFullScan** (3): integration with scan_project, deduplication across CI + docker-compose
- **TestConfidenceLevels** (5): verifies 0.85/0.8/0.7 per detection source for both GHA and GitLab
- Pattern: no mocking needed -- uses tmp_path with real YAML files written inline
- CI images matched by substring; python not in _CI_IMAGE_MAP so not matched
- _GITLAB_KEYWORDS frozenset prevents stages/variables/cache/etc. from being treated as jobs
- Hidden jobs (starting with ".") are skipped in GitLab CI

## Smithery + Aggregator + SmitheryInstaller Tests (2026-02-21)
- **test_smithery_client.py** -- 19 tests across 3 classes (Search 9, GetServer 3, Parsing 7)
  - SmitheryClient uses `httpx.AsyncClient` as `http` attr -- mock with `AsyncMock(spec=httpx.AsyncClient)`
  - 429 retry: `_MAX_429_RETRIES=1` means 2 total attempts; patch `mcp_tap.registry.smithery.asyncio.sleep`
  - get_server 404: the _get method raises RegistryError with "404" in msg; get_server catches and returns None
  - URL encoding: `urlquote(name, safe="")` encodes slash as %2F
  - Parsing: _parse_server is tolerant of missing fields; verified -> is_official, homepage -> repository_url
  - pageSize clamped to min(max(limit, 1), 100)
- **test_registry_aggregator.py** -- 18 tests across 4 classes (Search 5, Dedup 6, GetServer 3, ExtractGithubKey 7)
  - AggregatedRegistry takes two RegistryClientPort mocks (official, smithery)
  - Uses `asyncio.gather(..., return_exceptions=True)` -- failures become exceptions in results list
  - Dedup by GitHub URL: `_extract_github_key` regex, always lowercase
  - Merge: official base + smithery signals (use_count, verified, smithery_id), source="both"
  - Sort: both(0) < official(1) < smithery(2) via _sort_key
  - get_server: tries official first, falls back to smithery if None
- **test_smithery_installer.py** -- 15 tests across 4 classes (Availability 2, Install 6, BuildCommand 2, Uninstall 2)
  - Frozen dataclass (frozen=True, slots=True)
  - Patch `mcp_tap.installer.smithery.shutil.which` for availability
  - Patch `mcp_tap.installer.smithery.run_command` for install
  - Install uses `npx -y @smithery/cli@latest install <id> --client claude --config {}`
  - Uninstall is a no-op returning success=True (Smithery CLI has no uninstall)
  - build_server_command: `("npx", ["-y", "@smithery/cli@latest", "run", identifier])`
