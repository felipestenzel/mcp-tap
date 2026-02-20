# Handoff — v0.3.0 Release + Workflow Understanding + npm Publishing

- **Date**: 2026-02-20 03:10
- **Session context**: Continue roadmap implementation, publish v0.3.0
- **Context consumed**: ~55%

## What Was Done

### PR #31 — Workflow Understanding + Secret Masking + Protocols + npm Wrapper
- **I5**: `scanner/workflow.py` — CI/CD config parser (GitHub Actions + GitLab CI)
  - Detects databases, cloud providers (AWS/GCP/Azure), infrastructure tools (Terraform/K8s/Ansible)
  - Integrated into `scan_project` via `detector.py`
  - New recommendations for `aws` and `kubernetes` in `recommendations.py`
  - **+107 tests** in `tests/test_workflow.py`
- **L1**: `tools/list.py` — Layered secret masking (key hints → prefixes → high-entropy 40+)
  - **+26 tests** in `tests/test_tools_list.py`
- **A1**: 10 `base.py` Protocol files (16 Protocols total) across all adapter packages
- **D2**: `npm-wrapper/` — Thin Node.js shim for `npx mcp-tap` (uvx → pipx → python)
- **v0.3.0**: Version bump in `pyproject.toml`
- **Roadmap**: Updated `docs/issues/2026-02-19_premium-quality-roadmap.md` (I2, I3, I5, L1 marked DONE)

### PR #32 — npm Trusted Publishing
- `.github/workflows/publish.yml` — OIDC trusted publishing for both PyPI and npm
- No secrets/tokens needed; both registries use GitHub Actions OIDC

### v0.3.0 Release
- **PyPI**: Published automatically via trusted publisher ✅
- **npm**: Published manually via `npm publish --auth-type=web` ✅
- **GitHub Release**: https://github.com/felipestenzel/mcp-tap/releases/tag/v0.3.0

### npm Trusted Publisher Setup
- Configured on npmjs.com: Settings → Trusted Publisher → GitHub Actions
- felipestenzel / mcp-tap / publish.yml
- Next release will auto-publish to npm (no manual step needed)

## Where We Stopped

- **Branch**: `main` (clean, all PRs merged)
- **Tests**: 933 passing
- **Tools MCP**: 12
- **CI**: All green
- **Open PRs**: 0

## What To Do Next

### Quick fixes (before next release)

1. **npm README missing**: The npm package page shows "This package does not have a README."
   - Create `npm-wrapper/README.md` with install instructions and link to main repo
   - This will be included automatically on next `npm publish` (it's in `package.json` files array)

2. **Verify npm auto-publish works**: Create a v0.3.1 patch release to test the
   full automated flow (PyPI + npm publishing from tag push)

### Roadmap items remaining (ref: `docs/issues/2026-02-19_premium-quality-roadmap.md`)

#### Code tasks
3. **A2** — DI wiring in `server.py` (Large)
   - Expand `AppContext` with stateful adapters (GitHubMetadata, SecurityGate)
   - Pragmatic: only worth it for HTTP-dependent adapters, not stateless functions
   - Protocols already defined (A1 done)

4. **A4** — Anemic domain model (Medium)
   - Move validations/transformations from tools into domain models
   - Low priority — functional but not elegant

5. **M5** — `shutil.which()` sync in healing (Trivial, accepted as debt)

#### Human tasks (CRITICAL for adoption)
6. **D1** — Demo GIF 20-30s (Impact 10/10)
   - **MOST IMPORTANT for GitHub stars**. README sem demo não converte.
   - Record: scan_project → search → configure → test_connection flow
   - Tools: asciinema, vhs, or screen recording + gif conversion

7. **D3** — Submit to awesome-mcp-servers + Reddit/HN posts (Impact 8/10)
   - https://github.com/punkpeye/awesome-mcp-servers — submit PR
   - Reddit: r/MachineLearning, r/ChatGPT, r/ClaudeAI
   - HN: Show HN post

8. **D4** — Narrativa "mcp-installer successor" (Impact 8/10)
   - mcp-installer tem 1504 stars e está morto desde Nov/2024
   - Posicionar mcp-tap como o sucessor natural

### Release checklist (for future releases)
1. Bump version in `pyproject.toml`
2. `npm-wrapper/package.json` version syncs automatically from git tag in CI
3. `gh release create vX.Y.Z --title "..." --notes "..."`
4. Verify: `pip index versions mcp-tap` (PyPI) and `npm view mcp-tap version` (npm)

## Open Questions / Blockers

1. **npm auto-publish untested**: OIDC trusted publishing is configured but hasn't been
   tested with a real release yet. First test will be v0.3.1.
2. **npm README**: Currently empty on npmjs.com. Needs `npm-wrapper/README.md`.
3. **npm `package.json` warning**: npm auto-corrects `bin[mcp-tap]` script name on publish.
   Run `npm pkg fix` in `npm-wrapper/` to clean this up.

## Files Modified This Session

### PR #31 (merged)
- `pyproject.toml` — version bump to 0.3.0
- `src/mcp_tap/scanner/workflow.py` — NEW: CI/CD config parser
- `src/mcp_tap/scanner/detector.py` — integrate workflow parser
- `src/mcp_tap/scanner/recommendations.py` — add aws/kubernetes mappings
- `src/mcp_tap/tools/list.py` — layered secret masking
- `src/mcp_tap/{config,connection,evaluation,healing,inspector,lockfile,registry,scanner,security,stacks}/base.py` — NEW: 10 Protocol files
- `npm-wrapper/package.json` + `npm-wrapper/bin/mcp-tap.js` — NEW: npm wrapper
- `tests/test_workflow.py` — NEW: 107 tests
- `tests/test_tools_list.py` — +26 tests
- `docs/issues/2026-02-20_workflow-understanding.md` — NEW: issue doc
- `docs/issues/2026-02-19_premium-quality-roadmap.md` — updated status

### PR #32 (merged)
- `.github/workflows/publish.yml` — OIDC trusted publishing for npm

## Quick Start for Next Session

```
Leia docs/handoff/2026-02-20_0310_v030-release-workflow-npm.md
e docs/issues/2026-02-19_premium-quality-roadmap.md para contexto.
Branch: main (limpa, 933 testes, 12 tools, v0.3.0 publicada)
Próximo rápido: npm README + v0.3.1 para testar auto-publish.
Próximo grande: D1 (demo GIF) é o mais importante para adoção.
Tarefas de código: A2 (DI wiring) ou A4 (domain model).
Delete este handoff após resumir com sucesso.
```
