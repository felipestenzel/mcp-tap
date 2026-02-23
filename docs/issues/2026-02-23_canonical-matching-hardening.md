# Canonical Matching Hardening + Governance Guardrails

- **Date**: 2026-02-23
- **Status**: `done`
- **Branch**: `feature/2026-02-23-canonical-matching-hardening`
- **Priority**: `high`

## Problem

Ainda existem gaps entre o lockfile canônico e o estado real do cliente MCP:

- `verify` ainda pode gerar `MISSING/EXTRA` falsos quando o servidor instalado usa alias diferente
  (caso não-HTTP)
- `restore` reinstala servidores já presentes quando o alias local diverge do nome no lockfile
- `list_installed` não mostra identidade canônica quando o lockfile está disponível
- Lógica de equivalência está duplicada entre `scan`, `verify` e `restore`

Também há lacunas de processo:

- algumas issues ficaram em `in_progress` apesar de já entregues
- falta proteger `main` com regra obrigatória de PR + checks
- falta um smoke test orientado a release cobrindo fluxo crítico lockfile/config

## Context

- `docs/issues/2026-02-23_canonical-server-identity.md` já corrigiu a regressão HTTP do `verify`,
  mas deixou explícitos itens pendentes (alias canônico em verify/restore/list)
- histórico recente mostrou necessidade de reforçar governança para evitar bypass de PR
- já existe cobertura ampla unitária, mas faltam cenários e2e de release para drift semântico

## Root Cause

- `InstalledServer` não carrega identidade canônica por padrão e os consumidores não compartilham
  uma estratégia única de matching
- comparação por nome ainda é dominante em fluxos de lockfile
- governança depende mais de disciplina manual que de controles técnicos

## Solution

Implementação concluída em 5 frentes:

1. **Matching canônico unificado**
- Novo módulo `src/mcp_tap/config/matching.py` com helpers para:
  - equivalência HTTP (`HttpServerConfig` vs `mcp-remote URL`)
  - matching por `package_identifier`
  - resolução lockfile↔installed por nome + fallback canônico

2. **`verify`/`differ` com identidade canônica**
- `src/mcp_tap/lockfile/differ.py` agora usa matching canônico para evitar
  `MISSING/EXTRA` falsos por alias
- mantém drift real (`CONFIG_CHANGED`) quando URL/config realmente diverge

3. **`restore` sem reinstall desnecessário**
- `src/mcp_tap/tools/restore.py` detecta pacote já presente sob alias diferente
  e retorna `status: "already_installed"` sem reinstall

4. **`list_installed` enriquecido por lockfile**
- `src/mcp_tap/tools/list.py` recebeu `project_path` opcional
- quando lockfile existe, saída inclui `package_identifier`, `registry_type`,
  `repository_url` para cada servidor correspondente

5. **Hardening de processo**
- Branch protection de `main` aplicada via API:
  - required status checks: `lint`, `test (3.11)`, `test (3.12)`, `test (3.13)`
  - PR obrigatório (`required_pull_request_reviews` habilitado com 0 approvals)
  - `enforce_admins=true`
  - `required_conversation_resolution=true`
- Smoke tests de release adicionados em `tests/test_release_smoke.py`
- Issues pendentes de status foram atualizadas para `done`

## Files Changed

- `src/mcp_tap/models.py` — campos canônicos opcionais em `InstalledServer`
- `src/mcp_tap/config/matching.py` — módulo compartilhado de matching/equivalência
- `src/mcp_tap/lockfile/differ.py` — matching lockfile vs instalado por identidade canônica
- `src/mcp_tap/tools/restore.py` — skip de reinstall quando pacote canônico já existe
- `src/mcp_tap/tools/list.py` — enriquecimento canônico quando lockfile disponível
- `src/mcp_tap/tools/scan.py` — delegar matching para módulo compartilhado
- `tests/test_matching.py` — unit tests do matching compartilhado
- `tests/test_differ.py` — regressões alias/canonical + HTTP
- `tests/test_restore.py` — cenário `already_installed` por alias
- `tests/test_tools_list.py` — enriquecimento canônico com lockfile
- `tests/test_release_smoke.py` — smoke lockfile/config para release
- `docs/issues/2026-02-23_release-v063.md` — fechamento pós-release
- `docs/issues/2026-02-19_security-gate.md` — status/verification finalizados
- `docs/issues/2026-02-19_conversational-stacks.md` — status/verification finalizados
- `docs/issues/2026-02-21_streamable-http-configure.md` — status/verification finalizados
- `docs/issues/2026-02-23_canonical-server-identity.md` — fechamento da fase 2

## Verification

- [x] Tests pass: `pytest tests/` (1255 passed)
- [x] Linter passes: `ruff check src/ tests/ && ruff format --check src/ tests/`
- [x] `verify`: alias diferente com mesma canonical key não gera `MISSING/EXTRA`
- [x] `restore`: pacote já instalado sob alias diferente retorna `already_installed`/skip
- [x] `list_installed`: mostra `package_identifier`/`registry_type`/`repository_url` quando possível
- [x] Branch protection ativa para `main` exigindo PR e checks de CI
- [x] Smoke release test cobre caminho crítico lockfile/config

## Lessons Learned

(Optional)
