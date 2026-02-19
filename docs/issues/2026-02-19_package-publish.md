# Package and Publish — PyPI + npm Wrapper

- **Date**: 2026-02-19
- **Status**: `open`
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

(Fill after implementation)

## Files Changed

(Fill after implementation)

## Verification

- [ ] `pip install mcp-tap` in clean venv works
- [ ] `uvx mcp-tap` starts the server
- [ ] `mcp-tap` entry point runs correctly
- [ ] README has complete install instructions
- [ ] PyPI page shows correct metadata
