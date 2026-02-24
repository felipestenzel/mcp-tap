# Candidate Evaluation — Compare Server Alternatives by Maturity

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-v02-roadmap`
- **Priority**: `medium`
- **Issue**: #13

## Problem

`search_servers` returns results from the MCP Registry ranked by keyword relevance and project stack match. But when multiple servers serve the same need (e.g., 4 PostgreSQL MCP servers), the user has no data to choose between them. They must leave the conversation, visit each GitHub repo, and manually compare stars, last update, maintenance status, and feature set.

The original issue (adenhq/hive#4527) describes this in the `evaluate_candidates` node:

> "When two candidate servers provide overlapping functionality, evaluate maturity (GitHub stars, last update, open issues) and recommend the one that better fits your architecture."

> "I also looked at @alternative/pg-tools but it hasn't been updated in 5 months. Skipping."

That single line — showing the agent REJECTING a candidate with reasoning — is what builds user trust.

## Context

- **Module affected**: `tools/search.py`, `registry/client.py`, new `evaluation/` module
- **Existing infrastructure**:
  - `SearchResult` already has `repository_url`, `updated_at`, `is_official`
  - `RegistryServer` already has `version`, `packages` (with transport and env vars)
  - `search_servers` already accepts `project_path` for relevance scoring
  - `scanner/scoring.py` already has `score_result()` for project relevance
- **Data sources available**:
  - MCP Registry API: `updated_at`, `version`, `is_official` (already fetched)
  - GitHub API: stars, forks, open issues, last commit date (NOT currently fetched)
  - npm/PyPI: weekly downloads (NOT currently fetched)

## Architecture

### New module: `src/mcp_tap/evaluation/`

```
src/mcp_tap/evaluation/
├── __init__.py
├── github.py       # Fetch repo metadata from GitHub API
└── scorer.py       # Compute maturity score from multiple signals
```

### Maturity signals and scoring

```python
@dataclass(frozen=True, slots=True)
class MaturitySignals:
    """Raw signals collected about a server's maturity/health."""
    stars: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    last_commit_date: str | None = None      # ISO 8601
    last_release_date: str | None = None     # ISO 8601
    is_official: bool = False                 # From MCP Registry
    is_archived: bool = False                 # From GitHub API
    license: str | None = None
    weekly_downloads: int | None = None       # From npm/PyPI (stretch)

@dataclass(frozen=True, slots=True)
class MaturityScore:
    """Computed maturity assessment for a server."""
    score: float               # 0.0-1.0 composite score
    tier: str                  # "recommended", "acceptable", "caution", "avoid"
    reasons: list[str]         # Human-readable reasons for the score
    warning: str | None        # Warning if there's a red flag (archived, stale, etc.)
```

Scoring formula:
- **is_official**: +0.3 (official MCP servers are curated)
- **stars**: +0.0-0.2 (log scale: 0→0, 100→0.1, 1000→0.15, 5000+→0.2)
- **last_commit_date**: +0.0-0.3 (within 30 days→0.3, 90 days→0.2, 180 days→0.1, older→0)
- **is_archived**: -0.5 (archived repos should be flagged)
- **open_issues > 50**: -0.1 (potential maintenance burden)

Tier thresholds:
- **recommended**: score ≥ 0.6
- **acceptable**: score ≥ 0.4
- **caution**: score ≥ 0.2
- **avoid**: score < 0.2

### GitHub API integration (`github.py`)

```python
async def fetch_repo_metadata(
    repository_url: str,
    http_client: httpx.AsyncClient,
) -> MaturitySignals | None:
    """Fetch repository metadata from GitHub's public API.

    Uses unauthenticated requests (60 req/hour limit).
    Returns None if the URL is not a GitHub repo or the API fails.

    Converts: https://github.com/owner/repo → GET /repos/owner/repo
    """
```

Rate limiting considerations:
- GitHub public API: 60 requests/hour without auth
- A typical `search_servers` call returns 5-10 results → 5-10 API calls
- Cache results for the session (in-memory, not persisted)
- Graceful degradation: if rate-limited, return results without maturity data

### Integration into `search_servers`

Add optional `evaluate: bool = True` parameter:

```python
async def search_servers(
    query: str,
    ctx: Context,
    limit: int = 10,
    project_path: str | None = None,
    evaluate: bool = True,          # NEW
) -> list[dict[str, object]]:
```

When `evaluate=True`:
1. Run normal search
2. For each result with a `repository_url`, fetch maturity signals
3. Compute maturity scores
4. Add `maturity` field to each result:

```python
{
    "name": "@modelcontextprotocol/server-postgres",
    "description": "...",
    "relevance": "high",
    "maturity": {                          # NEW
        "score": 0.85,
        "tier": "recommended",
        "stars": 2300,
        "last_commit": "3 days ago",
        "reasons": [
            "Official MCP server",
            "2.3k stars",
            "Active development (last commit 3 days ago)"
        ],
    },
}
```

5. Sort results by: relevance (primary) → maturity score (secondary)

When `evaluate=False`: skip GitHub API calls (faster, no rate limit risk).

### Comparison output

When multiple servers match the same need, the tool should output a comparison:

```python
{
    "comparison": {
        "category": "postgresql",
        "recommended": "@modelcontextprotocol/server-postgres",
        "alternatives": [
            {
                "name": "@alternative/pg-tools",
                "maturity": {"tier": "caution", "score": 0.25},
                "reason_not_recommended": "Last updated 5 months ago, 3 open issues with no response"
            }
        ]
    }
}
```

## Scope

1. `src/mcp_tap/models.py` — Add `MaturitySignals`, `MaturityScore` dataclasses
2. `src/mcp_tap/evaluation/__init__.py` — NEW
3. `src/mcp_tap/evaluation/github.py` — NEW: GitHub API metadata fetcher
4. `src/mcp_tap/evaluation/scorer.py` — NEW: maturity scoring logic
5. `src/mcp_tap/tools/search.py` — Add `evaluate` param, integrate maturity scoring
6. `tests/test_evaluation.py` — NEW: tests for GitHub fetcher and scorer

## Test Plan

- [ ] GitHub URL → API path conversion correct (handles various URL formats)
- [ ] MaturitySignals populated from mocked GitHub API response
- [ ] Scoring: official server with recent commits scores ≥ 0.6
- [ ] Scoring: archived repo scores < 0.2
- [ ] Scoring: stale repo (6+ months) gets "caution" tier
- [ ] search_servers with evaluate=True includes maturity in results
- [ ] search_servers with evaluate=False skips maturity (faster)
- [ ] Rate limit handling: graceful degradation when GitHub API returns 429
- [ ] All httpx calls are mocked (tests run offline)
- [ ] All 320+ existing tests still pass

## Root Cause

`search_servers` returns results without maturity context. The user cannot distinguish between a well-maintained official server and an abandoned fork without leaving the conversation.

## Solution

Implemented `evaluation/` module with `github.py` (public API metadata fetcher, unauthenticated) and `scorer.py` (composite scoring: official +0.3, stars log-scale up to +0.2, activity recency up to +0.3, archived -0.5, high issues -0.1). Tiers: recommended/acceptable/caution/avoid. Integrated into `search_servers` with `evaluate: bool = True` parameter — fetches signals concurrently for all results, deduplicates by repo URL.

## Files Changed

- `src/mcp_tap/models.py` — Added `MaturitySignals`, `MaturityScore` dataclasses
- `src/mcp_tap/evaluation/__init__.py` — NEW
- `src/mcp_tap/evaluation/github.py` — NEW: GitHub API metadata fetcher
- `src/mcp_tap/evaluation/scorer.py` — NEW: maturity scoring logic
- `src/mcp_tap/tools/search.py` — Added `evaluate` param, maturity integration
- `tests/test_evaluation.py` — NEW: 23 tests

## Lessons Learned

Log-scale scoring for stars prevents popular repos from dominating. Activity recency (30/90/180 day buckets) is the most useful signal for maintenance status.
