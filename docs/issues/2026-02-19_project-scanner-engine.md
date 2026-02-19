# Project Scanner — File Detection Engine

- **Date**: 2026-02-19
- **Status**: `open`
- **Branch**: `feature/2026-02-19-project-scanner`
- **Priority**: `critical`
- **Issue**: #1

## Problem

mcp-tap's #1 differentiator — "scan your project and recommend servers" — does not exist. Without it, the product is just a CLI package manager wrapped in MCP protocol. The killer demo from the creative brief ("I scanned your project and found PostgreSQL, Slack, GitHub...") is impossible to run.

## Context

- The creative brief positions project-aware setup as THE headline feature
- All 5 existing tools are functional but none provide project intelligence
- This is pure file-parsing logic with zero external dependencies — easy to test, zero API risk
- Must produce a `ProjectProfile` that other tools can consume

## Scope

### New module: `src/mcp_tap/scanner/`

1. **File parsers** (`scanner/detector.py`):
   - `package.json` → Node.js, frameworks (next, express, react), deps (pg, redis, slack-bolt)
   - `pyproject.toml` / `requirements.txt` → Python, frameworks (fastapi, django, flask), deps
   - `docker-compose.yml` → services (postgres, redis, elasticsearch, mongo, rabbitmq)
   - `.env` / `.env.example` → existing env var names (detect tokens, keys, URLs)
   - `Gemfile` → Ruby, Rails
   - `go.mod` → Go
   - `Cargo.toml` → Rust
   - `Makefile` → build tool detection
   - `.github/` → GitHub presence
   - `vercel.json` / `netlify.toml` → deployment platform

2. **New domain models** (add to `models.py`):
   - `DetectedTechnology(name, category, source_file, confidence)`
   - `ProjectProfile(path, technologies, env_var_names, detected_services)`
   - Categories: `language`, `framework`, `database`, `service`, `platform`

3. **Recommendation mapping** (`scanner/recommendations.py`):
   - Static mapping: detected technology → recommended MCP server package
   - Example: `postgres` → `@modelcontextprotocol/server-postgres`
   - Returns ranked list with reason ("Found PostgreSQL in docker-compose.yml")

### Tests
   - Fixture directories with sample project files
   - Test each parser individually
   - Test full scan with mixed project

## Root Cause

N/A — greenfield feature

## Solution

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] Tests pass: `pytest tests/`
- [ ] Linter passes: `ruff check src/ tests/`
- [ ] Scanner detects at least 5 different technology types from fixture projects
- [ ] `ProjectProfile` is a frozen dataclass following existing patterns
