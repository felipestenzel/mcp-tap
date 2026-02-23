# Credential Detection and Mapping

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-v02-roadmap`
- **Priority**: `high`
- **Issue**: #11

## Problem

When `configure_server` is called, the user must manually know which environment variables a server needs AND what values to pass. Even when the project already has the credentials in `.env` or `docker-compose.yml` under a slightly different name, mcp-tap doesn't detect or reuse them.

Today's behavior:
```
LLM: "What's your POSTGRES_CONNECTION_STRING?"
User: "I don't know... I think I have DATABASE_URL in my .env?"
LLM: "Let me check... ok pass env_vars='POSTGRES_CONNECTION_STRING=...'"
```

Target behavior:
```
scan_project result:
  env_vars_found: ["DATABASE_URL", "SLACK_BOT_TOKEN", "GITHUB_TOKEN"]
  credential_mapping:
    - server: postgres-mcp
      required: POSTGRES_CONNECTION_STRING
      available_as: DATABASE_URL (from .env)
      status: "available — will reuse DATABASE_URL"
    - server: slack-mcp
      required: SLACK_BOT_TOKEN
      available_as: SLACK_BOT_TOKEN (from .env)
      status: "available — exact match"
    - server: github-mcp
      required: GITHUB_TOKEN
      available_as: null
      status: "missing — create at https://github.com/settings/tokens"
```

This directly addresses the original issue's Phase 2 (Credential Intelligence) and its insight that the agent should "detect existing credentials, collect missing ones securely."

## Context

- **Module affected**: `scanner/detector.py` (already reads `.env` names), `scanner/recommendations.py` (already maps tech→server), `tools/scan.py`, `tools/configure.py`
- **Existing infrastructure**:
  - `detector.py:_parse_env_files()` already extracts env var NAMES from `.env`, `.env.example`, `.env.local`
  - `detector.py:_ENV_PATTERNS` already maps env var patterns → technologies (e.g., `POSTGRES*` → postgresql)
  - `SearchResult.env_vars_required` already lists required env vars per server from the Registry API
  - `ServerRecommendation` already has `server_name` and `package_identifier`
  - `configure_server` already accepts `env_vars` as comma-separated KEY=VALUE
- **What's missing**: The bridge between "project has DATABASE_URL" and "postgres-mcp needs POSTGRES_CONNECTION_STRING" — the **mapping logic**.

## Architecture

### New model: `CredentialMapping`

```python
@dataclass(frozen=True, slots=True)
class CredentialMapping:
    """Maps a server's required env var to an available project credential."""
    server_name: str
    required_env_var: str           # What the MCP server expects (e.g. POSTGRES_CONNECTION_STRING)
    available_env_var: str | None   # What the project has (e.g. DATABASE_URL), or None
    source: str                     # Where found: ".env", "docker-compose.yml", "not found"
    status: str                     # "exact_match", "compatible_match", "missing"
    help_url: str                   # Where to create the credential (e.g. GitHub tokens page)
```

### New module: `src/mcp_tap/scanner/credentials.py`

Responsible for:
1. Taking a `ProjectProfile` (with `env_var_names`) and a list of `ServerRecommendation`
2. Looking up each recommendation's required env vars (from Registry API data or static mapping)
3. Matching required vars against available vars using:
   - **Exact match**: `SLACK_BOT_TOKEN` required, `SLACK_BOT_TOKEN` found in `.env`
   - **Compatible match**: `POSTGRES_CONNECTION_STRING` required, `DATABASE_URL` found — same type of credential
   - **Missing**: No match found
4. Returning a list of `CredentialMapping` for each recommendation

### Compatibility mapping table

Static knowledge about which env var names are interchangeable:

```python
COMPATIBLE_VARS: dict[str, list[str]] = {
    # Required var → list of compatible alternatives
    "POSTGRES_CONNECTION_STRING": ["DATABASE_URL", "POSTGRES_URL", "PG_URL", "PG_CONNECTION_STRING"],
    "GITHUB_TOKEN": ["GH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"],
    "SLACK_BOT_TOKEN": ["SLACK_TOKEN", "SLACK_API_TOKEN"],
    "REDIS_URL": ["REDIS_CONNECTION_STRING", "REDIS_HOST"],
    "MONGODB_URI": ["MONGO_URL", "MONGODB_URL", "MONGO_URI"],
    "MYSQL_CONNECTION_STRING": ["MYSQL_URL", "DATABASE_URL"],
}
```

### Help URL mapping

Static mapping from env var patterns to creation help pages:

```python
CREDENTIAL_HELP: dict[str, str] = {
    "GITHUB_TOKEN": "https://github.com/settings/tokens/new",
    "SLACK_BOT_TOKEN": "https://api.slack.com/apps",
    "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
}
```

### Integration into `scan_project`

After `recommend_servers()`, call `map_credentials()` to produce credential mappings. Include them in the scan result:

```python
# In tools/scan.py
return {
    "path": profile.path,
    "detected_technologies": technologies,
    "env_vars_found": profile.env_var_names,
    "recommendations": recommendations,
    "credential_mappings": credential_mappings,   # NEW
    "already_installed": already_installed,
    "summary": summary,
}
```

### Integration into `configure_server`

When `env_vars` is empty, auto-populate from credential mappings:
- If `scan_project` detected `DATABASE_URL` and the server needs `POSTGRES_CONNECTION_STRING`, and both are available in the environment → auto-map
- The tool should NOT read credential VALUES — only report the mapping to the LLM, which asks the user

### Integration into `search_servers`

Enrich search results with credential availability when `project_path` is provided:

```python
# Each result gets:
{
    "name": "postgres-mcp",
    "env_vars_required": ["POSTGRES_CONNECTION_STRING"],
    "credential_status": "available",       # NEW: available/partial/missing
    "credential_details": [                 # NEW
        {
            "required": "POSTGRES_CONNECTION_STRING",
            "available_as": "DATABASE_URL",
            "source": ".env"
        }
    ]
}
```

## Scope

1. `src/mcp_tap/models.py` — Add `CredentialMapping` dataclass
2. `src/mcp_tap/scanner/credentials.py` — NEW: credential mapping logic
3. `src/mcp_tap/scanner/recommendations.py` — Add required env vars to `ServerRecommendation`
4. `src/mcp_tap/tools/scan.py` — Include credential mappings in output
5. `src/mcp_tap/tools/search.py` — Enrich results with credential status
6. `tests/test_credentials.py` — NEW: tests for credential mapping

## Test Plan

- [ ] Exact match: `SLACK_BOT_TOKEN` found when `SLACK_BOT_TOKEN` required → status `exact_match`
- [ ] Compatible match: `DATABASE_URL` found when `POSTGRES_CONNECTION_STRING` required → status `compatible_match`
- [ ] Missing: no match for `GITHUB_TOKEN` → status `missing`, help_url populated
- [ ] scan_project includes credential_mappings in output
- [ ] search_servers includes credential_status when project_path provided
- [ ] No credential VALUES are ever read or returned (only names)
- [ ] All 320+ existing tests still pass

## Root Cause

`scan_project` and `search_servers` operate in isolation — scan detects env vars, search lists required vars, but nothing connects the two.

## Solution

Implemented `scanner/credentials.py` with static compatibility mapping (COMPATIBLE_VARS), help URL mapping (CREDENTIAL_HELP), and server-to-env-var mapping (SERVER_ENV_VARS). The `map_credentials()` function matches required env vars against available project vars using exact match, compatible match, or missing status. Integrated into `scan_project` (adds `credential_mappings` to output) and `search_servers` (adds `credential_status` + `credential_details` per result when `project_path` is provided).

## Files Changed

- `src/mcp_tap/models.py` — Added `CredentialMapping` dataclass
- `src/mcp_tap/scanner/credentials.py` — NEW: credential mapping logic
- `src/mcp_tap/tools/scan.py` — Include credential mappings in output
- `src/mcp_tap/tools/search.py` — Add credential status when project_path provided
- `tests/test_credentials.py` — NEW: 20 tests

## Lessons Learned

Static compatibility mapping is surprisingly effective for common env var patterns. The reverse lookup (checking if `required` is itself a compatible name) catches edge cases.
