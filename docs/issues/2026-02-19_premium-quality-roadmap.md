# Premium Quality Roadmap — mcp-tap para nível de produto cobrável

- **Date**: 2026-02-19
- **Status**: `open` (Fase 0 DONE, Fase 2 in progress)
- **Branch**: `fix/2026-02-19-production-resilience` (Fase 0), `feature/2026-02-19-differentiation` (Fase 2)
- **Priority**: `critical`

## Contexto

Avaliação completa do mcp-tap v0.2.4 por 4 agentes especializados rodando em paralelo:
- **product-strategy-advisor** — Posicionamento, monetização, competição
- **clean-architecture-designer** — Qualidade arquitetural (nota 6.7/10)
- **innovation-lab** — Features diferenciadores
- **perf-optimizer** — Resiliência e confiabilidade de produção

Resultado consolidado: o mcp-tap é tecnicamente bom mas tem 4 gaps estruturais
que impedem ser premium: (1) zero distribuição, (2) 4 bugs críticos de resiliência,
(3) falta de diferenciação defensável, (4) arquitetura incompleta.

---

## Workstream 1: Resiliência de Produção (CRÍTICO)

> **Agentes**: `perf-optimizer` + `python-craftsman` + `test-architect`

Sem corrigir esses 4 problemas, o produto não é confiável para uso real.

### C1. Race Condition no Config Writer — sem file locking ✅ DONE
- **Commit**: `d13c541` (branch `fix/2026-02-19-production-resilience`)
- **Fix aplicado**: `threading.Lock` per-path + `fcntl.flock(LOCK_EX)` + `tempfile.mkstemp()` para temp files únicos
- **Testes**: 5 novos (concurrent writes, lock file creation, unique temp files)

### C2. GitHub API Rate Limit — 60 req/hr sem cache nem aviso ✅ DONE
- **Commit**: `d13c541`
- **Fix aplicado**: Cache LRU TTL 15min, detecção `X-RateLimit-Remaining: 0`, `GITHUB_TOKEN` support, `asyncio.Semaphore(5)`
- **Testes**: 14 novos (cache hit/miss/TTL, rate limit detect/reset, headers, integration)

### C3. Processos Órfãos — kill() não mata filhos ✅ DONE
- **Commit**: `d13c541`
- **Fix aplicado**: `start_new_session=True` + `os.killpg(SIGKILL)` com fallback `proc.kill()`
- **Testes**: 13 novos (killpg, fallbacks ProcessLookupError/OSError, normal execution)

### C4. check_health sem limite de concorrência ✅ DONE
- **Commit**: `d13c541`
- **Fix aplicado**: `asyncio.Semaphore(5)` via `_MAX_CONCURRENT_CHECKS` + `_limited_check` wrapper
- **Testes**: 4 novos (constant value, concurrency limit tracking, failure handling)

### Problemas ALTOS adicionais:

#### H1. Zero retries em chamadas HTTP ✅ DONE
- **Commit**: `d13c541`
- **Fix aplicado**: `httpx.AsyncHTTPTransport(retries=3)` no `server.py` lifespan
- **Testes**: 5 novos (transport retries, timeout config, follow_redirects, lifecycle)

#### H2. Healing loop spawna até 7 processos por servidor
- **Arquivo**: `src/mcp_tap/tools/configure.py` (linhas 147-205)
- **Fix**: Reutilizar erro original em `_try_heal`, reduzir max_attempts de 3 para 2.
- **Esforço**: S

#### H3. configure_server não é transacional
- **Arquivo**: `src/mcp_tap/tools/configure.py`
- **Problema**: Config é escrito mesmo se validação falha. `success=True` com
  `validation_passed=False` é enganoso.
- **Fix**: Status mais granular ou rollback da config entry se validação falha.
- **Esforço**: M

#### H4. Connection tester — cleanup incerto no timeout
- **Arquivo**: `src/mcp_tap/connection/tester.py` (linhas 23-63)
- **Problema**: Se o shutdown do `stdio_client` travar, processo pode ficar pendurado.
- **Fix**: Verificar se `stdio_client.__aexit__` tem timeout interno, adicionar fallback.
- **Esforço**: M

---

## Workstream 2: Arquitetura para Enterprise (nota atual: 6.7/10)

> **Agentes**: `clean-architecture-designer` + `python-craftsman` + `refactoring-specialist`

### A1. Ports/Protocols formais ausentes (6/7 adapters)
- **Problema**: Apenas `installer/base.py` tem Protocol. Os adapters de registry,
  config (reader/writer/detection), connection, scanner, evaluation, inspector
  importam implementações concretas diretamente.
- **Fix**: Criar `Protocol` em `base.py` para cada adapter boundary.
- **Esforço**: L

### A2. Composition root incompleto
- **Problema**: `server.py` cria `RegistryClient` e `httpx.AsyncClient`, mas os tools
  importam adapters concretos diretamente (ex: `from mcp_tap.scanner.detector import scan_project`).
- **Fix**: Injetar dependências via lifespan context em `server.py`.
- **Esforço**: L

### A3. Testes patch-heavy por falta de DI
- **Problema**: Testes usam `unittest.mock.patch` excessivamente para substituir
  imports concretos. Com DI real, passariam mocks via construtor.
- **Fix**: Consequência de A1+A2 — corrigir ports resolve isso.
- **Esforço**: (incluso em A1+A2)

### A4. Modelo de domínio anêmico
- **Problema**: Dataclasses são puro dado sem comportamento. Lógica vive nos tools.
- **Fix**: Mover validações e transformações para os modelos onde fizer sentido.
- **Esforço**: M

---

## Workstream 3: Diferenciação Defensável (Innovation)

> **Agentes**: `innovation-lab` + `python-craftsman` + `test-architect`

### I1. MCP Lockfile (`mcp-tap.lock`)
- **O quê**: Arquivo que registra versões exatas, hashes, configs de todos os MCP servers.
  Como `package-lock.json` mas para MCP.
- **Por quê**: NINGUÉM faz isso. Quem define o formato primeiro, define o padrão.
  Resolve supply chain security (OWASP MCP03/04) + reproducibilidade + onboarding.
- **Impacto**: 10/10 | **Esforço**: M
- **Sem dependência externa**

### I2. Security Gate na instalação
- **O quê**: Antes de instalar um MCP server, verificar se é seguro (análise de permissões,
  package reputation, known vulnerabilities).
- **Por quê**: Scanners existem mas são pós-instalação. Segurança NO MOMENTO da install é único.
- **Impacto**: 9/10 | **Esforço**: M
- **Requer**: npmjs.com API (público) para package metadata

### I3. Stacks Conversacionais (`.mcp-tap.yaml`)
- **O quê**: Perfis compartilháveis de MCP servers. "Instale o stack de Data Science
  com uma frase."
- **Por quê**: mcp-compose faz composição manual. mcp-tap faz inteligente e conversacional.
  Cria network effects (UGC flywheel).
- **Impacto**: 8/10 | **Esforço**: M
- **Sem dependência externa**

### I4. Detecção de Conflitos de Tools
- **O quê**: Detectar quando dois MCP servers expõem tools com nomes iguais ou
  funcionalidades sobrepostas que confundem o LLM.
- **Por quê**: Problema real, não documentado em nenhum lugar, baixo esforço.
- **Impacto**: 7/10 | **Esforço**: S
- **Sem dependência externa**

### I5. Workflow Understanding (git + CI analysis)
- **O quê**: Ir além do scan estático — analisar git history e CI configs para
  entender workflows reais do projeto.
- **Por quê**: Todo concorrente faz file scan. Análise de workflow é defensável.
- **Impacto**: 8/10 | **Esforço**: L
- **Sem dependência externa**

---

## Workstream 4: Distribuição e Go-to-Market (MAIS IMPORTANTE)

> **Agentes**: Humano (Felipe) — não é trabalho de código

### D1. Demo GIF 20-30s (Before/After)
- SEM ISSO, NADA MAIS IMPORTA. README sem demo não converte.
- Esforço: S | Impacto: 10/10

### D2. npm wrapper (`npx mcp-tap`)
- 60-70% dos usuários MCP esperam npx. Wrapper fino que chama uvx.
- Esforço: M | Impacto: 9/10

### D3. Submit awesome-mcp-servers + posts Reddit/HN
- Distribuição grátis. O produto existe, precisa de eyeballs.
- Esforço: S | Impacto: 8/10

### D4. Narrativa "sucessor do mcp-installer"
- mcp-installer tem 1.504 stars e está morto desde Nov/2024. Ocupar esse espaço.
- Esforço: S | Impacto: 8/10

### D5. 3 Stacks pré-definidos (Data Science, Web Dev, DevOps)
- Dá algo compartilhável. "Instale o stack X com uma frase."
- Esforço: S | Impacto: 7/10

---

## Problemas MÉDIOS (quality of life)

| # | Problema | Arquivo | Fix | Esforço |
|---|---------|---------|-----|---------|
| M1 | httpx sem limites de pool | `server.py` | `Limits(max_connections=10)` | S |
| M2 | Config reader sync em async | `config/reader.py` | `asyncio.to_thread` | S |
| M3 | Env vars parser quebra com vírgula no valor | `tools/configure.py` | Documentar ou mudar delimitador | S |
| M4 | Import inline em loop | `tools/search.py:151` | Mover para topo do arquivo | Trivial |
| M5 | `shutil.which()` sync no healing | `healing/fixer.py` | Aceitar como debt | Trivial |
| L1 | Regex de segredos com falsos positivos | `tools/list.py` | Heurísticas por prefixo | S |

---

## Ordem de Execução Recomendada

### Fase 0: Stabilize ✅ COMPLETA (2026-02-19)
1. ✅ C3 — Processos órfãos
2. ✅ C4 — Semaphore no health check
3. ✅ C1 — File locking no config writer
4. ✅ C2 — Cache + rate limit do GitHub
5. ✅ H1 — HTTP retries
- **Branch**: `fix/2026-02-19-production-resilience`
- **Commit**: `d13c541`
- **Testes**: 498 → 542 (+44 novos cobrindo todos os 5 fixes)

### Fase 1: Distribute (2 semanas, PARALELO com Fase 0)
1. D1 — Demo GIF
2. D2 — npm wrapper
3. D3 — awesome-mcp-servers + Reddit
4. D4 — Narrativa mcp-installer successor

### Fase 2: Differentiate (2-3 semanas)
1. I4 — Detecção de conflitos de tools (S, quick win)
2. I1 — MCP Lockfile (M, define o padrão)
3. I3 — Stacks conversacionais (M, network effects)
4. I2 — Security gate (M, differentiator)

### Fase 3: Enterprise-Grade (ongoing)
1. A1+A2 — Ports formais + DI completo (L)
2. H3 — Configure transacional (M)
3. I5 — Workflow understanding (L)

---

## Riscos Estratégicos

1. **Anthropic absorve a funcionalidade** — Se Claude Code ganhar `mcp scan` nativo, game over.
   Timeline estimado: 6-12 meses. Mitigação: diferenciar com lockfile/security/stacks.
2. **API do Registry muda de novo** — Já aconteceu (issue 2026-02-19). Sem versioning.
   Mitigação: parsers defensivos + fallback para Smithery API.
3. **Python-only limita alcance** — Comunidade MCP é npm-first. Mitigação: npm wrapper.
4. **Zero users = zero feedback** — Construindo no escuro. Mitigação: Fase 1 urgente.
5. **Fadiga do ecossistema** — "Mais um gerenciador de MCP". Mitigação: posicionamento único
   ("dentro do assistente, não CLI").

---

## Métricas de Sucesso

| Fase | Métrica | Target |
|------|---------|--------|
| 0 | Testes de resiliência passando | 100% |
| 1 | GitHub stars | 50 em 30 dias |
| 1 | Issues de usuários reais | 10 em 30 dias |
| 2 | Downloads PyPI/semana | 100+ |
| 3 | Contribuidores externos | 3+ |
