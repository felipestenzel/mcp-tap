# I5 — Workflow Understanding (Git + CI Analysis)

- **Date**: 2026-02-20
- **Status**: `done`
- **Branch**: `feature/2026-02-20-workflow-understanding`
- **Priority**: `high`

## Problem

scan_project only does static file detection (package.json, pyproject.toml, docker-compose, .env).
It misses technologies and services used in CI/CD pipelines, deployment targets, and workflow
patterns that would generate better MCP server recommendations.

For example:
- A project using PostgreSQL in GitHub Actions `services:` but not in docker-compose won't
  get a postgres MCP recommendation
- A project deploying to AWS via GitHub Actions won't get AWS-related recommendations
- A project using Terraform/Ansible for infrastructure won't be detected

## Context

- Roadmap item I5 from `docs/issues/2026-02-19_premium-quality-roadmap.md`
- Impact: 8/10, Effort: L
- No external dependencies required
- Differentiator: every competitor does static file scan. Workflow analysis is defensible.

## Solution

### New module: `src/mcp_tap/scanner/workflow.py`

Parses CI/CD configs to extract:
1. **GitHub Actions** (`.github/workflows/*.yml`):
   - `services:` blocks → databases/caches (postgres, redis, mongo, mysql, elasticsearch)
   - `uses:` actions → deployment targets (aws, gcp, azure, vercel, netlify, docker)
   - `run:` commands → tools used (terraform, ansible, kubectl, helm)
   - `env:` blocks → environment variable patterns
2. **GitLab CI** (`.gitlab-ci.yml`):
   - `services:` → databases/caches
   - `image:` → container technologies
   - `stage:` → deployment stages
3. **Git metadata** (via `.git/` parsing, NO subprocess calls):
   - Last commit timestamp → project activity (stale detection)
   - Only if `.git/` exists; graceful skip otherwise

### New model in `models.py`

```python
@dataclass(frozen=True, slots=True)
class WorkflowSignal:
    technology: str           # e.g., "postgresql", "aws", "terraform"
    source: str              # e.g., ".github/workflows/test.yml"
    signal_type: str         # "ci_service" | "deploy_target" | "ci_tool"
    confidence: float        # 0.0-1.0 (CI services = 0.9, inferred = 0.7)
```

### Integration

- `detector.scan_project()` calls workflow analysis alongside existing parsers
- WorkflowSignals converted to `DetectedTechnology` with appropriate confidence
- Existing `recommendations.py` mapping automatically picks them up
- No changes to tool interface — scan_project returns same structure, enriched

### Design principles

- All async, runs in parallel with existing parsers
- No subprocess calls (parse files only, no `git log`)
- Defensive: malformed YAML skipped with logging
- Low confidence (0.7-0.9) since CI configs may not reflect production

## Files Changed

- `src/mcp_tap/scanner/workflow.py` — NEW: CI/CD config parser
- `src/mcp_tap/scanner/__init__.py` — Export new module
- `src/mcp_tap/scanner/detector.py` — Integrate workflow parser
- `src/mcp_tap/models.py` — Add WorkflowSignal model
- `tests/test_workflow.py` — NEW: Comprehensive tests

## Verification

- [x] Tests pass: `pytest tests/` — 933 passing (800 → 933, +133 new)
- [x] Linter passes: `ruff check src/ tests/`
- [x] GitHub Actions YAML parsing works correctly (107 workflow tests)
- [x] GitLab CI YAML parsing works correctly
- [x] Workflow-detected technologies appear in scan results
- [x] Existing tests unaffected (800 baseline still passing)
