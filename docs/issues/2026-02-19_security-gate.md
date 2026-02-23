# I2 — Security Gate: Pre-install safety checks

- **Date**: 2026-02-19
- **Status**: `done`
- **Branch**: `feature/2026-02-19-security-gate`
- **Priority**: `high`

## Problem

MCP servers are installed without any safety verification. A malicious or abandoned
package can be installed with no warning. Existing scanners check post-install — we
should check BEFORE install.

## Context

- Roadmap item I2 in `docs/issues/2026-02-19_premium-quality-roadmap.md`
- Impact: 9/10 | Effort: M
- No other MCP tool does pre-install security checks
- Can reuse existing `evaluation/github.py` for GitHub signals

## Solution

New `src/mcp_tap/security/` module with pre-install gate integrated into `configure_server`.

### Security signals to check:
1. **Repository age** — repos < 30 days old are suspicious
2. **Stars** — very low stars (< 5) for non-new repos is a warning
3. **Archived** — archived repos should not be installed
4. **License** — missing license is a warning
5. **Package age on registry** — new packages with no history are risky
6. **Known risky patterns** — shell=True in server command, suspicious env vars

### Risk levels:
- `pass` — no issues found
- `warn` — advisory warnings (proceed with caution)
- `block` — installation should be blocked (user can override)

## Files Changed

- `src/mcp_tap/security/gate.py` — motor do gate de segurança
- `src/mcp_tap/tools/configure.py` — integração do gate antes da escrita de config
- `tests/test_security_gate.py` — cobertura de bloqueios/avisos e integração

## Verification

- [x] Tests pass: `pytest tests/`
- [x] Linter passes: `ruff check src/ tests/`
- [x] Security gate blocks archived repos
- [x] Security gate warns on low-star repos
- [x] Security gate warns on very new repos
- [x] Integration with configure_server works
