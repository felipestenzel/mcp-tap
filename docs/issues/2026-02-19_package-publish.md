# Package and Publish — PyPI + npm Wrapper

- **Date**: 2026-02-19
- **Status**: `in-progress`
- **Branch**: `feature/2026-02-19-publish`
- **Priority**: `medium`
- **Issue**: #9

## Problem

mcp-tap cannot be installed by end users yet. `uvx mcp-tap` and `pip install mcp-tap` need to work flawlessly. The README needs real install instructions and a demo GIF. An npm wrapper would extend reach to JS developers.

## Context

- This is the LAST issue before launch — ship only when the product delivers on its promise
- Publishing a half-built tool kills the one chance at a first impression on Hacker News
- `pyproject.toml` entry point and hatchling build system already configured
- The creative brief recommends both `uvx mcp-tap` and `npx mcp-tap`

## Scope

1. **Verify PyPI packaging**:
   - `pip install -e .` works locally
   - `python -m build` creates correct wheel
   - Entry point `mcp-tap` runs the server
   - `uvx mcp-tap` works (test in clean venv)

2. **npm wrapper** (optional, stretch goal):
   - Thin npm package that checks for `uvx`/`pip` and runs the Python package
   - `npx mcp-tap` would work for JS developers
   - `package.json` + `bin/mcp-tap` shell script

3. **Update README.md**:
   - Full install instructions (Claude Desktop, Cursor, Windsurf, Claude Code)
   - Before/After comparison from creative brief
   - "What can it do?" table with all tools
   - Demo GIF placeholder (record after all features work)
   - No badges until first release (avoid "12 badges, zero users" look)

4. **PyPI publish**:
   - `hatch build && hatch publish`
   - Verify on pypi.org

5. **GitHub Release**:
   - Tag v0.1.0
   - Release notes

## Root Cause

N/A — final packaging step.

## Solution

1. Rewrote README.md with full launch content: tagline, before/after comparison, per-client install instructions (Claude Desktop, Claude Code, Cursor, Windsurf), conversational "What can it do?" table, tool reference, features list.
2. Verified `uv build` produces correct wheel with all modules and entry point.
3. Confirmed entry point `mcp-tap = mcp_tap:main` works.
4. npm wrapper deferred — not needed for v0.1.0 (Python-only launch).
5. PyPI publish and GitHub release to be done manually by maintainer.

## Files Changed

- `README.md` — Full rewrite for v0.1.0 launch
- `docs/issues/2026-02-19_package-publish.md` — Status update

## Verification

- [x] `uv build` creates correct wheel (`mcp_tap-0.1.0-py3-none-any.whl`)
- [x] Wheel contains all modules (32 files including scanner, tools, config, etc.)
- [x] Entry point `mcp-tap = mcp_tap:main` present in `entry_points.txt`
- [x] Import from wheel works (`version=0.1.0`)
- [x] README has complete install instructions for all 4 clients
- [x] 320 tests passing, ruff clean
- [ ] `pip install mcp-tap` from PyPI (pending publish)
- [ ] `uvx mcp-tap` from PyPI (pending publish)
- [ ] PyPI page shows correct metadata (pending publish)
